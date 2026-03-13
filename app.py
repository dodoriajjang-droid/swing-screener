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

if 'seen_links' not in st.session_state:
    st.session_state.seen_links = set()
if 'seen_titles' not in st.session_state:
    st.session_state.seen_titles = set()
if 'news_data' not in st.session_state:
    st.session_state.news_data = []

# ==========================================
# 2. 데이터 수집 및 분석 함수들
# ==========================================
@st.cache_data(ttl=3600)
def get_macro_indicators():
    results = {}
    try:
        df_vix = yf.Ticker("^VIX").history(period="1mo")
        if not df_vix.empty and len(df_vix) >= 2:
            results["VIX"] = {"value": float(df_vix['Close'].iloc[-1]), "delta": float(df_vix['Close'].iloc[-1] - df_vix['Close'].iloc[-2]), "prev": float(df_vix['Close'].iloc[-2])}
    except: pass
    try:
        df_tnx = yf.Ticker("^TNX").history(period="1mo")
        if not df_tnx.empty and len(df_tnx) >= 2:
            results["美 10년물 국채"] = {"value": float(df_tnx['Close'].iloc[-1]), "delta": float(df_tnx['Close'].iloc[-1] - df_tnx['Close'].iloc[-2]), "prev": float(df_tnx['Close'].iloc[-2])}
    except: pass
    try:
        df_krw = fdr.DataReader('USD/KRW', (datetime.now() - timedelta(days=30)).strftime('%Y-%m-%d'))
        if not df_krw.empty and len(df_krw) >= 2:
            results["원/달러 환율"] = {"value": float(df_krw['Close'].iloc[-1]), "delta": float(df_krw['Close'].iloc[-1] - df_krw['Close'].iloc[-2]), "prev": float(df_krw['Close'].iloc[-2])}
        else:
            df_krw_yf = yf.Ticker("KRW=X").history(period="1mo")
            if not df_krw_yf.empty and len(df_krw_yf) >= 2:
                results["원/달러 환율"] = {"value": float(df_krw_yf['Close'].iloc[-1]), "delta": float(df_krw_yf['Close'].iloc[-1] - df_krw_yf['Close'].iloc[-2]), "prev": float(df_krw_yf['Close'].iloc[-2])}
    except: pass
    return results if results else None

@st.cache_data(ttl=3600)
def get_fear_and_greed():
    url = "https://production.dataviz.cnn.io/index/fearandgreed/graphdata"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Accept": "application/json",
        "Origin": "https://edition.cnn.com",
        "Referer": "https://edition.cnn.com/"
    }
    try:
        res = requests.get(url, headers=headers, timeout=5)
        if res.status_code == 200:
            data = res.json()
            return {"score": round(data['fear_and_greed']['score']), "delta": round(data['fear_and_greed']['score'] - data['fear_and_greed']['previous_close']), "rating": data['fear_and_greed']['rating'].capitalize()}
            
        proxy_url = f"https://api.allorigins.win/raw?url={urllib.parse.quote(url)}"
        res2 = requests.get(proxy_url, headers={"User-Agent": "Mozilla/5.0"}, timeout=5)
        if res2.status_code == 200:
            data = res2.json()
            return {"score": round(data['fear_and_greed']['score']), "delta": round(data['fear_and_greed']['score'] - data['fear_and_greed']['previous_close']), "rating": data['fear_and_greed']['rating'].capitalize()}
    except: pass
    return None

@st.cache_data(ttl=3600)
def get_us_top_gainers():
    try:
        url = 'https://finance.yahoo.com/gainers'
        headers = {'User-Agent': 'Mozilla/5.0'}
        response = requests.get(url, headers=headers)
        tables = pd.read_html(StringIO(response.text))
        df = tables[0].iloc[:, :6] 
        df.columns = ['종목코드', '기업명', '현재가', '등락금액', '등락률', '거래량']
        def extract_pct(x):
            try:
                match = re.search(r'([+-]?\d+\.?\d*)%', str(x))
                if match: return float(match.group(1))
                return float(re.sub(r'[^\d\.\+\-]', '', str(x)))
            except: return 0.0
        df['실제등락률'] = df['등락률'].apply(extract_pct)
        df = df[df['실제등락률'] >= 10.0].drop(columns=['실제등락률']) 
        df['종목코드'] = df['종목코드'].astype(str).apply(lambda x: x.split()[0])
        def get_korean_name(name):
            try:
                res = requests.get(f"https://translate.googleapis.com/translate_a/single?client=gtx&sl=en&tl=ko&dt=t&q={urllib.parse.quote(name)}", timeout=2)
                ko_name = res.json()[0][0][0]
                return f"{name} / {ko_name}" if ko_name.lower() != name.lower() else name
            except: return name
        df['기업명'] = df['기업명'].apply(get_korean_name)
        try: ex_rate = yf.Ticker("KRW=X").history(period="5d")['Close'].iloc[-1]
        except: ex_rate = 1350.0 
        df['현재가'] = df['현재가'].apply(lambda x: f"${float(str(x).split()[0].replace(',', '')):.2f} (약 {int(float(str(x).split()[0].replace(',', '')) * ex_rate):,}원)" if pd.notnull(x) else x)
        return df, ex_rate
    except: return pd.DataFrame(), 1350.0

@st.cache_data(ttl=86400)
def get_krx_stocks():
    try:
        df = fdr.StockListing('KRX')
        if not df.empty: return df[['Name', 'Code']]
    except: pass
    return pd.DataFrame(columns=['Name', 'Code'])

@st.cache_data(ttl=600)
def get_trading_value_kings():
    try:
        df = fdr.StockListing('KRX')
        if df.empty: return pd.DataFrame()
        mask = df['Name'].str.contains('KODEX|TIGER|KBSTAR|KOSEF|ARIRANG|HANARO|ACE|스팩|ETN|선물|인버스|레버리지')
        df = df[~mask].sort_values('Amount', ascending=False).head(20)
        df['Amount_Ouk'] = (df['Amount'] / 100000000).astype(int)
        return df[['Code', 'Name', 'Close', 'ChagesRatio', 'Amount_Ouk']]
    except Exception as e:
        return pd.DataFrame()

@st.cache_data(ttl=300)
def get_latest_naver_news():
    try:
        res = requests.get("https://finance.naver.com/news/news_list.naver?mode=LSS2D&section_id=101&section_id2=258", headers={"User-Agent": "Mozilla/5.0"})
        res.encoding = 'euc-kr'
        soup = BeautifulSoup(res.text, 'html.parser')
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
def get_all_sector_info(tickers, api_key):
    results = {t: ("분석 대기", "분석 대기") for t in tickers}
    if not api_key: return results
    try:
        genai.configure(api_key=api_key)
        response = genai.GenerativeModel('gemini-2.5-flash').generate_content(f"당신은 월스트리트 주식 전문가입니다.\n다음 미국 주식 티커들의 섹터(Sector)와 세부 산업(Industry)을 '한국어'로 분류해주세요.\n반드시 '티커|섹터|산업' 형태로만 답변하세요.\n[티커 목록]\n{chr(10).join(tickers)}")
        for line in response.text.strip().split('\n'):
            parts = line.split('|')
            if len(parts) >= 3 and parts[0].strip().replace('*', '').replace('-', '') in results:
                results[parts[0].strip().replace('*', '').replace('-', '')] = (parts[1].strip(), parts[2].strip())
        return results
    except: return results

@st.cache_data(ttl=3600)
def get_ai_matched_stocks(ticker, sector, industry, comp_name, api_key):
    if not api_key: return []
    try:
        genai.configure(api_key=api_key)
        return re.findall(r"['\"]([^'\"]+)['\"]\s*,\s*['\"]([0-9]{6})['\"]", genai.GenerativeModel('gemini-2.5-flash').generate_content(f"미국 주식 '{comp_name}' (티커: {ticker}, 섹터: {sector}, 산업: {industry})와 비즈니스 모델이 유사하거나, 같은 테마로 움직일 수 있는 한국 코스피/코스닥 상장사 20개를 찾아주세요. 반드시 파이썬 리스트로만 답변하세요. 예시: [('삼성전자', '005930')]").text)[:20]
    except: return []

@st.cache_data(ttl=3600)
def get_theme_stocks_with_ai(theme_keyword, api_key):
    if not api_key: return []
    try:
        genai.configure(api_key=api_key)
        return re.findall(r"['\"]([^'\"]+)['\"]\s*,\s*['\"]([0-9]{6})['\"]", genai.GenerativeModel('gemini-2.5-flash').generate_content(f"테마명: '{theme_keyword}'\n이 테마와 관련된 한국 코스피/코스닥 대장주 및 주요 관련주 20개를 찾아주세요. 반드시 파이썬 리스트로만 답변하세요. 예시: [('에코프로', '086520')]").text)[:20]
    except: return []

@st.cache_data(ttl=3600)
def get_investor_trend(code):
    try:
        res = requests.get(f"https://finance.naver.com/item/frgn.naver?code={code}", headers={"User-Agent": "Mozilla/5.0"}, timeout=3)
        soup = BeautifulSoup(res.text, 'html.parser')
        rows = soup.select('table.type2')[1].select('tr')
        inst_sum, forgn_sum, count = 0, 0, 0
        for row in rows:
            tds = row.select('td')
            if len(tds) < 9 or not tds[0].text.strip(): continue 
            try:
                inst_sum += int(tds[5].text.strip().replace(',', '').replace('+', ''))
                forgn_sum += int(tds[6].text.strip().replace(',', '').replace('+', ''))
                count += 1
            except: pass
            if count >= 3: break 
        def fmt(v): return f"+{v:,}" if v > 0 else f"{v:,}"
        return f"{fmt(inst_sum)} ({'🔥매집' if inst_sum>0 else '💧매도' if inst_sum<0 else '➖중립'})", f"{fmt(forgn_sum)} ({'🔥매집' if forgn_sum>0 else '💧매도' if forgn_sum<0 else '➖중립'})"
    except: return "조회불가", "조회불가"

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
        latest_rsi = 100 - (100 / (1 + rs)).iloc[-1]
        
        latest = df.iloc[-1]
        ma20_price = latest['MA20']
        current_price = int(latest['Close'])
        
        target_1 = int(latest['Bollinger_Upper'])
        recent_high = int(df['Close'].max())
        target_2 = recent_high if recent_high > (target_1 * 1.02) else int(target_1 * 1.05)
        target_3 = int(target_2 * 1.08)
        stop_loss_price = int(ma20_price * 0.97)      
        
        if (ma20_price * 0.97) <= current_price <= (ma20_price * 1.03): status = "✅ 타점 근접 (분할 매수 고려)"
        elif current_price > (ma20_price * 1.03): status = "⚠️ 관심 집중 (단기 급등, 눌림목 대기)"
        else: status = "🛑 추세 이탈 (관망/손절 구간)"
        
        inst_vol, forgn_vol = get_investor_trend(ticker_code)
            
        return {
            "종목명": stock_name,
            "티커": ticker_code,
            "현재가": current_price, "상태": status,
            "진입가_가이드": int(ma20_price), 
            "목표가1": target_1, "목표가2": target_2, "목표가3": target_3,
            "손절가": stop_loss_price,
            "최근_거래량": int(latest['Volume']), "거래량 급증": "🔥 거래량 급증" if df.iloc[-10:]['Volume'].max() > (df.iloc[-10:]['Vol_MA20'].mean() * 2) else "평이함",
            "RSI": latest_rsi, "RSI_상태": "🔴 과열 (추격매수 금지)" if latest_rsi >= 70 else "🔵 바닥 (매수 관점)" if latest_rsi <= 30 else "⚪ 보통", 
            "기관수급": inst_vol, "외인수급": forgn_vol,
            "종가 데이터": df['Close'].tail(20), "거래량 데이터": df['Volume'].tail(20)
        }
    except: return None

@st.cache_data(ttl=3600)
def get_company_summary(ticker, api_key):
    try:
        genai.configure(api_key=api_key)
        biz_summary = yf.Ticker(ticker).info.get('longBusinessSummary', '')
        prompt = f"미국 주식 {ticker}의 개요를 '무엇을 만들고 어떻게 돈을 버는지' 한국어로 2줄 요약해 주세요. [개요]: {biz_summary[:1500]}" if biz_summary else f"미국 주식 '{ticker}' 핵심 비즈니스 모델을 한국어로 2~3줄 요약해 주세요."
        return genai.GenerativeModel('gemini-2.5-flash').generate_content(prompt).text
    except Exception: return "기업 정보를 요약하는 중 오류가 발생했습니다."

@st.cache_data(ttl=3600)
def analyze_news_with_gemini(ticker, api_key):
    try:
        genai.configure(api_key=api_key)
        news_list = yf.Ticker(ticker).news
        if not news_list: return "최근 관련 뉴스를 찾을 수 없습니다."
        news_text = "\n".join([f"[{n.get('publisher')}] {n.get('title')}" for n in news_list[:3]])
        prompt = f"스윙 전문 애널리스트입니다. 미국 주식 '{ticker}' 뉴스가 한국 테마에 미칠 영향을 분석하세요.\n{news_text}\n* 시장 센티먼트:\n* 재료 지속성:\n* 투자 코멘트:"
        return genai.GenerativeModel('gemini-2.5-flash').generate_content(prompt).text
    except Exception: return "뉴스 분석 중 오류가 발생했습니다."

@st.cache_data(ttl=3600)
def analyze_single_news(title, api_key):
    try:
        genai.configure(api_key=api_key)
        prompt = f"실전 스윙 트레이더입니다. 다음 속보를 트레이딩 관점에서 짧게 분석해주세요.\n[속보]: \"{title}\"\n1. 🔍 팩트 vs 노이즈:\n2. 📉 선반영 여부:\n3. ⚡ 트레이딩 전략:"
        return genai.GenerativeModel('gemini-2.5-flash').generate_content(prompt).text
    except Exception: return "뉴스 분석 중 오류가 발생했습니다."

@st.cache_data(ttl=10800)
def get_trending_themes_with_ai(api_key):
    default_themes = ["AI 반도체", "비만치료제", "저PBR/밸류업", "전력 설비", "로봇/자동화"]
    if not api_key: return default_themes
    try:
        genai.configure(api_key=api_key)
        raw_text = genai.GenerativeModel('gemini-2.5-flash').generate_content("최근 한국 증시 가장 핫한 주도 테마 5개만 쉼표로 구분해서 1줄로 출력하세요. 번호/부연설명 절대 금지.").text.replace('\n', '').replace('*', '')
        valid_themes = [t.strip() for t in raw_text.split(',')]
        return valid_themes[:5] if len(valid_themes) >= 5 else default_themes
    except Exception: return default_themes

@st.cache_data(ttl=3600)
def get_ai_trading_opinion(stock_name, ticker_code, current_price, ma20, rsi, api_key):
    if not api_key: return "API 키가 필요합니다."
    try:
        genai.configure(api_key=api_key)
        prompt = f"""
        당신은 한국과 미국 주식 시장을 꿰뚫고 있는 탑티어 실전 트레이더이자 가치투자자입니다.
        분석할 종목: {stock_name} (티커/코드: {ticker_code})
        현재 데이터: 현재가 {current_price:,}, 20일 이동평균선 {ma20:,}, RSI {rsi:.1f}
        
        이 종목의 펀더멘털과 위 기술적 지표를 종합하여 다음 3가지 항목을 명확하게 답변해 주세요. 부연 설명은 길지 않게 핵심만 짚어주세요.
        
        1. ⚖️ 가치 평가 (적정가 대비): 현재 가격이 이 회사의 내재가치 및 모멘텀 대비 비싼 편인지, 싼 편인지, 적정한지 평가.
        2. 📉 타점 분석: 현재가, 20일선, RSI를 볼 때 지금 당장 진입하기 유리한 자리인지 기술적 분석.
        3. 🎯 최종 액션 플랜: "적극 매수", "분할 매수", "관망(대기)", "매수 금지" 중 하나로 스탠스를 정하고, 그 이유를 1줄로 요약.
        """
        return genai.GenerativeModel('gemini-2.5-flash').generate_content(prompt).text
    except Exception as e:
        return f"AI 의견 생성 중 오류가 발생했습니다: {str(e)}"

@st.cache_data(ttl=43200)
def get_naver_calendar_events():
    try:
        res = requests.get("https://finance.naver.com/sise/calendar.naver", headers={"User-Agent": "Mozilla/5.0"}, timeout=5)
        if res.status_code == 200:
            soup = BeautifulSoup(res.content.decode('euc-kr', errors='replace'), 'html.parser')
            events_data = []
            for cell in soup.select("table.type_cal tbody tr td"):
                day_tag = cell.select_one("span.t_day")
                if not day_tag: continue
                day = day_tag.text.strip()
                for item in cell.select("ul li"):
                    if item.text.strip():
                        events_data.append({"날짜": f"{day}일", "일정": item.text.strip()})
            if events_data:
                return pd.DataFrame(events_data)
    except: pass
    return pd.DataFrame()

@st.cache_data(ttl=43200) 
def get_dividend_portfolio():
    portfolio = {
        "KRX": [
            ("088980.KS", "맥쿼리인프라", "반기 (6, 12월)", "6.0% ~ 6.5%"),
            ("024110.KS", "기업은행", "결산 (12월)", "7.5% ~ 8.5%"),
            ("316140.KS", "우리금융지주", "분기 (3,6,9,12월)", "8.0% ~ 9.0%"),
            ("033780.KS", "KT&G", "반기/결산", "6.0% ~ 7.0%"),
            ("017670.KS", "SK텔레콤", "분기 (3,6,9,12월)", "6.5% ~ 7.0%"),
            ("055550.KS", "신한지주", "분기 (3,6,9,12월)", "5.5% ~ 6.5%"),
            ("086790.KS", "하나금융지주", "분기/결산", "6.0% ~ 7.5%"),
            ("105560.KS", "KB금융", "분기 (3,6,9,12월)", "5.0% ~ 6.0%"),
            ("138040.KS", "메리츠금융지주", "결산 (12월)", "4.5% ~ 5.5%"),
            ("139130.KS", "DGB금융지주", "결산 (12월)", "8.0% ~ 9.0%"),
            ("175330.KS", "JB금융지주", "반기/결산", "8.0% ~ 9.0%"),
            ("138930.KS", "BNK금융지주", "결산 (12월)", "8.0% ~ 9.0%"),
            ("016360.KS", "삼성증권", "결산 (12월)", "7.0% ~ 8.0%"),
            ("005940.KS", "NH투자증권", "결산 (12월)", "7.0% ~ 8.0%"),
            ("051600.KS", "한전KPS", "결산 (12월)", "5.5% ~ 6.5%"),
            ("030200.KS", "KT", "분기 (3,6,9,12월)", "5.5% ~ 6.5%"),
            ("000815.KS", "삼성화재우", "결산 (12월)", "6.5% ~ 7.5%"),
            ("053800.KS", "현대차2우B", "분기/결산", "6.0% ~ 7.5%"),
            ("030000.KS", "제일기획", "결산 (12월)", "5.5% ~ 6.5%"),
            ("040420.KS", "정상제이엘에스", "결산 (12월)", "6.0% ~ 7.0%")
        ],
        "US": [
            ("O", "Realty Income", "월배당", "5.5% ~ 6.0%"),
            ("MO", "Altria Group", "분기 (1,4,7,10월)", "9.0% ~ 9.5%"),
            ("VZ", "Verizon", "분기 (2,5,8,11월)", "6.0% ~ 6.5%"),
            ("T", "AT&T", "분기 (1,4,7,10월)", "6.0% ~ 6.5%"),
            ("PM", "Philip Morris", "분기 (1,4,7,10월)", "5.0% ~ 5.5%"),
            ("KO", "Coca-Cola", "분기 (4,7,10,12월)", "3.0% ~ 3.5%"),
            ("PEP", "PepsiCo", "분기 (1,3,6,9월)", "2.8% ~ 3.2%"),
            ("JNJ", "Johnson & Johnson", "분기 (3,6,9,12월)", "3.0% ~ 3.5%"),
            ("PG", "Procter & Gamble", "분기 (2,5,8,11월)", "2.3% ~ 2.8%"),
            ("ABBV", "AbbVie", "분기 (2,5,8,11월)", "3.8% ~ 4.2%"),
            ("PFE", "Pfizer", "분기 (3,6,9,12월)", "5.5% ~ 6.0%"),
            ("CVX", "Chevron", "분기 (3,6,9,12월)", "4.0% ~ 4.5%"),
            ("XOM", "Exxon Mobil", "분기 (3,6,9,12월)", "3.0% ~ 3.5%"),
            ("MMM", "3M", "분기 (3,6,9,12월)", "5.5% ~ 6.5%"),
            ("IBM", "IBM", "분기 (3,6,9,12월)", "3.5% ~ 4.0%"),
            ("ENB", "Enbridge", "분기 (3,6,9,12월)", "7.0% ~ 7.5%"),
            ("WPC", "W. P. Carey", "분기 (1,4,7,10월)", "6.0% ~ 6.5%"),
            ("MAIN", "Main Street Capital", "월배당", "6.0% ~ 6.5%"),
            ("ARCC", "Ares Capital", "분기 (3,6,9,12월)", "9.0% ~ 9.5%"),
            ("KMI", "Kinder Morgan", "분기 (2,5,8,11월)", "6.0% ~ 6.5%")
        ],
        "ETF": [
            ("SCHD", "미국 SCHD (고배당 ETF)", "분기 (3,6,9,12월)", "3.4% ~ 3.8%"),
            ("JEPI", "미국 JEPI (S&P 프리미엄)", "월배당", "7.0% ~ 8.0%"),
            ("JEPQ", "미국 JEPQ (나스닥 프리미엄)", "월배당", "8.5% ~ 9.5%"),
            ("VYM", "미국 VYM (고배당 수익)", "분기 (3,6,9,12월)", "2.8% ~ 3.2%"),
            ("SPYD", "미국 SPYD (S&P500 고배당)", "분기 (3,6,9,12월)", "4.5% ~ 5.0%"),
            ("DGRO", "미국 DGRO (배당 성장)", "분기 (3,6,9,12월)", "2.2% ~ 2.6%"),
            ("QYLD", "미국 QYLD (나스닥 커버드콜)", "월배당", "11.0% ~ 12.0%"),
            ("XYLD", "미국 XYLD (S&P 커버드콜)", "월배당", "9.0% ~ 10.0%"),
            ("DIVO", "미국 DIVO (배당+옵션)", "월배당", "4.5% ~ 5.0%"),
            ("VNQ", "미국 VNQ (뱅가드 리츠)", "분기 (3,6,9,12월)", "4.0% ~ 4.5%"),
            ("458730.KS", "TIGER 미국배당다우존스", "월배당", "3.5% ~ 4.0%"),
            ("161510.KS", "ARIRANG 고배당주", "결산 (12월)", "6.0% ~ 7.0%"),
            ("458760.KS", "TIGER 미국배당+7%프리미엄", "월배당", "10.0% ~ 11.0%"),
            ("448550.KS", "ACE 미국배당다우존스", "월배당", "3.5% ~ 4.0%"),
            ("466950.KS", "KODEX 미국배당프리미엄", "월배당", "7.0% ~ 8.0%"),
            ("329200.KS", "TIGER 부동산인프라", "분기 (3,6,9,12월)", "6.5% ~ 7.5%"),
            ("091220.KS", "KODEX 은행", "결산 (12월)", "6.0% ~ 7.0%"),
            ("211560.KS", "TIGER 배당성장", "분기 (1,4,7,10월)", "4.0% ~ 5.0%"),
            ("271560.KS", "ARIRANG 미국고배당", "분기 (3,6,9,12월)", "3.5% ~ 4.5%"),
            ("433330.KS", "TIMEFOLIO 코리아플러스", "월배당", "5.0% ~ 6.0%")
        ]
    }
    
    all_tickers = []
    for cat in portfolio.values():
        for t, n, p, y in cat:
            all_tickers.append(t)
            
    price_dict = {}
    try:
        data = yf.download(all_tickers, period="5d", progress=False)
        if 'Close' in data:
            close_data = data['Close']
            for t in all_tickers:
                if t in close_data.columns:
                    val = close_data[t].dropna()
                    if not val.empty: price_dict[t] = float(val.iloc[-1])
    except Exception as e: print("YF Download error:", e)

    results = {"KRX": [], "US": [], "ETF": []}
    
    for category, stocks in portfolio.items():
        for t_code, name, period, est_yield in stocks:
            price_val = price_dict.get(t_code)
            
            if price_val:
                if ".KS" in t_code: price_str = f"{int(price_val):,}원"
                else: price_str = f"${price_val:,.2f}"
            else:
                price_str = "조회 지연"
                
            display_ticker = t_code.replace(".KS", "")
            results[category].append({
                "티커/코드": display_ticker,
                "종목명": name,
                "현재가": price_str,
                "배당수익률(예상)": est_yield,
                "배당주기": period
            })
                
    return {k: pd.DataFrame(v) for k, v in results.items()}

# 👈 [핵심 수정] st.plotly_chart 에 고유 key 파라미터 부여하여 충돌 방지
def draw_stock_card(tech_result, api_key=None, is_expanded=False, key_suffix="default"):
    status_emoji = tech_result['상태'].split(' ')[0]
    with st.expander(f"{status_emoji} {tech_result['종목명']} (현재가: {tech_result['현재가']:,}원) ｜ RSI: {tech_result['RSI']:.1f}", expanded=is_expanded):
        st.markdown(f"**진단 상태:** {tech_result['상태']} ｜ **수급/과열:** {tech_result['거래량 급증']} / {tech_result['RSI_상태']}")
        
        c1, c2, c3, c4 = st.columns(4)
        curr = tech_result['현재가']
        c1.metric("📌 진입 기준가", f"{tech_result['진입가_가이드']:,}원", f"{tech_result['진입가_가이드'] - curr:,}원 (대비)", delta_color="off")
        c2.metric("🎯 1차 (볼밴상단)", f"{tech_result['목표가1']:,}원", f"+{tech_result['목표가1'] - curr:,}원", delta_color="normal")
        c3.metric("🚀 2차 (전고점)", f"{tech_result['목표가2']:,}원", f"+{tech_result['목표가2'] - curr:,}원", delta_color="normal")
        c4.metric("🌌 3차 (오버슈팅)", f"{tech_result['목표가3']:,}원", f"+{tech_result['목표가3'] - curr:,}원", delta_color="normal")
        
        st.markdown("---")
        c5, c6, c7 = st.columns([1, 1, 2])
        c5.metric("🛑 손절 라인", f"{tech_result['손절가']:,}원", f"{tech_result['손절가'] - curr:,}원 (리스크)", delta_color="normal")
        c6.metric("📊 RSI (상대강도)", f"{tech_result['RSI']:.1f}", "과열 위험" if tech_result['RSI'] >= 70 else "바닥권" if tech_result['RSI'] <= 30 else "보통", delta_color="inverse" if tech_result['RSI'] >= 70 else "normal")
        with c7: st.markdown(f"🕵️ **최근 3일 수급 동향**<br>**외국인:** `{tech_result['외인수급']}` ｜ **기관:** `{tech_result['기관수급']}`", unsafe_allow_html=True)
        
        if api_key:
            st.markdown("<br>", unsafe_allow_html=True)
            if st.button(f"🤖 '{tech_result['종목명']}' AI 적정가 판단 및 매매 의견 듣기", key=f"ai_btn_{tech_result['티커']}_{key_suffix}"):
                with st.spinner("AI가 기업 내재 가치와 현재 타점을 종합 분석 중입니다..."):
                    ai_opinion = get_ai_trading_opinion(tech_result['종목명'], tech_result['티커'], tech_result['현재가'], tech_result['진입가_가이드'], tech_result['RSI'], api_key)
                    st.success(ai_opinion)
        
        ch1, ch2 = st.columns(2)
        price_df = tech_result["종가 데이터"].reset_index()
        price_df.columns = ['Date', 'Price']
        price_df['Date_Str'] = price_df['Date'].dt.strftime('%m/%d') 
        
        vol_df = tech_result["거래량 데이터"].reset_index()
        vol_df.columns = ['Date', 'Volume']
        vol_df['Date_Str'] = vol_df['Date'].dt.strftime('%m/%d')
        
        with ch1:
            st.caption("📈 주가 흐름 (최근 20일)")
            fig_price = px.line(price_df, x='Date_Str', y='Price', markers=True)
            fig_price.update_layout(
                margin=dict(l=0, r=0, t=10, b=0), 
                xaxis_title="", yaxis_title="", 
                yaxis_tickformat=",", 
                hovermode="x unified",
                xaxis=dict(showgrid=False, type='category'),
                yaxis=dict(showgrid=True, gridcolor='rgba(128,128,128,0.2)'),
                height=220
            )
            fig_price.update_traces(line_color="#FF4B4B", hovertemplate="<b>%{y:,}원</b>")
            # 💡 st.plotly_chart에 고유 key 추가 (이 부분 때문에 발생한 에러입니다)
            st.plotly_chart(fig_price, use_container_width=True, config={'displayModeBar': False}, key=f"price_chart_{tech_result['티커']}_{key_suffix}")
            
        with ch2:
            st.caption("📊 거래량 (최근 20일)")
            fig_vol = px.bar(vol_df, x='Date_Str', y='Volume')
            fig_vol.update_layout(
                margin=dict(l=0, r=0, t=10, b=0), 
                xaxis_title="", yaxis_title="", 
                yaxis_tickformat=",",
                hovermode="x unified", 
                xaxis=dict(showgrid=False, type='category'),
                yaxis=dict(showgrid=True, gridcolor='rgba(128,128,128,0.2)'), 
                height=220
            )
            fig_vol.update_traces(marker_color="#1f77b4", hovertemplate="<b>%{y:,}주</b>")
            # 💡 st.plotly_chart에 고유 key 추가
            st.plotly_chart(fig_vol, use_container_width=True, config={'displayModeBar': False}, key=f"vol_chart_{tech_result['티커']}_{key_suffix}")

def show_trading_guidelines():
    st.info("""
    **[매매 신호 및 타점 가이드]**
    * ✅ **타점 근접:** 주가가 20일선 근처에 위치 **(분할 매수 권장)**
    * ⚠️ **관심 집중:** 급등으로 인한 단기 이격 발생 **(눌림목 대기)**
    * 🛑 **추세 이탈:** 20일선 하향 이탈 **(손절 또는 접근 금지)**
    
    **[🎯 3단계 분할 익절 가이드]**
    * **1차 (단기 저항):** 볼린저 밴드 상단 도달 시 **절반 수익 실현**
    * **2차 (스윙 저항):** 전고점 부근 도달 시 **추가 비중 축소**
    * **3차 (오버슈팅):** 광기장 추세 연장 구간, **전량 익절** 목표
    
    **[RSI (상대강도지수) 활용 가이드]**
    * 🔴 **과열 (70 이상):** 매수세가 과도하게 몰려 단기 고점일 확률이 높습니다. **(추격 매수 자제)**
    * 🔵 **바닥 (30 이하):** 매도세가 과도하여 저평가된 상태입니다. **(과대 낙폭 줍줍 찬스)**
    * ⚪ **보통 (30 ~ 70):** 일반적인 추세 구간입니다.
    """)

# ==========================================
# 3. 사이드바 및 UI 화면 구성
# ==========================================
st.title("📈 Jaemini 스윙 트레이딩 대시보드")
st.markdown("단기 스윙 매매를 위한 **글로벌 주도주 분석** 및 **실시간 타점 모니터링** 시스템입니다.")

st.markdown("##### 🌍 실시간 글로벌 매크로 지표 & 시장 체력")

macro_data = get_macro_indicators()
fg_data = get_fear_and_greed()

m_col1, m_col2, m_col3 = st.columns([1, 1, 2])

with m_col1:
    if macro_data and 'VIX' in macro_data:
        vix_val = macro_data['VIX']['value']
        vix_prev = macro_data['VIX']['prev']
        fig_vix = go.Figure(go.Indicator(
            mode = "gauge+number+delta", value = vix_val,
            title = {'text': "<b>VIX (시장 공포지수)</b><br><span style='font-size:12px;color:gray'>20: 경계 ｜ 30: 공포 (현금확대)</span>", 'font': {'size': 15}},
            delta = {'reference': vix_prev, 'position': "top"},
            gauge = {
                'axis': {'range': [0, 50], 'tickwidth': 1, 'tickcolor': "darkblue"},
                'bar': {'color': "black", 'thickness': 0.2},
                'bgcolor': "white", 'borderwidth': 1, 'bordercolor': "gray",
                'steps': [{'range': [0, 15], 'color': "rgba(0, 255, 0, 0.3)"}, {'range': [15, 20], 'color': "rgba(255, 255, 0, 0.3)"}, {'range': [20, 30], 'color': "rgba(255, 165, 0, 0.3)"}, {'range': [30, 50], 'color': "rgba(255, 0, 0, 0.3)"}],
            }
        ))
        fig_vix.update_layout(margin=dict(l=10, r=10, t=80, b=10), height=250)
        st.plotly_chart(fig_vix, use_container_width=True, config={'displayModeBar': False})
    else:
        fig_vix = go.Figure(go.Indicator(
            mode = "gauge", value = 0,
            title = {'text': "<b>VIX (데이터 지연)</b><br><span style='font-size:12px;color:red'>야후 서버 응답 지연중</span>", 'font': {'size': 15}},
            gauge = {'axis': {'range': [0, 50]}, 'bar': {'color': "gray"}}
        ))
        fig_vix.update_layout(margin=dict(l=10, r=10, t=80, b=10), height=250)
        st.plotly_chart(fig_vix, use_container_width=True, config={'displayModeBar': False})

with m_col2:
    if fg_data:
        fg_val = fg_data['score']
        fg_prev = fg_val - fg_data['delta']
        fig_fg = go.Figure(go.Indicator(
            mode = "gauge+number+delta", value = fg_val,
            title = {'text': "<b>CNN 공포/탐욕 지수</b><br><span style='font-size:12px;color:gray'>25이하: 공포(매수) ｜ 75이상: 탐욕(매도)</span>", 'font': {'size': 15}},
            delta = {'reference': fg_prev, 'position': "top"},
            gauge = {
                'axis': {'range': [0, 100], 'tickwidth': 1, 'tickcolor': "darkblue"},
                'bar': {'color': "black", 'thickness': 0.2},
                'bgcolor': "white", 'borderwidth': 1, 'bordercolor': "gray",
                'steps': [{'range': [0, 25], 'color': "rgba(255, 0, 0, 0.4)"}, {'range': [25, 45], 'color': "rgba(255, 165, 0, 0.4)"}, {'range': [45, 55], 'color': "rgba(255, 255, 0, 0.4)"}, {'range': [55, 75], 'color': "rgba(144, 238, 144, 0.4)"}, {'range': [75, 100], 'color': "rgba(0, 128, 0, 0.4)"}],
            }
        ))
        fig_fg.update_layout(margin=dict(l=10, r=10, t=80, b=10), height=250)
        st.plotly_chart(fig_fg, use_container_width=True, config={'displayModeBar': False})
    else:
        fig_fg = go.Figure(go.Indicator(
            mode = "gauge", value = 0,
            title = {'text': "<b>CNN 공포/탐욕 지수</b><br><span style='font-size:12px;color:red'>서버 로딩 지연중</span>", 'font': {'size': 15}},
            gauge = {'axis': {'range': [0, 100]}, 'bar': {'color': "gray"}}
        ))
        fig_fg.update_layout(margin=dict(l=10, r=10, t=80, b=10), height=250)
        st.plotly_chart(fig_fg, use_container_width=True, config={'displayModeBar': False})
    
with m_col3:
    with st.container(border=True):
        st.markdown("<br>", unsafe_allow_html=True)
        c1, c2 = st.columns(2)
        if macro_data and '美 10년물 국채' in macro_data:
            c1.metric("🏦 美 10년물 국채 금리", f"{macro_data['美 10년물 국채']['value']:.3f}%", f"{macro_data['美 10년물 국채']['delta']:.3f}%", delta_color="inverse")
        else:
            c1.metric("🏦 美 10년물 국채 금리", "점검중")
            
        if macro_data and '원/달러 환율' in macro_data:
            c2.metric("💱 원/달러 환율", f"{macro_data['원/달러 환율']['value']:.1f}원", f"{macro_data['원/달러 환율']['delta']:.1f}원", delta_color="inverse")
        else:
            c2.metric("💱 원/달러 환율", "점검중")
            
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
    st.cache_data.clear()

if "gainers_df" not in st.session_state or fetch_button:
    with st.spinner('📡 글로벌 증시 데이터를 수집하는 중입니다...'):
        df, ex_rate = get_us_top_gainers()
        st.session_state.gainers_df = df
        st.session_state.ex_rate = ex_rate

tab1, tab2, tab3, tab4, tab5, tab6, tab7 = st.tabs(["🔥 🇺🇸 미국장 폭등주", "🎯 국내 종목 정밀 진단", "💡 AI 테마/관련주 검색", "📰 실시간 금융 속보", "💸 당일 거래대금 깡패", "📅 증시 캘린더", "💰 배당 파이프라인 (TOP 60)"])

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
                        st.markdown("### ✨ AI 추천 국내 수혜주 (클릭하여 타점 및 의견 확인)")
                        for i, (stock_name, ticker_code) in enumerate(kor_stocks):
                            tech_result = analyze_technical_pattern(stock_name, ticker_code)
                            if tech_result: draw_stock_card(tech_result, api_key=api_key_input, is_expanded=False, key_suffix=f"tab1_{i}")
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
            if tech_result: draw_stock_card(tech_result, api_key=api_key_input, is_expanded=True, key_suffix="tab2")
            else: st.error("❌ 데이터를 불러올 수 없습니다. (신규 상장 등으로 20일 데이터가 부족할 수 있습니다)")

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

    theme_input = st.text_input("🔍 직접 검색할 테마/키워드 입력:", value=clicked_theme if clicked_theme else "")
    
    if theme_input and api_key_input:
        with st.spinner(f"✨ AI가 증시 전체에서 '{theme_input}' 관련주를 발굴하고 타점을 진단하는 중입니다... (약 3~5초 소요)"):
            theme_stocks = get_theme_stocks_with_ai(theme_input, api_key_input)
            if theme_stocks:
                st.success(f"🎯 **'{theme_input}' 관련주 {len(theme_stocks)}개 발굴 및 진단 완료! (아래 종목을 클릭하세요)**")
                for i, (stock_name, ticker_code) in enumerate(theme_stocks):
                    tech_result = analyze_technical_pattern(stock_name, ticker_code)
                    if tech_result: draw_stock_card(tech_result, api_key=api_key_input, is_expanded=False, key_suffix=f"tab3_{i}")
            else: st.error(f"❌ '{theme_input}' 테마에 대한 관련주를 찾지 못했거나 AI 응답 지연이 발생했습니다.")

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
    
    keywords_input = st.text_input("하이라이트 및 필터링할 핵심 키워드 (쉼표로 구분):", value="AI, 반도체, 데이터센터, 원전, 로봇, 바이오, 선박, 방산, 드론")
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
                            st.info(analyze_single_news(title, api_key_input))
                    else: st.warning("사이드바에 API 키를 입력해주세요.")
                cols[2].link_button("원문 🔗", news['link'], use_container_width=True)

# ------------------------------------------
# [탭 5] 
# ------------------------------------------
with tab5:
    st.markdown("<br>", unsafe_allow_html=True)
    st.subheader("💸 실시간 당일 거래대금 깡패 스캐너")
    st.write("오늘 하루 한국 증시(코스피/코스닥)에서 돈이 가장 많이 몰리고 있는 상위 20개 종목입니다. (ETF 및 스팩주 제외)")
    
    with st.spinner("📡 거래소 데이터를 스캔 중입니다..."):
        trading_kings_df = get_trading_value_kings()
        
    if not trading_kings_df.empty:
        st.info("💡 **[매매 꿀팁]** 당일 거래대금이 가장 많이 터진 종목들은 시장의 수급이 완벽하게 쏠려있는 진짜 주도주일 확률이 높습니다.")
        display_df = trading_kings_df.copy()
        display_df.columns = ['종목코드', '종목명', '현재가', '등락률(%)', '거래대금(억원)']
        display_df['현재가'] = display_df['현재가'].apply(lambda x: f"{x:,}원")
        display_df['등락률(%)'] = display_df['등락률(%)'].apply(lambda x: f"+{x}%" if x > 0 else f"{x}%")
        display_df['거래대금(억원)'] = display_df['거래대금(억원)'].apply(lambda x: f"{x:,}억")
        
        st.dataframe(display_df, use_container_width=True, hide_index=True)
        
        st.markdown("### 🎯 주도주 즉시 타점 진단")
        king_options = ["🔍 종목을 선택하세요."] + (trading_kings_df['Name'] + " (" + trading_kings_df['Code'] + ")").tolist()
        selected_king = st.selectbox("목록에서 타점을 확인할 종목을 고르세요:", king_options)
        
        if selected_king != "🔍 종목을 선택하세요.":
            k_name = selected_king.split(" (")[0]
            k_code = selected_king.split("(")[1].replace(")", "")
            with st.spinner(f"📡 '{k_name}'의 타점 및 메이저 수급을 분석 중입니다..."):
                k_result = analyze_technical_pattern(k_name, k_code)
            if k_result: draw_stock_card(k_result, api_key=api_key_input, is_expanded=True, key_suffix="tab5")

# ------------------------------------------
# [탭 6] 
# ------------------------------------------
with tab6:
    st.markdown("<br>", unsafe_allow_html=True)
    st.subheader("📅 핵심 증시 일정 모니터링")
    st.write("시장의 방향성을 결정하는 글로벌 경제 지표와 국내 신규상장(IPO) 일정입니다.")
    
    cal_tab1, cal_tab2 = st.tabs(["🌍 글로벌 주요 경제 지표 (TradingView)", "🇰🇷 국내 주요 증시 일정 (Naver)"])
    
    with cal_tab1:
        st.info("💡 **[글로벌 매크로]** CPI, FOMC, 고용지표 등 중요 일정을 확인하세요. (TradingView 제공)")
        components.html("""<iframe scrolling="yes" allowtransparency="true" frameborder="0" src="https://s.tradingview.com/embed-widget/events/?locale=kr&importanceFilter=-1%2C0%2C1&currencyFilter=USD%2CKRW%2CCNY%2CEUR&colorTheme=light" style="box-sizing: border-box; height: 600px; width: 100%;"></iframe>""", height=600)

    with cal_tab2:
        st.info("💡 **[IPO 일정]** 이번 달 수급에 가장 직접적인 영향을 주는 국내 주식 신규상장(IPO) 표입니다.")
        
        with st.spinner("네이버 금융에서 IPO 일정을 로드 중입니다..."):
            try:
                res = requests.get("https://finance.naver.com/sise/ipo.naver", headers={"User-Agent": "Mozilla/5.0"}, timeout=5)
                res.encoding = 'euc-kr'
                tables = pd.read_html(StringIO(res.text))
                ipo_df = None
                for t in tables:
                    if '종목명' in t.columns and '상장일' in t.columns:
                        t = t.dropna(subset=['종목명', '상장일'])
                        if not t.empty:
                            ipo_df = t[['종목명', '현재가', '공모가', '청약일', '상장일']].head(15)
                            break
                
                if ipo_df is not None and not ipo_df.empty:
                    st.dataframe(ipo_df, use_container_width=True, hide_index=True)
            except:
                st.warning("⚠️ 현재 네이버 봇 차단(Cloudflare)으로 인해 자동 표 가져오기가 제한되었습니다. 아래 버튼을 이용해 주세요.")
        
        st.divider()
        st.markdown("👇 **막힘 없이 정확하게 확인하려면 아래 버튼을 클릭하여 네이버 금융으로 바로 이동하세요.**")
        btn_c1, btn_c2 = st.columns(2)
        btn_c1.link_button("🚀 네이버 신규상장(IPO) 일정 바로가기", "https://finance.naver.com/sise/ipo.naver", use_container_width=True)
        btn_c2.link_button("💰 네이버 배당금 일정 바로가기", "https://finance.naver.com/sise/dividend_list.naver", use_container_width=True)

# ------------------------------------------
# [탭 7] 고배당주
# ------------------------------------------
with tab7:
    st.markdown("<br>", unsafe_allow_html=True)
    st.subheader("💰 고배당주 & ETF 파이프라인 (TOP 60)")
    st.write("안정적인 현금흐름을 창출하는 국내외 대표 고배당 리스트입니다. (배당주기 표기)")
    
    with st.spinner("야후 파이낸스에서 60개 종목의 최신 실시간 데이터를 다운로드 중입니다... (약 3초 소요)"):
        div_dfs = get_dividend_portfolio()
        
    div_tab1, div_tab2, div_tab3 = st.tabs(["🇰🇷 국장 (한국 배당주 TOP 20)", "🇺🇸 미장 (미국 배당주 TOP 20)", "📈 배당 ETF (국내/해외 TOP 20)"])
    
    with div_tab1:
        st.info("💡 **[한국 고배당주]** 전통적으로 배당수익률이 높은 금융/통신주와 대표 배당주입니다.")
        st.dataframe(div_dfs["KRX"], use_container_width=True, hide_index=True)
    with div_tab2:
        st.info("💡 **[미국 고배당주]** 오랜 기간 배당을 늘려온 배당귀족주 및 통신/리츠 대표 종목입니다.")
        st.dataframe(div_dfs["US"], use_container_width=True, hide_index=True)
    with div_tab3:
        st.info("💡 **[배당 ETF]** 매월 현금이 들어오는 월배당 ETF 및 안정적인 배당 성장을 보여주는 인기 ETF 모음입니다.")
        st.dataframe(div_dfs["ETF"], use_container_width=True, hide_index=True)
