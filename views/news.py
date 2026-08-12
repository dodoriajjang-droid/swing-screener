# -*- coding: utf-8 -*-
"""📰 뉴스 — 이슈 분석과 속보를 한 화면에서.

[통합] 예전에는 뉴스 메뉴가 둘이었다.
  · 🗞️ 뉴스 이슈 TOP & 영향 분석  — AI가 오늘의 핵심 이슈를 선별·영향 관계도
  · 📰 실시간 특징주 속보 & 리포트 — 속보 / 증권사 리포트 / AI 데일리 (내부 탭 3개)
둘 다 '뉴스를 본다'는 같은 일이라 메뉴를 합치고, 안쪽 탭을 한 층으로 펼쳤다.
탭 안에 탭이 또 있으면 지금 어디를 보고 있는지 알기 어렵다.
"""
from core import *

import views.news_impact as _impact
import views.news_flash as _flash


def render(ctx):
    st.markdown("## 📰 뉴스")

    t_issue, t_flash, t_report, t_daily = st.tabs(
        ["🗞️ 오늘의 이슈 TOP", "🚨 실시간 특징주·속보", "📋 증권사 리포트 검색", "🔥 AI 데일리 리포트"])

    with t_issue:
        _impact.panel(ctx)
    with t_flash:
        _flash.flash_panel(ctx)
    with t_report:
        _flash.report_panel(ctx)
    with t_daily:
        _flash.daily_panel(ctx)
