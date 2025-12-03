# deep_research.py
import os
import json
from typing import List, Dict, Optional
from datetime import datetime

from langchain_community.tools.tavily_search import TavilySearchResults
from langchain_openai import ChatOpenAI

# ----------------------------------------------------------
# 절대경로 설정
# ----------------------------------------------------------
BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
OUTPUT_DIR = os.path.join(BASE_DIR, "output")
META_PATH = os.path.join(BASE_DIR, "metadata", "table_image_index.json")

os.makedirs(OUTPUT_DIR, exist_ok=True)


# ----------------------------------------------------------
# 표/이미지 페이지 데이터 로드
# ----------------------------------------------------------
def load_table_image_index() -> Dict:
    try:
        with open(META_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        print(f"⚠ table_image_index.json 파일이 없습니다: {META_PATH}")
        return {}
    except json.JSONDecodeError as e:
        print(f"⚠ table_image_index.json 파싱 실패: {e}")
        return {}


TABLE_IMAGE_INDEX = load_table_image_index()


# ----------------------------------------------------------
# 슈퍼바이저 에이전트 (핵심 추가)
# ----------------------------------------------------------
class ResearchSupervisor:
    """
    Deep Research 검색 품질을 감독하고
    추가 검색이 필요한지 판단하는 에이전트
    """

    def __init__(self, model: str = "gpt-4o-mini"):
        self.llm = ChatOpenAI(model=model, temperature=0)
        self.max_iterations = 3  # 최대 검색 반복 횟수

    def evaluate_search_quality(
        self, search_results: List[Dict], query: str, research_type: str
    ) -> Dict:
        """
        검색 결과의 품질을 평가하고 다음 액션 결정

        Returns:
            {
                "quality_score": int (0-100),
                "is_sufficient": bool,
                "missing_aspects": List[str],
                "next_query_suggestions": List[str],
                "reasoning": str
            }
        """

        # 검색 결과 요약
        results_summary = self._summarize_results(search_results)

        prompt = f"""
당신은 시장조사 Deep Research의 **품질 감독관(Supervisor)**입니다.

【검색 정보】
- 연구 유형: {research_type}
- 원본 쿼리: {query}
- 검색 결과 개수: {len(search_results)}

【검색 결과 요약】
{results_summary}

【평가 기준】
다음 기준으로 검색 결과의 품질을 평가하세요:

1. **정보 완전성** (40점)
   - 최신 정보 포함 여부 (2024-2025)
   - 구체적 수치/통계 존재 여부
   - 신뢰할 수 있는 출처 (정부, 공식 기관, 주요 언론)

2. **정보 관련성** (30점)
   - 쿼리와의 직접적 연관성
   - 국가/품목 특정성
   - 실행 가능한 인사이트 포함

3. **정보 다양성** (30점)
   - 여러 관점의 정보
   - 다양한 출처
   - 상반된 의견이나 리스크 요인 포함

【요구 출력 (JSON)】
{{
  "quality_score": 0-100 사이 정수,
  "is_sufficient": true/false,
  "confidence": "high/medium/low",
  "strengths": ["강점1", "강점2"],
  "missing_aspects": ["부족한 부분1", "부족한 부분2"],
  "next_query_suggestions": ["추가 검색 쿼리1", "추가 검색 쿼리2"],
  "reasoning": "평가 근거 설명 (2-3문장)"
}}

【규칙】
- quality_score 70점 이상 → is_sufficient: true
- quality_score 70점 미만 → is_sufficient: false
- is_sufficient가 false면 next_query_suggestions 필수 제공 (1-3개)
- 검색 결과가 없거나 너무 일반적이면 낮은 점수
"""

        try:
            response = self.llm.invoke(prompt)
            result = response.content.strip()

            # JSON 파싱
            if "```json" in result:
                result = result.split("```json")[1].split("```")[0]

            evaluation = json.loads(result)
            return evaluation

        except Exception as e:
            print(f"⚠️ 슈퍼바이저 평가 실패: {e}")
            # 기본값 반환
            return {
                "quality_score": 50,
                "is_sufficient": False,
                "confidence": "low",
                "strengths": [],
                "missing_aspects": ["평가 실패로 인한 재검색 필요"],
                "next_query_suggestions": [query + " 최신 정보"],
                "reasoning": "평가 프로세스 오류로 인한 보수적 판단",
            }

    def _summarize_results(self, results: List[Dict]) -> str:
        """검색 결과를 요약하여 슈퍼바이저에게 제공"""
        if not results:
            return "검색 결과 없음"

        summary_parts = []
        for i, r in enumerate(results[:5], 1):  # 상위 5개만
            title = r.get("title", "제목 없음")
            content = r.get("content", "")[:200]  # 200자로 제한
            url = r.get("url", "")

            summary_parts.append(
                f"[{i}] {title}\n    내용: {content}...\n    출처: {url}\n"
            )

        return "\n".join(summary_parts)

    def decide_next_action(self, evaluation: Dict, current_iteration: int) -> str:
        """
        다음 액션 결정

        Returns:
            "continue" - 추가 검색 필요
            "stop" - 검색 종료
        """
        # 최대 반복 횟수 도달
        if current_iteration >= self.max_iterations:
            print(f"   ⏹ 최대 반복 횟수({self.max_iterations}) 도달 - 검색 종료")
            return "stop"

        # 품질 점수가 충분
        if evaluation.get("is_sufficient", False):
            print(f"   ✅ 품질 점수 {evaluation['quality_score']}/100 - 충분")
            return "stop"

        # 추가 검색 필요
        print(f"   🔄 품질 점수 {evaluation['quality_score']}/100 - 추가 검색 필요")
        print(f"   부족한 부분: {', '.join(evaluation.get('missing_aspects', []))}")
        return "continue"


# ----------------------------------------------------------
# Deep Research 엔진 (슈퍼바이저 통합)
# ----------------------------------------------------------
class DeepResearchEngine:
    """최신 정보 웹 검색 엔진 (슈퍼바이저 감독 포함)"""

    def __init__(self, model: str = "gpt-4o-mini"):
        if not os.getenv("TAVILY_API_KEY"):
            raise ValueError(
                "TAVILY_API_KEY가 설정되지 않았습니다.\n"
                ".env 파일에 다음을 추가하세요:\n"
                "TAVILY_API_KEY=tvly-..."
            )

        self.search_tool = TavilySearchResults(
            max_results=5,
            search_depth="advanced",
            include_answer=True,
            include_raw_content=False,
        )
        self.llm = ChatOpenAI(model=model, temperature=0.3)
        self.supervisor = ResearchSupervisor(model=model)  # 슈퍼바이저 추가

    # ----------------------------------------------------------
    # 표/이미지 페이지 조회 기능
    # ----------------------------------------------------------
    def get_special_pages(self, source: str, country_code: str, year: Optional[int]):
        try:
            source = source.upper()
            country_code = country_code.upper()

            if source not in TABLE_IMAGE_INDEX:
                return {}

            if country_code not in TABLE_IMAGE_INDEX[source]:
                return {}

            year = str(year)
            if year not in TABLE_IMAGE_INDEX[source][country_code]:
                return {}

            return TABLE_IMAGE_INDEX[source][country_code][year]

        except Exception as e:
            print(f"⚠ 표/이미지 페이지 조회 실패: {e}")
            return {}

    # ----------------------------------------------------------
    # 슈퍼바이저 기반 반복 검색 (핵심 메서드)
    # ----------------------------------------------------------
    def _iterative_search(
        self,
        initial_queries: List[str],
        research_type: str,
        country: str,
        product_name: str,
    ) -> Dict:
        """
        슈퍼바이저가 감독하는 반복 검색 프로세스

        Returns:
            {
                "all_results": List[Dict],  # 모든 검색 결과 누적
                "iterations": int,
                "final_evaluation": Dict,
                "search_log": List[Dict]
            }
        """
        all_results = []
        search_log = []
        queries_to_try = initial_queries.copy()
        iteration = 0

        print(f"\n{'=' * 60}")
        print(f"🔍 [{research_type}] 슈퍼바이저 검색 시작")
        print(f"{'=' * 60}")

        while iteration < self.supervisor.max_iterations:
            iteration += 1

            if not queries_to_try:
                print(f"\n⏹ 반복 {iteration}: 더 이상 시도할 쿼리 없음")
                break

            current_query = queries_to_try.pop(0)
            print(f"\n🔎 반복 {iteration}/{self.supervisor.max_iterations}")
            print(f"   쿼리: {current_query}")

            # 검색 실행
            try:
                results = self.search_tool.invoke({"query": current_query})
                print(f"   결과: {len(results)}개")
                all_results.extend(results)

            except Exception as e:
                print(f"   ❌ 검색 실패: {e}")
                results = []

            # 슈퍼바이저 평가
            evaluation = self.supervisor.evaluate_search_quality(
                search_results=results, query=current_query, research_type=research_type
            )

            # 로그 기록
            search_log.append(
                {
                    "iteration": iteration,
                    "query": current_query,
                    "results_count": len(results),
                    "evaluation": evaluation,
                }
            )

            # 다음 액션 결정
            action = self.supervisor.decide_next_action(evaluation, iteration)

            if action == "stop":
                print(f"   ✅ 검색 종료 (충분한 정보 확보)\n")
                break

            # 추가 쿼리 추가
            new_queries = evaluation.get("next_query_suggestions", [])
            if new_queries:
                print(f"   📝 추가 쿼리 {len(new_queries)}개 생성")
                queries_to_try.extend(new_queries)

        # 최종 평가
        final_evaluation = self.supervisor.evaluate_search_quality(
            search_results=all_results,
            query=f"{country} {product_name} {research_type}",
            research_type=research_type,
        )

        print(f"\n{'=' * 60}")
        print(f"📊 최종 결과:")
        print(f"   - 총 반복: {iteration}회")
        print(f"   - 수집 결과: {len(all_results)}개")
        print(f"   - 최종 점수: {final_evaluation['quality_score']}/100")
        print(f"   - 신뢰도: {final_evaluation.get('confidence', 'N/A')}")
        print(f"{'=' * 60}\n")

        return {
            "all_results": all_results,
            "iterations": iteration,
            "final_evaluation": final_evaluation,
            "search_log": search_log,
        }

    # ----------------------------------------------------------
    # 최신 규제 검색 (슈퍼바이저 적용)
    # ----------------------------------------------------------
    def search_latest_regulation(
        self, country: str, product_name: str, hs_code: str
    ) -> Dict:
        print(f"\n[Deep Research] 최신 규제 검색")
        print(f"국가: {country}, 품목: {product_name}")

        initial_queries = [
            f"{country} {product_name} 수입 규제 2025 변경",
            f"{country} 식품 수입 규제 최신 2025",
            f"{country} HS {hs_code[:4]} 관세 2025",
        ]

        # 슈퍼바이저 기반 검색
        search_result = self._iterative_search(
            initial_queries=initial_queries,
            research_type="규제 정보",
            country=country,
            product_name=product_name,
        )

        if not search_result["all_results"]:
            return {
                "latest_info": "최신 규제 정보를 찾을 수 없습니다.",
                "source": "N/A",
                "confidence": "low",
                "date": datetime.now().strftime("%Y-%m-%d"),
                "urls": [],
                "supervisor_log": search_result["search_log"],
                "quality_score": 0,
            }

        # GPT 분석
        analysis = self._analyze_search_results(
            search_result["all_results"], country, product_name
        )

        # 슈퍼바이저 메타데이터 추가
        analysis["supervisor_log"] = search_result["search_log"]
        analysis["quality_score"] = search_result["final_evaluation"]["quality_score"]
        analysis["confidence"] = search_result["final_evaluation"].get(
            "confidence", "medium"
        )

        return analysis

    # ----------------------------------------------------------
    # 가격 추세 검색 (슈퍼바이저 적용)
    # ----------------------------------------------------------
    def search_price_trend(self, country: str, product_name: str) -> Dict:
        print(f"\n[Deep Research] 가격 추세 검색")

        initial_queries = [
            f"{country} {product_name} 수입 가격 2025",
            f"{country} {product_name} 시장 가격 동향",
            f"{product_name} price trend {country} 2024 2025",
        ]

        search_result = self._iterative_search(
            initial_queries=initial_queries,
            research_type="가격 추세",
            country=country,
            product_name=product_name,
        )

        if not search_result["all_results"]:
            return {
                "latest_info": "가격 정보를 찾을 수 없습니다.",
                "source": "N/A",
                "confidence": "low",
                "trend": "unknown",
                "supervisor_log": search_result["search_log"],
                "quality_score": 0,
            }

        analysis = self._analyze_price_results(
            search_result["all_results"], country, product_name
        )

        analysis["supervisor_log"] = search_result["search_log"]
        analysis["quality_score"] = search_result["final_evaluation"]["quality_score"]

        return analysis

    # ----------------------------------------------------------
    # 시장 리스크 검색 (슈퍼바이저 적용)
    # ----------------------------------------------------------
    def search_market_risk(self, country: str, product_name: str) -> Dict:
        print(f"\n[Deep Research] 시장 리스크 검색")

        initial_queries = [
            f"{country} 식품 시장 리스크 2025",
            f"{country} 경제 전망 2025",
            f"{country} {product_name} 시장 위험 요인",
        ]

        search_result = self._iterative_search(
            initial_queries=initial_queries,
            research_type="시장 리스크",
            country=country,
            product_name=product_name,
        )

        if not search_result["all_results"]:
            return {
                "latest_info": "리스크 정보를 찾을 수 없습니다.",
                "source": "N/A",
                "confidence": "low",
                "risk_level": "unknown",
                "supervisor_log": search_result["search_log"],
                "quality_score": 0,
            }

        analysis = self._analyze_risk_results(search_result["all_results"], country)

        analysis["supervisor_log"] = search_result["search_log"]
        analysis["quality_score"] = search_result["final_evaluation"]["quality_score"]

        return analysis

    # ----------------------------------------------------------
    # GPT 분석 로직 (기존 유지)
    # ----------------------------------------------------------
    def _analyze_search_results(self, results: List, country: str, product_name: str):
        formatted = self._format_results(results)

        prompt = f"""
다음은 {country} {product_name} 수입 규제에 대한 검색 결과입니다.

{formatted}

위 정보를 바탕으로 최신 규제 사항(2024~2025)을 정리하세요.

JSON 형식으로 출력:
{{
  "latest_info": "...",
  "source": "...",
  "confidence": "high/medium/low",
  "date": "YYYY-MM-DD",
  "key_changes": ["...", "..."],
  "urls": ["...", "..."]
}}
"""

        try:
            res = self.llm.invoke(prompt).content.strip()
            if "```json" in res:
                res = res.split("```json")[1].split("```")[0]
            return json.loads(res)
        except:
            return {
                "latest_info": formatted[:300],
                "source": "multiple sources",
                "confidence": "medium",
                "date": datetime.now().strftime("%Y-%m-%d"),
                "urls": [],
            }

    def _analyze_price_results(self, results, country, product_name):
        formatted = self._format_results(results)

        prompt = f"""
다음은 {country} {product_name} 가격 동향 검색 결과입니다.

{formatted}

JSON 형식으로 출력:
{{
  "latest_info": "...",
  "source": "...",
  "confidence": "high/medium/low",
  "trend": "상승/하락/안정"
}}
"""

        try:
            res = self.llm.invoke(prompt).content.strip()
            if "```json" in res:
                res = res.split("```json")[1].split("```")[0]
            return json.loads(res)
        except:
            return {
                "latest_info": "가격 분석 실패",
                "source": "N/A",
                "confidence": "low",
                "trend": "unknown",
            }

    def _analyze_risk_results(self, results, country):
        formatted = self._format_results(results)

        prompt = f"""
다음은 {country} 시장 리스크 검색 결과입니다.

{formatted}

JSON 형식으로 출력:
{{
  "latest_info": "...",
  "source": "...",
  "confidence": "high/medium/low",
  "risk_level": "high/medium/low",
  "key_risks": ["...", "..."]
}}
"""

        try:
            res = self.llm.invoke(prompt).content.strip()
            if "```json" in res:
                res = res.split("```json")[1].split("```")[0]
            return json.loads(res)
        except:
            return {
                "latest_info": "리스크 분석 실패",
                "source": "N/A",
                "confidence": "low",
                "risk_level": "unknown",
                "key_risks": [],
            }

    def _format_results(self, results: List) -> str:
        formatted = []
        for i, r in enumerate(results[:10], 1):
            if isinstance(r, dict):
                title = r.get("title", "N/A")
                content = r.get("content", "")
                url = r.get("url", "")
                formatted.append(f"[{i}] {title}\n{content[:250]}...\nURL: {url}\n")
        return "\n".join(formatted)

    # ----------------------------------------------------------
    # 전체 연구 실행
    # ----------------------------------------------------------
    def run_all_research(
        self,
        country: str,
        product_name: str,
        hs_code: str,
        extra_analysis: List[str],
        table_image_hint: Optional[Dict] = None,
    ) -> Dict:
        results = {}

        results["latest_regulation"] = self.search_latest_regulation(
            country, product_name, hs_code
        )

        if "가격 추세" in extra_analysis:
            results["price_trend"] = self.search_price_trend(country, product_name)

        if "시장 리스크" in extra_analysis:
            results["market_risk"] = self.search_market_risk(country, product_name)

        # 표/이미지 페이지 정보 추가
        if table_image_hint:
            results["table_image_hint"] = table_image_hint

        return results


# ----------------------------------------------------------
# 테스트 코드
# ----------------------------------------------------------
if __name__ == "__main__":
    from dotenv import load_dotenv

    load_dotenv()

    dr_engine = DeepResearchEngine()

    result = dr_engine.run_all_research(
        country="일본",
        product_name="견과류 조제품",
        hs_code="2008190000",
        extra_analysis=["시장 리스크", "가격 추세"],
        table_image_hint={
            "2024_kati_JP.pdf": {
                "table_pages": [1, 2, 3, 4],
                "image_pages": [12, 16, 18],
            }
        },
    )

    out_path = os.path.join(OUTPUT_DIR, "deep_research_result.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    print(f"\nDeep Research 결과 저장 완료: {out_path}")
