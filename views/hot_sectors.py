# -*- coding: utf-8 -*-
"""🔥 지금 뜨는 섹터 (국장·미장)

app.py 라우팅에서 분리된 페이지. 함수 라이브러리는 core 에서 가져온다.
"""
from core import *


def panel(ctx):
    _nav_changed = ctx.get('_nav_changed', False)
    api_key_input = ctx.get('api_key_input', "")

    st.caption("대표 종목 평균 등락률 순 · 🔴빨강=상승 / 🔵파랑=하락")

    def _render_sector_market(market, spinner_msg):
        with st.spinner(spinner_msg):
            sectors = get_trending_sectors(market)
        if not sectors:
            who = "국장" if market == "KR" else "미장"
            st.error(f"❌ {who} 섹터 데이터를 불러올 수 없습니다. 잠시 후 다시 시도해주세요.")
            return
        hot = sum(1 for s in sectors if s["avg"] > 0)
        cc1, cc2, cc3 = st.columns(3)
        cc1.metric("강세 테마", f"{hot} / {len(sectors)}")
        cc2.metric("🔥 최강 테마", sectors[0]["theme"], f"{sectors[0]['avg']:+.2f}%")
        cc3.metric("🧊 최약 테마", sectors[-1]["theme"], f"{sectors[-1]['avg']:+.2f}%")
        st.markdown("#### 테마별 평균 등락 (강세 순)")
        render_trending_sectors(sectors)

    tab_kr, tab_us = st.tabs(["🇰🇷 국장 (KOSPI·KOSDAQ)", "🇺🇸 미장 (US)"])
    with tab_kr:
        _render_sector_market("KR", "국장 테마별 등락 수집 중...")
    with tab_us:
        _render_sector_market("US", "미장 테마별 등락 수집 중... (첫 조회는 수십 초, 이후 30분 캐시)")
    st.caption("대표 종목 평균 등락률 기준이며, 테마 구성은 참고용입니다. 투자 권유가 아닙니다.")
