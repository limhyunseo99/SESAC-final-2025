"""
검색 엔진 - GPT 기반 쿼리 생성 및 통합 검색
"""

import os
import json
from typing import List, Dict, Optional
from pathlib import Path

from langchain_openai import ChatOpenAI
from langchain.schema import Document

from vectordb_manager import VectorDBManager, SearchEngine as BaseSearchEngine
from data_loader import DataLoader


class QueryGenerator:
    """GPT를 사용한 검색 쿼리 자동 생성"""

    def __init__(self, model: str = "gpt-4o-mini"):
        self.llm = ChatOpenAI(model=model, temperature=0.3)

    def generate_queries(
        self, country: str, hs_code: str, product_name: str, extra_analysis: List[str]
    ) -> Dict[str, str]:
        """
        섹션별 검색 쿼리 생성

        Args:
            country: 국가명
            hs_code: HS CODE
            product_name: 품목명
            extra_analysis: 추가 분석 항목

        Returns:
            Dict[str, str]: 섹션별 쿼리
        """
        prompt = f"""
당신은 해외 시장 조사 전문가입니다.
다음 정보를 바탕으로 VectorDB 검색에 사용할 최적의 검색 쿼리를 생성하세요.

**입력 정보**:
- 국가: {country}
- HS CODE: {hs_code} (앞 4자리: {hs_code[:4]})
- 품목명: {product_name}
- 추가 분석: {", ".join(extra_analysis) if extra_analysis else "없음"}

**생성할 쿼리**:
1. market (시장 분석): 시장 규모, 성장률, 트렌드
2. regulation (규제 환경): 수입 규제, 인증, 통관
3. distribution (유통 구조): 유통 채널, 온라인/오프라인
4. strategy (진출 전략): 진입 전략, 현지화 방안
5. risk (리스크 - 선택 항목에 있을 경우만)
6. price_trend (가격 추세 - 선택 항목에 있을 경우만)

**요구사항**:
- 각 쿼리는 5-10단어로 간결하게
- 국가명과 품목명 포함
- VectorDB 검색에 최적화된 키워드 중심

JSON 형식으로 출력:
{{
    "market": "...",
    "regulation": "...",
    "distribution": "...",
    "strategy": "...",
    "risk": "..." (필요시),
    "price_trend": "..." (필요시)
}}
"""

        response = self.llm.invoke(prompt)

        # JSON 파싱
        try:
            content = response.content.strip()
            # ```json 제거
            if "```json" in content:
                content = content.split("```json")[1].split("```")[0]
            elif "```" in content:
                content = content.split("```")[1].split("```")[0]

            queries = json.loads(content)

            # 선택 항목 필터링
            if "시장 리스크" not in extra_analysis:
                queries.pop("risk", None)
            if "가격 추세" not in extra_analysis:
                queries.pop("price_trend", None)

            print(f"✅ 쿼리 생성 완료:")
            for key, value in queries.items():
                print(f"   {key}: {value}")

            return queries

        except Exception as e:
            print(f"❌ 쿼리 파싱 실패: {e}")
            # 폴백: 기본 쿼리 생성
            return self._generate_fallback_queries(
                country, product_name, extra_analysis
            )

    def _generate_fallback_queries(
        self, country: str, product_name: str, extra_analysis: List[str]
    ) -> Dict[str, str]:
        """기본 쿼리 생성 (GPT 실패 시)"""
        queries = {
            "market": f"{country} {product_name} 시장 규모 트렌드",
            "regulation": f"{country} {product_name} 수입 규제 인증",
            "distribution": f"{country} {product_name} 유통 구조",
            "strategy": f"{country} {product_name} 진출 전략",
        }

        if "시장 리스크" in extra_analysis:
            queries["risk"] = f"{country} 식품 시장 리스크"
        if "가격 추세" in extra_analysis:
            queries["price_trend"] = f"{country} {product_name} 가격 동향"

        return queries

    def hs_code_to_product_name(self, hs_code: str) -> str:
        """HS CODE → 품목명 변환 (GPT 사용)"""
        prompt = f"""
HS CODE {hs_code}에 해당하는 한국어 품목명을 알려주세요.

다음 형식으로 답변:
{{
    "product_name": "간결한 품목명",
    "category": "대분류",
    "description": "한 줄 설명"
}}
"""

        response = self.llm.invoke(prompt)

        try:
            content = response.content.strip()
            if "```json" in content:
                content = content.split("```json")[1].split("```")[0]

            result = json.loads(content)
            return result["product_name"]
        except:
            # 폴백
            hs_prefix = hs_code[:4]
            fallback_map = {
                "2008": "견과류 조제품",
                "0810": "신선 과일",
                "1901": "맥아추출물",
                # ... 더 추가
            }
            return fallback_map.get(hs_prefix, "식품")


class IntegratedSearchEngine:
    """VectorDB + 국가정보 JSON 통합 검색"""

    def __init__(self, vectordb_manager: VectorDBManager, data_loader: DataLoader):
        self.vectordb = vectordb_manager
        self.data_loader = data_loader
        self.base_search = BaseSearchEngine(vectordb_manager)
        self.query_gen = QueryGenerator()

    def search_all(self, user_input: Dict) -> Dict:
        """
        전체 검색 실행 (VectorDB + 국가정보 JSON)

        Args:
            user_input: {
                "country": "일본",
                "hs_code": "2008190000",
                "extra_analysis": ["시장 리스크", "규제 검토"],
                "sns_keyword": "과일"
            }

        Returns:
            Dict: 통합 검색 결과
        """
        country = user_input["country"]
        hs_code = user_input["hs_code"]
        extra_analysis = user_input.get("extra_analysis", [])

        print(f"\n{'=' * 50}")
        print(f"🔍 통합 검색 시작")
        print(f"   국가: {country}")
        print(f"   HS CODE: {hs_code}")
        print(f"{'=' * 50}\n")

        # 1. HS CODE → 품목명 변환
        print("1️⃣ HS CODE → 품목명 변환 중...")
        product_name = self.query_gen.hs_code_to_product_name(hs_code)
        print(f"   ✅ {hs_code} → {product_name}\n")

        # 2. 검색 쿼리 생성
        print("2️⃣ 검색 쿼리 생성 중...")
        queries = self.query_gen.generate_queries(
            country=country,
            hs_code=hs_code,
            product_name=product_name,
            extra_analysis=extra_analysis,
        )
        print()

        # 3. VectorDB 검색 (섹션별)
        print("3️⃣ VectorDB 검색 중...")
        vectordb_results = self.base_search.search_all_sections(
            queries=queries, country=country, hs_code=hs_code, k_per_section=5
        )
        print()

        # 4. 국가정보 JSON 로드
        print("4️⃣ 국가정보 로드 중...")
        country_info = self.data_loader.load_country_info(country)
        print()

        # 5. 결과 통합
        integrated_result = {
            "request_info": {
                "country": country,
                "hs_code": hs_code,
                "product_name": product_name,
                "extra_analysis": extra_analysis,
                "sns_keyword": user_input.get("sns_keyword"),
            },
            "country_background": {
                "economy": country_info.get("경제현황", ""),
                "trade_relation": country_info.get("한국과의관계", ""),
                "market_characteristics": country_info.get("시장특성", ""),
                "import_regulation": country_info.get("수입관제및관세", ""),
            },
            "sections": {},
            "sources_used": {
                "KATI": 0,
                "KOTRA": 0,
                "country_json": 1 if country_info else 0,
            },
        }

        # 섹션별 결과 정리
        for section_name, docs in vectordb_results.items():
            section_data = []

            for doc in docs:
                section_data.append(
                    {
                        "source": doc.metadata.get("source"),
                        "content": doc.page_content,
                        "page": doc.metadata.get("page", "N/A"),
                        "file_name": doc.metadata.get("file_name", "N/A"),
                        "year": doc.metadata.get("year", 2024),
                    }
                )

                # 출처 카운트
                source = doc.metadata.get("source")
                if source in integrated_result["sources_used"]:
                    integrated_result["sources_used"][source] += 1

            integrated_result["sections"][section_name] = section_data

        print(f"\n{'=' * 50}")
        print(f"✅ 통합 검색 완료!")
        print(f"   KATI 문서: {integrated_result['sources_used']['KATI']}개")
        print(f"   KOTRA 문서: {integrated_result['sources_used']['KOTRA']}개")
        print(f"   국가정보: {'✓' if country_info else '✗'}")
        print(f"{'=' * 50}\n")

        return integrated_result


# 테스트 코드
if __name__ == "__main__":
    # VectorDB 로드
    db_manager = VectorDBManager()
    db_manager.load_vectorstore()

    # 데이터 로더
    data_loader = DataLoader()

    # 통합 검색 엔진
    search_engine = IntegratedSearchEngine(db_manager, data_loader)

    # 테스트 입력
    test_input = {
        "country": "일본",
        "hs_code": "2008190000",
        "extra_analysis": ["시장 리스크", "규제 검토"],
        "sns_keyword": "과일",
    }

    # 검색 실행
    result = search_engine.search_all(test_input)

    # 결과 저장 (동료에게 전달할 JSON)
    output_file = "search_result_sample.json"
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    print(f"📁 결과 저장: {output_file}")
