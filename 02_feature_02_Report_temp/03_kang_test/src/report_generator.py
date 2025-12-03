# report_generator.py
import json
from langchain_openai import ChatOpenAI


class ReportGenerator:
    def __init__(self, model="gpt-4o-mini"):
        self.llm = ChatOpenAI(model=model, temperature=0)

    # -----------------------------------------------------
    # 1) 국가정보 기반 초안 생성
    # -----------------------------------------------------
    def generate_initial_draft(self, country_info: dict, request_info: dict) -> str:
        """
        국가정보 JSON(country_background)을 기반으로
        보고서 초안을 생성하는 단계.
        """

        prompt = f"""
당신은 국가별 수출 전략 보고서를 작성하는 전문 분석가입니다.

다음은 해당 국가의 공식 국가정보 데이터(JSON)입니다:

{json.dumps(country_info, ensure_ascii=False, indent=2)}

사용자 요청 정보는 다음과 같습니다:

{json.dumps(request_info, ensure_ascii=False, indent=2)}

위 데이터를 기반으로 다음 항목을 포함한 '초안 보고서'를 작성하세요:

1. 국가 개요
2. 식품 시장 규모 & 성장 흐름
3. 수입 구조 및 한국과의 교역 현황
4. 소비자 성향 / 식문화 핵심 특징
5. FTA·관세·수입규제 관련 기본 정보
6. 분석 대상 품목(HS 코드)과 연관된 시장 적합성 평가

아직 KATI·KOTRA 문서나 최신 Deep Research 정보는 반영하지 마세요.
"""

        result = self.llm.invoke(prompt)
        return result.content.strip()

    # -----------------------------------------------------
    # 2) RAG(KATI/KOTRA/국가정보) 기반 보정 섹션 생성
    # -----------------------------------------------------
    def enhance_with_documents(
        self, draft: str, sections: dict, table_image_hint: dict
    ) -> str:
        """
        VectorDB 검색 결과(KATI/KOTRA 등)를 기반으로
        초안을 보정하여 세부 시장 분석을 추가한다.
        """

        prompt = f"""
아래는 현재 보고서 초안입니다:

{draft}

다음은 RAG(VectorDB 검색) 결과입니다.
각 섹션에는 문서 내용과 메타데이터가 포함됩니다:

{json.dumps(sections, ensure_ascii=False, indent=2)}

표·이미지 페이지 정보는 다음과 같습니다:

{json.dumps(table_image_hint, ensure_ascii=False, indent=2)}

요청:
- 초안에 RAG 결과의 수치·그래프·통계·시장 분석 내용을 반영하여 품질을 높여라.
- 표/이미지 페이지 번호도 참고하여 “근거가 있는 문장”을 작성해라.
- 중복 없이 자연스럽게 서술하라.
"""

        result = self.llm.invoke(prompt)
        return result.content.strip()

    # -----------------------------------------------------
    # 3) Deep Research 반영 (최신 정보 덮어쓰기)
    # -----------------------------------------------------
    def integrate_deep_research(self, draft: str, deep_result: dict) -> str:
        """
        최신 규제/위험/가격 동향을 보고서 본문에 반영.
        """

        prompt = f"""
다음은 현재까지 보정된 보고서 본문입니다:

{draft}

그리고 다음은 Deep Research 검색 결과입니다:

{json.dumps(deep_result, ensure_ascii=False, indent=2)}

요청:
- 초안에 최신 규제/가격 추세/시장 리스크 정보를 자연스럽게 추가하라.
- "최신 발표", "2025년 기준"과 같은 최신성을 나타내는 문장으로 보완하라.
"""

        result = self.llm.invoke(prompt)
        return result.content.strip()

    # -----------------------------------------------------
    # 4) 최종 보고서 조립
    # -----------------------------------------------------
    def assemble_final_report(self, final_text: str, request_info: dict) -> str:
        """
        최종적으로 통일된 형식의 보고서로 정리한다.
        """

        hs = request_info["hs_code"]
        country = request_info["country_name"]

        prompt = f"""
다음 내용을 기반으로 최종 보고서를 완성하세요:

{final_text}

요구되는 최종 보고서 구성은 다음과 같다:

1. 요약(Executive Summary)
2. 국가 및 시장 개요
3. 분석 대상 품목(HS {hs}) 적합성 평가
4. 시장 규모 · 성장 전망
5. 유통구조 & 주요 경쟁국
6. 규제 및 인증 요건
7. 가격 추세
8. 시장 리스크
9. 전략 제언

국가명: {country}

보고서를 잘 정리된 단일 문서 형태로 출력하세요.
"""

        result = self.llm.invoke(prompt)
        return result.content.strip()
