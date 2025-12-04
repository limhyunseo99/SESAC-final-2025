# config.py
# 설정 + DataLoader + Supervisor 통합

import os
import re
import json
import logging
from typing import Dict, List, Optional, Tuple

import fitz  # PyMuPDF
from dotenv import load_dotenv
from langchain_core.documents import Document

load_dotenv()
logger = logging.getLogger(__name__)


# =============================================================================
# Config - 환경설정
# =============================================================================
class Config:
    """프로젝트 공통 설정"""
    
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))
    DATA_DIR = os.path.join(BASE_DIR, "data")
    OUTPUT_DIR = os.path.join(BASE_DIR, "output")
    
    # LLM 모델
    MODEL_FAST = os.getenv("MODEL_FAST", "gpt-5-mini")
    MODEL_SMART = os.getenv("MODEL_SMART", "gpt-5")
    
    # API Keys
    TAVILY_API_KEY = os.getenv("TAVILY_API_KEY", "")
    OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
    
    # Qdrant
    QDRANT_URL = os.getenv("QDRANT_URL", "")
    QDRANT_API_KEY = os.getenv("QDRANT_API_KEY", "")
    QDRANT_COLLECTION = os.getenv("QDRANT_COLLECTION", "globalpath_vectors")
    
    # 국가 코드 맵
    COUNTRY_MAP = {"US": "US", "JP": "JP", "VN": "VN"}


# =============================================================================
# DataLoader - 데이터 로딩
# =============================================================================
class DataLoader:
    """JSON, PDF 데이터를 Document로 변환"""
    
    @staticmethod
    def normalize_country(name: str) -> str:
        """국가명 → 코드 변환"""
        if not name:
            raise ValueError("국가명이 비어 있습니다.")
        
        name = name.strip().upper()
        mapping = {
            "미국": "US", "UNITED STATES": "US", "USA": "US", "US": "US",
            "일본": "JP", "JAPAN": "JP", "JP": "JP",
            "베트남": "VN", "VIETNAM": "VN", "VN": "VN",
        }
        
        if name in mapping:
            return mapping[name]
        if name in Config.COUNTRY_MAP.values():
            return name
        
        raise ValueError(f"지원하지 않는 국가: {name}")
    
    @staticmethod
    def load_country_info(country_code: str) -> Dict:
        """국가 정보 JSON 로드"""
        path = os.path.join(Config.DATA_DIR, "country_info", f"country_info_{country_code.upper()}.json")
        
        if not os.path.exists(path):
            logger.warning(f"국가 정보 없음: {path}")
            return {}
        
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"JSON 로드 실패: {e}")
            return {}
    
    @staticmethod
    def process_country_json(country_code: str) -> List[Document]:
        """국가 JSON → Document 리스트"""
        data = DataLoader.load_country_info(country_code)
        docs = []
        
        items = data if isinstance(data, list) else data.get("chunks", [])
        
        for item in items:
            text = item.get("text") or item.get("content") or ""
            if not text.strip():
                continue
            
            docs.append(Document(
                page_content=text,
                metadata={
                    "country_code": country_code,
                    "source": item.get("source", "country_info"),
                    "year": item.get("year"),
                    "file_name": item.get("file_name", f"country_info_{country_code}.json"),
                }
            ))
        
        return docs
    
    @staticmethod
    def process_all_pdfs(root_dir: str) -> List[Document]:
        """폴더 내 모든 PDF → Document 리스트"""
        docs = []
        
        if not os.path.exists(root_dir):
            return docs
        
        for dirpath, _, filenames in os.walk(root_dir):
            for fname in filenames:
                if not fname.lower().endswith(".pdf"):
                    continue
                
                pdf_path = os.path.join(dirpath, fname)
                try:
                    pages = DataLoader._extract_pdf_pages(pdf_path)
                    chunks = DataLoader._chunk_pages(pages)
                    
                    country = DataLoader._infer_country(fname)
                    year = DataLoader._infer_year(fname)
                    source = "kati" if "kati" in pdf_path.lower() else "kotra" if "kotra" in pdf_path.lower() else "pdf"
                    
                    for text, page_start, page_end in chunks:
                        docs.append(Document(
                            page_content=text,
                            metadata={
                                "country_code": country,
                                "source": source,
                                "year": year,
                                "file_name": fname,
                                "page_start": page_start + 1,
                                "page_end": page_end + 1,
                            }
                        ))
                except Exception as e:
                    logger.error(f"PDF 처리 실패: {pdf_path}, {e}")
        
        return docs
    
    @staticmethod
    def _extract_pdf_pages(pdf_path: str) -> List[str]:
        """PDF에서 페이지별 텍스트 추출"""
        try:
            doc = fitz.open(pdf_path)
            pages = [page.get_text("text").strip() for page in doc]
            doc.close()
            return pages
        except:
            return []
    
    @staticmethod
    def _chunk_pages(pages: List[str], chunk_size: int = 1000) -> List[Tuple[str, int, int]]:
        """페이지 텍스트를 청크로 분할"""
        chunks = []
        current_text, start_page = "", 0
        
        for i, page in enumerate(pages):
            if not page:
                continue
            if not current_text:
                start_page = i
            
            if len(current_text) + len(page) <= chunk_size:
                current_text += "\n" + page
            else:
                if current_text.strip():
                    chunks.append((current_text.strip(), start_page, i))
                current_text = page
                start_page = i
        
        if current_text.strip():
            chunks.append((current_text.strip(), start_page, len(pages) - 1))
        
        return chunks
    
    @staticmethod
    def _infer_country(fname: str) -> Optional[str]:
        upper = fname.upper()
        if "JAPAN" in upper or "_JP" in upper: return "JP"
        if "VIETNAM" in upper or "_VN" in upper: return "VN"
        if "USA" in upper or "_US" in upper: return "US"
        return None
    
    @staticmethod
    def _infer_year(fname: str) -> Optional[int]:
        m = re.search(r"(20[0-3][0-9])", fname)
        return int(m.group(1)) if m else None


# =============================================================================
# Supervisor - 품질 검증
# =============================================================================
class Supervisor:
    """품질 검증 및 신뢰도 평가"""
    def __init__(self, research_logger=None):
        self.logger = research_logger
        self.quality_threshold = 70
    
    def score_web_result(self, content: str, urls: List[str]) -> Dict:
        """웹 검색 결과 신뢰도 평가"""
        if not content:
            return {"grade": "Low", "score": 0}
        
        numbers = len(re.findall(r"\d+", content))
        url_count = len([u for u in urls if u])
        
        score = min(numbers * 3, 30) + min(url_count * 10, 40) + min(len(content) // 500 * 10, 30)
        grade = "High" if score >= 80 else "Medium" if score >= 50 else "Low"
        
        return {"grade": grade, "score": score, "numbers": numbers, "sources": url_count}
    
    def validate_summary(self, text: str) -> Dict:
        """요약문 품질 검증"""
        if not text or not text.strip():
            return {"score": 0, "message": "요약문 없음"}
        
        length = len(text)
        numbers = len(re.findall(r"\d+", text))
        
        score = 0
        if length >= 400: score += 40
        elif length >= 250: score += 25
        
        if numbers >= 3: score += 40
        elif numbers >= 1: score += 20
        
        if any(kw in text for kw in ["성장", "시장", "수요"]): score += 10
        
        return {
            "score": score,
            "length": length,
            "numbers": numbers,
            "message": "양호" if score >= 70 else "개선 필요"
        }
