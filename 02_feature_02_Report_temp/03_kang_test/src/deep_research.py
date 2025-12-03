# deep_research.py
"""
Deep Research Engine
- Tavily 웹 검색 기반 최신 정보 수집
- Supervisor 모듈을 통한 공공기관 출처 검증
- 검증된 출처만을 사용하여 LLM 요약 수행
"""

import json
from typing import Dict, List
from langchain_openai import ChatOpenAI
from langchain_core.messages import AIMessage
from tavily import TavilyClient
from supervisor import Supervisor


# LLM 호출 관련 유틸 함수
def safe_llm_invoke(llm, prompt: str) -> str:
    """LLM 호출을 안전하게 수행하는 래퍼 함수 — 실패 시 JSON 오류 반환"""
    try:
        response = llm.invoke(prompt)
        return response.content if isinstance(response, AIMessage) else str(response)
    except Exception as e:
        return f'{{"error": "LLM invocation failed: {str(e)}"}}'


def safe_json_parse(text: str) -> Dict:
    """LLM 응답에서 JSON 블록만 안전하게 파싱"""
    import re
    # Markdown 코드 블록 제거
    text = re.sub(r'```(?:json)?\s*', '', text)
    text = re.sub(r'```\s*$', '', text)
    
    # Non-greedy JSON 매칭
    match = re.search(r'\{(?:[^{}]|(?:\{[^{}]*\}))*\}', text, re.DOTALL)
    if not match:
        return {"error": "JSON not found in response"}
    
    try:
        return json.loads(match.group(0))
    except json.JSONDecodeError as e:
        return {"error": f"JSON parse failed: {str(e)}"}



# Deep Research Engine 클래스
class DeepResearchEngine:
    """
    Deep Research Engine
    - Tavily 기반 인터넷 최신 정보 검색
    - Supervisor로 출처 검증(공공기관/국제기구)
    - 검증된 데이터로만 LLM 요약 생성
    """

    def __init__(self, model: str = "gpt-4o-mini"):
        self.llm = ChatOpenAI(model=model, temperature=0.3)
        self.supervisor = Supervisor(model=model)
        self.tavily = TavilyClient()
        self.max_iterations = 3  # 반복 검색 최대 횟수

    # 반복 검색 수행
    def _iterative_search(
        self, queries: List[str], research_type: str, country_code: str
    ) -> Dict:
        """
        Tavily 검색을 반복 수행하여 충분한 품질을 확보할 때까지 검색.
        - 최대 2개의 쿼리만 사용
        - Supervisor가 검색 품질 평가
        """

        all_results = []
        iteration = 0

        for q in queries[:2]:
            try:
                raw = self.tavily.search(
                    query=q,
                    search_depth="advanced",
                    max_results=5
                )
                results = raw.get("results", [])
                all_results.extend(results)

                # Supervisor가 검색 품질 검사
                eval_result = self.supervisor.evaluate_search_quality(
                    results, q, research_type, country_code
                )

                # 품질이 충분하면 반복 종료
                if eval_result["is_sufficient"] and eval_result["quality_score"] >= 70:
                    break

                iteration += 1
                if iteration >= self.max_iterations:
                    break

            except Exception as e:
                print("Search error:", e)
                continue

        return {
            "results": all_results,
            "total_found": len(all_results)
        }

    # 검증된 결과를 기반으로 LLM 요약 생성
    def _analyze(
        self, results: List[Dict], analysis_type: str, context: str, country_code: str
    ) -> Dict:
        """
        검색 결과를 Supervisor로 검증한 뒤,
        검증된 출처만 기반으로 LLM 요약 생성.

        결과 구조:
        {
            "latest_info": "...",
            "source": "...",
            "confidence": "...",
            "urls": [...],
            "validation": {...}
        }
        """

        # 결과 없음
        if not results:
            return {
                "latest_info": f"No data for {analysis_type}",
                "source": "N/A",
                "confidence": "no_data",
                "urls": []
            }

        urls = [r.get("url", "") for r in results]
        source_type = "regulation" if "regulation" in analysis_type.lower() else "price_risk"

        validation = self.supervisor.validate_source(urls, country_code, source_type)

        # 공공기관/국제기구 출처 없음 → 사용 불가
        valid_urls = validation["valid_urls"]
        if not valid_urls:
            return {
                "latest_info": f"No valid public sources for {analysis_type}",
                "source": "N/A",
                "confidence": "low",
                "urls": [],
                "warnings": validation["warnings"]
            }

        # 검증된 결과만 필터링
        valid_results = [r for r in results if r.get("url") in valid_urls]

        # LLM 입력용 포맷 구성
        formatted = "\n".join(
            f"[{i+1}] {r.get('title','N/A')}\n"
            f"{(r.get('content') or '')[:200]}...\n"
            f"URL: {r.get('url','')}"
            for i, r in enumerate(valid_results[:5])
        )

        # 영어 프롬프트 — LLM에게 전달
        prompt = f"""
You are an analytical research assistant specializing in verified, source-based factual synthesis.
Your task is to create a **strictly evidence-grounded summary** based ONLY on the *public institution–verified* search results provided below.
DO NOT use background knowledge, prior training data, assumptions, or anything not explicitly contained in the given text.
---

### Context
{context}

### Analysis Type
{analysis_type}

### Verified Search Results
(Only the URLs approved by source validation)
{formatted}

---

### STRICT RULES — FOLLOW EXACTLY
1. **Use ONLY the information shown above.**  
- If a fact is not explicitly included, it MUST NOT appear in the summary.

2. **ABSOLUTELY NO GUESSING or FILLING GAPS.**  
- No speculation, no implied interpretation, no generic statements.

3. **All insights must be traceable to the text above.**  
- Every claim must be directly grounded in the provided content.

4. **Include numerical data whenever available.**  
Examples:
- Percentages
- Growth rates
- Year-over-year changes
- Import/export volumes
- Market size figures

5. **Be concise, factual, and source-based.**  
- No adjectives without numerical support.
- No filler statements (“important”, “big market”, “strong demand”).

6. **If information is missing, explicitly state that it is not available.**

---

### OUTPUT FORMAT (JSON only)
Return a clean JSON object with NO extra explanations:

{{
"latest_info": "Factual summary using ONLY the provided data, including numerical metrics.",
"source": "Primary or most authoritative source name (from the list above)",
"confidence": "high/medium/low",
"urls": {valid_urls[:3]}
}}

Make sure the JSON is valid and parseable.
"""

        # LLM 응답 처리
        response = safe_llm_invoke(self.llm, prompt)
        parsed = safe_json_parse(response)

        parsed["urls"] = valid_urls[:3]
        parsed["validation"] = validation
        return parsed

    # 검색 종류별 API

    def search_regulation(self, country, product, hs_code, country_code):
        """규제 정보 검색 (공공기관 only)"""
        queries = [
            f"{country} {product} import regulation {hs_code}",
            f"{country} {hs_code} certification requirement"
        ]
        raw = self._iterative_search(queries, "regulation info", country_code)
        return self._analyze(
            raw["results"], "Regulation", f"{country} {product}", country_code
        )

    def search_price(self, country, product, country_code):
        """가격 추세 검색 (공공기관 + 국제기구 허용)"""
        queries = [
            f"{country} {product} price trend 2024",
            f"{country} {product} price statistics"
        ]
        raw = self._iterative_search(queries, "price trend", country_code)
        return self._analyze(
            raw["results"], "Price", f"{country} {product}", country_code
        )

    def search_risk(self, country, product, country_code):
        """시장 리스크 검색"""
        queries = [
            f"{country} market risk 2024",
            f"{country} trade barrier {product}"
        ]
        raw = self._iterative_search(queries, "market risk", country_code)
        return self._analyze(
            raw["results"], "Risk", country, country_code
        )

    # 전체 분석 실행

    def run_all_research(
        self, country: str, product: str, hs_code: str, extra: List[str], country_code: str
    ) -> Dict:
        """
        사용자의 요청에 따라
        규제 / 가격 / 리스크 분석을 모두 수행 후 결과 반환.
        """

        result = {
            "latest_regulation": self.search_regulation(
                country, product, hs_code, country_code
            )
        }

        if "가격 추세" in extra:
            result["price_trend"] = self.search_price(country, product, country_code)

        if "시장 리스크" in extra:
            result["market_risk"] = self.search_risk(country, product, country_code)

        result["validation_summary"] = self.supervisor.get_validation_summary()
        return result
