import os
import logging
from core import VectorDB, DataLoader, Config
from research import RAGSearch, DeepResearch
from generator import ReportGenerator

logger = logging.getLogger(__name__)


# -----------------------------------------------------------
# 벡터스토어 존재 여부 검사
# -----------------------------------------------------------
def is_vectordb_built(persist_dir: str) -> bool:
    if not os.path.exists(persist_dir):
        return False
    files = os.listdir(persist_dir)
    return any(fname.startswith("chroma") for fname in files)


# -----------------------------------------------------------
# 벡터스토어 자동 구축 함수
# -----------------------------------------------------------
def build_vectorstore_if_needed():
    persist_dir = Config.VECTORDB_DIR

    if is_vectordb_built(persist_dir):
        logger.info("VectorDB 이미 구축되어 있어 로딩만 진행합니다.")
        return

    logger.warning("VectorDB가 비어 있습니다. 데이터 임베딩을 시작합니다.")

    vectordb = VectorDB()
    vectordb.load()

    # 1. 국가정보 JSON 임베딩
    for country_code in Config.COUNTRY_MAP.values():
        docs = DataLoader.process_country_json(country_code)
        vectordb.insert(docs)
        logger.info(f"국가정보({country_code}) 임베딩 완료: {len(docs)}개")

    # 2. KATI/KOTRA PDF 임베딩
    pdf_dirs = [
        os.path.join(Config.DATA_DIR, "kati"),
        os.path.join(Config.DATA_DIR, "kotra"),
    ]

    total_pdf_docs = 0
    for folder in pdf_dirs:
        if os.path.exists(folder):
            docs = DataLoader.process_all_pdfs(folder)
            vectordb.insert(docs)
            total_pdf_docs += len(docs)
            logger.info(f"{folder} 임베딩 완료: {len(docs)}개")

    vectordb.save()
    logger.info(f"VectorDB 구축 완료. 총 문서 수: {total_pdf_docs}")


# -----------------------------------------------------------
# 전체 파이프라인 실행 함수
# -----------------------------------------------------------
def run_pipeline(user_input=None):
    logger.info("=== Report Generation Pipeline Start ===")

    # 0) 벡터스토어 자동 구축 (필수)
    build_vectorstore_if_needed()

    # 1) 사용자 입력
    if user_input is None:
        user_input = {
            "country": "일본",
            "hs_code": "0402999000",
            "item": "바나나우유",
            "extra_analysis": [
                "시장 리스크",
                "가격 추세",
                "규제 검토",
                "수요 전망",
            ],
        }

    logger.info(f"사용자 입력: {user_input}")

    # 2) VectorDB 로드
    vectordb = VectorDB()
    vectordb.load()

    # 3) RAG
    rag_search = RAGSearch(vectordb)
    rag_result = rag_search.search(
        country=user_input["country"],
        hs_code=user_input["hs_code"],
        extra=user_input.get("extra_analysis", []),
    )

    # 4) Deep Research
    deep_research = DeepResearch()
    deep_result = deep_research.run(
        country=user_input["country"],
        product=user_input.get("item", "제품"),
        hs_code=user_input["hs_code"],
        extra=user_input.get("extra_analysis", []),
    )
    # 5) Draft → 통합 → Finalize
    generator = ReportGenerator()
    generator.set_rag_sources(rag_result)

    draft = generator.generate_draft(
        rag_result=rag_result,
        request=user_input
    )

    updated = generator.integrate_deep_research(
        draft=draft,
        deep_result=deep_result
    )

    final_report, validation = generator.finalize(
        draft=updated,
        request=user_input
    )

    # 6) 출력 저장
    os.makedirs("output", exist_ok=True)
    text_path = "output/final_report.txt"
    with open(text_path, "w", encoding="utf-8") as f:
        f.write(final_report)

    pdf_path = "output/final_report.pdf"
    generator.export_pdf(
        markdown_text=final_report,
        output_path=pdf_path,
        metadata={
            "country": user_input["country"],
            "hs_code": user_input["hs_code"],
            "item": user_input.get("item", "제품"),
        },
    )

    logger.info("=== Report Generation Completed ===")
    logger.info(f"PDF: {pdf_path}")
    logger.info(f"TXT: {text_path}")
    logger.info(f"Executive Summary 점수: {validation.get('score', 0)}")

    return final_report, validation


# -----------------------------------------------------------
# 실행
# -----------------------------------------------------------
if __name__ == "__main__":
    run_pipeline()
