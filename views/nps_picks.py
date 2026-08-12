# -*- coding: utf-8 -*-
"""🏛️ 국민연금 5% 대량보유 픽

app.py 라우팅에서 분리된 페이지. 함수 라이브러리는 core 에서 가져온다.
"""
from core import *


def render(ctx):
    _nav_changed = ctx['_nav_changed']
    api_key_input = ctx['api_key_input']

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
