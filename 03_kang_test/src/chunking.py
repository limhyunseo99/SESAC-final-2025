# docs 리스트를 받아서 chunk 단위 텍스트로 쪼개고, 메타데이터 붙이기

# chunking.py
from typing import List, Dict


def simple_chunk(text: str, chunk_size=1000, overlap=200):
    tokens = text.split()
    chunks = []
    start = 0
    while start < len(tokens):
        end = start + chunk_size
        chunk_tokens = tokens[start:end]
        chunks.append(" ".join(chunk_tokens))
        if end >= len(tokens):
            break
        start = end - overlap
    return chunks


def make_chunks(raw_pages: List[Dict], chunk_size=1000, overlap=200):
    chunk_docs = []
    for page in raw_pages:
        chunks = simple_chunk(page["text"], chunk_size, overlap)
        for i, ch in enumerate(chunks):
            chunk_docs.append(
                {
                    "id": f"{page['id']}_c{i + 1}",
                    "text": ch,
                    "metadata": {
                        "source": page["source"],
                        "page": page["page"],
                        # 나중에 국가, 연도, 보고서 유형 등을 여기 추가
                    },
                }
            )
    return chunk_docs
