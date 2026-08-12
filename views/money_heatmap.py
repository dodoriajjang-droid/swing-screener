# -*- coding: utf-8 -*-
"""🗺️ 시장 주도주 자금 히트맵

app.py 라우팅에서 분리된 페이지. 함수 라이브러리는 core 에서 가져온다.
"""
from core import *


def render(ctx):
    _nav_changed = ctx['_nav_changed']
    api_key_input = ctx['api_key_input']

    st.subheader("🗺️ 시장 주도주 자금 히트맵")
    st.write("거래대금이 터진 종목들 중 기관 매수세가 동반된 종목을 파악합니다. (녹색: 상승 / 붉은색: 하락)")
    heatmap_limit = st.radio("🔥 히트맵 표시 종목 수 선택 (개)", [30, 50, 100], index=1, horizontal=True)
    
    with st.spinner(f"거래대금 상위 {heatmap_limit}종목 데이터 및 수급 스크래핑 중..."):
        t_kings = get_trading_value_kings(limit=heatmap_limit)
        if not t_kings.empty:
            pension_streaks = []
            progress_bar = st.progress(0)
            status_text = st.empty()
            total_k = len(t_kings)
            for i, (idx, row) in enumerate(t_kings.iterrows()):
                _, streak = get_pension_fund_trend(row['Code'])
                pension_streaks.append(streak)
                progress_bar.progress((i + 1) / total_k)
                status_text.text(f"📊 종목 수급 파싱 중... ({i + 1}/{total_k})")
            status_text.empty()
            progress_bar.empty()
            
            t_kings['연속매수'] = pension_streaks
            t_kings['수급상태'] = t_kings['연속매수'].apply(lambda x: "🔥기관 매집중" if x >= 2 else "일반거래")
            t_kings['display_text'] = "<span style='font-size:16px; font-weight:bold;'>" + t_kings['Name'] + "</span><br>" + t_kings['ChagesRatio'].map("{:+.2f}%".format) + "<br>" + t_kings['수급상태']
            
            fig = px.treemap(t_kings, path=[px.Constant("🔥 주도 섹터 (수급 동반)"), 'Sector', 'Name'], values='Amount_Ouk', color='ChagesRatio', color_continuous_scale=[(0.0, '#f63538'), (0.5, '#414554'), (1.0, '#30cc5a')], color_continuous_midpoint=0, custom_data=['ChagesRatio', 'Amount_Ouk', 'display_text', '연속매수'])
            fig.update_traces(textinfo="text", texttemplate="%{customdata[2]}", hovertemplate="<b>%{label}</b><br>등락률: %{customdata[0]:+.2f}%<br>거래대금: %{customdata[1]:,}억<br>연속매수: %{customdata[3]}일")
            fig.update_layout(margin=dict(t=30, l=10, r=10, b=10), height=600 if heatmap_limit <= 50 else 800)
            st.plotly_chart(fig, use_container_width=True)
            
            st.markdown("### 📊 수급 동반 거래대금 상위 종목 타점 확인")
            sel_king = st.selectbox("타점 확인:", ["선택"] + t_kings[t_kings['연속매수'] >= 1]['Name'].tolist())
            if sel_king != "선택":
                k_code = t_kings[t_kings['Name'] == sel_king]['Code'].iloc[0]
                if res := analyze_technical_pattern(sel_king, k_code): draw_stock_card(res, api_key_str=api_key_input, is_expanded=True)
