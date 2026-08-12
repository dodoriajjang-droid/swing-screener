# -*- coding: utf-8 -*-
"""
📈 Jaemini PRO — 진입점 (사이드바 + 페이지 라우팅)

함수 라이브러리는 core.py 에 있다. `from core import *` 로 전부 승계하므로
아래 라우팅 코드는 분리 전과 동일한 이름들을 그대로 쓴다.
"""
from core import *      # 데이터·분석·점수·렌더 함수 + 전역 설정 (import 시 페이지 설정 실행)
import core             # 모듈 자체 참조가 필요할 때

# ==========================================
# 4. 사이드바 메뉴 
# ==========================================
with st.sidebar:
    st.title("📈 Jaemini PRO v7.0")
    st.markdown("풀옵션 단기 스윙 & 퀀트 추적 시스템")
    st.caption("🆕 v7.0: 주봉 멀티타임프레임 · 시장 국면 신호등 · 공매도/빚투 리스크")

    # 실시간 현재 날짜·시간 (KST) — 브라우저에서 초 단위로 갱신, 모든 페이지에서 표시
    components.html(
        """
        <div id="kst-clock" style="
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
            background: linear-gradient(135deg, #1e293b, #334155);
            color: #e2e8f0; border: 1px solid #475569; border-radius: 10px;
            padding: 10px 12px; text-align: center; margin: 2px 0 8px 0;">
            <div style="font-size: 12px; color:#94a3b8; letter-spacing:0.5px;">🇰🇷 한국 시간 (KST)</div>
            <div id="kst-date" style="font-size: 15px; font-weight:600; margin-top:3px;">--</div>
            <div id="kst-time" style="font-size: 22px; font-weight:700; font-variant-numeric: tabular-nums; color:#f8fafc;">--:--:--</div>
        </div>
        <script>
        function updateKST() {
            const now = new Date();
            // 사용자 로컬과 무관하게 KST(UTC+9) 고정 계산
            const kst = new Date(now.getTime() + (now.getTimezoneOffset() * 60000) + (9 * 3600000));
            const days = ['일','월','화','수','목','금','토'];
            const y = kst.getFullYear();
            const mo = String(kst.getMonth()+1).padStart(2,'0');
            const d = String(kst.getDate()).padStart(2,'0');
            const dow = days[kst.getDay()];
            const h = String(kst.getHours()).padStart(2,'0');
            const mi = String(kst.getMinutes()).padStart(2,'0');
            const s = String(kst.getSeconds()).padStart(2,'0');
            const de = document.getElementById('kst-date');
            const te = document.getElementById('kst-time');
            if (de) de.textContent = `${y}.${mo}.${d} (${dow})`;
            if (te) te.textContent = `${h}:${mi}:${s}`;
        }
        updateKST();
        setInterval(updateKST, 1000);
        </script>
        """,
        height=92,
    )

    menu_options = [
        "📂 [ 홈 & 자산 관리 ]",
        " ┣ 🎛️ 홈: 종합 대시보드",
        " ┣ 💼 내 계좌 & 포트폴리오 진단",
        " ┗ ⭐ 내 관심종목 모니터링",
        " ", 
        "📂 [ 퀀트 스캐너 & 종목 발굴 ]",
        " ┣ 🔬 개별 기업 정밀 진단 (AI 비전)",
        " ┣ 🧭 AI 통합 투자 발굴기 (테스트)",
        " ┣ 🚀 단기 스윙 퀀트 스캐너",
        " ┣ 💎 장기 우량주 & 가치주 발굴",
        " ┣ 📉 낙폭과대 스캐너 (고점대비 -30%↓)",
        " ┣ 🏛️ 국민연금 5% 대량보유 픽",
        " ┣ ⚡ 메가트렌드 & 테마 대장주",
        " ┣ 🇰🇷 국민성장펀드 12대 산업 수혜주",
        " ┗ 📋 코스피·코스닥 종목 리스트",
        "  ", 
        "📂 [ 시장 흐름 & 매크로 ]",
        " ┣ 🌍 글로벌 매크로 & AI 분석 (v6.0)",
        " ┣ 🗺️ 시장 주도주 자금 히트맵",
        " ┣ 🕸️ 실시간 섹터 순환매 추적",
        " ┣ 🔥 지금 뜨는 섹터 (국장·미장)",
        " ┣ 💰 국장 수급 분석 (외국인·기관·개인)",
        " ┣ 📅 핵심 증시 일정 & IPO 달력",
        " ┗ 🔮 폴리마켓 예측시장 (금리·경제·정치)",
        "   ", 
        "📂 [ 트레이딩 & 시장 경보 ]",
        " ┣ 🗞️ 뉴스 이슈 TOP & 영향 분석",
        " ┣ 🚨 통합 경보 센터 (뉴스·차트·일정)",
        " ┣ 🔥 간밤의 미국 급등주 & 수혜주",
        " ┣ 🚨 당일 상/하한가 분석",
        " ┣ 🚦 거래량 급증 & 시장 경보",
        " ┗ 📰 실시간 특징주 속보 & 리포트",
        "    ", 
        "📂 [ 심층 분석 & 도구 ]",
        " ┣ 👴 노후 준비 ETF 시뮬레이터 (v2.0)",
        " ┣ 📊 국내외 핵심 ETF 분석",
        " ┣ 💰 고배당주 파이프라인 (TOP 300)",
        " ┣ 🎯 증권사 목표가 컨센서스",
        " ┣ ⚖️ 적정 주가 계산기 (버핏 모델)",
        " ┗ 👁️ 차트 이미지 AI 비전 분석",
    ]

    if "main_menu_radio" not in st.session_state:
        st.session_state.main_menu_radio = " ┣ 🎛️ 홈: 종합 대시보드"

    selected_display_menu = st.radio("📌 메뉴 이동", menu_options, key="main_menu_radio", label_visibility="collapsed")

    if selected_display_menu.startswith(" ┣ ") or selected_display_menu.startswith(" ┗ "):
        pure_menu_name = selected_display_menu[3:] 
    elif selected_display_menu.strip() == "":
        st.sidebar.warning("☝️ 구분선입니다. 위아래의 실제 메뉴를 선택해주세요.")
        pure_menu_name = "None"
    else:
        st.sidebar.info("☝️ [카테고리]를 누르셨습니다. 아래 하위 메뉴(┣, ┗)를 클릭해주세요.")
        pure_menu_name = "None"
        
    selected_menu = pure_menu_name
    clean_menu = pure_menu_name

    # [추가] 메뉴(페이지) 전환 감지 — 메뉴를 '새로 눌렀을 때'만 1회 동작시키기 위함.
    #  (자동 새로고침/챗봇 입력 등 일반적인 rerun 때는 False 가 되어 화면이 튀지 않음)
    _nav_changed = st.session_state.get("_prev_menu_nav") != selected_menu
    st.session_state["_prev_menu_nav"] = selected_menu

    st.divider()
    
    st.header("🧠 AI 엔진 연결 상태")
    api_key_input = ""
    if "GEMINI_API_KEY" in st.secrets:
        val = st.secrets["GEMINI_API_KEY"]
        api_key_input = str(val) if isinstance(val, str) else str(list(val.values())[0])
        st.success("✅ 시스템 연동 완료")
    else:
        api_key_input = st.text_input("Gemini API Key를 입력하세요", type="password")
        if api_key_input: 
            api_key_input = str(api_key_input)
            st.success("✅ 시스템 연동 완료")
            
    # [v7.2] API 키를 세션에 게시 — 전역 변수(api_key_input)에 직접 의존하던
    #        퀀트 비서/팝업이 모듈로 분리돼도 동작하도록 결합을 끊는다.
    st.session_state["_api_key"] = api_key_input

    if st.button("🔄 현재 화면 새로고침", use_container_width=True):
        st.cache_data.clear()
        st.rerun()

    # [v7.2] 데이터 수집 상태 — 조용히 실패한 수집이 있으면 여기서 먼저 눈에 띈다
    st.divider()
    diag.render_badge()


render_global_quant_button()

if selected_menu in LIVE_REFRESH_PAGES:
    st_autorefresh(interval=AUTOREFRESH_MS, limit=None, key="news_autorefresh")

if selected_menu == "🎛️ 홈: 종합 대시보드":
    # [추가] 메뉴를 '새로 눌러서' 이 화면으로 들어왔을 때만 화면을 맨 위로 올림.
    #  → 페이지 하단의 '실시간 퀀트 챗봇(채팅 입력창)'으로 화면이 튀어 내려가는 현상 방지.
    #  자동 새로고침/챗봇 입력 같은 일반 rerun 때는 동작하지 않으므로 챗봇은 정상 사용 가능.
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

    macro_data = get_macro_indicators()
    fg_data = get_fear_and_greed()

    now_kst = datetime.utcnow() + timedelta(hours=9)
    st.markdown(
        f"""
        <div style="display:flex;align-items:baseline;justify-content:space-between;flex-wrap:wrap;margin-bottom:2px;">
          <span style="font-size:25px;font-weight:900;color:#0f172a;letter-spacing:-1px;">🖥️ 여의도 모닝 데스크</span>
          <span style="font-size:13px;color:#94a3b8;font-weight:600;">{now_kst.strftime('%Y.%m.%d')} ({['월','화','수','목','금','토','일'][now_kst.weekday()]}) {now_kst.strftime('%H:%M')} KST · 5분 자동 갱신</span>
        </div>
        <div style="font-size:13px;color:#64748b;margin-bottom:14px;">간밤 글로벌 → 오늘의 국면 → 지수·수급 → 자금 흐름 → 심리 → 일정 → 내 종목 순으로, 매매에 필요한 핵심만 모았습니다.</div>
        """,
        unsafe_allow_html=True,
    )

    # ── ① 오늘의 시장 국면 (결정 배너) ──
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
            top_gainers_names = st.session_state.gainers_df['기업명'].tolist()[:5] if not st.session_state.gainers_df.empty else []
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
    st.caption("전체 테마는 좌측 **‘🔥 지금 뜨는 섹터 (국장·미장)’** 메뉴에서 확인하세요.")

    st.divider()

    # ── ④-b 거래량 급증·급감 TOP10 (국장) — 자세히는 경보 탭 ──
    st.markdown("##### 🔥 거래량 급증·급감 TOP10 (국장)")
    render_main_volume_top10()

    st.divider()

    # ── ⑤ 투자 심리 (VIX + 공포·탐욕) ──
    st.markdown("##### 🧭 투자 심리 (변동성·투자자 심리)")
    render_sentiment_strip(fg_data, macro_data)

    st.divider()

    # ── ⑥ 향후 1개월 핵심 매크로 일정 ──
    st.markdown("##### 🗓️ 향후 1개월 핵심 일정 (중앙은행·물가·경기·수급)")
    render_week_catalysts()

    st.divider()

    # ── ⑦ 내 관심종목 신호 (액션) ──
    st.markdown("##### 🚦 내 관심종목 신호 (손절·익절 자동 감시)")
    with st.spinner("관심종목 기술적 점검 중..."):
        render_watchlist_signals()



elif selected_menu == "💼 내 계좌 & 포트폴리오 진단":
    st.markdown("## 💼 내 계좌 & 포트폴리오 진단")
    st.write("현재 보유 중인 종목들을 표에 입력하면, 단순 개별 분석이 아닌 **계좌 전체의 자산 배분(비중)과 리스크를 고려한 종합 리밸런싱 전략**을 AI가 진단해 드립니다.")

    if "portfolio_df" not in st.session_state:
        st.session_state.portfolio_df = pd.DataFrame([{"종목명": "", "진입단가": 0, "보유수량": 0}])
    if "pf_editor_ver" not in st.session_state:
        st.session_state.pf_editor_ver = 0

    st.markdown("### 📊 1. 내 포트폴리오 입력")

    up_col, sample_col = st.columns([3, 2])
    with up_col:
        up_file = st.file_uploader(
            "📤 파일을 여기로 끌어다 놓으면 표가 한 번에 채워집니다 (엑셀/CSV)",
            type=["csv", "xlsx", "xlsm", "xls"],
            key="pf_upload",
            help="증권사(키움·미래에셋·삼성 등) 잔고 화면에서 내려받은 엑셀도 그대로 올리면 종목명·수량·매입단가 컬럼을 자동으로 찾아 읽습니다.",
        )
    with sample_col:
        st.caption("처음이라면 👇 샘플 양식을 받아 숫자만 바꿔 올리세요.")
        _sample_df = pd.DataFrame({
            "종목명": ["삼성전자", "SK하이닉스", "AAPL"],
            "진입단가": [71000, 180000, 210],
            "보유수량": [10, 5, 3],
        })
        st.download_button("📑 샘플 양식 받기 (CSV)", _sample_df.to_csv(index=False).encode("utf-8-sig"),
                           file_name="포트폴리오_샘플.csv", mime="text/csv", use_container_width=True)
        try:
            import io as _io
            _xbuf = _io.BytesIO()
            _sample_df.to_excel(_xbuf, index=False)
            st.download_button("📑 샘플 양식 받기 (엑셀)", _xbuf.getvalue(), file_name="포트폴리오_샘플.xlsx",
                               mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                               use_container_width=True)
        except Exception as _dg_e:
            _diag_note("<module>", _dg_e)
            pass  # openpyxl 미설치 환경에서는 CSV 샘플만 제공

    if up_file is not None:
        _file_key = (up_file.name, up_file.size)
        if st.session_state.get("pf_loaded_key") != _file_key:
            try:
                _pf_new, _pf_msg = parse_portfolio_upload(up_file)
                st.session_state.portfolio_df = _pf_new
                st.session_state.pf_loaded_key = _file_key
                st.session_state.pf_upload_msg = _pf_msg
                st.session_state.pf_editor_ver += 1
                st.rerun()
            except ValueError as _e:
                st.error(f"⚠️ {_e}")
            except Exception as _e:
                st.error(f"⚠️ 파일을 해석하지 못했습니다: {_e}")
    if st.session_state.get("pf_upload_msg"):
        st.success(st.session_state.pf_upload_msg)

    # 🔎 [NEW] 종목 검색해서 담기 (장바구니 방식) — 체크한 종목이 아래 표에 행으로 자동 추가됩니다.
    with st.container(border=True):
        st.markdown("**🔎 종목 검색해서 담기** — 검색 후 체크만 하면 아래 표에 자동으로 담깁니다. (담은 뒤 표에서 **단가·수량**만 입력하세요)")
        if "pf_search_query" not in st.session_state:
            st.session_state.pf_search_query = ""

        _s_cols = st.columns([4, 1], vertical_alignment="bottom")
        with _s_cols[0]:
            pf_search_input = st.text_input(
                "종목 검색", placeholder=" 🔍 검색어를 입력하세요. (예: 우주항공, 삼성전자, AAPL)",
                label_visibility="collapsed", key="pf_search_in").strip()
        with _s_cols[1]:
            pf_search_clicked = st.button("종목 검색", type="primary", use_container_width=True, key="pf_search_btn")

        if pf_search_clicked:
            if pf_search_input:
                st.session_state.pf_search_query = pf_search_input
            else:
                st.warning("⚠️ 검색어를 먼저 입력해주세요!")

        if st.session_state.pf_search_query:
            _q = st.session_state.pf_search_query
            pf_options = []
            with st.spinner("데이터베이스에서 종목을 찾는 중입니다..."):
                _krx_s = get_krx_stocks()   # 국내 주식 + ETF 포함
                if not _krx_s.empty:
                    _m = _krx_s[_krx_s['Name'].str.contains(_q, case=False, na=False)]
                    for _, _r in _m.head(60).iterrows():
                        pf_options.append(f"{_r['Name']} [{_r['Code']}]")
                if re.search('[a-zA-Z]', _q):   # 영문 포함 시 미국 주식/ETF 검색
                    try:
                        for _res_us in search_us_ticker(_q):
                            _sym = _res_us.split(" ")[0]
                            _ko = _res_us.split(" (")[1].split(" /")[0]
                            pf_options.append(f"{_ko} [{_sym}]")
                    except Exception as _dg_e:
                        _diag_note("<module>", _dg_e)
                        pass

            if pf_options:
                with st.form(key="pf_add_form", clear_on_submit=True):
                    st.success(f"🎉 '{_q}' 검색 결과 총 **{len(pf_options)}개**를 찾았습니다!")
                    pf_selected = st.multiselect("👇 결과 목록에서 포트폴리오에 담을 종목을 모두 골라주세요:", options=pf_options)
                    pf_submit = st.form_submit_button("🛒 선택한 종목 포트폴리오 표에 추가하기", use_container_width=True)

                    if pf_submit:
                        if pf_selected:
                            _cur = st.session_state.portfolio_df.copy()
                            _existing = set(_cur["종목명"].astype(str).str.strip().str.upper())
                            _new_rows = []
                            for _sel in pf_selected:
                                _nm = str(_sel).strip()   # "이름 [코드]" 형식 그대로 저장 → 진단 시 코드 우선 인식(모호 매칭 방지)
                                if _nm.upper() in _existing:
                                    continue
                                _new_rows.append({"종목명": _nm, "진입단가": 0, "보유수량": 0})
                                _existing.add(_nm.upper())
                            if _new_rows:
                                # 비어 있는 placeholder 행은 제거 후 합치기
                                _mask_empty = (_cur["종목명"].astype(str).str.strip() == "") \
                                              & (pd.to_numeric(_cur["진입단가"], errors="coerce").fillna(0) == 0) \
                                              & (pd.to_numeric(_cur["보유수량"], errors="coerce").fillna(0) == 0)
                                _cur = _cur[~_mask_empty]
                                st.session_state.portfolio_df = pd.concat(
                                    [_cur, pd.DataFrame(_new_rows)], ignore_index=True)
                                st.session_state.pf_editor_ver += 1   # data_editor 강제 새로고침
                                st.toast(f"✅ {len(_new_rows)}개 종목을 표에 담았습니다! 단가·수량을 입력해주세요.", icon="🛒")
                            st.session_state.pf_search_query = ""
                            st.rerun()
                        else:
                            st.warning("⚠️ 추가할 종목을 위에서 먼저 선택해주세요.")
            else:
                st.error("앗! 검색 결과가 없습니다. 🥲 다른 키워드로 다시 검색해보세요.")

    st.caption("표는 직접 고칠 수 있고, 엑셀에서 복사한 표를 셀에 붙여넣기(Ctrl+V)해도 됩니다. 행 추가는 표 맨 아래 ➕ 버튼.")
    edited_df = st.data_editor(
        st.session_state.portfolio_df,
        num_rows="dynamic",
        column_config={
            "종목명": st.column_config.TextColumn("종목명 또는 티커", required=True),
            "진입단가": st.column_config.NumberColumn("내 진입단가", min_value=0, step=1, format="%d"),
            "보유수량": st.column_config.NumberColumn("보유 수량", min_value=0, step=1, format="%d"),
        },
        use_container_width=True,
        key=f"pf_editor_{st.session_state.pf_editor_ver}",
    )
    st.session_state.portfolio_df = edited_df

    _save_col, _clear_col = st.columns([3, 1])
    with _save_col:
        _valid_save = edited_df[
            (edited_df["종목명"].astype(str).str.strip() != "")
            & (pd.to_numeric(edited_df["진입단가"], errors="coerce").fillna(0) > 0)
            & (pd.to_numeric(edited_df["보유수량"], errors="coerce").fillna(0) > 0)
        ]
        st.download_button(
            "💾 내 포트폴리오 저장 (CSV) — 다음에 이 파일만 다시 올리면 그대로 복원돼요",
            _valid_save.to_csv(index=False).encode("utf-8-sig"),
            file_name="내_포트폴리오.csv", mime="text/csv",
            use_container_width=True, disabled=_valid_save.empty,
        )
    with _clear_col:
        if st.button("🗑️ 표 비우기", use_container_width=True):
            st.session_state.portfolio_df = pd.DataFrame([{"종목명": "", "진입단가": 0, "보유수량": 0}])
            st.session_state.pf_editor_ver += 1
            st.session_state.pf_loaded_key = None
            st.session_state.pf_upload_msg = ""
            st.session_state.pop("pf_upload", None)
            st.rerun()

    valid_rows = edited_df[(edited_df["종목명"].astype(str).str.strip() != "") & (edited_df["진입단가"] > 0) & (edited_df["보유수량"] > 0)]

    st.markdown("### 💧 2. 개별 종목 물타기 시뮬레이터 (선택 사항)")
    def _prc_avgcalc():
        col_m1, col_m2, col_m3, col_m4 = st.columns(4)
        with col_m1:
            sim_opts = ["직접 입력"] + valid_rows["종목명"].tolist() if not valid_rows.empty else ["직접 입력"]
            sim_sel = st.selectbox("물타기 할 종목", sim_opts)
        with col_m2:
            sim_name = st.text_input("종목명", value="" if sim_sel == "직접 입력" else sim_sel, label_visibility="collapsed" if sim_sel != "직접 입력" else "visible")
        with col_m3:
            sim_add_price = st.number_input("추가 매수 단가", min_value=0, step=1, format="%d", key="sim_p")
        with col_m4:
            sim_add_qty = st.number_input("추가 매수 수량", min_value=0, step=1, format="%d", key="sim_q")
        
        if st.button("🧮 평단가 계산하기"):
            if sim_name and sim_add_price > 0 and sim_add_qty > 0:
                orig_row = valid_rows[valid_rows["종목명"] == sim_name]
                if not orig_row.empty:
                    orig_price = int(orig_row.iloc[0]["진입단가"])
                    orig_qty = int(orig_row.iloc[0]["보유수량"])
                    orig_invest = orig_price * orig_qty
                    add_invest = sim_add_price * sim_add_qty
                    new_qty = orig_qty + sim_add_qty
                    new_avg = int((orig_invest + add_invest) / new_qty)
                    st.info(f"💡 **[{sim_name} 시뮬레이션]** 기존 {orig_qty}주(평단 {orig_price:,}) + 추가 {sim_add_qty}주(단가 {sim_add_price:,}) ➡️ **총 {new_qty}주, 조정 평단가: {new_avg:,}**")
                else:
                    st.warning("위 포트폴리오 표에 등록된 종목을 선택해야 기존 데이터와 합산하여 정확한 계산이 가능합니다.")
    _register_popup("avgcalc", _prc_avgcalc)
    _popup_button("🧮 평단가(물타기) 계산기 열기", "avgcalc", "🧮 평단가(물타기) 계산기", key="btn_avgcalc")

    if st.button("📊 계좌 전체 종합 진단 및 AI 리밸런싱", type="primary", use_container_width=True):
        if valid_rows.empty:
            st.warning("종목명과 진입단가, 보유수량을 최소 1개 이상 표에 정확히 입력해주세요.")
        elif not api_key_input:
            st.error("좌측 사이드바에 API 키를 입력해주세요.")
        else:
            with st.spinner("전체 포트폴리오 구성 종목의 현재가 조회 및 자산 배분 비중을 분석 중입니다..."):
                portfolio_summary = []
                total_invested_all = 0
                total_current_all = 0
                ex_rate = st.session_state.get('ex_rate', 1350.0)
                
                for idx, row in valid_rows.iterrows():
                    pos_name = str(row["종목명"]).strip()
                    entry_price = int(row["진입단가"])
                    quantity = int(row["보유수량"])
                    
                    search_ticker = None
                    pos_name_kr = pos_name
                    is_us = False
                    
                    # 🛒 [NEW] '이름 [코드]' 형식(검색해서 담기)이면 코드를 우선 인식 → 이름 모호 매칭(예: KO→KODEX) 방지
                    _br = re.search(r'\[([A-Za-z0-9.\-]{1,12})\]\s*$', pos_name)
                    if _br:
                        _code = _br.group(1).strip()
                        pos_name_kr = pos_name[:_br.start()].strip() or _code
                        search_ticker = _code
                        is_us = not _code.isdigit()   # 6자리 숫자면 국내, 아니면 미국 티커
                    
                    # 💡 [핵심 로직 수정] 영어 포함 여부가 아니라, '한국 주식 DB(KRX)'에 있는지 먼저 확인!
                    krx_df = get_krx_stocks()
                    if search_ticker:
                        pass   # 위에서 코드로 확정됨 → 이름 검색 생략
                    # 1. 한국 종목 중에 정확히 일치하는 이름이 있는지 먼저 확인 (대소문자 무시)
                    elif not (exact_match := krx_df[krx_df['Name'].str.upper() == pos_name.upper()]).empty:
                        is_us = False
                        search_ticker = exact_match['Code'].iloc[0]
                        pos_name_kr = exact_match['Name'].iloc[0]
                    else:
                        # 2. 정확히 일치하는 게 없으면, 입력한 단어를 포함하는 한국 종목이 있는지 2차 확인
                        contains_match = krx_df[krx_df['Name'].str.contains(pos_name, case=False, na=False)]
                        if not contains_match.empty:
                            is_us = False
                            search_ticker = contains_match['Code'].iloc[0]
                            pos_name_kr = contains_match['Name'].iloc[0]
                        else:
                            # 3. 한국 주식 DB에 아예 없으면 그제서야 미국 주식으로 간주!
                            is_us = True
                            us_results = search_us_ticker(pos_name)
                            if us_results:
                                search_ticker = us_results[0].split(" ")[0]
                                pos_name_kr = us_results[0].split(" (")[1].split(" /")[0]
                            else:
                                search_ticker = pos_name
                                pos_name_kr = pos_name

                    if search_ticker:
                        time.sleep(0.2) 
                        res = analyze_technical_pattern(pos_name_kr, search_ticker)
                        if res:
                            current_price = res['현재가']
                            invested = entry_price * quantity
                            current_val = current_price * quantity
                            
                            # 💡 환율 곱셈 로직 정상화 (미국장에만 1350원 곱하기)
                            if is_us:
                                invested_krw = invested * ex_rate
                                current_val_krw = current_val * ex_rate
                            else:
                                invested_krw = invested
                                current_val_krw = current_val
                            
                            total_invested_all += invested_krw
                            total_current_all += current_val_krw
                            pnl_pct = ((current_price - entry_price) / entry_price) * 100
                            
                            portfolio_summary.append({
                                "종목명": pos_name_kr, "티커": search_ticker, "시장": "미국" if is_us else "한국",
                                "진입단가": entry_price, "현재가": current_price, "수익률(%)": pnl_pct,
                                "평가금액(원환산)": current_val_krw, "상태": res['상태'], "섹터": res.get('섹터', '기타')
                            })
                        else: st.error(f"'{pos_name}' 데이터를 수집할 수 없어 분석에서 제외되었습니다.")
                    else: st.error(f"'{pos_name}' 종목을 찾을 수 없어 분석에서 제외되었습니다.")
                        
                if portfolio_summary:
                    overall_pnl_pct = ((total_current_all - total_invested_all) / total_invested_all) * 100 if total_invested_all > 0 else 0
                    overall_pnl_amt = total_current_all - total_invested_all
                    
                    st.markdown("---")
                    st.markdown("### 🏦 종합 포트폴리오 대시보드")
                    
                    m1, m2, m3, m4 = st.columns(4)
                    m1.metric("총 매수 금액 (원화 환산)", f"{int(total_invested_all):,}원")
                    m2.metric("총 평가 금액 (원화 환산)", f"{int(total_current_all):,}원")
                    m3.metric("총 평가 손익", f"{int(overall_pnl_amt):,}원", f"{overall_pnl_pct:+.2f}%", delta_color="normal" if overall_pnl_amt > 0 else "inverse")
                    m4.metric("보유 종목 수", f"{len(portfolio_summary)}개")
                    
                    summary_df = pd.DataFrame(portfolio_summary)
                    summary_df["비중(%)"] = (summary_df["평가금액(원환산)"] / total_current_all) * 100
                    
                    display_cols = ["종목명", "시장", "섹터", "수익률(%)", "비중(%)", "상태"]
                    st.dataframe(summary_df[display_cols].style.format({"수익률(%)": "{:+.1f}%", "비중(%)": "{:.1f}%"}), use_container_width=True)

                    with st.spinner("AI가 자산 배분 비중과 개별 종목 상태를 종합하여 포트폴리오 리밸런싱 전략을 수립 중입니다..."):
                        now_kst = datetime.utcnow() + timedelta(hours=9)
                        today_str = now_kst.strftime("%Y년 %m월 %d일")
                        port_details_str = ""
                        for item in portfolio_summary:
                            weight = (item["평가금액(원환산)"] / total_current_all) * 100
                            port_details_str += f"- {item['종목명']} ({item['시장']}, {item['섹터']}): 계좌 내 비중 {weight:.1f}%, 수익률 {item['수익률(%)']:+.1f}%, 현재 차트상태: {item['상태']}\n"

                        ai_plan_prompt = f"""
                        당신은 여의도의 냉철한 펀드매니저이자 자산 배분 전문가입니다.
                        🚨 [시스템 필수 지침]: 오늘 날짜는 {today_str}입니다. 
                        [포트폴리오 전체 요약] 총 투자금액: {int(total_invested_all):,}원, 총 평가금액: {int(total_current_all):,}원, 계좌 전체 수익률: {overall_pnl_pct:+.2f}%
                        [개별 구성 종목 상세 (비중 및 상태)]\n{port_details_str}
                        위 포트폴리오를 '개별 종목'이 아닌 '전체 계좌' 관점에서 분석하여 마크다운으로 답변하세요.
                        1. 🏦 **포트폴리오 종합 진단**: 현재 계좌의 자산 배분(특정 섹터에 쏠렸는지 등) 및 전체 수익/리스크 상태에 대한 평가.
                        2. ⚖️ **비중 조절 & 리밸런싱 조언**: 
                           - 현재 비중이 너무 높거나 리스크가 큰 종목은 얼마나 덜어낼 거신가?
                           - 현금화해야 할 종목과 계속 홀딩할 종목 구분.
                        3. 🛡️ **종목별 액션 플랜 요약**: 각 종목별로 유지(Hold), 비중축소(Reduce), 손절(Cut) 여부와 간략한 이유 명시.
                        """
                        plan_result = ask_gemini(ai_plan_prompt, api_key_input)
                        st.success("✅ AI 포트폴리오 종합 진단 및 리밸런싱 플랜 수립 완료!")
                        st.markdown(plan_result)

elif selected_menu == "⭐ 내 관심종목 모니터링":
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

elif selected_menu == "🌍 글로벌 매크로 & AI 분석 (v6.0)":
    st.markdown("## 🌍 글로벌 매크로 & AI 분석 (v6.0)")
    st.write("기관 프랍 트레이더 수준의 거시경제 분석, AI 어닝 리포트 해독, 포트폴리오 최적화 등 하이엔드 기능을 제공합니다.")
    v6_t1, v6_t2, v6_t3, v6_t4, v6_t5 = st.tabs(["🌍 1. 글로벌 매크로 관제소", "💼 2. 스마트머니 & 밸류업 추적", "🧠 3. AI PDF 리포트 해독", "🏆 4. 마코위츠 포트폴리오 최적화", "⚡ 5. 체결강도 & 틱(Tick) 분석"])
    
    with v6_t1:
        st.markdown("### 🌍 글로벌 매크로 & 지정학적 리스크 관제소 (The All-Seeing Eye)")
        if st.button("📊 실시간 글로벌 매크로 데이터 연동", type="primary"):
            with st.spinner("Yahoo Finance에서 원자재 및 국채 금리 데이터를 수집 중입니다..."):
                try:
                    tickers = {"금 (Gold)": "GC=F", "은 (Silver)": "SI=F", "구리 (닥터 코퍼)": "HG=F", "비트코인 (BTC)": "BTC-USD"}
                    series_dict = {}
                    # 순차 yf.Ticker 호출 → yf.download 배치 1회 (4종목 동시 수집)
                    _macro_dl = yf.download(list(tickers.values()), period="6mo",
                                            group_by="ticker", threads=True, progress=False)
                    for name, ticker in tickers.items():
                        try:
                            df_hist = _macro_dl[ticker].dropna(how="all") if len(tickers) > 1 else _macro_dl
                        except Exception as _dg_e:
                            _diag_note("<module>", _dg_e)
                            continue
                        if not df_hist.empty:
                            # yf.download 일봉은 tz-naive로 올 수 있어 tz_localize 전에 방어
                            if getattr(df_hist.index, "tz", None) is not None:
                                df_hist.index = df_hist.index.tz_localize(None)
                            df_hist.index = df_hist.index.normalize()
                            close = df_hist['Close'].dropna()
                            if close.empty:
                                continue
                            normalized = (close / close.iloc[0] - 1) * 100
                            normalized = normalized[~normalized.index.duplicated(keep='first')]
                            series_dict[name] = normalized
                    if series_dict:
                        macro_df = pd.DataFrame(series_dict).ffill().dropna()
                        st.markdown("#### 🥇 원자재 & 암호화폐 슈퍼사이클 트래커 (6개월 상대수익률 %)")
                        fig_macro = px.line(macro_df, x=macro_df.index, y=macro_df.columns)
                        fig_macro.update_layout(height=400, yaxis_title="수익률 (%)", xaxis_title="날짜", hovermode="x unified")
                        st.plotly_chart(fig_macro, use_container_width=True)
                    
                    # 순차 yf.Ticker 2회 → yf.download 배치 1회 (^TNX, ^IRX 동시 수집)
                    _yc_dl = yf.download(["^TNX", "^IRX"], period="6mo",
                                         group_by="ticker", threads=True, progress=False)
                    try:
                        df_10y = _yc_dl["^TNX"].dropna(how="all")
                        df_2y = _yc_dl["^IRX"].dropna(how="all")
                    except Exception:
                        df_10y, df_2y = pd.DataFrame(), pd.DataFrame()
                    if not df_10y.empty and not df_2y.empty:
                        for _d in (df_10y, df_2y):
                            if getattr(_d.index, "tz", None) is not None:
                                _d.index = _d.index.tz_localize(None)
                            _d.index = _d.index.normalize()
                        df_spread = (df_10y['Close'] - df_2y['Close']).dropna()
                        st.markdown("#### 📉 미국채 10년-2년 장단기 금리차 (Yield Curve Spread)")
                        fig_spread = go.Figure()
                        fig_spread.add_trace(go.Scatter(x=df_spread.index, y=df_spread.values, mode='lines', name='10Y-2Y Spread', line=dict(color='purple', width=2)))
                        fig_spread.add_hline(y=0, line_dash="dash", line_color="red", annotation_text="금리 역전 기준선")
                        fig_spread.update_layout(height=300, yaxis_title="금리차 (%)", xaxis_title="날짜")
                        st.plotly_chart(fig_spread, use_container_width=True)
                        
                        current_spread = df_spread.iloc[-1]
                        if current_spread < 0: st.error(f"🚨 **현재 장단기 금리차: {current_spread:.2f}%** (금리 역전 상태 - 잠재적 경기침체 경고)")
                        else: st.success(f"✅ **현재 장단기 금리차: {current_spread:.2f}%** (정상 커브)")
                        
                    if api_key_input:
                        st.divider()
                        prompt = f"당신은 수석 이코노미스트입니다. 현재 장단기 금리차가 {df_spread.iloc[-1] if not df_spread.empty else '알수없음'}%이고, 금, 은, 구리, 비트코인 차트를 보았을 때 현재 시장이 '인플레이션 베팅'인지 '경기침체 우려'인지 3줄로 명확하게 판단해주세요."
                        st.info("💡 **AI 매크로 종합 해석:**\n" + ask_gemini(prompt, api_key_input))
                except Exception as e: st.error(f"매크로 데이터 수집 중 오류 발생: {e}")

    with v6_t2:
        st.markdown("### 💼 스마트머니 딥(Deep) 트래커: 밸류업 & 파생 수급")
        sub_t1, sub_t2 = st.tabs(["🔥 옵션 Put/Call 비율 (US)", "🚀 한국 밸류업 스캐너 (KR)"])
        with sub_t1:
            pc_ticker = st.text_input("분석할 미국 티커 (예: AAPL, NVDA)", value="NVDA").upper()
            if st.button("⚖️ Put/Call 비율 연산"):
                with st.spinner("옵션 체인 데이터 수집 중..."):
                    try:
                        tk = yf.Ticker(pc_ticker)
                        expirations = tk.options
                        if not expirations: st.error("해당 종목의 옵션 데이터가 없습니다.")
                        else:
                            opt = tk.option_chain(expirations[0])
                            call_vol = opt.calls['volume'].sum()
                            put_vol = opt.puts['volume'].sum()
                            if call_vol > 0: pc_ratio = put_vol / call_vol
                            c1, c2, c3 = st.columns(3)
                            c1.metric("총 Call 거래량", f"{int(call_vol):,}")
                            c2.metric("총 Put 거래량", f"{int(put_vol):,}")
                            c3.metric("Put/Call Ratio", f"{pc_ratio:.2f}", "1.0 초과 시 약세 심리", delta_color="inverse" if pc_ratio > 1 else "normal")
                            fig_pc = px.pie(values=[call_vol, put_vol], names=['Call (상승 기대)', 'Put (하락 기대)'], hole=0.5, color_discrete_sequence=['#2ca02c', '#d62728'])
                            st.plotly_chart(fig_pc, use_container_width=True)
                    except Exception as e: st.error(f"옵션 연산 실패: {e}")
        with sub_t2:
            if st.button("🚀 밸류업(Value-up) 잠재주 스캔"):
                with st.spinner("재무제표 및 수익성 스크리닝 중..."):
                    candidates = get_longterm_value_stocks_with_ai("PBR 0.8 이하이면서 ROE 10% 이상인 주주환원 유력 후보", "코스피/코스닥 대형주", api_key_input)
                    if candidates:
                        st.success(f"🎯 AI 밸류업 잠재 기업 포착")
                        for name, code in candidates:
                            res = analyze_technical_pattern(name, code)
                            if res: draw_stock_card(res, api_key_str=api_key_input, is_expanded=False, key_suffix=f"vup_{code}")
                    else: st.error("후보를 찾지 못했습니다.")

    with v6_t3:
        st.markdown("### 🧠 AI 어닝콜 & 공시 원문(PDF) 딥리딩 룸")
        if not HAS_PYPDF: st.warning("⚠️ PyPDF2 모듈이 없습니다. 텍스트를 직접 복사해서 넣어주세요.")
        pdf_file = st.file_uploader("📄 PDF 리포트 업로드", type=["pdf"])
        raw_text = ""
        if pdf_file and HAS_PYPDF:
            with st.spinner("PDF 텍스트 추출 중..."):
                pdf_reader = PyPDF2.PdfReader(pdf_file)
                for page in pdf_reader.pages: raw_text += page.extract_text() + "\n"
        elif not HAS_PYPDF: raw_text = st.text_area("📄 텍스트 직접 붙여넣기:", height=150)
        if raw_text and api_key_input:
            if st.button("🤖 Gemini 리포트 해독 시작", type="primary"):
                with st.spinner("AI 분석 중..."):
                    prompt = f"당신은 리서치 애널리스트입니다. 다음 원문에서 1)목표주가 2)핵심투자포인트 3가지 3)리스크 2가지를 요약해주세요.\n\n{raw_text[:15000]}"
                    st.info(ask_gemini(prompt, api_key_input))

    with v6_t4:
        st.markdown("### 🏆 노벨상 수상 알고리즘: '마코위츠' 포트폴리오 최적화 엔진")
        port_input_m = st.text_input("포트폴리오 종목 (예: AAPL, MSFT, TSLA)", value="AAPL, MSFT, GOOGL, NVDA, TSLA")
        if st.button("⚙️ 몬테카를로 시뮬레이션 (1,000번 반복)", type="primary"):
            tickers_m = [t.strip() for t in port_input_m.split(",") if t.strip()]
            if len(tickers_m) >= 2:
                with st.spinner("최적 가중치 연산 중..."):
                    try:
                        # 순차 yf.Ticker 호출 → yf.download 배치 1회 (컬럼 순서=tickers_m 보존, 라벨 일치 보장)
                        data_m = pd.DataFrame()
                        try:
                            _dl = yf.download(tickers_m, period="1y", threads=True, progress=False)["Close"]
                            if isinstance(_dl, pd.Series):
                                _dl = _dl.to_frame(tickers_m[0])
                            for t in tickers_m:
                                if t in _dl.columns and not _dl[t].dropna().empty:
                                    data_m[t] = _dl[t]
                        except Exception as _dg_e:
                            _diag_note("<module>", _dg_e)
                            pass
                        data_m = data_m.dropna()
                        if not data_m.empty:
                            returns = data_m.pct_change().dropna()
                            mean_returns = returns.mean() * 252
                            cov_matrix = returns.cov() * 252
                            num_portfolios = 1000
                            results_m = np.zeros((3, num_portfolios))
                            weights_record = []
                            for i in range(num_portfolios):
                                weights = np.random.random(len(tickers_m))
                                weights /= np.sum(weights)
                                weights_record.append(weights)
                                portfolio_return = np.sum(mean_returns * weights)
                                portfolio_std_dev = np.sqrt(np.dot(weights.T, np.dot(cov_matrix, weights)))
                                results_m[0,i] = portfolio_return
                                results_m[1,i] = portfolio_std_dev
                                results_m[2,i] = (portfolio_return - 0.02) / portfolio_std_dev
                            results_df = pd.DataFrame(results_m.T, columns=['Return', 'Volatility', 'Sharpe'])
                            max_sharpe_idx = results_df['Sharpe'].idxmax()
                            max_sharpe_port = results_df.iloc[max_sharpe_idx]
                            opt_weights = weights_record[max_sharpe_idx]
                            fig_ef = px.scatter(results_df, x='Volatility', y='Return', color='Sharpe', title="효율적 전선 (Efficient Frontier)")
                            fig_ef.add_trace(go.Scatter(x=[max_sharpe_port['Volatility']], y=[max_sharpe_port['Return']], mode='markers', marker=dict(color='red', size=15, symbol='star'), name='최적점'))
                            st.plotly_chart(fig_ef, use_container_width=True)
                            col_w, col_s = st.columns([1, 1])
                            with col_w:
                                weight_df = pd.DataFrame({'종목': tickers_m, '비율(%)': (opt_weights * 100).round(2)})
                                fig_w = px.pie(weight_df, values='비율(%)', names='종목', hole=0.4)
                                st.plotly_chart(fig_w, use_container_width=True)
                            with col_s:
                                st.metric("예상 연평균 수익률", f"{max_sharpe_port['Return']*100:.2f}%")
                                st.metric("예상 연 변동성", f"{max_sharpe_port['Volatility']*100:.2f}%")
                                st.metric("샤프 지수", f"{max_sharpe_port['Sharpe']:.2f}")
                    except Exception as e: st.error(f"오류: {e}")

    with v6_t5:
        st.markdown("### ⚡ 실시간 호가창 체결강도 & 모멘텀 (1분봉 틱 분석)")
        tick_ticker = st.text_input("종목 티커 입력 (예: TSLA - 야후 파이낸스 1m 데이터)", value="TSLA").upper()
        if st.button("🔎 1분봉 누적 거래량 델타(CVD) 분석"):
            with st.spinner("야후 파이낸스 1분봉 데이터 추출 중..."):
                try:
                    df_tick = yf.Ticker(tick_ticker).history(period="1d", interval="1m")
                    if df_tick.empty: st.error("1분봉 데이터가 없습니다.")
                    else:
                        delta_direction = np.sign(df_tick['Close'] - df_tick['Open'])
                        delta_direction = delta_direction.replace(0, method='ffill').fillna(1)
                        df_tick['CVD'] = (df_tick['Volume'] * delta_direction).cumsum()
                        fig_tick = go.Figure()
                        fig_tick.add_trace(go.Scatter(x=df_tick.index, y=df_tick['Close'], name='주가', line=dict(color='blue', width=2)))
                        fig_tick.add_trace(go.Scatter(x=df_tick.index, y=df_tick['CVD'], name='누적 매수압력(CVD)', yaxis='y2', line=dict(color='orange', width=2, dash='dot')))
                        fig_tick.update_layout(title=f"[{tick_ticker}] 당일 1분봉 주가 vs 누적 매수 압력(CVD)", yaxis=dict(title="주가"), yaxis2=dict(title="CVD", overlaying="y", side="right"), height=400, hovermode="x unified")
                        st.plotly_chart(fig_tick, use_container_width=True)
                except Exception as e: st.error(f"분석 실패: {e}")

elif selected_menu == "🗺️ 시장 주도주 자금 히트맵":
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


elif selected_menu == "🕸️ 실시간 섹터 순환매 추적":
    st.markdown("## 🕸️ 실시간 섹터 순환매 추적")
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


elif selected_menu == "📅 핵심 증시 일정 & IPO 달력":
    st.subheader("📅 핵심 증시 일정 & IPO 달력")
    cal_tab2, cal_tab3 = st.tabs(["🗓️ 통합 일정 달력 (경제지표+수급)", "🇰🇷 국내 IPO 분석"])

    with cal_tab2:
        st.markdown("#### 🗓️ 경제지표 · 파생수급 통합 달력")
        cc1, cc2, cc3 = st.columns([1, 8, 1])
        with cc1:
            if st.button("◀ 이전 달", use_container_width=True, key="us_prev"):
                st.session_state.smart_cal_month -= 1
                if st.session_state.smart_cal_month == 0:
                    st.session_state.smart_cal_month = 12
                    st.session_state.smart_cal_year -= 1
                st.rerun()
        with cc2: st.markdown(f"<h3 style='text-align: center; margin:0;'>{st.session_state.smart_cal_year}년 {st.session_state.smart_cal_month}월</h3>", unsafe_allow_html=True)
        with cc3:
            if st.button("다음 달 ▶", use_container_width=True, key="us_next"):
                st.session_state.smart_cal_month += 1
                if st.session_state.smart_cal_month == 13:
                    st.session_state.smart_cal_month = 1
                    st.session_state.smart_cal_year += 1
                st.rerun()
                
        if st.button("🔄 오늘로 돌아가기", key="us_today"):
            st.session_state.smart_cal_year = datetime.now().year
            st.session_state.smart_cal_month = datetime.now().month
            st.rerun()

        year = st.session_state.smart_cal_year
        month = st.session_state.smart_cal_month
        calendar.setfirstweekday(calendar.SUNDAY)
        cal = calendar.monthcalendar(year, month)
        
        fridays = [week[5] for week in cal if week[5] != 0]
        us_opex_day = fridays[2] if len(fridays) >= 3 else fridays[-1]
        us_opex_week_days = [us_opex_day - 4 + i for i in range(5)]

        tax_day = -1
        if month == 4:
            tax_day = 15
            for week in cal:
                if week[6] == 15: tax_day = 17 
                if week[0] == 15: tax_day = 16 

        thursdays = [week[calendar.THURSDAY] for week in cal if week[calendar.THURSDAY] != 0]
        kr_opex_day = thursdays[1] if len(thursdays) >= 2 else thursdays[0]
        kr_is_quadruple = month in [3, 6, 9, 12]
        today_day = datetime.now().day if year == datetime.now().year and month == datetime.now().month else -1

        html_parts = [
            "<style>",
            ".cal-grid { display: grid; grid-template-columns: repeat(7, 1fr); gap: 2px; background: #ddd; border: 1px solid #ccc; font-family: sans-serif; }",
            ".cal-head { background: #f8f9fa; text-align: center; font-weight: bold; padding: 10px; font-size: 14px; }",
            ".cal-cell { background: white; min-height: 120px; padding: 5px; display: flex; flex-direction: column; }",
            ".cal-cell.today { background: #f0f8ff; border: 2px solid #1f77b4; }",
            ".cal-num { font-weight: bold; margin-bottom: 5px; font-size: 15px; }",
            ".evt-us-red { background: #ffebee; color: #c62828; font-size: 11px; padding: 3px; margin-bottom: 2px; border-left: 3px solid #c62828; border-radius: 2px; font-weight: bold; line-height: 1.2; letter-spacing: -0.5px; }",
            ".evt-us-warn { background: #fff3e0; color: #e65100; font-size: 11px; padding: 3px; margin-bottom: 2px; border-left: 3px solid #e65100; border-radius: 2px; font-weight: bold; line-height: 1.2; letter-spacing: -0.5px; }",
            ".evt-us-green { background: #e8f5e9; color: #2e7d32; font-size: 11px; padding: 3px; margin-bottom: 2px; border-left: 3px solid #2e7d32; border-radius: 2px; font-weight: bold; line-height: 1.2; letter-spacing: -0.5px; }",
            ".evt-kr-red { background: #fce4ec; color: #b71c1c; font-size: 11px; padding: 3px; margin-bottom: 2px; border-left: 3px solid #b71c1c; border-radius: 2px; font-weight: bold; line-height: 1.2; letter-spacing: -0.5px; }",
            ".evt-kr-blue { background: #e3f2fd; color: #1565c0; font-size: 11px; padding: 3px; margin-bottom: 2px; border-left: 3px solid #1565c0; border-radius: 2px; font-weight: bold; line-height: 1.2; letter-spacing: -0.5px; }",
            ".evt-kr-green { background: #f1f8e9; color: #1b5e20; font-size: 11px; padding: 3px; margin-bottom: 2px; border-left: 3px solid #1b5e20; border-radius: 2px; font-weight: bold; line-height: 1.2; letter-spacing: -0.5px; }",
            ".evt-econ-fomc { background: #ede7f6; color: #4527a0; font-size: 11px; padding: 3px; margin-bottom: 2px; border-left: 3px solid #4527a0; border-radius: 2px; font-weight: bold; line-height: 1.2; letter-spacing: -0.5px; }",
            ".evt-econ-cpi { background: #fff8e1; color: #ff6f00; font-size: 11px; padding: 3px; margin-bottom: 2px; border-left: 3px solid #ff6f00; border-radius: 2px; font-weight: bold; line-height: 1.2; letter-spacing: -0.5px; }",
            ".evt-econ-jobs { background: #e0f7fa; color: #006064; font-size: 11px; padding: 3px; margin-bottom: 2px; border-left: 3px solid #006064; border-radius: 2px; font-weight: bold; line-height: 1.2; letter-spacing: -0.5px; }",
            ".evt-econ-bok { background: #fce4ec; color: #880e4f; font-size: 11px; padding: 3px; margin-bottom: 2px; border-left: 3px solid #880e4f; border-radius: 2px; font-weight: bold; line-height: 1.2; letter-spacing: -0.5px; }",
            "</style>",
            "<div class='cal-grid'>",
            "<div class='cal-head' style='color:#d32f2f;'>일</div><div class='cal-head'>월</div><div class='cal-head'>화</div><div class='cal-head'>수</div><div class='cal-head'>목</div><div class='cal-head'>금</div><div class='cal-head' style='color:#1976d2;'>토</div>"
        ]
        
        econ_events = get_economic_events(year, month)

        for week in cal:
            for i, day in enumerate(week):
                if day == 0: html_parts.append("<div class='cal-cell' style='background:#fafafa;'></div>")
                else:
                    events = ""
                    # 경제지표(FOMC·CPI·고용·금통위)를 가장 위에 표시
                    for label, cls in econ_events.get(day, []):
                        events += f"<div class='{cls}'>{label}</div>"
                    if day == tax_day: events += "<div class='evt-us-red'>🔴 🇺🇸세금납부일(하락압력)</div>"
                    if i == calendar.THURSDAY:
                        if day == kr_opex_day:
                            label = "🔥 🇰🇷네마녀의 날" if kr_is_quadruple else "🔴 🇰🇷옵션만기일"
                            events += f"<div class='evt-kr-red'>{label}(수급극대)</div>"
                        else: events += "<div class='evt-kr-blue'>🔹 🇰🇷위클리 만기(오후변동)</div>"
                    elif i == calendar.FRIDAY and day == kr_opex_day + 1: events += "<div class='evt-kr-green'>🟢 🇰🇷수급 되돌림(추세복귀)</div>"

                    if day in us_opex_week_days:
                        if day == us_opex_day: events += "<div class='evt-us-red'>🔴 🇺🇸옵션만기(변동성폭발)</div>"
                        else: events += "<div class='evt-us-warn'>⚠️ 🇺🇸만기주간(핀닝/하락)</div>"

                    num_color = "#d32f2f" if i == 0 else "#1976d2" if i == 6 else "#333"
                    cell_cls = "cal-cell today" if day == today_day else "cal-cell"
                    day_lbl = f"{day} (오늘)" if day == today_day else str(day)
                    html_parts.append(f"<div class='{cell_cls}'><div class='cal-num' style='color:{num_color};'>{day_lbl}</div>{events}</div>")

        html_parts.append("</div>")
        st.markdown("".join(html_parts), unsafe_allow_html=True)

        st.markdown(
            "<div style='margin-top:10px;font-size:12px;color:#555;line-height:1.9;'>"
            "<b>범례</b> &nbsp; "
            "<span style='background:#ede7f6;color:#4527a0;padding:2px 6px;border-radius:3px;'>🏛️ 중앙은행(FOMC·ECB·BOJ·의사록)</span> "
            "<span style='background:#fff8e1;color:#ff6f00;padding:2px 6px;border-radius:3px;'>📊 물가(CPI·PCE)</span> "
            "<span style='background:#e0f7fa;color:#006064;padding:2px 6px;border-radius:3px;'>👷 경기(고용·PMI·소매판매·수출입)</span> "
            "<span style='background:#fce4ec;color:#880e4f;padding:2px 6px;border-radius:3px;'>🏦 한은 금통위</span> "
            "<span style='background:#ffebee;color:#c62828;padding:2px 6px;border-radius:3px;'>🔴 옵션만기</span> "
            "<span style='background:#e3f2fd;color:#1565c0;padding:2px 6px;border-radius:3px;'>🔹 위클리만기</span>"
            "</div>",
            unsafe_allow_html=True,
        )
        st.caption(
            "ℹ️ **확정 일정(2026)** — 중앙은행(FOMC·한은·ECB·BOJ)·FOMC 의사록, 미 CPI·고용지표(BLS 공식), "
            "옵션만기(미 셋째 금요일·한국 둘째 목요일, 규칙 기반). "
            "**추정 일정** — PCE·소매판매·ISM·한국 CPI·중국 PMI·한국 수출입은 통상 발표 시기 기준이라 실제 발표일과 1~2일 차이날 수 있습니다. "
            "정부 셧다운 등으로 발표일이 사후 연기될 수 있으니 중대한 매매 전엔 원출처를 확인하세요."
        )

    with cal_tab3:
        with st.spinner("최신 IPO 일정을 파싱 중입니다..."):
            ipo_df = get_naver_ipo_data()
        if not ipo_df.empty:
            active_n = (ipo_df['청약일정'].astype(str).str.strip().replace({'nan': '-'}) != '-').sum()
            st.caption(f"📋 총 {len(ipo_df)}개 종목 · 청약 일정 확정 {active_n}개 (파란 음영) ｜ "
                       "**공모가**=주식을 처음 파는 가격, **청약**=상장 전 미리 사겠다고 신청, "
                       "**경쟁률**=청약 경쟁 정도(높을수록 인기), **따상**=상장일 시초가 2배+상한가")
            sty_ipo = style_ipo_table(ipo_df)
            if sty_ipo is not None:
                st.dataframe(sty_ipo, use_container_width=True, height=460)
            else:
                st.dataframe(ipo_df, use_container_width=True, hide_index=True)
            if api_key_input:
                if st.button("🤖 AI 공모주 옥석 가리기", type="primary"):
                    with st.spinner("AI가 공모주를 분석 중입니다..."):
                        ai_cols = [c for c in ['종목명', '청약일정', '공모가', '경쟁률', '업종'] if c in ipo_df.columns]
                        st.success(ask_gemini(
                            f"다음은 예정된 IPO 공모주 목록입니다:\n{ipo_df[ai_cols].to_string()}\n"
                            "이 중 상장일 '따상(시초가 2배+상한가)' 가능성이 높은 1~2개를 꼽고, "
                            "업종 매력도·경쟁률·시장 분위기를 근거로 각 3줄 이내로 평가해줘.", api_key_input))
            else:
                st.info("💡 사이드바에 API 키를 입력하면 'AI 공모주 옥석 가리기'로 따상 후보를 분석할 수 있어요.")
        else:
            st.error("❌ 현재 예정된 신규 상장(IPO) 일정이 없거나, 거래소 데이터를 불러올 수 없습니다. (주말·연휴엔 비어 있을 수 있어요)")

elif selected_menu == "📋 코스피·코스닥 종목 리스트":
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

elif selected_menu == "🚀 단기 스윙 퀀트 스캐너":
    st.markdown("## 🚀 단기 스윙 퀀트 스캐너")
    scan_tab, backtest_tab = st.tabs(["🚀 실시간 조건 검색 스캐너", "🧪 전략 백테스팅 (비용·거래단위 통계)"])
    
    with scan_tab:
        show_beginner_guide()
        show_trading_guidelines()
        
        scan_market = st.radio("시장 선택 (스캐너)", ["🇰🇷 국내 주식", "🇺🇸 미국 주식"], horizontal=True)
        _is_kr_scan = scan_market.startswith("🇰🇷")

        # 체크박스 기본값(프리셋으로 일괄 세팅하기 위해 key + session_state 사용)
        for _k, _dv in [("sc_golden", False), ("sc_pullback", True), ("sc_rsi", False),
                        ("sc_vol", False), ("sc_twin", False), ("sc_pension", False),
                        ("sc_weekly", False), ("sc_high52", False), ("sc_mfi", False)]:
            st.session_state.setdefault(_k, _dv)

        # ⚡ 조건 프리셋 원클릭 (on_click 콜백은 위젯 생성 전에 실행돼 안전하게 상태를 세팅)
        def _apply_scan_preset(on_keys):
            for _k in ["sc_golden", "sc_pullback", "sc_rsi", "sc_vol", "sc_twin",
                       "sc_pension", "sc_weekly", "sc_high52", "sc_mfi"]:
                st.session_state[_k] = (_k in on_keys)
        st.caption("⚡ **빠른 프리셋** — 한 번에 조건 세팅:")
        _pc1, _pc2, _pc3, _pc4 = st.columns(4)
        _pc1.button("🚀 돌파형", use_container_width=True, help="정배열/골든 + 52주 신고가권 + 거래량 급증 + 자금유입",
                    on_click=_apply_scan_preset, args=(["sc_golden", "sc_high52", "sc_vol", "sc_mfi"],))
        _pc2.button("📉 낙폭 반등형", use_container_width=True, help="RSI 과매도 + 20일선 눌림목",
                    on_click=_apply_scan_preset, args=(["sc_rsi", "sc_pullback"],))
        _pc3.button("🐋 세력주형", use_container_width=True, help="외인·기관 쌍끌이 + 거래량 급증 + 기관 연속매수",
                    on_click=_apply_scan_preset, args=(["sc_twin", "sc_vol", "sc_pension"],))
        _pc4.button("♻️ 조건 초기화", use_container_width=True, on_click=_apply_scan_preset, args=([],))

        col_c1, col_c2, col_c3, col_c4 = st.columns(4)
        with col_c1:
            cond_golden = st.checkbox("✨ 골든크로스 / 정배열 초입", key="sc_golden")
            cond_pullback = st.checkbox("✅ 20일선 눌림목 (타점 근접)", key="sc_pullback")
        with col_c2:
            cond_rsi_bottom = st.checkbox("🔵 RSI 30 이하 (낙폭과대)", key="sc_rsi")
            cond_vol_spike = st.checkbox("🔥 최근 거래량 급증 (세력 의심)", key="sc_vol")
        with col_c3:
            cond_twin_buy = st.checkbox("🐋 외인/기관 쌍끌이 순매수", key="sc_twin")
            cond_high52 = st.checkbox("🚀 52주 신고가권 (주도주)", key="sc_high52",
                                      help="현재가가 52주 최고가 대비 -3% 이내 (신고가 돌파 모멘텀)")
        with col_c4:
            cond_pension = st.checkbox("👴 기관 3일 연속 순매수", key="sc_pension")
            cond_weekly = st.checkbox("📅 주봉도 상승 추세만 (멀티TF)", key="sc_weekly")
            cond_mfi = st.checkbox("💰 MFI 자금 유입 (55~80)", key="sc_mfi",
                                   help="거래량 가중 자금흐름지표(MFI) 55~80 — 과열 전 건강한 매집 구간")

        _sc_col1, _sc_col2 = st.columns([2.2, 1.8])
        with _sc_col1:
            scan_mode = st.radio("🔬 검색 방식", ["🎯 조건 필터 (체크한 조건 전부 충족)", "🏆 점수 랭킹 (충족 개수로 정렬·1개 이상)"],
                                 horizontal=True,
                                 help="조건 필터: AND 방식 — 깐깐하지만 결과가 0개일 수 있음.\n점수 랭킹: 체크한 조건 중 몇 개를 충족하는지 점수화해 많이 충족한 순으로 보여줌 — 장이 안 좋은 날에도 상대적 상위 종목 발굴 가능.")
        with _sc_col2:
            scan_limit = st.selectbox("스캔할 상위 종목 수", [50, 100, 200, 300], index=3)

        # 💧 유동성·가격·과열 하드필터 (선택한 조건과 별개로 항상 적용, 0 = 미적용)
        with st.container(border=True):
            st.caption("💧 **유동성·가격 필터** — 실제로 사고팔 수 있는 종목만 남깁니다 (0=미적용):")
            _fl1, _fl2, _fl3 = st.columns(3)
            if _is_kr_scan:
                with _fl1:
                    _min_amt_disp = st.number_input("최소 거래대금 (억)", 0, 100000, 0, 10,
                                                    help="20일 평균 거래대금 하한. 저유동성·동전주 제외 (예: 30억)")
                with _fl2:
                    _min_price = st.number_input("최소 주가 (원)", 0, 2000000, 0, 100, help="동전주 제외")
                _min_amt_raw = _min_amt_disp * 1e8
            else:
                with _fl1:
                    _min_amt_disp = st.number_input("최소 거래대금 ($M)", 0.0, 200000.0, 0.0, 5.0,
                                                    help="20일 평균 거래대금 하한(백만달러). 저유동성 제외")
                with _fl2:
                    _min_price = st.number_input("최소 주가 ($)", 0.0, 100000.0, 0.0, 1.0, help="페니주 제외")
                _min_amt_raw = _min_amt_disp * 1e6
            with _fl3:
                _excl_overext = st.checkbox("🚫 과이격(추격) 종목 제외", value=False,
                                            help="20일선 대비 +15% 이상 벌어진 과열 종목 제외 (추격매수 방지)")
        
        # 📋 체크박스 → (라벨, 판정함수) 레지스트리로 일원화 (필터/점수 모드 공용)
        scan_checks = []
        if cond_golden: scan_checks.append(("✨ 정배열/골든크로스", lambda r: ("🔥 완벽 정배열" in str(r.get('배열상태', ''))) or ("✨ 5-20 골든크로스" in str(r.get('배열상태', '')))))
        if cond_pullback: scan_checks.append(("✅ 눌림목 타점", lambda r: r.get('상태') == "✅ 타점 근접 (분할 매수)"))
        if cond_rsi_bottom: scan_checks.append(("🔵 RSI≤30", lambda r: float(r.get('RSI', 100)) <= 30))
        if cond_vol_spike: scan_checks.append(("🔥 거래량 급증", lambda r: r.get('거래량 급증') == "🔥 거래량 터짐"))
        if cond_twin_buy: scan_checks.append(("🐋 쌍끌이 매수", lambda r: ("+" in str(r.get('기관수급', ''))) and ("+" in str(r.get('외인수급', '')))))
        if cond_pension: scan_checks.append(("👴 기관 3일 연속", lambda r: r.get('연기금연속순매수', 0) >= 3))
        if cond_weekly: scan_checks.append(("📅 주봉 상승", lambda r: "상승추세" in str(r.get('주봉추세', ''))))
        if cond_high52: scan_checks.append(("🚀 52주 신고가권", lambda r: (_f_num(r.get('고점대비52주')) is not None and _f_num(r.get('고점대비52주')) >= -3)))
        if cond_mfi: scan_checks.append(("💰 MFI 자금유입", lambda r: (_f_num(r.get('MFI')) is not None and 55 <= _f_num(r.get('MFI')) <= 80)))
        
        if st.button("🚀 쾌속 병렬 스캔 시작", type="primary", use_container_width=True):
            if not scan_checks:
                st.warning("⚠️ 검색 조건을 최소 1개 이상 체크해주세요. (조건 없이 스캔하면 전 종목이 쏟아져 화면이 멈출 수 있어요)")
            else:
                with st.spinner(f"⚡ {scan_limit}개 종목 고속 필터링 중..."):
                    if scan_market == "🇰🇷 국내 주식": targets = get_scan_targets(scan_limit)
                    else: targets = get_us_scan_targets(scan_limit)
                        
                    if not targets: st.error("❌ 종목 데이터를 불러오지 못했습니다.")
                    else:
                        _is_score_mode = scan_mode.startswith("🏆")
                        progress_bar = st.progress(0)
                        status_text = st.empty()
                        found_results = []
                        completed, total = 0, len(targets)
                        def process_stock(target):
                            name, code = target
                            time.sleep(0.1) 
                            res = analyze_technical_pattern(name, code, offset_days=0)
                            if not res: return None
                            # 💧 유동성·가격·과열 하드필터 (선택 조건과 별개로 우선 적용)
                            if _min_amt_raw > 0:
                                _a = _f_num(res.get('평균거래대금20일'))
                                if _a is None or _a < _min_amt_raw: return None
                            if _min_price > 0:
                                _p = _f_num(res.get('현재가'))
                                if _p is None or _p < _min_price: return None
                            if _excl_overext:
                                _g = _f_num(res.get('이격도20'))
                                if _g is not None and _g >= 15: return None
                            passed = []
                            for _lbl, _fn in scan_checks:
                                try:
                                    if _fn(res): passed.append(_lbl)
                                except Exception as _dg_e:
                                    _diag_note("process_stock", _dg_e)
                                    pass
                            if _is_score_mode:
                                if not passed: return None          # 점수 모드: 1개 이상 충족만
                            else:
                                if len(passed) < len(scan_checks): return None   # 필터 모드: 전부 충족
                            res['_score'] = len(passed)
                            res['스캔점수'] = f"{len(passed)}/{len(scan_checks)}"
                            res['충족조건'] = " · ".join(passed)
                            return res
                        with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
                            for future in concurrent.futures.as_completed({executor.submit(process_stock, t): t for t in targets}):
                                res = future.result()
                                completed += 1
                                if res: found_results.append(res)
                                progress_bar.progress(completed / total)
                                status_text.text(f"⚡ 스캔 진행 중... ({completed}/{total}) - {len(found_results)}개 포착")
                        if _is_score_mode:
                            found_results.sort(key=lambda r: r.get('_score', 0), reverse=True)
                        st.session_state.scan_results = found_results
                        st.session_state.scan_results_meta = {
                            "time": datetime.now().strftime("%Y-%m-%d %H:%M"),
                            "market": scan_market, "mode": "점수 랭킹" if _is_score_mode else "조건 필터",
                            "conds": " · ".join(lbl for lbl, _ in scan_checks), "limit": scan_limit,
                            "filters": (" · ".join([f for f in [
                                (f"거래대금≥{_min_amt_disp}{'억' if _is_kr_scan else '$M'}" if _min_amt_disp else ""),
                                (f"주가≥{_min_price}{'원' if _is_kr_scan else '$'}" if _min_price else ""),
                                ("과이격 제외" if _excl_overext else ""),
                            ] if f]) or "없음"),
                        }
                        st.rerun()
        if st.session_state.scan_results is not None:
            _meta = st.session_state.get("scan_results_meta") or {}
            _info_col, _clear_col = st.columns([5, 1], vertical_alignment="center")
            with _info_col:
                if _meta:
                    st.caption(f"🕒 스캔 시각: **{_meta.get('time','-')}** ｜ {_meta.get('market','')} 상위 {_meta.get('limit','')}개 ｜ 방식: {_meta.get('mode','')} ｜ 조건: {_meta.get('conds','')} ｜ 필터: {_meta.get('filters','없음')}")
            with _clear_col:
                if st.button("🗑️ 결과 지우기", key="scan_clear_btn", use_container_width=True):
                    st.session_state.scan_results = None
                    st.session_state.scan_results_meta = None
                    st.rerun()
            if st.session_state.scan_results is not None:
                display_sorted_results(st.session_state.scan_results, tab_key="t2", api_key=api_key_input)

    with backtest_tab:
        st.markdown("### 🧪 단기 스윙 전략 시뮬레이터")
        st.write("과거 데이터를 기반으로 다양한 퀀트 전략의 실제 수익률과 타점을 검증합니다. (실제 분석 기간은 결과 리포트에 표시됩니다)")
        
        market_choice_bt = st.radio("시장 선택 (백테스트)", ["🇰🇷 국내 주식", "🇺🇸 미국 주식"], horizontal=True, label_visibility="collapsed")
        t_code = None
        if market_choice_bt == "🇰🇷 국내 주식":
            krx_df = get_krx_stocks()
            opts = ["🔍 테스트할 종목 검색"] + (krx_df['Name'].astype(str) + " (" + krx_df['Code'].astype(str) + ")").tolist() if not krx_df.empty else ["005930"]
            test_query = st.selectbox("백테스트 종목:", opts)
            if test_query != "🔍 테스트할 종목 검색":
                t_code = test_query.rsplit("(", 1)[-1].replace(")", "").strip() if "(" in test_query else "005930"
        else:
            with st.form("bt_us_form"):
                us_bt_query = st.text_input("🔍 미국 주식 종목명/티커 (예: AAPL):")
                us_bt_search_btn = st.form_submit_button("검색")
            if us_bt_search_btn and us_bt_query:
                with st.spinner("검색 중..."): us_bt_results = search_us_ticker(us_bt_query)
                if us_bt_results: st.session_state.us_bt_results = us_bt_results
                else: st.error("검색 결과가 없습니다.")
            if "us_bt_results" in st.session_state and st.session_state.us_bt_results:
                sel_us_bt = st.selectbox("🎯 정확한 종목 선택:", ["선택하세요"] + st.session_state.us_bt_results)
                if sel_us_bt != "선택하세요": t_code = sel_us_bt.split(" ")[0]
        
        _bt_c1, _bt_c2 = st.columns([2.5, 1.5])
        with _bt_c1:
            strategy_sel = st.selectbox("🎯 백테스트 퀀트 전략 선택", [
                "5-20 이평선 골든크로스", "RSI 과매도 매수 (RSI < 30)", "볼린저밴드 하단 매수", "MACD 교차"
            ])
        with _bt_c2:
            bt_cost_pct = st.number_input("💸 왕복 거래비용 (%)", min_value=0.0, max_value=2.0, value=0.25, step=0.05,
                                          help="수수료+거래세+슬리피지를 합친 왕복(매수+매도) 비용. 국내 일반계좌 기준 약 0.2~0.4%, 미국 주식은 0.05~0.2% 수준을 권장합니다. 0으로 두면 비용 미반영(기존 방식).")

        # 🛡️ [개선] 손절·익절·보유상한 청산 규칙 (0 = 미적용 → 기존 신호 청산만)
        _bt_e1, _bt_e2, _bt_e3 = st.columns(3)
        with _bt_e1:
            bt_stop = st.number_input("🛑 손절 (%)", min_value=0.0, max_value=50.0, value=0.0, step=0.5,
                                      help="진입가 대비 이만큼 하락하면 청산. 0=미적용(신호로만 청산). 앱 권장 손절은 20일선 -3% 수준.")
        with _bt_e2:
            bt_target = st.number_input("🎯 익절 (%)", min_value=0.0, max_value=200.0, value=0.0, step=1.0,
                                        help="진입가 대비 이만큼 상승하면 청산. 0=미적용.")
        with _bt_e3:
            bt_maxhold = st.number_input("📆 최대 보유일", min_value=0, max_value=250, value=0, step=1,
                                         help="진입 후 이 영업일수를 넘기면 강제 청산. 0=미적용.")
        st.caption("💡 손절·익절·보유상한은 신호 청산보다 **우선** 적용됩니다. 셋 다 0이면 기존처럼 ‘신호 On=진입 / Off=청산’만 검증합니다. "
                   "일봉 종가 기준이라 장중 터치는 반영하지 않습니다(보수적 측정).")

        if t_code and st.button("▶️ 시뮬레이션 돌리기", type="primary"):
            with st.spinner("과거 1년 데이터 백테스팅 중..."):
                bt_df = get_historical_data(t_code, 365)
                if not bt_df.empty:
                    bt_df['MA5'] = bt_df['Close'].rolling(5).mean()
                    bt_df['MA20'] = bt_df['Close'].rolling(20).mean()
                    bt_df['Std_20'] = bt_df['Close'].rolling(window=20).std()
                    bt_df['Bollinger_Lower'] = bt_df['MA20'] - (bt_df['Std_20'] * 2)
                    delta = bt_df['Close'].diff()
                    rs = (delta.where(delta > 0, 0.0).rolling(14).mean()) / (-delta.where(delta < 0, 0.0).rolling(14).mean())
                    bt_df['RSI'] = 100 - (100 / (1 + rs))
                    exp1 = bt_df['Close'].ewm(span=12, adjust=False).mean()
                    exp2 = bt_df['Close'].ewm(span=26, adjust=False).mean()
                    bt_df['MACD'] = exp1 - exp2
                    bt_df['Signal_Line'] = bt_df['MACD'].ewm(span=9, adjust=False).mean()

                    bt_df['Signal'] = 0
                    if strategy_sel == "5-20 이평선 골든크로스": bt_df.loc[bt_df['MA5'] > bt_df['MA20'], 'Signal'] = 1
                    elif strategy_sel == "RSI 과매도 매수 (RSI < 30)": bt_df.loc[bt_df['RSI'] < 30, 'Signal'] = 1
                    elif strategy_sel == "볼린저밴드 하단 매수": bt_df.loc[bt_df['Close'] < bt_df['Bollinger_Lower'], 'Signal'] = 1
                    elif strategy_sel == "MACD 교차": bt_df.loc[bt_df['MACD'] > bt_df['Signal_Line'], 'Signal'] = 1

                    bt_df['Daily_Return'] = bt_df['Close'].pct_change()

                    # 🛡️ [개선] 손절·익절·보유상한 청산을 반영한 이벤트 기반 시뮬레이션.
                    #   진입: 관망(flat) 중 신호 발생일 종가 매수 → 다음날부터 수익 귀속(기존과 동일)
                    #   청산 우선순위: 손절 → 익절 → 보유상한 → 신호종료.
                    #   손절/익절/보유상한 청산 후에는 신호가 한 번 꺼졌다 다시 켜져야 재진입(휩쏘 방지).
                    #   신호종료 청산이면 즉시 재진입 가능(기존 동작과 동일).
                    _sig = bt_df['Signal'].fillna(0).values
                    _closes = bt_df['Close'].values
                    _dates = bt_df.index
                    _n = len(_closes)
                    _stop_f = (bt_stop / 100.0) if bt_stop > 0 else None
                    _tgt_f = (bt_target / 100.0) if bt_target > 0 else None
                    _maxh = int(bt_maxhold) if bt_maxhold > 0 else None
                    _oneway_cost = (bt_cost_pct / 2.0) / 100.0
                    _rt_cost = bt_cost_pct / 100.0

                    _pos = np.zeros(_n)
                    trade_records = []
                    _armed = True
                    _entry_i = None
                    _idx = 0
                    while _idx < _n:
                        if _entry_i is None:                       # 관망 상태
                            if _armed and _sig[_idx] == 1:
                                _entry_i = _idx                    # 신호일 종가 매수
                            elif _sig[_idx] == 0:
                                _armed = True
                            _idx += 1
                            continue
                        _entry_px = _closes[_entry_i]
                        _exit_i, _reason = None, None
                        _j = _entry_i + 1
                        while _j < _n:
                            _pos[_j] = 1                           # 보유일 표시
                            _chg = _closes[_j] / _entry_px - 1.0
                            if _stop_f is not None and _chg <= -_stop_f:
                                _exit_i, _reason = _j, "손절"; break
                            if _tgt_f is not None and _chg >= _tgt_f:
                                _exit_i, _reason = _j, "익절"; break
                            if _maxh is not None and (_j - _entry_i) >= _maxh:
                                _exit_i, _reason = _j, "보유상한"; break
                            if _sig[_j] == 0:
                                _exit_i, _reason = _j, "신호종료"; break
                            _j += 1
                        if _exit_i is None:                        # 기간 끝까지 보유 중
                            _exit_i, _reason, _open_trade = _n - 1, "보유중", True
                        else:
                            _open_trade = False
                        _ret = (_closes[_exit_i] / _entry_px - 1.0) - _rt_cost
                        trade_records.append({
                            "진입일": _dates[_entry_i].strftime("%y/%m/%d"),
                            "청산일": _dates[_exit_i].strftime("%y/%m/%d") + (" (보유중)" if _open_trade else ""),
                            "청산사유": _reason,
                            "보유일": max((_dates[_exit_i] - _dates[_entry_i]).days, 1),
                            "수익률(%)": _ret * 100.0,
                        })
                        _armed = (_reason == "신호종료")           # 신호종료면 즉시 재진입 가능
                        _entry_i = None
                        _idx = _exit_i + 1

                    bt_df['Position'] = _pos
                    bt_df['Trade_Mark'] = bt_df['Position'].diff().fillna(0)
                    # 💸 왕복 거래비용: 진입/청산 발생일마다 편도 비용 차감
                    bt_df['Strategy_Return'] = (bt_df['Position'] * bt_df['Daily_Return']) - (bt_df['Trade_Mark'].abs() * _oneway_cost)
                    bt_df['Cumulative_Market'] = (1 + bt_df['Daily_Return']).cumprod()
                    bt_df['Cumulative_Strategy'] = (1 + bt_df['Strategy_Return']).cumprod()

                    bt_df['Cum_Max'] = bt_df['Cumulative_Strategy'].cummax()
                    bt_df['Drawdown'] = (bt_df['Cumulative_Strategy'] - bt_df['Cum_Max']) / bt_df['Cum_Max']
                    mdd = bt_df['Drawdown'].min() * 100

                    # 📈 '매수→매도' 거래 단위 통계
                    total_trades = len(trade_records)
                    _wins = [t for t in trade_records if t["수익률(%)"] > 0]
                    _losses = [t for t in trade_records if t["수익률(%)"] <= 0]
                    win_rate = (len(_wins) / total_trades * 100.0) if total_trades > 0 else 0.0
                    avg_win = (sum(t["수익률(%)"] for t in _wins) / len(_wins)) if _wins else 0.0
                    avg_loss = (sum(t["수익률(%)"] for t in _losses) / len(_losses)) if _losses else 0.0
                    _gross_win = sum(t["수익률(%)"] for t in _wins)
                    _gross_loss = abs(sum(t["수익률(%)"] for t in _losses))
                    profit_factor = (_gross_win / _gross_loss) if _gross_loss > 0 else (float('inf') if _gross_win > 0 else 0.0)
                    avg_hold = (sum(t["보유일"] for t in trade_records) / total_trades) if total_trades > 0 else 0.0

                    # 📐 샤프지수 (연환산, 무위험수익률 0 가정)
                    _sr_std = bt_df['Strategy_Return'].std()
                    sharpe = (bt_df['Strategy_Return'].mean() / _sr_std * (252 ** 0.5)) if _sr_std and _sr_std > 0 else 0.0
                    # 🎲 기대값(회당 평균) · 평균 손익비(Payoff) · 시장 노출도 · CAGR
                    expectancy = (sum(t["수익률(%)"] for t in trade_records) / total_trades) if total_trades > 0 else 0.0
                    payoff = (avg_win / abs(avg_loss)) if avg_loss < 0 else (float('inf') if avg_win > 0 else 0.0)
                    exposure = (float(_pos.sum()) / _n * 100.0) if _n > 0 else 0.0
                    _cum_final = float(bt_df['Cumulative_Strategy'].iloc[-1])
                    _years = _n / 252.0
                    cagr = ((_cum_final ** (1.0 / _years) - 1.0) * 100.0) if (_cum_final > 0 and _years > 0) else 0.0
                    _exit_counts = {}
                    for _t in trade_records:
                        _exit_counts[_t["청산사유"]] = _exit_counts.get(_t["청산사유"], 0) + 1
                    
                    fig = go.Figure()
                    x_axis = bt_df.index
                    fig.add_trace(go.Scatter(x=x_axis, y=bt_df['Close'], name="주가 (Close)", line=dict(color='#3b82f6', width=1.5)))
                    buy_idx = bt_df[bt_df['Trade_Mark'] == 1].index
                    fig.add_trace(go.Scatter(x=buy_idx, y=bt_df.loc[buy_idx, 'Close'], mode='markers', name='Buy (매수)', marker=dict(symbol='triangle-up', size=14, color='#ef4444', line=dict(width=1, color='darkred'))))
                    sell_idx = bt_df[bt_df['Trade_Mark'] == -1].index
                    fig.add_trace(go.Scatter(x=sell_idx, y=bt_df.loc[sell_idx, 'Close'], mode='markers', name='Sell (매도)', marker=dict(symbol='triangle-down', size=14, color='#3b82f6', line=dict(width=1, color='darkblue'))))

                    fig.update_layout(title=f"'{t_code}' 백테스트 타점 시각화 ({strategy_sel})", height=500, hovermode="x unified", legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1))
                    st.plotly_chart(fig, use_container_width=True)
                    
                    final_market = (bt_df['Cumulative_Market'].iloc[-1] - 1) * 100
                    final_strat = (bt_df['Cumulative_Strategy'].iloc[-1] - 1) * 100
                    
                    _period_str = f"{bt_df.index[0].strftime('%Y.%m.%d')} ~ {bt_df.index[-1].strftime('%Y.%m.%d')} (영업일 {len(bt_df)}일)"
                    st.markdown("### 📊 백테스트 성과 리포트")
                    st.caption(f"🗓️ 실제 분석 기간: **{_period_str}** ｜ 💸 왕복 거래비용 **{bt_cost_pct:.2f}%** 반영 ｜ 승률·손익은 '매수→매도' **거래 단위** 기준")
                    c1, c2, c3, c4 = st.columns(4)
                    def metric_card(title, value, delta=None, is_red=False, is_green=False):
                        bg_color = "rgba(100, 100, 100, 0.05)"
                        border_color = "#888"
                        if is_red:
                            bg_color = "rgba(220, 38, 38, 0.08)"
                            border_color = "#dc2626"
                        elif is_green:
                            bg_color = "rgba(22, 163, 74, 0.08)"
                            border_color = "#16a34a"
                        delta_html = f"<div style='font-size:0.85em; margin-top:5px; color:#555;'>{delta}</div>" if delta else ""
                        return f"<div style='background-color: {bg_color}; padding: 15px; border-radius: 8px; border-left: 4px solid {border_color}; margin-bottom: 10px;'><div style='font-size:0.9em; color:#555; font-weight:bold;'>{title}</div><div style='font-size:1.6em; font-weight:bold; font-family:\"JetBrains Mono\", monospace; margin-top:5px;'>{value}</div>{delta_html}</div>"

                    with c1: st.markdown(metric_card("전략 누적 수익률", f"{final_strat:.2f}%", f"단순 보유 대비 {final_strat - final_market:+.2f}%p (비용 차감 후)", is_red=(final_strat>0), is_green=(final_strat<0)), unsafe_allow_html=True) 
                    with c2: st.markdown(metric_card("최대 낙폭 (MDD)", f"{mdd:.2f}%", "계좌 최대 하락률", is_green=(mdd<-20)), unsafe_allow_html=True)
                    with c3: st.markdown(metric_card("거래별 승률", f"{win_rate:.1f}%", f"총 {total_trades}건 중 {len(_wins)}건 수익", is_red=(win_rate>50)), unsafe_allow_html=True)
                    with c4: st.markdown(metric_card("Profit Factor", "∞" if profit_factor == float('inf') else f"{profit_factor:.2f}", "총수익 ÷ 총손실 (1 초과 = 우위)", is_red=(profit_factor>1)), unsafe_allow_html=True)
                    
                    c5, c6, c7, c8 = st.columns(4)
                    with c5: st.markdown(metric_card("평균 수익 거래", f"+{avg_win:.2f}%", "수익 거래의 평균 수익률", is_red=(avg_win>0)), unsafe_allow_html=True)
                    with c6: st.markdown(metric_card("평균 손실 거래", f"{avg_loss:.2f}%", "손실 거래의 평균 손실률", is_green=(avg_loss<0)), unsafe_allow_html=True)
                    with c7: st.markdown(metric_card("평균 보유 기간", f"{avg_hold:.1f}일", "거래당 평균 보유일"), unsafe_allow_html=True)
                    with c8: st.markdown(metric_card("샤프 지수 (연환산)", f"{sharpe:.2f}", "1 이상이면 양호한 위험 대비 수익"), unsafe_allow_html=True)

                    c9, c10, c11, c12 = st.columns(4)
                    with c9: st.markdown(metric_card("기대값 (회당)", f"{expectancy:+.2f}%", "거래 1회 평균 손익(비용 후)", is_red=(expectancy>0), is_green=(expectancy<0)), unsafe_allow_html=True)
                    with c10: st.markdown(metric_card("CAGR (연환산)", f"{cagr:+.2f}%", "전략 연환산 복리 수익률", is_red=(cagr>0), is_green=(cagr<0)), unsafe_allow_html=True)
                    with c11: st.markdown(metric_card("평균 손익비", "∞" if payoff == float('inf') else f"{payoff:.2f}", "평균수익 ÷ 평균손실 (Payoff)", is_red=(payoff>=1 and payoff!=float('inf')) or payoff==float('inf')), unsafe_allow_html=True)
                    with c12: st.markdown(metric_card("시장 노출도", f"{exposure:.0f}%", "전체 기간 중 실제 보유일 비중"), unsafe_allow_html=True)

                    if _exit_counts:
                        _ec_txt = " · ".join(f"{k} {v}건" for k, v in sorted(_exit_counts.items(), key=lambda x: -x[1]))
                        _rule_txt = " · ".join([x for x in [
                            (f"손절 {bt_stop:.1f}%" if bt_stop > 0 else ""),
                            (f"익절 {bt_target:.1f}%" if bt_target > 0 else ""),
                            (f"보유상한 {int(bt_maxhold)}일" if bt_maxhold > 0 else ""),
                        ] if x])
                        if _rule_txt:
                            st.caption(f"🚪 청산 사유 분포: {_ec_txt}  ｜  적용 규칙: {_rule_txt}")
                        else:
                            st.caption(f"🚪 청산 사유 분포: {_ec_txt}  (손절·익절 미적용 — 신호 청산만)")

                    if trade_records:
                        def _prc_trades():
                            _tr_df = pd.DataFrame(trade_records)
                            _tr_df["수익률(%)"] = _tr_df["수익률(%)"].map(lambda v: round(v, 2))
                            st.dataframe(_tr_df, use_container_width=True, hide_index=True)
                            st.caption("※ 진입가 = 신호 발생일 종가, 청산가 = 청산일 종가(손절·익절도 일봉 종가 기준). "
                                       "'청산사유'로 손절/익절/보유상한/신호종료를 구분합니다. '(보유중)'은 기간 종료까지 미청산 → 마지막 종가로 평가한 거래입니다.")
                        _register_popup("trades", _prc_trades)
                        _popup_button(f"📜 전체 거래 내역 보기 ({total_trades}건)", "trades", f"📜 전체 거래 내역 ({total_trades}건)", key="btn_trades")
                    else:
                        st.info("해당 기간에 전략 조건을 충족한 거래가 없었습니다.")
                else: st.error("❌ 데이터를 가져오지 못했습니다.")

        # =====================================================================
        # 🧪 [v7.2] 점수 엔진 검증 (스코어 백테스트)
        #   위 시뮬레이터는 '이평선/RSI 같은 단일 전략'을 검증한다.
        #   여기서는 앱 전반이 쓰는 score_one() 점수 자체가 실제 수익률과
        #   관계가 있는지를 검증한다. 과거 시점(offset_days)의 기술적 상태로
        #   점수를 매기고, 그 이후 실제 수익률과 대조한다.
        # =====================================================================
        st.divider()
        with st.expander("🧪 점수 엔진 검증 — 이 앱의 '점수'가 실제 수익률과 관계있는지 확인", expanded=False):
            st.caption(
                "발굴기·스캐너가 쓰는 **score_one() 점수**를 과거 시점 기준으로 매긴 뒤, 그 이후 실제 주가 수익률과 대조합니다. "
                "점수가 높은 그룹의 평균 수익률이 낮은 그룹보다 높게 나와야 점수 엔진이 의미가 있습니다. "
                "가중치는 `scoring_weights.py` 에서 조정할 수 있고, 아래에서 값을 바꿔 즉시 재검증할 수 있습니다."
            )

            _sb1, _sb2, _sb3 = st.columns(3)
            with _sb1:
                sb_market = st.radio("시장", ["🇰🇷 국내", "🇺🇸 미국"], horizontal=True, key="sb_market")
            with _sb2:
                sb_offset = st.selectbox("검증 시점 (며칠 전 기준으로 점수를 매길지)", [20, 40, 60, 90], index=1,
                                         key="sb_offset",
                                         help="예: 40 → 40영업일 전 시점의 차트 상태로 점수를 매기고, 그 이후 오늘까지의 실제 수익률과 비교합니다.")
            with _sb3:
                sb_n = st.selectbox("표본 종목 수", [30, 50, 100, 200], index=1, key="sb_n",
                                    help="많을수록 통계가 안정되지만 그만큼 오래 걸립니다(종목당 약 0.3~1초).")

            sb_lookahead = st.checkbox(
                "수급·밸류·컨센서스도 점수에 포함 (⚠️ 룩어헤드 있음)", value=False, key="sb_lookahead",
                help="수급·PER/PBR·목표가는 '지금' 값만 조회할 수 있어 과거 시점 점수에 넣으면 미래 정보가 섞입니다(룩어헤드 편향). "
                     "기본값(끔)은 순수 기술적 지표만으로 점수를 매겨 편향 없이 검증합니다.")

            _w_json = st.text_area(
                "가중치 덮어쓰기 (JSON, 비우면 기본값)", value="", height=68, key="sb_weights",
                placeholder='예: {"S_ALIGN_PERFECT": 30, "S_VOL_SPIKE": 10}',
                help="scoring_weights.py 의 DEFAULT_WEIGHTS 키만 사용할 수 있습니다. 값을 바꿔 돌려보면서 어떤 가중치가 성과를 개선하는지 확인하세요.")

            if st.button("🧪 점수 엔진 검증 실행", type="primary", use_container_width=True, key="sb_run"):
                _w_over = None
                _w_err = None
                if _w_json.strip():
                    try:
                        _w_over = make_weights(json.loads(_w_json))
                    except Exception as e:
                        _w_err = f"{type(e).__name__}: {e}"
                if _w_err:
                    st.error(f"❌ 가중치 JSON 오류 — {_w_err}\n\n사용 가능한 키는 {len(tunable_keys())}개입니다. scoring_weights.py 를 참고하세요.")
                else:
                    _sb_targets = get_scan_targets(sb_n) if sb_market == "🇰🇷 국내" else get_us_scan_targets(sb_n)
                    if not _sb_targets:
                        st.error("❌ 종목 리스트를 불러오지 못했습니다.")
                    else:
                        # 과거 시점 점수에 '지금 값'이 섞이지 않도록 제거할 필드
                        _LEAK_KEYS = ("외인수급", "기관수급", "개인수급", "장중잠정수급",
                                      "기관연속순매수", "외인연속순매수", "연기금추정순매수", "연기금연속순매수",
                                      "PER", "PBR", "목표가_컨센서스", "AI목표가")
                        _sb_mood = {"risk_on": 0.0, "_idx20": None}   # 과거 시장 분위기는 복원 불가 → 중립 고정

                        def _sb_one(target):
                            name, code = target
                            time.sleep(0.1)
                            res = analyze_technical_pattern(name, code, offset_days=int(sb_offset))
                            if not res:
                                return None
                            fwd = _f_num(res.get("수익률"))
                            if fwd is None:
                                return None
                            tech = dict(res)
                            if not sb_lookahead:
                                for k in _LEAK_KEYS:
                                    tech.pop(k, None)
                            try:
                                sc, hz, top, grade, _rs, _rf = score_one(
                                    tech, None, _sb_mood, weights=_w_over)
                            except Exception as _dg_e:
                                _diag_note("_sb_one", _dg_e)
                                return None
                            return {"종목명": name, "코드": code, "점수": top, "구간": hz, "등급": grade,
                                    "단기": sc["단기"], "중기": sc["중기"], "장기": sc["장기"],
                                    f"이후 {sb_offset}일 수익률(%)": round(fwd, 2)}

                        _sb_rows, _done = [], 0
                        _pb, _stat = st.progress(0), st.empty()
                        with concurrent.futures.ThreadPoolExecutor(max_workers=5) as ex:
                            for fut in concurrent.futures.as_completed(
                                    {ex.submit(_sb_one, t): t for t in _sb_targets}):
                                r = fut.result()
                                _done += 1
                                if r: _sb_rows.append(r)
                                _pb.progress(_done / len(_sb_targets))
                                _stat.text(f"🧪 검증 중... ({_done}/{len(_sb_targets)}) — {len(_sb_rows)}개 유효")
                        _pb.empty(); _stat.empty()
                        st.session_state["sb_result"] = {
                            "rows": _sb_rows, "offset": int(sb_offset), "market": sb_market,
                            "n_req": len(_sb_targets), "lookahead": bool(sb_lookahead),
                            "weights": ("사용자 지정" if _w_over else "기본값"),
                            "time": datetime.now().strftime("%Y-%m-%d %H:%M"),
                        }

            _sb_res = st.session_state.get("sb_result")
            if _sb_res and _sb_res["rows"]:
                _off = _sb_res["offset"]
                _rcol = f"이후 {_off}일 수익률(%)"
                sb_df = pd.DataFrame(_sb_res["rows"])
                if _rcol not in sb_df.columns:      # 이전 실행 결과(다른 기간)와 컬럼명이 다를 때
                    _rcol = [c for c in sb_df.columns if c.startswith("이후 ")][0]

                st.caption(f"📌 {_sb_res['time']} · {_sb_res['market']} · 요청 {_sb_res['n_req']}종목 중 "
                           f"**{len(sb_df)}종목 유효** · 가중치 {_sb_res['weights']} · "
                           f"{'⚠️ 룩어헤드 포함' if _sb_res['lookahead'] else '✅ 기술적 지표만(편향 없음)'}")

                # --- 순위상관 (Spearman): 점수 순위와 수익률 순위가 같이 움직이는가 ---
                _s = sb_df["점수"].rank()
                _r = sb_df[_rcol].rank()
                _rho = float(np.corrcoef(_s, _r)[0, 1]) if len(sb_df) > 2 and _s.std() > 0 and _r.std() > 0 else float("nan")

                # --- 점수 구간별 성과 ---
                _bins = [0, 40, 50, 60, 70, 100.01]
                _labels = ["~40 (약함)", "40~50", "50~60", "60~70", "70~ (강력)"]
                sb_df["_구간"] = pd.cut(sb_df["점수"], bins=_bins, labels=_labels, right=False)
                _agg = sb_df.groupby("_구간", observed=False).agg(
                    종목수=(_rcol, "size"),
                    평균수익률=(_rcol, "mean"),
                    중앙값=(_rcol, "median"),
                    승률=(_rcol, lambda s: (s > 0).mean() * 100 if len(s) else np.nan),
                ).reset_index().rename(columns={"_구간": "점수구간"})
                _agg = _agg[_agg["종목수"] > 0]
                for _c in ("평균수익률", "중앙값", "승률"):
                    _agg[_c] = _agg[_c].astype(float).round(2)

                _m1, _m2, _m3 = st.columns(3)
                _hi = sb_df[sb_df["점수"] >= 60][_rcol]
                _lo = sb_df[sb_df["점수"] < 50][_rcol]
                _spread = (_hi.mean() - _lo.mean()) if (len(_hi) and len(_lo)) else float("nan")
                with _m1:
                    st.metric("순위상관 (Spearman ρ)", "N/A" if _rho != _rho else f"{_rho:+.3f}",
                              help="점수 순위와 이후 수익률 순위의 상관. +0.1~0.2만 되어도 실무적으로 의미 있는 신호로 봅니다. 0 근처면 점수가 무의미하다는 뜻입니다.")
                with _m2:
                    st.metric("고점수(60↑) − 저점수(50↓) 수익률 차", "N/A" if _spread != _spread else f"{_spread:+.2f}%p",
                              help="점수 엔진이 실제로 잘 고르는지 보여주는 가장 직관적인 수치. 음수면 점수가 거꾸로 작동하고 있다는 뜻입니다.")
                with _m3:
                    st.metric("전체 평균 수익률", f"{sb_df[_rcol].mean():+.2f}%",
                              help="표본 전체 평균. 개별 구간 성과는 이 값과 비교해서 봐야 합니다(시장 전체가 오른 기간일 수 있음).")

                st.dataframe(_agg, use_container_width=True, hide_index=True)

                try:
                    _fig_sb = px.bar(_agg, x="점수구간", y="평균수익률", text="평균수익률",
                                     color="평균수익률", color_continuous_scale=["#dc2626", "#94a3b8", "#16a34a"],
                                     title=f"점수 구간별 이후 {_off}영업일 평균 수익률")
                    _fig_sb.update_traces(texttemplate="%{text:.2f}%", textposition="outside")
                    _fig_sb.update_layout(height=330, showlegend=False, coloraxis_showscale=False,
                                          margin=dict(t=50, b=10))
                    st.plotly_chart(_fig_sb, use_container_width=True)
                except Exception as e:
                    _diag_note("score_backtest_chart", e)

                with st.expander(f"📋 종목별 상세 ({len(sb_df)}건)"):
                    st.dataframe(sb_df.drop(columns=["_구간"]).sort_values("점수", ascending=False),
                                 use_container_width=True, hide_index=True)

                st.info(
                    "**해석 주의**\n"
                    f"- 표본 {len(sb_df)}종목·단일 기간({_off}영업일) 결과라 그대로 일반화하면 안 됩니다. 기간과 표본을 바꿔가며 반복 검증하세요.\n"
                    "- 검증 시점 이후 상장폐지·거래정지된 종목은 애초에 리스트에 없어 **생존 편향**이 있습니다.\n"
                    "- 표본은 '현재 거래대금 상위' 종목이라, 그 사이 거래대금이 늘어난 종목이 과대 대표됩니다.\n"
                    "- 시장 전체가 오른 기간이면 모든 구간이 플러스로 나옵니다. **구간 간 차이**를 보세요."
                )
            elif _sb_res:
                st.warning("유효한 결과가 없습니다. 표본 수를 늘리거나 검증 시점을 짧게 잡아보세요.")

elif selected_menu == "📉 낙폭과대 스캐너 (고점대비 -30%↓)":
    st.markdown("## 📉 낙폭과대 스캐너")
    st.caption("고점 대비 크게 하락한 종목만 추려냅니다. 낙폭과대 반등(역추세) 후보 발굴용 — "
               "**'떨어진 데는 이유가 있을 수 있으니'** 펀더멘털·뉴스를 반드시 함께 확인하세요.")

    if "dd_results" not in st.session_state:
        st.session_state.dd_results = None
        st.session_state.dd_meta = None

    c1, c2, c3 = st.columns(3)
    with c1:
        dd_scope_label = st.radio("🌍 시장", ["🇰🇷 국내", "🇺🇸 미국", "🇰🇷+🇺🇸 모두"], horizontal=True)
    with c2:
        min_fall = st.slider("📉 최소 낙폭 (고점 대비)", 20, 70, 30, step=5, format="%d%%")
    with c3:
        lookback = st.radio("📅 고점 기준", ["52주", "전체기간"], horizontal=True)
    c4, c5 = st.columns(2)
    with c4:
        dd_depth = st.select_slider("🔬 스캔 범위 (거래대금/시총 상위)",
                                    options=["상위 100", "상위 200", "상위 400"], value="상위 200")
    with c5:
        rb_label = st.select_slider("📈 ‘저점대비 반등’ 측정 기간",
                                    options=["1개월", "3개월", "6개월", "1년"], value="6개월")
    depth_n = {"상위 100": 100, "상위 200": 200, "상위 400": 400}[dd_depth]
    rebound_days = {"1개월": 21, "3개월": 63, "6개월": 126, "1년": 252}[rb_label]
    lb = "52주" if lookback == "52주" else "전체"
    st.caption("⏳ 범위가 넓을수록 1~3분 걸릴 수 있어요(종목별 시세 조회). 결과는 캐시되어 재실행이 빠릅니다.")

    def _prc_indicators():
        st.markdown(
            f"""
- **낙폭 (고점 대비)** — 선택한 기간({lookback})의 **최고가에서 현재가가 얼마나 떨어졌는지**. 예: -40%면 천장 대비 40% 하락. 값이 클수록(−쪽으로) 많이 빠진 것.
- **저점대비 반등** — 최근 **{rb_label}** 동안의 **가장 낮은 가격(바닥)에서 현재가가 얼마나 올라왔는지**. 바닥을 찍고 회복이 시작됐는지 보는 지표입니다.
    - **+0% 근처** → 아직 신저가 부근, 바닥 확인 안 됨 (떨어지는 칼날 주의 🔪)
    - **+10~30%** → 바닥 다지고 반등 초입일 가능성 (역추세 매매 관심 구간 ⭐)
    - **+100% 이상** → 이미 반등이 많이 진행됨 (늦었을 수 있음)
- **RSI** — 0~100 사이 과매수/과매도 지표. **30 이하면 🧊과매도**(단기 반등 기대 구간이나 추세 하락 지속 위험도 큼).
- **고점일** — 위 ‘최고가’가 기록된 날짜.
- **🩹 회복점수 (0~100)** — ‘많이 빠진 것’과 ‘회복이 시작된 것’은 다릅니다. 기술 신호(20일선 회복·단기 골든크로스·**저점 높이기**·거래량 회복·OBV 매집·60일선 상승 전환) + 반등 위치(바닥 확인 후 초입 구간 가점) + RSI 구간 + **테마 온기**(소속 업종/섹터가 살아나는 중인지)를 합산한 종합 점수입니다. 🟢70↑ 회복 유력 · 🟡50↑ 회복 조짐 · ⚪30↑ 관찰 · 🔴30↓ 바닥 미확인.
- **테마온기(%)** — 국내는 네이버 업종 전일 등락률, 미국은 섹터 ETF 최근 5거래일 수익률. 종목 혼자가 아니라 **업종 전체가 돌아서는지**(테마적 회복) 확인하는 지표.

💡 **활용 팁**: ‘많이 빠졌으면서(낙폭 큼) + 바닥 다지고 살짝 고개 든(반등 +10~30%) + 회복점수 높은’ 종목이 반등 매매에선 매력적입니다. 표 아래 **🤖 AI 회복 검증** 버튼을 누르면 상위 종목의 하락 원인이 일회성인지 구조적인지 실시간 검색으로 교차 확인해줍니다.
표의 **각 컬럼 머리글을 클릭하면 오름차순/내림차순 정렬**됩니다 (숫자 정렬).
"""
        )
    _register_popup("indicators", _prc_indicators)
    _popup_button("📖 지표 설명 보기 (꼭 읽어보세요)", "indicators", "📖 지표 설명", key="btn_indicators")

    if st.button("🔎 낙폭 스캔 시작", type="primary", use_container_width=True):
        scope = ("kr" if dd_scope_label.startswith("🇰🇷 국내")
                 else "us" if dd_scope_label.startswith("🇺🇸 미국") else "both")
        # 시장(코스피/코스닥)·섹터 룩업 준비
        kr_meta = {}
        if scope in ("kr", "both"):
            try:
                kdf = get_krx_stocks()
                if not kdf.empty:
                    for _, rr in kdf.iterrows():
                        kr_meta[str(rr["Code"]).zfill(6)] = (
                            (rr.get("Market") if "Market" in kdf.columns else "") or "국내",
                            (rr.get("Sector") if "Sector" in kdf.columns else "") or "-")
            except Exception as _dg_e:
                _diag_note("<module>", _dg_e)
                pass
        us_sec = get_us_sector_map() if scope in ("us", "both") else {}

        universe = []
        if scope in ("kr", "both"):
            try:
                for n, c in (get_scan_targets(depth_n) or []):
                    c = str(c).zfill(6)
                    mk, sec = kr_meta.get(c, ("국내", "-"))
                    universe.append((n, c, mk or "국내", sec or "-"))
            except Exception as _dg_e:
                _diag_note("<module>", _dg_e)
                pass
        if scope in ("us", "both"):
            try:
                for n, c in (get_us_scan_targets(min(depth_n, 500)) or []):
                    c = str(c)
                    universe.append((n, c, "미국", us_sec.get(c, "-")))
            except Exception as _dg_e:
                _diag_note("<module>", _dg_e)
                pass
        seen, uni = set(), []
        for n, c, mk, sec in universe:
            if c in seen:
                continue
            seen.add(c); uni.append((n, c, mk, sec))
        if not uni:
            st.error("❌ 종목 유니버스를 불러오지 못했습니다. 잠시 후 다시 시도해 주세요.")
        else:
            prog = st.progress(0.0); status = st.empty()
            done, total, rows = 0, len(uni), []

            def _dd_work(item):
                n, c, mk, sec = item
                return n, c, mk, sec, get_drawdown_info(c, lb, rebound_days)

            with concurrent.futures.ThreadPoolExecutor(max_workers=8) as ex:
                for fut in concurrent.futures.as_completed({ex.submit(_dd_work, it): it for it in uni}):
                    try:
                        n, c, mk, sec, info = fut.result()
                        if info and info["drawdown"] is not None and info["drawdown"] <= -min_fall:
                            rows.append({"name": n, "code": c, "market": mk, "sector": sec, **info})
                    except Exception as _dg_e:
                        _diag_note("<module>", _dg_e)
                        pass
                    done += 1
                    prog.progress(min(1.0, done / total))
                    status.text(f"📉 낙폭 스캔 중... ({done}/{total})")
            prog.empty(); status.empty()
            rows.sort(key=lambda r: r["drawdown"])   # 가장 많이 빠진 순

            # 업종 보강 — FDR 업종이 비어 '기타/분류불가'인 결과 종목만 네이버에서 개별 조회(가벼움)
            need_sec = [r for r in rows if str(r["code"]).isdigit()
                        and (not r.get("sector") or r["sector"] in ("-", "기타/분류불가"))]
            if need_sec:
                ss = st.empty(); ss.text(f"🏷️ 업종 분류 중... ({len(need_sec)}종목)")
                with concurrent.futures.ThreadPoolExecutor(max_workers=8) as ex:
                    fsec = {ex.submit(get_stock_sector_kr, r["code"]): r for r in need_sec}
                    for f in concurrent.futures.as_completed(fsec):
                        r = fsec[f]
                        try:
                            s = f.result()
                            if s:
                                r["sector"] = s
                        except Exception as _dg_e:
                            _diag_note("<module>", _dg_e)
                            pass
                ss.empty()

            st.session_state.dd_results = rows
            st.session_state.dd_meta = (dd_scope_label, min_fall, lookback, len(uni), rb_label)

    # ===== 결과 렌더 =====
    rows = st.session_state.dd_results
    if rows is not None:
        meta = st.session_state.dd_meta
        if not rows:
            st.warning(f"조건(고점 대비 -{meta[1]}% 이하)을 만족하는 종목이 없습니다. 낙폭 기준을 낮춰보세요.")
        else:
            st.success(f"✅ {meta[3]}개 스캔 중 **{len(rows)}개** 포착 — 고점({meta[2]}) 대비 **-{meta[1]}% 이하** · 반등기준 {meta[4] if len(meta) > 4 else '6개월'}")
            
            # 🩹 [NEW] 회복 가능성 점수 산출 (테마 온기 + 기술 신호 합산)
            _any_kr = any(str(r["code"]).isdigit() for r in rows)
            _any_us = any(not str(r["code"]).isdigit() for r in rows)
            with st.spinner("🩹 업종/섹터 온기 조회 및 회복 점수 계산 중..."):
                _kr_heat = get_kr_sector_heat() if _any_kr else {}
                _us_heat = get_us_sector_heat() if _any_us else {}
                for r in rows:
                    _is_kr = str(r["code"]).isdigit()
                    _hv = match_sector_heat(r.get("sector"), _kr_heat, _us_heat, _is_kr)
                    r["_heat"] = _hv
                    r["_rec_score"], r["_rec_grade"], r["_rec_why"] = calc_recovery_score(r, _hv)
            
            _dd_sort = st.radio("⬇️ 정렬 기준", ["🩹 회복점수 높은순 (추천)", "📉 낙폭 깊은순", "📈 저점대비 반등 높은순"],
                                horizontal=True, key="dd_sort_radio")
            if _dd_sort.startswith("🩹"):
                rows = sorted(rows, key=lambda r: (r.get("_rec_score", 0), -abs(r.get("drawdown") or 0)), reverse=True)
            elif _dd_sort.startswith("📈"):
                rows = sorted(rows, key=lambda r: (r.get("rebound") if r.get("rebound") is not None else -999), reverse=True)
            else:
                rows = sorted(rows, key=lambda r: r["drawdown"])
            
            # 시장 구성으로 가격 단위 판별(정렬 가능하도록 숫자 컬럼 유지)
            codes = [str(r["code"]) for r in rows]
            all_kr = all(c.isdigit() for c in codes)
            all_us = all(not c.isdigit() for c in codes)
            price_label = "현재가(원)" if all_kr else ("현재가($)" if all_us else "현재가")
            high_label = "최고가(원)" if all_kr else ("최고가($)" if all_us else "최고가")

            df_rows = []
            for i, r in enumerate(rows, 1):
                rsi = r.get("rsi")
                _sec = str(r.get("sector") or "-")
                if len(_sec) > 16:
                    _sec = _sec[:16] + "…"
                df_rows.append({
                    "순위": i,
                    "종목명": r["name"],
                    "시장": r["market"],
                    "테마/섹터": _sec,
                    "🩹회복점수": r.get("_rec_score", 0),
                    "회복판정": r.get("_rec_grade", "-"),
                    "테마온기(%)": (round(float(r["_heat"]), 1) if r.get("_heat") is not None else None),
                    price_label: round(float(r["current"]), 2),
                    high_label: round(float(r["high"]), 2),
                    "고점일": (r.get("high_date") or "-"),
                    "낙폭(%)": round(float(r["drawdown"]), 1),
                    "저점대비반등(%)": (round(float(r["rebound"]), 1) if r.get("rebound") is not None else None),
                    "RSI": (int(rsi) if rsi is not None else None),
                    "회복근거": r.get("_rec_why", "-"),
                })
            dd_df = pd.DataFrame(df_rows)
            price_fmt = "%.0f" if all_kr else ("$%.2f" if all_us else "%.2f")
            if hasattr(st, "column_config"):
                st.dataframe(
                    dd_df, use_container_width=True, hide_index=True,
                    height=min(640, 80 + len(df_rows) * 35),
                    column_config={
                        "순위": st.column_config.NumberColumn("순위", format="%d", width="small"),
                        "🩹회복점수": st.column_config.ProgressColumn("🩹회복점수", min_value=0, max_value=100, format="%d",
                            help="기술 신호(20일선 회복·저점 높이기·거래량/OBV 회복 등) + 반등 위치 + RSI 구간 + 업종 온기를 합산한 0~100점. 70↑ 회복 유력 / 50↑ 회복 조짐 / 30↓ 바닥 미확인."),
                        "테마온기(%)": st.column_config.NumberColumn("테마온기(%)", format="%+.1f%%",
                            help="국내: 네이버 업종 전일 등락률 ｜ 미국: 섹터 ETF 최근 5거래일 수익률. 업종이 살아나는 중인지(테마적 회복) 확인."),
                        price_label: st.column_config.NumberColumn(price_label, format=price_fmt),
                        high_label: st.column_config.NumberColumn(high_label, format=price_fmt),
                        "낙폭(%)": st.column_config.NumberColumn("낙폭(%)", format="%.1f%%",
                            help="고점 대비 하락률 (현재가÷최고가−1). 음수일수록 많이 빠진 것."),
                        "저점대비반등(%)": st.column_config.NumberColumn("저점대비반등(%)", format="%+.1f%%",
                            help="선택 기간 내 최저가(바닥) 대비 현재가 상승률. 바닥 회복 정도."),
                        "RSI": st.column_config.NumberColumn("RSI", format="%d",
                            help="0~100 과매수/과매도 지표. 30 이하면 과매도."),
                        "회복근거": st.column_config.TextColumn("회복근거", width="large",
                            help="회복점수에 반영된 신호 목록"),
                    },
                )
            else:
                # 구버전 Streamlit: 숫자 컬럼이면 머리글 클릭 정렬이 숫자로 동작(서식만 미적용)
                st.dataframe(dd_df, use_container_width=True, hide_index=True,
                             height=min(640, 80 + len(df_rows) * 35))
            st.caption("💡 컬럼 머리글을 클릭하면 **숫자 기준 오름차순/내림차순 정렬**됩니다. "
                       "🩹회복점수 = 기술 신호 + 반등 위치 + RSI + 테마 온기 종합 (🟢70↑ 유력 · 🟡50↑ 조짐 · ⚪30↑ 관찰 · 🔴30↓ 바닥 미확인). "
                       "상세 차트·수급·재무는 '🔬 개별 기업 정밀 진단' 탭에서 확인하세요.")
            st.download_button("⬇️ 결과 CSV 저장", dd_df.to_csv(index=False).encode("utf-8-sig"),
                               "낙폭과대_스캔.csv", "text/csv")
            
            # 🤖 [NEW] AI 회복 검증 — 상위 후보의 '하락 원인(일회성 vs 구조적)'과 테마 회복 가능성을 검색으로 교차 확인
            st.markdown("---")
            _top_n = min(10, len(rows))
            _top_rows = sorted(rows, key=lambda r: r.get("_rec_score", 0), reverse=True)[:_top_n]
            if st.button(f"🤖 AI 회복 검증 — 회복점수 상위 {_top_n}개 종목의 하락 원인·테마 전망 분석 (실시간 검색)",
                         use_container_width=True, key="dd_ai_btn"):
                if not api_key_input:
                    st.error("좌측 사이드바에 Gemini API 키를 입력해주세요.")
                else:
                    _facts = "\n".join(
                        f"- {r['name']} ({r['code']}/{r['market']}/{r.get('sector','-')}): "
                        f"낙폭 {r['drawdown']:.1f}% · 저점대비반등 {r.get('rebound','-')}% · RSI {r.get('rsi','-')} · "
                        f"회복점수 {r.get('_rec_score',0)}점 · 신호[{r.get('_rec_why','-')}] · 업종온기 {r.get('_heat','-')}%"
                        for r in _top_rows)
                    _prompt = f"""당신은 낙폭과대 역발상(컨트래리언) 전략 전문 펀드매니저입니다. 아래는 우리 시스템이 실측한 낙폭과대 종목 데이터입니다.

[검증된 실데이터]
{_facts}

반드시 '구글 검색(Google Search)'으로 각 종목의 최근 뉴스·공시를 확인한 뒤, 종목별로 아래 형식의 마크다운 표 한 줄씩 작성하세요:
| 종목명 | 하락 원인 (검색 근거) | 원인 성격 | 테마/업황 회복 전망 | 회복 가능성 |
- '원인 성격'은 [일회성 악재 / 수급·시장 동반 하락 / 구조적 악화] 중 택1.
- '회복 가능성'은 [상/중/하] + 5단어 이내 근거.
- 구조적 악화(실적 붕괴·산업 사양화·재무 위험)로 판단되면 회복 가능성 '하'로 솔직하게 평가할 것.
- 검색으로 확인 안 되는 내용은 '확인 불가'로 적고 지어내지 말 것.
표 아래에 '🏆 최종 회복 유력 TOP 3'를 이유와 함께 3줄로 요약. 마지막 줄에 '※ 투자 조언이 아닌 참고용' 표기."""
                    with st.spinner("🔍 AI가 종목별 하락 원인과 테마 전망을 실시간 검색으로 교차 확인 중... (10~20초)"):
                        _ai_out = None
                        try:
                            _g_res = _genai_generate(_prompt, api_key_input, grounding=True)
                            if _g_res.candidates and _g_res.candidates[0].content.parts:
                                _ai_out = _g_res.text
                        except Exception:
                            _ai_out = None
                        if not _ai_out:   # 그라운딩 실패 → 일반 모델 폴백 (지어내기 방지 지침 포함)
                            _ai_out = "⚠️ 실시간 검색 연동에 실패해 시스템 실데이터 기준으로만 평가합니다.\n\n" + ask_gemini(
                                _prompt + "\n\n(검색이 불가하니 위 실데이터의 기술 신호만으로 보수적으로 평가하고, 뉴스성 내용은 '확인 불가'로 표기할 것)", api_key_input)
                    st.session_state.dd_ai_result = _ai_out
            if st.session_state.get("dd_ai_result"):
                with st.container(border=True):
                    st.markdown("#### 🤖 AI 회복 검증 리포트")
                    st.markdown(st.session_state.dd_ai_result)

elif selected_menu == "🧭 AI 통합 투자 발굴기 (테스트)":
    st.markdown("## 🧭 AI 통합 투자 발굴기  <span style='font-size:0.5em;color:#94a3b8;'>BETA</span>", unsafe_allow_html=True)
    st.caption("시장 분위기(신호등·VIX·공포탐욕) + 테마/정치 + 차트 + 펀더멘털 + 공매도/신용 + 뉴스 본문 AI 판정 + "
               "**실적·목표가 컨센서스 + 매크로→섹터 틸트 + 52주 신고가·시장 상대강도(RS)·MFI 자금흐름·유동성/변동성 필터**를 한 번에 융합하고, **관리종목·거래정지·투자경보는 자동 제외**한 뒤 "
               "**단기·중기·장기 투자 후보를 자동 분류**합니다.")

    # 세션 상태 초기화
    for _k, _v in [("finder_results", None), ("finder_mood", None),
                   ("finder_radar", None), ("finder_brief", None), ("finder_meta", None),
                   ("finder_excluded", None), ("finder_macro", None), ("finder_news_diag", None),
                   ("finder_new_codes", None), ("finder_prev_codes", None)]:
        if _k not in st.session_state:
            st.session_state[_k] = _v

    # ── 0) 오늘의 시장 분위기 한 줄 ──
    with st.spinner("시장 분위기 진단 중..."):
        mood = get_market_mood()
    _mc = {"🟢": "#16a34a", "🟡": "#f59e0b", "🔴": "#dc2626"}.get(mood["light"], "#888")
    _risk_txt = ("공격적(위험선호)" if mood["risk_on"] >= 0.3
                 else "방어적(위험회피)" if mood["risk_on"] <= -0.3 else "중립")
    mc1, mc2, mc3, mc4 = st.columns(4)
    mc1.metric(f"{mood['light']} 시장 국면", mood["title"], _risk_txt, delta_color="off")
    if isinstance(mood.get("kospi"), dict):
        mc2.metric(f"{mood['kospi']['light']} 코스피", f"{mood['kospi']['price']:,.1f}", f"{mood['kospi']['pct']:+.2f}%")
    if isinstance(mood.get("kosdaq"), dict):
        mc3.metric(f"{mood['kosdaq']['light']} 코스닥", f"{mood['kosdaq']['price']:,.1f}", f"{mood['kosdaq']['pct']:+.2f}%")
    _fng = mood.get("fng")
    mc4.metric("😨 공포탐욕 / VIX", f"{_fng if _fng is not None else '-'} · VIX {mood.get('vix') if mood.get('vix') is not None else '-'}",
               mood.get("fng_rating") or "-", delta_color="off")

    st.divider()

    # ── 1) 검색 조건 ──
    fc1, fc2 = st.columns([1, 1])
    with fc1:
        horizon_focus = st.radio(
            "⏱️ 투자 기간",
            ["🧠 전체 (자동 분류)", "🔥 단기 (스윙)", "⚖️ 중기 (추세·테마)", "💎 장기 (가치·우량)"],
            help="‘전체’를 고르면 모든 후보를 단기/중기/장기로 자동 분류해 한 번에 보여줍니다.",
        )
    with fc2:
        scope_label = st.radio("🌍 시장 범위", ["🇰🇷 국내만", "🇰🇷+🇺🇸 국내·미국", "🇺🇸 미국만"], horizontal=True)
    scope = ("kr" if scope_label.startswith("🇰🇷 국내만")
             else "us" if scope_label.startswith("🇺🇸 미국만")
             else "kr_us")

    fc3, fc4 = st.columns([2, 1])
    with fc3:
        theme_focus = st.text_input("🎯 관심 테마·키워드 (선택)", placeholder="예: AI 반도체 / 방산 / 원자력 / 로봇 / 바이오")
    with fc4:
        depth = st.selectbox("🔬 탐색 깊이", ["빠르게 (TOP 100)", "표준 (TOP 200)", "정밀 (TOP 300)"], index=2)
    # (국내 거래대금 상위 N, 미국 상위 N, 펀더멘털 보강 상한, 뉴스 수집 종목 수)
    depth_cfg = {
        "빠르게 (TOP 100)": (100, 25, 70, 12),
        "표준 (TOP 200)": (200, 40, 110, 20),
        "정밀 (TOP 300)": (300, 60, 150, 28),
    }[depth]
    kr_n, us_n, phaseb_cap, news_n = depth_cfg

    want_long = ("전체" in horizon_focus) or ("장기" in horizon_focus)

    st.caption("⏳ 기본값인 정밀(TOP 300)은 거래대금 상위 300종목의 차트·펀더멘털·공매도·뉴스 본문까지 한 번에 수집해 3~6분 걸릴 수 있어요. 결과·기사 본문은 캐시되어 재실행은 훨씬 빠릅니다.")

    if st.button("🧭 통합 검색 시작", type="primary", use_container_width=True):
        if not api_key_input:
            st.warning("⚠️ AI 테마 분석·후보 발굴을 위해 좌측 사이드바에 Gemini API 키가 필요합니다.")
        else:
            # 1) 뉴스 + 폴리마켓(정치/매크로) 수집
            with st.spinner("실시간 뉴스·예측시장(정치/매크로) 수집 중..."):
                try:
                    news_titles = [a["title"] for a in (get_latest_naver_news() or [])][:18]
                except Exception:
                    news_titles = []
                poly_lines = []
                try:
                    pm = fetch_polymarket_markets(
                        search="election president fed rate cut tariff war ceasefire recession", limit=20)
                    for m in (pm.get("data") or [])[:12]:
                        q = m.get("question", "")
                        yp = m.get("yes_prob")
                        ko = _gtx_translate_en_ko(q) if q else q
                        poly_lines.append(f"{ko} (확률 {yp:.0f}%)" if yp is not None else ko)
                except Exception:
                    poly_lines = []

            # 2) AI 테마/정치 레이더
            with st.spinner("AI가 오늘의 핵심 테마·정치 이벤트를 종합하는 중..."):
                radar = get_theme_politics_radar(api_key_input, tuple(news_titles), tuple(poly_lines))

            # 3) 후보 풀 구성
            with st.spinner("후보 종목 풀 구성 중 (시총 상위 + 테마 리더 + 가치주)..."):
                pool = build_finder_candidates(
                    api_key_input, scope, theme_focus, radar.get("themes"),
                    kr_n, us_n, want_long)
            if not pool:
                st.error("❌ 후보 종목을 구성하지 못했습니다. 잠시 후 다시 시도해 주세요.")
            else:
                # 3-1) 리스크 하드필터 — 관리종목·투자경보·거래정지 종목은 후보에서 제외
                excluded = []
                try:
                    excl_names, excl_reason = get_finder_exclusion_set()
                except Exception:
                    excl_names, excl_reason = set(), {}
                if excl_names:
                    for cd in list(pool.keys()):
                        nm = re.sub(r"\s+", "", str(pool[cd]["name"]))
                        if nm in excl_names:
                            excluded.append((pool[cd]["name"], excl_reason.get(nm, "관리/경보")))
                            pool.pop(cd, None)
                st.session_state["finder_excluded"] = excluded

                # 매크로 지표(섹터 틸트용) — 1회 수집
                macro_ind = get_macro_indicators() or {}
                st.session_state["finder_macro"] = macro_ind
                mood["_idx20"] = get_index_ret20()   # 시장 상대강도(RS) 기준선(코스피·S&P 20일 수익률)

                items = list(pool.items())  # [(code, info)]
                # 4) Phase A — 기술적 분석 (병렬)
                progressA = st.progress(0.0)
                statusA = st.empty()
                techs = {}
                doneA, totalA = 0, len(items)

                def _runA(it):
                    code, info = it
                    return code, _finder_tech(info["name"], code)

                with concurrent.futures.ThreadPoolExecutor(max_workers=8) as ex:
                    for fut in concurrent.futures.as_completed({ex.submit(_runA, it): it for it in items}):
                        code, res = fut.result()
                        doneA += 1
                        if res:
                            techs[code] = res
                        progressA.progress(min(1.0, doneA / totalA))
                        statusA.text(f"📈 1/2 차트·수급 분석 중... ({doneA}/{totalA})")
                progressA.empty(); statusA.empty()

                # 사전 점수(밸류 미반영) → Phase B(가치 보강) 우선순위 선정
                prelim = {}
                for code, tech in techs.items():
                    th = pool[code].get("theme") is not None
                    _sc, _, top, _, _, _ = score_one(tech, None, mood, theme_hit=th)
                    prelim[code] = top
                kr_codes = [c for c in techs if str(c).isdigit()]
                must = [c for c in kr_codes if {"theme", "value"} & pool[c]["src"]]   # 테마/가치 후보는 반드시 보강
                rest = sorted([c for c in kr_codes if c not in must],
                              key=lambda c: prelim.get(c, 0), reverse=True)
                phaseb = (must + rest)[:phaseb_cap]

                # 5) Phase B — 가치/펀더멘털 + 공매도·신용 + 컨센서스 리비전 보강 (국내, 병렬)
                vmap, rmap, cmap = {}, {}, {}
                if phaseb:
                    progressB = st.progress(0.0)
                    statusB = st.empty()
                    doneB, totalB = 0, len(phaseb)

                    def _runB(c):
                        return c, _finder_value(c), _finder_risk(c), get_consensus_signal(c)

                    with concurrent.futures.ThreadPoolExecutor(max_workers=6) as ex:
                        for fut in concurrent.futures.as_completed({ex.submit(_runB, c): c for c in phaseb}):
                            try:
                                c, vm, rk, cs = fut.result()
                                vmap[c] = vm
                                rmap[c] = rk
                                cmap[c] = cs
                            except Exception as _dg_e:
                                _diag_note("<module>", _dg_e)
                                pass
                            doneB += 1
                            progressB.progress(min(1.0, doneB / totalB))
                            statusB.text(f"💎 2/2 펀더멘털·공매도·신용·컨센서스 보강 중... ({doneB}/{totalB})")
                    progressB.empty(); statusB.empty()

                # 6) 1차 점수 + 자동 분류 (리스크·컨센서스·매크로틸트 반영, 뉴스 전)
                enriched = []
                by_code = {}
                for code, tech in techs.items():
                    th_name = pool[code].get("theme")
                    th = th_name is not None
                    tilt_pts, tilt_notes = macro_tilt_for(tech.get("섹터", ""), macro_ind)
                    cons = cmap.get(code)
                    scores, horizon, top, grade, reasons, risk_flags = score_one(
                        tech, vmap.get(code), mood, theme_hit=th, risk=rmap.get(code),
                        sector_tilt=tilt_pts, consensus=cons)
                    r = dict(tech)
                    r["_scores"] = scores
                    r["_horizon"] = horizon
                    r["_top"] = top
                    r["_grade"] = grade
                    r["_reasons"] = reasons
                    r["_theme"] = th_name
                    r["_risk"] = rmap.get(code)
                    r["_risk_flags"] = risk_flags
                    r["_tilt"] = tilt_pts
                    r["_tilt_notes"] = tilt_notes
                    r["_consensus"] = cons
                    r["_upside"] = (((_f_num(tech.get("목표가_컨센서스")) / _f_num(tech.get("현재가"))) - 1) * 100
                                    if (_f_num(tech.get("목표가_컨센서스")) and _f_num(tech.get("현재가")) and _f_num(tech.get("현재가")) > 0) else None)
                    enriched.append(r)
                    by_code[code] = r

                # 6-1) 표시 대상(기간별 상위 10, 재정렬 여유분 포함)에 최신 뉴스 자동 첨부
                def _rebucket(lst):
                    b = {"단기": [], "중기": [], "장기": []}
                    for x in lst:
                        b[x["_horizon"]].append(x)
                    for hz in b:
                        b[hz].sort(key=lambda x: x["_top"], reverse=True)
                    return b

                buckets_full = _rebucket(enriched)
                news_targets, excerpt_codes = [], set()
                for hz in ("단기", "중기", "장기"):
                    for i, r in enumerate(buckets_full[hz][:news_n]):
                        tk = r.get("티커")
                        news_targets.append(tk)
                        if i < 10:               # 본문 발췌는 상위 10개만(속도)
                            excerpt_codes.add(tk)
                news_targets = list(dict.fromkeys([t for t in news_targets if t]))
                if news_targets:
                    code2name = {r.get("티커"): r.get("종목명") for r in enriched}
                    newsmap = {}
                    progressN = st.progress(0.0)
                    statusN = st.empty()
                    doneN, totalN = 0, len(news_targets)
                    # [속도개선] 워커 확대(6→12) + 전체 시간 상한(deadline). 일부 종목의 뉴스 API가
                    #            먹통이어도 그 '느린 꼬리'가 수집 전체를 붙잡지 않도록, 22초 안에 못 받은
                    #            종목은 빈 뉴스로 처리하고 즉시 다음 단계로 넘어간다.
                    exN = concurrent.futures.ThreadPoolExecutor(max_workers=12)
                    fmap = {exN.submit(get_stock_news, c, code2name.get(c, ""), 4): c for c in news_targets}
                    try:
                        for fut in concurrent.futures.as_completed(fmap, timeout=22):
                            c = fmap[fut]
                            try:
                                newsmap[c] = fut.result()
                            except Exception:
                                newsmap[c] = []
                            doneN += 1
                            progressN.progress(min(1.0, doneN / totalN))
                            statusN.text(f"📰 종목별 최신 뉴스 수집 중... ({doneN}/{totalN})")
                    except concurrent.futures.TimeoutError:
                        statusN.text(f"📰 뉴스 수집 시간 초과 — 받은 {doneN}/{totalN}건으로 진행합니다.")
                    for c in news_targets:          # 시간 내 못 받은 종목은 빈 뉴스 처리
                        newsmap.setdefault(c, [])
                    exN.shutdown(wait=False)        # 남은 작업은 백그라운드에 두고 UI는 즉시 진행
                    progressN.empty(); statusN.empty()
                    for c in newsmap:
                        if c in by_code:
                            by_code[c]["_news"] = newsmap[c]

                    # 6-1b) 기사 본문 발췌 병렬 수집 → 판정 정확도 향상 (상위 종목만)
                    link_set = []
                    for c in news_targets:
                        if c not in excerpt_codes:
                            continue
                        for n in (newsmap.get(c) or []):
                            lk = n.get("link")
                            if lk:
                                link_set.append(lk)
                    link_set = list(dict.fromkeys(link_set))
                    excerpt_map = {}
                    if link_set:
                        progressE = st.progress(0.0)
                        statusE = st.empty()
                        doneE, totalE = 0, len(link_set)
                        # [속도개선] 본문 발췌도 워커 확대(8→14) + 전체 시간 상한(18초).
                        #            본문은 호재/악재 '판정 정확도 보강용'이라 일부 누락돼도 분석은 정상 진행된다.
                        exE = concurrent.futures.ThreadPoolExecutor(max_workers=14)
                        emap = {exE.submit(fetch_article_excerpt, lk): lk for lk in link_set}
                        try:
                            for fut in concurrent.futures.as_completed(emap, timeout=18):
                                lk = emap[fut]
                                try:
                                    excerpt_map[lk] = fut.result()
                                except Exception:
                                    excerpt_map[lk] = ""
                                doneE += 1
                                progressE.progress(min(1.0, doneE / totalE))
                                statusE.text(f"📄 기사 본문 분석 중... ({doneE}/{totalE})")
                        except concurrent.futures.TimeoutError:
                            statusE.text(f"📄 본문 분석 시간 초과 — 받은 {doneE}/{totalE}건으로 진행합니다.")
                        exE.shutdown(wait=False)
                        progressE.empty(); statusE.empty()
                        # 발췌를 뉴스 항목에 부착 (모바일 API가 준 발췌가 있으면 보존, 본문 추출 성공 시 갱신)
                        for c in newsmap:
                            for n in (newsmap.get(c) or []):
                                fetched = excerpt_map.get(n.get("link"))
                                if fetched:
                                    n["excerpt"] = fetched

                    # 6-2) AI 뉴스 호재/악재 판정 (제목 + 본문 발췌, 개별 기사 단위) → 점수 재반영
                    sent_items = []
                    for c in news_targets:
                        nz = newsmap.get(c) or []
                        arts = tuple(
                            ((n.get("title") or "").strip(), (excerpt_map.get(n.get("link")) or n.get("excerpt") or ""))
                            for n in nz if n.get("title")
                        )
                        if arts:
                            sent_items.append((c, code2name.get(c, ""), arts))
                    if sent_items:
                        with st.spinner("AI가 제목·본문을 함께 읽고 호재/악재를 판정하는 중..."):
                            sentmap = classify_news_sentiment(api_key_input, tuple(sent_items))
                        for c, info in (sentmap or {}).items():
                            r = by_code.get(c)
                            if not r:
                                continue
                            r["_news_label"] = info.get("label")
                            r["_news_score"] = info.get("score")
                            r["_news_reason"] = info.get("reason")
                            r["_news_conf"] = info.get("confidence")
                            r["_news_auto_neutral"] = info.get("auto_neutral", False)
                            # 개별 기사 라벨을 해당 뉴스 항목에 부착 (입력 순서 일치)
                            al = info.get("article_labels") or []
                            nz = r.get("_news") or []
                            titled = [n for n in nz if n.get("title")]
                            for k, art in enumerate(al):
                                if k < len(titled):
                                    titled[k]["label"] = art[0]
                                    titled[k]["score"] = art[1]
                            # 증자/CB 희석 리스크 — 최근 기사 제목/본문에서 감지
                            _dil = False
                            for n in (r.get("_news") or []):
                                blob = (str(n.get("title", "")) + " " + str(n.get("excerpt", "")))
                                if any(k in blob for k in ["유상증자", "전환사채", "신주인수권", "BW 발행", "CB 발행", "주주배정 증자", "제3자배정"]):
                                    _dil = True
                                    n["dilution"] = True
                            r["_dilution"] = _dil
                            # 뉴스 점수·매크로틸트·컨센서스·증자리스크 반영해 재채점 (자동중립이면 score 0)
                            th_name = pool[c].get("theme")
                            _tilt_pts, _ = macro_tilt_for(techs[c].get("섹터", ""), macro_ind)
                            scores, horizon, top, grade, reasons, risk_flags = score_one(
                                techs[c], vmap.get(c), mood, theme_hit=(th_name is not None),
                                risk=rmap.get(c), news_sent=info.get("score"),
                                sector_tilt=_tilt_pts, consensus=cmap.get(c), dilution=_dil)
                            r["_scores"] = scores
                            r["_horizon"] = horizon
                            r["_top"] = top
                            r["_grade"] = grade
                            r["_reasons"] = reasons

                st.session_state.finder_results = enriched
                # [신규 종목 추적] 직전 검색에 없던 티커 = 이번 검색의 신규 진입
                _cur_codes = {r.get("티커") for r in enriched if r.get("티커")}
                _prev_codes = st.session_state.get("finder_prev_codes")
                st.session_state["finder_new_codes"] = (_cur_codes - _prev_codes) if _prev_codes else set()
                st.session_state["finder_prev_codes"] = _cur_codes
                st.session_state.finder_mood = mood
                st.session_state.finder_radar = radar
                st.session_state.finder_meta = (scope, depth, theme_focus, len(enriched), news_n)
                # 뉴스 수집/판정 진단 (왜 비는지 확인용)
                _n_targets = len(news_targets)
                _n_with_news = sum(1 for r in enriched if r.get("_news"))
                _n_articles = sum(len(r.get("_news") or []) for r in enriched)
                _n_labeled = sum(1 for r in enriched if r.get("_news_label"))
                st.session_state["finder_news_diag"] = (_n_targets, _n_with_news, _n_articles, _n_labeled)

                # 7) AI 통합 브리핑
                buckets_tmp = {"단기": [], "중기": [], "장기": []}
                for r in enriched:
                    buckets_tmp[r["_horizon"]].append((r.get("종목명"), r["_top"]))
                for hz in buckets_tmp:
                    buckets_tmp[hz].sort(key=lambda x: x[1], reverse=True)
                with st.spinner("AI 통합 전략 브리핑 작성 중..."):
                    st.session_state.finder_brief = get_finder_briefing(
                        api_key_input, mood, radar, buckets_tmp)

                # 8) 📌 픽 히스토리 기록 (기간별 상위 5 — 성과 추적용, 실패해도 검색엔 영향 없음)
                try:
                    finder_history_append(enriched, scope_label, depth, theme_focus)
                except Exception as _dg_e:
                    _diag_note("<module>", _dg_e)
                    pass

    # ── 결과 렌더 ──
    radar = st.session_state.get("finder_radar")
    if radar and radar.get("themes"):
        st.markdown("### 🛰️ 오늘의 테마·정치 레이더")
        if radar.get("mood_comment"):
            st.info(f"🗣️ {radar['mood_comment']}")
        _hz_color = {"단기": "#dc2626", "중기": "#2563eb", "장기": "#16a34a"}
        rcols = st.columns(min(len(radar["themes"]), 5) or 1)
        for i, t in enumerate(radar["themes"][:5]):
            with rcols[i % len(rcols)]:
                c = _hz_color.get(t["horizon"], "#888")
                st.markdown(
                    f"<div style='border:1px solid #e5e7eb;border-left:4px solid {c};border-radius:10px;"
                    f"padding:10px 12px;margin-bottom:8px;background:#fff;'>"
                    f"<div style='font-weight:800;font-size:14px;color:#1e293b;'>{t['theme']}</div>"
                    f"<div style='display:inline-block;font-size:11px;font-weight:700;color:#fff;background:{c};"
                    f"border-radius:6px;padding:1px 7px;margin:4px 0;'>{t['horizon']}</div>"
                    f"<div style='font-size:12px;color:#475569;line-height:1.4;'>{t['reason']}</div></div>",
                    unsafe_allow_html=True)

    if st.session_state.get("finder_brief"):
        with st.expander("🧠 AI 통합 투자 전략 브리핑", expanded=True):
            st.markdown(st.session_state.finder_brief)
            st.caption("※ 본 내용은 투자 권유가 아닌 참고 정보이며, 최종 판단과 책임은 투자자 본인에게 있습니다.")

    results = st.session_state.get("finder_results")
    if results:
        buckets = {"단기": [], "중기": [], "장기": []}
        for r in results:
            buckets[r["_horizon"]].append(r)
        for hz in buckets:
            buckets[hz].sort(key=lambda x: x["_top"], reverse=True)

        meta = st.session_state.get("finder_meta")
        if meta:
            st.success(f"✅ 총 {meta[3]}개 종목 분석 완료 — 단기 {len(buckets['단기'])} · 중기 {len(buckets['중기'])} · 장기 {len(buckets['장기'])}개로 자동 분류")

        # 매크로 → 섹터 틸트 배너 (오늘 매크로가 어느 섹터에 유·불리한지)
        _mnotes = macro_regime_notes(st.session_state.get("finder_macro") or get_macro_indicators())
        if _mnotes:
            st.info("🧭 **오늘의 매크로 → 섹터 틸트** (점수에 반영): " + " ｜ ".join(_mnotes))

        # 하드필터로 제외된 위험 종목 안내
        _excl = st.session_state.get("finder_excluded") or []
        if _excl:
            def _prc_excluded():
                st.caption("아래 종목은 상장폐지·거래정지 등 고위험으로 분류돼 후보에서 제외됐습니다.")
                st.dataframe(pd.DataFrame([{"종목명": n, "사유": rs} for n, rs in _excl]),
                             use_container_width=True, hide_index=True)
            _register_popup("excluded", _prc_excluded)
            _popup_button(f"🛑 리스크 하드필터 제외 종목 {len(_excl)}개 보기", "excluded", f"🛑 제외된 종목 {len(_excl)}개", key="btn_excluded")

        # 뉴스 수집/판정 진단 (뉴스가 비는 원인 확인)
        _diag = st.session_state.get("finder_news_diag")
        if _diag:
            _t, _wn, _na, _lb = _diag
            if _na == 0:
                st.warning(f"📰 뉴스 진단: 대상 {_t}종목에서 **기사 0건 수집** — 뉴스 소스가 현재 환경에서 차단된 상태입니다. (테마/점수는 정상)")
            elif _lb == 0:
                st.warning(f"📰 뉴스 진단: 기사 {_na}건 수집됐으나 **AI 판정 0건** — Gemini API 키/호출을 확인하세요.")
            else:
                st.caption(f"📰 뉴스 진단: 대상 {_t}종목 · 기사 {_na}건 수집 · {_wn}종목에 부착 · AI 판정 {_lb}종목")

        # ── [발굴기 확장] 결과 내보내기 · 신규 종목 · 필터/정렬 ─────────────
        _all_buckets = {hz: list(buckets[hz]) for hz in buckets}   # 필터 전 전체(내보내기·신규 판정용)

        # (1) 결과 내보내기 (CSV·엑셀) — 화면 필터와 무관하게 분석된 전체 종목 저장
        _exp_df = _finder_export_df(_all_buckets)
        if not _exp_df.empty:
            _xlsx_bytes = None
            try:
                import io as _io
                _buf = _io.BytesIO()
                with pd.ExcelWriter(_buf, engine="openpyxl") as _xw:
                    for _hz in ("단기", "중기", "장기"):
                        _dfh = _exp_df[_exp_df["기간분류"] == _hz].drop(columns=["기간분류"])
                        (_dfh if not _dfh.empty else pd.DataFrame({"안내": ["해당 종목 없음"]})).to_excel(_xw, sheet_name=_hz, index=False)
                _xlsx_bytes = _buf.getvalue()
            except Exception:
                _xlsx_bytes = None
            _stamp = datetime.now().strftime("%Y%m%d_%H%M")
            _ec1, _ec2, _ec3 = st.columns([1, 1, 2.6], vertical_alignment="center")
            _ec1.download_button("💾 CSV 내보내기", _exp_df.to_csv(index=False).encode("utf-8-sig"),
                                 file_name=f"통합발굴_{_stamp}.csv", mime="text/csv",
                                 use_container_width=True, key="finder_csv")
            if _xlsx_bytes:
                _ec2.download_button("📊 엑셀(xlsx)", _xlsx_bytes, file_name=f"통합발굴_{_stamp}.xlsx",
                                     mime="application/vnd.openpyxlformats-officedocument.spreadsheetml.sheet",
                                     use_container_width=True, key="finder_xlsx")
            else:
                _ec2.caption("엑셀 엔진 미설치 → CSV 이용")
            _ec3.caption(f"📋 분석된 전체 {len(_exp_df)}종목 저장(엑셀은 단기·중기·장기 시트 분리). 아래 화면 필터와 무관하게 전량 내보냅니다.")

        # (2) 직전 검색 대비 신규 진입 종목
        _new_codes = st.session_state.get("finder_new_codes") or set()
        if _new_codes:
            _new_names = list(dict.fromkeys(
                r.get("종목명") for hz in _all_buckets for r in _all_buckets[hz] if r.get("티커") in _new_codes))
            if _new_names:
                _shown = ", ".join(_new_names[:12])
                _more = f" 외 {len(_new_names) - 12}개" if len(_new_names) > 12 else ""
                st.success(f"🆕 **직전 검색 대비 신규 진입 {len(_new_names)}종목** — {_shown}{_more}  "
                           "*(같은 조건으로 다시 돌릴수록 정확합니다)*")

        # (3) 결과 필터 · 정렬
        with st.container(border=True):
            _fc_a, _fc_b = st.columns([2, 3])
            with _fc_a:
                _sort_mode = st.selectbox("⬇️ 정렬 기준",
                                          ["적합도 점수", "기대수익(컨센)", "손익비(R:R)", "20일 모멘텀"], key="finder_sort")
            with _fc_b:
                _cb1, _cb2, _cb3 = st.columns(3)
                _hide_bad = _cb1.checkbox("🔴 악재 숨기기", key="finder_hide_bad")
                _hide_risk = _cb2.checkbox("🩸 고위험 숨기기", key="finder_hide_risk",
                                           help="공매도 과다·신용 과다·증자/CB·리스크 적색 종목 제외")
                _hide_illiq = _cb3.checkbox("💧 저유동성 숨기기", key="finder_hide_illiq")
            _min_score = st.slider("최소 적합도 점수", 0, 80, 0, 5, key="finder_min_score")
            # 💰 포지션 사이징 가이드 — 예산 입력 시 국내 종목 상세 카드에 '제안 투입금·수량' 표시
            _ps1, _ps2 = st.columns([2, 1])
            _budget_man = _ps1.number_input("💰 투자 예산 (만원 — 0이면 포지션 가이드 끄기)",
                                            0, 1_000_000, 0, 100, key="finder_budget")
            _risk_pct = _ps2.select_slider("1회 매매 허용 손실(%)", options=[0.5, 1.0, 1.5, 2.0, 3.0],
                                           value=1.0, key="finder_risk_pct",
                                           help="한 종목이 손절가에 닿았을 때 감수할 '예산 대비' 최대 손실. "
                                                "제안 투입금 = 예산 × 허용손실% ÷ 손절까지 하방% (변동성 큰 종목일수록 적게 투입)")

        # 필터·정렬 적용 → 이후 탭/카드는 이 결과를 사용
        _filtered = {}
        for _hz in buckets:
            _lst = [r for r in buckets[_hz]
                    if (r.get("_top", 0) or 0) >= _min_score and not _finder_hide(r, _hide_bad, _hide_risk, _hide_illiq)]
            _lst.sort(key=lambda r: _finder_sort_val(r, _sort_mode), reverse=True)
            _filtered[_hz] = _lst
        _removed = sum(len(buckets[h]) for h in buckets) - sum(len(_filtered[h]) for h in _filtered)
        if _removed > 0:
            st.caption(f"🔎 필터로 {_removed}종목 숨김 · 정렬 기준: {_sort_mode}")
        buckets = _filtered

        # 🧩 상위 픽 섹터 집중도 점검 (분산 경고 — 한 테마 쏠림이면 알림)
        _top_all = [r for _hzc in ("단기", "중기", "장기") for r in buckets[_hzc][:8]]
        _sec_cnt = {}
        for r in _top_all:
            _s = str(r.get("_theme") or r.get("섹터") or "").strip()
            if _s and _s != "-":
                _sec_cnt[_s] = _sec_cnt.get(_s, 0) + 1
        if _sec_cnt:
            _tot = sum(_sec_cnt.values())
            _mx_s, _mx_c = max(_sec_cnt.items(), key=lambda kv: kv[1])
            if _tot >= 6 and _mx_c / _tot >= 0.4:
                st.warning(f"🧩 **분산 점검**: 상위 픽 {_tot}개 중 {_mx_c}개({_mx_c / _tot * 100:.0f}%)가 "
                           f"'{_mx_s}'에 집중돼 있어요. 한 테마 쏠림은 조정 시 동반 하락 위험이 커서 분산을 권합니다.")

        # 기간 포커스에 따라 기본 탭 순서 조정
        order = ["단기", "중기", "장기"]
        if "단기" in horizon_focus: order = ["단기", "중기", "장기"]
        elif "중기" in horizon_focus: order = ["중기", "단기", "장기"]
        elif "장기" in horizon_focus: order = ["장기", "중기", "단기"]
        tab_labels = {"단기": "🔥 단기 (스윙)", "중기": "⚖️ 중기 (추세·테마)", "장기": "💎 장기 (가치·우량)"}
        # 뉴스가 붙는 상위 종목만 표시 (표 전체에 뉴스 판정이 일관되게 나오도록)
        _disp_n = meta[4] if (meta and len(meta) > 4) else 20
        tabs = st.tabs([f"{tab_labels[h]}  ·  {min(len(buckets[h]), _disp_n)}" for h in order])

        for tab, hz in zip(tabs, order):
            with tab:
                picks = buckets[hz][:_disp_n]
                if not picks:
                    st.info(f"현재 분위기에서 '{hz}' 적합 종목이 충분히 포착되지 않았습니다. 탐색 깊이를 높이거나 테마 키워드를 바꿔보세요.")
                    continue
                # 요약 표
                rows = []
                for rk, r in enumerate(picks, 1):
                    _rk = r.get("_risk") or {}
                    _lvl = _rk.get("level")
                    risk_cell = (_lvl[0] if isinstance(_lvl, (list, tuple)) and _lvl else "")
                    if r.get("_risk_flags"):
                        risk_cell = (risk_cell + " " + " ".join(r["_risk_flags"])).strip()
                    if not risk_cell:
                        risk_cell = ("🟢" if str(r.get("티커", "")).isdigit() else "—")
                    _nl = r.get("_news_label")
                    news_cell = {"호재": "🟢 호재", "악재": "🔴 악재", "중립": "⚪ 중립"}.get(_nl, "—")
                    if _nl and r.get("_news_auto_neutral"):
                        news_cell = "⚪ 중립(저신뢰)"
                    # 컨센서스 셀: 목표가 상/하향 + 기대수익(괴리율)
                    _cons = r.get("_consensus") or {}
                    _up = r.get("_upside")
                    _rev = _cons.get("revision_dir")
                    _cons_cell = {"상향": "🔼상향", "하향": "🔽하향", "중립": "≈중립"}.get(_rev, "")
                    if _up is not None:
                        _cons_cell = (_cons_cell + f" {_up:+.0f}%").strip()
                    if not _cons_cell:
                        _cons_cell = "—"
                    if r.get("_dilution"):
                        _cons_cell += " 🔻증자"
                    _theme_cell = (r.get("_theme") or r.get("섹터") or "-")
                    _theme_cell = str(_theme_cell)
                    if len(_theme_cell) > 14:
                        _theme_cell = _theme_cell[:14] + "…"
                    _rr = _finder_rr(r)
                    if _rr and _rr.get("rr") is not None:
                        _rr_cell = f"{_rr['rr']:.1f}배 (▲{_rr['up']:.0f}%/▼{_rr['dn']:.0f}%)"
                    elif _rr and _rr.get("tag"):
                        _rr_cell = _rr["tag"]
                    else:
                        _rr_cell = "—"
                    _nm_cell = ("🆕 " if r.get("티커") in _new_codes else "") + str(r.get("종목명") or "")
                    rows.append({
                        "순위": rk, "등급": r["_grade"], f"{hz}점수": r["_top"],
                        "종목명": _nm_cell, "시장": r.get("시장", ""),
                        "테마/섹터": _theme_cell,
                        "현재가": (f"${r['현재가']:,.2f}" if not str(r.get('티커','')).isdigit() else f"{int(r.get('현재가',0)):,}원"),
                        "RSI": (f"{r['RSI']:.0f}" if _f_num(r.get('RSI')) is not None else "-"),
                        "손익비(R:R)": _rr_cell,
                        "컨센서스": _cons_cell,
                        "공매도/신용": risk_cell,
                        "뉴스(AI)": news_cell,
                        "핵심근거": " · ".join(r.get("_reasons", [])) or "-",
                    })
                st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
                st.caption("⚖️ 손익비(R:R) = 현재가 진입 시 1차목표까지 상방(▲) ÷ 손절까지 하방(▼), 클수록 유리 · 🆕=직전 검색 대비 신규 진입 · "
                           "🔼/🔽 목표가 상·하향 · +%는 컨센서스 기대수익(괴리율) · 🔻증자=유상증자/CB · 🩸공매도/⚠️신용=하방 리스크 (모두 점수 반영). 컨센서스·공매도·신용은 국내만 제공.")
                st.markdown("##### 📈 상세 카드 (상위 8종목)")
                for idx, r in enumerate(picks[:8]):
                    _new_badge = "🆕 " if r.get("티커") in _new_codes else ""
                    st.markdown(
                        f"**{idx+1}. {_new_badge}{r.get('종목명')}** · {r['_grade']} · {hz} 적합도 **{r['_top']:.0f}점**  "
                        + (f"· 🏷️ {r['_theme']}" if r.get("_theme") else "")
                    )
                    _sc3 = r.get("_scores") or {}
                    _prof = (" ｜ 📐 " + " · ".join(f"{_k} {_v:.0f}" for _k, _v in _sc3.items())) if _sc3 else ""
                    if r.get("_reasons") or _prof:
                        st.caption(("근거: " + " · ".join(r["_reasons"]) if r.get("_reasons") else "기간별 점수") + _prof)
                    # 손익비(R:R) + 컨센서스 + 매크로 틸트 + 증자리스크 한 줄
                    _cparts = []
                    _rr = _finder_rr(r)
                    if _rr and _rr.get("rr") is not None:
                        _cparts.append(f"⚖️ 손익비 {_rr['rr']:.1f}배 (▲{_rr['up']:.0f}% / ▼{_rr['dn']:.0f}%)")
                    elif _rr and _rr.get("tag"):
                        _cparts.append(f"⚖️ {_rr['tag']}")
                    _cons = r.get("_consensus") or {}
                    _up = r.get("_upside")
                    if _up is not None:
                        _cparts.append(f"🎯 기대수익 {_up:+.0f}% (컨센 목표가)")
                    if _cons.get("revision_dir") in ("상향", "하향"):
                        _arrow = "🔼" if _cons["revision_dir"] == "상향" else "🔽"
                        _cparts.append(f"{_arrow} 목표가 {_cons['revision_dir']}(최근 {_cons.get('report_total', 0)}건)")
                    if r.get("_tilt_notes"):
                        _t = r.get("_tilt") or 0
                        _tmark = "🟢" if _t > 0 else ("🔴" if _t < 0 else "⚪")
                        _cparts.append(f"{_tmark} 매크로: " + ", ".join(r["_tilt_notes"]))
                    if r.get("_dilution"):
                        _cparts.append("🔻 증자/CB 희석 리스크")
                    if _cparts:
                        st.caption(" ｜ ".join(_cparts))
                    # 💰 포지션 사이징 제안 (예산 입력 시 · 원화 계산이라 국내 종목만)
                    if _budget_man > 0 and str(r.get("티커", "")).isdigit():
                        _rr_ps = _finder_rr(r)
                        _dn_ps = (_rr_ps or {}).get("dn")
                        _cur_ps = _f_num(r.get("현재가"))
                        if _dn_ps and _dn_ps > 0 and _cur_ps and _cur_ps > 0:
                            _budget_w = _budget_man * 10000.0
                            _pos_w = _budget_w * (_risk_pct / 100.0) / (_dn_ps / 100.0)
                            _capped = _pos_w > _budget_w
                            _pos_w = min(_pos_w, _budget_w)
                            _qty = int(_pos_w // _cur_ps)
                            if _qty >= 1:
                                _eff_risk = (_dn_ps if _capped else _risk_pct)
                                st.caption(f"💰 포지션 가이드: **약 {_pos_w / 10000:,.0f}만원 ({_qty:,}주)** — "
                                           f"손절(▼{_dn_ps:.1f}%) 시 예산의 {_eff_risk:.1f}% 손실로 제한"
                                           + (" · ⚠️ 손절폭이 좁아 예산 100% 상한 적용" if _capped else ""))
                    # 공매도/신용 리스크 한 줄
                    _rk = r.get("_risk") or {}
                    if _rk:
                        parts = []
                        _lvl = _rk.get("level")
                        if isinstance(_lvl, (list, tuple)) and len(_lvl) == 2:
                            parts.append(f"{_lvl[0]} {_lvl[1]}")
                        if _rk.get("short_bal_ratio") is not None:
                            parts.append(f"공매도잔고 {_rk['short_bal_ratio']:.2f}%{(' '+_rk['short_bal_trend']) if _rk.get('short_bal_trend') else ''}")
                        if _rk.get("short_vol_ratio") is not None:
                            parts.append(f"당일공매도 {_rk['short_vol_ratio']:.1f}%{(' '+_rk['short_vol_trend']) if _rk.get('short_vol_trend') else ''}")
                        if _rk.get("credit_ratio") is not None:
                            parts.append(f"신용잔고율 {_rk['credit_ratio']:.2f}%")
                        if parts:
                            st.caption("🩸 리스크: " + " ｜ ".join(parts))
                    # AI 뉴스 호재/악재 판정 (종목 단위 + 신뢰도)
                    if r.get("_news_label"):
                        _emo = {"호재": "🟢", "악재": "🔴", "중립": "⚪"}.get(r["_news_label"], "⚪")
                        _ns = r.get("_news_score")
                        _sgn = f" ({_ns:+d})" if isinstance(_ns, int) and _ns != 0 else ""
                        _cf = r.get("_news_conf")
                        _cf_txt = f" · 신뢰도 {_cf:.2f}" if isinstance(_cf, (int, float)) else ""
                        _auto = " · 🔸자동 중립(저신뢰)" if r.get("_news_auto_neutral") else ""
                        _rsn = f" — {r['_news_reason']}" if r.get("_news_reason") else ""
                        st.caption(f"📰 AI 뉴스 판정: {_emo} **{r['_news_label']}**{_sgn}{_cf_txt}{_auto}{_rsn}")
                    # 공매도 추세 미니차트
                    _fig = _short_trend_figure(r.get("_risk"))
                    if _fig is not None:
                        st.plotly_chart(_fig, use_container_width=True)
                    draw_stock_card(r, api_key_str=api_key_input, is_expanded=False, key_suffix=f"finder_{hz}_{idx}")
                    # 종목별 최신 뉴스 (기사별 호재/악재 라벨 포함)
                    _news = r.get("_news")
                    if _news:
                        def _prc_news(_news=_news):
                            for nws in _news:
                                meta = " · ".join([x for x in [nws.get("source"), nws.get("date")] if x])
                                title = nws.get("title", "")
                                link = nws.get("link", "")
                                _alabel = nws.get("label")
                                _atag = {"호재": "🟢호재", "악재": "🔴악재", "중립": "⚪중립"}.get(_alabel, "")
                                _badge = f"`{_atag}` " if _atag else ""
                                _exc = (nws.get("excerpt") or "").strip()
                                _exc_html = ""
                                if _exc:
                                    _snip = _exc[:120] + ("…" if len(_exc) > 120 else "")
                                    _exc_html = f"  \n  <span style='color:#64748b;font-size:12px;'>📄 {_snip}</span>"
                                _meta_html = f"  \n  <span style='color:#94a3b8;font-size:12px;'>{meta}</span>" if meta else ""
                                if link:
                                    st.markdown(f"- {_badge}[{title}]({link})" + _meta_html + _exc_html, unsafe_allow_html=True)
                                else:
                                    st.markdown(f"- {_badge}{title}" + _meta_html + _exc_html, unsafe_allow_html=True)
                        _register_popup(f"news_{hz}_{idx}", _prc_news)
                        _popup_button(f"📰 {r.get('종목명')} 최신 뉴스 {len(_news)}건 보기", f"news_{hz}_{idx}", f"📰 {r.get('종목명')} 최신 뉴스", key=f"btn_news_{hz}_{idx}")
                    elif "_news" in r:
                        st.caption("📰 최근 뉴스를 찾지 못했습니다.")
                    st.markdown("")
    else:
        st.info("위에서 조건을 고르고 **‘통합 검색 시작’**을 누르면, 시장 분위기·테마·차트·펀더멘털을 종합해 기간별 투자 후보를 찾아드립니다.")

    # ── 📌 과거 픽 성과 추적 (발굴기 적중률 검증 — 검색 결과와 무관하게 항상 표시) ──
    _hist_runs = _finder_history_load()
    if _hist_runs:
        with st.expander(f"📌 과거 픽 성과 추적 — 저장된 검색 {len(_hist_runs)}회 (최근 30회 보관)", expanded=False):
            st.caption("검색할 때마다 기간별 상위 5픽이 자동 저장됩니다. 과거 실행을 골라 **'그때 픽이 지금 얼마인지'** 검증해 보세요. "
                       "발굴기의 실제 적중률을 확인하는 게 목적이에요.")
            app_state.render_backup_ui("finder_history", "발굴기 히스토리")   # [v7.2] 내보내기/불러오기
            _labels = []
            _runs_desc = list(reversed(_hist_runs))
            for _run in _runs_desc:
                _th = f" · 🎯{_run['theme']}" if _run.get("theme") else ""
                _labels.append(f"{_run['ts']} · {_run.get('scope', '')}{_th} · 픽 {len(_run.get('picks') or [])}개")
            _sel = st.selectbox("검증할 과거 검색", _labels, key="finder_hist_sel")
            _run_pick = _runs_desc[_labels.index(_sel)]
            _hc1, _hc2 = st.columns([2, 1])
            if _hc1.button("📈 이 검색의 픽 성과 계산", type="primary", use_container_width=True, key="finder_hist_calc"):
                with st.spinner("픽 당시 가격 대비 최근 종가 수익률 계산 중..."):
                    st.session_state["finder_hist_perf"] = (_run_pick["ts"], finder_history_perf(_run_pick))
            if _hc2.button("🗑️ 히스토리 전체 삭제", use_container_width=True, key="finder_hist_clear"):
                app_state.save("finder_history", [])       # 세션·파일 양쪽 비움
                try:
                    if os.path.exists(FINDER_HISTORY_FILE):
                        os.remove(FINDER_HISTORY_FILE)
                except Exception as _dg_e:
                    _diag_note("finder_history_clear", _dg_e)
                st.session_state.pop("finder_hist_perf", None)
                st.rerun()
            _perf = st.session_state.get("finder_hist_perf")
            if _perf and _perf[0] == _run_pick.get("ts"):
                _pdf = pd.DataFrame(_perf[1])
                if not _pdf.empty:
                    _rets = pd.to_numeric(_pdf["수익률(%)"], errors="coerce").dropna()
                    _sm1, _sm2, _sm3 = st.columns(3)
                    _sm1.metric("평균 수익률", f"{_rets.mean():+.2f}%" if len(_rets) else "-")
                    _sm2.metric("승률 (상승 픽)", f"{(_rets > 0).mean() * 100:.0f}%" if len(_rets) else "-",
                                f"{int((_rets > 0).sum())}/{len(_rets)} 종목", delta_color="off")
                    _sm3.metric("최고 / 최저", f"{_rets.max():+.1f}% / {_rets.min():+.1f}%" if len(_rets) else "-")

                    def _ret_css(v):
                        try:
                            v = float(v)
                        except (TypeError, ValueError) as _dg_e:
                            _diag_note("_ret_css", _dg_e)
                            return ""
                        if v > 0:
                            return "color:#e03131;font-weight:600"
                        if v < 0:
                            return "color:#1971c2;font-weight:600"
                        return ""
                    _psty = _pdf.style
                    _psty = (_psty.map if hasattr(_psty, "map") else _psty.applymap)(_ret_css, subset=["수익률(%)"])
                    st.dataframe(_psty, use_container_width=True, hide_index=True)
                    st.caption("※ 수익률 = 픽 저장 당시 현재가 → 최근 종가 (배당·수수료 미반영, 시세 1시간 캐시). "
                               "특정 날짜 픽의 성과가 좋았다면 그날과 비슷한 시장 국면에서 발굴기 신뢰도가 높다는 뜻이에요.")


elif selected_menu == "🏛️ 국민연금 5% 대량보유 픽":
    st.markdown("## 🏛️ 국민연금 5% 대량보유 픽")
    st.write("국민연금이 대량 보유한 국내/해외 핵심 기업 포트폴리오를 실시간 스크래핑하여 추적합니다.")

    # 🔑 [NEW] DART 오픈API 키 (선택) — FnGuide/WiseReport가 모두 차단될 때 공식 DART 공시로 조회
    with st.expander("🔑 DART 오픈API 키 설정 (선택 — 차단 우회용 공식 소스)"):
        st.caption("무료 발급: [opendart.fss.or.kr](https://opendart.fss.or.kr) → 인증키 신청 (일 20,000건 한도). "
                   "키를 입력하면 금융감독원 공식 '대량보유 상황보고' API를 최우선 소스로 사용합니다. "
                   "키는 이 세션에만 유지되며 파일로 저장되지 않습니다.")
        st.text_input("DART API 인증키 (40자)", type="password", key="dart_api_key",
                      placeholder="발급받은 인증키를 붙여넣으세요")
    _dart_key = (st.session_state.get("dart_api_key") or "").strip()

    # 🔍 [NEW] 실시간 종목 검색 — 고정 리스트에 없는 종목도 국민연금 지분율을 즉시 조회
    st.markdown("#### 🔍 종목 실시간 검색")
    st.caption("종목명 또는 6자리 코드를 입력하면 해당 종목의 국민연금 지분율을 실시간 조회합니다. "
               "아래 고정 리스트에 없는 코스피/코스닥 종목도 검색 가능합니다. "
               "(소스 체인: DART 공시(키 보유 시) → FnGuide → WiseReport 순으로 자동 우회)")
    nps_sc1, nps_sc2 = st.columns([7, 3])
    nps_q = nps_sc1.text_input("종목명 또는 6자리 코드", placeholder="예: 삼성전자 / 005930 / 에코프로",
                               key="nps_search_q", label_visibility="collapsed")
    _nps_target = None  # (종목명, 코드)
    if nps_q and nps_q.strip():
        _qs = nps_q.strip()
        _listing = get_krx_name_code_list()
        if re.fullmatch(r"\d{6}", _qs):
            _nm = _qs
            if not _listing.empty:
                _hit = _listing[_listing['Code'] == _qs]
                if not _hit.empty:
                    _nm = _hit['Name'].iloc[0]
            _nps_target = (_nm, _qs)
        elif _listing.empty:
            st.warning("⚠️ 종목 목록을 불러오지 못했습니다 (FDR 응답 없음). 6자리 종목코드로 검색해 주세요.")
        else:
            _exact = _listing[_listing['Name'].str.lower() == _qs.lower()]
            _cand = _exact if not _exact.empty else _listing[_listing['Name'].str.contains(re.escape(_qs), case=False, na=False)]
            if _cand.empty:
                st.warning(f"'{_qs}' 검색 결과가 없습니다. 종목명 철자 또는 6자리 코드를 확인해 주세요.")
            elif len(_cand) == 1:
                _nps_target = (_cand['Name'].iloc[0], _cand['Code'].iloc[0])
            else:
                _cand = _cand.head(20)
                _pick = st.selectbox(f"검색 결과 {len(_cand)}건 — 종목을 선택하세요 (최대 20건 표시)",
                                     [f"{r.Name} ({r.Code})" for r in _cand.itertuples()], key="nps_search_pick")
                _pm = re.search(r"\((\d{6})\)$", _pick)
                if _pm:
                    _nps_target = (_pick[:_pick.rfind("(")].strip(), _pm.group(1))
    if nps_sc2.button("📡 지분율 조회", type="primary", use_container_width=True,
                      key="nps_search_btn", disabled=_nps_target is None) and _nps_target:
        with st.spinner(f"{_nps_target[0]} 국민연금 지분율 실시간 조회 중... (DART→FnGuide→WiseReport)"):
            _sr = search_nps_holding(_nps_target[1], _nps_target[0], _dart_key)
        st.session_state.nps_search_result = {"r": _sr, "name": _nps_target[0], "code": _nps_target[1],
                                              "t": datetime.now().strftime("%Y-%m-%d %H:%M")}
    _saved = st.session_state.get("nps_search_result")
    if _saved:
        _sr, _snm, _scd = _saved["r"], _saved["name"], _saved["code"]
        if _sr is None:
            st.error(f"❌ {_snm}({_scd}) 조회 실패 — FnGuide·WiseReport 모두 응답 없음/차단. "
                     "위 '🔑 DART 오픈API 키'를 설정하면 공식 공시 API로 우회 조회할 수 있습니다.")
        elif _sr["지분율"] is None:
            _src_txt = f" (확인 소스: {_sr['출처']})" if _sr.get("출처") else ""
            st.info(f"ℹ️ **{_snm}({_scd})** — 주요주주/대량보유 내역에서 국민연금이 확인되지 않습니다{_src_txt}. "
                    "지분이 없거나 5% 미만(공시 의무 미발생)일 가능성이 큽니다.")
        else:
            _pct = _sr["지분율"]
            st.markdown(f"##### 📌 {_snm} ({_scd})")
            _rm1, _rm2, _rm3 = st.columns(3)
            _rm1.metric("국민연금 지분율", f"{_pct:.2f}%", help=f"표기: {_sr['주주표기']}")
            _rm2.metric("5% 대량보유 공시 대상", "✅ 해당 (5%↑)" if _pct >= 5.0 else "➖ 미해당 (5% 미만)")
            _src_lbl = _sr.get("출처") or "-"
            if _sr.get("기준일"):
                _src_lbl += f" · 보고일 {_sr['기준일']}"
            _rm3.metric("데이터 출처", _src_lbl, help=f"조회 시각: {_saved['t']}")
            st.caption(f"🔗 원본 확인: [FnGuide 지분현황](https://comp.fnguide.com/SVO2/ASP/SVD_Invest.asp?pGB=1&gicode=A{_scd}) · "
                       f"[WiseReport 지분현황](https://comp.wisereport.co.kr/company/c1070001.aspx?cmp_cd={_scd}) · "
                       "[DART 전자공시](https://dart.fss.or.kr)에서 '국민연금공단' 검색 시 대량보유 보고서 원문 확인 가능")
    st.divider()

    col_btn1, col_btn2 = st.columns([2, 8])
    if col_btn1.button("🔄 실시간 스크래핑 시도", type="primary", use_container_width=True):
        get_nps_holdings.clear()
        get_nps_us_portfolio.clear()
        search_nps_holding.clear()
        get_dart_corp_map.clear()
        st.session_state.pop("nps_search_result", None)
        st.rerun()
        
    with st.spinner("국민연금 보유현황을 실시간으로 파싱 중입니다. (서버 차단 시 표시되지 않을 수 있습니다)"):
        nps_kr_df = get_nps_holdings(_dart_key)
        nps_us_df = get_nps_us_portfolio()
    
    tab_nps1, tab_nps2, tab_nps3 = st.tabs(["🇰🇷 한국 주식 5% 이상 보유 현황", "🇺🇸 미국 주식 핵심 포트폴리오 (13F)", "🌟 황금 콤보 스캐너 (장기 가치 + 단기 수급)"])
    
    with tab_nps1:
        st.write("*(주요 기업의 국민연금 지분율을 DART 공시(키 보유 시)·FnGuide·WiseReport 체인으로 추출한 데이터입니다. '비고'에서 종목별 실제 소스를 확인할 수 있습니다.)*")
        if nps_kr_df is None or nps_kr_df.empty:
            st.warning("⚠️ 국민연금 국내 지분 데이터를 실시간으로 불러오지 못했습니다 (FnGuide·WiseReport 모두 응답 없음/차단). "
                       "상단 '🔑 DART 오픈API 키'를 설정하면 공식 공시 API로 우회 조회할 수 있습니다. "
                       "부정확한 캐시를 보여주지 않기 위해 표시를 생략합니다 — 잠시 후 새로고침해 주세요.")
        else:
            _f_kr = st.text_input("🔎 표 내 검색 (종목명/티커)", key="nps_kr_tbl_filter",
                                  placeholder="예: 삼성 / 005930 — 입력 즉시 필터링")
            _vdf_kr = nps_kr_df
            if _f_kr and _f_kr.strip():
                _mask_kr = nps_kr_df.astype(str).apply(
                    lambda c: c.str.contains(re.escape(_f_kr.strip()), case=False, na=False)).any(axis=1)
                _vdf_kr = nps_kr_df[_mask_kr]
                st.caption(f"검색 결과: {len(_vdf_kr)}건 / 전체 {len(nps_kr_df)}건")
            st.dataframe(_vdf_kr, use_container_width=True, hide_index=True)
         
    with tab_nps2:
        st.write("*(WhaleWisdom 등 미국 SEC 13F 공시 트래커를 기반으로 파싱된 국민연금 미국 주식 포트폴리오입니다.)*")
        if nps_us_df is None or nps_us_df.empty:
            st.warning("⚠️ 국민연금 미국 13F 데이터를 실시간으로 불러오지 못했습니다 (Dataroma 응답 없음/차단). "
                       "부정확한 캐시를 보여주지 않기 위해 표시를 생략합니다 — 잠시 후 새로고침해 주세요.")
        else:
            _f_us = st.text_input("🔎 표 내 검색 (종목명/티커)", key="nps_us_tbl_filter",
                                  placeholder="예: NVDA / Apple — 입력 즉시 필터링")
            _vdf_us = nps_us_df
            if _f_us and _f_us.strip():
                _mask_us = nps_us_df.astype(str).apply(
                    lambda c: c.str.contains(re.escape(_f_us.strip()), case=False, na=False)).any(axis=1)
                _vdf_us = nps_us_df[_mask_us]
                st.caption(f"검색 결과: {len(_vdf_us)}건 / 전체 {len(nps_us_df)}건")
            st.dataframe(_vdf_us, use_container_width=True, hide_index=True)
        
    with tab_nps3:
        st.markdown("### 🌟 황금 콤보 전략")
        st.write("**`[조건]`** 기관이 5% 이상 보유하여 **기본적인 펀더멘털이 검증된 종목** 중, 최근 시장에서 **기관이 다시 3일 이상 순매수를 시작**하며 단기 모멘텀이 붙기 시작한 종목을 스캔합니다.")
        
        if st.button("🚀 황금 콤보 교차 스캔 시작", type="primary"):
            with st.spinner("수급 패턴 교차 분석 중..."):
                combo_results = []
                progress_bar2 = st.progress(0)
                completed2, total2 = 0, len(nps_kr_df)
                
                for idx, row in nps_kr_df.iterrows():
                    res = analyze_technical_pattern(row['종목명'], row['티커'])
                    if res and res.get('연기금연속순매수', 0) >= 2: 
                        res['NPS_비중'] = row['보유비중']
                        combo_results.append(res)
                    completed2 += 1
                    progress_bar2.progress(completed2 / total2)
                    
                if combo_results:
                    st.success(f"🎯 펀더멘털과 수급이 완벽하게 일치하는 황금 콤보 {len(combo_results)}개 종목 포착!")
                    for i, res in enumerate(combo_results):
                        st.markdown(f"#### 🏆 기관 보유 비중: {res['NPS_비중']}")
                        draw_stock_card(res, api_key_str=api_key_input, is_expanded=True, key_suffix=f"combo_{i}")
                else:
                    st.warning("현재 황금 콤보 조건에 부합하는 종목이 없습니다.")

elif selected_menu == "💎 장기 우량주 & 가치주 발굴":
    st.markdown("## 💎 장기 우량주 & 가치주 발굴")
    st.caption("위험 성향(안전·중립·공격)을 고르고 세부 전략을 선택하면 → AI 후보 발굴 → 멀티팩터 검증(PER·PBR·배당·ROE·부채·성장·모멘텀) → 차트 타점까지 한 번에.")

    tier = st.radio("🎚️ 위험 성향", list(VALUE_STRATEGIES.keys()), horizontal=True)
    tier_list = VALUE_STRATEGIES[tier]
    col_v1, col_v2 = st.columns([2, 1])
    with col_v1:
        pick = st.selectbox("🧠 세부 전략", [s["name"] for s in tier_list])
    with col_v2:
        cap_size = st.selectbox("🏢 기업 규모", ["대/중/소형 상관없음", "코스피 대형우량주만", "코스닥 중소형 숨은진주"], index=0)
    strat = next(s for s in tier_list if s["name"] == pick)

    # 🎛️ 임계값 직접 조정(고급) — 선택한 전략의 하드필터 기준을 슬라이더로 덮어쓰기
    with st.expander("🎛️ 임계값 직접 조정 (고급)"):
        _use_custom = st.checkbox("이 전략의 기준을 직접 조정", value=False,
                                  help="선택한 전략의 임계값을 슬라이더로 덮어씁니다. 끄면 전략 기본값 사용. (해당 전략이 쓰는 항목만 노출)")
        _ov = {}
        if _use_custom:
            _oc1, _oc2, _oc3, _oc4 = st.columns(4)
            if strat["per"] is not None:
                with _oc1: _ov["per"] = st.slider("PER 상한 ≤", 3, 100, int(strat["per"]))
            if strat["pbr"] is not None:
                with _oc2: _ov["pbr"] = st.slider("PBR 상한 ≤", 0.3, 10.0, float(strat["pbr"]), 0.1)
            if strat["div"] is not None:
                with _oc3: _ov["div"] = st.slider("배당 하한 ≥ (%)", 0.0, 10.0, float(strat["div"]), 0.5)
            if strat["roe"] is not None:
                with _oc4: _ov["roe"] = st.slider("ROE 하한 ≥ (%)", 0, 40, int(strat["roe"]))
            if not _ov:
                st.caption("이 전략은 조정 가능한 수치 기준(PER·PBR·배당·ROE)이 없습니다.")
    eff_strat = dict(strat); eff_strat.update(_ov)   # 유효 전략 = 전략 기본값 + 오버라이드

    cond = []
    if eff_strat["per"] is not None: cond.append(f"PER ≤ {eff_strat['per']}")
    if eff_strat["pbr"] is not None: cond.append(f"PBR ≤ {eff_strat['pbr']}")
    if eff_strat["div"] is not None: cond.append(f"배당 ≥ {eff_strat['div']}%")
    if eff_strat["roe"] is not None: cond.append(f"ROE ≥ {eff_strat['roe']}%")
    if eff_strat["debt"] is not None: cond.append(f"부채비율 ≤ {eff_strat['debt']}")
    if eff_strat["growth"] is not None: cond.append(f"이익성장 ≥ {eff_strat['growth']}%")
    if eff_strat["mom"] == "strong": cond.append("강세 모멘텀(3·6M 상승)")
    if eff_strat["mom"] == "weak": cond.append("낙폭과대(고점 -25%↓)")
    _custom_tag = " · 🎛️ 커스텀 임계값 적용" if _ov else ""
    st.info(f"**{strat['name']}** — {strat['desc']}{_custom_tag}\n\n**적용 필터:** " + " ｜ ".join(cond) + "\n\n※ PER·PBR·모멘텀은 하드 필터, ROE·배당·부채·성장은 데이터가 있을 때만 적용(소프트)됩니다.")

    if st.button("💎 멀티팩터 병렬 스캔 시작", type="primary", use_container_width=True):
        if not api_key_input:
            st.warning("API 키를 입력해주세요.")
        else:
            with st.spinner("AI가 전략 부합 후보를 발굴 중..."):
                candidates = get_longterm_value_stocks_with_ai(strat["name"] + " — " + strat["hint"], cap_size, api_key_input)
            if not candidates:
                st.error("❌ 관련 기업을 찾지 못했습니다.")
            else:
                progress = st.progress(0.0)
                total, completed, passed = len(candidates), 0, []

                def _work(t):
                    name, c = t
                    m = get_value_metrics(c)
                    if not value_passes(m, eff_strat):
                        return None
                    res = analyze_technical_pattern(name, c)
                    return {"name": name, "code": c, "m": m, "res": res}

                with concurrent.futures.ThreadPoolExecutor(max_workers=5) as ex:
                    for fut in concurrent.futures.as_completed({ex.submit(_work, c): c for c in candidates}):
                        r = fut.result()
                        completed += 1
                        progress.progress(min(1.0, completed / total))
                        if r:
                            passed.append(r)

                if passed:
                    passed = _value_rank(passed)   # 🏆 가치 점수 계산 + 내림차순 정렬(베스트 밸류 순)
                    def _fmt(v, suf="", plus=False):
                        if v is None: return "-"
                        return (f"{v:+.1f}{suf}" if plus else f"{v:.1f}{suf}")
                    summary = pd.DataFrame([{
                        "순위": p["_vrank"], "가치점수": p["_vscore"],
                        "종목명": p["name"], "코드": p["code"],
                        "PER": _fmt(p["m"]["per"]), "이익수익%": _fmt(p["_factors"]["ey"], plus=False),
                        "PBR": (f"{p['m']['pbr']:.2f}" if p["m"]["pbr"] else "-"),
                        "PEG": (f"{p['_factors']['peg']:.2f}" if p["_factors"]["peg"] is not None else "-"),
                        "배당%": _fmt(p["m"]["div"]), "ROE%": (f"{p['m']['roe']:.0f}" if p["m"]["roe"] is not None else "-"),
                        "부채비율": (f"{p['m']['debt']:.0f}" if p["m"]["debt"] is not None else "-"),
                        "성장%": _fmt(p["m"]["growth"], plus=True),
                        "3M%": _fmt(p["m"]["mom3"], plus=True), "6M%": _fmt(p["m"]["mom6"], plus=True),
                        "고점대비%": _fmt(p["m"]["off_high"], plus=True),
                        "검증팩터": f"{p['_factors']['cov_n']}/{p['_factors']['cov_total']}",
                    } for p in passed])
                    st.session_state.value_scan_summary = summary
                    st.session_state.value_scan_top = passed[0]   # 베스트 밸류(1위) 콜아웃용
                    st.session_state.value_scan_results = [p["res"] for p in passed if p["res"]]
                else:
                    st.session_state.value_scan_summary = None
                    st.session_state.value_scan_top = None
                    st.session_state.value_scan_results = []
                st.session_state.value_scan_meta = (strat["name"], total, len(passed))

    meta = st.session_state.get("value_scan_meta")
    if meta:
        if meta[2] > 0:
            st.success(f"✅ {meta[1]}개 후보 중 **{meta[2]}개** 종목이 '{meta[0]}' 조건을 통과했습니다.")
        else:
            st.warning(f"'{meta[0]}' 조건을 통과한 종목이 없습니다. 위험 성향을 바꾸거나 다른 전략을 시도해보세요.")
    if st.session_state.get("value_scan_summary") is not None:
        _vtop = st.session_state.get("value_scan_top")
        if _vtop:
            _tm = _vtop["m"]; _tf = _vtop["_factors"]
            def _cv(v, suf="", d=1):
                return "—" if v is None else f"{v:.{d}f}{suf}"
            st.markdown(
                "<div style='border:1px solid #34d399;background:linear-gradient(135deg,#ecfdf5,#d1fae5);"
                "border-radius:14px;padding:14px 16px;margin:4px 0 10px;'>"
                f"<div style='font-size:12px;font-weight:800;color:#047857;'>💎 베스트 밸류 (가치 점수 {_vtop['_vscore']:.1f})</div>"
                f"<div style='font-size:21px;font-weight:800;color:#0f172a;margin:2px 0 6px;'>{_vtop['name']} "
                f"<span style='font-size:13px;color:#94a3b8;font-weight:600;'>{_vtop['code']}</span></div>"
                "<div style='font-size:13px;color:#334155;line-height:1.7;'>"
                f"PER <b>{_cv(_tm['per'])}</b> &nbsp;·&nbsp; PBR <b>{_cv(_tm['pbr'],'',2)}</b> &nbsp;·&nbsp; "
                f"PEG <b>{_cv(_tf['peg'],'',2)}</b> &nbsp;·&nbsp; ROE <b>{_cv(_tm['roe'],'%',0)}</b> &nbsp;·&nbsp; "
                f"배당 <b>{_cv(_tm['div'],'%')}</b> &nbsp;·&nbsp; 검증 <b>{_tf['cov_n']}/{_tf['cov_total']}</b></div>"
                "</div>", unsafe_allow_html=True)
        st.markdown("#### 📋 조건 통과 종목 요약 (가치 점수 순)")
        _vsum = st.session_state.value_scan_summary
        st.dataframe(_vsum, use_container_width=True, hide_index=True)
        st.caption("💡 **가치 점수** = 저평가(PER·PBR·PEG) 45% + 퀄리티(ROE) 20% + 인컴(배당) 15% + 안전(부채) 12% + 모멘텀(6M) 8%, "
                   "통과 종목 내 상대평가. **PEG**=PER÷이익성장(1 미만이면 성장 대비 저평가), **이익수익%**=1/PER, "
                   "**검증팩터**=실제 데이터가 확인된 팩터 수(값 없는 팩터는 소프트 통과). ROE·배당·부채·성장은 국내 데이터 특성상 일부 결측될 수 있습니다.")
        _vstamp = datetime.now().strftime("%Y%m%d_%H%M")
        st.download_button("💾 스크리닝 결과 CSV 저장", _vsum.to_csv(index=False).encode("utf-8-sig"),
                           file_name=f"가치스크리닝_{_vstamp}.csv", mime="text/csv", key="value_csv")
    if st.session_state.value_scan_results:
        st.markdown("#### 📈 통과 종목 차트·타점 정밀 분석")
        display_sorted_results(st.session_state.value_scan_results, tab_key="t3", api_key=api_key_input)

elif selected_menu == "⚡ 메가트렌드 & 테마 대장주":
        st.markdown("## ⚡ 메가트렌드 & 테마 대장주")
        st.write("AI가 최신 트렌드를 분석하여, 숨겨진 글로벌 텐배거(10배 상승) 후보와 한·미 양국의 핵심 수혜주를 동시에 발굴합니다.")

        # [버그수정] 이 페이지로 '새로 진입'했는데 결과 없는 '미완료 검색어'가 남아 있으면 정리한다.
        #  이전에 검색하다 만 deep_tech_query 가 재진입 시 자동 재실행되어 '종목을 찾지 못했습니다' 오류가
        #  잠깐 떴다 사라지던 현상을 방지. (이미 완료된 결과 deep_tech_results 는 그대로 보존)
        if _nav_changed and st.session_state.get("deep_tech_results") is None:
            st.session_state.deep_tech_query = None
            st.session_state.deep_tech_brief = None

        # ... (이하 해당 블록 내용 전체)
        
        if not api_key_input:
            st.warning("⚠️ 사이드바에 Gemini API 키를 입력하시면 글로벌 AI 스캐너가 활성화됩니다.")
        else:
            st.markdown("### 🔥 현재 글로벌 시장 주도 테마 (AI 자동 추출)")
            with st.spinner("한국(KRX) 및 미국(US) 주요 증시의 거래 데이터를 분석하여 핵심 테마를 추출 중입니다..."):
                hot_themes_tab5 = get_trending_themes_with_ai(api_key_input)
                
            cols_d = st.columns(4) 
            for idx, theme in enumerate(hot_themes_tab5[:4]):
                if cols_d[idx].button(f"🔥 {theme}", key=f"hot_theme_btn_{idx}", use_container_width=True):
                    st.session_state.deep_tech_query = theme
                    st.session_state.deep_tech_results = None
                    st.session_state.deep_tech_brief = None

            st.markdown("### 🔎 직접 글로벌 테마 검색")
            with st.form(key="theme_search_form", clear_on_submit=False):
                col_in1, col_in2 = st.columns([8, 2], vertical_alignment="bottom")
                with col_in1:
                    custom_query = st.text_input(
                        "분석할 메가트렌드나 테마를 입력하세요", 
                        label_visibility="collapsed", 
                        key="deep_tech_input", 
                        placeholder="예: AI 데이터센터 전력, 비만치료제, 우주항공"
                    )
                with col_in2:
                    submit_btn = st.form_submit_button("🚀 글로벌 대장주 발굴", use_container_width=True)
                    
                if submit_btn:
                    if custom_query.strip():
                        st.session_state.deep_tech_query = custom_query.strip()
                        st.session_state.deep_tech_results = None
                        st.session_state.deep_tech_brief = None
                    else:
                        st.warning("테마 키워드를 입력해주세요!")

            if st.session_state.deep_tech_query and st.session_state.deep_tech_results is None:
                st.divider()
                st.markdown(f"### 🎯 '{st.session_state.deep_tech_query}' 글로벌 밸류체인 정밀 분석")
                
                with st.spinner("AI가 해당 테마의 월스트리트 모멘텀과 글로벌 핵심 촉매를 분석 중입니다..."):
                    theme_brief_prompt = f"당신은 글로벌 퀀트 애널리스트입니다.\n'{st.session_state.deep_tech_query}' 테마가 한국과 미국 시장을 주도하는 이유와 향후 글로벌 전망을 3줄로 명확하게 요약하세요."
                    st.session_state.deep_tech_brief = ask_gemini(theme_brief_prompt, api_key_input)
                    
                with st.spinner(f"✨ '{st.session_state.deep_tech_query}' 테마의 한·미 핵심 대장주 및 밸류체인 수혜주를 필터링 중입니다..."):
                    theme_stocks = get_theme_stocks_with_ai(st.session_state.deep_tech_query, api_key_input)
                    if theme_stocks:
                        progress_bar = st.progress(0.0)
                        status_text = st.empty()
                        theme_res_list = []
                        completed, total = 0, len(theme_stocks)
                        
                        def process_theme_stock(item):
                            if len(item) == 2:
                                name, code = item
                                time.sleep(0.1)
                                return analyze_technical_pattern(name, code)
                            return None
                            
                        with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
                            for future in concurrent.futures.as_completed({executor.submit(process_theme_stock, t): t for t in theme_stocks}):
                                res = future.result()
                                completed += 1
                                if res: theme_res_list.append(res)
                                progress_bar.progress(min(1.0, completed / total))
                                status_text.text(f"⚡ 한·미 증시 재무/차트 데이터 파싱 중... ({completed}/{total}) - {len(theme_res_list)}개 타점 확보")
                        
                        st.session_state.deep_tech_results = theme_res_list
                    else:
                        st.error(f"❌ '{st.session_state.deep_tech_query}' 테마와 관련된 종목을 찾지 못했습니다.")
                        st.session_state.deep_tech_query = None

            if st.session_state.deep_tech_results is not None:
                if st.session_state.get('deep_tech_brief'):
                    st.info(f"**💡 글로벌 AI 퀀트 인사이트:**\n{st.session_state.deep_tech_brief}")
                display_sorted_results(st.session_state.deep_tech_results, tab_key="t5", api_key=api_key_input, show_leader_rank=True)

elif selected_menu == "🇰🇷 국민성장펀드 12대 산업 수혜주":
    st.markdown("## 🇰🇷 국민성장펀드 12대 산업 수혜주")
    st.write("정부 주도 **150조원 규모 국민성장펀드**가 집중 투자하는 12개 첨단전략산업을 선택하면, "
             "AI가 해당 분야의 국내(KRX) 핵심 수혜 대장주를 발굴하고 차트·수급 타점을 즉시 분석합니다.")

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("총 펀드 규모", GROWTH_FUND_ALLOC["총 규모"] + "원")
    c2.metric("AI 배정", GROWTH_FUND_ALLOC["AI"] + "원")
    c3.metric("반도체 배정", GROWTH_FUND_ALLOC["반도체"] + "원")
    c4.metric("모빌리티 배정", GROWTH_FUND_ALLOC["모빌리티"] + "원")
    st.caption("※ 금융위원회 지정 주목적 투자대상 12개 산업 기준. 개별 자펀드는 결성액의 60% 이상을 해당 산업에 투자합니다.")
    st.divider()

    if not api_key_input:
        st.warning("⚠️ 사이드바에 Gemini API 키를 입력하시면 수혜주 스캐너가 활성화됩니다.")
    else:
        st.markdown("### 🎯 분석할 첨단전략산업을 선택하세요")
        for cat_name, sectors in GROWTH_FUND_SECTORS.items():
            st.markdown(f"**{cat_name}**")
            cols = st.columns(len(sectors))
            for idx, (label, query) in enumerate(sectors):
                if cols[idx].button(label, key=f"gf_btn_{label}", use_container_width=True):
                    st.session_state.gf_sector_query = query
                    st.session_state.gf_results = None

        if st.session_state.gf_sector_query and st.session_state.gf_results is None:
            st.divider()
            q = st.session_state.gf_sector_query
            st.markdown(f"### 📈 '{q}' 국민성장펀드 수혜주 정밀 분석")
            with st.spinner(f"✨ '{q}' 분야의 국내 핵심 수혜주 및 밸류체인을 필터링 중입니다..."):
                gf_stocks = get_growth_fund_stocks_with_ai(q, api_key_input)

            if gf_stocks:
                progress_bar = st.progress(0.0)
                status_text = st.empty()
                gf_res_list = []
                completed, total = 0, len(gf_stocks)

                def process_gf_stock(item):
                    name, code = item
                    time.sleep(0.1)
                    return analyze_technical_pattern(name, code)

                with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
                    futures = {executor.submit(process_gf_stock, t): t for t in gf_stocks}
                    for future in concurrent.futures.as_completed(futures):
                        res = future.result()
                        completed += 1
                        if res:
                            gf_res_list.append(res)
                        progress_bar.progress(min(1.0, completed / total))
                        status_text.text(f"⚡ KRX 재무/차트 데이터 파싱 중... ({completed}/{total}) - {len(gf_res_list)}개 타점 확보")

                st.session_state.gf_results = gf_res_list
            else:
                st.error(f"❌ '{q}' 분야 수혜주를 찾지 못했습니다. 다시 시도해주세요.")
                st.session_state.gf_sector_query = None

        if st.session_state.gf_results is not None:
            st.info(f"💡 **{st.session_state.gf_sector_query}** 분야의 국민성장펀드 정책 수혜 기대 종목입니다. "
                    "(아래에서 RSI·수급 기준 정렬 가능)")
            display_sorted_results(st.session_state.gf_results, tab_key="gf", api_key=api_key_input, show_leader_rank=True)

elif selected_menu == "🔥 간밤의 미국 급등주 & 수혜주":
    st.markdown("## 🔥 간밤의 미국 급등주 & 수혜주")
    st.caption("간밤 미국 증시에서 급등한 종목 → AI가 한국 수혜주(밸류체인)를 찾아주고 → 그 수혜주의 매매 타점까지 한 번에 확인하는 페이지입니다.")

    # [v7.0] ① 간밤 미국 시황 미니 배너 — 급등주 보기 전 위험선호부터 파악
    st.markdown("#### 🌙 간밤 미국 시황 (Risk-On / Off 체크)")
    with st.spinner("간밤 지수·VIX·환율 수집 중..."):
        render_overnight_banner()
    st.caption("💡 VIX(공포지수)가 급등하거나 지수가 크게 빠진 날은, 미국 급등주가 있어도 국장이 위험회피로 갈 수 있으니 보수적으로 접근하세요.")

    # [v7.0] ② 초보자 가이드 배치 (이 페이지도 타점 분석을 쓰므로)
    show_beginner_guide()
    show_trading_guidelines()
    st.divider()

    col_sec, col_gain = st.columns([1, 1.2], gap="large")
    with col_sec:
        st.subheader("📊 1. 미 증시 주도 섹터 (ETF)")
        st.caption("간밤 어느 섹터로 돈이 몰렸는지 (등락률 높은 순). 🔴빨강=상승 / 🔵파랑=하락")
        with st.spinner("섹터 ETF 등락률 산출 중..."):
            etf_df = get_us_sector_etfs()
            sty_etf = style_sector_etf_table(etf_df)
            if sty_etf is not None:
                st.dataframe(sty_etf, use_container_width=True, height=400)
            elif not etf_df.empty:
                st.dataframe(etf_df, use_container_width=True, hide_index=True)

        st.subheader("🚀 2. 글로벌 급등주 필터링")
        fetch_t = st.session_state.get('us_fetch_time', '-')
        rc1, rc2 = st.columns([3, 1])
        rc1.caption(f"기준 시각: {fetch_t} (KST) · 전일 대비 +5% 이상 급등주")
        if rc2.button("🔄 새로고침", use_container_width=True, key="refresh_gainers"):
            get_us_top_gainers.clear()
            df, ex_rate, ft = get_us_top_gainers()
            st.session_state.gainers_df = df
            st.session_state.ex_rate = ex_rate
            st.session_state.us_fetch_time = ft
            st.rerun()

        if not st.session_state.gainers_df.empty:
            sty_g = style_us_gainers_table(st.session_state.gainers_df)
            if sty_g is not None:
                st.dataframe(sty_g, use_container_width=True, height=420)
            else:
                st.dataframe(st.session_state.gainers_df, use_container_width=True, hide_index=True)
            opts = ["🔍 종목 선택"] + [f"{r['종목코드']} ({r['기업명']})" for _, r in st.session_state.gainers_df.iterrows()]
            sel_opt = st.selectbox("🎯 분석할 주도주 선택", opts)
            sel_tick = "N/A" if sel_opt == "🔍 종목 선택" else sel_opt.split(" ")[0]
        else:
            sel_tick = "N/A"
            sel_opt = "🔍 종목 선택"
            st.error("❌ 현재 급등주 데이터를 불러올 수 없습니다. (장 마감 직후·주말이면 데이터가 없을 수 있어요) 새로고침을 눌러보세요.")

    with col_gain:
        st.subheader("🔗 3. 글로벌 밸류체인 & 갭상승 대응 시나리오")
        if sel_tick != "N/A" and api_key_input:
            comp_name = sel_opt.split(" (")[1].replace(")", "")
            krx_df = get_krx_stocks()

            # [v7.0] 같은 종목이면 AI를 다시 부르지 않도록 세션에 캐싱 (폼 클릭 시 재호출 방지)
            if st.session_state.get('us_vc_ticker') != sel_tick:
                with st.spinner(f"✨ AI가 '{sel_tick}'의 공급망과 국장 수혜주를 분석 중입니다..."):
                    prompt = (
                        f"간밤에 미국 증시에서 '{comp_name}({sel_tick})' 종목이 급등했습니다. "
                        f"1.급등사유 2.한국 수혜주 3~5개(각 종목의 수혜 이유 포함) 3.시초가 갭상승 대응 시나리오를 작성하세요.\n"
                        f"⚠️ 반드시 맨 마지막 줄에 한국거래소에 상장된 정확한 종목명만 다음 형식으로 나열하세요: "
                        f"[수혜주]: 종목명1, 종목명2, 종목명3"
                    )
                    report = ask_gemini(prompt, api_key_input)
                    beneficiaries = extract_beneficiary_stocks(report, krx_df)
                    st.session_state.us_vc_ticker = sel_tick
                    st.session_state.us_vc_report = report
                    st.session_state.us_vc_benef = beneficiaries

            report = st.session_state.get('us_vc_report', '')
            beneficiaries = st.session_state.get('us_vc_benef', [])

            st.success("✅ 밸류체인 및 대응 시나리오 분석 완료!")
            # 화면에는 [수혜주] 파싱용 라인은 숨겨서 깔끔하게 표시
            display_report = re.sub(r'\n?\[?\s*수혜주[^\]:：]*\]?\s*[:：].*$', '', report).strip()
            st.markdown(display_report)

            st.divider()
            st.subheader("🎯 추천된 국장 수혜주 타점 즉시 확인")
            if beneficiaries:
                st.caption(f"💡 위 AI 분석에서 언급된 한국 수혜주 {len(beneficiaries)}개만 골라뒀어요. 선택하면 바로 타점을 분석합니다.")
                opts_krx = ["🔍 추천 수혜주 선택"] + [f"{n} ({c})" for n, c in beneficiaries]
                with st.form("vs_kr_form"):
                    col_v1, col_v2 = st.columns([8, 2])
                    with col_v1: us_sub_query = st.selectbox("추천 수혜주 타점 확인:", opts_krx, key="us_sub_scan", label_visibility="collapsed")
                    with col_v2: vs_btn = st.form_submit_button("🔍 타점 확인", use_container_width=True)
                if vs_btn and us_sub_query != "🔍 추천 수혜주 선택":
                    q_name = us_sub_query.rsplit(" (", 1)[0]
                    q_code = us_sub_query.rsplit("(", 1)[-1].replace(")", "").strip()
                    with st.spinner("차트 타점 분석 중..."):
                        res = analyze_technical_pattern(q_name, q_code)
                        if res: draw_stock_card(res, api_key_str=api_key_input, is_expanded=True, key_suffix="us_val_chain")
                        else: st.error("❌ 해당 종목 데이터를 불러올 수 없습니다.")
            else:
                st.warning("AI 분석에서 한국 수혜주를 자동으로 추출하지 못했어요. 아래에서 직접 검색해 확인할 수 있습니다.")
                if not krx_df.empty:
                    opts_krx = ["🔍 종목명 검색 후 엔터"] + (krx_df['Name'].astype(str) + " (" + krx_df['Code'].astype(str) + ")").tolist()
                    with st.form("vs_kr_form_fallback"):
                        col_v1, col_v2 = st.columns([8, 2])
                        with col_v1: us_sub_query = st.selectbox("수혜주 차트 상태 확인:", opts_krx, key="us_sub_scan_fb", label_visibility="collapsed")
                        with col_v2: vs_btn = st.form_submit_button("🔍 타점 확인", use_container_width=True)
                    if vs_btn and us_sub_query != "🔍 종목명 검색 후 엔터":
                        q_name = us_sub_query.rsplit(" (", 1)[0]
                        q_code = us_sub_query.rsplit("(", 1)[-1].replace(")", "").strip()
                        with st.spinner("차트 타점 분석 중..."):
                            res = analyze_technical_pattern(q_name, q_code)
                            if res: draw_stock_card(res, api_key_str=api_key_input, is_expanded=True, key_suffix="us_val_chain_fb")
                            else: st.error("❌ 해당 종목 데이터를 불러올 수 없습니다.")
        elif sel_tick != "N/A" and not api_key_input:
            st.warning("⬅️ 왼쪽에서 종목은 선택됐어요. AI 밸류체인 분석을 보려면 사이드바에 API 키를 입력해주세요.")
        else:
            st.info("⬅️ 왼쪽 급등주 목록에서 분석할 종목을 선택하면, AI가 한국 수혜주와 대응 시나리오를 여기에 보여줍니다.")

elif selected_menu == "🚨 당일 상/하한가 분석":
    st.subheader("🚨 당일 상/하한가 분석")
    with st.spinner("데이터 수집 중..."): upper_df, lower_df = get_limit_stocks()
    if api_key_input and not upper_df.empty:
        if st.button("🤖 AI 상한가 테마 즉시 분석", type="primary", use_container_width=True):
            st.success(ask_gemini(f"오늘 상한가 종목들: {upper_df['Name'].tolist()}\n공통된 테마/이슈 3줄 요약해줘.", api_key_input))
    col_u, col_l = st.columns(2)
    with col_u:
        st.markdown("### 🔴 상한가 종목")
        if not upper_df.empty:
            display_upper = upper_df[['Name', 'Sector', 'Amount_Ouk']].copy()
            display_upper.columns = ['종목명', '섹터', '거래대금(억)']
            display_upper['거래대금(억)'] = display_upper['거래대금(억)'].apply(lambda x: f"{x:,}")
            st.dataframe(display_upper, use_container_width=True, hide_index=True)
            with st.form("u_limit_form"):
                col_u1, col_u2 = st.columns([8, 2])
                with col_u1: sel_u = st.selectbox("상한가 종목 타점 확인:", ["선택"] + upper_df['Name'].tolist(), key="sel_u", label_visibility="collapsed")
                with col_u2: sel_u_btn = st.form_submit_button("🔍 타점 확인", use_container_width=True)
            if sel_u_btn and sel_u != "선택":
                krx_df_local = get_krx_stocks()
                match_row = krx_df_local[krx_df_local['Name'] == sel_u]
                if not match_row.empty:
                    k_code = match_row['Code'].iloc[0]
                    with st.spinner("차트 타점 분석 중..."):
                        if res := analyze_technical_pattern(sel_u, k_code): draw_stock_card(res, api_key_str=api_key_input, is_expanded=True, key_suffix="t6_u")
                else: st.error(f"❌ '{sel_u}' 종목의 코드를 찾을 수 없어 분석할 수 없습니다.")
        else: st.info("현재 상한가 종목이 없습니다.")
    with col_l:
        st.markdown("### 🔵 하한가 종목")
        if not lower_df.empty: 
            display_lower = lower_df[['Name', 'Sector', 'Amount_Ouk']].copy()
            display_lower.columns = ['종목명', '섹터', '거래대금(억)']
            display_lower['거래대금(억)'] = display_lower['거래대금(억)'].apply(lambda x: f"{x:,}")
            st.dataframe(display_lower, use_container_width=True, hide_index=True)
        else: st.info("현재 하한가 종목이 없습니다.")

elif selected_menu == "💰 국장 수급 분석 (외국인·기관·개인)":
    st.markdown("## 💰 국장 수급 분석 (외국인·기관·개인)")
    st.caption("최근 거래일 기준 · 거래대금 상위 종목 스캔 · 단위: 억원 · 🔴빨강=순매수/상승 · 🔵파랑=순매도/하락")
    with st.spinner("네이버 투자자별 순매수 데이터 수집 중... (첫 조회는 십수 초, 이후 30분 캐시)"):
        flows = get_kr_investor_flows()
    if flows is None or flows.empty:
        st.error("❌ 수급 데이터를 불러오지 못했습니다. 잠시 후 다시 시도해주세요.")
    else:
        st.caption(f"📊 거래대금 상위 {len(flows)}개 종목 분석 · 개인은 외국인·기관의 반대값으로 추정")
        t_top, t_smart, t_hand = st.tabs(
            ["🏆 순매수·순매도 TOP", "🧠 개미 vs 스마트머니", "🔄 수급 주체 손바뀜"])
        with t_top:
            for emoji, inv, note in [("🦅", "외국인", ""), ("🏛️", "기관", ""), ("🐜", "개인", " (추정)")]:
                st.markdown(f"#### {emoji} {inv}{note}")
                cb, cs = st.columns(2)
                with cb:
                    st.markdown("**🔴 순매수 TOP10**")
                    _render_netbuy_list(flows, inv, ascending=False)
                with cs:
                    st.markdown("**🔵 순매도 TOP10**")
                    _render_netbuy_list(flows, inv, ascending=True)
                st.markdown("<div style='height:6px;'></div>", unsafe_allow_html=True)
        with t_smart:
            st.caption("스마트머니 = 외국인+기관 합산. (네이버 데이터 특성상 개인은 외국인·기관의 반대값으로 추정)")
            c1, c2 = st.columns(2)
            with c1:
                st.markdown("#### 🧠 스마트머니 매집")
                st.caption("외국인+기관 순매수 상위 (개미는 반대편)")
                _render_flow_chips(flows[flows["스마트머니"] > 0], sort_col="스마트머니", ascending=False)
            with c2:
                st.markdown("#### 🐜 개미 우위")
                st.caption("외국인+기관 순매도 상위 (개미가 받아낸 종목)")
                _render_flow_chips(flows[flows["스마트머니"] < 0], sort_col="스마트머니", ascending=True)
            st.markdown("#### 🤝 외국인·기관 동반 순매수")
            st.caption("외국인·기관이 둘 다 순매수한 종목 (가장 강한 수급 신호)")
            _render_flow_chips(flows[(flows["외국인"] > 0) & (flows["기관"] > 0)],
                               sort_col="스마트머니", ascending=False)
        with t_hand:
            st.caption("어제 순매도 → 오늘 순매수로 전환된 종목 (스마트머니 기준 · 흔히 '바닥 신호'로 해석)")
            _render_handover(flows)
    st.caption("데이터: 네이버 금융 · 정보 제공용이며 매수·매도 추천이 아닙니다. 투자 판단과 책임은 본인에게 있습니다.")

elif selected_menu == "🔥 지금 뜨는 섹터 (국장·미장)":
    st.markdown("## 🔥 지금 뜨는 섹터")
    st.caption("대표 종목 평균 등락률 순 · 🔴빨강=상승 / 🔵파랑=하락")

    def _render_sector_market(market, spinner_msg):
        with st.spinner(spinner_msg):
            sectors = get_trending_sectors(market)
        if not sectors:
            who = "국장" if market == "KR" else "미장"
            st.error(f"❌ {who} 섹터 데이터를 불러올 수 없습니다. 잠시 후 다시 시도해주세요.")
            return
        hot = sum(1 for s in sectors if s["avg"] > 0)
        cc1, cc2, cc3 = st.columns(3)
        cc1.metric("강세 테마", f"{hot} / {len(sectors)}")
        cc2.metric("🔥 최강 테마", sectors[0]["theme"], f"{sectors[0]['avg']:+.2f}%")
        cc3.metric("🧊 최약 테마", sectors[-1]["theme"], f"{sectors[-1]['avg']:+.2f}%")
        st.markdown("#### 테마별 평균 등락 (강세 순)")
        render_trending_sectors(sectors)

    tab_kr, tab_us = st.tabs(["🇰🇷 국장 (KOSPI·KOSDAQ)", "🇺🇸 미장 (US)"])
    with tab_kr:
        _render_sector_market("KR", "국장 테마별 등락 수집 중...")
    with tab_us:
        _render_sector_market("US", "미장 테마별 등락 수집 중... (첫 조회는 수십 초, 이후 30분 캐시)")
    st.caption("대표 종목 평균 등락률 기준이며, 테마 구성은 참고용입니다. 투자 권유가 아닙니다.")

elif selected_menu == "🚦 거래량 급증 & 시장 경보":
    st.markdown("## 🚦 거래량 급증 & 시장 경보")
    tab_vol, tab_warn = st.tabs(["📊 거래량 급증/급감", "🛡️ 관리종목 및 시장경보"])

    with tab_vol:
        st.caption("💡 **거래량 폭증** = 평소보다 돈·관심이 몰린 종목 (세력 의심 / 급등 후보). "
                   "색상은 한국식 — 🔴빨강=상승, 🔵파랑=하락. 막대가 길수록 거래량이 더 터진 종목입니다.")
        sub_kr, sub_us = st.tabs(["🇰🇷 국장 (KRX) TOP20", "🇺🇸 미장 (US) TOP20"])

        with sub_kr:
            with st.spinner("국장 거래량 데이터 스크래핑 중..."): surge_df, drop_df = get_volume_surge_drop()
            c_surge, c_drop = st.columns(2)
            with c_surge:
                st.markdown("#### 🔥 거래량 급증 TOP20")
                sty_s, _ = style_volume_table(surge_df, "surge")
                if sty_s is not None:
                    st.dataframe(sty_s, use_container_width=True, height=740)
                elif not surge_df.empty:
                    st.dataframe(surge_df, use_container_width=True, hide_index=True)
                else:
                    st.error("❌ 현재 데이터를 불러올 수 없습니다.")
            with c_drop:
                st.markdown("#### ❄️ 거래량 급감 TOP20")
                sty_d, _ = style_volume_table(drop_df, "drop")
                if sty_d is not None:
                    st.dataframe(sty_d, use_container_width=True, height=740)
                elif not drop_df.empty:
                    st.dataframe(drop_df, use_container_width=True, hide_index=True)
                else:
                    st.error("❌ 현재 데이터를 불러올 수 없습니다.")

        with sub_us:
            st.caption("🇺🇸 주요 미국 대형주 유니버스 기준 · **오늘 거래량 ÷ 최근 20일 평균** 배율(>1 급증 / <1 급감) · "
                       "첫 조회는 수십 초 걸릴 수 있어요(이후 30분 캐시).")
            with st.spinner("미장 거래량 데이터 수집 중... (야후 파이낸스)"):
                us_surge, us_drop = get_us_volume_surge_drop()
            if us_surge.empty and us_drop.empty:
                st.error("❌ 미국 거래량 데이터를 불러올 수 없습니다. 잠시 후 다시 시도해주세요.")
            else:
                uc1, uc2 = st.columns(2)
                with uc1:
                    st.markdown("#### 🔥 거래량 급증 TOP20")
                    s = style_us_volume_table(us_surge, "surge")
                    st.dataframe(s if s is not None else us_surge, use_container_width=True, height=740)
                with uc2:
                    st.markdown("#### ❄️ 거래량 급감 TOP20")
                    d = style_us_volume_table(us_drop, "drop")
                    st.dataframe(d if d is not None else us_drop, use_container_width=True, height=740)
    with tab_warn:
        with st.spinner("시장경보 데이터 스크래핑 중..."): mgmt_df, alert_df = get_market_warnings()

        st.markdown("#### 🛑 관리종목 (상장폐지 위험)")
        st.caption("⚠️ 여기 있는 종목은 **상장폐지·거래정지 위험**이 있는 고위험군입니다. 매매 전 반드시 사유를 확인하세요. "
                   "사유 색상: 🔴빨강=치명적(폐지·파산) / 🟠주황=위험(실질심사·회생) / 🟡노랑=주의")
        sty_m = style_warning_table(mgmt_df, "mgmt")
        if sty_m is not None:
            st.dataframe(sty_m, use_container_width=True, height=420)
        elif not mgmt_df.empty:
            st.dataframe(mgmt_df, use_container_width=True, hide_index=True)
        else:
            st.success("✅ 현재 지정된 관리종목이 없습니다.")

        st.markdown("#### ⚠️ 투자주의/경고/위험 종목")
        st.caption("💡 이상 급등·단기과열 등으로 거래소가 **투자자 보호 차원에서 지정**한 종목입니다. 변동성이 매우 큽니다.")
        sty_a = style_warning_table(alert_df, "alert")
        if sty_a is not None:
            st.dataframe(sty_a, use_container_width=True, height=420)
        elif not alert_df.empty:
            st.dataframe(alert_df, use_container_width=True, hide_index=True)
        else:
            st.success("✅ 현재 지정된 시장경보 종목이 없습니다.")

elif selected_menu == "📰 실시간 특징주 속보 & 리포트":
    st.subheader("📰 실시간 특징주 속보 & 리포트")
    news_sub1, news_sub2, news_sub3 = st.tabs(["🚨 실시간 특징주/속보", "📋 증권사 종목 리포트 검색", "🔥 AI 데일리 리포트 (TEBI-Style)"])
    
    with news_sub1:
        if st.button("🔄 속보 리로드"): 
            st.session_state.news_data = []
            st.session_state.seen_links = set()
            st.session_state.seen_titles = set()
            get_latest_naver_news.clear()
            st.rerun()
        with st.spinner("뉴스를 불러오는 중..."): update_news_state()
        
        # iterrows 제거: 2,800여 행을 매 새로고침마다 순회하던 것을 컬럼 벡터화로 대체
        _krx_df = get_krx_stocks()
        _name_ok = _krx_df['Name'].astype(str).str.len() > 1
        krx_dict = dict(zip(_krx_df.loc[_name_ok, 'Name'], _krx_df.loc[_name_ok, 'Code']))
        news_aliases = {"삼전": ("삼성전자", "005930"), "하이닉스": ("SK하이닉스", "000660"), "현차": ("현대차", "005380"), "엔솔": ("LG에너지솔루션", "373220")}
        sorted_names = sorted(krx_dict.keys(), key=len, reverse=True)
        
        for i, news in enumerate(st.session_state.news_data[:50]):
            title = news['title']
            found_comps = []
            for alias, (real_name, fallback_code) in news_aliases.items():
                if alias in title:
                    found_comps.append((real_name, krx_dict.get(real_name, fallback_code)))
                    break
            if not found_comps:
                for name in sorted_names:
                    if name in title:
                        found_comps.append((name, krx_dict[name]))
                        break 
            
            with st.container(border=True):
                cols = st.columns([1, 6, 2, 1])
                cols[0].markdown(f"**🕒 {news['time']}**")
                cols[1].markdown(f"{title}")
                with cols[2]:
                    if found_comps:
                        if st.button(f"🔍 {found_comps[0][0]} 분석", key=f"qa_{i}"):
                            st.session_state[f"news_analyze_{i}"] = not st.session_state.get(f"news_analyze_{i}", False)
                cols[3].link_button("원문🔗", news['link'])
            
            if st.session_state.get(f"news_analyze_{i}", False):
                with st.spinner(f"'{found_comps[0][0]}' 차트 분석 중..."):
                    res = analyze_technical_pattern(found_comps[0][0], found_comps[0][1])
                    if res: draw_stock_card(res, api_key_str=api_key_input, is_expanded=True, key_suffix=f"news_qa_{i}")
                
    with news_sub2:
        st.markdown("### 📋 당일 실시간 리포트 & 종목별 과거 리포트 검색")
        
        st.markdown("#### 🔍 특정 종목 리포트 검색 (최근 6개월)")
        search_krx_df = get_krx_stocks()
        if not search_krx_df.empty:
            opts = ["선택 안함 (당일 전체 신규 리포트 보기)"] + (search_krx_df['Name'].astype(str) + " (" + search_krx_df['Code'].astype(str) + ")").tolist()
            report_query = st.selectbox("리포트를 검색할 종목을 선택하세요:", opts)
            
            if report_query != "선택 안함 (당일 전체 신규 리포트 보기)":
                q_name = report_query.rsplit(" (", 1)[0]
                q_code = report_query.rsplit("(", 1)[-1].replace(")", "").strip()
                
                with st.spinner(f"'{q_name}'의 최근 6개월 리포트를 검색 중입니다..."):
                    history_df = get_stock_research_history(q_code)
                    
                if not history_df.empty:
                    st.success(f"✅ '{q_name}' 관련 리포트 {len(history_df)}건을 찾았습니다.")
                    display_history_df = history_df[['작성일', '증권사', '제목', '적정가격', '투자의견', '원문링크']].copy()
                    display_history_df['적정가격'] = display_history_df['적정가격'].apply(lambda x: f"{x:,}원" if x > 0 else "-")
                    st.dataframe(
                        display_history_df, 
                        column_config={"원문링크": st.column_config.LinkColumn("원문 보기")},
                        use_container_width=True, hide_index=True
                    )
                else:
                    st.warning("해당 종목의 최근 6개월 내 발간된 증권사 리포트가 없습니다.")
                
                st.divider()

        st.markdown("#### 🆕 오늘의 전체 신규 리포트")
        with st.spinner("당일 리포트의 투자의견·목표가를 분석 중입니다..."):
            res_df = get_today_research_details()
        if not res_df.empty:
            if api_key_input and st.button("🤖 AI 당일 리포트 종합 의견 및 섹터 요약", use_container_width=True, type="primary"):
                with st.spinner("당일 발간된 리포트들을 분석하여 시장 분위기와 유망 섹터를 요약 중입니다..."):
                    report_text = "\n".join([f"- [{r['증권사']}] {r['종목명']} (의견:{r['투자의견']}): {r['제목']}" for _, r in res_df.head(30).iterrows()])
                    prompt = f"당신은 증권사 리서치 센터장입니다. 오늘 발간된 다음 증권사 리포트 제목들을 분석하여, 1) 오늘 증권가가 가장 주목하는 핵심 섹터/테마 2개와 그 이유, 2) 시장의 전반적인 투자의견 요약을 마크다운으로 작성해주세요.\n\n[오늘의 리포트]\n{report_text}"
                    st.info(ask_gemini(prompt, api_key_input), icon="💡")

            show_df = res_df[['종목명', '증권사', '제목', '투자의견', '목표가', '변동', '작성일', '원문링크']].copy()
            show_df['목표가'] = show_df['목표가'].apply(lambda x: f"{int(x):,}원" if x and x > 0 else "-")
            st.dataframe(
                show_df,
                column_config={"원문링크": st.column_config.LinkColumn("원문 보기")},
                use_container_width=True, hide_index=True
            )
        else:
            st.error("❌ 리포트 데이터를 불러오지 못했습니다.")
            
    with news_sub3:
        st.markdown("### 🤖 Auto Research Desk (오늘의 증권가 종합 분석)")
        st.write("기관 트레이딩 데스크 수준의 일일 요약, 쟁점 분석, 목표가 랭킹을 AI가 생성합니다.")
        if api_key_input:
            if st.button("🚀 TEBI-Style 모닝 리포트 생성 시작", type="primary"):
                with st.spinner("오늘 발간된 30개의 증권사 리포트 원문을 AI가 해독 및 분석 중입니다..."):
                    today_reports = get_today_research_details()
                    if not today_reports.empty:
                        # 투자의견은 standardize_opinion으로 '강력매수/매수/중립/매도/N/A' 정규화됨
                        op = today_reports['투자의견'].astype(str)
                        buy_mask = op.isin(['강력매수', '매수'])
                        sell_mask = op.eq('매도')
                        buys = int(buy_mask.sum())
                        sells = int(sell_mask.sum())
                        holds = len(today_reports) - buys - sells

                        st.markdown("#### 📊 오늘의 증권가 투자의견 요약 (Verdict)")
                        c1, c2, c3, c4 = st.columns(4)
                        c1.metric("총 발간 리포트", f"{len(today_reports)}건")
                        c2.metric("BUY (매수·강력매수)", f"{buys}건")
                        c3.metric("HOLD/기타", f"{holds}건")
                        c4.metric("SELL (매도)", f"{sells}건")

                        # 매수의견 종목 목록 — 'BUY n건'이 어떤 종목인지 바로 확인
                        if buys > 0:
                            def _prc_buyops():
                                buy_tbl = today_reports[buy_mask][['종목명', '증권사', '투자의견', '목표가', '제목']].copy()
                                buy_tbl['목표가'] = buy_tbl['목표가'].apply(lambda x: f"{int(x):,}원" if x and x > 0 else "-")
                                st.dataframe(buy_tbl, use_container_width=True, hide_index=True)
                            _register_popup("buyops", _prc_buyops)
                            _popup_button(f"🔴 매수의견 종목 {buys}건 보기", "buyops", f"🔴 매수의견 종목 {buys}건", key="btn_buyops")

                        st.markdown("#### 📈 당일 목표가(TP) 상/하향 랭킹")
                        st.caption("💡 증권사가 직전 리포트 대비 목표가를 올렸으면 🔴상향, 내렸으면 🔵하향. "
                                   "원문에 '종전 목표가'가 없으면 `유지/신규`로 분류되어 이 랭킹에는 나오지 않습니다. "
                                   "따라서 위 BUY 건수와 아래 상향 건수는 서로 다른 지표입니다.")
                        upgrades = today_reports[today_reports['변동'] == '상향'].sort_values('변동률', ascending=False)
                        downgrades = today_reports[today_reports['변동'] == '하향'].sort_values('변동률', ascending=True)

                        col_up, col_down = st.columns(2)
                        with col_up:
                            st.success(f"**▲ 상향 리포트 ({len(upgrades)}건)**")
                            sty_up = style_report_table(upgrades, "up")
                            if sty_up is not None:
                                st.dataframe(sty_up, use_container_width=True, height=min(420, 80 + len(upgrades) * 36))
                            else:
                                st.write("목표가 상향 종목이 없습니다.")

                        with col_down:
                            st.error(f"**▼ 하향 리포트 ({len(downgrades)}건)**")
                            sty_down = style_report_table(downgrades, "down")
                            if sty_down is not None:
                                st.dataframe(sty_down, use_container_width=True, height=min(420, 80 + len(downgrades) * 36))
                            else:
                                st.write("목표가 하향 종목이 없습니다.")
                            
                        st.markdown("#### ⚔️ 애널리스트 갑론을박 & 💡 Bottom Line")
                        report_texts = "\n".join([f"- [{r['증권사']}] {r['종목명']} (의견: {r['투자의견']}, TP변동: {r['변동']}): {r['제목']}" for _, r in today_reports.iterrows()])
                        prompt = f"""
                        당신은 기관 프랍 트레이더를 위한 수석 퀀트 애널리스트입니다. 오늘 한국 증시에서 발간된 증권사 리포트 목록입니다:
                        {report_texts}
                        
                        다음 3가지를 마크다운으로 명확하게 작성하세요:
                        1. **🔥 주도 섹터 및 핵심 모멘텀**: 오늘 리포트들이 가장 집중적으로 다루고 있는(목표가 상향이 많은) 핵심 섹터 1~2개와 그 이유.
                        2. **⚔️ 애널리스트 갑론을박 (Debate)**: 시장에서 의견이 엇갈리는 종목이나 섹터를 찾아 강세(Bull) 논리와 약세/보수적(Bear) 논리를 대비시켜 서술하세요.
                        3. **💡 Bottom Line (최종 액션 플랜)**: 전체적인 매수/매도 비율을 고려했을 때, 투자자가 오늘 취해야 할 명확한 행동 지침(예: 적극 매수, 차익 실현 등)을 3줄로 결론지으세요.
                        """
                        st.info(ask_gemini(prompt, api_key_input))
                    else:
                        st.error("리포트 데이터를 파싱하지 못했습니다.")
        else:
            st.warning("API 키를 입력해야 AI 데일리 리포트를 생성할 수 있습니다.")

elif selected_menu == "🔬 개별 기업 정밀 진단 (AI 비전)":
    st.markdown("## 🔬 개별 기업 정밀 진단 (AI 비전)")
    st.caption("👁️ 차트 이미지(캡처) AI 비전 분석은 사이드바 **[심층 분석 & 도구] → 👁️ 차트 이미지 AI 비전 분석** 메뉴로 이동했습니다.")
    market_choice = st.radio("시장 선택", ["🇰🇷 국내 주식", "🇺🇸 미국 주식"], horizontal=True)
    if market_choice == "🇰🇷 국내 주식":
        krx_df = get_krx_stocks()
        searched_name = searched_code = None
        do_analyze = False
        if not krx_df.empty:
            opts = ["🔍 분석할 국내 종목을 검색/선택하세요"] + (krx_df['Name'].astype(str) + " (" + krx_df['Code'].astype(str) + ")").tolist()
            col_s1, col_s2 = st.columns([8, 2])
            with col_s1: kr_query = st.selectbox("👇 종목명/코드 검색:", opts, label_visibility="collapsed")
            with col_s2: kr_search_btn = st.button("📊 분석 시작", use_container_width=True)
            if kr_query != "🔍 분석할 국내 종목을 검색/선택하세요" and (kr_query or kr_search_btn):
                searched_name = kr_query.rsplit(" (", 1)[0]
                searched_code = kr_query.rsplit("(", 1)[-1].replace(")", "").strip()
                do_analyze = True
        else:
            # 폴백: 종목 목록 로드 실패 시 종목코드 직접 입력
            st.warning("⚠️ 국내 종목 목록을 일시적으로 불러오지 못했습니다. 아래에 **종목코드 6자리**를 직접 입력해 분석하세요. (예: 005930)")
            col_s1, col_s2 = st.columns([8, 2])
            with col_s1: kr_manual = st.text_input("종목코드/이름 입력:", placeholder="예: 005930  또는  005930 삼성전자", label_visibility="collapsed", key="kr_manual_in")
            with col_s2: kr_manual_btn = st.button("📊 분석 시작", use_container_width=True, key="kr_manual_btn")
            if kr_manual:
                m = re.search(r"\d{6}", kr_manual)
                if m:
                    searched_code = m.group()
                    searched_name = kr_manual.replace(searched_code, "").strip() or searched_code
                    do_analyze = True
                elif kr_manual_btn:
                    st.error("6자리 종목코드를 포함해 입력해 주세요. 예: 005930")
        if do_analyze and searched_code:
            with st.spinner(f"📡 '{searched_name}' 타점 분석 중..."):
                res = analyze_technical_pattern(searched_name, searched_code)
                if res:
                    # 🌟 다중 테마 뷰어 출력 (국내 주식) 🌟
                    render_single_stock_themes(searched_name, api_key_input)
                    draw_stock_card(res, api_key_str=api_key_input, is_expanded=True, key_suffix="t4_kr")
                else:
                    st.error("❌ 데이터 로드 실패 — 종목코드를 확인해 주세요.")
    else:
        col_us1, col_us2 = st.columns([8, 2])
        with col_us1: us_query = st.text_input("👇 미국 주식 종목명/티커 입력 (예: AAPL):", label_visibility="collapsed")
        with col_us2: us_search_btn = st.button("🔍 검색", use_container_width=True)
        if us_query or us_search_btn:
            with st.spinner(f"📡 검색 중..."): us_results = search_us_ticker(us_query)
            if us_results: st.session_state.us_search_results = us_results
            else: st.error("❌ 검색 결과 없음")
        
        if "us_search_results" in st.session_state and st.session_state.us_search_results:
            sel_us_opt = st.selectbox("🎯 정확한 종목 선택:", ["선택하세요"] + st.session_state.us_search_results)
            analyze_btn = st.button("📊 분석 시작", use_container_width=True)
            if analyze_btn and sel_us_opt != "선택하세요":
                us_ticker = sel_us_opt.split(" ")[0]
                with st.spinner(f"📡 '{us_ticker}' 분석 중..."):
                    _res_us = analyze_technical_pattern(us_ticker, us_ticker)
                st.session_state.indiv_result_us = {"res": _res_us, "ticker": us_ticker} if _res_us else None
                if not _res_us:
                    st.error("❌ 데이터 로드 실패 — 종목을 확인해 주세요.")
            # 분석 결과를 세션에 보존 → 질의응답 토글 등 리런에도 카드가 사라지지 않음
            _ir_us = st.session_state.get("indiv_result_us")
            if _ir_us and _ir_us.get("res"):
                render_single_stock_themes(_ir_us["ticker"], api_key_input)
                draw_stock_card(_ir_us["res"], api_key_str=api_key_input, is_expanded=True, key_suffix="t4_us")


elif selected_menu == "👁️ 차트 이미지 AI 비전 분석":
    st.markdown("## 👁️ 차트 이미지 AI 비전 분석")
    st.info("💡 차트를 캡처(Windows: `Win+Shift+S` / Mac: `Cmd+Shift+4`)한 뒤 **📋 클립보드 붙여넣기 버튼**만 누르면 바로 들어옵니다. 파일 업로드와 이미지 URL 방식도 그대로 지원해요.")
    paste_col, upload_col, url_col = st.columns([1, 1, 1])
    with paste_col:
        st.markdown("**📋 클립보드 캡처 붙여넣기**")
        try:
            from streamlit_paste_button import paste_image_button as _paste_image_button
            _paste_res = _paste_image_button(label="📋 캡처한 차트 붙여넣기", key="vision_paste_btn", errors="ignore")
            if _paste_res is not None and getattr(_paste_res, "image_data", None) is not None:
                st.session_state["vision_pasted_img"] = _paste_res.image_data
        except ImportError:
            st.warning("📦 클립보드 붙여넣기에는 `streamlit-paste-button` 패키지가 필요합니다. "
                       "requirements.txt에 추가해 두었으니 재배포(또는 `pip install streamlit-paste-button`)하면 버튼이 활성화돼요.")
        if st.session_state.get("vision_pasted_img") is not None:
            if st.button("🗑️ 붙여넣은 이미지 지우기", key="vision_paste_clear", use_container_width=True):
                st.session_state["vision_pasted_img"] = None
                st.rerun()
    with upload_col:
        uploaded_chart = st.file_uploader("📸 이미지 파일 업로드", type=["png", "jpg", "jpeg"])
    with url_col:
        image_url = st.text_input("🔗 이미지 주소(URL) 붙여넣기", placeholder="https://example.com/chart.png")

    img_to_analyze = None
    if st.session_state.get("vision_pasted_img") is not None:
        img_to_analyze = st.session_state["vision_pasted_img"]
        st.image(img_to_analyze, caption="📋 클립보드에서 붙여넣은 차트", use_container_width=True)
    elif uploaded_chart:
        img_to_analyze = PIL.Image.open(uploaded_chart)
        st.image(img_to_analyze, use_container_width=True)
    elif image_url:
        try:
            img_to_analyze = PIL.Image.open(requests.get(image_url, stream=True).raw)
            st.image(img_to_analyze, use_container_width=True)
        except Exception: st.error("❌ 이미지 URL 오류")

    if img_to_analyze and st.button("🤖 Gemini Vision 정밀 분석 시작", type="primary", use_container_width=True):
        if not api_key_input: st.error("API 키가 필요합니다.")
        else:
            with st.spinner("AI가 차트를 시각적으로 해독 중입니다..."):
                prompt = "전설적인 차트 분석가로서 차트의 패턴, 지지/저항선, 단기 대응 전략을 마크다운으로 분석해주세요."
                result = ask_gemini_vision(prompt, img_to_analyze, api_key_input)
                st.success(result)

elif selected_menu == "📊 국내외 핵심 ETF 분석":
    st.markdown("## 📊 국내외 핵심 ETF 분석")
    etf_tab1, etf_tab2 = st.tabs(["🇰🇷 국내 핵심 ETF", "🇺🇸 미국 핵심 ETF"])
    
    with etf_tab1:
        st.subheader("국내 상장 주요 ETF (TOP 50)")
        with st.spinner("국내 ETF 실시간 데이터를 불러오는 중..."):
            try:
                krx_etf = get_krx_etf_list()
                if not krx_etf.empty:
                    price_col = 'Close' if 'Close' in krx_etf.columns else 'Price'
                    display_etf = krx_etf[['Symbol', 'Name', price_col, 'Change', 'Volume']].head(50).copy()
                    
                    # 💡 [핵심 버그 수정] Change 컬럼은 '등락률(%)'이 아니라 '등락금액(원)'입니다!
                    # 따라서 (등락금액 / 전일종가) * 100 으로 실제 등락률(%)을 직접 계산합니다.
                    def calc_pct_change(row):
                        try:
                            current_price = float(row[price_col])
                            change_amount = float(row['Change'])
                            prev_price = current_price - change_amount  # 전일종가 역산
                            if prev_price > 0:
                                return (change_amount / prev_price) * 100
                            return 0.0
                        except Exception as _dg_e:
                            _diag_note("calc_pct_change", _dg_e)
                            return 0.0
                            
                    display_etf['ChangeRatio'] = display_etf.apply(calc_pct_change, axis=1)
                    
                    # UI 표출용으로 컬럼 재배치 및 이름 변경
                    display_etf = display_etf[['Symbol', 'Name', price_col, 'ChangeRatio', 'Volume']]
                    display_etf.columns = ['종목코드', '종목명', '현재가', '등락률', '거래량']
                    
                    display_etf['등락률'] = display_etf['등락률'].apply(lambda x: f"{x:+.2f}%")
                    display_etf['현재가'] = display_etf['현재가'].apply(lambda x: f"{int(x):,}원" if pd.notna(x) else "0원")
                    display_etf['거래량'] = display_etf['거래량'].apply(lambda x: f"{int(x):,}" if pd.notna(x) else "0")
                    
                    st.dataframe(display_etf, use_container_width=True, hide_index=True)
            except Exception as e:
                st.error(f"ETF 스크래핑 에러: {e}")
                krx_etf = pd.DataFrame()
                
        st.divider()
        st.subheader("🔍 개별 ETF 정밀 타점 분석 (전체 화면)")
        if not krx_etf.empty:
            etf_opts = ["선택하세요"] + (krx_etf['Name'].astype(str) + " (" + krx_etf['Symbol'].astype(str) + ")").tolist()
            sel_etf = st.selectbox("분석할 ETF 선택:", etf_opts, label_visibility="collapsed")
            if sel_etf != "선택하세요":
                e_name = sel_etf.rsplit(" (", 1)[0]
                e_code = sel_etf.rsplit("(", 1)[-1].replace(")", "").strip()
                with st.spinner(f"'{e_name}' 타점 분석 중..."):
                    res = analyze_technical_pattern(e_name, e_code)
                    if res: draw_stock_card(res, api_key_str=api_key_input, is_expanded=True, key_suffix="kr_etf")
                
    with etf_tab2:
        st.subheader("미국 상장 주요 메가 ETF")
        us_etfs = ['SPY', 'QQQ', 'DIA', 'IWM', 'SCHD', 'JEPI', 'VOO', 'VTI', 'ARKK', 'SMH', 'SOXX', 'XLK', 'XLF', 'XLV', 'TLT', 'TMF']
        with st.spinner("미국 ETF 데이터를 불러오는 중..."):
            us_data_df = get_us_etf_summary(us_etfs)
            if not us_data_df.empty: 
                st.dataframe(us_data_df, use_container_width=True, hide_index=True)
                
        st.divider()
        st.subheader("🔍 미국 ETF 정밀 타점 분석 (전체 화면)")
        sel_us_etf = st.selectbox("분석할 미국 ETF 선택:", ["선택하세요"] + us_etfs)
        if sel_us_etf != "선택하세요":
            with st.spinner(f"'{sel_us_etf}' 타점 분석 중..."):
                res = analyze_technical_pattern(sel_us_etf, sel_us_etf)
                if res: draw_stock_card(res, api_key_str=api_key_input, is_expanded=True, key_suffix="us_etf")

elif selected_menu == "💰 고배당주 파이프라인 (TOP 300)":
    st.subheader("💰 고배당주 파이프라인 (TOP 300)")
    st.caption("🗓️ **배당주기**는 최근 12개월간 '실제 배당 지급 내역'으로 추정합니다 — 월·분기·반기·연배당. "
               "괄호 안 숫자는 배당이 들어온 '월'입니다 (예: 분기배당(3·6·9·12월)). "
               "한국거래소(pykrx) 공식데이터로 잡힌 종목은 지급일 정보가 없어 통상값인 '연 1회(추정)'로 표기되며, "
               "야후(yfinance)로 조회된 종목은 실제 지급월 기준으로 표시됩니다.")

    hcol1, hcol2 = st.columns([5, 1])
    with hcol2:
        if st.button("🔄 데이터 다시 불러오기", use_container_width=True, key="div_refetch"):
            get_dividend_portfolio.clear()   # 이 함수의 캐시만 비우고 즉시 재조회
            st.rerun()

    with st.spinner("배당 데이터를 다운로드 중입니다..."): 
        div_dfs = get_dividend_portfolio(st.session_state.get('ex_rate', 1350.0))
        
    sort_opt = st.radio("⬇ 정렬 기준", ["기본 (분류순)", "예상 배당금 높은순", "현재가 높은순", "현재가 낮은순"], horizontal=True)
    
    def apply_sort(df, opt):
        if df.empty: return df
        temp_df = df.copy()
        if opt == "기본 (분류순)": return temp_df 
        def ex_val(val_str):
            try: return float(str(val_str).split('(')[0].replace(',', '').replace('원', '').replace('$', '').strip())
            except Exception as _dg_e: _diag_note("ex_val", _dg_e); return 0.0
        sort_col = '예상 배당금' if "배당금" in opt else '현재가'
        temp_df['__sort'] = temp_df[sort_col].apply(lambda x: ex_val(x))
        if opt == "현재가 낮은순": return pd.concat([temp_df[temp_df['__sort']>0].sort_values('__sort'), temp_df[temp_df['__sort']==0]]).drop(columns=['__sort'])
        return temp_df.sort_values('__sort', ascending=False).drop(columns=['__sort'])

    t1, t2, t3 = st.tabs(["🇰🇷 국장", "🇺🇸 미장", "📈 ETF"])
    
    with t1: 
        if div_dfs["KRX"].empty:
            st.error("🚨 국내 주식 배당 데이터를 불러오지 못했습니다.")
            st.caption("• 클라우드(서버) 환경에서는 한국거래소(pykrx)·야후 접속이 일시 차단될 수 있습니다.\n"
                       "• 위의 [🔄 데이터 다시 불러오기]를 눌러 재시도해 주세요. (캐시를 비우고 새로 조회합니다)\n"
                       "• 계속 실패하면 requirements.txt 에 `yfinance`, `pykrx`, `yahooquery` 가 포함됐는지 확인하세요.")
        else:
            st.dataframe(apply_sort(div_dfs["KRX"], sort_opt), use_container_width=True, hide_index=True)
            
    with t2: 
        if div_dfs["US"].empty:
            st.error("🚨 미국 주식 배당 데이터를 가져오지 못했습니다.")
            st.caption("• Yahoo Finance 접속이 일시 제한됐을 수 있습니다. 위의 [🔄 데이터 다시 불러오기]로 재시도해 주세요.\n"
                       "• 계속 실패하면 requirements.txt 에 `yfinance` 설치 여부를 확인하세요.")
        else:
            st.dataframe(apply_sort(div_dfs["US"], sort_opt), use_container_width=True, hide_index=True)
            
    with t3: 
        if div_dfs["ETF"].empty:
            st.error("🚨 ETF 배당 데이터를 가져오지 못했습니다.")
            st.caption("• Yahoo Finance 접속이 일시 제한됐을 수 있습니다. 위의 [🔄 데이터 다시 불러오기]로 재시도해 주세요.\n"
                       "• 계속 실패하면 requirements.txt 에 `yfinance` 설치 여부를 확인하세요.")
        else:
            st.dataframe(apply_sort(div_dfs["ETF"], sort_opt), use_container_width=True, hide_index=True)

elif selected_menu == "🎯 증권사 목표가 컨센서스":
    st.markdown("## 🎯 증권사 목표가 컨센서스")
    st.write("특정 종목에 대한 여러 증권사의 최근 6개월 목표가 추이와 투자의견 분포를 시각적으로 분석합니다.")
    
    krx_df = get_krx_stocks()
    if not krx_df.empty:
        opts = ["🔍 종목을 선택하세요"] + (krx_df['Name'].astype(str) + " (" + krx_df['Code'].astype(str) + ")").tolist()
        cons_query = st.selectbox("컨센서스를 분석할 종목:", opts)
        
        if cons_query != "🔍 종목을 선택하세요":
            q_name = cons_query.rsplit(" (", 1)[0]
            q_code = cons_query.rsplit("(", 1)[-1].replace(")", "").strip()
            
            with st.spinner(f"'{q_name}' 증권사 리포트 및 현재가 데이터 연산 중..."):
                history_df = get_stock_research_history(q_code, q_name)
                # 💡 추가됨: 현재 주가 가져오기
                tech_res = analyze_technical_pattern(q_name, q_code)
                curr_price = int(tech_res['현재가']) if tech_res else 0
            
            if history_df.empty:
                st.warning("최근 6개월 내 발간된 증권사 리포트가 없어 컨센서스를 산출할 수 없습니다.")
            else:
                valid_df = history_df[history_df['적정가격'] > 0].copy()
                
                if valid_df.empty:
                    st.warning("목표가가 제시된 리포트가 없습니다.")
                else:
                    avg_price = int(valid_df['적정가격'].mean())
                    median_price = int(valid_df['적정가격'].median())
                    max_price = int(valid_df['적정가격'].max())
                    min_price = int(valid_df['적정가격'].min())
                    report_count = len(valid_df)
                    
                    max_broker = valid_df[valid_df['적정가격'] == max_price]['증권사'].iloc[0]
                    min_broker = valid_df[valid_df['적정가격'] == min_price]['증권사'].iloc[0]
                    
                    # 💡 추가됨: 현재가 대비 평균 목표가 괴리율(기대수익률) 계산
                    upside_pct = ((avg_price - curr_price) / curr_price * 100) if curr_price > 0 else 0
                    
                    with st.container(border=True):
                        st.markdown(f"### {q_name} <span style='font-size: 16px; color: gray;'>{q_code}</span>", unsafe_allow_html=True)
                        
                        # 💡 수정됨: 6열로 변경하고 맨 앞에 현재 주가 배치
                        c0, c1, c2, c3, c4, c5 = st.columns(6)
                        if curr_price > 0:
                            c0.metric("현재 주가", f"{curr_price:,}원")
                            c1.metric("평균 목표가", f"{avg_price:,}원", f"{upside_pct:+.1f}% (괴리율)", delta_color="normal")
                        else:
                            c0.metric("현재 주가", "조회불가")
                            c1.metric("평균 목표가", f"{avg_price:,}원")
                            
                        c2.metric("중앙값", f"{median_price:,}원", f"증권사 {len(valid_df['증권사'].unique())}곳")
                        c3.metric("최고가", f"{max_price:,}원", max_broker, delta_color="normal")
                        c4.metric("최저가", f"{min_price:,}원", min_broker, delta_color="inverse")
                        c5.metric("수집 리포트", f"{report_count}건")
                        
                    st.divider()
                    
                    col_chart1, col_chart2 = st.columns([7, 3])
                    
                    with col_chart1:
                        st.markdown("#### 📈 목표주가 시계열 (최근 6개월)")
                        valid_df['Date'] = pd.to_datetime(valid_df['작성일'], format="%y.%m.%d")
                        valid_df = valid_df.sort_values('Date')
                        
                        fig_line = px.line(valid_df, x='Date', y='적정가격', color='증권사', markers=True, 
                                           title=f"{q_name} 증권사별 목표가 추이",
                                           labels={"Date": "발간일", "적정가격": "목표주가 (원)"})
                        
                        fig_line.add_hline(y=avg_price, line_dash="dash", line_color="rgba(255,0,0,0.5)", annotation_text=f"평균 {avg_price:,}원")
                        # 💡 추가됨: 차트에 현재 주가 기준선 추가
                        if curr_price > 0:
                            fig_line.add_hline(y=curr_price, line_dash="dot", line_color="rgba(0,0,255,0.5)", annotation_text=f"현재 주가 {curr_price:,}원")
                            
                        fig_line.update_layout(hovermode="x unified", height=400, template="plotly_white")
                        st.plotly_chart(fig_line, use_container_width=True)
                        
                    with col_chart2:
                        st.markdown("#### 📊 투자의견 분포")
                        
                        # 투자의견 표준화 → 파이차트용 라벨(영문 병기). 분류는 전역 헬퍼로 통일.
                        def opinion_pie_label(op):
                            std = standardize_opinion(op)  # '강력매수/매수/중립/매도/N/A'
                            return {
                                '강력매수': '강력매수 (Strong Buy)',
                                '매수': '매수 (Buy)',
                                '중립': '중립 (Hold)',
                                '매도': '매도 (Sell)',
                            }.get(std, str(op).strip().upper())

                        history_df['투자의견_표준화'] = history_df['투자의견'].apply(opinion_pie_label)
                        opinion_counts = history_df['투자의견_표준화'].value_counts().reset_index()
                        opinion_counts.columns = ['투자의견', '건수']
                        
                        fig_pie = px.pie(opinion_counts, values='건수', names='투자의견', hole=0.5,
                                         color='투자의견', 
                                         color_discrete_map={
                                            '강력매수 (Strong Buy)': '#003300', 
                                            '매수 (Buy)': '#1b5e20', 
                                            '중립 (Hold)': '#ff7f0e', 
                                            '매도 (Sell)': '#d62728'
                                         })
                        fig_pie.update_layout(height=400, showlegend=True, legend=dict(orientation="h", yanchor="bottom", y=-0.2, xanchor="center", x=0.5))
                        st.plotly_chart(fig_pie, use_container_width=True)
                        
                    st.markdown("#### 📋 증권사별 최신 컨센서스")
                    latest_df = valid_df.sort_values('Date', ascending=False).drop_duplicates(subset=['증권사'], keep='first')
                    
                    display_latest = latest_df[['증권사', '투자의견', '적정가격', '작성일', '원문링크']].copy()
                    display_latest['적정가격'] = display_latest['적정가격'].apply(lambda x: f"{x:,}원")
                    st.dataframe(
                        display_latest,
                        column_config={"원문링크": st.column_config.LinkColumn("리포트 보기")},
                        use_container_width=True, hide_index=True
                    )
                    
                    st.divider()
                    if api_key_input and st.button(f"🤖 '{q_name}' 애널리스트 갑론을박 (Debate) 분석", type="primary", use_container_width=True):
                        with st.spinner(f"최근 발간된 '{q_name}' 리포트들의 강세/약세 논리를 분석 중입니다..."):
                            report_texts = "\n".join([f"- [{r['증권사']}] 투자의견: {r['투자의견']}, 목표가: {r['적정가격']}\n제목: {r['제목']}" for _, r in history_df.head(10).iterrows()])
                            prompt = f"""
                            당신은 애널리스트입니다. '{q_name}'에 대한 최근 증권사 리포트들을 바탕으로 시장의 '갑론을박(Debate)'을 분석해주세요.
                            [리포트 요약]
                            {report_texts}
                            
                            다음 형식으로 마크다운 작성:
                            1. 🟢 **강세 논리 (Bull Case)**: 긍정적인 전망과 목표가 상향의 주된 근거 (2~3줄)
                            2. 🔴 **약세/보수적 논리 (Bear Case)**: 우려 사항, 리스크, 목표가 하향/유지의 주된 근거 (2~3줄)
                            3. 💡 **핵심 쟁점 (Key Controversy)**: 가장 의견이 엇갈리는 포인트 (1줄)
                            """
                            st.success(ask_gemini(prompt, api_key_input))

elif selected_menu == "⚖️ 적정 주가 계산기 (버핏 모델)":
    st.markdown("## ⚖️ 적정 주가 계산기 (버핏 모델)")
    b_tab1, b_tab2, b_tab3 = st.tabs(["📊 적정 주가 계산기 (DCF 모델)", "📈 버핏 지수 & 72의 법칙", "🔍 퀀트 스크리닝 가이드"])
    
    with b_tab1:
        st.markdown("### 📊 잉여현금흐름(FCF) 기반 내재가치 계산기")
        market_choice_dcf = st.radio("시장 선택 (가치평가)", ["🇰🇷 국내 주식", "🇺🇸 미국 주식"], horizontal=True, key="dcf_market")
        
        # 💡 [버그 수정] Streamlit Rerun 시 화면이 닫히지 않도록 세션 상태(Session State)에 종목 정보 저장
        if 'dcf_sel_ticker' not in st.session_state: st.session_state.dcf_sel_ticker = None
        if 'dcf_sel_name' not in st.session_state: st.session_state.dcf_sel_name = ""
        
        is_us_dcf = (market_choice_dcf == "🇺🇸 미국 주식")
        
        if not is_us_dcf:
            krx_df = get_krx_stocks()
            if not krx_df.empty:
                opts = ["🔍 평가할 국내 종목을 선택하세요."] + (krx_df['Name'].astype(str) + " (" + krx_df['Code'].astype(str) + ")").tolist()
                with st.form("dcf_kr_form"):
                    col_dcf1, col_dcf2 = st.columns([8, 2])
                    with col_dcf1: query = st.selectbox("👇 종목명 검색:", opts, key="dcf_kr_search", label_visibility="collapsed")
                    with col_dcf2: dcf_kr_btn = st.form_submit_button("🔍 데이터 로드", use_container_width=True)
                    if dcf_kr_btn and query != "🔍 평가할 국내 종목을 선택하세요.":
                        st.session_state.dcf_sel_name = query.rsplit(" (", 1)[0]
                        st.session_state.dcf_sel_ticker = query.rsplit("(", 1)[-1].replace(")", "").strip()
        else:
            with st.form("dcf_us_form"):
                col_dcf_us1, col_dcf_us2 = st.columns([8, 2])
                with col_dcf_us1: us_query = st.text_input("👇 미국 주식 종목명/티커 (예: AAPL):", key="dcf_us_input", label_visibility="collapsed")
                with col_dcf_us2: dcf_us_search_btn = st.form_submit_button("🔍 검색", use_container_width=True)
            if dcf_us_search_btn and us_query:
                with st.spinner("검색 중..."): us_results = search_us_ticker(us_query)
                if us_results: st.session_state.dcf_us_results = us_results
                else: st.error("검색 결과가 없습니다.")
            if "dcf_us_results" in st.session_state and st.session_state.dcf_us_results:
                sel_us_opt = st.selectbox("🎯 정확한 종목을 선택해주세요:", ["선택하세요"] + st.session_state.dcf_us_results)
                if sel_us_opt != "선택하세요":
                    st.session_state.dcf_sel_ticker = sel_us_opt.split(" ")[0]
                    st.session_state.dcf_sel_name = sel_us_opt.split(" (")[1].split(" /")[0]

        # 💡 기존 로컬 변수 대신 영구적으로 유지되는 세션 상태 변수 사용
        if st.session_state.dcf_sel_ticker:
            st.success(f"✅ [{st.session_state.dcf_sel_name}] 기초 데이터 로드 완료")
            _, _, fcf_val, shares_val, _ = get_fundamentals(st.session_state.dcf_sel_ticker)
            default_price, res = 0.0, analyze_technical_pattern(st.session_state.dcf_sel_name, st.session_state.dcf_sel_ticker)
            if res: default_price = float(res['현재가'])
            default_fcf = float(fcf_val) if fcf_val and pd.notna(fcf_val) else 1000.0
            default_shares = float(shares_val) if shares_val and pd.notna(shares_val) else 100.0

            st.markdown("#### ⚙️ DCF 파라미터 입력")
            col_dcf_p1, col_dcf_p2 = st.columns(2)
            with col_dcf_p1:
                input_price = st.number_input("현재 주가", value=default_price, step=1.0)
                input_fcf = st.number_input("최근 잉여현금흐름(FCF)", value=default_fcf, step=100.0)
                input_shares = st.number_input("유통 주식수", value=default_shares, step=10.0)
            with col_dcf_p2:
                growth_rate = st.slider("예상 연평균 성장률 (%)", 1.0, 50.0, 10.0)
                discount_rate = st.slider("할인율 (요구수익률) (%)", 5.0, 20.0, 9.0)
                terminal_growth = st.slider("영구 성장률 (%)", 1.0, 5.0, 2.5)

            # 이 버튼을 눌러도 이제 화면이 날아가지 않습니다!
            if st.button("🧮 적정 주가 연산", type="primary", use_container_width=True):
                with st.spinner("미래 현금흐름 할인 연산 중..."):
                    future_fcfs = []
                    current_fcf = input_fcf
                    for i in range(1, 11):
                        current_fcf *= (1 + growth_rate/100)
                        future_fcfs.append(current_fcf / ((1 + discount_rate/100) ** i))
                    
                    terminal_value = (current_fcf * (1 + terminal_growth/100)) / ((discount_rate/100) - (terminal_growth/100))
                    discounted_tv = terminal_value / ((1 + discount_rate/100) ** 10)
                    total_value = sum(future_fcfs) + discounted_tv
                    
                    # 💡 [치명적 버그 수정] FCF(억/10^8)와 주식수(백만/10^6) 단위 스케일링을 위해 100을 곱함
                    fair_price = (total_value / input_shares) * 100 if input_shares > 0 else 0
                    
                    margin_of_safety = ((fair_price - input_price) / fair_price) * 100 if fair_price > 0 else 0
                    
                    st.divider()
                    st.markdown(f"### 🎯 [{st.session_state.dcf_sel_name}] DCF 가치평가 결과")
                    c1, c2, c3 = st.columns(3)
                    c1.metric("현재 주가", f"{input_price:,.2f}")
                    c2.metric("DCF 적정 주가", f"{fair_price:,.2f}")
                    c3.metric("안전 마진", f"{margin_of_safety:+.1f}%", delta_color="normal" if margin_of_safety > 0 else "inverse")
                    
                    if margin_of_safety > 20: st.success("🟢 **강력 매수 구간**: 현재 주가가 내재가치 대비 20% 이상 저렴합니다.")
                    elif margin_of_safety > 0: st.info("🔵 **매수 구간**: 현재 주가가 내재가치보다 저렴합니다.")
                    elif margin_of_safety > -20: st.warning("🟡 **적정 가치 구간**: 주가가 내재가치와 비슷하게 형성되어 있습니다.")
                    else: st.error("🔴 **고평가 구간**: 현재 주가가 미래 성장성을 이미 과도하게 반영하고 있을 수 있습니다.")

    with b_tab2:
        st.markdown("### 📈 버핏 지수 (Buffett Indicator)")
        st.write("국가의 시가총액을 명목 GDP로 나눈 값으로, 증시 전체의 고평가/저평가 여부를 판단합니다.")
        buffett_ratio = 115.5 
        st.metric("현재 한국 증시 추정 버핏 지수", f"{buffett_ratio}%")
        if buffett_ratio > 120: st.error("🚨 증시가 역사적 고평가 상태입니다. 현금 비중을 늘리는 것을 고려하세요.")
        elif buffett_ratio > 80: st.success("✅ 시장이 적정 가치 구간에 있습니다.")
        else: st.info("💰 시장이 저평가 상태입니다. 적극적인 매수 기회일 수 있습니다.")
            
        st.divider()
        st.markdown("### ⏱️ 복리 계산기 (72의 법칙)")
        return_rate = st.slider("목표 연평균 수익률 (%)", min_value=1.0, max_value=30.0, value=15.0, step=0.5)
        years_to_double = 72 / return_rate
        st.markdown(f"👉 연수익률 **{return_rate}%** 유지 시, 원금이 2배가 되는 데 약 **<span style='color:#ff4b4b; font-size:24px;'>{years_to_double:.1f}년</span>**이 걸립니다.", unsafe_allow_html=True)

    with b_tab3:
        st.markdown("### 🔍 퀀트식 버핏 전략 스크리닝 기준")
        st.info("실제 시중 퀀트 플랫폼(퀀터스 등)에서 워런 버핏 스타일의 알짜 가치주를 찾기 위해 설정해야 하는 검색 조건식 가이드입니다.")
        st.markdown("""
        1. **ROE (자기자본이익률)**: 과거 3~5년 평균 **15% 이상** 꾸준히 유지
        2. **영업이익률**: 동종 업계 평균 대비 우위 (최소 **10% 이상**)
        3. **부채비율**: **100% 이하** (금융업 제외)
        4. **FCF (잉여현금흐름)**: 최근 3년 연속 **흑자** 및 증가 추세
        5. **PBR (주가순자산비율)**: 가급적 **1.5 이하** (절대적 기준은 아니며 ROE와 결합하여 판단)
        6. **경제적 해자**: 위 1~5번이 숫자로 증명되며, 브랜드 파워나 독점적 기술력(워런 버핏의 '소비자 독점 기업')을 가진 기업
        """)

elif selected_menu == "👴 노후 준비 ETF 시뮬레이터 (v2.0)":
    st.markdown("## 👴 노후 준비 ETF 시뮬레이터 (v2.0)")
    st.write("절세 계좌(연금저축/IRP/ISA) 활용법과 테마별 ETF 조합을 통해 은퇴 후 현금흐름을 설계합니다.")

    # --- 1. 절세 계좌 자동 배분 계산기 ---
    st.markdown("### 🎯 1. 월 투자금액별 절세 계좌 배분 최적화 가이드")
    
    st.info("""
    **💡 노후 자금은 왜 반드시 이 순서대로 계좌를 채워야 할까요? (절세 극대화 룰)**
    1. **1순위: 연금저축펀드 (연 600만 원 우선)** - 세액공제 및 수익률 극대화에 가장 유리합니다.
    2. **2순위: IRP (연 300만 원 추가)** - 연금저축과 합산해 총 900만 원까지 세액공제를 받습니다.
    3. **3순위: 중개형 ISA (연 2,000만 원 한도)** - 수익의 200~400만 원까지 비과세 혜택을 줍니다.
    4. **4순위: 일반/해외계좌** - 국가 절세 혜택을 소진한 뒤 남는 여유 현금을 굴리는 계좌입니다.
    """)

    with st.container(border=True):
        col_in, col_spacer = st.columns([2, 1])
        monthly_budget = col_in.number_input("월 총 노후대비 투자 가능 금액 (원)", min_value=0, step=100000, value=0)
        
        temp_budget = monthly_budget
        pension = min(500000, temp_budget) 
        temp_budget -= pension
        irp = min(250000, temp_budget)    
        temp_budget -= irp
        isa = min(1666666, temp_budget)   
        normal = max(0, temp_budget - isa)

        c1, c2, c3, c4 = st.columns(4)
        c1.metric("연금저축펀드", f"{int(pension):,}원", "연 600만 한도")
        c2.metric("IRP (퇴직연금)", f"{int(irp):,}원", "합산 900만 한도")
        c3.metric("중개형 ISA", f"{int(isa):,}원", "비과세 혜택")
        c4.metric("일반/해외계좌", f"{int(normal):,}원", "한도 초과분")

    # 👇 네이버 금융 실시간 API 직결 엔진
    @st.cache_data(ttl=3600)
    def get_naver_etf_and_stocks():
        res_dfs = []
        try:
            url = "https://finance.naver.com/api/sise/etfItemList.nhn"
            res = requests.get(url, timeout=5)
            if res.status_code == 200:
                etf_list = res.json().get('result', {}).get('etfItemList', [])
                if etf_list:
                    df_etf = pd.DataFrame(etf_list)[['itemcode', 'itemname', 'nowVal']].rename(
                        columns={'itemcode': 'Code', 'itemname': 'Name', 'nowVal': 'Price'})
                    res_dfs.append(df_etf)
        except Exception as _dg_e: _diag_note("get_naver_etf_and_stocks", _dg_e); pass
        try:
            df_stocks = fdr.StockListing('KRX')
            if not df_stocks.empty:
                df_s = df_stocks[['Code', 'Name', 'Close']].rename(columns={'Close': 'Price'}) if 'Close' in df_stocks.columns else df_stocks[['Code', 'Name']].assign(Price=0)
                res_dfs.append(df_s)
        except Exception as _dg_e: _diag_note("get_naver_etf_and_stocks", _dg_e); pass
        if res_dfs:
            df_final = pd.concat(res_dfs, ignore_index=True)
            df_final['Code'] = df_final['Code'].astype(str).str.zfill(6)
            df_final['Price'] = pd.to_numeric(df_final['Price'], errors='coerce').fillna(0)
            return df_final.sort_values('Price', ascending=False).drop_duplicates(subset=['Code']).reset_index(drop=True)
        return pd.DataFrame(columns=['Code', 'Name', 'Price'])

    # 고정 테마 대배열 명단 (맞춤 종목 메뉴 최하단 고정)
    theme_order = [
        "🌐 1. 시장 대표 지수 코어", 
        "💻 2. 반도체 & 빅테크 핵심 성장", 
        "🤖 3. AI·로봇 & 사이버보안 혁신",
        "🚀 4. 방산 & 우주항공 미래 테크",
        "🏦 5. 금융 지주 & 밸류업 모멘텀",
        "💰 6. 고배당 & 월배당 인컴 밸류업", 
        "🛡️ 7. 안전자산 채권 & 원자재 방어",
        "🌍 8. 해외 직상장 글로벌 메이저",
        "🚢 9. 조선 & 해운 슈퍼사이클",
        "⚡ 10. 전력 인프라 & 글로벌 에너지",
        "🔎 내가 추가한 맞춤 종목"
    ]

    # --- 2. 스마트 맞춤 종목 다중 검색 ---
    if 'custom_etfs' not in st.session_state or (len(st.session_state.custom_etfs) > 0 and isinstance(st.session_state.custom_etfs[0], str)):
        st.session_state.custom_etfs = []
    if 'search_query' not in st.session_state: st.session_state.search_query = ""

    st.markdown("### 🔎 2. 맞춤형 종목 검색 및 추가")
    with st.container(border=True):
        st.markdown("**✨ 원하는 종목을 직접 찾아 내 포트폴리오에 담아보세요.**")
        
        cols = st.columns([4, 1], vertical_alignment="bottom")
        with cols[0]:
            search_input = st.text_input(
                "검색어 입력", 
                placeholder=" 🔍 검색어를 입력하세요. (예: 반도체, 삼성전자, SCHD)", 
                label_visibility="collapsed"
            ).strip()
        with cols[1]:
            search_clicked = st.button("종목 검색", type="primary", use_container_width=True)

        if search_clicked:
            if search_input: st.session_state.search_query = search_input
            else: st.warning("⚠️ 검색어를 먼저 입력해주세요!")

        if st.session_state.search_query:
            query = st.session_state.search_query
            search_options = []
            with st.spinner("데이터베이스에서 종목을 찾는 중입니다..."):
                kr_assets_df = get_naver_etf_and_stocks()
                if not kr_assets_df.empty:
                    matches = kr_assets_df[kr_assets_df['Name'].str.contains(query, case=False, na=False)]
                    for _, row in matches.iterrows(): search_options.append(f"{row['Name']} [{row['Code']}]")
                if re.search('[a-zA-Z]', query):
                    try:
                        us_results = search_us_ticker(query)
                        if us_results:
                            for res in us_results:
                                search_options.append(f"{res.split(' (')[1].split(' /')[0]} [{res.split(' ')[0]}]")
                    except Exception as _dg_e: _diag_note("<module>", _dg_e); pass
            
            st.divider()
            if search_options:
                with st.form(key="add_stock_form", clear_on_submit=True):
                    st.success(f"🎉 '{query}' 검색 결과 총 **{len(search_options)}개**를 찾았습니다!")
                    selected_to_add = st.multiselect("👇 결과 목록에서 장바구니에 담을 종목을 모두 골라주세요:", options=search_options)
                    submit_btn = st.form_submit_button("🛒 선택한 종목 포트폴리오에 추가하기", use_container_width=True)
                    
                    if submit_btn:
                        if selected_to_add:
                            added_count = 0
                            for sel in selected_to_add:
                                parts = sel.split(" [")
                                parsed_name, parsed_code = parts[0].strip(), parts[1].replace("]", "").strip()
                                if not any(item['code'] == parsed_code for item in st.session_state.custom_etfs):
                                    # 👇 [핵심 조치 1] 다른 테마로 숨지 않도록 강제로 "🔎 내가 추가한 맞춤 종목" 메뉴로 배치
                                    st.session_state.custom_etfs.append({
                                        'theme': "🔎 내가 추가한 맞춤 종목", 
                                        'name': parsed_name, 
                                        'code': parsed_code, 
                                        'holdings': '관심 종목 (아래 버튼으로 편입종목을 확인하세요)'
                                    })
                                    added_count += 1
                            if added_count > 0: st.toast(f"✅ {added_count}개 종목 추가 완료!", icon="✅")
                            st.session_state.search_query = ""
                            st.rerun()
                        else: st.warning("⚠️ 추가할 종목을 위에서 먼저 선택해주세요.")
            else: st.error("앗! 검색 결과가 없습니다. 🥲")

    # 👇 고정 마스터 리스트 (6번 항목 미국 배당주 통합)
    raw_etf_data = [
        {"theme": "🌐 1. 시장 대표 지수 코어", "code": "069500", "name": "KODEX 200"},
        {"theme": "🌐 1. 시장 대표 지수 코어", "code": "102110", "name": "TIGER 200"},
        {"theme": "🌐 1. 시장 대표 지수 코어", "code": "229200", "name": "KODEX 코스닥150"},
        {"theme": "🌐 1. 시장 대표 지수 코어", "code": "360750", "name": "TIGER 미국S&P500"},
        {"theme": "🌐 1. 시장 대표 지수 코어", "code": "360200", "name": "ACE 미국S&P500"},
        {"theme": "🌐 1. 시장 대표 지수 코어", "code": "379780", "name": "RISE 미국S&P500"},
        {"theme": "🌐 1. 시장 대표 지수 코어", "code": "379800", "name": "KODEX 미국S&P500TR"},
        {"theme": "🌐 1. 시장 대표 지수 코어", "code": "133690", "name": "TIGER 미국나스닥100"},
        {"theme": "🌐 1. 시장 대표 지수 코어", "code": "379810", "name": "KODEX 미국나스닥100TR"},
        {"theme": "🌐 1. 시장 대표 지수 코어", "code": "453810", "name": "KODEX 인도Nifty50"},
        {"theme": "🌐 1. 시장 대표 지수 코어", "code": "241180", "name": "TIGER 일본니케이225"},

        {"theme": "💻 2. 반도체 & 빅테크 핵심 성장", "code": "381180", "name": "TIGER 미국테크TOP10 INDXX"},
        {"theme": "💻 2. 반도체 & 빅테크 핵심 성장", "code": "381170", "name": "TIGER 미국필라델피아반도체나스닥"},
        {"theme": "💻 2. 반도체 & 빅테크 핵심 성장", "code": "441680", "name": "ACE 글로벌반도체TOP4 Plus SOLACTIVE"},
        {"theme": "💻 2. 반도체 & 빅테크 핵심 성장", "code": "091160", "name": "KODEX 반도체"},
        {"theme": "💻 2. 반도체 & 빅테크 핵심 성장", "code": "091230", "name": "TIGER 반도체"},
        {"theme": "💻 2. 반도체 & 빅테크 핵심 성장", "code": "455850", "name": "SOL 반도체소부장Fn"},
        {"theme": "💻 2. 반도체 & 빅테크 핵심 성장", "code": "305720", "name": "KODEX 2차전지산업"},
        {"theme": "💻 2. 반도체 & 빅테크 핵심 성장", "code": "305540", "name": "TIGER 2차전지테마"},

        {"theme": "🤖 3. AI·로봇 & 사이버보안 혁신", "code": "456600", "name": "TIMEFOLIO 글로벌AI인공지능액티브"},
        {"theme": "🤖 3. AI·로봇 & 사이버보안 혁신", "code": "445290", "name": "KODEX 로봇액티브"},
        {"theme": "🤖 3. AI·로봇 & 사이버보안 혁신", "code": "462330", "name": "KODEX 로보틱스"},
        {"theme": "🤖 3. AI·로봇 & 사이버보안 혁신", "code": "469070", "name": "ACE AI로봇핵심장비TOP4플러스"},
        {"theme": "🤖 3. AI·로봇 & 사이버보안 혁신", "code": "411420", "name": "TIGER 글로벌사이버보안INDXX"},
        {"theme": "🤖 3. AI·로봇 & 사이버보안 혁신", "code": "276990", "name": "KODEX 글로벌4차산업로보틱스(합성)"},
        {"theme": "🤖 3. AI·로봇 & 사이버보안 혁신", "code": "275980", "name": "TIGER 글로벌4차산업혁신기술(합성 H)"},

        {"theme": "🚀 4. 방산 & 우주항공 미래 테크", "code": "449450", "name": "PLUS K방산"},
        {"theme": "🚀 4. 방산 & 우주항공 미래 테크", "code": "463250", "name": "TIGER K방산&우주"},
        {"theme": "🚀 4. 방산 & 우주항공 미래 테크", "code": "421320", "name": "PLUS 우주항공&UAM"},
        {"theme": "🚀 4. 방산 & 우주항공 미래 테크", "code": "440910", "name": "WON 미국우주항공방산"},

        {"theme": "🏦 5. 금융 지주 & 밸류업 모멘텀", "code": "466950", "name": "TIGER 은행고배당플러스TOP10"},
        {"theme": "🏦 5. 금융 지주 & 밸류업 모멘텀", "code": "474220", "name": "KODEX 은행고배당플러스"},
        {"theme": "🏦 5. 금융 지주 & 밸류업 모멘텀", "code": "091170", "name": "KODEX 은행"},
        {"theme": "🏦 5. 금융 지주 & 밸류업 모멘텀", "code": "287330", "name": "RISE 금융지주"},
        {"theme": "🏦 5. 금융 지주 & 밸류업 모멘텀", "code": "494330", "name": "KODEX 코리아밸류업"},
        {"theme": "🏦 5. 금융 지주 & 밸류업 모멘텀", "code": "494340", "name": "TIGER 코리아밸류업"},
        {"theme": "🏦 5. 금융 지주 & 밸류업 모멘텀", "code": "492500", "name": "RISE 현대차그룹밸류업모멘텀"},
        {"theme": "🏦 5. 금융 지주 & 밸류업 모멘텀", "code": "466810", "name": "ACE 주주환원가치주액티브"},
        {"theme": "🏦 5. 금융 지주 & 밸류업 모멘텀", "code": "157500", "name": "TIGER 증권"},

        {"theme": "💰 6. 고배당 & 월배당 인컴 밸류업", "code": "458730", "name": "TIGER 미국배당다우존스"},
        {"theme": "💰 6. 고배당 & 월배당 인컴 밸류업", "code": "488210", "name": "KODEX 미국배당다우존스"},
        {"theme": "💰 6. 고배당 & 월배당 인컴 밸류업", "code": "446720", "name": "SOL 미국배당다우존스"},
        {"theme": "💰 6. 고배당 & 월배당 인컴 밸류업", "code": "210780", "name": "TIGER 코스피고배당"},
        {"theme": "💰 6. 고배당 & 월배당 인컴 밸류업", "code": "276970", "name": "KODEX 고배당"},
        {"theme": "💰 6. 고배당 & 월배당 인컴 밸류업", "code": "461580", "name": "TIGER 미국배당+7%프리미엄다우존스"},
        {"theme": "💰 6. 고배당 & 월배당 인컴 밸류업", "code": "SCHD", "name": "Schwab US Dividend Equity ETF"},
        {"theme": "💰 6. 고배당 & 월배당 인컴 밸류업", "code": "JEPI", "name": "JPMorgan Equity Premium Income ETF"},
        {"theme": "💰 6. 고배당 & 월배당 인컴 밸류업", "code": "JEPQ", "name": "JPMorgan Nasdaq Equity Premium Income ETF"},
        {"theme": "💰 6. 고배당 & 월배당 인컴 밸류업", "code": "O", "name": "Realty Income Corp"},
        {"theme": "💰 6. 고배당 & 월배당 인컴 밸류업", "code": "MAIN", "name": "Main Street Capital"},
        {"theme": "💰 6. 고배당 & 월배당 인컴 밸류업", "code": "VIG", "name": "Vanguard Dividend Appreciation ETF"},
        {"theme": "💰 6. 고배당 & 월배당 인컴 밸류업", "code": "VYM", "name": "Vanguard High Dividend Yield ETF"},
        {"theme": "💰 6. 고배당 & 월배당 인컴 밸류업", "code": "DGRW", "name": "WisdomTree US Quality Dividend Growth"},
        {"theme": "💰 6. 고배당 & 월배당 인컴 밸류업", "code": "SDY", "name": "SPDR S&P Dividend ETF"},
        {"theme": "💰 6. 고배당 & 월배당 인컴 밸류업", "code": "MO", "name": "Altria Group Inc"},
        {"theme": "💰 6. 고배당 & 월배당 인컴 밸류업", "code": "PM", "name": "Philip Morris International"},
        {"theme": "💰 6. 고배당 & 월배당 인컴 밸류업", "code": "VZ", "name": "Verizon Communications"},
        {"theme": "💰 6. 고배당 & 월배당 인컴 밸류업", "code": "T", "name": "AT&T Inc"},
        {"theme": "💰 6. 고배당 & 월배당 인컴 밸류업", "code": "CVX", "name": "Chevron Corp"},
        {"theme": "💰 6. 고배당 & 월배당 인컴 밸류업", "code": "XOM", "name": "Exxon Mobil Corp"},
        {"theme": "💰 6. 고배당 & 월배당 인컴 밸류업", "code": "PEP", "name": "PepsiCo Inc"},
        {"theme": "💰 6. 고배당 & 월배당 인컴 밸류업", "code": "KO", "name": "Coca-Cola Co"},
        {"theme": "💰 6. 고배당 & 월배당 인컴 밸류업", "code": "PG", "name": "Procter & Gamble Co"},
        {"theme": "💰 6. 고배당 & 월배당 인컴 밸류업", "code": "ABBV", "name": "AbbVie Inc"},
        {"theme": "💰 6. 고배당 & 월배당 인컴 밸류업", "code": "PFE", "name": "Pfizer Inc"},
        {"theme": "💰 6. 고배당 & 월배당 인컴 밸류업", "code": "MMM", "name": "3M Co"},
        {"theme": "💰 6. 고배당 & 월배당 인컴 밸류업", "code": "IBM", "name": "International Business Machines"},
        {"theme": "💰 6. 고배당 & 월배당 인컴 밸류업", "code": "HD", "name": "Home Depot Inc"},
        {"theme": "💰 6. 고배당 & 월배당 인컴 밸류업", "code": "LOW", "name": "Lowe's Companies Inc"},
        {"theme": "💰 6. 고배당 & 월배당 인컴 밸류업", "code": "CSCO", "name": "Cisco Systems Inc"},
        {"theme": "💰 6. 고배당 & 월배당 인컴 밸류업", "code": "TLT", "name": "iShares 20+ Year Treasury Bond ETF"},
        {"theme": "💰 6. 고배당 & 월배당 인컴 밸류업", "code": "DIVO", "name": "Amplify CWP Strategic Focus Equity ETF"},
        {"theme": "💰 6. 고배당 & 월배당 인컴 밸류업", "code": "STAG", "name": "STAG Industrial Inc"},
        {"theme": "💰 6. 고배당 & 월배당 인컴 밸류업", "code": "VICI", "name": "VICI Properties Inc"},
        {"theme": "💰 6. 고배당 & 월배당 인컴 밸류업", "code": "ADC", "name": "Agree Realty Corp"},

        {"theme": "🛡️ 7. 안전자산 채권 & 원자재 방어", "code": "273130", "name": "KODEX 종합채권(AA-이상)액티브"},
        {"theme": "🛡️ 7. 안전자산 채권 & 원자재 방어", "code": "423160", "name": "KODEX KOFR금리액티브(합성)"},
        {"theme": "🛡️ 7. 안전자산 채권 & 원자재 방어", "code": "411060", "name": "ACE KRX금현물"},
        {"theme": "🛡️ 7. 안전자산 채권 & 원자재 방어", "code": "132030", "name": "KODEX 골드선물(H)"},
        {"theme": "🛡️ 7. 안전자산 채권 & 원자재 방어", "code": "138900", "name": "TIGER 구리선물(H)"},
        {"theme": "🛡️ 7. 안전자산 채권 & 원자재 방어", "code": "153130", "name": "KODEX 단기채권"},

        {"theme": "🌍 8. 해외 직상장 글로벌 메이저", "code": "SPY", "name": "SPDR S&P 500"},
        {"theme": "🌍 8. 해외 직상장 글로벌 메이저", "code": "VOO", "name": "Vanguard S&P 500"},
        {"theme": "🌍 8. 해외 직상장 글로벌 메이저", "code": "QQQ", "name": "Invesco QQQ"},
        {"theme": "🌍 8. 해외 직상장 글로벌 메이저", "code": "SOXX", "name": "iShares Semiconductor"},

        {"theme": "🚢 9. 조선 & 해운 슈퍼사이클", "code": "091180", "name": "KODEX 조선"},
        {"theme": "🚢 9. 조선 & 해운 슈퍼사이클", "code": "380960", "name": "HANARO Fn조선해운"},
        {"theme": "🚢 9. 조선 & 해운 슈퍼사이클", "code": "466920", "name": "SOL 조선TOP3플러스"},

        {"theme": "⚡ 10. 전력 인프라 & 글로벌 에너지", "code": "226490", "name": "KODEX 에너지화학"},
        {"theme": "⚡ 10. 전력 인프라 & 글로벌 에너지", "code": "117460", "name": "TIGER 에너지화학"},
        {"theme": "⚡ 10. 전력 인프라 & 글로벌 에너지", "code": "442320", "name": "RISE 글로벌원자력"},
        {"theme": "⚡ 10. 전력 인프라 & 글로벌 에너지", "code": "418650", "name": "HANARO 글로벌수소&차세대연료전지"},
        {"theme": "⚡ 10. 전력 인프라 & 글로벌 에너지", "code": "385600", "name": "KODEX K-신재생에너지액티브"},
        {"theme": "⚡ 10. 전력 인프라 & 글로벌 에너지", "code": "XLU", "name": "Utilities Select Sector SPDR"},
        {"theme": "⚡ 10. 전력 인프라 & 글로벌 에너지", "code": "ICLN", "name": "iShares Global Clean Energy"}
    ]

    # 공식 명칭 동기화 및 덮어쓰기
    @st.cache_data(ttl=86400)
    def update_official_names(items):
        try:
            krx_df = get_naver_etf_and_stocks()
            krx_name_map = dict(zip(krx_df['Code'], krx_df['Name'])) if not krx_df.empty else {}
            us_tickers = [it['code'] for it in items if not (len(str(it['code'])) == 6 and any(char.isdigit() for char in str(it['code'])))]
            us_name_map = {}
            import yfinance as yf
            import concurrent.futures
            def get_us_name(ticker):
                try:
                    info = yf.Ticker(ticker).info
                    return ticker, info.get('longName', info.get('shortName', ticker))
                except Exception as _dg_e: _diag_note("get_us_name", _dg_e); return ticker, ticker
            if us_tickers:
                with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
                    for code, name in executor.map(get_us_name, us_tickers): us_name_map[code] = name
            updated_items = []
            for it in items:
                new_it = it.copy()
                code = str(it['code']).zfill(6) if str(it['code']).isdigit() else str(it['code'])
                is_kr = len(code) == 6 and code.isdigit()
                if is_kr and code in krx_name_map: new_it['name'] = krx_name_map[code]
                elif not is_kr and code in us_name_map and us_name_map[code] != code: new_it['name'] = us_name_map[code]
                new_it['code'] = code
                updated_items.append(new_it)
            return updated_items
        except Exception as _dg_e: _diag_note("update_official_names", _dg_e); return items 

    etf_data = update_official_names(raw_etf_data)
    for item in etf_data:
        item.update({"price": 0, "cagr": "데이터없음", "list_date": "데이터없음", "holdings": "해당 테마 핵심 우량종목 (아래 버튼으로 검색 가능)"})

    # 사용자가 직접 추가한 종목도 리스트에 이식
    for custom_item in st.session_state.custom_etfs:
        if not any(item['code'] == custom_item['code'] for item in etf_data):
            etf_data.append({
                "theme": "🔎 내가 추가한 맞춤 종목",  # 무조건 고정
                "name": custom_item['name'], 
                "code": custom_item['code'], 
                "price": 0, 
                "cagr": "데이터없음", 
                "list_date": "데이터없음", 
                "holdings": "관심 종목 (아래 버튼으로 편입종목 검색 가능)"
            })

    # 👇 실시간 가격 및 백데이터 로딩 엔진
    import yfinance as yf
    import concurrent.futures
    @st.cache_data(ttl=3600)
    def fetch_realtime_data(codes, ex_rate):
        prices, cagrs = {}, {}
        kr_codes = [c for c in codes if len(str(c)) == 6 and any(char.isdigit() for char in str(c))]
        us_codes = [c for c in codes if c not in kr_codes]
        
        # 1) 국내 실시간 가격
        bulk_krx = get_naver_etf_and_stocks()
        if not bulk_krx.empty:
            p_dict = dict(zip(bulk_krx['Code'], bulk_krx['Price']))
            for c in kr_codes:
                if c in p_dict and int(p_dict[c]) > 0: prices[c] = int(p_dict[c])

        # 1-B) [0원 방어] 일괄 조회에서 누락(0원)된 국내 종목만 개별 보강
        def get_kr_price_fallback(c):
            # (a) 네이버 차트 API의 가장 최근 종가를 현재가로 사용
            try:
                url = f"https://fchart.stock.naver.com/sise.nhn?symbol={c}&timeframe=day&count=5&requestType=0"
                res = requests.get(url, headers={'User-Agent': 'Mozilla/5.0'}, timeout=5)
                if res.status_code == 200:
                    soup = BeautifulSoup(res.text, 'html.parser')
                    items = soup.find_all('item')
                    if items:
                        last_close = float(items[-1].get('data').split('|')[4])
                        if last_close > 0:
                            return c, int(last_close)
            except Exception as _dg_e: _diag_note("get_kr_price_fallback", _dg_e); pass
            # (b) FinanceDataReader 최근 종가로 2차 보강
            try:
                df = fdr.DataReader(c)
                if not df.empty:
                    last_close = float(df['Close'].iloc[-1])
                    if last_close > 0:
                        return c, int(last_close)
            except Exception as _dg_e: _diag_note("get_kr_price_fallback", _dg_e); pass
            return c, 0

        missing_kr = [c for c in kr_codes if prices.get(c, 0) == 0]
        if missing_kr:
            with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
                for c, p in executor.map(get_kr_price_fallback, missing_kr):
                    if p > 0: prices[c] = p

        # 2) 국내 백데이터
        def get_kr_historical_info(c):
            try:
                url = f"https://fchart.stock.naver.com/sise.nhn?symbol={c}&timeframe=month&count=1200&requestType=0"
                res = requests.get(url, headers={'User-Agent': 'Mozilla/5.0'}, timeout=5)
                if res.status_code == 200:
                    soup = BeautifulSoup(res.text, 'html.parser')
                    items = soup.find_all('item')
                    if len(items) > 12:
                        first_date, last_date = items[0].get('data').split('|')[0], items[-1].get('data').split('|')[0]
                        p_start, p_end = float(items[0].get('data').split('|')[4]), float(items[-1].get('data').split('|')[4])
                        days = (pd.to_datetime(last_date) - pd.to_datetime(first_date)).days
                        if days >= 365 and p_start > 0:
                            cagr = ((p_end / p_start) ** (365.25 / days) - 1) * 100
                            return c, round(cagr, 2), pd.to_datetime(first_date).strftime('%Y-%m-%d')
            except Exception as _dg_e: _diag_note("get_kr_historical_info", _dg_e); pass
            try:
                df = fdr.DataReader(c)
                if len(df) > 250:
                    p_start, p_end = float(df['Close'].iloc[0]), float(df['Close'].iloc[-1])
                    days = (df.index[-1] - df.index[0]).days
                    if days >= 365 and p_start > 0:
                        cagr = ((p_end / p_start) ** (365.25 / days) - 1) * 100
                        return c, round(cagr, 2), df.index[0].strftime('%Y-%m-%d')
            except Exception as _dg_e: _diag_note("get_kr_historical_info", _dg_e); pass
            return c, 0.0, "데이터없음"

        if kr_codes:
            with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
                for c, cg, dt in executor.map(get_kr_historical_info, kr_codes):
                    if dt != "데이터없음": cagrs[c] = {'cagr': cg, 'date': dt}

        # 3) 미국 실시간 가격 및 백데이터
        def get_us_info(c):
            try:
                hist = yf.Ticker(c).history(period="max", interval="1mo")
                if not hist.empty:
                    p = float(hist['Close'].iloc[-1])
                    p_start = float(hist['Close'].iloc[0])
                    days = (hist.index[-1] - hist.index[0]).days
                    cagr = ((p / p_start) ** (365.25 / days) - 1) * 100 if days > 365 else 0
                    return c, int(p * ex_rate), round(cagr, 2), hist.index[0].strftime('%Y-%m-%d')
            except Exception as _dg_e: _diag_note("get_us_info", _dg_e); pass
            return c, 0, 0, "데이터없음"

        if us_codes:
            with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
                for c, p, cg, dt in executor.map(get_us_info, us_codes):
                    if p > 0: prices[c] = p
                    if cg != 0: cagrs[c] = {'cagr': cg, 'date': dt}
        return prices, cagrs

    with st.spinner("최신 마켓 데이터를 전수 매칭하는 중입니다..."):
        ex_rate = st.session_state.get('ex_rate', 1350.0)
        # [v7.0] 잘못된/리브랜딩된 코드 자동 보정 (이름 기준 실시간 목록 매칭)
        resolve_etf_codes(etf_data, get_naver_etf_and_stocks())
        real_prices, real_cagrs = fetch_realtime_data([item['code'] for item in etf_data], ex_rate)
        for item in etf_data:
            if item['code'] in real_prices: item['price'] = real_prices[item['code']]
            if item['code'] in real_cagrs:
                item['cagr'], item['list_date'] = real_cagrs[item['code']]['cagr'], real_cagrs[item['code']]['date']

    # --- 3. 포트폴리오 구성 UI ---
    st.markdown("### 🛒 3. 나만의 노후 포트폴리오 담기")
    if 'retirement_cart' not in st.session_state: st.session_state.retirement_cart = {}

    for theme in theme_order:
        theme_stocks = [item for item in etf_data if item['theme'] == theme]
        seen = set()
        unique_stocks = [s for s in theme_stocks if s['code'] not in seen and not seen.add(s['code'])]

        if unique_stocks:
            with st.expander(f"{theme} 선택", expanded=False):
                for idx, stock in enumerate(unique_stocks):
                    cols = st.columns([3, 1.5, 1.5, 1.5, 1.5, 1]) 
                    
                    with cols[0]: 
                        st.markdown(f"**{stock['name']}** ({stock['code']})")
                        
                        # 👇 [핵심 조치 2] 제한 없이 "모든 종목"에 대해 AI 편입종목 검색 기능 제공
                        current_holdings = st.session_state.get(f"holdings_{stock['code']}", stock['holdings'])
                        st.caption(f"🔍 {current_holdings}")
                        
                        if "💡 AI" not in current_holdings:
                            if st.button("🤖 편입종목 검색", key=f"ai_h_{stock['code']}_{idx}"):
                                if not api_key_input:
                                    st.error("좌측 사이드바에 API 키를 입력해주세요.")
                                else:
                                    with st.spinner("AI가 편입 종목을 분석 중입니다..."):
                                        ai_prompt = f"주식/ETF '{stock['name']} ({stock['code']})'가 가장 많이 편입하고 있는 핵심 종목 5~10개를 쉼표로 나열해줘. 다른 말은 하지 마."
                                        ai_holdings = ask_gemini(ai_prompt, api_key_input)
                                        st.session_state[f"holdings_{stock['code']}"] = "💡 AI 분석: " + ai_holdings
                                        st.rerun()

                    cols[1].markdown(f"현재가:<br>{stock['price']:,}원", unsafe_allow_html=True)
                    cols[2].markdown(f"상장일:<br>{stock.get('list_date', '데이터없음')}", unsafe_allow_html=True)
                    c_val = stock['cagr']
                    cols[3].markdown(f"수익률:<br>{c_val}%" if isinstance(c_val, (int, float)) else f"수익률:<br>{c_val}", unsafe_allow_html=True)
                    
                    qty = cols[4].number_input("수량", min_value=0, step=1, key=f"ret_qty_{theme}_{stock['code']}_{idx}", label_visibility="collapsed")
                    if qty > 0: st.session_state.retirement_cart[stock['code']] = {"name": stock['name'], "qty": qty, "price": stock['price'], "cagr": stock['cagr'] if isinstance(stock['cagr'], (int, float)) else 0}
                    elif stock['code'] in st.session_state.retirement_cart: del st.session_state.retirement_cart[stock['code']]
                    
                    # 맞춤 종목만 삭제 버튼 활성화
                    is_custom = any(c['code'] == stock['code'] for c in st.session_state.custom_etfs)
                    if is_custom:
                        if cols[5].button("🗑️ 삭제", key=f"del_{theme}_{stock['code']}_{idx}"):
                            st.session_state.custom_etfs = [x for x in st.session_state.custom_etfs if x['code'] != stock['code']]
                            if stock['code'] in st.session_state.retirement_cart: del st.session_state.retirement_cart[stock['code']]
                            st.rerun()

    # --- 4. 시뮬레이션 대시보드 ---
    st.divider()
    st.markdown("### 📊 4. 복리 성장 & 노후 현금흐름 시뮬레이션")
    cart = st.session_state.retirement_cart
    if cart:
        total_p = sum(v['qty'] * v['price'] for v in cart.values())
        w_cagr = sum(v['qty'] * v['price'] * v['cagr'] for v in cart.values()) / total_p if total_p > 0 else 0

        # 투자 방식 / 기간 / 월 적립금 입력
        opt1, opt2, opt3 = st.columns([1.3, 1, 1])
        invest_mode = opt1.radio("투자 방식", ["💰 거치식 (목돈 한 번)", "📅 적립식 (매달 추가)"], horizontal=False)
        yrs = opt2.select_slider("투자기간 (년)", options=[1, 3, 5, 10, 15, 20, 25, 30], value=20)
        default_monthly = int(monthly_budget) if 'monthly_budget' in dir() and monthly_budget else 0
        monthly_add = opt3.number_input("매달 추가 투자금 (원)", min_value=0, step=100000, value=default_monthly,
                                        help="위 1번에서 입력한 월 투자금이 기본값으로 들어옵니다. 적립식일 때 사용됩니다.")

        r = w_cagr / 100.0
        is_install = invest_mode.startswith("📅")
        # 미래가치 계산
        fv_lump = total_p * ((1 + r) ** yrs)
        if is_install and monthly_add > 0:
            r_m = r / 12.0
            n = yrs * 12
            fv_series = monthly_add * ((((1 + r_m) ** n) - 1) / r_m) if r_m != 0 else monthly_add * n
            fv = fv_lump + fv_series
            total_invested = total_p + monthly_add * n
        else:
            fv = fv_lump
            total_invested = total_p

        inflation = 0.025  # 연 2.5% 물가 가정
        real_fv = fv / ((1 + inflation) ** yrs)
        monthly_pension = fv * 0.04 / 12  # 4% 인출 룰 → 월 연금
        profit = fv - total_invested

        # 핵심 지표 4종
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("총 투자 원금", f"{int(total_invested):,}원",
                  f"수익 +{int(profit):,}원" if profit >= 0 else f"{int(profit):,}원", delta_color="normal")
        m2.metric(f"{yrs}년 후 예상 자산", f"{int(fv):,}원")
        m3.metric("실질가치 (오늘 돈 기준)", f"{int(real_fv):,}원", help="연 2.5% 물가상승률을 반영한 현재가치")
        m4.metric("은퇴 후 예상 월 연금", f"{int(monthly_pension):,}원", help="4% 인출 룰 기준 (자산의 연 4%를 매년 인출)")

        st.caption(f"📈 가중평균 수익률(CAGR) **{w_cagr:.2f}%** 가정 · "
                   f"{'매달 ' + format(monthly_add, ',') + '원씩 ' + str(yrs) + '년 적립' if is_install and monthly_add > 0 else '목돈 거치 ' + str(yrs) + '년'}")

        # 자산 성장 차트 (투입 원금 vs 평가액)
        years, inv_list, val_list = [], [], []
        for y in range(yrs + 1):
            lump_y = total_p * ((1 + r) ** y)
            if is_install and monthly_add > 0:
                r_m = r / 12.0; n_y = y * 12
                ser_y = monthly_add * ((((1 + r_m) ** n_y) - 1) / r_m) if r_m != 0 else monthly_add * n_y
                val_y = lump_y + ser_y
                inv_y = total_p + monthly_add * n_y
            else:
                val_y = lump_y
                inv_y = total_p
            years.append(y); inv_list.append(float(inv_y)); val_list.append(float(val_y))
        # 연차를 숫자 x축으로 두어 정렬을 보장하고(문자열 정렬 시 0,10,11,…,1,20,2 로 꼬임)
        # 눈금 라벨만 'N년'으로 표시
        fig_growth = go.Figure()
        fig_growth.add_trace(go.Scatter(
            x=years, y=val_list, name="평가액", mode="lines",
            line=dict(color="#93c5fd", width=1.5), fill="tozeroy",
            fillcolor="rgba(147,197,253,0.45)",
            hovertemplate="%{x}년<br>평가액 %{y:,.0f}원<extra></extra>"))
        fig_growth.add_trace(go.Scatter(
            x=years, y=inv_list, name="투입 원금", mode="lines",
            line=dict(color="#3b82f6", width=1.5), fill="tozeroy",
            fillcolor="rgba(59,130,246,0.55)",
            hovertemplate="%{x}년<br>투입 원금 %{y:,.0f}원<extra></extra>"))
        fig_growth.update_layout(
            height=380, margin=dict(l=10, r=10, t=10, b=10),
            hovermode="x unified",
            legend=dict(orientation="h", yanchor="bottom", y=1.02, x=0),
            xaxis=dict(tickmode="array", tickvals=years,
                       ticktext=[f"{y}년" for y in years], title=None),
            yaxis=dict(title=None, tickformat=","),
        )
        st.plotly_chart(fig_growth, use_container_width=True)

        # 포트폴리오 비중 (막대) + 명세서
        pf_col1, pf_col2 = st.columns([1, 1])
        with pf_col1:
            st.markdown("#### 🥧 포트폴리오 비중")
            wdf = pd.DataFrame([{"종목": v['name'], "비중": round(v['qty'] * v['price'] / total_p * 100, 1)}
                                for v in cart.values()]).sort_values("비중", ascending=False)
            wdf_show = wdf.set_index("종목")
            try:
                sty_w = wdf_show.style.format({"비중": "{:.1f}%"}).bar(subset=["비중"], color="#ffd8a8", vmin=0)
                st.dataframe(sty_w, use_container_width=True, height=300)
            except Exception:
                st.dataframe(wdf_show, use_container_width=True)
            if len(wdf) >= 1 and wdf.iloc[0]["비중"] >= 50:
                st.caption(f"⚠️ '{wdf.iloc[0]['종목']}' 비중이 {wdf.iloc[0]['비중']}%로 높아요. 분산을 권장합니다.")
        with pf_col2:
            st.markdown("#### 📝 내 포트폴리오 명세서")
            st.dataframe(pd.DataFrame([{'종목명': v['name'], '수량': f"{v['qty']}주",
                                        '현재가': f"{v['price']:,}원", '총액': f"{v['qty'] * v['price']:,}원",
                                        '연수익률': f"{v['cagr']}%"} for v in cart.values()]),
                         use_container_width=True, hide_index=True, height=300)
        st.caption("※ '데이터없음' 종목은 계산 안전을 위해 수익률 0%로 보수 적용 ｜ 4% 룰·물가 2.5%는 가정치이며 실제와 다를 수 있습니다.")

        st.markdown("---")
        if st.button("🤖 AI 노후 포트폴리오 정밀 진단 (클릭)", type="primary", use_container_width=True):
            if not api_key_input:
                st.error("사이드바에 API 키를 먼저 입력해주세요.")
            else:
                with st.spinner("AI가 은퇴 설계 전문가의 관점으로 포트폴리오를 분석 중입니다..."):
                    port_str = "".join([f"- {v['name']}: 비중 {(v['qty'] * v['price'] / total_p) * 100:.1f}%, 총액 {v['qty'] * v['price']:,}원\n" for v in cart.values()])
                    ai_prompt = (f"은퇴 설계 전문가로서 다음 포트폴리오를 진단해 주세요.\n"
                                 f"투자 방식: {'적립식(매달 ' + format(monthly_add, ',') + '원)' if is_install else '거치식'}\n"
                                 f"총 투자원금: {int(total_invested):,}원\n예상 CAGR: {w_cagr:.2f}%\n투자기간: {yrs}년\n"
                                 f"{yrs}년 후 예상자산(명목): {int(fv):,}원, 은퇴 후 월 연금(4%룰): {int(monthly_pension):,}원\n{port_str}\n"
                                 f"1.분산/리스크 진단 2.개선 제안 3.이 월 연금으로 노후가 충분한지 평가, 순으로 작성하세요.")
                    st.success("✅ 진단 완료!")
                    st.markdown(ask_gemini(ai_prompt, api_key_input))
    else:
        st.info("💡 위 리스트에서 수량을 입력하시면 시뮬레이션이 즉시 시작됩니다.")

    # 0원 검출기를 화면 맨 하단으로 깔끔하게 이동 배치
    st.divider()
    st.markdown("### 🚨 시스템 상태 분석기")
    def _prc_zeroerr():
        errs = [it for it in etf_data if it.get('price', 0) == 0]
        if errs:
            st.error(f"현재 총 {len(errs)}개 종목의 데이터 수집이 지연되고 있습니다.")
            st.table(pd.DataFrame([{'테마': i['theme'], '종목': i['name'], '코드': i['code']} for i in errs]))
        else: 
            st.success("🎉 현재 시스템상 가격이 0원으로 조회되는 오류 종목이 단 하나도 없습니다! (무결점 상태)")
    _register_popup("zeroerr", _prc_zeroerr)
    _popup_button("⚠️ 데이터 통신 지연 종목 확인 (0원 에러 검출기)", "zeroerr", "⚠️ 0원 에러 검출기", key="btn_zeroerr")

# ==========================================
# [v7.0] 🔮 폴리마켓 예측시장 (금리·경제·정치)
# ==========================================
elif selected_menu == "🔮 폴리마켓 예측시장 (금리·경제·정치)":
    st.title("🔮 폴리마켓 예측시장 트래커")
    st.caption("참여자들이 실제 돈을 걸고 형성한 확률입니다. 뉴스보다 빠른 '선행 심리지표'로 활용하세요. (출처: Polymarket Gamma API · 무료/실시간)")

    st.info("💡 **확률(%) = 시장이 매긴 발생 가능성**입니다. 예: '연내 금리 인하' 78% → 시장은 인하를 78% 확신. 주식·환율·채권에 직접적 영향을 주는 매크로 이벤트 위주로 보세요.", icon="🧭")

    # --- 카테고리 프리셋(키워드 필터) ---
    PRESETS = {
        "🔥 전체 인기 (거래량순)": None,
        "🏦 연준/금리 (Fed·Rate)": "fed rate interest hike cut fomc powell",
        "📉 경기침체/인플레 (Recession·CPI)": "recession inflation cpi gdp economy",
        "🗳️ 미국 정치/선거 (Election)": "election president senate house trump congress",
        "🌐 무역/관세 (Tariff)": "tariff trade china taiwan import export",
        "₿ 암호화폐 (Crypto)": "bitcoin ethereum crypto btc eth",
        "🛢️ 지정학/원자재 (War·Oil)": "war ceasefire russia ukraine israel iran oil",
    }

    c_top1, c_top2 = st.columns([2, 1])
    with c_top1:
        preset_name = st.radio("📂 카테고리", list(PRESETS.keys()),
                               horizontal=True, key="poly_preset")
    with c_top2:
        custom_kw = st.text_input("🔍 직접 검색 (영문 키워드)", key="poly_kw",
                                  placeholder="예: nvidia, tesla, gold")

    search_term = custom_kw.strip() if custom_kw.strip() else PRESETS[preset_name]

    cc1, cc2, cc3 = st.columns([1, 1, 2])
    fetch_limit = cc1.selectbox("가져올 마켓 수", [40, 80, 120], index=1, key="poly_limit")
    sort_opt = cc2.radio("정렬", ["24h 거래량", "확률 높은순", "마감 임박순"],
                         horizontal=False, key="poly_sort")
    if cc3.button("🔄 새로고침 (캐시 비우기)", key="poly_refresh"):
        st.cache_data.clear()
        st.rerun()

    with st.spinner("폴리마켓에서 실시간 예측 데이터를 가져오는 중..."):
        result = fetch_polymarket_markets(search=search_term, limit=fetch_limit)

    if result["error"]:
        st.error(f"🚨 데이터를 가져오지 못했습니다: {result['error']}")
        st.caption("Polymarket API가 일시적으로 차단되었거나 네트워크 환경에서 외부 호출이 막혀 있을 수 있습니다. 잠시 후 다시 시도하거나, 앱을 외부 인터넷이 열린 환경에서 실행해 주세요.")
    else:
        markets = result["data"]
        if not markets:
            st.warning("조건에 맞는 마켓이 없습니다. 다른 카테고리나 키워드를 시도해 보세요.")
        else:
            # 정렬
            if sort_opt == "확률 높은순":
                markets = sorted(markets, key=lambda x: (x["yes_prob"] is None, -(x["yes_prob"] or 0)))
            elif sort_opt == "마감 임박순":
                markets = sorted(markets, key=lambda x: (x["end_date"] == "", x["end_date"]))
            else:
                markets = sorted(markets, key=lambda x: -x["volume24hr"])

            st.success(f"✅ 총 {len(markets)}개 마켓 로드 완료 · 카테고리: {preset_name if not custom_kw.strip() else '직접검색'}")

            # --- 한글 번역 처리 ---
            tr_col1, tr_col2 = st.columns([1, 3])
            show_ko = tr_col1.toggle("🇰🇷 한글 번역", value=True, key="poly_translate",
                                     help="폴리마켓 질문/선택지를 한국어로 번역해 보여줍니다. (끄면 영어 원문 · 별도 키 불필요)")
            trans_map = {}
            if show_ko:
                # 번역 대상: 표에 보이는 모든 질문 + 상세(상위)에 쓰이는 선택지
                to_translate = [m["question"] for m in markets]
                for m in markets[:12]:
                    for o in (m["outcomes"] or []):
                        if o not in ("Yes", "No"):   # Yes/No 는 아래서 자체 처리
                            to_translate.append(o)
                with st.spinner("질문을 한글로 번역하는 중... (최초 1회만, 이후 캐시)"):
                    trans_map = translate_poly_questions(tuple(to_translate))

            _YESNO_KO = {"Yes": "예", "No": "아니오"}

            def _q_ko(m):
                if show_ko and trans_map.get(m["question"]):
                    return trans_map[m["question"]]
                return m["question"]

            def _out_ko(o):
                if not show_ko:
                    return o
                if o in _YESNO_KO:
                    return _YESNO_KO[o]
                return trans_map.get(o, o)

            # 요약 테이블
            df_view = pd.DataFrame([{
                "질문": (_q_ko(m))[:70] + ("…" if len(_q_ko(m)) > 70 else ""),
                "확률(Yes)": f"{m['yes_prob']:.1f}%" if m["yes_prob"] is not None else "다중선택지",
                "24h 거래량($)": f"{int(m['volume24hr']):,}",
                "누적 거래량($)": f"{int(m['volume']):,}",
                "마감일": m["end_date"] or "-",
            } for m in markets])
            st.dataframe(df_view, use_container_width=True, hide_index=True, height=380)

            st.divider()
            st.markdown("### 📊 상위 마켓 상세 + 확률 게이지")
            for i, m in enumerate(markets[:12]):
                with st.container():
                    cL, cR = st.columns([3, 1])
                    with cL:
                        st.markdown(f"**{i+1}. {_q_ko(m)}**")
                        # 영어 원문 병기 (번역이 켜져 있고 실제 번역된 경우)
                        if show_ko and _q_ko(m) != m["question"]:
                            st.caption(f"🇺🇸 {m['question']}")
                        # 다중 선택지 확률 표시
                        if m["outcomes"] and m["prices"] and len(m["outcomes"]) == len(m["prices"]):
                            badge = " ｜ ".join(
                                [f"{_out_ko(o)}: **{p:.1f}%**" for o, p in zip(m["outcomes"], m["prices"])][:6]
                            )
                            st.caption(badge)
                        if m["yes_prob"] is not None:
                            st.progress(min(max(m["yes_prob"] / 100, 0), 1.0))
                        meta = f"💰 24h ${int(m['volume24hr']):,} · 누적 ${int(m['volume']):,}"
                        if m["end_date"]:
                            meta += f" · 🗓️ 마감 {m['end_date']}"
                        st.caption(meta)
                        if m["slug"]:
                            st.caption(f"🔗 https://polymarket.com/event/{m['slug']}")
                    with cR:
                        if m["yes_prob"] is not None:
                            st.metric("Yes 확률", f"{m['yes_prob']:.1f}%")
                    st.divider()

            # --- AI 종합 해석 ---
            st.markdown("### 🤖 AI 매크로 해석: 이 확률들이 한국/미국 증시에 주는 시그널")
            if st.button("🧠 AI에게 예측시장 → 투자 시그널 분석 요청", type="primary", use_container_width=True, key="poly_ai"):
                if not api_key_input:
                    st.error("좌측 사이드바에 Gemini API 키를 먼저 입력해주세요.")
                else:
                    with st.spinner("AI가 예측시장 데이터를 매크로 관점에서 해석 중입니다..."):
                        top_for_ai = markets[:15]
                        lines = []
                        for m in top_for_ai:
                            prob_str = f"{m['yes_prob']:.0f}%" if m["yes_prob"] is not None else "다중"
                            lines.append(f"- {_q_ko(m)} → {prob_str} (24h거래량 ${int(m['volume24hr']):,})")
                        data_block = "\n".join(lines)
                        ai_prompt = (
                            "너는 매크로 전략가다. 아래는 Polymarket 예측시장의 실시간 확률 데이터다.\n"
                            "이 베팅 확률(시장 참여자들의 집단 예측)을 근거로 분석하라.\n\n"
                            f"[데이터]\n{data_block}\n\n"
                            "다음 순서로 한국어로 간결하게 작성하라:\n"
                            "1. 핵심 시그널 3가지 (금리/경제/정치 중 주가에 영향 큰 순)\n"
                            "2. 이 확률대로면 수혜 받을 섹터/자산과 타격 받을 섹터 (한국·미국 모두)\n"
                            "3. 환율(원/달러)·채권·코스피에 미칠 단기 영향\n"
                            "4. ⚠️ 투자 유의사항 (예측시장은 참고지표일 뿐 보장 아님)\n"
                            "과도한 단정 대신 확률 기반 시나리오로 서술하라."
                        )
                        st.markdown(ask_gemini(ai_prompt, api_key_input))

            st.caption("※ 예측시장 확률은 실시간 베팅으로 계속 변동하며, 미래를 보장하지 않습니다. 투자 판단의 참고용 선행지표로만 활용하세요.")


# ==========================================
# 🗞️ 뉴스 이슈 TOP & 영향 분석
#   오늘의 핵심 증시 이슈를 AI(구글검색 그라운딩)로 선별·요약 → 영향받는 섹터/종목을
#   호재(긍정)·악재(부정)·중립으로 분기해 '영향 관계도'로 시각화.
# ==========================================
elif selected_menu == "🗞️ 뉴스 이슈 TOP & 영향 분석":
    st.markdown("## 🗞️ 오늘의 뉴스 이슈 TOP & 영향 분석  "
                "<span style='font-size:0.5em;color:#94a3b8;'>BETA</span>", unsafe_allow_html=True)
    st.caption("지금 증시를 움직이는 핵심 뉴스 이슈를 AI가 선별·요약하고, 각 이슈가 어떤 업종·종목에 "
               "호재/악재로 작용하는지 '영향 관계도'로 보여줍니다. (구글 검색 그라운딩 · 무료)")

    if "news_issue_data" not in st.session_state:
        st.session_state.news_issue_data = None

    ctop1, ctop2, ctop3 = st.columns([1, 1, 1], vertical_alignment="bottom")
    ni_topn = ctop1.selectbox("표시할 이슈 수", [3, 5], index=0, key="ni_topn")
    ni_run = ctop2.button("🔎 오늘의 이슈 분석", type="primary", use_container_width=True, key="ni_run")
    if ctop3.button("🔄 새로고침(캐시 비우기)", use_container_width=True, key="ni_refresh"):
        try:
            get_news_issue_impact.clear()
        except Exception as _dg_e:
            _diag_note("<module>", _dg_e)
            pass
        st.session_state.news_issue_data = None
        st.rerun()

    if ni_run:
        if not api_key_input:
            st.warning("⚠️ AI 분석을 위해 좌측 사이드바에 Gemini API 키가 필요합니다.")
        else:
            with st.spinner("실시간 증시 헤드라인 수집 중..."):
                try:
                    _ni_titles = tuple(a["title"] for a in (get_latest_naver_news() or []))[:25]
                except Exception:
                    _ni_titles = tuple()
            with st.spinner("AI가 핵심 이슈와 영향 관계를 분석 중입니다... (구글 검색 → 최초 1회 다소 소요)"):
                st.session_state.news_issue_data = get_news_issue_impact(api_key_input, _ni_titles, ni_topn)

    _ni_data = st.session_state.get("news_issue_data")
    if not _ni_data or not _ni_data.get("issues"):
        st.info("위 **‘🔎 오늘의 이슈 분석’** 버튼을 누르면, 지금 증시를 움직이는 핵심 뉴스 이슈와 그 파급 효과를 분석해 드려요.")
    else:
        # 긍정=빨강(호재), 부정=파랑(악재), 중립=회색 — 한국 증시 색 관례
        _SENT_STYLE = {
            "긍정": ("#e11d48", "rgba(225,29,72,0.07)", "📈", "수혜"),
            "부정": ("#2563eb", "rgba(37,99,235,0.07)", "📉", "타격"),
            "중립": ("#64748b", "rgba(100,116,139,0.07)", "⚖️", "중립"),
        }
        _gen = _ni_data.get("generated_at", "")
        for _iss in _ni_data["issues"]:
            _rank = _iss.get("rank", 1)
            _src_n = len(_iss.get("sources") or [])

            # ── 이슈 헤더 카드 ──
            st.markdown(
                f"<div style='font-size:13px;font-weight:800;color:#6366f1;margin-bottom:2px;'>뉴스 이슈 {_rank}위</div>"
                f"<div style='font-size:24px;font-weight:800;color:#0f172a;line-height:1.25;margin-bottom:10px;'>{_iss['title']}</div>",
                unsafe_allow_html=True)
            if _iss.get("summary"):
                st.markdown(
                    f"<div style='border-left:4px solid #cbd5e1;padding:2px 0 2px 14px;color:#334155;"
                    f"font-size:15.5px;line-height:1.7;margin-bottom:6px;'>{_iss['summary']}</div>",
                    unsafe_allow_html=True)
            if _iss.get("points"):
                with st.expander("📌 주목할 포인트"):
                    for _p in _iss["points"]:
                        st.markdown(f"- {_p}")
            _meta = []
            if _src_n:
                _meta.append(f"📰 {_src_n}개 출처")
            if _gen:
                _meta.append(f"🕒 {_gen} 기준")
            if _iss.get("sources"):
                _meta.append("· " + ", ".join(_iss["sources"][:6]))
            if _meta:
                st.caption("   ".join(_meta))

            # ── 영향 관계도 ──
            st.markdown("<div style='font-size:17px;font-weight:800;color:#0f172a;margin:14px 0 4px;'>"
                        "어떤 영향을 줄까?</div>", unsafe_allow_html=True)
            _impacts = _iss.get("impacts") or []
            if not _impacts:
                st.caption("영향 관계 데이터가 없습니다.")
            else:
                _order = {"긍정": 0, "중립": 1, "부정": 2}
                _impacts = sorted(_impacts, key=lambda x: _order.get(x["sentiment"], 1))
                _chips = []
                for _im in _impacts:
                    _color, _bg, _emo, _tag = _SENT_STYLE.get(_im["sentiment"], _SENT_STYLE["중립"])
                    _tk_html = ""
                    if _im.get("tickers"):
                        _tk_html = "".join(
                            "<span style='display:inline-block;font-size:11px;color:#475569;background:#f1f5f9;"
                            "border-radius:5px;padding:1px 7px;margin:4px 5px 0 0;'>"
                            + _t["name"] + (f" · {_t['code']}" if _t.get("code") else "") + "</span>"
                            for _t in _im["tickers"]
                        )
                    _chips.append(
                        f"<div style='border:1px solid {_color}33;border-left:4px solid {_color};background:{_bg};"
                        f"border-radius:12px;padding:10px 14px;margin:8px 0;'>"
                        f"<div><span style='font-weight:800;color:#0f172a;font-size:15px;'>{_emo} {_im['target']}</span>"
                        f"<span style='font-size:11.5px;font-weight:800;color:#fff;background:{_color};"
                        f"border-radius:6px;padding:1px 8px;margin-left:9px;'>{_im['sentiment']}</span>"
                        f"<span style='font-size:11px;color:#94a3b8;margin-left:7px;'>{_im['kind']} · {_tag}</span></div>"
                        f"<div style='font-size:13px;color:#475569;line-height:1.5;margin-top:4px;'>{_im['reason']}</div>"
                        + (f"<div style='margin-top:4px;'>{_tk_html}</div>" if _tk_html else "")
                        + "</div>"
                    )
                st.markdown(
                    "<div style='display:flex;gap:14px;align-items:stretch;'>"
                    "<div style='flex:0 0 132px;display:flex;align-items:center;justify-content:center;text-align:center;"
                    "background:linear-gradient(135deg,#eef2ff,#e0e7ff);border:1px solid #c7d2fe;border-radius:14px;"
                    f"padding:12px;font-weight:800;color:#3730a3;font-size:14px;line-height:1.35;'>{_iss['title']}</div>"
                    "<div style='flex:1;min-width:0;'>" + "".join(_chips) + "</div>"
                    "</div>",
                    unsafe_allow_html=True)

                # 영향받는 종목을 '이 자리에서' 바로 정밀 진단 (페이지 이동 없이 인라인 표시)
                _codes_seen, _opts = set(), {}
                for _im in _impacts:
                    for _t in (_im.get("tickers") or []):
                        if _t.get("code") and _t["code"] not in _codes_seen:
                            _codes_seen.add(_t["code"])
                            _opts[f"{_t['name']} ({_t['code']}) · {_im['sentiment']}"] = (_t["name"], _t["code"])
                if _opts:
                    _pick = st.selectbox("🔬 이 이슈의 관련 종목 — 선택하면 바로 아래에 정밀 진단이 표시됩니다",
                                         ["(선택)"] + list(_opts.keys()), key=f"ni_pick_{_rank}")
                    if _pick != "(선택)":
                        _nm, _cd = _opts[_pick]
                        with st.container(border=True):
                            st.markdown(f"#### 🔬 {_nm} ({_cd}) 정밀 진단")
                            with st.spinner(f"📡 '{_nm}' 타점·수급 분석 중..."):
                                _res_ni = analyze_technical_pattern(_nm, _cd)
                            if _res_ni:
                                try:
                                    render_single_stock_themes(_nm, api_key_input)
                                except Exception as _dg_e:
                                    _diag_note("<module>", _dg_e)
                                    pass
                                draw_stock_card(_res_ni, api_key_str=api_key_input,
                                                is_expanded=True, key_suffix=f"ni_{_rank}_{_cd}")
                            else:
                                st.error(f"❌ '{_nm}({_cd})' 데이터를 불러오지 못했어요. 종목코드를 확인해 주세요.")
            st.divider()

        st.caption("※ AI가 실시간 검색으로 생성한 분석으로, 부정확하거나 지연될 수 있습니다. "
                   "호재/악재·영향 판단은 참고용이며, 최종 투자 판단과 책임은 투자자 본인에게 있습니다.")


# ==========================================
# [v7.1] 🚨 통합 경보 센터 (뉴스·차트·일정)
#   - jaemini_alert_center.py 의 함수에 기존 앱 함수들을 '주입'해서 렌더
# ==========================================
elif selected_menu == "🚨 통합 경보 센터 (뉴스·차트·일정)":
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


# =====================================================================
# [v7.2] 데이터 수집 진단 패널 — 어떤 메뉴에서든 화면 하단에서 확인 가능
#   화면이 비어 보일 때 "데이터가 없는 것"인지 "수집이 실패한 것"인지 구분한다.
# =====================================================================
diag.render_panel()


# =====================================================================
# [공통] 전 페이지 하단 면책 푸터 — 어떤 메뉴든 화면 맨 아래에 항상 표시
#   (메뉴 분기 바깥 최상위에 두어 매 실행마다 렌더됨)
# =====================================================================
st.markdown(
    "<div style=\"margin-top:46px;padding:16px 20px;border-top:1px solid #e2e8f0;"
    "background:#f8fafc;border-radius:12px;text-align:center;\">"
    "<div style=\"font-size:12.5px;color:#64748b;line-height:1.75;\">"
    "⚠️ 본 서비스의 모든 정보·점수·신호·AI 분석은 <b>투자 권유가 아닌 참고 자료</b>이며, "
    "데이터는 지연되거나 오류가 있을 수 있습니다.<br>"
    "모든 투자 판단과 그 결과에 대한 책임은 <b>전적으로 이용자 본인</b>에게 있습니다."
    "</div>"
    "<div style=\"font-size:11px;color:#94a3b8;margin-top:7px;\">"
    "정보 제공 목적 · 매수·매도 추천이 아닙니다 · © 2026</div>"
    "</div>", unsafe_allow_html=True)
