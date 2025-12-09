# init_db.py
# 벡터 DB 초기화 전용 스크립트
# 벡터 DB 이미 구축했으면 삭제
import logging
from pipeline import init_vectorstore
from vectorstore import QdrantVectorDB

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)

if __name__ == "__main__":
    print("=" * 60)
    print("벡터 DB 재구축")
    print("=" * 60)
    print()
    
    # 기존 컬렉션 삭제
    try:
        print("⚠️  기존 컬렉션 삭제 중...")
        db = QdrantVectorDB()
        db.client.delete_collection("REPORT")
        print("✓ 삭제 완료")
        print()
    except Exception as e:
        print(f"삭제 실패 (무시하고 진행): {e}")
        print()
    
    # 재구축
    print("새로운 데이터로 벡터 DB 구축 중...")
    print()
    
    try:
        db = init_vectorstore()
        print()
        print("=" * 60)
        print("✅ 벡터 DB 재구축 완료!")
        print("=" * 60)
        print()
        
        # 통계 출력
        info = db.get_collection_info()
        print(f"📊 총 문서 수: {info.get('vectors_count', 0)}개")
        print()
        
    except Exception as e:
        print()
        print("=" * 60)
        print("❌ 재구축 실패")
        print("=" * 60)
        print(f"에러: {e}")
        print()