# -*- coding: utf-8 -*-
"""🚨 통합 경보 센터 (뉴스·차트·일정)

app.py 라우팅에서 분리된 페이지. 함수 라이브러리는 core 에서 가져온다.
"""
from core import *


# ==========================================
# [v7.1] 🚨 통합 경보 센터 (뉴스·차트·일정)
#   - jaemini_alert_center.py 의 함수에 기존 앱 함수들을 '주입'해서 렌더
# ==========================================

def panel(ctx):
    _nav_changed = ctx.get('_nav_changed', False)
    api_key_input = ctx.get('api_key_input', "")

    alert_center.render_alert_center({
        "analyze_technical_pattern": analyze_technical_pattern,
        "get_latest_naver_news": get_latest_naver_news,
        "get_economic_events": get_economic_events,
        "get_kr_index_panel": get_kr_index_panel,
        "fetch_polymarket_markets": fetch_polymarket_markets,
        "get_krx_stocks": get_krx_stocks,
        "ask_gemini": ask_gemini,
        "api_key": api_key_input,
    })
