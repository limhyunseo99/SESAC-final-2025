# integrated_search.py
import os
import json
from typing import Dict
from langchain_openai import ChatOpenAI
from vectordb_manager import VectorDBManager, SearchEngine as BaseSearchEngine
from data_loader import DataLoader
from dotenv import load_dotenv
from deep_research import DeepResearchEngine

load_dotenv()

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
TABLE_INDEX_PATH = os.path.join(BASE_DIR, "metadata", "table_image_index.json")
VECTORDB_DIR = os.path.join(BASE_DIR, "vectordb_store")


def load_table_image_index():
    try:
        with open(TABLE_INDEX_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except:
        print(f"⚠ 표/이미지 메타데이터 로드 실패: {TABLE_INDEX_PATH}")
        return {}


TABLE_IMAGE_INDEX = load_table_image_index()

# QueryGenerator (프롬프트 최신화)
class QueryGenerator:
    def __init__(self, model: str = "gpt-4o-mini"):
        self.llm = ChatOpenAI(model=model, temperature=0.3)

    def generate_queries(self, payload: Dict) -> str:
        prompt = """
You are an expert search-query generator designed for a Korean-language
Retrieval-Augmented Generation (RAG) system.

Your task is to generate the most effective, information-dense Korean
query_text for retrieving relevant documents from a vector database.

You will receive a JSON payload containing:
- country_name_kor: Target country name in Korean
- hs_code: 10-digit HS code
- default_sections: Mandatory analysis areas
- user_requirements: Boolean analysis options selected by the user
- custom_request_text: Optional free-text keyword provided by the user

Rules you MUST follow:

1. Always produce the final query_text **in Korean only**.

2. The query must ALWAYS begin with:
   “{country_name_kor} 시장 HS {hs_code}”

3. Afterwards, you MUST append the compressed phrase representing all
   mandatory analysis categories, exactly as follows:
   “시장규모·수출현황·트렌드·전망·PEST·SWOT·전략”

4. For each TRUE value inside user_requirements, append the EXACT Korean label:
   - include_market_risk → “시장 리스크”
   - include_price_trend → “가격 추세”
   - include_regulation_review → “규제 검토”
   - include_demand_forecast → “수요전망”
   - include_table_summary → “요약 표”

5. If custom_request_text is provided, append it last.

6. Combine ALL elements using “ / ” as separators.
   Do NOT add anything else.

7. Output ONLY the final query_text string.
   Do NOT explain, do NOT describe, do NOT add formatting.

STRICT SAFETY RULES:
- DO NOT invent or assume any information not contained in the payload.
- DO NOT add numbers, years, facts, statistics, or examples.
- Use ONLY the explicit content of the payload.
- If a field is missing, simply omit it without substituting anything.

Your output must always be a single Korean query string.
"""

        response = self.llm.invoke(
            prompt
            + "\n\nPAYLOAD:\n"
            + json.dumps(payload, ensure_ascii=False, indent=2)
        )
        text = response.content.strip()
        if "```" in text:
            text = text.split("```")[1].split("```")[0]
        return text


# Integrated Search Engine
class IntegratedSearchEngine:
    def __init__(self, vectordb_manager: VectorDBManager, data_loader: DataLoader):
        self.vectordb = vectordb_manager
        self.data_loader = data_loader
        self.base_search = BaseSearchEngine(vectordb_manager)
        self.query_gen = QueryGenerator()

    # 파일명 기준 표/이미지 페이지 조회
    def get_table_image_hint(self, source: str, country_code: str, year):
        try:
            source = source.upper()
            country_code = country_code.upper()
            year = str(year)

            if source not in TABLE_IMAGE_INDEX:
                return {}

            if country_code not in TABLE_IMAGE_INDEX[source]:
                return {}

            if year not in TABLE_IMAGE_INDEX[source][country_code]:
                return {}

            return TABLE_IMAGE_INDEX[source][country_code][year]

        except Exception as e:
            print(f"⚠ 표/이미지 페이지 조회 실패: {e}")
            return {}

    # 메인 처리
    def search_all(self, user_input: Dict) -> Dict:
        country_name = user_input["country"]
        country_code = self.data_loader.normalize_country(country_name)
        hs_code = user_input["hs_code"]
        extra_analysis = user_input.get("extra_analysis", [])
        sns_keyword = user_input.get("sns_keyword")

        # 프롬프트 생성용 payload
        payload = {
            "country_name_kor": country_name,
            "hs_code": hs_code,
            "default_sections": ["market", "regulation", "distribution", "strategy"],
            "user_requirements": {
                "include_market_risk": "시장 리스크" in extra_analysis,
                "include_price_trend": "가격 추세" in extra_analysis,
                "include_regulation_review": "규제 검토" in extra_analysis,
                "include_demand_forecast": "수요전망" in extra_analysis,
                "include_table_summary": "요약 표" in extra_analysis,
            },
            "custom_request_text": sns_keyword,
        }

        # 1) GPT 검색 쿼리 생성
        query_text = self.query_gen.generate_queries(payload)
        queries = {"market": query_text}
        
        # 2) VectorDB 검색
        vectordb_results = self.base_search.search_all_sections(
            queries=queries,
            country=country_code,
            hs_code=hs_code,
            k_per_section=5,
        )

        # 3) 국가정보 (JSON)
        country_info = self.data_loader.load_country_info(country_code)

        sections = {}
        sources_used = {
            "KATI": 0,
            "KOTRA": 0,
            "COUNTRY_INFO": 1 if country_info else 0,
        }

        # 4) 표/이미지 힌트 수집
        table_image_hint = {}

        for section_name, docs in vectordb_results.items():
            entries = []

            for doc in docs:
                meta = doc.metadata

                entries.append(
                    {
                        "content": doc.page_content,
                        "source": meta.get("source"),
                        "country_code": meta.get("country_code"),
                        "year": meta.get("year"),
                        "file_name": meta.get("file_name"),
                        "page_chunk": meta.get("page_chunk"),
                    }
                )

                # 출처 통계 업데이트
                src = meta.get("source")
                if src in sources_used:
                    sources_used[src] += 1

                # 표/이미지 힌트 조회
                hint = self.get_table_image_hint(
                    source=meta.get("source"),
                    country_code=meta.get("country_code"),
                    year=meta.get("year"),
                )

                if hint:
                    table_image_hint[meta.get("file_name")] = hint

            sections[section_name] = entries

        empty_sections = [name for name, docs in vectordb_results.items() if not docs]

        # 최종 결과 반환 (Deep Research 단계에서 반드시 필요!)
        return {
            "request_info": {
                "country_name": country_name,
                "country_code": country_code,
                "hs_code": hs_code,
                "extra_analysis": extra_analysis,
                "sns_keyword": sns_keyword,
            },
            "country_background": country_info,
            "sections": sections,
            "sections_needing_deep_research": empty_sections,
            "sources_used": sources_used,
            "table_image_hint": table_image_hint,

            # 여기부터 Deep Research 전달용 메타데이터 추가
            "deep_research_payload": {
                "country": country_name,
                "country_code": country_code,
                "hs_code": hs_code,
                "extra_analysis": extra_analysis,
                "sns_keyword": sns_keyword,
                "vector_summary": {
                    "sections_found": list(sections.keys()),
                    "sections_missing": empty_sections,
                    "sources_used": sources_used,
                },
                "table_image_hint": table_image_hint,
            },
        }


if __name__ == "__main__":
    print("\n==============================")
    print("🔍 Integrated Search Test Start")
    print("==============================\n")

    from dotenv import load_dotenv

    load_dotenv()

    # VectorDB 로드
    vectordb = VectorDBManager(persist_dir=VECTORDB_DIR)
    vectordb.load_vectorstore()

    # DataLoader 초기화 (인자 없음)
    loader = DataLoader()

    search_engine = IntegratedSearchEngine(vectordb, loader)

    test_input = {
        "country": "일본",
        "hs_code": "2008190000",
        "extra_analysis": ["시장 리스크", "가격 추세"],
        "sns_keyword": "바나나우유",
    }

    result = search_engine.search_all(test_input)

    print("\n검색 결과 요약:")
    print(json.dumps(result, ensure_ascii=False, indent=2))

    print("\n==============================")
    print("✅ Integrated Search Test Finished")
    print("==============================\n")
    dr = DeepResearchEngine()

    # Deep Research 호출

    dr = DeepResearchEngine()

    dr_result = dr.run_all_research(
        country=result["deep_research_payload"]["country"],
        product_name="바나나우유",
        hs_code=result["deep_research_payload"]["hs_code"],
        extra_analysis=result["deep_research_payload"]["extra_analysis"],
    )

    print("\n===== Deep Research 결과 =====")
    print(json.dumps(dr_result, ensure_ascii=False, indent=2))
