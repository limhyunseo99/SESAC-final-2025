from pathlib import Path
from dotenv import load_dotenv
import os
import sys

load_dotenv()

# 프로젝트 최상위 경로
BASE_DIR = Path(__file__).resolve().parent.parent

def hs_main(product_detail: str):

    QDRANT_URL = os.getenv("QDRANT_URL")
    QDRANT_API_KEY = os.getenv("QDRANT_API_KEY")

    # 🔥 규칙 파일의 정확한 경로
    rule_path = BASE_DIR / "data" / "hts_code" / "hs_rule_text.txt"

    if not rule_path.exists():
        raise FileNotFoundError(f"규칙 파일을 찾을 수 없음: {rule_path}")

    with open(rule_path, "r", encoding="utf-8") as f:
        HS_RULE_TEXT = f.read()

    from modules.hts_code import HSRagPredictor
    from modules.json_parser import parse_llm_hs_result

    predictor = HSRagPredictor(
        qdrant_url=QDRANT_URL,
        collection_name="hts_case_all",
        qdrant_api_key=QDRANT_API_KEY
    )

    result = predictor.predict(
        product_detail=product_detail,
        hs_rule_text=HS_RULE_TEXT,
        k=5,
        temperature=0.0,
    )

    return parse_llm_hs_result(result)
