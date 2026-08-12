# -*- coding: utf-8 -*-
"""🔬 종목 상세 — 한 종목을 한 번 고르고, 탭으로 각도를 바꿔 본다.

[통합] 예전에는 같은 종목을 세 화면에서 세 번 검색해야 했다.
  · 개별 기업 정밀 진단  → 차트·기술적 타점
  · 적정 주가 계산기      → DCF 내재가치
  · 증권사 목표가 컨센서스 → 애널리스트 목표가
세 화면 모두 '같은 종목의 다른 면'인데 입구가 따로였다.
지금은 위에서 종목을 한 번 고르면 아래 탭이 전부 그 종목을 따라간다.

각 탭의 내용은 기존 페이지 코드를 그대로 옮긴 것이라 기능은 동일하다.
"""
from core import *

import views.company_deep_dive as _tech
import views.fair_value as _value
import views.consensus as _consensus


def _pick_stock():
    """공용 종목 선택기. 반환: (종목명, 코드, 미국주식여부) — 아직 안 골랐으면 (None, None, False).

    선택은 세션에 남는다. 탭을 옮기거나 화면이 다시 그려져도 고른 종목이 유지된다.
    """
    market = st.radio("시장", ["🇰🇷 국내 주식", "🇺🇸 미국 주식"], horizontal=True,
                      key="sd_market", label_visibility="collapsed")
    is_us = market.startswith("🇺🇸")

    if not is_us:
        krx_df = get_krx_stocks()
        if not krx_df.empty:
            opts = ["🔍 종목명 또는 코드로 검색"] + \
                   (krx_df['Name'].astype(str) + " (" + krx_df['Code'].astype(str) + ")").tolist()
            q = st.selectbox("종목 검색", opts, key="sd_kr_pick", label_visibility="collapsed")
            if q != opts[0]:
                st.session_state.sd_name = q.rsplit(" (", 1)[0]
                st.session_state.sd_code = q.rsplit("(", 1)[-1].replace(")", "").strip()
                st.session_state.sd_is_us = False
        else:
            # 폴백: 종목 목록을 못 불러오면 코드 직접 입력
            st.warning("⚠️ 국내 종목 목록을 일시적으로 불러오지 못했습니다. **종목코드 6자리**를 직접 입력하세요. (예: 005930)")
            manual = st.text_input("종목코드 입력", placeholder="예: 005930  또는  005930 삼성전자",
                                   key="sd_kr_manual", label_visibility="collapsed")
            if manual:
                m = re.search(r"\d{6}", manual)
                if m:
                    st.session_state.sd_code = m.group()
                    st.session_state.sd_name = manual.replace(m.group(), "").strip() or m.group()
                    st.session_state.sd_is_us = False
                else:
                    st.error("6자리 종목코드를 포함해 입력해 주세요. 예: 005930")
    else:
        c1, c2 = st.columns([8, 2])
        with c1:
            us_q = st.text_input("미국 종목 검색", placeholder="예: AAPL 또는 Apple",
                                 key="sd_us_query", label_visibility="collapsed")
        with c2:
            do_search = st.button("🔍 검색", use_container_width=True, key="sd_us_search")
        if do_search and us_q:
            with st.spinner("검색 중..."):
                found = search_us_ticker(us_q)
            if found:
                st.session_state.sd_us_results = found
            else:
                st.error("❌ 검색 결과가 없습니다. 티커를 직접 입력해 보세요.")
        results = st.session_state.get("sd_us_results") or []
        if results:
            sel = st.selectbox("검색 결과", ["선택하세요"] + results,
                               key="sd_us_pick", label_visibility="collapsed")
            if sel != "선택하세요":
                st.session_state.sd_code = sel.split(" ")[0]
                st.session_state.sd_name = sel.split(" ")[0]
                st.session_state.sd_is_us = True

    return (st.session_state.get("sd_name"),
            st.session_state.get("sd_code"),
            bool(st.session_state.get("sd_is_us")))


def render(ctx):
    api_key_input = ctx['api_key_input']

    st.markdown("## 🔬 종목 상세")
    st.caption("종목을 한 번 고르면 차트·적정주가·컨센서스를 탭으로 바꿔가며 볼 수 있습니다.")

    with st.container(border=True):
        name, code, is_us = _pick_stock()
        if code:
            st.markdown(f"**선택한 종목 · {name}** `{code}` {'🇺🇸' if is_us else '🇰🇷'}")

    if not code:
        st.info("위에서 종목을 고르면 아래에 분석이 나타납니다.")
        return

    t_tech, t_value, t_cons, t_ref = st.tabs(
        ["📊 차트·기술", "⚖️ 적정주가 (DCF)", "🎯 증권사 컨센서스", "📚 밸류에이션 참고"])

    with t_tech:
        _tech.panel(ctx, name, code, is_us)
    with t_value:
        _value.dcf_panel(ctx, name, code, is_us)
    with t_cons:
        _consensus.panel(ctx, name, code, is_us)
    with t_ref:
        _value.reference_panel(ctx)
