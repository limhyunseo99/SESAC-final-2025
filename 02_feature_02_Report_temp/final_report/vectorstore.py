# vectorstore.py
# Qdrant Cloud 벡터 저장소

import logging
from typing import List, Optional, Any

from qdrant_client import QdrantClient
from qdrant_client.http import models as qmodels
from langchain_openai import OpenAIEmbeddings
from langchain_core.documents import Document

from config import Config

logger = logging.getLogger(__name__)


class QdrantVectorDB:
    """Qdrant Cloud 기반 벡터 저장소"""
    
    def __init__(self):
        self.collection = Config.QDRANT_COLLECTION
        self.client = QdrantClient(
            url=Config.QDRANT_URL,
            api_key=Config.QDRANT_API_KEY,
            timeout=60
        )
        self.embedding = OpenAIEmbeddings(model="text-embedding-3-large")
        self._ensure_collection()
        logger.info("QdrantVectorDB 초기화 완료")
    
    def _ensure_collection(self):
        """컬렉션이 없으면 생성"""
        if self.client.collection_exists(self.collection):
            return
        
        logger.warning(f"컬렉션 생성: {self.collection}")
        self.client.recreate_collection(
            collection_name=self.collection,
            vectors_config=qmodels.VectorParams(size=3072, distance=qmodels.Distance.COSINE)
        )
    
    def insert(self, docs: List[Document]):
        """문서 벡터 삽입"""
        if not docs:
            return
        
        contents = [d.page_content for d in docs]
        vectors = self.embedding.embed_documents(contents)
        
        payloads = [{
            "text": d.page_content,
            "country_code": d.metadata.get("country_code"),
            "source": d.metadata.get("source"),
            "year": d.metadata.get("year"),
            "file_name": d.metadata.get("file_name"),
        } for d in docs]
        
        self.client.upsert(
            collection_name=self.collection,
            points=qmodels.Batch(ids=None, vectors=vectors, payloads=payloads)
        )
        logger.info(f"{len(docs)}개 문서 삽입 완료")
    
    def search(self, query: str, country: Optional[str] = None, k: int = 5) -> List[Document]:
        """벡터 검색"""
        query_vec = self.embedding.embed_query(query)
        
        filters = None
        if country:
            filters = qmodels.Filter(must=[
                qmodels.FieldCondition(key="country_code", match=qmodels.MatchValue(value=country))
            ])
        
        results = self.client.search(
            collection_name=self.collection,
            query_vector=query_vec,
            limit=k,
            score_threshold=0.55,
            query_filter=filters
        )
        
        return [
            Document(
                page_content=r.payload.get("text", ""),
                metadata={
                    "score": r.score,
                    "country_code": r.payload.get("country_code"),
                    "source": r.payload.get("source"),
                    "file_name": r.payload.get("file_name"),
                }
            )
            for r in results if r.payload.get("text")
        ]
    
    def has_data(self) -> bool:
        """데이터 존재 여부"""
        try:
            return self.client.count(collection_name=self.collection).count > 0
        except:
            return False