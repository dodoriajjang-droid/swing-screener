# -*- coding: utf-8 -*-
"""📋 코스피·코스닥 종목 리스트

app.py 라우팅에서 분리된 페이지. 함수 라이브러리는 core 에서 가져온다.
"""
from core import *


def render(ctx):
    _nav_changed = ctx['_nav_changed']
    api_key_input = ctx['api_key_input']

    st.markdown("## 📋 코스피·코스닥 종목 리스트")
    st.write("국내 전체 상장 종목을 시장별로 검색·정렬해서 볼 수 있습니다.")

    with st.spinner("거래소 종목 데이터를 불러오는 중..."):
        all_stocks = get_stock_list_by_market()

    if all_stocks.empty:
        st.error("❌ 종목 데이터를 불러오지 못했습니다. 잠시 후 다시 시도해 주세요.")
    else:
        # ── 🎛️ 필터 패널 (테두리 카드로 묶어 시각적 구분) ─────────────────
        with st.container(border=True):
            c1, c2, c3 = st.columns([1.5, 1, 1])
            with c1:
                market_pick = st.radio("시장 구분", ["전체", "코스피", "코스닥", "코넥스"], horizontal=True)
            with c2:
                sort_by = st.selectbox("정렬 기준", ["시가총액(억)", "거래대금(억)", "등락률", "현재가", "종목명"])
            with c3:
                sort_desc = st.radio("정렬 순서", ["내림차순", "오름차순"], horizontal=True)

            c4, c5 = st.columns([1.5, 2])
            with c4:
                _sector_opts = sorted(s for s in all_stocks['업종'].dropna().unique()
                                      if s not in ('-', '기타/분류불가'))
                sector_pick = st.selectbox("🏷️ 업종 필터", ["전체 업종"] + _sector_opts)
            with c5:
                keyword = st.text_input("🔍 종목명 또는 종목코드 검색", placeholder="예: 삼성전자 / 005930")

        view = all_stocks.copy()
        if market_pick != "전체":
            view = view[view['시장'] == market_pick]
        if sector_pick != "전체 업종":
            view = view[view['업종'] == sector_pick]
        if keyword.strip():
            kw = keyword.strip()
            view = view[view['종목명'].str.contains(kw, case=False, na=False) | view['종목코드'].str.contains(kw, na=False)]

        ascending = (sort_desc == "오름차순")
        if sort_by == "종목명":
            view = view.sort_values("종목명", ascending=ascending, kind="stable")
        else:
            view = view.sort_values(sort_by, ascending=ascending, kind="stable")

        # ── 📊 요약 메트릭 (검색 결과의 시장 온도를 한눈에) ─────────────────
        _up = int((view['등락률'] > 0).sum())
        _down = int((view['등락률'] < 0).sum())
        _avg = float(view['등락률'].mean()) if len(view) else 0.0
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("검색 결과", f"{len(view):,}개")
        m2.metric("🔺 상승", f"{_up:,}개")
        m3.metric("🔻 하락", f"{_down:,}개")
        m4.metric("평균 등락률", f"{_avg:+.2f}%")

        # ── 📋 종목 테이블 ────────────────────────────────────────────────
        #   숫자 컬럼을 '숫자 그대로' 유지 + Styler로 표시만 포맷 → 헤더 클릭 정렬이
        #   사전순("9,900" > "10,000")으로 꼬이던 문제 해결. 등락률은 상승=빨강/하락=파랑.
        show = view[['시장', '종목코드', '종목명', '현재가', '등락률', '거래대금(억)', '시가총액(억)', '업종']].copy()
        show['차트'] = "https://finance.naver.com/item/main.naver?code=" + show['종목코드'].astype(str)

        def _updown_css(v):
            try:
                v = float(v)
            except (TypeError, ValueError) as _dg_e:
                _diag_note("_updown_css", _dg_e)
                return ""
            if v > 0:
                return "color:#e03131;font-weight:600"
            if v < 0:
                return "color:#1971c2;font-weight:600"
            return "color:#868e96"

        sty = show.style.format({
            '현재가': '{:,.0f}원', '등락률': '{:+.2f}%',
            '거래대금(억)': '{:,.0f}', '시가총액(억)': '{:,.0f}',
        })
        # pandas 2.1+ 는 Styler.map, 구버전은 applymap (양쪽 호환)
        sty = (sty.map if hasattr(sty, "map") else sty.applymap)(_updown_css, subset=['등락률'])

        st.dataframe(
            sty,
            use_container_width=True, hide_index=True, height=620,
            column_config={
                "시장": st.column_config.TextColumn("시장", width="small"),
                "종목코드": st.column_config.TextColumn("코드", width="small"),
                "종목명": st.column_config.TextColumn("종목명", width="medium"),
                "업종": st.column_config.TextColumn("업종", width="medium"),
                "차트": st.column_config.LinkColumn("차트", display_text="📈 보기", width="small",
                                                  help="네이버 증권 종목 페이지 새 창으로 열기"),
            },
        )

        csv = view.to_csv(index=False).encode('utf-8-sig')
        st.download_button("⬇️ 현재 목록 CSV 다운로드", data=csv,
                           file_name=f"종목리스트_{market_pick}.csv", mime="text/csv")
        st.caption("💡 시세·시가총액은 거래소 마감 기준(약 10분 캐시) · 업종은 KRX 차단 시 네이버 업종별 시세로 자동 복구됩니다. 표 헤더를 클릭해도 정렬돼요.")
