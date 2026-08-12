# -*- coding: utf-8 -*-
"""📰 뉴스 패널 모음 — '뉴스' 메뉴의 탭들.

[통합] 예전에는 '📰 실시간 특징주 속보 & 리포트'라는 독립 메뉴 안에 탭 3개가
들어 있었다. 지금은 views/news.py 가 이슈 분석과 함께 한 층으로 펼쳐 보여준다.
탭 안에 탭이 또 있으면 어디를 눌러야 할지 알기 어렵다. 내용은 그대로다.
"""
from core import *


def flash_panel(ctx):
    """실시간 특징주/속보"""
    api_key_input = ctx.get("api_key_input", "")

    if st.button("🔄 속보 리로드"): 
        st.session_state.news_data = []
        st.session_state.seen_links = set()
        st.session_state.seen_titles = set()
        get_latest_naver_news.clear()
        st.rerun()
    with st.spinner("뉴스를 불러오는 중..."): update_news_state()

    # iterrows 제거: 2,800여 행을 매 새로고침마다 순회하던 것을 컬럼 벡터화로 대체
    _krx_df = get_krx_stocks()
    _name_ok = _krx_df['Name'].astype(str).str.len() > 1
    krx_dict = dict(zip(_krx_df.loc[_name_ok, 'Name'], _krx_df.loc[_name_ok, 'Code']))
    news_aliases = {"삼전": ("삼성전자", "005930"), "하이닉스": ("SK하이닉스", "000660"), "현차": ("현대차", "005380"), "엔솔": ("LG에너지솔루션", "373220")}
    sorted_names = sorted(krx_dict.keys(), key=len, reverse=True)

    for i, news in enumerate(st.session_state.news_data[:50]):
        title = news['title']
        found_comps = []
        for alias, (real_name, fallback_code) in news_aliases.items():
            if alias in title:
                found_comps.append((real_name, krx_dict.get(real_name, fallback_code)))
                break
        if not found_comps:
            for name in sorted_names:
                if name in title:
                    found_comps.append((name, krx_dict[name]))
                    break 

        with st.container(border=True):
            cols = st.columns([1, 6, 2, 1])
            cols[0].markdown(f"**🕒 {news['time']}**")
            cols[1].markdown(f"{title}")
            with cols[2]:
                if found_comps:
                    if st.button(f"🔍 {found_comps[0][0]} 분석", key=f"qa_{i}"):
                        st.session_state[f"news_analyze_{i}"] = not st.session_state.get(f"news_analyze_{i}", False)
            cols[3].link_button("원문🔗", news['link'])

        if st.session_state.get(f"news_analyze_{i}", False):
            with st.spinner(f"'{found_comps[0][0]}' 차트 분석 중..."):
                res = analyze_technical_pattern(found_comps[0][0], found_comps[0][1])
                if res: draw_stock_card(res, api_key_str=api_key_input, is_expanded=True, key_suffix=f"news_qa_{i}")



def report_panel(ctx):
    """증권사 종목 리포트 검색"""
    api_key_input = ctx.get("api_key_input", "")

    st.markdown("### 📋 당일 실시간 리포트 & 종목별 과거 리포트 검색")

    st.markdown("#### 🔍 특정 종목 리포트 검색 (최근 6개월)")
    search_krx_df = get_krx_stocks()
    if not search_krx_df.empty:
        opts = ["선택 안함 (당일 전체 신규 리포트 보기)"] + (search_krx_df['Name'].astype(str) + " (" + search_krx_df['Code'].astype(str) + ")").tolist()
        report_query = st.selectbox("리포트를 검색할 종목을 선택하세요:", opts)

        if report_query != "선택 안함 (당일 전체 신규 리포트 보기)":
            q_name = report_query.rsplit(" (", 1)[0]
            q_code = report_query.rsplit("(", 1)[-1].replace(")", "").strip()

            with st.spinner(f"'{q_name}'의 최근 6개월 리포트를 검색 중입니다..."):
                history_df = get_stock_research_history(q_code)

            if not history_df.empty:
                st.success(f"✅ '{q_name}' 관련 리포트 {len(history_df)}건을 찾았습니다.")
                display_history_df = history_df[['작성일', '증권사', '제목', '적정가격', '투자의견', '원문링크']].copy()
                display_history_df['적정가격'] = display_history_df['적정가격'].apply(lambda x: f"{x:,}원" if x > 0 else "-")
                st.dataframe(
                    display_history_df, 
                    column_config={"원문링크": st.column_config.LinkColumn("원문 보기")},
                    use_container_width=True, hide_index=True
                )
            else:
                st.warning("해당 종목의 최근 6개월 내 발간된 증권사 리포트가 없습니다.")

            st.divider()

    st.markdown("#### 🆕 오늘의 전체 신규 리포트")
    with st.spinner("당일 리포트의 투자의견·목표가를 분석 중입니다..."):
        res_df = get_today_research_details()
    if not res_df.empty:
        if api_key_input and st.button("🤖 AI 당일 리포트 종합 의견 및 섹터 요약", use_container_width=True, type="primary"):
            with st.spinner("당일 발간된 리포트들을 분석하여 시장 분위기와 유망 섹터를 요약 중입니다..."):
                report_text = "\n".join([f"- [{r['증권사']}] {r['종목명']} (의견:{r['투자의견']}): {r['제목']}" for _, r in res_df.head(30).iterrows()])
                prompt = f"당신은 증권사 리서치 센터장입니다. 오늘 발간된 다음 증권사 리포트 제목들을 분석하여, 1) 오늘 증권가가 가장 주목하는 핵심 섹터/테마 2개와 그 이유, 2) 시장의 전반적인 투자의견 요약을 마크다운으로 작성해주세요.\n\n[오늘의 리포트]\n{report_text}"
                st.info(ask_gemini(prompt, api_key_input), icon="💡")

        show_df = res_df[['종목명', '증권사', '제목', '투자의견', '목표가', '변동', '작성일', '원문링크']].copy()
        show_df['목표가'] = show_df['목표가'].apply(lambda x: f"{int(x):,}원" if x and x > 0 else "-")
        st.dataframe(
            show_df,
            column_config={"원문링크": st.column_config.LinkColumn("원문 보기")},
            use_container_width=True, hide_index=True
        )
    else:
        st.error("❌ 리포트 데이터를 불러오지 못했습니다.")



def daily_panel(ctx):
    """AI 데일리 리포트"""
    api_key_input = ctx.get("api_key_input", "")

    st.markdown("### 🤖 Auto Research Desk (오늘의 증권가 종합 분석)")
    st.write("기관 트레이딩 데스크 수준의 일일 요약, 쟁점 분석, 목표가 랭킹을 AI가 생성합니다.")
    if api_key_input:
        if st.button("🚀 TEBI-Style 모닝 리포트 생성 시작", type="primary"):
            with st.spinner("오늘 발간된 30개의 증권사 리포트 원문을 AI가 해독 및 분석 중입니다..."):
                today_reports = get_today_research_details()
                if not today_reports.empty:
                    # 투자의견은 standardize_opinion으로 '강력매수/매수/중립/매도/N/A' 정규화됨
                    op = today_reports['투자의견'].astype(str)
                    buy_mask = op.isin(['강력매수', '매수'])
                    sell_mask = op.eq('매도')
                    buys = int(buy_mask.sum())
                    sells = int(sell_mask.sum())
                    holds = len(today_reports) - buys - sells

                    st.markdown("#### 📊 오늘의 증권가 투자의견 요약 (Verdict)")
                    c1, c2, c3, c4 = st.columns(4)
                    c1.metric("총 발간 리포트", f"{len(today_reports)}건")
                    c2.metric("BUY (매수·강력매수)", f"{buys}건")
                    c3.metric("HOLD/기타", f"{holds}건")
                    c4.metric("SELL (매도)", f"{sells}건")

                    # 매수의견 종목 목록 — 'BUY n건'이 어떤 종목인지 바로 확인
                    if buys > 0:
                        def _prc_buyops():
                            buy_tbl = today_reports[buy_mask][['종목명', '증권사', '투자의견', '목표가', '제목']].copy()
                            buy_tbl['목표가'] = buy_tbl['목표가'].apply(lambda x: f"{int(x):,}원" if x and x > 0 else "-")
                            st.dataframe(buy_tbl, use_container_width=True, hide_index=True)
                        _register_popup("buyops", _prc_buyops)
                        _popup_button(f"🔴 매수의견 종목 {buys}건 보기", "buyops", f"🔴 매수의견 종목 {buys}건", key="btn_buyops")

                    st.markdown("#### 📈 당일 목표가(TP) 상/하향 랭킹")
                    st.caption("💡 증권사가 직전 리포트 대비 목표가를 올렸으면 🔴상향, 내렸으면 🔵하향. "
                               "원문에 '종전 목표가'가 없으면 `유지/신규`로 분류되어 이 랭킹에는 나오지 않습니다. "
                               "따라서 위 BUY 건수와 아래 상향 건수는 서로 다른 지표입니다.")
                    upgrades = today_reports[today_reports['변동'] == '상향'].sort_values('변동률', ascending=False)
                    downgrades = today_reports[today_reports['변동'] == '하향'].sort_values('변동률', ascending=True)

                    col_up, col_down = st.columns(2)
                    with col_up:
                        st.success(f"**▲ 상향 리포트 ({len(upgrades)}건)**")
                        sty_up = style_report_table(upgrades, "up")
                        if sty_up is not None:
                            st.dataframe(sty_up, use_container_width=True, height=min(420, 80 + len(upgrades) * 36))
                        else:
                            st.write("목표가 상향 종목이 없습니다.")

                    with col_down:
                        st.error(f"**▼ 하향 리포트 ({len(downgrades)}건)**")
                        sty_down = style_report_table(downgrades, "down")
                        if sty_down is not None:
                            st.dataframe(sty_down, use_container_width=True, height=min(420, 80 + len(downgrades) * 36))
                        else:
                            st.write("목표가 하향 종목이 없습니다.")

                    st.markdown("#### ⚔️ 애널리스트 갑론을박 & 💡 Bottom Line")
                    report_texts = "\n".join([f"- [{r['증권사']}] {r['종목명']} (의견: {r['투자의견']}, TP변동: {r['변동']}): {r['제목']}" for _, r in today_reports.iterrows()])
                    prompt = f"""
                    당신은 기관 프랍 트레이더를 위한 수석 퀀트 애널리스트입니다. 오늘 한국 증시에서 발간된 증권사 리포트 목록입니다:
                    {report_texts}

                    다음 3가지를 마크다운으로 명확하게 작성하세요:
                    1. **🔥 주도 섹터 및 핵심 모멘텀**: 오늘 리포트들이 가장 집중적으로 다루고 있는(목표가 상향이 많은) 핵심 섹터 1~2개와 그 이유.
                    2. **⚔️ 애널리스트 갑론을박 (Debate)**: 시장에서 의견이 엇갈리는 종목이나 섹터를 찾아 강세(Bull) 논리와 약세/보수적(Bear) 논리를 대비시켜 서술하세요.
                    3. **💡 Bottom Line (최종 액션 플랜)**: 전체적인 매수/매도 비율을 고려했을 때, 투자자가 오늘 취해야 할 명확한 행동 지침(예: 적극 매수, 차익 실현 등)을 3줄로 결론지으세요.
                    """
                    st.info(ask_gemini(prompt, api_key_input))
                else:
                    st.error("리포트 데이터를 파싱하지 못했습니다.")
    else:
        st.warning("API 키를 입력해야 AI 데일리 리포트를 생성할 수 있습니다.")


