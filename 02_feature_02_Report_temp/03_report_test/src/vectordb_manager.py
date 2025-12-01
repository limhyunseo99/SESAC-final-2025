"""
VectorDB (Chroma) 관리 모듈
"""

import os
from typing import List, Dict, Optional
from pathlib import Path

from langchain_openai import OpenAIEmbeddings
from langchain_community.vectorstores import Chroma
from langchain.schema import Document


class VectorDBManager:
    """VectorDB 생성 및 검색 관리 클래스"""

    def __init__(
        self,
        persist_directory: str = "vectordb",
        collection_name: str = "market_reports",
    ):
        """
        Args:
            persist_directory: VectorDB 저장 경로
            collection_name: 컬렉션 이름
        """
        self.persist_directory = Path(persist_directory)
        self.persist_directory.mkdir(exist_ok=True)

        self.collection_name = collection_name

        # OpenAI Embeddings 초기화
        self.embeddings = OpenAIEmbeddings(
            model="text-embedding-3-small"  # 비용 효율적
        )

        self.vectorstore = None

    def create_vectorstore(
        self, documents: List[Document], clear_existing: bool = False
    ) -> Chroma:
        """
        VectorDB 생성

        Args:
            documents: 저장할 문서들
            clear_existing: 기존 DB 삭제 여부

        Returns:
            Chroma: VectorDB 인스턴스
        """
        if clear_existing and self.persist_directory.exists():
            print("🗑️  기존 VectorDB 삭제 중...")
            import shutil

            shutil.rmtree(self.persist_directory)
            self.persist_directory.mkdir(exist_ok=True)

        print(f"📦 VectorDB 생성 중... (문서 {len(documents)}개)")
        print(f"   저장 경로: {self.persist_directory}")

        self.vectorstore = Chroma.from_documents(
            documents=documents,
            embedding=self.embeddings,
            collection_name=self.collection_name,
            persist_directory=str(self.persist_directory),
        )

        print(f"✅ VectorDB 생성 완료!\n")
        return self.vectorstore

    def load_vectorstore(self) -> Chroma:
        """기존 VectorDB 로드"""
        if not self.persist_directory.exists():
            raise FileNotFoundError(
                f"VectorDB가 존재하지 않습니다: {self.persist_directory}"
            )

        print(f"📂 VectorDB 로드 중: {self.persist_directory}")

        self.vectorstore = Chroma(
            collection_name=self.collection_name,
            embedding_function=self.embeddings,
            persist_directory=str(self.persist_directory),
        )

        print(f"✅ VectorDB 로드 완료\n")
        return self.vectorstore

    def search(
        self, query: str, k: int = 10, filter_dict: Optional[Dict] = None
    ) -> List[Document]:
        """
        유사도 검색

        Args:
            query: 검색 쿼리
            k: 반환할 문서 수
            filter_dict: 메타데이터 필터
                예: {"source": "KATI", "country": "일본"}

        Returns:
            List[Document]: 검색된 문서들
        """
        if self.vectorstore is None:
            self.load_vectorstore()

        # 필터가 있으면 적용
        if filter_dict:
            results = self.vectorstore.similarity_search(
                query=query, k=k, filter=filter_dict
            )
        else:
            results = self.vectorstore.similarity_search(query=query, k=k)

        return results

    def search_with_scores(
        self, query: str, k: int = 10, filter_dict: Optional[Dict] = None
    ) -> List[tuple]:
        """
        유사도 검색 (점수 포함)

        Returns:
            List[tuple]: (Document, score) 튜플 리스트
        """
        if self.vectorstore is None:
            self.load_vectorstore()

        if filter_dict:
            results = self.vectorstore.similarity_search_with_score(
                query=query, k=k, filter=filter_dict
            )
        else:
            results = self.vectorstore.similarity_search_with_score(query=query, k=k)

        return results

    def get_stats(self) -> Dict:
        """VectorDB 통계 정보"""
        if self.vectorstore is None:
            self.load_vectorstore()

        # Chroma에서 전체 문서 수 조회
        collection = self.vectorstore._collection

        stats = {
            "total_documents": collection.count(),
            "collection_name": self.collection_name,
            "persist_directory": str(self.persist_directory),
        }

        return stats


class SearchEngine:
    """검색 엔진 - 섹션별 검색 관리"""

    def __init__(self, vectordb_manager: VectorDBManager):
        self.db = vectordb_manager

    def search_by_section(
        self,
        query: str,
        section_type: str,
        country: str,
        hs_code_prefix: str,
        k: int = 5,
    ) -> List[Document]:
        """
        섹션별 검색

        Args:
            query: 검색 쿼리
            section_type: "market" | "regulation" | "distribution" | "strategy"
            country: 국가명
            hs_code_prefix: HS CODE 앞 4자리
            k: 반환할 문서 수

        Returns:
            List[Document]: 검색 결과
        """
        # 섹션별 소스 우선순위
        section_sources = {
            "market": ["KATI"],
            "regulation": ["KATI"],
            "distribution": ["KATI"],
            "strategy": ["KOTRA"],
            "risk": ["KOTRA"],
        }

        results = []
        sources = section_sources.get(section_type, ["KATI", "KOTRA"])

        for source in sources:
            filter_dict = {"source": source, "country": country}

            # 해당 소스에서 검색
            docs = self.db.search(query=query, k=k, filter_dict=filter_dict)

            # 섹션 타입 메타데이터 추가
            for doc in docs:
                doc.metadata["section_type"] = section_type

            results.extend(docs)

        return results[:k]  # 최대 k개만 반환

    def search_all_sections(
        self,
        queries: Dict[str, str],
        country: str,
        hs_code: str,
        k_per_section: int = 5,
    ) -> Dict[str, List[Document]]:
        """
        모든 섹션에 대해 검색

        Args:
            queries: 섹션별 쿼리 딕셔너리
                예: {"market": "일본 견과류 시장", "regulation": "..."}
            country: 국가명
            hs_code: HS CODE (10자리)
            k_per_section: 섹션당 문서 수

        Returns:
            Dict[str, List[Document]]: 섹션별 검색 결과
        """
        hs_prefix = hs_code[:4]
        results = {}

        for section_type, query in queries.items():
            print(f"🔍 {section_type} 섹션 검색 중...")

            docs = self.search_by_section(
                query=query,
                section_type=section_type,
                country=country,
                hs_code_prefix=hs_prefix,
                k=k_per_section,
            )

            results[section_type] = docs
            print(f"   ✅ {len(docs)}개 문서 검색 완료")

        return results


# 테스트 코드
if __name__ == "__main__":
    from data_loader import DataLoader

    # 1. 데이터 로드
    loader = DataLoader()
    kati_docs = loader.load_kati_pdfs()
    kotra_docs = loader.load_kotra_pdfs()

    # 2. 청크 분할
    kati_chunks = loader.chunk_documents(kati_docs)
    kotra_chunks = loader.chunk_documents(kotra_docs)

    all_chunks = kati_chunks + kotra_chunks

    # 3. VectorDB 생성
    db_manager = VectorDBManager()
    db_manager.create_vectorstore(all_chunks, clear_existing=True)

    # 4. 통계 확인
    stats = db_manager.get_stats()
    print(f"\n📊 VectorDB 통계:")
    print(f"   총 문서: {stats['total_documents']}개")

    # 5. 검색 테스트
    search_engine = SearchEngine(db_manager)

    test_query = "일본 식품 시장 규모"
    results = search_engine.search_by_section(
        query=test_query,
        section_type="market",
        country="일본",
        hs_code_prefix="2008",
        k=3,
    )

    print(f"\n🔍 검색 테스트: '{test_query}'")
    for i, doc in enumerate(results, 1):
        print(
            f"\n{i}. [{doc.metadata['source']}] {doc.metadata.get('file_name', 'N/A')}"
        )
        print(f"   {doc.page_content[:200]}...")
