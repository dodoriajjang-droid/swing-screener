# -*- coding: utf-8 -*-
"""📅 핵심 증시 일정 & IPO 달력

app.py 라우팅에서 분리된 페이지. 함수 라이브러리는 core 에서 가져온다.
"""
from core import *


def render(ctx):
    _nav_changed = ctx['_nav_changed']
    api_key_input = ctx['api_key_input']

    st.subheader("📅 핵심 증시 일정 & IPO 달력")
    cal_tab2, cal_tab3 = st.tabs(["🗓️ 통합 일정 달력 (경제지표+수급)", "🇰🇷 국내 IPO 분석"])

    with cal_tab2:
        st.markdown("#### 🗓️ 경제지표 · 파생수급 통합 달력")
        cc1, cc2, cc3 = st.columns([1, 8, 1])
        with cc1:
            if st.button("◀ 이전 달", use_container_width=True, key="us_prev"):
                st.session_state.smart_cal_month -= 1
                if st.session_state.smart_cal_month == 0:
                    st.session_state.smart_cal_month = 12
                    st.session_state.smart_cal_year -= 1
                st.rerun()
        with cc2: st.markdown(f"<h3 style='text-align: center; margin:0;'>{st.session_state.smart_cal_year}년 {st.session_state.smart_cal_month}월</h3>", unsafe_allow_html=True)
        with cc3:
            if st.button("다음 달 ▶", use_container_width=True, key="us_next"):
                st.session_state.smart_cal_month += 1
                if st.session_state.smart_cal_month == 13:
                    st.session_state.smart_cal_month = 1
                    st.session_state.smart_cal_year += 1
                st.rerun()
                
        if st.button("🔄 오늘로 돌아가기", key="us_today"):
            st.session_state.smart_cal_year = datetime.now().year
            st.session_state.smart_cal_month = datetime.now().month
            st.rerun()

        year = st.session_state.smart_cal_year
        month = st.session_state.smart_cal_month
        calendar.setfirstweekday(calendar.SUNDAY)
        cal = calendar.monthcalendar(year, month)
        
        fridays = [week[5] for week in cal if week[5] != 0]
        us_opex_day = fridays[2] if len(fridays) >= 3 else fridays[-1]
        us_opex_week_days = [us_opex_day - 4 + i for i in range(5)]

        tax_day = -1
        if month == 4:
            tax_day = 15
            for week in cal:
                if week[6] == 15: tax_day = 17 
                if week[0] == 15: tax_day = 16 

        thursdays = [week[calendar.THURSDAY] for week in cal if week[calendar.THURSDAY] != 0]
        kr_opex_day = thursdays[1] if len(thursdays) >= 2 else thursdays[0]
        kr_is_quadruple = month in [3, 6, 9, 12]
        today_day = datetime.now().day if year == datetime.now().year and month == datetime.now().month else -1

        html_parts = [
            "<style>",
            ".cal-grid { display: grid; grid-template-columns: repeat(7, 1fr); gap: 2px; background: #ddd; border: 1px solid #ccc; font-family: sans-serif; }",
            ".cal-head { background: #f8f9fa; text-align: center; font-weight: bold; padding: 10px; font-size: 14px; }",
            ".cal-cell { background: white; min-height: 120px; padding: 5px; display: flex; flex-direction: column; }",
            ".cal-cell.today { background: #f0f8ff; border: 2px solid #1f77b4; }",
            ".cal-num { font-weight: bold; margin-bottom: 5px; font-size: 15px; }",
            ".evt-us-red { background: #ffebee; color: #b91c1c; font-size: 11px; padding: 3px; margin-bottom: 2px; border-left: 3px solid #b91c1c; border-radius: 2px; font-weight: bold; line-height: 1.2; letter-spacing: -0.5px; }",
            ".evt-us-warn { background: #fff3e0; color: #e65100; font-size: 11px; padding: 3px; margin-bottom: 2px; border-left: 3px solid #e65100; border-radius: 2px; font-weight: bold; line-height: 1.2; letter-spacing: -0.5px; }",
            ".evt-us-green { background: #e8f5e9; color: #2e7d32; font-size: 11px; padding: 3px; margin-bottom: 2px; border-left: 3px solid #2e7d32; border-radius: 2px; font-weight: bold; line-height: 1.2; letter-spacing: -0.5px; }",
            ".evt-kr-red { background: #fce4ec; color: #b71c1c; font-size: 11px; padding: 3px; margin-bottom: 2px; border-left: 3px solid #b71c1c; border-radius: 2px; font-weight: bold; line-height: 1.2; letter-spacing: -0.5px; }",
            ".evt-kr-blue { background: #e3f2fd; color: #1565c0; font-size: 11px; padding: 3px; margin-bottom: 2px; border-left: 3px solid #1565c0; border-radius: 2px; font-weight: bold; line-height: 1.2; letter-spacing: -0.5px; }",
            ".evt-kr-green { background: #f1f8e9; color: #1b5e20; font-size: 11px; padding: 3px; margin-bottom: 2px; border-left: 3px solid #1b5e20; border-radius: 2px; font-weight: bold; line-height: 1.2; letter-spacing: -0.5px; }",
            ".evt-econ-fomc { background: #ede7f6; color: #4527a0; font-size: 11px; padding: 3px; margin-bottom: 2px; border-left: 3px solid #4527a0; border-radius: 2px; font-weight: bold; line-height: 1.2; letter-spacing: -0.5px; }",
            ".evt-econ-cpi { background: #fff8e1; color: #ff6f00; font-size: 11px; padding: 3px; margin-bottom: 2px; border-left: 3px solid #ff6f00; border-radius: 2px; font-weight: bold; line-height: 1.2; letter-spacing: -0.5px; }",
            ".evt-econ-jobs { background: #e0f7fa; color: #006064; font-size: 11px; padding: 3px; margin-bottom: 2px; border-left: 3px solid #006064; border-radius: 2px; font-weight: bold; line-height: 1.2; letter-spacing: -0.5px; }",
            ".evt-econ-bok { background: #fce4ec; color: #880e4f; font-size: 11px; padding: 3px; margin-bottom: 2px; border-left: 3px solid #880e4f; border-radius: 2px; font-weight: bold; line-height: 1.2; letter-spacing: -0.5px; }",
            "</style>",
            "<div class='cal-grid'>",
            "<div class='cal-head' style='color:#d32f2f;'>일</div><div class='cal-head'>월</div><div class='cal-head'>화</div><div class='cal-head'>수</div><div class='cal-head'>목</div><div class='cal-head'>금</div><div class='cal-head' style='color:#1976d2;'>토</div>"
        ]
        
        econ_events = get_economic_events(year, month)

        for week in cal:
            for i, day in enumerate(week):
                if day == 0: html_parts.append("<div class='cal-cell' style='background:#fafafa;'></div>")
                else:
                    events = ""
                    # 경제지표(FOMC·CPI·고용·금통위)를 가장 위에 표시
                    for label, cls in econ_events.get(day, []):
                        events += f"<div class='{cls}'>{label}</div>"
                    if day == tax_day: events += "<div class='evt-us-red'>🔴 🇺🇸세금납부일(하락압력)</div>"
                    if i == calendar.THURSDAY:
                        if day == kr_opex_day:
                            label = "🔥 🇰🇷네마녀의 날" if kr_is_quadruple else "🔴 🇰🇷옵션만기일"
                            events += f"<div class='evt-kr-red'>{label}(수급극대)</div>"
                        else: events += "<div class='evt-kr-blue'>🔹 🇰🇷위클리 만기(오후변동)</div>"
                    elif i == calendar.FRIDAY and day == kr_opex_day + 1: events += "<div class='evt-kr-green'>🟢 🇰🇷수급 되돌림(추세복귀)</div>"

                    if day in us_opex_week_days:
                        if day == us_opex_day: events += "<div class='evt-us-red'>🔴 🇺🇸옵션만기(변동성폭발)</div>"
                        else: events += "<div class='evt-us-warn'>⚠️ 🇺🇸만기주간(핀닝/하락)</div>"

                    num_color = "#d32f2f" if i == 0 else "#1976d2" if i == 6 else "#333"
                    cell_cls = "cal-cell today" if day == today_day else "cal-cell"
                    day_lbl = f"{day} (오늘)" if day == today_day else str(day)
                    html_parts.append(f"<div class='{cell_cls}'><div class='cal-num' style='color:{num_color};'>{day_lbl}</div>{events}</div>")

        html_parts.append("</div>")
        st.markdown("".join(html_parts), unsafe_allow_html=True)

        st.markdown(
            "<div style='margin-top:10px;font-size:12px;color:#555;line-height:1.9;'>"
            "<b>범례</b> &nbsp; "
            "<span style='background:#ede7f6;color:#4527a0;padding:2px 6px;border-radius:3px;'>🏛️ 중앙은행(FOMC·ECB·BOJ·의사록)</span> "
            "<span style='background:#fff8e1;color:#ff6f00;padding:2px 6px;border-radius:3px;'>📊 물가(CPI·PCE)</span> "
            "<span style='background:#e0f7fa;color:#006064;padding:2px 6px;border-radius:3px;'>👷 경기(고용·PMI·소매판매·수출입)</span> "
            "<span style='background:#fce4ec;color:#880e4f;padding:2px 6px;border-radius:3px;'>🏦 한은 금통위</span> "
            "<span style='background:#ffebee;color:#b91c1c;padding:2px 6px;border-radius:3px;'>🔴 옵션만기</span> "
            "<span style='background:#e3f2fd;color:#1565c0;padding:2px 6px;border-radius:3px;'>🔹 위클리만기</span>"
            "</div>",
            unsafe_allow_html=True,
        )
        st.caption(
            "ℹ️ **확정 일정(2026)** — 중앙은행(FOMC·한은·ECB·BOJ)·FOMC 의사록, 미 CPI·고용지표(BLS 공식), "
            "옵션만기(미 셋째 금요일·한국 둘째 목요일, 규칙 기반). "
            "**추정 일정** — PCE·소매판매·ISM·한국 CPI·중국 PMI·한국 수출입은 통상 발표 시기 기준이라 실제 발표일과 1~2일 차이날 수 있습니다. "
            "정부 셧다운 등으로 발표일이 사후 연기될 수 있으니 중대한 매매 전엔 원출처를 확인하세요."
        )

    with cal_tab3:
        with st.spinner("최신 IPO 일정을 파싱 중입니다..."):
            ipo_df = get_naver_ipo_data()
        if not ipo_df.empty:
            active_n = (ipo_df['청약일정'].astype(str).str.strip().replace({'nan': '-'}) != '-').sum()
            st.caption(f"📋 총 {len(ipo_df)}개 종목 · 청약 일정 확정 {active_n}개 (파란 음영) ｜ "
                       "**공모가**=주식을 처음 파는 가격, **청약**=상장 전 미리 사겠다고 신청, "
                       "**경쟁률**=청약 경쟁 정도(높을수록 인기), **따상**=상장일 시초가 2배+상한가")
            sty_ipo = style_ipo_table(ipo_df)
            if sty_ipo is not None:
                st.dataframe(sty_ipo, use_container_width=True, height=460)
            else:
                st.dataframe(ipo_df, use_container_width=True, hide_index=True)
            if api_key_input:
                if st.button("🤖 AI 공모주 옥석 가리기", type="primary"):
                    with st.spinner("AI가 공모주를 분석 중입니다..."):
                        ai_cols = [c for c in ['종목명', '청약일정', '공모가', '경쟁률', '업종'] if c in ipo_df.columns]
                        st.success(ask_gemini(
                            f"다음은 예정된 IPO 공모주 목록입니다:\n{ipo_df[ai_cols].to_string()}\n"
                            "이 중 상장일 '따상(시초가 2배+상한가)' 가능성이 높은 1~2개를 꼽고, "
                            "업종 매력도·경쟁률·시장 분위기를 근거로 각 3줄 이내로 평가해줘.", api_key_input))
            else:
                st.info("💡 사이드바에 API 키를 입력하면 'AI 공모주 옥석 가리기'로 따상 후보를 분석할 수 있어요.")
        else:
            st.error("❌ 현재 예정된 신규 상장(IPO) 일정이 없거나, 거래소 데이터를 불러올 수 없습니다. (주말·연휴엔 비어 있을 수 있어요)")
