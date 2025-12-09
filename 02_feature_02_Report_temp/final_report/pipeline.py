# pipeline_upgraded.py
# 검증 강화 버전 v2.0
# 주요 개선사항:
# 1. HS Code 기반 필터링 추가
# 2. Executive Summary 섹션 추가
# 3. 시장 리스크/규제/가격 섹션 출처 강제화
# 4. 데이터 관련성 검증 추가

import os
import asyncio
import logging
import re
import time
from typing import Dict, List, Optional, Callable, Any, Tuple
from dataclasses import dataclass, field

from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage
from langchain_core.documents import Document
from tavily import TavilyClient

from config import Config, DataLoader, Supervisor
from vectorstore import QdrantVectorDB
from logger import ResearchLogger
from prompts import get_section_prompt, FINAL_REPORT_PROMPT
from supervisor import StrategySelector

logger = logging.getLogger(__name__)

ProgressCallback = Callable[[str, str, float], None]

# ============================================================
# HS Code 카테고리 매핑 (신규 추가)
# ============================================================

HS_CODE_CATEGORIES = {
    # 음료류 (22XX)
    "2201": {"category": "음료", "keywords": ["음료", "물", "생수", "미네랄워터", "beverage", "water"]},
    "2202": {"category": "음료", "keywords": ["음료", "탄산", "청량음료", "주스", "에너지드링크", "beverage", "soft drink", "juice"]},
    "2203": {"category": "주류", "keywords": ["맥주", "beer", "주류"]},
    "2204": {"category": "주류", "keywords": ["와인", "포도주", "wine"]},
    "2205": {"category": "주류", "keywords": ["버뮤스", "vermouth"]},
    "2206": {"category": "주류", "keywords": ["발효주", "사과주", "cider"]},
    "2207": {"category": "주류", "keywords": ["에탄올", "알코올", "ethanol"]},
    "2208": {"category": "주류", "keywords": ["증류주", "위스키", "보드카", "소주", "spirits", "whisky"]},
    "2209": {"category": "식품", "keywords": ["식초", "vinegar"]},
    
    # 식품류 (일부 예시)
    "0901": {"category": "음료원료", "keywords": ["커피", "coffee"]},
    "0902": {"category": "음료원료", "keywords": ["차", "tea", "녹차"]},
    "1704": {"category": "과자", "keywords": ["과자", "사탕", "candy", "confectionery"]},
    "1806": {"category": "초콜릿", "keywords": ["초콜릿", "chocolate", "코코아"]},
    "1905": {"category": "빵류", "keywords": ["빵", "과자", "비스킷", "bread", "biscuit"]},
    
    # 항공기부품
    "8473": {"category": "전자부품", "keywords": ["컴퓨터부품", "전자부품", "computer parts"]},
    "8803": {"category": "항공기부품", "keywords": ["항공기", "항공", "부품", "aircraft", "aviation"]},
    
    # 자동차
    "8703": {"category": "자동차", "keywords": ["자동차", "승용차", "car", "automobile"]},
    "8708": {"category": "자동차부품", "keywords": ["자동차부품", "auto parts"]},
}

def get_hs_category(hs_code: str) -> Dict:
    """HS Code에서 카테고리 정보 추출"""
    # HS Code 정규화 (점, 공백 제거)
    hs_clean = re.sub(r'[.\s]', '', str(hs_code))
    
    # 4자리, 6자리, 10자리 순으로 매칭 시도
    for length in [4, 6, 2]:
        prefix = hs_clean[:length]
        if prefix in HS_CODE_CATEGORIES:
            return HS_CODE_CATEGORIES[prefix]
    
    # 기본값
    return {"category": "일반", "keywords": []}


def validate_content_relevance(content: str, hs_code: str, item: str) -> Dict:
    """
    콘텐츠가 HS Code/품목과 관련 있는지 검증
    
    Returns:
        {
            "relevant": bool,
            "score": float (0-1),
            "matched_keywords": list,
            "irrelevant_topics": list
        }
    """
    hs_info = get_hs_category(hs_code)
    keywords = hs_info.get("keywords", []) + [item]
    
    # 관련 키워드 매칭
    content_lower = content.lower()
    matched = [kw for kw in keywords if kw.lower() in content_lower]
    
    # 무관한 토픽 감지 (다른 카테고리 키워드)
    irrelevant_keywords = []
    for code, info in HS_CODE_CATEGORIES.items():
        if code[:2] != hs_code[:2]:  # 다른 대분류
            for kw in info.get("keywords", []):
                if kw.lower() in content_lower and kw not in keywords:
                    irrelevant_keywords.append(kw)
    
    # 점수 계산
    if not keywords:
        relevance_score = 0.5
    else:
        relevance_score = len(matched) / len(keywords)
    
    # 무관한 키워드가 많으면 점수 감소
    if irrelevant_keywords:
        penalty = min(len(irrelevant_keywords) * 0.1, 0.5)
        relevance_score = max(0, relevance_score - penalty)
    
    return {
        "relevant": relevance_score >= 0.3,
        "score": relevance_score,
        "matched_keywords": matched,
        "irrelevant_topics": list(set(irrelevant_keywords))
    }


# ============================================================
# 개선된 섹션 정의
# ============================================================

# 기본 섹션 (항상 생성)
BASE_SECTIONS = [
    ("summary", "요약 (Executive Summary)"),      # 신규 추가
    ("overview", "국가 및 시장 개요"),
    ("market_size", "시장 규모"),
    ("distribution", "유통 구조"),
]

# 분석 옵션 (선택적 또는 기본 포함)
ANALYSIS_OPTIONS = {
    "regulation": "규제 검토",
    "risk": "시장 리스크",
    "price": "가격 추세",
    "demand": "수요 전망",
}

# 항상 포함할 분석 섹션 (출처 필수)
MANDATORY_ANALYSIS = ["risk", "regulation", "price"]


class PipelineStage:
    """파이프라인 단계 정의"""
    INPUT_PARSING = "input_parsing" 
    QUERY_GENERATION = "query_generation"
    DRAFT_GENERATION = "draft_generation"
    KATI_VERIFICATION = "kati_verification"
    PDF_ENHANCEMENT = "pdf_enhancement"
    WEB_SEARCH = "web_search"
    EVALUATION = "evaluation"
    FINAL_REPORT = "final_report"


@dataclass
class SectionResult:
    """섹션 결과 - 단계별 버전 관리"""
    key: str
    title: str
    
    # 각 단계별 내용과 품질 점수
    draft: str = ""
    draft_score: int = 0
    
    kati_verified: str = ""
    kati_score: int = 0
    
    pdf_enhanced: str = ""
    pdf_score: int = 0
    
    web_enhanced: str = ""
    web_score: int = 0
    
    # 최종 선택된 버전
    final: str = ""
    final_score: int = 0
    final_version: str = ""
    
    # 관련성 검증 결과 (신규)
    relevance: Dict = field(default_factory=dict)
    
    citations: List[str] = field(default_factory=list)
    evaluation: Dict = field(default_factory=dict)
    success: bool = False


@dataclass
class PipelineState:
    """파이프라인 상태"""
    country: str
    country_code: str
    hs_code: str
    hs_code_clean: str = ""  # 신규: 정규화된 HS Code
    hs_category: Dict = field(default_factory=dict)  # 신규: HS 카테고리 정보
    item: str = ""
    options: List[str] = field(default_factory=list)
    sections: Dict[str, SectionResult] = field(default_factory=dict)
    final_report: str = ""
    all_citations: List[str] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)
    log_path: str = ""


class WebSearcher:
    """공공기관 전용 Tavily 검색"""
    
    def __init__(self):
        self.client = TavilyClient(api_key=Config.TAVILY_API_KEY) if Config.TAVILY_API_KEY else None
    
    def search_public_only(self, query: str, top_k: int = 5) -> List[Dict]:
        """공공기관 도메인만 검색"""
        if not self.client:
            return []
        
        try:
            enhanced_query = f"{query} site:go.kr OR site:gov OR site:or.kr OR site:kotra.or.kr"
            result = self.client.search(query=enhanced_query, max_results=top_k * 2)
            
            if not result or "results" not in result:
                return []
            
            filtered = []
            for r in result["results"]:
                url = r.get("url", "").lower()
                if any(domain in url for domain in Config.PUBLIC_DOMAINS):
                    filtered.append({
                        "content": r.get("content", ""),
                        "url": r.get("url", ""),
                        "title": r.get("title", ""),
                    })
            
            return filtered[:top_k]
        
        except Exception as e:
            logger.error(f"웹 검색 실패: {e}")
            return []


class ResearchPipelineUpgraded:
    """연구 파이프라인 - 검증 강화 버전 v2.0"""
    
    def __init__(self, vectordb: Optional[QdrantVectorDB] = None):
        self.vectordb = vectordb or QdrantVectorDB()
        self.web = WebSearcher()
        self.llm_fast = ChatOpenAI(model=Config.MODEL_FAST, temperature=0)
        self.llm_smart = ChatOpenAI(model=Config.MODEL_SMART, temperature=0)
        self.strategy_selector = StrategySelector()
        
        # 품질 기준
        self.MIN_SCORE = 70
        self.IMPROVEMENT_THRESHOLD = 5
        self.MIN_RELEVANCE_SCORE = 0.3  # 신규: 최소 관련성 점수
        
        self.research_logger: Optional[ResearchLogger] = None
        self.supervisor: Optional[Supervisor] = None
    
    def run(self, payload: Dict, callback: Optional[ProgressCallback] = None) -> Dict:
        """동기 실행"""
        return asyncio.run(self.run_async(payload, callback))
    
    async def run_async(self, payload: Dict, callback: Optional[ProgressCallback] = None) -> Dict:
        """비동기 실행"""
        
        # 로거 초기화
        self.research_logger = ResearchLogger()
        self.supervisor = Supervisor(self.research_logger)
        self.research_logger.log_user_input(payload)
        self.research_logger.log_stage_start(PipelineStage.INPUT_PARSING, payload)
        
        start_time = time.time()
        
        # 상태 초기화 (HS Code 정보 추가)
        country_name = payload.get("country", "미국")
        hs_code = payload.get("hs_code", "")
        hs_code_clean = re.sub(r'[.\s]', '', str(hs_code))
        
        state = PipelineState(
            country=country_name,
            country_code=DataLoader.normalize_country(country_name),
            hs_code=hs_code,
            hs_code_clean=hs_code_clean,
            hs_category=get_hs_category(hs_code),
            item=payload.get("item", "제품"),
            options=payload.get("options", []),
        )
        
        logger.info(f"📦 HS Code: {hs_code} → 카테고리: {state.hs_category.get('category', '일반')}")
        logger.info(f"🔍 관련 키워드: {state.hs_category.get('keywords', [])}")
        
        self.research_logger.log_stage_end(
            PipelineStage.INPUT_PARSING,
            {
                "country_code": state.country_code,
                "hs_code_clean": hs_code_clean,
                "hs_category": state.hs_category
            },
            (time.time() - start_time) * 1000
        )
        
        # ============================================================
        # 섹션 구성 (개선)
        # ============================================================
        sections_to_process = list(BASE_SECTIONS)  # 기본 섹션 복사
        
        # 필수 분석 섹션 추가
        for opt_key in MANDATORY_ANALYSIS:
            sections_to_process.append((opt_key, ANALYSIS_OPTIONS[opt_key]))
        
        # 추가 옵션 섹션
        for opt_key, opt_name in ANALYSIS_OPTIONS.items():
            if opt_key in state.options and opt_key not in MANDATORY_ANALYSIS:
                sections_to_process.append((opt_key, opt_name))
        
        total_steps = len(sections_to_process) * 4 + 1
        current = 0
        
        # 섹션별 처리
        for key, title in sections_to_process:
            section = SectionResult(key=key, title=title)
            
            self.research_logger.start_section(key, title)
            
            strategy = self.strategy_selector.get_strategy(key)
            logger.info(f"📋 섹션 {key}: {strategy['reason']}")
            
            # 섹션 처리 (HS Code 필터링 포함)
            await self._process_section_with_validation(
                section, state, strategy, callback, current, total_steps
            )
            
            self.research_logger.end_section(
                key,
                section.final_score,
                section.evaluation.get("grade", "F"),
                section.success,
                section.citations
            )
            
            state.sections[key] = section
            state.all_citations.extend(section.citations)
            current += 4
        
        # 최종 보고서 생성
        if callback:
            callback("report", "최종 보고서 생성 중...", (total_steps - 1) / total_steps)
        
        self.research_logger.log_stage_start("final_report")
        report_start = time.time()
        state.final_report = await self._generate_final_report(state)
        self.research_logger.log_stage_end(
            "final_report",
            {"report_length": len(state.final_report)},
            (time.time() - report_start) * 1000
        )
        
        if callback:
            callback("done", "완료", 1.0)
        
        # 로그 저장
        if self.research_logger:
            try:
                state.log_path = self.research_logger.finalize()
            except Exception as e:
                logger.error(f"로그 저장 실패: {e}")
                state.log_path = ""
        
        return self._to_output(state)
    
    async def _process_section_with_validation(
        self, 
        section: SectionResult, 
        state: PipelineState,
        strategy: Dict,
        callback: Optional[ProgressCallback],
        current: int,
        total: int
    ):
        """검증 강화 섹션 처리 - HS Code 필터링 포함"""
        
        key = section.key
        title = section.title
        
        # ============================================================
        # 특수 섹션 처리: summary (Executive Summary)
        # ============================================================
        if key == "summary":
            # summary는 다른 섹션 완료 후 생성해야 하므로 일단 스킵
            # _generate_final_report에서 처리
            section.draft = "[요약은 최종 단계에서 생성됩니다]"
            section.draft_score = 0
            section.final = ""
            section.final_score = 0
            section.success = True  # 일단 통과
            return
        
        # ============================================================
        # 단계 1: Draft 생성 + HS Code 관련성 검증
        # ============================================================
        if strategy.get("use_json", True):
            if callback:
                callback(key, f"✍️ {title}: 초안 생성 중...", current / total)
            
            draft_content, draft_citations = await self._generate_section_with_hs_filter(
                key, state, mode="draft"
            )
            
            # 관련성 검증
            relevance = validate_content_relevance(
                draft_content, state.hs_code, state.item
            )
            section.relevance = relevance
            
            if not relevance["relevant"]:
                logger.warning(
                    f"⚠️ {key} 관련성 낮음 (점수: {relevance['score']:.2f}), "
                    f"무관 토픽: {relevance['irrelevant_topics']}"
                )
            
            # Supervisor 검증
            draft_eval = self.supervisor.evaluate_content(
                content=draft_content,
                source_type="json",
                metadata={"section": key, "step": "draft", "relevance": relevance}
            )
            
            # 관련성이 낮으면 점수 감점
            if not relevance["relevant"]:
                draft_eval["score"] = max(0, draft_eval.get("score", 0) - 20)
            
            section.draft = draft_content
            section.draft_score = draft_eval.get("score", 0)
            section.citations.extend(draft_citations)
            
            logger.info(f"✅ {key} Draft: {section.draft_score}점 (관련성: {relevance['score']:.2f})")
        
        # ============================================================
        # 단계 2: KATI 검증
        # ============================================================
        if strategy.get("use_kati", False) and section.draft:
            if callback:
                callback(key, f"🔍 {title}: KATI 검증 중...", (current + 1) / total)
            
            kati_content, kati_citations = await self._generate_section_with_hs_filter(
                key, state, mode="verify", existing_content=section.draft
            )
            
            kati_eval = self.supervisor.evaluate_content(
                content=kati_content,
                source_type="kati",
                metadata={"section": key, "step": "kati"}
            )
            
            section.kati_verified = kati_content
            section.kati_score = kati_eval.get("score", 0)
            section.citations.extend(kati_citations)
            
            logger.info(f"✅ {key} KATI: {section.kati_score}점")
            
            if section.kati_score < section.draft_score - self.IMPROVEMENT_THRESHOLD:
                logger.warning(f"⚠️ {key} KATI 검증 후 품질 하락 → Draft 유지")
                section.kati_verified = section.draft
                section.kati_score = section.draft_score
        
        # ============================================================
        # 단계 3: PDF 보완
        # ============================================================
        if strategy.get("use_pdf", False):
            if callback:
                callback(key, f"📚 {title}: PDF 보완 중...", (current + 2) / total)
            
            base_content = section.kati_verified or section.draft
            pdf_content, pdf_citations = await self._generate_section_with_hs_filter(
                key, state, mode="enhance_pdf", existing_content=base_content
            )
            
            pdf_eval = self.supervisor.evaluate_content(
                content=pdf_content,
                source_type="pdf",
                metadata={"section": key, "step": "pdf"}
            )
            
            section.pdf_enhanced = pdf_content
            section.pdf_score = pdf_eval.get("score", 0)
            section.citations.extend(pdf_citations)
            
            logger.info(f"✅ {key} PDF: {section.pdf_score}점")
            
            prev_score = section.kati_score or section.draft_score
            if section.pdf_score < prev_score - self.IMPROVEMENT_THRESHOLD:
                logger.warning(f"⚠️ {key} PDF 보완 후 품질 하락 → 이전 버전 유지")
                section.pdf_enhanced = base_content
                section.pdf_score = prev_score
        
        # ============================================================
        # 단계 4: Web 보완
        # ============================================================
        if strategy.get("use_web", False):
            if callback:
                callback(key, f"🌐 {title}: 웹 보완 중...", (current + 3) / total)
            
            base_content = section.pdf_enhanced or section.kati_verified or section.draft
            web_content, web_citations = await self._generate_section_with_hs_filter(
                key, state, mode="enhance_web", existing_content=base_content
            )
            
            web_eval = self.supervisor.evaluate_content(
                content=web_content,
                source_type="web",
                metadata={"section": key, "step": "web"}
            )
            
            section.web_enhanced = web_content
            section.web_score = web_eval.get("score", 0)
            section.citations.extend(web_citations)
            
            logger.info(f"✅ {key} Web: {section.web_score}점")
            
            prev_score = section.pdf_score or section.kati_score or section.draft_score
            if section.web_score < prev_score - self.IMPROVEMENT_THRESHOLD:
                logger.warning(f"⚠️ {key} Web 보완 후 품질 하락 → 이전 버전 유지")
                section.web_enhanced = base_content
                section.web_score = prev_score
        
        # ============================================================
        # 최종: 가장 높은 점수 버전 선택
        # ============================================================
        self._select_best_version(section, key)
    
    def _select_best_version(self, section: SectionResult, key: str):
        """최고 점수 버전 선택"""
        versions = [
            ("draft", section.draft, section.draft_score),
            ("kati", section.kati_verified, section.kati_score),
            ("pdf", section.pdf_enhanced, section.pdf_score),
            ("web", section.web_enhanced, section.web_score),
        ]
        
        # 빈 콘텐츠 제외하고 점수 순 정렬
        valid_versions = [(v, c, s) for v, c, s in versions if c.strip()]
        if not valid_versions:
            section.final = f"{section.title}에 대한 데이터를 찾을 수 없습니다."
            section.final_score = 0
            section.final_version = "none"
            section.success = False
            return
        
        valid_versions.sort(key=lambda x: x[2], reverse=True)
        best_version, best_content, best_score = valid_versions[0]
        
        section.final = best_content
        section.final_score = best_score
        section.final_version = best_version
        section.success = best_score >= self.MIN_SCORE
        
        section.evaluation = {
            "score": best_score,
            "grade": self._score_to_grade(best_score),
            "version": best_version,
            "all_scores": {v[0]: v[2] for v in versions},
            "relevance": section.relevance
        }
        
        if section.success:
            logger.info(f"🏆 {key} 최종: {best_version.upper()} 버전 선택 ({best_score}점)")
        else:
            logger.error(f"❌ {key} 최종: 모든 버전 품질 미달 (최고 {best_score}점)")
    
    async def _generate_section_with_hs_filter(
        self,
        section_key: str,
        state: PipelineState,
        mode: str,
        existing_content: str = ""
    ) -> Tuple[str, List[str]]:
        """섹션 생성 - HS Code 필터링 포함"""
        
        # 웹 검색 모드
        if mode == "enhance_web":
            # HS 카테고리 키워드 포함 쿼리
            hs_keywords = " ".join(state.hs_category.get("keywords", [])[:3])
            query = f"{state.country} {state.item} {hs_keywords} {section_key} 최신 2024 2025"
            
            web_results = self.web.search_public_only(query, top_k=5)
            
            if not web_results:
                return existing_content, []
            
            context = "\n\n".join([
                f"🌐 [출처: {r.get('url', 'N/A')}]\n제목: {r.get('title', '')}\n{r.get('content', '')}"
                for r in web_results
            ])
            
            prompt = get_section_prompt(
                mode=mode,
                context=context,
                existing_content=existing_content,
                country=state.country,
                item=state.item,
                section_key=section_key,
                country_code=state.country_code,
                hs_code=state.hs_code
            )
            
            response = await self.llm_smart.ainvoke([HumanMessage(content=prompt)])
            citations = [f"웹: {r.get('url', 'N/A')}" for r in web_results]
            
            return response.content.strip(), citations
        
        # 필터 타입 결정
        if mode == "draft":
            filter_type = "country_info"
        elif mode == "verify":
            filter_type = "kati"
        elif mode == "enhance_pdf":
            filter_type = "kotra"
        else:
            filter_type = "country_info"
        
        # ============================================================
        # 개선된 쿼리: HS 카테고리 키워드 포함
        # ============================================================
        hs_keywords = state.hs_category.get("keywords", [])
        keyword_str = " ".join(hs_keywords[:3]) if hs_keywords else state.item
        
        query = f"{state.country} {state.item} {keyword_str} {section_key}"
        
        # 벡터 검색 (HS Code 메타데이터 필터 시도)
        filter_dict = {
            "type": filter_type,
            "country_code": state.country_code
        }
        
        docs = self.vectordb.retrieve(
            query=query,
            top_k=10,  # 더 많이 가져와서 필터링
            filter_dict=filter_dict
        )
        
        # ============================================================
        # 관련성 기반 문서 필터링 (신규)
        # ============================================================
        if docs:
            filtered_docs = []
            for doc in docs:
                content = doc.page_content
                relevance = validate_content_relevance(content, state.hs_code, state.item)
                
                if relevance["relevant"] or relevance["score"] >= 0.2:
                    filtered_docs.append(doc)
                else:
                    logger.debug(f"문서 제외 (관련성 {relevance['score']:.2f}): {content[:50]}...")
            
            # 필터링 후 문서가 없으면 원본 사용 (최소 2개)
            if len(filtered_docs) < 2:
                filtered_docs = docs[:5]
                logger.warning(f"관련 문서 부족, 원본 사용: {len(filtered_docs)}개")
            
            docs = filtered_docs[:5]
        
        if not docs:
            if existing_content:
                return existing_content, []
            return f"{state.country}의 {section_key} 정보를 찾을 수 없습니다.", []
        
        # 컨텍스트 구성
        context = "\n\n".join([
            f"📊 [출처: {d.metadata.get('source', filter_type)}]\n{d.page_content}"
            for d in docs
        ])
        
        # 프롬프트에 HS Code 정보 추가
        prompt = get_section_prompt(
            mode=mode,
            context=context,
            existing_content=existing_content,
            country=state.country,
            item=state.item,
            section_key=section_key,
            country_code=state.country_code,
            hs_code=state.hs_code
        )
        
        # HS Code 관련 지시 추가
        hs_instruction = f"""
⚠️ 중요: 이 보고서는 HS Code {state.hs_code} ({state.item})에 대한 것입니다.
관련 카테고리: {state.hs_category.get('category', '일반')}
관련 키워드: {', '.join(hs_keywords[:5])}

다른 품목(항공기부품, MCU, 철강 등)에 대한 내용은 포함하지 마십시오.
{state.item} 또는 {state.hs_category.get('category', '')} 관련 내용만 작성하십시오.
"""
        prompt = hs_instruction + "\n" + prompt
        
        # LLM 호출
        llm = self.llm_smart if mode in ["verify", "enhance_web"] else self.llm_fast
        response = await llm.ainvoke([HumanMessage(content=prompt)])
        
        # 출처 수집
        citations = [
            d.metadata.get("citation", d.metadata.get("source", filter_type))
            for d in docs
        ]
        
        return response.content.strip(), citations
    
    def _score_to_grade(self, score: int) -> str:
        """점수를 등급으로 변환"""
        if score >= 90:
            return "A"
        elif score >= 80:
            return "B"
        elif score >= 70:
            return "C"
        elif score >= 50:
            return "D"
        else:
            return "F"
    
    async def _generate_final_report(self, state: PipelineState) -> str:
        """최종 보고서 생성 - A등급(90점 이상)만 포함"""
        
        # A등급(90점 이상) 섹션만 승인
        approved_sections = {
            key: section
            for key, section in state.sections.items()
            if section.success and section.final_score >= 90 and key != "summary"
        }
        
        logger.info(f"📊 A등급 섹션: {len(approved_sections)}/{len(state.sections)}개")
        
        # 각 섹션의 등급 로깅
        for key, section in state.sections.items():
            score = section.final_score
            grade = section.evaluation.get("grade", "F")
            if section.success:
                if score >= 90:
                    logger.info(f"  ✅ {key}: {grade}등급 ({score}점) - 승인")
                else:
                    logger.warning(f"  ❌ {key}: {grade}등급 ({score}점) - A등급 미달로 제외")
        
        if not approved_sections:
            return "# ⚠️ A등급 기준을 충족하는 섹션이 없습니다.\n\n모든 섹션이 A등급(90점 이상) 기준에 미달했습니다."
        
        # ============================================================
        # Executive Summary 생성
        # ============================================================
        summary_content = await self._generate_executive_summary(state, approved_sections)
        
        # 보고서 조립
        parts = [
            f"# {state.country} {state.item} 시장진출 보고서",
            f"\n🔢 HS Code: {state.hs_code}",
            f"📅 생성일: {time.strftime('%Y-%m-%d')}",
            f"\n---\n"
        ]
        
        # 1. Executive Summary (첫 번째)
        parts.append("\n## 1. 요약 (Executive Summary)")
        parts.append(f"*품질: 자동생성*\n")
        parts.append(summary_content)
        
        # 2-8. 나머지 섹션 (A등급만)
        section_order = [
            ("overview", "2. 국가 및 시장 개요"),
            ("market_size", "3. 시장 규모"),
            ("distribution", "4. 유통 구조"),
            ("risk", "5. 시장 리스크"),
            ("regulation", "6. 규제 검토"),
            ("price", "7. 가격 추세"),
            ("sns_hashtag", "8. SNS 해시태그"),
        ]
        
        for key, title in section_order:
            if key in approved_sections:
                section = approved_sections[key]
                score = section.final_score
                grade = section.evaluation.get("grade", "F")
                version = section.final_version.upper()
                
                parts.append(f"\n## {title}")
                parts.append(f"*품질: {grade}등급 ({score}점) | 버전: {version}*\n")
                parts.append(section.final)
        
        # 9. 출처 (KOTRA p.X, KATI p.Y, 웹 URL 형식)
        if state.all_citations:
            parts.append("\n## 9. 출처\n")
            
            # 출처를 KOTRA, KATI, 웹으로 분류
            kotra_sources = []
            kati_sources = []
            web_sources = []
            other_sources = []
            
            unique_citations = list(set(state.all_citations))
            for c in unique_citations:
                c_lower = c.lower()
                if "kotra" in c_lower:
                    kotra_sources.append(c)
                elif "kati" in c_lower:
                    kati_sources.append(c)
                elif "http" in c_lower or "웹" in c:
                    web_sources.append(c)
                else:
                    other_sources.append(c)
            
            # KOTRA 출처
            if kotra_sources:
                parts.append("\n### KOTRA 자료")
                for src in sorted(kotra_sources):
                    parts.append(f"- {src}")
            
            # KATI 출처
            if kati_sources:
                parts.append("\n### KATI 자료")
                for src in sorted(kati_sources):
                    parts.append(f"- {src}")
            
            # 웹 출처
            if web_sources:
                parts.append("\n### 웹 자료")
                for src in sorted(web_sources):
                    parts.append(f"- {src}")
            
            # 기타 출처
            if other_sources:
                parts.append("\n### 기타")
                for src in sorted(other_sources):
                    parts.append(f"- {src}")
        
        # 품질 요약 (디버그용, 내부 모드에서만)
        parts.append("\n---\n## 📊 품질 요약\n")
        for key, title in section_order:
            if key in approved_sections:
                section = approved_sections[key]
                relevance_info = ""
                if section.relevance:
                    rel_score = section.relevance.get("score", 0)
                    relevance_info = f", 관련성: {rel_score:.0%}"
                
                parts.append(
                    f"- **{title.split('. ')[1]}**: {section.evaluation.get('grade', 'F')}등급 "
                    f"({section.final_score}점, {section.final_version.upper()}{relevance_info})"
                )
        
        return "\n".join(parts)
    
    async def _generate_executive_summary(
        self, 
        state: PipelineState, 
        approved_sections: Dict[str, SectionResult]
    ) -> str:
        """Executive Summary 자동 생성"""
        
        # 각 섹션에서 핵심 정보 추출
        section_summaries = []
        for key, section in approved_sections.items():
            content = section.final[:500]  # 앞부분만
            section_summaries.append(f"### {section.title}\n{content}")
        
        combined_content = "\n\n".join(section_summaries)
        
        prompt = f"""
당신은 KOTRA 보고서 요약 전문가입니다.

아래 섹션 내용을 바탕으로 Executive Summary를 작성하세요.

📌 대상 국가: {state.country}
📌 HS Code: {state.hs_code}
📌 품목: {state.item}
📌 카테고리: {state.hs_category.get('category', '일반')}

## 섹션 내용:
{combined_content}

## 요약 작성 규칙:
1. **보고서 목적** (1-2문장): 대상 국가, HS코드, 품목 명시
2. **시장 규모** (2-3문장): 구체적 금액, 성장률 (있는 경우)
3. **한국산 제품 위치** (2-3문장): 순위, 점유율 (있는 경우)
4. **관세 및 진입장벽** (2-3문장): 관세율 %, 주요 규제
5. **GO/Conditional GO/NO-GO 판단** (2-3문장): 판단 + 근거 3가지

⚠️ 규칙:
- 각 항목에 출처 표기: [출처: ...]
- 데이터가 없으면 "해당 데이터 없음" 명시
- 일반론, 추측 금지
- 최소 400자 이상
"""
        
        try:
            response = await self.llm_smart.ainvoke([HumanMessage(content=prompt)])
            return response.content.strip()
        except Exception as e:
            logger.error(f"Executive Summary 생성 실패: {e}")
            return f"""
본 보고서는 {state.country} 시장에서 {state.item}(HS {state.hs_code})의 진출 전략을 분석합니다.

상세 내용은 아래 각 섹션을 참조하십시오.

[자동 요약 생성 실패 - 수동 검토 필요]
"""
    
    def _to_output(self, state: PipelineState) -> Dict:
        """출력 형식 변환"""
        return {
            "success": True,
            "final_report": state.final_report,
            "hs_category": state.hs_category,
            "sections": [
                {
                    "key": s.key,
                    "title": s.title,
                    "content": s.final,
                    "passed": s.success,
                    "evaluation": s.evaluation,
                    "citations": s.citations,
                    "version": s.final_version,
                    "relevance": s.relevance,
                    "all_scores": {
                        "draft": s.draft_score,
                        "kati": s.kati_score,
                        "pdf": s.pdf_score,
                        "web": s.web_score
                    }
                }
                for s in state.sections.values()
            ],
            "all_citations": list(set(state.all_citations)),
            "log_path": state.log_path,
            "errors": state.errors,
            "quality_summary": {
                "total_sections": len(state.sections),
                "approved_sections": sum(1 for s in state.sections.values() if s.success),
                "average_score": sum(s.final_score for s in state.sections.values()) / len(state.sections) if state.sections else 0
            }
        }


# ============================================================
# 초기화 함수
# ============================================================

def init_vectorstore() -> QdrantVectorDB:
    """벡터스토어 초기화"""
    db = QdrantVectorDB()
    
    if not db.has_data():
        logger.warning("⚠️ 벡터스토어에 데이터가 없습니다. init_db.py를 먼저 실행하세요.")
    
    return db


# ============================================================
# 테스트
# ============================================================

if __name__ == "__main__":
    # HS Code 카테고리 테스트
    test_codes = ["2202010000", "8803", "0901", "1905"]
    
    for code in test_codes:
        info = get_hs_category(code)
        print(f"HS {code}: {info}")
    
    # 관련성 검증 테스트
    test_content = """
    미국의 탄산음료 시장은 2024년 기준 500억 달러 규모입니다.
    주요 브랜드로는 코카콜라, 펩시 등이 있습니다.
    """
    
    relevance = validate_content_relevance(test_content, "2202010000", "탄산음료")
    print(f"관련성 테스트: {relevance}")
    
    # 무관한 콘텐츠 테스트
    irrelevant_content = """
    항공기부품 시장은 2024년 기준 2,331억 달러 규모입니다.
    Boeing, Lockheed Martin 등이 주요 기업입니다.
    """
    
    relevance2 = validate_content_relevance(irrelevant_content, "2202010000", "탄산음료")
    print(f"무관 콘텐츠 테스트: {relevance2}")