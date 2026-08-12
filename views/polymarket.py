# -*- coding: utf-8 -*-
"""🔮 폴리마켓 예측시장 (금리·경제·정치)

app.py 라우팅에서 분리된 페이지. 함수 라이브러리는 core 에서 가져온다.
"""
from core import *


# ==========================================
# [v7.0] 🔮 폴리마켓 예측시장 (금리·경제·정치)
# ==========================================

def render(ctx):
    _nav_changed = ctx['_nav_changed']
    api_key_input = ctx['api_key_input']

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
