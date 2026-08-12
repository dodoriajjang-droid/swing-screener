# -*- coding: utf-8 -*-
"""🌅 간밤의 미국 급등주 & 수혜주

app.py 라우팅에서 분리된 페이지. 함수 라이브러리는 core 에서 가져온다.
"""
from core import *


def render(ctx):
    _nav_changed = ctx['_nav_changed']
    api_key_input = ctx['api_key_input']

    st.markdown("## 🌅 간밤의 미국 급등주 & 수혜주")
    st.caption("간밤 미국 증시에서 급등한 종목 → AI가 한국 수혜주(밸류체인)를 찾아주고 → 그 수혜주의 매매 타점까지 한 번에 확인하는 페이지입니다.")

    # [v7.0] ① 간밤 미국 시황 미니 배너 — 급등주 보기 전 위험선호부터 파악
    st.markdown("#### 🌙 간밤 미국 시황 (Risk-On / Off 체크)")
    with st.spinner("간밤 지수·VIX·환율 수집 중..."):
        render_overnight_banner()
    st.caption("💡 VIX(공포지수)가 급등하거나 지수가 크게 빠진 날은, 미국 급등주가 있어도 국장이 위험회피로 갈 수 있으니 보수적으로 접근하세요.")

    # [v7.0] ② 초보자 가이드 배치 (이 페이지도 타점 분석을 쓰므로)
    show_beginner_guide()
    show_trading_guidelines()
    st.divider()

    col_sec, col_gain = st.columns([1, 1.2], gap="large")
    with col_sec:
        st.subheader("📊 1. 미 증시 주도 섹터 (ETF)")
        st.caption("간밤 어느 섹터로 돈이 몰렸는지 (등락률 높은 순). 🔴빨강=상승 / 🔵파랑=하락")
        with st.spinner("섹터 ETF 등락률 산출 중..."):
            etf_df = get_us_sector_etfs()
            sty_etf = style_sector_etf_table(etf_df)
            if sty_etf is not None:
                st.dataframe(sty_etf, use_container_width=True, height=400)
            elif not etf_df.empty:
                st.dataframe(etf_df, use_container_width=True, hide_index=True)

        st.subheader("🚀 2. 글로벌 급등주 필터링")
        # 이 페이지가 급등주 데이터를 실제로 쓰는 곳 — 여기서 처음 받아온다(지연 로딩)
        with st.spinner("미국 급등주 수집 중..."):
            ensure_us_gainers()
        fetch_t = st.session_state.get('us_fetch_time', '-')
        rc1, rc2 = st.columns([3, 1])
        rc1.caption(f"기준 시각: {fetch_t} (KST) · 전일 대비 +5% 이상 급등주")
        if rc2.button("🔄 새로고침", use_container_width=True, key="refresh_gainers"):
            get_us_top_gainers.clear()
            df, ex_rate, ft = get_us_top_gainers()
            st.session_state.gainers_df = df
            st.session_state.ex_rate = ex_rate
            st.session_state.us_fetch_time = ft
            st.rerun()

        if not st.session_state.gainers_df.empty:
            sty_g = style_us_gainers_table(st.session_state.gainers_df)
            if sty_g is not None:
                st.dataframe(sty_g, use_container_width=True, height=420)
            else:
                st.dataframe(st.session_state.gainers_df, use_container_width=True, hide_index=True)
            opts = ["🔍 종목 선택"] + [f"{r['종목코드']} ({r['기업명']})" for _, r in st.session_state.gainers_df.iterrows()]
            sel_opt = st.selectbox("🎯 분석할 주도주 선택", opts)
            sel_tick = "N/A" if sel_opt == "🔍 종목 선택" else sel_opt.split(" ")[0]
        else:
            sel_tick = "N/A"
            sel_opt = "🔍 종목 선택"
            st.error("❌ 현재 급등주 데이터를 불러올 수 없습니다. (장 마감 직후·주말이면 데이터가 없을 수 있어요) 새로고침을 눌러보세요.")

    with col_gain:
        st.subheader("🔗 3. 글로벌 밸류체인 & 갭상승 대응 시나리오")
        if sel_tick != "N/A" and api_key_input:
            comp_name = sel_opt.split(" (")[1].replace(")", "")
            krx_df = get_krx_stocks()

            # [v7.0] 같은 종목이면 AI를 다시 부르지 않도록 세션에 캐싱 (폼 클릭 시 재호출 방지)
            if st.session_state.get('us_vc_ticker') != sel_tick:
                with st.spinner(f"✨ AI가 '{sel_tick}'의 공급망과 국장 수혜주를 분석 중입니다..."):
                    prompt = (
                        f"간밤에 미국 증시에서 '{comp_name}({sel_tick})' 종목이 급등했습니다. "
                        f"1.급등사유 2.한국 수혜주 3~5개(각 종목의 수혜 이유 포함) 3.시초가 갭상승 대응 시나리오를 작성하세요.\n"
                        f"⚠️ 반드시 맨 마지막 줄에 한국거래소에 상장된 정확한 종목명만 다음 형식으로 나열하세요: "
                        f"[수혜주]: 종목명1, 종목명2, 종목명3"
                    )
                    report = ask_gemini(prompt, api_key_input)
                    beneficiaries = extract_beneficiary_stocks(report, krx_df)
                    st.session_state.us_vc_ticker = sel_tick
                    st.session_state.us_vc_report = report
                    st.session_state.us_vc_benef = beneficiaries

            report = st.session_state.get('us_vc_report', '')
            beneficiaries = st.session_state.get('us_vc_benef', [])

            st.success("✅ 밸류체인 및 대응 시나리오 분석 완료!")
            # 화면에는 [수혜주] 파싱용 라인은 숨겨서 깔끔하게 표시
            display_report = re.sub(r'\n?\[?\s*수혜주[^\]:：]*\]?\s*[:：].*$', '', report).strip()
            st.markdown(display_report)

            st.divider()
            st.subheader("🎯 추천된 국장 수혜주 타점 즉시 확인")
            if beneficiaries:
                st.caption(f"💡 위 AI 분석에서 언급된 한국 수혜주 {len(beneficiaries)}개만 골라뒀어요. 선택하면 바로 타점을 분석합니다.")
                opts_krx = ["🔍 추천 수혜주 선택"] + [f"{n} ({c})" for n, c in beneficiaries]
                with st.form("vs_kr_form"):
                    col_v1, col_v2 = st.columns([8, 2])
                    with col_v1: us_sub_query = st.selectbox("추천 수혜주 타점 확인:", opts_krx, key="us_sub_scan", label_visibility="collapsed")
                    with col_v2: vs_btn = st.form_submit_button("🔍 타점 확인", use_container_width=True)
                if vs_btn and us_sub_query != "🔍 추천 수혜주 선택":
                    q_name = us_sub_query.rsplit(" (", 1)[0]
                    q_code = us_sub_query.rsplit("(", 1)[-1].replace(")", "").strip()
                    with st.spinner("차트 타점 분석 중..."):
                        res = analyze_technical_pattern(q_name, q_code)
                        if res: draw_stock_card(res, api_key_str=api_key_input, is_expanded=True, key_suffix="us_val_chain")
                        else: st.error("❌ 해당 종목 데이터를 불러올 수 없습니다.")
            else:
                st.warning("AI 분석에서 한국 수혜주를 자동으로 추출하지 못했어요. 아래에서 직접 검색해 확인할 수 있습니다.")
                if not krx_df.empty:
                    opts_krx = ["🔍 종목명 검색 후 엔터"] + (krx_df['Name'].astype(str) + " (" + krx_df['Code'].astype(str) + ")").tolist()
                    with st.form("vs_kr_form_fallback"):
                        col_v1, col_v2 = st.columns([8, 2])
                        with col_v1: us_sub_query = st.selectbox("수혜주 차트 상태 확인:", opts_krx, key="us_sub_scan_fb", label_visibility="collapsed")
                        with col_v2: vs_btn = st.form_submit_button("🔍 타점 확인", use_container_width=True)
                    if vs_btn and us_sub_query != "🔍 종목명 검색 후 엔터":
                        q_name = us_sub_query.rsplit(" (", 1)[0]
                        q_code = us_sub_query.rsplit("(", 1)[-1].replace(")", "").strip()
                        with st.spinner("차트 타점 분석 중..."):
                            res = analyze_technical_pattern(q_name, q_code)
                            if res: draw_stock_card(res, api_key_str=api_key_input, is_expanded=True, key_suffix="us_val_chain_fb")
                            else: st.error("❌ 해당 종목 데이터를 불러올 수 없습니다.")
        elif sel_tick != "N/A" and not api_key_input:
            st.warning("⬅️ 왼쪽에서 종목은 선택됐어요. AI 밸류체인 분석을 보려면 사이드바에 API 키를 입력해주세요.")
        else:
            st.info("⬅️ 왼쪽 급등주 목록에서 분석할 종목을 선택하면, AI가 한국 수혜주와 대응 시나리오를 여기에 보여줍니다.")
