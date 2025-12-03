import os
import json
import re
import logging
from typing import Dict, List, Optional
from tavily import TavilyClient
from tenacity import retry, stop_after_attempt, wait_exponential
from langchain_openai import ChatOpenAI
from core import Config, VectorDB, DataLoader, Supervisor

logger = logging.getLogger(__name__)


# ------------------------------------------------------------
# 안전한 LLM 호출 (Critical Fix #1)
# ------------------------------------------------------------
@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=10),
    reraise=True
)
def invoke_llm_with_retry(llm, prompt: str):
    try:
        resp = llm.invoke(prompt)
        return resp.content
    except Exception as e:
        logger.error(f"LLM 호출 실패 (재시도 중): {e}")
        raise


# ------------------------------------------------------------
# 표/이미지 인덱스 로더
# ------------------------------------------------------------
def _load_table_index() -> Dict:
    base_dir = os.path.dirname(os.path.abspath(__file__))
    candidates = [
        os.path.join(base_dir, "table_image_index.json"),
        os.path.join(base_dir, "metadata", "table_image_index.json"),
        os.path.join(os.getcwd(), "table_image_index.json"),
    ]
    for path in candidates:
        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                continue
    return {}

TABLE_INDEX = _load_table_index()


# ------------------------------------------------------------
# Query Generator
# ------------------------------------------------------------
class QueryGenerator:
    def __init__(self):
        self.llm = ChatOpenAI(model=Config.MODEL_DRAFT, temperature=0)

    def generate(self, country: str, hs_code: str, extra: List[str]) -> str:
        base = f"{country} 시장 HS {hs_code} 시장규모·수출현황·트렌드·전망·PEST·SWOT·전략"

        extra_labels = {
            "시장 리스크": "시장 리스크",
            "가격 추세": "가격 추세",
            "규제 검토": "규제 검토",
        }

        parts = [extra_labels[e] for e in extra if e in extra_labels]
        query = base if not parts else f"{base} / {' / '.join(parts)}"

        logger.info(f"생성된 검색 쿼리: {query}")
        return query


# ------------------------------------------------------------
# RAG Search
# ------------------------------------------------------------
class RAGSearch:
    def __init__(self, vectordb: VectorDB):
        self.vectordb = vectordb
        self.query_gen = QueryGenerator()

    def search(self, country: str, hs_code: str, extra: List[str]) -> Dict:
        # Critical Fix #3: 국가코드 오류 대비
        try:
            country_code = DataLoader.normalize_country(country)
        except ValueError as e:
            logger.error(f"국가코드 변환 실패: {e}")
            return {
                "country_code": "UNKNOWN",
                "query": "",
                "documents": [],
                "country_info": {},
                "error": str(e)
            }

        query = self.query_gen.generate(country, hs_code, extra)

        docs = self.vectordb.search(query, country_code, k=5)

        # Critical Fix #3: 검색 결과 없음 대비
        if not docs:
            logger.warning("RAG 검색 결과 없음. 빈 리스트 반환")
            return {
                "country_code": country_code,
                "query": query,
                "documents": [],
                "country_info": DataLoader.load_country_info(country_code)
            }

        return {
            "country_code": country_code,
            "query": query,
            "documents": [
                {
                    "content": d.page_content,
                    "source": d.metadata.get("source"),
                    "year": d.metadata.get("year"),
                    "file_name": d.metadata.get("file_name"),
                }
                for d in docs
            ],
            "country_info": DataLoader.load_country_info(country_code),
        }


# ------------------------------------------------------------
# Deep Research
# ------------------------------------------------------------
class DeepResearch:
    def __init__(self):
        api_key = os.getenv("TAVILY_API_KEY")
        if not api_key:
            logger.error("TAVILY_API_KEY 누락")
            raise EnvironmentError("TAVILY_API_KEY가 필요합니다.")

        self.tavily = TavilyClient(api_key=api_key)
        self.supervisor = Supervisor()
        self.llm = ChatOpenAI(model=Config.MODEL_DRAFT, temperature=0.3)

    # Critical Fix #1 – Tavily 검색 안정화
    def _search(self, query: str) -> List[Dict]:
        if not query or not query.strip():
            logger.warning("검색 쿼리가 비어있음")
            return []

        try:
            r = self.tavily.search(query=query, search_depth="advanced", max_results=5)
            return r.get("results", [])
        except Exception as e:
            logger.error(f"Tavily 검색 실패: {e}")
            return []

    def _build_table_hints(self, country_code: str) -> Dict:
        hints = {}
        code = country_code.upper()
        for src in ["KOTRA", "KATI"]:
            if src not in TABLE_INDEX:
                continue
            if code not in TABLE_INDEX[src]:
                continue
            years = sorted(TABLE_INDEX[src][code].keys(), reverse=True)
            if not years:
                continue
            latest_year = years[0]
            info = TABLE_INDEX[src][code][latest_year]
            hints[src] = {
                "latest_year": latest_year,
                "table_pages": info.get("table_pages") or [],
                "image_pages": info.get("image_pages") or [],
            }
        return hints

    # ------------------------------------------------------------
    # Critical Fix #2: JSON 파싱 안전성 강화
    # ------------------------------------------------------------
    def _extract_json(self, text: str) -> Dict:
        try:
            match = re.search(r"\{.*?\}", text, re.DOTALL)
            if match:
                return json.loads(match.group(0))
            logger.warning("LLM JSON 미검출. fallback 처리")
            return {"info": text[:200], "confidence": "low", "key_numbers": [], "main_sources": []}
        except json.JSONDecodeError as e:
            logger.error(f"JSON 파싱 오류: {e}")
            return {"info": text[:200], "confidence": "low", "key_numbers": [], "main_sources": []}

    # ------------------------------------------------------------
    # Core analysis
    # ------------------------------------------------------------
    def _analyze(self, results: List[Dict], analysis_type: str,
                 country_code: str, source_type: str) -> Dict:

        if not results:
            return {
                "info": f"No data for {analysis_type}",
                "confidence": "no_data",
                "urls": [],
                "trust": self.supervisor.compute_trust_breakdown(
                    analysis_type,
                    country_code,
                    {"source_score": 0.0},
                    ""
                )
            }

        urls = [r.get("url", "") for r in results]
        validation = self.supervisor.validate_source(urls, country_code, source_type)

        valid_results = [r for r in results if r.get("url") in validation["valid_urls"]]

        formatted = "\n".join(
            f"[{i+1}] {r.get('title','N/A')}\n{(r.get('content') or '')[:200]}...\nURL: {r.get('url','')}"
            for i, r in enumerate(valid_results[:3])
        )

        prompt = f"""
You are an export market analyst.

CONTEXT:
{formatted if formatted.strip() else "No valid context."}

Return ONLY JSON:
{{
  "info": "summary",
  "confidence": "high|medium|low",
  "key_numbers": [],
  "main_sources": []
}}
"""

        # Critical Fix #1 — LLM 재시도
        llm_text = invoke_llm_with_retry(self.llm, prompt)

        # Critical Fix #2 — JSON 파싱 보강
        data = self._extract_json(llm_text)

        trust = self.supervisor.compute_trust_breakdown(
            analysis_type,
            country_code,
            validation,
            data.get("info", "")
        )

        data["trust"] = trust
        data["urls"] = validation["valid_urls"][:3]

        return data

    # ------------------------------------------------------------
    def search_regulation(self, country: str, product: str, hs_code: str, country_code: str) -> Dict:
        query = f"{country} {product} import regulation {hs_code}"
        return self._analyze(self._search(query), "수입 규제 및 인증 요건", country_code, "regulation")

    def search_price(self, country: str, product: str, country_code: str) -> Dict:
        query = f"{country} {product} price trend 2024"
        return self._analyze(self._search(query), "가격 추세", country_code, "price_risk")

    def search_risk(self, country: str, product: str, country_code: str) -> Dict:
        query = f"{country} market risk 2024"
        return self._analyze(self._search(query), "시장 리스크", country_code, "price_risk")

    # ------------------------------------------------------------
    def run_all(self, country: str, product: str, hs_code: str, extra: List[str], country_code: str) -> Dict:
        result = {}

        result["regulation"] = self.search_regulation(country, product, hs_code, country_code)
        if "가격 추세" in extra:
            result["price"] = self.search_price(country, product, country_code)
        if "시장 리스크" in extra:
            result["risk"] = self.search_risk(country, product, country_code)

        result["table_hints"] = self._build_table_hints(country_code)

        summary = []
        for key in ["regulation", "price", "risk"]:
            if key in result:
                trust = result[key]["trust"]
                summary.append({
                    "type": key,
                    "trust_score": trust["overall_score"],
                    "trust_level": trust["overall_grade"],
                    "valid_source_count": len(result[key]["urls"]),
                })

        result["summary_trust"] = summary

        return result
