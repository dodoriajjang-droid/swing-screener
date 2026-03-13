import streamlit as st
import pandas as pd
import numpy as np
import requests
from bs4 import BeautifulSoup
from io import StringIO
import yfinance as yf
import FinanceDataReader as fdr
from datetime import datetime, timedelta
import google.generativeai as genai
import urllib.parse
import re
import plotly.express as px
import plotly.graph_objects as go
from streamlit_autorefresh import st_autorefresh
import streamlit.components.v1 as components

# ==========================================
# 1. 초기 설정 
# ==========================================
st.set_page_config(page_title="Jaemini 주식 검색기", layout="wide", page_icon="📈")

st_autorefresh(interval=300000, limit=None, key="news_autorefresh")

# 세션 상태 초기화 (관심종목 추가)
for key in ['seen_links', 'seen_titles', 'news_data', 'watchlist']:
    if key not in st.session_state:
        st.session_state[key] = set() if 'seen' in key else []

# ==========================================
# 2. 데이터 수집 및 분석 함수들
# ==========================================
@st.cache_data(ttl=3600)
def get_macro_indicators():
    results = {}
    tickers = {"VIX": "^VIX", "美 10년물 국채": "^TNX", "필라델피아 반도체": "^SOX", "WTI 원유": "CL=F", "원/달러 환율": "KRW=X"}
    for name, ticker in tickers.items():
        try:
            df = yf.Ticker(ticker).history(period="5d")
            if not df.empty and len(df) >= 2:
                results[name] = {"value": float(df['Close'].iloc[-1]), "delta": float(df['Close'].iloc[-1] - df['Close'].iloc[-2]), "prev": float(df['Close'].iloc[-2])}
        except: pass
    return results if results else None

@st.cache_data(ttl=3600)
def get_fear_and_greed():
    url = "https://production.dataviz.cnn.io/index/fearandgreed/graphdata"
    headers = {"User-Agent": "Mozilla/5.0", "Accept": "application/json", "Origin": "https://edition.cnn.com", "Referer": "https://edition.cnn.com/"}
    try:
        res = requests.get(url, headers=headers, timeout=5)
        if res.status_code != 200: res = requests.get(f"https://api.allorigins.win/raw?url={urllib.parse.quote(url)}", headers={"User-Agent": "Mozilla/5.0"}, timeout=5)
        if res.status_code == 200:
            data = res.json()
            return {"score": round(data['fear_and_greed']['score']), "delta": round(data['fear_and_greed']['score'] - data['fear_and_greed']['previous_close']), "rating": data['fear_and_greed']['rating'].capitalize()}
    except: pass
    return None

@st.cache_data(ttl=3600)
def get_us_top_gainers():
    try:
        response = requests.get('https://finance.yahoo.com/gainers', headers={'User-Agent': 'Mozilla/5.0'})
        df = pd.read_html(StringIO(response.text))[0].iloc[:, :6]
        df.columns = ['종목코드', '기업명', '현재가', '등락금액', '등락률', '거래량']
        df['실제등락률'] = df['등락률'].apply(lambda x: float(re.sub(r'[^\d\.\+\-]', '', str(x))) if pd.notnull(x) else 0.0)
        df = df[df['실제등락률'] >= 10.0].drop(columns=['실제등락률'])
        df['종목코드'] = df['종목코드'].astype(str).apply(lambda x: x.split()[0])
        try: ex_rate = yf.Ticker("KRW=X").history(period="5d")['Close'].iloc[-1]
        except: ex_rate = 1350.0 
        df['현재가'] = df['현재가'].apply(lambda x: f"${float(str(x).split()[0].replace(',', '')):.2f} (약 {int(float(str(x).split()[0].replace(',', '')) * ex_rate):,}원)" if pd.notnull(x) else x)
        return df, ex_rate
    except: return pd.DataFrame(), 1350.0

@st.cache_data(ttl=86400)
def get_krx_stocks():
    try:
        df = fdr.StockListing('KRX')
        if not df.empty: return df[['Name', 'Code', 'Sector']] # 섹터 데이터 포함
    except: pass
    return pd.DataFrame(columns=['Name', 'Code', 'Sector'])

@st.cache_data(ttl=300)
def get_latest_naver_news():
    try:
        res = requests.get("https://finance.naver.com/news/news_list.naver?mode=LSS2D&section_id=101&section_id2=258", headers={"User-Agent": "Mozilla/5.0"})
        soup = BeautifulSoup(res.content.decode('euc-kr', errors='replace'), 'html.parser')
        return [{"title": tag.get_text(strip=True), "link": "https://finance.naver.com" + tag['href'] if tag['href'].startswith("/") else tag['href']} for tag in soup.select("dl dd.articleSubject a")]
    except: return []

def update_news_state():
    items = get_latest_naver_news()
    time_str = (datetime.utcnow() + timedelta(hours=9)).strftime("%H:%M")
    for item in reversed(items): 
        if item['link'] not in st.session_state.seen_links and item['title'] not in st.session_state.seen_titles:
            st.session_state.news_data.insert(0, {"time": time_str, "title": item['title'], "link": item['link']})
            st.session_state.seen_links.add(item['link'])
            st.session_state.seen_titles.add(item['title'])

@st.cache_data(ttl=3600)
def ask_gemini(prompt, api_key):
    if not api_key: return "API 키가 필요합니다."
    try:
        genai.configure(api_key=api_key)
        return genai.GenerativeModel('gemini-2.5-flash').generate_content(prompt).text
    except Exception as e: return f"AI 분석 오류: {str(e)}"

# 👈 [핵심 추가] 네이버 연속 순매수 추적기
@st.cache_data(ttl=3600)
def get_investor_trend(code):
    try:
        res = requests.get(f"https://finance.naver.com/item/frgn.naver?code={code}", headers={"User-Agent": "Mozilla/5.0"}, timeout=3)
        soup = BeautifulSoup(res.text, 'html.parser')
        rows = soup.select('table.type2')[1].select('tr')
        inst_sum, forgn_sum, inst_streak, forgn_streak = 0, 0, 0, 0
        inst_break, forgn_break = False, False
        count = 0
        for row in rows:
            tds = row.select('td')
            if len(tds) < 9 or not tds[0].text.strip(): continue 
            try:
                i_val = int(tds[5].text.strip().replace(',', '').replace('+', ''))
                f_val = int(tds[6].text.strip().replace(',', '').replace('+', ''))
                inst_sum += i_val
                forgn_sum += f_val
                
                # 연속 순매수 계산
                if i_val > 0 and not inst_break: inst_streak += 1
                elif i_val <= 0: inst_break = True
                
                if f_val > 0 and not forgn_break: forgn_streak += 1
                elif f_val <= 0: forgn_break = True
                
                count += 1
            except: pass
            if count >= 5: break 
            
        def fmt(v, streak): 
            base = f"+{v:,}" if v > 0 else f"{v:,}"
            if streak >= 3: return f"{base} (🔥{streak}일 연속 매집)"
            return f"{base} ({'🔥매집' if v>0 else '💧매도' if v<0 else '➖중립'})"
            
        return fmt(inst_sum, inst_streak), fmt(forgn_sum, forgn_streak)
    except: return "조회불가", "조회불가"

# 👈 [핵심 추가] 재무 데이터 (PER, PBR) 추출기
def get_fundamentals(ticker_code):
    try:
        info = yf.Ticker(f"{ticker_code}.KS" if ticker_code.isdigit() else ticker_code).info
        return info.get('trailingPE', 'N/A'), info.get('priceToBook', 'N/A')
    except: return 'N/A', 'N/A'

# 👈 [핵심 추가] OBV 및 이평선 정배열 로직 추가
@st.cache_data(ttl=3600)
def analyze_technical_pattern(stock_name, ticker_code):
    if not ticker_code: return None
    try:
        df = fdr.DataReader(ticker_code, (datetime.now() - timedelta(days=150)).strftime('%Y-%m-%d'))
        if len(df) < 60: return None
        
        # 이동평균선
        df['MA5'] = df['Close'].rolling(window=5).mean()
        df['MA20'] = df['Close'].rolling(window=20).mean()
        df['MA60'] = df['Close'].rolling(window=60).mean()
        
        # 볼린저 밴드 & RSI
        df['Vol_MA20'] = df['Volume'].rolling(window=20).mean()
        df['Std_20'] = df['Close'].rolling(window=20).std()
        df['Bollinger_Upper'] = df['MA20'] + (df['Std_20'] * 2)
        delta = df['Close'].diff()
        rs = (delta.where(delta > 0, 0.0).rolling(14).mean()) / (-delta.where(delta < 0, 0.0).rolling(14).mean())
        df['RSI'] = 100 - (100 / (1 + rs))
        
        # OBV (거래량 누적 지표)
        df['OBV'] = (np.sign(df['Close'].diff()) * df['Volume']).fillna(0).cumsum()
        
        latest = df.iloc[-1]
        prev = df.iloc[-2]
        current_price = int(latest['Close'])
        
        # 배열 상태 판별
        if latest['MA5'] > latest['MA20'] > latest['MA60']: align_status = "🔥 완벽 정배열 (상승 추세)"
        elif latest['MA5'] < latest['MA20'] < latest['MA60']: align_status = "❄️ 역배열 (하락 추세)"
        elif latest['MA5'] > latest['MA20'] and prev['MA5'] <= prev['MA20']: align_status = "✨ 5일-20일 골든크로스"
        else: align_status = "🌀 혼조세/횡보"
        
        if (latest['MA20'] * 0.97) <= current_price <= (latest['MA20'] * 1.03): status = "✅ 타점 근접 (분할 매수)"
        elif current_price > (latest['MA20'] * 1.03): status = "⚠️ 이격 과다 (눌림목 대기)"
        else: status = "🛑 20일선 이탈 (관망)"
        
        inst_vol, forgn_vol = get_investor_trend(ticker_code)
        per, pbr = get_fundamentals(ticker_code)
            
        return {
            "종목명": stock_name, "티커": ticker_code, "현재가": current_price, "상태": status,
            "진입가_가이드": int(latest['MA20']), "목표가1": int(latest['Bollinger_Upper']), 
            "목표가2": int(df['Close'].max()) if int(df['Close'].max()) > (int(latest['Bollinger_Upper']) * 1.02) else int(latest['Bollinger_Upper'] * 1.05),
            "손절가": int(latest['MA20'] * 0.97),
            "거래량 급증": "🔥 거래량 터짐" if df.iloc[-10:]['Volume'].max() > (df.iloc[-10:]['Vol_MA20'].mean() * 2) else "평이함",
            "RSI": latest['RSI'], "배열상태": align_status, "기관수급": inst_vol, "외인수급": forgn_vol,
            "PER": per, "PBR": pbr, "OBV": df['OBV'].tail(20),
            "종가 데이터": df['Close'].tail(20), "거래량 데이터": df['Volume'].tail(20)
        }
    except: return None

# ==========================================
# UI 컴포넌트: 주식 카드 그리기 (관심종목 버튼 포함)
# ==========================================
def draw_stock_card(tech_result, api_key=None, is_expanded=False, key_suffix="default"):
    status_emoji = tech_result['상태'].split(' ')[0]
    with st.expander(f"{status_emoji} {tech_result['종목명']} (현재가: {tech_result['현재가']:,}원) ｜ RSI: {tech_result['RSI']:.1f} ｜ {tech_result['배열상태']}", expanded=is_expanded):
        
        # 👈 [관심종목 추가 버튼]
        col_btn1, col_btn2 = st.columns([8, 2])
        col_btn1.markdown(f"**진단:** {tech_result['상태']} ｜ **수급:** {tech_result['거래량 급증']} ｜ **PER:** {tech_result['PER']} ｜ **PBR:** {tech_result['PBR']}")
        
        # 관심종목 리스트에 있는지 확인
        is_in_watchlist = any(x['티커'] == tech_result['티커'] for x in st.session_state.watchlist)
        if col_btn2.button("⭐ 관심종목 추가" if not is_in_watchlist else "🌟 추가됨", disabled=is_in_watchlist, key=f"star_{tech_result['티커']}_{key_suffix}"):
            st.session_state.watchlist.append({'종목명': tech_result['종목명'], '티커': tech_result['티커']})
            st.rerun()

        c1, c2, c3, c4 = st.columns(4)
        curr = tech_result['현재가']
        c1.metric("📌 진입 기준가 (20일선)", f"{tech_result['진입가_가이드']:,}원", f"{tech_result['진입가_가이드'] - curr:,}원 (대비)", delta_color="off")
        c2.metric("🎯 1차 (볼밴상단)", f"{tech_result['목표가1']:,}원", f"+{tech_result['목표가1'] - curr:,}원", delta_color="normal")
        c3.metric("🚀 2차 (스윙전고)", f"{tech_result['목표가2']:,}원", f"+{tech_result['목표가2'] - curr:,}원", delta_color="normal")
        c4.metric("🛑 손절 라인", f"{tech_result['손절가']:,}원", f"{tech_result['손절가'] - curr:,}원 (리스크)", delta_color="normal")
        
        st.markdown("---")
        c5, c6 = st.columns([1, 2])
        c5.metric("📊 RSI (상대강도)", f"{tech_result['RSI']:.1f}", "🔴 과열" if tech_result['RSI'] >= 70 else "🔵 바닥" if tech_result['RSI'] <= 30 else "⚪ 보통", delta_color="inverse" if tech_result['RSI'] >= 70 else "normal")
        with c6: st.markdown(f"🕵️ **최근 수급 동향 (5일 누적)**<br>**외국인:** `{tech_result['외인수급']}` ｜ **기관:** `{tech_result['기관수급']}`", unsafe_allow_html=True)
        
        # 👈 [핵심 추가] 재무 데이터 주입된 AI 매매 의견
        if api_key:
            st.markdown("<br>", unsafe_allow_html=True)
            if st.button(f"🤖 '{tech_result['종목명']}' AI 적정가 판단 및 매매 의견", key=f"ai_btn_{tech_result['티커']}_{key_suffix}"):
                with st.spinner("AI가 재무(PER/PBR) 및 차트를 종합 분석 중입니다..."):
                    prompt = f"트레이더로서 분석 요망. 종목: {tech_result['종목명']}. 현재가: {curr}, 20일선: {tech_result['진입가_가이드']}, RSI: {tech_result['RSI']:.1f}, PER: {tech_result['PER']}, PBR: {tech_result['PBR']}. 1.가치평가(비싼지/싼지) 2.타점분석(차트상 위치) 3.최종액션(적극매수/분할매수/관망/매수금지 중 택1 및 이유 1줄)"
                    st.success(ask_gemini(prompt, api_key))
        
        ch1, ch2 = st.columns(2)
        price_df = tech_result["종가 데이터"].reset_index()
        price_df['Date_Str'] = price_df['Date'].dt.strftime('%m/%d') 
        vol_df = tech_result["거래량 데이터"].reset_index()
        vol_df['Date_Str'] = vol_df['Date'].dt.strftime('%m/%d')
        
        with ch1:
            st.caption("📈 주가 흐름 (최근 20일)")
            fig_price = px.line(price_df, x='Date_Str', y='Close', markers=True)
            fig_price.update_layout(margin=dict(l=0, r=0, t=10, b=0), xaxis_title="", yaxis_title="", yaxis_tickformat=",", hovermode="x unified", xaxis=dict(showgrid=False, type='category'), height=220)
            fig_price.update_traces(line_color="#FF4B4B", hovertemplate="<b>%{y:,}원</b>")
            st.plotly_chart(fig_price, use_container_width=True, config={'displayModeBar': False}, key=f"p_{tech_result['티커']}_{key_suffix}")
            
        with ch2:
            st.caption("📊 거래량 (막대) & OBV 누적 (꺾은선)")
            fig_vol = go.Figure()
            fig_vol.add_trace(go.Bar(x=vol_df['Date_Str'], y=vol_df['Volume'], name="거래량", marker_color="#1f77b4"))
            # 👈 OBV 차트 겹쳐 그리기
            fig_vol.add_trace(go.Scatter(x=vol_df['Date_Str'], y=tech_result['OBV'], name="OBV", yaxis="y2", line=dict(color="orange", width=2)))
            fig_vol.update_layout(
                margin=dict(l=0, r=0, t=10, b=0), xaxis=dict(showgrid=False, type='category'), hovermode="x unified", height=220, showlegend=False,
                yaxis=dict(title="", showgrid=False), yaxis2=dict(title="", overlaying="y", side="right", showgrid=False, showticklabels=False)
            )
            st.plotly_chart(fig_vol, use_container_width=True, config={'displayModeBar': False}, key=f"v_{tech_result['티커']}_{key_suffix}")

# ==========================================
# 3. 사이드바 및 메인 화면 구성
# ==========================================
st.title("📈 Jaemini PRO 트레이딩 대시보드")
st.markdown("단기 스윙 매매를 위한 **수급 추적** 및 **실시간 타점 모니터링** 시스템입니다.")

macro_data = get_macro_indicators()
fg_data = get_fear_and_greed()

m_col1, m_col2, m_col3 = st.columns([1, 1, 2])

# 게이지 차트 그리는 공통 함수 적용으로 코드 압축
def draw_gauge(val, prev, title, steps, is_error=False):
    if is_error: return go.Figure(go.Indicator(mode="gauge", value=0, title={'text': f"<b>{title}</b><br><span style='font-size:12px;color:red'>데이터 로딩 지연중</span>"}, gauge={'axis': {'range': [0, steps[-1]['range'][1]]}, 'bar': {'color': "gray"}}))
    return go.Figure(go.Indicator(mode="gauge+number+delta", value=val, title={'text': title}, delta={'reference': prev, 'position': "top"}, gauge={'axis': {'range': [0, steps[-1]['range'][1]], 'tickwidth': 1, 'tickcolor': "darkblue"}, 'bar': {'color': "black", 'thickness': 0.2}, 'bgcolor': "white", 'borderwidth': 1, 'bordercolor': "gray", 'steps': steps}))

with m_col1:
    steps_vix = [{'range': [0, 15], 'color': "rgba(0, 255, 0, 0.3)"}, {'range': [15, 20], 'color': "rgba(255, 255, 0, 0.3)"}, {'range': [20, 30], 'color': "rgba(255, 165, 0, 0.3)"}, {'range': [30, 50], 'color': "rgba(255, 0, 0, 0.3)"}]
    fig_vix = draw_gauge(macro_data['VIX']['value'], macro_data['VIX']['prev'], "<b>VIX (공포지수)</b><br><span style='font-size:12px;color:gray'>20: 경계 ｜ 30: 현금확대</span>", steps_vix) if macro_data and 'VIX' in macro_data else draw_gauge(0,0,"VIX", steps_vix, True)
    fig_vix.update_layout(margin=dict(l=10, r=10, t=80, b=10), height=250)
    st.plotly_chart(fig_vix, use_container_width=True)

with m_col2:
    steps_fg = [{'range': [0, 25], 'color': "rgba(255, 0, 0, 0.4)"}, {'range': [25, 45], 'color': "rgba(255, 165, 0, 0.4)"}, {'range': [45, 55], 'color': "rgba(255, 255, 0, 0.4)"}, {'range': [55, 75], 'color': "rgba(144, 238, 144, 0.4)"}, {'range': [75, 100], 'color': "rgba(0, 128, 0, 0.4)"}]
    fig_fg = draw_gauge(fg_data['score'], fg_data['score'] - fg_data['delta'], "<b>CNN 공포/탐욕 지수</b><br><span style='font-size:12px;color:gray'>25이하: 줍줍 ｜ 75이상: 매도</span>", steps_fg) if fg_data else draw_gauge(0,0,"CNN 공포/탐욕 지수", steps_fg, True)
    fig_fg.update_layout(margin=dict(l=10, r=10, t=80, b=10), height=250)
    st.plotly_chart(fig_fg, use_container_width=True)
    
with m_col3:
    with st.container(border=True):
        st.markdown("<br>", unsafe_allow_html=True)
        c1, c2 = st.columns(2)
        if macro_data:
            if '美 10년물 국채' in macro_data: c1.metric("🏦 美 10년물 국채", f"{macro_data['美 10년물 국채']['value']:.3f}%", f"{macro_data['美 10년물 국채']['delta']:.3f}%", delta_color="inverse")
            if '원/달러 환율' in macro_data: c2.metric("💱 원/달러 환율", f"{macro_data['원/달러 환율']['value']:.1f}원", f"{macro_data['원/달러 환율']['delta']:.1f}원", delta_color="inverse")
            st.markdown("---")
            c3, c4 = st.columns(2)
            if '필라델피아 반도체' in macro_data: c3.metric("💻 필라델피아 반도체(SOX)", f"{macro_data['필라델피아 반도체']['value']:.1f}", f"{macro_data['필라델피아 반도체']['delta']:.1f}")
            if 'WTI 원유' in macro_data: c4.metric("🛢️ WTI 원유 (달러)", f"{macro_data['WTI 원유']['value']:.2f}", f"{macro_data['WTI 원유']['delta']:.2f}")

with st.sidebar:
    st.header("⚙️ 대시보드 컨트롤")
    if st.button("🔄 증시 데이터 리로드", type="primary", use_container_width=True): st.cache_data.clear()
    st.divider()
    st.header("🧠 AI 엔진 연결 상태")
    api_key_input = st.secrets["GEMINI_API_KEY"] if "GEMINI_API_KEY" in st.secrets else st.text_input("Gemini API Key를 입력하세요", type="password")
    if api_key_input: st.success("✅ 시스템 연동 완료 (정상)")

if "gainers_df" not in st.session_state:
    with st.spinner('📡 글로벌 증시 데이터를 수집하는 중입니다...'):
        df, ex_rate = get_us_top_gainers()
        st.session_state.gainers_df = df
        st.session_state.ex_rate = ex_rate

# 👈 [탭 추가] 8개의 탭으로 구성
tab1, tab2, tab3, tab4, tab5, tab6, tab7, tab8 = st.tabs(["🔥 🇺🇸 미국 폭등주", "🎯 국내 타점 진단", "💡 AI 테마 검색", "📰 속보 필터링", "💸 자금 흐름(히트맵)", "📅 증시 캘린더", "💰 배당주(TOP 60)", "⭐ 내 관심종목"])

with tab1:
    st.markdown("<br>", unsafe_allow_html=True)
    col1, col2 = st.columns([1, 1.2], gap="large")
    with col1:
        st.subheader("🔥 미국장 폭등주 (+10% 이상)")
        if not st.session_state.gainers_df.empty:
            tickers_list = st.session_state.gainers_df['종목코드'].tolist()
            sector_dict = get_all_sector_info(tuple(tickers_list), api_key_input) if api_key_input else {t: ("분석 대기", "분석 대기") for t in tickers_list}
            display_df = st.session_state.gainers_df.copy()
            opts = ["🔍 종목 선택"]
            for i, row in display_df.iterrows():
                sec, ind = sector_dict.get(row['종목코드'], ("분석 불가", "분석 불가"))
                opts.append(f"{row['종목코드']} ({row['기업명'].split(' / ')[-1] if ' / ' in row['기업명'] else row['기업명']}) - ({sec} / {ind})")
            st.dataframe(display_df, use_container_width=True, hide_index=True, height=400)
            sel_opt = st.selectbox("#### 🔍 분석 대상 종목 선택", opts)
            sel_tick = "N/A" if sel_opt == "🔍 종목 선택" else sel_opt.split(" ")[0]
        else: sel_tick = "N/A"; st.info("현재 +10% 이상 급등한 종목이 없습니다.")
    with col2:
        st.subheader("🎯 연관 테마 매칭 및 타점 진단")
        if sel_tick != "N/A" and api_key_input:
            sec, ind = sector_dict.get(sel_tick, ("분석 불가", "분석 불가"))
            st.markdown(f"**🏷️ 섹터 정보:** `{sec}` / `{ind}`")
            with st.spinner('✨ AI가 연관된 한국 수혜주를 샅샅이 검색하고 타점을 계산 중입니다...'):
                kor_stocks = get_ai_matched_stocks(sel_tick, sec, ind, sel_opt.split(" - ")[0], api_key_input)
                if kor_stocks:
                    for i, (name, code) in enumerate(kor_stocks):
                        res = analyze_technical_pattern(name, code)
                        if res: draw_stock_card(res, api_key=api_key_input, key_suffix=f"t1_{i}")

with tab2:
    st.markdown("<br>", unsafe_allow_html=True)
    st.subheader("🔍 국내 개별 종목 정밀 타점 진단기")
    krx_df = get_krx_stocks()
    if not krx_df.empty:
        opts = ["🔍 검색 종목을 입력하세요."] + (krx_df['Name'] + " (" + krx_df['Code'] + ")").tolist()
        query = st.selectbox("👇 종목명 또는 초성을 입력하여 검색하세요:", opts)
        if query != "🔍 검색 종목을 입력하세요.":
            with st.spinner(f"📡 타점 분석 중..."):
                res = analyze_technical_pattern(query.split(" (")[0], query.split("(")[1].replace(")", ""))
            if res: draw_stock_card(res, api_key=api_key_input, is_expanded=True, key_suffix="t2")

with tab3:
    st.markdown("<br>", unsafe_allow_html=True)
    st.subheader("💡 테마 및 관련주 실시간 AI 발굴기")
    hot_themes = get_trending_themes_with_ai(api_key_input)
    cols = st.columns(len(hot_themes))
    clicked_theme = None
    for i, theme in enumerate(hot_themes):
        if cols[i].button(theme, use_container_width=True): clicked_theme = theme
    query = st.text_input("🔍 테마 입력:", value=clicked_theme if clicked_theme else "")
    if query and api_key_input:
        with st.spinner(f"✨ '{query}' 관련주 진단 중..."):
            theme_stocks = get_theme_stocks_with_ai(query, api_key_input)
            if theme_stocks:
                for i, (name, code) in enumerate(theme_stocks):
                    res = analyze_technical_pattern(name, code)
                    if res: draw_stock_card(res, api_key=api_key_input, key_suffix=f"t3_{i}")

with tab4:
    st.markdown("<br>", unsafe_allow_html=True)
    cols_top = st.columns([4, 1])
    cols_top[0].subheader("📰 트레이더용 실시간 금융 속보")
    if cols_top[1].button("🔄 리로드", use_container_width=True): get_latest_naver_news.clear()
    keywords = [k.strip() for k in st.text_input("핵심 키워드 필터:", value="AI, 반도체, 데이터센터, 원전, 로봇, 바이오").split(",") if k.strip()]
    only_kw = st.checkbox("🔥 위 키워드가 포함된 뉴스만 보기", value=False)
    update_news_state()
    st.divider()
    if st.session_state.news_data:
        for i, news in enumerate(st.session_state.news_data[:50]):
            has_kw = any(k.lower() in news['title'].lower() for k in keywords)
            if only_kw and not has_kw: continue
            with st.container(border=True):
                cols = st.columns([6, 1.5, 1])
                cols[0].markdown(f"**🕒 {news['time']}** | {'🔥 **'+news['title']+'**' if has_kw else news['title']}")
                if cols[1].button("🤖 AI 뉴스 판독", key=f"n_{i}") and api_key_input:
                    st.info(ask_gemini(f"속보 트레이딩 관점 분석(팩트/선반영/전략): {news['title']}", api_key_input))
                cols[2].link_button("원문 🔗", news['link'], use_container_width=True)

# 👈 [핵심 추가] 탭 5: 섹터별 자금 흐름 히트맵 (Treemap)
with tab5:
    st.markdown("<br>", unsafe_allow_html=True)
    st.subheader("💸 시장 주도주 & 자금 흐름 히트맵")
    st.write("오늘 하루 한국 증시에서 돈이 가장 많이 몰리는 섹터와 종목을 한눈에 파악하세요.")
    
    with st.spinner("📡 거래소 데이터와 섹터 맵을 생성 중입니다..."):
        t_kings = get_trading_value_kings()
        all_krx = get_krx_stocks() # 섹터 정보가 들어있는 전체 목록
        
    if not t_kings.empty and not all_krx.empty:
        # 트리맵을 위한 데이터 병합
        merged_df = pd.merge(t_kings, all_krx[['Code', 'Sector']], on='Code', how='left')
        merged_df['Sector'] = merged_df['Sector'].fillna("기타/분류불가")
        
        # 트리맵 그리기
        fig_tree = px.treemap(
            merged_df, 
            path=[px.Constant("한국증시 주도섹터"), 'Sector', 'Name'], 
            values='Amount_Ouk', 
            color='ChagesRatio', 
            color_continuous_scale='RdYlGn',
            color_continuous_midpoint=0,
            hover_data={'Amount_Ouk': ':.0f'}
        )
        fig_tree.update_layout(margin=dict(t=30, l=10, r=10, b=10), height=500)
        fig_tree.update_traces(hovertemplate="<b>%{label}</b><br>등락률: %{color:.2f}%<br>거래대금: %{value:,}억")
        st.plotly_chart(fig_tree, use_container_width=True)
        
        st.markdown("### 🎯 주도주 즉시 타점 진단")
        opts = ["🔍 종목을 선택하세요."] + (t_kings['Name'] + " (" + t_kings['Code'] + ")").tolist()
        sel_king = st.selectbox("목록에서 타점을 확인할 종목을 고르세요:", opts)
        if sel_king != "🔍 종목을 선택하세요.":
            res = analyze_technical_pattern(sel_king.split(" (")[0], sel_king.split("(")[1].replace(")", ""))
            if res: draw_stock_card(res, api_key=api_key_input, is_expanded=True, key_suffix="t5")

with tab6:
    st.markdown("<br>", unsafe_allow_html=True)
    st.subheader("📅 핵심 증시 일정 모니터링")
    cal_tab1, cal_tab2 = st.tabs(["🌍 글로벌 주요 경제 지표 (TradingView)", "🇰🇷 국내 주요 증시 일정 (Naver)"])
    with cal_tab1:
        components.html("""<iframe scrolling="yes" allowtransparency="true" frameborder="0" src="https://s.tradingview.com/embed-widget/events/?locale=kr&importanceFilter=-1%2C0%2C1&currencyFilter=USD%2CKRW%2CCNY%2CEUR&colorTheme=light" style="box-sizing: border-box; height: 600px; width: 100%;"></iframe>""", height=600)
    with cal_tab2:
        st.info("💡 **[IPO 일정]** 이번 달 수급에 가장 직접적인 영향을 주는 국내 주식 신규상장(IPO) 표입니다.")
        try:
            res = requests.get("https://finance.naver.com/sise/ipo.naver", headers={"User-Agent": "Mozilla/5.0"}, timeout=5)
            tables = pd.read_html(StringIO(res.content.decode('euc-kr')))
            for t in tables:
                if '종목명' in t.columns and '상장일' in t.columns:
                    t = t.dropna(subset=['종목명', '상장일'])
                    if not t.empty: st.dataframe(t[['종목명', '현재가', '공모가', '청약일', '상장일']].head(15), use_container_width=True, hide_index=True); break
        except: st.warning("⚠️ 자동 표 가져오기가 제한되었습니다. 아래 버튼을 이용해 주세요.")
        st.divider()
        btn_c1, btn_c2 = st.columns(2)
        btn_c1.link_button("🚀 네이버 신규상장(IPO) 일정 바로가기", "https://finance.naver.com/sise/ipo.naver", use_container_width=True)
        btn_c2.link_button("💰 네이버 배당금 일정 바로가기", "https://finance.naver.com/sise/dividend_list.naver", use_container_width=True)

with tab7:
    st.markdown("<br>", unsafe_allow_html=True)
    st.subheader("💰 고배당주 & ETF 파이프라인 (TOP 60)")
    with st.spinner("야후 파이낸스에서 60개 종목의 최신 실시간 데이터를 다운로드 중입니다..."):
        div_dfs = get_dividend_portfolio()
    dt1, dt2, dt3 = st.tabs(["🇰🇷 국장 (배당주 TOP 20)", "🇺🇸 미장 (배당주 TOP 20)", "📈 배당 ETF (국내/해외 TOP 20)"])
    with dt1: st.dataframe(div_dfs["KRX"], use_container_width=True, hide_index=True)
    with dt2: st.dataframe(div_dfs["US"], use_container_width=True, hide_index=True)
    with dt3: st.dataframe(div_dfs["ETF"], use_container_width=True, hide_index=True)

# 👈 [핵심 추가] 탭 8: 나만의 관심종목 (Watchlist) 모니터링
with tab8:
    st.markdown("<br>", unsafe_allow_html=True)
    st.subheader("⭐ 나만의 관심종목 (Watchlist)")
    st.write("분석 중 저장한 종목들의 현재 타점을 실시간으로 모니터링합니다.")
    
    if st.button("🗑️ 관심종목 모두 지우기"):
        st.session_state.watchlist = []
        st.rerun()
        
    if not st.session_state.watchlist:
        st.info("아직 추가된 관심종목이 없습니다. 다른 탭에서 타점을 분석하고 '⭐ 관심종목 추가' 버튼을 눌러주세요.")
    else:
        for i, item in enumerate(st.session_state.watchlist):
            res = analyze_technical_pattern(item['종목명'], item['티커'])
            if res: draw_stock_card(res, api_key=api_key_input, is_expanded=False, key_suffix=f"wl_{i}")
