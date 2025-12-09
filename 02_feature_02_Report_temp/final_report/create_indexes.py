# create_indexes.py
# Qdrant 컬렉션에 필터용 인덱스 생성
# Qdrant 인덱스 이미 생성했으면 삭제
import logging
from qdrant_client import QdrantClient
from qdrant_client.http import models as qmodels
from config import Config

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def create_indexes():
    """Qdrant 컬렉션에 필터링용 인덱스 생성"""
    
    client = QdrantClient(
        url=Config.QDRANT_URL,
        api_key=Config.QDRANT_API_KEY,
        timeout=120
    )
    
    collection_name = Config.QDRANT_COLLECTION_REPORT
    
    print("=" * 60)
    print("Qdrant 인덱스 생성")
    print("=" * 60)
    print()
    
    # 1. country_code 인덱스
    print("📌 country_code 인덱스 생성 중...")
    try:
        client.create_payload_index(
            collection_name=collection_name,
            field_name="country_code",
            field_schema=qmodels.PayloadSchemaType.KEYWORD
        )
        print("✅ country_code 인덱스 생성 완료")
    except Exception as e:
        if "already exists" in str(e).lower():
            print("✓ country_code 인덱스 이미 존재")
        else:
            print(f"❌ country_code 인덱스 생성 실패: {e}")
    
    print()
    
    # 2. source 인덱스
    print("📌 source 인덱스 생성 중...")
    try:
        client.create_payload_index(
            collection_name=collection_name,
            field_name="source",
            field_schema=qmodels.PayloadSchemaType.KEYWORD
        )
        print("✅ source 인덱스 생성 완료")
    except Exception as e:
        if "already exists" in str(e).lower():
            print("✓ source 인덱스 이미 존재")
        else:
            print(f"❌ source 인덱스 생성 실패: {e}")
    
    print()
    
    # 3. type 인덱스
    print("📌 type 인덱스 생성 중...")
    try:
        client.create_payload_index(
            collection_name=collection_name,
            field_name="type",
            field_schema=qmodels.PayloadSchemaType.KEYWORD
        )
        print("✅ type 인덱스 생성 완료")
    except Exception as e:
        if "already exists" in str(e).lower():
            print("✓ type 인덱스 이미 존재")
        else:
            print(f"❌ type 인덱스 생성 실패: {e}")
    
    print()
    
    # 4. year 인덱스 (선택사항)
    print("📌 year 인덱스 생성 중...")
    try:
        client.create_payload_index(
            collection_name=collection_name,
            field_name="year",
            field_schema=qmodels.PayloadSchemaType.INTEGER
        )
        print("✅ year 인덱스 생성 완료")
    except Exception as e:
        if "already exists" in str(e).lower():
            print("✓ year 인덱스 이미 존재")
        else:
            print(f"❌ year 인덱스 생성 실패: {e}")
    
    print()
    print("=" * 60)
    print("✅ 인덱스 생성 완료!")
    print("=" * 60)
    print()
    print("이제 test_vectordb.py를 다시 실행해보세요:")
    print("  python test_vectordb.py")
    print()

if __name__ == "__main__":
    create_indexes()