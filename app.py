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

# [v7.0] 공매도/대차 등 한국시장 리스크 지표용 (pip install pykrx)
try:
    from pykrx import stock as pykrx_stock
    HAS_PYKRX = True
    PYKRX_IMPORT_ERR = ""
except Exception as e:
    pykrx_stock = None
    HAS_PYKRX = False
    PYKRX_IMPORT_ERR = f"{type(e).__name__}: {e}"   # 실제 import 실패 원인 보존

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
st.set_page_config(page_title="Jaemini PRO 터미널 v7.0", layout="wide", page_icon="📈")
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

# [추가] 국민성장펀드 스캐너 상태
if 'gf_sector_query' not in st.session_state: st.session_state.gf_sector_query = None
if 'gf_results' not in st.session_state: st.session_state.gf_results = None

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
# ==========================================
# [v7.0] 폴리마켓(Polymarket) 예측시장 데이터
#   - Gamma API (공개, 키 불필요): https://gamma-api.polymarket.com
#   - 시장 참여자들이 '실제 돈'을 걸고 만든 확률 → 금리/경제/정치 선행지표
# ==========================================
POLY_GAMMA = "https://gamma-api.polymarket.com"

def _poly_parse_list(val):
    """outcomes/outcomePrices 가 JSON 문자열로 오는 경우를 안전하게 리스트로 변환."""
    if isinstance(val, list):
        return val
    if isinstance(val, str):
        try:
            return json.loads(val)
        except Exception:
            return []
    return []

def _poly_num(x):
    try:
        return float(x)
    except Exception:
        return 0.0

@st.cache_data(ttl=300)
def fetch_polymarket_markets(search=None, limit=80):
    """
    활성/미마감 마켓을 24시간 거래량 순으로 가져온다.
    search 가 주어지면 질문 텍스트로 한 번 더 필터링.
    반환: list[dict] (질문, 확률, 거래량 등 정규화된 형태)
    """
    headers = {"User-Agent": "Mozilla/5.0", "Accept": "application/json"}
    params = {
        "active": "true",
        "closed": "false",
        "archived": "false",
        "order": "volume24hr",
        "ascending": "false",
        "limit": int(limit),
    }
    try:
        res = requests.get(f"{POLY_GAMMA}/markets", params=params,
                           headers=headers, timeout=12)
        res.raise_for_status()
        raw = res.json()
    except Exception as e:
        return {"error": f"{type(e).__name__}: {e}", "data": []}

    rows = []
    for m in raw:
        try:
            outcomes = _poly_parse_list(m.get("outcomes"))
            prices = _poly_parse_list(m.get("outcomePrices"))
            # 가장 대표적인 'Yes' 또는 첫 번째 결과의 확률
            yes_prob = None
            if outcomes and prices and len(outcomes) == len(prices):
                pair = dict(zip(outcomes, prices))
                if "Yes" in pair:
                    yes_prob = _poly_num(pair["Yes"]) * 100
                else:
                    yes_prob = _poly_num(prices[0]) * 100
            elif prices:
                yes_prob = _poly_num(prices[0]) * 100

            row = {
                "question": m.get("question") or m.get("title") or "(제목 없음)",
                "yes_prob": round(yes_prob, 1) if yes_prob is not None else None,
                "outcomes": outcomes,
                "prices": [round(_poly_num(p) * 100, 1) for p in prices],
                "volume24hr": _poly_num(m.get("volume24hr")),
                "volume": _poly_num(m.get("volume") or m.get("volumeNum")),
                "liquidity": _poly_num(m.get("liquidity") or m.get("liquidityNum")),
                "end_date": (m.get("endDate") or "")[:10],
                "slug": m.get("slug", ""),
                "category": m.get("category", ""),
            }
            rows.append(row)
        except Exception:
            continue

    if search:
        kw = [s.strip().lower() for s in search.split() if s.strip()]
        if kw:
            rows = [r for r in rows
                    if any(k in r["question"].lower() for k in kw)]
    return {"error": None, "data": rows}

@st.cache_data(ttl=86400, show_spinner=False)
def translate_poly_questions(questions, _api_key):
    """
    여러 영문 질문/선택지를 한 번의 Gemini 호출로 일괄 번역.
    반환: {원문: 한글번역} 딕셔너리. 실패 시 원문 그대로 매핑.
    (API 키가 없으면 번역 없이 원문 반환)
    """
    uniq = [q for q in dict.fromkeys(questions) if q and q.strip()]
    if not uniq:
        return {}
    if not _api_key:
        return {q: q for q in uniq}
    try:
        numbered = "\n".join([f"{i+1}. {q}" for i, q in enumerate(uniq)])
        prompt = (
            "다음은 예측시장(Polymarket)의 영문 질문/선택지 목록이다. "
            "각 항목을 자연스러운 한국어로 번역하라.\n"
            "규칙:\n"
            "- 번호와 순서를 그대로 유지하고, '번호. 번역문' 형식으로만 출력\n"
            "- 고유명사(인물·기관·티커·코인명)는 통용되는 한국어 표기 사용(없으면 원문 유지)\n"
            "- 군더더기 설명 없이 번역 결과만 출력\n\n"
            f"{numbered}"
        )
        resp = ask_gemini(prompt, _api_key)
        mapping = {}
        for line in resp.splitlines():
            line = line.strip()
            mt = re.match(r'^\s*(\d+)\s*[.)]\s*(.+)$', line)
            if mt:
                idx = int(mt.group(1)) - 1
                if 0 <= idx < len(uniq):
                    mapping[uniq[idx]] = mt.group(2).strip()
        # 누락분은 원문으로 보강
        for q in uniq:
            mapping.setdefault(q, q)
        return mapping
    except Exception:
        return {q: q for q in uniq}

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
@st.cache_data(ttl=1800)
def get_us_sector_etfs():
    # [v7.0] 하드코딩 더미 → yfinance 실데이터로 교체 (전일 종가 대비 등락률)
    sectors = [
        ("기술(Technology)", "XLK"), ("금융(Financials)", "XLF"),
        ("헬스케어(Healthcare)", "XLV"), ("에너지(Energy)", "XLE"),
        ("임의소비재(Consumer)", "XLY"), ("필수소비재(Staples)", "XLP"),
        ("산업재(Industrials)", "XLI"), ("반도체(Semicon)", "SMH"),
        ("커뮤니케이션(Comm)", "XLC"), ("유틸리티(Utilities)", "XLU"),
    ]
    def fetch_one(item):
        name, tk = item
        try:
            h = yf.Ticker(tk).history(period="5d")
            if len(h) >= 2:
                close = float(h['Close'].iloc[-1])
                pct = (close / float(h['Close'].iloc[-2]) - 1) * 100
                return {"섹터": name, "ETF": tk, "현재가": round(close, 2), "등락률": round(pct, 2)}
        except Exception:
            pass
        return None
    rows = []
    try:
        with concurrent.futures.ThreadPoolExecutor(max_workers=10) as ex:
            for r in ex.map(fetch_one, sectors):
                if r: rows.append(r)
    except Exception:
        pass
    if rows:
        return pd.DataFrame(rows).sort_values('등락률', ascending=False).reset_index(drop=True)
    # 통신 실패 시 안전 폴백 (값 없음 표시)
    return pd.DataFrame({'섹터': [s[0] for s in sectors], 'ETF': [s[1] for s in sectors],
                         '현재가': [0] * len(sectors), '등락률': [0.0] * len(sectors)})


@st.cache_data(ttl=600)
def get_overnight_us_market():
    """간밤 미국 주요 지수·VIX·환율 스냅샷 (전일 대비 %)."""
    targets = [("나스닥", "^IXIC"), ("S&P500", "^GSPC"), ("다우", "^DJI"),
               ("VIX(공포지수)", "^VIX"), ("원/달러", "KRW=X")]
    out = []
    def fetch(item):
        label, tk = item
        try:
            h = yf.Ticker(tk).history(period="5d")
            if len(h) >= 2:
                last = float(h['Close'].iloc[-1]); prev = float(h['Close'].iloc[-2])
                pct = (last / prev - 1) * 100 if prev else 0
                return {"label": label, "ticker": tk, "value": last, "pct": pct}
        except Exception:
            pass
        return None
    try:
        with concurrent.futures.ThreadPoolExecutor(max_workers=5) as ex:
            for r in ex.map(fetch, targets):
                if r: out.append(r)
    except Exception:
        pass
    order = {t[1]: i for i, t in enumerate(targets)}
    out.sort(key=lambda x: order.get(x['ticker'], 99))
    return out


def render_overnight_banner():
    """간밤 미국 시황 미니 배너 — 급등주 보기 전에 위험선호(Risk-on/off)부터 파악."""
    data = get_overnight_us_market()
    if not data:
        st.caption("⚠️ 간밤 미국 시황 데이터를 불러오지 못했습니다.")
        return
    cols = st.columns(len(data))
    for col, d in zip(cols, data):
        if d['ticker'] == "KRW=X":
            val = f"{d['value']:,.1f}원"
        elif d['ticker'] == "^VIX":
            val = f"{d['value']:.2f}"
        else:
            val = f"{d['value']:,.0f}"
        # VIX는 오르면 위험(빨강이 나쁨)이므로 색 반전
        delta_color = "inverse" if d['ticker'] == "^VIX" else "normal"
        col.metric(d['label'], val, f"{d['pct']:+.2f}%", delta_color=delta_color)

def get_economic_events(year, month):
    """[추가] 해당 연·월의 주요 경제지표 일정을 {일: [(label, css_class), ...]} 형태로 반환.
    - FOMC: 미 연준 공식 확정 일정(2026) — 결정 발표는 회의 2일차.
    - CPI/고용지표: 통상 발표 시기(추정). BLS가 매달 확정하므로 정확한 날짜는 다를 수 있음.
    실제 자동 수집은 환경 제약으로 어려워, 확정 일정은 직접 입력하고 추정 항목은 명시한다."""
    events = {}
    def _add(day, label, cls):
        events.setdefault(day, []).append((label, cls))

    # ── 2026 FOMC 금리결정일 (회의 2일차, 공식 확정) ──
    fomc_2026 = {
        1: [28], 3: [18], 4: [29], 6: [17], 7: [29], 9: [16], 10: [28], 12: [9],
    }
    if year == 2026 and month in fomc_2026:
        for d in fomc_2026[month]:
            _add(d, "🏛️ 🇺🇸FOMC 금리결정", "evt-econ-fomc")

    # ── 미국 CPI (BLS 공식 확정 2026) ──
    # 1월은 셧다운으로 13→2/13 연기됐으나, 표준 공식 일정을 사용.
    cpi_2026 = {1: 13, 2: 11, 3: 11, 4: 10, 5: 12, 6: 10, 7: 14, 8: 12, 9: 11, 10: 14, 11: 10, 12: 10}
    if year == 2026 and month in cpi_2026:
        _add(cpi_2026[month], "📊 🇺🇸CPI 물가", "evt-econ-cpi")

    # ── 미국 고용지표(비농업, BLS 공식 확정 2026) ──
    jobs_2026 = {1: 9, 2: 6, 3: 6, 4: 3, 5: 8, 6: 5, 7: 2, 8: 7, 9: 4, 10: 2, 11: 6, 12: 4}
    if year == 2026 and month in jobs_2026:
        _add(jobs_2026[month], "👷 🇺🇸고용지표", "evt-econ-jobs")

    # ── 한국 금통위 통화정책방향 결정회의 (2026 공식 확정) ──
    # 한국은행 발표: 1/15, 2/26, 4/10, 5/28, 7/16, 8/27, 10/22, 11/26
    bok_2026 = {1: 15, 2: 26, 4: 10, 5: 28, 7: 16, 8: 27, 10: 22, 11: 26}
    if year == 2026 and month in bok_2026:
        _add(bok_2026[month], "🏦 🇰🇷한은 금통위", "evt-econ-bok")

    return events


@st.cache_data(ttl=3600)
def analyze_theme_trends():
    """국내 대표 섹터 ETF의 1·3·6개월 수익률을 실측해 섹터 순환매 분석용 DataFrame 반환.
       컬럼: 테마, 1M수익률, 3M수익률, 6M수익률 (단위: %)"""
    sector_etfs = {
        "반도체": "091160",
        "2차전지": "305720",
        "자동차": "091180",
        "은행": "091170",
        "증권": "102970",
        "건설": "117700",
        "에너지화학": "117460",
        "철강": "117680",
        "헬스케어": "266420",
        "미디어/엔터": "266360",
        "기계장비": "102960",
        "운송": "140710",
    }
    end = datetime.now()
    start = end - timedelta(days=240)

    def _calc(item):
        name, c = item
        try:
            df = fdr.DataReader(c, start.strftime('%Y-%m-%d'), end.strftime('%Y-%m-%d'))
            if df is None or df.empty or 'Close' not in df.columns:
                return None
            s = df['Close'].dropna()
            if len(s) < 5:
                return None
            last = float(s.iloc[-1])
            def _ret(days):
                target = s.index[-1] - pd.Timedelta(days=days)
                past = s[s.index <= target]
                if past.empty:
                    past = s
                base = float(past.iloc[0]) if past is s else float(past.iloc[-1])
                return round((last / base - 1) * 100, 2) if base > 0 else 0.0
            return {"테마": name, "1M수익률": _ret(30), "3M수익률": _ret(90), "6M수익률": _ret(180)}
        except Exception:
            return None

    rows = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as executor:
        for r in executor.map(_calc, list(sector_etfs.items())):
            if r:
                rows.append(r)
    return pd.DataFrame(rows)


@st.cache_data(ttl=3600)
def _parse_ipo_enddate(s):
    """청약일정 문자열에서 종료 날짜를 파싱 (예: '26.05.22~05.26' → 2026-05-26)."""
    s = str(s).strip()
    full = re.findall(r'(\d{2,4})[.\-/](\d{1,2})[.\-/](\d{1,2})', s)
    if not full:
        return None
    y, m, d = full[0]
    y = int(y); y = (2000 + y) if y < 100 else y
    try:
        start = datetime(y, int(m), int(d))
    except Exception:
        return None
    end = start
    rng = re.search(r'[~∼\-]\s*(?:(\d{1,2})[.\-/])?(\d{1,2})\s*$', s)
    if rng:
        em, ed = rng.groups()
        try:
            end = datetime(y, int(em) if em else int(m), int(ed))
        except Exception:
            end = start
    return end


def _clean_ipo_df(df):
    """IPO 표 후처리: 가비지 제거 + 컬럼 검증 + 공모가 포맷 + 다가오는 일정 정렬/필터 + 중복 제거."""
    if df is None or df.empty:
        return pd.DataFrame()
    df = df.copy()
    base_cols = ['시장', '종목명', '청약일정', '상장일', '공모가', '주관사', '경쟁률', '업종']
    for c in base_cols:
        if c not in df.columns:
            df[c] = '-'
    df = df[base_cols]
    for c in base_cols:
        df[c] = df[c].fillna('-').astype(str).str.strip().replace({'nan': '-', 'None': '-', 'NaN': '-', '': '-'})

    # 1) 가비지 행 제거 (종목명이 안내문장)
    df = df[df['종목명'].str.len().between(1, 25)]
    df = df[~df['종목명'].str.contains('공모함|수요예측|기관투자|파악|결정됨|청약을|투자자의', na=False)]

    # 2) 청약일정 검증 — 날짜 형태가 아니면(예: 경쟁률 '747:1') '-' 처리
    def valid_date(s):
        s = str(s)
        if re.search(r'\d{1,2}\s*:\s*1', s):      # 경쟁률 패턴
            return '-'
        if re.search(r'\d{1,4}[.\-/]\d{1,2}', s):  # 날짜 패턴
            return s
        return '-'
    df['청약일정'] = df['청약일정'].apply(valid_date)
    df['상장일'] = df['상장일'].apply(lambda x: x if (re.search(r'\d{1,4}[.\-/]\d{1,2}', str(x)) or '미정' in str(x)) else '-')

    # 3) 공모가 포맷 (숫자만 → '12,300원', 범위 → '10,000~12,000원')
    def clean_price(v):
        s = str(v).strip()
        if not s or s == '-':
            return '-'
        if re.search(r'결정|파악|수요|공모함|기관|투자자', s) or re.search(r'[가-힣]{4,}', s):
            return '-'
        nums = re.findall(r'\d[\d,]*', s)
        if not nums:
            return '-'
        def fmt(n):
            n = n.replace(',', '')
            return f"{int(n):,}" if n.isdigit() else None
        a = fmt(nums[0]); b = fmt(nums[1]) if len(nums) > 1 else None
        if a and b and a != b:
            return f"{a}~{b}원"
        return f"{a}원" if a else '-'
    df['공모가'] = df['공모가'].apply(clean_price)

    # 4) 종목명 중복 제거 (실데이터 많은 행 우선)
    def score(row):
        return sum(1 for c in ['청약일정', '상장일', '공모가', '주관사', '경쟁률', '업종']
                   if str(row[c]).strip() not in ('-', '', 'nan'))
    df['_score'] = df.apply(score, axis=1)
    df = (df.sort_values('_score', ascending=False)
            .drop_duplicates(subset=['종목명'], keep='first')
            .drop(columns=['_score']))

    # 5) 날짜 파싱 → 다가오는(또는 최근) 일정만, 빠른 순 정렬
    df['_end'] = df['청약일정'].apply(_parse_ipo_enddate)
    today = datetime.now()
    recent_or_future = df[df['_end'].notna() & (df['_end'] >= today - timedelta(days=5))]
    if len(recent_or_future) >= 1:
        dated = recent_or_future.sort_values('_end', ascending=True)           # 다가오는 순
        undated = df[df['_end'].isna()]
        out = pd.concat([dated, undated])
    else:
        # 다가오는 게 없으면(소스에 과거만 있으면) 최근 날짜 순으로라도 보여줌
        out = df.sort_values('_end', ascending=False, na_position='last')
    out = out.drop(columns=['_end']).reset_index(drop=True)
    return out.head(20)


@st.cache_data(ttl=3600)
def get_naver_ipo_data():
    # [v7.0] 표 기반(38.co.kr → 네이버 read_html) 우선, _clean_ipo_df로 정제 후 반환.

    def priority_pick(cols, cands, exclude=None):
        for cand in cands:                       # 우선순위 순
            for c in cols:
                if exclude and any(x in c for x in exclude):
                    continue
                if cand in c:
                    return c
        return None

    # ── 소스 A: 38커뮤니케이션 공모청약 일정 ──
    try:
        url = "http://www.38.co.kr/html/fund/index.htm?o=k"
        res = requests.get(url, headers={'User-Agent': 'Mozilla/5.0'}, timeout=5)
        res.encoding = 'euc-kr'
        tables = pd.read_html(StringIO(res.text))
        for t in tables:
            cols = [str(c) for c in t.columns]
            if not any(('기업명' in c or '종목명' in c) for c in cols):
                continue
            t = t.copy(); t.columns = cols
            name_c = priority_pick(cols, ['기업명', '종목명'])
            if not name_c:
                continue
            res_df = pd.DataFrame()
            res_df['종목명'] = t[name_c]
            res_df['시장'] = '-'
            # 청약일정: '경쟁률/률' 들어간 컬럼은 제외하고 날짜 컬럼만
            sub_c = priority_pick(cols, ['공모청약일', '공모주일정', '청약일정', '청약일', '청약', '일정'], exclude=['경쟁', '률'])
            res_df['청약일정'] = t[sub_c] if sub_c else '-'
            res_df['상장일'] = (lambda c: t[c] if c else '-')(priority_pick(cols, ['상장일', '상장'], exclude=['주가', '수익']))
            res_df['공모가'] = (lambda c: t[c] if c else '-')(priority_pick(cols, ['확정공모가', '공모가', '희망공모가']))
            res_df['주관사'] = (lambda c: t[c] if c else '-')(priority_pick(cols, ['주간사', '주관사']))
            res_df['경쟁률'] = (lambda c: t[c] if c else '-')(priority_pick(cols, ['청약경쟁률', '경쟁률']))
            res_df['업종'] = (lambda c: t[c] if c else '-')(priority_pick(cols, ['업종', '업태']))
            cleaned = _clean_ipo_df(res_df)
            if not cleaned.empty:
                return cleaned
    except Exception:
        pass

    # ── 소스 B: 네이버 IPO 표 ──
    try:
        url = "https://finance.naver.com/sise/ipo.naver"
        res = requests.get(url, headers={'User-Agent': 'Mozilla/5.0'}, timeout=5)
        html_text = res.content.decode('euc-kr', 'replace')
        tables = pd.read_html(StringIO(html_text))
        for t in tables:
            t_str = t.to_string()
            if '공모가' in t_str and ('청약' in t_str or '상장일' in t_str):
                cols = [str(c) for c in t.columns]
                t = t.copy(); t.columns = cols
                name_col = priority_pick(cols, ['종목', '기업', '회사']) or cols[0]
                t = t.dropna(subset=[name_col]).copy()
                t = t[t[name_col].astype(str) != str(name_col)]

                def extract_market(x):
                    x = str(x).replace(' ', '')
                    for m in ['코스닥', '유가증권', '코넥스']:
                        if x.startswith(m):
                            return m
                    return '-'
                def clean_name(x):
                    x = str(x).strip()
                    for m in ['코스닥', '유가증권', '코넥스']:
                        if x.startswith(m):
                            return x[len(m):].strip()
                    return x

                res_df = pd.DataFrame()
                res_df['시장'] = t[name_col].apply(extract_market)
                res_df['종목명'] = t[name_col].apply(clean_name)
                sub_c = priority_pick(cols, ['공모청약일', '청약일', '청약', '일정'], exclude=['경쟁', '률'])
                res_df['청약일정'] = t[sub_c] if sub_c else '-'
                res_df['상장일'] = (lambda c: t[c] if c else '-')(priority_pick(cols, ['상장일']))
                res_df['공모가'] = (lambda c: t[c] if c else '-')(priority_pick(cols, ['확정공모가', '공모가']))
                res_df['주관사'] = (lambda c: t[c] if c else '-')(priority_pick(cols, ['주관', '주간']))
                res_df['경쟁률'] = (lambda c: t[c] if c else '-')(priority_pick(cols, ['경쟁률']))
                res_df['업종'] = (lambda c: t[c] if c else '-')(priority_pick(cols, ['업종']))
                cleaned = _clean_ipo_df(res_df)
                if not cleaned.empty:
                    return cleaned
    except Exception:
        pass

    return pd.DataFrame()


@st.cache_data(ttl=86400)
def get_dividend_portfolio(ex_rate):
    # =========================================================
    # [공용] yfinance 견고 수집기 : (현재가, 연간배당금, 이름) 반환
    #   - Yahoo 차단/지연 대비 세션 위장 + 다중 폴백
    #   - 연간배당금은 "최근 12개월 실배당 합계"를 최우선으로 사용
    # =========================================================
    def _yf_fetch_one(ticker_code):
        try:
            import yfinance as yf
        except Exception:
            return ticker_code, 0.0, 0.0, ticker_code, "—"

        t = None
        try:
            sess = requests.Session()
            sess.headers.update({'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'})
            t = yf.Ticker(ticker_code, session=sess)
        except Exception:
            try:
                t = yf.Ticker(ticker_code)
            except Exception:
                return ticker_code, 0.0, 0.0, ticker_code, "—"

        price = 0.0
        annual_div = 0.0
        name = ticker_code
        freq = "—"   # 배당 주기 (월/분기/반기/연배당) — 아래 배당내역에서 추정

        # 1) 현재가 (fast_info → info → 최근 종가 순)
        try:
            fi = t.fast_info
            price = float(fi.get('lastPrice') or fi.get('last_price') or 0) or 0.0
        except Exception:
            price = 0.0

        info = {}
        try:
            info = t.info or {}
        except Exception:
            info = {}

        if not price:
            price = float(info.get('currentPrice') or info.get('regularMarketPrice')
                          or info.get('previousClose') or 0) or 0.0
        if not price:
            try:
                h = t.history(period="5d")
                if not h.empty:
                    price = float(h['Close'].dropna().iloc[-1])
            except Exception:
                pass

        name = info.get('shortName') or info.get('longName') or ticker_code

        # 2) 연간 배당금 — 최근 12개월 실지급 배당 합계 (가장 신뢰도 높음)
        try:
            divs = t.dividends
            if divs is not None and len(divs) > 0:
                idx = divs.index
                try:
                    cutoff = pd.Timestamp.now(tz=idx.tz) - pd.Timedelta(days=365)
                except Exception:
                    cutoff = pd.Timestamp.now() - pd.Timedelta(days=365)
                recent = divs[idx >= cutoff]
                if len(recent) > 0:
                    annual_div = float(recent.sum())
                    # 최근 12개월 '실제 지급 횟수 + 지급 월'로 배당 주기 추정
                    try:
                        n_pay = int(len(recent))
                        months = sorted(set(int(m) for m in recent.index.month))
                        mtxt = "·".join(str(m) for m in months) + "월"
                        if n_pay >= 7:
                            freq = "월배당 (매월)"
                        elif n_pay >= 3:
                            freq = f"분기배당 ({mtxt})"
                        elif n_pay == 2:
                            freq = f"반기배당 ({mtxt})"
                        else:
                            freq = f"연배당 ({mtxt})"
                    except Exception:
                        pass
        except Exception:
            pass

        # 폴백 A : info 의 배당금 필드
        if not annual_div:
            annual_div = float(info.get('dividendRate') or info.get('trailingAnnualDividendRate') or 0) or 0.0

        # 폴백 B : 배당수익률 × 현재가
        if not annual_div and price:
            dy = info.get('dividendYield') or info.get('trailingAnnualDividendYield') or 0
            try:
                dy = float(dy)
                if dy > 1:           # 일부 버전은 퍼센트(예: 3.5)로 반환
                    dy = dy / 100.0
                if dy:
                    annual_div = price * dy
            except Exception:
                pass

        return ticker_code, float(price or 0), float(annual_div or 0), name, freq

    def _yf_fetch_many(tickers, max_workers=8):
        out = {}
        try:
            with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as ex:
                for tk, pr, dv, nm, fq in ex.map(_yf_fetch_one, tickers):
                    out[tk] = (pr, dv, nm, fq)
        except Exception:
            for tk in tickers:
                try:
                    _, pr, dv, nm, fq = _yf_fetch_one(tk)
                    out[tk] = (pr, dv, nm, fq)
                except Exception:
                    out[tk] = (0.0, 0.0, tk, "—")
        return out

    # ----- 조회 대상 종목 -----
    kr_tickers = [
        "024110.KS", "316140.KS", "086790.KS", "105560.KS", "055550.KS", "033780.KS",
        "017670.KS", "030200.KS", "032640.KS", "090430.KS", "000810.KS", "058300.KS",
        "001450.KS", "032830.KS", "029780.KS", "005930.KS", "005935.KS", "000270.KS",
        "005380.KS", "004800.KS", "003550.KS", "034730.KS", "078930.KS", "010130.KS",
        "010950.KS", "053690.KS", "000400.KS",
        # --- 추가 확장분 (pykrx 차단 시 폴백용 대형 배당주) ---
        "000660.KS", "005490.KS", "051910.KS", "006400.KS", "035420.KS", "035720.KS",
        "028260.KS", "012330.KS", "068270.KS", "051900.KS", "097950.KS", "271560.KS",
        "011170.KS", "096770.KS", "015760.KS", "036460.KS", "009540.KS", "010140.KS",
        "011200.KS", "086280.KS", "000120.KS", "003490.KS", "138040.KS", "088350.KS",
        "005830.KS", "005385.KS", "071050.KS", "016360.KS", "006800.KS", "039490.KS",
        "004170.KS", "023530.KS", "069960.KS", "161390.KS", "009150.KS", "018260.KS",
        "010120.KS", "006260.KS", "001120.KS", "012450.KS", "047810.KS", "267250.KS",
        "004020.KS", "001040.KS", "002790.KS", "000150.KS", "064350.KS", "272210.KS"
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
    us_tickers = ["AAPL", "MSFT", "JNJ", "XOM", "JPM", "PG", "CVX", "HD", "ABBV", "MRK",
                  "KO", "PEP", "BAC", "PFE", "TMO", "CSCO", "MCD", "WMT", "TXN", "IBM",
                  "VZ", "MMM", "MO", "CAT", "UPS", "T", "KMB", "CL", "CLX", "K",
                  "ADP", "EMR", "ITW", "GD", "LMT", "NOC", "RTX", "HON", "SHW", "APD",
                  "LIN", "NEE", "DUK", "SO", "D", "AEP", "O", "PLD", "AMT", "PSA",
                  "ABT", "MDT", "BMY", "AMGN", "LLY", "UNH", "CVS", "TGT", "LOW", "COST",
                  "TJX", "KR", "HSY", "MDLZ", "STZ", "PM", "KDP", "COP", "EOG", "SLB",
                  "PSX", "MPC", "VLO", "OKE", "KMI", "WMB", "NUE", "WFC", "C", "USB",
                  "PNC", "TFC", "AXP", "BLK", "SPGI", "TROW", "GS", "PRU", "TRV", "QCOM",
                  "AVGO", "AMAT", "INTC", "NKE", "SBUX", "CMCSA", "UNP", "FDX", "MMC", "WM"]
    etf_tickers = ["SCHD", "JEPI", "VYM", "VIG", "SPYD", "JEPQ", "DGRO", "NOBL", "DVY", "SDY",
                   "HDV", "PFF", "TLT", "HYG", "LQD", "VNQ", "DGRW", "FVD", "RDVY", "PEY",
                   "DHS", "DLN", "DTD", "DON", "DES", "FDVV", "SPHD", "DIV", "SCHY", "VYMI",
                   "IDV", "DWX", "DEM", "DGS", "HDEF", "QYLD", "XYLD", "RYLD", "DIVO", "QYLG",
                   "XYLG", "NUSI", "SPYI", "QQQI", "GPIX", "GPIQ", "JEPY", "FEPI", "BALI", "SVOL",
                   "TLTW", "HYGW", "PFFD", "PGX", "PGF", "VRP", "PFXF", "FPE", "PFFA", "PFFR",
                   "PFLD", "IEF", "IEI", "SHY", "GOVT", "BND", "AGG", "VCIT", "VCSH", "VCLT",
                   "JNK", "USHY", "SHYG", "SJNK", "EMB", "BNDX", "MUB", "TFI", "HYD", "BAB",
                   "ANGL", "FALN", "BIL", "SGOV", "USFR", "FLOT", "JAAA", "BINC", "SCHH", "RWR",
                   "IYR", "REM", "MORT", "SRET", "KBWY", "SDIV", "KBWD", "YYY"]

    # =========================================================
    # 1. 🇰🇷 한국 주식 (KRX)
    # =========================================================
    krx_list = []

    # (1-A) pykrx 공식 API (국내 IP / 로컬에서 최상)
    try:
        from pykrx import stock
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
                '배당주기': '연 1회(추정)',
                '비고': 'KRX 공식 데이터'
            })
    except Exception:
        pass

    # (1-B) yfinance 우회 — 클라우드 IP에서 pykrx 가 막혔을 때 (가장 안정적)
    if not krx_list:
        kr_res = _yf_fetch_many(kr_tickers)
        for t_code in kr_tickers:
            pr, dv, nm, fq = kr_res.get(t_code, (0.0, 0.0, t_code, "—"))
            if pr > 0 and dv > 0:
                krx_list.append({
                    '종목명': kr_names.get(t_code) or nm or t_code,
                    '현재가': f"{int(pr):,}원",
                    '예상 배당금': float(dv),
                    '배당주기': fq,
                    '비고': 'Yahoo(yfinance) 우회'
                })

    # (1-C) yahooquery 우회 — 최후의 폴백
    if not krx_list:
        try:
            from yahooquery import Ticker as yq_Ticker
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
                            '종목명': kr_names.get(t_code) or p.get('shortName') or p.get('longName') or t_code,
                            '현재가': f"{int(price):,}원",
                            '예상 배당금': float(div_rate),
                            '배당주기': '—',
                            '비고': 'yahooquery 우회'
                        })
                except Exception:
                    pass
        except Exception:
            pass

    krx_df = pd.DataFrame(krx_list)
    if not krx_df.empty:
        krx_df = krx_df.sort_values('예상 배당금', ascending=False)
        krx_df['예상 배당금'] = krx_df['예상 배당금'].apply(lambda x: f"{int(x):,}원" if isinstance(x, (int, float)) else str(x))

    # =========================================================
    # 2. 🇺🇸 미국 주식 & 📈 ETF
    # =========================================================
    us_list, etf_list = [], []

    def _build_us_row(ticker, pr, dv, nm, src, freq="—"):
        if pr > 0 and dv > 0:
            name_ko = ticker
            if 'get_korean_name' in globals():
                name_ko = get_korean_name(nm)
                if name_ko == nm:          # 사전 미매칭 → 티커로 재시도
                    name_ko = get_korean_name(ticker)
            return {
                '종목명': f"{name_ko} ({ticker})",
                '현재가': f"${pr:,.2f} ({int(pr * ex_rate):,}원)",
                '예상 배당금': float(dv),
                '표시 배당금': f"${dv:,.2f} ({int(dv * ex_rate):,}원)",
                '배당주기': freq,
                '비고': src
            }
        return None

    # (2-A) yfinance 우선 (이 앱에서 검증된 경로)
    yf_res = _yf_fetch_many(us_tickers + etf_tickers)
    for tk in us_tickers:
        pr, dv, nm, fq = yf_res.get(tk, (0.0, 0.0, tk, "—"))
        row = _build_us_row(tk, pr, dv, nm, 'yfinance', freq=fq)
        if row: us_list.append(row)
    for tk in etf_tickers:
        pr, dv, nm, fq = yf_res.get(tk, (0.0, 0.0, tk, "—"))
        row = _build_us_row(tk, pr, dv, nm, 'yfinance', freq=fq)
        if row: etf_list.append(row)

    # (2-B) yahooquery 폴백 — yfinance 가 비었을 때만
    if not us_list or not etf_list:
        try:
            from yahooquery import Ticker as yq_Ticker
            need = ([] if us_list else us_tickers) + ([] if etf_list else etf_tickers)
            if need:
                yq = yq_Ticker(need)
                details = yq.summary_detail
                prices = yq.price

                def _yq_row(ticker):
                    try:
                        detail = details.get(ticker, {})
                        price_info = prices.get(ticker, {})
                        if isinstance(detail, str): return None
                        price = price_info.get('regularMarketPrice', 0)
                        div_rate = detail.get('dividendRate', 0)
                        if not div_rate or div_rate == 0:
                            dy = detail.get('yield', detail.get('trailingAnnualDividendYield', 0))
                            if dy and price > 0: div_rate = price * dy
                        nm = price_info.get('shortName', ticker)
                        return _build_us_row(ticker, price, div_rate, nm, 'yahooquery')
                    except Exception:
                        return None

                if not us_list:
                    for tk in us_tickers:
                        r = _yq_row(tk)
                        if r: us_list.append(r)
                if not etf_list:
                    for tk in etf_tickers:
                        r = _yq_row(tk)
                        if r: etf_list.append(r)
        except Exception:
            pass

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
        
        model = genai.GenerativeModel('gemini-3.1-flash-lite')
        
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
        model = genai.GenerativeModel('gemini-3.1-flash-lite')
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

# 👇 [업그레이드 1] 한미 통합 듀얼 엔진으로 시장 주도 테마를 추출하는 함수
@st.cache_data(ttl=10800) # 3시간마다 캐시 갱신
def get_trending_themes_with_ai(api_key):
        if not api_key: return ["테스트 테마 A", "테스트 테마 B", "테스트 테마 C", "테스트 테마 D"]
        
        market_context = ""
        try:
            # 1. 한국 시장 (KRX) 거래대금 상위 종목 추출
            krx_df = fdr.StockListing('KRX')
            if 'Volume' in krx_df.columns and 'Close' in krx_df.columns:
                krx_df['Amount'] = krx_df['Volume'] * krx_df['Close']
                top_kr = krx_df.sort_values('Amount', ascending=False).head(30)
                kr_tickers = ", ".join(top_kr['Name'].tolist())
                market_context += f"🔥 [한국 증시(KRX) 거래대금 상위 30종목]: {kr_tickers}\n"
            
            # 2. 미국 시장 (US) S&P500 등 주요 종목 거래량 급증 탐지 (yfinance 활용)
            # (시간 관계상 S&P500 대표 종목군 리스트를 활용하여 빠른 스캔)
            us_major_tickers = ["NVDA", "AAPL", "MSFT", "AMZN", "META", "GOOGL", "TSLA", "LLY", "AVGO", "TSM", "AMD", "SMCI"]
            us_active = []
            import yfinance as yf
            import concurrent.futures
            
            def check_us_volume(ticker):
                try:
                    hist = yf.Ticker(ticker).history(period="5d")
                    if len(hist) >= 2:
                        # 최근 거래량이 5일 평균보다 급증했는지 확인 (단순 지표)
                        vol_today = hist['Volume'].iloc[-1]
                        vol_avg = hist['Volume'].mean()
                        if vol_today > vol_avg * 1.2:  # 20% 이상 거래량 폭발 시
                            return ticker
                except: pass
                return None

            with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
                for res in executor.map(check_us_volume, us_major_tickers):
                    if res: us_active.append(res)
            
            if us_active:
                market_context += f"🦅 [미국 증시(US) 거래량 급증 주요 티커]: {', '.join(us_active)}\n"

        except Exception as e:
            market_context = "시장 데이터를 불러오는 중 오류 발생 (AI 자체 판단 필요)"

        # 👇 [업그레이드 2] AI에게 글로벌(한+미) 시각으로 분석하도록 프롬프트 전면 수정
        prompt = f"""
        당신은 월스트리트와 여의도를 아우르는 글로벌 퀀트 애널리스트입니다.
        아래는 오늘 한국 증시(KRX) 거래대금 상위 종목과 미국 증시(US) 거래량 급증 종목 데이터입니다.
        
        {market_context}
        
        이 데이터를 바탕으로, 현재 전 세계 주식시장을 관통하고 있는 '가장 뜨거운 메가트렌드 및 핵심 주도 테마' 4가지를 추출하세요.
        반드시 쉼표(,)로만 구분된 텍스트로 출력해야 합니다.
        예시: 차세대 AI 반도체, 비만치료제(GLP-1), 전력 인프라 및 변압기, 자율주행 및 로보택시
        """
        try:
            res = ask_gemini(prompt, api_key)
            themes = [t.strip() for t in res.split(',') if t.strip()]
            return themes[:4] if len(themes) >= 4 else (themes + ["추가 테마 분석 필요"] * 4)[:4]
        except:
            return ["글로벌 AI 반도체", "비만치료제 및 K-바이오", "전력기기 및 K-방산", "자율주행 및 로보틱스"]

# 👇 [업그레이드 3] 테마 검색 시, 미국(US) 텐배거 대장주까지 함께 발굴하도록 수정
@st.cache_data(ttl=3600)
def get_theme_stocks_with_ai(theme, api_key):
    prompt = f"""
    당신은 글로벌 테마주 발굴 전문가입니다.
    현재 '{theme}' 테마가 글로벌 주식시장을 주도하고 있습니다.
    이 테마의 '진짜 수혜주'이자 폭발적인 상승(텐배거)이 기대되는 '핵심 대장주' 30개를 선정해 주세요.
    [필수 조건]
    1. 반드시 한국 증시(KRX) 종목 15개와 미국 증시(US) 종목 15개를 섞어서 구성하세요.
    2. 미국 주식은 한국인이 많이 투자하는 친숙한 티커(예: NVDA, TSLA 등) 위주로 선정하세요.
    3. 출력 형식은 반드시 "종목명,종목코드" 여야 합니다. (예: 삼성전자,005930 / 엔비디아,NVDA)
    4. 번호 매기기, 부연 설명, 마크다운 기호(-, * 등)는 절대 쓰지 말고 오직 종목 데이터만 한 줄에 하나씩 출력하세요.
    """
    try:
        res = ask_gemini(prompt, api_key)
        lines = res.split('\n')
        stocks = []
        for line in lines:
            parts = line.split(',')
            if len(parts) >= 2:
                name = parts[0].strip().replace("-", "").replace("*", "").strip()
                code = parts[1].strip()
                # 한국 종목(숫자 6자리)이거나 미국 티커(알파벳)인 경우만 허용
                if (len(code) == 6 and code.isdigit()) or code.isalpha():
                    stocks.append((name, code))
        return stocks[:30] # 👈 기존 15에서 30으로 확장
    except:
        return []


# ==========================================
# [추가] 국민성장펀드 12대 첨단전략산업 연동
# ==========================================
# 금융위원회 지정 주목적 투자대상 12개 첨단전략산업 (2026년 기준)
GROWTH_FUND_SECTORS = {
    "🤖 미래 기술": [
        ("AI 인공지능", "AI 인공지능"),
        ("반도체", "반도체 소부장"),
        ("바이오", "바이오 신약"),
        ("백신", "백신 주권"),
        ("로봇", "로봇 자동화"),
    ],
    "🔋 에너지·모빌리티": [
        ("이차전지", "이차전지 배터리"),
        ("수소", "수소 경제"),
        ("미래차", "미래차 전기차 자율주행"),
        ("디스플레이", "디스플레이 OLED"),
    ],
    "🛡️ 전략·소재·콘텐츠": [
        ("방산", "방위산업 항공우주"),
        ("콘텐츠", "미디어 콘텐츠"),
        ("핵심광물", "핵심광물 희토류"),
    ],
}
# 정부 자금 배분 하이라이트
GROWTH_FUND_ALLOC = {"총 규모": "150조", "AI": "30조", "반도체": "20.9조", "모빌리티": "15.4조"}

@st.cache_data(ttl=3600)
def get_growth_fund_stocks_with_ai(sector_query, _api_key):
    """국민성장펀드 특정 첨단전략산업의 국내(KRX) 수혜 대장주를 AI로 발굴"""
    if not _api_key:
        return []
    prompt = f"""당신은 한국 정책펀드(국민성장펀드, 150조원) 전문 애널리스트입니다.
정부가 첨단전략산업으로 지정한 '{sector_query}' 분야에서, 국민성장펀드 투자 및 정책 수혜가 기대되는
한국 증시(KRX) 상장 핵심 대장주 및 밸류체인(소재·부품·장비) 종목 20개를 선정하세요.
[필수 조건]
1. 반드시 한국 증시(KRX)에 상장된 종목만 선정하세요.
2. 출력 형식은 반드시 "종목명,종목코드(6자리 숫자)" 입니다. (예: 삼성전자,005930)
3. 번호, 부연 설명, 마크다운 기호(-, * 등) 없이 오직 종목 데이터만 한 줄에 하나씩 출력하세요."""
    try:
        res = ask_gemini(prompt, _api_key)
        stocks = []
        seen = set()
        for line in res.split("\n"):
            parts = line.split(",")
            if len(parts) >= 2:
                name = parts[0].strip().replace("-", "").replace("*", "").strip()
                code = parts[1].strip()
                if len(code) == 6 and code.isdigit() and code not in seen:
                    seen.add(code)
                    stocks.append((name, code))
        return stocks[:20]
    except Exception:
        return []



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


# ==========================================
# [추가] 멀티팩터 가치/성장 스캐너 v2
#   - 위험성향 3단계 × 세부전략 9종, PER·PBR·배당·ROE·부채·성장·모멘텀 사용
#   - PER/PBR/모멘텀은 하드 필터(신뢰도 높은 데이터), 나머지는 소프트(값 있을 때만 탈락)
# ==========================================
VALUE_STRATEGIES = {
    "🛡️ 안전/방어": [
        {"name": "그레이엄 딥밸류 (안전마진)", "per": 10, "pbr": 1.0, "div": None, "roe": None, "debt": None, "growth": None, "mom": None,
         "desc": "초저 PER·PBR + 흑자. 자산가치 대비 싼 종목.",
         "hint": "저평가 자산가치주, 청산가치 근처의 안전마진이 큰 흑자 기업"},
        {"name": "고배당 방어주 (인컴)", "per": 15, "pbr": 2.0, "div": 4.0, "roe": None, "debt": 150, "growth": None, "mom": None,
         "desc": "배당 4%+ , 부채 적고 현금흐름 안정적인 방어주.",
         "hint": "배당수익률이 높고 부채가 적으며 현금흐름이 안정적인 방어적 고배당주"},
        {"name": "퀄리티 우량주 (버핏형 해자)", "per": 25, "pbr": 6.0, "div": None, "roe": 15, "debt": 150, "growth": None, "mom": None,
         "desc": "높은 ROE + 독점력(해자) + 낮은 부채의 컴파운더.",
         "hint": "높은 ROE와 경제적 해자, 브랜드/독점력을 가진 우량 기업"},
    ],
    "⚖️ 중립/균형": [
        {"name": "GARP 합리적 성장 (피터 린치)", "per": 20, "pbr": 3.0, "div": None, "roe": 12, "debt": None, "growth": 10, "mom": None,
         "desc": "합리적 PER에 이익 성장(낮은 PEG)을 겸비.",
         "hint": "이익이 꾸준히 성장하면서 PER이 성장률 대비 합리적인 GARP 종목"},
        {"name": "마법공식 (그린블라트)", "per": 15, "pbr": None, "div": None, "roe": 15, "debt": None, "growth": None, "mom": None,
         "desc": "높은 자본수익률(ROE) + 높은 이익수익률(저 PER) 결합.",
         "hint": "자본수익률(ROE/ROIC)이 높고 이익수익률(저PER)도 높은 마법공식형 저평가 우량주"},
        {"name": "배당성장주 (디비던드 그로스)", "per": 20, "pbr": 4.0, "div": 2.0, "roe": 12, "debt": None, "growth": 8, "mom": None,
         "desc": "배당 2%+ 와 이익 성장을 함께 가진 복리 배당주.",
         "hint": "배당을 꾸준히 늘려온 이익 성장형 배당성장주"},
    ],
    "🚀 공격/성장": [
        {"name": "모멘텀 성장주 (강세 추세)", "per": 60, "pbr": None, "div": None, "roe": None, "debt": None, "growth": 15, "mom": "strong",
         "desc": "강한 가격 모멘텀(3·6개월 상승) + 고성장. PER 관대.",
         "hint": "매출·이익이 고성장하며 주가가 강한 상승 추세(신고가 부근)인 모멘텀 주도주"},
        {"name": "턴어라운드 역발상 (바닥 탈출)", "per": None, "pbr": 1.5, "div": None, "roe": None, "debt": None, "growth": None, "mom": "weak",
         "desc": "52주 고점 대비 크게 하락 + 저 PBR. 실적 바닥 반등 기대.",
         "hint": "실적/주가가 바닥을 치고 턴어라운드가 기대되는 낙폭과대 저평가 역발상 종목"},
        {"name": "중소형 폭발 성장주 (스몰캡)", "per": 50, "pbr": None, "div": None, "roe": None, "debt": None, "growth": 20, "mom": "strong",
         "desc": "코스닥 중소형 고성장 + 강세 모멘텀. 고위험·고수익.",
         "hint": "시가총액이 작지만 폭발적 성장과 강한 모멘텀을 가진 코스닥 중소형 성장주"},
    ],
}

@st.cache_data(ttl=3600)
def get_value_metrics(code):
    """멀티팩터 스캐너용 지표 수집. 반환 dict: per,pbr,div,roe,debt,growth,mom3,mom6,off_high"""
    out = {"per": None, "pbr": None, "div": None, "roe": None, "debt": None,
           "growth": None, "mom3": None, "mom6": None, "off_high": None}
    # 1) PER/PBR (네이버 - 신뢰도 높음)
    try:
        per_str, pbr_str, _, _, _ = get_fundamentals(code)
        def _f(x):
            try:
                v = float(str(x).replace(",", ""))
                return v if v != 0 else None
            except Exception:
                return None
        out["per"], out["pbr"] = _f(per_str), _f(pbr_str)
    except Exception:
        pass
    # 2) ROE/배당/부채/성장 (yfinance - KR 커버리지 편차 있어 소프트 처리)
    try:
        t = yf.Ticker(f"{code}.KS")
        info = t.info
        if not info or (info.get("currentPrice") is None and info.get("regularMarketPrice") is None):
            t = yf.Ticker(f"{code}.KQ")
            info = t.info
        def _pct(v):
            if v is None:
                return None
            v = float(v)
            return round(v * 100, 1) if abs(v) < 5 else round(v, 1)
        out["roe"] = _pct(info.get("returnOnEquity"))
        out["growth"] = _pct(info.get("earningsGrowth"))
        dy = info.get("dividendYield")
        if dy is not None:
            dy = float(dy)
            out["div"] = round(dy * 100, 2) if dy < 1 else round(dy, 2)
        de = info.get("debtToEquity")
        out["debt"] = round(float(de), 1) if de is not None else None
    except Exception:
        pass
    # 3) 모멘텀 (fdr 가격 - 신뢰도 높음)
    try:
        end = datetime.now()
        start = end - timedelta(days=400)
        df = fdr.DataReader(code, start.strftime("%Y-%m-%d"), end.strftime("%Y-%m-%d"))
        if df is not None and not df.empty and "Close" in df.columns:
            s = df["Close"].dropna()
            if len(s) > 20:
                last = float(s.iloc[-1])
                def _ret(days):
                    tgt = s.index[-1] - pd.Timedelta(days=days)
                    past = s[s.index <= tgt]
                    base = float(past.iloc[-1]) if not past.empty else float(s.iloc[0])
                    return round((last / base - 1) * 100, 1) if base > 0 else None
                out["mom3"], out["mom6"] = _ret(90), _ret(180)
                hi = float(s.max())
                out["off_high"] = round((last / hi - 1) * 100, 1) if hi > 0 else None
    except Exception:
        pass
    return out

def value_passes(m, s):
    """전략 s 기준 통과 여부. PER/PBR/모멘텀=하드, ROE/배당/부채/성장=소프트(값 있을 때만 탈락)."""
    if s["per"] is not None:
        if m["per"] is None or not (0 < m["per"] <= s["per"]):
            return False
    if s["pbr"] is not None:
        if m["pbr"] is None or not (0 < m["pbr"] <= s["pbr"]):
            return False
    if s["div"] is not None and m["div"] is not None and m["div"] < s["div"]:
        return False
    if s["roe"] is not None and m["roe"] is not None and m["roe"] < s["roe"]:
        return False
    if s["debt"] is not None and m["debt"] is not None and m["debt"] > s["debt"]:
        return False
    if s["growth"] is not None and m["growth"] is not None and m["growth"] < s["growth"]:
        return False
    if s["mom"] == "strong":
        if m["mom3"] is None or m["mom6"] is None or m["mom3"] <= 0 or m["mom6"] <= 0:
            return False
    elif s["mom"] == "weak":
        if m["off_high"] is None or m["off_high"] > -25:
            return False
    return True

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
            
            if not df_desc.empty and 'Symbol' in df_desc.columns and 'Sector' in df_desc.columns:
                df_desc = df_desc.rename(columns={'Symbol': 'Code'})
                
                df['Code'] = df['Code'].astype(str).str.zfill(6)
                df_desc['Code'] = df_desc['Code'].astype(str).str.zfill(6)
                
                # 🔥 [핵심 1] 기존 데이터에 불량 Sector가 있다면 꼬이지 않게 통째로 날려버림
                if 'Sector' in df.columns:
                    df = df.drop(columns=['Sector'])
                    
                # 정확한 KRX-DESC의 Sector로만 깔끔하게 병합
                df = pd.merge(df, df_desc[['Code', 'Sector']], on='Code', how='left')
        except Exception:
            pass

        if not df.empty:
            if 'Sector' not in df.columns: 
                df['Sector'] = '기타/분류불가'
            
            # 🔥 [핵심 2] API가 보내는 악성 빈칸('')이나 띄어쓰기(' ')를 잡아내 결측치로 강제 변환
            df['Sector'] = df['Sector'].replace('', np.nan).replace(' ', np.nan)
            df['Sector'] = df['Sector'].fillna('기타/분류불가') 
            
            # 🛡️ [핵심 3: 최후의 방어막] API 서버가 죽더라도 주요 대장주 섹터는 무조건 살려내는 하드코딩
            major_sectors = {
                '005930': '반도체', '000660': '반도체', '005380': '자동차', '000270': '자동차',
                '373220': '2차전지', '207940': '바이오', '068270': '바이오', '035420': 'IT/플랫폼',
                '035720': 'IT/플랫폼', '105560': '금융지주', '055550': '금융지주', '028260': '지주사',
                '051910': '화학/2차전지', '006400': '2차전지', '012330': '자동차부품', '005490': '철강'
            }
            def safe_sector(row):
                if row['Code'] in major_sectors and row['Sector'] == '기타/분류불가':
                    return major_sectors[row['Code']]
                return row['Sector']
                
            df['Sector'] = df.apply(safe_sector, axis=1)
            
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
            else: 
                df_fdr['Sector'] = '기타/분류불가'
            
            # 🔥 [히트맵 섹터 복구 엔진] 거래소 서버 차단 시, 네이버 증권에서 쾌속 병렬 처리로 업종을 구출해옵니다.
            missing_mask = df_fdr['Sector'] == '기타/분류불가'
            if missing_mask.any():
                missing_codes = df_fdr.loc[missing_mask, 'Code'].tolist()
                
                def rescue_sector(code):
                    try:
                        res = requests.get(f"https://finance.naver.com/item/main.naver?code={code}", headers={'User-Agent': 'Mozilla/5.0'}, timeout=2)
                        soup = BeautifulSoup(res.text, 'html.parser')
                        
                        # 🛠️ [핵심 수정] 여기도 동일하게 a 태그만 정확하게 타겟팅합니다.
                        tag = soup.select_one('a[href*="/sise/sise_group_detail.naver"]')
                        return code, tag.text.strip() if tag else '기타'
                    except: return code, '기타'
                
                with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
                    rescued_sectors = dict(executor.map(rescue_sector, missing_codes))
                
                df_fdr.loc[missing_mask, 'Sector'] = df_fdr.loc[missing_mask, 'Code'].map(rescued_sectors).fillna('기타')
                
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


# [v7.0] 거래량 표 가독성 개선 — 핵심 컬럼만 추려 색상·단위·막대그래프로 표시
def style_volume_table(df, kind="surge"):
    """네이버 원본 표 → 종목명/현재가/등락률/거래량증감률 4컬럼으로 정리 후 Styler 반환."""
    if df is None or df.empty:
        return None, None
    def to_num(x):
        try: return float(re.sub(r'[^0-9.\-]', '', str(x)))
        except Exception: return np.nan

    df = df.copy()
    colmap = {}
    for c in df.columns:
        cs = str(c)
        if '종목' in cs: colmap[c] = '종목명'
        elif '현재가' in cs: colmap[c] = '현재가'
        elif '등락' in cs: colmap[c] = '등락률'
        elif ('증가율' in cs) or ('감소율' in cs): colmap[c] = '_rate'
    df = df.rename(columns=colmap)

    keep = ['종목명'] if '종목명' in df.columns else []
    if not keep:  # 종목명조차 없으면 원본 그대로
        return None, None
    if '현재가' in df.columns:
        df['현재가'] = df['현재가'].apply(to_num); keep.append('현재가')
    if '등락률' in df.columns:
        df['등락률'] = df['등락률'].apply(to_num); keep.append('등락률')
    rate_name = '🔥 거래량 폭증률' if kind == "surge" else '❄️ 거래량 감소율'
    if '_rate' in df.columns:
        df['_rate'] = df['_rate'].apply(to_num).abs()
        df = df.rename(columns={'_rate': rate_name}); keep.append(rate_name)
    else:
        rate_name = None

    out = df[keep].reset_index(drop=True)
    out.index = out.index + 1
    out.index.name = '순위'

    def color_updown(v):
        if pd.isna(v): return ''
        if v > 0: return 'color:#e74c3c;font-weight:700;'   # 빨강=상승(한국식)
        if v < 0: return 'color:#2e86de;font-weight:700;'   # 파랑=하락
        return 'color:gray;'

    fmt = {}
    if '현재가' in out.columns: fmt['현재가'] = lambda x: f"{int(x):,}원" if pd.notna(x) else "-"
    if '등락률' in out.columns: fmt['등락률'] = lambda x: f"{x:+.2f}%" if pd.notna(x) else "-"
    if rate_name: fmt[rate_name] = lambda x: f"{x:,.0f}%" if pd.notna(x) else "-"

    sty = out.style.format(fmt)
    if '등락률' in out.columns:
        sty = sty.map(color_updown, subset=['등락률'])
    if rate_name:
        bar_color = '#ffd8a8' if kind == "surge" else '#a5d8ff'
        try:
            sty = sty.bar(subset=[rate_name], color=bar_color, vmin=0)
        except Exception:
            pass
    sty = sty.set_properties(**{'font-size': '14px', 'text-align': 'center'})
    sty = sty.set_properties(subset=['종목명'], **{'text-align': 'left', 'font-weight': '600'})
    return sty, rate_name

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


# [v7.0] 시장경보 표 가독성 개선 — 핵심 컬럼만 + 지정사유 중복 제거 + 심각도 색상
def style_warning_table(df, kind="mgmt"):
    """관리종목/투자경보 표를 종목명·현재가·등락률·(지정일)·(지정사유)로 정리."""
    if df is None or df.empty:
        return None
    def to_num(x):
        try: return float(re.sub(r'[^0-9.\-]', '', str(x)))
        except Exception: return np.nan
    def dedup_text(s):
        # 네이버가 같은 사유를 두 번 붙여 보내는 버그 교정 ("A 발생 A 발생" → "A 발생")
        s = str(s).strip()
        toks = s.split()
        n = len(toks)
        if n >= 2 and n % 2 == 0 and toks[:n // 2] == toks[n // 2:]:
            return ' '.join(toks[:n // 2])
        return s

    df = df.copy()
    colmap = {}
    for c in df.columns:
        cs = str(c)
        if '종목' in cs: colmap[c] = '종목명'
        elif '현재가' in cs: colmap[c] = '현재가'
        elif '등락' in cs: colmap[c] = '등락률'
        elif ('지정일' in cs) or ('날짜' in cs) or ('일자' in cs): colmap[c] = '지정일'
        elif ('사유' in cs) or ('구분' in cs): colmap[c] = '지정사유'
    df = df.rename(columns=colmap)
    if '종목명' not in df.columns:
        return None

    order = ['종목명', '현재가', '등락률', '지정일', '지정사유']
    keep = [c for c in order if c in df.columns]
    df = df[keep]
    if '현재가' in df.columns: df['현재가'] = df['현재가'].apply(to_num)
    if '등락률' in df.columns: df['등락률'] = df['등락률'].apply(to_num)
    if '지정사유' in df.columns: df['지정사유'] = df['지정사유'].apply(dedup_text)

    out = df.reset_index(drop=True)
    out.index = out.index + 1
    out.index.name = '순위'

    def color_updown(v):
        if pd.isna(v): return ''
        if v > 0: return 'color:#e74c3c;font-weight:700;'
        if v < 0: return 'color:#2e86de;font-weight:700;'
        return 'color:gray;'

    def color_reason(s):
        s = str(s)
        if any(k in s for k in ['상장폐지', '파산', '정리매매', '거래정지']):
            return 'color:#c0392b;font-weight:700;'   # 🔴 치명적
        if any(k in s for k in ['실질심사', '적격성', '회생', '감사의견', '미제출']):
            return 'color:#e67e22;font-weight:600;'    # 🟠 위험
        return 'color:#b7791f;'                          # 🟡 주의

    fmt = {}
    if '현재가' in out.columns: fmt['현재가'] = lambda x: f"{int(x):,}원" if pd.notna(x) else "-"
    if '등락률' in out.columns: fmt['등락률'] = lambda x: f"{x:+.2f}%" if pd.notna(x) else "-"

    sty = out.style.format(fmt)
    if '등락률' in out.columns:
        sty = sty.map(color_updown, subset=['등락률'])
    if '지정사유' in out.columns:
        sty = sty.map(color_reason, subset=['지정사유'])
    sty = sty.set_properties(**{'font-size': '14px'})
    sty = sty.set_properties(subset=['종목명'], **{'font-weight': '600'})
    if '지정사유' in out.columns:
        sty = sty.set_properties(subset=['지정사유'], **{'text-align': 'left'})
    return sty


# [v7.0] 증권사 리포트 목표가 상/하향 랭킹 — 깨지던 막대그래프 대신 가독성 표로 교체
def style_report_table(df, kind="up"):
    """오늘 발간 리포트를 종목명·증권사·투자의견·목표가·변동률 표로 정리."""
    if df is None or df.empty:
        return None
    cols = [c for c in ['종목명', '증권사', '투자의견', '목표가', '변동률'] if c in df.columns]
    if '종목명' not in cols:
        return None
    out = df[cols].copy().reset_index(drop=True)
    out.index = out.index + 1
    out.index.name = '순위'

    def color_updown(v):
        if pd.isna(v): return ''
        if v > 0.05: return 'color:#e74c3c;font-weight:700;'
        if v < -0.05: return 'color:#2e86de;font-weight:700;'
        return 'color:gray;'

    fmt = {}
    if '목표가' in out.columns:
        fmt['목표가'] = lambda x: f"{int(x):,}원" if pd.notna(x) and x > 0 else "-"
    if '변동률' in out.columns:
        fmt['변동률'] = lambda x: (f"{x:+.1f}%" if pd.notna(x) and abs(x) >= 0.05 else "신규/유지")

    sty = out.style.format(fmt)
    if '변동률' in out.columns:
        sty = sty.map(color_updown, subset=['변동률'])
        try:
            if (out['변동률'].abs().fillna(0) >= 0.05).sum() >= 1:
                bar_color = '#ffd8a8' if kind == "up" else '#a5d8ff'
                sty = sty.bar(subset=['변동률'], color=bar_color, align='zero')
        except Exception:
            pass
    sty = sty.set_properties(**{'font-size': '13px'})
    sty = sty.set_properties(subset=['종목명'], **{'font-weight': '600'})
    return sty


# [v7.0] 미국 섹터 ETF 표 — 등락률 색상 + 막대
def style_sector_etf_table(df):
    if df is None or df.empty:
        return None
    out = df.copy().reset_index(drop=True)
    out.index = out.index + 1
    out.index.name = '순위'

    def color_updown(v):
        if pd.isna(v): return ''
        if v > 0: return 'color:#e74c3c;font-weight:700;'
        if v < 0: return 'color:#2e86de;font-weight:700;'
        return 'color:gray;'

    fmt = {}
    if '현재가' in out.columns: fmt['현재가'] = lambda x: f"${x:,.2f}" if pd.notna(x) and x > 0 else "-"
    if '등락률' in out.columns: fmt['등락률'] = lambda x: f"{x:+.2f}%" if pd.notna(x) else "-"
    sty = out.style.format(fmt)
    if '등락률' in out.columns:
        sty = sty.map(color_updown, subset=['등락률'])
        try: sty = sty.bar(subset=['등락률'], color=['#a5d8ff', '#ffd8a8'], align='zero')
        except Exception: pass
    sty = sty.set_properties(**{'font-size': '13px'})
    sty = sty.set_properties(subset=['섹터'], **{'font-weight': '600'})
    return sty


# [v7.0] 미국 급등주 표 — 핵심 컬럼 정리 + 등락률 색상 (문자열 데이터 처리)
def style_us_gainers_table(df):
    if df is None or df.empty:
        return None
    cols = [c for c in ['종목코드', '기업명', '현재가', '환산(원)', '등락률', '등락금액'] if c in df.columns]
    if '기업명' not in cols:
        return None
    out = df[cols].copy().reset_index(drop=True)
    out.index = out.index + 1
    out.index.name = '순위'

    def color_str(s):
        s = str(s)
        if s.startswith('+') or (s.startswith('$') is False and '+' in s):
            return 'color:#e74c3c;font-weight:700;'
        if s.startswith('-'):
            return 'color:#2e86de;font-weight:700;'
        return ''
    sty = out.style
    for c in ['등락률', '등락금액']:
        if c in out.columns:
            sty = sty.map(color_str, subset=[c])
    sty = sty.set_properties(**{'font-size': '13px'})
    sty = sty.set_properties(subset=['기업명'], **{'font-weight': '600'})
    return sty


# [v7.0] IPO 표 — 청약 예정(일정 있는) 종목 강조 + 종목명 굵게
def style_ipo_table(df):
    if df is None or df.empty:
        return None
    out = df.copy().reset_index(drop=True)
    out.index = out.index + 1
    out.index.name = 'No'

    def highlight_active(row):
        active = str(row.get('청약일정', '-')).strip() not in ('-', '', 'nan')
        bg = 'background-color: rgba(46,134,222,0.08);' if active else ''
        return [bg] * len(row)

    sty = out.style.apply(highlight_active, axis=1)
    sty = sty.set_properties(**{'font-size': '13px'})
    sty = sty.set_properties(subset=['종목명'], **{'font-weight': '700'})
    for c in ['청약일정', '상장일', '공모가', '경쟁률']:
        if c in out.columns:
            sty = sty.set_properties(subset=[c], **{'text-align': 'center'})
    return sty


# [v7.0] 하드코딩된 ETF 코드가 틀렸을 때, 이름으로 실시간 목록에서 정확한 코드를 자동 보정
_ETF_BRANDS = ['KODEX', 'TIGER', 'PLUS', 'ARIRANG', 'HANARO', 'SOL', 'RISE', 'KBSTAR', 'KB STAR',
               'ACE', 'KOSEF', 'TIMEFOLIO', 'WON', '히어로즈', '마이다스', 'TREX', 'FOCUS',
               '파워', 'BNK', 'HK', '네비게이터', '우리', '신한', '하나', '미래에셋']

def _norm_etf_name(s):
    s = str(s).upper()
    for b in _ETF_BRANDS:
        s = s.replace(b.upper(), '')
    return re.sub(r'[^가-힣A-Z0-9]', '', s)   # 공백·특수문자 제거

def resolve_etf_codes(etf_data, live_df):
    """live_df(실시간 ETF 목록: Code,Name)에서 이름으로 정확한 코드를 찾아 보정.
    리브랜딩(예: HANARO→PLUS)·오타 코드를 자동 교정하고, 매칭 시 정식 이름으로 갱신."""
    if live_df is None or live_df.empty:
        return etf_data
    exact, normed = {}, {}
    for _, r in live_df.iterrows():
        code = str(r['Code']).zfill(6)
        nm = str(r['Name'])
        exact[re.sub(r'\s+', '', nm)] = code
        k = _norm_etf_name(nm)
        if not k:
            continue
        if k in normed:
            if normed[k] is not None and normed[k][0] != code:
                normed[k] = None        # 정규화 이름이 모호하면 사용 안 함
        else:
            normed[k] = (code, nm)
    for item in etf_data:
        if not str(item.get('code', '')).isdigit():   # 미국·맞춤종목은 건드리지 않음
            continue
        nm_ws = re.sub(r'\s+', '', str(item['name']))
        if nm_ws in exact:                              # 1순위: 정확 일치
            item['code'] = exact[nm_ws]
            continue
        k = _norm_etf_name(item['name'])                # 2순위: 브랜드 무시 정규화 일치(모호하지 않을 때만)
        if k and normed.get(k):
            item['code'], item['name'] = normed[k][0], normed[k][1]
    return etf_data


# [v7.0] AI 밸류체인 리포트에서 '한국 수혜주' 종목명만 추출 → KRX 코드 매칭
def extract_beneficiary_stocks(report_text, krx_df, max_n=8):
    if not report_text or krx_df is None or krx_df.empty:
        return []
    name_to_code = dict(zip(krx_df['Name'].astype(str), krx_df['Code'].astype(str)))
    names_sorted = sorted(name_to_code.keys(), key=len, reverse=True)  # 긴 이름 우선(부분 오매칭 방지)
    found, seen = [], set()

    def add_match(cand):
        cand = re.sub(r'\(.*?\)', '', str(cand)).strip().strip('*•-· ')
        if not cand:
            return
        if cand in name_to_code and cand not in seen:          # 정확 일치
            found.append((cand, name_to_code[cand])); seen.add(cand); return
        for nm in names_sorted:                                # 부분 일치(긴 이름 우선)
            if len(nm) >= 2 and nm in cand and nm not in seen:
                found.append((nm, name_to_code[nm])); seen.add(nm); return

    # 1) AI가 마지막에 넣어준 '[수혜주]: A, B, C' 라인 우선 파싱
    m = re.search(r'\[?\s*수혜주[^\]:：]*\]?\s*[:：]\s*(.+)', report_text)
    if m:
        line = m.group(1).split('\n')[0]
        for c in re.split(r'[,/·、|]+', line):
            add_match(c)
            if len(found) >= max_n:
                return found[:max_n]

    # 2) 폴백: 리포트 본문 전체에서 KRX 종목명 직접 스캔 (3글자 이상만, 과매칭 방지)
    if len(found) < 2:
        for nm in names_sorted:
            if len(nm) >= 3 and nm in report_text and nm not in seen:
                found.append((nm, name_to_code[nm])); seen.add(nm)
                if len(found) >= max_n:
                    break
    return found[:max_n]

@st.cache_data(ttl=60)
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

@st.cache_data(ttl=120)
def get_intraday_estimate(code):
    """투자자별(외국인·기관·개인) 순매매 수량 — 네이버 모바일 증권 trend API.
    레거시 frgn HTML 페이지가 Streamlit Cloud IP에서 403/구조변경으로 불안정하여
    안정적인 m.stock.naver.com JSON API로 교체했다.
    ※ 분단위 장중 잠정치가 아니라 '가장 최근 거래일(확정)' 수치이며, 단위는 '주식 수'.
    반환: {"time": "MM/DD", "forgn": 외인순매수주, "inst": 기관순매수주,
           "indiv": 개인순매수주, "is_daily": True} | None (실패 시)"""
    if not str(code).isdigit():
        return None
    try:
        url = f"https://m.stock.naver.com/api/stock/{code}/trend"
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            "Referer": f"https://m.stock.naver.com/domestic/stock/{code}/total",
            "Accept": "application/json",
        }
        res = requests.get(url, headers=headers, timeout=5)
        if res.status_code != 200:
            return None
        data = res.json()
        # 응답은 최신 거래일이 [0]인 리스트 (혹은 dict로 감싸진 경우 대비)
        if isinstance(data, dict):
            for k in ("trends", "result", "list", "data"):
                if isinstance(data.get(k), list):
                    data = data[k]; break
        if not isinstance(data, list) or not data:
            return None
        row = data[0]

        def _num(v):
            """'+5,314,304' / '-1,061,741' → int. 파싱 실패 시 None."""
            if v is None:
                return None
            s = str(v).replace(',', '').replace('+', '').strip()
            return int(s) if s.lstrip('-').isdigit() else None

        f_val = _num(row.get("foreignerPureBuyQuant"))
        i_val = _num(row.get("organPureBuyQuant"))
        d_val = _num(row.get("individualPureBuyQuant"))
        if f_val is None and i_val is None:
            return None

        # 날짜 YYYYMMDD → MM/DD (기존 UI의 'time' 자리에 표기)
        bd = str(row.get("bizdate", ""))
        time_label = f"{bd[4:6]}/{bd[6:8]}" if len(bd) == 8 and bd.isdigit() else "최근"

        return {
            "time": time_label,
            "forgn": f_val or 0,
            "inst": i_val or 0,
            "indiv": d_val or 0,
            "is_daily": True,
        }
    except Exception:
        return None


@st.cache_data(ttl=120)
def get_intraday_estimate_debug(code):
    """장중 잠정치가 왜 안 잡히는지 진단용 — 네이버 응답/표 구조를 그대로 보여준다."""
    info = {"http": None, "tables": 0, "summaries": [], "cand_via": "없음", "rows": [], "foreign_rows": [], "err": ""}
    try:
        url = f"https://finance.naver.com/item/frgn.naver?code={code}"
        res = requests.get(url, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}, timeout=4)
        info["http"] = res.status_code
        res.encoding = 'euc-kr'
        soup = BeautifulSoup(res.text, 'html.parser')
        all_t = soup.find_all('table')
        info["tables"] = len(all_t)
        info["summaries"] = [((t.get('summary', '') or '').strip())[:40] for t in all_t][:10]
        # '외국계' 가 들어간 행(거래원 추정합) 원본도 수집 → 파서 정합성 확인용
        for tr in soup.find_all('tr'):
            txt = tr.get_text(" ", strip=True)
            if '외국계' in txt:
                info["foreign_rows"].append(txt[:120])
            if len(info["foreign_rows"]) >= 4:
                break
        cand = None
        for t in all_t:
            if '잠정' in (t.get('summary', '') or ''):
                cand = t; info["cand_via"] = "summary:잠정"; break
        if cand is None:
            t2 = soup.select('table.type2')
            if t2:
                cand = t2[0]; info["cand_via"] = "type2[0] 폴백"
        if cand is not None:
            for tr in cand.find_all('tr')[:6]:
                tds = tr.find_all('td')
                if tds:
                    info["rows"].append(" | ".join(td.get_text(strip=True) for td in tds)[:90])
    except Exception as e:
        info["err"] = f"{type(e).__name__}: {e}"
    return info


@st.cache_data(ttl=120)
def get_foreign_broker_estimate(code):
    """장중 실시간 '외국계 거래원 순매수 추정'(KRX 거래원 기준).
    네이버 frgn 페이지의 '거래원 동향' 표에서 '외국계 거래원 매수/매도량 추정합'을 뽑는다.
    외국인 '확정 순매수'와는 다른 '외국계 창구 추정치'지만, 장중 외국인 매매를 가늠하는
    실시간 프록시로 널리 쓰인다. 반환: {"sell":매도추정, "buy":매수추정, "net":순매수추정} | None"""
    if not str(code).isdigit():
        return None
    try:
        url = f"https://finance.naver.com/item/frgn.naver?code={code}"
        res = requests.get(url, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}, timeout=4)
        res.encoding = 'euc-kr'
        soup = BeautifulSoup(res.text, 'html.parser')
        sell = buy = None
        for tr in soup.find_all('tr'):
            txt = tr.get_text(" ", strip=True)
            if '외국계' in txt and '추정' in txt:
                nums = [int(n.replace(',', '')) for n in re.findall(r'-?[\d,]{2,}', txt)
                        if n.replace(',', '').lstrip('-').isdigit()]
                if '매도' in txt and '매수' in txt and len(nums) >= 2:
                    sell, buy = nums[0], nums[1]
                    break
                elif '매도' in txt and nums and sell is None:
                    sell = nums[0]
                elif '매수' in txt and nums and buy is None:
                    buy = nums[0]
        if sell is not None and buy is not None:
            return {"sell": sell, "buy": buy, "net": buy - sell}
        return None
    except Exception:
        return None


@st.cache_data(ttl=120)
def get_kr_market_breadth():
    """국내(코스피+코스닥) 등락 종목 수(상승/보합/하락) — 네이버 지수 페이지에서 합산.
    ★속도 핵심: 개별 종목 2,600여 개를 받지 않고, 네이버가 '집계해 둔' 종목 수만
      가볍게 2회 요청(각 timeout 3.5s) + 2분 캐시 → 대시보드 부하 거의 없음. 실패 시 None."""
    def _one(mkt):
        try:
            url = f"https://finance.naver.com/sise/sise_index.naver?code={mkt}"
            res = requests.get(url, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}, timeout=3.5)
            res.encoding = 'euc-kr'
            text = BeautifulSoup(res.text, 'html.parser').get_text(" ", strip=True)
            def f(kw):
                # '상승 243' / '상승종목 243' / '상승 종목수 243' 모두 매칭, '상승률 1.2'·'상한 0'은 회피
                m = re.search(kw + r'(?:\s*종목수?)?\s*([\d,]+)', text)
                return int(m.group(1).replace(',', '')) if m else None
            up, flat, down = f('상승'), f('보합'), f('하락')
            if up is None or down is None:
                return None
            return (up, flat or 0, down)
        except Exception:
            return None
    parts = [r for r in (_one('KOSPI'), _one('KOSDAQ')) if r]
    if not parts:
        return None
    up = sum(p[0] for p in parts)
    flat = sum(p[1] for p in parts)
    down = sum(p[2] for p in parts)
    total = up + flat + down
    if not (50 <= total <= 6000):   # 비정상 파싱이면 실패 처리
        return None
    return {"up": up, "flat": flat, "down": down, "total": total, "markets": len(parts)}


def render_kr_market_breadth():
    """홈 대시보드용 '오늘의 국장 장세' 위젯 (상승/하락 종목 수 + 막대)."""
    b = get_kr_market_breadth()
    if not b:
        st.caption("📊 오늘의 국장 장세(등락 종목 수)를 불러오지 못했습니다. (네이버 지수 페이지 일시 지연 또는 구조 변경)")
        return
    total, up, down, flat = b["total"], b["up"], b["down"], b["flat"]
    up_pct = up / total * 100
    down_pct = down / total * 100
    flat_pct = max(0.0, 100 - up_pct - down_pct)
    scope = "코스피+코스닥" if b["markets"] == 2 else "단일 시장"
    st.markdown(
        f"#### 📊 오늘의 국장 장세 "
        f"<span style='color:#94a3b8;font-size:0.78em;'>({scope} 전체 {total:,} 종목)</span>",
        unsafe_allow_html=True,
    )
    st.markdown(
        f"""
        <div style="display:flex;height:16px;border-radius:8px;overflow:hidden;background:#e5e7eb;margin:4px 0 6px;">
          <div style="width:{up_pct:.1f}%;background:#ef4444;"></div>
          <div style="width:{flat_pct:.1f}%;background:#cbd5e1;"></div>
          <div style="width:{down_pct:.1f}%;background:#3b82f6;"></div>
        </div>
        <div style="display:flex;justify-content:space-between;font-size:0.9em;">
          <span style="color:#ef4444;font-weight:700;">🔴 상승 {up:,} ({up_pct:.0f}%)</span>
          <span style="color:#64748b;">➖ 보합 {flat:,}</span>
          <span style="color:#3b82f6;font-weight:700;">하락 {down:,} ({down_pct:.0f}%) 🔵</span>
        </div>
        """,
        unsafe_allow_html=True,
    )


NAVER_API_HDRS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36",
    "Referer": "https://m.stock.naver.com/",
    "Accept": "application/json, text/plain, */*",
}


def _naver_json(url, timeout=7):
    """네이버 증권 API GET → JSON. 실패/비-JSON이면 None. (일시적 지연 대비 타임아웃 7초)"""
    try:
        r = requests.get(url, headers=NAVER_API_HDRS, timeout=timeout)
        if r.status_code != 200 or "json" not in r.headers.get("Content-Type", "").lower():
            return None
        return r.json()
    except Exception:
        return None


def _num(s):
    """'8,367.43' / '+20,409' / '-0.53' / '2.23' → float. 실패 시 None."""
    if s is None:
        return None
    try:
        return float(str(s).replace(',', '').replace('+', '').replace('%', '').strip())
    except Exception:
        return None


def _deep_find_number(obj, key_substrings, _depth=0):
    """[추가] 중첩 dict/list(JSON)에서 key 이름에 주어진 부분문자열이 들어간 첫 숫자값을 찾아 반환.
    네이버 API 응답의 정확한 필드명을 몰라도 '외국인/기관/개인' 같은 키를 자동 탐색하기 위함."""
    if _depth > 6 or obj is None:
        return None
    if isinstance(obj, dict):
        # 1) 이번 레벨에서 키 매칭 우선
        for k, v in obj.items():
            kl = str(k).lower()
            if any(s in kl for s in key_substrings) and isinstance(v, (int, float, str)):
                try:
                    n = float(str(v).replace(',', '').replace('+', '').replace('%', ''))
                    return n
                except Exception:
                    pass
        # 2) 못 찾으면 하위로 재귀
        for v in obj.values():
            r = _deep_find_number(v, key_substrings, _depth + 1)
            if r is not None:
                return r
    elif isinstance(obj, list):
        for v in obj:
            r = _deep_find_number(v, key_substrings, _depth + 1)
            if r is not None:
                return r
    return None


def _to_eok(val):
    """순매매 값을 '억원' 정수로 정규화. 네이버 API가 원 단위(예: -1401600000000)면 억으로 환산.
    이미 억 단위(예: -14016)면 그대로 사용. 백만/천 단위 등 애매한 경우 자릿수로 추정."""
    if val is None:
        return None
    try:
        v = float(val)
    except Exception:
        return None
    a = abs(v)
    if a >= 1e11:          # 원 단위(조 단위) → 억으로
        return int(round(v / 1e8))
    if a >= 1e8:           # 원 단위(억~조) → 억으로
        return int(round(v / 1e8))
    if a >= 1e6:           # 백만원 단위로 들어온 경우 → 억(=100백만)
        return int(round(v / 1e2))
    return int(round(v))   # 이미 억 단위로 추정


def _diag_index_endpoints():
    """[추가] 진단 도구: 후보 API에 직접 요청해 status code와 응답 앞부분을 화면에 출력.
    4개 신규 기능(미니차트/주요지수/시총TOP/업종등락)에 쓸 엔드포인트를 한 번에 점검한다."""
    HDRS = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36",
        "Referer": "https://m.stock.naver.com/",
        "Accept": "application/json, text/plain, */*",
    }
    groups = {
        "① 지수 시세/수급 (이미 작동)": [
            "https://m.stock.naver.com/api/index/KOSPI/basic",
            "https://m.stock.naver.com/api/index/KOSPI/integration",
            "https://m.stock.naver.com/api/index/KOSPI/trend",
        ],
        "② 지수 미니차트(일봉 스파크라인)": [
            "https://m.stock.naver.com/api/index/KOSPI/price?pageSize=30&page=1",
            "https://api.stock.naver.com/chart/domestic/index/KOSPI?periodType=dayCandle&count=30",
            "https://m.stock.naver.com/api/chart/domestic/index/KOSPI?periodType=dayCandle&count=30",
        ],
        "③ 주요지수/환율/유가 바": [
            "https://m.stock.naver.com/api/home/majorIndex",
            "https://m.stock.naver.com/api/index/KPI200/basic",
            "https://m.stock.naver.com/api/marketindex/exchange/FX_USDKRW",
            "https://api.stock.naver.com/marketindex/exchange/FX_USDKRW",
            "https://api.stock.naver.com/marketindex/oil/OIL_CL",
        ],
        "④ 시가총액 TOP 종목": [
            "https://m.stock.naver.com/api/stocks/marketValue/KOSPI?page=1&pageSize=10",
            "https://api.stock.naver.com/stock/marketValue/KOSPI?page=1&pageSize=10",
        ],
        "⑤ 업종/테마 등락률": [
            "https://m.stock.naver.com/api/stocks/industry?page=1&pageSize=20",
            "https://api.stock.naver.com/industry",
            "https://m.stock.naver.com/api/home/industry",
        ],
    }
    for title, urls in groups.items():
        st.markdown(f"### {title}")
        for u in urls:
            try:
                r = requests.get(u, headers=HDRS, timeout=5)
                ct = r.headers.get("Content-Type", "")
                ok = r.status_code == 200 and "json" in ct.lower()
                badge = "✅" if ok else "⚠️"
                body = r.text[:700] if r.text else ""
                st.markdown(f"{badge} **`{u}`** → `{r.status_code}` · `{ct}`")
                if body:
                    st.code(body, language="json")
            except Exception as e:
                st.markdown(f"❌ **`{u}`** → `{type(e).__name__}: {e}`")
    st.caption("✅ 표시된 URL의 JSON 응답(특히 키 이름)을 복사해 주시면, 4개 기능을 정확한 키로 완성하겠습니다.")


@st.cache_data(ttl=120)
def get_kr_index_panel():
    """[추가] 네이버 모바일 스타일 메인 지수 패널 데이터.
    코스피·코스닥 각각: 지수값/등락률/등락폭/상승·보합·하락 종목수 + 전체 투자자별 순매매(외국인/기관/개인).
    확인된 네이버 API 키 사용:
      - /index/{KOSPI|KOSDAQ}/basic   → closePrice, compareToPreviousClosePrice, fluctuationsRatio, compareToPreviousPrice.name(RISING/FALLING)
      - /index/{KOSPI|KOSDAQ}/trend   → personalValue(개인), foreignValue(외국인), institutionalValue(기관)  (단위: 억원, 부호 포함 문자열)
    상승/보합/하락 종목수는 지수 basic/integration에 없어 기존 get_kr_market_breadth() 폴백 사용."""
    def _scrape(mkt):
        price = diff = pct = None
        sign = 0
        forgn = inst = indiv = None

        # 1) 시세
        basic = _naver_json(f"https://m.stock.naver.com/api/index/{mkt}/basic")
        if basic:
            price = _num(basic.get("closePrice"))
            diff = _num(basic.get("compareToPreviousClosePrice"))
            pct = _num(basic.get("fluctuationsRatio"))
            nm = (basic.get("compareToPreviousPrice") or {}).get("name", "")
            sign = 1 if nm == "RISING" else (-1 if nm == "FALLING" else 0)
            if sign == 0 and diff is not None:
                sign = 1 if diff > 0 else (-1 if diff < 0 else 0)
            if diff is not None:
                diff = abs(diff)
            if pct is not None:
                pct = abs(pct)

        # 2) 투자자별 순매매 (억원)
        trend = _naver_json(f"https://m.stock.naver.com/api/index/{mkt}/trend")
        if trend:
            indiv = _num(trend.get("personalValue"))
            forgn = _num(trend.get("foreignValue"))
            inst = _num(trend.get("institutionalValue"))

        forgn = int(round(forgn)) if forgn is not None else None
        inst = int(round(inst)) if inst is not None else None
        indiv = int(round(indiv)) if indiv is not None else None

        # [폴백] 시세 실패 시 구형 finance.naver.com
        if price is None:
            try:
                fres = requests.get(
                    f"https://finance.naver.com/sise/sise_index.naver?code={mkt}",
                    headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"},
                    timeout=4,
                )
                fres.encoding = 'euc-kr'
                fsoup = BeautifulSoup(fres.text, 'html.parser')
                now_el = fsoup.select_one('#now_value')
                if now_el:
                    price = _num(now_el.get_text(strip=True))
                chg_el = fsoup.select_one('#change_value_and_rate')
                if chg_el:
                    nums = re.findall(r'[\d,]+\.\d+', chg_el.get_text(" ", strip=True))
                    if len(nums) >= 2:
                        if diff is None:
                            diff = _num(nums[0])
                        if pct is None:
                            pct = _num(nums[1])
                    cls = ' '.join(chg_el.get('class') or [])
                    if sign == 0:
                        sign = -1 if 'down' in cls else (1 if 'up' in cls else 0)
            except Exception:
                pass

        if price is None:
            return None
        return {
            "name": "코스피" if mkt == "KOSPI" else "코스닥",
            "price": price, "diff": diff, "pct": pct, "sign": sign,
            "up": None, "flat": None, "down": None,   # 종목수는 렌더에서 breadth 폴백으로 채움
            "forgn": forgn, "inst": inst, "indiv": indiv,
        }

    kospi = _scrape("KOSPI")
    kosdaq = _scrape("KOSDAQ")
    if not kospi and not kosdaq:
        return None
    return {"KOSPI": kospi, "KOSDAQ": kosdaq}


@st.cache_data(ttl=300)
def get_index_spark(mkt, n=30):
    """[추가] 지수 일봉 종가 배열(최신 n개) — 미니차트(스파크라인)용.
    /api/index/{mkt}/price 는 최신순 배열. 오래된→최신 순으로 정렬해 종가 리스트 반환."""
    data = _naver_json(f"https://m.stock.naver.com/api/index/{mkt}/price?pageSize={n}&page=1")
    if not isinstance(data, list) or not data:
        return None
    rows = []
    for it in data:
        c = _num(it.get("closePrice"))
        d = it.get("localTradedAt")
        if c is not None:
            rows.append((d, c))
    if len(rows) < 2:
        return None
    rows.reverse()  # 과거 → 현재
    return [c for _, c in rows]


@st.cache_data(ttl=120)
def get_major_indices():
    """[추가] 주요 지표 바: 코스피200 + 원/달러 환율. (유가 엔드포인트는 없어 제외)"""
    out = []
    kpi = _naver_json("https://m.stock.naver.com/api/index/KPI200/basic")
    if kpi:
        nm = (kpi.get("compareToPreviousPrice") or {}).get("name", "")
        out.append({
            "label": "코스피200",
            "value": _num(kpi.get("closePrice")),
            "pct": _num(kpi.get("fluctuationsRatio")),
            "sign": 1 if nm == "RISING" else (-1 if nm == "FALLING" else 0),
            "fmt": "{:,.2f}",
        })
    fx = _naver_json("https://api.stock.naver.com/marketindex/exchange/FX_USDKRW")
    if fx:
        info = fx.get("exchangeInfo", fx)
        nm = (info.get("fluctuationsType") or {}).get("name", "")
        out.append({
            "label": "원/달러",
            "value": _num(info.get("closePrice")),
            "pct": _num(info.get("fluctuationsRatio")),
            "sign": 1 if nm == "RISING" else (-1 if nm == "FALLING" else 0),
            "fmt": "{:,.2f}원",
        })
    return out or None


@st.cache_data(ttl=120)
def get_marketcap_top(mkt="KOSPI", n=10):
    """[추가] 시가총액 TOP 종목 — /api/stocks/marketValue/{mkt}."""
    data = _naver_json(f"https://m.stock.naver.com/api/stocks/marketValue/{mkt}?page=1&pageSize={n}")
    if not data or "stocks" not in data:
        return None
    rows = []
    for s in data["stocks"][:n]:
        nm = (s.get("compareToPreviousPrice") or {}).get("name", "")
        rows.append({
            "code": s.get("itemCode"),
            "name": s.get("stockName"),
            "price": _num(s.get("closePrice")),
            "pct": _num(s.get("fluctuationsRatio")),
            "sign": 1 if nm == "RISING" else (-1 if nm == "FALLING" else 0),
            "cap": s.get("marketValueHangeul"),
        })
    return rows or None


@st.cache_data(ttl=180)
def get_industry_changes(n=20):
    """[추가] 업종별 등락률 — /api/stocks/industry. changeRate 기준 정렬돼 옴."""
    data = _naver_json(f"https://m.stock.naver.com/api/stocks/industry?page=1&pageSize={n}")
    if not data or "groups" not in data:
        return None
    rows = []
    for g in data["groups"]:
        rows.append({
            "name": g.get("name"),
            "rate": _num(g.get("changeRate")),
            "rise": g.get("riseCount"),
            "fall": g.get("fallCount"),
            "total": g.get("totalCount"),
        })
    return rows or None


def _sparkline_svg(vals, sign, w=120, h=36):
    """[추가] 종가 리스트 → 미니 라인차트(SVG). 상승=빨강/하락=파랑."""
    if not vals or len(vals) < 2:
        return ""
    color = "#ef4444" if sign > 0 else ("#3b82f6" if sign < 0 else "#64748b")
    lo, hi = min(vals), max(vals)
    rng = (hi - lo) or 1
    n = len(vals)
    pts = []
    for i, v in enumerate(vals):
        x = i / (n - 1) * (w - 4) + 2
        y = h - 2 - (v - lo) / rng * (h - 4)
        pts.append(f"{x:.1f},{y:.1f}")
    pts_str = " ".join(pts)
    # 면적 채우기 좌표
    area = f"2,{h} " + pts_str + f" {w-2},{h}"
    return (
        f'<svg width="{w}" height="{h}" viewBox="0 0 {w} {h}" style="display:block;">'
        f'<polygon points="{area}" fill="{color}" opacity="0.10"/>'
        f'<polyline points="{pts_str}" fill="none" stroke="{color}" stroke-width="1.6" '
        f'stroke-linejoin="round" stroke-linecap="round"/></svg>'
    )


def _index_card_html(d, spark=None):
    """이미지(네이버 모바일) 스타일 개별 지수 카드 HTML."""
    if not d:
        return ""
    up_c, flat_c, down_c = "#ef4444", "#94a3b8", "#3b82f6"
    sign = d.get("sign", 0)
    val_color = up_c if sign > 0 else (down_c if sign < 0 else "#334155")
    arrow = "▲" if sign > 0 else ("▼" if sign < 0 else "■")
    psign = "+" if sign > 0 else ("-" if sign < 0 else "")
    pct = d.get("pct")
    diff = d.get("diff")
    pct_str = f"{psign}{pct:.2f}%" if pct is not None else ""
    diff_str = f"{arrow} {diff:,.2f}" if diff is not None else ""
    up, flat, down = d.get("up"), d.get("flat"), d.get("down")
    spark_svg = _sparkline_svg(spark, sign) if spark else ""
    # 등락 막대 (상승=빨강 / 보합=회색 / 하락=파랑)
    bar = ""
    if up is not None and down is not None:
        tot = (up or 0) + (flat or 0) + (down or 0)
        if tot > 0:
            up_p = (up or 0) / tot * 100
            flat_p = (flat or 0) / tot * 100
            down_p = max(0.0, 100 - up_p - flat_p)
            bar = (
                f'<div style="display:flex;height:8px;border-radius:5px;overflow:hidden;'
                f'background:#e5e7eb;margin-top:10px;">'
                f'<div style="width:{up_p:.1f}%;background:{up_c};"></div>'
                f'<div style="width:{flat_p:.1f}%;background:{flat_c};"></div>'
                f'<div style="width:{down_p:.1f}%;background:{down_c};"></div></div>'
            )
    cnt = ""
    if up is not None and down is not None:
        cnt = (
            f'<span style="color:{up_c};font-weight:700;">↗{up:,}</span>'
            f'<span style="color:{flat_c};margin:0 6px;">{flat or 0:,}</span>'
            f'<span style="color:{down_c};font-weight:700;">↘{down:,}</span>'
        )
    return (
        f'<div style="padding:14px 4px;">'
        f'<div style="display:flex;justify-content:space-between;align-items:center;">'
        f'<span style="font-size:20px;font-weight:800;color:#1e293b;">{d["name"]}</span>'
        f'<span style="font-size:13px;">{cnt}</span></div>'
        f'<div style="margin-top:6px;display:flex;align-items:flex-end;justify-content:space-between;gap:10px;">'
        f'<div style="display:flex;align-items:baseline;gap:10px;flex-wrap:wrap;">'
        f'<span style="font-size:28px;font-weight:800;color:#1e293b;">{d["price"]:,.2f}</span>'
        f'<span style="font-size:16px;font-weight:700;color:{val_color};">{pct_str}</span>'
        f'<span style="font-size:15px;color:{val_color};">{diff_str}</span></div>'
        f'<div style="flex-shrink:0;">{spark_svg}</div></div>'
        f'{bar}</div>'
    )


def _flow_bar_html(label, val):
    """투자자별 순매매 한 줄 (외국인/기관/개인). val 단위: 억원(정수, +매수/-매도)."""
    buy_c, sell_c = "#ef4444", "#3b82f6"
    if val is None:
        return (
            f'<div style="display:flex;align-items:center;justify-content:space-between;margin:8px 0;">'
            f'<span style="width:52px;color:#475569;font-weight:600;">{label}</span>'
            f'<span style="flex:1;height:8px;background:#eef2f6;border-radius:5px;margin:0 14px;"></span>'
            f'<span style="color:#94a3b8;font-weight:700;min-width:96px;text-align:right;">조회불가</span></div>'
        )
    color = buy_c if val >= 0 else sell_c
    sign = "+" if val >= 0 else "-"
    mag = min(abs(val) / 20000.0, 1.0)  # 2조원=풀바 기준 (시각용)
    half = mag * 50.0
    if val >= 0:
        fill = f'<div style="position:absolute;left:50%;width:{half:.1f}%;height:100%;background:{color};border-radius:5px;"></div>'
    else:
        fill = f'<div style="position:absolute;right:50%;width:{half:.1f}%;height:100%;background:{color};border-radius:5px;"></div>'
    return (
        f'<div style="display:flex;align-items:center;justify-content:space-between;margin:8px 0;">'
        f'<span style="width:52px;color:#475569;font-weight:600;">{label}</span>'
        f'<span style="flex:1;position:relative;height:8px;background:#eef2f6;border-radius:5px;margin:0 14px;">{fill}'
        f'<span style="position:absolute;left:50%;top:-2px;width:1px;height:12px;background:#cbd5e1;"></span></span>'
        f'<span style="color:{color};font-weight:800;min-width:96px;text-align:right;">{sign}{abs(val):,}억</span></div>'
    )


def render_main_index_panel():
    """[추가] 메인페이지 상단 — 네이버 모바일 스타일 코스피/코스닥 + 오늘의 시장 + 투자자별 순매매."""
    data = get_kr_index_panel()
    if not data:
        st.warning("📊 지수 패널을 일시적으로 불러오지 못했습니다 (네이버 응답 지연). 잠시 후 다시 시도해 주세요.")
        if st.button("🔄 다시 시도", key="retry_index_panel"):
            get_kr_index_panel.clear()
            st.rerun()
        with st.expander("🔧 진단: 어떤 응답이 오는지 확인 (펼치기)"):
            _diag_index_endpoints()
        return

    # 시장 국면(신호등) → '오늘의 시장' 한 줄 요약 + 게이지 위치
    try:
        reg = get_market_regime()
        light, title, _ = reg.get('verdict', ("🟡", "중립", ""))
    except Exception:
        light, title = "🟡", "중립"
    regime_map = {"🟢": ("좋아요", "#22c55e", 88), "🟡": ("중립", "#f59e0b", 50), "🔴": ("조심해요", "#ef4444", 14)}
    reg_label, reg_color, reg_pos = regime_map.get(light, ("중립", "#f59e0b", 50))

    kospi = data.get("KOSPI")
    kosdaq = data.get("KOSDAQ")

    # [폴백] API에서 종목수(상승/보합/하락)를 못 받았으면 기존 집계 함수로 보완 (코스피+코스닥 합산값)
    try:
        if (kospi and kospi.get("up") is None) or (kosdaq and kosdaq.get("up") is None):
            b = get_kr_market_breadth()
            if b:
                # 단일 합산값뿐이라, 어느 한쪽 카드에만 합산 막대를 채우기보다
                # 비율만 맞춰 양쪽 카드에 동일 비율 막대를 적용 (시각적 참고용)
                for card in (kospi, kosdaq):
                    if card and card.get("up") is None:
                        card["up"], card["flat"], card["down"] = b["up"], b["flat"], b["down"]
    except Exception:
        pass

    cards = ""
    if kospi:
        cards += _index_card_html(kospi, spark=get_index_spark("KOSPI"))
    if kospi and kosdaq:
        cards += '<div style="height:1px;background:#eef2f6;margin:2px 0;"></div>'
    if kosdaq:
        cards += _index_card_html(kosdaq, spark=get_index_spark("KOSDAQ"))

    # 투자자별 순매매: 코스피 기준 (코스피 trend 값)
    src = kospi if (kospi and kospi.get("forgn") is not None) else kosdaq
    f_v = src.get("forgn") if src else None
    i_v = src.get("inst") if src else None
    p_v = src.get("indiv") if src else None

    flows = (
        _flow_bar_html("외국인", f_v)
        + _flow_bar_html("기관", i_v)
        + _flow_bar_html("개인", p_v)
    )

    gauge = (
        f'<div style="display:flex;align-items:center;gap:8px;margin-top:4px;">'
        f'<span style="color:#ef4444;">●</span>'
        f'<span style="font-weight:800;font-size:17px;color:#1e293b;">오늘의 시장</span>'
        f'<span style="color:#94a3b8;">ⓘ</span>'
        f'<span style="font-weight:800;font-size:17px;color:{reg_color};margin-left:2px;">{reg_label}</span>'
        f'<span style="flex:1;position:relative;height:6px;border-radius:5px;margin-left:10px;'
        f'background:linear-gradient(90deg,#3b82f6,#cbd5e1,#ef4444);">'
        f'<span style="position:absolute;left:{reg_pos}%;top:-4px;width:14px;height:14px;border-radius:50%;'
        f'background:#fff;border:2px solid {reg_color};transform:translateX(-50%);"></span></span></div>'
    )

    st.markdown(
        f"""
        <div style="background:#fff;border:1px solid #e9eef3;border-radius:16px;
                    padding:6px 18px 14px;box-shadow:0 1px 3px rgba(0,0,0,0.04);">
          {cards}
        </div>
        <div style="background:#fff5f5;border:1px solid #fcdcdc;border-radius:16px;
                    padding:14px 18px;margin-top:10px;">
          {gauge}
          <div style="margin-top:12px;">{flows}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    st.caption("💡 외국인·기관·개인 순매매(억원)는 코스피 전체 기준 · 빨강=순매수 / 파랑=순매도. 장중 잠정치이며 마감 후 거래소가 확정합니다.")

    # 주요 지표 바 (코스피200 / 원·달러)
    render_major_indices_bar()


def render_major_indices_bar():
    """[추가] 코스피200 + 원/달러 환율 한 줄 바."""
    items = get_major_indices()
    if not items:
        return
    cells = ""
    for it in items:
        sign = it.get("sign", 0)
        c = "#ef4444" if sign > 0 else ("#3b82f6" if sign < 0 else "#64748b")
        arrow = "▲" if sign > 0 else ("▼" if sign < 0 else "")
        v = it.get("value")
        pct = it.get("pct")
        vstr = it["fmt"].format(v) if v is not None else "-"
        pstr = f'{arrow} {abs(pct):.2f}%' if pct is not None else ""
        cells += (
            f'<div style="flex:1;text-align:center;padding:6px 4px;">'
            f'<div style="font-size:12px;color:#64748b;">{it["label"]}</div>'
            f'<div style="font-size:15px;font-weight:800;color:#1e293b;">{vstr}</div>'
            f'<div style="font-size:12px;font-weight:700;color:{c};">{pstr}</div></div>'
        )
    st.markdown(
        f'<div style="display:flex;background:#fff;border:1px solid #e9eef3;border-radius:14px;'
        f'padding:6px;margin-top:10px;box-shadow:0 1px 3px rgba(0,0,0,0.04);">{cells}</div>',
        unsafe_allow_html=True,
    )


def render_marketcap_top(mkt="KOSPI", n=10):
    """[추가] 시가총액 TOP 종목 리스트. CSS Grid로 칸 폭 고정 → 숫자 정렬 흐트러짐 방지."""
    rows = get_marketcap_top(mkt, n)
    if not rows:
        st.caption("📊 시가총액 TOP 종목을 불러오지 못했습니다.")
        return
    # 컬럼: [순위 18] [종목명 1fr] [가격 70] [등락률 62] — 절반 폭 컬럼에서 잘리지 않게 축소
    GRID = "grid-template-columns:18px minmax(0,1fr) 70px 62px;"
    body = ""
    for i, r in enumerate(rows, 1):
        sign = r.get("sign", 0)
        c = "#ef4444" if sign > 0 else ("#3b82f6" if sign < 0 else "#64748b")
        arrow = "▲" if sign > 0 else ("▼" if sign < 0 else "")
        pct = r.get("pct")
        pstr = f'{arrow}{abs(pct):.2f}%' if pct is not None else ""
        price = f'{r["price"]:,.0f}' if r.get("price") is not None else "-"
        border = "border-bottom:1px solid #f1f5f9;" if i < len(rows) else ""
        body += (
            f'<div style="display:grid;{GRID}align-items:center;column-gap:6px;padding:8px 0;{border}box-sizing:border-box;">'
            f'<span style="color:#94a3b8;font-weight:700;font-size:12px;">{i}</span>'
            f'<div style="min-width:0;overflow:hidden;">'
            f'<div style="font-weight:700;color:#1e293b;font-size:13px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;">{r["name"]}</div>'
            f'<div style="font-size:10px;color:#94a3b8;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;">{r.get("cap","")}</div></div>'
            f'<span style="text-align:right;color:#1e293b;font-size:12px;white-space:nowrap;overflow:hidden;">{price}</span>'
            f'<span style="text-align:right;color:{c};font-weight:700;font-size:12px;white-space:nowrap;overflow:hidden;">{pstr}</span>'
            f'</div>'
        )
    st.markdown(
        f'<div style="background:#fff;border:1px solid #e9eef3;border-radius:14px;'
        f'padding:2px 14px;box-sizing:border-box;overflow:hidden;">{body}</div>',
        unsafe_allow_html=True,
    )


def render_industry_changes(n=12):
    """[추가] 업종별 등락률. CSS Grid로 [업종명][막대][%] 3칸 고정."""
    rows = get_industry_changes(30)
    if not rows:
        st.caption("📊 업종별 등락률을 불러오지 못했습니다.")
        return
    rows = [r for r in rows if r.get("rate") is not None]
    top = sorted(rows, key=lambda x: x["rate"], reverse=True)[:n]
    max_abs = max((abs(r["rate"]) for r in top), default=1) or 1
    # 컬럼: [업종명 88] [막대 1fr] [% 60]
    GRID = "grid-template-columns:88px minmax(0,1fr) 60px;"
    def _row(r):
        rate = r["rate"]
        c = "#ef4444" if rate > 0 else ("#3b82f6" if rate < 0 else "#64748b")
        arrow = "▲" if rate > 0 else ("▼" if rate < 0 else "")
        w = abs(rate) / max_abs * 100
        return (
            f'<div style="display:grid;{GRID}align-items:center;column-gap:8px;padding:7px 0;box-sizing:border-box;">'
            f'<span style="font-weight:600;color:#1e293b;font-size:12px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;">{r["name"]}</span>'
            f'<span style="height:8px;background:#f1f5f9;border-radius:5px;position:relative;min-width:0;">'
            f'<span style="position:absolute;left:0;width:{w:.0f}%;height:100%;background:{c};border-radius:5px;"></span></span>'
            f'<span style="text-align:right;color:{c};font-weight:700;font-size:12px;white-space:nowrap;overflow:hidden;">{arrow}{abs(rate):.2f}%</span>'
            f'</div>'
        )
    body = "".join(_row(r) for r in top)
    st.markdown(
        f'<div style="background:#fff;border:1px solid #e9eef3;border-radius:14px;'
        f'padding:6px 14px;box-sizing:border-box;overflow:hidden;">{body}</div>',
        unsafe_allow_html=True,
    )


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
    """일별 시세 + 투자자별 순매매(외국인·기관·개인) — 네이버 모바일 trend API.
    종가·전일비·등락률·수급을 '같은 소스의 같은 날짜 확정치'로 받아 표 정합성을 보장한다.
    (기존 frgn HTML은 개인을 -(외인+기관) 추정으로 채워 첫 행과 어긋나는 문제가 있었음)
    수급 단위는 '주식 수'."""
    if not str(code).isdigit():
        return pd.DataFrame()
    try:
        url = f"https://m.stock.naver.com/api/stock/{code}/trend"
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            "Referer": f"https://m.stock.naver.com/domestic/stock/{code}/total",
            "Accept": "application/json",
        }
        res = requests.get(url, headers=headers, timeout=5)
        if res.status_code != 200:
            return pd.DataFrame()
        rows = res.json()
        if isinstance(rows, dict):
            for k in ("trends", "result", "list", "data"):
                if isinstance(rows.get(k), list):
                    rows = rows[k]; break
        if not isinstance(rows, list) or not rows:
            return pd.DataFrame()

        def _num(v):
            if v is None: return None
            s = str(v).replace(',', '').replace('+', '').strip()
            return int(s) if s.lstrip('-').isdigit() else None

        def fmt_vol(v):
            if v is None: return "-"
            if v > 0: return f"🔴 +{v:,}"
            if v < 0: return f"🔵 {v:,}"
            return "0"

        data = []
        for row in rows[:10]:
            bd = str(row.get("bizdate", ""))
            date = f"{bd[0:4]}.{bd[4:6]}.{bd[6:8]}" if len(bd) == 8 and bd.isdigit() else bd
            close = str(row.get("closePrice", "")).strip()
            chg = _num(row.get("compareToPreviousClosePrice"))
            sign_txt = (row.get("compareToPreviousPrice") or {}).get("text", "")
            diff = f"{sign_txt} {abs(chg):,}" if chg is not None else "-"
            close_n = _num(close)
            if close_n is not None and chg is not None and (close_n - chg) != 0:
                rate = f"{'+' if chg > 0 else ''}{chg / (close_n - chg) * 100:.2f}%"
            else:
                rate = "-"
            f_v = _num(row.get("foreignerPureBuyQuant"))
            i_v = _num(row.get("organPureBuyQuant"))
            d_v = _num(row.get("individualPureBuyQuant"))
            data.append({
                "날짜": date, "종가": close, "전일비": diff, "등락률": rate,
                "외국인": fmt_vol(f_v), "기관": fmt_vol(i_v), "개인": fmt_vol(d_v),
            })
        return pd.DataFrame(data)
    except Exception:
        return pd.DataFrame()

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

# =====================================================================
# [v7.0 신규] ① 멀티 타임프레임 — 주봉 추세 판정
# 일봉 df를 주봉으로 리샘플링 → 주봉 이평선 배열로 큰 추세를 확인.
# "일봉 타점 + 주봉 상승"이 겹칠 때 가짜 신호가 크게 줄어듭니다.
# =====================================================================
def get_weekly_trend(daily_df):
    try:
        if daily_df is None or daily_df.empty or len(daily_df) < 35:
            return "❔ 주봉 데이터 부족"
        # 일봉 OHLCV → 주봉(매주 금요일 기준) 리샘플링
        wdf = daily_df.resample('W-FRI').agg({
            'Open': 'first', 'High': 'max', 'Low': 'min', 'Close': 'last', 'Volume': 'sum'
        }).dropna()
        if len(wdf) < 11:
            return "❔ 주봉 데이터 부족"
        wdf['WMA5'] = wdf['Close'].rolling(5).mean()
        wdf['WMA10'] = wdf['Close'].rolling(10).mean()
        wdf['WMA20'] = wdf['Close'].rolling(20).mean()
        last = wdf.iloc[-1]
        w5, w10, w20 = last['WMA5'], last['WMA10'], last['WMA20']
        price = last['Close']
        # 20주선이 없으면(데이터 짧음) 5/10주선만으로 판정
        if pd.isna(w20):
            if pd.notna(w5) and pd.notna(w10):
                if price > w5 > w10: return "🔥 주봉 상승추세"
                elif price < w5 < w10: return "❄️ 주봉 하락추세"
            return "🌀 주봉 중립"
        if w5 > w10 > w20: return "🔥 주봉 상승추세"
        elif w5 < w10 < w20: return "❄️ 주봉 하락추세"
        else: return "🌀 주봉 중립"
    except Exception:
        return "❔ 주봉 분석불가"


# =====================================================================
# [v7.0 신규] ② 시장 국면 대시보드 — "지금 매매해도 되는 장인가?"
# KOSPI/KOSDAQ 지수의 이평선 배열·추세 + 시장 폭(상승/하락 종목 비율)으로
# 🟢매수우호 / 🟡중립 / 🔴위험 신호등을 산출합니다.
# =====================================================================
@st.cache_data(ttl=900)
def get_market_regime():
    result = {}

    def analyze_index(code, name):
        try:
            df = fdr.DataReader(code)
            if df.empty or len(df) < 65:
                return None
            df = df.tail(120).copy()
            df['MA5'] = df['Close'].rolling(5).mean()
            df['MA20'] = df['Close'].rolling(20).mean()
            df['MA60'] = df['Close'].rolling(60).mean()
            last = df.iloc[-1]
            ma20_prev = df['MA20'].iloc[-6]  # 5거래일 전 20일선 (기울기)
            price, ma5, ma20, ma60 = last['Close'], last['MA5'], last['MA20'], last['MA60']
            ma20_rising = ma20 > ma20_prev

            # RSI(14)
            delta = df['Close'].diff()
            gain = delta.where(delta > 0, 0.0).rolling(14).mean()
            loss = (-delta.where(delta < 0, 0.0)).rolling(14).mean()
            rs = gain / loss.replace(0, np.nan)
            rsi = float((100 - (100 / (1 + rs))).iloc[-1])

            # 점수화: 정배열·이평선 위·우상향일수록 가산
            score = 0
            if ma5 > ma20 > ma60: score += 2     # 완전 정배열
            elif ma5 > ma20: score += 1
            if price > ma20: score += 1
            if ma20_rising: score += 1
            if ma5 < ma20 < ma60: score -= 2     # 역배열
            elif ma5 < ma20: score -= 1
            if price < ma20: score -= 1

            if score >= 3: light = "🟢"
            elif score <= -2: light = "🔴"
            else: light = "🟡"

            pct = (price / df['Close'].iloc[-2] - 1) * 100 if len(df) > 1 else 0
            return {
                "name": name, "light": light, "score": score,
                "price": float(price), "pct": float(pct), "rsi": rsi,
                "ma20_rising": ma20_rising, "above_ma20": price > ma20,
                "align": "정배열" if ma5 > ma20 > ma60 else ("역배열" if ma5 < ma20 < ma60 else "혼조"),
            }
        except Exception:
            return None

    result['KOSPI'] = analyze_index('KS11', 'KOSPI')
    result['KOSDAQ'] = analyze_index('KQ11', 'KOSDAQ')

    # 시장 폭(Breadth): 상승 vs 하락 종목 비율
    breadth = None
    try:
        listing = fdr.StockListing('KOSPI')
        chg_col = next((c for c in ['ChagesRatio', 'ChangesRatio', 'ChangeRatio', 'Changes'] if c in listing.columns), None)
        if chg_col:
            vals = pd.to_numeric(listing[chg_col], errors='coerce').dropna()
            up = int((vals > 0).sum())
            down = int((vals < 0).sum())
            flat = int((vals == 0).sum())
            total = up + down + flat
            if total > 0:
                breadth = {"up": up, "down": down, "flat": flat,
                           "up_ratio": round(up / total * 100, 1)}
    except Exception:
        breadth = None
    result['breadth'] = breadth

    # 종합 신호등
    scores = [v['score'] for k, v in result.items() if isinstance(v, dict) and 'score' in v]
    avg = sum(scores) / len(scores) if scores else 0
    if breadth:
        if breadth['up_ratio'] >= 60: avg += 0.5
        elif breadth['up_ratio'] <= 40: avg -= 0.5
    if avg >= 2:
        result['verdict'] = ("🟢", "매수 우호적인 장", "추세·타점 신호가 나오면 적극 대응 가능한 환경입니다.")
    elif avg <= -1:
        result['verdict'] = ("🔴", "위험 — 신규 진입 자제", "시장이 약합니다. 현금 비중을 늘리고 손절을 타이트하게 가져가세요.")
    else:
        result['verdict'] = ("🟡", "중립 / 혼조", "선별적으로만 대응하세요. 강한 신호(정배열+거래량+수급)만 골라 진입.")
    return result


def render_market_regime_banner():
    """홈/경보 화면 상단에 시장 국면 신호등 배너를 그립니다."""
    try:
        reg = get_market_regime()
    except Exception:
        return
    light, title, desc = reg.get('verdict', ("🟡", "데이터 지연", ""))
    bg = {"🟢": "rgba(40,167,69,0.12)", "🟡": "rgba(255,193,7,0.12)", "🔴": "rgba(220,53,69,0.12)"}.get(light, "rgba(120,120,120,0.1)")
    border = {"🟢": "#28a745", "🟡": "#ffc107", "🔴": "#dc3545"}.get(light, "#888")
    st.markdown(
        f"""<div style="background:{bg};border:1px solid {border};border-radius:10px;padding:12px 16px;margin-bottom:10px;">
        <span style="font-size:20px;font-weight:700;">{light} 오늘의 시장 국면: {title}</span><br>
        <span style="font-size:13px;color:#666;">{desc}</span></div>""",
        unsafe_allow_html=True)
    cols = st.columns(3)
    for i, key in enumerate(['KOSPI', 'KOSDAQ']):
        d = reg.get(key)
        if isinstance(d, dict):
            cols[i].metric(f"{d['light']} {d['name']} ({d['align']})",
                           f"{d['price']:,.2f}", f"{d['pct']:+.2f}%")
    b = reg.get('breadth')
    if b:
        cols[2].metric("📊 시장 폭 (상승종목 비율)", f"{b['up_ratio']}%",
                       f"▲{b['up']} ▼{b['down']}", delta_color="off")


# =====================================================================
# [v7.0 신규] ③ 공매도 & 빚투(신용) 리스크 진단 — 한국 시장 특화
# 공매도: pykrx로 거래 비중 + 잔고 비중 산출 (신뢰도 높음)
# 신용잔고: 무료 공개 소스가 제한적이라 네이버 베스트에포트(환경 따라 조정 필요)
# =====================================================================
def _krx_retry(fn, *args, retries=3, **kwargs):
    """pykrx(→KRX) 호출 우회/안정화 래퍼.
    KRX 는 해외·클라우드 IP 를 자주 차단/지연시키므로:
      ① 일시적 통신 지연 → 짧은 백오프로 재시도
      ② 하드 IP 차단     → st.secrets['KRX_PROXY'] 또는 환경변수 KRX_PROXY 가
                            설정돼 있으면 '한국 IP 프록시'로 우회 시도
    프록시 미설정 시 기존과 동일하게 직접 호출(재시도만 적용)."""
    proxy = None
    try:
        proxy = st.secrets.get("KRX_PROXY")
    except Exception:
        proxy = None
    proxy = proxy or os.environ.get("KRX_PROXY")

    keys = ("HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy")
    saved = {}
    if proxy:
        for k in keys:
            saved[k] = os.environ.get(k)
            os.environ[k] = proxy
    try:
        for i in range(max(1, retries)):
            try:
                res = fn(*args, **kwargs)
                # DataFrame 은 '비어있지 않을 때'만 성공으로 간주
                if res is not None and not getattr(res, "empty", False):
                    return res
            except Exception:
                pass
            time.sleep(0.7 * (i + 1))
        return None
    finally:
        if proxy:   # 환경변수 원복 (yfinance 등 다른 요청에 영향 없도록)
            for k in keys:
                v = saved.get(k)
                if v is None:
                    os.environ.pop(k, None)
                else:
                    os.environ[k] = v


@st.cache_data(ttl=3600)
def get_short_selling_risk(code):
    if not str(code).isdigit() or not HAS_PYKRX:
        return None
    try:
        today = datetime.now()
        frm = (today - timedelta(days=40)).strftime("%Y%m%d")
        to = today.strftime("%Y%m%d")

        out = {}
        # (1) 공매도 거래 비중 — 오늘 거래량 중 공매도 비율
        try:
            vol = _krx_retry(pykrx_stock.get_shorting_volume_by_date, frm, to, code)
            if vol is not None and not vol.empty and '비중' in vol.columns:
                ratio = vol['비중'].dropna()  # 0~1 또는 % 형태 (라이브러리 버전차)
                if not ratio.empty:
                    latest = float(ratio.iloc[-1])
                    avg5 = float(ratio.tail(5).mean())
                    # 0~1 스케일이면 %로 변환
                    if latest <= 1.5:
                        latest *= 100; avg5 *= 100
                    out['short_vol_ratio'] = round(latest, 2)
                    out['short_vol_avg5'] = round(avg5, 2)
                    out['short_vol_trend'] = "📈 증가" if latest > avg5 * 1.1 else ("📉 감소" if latest < avg5 * 0.9 else "➖ 유지")
        except Exception:
            pass

        # (2) 공매도 잔고 비중 — 전체 주식 중 공매도로 잠긴 비율
        try:
            bal = _krx_retry(pykrx_stock.get_shorting_balance_by_date, frm, to, code)
            if bal is not None and not bal.empty and '비중' in bal.columns:
                br = bal['비중'].dropna()
                if not br.empty:
                    out['short_bal_ratio'] = round(float(br.iloc[-1]), 2)
                    if len(br) >= 5:
                        out['short_bal_trend'] = "📈 증가" if br.iloc[-1] > br.tail(5).mean() else "📉 감소"
        except Exception:
            pass

        if not out:
            return None

        # 위험도 종합 판정
        svr = out.get('short_vol_ratio', 0)
        sbr = out.get('short_bal_ratio', 0)
        if svr >= 20 or sbr >= 3.0:
            out['level'] = ("🔴", "공매도 과열 — 단기 하락 압력 큼 (단, 숏스퀴즈 반등 가능성도)")
        elif svr >= 10 or sbr >= 1.5:
            out['level'] = ("🟡", "공매도 보통 — 흐름 주시 필요")
        else:
            out['level'] = ("🟢", "공매도 부담 낮음")
        return out
    except Exception:
        return None


@st.cache_data(ttl=3600)
def get_credit_balance_naver(code):
    """신용잔고(빚투) 베스트에포트 스크래핑. 실패 시 None.
    ※ 무료 소스가 불안정하여 환경에 따라 조정이 필요할 수 있습니다."""
    if not str(code).isdigit():
        return None
    try:
        url = f"https://finance.naver.com/item/coinfo.naver?code={code}"
        res = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=3)
        text = BeautifulSoup(res.text, 'html.parser').get_text(separator=' ', strip=True)
        m = re.search(r'신용[가-힣]*잔고[율]?\s*([0-9.]+)\s*%', text)
        if m:
            return {"credit_ratio": float(m.group(1))}
    except Exception:
        pass
    return None


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

        # [v7.0] 멀티 타임프레임: 주봉 추세 판정
        weekly_trend = get_weekly_trend(analysis_df)
        
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
        sector_val = "기타/분류불가"
        if not krx_df.empty and not is_us:
            match_sec = krx_df[krx_df['Code'] == ticker_code]['Sector']
            if not match_sec.empty and pd.notna(match_sec.iloc[0]):
                raw_sec = str(match_sec.iloc[0])
                sector_val = raw_sec.replace(" 및 공급업", "").replace(" 제조업", "").replace(" 제조 및", "").replace(" 도매업", "").replace(" 소매업", "")
        
        # 🔥 [강력한 해결책] KRX 서버가 막혀서 '기타/분류불가'가 뜨면, 네이버 증권에서 실시간으로 섹터를 긁어옵니다.
        if not is_us and sector_val in ['기타/분류불가', 'ETF/미국주식/분류없음', '기타', '']:
            try:
                url = f"https://finance.naver.com/item/main.naver?code={ticker_code}"
                res = requests.get(url, headers={'User-Agent': 'Mozilla/5.0'}, timeout=3)
                soup = BeautifulSoup(res.text, 'html.parser')
                
                # 🛠️ [핵심 수정] 재무정보가 딸려오지 않게, 업종 전용 링크 태그(a)만 핀포인트로 타겟팅합니다.
                sec_tag = soup.select_one('a[href*="/sise/sise_group_detail.naver"]')
                if sec_tag:
                    sector_val = sec_tag.text.strip()
            except Exception:
                sector_val = "개별이슈/기타"
                
# 👇 수정된 미국 주식 섹터 파싱 로직
        if is_us:
            try:
                info = yf.Ticker(ticker_code).info
                raw_sector = info.get('sector', '미국주식')
                
                # 영문 섹터명을 한글로 매핑
                sector_map = {
                    "Technology": "IT/기술", 
                    "Financial Services": "금융", 
                    "Healthcare": "헬스케어/바이오", 
                    "Consumer Cyclical": "임의소비재",
                    "Industrials": "산업재", 
                    "Communication Services": "통신/플랫폼",
                    "Consumer Defensive": "필수소비재", 
                    "Energy": "에너지",
                    "Basic Materials": "소재", 
                    "Real Estate": "부동산", 
                    "Utilities": "유틸리티"
                }
                sector_val = sector_map.get(raw_sector, raw_sector)
            except Exception:
                sector_val = "미국주식"
        
        return {
            "종목명": stock_name, "티커": ticker_code, "섹터": sector_val, "현재가": current_price, "상태": status,
            "진입가_가이드": ma20_val, "목표가1": target_1, "목표가2": target_2, "목표가3": target_3, "손절가": ma20_val * 0.97,
            "거래량 급증": "🔥 거래량 터짐" if analysis_df.iloc[-10:]['Volume'].max() > (analysis_df.iloc[-10:]['Vol_MA20'].mean() * 2) else "평이함",
            "RSI": latest['RSI'], "배열상태": align_status, "주봉추세": weekly_trend,
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
        
@st.cache_data(ttl=86400, max_entries=500)
def get_granular_themes(stock_name: str, api_key: str) -> list:
    if not api_key:
        return ["API_KEY_MISSING"]
    
    try:
        genai.configure(api_key=api_key)
        
        prompt = f"""
        대상 기업: [{stock_name}]
        이 기업의 핵심 사업 모델과 현재 주식 시장에서 편입되어 있는 구체적인 테마/섹터를 3~5개의 단어로 추출하세요.
        - 지시사항 1: 'IT', '제조' 같은 포괄적인 단어는 제외합니다.
        - 지시사항 2: 'AI 데이터센터 인프라', 'HBM', '전력기기', '토큰증권', '온디바이스 AI' 등 실전 투자에서 쓰이는 구체적인 밸류체인 용어를 사용하세요.
        - 지시사항 3: 반드시 아래의 JSON 배열 형식으로만 출력하세요. 마크다운 기호나 추가 설명은 절대 포함하지 마세요.
        
        출력 예시:
        ["메모리 반도체", "파운드리", "온디바이스 AI"]
        """
        
        # 시스템 통합 모델 버전 적용
        model = genai.GenerativeModel('gemini-3.1-flash-lite')
        response = model.generate_content(prompt)
        
        text = response.text.strip()
        if text.startswith("```json"):
            text = text[7:-3].strip()
        elif text.startswith("```"):
            text = text[3:-3].strip()
            
        themes = json.loads(text)
        
        if isinstance(themes, list):
            return themes
        else:
            return ["분류 오류"]
            
    except Exception as e:
        import logging
        logging.error(f"[{stock_name}] 테마 추출 실패: {e}")
        return ["데이터 확인 필요"]

def render_multi_theme_dataframe(df: pd.DataFrame, api_key: str):
    st.subheader("🔍 종목별 디테일 업종/테마 분석")
    st.caption("AI가 각 기업의 세부 밸류체인을 분석하여 속해있는 모든 업종과 테마를 찾아냅니다.")
    
    display_df = df.copy()
    
    if "업종/테마" not in display_df.columns:
        progress_text = "AI가 종목별 세부 업종/테마를 스캐닝 중입니다..."
        progress_bar = st.progress(0, text=progress_text)
        
        theme_lists = []
        total_rows = len(display_df)
        
        for i, row in display_df.iterrows():
            stock_name = row['종목명']
            themes = get_granular_themes(stock_name, api_key)
            theme_lists.append(themes)
            
            time.sleep(0.5) 
            
            percent_complete = int(((i + 1) / total_rows) * 100)
            progress_bar.progress(percent_complete, text=f"{progress_text} ({stock_name} 완료)")
            
        display_df['업종/테마'] = theme_lists
        progress_bar.empty()
        
    # --- 🌟 '섹터'와 '현재가' 사이로 정확하게 타겟팅하여 순서 고정 ---
    cols = list(display_df.columns)
    if "업종/테마" in cols:
        cols.remove("업종/테마")
        
        if "섹터" in cols and "현재가" in cols:
            # '섹터' 바로 뒤 (즉, '현재가' 앞)에 삽입
            idx = cols.index("섹터") + 1
            cols.insert(idx, "업종/테마")
        elif "섹터" in cols:
            idx = cols.index("섹터") + 1
            cols.insert(idx, "업종/테마")
        elif "현재가" in cols:
            idx = cols.index("현재가")
            cols.insert(idx, "업종/테마")
        else:
            cols.insert(2, "업종/테마")
            
        display_df = display_df[cols]
    # ----------------------------------------------------------------
        
    st.dataframe(
        display_df,
        column_order=cols, 
        column_config={
            "종목코드": st.column_config.TextColumn("종목코드", width="small"),
            "종목명": st.column_config.TextColumn("종목명", width="medium"),
            "섹터": st.column_config.TextColumn("섹터", width="medium"),
            "업종/테마": st.column_config.ListColumn(
                "업종 / 테마",
                help="기업이 속한 모든 밸류체인 및 시장 테마 목록입니다.",
                width="large"
            ),
            "현재가": st.column_config.NumberColumn("현재가", format="%d")
        },
        hide_index=True,
        use_container_width=True
    )
def render_single_stock_themes(stock_name: str, api_key: str):
    """
    개별 기업 정밀 진단 화면용 다중 테마 렌더링 함수.
    HTML/CSS를 활용하여 테마를 세련된 해시태그 뱃지 형태로 출력합니다.
    """
    if not api_key:
        st.warning("API 키가 없어 테마 분석을 건너뜁니다.")
        return
        
    with st.spinner(f"'{stock_name}'의 딥-다이브 밸류체인 테마를 스캐닝 중입니다..."):
        # 이전에 추가한 AI 테마 추출 함수 재활용
        themes = get_granular_themes(stock_name, api_key)
        
    if themes and themes[0] not in ["API_KEY_MISSING", "분류 오류", "데이터 확인 필요"]:
        st.markdown("##### 🧩 AI 포착 핵심 밸류체인")
        
        # HTML과 CSS를 사용해 스트림릿 화면에 예쁜 태그(칩) 디자인 적용
        tags_html = "".join([
            f'<span style="display: inline-block; background-color: #1e3a8a; color: #ffffff; '
            f'padding: 5px 12px; border-radius: 15px; margin-right: 8px; margin-bottom: 8px; '
            f'font-size: 13px; font-weight: 600; box-shadow: 0px 2px 4px rgba(0,0,0,0.1);">'
            f'# {theme}</span>' 
            for theme in themes
        ])
        st.markdown(tags_html, unsafe_allow_html=True)
        st.write("") # 아래 콘텐츠와의 간격을 위한 빈 줄
        
# ==========================================
# 3. UI 렌더링 가이드 및 카드 함수
# ==========================================
def show_beginner_guide():
    with st.expander("🐥 [주린이 필독] 주식 용어 & 매매 타점 완벽 가이드", expanded=False):
        st.markdown("""
### 1. 📊 차트 상태 — 이동평균선(이평선) 완전 정복

**이동평균선(이평선)이란?** 매일 출렁이는 주가를 보기 쉽게, *최근 며칠간의 평균 가격*을 이은 선입니다.
- **5일선** = 최근 5일 평균 → 단기 흐름 *(요즘 분위기)*
- **20일선** = 최근 20일 평균 → 중기 추세 *(이번 달 컨디션)* ← **이 앱에서 가장 중요!**
- **60일선** = 최근 60일 평균 → 큰 추세 *(올해 체질)*

| 상태 | 기준 | 초보자 해석 |
|---|---|---|
| 🔥 **완벽 정배열** | `5일선 > 20일선 > 60일선` | 꾸준히 우상향. 올라타기 좋은 추세 |
| ❄️ **역배열** | `5일선 < 20일선 < 60일선` | 떨어지는 칼날. 함부로 잡지 말 것 |
| ✨ **5-20 골든크로스** | 5일선이 20일선을 *오늘* 상향 돌파 | 상승 전환의 첫 깃발 |
| 🌀 **혼조세/횡보** | 이평선들이 서로 얽힘 | 방향 미정. 굳이 진입 X |

---

### 2. ✅ 매매 타점 — "지금 사도 되는 자리인가?"
이 앱은 **현재가와 20일선의 거리(%)** 로 매수 자리를 판정합니다.

| 화면 표시 | 기준 | 행동 |
|---|---|---|
| ✅ **타점 근접 (분할매수)** | 20일선 **±3% 이내** | 한 번에 X, **나눠서** 매수 |
| ⚠️ **이격 과다 (눌림 대기)** | 20일선 **+3% 초과** | 추격 X, 내려올 때까지 대기 |
| 🛑 **20일선 이탈 (관망)** | 20일선 **-3% 아래** | 지지 깨짐, 신규 매수 멈춤 |

> 💧 **눌림목:** 오르던 주식이 잠깐 쉬며 20일선까지 내려온 자리.
> **상승 추세 + 눌림목**이 가장 좋은 매수 타이밍입니다.
> 🛑 **손절가 = 20일선 -3%** 로 자동 계산됩니다. (매수와 동시에 손절선을 정하세요!)

---

### 3. 📈 화면에 같이 뜨는 보조지표
- **RSI (0~100):** 과열·과매도 온도계. **70↑ 과열 / 30↓ 과매도(낙폭과대)**
- **🔥 거래량 급증:** 최근 10일 최대 거래량이 *20일 평균의 2배 초과*. 돈과 관심이 몰렸다는 신호
- **🐋 수급:** 누가 사나? **기관·외인이 동시 순매수(쌍끌이)** 하면 강력 신호 (`+` = 그날 더 샀다는 뜻)
- **📅 주봉 추세 (v7.0):** 일봉보다 한 단계 큰 흐름. **일봉 타점 + 주봉 상승**이 겹치면 가짜 신호 확률↓

> 💡 핵심: **좋은 자리(타점) + 거래량/수급**이 겹칠 때가 진짜입니다. 가격만 보지 마세요.
        """)

def show_trading_guidelines():
    with st.expander("🎯 [필독] Jaemini PRO 실전 매매 4STEP 시나리오 (단기 스윙 전략)", expanded=False):
        st.markdown("""
        *💡 단기 스윙 전략 가이드*
        * 🅰️ **안전 스윙 (목표 3일~2주):** `✅20일선 눌림목` + `🔥거래량 급증` 
        * 🅱️ **추세 탑승 (목표 1일~5일):** `✨정배열 초입` + `🔥거래량 급증` 

        ---
        **🆕 v7.0 강화 체크리스트 (이 순서로 확인하세요)**
        0. 🚦 **시장 국면 먼저!** 홈 화면 신호등이 🔴면 신규 진입 자제 (장이 안 좋으면 좋은 종목도 떨어집니다)
        1. 📈 일봉 추세(정배열/골든크로스) + ✅타점 근접인가?
        2. 📅 **주봉도 상승추세인가?** → `🎯 일봉+주봉 합류` 배지가 뜨면 가짜 신호 확률↓ (신뢰도 최상)
        3. 🔥 거래량/수급(쌍끌이)이 받쳐주는가?
        4. 🩸 **공매도 비중**이 과하지 않은가? (🔴 과열이면 하락 압력 주의)
        5. 🛑 손절가(20일선 -3%)·목표가를 **사기 전에** 정했는가?
        """)

def draw_stock_card(tech_result, api_key_str="", is_expanded=False, key_suffix="default"):

    # 1. 기본 데이터 추출
    stock_name = tech_result.get('종목명', '알수없음')
    sector = tech_result.get('섹터', '분류없음')
    curr = tech_result.get('현재가', 0)
    status = tech_result.get('상태', '')

    ticker_code = tech_result.get('티커', '')
    is_us = not str(ticker_code).isdigit()

    # 보조 함수 정의 (미국 주식이면 $, 국내 주식이면 원 단위 적용)
    def fmt_price(p, is_delta=False):
        try:
            val = float(p)
            prefix = "+" if is_delta and val > 0 else ""
            if is_us:
                # 미국 주식: 달러 + 소수점 2자리
                return f"{prefix}${val:,.2f}"
            else:
                # 국내 주식: 원 + 정수
                return f"{prefix}{int(val):,}원"
        except:
            return str(p)
            
    # 2. 상세 진단(배열상태) 및 RSI 가공
    align_status = str(tech_result.get('배열상태', '')).split(' ｜ ')[0]
    if not align_status: align_status = status
    
    rsi_val = str(tech_result.get('RSI', '-'))
    
    # 3. AI 테마 추출
    core_theme = "일반"
    if api_key_str:
        try:
            themes = get_granular_themes(stock_name, api_key_str)
            if themes and themes[0] not in ["데이터 확인 필요", "분류 오류"]:
                core_theme = themes[0]
        except:
            pass

# 4. 타이틀 조립: 업체명 / 테마 / 업종 / 현재가 / (진단 / 상세진단 / 외인 / 기관 / RSI)
    # RSI 소수점 정리 (84.0 형태)
    try:
        rsi_display = f"{float(tech_result.get('RSI', 0)):.1f}"
    except (ValueError, TypeError):
        rsi_display = str(tech_result.get('RSI', '-'))

    # 외인/기관 수급 이모지+숫자만 깔끔하게 추출 (예: "💧-345,982", "🔥+329,151")
    def _fmt_flow(raw):
        s = str(raw)
        if s in ("조회불가", "", "None"):
            return "조회불가"
        # "+329,151 (🔥매집)" / "-345,982 (💧매도)" → 부호 숫자만 추출
        num_part = s.split(' (')[0].strip()
        if num_part.startswith('-'):
            return f"💧{num_part}"
        elif num_part.startswith('+') or (num_part.replace(',', '').isdigit()):
            return f"🔥{num_part}"
        else:
            return num_part

    forgn_disp = _fmt_flow(tech_result.get('외인수급', '조회불가'))
    inst_disp = _fmt_flow(tech_result.get('기관수급', '조회불가'))

    # [v7.0] 주봉 추세 (멀티 타임프레임)
    weekly_trend = tech_result.get('주봉추세', '')
    weekly_short = weekly_trend.split(' ')[0] if weekly_trend else ''

    # 진단(상태) / 상세진단(배열상태 앞부분) / 외인 / 기관 / RSI 를 괄호로 묶어 표시
    detail_str = f"(진단: {status} ｜ 상세 진단: {align_status} ｜ 주봉: {weekly_short} ｜ 외인: {forgn_disp} ｜ 기관: {inst_disp} ｜ RSI: {rsi_display})"
    card_title = f"{stock_name} / {core_theme} / {sector} / {fmt_price(curr)} / {detail_str}"

    # 5. 펼침막 생성 (하단 지표 삭제)
    with st.expander(card_title, expanded=is_expanded):
        
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

        # [v7.0] ① 멀티 타임프레임 합류 신호
        wt = tech_result.get('주봉추세', '')
        daily_bull = ("정배열" in str(tech_result.get('배열상태', ''))) or ("골든크로스" in str(tech_result.get('배열상태', '')))
        good_entry = tech_result.get('상태', '') == "✅ 타점 근접 (분할 매수)"
        if "상승추세" in wt:
            if daily_bull and good_entry:
                col_btn1.success(f"🎯 **일봉 타점 + {wt} 합류!** → 신뢰도 높은 자리 (가짜 신호 확률 ↓)")
            else:
                col_btn1.info(f"📅 큰 추세 양호: {wt} (일봉 신호 대기 중)")
        elif "하락추세" in wt:
            col_btn1.warning(f"📅 주의: {wt} — 큰 흐름이 하락입니다. 단기 반등도 보수적으로 접근하세요.")
        elif wt:
            col_btn1.caption(f"📅 주봉 추세: {wt}")

        
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
                id_data = get_intraday_estimate(tech_result['티커'])
                if id_data:
                    f_val_str = f"🔥+{id_data['forgn']:,}" if id_data['forgn'] > 0 else f"💧{id_data['forgn']:,}"
                    i_val_str = f"🔥+{id_data['inst']:,}" if id_data['inst'] > 0 else f"💧{id_data['inst']:,}"
                    st.markdown(f"⚡ **최근 거래일 투자자별 순매수 (주)**<br>외인 `{f_val_str}` ｜ 기관 `{i_val_str}` `({id_data['time']} 기준)`", unsafe_allow_html=True)
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
                    intraday_missing = False   # 오늘 장중 잠정치 조회 실패 여부 (진단 표시용)
                    foreign_proxy = None        # 외국계 거래원 순매수 추정(장중 실시간 프록시)
                    
                    if not daily_df.empty:
                        now_kst = datetime.utcnow() + timedelta(hours=9)
                        today_date = now_kst.strftime('%Y.%m.%d')
                        
                        if today_date not in str(daily_df.iloc[0]['날짜']):
                            # 첫 행 = '오늘 실시간 시세' 행. 종가·전일비·등락률만 실시간가로 채우고,
                            # 수급은 장중 분단위 확정 소스가 없으므로 '장 마감 후 확정'으로 표기한다.
                            # (외국계 거래원 추정치가 잡히면 외국인 칸에 프록시로 보강)
                            try:
                                prev_close = int(str(daily_df.iloc[0]['종가']).replace(',', ''))
                                curr_price = int(tech_result['현재가'])
                                diff = curr_price - prev_close
                                diff_str = f"상승 {diff:,}" if diff > 0 else f"하락 {abs(diff):,}" if diff < 0 else "보합 0"
                                pct_str = f"{'+' if diff > 0 else ''}{(diff / prev_close) * 100:.2f}%"
                            except Exception:
                                diff_str = "-"
                                pct_str = "-"

                            fb = get_foreign_broker_estimate(tech_result['티커'])
                            if fb:
                                n = fb['net']
                                proxy_str = (f"🔴 +{n:,}" if n > 0 else f"🔵 {n:,}" if n < 0 else "0")
                                est_f = f"{proxy_str} (창구추정)"
                                est_i = "장 마감 후 확정"
                                est_r = "장 마감 후 확정"
                                time_label = "(장중·외국계 창구추정)"
                                foreign_proxy = fb
                            else:
                                est_f = "장 마감 후 확정"
                                est_i = "장 마감 후 확정"
                                est_r = "장 마감 후 확정"
                                time_label = "(실시간가·수급 미확정)"
                                intraday_missing = True

                            new_row = pd.DataFrame([{
                                "날짜": f"✨ {today_date} {time_label}",
                                "종가": f"{int(tech_result['현재가']):,}",
                                "전일비": diff_str,
                                "등락률": pct_str,
                                "외국인": est_f,
                                "기관": est_i,
                                "개인": est_r
                            }])
                            daily_df = pd.concat([new_row, daily_df], ignore_index=True)
                        st.dataframe(daily_df, use_container_width=True, hide_index=True)
                        if foreign_proxy:
                            st.caption(
                                f"🌍 **오늘 외국계 거래원 순매수(추정, 장중 실시간·KRX):** "
                                f"매수 {foreign_proxy['buy']:,} − 매도 {foreign_proxy['sell']:,} = "
                                f"**{'+' if foreign_proxy['net'] >= 0 else ''}{foreign_proxy['net']:,}주**.  "
                                "이는 외국계 증권사 '창구' 거래량 추정치로, 장중 외국인 매매를 가늠하는 실시간 프록시입니다. "
                                "투자자별 '확정' 외국인·기관 순매수는 장 마감 후 거래소가 공개합니다."
                            )
                        if intraday_missing:
                            st.caption("ℹ️ 오늘 **외국인·기관 순매수는 장 마감 후** 거래소가 확정 공개합니다. "
                                       "네이버가 제공하던 장중 '잠정' 실시간 피드는 현재 이 페이지(frgn)에서 내려가 있어, "
                                       "장중 실시간 수급은 표시되지 않습니다. (종가·등락률은 실시간 반영)")
                            with st.expander("🔍 장중 수급 미표시 원인 진단  (실시간 보강판 rt-v2)", expanded=False):
                                dbg = get_intraday_estimate_debug(tech_result['티커'])
                                if dbg["err"]:
                                    st.write(f"- 요청 오류: `{dbg['err']}`  → 서버에서 네이버 접근 자체가 막혔을 수 있습니다.")
                                else:
                                    st.write(f"- 네이버 응답 코드: `{dbg['http']}`  (200이면 접근은 정상)")
                                    st.write(f"- 페이지 내 표 개수: `{dbg['tables']}`  /  잠정치 표 선택 경로: `{dbg['cand_via']}`")
                                    st.write(f"- 표 summary 목록: `{dbg['summaries']}`")
                                    st.write("- 선택된 표의 상위 행(원본 그대로):")
                                    if dbg["rows"]:
                                        for r in dbg["rows"]:
                                            st.write(f"　· `{r}`")
                                    else:
                                        st.write("　· (행 없음)")
                                    st.write(f"- '외국계' 포함 행(거래원 추정합 후보): `{dbg.get('foreign_rows', [])}`")
                                st.caption("summary 목록에 '잠정' 표가 없고 '…날짜별로 정보를 제공' 표만 있으면, 이 페이지에는 장중 잠정 피드가 없는 것입니다(확정·일별만 제공). "
                                           "장중 실시간이 꼭 필요하면 네이버 신형 증권의 내부 API를 잡아야 하며, 방법은 채팅 안내를 참고하세요.")
                    else: 
                        st.caption("수급 데이터를 제공하지 않는 종목입니다.")
            else: 
                st.error("데이터를 불러오지 못했습니다.")
                 
def display_sorted_results(results_list, tab_key, api_key=""):
    if not results_list:
        st.info("조건에 부합하는 종목이 없습니다.")
        return
        
    st.success(f"🎯 총 {len(results_list)}개 종목 포착 완료!")
    
    # --- 🌟 [추가됨] 시장 필터 및 정렬 옵션을 2열로 깔끔하게 배치 ---
    col_f1, col_f2 = st.columns(2)
    with col_f1:
        market_filter = st.radio("🌍 시장 필터", ["전체 보기", "🇰🇷 국내 주식만", "🇺🇸 미국 주식만"], horizontal=True, key=f"market_filter_{tab_key}")
    with col_f2:
        sort_opt = st.radio("⬇️ 결과 정렬 방식", ["기본 (검색순)", "RSI 낮은순 (바닥줍기)", "기관 연속 순매수 긴 순서"], horizontal=True, key=f"sort_radio_{tab_key}")
    
    # 1. 시장 필터링 적용 (티커가 숫자인지 알파벳인지로 구분)
    display_list = []
    for res in results_list:
        is_us = not str(res.get('티커', '')).isdigit()
        
        if market_filter == "🇰🇷 국내 주식만" and is_us:
            continue
        if market_filter == "🇺🇸 미국 주식만" and not is_us:
            continue
            
        display_list.append(res)
        
    if not display_list:
        st.warning(f"선택하신 '{market_filter}' 조건에 해당하는 종목이 없습니다.")
        return

    # 2. 정렬 방식 적용
    if "RSI 낮은순" in sort_opt: 
        sorted_res = sorted(display_list, key=lambda x: x['RSI'])
    elif "기관 연속" in sort_opt: 
        sorted_res = sorted(display_list, key=lambda x: x.get('기관연속순매수', 0), reverse=True)
    else: 
        sorted_res = display_list

    # --- 🌟 다중 테마 뷰어 버튼 (Streamlit Session State 토글 방어막 적용) ---
    btn_state_key = f"multi_theme_show_{tab_key}"
    
    # 👇 이 부분의 버튼 텍스트를 '업종/테마'로 수정했습니다.
    if st.button("🧩 포착된 종목 '업종/테마' 한눈에 보기", key=f"multi_theme_btn_{tab_key}", type="primary"):
        # 버튼을 누르면 상태를 On/Off (토글) 처리하여 표가 증발하는 것을 방지합니다.
        st.session_state[btn_state_key] = not st.session_state.get(btn_state_key, False)

    if st.session_state.get(btn_state_key, False):
        df = pd.DataFrame(sorted_res)
        if '티커' in df.columns:
            df = df.rename(columns={'티커': '종목코드'})
        render_multi_theme_dataframe(df, api_key)
        st.markdown("---")
    # -----------------------------------

    # 3. 최종 결과 카드 출력
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
    st.title("📈 Jaemini PRO v7.0")
    st.markdown("풀옵션 단기 스윙 & 퀀트 추적 시스템")
    st.caption("🆕 v7.0: 주봉 멀티타임프레임 · 시장 국면 신호등 · 공매도/빚투 리스크")
    
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
        " ┣ 📅 핵심 증시 일정 & IPO 달력",
        " ┗ 🔮 폴리마켓 예측시장 (금리·경제·정치)",
        "  ", 
        "📂 [ 퀀트 스캐너 & 종목 발굴 ]",
        " ┣ 🚀 단기 스윙 퀀트 스캐너",
        " ┣ 👨‍🦳 기관/외인 수급 스캐너",
        " ┣ 🏛️ 국민연금 5% 대량보유 픽",
        " ┣ 💎 장기 우량주 & 가치주 발굴",
        " ┣ ⚡ 메가트렌드 & 테마 대장주",
        " ┗ 🇰🇷 국민성장펀드 12대 산업 수혜주",
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

    # [추가] 메뉴(페이지) 전환 감지 — 메뉴를 '새로 눌렀을 때'만 1회 동작시키기 위함.
    #  (자동 새로고침/챗봇 입력 등 일반적인 rerun 때는 False 가 되어 화면이 튀지 않음)
    _nav_changed = st.session_state.get("_prev_menu_nav") != selected_menu
    st.session_state["_prev_menu_nav"] = selected_menu

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
    # [추가] 메뉴를 '새로 눌러서' 이 화면으로 들어왔을 때만 화면을 맨 위로 올림.
    #  → 페이지 하단의 '실시간 퀀트 챗봇(채팅 입력창)'으로 화면이 튀어 내려가는 현상 방지.
    #  자동 새로고침/챗봇 입력 같은 일반 rerun 때는 동작하지 않으므로 챗봇은 정상 사용 가능.
    if _nav_changed:
        components.html(
            """
            <script>
            (function () {
              function toTop() {
                try {
                  var d = window.parent.document;
                  var sels = ['section.main', '[data-testid="stMain"]',
                              '[data-testid="stAppViewContainer"]', '.main',
                              '.stMainBlockContainer', '.appview-container'];
                  sels.forEach(function (s) {
                    var el = d.querySelector(s);
                    if (el) { try { el.scrollTo(0, 0); } catch (e) {} el.scrollTop = 0; }
                  });
                  try { window.parent.scrollTo(0, 0); } catch (e) {}
                  d.documentElement.scrollTop = 0;
                  d.body.scrollTop = 0;
                } catch (e) {}
              }
              toTop();
              [60, 200, 450, 800].forEach(function (t) { setTimeout(toTop, t); });
            })();
            </script>
            """,
            height=0,
        )

    macro_data = get_macro_indicators()
    fg_data = get_fear_and_greed()
    
    st.markdown("## 🎛️ 홈: 종합 대시보드")

    # [추가] 네이버 모바일 스타일 메인 지수 패널 (코스피/코스닥 + 오늘의 시장 + 투자자별 순매매 + 미니차트 + 주요지표)
    with st.spinner("코스피·코스닥 지수 / 투자자별 수급 수집 중..."):
        render_main_index_panel()
    st.divider()

    # [추가] 시가총액 TOP & 업종별 등락률
    mc_col, ind_col = st.columns(2)
    with mc_col:
        st.markdown("#### 🏆 시가총액 TOP 10")
        mc_market = st.radio("시장", ["KOSPI", "KOSDAQ"], horizontal=True,
                             label_visibility="collapsed", key="mcap_market_radio")
        with st.spinner("시가총액 상위 종목 수집 중..."):
            render_marketcap_top(mc_market, 10)
    with ind_col:
        st.markdown("#### 🔥 업종별 등락률 (강세 순)")
        # 좌측 시총 컬럼의 KOSPI/KOSDAQ 라디오 높이만큼 여백을 줘서 두 표의 시작점을 맞춘다.
        st.markdown("<div style='height:46px;'></div>", unsafe_allow_html=True)
        with st.spinner("업종별 등락률 수집 중..."):
            render_industry_changes(12)
    st.divider()

    # [v7.0] 시장 국면 신호등 — 가장 먼저 '오늘 장이 좋은지'부터 확인
    render_market_regime_banner()

    # [추가] 간밤 미국 시황 배너 — 공포지수/탐욕지수 게이지 '위'에 배치
    st.markdown("#### 🌙 간밤 미국 시황 (Risk-On / Off 체크)")
    with st.spinner("간밤 지수·VIX·환율 수집 중..."):
        render_overnight_banner()
    st.caption("💡 VIX(공포지수)가 급등하거나 지수가 크게 빠진 날은, 미국 급등주가 있어도 국장이 위험회피로 갈 수 있으니 보수적으로 접근하세요.")
    st.divider()

    # [추가] 오늘의 국장 장세 (상승/하락 종목 수) — 네이버 집계 수치만 가볍게 사용
    with st.spinner("국장 등락 종목 수 집계 중..."):
        render_kr_market_breadth()
    st.divider()

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
                        with st.expander(f"📊 '{us_ticker}' 퀵 타점 보기", expanded=False):
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

    # [수정] st.chat_input 은 페이지 최하단에 '고정'되는 위젯이라,
    #  홈 화면 진입 시 브라우저가 입력창으로 스크롤을 튕겨 내리는 현상이 있었음.
    #  → 일반 text_input + 전송 버튼으로 교체하여 화면이 튀지 않도록 고정.
    in_col, btn_col = st.columns([5, 1])
    prompt = in_col.text_input(
        "퀀트 비서에게 질문", key="main_chat_text",
        placeholder="예: 펄어비스 붉은사막 최신 출시 일정 검색해서 알려줘",
        label_visibility="collapsed",
    )
    send = btn_col.button("📨 전송", key="main_chat_send", use_container_width=True)

    if send and prompt and prompt.strip():
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
                        model = genai.GenerativeModel('gemini-3.1-flash-lite', tools='google_search_retrieval')
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
    st.markdown("## 💼 내 계좌 & 포트폴리오 진단")
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
    st.subheader("⭐ 내 관심종목 모니터링")
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
    st.markdown("## 🌍 글로벌 매크로 & AI 분석 (v6.0)")
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
    st.subheader("🗺️ 시장 주도주 자금 히트맵")
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
    st.markdown("## 🕸️ 실시간 섹터 순환매 추적")
    st.write("국내 대표 섹터 ETF의 기간별 수익률을 실측해, **강세 섹터(자금 유입 추정)**와 **약세 섹터(자금 이탈 추정)**를 한눈에 보여줍니다.")

    period_sk = st.radio("분석 기간", ["1개월", "3개월", "6개월"], horizontal=True)
    period_col = "1M수익률" if period_sk == "1개월" else "3M수익률" if period_sk == "3개월" else "6M수익률"

    with st.spinner(f"최근 {period_sk} 시장 섹터 수익률 실시간 연산 중..."):
        trend_df = analyze_theme_trends()

    if not trend_df.empty:
        df_sorted = trend_df.sort_values(period_col, ascending=False).reset_index(drop=True)
        winners = df_sorted.head(3)
        losers = df_sorted.tail(3).iloc[::-1]  # 최약세부터

        # ── 요약 카드: 강세 3 / 약세 3 ─────────────────────────
        c_win, c_lose = st.columns(2)
        def _chip(name, val):
            color = "#ef4444" if val > 0 else ("#3b82f6" if val < 0 else "#64748b")
            arrow = "▲" if val > 0 else ("▼" if val < 0 else "")
            return (f'<div style="display:flex;justify-content:space-between;padding:8px 12px;margin:5px 0;'
                    f'background:#fff;border:1px solid #eef2f6;border-radius:10px;">'
                    f'<span style="font-weight:700;color:#1e293b;">{name}</span>'
                    f'<span style="font-weight:800;color:{color};">{arrow}{abs(val):.2f}%</span></div>')
        with c_win:
            st.markdown("#### 🔥 강세 섹터 (자금 유입 추정)")
            st.markdown("".join(_chip(r['테마'], r[period_col]) for _, r in winners.iterrows()),
                        unsafe_allow_html=True)
        with c_lose:
            st.markdown("#### 🧊 약세 섹터 (자금 이탈 추정)")
            st.markdown("".join(_chip(r['테마'], r[period_col]) for _, r in losers.iterrows()),
                        unsafe_allow_html=True)

        st.markdown("---")

        # ── 전체 섹터 수익률 가로 바 차트 (강세 빨강 / 약세 파랑) ──
        chart_df = df_sorted.sort_values(period_col, ascending=True)  # 아래→위 오름차순
        bar_colors = ["#ef4444" if v > 0 else "#3b82f6" for v in chart_df[period_col]]
        fig_bar = go.Figure(go.Bar(
            x=chart_df[period_col],
            y=chart_df['테마'],
            orientation='h',
            marker=dict(color=bar_colors),
            text=[f"{v:+.2f}%" for v in chart_df[period_col]],
            textposition='outside',
            cliponaxis=False,
        ))
        fig_bar.update_layout(
            title_text=f"최근 {period_sk} 섹터별 수익률 ({datetime.now().strftime('%Y.%m.%d')} 기준)",
            height=480,
            margin=dict(l=10, r=60, t=50, b=20),
            xaxis_title="수익률 (%)",
            plot_bgcolor="rgba(0,0,0,0)",
        )
        fig_bar.add_vline(x=0, line_width=1, line_color="#94a3b8")
        st.plotly_chart(fig_bar, use_container_width=True)

        st.info(
            f"💡 최근 {period_sk} 동안 **{', '.join(winners['테마'].tolist())}**가 가장 강했고, "
            f"**{', '.join(losers['테마'].tolist())}**가 가장 부진했습니다. "
            "통상 약세 섹터에서 차익이 실현되며 강세 섹터로 수급이 옮겨가는 '순환매'로 해석하지만, "
            "이는 수익률 차이에 근거한 **추정**이며 실제 자금 이동을 직접 측정한 값은 아닙니다."
        )
    else:
        st.error("테마별 시장 데이터를 불러오지 못했습니다.")


elif selected_menu == "📅 핵심 증시 일정 & IPO 달력":
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
            ".evt-us-red { background: #ffebee; color: #c62828; font-size: 11px; padding: 3px; margin-bottom: 2px; border-left: 3px solid #c62828; border-radius: 2px; font-weight: bold; line-height: 1.2; letter-spacing: -0.5px; }",
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
            "<span style='background:#ede7f6;color:#4527a0;padding:2px 6px;border-radius:3px;'>🏛️ FOMC</span> "
            "<span style='background:#fff8e1;color:#ff6f00;padding:2px 6px;border-radius:3px;'>📊 CPI</span> "
            "<span style='background:#e0f7fa;color:#006064;padding:2px 6px;border-radius:3px;'>👷 고용지표</span> "
            "<span style='background:#fce4ec;color:#880e4f;padding:2px 6px;border-radius:3px;'>🏦 한은 금통위</span> "
            "<span style='background:#ffebee;color:#c62828;padding:2px 6px;border-radius:3px;'>🔴 옵션만기</span> "
            "<span style='background:#e3f2fd;color:#1565c0;padding:2px 6px;border-radius:3px;'>🔹 위클리만기</span>"
            "</div>",
            unsafe_allow_html=True,
        )
        st.caption(
            "ℹ️ 표시된 경제지표는 모두 **공식 확정 일정(2026)**입니다 — "
            "FOMC(미 연준)·한은 금통위, 미 CPI·고용지표(BLS·OMB 공식 발표 기준). "
            "옵션만기(미 셋째 금요일·한국 둘째 목요일)는 규칙 기반입니다. "
            "단, 정부 셧다운 등으로 발표일이 사후 연기될 수 있으니 중대한 매매 전엔 원출처를 확인하세요."
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

elif selected_menu == "🚀 단기 스윙 퀀트 스캐너":
    st.markdown("## 🚀 단기 스윙 퀀트 스캐너")
    scan_tab, backtest_tab = st.tabs(["🚀 실시간 조건 검색 스캐너", "🧪 1년 전략 백테스팅"])
    
    with scan_tab:
        show_beginner_guide()
        show_trading_guidelines()
        
        scan_market = st.radio("시장 선택 (스캐너)", ["🇰🇷 국내 주식", "🇺🇸 미국 주식"], horizontal=True)
        col_c1, col_c2, col_c3, col_c4 = st.columns(4)
        with col_c1: cond_golden = st.checkbox("✨ 골든크로스 / 정배열 초입"); cond_pullback = st.checkbox("✅ 20일선 눌림목 (타점 근접)", value=True)
        with col_c2: cond_rsi_bottom = st.checkbox("🔵 RSI 30 이하 (낙폭과대)"); cond_vol_spike = st.checkbox("🔥 최근 거래량 급증 (세력 의심)")
        with col_c3: cond_twin_buy = st.checkbox("🐋 외인/기관 쌍끌이 순매수")
        with col_c4: cond_pension = st.checkbox("👴 기관 3일 연속 순매수"); cond_weekly = st.checkbox("📅 주봉도 상승 추세만 (멀티TF)")
        
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
                            if cond_weekly and "상승추세" not in str(res.get('주봉추세', '')): return None
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
    st.markdown("## 👨‍🦳 기관/외인 수급 스캐너")
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
    st.markdown("## 🏛️ 국민연금 5% 대량보유 픽")
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
    st.markdown("## 💎 장기 우량주 & 가치주 발굴")
    st.caption("위험 성향(안전·중립·공격)을 고르고 세부 전략을 선택하면 → AI 후보 발굴 → 멀티팩터 검증(PER·PBR·배당·ROE·부채·성장·모멘텀) → 차트 타점까지 한 번에.")

    tier = st.radio("🎚️ 위험 성향", list(VALUE_STRATEGIES.keys()), horizontal=True)
    tier_list = VALUE_STRATEGIES[tier]
    col_v1, col_v2 = st.columns([2, 1])
    with col_v1:
        pick = st.selectbox("🧠 세부 전략", [s["name"] for s in tier_list])
    with col_v2:
        cap_size = st.selectbox("🏢 기업 규모", ["대/중/소형 상관없음", "코스피 대형우량주만", "코스닥 중소형 숨은진주"], index=0)
    strat = next(s for s in tier_list if s["name"] == pick)

    cond = []
    if strat["per"] is not None: cond.append(f"PER ≤ {strat['per']}")
    if strat["pbr"] is not None: cond.append(f"PBR ≤ {strat['pbr']}")
    if strat["div"] is not None: cond.append(f"배당 ≥ {strat['div']}%")
    if strat["roe"] is not None: cond.append(f"ROE ≥ {strat['roe']}%")
    if strat["debt"] is not None: cond.append(f"부채비율 ≤ {strat['debt']}")
    if strat["growth"] is not None: cond.append(f"이익성장 ≥ {strat['growth']}%")
    if strat["mom"] == "strong": cond.append("강세 모멘텀(3·6M 상승)")
    if strat["mom"] == "weak": cond.append("낙폭과대(고점 -25%↓)")
    st.info(f"**{strat['name']}** — {strat['desc']}\n\n**적용 필터:** " + " ｜ ".join(cond) + "\n\n※ PER·PBR·모멘텀은 하드 필터, ROE·배당·부채·성장은 데이터가 있을 때만 적용(소프트)됩니다.")

    if st.button("💎 멀티팩터 병렬 스캔 시작", type="primary", use_container_width=True):
        if not api_key_input:
            st.warning("API 키를 입력해주세요.")
        else:
            with st.spinner("AI가 전략 부합 후보를 발굴 중..."):
                candidates = get_longterm_value_stocks_with_ai(strat["name"] + " — " + strat["hint"], cap_size, api_key_input)
            if not candidates:
                st.error("❌ 관련 기업을 찾지 못했습니다.")
            else:
                progress = st.progress(0.0)
                total, completed, passed = len(candidates), 0, []

                def _work(t):
                    name, c = t
                    m = get_value_metrics(c)
                    if not value_passes(m, strat):
                        return None
                    res = analyze_technical_pattern(name, c)
                    return {"name": name, "code": c, "m": m, "res": res}

                with concurrent.futures.ThreadPoolExecutor(max_workers=5) as ex:
                    for fut in concurrent.futures.as_completed({ex.submit(_work, c): c for c in candidates}):
                        r = fut.result()
                        completed += 1
                        progress.progress(min(1.0, completed / total))
                        if r:
                            passed.append(r)

                if passed:
                    def _fmt(v, suf="", plus=False):
                        if v is None: return "-"
                        return (f"{v:+.1f}{suf}" if plus else f"{v:.1f}{suf}")
                    summary = pd.DataFrame([{
                        "종목명": p["name"], "코드": p["code"],
                        "PER": _fmt(p["m"]["per"]), "PBR": (f"{p['m']['pbr']:.2f}" if p["m"]["pbr"] else "-"),
                        "배당%": _fmt(p["m"]["div"]), "ROE%": (f"{p['m']['roe']:.0f}" if p["m"]["roe"] is not None else "-"),
                        "3M%": _fmt(p["m"]["mom3"], plus=True), "6M%": _fmt(p["m"]["mom6"], plus=True),
                        "고점대비%": _fmt(p["m"]["off_high"], plus=True),
                    } for p in passed])
                    st.session_state.value_scan_summary = summary
                    st.session_state.value_scan_results = [p["res"] for p in passed if p["res"]]
                else:
                    st.session_state.value_scan_summary = None
                    st.session_state.value_scan_results = []
                st.session_state.value_scan_meta = (strat["name"], total, len(passed))

    meta = st.session_state.get("value_scan_meta")
    if meta:
        if meta[2] > 0:
            st.success(f"✅ {meta[1]}개 후보 중 **{meta[2]}개** 종목이 '{meta[0]}' 조건을 통과했습니다.")
        else:
            st.warning(f"'{meta[0]}' 조건을 통과한 종목이 없습니다. 위험 성향을 바꾸거나 다른 전략을 시도해보세요.")
    if st.session_state.get("value_scan_summary") is not None:
        st.markdown("#### 📋 조건 통과 종목 요약 (멀티팩터)")
        st.dataframe(st.session_state.value_scan_summary, use_container_width=True, hide_index=True)
    if st.session_state.value_scan_results:
        st.markdown("#### 📈 통과 종목 차트·타점 정밀 분석")
        display_sorted_results(st.session_state.value_scan_results, tab_key="t3", api_key=api_key_input)

elif selected_menu == "⚡ 메가트렌드 & 테마 대장주":
        st.markdown("## ⚡ 메가트렌드 & 테마 대장주")
        st.write("AI가 최신 트렌드를 분석하여, 숨겨진 글로벌 텐배거(10배 상승) 후보와 한·미 양국의 핵심 수혜주를 동시에 발굴합니다.")
        # ... (이하 해당 블록 내용 전체)
        
        if not api_key_input:
            st.warning("⚠️ 사이드바에 Gemini API 키를 입력하시면 글로벌 AI 스캐너가 활성화됩니다.")
        else:
            st.markdown("### 🔥 현재 글로벌 시장 주도 테마 (AI 자동 추출)")
            with st.spinner("한국(KRX) 및 미국(US) 주요 증시의 거래 데이터를 분석하여 핵심 테마를 추출 중입니다..."):
                hot_themes_tab5 = get_trending_themes_with_ai(api_key_input)
                
            cols_d = st.columns(4) 
            for idx, theme in enumerate(hot_themes_tab5[:4]):
                if cols_d[idx].button(f"🔥 {theme}", key=f"hot_theme_btn_{idx}", use_container_width=True):
                    st.session_state.deep_tech_query = theme
                    st.session_state.deep_tech_results = None
                    st.session_state.deep_tech_brief = None

            st.markdown("### 🔎 직접 글로벌 테마 검색")
            with st.form(key="theme_search_form", clear_on_submit=False):
                col_in1, col_in2 = st.columns([8, 2], vertical_alignment="bottom")
                with col_in1:
                    custom_query = st.text_input(
                        "분석할 메가트렌드나 테마를 입력하세요", 
                        label_visibility="collapsed", 
                        key="deep_tech_input", 
                        placeholder="예: AI 데이터센터 전력, 비만치료제, 우주항공"
                    )
                with col_in2:
                    submit_btn = st.form_submit_button("🚀 글로벌 대장주 발굴", use_container_width=True)
                    
                if submit_btn:
                    if custom_query.strip():
                        st.session_state.deep_tech_query = custom_query.strip()
                        st.session_state.deep_tech_results = None
                        st.session_state.deep_tech_brief = None
                    else:
                        st.warning("테마 키워드를 입력해주세요!")

            if st.session_state.deep_tech_query and st.session_state.deep_tech_results is None:
                st.divider()
                st.markdown(f"### 🎯 '{st.session_state.deep_tech_query}' 글로벌 밸류체인 정밀 분석")
                
                with st.spinner("AI가 해당 테마의 월스트리트 모멘텀과 글로벌 핵심 촉매를 분석 중입니다..."):
                    theme_brief_prompt = f"당신은 글로벌 퀀트 애널리스트입니다.\n'{st.session_state.deep_tech_query}' 테마가 한국과 미국 시장을 주도하는 이유와 향후 글로벌 전망을 3줄로 명확하게 요약하세요."
                    st.session_state.deep_tech_brief = ask_gemini(theme_brief_prompt, api_key_input)
                    
                with st.spinner(f"✨ '{st.session_state.deep_tech_query}' 테마의 한·미 핵심 대장주 및 밸류체인 수혜주를 필터링 중입니다..."):
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
                                status_text.text(f"⚡ 한·미 증시 재무/차트 데이터 파싱 중... ({completed}/{total}) - {len(theme_res_list)}개 타점 확보")
                        
                        st.session_state.deep_tech_results = theme_res_list
                    else:
                        st.error(f"❌ '{st.session_state.deep_tech_query}' 테마와 관련된 종목을 찾지 못했습니다.")
                        st.session_state.deep_tech_query = None

            if st.session_state.deep_tech_results is not None:
                if st.session_state.get('deep_tech_brief'):
                    st.info(f"**💡 글로벌 AI 퀀트 인사이트:**\n{st.session_state.deep_tech_brief}")
                display_sorted_results(st.session_state.deep_tech_results, tab_key="t5", api_key=api_key_input)

elif selected_menu == "🇰🇷 국민성장펀드 12대 산업 수혜주":
    st.markdown("## 🇰🇷 국민성장펀드 12대 산업 수혜주")
    st.write("정부 주도 **150조원 규모 국민성장펀드**가 집중 투자하는 12개 첨단전략산업을 선택하면, "
             "AI가 해당 분야의 국내(KRX) 핵심 수혜 대장주를 발굴하고 차트·수급 타점을 즉시 분석합니다.")

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("총 펀드 규모", GROWTH_FUND_ALLOC["총 규모"] + "원")
    c2.metric("AI 배정", GROWTH_FUND_ALLOC["AI"] + "원")
    c3.metric("반도체 배정", GROWTH_FUND_ALLOC["반도체"] + "원")
    c4.metric("모빌리티 배정", GROWTH_FUND_ALLOC["모빌리티"] + "원")
    st.caption("※ 금융위원회 지정 주목적 투자대상 12개 산업 기준. 개별 자펀드는 결성액의 60% 이상을 해당 산업에 투자합니다.")
    st.divider()

    if not api_key_input:
        st.warning("⚠️ 사이드바에 Gemini API 키를 입력하시면 수혜주 스캐너가 활성화됩니다.")
    else:
        st.markdown("### 🎯 분석할 첨단전략산업을 선택하세요")
        for cat_name, sectors in GROWTH_FUND_SECTORS.items():
            st.markdown(f"**{cat_name}**")
            cols = st.columns(len(sectors))
            for idx, (label, query) in enumerate(sectors):
                if cols[idx].button(label, key=f"gf_btn_{label}", use_container_width=True):
                    st.session_state.gf_sector_query = query
                    st.session_state.gf_results = None

        if st.session_state.gf_sector_query and st.session_state.gf_results is None:
            st.divider()
            q = st.session_state.gf_sector_query
            st.markdown(f"### 📈 '{q}' 국민성장펀드 수혜주 정밀 분석")
            with st.spinner(f"✨ '{q}' 분야의 국내 핵심 수혜주 및 밸류체인을 필터링 중입니다..."):
                gf_stocks = get_growth_fund_stocks_with_ai(q, api_key_input)

            if gf_stocks:
                progress_bar = st.progress(0.0)
                status_text = st.empty()
                gf_res_list = []
                completed, total = 0, len(gf_stocks)

                def process_gf_stock(item):
                    name, code = item
                    time.sleep(0.1)
                    return analyze_technical_pattern(name, code)

                with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
                    futures = {executor.submit(process_gf_stock, t): t for t in gf_stocks}
                    for future in concurrent.futures.as_completed(futures):
                        res = future.result()
                        completed += 1
                        if res:
                            gf_res_list.append(res)
                        progress_bar.progress(min(1.0, completed / total))
                        status_text.text(f"⚡ KRX 재무/차트 데이터 파싱 중... ({completed}/{total}) - {len(gf_res_list)}개 타점 확보")

                st.session_state.gf_results = gf_res_list
            else:
                st.error(f"❌ '{q}' 분야 수혜주를 찾지 못했습니다. 다시 시도해주세요.")
                st.session_state.gf_sector_query = None

        if st.session_state.gf_results is not None:
            st.info(f"💡 **{st.session_state.gf_sector_query}** 분야의 국민성장펀드 정책 수혜 기대 종목입니다. "
                    "(아래에서 RSI·수급 기준 정렬 가능)")
            display_sorted_results(st.session_state.gf_results, tab_key="gf", api_key=api_key_input)

elif selected_menu == "🔥 간밤의 미국 급등주 & 수혜주":
    st.markdown("## 🔥 간밤의 미국 급등주 & 수혜주")
    st.caption("간밤 미국 증시에서 급등한 종목 → AI가 한국 수혜주(밸류체인)를 찾아주고 → 그 수혜주의 매매 타점까지 한 번에 확인하는 페이지입니다.")

    # [v7.0] ① 간밤 미국 시황 미니 배너 — 급등주 보기 전 위험선호부터 파악
    st.markdown("#### 🌙 간밤 미국 시황 (Risk-On / Off 체크)")
    with st.spinner("간밤 지수·VIX·환율 수집 중..."):
        render_overnight_banner()
    st.caption("💡 VIX(공포지수)가 급등하거나 지수가 크게 빠진 날은, 미국 급등주가 있어도 국장이 위험회피로 갈 수 있으니 보수적으로 접근하세요.")

    # [v7.0] ② 초보자 가이드 배치 (이 페이지도 타점 분석을 쓰므로)
    show_beginner_guide()
    show_trading_guidelines()
    st.divider()

    col_sec, col_gain = st.columns([1, 1.2], gap="large")
    with col_sec:
        st.subheader("📊 1. 미 증시 주도 섹터 (ETF)")
        st.caption("간밤 어느 섹터로 돈이 몰렸는지 (등락률 높은 순). 🔴빨강=상승 / 🔵파랑=하락")
        with st.spinner("섹터 ETF 등락률 산출 중..."):
            etf_df = get_us_sector_etfs()
            sty_etf = style_sector_etf_table(etf_df)
            if sty_etf is not None:
                st.dataframe(sty_etf, use_container_width=True, height=400)
            elif not etf_df.empty:
                st.dataframe(etf_df, use_container_width=True, hide_index=True)

        st.subheader("🚀 2. 글로벌 급등주 필터링")
        fetch_t = st.session_state.get('us_fetch_time', '-')
        rc1, rc2 = st.columns([3, 1])
        rc1.caption(f"기준 시각: {fetch_t} (KST) · 전일 대비 +5% 이상 급등주")
        if rc2.button("🔄 새로고침", use_container_width=True, key="refresh_gainers"):
            get_us_top_gainers.clear()
            df, ex_rate, ft = get_us_top_gainers()
            st.session_state.gainers_df = df
            st.session_state.ex_rate = ex_rate
            st.session_state.us_fetch_time = ft
            st.rerun()

        if not st.session_state.gainers_df.empty:
            sty_g = style_us_gainers_table(st.session_state.gainers_df)
            if sty_g is not None:
                st.dataframe(sty_g, use_container_width=True, height=420)
            else:
                st.dataframe(st.session_state.gainers_df, use_container_width=True, hide_index=True)
            opts = ["🔍 종목 선택"] + [f"{r['종목코드']} ({r['기업명']})" for _, r in st.session_state.gainers_df.iterrows()]
            sel_opt = st.selectbox("🎯 분석할 주도주 선택", opts)
            sel_tick = "N/A" if sel_opt == "🔍 종목 선택" else sel_opt.split(" ")[0]
        else:
            sel_tick = "N/A"
            sel_opt = "🔍 종목 선택"
            st.error("❌ 현재 급등주 데이터를 불러올 수 없습니다. (장 마감 직후·주말이면 데이터가 없을 수 있어요) 새로고침을 눌러보세요.")

    with col_gain:
        st.subheader("🔗 3. 글로벌 밸류체인 & 갭상승 대응 시나리오")
        if sel_tick != "N/A" and api_key_input:
            comp_name = sel_opt.split(" (")[1].replace(")", "")
            krx_df = get_krx_stocks()

            # [v7.0] 같은 종목이면 AI를 다시 부르지 않도록 세션에 캐싱 (폼 클릭 시 재호출 방지)
            if st.session_state.get('us_vc_ticker') != sel_tick:
                with st.spinner(f"✨ AI가 '{sel_tick}'의 공급망과 국장 수혜주를 분석 중입니다..."):
                    prompt = (
                        f"간밤에 미국 증시에서 '{comp_name}({sel_tick})' 종목이 급등했습니다. "
                        f"1.급등사유 2.한국 수혜주 3~5개(각 종목의 수혜 이유 포함) 3.시초가 갭상승 대응 시나리오를 작성하세요.\n"
                        f"⚠️ 반드시 맨 마지막 줄에 한국거래소에 상장된 정확한 종목명만 다음 형식으로 나열하세요: "
                        f"[수혜주]: 종목명1, 종목명2, 종목명3"
                    )
                    report = ask_gemini(prompt, api_key_input)
                    beneficiaries = extract_beneficiary_stocks(report, krx_df)
                    st.session_state.us_vc_ticker = sel_tick
                    st.session_state.us_vc_report = report
                    st.session_state.us_vc_benef = beneficiaries

            report = st.session_state.get('us_vc_report', '')
            beneficiaries = st.session_state.get('us_vc_benef', [])

            st.success("✅ 밸류체인 및 대응 시나리오 분석 완료!")
            # 화면에는 [수혜주] 파싱용 라인은 숨겨서 깔끔하게 표시
            display_report = re.sub(r'\n?\[?\s*수혜주[^\]:：]*\]?\s*[:：].*$', '', report).strip()
            st.markdown(display_report)

            st.divider()
            st.subheader("🎯 추천된 국장 수혜주 타점 즉시 확인")
            if beneficiaries:
                st.caption(f"💡 위 AI 분석에서 언급된 한국 수혜주 {len(beneficiaries)}개만 골라뒀어요. 선택하면 바로 타점을 분석합니다.")
                opts_krx = ["🔍 추천 수혜주 선택"] + [f"{n} ({c})" for n, c in beneficiaries]
                with st.form("vs_kr_form"):
                    col_v1, col_v2 = st.columns([8, 2])
                    with col_v1: us_sub_query = st.selectbox("추천 수혜주 타점 확인:", opts_krx, key="us_sub_scan", label_visibility="collapsed")
                    with col_v2: vs_btn = st.form_submit_button("🔍 타점 확인", use_container_width=True)
                if vs_btn and us_sub_query != "🔍 추천 수혜주 선택":
                    q_name = us_sub_query.rsplit(" (", 1)[0]
                    q_code = us_sub_query.rsplit("(", 1)[-1].replace(")", "").strip()
                    with st.spinner("차트 타점 분석 중..."):
                        res = analyze_technical_pattern(q_name, q_code)
                        if res: draw_stock_card(res, api_key_str=api_key_input, is_expanded=True, key_suffix="us_val_chain")
                        else: st.error("❌ 해당 종목 데이터를 불러올 수 없습니다.")
            else:
                st.warning("AI 분석에서 한국 수혜주를 자동으로 추출하지 못했어요. 아래에서 직접 검색해 확인할 수 있습니다.")
                if not krx_df.empty:
                    opts_krx = ["🔍 종목명 검색 후 엔터"] + (krx_df['Name'].astype(str) + " (" + krx_df['Code'].astype(str) + ")").tolist()
                    with st.form("vs_kr_form_fallback"):
                        col_v1, col_v2 = st.columns([8, 2])
                        with col_v1: us_sub_query = st.selectbox("수혜주 차트 상태 확인:", opts_krx, key="us_sub_scan_fb", label_visibility="collapsed")
                        with col_v2: vs_btn = st.form_submit_button("🔍 타점 확인", use_container_width=True)
                    if vs_btn and us_sub_query != "🔍 종목명 검색 후 엔터":
                        q_name = us_sub_query.rsplit(" (", 1)[0]
                        q_code = us_sub_query.rsplit("(", 1)[-1].replace(")", "").strip()
                        with st.spinner("차트 타점 분석 중..."):
                            res = analyze_technical_pattern(q_name, q_code)
                            if res: draw_stock_card(res, api_key_str=api_key_input, is_expanded=True, key_suffix="us_val_chain_fb")
                            else: st.error("❌ 해당 종목 데이터를 불러올 수 없습니다.")
        elif sel_tick != "N/A" and not api_key_input:
            st.warning("⬅️ 왼쪽에서 종목은 선택됐어요. AI 밸류체인 분석을 보려면 사이드바에 API 키를 입력해주세요.")
        else:
            st.info("⬅️ 왼쪽 급등주 목록에서 분석할 종목을 선택하면, AI가 한국 수혜주와 대응 시나리오를 여기에 보여줍니다.")

elif selected_menu == "🚨 당일 상/하한가 분석":
    st.subheader("🚨 당일 상/하한가 분석")
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
    st.markdown("## 🚦 거래량 급증 & 시장 경보")
    tab_regime, tab_vol, tab_warn = st.tabs(["🚦 오늘 매매해도 될까? (시장 국면)", "📊 거래량 급증/급감", "🛡️ 관리종목 및 시장경보"])

    with tab_regime:
        st.markdown("### 🚦 시장 국면 신호등")
        st.caption("개별 종목 신호가 아무리 좋아도 시장 전체가 약하면 승률이 떨어집니다. 먼저 '장'부터 확인하세요.")
        with st.spinner("KOSPI/KOSDAQ 지수 추세와 시장 폭을 분석 중입니다..."):
            render_market_regime_banner()
        with st.expander("📖 신호등 읽는 법", expanded=False):
            st.markdown("""
- **🟢 매수 우호:** 지수가 20일선 위 + 우상향(정배열). 추세·타점 신호가 나오면 적극 대응 OK.
- **🟡 중립/혼조:** 방향 불분명. 강한 신호(정배열+거래량+수급)만 선별 진입.
- **🔴 위험/관망:** 지수 역배열 또는 20일선 이탈. 신규 진입 자제, 현금 비중↑, 손절 타이트하게.
- **📊 시장 폭(Breadth):** 오른 종목 비율. **60%↑면 강세장**, 40%↓면 약세장으로 봅니다.
            """)

    with tab_vol:
        with st.spinner("데이터 스크래핑 중..."): surge_df, drop_df = get_volume_surge_drop()
        st.caption("💡 **거래량 폭증** = 평소보다 돈·관심이 몰린 종목 (세력 의심 / 급등 후보). "
                   "색상은 한국식 — 🔴빨강=상승, 🔵파랑=하락. 막대가 길수록 거래량이 더 터진 종목입니다.")

        c_surge, c_drop = st.columns(2)
        with c_surge:
            st.markdown("#### 🔥 거래량 급증 TOP")
            sty_s, _ = style_volume_table(surge_df, "surge")
            if sty_s is not None:
                st.dataframe(sty_s, use_container_width=True, height=560)
            elif not surge_df.empty:
                st.dataframe(surge_df, use_container_width=True, hide_index=True)
            else:
                st.error("❌ 현재 데이터를 불러올 수 없습니다.")
        with c_drop:
            st.markdown("#### ❄️ 거래량 급감 TOP")
            sty_d, _ = style_volume_table(drop_df, "drop")
            if sty_d is not None:
                st.dataframe(sty_d, use_container_width=True, height=560)
            elif not drop_df.empty:
                st.dataframe(drop_df, use_container_width=True, hide_index=True)
            else:
                st.error("❌ 현재 데이터를 불러올 수 없습니다.")
    with tab_warn:
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

elif selected_menu == "📰 실시간 특징주 속보 & 리포트":
    st.subheader("📰 실시간 특징주 속보 & 리포트")
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
                        st.caption("💡 증권사가 직전 리포트 대비 목표가를 올렸으면 🔴상향, 내렸으면 🔵하향. "
                                   "원문에 '종전 목표가'가 없으면 변동률은 `신규/유지`로 표시됩니다.")
                        upgrades = today_reports[today_reports['변동'] == '상향'].sort_values('변동률', ascending=False)
                        downgrades = today_reports[today_reports['변동'] == '하향'].sort_values('변동률', ascending=True)

                        col_up, col_down = st.columns(2)
                        with col_up:
                            st.success(f"**▲ 상향 리포트 ({len(upgrades)}건)**")
                            sty_up = style_report_table(upgrades, "up")
                            if sty_up is not None:
                                st.dataframe(sty_up, use_container_width=True, height=min(420, 80 + len(upgrades) * 36))
                            else:
                                st.write("목표가 상향 종목이 없습니다.")

                        with col_down:
                            st.error(f"**▼ 하향 리포트 ({len(downgrades)}건)**")
                            sty_down = style_report_table(downgrades, "down")
                            if sty_down is not None:
                                st.dataframe(sty_down, use_container_width=True, height=min(420, 80 + len(downgrades) * 36))
                            else:
                                st.write("목표가 하향 종목이 없습니다.")
                            
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
    st.markdown("## 🔬 개별 기업 정밀 진단 (AI 비전)")
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
                        if res: 
                            # 🌟 다중 테마 뷰어 출력 (국내 주식) 🌟
                            render_single_stock_themes(searched_name, api_key_input)
                            
                            draw_stock_card(res, api_key_str=api_key_input, is_expanded=True, key_suffix="t4_kr")
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
                        if res: 
                            # 🌟 다중 테마 뷰어 출력 (미국 주식) 🌟
                            render_single_stock_themes(us_ticker, api_key_input)
                            
                            draw_stock_card(res, api_key_str=api_key_input, is_expanded=True, key_suffix="t4_us")

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
    st.subheader("💰 고배당주 파이프라인 (TOP 300)")
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
            except: return 0.0
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

elif selected_menu == "🎯 증권사 목표가 컨센서스":
    st.markdown("## 🎯 증권사 목표가 컨센서스")
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
    st.markdown("## ⚖️ 적정 주가 계산기 (버핏 모델)")
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
    st.markdown("## 👴 노후 준비 ETF 시뮬레이터 (v2.0)")
    st.write("절세 계좌(연금저축/IRP/ISA) 활용법과 테마별 ETF 조합을 통해 은퇴 후 현금흐름을 설계합니다.")

    # --- 1. 절세 계좌 자동 배분 계산기 ---
    st.markdown("### 🎯 1. 월 투자금액별 절세 계좌 배분 최적화 가이드")
    
    st.info("""
    **💡 노후 자금은 왜 반드시 이 순서대로 계좌를 채워야 할까요? (절세 극대화 룰)**
    1. **1순위: 연금저축펀드 (연 600만 원 우선)** - 세액공제 및 수익률 극대화에 가장 유리합니다.
    2. **2순위: IRP (연 300만 원 추가)** - 연금저축과 합산해 총 900만 원까지 세액공제를 받습니다.
    3. **3순위: 중개형 ISA (연 2,000만 원 한도)** - 수익의 200~400만 원까지 비과세 혜택을 줍니다.
    4. **4순위: 일반/해외계좌** - 국가 절세 혜택을 소진한 뒤 남는 여유 현금을 굴리는 계좌입니다.
    """)

    with st.container(border=True):
        col_in, col_spacer = st.columns([2, 1])
        monthly_budget = col_in.number_input("월 총 노후대비 투자 가능 금액 (원)", min_value=0, step=100000, value=0)
        
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

    # 👇 네이버 금융 실시간 API 직결 엔진
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

    # 고정 테마 대배열 명단 (맞춤 종목 메뉴 최하단 고정)
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

    # --- 2. 스마트 맞춤 종목 다중 검색 ---
    if 'custom_etfs' not in st.session_state or (len(st.session_state.custom_etfs) > 0 and isinstance(st.session_state.custom_etfs[0], str)):
        st.session_state.custom_etfs = []
    if 'search_query' not in st.session_state: st.session_state.search_query = ""

    st.markdown("### 🔎 2. 맞춤형 종목 검색 및 추가")
    with st.container(border=True):
        st.markdown("**✨ 원하는 종목을 직접 찾아 내 포트폴리오에 담아보세요.**")
        
        cols = st.columns([4, 1], vertical_alignment="bottom")
        with cols[0]:
            search_input = st.text_input(
                "검색어 입력", 
                placeholder=" 🔍 검색어를 입력하세요. (예: 반도체, 삼성전자, SCHD)", 
                label_visibility="collapsed"
            ).strip()
        with cols[1]:
            search_clicked = st.button("종목 검색", type="primary", use_container_width=True)

        if search_clicked:
            if search_input: st.session_state.search_query = search_input
            else: st.warning("⚠️ 검색어를 먼저 입력해주세요!")

        if st.session_state.search_query:
            query = st.session_state.search_query
            search_options = []
            with st.spinner("데이터베이스에서 종목을 찾는 중입니다..."):
                kr_assets_df = get_naver_etf_and_stocks()
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
            
            st.divider()
            if search_options:
                with st.form(key="add_stock_form", clear_on_submit=True):
                    st.success(f"🎉 '{query}' 검색 결과 총 **{len(search_options)}개**를 찾았습니다!")
                    selected_to_add = st.multiselect("👇 결과 목록에서 장바구니에 담을 종목을 모두 골라주세요:", options=search_options)
                    submit_btn = st.form_submit_button("🛒 선택한 종목 포트폴리오에 추가하기", use_container_width=True)
                    
                    if submit_btn:
                        if selected_to_add:
                            added_count = 0
                            for sel in selected_to_add:
                                parts = sel.split(" [")
                                parsed_name, parsed_code = parts[0].strip(), parts[1].replace("]", "").strip()
                                if not any(item['code'] == parsed_code for item in st.session_state.custom_etfs):
                                    # 👇 [핵심 조치 1] 다른 테마로 숨지 않도록 강제로 "🔎 내가 추가한 맞춤 종목" 메뉴로 배치
                                    st.session_state.custom_etfs.append({
                                        'theme': "🔎 내가 추가한 맞춤 종목", 
                                        'name': parsed_name, 
                                        'code': parsed_code, 
                                        'holdings': '관심 종목 (아래 버튼으로 편입종목을 확인하세요)'
                                    })
                                    added_count += 1
                            if added_count > 0: st.toast(f"✅ {added_count}개 종목 추가 완료!", icon="✅")
                            st.session_state.search_query = ""
                            st.rerun()
                        else: st.warning("⚠️ 추가할 종목을 위에서 먼저 선택해주세요.")
            else: st.error("앗! 검색 결과가 없습니다. 🥲")

    # 👇 고정 마스터 리스트 (6번 항목 미국 배당주 통합)
    raw_etf_data = [
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

        {"theme": "💻 2. 반도체 & 빅테크 핵심 성장", "code": "381180", "name": "TIGER 미국테크TOP10 INDXX"},
        {"theme": "💻 2. 반도체 & 빅테크 핵심 성장", "code": "381170", "name": "TIGER 미국필라델피아반도체나스닥"},
        {"theme": "💻 2. 반도체 & 빅테크 핵심 성장", "code": "441680", "name": "ACE 글로벌반도체TOP4 Plus SOLACTIVE"},
        {"theme": "💻 2. 반도체 & 빅테크 핵심 성장", "code": "091160", "name": "KODEX 반도체"},
        {"theme": "💻 2. 반도체 & 빅테크 핵심 성장", "code": "091230", "name": "TIGER 반도체"},
        {"theme": "💻 2. 반도체 & 빅테크 핵심 성장", "code": "455850", "name": "SOL 반도체소부장Fn"},
        {"theme": "💻 2. 반도체 & 빅테크 핵심 성장", "code": "305720", "name": "KODEX 2차전지산업"},
        {"theme": "💻 2. 반도체 & 빅테크 핵심 성장", "code": "305540", "name": "TIGER 2차전지테마"},

        {"theme": "🤖 3. AI·로봇 & 사이버보안 혁신", "code": "456600", "name": "TIMEFOLIO 글로벌AI인공지능액티브"},
        {"theme": "🤖 3. AI·로봇 & 사이버보안 혁신", "code": "445290", "name": "KODEX 로봇액티브"},
        {"theme": "🤖 3. AI·로봇 & 사이버보안 혁신", "code": "462330", "name": "KODEX 로보틱스"},
        {"theme": "🤖 3. AI·로봇 & 사이버보안 혁신", "code": "469070", "name": "ACE AI로봇핵심장비TOP4플러스"},
        {"theme": "🤖 3. AI·로봇 & 사이버보안 혁신", "code": "411420", "name": "TIGER 글로벌사이버보안INDXX"},
        {"theme": "🤖 3. AI·로봇 & 사이버보안 혁신", "code": "276990", "name": "KODEX 글로벌4차산업로보틱스(합성)"},
        {"theme": "🤖 3. AI·로봇 & 사이버보안 혁신", "code": "275980", "name": "TIGER 글로벌4차산업혁신기술(합성 H)"},

        {"theme": "🚀 4. 방산 & 우주항공 미래 테크", "code": "449450", "name": "PLUS K방산"},
        {"theme": "🚀 4. 방산 & 우주항공 미래 테크", "code": "463250", "name": "TIGER K방산&우주"},
        {"theme": "🚀 4. 방산 & 우주항공 미래 테크", "code": "421320", "name": "PLUS 우주항공&UAM"},
        {"theme": "🚀 4. 방산 & 우주항공 미래 테크", "code": "440910", "name": "WON 미국우주항공방산"},

        {"theme": "🏦 5. 금융 지주 & 밸류업 모멘텀", "code": "466950", "name": "TIGER 은행고배당플러스TOP10"},
        {"theme": "🏦 5. 금융 지주 & 밸류업 모멘텀", "code": "474220", "name": "KODEX 은행고배당플러스"},
        {"theme": "🏦 5. 금융 지주 & 밸류업 모멘텀", "code": "091170", "name": "KODEX 은행"},
        {"theme": "🏦 5. 금융 지주 & 밸류업 모멘텀", "code": "287330", "name": "RISE 금융지주"},
        {"theme": "🏦 5. 금융 지주 & 밸류업 모멘텀", "code": "494330", "name": "KODEX 코리아밸류업"},
        {"theme": "🏦 5. 금융 지주 & 밸류업 모멘텀", "code": "494340", "name": "TIGER 코리아밸류업"},
        {"theme": "🏦 5. 금융 지주 & 밸류업 모멘텀", "code": "492500", "name": "RISE 현대차그룹밸류업모멘텀"},
        {"theme": "🏦 5. 금융 지주 & 밸류업 모멘텀", "code": "466810", "name": "ACE 주주환원가치주액티브"},
        {"theme": "🏦 5. 금융 지주 & 밸류업 모멘텀", "code": "157500", "name": "TIGER 증권"},

        {"theme": "💰 6. 고배당 & 월배당 인컴 밸류업", "code": "458730", "name": "TIGER 미국배당다우존스"},
        {"theme": "💰 6. 고배당 & 월배당 인컴 밸류업", "code": "488210", "name": "KODEX 미국배당다우존스"},
        {"theme": "💰 6. 고배당 & 월배당 인컴 밸류업", "code": "446720", "name": "SOL 미국배당다우존스"},
        {"theme": "💰 6. 고배당 & 월배당 인컴 밸류업", "code": "210780", "name": "TIGER 코스피고배당"},
        {"theme": "💰 6. 고배당 & 월배당 인컴 밸류업", "code": "276970", "name": "KODEX 고배당"},
        {"theme": "💰 6. 고배당 & 월배당 인컴 밸류업", "code": "461580", "name": "TIGER 미국배당+7%프리미엄다우존스"},
        {"theme": "💰 6. 고배당 & 월배당 인컴 밸류업", "code": "SCHD", "name": "Schwab US Dividend Equity ETF"},
        {"theme": "💰 6. 고배당 & 월배당 인컴 밸류업", "code": "JEPI", "name": "JPMorgan Equity Premium Income ETF"},
        {"theme": "💰 6. 고배당 & 월배당 인컴 밸류업", "code": "JEPQ", "name": "JPMorgan Nasdaq Equity Premium Income ETF"},
        {"theme": "💰 6. 고배당 & 월배당 인컴 밸류업", "code": "O", "name": "Realty Income Corp"},
        {"theme": "💰 6. 고배당 & 월배당 인컴 밸류업", "code": "MAIN", "name": "Main Street Capital"},
        {"theme": "💰 6. 고배당 & 월배당 인컴 밸류업", "code": "VIG", "name": "Vanguard Dividend Appreciation ETF"},
        {"theme": "💰 6. 고배당 & 월배당 인컴 밸류업", "code": "VYM", "name": "Vanguard High Dividend Yield ETF"},
        {"theme": "💰 6. 고배당 & 월배당 인컴 밸류업", "code": "DGRW", "name": "WisdomTree US Quality Dividend Growth"},
        {"theme": "💰 6. 고배당 & 월배당 인컴 밸류업", "code": "SDY", "name": "SPDR S&P Dividend ETF"},
        {"theme": "💰 6. 고배당 & 월배당 인컴 밸류업", "code": "MO", "name": "Altria Group Inc"},
        {"theme": "💰 6. 고배당 & 월배당 인컴 밸류업", "code": "PM", "name": "Philip Morris International"},
        {"theme": "💰 6. 고배당 & 월배당 인컴 밸류업", "code": "VZ", "name": "Verizon Communications"},
        {"theme": "💰 6. 고배당 & 월배당 인컴 밸류업", "code": "T", "name": "AT&T Inc"},
        {"theme": "💰 6. 고배당 & 월배당 인컴 밸류업", "code": "CVX", "name": "Chevron Corp"},
        {"theme": "💰 6. 고배당 & 월배당 인컴 밸류업", "code": "XOM", "name": "Exxon Mobil Corp"},
        {"theme": "💰 6. 고배당 & 월배당 인컴 밸류업", "code": "PEP", "name": "PepsiCo Inc"},
        {"theme": "💰 6. 고배당 & 월배당 인컴 밸류업", "code": "KO", "name": "Coca-Cola Co"},
        {"theme": "💰 6. 고배당 & 월배당 인컴 밸류업", "code": "PG", "name": "Procter & Gamble Co"},
        {"theme": "💰 6. 고배당 & 월배당 인컴 밸류업", "code": "ABBV", "name": "AbbVie Inc"},
        {"theme": "💰 6. 고배당 & 월배당 인컴 밸류업", "code": "PFE", "name": "Pfizer Inc"},
        {"theme": "💰 6. 고배당 & 월배당 인컴 밸류업", "code": "MMM", "name": "3M Co"},
        {"theme": "💰 6. 고배당 & 월배당 인컴 밸류업", "code": "IBM", "name": "International Business Machines"},
        {"theme": "💰 6. 고배당 & 월배당 인컴 밸류업", "code": "HD", "name": "Home Depot Inc"},
        {"theme": "💰 6. 고배당 & 월배당 인컴 밸류업", "code": "LOW", "name": "Lowe's Companies Inc"},
        {"theme": "💰 6. 고배당 & 월배당 인컴 밸류업", "code": "CSCO", "name": "Cisco Systems Inc"},
        {"theme": "💰 6. 고배당 & 월배당 인컴 밸류업", "code": "TLT", "name": "iShares 20+ Year Treasury Bond ETF"},
        {"theme": "💰 6. 고배당 & 월배당 인컴 밸류업", "code": "DIVO", "name": "Amplify CWP Strategic Focus Equity ETF"},
        {"theme": "💰 6. 고배당 & 월배당 인컴 밸류업", "code": "STAG", "name": "STAG Industrial Inc"},
        {"theme": "💰 6. 고배당 & 월배당 인컴 밸류업", "code": "VICI", "name": "VICI Properties Inc"},
        {"theme": "💰 6. 고배당 & 월배당 인컴 밸류업", "code": "ADC", "name": "Agree Realty Corp"},

        {"theme": "🛡️ 7. 안전자산 채권 & 원자재 방어", "code": "273130", "name": "KODEX 종합채권(AA-이상)액티브"},
        {"theme": "🛡️ 7. 안전자산 채권 & 원자재 방어", "code": "423160", "name": "KODEX KOFR금리액티브(합성)"},
        {"theme": "🛡️ 7. 안전자산 채권 & 원자재 방어", "code": "411060", "name": "ACE KRX금현물"},
        {"theme": "🛡️ 7. 안전자산 채권 & 원자재 방어", "code": "132030", "name": "KODEX 골드선물(H)"},
        {"theme": "🛡️ 7. 안전자산 채권 & 원자재 방어", "code": "138900", "name": "TIGER 구리선물(H)"},
        {"theme": "🛡️ 7. 안전자산 채권 & 원자재 방어", "code": "153130", "name": "KODEX 단기채권"},

        {"theme": "🌍 8. 해외 직상장 글로벌 메이저", "code": "SPY", "name": "SPDR S&P 500"},
        {"theme": "🌍 8. 해외 직상장 글로벌 메이저", "code": "VOO", "name": "Vanguard S&P 500"},
        {"theme": "🌍 8. 해외 직상장 글로벌 메이저", "code": "QQQ", "name": "Invesco QQQ"},
        {"theme": "🌍 8. 해외 직상장 글로벌 메이저", "code": "SOXX", "name": "iShares Semiconductor"},

        {"theme": "🚢 9. 조선 & 해운 슈퍼사이클", "code": "091180", "name": "KODEX 조선"},
        {"theme": "🚢 9. 조선 & 해운 슈퍼사이클", "code": "380960", "name": "HANARO Fn조선해운"},
        {"theme": "🚢 9. 조선 & 해운 슈퍼사이클", "code": "466920", "name": "SOL 조선TOP3플러스"},

        {"theme": "⚡ 10. 전력 인프라 & 글로벌 에너지", "code": "226490", "name": "KODEX 에너지화학"},
        {"theme": "⚡ 10. 전력 인프라 & 글로벌 에너지", "code": "117460", "name": "TIGER 에너지화학"},
        {"theme": "⚡ 10. 전력 인프라 & 글로벌 에너지", "code": "442320", "name": "RISE 글로벌원자력"},
        {"theme": "⚡ 10. 전력 인프라 & 글로벌 에너지", "code": "418650", "name": "HANARO 글로벌수소&차세대연료전지"},
        {"theme": "⚡ 10. 전력 인프라 & 글로벌 에너지", "code": "385600", "name": "KODEX K-신재생에너지액티브"},
        {"theme": "⚡ 10. 전력 인프라 & 글로벌 에너지", "code": "XLU", "name": "Utilities Select Sector SPDR"},
        {"theme": "⚡ 10. 전력 인프라 & 글로벌 에너지", "code": "ICLN", "name": "iShares Global Clean Energy"}
    ]

    # 공식 명칭 동기화 및 덮어쓰기
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
                code = str(it['code']).zfill(6) if str(it['code']).isdigit() else str(it['code'])
                is_kr = len(code) == 6 and code.isdigit()
                if is_kr and code in krx_name_map: new_it['name'] = krx_name_map[code]
                elif not is_kr and code in us_name_map and us_name_map[code] != code: new_it['name'] = us_name_map[code]
                new_it['code'] = code
                updated_items.append(new_it)
            return updated_items
        except: return items 

    etf_data = update_official_names(raw_etf_data)
    for item in etf_data:
        item.update({"price": 0, "cagr": "데이터없음", "list_date": "데이터없음", "holdings": "해당 테마 핵심 우량종목 (아래 버튼으로 검색 가능)"})

    # 사용자가 직접 추가한 종목도 리스트에 이식
    for custom_item in st.session_state.custom_etfs:
        if not any(item['code'] == custom_item['code'] for item in etf_data):
            etf_data.append({
                "theme": "🔎 내가 추가한 맞춤 종목",  # 무조건 고정
                "name": custom_item['name'], 
                "code": custom_item['code'], 
                "price": 0, 
                "cagr": "데이터없음", 
                "list_date": "데이터없음", 
                "holdings": "관심 종목 (아래 버튼으로 편입종목 검색 가능)"
            })

    # 👇 실시간 가격 및 백데이터 로딩 엔진
    import yfinance as yf
    import concurrent.futures
    @st.cache_data(ttl=3600)
    def fetch_realtime_data(codes, ex_rate):
        prices, cagrs = {}, {}
        kr_codes = [c for c in codes if len(str(c)) == 6 and any(char.isdigit() for char in str(c))]
        us_codes = [c for c in codes if c not in kr_codes]
        
        # 1) 국내 실시간 가격
        bulk_krx = get_naver_etf_and_stocks()
        if not bulk_krx.empty:
            p_dict = dict(zip(bulk_krx['Code'], bulk_krx['Price']))
            for c in kr_codes:
                if c in p_dict and int(p_dict[c]) > 0: prices[c] = int(p_dict[c])

        # 1-B) [0원 방어] 일괄 조회에서 누락(0원)된 국내 종목만 개별 보강
        def get_kr_price_fallback(c):
            # (a) 네이버 차트 API의 가장 최근 종가를 현재가로 사용
            try:
                url = f"https://fchart.stock.naver.com/sise.nhn?symbol={c}&timeframe=day&count=5&requestType=0"
                res = requests.get(url, headers={'User-Agent': 'Mozilla/5.0'}, timeout=5)
                if res.status_code == 200:
                    soup = BeautifulSoup(res.text, 'html.parser')
                    items = soup.find_all('item')
                    if items:
                        last_close = float(items[-1].get('data').split('|')[4])
                        if last_close > 0:
                            return c, int(last_close)
            except: pass
            # (b) FinanceDataReader 최근 종가로 2차 보강
            try:
                df = fdr.DataReader(c)
                if not df.empty:
                    last_close = float(df['Close'].iloc[-1])
                    if last_close > 0:
                        return c, int(last_close)
            except: pass
            return c, 0

        missing_kr = [c for c in kr_codes if prices.get(c, 0) == 0]
        if missing_kr:
            with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
                for c, p in executor.map(get_kr_price_fallback, missing_kr):
                    if p > 0: prices[c] = p

        # 2) 국내 백데이터
        def get_kr_historical_info(c):
            try:
                url = f"https://fchart.stock.naver.com/sise.nhn?symbol={c}&timeframe=month&count=1200&requestType=0"
                res = requests.get(url, headers={'User-Agent': 'Mozilla/5.0'}, timeout=5)
                if res.status_code == 200:
                    soup = BeautifulSoup(res.text, 'html.parser')
                    items = soup.find_all('item')
                    if len(items) > 12:
                        first_date, last_date = items[0].get('data').split('|')[0], items[-1].get('data').split('|')[0]
                        p_start, p_end = float(items[0].get('data').split('|')[4]), float(items[-1].get('data').split('|')[4])
                        days = (pd.to_datetime(last_date) - pd.to_datetime(first_date)).days
                        if days >= 365 and p_start > 0:
                            cagr = ((p_end / p_start) ** (365.25 / days) - 1) * 100
                            return c, round(cagr, 2), pd.to_datetime(first_date).strftime('%Y-%m-%d')
            except: pass
            try:
                df = fdr.DataReader(c)
                if len(df) > 250:
                    p_start, p_end = float(df['Close'].iloc[0]), float(df['Close'].iloc[-1])
                    days = (df.index[-1] - df.index[0]).days
                    if days >= 365 and p_start > 0:
                        cagr = ((p_end / p_start) ** (365.25 / days) - 1) * 100
                        return c, round(cagr, 2), df.index[0].strftime('%Y-%m-%d')
            except: pass
            return c, 0.0, "데이터없음"

        if kr_codes:
            with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
                for c, cg, dt in executor.map(get_kr_historical_info, kr_codes):
                    if dt != "데이터없음": cagrs[c] = {'cagr': cg, 'date': dt}

        # 3) 미국 실시간 가격 및 백데이터
        def get_us_info(c):
            try:
                hist = yf.Ticker(c).history(period="max", interval="1mo")
                if not hist.empty:
                    p = float(hist['Close'].iloc[-1])
                    p_start = float(hist['Close'].iloc[0])
                    days = (hist.index[-1] - hist.index[0]).days
                    cagr = ((p / p_start) ** (365.25 / days) - 1) * 100 if days > 365 else 0
                    return c, int(p * ex_rate), round(cagr, 2), hist.index[0].strftime('%Y-%m-%d')
            except: pass
            return c, 0, 0, "데이터없음"

        if us_codes:
            with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
                for c, p, cg, dt in executor.map(get_us_info, us_codes):
                    if p > 0: prices[c] = p
                    if cg != 0: cagrs[c] = {'cagr': cg, 'date': dt}
        return prices, cagrs

    with st.spinner("최신 마켓 데이터를 전수 매칭하는 중입니다..."):
        ex_rate = st.session_state.get('ex_rate', 1350.0)
        # [v7.0] 잘못된/리브랜딩된 코드 자동 보정 (이름 기준 실시간 목록 매칭)
        resolve_etf_codes(etf_data, get_naver_etf_and_stocks())
        real_prices, real_cagrs = fetch_realtime_data([item['code'] for item in etf_data], ex_rate)
        for item in etf_data:
            if item['code'] in real_prices: item['price'] = real_prices[item['code']]
            if item['code'] in real_cagrs:
                item['cagr'], item['list_date'] = real_cagrs[item['code']]['cagr'], real_cagrs[item['code']]['date']

    # --- 3. 포트폴리오 구성 UI ---
    st.markdown("### 🛒 3. 나만의 노후 포트폴리오 담기")
    if 'retirement_cart' not in st.session_state: st.session_state.retirement_cart = {}

    for theme in theme_order:
        theme_stocks = [item for item in etf_data if item['theme'] == theme]
        seen = set()
        unique_stocks = [s for s in theme_stocks if s['code'] not in seen and not seen.add(s['code'])]

        if unique_stocks:
            with st.expander(f"{theme} 선택", expanded=False):
                for idx, stock in enumerate(unique_stocks):
                    cols = st.columns([3, 1.5, 1.5, 1.5, 1.5, 1]) 
                    
                    with cols[0]: 
                        st.markdown(f"**{stock['name']}** ({stock['code']})")
                        
                        # 👇 [핵심 조치 2] 제한 없이 "모든 종목"에 대해 AI 편입종목 검색 기능 제공
                        current_holdings = st.session_state.get(f"holdings_{stock['code']}", stock['holdings'])
                        st.caption(f"🔍 {current_holdings}")
                        
                        if "💡 AI" not in current_holdings:
                            if st.button("🤖 편입종목 검색", key=f"ai_h_{stock['code']}_{idx}"):
                                if not api_key_input:
                                    st.error("좌측 사이드바에 API 키를 입력해주세요.")
                                else:
                                    with st.spinner("AI가 편입 종목을 분석 중입니다..."):
                                        ai_prompt = f"주식/ETF '{stock['name']} ({stock['code']})'가 가장 많이 편입하고 있는 핵심 종목 5~10개를 쉼표로 나열해줘. 다른 말은 하지 마."
                                        ai_holdings = ask_gemini(ai_prompt, api_key_input)
                                        st.session_state[f"holdings_{stock['code']}"] = "💡 AI 분석: " + ai_holdings
                                        st.rerun()

                    cols[1].markdown(f"현재가:<br>{stock['price']:,}원", unsafe_allow_html=True)
                    cols[2].markdown(f"상장일:<br>{stock.get('list_date', '데이터없음')}", unsafe_allow_html=True)
                    c_val = stock['cagr']
                    cols[3].markdown(f"수익률:<br>{c_val}%" if isinstance(c_val, (int, float)) else f"수익률:<br>{c_val}", unsafe_allow_html=True)
                    
                    qty = cols[4].number_input("수량", min_value=0, step=1, key=f"ret_qty_{theme}_{stock['code']}_{idx}", label_visibility="collapsed")
                    if qty > 0: st.session_state.retirement_cart[stock['code']] = {"name": stock['name'], "qty": qty, "price": stock['price'], "cagr": stock['cagr'] if isinstance(stock['cagr'], (int, float)) else 0}
                    elif stock['code'] in st.session_state.retirement_cart: del st.session_state.retirement_cart[stock['code']]
                    
                    # 맞춤 종목만 삭제 버튼 활성화
                    is_custom = any(c['code'] == stock['code'] for c in st.session_state.custom_etfs)
                    if is_custom:
                        if cols[5].button("🗑️ 삭제", key=f"del_{theme}_{stock['code']}_{idx}"):
                            st.session_state.custom_etfs = [x for x in st.session_state.custom_etfs if x['code'] != stock['code']]
                            if stock['code'] in st.session_state.retirement_cart: del st.session_state.retirement_cart[stock['code']]
                            st.rerun()

    # --- 4. 시뮬레이션 대시보드 ---
    st.divider()
    st.markdown("### 📊 4. 복리 성장 & 노후 현금흐름 시뮬레이션")
    cart = st.session_state.retirement_cart
    if cart:
        total_p = sum(v['qty'] * v['price'] for v in cart.values())
        w_cagr = sum(v['qty'] * v['price'] * v['cagr'] for v in cart.values()) / total_p if total_p > 0 else 0

        # 투자 방식 / 기간 / 월 적립금 입력
        opt1, opt2, opt3 = st.columns([1.3, 1, 1])
        invest_mode = opt1.radio("투자 방식", ["💰 거치식 (목돈 한 번)", "📅 적립식 (매달 추가)"], horizontal=False)
        yrs = opt2.select_slider("투자기간 (년)", options=[1, 3, 5, 10, 15, 20, 25, 30], value=20)
        default_monthly = int(monthly_budget) if 'monthly_budget' in dir() and monthly_budget else 0
        monthly_add = opt3.number_input("매달 추가 투자금 (원)", min_value=0, step=100000, value=default_monthly,
                                        help="위 1번에서 입력한 월 투자금이 기본값으로 들어옵니다. 적립식일 때 사용됩니다.")

        r = w_cagr / 100.0
        is_install = invest_mode.startswith("📅")
        # 미래가치 계산
        fv_lump = total_p * ((1 + r) ** yrs)
        if is_install and monthly_add > 0:
            r_m = r / 12.0
            n = yrs * 12
            fv_series = monthly_add * ((((1 + r_m) ** n) - 1) / r_m) if r_m != 0 else monthly_add * n
            fv = fv_lump + fv_series
            total_invested = total_p + monthly_add * n
        else:
            fv = fv_lump
            total_invested = total_p

        inflation = 0.025  # 연 2.5% 물가 가정
        real_fv = fv / ((1 + inflation) ** yrs)
        monthly_pension = fv * 0.04 / 12  # 4% 인출 룰 → 월 연금
        profit = fv - total_invested

        # 핵심 지표 4종
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("총 투자 원금", f"{int(total_invested):,}원",
                  f"수익 +{int(profit):,}원" if profit >= 0 else f"{int(profit):,}원", delta_color="normal")
        m2.metric(f"{yrs}년 후 예상 자산", f"{int(fv):,}원")
        m3.metric("실질가치 (오늘 돈 기준)", f"{int(real_fv):,}원", help="연 2.5% 물가상승률을 반영한 현재가치")
        m4.metric("은퇴 후 예상 월 연금", f"{int(monthly_pension):,}원", help="4% 인출 룰 기준 (자산의 연 4%를 매년 인출)")

        st.caption(f"📈 가중평균 수익률(CAGR) **{w_cagr:.2f}%** 가정 · "
                   f"{'매달 ' + format(monthly_add, ',') + '원씩 ' + str(yrs) + '년 적립' if is_install and monthly_add > 0 else '목돈 거치 ' + str(yrs) + '년'}")

        # 자산 성장 차트 (투입 원금 vs 평가액)
        rows = []
        for y in range(yrs + 1):
            lump_y = total_p * ((1 + r) ** y)
            if is_install and monthly_add > 0:
                r_m = r / 12.0; n_y = y * 12
                ser_y = monthly_add * ((((1 + r_m) ** n_y) - 1) / r_m) if r_m != 0 else monthly_add * n_y
                val_y = lump_y + ser_y
                inv_y = total_p + monthly_add * n_y
            else:
                val_y = lump_y
                inv_y = total_p
            rows.append({"년수": f"{y}년", "투입 원금": float(inv_y), "평가액": float(val_y)})
        st.area_chart(pd.DataFrame(rows).set_index("년수"))

        # 포트폴리오 비중 (막대) + 명세서
        pf_col1, pf_col2 = st.columns([1, 1])
        with pf_col1:
            st.markdown("#### 🥧 포트폴리오 비중")
            wdf = pd.DataFrame([{"종목": v['name'], "비중": round(v['qty'] * v['price'] / total_p * 100, 1)}
                                for v in cart.values()]).sort_values("비중", ascending=False)
            wdf_show = wdf.set_index("종목")
            try:
                sty_w = wdf_show.style.format({"비중": "{:.1f}%"}).bar(subset=["비중"], color="#ffd8a8", vmin=0)
                st.dataframe(sty_w, use_container_width=True, height=300)
            except Exception:
                st.dataframe(wdf_show, use_container_width=True)
            if len(wdf) >= 1 and wdf.iloc[0]["비중"] >= 50:
                st.caption(f"⚠️ '{wdf.iloc[0]['종목']}' 비중이 {wdf.iloc[0]['비중']}%로 높아요. 분산을 권장합니다.")
        with pf_col2:
            st.markdown("#### 📝 내 포트폴리오 명세서")
            st.dataframe(pd.DataFrame([{'종목명': v['name'], '수량': f"{v['qty']}주",
                                        '현재가': f"{v['price']:,}원", '총액': f"{v['qty'] * v['price']:,}원",
                                        '연수익률': f"{v['cagr']}%"} for v in cart.values()]),
                         use_container_width=True, hide_index=True, height=300)
        st.caption("※ '데이터없음' 종목은 계산 안전을 위해 수익률 0%로 보수 적용 ｜ 4% 룰·물가 2.5%는 가정치이며 실제와 다를 수 있습니다.")

        st.markdown("---")
        if st.button("🤖 AI 노후 포트폴리오 정밀 진단 (클릭)", type="primary", use_container_width=True):
            if not api_key_input:
                st.error("사이드바에 API 키를 먼저 입력해주세요.")
            else:
                with st.spinner("AI가 은퇴 설계 전문가의 관점으로 포트폴리오를 분석 중입니다..."):
                    port_str = "".join([f"- {v['name']}: 비중 {(v['qty'] * v['price'] / total_p) * 100:.1f}%, 총액 {v['qty'] * v['price']:,}원\n" for v in cart.values()])
                    ai_prompt = (f"은퇴 설계 전문가로서 다음 포트폴리오를 진단해 주세요.\n"
                                 f"투자 방식: {'적립식(매달 ' + format(monthly_add, ',') + '원)' if is_install else '거치식'}\n"
                                 f"총 투자원금: {int(total_invested):,}원\n예상 CAGR: {w_cagr:.2f}%\n투자기간: {yrs}년\n"
                                 f"{yrs}년 후 예상자산(명목): {int(fv):,}원, 은퇴 후 월 연금(4%룰): {int(monthly_pension):,}원\n{port_str}\n"
                                 f"1.분산/리스크 진단 2.개선 제안 3.이 월 연금으로 노후가 충분한지 평가, 순으로 작성하세요.")
                    st.success("✅ 진단 완료!")
                    st.markdown(ask_gemini(ai_prompt, api_key_input))
    else:
        st.info("💡 위 리스트에서 수량을 입력하시면 시뮬레이션이 즉시 시작됩니다.")

    # 0원 검출기를 화면 맨 하단으로 깔끔하게 이동 배치
    st.divider()
    st.markdown("### 🚨 시스템 상태 분석기")
    with st.expander("⚠️ 데이터 통신 지연 종목 확인 (0원 에러 검출기)", expanded=False):
        errs = [it for it in etf_data if it.get('price', 0) == 0]
        if errs:
            st.error(f"현재 총 {len(errs)}개 종목의 데이터 수집이 지연되고 있습니다.")
            st.table(pd.DataFrame([{'테마': i['theme'], '종목': i['name'], '코드': i['code']} for i in errs]))
        else: 
            st.success("🎉 현재 시스템상 가격이 0원으로 조회되는 오류 종목이 단 하나도 없습니다! (무결점 상태)")

# ==========================================
# [v7.0] 🔮 폴리마켓 예측시장 (금리·경제·정치)
# ==========================================
elif selected_menu == "🔮 폴리마켓 예측시장 (금리·경제·정치)":
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
                                     help="폴리마켓 질문/선택지를 Gemini로 번역해 보여줍니다. (끄면 영어 원문)")
            # 번역 대상: 표/상세에 쓰이는 상위 마켓 위주 (API 호출 최소화)
            TR_N = min(len(markets), 30)
            trans_map = {}
            if show_ko:
                if not api_key_input:
                    tr_col2.warning("⚠️ 번역하려면 좌측 사이드바에 Gemini API 키가 필요합니다. (지금은 영어 원문 표시)")
                else:
                    to_translate = []
                    for m in markets[:TR_N]:
                        to_translate.append(m["question"])
                        for o in (m["outcomes"] or []):
                            # Yes/No 는 굳이 번역 호출에 넣지 않음 (아래서 자체 처리)
                            if o not in ("Yes", "No"):
                                to_translate.append(o)
                    with st.spinner("질문을 한글로 번역하는 중... (최초 1회만, 이후 캐시)"):
                        trans_map = translate_poly_questions(tuple(to_translate), api_key_input)

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
