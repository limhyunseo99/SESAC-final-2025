# pipeline.py
# 검증 강화 버전: Supervisor가 각 단계 승인
# 프롬프트 3개로 축소 + 이모지 활용

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

ANALYSIS_OPTIONS = {
    "regulation": "규제",
    "risk": "시장리스크",
    "price": "가격추세",
    "demand": "수요전망",
}

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
    final_version: str = ""  # "draft", "kati", "pdf", "web"
    
    citations: List[str] = field(default_factory=list)
    evaluation: Dict = field(default_factory=dict)
    success: bool = False


@dataclass
class PipelineState:
    """파이프라인 상태"""
    country: str
    country_code: str
    hs_code: str
    item: str
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


class ResearchPipeline:
    """연구 파이프라인 - 검증 강화 버전"""
    
    def __init__(self, vectordb: Optional[QdrantVectorDB] = None):
        self.vectordb = vectordb or QdrantVectorDB()
        self.web = WebSearcher()
        self.llm_fast = ChatOpenAI(model=Config.MODEL_FAST, temperature=0)
        self.llm_smart = ChatOpenAI(model=Config.MODEL_SMART, temperature=0)
        self.strategy_selector = StrategySelector()
        
        # 품질 기준
        self.MIN_SCORE = 70  # 최소 통과 점수
        self.IMPROVEMENT_THRESHOLD = 5  # 개선 최소 폭 (점)
        
        # 로거 초기화
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
        
        # 상태 초기화
        country_name = payload.get("country", "미국")
        state = PipelineState(
            country=country_name,
            country_code=DataLoader.normalize_country(country_name),
            hs_code=payload.get("hs_code", ""),
            item=payload.get("item", "제품"),
            options=payload.get("options", []),
        )
        
        self.research_logger.log_stage_end(
            PipelineStage.INPUT_PARSING,
            {"country_code": state.country_code},
            (time.time() - start_time) * 1000
        )
        
        # 기본 섹션 + 선택 옵션
        sections_to_process = [
            ("overview", "국가 및 시장 개요"),
            ("market_size", "시장 규모"),
            ("distribution", "유통 구조"),
        ]
        
        for opt_key, opt_name in ANALYSIS_OPTIONS.items():
            if opt_key in state.options:
                sections_to_process.append((opt_key, opt_name))
        
        total_steps = len(sections_to_process) * 4 + 1
        current = 0
        
        # 섹션별 처리 (검증 강화)
        for key, title in sections_to_process:
            section = SectionResult(key=key, title=title)
            
            # 로거에 섹션 시작 기록
            self.research_logger.start_section(key, title)
            
            # 전략 가져오기
            strategy = self.strategy_selector.get_strategy(key)
            logger.info(f"📋 섹션 {key}: {strategy['reason']}")
            
            # 🔥 검증 강화 파이프라인
            await self._process_section_with_validation(section, state, strategy, callback, current, total_steps)
            
            # 로거에 섹션 완료 기록
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
        
        # 최종 보고서 생성 (Supervisor 승인된 섹션만)
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
        """🔥 검증 강화 섹션 처리 - 각 단계마다 Supervisor 검증"""
        
        key = section.key
        title = section.title
        
        # ============================================================
        # 단계 1: Draft 생성 + Supervisor 검증 ⭐
        # ============================================================
        if strategy.get("use_json", True):
            if callback:
                callback(key, f"✍️ {title}: 초안 생성 중...", current / total)
            
            draft_content, draft_citations = await self._generate_section(
                key, state, mode="draft"
            )
            
            # Supervisor 검증
            draft_eval = self.supervisor.evaluate_content(
                content=draft_content,
                source_type="json",
                metadata={"section": key, "step": "draft"}
            )
            
            section.draft = draft_content
            section.draft_score = draft_eval.get("score", 0)
            section.citations.extend(draft_citations)
            
            logger.info(f"✅ {key} Draft: {section.draft_score}점 ({draft_eval.get('grade', 'F')})")
            
            # 최소 기준 미달 시 경고
            if section.draft_score < self.MIN_SCORE:
                logger.warning(f"⚠️ {key} Draft 품질 미달 ({section.draft_score}점) - 계속 진행")
        
        # ============================================================
        # 단계 2: KATI 검증 + Supervisor 검증 ⭐
        # ============================================================
        if strategy.get("use_kati", False) and section.draft:
            if callback:
                callback(key, f"🔍 {title}: KATI 검증 중...", (current + 1) / total)
            
            kati_content, kati_citations = await self._generate_section(
                key, state, mode="verify", existing_content=section.draft
            )
            
            # Supervisor 검증
            kati_eval = self.supervisor.evaluate_content(
                content=kati_content,
                source_type="kati",
                metadata={"section": key, "step": "kati"}
            )
            
            section.kati_verified = kati_content
            section.kati_score = kati_eval.get("score", 0)
            section.citations.extend(kati_citations)
            
            logger.info(f"✅ {key} KATI: {section.kati_score}점 ({kati_eval.get('grade', 'F')})")
            
            # 개선되지 않으면 draft로 롤백
            if section.kati_score < section.draft_score - self.IMPROVEMENT_THRESHOLD:
                logger.warning(f"⚠️ {key} KATI 검증 후 품질 하락 → Draft 유지")
                section.kati_verified = section.draft
                section.kati_score = section.draft_score
        
        # ============================================================
        # 단계 3: PDF 보완 + Supervisor 검증 ⭐
        # ============================================================
        if strategy.get("use_pdf", False):
            if callback:
                callback(key, f"📚 {title}: PDF 보완 중...", (current + 2) / total)
            
            base_content = section.kati_verified or section.draft
            pdf_content, pdf_citations = await self._generate_section(
                key, state, mode="enhance_pdf", existing_content=base_content
            )
            
            # Supervisor 검증
            pdf_eval = self.supervisor.evaluate_content(
                content=pdf_content,
                source_type="pdf",
                metadata={"section": key, "step": "pdf"}
            )
            
            section.pdf_enhanced = pdf_content
            section.pdf_score = pdf_eval.get("score", 0)
            section.citations.extend(pdf_citations)
            
            logger.info(f"✅ {key} PDF: {section.pdf_score}점 ({pdf_eval.get('grade', 'F')})")
            
            # 개선되지 않으면 이전 버전 유지
            prev_score = section.kati_score or section.draft_score
            if section.pdf_score < prev_score - self.IMPROVEMENT_THRESHOLD:
                logger.warning(f"⚠️ {key} PDF 보완 후 품질 하락 → 이전 버전 유지")
                section.pdf_enhanced = base_content
                section.pdf_score = prev_score
        
        # ============================================================
        # 단계 4: Web 보완 + Supervisor 최종 검증 ⭐
        # ============================================================
        if strategy.get("use_web", False):
            if callback:
                callback(key, f"🌐 {title}: 웹 보완 중...", (current + 3) / total)
            
            base_content = section.pdf_enhanced or section.kati_verified or section.draft
            web_content, web_citations = await self._generate_section(
                key, state, mode="enhance_web", existing_content=base_content
            )
            
            # Supervisor 최종 검증
            web_eval = self.supervisor.evaluate_content(
                content=web_content,
                source_type="web",
                metadata={"section": key, "step": "web"}
            )
            
            section.web_enhanced = web_content
            section.web_score = web_eval.get("score", 0)
            section.citations.extend(web_citations)
            
            logger.info(f"✅ {key} Web: {section.web_score}점 ({web_eval.get('grade', 'F')})")
            
            # 개선되지 않으면 이전 버전 유지
            prev_score = section.pdf_score or section.kati_score or section.draft_score
            if section.web_score < prev_score - self.IMPROVEMENT_THRESHOLD:
                logger.warning(f"⚠️ {key} Web 보완 후 품질 하락 → 이전 버전 유지")
                section.web_enhanced = base_content
                section.web_score = prev_score
        
        # ============================================================
        # 최종: 가장 높은 점수 버전 선택 🏆
        # ============================================================
        versions = [
            ("draft", section.draft, section.draft_score),
            ("kati", section.kati_verified, section.kati_score),
            ("pdf", section.pdf_enhanced, section.pdf_score),
            ("web", section.web_enhanced, section.web_score),
        ]
        
        # 점수 순 정렬
        versions.sort(key=lambda x: x[2], reverse=True)
        best_version, best_content, best_score = versions[0]
        
        section.final = best_content
        section.final_score = best_score
        section.final_version = best_version
        section.success = best_score >= self.MIN_SCORE
        
        section.evaluation = {
            "score": best_score,
            "grade": self._score_to_grade(best_score),
            "version": best_version,
            "all_scores": {v[0]: v[2] for v in versions}
        }
        
        if section.success:
            logger.info(f"🏆 {key} 최종: {best_version.upper()} 버전 선택 ({best_score}점)")
        else:
            logger.error(f"❌ {key} 최종: 모든 버전 품질 미달 (최고 {best_score}점)")
    
    async def _generate_section(
        self,
        section_key: str,
        state: PipelineState,
        mode: str,
        existing_content: str = ""
    ) -> Tuple[str, List[str]]:
        """섹션 생성 (통합 프롬프트 사용)"""
        
        # 데이터 검색
        if mode == "draft":
            filter_type = "country_info"
        elif mode == "verify":
            filter_type = "kati"
        elif mode == "enhance_pdf":
            filter_type = "kotra"
        elif mode == "enhance_web":
            # 웹 검색
            query = f"{state.country} {state.item} {section_key} 최신"
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
        else:
            filter_type = "country_info"
        
        # 벡터 검색
        docs = self.vectordb.retrieve(
            query=f"{state.country} {state.item} {section_key}",
            top_k=5,
            filter_dict={"type": filter_type, "country_code": state.country_code}
        )
        
        if not docs:
            if existing_content:
                return existing_content, []
            return f"{state.country}의 {section_key} 정보를 찾을 수 없습니다.", []
        
        # 컨텍스트 구성
        context = "\n\n".join([
            f"📊 [출처: {d.metadata.get('source', filter_type)}]\n{d.page_content}"
            for d in docs
        ])
        
        # 프롬프트 생성
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
        """최종 보고서 생성 (Supervisor 승인된 섹션만)"""
        
        # 승인된 섹션만 수집
        approved_sections = {
            key: section
            for key, section in state.sections.items()
            if section.success
        }
        
        logger.info(f"📊 승인된 섹션: {len(approved_sections)}/{len(state.sections)}개")
        
        if not approved_sections:
            return "# ⚠️ 품질 기준을 충족하는 섹션이 없습니다.\n\n모든 섹션이 Supervisor 검증에서 실패했습니다."
        
        # 섹션 내용 조합
        parts = [
            f"# {state.country} {state.item} 시장진출 보고서",
            f"\n🔢 HS Code: {state.hs_code}",
            f"📅 생성일: {time.strftime('%Y-%m-%d')}",
            f"\n---\n"
        ]
        
        section_titles = {
            "overview": "국가 및 시장 개요",
            "market_size": "시장 규모",
            "distribution": "유통 구조",
            "regulation": "규제",
            "risk": "시장리스크",
            "price": "가격추세",
            "demand": "수요전망"
        }
        
        for key in ["overview", "market_size", "distribution", "regulation", "risk", "price", "demand"]:
            if key in approved_sections:
                section = approved_sections[key]
                title = section_titles.get(key, key)
                score = section.final_score
                grade = section.evaluation.get("grade", "F")
                version = section.final_version.upper()
                
                parts.append(f"\n## {title}")
                parts.append(f"*품질: {grade}등급 ({score}점) | 버전: {version}*\n")
                parts.append(section.final)
        
        # 참고문헌
        if state.all_citations:
            parts.append("\n## 📚 참고문헌\n")
            unique_citations = list(set(state.all_citations))
            for c in unique_citations[:30]:  # 최대 30개
                parts.append(f"- {c}")
        
        # 품질 요약
        parts.append("\n---\n## 📊 품질 요약\n")
        for key, section in approved_sections.items():
            parts.append(
                f"- **{section.title}**: {section.evaluation.get('grade', 'F')}등급 "
                f"({section.final_score}점, {section.final_version.upper()})"
            )
        
        return "\n".join(parts)
    
    def _to_output(self, state: PipelineState) -> Dict:
        """출력 형식 변환"""
        return {
            "success": True,
            "final_report": state.final_report,
            "sections": [
                {
                    "key": s.key,
                    "title": s.title,
                    "content": s.final,
                    "passed": s.success,
                    "evaluation": s.evaluation,
                    "citations": s.citations,
                    "version": s.final_version,
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


def init_vectorstore() -> QdrantVectorDB:
    """벡터스토어 초기화"""
    db = QdrantVectorDB()
    
    if not db.has_data():
        logger.warning("⚠️ 벡터스토어에 데이터가 없습니다. init_db.py를 먼저 실행하세요.")
    
    return db