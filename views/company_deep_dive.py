# -*- coding: utf-8 -*-
"""🔬 개별 기업 정밀 진단 (AI 비전)

app.py 라우팅에서 분리된 페이지. 함수 라이브러리는 core 에서 가져온다.
"""
from core import *


def render(ctx):
    _nav_changed = ctx['_nav_changed']
    api_key_input = ctx['api_key_input']

    st.markdown("## 🔬 개별 기업 정밀 진단 (AI 비전)")
    st.caption("👁️ 차트 이미지(캡처) AI 비전 분석은 사이드바 **[심층 분석 & 도구] → 👁️ 차트 이미지 AI 비전 분석** 메뉴로 이동했습니다.")
    market_choice = st.radio("시장 선택", ["🇰🇷 국내 주식", "🇺🇸 미국 주식"], horizontal=True)
    if market_choice == "🇰🇷 국내 주식":
        krx_df = get_krx_stocks()
        searched_name = searched_code = None
        do_analyze = False
        if not krx_df.empty:
            opts = ["🔍 분석할 국내 종목을 검색/선택하세요"] + (krx_df['Name'].astype(str) + " (" + krx_df['Code'].astype(str) + ")").tolist()
            col_s1, col_s2 = st.columns([8, 2])
            with col_s1: kr_query = st.selectbox("👇 종목명/코드 검색:", opts, label_visibility="collapsed")
            with col_s2: kr_search_btn = st.button("📊 분석 시작", use_container_width=True)
            if kr_query != "🔍 분석할 국내 종목을 검색/선택하세요" and (kr_query or kr_search_btn):
                searched_name = kr_query.rsplit(" (", 1)[0]
                searched_code = kr_query.rsplit("(", 1)[-1].replace(")", "").strip()
                do_analyze = True
        else:
            # 폴백: 종목 목록 로드 실패 시 종목코드 직접 입력
            st.warning("⚠️ 국내 종목 목록을 일시적으로 불러오지 못했습니다. 아래에 **종목코드 6자리**를 직접 입력해 분석하세요. (예: 005930)")
            col_s1, col_s2 = st.columns([8, 2])
            with col_s1: kr_manual = st.text_input("종목코드/이름 입력:", placeholder="예: 005930  또는  005930 삼성전자", label_visibility="collapsed", key="kr_manual_in")
            with col_s2: kr_manual_btn = st.button("📊 분석 시작", use_container_width=True, key="kr_manual_btn")
            if kr_manual:
                m = re.search(r"\d{6}", kr_manual)
                if m:
                    searched_code = m.group()
                    searched_name = kr_manual.replace(searched_code, "").strip() or searched_code
                    do_analyze = True
                elif kr_manual_btn:
                    st.error("6자리 종목코드를 포함해 입력해 주세요. 예: 005930")
        if do_analyze and searched_code:
            with st.spinner(f"📡 '{searched_name}' 타점 분석 중..."):
                res = analyze_technical_pattern(searched_name, searched_code)
                if res:
                    # 🌟 다중 테마 뷰어 출력 (국내 주식) 🌟
                    render_single_stock_themes(searched_name, api_key_input)
                    draw_stock_card(res, api_key_str=api_key_input, is_expanded=True, key_suffix="t4_kr")
                else:
                    st.error("❌ 데이터 로드 실패 — 종목코드를 확인해 주세요.")
    else:
        col_us1, col_us2 = st.columns([8, 2])
        with col_us1: us_query = st.text_input("👇 미국 주식 종목명/티커 입력 (예: AAPL):", label_visibility="collapsed")
        with col_us2: us_search_btn = st.button("🔍 검색", use_container_width=True)
        if us_query or us_search_btn:
            with st.spinner(f"📡 검색 중..."): us_results = search_us_ticker(us_query)
            if us_results: st.session_state.us_search_results = us_results
            else: st.error("❌ 검색 결과 없음")
        
        if "us_search_results" in st.session_state and st.session_state.us_search_results:
            sel_us_opt = st.selectbox("🎯 정확한 종목 선택:", ["선택하세요"] + st.session_state.us_search_results)
            analyze_btn = st.button("📊 분석 시작", use_container_width=True)
            if analyze_btn and sel_us_opt != "선택하세요":
                us_ticker = sel_us_opt.split(" ")[0]
                with st.spinner(f"📡 '{us_ticker}' 분석 중..."):
                    _res_us = analyze_technical_pattern(us_ticker, us_ticker)
                st.session_state.indiv_result_us = {"res": _res_us, "ticker": us_ticker} if _res_us else None
                if not _res_us:
                    st.error("❌ 데이터 로드 실패 — 종목을 확인해 주세요.")
            # 분석 결과를 세션에 보존 → 질의응답 토글 등 리런에도 카드가 사라지지 않음
            _ir_us = st.session_state.get("indiv_result_us")
            if _ir_us and _ir_us.get("res"):
                render_single_stock_themes(_ir_us["ticker"], api_key_input)
                draw_stock_card(_ir_us["res"], api_key_str=api_key_input, is_expanded=True, key_suffix="t4_us")
