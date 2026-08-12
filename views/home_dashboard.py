# -*- coding: utf-8 -*-
"""🎛️ 종합 대시보드 (홈)

app.py 라우팅에서 분리된 페이지. 함수 라이브러리는 core 에서 가져온다.
"""
from core import *


def render(ctx):
    _nav_changed = ctx['_nav_changed']
    api_key_input = ctx['api_key_input']

    if _nav_changed:
        components.html(
            """
            <script>
            (function () {
              function toTop() {
                try {
                  var d = window.parent.document;
                  var sels = ['section.main', '[data-testid="stMain"]',
                              '[data-testid="stAppViewContainer"]', '.main',
                              '.stMainBlockContainer', '.appview-container'];
                  sels.forEach(function (s) {
                    var el = d.querySelector(s);
                    if (el) { try { el.scrollTo(0, 0); } catch (e) {} el.scrollTop = 0; }
                  });
                  try { window.parent.scrollTo(0, 0); } catch (e) {}
                  d.documentElement.scrollTop = 0;
                  d.body.scrollTop = 0;
                } catch (e) {}
              }
              toTop();
              [60, 200, 450, 800].forEach(function (t) { setTimeout(toTop, t); });
            })();
            </script>
            """,
            height=0,
        )

    # [속도개선] 아래 섹션들이 쓰는 수집 함수는 서로 독립적인 네트워크 요청이다.
    #   섹션을 그리면서 하나씩 순차 호출하면 실측 21.3초가 걸렸다.
    #   먼저 병렬로 캐시를 데워두면 10.2초로 줄고, 이후 각 섹션은 캐시 적중이라 즉시 그려진다.
    #   (캐시가 이미 살아 있으면 이 호출 자체가 0초에 가깝다)
    #   관심종목이 있으면 마지막 '관심종목 신호' 섹션이 종목 마스터(15초)를 필요로 하므로
    #   그것까지 같이 데워 화면 끝에서 따로 기다리지 않게 한다.
    with st.spinner("시장 데이터 수집 중... (캐시가 비어 있을 때만 오래 걸립니다)"):
        prefetch_home_data(include_krx=bool(st.session_state.get("watchlist")))

    macro_data = get_macro_indicators()
    fg_data = get_fear_and_greed()

    now_kst = datetime.utcnow() + timedelta(hours=9)
    st.markdown(
        f"""
        <div style="display:flex;align-items:baseline;justify-content:space-between;flex-wrap:wrap;margin-bottom:2px;">
          <span style="font-size:25px;font-weight:900;color:#0f172a;letter-spacing:-1px;">🖥️ 여의도 모닝 데스크</span>
          <span style="font-size:13px;color:#94a3b8;font-weight:600;">{now_kst.strftime('%Y.%m.%d')} ({['월','화','수','목','금','토','일'][now_kst.weekday()]}) {now_kst.strftime('%H:%M')} KST · 5분 자동 갱신</span>
        </div>
        <div style="font-size:13px;color:#64748b;margin-bottom:14px;">내 종목 → 오늘의 국면 → 간밤 글로벌 → 지수·수급 → 자금 흐름 → 섹터 순으로, 지금 확인해야 할 것부터 배치했습니다.</div>
        """,
        unsafe_allow_html=True,
    )

    # ── ① 내 관심종목 신호 (가장 개인적이고 당장 행동해야 하는 정보) ──
    # [재배치] 예전에는 이 블록이 맨 아래였다. 손절선을 이탈한 보유 종목이 있어도
    #   그걸 보려면 아홉 블록을 스크롤해야 했다. 대시보드의 첫 화면은
    #   '시장이 어떤가'보다 '내가 지금 뭘 해야 하나'가 먼저다.
    st.markdown("##### 🚦 내 관심종목 신호 (손절·익절 자동 감시)")
    with st.spinner("관심종목 기술적 점검 중..."):
        render_watchlist_signals()

    st.divider()

    # ── ② 오늘의 시장 국면 (결정 배너) ──
    with st.spinner("시장 국면 분석 중..."):
        render_regime_hero()

    # ── ② 간밤 글로벌 (오늘 국장 방향타) ──
    st.markdown("##### 🌙 간밤 글로벌 — 오늘 국장의 방향타")
    with st.spinner("간밤 미국 지수·금리·유가 수집 중..."):
        render_overnight_tape()
    st.caption("💡 VIX 급등·美 금리 급등·환율 급등 시엔 국장도 위험회피로 기울 수 있어, 좋은 종목이 있어도 보수적으로 접근하는 편이 유리합니다.")

    st.divider()

    # ── [이동] 📰 AI 모닝 브리핑 (간밤 글로벌 바로 아래로 배치) ──
    st.markdown("##### 📰 AI 모닝 브리핑 (Global → Local)")
    if api_key_input:
        with st.spinner("AI가 글로벌 매크로 데이터로 모닝 브리핑을 작성 중입니다..."):
            # 미국 급등주는 이 브리핑에서만 쓰므로 여기서 처음 받아온다(지연 로딩)
            _gainers = ensure_us_gainers()
            top_gainers_names = _gainers['기업명'].tolist()[:5] if not _gainers.empty else []
            briefing_text = get_daily_market_briefing(macro_data, top_gainers_names, api_key_input)
            nb_render_briefing(briefing_text, now_kst.strftime('%Y-%m-%d %H:%M'))
            st.caption("※ 본 브리핑은 24시간 단위로 캐시가 갱신됩니다.")
    else:
        st.warning("좌측 사이드바에 API 키를 입력하시면, AI가 작성하는 글로벌→국내 모닝 브리핑을 볼 수 있습니다.")

    st.divider()

    # ── ③ 코스피·코스닥 실시간 & 투자자별 수급 ──
    st.markdown("##### 📈 코스피·코스닥 실시간 & 수급 (외국인·기관·개인)")
    with st.spinner("지수·투자자별 수급 수집 중..."):
        render_main_index_panel()

    st.divider()

    # ── ④ 오늘의 자금 흐름: 시총 TOP & 업종 등락 ──
    st.markdown("##### 💰 오늘의 자금 흐름 (주도주·섹터)")
    # 헤더+컨트롤 행과 표 행을 분리 → 라디오 높이에 상관없이 두 표의 시작점이 자동 정렬됨(단차 제거)
    h_mc, h_ind = st.columns(2)
    with h_mc:
        st.markdown("**🏆 시가총액 TOP 10**")
        mc_market = st.radio("시장", ["KOSPI", "KOSDAQ"], horizontal=True,
                             label_visibility="collapsed", key="mcap_market_radio")
    with h_ind:
        st.markdown("**🔥 업종별 등락률 (강세 순)**")

    t_mc, t_ind = st.columns(2)
    with t_mc:
        with st.spinner("시가총액 상위 수집 중..."):
            render_marketcap_top(mc_market, 10)
    with t_ind:
        with st.spinner("업종별 등락 수집 중..."):
            render_industry_changes(12)

    st.divider()

    # ── ④-c 지금 뜨는 섹터 TOP5 (국장·미장) ──
    st.markdown("##### 🔥 지금 뜨는 섹터 TOP5")
    _sec_kr_col, _sec_us_col = st.columns(2)
    with _sec_kr_col:
        st.markdown("**🇰🇷 국장 TOP5**")
        with st.spinner("국장 섹터 분석 중..."):
            _sec_kr = get_trending_sectors("KR")
        if _sec_kr:
            render_trending_sectors(_sec_kr, limit=5)
        else:
            st.caption("국장 섹터 데이터를 일시적으로 불러오지 못했어요.")
    with _sec_us_col:
        st.markdown("**🇺🇸 미장 TOP5**")
        with st.spinner("미장 섹터 분석 중..."):
            _sec_us = get_trending_sectors("US")
        if _sec_us:
            render_trending_sectors(_sec_us, limit=5)
        else:
            st.caption("미장 섹터 데이터를 일시적으로 불러오지 못했어요.")
    st.caption("전체 테마는 좌측 **‘🔥 지금 뜨는 섹터’** 메뉴에서 확인하세요.")

    st.divider()

    # ── ④-b 거래량 급증·급감 TOP10 (국장) — 자세히는 경보 탭 ──
    st.markdown("##### 🔥 거래량 급증·급감 TOP10 (국장)")
    render_main_volume_top10()

    st.divider()

    # ── ⑦ 참고 지표 — 매일 볼 필요는 없어 접어 둔다 ──
    #    액션이 필요한 정보(내 종목·국면)를 위로 올린 만큼, 배경 정보는 기본 접기로
    #    스크롤을 줄인다. 펼침 상태는 Streamlit 이 세션 동안 기억한다.
    with st.expander("🧭 투자 심리 (변동성·투자자 심리)", expanded=False):
        render_sentiment_strip(fg_data, macro_data)

    with st.expander("🗓️ 향후 1개월 핵심 일정 (중앙은행·물가·경기·수급)", expanded=False):
        render_week_catalysts()

