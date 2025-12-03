from hts_code import HSRagPredictor
from json_parser import parse_llm_hs_result

def hs_main(product_detail: str):
    QDRANT_URL = "https://933ad41b-bc00-4b42-a9b6-da3f661283ce.us-west-2-0.aws.cloud.qdrant.io:6333"
    QDRANT_API_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJhY2Nlc3MiOiJtIn0.W0VJE7ks-1kOeFbvUXwiGzpYt79HsSxMZNN4Cz-5JH4"

    # 예측기 생성
    predictor = HSRagPredictor(
        qdrant_url=QDRANT_URL,
        qdrant_api_key=QDRANT_API_KEY,
        collection_name="hts_case_all",
    )

    # HS 규칙 로드
    with open("hs_rule_text.txt", "r", encoding="utf-8") as f:
        HS_RULE_TEXT = f.read()

    # 예측 실행
    result = predictor.predict(
        product_detail=product_detail,
        hs_rule_text=HS_RULE_TEXT,
        k=5,
        temperature=0.0,
    )
    fianl_result = parse_llm_hs_result(result)

    return fianl_result