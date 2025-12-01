from typing import List, Dict
from langchain_core.documents import Document
from langchain_openai import OpenAIEmbeddings
from langchain_community.vectorstores import Chroma


class VectorDBManager:
    def __init__(self, persist_dir="vectordb_store"):
        self.persist_dir = persist_dir
        self.embedding = OpenAIEmbeddings(model="text-embedding-3-large")
        self.db = None

    def load_vectorstore(self):
        self.db = Chroma(
            persist_directory=self.persist_dir, embedding_function=self.embedding
        )

    def save_vectorstore(self):
        if self.db:
            self.db.persist()

    def insert_documents(self, docs: List[Document]):
        if not self.db:
            self.load_vectorstore()
        self.db.add_documents(docs)


class SearchEngine:
    def __init__(self, vectordb_manager: VectorDBManager):
        if not vectordb_manager.db:
            vectordb_manager.load_vectorstore()
        self.db = vectordb_manager.db

    def search_all_sections(
        self,
        queries: Dict[str, str],
        country: str,
        hs_code: str,
        k_per_section: int = 5,
    ):
        results = {}
        for section_name, query_text in queries.items():
            filter_dict = {"country_code": country}
            docs = self.db.similarity_search(
                query=query_text, k=k_per_section, filter=filter_dict
            )
            results[section_name] = docs
        return results
