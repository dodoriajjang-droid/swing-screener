# -*- coding: utf-8 -*-
"""📉 낙폭과대 스캐너 (고점대비 -30%↓)

app.py 라우팅에서 분리된 페이지. 함수 라이브러리는 core 에서 가져온다.
"""
from core import *


def render(ctx):
    _nav_changed = ctx['_nav_changed']
    api_key_input = ctx['api_key_input']

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
