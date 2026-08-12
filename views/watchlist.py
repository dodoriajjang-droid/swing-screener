# -*- coding: utf-8 -*-
"""⭐ 내 관심종목 모니터링

app.py 라우팅에서 분리된 페이지. 함수 라이브러리는 core 에서 가져온다.
"""
from core import *


def render(ctx):
    _nav_changed = ctx['_nav_changed']
    api_key_input = ctx['api_key_input']

    st.subheader("⭐ 내 관심종목 모니터링")
    app_state.render_backup_ui("watchlist", "관심종목")   # [v7.2] 내보내기/불러오기
    if not st.session_state.watchlist:
        st.info("추가된 종목이 없습니다. 스캐너나 분석기에서 관심종목을 추가해보세요.")
    else:
        col1, col2 = st.columns([8, 2])
        if col2.button("🗑️ 관심종목 모두 지우기", use_container_width=True): 
            st.session_state.watchlist = []; save_watchlist([]); st.rerun()
            
        for i, item in enumerate(st.session_state.watchlist):
            with st.spinner(f"'{item['종목명']}' 데이터 로딩 중..."):
                try:
                    res = analyze_technical_pattern(item['종목명'], item['티커'])
                    if res: draw_stock_card(res, api_key_str=api_key_input, is_expanded=False, key_suffix=f"wl_{i}")
                    else: st.error(f"❌ '{item['종목명']}' ({item['티커']}) 데이터를 불러오지 못했습니다.")
                except Exception as e: st.error(f"❌ '{item['종목명']}' 데이터 분석 중 치명적 오류 발생: {str(e)}")
