# pdf_exporter.py
"""
보고서 PDF 변환 모듈
Markdown → HTML → PDF
"""

import os
import markdown
from weasyprint import HTML, CSS
from datetime import datetime


def markdown_to_html(md_text: str, metadata: dict) -> str:
    """
    Markdown을 HTML로 변환 (스타일 포함)

    Args:
        md_text: 마크다운 텍스트
        metadata: 보고서 메타데이터

    Returns:
        완성된 HTML
    """

    # Markdown 확장 기능 활성화
    html_body = markdown.markdown(
        md_text,
        extensions=[
            "extra",  # 표, 각주 등
            "codehilite",  # 코드 하이라이트
            "toc",  # 목차
            "sane_lists",  # 리스트 개선
        ],
    )

    # 메타데이터 추출
    country = metadata.get("country_name", "N/A")
    hs_code = metadata.get("hs_code", "N/A")
    today = datetime.now().strftime("%Y년 %m월 %d일")

    # HTML 템플릿
    html_template = f"""
<!DOCTYPE html>
<html lang="ko">
<head>
    <meta charset="UTF-8">
    <title>{country} 수출 전략 보고서 (HS {hs_code})</title>
    <style>
        @page {{
            size: A4;
            margin: 2.5cm;
            @bottom-right {{
                content: "페이지 " counter(page) " / " counter(pages);
                font-size: 9pt;
                color: #666;
            }}
        }}
        
        body {{
            font-family: "Malgun Gothic", "맑은 고딕", sans-serif;
            font-size: 11pt;
            line-height: 1.6;
            color: #333;
        }}
        
        h1 {{
            font-size: 24pt;
            color: #1a5490;
            border-bottom: 3px solid #1a5490;
            padding-bottom: 10px;
            margin-top: 0;
            page-break-before: auto;
        }}
        
        h2 {{
            font-size: 18pt;
            color: #2c5aa0;
            margin-top: 30px;
            margin-bottom: 15px;
            page-break-after: avoid;
        }}
        
        h3 {{
            font-size: 14pt;
            color: #4a7bb7;
            margin-top: 20px;
            margin-bottom: 10px;
        }}
        
        table {{
            width: 100%;
            border-collapse: collapse;
            margin: 15px 0;
            font-size: 10pt;
            page-break-inside: avoid;
        }}
        
        th, td {{
            border: 1px solid #ddd;
            padding: 8px;
            text-align: left;
        }}
        
        th {{
            background-color: #f0f4f8;
            font-weight: bold;
            color: #1a5490;
        }}
        
        ul, ol {{
            margin: 10px 0;
            padding-left: 25px;
        }}
        
        li {{
            margin: 5px 0;
        }}
        
        .metadata {{
            background-color: #f8f9fa;
            padding: 15px;
            border-left: 4px solid #1a5490;
            margin-bottom: 30px;
            font-size: 10pt;
        }}
        
        .warning-box {{
            background-color: #fff3cd;
            border-left: 4px solid #ff9800;
            padding: 12px;
            margin: 15px 0;
        }}
        
        .info-box {{
            background-color: #e3f2fd;
            border-left: 4px solid #2196f3;
            padding: 12px;
            margin: 15px 0;
        }}
        
        .page-break {{
            page-break-before: always;
        }}
        
        code {{
            background-color: #f4f4f4;
            padding: 2px 5px;
            border-radius: 3px;
            font-family: "Courier New", monospace;
            font-size: 9pt;
        }}
        
        pre {{
            background-color: #f4f4f4;
            padding: 10px;
            border-radius: 5px;
            overflow-x: auto;
            page-break-inside: avoid;
        }}
        
        a {{
            color: #1a5490;
            text-decoration: none;
        }}
        
        a[href^="http"]::after {{
            content: " (" attr(href) ")";
            font-size: 8pt;
            color: #666;
        }}
        
        .footnote {{
            font-size: 9pt;
            color: #666;
            margin-top: 30px;
            padding-top: 10px;
            border-top: 1px solid #ddd;
        }}
    </style>
</head>
<body>
    <div class="metadata">
        <h1>{country} 수출 전략 보고서</h1>
        <p><strong>분석 품목:</strong> HS {hs_code}</p>
        <p><strong>생성일:</strong> {today}</p>
        <p><strong>작성:</strong> AI 기반 자동 생성 시스템</p>
    </div>
    
    {html_body}
    
    <div class="footnote">
        <p><em>본 보고서는 KATI, KOTRA 자료 및 웹 검색 결과를 기반으로 AI가 자동 생성한 참고 자료입니다.</em></p>
        <p><em>실제 수출 진행 시 반드시 전문가의 검토가 필요합니다.</em></p>
    </div>
</body>
</html>
"""

    return html_template


def export_to_pdf(markdown_text: str, output_path: str, metadata: dict):
    """
    Markdown 보고서를 PDF로 변환

    Args:
        markdown_text: 마크다운 텍스트
        output_path: PDF 저장 경로
        metadata: 보고서 메타데이터
    """
    try:
        # HTML 변환
        html_content = markdown_to_html(markdown_text, metadata)

        # PDF 생성
        HTML(string=html_content).write_pdf(
            output_path,
            stylesheets=[
                CSS(
                    string="""
                @page {
                    margin: 2.5cm;
                }
            """
                )
            ],
        )

        print(f"✅ PDF 생성 완료: {output_path}")

    except Exception as e:
        print(f"❌ PDF 변환 실패: {e}")
        raise


# 테스트
if __name__ == "__main__":
    test_markdown = """
# 일본 수출 전략 보고서

## 1. Executive Summary

일본 견과류 시장은 2024년 기준 **230억 달러** 규모입니다.

## 2. 시장 규모

| 연도 | 시장 규모 |
|------|----------|
| 2022 | 210억 달러 |
| 2023 | 220억 달러 |
| 2024 | 230억 달러 |

### 주요 트렌드
- 건강식품 수요 증가
- 프리미엄 제품 선호

## 참고 링크
[1] https://example.com/report
"""

    export_to_pdf(
        test_markdown,
        "test_report.pdf",
        {"country_name": "일본", "hs_code": "2008190000"},
    )
