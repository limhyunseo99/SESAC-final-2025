# research.py 
import os
import re
import json
import logging
from datetime import datetime
from typing import Dict, List, Optional, Any
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

from langchain_openai import ChatOpenAI
from core import Config, Supervisor, VectorDB, DataLoader

logger = logging.getLogger(__name__)


class DeepResearch:
    """
    웹 검색 + 출처 검증 + 신뢰도 점수화의 전체 흐름을 담당.
    High(신뢰도 높음)만 최종 보고서에 반영하도록 use_in_report 필드 부여.
    """

    def __init__(self):
        api_key = os.getenv("TAVILY_API_KEY")
        if not api_key:
            logger.error("환경변수 TAVILY_API_KEY 가 없습니다.")
            raise EnvironmentError("TAVILY_API_KEY가 필요합니다.")

        from tavily import TavilyClient
        self.client = TavilyClient(api_key=api_key)

        self.supervisor = Supervisor()

        # LLM 초기화
        self.llm = ChatOpenAI(
            model=Config.MODEL_DRAFT,
            temperature=0
        )

        logger.info("DeepResearch 초기화 완료")

    # -------------------------------------------------------
    # LLM 안전 호출
    # -------------------------------------------------------
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=6),
        retry=retry_if_exception_type(Exception),
        reraise=True
    )
    def _invoke_llm(self, prompt: str) -> str:
        """안정적 LLM 호출"""
        try:
            response = self.llm.invoke(prompt)
            return response.content
        except Exception as e:
            logger.error(f"LLM 호출 실패: {e}")
            raise

    # -------------------------------------------------------
    # Tavily 검색
    # -------------------------------------------------------
    def _search_web(self, query: str) -> List[Dict]:
        """웹 검색 수행 (에러 핸들링 강화)"""
        if not query or not query.strip():
            logger.warning("빈 검색 쿼리")
            return []
        
        try:
            result = self.client.search(
                query=query,
                search_depth="advanced",
                max_results=7,
            )
            results = result.get("results", [])
            
            if not results:
                logger.warning(f"검색 결과 없음: {query}")
            
            return results
            
        except ConnectionError as e:
            logger.error(f"네트워크 오류: {e}")
            return []
        except TimeoutError as e:
            logger.error(f"타임아웃: {e}")
            return []
        except Exception as e:
            logger.error(f"Tavily 검색 실패: {e}")
            return []

    # -------------------------------------------------------
    # JSON 파싱 보조 함수
    # -------------------------------------------------------
    def _safe_extract_json(self, text: str) -> Dict:
        """중첩 JSON도 처리 가능한 안전한 파싱"""
        if not text:
            return {}
        
        try:
            # 1. 직접 JSON 파싱 시도
            return json.loads(text)
        except json.JSONDecodeError:
            pass
        
        try:
            # 2. JSON 블록 탐색 (깊이 추적)
            start = text.find('{')
            if start == -1:
                logger.warning("JSON 블록 시작 없음")
                return {}
            
            depth = 0
            for i, char in enumerate(text[start:], start):
                if char == '{':
                    depth += 1
                elif char == '}':
                    depth -= 1
                    if depth == 0:
                        json_str = text[start:i+1]
                        return json.loads(json_str)
            
            logger.warning("JSON 블록 종료 없음")
            return {}
            
        except Exception as e:
            logger.error(f"JSON 파싱 실패: {e}")
            return {}
    # -------------------------------------------------------
    # 검색 → 요약 → 검증 → High 필터링
    # -------------------------------------------------------
    def _analyze(self, results: List[Dict], analysis_type: str,
                 country_code: str, source_type: str) -> Dict:
        """
        검색 결과를 LLM으로 요약하고 Supervisor로 검증 후
        High 등급만 use_in_report=True 로 표시
        """

        urls = [r.get("url") for r in results if r.get("url")]
        source_validation = self.supervisor.validate_source(urls, country_code, source_type)

        # LLM 요약용 formatted block 생성
        formatted = "\n\n".join(
            f"[{i+1}] {r.get('title','N/A')}\n{(r.get('content') or '')[:400]}...\nURL: {r.get('url','')}"
            for i, r in enumerate(results[:3])
        )
        if not formatted.strip():
            return {
                "analysis_type": analysis_type,
                "info": "",
                "trust": {"overall_grade": "Low", "overall_score": 0},
                "use_in_report": False,
                "urls": []
            }

        # LLM Prompt
        prompt = f"""
당신은 대한민국 정부 산하 무역·시장 전문기관(KOTRA)의 
수석 애널리스트(Senior Export Market Intelligence Analyst)입니다.

========================================================
절대 준수해야 하는 핵심 규칙 (위반 시 보고서 무효)
========================================================
1) 제공된 VERIFIED SOURCES 안의 내용만 사용한다.
   - 새로운 사실, 추정, 가정, 브레인스토밍, 창작 절대 금지.
   - 제공되지 않은 수치·기관명·연도·법령·통계는 “출처 없음”이라고 명시.

2) FACT-CHECK RULES  
   - 숫자(%, $, 톤, 지수 등)는 반드시 출처에서 직접 확인된 값만 사용.
   - ‘아마’, ‘추정’, ‘전망된다’ 등 불확실한 표현 금지.
   - year, amount, %, rank가 언급될 때는 반드시 출처에 존재해야 함.

3) LANGUAGE RULES  
   - 한국어 공식 보고서 톤으로 작성.
   - 문헌 스타일: “~로 분석된다 / ~을 기준으로 판단된다 / ~을 보이며”
   - SNS 스타일·캐주얼 표현 금지.
   - ‘~같다, ~추정됨’ 같은 추측 문장 금지.

4) STRUCTURE & LENGTH RULES  
   - Executive Summary는 **400자 이상**
   - 모든 본문 섹션(시장 개요 / 규제 / 가격 / 리스크 / 수요)은 **400자 이상**
   - 정보가 부족한 경우 “해당 정보는 출처에 없음”을 명확히 기재.
   - 한 문단은 최소 5문장 이상.

5) SOURCE RELIABILITY RULES  
   - High 등급이 아닌 내용은 절대 포함하지 않는다.
   - 낮은 신뢰도의 정보는 즉시 배제한다.
   - 기관명을 언급할 경우 반드시 출처 내 명시된 기관명만 사용.

6) CITATION RULES  
   - 본문에 출처 표기하지 않는다. (ReportGenerator에서 자동 처리)
   - 대신 “출처 기반 근거 중심의 분석만 작성할 것”.

========================================================
분석 대상
- 국가: {country_code}
- 분석 유형: {analysis_type}

========================================================
VERIFIED PUBLIC SOURCES (아래 내용만 허용)
{formatted}

========================================================
수행할 작업
“위 검증된 근거 기반으로만” 다음 내용을 JSON으로 생성한다:

{
  "summary": "한국어로 된 분석 요약. 최소 400자. High 신뢰도 기반의 핵심 데이터만 포함",
  "key_numbers": ["출처에서 직접 확인된 수치 목록"],
  "main_sources": ["출처에 명시된 공식 기관명 목록 (예: USDA, 일본 MAFF)"],
  "limitations": ["출처에 없어서 제공할 수 없는 정보 목록"]
}

JSON 이외의 텍스트는 절대 포함하지 말 것.
JSON 앞뒤로 설명 문구도 절대 추가하지 말 것.
"""

        response_text = self._invoke_llm(prompt)
        parsed = self._safe_extract_json(response_text)

        summary_text = parsed.get("summary", "")
        trust = self.supervisor.compute_trust_breakdown(
            analysis_type=analysis_type,
            country_code=country_code,
            source_validation=source_validation,
            summary_text=summary_text
        )

        # High만 보고서 사용 가능
        use_flag = trust["overall_grade"] == "High"

        return {
            "analysis_type": analysis_type,
            "info": summary_text,
            "key_numbers": parsed.get("key_numbers", []),
            "main_sources": parsed.get("main_sources", []),
            "trust": trust,
            "source_validation": source_validation,
            "urls": urls,
            "use_in_report": use_flag
        }

    # -------------------------------------------------------
    # 분석 함수 묶음
    # -------------------------------------------------------
    def analyze_regulation(self, country: str, product: str, hs_code: str, code: str) -> Dict:
        query = f"{country} {product} import regulation HS {hs_code}"
        results = self._search_web(query)
        return self._analyze(results, "수입 규제", code, "regulation")

    def analyze_price(self, country: str, product: str, hs_code: str, code: str) -> Dict:
        y = datetime.now().year
        query = f"{country} {product} price trend {y}"
        results = self._search_web(query)
        return self._analyze(results, "가격 추세", code, "price_risk")

    def analyze_risk(self, country: str, product: str, hs_code: str, code: str) -> Dict:
        query = f"{country} {product} market risk factors"
        results = self._search_web(query)
        return self._analyze(results, "시장 리스크", code, "price_risk")

    def analyze_demand(self, country: str, product: str, hs_code: str, code: str) -> Dict:
        y = datetime.now().year
        query = f"{country} {product} demand forecast {y}"
        results = self._search_web(query)
        return self._analyze(results, "수요 전망", code, "price_risk")

    # -------------------------------------------------------
    # SNS 트렌드 분석 요청 (YouTube용)
    # -------------------------------------------------------
    def extract_sns_keyword(self, product: str) -> str:
        """
        generator.py에서 YouTube trend 그래프를 그릴 때 검색할 키워드 반환.
        해당 키워드가 youtube.csv 에 존재해야 그래프가 생성됨.
        """
        return product  # 여기서는 그대로 반환 (예: 바나나우유)


    # -------------------------------------------------------
    # DeepResearch 전체 호출
    # -------------------------------------------------------
    def run(self, country: str, product: str, hs_code: str, extra: List[str]) -> Dict:
        """
        extra = ["regulation", "price", "risk", "demand"]
        """
        logger.info(f"[DeepResearch] 실행 시작: {country}, {product}, {hs_code}")

        try:
            country_code = DataLoader.normalize_country(country)
        except ValueError as e:
            logger.error(str(e))
            return {}

        result = {}

        if "regulation" in extra:
            result["regulation"] = self.analyze_regulation(country, product, hs_code, country_code)

        if "price" in extra:
            result["price"] = self.analyze_price(country, product, hs_code, country_code)

        if "risk" in extra:
            result["risk"] = self.analyze_risk(country, product, hs_code, country_code)

        if "demand" in extra:
            result["demand"] = self.analyze_demand(country, product, hs_code, country_code)

        # SNS 키워드
        result["sns_keyword"] = self.extract_sns_keyword(product)

        # High 항목만 필터링 목록 생성
        result["high_sections"] = [
            k for k, v in result.items()
            if isinstance(v, dict) and v.get("use_in_report") is True
        ]

        logger.info(f"[DeepResearch] 완료 → High 목록: {result['high_sections']}")

        return result

    def run_all(self, country, product, hs_code, extra, country_code=None):
        """
        기존 main.py에서 country_code를 넘기기 때문에 
        호환성을 유지하기 위해 country_code를 받지만,
        내부에서는 사용하지 않고 무시합니다.
        """
        return self.run(country, product, hs_code, extra)


# ======================================================================
# RAGSearch 클래스 (main.py가 필요로 하는 공식 버전)
# ======================================================================

class RAGSearch:
    """
    국가 + HS코드 기준으로 벡터스토어에서 문서를 검색하고
    country_info JSON도 함께 반환하는 RAG 모듈
    """

    def __init__(self, vectordb: VectorDB):
        if not isinstance(vectordb, VectorDB):
            raise ValueError("vectordb는 VectorDB 인스턴스여야 합니다.")
        
        self.vectordb = vectordb
        self.supervisor = Supervisor()

    def build_query(self, country: str, hs_code: str) -> str:
        return f"{country} 시장 HS {hs_code} 수출 동향·규제·시장 분석"

    def search(self, country: str, hs_code: str, extra: Optional[List[str]] = None) -> Dict:
        logger.info(f"[RAGSearch] 시작: {country}, {hs_code}")

        try:
            country_code = DataLoader.normalize_country(country)
        except Exception as e:
            logger.error(f"국가명 오류: {e}")
            return {
                "country_code": None,
                "query": "",
                "documents": [],
                "country_info": {}
            }

        query = self.build_query(country, hs_code)

        docs = self.vectordb.search(
            query=query,
            country=country_code,
            k=5,
            score_threshold=0.65
        )

        structured_docs = []
        for d in docs:
            structured_docs.append({
                "content": d.page_content,
                "source": d.metadata.get("source", "N/A"),
                "year": d.metadata.get("year", "N/A"),
                "file_name": d.metadata.get("file_name", "N/A"),
                "page_start": d.metadata.get("page_start", 1),
                "page_end": d.metadata.get("page_end", 1),
                "citation": f"(출처: {d.metadata.get('file_name','N/A')} · p.{d.metadata.get('page_start','N/A')})"
            })

        # 국가 기본정보 JSON
        country_info_docs = DataLoader.process_country_json(country_code)
        country_info = {}
        if country_info_docs:
            try:
                combined = "".join(d.page_content for d in country_info_docs)
                country_info = json.loads(combined)
            except Exception:
                country_info = {}

        logger.info(f"[RAGSearch] 종료. 문서 {len(structured_docs)}건")

        return {
            "country_code": country_code,
            "query": query,
            "documents": structured_docs,
            "country_info": country_info
        }
