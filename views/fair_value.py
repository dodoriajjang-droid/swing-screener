# -*- coding: utf-8 -*-
"""⚖️ 적정 주가 계산기 (버핏 모델)

app.py 라우팅에서 분리된 페이지. 함수 라이브러리는 core 에서 가져온다.
"""
from core import *


def render(ctx):
    _nav_changed = ctx['_nav_changed']
    api_key_input = ctx['api_key_input']

    st.markdown("## ⚖️ 적정 주가 계산기 (버핏 모델)")
    b_tab1, b_tab2, b_tab3 = st.tabs(["📊 적정 주가 계산기 (DCF 모델)", "📈 버핏 지수 & 72의 법칙", "🔍 퀀트 스크리닝 가이드"])
    
    with b_tab1:
        st.markdown("### 📊 잉여현금흐름(FCF) 기반 내재가치 계산기")
        market_choice_dcf = st.radio("시장 선택 (가치평가)", ["🇰🇷 국내 주식", "🇺🇸 미국 주식"], horizontal=True, key="dcf_market")
        
        # 💡 [버그 수정] Streamlit Rerun 시 화면이 닫히지 않도록 세션 상태(Session State)에 종목 정보 저장
        if 'dcf_sel_ticker' not in st.session_state: st.session_state.dcf_sel_ticker = None
        if 'dcf_sel_name' not in st.session_state: st.session_state.dcf_sel_name = ""
        
        is_us_dcf = (market_choice_dcf == "🇺🇸 미국 주식")
        
        if not is_us_dcf:
            krx_df = get_krx_stocks()
            if not krx_df.empty:
                opts = ["🔍 평가할 국내 종목을 선택하세요."] + (krx_df['Name'].astype(str) + " (" + krx_df['Code'].astype(str) + ")").tolist()
                with st.form("dcf_kr_form"):
                    col_dcf1, col_dcf2 = st.columns([8, 2])
                    with col_dcf1: query = st.selectbox("👇 종목명 검색:", opts, key="dcf_kr_search", label_visibility="collapsed")
                    with col_dcf2: dcf_kr_btn = st.form_submit_button("🔍 데이터 로드", use_container_width=True)
                    if dcf_kr_btn and query != "🔍 평가할 국내 종목을 선택하세요.":
                        st.session_state.dcf_sel_name = query.rsplit(" (", 1)[0]
                        st.session_state.dcf_sel_ticker = query.rsplit("(", 1)[-1].replace(")", "").strip()
        else:
            with st.form("dcf_us_form"):
                col_dcf_us1, col_dcf_us2 = st.columns([8, 2])
                with col_dcf_us1: us_query = st.text_input("👇 미국 주식 종목명/티커 (예: AAPL):", key="dcf_us_input", label_visibility="collapsed")
                with col_dcf_us2: dcf_us_search_btn = st.form_submit_button("🔍 검색", use_container_width=True)
            if dcf_us_search_btn and us_query:
                with st.spinner("검색 중..."): us_results = search_us_ticker(us_query)
                if us_results: st.session_state.dcf_us_results = us_results
                else: st.error("검색 결과가 없습니다.")
            if "dcf_us_results" in st.session_state and st.session_state.dcf_us_results:
                sel_us_opt = st.selectbox("🎯 정확한 종목을 선택해주세요:", ["선택하세요"] + st.session_state.dcf_us_results)
                if sel_us_opt != "선택하세요":
                    st.session_state.dcf_sel_ticker = sel_us_opt.split(" ")[0]
                    st.session_state.dcf_sel_name = sel_us_opt.split(" (")[1].split(" /")[0]

        # 💡 기존 로컬 변수 대신 영구적으로 유지되는 세션 상태 변수 사용
        if st.session_state.dcf_sel_ticker:
            st.success(f"✅ [{st.session_state.dcf_sel_name}] 기초 데이터 로드 완료")
            _, _, fcf_val, shares_val, _ = get_fundamentals(st.session_state.dcf_sel_ticker)
            default_price, res = 0.0, analyze_technical_pattern(st.session_state.dcf_sel_name, st.session_state.dcf_sel_ticker)
            if res: default_price = float(res['현재가'])
            default_fcf = float(fcf_val) if fcf_val and pd.notna(fcf_val) else 1000.0
            default_shares = float(shares_val) if shares_val and pd.notna(shares_val) else 100.0

            st.markdown("#### ⚙️ DCF 파라미터 입력")
            col_dcf_p1, col_dcf_p2 = st.columns(2)
            with col_dcf_p1:
                input_price = st.number_input("현재 주가", value=default_price, step=1.0)
                input_fcf = st.number_input("최근 잉여현금흐름(FCF)", value=default_fcf, step=100.0)
                input_shares = st.number_input("유통 주식수", value=default_shares, step=10.0)
            with col_dcf_p2:
                growth_rate = st.slider("예상 연평균 성장률 (%)", 1.0, 50.0, 10.0)
                discount_rate = st.slider("할인율 (요구수익률) (%)", 5.0, 20.0, 9.0)
                terminal_growth = st.slider("영구 성장률 (%)", 1.0, 5.0, 2.5)

            # 이 버튼을 눌러도 이제 화면이 날아가지 않습니다!
            if st.button("🧮 적정 주가 연산", type="primary", use_container_width=True):
                with st.spinner("미래 현금흐름 할인 연산 중..."):
                    future_fcfs = []
                    current_fcf = input_fcf
                    for i in range(1, 11):
                        current_fcf *= (1 + growth_rate/100)
                        future_fcfs.append(current_fcf / ((1 + discount_rate/100) ** i))
                    
                    terminal_value = (current_fcf * (1 + terminal_growth/100)) / ((discount_rate/100) - (terminal_growth/100))
                    discounted_tv = terminal_value / ((1 + discount_rate/100) ** 10)
                    total_value = sum(future_fcfs) + discounted_tv
                    
                    # 💡 [치명적 버그 수정] FCF(억/10^8)와 주식수(백만/10^6) 단위 스케일링을 위해 100을 곱함
                    fair_price = (total_value / input_shares) * 100 if input_shares > 0 else 0
                    
                    margin_of_safety = ((fair_price - input_price) / fair_price) * 100 if fair_price > 0 else 0
                    
                    st.divider()
                    st.markdown(f"### 🎯 [{st.session_state.dcf_sel_name}] DCF 가치평가 결과")
                    c1, c2, c3 = st.columns(3)
                    c1.metric("현재 주가", f"{input_price:,.2f}")
                    c2.metric("DCF 적정 주가", f"{fair_price:,.2f}")
                    c3.metric("안전 마진", f"{margin_of_safety:+.1f}%", delta_color="normal" if margin_of_safety > 0 else "inverse")
                    
                    if margin_of_safety > 20: st.success("🟢 **강력 매수 구간**: 현재 주가가 내재가치 대비 20% 이상 저렴합니다.")
                    elif margin_of_safety > 0: st.info("🔵 **매수 구간**: 현재 주가가 내재가치보다 저렴합니다.")
                    elif margin_of_safety > -20: st.warning("🟡 **적정 가치 구간**: 주가가 내재가치와 비슷하게 형성되어 있습니다.")
                    else: st.error("🔴 **고평가 구간**: 현재 주가가 미래 성장성을 이미 과도하게 반영하고 있을 수 있습니다.")

    with b_tab2:
        st.markdown("### 📈 버핏 지수 (Buffett Indicator)")
        st.write("국가의 시가총액을 명목 GDP로 나눈 값으로, 증시 전체의 고평가/저평가 여부를 판단합니다.")
        buffett_ratio = 115.5 
        st.metric("현재 한국 증시 추정 버핏 지수", f"{buffett_ratio}%")
        if buffett_ratio > 120: st.error("🚨 증시가 역사적 고평가 상태입니다. 현금 비중을 늘리는 것을 고려하세요.")
        elif buffett_ratio > 80: st.success("✅ 시장이 적정 가치 구간에 있습니다.")
        else: st.info("💰 시장이 저평가 상태입니다. 적극적인 매수 기회일 수 있습니다.")
            
        st.divider()
        st.markdown("### ⏱️ 복리 계산기 (72의 법칙)")
        return_rate = st.slider("목표 연평균 수익률 (%)", min_value=1.0, max_value=30.0, value=15.0, step=0.5)
        years_to_double = 72 / return_rate
        st.markdown(f"👉 연수익률 **{return_rate}%** 유지 시, 원금이 2배가 되는 데 약 **<span style='color:#ff4b4b; font-size:24px;'>{years_to_double:.1f}년</span>**이 걸립니다.", unsafe_allow_html=True)

    with b_tab3:
        st.markdown("### 🔍 퀀트식 버핏 전략 스크리닝 기준")
        st.info("실제 시중 퀀트 플랫폼(퀀터스 등)에서 워런 버핏 스타일의 알짜 가치주를 찾기 위해 설정해야 하는 검색 조건식 가이드입니다.")
        st.markdown("""
        1. **ROE (자기자본이익률)**: 과거 3~5년 평균 **15% 이상** 꾸준히 유지
        2. **영업이익률**: 동종 업계 평균 대비 우위 (최소 **10% 이상**)
        3. **부채비율**: **100% 이하** (금융업 제외)
        4. **FCF (잉여현금흐름)**: 최근 3년 연속 **흑자** 및 증가 추세
        5. **PBR (주가순자산비율)**: 가급적 **1.5 이하** (절대적 기준은 아니며 ROE와 결합하여 판단)
        6. **경제적 해자**: 위 1~5번이 숫자로 증명되며, 브랜드 파워나 독점적 기술력(워런 버핏의 '소비자 독점 기업')을 가진 기업
        """)
