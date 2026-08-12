# -*- coding: utf-8 -*-
"""🧭 AI 통합 투자 발굴기 (테스트)

app.py 라우팅에서 분리된 페이지. 함수 라이브러리는 core 에서 가져온다.
"""
from core import *


def render(ctx):
    _nav_changed = ctx['_nav_changed']
    api_key_input = ctx['api_key_input']

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
