# report_pipeline.py
import os
import json

from vectordb_manager import VectorDBManager
from data_loader import DataLoader
from integrated_search import IntegratedSearchEngine
from deep_research import DeepResearchEngine
from report_generator import ReportGenerator


BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
VECTORDB_DIR = os.path.join(BASE_DIR, "vectordb_store")
OUTPUT_DIR = os.path.join(BASE_DIR, "output")


def run_pipeline():
    print("\n==============================")
    print("Report Generation Pipeline Start")
    print("==============================\n")

    # -------------------------------------------------------
    # 1) VectorDB 로드
    # -------------------------------------------------------
    vectordb = VectorDBManager(persist_dir=VECTORDB_DIR)
    vectordb.load_vectorstore()

    loader = DataLoader()
    search_engine = IntegratedSearchEngine(vectordb, loader)

    # -------------------------------------------------------
    # 2) 테스트 사용자 입력값
    # -------------------------------------------------------
    user_input = {
        "country": "일본",
        "hs_code": "2008190000",
        "extra_analysis": ["시장 리스크", "가격 추세"],
        "sns_keyword": "견과류 수요",
    }

    # -------------------------------------------------------
    # 3) 통합 검색 실행
    # -------------------------------------------------------
    result = search_engine.search_all(user_input)

    # -------------------------------------------------------
    # 4) Deep Research 실행
    # -------------------------------------------------------
    dr = DeepResearchEngine()
    dr_result = dr.run_all_research(
        country=result["request_info"]["country_name"],
        product_name="견과류 조제품",
        hs_code=result["request_info"]["hs_code"],
        extra_analysis=result["request_info"]["extra_analysis"],
    )

    # -------------------------------------------------------
    # 5) 보고서 생성
    # -------------------------------------------------------
    rg = ReportGenerator()

    initial = rg.generate_initial_draft(
        result["country_background"], result["request_info"]
    )

    enhanced = rg.enhance_with_documents(
        initial, result["sections"], result["table_image_hint"]
    )

    deep_added = rg.integrate_deep_research(enhanced, dr_result)

    final = rg.assemble_final_report(deep_added, result["request_info"])

    # -------------------------------------------------------
    # 6) 결과 저장
    # -------------------------------------------------------
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    out_path = os.path.join(OUTPUT_DIR, "final_report.txt")

    with open(out_path, "w", encoding="utf-8") as f:
        f.write(final)

    print("\n==============================")
    print("Report Generated Successfully")
    print(f"Location: {out_path}")
    print("==============================\n")

    return final


if __name__ == "__main__":
    run_pipeline()
