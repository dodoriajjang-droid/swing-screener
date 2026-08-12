# -*- coding: utf-8 -*-
"""💰 고배당주 파이프라인 (TOP 300)

app.py 라우팅에서 분리된 페이지. 함수 라이브러리는 core 에서 가져온다.
"""
from core import *


def render(ctx):
    _nav_changed = ctx['_nav_changed']
    api_key_input = ctx['api_key_input']

    st.subheader("💰 고배당주 파이프라인")
    st.caption("거래대금 상위 300종목을 대상으로 배당수익률을 계산합니다.")
    st.caption("🗓️ **배당주기**는 최근 12개월간 '실제 배당 지급 내역'으로 추정합니다 — 월·분기·반기·연배당. "
               "괄호 안 숫자는 배당이 들어온 '월'입니다 (예: 분기배당(3·6·9·12월)). "
               "한국거래소(pykrx) 공식데이터로 잡힌 종목은 지급일 정보가 없어 통상값인 '연 1회(추정)'로 표기되며, "
               "야후(yfinance)로 조회된 종목은 실제 지급월 기준으로 표시됩니다.")

    hcol1, hcol2 = st.columns([5, 1])
    with hcol2:
        if st.button("🔄 데이터 다시 불러오기", use_container_width=True, key="div_refetch"):
            get_dividend_portfolio.clear()   # 이 함수의 캐시만 비우고 즉시 재조회
            st.rerun()

    with st.spinner("배당 데이터를 다운로드 중입니다..."): 
        div_dfs = get_dividend_portfolio(st.session_state.get('ex_rate', 1350.0))
        
    sort_opt = st.radio("⬇ 정렬 기준", ["기본 (분류순)", "예상 배당금 높은순", "현재가 높은순", "현재가 낮은순"], horizontal=True)
    
    def apply_sort(df, opt):
        if df.empty: return df
        temp_df = df.copy()
        if opt == "기본 (분류순)": return temp_df 
        def ex_val(val_str):
            try: return float(str(val_str).split('(')[0].replace(',', '').replace('원', '').replace('$', '').strip())
            except Exception as _dg_e: _diag_note("ex_val", _dg_e); return 0.0
        sort_col = '예상 배당금' if "배당금" in opt else '현재가'
        temp_df['__sort'] = temp_df[sort_col].apply(lambda x: ex_val(x))
        if opt == "현재가 낮은순": return pd.concat([temp_df[temp_df['__sort']>0].sort_values('__sort'), temp_df[temp_df['__sort']==0]]).drop(columns=['__sort'])
        return temp_df.sort_values('__sort', ascending=False).drop(columns=['__sort'])

    t1, t2, t3 = st.tabs(["🇰🇷 국장", "🇺🇸 미장", "📈 ETF"])
    
    with t1: 
        if div_dfs["KRX"].empty:
            st.error("🚨 국내 주식 배당 데이터를 불러오지 못했습니다.")
            st.caption("• 클라우드(서버) 환경에서는 한국거래소(pykrx)·야후 접속이 일시 차단될 수 있습니다.\n"
                       "• 위의 [🔄 데이터 다시 불러오기]를 눌러 재시도해 주세요. (캐시를 비우고 새로 조회합니다)\n"
                       "• 계속 실패하면 requirements.txt 에 `yfinance`, `pykrx`, `yahooquery` 가 포함됐는지 확인하세요.")
        else:
            st.dataframe(apply_sort(div_dfs["KRX"], sort_opt), use_container_width=True, hide_index=True)
            
    with t2: 
        if div_dfs["US"].empty:
            st.error("🚨 미국 주식 배당 데이터를 가져오지 못했습니다.")
            st.caption("• Yahoo Finance 접속이 일시 제한됐을 수 있습니다. 위의 [🔄 데이터 다시 불러오기]로 재시도해 주세요.\n"
                       "• 계속 실패하면 requirements.txt 에 `yfinance` 설치 여부를 확인하세요.")
        else:
            st.dataframe(apply_sort(div_dfs["US"], sort_opt), use_container_width=True, hide_index=True)
            
    with t3: 
        if div_dfs["ETF"].empty:
            st.error("🚨 ETF 배당 데이터를 가져오지 못했습니다.")
            st.caption("• Yahoo Finance 접속이 일시 제한됐을 수 있습니다. 위의 [🔄 데이터 다시 불러오기]로 재시도해 주세요.\n"
                       "• 계속 실패하면 requirements.txt 에 `yfinance` 설치 여부를 확인하세요.")
        else:
            st.dataframe(apply_sort(div_dfs["ETF"], sort_opt), use_container_width=True, hide_index=True)
