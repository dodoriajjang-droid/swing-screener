# -*- coding: utf-8 -*-
"""🚦 거래량·시장경보 패널 — '경보 센터' 메뉴의 탭들.

[통합] '🚦 거래량 급증 & 시장 경보' 독립 메뉴였다. 경보는 경보 센터 한 곳에
모으는 게 맞아 탭으로 옮겼다. 내용은 그대로다.
"""
from core import *


def volume_panel(ctx):
    """거래량 급증/급감"""
    api_key_input = ctx.get("api_key_input", "")

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


def warning_panel(ctx):
    """관리종목 및 시장경보"""
    api_key_input = ctx.get("api_key_input", "")

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

