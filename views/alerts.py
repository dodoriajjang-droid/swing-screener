# -*- coding: utf-8 -*-
"""🚨 경보 센터 — 지금 챙겨야 할 신호를 한 곳에.

[통합] '통합 경보 센터'라는 이름의 화면이 이미 뉴스·차트·일정 3트랙을 묶어 놓고도,
그 옆에 경보 성격의 메뉴가 둘 더 있었다. 통합해 놓고 통합이 안 된 상태였다.
  · 🚦 거래량 급증 & 시장 경보 — 거래량 이상 + 관리종목
  · 🔺 당일 상/하한가 분석      — 상·하한가
둘 다 '오늘 이상 신호'라 경보 센터의 탭으로 흡수했다. 내용은 그대로다.
"""
from core import *

import views.alert_center_page as _center
import views.volume_alerts as _volume
import views.limit_moves as _limit


def render(ctx):
    st.markdown("## 🚨 경보 센터")
    st.caption("뉴스·차트·일정 경보와 함께, 오늘 시장에서 튄 신호(거래량·상하한가·관리종목)를 모았습니다.")

    t_center, t_volume, t_limit, t_warn = st.tabs(
        ["🔔 뉴스·차트·일정 경보", "🚦 거래량 급증·급감", "🔺 당일 상/하한가", "🛡️ 관리종목·시장경보"])

    with t_center:
        _center.panel(ctx)
    with t_volume:
        _volume.volume_panel(ctx)
    with t_limit:
        _limit.panel(ctx)
    with t_warn:
        _volume.warning_panel(ctx)
