# -*- coding: utf-8 -*-
"""🚀 단기 스윙 조건 스캐너 패널 — 종목 스크리너의 프리셋 하나.

[통합] 예전에는 '🚀 단기 스윙 퀀트 스캐너' 독립 메뉴였고, 전략 백테스트가
같은 화면의 두 번째 탭으로 붙어 있었다. 스캐닝(후보 찾기)과 백테스트(전략 검증)는
목적이 다른 작업이라 분리했다.
  · 조건 스캔  → views/screener.py 의 '단기 스윙' 프리셋
  · 전략 검증  → views/backtest.py (독립 메뉴)
조건과 판정 로직은 그대로다.
"""
from core import *


def scan_panel(ctx):
    """조건 체크박스 기반 실시간 스캔."""
    api_key_input = ctx.get('api_key_input', "")

    # [밀도개선] 예전에는 조건 체크박스 9개·유동성 필터·검색 방식·종목 수가 한 화면에
    #   전부 펼쳐져 있어(위젯 40개), 처음 여는 사람은 어디부터 만져야 할지 알 수 없었다.
    #   지금은 '어떻게 찾을지' 버튼 4개와 [스캔 시작]만 보이고, 세부 조건은 접어 둔다.
    #   화면 아래에서 만든 체크박스 값을 위쪽 버튼이 써야 하므로 st.empty() 슬롯을 먼저
    #   잡아두고 나중에 채운다(코드 순서와 화면 순서를 분리).
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
    st.markdown("**⚡ 어떻게 찾을까요?**")
    _pc1, _pc2, _pc3, _pc4 = st.columns(4)
    _pc1.button("🚀 돌파형", use_container_width=True, help="정배열/골든 + 52주 신고가권 + 거래량 급증 + 자금유입",
                on_click=_apply_scan_preset, args=(["sc_golden", "sc_high52", "sc_vol", "sc_mfi"],))
    _pc2.button("📉 낙폭 반등형", use_container_width=True, help="RSI 과매도 + 20일선 눌림목",
                on_click=_apply_scan_preset, args=(["sc_rsi", "sc_pullback"],))
    _pc3.button("🐋 세력주형", use_container_width=True, help="외인·기관 쌍끌이 + 거래량 급증 + 기관 연속매수",
                on_click=_apply_scan_preset, args=(["sc_twin", "sc_vol", "sc_pension"],))
    _pc4.button("♻️ 조건 초기화", use_container_width=True, on_click=_apply_scan_preset, args=([],))

    # 조건 요약과 실행 버튼이 놓일 자리를 미리 잡아둔다 (아래에서 값이 정해진 뒤 채움)
    _summary_slot = st.empty()
    _action_slot = st.empty()

    with st.expander("🔧 조건 직접 고르기", expanded=False):
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

    with st.expander("⚙️ 고급 설정 — 검색 방식 · 범위 · 유동성 필터", expanded=False):
        _sc_col1, _sc_col2 = st.columns([2.2, 1.8])
        with _sc_col1:
            scan_mode = st.radio("🔬 검색 방식", ["🎯 조건 필터 (체크한 조건 전부 충족)", "🏆 점수 랭킹 (충족 개수로 정렬·1개 이상)"],
                                 horizontal=True,
                                 help="조건 필터: AND 방식 — 깐깐하지만 결과가 0개일 수 있음.\n점수 랭킹: 체크한 조건 중 몇 개를 충족하는지 점수화해 많이 충족한 순으로 보여줌 — 장이 안 좋은 날에도 상대적 상위 종목 발굴 가능.")
        with _sc_col2:
            scan_limit = st.selectbox("스캔할 상위 종목 수", [50, 100, 200, 300], index=3)

        # 💧 유동성·가격·과열 하드필터 (선택한 조건과 별개로 항상 적용, 0 = 미적용)
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

    with st.expander("🐥 처음이신가요? 용어와 매매 타점 가이드", expanded=False):
        show_beginner_guide()
        show_trading_guidelines()

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

    # 위에 잡아둔 슬롯을 이제 채운다 — 지금 무엇으로 찾는지 한 줄로 보여준다
    if scan_checks:
        _summary_slot.caption(
            "🔎 지금 조건 **" + str(len(scan_checks)) + "개** · "
            + " · ".join(lbl for lbl, _ in scan_checks)
            + f"  ｜  상위 {scan_limit}종목 대상")
    else:
        _summary_slot.caption("🔎 조건이 없습니다 — 위 버튼으로 한 번에 세팅하거나 **조건 직접 고르기**에서 선택하세요.")

    if _action_slot.button("🚀 쾌속 병렬 스캔 시작", type="primary", use_container_width=True):
        if not scan_checks:
            st.warning("⚠️ 검색 조건을 최소 1개 이상 골라주세요. 위의 **🚀 돌파형 / 📉 낙폭 반등형 / 🐋 세력주형** 버튼을 누르면 한 번에 세팅됩니다.")
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
        if not st.session_state.scan_results:
            # [개선] 예전에는 결과가 0개면 빈 화면이었고, 다음에 뭘 해야 할지는 사용자 몫이었다.
            st.info("조건을 만족하는 종목이 없습니다. 아래 중 하나를 시도해 보세요.")
            _e1, _e2, _e3 = st.columns(3)
            _e1.button("🏆 점수 랭킹으로 보기", use_container_width=True, key="empty_to_rank",
                       help="조건을 전부 만족하지 않아도, 많이 만족한 순으로 보여줍니다. "
                            "'고급 설정 → 검색 방식'에서 바꿀 수 있습니다.")
            _e2.button("♻️ 조건 줄이기", use_container_width=True, key="empty_reset",
                       on_click=_apply_scan_preset, args=(["sc_pullback"],),
                       help="조건을 '20일선 눌림목' 하나만 남깁니다.")
            _e3.button("🔍 범위 넓히기", use_container_width=True, key="empty_widen",
                       help="'고급 설정 → 스캔할 상위 종목 수'를 300으로 올려 보세요.")
        else:
            display_sorted_results(st.session_state.scan_results, tab_key="t2", api_key=api_key_input)

