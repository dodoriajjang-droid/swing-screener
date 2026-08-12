# -*- coding: utf-8 -*-
"""💸 자금 흐름 — "지금 돈이 어디로 가나" 하나의 질문, 세 개의 시간축.

[통합] 예전에는 메뉴가 셋이었다.
  · 🗺️ 시장 주도주 자금 히트맵   — 오늘 거래대금이 터진 곳
  · 🔥 지금 뜨는 섹터            — 최근 며칠 강세 섹터
  · 🕸️ 실시간 섹터 순환매 추적    — 1~6개월 자금 이동
세 화면 모두 같은 질문에 답하고 기간만 다르다. 그래서 기간을 탭으로 두고
메뉴는 하나로 합쳤다. 각 탭의 계산과 표는 그대로다.
"""
from core import *

import views.money_heatmap as _heatmap
import views.hot_sectors as _hot
import views.sector_rotation as _rotation


def render(ctx):
    st.markdown("## 💸 자금 흐름")
    st.caption("오늘 → 최근 → 중기 순으로, 자금이 어디로 몰리고 어디서 빠지는지 봅니다.")

    t_today, t_short, t_mid = st.tabs(
        ["🗺️ 오늘 (주도주 히트맵)", "🔥 최근 (뜨는 섹터)", "🕸️ 중기 (섹터 순환매)"])

    with t_today:
        _heatmap.panel(ctx)
    with t_short:
        _hot.panel(ctx)
    with t_mid:
        _rotation.panel(ctx)
