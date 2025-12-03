import os
import re
import json
import logging
import sys
from datetime import datetime
from typing import Dict, Tuple, List, Optional
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.colors import HexColor
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
from dateutil import parser
from PyPDF2 import PdfReader, PdfWriter

from langchain_openai import ChatOpenAI
from core import Config, Supervisor, DataLoader
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

logger = logging.getLogger(__name__)

# 표지용 고정 폰트 등록
try:
    pdfmetrics.registerFont(TTFont("Free-Regular", r"c:\USERS\KMOON\APPDATA\LOCAL\MICROSOFT\WINDOWS\FONTS\FREESENTATION-4REGULAR.TTF"))
    pdfmetrics.registerFont(TTFont("Free-Bold", r"c:\USERS\KMOON\APPDATA\LOCAL\MICROSOFT\WINDOWS\FONTS\FREESENTATION-7BOLD.TTF"))
        
    
    logger.info("표지 폰트 등록 완료")
except Exception as e:
    logger.error(f"표지 폰트 등록 실패: {e}")
    raise


class ReportGenerator:
    """
    RAG 초안 생성 → Deep Research 통합 → 최종 보고서 생성 및 PDF 출력까지 담당하는 클래스
    """

    def __init__(self):
        try:
            self.llm_draft = ChatOpenAI(model=Config.MODEL_DRAFT, temperature=0)
            self.llm_final = ChatOpenAI(model=Config.MODEL_FINAL, temperature=0)
            self.supervisor = Supervisor()
            logger.info("ReportGenerator 초기화 완료")
        except Exception as e:
            logger.error(f"ReportGenerator 초기화 실패: {e}")
            raise

        self._register_fonts()

        # 출처·신뢰도 디버깅용 내부 상태
        self._rag_sources: Optional[Dict] = None
        self._deep_result: Optional[Dict] = None

    def _register_fonts(self):
        """
        본문 PDF에 사용할 한글 폰트를 순차적으로 시도하여 등록
        """

        font_candidates = [
            {
                "name_regular": "Free-Regular",
                "name_bold": "Free-Bold",
                "path_regular": r"c:\USERS\KMOON\APPDATA\LOCAL\MICROSOFT\WINDOWS\FONTS\FREESENTATION-4REGULAR.TTF",
                "path_bold": r"c:\USERS\KMOON\APPDATA\LOCAL\MICROSOFT\WINDOWS\FONTS\FREESENTATION-7BOLD.TTF",
            },
            {
                "name_regular": "KoPubWorldBatang-Medium",
                "name_bold": "KoPubWorldBatang-Bold",
                "path_regular": r"c:\USERS\KMOON\APPDATA\LOCAL\MICROSOFT\WINDOWS\FONTS\KOPUBWORLD BATANG MEDIUM.TTF",
                "path_bold": r"c:\USERS\KMOON\APPDATA\LOCAL\MICROSOFT\WINDOWS\FONTS\KOPUBWORLD BATANG BOLD.TTF",
            },
        ]

        for cfg in font_candidates:
            if os.path.exists(cfg["path_regular"]) and os.path.exists(cfg["path_bold"]):
                try:
                    pdfmetrics.registerFont(TTFont(cfg["name_regular"], cfg["path_regular"]))
                    pdfmetrics.registerFont(TTFont(cfg["name_bold"], cfg["path_bold"]))
                    self.font_regular = cfg["name_regular"]
                    self.font_bold = cfg["name_bold"]
                    logger.info(f"본문 폰트 로드 성공: {cfg['name_regular']}, {cfg['name_bold']}")
                    return
                except Exception as e:
                    logger.warning(f"폰트 로드 실패 ({cfg['name_regular']}): {e}")
                    continue

        self.font_regular = "Helvetica"
        self.font_bold = "Helvetica-Bold"
        logger.warning("기본 폰트 사용: Helvetica")

    def set_rag_sources(self, rag_result: Dict):
        """
        RAG 검색 결과 전체를 내부 상태에 저장
        (섹션별 출처 표시 및 [DEBUG] 섹션에서 사용)
        """
        if not isinstance(rag_result, dict):
            logger.warning(f"잘못된 rag_result 타입: {type(rag_result)}")
            return
        self._rag_sources = rag_result
        logger.debug("RAG 출처 저장 완료")

    def _resolve_conflict(self, rag_info: str, deep_info: Dict, section_name: str) -> str:
        """
        RAG vs Deep Research 충돌 시 신뢰도 점수와 수치 포함 여부에 따라 선택/병합
        (여기서는 이미 'High' 등급만 deep_info로 들어오도록 상위에서 필터링)
        """

        if not isinstance(deep_info, dict):
            logger.warning(f"잘못된 deep_info 타입: {type(deep_info)}")
            return rag_info if rag_info else "해당 정보를 찾을 수 없습니다."

        deep_trust = deep_info.get("trust", {})
        deep_grade = deep_trust.get("overall_grade", "Low")
        deep_score = deep_trust.get("overall_score", 0)
        deep_content = deep_info.get("info", "")

        logger.info(f"충돌 해결 ({section_name}): Deep grade={deep_grade}, score={deep_score}")

        if deep_grade == "High" and deep_trust.get("numbers_found", 0) >= 3:
            logger.info(f"{section_name}: Deep Research 우선 (High 신뢰도 + 수치 풍부)")
            result = deep_content
            if rag_info and len(rag_info) > 50:
                result += f"\n\n[참고: RAG 기반 정보 - {rag_info[:200]}...]"
            return result

        if deep_grade == "Medium" and rag_info and len(rag_info) > 50:
            logger.info(f"{section_name}: RAG + Deep Research 병합 (Medium 신뢰도)")
            return f"{rag_info}\n\n[웹 검색 보완] {deep_content}"

        logger.info(f"{section_name}: RAG 우선 (Deep 신뢰도 부족)")
        result = rag_info if rag_info and len(rag_info) > 50 else deep_content
        return result if result else "해당 정보를 찾을 수 없습니다."

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        retry=retry_if_exception_type(Exception),
        reraise=True,
    )
    def _invoke_llm(self, llm, prompt: str) -> str:
        """
        LLM 호출용 공통 함수 (재시도 로직 포함)
        """
        response = llm.invoke(prompt)
        return response.content

    def generate_draft(self, rag_result: Dict, request: Dict) -> str:
        """
        RAG 검색 결과를 기반으로 KOTRA 스타일 초안 보고서를 생성
        - 1. 요약 및 각 섹션은 최소 400자 이상
        - 가능한 한 수치 중심, 고신뢰 출처 기반으로 작성
        """

        logger.info("Draft 생성 시작")

        try:
            country = request.get("country", "N/A")
            hs_code = request.get("hs_code", "0403901000")  # 바나나우유 예시 HS 코드
            item = request.get("item", "바나나우유")

            documents = rag_result.get("documents", [])
            if not documents:
                logger.warning("RAG 문서가 없음")

            docs_summary = "\n".join(
                f"[{i+1}] {d.get('source', 'N/A')} {d.get('year', 'N/A')} - {d.get('file_name', 'N/A')}\n"
                f"{d.get('content', '')[:300]}..."
                for i, d in enumerate(documents[:5])
            )

            country_info = json.dumps(
                rag_result.get("country_info", {}),
                ensure_ascii=False,
                indent=2,
            )

            prompt = f"""당신은 한국 공공 무역기관(KOTRA)에 소속된 수출 전략 전문 애널리스트입니다.

[입력 정보]
- 대상 국가: {country}
- HS 코드(10단위): {hs_code}
- 품목(예시): {item}
- RAG 검색 결과(요약):
{docs_summary}

- 국가 기본 정보(JSON):
{country_info}

[작성 원칙 – 매우 중요]
1) 보고서에 포함되는 내용은 반드시 위 RAG 검색 결과와 국가 정보에 실제로 등장하는 사실만 사용해야 합니다.
2) 출처가 불분명하거나, 위 자료에 근거가 없는 수치·사실·사례는 절대 추측하여 작성하지 마십시오.
3) 신뢰도가 낮거나 근거가 불명확한 일반론적 설명은 최대한 배제하고, 수치·연도·순위 등 객관적인 지표 위주로 작성하십시오.
4) 모호한 표현(“ ~ 것으로 보인다”, “ ~ 일 수 있다” 등)은 피하고, 데이터가 없으면 “자료 부족으로 특정할 수 없음”이라고 명시하십시오.
5) 문체는 KOTRA 공식 보고서 스타일의 격식 있고 분석적인 톤으로 유지하십시오.
6) 각 섹션은 최소 400자 이상이 되도록 충분히 서술하십시오.
7) 1. 요약(Executive Summary에 해당)은 최소 400자 이상으로, 핵심 수치·시장 규모·성장률·유망성에 대한 결론을 반드시 포함하십시오.

[보고서 구조 – 반드시 이 구조를 따르십시오]
## 1. 요약
- 전체 시장 규모, 최근 3~5년 추이, 성장률, 수입/수출 비중, 한국산 제품의 포지션을 요약합니다.
- 수치가 없으면 “자료 부족”을 명시하고, 확인 가능한 수치만 사용합니다.

## 2. 시장 개요
- 전체 음료 시장 및 유제품/가공유(바나나우유 포함) 시장의 구조, 주요 소비 계층, 채널(대형마트, 편의점 등), 가격대 분포 등을 최소 400자 이상으로 설명합니다.

## 3. 수출 현황
- HS 코드 {hs_code} 및 유사 품목 기준으로, 최근 연도별 수출액·수입액·한국의 점유율·경쟁국(일본, 중국, EU 등)을 최소 400자 이상으로 정리합니다.

## 4. PEST 분석
- 정치(관세, FTA 등), 경제(물가·소득 수준), 사회(소비 트렌드·건강 이슈), 기술(유통·콜드체인·포장기술) 관점에서 최소 400자 이상으로 분석합니다.

## 5. SWOT 분석
- 한국산 바나나우유(또는 유사 가공유)의 강점, 약점, 기회, 위협을 최소 400자 이상으로 정리합니다.

## 6. 진출 전략
- 진출 유망 세그먼트, 가격·채널 전략, 파트너십 전략, 리스크 관리 방안을 최소 400자 이상으로 제시합니다.

위 구조와 원칙을 모두 지키면서, 마크다운 형식으로 초안 보고서를 작성하십시오.
"""

            draft = self._invoke_llm(self.llm_draft, prompt)
            logger.info(f"Draft 생성 완료: {len(draft)}자")
            return draft

        except Exception as e:
            logger.error(f"Draft 생성 실패: {e}")
            return "# 보고서 생성 실패\n\n오류가 발생했습니다."

    def integrate_deep_research(self, draft: str, deep_result: Dict) -> str:
        """
        Deep Research 결과를 초안에 통합
        - Supervisor가 평가한 trust가 "High" 인 내용만 사용
        - Medium/Low 등급은 보고서 본문 보완에 사용하지 않음
        """

        logger.info("Deep Research 통합 시작")

        try:
            if not isinstance(deep_result, dict):
                logger.warning("deep_result가 딕셔너리가 아님")
                return draft

            self._deep_result = deep_result

            def _high_only(section_key: str) -> Dict:
                sec = deep_result.get(section_key)
                if not sec:
                    return {}
                trust = sec.get("trust", {})
                if trust.get("overall_grade") == "High":
                    return sec
                logger.info(f"{section_key}: 신뢰도 {trust.get('overall_grade')} → 본문 반영에서 제외")
                return {}

            regulation_info = self._resolve_conflict(
                rag_info=draft,
                deep_info=_high_only("regulation"),
                section_name="수입 규제",
            )

            price_info = ""
            risk_info = ""

            if "price" in deep_result:
                price_info = self._resolve_conflict(
                    rag_info="",
                    deep_info=_high_only("price"),
                    section_name="가격 추세",
                )

            if "risk" in deep_result:
                risk_info = self._resolve_conflict(
                    rag_info="",
                    deep_info=_high_only("risk"),
                    section_name="시장 리스크",
                )

            table_hints = deep_result.get("table_hints", {})
            table_hint_text = ""
            if table_hints:
                for source, info in table_hints.items():
                    pages = info.get("table_pages", [])
                    if pages:
                        table_hint_text += f"\n[{source} {info.get('latest_year', 'N/A')} 표 위치: p.{', p.'.join(map(str, pages[:3]))}]"

            trust_summary = deep_result.get("summary_trust", [])
            trust_text = "\n".join(
                f"- {t.get('type', 'N/A')}: {t.get('trust_level', 'N/A')} 신뢰도 "
                f"(검증된 출처 {t.get('valid_source_count', 0)}건)"
                for t in trust_summary
            )

            prompt = f"""당신은 KOTRA 수석 애널리스트입니다.

[기존 Draft]
{draft}

[검증된 Deep Research 결과 – High 신뢰도만 사용]
=== 수입 규제 및 인증 요건 ===
{regulation_info}
신뢰도: {deep_result.get('regulation', {}).get('trust', {}).get('overall_grade', 'N/A')}

=== 가격 추세 ===
{price_info if price_info else "N/A"}
{f"신뢰도: {deep_result.get('price', {}).get('trust', {}).get('overall_grade', 'N/A')}" if price_info else ""}

=== 시장 리스크 ===
{risk_info if risk_info else "N/A"}
{f"신뢰도: {deep_result.get('risk', {}).get('trust', {}).get('overall_grade', 'N/A')}" if risk_info else ""}

[표/이미지 참조 정보]
{table_hint_text}

[신뢰도 요약]
{trust_text}

[작업 지시 – 매우 중요]
1) 위 Deep Research 결과 중에서도 신뢰도 High 등급 정보만 적극 활용하고, Medium/Low 등급 정보는 참고만 하거나 본문에 포함하지 마십시오.
2) 수입 규제·인증·시장 리스크·가격 추세에 대해, 이미 작성된 Draft의 관련 내용을 교차 검증한 뒤, 신뢰도 High인 정보로 보완·수정하십시오.
3) 근거가 애매한 문장은 과감히 삭제하거나 “자료 부족으로 특정 어려움”이라고 명시하십시오.
4) 숫자·연도·비율 등 구체적 지표가 있는 경우, 해당 수치가 실제 검색 결과에 존재하는 값인지 다시 한 번 확인하고 반영하십시오.
5) 전체 구조(1. 요약 ~ 6. 진출 전략)는 그대로 유지하되, 각 섹션이 최소 400자 이상이 되도록 내용을 보완하십시오.
6) 이미 작성된 구조와 흐름을 크게 깨지 않는 선에서, Deep Research 결과를 자연스럽게 녹여 넣으십시오.
7) 마크다운 형식을 유지하십시오.

위 원칙을 지키면서, 보완된 전체 보고서를 마크다운 형식으로 다시 작성하십시오.
"""

            updated = self._invoke_llm(self.llm_draft, prompt)
            logger.info(f"Deep Research 통합 완료: {len(updated)}자")
            return updated

        except Exception as e:
            logger.error(f"Deep Research 통합 실패: {e}")
            return draft

    def _append_debug_sources(self, report_text: str) -> str:
        """
        테스트 단계에서 사용하는 [DEBUG] 출처·신뢰도 요약 섹션을 보고서 끝에 추가
        나중에 제거하기 쉽게 전체를 한 블록으로 추가
        """

        try:
            debug_blocks: List[str] = []

            if self._rag_sources and self._rag_sources.get("documents"):
                rag_docs = self._rag_sources["documents"]
                unique = {}
                for d in rag_docs:
                    key = (
                        d.get("source"),
                        d.get("year"),
                        d.get("file_name"),
                        d.get("page_start", "-"),
                    )
                    unique[key] = True

                rag_lines = []
                for (source, year, fname, page_start) in unique.keys():
                    rag_lines.append(
                        f"- {source or 'N/A'} / {year or 'N/A'} / {fname or 'N/A'} · p.{page_start}"
                    )

                if rag_lines:
                    debug_blocks.append("### [DEBUG] RAG 기반 문서 출처 목록")
                    debug_blocks.extend(rag_lines)

            if self._deep_result:
                deep_lines = []
                for key in ["regulation", "price", "risk"]:
                    sec = self._deep_result.get(key)
                    if not sec:
                        continue
                    trust = sec.get("trust", {})
                    urls = sec.get("urls", [])
                    deep_lines.append(
                        f"- {key} | 신뢰도 등급: {trust.get('overall_grade', 'N/A')} "
                        f"(점수: {trust.get('overall_score', 0)})"
                    )
                    for u in urls:
                        deep_lines.append(f"    · URL: {u}")

                if deep_lines:
                    debug_blocks.append("")
                    debug_blocks.append("### [DEBUG] Deep Research 웹 출처 및 신뢰도")
                    debug_blocks.extend(deep_lines)

            if not debug_blocks:
                return report_text

            debug_text = "\n".join(debug_blocks)
            return report_text + "\n\n---\n\n" + "## [DEBUG] 출처 및 신뢰도 점검용 섹션\n" + debug_text + "\n"

        except Exception as e:
            logger.error(f"디버그 섹션 생성 실패: {e}")
            return report_text

    def _build_section_citations(self) -> Dict[str, str]:
        """
        RAG 문서 메타데이터를 사용하여 섹션 단위 출처 문자열 생성
        - 현재는 보고서 전체에 동일한 출처 세트를 사용하지만,
          나중에 섹션별 매핑 로직을 추가하기 쉬운 형태로 구성
        """
        if not self._rag_sources or not self._rag_sources.get("documents"):
            return {}

        docs = self._rag_sources["documents"]
        citations = []

        for d in docs:
            file_name = d.get("file_name") or "UNKNOWN.pdf"
            page_start = d.get("page_start")
            page_end = d.get("page_end")

            if page_start is None and "page" in d:
                page_start = d.get("page")

            if page_start is None:
                page_label = "p.-"
            elif page_end and page_end != page_start:
                page_label = f"p.{page_start}-{page_end}"
            else:
                page_label = f"p.{page_start}"

            citations.append(f"{file_name} · {page_label}")

        if not citations:
            return {}

        citations = list(dict.fromkeys(citations))  # 중복 제거, 순서 유지
        citation_str = "*출처: " + ", ".join(citations)

        section_citations = {
            "## 1. 요약": citation_str,
            "## 2. 시장 개요": citation_str,
            "## 3. 수출 현황": citation_str,
            "## 4. PEST 분석": citation_str,
            "## 5. SWOT 분석": citation_str,
            "## 6. 진출 전략": citation_str,
        }
        return section_citations

    def _inject_section_citations(self, text: str) -> str:
        """
        각 섹션(## 로 시작하는 소제목)의 마지막 본문 라인 뒤에
        (출처: 파일 · p.xx) 형식의 출처를 삽입
        """
        section_citations = self._build_section_citations()
        if not section_citations:
            return text

        lines = text.split("\n")
        result_lines: List[str] = []

        current_section = None
        already_cited = set()

        for i, line in enumerate(lines):
            stripped = line.strip()
            result_lines.append(line)

            if stripped.startswith("## "):
                current_section = stripped
                continue

            is_next_section = (
                i + 1 < len(lines) and lines[i + 1].strip().startswith("## ")
            )
            is_end_of_file = i + 1 == len(lines)

            if (
                current_section
                and current_section in section_citations
                and stripped
                and (is_next_section or is_end_of_file)
                and current_section not in already_cited
                and "[DEBUG]" not in current_section
            ):
                citation = section_citations[current_section]
                result_lines.append("")
                result_lines.append(citation)
                already_cited.add(current_section)

        return "\n".join(result_lines)

    def _load_youtube_data(self, country_code: str, item_kr: str) -> List[Dict]:
        """
        youtube.csv에서 해당 국가·상품에 해당하는 검색량 데이터 로드
        - 파일이 없거나 데이터가 없으면 빈 리스트 반환
        """
        candidates = [
            os.path.join(Config.BASE_DIR, "youtube.csv"),
            os.path.join(Config.DATA_DIR, "youtube.csv"),
        ]
        csv_path = None
        for path in candidates:
            if os.path.exists(path):
                csv_path = path
                break

        if not csv_path:
            logger.warning("youtube.csv 파일을 찾을 수 없음")
            return []

        import csv

        rows = []
        try:
            with open(csv_path, "r", encoding="utf-8-sig") as f:
                reader = csv.DictReader(f)
                for r in reader:
                    if (
                        r.get("country") == country_code
                        and (r.get("name_kr") or "").strip() == item_kr
                    ):
                        mm_yy = r.get("mm-yy")
                        cnt = r.get("count")
                        if not mm_yy or not cnt:
                            continue
                        try:
                            # 다양한 형식 자동 파싱
                            dt = parser.parse(mm_yy)
                        except Exception as e:
                            logger.warning(f"날짜 파싱 실패 ({mm_yy}): {e}")
                            continue
                        try:
                            value = int(cnt)
                        except Exception:
                            logger.warning(f"count 파싱 실패: {cnt}")
                            continue
                        rows.append({"label": mm_yy, "dt": dt, "value": value})
        except Exception as e:
            logger.error(f"youtube.csv 읽기 실패: {e}")
            return []

        rows.sort(key=lambda x: x["dt"])
        return rows

    def _create_youtube_chart(self, data: List[Dict], output_path: str):
        """
        YouTube 검색량 추세를 라인 차트로 저장
        """
        if not data:
            return
    
        try:
            import matplotlib
            # 백엔드 설정은 최초 1회만
            if 'matplotlib.pyplot' not in sys.modules:
                matplotlib.use("Agg")
            
            import matplotlib.pyplot as plt
            import matplotlib.font_manager as fm

            # 한글 폰트 설정 (가능한 경우에만)
            try:
                if os.name == "nt":
                    font_path = r"C:\Windows\Fonts\malgun.ttf"
                else:
                    font_path = None
                    for cand in [
                        "/System/Library/Fonts/AppleGothic.ttf",
                        "/usr/share/fonts/truetype/nanum/NanumGothic.ttf",
                    ]:
                        if os.path.exists(cand):
                            font_path = cand
                            break
                if font_path and os.path.exists(font_path):
                    font_prop = fm.FontProperties(fname=font_path)
                    plt.rcParams["font.family"] = font_prop.get_name()
                    plt.rcParams["axes.unicode_minus"] = False
            except Exception as e:
                logger.warning(f"한글 폰트 설정 실패: {e}")

            labels = [d["label"] for d in data]
            values = [d["value"] for d in data]

            plt.figure(figsize=(6, 3))
            plt.plot(labels, values, marker="o")
            plt.title("YouTube 검색량 추세 (바나나우유)")
            plt.xlabel("월")
            plt.ylabel("검색량(건)")
            plt.grid(True, alpha=0.3)
            plt.tight_layout()

            plt.savefig(output_path, dpi=150, bbox_inches="tight")
            logger.info(f"YouTube 차트 생성 완료: {output_path}")
        except ImportError:
            logger.error("matplotlib 미설치. 'pip install matplotlib' 필요")
            return
        except Exception as e:
            logger.error(f"차트 생성 실패: {e}")
            return
        finally:
            try:
                plt.close('all')
            except:
                pass

    def finalize(self, draft: str, request: Dict) -> Tuple[str, Dict]:
        """
        최종 편집 수행 + 표 참조 태깅 + 섹션별 출처 삽입 + Executive Summary 품질 검증
        또한 YouTube SNS 트렌드 섹션을 추가(데이터가 있는 경우)
        """

        logger.info("최종 편집 시작")

        try:
            prompt = f"""당신은 KOTRA 수석 애널리스트입니다.

[보고서 초안]
{draft}

[최종 편집 요구사항 – 매우 중요]
1) '## 1. 요약' 섹션은 최소 400자 이상이 되도록 정제하고, 시장 규모·성장률·수출 현황·유망성에 관한 핵심 수치를 최소 3개 이상 포함하십시오.
2) '## 2. 시장 개요'부터 '## 6. 진출 전략'까지 각 섹션도 최소 400자 이상이 되도록 내용을 보완하십시오.
3) 이미 존재하는 구조(1. 요약 ~ 6. 진출 전략)는 유지하되, 문단 간 논리 흐름을 자연스럽게 정리하십시오.
4) 숫자·연도·비율 등은 실제 RAG/Deep Research 결과에 존재하는 값만 사용해야 하며, 데이터가 없는 경우에는 '자료 부족으로 특정 어려움'과 같이 명시하십시오.
5) 출처가 불분명하거나 신뢰도가 낮은 일반론적 표현은 과감히 삭제하십시오.
6) 문체는 한국 공공기관의 공식 시장 보고서 수준으로 전문적이되, 중소기업 담당자가 이해할 수 있도록 명료하게 작성하십시오.
7) 마크다운 형식을 유지하십시오.

위 조건을 모두 만족하도록 보고서를 최종 편집하십시오.
"""

            final_report = self._invoke_llm(self.llm_final, prompt)
            logger.info(f"LLM 최종 편집 완료: {len(final_report)}자")

            country = request.get("country", "N/A")
            country_code = DataLoader.normalize_country(country) if country != "N/A" else "US"

            final_report = self.supervisor.inject_table_references(
                text=final_report,
                country_code=country_code,
                source="KOTRA",
                year=2024,
            )

            final_report = self._inject_section_citations(final_report)

            item = request.get("item", "바나나우유")
            youtube_data = self._load_youtube_data(country_code, item)
            if youtube_data:
                os.makedirs("output", exist_ok=True)
                chart_path = os.path.join("output", f"youtube_{country_code}_{item}.png")
                self._create_youtube_chart(youtube_data, chart_path)

                summary_lines = [
                    "## 7. SNS 트렌드(YouTube)",
                    "",
                    f"- 대상 품목: {item}",
                    f"- 대상 국가 코드: {country_code}",
                    f"- 그래프 파일 경로: `{chart_path}`",
                    "",
                ]
                for d in youtube_data:
                    summary_lines.append(f"- {d['label']}: {d['value']}건")

                summary_lines.append("")
                summary_lines.append("*출처: youtube.csv (내부 수집 데이터)")

                final_report = final_report.rstrip() + "\n\n" + "\n".join(summary_lines) + "\n"

            final_report = self._append_debug_sources(final_report)

            exec_match = re.search(
                r"##\s*1.*?요약\s*\n(.*?)(?=\n##|\Z)",
                final_report,
                re.DOTALL,
            )
            exec_text = exec_match.group(1).strip() if exec_match else final_report[:400]

            validation = self.supervisor.validate_executive_summary(exec_text)
            logger.info(f"최종 편집 완료: 검증 점수={validation['score']}")

            return final_report, validation

        except Exception as e:
            logger.error(f"최종 편집 실패: {e}")
            validation = {
                "score": 0,
                "length": 0,
                "has_numbers": False,
                "number_count": 0,
                "message": f"편집 실패: {e}",
            }
            return draft, validation

    def create_enhanced_cover(self, country="미국", item="커피", output_path=None):
        """
        표지 PDF 생성 (기존 디자인 유지)
        """

        logger.info(f"표지 생성 시작: {country}, {item}")

        try:
            w, h = A4
            today = datetime.now().strftime("%Y-%m-%d")

            filename = output_path or f"{today}_{country}_{item}_보고서.pdf"
            c = canvas.Canvas(filename, pagesize=A4)

            c.setFillColor(HexColor("#FFFFFF"))
            c.rect(0, 0, w, h, fill=1, stroke=0)

            c.setFillColor(HexColor("#7DA0CA"))
            c.circle(w + 360, h * 0.55, 540, fill=1, stroke=0)

            c.setFillColor(HexColor("#052659"))
            c.circle(w * 0.70, -40, 320, fill=1, stroke=0)

            c.setFont("KoPubWorldBatang-Bold", 40)
            c.setFillColor(HexColor("#052659"))
            c.drawString(70, h - 200, f"{country} 시장 진출 전략 보고서")

            c.setFont("KoPubWorldBatang-Bold", 48)
            c.drawString(70, h - 250, datetime.now().strftime("%Y"))

            c.setFont("KoPubWorldBatang-Medium", 17)
            c.drawString(70, h - 290, "데이터 기반 해외시장 분석")

            c.setStrokeColor(HexColor("#021024"))
            c.setLineWidth(1)
            c.line(70, h - 305, 320, h - 305)

            desc = (
                "본 보고서는 국가정보·진출전략·수출데이터 기반으로 생성되었습니다.\n"
                "AI 기반 분석을 통해 시장성 평가 및 진출 전략을 제공합니다."
            )

            c.setFont("KoPubWorldBatang-Medium", 13)
            y = h - 330
            for line in desc.split("\n"):
                c.drawString(70, y, line)
                y -= 14

            c.setFillColor(HexColor("#FFFFFF"))
            c.setFont("KoPubWorldBatang-Medium", 10)
            base_y = 40

            c.drawRightString(w - 40, base_y + 20, f"발행일: {today}")
            c.drawRightString(
                w - 40, base_y + 10, "작성기관: Global Path AI – Market Intelligence Unit"
            )
            c.drawRightString(
                w - 40, base_y, "저작권: © Global Path AI. All Rights Reserved."
            )

            c.save()
            logger.info(f"표지 생성 완료: {filename}")
            return filename

        except Exception as e:
            logger.error(f"표지 생성 실패: {e}")
            raise

    def _create_body_pdf(self, body_path: str, text: str):
        """
        마크다운 형태 텍스트를 ReportLab으로 본문 PDF로 변환
        - ## 소제목은 굵은 글씨 + 파란색으로 스타일링
        """

        logger.info("본문 PDF 생성 시작")

        try:
            styles = getSampleStyleSheet()

            body_style = ParagraphStyle(
                "KoreanBody",
                parent=styles["Normal"],
                fontName=self.font_regular,
                fontSize=11,
                leading=16,
            )

            heading_style = ParagraphStyle(
                "KoreanHeading",
                parent=styles["Heading2"],
                fontName=self.font_bold,
                fontSize=14,
                leading=18,
                textColor=HexColor("#1F4E79"),
                spaceBefore=6,
                spaceAfter=6,
            )

            heading1_style = ParagraphStyle(
                "KoreanHeading1",
                parent=styles["Heading1"],
                fontName=self.font_bold,
                fontSize=16,
                leading=20,
                textColor=HexColor("#1F4E79"),
                spaceBefore=10,
                spaceAfter=8,
            )

            story = []
            lines = text.split("\n")
            for line in lines:
                try:
                    stripped = line.strip()
                    if stripped.startswith("# "):
                        story.append(
                            Paragraph(f"<b>{stripped[2:]}</b>", heading1_style)
                        )
                    elif stripped.startswith("## "):
                        story.append(
                            Paragraph(f"<b>{stripped[3:]}</b>", heading_style)
                        )
                    else:
                        if stripped:
                            story.append(Paragraph(stripped, body_style))
                    story.append(Spacer(1, 8))
                except Exception as e:
                    logger.warning(f"단락 처리 실패 (무시): {e}")
                    continue

            doc = SimpleDocTemplate(body_path, pagesize=A4)
            doc.build(story)

            logger.info(f"본문 PDF 생성 완료: {body_path}")

        except Exception as e:
            logger.error(f"본문 PDF 생성 실패: {e}")
            raise

    def export_pdf(self, markdown_text: str, output_path: str, metadata: Dict):
        """
        표지 + 본문 PDF를 생성하고 하나의 파일로 병합
        """

        logger.info("최종 PDF 생성 시작")

        try:
            os.makedirs("output", exist_ok=True)

            cover_path = "output/temp_cover.pdf"
            self.create_enhanced_cover(
                country=metadata.get("country", "N/A"),
                item=metadata.get("item", "제품"),
                output_path=cover_path,
            )

            body_path = "output/temp_body.pdf"
            self._create_body_pdf(body_path, markdown_text)

            writer = PdfWriter()

            for pdf_path in [cover_path, body_path]:
                try:
                    reader = PdfReader(pdf_path)
                    for page in reader.pages:
                        writer.add_page(page)
                except Exception as e:
                    logger.error(f"PDF 병합 실패 ({pdf_path}): {e}")
                    raise

            with open(output_path, "wb") as f:
                writer.write(f)

            logger.info(f"최종 PDF 생성 완료 → {output_path}")

            try:
                os.remove(cover_path)
                os.remove(body_path)
                logger.debug("임시 PDF 파일 정리 완료")
            except Exception as e:
                logger.warning(f"임시 파일 정리 실패: {e}")

        except Exception as e:
            logger.error(f"PDF 생성 실패: {e}")
            raise
