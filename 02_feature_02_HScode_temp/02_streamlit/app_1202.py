import streamlit as st
import pandas as pd
import plotly.express as px
import time
import random

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

    section[data-testid="stMain"] button[kind="primary"] {
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
    section[data-testid="stMain"] button[kind="primary"]:hover {
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
@st.dialog("HS 코드 찾기")
def hs_code_finder_dialog():
    st.caption("찾고자 하는 상품의 정보를 입력해주세요.")

    col_d1, col_d2 = st.columns(2)
    with col_d1:
        prod_name = st.text_input("상품명 (필수)", placeholder="예: 립스틱")
    with col_d2:
        item_name = st.text_input("품목명 (필수)", placeholder="예: 화장품")

    desc = st.text_area(
        "상세 설명", placeholder="상품의 재질, 용도 등을 자세히 적어주세요.", height=100
    )

    st.markdown("<br>", unsafe_allow_html=True)

    if st.button("🔍 코드 찾기", type="primary", use_container_width=True):
        if not prod_name or not item_name:
            st.error("상품명과 품목명을 모두 입력해주세요.")
        else:
            st.success("검색 결과: 3304.99 (기타 미용 제품)")
            st.session_state.analysis_data["hs_code"] = "3304.99"
            time.sleep(1)
            st.rerun()


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
# 5. 페이지: Dashboard
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
    "---"

    def feature_card(icon, title, desc):
        return f"""
        <div class="css-card" style="padding: 2rem 1.5rem; text-align: center; height: 100%;">
            <div style="font-size: 2.5rem; margin-bottom: 1rem;">{icon}</div>
            <h3 style="font-size: 1.1rem; margin-bottom: 0.5rem;">{title}</h3>
            <p style="font-size: 0.9rem; color: #6b7280;">{desc}</p>
        </div>
        """
    
    st.markdown(
    """
    <div class="css-card" style="padding: 2rem 1.5rem; text-align: left;">
        <div style="font-size: 1.0rem; margin-bottom: 0.5rem;">
            지금 바로 첫 분석을 시작해볼까요?<br>
            관심 있는 국가와 품목(HS Code)을 입력하면 AI가 시장성을 분석해 드립니다.
        </div>
    """,
    unsafe_allow_html=True,
)

    col_home1, col_home2, col_home3 = st.columns([1, 1, 1])
    with col_home2:
        if st.button("🚀 Start Your First Analysis",
                     type="primary",
                    use_container_width=True):
            navigate_to("new_analysis")

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

    # 상단 버튼 영역 (분석 실행)
    top_col1, top_col2 = st.columns([2, 1])
    # with top_col1:
    #     st.subheader("분석 조건 설정")
    with top_col2:
        btn_col1, btn_col2 = st.columns(2)
        # with btn_col1:
        #     if st.button("지우기", use_container_width=True):
        #         st.session_state.analysis_data = {}
        #         st.rerun()
        with btn_col2:
            if st.button(
                "분석 실행",
                key="execute_analysis_top",
                type="primary",
                use_container_width=True,
            ):
                with st.spinner("데이터 분석 중입니다..."):
                    time.sleep(1.5)
                    st.session_state.page = "results"
                    st.rerun()

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
            "HS Code",
            placeholder="예: 3304.99",
            value=st.session_state.analysis_data.get("hs_code", ""),
        )
        st.session_state.analysis_data["hs_code"] = hs_code

    with col_btn:
        st.markdown("<div style='margin-top: 29px;'></div>", unsafe_allow_html=True)
        if st.button("🔍 HS Code 찾기", key="hs_finder_btn", use_container_width=True):
            hs_code_finder_dialog()

    st.write("")

    st.markdown("---")
    st.write("")

    st.markdown("**분석 옵션 선택**")
    # 체크박스: 선택 시 파란색 (CSS로 처리됨)
    opt_col1, opt_col2, opt_col3, opt_col4 = st.columns(4)
    with opt_col1:
        st.checkbox("무역 데이터", value=True)
    with opt_col2:
        st.checkbox("소셜 트렌드", value=True)
    with opt_col3:
        st.checkbox("경쟁국 비교")
    with opt_col4:
        st.checkbox("전망 분석")

    st.write("")

    st.markdown("**추가 메모**")
    st.text_area("분석에 참고할 메모를 자유롭게 입력하세요.", height=100)


# -----------------------------------------------------------------------------
# 7. 페이지: Results
# -----------------------------------------------------------------------------
def page_results():
    target_country = st.session_state.analysis_data.get("country", "미국 (USA)")
    target_code = st.session_state.analysis_data.get("hs_code", "3304.99")
    if not target_code:
        target_code = "3304.99 (Sample)"

    st.title(f"분석 결과 — {target_country.split('(')[0].strip()} / HS {target_code}")
    st.caption(f"Analysis generated at {time.strftime('%Y-%m-%d %H:%M')}")
    st.markdown("---")

    col_kpi1, col_kpi2, col_kpi3 = st.columns(3)

    export_val = random.randint(500, 1500)
    growth_rate = round(random.uniform(-5.0, 15.0), 1)
    market_share = round(random.uniform(10.0, 35.0), 1)

    with col_kpi1:
        st.markdown(
            '<div class="css-card" style="padding: 1.5rem; text-align: center;">',
            unsafe_allow_html=True,
        )
        st.metric("수출액 (Export Value)", f"${export_val}M", "+12.5%")
        st.markdown("</div>", unsafe_allow_html=True)
    with col_kpi2:
        st.markdown(
            '<div class="css-card" style="padding: 1.5rem; text-align: center;">',
            unsafe_allow_html=True,
        )
        st.metric("전년 대비 성장률", f"{growth_rate}%", f"{growth_rate - 2}%p")
        st.markdown("</div>", unsafe_allow_html=True)
    with col_kpi3:
        st.markdown(
            '<div class="css-card" style="padding: 1.5rem; text-align: center;">',
            unsafe_allow_html=True,
        )
        st.metric("시장 점유율", f"{market_share}%", "Top 3")
        st.markdown("</div>", unsafe_allow_html=True)

    st.markdown('<div class="css-card">', unsafe_allow_html=True)
    st.subheader("📊 5년 수출 추세 (Export Trend)")

    years = [2020, 2021, 2022, 2023, 2024]
    values = [random.randint(800, 1200) for _ in range(5)]
    values = sorted(values)

    df_chart = pd.DataFrame({"Year": years, "Export Value ($M)": values})

    fig = px.line(df_chart, x="Year", y="Export Value ($M)", markers=True)
    fig.update_layout(
        plot_bgcolor="white",
        paper_bgcolor="white",
        xaxis=dict(showgrid=False),
        yaxis=dict(showgrid=True, gridcolor="#f3f4f6"),
        font=dict(color="#4b5563"),
    )
    # 차트 색상: 보라색 계열 유지
    fig.update_traces(line_color="#8b5cf6", line_width=4, marker=dict(size=8))
    st.plotly_chart(fig, use_container_width=True)
    st.markdown("</div>", unsafe_allow_html=True)

    st.markdown('<div class="css-card">', unsafe_allow_html=True)
    st.subheader("📱 소셜 트렌드 요약 (Social Intelligence)")

    social_col1, social_col2, social_col3 = st.columns(3)
    with social_col1:
        st.markdown("**총 언급량 (Mentions)**")
        st.info("24,500 건 (▲ 15% this week)")
    with social_col2:
        st.markdown("**감성 분석 (Sentiment)**")
        st.success("긍정적 (Positive 68%)")
    with social_col3:
        st.markdown("**참여율 (Engagement)**")
        st.warning("High (4.8%)")

    st.caption(
        "※ 분석된 소셜 데이터는 Twitter, Instagram, LinkedIn의 공개 데이터를 기반으로 합니다."
    )
    st.markdown("</div>", unsafe_allow_html=True)

    st.markdown(
        "<div style='text-align: center; margin-top: 2rem;'>", unsafe_allow_html=True
    )
    st.caption("현재 데이터는 데모용입니다. (Dummy Data)")
    if st.button("↩ 새 분석으로 돌아가기"):
        navigate_to("new_analysis")
    st.markdown("</div>", unsafe_allow_html=True)


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
