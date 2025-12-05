# generator.py
# 보고서 생성 및 PDF 출력
# 사용법: python generator.py input_payload.json

import os
import sys
import json
import logging
import re
from datetime import datetime
from typing import Dict, List, Tuple, Optional
from pathlib import Path

import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.font_manager as fm

from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.colors import HexColor
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Image, PageBreak
from PyPDF2 import PdfReader, PdfWriter

from config import Config

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

# 폰트 위치 
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
FONT_DIR = os.path.join(BASE_DIR, "..", "data", "font")
KOPUB_BOLD = os.path.join(FONT_DIR, "KOPUBWORLD DOTUM BOLD.TTF")
KOPUB_MEDIUM = os.path.join(FONT_DIR, "KOPUBWORLD DOTUM MEDIUM.TTF")
KOPUB_LIGHT = os.path.join(FONT_DIR, "KOPUBWORLD DOTUM LIGHT.TTF")

try:
    pdfmetrics.registerFont(TTFont("KoPubBold", KOPUB_BOLD))
    pdfmetrics.registerFont(TTFont("KoPubMedium", KOPUB_MEDIUM))
    pdfmetrics.registerFont(TTFont("KoPubLight", KOPUB_LIGHT))

    FONT_REGULAR = "KoPubMedium"
    FONT_BOLD = "KoPubBold"
    logger.info("✓ KoPub 폰트 로드 완료")

except Exception as e:
    logger.warning(f"⚠ 로컬 프로젝트 폰트 로드 실패: {e}")
    # OS 폰트 fallback
    try:
        pdfmetrics.registerFont(TTFont("Malgun", "malgun.ttf"))
        FONT_REGULAR = "Malgun"
        FONT_BOLD = "Malgun"
    except:
        # Fallback
        FONT_REGULAR = "Helvetica"
        FONT_BOLD = "Helvetica-Bold"

# Matplotlib 한글 폰트 설정
plt.rcParams['font.family'] = 'Noto Sans CJK JP'
plt.rcParams['axes.unicode_minus'] = False

# -----------------------------------------------------------------------------
# 국가 코드 매핑
# -----------------------------------------------------------------------------
COUNTRY_CODE_MAP = {
    "미국 (USA)": "US",
    "일본 (Japan)": "JP",
    "베트남 (Vietnam)": "VN",
    "미국": "US",
    "일본": "JP",
    "베트남": "VN",
    "US": "US",
    "JP": "JP",
    "VN": "VN",
}

# -----------------------------------------------------------------------------
# 그래프 생성 함수
# -----------------------------------------------------------------------------
def create_success_rate_chart(country_code: str, hs_code: str, output_dir: str) -> Optional[str]:
    """수출 유망 확률 꺾은선 그래프 생성"""
    try:
        base_dir = Path(__file__).parent
        csv_path = base_dir / "data" / f"{country_code}_success_growth_2026_최적화.csv"
        
        if not csv_path.exists():
            logger.warning(f"성공률 CSV 파일 없음: {csv_path}")
            return None
        
        df = pd.read_csv(csv_path, encoding='utf-8-sig')
        
        # 상위 10개 품목 추출
        top_items = df.head(10)
        
        fig, ax = plt.subplots(figsize=(10, 5))
        
        # 꺾은선 그래프
        x = range(len(top_items))
        y = top_items['2026성공확률(%)'].values
        labels = top_items['품목명'].values
        
        ax.plot(x, y, marker='o', linewidth=2, markersize=8, color='#3B82F6')
        ax.fill_between(x, y, alpha=0.1, color='#3B82F6')
        
        # 현재 HS코드 강조 표시
        hs_code_clean = str(hs_code).replace(".", "")
        for idx, row in top_items.iterrows():
            row_hs = str(row['HS코드']).replace(".", "")
            if row_hs == hs_code_clean or hs_code_clean in row_hs:
                ax.scatter([idx], [row['2026성공확률(%)']], color='#EF4444', s=150, zorder=5)
                ax.annotate(f"{row['2026성공확률(%)']}%", 
                           (idx, row['2026성공확률(%)']), 
                           textcoords="offset points", 
                           xytext=(0, 10),
                           ha='center',
                           fontsize=10,
                           fontweight='bold',
                           color='#EF4444')
        
        ax.set_xticks(x)
        ax.set_xticklabels([f"{l[:8]}..." if len(str(l)) > 8 else l for l in labels], 
                           rotation=45, ha='right', fontsize=8)
        ax.set_ylabel('성공확률 (%)', fontsize=10)
        ax.set_ylim(70, 100)
        ax.set_title('2026년 수출 유망 확률 (상위 10개 품목)', fontsize=12, fontweight='bold', pad=15)
        ax.grid(True, alpha=0.3)
        ax.spines['top'].set_visible(False)
        ax.spines['right'].set_visible(False)
        
        plt.tight_layout()
        chart_path = os.path.join(output_dir, 'success_chart.png')
        plt.savefig(chart_path, dpi=150, bbox_inches='tight', facecolor='white')
        plt.close()
        
        logger.info(f"✓ 수출 유망 확률 차트 생성: {chart_path}")
        return chart_path
        
    except Exception as e:
        logger.error(f"수출 유망 확률 차트 생성 실패: {e}")
        return None


def create_sns_hashtag_chart(country_code: str, hashtag: str, output_dir: str) -> Optional[str]:
    """SNS 해시태그 트렌드 꺾은선 그래프 생성"""
    try:
        if not hashtag:
            return None
            
        base_dir = Path(__file__).parent
        xlsx_path = base_dir / "data" / "sns.xlsx"
        
        if not xlsx_path.exists():
            logger.warning(f"SNS 데이터 파일 없음: {xlsx_path}")
            return None
        
        df = pd.read_excel(xlsx_path)
        
        # 해당 국가 + 해시태그 필터링
        filtered = df[(df['country'] == country_code) & (df['name_kr'] == hashtag)]
        
        if filtered.empty:
            logger.warning(f"SNS 데이터 없음: country={country_code}, hashtag={hashtag}")
            return None
        
        # 날짜순 정렬
        filtered = filtered.sort_values('mm-yy')
        
        fig, ax = plt.subplots(figsize=(10, 5))
        
        x = range(len(filtered))
        y = filtered['count'].values
        dates = pd.to_datetime(filtered['mm-yy']).dt.strftime('%Y-%m')
        
        ax.plot(x, y, marker='o', linewidth=2, markersize=8, color='#0D9488')
        ax.fill_between(x, y, alpha=0.1, color='#0D9488')
        
        # 값 표시
        for i, (xi, yi) in enumerate(zip(x, y)):
            ax.annotate(f'{yi}', (xi, yi), textcoords="offset points", 
                       xytext=(0, 8), ha='center', fontsize=9)
        
        ax.set_xticks(x)
        ax.set_xticklabels(dates, rotation=45, ha='right', fontsize=9)
        ax.set_ylabel('언급 횟수', fontsize=10)
        ax.grid(True, alpha=0.3)
        ax.spines['top'].set_visible(False)
        ax.spines['right'].set_visible(False)
        
        # 현지 해시태그 이름 표시
        local_name = filtered['name_country_ver'].iloc[0] if not filtered.empty else hashtag
        ax.set_title(f'SNS 해시태그 트렌드: #{hashtag} (#{local_name})', fontsize=12, fontweight='bold', pad=15)
        
        plt.tight_layout()
        chart_path = os.path.join(output_dir, 'sns_chart.png')
        plt.savefig(chart_path, dpi=150, bbox_inches='tight', facecolor='white')
        plt.close()
        
        logger.info(f"✓ SNS 해시태그 차트 생성: {chart_path}")
        return chart_path
        
    except Exception as e:
        logger.error(f"SNS 해시태그 차트 생성 실패: {e}")
        return None


# -----------------------------------------------------------------------------
# 추가 분석 섹션 텍스트 생성
# -----------------------------------------------------------------------------
def generate_market_risk_section(country: str) -> str:
    """시장 리스크 섹션 생성"""
    return f"""## 시장 리스크

{country} 시장 진출 시 고려해야 할 주요 리스크 요인은 다음과 같습니다.

- **환율 변동성**: 환율 변동으로 인한 수입 물가 변동이 가공식품 소비자 가격에 영향을 미칠 수 있습니다.
- **규제 변화**: 현지 규제 변화에 대한 상시 모니터링이 필요합니다 (알레르겐 표시 항목 추가 등).
- **경쟁 심화**: 대형 유통 PB와의 가격 경쟁 및 안정적 공급(납기·규격 일관성) 확보가 도전 과제입니다.
- **통관 리스크**: 통관 지연 및 서류 불비로 인한 비용 증가 리스크가 존재합니다.
- **소비 트렌드 변화**: 현지 소비자 선호도 변화에 대한 빠른 대응이 필요합니다.

"""


def generate_regulation_section(country: str) -> str:
    """규제 검토 섹션 생성"""
    return f"""## 규제 검토

{country}에서 해당 품목의 주요 규제 요건은 다음과 같습니다.

- **식품위생법**: 수입자는 수입신고서를 제출하며, 잔류농약·중금속·곰팡이독소 등 위생기준을 충족해야 합니다.
- **식품표시법**: 원재료명, 알레르겐, 내용량, 유통기한, 영양성분, 원산지, 수입자 정보를 현지 언어로 기재해야 합니다.
- **첨가물/성분**: 현지 허용 첨가물 목록 및 사용기준을 준수해야 합니다.
- **포장·환경**: 재질 표기 및 분리배출 표시 가이드라인을 확인해야 합니다.
- **인증**: HACCP, ISO 22000, FSSC 22000 등 식품안전관리 인증이 바이어 신뢰 지표로 활용됩니다.

실무 권고사항:
1. 선적 전 성분·오염물질 사전검사 실시
2. 현지어 라벨 목업의 사전 감리
3. 수입자·통관사와의 첨가물 대조표 공유
4. 초기 로트에 대한 리스크 기반 검사 대응계획 수립

"""


def generate_price_trend_section(country: str) -> str:
    """가격 추세 섹션 생성"""
    return f"""## 가격 추세

{country} 시장 내 해당 품목군의 가격 동향은 다음과 같습니다.

- **원가 압력**: 최근 2~3년간 원재료 가격 상승, 환율 변동, 물류비 증가로 점진적 인상 압력이 존재했습니다.
- **소비자 대응**: 소비자는 소용량·단가 절감 제품과 PB 대체품으로 대응하는 경향을 보입니다.
- **가격대 형성**: 표준 소포장 제품의 권장소비자가는 채널·원산지·원가에 따라 조정되며, 프리미엄·원산지 차별화 제품은 더 높은 가격대를 형성합니다.
- **채널별 차이**: 편의점 > 드럭스토어 > 슈퍼마켓 > 온라인(EC) 순으로 가격대가 형성되는 경향이 있습니다.

가격 전략 권고:
- 초기 진입 시 경쟁력 있는 가격 설정 필요
- 프리미엄 포지셔닝 시 차별화 가치 명확히 전달
- 채널별 가격 정책 수립

"""


class ReportGenerator:
    """보고서 생성기"""
    
    def __init__(self, internal_mode: bool = True):
        """
        Args:
            internal_mode: True면 문장별 출처 표시, False면 끝에만 표시
        """
        self.internal_mode = internal_mode
    
    def generate(self, payload: Dict, pipeline_result: Dict) -> Tuple[str, Dict]:
        """
        마크다운 보고서 생성
        
        Returns:
            (보고서 텍스트, 검증 정보)
        """
        try:
            final_report = pipeline_result.get("final_report", "")
            
            if not final_report:
                final_report = self._build_report_from_sections(payload, pipeline_result)
            
            # 배포 모드면 본문 출처 제거 후 끝으로 이동
            if not self.internal_mode:
                final_report = self._move_citations_to_end(
                    final_report,
                    pipeline_result.get("all_citations", [])
                )
            
            validation = {
                "sections_count": len(pipeline_result.get("sections", [])),
                "passed_count": sum(1 for s in pipeline_result.get("sections", []) if s.get("passed")),
                "citations_count": len(pipeline_result.get("all_citations", [])),
                "log_path": pipeline_result.get("log_path", "")
            }
            
            return final_report, validation
            
        except Exception as e:
            logger.error(f"보고서 생성 실패: {e}", exc_info=True)
            # 최소한의 fallback 보고서
            fallback = f"# 보고서 생성 오류\n\n오류 내용: {str(e)}"
            return fallback, {"error": str(e)}
    
    def _build_report_from_sections(self, payload: Dict, result: Dict) -> str:
        """섹션으로부터 보고서 구성"""
        sections = result.get("sections", [])
        citations = result.get("all_citations", [])
        
        parts = [
            f"# {payload.get('country', '')} {payload.get('item', '')} 시장진출 보고서",
            f"\nHS Code: {payload.get('hs_code', '')}",
            f"생성일: {datetime.now().strftime('%Y-%m-%d')}",
        ]
        
        for i, section in enumerate(sections):
            if section.get("passed"):
                title = section.get("title", f"섹션 {i+1}")
                content = section.get("content", "")
                eval_info = section.get("evaluation", {})
                grade = eval_info.get("grade", "N/A")
                score = eval_info.get("score", 0)
                
                if self.internal_mode:
                    parts.append(f"\n## {i+1}. {title} [품질: {grade}, {score}점]\n\n{content}")
                else:
                    parts.append(f"\n## {i+1}. {title}\n\n{content}")
        
        if citations:
            parts.append("\n## 참고문헌\n")
            for c in list(set(citations)):
                parts.append(f"- {c}")
        
        return "\n".join(parts)
    
    def _move_citations_to_end(self, report: str, citations: List[str]) -> str:
        """본문 출처 제거 후 끝으로 이동"""
        
        # 다양한 출처 패턴 제거
        patterns = [
            r'\s*\[[^\]]*\.(pdf|json|csv|xlsx)[^\]]*\]',  # [파일명.확장자, ...]
            r'\s*\[출처:[^\]]+\]',  # [출처: ...]
            r'\s*\[웹:[^\]]+\]',  # [웹: ...]
            r'\s*\[KATI[^\]]*\]',  # [KATI ...]
            r'\s*\[KOTRA[^\]]*\]',  # [KOTRA ...]
            r'\s*\([^)]*\.pdf[^)]*\)',  # (파일명.pdf)
            r'\s*\([^)]*https?://[^)]+\)',  # (URL)
        ]
        
        cleaned = report
        for pattern in patterns:
            cleaned = re.sub(pattern, '', cleaned, flags=re.IGNORECASE)
        
        # 연속된 공백 정리
        cleaned = re.sub(r'\n\n\n+', '\n\n', cleaned)
        cleaned = re.sub(r'  +', ' ', cleaned)
        
        # 참고문헌 섹션이 없으면 추가
        if "## 참고문헌" not in cleaned and "## 출처" not in cleaned:
            cleaned += "\n\n## 참고문헌\n\n"
            unique_citations = list(set(citations))
            if unique_citations:
                cleaned += "\n".join([f"- {c}" for c in unique_citations])
            else:
                cleaned += "- 출처 정보 없음"
        
        return cleaned
# ⬇️⬇️ pdf 생성에 관한 코드 ⬇️⬇️    
    def export_pdf(self, markdown_text: str, output_path: str, metadata: Dict) -> bool:
        """
        PDF 내보내기
        
        Args:
            markdown_text: 보고서 마크다운 텍스트
            output_path: PDF 출력 경로
            metadata: 메타데이터 (country, hs_code, market_risk, regulation, price_trend, sns_hashtag 등)
        
        Returns:
            성공 여부
        """
        try:
            # 출력 디렉토리 생성
            output_dir = os.path.dirname(output_path) or "output"
            os.makedirs(output_dir, exist_ok=True)
            
            # 국가 코드 추출
            country_raw = metadata.get("country", "")
            country_code = COUNTRY_CODE_MAP.get(country_raw, "JP")
            
            # 국가명 정리 (괄호 제거)
            country_name = country_raw.split("(")[0].strip() if "(" in country_raw else country_raw
            
            # 추가 분석 섹션을 마크다운에 추가
            enhanced_markdown = markdown_text
            
            # 참고문헌 섹션 앞에 추가 분석 섹션 삽입
            additional_sections = ""
            
            if metadata.get("market_risk", False):
                additional_sections += generate_market_risk_section(country_name)
            
            if metadata.get("regulation", False):
                additional_sections += generate_regulation_section(country_name)
            
            if metadata.get("price_trend", False):
                additional_sections += generate_price_trend_section(country_name)
            
            # 참고문헌 앞에 삽입
            if additional_sections:
                if "## 참고문헌" in enhanced_markdown:
                    enhanced_markdown = enhanced_markdown.replace(
                        "## 참고문헌",
                        f"{additional_sections}\n## 참고문헌"
                    )
                elif "## 출처" in enhanced_markdown:
                    enhanced_markdown = enhanced_markdown.replace(
                        "## 출처",
                        f"{additional_sections}\n## 출처"
                    )
                else:
                    enhanced_markdown += f"\n\n{additional_sections}"
            
            # 임시 파일 경로
            cover_path = output_path.replace(".pdf", "_cover.pdf")
            body_path = output_path.replace(".pdf", "_body.pdf")
            charts_path = output_path.replace(".pdf", "_charts.pdf")
            
            # 표지 및 본문 생성
            self._create_cover(cover_path, metadata)
            self._create_body(body_path, enhanced_markdown)
            
            # 그래프 생성 및 차트 PDF 생성
            pdf_parts = [cover_path, body_path]
            
            hs_code = metadata.get("hs_code", "")
            sns_hashtag = metadata.get("sns_hashtag", "")
            
            success_chart = create_success_rate_chart(country_code, hs_code, output_dir)
            sns_chart = create_sns_hashtag_chart(country_code, sns_hashtag, output_dir)
            
            if success_chart or sns_chart:
                self._create_charts_page(charts_path, success_chart, sns_chart)
                pdf_parts.append(charts_path)
            
            # PDF 병합
            self._merge_pdfs(pdf_parts, output_path)
            
            # 임시 파일 삭제
            temp_files = [cover_path, body_path, charts_path]
            if success_chart:
                temp_files.append(success_chart)
            if sns_chart:
                temp_files.append(sns_chart)
                
            for p in temp_files:
                if os.path.exists(p):
                    try:
                        os.remove(p)
                    except Exception as e:
                        logger.warning(f"임시 파일 삭제 실패 ({p}): {e}")
            
            logger.info(f"✓ PDF 생성 완료: {output_path}")
            return True
            
        except Exception as e:
            logger.error(f"PDF 생성 실패: {e}", exc_info=True)
            return False
    
    def _create_charts_page(self, path: str, success_chart: Optional[str], sns_chart: Optional[str]):
        """차트 페이지 생성"""
        try:
            styles = getSampleStyleSheet()
            
            chart_title_style = ParagraphStyle(
                "ChartTitle",
                parent=styles["Heading2"],
                fontName=FONT_BOLD,
                fontSize=14,
                leading=18,
                textColor=HexColor("#1e40af"),
                spaceBefore=10,
                spaceAfter=10,
                alignment=1  # 중앙 정렬
            )
            
            story = []
            
            # 수출 유망 확률 차트
            if success_chart and os.path.exists(success_chart):
                story.append(Spacer(1, 20))
                img = Image(success_chart, width=160*mm, height=80*mm)
                story.append(img)
                story.append(Spacer(1, 10))
            
            # SNS 해시태그 차트
            if sns_chart and os.path.exists(sns_chart):
                story.append(Spacer(1, 20))
                img = Image(sns_chart, width=160*mm, height=80*mm)
                story.append(img)
                story.append(Spacer(1, 10))
            
            if story:
                doc = SimpleDocTemplate(
                    path,
                    pagesize=A4,
                    leftMargin=25*mm,
                    rightMargin=25*mm,
                    topMargin=20*mm,
                    bottomMargin=20*mm
                )
                doc.build(story)
                logger.debug(f"✓ 차트 페이지 생성 완료: {path}")
            
        except Exception as e:
            logger.error(f"차트 페이지 생성 실패: {e}", exc_info=True)
            raise
    
    def _create_cover(self, path: str, metadata: Dict):
        """프리미엄 디자인 표지 생성 — 사용자가 입력한 국가/품목/HS코드 반영"""
        try:
            w, h = A4
            c = canvas.Canvas(path, pagesize=A4)

            country_raw = metadata.get("country", "")
            item = metadata.get("item", "")
            hs_code = metadata.get("hs_code", "")
            today = datetime.now().strftime("%Y-%m-%d")

            # 괄호 제거된 국가명 (미국(USA) → 미국)
            country = country_raw.split("(")[0].strip() if "(" in country_raw else country_raw

            # ----------------------
            # ① 배경 흰색
            # ----------------------
            c.setFillColor(HexColor("#FFFFFF"))
            c.rect(0, 0, w, h, fill=1, stroke=0)

            # ----------------------
            # ② 큰 원 (파란 계열)
            # ----------------------
            big_r = 540
            big_cx = w + 360
            big_cy = h * 0.55
            c.setFillColor(HexColor("#7DA0CA"))
            c.circle(big_cx, big_cy, big_r, fill=1, stroke=0)

            # ----------------------
            # ③ 작은 원 (남색)
            # ----------------------
            small_r = 320
            small_cx = w * 0.70
            small_cy = -40
            c.setFillColor(HexColor("#052659"))
            c.circle(small_cx, small_cy, small_r, fill=1, stroke=0)

            # ----------------------
            # ④ 제목 텍스트
            # ----------------------
            c.setFillColor(HexColor("#052659"))
            c.setFont(FONT_BOLD, 40)
            c.drawString(70, h - 200, f"{country} 시장 진출 전략 보고서")

            c.setFont(FONT_BOLD, 48)
            c.drawString(70, h - 250, "2025")

            c.setFont(FONT_REGULAR, 17)
            c.drawString(70, h - 290, "데이터 기반 해외시장 분석")

            # ----------------------
            # ⑤ 구분선
            # ----------------------
            c.setStrokeColor(HexColor("#021024"))
            c.setLineWidth(1)
            c.line(70, h - 305, 320, h - 305)

            # ----------------------
            # ⑥ 설명문
            # ----------------------
            desc = (
                "본 보고서는 국가정보·진출전략·수출데이터 기반으로 생성되었습니다.\n"
                "AI 기반 분석을 통해 시장성 평가 및 진출 전략을 제공합니다."
            )

            c.setFont(FONT_REGULAR, 13)
            y = h - 330
            for line in desc.split("\n"):
                c.drawString(70, y, line)
                y -= 14

            # ----------------------
            # ⑦ 주요 입력값 노출 (품목 / HS Code)
            # ----------------------
            c.setFont(FONT_BOLD, 16)
            c.drawString(70, y - 20, f"품목: {item}")
            c.drawString(70, y - 50, f"HS Code: {hs_code}")

            # ----------------------
            # ⑧ 오른쪽 아래 표기 (발행일 / 기관 / 저작권)
            # ----------------------
            c.setFillColor(HexColor("#FFFFFF"))
            c.setFont(FONT_REGULAR, 10)

            base_y = 40
            c.drawRightString(w - 40, base_y + 20, f"발행일: {today}")
            c.drawRightString(w - 40, base_y + 10, "작성기관: Global Path AI – Market Intelligence Unit")
            c.drawRightString(w - 40, base_y, "저작권: © Global Path AI. All Rights Reserved.")

            c.save()

        except Exception as e:
            logger.error(f"표지 생성 실패: {e}", exc_info=True)
            raise

    
    def _create_body(self, path: str, text: str):
        """본문 생성"""
        try:
            styles = getSampleStyleSheet()
            
            # 스타일 정의
            body_style = ParagraphStyle(
                "Body",
                parent=styles["Normal"],
                fontName=FONT_REGULAR,
                fontSize=9,
                leading=13,
                wordWrap='CJK'  # 한글 줄바꿈
            )
            
            heading1_style = ParagraphStyle(
                "Heading1",
                parent=styles["Heading1"],
                fontName=FONT_BOLD,
                fontSize=16,
                leading=20,
                textColor=HexColor("#1e40af"),
                spaceBefore=20,
                spaceAfter=10
            )
            
            heading2_style = ParagraphStyle(
                "Heading2",
                parent=styles["Heading2"],
                fontName=FONT_BOLD,
                fontSize=12,
                leading=15,
                textColor=HexColor("#1e40af"),
                spaceBefore=12,
                spaceAfter=6
            )
            
            citation_style = ParagraphStyle(
                "Citation",
                parent=styles["Normal"],
                fontName=FONT_REGULAR,
                fontSize=7,
                textColor=HexColor("#6b7280"),
                leftIndent=15
            )
            
            story = []
            
            lines = text.split("\n")
            for i, line in enumerate(lines):
                line = line.strip()
                
                if not line:
                    # 연속된 빈 줄 방지
                    if i > 0 and lines[i-1].strip():
                        story.append(Spacer(1, 4))
                    continue
                
                # HTML 특수문자 이스케이프 (더 안전하게)
                safe_line = self._escape_html(line)
                
                # 마크다운 처리
                if line.startswith("# ") and not line.startswith("## "):
                    # H1
                    story.append(Paragraph(safe_line[2:], heading1_style))
                elif line.startswith("## "):
                    # H2
                    story.append(Paragraph(safe_line[3:], heading2_style))
                elif line.startswith("- ") or line.startswith("* "):
                    # 리스트
                    story.append(Paragraph(f"• {safe_line[2:]}", citation_style))
                elif line.startswith("### "):
                    # H3 (H2와 동일하게 처리)
                    story.append(Paragraph(safe_line[4:], heading2_style))
                else:
                    # 일반 텍스트
                    story.append(Paragraph(safe_line, body_style))
            
            # PDF 생성
            doc = SimpleDocTemplate(
                path,
                pagesize=A4,
                leftMargin=50,
                rightMargin=50,
                topMargin=50,
                bottomMargin=50
            )
            doc.build(story)
            logger.debug(f"✓ 본문 생성 완료: {path}")
            
        except Exception as e:
            logger.error(f"본문 생성 실패: {e}", exc_info=True)
            raise
    
    def _escape_html(self, text: str) -> str:
        """HTML 특수문자 이스케이프"""
        # 기본 HTML 엔티티
        text = text.replace("&", "&amp;")
        text = text.replace("<", "&lt;")
        text = text.replace(">", "&gt;")
        
        # 추가 특수문자 (ReportLab에서 문제될 수 있는 것들)
        text = text.replace("'", "&apos;")
        text = text.replace('"', "&quot;")
        
        # 마크다운 강조 문법 처리
        # **bold** -> <b>bold</b>
        text = re.sub(r'\*\*([^*]+)\*\*', r'<b>\1</b>', text)
        # *italic* -> <i>italic</i>
        text = re.sub(r'\*([^*]+)\*', r'<i>\1</i>', text)
        
        return text
    
    def _merge_pdfs(self, input_paths: List[str], output_path: str):
        """PDF 병합"""
        try:
            writer = PdfWriter()
            
            for path in input_paths:
                if os.path.exists(path):
                    try:
                        reader = PdfReader(path)
                        for page in reader.pages:
                            writer.add_page(page)
                    except Exception as e:
                        logger.error(f"PDF 읽기 실패 ({path}): {e}")
                        raise
                else:
                    logger.warning(f"파일이 존재하지 않음: {path}")
            
            # 파일 쓰기
            with open(output_path, "wb") as f:
                writer.write(f)
            
            logger.debug(f"✓ PDF 병합 완료: {output_path}")
            
        except Exception as e:
            logger.error(f"PDF 병합 실패: {e}", exc_info=True)
            raise


def main():
    """CLI 실행 - subprocess에서 호출됨"""
    try:
        from pipeline import ResearchPipeline, init_vectorstore
        
        # payload 로드
        if len(sys.argv) > 1:
            payload_path = sys.argv[1]
            if not os.path.exists(payload_path):
                raise FileNotFoundError(f"Payload 파일을 찾을 수 없습니다: {payload_path}")
            
            with open(payload_path, "r", encoding="utf-8") as f:
                payload = json.load(f)
        else:
            # 개발 테스트용 기본값
            logger.warning("⚠ payload 파일이 지정되지 않았습니다. 기본값 사용")
            payload = {
                "country": "일본",
                "hs_code": "2202.99.1000",
                "item": "바나나우유",
                "options": []
            }
        
        logger.info(f"분석 시작: {payload}")
        
        # 국가 코드 정규화 추가 ⬇️
        from config import DataLoader
        
        try:
            if "country" in payload:
                original_country = payload["country"]
                payload["country"] = DataLoader.normalize_country(original_country)
                logger.info(f"✓ 국가 코드 변환: {original_country} → {payload['country']}")
        except Exception as e:
            logger.error(f"✗ 국가 코드 변환 실패: {e}")
        
        logger.info(f"최종 payload: {payload}")
        
        # 파이프라인 실행
        db = init_vectorstore()
        pipeline = ResearchPipeline(db)
        
        def progress_callback(step, msg, progress):
            logger.info(f"[{progress*100:.0f}%] {msg}")
        
        result = pipeline.run(payload, progress_callback)
        
        # 보고서 생성
        generator = ReportGenerator(internal_mode=True)
        report_text, validation = generator.generate(payload, result)
        
        # 파일명 생성: 국가코드_hscode_날짜.pdf
        country_raw = payload.get("country", "")
        country_code = COUNTRY_CODE_MAP.get(country_raw, country_raw[:2].upper() if country_raw else "XX")
        hs_code_clean = payload.get("hs_code", "000000").replace(".", "").replace(" ", "")
        today_str = datetime.now().strftime('%Y%m%d')
        
        pdf_filename = f"{country_code}_{hs_code_clean}_{today_str}.pdf"
        md_filename = f"{country_code}_{hs_code_clean}_{today_str}.md"
        
        # 마크다운 파일도 저장
        os.makedirs("output", exist_ok=True)
        md_path = f"output/{md_filename}"
        with open(md_path, "w", encoding="utf-8") as f:
            f.write(report_text)
        logger.info(f"✓ 마크다운 저장: {md_path}")
        
        # PDF 출력
        pdf_path = f"output/{pdf_filename}"
        pdf_success = generator.export_pdf(report_text, pdf_path, payload)
        
        # 결과를 JSON으로 출력 (subprocess에서 파싱)
        output_result = {
            "success": pdf_success,
            "pdf_path": pdf_path if pdf_success else None,
            "md_path": md_path,
            "log_path": result.get("log_path", ""),
            "validation": validation
        }
        
        print(json.dumps(output_result, ensure_ascii=False))
        
        return 0 if pdf_success else 1
        
    except Exception as e:
        logger.error(f"프로그램 실행 실패: {e}", exc_info=True)
        
        error_result = {
            "success": False,
            "error": str(e),
            "error_type": type(e).__name__
        }
        print(json.dumps(error_result, ensure_ascii=False))
        
        return 1


if __name__ == "__main__":
    sys.exit(main())