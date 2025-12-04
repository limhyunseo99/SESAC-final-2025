# generator.py
# 보고서 생성 및 PDF 출력

import os
import logging
from datetime import datetime
from typing import Dict, List, Tuple

from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.colors import HexColor
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
from PyPDF2 import PdfReader, PdfWriter

from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage

from config import Config, Supervisor

logger = logging.getLogger(__name__)

# 폰트 등록 (시스템에 맞게 수정)
try:
    pdfmetrics.registerFont(TTFont("NanumGothic", "/usr/share/fonts/truetype/nanum/NanumGothic.ttf"))
    FONT_REGULAR = "NanumGothic"
    FONT_BOLD = "NanumGothic"
except:
    FONT_REGULAR = "Helvetica"
    FONT_BOLD = "Helvetica-Bold"


class ReportGenerator:
    """보고서 생성 및 PDF 출력"""
    
    def __init__(self):
        self.llm = ChatOpenAI(model=Config.MODEL_SMART, temperature=0)
        self.supervisor = Supervisor()
    
    # -------------------------------------------------------------------------
    # 메인: 섹션 결과 → 최종 보고서
    # -------------------------------------------------------------------------
    def generate(self, payload: Dict, pipeline_result: Dict) -> Tuple[str, Dict]:
        """
        파이프라인 결과를 최종 보고서로 변환
        
        Returns:
            (markdown_text, validation_result)
        """
        country = payload.get("country", "")
        hs_code = payload.get("hs_code", "")
        item = payload.get("item", "제품")
        
        sections = pipeline_result.get("sections", [])
        final_report = pipeline_result.get("final_report", "")
        
        # 이미 최종 보고서가 있으면 그대로 사용
        if final_report:
            validation = self.supervisor.validate_summary(final_report[:500])
            return final_report, validation
        
        # 없으면 섹션 기반으로 생성
        report_parts = []
        
        # 1. Executive Summary
        summary = self._generate_summary(payload, sections)
        report_parts.append(f"## 1. 요약 (Executive Summary)\n\n{summary}")
        
        # 2. 각 섹션
        section_titles = [
            "국가 및 시장 개요", "품목 적합성 평가", "시장 규모 및 성장 전망",
            "유통 구조", "규제 요건", "가격 추세", "리스크 분석", "수요 전망"
        ]
        
        for i, sec in enumerate(sections):
            title = sec.get("title", section_titles[i] if i < len(section_titles) else f"섹션 {i+1}")
            content = sec.get("summary", "자료 부족")
            report_parts.append(f"## {i+2}. {title}\n\n{content}")
        
        # 3. 전략 제언
        strategy = self._generate_strategy(payload, sections)
        report_parts.append(f"## {len(sections)+2}. 전략 제언\n\n{strategy}")
        
        # 합치기
        full_report = "\n\n".join(report_parts)
        validation = self.supervisor.validate_summary(summary)
        
        return full_report, validation
    
    def _generate_summary(self, payload: Dict, sections: List[Dict]) -> str:
        """Executive Summary 생성"""
        sections_text = "\n".join([f"- {s.get('title', '')}: {s.get('summary', '')[:200]}" for s in sections])
        
        prompt = f"""
KOTRA 수석 애널리스트로서 Executive Summary를 작성하세요.

국가: {payload.get('country')}
품목: {payload.get('item')}
HS Code: {payload.get('hs_code')}

섹션 요약:
{sections_text}

400-500자로 핵심 내용을 요약하세요. 시장 규모, 성장률, 기회, 리스크를 포함하세요.
"""
        try:
            response = self.llm.invoke([HumanMessage(content=prompt)])
            return response.content.strip()
        except:
            return "Executive Summary 생성 실패"
    
    def _generate_strategy(self, payload: Dict, sections: List[Dict]) -> str:
        """전략 제언 생성"""
        sections_text = "\n".join([f"- {s.get('title', '')}: {s.get('summary', '')[:150]}" for s in sections])
        
        prompt = f"""
KOTRA 수석 분석관으로서 시장진출 전략을 제언하세요.

국가: {payload.get('country')}
품목: {payload.get('item')}

분석 결과:
{sections_text}

400-600자로 실행 가능한 전략을 제시하세요.
가격 전략, 유통 전략, 리스크 대응, 경쟁 우위 활용을 포함하세요.
"""
        try:
            response = self.llm.invoke([HumanMessage(content=prompt)])
            return response.content.strip()
        except:
            return "전략 제언 생성 실패"
    
    # -------------------------------------------------------------------------
    # PDF 생성
    # -------------------------------------------------------------------------
    def export_pdf(self, markdown_text: str, output_path: str, metadata: Dict):
        """마크다운 → PDF 변환"""
        os.makedirs(os.path.dirname(output_path) or "output", exist_ok=True)
        
        cover_path = output_path.replace(".pdf", "_cover.pdf")
        body_path = output_path.replace(".pdf", "_body.pdf")
        
        # 표지 생성
        self._create_cover(cover_path, metadata)
        
        # 본문 생성
        self._create_body(body_path, markdown_text)
        
        # 병합
        self._merge_pdfs([cover_path, body_path], output_path)
        
        # 임시 파일 삭제
        for p in [cover_path, body_path]:
            if os.path.exists(p):
                os.remove(p)
        
        logger.info(f"PDF 생성 완료: {output_path}")
    
    def _create_cover(self, path: str, metadata: Dict):
        """표지 PDF 생성"""
        w, h = A4
        c = canvas.Canvas(path, pagesize=A4)
        
        # 배경
        c.setFillColor(HexColor("#3b82f6"))
        c.rect(0, 0, w, h, fill=1, stroke=0)
        
        # 텍스트
        c.setFillColor(HexColor("#FFFFFF"))
        c.setFont(FONT_BOLD, 32)
        c.drawString(60, h - 200, f"{metadata.get('country', '')} 시장 진출 보고서")
        
        c.setFont(FONT_REGULAR, 18)
        c.drawString(60, h - 260, f"품목: {metadata.get('item', '')}")
        c.drawString(60, h - 290, f"HS Code: {metadata.get('hs_code', '')}")
        
        c.setFont(FONT_REGULAR, 12)
        c.drawString(60, h - 350, f"생성일: {datetime.now().strftime('%Y-%m-%d')}")
        c.drawString(60, h - 370, "Powered by GlobalPath AI")
        
        c.save()
    
    def _create_body(self, path: str, text: str):
        """본문 PDF 생성"""
        styles = getSampleStyleSheet()
        
        body_style = ParagraphStyle(
            "Body", parent=styles["Normal"],
            fontName=FONT_REGULAR, fontSize=10, leading=14
        )
        heading_style = ParagraphStyle(
            "Heading", parent=styles["Heading2"],
            fontName=FONT_BOLD, fontSize=13, leading=16,
            textColor=HexColor("#1f2937"), spaceAfter=10
        )
        
        story = []
        
        for line in text.split("\n"):
            line = line.strip()
            if not line:
                story.append(Spacer(1, 6))
            elif line.startswith("## "):
                story.append(Spacer(1, 12))
                story.append(Paragraph(line[3:], heading_style))
            else:
                # HTML 특수문자 이스케이프
                safe_line = line.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
                story.append(Paragraph(safe_line, body_style))
        
        doc = SimpleDocTemplate(path, pagesize=A4, leftMargin=50, rightMargin=50, topMargin=50, bottomMargin=50)
        doc.build(story)
    
    def _merge_pdfs(self, input_paths: List[str], output_path: str):
        """PDF 병합"""
        writer = PdfWriter()
        
        for path in input_paths:
            if os.path.exists(path):
                reader = PdfReader(path)
                for page in reader.pages:
                    writer.add_page(page)
        
        with open(output_path, "wb") as f:
            writer.write(f)