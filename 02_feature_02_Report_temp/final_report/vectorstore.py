# vectorstore.py
# Qdrant Cloud 벡터 저장소

import logging
from typing import List, Optional, Dict
import uuid
import time

from qdrant_client import QdrantClient
from qdrant_client.http import models as qmodels
from langchain_openai import OpenAIEmbeddings
from langchain_core.documents import Document

from config import Config

logger = logging.getLogger(__name__)


class QdrantVectorDB:
    """Qdrant Cloud 기반 벡터 저장소"""
    
    def __init__(self):
        self.collection = Config.QDRANT_COLLECTION_REPORT
        self.client = QdrantClient(
            url=Config.QDRANT_URL,
            api_key=Config.QDRANT_API_KEY,
            timeout=120
        )
        self.embedding = OpenAIEmbeddings(model="text-embedding-3-large")
        self._ensure_collection()
    
    def _ensure_collection(self):
        """컬렉션 존재 확인 및 생성"""
        if self.client.collection_exists(self.collection):
            logger.info(f"✓ 컬렉션 존재: {self.collection}")
            return
        
        self.client.recreate_collection(
            collection_name=self.collection,
            vectors_config=qmodels.VectorParams(
                size=3072,
                distance=qmodels.Distance.COSINE
            )
        )
        logger.info(f"✓ 컬렉션 생성 완료: {self.collection}")
    
    def insert(self, docs: List[Document], batch_size: int = 50):
        """문서 벡터 삽입 (배치 처리)"""
        if not docs:
            logger.warning("삽입할 문서가 없습니다.")
            return
        
        total_docs = len(docs)
        logger.info(f"총 {total_docs}개 문서를 {batch_size}개씩 배치 업로드합니다...")
        
        for batch_num, i in enumerate(range(0, total_docs, batch_size), 1):
            batch_docs = docs[i:i + batch_size]
            
            try:
                contents = [d.page_content for d in batch_docs]
                
                logger.info(f"배치 {batch_num}/{(total_docs + batch_size - 1) // batch_size}: 임베딩 생성 중... ({len(batch_docs)}개)")
                vectors = self.embedding.embed_documents(contents)
                
                ids = [str(uuid.uuid4()) for _ in range(len(batch_docs))]
                
                payloads = []
                for d in batch_docs:
                    meta = d.metadata
                    payloads.append({
                        "text": d.page_content,
                        "type": meta.get("source"),
                        "country_code": meta.get("country_code"),
                        "source": meta.get("source"),
                        "source_type": meta.get("source_type"),
                        "file_name": meta.get("file_name"),
                        "page_start": meta.get("page_start"),
                        "page_end": meta.get("page_end"),
                        "year": meta.get("year"),
                        "section": meta.get("section"),
                        "citation": meta.get("citation", ""),
                    })
                
                logger.info(f"배치 {batch_num}: Qdrant 업로드 중...")
                self.client.upsert(
                    collection_name=self.collection,
                    points=qmodels.Batch(
                        ids=ids,
                        vectors=vectors,
                        payloads=payloads
                    )
                )
                
                logger.info(f"✓ 배치 {batch_num} 완료 ({len(batch_docs)}개)")
                
                if i + batch_size < total_docs:
                    time.sleep(0.5)
                    
            except Exception as e:
                logger.error(f"✗ 배치 {batch_num} 실패: {e}", exc_info=True)
                continue
        
        logger.info(f"✅ 전체 업로드 완료: {total_docs}개 문서")
    
    def search(
        self,
        query: str,
        country: Optional[str] = None,
        source: Optional[str] = None,
        k: int = 5,
        score_threshold: float = 0.55
    ) -> List[Document]:
        """벡터 검색 (올바른 API 사용)"""
        try:
            query_vec = self.embedding.embed_query(query)
            
            must_conditions = []
            
            # 국가 필터
            if country:
                must_conditions.append(
                    qmodels.FieldCondition(
                        key="country_code",
                        match=qmodels.MatchValue(value=country)
                    )
                )
            
            # 소스 필터
            if source:
                must_conditions.append(
                    qmodels.Filter(
                        should=[
                            qmodels.FieldCondition(
                                key="source",
                                match=qmodels.MatchValue(value=source)
                            ),
                            qmodels.FieldCondition(
                                key="type",
                                match=qmodels.MatchValue(value=source)
                            )
                        ]
                    )
                )
            
            query_filter = qmodels.Filter(must=must_conditions) if must_conditions else None
            
            results = self.client.query_points(
                collection_name=self.collection,
                query=query_vec,
                limit=k,
                score_threshold=0.0,  
                query_filter=query_filter
            )
            
            docs = []
            
            # results.points가 ScoredPoint 리스트
            for point in results.points:
                if not point.payload.get("text"):
                    continue
                
                docs.append(Document(
                    page_content=point.payload.get("text", ""),
                    metadata={
                        "score": point.score,
                        "country_code": point.payload.get("country_code"),
                        "source": point.payload.get("source"),
                        "source_type": point.payload.get("source_type"),
                        "file_name": point.payload.get("file_name"),
                        "page_start": point.payload.get("page_start"),
                        "page_end": point.payload.get("page_end"),
                        "year": point.payload.get("year"),
                        "section": point.payload.get("section"),
                        "citation": point.payload.get("citation", ""),
                    }
                ))
            
            logger.debug(f"✓ 검색 완료: {len(docs)}개 문서 반환")
            return docs
            
        except Exception as e:
            logger.error(f"✗ 검색 실패: {e}", exc_info=True)
            return []
    
    def retrieve(
        self,
        query: str,
        top_k: int = 5,
        filter_dict: Optional[Dict] = None,
        score_threshold: float = 0.55
    ) -> List[Document]:
        """retrieve 메서드 (pipeline.py에서 사용)"""
        country = None
        source = None
        
        if filter_dict:
            country = filter_dict.get("country_code")
            source = filter_dict.get("type")
        
        return self.search(
            query=query,
            country=country,
            source=source,
            k=top_k,
            score_threshold=score_threshold
        )
    
    def search_by_source(
        self,
        query: str,
        country: str,
        sources: List[str],
        k: int = 5
    ) -> List[Document]:
        """여러 소스에서 검색"""
        all_docs = []
        
        for source in sources:
            docs = self.search(query, country=country, source=source, k=k)
            all_docs.extend(docs)
        
        all_docs.sort(key=lambda x: x.metadata.get("score", 0), reverse=True)
        
        seen_content = set()
        unique_docs = []
        for doc in all_docs:
            content_hash = hash(doc.page_content[:200])
            if content_hash not in seen_content:
                seen_content.add(content_hash)
                unique_docs.append(doc)
        
        return unique_docs[:k]
    
    def has_data(self) -> bool:
        """데이터 존재 여부 확인"""
        try:
            count = self.client.count(collection_name=self.collection)
            has_data = count.count > 0
            logger.info(f"✓ 컬렉션 데이터 개수: {count.count}")
            return has_data
        except Exception as e:
            logger.error(f"✗ 데이터 확인 실패: {e}")
            return False
    
    def get_collection_info(self) -> Dict:
        """컬렉션 정보 조회"""
        try:
            collection = self.client.get_collection(self.collection)
            count = self.client.count(collection_name=self.collection)
            
            return {
                "name": self.collection,
                "vectors_count": count.count,
                "status": collection.status,
                "optimizer_status": collection.optimizer_status,
            }
        except Exception as e:
            logger.error(f"✗ 컬렉션 정보 조회 실패: {e}")
            return {"error": str(e)}