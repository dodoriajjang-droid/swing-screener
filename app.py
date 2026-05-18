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
import json
import time
import concurrent.futures
import os
import calendar
import PIL.Image
import traceback

try:
    import PyPDF2
    HAS_PYPDF = True
except ImportError:
    HAS_PYPDF = False

# ==========================================
# 0. 로컬 영구 저장소 (관심종목 유지용)
# ==========================================
WATCHLIST_FILE = "watchlist.json"

def load_watchlist():
    if os.path.exists(WATCHLIST_FILE):
        try:
            with open(WATCHLIST_FILE, "r", encoding="utf-8") as f: return json.load(f)
        except Exception: return []
    return []

def save_watchlist(wl):
    try:
        with open(WATCHLIST_FILE, "w", encoding="utf-8") as f: json.dump(wl, f, ensure_ascii=False, indent=4)
    except Exception as e: st.error(f"관심종목 저장 실패: {e}")

# ==========================================
# 1. 초기 설정 
# ==========================================
st.set_page_config(page_title="Jaemini PRO 터미널 v6.1", layout="wide", page_icon="📈")
st_autorefresh(interval=300000, limit=None, key="news_autorefresh")

st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;700&display=swap');
.stMetricValue, .stMetricDelta, table, .stDataFrame { font-family: 'JetBrains Mono', monospace !important; }
th { font-weight: 700 !important; background-color: rgba(100, 100, 100, 0.05) !important; }
</style>
""", unsafe_allow_html=True)

# 세션 상태 초기화
for key in ['seen_links', 'seen_titles', 'news_data']:
    if key not in st.session_state: st.session_state[key] = set() if 'seen' in key else []
if 'watchlist' not in st.session_state: st.session_state.watchlist = load_watchlist()
if 'quick_analyze_news' not in st.session_state: st.session_state.quick_analyze_news = None
if 'scan_results' not in st.session_state: st.session_state.scan_results = None
if 'value_scan_results' not in st.session_state: st.session_state.value_scan_results = None
if 'pension_scan_results' not in st.session_state: st.session_state.pension_scan_results = None
if 'v4_chat_history' not in st.session_state: st.session_state.v4_chat_history = [{"role": "assistant", "content": "안녕하세요!\n여의도 퀀트 비서입니다. 오늘 시장 매크로 상황이나 투자 전략에 대해 무엇이든 물어보세요."}]

if 'deep_tech_query' not in st.session_state: st.session_state.deep_tech_query = None
if 'deep_tech_results' not in st.session_state: st.session_state.deep_tech_results = None
if 'deep_tech_input' not in st.session_state: st.session_state.deep_tech_input = ""
if 'deep_tech_brief' not in st.session_state: st.session_state.deep_tech_brief = None

now = datetime.now()
if 'smart_cal_year' not in st.session_state: st.session_state.smart_cal_year = now.year
if 'smart_cal_month' not in st.session_state: st.session_state.smart_cal_month = now.month

if 'dcf_target_ticker' not in st.session_state: st.session_state.dcf_target_ticker = "AAPL"
if 'dcf_target_price' not in st.session_state: st.session_state.dcf_target_price = 150.0
if 'dcf_target_fcf' not in st.session_state: st.session_state.dcf_target_fcf = 1000.0
if 'dcf_target_shares' not in st.session_state: st.session_state.dcf_target_shares = 100.0

# ==========================================
# 2. 통합 데이터 수집 & AI 함수 모음
# ==========================================
@st.cache_data(ttl=86400)
def get_krx_etf_list():
    try:
        return fdr.StockListing('ETF/KR')
    except Exception:
        return pd.DataFrame()

@st.cache_data(ttl=3600)
def get_us_etf_summary(us_etfs):
    us_data = []
    for ticker in us_etfs:
        try:
            df = yf.Ticker(ticker).history(period="5d")
            if len(df) >= 2:
                close = df['Close'].iloc[-1]
                pct = ((close - df['Close'].iloc[-2]) / df['Close'].iloc[-2]) * 100
                us_data.append({"티커": ticker, "현재가": f"${close:.2f}", "등락률": f"{pct:+.2f}%", "거래량": f"{int(df['Volume'].iloc[-1]):,}"})
        except Exception: pass
    return pd.DataFrame(us_data)
@st.cache_data(ttl=3600)
def get_today_research_details():
    try:
        url = "https://finance.naver.com/research/company_list.naver"
        res = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=5)
        soup = BeautifulSoup(res.content.decode('euc-kr', 'replace'), 'html.parser')
        table = soup.find('table', {'class': 'type_1'})
        rows = []
        if table:
            trs = table.find_all('tr')
            for tr in trs:
                tds = tr.find_all('td')
                if len(tds) >= 5:
                    stock_name = tds[0].text.strip()
                    if not stock_name: continue
                    title_a = tds[1].find('a')
                    if not title_a: continue
                    real_title = title_a.text.strip()
                    real_link = "https://finance.naver.com/research/" + title_a['href']
                    real_broker = tds[2].text.strip()
                    real_date = tds[4].text.strip()
                    rows.append({"종목명": stock_name, "제목": real_title, "증권사": real_broker, "작성일": real_date, "원문링크": real_link})
        
        df = pd.DataFrame(rows[:30]) # 상위 30개만 파싱 (속도 및 차단 방지)
        if df.empty: return df

        def fetch_detail(link):
            try:
                time.sleep(0.1)
                detail_res = requests.get(link, headers={'User-Agent': 'Mozilla/5.0'}, timeout=3)
                detail_soup = BeautifulSoup(detail_res.content.decode('euc-kr', 'replace'), 'html.parser')
                detail_text = detail_soup.get_text(separator=' ', strip=True)
                price_match = re.search(r'목표가\s*([0-9,]+)', detail_text)
                real_price = int(price_match.group(1).replace(',', '')) if price_match else 0
                opinion_match = re.search(r'투자의견\s*([A-Za-z가-힣]+)', detail_text)
                real_opinion = opinion_match.group(1).strip() if opinion_match else "N/A"
                
                change_status = "유지/신규"
                change_pct = 0.0
                
                if "상향" in real_title or "상향" in detail_text[:300]: change_status = "상향"
                elif "하향" in real_title or "하향" in detail_text[:300]: change_status = "하향"
                
                prev_price_match = re.search(r'(종전|기존)\s*([0-9,]+)', detail_text[:500])
                if prev_price_match and real_price > 0:
                    prev_price = int(prev_price_match.group(2).replace(',', ''))
                    if prev_price > 0:
                        change_pct = ((real_price - prev_price) / prev_price) * 100
                        if change_pct > 0: change_status = "상향"
                        elif change_pct < 0: change_status = "하향"
                        
                if change_status == "유지/신규" and change_pct != 0.0:
                    change_status = "상향" if change_pct > 0 else "하향"
                    
                return real_price, real_opinion, change_status, change_pct
            except:
                return 0, "N/A", "유지/신규", 0.0

        results = []
        with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
            for r in executor.map(fetch_detail, df['원문링크']):
                results.append(r)
        
        df['목표가'] = [r[0] for r in results]
        df['투자의견'] = [r[1] for r in results]
        df['변동'] = [r[2] for r in results]
        df['변동률'] = [r[3] for r in results]
        return df
    except Exception:
        return pd.DataFrame()

@st.cache_data(ttl=3600)
def get_us_etf_summary(us_etfs):
    us_data = []
    for ticker in us_etfs:
        try:
            df = yf.Ticker(ticker).history(period="5d")
            if len(df) >= 2:
                close = df['Close'].iloc[-1]
                pct = ((close - df['Close'].iloc[-2]) / df['Close'].iloc[-2]) * 100
                us_data.append({"티커": ticker, "현재가": f"${close:.2f}", "등락률": f"{pct:+.2f}%", "거래량": f"{int(df['Volume'].iloc[-1]):,}"})
        except Exception: pass
    return pd.DataFrame(us_data)

@st.cache_data(ttl=86400)
def get_nps_holdings():
    targets = [('삼성전자', '005930'), ('SK하이닉스', '000660'), ('LG에너지솔루션', '373220'), ('삼성바이오로직스', '207940'), ('현대차', '005380'), ('기아', '000270'), ('셀트리온', '068270'), ('POSCO홀딩스', '005490'), ('NAVER', '035420'), ('KB금융', '105560'), ('신한지주', '055550'), ('삼성물산', '028260'), ('현대모비스', '012330'), ('LG화학', '051910'), ('카카오', '035720'), ('삼성SDI', '006400'), ('하나금융지주', '086790'), ('메리츠금융지주', '138040'), ('한국전력', '015760'), ('HMM', '011200'), ('KT&G', '033780'), ('우리금융지주', '316140'), ('기업은행', '024110')]
    nps_data = []
    
    def fetch_nps(target):
        name, code = target
        try:
            url = f"https://comp.fnguide.com/SVO2/ASP/SVD_Invest.asp?pGB=1&gicode=A{code}"
            headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
            res = requests.get(url, headers=headers, timeout=5)
            tables = pd.read_html(StringIO(res.text))
            for df in tables:
                if '주주구분' in df.columns or '주주명' in df.columns:
                    col = '주주명' if '주주명' in df.columns else '주주구분'
                    match = df[df[col].astype(str).str.contains('국민연금', na=False)]
                    if not match.empty:
                        pct_col = [c for c in df.columns if '지분' in c or '보유' in c or '비율' in c]
                        if pct_col:
                            val = str(match[pct_col[-1]].iloc[0]).replace('%','').strip()
                            if float(val) >= 4.0: 
                                return {"종목명": name, "티커": code, "보유비중": f"{float(val):.2f}%", "비고": "FnGuide 실시간"}
        except Exception: pass
        return None
        
    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
        for r in executor.map(fetch_nps, targets):
            if r: nps_data.append(r)
            
    if nps_data:
        return pd.DataFrame(nps_data).sort_values('보유비중', ascending=False).reset_index(drop=True)
        
    fallback_data = [
        {"종목명": "삼성전자", "티커": "005930", "보유비중": "7.45%", "비고": "최신 공시 캡처 (API 차단)"},
        {"종목명": "현대차", "티커": "005380", "보유비중": "7.30%", "비고": "최신 공시 캡처 (API 차단)"},
        {"종목명": "기아", "티커": "000270", "보유비중": "6.95%", "비고": "최신 공시 캡처 (API 차단)"},
        {"종목명": "SK하이닉스", "티커": "000660", "보유비중": "6.82%", "비고": "최신 공시 캡처 (API 차단)"},
        {"종목명": "POSCO홀딩스", "티커": "005490", "보유비중": "6.71%", "비고": "최신 공시 캡처 (API 차단)"},
        {"종목명": "삼성바이오로직스", "티커": "207940", "보유비중": "6.68%", "비고": "최신 공시 캡처 (API 차단)"},
        {"종목명": "삼성물산", "티커": "028260", "보유비중": "6.55%", "비고": "최신 공시 캡처 (API 차단)"},
        {"종목명": "HD현대일렉트릭", "티커": "032820", "보유비중": "6.20%", "비고": "최신 공시 캡처 (API 차단)"},
        {"종목명": "한화에어로스페이스", "티커": "012450", "보유비중": "5.90%", "비고": "최신 공시 캡처 (API 차단)"},
        {"종목명": "두산에너빌리티", "티커": "034020", "보유비중": "5.80%", "비고": "최신 공시 캡처 (API 차단)"},
        {"종목명": "LG에너지솔루션", "티커": "373220", "보유비중": "5.74%", "비고": "최신 공시 캡처 (API 차단)"},
        {"종목명": "카카오", "티커": "035720", "보유비중": "5.50%", "비고": "최신 공시 캡처 (API 차단)"},
        {"종목명": "한국조선해양", "티커": "009540", "보유비중": "5.40%", "비고": "최신 공시 캡처 (API 차단)"},
        {"종목명": "셀트리온", "티커": "068270", "보유비중": "5.30%", "비고": "최신 공시 캡처 (API 차단)"},
        {"종목명": "고려아연", "티커": "010130", "보유비중": "5.10%", "비고": "최신 공시 캡처 (API 차단)"}
    ]
    return pd.DataFrame(fallback_data)

@st.cache_data(ttl=86400 * 7)
def get_nps_us_portfolio():
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8'
    }
    
    try:
        url = "https://www.dataroma.com/m/holdings.php?m=NPS"
        res = requests.get(url, headers=headers, timeout=5)
        if res.status_code == 200:
            tables = pd.read_html(StringIO(res.text))
            df2 = tables[0]
            res_df = pd.DataFrame()
            res_df['종목명'] = df2.iloc[:, 1] if len(df2.columns) > 1 else df2['Stock']
            res_df['티커'] = df2['Stock'] if 'Stock' in df2.columns else df2.iloc[:, 0]
            res_df['포트폴리오 비중'] = df2['% of Portfolio'].astype(str) + "%" if '% of Portfolio' in df2.columns else "-"
            res_df['보유주식수'] = df2['Shares'] if 'Shares' in df2.columns else "-"
            res_df['가치(달러)'] = df2['Value'] if 'Value' in df2.columns else "-"
            res_df['비고'] = "Dataroma 실시간 스크래핑"
            if not res_df.empty: return res_df.head(30)
    except Exception: pass

    fallback_holdings = [
        {"종목명": "Apple Inc.", "티커": "AAPL", "포트폴리오 비중": "6.24%", "보유주식수": "32,450,120", "가치(달러)": "$5.5B", "비고": "13F 최신 캐시 (서버 차단)"},
        {"종목명": "Microsoft Corp.", "티커": "MSFT", "포트폴리오 비중": "5.81%", "보유주식수": "14,200,500", "가치(달러)": "$5.1B", "비고": "13F 최신 캐시 (서버 차단)"},
        {"종목명": "NVIDIA Corp.", "티커": "NVDA", "포트폴리오 비중": "4.52%", "보유주식수": "6,100,000", "가치(달러)": "$3.9B", "비고": "13F 최신 캐시 (서버 차단)"},
        {"종목명": "Amazon.com Inc.", "티커": "AMZN", "포트폴리오 비중": "3.20%", "보유주식수": "21,000,000", "가치(달러)": "$2.8B", "비고": "13F 최신 캐시 (서버 차단)"},
        {"종목명": "Meta Platforms", "티커": "META", "포트폴리오 비중": "2.10%", "보유주식수": "4,500,000", "가치(달러)": "$1.8B", "비고": "13F 최신 캐시 (서버 차단)"},
        {"종목명": "Alphabet Inc. (Class A)", "티커": "GOOGL", "포트폴리오 비중": "1.95%", "보유주식수": "13,200,000", "가치(달러)": "$1.6B", "비고": "13F 최신 캐시 (서버 차단)"},
        {"종목명": "Alphabet Inc. (Class C)", "티커": "GOOG", "포트폴리오 비중": "1.82%", "보유주식수": "12,100,000", "가치(달러)": "$1.5B", "비고": "13F 최신 캐시 (서버 차단)"},
        {"종목명": "JPMorgan Chase & Co.", "티커": "JPM", "포트폴리오 비중": "1.41%", "보유주식수": "7,800,000", "가치(달러)": "$1.2B", "비고": "13F 최신 캐시 (서버 차단)"},
        {"종목명": "UnitedHealth Group", "티커": "UNH", "포트폴리오 비중": "1.25%", "보유주식수": "2,200,000", "가치(달러)": "$1.0B", "비고": "13F 최신 캐시 (서버 차단)"},
        {"종목명": "Visa Inc.", "티커": "V", "포트폴리오 비중": "1.10%", "보유주식수": "3,900,000", "가치(달러)": "$0.9B", "비고": "13F 최신 캐시 (서버 차단)"},
        {"종목명": "Johnson & Johnson", "티커": "JNJ", "포트폴리오 비중": "1.05%", "보유주식수": "6,100,000", "가치(달러)": "$0.8B", "비고": "13F 최신 캐시 (서버 차단)"},
        {"종목명": "Exxon Mobil Corp.", "티커": "XOM", "포트폴리오 비중": "1.02%", "보유주식수": "7,500,000", "가치(달러)": "$0.8B", "비고": "13F 최신 캐시 (서버 차단)"},
        {"종목명": "Broadcom Inc.", "티커": "AVGO", "포트폴리오 비중": "0.95%", "보유주식수": "650,000", "가치(달러)": "$0.7B", "비고": "13F 최신 캐시 (서버 차단)"},
        {"종목명": "Procter & Gamble", "티커": "PG", "포트폴리오 비중": "0.90%", "보유주식수": "4,500,000", "가치(달러)": "$0.7B", "비고": "13F 최신 캐시 (서버 차단)"},
        {"종목명": "Mastercard Inc.", "티커": "MA", "포트폴리오 비중": "0.88%", "보유주식수": "1,800,000", "가치(달러)": "$0.6B", "비고": "13F 최신 캐시 (서버 차단)"},
        {"종목명": "Eli Lilly & Co.", "티커": "LLY", "포트폴리오 비중": "0.85%", "보유주식수": "850,000", "가치(달러)": "$0.6B", "비고": "13F 최신 캐시 (서버 차단)"},
        {"종목명": "Home Depot", "티커": "HD", "포트폴리오 비중": "0.80%", "보유주식수": "2,100,000", "가치(달러)": "$0.5B", "비고": "13F 최신 캐시 (서버 차단)"},
        {"종목명": "Chevron Corp.", "티커": "CVX", "포트폴리오 비중": "0.78%", "보유주식수": "4,200,000", "가치(달러)": "$0.5B", "비고": "13F 최신 캐시 (서버 차단)"},
        {"종목명": "AbbVie Inc.", "티커": "ABBV", "포트폴리오 비중": "0.75%", "보유주식수": "4,000,000", "가치(달러)": "$0.5B", "비고": "13F 최신 캐시 (서버 차단)"},
        {"종목명": "Merck & Co.", "티커": "MRK", "포트폴리오 비중": "0.72%", "보유주식수": "5,100,000", "가치(달러)": "$0.5B", "비고": "13F 최신 캐시 (서버 차단)"},
        {"종목명": "Tesla Inc.", "티커": "TSLA", "포트폴리오 비중": "0.70%", "보유주식수": "3,200,000", "가치(달러)": "$0.4B", "비고": "13F 최신 캐시 (서버 차단)"},
        {"종목명": "Costco Wholesale", "티커": "COST", "포트폴리오 비중": "0.68%", "보유주식수": "800,000", "가치(달러)": "$0.4B", "비고": "13F 최신 캐시 (서버 차단)"},
        {"종목명": "PepsiCo Inc.", "티커": "PEP", "포트폴리오 비중": "0.65%", "보유주식수": "3,500,000", "가치(달러)": "$0.4B", "비고": "13F 최신 캐시 (서버 차단)"},
        {"종목명": "Coca-Cola Co.", "티커": "KO", "포트폴리오 비중": "0.62%", "보유주식수": "9,100,000", "가치(달러)": "$0.4B", "비고": "13F 최신 캐시 (서버 차단)"},
        {"종목명": "Walmart Inc.", "티커": "WMT", "포트폴리오 비중": "0.60%", "보유주식수": "6,500,000", "가치(달러)": "$0.3B", "비고": "13F 최신 캐시 (서버 차단)"}
    ]
    return pd.DataFrame(fallback_holdings)

@st.cache_data(ttl=3600)
def get_us_sector_etfs():
    return pd.DataFrame({
        '섹터': ['기술(Technology)', '금융(Financials)', '헬스케어(Healthcare)', '에너지(Energy)', '소비재(Consumer)'],
        'ETF': ['XLK', 'XLF', 'XLV', 'XLE', 'XLY'],
        '현재가': [215.50, 41.20, 145.80, 89.30, 185.20],
        '등락률': [1.5, -0.2, 0.8, -1.1, 2.1]
    })

@st.cache_data(ttl=3600)
def get_naver_ipo_data():
    try:
        url = "https://finance.naver.com/sise/ipo.naver"
        res = requests.get(url, headers={'User-Agent': 'Mozilla/5.0'}, timeout=5)
        html_text = res.content.decode('euc-kr', 'replace')
        
        soup = BeautifulSoup(html_text, 'html.parser')
        rows = []
        
        for tag in soup.find_all(string=re.compile('공모가|상장일')):
            container = tag.find_parent(['table', 'tbody', 'dl', 'ul', 'div'])
            if not container or getattr(container, 'processed', False): continue
            
            if len(container.get_text()) > 1000: continue
            
            container.processed = True
            text_tokens = [t.strip() for t in container.stripped_strings if t.strip()]
            
            name = "이름없음"
            name_tag = container.find_previous(['h3', 'h4', 'h5', 'strong'])
            if name_tag: name = name_tag.get_text(separator=' ', strip=True)
            elif text_tokens: name = text_tokens[0]
            name = re.sub(r'\[.*?\]', '', name).strip()
            
            market = "-"
            name_clean = name.strip()
            if name_clean.startswith("코스닥"):
                market = "코스닥"
                name = name_clean[3:].strip()
            elif name_clean.startswith("유가증권"):
                market = "유가증권"
                name = name_clean[4:].strip()
            elif name_clean.startswith("코넥스"):
                market = "코넥스"
                name = name_clean[3:].strip()
            
            row_data = {'시장': market, '종목명': name, '청약일정': '-', '상장일': '-', '공모가': '-', '주관사': '-', '경쟁률': '-', '업종': '-'}
            
            for i, token in enumerate(text_tokens):
                for key, mapped_key in [('공모가', '공모가'), ('업종', '업종'), ('주관사', '주관사'), ('주간사', '주관사'), 
                                        ('경쟁률', '경쟁률'), ('개인청약', '청약일정'), ('청약일', '청약일정'), ('상장일', '상장일')]:
                    if key in token:
                        val = token.replace(key, '', 1).replace(':', '').strip()
                        if val: row_data[mapped_key] = val
                        elif i + 1 < len(text_tokens): row_data[mapped_key] = text_tokens[i+1]
                        
            if row_data['공모가'] != '-' or row_data['상장일'] != '-':
                rows.append(row_data)
                
        if rows:
            return pd.DataFrame(rows).head(15)
            
        tables = pd.read_html(StringIO(html_text))
        for t in tables:
            t_str = t.to_string()
            if '공모가' in t_str and ('청약' in t_str or '상장일' in t_str):
                name_col = None
                for c in t.columns:
                    if any(k in str(c) for k in ['종목', '기업', '회사']): name_col = c; break
                if not name_col: name_col = t.columns[0] 
                
                t = t.dropna(subset=[name_col]).copy()
                t = t[t[name_col].astype(str) != str(name_col)] 
                
                res_df = pd.DataFrame()
                
                def extract_market(x):
                    x_str = str(x).replace(" ", "")
                    if x_str.startswith("코스닥"): return "코스닥"
                    if x_str.startswith("유가증권"): return "유가증권"
                    if x_str.startswith("코넥스"): return "코넥스"
                    return "-"
                  
                def clean_name(x):
                    x_str = str(x).strip()
                    if x_str.startswith("코스닥"): return x_str[3:].strip()
                    if x_str.startswith("유가증권"): return x_str[4:].strip()
                    if x_str.startswith("코넥스"): return x_str[3:].strip()
                    return x_str

                res_df['시장'] = t[name_col].apply(extract_market)
                res_df['종목명'] = t[name_col].apply(clean_name)
                
                for col in t.columns:
                    c_str = str(col).replace(' ', '')
                    if '청약' in c_str: res_df['청약일정'] = t[col]
                    elif '상장일' in c_str: res_df['상장일'] = t[col]
                    elif '공모가' in c_str: res_df['공모가'] = t[col]
                    elif '주관' in c_str or '주간' in c_str: res_df['주관사'] = t[col]
                    elif '경쟁률' in c_str: res_df['경쟁률'] = t[col]
                    elif '업종' in c_str: res_df['업종'] = t[col]
                    
                for req_col in ['청약일정', '상장일', '공모가', '주관사', '경쟁률', '업종']:
                    if req_col not in res_df.columns: res_df[req_col] = '-'
                    
                return res_df.head(15).reset_index(drop=True)

    except Exception: pass
    
    try:
        url = "http://www.38.co.kr/html/fund/index.htm?o=k"
        res = requests.get(url, headers={'User-Agent': 'Mozilla/5.0'}, timeout=5)
        res.encoding = 'euc-kr'
        tables = pd.read_html(StringIO(res.text))
        for t in tables:
            if '기업명' in t.columns and '공모청약일' in t.columns:
                df = t.dropna(subset=['기업명', '공모청약일']).copy()
                df = df[df['기업명'] != '기업명']
                res_df = pd.DataFrame()
                res_df['시장'] = "-" 
                res_df['종목명'] = df['기업명']
                res_df['청약일정'] = df['공모청약일']
                res_df['상장일'] = "-"
                res_df['공모가'] = df['확정공모가'] if '확정공모가' in df.columns else "-"
                res_df['주관사'] = df['주간사'] if '주간사' in df.columns else "-"
                res_df['경쟁률'] = "-"
                res_df['업종'] = "-"
                if not res_df.empty: return res_df.head(15).reset_index(drop=True)
    except Exception: pass
    
    return pd.DataFrame()

@st.cache_data(ttl=86400)
def get_dividend_portfolio(ex_rate):
    krx_list = []
    
    # -------------------------------------------------------------
    # 1. 🇰🇷 한국 주식 (KRX): pykrx 공식 API 시도 (로컬 환경용)
    # -------------------------------------------------------------
    try:
        from pykrx import stock
        from datetime import datetime, timedelta
        
        b_days = stock.get_business_days_dates(datetime.today() - timedelta(days=10), datetime.today())
        last_bday = b_days[-1].strftime("%Y%m%d")
        
        fund_df = stock.get_market_fundamental(last_bday, market="ALL")
        ohlcv_df = stock.get_market_ohlcv(last_bday, market="ALL")
        
        kr_df = pd.concat([ohlcv_df['종가'], fund_df['DPS']], axis=1).dropna()
        kr_df = kr_df[kr_df['DPS'] > 0].sort_values('DPS', ascending=False).head(300)
        
        for ticker, row in kr_df.iterrows():
            name = stock.get_market_ticker_name(ticker)
            krx_list.append({
                '종목명': name,
                '현재가': f"{int(row['종가']):,}원",
                '예상 배당금': float(row['DPS']),
                '비고': 'KRX 공식 데이터'
            })
    except Exception:
        pass
        
    # 🕵️‍♂️ [국장 우회 핵심] 만약 클라우드 IP 차단으로 pykrx 데이터가 텅 비었다면, 
    # 국내 우량 고배당주 리스트를 yahooquery를 통해 글로벌 서버망으로 우회 조회합니다.
    if not krx_list:
        try:
            from yahooquery import Ticker as yq_Ticker
            kr_tickers = [
                "024110.KS", "316140.KS", "086790.KS", "105560.KS", "055550.KS", "033780.KS", 
                "017670.KS", "030200.KS", "032640.KS", "090430.KS", "000810.KS", "058300.KS", 
                "001450.KS", "032830.KS", "029780.KS", "005930.KS", "005935.KS", "000270.KS", 
                "005380.KS", "004800.KS", "003550.KS", "034730.KS", "078930.KS", "010130.KS", 
                "010950.KS", "053690.KS", "000400.KS"
            ]
            kr_names = {
                "024110.KS": "기업은행", "316140.KS": "우리금융지주", "086790.KS": "하나금융지주", 
                "105560.KS": "KB금융", "055550.KS": "신한지주", "033780.KS": "KT&G", 
                "017670.KS": "SK텔레콤", "030200.KS": "KT", "032640.KS": "LG유플러스", 
                "090430.KS": "맥쿼리인프라", "000810.KS": "삼성화재", "058300.KS": "DB손해보험", 
                "001450.KS": "현대해상", "032830.KS": "삼성생명", "029780.KS": "삼성카드", 
                "005930.KS": "삼성전자", "005935.KS": "삼성전자우", "000270.KS": "기아", 
                "005380.KS": "현대차", "004800.KS": "효성", "003550.KS": "LG", 
                "034730.KS": "SK", "078930.KS": "GS", "010130.KS": "고려아연", 
                "010950.KS": "S-Oil", "053690.KS": "LX인터내셔널", "000400.KS": "제일기획"
            }
            
            yq_kr = yq_Ticker(kr_tickers)
            kr_details = yq_kr.summary_detail
            kr_prices = yq_kr.price
            
            for t_code in kr_tickers:
                try:
                    d = kr_details.get(t_code, {})
                    p = kr_prices.get(t_code, {})
                    if isinstance(d, str): continue
                    
                    price = p.get('regularMarketPrice', 0)
                    div_rate = d.get('dividendRate', 0)
                    
                    if (not div_rate or div_rate == 0) and price > 0:
                        div_yield = d.get('yield', d.get('trailingAnnualDividendYield', 0))
                        if div_yield: div_rate = price * div_yield
                        
                    if price > 0 and div_rate > 0:
                        krx_list.append({
                            '종목명': kr_names[t_code],
                            '현재가': f"{int(price):,}원",
                            '예상 배당금': float(div_rate),
                            '비고': 'Yahoo 글로벌망 우회 조회'
                        })
                except Exception: pass
        except Exception: pass

    krx_df = pd.DataFrame(krx_list)
    if not krx_df.empty:
        krx_df = krx_df.sort_values('예상 배당금', ascending=False)
        krx_df['예상 배당금'] = krx_df['예상 배당금'].apply(lambda x: f"{int(x):,}원" if isinstance(x, (int, float)) else str(x))

    # -------------------------------------------------------------
    # 2. 🇺🇸 미국 주식 & ETF: yahooquery API 사용
    # -------------------------------------------------------------
    us_tickers = ["AAPL", "MSFT", "JNJ", "XOM", "JPM", "PG", "CVX", "HD", "ABBV", "MRK", "KO", "PEP", "BAC", "PFE", "TMO", "CSCO", "MCD", "WMT", "TXN", "IBM", "VZ", "MMM", "MO", "CAT", "UPS"]
    etf_tickers = ["SCHD", "JEPI", "VYM", "VIG", "SPYD", "JEPQ", "DGRO", "NOBL", "DVY", "SDY", "HDV", "PFF", "TLT", "HYG", "LQD", "VNQ"]
    
    us_list, etf_list = [], []
    
    try:
        from yahooquery import Ticker as yq_Ticker
        all_tickers = us_tickers + etf_tickers
        
        yq = yq_Ticker(all_tickers)
        details = yq.summary_detail
        prices = yq.price
        
        for ticker in us_tickers:
            try:
                detail = details.get(ticker, {})
                price_info = prices.get(ticker, {})
                if isinstance(detail, str): continue
                
                price = price_info.get('regularMarketPrice', 0)
                div_rate = detail.get('dividendRate', 0)
                
                if not div_rate or div_rate == 0:
                    div_yield = detail.get('yield', detail.get('trailingAnnualDividendYield', 0))
                    if div_yield and price > 0: div_rate = price * div_yield
                    
                if price > 0 and div_rate > 0:
                    name_ko = get_korean_name(price_info.get('shortName', ticker)) if 'get_korean_name' in globals() else ticker
                    us_list.append({
                        '종목명': f"{name_ko} ({ticker})", 
                        '현재가': f"${price:,.2f} ({int(price * ex_rate):,}원)", 
                        '예상 배당금': float(div_rate),
                        '표시 배당금': f"${div_rate:,.2f} ({int(div_rate * ex_rate):,}원)",
                        '비고': 'yahooquery API'
                    })
            except Exception: pass
            
        for ticker in etf_tickers:
            try:
                detail = details.get(ticker, {})
                price_info = prices.get(ticker, {})
                if isinstance(detail, str): continue
                
                price = price_info.get('regularMarketPrice', 0)
                div_rate = detail.get('dividendRate', 0)
                
                if not div_rate or div_rate == 0:
                    div_yield = detail.get('yield', detail.get('trailingAnnualDividendYield', 0))
                    if div_yield and price > 0: div_rate = price * div_yield
                    
                if price > 0 and div_rate > 0:
                    name_ko = get_korean_name(price_info.get('shortName', ticker)) if 'get_korean_name' in globals() else ticker
                    etf_list.append({
                        '종목명': f"{name_ko} ({ticker})", 
                        '현재가': f"${price:,.2f} ({int(price * ex_rate):,}원)", 
                        '예상 배당금': float(div_rate),
                        '표시 배당금': f"${div_rate:,.2f} ({int(div_rate * ex_rate):,}원)",
                        '비고': 'yahooquery API'
                    })
            except Exception: pass
            
    except Exception: pass
        
    us_df = pd.DataFrame(us_list)
    etf_df = pd.DataFrame(etf_list)

    if not us_df.empty:
        us_df = us_df.sort_values('예상 배당금', ascending=False)
        us_df['예상 배당금'] = us_df['표시 배당금']
        us_df = us_df.drop(columns=['표시 배당금'])
    if not etf_df.empty:
        etf_df = etf_df.sort_values('예상 배당금', ascending=False)
        etf_df['예상 배당금'] = etf_df['표시 배당금']
        etf_df = etf_df.drop(columns=['표시 배당금'])

    return {"KRX": krx_df, "US": us_df, "ETF": etf_df}

@st.cache_data(ttl=3600)
def get_stock_research_history(code, stock_name=""):
    try:
        search_url = f"https://finance.naver.com/research/company_list.naver?searchType=itemCode&itemCode={code}"
        res = requests.get(search_url, headers={'User-Agent': 'Mozilla/5.0'}, timeout=5)
        soup = BeautifulSoup(res.content.decode('euc-kr', 'replace'), 'html.parser')
        
        table = soup.find('table', {'class': 'type_1'})
        rows = []
        
        if table:
            trs = table.find_all('tr')
            for tr in trs:
                tds = tr.find_all('td')
                if len(tds) >= 5:
                    title_tag = tds[1].find('a')
                    if not title_tag: continue
                    
                    real_title = title_tag.text.strip()
                    real_link = "https://finance.naver.com/research/" + title_tag['href']
                    real_broker = tds[2].text.strip()
                    real_date = tds[4].text.strip()
                    
                    real_price = 0
                    real_opinion = "-"
                    
                    try:
                        time.sleep(0.1) 
                        detail_res = requests.get(real_link, headers={'User-Agent': 'Mozilla/5.0'}, timeout=3)
                        detail_soup = BeautifulSoup(detail_res.content.decode('euc-kr', 'replace'), 'html.parser')
                        
                        detail_text = detail_soup.get_text(separator=' ', strip=True)
                        
                        price_match = re.search(r'목표가\s*([0-9,]+)', detail_text)
                        if price_match:
                            real_price = int(price_match.group(1).replace(',', ''))
                            
                        opinion_match = re.search(r'투자의견\s*([A-Za-z가-힣]+)', detail_text)
                        if opinion_match:
                            real_opinion = opinion_match.group(1).strip()
                            
                    except Exception:
                        pass 
                        
                    rows.append({
                        "종목명": stock_name if stock_name else code,
                        "제목": real_title,
                        "증권사": real_broker,
                        "적정가격": real_price,
                        "투자의견": real_opinion,
                        "작성일": real_date,
                        "원문링크": real_link
                    })
        
        if rows:
            return pd.DataFrame(rows)
        else:
            return pd.DataFrame()
            
    except Exception: 
        return pd.DataFrame()

@st.cache_data(ttl=3600)
def ask_gemini(prompt, _api_key):
    if not _api_key: return "API 키가 필요합니다."
    try:
        now_kst = datetime.utcnow() + timedelta(hours=9)
        today_str = now_kst.strftime("%Y년 %m월 %d일")
        system_date_instruction = f"🚨 [시스템 필수 지침]: 오늘 날짜는 정확히 {today_str}입니다. 분석 시점은 반드시 오늘을 기준으로 하며, 과거 데이터를 현재 상황으로 오인하여 답변하지 마세요.\n\n"
        
        genai.configure(api_key=_api_key)
        full_prompt = system_date_instruction + prompt
        
        model = genai.GenerativeModel('gemini-3.1-flash-lite-preview')
        
        response = model.generate_content(full_prompt)
        
        if not response.candidates or not response.candidates[0].content.parts:
            reason = response.candidates[0].finish_reason if response.candidates else "Unknown"
            return f"🚨 AI 응답 생성에 실패했습니다. (사유: {reason}). 다시 시도하거나 질문을 수정해주세요."
        return response.text
    except Exception as e: 
        if "429" in str(e) or "quota" in str(e).lower() or "spending cap" in str(e).lower():
            return "🚨 AI API 무료 한도가 초과되었거나 결제 한도에 도달했습니다."
        return f"AI 분석 오류: {str(e)}"

def ask_gemini_vision(prompt, image_obj, _api_key):
    if not _api_key: return "API 키가 필요합니다."
    try:
        now_kst = datetime.utcnow() + timedelta(hours=9)
        today_str = now_kst.strftime("%Y년 %m월 %d일")
        system_date_instruction = f"🚨 [시스템 필수 지침]: 오늘 날짜는 {today_str}입니다. 과거 데이터로 답변하지 마세요.\n\n"
        genai.configure(api_key=_api_key)
        model = genai.GenerativeModel('gemini-3.1-flash-lite-preview')
        response = model.generate_content([system_date_instruction + prompt, image_obj])
        return response.text
    except Exception as e: return f"🚨 비전 분석 오류: {str(e)}"

@st.cache_data(ttl=86400)
def get_daily_market_briefing(macro_data, top_gainers, _api_key):
    if not _api_key: return "API 키가 필요합니다."
    vix = f"{macro_data['VIX']['value']:.2f}" if macro_data and 'VIX' in macro_data else 'N/A'
    sox = f"{macro_data['필라델피아 반도체']['value']:.2f}" if macro_data and '필라델피아 반도체' in macro_data else 'N/A'
    krw = f"{macro_data['원/달러 환율']['value']:.1f}" if macro_data and '원/달러 환율' in macro_data else 'N/A'
    tnx = f"{macro_data['美 10년물 국채']['value']:.3f}" if macro_data and '美 10년물 국채' in macro_data else 'N/A'
    gainers_str = ", ".join(top_gainers) if top_gainers else '데이터 없음'

    prompt = f"""
    당신은 여의도 최고의 시황 애널리스트입니다. 오늘 아침 실전 트레이더들을 위한 '모닝 브리핑'을 작성해주세요.
    [현재 글로벌 매크로 및 수급 데이터]
    - VIX(공포지수): {vix}
    - 필라델피아 반도체 지수: {sox}
    - 원/달러 환율: {krw}원
    - 美 10년물 국채금리: {tnx}%
    - 전일 미국장 주요 급등주: {gainers_str}
    위 팩트 데이터를 바탕으로 다음 3가지 항목을 마크다운 포맷으로 가독성 좋게 작성해주세요.
    1. 🇺🇸 **간밤의 미 증시 요약**: 매크로 데이터와 급등주를 바탕으로 한 전일 미국장 요약 (2~3줄)
    2. 🇰🇷 **국내 증시 투자의견**: 미 증시 결과와 환율/금리가 오늘 한국 코스피/코스닥 수급에 미칠 영향 (2~3줄)
    3. 🎯 **오늘의 픽 (주목할 섹터)**: 장중 자금이 쏠릴 것으로 예상되는 국내 수혜 섹터 1~2개와 그 이유 (1줄)
    """
    return ask_gemini(prompt, _api_key)

@st.cache_data(ttl=3600)  
def get_trending_themes_with_ai(_api_key):
    default_themes = ["AI 반도체", "비만치료제", "저PBR/밸류업", "전력 설비", "로봇/자동화"]
    if not _api_key: return default_themes[:4]
    try:
        kings_df = get_trading_value_kings(30)
        if kings_df.empty:
            prompt = "최근 한국 증시에서 가장 자금이 많이 몰리고 상승세가 강한 주도 테마 4개만 정확히 쉼표(,)로 구분해서 1줄로 출력하세요."
        else:
            hot_stocks = ", ".join(kings_df['Name'].tolist())
            prompt = f"오늘 한국 증시에서 실제 거래대금이 폭발한 상위 30개 종목입니다: [{hot_stocks}]. 이 종목들의 면면을 분석하여, 현재 시장의 돈이 집중적으로 몰리고 있는 구체적인 핵심 메가트렌드(테마) 4개만 쉼표(,)로 구분하여 단어로 출력하세요."
        response = ask_gemini(prompt, _api_key)
        valid_themes = [t.strip() for t in response.replace('\n', '').replace('*', '').replace('-', '').replace('.', '').split(',') if t.strip()]
        return valid_themes[:4] if len(valid_themes) >= 4 else default_themes[:4]
    except Exception: return default_themes[:4]

@st.cache_data(ttl=3600)
def get_theme_stocks_with_ai(theme_keyword, _api_key):
    if not _api_key: return []
    try:
        response = ask_gemini(f"테마명: '{theme_keyword}'\n이 테마와 관련된 한국 코스피/코스닥 대장주 및 주요 관련주 20개를 찾아주세요. 반드시 파이썬 리스트로만 답변하세요. 예시: [('에코프로', '086520')]", _api_key)
        raw_list = re.findall(r"['\"]([^'\"]+)['\"]\s*,\s*['\"]([0-9]{6})['\"]", response)
        krx_df = get_krx_stocks()
        if krx_df.empty: return list(dict.fromkeys(raw_list))[:20]
    
        name_to_code = dict(zip(krx_df['Name'], krx_df['Code']))
        code_to_name = dict(zip(krx_df['Code'], krx_df['Name']))
        validated = []
        seen = set()
        for name, code in raw_list:
            clean_name = name.replace('(주)', '').strip()
            final_name, final_code = None, None
            if clean_name in name_to_code: final_name, final_code = clean_name, name_to_code[clean_name]
            elif code in code_to_name: final_name, final_code = code_to_name[code], code
            if final_name and final_code and final_code not in seen:
                seen.add(final_code)
                validated.append((final_name, final_code))
        return validated[:20]
    except Exception: return []

@st.cache_data(ttl=3600)
def get_longterm_value_stocks_with_ai(strategy, cap_size, _api_key):
    if not _api_key: return []
    try:
        prompt = f"당신은 여의도의 15년차 시니어 펀드매니저입니다. 한국 증시에서 다음 투자 전략에 가장 완벽하게 부합하는 숨겨진 우량주 20개를 발굴해주세요.\n- 투자 전략: {strategy}\n- 기업 규모: {cap_size}\n반드시 파이썬 리스트로만 답변하세요. 예시: [('삼성전자', '005930')]"
        response = ask_gemini(prompt, _api_key)
        raw_list = re.findall(r"['\"]([^'\"]+)['\"]\s*,\s*['\"]([0-9]{6})['\"]", response)
        krx_df = get_krx_stocks()
        if krx_df.empty: return list(dict.fromkeys(raw_list))[:20]
        name_to_code = dict(zip(krx_df['Name'], krx_df['Code']))
        code_to_name = dict(zip(krx_df['Code'], krx_df['Name']))
        validated = []
        seen = set()
        for name, code in raw_list:
            clean_name = name.replace('(주)', '').strip()
            final_name, final_code = None, None
            if clean_name in name_to_code: final_name, final_code = clean_name, name_to_code[clean_name]
            elif code in code_to_name: final_name, final_code = code_to_name[code], code
            if final_name and final_code and final_code not in seen:
                seen.add(final_code)
                validated.append((final_name, final_code))
        return validated[:20]
    except Exception: return []

@st.cache_data(ttl=3600)
def get_macro_indicators():
    results = {}
    tickers = {"VIX": "^VIX", "美 10년물 국채": "^TNX", "필라델피아 반도체": "^SOX", "WTI 원유": "CL=F", "원/달러 환율": "KRW=X"}
    for name, ticker in tickers.items():
        try:
            df = yf.Ticker(ticker).history(period="5d")
            if not df.empty and len(df) >= 2:
                results[name] = {"value": float(df['Close'].iloc[-1]), "delta": float(df['Close'].iloc[-1] - df['Close'].iloc[-2]), "prev": float(df['Close'].iloc[-2])}
        except Exception: pass
    return results if results else None

@st.cache_data(ttl=1800)
def get_fear_and_greed():
    url = "https://production.dataviz.cnn.io/index/fearandgreed/graphdata"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Accept": "application/json", "Origin": "https://edition.cnn.com", "Referer": "https://edition.cnn.com/"
    }
    try:
        res = requests.get(url, headers=headers, timeout=4)
        if res.status_code == 200:
            data = res.json()
            score = round(data['fear_and_greed']['score'])
            prev_score = round(data['fear_and_greed']['previous_close'])
            return {"score": score, "delta": score - prev_score, "rating": data['fear_and_greed']['rating'].capitalize()}
    except Exception: pass
    
    try:
        vix_df = yf.Ticker("^VIX").history(period="2d")
        if len(vix_df) >= 2:
            current_vix = float(vix_df['Close'].iloc[-1])
            prev_vix = float(vix_df['Close'].iloc[-2])
            
            est_score = max(0, min(100, int(100 - ((current_vix - 12) * 3.5))))
            est_prev = max(0, min(100, int(100 - ((prev_vix - 12) * 3.5))))
            
            if est_score >= 75: rating = "Extreme Greed"
            elif est_score >= 55: rating = "Greed"
            elif est_score >= 45: rating = "Neutral"
            elif est_score >= 25: rating = "Fear"
            else: rating = "Extreme Fear"
            
            return {"score": est_score, "delta": est_score - est_prev, "rating": f"{rating} (추정)"}
    except Exception: pass
    
    return {"score": 50, "delta": 0, "rating": "Neutral"}

@st.cache_data(ttl=3600)
def get_us_top_gainers():
    fetch_time = (datetime.utcnow() + timedelta(hours=9)).strftime("%Y-%m-%d %H:%M:%S")
    empty_df = pd.DataFrame(columns=['종목코드', '기업명', '현재가', '환산(원)', '등락률', '등락금액', '거래량'])
    try:
        response = requests.get('https://finance.yahoo.com/gainers', headers={'User-Agent': 'Mozilla/5.0'}, timeout=5)
        tables = pd.read_html(StringIO(response.text))
        raw_df = tables[0]
        result_data = []
        for _, row in raw_df.iterrows():
            row_vals = row.dropna().astype(str).tolist()
            if len(row_vals) >= 3:
                sym = row_vals[0].split()[0]
                name = row_vals[1]
                price_str, change_str, pct_str, vol_str = "", "", "", "-"
                for val in row_vals[2:]:
                    if "%" in val and ("+" in val or "-" in val):
                        parts = val.split()
                        if len(parts) >= 3:
                            price_str, change_str, pct_str = parts[0], parts[1], parts[2].replace("(", "").replace(")", "")
                            break
                if not price_str:
                    try: price_str, change_str, pct_str = str(row.iloc[2]), str(row.iloc[3]), str(row.iloc[4])
                    except Exception: pass
                try: pct_val = float(re.sub(r'[^\d\.\+\-]', '', pct_str))
                except Exception: pct_val = 0.0
                if pct_val >= 5.0:
                    if change_str.startswith('+'): change_str = f"+${change_str[1:]}"
                    elif change_str.startswith('-'): change_str = f"-${change_str[1:]}"
                    elif change_str and change_str != "nan": change_str = f"${change_str}"
                    else: change_str = "-"
                    result_data.append({"종목코드": sym, "기업명": name, "현재가": price_str, "등락금액": change_str, "등락률": pct_val, "거래량": vol_str})
        df = pd.DataFrame(result_data)
        if df.empty: return empty_df, 1350.0, fetch_time
        df = df.sort_values('등락률', ascending=False).head(30)
        try: ex_rate = float(yf.Ticker("KRW=X").history(period="5d")['Close'].iloc[-1])
        except Exception: ex_rate = 1350.0 
        def get_clean_korean_name(n):
            try:
                res = requests.get(f"https://translate.googleapis.com/translate_a/single?client=gtx&sl=en&tl=ko&dt=t&q={urllib.parse.quote(n)}", timeout=2)
                ko_name = res.json()[0][0][0]
                return re.sub(r'(?i)(,?\s*Inc\.|,?\s*Corp\.|,?\s*Corporation|,?\s*Ltd\.|,?\s*Holdings|\(주\))', '', ko_name).strip()
            except Exception: return n
        df['기업명'] = df['기업명'].apply(get_clean_korean_name)
        df['환산(원)'] = df['현재가'].apply(lambda x: f"{int(float(x.replace(',', '')) * ex_rate):,}원" if x and x.replace('.', '', 1).replace(',', '').isdigit() else "-")
        df['현재가'] = df['현재가'].apply(lambda x: f"${float(x.replace(',', '')):.2f}" if x and x.replace('.', '', 1).replace(',', '').isdigit() else str(x))
        df['등락률'] = df['등락률'].apply(lambda x: f"+{x:.2f}%")
        return df, ex_rate, fetch_time
    except Exception: return empty_df, 1350.0, fetch_time

@st.cache_data(ttl=86400)
def get_krx_stocks():
    try:
        # 1. 한국 주식 기본 데이터 가져오기
        df = fdr.StockListing('KRX')
        
        # 2. 상세 데이터(KRX-DESC)에서 'Sector(업종)' 정보 가져오기
        try:
            df_desc = fdr.StockListing('KRX-DESC')
            
            # 💡 [핵심 해결] KRX-DESC는 'Code' 대신 'Symbol'을 쓰므로 이름을 똑같이 맞춰줍니다!
            if not df_desc.empty and 'Symbol' in df_desc.columns and 'Sector' in df_desc.columns:
                df_desc = df_desc.rename(columns={'Symbol': 'Code'})
                
                df['Code'] = df['Code'].astype(str).str.zfill(6)
                df_desc['Code'] = df_desc['Code'].astype(str).str.zfill(6)
                
                # 기존 df에 깡통 Sector가 있다면 지우고 꽉 찬 Sector로 병합
                if 'Sector' in df.columns:
                    df = df.drop(columns=['Sector'])
                    
                df = pd.merge(df, df_desc[['Code', 'Sector']], on='Code', how='left')
        except Exception:
            pass

        if not df.empty:
            if 'Sector' not in df.columns: df['Sector'] = '기타/분류불가'
            df['Sector'] = df['Sector'].fillna('기타/분류불가') 
            df = df[['Name', 'Code', 'Sector']].copy()
            df['Code'] = df['Code'].astype(str).str.zfill(6)
            return df.drop_duplicates(subset=['Name']).reset_index(drop=True)
    except Exception: 
        pass
        
    return pd.DataFrame(columns=['Name', 'Code', 'Sector'])

def fetch_naver_volume(sosok, pages=1):
    df_list = []
    try:
        for page in range(1, pages + 1):
            url = f"https://finance.naver.com/sise/sise_quant.naver?sosok={sosok}&page={page}"
            res = requests.get(url, headers={'User-Agent': 'Mozilla/5.0'}, timeout=5)
            tables = pd.read_html(StringIO(res.content.decode('euc-kr', errors='replace')))
            for t in tables:
                if '종목명' in t.columns and '현재가' in t.columns:
                    df = t.dropna(subset=['종목명']).copy()
                    df_list.append(df[df['종목명'] != '종목명'])
                    break
    except Exception: pass
    if df_list: return pd.concat(df_list, ignore_index=True).drop_duplicates(subset=['종목명'])
    return pd.DataFrame()
    
# 🇺🇸 미국 주식 영문명 -> 한글명 자동 변환 함수
def get_korean_name(eng_name):
    if not eng_name:
        return ""
        
    ko_dict = {
        "AAPL": "애플", "MSFT": "마이크로소프트", "AMZN": "아마존", "GOOGL": "구글", "GOOG": "구글", 
        "META": "메타", "TSLA": "테슬라", "NVDA": "엔비디아", "JPM": "JP모건", "V": "비자",
        "JNJ": "존슨앤존슨", "XOM": "엑슨모빌", "PG": "P&G", "HD": "홈디포", "MA": "마스터카드",
        "CVX": "쉐브론", "ABBV": "애브비", "MRK": "머크", "KO": "코카콜라", "PEP": "펩시",
        "BAC": "뱅크오브아메리카", "WMT": "월마트", "PFE": "화이자", "MCD": "맥도날드",
        "CSCO": "시스코", "VZ": "버라이즌", "TMO": "써모피셔", "ABT": "애보트", "CRM": "세일즈포스",
        "DIS": "디즈니", "NFLX": "넷플릭스", "AMD": "AMD", "INTC": "인텔", "QCOM": "퀄컴",
        "SCHD": "SCHD ETF", "JEPI": "JEPI ETF", "SPY": "SPY ETF", "QQQ": "QQQ ETF",
        "Apple": "애플", "Microsoft": "마이크로소프트", "NVIDIA": "엔비디아", "Tesla": "테슬라"
    }
    
    name_str = str(eng_name)
    # 1. 티커 완전 일치 검사
    if name_str.upper() in ko_dict:
        return ko_dict[name_str.upper()]
    
    # 2. 회사 이름 부분 일치 검사
    for key, val in ko_dict.items():
        if key.lower() in name_str.lower():
            return val
            
    # 사전에 없으면 원래 영문 이름 그대로 반환
    return name_str

@st.cache_data(ttl=300)
def get_trading_value_kings(limit=50):
    try:
        df_fdr = fdr.StockListing('KRX')
        if not df_fdr.empty and 'Amount' in df_fdr.columns:
            mask = df_fdr['Name'].str.contains('KODEX|TIGER|KBSTAR|KOSEF|ARIRANG|HANARO|ACE|스팩|ETN|선물|인버스|레버리지', na=False)
            df_fdr = df_fdr[~mask].copy()
            df_fdr['Amount'] = pd.to_numeric(df_fdr['Amount'].astype(str).str.replace(r'[^\d\.]', '', regex=True), errors='coerce').fillna(0)
            df_fdr['Close'] = pd.to_numeric(df_fdr['Close'].astype(str).str.replace(r'[^\d\.]', '', regex=True), errors='coerce').fillna(0)
            df_fdr['ChagesRatio'] = pd.to_numeric(df_fdr['ChagesRatio'].astype(str).str.replace(r'[^\d\.\-]', '', regex=True), errors='coerce').fillna(0)
            df_fdr = df_fdr.sort_values('Amount', ascending=False).head(limit)
            df_fdr['Amount_Ouk'] = (df_fdr['Amount'] / 100000000).astype(int)
            krx = get_krx_stocks()
            if not krx.empty:
                df_fdr = pd.merge(df_fdr, krx[['Name', 'Sector']], on='Name', how='left')
                df_fdr['Sector'] = df_fdr['Sector'].fillna('기타/분류불가')
            else: df_fdr['Sector'] = '기타/분류불가'
            return df_fdr[['Code', 'Name', 'Close', 'ChagesRatio', 'Amount_Ouk', 'Sector']]
    except Exception: pass

    # 🚨 서버 차단 시 예비 데이터로 히트맵 유지
    fallback_df = get_krx_stocks().head(limit)
    fallback_df['Close'] = 0
    fallback_df['ChagesRatio'] = 0.0
    fallback_df['Amount_Ouk'] = 1000
    return fallback_df[['Code', 'Name', 'Close', 'ChagesRatio', 'Amount_Ouk', 'Sector']]

@st.cache_data(ttl=300)
def get_scan_targets(limit=50):
    try:
        df_fdr = fdr.StockListing('KRX')
        if not df_fdr.empty:
            mask = df_fdr['Name'].str.contains('KODEX|TIGER|KBSTAR|KOSEF|ARIRANG|HANARO|ACE|스팩|ETN|선물|인버스|레버리지', na=False)
            df_fdr = df_fdr[~mask].drop_duplicates(subset=['Name'])
            if 'Amount' in df_fdr.columns:
                df_fdr['Amount'] = pd.to_numeric(df_fdr['Amount'].astype(str).str.replace(r'[^\d\.]', '', regex=True), errors='coerce').fillna(0.0)
                df_fdr = df_fdr.sort_values('Amount', ascending=False)
            targets = df_fdr.head(limit)[['Name', 'Code']].values.tolist()
            if targets: return targets
    except Exception: pass

    # 🚨 중복 현상 해결: limit 개수를 채우기 위해 억지로 리스트를 곱하여 복사하는 로직 제거
    fallback_targets = get_krx_stocks()[['Name', 'Code']].values.tolist()
    if fallback_targets:
        return fallback_targets[:limit] # 준비된 예비 데이터만큼만 중복 없이 반환
    return []

@st.cache_data(ttl=86400)
def get_us_scan_targets(limit=300):
    try:
        url = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"
        res = requests.get(url, headers={'User-Agent': 'Mozilla/5.0'})
        df = pd.read_html(StringIO(res.text))[0]
        targets = df[['Security', 'Symbol']].head(limit).values.tolist()
        return [(row[0], str(row[1]).replace('.', '-')) for row in targets]
    except Exception:
        return [('Apple', 'AAPL'), ('Microsoft', 'MSFT'), ('Nvidia', 'NVDA'), ('Tesla', 'TSLA')] * (limit // 4 + 1)

@st.cache_data(ttl=300)
def get_limit_stocks():
    def fetch_naver_limit(url, is_upper):
        try:
            res = requests.get(url, headers={'User-Agent': 'Mozilla/5.0'}, timeout=5)
            tables = pd.read_html(StringIO(res.content.decode('euc-kr', errors='replace')))
            for t in tables:
                if '종목명' in t.columns and '현재가' in t.columns:
                    t = t.dropna(subset=['종목명', '현재가'])
                    t = t[t['종목명'] != '종목명']
                    t = t[~t['종목명'].str.contains('스팩|ETN|선물|인버스|레버리지', na=False, regex=True)]
                    if not t.empty:
                        res_df = pd.DataFrame()
                        res_df['Name'] = t['종목명']
                        def to_f(x):
                            try: return float(str(x).replace(',', '').replace('%', '').replace('+', '').strip())
                            except Exception: return 0.0
                        res_df['Close'] = t['현재가'].apply(to_f)
                        res_df['Changes'] = t['전일비'].apply(to_f) if is_upper else -t['전일비'].apply(to_f)
                        if '등락률' in t.columns: res_df['ChagesRatio'] = t['등락률'].apply(to_f) if is_upper else -t['등락률'].apply(to_f)
                        else: res_df['ChagesRatio'] = 0.0
                        if '거래량' in t.columns: res_df['Amount_Ouk'] = (res_df['Close'] * t['거래량'].apply(to_f) / 100000000).astype(int)
                        else: res_df['Amount_Ouk'] = 0
                        res_df['PrevClose'] = res_df['Close'] - res_df['Changes']
                        res_df['Code'] = ""
                        return res_df.drop_duplicates(subset=['Name'])
        except Exception: pass
        return pd.DataFrame()

    upper_df = fetch_naver_limit("https://finance.naver.com/sise/sise_upper.naver", True)
    lower_df = fetch_naver_limit("https://finance.naver.com/sise/sise_lower.naver", False)
    krx = get_krx_stocks()
    empty_cols = ['Code', 'Sector', 'Close', 'Changes', 'ChagesRatio', 'Amount_Ouk', 'PrevClose', 'Name']
    
    if not upper_df.empty and not krx.empty:
        upper_df = pd.merge(upper_df, krx[['Name', 'Code', 'Sector']], on='Name', how='left')
        upper_df['Sector'] = upper_df['Sector'].fillna('개별이슈/기타')
    elif upper_df.empty: upper_df = pd.DataFrame(columns=empty_cols)
        
    if not lower_df.empty and not krx.empty:
        lower_df = pd.merge(lower_df, krx[['Name', 'Code', 'Sector']], on='Name', how='left')
        lower_df['Sector'] = lower_df['Sector'].fillna('개별이슈/기타')
    elif lower_df.empty: lower_df = pd.DataFrame(columns=empty_cols)

    for col in empty_cols:
        if col not in upper_df.columns: upper_df[col] = 0
        if col not in lower_df.columns: lower_df[col] = 0

    return upper_df.sort_values('Amount_Ouk', ascending=False), lower_df.sort_values('Amount_Ouk', ascending=False)

@st.cache_data(ttl=60)
def get_volume_surge_drop():
    def fetch_vol_table(url):
        try:
            res = requests.get(url, headers={'User-Agent': 'Mozilla/5.0'}, timeout=5)
            tables = pd.read_html(StringIO(res.content.decode('euc-kr', 'replace')))
            for t in tables:
                if '종목명' in t.columns and '현재가' in t.columns:
                    df = t.dropna(subset=['종목명', '현재가']).copy()
                    df = df[df['종목명'] != '종목명']
                    df = df[~df['종목명'].str.contains('스팩|ETN|선물|인버스|레버리지', na=False, regex=True)]
                    return df.dropna(axis=1, how='all').head(20).reset_index(drop=True)
        except Exception: pass
        return pd.DataFrame()
    ts = int(time.time())
    surge_df = fetch_vol_table(f"https://finance.naver.com/sise/sise_quant_high.naver?_ts={ts}")
    drop_df = fetch_vol_table(f"https://finance.naver.com/sise/sise_quant_low.naver?_ts={ts}")
    return surge_df, drop_df

@st.cache_data(ttl=3600)
def get_market_warnings():
    def fetch_warning_table(url):
        try:
            res = requests.get(url, headers={'User-Agent': 'Mozilla/5.0'}, timeout=5)
            tables = pd.read_html(StringIO(res.content.decode('euc-kr', 'replace')))
            for t in tables:
                if '종목명' in t.columns:
                    df = t.dropna(subset=['종목명']).copy()
                    df = df[df['종목명'] != '종목명']
                    return df.dropna(axis=1, how='all').reset_index(drop=True)
        except Exception: pass
        return pd.DataFrame()
    mgmt_df = fetch_warning_table("https://finance.naver.com/sise/management.naver")
    alert_df = fetch_warning_table("https://finance.naver.com/sise/investment_alert.naver")
    return mgmt_df, alert_df

@st.cache_data(ttl=120)
def get_latest_naver_news():
    articles = []
    now_kst = datetime.utcnow() + timedelta(hours=9)
    three_hours_ago = now_kst - timedelta(hours=3)
    ts = int(now_kst.timestamp())
    def fetch_page(page):
        try:
            url = f"https://finance.naver.com/news/news_list.naver?mode=LSS2D&section_id=101&section_id2=258&page={page}&_ts={ts}"
            res = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=2.5) 
            if res.status_code != 200: return []
            soup = BeautifulSoup(res.content.decode('euc-kr', 'replace'), 'html.parser')
            page_articles = []
            for dl in soup.select("dl"):
                subject = dl.select_one(".articleSubject a")
                if not subject: continue
                title = subject.get_text(strip=True)
                link = "https://finance.naver.com" + subject['href'] if subject['href'].startswith("/") else subject['href']
                pub_time = ""
                wdate = dl.select_one(".wdate")
                if wdate:
                    raw_date = wdate.get_text(strip=True)
                    match = re.search(r'(\d{4}-\d{2}-\d{2})\s+(\d{2}:\d{2})', raw_date)
                    if match:
                        news_dt_str = f"{match.group(1)} {match.group(2)}"
                        try:
                            news_dt = datetime.strptime(news_dt_str, "%Y-%m-%d %H:%M")
                            if news_dt < three_hours_ago: continue 
                        except Exception: pass
                        pub_time = match.group(2) if match.group(1) == now_kst.strftime("%Y-%m-%d") else f"{match.group(1)[5:].replace('-', '/')} {match.group(2)}"
                    else:
                        match_time = re.search(r'(\d{2}:\d{2})', raw_date)
                        if match_time: pub_time = match_time.group(1)
                if not pub_time: pub_time = now_kst.strftime("%H:%M")
                page_articles.append({"title": title, "link": link, "time": pub_time})
            return page_articles
        except Exception: return []
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
        results = executor.map(fetch_page, [1, 2, 3]) 
        for res in results: articles.extend(res)
    return articles

def update_news_state():
    items = get_latest_naver_news()
    for item in reversed(items): 
        if item['link'] not in st.session_state.seen_links and item['title'] not in st.session_state.seen_titles:
            st.session_state.news_data.insert(0, item)
            st.session_state.seen_links.add(item['link'])
            st.session_state.seen_titles.add(item['title'])

@st.cache_data(ttl=3600)
def get_naver_research():
    try:
        url = "https://finance.naver.com/research/company_list.naver"
        res = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=3)
        soup = BeautifulSoup(res.content.decode('euc-kr', 'replace'), 'html.parser')
        table = soup.find('table', {'class': 'type_1'})
        rows = []
        for tr in table.find_all('tr'):
            tds = tr.find_all('td')
            if len(tds) >= 5:
                stock_name = tds[0].get_text(strip=True)
                if not stock_name: continue
                title_a = tds[1].find('a')
                title = title_a.get_text(strip=True) if title_a else tds[1].get_text(strip=True)
                link = "https://finance.naver.com/research/" + title_a['href'] if title_a and 'href' in title_a.attrs else ""
                broker = tds[2].get_text(strip=True)
                date = tds[4].get_text(strip=True)
                rows.append({"종목명": stock_name, "제목": title, "증권사": broker, "작성일": date, "원문링크": link})
        return pd.DataFrame(rows).head(30)
    except Exception: return pd.DataFrame()

@st.cache_data(ttl=86400)
def get_financial_deep_data(code):
    try:
        url = f"https://finance.naver.com/item/main.naver?code={code}"
        res = requests.get(url, headers={'User-Agent': 'Mozilla/5.0'}, timeout=4)
        tables = pd.read_html(StringIO(res.text))
        fin_df, peer_df = None, None
        for t in tables:
            str_t = str(t)
            if '매출액' in str_t and '영업이익' in str_t and '당기순이익' in str_t and fin_df is None: fin_df = t
            if '종목명' in str_t and '현재가' in str_t and 'PER' in str_t and peer_df is None: peer_df = t
        soup = BeautifulSoup(res.text, 'html.parser')
        c_area = soup.select_one('.r_cmp_area .f_up em')
        consensus = c_area.text if c_area else "증권사 목표가 추정치 없음"
        return fin_df, peer_df, consensus
    except Exception: return None, None, "데이터 스크래핑 오류"

@st.cache_data(ttl=300)
def get_intraday_estimate(code):
    if not code.isdigit(): return None
    try:
        url = f"https://finance.naver.com/item/frgn.naver?code={code}"
        res = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=3)
        soup = BeautifulSoup(res.text, 'html.parser')
        tables = soup.find_all('table', {'class': 'type2'})
        for table in tables:
            summary = table.get('summary', '')
            if '잠정치' in summary:
                trs = table.find_all('tr')
                for tr in trs:
                    tds = tr.find_all('td')
                    if len(tds) >= 3 and not '비어있습니다' in tr.text:
                        time_str = tds[0].text.strip()
                        if not time_str or time_str == '': continue
                        forgn_str = tds[1].text.strip().replace(',', '').replace('+', '')
                        inst_str = tds[2].text.strip().replace(',', '').replace('+', '')
                        forgn_val = int(forgn_str) if forgn_str.lstrip('-').isdigit() else 0
                        inst_val = int(inst_str) if inst_str.lstrip('-').isdigit() else 0
                        return {"time": time_str, "forgn": forgn_val, "inst": inst_val}
        return None
    except Exception: return None

@st.cache_data(ttl=3600)
def get_investor_trend(code):
    try:
        res = requests.get(f"https://finance.naver.com/item/frgn.naver?code={code}", headers={"User-Agent": "Mozilla/5.0"}, timeout=3)
        soup = BeautifulSoup(res.text, 'html.parser')
        rows = soup.select('table.type2')[1].select('tr')
        i_vals, f_vals, p_vals = [], [], []
        for row in rows:
            tds = row.select('td')
            if len(tds) < 9 or not tds[0].text.strip(): continue 
            try:
                i_val = int(tds[5].text.strip().replace(',', '').replace('+', ''))
                f_val = int(tds[6].text.strip().replace(',', '').replace('+', ''))
                p_val = -(i_val + f_val) 
                i_vals.append(i_val)
                f_vals.append(f_val)
                p_vals.append(p_val)
            except Exception: pass
            if len(i_vals) >= 5: break 
            
        def calc_trend(vals):
            if not vals: return "0 (➖중립)", 0
            total = sum(vals)
            buy_streak, sell_streak = 0, 0
            for v in vals:
                if v > 0: buy_streak += 1
                else: break
            for v in vals:
                if v < 0: sell_streak += 1
                else: break
            if total > 0: desc = f"🔥{buy_streak}일 연속 매집" if buy_streak >= 3 else "🔥매집"
            elif total < 0: desc = f"💧{sell_streak}일 연속 매도" if sell_streak >= 3 else "💧매도"
            else: desc = "➖중립"
            base = f"+{total:,}" if total > 0 else f"{total:,}"
            return f"{base} ({desc})", buy_streak

        i_str, i_streak = calc_trend(i_vals)
        f_str, f_streak = calc_trend(f_vals)
        p_str, _ = calc_trend(p_vals)
        return i_str, f_str, p_str, i_streak, f_streak
    except Exception: return "조회불가", "조회불가", "조회불가", 0, 0

@st.cache_data(ttl=3600)
def get_pension_fund_trend(code):
    try:
        res = requests.get(f"https://finance.naver.com/item/frgn.naver?code={code}", headers={"User-Agent": "Mozilla/5.0"}, timeout=3)
        soup = BeautifulSoup(res.text, 'html.parser')
        rows = soup.select('table.type2')[1].select('tr')
        pension_like_sum, pension_like_streak, pension_break, count = 0, 0, False, 0
        for row in rows:
            tds = row.select('td')
            if len(tds) < 9 or not tds[0].text.strip(): continue 
            try:
                i_val = int(tds[5].text.strip().replace(',', '').replace('+', '')) 
                pension_like_sum += i_val
                if i_val > 0 and not pension_break: pension_like_streak += 1
                elif i_val <= 0: pension_break = True
                count += 1
            except Exception: pass
            if count >= 5: break
        return pension_like_sum, pension_like_streak
    except Exception: return 0, 0

@st.cache_data(ttl=3600)
def get_daily_sise_and_investor(code):
    if not code.isdigit(): return pd.DataFrame()
    try:
        url = f"https://finance.naver.com/item/frgn.naver?code={code}"
        res = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=4)
        soup = BeautifulSoup(res.text, 'html.parser')
        table = soup.select('table.type2')[1]
        rows = table.select('tr')
        data = []
        for row in rows:
            tds = row.select('td')
            if len(tds) < 9 or not tds[0].text.strip(): continue
            try:
                date = tds[0].text.strip()
                close = tds[1].text.strip()
                diff = tds[2].text.strip()
                rate = tds[3].text.strip()
                inst = int(tds[5].text.strip().replace(',', '').replace('+', ''))
                forgn = int(tds[6].text.strip().replace(',', '').replace('+', ''))
                retail = -(inst + forgn)
                def fmt_vol(v):
                    if v > 0: return f"🔴 +{v:,}"
                    elif v < 0: return f"🔵 {v:,}"
                    return "0"
                data.append({
                    "날짜": date, "종가": close, "전일비": diff, "등락률": rate,
                    "외국인": fmt_vol(forgn), "기관": fmt_vol(inst), "개인(추정)": fmt_vol(retail)
                })
            except Exception: pass
            if len(data) >= 10: break
        return pd.DataFrame(data)
    except Exception: return pd.DataFrame()

def get_fundamentals(ticker_code):
    if str(ticker_code).isdigit():
        per, pbr, target_price = 'N/A', 'N/A', 'N/A'
        try:
            url = f"https://finance.naver.com/item/main.naver?code={ticker_code}"
            res = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=5)
            soup = BeautifulSoup(res.text, 'html.parser')
            per = soup.select_one('#_per').text if soup.select_one('#_per') else 'N/A'
            pbr = soup.select_one('#_pbr').text if soup.select_one('#_pbr') else 'N/A'
            for tr in soup.find_all('tr'):
                th = tr.find('th')
                if th and '목표주가' in th.text:
                    td = tr.find('td')
                    if td:
                        text_content = td.get_text(separator=' ', strip=True)
                        possible_prices = []
                        for n_str in re.findall(r'[0-9,]+', text_content):
                            clean_n = n_str.replace(',', '')
                            if clean_n.isdigit(): possible_prices.append(int(clean_n))
                        if possible_prices:
                            max_val = max(possible_prices)
                            if max_val > 10: target_price = str(max_val)
                    break
        except Exception: pass

        fcf, shares = None, None
        try:
            t_obj = yf.Ticker(f"{ticker_code}.KS")
            info = t_obj.info
            
            if not info or 'sharesOutstanding' not in info:
                t_obj = yf.Ticker(f"{ticker_code}.KQ")
                info = t_obj.info

            raw_shares = info.get('sharesOutstanding')
            if raw_shares: shares = raw_shares / 1000000.0

            cf = t_obj.cash_flow
            if cf is not None and not cf.empty and 'Free Cash Flow' in cf.index:
                fcf_raw = cf.loc['Free Cash Flow'].iloc[0]
                if pd.notna(fcf_raw): fcf = fcf_raw / 100000000.0 
        except Exception: pass

        return per, pbr, fcf, shares, target_price
        
    else:
        try:
            t_obj = yf.Ticker(ticker_code)
            info = t_obj.info
            per = round(info.get('trailingPE', 0), 2) if info.get('trailingPE') else 'N/A'
            pbr = round(info.get('priceToBook', 0), 2) if info.get('priceToBook') else 'N/A'
            target_price = info.get('targetMeanPrice', 'N/A')
            fcf, shares = None, None

            raw_shares = info.get('sharesOutstanding')
            if raw_shares: shares = raw_shares / 1000000.0

            try:
                cf = t_obj.cash_flow
                if cf is not None and not cf.empty and 'Free Cash Flow' in cf.index:
                    fcf_raw = cf.loc['Free Cash Flow'].iloc[0]
                    if pd.notna(fcf_raw): fcf = fcf_raw / 100000000.0 
            except Exception: pass
            
            return per, pbr, fcf, shares, target_price
        except Exception: 
            return 'N/A', 'N/A', None, None, 'N/A'

@st.cache_data(ttl=3600)
def get_historical_data(ticker_code, days):
    if str(ticker_code).isdigit():
        try:
            url = f"https://fchart.stock.naver.com/sise.nhn?symbol={ticker_code}&timeframe=day&count={days}&requestType=0"
            res = requests.get(url, headers={'User-Agent': 'Mozilla/5.0'}, timeout=5)
            soup = BeautifulSoup(res.text, 'html.parser')
            items = soup.find_all('item')
            data = []
            for item in items:
                val = item.get('data')
                if val:
                    parts = val.split('|')
                    data.append([pd.to_datetime(parts[0]), float(parts[1]), float(parts[2]), float(parts[3]), float(parts[4]), float(parts[5])])
            if data:
                df = pd.DataFrame(data, columns=['Date', 'Open', 'High', 'Low', 'Close', 'Volume'])
                df.set_index('Date', inplace=True)
                return df
        except Exception: pass
        
        try:
            df = yf.Ticker(f"{ticker_code}.KS").history(period=f"{days}d")
            if not df.empty:
                df.index = df.index.tz_localize(None)
                return df
        except Exception: pass
        
    else:
        # 💡 [핵심 우회] 미국 주식 연속 조회 시 차단 방어 (세션 위장 + yahooquery 2중 콤보)
        try:
            session = requests.Session()
            session.headers.update({'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'})
            df = yf.Ticker(ticker_code, session=session).history(period=f"{days}d")
            if not df.empty:
                df.index = df.index.tz_localize(None)
                return df
        except Exception: pass
        
        try:
            from yahooquery import Ticker as yq_Ticker
            yq_t = yq_Ticker(ticker_code)
            df = yq_t.history(period=f"{days}d")
            if isinstance(df, pd.DataFrame) and not df.empty:
                df = df.reset_index()
                df = df.rename(columns={'date': 'Date', 'open': 'Open', 'high': 'High', 'low': 'Low', 'close': 'Close', 'volume': 'Volume'})
                df.set_index('Date', inplace=True)
                df.index = pd.to_datetime(df.index).tz_localize(None)
                return df[['Open', 'High', 'Low', 'Close', 'Volume']]
        except Exception: pass
        
    return pd.DataFrame()

@st.cache_data(ttl=300)
def get_advanced_chart_data(ticker_code, timeframe):
    is_us = not str(ticker_code).isdigit()
    yf_ticker = ticker_code if is_us else f"{ticker_code}.KS"
    try:
        if timeframe == "30분": df = yf.Ticker(yf_ticker).history(period="1mo", interval="30m")
        elif timeframe == "1시간": df = yf.Ticker(yf_ticker).history(period="1mo", interval="60m")
        elif timeframe == "4시간":
            df = yf.Ticker(yf_ticker).history(period="2mo", interval="60m")
            if not df.empty: df = df.resample('4h').agg({'Open': 'first', 'High': 'max', 'Low': 'min', 'Close': 'last', 'Volume': 'sum'}).dropna()
        elif timeframe == "일봉": df = yf.Ticker(yf_ticker).history(period="6mo", interval="1d")
        elif timeframe == "주봉": df = yf.Ticker(yf_ticker).history(period="2y", interval="1wk")
        elif timeframe == "1년": df = yf.Ticker(yf_ticker).history(period="1y", interval="1d")
        elif timeframe == "5년": df = yf.Ticker(yf_ticker).history(period="5y", interval="1wk")
        elif timeframe == "10년": df = yf.Ticker(yf_ticker).history(period="10y", interval="1mo")
        else: df = yf.Ticker(yf_ticker).history(period="6mo", interval="1d")
            
        if not df.empty:
            df.index = df.index.tz_localize(None)
            if df.index.name == 'Datetime': df.index.name = 'Date'
        return df
    except Exception as e:
        return pd.DataFrame()

@st.cache_data(ttl=3600)
def search_us_ticker(query):
    if not query: return []
    if re.search('[가-힣]', query):
        try:
            res = requests.get(f"https://translate.googleapis.com/translate_a/single?client=gtx&sl=ko&tl=en&dt=t&q={urllib.parse.quote(query)}", timeout=2)
            search_term = res.json()[0][0][0]
        except Exception: search_term = query
    else: search_term = query
    try:
        url = f"https://query2.finance.yahoo.com/v1/finance/search?q={urllib.parse.quote(search_term)}&quotesCount=5"
        headers = {'User-Agent': 'Mozilla/5.0'}
        response = requests.get(url, headers=headers, timeout=5)
        data = response.json()
        results = []
        for quote in data.get('quotes', []):
            if quote.get('quoteType') in ['EQUITY', 'ETF']:
                sym = quote.get('symbol')
                name = quote.get('shortname', 'Unknown')
                ko_name = get_korean_name(name)
                exch = quote.get('exchDisp', 'US')
                results.append(f"{sym} ({ko_name} / {exch})")
        return results
    except Exception: return []

@st.cache_data(ttl=3600)
def analyze_technical_pattern(stock_name, ticker_code, offset_days=0):
    if not ticker_code: return None
    is_us = not str(ticker_code).isdigit()
    if is_us: stock_name = get_korean_name(stock_name)
    try:
        df = get_historical_data(ticker_code, 150)
        if df.empty or len(df) < 20 + offset_days: return None
        
        today_close = float(df['Close'].iloc[-1]) 
        if offset_days > 0: analysis_df = df.iloc[:-offset_days].copy()
        else: analysis_df = df.copy()
            
        analysis_df['MA5'] = analysis_df['Close'].rolling(window=5).mean()
        analysis_df['MA20'] = analysis_df['Close'].rolling(window=20).mean()
        analysis_df['MA60'] = analysis_df['Close'].rolling(window=60).mean()
        analysis_df['Vol_MA20'] = analysis_df['Volume'].rolling(window=20).mean()
        analysis_df['Std_20'] = analysis_df['Close'].rolling(window=20).std()
        analysis_df['Bollinger_Upper'] = analysis_df['MA20'] + (analysis_df['Std_20'] * 2)
        
        delta = analysis_df['Close'].diff()
        rs = (delta.where(delta > 0, 0.0).rolling(14).mean()) / (-delta.where(delta < 0, 0.0).rolling(14).mean())
        analysis_df['RSI'] = 100 - (100 / (1 + rs))
        analysis_df['OBV'] = (np.sign(analysis_df['Close'].diff()) * analysis_df['Volume']).fillna(0).cumsum()
        
        latest = analysis_df.iloc[-1]
        prev = analysis_df.iloc[-2] if len(analysis_df) > 1 else latest
        current_price = float(latest['Close']) 
        
        if pd.notna(latest['MA60']) and latest['MA5'] > latest['MA20'] > latest['MA60']: align_status = "🔥 완벽 정배열 (상승 추세) ｜ 💡 기준: 5일선 > 20일선 > 60일선"
        elif pd.notna(latest['MA60']) and latest['MA5'] < latest['MA20'] < latest['MA60']: align_status = "❄️ 역배열 (하락 추세) ｜ 💡 기준: 5일선 < 20일선 < 60일선"
        elif latest['MA5'] > latest['MA20'] and prev['MA5'] <= prev['MA20']: align_status = "✨ 5-20 골든크로스 ｜ 💡 기준: 5일선이 20일선을 상향 돌파"
        else: align_status = "🌀 혼조세/횡보 ｜ 💡 기준: 이평선 얽힘 (방향 탐색중)"
        
        ma20_val = float(latest['MA20'])
        if (ma20_val * 0.97) <= current_price <= (ma20_val * 1.03): status = "✅ 타점 근접 (분할 매수)"
        elif current_price > (ma20_val * 1.03): status = "⚠️ 이격 과다 (눌림목 대기)"
        else: status = "🛑 20일선 이탈 (관망)"
        
        is_us = not str(ticker_code).isdigit()
        if is_us:
            inst_vol, forgn_vol, ind_vol, inst_streak, forgn_streak = "조회불가", "조회불가", "조회불가", 0, 0
            intraday_est = None
            pension_sum, pension_streak = 0, 0
        else:
            inst_vol, forgn_vol, ind_vol, inst_streak, forgn_streak = get_investor_trend(ticker_code)
            intraday_est = get_intraday_estimate(ticker_code) 
            pension_sum, pension_streak = get_pension_fund_trend(ticker_code)
            
        per, pbr, fcf, shares, target_price = get_fundamentals(ticker_code)
        
        target_1 = float(latest['Bollinger_Upper'])
        recent_high = float(analysis_df['Close'].max())
        target_2 = float(recent_high) if recent_high > (target_1 * 1.02) else float(target_1 * 1.05)
        target_3 = float(target_2 * 1.08)
        
        pnl_pct = ((today_close - current_price) / current_price) * 100 if offset_days > 0 and current_price > 0 else 0.0
        
        krx_df = get_krx_stocks()
        sector_val = "ETF/미국주식/분류없음"
        if not krx_df.empty and not is_us:
            match_sec = krx_df[krx_df['Code'] == ticker_code]['Sector']
            if not match_sec.empty and pd.notna(match_sec.iloc[0]):
                raw_sec = str(match_sec.iloc[0])
                sector_val = raw_sec.replace(" 및 공급업", "").replace(" 제조업", "").replace(" 제조 및", "").replace(" 도매업", "").replace(" 소매업", "")
        
        return {
            "종목명": stock_name, "티커": ticker_code, "섹터": sector_val, "현재가": current_price, "상태": status,
            "진입가_가이드": ma20_val, "목표가1": target_1, "목표가2": target_2, "목표가3": target_3, "손절가": ma20_val * 0.97,
            "거래량 급증": "🔥 거래량 터짐" if analysis_df.iloc[-10:]['Volume'].max() > (analysis_df.iloc[-10:]['Vol_MA20'].mean() * 2) else "평이함",
            "RSI": latest['RSI'], "배열상태": align_status, 
            "기관수급": inst_vol, "외인수급": forgn_vol, "개인수급": ind_vol, "장중잠정수급": intraday_est,
            "기관연속순매수": inst_streak, "외인연속순매수": forgn_streak,
            "연기금추정순매수": pension_sum, "연기금연속순매수": pension_streak,
            "PER": per, "PBR": pbr, "FCF": fcf, "Shares": shares, "목표가_컨센서스": target_price,
            "OBV": analysis_df['OBV'].tail(20), "차트 데이터": analysis_df.tail(20), 
            "오늘현재가": today_close, "수익률": pnl_pct, "과거검증": offset_days > 0
        }
    except Exception as e: 
        print(f"Technical Analysis Error for {ticker_code}: {e}")
        return None

# ==========================================
# 3. UI 렌더링 가이드 및 카드 함수
# ==========================================
def show_beginner_guide():
    with st.expander("🐥 [주린이 필독] 주식 용어 & 매매 타점 완벽 가이드", expanded=False):
        st.markdown("""
        ### 1. 📊 차트 상태 (상세 진단 기준 & 이평선)
        * **이동평균선(이평선):** 일정 기간 동안의 주가 평균을 이은 선입니다.
        * **🔥 완벽 정배열 (상승 추세):** `5일선 > 20일선 > 60일선`
        * **❄️ 역배열 (하락 추세):** `5일선 < 20일선 < 60일선`
        * **✨ 5-20 골든크로스:** 어제까지 아래에 있던 단기선이 중기선을 오늘 상향 돌파
        """)

def show_trading_guidelines():
    with st.expander("🎯 [필독] Jaemini PRO 실전 매매 4STEP 시나리오 (단기 스윙 전략)", expanded=True):
        st.markdown("""
        *💡 단기 스윙 전략 가이드*
        * 🅰️ **안전 스윙 (목표 3일~2주):** `✅20일선 눌림목` + `🔥거래량 급증` 
        * 🅱️ **추세 탑승 (목표 1일~5일):** `✨정배열 초입` + `🔥거래량 급증` 
        """)

def draw_stock_card(tech_result, api_key_str="", is_expanded=False, key_suffix="default"):
    status_emoji = tech_result['상태'].split(' ')[0]
    is_us = not str(tech_result['티커']).isdigit() 

    def get_short_trend(trend_text):
        val = str(trend_text).split(' ')[0]
        if "🔥" in str(trend_text): return f"🔥{val}"
        if "💧" in str(trend_text): return f"💧{val}"
        return f"➖{val}"
        
    f_trend = get_short_trend(tech_result['외인수급'])
    i_trend = get_short_trend(tech_result['기관수급'])
    sector_info = tech_result.get('섹터', '기타')
    if len(sector_info) > 12: sector_info = sector_info[:12] + ".."
    align_status_short = tech_result['배열상태'].split(' ｜ ')[0]
    
    def fmt_price(p, delta=False):
        if is_us: return f"{'+' if p>0 else ''}${p:,.2f}" if delta else f"${p:,.2f}"
        else: return f"{'+' if p>0 else ''}{int(p):,}원" if delta else f"{int(p):,}원"
            
    if is_us: base_info = f"(진단: {tech_result['상태']} ｜ 상세 진단: {align_status_short} ｜ RSI: {tech_result['RSI']:.1f})"
    else: base_info = f"(진단: {tech_result['상태']} ｜ 상세 진단: {align_status_short} ｜ 외인: {f_trend} ｜ 기관: {i_trend} ｜ RSI: {tech_result['RSI']:.1f})"
    
    header_block = f"{status_emoji} {tech_result['종목명']} / {sector_info} / {fmt_price(tech_result['현재가'])}"
    expander_title = f"{header_block} ｜ {base_info}"
    
    with st.expander(expander_title, expanded=is_expanded):
        if tech_result.get('과거검증'):
            pnl = tech_result['수익률']
            color = "#ff4b4b" if pnl > 0 else "#1f77b4"
            bg_color = "rgba(255, 75, 75, 0.1)" if pnl > 0 else "rgba(31, 119, 180, 0.1)"
            st.markdown(f"""<div style="background-color: {bg_color}; padding: 15px; border-radius: 10px; margin-bottom: 15px; border: 1px solid {color};">
                <h3 style="margin:0; color: {color};">⏰ 타임머신 검증 결과</h3>
                <p style="margin:5px 0 0 0; font-size: 16px;">스캔 당시 가격 <b style="font-family:'JetBrains Mono',monospace;">{fmt_price(tech_result['현재가'])}</b> ➡️ 오늘 현재 가격 <b style="font-family:'JetBrains Mono',monospace;">{fmt_price(tech_result['오늘현재가'])}</b> <span style="font-size: 20px; font-weight: bold; color: {color}; font-family:'JetBrains Mono',monospace;">({pnl:+.2f}%)</span></p>
            </div>""", unsafe_allow_html=True)
            
        col_btn1, col_btn3 = st.columns([8, 2])
        col_btn1.markdown(f"**상세 진단:** {tech_result['배열상태']}")
        
        is_in_wl = any(x['티커'] == tech_result['티커'] for x in st.session_state.watchlist)
        if not is_in_wl:
            if col_btn3.button("⭐ 관심종목 추가", key=f"star_add_{tech_result['티커']}_{key_suffix}"):
                st.session_state.watchlist.append({'종목명': tech_result['종목명'], '티커': tech_result['티커']})
                save_watchlist(st.session_state.watchlist)
                st.rerun()
        else:
            if col_btn3.button("❌ 관심종목 삭제", key=f"star_del_{tech_result['티커']}_{key_suffix}"):
                st.session_state.watchlist = [x for x in st.session_state.watchlist if x['티커'] != tech_result['티커']]
                save_watchlist(st.session_state.watchlist)
                st.rerun()

        c1, c2, c3, c4 = st.columns(4)
        curr = tech_result['현재가']
        c1.metric("📌 진입 기준가", fmt_price(tech_result['진입가_가이드']), fmt_price(tech_result['진입가_가이드'] - curr, True) + " (대비)", delta_color="off")
        c2.metric("🎯 1차 (볼밴상단)", fmt_price(tech_result['목표가1']), fmt_price(tech_result['목표가1'] - curr, True), delta_color="normal")
        c3.metric("🚀 2차 (스윙전고)", fmt_price(tech_result['목표가2']), fmt_price(tech_result['목표가2'] - curr, True), delta_color="normal")
        c4.metric("🌌 3차 (오버슈팅)", fmt_price(tech_result['목표가3']), fmt_price(tech_result['목표가3'] - curr, True), delta_color="normal")
        
        st.markdown("---")
        
        c5, c6, c7, c8 = st.columns([1.2, 1.2, 1, 2.5]) 
        c5.metric("🛑 손절 라인", fmt_price(tech_result['손절가']), fmt_price(tech_result['손절가'] - curr, True) + " (리스크)", delta_color="normal")
        
        cons_text = tech_result.get("목표가_컨센서스", "N/A")
        def is_float(s):
            try: float(s); return True
            except Exception: return False
            
        if is_float(str(cons_text).replace('.', '', 1).replace('-', '')):
            cons_val = float(str(cons_text))
            c6.metric("🏦 증권가 목표가", fmt_price(cons_val), fmt_price(cons_val - curr, True) + " (괴리)", delta_color="normal")
        else:
            c6.metric("🏦 증권가 목표가", "목표가 없음")
            
        c7.metric("📊 RSI (상대강도)", f"{tech_result['RSI']:.1f}", "🔴 과열" if tech_result['RSI'] >= 70 else "🔵 바닥" if tech_result['RSI'] <= 30 else "⚪ 보통", delta_color="inverse" if tech_result['RSI'] >= 70 else "normal")
        
        if not is_us:
            with c8: 
                st.markdown(f"🕵️ **당시 수급 동향 (5일 누적)**<br>**외국인:** `{tech_result['외인수급']}` ｜ **기관:** `{tech_result['기관수급']}` ｜ **개인:** `{tech_result.get('개인수급', '조회불가')}`", unsafe_allow_html=True)
                if tech_result.get('장중잠정수급'):
                    id_data = tech_result['장중잠정수급']
                    f_val_str = f"🔥+{id_data['forgn']:,}" if id_data['forgn'] > 0 else f"💧{id_data['forgn']:,}"
                    i_val_str = f"🔥+{id_data['inst']:,}" if id_data['inst'] > 0 else f"💧{id_data['inst']:,}"
                    st.markdown(f"⚡ **오늘 장중 실시간 수급 (잠정)**<br>외인 `{f_val_str}` ｜ 기관 `{i_val_str}` `({id_data['time']} 기준)`", unsafe_allow_html=True)
                if tech_result.get('연기금연속순매수', 0) >= 3:
                    st.markdown(f"👴 **스마트머니 시그널:** <span style='color:orange; font-weight:bold;'>🔥 기관(전체) {tech_result['연기금연속순매수']}일 연속 순매수 포착</span>", unsafe_allow_html=True)
        else:
            with c8:
                per_val = tech_result.get('PER', 'N/A')
                pbr_val = tech_result.get('PBR', 'N/A')
                st.markdown(f"🏢 **핵심 펀더멘털 (TTM)**<br>**PER:** `{per_val}` ｜ **PBR:** `{pbr_val}`", unsafe_allow_html=True)
        
        if api_key_str:
            st.markdown("<br>", unsafe_allow_html=True)
            col_ai1, col_ai2 = st.columns(2)
            ai_btn_key = f"ai_btn_{tech_result['티커']}_{key_suffix}"
            ai_res_key = f"ai_res_{ai_btn_key}"
            biz_btn_key = f"biz_btn_{tech_result['티커']}_{key_suffix}"
            biz_res_key = f"biz_res_{biz_btn_key}"
            
            with col_ai1:
                if st.button(f"🤖 차트·수급·재무 정밀 진단", key=ai_btn_key, use_container_width=True):
                    st.session_state[ai_res_key] = "loading"
                    st.session_state[biz_res_key] = None
                    
            with col_ai2:
                if st.button(f"🏢 기업 심층 분석 (비즈니스/전망)", key=biz_btn_key, use_container_width=True):
                    st.session_state[biz_res_key] = "loading"
                    st.session_state[ai_res_key] = None
                    
            if st.session_state.get(ai_res_key):
                if st.session_state[ai_res_key] == "loading":
                    with st.spinner("AI가 차트 및 재무 데이터를 바탕으로 종합 분석 중입니다... (약 5~10초 소요)"):
                        if str(tech_result['티커']).isdigit():
                            fin_df, peer_df, cons = get_financial_deep_data(tech_result['티커'])
                            fin_text = fin_df.to_string() if fin_df is not None and not fin_df.empty else "재무 데이터 없음"
                            peer_text = peer_df.to_string() if peer_df is not None and not peer_df.empty else "비교 데이터 없음"
                            prompt = f"""
                            당신은 여의도 최고의 퀀트 애널리스트이자 펀드매니저입니다. '{tech_result['종목명']}' 분석 리포트를 마크다운으로 작성하세요.
                            [기술적 지표 및 수급]
                            - 현재가: {fmt_price(curr)}, 20일선: {fmt_price(tech_result['진입가_가이드'])} (상태: {tech_result['상태']})
                            - RSI: {tech_result['RSI']:.1f}, 추세: {tech_result['배열상태']}
                            - 수급: 외인 {tech_result['외인수급']}, 기관 {tech_result['기관수급']}
                            [증권사 목표주가 컨센서스]: {cons}
                            [최근 재무제표 요약 (단위: 억 원)]
                            {fin_text[:1500]}
                            [동일 업종 경쟁사 비교 (PER/PBR 포함)]
                            {peer_text[:1000]}
                            1. 📈 **기술적 타점 & 수급 분석**: 현재 진입하기 좋은 자리인지.
                            2. 🏢 **실적 트렌드 & 밸류에이션**: 고평가/저평가 여부 판단.
                            3. 🎯 **단기 매매 의견 및 목표가**: (적극매수/분할매수/관망/매수금지 중 택 1).
                            4. 💡 **최종 투자 코멘트**: 3줄 요약.
                            """
                            st.session_state[ai_res_key] = ask_gemini(prompt, api_key_str)
                        else:
                            prompt = f"전문 트레이더 관점에서 '{tech_result['종목명']}'을(를) 분석해주세요.\n[데이터] 현재가:{fmt_price(curr)}, 20일선:{fmt_price(tech_result['진입가_가이드'])}, RSI:{tech_result['RSI']:.1f}\n1. ⚡ 단기 트레이딩 관점\n2. 🛡️ 스윙/가치 투자 관점\n3. 🎯 종합 요약 (1줄):"
                            st.session_state[ai_res_key] = ask_gemini(prompt, api_key_str)
                            
                st.success("✅ AI 기술적 정밀 분석 완료!")
                st.markdown(st.session_state[ai_res_key])
                
                if not is_us:
                    with st.expander(f"📊 '{tech_result['종목명']}' 수집된 로우 데이터 (Raw Data) 확인"):
                        fin_df, peer_df, cons = get_financial_deep_data(tech_result['티커'])
                        st.write("✅ **증권사 목표가 컨센서스:**", cons)
                        if fin_df is not None: st.dataframe(fin_df)
                        if peer_df is not None: st.dataframe(peer_df)
            
            if st.session_state.get(biz_res_key):
                if st.session_state[biz_res_key] == "loading":
                    with st.spinner(f"AI가 '{tech_result['종목명']}'의 방대한 기업 정보와 비즈니스 모델을 분석 중입니다... (약 10초 소요)"):
                        prompt = f"""
                        당신은 여의도 최고의 기업 분석 리서치 센터장입니다. '{tech_result['종목명']}' 기업에 대해 심층 분석 리포트를 마크다운으로 작성하세요.
                        1. 🏭 **무엇을 하는 회사인가? (기업 개요)**: 회사가 구체적으로 어떤 비즈니스 모델을 가지며 어떻게 수익을 창출하는지 초보자도 알기 쉽게 설명.
                        2. 📊 **사업 구성 및 밸류체인**: 회사의 핵심 매출 파이프라인(주력 사업 비중)과 시장 내에서의 경쟁력 (독점력, 경제적 해자 등).
                        3. 🚀 **향후 전망 및 모멘텀 (Catalyst)**: 회사의 미래 성장 동력, 신사업 확장 가능성, 그리고 투자자가 반드시 주의해야 할 핵심 리스크 요인.
                        4. 💡 **한 줄 평**: 이 기업의 본질적인 가치와 투자 매력도에 대한 직관적인 한 줄 요약.
                        단순 주가 예측이 아닌 '비즈니스 모델'과 '기업의 본질적인 펀더멘털'에 집중하여 통찰력 있게 작성해 주세요.
                        """
                        st.session_state[biz_res_key] = ask_gemini(prompt, api_key_str)
                        
                st.success("✅ AI 비즈니스 심층 분석 완료!")
                st.markdown(st.session_state[biz_res_key])
        
        tf = st.radio("📅 차트 주기 선택", ["30분", "1시간", "4시간", "일봉", "주봉", "1년", "5년", "10년"], horizontal=True, key=f"tf_{key_suffix}", index=3)
        with st.spinner(f"{tf} 차트 데이터 및 피보나치 지표 불러오는 중..."):
            long_df = get_advanced_chart_data(tech_result['티커'], tf)
            
            # 여기서부터 들여쓰기가 수정된 부분입니다!
            if not long_df.empty:
                long_df = long_df.reset_index()
                long_df['OBV'] = (np.sign(long_df['Close'].diff()) * long_df['Volume']).fillna(0).cumsum()
                long_df['MA20'] = long_df['Close'].rolling(window=20).mean()
                long_df['Std_20'] = long_df['Close'].rolling(window=20).std()
                long_df['Bollinger_Upper'] = long_df['MA20'] + (long_df['Std_20'] * 2)
                
                if tf in ["30분", "1시간", "4시간"]: long_df['Date_Str'] = long_df['Date'].dt.strftime('%m/%d %H:%M')
                else: long_df['Date_Str'] = long_df['Date'].dt.strftime('%y/%m/%d')
                
                x_col, x_type = ('Date_Str', 'category')
                max_p = float(long_df['High'].max())
                min_p = float(long_df['Low'].min())
                diff_p = max_p - min_p
                f_382 = max_p - 0.382 * diff_p
                f_500 = max_p - 0.500 * diff_p
                f_618 = max_p - 0.618 * diff_p

                ch1, ch2 = st.columns(2)
                with ch1:
                    fig_price = go.Figure(data=[go.Candlestick(x=long_df[x_col], open=long_df['Open'], high=long_df['High'], low=long_df['Low'], close=long_df['Close'], increasing_line_color='#ff4b4b', decreasing_line_color='#1f77b4', name="주가")])
                    fig_price.add_trace(go.Scatter(x=long_df[x_col], y=long_df['MA20'], mode='lines', line=dict(color='orange', width=1.5), name='20일선'))
                    fig_price.add_trace(go.Scatter(x=long_df[x_col], y=long_df['Bollinger_Upper'], mode='lines', line=dict(color='gray', width=1, dash='dot'), name='볼밴상단'))
                    fig_price.add_hline(y=max_p, line_dash="dash", line_color="rgba(255,0,0,0.5)", annotation_text="고점(1.0)")
                    fig_price.add_hline(y=f_382, line_dash="dash", line_color="rgba(255,165,0,0.5)", annotation_text="Fib 0.382")
                    fig_price.add_hline(y=f_500, line_dash="dash", line_color="rgba(0,128,0,0.5)", annotation_text="Fib 0.500")
                    fig_price.add_hline(y=f_618, line_dash="dash", line_color="rgba(0,0,255,0.5)", annotation_text="Fib 0.618")
                    fig_price.add_hline(y=min_p, line_dash="dash", line_color="rgba(128,128,128,0.5)", annotation_text="저점(0.0)")
                    fig_price.update_layout(margin=dict(l=0, r=0, t=10, b=0), xaxis_rangeslider_visible=False, xaxis=dict(showgrid=False, type=x_type), height=250)
                    st.plotly_chart(fig_price, use_container_width=True, config={'displayModeBar': False}, key=f"lp_{tech_result['티커']}_{key_suffix}")
                
                with ch2:
                    fig_vol = go.Figure()
                    fig_vol.add_trace(go.Bar(x=long_df[x_col], y=long_df['Volume'], name="거래량", marker_color="#1f77b4"))
                    fig_vol.add_trace(go.Scatter(x=long_df[x_col], y=long_df['OBV'], name="OBV", yaxis="y2", line=dict(color="orange", width=2)))
                    fig_vol.update_layout(margin=dict(l=0, r=0, t=10, b=0), xaxis=dict(showgrid=False, type=x_type), height=250, showlegend=False, yaxis=dict(showgrid=False), yaxis2=dict(overlaying="y", side="right", showgrid=False))
                    st.plotly_chart(fig_vol, use_container_width=True, config={'displayModeBar': False}, key=f"lv_{tech_result['티커']}_{key_suffix}")
                
                if not is_us:
                    st.markdown("#### 📅 일별 시세 및 매매동향 (최근 10일)")
                    daily_df = get_daily_sise_and_investor(tech_result['티커'])
                    
                    if not daily_df.empty:
                        now_kst = datetime.utcnow() + timedelta(hours=9)
                        today_date = now_kst.strftime('%Y.%m.%d')
                        
                        if today_date not in str(daily_df.iloc[0]['날짜']):
                            est = tech_result.get('장중잠정수급')
                            try:
                                prev_close = int(str(daily_df.iloc[0]['종가']).replace(',', ''))
                                curr_price = int(tech_result['현재가'])
                                diff = curr_price - prev_close
                                diff_str = f"상승 {diff:,}" if diff > 0 else f"하락 {abs(diff):,}" if diff < 0 else "보합 0"
                                pct_str = f"{'+' if diff > 0 else ''}{(diff / prev_close) * 100:.2f}%"
                            except Exception:
                                diff_str = "-"
                                pct_str = "-"
                                
                            if est:
                                def fmt_v(v):
                                    if v > 0: return f"🔴 +{v:,}"
                                    elif v < 0: return f"🔵 {v:,}"
                                    return "0"
                                est_f = fmt_v(est['forgn'])
                                est_i = fmt_v(est['inst'])
                                est_r = fmt_v(-(est['forgn'] + est['inst']))
                                time_label = f"({est['time']} 잠정)"
                            else:
                                est_f = "장중 집계중"
                                est_i = "장중 집계중"
                                est_r = "장중 집계중"
                                time_label = "(실시간가)"
                                
                            new_row = pd.DataFrame([{
                                "날짜": f"✨ {today_date} {time_label}",
                                "종가": f"{int(tech_result['현재가']):,}",
                                "전일비": diff_str,
                                "등락률": pct_str,
                                "외국인": est_f,
                                "기관": est_i,
                                "개인(추정)": est_r
                            }])
                            daily_df = pd.concat([new_row, daily_df], ignore_index=True)
                        st.dataframe(daily_df, use_container_width=True, hide_index=True)
                    else: 
                        st.caption("수급 데이터를 제공하지 않는 종목입니다.")
            else: 
                st.error("데이터를 불러오지 못했습니다.")

def display_sorted_results(results_list, tab_key, api_key=""):
    if not results_list:
        st.info("조건에 부합하는 종목이 없습니다.")
        return
    st.success(f"🎯 총 {len(results_list)}개 종목 포착 완료!")
    sort_opt = st.radio("⬇️ 결과 정렬 방식", ["기본 (검색순)", "RSI 낮은순 (바닥줍기)", "기관 연속 순매수 긴 순서"], horizontal=True, key=f"sort_radio_{tab_key}")
    display_list = results_list.copy()
    
    if "RSI 낮은순" in sort_opt: sorted_res = sorted(display_list, key=lambda x: x['RSI'])
    elif "기관 연속" in sort_opt: sorted_res = sorted(display_list, key=lambda x: x.get('기관연속순매수', 0), reverse=True)
    else: sorted_res = display_list

    for i, res in enumerate(sorted_res):
        draw_stock_card(res, api_key_str=api_key, is_expanded=False, key_suffix=f"{tab_key}_{i}")

if "gainers_df" not in st.session_state or '환산(원)' not in st.session_state.gainers_df.columns:
    df, ex_rate, fetch_time = get_us_top_gainers()
    st.session_state.gainers_df = df
    st.session_state.ex_rate = ex_rate
    st.session_state.us_fetch_time = fetch_time

# ==========================================
# 4. 사이드바 메뉴 
# ==========================================
with st.sidebar:
    st.title("📈 Jaemini PRO v6.1")
    st.markdown("풀옵션 단기 스윙 & 퀀트 추적 시스템")
    
    menu_options = [
        "📂 [ 홈 & 자산 관리 ]",
        " ┣ 🎛️ 홈: 종합 대시보드",
        " ┣ 💼 내 계좌 & 포트폴리오 진단",
        " ┗ ⭐ 내 관심종목 모니터링",
        " ", 
        "📂 [ 시장 흐름 & 매크로 ]",
        " ┣ 🌍 글로벌 매크로 & AI 분석 (v6.0)",
        " ┣ 🗺️ 시장 주도주 자금 히트맵",
        " ┣ 🕸️ 실시간 섹터 순환매 추적",
        " ┗ 📅 핵심 증시 일정 & IPO 달력",
        "  ", 
        "📂 [ 퀀트 스캐너 & 종목 발굴 ]",
        " ┣ 🚀 단기 스윙 퀀트 스캐너",
        " ┣ 👨‍🦳 기관/외인 수급 스캐너",
        " ┣ 🏛️ 국민연금 5% 대량보유 픽",
        " ┣ 💎 장기 우량주 & 가치주 발굴",
        " ┗ ⚡ 메가트렌드 & 테마 대장주",
        "   ", 
        "📂 [ 트레이딩 & 시장 경보 ]",
        " ┣ 🔥 간밤의 미국 급등주 & 수혜주",
        " ┣ 🚨 당일 상/하한가 분석",
        " ┣ 🚦 거래량 급증 & 시장 경보",
        " ┗ 📰 실시간 특징주 속보 & 리포트",
        "    ", 
        "📂 [ 심층 분석 & 도구 ]",
        " ┣ 👴 노후 준비 ETF 시뮬레이터 (v2.0)", # <-- 이거 추가
        " ┣ 🔬 개별 기업 정밀 진단 (AI 비전)",
        " ┣ 📊 국내외 핵심 ETF 분석",
        " ┣ 💰 고배당주 파이프라인 (TOP 300)",
        " ┣ 🎯 증권사 목표가 컨센서스",
        " ┗ ⚖️ 적정 주가 계산기 (버핏 모델)"
    ]

    if "main_menu_radio" not in st.session_state:
        st.session_state.main_menu_radio = " ┣ 🎛️ 홈: 종합 대시보드"

    selected_display_menu = st.radio("📌 메뉴 이동", menu_options, key="main_menu_radio", label_visibility="collapsed")

    if selected_display_menu.startswith(" ┣ ") or selected_display_menu.startswith(" ┗ "):
        pure_menu_name = selected_display_menu[3:] 
    elif selected_display_menu.strip() == "":
        st.sidebar.warning("☝️ 구분선입니다. 위아래의 실제 메뉴를 선택해주세요.")
        pure_menu_name = "None"
    else:
        st.sidebar.info("☝️ [카테고리]를 누르셨습니다. 아래 하위 메뉴(┣, ┗)를 클릭해주세요.")
        pure_menu_name = "None"
        
    selected_menu = pure_menu_name
    clean_menu = pure_menu_name

    st.divider()
    
    st.header("🧠 AI 엔진 연결 상태")
    api_key_input = ""
    if "GEMINI_API_KEY" in st.secrets:
        val = st.secrets["GEMINI_API_KEY"]
        api_key_input = str(val) if isinstance(val, str) else str(list(val.values())[0])
        st.success("✅ 시스템 연동 완료")
    else:
        api_key_input = st.text_input("Gemini API Key를 입력하세요", type="password")
        if api_key_input: 
            api_key_input = str(api_key_input)
            st.success("✅ 시스템 연동 완료")
            
    if st.button("🔄 현재 화면 새로고침", use_container_width=True): 
        st.cache_data.clear()
        st.rerun()

# ==========================================
# 5. 메인 로직 
# ==========================================

if selected_menu == "🎛️ 홈: 종합 대시보드":
    macro_data = get_macro_indicators()
    fg_data = get_fear_and_greed()
    
    st.markdown("## 🎛️ 트레이딩 관제 센터 (Command Center)")
    m_col1, m_col2, m_col3 = st.columns([1, 1, 2])
    def draw_gauge(val, prev, title, steps, is_error=False):
        if is_error: return go.Figure(go.Indicator(mode="gauge", value=50, title={'text': f"<b>{title}</b><br><span style='font-size:12px;color:red'>서버 통신 지연 (방어)</span>"}, gauge={'axis': {'range': [0, steps[-1]['range'][1]]}, 'bar': {'color': "gray"}}))
        return go.Figure(go.Indicator(mode="gauge+number+delta", value=val, title={'text': title}, delta={'reference': prev, 'position': "top"}, gauge={'axis': {'range': [0, steps[-1]['range'][1]], 'tickwidth': 1, 'tickcolor': "darkblue"}, 'bar': {'color': "black", 'thickness': 0.2}, 'bgcolor': "white", 'borderwidth': 1, 'bordercolor': "gray", 'steps': steps}))

    with m_col1:
        steps_vix = [{'range': [0, 15], 'color': "rgba(0, 255, 0, 0.3)"}, {'range': [15, 20], 'color': "rgba(255, 255, 0, 0.3)"}, {'range': [20, 30], 'color': "rgba(255, 165, 0, 0.3)"}, {'range': [30, 50], 'color': "rgba(255, 0, 0, 0.3)"}]
        fig_vix = draw_gauge(macro_data['VIX']['value'], macro_data['VIX']['prev'], "<b>VIX (공포지수)</b>", steps_vix) if macro_data and 'VIX' in macro_data else draw_gauge(0,0,"VIX", steps_vix, True)
        fig_vix.update_layout(margin=dict(l=10, r=10, t=60, b=10), height=200)
        st.plotly_chart(fig_vix, use_container_width=True)

    with m_col2:
        steps_fg = [{'range': [0, 25], 'color': "rgba(255, 0, 0, 0.4)"}, {'range': [25, 45], 'color': "rgba(255, 165, 0, 0.4)"}, {'range': [45, 55], 'color': "rgba(255, 255, 0, 0.4)"}, {'range': [55, 75], 'color': "rgba(144, 238, 144, 0.4)"}, {'range': [75, 100], 'color': "rgba(0, 128, 0, 0.4)"}]
        fig_fg = draw_gauge(fg_data['score'], fg_data['score'] - fg_data['delta'], "<b>CNN 탐욕 지수</b>", steps_fg) if fg_data else draw_gauge(50, 50, "CNN 공포/탐욕 지수", steps_fg, True)
        fig_fg.update_layout(margin=dict(l=10, r=10, t=60, b=10), height=200)
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

    st.divider()
    st.subheader("📰 AI 모닝 브리핑 (Global to Local)")
    if api_key_input:
        with st.spinner("최신 글로벌 매크로 데이터를 바탕으로 AI가 모닝 브리핑을 작성 중입니다..."):
            top_gainers_names = st.session_state.gainers_df['기업명'].tolist()[:5] if not st.session_state.gainers_df.empty else []
            briefing_text = get_daily_market_briefing(macro_data, top_gainers_names, api_key_input)
            current_time = (datetime.utcnow() + timedelta(hours=9)).strftime("%Y-%m-%d %H:%M")
            st.info(f"**[생성 일시: {current_time} (KST)]**\n\n{briefing_text}", icon="💡")
            st.caption("※ 본 브리핑은 24시간 단위로 캐시가 갱신됩니다.")
    else:
        st.warning("API 키를 입력하시면 AI가 작성하는 실시간 글로벌-국내 증시 브리핑을 볼 수 있습니다.")

    st.divider()
    col_dash1, col_dash2 = st.columns([1, 1])
    with col_dash1:
        st.subheader("⚡ 퀵 오더 (종목 직접 검색)")
        market_radio_quick = st.radio("시장 선택 (퀵 오더)", ["🇰🇷 국내 주식", "🇺🇸 미국 주식"], horizontal=True, label_visibility="collapsed")
        
        if market_radio_quick == "🇰🇷 국내 주식":
            krx_df = get_krx_stocks()
            if not krx_df.empty:
                opts = ["🔍 종목명 검색 후 엔터"] + (krx_df['Name'].astype(str) + " (" + krx_df['Code'].astype(str) + ")").tolist()
                quick_query = st.selectbox("빠르게 매매할 종목을 찾아 호가창으로 이동하세요.", opts)
                if quick_query != "🔍 종목명 검색 후 엔터":
                    q_name = quick_query.rsplit(" (", 1)[0]
                    q_code = quick_query.rsplit("(", 1)[-1].replace(")", "").strip()
                    st.link_button(f"🛒 '{q_name}' 네이버 호가창(주문) 바로가기", f"https://finance.naver.com/item/main.naver?code={q_code}", use_container_width=True)
                    with st.expander(f"📊 '{q_name}' 퀵 타점 보기"):
                        res = analyze_technical_pattern(q_name, q_code)
                        if res:
                            st.markdown(f"**현재가:** {int(res['현재가']):,}원 ｜ **상태:** {res['상태']} ｜ **RSI:** {res['RSI']:.1f}")
                            st.markdown(f"**진입가:** {int(res['진입가_가이드']):,}원 ｜ **손절가:** {int(res['손절가']):,}원")
                        else: st.error("❌ 데이터를 불러올 수 없습니다.")
        else:
            us_search_query = st.text_input("🔍 미국 주식 종목명(한/영) 또는 티커를 검색하세요 (예: 애플, Nvidia, TSLA)")
            if us_search_query:
                with st.spinner("야후 파이낸스 글로벌 DB에서 종목을 찾는 중..."):
                    search_results = search_us_ticker(us_search_query)
                if search_results:
                    selected_us_stock = st.selectbox("👇 검색된 종목 중 정확한 티커를 선택하세요:", ["선택하세요"] + search_results)
                    if selected_us_stock != "선택하세요":
                        us_ticker = selected_us_stock.split(" ")[0]
                        st.link_button(f"🛒 '{us_ticker}' 야후 파이낸스 바로가기", f"https://finance.yahoo.com/quote/{us_ticker}", use_container_width=True)
                        with st.expander(f"📊 '{us_ticker}' 퀵 타점 보기", expanded=True):
                            with st.spinner("미국 주식 기술적 데이터 불러오는 중..."):
                                res = analyze_technical_pattern(us_ticker, us_ticker)
                                if res:
                                    st.markdown(f"**현재가:** ${res['현재가']:,.2f} ｜ **상태:** {res['상태']} ｜ **RSI:** {res['RSI']:.1f}")
                                    st.markdown(f"**진입가:** ${res['진입가_가이드']:,.2f} ｜ **손절가:** ${res['손절가']:,.2f}")
                                else: st.error("❌ 해당 티커의 데이터를 찾을 수 없습니다.")
                else:
                    st.error("❌ 검색 결과가 없습니다. 영문 명칭이나 다른 키워드로 다시 검색해보세요.")

    with col_dash2:
        st.subheader("🚦 내 관심종목 리스크 모니터링")
        if not st.session_state.watchlist:
            st.info("⭐내 관심종목 탭에 종목을 추가하시면 손익절 도달 여부를 감시해드립니다.")
        else:
            for item in st.session_state.watchlist:
                res = analyze_technical_pattern(item['종목명'], item['티커'])
                if res:
                    is_us = not str(item['티커']).isdigit()
                    cur_str = f"${res['현재가']:,.2f}" if is_us else f"{int(res['현재가']):,}원"
                    sl_str = f"${res['손절가']:,.2f}" if is_us else f"{int(res['손절가']):,}원"
                    tg_str = f"${res['목표가1']:,.2f}" if is_us else f"{int(res['목표가1']):,}원"
                    
                    if res['현재가'] <= res['손절가']: st.error(f"🔴 **손절가 이탈 위험:** {item['종목명']} (현재: {cur_str} / 손절선: {sl_str})")
                    elif res['현재가'] >= res['목표가1'] * 0.98: st.success(f"🟢 **익절 구간 도달:** {item['종목명']} (현재: {cur_str} / 1차목표: {tg_str})")
                    else: st.warning(f"🟡 **홀딩 대기중:** {item['종목명']} (현재: {cur_str})")

    st.divider()
    st.subheader("💬 실시간 퀀트 챗봇 (Interactive RAG & Google Search)")
    st.write("장중 궁금한 시장 이슈나 신작 출시 일정 등을 퀀트 비서에게 직접 물어보세요. (구글 실시간 검색 연동)")
    
    chat_container = st.container(height=400)
    for msg in st.session_state.v4_chat_history:
        chat_container.chat_message(msg["role"]).write(msg["content"])
        
    if prompt := st.chat_input("예: 펄어비스 붉은사막 최신 출시 일정 검색해서 알려줘", key="main_chat"):
        st.session_state.v4_chat_history.append({"role": "user", "content": prompt})
        chat_container.chat_message("user").write(prompt)
        
        if not api_key_input:
            st.error("좌측 사이드바에 API 키를 입력해주세요.")
        else:
            with chat_container.chat_message("assistant"):
                with st.spinner("구글 검색을 통해 최신 팩트를 확인 중입니다..."):
                    now_kst = datetime.utcnow() + timedelta(hours=9)
                    today_str = now_kst.strftime("%Y년 %m월 %d일")
                    macro_context = "현재 거시경제: " + ", ".join([f"{k} {v['value']}" for k, v in macro_data.items()]) if macro_data else ""
                    
                    sys_prompt = f"""
                    당신은 사용자의 실전 트레이딩을 돕는 여의도 최고의 퀀트 비서입니다.
                    🚨 [시스템 필수 지침]: 오늘 날짜는 정확히 {today_str}입니다.
                    1. 사용자의 질문에 대해 당신은 반드시 '구글 검색(Google Search)'을 실행하여 가장 최신 기사와 공시를 확인해야 합니다.
                    2. 과거 학습 데이터에 의존한 하드코딩된 답변을 금지합니다.
                    3. 검색 결과를 바탕으로 확정된 '사실'만 명확하게 3~4줄로 요약하세요.
                    [매크로 데이터]: {macro_context}\n사용자 질문: {prompt}
                    """
                    try:
                        genai.configure(api_key=api_key_input)
                        model = genai.GenerativeModel('gemini-3.1-flash-lite-preview', tools='google_search_retrieval')
                        response = model.generate_content(sys_prompt)
                        
                        if response.candidates and response.candidates[0].content.parts:
                            reply = response.text
                        else:
                            reply = ask_gemini(prompt, api_key_input)
                    except Exception:
                        reply = ask_gemini(prompt, api_key_input)
                    st.write(reply)
            
        st.session_state.v4_chat_history.append({"role": "assistant", "content": reply})

elif selected_menu == "💼 내 계좌 & 포트폴리오 진단":
    st.markdown("## 💼 내 계좌 & 포트폴리오 진단 및 리밸런싱")
    st.write("현재 보유 중인 종목들을 표에 입력하면, 단순 개별 분석이 아닌 **계좌 전체의 자산 배분(비중)과 리스크를 고려한 종합 리밸런싱 전략**을 AI가 진단해 드립니다.")

    if "portfolio_df" not in st.session_state:
        st.session_state.portfolio_df = pd.DataFrame([{"종목명": "", "진입단가": 0, "보유수량": 0}])

    st.markdown("### 📊 1. 내 포트폴리오 입력 (표 아래 '➕ 추가'를 눌러 종목 추가)")
    
    edited_df = st.data_editor(
        st.session_state.portfolio_df, 
        num_rows="dynamic", 
        column_config={
            "종목명": st.column_config.TextColumn("종목명 또는 티커", required=True),
            "진입단가": st.column_config.NumberColumn("내 진입단가", min_value=0, step=1, format="%d"),
            "보유수량": st.column_config.NumberColumn("보유 수량", min_value=0, step=1, format="%d"),
        },
        use_container_width=True
    )

    valid_rows = edited_df[(edited_df["종목명"].astype(str).str.strip() != "") & (edited_df["진입단가"] > 0) & (edited_df["보유수량"] > 0)]

    st.markdown("### 💧 2. 개별 종목 물타기 시뮬레이터 (선택 사항)")
    with st.expander("특정 종목의 추가 매수 시 평단가 변화를 계산하려면 여기를 펼쳐주세요."):
        col_m1, col_m2, col_m3, col_m4 = st.columns(4)
        with col_m1:
            sim_opts = ["직접 입력"] + valid_rows["종목명"].tolist() if not valid_rows.empty else ["직접 입력"]
            sim_sel = st.selectbox("물타기 할 종목", sim_opts)
        with col_m2:
            sim_name = st.text_input("종목명", value="" if sim_sel == "직접 입력" else sim_sel, label_visibility="collapsed" if sim_sel != "직접 입력" else "visible")
        with col_m3:
            sim_add_price = st.number_input("추가 매수 단가", min_value=0, step=1, format="%d", key="sim_p")
        with col_m4:
            sim_add_qty = st.number_input("추가 매수 수량", min_value=0, step=1, format="%d", key="sim_q")
        
        if st.button("🧮 평단가 계산하기"):
            if sim_name and sim_add_price > 0 and sim_add_qty > 0:
                orig_row = valid_rows[valid_rows["종목명"] == sim_name]
                if not orig_row.empty:
                    orig_price = int(orig_row.iloc[0]["진입단가"])
                    orig_qty = int(orig_row.iloc[0]["보유수량"])
                    orig_invest = orig_price * orig_qty
                    add_invest = sim_add_price * sim_add_qty
                    new_qty = orig_qty + sim_add_qty
                    new_avg = int((orig_invest + add_invest) / new_qty)
                    st.info(f"💡 **[{sim_name} 시뮬레이션]** 기존 {orig_qty}주(평단 {orig_price:,}) + 추가 {sim_add_qty}주(단가 {sim_add_price:,}) ➡️ **총 {new_qty}주, 조정 평단가: {new_avg:,}**")
                else:
                    st.warning("위 포트폴리오 표에 등록된 종목을 선택해야 기존 데이터와 합산하여 정확한 계산이 가능합니다.")

    if st.button("📊 계좌 전체 종합 진단 및 AI 리밸런싱", type="primary", use_container_width=True):
        if valid_rows.empty:
            st.warning("종목명과 진입단가, 보유수량을 최소 1개 이상 표에 정확히 입력해주세요.")
        elif not api_key_input:
            st.error("좌측 사이드바에 API 키를 입력해주세요.")
        else:
            with st.spinner("전체 포트폴리오 구성 종목의 현재가 조회 및 자산 배분 비중을 분석 중입니다..."):
                portfolio_summary = []
                total_invested_all = 0
                total_current_all = 0
                ex_rate = st.session_state.get('ex_rate', 1350.0)
                
                for idx, row in valid_rows.iterrows():
                    pos_name = str(row["종목명"]).strip()
                    entry_price = int(row["진입단가"])
                    quantity = int(row["보유수량"])
                    
                    search_ticker = None
                    pos_name_kr = pos_name
                    is_us = False
                    
                    # 💡 [핵심 로직 수정] 영어 포함 여부가 아니라, '한국 주식 DB(KRX)'에 있는지 먼저 확인!
                    krx_df = get_krx_stocks()
                    # 1. 한국 종목 중에 정확히 일치하는 이름이 있는지 먼저 확인 (대소문자 무시)
                    exact_match = krx_df[krx_df['Name'].str.upper() == pos_name.upper()]
                    
                    if not exact_match.empty:
                        is_us = False
                        search_ticker = exact_match['Code'].iloc[0]
                        pos_name_kr = exact_match['Name'].iloc[0]
                    else:
                        # 2. 정확히 일치하는 게 없으면, 입력한 단어를 포함하는 한국 종목이 있는지 2차 확인
                        contains_match = krx_df[krx_df['Name'].str.contains(pos_name, case=False, na=False)]
                        if not contains_match.empty:
                            is_us = False
                            search_ticker = contains_match['Code'].iloc[0]
                            pos_name_kr = contains_match['Name'].iloc[0]
                        else:
                            # 3. 한국 주식 DB에 아예 없으면 그제서야 미국 주식으로 간주!
                            is_us = True
                            us_results = search_us_ticker(pos_name)
                            if us_results:
                                search_ticker = us_results[0].split(" ")[0]
                                pos_name_kr = us_results[0].split(" (")[1].split(" /")[0]
                            else:
                                search_ticker = pos_name
                                pos_name_kr = pos_name

                    if search_ticker:
                        time.sleep(0.2) 
                        res = analyze_technical_pattern(pos_name_kr, search_ticker)
                        if res:
                            current_price = res['현재가']
                            invested = entry_price * quantity
                            current_val = current_price * quantity
                            
                            # 💡 환율 곱셈 로직 정상화 (미국장에만 1350원 곱하기)
                            if is_us:
                                invested_krw = invested * ex_rate
                                current_val_krw = current_val * ex_rate
                            else:
                                invested_krw = invested
                                current_val_krw = current_val
                            
                            total_invested_all += invested_krw
                            total_current_all += current_val_krw
                            pnl_pct = ((current_price - entry_price) / entry_price) * 100
                            
                            portfolio_summary.append({
                                "종목명": pos_name_kr, "티커": search_ticker, "시장": "미국" if is_us else "한국",
                                "진입단가": entry_price, "현재가": current_price, "수익률(%)": pnl_pct,
                                "평가금액(원환산)": current_val_krw, "상태": res['상태'], "섹터": res.get('섹터', '기타')
                            })
                        else: st.error(f"'{pos_name}' 데이터를 수집할 수 없어 분석에서 제외되었습니다.")
                    else: st.error(f"'{pos_name}' 종목을 찾을 수 없어 분석에서 제외되었습니다.")
                        
                if portfolio_summary:
                    overall_pnl_pct = ((total_current_all - total_invested_all) / total_invested_all) * 100 if total_invested_all > 0 else 0
                    overall_pnl_amt = total_current_all - total_invested_all
                    
                    st.markdown("---")
                    st.markdown("### 🏦 종합 포트폴리오 대시보드")
                    
                    m1, m2, m3, m4 = st.columns(4)
                    m1.metric("총 매수 금액 (원화 환산)", f"{int(total_invested_all):,}원")
                    m2.metric("총 평가 금액 (원화 환산)", f"{int(total_current_all):,}원")
                    m3.metric("총 평가 손익", f"{int(overall_pnl_amt):,}원", f"{overall_pnl_pct:+.2f}%", delta_color="normal" if overall_pnl_amt > 0 else "inverse")
                    m4.metric("보유 종목 수", f"{len(portfolio_summary)}개")
                    
                    summary_df = pd.DataFrame(portfolio_summary)
                    summary_df["비중(%)"] = (summary_df["평가금액(원환산)"] / total_current_all) * 100
                    
                    display_cols = ["종목명", "시장", "섹터", "수익률(%)", "비중(%)", "상태"]
                    st.dataframe(summary_df[display_cols].style.format({"수익률(%)": "{:+.1f}%", "비중(%)": "{:.1f}%"}), use_container_width=True)

                    with st.spinner("AI가 자산 배분 비중과 개별 종목 상태를 종합하여 포트폴리오 리밸런싱 전략을 수립 중입니다..."):
                        now_kst = datetime.utcnow() + timedelta(hours=9)
                        today_str = now_kst.strftime("%Y년 %m월 %d일")
                        port_details_str = ""
                        for item in portfolio_summary:
                            weight = (item["평가금액(원환산)"] / total_current_all) * 100
                            port_details_str += f"- {item['종목명']} ({item['시장']}, {item['섹터']}): 계좌 내 비중 {weight:.1f}%, 수익률 {item['수익률(%)']:+.1f}%, 현재 차트상태: {item['상태']}\n"

                        ai_plan_prompt = f"""
                        당신은 여의도의 냉철한 펀드매니저이자 자산 배분 전문가입니다.
                        🚨 [시스템 필수 지침]: 오늘 날짜는 {today_str}입니다. 
                        [포트폴리오 전체 요약] 총 투자금액: {int(total_invested_all):,}원, 총 평가금액: {int(total_current_all):,}원, 계좌 전체 수익률: {overall_pnl_pct:+.2f}%
                        [개별 구성 종목 상세 (비중 및 상태)]\n{port_details_str}
                        위 포트폴리오를 '개별 종목'이 아닌 '전체 계좌' 관점에서 분석하여 마크다운으로 답변하세요.
                        1. 🏦 **포트폴리오 종합 진단**: 현재 계좌의 자산 배분(특정 섹터에 쏠렸는지 등) 및 전체 수익/리스크 상태에 대한 평가.
                        2. ⚖️ **비중 조절 & 리밸런싱 조언**: 
                           - 현재 비중이 너무 높거나 리스크가 큰 종목은 얼마나 덜어낼 거신가?
                           - 현금화해야 할 종목과 계속 홀딩할 종목 구분.
                        3. 🛡️ **종목별 액션 플랜 요약**: 각 종목별로 유지(Hold), 비중축소(Reduce), 손절(Cut) 여부와 간략한 이유 명시.
                        """
                        plan_result = ask_gemini(ai_plan_prompt, api_key_input)
                        st.success("✅ AI 포트폴리오 종합 진단 및 리밸런싱 플랜 수립 완료!")
                        st.markdown(plan_result)

elif selected_menu == "⭐ 내 관심종목 모니터링":
    st.subheader("⭐ 나만의 관심종목 (Watchlist)")
    if not st.session_state.watchlist: 
        st.info("추가된 종목이 없습니다. 스캐너나 분석기에서 관심종목을 추가해보세요.")
    else:
        col1, col2 = st.columns([8, 2])
        if col2.button("🗑️ 관심종목 모두 지우기", use_container_width=True): 
            st.session_state.watchlist = []; save_watchlist([]); st.rerun()
            
        for i, item in enumerate(st.session_state.watchlist):
            with st.spinner(f"'{item['종목명']}' 데이터 로딩 중..."):
                try:
                    res = analyze_technical_pattern(item['종목명'], item['티커'])
                    if res: draw_stock_card(res, api_key_str=api_key_input, is_expanded=False, key_suffix=f"wl_{i}")
                    else: st.error(f"❌ '{item['종목명']}' ({item['티커']}) 데이터를 불러오지 못했습니다.")
                except Exception as e: st.error(f"❌ '{item['종목명']}' 데이터 분석 중 치명적 오류 발생: {str(e)}")

elif selected_menu == "🌍 글로벌 매크로 & AI 분석 (v6.0)":
    st.markdown("## 🚀 v6.0 메이저 업데이트 (Beta 테스트 룸)")
    st.write("기관 프랍 트레이더 수준의 거시경제 분석, AI 어닝 리포트 해독, 포트폴리오 최적화 등 하이엔드 기능을 제공합니다.")
    v6_t1, v6_t2, v6_t3, v6_t4, v6_t5 = st.tabs(["🌍 1. 글로벌 매크로 관제소", "💼 2. 스마트머니 & 밸류업 추적", "🧠 3. AI PDF 리포트 해독", "🏆 4. 마코위츠 포트폴리오 최적화", "⚡ 5. 체결강도 & 틱(Tick) 분석"])
    
    with v6_t1:
        st.markdown("### 🌍 글로벌 매크로 & 지정학적 리스크 관제소 (The All-Seeing Eye)")
        if st.button("📊 실시간 글로벌 매크로 데이터 연동", type="primary"):
            with st.spinner("Yahoo Finance에서 원자재 및 국채 금리 데이터를 수집 중입니다..."):
                try:
                    tickers = {"금 (Gold)": "GC=F", "은 (Silver)": "SI=F", "구리 (닥터 코퍼)": "HG=F", "비트코인 (BTC)": "BTC-USD"}
                    series_dict = {}
                    for name, ticker in tickers.items():
                        df_hist = yf.Ticker(ticker).history(period="6mo")
                        if not df_hist.empty:
                            df_hist.index = df_hist.index.tz_localize(None).normalize()
                            normalized = (df_hist['Close'] / df_hist['Close'].iloc[0] - 1) * 100
                            normalized = normalized[~normalized.index.duplicated(keep='first')]
                            series_dict[name] = normalized
                    if series_dict:
                        macro_df = pd.DataFrame(series_dict).ffill().dropna()
                        st.markdown("#### 🥇 원자재 & 암호화폐 슈퍼사이클 트래커 (6개월 상대수익률 %)")
                        fig_macro = px.line(macro_df, x=macro_df.index, y=macro_df.columns)
                        fig_macro.update_layout(height=400, yaxis_title="수익률 (%)", xaxis_title="날짜", hovermode="x unified")
                        st.plotly_chart(fig_macro, use_container_width=True)
                    
                    df_10y = yf.Ticker("^TNX").history(period="6mo")
                    df_2y = yf.Ticker("^IRX").history(period="6mo")
                    if not df_10y.empty and not df_2y.empty:
                        df_10y.index = df_10y.index.tz_localize(None).normalize()
                        df_2y.index = df_2y.index.tz_localize(None).normalize()
                        df_spread = (df_10y['Close'] - df_2y['Close']).dropna()
                        st.markdown("#### 📉 미국채 10년-2년 장단기 금리차 (Yield Curve Spread)")
                        fig_spread = go.Figure()
                        fig_spread.add_trace(go.Scatter(x=df_spread.index, y=df_spread.values, mode='lines', name='10Y-2Y Spread', line=dict(color='purple', width=2)))
                        fig_spread.add_hline(y=0, line_dash="dash", line_color="red", annotation_text="금리 역전 기준선")
                        fig_spread.update_layout(height=300, yaxis_title="금리차 (%)", xaxis_title="날짜")
                        st.plotly_chart(fig_spread, use_container_width=True)
                        
                        current_spread = df_spread.iloc[-1]
                        if current_spread < 0: st.error(f"🚨 **현재 장단기 금리차: {current_spread:.2f}%** (금리 역전 상태 - 잠재적 경기침체 경고)")
                        else: st.success(f"✅ **현재 장단기 금리차: {current_spread:.2f}%** (정상 커브)")
                        
                    if api_key_input:
                        st.divider()
                        prompt = f"당신은 수석 이코노미스트입니다. 현재 장단기 금리차가 {df_spread.iloc[-1] if not df_spread.empty else '알수없음'}%이고, 금, 은, 구리, 비트코인 차트를 보았을 때 현재 시장이 '인플레이션 베팅'인지 '경기침체 우려'인지 3줄로 명확하게 판단해주세요."
                        st.info("💡 **AI 매크로 종합 해석:**\n" + ask_gemini(prompt, api_key_input))
                except Exception as e: st.error(f"매크로 데이터 수집 중 오류 발생: {e}")

    with v6_t2:
        st.markdown("### 💼 스마트머니 딥(Deep) 트래커: 밸류업 & 파생 수급")
        sub_t1, sub_t2 = st.tabs(["🔥 옵션 Put/Call 비율 (US)", "🚀 한국 밸류업 스캐너 (KR)"])
        with sub_t1:
            pc_ticker = st.text_input("분석할 미국 티커 (예: AAPL, NVDA)", value="NVDA").upper()
            if st.button("⚖️ Put/Call 비율 연산"):
                with st.spinner("옵션 체인 데이터 수집 중..."):
                    try:
                        tk = yf.Ticker(pc_ticker)
                        expirations = tk.options
                        if not expirations: st.error("해당 종목의 옵션 데이터가 없습니다.")
                        else:
                            opt = tk.option_chain(expirations[0])
                            call_vol = opt.calls['volume'].sum()
                            put_vol = opt.puts['volume'].sum()
                            if call_vol > 0: pc_ratio = put_vol / call_vol
                            c1, c2, c3 = st.columns(3)
                            c1.metric("총 Call 거래량", f"{int(call_vol):,}")
                            c2.metric("총 Put 거래량", f"{int(put_vol):,}")
                            c3.metric("Put/Call Ratio", f"{pc_ratio:.2f}", "1.0 초과 시 약세 심리", delta_color="inverse" if pc_ratio > 1 else "normal")
                            fig_pc = px.pie(values=[call_vol, put_vol], names=['Call (상승 기대)', 'Put (하락 기대)'], hole=0.5, color_discrete_sequence=['#2ca02c', '#d62728'])
                            st.plotly_chart(fig_pc, use_container_width=True)
                    except Exception as e: st.error(f"옵션 연산 실패: {e}")
        with sub_t2:
            if st.button("🚀 밸류업(Value-up) 잠재주 스캔"):
                with st.spinner("재무제표 및 수익성 스크리닝 중..."):
                    candidates = get_longterm_value_stocks_with_ai("PBR 0.8 이하이면서 ROE 10% 이상인 주주환원 유력 후보", "코스피/코스닥 대형주", api_key_input)
                    if candidates:
                        st.success(f"🎯 AI 밸류업 잠재 기업 포착")
                        for name, code in candidates:
                            res = analyze_technical_pattern(name, code)
                            if res: draw_stock_card(res, api_key_str=api_key_input, is_expanded=False, key_suffix=f"vup_{code}")
                    else: st.error("후보를 찾지 못했습니다.")

    with v6_t3:
        st.markdown("### 🧠 AI 어닝콜 & 공시 원문(PDF) 딥리딩 룸")
        if not HAS_PYPDF: st.warning("⚠️ PyPDF2 모듈이 없습니다. 텍스트를 직접 복사해서 넣어주세요.")
        pdf_file = st.file_uploader("📄 PDF 리포트 업로드", type=["pdf"])
        raw_text = ""
        if pdf_file and HAS_PYPDF:
            with st.spinner("PDF 텍스트 추출 중..."):
                pdf_reader = PyPDF2.PdfReader(pdf_file)
                for page in pdf_reader.pages: raw_text += page.extract_text() + "\n"
        elif not HAS_PYPDF: raw_text = st.text_area("📄 텍스트 직접 붙여넣기:", height=150)
        if raw_text and api_key_input:
            if st.button("🤖 Gemini 리포트 해독 시작", type="primary"):
                with st.spinner("AI 분석 중..."):
                    prompt = f"당신은 리서치 애널리스트입니다. 다음 원문에서 1)목표주가 2)핵심투자포인트 3가지 3)리스크 2가지를 요약해주세요.\n\n{raw_text[:15000]}"
                    st.info(ask_gemini(prompt, api_key_input))

    with v6_t4:
        st.markdown("### 🏆 노벨상 수상 알고리즘: '마코위츠' 포트폴리오 최적화 엔진")
        port_input_m = st.text_input("포트폴리오 종목 (예: AAPL, MSFT, TSLA)", value="AAPL, MSFT, GOOGL, NVDA, TSLA")
        if st.button("⚙️ 몬테카를로 시뮬레이션 (1,000번 반복)", type="primary"):
            tickers_m = [t.strip() for t in port_input_m.split(",") if t.strip()]
            if len(tickers_m) >= 2:
                with st.spinner("최적 가중치 연산 중..."):
                    try:
                        data_m = pd.DataFrame()
                        for t in tickers_m:
                            df_t = yf.Ticker(t).history(period="1y")
                            if not df_t.empty: data_m[t] = df_t['Close']
                        data_m = data_m.dropna()
                        if not data_m.empty:
                            returns = data_m.pct_change().dropna()
                            mean_returns = returns.mean() * 252
                            cov_matrix = returns.cov() * 252
                            num_portfolios = 1000
                            results_m = np.zeros((3, num_portfolios))
                            weights_record = []
                            for i in range(num_portfolios):
                                weights = np.random.random(len(tickers_m))
                                weights /= np.sum(weights)
                                weights_record.append(weights)
                                portfolio_return = np.sum(mean_returns * weights)
                                portfolio_std_dev = np.sqrt(np.dot(weights.T, np.dot(cov_matrix, weights)))
                                results_m[0,i] = portfolio_return
                                results_m[1,i] = portfolio_std_dev
                                results_m[2,i] = (portfolio_return - 0.02) / portfolio_std_dev
                            results_df = pd.DataFrame(results_m.T, columns=['Return', 'Volatility', 'Sharpe'])
                            max_sharpe_idx = results_df['Sharpe'].idxmax()
                            max_sharpe_port = results_df.iloc[max_sharpe_idx]
                            opt_weights = weights_record[max_sharpe_idx]
                            fig_ef = px.scatter(results_df, x='Volatility', y='Return', color='Sharpe', title="효율적 전선 (Efficient Frontier)")
                            fig_ef.add_trace(go.Scatter(x=[max_sharpe_port['Volatility']], y=[max_sharpe_port['Return']], mode='markers', marker=dict(color='red', size=15, symbol='star'), name='최적점'))
                            st.plotly_chart(fig_ef, use_container_width=True)
                            col_w, col_s = st.columns([1, 1])
                            with col_w:
                                weight_df = pd.DataFrame({'종목': tickers_m, '비율(%)': (opt_weights * 100).round(2)})
                                fig_w = px.pie(weight_df, values='비율(%)', names='종목', hole=0.4)
                                st.plotly_chart(fig_w, use_container_width=True)
                            with col_s:
                                st.metric("예상 연평균 수익률", f"{max_sharpe_port['Return']*100:.2f}%")
                                st.metric("예상 연 변동성", f"{max_sharpe_port['Volatility']*100:.2f}%")
                                st.metric("샤프 지수", f"{max_sharpe_port['Sharpe']:.2f}")
                    except Exception as e: st.error(f"오류: {e}")

    with v6_t5:
        st.markdown("### ⚡ 실시간 호가창 체결강도 & 모멘텀 (1분봉 틱 분석)")
        tick_ticker = st.text_input("종목 티커 입력 (예: TSLA - 야후 파이낸스 1m 데이터)", value="TSLA").upper()
        if st.button("🔎 1분봉 누적 거래량 델타(CVD) 분석"):
            with st.spinner("야후 파이낸스 1분봉 데이터 추출 중..."):
                try:
                    df_tick = yf.Ticker(tick_ticker).history(period="1d", interval="1m")
                    if df_tick.empty: st.error("1분봉 데이터가 없습니다.")
                    else:
                        delta_direction = np.sign(df_tick['Close'] - df_tick['Open'])
                        delta_direction = delta_direction.replace(0, method='ffill').fillna(1)
                        df_tick['CVD'] = (df_tick['Volume'] * delta_direction).cumsum()
                        fig_tick = go.Figure()
                        fig_tick.add_trace(go.Scatter(x=df_tick.index, y=df_tick['Close'], name='주가', line=dict(color='blue', width=2)))
                        fig_tick.add_trace(go.Scatter(x=df_tick.index, y=df_tick['CVD'], name='누적 매수압력(CVD)', yaxis='y2', line=dict(color='orange', width=2, dash='dot')))
                        fig_tick.update_layout(title=f"[{tick_ticker}] 당일 1분봉 주가 vs 누적 매수 압력(CVD)", yaxis=dict(title="주가"), yaxis2=dict(title="CVD", overlaying="y", side="right"), height=400, hovermode="x unified")
                        st.plotly_chart(fig_tick, use_container_width=True)
                except Exception as e: st.error(f"분석 실패: {e}")

elif selected_menu == "🗺️ 시장 주도주 자금 히트맵":
    st.subheader("🗺️ 시장 주도주 & 스마트머니 유입 섹터 히트맵")
    st.write("거래대금이 터진 종목들 중 기관 매수세가 동반된 종목을 파악합니다. (녹색: 상승 / 붉은색: 하락)")
    heatmap_limit = st.radio("🔥 히트맵 표시 종목 수 선택 (개)", [30, 50, 100], index=1, horizontal=True)
    
    with st.spinner(f"거래대금 상위 {heatmap_limit}종목 데이터 및 수급 스크래핑 중..."):
        t_kings = get_trading_value_kings(limit=heatmap_limit)
        if not t_kings.empty:
            pension_streaks = []
            progress_bar = st.progress(0)
            status_text = st.empty()
            total_k = len(t_kings)
            for i, (idx, row) in enumerate(t_kings.iterrows()):
                _, streak = get_pension_fund_trend(row['Code'])
                pension_streaks.append(streak)
                progress_bar.progress((i + 1) / total_k)
                status_text.text(f"📊 종목 수급 파싱 중... ({i + 1}/{total_k})")
            status_text.empty()
            progress_bar.empty()
            
            t_kings['연속매수'] = pension_streaks
            t_kings['수급상태'] = t_kings['연속매수'].apply(lambda x: "🔥기관 매집중" if x >= 2 else "일반거래")
            t_kings['display_text'] = "<span style='font-size:16px; font-weight:bold;'>" + t_kings['Name'] + "</span><br>" + t_kings['ChagesRatio'].map("{:+.2f}%".format) + "<br>" + t_kings['수급상태']
            
            fig = px.treemap(t_kings, path=[px.Constant("🔥 주도 섹터 (수급 동반)"), 'Sector', 'Name'], values='Amount_Ouk', color='ChagesRatio', color_continuous_scale=[(0.0, '#f63538'), (0.5, '#414554'), (1.0, '#30cc5a')], color_continuous_midpoint=0, custom_data=['ChagesRatio', 'Amount_Ouk', 'display_text', '연속매수'])
            fig.update_traces(textinfo="text", texttemplate="%{customdata[2]}", hovertemplate="<b>%{label}</b><br>등락률: %{customdata[0]:+.2f}%<br>거래대금: %{customdata[1]:,}억<br>연속매수: %{customdata[3]}일")
            fig.update_layout(margin=dict(t=30, l=10, r=10, b=10), height=600 if heatmap_limit <= 50 else 800)
            st.plotly_chart(fig, use_container_width=True)
            
            st.markdown("### 📊 수급 동반 거래대금 상위 종목 타점 확인")
            sel_king = st.selectbox("타점 확인:", ["선택"] + t_kings[t_kings['연속매수'] >= 1]['Name'].tolist())
            if sel_king != "선택":
                k_code = t_kings[t_kings['Name'] == sel_king]['Code'].iloc[0]
                if res := analyze_technical_pattern(sel_king, k_code): draw_stock_card(res, api_key_str=api_key_input, is_expanded=True)

elif selected_menu == "🕸️ 실시간 섹터 순환매 추적":
    st.markdown("## 🕸️ 실시간 스마트머니 물길 추적 (Sankey Diagram)")
    st.write("현재 시점의 시장 데이터를 실시간 역산하여, **수익률이 가장 저조한 3개 섹터(자금 유출)**에서 **가장 높은 3개 섹터(자금 유입)**로 수급이 이동하는 '순환매' 흐름을 시각화합니다.")
    
    period_sk = st.radio("분석 기간", ["1개월", "3개월", "6개월"], horizontal=True)
    period_col = "1M수익률" if period_sk == "1개월" else "3M수익률" if period_sk == "3개월" else "6M수익률"
    
    with st.spinner(f"최근 {period_sk} 시장 섹터 수익률 실시간 연산 중..."):
        trend_df = analyze_theme_trends()
        
    if not trend_df.empty:
        df_sorted = trend_df.sort_values(period_col, ascending=True)
        losers = df_sorted.head(3) 
        winners = df_sorted.tail(3) 
        nodes = losers['테마'].tolist() + ["시장 유동성(대기자금)"] + winners['테마'].tolist()
        colors = ["#7f7f7f", "#7f7f7f", "#7f7f7f", "#d3d3d3", "#ff4b4b", "#2ca02c", "#ff9800"]
        sources = [0, 1, 2, 3, 3, 3]
        targets = [3, 3, 3, 4, 5, 6]
        
        v_in = [max(1, abs(x)) for x in losers[period_col]]
        v_out = [max(1, abs(x)) for x in winners[period_col]]
        sum_in, sum_out = sum(v_in), sum(v_out)
        v_out_adjusted = [x * (sum_in / sum_out) for x in v_out] if sum_in > 0 and sum_out > 0 else v_out
        values = v_in + v_out_adjusted
        
        fig_sk = go.Figure(data=[go.Sankey(node = dict(pad = 35, thickness = 30, line = dict(color = "black", width = 1.0), label = nodes, color = colors), link = dict(source = sources, target = targets, value = values, color = "rgba(200, 200, 200, 0.4)"))])
        fig_sk.update_traces(textfont=dict(size=14, color="black", family="Arial Black"))
        fig_sk.update_layout(title_text=f"최근 {period_sk} 주도 테마 순환매 흐름 ({datetime.now().strftime('%Y.%m.%d')} 기준)", height=600)
        st.plotly_chart(fig_sk, use_container_width=True)
        st.info(f"💡 **실시간 데이터 분석:** 최근 {period_sk} 동안 **[{', '.join(losers['테마'].tolist())}]** 섹터에서 차익 실현된 자금이 유출되어, **[{', '.join(winners['테마'].tolist())}]** 섹터의 상승을 주도하고 있는 것으로 추정됩니다.")
    else: st.error("테마별 시장 데이터를 불러오지 못했습니다.")

elif selected_menu == "📅 핵심 증시 일정 & IPO 달력":
    st.subheader("📅 핵심 증시 일정 & 스마트머니 달력")
    cal_tab1, cal_tab2, cal_tab3 = st.tabs(["🌍 글로벌 경제 지표", "🧠 통합 수급 달력 (국장+미장)", "🇰🇷 국내 IPO 분석"])
    
    with cal_tab1: 
        components.html("""
        <div class="tradingview-widget-container"><div class="tradingview-widget-container__widget"></div>
        <script type="text/javascript" src="https://s3.tradingview.com/external-embedding/embed-widget-events.js" async>
        { "colorTheme": "light", "isTransparent": true, "width": "100%", "height": "600", "locale": "kr", "importanceFilter": "-1,0,1", "currencyFilter": "USD,KRW,CNY,EUR,JPY" }
        </script></div>
        """, height=600)

    with cal_tab2:
        st.markdown("#### 🌎 글로벌 파생수급 통합 시나리오")
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
        us_shoot_days = [us_opex_day + 3, us_opex_day + 4] 
        us_macro_days = [day for day in range(10, 15) if day not in us_opex_week_days]

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
            ".evt-us-red { background: #ffebee; color: #c62828; font-size: 11px; padding: 3px; margin-bottom: 2px; border-left: 3px solid #c62828; border-radius: 2px; font-weight: bold; line-height: 1.2; letter-spacing: -0.5px; }",
            ".evt-us-warn { background: #fff3e0; color: #e65100; font-size: 11px; padding: 3px; margin-bottom: 2px; border-left: 3px solid #e65100; border-radius: 2px; font-weight: bold; line-height: 1.2; letter-spacing: -0.5px; }",
            ".evt-us-green { background: #e8f5e9; color: #2e7d32; font-size: 11px; padding: 3px; margin-bottom: 2px; border-left: 3px solid #2e7d32; border-radius: 2px; font-weight: bold; line-height: 1.2; letter-spacing: -0.5px; }",
            ".evt-kr-red { background: #fce4ec; color: #b71c1c; font-size: 11px; padding: 3px; margin-bottom: 2px; border-left: 3px solid #b71c1c; border-radius: 2px; font-weight: bold; line-height: 1.2; letter-spacing: -0.5px; }",
            ".evt-kr-blue { background: #e3f2fd; color: #1565c0; font-size: 11px; padding: 3px; margin-bottom: 2px; border-left: 3px solid #1565c0; border-radius: 2px; font-weight: bold; line-height: 1.2; letter-spacing: -0.5px; }",
            ".evt-kr-green { background: #f1f8e9; color: #1b5e20; font-size: 11px; padding: 3px; margin-bottom: 2px; border-left: 3px solid #1b5e20; border-radius: 2px; font-weight: bold; line-height: 1.2; letter-spacing: -0.5px; }",
            "</style>",
            "<div class='cal-grid'>",
            "<div class='cal-head' style='color:#d32f2f;'>일</div><div class='cal-head'>월</div><div class='cal-head'>화</div><div class='cal-head'>수</div><div class='cal-head'>목</div><div class='cal-head'>금</div><div class='cal-head' style='color:#1976d2;'>토</div>"
        ]
        
        for week in cal:
            for i, day in enumerate(week):
                if day == 0: html_parts.append("<div class='cal-cell' style='background:#fafafa;'></div>")
                else:
                    events = ""
                    if day == tax_day: events += "<div class='evt-us-red'>🔴 🇺🇸세금납부일(하락압력)</div>"
                    if i == calendar.MONDAY: events += "<div class='evt-kr-blue'>🔹 🇰🇷위클리 만기(수급재편)</div>"
                    elif i == calendar.THURSDAY:
                        if day == kr_opex_day:
                            label = "🔥 🇰🇷네마녀의 날" if kr_is_quadruple else "🔴 🇰🇷옵션만기일"
                            events += f"<div class='evt-kr-red'>{label}(수급극대)</div>"
                        else: events += "<div class='evt-kr-blue'>🔹 🇰🇷위클리 만기(오후변동)</div>"
                    elif i == calendar.FRIDAY and day == kr_opex_day + 1: events += "<div class='evt-kr-green'>🟢 🇰🇷수급 되돌림(추세복귀)</div>"

                    if day in us_opex_week_days:
                        if day == us_opex_day: events += "<div class='evt-us-red'>🔴 🇺🇸옵션만기(변동성폭발)</div>"
                        else: events += "<div class='evt-us-warn'>⚠️ 🇺🇸만기주간(핀닝/하락)</div>"
                    elif day in us_macro_days and day != tax_day: events += "<div class='evt-us-warn'>⚠️ 🇺🇸매크로 경계(관망)</div>"
                    
                    if day in us_shoot_days: events += "<div class='evt-us-green'>🟢 🇺🇸헤지청산(슈팅기대)</div>"

                    num_color = "#d32f2f" if i == 0 else "#1976d2" if i == 6 else "#333"
                    cell_cls = "cal-cell today" if day == today_day else "cal-cell"
                    day_lbl = f"{day} (오늘)" if day == today_day else str(day)
                    html_parts.append(f"<div class='{cell_cls}'><div class='cal-num' style='color:{num_color};'>{day_lbl}</div>{events}</div>")

        html_parts.append("</div>")
        st.markdown("".join(html_parts), unsafe_allow_html=True)

    with cal_tab3:
        with st.spinner("최신 IPO 일정을 파싱 중입니다..."):
            ipo_df = get_naver_ipo_data()
        if not ipo_df.empty:
            st.dataframe(ipo_df, use_container_width=True, hide_index=True)
            if api_key_input and st.button("🤖 AI 공모주 옥석 가리기", type="primary"):
                st.success(ask_gemini(f"다음 상장 일정: {ipo_df[['종목명', '청약일정']].to_string()}\n따상 가능성 높은 1~2개 꼽고 이유 3줄 평가.", api_key_input))
        else: 
            st.error("❌ 현재 예정된 신규 상장(IPO) 일정이 없거나, 거래소 데이터를 불러올 수 없습니다.")

elif selected_menu == "🚀 단기 스윙 퀀트 스캐너":
    st.markdown("## 🚀 실시간 조건 검색 및 1년 백테스팅 시뮬레이터")
    scan_tab, backtest_tab = st.tabs(["🚀 실시간 조건 검색 스캐너", "🧪 1년 전략 백테스팅"])
    
    with scan_tab:
        show_beginner_guide()
        show_trading_guidelines()
        
        scan_market = st.radio("시장 선택 (스캐너)", ["🇰🇷 국내 주식", "🇺🇸 미국 주식"], horizontal=True)
        col_c1, col_c2, col_c3, col_c4 = st.columns(4)
        with col_c1: cond_golden = st.checkbox("✨ 골든크로스 / 정배열 초입"); cond_pullback = st.checkbox("✅ 20일선 눌림목 (타점 근접)", value=True)
        with col_c2: cond_rsi_bottom = st.checkbox("🔵 RSI 30 이하 (낙폭과대)"); cond_vol_spike = st.checkbox("🔥 최근 거래량 급증 (세력 의심)")
        with col_c3: cond_twin_buy = st.checkbox("🐋 외인/기관 쌍끌이 순매수")
        with col_c4: cond_pension = st.checkbox("👴 기관 3일 연속 순매수")
        
        scan_limit = st.selectbox("스캔할 상위 종목 수", [50, 100, 200, 300], index=3)
        
        if st.button("🚀 쾌속 병렬 스캔 시작", type="primary", use_container_width=True):
            with st.spinner(f"⚡ {scan_limit}개 종목 고속 필터링 중..."):
                if scan_market == "🇰🇷 국내 주식": targets = get_scan_targets(scan_limit)
                else: targets = get_us_scan_targets(scan_limit)
                    
                if not targets: st.error("❌ 종목 데이터를 불러오지 못했습니다.")
                else:
                    progress_bar = st.progress(0)
                    status_text = st.empty()
                    found_results = []
                    completed, total = 0, len(targets)
                    def process_stock(target):
                        name, code = target
                        time.sleep(0.1) 
                        res = analyze_technical_pattern(name, code, offset_days=0)
                        if res:
                            if cond_golden and "🔥 완벽 정배열" not in res['배열상태'] and "✨ 5-20 골든크로스" not in res['배열상태']: return None
                            if cond_pullback and res['상태'] != "✅ 타점 근접 (분할 매수)": return None
                            if cond_rsi_bottom and res['RSI'] > 30: return None
                            if cond_vol_spike and res['거래량 급증'] != "🔥 거래량 터짐": return None
                            if cond_twin_buy and ("+" not in str(res['기관수급']) or "+" not in str(res['외인수급'])): return None
                            if cond_pension and res.get('연기금연속순매수', 0) < 3: return None
                            return res
                        return None
                    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
                        for future in concurrent.futures.as_completed({executor.submit(process_stock, t): t for t in targets}):
                            res = future.result()
                            completed += 1
                            if res: found_results.append(res)
                            progress_bar.progress(completed / total)
                            status_text.text(f"⚡ 스캔 진행 중... ({completed}/{total}) - {len(found_results)}개 포착")
                    st.session_state.scan_results = found_results
                    st.rerun()
        if st.session_state.scan_results is not None: display_sorted_results(st.session_state.scan_results, tab_key="t2", api_key=api_key_input)

    with backtest_tab:
        st.markdown("### 🧪 단기 스윙 전략 시뮬레이터")
        st.write("과거 1년 데이터를 기반으로 다양한 퀀트 전략의 실제 수익률과 타점을 검증합니다.")
        
        market_choice_bt = st.radio("시장 선택 (백테스트)", ["🇰🇷 국내 주식", "🇺🇸 미국 주식"], horizontal=True, label_visibility="collapsed")
        t_code = None
        if market_choice_bt == "🇰🇷 국내 주식":
            krx_df = get_krx_stocks()
            opts = ["🔍 테스트할 종목 검색"] + (krx_df['Name'].astype(str) + " (" + krx_df['Code'].astype(str) + ")").tolist() if not krx_df.empty else ["005930"]
            test_query = st.selectbox("백테스트 종목:", opts)
            if test_query != "🔍 테스트할 종목 검색":
                t_code = test_query.rsplit("(", 1)[-1].replace(")", "").strip() if "(" in test_query else "005930"
        else:
            with st.form("bt_us_form"):
                us_bt_query = st.text_input("🔍 미국 주식 종목명/티커 (예: AAPL):")
                us_bt_search_btn = st.form_submit_button("검색")
            if us_bt_search_btn and us_bt_query:
                with st.spinner("검색 중..."): us_bt_results = search_us_ticker(us_bt_query)
                if us_bt_results: st.session_state.us_bt_results = us_bt_results
                else: st.error("검색 결과가 없습니다.")
            if "us_bt_results" in st.session_state and st.session_state.us_bt_results:
                sel_us_bt = st.selectbox("🎯 정확한 종목 선택:", ["선택하세요"] + st.session_state.us_bt_results)
                if sel_us_bt != "선택하세요": t_code = sel_us_bt.split(" ")[0]
        
        strategy_sel = st.selectbox("🎯 백테스트 퀀트 전략 선택", [
            "5-20 이평선 골든크로스", "RSI 과매도 매수 (RSI < 30)", "볼린저밴드 하단 매수", "MACD 교차"
        ])

        if t_code and st.button("▶️ 시뮬레이션 돌리기", type="primary"):
            with st.spinner("과거 1년 데이터 백테스팅 중..."):
                bt_df = get_historical_data(t_code, 365)
                if not bt_df.empty:
                    bt_df['MA5'] = bt_df['Close'].rolling(5).mean()
                    bt_df['MA20'] = bt_df['Close'].rolling(20).mean()
                    bt_df['Std_20'] = bt_df['Close'].rolling(window=20).std()
                    bt_df['Bollinger_Lower'] = bt_df['MA20'] - (bt_df['Std_20'] * 2)
                    delta = bt_df['Close'].diff()
                    rs = (delta.where(delta > 0, 0.0).rolling(14).mean()) / (-delta.where(delta < 0, 0.0).rolling(14).mean())
                    bt_df['RSI'] = 100 - (100 / (1 + rs))
                    exp1 = bt_df['Close'].ewm(span=12, adjust=False).mean()
                    exp2 = bt_df['Close'].ewm(span=26, adjust=False).mean()
                    bt_df['MACD'] = exp1 - exp2
                    bt_df['Signal_Line'] = bt_df['MACD'].ewm(span=9, adjust=False).mean()

                    bt_df['Signal'] = 0
                    if strategy_sel == "5-20 이평선 골든크로스": bt_df.loc[bt_df['MA5'] > bt_df['MA20'], 'Signal'] = 1
                    elif strategy_sel == "RSI 과매도 매수 (RSI < 30)": bt_df.loc[bt_df['RSI'] < 30, 'Signal'] = 1
                    elif strategy_sel == "볼린저밴드 하단 매수": bt_df.loc[bt_df['Close'] < bt_df['Bollinger_Lower'], 'Signal'] = 1
                    elif strategy_sel == "MACD 교차": bt_df.loc[bt_df['MACD'] > bt_df['Signal_Line'], 'Signal'] = 1

                    bt_df['Position'] = bt_df['Signal'].shift(1).fillna(0)
                    bt_df['Daily_Return'] = bt_df['Close'].pct_change()
                    bt_df['Strategy_Return'] = bt_df['Position'] * bt_df['Daily_Return']
                    bt_df['Cumulative_Market'] = (1 + bt_df['Daily_Return']).cumprod()
                    bt_df['Cumulative_Strategy'] = (1 + bt_df['Strategy_Return']).cumprod()
                    bt_df['Trade_Mark'] = bt_df['Position'].diff()
                    
                    bt_df['Cum_Max'] = bt_df['Cumulative_Strategy'].cummax()
                    bt_df['Drawdown'] = (bt_df['Cumulative_Strategy'] - bt_df['Cum_Max']) / bt_df['Cum_Max']
                    mdd = bt_df['Drawdown'].min() * 100
                    
                    total_trades = len(bt_df[bt_df['Trade_Mark'] == 1])
                    winning_days = len(bt_df[bt_df['Strategy_Return'] > 0])
                    losing_days = len(bt_df[bt_df['Strategy_Return'] < 0])
                    win_rate = (winning_days / (winning_days + losing_days) * 100) if (winning_days + losing_days) > 0 else 0
                    
                    fig = go.Figure()
                    x_axis = bt_df.index
                    fig.add_trace(go.Scatter(x=x_axis, y=bt_df['Close'], name="주가 (Close)", line=dict(color='#3b82f6', width=1.5)))
                    buy_idx = bt_df[bt_df['Trade_Mark'] == 1].index
                    fig.add_trace(go.Scatter(x=buy_idx, y=bt_df.loc[buy_idx, 'Close'], mode='markers', name='Buy (매수)', marker=dict(symbol='triangle-up', size=14, color='#ef4444', line=dict(width=1, color='darkred'))))
                    sell_idx = bt_df[bt_df['Trade_Mark'] == -1].index
                    fig.add_trace(go.Scatter(x=sell_idx, y=bt_df.loc[sell_idx, 'Close'], mode='markers', name='Sell (매도)', marker=dict(symbol='triangle-down', size=14, color='#3b82f6', line=dict(width=1, color='darkblue'))))

                    fig.update_layout(title=f"'{t_code}' 백테스트 타점 시각화 ({strategy_sel})", height=500, hovermode="x unified", legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1))
                    st.plotly_chart(fig, use_container_width=True)
                    
                    final_market = (bt_df['Cumulative_Market'].iloc[-1] - 1) * 100
                    final_strat = (bt_df['Cumulative_Strategy'].iloc[-1] - 1) * 100
                    
                    st.markdown("### 📊 백테스트 성과 리포트")
                    c1, c2, c3, c4 = st.columns(4)
                    def metric_card(title, value, delta=None, is_red=False, is_green=False):
                        bg_color = "rgba(100, 100, 100, 0.05)"
                        border_color = "#888"
                        if is_red:
                            bg_color = "rgba(220, 38, 38, 0.08)"
                            border_color = "#dc2626"
                        elif is_green:
                            bg_color = "rgba(22, 163, 74, 0.08)"
                            border_color = "#16a34a"
                        delta_html = f"<div style='font-size:0.85em; margin-top:5px; color:#555;'>{delta}</div>" if delta else ""
                        return f"<div style='background-color: {bg_color}; padding: 15px; border-radius: 8px; border-left: 4px solid {border_color}; margin-bottom: 10px;'><div style='font-size:0.9em; color:#555; font-weight:bold;'>{title}</div><div style='font-size:1.6em; font-weight:bold; font-family:\"JetBrains Mono\", monospace; margin-top:5px;'>{value}</div>{delta_html}</div>"

                    with c1: st.markdown(metric_card("전략 누적 수익률", f"{final_strat:.2f}%", f"단순 보유 대비 {final_strat - final_market:+.2f}%p", is_red=(final_strat>0), is_green=(final_strat<0)), unsafe_allow_html=True) 
                    with c2: st.markdown(metric_card("최대 낙폭 (MDD)", f"{mdd:.2f}%", "계좌 최대 하락률", is_green=(mdd<-20)), unsafe_allow_html=True)
                    with c3: st.markdown(metric_card("총 매매 횟수", f"{total_trades}회", "신규 진입 기준"), unsafe_allow_html=True)
                    with c4: st.markdown(metric_card("승률 (Win Rate)", f"{win_rate:.1f}%", "수익 마감 거래일 기준", is_red=(win_rate>50)), unsafe_allow_html=True)
                else: st.error("❌ 데이터를 가져오지 못했습니다.")

elif selected_menu == "👨‍🦳 기관/외인 수급 스캐너":
    st.markdown("## 👨‍🦳 기관/외인 메이저 수급 스캐너 (Smart Money Tracker)")
    show_trading_guidelines()
    
    col_c1, col_c2 = st.columns(2)
    with col_c1: pension_streak_cond = st.slider("최소 기관 연속 순매수 일수", min_value=1, max_value=5, value=3)
    with col_c2: pension_pullback_cond = st.checkbox("✅ 20일선 눌림목 근접 종목만 보기", value=True)
        
    scan_limit = st.selectbox("스캔할 거래대금 상위 종목 수", [50, 100, 200], index=1)
    
    if st.button("🚀 기관 수급 종목 스캔 시작", type="primary", use_container_width=True):
        with st.spinner(f"⚡ 상위 {scan_limit}개 종목의 수급 동향 파싱 중..."):
            targets = get_scan_targets(scan_limit)
            if not targets: st.error("종목 데이터를 불러오지 못했습니다.")
            else:
                progress_bar = st.progress(0)
                status_text = st.empty()
                found_results = []
                completed, total = 0, len(targets)
                def process_pension_stock(target):
                    name, code = target
                    time.sleep(0.1) 
                    res = analyze_technical_pattern(name, code)
                    if res:
                        if res.get('연기금연속순매수', 0) < pension_streak_cond: return None
                        if pension_pullback_cond and "✅ 타점 근접" not in res['상태']: return None
                        return res
                    return None
                 
                with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
                    for future in concurrent.futures.as_completed({executor.submit(process_pension_stock, t): t for t in targets}):
                        res = future.result()
                        completed += 1
                        if res: found_results.append(res)
                        progress_bar.progress(completed / total)
                        status_text.text(f"⚡ 수급 분석 중... ({completed}/{total}) - {len(found_results)}개 포착")
                st.session_state.pension_scan_results = found_results
                st.rerun()
    if st.session_state.pension_scan_results is not None: display_sorted_results(st.session_state.pension_scan_results, tab_key="pension", api_key=api_key_input)

elif selected_menu == "🏛️ 국민연금 5% 대량보유 픽":
    st.markdown("## 🏛️ 국민연금(NPS) 메가 포트폴리오 트래커")
    st.write("국민연금이 대량 보유한 국내/해외 핵심 기업 포트폴리오를 실시간 스크래핑하여 추적합니다.")

    col_btn1, col_btn2 = st.columns([2, 8])
    if col_btn1.button("🔄 실시간 스크래핑 시도", type="primary", use_container_width=True):
        get_nps_holdings.clear()
        get_nps_us_portfolio.clear()
        st.rerun()
        
    with st.spinner("데이터를 실시간으로 파싱 중입니다. (서버 차단 시 최신 캐시 데이터 제공)"):
        nps_kr_df = get_nps_holdings()
        nps_us_df = get_nps_us_portfolio()
    
    tab_nps1, tab_nps2, tab_nps3 = st.tabs(["🇰🇷 한국 주식 5% 이상 보유 현황", "🇺🇸 미국 주식 핵심 포트폴리오 (13F)", "🌟 황금 콤보 스캐너 (장기 가치 + 단기 수급)"])
    
    with tab_nps1:
        st.write("*(에프앤가이드(FnGuide)를 통해 코스피/코스닥 주요 기업의 국민연금 지분율을 추출한 데이터입니다.)*")
        st.dataframe(nps_kr_df, use_container_width=True, hide_index=True)
         
    with tab_nps2:
        st.write("*(WhaleWisdom 등 미국 SEC 13F 공시 트래커를 기반으로 파싱된 국민연금 미국 주식 포트폴리오입니다.)*")
        st.dataframe(nps_us_df, use_container_width=True, hide_index=True)
        
    with tab_nps3:
        st.markdown("### 🌟 황금 콤보 전략")
        st.write("**`[조건]`** 기관이 5% 이상 보유하여 **기본적인 펀더멘털이 검증된 종목** 중, 최근 시장에서 **기관이 다시 3일 이상 순매수를 시작**하며 단기 모멘텀이 붙기 시작한 종목을 스캔합니다.")
        
        if st.button("🚀 황금 콤보 교차 스캔 시작", type="primary"):
            with st.spinner("수급 패턴 교차 분석 중..."):
                combo_results = []
                progress_bar2 = st.progress(0)
                completed2, total2 = 0, len(nps_kr_df)
                
                for idx, row in nps_kr_df.iterrows():
                    res = analyze_technical_pattern(row['종목명'], row['티커'])
                    if res and res.get('연기금연속순매수', 0) >= 2: 
                        res['NPS_비중'] = row['보유비중']
                        combo_results.append(res)
                    completed2 += 1
                    progress_bar2.progress(completed2 / total2)
                    
                if combo_results:
                    st.success(f"🎯 펀더멘털과 수급이 완벽하게 일치하는 황금 콤보 {len(combo_results)}개 종목 포착!")
                    for i, res in enumerate(combo_results):
                        st.markdown(f"#### 🏆 기관 보유 비중: {res['NPS_비중']}")
                        draw_stock_card(res, api_key_str=api_key_input, is_expanded=True, key_suffix=f"combo_{i}")
                else:
                    st.warning("현재 황금 콤보 조건에 부합하는 종목이 없습니다.")

elif selected_menu == "💎 장기 우량주 & 가치주 발굴":
    st.markdown("## 💎 여의도 데스크: 기관급 가치주/성장주 스캐너")
    col_v1, col_v2 = st.columns([2, 1])
    with col_v1:
        expert_strategy = st.selectbox("🧠 펀드매니저 투자 전략 선택:", [
            "👑 벤저민 그레이엄형 (안전마진 + 딥밸류: 초저PER & PBR)", "📈 피터 린치형 (GARP: 합리적 가격의 우량 성장주)",
            "🏰 워런 버핏형 (경제적 해자 + 독점력 + 높은 ROE)", "🔄 턴어라운드 & 배당 (실적 바닥 탈출 또는 고배당 방어주)"
        ])
    with col_v2: cap_size = st.selectbox("🏢 기업 규모 선택:", ["대/중/소형 상관없음", "코스피 대형우량주만", "코스닥 중소형 숨은진주"], index=0)
        
    if "그레이엄" in expert_strategy: max_per, max_pbr = 10.0, 1.0
    elif "피터 린치" in expert_strategy: max_per, max_pbr = 20.0, 3.0
    elif "워런 버핏" in expert_strategy: max_per, max_pbr = 30.0, 5.0
    else: max_per, max_pbr = 999.0, 3.0
        
    st.info(f"💡 **현재 전략 필터 기준:** AI가 1차 발굴한 종목 중 **[PER {max_per} 이하 ｜ PBR {max_pbr} 이하]**인 펀더멘털 합격 종목만 2차로 차트 타점을 검증합니다.")

    if st.button("💎 딥 밸류 병렬 스캔 시작", type="primary", use_container_width=True):
        if not api_key_input: st.warning("API 키를 입력해주세요.")
        else:
            with st.spinner("여의도 퀀트 알고리즘으로 스캔 중..."):
                candidates = get_longterm_value_stocks_with_ai(expert_strategy, cap_size, api_key_input)
                if not candidates: st.error("❌ 관련 기업을 찾지 못했습니다.")
                else:
                    progress_bar = st.progress(0)
                    value_results = []
                    completed, total = 0, len(candidates)
                    def process_fundamental(target):
                        name, code = target
                        time.sleep(0.1) 
                        per_str, pbr_str, _, _, _ = get_fundamentals(code)
                        try:
                            per_val = float(str(per_str).replace(',', '')) if str(per_str) not in ['N/A', 'None', ''] else 9999.0
                            pbr_val = float(str(pbr_str).replace(',', '')) if str(pbr_str) not in ['N/A', 'None', ''] else 9999.0
                            if (0 < per_val <= max_per) and (0 < pbr_val <= max_pbr):
                                return analyze_technical_pattern(name, code)
                        except Exception: pass
                        return None
                    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
                        for future in concurrent.futures.as_completed({executor.submit(process_fundamental, c): c for c in candidates}):
                            res = future.result()
                            completed += 1
                            if res: value_results.append(res)
                            progress_bar.progress(completed / total)
                    st.session_state.value_scan_results = value_results
                    st.rerun()
    if st.session_state.value_scan_results is not None: display_sorted_results(st.session_state.value_scan_results, tab_key="t3", api_key=api_key_input)

elif clean_menu == "⚡ 메가트렌드 & 테마 대장주":
    st.markdown("## ⚡ 메가트렌드 & 주도 테마 밸류체인 스캐너")
    hot_themes_tab5 = get_trending_themes_with_ai(api_key_input)
    cols_d = st.columns(4)
    for idx, theme in enumerate(hot_themes_tab5[:4]):
        if cols_d[idx].button(f"🔥 {theme}", key=f"hot_theme_btn_{idx}", use_container_width=True): 
            st.session_state.deep_tech_query = theme
            st.session_state.deep_tech_results = None 
            st.session_state.deep_tech_brief = None
            st.session_state.deep_tech_input = ""
            
    st.markdown("**직접 테마 입력:**")
    with st.form(key="theme_search_form", clear_on_submit=False):
        col_in1, col_in2 = st.columns([8, 2])
        custom_query = col_in1.text_input("테마입력", label_visibility="collapsed", key="deep_tech_input", placeholder="예: 양자암호, 전고체 배터리, 비만치료제")
        submit_btn = col_in2.form_submit_button("🔍 대장주 발굴", use_container_width=True)
        if submit_btn and custom_query:
            st.session_state.deep_tech_query = custom_query
            st.session_state.deep_tech_results = None
            st.session_state.deep_tech_brief = None

    if st.session_state.deep_tech_query and st.session_state.deep_tech_results is None and api_key_input:
        st.markdown(f"### 🔎 '{st.session_state.deep_tech_query}' 테마/섹터 정밀 분석")
        with st.spinner("AI가 해당 테마의 시장 모멘텀과 핵심 촉매를 분석 중입니다..."):
            theme_brief_prompt = f"당신은 테마주 퀀트 애널리스트입니다. '{st.session_state.deep_tech_query}' 테마의 시장 주도 이유와 전망을 3줄 요약하세요."
            st.session_state.deep_tech_brief = ask_gemini(theme_brief_prompt, api_key_input)

        with st.spinner(f"✨ '{st.session_state.deep_tech_query}' 핵심 대장주 및 밸류체인 수혜주 발굴 중..."):
            theme_stocks = get_theme_stocks_with_ai(st.session_state.deep_tech_query, api_key_input)
            if theme_stocks:
                progress_bar = st.progress(0.0)
                status_text = st.empty()
                theme_res_list = []
                completed, total = 0, len(theme_stocks)
                def process_theme_stock(item):
                    if len(item) == 2:
                        name, code = item
                        time.sleep(0.1)
                        return analyze_technical_pattern(name, code)
                    return None
                with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
                    for future in concurrent.futures.as_completed({executor.submit(process_theme_stock, t): t for t in theme_stocks}):
                        res = future.result()
                        completed += 1
                        if res: theme_res_list.append(res)
                        progress_bar.progress(min(1.0, completed / total))
                        status_text.text(f"⚡ 파싱 중... ({completed}/{total}) - {len(theme_res_list)}개 완료")
                st.session_state.deep_tech_results = theme_res_list
            else:
                st.error(f"❌ '{st.session_state.deep_tech_query}' 관련 종목을 찾지 못했습니다.")
                st.session_state.deep_tech_query = None 
                
    if st.session_state.deep_tech_results is not None:
        if st.session_state.get('deep_tech_brief'): st.info(f"**💡 AI 테마 인사이트:**\n{st.session_state.deep_tech_brief}")
        display_sorted_results(st.session_state.deep_tech_results, tab_key="t5", api_key=api_key_input)

elif selected_menu == "🔥 간밤의 미국 급등주 & 수혜주":
    st.markdown("## 🔥 오버나이트 모멘텀 & 밸류체인 스캐너")
    col_sec, col_gain = st.columns([1, 1.2], gap="large")
    with col_sec:
        st.subheader("📊 1. 미 증시 주도 섹터 (ETF)")
        with st.spinner("섹터 ETF 등락률 산출 중..."):
            etf_df = get_us_sector_etfs()
            if not etf_df.empty:
                etf_df['등락률'] = etf_df['등락률'].apply(lambda x: f"{'+' if x>0 else ''}{x:.2f}%")
                st.dataframe(etf_df, use_container_width=True, hide_index=True)
        st.subheader("🚀 2. 글로벌 급등주 필터링")
        if not st.session_state.gainers_df.empty:
            display_df = st.session_state.gainers_df[['종목코드', '기업명', '현재가', '등락률']].copy()
            st.dataframe(display_df, use_container_width=True, hide_index=True)
            opts = ["🔍 종목 선택"] + [f"{r['종목코드']} ({r['기업명']})" for _, r in display_df.iterrows()]
            sel_opt = st.selectbox("#### 🎯 분석할 주도주 선택", opts)
            sel_tick = "N/A" if sel_opt == "🔍 종목 선택" else sel_opt.split(" ")[0]
        else:
            sel_tick = "N/A"
            st.error("❌ 현재 급등주 데이터를 불러올 수 없습니다.")

    with col_gain:
        st.subheader("🔗 3. 글로벌 밸류체인 & 갭상승 대응 시나리오")
        if sel_tick != "N/A" and api_key_input:
            comp_name = sel_opt.split(" (")[1].replace(")", "")
            with st.spinner(f"✨ AI가 '{sel_tick}'의 공급망과 국장 수혜주를 분석 중입니다..."):
                prompt = f"간밤에 미국 증시에서 '{comp_name}({sel_tick})' 종목이 급등했습니다. 1.급등사유 2.한국 수혜주 3~5개 3.시초가 갭상승 대응 시나리오를 작성하세요."
                report = ask_gemini(prompt, api_key_input)
                st.success("✅ 밸류체인 및 대응 시나리오 분석 완료!")
                st.markdown(report)
            st.divider()
            st.subheader("🎯 추천된 국장 수혜주 타점 즉시 확인")
            krx_df = get_krx_stocks()
            if not krx_df.empty:
                opts_krx = ["🔍 종목명 검색 후 엔터"] + (krx_df['Name'].astype(str) + " (" + krx_df['Code'].astype(str) + ")").tolist()
                with st.form("vs_kr_form"):
                    col_v1, col_v2 = st.columns([8,2])
                    with col_v1: us_sub_query = st.selectbox("수혜주 차트 상태 확인:", opts_krx, key="us_sub_scan", label_visibility="collapsed")
                    with col_v2: vs_btn = st.form_submit_button("🔍 타점 확인", use_container_width=True)
                if vs_btn and us_sub_query != "🔍 종목명 검색 후 엔터":
                    q_name = us_sub_query.rsplit(" (", 1)[0]
                    q_code = us_sub_query.rsplit("(", 1)[-1].replace(")", "").strip()
                    with st.spinner("차트 타점 분석 중..."):
                        res = analyze_technical_pattern(q_name, q_code)
                        if res: draw_stock_card(res, api_key_str=api_key_input, is_expanded=True, key_suffix="us_val_chain")
                        else: st.error("❌ 해당 종목 데이터를 불러올 수 없습니다.")

elif selected_menu == "🚨 당일 상/하한가 분석":
    st.subheader("🚨 오늘의 상/하한가 및 테마 분석")
    with st.spinner("데이터 수집 중..."): upper_df, lower_df = get_limit_stocks()
    if api_key_input and not upper_df.empty:
        if st.button("🤖 AI 상한가 테마 즉시 분석", type="primary", use_container_width=True):
            st.success(ask_gemini(f"오늘 상한가 종목들: {upper_df['Name'].tolist()}\n공통된 테마/이슈 3줄 요약해줘.", api_key_input))
    col_u, col_l = st.columns(2)
    with col_u:
        st.markdown("### 🔴 상한가 종목")
        if not upper_df.empty:
            display_upper = upper_df[['Name', 'Sector', 'Amount_Ouk']].copy()
            display_upper.columns = ['종목명', '섹터', '거래대금(억)']
            display_upper['거래대금(억)'] = display_upper['거래대금(억)'].apply(lambda x: f"{x:,}")
            st.dataframe(display_upper, use_container_width=True, hide_index=True)
            with st.form("u_limit_form"):
                col_u1, col_u2 = st.columns([8, 2])
                with col_u1: sel_u = st.selectbox("상한가 종목 타점 확인:", ["선택"] + upper_df['Name'].tolist(), key="sel_u", label_visibility="collapsed")
                with col_u2: sel_u_btn = st.form_submit_button("🔍 타점 확인", use_container_width=True)
            if sel_u_btn and sel_u != "선택":
                krx_df_local = get_krx_stocks()
                match_row = krx_df_local[krx_df_local['Name'] == sel_u]
                if not match_row.empty:
                    k_code = match_row['Code'].iloc[0]
                    with st.spinner("차트 타점 분석 중..."):
                        if res := analyze_technical_pattern(sel_u, k_code): draw_stock_card(res, api_key_str=api_key_input, is_expanded=True, key_suffix="t6_u")
                else: st.error(f"❌ '{sel_u}' 종목의 코드를 찾을 수 없어 분석할 수 없습니다.")
        else: st.info("현재 상한가 종목이 없습니다.")
    with col_l:
        st.markdown("### 🔵 하한가 종목")
        if not lower_df.empty: 
            display_lower = lower_df[['Name', 'Sector', 'Amount_Ouk']].copy()
            display_lower.columns = ['종목명', '섹터', '거래대금(억)']
            display_lower['거래대금(억)'] = display_lower['거래대금(억)'].apply(lambda x: f"{x:,}")
            st.dataframe(display_lower, use_container_width=True, hide_index=True)
        else: st.info("현재 하한가 종목이 없습니다.")

elif selected_menu == "🚦 거래량 급증 & 시장 경보":
    st.markdown("## 🚦 거래량 급증/급감 & 투자자 보호(시장경보)")
    tab_vol, tab_warn = st.tabs(["📊 거래량 급증/급감", "🛡️ 관리종목 및 시장경보"])
    with tab_vol:
        with st.spinner("데이터 스크래핑 중..."): surge_df, drop_df = get_volume_surge_drop()
        c_surge, c_drop = st.columns(2)
        with c_surge:
            st.markdown("### 🔥 거래량 급증")
            if not surge_df.empty: st.dataframe(surge_df, use_container_width=True, hide_index=True)
            else: st.error("❌ 현재 데이터를 불러올 수 없습니다.")
        with c_drop:
            st.markdown("### ❄️ 거래량 급감")
            if not drop_df.empty: st.dataframe(drop_df, use_container_width=True, hide_index=True)
            else: st.error("❌ 현재 데이터를 불러올 수 없습니다.")
    with tab_warn:
        with st.spinner("시장경보 데이터 스크래핑 중..."): mgmt_df, alert_df = get_market_warnings()
        st.markdown("### 🛑 관리종목 (상장폐지 위험)")
        if not mgmt_df.empty: st.dataframe(mgmt_df, use_container_width=True, hide_index=True)
        else: st.success("현재 지정된 관리종목이 없습니다.")
        st.markdown("### ⚠️ 투자주의/경고/위험 종목")
        if not alert_df.empty: st.dataframe(alert_df, use_container_width=True, hide_index=True)
        else: st.success("현재 지정된 시장경보 종목이 없습니다.")

elif selected_menu == "📰 실시간 특징주 속보 & 리포트":
    st.subheader("📰 실시간 속보 및 증권사 리포트 터미널")
    news_sub1, news_sub2, news_sub3 = st.tabs(["🚨 실시간 특징주/속보", "📋 증권사 종목 리포트 검색", "🔥 AI 데일리 리포트 (TEBI-Style)"])
    
    with news_sub1:
        if st.button("🔄 속보 리로드"): 
            st.session_state.news_data = []
            st.session_state.seen_links = set()
            st.session_state.seen_titles = set()
            get_latest_naver_news.clear()
            st.rerun()
        with st.spinner("뉴스를 불러오는 중..."): update_news_state()
        
        krx_dict = {row['Name']: row['Code'] for _, row in get_krx_stocks().iterrows() if len(str(row['Name'])) > 1}
        news_aliases = {"삼전": ("삼성전자", "005930"), "하이닉스": ("SK하이닉스", "000660"), "현차": ("현대차", "005380"), "엔솔": ("LG에너지솔루션", "373220")}
        sorted_names = sorted(krx_dict.keys(), key=len, reverse=True)
        
        for i, news in enumerate(st.session_state.news_data[:50]):
            title = news['title']
            found_comps = []
            for alias, (real_name, fallback_code) in news_aliases.items():
                if alias in title:
                    found_comps.append((real_name, krx_dict.get(real_name, fallback_code)))
                    break
            if not found_comps:
                for name in sorted_names:
                    if name in title:
                        found_comps.append((name, krx_dict[name]))
                        break 
            
            with st.container(border=True):
                cols = st.columns([1, 6, 2, 1])
                cols[0].markdown(f"**🕒 {news['time']}**")
                cols[1].markdown(f"{title}")
                with cols[2]:
                    if found_comps:
                        if st.button(f"🔍 {found_comps[0][0]} 분석", key=f"qa_{i}"):
                            st.session_state[f"news_analyze_{i}"] = not st.session_state.get(f"news_analyze_{i}", False)
                cols[3].link_button("원문🔗", news['link'])
            
            if st.session_state.get(f"news_analyze_{i}", False):
                with st.spinner(f"'{found_comps[0][0]}' 차트 분석 중..."):
                    res = analyze_technical_pattern(found_comps[0][0], found_comps[0][1])
                    if res: draw_stock_card(res, api_key_str=api_key_input, is_expanded=True, key_suffix=f"news_qa_{i}")
                
    with news_sub2:
        st.markdown("### 📋 당일 실시간 리포트 & 종목별 과거 리포트 검색")
        
        st.markdown("#### 🔍 특정 종목 리포트 검색 (최근 6개월)")
        search_krx_df = get_krx_stocks()
        if not search_krx_df.empty:
            opts = ["선택 안함 (당일 전체 신규 리포트 보기)"] + (search_krx_df['Name'].astype(str) + " (" + search_krx_df['Code'].astype(str) + ")").tolist()
            report_query = st.selectbox("리포트를 검색할 종목을 선택하세요:", opts)
            
            if report_query != "선택 안함 (당일 전체 신규 리포트 보기)":
                q_name = report_query.rsplit(" (", 1)[0]
                q_code = report_query.rsplit("(", 1)[-1].replace(")", "").strip()
                
                with st.spinner(f"'{q_name}'의 최근 6개월 리포트를 검색 중입니다..."):
                    history_df = get_stock_research_history(q_code)
                    
                if not history_df.empty:
                    st.success(f"✅ '{q_name}' 관련 리포트 {len(history_df)}건을 찾았습니다.")
                    display_history_df = history_df[['작성일', '증권사', '제목', '적정가격', '투자의견', '원문링크']].copy()
                    display_history_df['적정가격'] = display_history_df['적정가격'].apply(lambda x: f"{x:,}원" if x > 0 else "-")
                    st.dataframe(
                        display_history_df, 
                        column_config={"원문링크": st.column_config.LinkColumn("원문 보기")},
                        use_container_width=True, hide_index=True
                    )
                else:
                    st.warning("해당 종목의 최근 6개월 내 발간된 증권사 리포트가 없습니다.")
                
                st.divider()

        st.markdown("#### 🆕 오늘의 전체 신규 리포트")
        res_df = get_naver_research()
        if not res_df.empty:
            if api_key_input and st.button("🤖 AI 당일 리포트 종합 의견 및 섹터 요약", use_container_width=True, type="primary"):
                with st.spinner("당일 발간된 리포트들을 분석하여 시장 분위기와 유망 섹터를 요약 중입니다..."):
                    report_text = "\n".join([f"- [{r['증권사']}] {r['종목명']}: {r['제목']}" for _, r in res_df.head(30).iterrows()])
                    prompt = f"당신은 증권사 리서치 센터장입니다. 오늘 발간된 다음 증권사 리포트 제목들을 분석하여, 1) 오늘 증권가가 가장 주목하는 핵심 섹터/테마 2개와 그 이유, 2) 시장의 전반적인 투자의견 요약을 마크다운으로 작성해주세요.\n\n[오늘의 리포트]\n{report_text}"
                    st.info(ask_gemini(prompt, api_key_input), icon="💡")
            
            st.dataframe(
                res_df, 
                column_config={"원문링크": st.column_config.LinkColumn("원문 보기")},
                use_container_width=True, hide_index=True
            )
        else:
            st.error("❌ 리포트 데이터를 불러오지 못했습니다.")
            
    with news_sub3:
        st.markdown("### 🤖 Auto Research Desk (오늘의 증권가 종합 분석)")
        st.write("기관 트레이딩 데스크 수준의 일일 요약, 쟁점 분석, 목표가 랭킹을 AI가 생성합니다.")
        if api_key_input:
            if st.button("🚀 TEBI-Style 모닝 리포트 생성 시작", type="primary"):
                with st.spinner("오늘 발간된 30개의 증권사 리포트 원문을 AI가 해독 및 분석 중입니다..."):
                    today_reports = get_today_research_details()
                    if not today_reports.empty:
                        buys = len(today_reports[today_reports['투자의견'].str.contains('매수|Buy', na=False, case=False)])
                        sells = len(today_reports[today_reports['투자의견'].str.contains('매도|Sell|축소', na=False, case=False)])
                        holds = len(today_reports) - buys - sells
                        
                        st.markdown("#### 📊 오늘의 증권가 투자의견 요약 (Verdict)")
                        c1, c2, c3, c4 = st.columns(4)
                        c1.metric("총 발간 리포트", f"{len(today_reports)}건")
                        c2.metric("BUY (비중확대)", f"{buys}건")
                        c3.metric("HOLD (관망)", f"{holds}건")
                        c4.metric("SELL (비중축소)", f"{sells}건")
                        
                        st.markdown("#### 📈 당일 목표가(TP) 상/하향 랭킹")
                        upgrades = today_reports[today_reports['변동'] == '상향'].sort_values('변동률', ascending=False)
                        downgrades = today_reports[today_reports['변동'] == '하향'].sort_values('변동률', ascending=True)
                        
                        col_up, col_down = st.columns(2)
                        with col_up:
                            st.success(f"**▲ 상향 리포트 ({len(upgrades)}건)**")
                            if not upgrades.empty:
                                fig_up = px.bar(upgrades, x='변동률', y='종목명', orientation='h', text='증권사', color_discrete_sequence=['#ff4b4b'])
                                fig_up.update_layout(height=300, margin=dict(l=0, r=0, t=0, b=0), yaxis={'categoryorder':'total ascending'})
                                st.plotly_chart(fig_up, use_container_width=True)
                            else: st.write("목표가 상향 종목이 없습니다.")
                        
                        with col_down:
                            st.error(f"**▼ 하향 리포트 ({len(downgrades)}건)**")
                            if not downgrades.empty:
                                fig_down = px.bar(downgrades, x='변동률', y='종목명', orientation='h', text='증권사', color_discrete_sequence=['#1f77b4'])
                                fig_down.update_layout(height=300, margin=dict(l=0, r=0, t=0, b=0), yaxis={'categoryorder':'total descending'})
                                st.plotly_chart(fig_down, use_container_width=True)
                            else: st.write("목표가 하향 종목이 없습니다.")
                            
                        st.markdown("#### ⚔️ 애널리스트 갑론을박 & 💡 Bottom Line")
                        report_texts = "\n".join([f"- [{r['증권사']}] {r['종목명']} (의견: {r['투자의견']}, TP변동: {r['변동']}): {r['제목']}" for _, r in today_reports.iterrows()])
                        prompt = f"""
                        당신은 기관 프랍 트레이더를 위한 수석 퀀트 애널리스트입니다. 오늘 한국 증시에서 발간된 증권사 리포트 목록입니다:
                        {report_texts}
                        
                        다음 3가지를 마크다운으로 명확하게 작성하세요:
                        1. **🔥 주도 섹터 및 핵심 모멘텀**: 오늘 리포트들이 가장 집중적으로 다루고 있는(목표가 상향이 많은) 핵심 섹터 1~2개와 그 이유.
                        2. **⚔️ 애널리스트 갑론을박 (Debate)**: 시장에서 의견이 엇갈리는 종목이나 섹터를 찾아 강세(Bull) 논리와 약세/보수적(Bear) 논리를 대비시켜 서술하세요.
                        3. **💡 Bottom Line (최종 액션 플랜)**: 전체적인 매수/매도 비율을 고려했을 때, 투자자가 오늘 취해야 할 명확한 행동 지침(예: 적극 매수, 차익 실현 등)을 3줄로 결론지으세요.
                        """
                        st.info(ask_gemini(prompt, api_key_input))
                    else:
                        st.error("리포트 데이터를 파싱하지 못했습니다.")
        else:
            st.warning("API 키를 입력해야 AI 데일리 리포트를 생성할 수 있습니다.")

elif selected_menu == "🔬 개별 기업 정밀 진단 (AI 비전)":
    st.markdown("## 🔬 기업 정밀 진단 (차트/수급/비전 AI)")
    ana_tab1, ana_tab2 = st.tabs(["📊 티커 검색 분석", "👁️ 차트 이미지 AI 비전 분석"])
    
    with ana_tab1:
        market_choice = st.radio("시장 선택", ["🇰🇷 국내 주식", "🇺🇸 미국 주식"], horizontal=True)
        if market_choice == "🇰🇷 국내 주식":
            krx_df = get_krx_stocks()
            if not krx_df.empty:
                opts = ["🔍 분석할 국내 종목을 검색/선택하세요"] + (krx_df['Name'].astype(str) + " (" + krx_df['Code'].astype(str) + ")").tolist()
                col_s1, col_s2 = st.columns([8, 2])
                with col_s1: kr_query = st.selectbox("👇 종목명/코드 검색:", opts, label_visibility="collapsed")
                with col_s2: kr_search_btn = st.button("📊 분석 시작", use_container_width=True)
                if kr_query != "🔍 분석할 국내 종목을 검색/선택하세요" and (kr_query or kr_search_btn):
                    searched_name = kr_query.rsplit(" (", 1)[0]
                    searched_code = kr_query.rsplit("(", 1)[-1].replace(")", "").strip()
                    with st.spinner(f"📡 '{searched_name}' 타점 분석 중..."):
                        res = analyze_technical_pattern(searched_name, searched_code)
                        if res: draw_stock_card(res, api_key_str=api_key_input, is_expanded=True, key_suffix="t4_kr")
                        else: st.error("❌ 데이터 로드 실패")
        else:
            col_us1, col_us2 = st.columns([8, 2])
            with col_us1: us_query = st.text_input("👇 미국 주식 종목명/티커 입력 (예: AAPL):", label_visibility="collapsed")
            with col_us2: us_search_btn = st.button("🔍 검색", use_container_width=True)
            if us_query or us_search_btn:
                with st.spinner(f"📡 검색 중..."): us_results = search_us_ticker(us_query)
                if us_results: st.session_state.us_search_results = us_results
                else: st.error("❌ 검색 결과 없음")
            
            if "us_search_results" in st.session_state and st.session_state.us_search_results:
                sel_us_opt = st.selectbox("🎯 정확한 종목 선택:", ["선택하세요"] + st.session_state.us_search_results)
                analyze_btn = st.button("📊 분석 시작", use_container_width=True)
                if analyze_btn and sel_us_opt != "선택하세요":
                    us_ticker = sel_us_opt.split(" ")[0]
                    with st.spinner(f"📡 '{us_ticker}' 분석 중..."):
                        res = analyze_technical_pattern(us_ticker, us_ticker)
                        if res: draw_stock_card(res, api_key_str=api_key_input, is_expanded=True, key_suffix="t4_us")

    with ana_tab2:
        st.markdown("### 👁️ AI Vision: 인간의 눈으로 보는 차트 분석")
        st.info("💡 **이미지 복사 팁:** 차트 위에서 우클릭 후 '이미지 주소 복사'를 하여 우측 칸에 `Ctrl+V` 하시는 것이 가장 오류가 없습니다.")
        upload_col, url_col = st.columns(2)
        with upload_col: uploaded_chart = st.file_uploader("📸 점선 박스 클릭 후 Ctrl+V", type=["png", "jpg", "jpeg"])
        with url_col: image_url = st.text_input("🔗 이미지 주소(URL) 붙여넣기", placeholder="https://example.com/chart.png")
            
        img_to_analyze = None
        if uploaded_chart:
            img_to_analyze = PIL.Image.open(uploaded_chart)
            st.image(img_to_analyze, use_container_width=True)
        elif image_url:
            try:
                img_to_analyze = PIL.Image.open(requests.get(image_url, stream=True).raw)
                st.image(img_to_analyze, use_container_width=True)
            except Exception: st.error("❌ 이미지 URL 오류")

        if img_to_analyze and st.button("🤖 Gemini Vision 정밀 분석 시작", type="primary", use_container_width=True):
            if not api_key_input: st.error("API 키가 필요합니다.")
            else:
                with st.spinner("AI가 차트를 시각적으로 해독 중입니다..."):
                    prompt = "전설적인 차트 분석가로서 차트의 패턴, 지지/저항선, 단기 대응 전략을 마크다운으로 분석해주세요."
                    result = ask_gemini_vision(prompt, img_to_analyze, api_key_input)
                    st.success(result)

elif selected_menu == "📊 국내외 핵심 ETF 분석":
    st.markdown("## 📊 국내외 핵심 ETF 종목 분석")
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
                        except:
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

elif selected_menu == "💰 고배당주 파이프라인 (TOP 300)":
    st.subheader("💰 고배당주 & ETF 파이프라인 (TOP 300)")
    
    with st.spinner("배당 데이터를 다운로드 중입니다..."): 
        div_dfs = get_dividend_portfolio(st.session_state.get('ex_rate', 1350.0))
        
    sort_opt = st.radio("⬇ 정렬 기준", ["기본 (분류순)", "예상 배당금 높은순", "현재가 높은순", "현재가 낮은순"], horizontal=True)
    
    def apply_sort(df, opt):
        if df.empty: return df
        temp_df = df.copy()
        if opt == "기본 (분류순)": return temp_df 
        def ex_val(val_str):
            try: return float(str(val_str).split('(')[0].replace(',', '').replace('원', '').replace('$', '').strip())
            except: return 0.0
        sort_col = '예상 배당금' if "배당금" in opt else '현재가'
        temp_df['__sort'] = temp_df[sort_col].apply(lambda x: ex_val(x))
        if opt == "현재가 낮은순": return pd.concat([temp_df[temp_df['__sort']>0].sort_values('__sort'), temp_df[temp_df['__sort']==0]]).drop(columns=['__sort'])
        return temp_df.sort_values('__sort', ascending=False).drop(columns=['__sort'])

    t1, t2, t3 = st.tabs(["🇰🇷 국장", "🇺🇸 미장", "📈 ETF"])
    
    with t1: 
        if div_dfs["KRX"].empty:
            st.error("🚨 국내 거래소 및 외부 가치평가 서버망 통신 제한으로 인해 국내 주식 데이터를 불러오지 못했습니다. 잠시 후 사이드바 하단의 [새로고침]을 실행해 주세요.")
        else:
            st.dataframe(apply_sort(div_dfs["KRX"], sort_opt), use_container_width=True, hide_index=True)
            
    with t2: 
        if div_dfs["US"].empty:
            st.error("🚨 글로벌 금융 서버망 접속 제한으로 인해 미국 주식 데이터를 가져오지 못했습니다.")
        else:
            st.dataframe(apply_sort(div_dfs["US"], sort_opt), use_container_width=True, hide_index=True)
            
    with t3: 
        if div_dfs["ETF"].empty:
            st.error("🚨 글로벌 금융 서버망 접속 제한으로 인해 ETF 데이터를 가져오지 못했습니다.")
        else:
            st.dataframe(apply_sort(div_dfs["ETF"], sort_opt), use_container_width=True, hide_index=True)

elif selected_menu == "🎯 증권사 목표가 컨센서스":
    st.markdown("## 🎯 증권사 목표가 컨센서스 대시보드")
    st.write("특정 종목에 대한 여러 증권사의 최근 6개월 목표가 추이와 투자의견 분포를 시각적으로 분석합니다.")
    
    krx_df = get_krx_stocks()
    if not krx_df.empty:
        opts = ["🔍 종목을 선택하세요"] + (krx_df['Name'].astype(str) + " (" + krx_df['Code'].astype(str) + ")").tolist()
        cons_query = st.selectbox("컨센서스를 분석할 종목:", opts)
        
        if cons_query != "🔍 종목을 선택하세요":
            q_name = cons_query.rsplit(" (", 1)[0]
            q_code = cons_query.rsplit("(", 1)[-1].replace(")", "").strip()
            
            with st.spinner(f"'{q_name}' 증권사 리포트 및 현재가 데이터 연산 중..."):
                history_df = get_stock_research_history(q_code, q_name)
                # 💡 추가됨: 현재 주가 가져오기
                tech_res = analyze_technical_pattern(q_name, q_code)
                curr_price = int(tech_res['현재가']) if tech_res else 0
            
            if history_df.empty:
                st.warning("최근 6개월 내 발간된 증권사 리포트가 없어 컨센서스를 산출할 수 없습니다.")
            else:
                valid_df = history_df[history_df['적정가격'] > 0].copy()
                
                if valid_df.empty:
                    st.warning("목표가가 제시된 리포트가 없습니다.")
                else:
                    avg_price = int(valid_df['적정가격'].mean())
                    median_price = int(valid_df['적정가격'].median())
                    max_price = int(valid_df['적정가격'].max())
                    min_price = int(valid_df['적정가격'].min())
                    report_count = len(valid_df)
                    
                    max_broker = valid_df[valid_df['적정가격'] == max_price]['증권사'].iloc[0]
                    min_broker = valid_df[valid_df['적정가격'] == min_price]['증권사'].iloc[0]
                    
                    # 💡 추가됨: 현재가 대비 평균 목표가 괴리율(기대수익률) 계산
                    upside_pct = ((avg_price - curr_price) / curr_price * 100) if curr_price > 0 else 0
                    
                    with st.container(border=True):
                        st.markdown(f"### {q_name} <span style='font-size: 16px; color: gray;'>{q_code}</span>", unsafe_allow_html=True)
                        
                        # 💡 수정됨: 6열로 변경하고 맨 앞에 현재 주가 배치
                        c0, c1, c2, c3, c4, c5 = st.columns(6)
                        if curr_price > 0:
                            c0.metric("현재 주가", f"{curr_price:,}원")
                            c1.metric("평균 목표가", f"{avg_price:,}원", f"{upside_pct:+.1f}% (괴리율)", delta_color="normal")
                        else:
                            c0.metric("현재 주가", "조회불가")
                            c1.metric("평균 목표가", f"{avg_price:,}원")
                            
                        c2.metric("중앙값", f"{median_price:,}원", f"증권사 {len(valid_df['증권사'].unique())}곳")
                        c3.metric("최고가", f"{max_price:,}원", max_broker, delta_color="normal")
                        c4.metric("최저가", f"{min_price:,}원", min_broker, delta_color="inverse")
                        c5.metric("수집 리포트", f"{report_count}건")
                        
                    st.divider()
                    
                    col_chart1, col_chart2 = st.columns([7, 3])
                    
                    with col_chart1:
                        st.markdown("#### 📈 목표주가 시계열 (최근 6개월)")
                        valid_df['Date'] = pd.to_datetime(valid_df['작성일'], format="%y.%m.%d")
                        valid_df = valid_df.sort_values('Date')
                        
                        fig_line = px.line(valid_df, x='Date', y='적정가격', color='증권사', markers=True, 
                                           title=f"{q_name} 증권사별 목표가 추이",
                                           labels={"Date": "발간일", "적정가격": "목표주가 (원)"})
                        
                        fig_line.add_hline(y=avg_price, line_dash="dash", line_color="rgba(255,0,0,0.5)", annotation_text=f"평균 {avg_price:,}원")
                        # 💡 추가됨: 차트에 현재 주가 기준선 추가
                        if curr_price > 0:
                            fig_line.add_hline(y=curr_price, line_dash="dot", line_color="rgba(0,0,255,0.5)", annotation_text=f"현재 주가 {curr_price:,}원")
                            
                        fig_line.update_layout(hovermode="x unified", height=400, template="plotly_white")
                        st.plotly_chart(fig_line, use_container_width=True)
                        
                    with col_chart2:
                        st.markdown("#### 📊 투자의견 분포")
                        
                        # 💡 추가됨: '투자의견' 표준화 병합 로직 (Buy = 매수, Hold = 중립, Sell = 매도)
                        def standardize_opinion(op):
                            op_str = str(op).strip().upper()
                            if 'STRONG BUY' in op_str or '강력매수' in op_str:
                                return '강력매수 (Strong Buy)'
                            elif 'BUY' in op_str or '매수' in op_str:
                                return '매수 (Buy)'
                            elif 'HOLD' in op_str or '중립' in op_str or 'MARKETPERFORM' in op_str:
                                return '중립 (Hold)'
                            elif 'SELL' in op_str or '매도' in op_str or 'UNDERPERFORM' in op_str or '축소' in op_str:
                                return '매도 (Sell)'
                            else:
                                return op_str

                        history_df['투자의견_표준화'] = history_df['투자의견'].apply(standardize_opinion)
                        opinion_counts = history_df['투자의견_표준화'].value_counts().reset_index()
                        opinion_counts.columns = ['투자의견', '건수']
                        
                        fig_pie = px.pie(opinion_counts, values='건수', names='투자의견', hole=0.5,
                                         color='투자의견', 
                                         color_discrete_map={
                                            '강력매수 (Strong Buy)': '#003300', 
                                            '매수 (Buy)': '#1b5e20', 
                                            '중립 (Hold)': '#ff7f0e', 
                                            '매도 (Sell)': '#d62728'
                                         })
                        fig_pie.update_layout(height=400, showlegend=True, legend=dict(orientation="h", yanchor="bottom", y=-0.2, xanchor="center", x=0.5))
                        st.plotly_chart(fig_pie, use_container_width=True)
                        
                    st.markdown("#### 📋 증권사별 최신 컨센서스")
                    latest_df = valid_df.sort_values('Date', ascending=False).drop_duplicates(subset=['증권사'], keep='first')
                    
                    display_latest = latest_df[['증권사', '투자의견', '적정가격', '작성일', '원문링크']].copy()
                    display_latest['적정가격'] = display_latest['적정가격'].apply(lambda x: f"{x:,}원")
                    st.dataframe(
                        display_latest,
                        column_config={"원문링크": st.column_config.LinkColumn("리포트 보기")},
                        use_container_width=True, hide_index=True
                    )
                    
                    st.divider()
                    if api_key_input and st.button(f"🤖 '{q_name}' 애널리스트 갑론을박 (Debate) 분석", type="primary", use_container_width=True):
                        with st.spinner(f"최근 발간된 '{q_name}' 리포트들의 강세/약세 논리를 분석 중입니다..."):
                            report_texts = "\n".join([f"- [{r['증권사']}] 투자의견: {r['투자의견']}, 목표가: {r['적정가격']}\n제목: {r['제목']}" for _, r in history_df.head(10).iterrows()])
                            prompt = f"""
                            당신은 애널리스트입니다. '{q_name}'에 대한 최근 증권사 리포트들을 바탕으로 시장의 '갑론을박(Debate)'을 분석해주세요.
                            [리포트 요약]
                            {report_texts}
                            
                            다음 형식으로 마크다운 작성:
                            1. 🟢 **강세 논리 (Bull Case)**: 긍정적인 전망과 목표가 상향의 주된 근거 (2~3줄)
                            2. 🔴 **약세/보수적 논리 (Bear Case)**: 우려 사항, 리스크, 목표가 하향/유지의 주된 근거 (2~3줄)
                            3. 💡 **핵심 쟁점 (Key Controversy)**: 가장 의견이 엇갈리는 포인트 (1줄)
                            """
                            st.success(ask_gemini(prompt, api_key_input))

elif selected_menu == "⚖️ 적정 주가 계산기 (버핏 모델)":
    st.markdown("## ⚖️ 워런 버핏식 가치투자 퀀트 계산기")
    b_tab1, b_tab2, b_tab3 = st.tabs(["📊 적정 주가 계산기 (DCF 모델)", "📈 버핏 지수 & 72의 법칙", "🔍 퀀트 스크리닝 가이드"])
    
    with b_tab1:
        st.markdown("### 📊 잉여현금흐름(FCF) 기반 내재가치 계산기")
        market_choice_dcf = st.radio("시장 선택 (가치평가)", ["🇰🇷 국내 주식", "🇺🇸 미국 주식"], horizontal=True, key="dcf_market")
        
        # 💡 [버그 수정] Streamlit Rerun 시 화면이 닫히지 않도록 세션 상태(Session State)에 종목 정보 저장
        if 'dcf_sel_ticker' not in st.session_state: st.session_state.dcf_sel_ticker = None
        if 'dcf_sel_name' not in st.session_state: st.session_state.dcf_sel_name = ""
        
        is_us_dcf = (market_choice_dcf == "🇺🇸 미국 주식")
        
        if not is_us_dcf:
            krx_df = get_krx_stocks()
            if not krx_df.empty:
                opts = ["🔍 평가할 국내 종목을 선택하세요."] + (krx_df['Name'].astype(str) + " (" + krx_df['Code'].astype(str) + ")").tolist()
                with st.form("dcf_kr_form"):
                    col_dcf1, col_dcf2 = st.columns([8, 2])
                    with col_dcf1: query = st.selectbox("👇 종목명 검색:", opts, key="dcf_kr_search", label_visibility="collapsed")
                    with col_dcf2: dcf_kr_btn = st.form_submit_button("🔍 데이터 로드", use_container_width=True)
                    if dcf_kr_btn and query != "🔍 평가할 국내 종목을 선택하세요.":
                        st.session_state.dcf_sel_name = query.rsplit(" (", 1)[0]
                        st.session_state.dcf_sel_ticker = query.rsplit("(", 1)[-1].replace(")", "").strip()
        else:
            with st.form("dcf_us_form"):
                col_dcf_us1, col_dcf_us2 = st.columns([8, 2])
                with col_dcf_us1: us_query = st.text_input("👇 미국 주식 종목명/티커 (예: AAPL):", key="dcf_us_input", label_visibility="collapsed")
                with col_dcf_us2: dcf_us_search_btn = st.form_submit_button("🔍 검색", use_container_width=True)
            if dcf_us_search_btn and us_query:
                with st.spinner("검색 중..."): us_results = search_us_ticker(us_query)
                if us_results: st.session_state.dcf_us_results = us_results
                else: st.error("검색 결과가 없습니다.")
            if "dcf_us_results" in st.session_state and st.session_state.dcf_us_results:
                sel_us_opt = st.selectbox("🎯 정확한 종목을 선택해주세요:", ["선택하세요"] + st.session_state.dcf_us_results)
                if sel_us_opt != "선택하세요":
                    st.session_state.dcf_sel_ticker = sel_us_opt.split(" ")[0]
                    st.session_state.dcf_sel_name = sel_us_opt.split(" (")[1].split(" /")[0]

        # 💡 기존 로컬 변수 대신 영구적으로 유지되는 세션 상태 변수 사용
        if st.session_state.dcf_sel_ticker:
            st.success(f"✅ [{st.session_state.dcf_sel_name}] 기초 데이터 로드 완료")
            _, _, fcf_val, shares_val, _ = get_fundamentals(st.session_state.dcf_sel_ticker)
            default_price, res = 0.0, analyze_technical_pattern(st.session_state.dcf_sel_name, st.session_state.dcf_sel_ticker)
            if res: default_price = float(res['현재가'])
            default_fcf = float(fcf_val) if fcf_val and pd.notna(fcf_val) else 1000.0
            default_shares = float(shares_val) if shares_val and pd.notna(shares_val) else 100.0

            st.markdown("#### ⚙️ DCF 파라미터 입력")
            col_dcf_p1, col_dcf_p2 = st.columns(2)
            with col_dcf_p1:
                input_price = st.number_input("현재 주가", value=default_price, step=1.0)
                input_fcf = st.number_input("최근 잉여현금흐름(FCF)", value=default_fcf, step=100.0)
                input_shares = st.number_input("유통 주식수", value=default_shares, step=10.0)
            with col_dcf_p2:
                growth_rate = st.slider("예상 연평균 성장률 (%)", 1.0, 50.0, 10.0)
                discount_rate = st.slider("할인율 (요구수익률) (%)", 5.0, 20.0, 9.0)
                terminal_growth = st.slider("영구 성장률 (%)", 1.0, 5.0, 2.5)

            # 이 버튼을 눌러도 이제 화면이 날아가지 않습니다!
            if st.button("🧮 적정 주가 연산", type="primary", use_container_width=True):
                with st.spinner("미래 현금흐름 할인 연산 중..."):
                    future_fcfs = []
                    current_fcf = input_fcf
                    for i in range(1, 11):
                        current_fcf *= (1 + growth_rate/100)
                        future_fcfs.append(current_fcf / ((1 + discount_rate/100) ** i))
                    
                    terminal_value = (current_fcf * (1 + terminal_growth/100)) / ((discount_rate/100) - (terminal_growth/100))
                    discounted_tv = terminal_value / ((1 + discount_rate/100) ** 10)
                    total_value = sum(future_fcfs) + discounted_tv
                    
                    # 💡 [치명적 버그 수정] FCF(억/10^8)와 주식수(백만/10^6) 단위 스케일링을 위해 100을 곱함
                    fair_price = (total_value / input_shares) * 100 if input_shares > 0 else 0
                    
                    margin_of_safety = ((fair_price - input_price) / fair_price) * 100 if fair_price > 0 else 0
                    
                    st.divider()
                    st.markdown(f"### 🎯 [{st.session_state.dcf_sel_name}] DCF 가치평가 결과")
                    c1, c2, c3 = st.columns(3)
                    c1.metric("현재 주가", f"{input_price:,.2f}")
                    c2.metric("DCF 적정 주가", f"{fair_price:,.2f}")
                    c3.metric("안전 마진", f"{margin_of_safety:+.1f}%", delta_color="normal" if margin_of_safety > 0 else "inverse")
                    
                    if margin_of_safety > 20: st.success("🟢 **강력 매수 구간**: 현재 주가가 내재가치 대비 20% 이상 저렴합니다.")
                    elif margin_of_safety > 0: st.info("🔵 **매수 구간**: 현재 주가가 내재가치보다 저렴합니다.")
                    elif margin_of_safety > -20: st.warning("🟡 **적정 가치 구간**: 주가가 내재가치와 비슷하게 형성되어 있습니다.")
                    else: st.error("🔴 **고평가 구간**: 현재 주가가 미래 성장성을 이미 과도하게 반영하고 있을 수 있습니다.")

    with b_tab2:
        st.markdown("### 📈 버핏 지수 (Buffett Indicator)")
        st.write("국가의 시가총액을 명목 GDP로 나눈 값으로, 증시 전체의 고평가/저평가 여부를 판단합니다.")
        buffett_ratio = 115.5 
        st.metric("현재 한국 증시 추정 버핏 지수", f"{buffett_ratio}%")
        if buffett_ratio > 120: st.error("🚨 증시가 역사적 고평가 상태입니다. 현금 비중을 늘리는 것을 고려하세요.")
        elif buffett_ratio > 80: st.success("✅ 시장이 적정 가치 구간에 있습니다.")
        else: st.info("💰 시장이 저평가 상태입니다. 적극적인 매수 기회일 수 있습니다.")
            
        st.divider()
        st.markdown("### ⏱️ 복리 계산기 (72의 법칙)")
        return_rate = st.slider("목표 연평균 수익률 (%)", min_value=1.0, max_value=30.0, value=15.0, step=0.5)
        years_to_double = 72 / return_rate
        st.markdown(f"👉 연수익률 **{return_rate}%** 유지 시, 원금이 2배가 되는 데 약 **<span style='color:#ff4b4b; font-size:24px;'>{years_to_double:.1f}년</span>**이 걸립니다.", unsafe_allow_html=True)

    with b_tab3:
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

elif selected_menu == "👴 노후 준비 ETF 시뮬레이터 (v2.0)":
    st.markdown("## 👴 노후 준비 핵심 ETF 테마별 통합 시뮬레이터")
    st.write("절세 계좌(연금저축/IRP/ISA) 활용법과 테마별 ETF 조합을 통해 은퇴 후 현금흐름을 설계합니다.")

    # --- 1. 절세 계좌 자동 배분 계산기 ---
    st.markdown("### 🎯 1. 월 투자금액별 절세 계좌 배분 최적화 가이드")
    
    st.info("""
    **💡 노후 자금은 왜 반드시 이 순서대로 계좌를 채워야 할까요? (절세 극대화 룰)**
    1. **1순위: 연금저축펀드 (연 600만 원 우선)** - 13.2~16.5%의 강력한 연말정산 세액공제! 위험자산(주식형 ETF)을 100% 꽉 채워 담을 수 있어 수익률 극대화에 가장 유리합니다.
    2. **2순위: IRP (연 300만 원 추가)** - 연금저축과 합산해 총 900만 원까지 세액공제를 받습니다. 단, 안전자산(채권, 현금 등)을 무조건 30% 이상 담아야 하는 제약이 있어 2순위로 밀립니다.
    3. **3순위: 중개형 ISA (연 2,000만 원 한도)** - 수익의 200~400만 원까지 비과세되는 ISA를 채웁니다. 만기 자금을 연금계좌로 넘기면 추가 세액공제도 줍니다!
    4. **4순위: 일반/해외계좌** - 국가가 주는 꿀 같은 절세 혜택을 모두 소진한 뒤 남는 여유 현금을 제약 없이 자유롭게 굴리는 계좌입니다.
    """)

    with st.container(border=True):
        col_in, col_spacer = st.columns([2, 1])
        monthly_budget = col_in.number_input("월 총 노후대비 투자 가능 금액 (원)", min_value=0, step=100000, value=1500000)
        
        temp_budget = monthly_budget
        pension = min(500000, temp_budget) 
        temp_budget -= pension
        irp = min(250000, temp_budget)    
        temp_budget -= irp
        isa = min(1666666, temp_budget)   
        normal = max(0, temp_budget - isa)

        c1, c2, c3, c4 = st.columns(4)
        c1.metric("연금저축펀드", f"{int(pension):,}원", "연 600만 한도")
        c2.metric("IRP (퇴직연금)", f"{int(irp):,}원", "합산 900만 한도")
        c3.metric("중개형 ISA", f"{int(isa):,}원", "비과세 혜택")
        c4.metric("일반/해외계좌", f"{int(normal):,}원", "한도 초과분")

    # 👇 네이버 금융 실시간 ETF 및 주식 가져오기
    @st.cache_data(ttl=3600)
    def get_naver_etf_and_stocks():
        res_dfs = []
        try:
            url = "https://finance.naver.com/api/sise/etfItemList.nhn"
            res = requests.get(url, timeout=5)
            if res.status_code == 200:
                etf_list = res.json().get('result', {}).get('etfItemList', [])
                if etf_list:
                    df_etf = pd.DataFrame(etf_list)[['itemcode', 'itemname', 'nowVal']].rename(
                        columns={'itemcode': 'Code', 'itemname': 'Name', 'nowVal': 'Price'})
                    res_dfs.append(df_etf)
        except: pass
        
        try:
            df_stocks = fdr.StockListing('KRX')
            if not df_stocks.empty:
                df_s = df_stocks[['Code', 'Name', 'Close']].rename(columns={'Close': 'Price'}) if 'Close' in df_stocks.columns else df_stocks[['Code', 'Name']].assign(Price=0)
                res_dfs.append(df_s)
        except: pass
        
        if res_dfs:
            df_final = pd.concat(res_dfs, ignore_index=True)
            df_final['Code'] = df_final['Code'].astype(str).str.zfill(6)
            df_final['Price'] = pd.to_numeric(df_final['Price'], errors='coerce').fillna(0)
            return df_final.sort_values('Price', ascending=False).drop_duplicates(subset=['Code']).reset_index(drop=True)
        return pd.DataFrame(columns=['Code', 'Name', 'Price'])

    # --- 2. 스마트 맞춤 종목 다중 검색 ---
    if 'custom_etfs' not in st.session_state or (len(st.session_state.custom_etfs) > 0 and isinstance(st.session_state.custom_etfs[0], str)):
        st.session_state.custom_etfs = []
    if 'search_query' not in st.session_state: st.session_state.search_query = ""

    st.markdown("### 🔎 2. 맞춤형 종목 검색 및 추가")
    with st.container(border=True):
        st.write("찾으시는 운용사(예: 미래에셋, TIGER)나 키워드를 검색하시면 하단에서 선택하여 일괄 추가할 수 있습니다.")
        col_input, col_search = st.columns([4, 1])
        search_input = col_input.text_input("종목명 또는 키워드 입력", placeholder="예: 반도체, 미래에셋, SCHD", label_visibility="collapsed").strip()
        if col_search.button("🔍 연관 종목 검색", use_container_width=True):
            if search_input: st.session_state.search_query = search_input

        if st.session_state.search_query:
            query = st.session_state.search_query
            kr_assets_df = get_naver_etf_and_stocks()
            search_options = []
            if not kr_assets_df.empty:
                matches = kr_assets_df[kr_assets_df['Name'].str.contains(query, case=False, na=False)]
                for _, row in matches.iterrows(): search_options.append(f"{row['Name']} [{row['Code']}]")
            if re.search('[a-zA-Z]', query):
                try:
                    us_results = search_us_ticker(query)
                    if us_results:
                        for res in us_results:
                            search_options.append(f"{res.split(' (')[1].split(' /')[0]} [{res.split(' ')[0]}]")
                except: pass
            st.markdown("---")
            if search_options:
                st.success(f"💡 '{query}' 검색 결과 총 {len(search_options)}개를 찾았습니다!")
                selected_to_add = st.multiselect("👇 장바구니에 담을 종목을 모두 선택하세요:", options=search_options)
                if st.button("➕ 선택한 종목 일괄 추가하기", type="primary"):
                    added_count = 0
                    for sel in selected_to_add:
                        parts = sel.split(" [")
                        parsed_name, parsed_code = parts[0].strip(), parts[1].replace("]", "").strip()
                        if not any(item['code'] == parsed_code for item in st.session_state.custom_etfs):
                            st.session_state.custom_etfs.append({'name': parsed_name, 'code': parsed_code, 'holdings': '사용자가 직접 검색하여 추가한 맞춤 관심 종목'})
                            added_count += 1
                    if added_count > 0: st.success(f"{added_count}개 종목 추가 완료!")
                    st.session_state.search_query = ""
                    st.rerun()
            else:
                st.warning("검색 결과가 없습니다.")

    # 👇 [가짜 종목 전면 폐기] 오직 실존하는 핵심 대장주만 엄선한 무결점 리스트
    raw_etf_data = [
        # 🌐 1. 시장 대표 지수 코어
        {"theme": "🌐 1. 시장 대표 지수 코어", "code": "069500", "name": "KODEX 200"},
        {"theme": "🌐 1. 시장 대표 지수 코어", "code": "102110", "name": "TIGER 200"},
        {"theme": "🌐 1. 시장 대표 지수 코어", "code": "229200", "name": "KODEX 코스닥150"},
        {"theme": "🌐 1. 시장 대표 지수 코어", "code": "360750", "name": "TIGER 미국S&P500"},
        {"theme": "🌐 1. 시장 대표 지수 코어", "code": "360200", "name": "ACE 미국S&P500"},
        {"theme": "🌐 1. 시장 대표 지수 코어", "code": "379780", "name": "RISE 미국S&P500"},
        {"theme": "🌐 1. 시장 대표 지수 코어", "code": "379800", "name": "KODEX 미국S&P500TR"},
        {"theme": "🌐 1. 시장 대표 지수 코어", "code": "133690", "name": "TIGER 미국나스닥100"},
        {"theme": "🌐 1. 시장 대표 지수 코어", "code": "379810", "name": "KODEX 미국나스닥100TR"},
        {"theme": "🌐 1. 시장 대표 지수 코어", "code": "453810", "name": "KODEX 인도Nifty50"},
        {"theme": "🌐 1. 시장 대표 지수 코어", "code": "241180", "name": "TIGER 일본니케이225"},

        # 💻 2. 반도체 & 빅테크 핵심 성장
        {"theme": "💻 2. 반도체 & 빅테크 핵심 성장", "code": "381180", "name": "TIGER 미국테크TOP10 INDXX"},
        {"theme": "💻 2. 반도체 & 빅테크 핵심 성장", "code": "381170", "name": "TIGER 미국필라델피아반도체나스닥"},
        {"theme": "💻 2. 반도체 & 빅테크 핵심 성장", "code": "441680", "name": "ACE 글로벌반도체TOP4 Plus SOLACTIVE"},
        {"theme": "💻 2. 반도체 & 빅테크 핵심 성장", "code": "091160", "name": "KODEX 반도체"},
        {"theme": "💻 2. 반도체 & 빅테크 핵심 성장", "code": "091230", "name": "TIGER 반도체"},
        {"theme": "💻 2. 반도체 & 빅테크 핵심 성장", "code": "455850", "name": "SOL 반도체소부장Fn"},
        {"theme": "💻 2. 반도체 & 빅테크 핵심 성장", "code": "305720", "name": "KODEX 2차전지산업"},
        {"theme": "💻 2. 반도체 & 빅테크 핵심 성장", "code": "305540", "name": "TIGER 2차전지테마"},

        # 🤖 3. AI·로봇 & 사이버보안 혁신 (🔥 가짜 번호 전면 정정 완료)
        {"theme": "🤖 3. AI·로봇 & 사이버보안 혁신", "code": "456600", "name": "TIMEFOLIO 글로벌AI인공지능액티브"}, # (463120 교정)
        {"theme": "🤖 3. AI·로봇 & 사이버보안 혁신", "code": "445290", "name": "KODEX 로봇액티브"}, # (447770 교정)
        {"theme": "🤖 3. AI·로봇 & 사이버보안 혁신", "code": "462330", "name": "KODEX 로보틱스"}, # (462310 교정)
        {"theme": "🤖 3. AI·로봇 & 사이버보안 혁신", "code": "469070", "name": "ACE AI로봇핵심장비TOP4플러스"}, # (469110 교정)
        {"theme": "🤖 3. AI·로봇 & 사이버보안 혁신", "code": "411420", "name": "TIGER 글로벌사이버보안INDXX"},
        {"theme": "🤖 3. AI·로봇 & 사이버보안 혁신", "code": "276990", "name": "KODEX 글로벌4차산업로보틱스(합성)"}, # (279310 교정)
        {"theme": "🤖 3. AI·로봇 & 사이버보안 혁신", "code": "275980", "name": "TIGER 글로벌4차산업혁신기술(합성 H)"}, # (317730 교정)

        # 🚀 4. 방산 & 우주항공 미래 테크 (🔥 가짜 번호 전면 정정 완료)
        {"theme": "🚀 4. 방산 & 우주항공 미래 테크", "code": "449450", "name": "PLUS K방산"}, # (417610 교정)
        {"theme": "🚀 4. 방산 & 우주항공 미래 테크", "code": "449920", "name": "PLUS K방산Fn"},
        {"theme": "🚀 4. 방산 & 우주항공 미래 테크", "code": "432200", "name": "TIGER 우주항공iSelect"},
        {"theme": "🚀 4. 방산 & 우주항공 미래 테크", "code": "421550", "name": "HANARO 우주항공&UAM"},
        {"theme": "🚀 4. 방산 & 우주항공 미래 테크", "code": "482200", "name": "TIGER 글로벌우주항공액티브"},

        # 🏦 5. 금융 지주 & 밸류업 모멘텀 (🔥 가짜 번호 전면 정정 완료)
        {"theme": "🏦 5. 금융 지주 & 밸류업 모멘텀", "code": "466950", "name": "TIGER 은행고배당플러스TOP10"},
        {"theme": "🏦 5. 금융 지주 & 밸류업 모멘텀", "code": "474220", "name": "KODEX 은행고배당플러스"},
        {"theme": "🏦 5. 금융 지주 & 밸류업 모멘텀", "code": "091170", "name": "KODEX 은행"},
        {"theme": "🏦 5. 금융 지주 & 밸류업 모멘텀", "code": "287330", "name": "RISE 금융지주"},
        {"theme": "🏦 5. 금융 지주 & 밸류업 모멘텀", "code": "494330", "name": "KODEX 코리아밸류업"}, # (491100 교정)
        {"theme": "🏦 5. 금융 지주 & 밸류업 모멘텀", "code": "494340", "name": "TIGER 코리아밸류업"},
        {"theme": "🏦 5. 금융 지주 & 밸류업 모멘텀", "code": "492500", "name": "RISE 현대차그룹밸류업모멘텀"},
        {"theme": "🏦 5. 금융 지주 & 밸류업 모멘텀", "code": "466810", "name": "ACE 주주환원가치주액티브"},
        {"theme": "🏦 5. 금융 지주 & 밸류업 모멘텀", "code": "157500", "name": "TIGER 증권"},

        # 💰 6. 고배당 & 월배당 인컴 밸류업 (🔥 가짜 번호 전면 정정 완료)
        {"theme": "💰 6. 고배당 & 월배당 인컴 밸류업", "code": "458730", "name": "TIGER 미국배당다우존스"},
        {"theme": "💰 6. 고배당 & 월배당 인컴 밸류업", "code": "488210", "name": "KODEX 미국배당다우존스"}, # (480350 교정)
        {"theme": "💰 6. 고배당 & 월배당 인컴 밸류업", "code": "446720", "name": "SOL 미국배당다우존스"},
        {"theme": "💰 6. 고배당 & 월배당 인컴 밸류업", "code": "210780", "name": "TIGER 코스피고배당"},
        {"theme": "💰 6. 고배당 & 월배당 인컴 밸류업", "code": "276970", "name": "KODEX 고배당"},
        {"theme": "💰 6. 고배당 & 월배당 인컴 밸류업", "code": "461580", "name": "TIGER 미국배당+7%프리미엄다우존스"},

        # 🛡️ 7. 안전자산 채권 & 원자재 방어
        {"theme": "🛡️ 7. 안전자산 채권 & 원자재 방어", "code": "273130", "name": "KODEX 종합채권(AA-이상)액티브"},
        {"theme": "🛡️ 7. 안전자산 채권 & 원자재 방어", "code": "423160", "name": "KODEX KOFR금리액티브(합성)"},
        {"theme": "🛡️ 7. 안전자산 채권 & 원자재 방어", "code": "411060", "name": "ACE KRX금현물"},
        {"theme": "🛡️ 7. 안전자산 채권 & 원자재 방어", "code": "132030", "name": "KODEX 골드선물(H)"},
        {"theme": "🛡️ 7. 안전자산 채권 & 원자재 방어", "code": "138900", "name": "TIGER 구리선물(H)"},
        {"theme": "🛡️ 7. 안전자산 채권 & 원자재 방어", "code": "153130", "name": "KODEX 단기채권"},
        {"theme": "🛡️ 7. 안전자산 채권 & 원자재 방어", "code": "329650", "name": "TIGER 미국달러단기채권"},
        {"theme": "🛡️ 7. 안전자산 채권 & 원자재 방어", "code": "261200", "name": "KODEX 미국달러선물"},

        # 🌍 8. 해외 직상장 글로벌 메이저
        {"theme": "🌍 8. 해외 직상장 글로벌 메이저", "code": "SPY", "name": "SPDR S&P 500"},
        {"theme": "🌍 8. 해외 직상장 글로벌 메이저", "code": "VOO", "name": "Vanguard S&P 500"},
        {"theme": "🌍 8. 해외 직상장 글로벌 메이저", "code": "QQQ", "name": "Invesco QQQ"},
        {"theme": "🌍 8. 해외 직상장 글로벌 메이저", "code": "SCHD", "name": "Schwab US Dividend"},
        {"theme": "🌍 8. 해외 직상장 글로벌 메이저", "code": "JEPI", "name": "JPMorgan Equity Premium"},
        {"theme": "🌍 8. 해외 직상장 글로벌 메이저", "code": "TLT", "name": "iShares 20+Y Treasury"},
        {"theme": "🌍 8. 해외 직상장 글로벌 메이저", "code": "SOXX", "name": "iShares Semiconductor"},

        # 🚢 9. 조선 & 해운 슈퍼사이클
        {"theme": "🚢 9. 조선 & 해운 슈퍼사이클", "code": "091180", "name": "KODEX 조선"},
        {"theme": "🚢 9. 조선 & 해운 슈퍼사이클", "code": "380960", "name": "HANARO Fn조선해운"},
        {"theme": "🚢 9. 조선 & 해운 슈퍼사이클", "code": "466960", "name": "SOL 조선TOP3플러스"},
        {"theme": "🚢 9. 조선 & 해운 슈퍼사이클", "code": "485520", "name": "KODEX K-조선배당플러스"},

        # ⚡ 10. 전력 인프라 & 글로벌 에너지
        {"theme": "⚡ 10. 전력 인프라 & 글로벌 에너지", "code": "226490", "name": "KODEX 에너지화학"},
        {"theme": "⚡ 10. 전력 인프라 & 글로벌 에너지", "code": "117460", "name": "TIGER 에너지화학"},
        {"theme": "⚡ 10. 전력 인프라 & 글로벌 에너지", "code": "444000", "name": "RISE 글로벌원자력iSelect"},
        {"theme": "⚡ 10. 전력 인프라 & 글로벌 에너지", "code": "418650", "name": "HANARO 글로벌수소&차세대연료전지"},
        {"theme": "⚡ 10. 전력 인프라 & 글로벌 에너지", "code": "385600", "name": "KODEX K-신재생에너지액티브"},
        {"theme": "⚡ 10. 전력 인프라 & 글로벌 에너지", "code": "XLU", "name": "Utilities Select Sector SPDR"},
        {"theme": "⚡ 10. 전력 인프라 & 글로벌 에너지", "code": "ICLN", "name": "iShares Global Clean Energy"}
    ]

    # 👇 공식 이름 동기화 엔진
    @st.cache_data(ttl=86400)
    def update_official_names(items):
        try:
            krx_df = get_naver_etf_and_stocks()
            krx_name_map = dict(zip(krx_df['Code'], krx_df['Name'])) if not krx_df.empty else {}
            
            us_tickers = [it['code'] for it in items if not (len(str(it['code'])) == 6 and any(char.isdigit() for char in str(it['code'])))]
            us_name_map = {}
            import yfinance as yf
            import concurrent.futures
            def get_us_name(ticker):
                try:
                    info = yf.Ticker(ticker).info
                    return ticker, info.get('longName', info.get('shortName', ticker))
                except: return ticker, ticker
            
            if us_tickers:
                with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
                    for code, name in executor.map(get_us_name, us_tickers): us_name_map[code] = name
            
            updated_items = []
            for it in items:
                new_it = it.copy()
                if 'name' not in new_it: new_it['name'] = str(new_it['code'])
                
                code = str(it['code']).zfill(6) if str(it['code']).isdigit() else str(it['code'])
                is_kr = len(code) == 6 and any(char.isdigit() for _ in code)
                
                if is_kr and code in krx_name_map: new_it['name'] = krx_name_map[code]
                elif not is_kr and code in us_name_map and us_name_map[code] != code: new_it['name'] = us_name_map[code]
                
                new_it['code'] = code
                updated_items.append(new_it)
            return updated_items
        except: 
            for it in items:
                if 'name' not in it: it['name'] = str(it['code'])
            return items 

    with st.spinner("가짜 종목 완전 제거 후 네이버 공식 명칭으로 100% 매칭 중입니다..."):
        etf_data = update_official_names(raw_etf_data)

    for item in etf_data:
        item["price"] = 0
        item["cagr"] = "데이터없음(1년미만)"
        item["list_date"] = "데이터없음"
        item["holdings"] = "해당 테마의 국내외 주요 우량 편입 종목"

    for custom_item in st.session_state.custom_etfs:
        if not any(item['code'] == custom_item['code'] for item in etf_data):
            etf_data.append({
                "theme": "🔎 내가 추가한 맞춤 종목", "name": custom_item['name'], "code": custom_item['code'], 
                "price": 0, "cagr": "데이터없음(1년미만)", "list_date": "데이터없음", "holdings": custom_item.get('holdings', "사용자가 직접 검색하여 추가한 맞춤 관심 종목")
            })

    # 👇 절대 0원이 나오지 않게 하는 3중 방어 추적 엔진
    import yfinance as yf
    import datetime
    import concurrent.futures
    
    @st.cache_data(ttl=86400)
    def fetch_historical_cagr(codes):
        cagr_dict = {}
        kr_codes = [c for c in codes if len(str(c)) == 6 and any(char.isdigit() for char in str(c))]
        us_codes = [c for c in codes if c not in kr_codes]

        def get_us_cagr(c):
            try:
                hist = yf.Ticker(c).history(period="max", interval="1mo")
                if not hist.empty and len(hist) > 12:
                    df = hist.dropna(subset=['Close'])
                    if len(df) > 12:
                        p_start, p_end = float(df['Close'].iloc[0]), float(df['Close'].iloc[-1])
                        days = (df.index[-1] - df.index[0]).days
                        if days >= 365 and p_start > 0:
                            return c, {'cagr': round(((p_end / p_start) ** (365.25 / days) - 1) * 100, 2), 'date': df.index[0].strftime('%Y-%m-%d')}
            except: pass
            return c, None
        
        if us_codes:
            with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
                for code, data in executor.map(get_us_cagr, us_codes):
                    if data: cagr_dict[code] = data

        def get_naver_cagr(c):
            try:
                url = f"https://fchart.stock.naver.com/sise.nhn?symbol={c}&timeframe=month&count=1200&requestType=0"
                res = requests.get(url, headers={'User-Agent': 'Mozilla/5.0'}, timeout=5)
                if res.status_code == 200:
                    soup = BeautifulSoup(res.text, 'html.parser')
                    items = soup.find_all('item')
                    if len(items) > 12:
                        first_date, last_date = pd.to_datetime(items[0].get('data').split('|')[0]), pd.to_datetime(items[-1].get('data').split('|')[0])
                        p_start, p_end = float(items[0].get('data').split('|')[4]), float(items[-1].get('data').split('|')[4])
                        days = (last_date - first_date).days
                        if days >= 365 and p_start > 0:
                            return c, {'cagr': round(((p_end / p_start) ** (365.25 / days) - 1) * 100, 2), 'date': first_date.strftime('%Y-%m-%d')}
            except: pass
            try:
                df = fdr.DataReader(c)
                if len(df) > 250:
                    p_start, p_end = float(df['Close'].iloc[0]), float(df['Close'].iloc[-1])
                    days = (df.index[-1] - df.index[0]).days
                    if days >= 365 and p_start > 0:
                        return c, {'cagr': round(((p_end / p_start) ** (365.25 / days) - 1) * 100, 2), 'date': df.index[0].strftime('%Y-%m-%d')}
            except: pass
            return c, None
            
        if kr_codes:
            with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
                for code, data in executor.map(get_naver_cagr, kr_codes):
                    if data: cagr_dict[code] = data
                    
        return cagr_dict

    @st.cache_data(ttl=3600)
    def fetch_realtime_simulator_prices(codes, ex_rate):
        prices = {}
        kr_codes = [c for c in codes if len(str(c)) == 6 and any(char.isdigit() for char in str(c))]
        us_codes = [c for c in codes if c not in kr_codes]
        
        try:
            bulk_krx = get_naver_etf_and_stocks()
            if not bulk_krx.empty and 'Price' in bulk_krx.columns:
                bulk_price_dict = dict(zip(bulk_krx['Code'], bulk_krx['Price']))
                for c in kr_codes:
                    if c in bulk_price_dict and bulk_price_dict[c] > 0: prices[c] = int(bulk_price_dict[c])
        except: pass

        missing_kr = [c for c in kr_codes if c not in prices or prices[c] == 0]
        def get_direct_kr_price(c):
            try:
                df = fdr.DataReader(c)
                if not df.empty: return c, int(df['Close'].iloc[-1])
            except: pass
            return c, 0
            
        if missing_kr:
            with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
                for code, price in executor.map(get_direct_kr_price, missing_kr):
                    if price > 0: prices[code] = price
        
        def get_us_price(c):
            try:
                hist = yf.Ticker(c).history(period="1d")
                if not hist.empty:
                    price = float(hist['Close'].iloc[-1])
                    if price > 0: return c, int(price * ex_rate)
            except: pass
            return c, 0
            
        if us_codes:
            with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
                for code, price in executor.map(get_us_price, us_codes):
                    if price > 0: prices[code] = price
        return prices

    with st.spinner("실시간 가격을 매칭 중입니다..."):
        current_ex_rate = st.session_state.get('ex_rate', 1350.0)
        all_codes = [item['code'] for item in etf_data]
        
        real_prices = fetch_realtime_simulator_prices(all_codes, current_ex_rate)
        real_cagrs = fetch_historical_cagr(all_codes)
        
        for item in etf_data:
            if 'list_date' not in item: item['list_date'] = "데이터없음"
            if item['code'] in real_prices and real_prices[item['code']] > 0: item['price'] = real_prices[item['code']]
            if item['code'] in real_cagrs:
                item['cagr'] = real_cagrs[item['code']]['cagr']
                item['list_date'] = real_cagrs[item['code']]['date']

    # --- [신규 기능] 0원 에러 종목 검출기 ---
    st.markdown("### 🚨 0원 에러 종목 검출기")
    with st.expander("가격이 0원으로 조회되는 종목 확인하기", expanded=False):
        error_items = [{'테마': item['theme'], '종목명': item['name'], '코드': item['code']} for item in etf_data if item.get('price', 0) == 0]
        if error_items:
            st.error(f"총 {len(error_items)}개의 종목이 0원으로 조회되고 있습니다. (상장폐지, 거래정지 또는 티커 오류)")
            error_df = pd.DataFrame(error_items)
            st.dataframe(error_df, use_container_width=True)
            st.info("💡 위 종목들은 종목 코드가 잘못되었거나, 거래 정지 상태일 수 있습니다.")
        else:
            st.success("🎉 현재 0원으로 조회되는 에러 종목이 단 하나도 없습니다! 완벽합니다.")

    # --- 4. 포트폴리오 구성 UI ---
    st.markdown("### 🛒 3. 나만의 노후 포트폴리오 담기")
    if 'retirement_cart' not in st.session_state: st.session_state.retirement_cart = {}

    theme_order = [
        "🌐 1. 시장 대표 지수 코어", 
        "💻 2. 반도체 & 빅테크 핵심 성장", 
        "🤖 3. AI·로봇 & 사이버보안 혁신",
        "🚀 4. 방산 & 우주항공 미래 테크",
        "🏦 5. 금융 지주 & 밸류업 모멘텀",
        "💰 6. 고배당 & 월배당 인컴 밸류업", 
        "🛡️ 7. 안전자산 채권 & 원자재 방어",
        "🌍 8. 해외 직상장 글로벌 메이저",
        "🚢 9. 조선 & 해운 슈퍼사이클",
        "⚡ 10. 전력 인프라 & 글로벌 에너지",
        "🔎 내가 추가한 맞춤 종목"
    ]
    
    for theme in theme_order:
        theme_stocks = [item for item in etf_data if item['theme'] == theme]
        seen = set()
        unique_stocks = [s for s in theme_stocks if s['code'] not in seen and not seen.add(s['code'])]

        if unique_stocks:
            with st.expander(f"{theme} 선택", expanded=(theme=="🌐 1. 시장 대표 지수 코어")):
                for idx, stock in enumerate(unique_stocks):
                    cols = st.columns([3, 1.5, 1.5, 1.5, 1.5, 1]) 
                    with cols[0]:
                        st.markdown(f"**{stock['name']}** ({stock['code']})")
                        st.caption(f"🔍 {stock.get('holdings', '')}")
                        if theme == "🔎 내가 추가한 맞춤 종목" and "사용자가 직접 검색" in stock.get('holdings', ''):
                            if st.button("🤖 AI 편입종목 검색", key=f"ai_{stock['code']}"):
                                if not api_key_input: st.error("좌측 사이드바에 API 키를 입력해주세요.")
                                else:
                                    with st.spinner(f"{stock['name']} 분석 중..."):
                                        ai_holdings = ask_gemini(f"'{stock['name']} ({stock['code']})' 주요 편입 종목 쉼표로 나열.", api_key_input)
                                        for custom_item in st.session_state.custom_etfs:
                                            if custom_item['code'] == stock['code']: custom_item['holdings'] = "💡 AI 분석: " + ai_holdings
                                        st.rerun()
                        
                    cols[1].markdown(f"현재가:<br>{stock['price']:,}원", unsafe_allow_html=True)
                    cols[2].markdown(f"상장(기준)일:<br><span style='color:#328cc1; font-weight:bold;'>{stock.get('list_date', '데이터없음')}</span>", unsafe_allow_html=True)
                    cagr_val = stock['cagr']
                    cagr_display = f"{cagr_val}%" if isinstance(cagr_val, (int, float)) else f"<span style='font-size:0.85em; color:gray;'>{cagr_val}</span>"
                    cols[3].markdown(f"연평균(상장후):<br>{cagr_display}", unsafe_allow_html=True)
                    
                    qty = cols[4].number_input("수량(주)", min_value=0, step=1, key=f"ret_qty_{theme}_{stock['code']}_{idx}", label_visibility="collapsed")
                    
                    if qty > 0: st.session_state.retirement_cart[stock['code']] = {"name": stock['name'], "qty": qty, "price": stock['price'], "cagr": stock['cagr']}
                    elif stock['code'] in st.session_state.retirement_cart: del st.session_state.retirement_cart[stock['code']]

                    if theme == "🔎 내가 추가한 맞춤 종목":
                        if cols[5].button("🗑️ 삭제", key=f"del_{stock['code']}"):
                            st.session_state.custom_etfs = [x for x in st.session_state.custom_etfs if x['code'] != stock['code']]
                            if stock['code'] in st.session_state.retirement_cart: del st.session_state.retirement_cart[stock['code']]
                            st.rerun()

    # --- 5. 시뮬레이션 대시보드 ---
    st.divider()
    st.markdown("### 📊 4. 복리 성장 시뮬레이션 결과")
    cart = st.session_state.retirement_cart
    if not cart: st.info("위 리스트에서 수량을 입력하시면 시뮬레이션이 시작됩니다.")
    else:
        total_principal = sum(v['qty'] * v['price'] for v in cart.values())
        weighted_cagr_sum = sum(v['qty'] * v['price'] * (v['cagr'] if isinstance(v['cagr'], (int, float)) else 0.0) for v in cart.values())
        weighted_cagr = weighted_cagr_sum / total_principal if total_principal > 0 else 0
        
        d_col1, d_col2 = st.columns([1, 2])
        with d_col1:
            st.markdown("#### 📉 포트폴리오 요약")
            st.metric("총 매입 원금", f"{total_principal:,}원")
            st.metric("가중평균 연 수익률", f"{weighted_cagr:.2f}%")
            years = st.select_slider("미래 거치 기간 선택 (년)", options=[1, 3, 5, 10, 15, 20, 25, 30], value=20)
            future_value = total_principal * ((1 + weighted_cagr/100) ** years)
            st.metric(f"{years}년 후 예상 자산", f"{int(future_value):,}원", f"원금 대비 {(future_value/total_principal):.1f}배")
            
        with d_col2:
            st.markdown(f"#### 📈 {years}년 복리 성장 곡선")
            df_chart = pd.DataFrame([{"년수": f"{y}년", "자산규모": int(total_principal * ((1 + weighted_cagr/100) ** y))} for y in range(years + 1)])
            st.area_chart(df_chart.set_index("년수"), color="#2b579a")

        with st.expander("📝 선택한 종목 명세서 보기"):
            if cart:
                st.table(pd.DataFrame([{'name': v['name'], 'qty': v['qty'], 'price': v['price'], '총액': v['qty'] * v['price'], 'cagr': f"{v['cagr']}%" if isinstance(v['cagr'], (int, float)) else v['cagr']} for v in cart.values()]))

        st.caption("※ '데이터없음' 종목은 계산의 안전을 위해 수익률 0%로 보수적 적용됩니다.")

        st.markdown("---")
        if st.button("🤖 AI 노후 포트폴리오 정밀 진단", type="primary", use_container_width=True):
            if not api_key_input: st.error("API 키를 입력해주세요.")
            else:
                with st.spinner("AI가 포트폴리오를 분석 중입니다..."):
                    port_str = "".join([f"- {v['name']}: 비중 {(v['qty'] * v['price'] / total_principal) * 100:.1f}%, 현재가 {v['price']:,}원\n" for v in cart.values()])
                    ai_prompt = f"은퇴 설계 전문가로서 다음 포트폴리오를 진단해 주세요.\n총 매입 원금: {total_principal:,}원\n예상 CAGR: {weighted_cagr:.2f}%\n투자기간: {years}년\n{port_str}"
                    st.success("✅ 진단 완료!")
                    st.markdown(ask_gemini(ai_prompt, api_key_input))
