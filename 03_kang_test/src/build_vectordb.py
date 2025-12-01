"""
VectorDB 구축 스크립트 (절대경로 기반 안정화 버전)
- 모든 PDF 및 JSON을 로드
- 청킹 후 VectorDB에 저장
"""

import os
from dotenv import load_dotenv

from data_loader import DataLoader
from vectordb_manager import VectorDBManager

# .env 파일 로드
load_dotenv()

# -------------------------------------------------------------------
# 1. 절대경로 설정
# -------------------------------------------------------------------
# build_vectordb.py 파일 기준으로 상위 폴더(프로젝트 루트)를 자동 탐지
BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))

DATA_DIR = os.path.join(BASE_DIR, "data")
KATI_DIR = os.path.join(DATA_DIR, "kati")
KOTRA_DIR = os.path.join(DATA_DIR, "kotra")
COUNTRY_INFO_DIR = os.path.join(DATA_DIR, "country_info")


def build_vectordb():
    """
    VectorDB 구축 메인 작업
    """
    print("\n======================================================================")
    print("VectorDB 구축 시작")
    print("======================================================================\n")

    if not os.getenv("OPENAI_API_KEY"):
        print("오류: OPENAI_API_KEY가 설정되지 않았습니다.")
        print(".env 파일에 키를 추가해 주세요.\n")
        return

    loader = DataLoader()
    db_manager = VectorDBManager(persist_dir=os.path.join(BASE_DIR, "vectordb_store"))

    all_documents = []

    # -------------------------------------------------------------------
    # Step 1: KATI PDF 로드
    # -------------------------------------------------------------------
    print("------------------------------------------------------------------")
    print("Step 1: KATI PDF 로드")
    print("------------------------------------------------------------------")

    kati_docs = loader.process_all_pdfs(KATI_DIR)
    all_documents.extend(kati_docs)
    print(f"KATI 문서 수: {len(kati_docs)}\n")

    # -------------------------------------------------------------------
    # Step 2: KOTRA PDF 로드
    # -------------------------------------------------------------------
    print("------------------------------------------------------------------")
    print("Step 2: KOTRA PDF 로드")
    print("------------------------------------------------------------------")

    kotra_docs = loader.process_all_pdfs(KOTRA_DIR)
    all_documents.extend(kotra_docs)
    print(f"KOTRA 문서 수: {len(kotra_docs)}\n")

    # -------------------------------------------------------------------
    # Step 3: 국가정보 JSON 로드
    # -------------------------------------------------------------------
    print("------------------------------------------------------------------")
    print("Step 3: 국가정보 JSON 로드")
    print("------------------------------------------------------------------")

    country_codes = ["JP", "US", "VN"]
    for code in country_codes:
        docs = loader.process_country_info(code)
        all_documents.extend(docs)

    country_info_count = len(
        [d for d in all_documents if d.metadata.get("source") == "COUNTRY_INFO"]
    )
    print(f"국가정보 JSON 문서 수: {country_info_count}\n")

    # -------------------------------------------------------------------
    # Step 4: 통계 출력
    # -------------------------------------------------------------------
    print("------------------------------------------------------------------")
    print("Step 4: 문서 통계")
    print("------------------------------------------------------------------")

    stats = {"KATI": 0, "KOTRA": 0, "COUNTRY_INFO": 0}

    for doc in all_documents:
        src = doc.metadata.get("source")
        if src in stats:
            stats[src] += 1

    print(f"KATI: {stats['KATI']:,}개")
    print(f"KOTRA: {stats['KOTRA']:,}개")
    print(f"COUNTRY_INFO: {stats['COUNTRY_INFO']:,}개")
    print(f"총 문서 수: {len(all_documents):,}개\n")

    # -------------------------------------------------------------------
    # Step 5: VectorDB 저장
    # -------------------------------------------------------------------
    print("------------------------------------------------------------------")
    print("Step 5: VectorDB 생성 및 저장")
    print("------------------------------------------------------------------")

    try:
        db_manager.insert_documents(all_documents)
        db_manager.save_vectorstore()
        print("VectorDB 저장 완료\n")
    except Exception as e:
        print(f"VectorDB 생성 중 오류 발생: {e}")
        import traceback

        traceback.print_exc()
        return

    # -------------------------------------------------------------------
    # Step 6: 테스트 검색
    # -------------------------------------------------------------------
    print("------------------------------------------------------------------")
    print("Step 6: 테스트 검색")
    print("------------------------------------------------------------------")

    from vectordb_manager import SearchEngine

    search_engine = SearchEngine(db_manager)

    query = "일본 시장 규모 트렌드"

    print(f"테스트 쿼리: {query}")
    results = search_engine.db.similarity_search(
        query=query, k=3, filter={"country_code": "JP"}
    )

    if results:
        print(f"검색 결과 {len(results)}개 발견\n")
        for i, doc in enumerate(results, 1):
            print(f"[결과 {i}]")
            print(f"출처: {doc.metadata.get('source')}")
            print(f"국가: {doc.metadata.get('country_code')}")
            print(f"연도: {doc.metadata.get('year', 'N/A')}")
            print(f"파일명: {doc.metadata.get('file_name')}")
            print(doc.page_content[:150], "...\n")
    else:
        print("검색 결과 없음\n")

    print("======================================================================")
    print("VectorDB 구축 완료")
    print(f"저장 위치: {db_manager.persist_dir}")
    print("======================================================================\n")


if __name__ == "__main__":
    build_vectordb()
