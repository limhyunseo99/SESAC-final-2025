# config.py
# 설정, 청킹 규칙, DataLoader, Supervisor 통합

import os
import re
import json
import csv
import time
import logging
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass

import fitz
from dotenv import load_dotenv
from langchain_core.documents import Document
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage

load_dotenv()
logger = logging.getLogger(__name__)


class Config:
    """프로젝트 설정"""
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))
    DATA_DIR = os.path.join(BASE_DIR, "data")
    OUTPUT_DIR = os.path.join(BASE_DIR, "output")
    
    MODEL_FAST = os.getenv("MODEL_FAST", "gpt-5-mini") # 간단하고 작업
    MODEL_SMART = os.getenv("MODEL_SMART", "gpt-5") # 복잡한 작업
    
    TAVILY_API_KEY = os.getenv("TAVILY_API_KEY", "")
    OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
    
    QDRANT_URL = os.getenv("QDRANT_URL", "")
    QDRANT_API_KEY = os.getenv("QDRANT_API_KEY", "")
    QDRANT_COLLECTION_HTS = os.getenv("QDRANT_COLLECTION_HTS", "hts_case_all")
    QDRANT_COLLECTION_REPORT = os.getenv("QDRANT_COLLECTION_REPORT", "REPORT")

    COUNTRY_MAP = {"미국": "US", "일본": "JP", "베트남": "VN"}
    COUNTRY_NAMES = {"US": "미국", "JP": "일본", "VN": "베트남"}
    
    PUBLIC_DOMAINS = [
        "go.kr", "gov", "or.kr", "ac.kr", "edu",
        "kotra.or.kr", "kati.net", "customs.go.kr",
        "fda.gov", "usda.gov", "maff.go.jp", "meti.go.jp"
    ]


# 청킹 규칙
CHUNKING_RULES = {
    "country_info_US": {"chunk_size": 700, "chunk_overlap": 150},
    "country_info_VN": {"chunk_size": 1000, "chunk_overlap": 200},
    "country_info_JP": {"chunk_size": 1000, "chunk_overlap": 200},
    "2025_kati_US": {"chunk_size": 1000, "chunk_overlap": 200},
    "2025_kati_VN": {"chunk_size": 1000, "chunk_overlap": 200},
    "2025_kati_JP": {"chunk_size": 1000, "chunk_overlap": 200},
    "2024_kati_US": {"chunk_size": 1000, "chunk_overlap": 180},
    "2024_kati_VN": {"chunk_size": 1000, "chunk_overlap": 180},
    "2024_kati_JP": {"chunk_size": 1000, "chunk_overlap": 200},
    "2023_kati_US": {"chunk_size": 1000, "chunk_overlap": 180},
    "2023_kati_VN": {"chunk_size": 1000, "chunk_overlap": 180},
    "2023_kati_JP": {"chunk_size": 1000, "chunk_overlap": 180},
    "2022_kati_US": {"chunk_size": 1000, "chunk_overlap": 180},
    "2022_kati_VN": {"chunk_size": 1000, "chunk_overlap": 180},
    "2022_kati_JP": {"chunk_size": 1000, "chunk_overlap": 180},
    "2025_kotra_US": {"chunk_size": 1000, "chunk_overlap": 200},
    "2025_kotra_VN": {"chunk_size": 1000, "chunk_overlap": 200},
    "2025_kotra_JP": {"chunk_size": 1000, "chunk_overlap": 200},
    "2024_kotra_US": {"chunk_size": 1000, "chunk_overlap": 180},
    "2024_kotra_VN": {"chunk_size": 1000, "chunk_overlap": 180},
    "2024_kotra_JP": {"chunk_size": 1000, "chunk_overlap": 200},
    "2023_kotra_US": {"chunk_size": 1000, "chunk_overlap": 180},
    "2023_kotra_VN": {"chunk_size": 1000, "chunk_overlap": 180},
    "2023_kotra_JP": {"chunk_size": 1000, "chunk_overlap": 180},
    "default": {"chunk_size": 1000, "chunk_overlap": 200},
}


def get_chunking_rule(filename: str) -> Dict[str, int]:
    """파일명에서 청킹 규칙 추출"""
    fname_upper = filename.upper()
    
    year_match = re.search(r"(202[0-9])", filename)
    year = year_match.group(1) if year_match else ""
    
    country = ""
    if "_US" in fname_upper or "US." in fname_upper:
        country = "US"
    elif "_JP" in fname_upper or "JP." in fname_upper:
        country = "JP"
    elif "_VN" in fname_upper or "VN." in fname_upper:
        country = "VN"
    
    source = ""
    if "KATI" in fname_upper:
        source = "kati"
    elif "KOTRA" in fname_upper:
        source = "kotra"
    elif "COUNTRY_INFO" in fname_upper:
        source = "country_info"
    
    if source == "country_info" and country:
        key = f"country_info_{country}"
    elif year and source and country:
        key = f"{year}_{source}_{country}"
    else:
        key = "default"
    
    return CHUNKING_RULES.get(key, CHUNKING_RULES["default"])


class DataLoader:
    """데이터 로딩 및 처리"""
    
    @staticmethod
    def normalize_country(name: str) -> str:
        """국가명을 코드로 변환/일관된 코드로 변환하여 전달"""
        if not name:
            raise ValueError("국가명이 비어 있습니다.")
        
        name = name.strip()
        
        # 괄호 제거 (예: "미국 (USA)" → "미국")
        if "(" in name:
            name = name.split("(")[0].strip()
        
        if name in Config.COUNTRY_MAP:
            return Config.COUNTRY_MAP[name]
        
        name_upper = name.upper()
        mapping = {
            "UNITED STATES": "US", "USA": "US", "US": "US", "미국": "US",
            "JAPAN": "JP", "JP": "JP", "일본": "JP",
            "VIETNAM": "VN", "VN": "VN", "베트남": "VN",
        }
        
        if name_upper in mapping:
            return mapping[name_upper]
        
        raise ValueError(f"지원하지 않는 국가: {name}")
    
    @staticmethod
    def load_country_info_json(country_code: str) -> List[Dict]:
        """country_info JSON 파일 로드 및 파싱/ json 파일 구조가 복잡해서 다양한 형식 로드 및 파싱 가능하도록 설계"""
        path = os.path.join(Config.DATA_DIR, "country_info", f"country_info_{country_code}.json")
        
        if not os.path.exists(path):
            logger.warning(f"국가정보 JSON 없음: {path}")
            return []
        
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            
            # 리스트 형태면 그대로 반환
            if isinstance(data, list):
                return data
            
            # "chunks" 키가 있으면 반환
            if "chunks" in data:
                return data["chunks"]
            
            # 객체 형태면 섹션별로 파싱
            if isinstance(data, dict):
                chunks = []
                
                for section_key, section_data in data.items():
                    if not isinstance(section_data, dict):
                        continue
                    
                    # pages 배열이 있는 경우
                    if "pages" in section_data:
                        for page in section_data["pages"]:
                            if "text" in page:
                                chunks.append({
                                    "text": page["text"],
                                    "section": section_key,
                                    "page": page.get("page"),
                                    "has_table": bool(page.get("tables")),
                                    "has_image": bool(page.get("images")),
                                    "year": 2024
                                })
                    
                    # 직접 text가 있는 경우
                    elif "text" in section_data:
                        chunks.append({
                            "text": section_data["text"],
                            "section": section_key,
                            "year": section_data.get("year", 2024)
                        })
                
                logger.info(f"✓ {country_code} JSON 파싱 완료: {len(chunks)}개 청크")
                return chunks
            
            return []
            
        except Exception as e:
            logger.error(f"JSON 로드 실패 ({path}): {e}", exc_info=True)
            return []
    
    @staticmethod
    def load_table_image_index() -> Dict:
        """표/이미지 인덱스 로드"""
        path = os.path.join(Config.DATA_DIR, "table_image_index.json")
        
        if not os.path.exists(path):
            return {}
        
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except:
            return {}
    
    @staticmethod
    def load_regulation_csv() -> List[Dict]:
        """regulation.csv 로드"""
        path = os.path.join(Config.DATA_DIR, "regulation.csv")
        
        if not os.path.exists(path):
            logger.warning("regulation.csv 없음")
            return []
        
        try:
            with open(path, "r", encoding="utf-8-sig") as f:
                reader = csv.DictReader(f)
                return list(reader)
        except Exception as e:
            logger.error(f"CSV 로드 실패: {e}")
            return []
    
    @staticmethod
    def process_country_json(country_code: str) -> List[Document]:
        """country_info JSON을 Document로 변환"""
        items = DataLoader.load_country_info_json(country_code)
        docs = []
        
        rule = get_chunking_rule(f"country_info_{country_code}")
        
        for item in items:
            text = item.get("text") or item.get("content") or ""
            if not text.strip():
                continue
            
            chunks = DataLoader._chunk_text(text, rule["chunk_size"], rule["chunk_overlap"])
            
            for i, chunk in enumerate(chunks):
                docs.append(Document(
                    page_content=chunk,
                    metadata={
                        "country_code": country_code,
                        "source": "country_info",
                        "source_type": "json",
                        "file_name": f"country_info_{country_code}.json",
                        "section": item.get("section", ""),
                        "has_table": item.get("has_table", False),
                        "has_image": item.get("has_image", False),
                        "chunk_index": i,
                        "year": item.get("year"),
                    }
                ))
        
        logger.info(f"country_info_{country_code}: {len(docs)}개 문서 생성")
        return docs
    
    @staticmethod
    def process_pdf(pdf_path: str) -> List[Document]:
        """단일 PDF를 Document로 변환"""
        if not os.path.exists(pdf_path):
            return []
        
        fname = os.path.basename(pdf_path)
        rule = get_chunking_rule(fname)
        
        country = DataLoader._infer_country(fname)
        year = DataLoader._infer_year(fname)
        source = DataLoader._infer_source(pdf_path)
        
        pages = DataLoader._extract_pdf_pages(pdf_path)
        if not pages:
            return []
        
        chunks = DataLoader._chunk_pages(pages, rule["chunk_size"], rule["chunk_overlap"])
        
        docs = []
        for text, page_start, page_end in chunks:
            docs.append(Document(
                page_content=text,
                metadata={
                    "country_code": country,
                    "source": source,
                    "source_type": "pdf",
                    "file_name": fname,
                    "page_start": page_start + 1,
                    "page_end": page_end + 1,
                    "year": year,
                    "citation": f"[{fname}, p.{page_start+1}-{page_end+1}]",
                }
            ))
        
        logger.info(f"{fname}: {len(docs)}개 청크 생성")
        return docs
    
    @staticmethod
    def process_all_pdfs(folder: str) -> List[Document]:
        """폴더 내 모든 PDF 처리"""
        docs = []
        
        if not os.path.exists(folder):
            return docs
        
        for fname in os.listdir(folder):
            if fname.lower().endswith(".pdf"):
                pdf_path = os.path.join(folder, fname)
                docs.extend(DataLoader.process_pdf(pdf_path))
        
        return docs
    
    @staticmethod
    def _extract_pdf_pages(pdf_path: str) -> List[str]:
        """PDF 페이지별 텍스트 추출"""
        try:
            doc = fitz.open(pdf_path)
            pages = [page.get_text("text").strip() for page in doc]
            doc.close()
            return pages
        except Exception as e:
            logger.error(f"PDF 추출 실패: {e}")
            return []
    
    @staticmethod
    def _chunk_text(text: str, chunk_size: int, chunk_overlap: int) -> List[str]:
        """텍스트 청킹"""
        if len(text) <= chunk_size:
            return [text]
        
        chunks = []
        start = 0
        
        while start < len(text):
            end = start + chunk_size
            chunk = text[start:end]
            if chunk.strip():
                chunks.append(chunk.strip())
            start = end - chunk_overlap
        
        return chunks
    
    @staticmethod
    def _chunk_pages(pages: List[str], chunk_size: int, chunk_overlap: int) -> List[Tuple[str, int, int]]:
        """페이지 리스트 청킹"""
        chunks = []
        current_text = ""
        start_page = 0
        
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
                overlap_text = current_text[-chunk_overlap:] if chunk_overlap > 0 else ""
                current_text = overlap_text + "\n" + page
                start_page = max(i - 1, 0)
        
        if current_text.strip():
            chunks.append((current_text.strip(), start_page, len(pages) - 1))
        
        return chunks
    
    @staticmethod
    def _infer_country(fname: str) -> Optional[str]:
        """파일명에서 국가 추출"""
        upper = fname.upper()
        if "_US" in upper or "US." in upper:
            return "US"
        if "_JP" in upper or "JP." in upper:
            return "JP"
        if "_VN" in upper or "VN." in upper:
            return "VN"
        return None
    
    @staticmethod
    def _infer_year(fname: str) -> Optional[int]:
        """파일명에서 연도 추출"""
        m = re.search(r"(202[0-9])", fname)
        return int(m.group(1)) if m else None
    
    @staticmethod
    def _infer_source(path: str) -> str:
        """경로에서 소스 추출"""
        lower = path.lower()
        if "kati" in lower:
            return "kati"
        if "kotra" in lower:
            return "kotra"
        return "pdf"


class Supervisor:
    """Supervisor - 품질 평가 및 의사결정 (로깅 통합)"""
    
    def __init__(self, research_logger=None):
        self.logger = research_logger
        self.llm = ChatOpenAI(model=Config.MODEL_SMART, temperature=0)
        self.quality_threshold = 70
    
    def evaluate_content(self, content: str, source_type: str, metadata: Dict) -> Dict:
        """콘텐츠 품질 평가"""
        if not content or len(content.strip()) < 50:
            return {
                "score": 0,
                "grade": "F",
                "passed": False,
                "reasons": ["내용이 너무 짧음"],
                "scores": {},
                "citation": ""
            }
        
        scores = {}
        reasons = []
        
        # 1. 길이 (20점)
        length = len(content)
        if length >= 500:
            scores["length"] = 20
        elif length >= 300:
            scores["length"] = 15
        elif length >= 100:
            scores["length"] = 10
        else:
            scores["length"] = 5
            reasons.append("내용 길이 부족")
        
        # 2. 수치/통계 (25점)
        numbers = re.findall(r"\d+[,.]?\d*%?", content)
        if len(numbers) >= 5:
            scores["statistics"] = 25
        elif len(numbers) >= 3:
            scores["statistics"] = 20
        elif len(numbers) >= 1:
            scores["statistics"] = 10
        else:
            scores["statistics"] = 0
            reasons.append("구체적 수치 부족")
        
        # 3. 출처 신뢰도 (25점)
        if source_type == "json":
            scores["source_trust"] = 25
        elif source_type == "pdf":
            source = metadata.get("source", "")
            if source in ["kati", "kotra"]:
                scores["source_trust"] = 23
            else:
                scores["source_trust"] = 15
        elif source_type == "web":
            url = metadata.get("url", "")
            if any(d in url for d in Config.PUBLIC_DOMAINS):
                scores["source_trust"] = 20
            else:
                scores["source_trust"] = 5
                reasons.append("비공공기관 출처")
        else:
            scores["source_trust"] = 10
        
        # 4. 최신성 (15점)
        year = metadata.get("year")
        if year:
            if year >= 2024:
                scores["recency"] = 15
            elif year >= 2023:
                scores["recency"] = 12
            elif year >= 2022:
                scores["recency"] = 8
            else:
                scores["recency"] = 3
                reasons.append("오래된 자료")
        else:
            scores["recency"] = 5
        
        # 5. 관련성 (15점)
        keywords = ["시장", "수출", "수입", "규제", "가격", "성장", "전망", "동향"]
        keyword_count = sum(1 for kw in keywords if kw in content)
        scores["relevance"] = min(keyword_count * 2, 15)
        
        total = sum(scores.values())
        
        if total >= 90:
            grade = "A"
        elif total >= 80:
            grade = "B"
        elif total >= 70:
            grade = "C"
        elif total >= 50:
            grade = "D"
        else:
            grade = "F"
        
        citation = self._generate_citation(metadata)
        
        return {
            "score": total,
            "grade": grade,
            "passed": total >= self.quality_threshold,
            "reasons": reasons,
            "scores": scores,
            "citation": citation
        }
    
    def _generate_citation(self, metadata: Dict) -> str:
        """출처 문자열 생성"""
        source = metadata.get("source", "")
        file_name = metadata.get("file_name", "")
        page_start = metadata.get("page_start", "")
        page_end = metadata.get("page_end", "")
        year = metadata.get("year", "")
        url = metadata.get("url", "")
        
        if url:
            return f"[웹: {url}]"
        elif file_name:
            if page_start and page_end:
                return f"[{file_name}, p.{page_start}-{page_end}]"
            return f"[{file_name}]"
        elif source:
            return f"[{source.upper()}, {year}]"
        return "[출처 불명]"
    
    def compare_with_source(self, draft_text: str, source_docs: List[Document]) -> Dict:
        """초안과 원본 문서 비교"""
        if not source_docs:
            return {"match_rate": 0, "matched_docs": [], "unmatched_parts": [draft_text]}
        
        sentences = re.split(r'[.。]', draft_text)
        sentences = [s.strip() for s in sentences if s.strip()]
        
        matched = []
        unmatched = []
        matched_citations = []
        
        for sentence in sentences:
            found = False
            for doc in source_docs:
                words = set(re.findall(r'\w+', sentence))
                doc_words = set(re.findall(r'\w+', doc.page_content))
                
                overlap = len(words & doc_words) / max(len(words), 1)
                
                if overlap >= 0.5:
                    found = True
                    matched.append(sentence)
                    citation = self._generate_citation(doc.metadata)
                    matched_citations.append(f"{sentence} {citation}")
                    break
            
            if not found:
                unmatched.append(sentence)
        
        match_rate = len(matched) / max(len(sentences), 1) * 100
        
        return {
            "match_rate": match_rate,
            "matched_count": len(matched),
            "total_count": len(sentences),
            "matched_with_citations": matched_citations,
            "unmatched_parts": unmatched
        }
    
    async def evaluate_section_quality(self, section_name: str, content: str, sources: List) -> Dict:
        """LLM을 사용한 섹션 품질 심층 평가"""
        prompt = f"""
당신은 KOTRA 보고서 품질 검증 전문가입니다.

[평가 대상 섹션]: {section_name}

[섹션 내용]:
{content[:1500]}

[사용된 출처 수]: {len(sources)}개

[평가 기준]
1. 정확성 (25점): 구체적 수치와 사실 기반 여부
2. 완성도 (25점): 주제를 충분히 다루고 있는지
3. 논리성 (25점): 논리적 흐름과 구성
4. 신뢰성 (25점): 출처의 명확성과 최신성

[출력 형식]
정확성: [점수]/25 - [이유]
완성도: [점수]/25 - [이유]
논리성: [점수]/25 - [이유]
신뢰성: [점수]/25 - [이유]
총점: [점수]/100
등급: [A/B/C/D/F]
개선점: [구체적 개선 사항]
"""
        
        try:
            response = await self.llm.ainvoke([HumanMessage(content=prompt)])
            return self._parse_evaluation(response.content)
        except Exception as e:
            logger.error(f"품질 평가 실패: {e}")
            return {"score": 50, "grade": "C", "passed": False, "details": "평가 실패"}
    
    def _parse_evaluation(self, text: str) -> Dict:
        """LLM 평가 결과 파싱"""
        result = {"details": text}
        
        score_match = re.search(r"총점[:\s]*(\d+)", text)
        if score_match:
            result["score"] = int(score_match.group(1))
        
        grade_match = re.search(r"등급[:\s]*([A-F])", text)
        if grade_match:
            result["grade"] = grade_match.group(1)
        
        result["passed"] = result.get("score", 0) >= self.quality_threshold
        
        return result
    
    def filter_high_quality(self, contents: List[Dict]) -> List[Dict]:
        """고품질 콘텐츠만 필터링"""
        filtered = []
        
        for item in contents:
            evaluation = self.evaluate_content(
                item.get("content", ""),
                item.get("source_type", ""),
                item.get("metadata", {})
            )
            
            if evaluation["passed"]:
                item["evaluation"] = evaluation
                item["citation"] = evaluation["citation"]
                filtered.append(item)
            else:
                logger.debug(f"품질 미달로 제외: {evaluation['reasons']}")
        
        filtered.sort(key=lambda x: x.get("evaluation", {}).get("score", 0), reverse=True)
        
        return filtered