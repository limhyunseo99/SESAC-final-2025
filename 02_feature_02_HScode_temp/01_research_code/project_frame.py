import streamlit as st

# --- 1. 페이지 설정 및 사용자 지정 CSS (폰트, 색상 등) ---
st.set_page_config(layout="wide", page_title="Dashipping")

# 이미지의 레이아웃과 비슷하게 보이도록 기본 Streamlit 스타일을 커스터마이징
# 실제 이미지와 완벽하게 동일한 디자인을 만들려면 복잡한 CSS 지식이 필요합니다.
custom_css = f"""
<style>
    /* 전체 배경색을 흰색으로 설정 */
    .stApp {{
        background-color: white;
    }}

    /* 사이드바 배경색을 밝은 회색으로 설정 */
    .st-emotion-cache-1oe28u3.eqdzkfz1 {{ 
        background-color: #f8f8f8; 
    }}

    /* --- 메뉴 항목 (배경 없는 텍스트 링크) 스타일 --- */
    .sidebar-link {{
        display: block;
        padding: 8px 10px;
        margin-bottom: 2px;
        color: #4a4a4a; /* 기본 글자색 (회색) */
        text-decoration: none;
        cursor: pointer;
        font-weight: 400;
        border-radius: 4px;
        transition: background-color 0.2s;
    }}

    /* 호버 시: 매우 옅은 배경색을 표시 */
    .sidebar-link:hover {{
        background-color: #e0e0e0; 
    }}

    /* 선택된 메뉴 항목 스타일: 배경은 이미지와 비슷한 옅은 회색, 폰트는 보라색 */
    .sidebar-link.selected {{
        background-color: #f0f2f6; 
        color: #5850e0; /* 보라색 글자 */
        font-weight: 600;
        border-left: 3px solid #5850e0; /* 보라색 세로선 추가로 선택 강조 */
        padding-left: 7px; /* 세로선 때문에 패딩 조정 */
    }}
    
    /* --- SETTINGS 버튼 스타일 (배경 제거) --- */
    /* st.button을 텍스트 링크처럼 보이도록 배경색, 테두리 제거 */
    .stButton button {{
        background-color: transparent !important;
        border: none !important;
        color: #4a4a4a !important;
        text-align: left;
        font-weight: 400;
        padding: 8px 10px;
        margin: 0;
        height: auto;
    }}
    .stButton button:hover {{
        background-color: #e0e0e0 !important;
        color: #4a4a4a !important;
    }}

    /* 'Analyze' 버튼 스타일 (메인 컨텐츠) */
    .stButton>button[key="analyze_button"] {{
        background-color: #5850e0;
        color: white;
        border-radius: 4px;
        padding: 8px 20px;
        font-weight: 600;
        border: none;
    }}

    /* Trade Analyst 프로필 스타일 */
    .profile-circle {{
        width: 40px; 
        height: 40px; 
        background-color: #5850e0; 
        border-radius: 50%; 
        display: flex; 
        align-items: center; 
        justify-content: center; 
        color: white; 
        font-size: 1.2em;
    }}

</style>
"""
st.markdown(custom_css, unsafe_allow_html=True)


# --- 2. 사이드바 (MENU, SETTINGS) 구현 ---
with st.sidebar:
    # 대시보드 제목
    st.markdown("# Dashipping")
    
    ""
    ""

    # 1. MENU 섹션
    st.markdown("### 📁MENU")
    
    # st.selectbox 대신 st.page_link나 st.button을 사용해야 실제 메뉴처럼 작동하지만, 
    # 여기서는 시각적인 구조를 위해 st.radio를 사용하고 선택된 항목을 'New Analysis'로 설정합니다.

    # 딕셔너리로 메뉴 아이템과 아이콘 정의 (st.navlink를 사용할 수도 있습니다)
    st.button("New Analysis")   #  use_container_width=True < 가운데 정렬
    st.button("Analysis History")
    st.button("Saved Reports")

    # 2. SETTINGS 섹션
    st.markdown("### ⚙️SETTINGS")
    st.button("Preferences")
    st.button("Help & Support")

    # 3. 사용자 정보 및 로그아웃 (하단 고정은 CSS로 처리 필요)
    st.markdown("---")
    
    # 사용자를 원형으로 표현
    col1, col2 = st.columns([0.3, 0.7])
    with col1:
        # 이모지를 사용하여 원형 프로필 이미지 대체
        st.markdown(
            f'<div style="width: 40px; height: 40px; background-color: #5850e0; border-radius: 50%; display: flex; align-items: center; justify-content: center; color: white; font-size: 1.2em;">TA</div>', 
            unsafe_allow_html=True
        )
    with col2:
        st.markdown("**Trade Analyst**")
        st.caption("Premium User")
        
    st.button("Sign out")


# --- 3. 메인 컨텐츠 구현 (New Analysis) ---
st.markdown('<div class="main-content">', unsafe_allow_html=True)

col_main1, col_main2, col_main3 = st.columns([800, 300, 800])
with col_main2:
    # 이미지 주소
    image_url = "https://ugokawaii.com/wp-content/uploads/2023/06/ship.gif" 
    st.image(
    image_url,
    caption="Dash your shipping",  # 이미지 아래에 표시할 캡션
    width=150,                        # 이미지의 너비를 픽셀 단위로 지정 (생략 가능)
)

""
""

# 1. 헤더 (New Analysis, Clear, Analyze 버튼)
col_left, col_right = st.columns([0.8, 0.2])
with col_left:
    st.header("New Analysis")

with col_right:
    # 버튼들을 오른쪽으로 정렬
    col_clear, col_analyze = st.columns([1, 1])
    with col_clear:
        # Clear 버튼은 이미지에서 일반 텍스트 링크처럼 보임
        st.button("Clear", key="clear_button")
    with col_analyze:
        st.button("Analyze", key="analyze_button")


# 2. Configure Your Analysis 섹션
st.markdown("### Configure Your Analysis")
st.markdown("Enter the destination country and HTS code to receive comprehensive trade data and social media insights")

# 2-1. Destination Country
st.markdown("**Destination Country**")
st.selectbox("Select the target market country", ["Select the target market country", "USA", "Japan", "Vietnam"], label_visibility="collapsed")


# 2-2. HTS Code
st.markdown("**HTS Code**")
col_input, col_button = st.columns([0.8, 0.2])

with col_input:
    # HTS 코드 입력 필드는 세션 상태에 저장하여 모달에서 선택한 값으로 업데이트 가능하게 함
    if 'hts_code' not in st.session_state:
        st.session_state.hts_code = ''
        
    st.text_input("Enter product HTS code (e.g., 8517.12.00)", value=st.session_state.hts_code, label_visibility="collapsed", key="hts_input")

with col_button:
    # st.popover를 사용하여 'Find Code' 버튼 클릭 시 검색 창을 띄웁니다.
    with st.popover("🔎 Find Code", use_container_width=True):
        st.subheader("HTS Code Search")
        st.write("Search for your product's HTS code")
        
        search_query = st.text_input("Search by product detail", key="search_query")
        
        # 실제 데이터베이스 대신 예시 데이터를 사용합니다.
        hts_data = {
            "8517.12.00": "Smartphones",
            "8471.30.00": "Portable Digital Automatic Data Processing Machines (Laptops)",
            "8528.71.00": "Television Receivers, not designed to incorporate a video display"
        }
        
        if search_query:
            st.markdown("---")
            found = False
            for code, desc in hts_data.items():
                if search_query.lower() in desc.lower():
                    # 라디오 버튼 대신 버튼을 사용하여 모달 닫기 없이 선택하도록 유도
                    if st.button(f"**{code}** - {desc}", key=f"select_{code}"):
                        # 선택 시 st.session_state 값을 업데이트
                        st.session_state.hts_code = code
                        # 앱 전체를 다시 로드하여 입력 필드를 업데이트 (popover는 자동으로 닫히지 않음)
                        st.experimental_rerun() 
                        found = True

            if not found:
                st.write("No matching HTS codes found.")
        else:
             st.write("Enter product de to start searching.")
    
st.markdown("Don't know your HS code? Click \"Find Code\" to search our database")


# 3. Analysis Options 섹션
st.markdown("### Analysis Options")

col_trade, col_social = st.columns(2)
col_comp, col_forecast = st.columns(2)


# 박스형 체크박스 구현 (Streamlit의 기본 체크박스를 활용)
# 실제 박스 디자인을 하려면 더 많은 CSS가 필요하지만, 여기서는 구조만 만듭니다.

with col_trade:
    st.checkbox("**Trade Data Analysis**", value=True)
    st.caption("Export values, volumes, and trends")
    
with col_social:
    st.checkbox("**Social Media Trends**", value=True)
    st.caption("Sentiment and engagement analysis")

with col_comp:
    st.checkbox("**Competitor Analysis**", value=False)
    st.caption("Market share comparison")

with col_forecast:
    st.checkbox("**Forecast Model**", value=False)
    st.caption("Predictive insights")


# 4. Additional Notes
st.markdown("---")
st.markdown("Additional Notes (Optional)")
# st.text_area는 이미지의 텍스트 상자와 비슷하게 구현됩니다.
st.text_area("Notes", label_visibility="collapsed")

st.markdown('</div>', unsafe_allow_html=True)