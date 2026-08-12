# -*- coding: utf-8 -*-
"""💎 장기 우량주 & 가치주 발굴

app.py 라우팅에서 분리된 페이지. 함수 라이브러리는 core 에서 가져온다.
"""
from core import *


def scan_panel(ctx):
    """💎 장기 가치 — 위험 성향 → 세부 전략 → 멀티팩터 검증"""
    _nav_changed = ctx.get('_nav_changed', False)
    api_key_input = ctx.get('api_key_input', "")

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
