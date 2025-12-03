"""
PDF, JSON, CSV 데이터를 로드하고 처리하는 모듈
"""

import os
import json
from typing import List, Dict
from pathlib import Path

from langchain_community.document_loaders import PyPDFLoader
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain.schema import Document


class DataLoader:
    """데이터 로드 및 전처리 클래스"""

    def __init__(self, data_dir: str = "data"):
        self.data_dir = Path(data_dir)
        self.kati_dir = self.data_dir / "kati"
        self.kotra_dir = self.data_dir / "kotra"
        self.country_info_dir = self.data_dir / "country_info"

    # ---------------------------------------------------------
    # 청킹 규칙 테이블

    # ---------------------------------------------------------

    CHUNK_RULES = {
        "country_info": {
            "미국": {"size": 700, "overlap": 150},
            "베트남": {"size": 1000, "overlap": 200},
            "일본": {"size": 1000, "overlap": 200},
        },
        "strategy": {  # KATI/KOTRA 공통
            2025: {
                "미국": {"size": 1000, "overlap": 200},
                "베트남": {"size": 1000, "overlap": 200},
                "일본": {"size": 1000, "overlap": 200},
            },
            2024: {
                "미국": {"size": 1000, "overlap": 180},
                "베트남": {"size": 1000, "overlap": 180},
                "일본": {"size": 1000, "overlap": 200},
            },
            2023: {
                "미국": {"size": 1000, "overlap": 180},
                "베트남": {"size": 1000, "overlap": 180},
                "일본": {"size": 1000, "overlap": 180},
            },
        },
    }

    # ---------------------------------------------------------
    # PDF 로더들
    # ---------------------------------------------------------
    def load_kati_pdfs(self, country: str = None) -> List[Document]:
        documents = []
        pdf_files = list(self.kati_dir.glob("*.pdf"))

        # 국가 필터링 추가
        if country:
            pdf_files = [f for f in pdf_files if country in f.name]

        print(f"📚 KATI PDF 파일 {len(pdf_files)}개 발견")

        for pdf_file in pdf_files:
            try:
                loader = PyPDFLoader(str(pdf_file))
                pages = loader.load()

                for page in pages:
                    page.metadata.update(
                        {
                            "source": "KATI",
                            "file_name": pdf_file.name,
                            "year": self._extract_year(pdf_file.name),
                            "country": self._extract_country(pdf_file.name),
                            "doc_type": "strategy",
                        }
                    )

                documents.extend(pages)
                print(f"  ✅ {pdf_file.name}: {len(pages)} 페이지")

            except Exception as e:
                print(f"  ❌ {pdf_file.name} 로드 실패: {e}")

        print(f"📊 총 {len(documents)} 페이지 로드 완료\n")
        return documents

    def load_kotra_pdfs(self, country: str = None) -> List[Document]:
        documents = []
        pdf_files = list(self.kotra_dir.glob("*.pdf"))

        if country:
            pdf_files = [f for f in pdf_files if country in f.name]

        print(f"🌍 KOTRA PDF 파일 {len(pdf_files)}개 발견")

        for pdf_file in pdf_files:
            try:
                loader = PyPDFLoader(str(pdf_file))
                pages = loader.load()

                for page in pages:
                    page.metadata.update(
                        {
                            "source": "KOTRA",
                            "file_name": pdf_file.name,
                            "country": self._extract_country(pdf_file.name),
                            "year": self._extract_year(pdf_file.name),
                            "doc_type": "strategy",
                        }
                    )

                documents.extend(pages)
                print(f"  ✅ {pdf_file.name}: {len(pages)} 페이지")

            except Exception as e:
                print(f"  ❌ {pdf_file.name} 로드 실패: {e}")

        print(f"📊 총 {len(documents)} 페이지 로드 완료\n")
        return documents

    # ---------------------------------------------------------
    # 국가정보 JSON 로드
    # ---------------------------------------------------------
    def load_country_info(self, country: str) -> Dict:
        json_file = self.country_info_dir / f"{country}.json"

        if not json_file.exists():
            print(f"⚠️  {country}.json 파일을 찾을 수 없습니다")
            return {}

        try:
            with open(json_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            print(f"✅ {country} 정보 로드 완료")
            return data
        except Exception as e:
            print(f"❌ JSON 로드 실패: {e}")
            return {}

    # ---------------------------------------------------------
    # ★ 핵심: 청킹 규칙 자동 적용
    # ---------------------------------------------------------
    def chunk_documents(self, documents: List[Document]) -> List[Document]:
        if not documents:
            return []

        # 첫 문서의 메타데이터로 통일된 설정 추론
        meta = documents[0].metadata
        country = meta.get("country")
        year = meta.get("year")
        doc_type = meta.get("doc_type", "strategy")  # 기본값: 진출전략 PDF

        # 1) 국가정보 JSON
        if doc_type == "country_info":
            rule = self.CHUNK_RULES["country_info"].get(
                country, {"size": 1000, "overlap": 200}
            )

        # 2) 진출전략 PDF
        else:
            year_rules = self.CHUNK_RULES["strategy"].get(year, {})
            rule = year_rules.get(country, {"size": 1000, "overlap": 200})

        chunk_size = rule["size"]
        chunk_overlap = rule["overlap"]

        print(f"✂️  문서 분할 시작 | country={country}, year={year}, type={doc_type}")
        print(f"    → chunk_size={chunk_size}, overlap={chunk_overlap}")

        splitter = RecursiveCharacterTextSplitter(
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
            length_function=len,
            separators=["\n\n", "\n", " ", ""],
        )

        chunks = splitter.split_documents(documents)

        for i, chunk in enumerate(chunks):
            chunk.metadata["chunk_id"] = i

        print(f"✅ {len(documents)} 문서 → {len(chunks)} 청크 생성\n")
        return chunks

    # ---------------------------------------------------------
    # 보조 함수들
    # ---------------------------------------------------------
    def _extract_year(self, filename: str) -> int:
        import re

        match = re.search(r"20\d{2}", filename)
        return int(match.group(0)) if match else None

    def _extract_country(self, filename: str) -> str:
        country_map = {
            "japan": "일본",
            "일본": "일본",
            "usa": "미국",
            "미국": "미국",
            "vietnam": "베트남",
            "베트남": "베트남",
            "china": "중국",
            "중국": "중국",
        }
        filename_lower = filename.lower()
        for key, value in country_map.items():
            if key in filename_lower:
                return value
        return "Unknown"
