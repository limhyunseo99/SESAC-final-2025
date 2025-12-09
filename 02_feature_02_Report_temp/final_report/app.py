import streamlit as st
import pandas as pd
import plotly.express as px
import time
import random
import json
import subprocess
import sys, os
from modules.hs_code_main import hs_main

import base64
from pathlib import Path

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.append(BASE_DIR)

# -----------------------------------------------------------------------------
# 1. 페이지 설정
# -----------------------------------------------------------------------------
st.set_page_config(
    page_title="GlobalPath AI",
    page_icon="🐋",
    layout="wide",
    initial_sidebar_state="expanded",
)

# -----------------------------------------------------------------------------
# 2. 디자인 (Custom CSS)
# -----------------------------------------------------------------------------
st.markdown(
    """
<style>
    :root {
        --primary-color: #3b82f6; /* 기본 파란색 유지 */
        --bg-color: #F9FAFB;
        --teal-primary: #0D9488; 
        --teal-hover: #0F766E;
        --black-primary: #000000; /* 검은색 추가 */
        --black-hover: #333333; /* 호버 시 진한 회색 */
    }

    .stApp {
        font-family: 'Pretendard', sans-serif;
    }

    /* ------------------------------------------------------------------------
     * 사이드바 스타일: 사용자 정보 하단 고정
     * ------------------------------------------------------------------------ */
    section[data-testid="stSidebar"] {
    background-color: #75bcff;
    border-right: 1px solid #E5E7EB;
    }

    /* 사이드바 버튼 글자 흰색 */
    section[data-testid="stSidebar"] button,
    section[data-testid="stSidebar"] button * ,
    section[data-testid="stSidebar"] div[data-baseweb="button"] span {
    color: white !important;
    }

    /* 사이드바 버튼 테두리 없앰 */
    section[data-testid="stSidebar"] button {
    border: 0 !important;
    outline: 0 !important;
    box-shadow: none !important;
    background: transparent !important;
    }

    /* 사이드바 버튼 누를 때 색깔 */
    section[data-testid="stSidebar"] button:hover,
    section[data-testid="stSidebar"] button:focus,
    section[data-testid="stSidebar"] button:active {
    border: 0 !important;
    outline: 0 !important;
    background-color: #3b82f6 !important;
}

    /* ------------------------------------------------------------------------
     * 카드 스타일
     * ------------------------------------------------------------------------ */
    .css-card {
        background-color: white;
        padding: 2rem;
        border-radius: 16px;
        box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.05);
        border: 1px solid #e5e7eb;
        margin-bottom: 1.5rem;
    }

    /* 외곽선만 있는 카드 스타일 */
    .outlined-card {
        background-color: white;
        padding: 2.5rem 3rem;
        border-radius: 16px;
        border: 2px solid var(--black-primary); /* 검은색 외곽선 */
        margin-bottom: 3rem;
        box-shadow: none; /* 그림자 제거 */
    }
    
    /* ------------------------------------------------------------------------
     * 기타 컴포넌트 스타일
     * ------------------------------------------------------------------------ */
    h1, h2, h3 { color: #1f2937; font-weight: 700; }
    p, span, label, .stMarkdown { color: #4b5563; }
    
    .logo-text {
        font-size: 1.4rem;
        font-weight: 800;
        color: #1f2937;
    }
    .logo-icon {
        font-size: 1.8rem;
        margin-right: 8px;
    }

    /* 메인화면 primary 버튼*/
    section[data-testid="stMain"] button[kind="primary"],
    div[data-testid="stDialog"] button[kind="primary"] {
    background-image: linear-gradient(to right, #4facfe 0%, #00f2fe 100%) !important;
    border: none !important;
    color: white !important;
    padding: 10px 20px !important;
    text-align: center;
    font-size: 16px !important;
    margin: 4px 2px !important;
    cursor: pointer;
    border-radius: 8px !important;
    box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1) !important;
    transition: 0.3s;
    }

    /* 호버 효과도 추가 */
    section[data-testid="stMain"], div[data-testid="stDialog"]
    button[kind="primary"]:hover {
    transform: translateY(-1px);
    box-shadow: 0 6px 10px rgba(0, 0, 0, 0.15) !important;
    }


""",
    unsafe_allow_html=True,
)

# -----------------------------------------------------------------------------
# 3. 상태 관리
# -----------------------------------------------------------------------------
if "page" not in st.session_state:
    st.session_state.page = "dashboard"
if "analysis_data" not in st.session_state:
    st.session_state.analysis_data = {}


def navigate_to(page_name):
    st.session_state.page = page_name
    st.rerun()


# HS Code 찾기 팝업
@st.dialog("HTS 코드 찾기")
def hs_code_finder_dialog():
    st.caption("수출하고자 하는 상품의 상세설명을 입력해주세요.<br>관세청 기반 데이터를 통해 가장 적절한 HTS코드 10자리를 찾아드려요.", unsafe_allow_html=True)

    # col_d1, col_d2 = st.columns(2)
    # with col_d1:
    #     prod_name = st.text_input("상품명", placeholder="예: 립스틱")
    # with col_d2:
    #     item_name = st.text_input("품목명", placeholder="예: 화장품")

    desc = st.text_area(
        "상품 설명", placeholder="원재료, 함량(%), 제조방식, 용도 등을 자세히 적어주세요.", height=170
    )

    st.markdown("<br>", unsafe_allow_html=True)

     # 결과 저장용 세션
    if "hs_result" not in st.session_state:
        st.session_state.hs_result = None

    if "selected_row" not in st.session_state:
        st.session_state.selected_row = None

    # 검색 버튼
    if st.button("🔍 검색", type="primary", use_container_width=True):

        if not desc.strip():
            st.error("상품 설명을 입력해주세요.")
            return

        with st.spinner("HTS 코드 분석 중... (약 1분 소요)"):
            result = hs_main(desc)  # hs코드 예측 함수
            st.session_state.hs_result = result
            st.session_state.selected_row = None

        # 결과 표 출력 + 선택
    if st.session_state.get("hs_result"):


        # 1) df 정의
        df = pd.DataFrame(st.session_state.hs_result)

        # 2) 탭 생성 (1순위, 2순위, 3순위...)
        tab_labels = [f"{i+1}순위" for i in range(len(df))]
        tabs = st.tabs(tab_labels)
    
        # 3) 각 탭에 해당 순위의 정보 표시
        for i, tab in enumerate(tabs):
            with tab:
                st.markdown(f"### 🔎 {i+1}순위 HTS 코드")
                st.write(f"**HTS 코드:** {df.loc[i, 'hs_code']}")
                st.write(f"**품목명:** {df.loc[i, 'title']}")
            
                st.markdown("### 📌 결정 사유")
                st.write(df.loc[i, "reason"])
            
                # 각 탭마다 선택 버튼 추가
                if st.button(f"{i+1}순위 HTS 코드 선택하기", key=f"select_hs_{i}", use_container_width=True):
                    st.session_state.analysis_data["hs_code"] = df.loc[i, "hs_code"]
                    time.sleep(0.3)
                    st.rerun()

    else:
        st.warning("HS 추천 결과가 없습니다. 먼저 분석을 실행해주세요.")

# -----------------------------------------------------------------------------
# 4. 사이드바
# -----------------------------------------------------------------------------
def render_sidebar():
    with st.sidebar:
        # 상단 로고 영역
        st.markdown(
            """
            <div style="display: flex; align-items: center; margin-bottom: 30px;">
                <span class="logo-icon">🐋</span>
                <span class="logo-text">GlobalPath AI</span>
            </div>
        """,
            unsafe_allow_html=True,
        )

        # 메뉴 영역
        st.markdown(
            "<div style='font-size: 0.75rem; color: #1f2937; font-weight: 700; margin-bottom: 10px; letter-spacing: 0.05em;'>MENU</div>",
            unsafe_allow_html=True,
        )

        if st.button("Home"):
            navigate_to("dashboard")

        if st.button("New Analysis"):
            navigate_to("new_analysis")

        st.button(
            "Analysis History",
            disabled=True,
            help="향후 제공 예정",
        )
        st.button(
            "Saved Reports",
            disabled=True,
            help="향후 제공 예정",
        )

        st.markdown(
            "<div style='margin-top: 30px; font-size: 0.75rem; color: #1f2937; font-weight: 700; margin-bottom: 10px; letter-spacing: 0.05em;'>SETTINGS</div>",
            unsafe_allow_html=True,
        )
        st.button("Preferences",
                  disabled=True,
                  help="향후 제공 예정")
        st.button("Help & Support",
                  disabled=True,
                  help="향후 제공 예정")

        # # 사용자 정보 하단 고정용 여백
        # st.markdown(
        #     "<div style='margin-top: auto;'></div>",
        #     unsafe_allow_html=True,
        # )

        # 구분선
        st.markdown(
            "<hr style='margin: 1rem 0; border-top: 1px solid #e5e7eb;'>",
            unsafe_allow_html=True,
        )
        
        ""

        # 사용자 프로필 카드
        profile_col1, profile_col2 = st.columns([1, 3])
        with profile_col1:
            st.markdown(
                """
                <div style="
                    width: 38px; 
                    height: 38px; 
                    background-color: #3b82f6; 
                    border-radius: 50%; 
                    display: flex; 
                    align-items: center; 
                    justify-content: center;
                    color: white;
                    font-weight: bold;
                    font-size: 0.9rem;
                ">
                    B
                </div>
            """,
                unsafe_allow_html=True,
            )
        with profile_col2:
            st.markdown(
                """
                <div style="line-height: 1.2; display: flex; flex-direction: column; justify-content: center; height: 100%;">
                    <span style="font-weight: 600; color: #374151; font-size: 0.9rem;">Bunny</span>
                    <span style="font-size: 0.75rem; color: #374151;">Trade Analyst</span>
                </div>
            """,
                unsafe_allow_html=True,
            )
        
        ""
        ""
        
        st.button("Sign Out")
        #     # st.success("로그아웃 되었습니다.")


# -----------------------------------------------------------------------------
# 5. 페이지: Home
# -----------------------------------------------------------------------------
def page_dashboard():
    col_main1, col_main2, col_main3 = st.columns([2, 1, 2])
    with col_main2:
        # 이미지 주소
        image_url = "https://ugokawaii.com/wp-content/uploads/2023/06/ship.gif" 
        st.image(
        image_url,
        # caption="Dash your shipping",  # 이미지 아래에 표시할 캡션
        width=150,                     # 이미지의 너비를 픽셀 단위로 지정 (생략 가능)
)
    # 메인 헤더 가운데 정렬
    st.markdown(
        """
        <div style="margin-bottom: 3rem; text-align: center;">
            <div style="font-size: 3.5rem; margin-bottom: 1rem; color: #1f2937;"></div>
            <h1 style="color: #1f2937; margin-bottom: 0.5rem; font-size: 2.2rem;">Welcome to GlobalPath AI</h1>
            <p style="color: #4b5563; font-size: 1.1rem; opacity: 1;">
            데이터 기반의 무역 의사결정을 위한 최고의 솔루션입니다<br>
            복잡한 무역 데이터와 소셜 트렌드를 한눈에 파악하세요
            </p>
        </div>
    """,
        unsafe_allow_html=True,
    )

    # 분석 시작 카드 (외곽선 스타일 적용)
    # ------------------------------------------------------------------------
    # "---"

    def feature_card(icon, title, desc):
        return f"""
        <div class="css-card" style="padding: 2rem 1.5rem; text-align: center; height: 100%;">
            <div style="font-size: 2.5rem; margin-bottom: 1rem;">{icon}</div>
            <h3 style="font-size: 1.1rem; margin-bottom: 0.5rem;">{title}</h3>
            <p style="font-size: 0.9rem; color: #6b7280;">{desc}</p>
        </div>
        """
    
#     st.markdown(
#     """
#     <div class="css-card" style="padding: 2rem 1.5rem; text-align: left;">
#         <div style="font-size: 1.0rem; margin-bottom: 0.5rem;">
#             지금 바로 첫 분석을 시작해볼까요?<br>
#             관심 있는 국가와 품목(HS Code)을 입력하면 AI가 시장성을 분석해 드립니다.
#         </div>
#     """,
#     unsafe_allow_html=True,
# )

    col_home1, col_home2, col_home3 = st.columns([1, 1, 1])
    with col_home2:
        if st.button("🚀 Start Your First Analysis",
                     type="primary",
                    use_container_width=True):
            navigate_to("new_analysis")

    ""
    ""

    # ------------------------------------------------------------------------

    col1, col2, col3 = st.columns(3)

    with col1:
        st.markdown(
            feature_card(
                "🌍",
                "무역 데이터 분석",
                "국가별 수출입 통계와 성장률을<br>시각화하여 제공합니다",
            ),
            unsafe_allow_html=True,
        )
    with col2:
        st.markdown(
            feature_card(
                "📱",
                "소셜 미디어 인텔리전스",
                "글로벌 소셜 트렌드와 소비자 반응을<br>실시간으로 추적합니다",
            ),
            unsafe_allow_html=True,
        )
    with col3:
        st.markdown(
            feature_card(
                "📈",
                "시장 인사이트",
                "경쟁국 비교 분석과 향후 시장 전망<br>리포트를 생성합니다",
            ),
            unsafe_allow_html=True,
        )


# -----------------------------------------------------------------------------
# 6. 페이지: New Analysis
# -----------------------------------------------------------------------------
def page_new_analysis():
    st.title("New Analysis")
    st.markdown("---")
    st.caption("정확한 분석을 위해 대상 국가와 품목 코드를 입력해주세요.")
    st.write("")

    col_c1, col_c2, col_btn = st.columns([2, 2, 1])

    with col_c1:
        country = st.selectbox(
            "대상 국가 (Target Country)",
            [
                "미국 (USA)",
                "일본 (Japan)",
                "베트남 (Vietnam)",
            ],
            index=0,
        )
        st.session_state.analysis_data["country"] = country

    with col_c2:
        hs_code = st.text_input(
            "HTS Code (10자리)",
            placeholder="예: 2204990000",
            value=st.session_state.analysis_data.get("hs_code", ""),
            help="10자리 숫자만 입력 가능합니다 (예: 2204990000)"
        )
        
        # HS Code 검증
        if hs_code:
            # 숫자만 추출 (점이나 대시 제거)
            hs_code_clean = hs_code.replace(".", "").replace("-", "").replace(" ", "")
            
            # 숫자가 아닌 문자가 있는지 확인
            if not hs_code_clean.isdigit():
                st.error("❌ HS Code는 숫자만 입력 가능합니다.")
                hs_code_clean = ""
            # 10자리가 아닌 경우
            elif len(hs_code_clean) != 10:
                st.warning(f"⚠️ HS Code는 10자리여야 합니다. (현재: {len(hs_code_clean)}자리)")
            
            st.session_state.analysis_data["hs_code"] = hs_code_clean
        else:
            st.session_state.analysis_data["hs_code"] = ""

    with col_btn:
        st.markdown("<div style='margin-top: 29px;'></div>", unsafe_allow_html=True)
        if st.button("🔍 HTS Code 찾기", key="hs_finder_btn", use_container_width=True):
            hs_code_finder_dialog()

    st.write("")

    st.markdown("---")
    st.write("")

    st.markdown("**추가 분석 옵션 선택**")
    # 체크박스: 선택 시 파란색 (CSS로 처리됨)
    opt_col1, opt_col2, opt_col3 = st.columns([1, 1, 1])
    with opt_col1:
        chk_market_risk = st.checkbox("⚠️ 시장 리스크", value=False)
    with opt_col2:
        chk_regulation = st.checkbox("📋 규제 검토", value=False)
    with opt_col3:
        chk_price_trend = st.checkbox("💰 가격 추세", value=False)
    
    # 체크박스 값 저장
    st.session_state.analysis_data["market_risk"] = chk_market_risk
    st.session_state.analysis_data["regulation"] = chk_regulation
    st.session_state.analysis_data["price_trend"] = chk_price_trend

    ""
    ""
    
    st.markdown("**SNS 해시태그 분석**")
    sns_hashtag = st.text_input(
        label="SNS 키워드",
        label_visibility="collapsed",
        placeholder="예: 녹차, 식혜, 바나나 우유",
        help="분석하고 싶은 SNS 해시태그 키워드를 입력하세요"
    )
    st.session_state.analysis_data["sns_hashtag"] = sns_hashtag

    # 분석 실행 버튼 영역 
    bottom_col1, bottom_col2, bottom_col13 = st.columns([7, 4, 7])
    with bottom_col2:
        if st.button("분석 실행", type="primary", use_container_width=True):
            payload = st.session_state.analysis_data
            
            # HS Code 2자리, 4자리 추출 (음료 카테고리 분석용)
            hs_code = payload.get("hs_code", "")
            if hs_code and len(hs_code) == 10:
                payload["hs_code_2digit"] = hs_code[:2]  # 앞 2자리
                payload["hs_code_4digit"] = hs_code[:4]  # 앞 4자리
                
                # 음료 카테고리 여부 확인 (HS Code 22로 시작)
                if hs_code.startswith("22"):
                    payload["is_beverage"] = True
                else:
                    payload["is_beverage"] = False
            
            payload_path = Path("input_payload.json")
            with open(payload_path, "w", encoding="utf-8") as f:
                json.dump(payload, f, ensure_ascii=False, indent=2)

            with st.spinner("보고서를 생성하고 있습니다...약 5분 소요"):
                result = subprocess.run(
                    ["python", "generator.py", str(payload_path)],
                    capture_output=True,
                    text=True
                )
            
            # 결과 파싱
            if result.returncode == 0:
                try:
                    analysis_result = json.loads(result.stdout)
                    st.session_state.report_pdf_path = analysis_result.get("pdf_path", "output/report.pdf")
                    st.session_state.analysis_log_path = analysis_result.get("log_path", "")
                except:
                    st.session_state.report_pdf_path = "output/report.pdf"
            else:
                st.session_state.report_pdf_path = "output/report.pdf"

            st.session_state.page = "results"
            st.rerun()

# -----------------------------------------------------------------------------
# 7. 페이지: Results
# -----------------------------------------------------------------------------

# pdf 뷰어 생성기
def render_pdf_viewer(pdf_path: str):
    """
    pdf_path에 있는 PDF 파일을 Streamlit 페이지 안에 뷰어로 띄워주는 함수
    """
    file_path = Path(pdf_path)

    if not file_path.exists():
        st.error(f"PDF 파일을 찾을 수 없어요: {file_path}")
        return

    with open(file_path, "rb") as f:
        pdf_bytes = f.read()

    # PDF → base64 인코딩
    base64_pdf = base64.b64encode(pdf_bytes).decode("utf-8")

    # iframe으로 임베딩
    pdf_display = f"""
    <iframe
        src="data:application/pdf;base64,{base64_pdf}"
        width="100%"
        height="800"
        type="application/pdf">
    </iframe>
    """

    st.markdown(pdf_display, unsafe_allow_html=True)


def page_results():
    
    st.header("📄 분석 결과 리포트")

    pdf_path = st.session_state.get("report_pdf_path", "")

    if not pdf_path:
        st.warning("아직 표시할 PDF 리포트가 없어요")
        st.stop()

    st.subheader("결과 리포트 미리보기")
    st.write("뷰어의 📥 다운로드 버튼을 누르면 pdf 문서를 저장할 수 있어요")
    ""

    render_pdf_viewer(pdf_path)

# -----------------------------------------------------------------------------
# 8. 메인 실행 루프
# -----------------------------------------------------------------------------
def main():
    render_sidebar()

    if st.session_state.page == "dashboard":
        page_dashboard()
    elif st.session_state.page == "new_analysis":
        page_new_analysis()
    elif st.session_state.page == "results":
        page_results()
    else:
        st.error(f"Error: Page '{st.session_state.page}' not found.")
        if st.button("Go to Home"):
            navigate_to("dashboard")


if __name__ == "__main__":
    main()