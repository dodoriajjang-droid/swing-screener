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

# ==========================================
# 1. 초기 설정 
# ==========================================
st.set_page_config(page_title="Jaemini 주식 검색기", layout="wide", page_icon="📈")

st_autorefresh(interval=300000, limit=None, key="news_autorefresh")

if 'seen_links' not in st.session_state:
    st.session_state.seen_links = set()
if 'seen_titles' not in st.session_state:
    st.session_state.seen_titles = set()
if 'news_data' not in st.session_state:
    st.session_state.news_data = []

# ==========================================
# 2. 데이터 수집 및 분석 함수들
# ==========================================
# 💡 수정: 하나가 실패해도 다른 건 살리도록 에러 독립 처리
@st.cache_data(ttl=3600)
def get_macro_indicators():
    tickers = {"VIX": "^VIX", "美 10년물 국채": "^TNX", "원/달러 환율": "KRW=X"}
    results = {}
    for name, t in tickers.items():
        try:
            df = yf.Ticker(t).history(period="5d")
            if len(df) >= 2:
                latest = float(df['Close'].iloc[-1])
                prev = float(df['Close'].iloc[-2])
                results[name] = {"value": latest, "delta": latest - prev, "prev": prev}
        except:
            continue # 에러 나면 그냥 넘어가고 성공한 것만 반환
    return results

@st.cache_data(ttl=3600)
def get_fear_and_greed():
    try:
        url = "https://production.dataviz.cnn.io/index/fearandgreed/graphdata"
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "application/json",
            "Referer": "https://edition.cnn.com/"
        }
        res = requests.get(url, headers=headers, timeout=5)
        data = res.json()
        score = data['fear_and_greed']['score']
        prev = data['fear_and_greed']['previous_close']
        return {"score": round(score), "delta": round(score - prev)}
    except:
        return None

@st.cache_data(ttl=3600)
def get_us_top_gainers():
    try:
        url = 'https://finance.yahoo.com/gainers'
        headers = {'User-Agent': 'Mozilla/5.0'}
        response = requests.get(url, headers=headers)
        tables = pd.read_html(StringIO(response.text))
        df = tables[0]
        
        df = df.loc[:, ~df.columns.str.contains('^Unnamed')]
        df = df.iloc[:, :6] 
        df.columns = ['종목코드', '기업명', '현재가', '등락금액', '등락률', '거래량']
        
        def extract_pct(x):
            try:
                match = re.search(r'([+-]?\d+\.?\d*)%', str(x))
                if match: return float(match.group(1))
                return float(re.sub(r'[^\d\.\+\-]', '', str(x)))
            except: return 0.0
                
        df['실제등락률'] = df['등락률'].apply(extract_pct)
        df = df[df['실제등락률'] >= 10.0] 
        df = df.drop(columns=['실제등락률']) 
        df['종목코드'] = df['종목코드'].astype(str).apply(lambda x: x.split()[0])
        
        def get_korean_name(name):
            try:
                encoded_name = urllib.parse.quote(name)
                api_url = f"https://translate.googleapis.com/translate_a/single?client=gtx&sl=en&tl=ko&dt=t&q={encoded_name}"
                res = requests.get(api_url, timeout=2)
                ko_name = res.json()[0][0][0]
                if ko_name.lower() != name.lower() and ko_name.strip(): return f"{name} / {ko_name}"
                return name
            except: return name
                
        df['기업명'] = df['기업명'].apply(get_korean_name)
        
        try: ex_rate = yf.Ticker("KRW=X").history(period="5d")['Close'].iloc[-1]
        except: ex_rate = 1350.0 
            
        def format_price(x):
            try:
                val = float(str(x).split()[0].replace(',', ''))
                return f"${val:.2f} (약 {int(val * ex_rate):,}원)"
            except: return str(x)
                
        df['현재가'] = df['현재가'].apply(format_price)
        return df, ex_rate
    except Exception as e:
        return pd.DataFrame(), 1350.0

@st.cache_data(ttl=86400)
def get_krx_stocks():
    try:
        df = fdr.StockListing('KRX')
        if not df.empty: return df[['Name', 'Code']]
    except: pass
    try:
        kospi = fdr.StockListing('KOSPI')
        kosdaq = fdr.StockListing('KOSDAQ')
        df = pd.concat([kospi, kosdaq], ignore_index=True)
        if not df.empty: return df[['Name', 'Code']]
    except: pass
    try:
        url = 'http://kind.krx.co.kr/corpgeneral/corpList.do?method=download&searchType=13'
        headers = {'User-Agent': 'Mozilla/5.0'}
        res = requests.get(url, headers=headers, timeout=10)
        res.encoding = 'euc-kr' 
        df = pd.read_html(StringIO(res.text), header=0)[0]
        df = df[['회사명', '종목코드']]
        df.columns = ['Name', 'Code']
        df['Code'] = df['Code'].astype(str).str.zfill(6)
        return df
    except Exception:
        return pd.DataFrame(columns=['Name', 'Code'])

@st.cache_data(ttl=300)
def get_latest_naver_news():
    base_url = "https://finance.naver.com"
    list_url = f"{base_url}/news/news_list.naver?mode=LSS2D&section_id=101&section_id2=258"
    headers = {"User-Agent": "Mozilla/5.0"}
    try:
        res = requests.get(list_url, headers=headers)
        res.raise_for_status()
        res.encoding = 'euc-kr'
        soup = BeautifulSoup(res.text, 'html.parser')
        subject_tags = soup.select("dl dd.articleSubject a")
        items = []
        for tag in subject_tags:
            title = tag.get_text(strip=True)
            link = tag['href']
            full_link = base_url + link if link.startswith("/") else link
            items.append({"title": title, "link": full_link})
        return items
    except Exception:
        return []

def update_news_state():
    items = get_latest_naver_news()
    kst_now = datetime.utcnow() + timedelta(hours=9)
    time_str = kst_now.strftime("%H:%M")
    for item in reversed(items): 
        if item['link'] not in st.session_state.seen_links and item['title'] not in st.session_state.seen_titles:
            st.session_state.news_data.insert(0, {"time": time_str, "title": item['title'], "link": item['link']})
            st.session_state.seen_links.add(item['link'])
            st.session_state.seen_titles.add(item['title'])

@st.cache_data(ttl=3600)
def get_all_sector_info(tickers, api_key):
    results = {t: ("분석 대기", "분석 대기") for t in tickers}
    if not api_key: return results
    try:
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel('gemini-2.5-flash')
        ticker_str = "\n".join(tickers)
        prompt = f"당신은 월스트리트 주식 전문가입니다.\n다음 미국 주식 티커들의 섹터(Sector)와 세부 산업(Industry)을 '한국어'로 분류해주세요.\n반드시 '티커|섹터|산업' 형태로만 답변하세요.\n[티커 목록]\n{ticker_str}"
        response = model.generate_content(prompt)
        for line in response.text.strip().split('\n'):
            parts = line.split('|')
            if len(parts) >= 3:
                t = parts[0].strip().replace('*', '').replace('-', '')
                s = parts[1].strip()
                i = parts[2].strip()
                if t in results: results[t] = (s, i)
        return results
    except Exception: return results

@st.cache_data(ttl=3600)
def get_ai_matched_stocks(ticker, sector, industry, comp_name, api_key):
    if not api_key: return []
    try:
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel('gemini-2.5-flash')
        prompt = f"미국 주식 '{comp_name}' (티커: {ticker}, 섹터: {sector}, 산업: {industry})와 비즈니스 모델이 유사하거나, 같은 테마로 움직일 수 있는 한국 코스피/코스닥 상장사 20개를 찾아주세요. 반드시 파이썬 리스트로만 답변하세요. 예시: [('삼성전자', '005930')]"
        return re.findall(r"['\"]([^'\"]+)['\"]\s*,\s*['\"]([0-9]{6})['\"]", model.generate_content(prompt).text)[:20]
    except Exception: return []

@st.cache_data(ttl=3600)
def get_theme_stocks_with_ai(theme_keyword, api_key):
    if not api_key: return []
    try:
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel('gemini-2.5-flash')
        prompt = f"테마명: '{theme_keyword}'\n이 테마와 관련된 한국 코스피/코스닥 대장주 및 주요 관련주 20개를 찾아주세요. 반드시 파이썬 리스트로만 답변하세요. 예시: [('에코프로', '086520')]"
        return re.findall(r"['\"]([^'\"]+)['\"]\s*,\s*['\"]([0-9]{6})['\"]", model.generate_content(prompt).text)[:20]
    except Exception: return []

@st.cache_data(ttl=3600)
def get_investor_trend(code):
    try:
        url = f"https://finance.naver.com/item/frgn.naver?code={code}"
        headers = {"User-Agent": "Mozilla/5.0"}
        res = requests.get(url, headers=headers, timeout=3)
        soup = BeautifulSoup(res.text, 'html.parser')
        tables = soup.select('table.type2')
        if len(tables) < 2: return "조회불가", "조회불가"
        rows = tables[1].select('tr')
        inst_sum, forgn_sum, count = 0, 0, 0
        for row in rows:
            tds = row.select('td')
            if len(tds) < 9: continue 
            date_str = tds[0].text.strip()
            if not date_str or len(date_str) < 8: continue
            inst_str = tds[5].text.strip().replace(',', '').replace('+', '')
            forgn_str = tds[6].text.strip().replace(',', '').replace('+', '')
            if not inst_str or not forgn_str: continue
            try:
                inst_sum += int(inst_str)
                forgn_sum += int(forgn_str)
                count += 1
            except: pass
            if count >= 3: break 
        inst_status = "🔥매집" if inst_sum > 0 else "💧매도" if inst_sum < 0 else "➖중립"
        forgn_status = "🔥매집" if forgn_sum > 0 else "💧매도" if forgn_sum < 0 else "➖중립"
        def format_val(val): return f"+{val:,}" if val > 0 else f"{val:,}"
        return f"{format_val(inst_sum)} ({inst_status})", f"{format_val(forgn_sum)} ({forgn_status})"
    except:
        return "조회불가", "조회불가"

@st.cache_data(ttl=3600)
def analyze_technical_pattern(stock_name, ticker_code):
    if not ticker_code: return None
    try:
        df = fdr.DataReader(ticker_code, (datetime.now() - timedelta(days=90)).strftime('%Y-%m-%d'))
        if len(df) < 20: return None
        
        df['MA20'] = df['Close'].rolling(window=20).mean()
        df['Vol_MA20'] = df['Volume'].rolling(window=20).mean()
        df['Std_20'] = df['Close'].rolling(window=20).std()
        df['Bollinger_Upper'] = df['MA20'] + (df['Std_20'] * 2)
        
        delta = df['Close'].diff()
        gain = delta.where(delta > 0, 0.0).rolling(window=14).mean()
        loss = -delta.where(delta < 0, 0.0).rolling(window=14).mean()
        rs = gain / loss
        df['RSI'] = 100 - (100 / (1 + rs))
        latest_rsi = df['RSI'].iloc[-1]
        rsi_status = "🔴 과열 (추격매수 금지)" if latest_rsi >= 70 else "🟢 바닥 (매수 관점)" if latest_rsi <= 30 else "⚪ 보통"

        latest = df.iloc[-1]
        recent_10_days = df.iloc[-10:]
        is_volume_spike = recent_10_days['Volume'].max() > (recent_10_days['Vol_MA20'].mean() * 2)
        
        current_price = latest['Close']
        ma20_price = latest['MA20']
        target_price = latest['Bollinger_Upper'] 
        stop_loss_price = ma20_price * 0.97      
        
        if (ma20_price * 0.97) <= current_price <= (ma20_price * 1.03): status = "✅ 타점 근접 (분할 매수 고려)"
        elif current_price > (ma20_price * 1.03): status = "⚠️ 관심 집중 (단기 급등, 눌림목 대기)"
        else: status = "🛑 추세 이탈 (관망/손절 구간)"
        
        inst_vol, forgn_vol = get_investor_trend(ticker_code)
            
        return {
            "종목명": stock_name, "현재가": int(current_price), "상태": status,
            "진입가_가이드": int(ma20_price), "목표가": int(target_price), "손절가": int(stop_loss_price),
            "최근_거래량": int(latest['Volume']), "거래량 급증": "🔥 거래량 급증" if is_volume_spike else "평이함",
            "RSI": latest_rsi, "RSI_상태": rsi_status, 
            "기관수급": inst_vol, "외인수급": forgn_vol,
            "종가 데이터": df['Close'].tail(20), "거래량 데이터": df['Volume'].tail(20)
        }
    except: return None

@st.cache_data(ttl=3600)
def get_company_summary(ticker, api_key):
    try:
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel('gemini-2.5-flash')
        biz_summary = ""
        try: biz_summary = yf.Ticker(ticker).info.get('longBusinessSummary', '')
        except: pass 
        if biz_summary: prompt = f"미국 주식 {ticker}의 영문 개요를 읽고, '무엇을 만들고 어떻게 돈을 버는지' 한국어로 2줄 요약해 주세요. [개요]: {biz_summary[:1500]}"
        else: prompt = f"미국 주식 티커 '{ticker}' 기업에 대해 아는 대로 '무엇을 만들고 어떻게 돈을 버는 기업인지' 핵심 비즈니스 모델을 한국어로 2~3줄로 요약해 주세요."
        return model.generate_content(prompt).text
    except Exception: return f"기업 정보를 요약하는 중 오류가 발생했습니다."

@st.cache_data(ttl=3600)
def analyze_news_with_gemini(ticker, api_key):
    try:
        genai.configure(api_key=api_key)
        news_list = []
        try: news_list = yf.Ticker(ticker).news
        except: pass
        if not news_list: return "최근 관련 뉴스를 찾을 수 없습니다."
        news_text = "\n".join([f"[{n.get('publisher')}] {n.get('title')}" for n in news_list[:3]])
        prompt = f"한국 주식 스윙 전문 애널리스트입니다. 미국 주식 '{ticker}' 영문 헤드라인을 바탕으로 한국 테마주에 미칠 영향을 분석하세요.\n{news_text}\n* 시장 센티먼트:\n* 재료 지속성:\n* 투자 코멘트:"
        return genai.GenerativeModel('gemini-2.5-flash').generate_content(prompt).text
    except Exception: return "뉴스 분석 중 오류가 발생했습니다."

@st.cache_data(ttl=3600)
def analyze_single_news(title, api_key):
    try:
        genai.configure(api_key=api_key)
        prompt = f"한국 주식 시장의 실전 스윙 트레이더입니다. 다음 발생한 실시간 뉴스 속보를 트레이딩 관점에서 냉철하게 분석해주세요.\n[속보 헤드라인]: \"{title}\"\n다음 3가지 항목에 대해 짧고 명확하게 답변하세요:\n1. 🔍 팩트 vs 노이즈:\n2. 📉 선반영 및 기대치:\n3. ⚡ 트레이딩 전략:"
        return genai.GenerativeModel('gemini-2.5-flash').generate_content(prompt).text
    except Exception: return "뉴스 분석 중 오류가 발생했습니다."

@st.cache_data(ttl=10800)
def get_trending_themes_with_ai(api_key):
    default_themes = ["전고체 배터리", "비만치료제", "저PBR/밸류업", "유리기판", "로봇/자동화"]
    if not api_key: return default_themes
    try:
        genai.configure(api_key=api_key)
        prompt = "최근 1~2일 사이 한국 증시에서 가장 핫한 주도 테마 5개를 쉼표(,)로 구분해서 알려주세요. 절대 부가 설명이나 번호, 기호를 쓰지 말고 딱 테마 이름만 출력하세요."
        themes = [t.strip() for t in genai.GenerativeModel('gemini-2.5-flash').generate_content(prompt).text.replace('\n', '').replace('*', '').split(',')]
        return themes[:5] if len(themes) >= 5 else default_themes
    except Exception: return default_themes

def show_trading_guidelines():
    st.info("""
    **[매매 신호 및 타점 가이드]**
    * ✅ **타점 근접:** 주가가 20일선 근처에 위치 **(분할 매수 권장)**
    * ⚠️ **관심 집중:** 급등으로 인한 단기 이격 발생 **(눌림목 대기)**
    * 🛑 **추세 이탈:** 20일선 하향 이탈 **(손절 또는 접근 금지)**
    * 🎯 **1차 목표가:** 볼린저 밴드 상단 저항선 **(절반 수익 실현 권장)**
    
    **[RSI (상대강도지수) 활용 가이드]**
    * 🔴 **과열 (70 이상):** 매수세가 과도하게 몰려 단기 고점일 확률이 높습니다. **(추격 매수 자제)**
    * 🟢 **바닥 (30 이하):** 매도세가 과도하여 저평가된 상태입니다. **(과대 낙폭 줍줍 찬스)**
    * ⚪ **보통 (30 ~ 70):** 일반적인 추세 구간입니다.
    """)

def draw_stock_card(tech_result, is_expanded=False):
    status_emoji = tech_result['상태'].split(' ')[0]
    
    with st.expander(f"{status_emoji} {tech_result['종목명']} (현재가: {tech_result['현재가']:,}원) ｜ RSI: {tech_result['RSI']:.1f}", expanded=is_expanded):
        st.markdown(f"**진단 상태:** {tech_result['상태']} ｜ **수급/과열:** {tech_result['거래량 급증']} / {tech_result['RSI_상태']}")
        
        c1, c2, c3, c4 = st.columns(4)
        curr = tech_result['현재가']
        
        c1.metric("📌 진입 기준가", f"{tech_result['진입가_가이드']:,}원", f"{tech_result['진입가_가이드'] - curr:,}원 (대비)", delta_color="off")
        c2.metric("🎯 1차 목표가", f"{tech_result['목표가']:,}원", f"+{tech_result['목표가'] - curr:,}원 (기대수익)")
        c3.metric("🛑 손절 라인", f"{tech_result['손절가']:,}원", f"{tech_result['손절가'] - curr:,}원 (리스크)", delta_color="normal")
        c4.metric("📊 RSI (상대강도)", f"{tech_result['RSI']:.1f}", "과열 위험" if tech_result['RSI'] >= 70 else "바닥권" if tech_result['RSI'] <= 30 else "보통", delta_color="inverse" if tech_result['RSI'] >= 70 else "normal")
        
        st.markdown(f"🕵️ **최근 3일 수급 동향** ｜ **외국인:** `{tech_result['외인수급']}` ｜ **기관:** `{tech_result['기관수급']}`")
        
        ch1, ch2 = st.columns(2)
        price_df = tech_result["종가 데이터"].reset_index()
        price_df.columns = ['Date', 'Price']
        price_df['Date_Str'] = price_df['Date'].dt.strftime('%m-%d')
        vol_df = tech_result["거래량 데이터"].reset_index()
        vol_df.columns = ['Date', 'Volume']
        vol_df['Date_Str'] = vol_df['Date'].dt.strftime('%m-%d')
        
        with ch1:
            st.caption("📈 주가 흐름 (최근 20일)")
            fig_price = px.line(price_df, x='Date_Str', y='Price', markers=True)
            fig_price.update_layout(margin=dict(l=0, r=0, t=10, b=0), xaxis_title="", yaxis_title="", yaxis_tickformat=",", hovermode="x unified", xaxis=dict(showgrid=False, type='category'), yaxis=dict(showgrid=True, gridcolor='rgba(128,128,128,0.2)'), height=220)
            fig_price.update_traces(line_color="#FF4B4B", hovertemplate="<b>%{y:,}원</b>")
            st.plotly_chart(fig_price, use_container_width=True, config={'displayModeBar': False})
            
        with ch2:
            st.caption("📊 거래량 (최근 20일)")
            fig_vol = px.bar(vol_df, x='Date_Str', y='Volume')
            fig_vol.update_layout(margin=dict(l=0, r=0, t=10, b=0), xaxis_title="", yaxis_title="", yaxis_tickformat=",", hovermode="x unified", xaxis=dict(showgrid=False, type='category'), yaxis=dict(showgrid=True, gridcolor='rgba(128,128,128,0.2)'), height=220)
            fig_vol.update_traces(marker_color="#1f77b4", hovertemplate="<b>%{y:,}주</b>")
            st.plotly_chart(fig_vol, use_container_width=True, config={'displayModeBar': False})

# ==========================================
# 3. 사이드바 및 UI 화면 구성
# ==========================================
st.title("📈 Jaemini 스윙 트레이딩 대시보드")
st.markdown("단기 스윙 매매를 위한 **글로벌 주도주 분석** 및 **실시간 타점 모니터링** 시스템입니다.")

# 💡 수정: 매크로 지표 영역이 절대 사라지지 않도록 무조건 렌더링하도록 뼈대 고정
st.markdown("##### 🌍 실시간 글로벌 매크로 지표 & 시장 체력")

macro_data = get_macro_indicators()
fg_data = get_fear_and_greed()

m_col1, m_col2, m_col3 = st.columns([1, 1, 2])

with m_col1:
    if macro_data and 'VIX' in macro_data:
        vix_val = macro_data['VIX']['value']
        vix_prev = macro_data['VIX']['prev']
        fig_vix = go.Figure(go.Indicator(
            mode = "gauge+number+delta",
            value = vix_val,
            title = {'text': "<b>VIX (시장 공포지수)</b><br><span style='font-size:12px;color:gray'>20: 경계 ｜ 30: 공포 (현금확대)</span>", 'font': {'size': 15}},
            delta = {'reference': vix_prev, 'position': "top"},
            gauge = {
                'axis': {'range': [0, 50], 'tickwidth': 1, 'tickcolor': "darkblue"},
                'bar': {'color': "black", 'thickness': 0.2},
                'bgcolor': "white",
                'borderwidth': 1,
                'bordercolor': "gray",
                'steps': [
                    {'range': [0, 15], 'color': "rgba(0, 255, 0, 0.3)"},
                    {'range': [15, 20], 'color': "rgba(255, 255, 0, 0.3)"},
                    {'range': [20, 30], 'color': "rgba(255, 165, 0, 0.3)"},
                    {'range': [30, 50], 'color': "rgba(255, 0, 0, 0.3)"}
                ],
            }
        ))
        fig_vix.update_layout(margin=dict(l=10, r=10, t=80, b=10), height=250)
        st.plotly_chart(fig_vix, use_container_width=True, config={'displayModeBar': False})
    else:
        st.info("⚠️ VIX 데이터 로딩 지연")

with m_col2:
    if fg_data:
        fg_val = fg_data['score']
        fg_prev = fg_val - fg_data['delta']
        fig_fg = go.Figure(go.Indicator(
            mode = "gauge+number+delta",
            value = fg_val,
            title = {'text': "<b>CNN 공포/탐욕 지수</b><br><span style='font-size:12px;color:gray'>25이하: 공포(매수) ｜ 75이상: 탐욕(매도)</span>", 'font': {'size': 15}},
            delta = {'reference': fg_prev, 'position': "top"},
            gauge = {
                'axis': {'range': [0, 100], 'tickwidth': 1, 'tickcolor': "darkblue"},
                'bar': {'color': "black", 'thickness': 0.2},
                'bgcolor': "white",
                'borderwidth': 1,
                'bordercolor': "gray",
                'steps': [
                    {'range': [0, 25], 'color': "rgba(255, 0, 0, 0.4)"},     
                    {'range': [25, 45], 'color': "rgba(255, 165, 0, 0.4)"},   
                    {'range': [45, 55], 'color': "rgba(255, 255, 0, 0.4)"},   
                    {'range': [55, 75], 'color': "rgba(144, 238, 144, 0.4)"}, 
                    {'range': [75, 100], 'color': "rgba(0, 128, 0, 0.4)"}     
                ],
            }
        ))
        fig_fg.update_layout(margin=dict(l=10, r=10, t=80, b=10), height=250)
        st.plotly_chart(fig_fg, use_container_width=True, config={'displayModeBar': False})
    else:
        st.info("⚠️ CNN 공포지수 데이터 로딩 지연")
    
with m_col3:
    with st.container(border=True):
        st.markdown("<br>", unsafe_allow_html=True)
        c1, c2 = st.columns(2)
        
        if macro_data and '美 10년물 국채' in macro_data:
            c1.metric("🏦 美 10년물 국채 금리", f"{macro_data['美 10년물 국채']['value']:.3f}%", f"{macro_data['美 10년물 국채']['delta']:.3f}%", delta_color="inverse")
        else:
            c1.metric("🏦 美 10년물 국채 금리", "조회 불가")
            
        if macro_data and '원/달러 환율' in macro_data:
            c2.metric("💱 원/달러 환율", f"{macro_data['원/달러 환율']['value']:.1f}원", f"{macro_data['원/달러 환율']['delta']:.1f}원", delta_color="inverse")
        else:
            c2.metric("💱 원/달러 환율", "조회 불가")
            
        st.info("💡 **[시장 체력 가이드]** VIX가 높게 치솟거나 공포/탐욕 지수가 '공포(빨간색)' 구간일 때가 통계적으로 최고의 스윙 매수 찬스입니다.")

with st.sidebar:
    st.header("⚙️ 대시보드 컨트롤")
    fetch_button = st.button("🔄 증시 데이터 리로드", type="primary", use_container_width=True)
    st.divider()
    st.header("🧠 AI 엔진 연결 상태")
    if "GEMINI_API_KEY" in st.secrets:
        api_key_input = st.secrets["GEMINI_API_KEY"]
        st.success("✅ 시스템 연동 완료 (정상)")
    else:
        api_key_input = st.text_input("Gemini API Key를 입력하세요", type="password")

if fetch_button:
    get_us_top_gainers.clear()
    get_krx_stocks.clear()
    get_all_sector_info.clear()
    get_macro_indicators.clear()
    get_fear_and_greed.clear()
    get_latest_naver_news.clear()
    analyze_technical_pattern.clear()
    get_investor_trend.clear()
    get_company_summary.clear()
    analyze_news_with_gemini.clear()
    analyze_single_news.clear()
    get_ai_matched_stocks.clear()
    get_theme_stocks_with_ai.clear()

if "gainers_df" not in st.session_state or fetch_button:
    with st.spinner('📡 글로벌 증시 데이터를 수집하는 중입니다...'):
        df, ex_rate = get_us_top_gainers()
        st.session_state.gainers_df = df
        st.session_state.ex_rate = ex_rate

tab1, tab2, tab3, tab4 = st.tabs(["🔥 🇺🇸 미국장 기반 테마 발굴", "🎯 국내 종목 정밀 진단", "💡 AI 테마/관련주 검색", "📰 실시간 금융 속보"])

# ------------------------------------------
# [탭 1]
# ------------------------------------------
with tab1:
    st.markdown("<br>", unsafe_allow_html=True)
    col1, col2 = st.columns([1, 1.2], gap="large")

    with col1:
        us_time = datetime.utcnow() - timedelta(hours=5) 
        st.subheader("🔥 미국장 폭등주 (+10% 이상)")
        st.caption(f"🗓️ **기준일:** {us_time.strftime('%Y-%m-%d')} (NYT) ｜ 💱 **적용 환율:** 1달러 = {int(st.session_state.get('ex_rate', 1350)):,}원")
        
        if not st.session_state.gainers_df.empty:
            tickers_list = st.session_state.gainers_df['종목코드'].tolist()
            if api_key_input:
                with st.spinner("🤖 AI가 30개 종목의 섹터 정보를 일괄 분석 중입니다..."):
                    sector_dict = get_all_sector_info(tuple(tickers_list), api_key_input)
            else: sector_dict = {t: ("분석 대기", "분석 대기") for t in tickers_list}
            
            display_df = st.session_state.gainers_df.copy()
            new_company_names = []
            PLACEHOLDER = "🔍 검색 종목을 선택해주세요."
            options = [PLACEHOLDER]
            
            for index, row in display_df.iterrows():
                t = row['종목코드']
                full_name = row['기업명']
                kor_name = full_name.split(' / ')[-1] if ' / ' in full_name else full_name
                sec, ind = sector_dict.get(t, ("분석 불가", "분석 불가"))
                new_company_names.append(f"{full_name} ({sec} / {ind})")
                options.append(f"{t} ({kor_name}) - ({sec} / {ind})")
                
            display_df['기업명'] = new_company_names
            st.dataframe(display_df, use_container_width=True, hide_index=True, height=400)
            st.markdown("#### 🔍 분석 대상 종목 선택")
            selected_option = st.selectbox("목록에서 주식을 선택하세요:", options, label_visibility="collapsed")
            selected_ticker = "N/A" if selected_option == PLACEHOLDER else selected_option.split(" ")[0]
        else:
            selected_ticker = "N/A"
            st.info("현재 +10% 이상 급등한 종목이 없습니다.")

    with col2:
        st.subheader("🎯 연관 테마 매칭 및 타점 진단")
        show_trading_guidelines() 
        if selected_ticker != "N/A":
            sector, industry = sector_dict.get(selected_ticker, ("분석 불가", "분석 불가"))
            st.markdown(f"**🏷️ 섹터 정보:** `{sector}` / `{industry}`")
            if api_key_input:
                with st.spinner(f"🔍 '{selected_ticker}' 기업 정보 및 뉴스를 AI가 분석 중입니다..."):
                    with st.container(border=True):
                        st.markdown(f"**🏢 비즈니스 모델 요약 ({selected_ticker})**\n> {get_company_summary(selected_ticker, api_key_input)}")
                        st.markdown(f"**📰 AI 뉴스 판독**\n> {analyze_news_with_gemini(selected_ticker, api_key_input)}")
                
                with st.spinner('✨ AI가 연관된 한국 수혜주를 샅샅이 검색하고 타점을 계산 중입니다...'):
                    kor_stocks = get_ai_matched_stocks(selected_ticker, sector, industry, selected_option.split(" - ")[0], api_key_input)
                    if kor_stocks:
                        st.markdown("### ✨ AI 추천 국내 수혜주 (클릭하여 타점 확인)")
                        for stock_name, ticker_code in kor_stocks:
                            tech_result = analyze_technical_pattern(stock_name, ticker_code)
                            if tech_result: draw_stock_card(tech_result, is_expanded=False)
                    else: st.error("❌ 연관된 국내 주식을 찾는 데 실패했습니다. 서버 연결 상태를 확인해 주세요.")
            else: st.warning("👈 좌측 사이드바에 API 키를 입력하시면 AI 분석이 시작됩니다.")

# ------------------------------------------
# [탭 2]
# ------------------------------------------
with tab2:
    st.markdown("<br>", unsafe_allow_html=True)
    st.subheader("🔍 국내 개별 종목 정밀 타점 진단기")
    st.write("관심 있는 국내 상장사를 검색하면 즉시 20일선 및 볼린저 밴드 기준 기술적 분석 타점을 계산합니다.")
    show_trading_guidelines() 
    krx_df = get_krx_stocks()
    if not krx_df.empty:
        krx_options = ["🔍 검색 종목을 선택해주세요."] + (krx_df['Name'] + " (" + krx_df['Code'] + ")").tolist()
        search_query = st.selectbox("👇 종목명 또는 초성을 입력하여 검색하세요:", krx_options)
        if search_query and search_query != "🔍 검색 종목을 선택해주세요.":
            searched_name = search_query.split(" (")[0]
            searched_code = search_query.split("(")[1].replace(")", "")
            with st.spinner(f"📡 증권사 서버에서 '{searched_name}' 과거 90일 치 데이터를 가져와 타점 분석 중입니다..."):
                tech_result = analyze_technical_pattern(searched_name, searched_code)
            if tech_result: draw_stock_card(tech_result, is_expanded=True)
            else: st.error("❌ 데이터를 불러올 수 없습니다. (신규 상장 등으로 20일 데이터가 부족할 수 있습니다)")
    else: st.error("❌ 국내 주식 목록을 불러오는 데 실패했습니다. 좌측 사이드바에서 [🔄 증시 데이터 리로드] 버튼을 눌러주세요.")

# ------------------------------------------
# [탭 3]
# ------------------------------------------
with tab3:
    st.markdown("<br>", unsafe_allow_html=True)
    st.subheader("💡 테마 및 관련주 실시간 AI 발굴기")
    st.write("검색할 테마/키워드를 직접 입력하거나, AI가 스캔한 오늘의 핫 테마를 클릭하세요.")
    show_trading_guidelines() 
    st.markdown("🔥 **AI가 감지한 오늘의 실시간 주도 테마**")
    
    with st.spinner("📡 현재 시장을 주도하는 핫 테마를 스캔 중입니다..."):
        hot_themes = get_trending_themes_with_ai(api_key_input)
        
    cols = st.columns(len(hot_themes))
    clicked_theme = None
    for i, theme in enumerate(hot_themes):
        if cols[i].button(theme, use_container_width=True): clicked_theme = theme

    theme_input = st.text_input("🔍 직접 검색할 테마/키워드 입력:", value=clicked_theme if clicked_theme else "", placeholder="🔍 검색 종목을 선택해주세요.")
    
    if theme_input and api_key_input:
        with st.spinner(f"✨ AI가 증시 전체에서 '{theme_input}' 관련주를 발굴하고 타점을 진단하는 중입니다... (약 3~5초 소요)"):
            theme_stocks = get_theme_stocks_with_ai(theme_input, api_key_input)
            if theme_stocks:
                st.success(f"🎯 **'{theme_input}' 관련주 {len(theme_stocks)}개 발굴 및 진단 완료! (아래 종목을 클릭하세요)**")
                for stock_name, ticker_code in theme_stocks:
                    tech_result = analyze_technical_pattern(stock_name, ticker_code)
                    if tech_result: draw_stock_card(tech_result, is_expanded=False)
            else: st.error(f"❌ '{theme_input}' 테마에 대한 관련주를 찾지 못했거나 AI 응답 지연이 발생했습니다. 다시 시도해 주세요.")

# ------------------------------------------
# [탭 4]
# ------------------------------------------
with tab4:
    st.markdown("<br>", unsafe_allow_html=True)
    st.subheader("📰 트레이더용 실시간 금융 속보 (노이즈 필터링 적용)")
    st.write("5분 주기로 시장 속보를 스캔하며, 중복된 재탕 기사는 자동으로 차단합니다.")
    
    cols_top = st.columns([4, 1])
    with cols_top[0]:
        st.markdown("### 🎯 주도 테마 핵심 키워드 모니터링")
    with cols_top[1]:
        if st.button("🔄 실시간 뉴스 리로드", use_container_width=True):
            get_latest_naver_news.clear()
    
    keywords_input = st.text_input("하이라이트 및 필터링할 핵심 키워드 (쉼표로 구분):", value="AI, 반도체, 데이터센터, 원전")
    keywords = [k.strip() for k in keywords_input.split(",") if k.strip()]
    only_keyword_news = st.checkbox("🔥 위 키워드가 포함된 핵심 뉴스만 보기", value=False)
    
    update_news_state()
    st.divider()
        
    if st.session_state.news_data:
        for i, news in enumerate(st.session_state.news_data[:50]):
            title = news['title']
            has_keyword = any(k.lower() in title.lower() for k in keywords)
            if only_keyword_news and not has_keyword: continue
            display_title = f"🔥 **{title}**" if has_keyword else title
                
            with st.container(border=True):
                cols = st.columns([6, 1.5, 1])
                cols[0].markdown(f"**🕒 {news['time']}** | {display_title}")
                if cols[1].button("🤖 AI 뉴스 판독", key=f"ai_news_{i}"):
                    if api_key_input:
                        with st.spinner("AI가 재료의 가치와 선반영 여부를 분석 중입니다..."):
                            analysis_result = analyze_single_news(title, api_key_input)
                            st.info(analysis_result)
                    else: st.warning("사이드바에 API 키를 입력해주세요.")
                cols[2].link_button("원문 🔗", news['link'], use_container_width=True)
    else:
        st.info("수집된 뉴스가 없습니다. 잠시 후 다시 확인합니다.")
