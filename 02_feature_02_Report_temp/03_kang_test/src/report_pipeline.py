# report_pipeline.py
"""
보고서 생성 전체 파이프라인
- VectorDB 기반 RAG 검색
- Deep Research 웹 최신 정보 검색
- Draft 생성 → Deep Research 반영 → 최종 보고서 조립
- PDF / TXT 파일 출력까지 수행
"""

import os
from vectordb_manager import VectorDBManager
from data_loader import DataLoader
from integrated_search import IntegratedSearchEngine
from deep_research import DeepResearchEngine
from report_generator import ReportGenerator
from pdf_exporter import export_to_pdf


def run_pipeline(user_input=None):
    """전체 보고서 생성 파이프라인"""
    print("\n=== Report Generation Pipeline Start ===\n")

    # 기본 입력값 설정
    if user_input is None:
        user_input = {
            "country": "Japan",
            "hs_code": "2008190000",
            "extra_analysis": ["시장 리스크", "가격 추세"],
            "sns_keyword": "바나나우유",
        }

    # VectorDB 로드 및 RAG 검색 준비
    vectordb = VectorDBManager(persist_dir="vectordb_store")
    vectordb.load_vectorstore()

    loader = DataLoader()
    search_engine = IntegratedSearchEngine(vectordb, loader)

    print("Step 1: Running integrated RAG search...")
    result = search_engine.search_all(user_input)

    # result 예시 구조:
    # {
    #   "request_info": {...},
    #   "country_background": {...},
    #   "sections": {...},
    #   "table_image_hint": {...}
    # }

    print("Step 2: Running Deep Research...")
    dr = DeepResearchEngine()
    dr_result = dr.run_all_research(
        country=result["request_info"]["country_name"],
        product=result["request_info"].get("product_name", "Processed Nuts"),
        hs_code=result["request_info"]["hs_code"],
        extra=result["request_info"]["extra_analysis"],
        country_code=result["request_info"]["country_code"],
    )

    print("Step 3: Generating report draft...")
    rg = ReportGenerator()
    draft = rg.generate_draft_with_rag(
        country_info=result["country_background"],
        sections=result["sections"],
        table_image_hint=result.get("table_image_hint", {}),
        request_info=result["request_info"],
    )

    print("Step 4: Integrating Deep Research...")
    updated = rg.integrate_deep_research(draft, dr_result)

    print("Step 5: Final assembly...")
    final_report, validation = rg.assemble_final_report(
        updated, result["request_info"]
    )

    # Executive Summary 검증 실패 시 재생성
    if not validation["passed"] and validation["score"] < 60:
        print("Validation failed — regenerating Executive Summary...")
        final_report = rg.regenerate_with_feedback(
            final_report, validation, result["request_info"]
        )

    # 출력 폴더 생성
    os.makedirs("output", exist_ok=True)

    # TXT 저장
    with open("output/final_report.txt", "w", encoding="utf-8") as f:
        f.write(final_report)

    # PDF 저장
    try:
        export_to_pdf(final_report, "output/final_report.pdf", result["request_info"])
    except Exception as e:
        print("PDF failed:", e)

    print("\n=== Report Generation Complete ===\n")

    return final_report, validation
