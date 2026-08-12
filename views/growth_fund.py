# -*- coding: utf-8 -*-
"""🇰🇷 국민성장펀드 12대 산업 수혜주

app.py 라우팅에서 분리된 페이지. 함수 라이브러리는 core 에서 가져온다.
"""
from core import *


def render(ctx):
    _nav_changed = ctx['_nav_changed']
    api_key_input = ctx['api_key_input']

    st.markdown("## 🇰🇷 국민성장펀드 12대 산업 수혜주")
    st.write("정부 주도 **150조원 규모 국민성장펀드**가 집중 투자하는 12개 첨단전략산업을 선택하면, "
             "AI가 해당 분야의 국내(KRX) 핵심 수혜 대장주를 발굴하고 차트·수급 타점을 즉시 분석합니다.")

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("총 펀드 규모", GROWTH_FUND_ALLOC["총 규모"] + "원")
    c2.metric("AI 배정", GROWTH_FUND_ALLOC["AI"] + "원")
    c3.metric("반도체 배정", GROWTH_FUND_ALLOC["반도체"] + "원")
    c4.metric("모빌리티 배정", GROWTH_FUND_ALLOC["모빌리티"] + "원")
    st.caption("※ 금융위원회 지정 주목적 투자대상 12개 산업 기준. 개별 자펀드는 결성액의 60% 이상을 해당 산업에 투자합니다.")
    st.divider()

    if not api_key_input:
        st.warning("⚠️ 사이드바에 Gemini API 키를 입력하시면 수혜주 스캐너가 활성화됩니다.")
    else:
        st.markdown("### 🎯 분석할 첨단전략산업을 선택하세요")
        for cat_name, sectors in GROWTH_FUND_SECTORS.items():
            st.markdown(f"**{cat_name}**")
            cols = st.columns(len(sectors))
            for idx, (label, query) in enumerate(sectors):
                if cols[idx].button(label, key=f"gf_btn_{label}", use_container_width=True):
                    st.session_state.gf_sector_query = query
                    st.session_state.gf_results = None

        if st.session_state.gf_sector_query and st.session_state.gf_results is None:
            st.divider()
            q = st.session_state.gf_sector_query
            st.markdown(f"### 📈 '{q}' 국민성장펀드 수혜주 정밀 분석")
            with st.spinner(f"✨ '{q}' 분야의 국내 핵심 수혜주 및 밸류체인을 필터링 중입니다..."):
                gf_stocks = get_growth_fund_stocks_with_ai(q, api_key_input)

            if gf_stocks:
                progress_bar = st.progress(0.0)
                status_text = st.empty()
                gf_res_list = []
                completed, total = 0, len(gf_stocks)

                def process_gf_stock(item):
                    name, code = item
                    time.sleep(0.1)
                    return analyze_technical_pattern(name, code)

                with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
                    futures = {executor.submit(process_gf_stock, t): t for t in gf_stocks}
                    for future in concurrent.futures.as_completed(futures):
                        res = future.result()
                        completed += 1
                        if res:
                            gf_res_list.append(res)
                        progress_bar.progress(min(1.0, completed / total))
                        status_text.text(f"⚡ KRX 재무/차트 데이터 파싱 중... ({completed}/{total}) - {len(gf_res_list)}개 타점 확보")

                st.session_state.gf_results = gf_res_list
            else:
                st.error(f"❌ '{q}' 분야 수혜주를 찾지 못했습니다. 다시 시도해주세요.")
                st.session_state.gf_sector_query = None

        if st.session_state.gf_results is not None:
            st.info(f"💡 **{st.session_state.gf_sector_query}** 분야의 국민성장펀드 정책 수혜 기대 종목입니다. "
                    "(아래에서 RSI·수급 기준 정렬 가능)")
            display_sorted_results(st.session_state.gf_results, tab_key="gf", api_key=api_key_input, show_leader_rank=True)
