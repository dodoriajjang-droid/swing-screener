# -*- coding: utf-8 -*-
"""📊 차트·기술 패널 — 종목 상세의 한 탭.

[통합] 예전에는 '🔬 개별 기업 정밀 진단'이라는 독립 메뉴였고, 자체 종목 검색을
가지고 있었다. 지금은 views/stock_detail.py 가 종목을 한 번 고르고 이 패널을 부른다.
분석·표출 로직은 그대로다.
"""
from core import *


def panel(ctx, name, code, is_us):
    """선택된 종목의 기술적 분석 카드를 그린다."""
    api_key_input = ctx.get('api_key_input', "")

    with st.spinner(f"📡 '{name}' 타점 분석 중..."):
        res = analyze_technical_pattern(name, code)

    if not res:
        st.error("❌ 데이터를 불러오지 못했습니다 — 종목코드를 확인하거나 잠시 후 다시 시도해 주세요.")
        st.caption("반복되면 사이드바 아래 '데이터 수집 진단'에서 원인을 확인할 수 있습니다.")
        return

    render_single_stock_themes(name, api_key_input)
    draw_stock_card(res, api_key_str=api_key_input, is_expanded=True,
                    key_suffix=f"sd_{'us' if is_us else 'kr'}")
