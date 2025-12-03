import os
import re
import json
import logging
from datetime import datetime
from typing import Dict, Tuple
from io import BytesIO

from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.colors import HexColor
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer

from PyPDF2 import PdfReader, PdfWriter

from langchain_openai import ChatOpenAI
from core import Config, Supervisor, DataLoader
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

logger = logging.getLogger(__name__)


# 전역 폰트 등록 (표지용 고정 폰트)
try:
    pdfmetrics.registerFont(
        TTFont(
            "KoPubWorldBatang-Medium",
            r"c:\USERS\KMOON\APPDATA\LOCAL\MICROSOFT\WINDOWS\FONTS\KOPUBWORLD BATANG MEDIUM.TTF",
        )
    )
    pdfmetrics.registerFont(
        TTFont(
            "KoPubWorldBatang-Bold",
            r"c:\USERS\KMOON\APPDATA\LOCAL\MICROSOFT\WINDOWS\FONTS\KOPUBWORLD BATANG BOLD.TTF",
        )
    )
    logger.info("표지 폰트 등록 완료")
except Exception as e:
    logger.error(f"표지 폰트 등록 실패: {e}")
    raise


class ReportGenerator:
    """RAG 초안 생성 → Deep Research 통합 → 최종 보고서 생성 및 PDF 출력 전체를 담당하는 클래스"""

    def __init__(self):
        # LLM 초기화
        try:
            self.llm_draft = ChatOpenAI(model=Config.MODEL_DRAFT, temperature=0)
            self.llm_final = ChatOpenAI(model=Config.MODEL_FINAL, temperature=0)
            self.supervisor = Supervisor()
            logger.info("ReportGenerator 초기화 완료")
        except Exception as e:
            logger.error(f"ReportGenerator 초기화 실패: {e}")
            raise

        # 본문 PDF에 사용할 폰트 등록
        self._register_fonts()

        # RAG / Deep Research 결과를 나중에 출처 디버그 섹션에서 활용하기 위한 내부 상태
        self._rag_sources: Dict | None = None
        self._deep_result: Dict | None = None

    def _register_fonts(self):
        """본문 PDF에서 사용할 한글 폰트를 순차적으로 시도하여 등록"""

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

        # 폰트 모두 실패 시 기본 폰트로 폴백
        self.font_regular = "Helvetica"
        self.font_bold = "Helvetica-Bold"
        logger.warning("기본 폰트 사용: Helvetica")

    def set_rag_sources(self, rag_result: Dict):
        """RAG 검색 결과를 내부 상태로 저장 (출처 디버그 섹션에서 활용)"""
        if not isinstance(rag_result, dict):
            logger.warning(f"잘못된 rag_result 타입: {type(rag_result)}")
            return
        self._rag_sources = rag_result
        logger.debug("RAG 출처 저장 완료")

    def _resolve_conflict(self, rag_info: str, deep_info: Dict, section_name: str) -> str:
        """RAG vs Deep Research 충돌 시 신뢰도 점수와 수치 포함 여부에 따라 선택/병합"""
        
        if not isinstance(deep_info, dict):
            logger.warning(f"잘못된 deep_info 타입: {type(deep_info)}")
            return rag_info if rag_info else "해당 정보를 찾을 수 없습니다."

        deep_trust = deep_info.get("trust", {})
        deep_grade = deep_trust.get("overall_grade", "Low")
        deep_score = deep_trust.get("overall_score", 0)
        deep_content = deep_info.get("info", "")

        logger.info(f"충돌 해결 ({section_name}): Deep grade={deep_grade}, score={deep_score}")

        # Deep Research가 신뢰도 High이고 수치가 충분하면 Deep 기반으로 우선
        if deep_grade == "High" and deep_trust.get("numbers_found", 0) >= 3:
            logger.info(f"{section_name}: Deep Research 우선 (High 신뢰도 + 수치 풍부)")
            result = deep_content
            if rag_info and len(rag_info) > 50:
                result += f"\n\n[참고: RAG 기반 정보 - {rag_info[:200]}...]"
            return result

        # Deep Research가 Medium이면 RAG와 병합
        elif deep_grade == "Medium" and rag_info and len(rag_info) > 50:
            logger.info(f"{section_name}: RAG + Deep Research 병합 (Medium 신뢰도)")
            return f"{rag_info}\n\n[웹 검색 보완] {deep_content}"

        # 그 외에는 RAG 우선 사용
        else:
            logger.info(f"{section_name}: RAG 우선 (Deep 신뢰도 부족)")
            result = rag_info if rag_info and len(rag_info) > 50 else deep_content
            return result if result else "해당 정보를 찾을 수 없습니다."

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        retry=retry_if_exception_type(Exception),
        reraise=True
    )
    def _invoke_llm(self, llm, prompt: str):
        """LLM 호출 with 재시도 로직"""
        try:
            response = llm.invoke(prompt)
            return response.content
        except Exception as e:
            logger.error(f"LLM 호출 실패: {e}")
            raise

    def generate_draft(self, rag_result: Dict, request: Dict) -> str:
        """RAG 검색 결과를 기반으로 KOTRA 스타일 초안 보고서를 생성"""

        logger.info("Draft 생성 시작")

        try:
            country = request.get("country", "N/A")
            hs_code = request.get("hs_code", "N/A")

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

            prompt = f""" 당신은 KOTRA 해외시장 조사 전문 애널리스트입니다.
아래의 RAG 기반 핵심 문서를 “참고자료”로 활용하되, 문장을 직접 복사하지 말고 재해석하여 작성하십시오.
모든 출력은 한국어이며, 마크다운 구조를 반드시 유지합니다.

[참고자료: RAG 추출 핵심 문서 요약]
{docs_summary}

[국가 정보]
{country_info}

작성 규칙:
1) 참고자료의 내용을 ‘인용·요약·확장 분석’ 형태로만 사용하고, 신조어/비사실 내용은 생성하지 않을 것
2) 시장규모·성장률·수입액·점유율 등 수치 기반 문장은 반드시 “출처 기반 추정” 형식으로 작성
3) 객관적·사실 기반 문체 사용 (“~으로 평가된다”, “~으로 나타난다”)
4) 각 장은 최소 300자 이상
5) Executive Summary에는 최소 3개의 정량지표 포함
6) 용어는 KOTRA 보고서의 표준 용어 사용 (시장규모, CAGR, 관세장벽, 유통구조 등)

보고서 구조:
## 1. Executive Summary
## 2. 시장 개요
## 3. 수출 현황 (HS 코드 기반)
## 4. PEST 분석
## 5. SWOT 분석
## 6. 진출 전략

주의사항:
- 주어진 자료에서만 정보를 가져오고 없는 내용을 임의로 작성하지 마세요.
- 거짓을 넣지 마세요.

위 구조에 따라 전체 초안을 생성하십시오.
"""

            draft = self._invoke_llm(self.llm_draft, prompt)
            logger.info(f"Draft 생성 완료: {len(draft)}자")
            return draft
            
        except Exception as e:
            logger.error(f"Draft 생성 실패: {e}")
            return "# 보고서 생성 실패\n\n오류가 발생했습니다."

    def integrate_deep_research(self, draft: str, deep_result: Dict) -> str:
        """Deep Research 결과를 초안에 통합하고, 신뢰도 정보와 함께 보완"""

        logger.info("Deep Research 통합 시작")

        try:
            if not isinstance(deep_result, dict):
                logger.warning("deep_result가 딕셔너리가 아님")
                return draft

            # Deep Research 결과를 내부 상태에 저장해 두고, 나중에 출처 섹션 생성에 사용
            self._deep_result = deep_result

            regulation_info = self._resolve_conflict(
                rag_info=draft,
                deep_info=deep_result.get("regulation", {}),
                section_name="수입 규제",
            )

            price_info = ""
            if "price" in deep_result:
                price_info = self._resolve_conflict(
                    rag_info="",
                    deep_info=deep_result.get("price", {}),
                    section_name="가격 추세",
                )

            risk_info = ""
            if "risk" in deep_result:
                risk_info = self._resolve_conflict(
                    rag_info="",
                    deep_info=deep_result.get("risk", {}),
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
아래 초안을 Deep Research 결과로 보완하되, 신뢰도(High/Medium/Low)에 따라 반영 강도를 조절하십시오.

[기존 Draft]
{draft}

[Deep Research 결과 - 신뢰도 포함]
(수입 규제) {regulation_info}
(가격 추세) {price_info}
(시장 리스크) {risk_info}

표·이미지 위치:
{table_hint_text}

신뢰도 반영 규칙:
1) High 등급: 본문에 적극 반영 (정량지표 우선)
2) Medium 등급: 기존 Draft를 유지하되 보조 설명으로 추가
3) Low 등급: 내용은 유지하되 단정적 표현 금지, 영향력 낮게 서술
4) 근거 없는 정보/출처 불명 URL은 절대 반영 금지

문체 규칙:
- Draft의 구조는 절대 변경하지 말 것
- KOTRA 공식 보고서의 형식·어투 준수
- 수치 기반 문장을 우선 배치
- 표 참조 정보는 “(표 참조: p.X)” 형식으로만 삽입

주의사항:
- 주어진 자료에서만 정보를 가져오고 없는 내용을 임의로 작성하지 마세요.
- 거짓을 넣지 마세요.

보완된 전체 보고서를 마크다운으로 출력하십시오.
"""

            updated = self._invoke_llm(self.llm_draft, prompt)
            logger.info(f"Deep Research 통합 완료: {len(updated)}자")
            return updated
            
        except Exception as e:
            logger.error(f"Deep Research 통합 실패: {e}")
            return draft

    def _append_debug_sources(self, report_text: str) -> str:
        """테스트 단계에서만 사용하는 출처·신뢰도 요약 디버그 섹션을 보고서 끝에 추가"""

        try:
            debug_blocks: list[str] = []

            # RAG에서 사용된 문서 출처 요약
            if self._rag_sources and self._rag_sources.get("documents"):
                rag_docs = self._rag_sources["documents"]
                unique_sources = {}
                for d in rag_docs:
                    key = (d.get("source"), d.get("year"), d.get("file_name"))
                    unique_sources[key] = True

                rag_lines = []
                for (source, year, fname) in unique_sources.keys():
                    rag_lines.append(f"- {source or 'N/A'} / {year or 'N/A'} / {fname or 'N/A'}")

                if rag_lines:
                    debug_blocks.append("### [DEBUG] RAG 기반 문서 출처 목록")
                    debug_blocks.extend(rag_lines)

            # Deep Research에서 사용한 웹 출처 및 신뢰도 요약
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
            return report_text + "\n\n\n# [DEBUG – remove before release]\n" + debug_text + "\n"
            
        except Exception as e:
            logger.error(f"디버그 섹션 생성 실패: {e}")
            return report_text

    def finalize(self, draft: str, request: Dict) -> Tuple[str, Dict]:
        """최종 편집 수행 + 표 참조 태깅 + Executive Summary 품질 검증"""

        logger.info("최종 편집 시작")

        try:
            prompt = f"""당신은 KOTRA 수석 애널리스트이며, 아래 보고서를 최종 편집하는 역할입니다.
보고서의 구조나 문장을 과도하게 변경하지 말고, 명확성·연결성·정량근거 중심으로 강화하십시오.

[편집 대상 초안]
{draft}

편집 기준:
1) Executive Summary는 300~500자로 정리하고, 정량지표 최소 3개 포함
2) 본문에서 논리적 비약, 중복 문장을 제거
3) “시장 규모”, “수입 동향”, “경쟁 구조”, “규제 요소” 등 KOTRA 표준 용어로 통일
4) 출처 기반 문장만 유지하고 확정적 어투 금지 (“확실하다” X → “가능성이 있다”)
5) 표 참조 자동 태깅을 고려하여 문장 표현을 정돈 (표 참조: p.X 유지)

주의사항:
- 주어진 자료에서만 정보를 가져오고 없는 내용을 임의로 작성하지 마세요.
- 거짓을 넣지 마세요.

최종 보고서를 마크다운 형식 그대로 출력하십시오.
"""

            final_report = self._invoke_llm(self.llm_final, prompt)
            logger.info(f"LLM 최종 편집 완료: {len(final_report)}자")

            # KOTRA/KATI 표 참조 자동 태깅
            country = request.get("country", "N/A")
            country_code = DataLoader.normalize_country(country) if country != "N/A" else "US"
            
            final_report = self.supervisor.inject_table_references(
                text=final_report,
                country_code=country_code,
                source="KOTRA",
                year=2024,
            )

            # 테스트 단계: 출처·신뢰도 디버그 섹션을 끝에 추가
            final_report = self._append_debug_sources(final_report)

            # Executive Summary 검증
            exec_match = re.search(
                r"##\s*1.*?Executive Summary\s*\n(.*?)(?=\n##|\Z)",
                final_report,
                re.DOTALL,
            )
            exec_text = exec_match.group(1).strip() if exec_match else final_report[:300]

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
                "message": f"편집 실패: {e}"
            }
            return draft, validation

    def create_enhanced_cover(self, country="미국", item="커피", output_path=None):
        """표지 PDF 생성"""

        logger.info(f"표지 생성 시작: {country}, {item}")

        try:
            w, h = A4
            today = datetime.now().strftime("%Y-%m-%d")

            filename = output_path or f"{today}_{country}_{item}_보고서.pdf"
            c = canvas.Canvas(filename, pagesize=A4)

            # 배경
            c.setFillColor(HexColor("#FFFFFF"))
            c.rect(0, 0, w, h, fill=1, stroke=0)

            # 원형 디자인
            c.setFillColor(HexColor("#7DA0CA"))
            c.circle(w + 360, h * 0.55, 540, fill=1, stroke=0)

            c.setFillColor(HexColor("#052659"))
            c.circle(w * 0.70, -40, 320, fill=1, stroke=0)

            # 제목
            c.setFont("KoPubWorldBatang-Bold", 40)
            c.setFillColor(HexColor("#052659"))
            c.drawString(70, h - 200, f"{country} 시장 진출 전략 보고서")

            c.setFont("KoPubWorldBatang-Bold", 48)
            c.drawString(70, h - 250, datetime.now().strftime("%Y"))

            c.setFont("KoPubWorldBatang-Medium", 17)
            c.drawString(70, h - 290, "데이터 기반 해외시장 분석")

            # 구분선
            c.setStrokeColor(HexColor("#021024"))
            c.setLineWidth(1)
            c.line(70, h - 305, 320, h - 305)

            # 설명
            desc = (
                "본 보고서는 국가정보·진출전략·수출데이터 기반으로 생성되었습니다.\n"
                "AI 기반 분석을 통해 시장성 평가 및 진출 전략을 제공합니다."
            )

            c.setFont("KoPubWorldBatang-Medium", 13)
            y = h - 330
            for line in desc.split("\n"):
                c.drawString(70, y, line)
                y -= 14

            # 하단 정보
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
        """마크다운 형태 텍스트를 ReportLab을 이용해 본문 PDF로 변환"""

        logger.info("본문 PDF 생성 시작")

        try:
            styles = getSampleStyleSheet()
            style = ParagraphStyle(
                "KoreanBody",
                parent=styles["Normal"],
                fontName=self.font_regular,
                fontSize=11,
                leading=16,
            )

            story = []
            for line in text.split("\n"):
                try:
                    if line.startswith("# "):
                        story.append(
                            Paragraph(f"<b><font size=16>{line[2:]}</font></b>", style)
                        )
                    elif line.startswith("## "):
                        story.append(
                            Paragraph(f"<b><font size=14>{line[3:]}</font></b>", style)
                        )
                    else:
                        if line.strip():  # 빈 줄 제외
                            story.append(Paragraph(line, style))
                    story.append(Spacer(1, 12))
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
        """표지 + 본문 PDF를 생성하고 하나의 파일로 병합"""

        logger.info("최종 PDF 생성 시작")

        try:
            os.makedirs("output", exist_ok=True)

            # 표지 생성
            cover_path = "output/temp_cover.pdf"
            self.create_enhanced_cover(
                country=metadata.get("country", "N/A"),
                item=metadata.get("item", "제품"),
                output_path=cover_path,
            )

            # 본문 생성
            body_path = "output/temp_body.pdf"
            self._create_body_pdf(body_path, markdown_text)

            # 두 PDF 병합
            writer = PdfWriter()
            
            for pdf_path in [cover_path, body_path]:
                try:
                    with open(pdf_path, "rb") as f:
                        reader = PdfReader(f)
                        for page in reader.pages:
                            writer.add_page(page)
                except Exception as e:
                    logger.error(f"PDF 병합 실패 ({pdf_path}): {e}")
                    raise

            with open(output_path, "wb") as f:
                writer.write(f)

            logger.info(f"최종 PDF 생성 완료 → {output_path}")
            
            # 임시 파일 정리
            try:
                os.remove(cover_path)
                os.remove(body_path)
                logger.debug("임시 PDF 파일 정리 완료")
            except Exception as e:
                logger.warning(f"임시 파일 정리 실패: {e}")
                
        except Exception as e:
            logger.error(f"PDF 생성 실패: {e}")
            raise