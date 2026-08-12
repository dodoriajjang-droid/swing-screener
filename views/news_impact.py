# -*- coding: utf-8 -*-
"""🗞️ 뉴스 이슈 TOP & 영향 분석

app.py 라우팅에서 분리된 페이지. 함수 라이브러리는 core 에서 가져온다.
"""
from core import *


# ==========================================
# 🗞️ 뉴스 이슈 TOP & 영향 분석
#   오늘의 핵심 증시 이슈를 AI(구글검색 그라운딩)로 선별·요약 → 영향받는 섹터/종목을
#   호재(긍정)·악재(부정)·중립으로 분기해 '영향 관계도'로 시각화.
# ==========================================

def render(ctx):
    _nav_changed = ctx['_nav_changed']
    api_key_input = ctx['api_key_input']

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
