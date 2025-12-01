"""
VectorDB 구축 및 테스트 스크립트
오늘 밤 23:00에 실행할 최종 통합 스크립트
"""

import os
from dotenv import load_dotenv

# 환경변수 로드
load_dotenv()

from data_loader import DataLoader
from vectordb_manager import VectorDBManager
from search_engine import IntegratedSearchEngine


def build_vectordb(clear_existing: bool = True):
    """VectorDB 구축"""

    print("\n" + "=" * 60)
    print("🚀 VectorDB 구축 시작")
    print("=" * 60 + "\n")

    # 1. 데이터 로더 초기화
    loader = DataLoader(data_dir="data")

    # 2. PDF 로드
    print("📚 Step 1: PDF 파일 로드 중...\n")
    kati_docs = loader.load_kati_pdfs()
    kotra_docs = loader.load_kotra_pdfs()

    # 3. 청크 분할
    print("✂️  Step 2: 문서 분할 중...\n")
    kati_chunks = loader.chunk_documents(kati_docs, chunk_size=1000, chunk_overlap=200)
    kotra_chunks = loader.chunk_documents(
        kotra_docs, chunk_size=1000, chunk_overlap=200
    )

    all_chunks = kati_chunks + kotra_chunks

    print(f"📊 총 청크 수: {len(all_chunks)}개")
    print(f"   - KATI: {len(kati_chunks)}개")
    print(f"   - KOTRA: {len(kotra_chunks)}개\n")

    # 4. VectorDB 생성
    print("💾 Step 3: VectorDB 생성 중...\n")
    db_manager = VectorDBManager(
        persist_directory="vectordb", collection_name="market_reports"
    )

    vectorstore = db_manager.create_vectorstore(
        documents=all_chunks, clear_existing=clear_existing
    )

    # 5. 통계 확인
    stats = db_manager.get_stats()
    print("📊 VectorDB 통계:")
    print(f"   - 총 문서: {stats['total_documents']}개")
    print(f"   - 저장 위치: {stats['persist_directory']}")
    print(f"   - 컬렉션: {stats['collection_name']}\n")

    print("=" * 60)
    print("✅ VectorDB 구축 완료!")
    print("=" * 60 + "\n")

    return db_manager


def test_search(db_manager: VectorDBManager):
    """검색 테스트"""

    print("\n" + "=" * 60)
    print("🧪 검색 테스트 시작")
    print("=" * 60 + "\n")

    # 데이터 로더
    loader = DataLoader()

    # 통합 검색 엔진
    search_engine = IntegratedSearchEngine(db_manager, loader)

    # 테스트 케이스들
    test_cases = [
        {
            "country": "일본",
            "hs_code": "2008190000",
            "extra_analysis": ["시장 리스크", "규제 검토"],
            "sns_keyword": "과일",
        },
        # 추가 테스트 케이스
        # {
        #     "country": "미국",
        #     "hs_code": "0810200000",
        #     "extra_analysis": ["가격 추세"],
        #     "sns_keyword": None
        # }
    ]

    for i, test_input in enumerate(test_cases, 1):
        print(f"\n📝 테스트 케이스 {i}")
        print(f"   국가: {test_input['country']}")
        print(f"   HS CODE: {test_input['hs_code']}")

        # 검색 실행
        result = search_engine.search_all(test_input)

        # 결과 저장
        import json

        output_file = f"output/test_result_{i}.json"
        os.makedirs("output", exist_ok=True)

        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=2)

        print(f"   💾 결과 저장: {output_file}")

        # 간단한 결과 요약
        print(f"\n   📊 검색 결과 요약:")
        for section, docs in result["sections"].items():
            print(f"      {section}: {len(docs)}개 문서")

    print("\n" + "=" * 60)
    print("✅ 검색 테스트 완료!")
    print("=" * 60 + "\n")


def main():
    """메인 실행 함수"""

    # API 키 확인
    if not os.getenv("OPENAI_API_KEY"):
        print("❌ OPENAI_API_KEY가 설정되지 않았습니다!")
        print("   .env 파일에 OPENAI_API_KEY를 추가해주세요.")
        return

    try:
        # 1. VectorDB 구축
        db_manager = build_vectordb(clear_existing=True)

        # 2. 검색 테스트
        test_search(db_manager)

        print("\n🎉 모든 작업 완료!")
        print("   - VectorDB가 'vectordb/' 폴더에 저장되었습니다")
        print("   - 테스트 결과가 'output/' 폴더에 저장되었습니다")
        print("   - 이제 동료에게 'output/test_result_1.json'을 전달하세요!")

    except Exception as e:
        print(f"\n❌ 에러 발생: {e}")
        import traceback

        traceback.print_exc()


if __name__ == "__main__":
    main()
