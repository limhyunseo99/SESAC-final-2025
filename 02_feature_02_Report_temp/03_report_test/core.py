# core.py

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
    """필수 환경변수 검증"""
    required_vars = ["OPENAI_API_KEY"]
    missing = [var for var in required_vars if not os.getenv(var)]
    if missing:
        raise EnvironmentError(f"누락된 환경변수: {missing}")
    logger.info("환경변수 검증 완료")


validate_environment()


# Config 클래스
class Config:
    """프로젝트 전역 설정"""

    BASE_DIR = os.path.dirname(os.path.abspath(__file__))
    DATA_DIR = os.path.join(BASE_DIR, "data")
    VECTORDB_DIR = os.path.join(BASE_DIR, "vectordb_store")

    MODEL_DRAFT = "gpt-5-mini"
    MODEL_FINAL = "gpt-5"

    COUNTRY_MAP = {
        "일본": "JP",
        "미국": "US",
        "베트남": "VN",
        "한국": "KR"
    }

    GOV_DOMAINS = {
        "JP": ["go.jp"],
        "VN": ["gov.vn"],
        "US": [".gov"],
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
    """PDF, JSON 로드 및 청킹 담당"""

    @staticmethod
    def normalize_country(name: str) -> str:
        """한국어 국가명을 ISO2 코드로 변환"""
        if not isinstance(name, str) or not name.strip():
            raise ValueError(f"유효하지 않은 국가명: {name}")
        code = Config.COUNTRY_MAP.get(name)
        if not code:
            raise ValueError(f"지원하지 않는 국가명: {name}")
        return code

    @staticmethod
    def load_country_info(country_code: str) -> Dict:
        """국가별 기본 정보 JSON 로드"""
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
    def extract_pdf_pages(pdf_path: str) -> List[str]:
        """
        PDF에서 페이지별 텍스트를 리스트로 추출.
        나중에 chunk 메타데이터에 page_start/page_end를 넣기 위해 사용.
        """
        if not os.path.exists(pdf_path):
            logger.error(f"PDF 파일 없음: {pdf_path}")
            return []

        doc = None
        try:
            doc = fitz.open(pdf_path)
            pages: List[str] = []
            for page_num, page in enumerate(doc):
                try:
                    text = page.get_text("text").strip()
                    if text:
                        pages.append(text)
                    else:
                        pages.append("")  # 페이지는 유지하되 빈 문자열 저장
                except Exception as e:
                    logger.warning(f"페이지 {page_num} 텍스트 추출 실패 ({pdf_path}): {e}")
                    pages.append("")
            return pages
        except Exception as e:
            logger.error(f"PDF 읽기 실패: {e}")
            return []
        finally:
            if doc:
                doc.close()

    @staticmethod
    def extract_pdf_text(pdf_path: str) -> str:
        """
        이전 코드와의 호환성을 위한 전체 텍스트 추출 함수.
        내부적으로 extract_pdf_pages를 호출하여 이어붙인다.
        """
        pages = DataLoader.extract_pdf_pages(pdf_path)
        if not pages:
            return ""
        return "\n\n".join([p for p in pages if p.strip()])

    @staticmethod
    def chunk_text(text: str, size: int, overlap: int) -> List[str]:
        """텍스트를 일정 길이로 겹치면서 잘라 List[str] 형태로 반환"""
        if not text or not text.strip():
            return []
        if size <= 0:
            raise ValueError("chunk size는 양수여야 합니다.")
        if overlap < 0 or overlap >= size:
            raise ValueError("overlap은 0 이상이며 size보다 작아야 합니다.")

        chunks: List[str] = []
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
        """파일명에서 연도, 국가코드, 출처를 추출"""
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
        """
        문서 유형/국가/연도에 따른 청킹 규칙.
        (보고서 프로젝트에서 합의된 규칙 유지)
        """
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
        """
        PDF 파일을 페이지 단위로 읽어,
        페이지별로 청킹하여 Document 리스트로 변환.
        각 청크에는 page_start/page_end 메타데이터를 포함시켜
        나중에 (출처: 파일명 · p.X) 형태 citation에 활용할 수 있게 한다.
        """
        try:
            metadata = cls.extract_metadata(pdf_path)
            pages = cls.extract_pdf_pages(pdf_path)

            if not pages:
                logger.warning(f"PDF 페이지 텍스트 추출 실패 또는 빈 파일: {pdf_path}")
                return []

            chunk_size, overlap = cls.get_chunk_rule(
                metadata["country_code"],
                metadata["year"],
                metadata["source"]
            )

            docs: List[Document] = []

            for page_idx, page_text in enumerate(pages, start=1):  # 1부터 시작
                if not page_text or len(page_text.strip()) < 30:
                    continue
                
                page_chunks = cls.chunk_text(page_text, chunk_size, overlap)
                if not page_chunks:
                    continue

                year_label = metadata["year"] if metadata["year"] else "N/A"
                page_number = page_idx + 1  # 사람 기준 페이지 번호는 1부터

                for local_idx, chunk in enumerate(page_chunks):
                    label = (
                        f"{metadata['source']} {year_label} "
                        f"({metadata['country_code']}) · "
                        f"{metadata['file_name']} · p.{page_idx} | "  # 이미 1부터 시작
                        f"chunk {local_idx + 1}/{len(page_chunks)}"
                    )

                    doc = Document(
                        page_content=chunk,
                        metadata={
                            **metadata,
                            "source_label": label,
                            "page_start": page_number,
                            "page_end": page_number,
                            "chunk_index": local_idx,
                            "total_chunks_in_page": len(page_chunks),
                        }
                    )
                    docs.append(doc)

            return docs

        except Exception as e:
            logger.error(f"PDF 처리 실패: {e}")
            return []

    @classmethod
    def process_all_pdfs(cls, folder_path: str) -> List[Document]:
        """폴더 내 모든 PDF 파일을 처리하여 Document 리스트로 반환"""
        if not os.path.exists(folder_path):
            logger.warning(f"PDF 폴더 없음: {folder_path}")
            return []

        docs: List[Document] = []
        for filename in os.listdir(folder_path):
            if filename.endswith(".pdf"):
                pdf_path = os.path.join(folder_path, filename)
                docs.extend(cls.process_pdf(pdf_path))

        return docs

    @classmethod
    def process_country_json(cls, country_code: str) -> List[Document]:
        """
        국가별 JSON 정보(country_info)를 Document로 변환.
        (표/페이지 개념이 없으므로 page_start/page_end는 사용하지 않는다.)
        """
        try:
            data = cls.load_country_info(country_code)
            if not data:
                return []

            text = json.dumps(data, ensure_ascii=False, indent=2)
            chunk_size, overlap = cls.get_chunk_rule(country_code, None, "COUNTRY_INFO")
            chunks = cls.chunk_text(text, chunk_size, overlap)

            docs: List[Document] = []
            for i, chunk in enumerate(chunks):
                label = f"COUNTRY_INFO {country_code} · chunk {i + 1}/{len(chunks)}"
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
    """Chroma 기반 벡터 스토어 관리"""

    def __init__(self, persist_dir: Optional[str] = None):
        self.persist_dir = persist_dir or Config.VECTORDB_DIR
        self.embedding = OpenAIEmbeddings(model="text-embedding-3-large")
        self.db = None

    def load(self):
        """벡터 스토어 로드"""
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
        """Document 리스트를 벡터 스토어에 삽입"""
        if not docs:
            logger.warning("삽입할 문서가 없음")
            return
        if not self.db:
            self.load()

        try:
            self.db.add_documents(docs)
            logger.info(f"VectorDB에 {len(docs)}개 문서 추가")
        except Exception as e:
            logger.error(f"문서 삽입 실패: {e}")

    def save(self):
        """벡터 스토어 저장"""
        if self.db:
            try:
                self.db.persist()
                logger.info("VectorDB 저장 완료")
            except Exception as e:
                logger.error(f"VectorDB 저장 실패: {e}")
        else:
            logger.warning("저장할 VectorDB 인스턴스가 없음")

    def search(self, query: str, country: str, k: int = 5, score_threshold: float = 0.6):
        if not self.db:
            self.load()

        try:
            # Chroma 컬렉션의 메트릭 타입 확인
            collection_metadata = self.db._collection.metadata
            metric = collection_metadata.get("hnsw:space", "l2")
            
            results = self.db.similarity_search_with_score(
                query=query,
                k=k * 2,
                filter={"country_code": country}
            )

            filtered: List[Document] = []
            for doc, distance in results:
                try:
                    # 메트릭에 따라 유사도 계산 방식 변경
                    if metric == "cosine":
                        # cosine distance: 0(완전 유사) ~ 2(완전 반대)
                        similarity = 1 - (float(distance) / 2.0)
                    elif metric == "ip":  # inner product
                        # 정규화된 벡터라면 cosine과 동일
                        similarity = 1 - (float(distance) / 2.0)
                    else:  # l2 (유클리드 거리)
                        similarity = 1 / (1 + float(distance))
                    
                    # [0, 1] 범위로 클램핑
                    similarity = max(0.0, min(1.0, similarity))
                    
                except Exception as e:
                    logger.warning(f"유사도 계산 실패: {e}")
                    similarity = 0.0

                logger.debug(f"metric={metric}, distance={distance:.4f}, similarity={similarity:.4f}")

                if similarity >= score_threshold:
                    filtered.append(doc)

            logger.info(f"검색 완료: {len(filtered)}/{len(results)}개 문서 (threshold={score_threshold})")
            return filtered[:k]

        except Exception as e:
            logger.warning(f"검색 오류, fallback 사용: {e}")
            return self.db.similarity_search(query=query, k=k, filter={"country_code": country})


# Supervisor 클래스
class Supervisor:
    """출처 검증, 신뢰도 평가, 표/이미지 인덱스 관리"""

    def __init__(self):
        self.llm = ChatOpenAI(model=Config.MODEL_DRAFT, temperature=0)
        self.table_index = self._load_table_index()

    def _load_table_index(self) -> Dict:
        """표/이미지 인덱스 로드"""
        try:
            meta_path = os.path.join(Config.BASE_DIR, "metadata", "table_image_index.json")
            if os.path.exists(meta_path):
                with open(meta_path, "r", encoding="utf-8") as f:
                    return json.load(f)
            return {}
        except Exception as e:
            logger.error(f"table_image_index.json 로드 실패: {e}")
            return {}

    @staticmethod
    def _extract_domain(url: str) -> str:
        """URL에서 도메인 부분만 추출"""
        match = re.search(r"https?://([^/]+)", url)
        return match.group(1).lower() if match else ""

    def validate_source(self, urls: List[str], country_code: str, source_type: str) -> Dict:
        """
        검색 결과 URL 목록에 대해
        - 정부 도메인
        - 공공기관 도메인
        - 국제기구 도메인
        를 우선하는 필터링 및 점수 계산 수행
        """
        gov_domains = Config.GOV_DOMAINS.get(country_code.upper(), [])
        valid_urls: List[str] = []
        warnings: List[str] = []
        scores: List[int] = []
        categories: List[str] = []

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

        avg_score = sum(scores) / len(scores) if scores else 0.0
        grade = "High" if avg_score >= 85 else ("Medium" if avg_score >= 60 else "Low")

        return {
            "is_valid": len(valid_urls) > 0,
            "valid_urls": valid_urls,
            "warnings": warnings,
            "source_score": round(avg_score, 1),
            "categories": categories,
            "source_grade": grade,
        }

    def compute_trust_breakdown(
        self,
        analysis_type: str,
        country_code: str,
        source_validation: Dict,
        summary_text: str
    ) -> Dict:
        """
        출처 점수, 텍스트 길이, 숫자 개수를 종합하여
        overall_grade / overall_score 산출
        """
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
        """
        table_image_index.json에서
        해당 source / country / year에 해당하는
        표 페이지, 이미지 페이지 정보를 가져온다.
        """
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
        """
        본문 텍스트에서 '시장규모', '수출', '품목' 문장을 찾아
        (표 참조: p.X) 꼬리표를 1회씩 삽입.
        """
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
                if not pages:
                    continue
                if keyword not in text:
                    continue

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
        """
        Executive Summary 최소 요건(길이, 숫자 포함 여부)을 간단히 점검.
        """
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
