# -*- coding: utf-8 -*-
"""🐋 국장 수급 분석 (외국인·기관·개인)

app.py 라우팅에서 분리된 페이지. 함수 라이브러리는 core 에서 가져온다.
"""
from core import *


def render(ctx):
    _nav_changed = ctx['_nav_changed']
    api_key_input = ctx['api_key_input']

    st.markdown("## 🐋 국장 수급 분석 (외국인·기관·개인)")
    st.caption("최근 거래일 기준 · 거래대금 상위 종목 스캔 · 단위: 억원 · 🔴빨강=순매수/상승 · 🔵파랑=순매도/하락")
    with st.spinner("네이버 투자자별 순매수 데이터 수집 중... (첫 조회는 십수 초, 이후 30분 캐시)"):
        flows = get_kr_investor_flows()
    if flows is None or flows.empty:
        st.error("❌ 수급 데이터를 불러오지 못했습니다. 잠시 후 다시 시도해주세요.")
    else:
        st.caption(f"📊 거래대금 상위 {len(flows)}개 종목 분석 · 개인은 외국인·기관의 반대값으로 추정")
        t_top, t_smart, t_hand = st.tabs(
            ["🏆 순매수·순매도 TOP", "🧠 개미 vs 스마트머니", "🔄 수급 주체 손바뀜"])
        with t_top:
            for emoji, inv, note in [("🦅", "외국인", ""), ("🏛️", "기관", ""), ("🐜", "개인", " (추정)")]:
                st.markdown(f"#### {emoji} {inv}{note}")
                cb, cs = st.columns(2)
                with cb:
                    st.markdown("**🔴 순매수 TOP10**")
                    _render_netbuy_list(flows, inv, ascending=False)
                with cs:
                    st.markdown("**🔵 순매도 TOP10**")
                    _render_netbuy_list(flows, inv, ascending=True)
                st.markdown("<div style='height:6px;'></div>", unsafe_allow_html=True)
        with t_smart:
            st.caption("스마트머니 = 외국인+기관 합산. (네이버 데이터 특성상 개인은 외국인·기관의 반대값으로 추정)")
            c1, c2 = st.columns(2)
            with c1:
                st.markdown("#### 🧠 스마트머니 매집")
                st.caption("외국인+기관 순매수 상위 (개미는 반대편)")
                _render_flow_chips(flows[flows["스마트머니"] > 0], sort_col="스마트머니", ascending=False)
            with c2:
                st.markdown("#### 🐜 개미 우위")
                st.caption("외국인+기관 순매도 상위 (개미가 받아낸 종목)")
                _render_flow_chips(flows[flows["스마트머니"] < 0], sort_col="스마트머니", ascending=True)
            st.markdown("#### 🤝 외국인·기관 동반 순매수")
            st.caption("외국인·기관이 둘 다 순매수한 종목 (가장 강한 수급 신호)")
            _render_flow_chips(flows[(flows["외국인"] > 0) & (flows["기관"] > 0)],
                               sort_col="스마트머니", ascending=False)
        with t_hand:
            st.caption("어제 순매도 → 오늘 순매수로 전환된 종목 (스마트머니 기준 · 흔히 '바닥 신호'로 해석)")
            _render_handover(flows)
    st.caption("데이터: 네이버 금융 · 정보 제공용이며 매수·매도 추천이 아닙니다. 투자 판단과 책임은 본인에게 있습니다.")
