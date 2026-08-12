# -*- coding: utf-8 -*-
"""⚖️ 적정주가(DCF) 패널 + 밸류에이션 참고 — 종목 상세의 탭 두 개.

[통합] 예전에는 '⚖️ 적정 주가 계산기'라는 독립 메뉴가 자체 종목 검색 폼을 갖고
있었다. 지금은 views/stock_detail.py 가 고른 종목을 받아 계산만 한다.
종목과 무관한 내용(버핏 지수·72의 법칙·스크리닝 기준)은 reference_panel 로 분리했다.
계산식과 결과 표현은 그대로다.
"""
from core import *


def dcf_panel(ctx, name, code, is_us):
    """선택된 종목의 잉여현금흐름(FCF) 기반 내재가치 계산."""
    st.markdown("### 📊 잉여현금흐름(FCF) 기반 내재가치 계산기")
    st.caption("회사가 앞으로 벌어들일 현금을 현재 가치로 할인해 '이 주식의 값어치'를 추정합니다. "
               "가정(성장률·할인율)에 따라 결과가 크게 달라지므로 참고용으로 보세요.")

    _, _, fcf_val, shares_val, _ = get_fundamentals(code)
    res = analyze_technical_pattern(name, code)
    default_price = float(res['현재가']) if res else 0.0
    default_fcf = float(fcf_val) if fcf_val and pd.notna(fcf_val) else 1000.0
    default_shares = float(shares_val) if shares_val and pd.notna(shares_val) else 100.0

    if not res:
        st.warning("현재가를 불러오지 못해 0으로 채웠습니다. 아래에서 직접 입력해 주세요.")

    st.markdown("#### ⚙️ DCF 파라미터")
    col1, col2 = st.columns(2)
    with col1:
        input_price = st.number_input("현재 주가", value=default_price, step=1.0, key="sd_dcf_price")
        input_fcf = st.number_input("최근 잉여현금흐름(FCF)", value=default_fcf, step=100.0, key="sd_dcf_fcf")
        input_shares = st.number_input("유통 주식수", value=default_shares, step=10.0, key="sd_dcf_shares")
    with col2:
        growth_rate = st.slider("예상 연평균 성장률 (%)", 1.0, 50.0, 10.0, key="sd_dcf_growth")
        discount_rate = st.slider("할인율 (요구수익률) (%)", 5.0, 20.0, 9.0, key="sd_dcf_discount")
        terminal_growth = st.slider("영구 성장률 (%)", 1.0, 5.0, 2.5, key="sd_dcf_terminal")

    if st.button("🧮 적정 주가 연산", type="primary", use_container_width=True, key="sd_dcf_run"):
        with st.spinner("미래 현금흐름 할인 연산 중..."):
            future_fcfs = []
            current_fcf = input_fcf
            for i in range(1, 11):
                current_fcf *= (1 + growth_rate / 100)
                future_fcfs.append(current_fcf / ((1 + discount_rate / 100) ** i))

            terminal_value = (current_fcf * (1 + terminal_growth / 100)) / ((discount_rate / 100) - (terminal_growth / 100))
            discounted_tv = terminal_value / ((1 + discount_rate / 100) ** 10)
            total_value = sum(future_fcfs) + discounted_tv

            # 💡 [단위 보정] FCF(억/10^8)와 주식수(백만/10^6) 스케일을 맞추기 위해 100을 곱함
            fair_price = (total_value / input_shares) * 100 if input_shares > 0 else 0
            margin_of_safety = ((fair_price - input_price) / fair_price) * 100 if fair_price > 0 else 0

            st.divider()
            st.markdown(f"### 🎯 [{name}] DCF 가치평가 결과")
            c1, c2, c3 = st.columns(3)
            c1.metric("현재 주가", f"{input_price:,.2f}")
            c2.metric("DCF 적정 주가", f"{fair_price:,.2f}")
            c3.metric("안전 마진", f"{margin_of_safety:+.1f}%",
                      delta_color="normal" if margin_of_safety > 0 else "inverse")

            if margin_of_safety > 20:
                st.success("🟢 **강력 매수 구간**: 현재 주가가 내재가치 대비 20% 이상 저렴합니다.")
            elif margin_of_safety > 0:
                st.info("🔵 **매수 구간**: 현재 주가가 내재가치보다 저렴합니다.")
            elif margin_of_safety > -20:
                st.warning("🟡 **적정 가치 구간**: 주가가 내재가치와 비슷하게 형성되어 있습니다.")
            else:
                st.error("🔴 **고평가 구간**: 현재 주가가 미래 성장성을 이미 과도하게 반영하고 있을 수 있습니다.")


def reference_panel(ctx):
    """종목과 무관한 밸류에이션 참고 자료 — 시장 전체 지표와 스크리닝 기준."""
    st.markdown("### 📈 버핏 지수 (Buffett Indicator)")
    st.write("국가의 시가총액을 명목 GDP로 나눈 값으로, 증시 전체의 고평가/저평가 여부를 판단합니다.")
    buffett_ratio = 115.5
    st.metric("현재 한국 증시 추정 버핏 지수", f"{buffett_ratio}%")
    st.caption("⚠️ 이 값은 실시간 산출이 아니라 고정된 추정치입니다. 방향 감각을 잡는 용도로만 보세요.")
    if buffett_ratio > 120:
        st.error("🚨 증시가 역사적 고평가 상태입니다. 현금 비중을 늘리는 것을 고려하세요.")
    elif buffett_ratio > 80:
        st.success("✅ 시장이 적정 가치 구간에 있습니다.")
    else:
        st.info("💰 시장이 저평가 상태입니다. 적극적인 매수 기회일 수 있습니다.")

    st.divider()
    st.markdown("### ⏱️ 복리 계산기 (72의 법칙)")
    return_rate = st.slider("목표 연평균 수익률 (%)", min_value=1.0, max_value=30.0,
                            value=15.0, step=0.5, key="sd_rule72")
    years_to_double = 72 / return_rate
    st.markdown(
        f"👉 연수익률 **{return_rate}%** 유지 시, 원금이 2배가 되는 데 약 "
        f"**<span style='color:#ff4b4b; font-size:24px;'>{years_to_double:.1f}년</span>**이 걸립니다.",
        unsafe_allow_html=True)

    st.divider()
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
