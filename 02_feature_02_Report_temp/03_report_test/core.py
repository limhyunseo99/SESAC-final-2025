import os
import json
import re
import fitz
import logging
from typing import Dict, List, Optional, Tuple
from dotenv import load_dotenv
from langchain_core.documents import Document
from langchain_openai import OpenAIEmbeddings, ChatOpenAI
from langchain_community.vectorstores import Chroma
from tenacity import retry, stop_after_attempt, wait_exponential

load_dotenv()

# 로깅 설정
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
    handlers=[
        logging.FileHandler('report_generation.log', encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


# 환경변수 검증
def validate_environment():
    required_vars = ["OPENAI_API_KEY"]
    missing = [var for var in required_vars if not os.getenv(var)]
    if missing:
        raise EnvironmentError(f"누락된 환경변수: {missing}")
    logger.info("환경변수 검증 완료")

validate_environment()


# Config 클래스
class Config:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))
    DATA_DIR = os.path.join(BASE_DIR, "data")
    VECTORDB_DIR = os.path.join(BASE_DIR, "vectordb_store")

    MODEL_DRAFT = "gpt-4o-mini"
    MODEL_FINAL = "gpt-5"

    COUNTRY_MAP = {
        "일본": "JP",
        "미국": "US",
        "베트남": "VN",
        "중국": "CN",
        "한국": "KR"
    }

    GOV_DOMAINS = {
        "JP": ["go.jp"],
        "VN": ["gov.vn"],
        "US": [".gov"],
        "CN": ["gov.cn"],
        "KR": ["go.kr"],
    }

    PUBLIC_DOMAINS = [
        "kotra.or.kr",
        "koti.re.kr",
        "kati.net",
        "customs.go.kr",
        "mafra.go.kr",
    ]

    INTL_DOMAINS = [
        "oecd.org",
        "fao.org",
        "un.org",
        "wto.org",
        "worldbank.org",
        "imf.org",
    ]


# DataLoader: PDF/JSON 로드 및 청킹
class DataLoader:

    @staticmethod
    def normalize_country(name: str) -> str:
        if not isinstance(name, str) or not name.strip():
            raise ValueError(f"유효하지 않은 국가명: {name}")
        code = Config.COUNTRY_MAP.get(name)
        if not code:
            raise ValueError(f"지원하지 않는 국가명: {name}")
        return code

    @staticmethod
    def load_country_info(country_code: str) -> Dict:
        if not re.match(r'^[A-Z]{2}$', country_code):
            logger.error(f"잘못된 국가코드 형식: {country_code}")
            return {}

        path = os.path.join(
            Config.DATA_DIR,
            "country_info",
            f"country_info_{country_code}.json"
        )

        if not os.path.exists(path):
            logger.warning(f"국가 정보 없음: {path}")
            return {}

        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            return data
        except Exception as e:
            logger.error(f"국가 정보 로드 실패: {e}")
            return {}

    @staticmethod
    def extract_pdf_text(pdf_path: str) -> str:
        if not os.path.exists(pdf_path):
            logger.error(f"PDF 파일 없음: {pdf_path}")
            return ""

        doc = None
        try:
            doc = fitz.open(pdf_path)
            pages = []
            for page in doc:
                text = page.get_text("text").strip()
                if text:
                    pages.append(text)

            return "\n\n".join(pages)
        except Exception as e:
            logger.error(f"PDF 읽기 실패: {e}")
            return ""
        finally:
            if doc:
                doc.close()

    @staticmethod
    def chunk_text(text: str, size: int, overlap: int) -> List[str]:
        if not text or not text.strip():
            return []
        if size <= 0:
            raise ValueError("chunk size는 양수여야 합니다.")
        if overlap < 0 or overlap >= size:
            raise ValueError("overlap은 0 이상이며 size보다 작아야 합니다.")

        chunks = []
        start = 0
        text_len = len(text)
        while start < text_len:
            end = min(start + size, text_len)
            chunk = text[start:end].strip()
            if chunk:
                chunks.append(chunk)
            if end >= text_len:
                break
            start = end - overlap
        return chunks

    @staticmethod
    def extract_metadata(filename: str) -> Dict:
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
            "file_name": os.path.basename(filename),
        }

    @staticmethod
    def get_chunk_rule(country: str, year: Optional[int], source: str) -> Tuple[int, int]:
        if source == "COUNTRY_INFO":
            return (700, 150) if country == "US" else (1000, 200)
        if source == "KATI":
            return (1000, 200)
        if source == "KOTRA":
            if year == 2025:
                return (1000, 200)
            if year == 2024:
                return (1000, 200) if country == "JP" else (1000, 180)
            if year == 2023:
                return (1000, 180)
        return (1000, 200)

    @classmethod
    def process_pdf(cls, pdf_path: str) -> List[Document]:
        try:
            metadata = cls.extract_metadata(pdf_path)
            text = cls.extract_pdf_text(pdf_path)
            if len(text) < 30:
                return []

            chunk_size, overlap = cls.get_chunk_rule(
                metadata["country_code"],
                metadata["year"],
                metadata["source"]
            )
            chunks = cls.chunk_text(text, chunk_size, overlap)

            docs = []
            for i, chunk in enumerate(chunks):

                # 수정사항 1: 연도 None 방지
                year_label = metadata["year"] if metadata["year"] else "N/A"

                label = (
                    f"{metadata['source']} {year_label} "
                    f"({metadata['country_code']}) · "
                    f"{metadata['file_name']} | "
                    f"chunk {i+1}/{len(chunks)}"
                )

                doc = Document(
                    page_content=chunk,
                    metadata={
                        **metadata,
                        "source_label": label,
                        "chunk_index": i,
                        "total_chunks": len(chunks),
                    }
                )
                docs.append(doc)

            return docs

        except Exception as e:
            logger.error(f"PDF 처리 실패: {e}")
            return []


    @classmethod
    def process_all_pdfs(cls, folder_path: str) -> List[Document]:
        if not os.path.exists(folder_path):
            return []
        docs = []
        for filename in os.listdir(folder_path):
            if filename.endswith(".pdf"):
                docs.extend(
                    cls.process_pdf(os.path.join(folder_path, filename))
                )
        return docs

    @classmethod
    def process_country_json(cls, country_code: str) -> List[Document]:
        try:
            data = cls.load_country_info(country_code)
            if not data:
                return []

            text = json.dumps(data, ensure_ascii=False, indent=2)
            chunk_size, overlap = cls.get_chunk_rule(country_code, None, "COUNTRY_INFO")
            chunks = cls.chunk_text(text, chunk_size, overlap)

            docs = []
            for i, chunk in enumerate(chunks):
                label = f"COUNTRY_INFO {country_code} · chunk {i+1}/{len(chunks)}"
                docs.append(
                    Document(
                        page_content=chunk,
                        metadata={
                            "source": "COUNTRY_INFO",
                            "country_code": country_code,
                            "source_label": label,
                            "chunk_index": i,
                            "total_chunks": len(chunks),
                            "file_name": f"country_info_{country_code}.json",
                        }
                    )
                )
            return docs

        except Exception as e:
            logger.error(f"국가 정보 처리 실패: {e}")
            return []


# VectorDB 클래스
class VectorDB:
    def __init__(self, persist_dir=None):
        self.persist_dir = persist_dir or Config.VECTORDB_DIR
        self.embedding = OpenAIEmbeddings(model="text-embedding-3-large")
        self.db = None

    def load(self):
        try:
            if not os.path.exists(self.persist_dir):
                os.makedirs(self.persist_dir, exist_ok=True)
            self.db = Chroma(
                persist_directory=self.persist_dir,
                embedding_function=self.embedding
            )
            logger.info(f"VectorDB 로드 완료: {self.persist_dir}")
        except Exception as e:
            logger.error(f"VectorDB 로드 실패: {e}")
            raise

    def insert(self, docs: List[Document]):
        if not docs:
            return
        if not self.db:
            self.load()

        try:
            self.db.add_documents(docs)
        except Exception as e:
            logger.error(f"문서 삽입 실패: {e}")

    def save(self):
        if self.db:
            try:
                self.db.persist()
            except Exception as e:
                logger.error(f"VectorDB 저장 실패: {e}")

    def search(self, query: str, country: str, k=5, score_threshold=0.6) -> List[Document]:
        if not self.db:
            self.load()

        try:
            results = self.db.similarity_search_with_score(
                query=query,
                k=k * 2,
                filter={"country_code": country}
            )

            filtered = []
            for doc, score in results:

                # 수정사항 2: 거리 기반 score 처리 안정화
                # Chroma score = distance (0 = 매우 유사)
                # 유사도 = 1 / (1 + distance)
                similarity = 1 / (1 + score)

                if similarity >= score_threshold:
                    filtered.append(doc)

            return filtered[:k]

        except Exception as e:
            logger.warning(f"similarity_search_with_score 오류 → fallback 사용: {e}")
            try:
                return self.db.similarity_search(
                    query=query,
                    k=k,
                    filter={"country_code": country}
                )
            except:
                return []


# Supervisor 클래스
class Supervisor:
    def __init__(self):
        self.llm = ChatOpenAI(model=Config.MODEL_DRAFT, temperature=0)
        self.table_index = self._load_table_index()

    def _load_table_index(self) -> Dict:
        try:
            meta_path = os.path.join(Config.BASE_DIR, "metadata", "table_image_index.json")
            if os.path.exists(meta_path):
                with open(meta_path, "r", encoding="utf-8") as f:
                    return json.load(f)
            return {}
        except:
            return {}

    @staticmethod
    def _extract_domain(url: str) -> str:
        match = re.search(r"https?://([^/]+)", url)
        return match.group(1).lower() if match else ""

    def validate_source(self, urls: List[str], country_code: str, source_type: str) -> Dict:
        gov_domains = Config.GOV_DOMAINS.get(country_code.upper(), [])
        valid_urls = []
        warnings = []
        scores = []
        categories = []

        for url in urls:
            if not url:
                continue

            domain = self._extract_domain(url)
            is_gov = any(domain.endswith(g) for g in gov_domains)
            is_public = any(domain.endswith(p) for p in Config.PUBLIC_DOMAINS)
            is_intl = any(domain.endswith(i) for i in Config.INTL_DOMAINS)

            if is_gov:
                score = 100
                category = "gov"
            elif is_public:
                score = 90
                category = "public"
            elif is_intl:
                score = 80
                category = "intl"
            else:
                score = 40
                category = "unknown"

            if source_type == "regulation":
                if is_gov or is_public:
                    valid_urls.append(url)
                    scores.append(score)
                    categories.append(category)
                else:
                    warnings.append(f"규제 출처 부적합: {url}")

            elif source_type == "price_risk":
                if is_gov or is_public or is_intl:
                    valid_urls.append(url)
                    scores.append(score)
                    categories.append(category)
                else:
                    warnings.append(f"신뢰도 낮은 출처: {url}")

        avg_score = sum(scores) / len(scores) if scores else 0
        grade = "High" if avg_score >= 85 else ("Medium" if avg_score >= 60 else "Low")

        return {
            "is_valid": len(valid_urls) > 0,
            "valid_urls": valid_urls,
            "warnings": warnings,
            "source_score": round(avg_score, 1),
            "categories": categories,
            "source_grade": grade,
        }

    def compute_trust_breakdown(self, analysis_type: str, country_code: str,
                                source_validation: Dict, summary_text: str) -> Dict:

        source_score = float(source_validation.get("source_score", 0.0))
        text_len = len(summary_text) if summary_text else 0
        numbers = re.findall(r"\d[\d,\.]*", summary_text) if summary_text else []
        num_count = len(numbers)

        if text_len >= 1000 and num_count >= 6:
            content_score = 90
        elif text_len >= 600 and num_count >= 4:
            content_score = 80
        elif text_len >= 300 and num_count >= 2:
            content_score = 70
        elif text_len > 0:
            content_score = 55
        else:
            content_score = 0

        if num_count >= 6:
            numeric_score = 90
        elif num_count >= 3:
            numeric_score = 80
        elif num_count >= 1:
            numeric_score = 65
        else:
            numeric_score = 0 if text_len == 0 else 40

        overall = (
            source_score * 0.5 +
            content_score * 0.3 +
            numeric_score * 0.2
        )
        grade = "High" if overall >= 85 else ("Medium" if overall >= 65 else "Low")

        return {
            "analysis_type": analysis_type,
            "country_code": country_code,
            "source_score": round(source_score, 1),
            "content_score": content_score,
            "numeric_score": numeric_score,
            "overall_score": round(overall, 1),
            "overall_grade": grade,
            "numbers_found": num_count,
        }

    def get_table_refs(self, source: str, country_code: str, year: int) -> Dict:

        # 수정사항 3: 안정적 fallback + 누락 경고
        try:
            src_block = self.table_index.get(source.upper())
            if not src_block:
                logger.warning(f"표 인덱스에 소스 없음: {source}")
                return {"tables": [], "images": []}

            country_block = src_block.get(country_code.upper())
            if not country_block:
                logger.warning(f"표 인덱스에 국가 없음: {country_code}")
                return {"tables": [], "images": []}

            year_block = country_block.get(str(year))
            if not year_block:
                logger.warning(f"표 인덱스에 연도 없음: {year}")
                return {"tables": [], "images": []}

            return {
                "tables": year_block.get("table_pages", []),
                "images": year_block.get("image_pages", [])
            }

        except Exception as e:
            logger.error(f"표 인덱스 조회 실패: {e}")
            return {"tables": [], "images": []}

    def inject_table_references(self, text: str, country_code: str, source: str, year: int) -> str:
        try:
            refs = self.get_table_refs(source, country_code, year)
            table_pages = refs.get("tables", [])

            if not table_pages:
                return text

            keywords = {
                "시장규모": table_pages[:1],
                "수출": table_pages[1:2],
                "품목": table_pages[-1:]
            }

            for keyword, pages in keywords.items():
                if keyword in text and pages:
                    pattern = f"({keyword}[^.]*?\\.)"
                    match = re.search(pattern, text)
                    if match:
                        original = match.group(1)
                        ref = f" (표 참조: p.{pages[0]})"
                        text = text.replace(original, original + ref, 1)

            return text
        except Exception as e:
            logger.error(f"표 참조 삽입 실패: {e}")
            return text

    def validate_executive_summary(self, summary_text: str) -> Dict:
        try:
            if not summary_text or not summary_text.strip():
                return {
                    "score": 0,
                    "length": 0,
                    "has_numbers": False,
                    "number_count": 0,
                    "message": "요약문이 비어있음"
                }
            
            length = len(summary_text)
            numbers = re.findall(r"\d[\d,\.]+", summary_text)
            num_count = len(numbers)
            
            score = 0
            if length >= 300:
                score += 50
            elif length >= 200:
                score += 30
            
            if num_count >= 3:
                score += 50
            elif num_count >= 1:
                score += 30
            
            return {
                "score": score,
                "length": length,
                "has_numbers": num_count > 0,
                "number_count": num_count,
                "message": "통과" if score >= 70 else "개선 필요"
            }
        except Exception as e:
            logger.error(f"Executive Summary 검증 실패: {e}")
            return {
                "score": 0,
                "length": 0,
                "has_numbers": False,
                "number_count": 0,
                "message": f"검증 오류: {e}"
            }
