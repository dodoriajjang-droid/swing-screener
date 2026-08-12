# -*- coding: utf-8 -*-
"""🕸️ 실시간 섹터 순환매 추적

app.py 라우팅에서 분리된 페이지. 함수 라이브러리는 core 에서 가져온다.
"""
from core import *


def panel(ctx):
    _nav_changed = ctx.get('_nav_changed', False)
    api_key_input = ctx.get('api_key_input', "")

    st.write("국내 대표 섹터 ETF의 기간별 수익률을 실측해, **강세 섹터(자금 유입 추정)**와 **약세 섹터(자금 이탈 추정)**를 한눈에 보여줍니다.")

    period_sk = st.radio("분석 기간", ["1개월", "3개월", "6개월"], horizontal=True)
    period_col = "1M수익률" if period_sk == "1개월" else "3M수익률" if period_sk == "3개월" else "6M수익률"

    with st.spinner(f"최근 {period_sk} 시장 섹터 수익률 실시간 연산 중..."):
        trend_df = analyze_theme_trends()

    if not trend_df.empty:
        df_sorted = trend_df.sort_values(period_col, ascending=False).reset_index(drop=True)
        winners = df_sorted.head(3)
        losers = df_sorted.tail(3).iloc[::-1]  # 최약세부터

        # ── 요약 카드: 강세 3 / 약세 3 ─────────────────────────
        c_win, c_lose = st.columns(2)
        def _chip(name, val):
            color = "#ef4444" if val > 0 else ("#3b82f6" if val < 0 else "#64748b")
            arrow = "▲" if val > 0 else ("▼" if val < 0 else "")
            return (f'<div style="display:flex;justify-content:space-between;padding:8px 12px;margin:5px 0;'
                    f'background:#fff;border:1px solid #eef2f6;border-radius:10px;">'
                    f'<span style="font-weight:700;color:#1e293b;">{name}</span>'
                    f'<span style="font-weight:800;color:{color};">{arrow}{abs(val):.2f}%</span></div>')
        with c_win:
            st.markdown("#### 🔥 강세 섹터 (자금 유입 추정)")
            st.markdown("".join(_chip(r['테마'], r[period_col]) for _, r in winners.iterrows()),
                        unsafe_allow_html=True)
        with c_lose:
            st.markdown("#### 🧊 약세 섹터 (자금 이탈 추정)")
            st.markdown("".join(_chip(r['테마'], r[period_col]) for _, r in losers.iterrows()),
                        unsafe_allow_html=True)

        st.markdown("---")

        # ── 전체 섹터 수익률 가로 바 차트 (강세 빨강 / 약세 파랑) ──
        chart_df = df_sorted.sort_values(period_col, ascending=True)  # 아래→위 오름차순
        bar_colors = ["#ef4444" if v > 0 else "#3b82f6" for v in chart_df[period_col]]
        fig_bar = go.Figure(go.Bar(
            x=chart_df[period_col],
            y=chart_df['테마'],
            orientation='h',
            marker=dict(color=bar_colors),
            text=[f"{v:+.2f}%" for v in chart_df[period_col]],
            textposition='outside',
            cliponaxis=False,
        ))
        fig_bar.update_layout(
            title_text=f"최근 {period_sk} 섹터별 수익률 ({datetime.now().strftime('%Y.%m.%d')} 기준)",
            height=480,
            margin=dict(l=10, r=60, t=50, b=20),
            xaxis_title="수익률 (%)",
            plot_bgcolor="rgba(0,0,0,0)",
        )
        fig_bar.add_vline(x=0, line_width=1, line_color="#94a3b8")
        st.plotly_chart(fig_bar, use_container_width=True)

        st.info(
            f"💡 최근 {period_sk} 동안 **{', '.join(winners['테마'].tolist())}**가 가장 강했고, "
            f"**{', '.join(losers['테마'].tolist())}**가 가장 부진했습니다. "
            "통상 약세 섹터에서 차익이 실현되며 강세 섹터로 수급이 옮겨가는 '순환매'로 해석하지만, "
            "이는 수익률 차이에 근거한 **추정**이며 실제 자금 이동을 직접 측정한 값은 아닙니다."
        )
    else:
        st.error("테마별 시장 데이터를 불러오지 못했습니다.")
