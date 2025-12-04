# app.py
# Streamlit 앱 - 실시간 진행 상태 + PDF 뷰어

import streamlit as st
import base64
import time
from pathlib import Path
from typing import Optional

from pipeline import ResearchPipeline, init_vectorstore
from generator import ReportGenerator

# =============================================================================
# 페이지 설정
# =============================================================================
st.set_page_config(
    page_title="GlobalPath AI",
    page_icon="🐋",
    layout="wide",
    initial_sidebar_state="expanded",
)

# =============================================================================
# CSS 스타일
# =============================================================================
st.markdown("""
<style>
    .main-header { text-align: center; padding: 2rem 0; }
    .card {
        background: white;
        padding: 1.5rem;
        border-radius: 12px;
        border: 1px solid #e5e7eb;
        margin-bottom: 1rem;
    }
    .status-running { color: #3b82f6; }
    .status-done { color: #10b981; }
    .status-error { color: #ef4444; }
</style>
""", unsafe_allow_html=True)

# =============================================================================
# 상태 관리
# =============================================================================
if "page" not in st.session_state:
    st.session_state.page = "home"
if "payload" not in st.session_state:
    st.session_state.payload = {}
if "pdf_path" not in st.session_state:
    st.session_state.pdf_path = None
if "result" not in st.session_state:
    st.session_state.result = None


def go_to(page: str):
    st.session_state.page = page
    st.rerun()


# =============================================================================
# 컴포넌트: PDF 뷰어
# =============================================================================
def show_pdf(path: str, height: int = 700):
    """PDF를 iframe으로 표시"""
    if not Path(path).exists():
        st.error(f"PDF 파일 없음: {path}")
        return False
    
    with open(path, "rb") as f:
        base64_pdf = base64.b64encode(f.read()).decode("utf-8")
    
    st.markdown(f"""
        <iframe src="data:application/pdf;base64,{base64_pdf}" 
                width="100%" height="{height}" 
                style="border: 1px solid #ddd; border-radius: 8px;">
        </iframe>
    """, unsafe_allow_html=True)
    return True


def download_pdf(path: str, filename: str = "report.pdf"):
    """PDF 다운로드 버튼"""
    if Path(path).exists():
        with open(path, "rb") as f:
            st.download_button("📥 PDF 다운로드", f.read(), filename, "application/pdf", use_container_width=True)


# =============================================================================
# 사이드바
# =============================================================================
def render_sidebar():
    with st.sidebar:
        st.markdown("## 🐋 GlobalPath AI")
        st.markdown("---")
        
        if st.button("🏠 홈", use_container_width=True):
            go_to("home")
        
        if st.button("🔬 새 분석", use_container_width=True):
            go_to("analysis")
        
        if st.button("📄 결과", use_container_width=True, disabled=st.session_state.pdf_path is None):
            go_to("results")
        
        st.markdown("---")
        st.caption("v1.0 | Powered by LangChain")


# =============================================================================
# 페이지: 홈
# =============================================================================
def page_home():
    st.markdown("""
        <div class="main-header">
            <h1>🐋 GlobalPath AI</h1>
            <p style="font-size: 1.2rem; color: #6b7280;">
                AI 기반 해외시장 진출 분석 솔루션
            </p>
        </div>
    """, unsafe_allow_html=True)
    
    col1, col2, col3 = st.columns(3)
    
    with col1:
        st.markdown("""
            <div class="card" style="text-align: center;">
                <h3>🌍 무역 데이터</h3>
                <p>국가별 수출입 통계 분석</p>
            </div>
        """, unsafe_allow_html=True)
    
    with col2:
        st.markdown("""
            <div class="card" style="text-align: center;">
                <h3>📊 시장 분석</h3>
                <p>규제, 가격, 유통 구조 분석</p>
            </div>
        """, unsafe_allow_html=True)
    
    with col3:
        st.markdown("""
            <div class="card" style="text-align: center;">
                <h3>📈 전략 제언</h3>
                <p>맞춤형 시장진출 전략</p>
            </div>
        """, unsafe_allow_html=True)
    
    st.markdown("<br>", unsafe_allow_html=True)
    
    col_btn = st.columns([1, 1, 1])[1]
    with col_btn:
        if st.button("🚀 분석 시작하기", type="primary", use_container_width=True):
            go_to("analysis")


# =============================================================================
# 페이지: 새 분석
# =============================================================================
def page_analysis():
    st.title("🔬 새 분석")
    st.markdown("---")
    
    # 입력 폼
    col1, col2 = st.columns(2)
    
    with col1:
        country = st.selectbox("대상 국가", ["미국 (USA)", "일본 (Japan)", "베트남 (Vietnam)"])
    
    with col2:
        hs_code = st.text_input("HS Code", placeholder="예: 3304.99")
    
    item = st.text_input("품목명", placeholder="예: 화장품, 식품 등")
    
    st.markdown("---")
    
    # 분석 버튼
    if st.button("🔍 분석 실행", type="primary", use_container_width=True):
        
        if not hs_code or not item:
            st.error("HS Code와 품목명을 입력해주세요.")
            return
        
        # 페이로드 저장
        st.session_state.payload = {
            "country": country.split(" ")[0],  # "미국" 추출
            "hs_code": hs_code,
            "item": item,
        }
        
        # 진행 상태 UI
        st.markdown("### 📊 분석 진행 중...")
        progress_bar = st.progress(0)
        status_text = st.empty()
        status_list = st.container()
        
        statuses = []
        
        def update_progress(step: str, msg: str, progress: float):
            """진행 상태 콜백"""
            progress_bar.progress(progress)
            status_text.markdown(f"**{msg}**")
            
            # 상태 목록 업데이트
            icon = "✅" if progress > 0 and "완료" in msg else "🔄" if "중" in msg else "⏳"
            statuses.append(f"{icon} {msg}")
            
            with status_list:
                for s in statuses[-8:]:  # 최근 8개만 표시
                    st.text(s)
        
        try:
            # 파이프라인 실행
            with st.spinner("초기화 중..."):
                vectordb = init_vectorstore()
                pipeline = ResearchPipeline(vectordb)
                generator = ReportGenerator()
            
            # 연구 실행
            result = pipeline.run(st.session_state.payload, update_progress)
            st.session_state.result = result
            
            # 보고서 생성
            update_progress("report", "📄 PDF 보고서 생성 중...", 0.95)
            
            report_text, validation = generator.generate(st.session_state.payload, result)
            
            output_path = "output/report.pdf"
            generator.export_pdf(report_text, output_path, st.session_state.payload)
            
            st.session_state.pdf_path = output_path
            
            # 완료
            progress_bar.progress(1.0)
            status_text.markdown("**✅ 분석 완료!**")
            
            st.success("보고서가 생성되었습니다!")
            st.balloons()
            
            time.sleep(1)
            
            # 결과 페이지로 이동 버튼
            if st.button("📄 결과 보기", type="primary"):
                go_to("results")
        
        except Exception as e:
            st.error(f"오류 발생: {e}")
            st.exception(e)


# =============================================================================
# 페이지: 결과
# =============================================================================
def page_results():
    st.title("📄 분석 결과")
    st.markdown("---")
    
    pdf_path = st.session_state.pdf_path
    
    if not pdf_path or not Path(pdf_path).exists():
        st.warning("생성된 보고서가 없습니다.")
        if st.button("🔬 새 분석 시작"):
            go_to("analysis")
        return
    
    # 액션 버튼
    col1, col2, col3 = st.columns(3)
    
    with col1:
        download_pdf(pdf_path, "GlobalPath_Report.pdf")
    
    with col2:
        if st.button("🔄 새 분석", use_container_width=True):
            go_to("analysis")
    
    with col3:
        if st.button("🏠 홈으로", use_container_width=True):
            go_to("home")
    
    st.markdown("---")
    
    # 분석 정보
    payload = st.session_state.payload
    if payload:
        st.markdown(f"""
            **분석 정보**: {payload.get('country', '')} | {payload.get('item', '')} | HS {payload.get('hs_code', '')}
        """)
    
    # PDF 뷰어
    st.markdown("### 📑 보고서 미리보기")
    show_pdf(pdf_path, height=750)


# =============================================================================
# 메인
# =============================================================================
def main():
    render_sidebar()
    
    if st.session_state.page == "home":
        page_home()
    elif st.session_state.page == "analysis":
        page_analysis()
    elif st.session_state.page == "results":
        page_results()
    else:
        go_to("home")


if __name__ == "__main__":
    main()