# pipeline.py
# 연구 파이프라인 통합 (Scoping + Research + Reflection)

import os
import asyncio
import logging
from typing import Dict, List, Optional, Callable, Any
from dataclasses import dataclass, field
from datetime import datetime

from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage
from tavily import TavilyClient

from config import Config, DataLoader, Supervisor
from vectorstore import QdrantVectorDB
from logger import ResearchLogger, PipelineStage

logger = logging.getLogger(__name__)

# 타입 정의
ProgressCallback = Callable[[str, str, float], None]


# =============================================================================
# 상태 정의
# =============================================================================
@dataclass
class SectionResult:
    """섹션 연구 결과"""
    key: str
    title: str
    summary: str = ""
    rag_docs: List[Dict] = field(default_factory=list)
    web_info: Optional[Dict] = None
    success: bool = False


@dataclass
class PipelineState:
    """파이프라인 전체 상태"""
    country: str
    hs_code: str
    item: str
    country_code: str = ""
    brief: str = ""
    sections: Dict[str, SectionResult] = field(default_factory=dict)
    final_report: str = ""
    errors: List[str] = field(default_factory=list)


# =============================================================================
# 섹션 정의
# =============================================================================
SECTIONS = [
    ("overview", "국가 및 시장 개요"),
    ("suitability", "품목 적합성 평가"),
    ("market_size", "시장 규모 및 성장 전망"),
    ("distribution", "유통 구조"),
    ("regulation", "규제 요건"),
    ("price", "가격 추세"),
    ("risk", "리스크 분석"),
    ("demand", "수요 전망"),
]

WEB_SECTIONS = ["regulation", "price", "risk", "demand"]  # 웹 검색이 필요한 섹션


# =============================================================================
# 웹 검색 (Tavily)
# =============================================================================
class WebSearcher:
    """Tavily 기반 웹 검색"""
    
    def __init__(self):
        self.client = TavilyClient(api_key=Config.TAVILY_API_KEY) if Config.TAVILY_API_KEY else None
        self.supervisor = Supervisor()
    
    def search(self, query: str, top_k: int = 5) -> List[Dict]:
        """웹 검색 실행"""
        if not self.client:
            return []
        try:
            result = self.client.search(query=query, max_results=top_k)
            return result.get("results", []) if result else []
        except Exception as e:
            logger.error(f"웹 검색 실패: {e}")
            return []
    
    def analyze(self, section_key: str, country: str, product: str, hs_code: str) -> Dict:
        """섹션별 웹 분석"""
        queries = {
            "regulation": f"{country} {product} import regulation certification HS {hs_code}",
            "price": f"{country} {product} import price trend wholesale HS {hs_code}",
            "risk": f"{country} {product} market risk political economic HS {hs_code}",
            "demand": f"{country} {product} demand forecast growth HS {hs_code}",
        }
        
        query = queries.get(section_key, f"{country} {product} {section_key}")
        results = self.search(query)
        
        text = "\n".join([r.get("content", "") for r in results])
        urls = [r.get("url", "") for r in results]
        trust = self.supervisor.score_web_result(text, urls)
        
        return {
            "text": text,
            "urls": urls,
            "trust": trust,
            "use": trust.get("grade") == "High"
        }


# =============================================================================
# 연구 파이프라인
# =============================================================================
class ResearchPipeline:
    """통합 연구 파이프라인"""
    
    def __init__(self, vectordb: Optional[QdrantVectorDB] = None):
        self.vectordb = vectordb or QdrantVectorDB()
        self.web = WebSearcher()
        self.llm_fast = ChatOpenAI(model=Config.MODEL_FAST, temperature=0)
        self.llm_smart = ChatOpenAI(model=Config.MODEL_SMART, temperature=0)
        
        # 로거 초기화
        self.research_logger: Optional[ResearchLogger] = None
        self.supervisor: Optional[Supervisor] = None
    # -------------------------------------------------------------------------
    # 메인 실행
    # -------------------------------------------------------------------------
    def run(self, payload: Dict, callback: Optional[ProgressCallback] = None) -> Dict:
        """동기 실행"""
        return asyncio.run(self.run_async(payload, callback))
    
    async def run_async(self, payload: Dict, callback: Optional[ProgressCallback] = None) -> Dict:
        """비동기 실행"""
        
        # 로거 초기화
        self.research_logger = ResearchLogger()
        self.supervisor = Supervisor(self.research_logger)
        self.research_logger.log_user_input(payload)
    
        # 상태 초기화
        country_name = payload.get("country", "미국")
        state = PipelineState(
            country=payload.get("country", ""),
            hs_code=payload.get("hs_code", ""),
            item=payload.get("item", "제품"),
        )
        
        try:
            state.country_code = DataLoader.normalize_country(state.country)
        except:
            state.country_code = "US"
        
        total_steps = len(SECTIONS) + 2  # 섹션 + 브리프 + 최종보고서
        current = 0
        
        # 2. 브리프 생성
        if callback:
            callback("brief", "🎯 연구 브리프 생성 중...", current / total_steps)
        
        state.brief = await self._generate_brief(state)
        current += 1
        
        if callback:
            callback("brief", "🎯 연구 브리프 완료", current / total_steps)
        
        # 3. 섹션별 연구 (병렬)
        tasks = []
        for key, title in SECTIONS:
            tasks.append(self._research_section(key, title, state))
        
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        for i, result in enumerate(results):
            key, title = SECTIONS[i]
            current += 1
            
            if isinstance(result, SectionResult):
                state.sections[key] = result
                status = "✅" if result.success else "⚠️"
            else:
                state.sections[key] = SectionResult(key=key, title=title, summary="분석 실패")
                state.errors.append(str(result))
                status = "❌"
            
            if callback:
                callback(key, f"{status} {title}", current / total_steps)
        
        # 4. 최종 보고서
        if callback:
            callback("report", "📄 최종 보고서 생성 중...", current / total_steps)
        
        state.final_report = await self._generate_report(state)
        
        if callback:
            callback("report", "📄 보고서 완료", 1.0)
        
        return self._to_dict(state)
    
    # -------------------------------------------------------------------------
    # 브리프 생성
    # -------------------------------------------------------------------------
    async def _generate_brief(self, state: PipelineState) -> str:
        """연구 브리프 생성"""
        prompt = f"""
당신은 KOTRA 시장분석 전문가입니다.

[분석 대상]
- 국가: {state.country}
- HS Code: {state.hs_code}
- 품목: {state.item}

위 정보를 바탕으로 시장조사 브리프를 200자 내외로 작성하세요.
포함: 조사 목적, 핵심 분석 항목, 기대 결과물
"""
        response = await self.llm_fast.ainvoke([HumanMessage(content=prompt)])
        return response.content.strip()
    
    # -------------------------------------------------------------------------
    # 섹션 연구
    # -------------------------------------------------------------------------
    async def _research_section(self, key: str, title: str, state: PipelineState) -> SectionResult:
        """단일 섹션 연구"""
        result = SectionResult(key=key, title=title)
        
        try:
            # RAG 검색
            query = self._build_query(key, state)
            docs = self.vectordb.search(query, state.country_code, k=5)
            result.rag_docs = [{"content": d.page_content, "meta": d.metadata} for d in docs]
            
            # 웹 검색 (해당 섹션만)
            if key in WEB_SECTIONS:
                result.web_info = self.web.analyze(key, state.country, state.item, state.hs_code)
            
            # 요약 생성
            result.summary = await self._summarize_section(result, state)
            result.success = bool(result.summary and len(result.summary) > 50)
            
        except Exception as e:
            logger.error(f"섹션 {key} 오류: {e}")
            result.summary = "분석 중 오류 발생"
        
        return result
    
    def _build_query(self, key: str, state: PipelineState) -> str:
        """섹션별 RAG 쿼리 생성"""
        base = f"{state.country} {state.item} HS {state.hs_code}"
        
        suffixes = {
            "overview": "시장 개요 동향 경제 소비",
            "suitability": "적합성 경쟁력 수입 수출",
            "market_size": "시장 규모 성장률 통계",
            "distribution": "유통 채널 공급망 소매",
            "regulation": "규제 인증 라벨링 위생",
            "price": "가격 추세 단가 경쟁력",
            "risk": "리스크 위험 변동 경쟁",
            "demand": "수요 전망 소비 성장",
        }
        
        return f"{base} {suffixes.get(key, '')}"
    
    async def _summarize_section(self, section: SectionResult, state: PipelineState) -> str:
        """섹션 요약 생성"""
        rag_text = "\n".join([d["content"][:500] for d in section.rag_docs[:2]]) if section.rag_docs else ""
        web_text = section.web_info.get("text", "")[:500] if section.web_info else ""
        
        if not rag_text and not web_text:
            return "자료 부족"
        
        prompt = f"""
[{section.title}] 섹션 요약

국가: {state.country} | 품목: {state.item} | HS: {state.hs_code}

[RAG 자료]
{rag_text or "없음"}

[웹 검색]
{web_text or "없음"}

위 자료를 바탕으로 400-600자의 KOTRA 스타일 분석문을 작성하세요.
사실 기반으로만 작성하고, 불확실한 내용은 제외하세요.
"""
        response = await self.llm_fast.ainvoke([HumanMessage(content=prompt)])
        return response.content.strip()
    
    # -------------------------------------------------------------------------
    # 최종 보고서
    # -------------------------------------------------------------------------
    async def _generate_report(self, state: PipelineState) -> str:
        """최종 보고서 생성"""
        sections_md = "\n\n".join([
            f"## {s.title}\n{s.summary}"
            for s in state.sections.values() if s.success
        ])
        
        prompt = f"""
KOTRA 스타일의 시장진출 보고서를 작성하세요.

[연구 브리프]
{state.brief}

[섹션별 분석]
{sections_md}

[작성 지침]
1. 요약(Executive Summary): 400자
2. 각 섹션 내용 통합
3. 전략 제언: 500자

마크다운 형식으로 작성하세요.
"""
        response = await self.llm_smart.ainvoke([HumanMessage(content=prompt)])
        return response.content.strip()
    
    # -------------------------------------------------------------------------
    # 결과 변환
    # -------------------------------------------------------------------------
    def _to_dict(self, state: PipelineState) -> Dict:
        """상태를 딕셔너리로 변환"""
        return {
            "brief": state.brief,
            "sections": [
                {
                    "key": s.key,
                    "title": s.title,
                    "summary": s.summary,
                    "success": s.success,
                }
                for s in state.sections.values()
            ],
            "final_report": state.final_report,
            "errors": state.errors,
        }


# =============================================================================
# 벡터스토어 초기화
# =============================================================================
def init_vectorstore() -> QdrantVectorDB:
    """벡터스토어 초기화 (데이터 없으면 구축)"""
    db = QdrantVectorDB()
    
    if db.has_data():
        logger.info("VectorDB 준비 완료")
        return db
    
    logger.warning("VectorDB 구축 시작...")
    
    # 국가 JSON
    for code in Config.COUNTRY_MAP.values():
        docs = DataLoader.process_country_json(code)
        if docs:
            db.insert(docs)
    
    # PDF
    for folder in ["kati", "kotra"]:
        path = os.path.join(Config.DATA_DIR, folder)
        if os.path.exists(path):
            docs = DataLoader.process_all_pdfs(path)
            if docs:
                db.insert(docs)
    
    return db


# =============================================================================
# CLI 실행
# =============================================================================
if __name__ == "__main__":
    import sys
    import json
    
    logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
    
    # 페이로드
    if len(sys.argv) > 1:
        with open(sys.argv[1], "r", encoding="utf-8") as f:
            payload = json.load(f)
    else:
        payload = {"country": "일본", "hs_code": "3304.99", "item": "화장품"}
    
    print(f"\n{'='*50}")
    print(f"GlobalPath AI - Research Pipeline")
    print(f"{'='*50}")
    print(f"국가: {payload['country']}")
    print(f"HS Code: {payload['hs_code']}")
    print(f"품목: {payload['item']}")
    print(f"{'='*50}\n")
    
    # 콜백
    def cli_callback(step: str, msg: str, progress: float):
        bar = "█" * int(30 * progress) + "░" * int(30 * (1 - progress))
        print(f"\r[{bar}] {progress*100:5.1f}% | {msg}", end="", flush=True)
        if progress >= 1.0:
            print()
    
    # 실행
    db = init_vectorstore()
    pipeline = ResearchPipeline(db)
    result = pipeline.run(payload, cli_callback)
    
    print(f"\n{'='*50}")
    print("완료!")
    print(f"섹션: {len(result['sections'])}개")
    print(f"오류: {len(result['errors'])}개")