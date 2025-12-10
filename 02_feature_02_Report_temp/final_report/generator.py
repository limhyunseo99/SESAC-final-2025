# generator.py (수정본 v2.1)
# 보고서 생성 및 PDF 출력
# 🔧 변경사항:
# 1. 하드코딩된 시장리스크/규제/가격 섹션 제거 → pipeline 결과 사용
# 2. 보고서 제목에서 item 제거 → HS Code 기반으로 변경
# 3. SNS 섹션 HS코드 기반 자동 선택 로직 추가
# 4. B등급(80점) 이상 섹션만 포함

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
    try:
        pdfmetrics.registerFont(TTFont("Malgun", "malgun.ttf"))
        FONT_REGULAR = "Malgun"
        FONT_BOLD = "Malgun"
    except:
        FONT_REGULAR = "Helvetica"
        FONT_BOLD = "Helvetica-Bold"

def setup_matplotlib_korean_font():
    """matplotlib 한글 폰트 설정"""
    try:
        font_list = [f.name for f in fm.fontManager.ttflist]
        korean_fonts = ['KoPubDotum', 'KoPub Dotum', 'Noto Sans CJK JP', 'Noto Sans CJK KR',
                       'NanumGothic', 'NanumBarunGothic', 'Malgun Gothic', 'AppleGothic']
        for font in korean_fonts:
            if font in font_list:
                plt.rcParams['font.family'] = font
                plt.rcParams['axes.unicode_minus'] = False
                logger.info(f"✓ Matplotlib 한글 폰트 설정: {font}")
                return font
        plt.rcParams['font.family'] = 'DejaVu Sans'
        plt.rcParams['axes.unicode_minus'] = False
        return 'DejaVu Sans'
    except Exception as e:
        logger.error(f"폰트 설정 오류: {e}")
        plt.rcParams['font.family'] = 'DejaVu Sans'
        plt.rcParams['axes.unicode_minus'] = False
        return 'DejaVu Sans'

MATPLOTLIB_FONT = setup_matplotlib_korean_font()

COUNTRY_CODE_MAP = {
    "미국 (USA)": "US", "일본 (Japan)": "JP", "베트남 (Vietnam)": "VN",
    "미국": "US", "일본": "JP", "베트남": "VN", "US": "US", "JP": "JP", "VN": "VN",
}

# 🔧 신규: HS Code → SNS 키워드 매핑
HS_TO_SNS_KEYWORD = {
    "2201": "생수", "2202": "음료", "2203": "맥주", "2204": "와인",
    "2205": "버뮤스", "2206": "사과주", "2207": "에탄올", "2208": "위스키", "2209": "식초",
    "0901": "커피", "0902": "차", "1704": "사탕", "1806": "초콜릿", "1905": "빵",
    "2106": "단백질", "0401": "우유", "0402": "분유",  # 추가
}

# 🔧 신규: 직접 키워드 매핑 (HS Code 외 추가 검색용)
DIRECT_SNS_KEYWORDS = ["바나나우유", "딸기우유", "초코우유", "와인", "맥주", "소주", "막걸리"]

def get_sns_keyword_from_hs(hs_code: str) -> Optional[str]:
    """HS Code에서 SNS 검색 키워드 추출"""
    hs_clean = re.sub(r'[.\s]', '', str(hs_code))
    for length in [4, 2]:
        prefix = hs_clean[:length]
        if prefix in HS_TO_SNS_KEYWORD:
            return HS_TO_SNS_KEYWORD[prefix]
    return None

def get_success_rate_info(country_code: str, hs_code: str) -> Optional[Dict]:
    """수출 유망 확률 정보 조회"""
    try:
        base_dir = Path(__file__).parent
        csv_path = base_dir / "data" / f"{country_code}_success_growth_2026_최적화.csv"
        if not csv_path.exists():
            logger.warning(f"성공률 CSV 파일 없음: {csv_path}")
            return None
        df = pd.read_csv(csv_path, encoding='utf-8-sig')
        hs_code_clean = str(hs_code).replace(".", "").replace(" ", "")
        df['HS코드_clean'] = df['HS코드'].astype(str).str.replace(".", "").str.replace(" ", "")
        exact_match = df[df['HS코드_clean'] == hs_code_clean]
        if exact_match.empty:
            logger.warning(f"HS Code {hs_code}를 CSV에서 찾을 수 없습니다.")
            return None
        target_item = exact_match.iloc[0]
        return {
            '순위': int(target_item['순위']),
            '국가명': str(target_item['국가명']),
            'HS코드': str(target_item['HS코드']),
            '품목명': str(target_item['품목명']),
            '카테고리': str(target_item['카테고리']),
            '2025년수출액': float(target_item['2025년수출액($)']),
            '2026성공확률': float(target_item['2026성공확률(%)']),
            '2026성공예측': str(target_item['2026성공예측'])
        }
    except Exception as e:
        logger.error(f"수출 유망 확률 정보 조회 실패: {e}", exc_info=True)
        return None

def create_sns_hashtag_chart(country_code: str, hashtag: str, output_dir: str, hs_code: str = "") -> Optional[str]:
    """🔧 개선: SNS 해시태그 트렌드 그래프 생성 - HS코드 기반 자동 선택 + CSV 지원"""
    try:
        if not hashtag or not hashtag.strip():
            if hs_code:
                hashtag = get_sns_keyword_from_hs(hs_code)
                if hashtag:
                    logger.info(f"✓ HS Code {hs_code}에서 SNS 키워드 추출: {hashtag}")
                else:
                    return None
            else:
                return None
        plt.rcParams['font.family'] = MATPLOTLIB_FONT
        plt.rcParams['axes.unicode_minus'] = False
        base_dir = Path(__file__).parent
        
        # 🔧 CSV 파일 우선 탐색 (sns_{keyword}.csv 또는 sns_{keyword}_*.csv)
        df = None
        hashtag_safe = re.sub(r'[^\w\s-]', '', hashtag).strip().replace(' ', '_')
        
        # 🔧 한글→영문 키워드 매핑 (파일명 검색용)
        KR_TO_EN_KEYWORD = {
            "바나나우유": "banana_milk", "딸기우유": "strawberry_milk", 
            "초코우유": "choco_milk", "와인": "wine", "맥주": "beer",
            "소주": "soju", "막걸리": "makgeolli", "커피": "coffee",
        }
        hashtag_en = KR_TO_EN_KEYWORD.get(hashtag, hashtag_safe)
        
        # 1) 정확한 이름의 CSV 먼저 시도 (한글 및 영문)
        csv_patterns = [
            base_dir / "data" / f"sns_{hashtag_safe}.csv",
            base_dir / "data" / f"sns_{hashtag}.csv",
            base_dir / "data" / f"sns_{hashtag_en}.csv",  # 영문 버전
        ]
        
        for csv_path in csv_patterns:
            if csv_path.exists():
                logger.info(f"✓ SNS CSV 파일 발견: {csv_path}")
                df = pd.read_csv(csv_path, encoding='utf-8-sig')
                break
        
        # 2) 와일드카드 검색 (sns_*{keyword}*.csv)
        if df is None:
            data_dir = base_dir / "data"
            if data_dir.exists():
                for csv_file in data_dir.glob(f"sns_*{hashtag_safe}*.csv"):
                    logger.info(f"✓ SNS CSV 파일 발견 (패턴): {csv_file}")
                    df = pd.read_csv(csv_file, encoding='utf-8-sig')
                    break
                    
                # 3) 키워드 포함된 CSV 검색
                if df is None:
                    for csv_file in data_dir.glob("sns_*.csv"):
                        try:
                            temp_df = pd.read_csv(csv_file, encoding='utf-8-sig')
                            if 'name_kr' in temp_df.columns:
                                if hashtag in temp_df['name_kr'].values:
                                    logger.info(f"✓ SNS CSV 파일에서 키워드 발견: {csv_file}")
                                    df = temp_df
                                    break
                        except:
                            continue
        
        # 3) xlsx 파일 폴백
        if df is None:
            xlsx_path = base_dir / "data" / "sns.xlsx"
            if xlsx_path.exists():
                logger.info(f"✓ SNS xlsx 파일 사용: {xlsx_path}")
                df = pd.read_excel(xlsx_path, engine="openpyxl")
            else:
                logger.warning(f"❌ SNS 데이터 파일 없음")
                return None
        
        # 데이터 필터링
        filtered = df[(df['country'] == country_code) & (df['name_kr'] == hashtag)]
        if filtered.empty:
            logger.warning(f"❌ 데이터 없음: {country_code} - {hashtag}")
            return None
        filtered = filtered.sort_values("mm-yy")
        plt.figure(figsize=(12, 6))
        plt.plot(filtered["mm-yy"], filtered["count"], marker="o", linewidth=2.5, markersize=8, color="#0D9488")
        plt.title(f"SNS 해시태그 트렌드: {hashtag} (국가: {country_code})", fontsize=13, fontweight="bold", pad=15)
        plt.xlabel("월", fontsize=11)
        plt.ylabel("건수", fontsize=11)
        plt.grid(True, alpha=0.3)
        plt.xticks(rotation=45)
        plt.tight_layout()
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        chart_path = output_dir / f"sns_chart_{country_code}_{hashtag_safe}.png"
        plt.savefig(chart_path, dpi=150, bbox_inches="tight", facecolor="white")
        plt.close()
        logger.info(f"✓ SNS 차트 생성 완료: {chart_path}")
        return str(chart_path)
    except Exception as e:
        logger.error(f"SNS 차트 생성 실패: {e}", exc_info=True)
        return None


class ReportGenerator:
    """보고서 생성기"""
    QUALITY_THRESHOLD = 70  # 🔧 C등급 기준으로 완화
    
    def __init__(self, internal_mode: bool = True):
        self.internal_mode = internal_mode
    
    def generate(self, payload: Dict, pipeline_result: Dict) -> Tuple[str, Dict]:
        """마크다운 보고서 생성"""
        try:
            final_report = pipeline_result.get("final_report", "")
            if not final_report:
                final_report = self._build_report_from_sections(payload, pipeline_result)
            if not self.internal_mode:
                final_report = self._move_citations_to_end(final_report, pipeline_result.get("all_citations", []))
            validation = {
                "sections_count": len(pipeline_result.get("sections", [])),
                "passed_count": sum(1 for s in pipeline_result.get("sections", []) if s.get("passed")),
                "citations_count": len(pipeline_result.get("all_citations", [])),
                "log_path": pipeline_result.get("log_path", "")
            }
            return final_report, validation
        except Exception as e:
            logger.error(f"보고서 생성 실패: {e}", exc_info=True)
            return f"# 보고서 생성 오류\n\n오류 내용: {str(e)}", {"error": str(e)}
    
    def _build_report_from_sections(self, payload: Dict, result: Dict) -> str:
        """섹션으로부터 보고서 구성 - 🔧 HS Code 기반 제목"""
        sections = result.get("sections", [])
        citations = result.get("all_citations", [])
        hs_category = result.get("hs_category", {})
        country_raw = payload.get('country', '')
        country_code = COUNTRY_CODE_MAP.get(country_raw, country_raw[:2].upper() if country_raw else "XX")
        hs_code = payload.get('hs_code', '')
        item = payload.get('item', '제품')
        category = hs_category.get('category', '제품')
        
        # 🔧 제목에서 item 제거 → HS Code 기반
        parts = [
            f"# {country_raw} HS {hs_code} 시장진출 보고서",
            f"\n📦 품목 카테고리: {category}",
            f"📅 생성일: {datetime.now().strftime('%Y-%m-%d')}",
            f"\n---\n"
        ]
        
        section_map = {}
        for section in sections:
            key = section.get("key")
            eval_info = section.get("evaluation", {})
            score = eval_info.get("score", 0)
            passed = section.get("passed")
            content = section.get("content", "") or ""
            
            # 💰 가격 추세 섹션은 내용만 있으면 포함 (검증 점수와 무관)
            if key == "price":
                if content.strip():
                    section_map[key] = section
                continue
            
            # 그 외 섹션은 기존 기준 유지
            if passed and score >= self.QUALITY_THRESHOLD and content.strip():
                section_map[key] = section
        
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
        
        success_info = get_success_rate_info(country_code, hs_code)
        
        for key, title in section_order:
            if key in section_map:
                section = section_map[key]
                content = section.get("content", "")
                eval_info = section.get("evaluation", {})
                grade = eval_info.get("grade", "N/A")
                score = eval_info.get("score", 0)
                parts.append(f"\n## {title}")
                if self.internal_mode:
                    parts.append(f"*품질: {grade}등급 ({score}점)*\n")
                if key == "distribution" and success_info:
                    parts.append(f"**📊 2026년 수출 유망 확률**: {success_info['2026성공확률']:.1f}%\n")
                parts.append(content)
        
        if citations:
            parts.append("\n## 9. 출처\n")
            kotra_sources = [c for c in set(citations) if "kotra" in c.lower()]
            kati_sources = [c for c in set(citations) if "kati" in c.lower()]
            web_sources = [c for c in set(citations) if "http" in c.lower() or "웹" in c]
            other_sources = [c for c in set(citations) if c not in kotra_sources + kati_sources + web_sources]
            if kotra_sources:
                parts.append("\n### KOTRA 자료")
                parts.extend([f"- {src}" for src in sorted(kotra_sources)])
            if kati_sources:
                parts.append("\n### KATI 자료")
                parts.extend([f"- {src}" for src in sorted(kati_sources)])
            if web_sources:
                parts.append("\n### 웹 자료")
                parts.extend([f"- {src}" for src in sorted(web_sources)])
            if other_sources:
                parts.append("\n### 기타")
                parts.extend([f"- {src}" for src in sorted(other_sources)])
        return "\n".join(parts)
    
    def _move_citations_to_end(self, report: str, citations: List[str]) -> str:
        """🔧 본문 출처 제거 후 끝으로 이동"""
        patterns = [
            r'\s*\[[^\]]*\.(pdf|json|csv|xlsx)[^\]]*\]',
            r'\s*\[출처:[^\]]+\]',
            r'\s*\[웹:[^\]]+\]',
            r'\s*\[KATI[^\]]*\]',
            r'\s*\[KOTRA[^\]]*\]',
            r'\s*\([^)]*\.pdf[^)]*\)',
            r'\s*\([^)]*https?://[^)]+\)',
        ]
        cleaned = report
        for pattern in patterns:
            cleaned = re.sub(pattern, '', cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r'\n\n\n+', '\n\n', cleaned)
        cleaned = re.sub(r'  +', ' ', cleaned)
        if "## 참고문헌" not in cleaned and "## 출처" not in cleaned and "## 9. 출처" not in cleaned:
            cleaned += "\n\n## 참고문헌\n\n"
            if citations:
                unique = list(set(citations))
                kotra = [c for c in unique if "kotra" in c.lower()]
                kati = [c for c in unique if "kati" in c.lower()]
                web = [c for c in unique if "http" in c.lower() or "웹" in c.lower()]
                other = [c for c in unique if c not in kotra + kati + web]
                if kotra:
                    cleaned += "### KOTRA 자료\n" + "\n".join([f"- {c}" for c in sorted(kotra)]) + "\n\n"
                if kati:
                    cleaned += "### KATI 자료\n" + "\n".join([f"- {c}" for c in sorted(kati)]) + "\n\n"
                if web:
                    cleaned += "### 웹 자료\n" + "\n".join([f"- {c}" for c in sorted(web)]) + "\n\n"
                if other:
                    cleaned += "### 기타\n" + "\n".join([f"- {c}" for c in sorted(other)]) + "\n"
            else:
                cleaned += "- 출처 정보 없음"
        return cleaned

    def export_pdf(self, markdown_text: str, output_path: str, metadata: Dict) -> bool:
        """PDF 내보내기 - 🔧 SNS 차트가 출처 앞에 오도록 수정"""
        try:
            output_dir = os.path.dirname(output_path) or "output"
            os.makedirs(output_dir, exist_ok=True)
            country_raw = metadata.get("country", "")
            country_code = COUNTRY_CODE_MAP.get(country_raw, "JP")
            enhanced_markdown = markdown_text
            hs_code = metadata.get("hs_code", "")
            success_info = get_success_rate_info(country_code, hs_code)
            if success_info:
                success_text = (
                    "\n## 📊 2026년 수출 유망 확률\n\n"
                    f"2026년 HS {success_info['HS코드']} 성공확률은: "
                    f"{success_info['2026성공확률']:.2f}%입니다.\n\n---\n"
                )
                for split_str in ["## 국가 및 시장 개요", "## 2. 국가"]:
                    parts = enhanced_markdown.split(split_str, 1)
                    if len(parts) == 2:
                        enhanced_markdown = parts[0] + success_text + split_str + parts[1]
                        break

            
            cover_path = output_path.replace(".pdf", "_cover.pdf")
            body_path = output_path.replace(".pdf", "_body.pdf")
            body_part1_path = output_path.replace(".pdf", "_body1.pdf")
            body_part2_path = output_path.replace(".pdf", "_body2.pdf")
            charts_path = output_path.replace(".pdf", "_charts.pdf")
            
            self._create_cover(cover_path, metadata)
            
            # 🔧 SNS 차트 생성
            sns_hashtag = metadata.get("sns_hashtag", "")
            sns_chart = None
            if sns_hashtag and sns_hashtag.strip():
                sns_chart = create_sns_hashtag_chart(country_code, sns_hashtag, output_dir, hs_code)
            elif hs_code:
                sns_chart = create_sns_hashtag_chart(country_code, "", output_dir, hs_code)
            
            # 🔧 SNS 차트가 있으면 본문을 출처 기준으로 분리
            if sns_chart:
                # 출처 섹션 분리 (9. 출처 또는 ## 출처 또는 ## 참고문헌)
                source_patterns = ["## 9. 출처", "## 출처", "## 참고문헌"]
                body_before_source = enhanced_markdown
                body_source = ""
                
                for pattern in source_patterns:
                    if pattern in enhanced_markdown:
                        split_parts = enhanced_markdown.split(pattern, 1)
                        body_before_source = split_parts[0]
                        body_source = pattern + split_parts[1]
                        break
                
                # Part 1: 본문 (출처 제외)
                self._create_body(body_part1_path, body_before_source)
                
                # Part 2: SNS 차트 페이지
                self._create_charts_page(charts_path, None, sns_chart)
                
                # Part 3: 출처 섹션
                if body_source:
                    self._create_body(body_part2_path, body_source)
                    pdf_parts = [cover_path, body_part1_path, charts_path, body_part2_path]
                else:
                    pdf_parts = [cover_path, body_part1_path, charts_path]
                
                temp_files = [cover_path, body_part1_path, charts_path, sns_chart]
                if body_source:
                    temp_files.append(body_part2_path)
            else:
                # SNS 차트 없으면 기존 방식
                self._create_body(body_path, enhanced_markdown)
                pdf_parts = [cover_path, body_path]
                temp_files = [cover_path, body_path]
            
            self._merge_pdfs(pdf_parts, output_path)
            
            # 임시 파일 정리
            for p in temp_files:
                if os.path.exists(p):
                    try:
                        os.remove(p)
                    except:
                        pass
            
            logger.info(f"✓ PDF 생성 완료: {output_path}")
            return True
        except Exception as e:
            logger.error(f"PDF 생성 실패: {e}", exc_info=True)
            return False
    
    def _create_charts_page(self, path: str, success_chart: Optional[str], sns_chart: Optional[str]):
        """차트 페이지 생성"""
        try:
            styles = getSampleStyleSheet()
            story = []
            if success_chart and os.path.exists(success_chart):
                story.append(Spacer(1, 20))
                story.append(Image(success_chart, width=160*mm, height=80*mm))
            if sns_chart and os.path.exists(sns_chart):
                story.append(Spacer(1, 20))
                story.append(Image(sns_chart, width=160*mm, height=80*mm))
            if story:
                doc = SimpleDocTemplate(path, pagesize=A4, leftMargin=25*mm, rightMargin=25*mm, topMargin=20*mm, bottomMargin=20*mm)
                doc.build(story)
        except Exception as e:
            logger.error(f"차트 페이지 생성 실패: {e}", exc_info=True)
            raise
    
    def _create_cover(self, path: str, metadata: Dict):
        """프리미엄 디자인 표지 - 🔧 HS코드 강조"""
        try:
            w, h = A4
            c = canvas.Canvas(path, pagesize=A4)
            country_raw = metadata.get("country", "")
            item = metadata.get("item", "제품")
            hs_code = metadata.get("hs_code", "")
            today = datetime.now().strftime("%Y-%m-%d")
            country = country_raw.split("(")[0].strip() if "(" in country_raw else country_raw
            
            c.setFillColor(HexColor("#FFFFFF"))
            c.rect(0, 0, w, h, fill=1, stroke=0)
            c.setFillColor(HexColor("#7DA0CA"))
            c.circle(w + 360, h * 0.55, 540, fill=1, stroke=0)
            c.setFillColor(HexColor("#052659"))
            c.circle(w * 0.70, -40, 320, fill=1, stroke=0)
            
            c.setFillColor(HexColor("#052659"))
            c.setFont(FONT_BOLD, 40)
            c.drawString(70, h - 200, f"{country} 시장 진출 전략 보고서")
            c.setFont(FONT_BOLD, 48)
            c.drawString(70, h - 250, "2025")
            c.setFont(FONT_REGULAR, 17)
            c.drawString(70, h - 290, "데이터 기반 해외시장 분석")
            c.setStrokeColor(HexColor("#021024"))
            c.setLineWidth(1)
            c.line(70, h - 305, 320, h - 305)
            
            desc = "본 보고서는 국가정보·진출전략·수출데이터 기반으로 생성되었습니다.\nAI 기반 분석을 통해 시장성 평가 및 진출 전략을 제공합니다."
            c.setFont(FONT_REGULAR, 13)
            y = h - 330
            for line in desc.split("\n"):
                c.drawString(70, y, line)
                y -= 14
            
            c.setFont(FONT_BOLD, 16)
            c.drawString(70, y - 20, f"HS Code: {hs_code}")
            c.drawString(70, y - 50, f"품목: {item}")
            
            c.setFillColor(HexColor("#FFFFFF"))
            c.setFont(FONT_REGULAR, 10)
            c.drawRightString(w - 40, 60, f"발행일: {today}")
            c.drawRightString(w - 40, 50, "작성기관: GlobalPath AI – Market Intelligence Unit")
            c.drawRightString(w - 40, 40, "저작권: © GlobalPath AI. All Rights Reserved.")
            c.save()
        except Exception as e:
            logger.error(f"표지 생성 실패: {e}", exc_info=True)
            raise
    
    def _create_body(self, path: str, text: str):
        """본문 생성"""
        try:
            styles = getSampleStyleSheet()
            body_style = ParagraphStyle("Body", parent=styles["Normal"], fontName=FONT_REGULAR, fontSize=9, leading=13, wordWrap='CJK')
            heading1_style = ParagraphStyle("Heading1", parent=styles["Heading1"], fontName=FONT_BOLD, fontSize=16, leading=20, textColor=HexColor("#1e40af"), spaceBefore=20, spaceAfter=10)
            heading2_style = ParagraphStyle("Heading2", parent=styles["Heading2"], fontName=FONT_BOLD, fontSize=12, leading=15, textColor=HexColor("#1e40af"), spaceBefore=12, spaceAfter=6)
            citation_style = ParagraphStyle("Citation", parent=styles["Normal"], fontName=FONT_REGULAR, fontSize=7, textColor=HexColor("#6b7280"), leftIndent=15)
            
            story = []
            lines = text.split("\n")
            for i, line in enumerate(lines):
                line = line.strip()
                if not line:
                    if i > 0 and lines[i-1].strip():
                        story.append(Spacer(1, 4))
                    continue
                safe_line = self._escape_html(line)
                if line.startswith("# ") and not line.startswith("## "):
                    story.append(Paragraph(safe_line[2:], heading1_style))
                elif line.startswith("## "):
                    story.append(Paragraph(safe_line[3:], heading2_style))
                elif line.startswith("- ") or line.startswith("* "):
                    story.append(Paragraph(f"• {safe_line[2:]}", citation_style))
                elif line.startswith("### "):
                    story.append(Paragraph(safe_line[4:], heading2_style))
                else:
                    story.append(Paragraph(safe_line, body_style))
            
            doc = SimpleDocTemplate(path, pagesize=A4, leftMargin=50, rightMargin=50, topMargin=50, bottomMargin=50)
            doc.build(story)
        except Exception as e:
            logger.error(f"본문 생성 실패: {e}", exc_info=True)
            raise
    
    def _escape_html(self, text: str) -> str:
        """HTML 특수문자 이스케이프"""
        text = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        text = text.replace("'", "&apos;").replace('"', "&quot;")
        text = re.sub(r'\*\*([^*]+)\*\*', r'<b>\1</b>', text)
        text = re.sub(r'\*([^*]+)\*', r'<i>\1</i>', text)
        return text
    
    def _merge_pdfs(self, input_paths: List[str], output_path: str):
        """PDF 병합"""
        try:
            writer = PdfWriter()
            for path in input_paths:
                if os.path.exists(path):
                    reader = PdfReader(path)
                    for page in reader.pages:
                        writer.add_page(page)
            with open(output_path, "wb") as f:
                writer.write(f)
        except Exception as e:
            logger.error(f"PDF 병합 실패: {e}", exc_info=True)
            raise


def main():
    """CLI 실행"""
    try:
        from pipeline import ResearchPipelineUpgraded, init_vectorstore
        
        if len(sys.argv) > 1:
            with open(sys.argv[1], "r", encoding="utf-8") as f:
                payload = json.load(f)
        else:
            payload = {"country": "일본", "hs_code": "2204.29.1000", "item": "와인", "options": []}
        
        logger.info(f"분석 시작: {payload}")
        hs_code = payload.get("hs_code", "")
        if hs_code:
            hs_code_clean = str(hs_code).replace(".", "").replace(" ", "")
            if len(hs_code_clean) == 10:
                payload["hs_code_2digit"] = hs_code_clean[:2]
                payload["hs_code_4digit"] = hs_code_clean[:4]
                payload["is_beverage"] = hs_code_clean[:2] == "22"
        
        db = init_vectorstore()
        pipeline = ResearchPipelineUpgraded(db)
        result = pipeline.run(payload, lambda step, msg, progress: logger.info(f"[{progress*100:.0f}%] {msg}"))
        
        generator = ReportGenerator(internal_mode=True)
        report_text, validation = generator.generate(payload, result)
        
        country_raw = payload.get("country", "")
        country_code = COUNTRY_CODE_MAP.get(country_raw, country_raw[:2].upper() if country_raw else "XX")
        hs_code_clean = payload.get("hs_code", "000000").replace(".", "").replace(" ", "")
        today_str = datetime.now().strftime('%Y%m%d')
        
        os.makedirs("output", exist_ok=True)
        md_path = f"output/{country_code}_{hs_code_clean}_{today_str}.md"
        with open(md_path, "w", encoding="utf-8") as f:
            f.write(report_text)
        
        pdf_path = f"output/{country_code}_{hs_code_clean}_{today_str}.pdf"
        pdf_success = generator.export_pdf(report_text, pdf_path, payload)
        
        print(json.dumps({"success": pdf_success, "pdf_path": pdf_path if pdf_success else None, "md_path": md_path, "log_path": result.get("log_path", ""), "validation": validation}, ensure_ascii=False))
        return 0 if pdf_success else 1
    except Exception as e:
        logger.error(f"프로그램 실행 실패: {e}", exc_info=True)
        print(json.dumps({"success": False, "error": str(e), "error_type": type(e).__name__}, ensure_ascii=False))
        return 1


if __name__ == "__main__":
    sys.exit(main())