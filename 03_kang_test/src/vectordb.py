# VectorDB 생성·로드 함수

from langchain_community.vectorstores import Chroma
from langchain_openai import OpenAIEmbeddings


def build_vector_db(chunks, persist_dir="./chroma_kang"):
    texts = [c["text"] for c in chunks]
    metadatas = [c["metadata"] for c in chunks]

    embeddings = OpenAIEmbeddings(model="text-embedding-3-small")
    db = Chroma.from_texts(
        texts=texts,
        metadatas=metadatas,
        embedding=embeddings,
        persist_directory=persist_dir,
    )
    db.persist()
    return db


def load_vector_db(persist_dir="./chroma_kang"):
    embeddings = OpenAIEmbeddings(model="text-embedding-3-small")
    db = Chroma(embedding_function=embeddings, persist_directory=persist_dir)
    return db
