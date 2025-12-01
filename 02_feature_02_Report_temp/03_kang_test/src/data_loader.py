# data_loader.py
import os
import json
import re
import fitz
from typing import Dict, List, Optional, Tuple
from langchain_core.documents import Document


# ------------------------------------------------------
# 청킹 규칙 정의
# ------------------------------------------------------
CHUNK_RULES = {
    "country_info": {
        "US": {"chunk_size": 700, "overlap": 150},
        "VN": {"chunk_size": 1000, "overlap": 200},
        "JP": {"chunk_size": 1000, "overlap": 200},
        "CN": {"chunk_size": 1000, "overlap": 200},
        "KR": {"chunk_size": 1000, "overlap": 200},
    },
    "strategy_pdf": {
        "KATI": {
            2022: {"chunk_size": 1000, "overlap": 180},
            2023: {"chunk_size": 1000, "overlap": 180},
            2024: {"chunk_size": 1000, "overlap": 200},
        },
        "KOTRA": {
            2023: {"chunk_size": 1000, "overlap": 180},
            2024: {"chunk_size": 1000, "overlap": 200},
            2025: {"chunk_size": 1000, "overlap": 200},
        },
    },
}


class DataLoader:
    def __init__(self):
        self.chunk_rules = CHUNK_RULES

    # ------------------------------------------------------
    # 국가명 → 국가코드 변환
    # ------------------------------------------------------
    def normalize_country(self, country_name: str) -> str:
        country_map = {
            "일본": "JP",
            "미국": "US",
            "베트남": "VN",
            "중국": "CN",
            "한국": "KR",
        }

        code = country_map.get(country_name)
        if not code:
            available = ", ".join(country_map.keys())
            raise ValueError(
                f"지원하지 않는 국가명: {country_name}\n사용 가능: {available}"
            )
        return code

    def get_available_countries(self) -> List[str]:
        return ["일본", "미국", "베트남", "중국", "한국"]

    # ------------------------------------------------------
    # JSON 로드
    # ------------------------------------------------------
    def load_country_info(self, country_code: str) -> Dict:
        filepath = os.path.join(
            "..", "data", "country_info", f"country_info_{country_code}.json"
        )

        if not os.path.exists(filepath):
            print(f"⚠️ 국가정보 JSON 없음: {filepath}")
            return {}

        try:
            with open(filepath, "r", encoding="utf-8") as f:
                data = json.load(f)
            print(f"국가정보 로드 완료: {filepath}")
            return data
        except Exception as e:
            print(f"JSON 로드 실패: {filepath} - {e}")
            return {}

    # ------------------------------------------------------
    # PDF에서 텍스트 추출
    # ------------------------------------------------------
    def extract_text_from_pdf(self, pdf_path: str) -> List[str]:
        try:
            doc = fitz.open(pdf_path)
            pages = []
            for page in doc:
                text = page.get_text("text")
                if text.strip():
                    pages.append(text.strip())
            doc.close()
            return pages
        except Exception as e:
            print(f"PDF 로드 실패: {pdf_path} - {e}")
            return []

    # ------------------------------------------------------
    # 텍스트 청킹
    # ------------------------------------------------------
    def chunk_text(self, text: str, chunk_size=1000, overlap=200) -> List[str]:
        if not text:
            return []

        chunks = []
        start = 0
        length = len(text)

        while start < length:
            end = min(start + chunk_size, length)
            chunk = text[start:end]
            if chunk.strip():
                chunks.append(chunk)
            if end >= length:
                break
            start = end - overlap
        return chunks

    # ------------------------------------------------------
    # 파일명으로 메타데이터 추출
    # ------------------------------------------------------
    def extract_metadata(self, filename: str) -> Dict:
        base = os.path.basename(filename).lower()

        year_match = re.search(r"(202[2-5])", base)
        year = int(year_match.group(1)) if year_match else None

        if "kati" in base:
            source = "KATI"
        elif "kotra" in base:
            source = "KOTRA"
        else:
            source = "UNKNOWN"

        country_match = re.search(r"(JP|US|VN|CN|KR)", base, re.IGNORECASE)
        country_code = country_match.group(1).upper() if country_match else "UNKNOWN"

        return {
            "year": year,
            "source": source,
            "country_code": country_code,
        }

    # ------------------------------------------------------
    # 청킹 파라미터 선택 (출처·연도 규칙 적용)
    # ------------------------------------------------------
    def get_chunk_params(
        self, source: str, country_code: str, year: Optional[int], origin: Optional[str]
    ):
        if source == "country_info":
            rule = self.chunk_rules["country_info"].get(country_code)
            return (rule["chunk_size"], rule["overlap"]) if rule else (1000, 200)

        if source == "strategy_pdf":
            if origin not in self.chunk_rules["strategy_pdf"]:
                return 1000, 200

            year_rules = self.chunk_rules["strategy_pdf"][origin]

            if year not in year_rules:
                year = max(year_rules.keys())

            rule = year_rules.get(year)
            if rule:
                return rule["chunk_size"], rule["overlap"]

            return 1000, 200

        return 1000, 200

    # ------------------------------------------------------
    # PDF 병합
    # ------------------------------------------------------
    def merge_pages(self, pages: List[str]) -> str:
        return "\n\n".join(pages)

    # ------------------------------------------------------
    # PDF → Document 리스트 변환
    # ------------------------------------------------------
    def process_pdf(self, pdf_path: str):
        metadata = self.extract_metadata(pdf_path)

        if metadata["source"] not in ["KATI", "KOTRA"]:
            print(f"지원하지 않는 출처 PDF: {pdf_path}")
            return []

        pages = self.extract_text_from_pdf(pdf_path)

        valid_pages = [p for p in pages if len(p.strip()) > 30]

        if not valid_pages:
            print("텍스트 없는 PDF 건너뜀:", pdf_path)
            return []

        full_text = self.merge_pages(valid_pages)

        chunk_size, overlap = self.get_chunk_params(
            source="strategy_pdf",
            country_code=metadata["country_code"],
            year=metadata["year"],
            origin=metadata["source"],
        )

        chunks = self.chunk_text(full_text, chunk_size, overlap)

        documents = []
        for i, chunk in enumerate(chunks):
            doc_meta = {
                "source": metadata["source"],
                "country_code": metadata["country_code"],
                "year": metadata["year"],
                "chunk_index": i,
                "total_chunks": len(chunks),
                "file_name": os.path.basename(pdf_path),
            }

            documents.append(Document(page_content=chunk, metadata=doc_meta))

        return documents

    # ------------------------------------------------------
    # JSON → Document 리스트 변환
    # ------------------------------------------------------
    def process_country_info(self, country_code: str) -> List[Document]:
        data = self.load_country_info(country_code)
        if not data:
            return []

        text = json.dumps(data, ensure_ascii=False, indent=2)

        chunk_size, overlap = self.get_chunk_params(
            source="country_info",
            country_code=country_code,
            year=None,
            origin=None,
        )

        chunks = self.chunk_text(text, chunk_size, overlap)

        documents = []
        for i, chunk in enumerate(chunks):
            meta = {
                "source": "COUNTRY_INFO",
                "country_code": country_code,
                "chunk_index": i,
                "total_chunks": len(chunks),
                "file_name": f"country_info_{country_code}.json",
            }

            documents.append(Document(page_content=chunk, metadata=meta))

        return documents

    # ------------------------------------------------------
    # 폴더 내 PDF 전체 처리
    # ------------------------------------------------------
    def process_all_pdfs(self, folder_path: str) -> List[Document]:
        if not os.path.exists(folder_path):
            print(f"폴더 없음: {folder_path}")
            return []

        pdf_files = [f for f in os.listdir(folder_path) if f.endswith(".pdf")]

        all_docs = []
        for f in pdf_files:
            pdf_path = os.path.join(folder_path, f)
            docs = self.process_pdf(pdf_path)
            all_docs.extend(docs)

        return all_docs
