# search_engine.py
import json
from typing import Dict

from langchain_openai import ChatOpenAI
from langchain_core.documents import Document

from vectordb_manager import VectorDBManager, SearchEngine as BaseSearchEngine
from data_loader import DataLoader


class QueryGenerator:
    def __init__(self, model: str = "gpt-4o-mini"):
        self.llm = ChatOpenAI(model=model, temperature=0.0)

    def generate_queries(self, payload: Dict) -> str:
        prompt = """
You are an expert search-query generator for a RAG (Retrieval-Augmented Generation) system.
Your objective is to generate the most effective Korean-language query_text for retrieving documents from a vector database.

You will receive a JSON payload containing:
- country_name_kor
- hs_code
- default_sections
- user_requirements (five boolean fields)
- custom_request_text

Rules:
1. Always generate the final query_text in Korean.
2. The query must begin with:
   “{country_name_kor} 시장 HS {hs_code}”
3. Always include the mandatory compressed analysis phrase:
   “시장규모·수출현황·트렌드·전망·PEST·SWOT·전략”
4. For every TRUE field in user_requirements, append the corresponding Korean label:
   include_market_risk → “시장 리스크”
   include_price_trend → “가격 추세”
   include_regulation_review → “규제 검토”
   include_demand_forecast → “수요전망”
   include_table_summary → “요약 표”
5. If custom_request_text is provided, append it at the end.
6. Combine all components with “ / ” as separators.
7. Output the final query_text only.

Safety:
- Do NOT invent any information not present in the payload.
- Do NOT add facts, numbers, years, or assumptions.
- If some information is absent, simply omit it.
"""

        merged = (
            prompt
            + "\n\nPAYLOAD:\n"
            + json.dumps(payload, ensure_ascii=False, indent=2)
        )
        response = self.llm.invoke(merged)
        text = response.content.strip()

        if "```" in text:
            text = text.split("```")[1].split("```")[0]

        return text


class IntegratedSearchEngine:
    def __init__(self, vectordb_manager: VectorDBManager, data_loader: DataLoader):
        self.vectordb = vectordb_manager
        self.data_loader = data_loader
        self.base_search = BaseSearchEngine(vectordb_manager)
        self.query_gen = QueryGenerator()

    def search_all(self, user_input: Dict) -> Dict:
        country_name = user_input["country"]
        country_code = self.data_loader.normalize_country(country_name)
        hs_code = user_input["hs_code"]
        extra_analysis = user_input.get("extra_analysis", [])
        sns_keyword = user_input.get("sns_keyword")

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

        query_text = self.query_gen.generate_queries(payload)
        queries = {"market": query_text}

        vectordb_results = self.base_search.search_all_sections(
            queries=queries,
            country=country_code,
            hs_code=hs_code,
            k_per_section=5,
        )

        country_info = self.data_loader.load_country_info(country_code)

        sections = {}
        sources_used = {"KATI": 0, "KOTRA": 0, "COUNTRY_INFO": 1 if country_info else 0}

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
                src = meta.get("source")
                if src in sources_used:
                    sources_used[src] += 1
            sections[section_name] = entries

        empty_sections = [name for name, docs in vectordb_results.items() if not docs]

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
        }
