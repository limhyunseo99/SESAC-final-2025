# hs_code.py

from typing import List
from uuid import uuid4
import re

from qdrant_client import QdrantClient
from langchain_openai import OpenAIEmbeddings, ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser
from langchain_core.documents import Document


class HSRagPredictor:
    def __init__(
        self,
        qdrant_url: str,
        qdrant_api_key: str,
        collection_name: str,
        embedding_model: str = "text-embedding-3-large",
        llm_model: str = "gpt-5-mini-2025-08-07", # gpt-5-mini-2025-08-07
    ):
        """
        HS 코드 RAG + LLM 예측 클래스
        """

        self.collection_name = collection_name
        self.llm_model = llm_model

        # Qdrant Cloud 연결
        self.qdrant_client = QdrantClient(
            url=qdrant_url,
            api_key=qdrant_api_key,
        )

        # Embedding 모델
        self.embeddings = OpenAIEmbeddings(
            model=embedding_model,
            openai_api_key="")


    # LLM 출력 결과에서 결정세번만 파싱    
    def _llm_hts(self, llm_text: str) -> List[str]:

        pattern = r"결정세번:\s*([0-9]{4}\.[0-9]{2}-[0-9]{4})"
        return re.findall(pattern, llm_text)
    

    # Qdrant 검색 결과 → LLM 컨텍스트 문자열 변환
    def _build_context_from_docs(self, docs: List[Document]) -> str:
        lines = []
        for i, d in enumerate(docs, 1):
            hs_code = d.payload.get("hts_code")
            name = d.payload.get("ptd_name")
            desc = d.payload.get("page_content")

            lines.append(
                f"[사례 {i}]\n"
                f"HS코드: {hs_code}\n"
                f"품명: {name}\n"
                f"물품설명: {desc}\n"
            )

        return "\n".join(lines)
    

    # 신뢰도 점수 구간
    def _confidence_score(self, score: float) -> str:
        if score >= 0.90:
            return "매우 높음"
        elif score >= 0.80:
            return "높음"
        elif score >= 0.70:
            return "중간"
        else: return "낮음"


    # LLM 예측 프롬프트
    def _predict_hts_llm(
        self,
        product_detail: str,
        context: str,
        rule: str,
        temperature: float,
    ) -> str:
        system_prompt = """
#역할과 목표
당신은 수출하는 물건의 HS코드를 결정해주는 능력있는 관세사입니다.
목표는 product_detail을 읽고 한국 HS코드 기준 10자리를 예측하는 것입니다.

#출력 규칙
다음 기준을 지켜주세요:
1. **product_detail의 내용물, 함량, 제조방법 충분히 고려**해야 합니다.
2. **rule과 context를 참고**하여 결과를 도출해야 합니다.
3. rule과 context의 사실과 위배되는 내용을 출력해서는 안됩니다.
4. **rule의 hs_code에 존재하지 않는 결정세번을 출력해서는 안됩니다.**
5. 분석 후, 가장 타당한 HS코드 순서대로 1순위, 2순위, 3순위를 배치하세요.
6. 결정사유는 최대 150자로 작성해주세요.
7. 말투는 -입니다. -습니다. 로 통일해주세요.
8. 일반인이 쉽게 알아들을 수 있도록 **결정사유를 쉬운 단어로 작성**해주세요.

#출력 형식
1순위
결정세번: {{결정세번}} ex) 2202.10-9000
세번설명: {{법령을 근거로 한 해당 결정세번 짧은 설명, 문장이 아닌 단어로 간결하게 표시}}
결정사유: {{결정사유}}
{{해당 결정세번이 1순위로 선정된 이유를 법령 및 유사 사례에 근거하여 설명합니다.
만약 선정된 결정세번이 물품설명과 의미가 상충되어 우려되는 부분이 있다면 추가 설명을 덧붙입니다.}}

2순위
결정세번: {{결정세번}} ex) 2202.10-9000
세번설명: {{법령을 근거로 한 해당 결정세번 짧은 설명, 문장이 아닌 단어로 간결하게 표시}}
결정사유: {{결정사유}}
{{해당 결정세번이 결정된 이유를 법령과 유사 사례에 근거하여 설명합니다.
만약 선정된 결정세번이 물품설명과 의미가 상충되어 우려되는 부분이 있다면 추가 설명을 덧붙입니다. 
또 1순위 결정세번과 분류기준이 어떻게 다른지에 초점을 맞춰 설명합니다.}}

3순위
결정세번: {{결정세번}} ex) 2202.10-9000
세번설명: {{법령을 근거로 한 해당 결정세번 짧은 설명, 문장이 아닌 단어로 간결하게 표시}}
결정사유: {{결정사유}}
{{해당 결정세번이 결정된 이유를 법령과 유사 사례에 근거하여 설명합니다.
만약 선정된 결정세번이 물품설명과 의미가 상충되어 우려되는 부분이 있다면 추가 설명을 덧붙입니다. 
또 1순위, 2순위 결정세번과 분류기준이 어떻게 다른지에 초점을 맞춰 설명합니다.}}

#의사결정 참고자료
아래 상품의 HS 소호를 대답해주세요.
---상품---
{product_detail}

#유사물품분류사례 (사례는 유사도 내림차순): 품목의 설명이 유사한 것에 초점을 맞춰 분석합니다.
---context---
{context}

#HS코드 분류기준 법령
---법령---
{rule}

법령에서 "기타"는 **같은 계층 다른 HS코드 중 그 어느 것에도 해당되지 않는 것**을 "기타"로 분류합니다.
"""

        user_prompt = f"""
아래의 사용자 질의에 작성된 물품설명에 따라 가장 타당한 한국 HS코드 10자리를 출력해주세요.
사용자 질의에는 물품의 재료, 함량, 물품의 제조방식, 물품 용도 등이 적혀있어야 합니다.

--사용자 질의--
{product_detail}
"""

        prompt = ChatPromptTemplate.from_messages([
            ("system", system_prompt),
            ("user", user_prompt)
        ])

        llm = ChatOpenAI(
            model=self.llm_model,
            temperature=temperature,
            openai_api_key=""
            )

        chain = prompt | llm | StrOutputParser()

        return chain.invoke({
            "product_detail": product_detail,
            "context": context,
            "rule": rule
        })

    # 최종 외부 호출용 메인 함수
    def predict(
        self,
        product_detail: str,
        hs_rule_text: str,
        k: int = 5,
        temperature: float = 0.5,
    ) -> str:
        """
        product_detail 넣으면:
        1) Qdrant 검색
        2) context 자동 생성
        3) LLM 예측
        한 번에 실행
        """

        # 쿼리 임베딩 벡터 생성
        query_vec = self.embeddings.embed_query(product_detail)

        # Qdrant 클라이언트로 직접 검색
        search_results = self.qdrant_client.query_points(
            collection_name = self.collection_name,
            query = query_vec,
            limit = k,
            with_payload=True,  # 메타데이터 같이 가져오기
        ).points

        # context 구성
        context = self._build_context_from_docs(search_results)

        # LLM 예측
        response = self._predict_hts_llm(
            product_detail=product_detail,
            context=context,
            rule=hs_rule_text,
            temperature=temperature,
        )

        return response