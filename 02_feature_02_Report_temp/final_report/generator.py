# generator.py (수정본)
# 보고서 생성 및 PDF 출력
# 🔧 변경사항: 하드코딩된 시장리스크/규제/가격 섹션 제거 → pipeline 결과 사용

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

# Matplotlib 한글 폰트 설정 (개선됨)
def setup_matplotlib_korean_font():
    """matplotlib 한글 폰트를 설정합니다."""
    try:
        # 사용 가능한 한글 폰트 찾기
        font_list = [f.name for f in fm.fontManager.ttflist]
        
        # 우선순위: KoPub > Noto Sans CJK > NanumGothic > Malgun Gothic
        korean_fonts = [
            'KoPubDotum', 'KoPub Dotum', 
            'Noto Sans CJK JP', 'Noto Sans CJK KR',
            'NanumGothic', 'NanumBarunGothic',
            'Malgun Gothic', 'AppleGothic'
        ]
        
        for font in korean_fonts:
            if font in font_list:
                plt.rcParams['font.family'] = font
                plt.rcParams['axes.unicode_minus'] = False
                logger.info(f"✓ Matplotlib 한글 폰트 설정: {font}")
                return font
        
        # 한글 폰트가 없으면 DejaVu Sans 사용 (경고 출력)
        plt.rcParams['font.family'] = 'DejaVu Sans'
        plt.rcParams['axes.unicode_minus'] = False
        logger.warning("⚠ 한글 폰트를 찾을 수 없습니다. 그래프에서 한글이 깨질 수 있습니다.")
        logger.warning("   해결 방법: sudo apt-get install fonts-nanum")
        return 'DejaVu Sans'
        
    except Exception as e:
        logger.error(f"폰트 설정 오류: {e}")
        plt.rcParams['font.family'] = 'DejaVu Sans'
        plt.rcParams['axes.unicode_minus'] = False
        return 'DejaVu Sans'

# 폰트 설정 실행
MATPLOTLIB_FONT = setup_matplotlib_korean_font()

# HS코드별 SNS 데이터 파일 매핑
SNS_FILE_BY_HS = {
    "2106109020": "data/sns_banana_milk.csv"
}
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
def get_success_rate_info(country_code: str, hs_code: str) -> Optional[Dict]:
    """수출 유망 확률 정보 조회 - 텍스트로 반환"""
    try:
        base_dir = Path(__file__).parent
        csv_path = base_dir / "data" / f"{country_code}_success_growth_2026_최적화.csv"
        
        if not csv_path.exists():
            logger.warning(f"성공률 CSV 파일 없음: {csv_path}")
            return None
        
        df = pd.read_csv(csv_path, encoding='utf-8-sig')
        
        # HS Code 클린징
        hs_code_clean = str(hs_code).replace(".", "").replace(" ", "")
        
        # 해당 HS Code 찾기
        df['HS코드_clean'] = df['HS코드'].astype(str).str.replace(".", "").str.replace(" ", "")
        
        # 정확히 일치하는 HS Code 찾기
        exact_match = df[df['HS코드_clean'] == hs_code_clean]
        
        if exact_match.empty:
            logger.warning(f"HS Code {hs_code}를 CSV에서 찾을 수 없습니다.")
            logger.info(f"사용 가능한 HS Code 예시: {df['HS코드'].head(10).tolist()}")
            return None
        
        # 해당 품목 정보
        target_item = exact_match.iloc[0]
        
        logger.info(f"✓ HS Code {hs_code} 발견!")
        logger.info(f"  순위: {target_item['순위']}위")
        logger.info(f"  품목명: {target_item['품목명']}")
        logger.info(f"  성공확률: {target_item['2026성공확률(%)']}%")
        
        # 딕셔너리로 정보 반환
        info = {
            '순위': int(target_item['순위']),
            '국가명': str(target_item['국가명']),
            'HS코드': str(target_item['HS코드']),
            '품목명': str(target_item['품목명']),
            '카테고리': str(target_item['카테고리']),
            '2025년수출액': float(target_item['2025년수출액($)']),
            '2026성공확률': float(target_item['2026성공확률(%)']),
            '2026성공예측': str(target_item['2026성공예측'])
        }
        
        logger.info(f"✓ 수출 유망 확률 정보 조회 완료")
        return info
        
    except Exception as e:
        logger.error(f"수출 유망 확률 정보 조회 실패: {e}", exc_info=True)
        return None
    
def load_sns_data(item: str, hs_code: str):
    """
    SNS 데이터 파일을 HS코드 기준으로 선택하여 로드한다.
    """
    # 1) HS 코드 기반 선택
    if hs_code in SNS_FILE_BY_HS:
        return pd.read_csv(SNS_FILE_BY_HS[hs_code])

    # 2) 기본값 (기존 구조 유지용)
    return pd.read_excel("data/sns.xlsx", engine="openpyxl")



def create_sns_hashtag_chart(country_code: str, hashtag: str, hs_code: str, output_dir: str) -> Optional[str]:
    """SNS 해시태그 트렌드 그래프 생성 (CSV 기반)"""

    try:
        # 해시태그가 없으면 HS코드 기반 품목 사용
        if not hashtag:
            hashtag = get_item_from_hs(hs_code)
            if not hashtag:
                logger.info("SNS 해시태그 또는 품목명이 제공되지 않아 분석 생략")
                return None
        
        # 한글 폰트 설정
        plt.rcParams['font.family'] = MATPLOTLIB_FONT
        plt.rcParams['axes.unicode_minus'] = False
        
        # ★ CSV / XLSX 자동 로드 (핵심)
        df = load_sns_data(hashtag, hs_code)
        if df is None or df.empty:
            logger.warning("SNS 데이터가 존재하지 않습니다.")
            return None
        
        # 필터링
        filtered = df[
            (df['country'].astype(str).str.upper() == country_code.upper()) & 
            (df['name_kr'] == hashtag)
        ]
        
        if filtered.empty:
            logger.warning(f"❌ 데이터 없음: {country_code} - {hashtag}")
            return None
        
        # 날짜 정렬
        filtered["mm-yy"] = pd.to_datetime(filtered["mm-yy"], errors="coerce")
        filtered = filtered.sort_values("mm-yy")
        
        # 그래프 생성
        plt.figure(figsize=(12, 6))
        plt.plot(filtered["mm-yy"], filtered["count"], marker="o", linewidth=2.5, 
                 markersize=8, color="#0D9488")
        
        plt.title(f"SNS 해시태그 트렌드: {hashtag} (국가: {country_code})", 
                  fontsize=13, fontweight="bold", pad=15)
        plt.xlabel("월", fontsize=11)
        plt.ylabel("건수", fontsize=11)
        plt.grid(True, alpha=0.3)
        plt.xticks(rotation=45)
        plt.tight_layout()
        
        # 저장
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        
        hashtag_safe = re.sub(r"[^\w\s-]", "", hashtag).strip().replace(" ", "_")
        chart_path = output_dir / f"sns_chart_{country_code}_{hashtag_safe}.png"
        
        plt.savefig(chart_path, dpi=150, bbox_inches="tight", facecolor="white")
        plt.close()
        
        return str(chart_path)

    except Exception as e:
        logger.error(f"SNS 차트 생성 실패: {e}", exc_info=True)
        return None


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
        """
        섹션으로부터 보고서 구성 (9개 항목 구조)
        
        1. 요약 (Executive Summary)
        2. 국가 및 시장 개요
        3. 시장 규모
        4. 유통 구조 (수출 유망 확률 문장 포함)
        5. 시장 리스크 (선택)
        6. 규제 검토 (선택)
        7. 가격 추세 (선택)
        8. SNS 해시태그 (선택, 시각화)
        9. 출처 (KOTRA p.X, KATI p.Y, 웹 URL)
        """
        sections = result.get("sections", [])
        citations = result.get("all_citations", [])
        
        # 국가 코드 추출
        country_raw = payload.get('country', '')
        country_code = COUNTRY_CODE_MAP.get(country_raw, country_raw[:2].upper() if country_raw else "XX")
        hs_code = payload.get('hs_code', '')
        item = payload.get('item', '제품')
        
        parts = [
            f"# {country_raw} {item} 시장진출 보고서",
            f"\n🔢 HS Code: {hs_code}",
            f"📅 생성일: {datetime.now().strftime('%Y-%m-%d')}",
            f"\n---\n"
        ]
        
        # 섹션 키별로 매핑
        section_map = {}
        for section in sections:
            if section.get("passed"):
                section_map[section.get("key")] = section
        
        # 보고서 구조에 맞는 순서 (A등급만 포함)
        section_order = [
            ("summary", "1. 요약 (Executive Summary)"),
            ("overview", "2. 국가 및 시장 개요"),
            ("market_size", "3. 시장 규모"),
            ("distribution", "4. 유통 구조"),
            ("risk", "5. 시장 리스크"),
            ("regulation", "6. 규제 검토"),
            ("price", "7. 가격 추세"),
            ("sns_hashtag", "8. SNS 해시태그"),
        ]
        
        # 유통 구조 섹션에 수출 유망 확률 추가
        success_info = get_success_rate_info(country_code, hs_code)
        
        # 각 섹션 추가
        for key, title in section_order:
            if key in section_map:
                section = section_map[key]
                content = section.get("content", "")
                eval_info = section.get("evaluation", {})
                grade = eval_info.get("grade", "N/A")
                score = eval_info.get("score", 0)
                
                # A등급만 포함 
                if grade != "C":
                    logger.warning(f"⚠️ {title}: {grade}등급 ({score}점) - 70점 미달로 제외")
                    continue
                
                parts.append(f"\n## {title}")
                
                if self.internal_mode:
                    parts.append(f"*품질: {grade}등급 ({score}점)*\n")
                
                # 유통 구조 섹션에 수출 유망 확률 추가
                if key == "distribution" and success_info:
                    success_prob = success_info['2026성공확률']
                    parts.append(f"**📊 2026년 수출 유망 확률**: {success_prob:.1f}%\n")
                
                parts.append(content)
        
        # 9. 출처 (KOTRA p.X, KATI p.Y, 웹 URL 형식)
        if citations:
            parts.append("\n## 9. 출처\n")
            
            # 출처를 KOTRA, KATI, 웹으로 분류
            kotra_sources = []
            kati_sources = []
            web_sources = []
            other_sources = []
            
            unique_citations = list(set(citations))
            for c in unique_citations:
                c_lower = c.lower()
                if "kotra" in c_lower:
                    kotra_sources.append(c)
                elif "kati" in c_lower:
                    kati_sources.append(c)
                elif "http" in c_lower or "웹" in c:
                    web_sources.append(c)
                else:
                    other_sources.append(c)
            
            # KOTRA 출처
            if kotra_sources:
                parts.append("\n### KOTRA 자료")
                for src in sorted(kotra_sources):
                    parts.append(f"- {src}")
            
            # KATI 출처
            if kati_sources:
                parts.append("\n### KATI 자료")
                for src in sorted(kati_sources):
                    parts.append(f"- {src}")
            
            # 웹 출처
            if web_sources:
                parts.append("\n### 웹 자료")
                for src in sorted(web_sources):
                    parts.append(f"- {src}")
            
            # 기타 출처
            if other_sources:
                parts.append("\n### 기타")
                for src in sorted(other_sources):
                    parts.append(f"- {src}")
        
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

    def export_pdf(self, markdown_text: str, output_path: str, metadata: Dict) -> bool:
        """
        PDF 내보내기
        
        🔧 변경: 하드코딩된 섹션 추가 로직 제거
        - 시장 리스크, 규제 검토, 가격 추세는 이제 pipeline에서 생성됨
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
            
            # 🔧 하드코딩된 추가 섹션 삽입 로직 제거됨
            # 이제 pipeline.py에서 risk, regulation, price 섹션을 생성함
            enhanced_markdown = markdown_text
            
            # 수출 유망 확률 정보 조회
            hs_code = metadata.get("hs_code", "")
            success_info = get_success_rate_info(country_code, hs_code)
            
            # success_info를 본문 시작 부분에 추가
            if success_info:
                success_text = (
                    "\n## 📊 2026년 수출 유망 확률\n\n"
                    f"**{success_info['순위']}위** | "
                    f"**{success_info['국가명']}** | "
                    f"**HS코드: {success_info['HS코드']}** | "
                    f"**품목: {success_info['품목명']}** | "
                    f"**카테고리: {success_info['카테고리']}** | "
                    f"**2025년 수출액: ${success_info['2025년수출액']:,.0f}** | "
                    f"**2026 성공확률: {success_info['2026성공확률']:.2f}%** | "
                    f"**예측: {success_info['2026성공예측']}**\n\n"
                    "---\n"
                )
                # 요약 섹션 바로 다음에 추가
                parts = enhanced_markdown.split("## 국가 및 시장 개요", 1)
                if len(parts) == 2:
                    enhanced_markdown = parts[0] + success_text + "## 국가 및 시장 개요" + parts[1]
                else:
                    # "국가 및 시장 개요"가 없으면 맨 앞에 추가
                    enhanced_markdown = success_text + enhanced_markdown
            
            # 임시 파일 경로
            cover_path = output_path.replace(".pdf", "_cover.pdf")
            body_path = output_path.replace(".pdf", "_body.pdf")
            charts_path = output_path.replace(".pdf", "_charts.pdf")
            
            # 표지 및 본문 생성
            self._create_cover(cover_path, metadata)
            self._create_body(body_path, enhanced_markdown)
            
            # 그래프 생성 및 차트 PDF 생성
            pdf_parts = [cover_path, body_path]
            
            sns_hashtag = metadata.get("sns_hashtag", "")
            
            # 디버깅 로그 추가
            logger.info(f"📊 정보 조회 시작:")
            logger.info(f"  - HS Code: {hs_code}")
            logger.info(f"  - SNS 해시태그: '{sns_hashtag}' (타입: {type(sns_hashtag)})")
            logger.info(f"  - 국가 코드: {country_code}")
            
            # SNS 해시태그가 있을 때만 차트 생성
            sns_chart = None
            if sns_hashtag and sns_hashtag.strip():
                logger.info(f"🔍 SNS 해시태그 차트 생성 시도: '{sns_hashtag}'")
                sns_chart = create_sns_hashtag_chart(country_code, sns_hashtag, hs_code, output_dir)
                if sns_chart:
                    logger.info(f"✓ SNS 차트 생성 완료: {sns_chart}")
                else:
                    logger.warning(f"⚠ SNS 차트 생성 실패 (키워드: {sns_hashtag})")
            else:
                logger.info("ℹ SNS 해시태그가 입력되지 않았습니다.")
            
            # 차트 페이지 생성 (SNS만)
            if sns_chart:
                self._create_charts_page(charts_path, None, sns_chart)
                pdf_parts.append(charts_path)
            
            # PDF 병합
            self._merge_pdfs(pdf_parts, output_path)
            
            # 임시 파일 삭제
            temp_files = [cover_path, body_path]
            if sns_chart:
                temp_files.append(sns_chart)
                temp_files.append(charts_path)
                
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
            item = metadata.get("item", "제품")  # 🔧 기본값 추가
            hs_code = metadata.get("hs_code", "")
            today = datetime.now().strftime("%Y-%m-%d")

            # 괄호 제거된 국가명 (미국(USA) → 미국)
            country = country_raw.split("(")[0].strip() if "(" in country_raw else country_raw

            # ① 배경 흰색
            c.setFillColor(HexColor("#FFFFFF"))
            c.rect(0, 0, w, h, fill=1, stroke=0)

            # ② 큰 원 (파란 계열)
            big_r = 540
            big_cx = w + 360
            big_cy = h * 0.55
            c.setFillColor(HexColor("#7DA0CA"))
            c.circle(big_cx, big_cy, big_r, fill=1, stroke=0)

            # ③ 작은 원 (남색)
            small_r = 320
            small_cx = w * 0.70
            small_cy = -40
            c.setFillColor(HexColor("#052659"))
            c.circle(small_cx, small_cy, small_r, fill=1, stroke=0)

            # ④ 제목 텍스트
            c.setFillColor(HexColor("#052659"))
            c.setFont(FONT_BOLD, 40)
            c.drawString(70, h - 200, f"{country} 시장 진출 전략 보고서")

            c.setFont(FONT_BOLD, 48)
            c.drawString(70, h - 250, "2025")

            c.setFont(FONT_REGULAR, 17)
            c.drawString(70, h - 290, "데이터 기반 해외시장 분석")

            # ⑤ 구분선
            c.setStrokeColor(HexColor("#021024"))
            c.setLineWidth(1)
            c.line(70, h - 305, 320, h - 305)

            # ⑥ 설명문
            desc = (
                "본 보고서는 국가정보·진출전략·수출데이터 기반으로 생성되었습니다.\n"
                "AI 기반 분석을 통해 시장성 평가 및 진출 전략을 제공합니다."
            )

            c.setFont(FONT_REGULAR, 13)
            y = h - 330
            for line in desc.split("\n"):
                c.drawString(70, y, line)
                y -= 14

            # ⑦ 주요 입력값 노출 (품목 / HS Code)
            c.setFont(FONT_BOLD, 16)
            c.drawString(70, y - 20, f"품목: {item}")
            c.drawString(70, y - 50, f"HS Code: {hs_code}")

            # ⑧ 오른쪽 아래 표기 (발행일 / 기관 / 저작권)
            c.setFillColor(HexColor("#FFFFFF"))
            c.setFont(FONT_REGULAR, 10)

            base_y = 40
            c.drawRightString(w - 40, base_y + 20, f"발행일: {today}")
            c.drawRightString(w - 40, base_y + 10, "작성기관: GlobalPath AI – Market Intelligence Unit")
            c.drawRightString(w - 40, base_y, "저작권: © GlobalPath AI. All Rights Reserved.")

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
        from pipeline import ResearchPipelineUpgraded, init_vectorstore
        
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
        
        # HS Code 정보 로깅
        hs_code = payload.get("hs_code", "")
        if hs_code:
            hs_code_clean = str(hs_code).replace(".", "").replace(" ", "")
            if len(hs_code_clean) == 10:
                hs_2digit = hs_code_clean[:2]
                hs_4digit = hs_code_clean[:4]
                is_beverage = hs_2digit == "22"
                
                logger.info(f"  HS Code (10자리): {hs_code_clean}")
                logger.info(f"  HS Code (2자리): {hs_2digit}")
                logger.info(f"  HS Code (4자리): {hs_4digit}")
                logger.info(f"  음료 카테고리: {'예' if is_beverage else '아니오'}")
                
                # payload에 추가 정보 저장 (pipeline에서 사용 가능)
                payload["hs_code_2digit"] = hs_2digit
                payload["hs_code_4digit"] = hs_4digit
                payload["is_beverage"] = is_beverage
        
        # 국가 코드 정규화
        from config import DataLoader
        
        try:
            if "country" in payload:
                original_country = payload["country"]
                # 🔧 country는 표시용으로 유지, country_code는 내부용
                # pipeline에서 DataLoader.normalize_country 호출함
                logger.info(f"✓ 국가: {original_country}")
        except Exception as e:
            logger.error(f"✗ 국가 코드 변환 실패: {e}")
        
        logger.info(f"최종 payload: {payload}")
        
        # 파이프라인 실행 (🔧 ResearchPipelineUpgraded 사용)
        db = init_vectorstore()
        pipeline = ResearchPipelineUpgraded(db)
        
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