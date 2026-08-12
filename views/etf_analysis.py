# -*- coding: utf-8 -*-
"""📊 국내외 핵심 ETF 분석

app.py 라우팅에서 분리된 페이지. 함수 라이브러리는 core 에서 가져온다.
"""
from core import *


def render(ctx):
    _nav_changed = ctx['_nav_changed']
    api_key_input = ctx['api_key_input']

    st.markdown("## 📊 국내외 핵심 ETF 분석")
    etf_tab1, etf_tab2 = st.tabs(["🇰🇷 국내 핵심 ETF", "🇺🇸 미국 핵심 ETF"])
    
    with etf_tab1:
        st.subheader("국내 상장 주요 ETF (TOP 50)")
        with st.spinner("국내 ETF 실시간 데이터를 불러오는 중..."):
            try:
                krx_etf = get_krx_etf_list()
                if not krx_etf.empty:
                    price_col = 'Close' if 'Close' in krx_etf.columns else 'Price'
                    display_etf = krx_etf[['Symbol', 'Name', price_col, 'Change', 'Volume']].head(50).copy()
                    
                    # 💡 [핵심 버그 수정] Change 컬럼은 '등락률(%)'이 아니라 '등락금액(원)'입니다!
                    # 따라서 (등락금액 / 전일종가) * 100 으로 실제 등락률(%)을 직접 계산합니다.
                    def calc_pct_change(row):
                        try:
                            current_price = float(row[price_col])
                            change_amount = float(row['Change'])
                            prev_price = current_price - change_amount  # 전일종가 역산
                            if prev_price > 0:
                                return (change_amount / prev_price) * 100
                            return 0.0
                        except Exception as _dg_e:
                            _diag_note("calc_pct_change", _dg_e)
                            return 0.0
                            
                    display_etf['ChangeRatio'] = display_etf.apply(calc_pct_change, axis=1)
                    
                    # UI 표출용으로 컬럼 재배치 및 이름 변경
                    display_etf = display_etf[['Symbol', 'Name', price_col, 'ChangeRatio', 'Volume']]
                    display_etf.columns = ['종목코드', '종목명', '현재가', '등락률', '거래량']
                    
                    display_etf['등락률'] = display_etf['등락률'].apply(lambda x: f"{x:+.2f}%")
                    display_etf['현재가'] = display_etf['현재가'].apply(lambda x: f"{int(x):,}원" if pd.notna(x) else "0원")
                    display_etf['거래량'] = display_etf['거래량'].apply(lambda x: f"{int(x):,}" if pd.notna(x) else "0")
                    
                    st.dataframe(display_etf, use_container_width=True, hide_index=True)
            except Exception as e:
                st.error(f"ETF 스크래핑 에러: {e}")
                krx_etf = pd.DataFrame()
                
        st.divider()
        st.subheader("🔍 개별 ETF 정밀 타점 분석 (전체 화면)")
        if not krx_etf.empty:
            etf_opts = ["선택하세요"] + (krx_etf['Name'].astype(str) + " (" + krx_etf['Symbol'].astype(str) + ")").tolist()
            sel_etf = st.selectbox("분석할 ETF 선택:", etf_opts, label_visibility="collapsed")
            if sel_etf != "선택하세요":
                e_name = sel_etf.rsplit(" (", 1)[0]
                e_code = sel_etf.rsplit("(", 1)[-1].replace(")", "").strip()
                with st.spinner(f"'{e_name}' 타점 분석 중..."):
                    res = analyze_technical_pattern(e_name, e_code)
                    if res: draw_stock_card(res, api_key_str=api_key_input, is_expanded=True, key_suffix="kr_etf")
                
    with etf_tab2:
        st.subheader("미국 상장 주요 메가 ETF")
        us_etfs = ['SPY', 'QQQ', 'DIA', 'IWM', 'SCHD', 'JEPI', 'VOO', 'VTI', 'ARKK', 'SMH', 'SOXX', 'XLK', 'XLF', 'XLV', 'TLT', 'TMF']
        with st.spinner("미국 ETF 데이터를 불러오는 중..."):
            us_data_df = get_us_etf_summary(us_etfs)
            if not us_data_df.empty: 
                st.dataframe(us_data_df, use_container_width=True, hide_index=True)
                
        st.divider()
        st.subheader("🔍 미국 ETF 정밀 타점 분석 (전체 화면)")
        sel_us_etf = st.selectbox("분석할 미국 ETF 선택:", ["선택하세요"] + us_etfs)
        if sel_us_etf != "선택하세요":
            with st.spinner(f"'{sel_us_etf}' 타점 분석 중..."):
                res = analyze_technical_pattern(sel_us_etf, sel_us_etf)
                if res: draw_stock_card(res, api_key_str=api_key_input, is_expanded=True, key_suffix="us_etf")
