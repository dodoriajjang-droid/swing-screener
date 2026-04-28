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

# ==========================================
# 0. 로컬 영구 저장소 (관심종목 유지용)
# ==========================================
WATCHLIST_FILE = "watchlist.json"

def load_watchlist():
    if os.path.exists(WATCHLIST_FILE):
        try:
            with open(WATCHLIST_FILE, "r", encoding="utf-8") as f: return json.load(f)
        except: return []
    return []

def save_watchlist(wl):
    try:
        with open(WATCHLIST_FILE, "w", encoding="utf-8") as f: json.dump(wl, f, ensure_ascii=False, indent=4)
    except Exception as e: st.error(f"관심종목 저장 실패: {e}")

# ==========================================
# 1. 초기 설정 
# ==========================================
st.set_page_config(page_title="Jaemini PRO 터미널 v5.8", layout="wide", page_icon="📈")
st_autorefresh(interval=300000, limit=None, key="news_autorefresh")

# 세션 상태 초기화
for key in ['seen_links', 'seen_titles', 'news_data']:
    if key not in st.session_state: st.session_state[key] = set() if 'seen' in key else []
if 'watchlist' not in st.session_state: st.session_state.watchlist = load_watchlist()
if 'quick_analyze_news' not in st.session_state: st.session_state.quick_analyze_news = None
if 'scan_results' not in st.session_state: st.session_state.scan_results = None
if 'value_scan_results' not in st.session_state: st.session_state.value_scan_results = None
if 'pension_scan_results' not in st.session_state: st.session_state.pension_scan_results = None
if 'v4_chat_history' not in st.session_state: st.session_state.v4_chat_history = [{"role": "assistant", "content": "안녕하세요! 여의도 퀀트 비서입니다. 오늘 시장 매크로 상황이나 투자 전략에 대해 무엇이든 물어보세요."}]

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

if 'price_scan_results' not in st.session_state: st.session_state.price_scan_results = None

# ==========================================
# 2. 통합 데이터 수집 & AI 함수 모음
# ==========================================
@st.cache_data(ttl=3600)
def ask_gemini(prompt, _api_key):
    if not _api_key: return "API 키가 필요합니다."
    try:
        genai.configure(api_key=_api_key)
        return genai.GenerativeModel('gemini-3.1-flash-lite-preview').generate_content(prompt).text
    except Exception as e: 
        if "429" in str(e) or "quota" in str(e).lower() or "spending cap" in str(e).lower():
            return "🚨 AI API 무료 한도가 초과되었거나 결제 한도에 도달했습니다."
        return f"AI 분석 오류: {str(e)}"

def ask_gemini_vision(prompt, image_obj, _api_key):
    if not _api_key: return "API 키가 필요합니다."
    try:
        genai.configure(api_key=_api_key)
        model = genai.GenerativeModel('gemini-3.1-flash-lite-preview')
        response = model.generate_content([prompt, image_obj])
        return response.text
    except Exception as e:
        return f"🚨 비전 분석 오류: {str(e)}"

@st.cache_data(ttl=86400)
def get_daily_market_briefing(macro_data, top_gainers, _api_key):
    if not _api_key: return "API 키가 필요합니다."
    vix = f"{macro_data['VIX']['value']:.2f}" if macro_data and 'VIX' in macro_data else 'N/A'
    sox = f"{macro_data['필라델피아 반도체']['value']:.2f}" if macro_data and '필라델피아 반도체' in macro_data else 'N/A'
    krw = f"{macro_data['원/달러 환율']['value']:.1f}" if macro_data and '원/달러 환율' in macro_data else 'N/A'
    tnx = f"{macro_data['美 10년물 국채']['value']:.3f}" if macro_data and '美 10년물 국채' in macro_data else 'N/A'
    gainers_str = ", ".join(top_gainers) if top_gainers else '데이터 없음'
    today_str = (datetime.utcnow() + timedelta(hours=9)).strftime("%Y년 %m월 %d일")

    prompt = f"""
    당신은 여의도 최고의 시황 애널리스트입니다.
    🚨 중요: 오늘은 정확히 {today_str}입니다. 절대 과거 날짜를 지어내지 마세요.
    [현재 글로벌 매크로 및 수급 데이터] VIX:{vix} / SOX:{sox} / 환율:{krw} / 美국채:{tnx} / 미급등주:{gainers_str}
    위 데이터를 바탕으로 다음 3가지 항목을 마크다운 포맷으로 가독성 좋게 작성해주세요. 
    1. 🇺🇸 **간밤의 미 증시 요약** (2~3줄)
    2. 🇰🇷 **국내 증시 투자의견** (2~3줄)
    3. 🎯 **오늘의 픽 (주목할 섹터)** (1줄)
    """
    return ask_gemini(prompt, _api_key)

@st.cache_data(ttl=3600)
def analyze_news_with_gemini(ticker, _api_key):
    try:
        news_list = yf.Ticker(ticker).news
        if not news_list: return "최근 관련 뉴스를 찾을 수 없습니다."
        news_text = "\n".join([f"[{n.get('publisher')}] {n.get('title')}" for n in news_list[:3]])
        prompt = f"한국 주식 스윙 전문 애널리스트입니다. 미국 주식 '{ticker}' 영문 헤드라인을 바탕으로 한국 테마주에 미칠 영향을 분석하세요.\n{news_text}\n* 시장 센티먼트:\n* 재료 지속성:\n* 투자 코멘트:"
        return ask_gemini(prompt, _api_key)
    except: return "뉴스 분석 중 오류가 발생했습니다."

@st.cache_data(ttl=10800)
def get_trending_themes_with_ai(_api_key):
    default_themes = ["AI 반도체", "비만치료제", "저PBR/밸류업", "전력 설비", "로봇/자동화"]
    if not _api_key: return default_themes
    try:
        prompt = "최근 한국 증시에서 가장 자금이 많이 몰리고 상승세가 강한 주도 테마 4개만 정확히 쉼표(,)로 구분해서 단어 형태로 1줄로 출력하세요. 부연설명, 번호표, 특수문자 절대 금지. 예시: 반도체장비, 2차전지, 제약바이오, 원자력"
        response = ask_gemini(prompt, _api_key)
        valid_themes = [t.strip() for t in response.replace('\n', '').replace('*', '').replace('-', '').replace('.', '').split(',') if t.strip()]
        return valid_themes[:4] if len(valid_themes) >= 4 else default_themes[:4]
    except: return default_themes

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
            if clean_name in name_to_code:
                final_name = clean_name
                final_code = name_to_code[clean_name]
            elif code in code_to_name:
                final_name = code_to_name[code]
                final_code = code
            if final_name and final_code and final_code not in seen:
                seen.add(final_code)
                validated.append((final_name, final_code))
        return validated[:20]
    except: return []

@st.cache_data(ttl=3600)
def get_longterm_value_stocks_with_ai(strategy, cap_size, _api_key):
    if not _api_key: return []
    try:
        prompt = f"당신은 여의도의 15년차 시니어 펀드매니저입니다. 한국 증시(코스피/코스닥)에서 다음 투자 전략에 가장 완벽하게 부합하는 숨겨진 우량주 20개를 발굴해주세요.\n- 투자 전략: {strategy}\n- 기업 규모: {cap_size}\n단기 테마주나 작전주는 철저히 배제하고, 실제 비즈니스 모델, 경제적 해자, 펀더멘털이 우수한 종목만 엄선하세요. 반드시 파이썬 리스트로만 답변하세요. 예시: [('삼성전자', '005930')]"
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
            if clean_name in name_to_code:
                final_name = clean_name
                final_code = name_to_code[clean_name]
            elif code in code_to_name:
                final_name = code_to_name[code]
                final_code = code
            if final_name and final_code and final_code not in seen:
                seen.add(final_code)
                validated.append((final_name, final_code))
        return validated[:20]
    except: return []

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

@st.cache_data(ttl=1800)
def get_fear_and_greed():
    url = "https://production.dataviz.cnn.io/index/fearandgreed/graphdata"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "Accept": "application/json",
        "Referer": "https://edition.cnn.com/"
    }
    try:
        res = requests.get(url, headers=headers, timeout=4)
        if res.status_code == 200:
            data = res.json()
            return {"score": round(data['fear_and_greed']['score']), "delta": round(data['fear_and_greed']['score'] - data['fear_and_greed']['previous_close']), "rating": data['fear_and_greed']['rating'].capitalize()}
    except: pass
    
    try:
        vix_df = yf.Ticker("^VIX").history(period="5d")
        if not vix_df.empty and len(vix_df) >= 2:
            vix_val = float(vix_df['Close'].iloc[-1])
            vix_prev = float(vix_df['Close'].iloc[-2])
            syn_score = max(0, min(100, 100 - ((vix_val - 12) / 20) * 100))
            syn_prev = max(0, min(100, 100 - ((vix_prev - 12) / 20) * 100))
            rating = "Extreme Greed" if syn_score >= 75 else "Greed" if syn_score >= 55 else "Neutral" if syn_score >= 45 else "Fear" if syn_score >= 25 else "Extreme Fear"
            return {"score": round(syn_score), "delta": round(syn_score - syn_prev), "rating": f"{rating} (VIX 추정)"}
    except: pass
    return {"score": 50, "delta": 0, "rating": "데이터 수집 불가"}

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
                    except: pass
                try: pct_val = float(re.sub(r'[^\d\.\+\-]', '', pct_str))
                except: pct_val = 0.0
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
        except: ex_rate = 1350.0 
        def get_clean_korean_name(n):
            try:
                res = requests.get(f"https://translate.googleapis.com/translate_a/single?client=gtx&sl=en&tl=ko&dt=t&q={urllib.parse.quote(n)}", timeout=2)
                ko_name = res.json()[0][0][0]
                return re.sub(r'(?i)(,?\s*Inc\.|,?\s*Corp\.|,?\s*Corporation|,?\s*Ltd\.|,?\s*Holdings|\(주\))', '', ko_name).strip()
            except: return n
        df['기업명'] = df['기업명'].apply(get_clean_korean_name)
        df['환산(원)'] = df['현재가'].apply(lambda x: f"{int(float(x.replace(',', '')) * ex_rate):,}원" if x and x.replace('.', '', 1).replace(',', '').isdigit() else "-")
        df['현재가'] = df['현재가'].apply(lambda x: f"${float(x.replace(',', '')):.2f}" if x and x.replace('.', '', 1).replace(',', '').isdigit() else str(x))
        df['등락률'] = df['등락률'].apply(lambda x: f"+{x:.2f}%")
        return df, ex_rate, fetch_time
    except: return empty_df, 1350.0, fetch_time

@st.cache_data(ttl=86400)
def get_krx_stocks():
    try:
        url = 'http://kind.krx.co.kr/corpgeneral/corpList.do?method=download&searchType=13'
        res = requests.get(url, headers={'User-Agent': 'Mozilla/5.0'}, timeout=10)
        df = pd.read_html(StringIO(res.content.decode('euc-kr')), header=0)[0]
        df = df[['회사명', '종목코드', '업종']]
        df.columns = ['Name', 'Code', 'Sector']
        df['Code'] = df['Code'].astype(str).str.zfill(6)
        return df.drop_duplicates(subset=['Name']).reset_index(drop=True)
    except: return pd.DataFrame(columns=['Name', 'Code', 'Sector'])

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
    except: pass
    if df_list: return pd.concat(df_list, ignore_index=True).drop_duplicates(subset=['종목명'])
    return pd.DataFrame()

@st.cache_data(ttl=300)
def get_trading_value_kings():
    try:
        df_fdr = fdr.StockListing('KRX')
        if not df_fdr.empty and 'Amount' in df_fdr.columns:
            mask = df_fdr['Name'].str.contains('KODEX|TIGER|KBSTAR|KOSEF|ARIRANG|HANARO|ACE|스팩|ETN|선물|인버스|레버리지', na=False)
            df_fdr = df_fdr[~mask].copy()
            df_fdr['Amount'] = pd.to_numeric(df_fdr['Amount'].astype(str).str.replace(r'[^\d\.]', '', regex=True), errors='coerce').fillna(0)
            df_fdr['Close'] = pd.to_numeric(df_fdr['Close'].astype(str).str.replace(r'[^\d\.]', '', regex=True), errors='coerce').fillna(0)
            df_fdr['ChagesRatio'] = pd.to_numeric(df_fdr['ChagesRatio'].astype(str).str.replace(r'[^\d\.\-]', '', regex=True), errors='coerce').fillna(0)
            df_fdr = df_fdr.sort_values('Amount', ascending=False).head(20)
            df_fdr['Amount_Ouk'] = (df_fdr['Amount'] / 100000000).astype(int)
            df_fdr['Amount_Ouk'] = df_fdr['Amount_Ouk'].apply(lambda x: x if x > 0 else 1) 
            krx = get_krx_stocks()
            if not krx.empty:
                df_fdr = pd.merge(df_fdr, krx[['Name', 'Sector']], on='Name', how='left')
                df_fdr['Sector'] = df_fdr['Sector'].fillna('기타/분류불가')
            else: df_fdr['Sector'] = '기타/분류불가'
            return df_fdr[['Code', 'Name', 'Close', 'ChagesRatio', 'Amount_Ouk', 'Sector']]
    except: pass
    try:
        df_kpi = fetch_naver_volume(0, 1)
        df_kdq = fetch_naver_volume(1, 1)
        df = pd.concat([df_kpi, df_kdq], ignore_index=True)
        if not df.empty:
            mask = df['종목명'].str.contains('KODEX|TIGER|KBSTAR|KOSEF|ARIRANG|HANARO|ACE|스팩|ETN|선물|인버스|레버리지', na=False)
            df = df[~mask].copy()
            def extract_num(x):
                try: return float(re.sub(r'[^\d\.\-]', '', str(x)))
                except: return 0.0
            df['Name'] = df['종목명']
            df['Close'] = df['현재가'].apply(extract_num)
            df['ChagesRatio'] = df['등락률'].apply(extract_num)
            df['Volume'] = df['거래량'].apply(extract_num)
            df['Amount_Ouk'] = (df['Close'] * df['Volume'] / 100000000).astype(int)
            df['Amount_Ouk'] = df['Amount_Ouk'].apply(lambda x: x if x > 0 else 1) 
            df = df.sort_values('Amount_Ouk', ascending=False).head(20)
            krx = get_krx_stocks()
            if not krx.empty:
                df = pd.merge(df, krx[['Name', 'Code', 'Sector']], on='Name', how='left')
                df['Code'] = df['Code'].fillna('000000')
                df['Sector'] = df['Sector'].fillna('기타/분류불가')
            else:
                df['Code'] = '000000'
                df['Sector'] = '기타/분류불가'
            return df[['Code', 'Name', 'Close', 'ChagesRatio', 'Amount_Ouk', 'Sector']]
    except: pass
    return pd.DataFrame()

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
    except: pass
    try:
        df_kpi = fetch_naver_volume(0, pages=3) 
        df_kdq = fetch_naver_volume(1, pages=3)
        df = pd.concat([df_kpi, df_kdq], ignore_index=True)
        if not df.empty:
            mask = df['종목명'].str.contains('KODEX|TIGER|KBSTAR|KOSEF|ARIRANG|HANARO|ACE|스팩|ETN|선물|인버스|레버리지', na=False)
            df = df[~mask].drop_duplicates(subset=['종목명']).copy()
            def extract_num(x):
                try: return float(re.sub(r'[^\d\.\-]', '', str(x)))
                except: return 0.0
            df['Close'] = df['현재가'].apply(extract_num)
            df['Volume'] = df['거래량'].apply(extract_num)
            df['Amount'] = df['Close'] * df['Volume']
            df = df.sort_values('Amount', ascending=False).head(limit)
            krx = get_krx_stocks()
            if not krx.empty:
                df = pd.merge(df, krx[['Name', 'Code']], left_on='종목명', right_on='Name', how='inner')
                targets = df[['Name', 'Code']].values.tolist()
                if targets: return targets
    except: pass
    try:
        krx = get_krx_stocks()
        if not krx.empty:
            mask = krx['Name'].str.contains('KODEX|TIGER|KBSTAR|KOSEF|ARIRANG|HANARO|ACE|스팩|ETN|선물|인버스|레버리지', na=False)
            krx = krx[~mask].drop_duplicates(subset=['Name'])
            return krx.head(limit)[['Name', 'Code']].values.tolist()
    except: pass
    return []

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
                            except: return 0.0
                        res_df['Close'] = t['현재가'].apply(to_f)
                        res_df['Changes'] = t['전일비'].apply(to_f) if is_upper else -t['전일비'].apply(to_f)
                        res_df['ChagesRatio'] = t['등락률'].apply(to_f) if is_upper else -t['등락률'].apply(to_f)
                        res_df['Amount_Ouk'] = (res_df['Close'] * t['거래량'].apply(to_f) / 100000000).astype(int)
                        res_df['PrevClose'] = res_df['Close'] - res_df['Changes']
                        res_df['Code'] = ""
                        return res_df.drop_duplicates(subset=['Name'])
        except: pass
        return pd.DataFrame()
    upper_df = fetch_naver_limit("https://finance.naver.com/sise/sise_upper.naver", True)
    lower_df = fetch_naver_limit("https://finance.naver.com/sise/sise_lower.naver", False)
    krx = get_krx_stocks()
    if not upper_df.empty and not krx.empty:
        upper_df = pd.merge(upper_df, krx[['Name', 'Code', 'Sector']], on='Name', how='left')
        upper_df['Sector'] = upper_df['Sector'].fillna('개별이슈/기타')
    if not lower_df.empty and not krx.empty:
        lower_df = pd.merge(lower_df, krx[['Name', 'Code', 'Sector']], on='Name', how='left')
        lower_df['Sector'] = lower_df['Sector'].fillna('개별이슈/기타')
    return upper_df.sort_values('Amount_Ouk', ascending=False), lower_df.sort_values('Amount_Ouk', ascending=False)

@st.cache_data(ttl=600)
def get_volume_surge_drop():
    def fetch_vol_table(url):
        try:
            res = requests.get(url, headers={'User-Agent': 'Mozilla/5.0'}, timeout=5)
            tables = pd.read_html(StringIO(res.content.decode('euc-kr', errors='replace')))
            for t in tables:
                if '종목명' in t.columns and '현재가' in t.columns:
                    df = t.dropna(subset=['종목명', '현재가']).copy()
                    df = df[df['종목명'] != '종목명']
                    df = df[~df['종목명'].str.contains('스팩|ETN|선물|인버스|레버리지', na=False, regex=True)]
                    return df.dropna(axis=1, how='all').head(20).reset_index(drop=True)
        except: pass
        return pd.DataFrame()
    surge_df = fetch_vol_table("https://finance.naver.com/sise/sise_quant_high.naver")
    drop_df = fetch_vol_table("https://finance.naver.com/sise/sise_quant_low.naver")
    return surge_df, drop_df

@st.cache_data(ttl=3600)
def get_market_warnings():
    def fetch_warning_table(url):
        try:
            res = requests.get(url, headers={'User-Agent': 'Mozilla/5.0'}, timeout=5)
            tables = pd.read_html(StringIO(res.content.decode('euc-kr', errors='replace')))
            for t in tables:
                if '종목명' in t.columns:
                    df = t.dropna(subset=['종목명']).copy()
                    df = df[df['종목명'] != '종목명']
                    return df.dropna(axis=1, how='all').reset_index(drop=True)
        except: pass
        return pd.DataFrame()
    mgmt_df = fetch_warning_table("https://finance.naver.com/sise/management.naver")
    alert_df = fetch_warning_table("https://finance.naver.com/sise/investment_alert.naver")
    return mgmt_df, alert_df

@st.cache_data(ttl=120)
def get_latest_naver_news():
    articles = []
    ts = int(datetime.now().timestamp())
    def fetch_page(page):
        try:
            url = f"https://finance.naver.com/news/news_list.naver?mode=LSS2D&section_id=101&section_id2=258&page={page}&_ts={ts}"
            res = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=2.5) 
            if res.status_code != 200: return []
            soup = BeautifulSoup(res.content.decode('euc-kr', errors='replace'), 'html.parser')
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
                        pub_time = match.group(2) if match.group(1) == (datetime.utcnow() + timedelta(hours=9)).strftime("%Y-%m-%d") else f"{match.group(1)[5:].replace('-', '/')} {match.group(2)}"
                    else:
                        match_time = re.search(r'(\d{2}:\d{2})', raw_date)
                        if match_time: pub_time = match_time.group(1)
                if not pub_time: pub_time = (datetime.utcnow() + timedelta(hours=9)).strftime("%H:%M")
                page_articles.append({"title": title, "link": link, "time": pub_time})
            return page_articles
        except: return []
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
        results = executor.map(fetch_page, [1, 2])
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
    except: return pd.DataFrame()

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
    except: return None, None, "데이터 스크래핑 오류"

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
    except: return None

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
            except: pass
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
    except: return "조회불가", "조회불가", "조회불가", 0, 0

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
            except: pass
            if count >= 5: break
        return pension_like_sum, pension_like_streak
    except: return 0, 0

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
            except: pass
            if len(data) >= 10: break
        return pd.DataFrame(data)
    except: return pd.DataFrame()

def get_fundamentals(ticker_code):
    if str(ticker_code).isdigit():
        try:
            url = f"https://finance.naver.com/item/main.naver?code={ticker_code}"
            res = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=5)
            soup = BeautifulSoup(res.text, 'html.parser')
            per = soup.select_one('#_per').text if soup.select_one('#_per') else 'N/A'
            pbr = soup.select_one('#_pbr').text if soup.select_one('#_pbr') else 'N/A'
            
            target_price = 'N/A'
            for tr in soup.find_all('tr'):
                th = tr.find('th')
                if th and '목표주가' in th.text:
                    td = tr.find('td')
                    if td:
                        text_content = td.get_text(separator=' ', strip=True)
                        possible_prices = []
                        for n_str in re.findall(r'[0-9,]+', text_content):
                            clean_n = n_str.replace(',', '')
                            if clean_n.isdigit():
                                possible_prices.append(int(clean_n))
                        if possible_prices:
                            max_val = max(possible_prices)
                            if max_val > 10: 
                                target_price = str(max_val)
                    break
            
            return per, pbr, None, None, target_price
        except: return 'N/A', 'N/A', None, None, 'N/A'
    else:
        try:
            t_obj = yf.Ticker(ticker_code)
            info = t_obj.info
            per = round(info.get('trailingPE', 0), 2) if info.get('trailingPE') else 'N/A'
            pbr = round(info.get('priceToBook', 0), 2) if info.get('priceToBook') else 'N/A'
            target_price = info.get('targetMeanPrice', 'N/A')
            fcf = None
            shares = info.get('sharesOutstanding', None)
            
            try:
                cf = t_obj.cash_flow
                if cf is not None and not cf.empty and 'Free Cash Flow' in cf.index:
                    fcf_raw = cf.loc['Free Cash Flow'].iloc[0]
                    if pd.notna(fcf_raw): fcf = fcf_raw
            except: pass
            
            return per, pbr, fcf, shares, target_price
        except: return 'N/A', 'N/A', None, None, 'N/A'

@st.cache_data(ttl=3600)
def get_historical_data(ticker_code, days):
    start_date = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d')
    df = pd.DataFrame()
    if str(ticker_code).isdigit():
        try: df = fdr.DataReader(ticker_code, start_date)
        except: pass
        if df is None or df.empty:
            try:
                df = yf.Ticker(ticker_code + ".KS").history(start=start_date)
                if not df.empty: df.index = df.index.tz_localize(None)
            except: pass
    else:
        try:
            df = yf.Ticker(ticker_code).history(start=start_date)
            if not df.empty: df.index = df.index.tz_localize(None)
        except: pass
        if df is None or df.empty:
            try: df = fdr.DataReader(ticker_code, start_date)
            except: pass
    return df

@st.cache_data(ttl=3600)
def search_us_ticker(query):
    if not query: return []
    if re.search('[가-힣]', query):
        try:
            res = requests.get(f"https://translate.googleapis.com/translate_a/single?client=gtx&sl=ko&tl=en&dt=t&q={urllib.parse.quote(query)}", timeout=2)
            search_term = res.json()[0][0][0]
        except:
            search_term = query
    else:
        search_term = query
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
                exch = quote.get('exchDisp', 'US')
                results.append(f"{sym} ({name} / {exch})")
        return results
    except: return []

@st.cache_data(ttl=3600)
def analyze_technical_pattern(stock_name, ticker_code, offset_days=0):
    if not ticker_code: return None
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
    except: return None

# ==========================================
# 3. UI 렌더링 가이드 및 카드 함수
# ==========================================
def show_beginner_guide():
    with st.expander("🐥 [주린이 필독] 주식 용어 & 매매 타점 완벽 가이드", expanded=False):
        st.markdown("""
        ### 1. 📊 차트 상태 (상세 진단 기준 & 이평선)
        * **이동평균선(이평선):** 일정 기간 동안의 주가 평균을 이은 선입니다. (5일선=1주일, 20일선=1달, 60일선=3달)
        * **🔥 완벽 정배열 (상승 추세):** `5일선 > 20일선 > 60일선` 순서로 주가 아래에 예쁘게 깔려 있는 가장 이상적인 상승 구간입니다.
        * **❄️ 역배열 (하락 추세):** `5일선 < 20일선 < 60일선` 순서로 주가 위에서 짓누르고 있는 하락 구간입니다.
        * **✨ 5-20 골든크로스:** 어제까지 아래에 있던 단기선(5일)이 중기선(20일)을 **오늘 뚫고 위로 올라온** 긍정적 턴어라운드 신호입니다.
        * **🌀 혼조세/횡보:** 위 조건들에 해당하지 않고 선들이 뒤엉켜 방향을 탐색하는 박스권 상태입니다.
        """)

def show_trading_guidelines():
    with st.expander("🎯 [필독] Jaemini PRO 실전 매매 4STEP 시나리오 (단기 스윙 전략)", expanded=True):
        st.markdown("""
        *💡 본 시나리오는 장중 계속 호가창만 볼 수 없는 환경에 최적화된 **'단기 스윙(며칠~1, 2주 보유)'** 전략입니다. 스캐너로 타점을 찾아 미리 지정가로 매수/매도/손절을 걸어두고 기계적으로 대응하십시오.*
        **1️⃣ 숲을 본다 (09:00~09:30) : 주도 테마 선점**
        * **시장 자금 히트맵**을 통해 오늘 돈이 몰리는 주도 섹터 파악
        **2️⃣ 나무를 고른다 (09:30~) : 스캐너 황금 콤보 적용 및 보유 기간**
        * 🅰️ **안전 스윙 (목표 3일~2주):** `✅20일선 눌림목` + `🔥거래량 급증` 
        * 🅱️ **추세 탑승 (목표 1일~5일):** `✨정배열 초입` + `🔥거래량 급증` 
        * ©️ **바닥 줍줍 (목표 1일~3일):** `🔵RSI 30이하` + `🔥거래량 급증` 
        * 🐋 **스마트머니 편승 (목표 3일~1주):** `[✅ 눌림목]` + `[👴 연기금 3일 연속 순매수]`
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
    p_trend = get_short_trend(tech_result.get('개인수급', '0'))
    sector_info = tech_result.get('섹터', '기타')
    if len(sector_info) > 12: sector_info = sector_info[:12] + ".."
    align_status_short = tech_result['배열상태'].split(' ｜ ')[0]
    
    def fmt_price(p, delta=False):
        if is_us:
            if delta: return f"{'+' if p>0 else ''}${p:,.2f}"
            return f"${p:,.2f}"
        else:
            if delta: return f"{'+' if p>0 else ''}{int(p):,}원"
            return f"{int(p):,}원"
            
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
                <p style="margin:5px 0 0 0; font-size: 16px;">스캔 당시 가격 <b>{fmt_price(tech_result['현재가'])}</b> ➡️ 오늘 현재 가격 <b>{fmt_price(tech_result['오늘현재가'])}</b> <span style="font-size: 20px; font-weight: bold; color: {color};">({pnl:+.2f}%)</span></p>
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
            except: return False
            
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
                    st.markdown(f"👴 **스마트머니 시그널:** <span style='color:orange; font-weight:bold;'>🔥 기관(연기금 추정) {tech_result['연기금연속순매수']}일 연속 순매수 포착</span>", unsafe_allow_html=True)
        else:
            with c8:
                per_val = tech_result.get('PER', 'N/A')
                pbr_val = tech_result.get('PBR', 'N/A')
                st.markdown(f"🏢 **핵심 펀더멘털 (TTM)**<br>**PER:** `{per_val}` ｜ **PBR:** `{pbr_val}`", unsafe_allow_html=True)
        
        if api_key_str:
            st.markdown("<br>", unsafe_allow_html=True)
            ai_btn_key = f"ai_btn_{tech_result['티커']}_{key_suffix}"
            ai_res_key = f"ai_res_{ai_btn_key}"
            
            if st.button(f"🤖 '{tech_result['종목명']}' AI 딥다이브 정밀 분석 (차트+재무+컨센서스)", key=ai_btn_key):
                st.session_state[ai_res_key] = "loading"
                
            if st.session_state.get(ai_res_key):
                if st.session_state[ai_res_key] == "loading":
                    with st.spinner("AI가 차트, 수급, 재무제표 및 컨센서스를 종합 분석 중입니다... (약 5~10초 소요)"):
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
                            
                st.success("✅ AI 정밀 분석 완료!")
                st.markdown(st.session_state[ai_res_key])
                
                if not is_us:
                    with st.expander(f"📊 '{tech_result['종목명']}' 수집된 로우 데이터 (Raw Data) 확인"):
                        fin_df, peer_df, cons = get_financial_deep_data(tech_result['티커'])
                        st.write("✅ **증권사 목표가 컨센서스:**", cons)
                        if fin_df is not None: st.dataframe(fin_df)
                        if peer_df is not None: st.dataframe(peer_df)
        
        tf = st.radio("📅 차트 기간 선택", ["1개월", "3개월", "1년"], horizontal=True, key=f"tf_{key_suffix}", index=0)
        days_dict = {"1개월": 30, "3개월": 90, "1년": 365}
        with st.spinner(f"{tf} 차트 데이터 불러오는 중..."):
            long_df = get_historical_data(tech_result['티커'], days_dict[tf])
            if not long_df.empty:
                long_df = long_df.reset_index()
                long_df['OBV'] = (np.sign(long_df['Close'].diff()) * long_df['Volume']).fillna(0).cumsum()
                long_df['MA20'] = long_df['Close'].rolling(window=20).mean()
                long_df['Std_20'] = long_df['Close'].rolling(window=20).std()
                long_df['Bollinger_Upper'] = long_df['MA20'] + (long_df['Std_20'] * 2)
                
                x_col, x_type = ('Date_Str', 'category') if tf in ["1개월", "3개월"] else ('Date', 'date')
                if tf in ["1개월", "3개월"]: long_df['Date_Str'] = long_df['Date'].dt.strftime('%m월 %d일')
                
                ch1, ch2 = st.columns(2)
                with ch1:
                    fig_price = go.Figure(data=[go.Candlestick(x=long_df[x_col], open=long_df['Open'], high=long_df['High'], low=long_df['Low'], close=long_df['Close'], increasing_line_color='#ff4b4b', decreasing_line_color='#1f77b4', name="주가")])
                    fig_price.add_trace(go.Scatter(x=long_df[x_col], y=long_df['MA20'], mode='lines', line=dict(color='orange', width=1.5), name='20일선'))
                    fig_price.add_trace(go.Scatter(x=long_df[x_col], y=long_df['Bollinger_Upper'], mode='lines', line=dict(color='gray', width=1, dash='dot'), name='볼밴상단'))
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
                        today_date = datetime.now().strftime('%Y.%m.%d')
                        if daily_df.iloc[0]['날짜'] not in [today_date, f"{today_date} (잠정)"] and not daily_df.iloc[0]['날짜'].startswith(today_date):
                            try:
                                prev_close = int(daily_df.iloc[0]['종가'].replace(',', ''))
                                curr_price = int(tech_result['현재가'])
                                diff = curr_price - prev_close
                                diff_str = f"상승 {diff:,}" if diff > 0 else f"하락 {abs(diff):,}" if diff < 0 else "보합 0"
                                pct_str = f"{'+' if diff > 0 else ''}{(diff / prev_close) * 100:.2f}%"
                            except:
                                diff_str, pct_str = "-", "-"
                                
                            est = tech_result.get('장중잠정수급')
                            if est:
                                def fmt_v(v):
                                    if v > 0: return f"🔴 +{v:,}"
                                    elif v < 0: return f"🔵 {v:,}"
                                    return "0"
                                f_val = fmt_v(est['forgn'])
                                i_val = fmt_v(est['inst'])
                                r_val = fmt_v(-(est['forgn'] + est['inst']))
                                date_str = f"{today_date} ({est['time']} 잠정)"
                            else:
                                f_val, i_val, r_val = "집계중", "집계중", "집계중"
                                date_str = f"{today_date} (장마감 집계중)"
                                
                            new_row = pd.DataFrame([{
                                "날짜": date_str, "종가": f"{int(curr_price):,}", "전일비": diff_str, "등락률": pct_str,
                                "외국인": f_val, "기관": i_val, "개인(추정)": r_val
                            }])
                            daily_df = pd.concat([new_row, daily_df], ignore_index=True)
                            
                        st.dataframe(daily_df, use_container_width=True, hide_index=True)
                    else: st.caption("수급 데이터를 제공하지 않는 종목입니다.")
            else: st.error("데이터를 불러오지 못했습니다.")

def display_sorted_results(results_list, tab_key, api_key=""):
    if not results_list:
        st.info("조건에 부합하는 종목이 없습니다.")
        return
    st.success(f"🎯 총 {len(results_list)}개 종목 포착 완료!")
    sort_opt = st.radio("⬇️ 결과 정렬 방식", ["기본 (검색순)", "RSI 낮은순 (바닥줍기)", "연기금 순매수 긴 순서"], horizontal=True, key=f"sort_radio_{tab_key}")
    display_list = results_list.copy()
    
    if "RSI 낮은순" in sort_opt: sorted_res = sorted(display_list, key=lambda x: x['RSI'])
    elif "연기금 순매수 긴 순서" in sort_opt: sorted_res = sorted(display_list, key=lambda x: x.get('연기금연속순매수', 0), reverse=True)
    else: sorted_res = display_list

    for i, res in enumerate(sorted_res):
        draw_stock_card(res, api_key_str=api_key, is_expanded=False, key_suffix=f"{tab_key}_{i}")

# ==========================================
# 4. 메인 화면 & 사이드바 메뉴 
# ==========================================
with st.sidebar:
    st.title("📈 Jaemini PRO v5.7")
    st.markdown("풀옵션 단기 스윙 & 스마트머니 추적 시스템")
    st.divider()
    
    menu_list = [
        "🎛️ 메인 대시보드",
        "👨‍🦳 연기금 그림자 매매 스캐너", 
        "🗺️ 시장 자금 & 스마트머니 히트맵", 
        "🕸️ 실시간 3D 순환매 맵",
        "🏛️ DART: 국민연금 코어픽 5%", 
        "🚀 실시간 퀀트 스캐너 & 백테스팅",
        "🔥 🇺🇸 미국 급등주",
        "💎 장기 가치주 스캐너", 
        "🔬 기업 정밀 분석기", 
        "⚡ 메가트렌드 & 테마 발굴기", 
        "🚨 상/하한가 분석", 
        "🚦 거래량 급증 & 시장경보",
        "📰 실시간 속보/리포트", 
        "📅 IPO / 증시 일정", 
        "💰 배당 파이프라인 (TOP 300)", 
        "📊 글로벌 ETF 분석", 
        "⭐ 내 관심종목",
        "⚖️ 워런 버핏 퀀트 계산기",
        "🧪 v5.0 AI 포트폴리오 랩"
    ]
    
    if "main_menu_radio" not in st.session_state:
        st.session_state.main_menu_radio = "🎛️ 메인 대시보드"
        
    selected_menu = st.radio("📌 메뉴 이동", menu_list, key="main_menu_radio")
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
# 5. 각 탭별 실행 내용
# ==========================================

# 데이터 로딩 지연 방지용 (필요시에만 호출)
if selected_menu in ["🔥 🇺🇸 미국 급등주", "🎛️ 메인 대시보드", "🧪 v5.0 AI 포트폴리오 랩"]:
    if "gainers_df" not in st.session_state or '환산(원)' not in st.session_state.gainers_df.columns:
        df, ex_rate, fetch_time = get_us_top_gainers()
        st.session_state.gainers_df = df
        st.session_state.ex_rate = ex_rate
        st.session_state.us_fetch_time = fetch_time

if selected_menu == "🎛️ 메인 대시보드":
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
                            st.markdown(f"**현재가:** {res['현재가']:,}원 ｜ **상태:** {res['상태']} ｜ **RSI:** {res['RSI']:.1f}")
                            st.markdown(f"**진입가:** {res['진입가_가이드']:,}원 ｜ **손절가:** {res['손절가']:,}원")
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
                    if res['현재가'] <= res['손절가']: st.error(f"🔴 **손절가 이탈 위험:** {item['종목명']} (현재: {res['현재가']:,}원 / 손절선: {res['손절가']:,}원)")
                    elif res['현재가'] >= res['목표가1'] * 0.98: st.success(f"🟢 **익절 구간 도달:** {item['종목명']} (현재: {res['현재가']:,}원 / 1차목표: {res['목표가1']:,}원)")
                    else: st.warning(f"🟡 **홀딩 대기중:** {item['종목명']} (현재: {res['현재가']:,}원)")

    st.divider()
    st.subheader("💬 실시간 퀀트 챗봇 (Interactive RAG)")
    st.write("장중 궁금한 시장 이슈나 내 관심종목의 상태를 퀀트 비서에게 직접 물어보세요.")
    
    chat_container = st.container(height=400)
    for msg in st.session_state.v4_chat_history:
        chat_container.chat_message(msg["role"]).write(msg["content"])
        
    if prompt := st.chat_input("예: 오늘 삼성전자 수급 동향과 차트 상태를 요약해줘.", key="main_chat"):
        st.session_state.v4_chat_history.append({"role": "user", "content": prompt})
        chat_container.chat_message("user").write(prompt)
        
        if not api_key_input:
            st.error("좌측 사이드바에 API 키를 입력해주세요.")
        else:
            with chat_container.chat_message("assistant"):
                with st.spinner("전문가 모드로 답변을 생성 중입니다..."):
                    today_str = datetime.now().strftime("%Y년 %m월 %d일")
                    macro_context = ""
                    if macro_data:
                        macro_context = "현재 거시경제: " + ", ".join([f"{k} {v['value']}" for k, v in macro_data.items()])
                        
                    sys_prompt = f"""
                    당신은 사용자의 실전 트레이딩을 돕는 여의도 최고의 퀀트 비서입니다.
                    🚨 아주 중요: 오늘은 정확히 {today_str}입니다! 현재 연도는 2026년입니다. 절대 과거 연도를 현재인 것처럼 말하지 마세요.
                    [매크로 데이터]: {macro_context}
                    [주의사항] 당신은 현재 실시간 개별 종목 주가 검색 권한이 없습니다! 사용자가 특정 종목의 현재가나 목표가를 물어보면, 절대 임의의 숫자를 지어내지(환각) 말고 "정확한 실시간 주가와 목표가는 좌측의 '🔬 기업 정밀 분석기' 메뉴를 이용해 주세요"라고 안내하세요.
                    사용자의 질문에 명확하고 날카롭게 답변하세요. 불필요한 서론은 빼고 핵심만 전달하세요.
                    사용자 질문: {prompt}
                    """
                    reply = ask_gemini(sys_prompt, api_key_input)
                    st.write(reply)
                    st.session_state.v4_chat_history.append({"role": "assistant", "content": reply})

elif selected_menu == "👨‍🦳 연기금 그림자 매매 스캐너":
    st.markdown("## 👨‍🦳 연기금 그림자 매매 스캐너 (Smart Money Tracker)")
    show_trading_guidelines()
    
    col_c1, col_c2 = st.columns(2)
    with col_c1:
        pension_streak_cond = st.slider("최소 기관(연기금 추정) 연속 순매수 일수", min_value=1, max_value=5, value=3)
    with col_c2:
        pension_pullback_cond = st.checkbox("✅ 20일선 눌림목 근접 종목만 보기", value=True)
        
    scan_limit = st.selectbox("스캔할 거래대금 상위 종목 수", [50, 100, 200], index=1)
    
    if st.button("🚀 연기금 수급 종목 스캔 시작", type="primary", use_container_width=True):
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
                
    if st.session_state.pension_scan_results is not None: 
        display_sorted_results(st.session_state.pension_scan_results, tab_key="pension", api_key=api_key_input)

elif selected_menu == "🗺️ 시장 자금 & 스마트머니 히트맵":
    st.subheader("🗺️ 시장 주도주 & 스마트머니 유입 섹터 히트맵")
    st.write("거래대금이 터진 종목들 중 기관 매수세가 동반된 종목을 파악합니다. (녹색: 상승 / 붉은색: 하락)")
    
    with st.spinner("거래대금 상위 30종목 데이터 및 수급 스크래핑 중..."):
        t_kings = get_trading_value_kings()
        if not t_kings.empty:
            t_kings = t_kings.head(30)
            pension_streaks = []
            
            for idx, row in t_kings.iterrows():
                _, streak = get_pension_fund_trend(row['Code'])
                pension_streaks.append(streak)
            
            t_kings['연속매수'] = pension_streaks
            t_kings['수급상태'] = t_kings['연속매수'].apply(lambda x: "🔥기관 매집중" if x >= 2 else "일반거래")
            t_kings['display_text'] = "<span style='font-size:16px; font-weight:bold;'>" + t_kings['Name'] + "</span><br>" + t_kings['ChagesRatio'].map("{:+.2f}%".format) + "<br>" + t_kings['수급상태']
            
            fig = px.treemap(
                t_kings, 
                path=[px.Constant("🔥 주도 섹터 (수급 동반)"), 'Sector', 'Name'], 
                values='Amount_Ouk', 
                color='ChagesRatio', 
                color_continuous_scale=[(0.0, '#f63538'), (0.5, '#414554'), (1.0, '#30cc5a')], 
                color_continuous_midpoint=0,
                custom_data=['ChagesRatio', 'Amount_Ouk', 'display_text', '연속매수']
            )
            fig.update_traces(textinfo="text", texttemplate="%{customdata[2]}", hovertemplate="<b>%{label}</b><br>등락률: %{customdata[0]:+.2f}%<br>거래대금: %{customdata[1]:,}억<br>연속매수: %{customdata[3]}일")
            fig.update_layout(margin=dict(t=30, l=10, r=10, b=10), height=600)
            st.plotly_chart(fig, use_container_width=True)
            
            st.markdown("### 📊 수급 동반 거래대금 상위 종목 타점 확인")
            sel_king = st.selectbox("타점 확인:", ["선택"] + t_kings[t_kings['연속매수'] >= 1]['Name'].tolist())
            if sel_king != "선택":
                k_code = t_kings[t_kings['Name'] == sel_king]['Code'].iloc[0]
                if res := analyze_technical_pattern(sel_king, k_code): draw_stock_card(res, api_key_str=api_key_input, is_expanded=True)

elif selected_menu == "🕸️ 실시간 3D 순환매 맵":
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
        
        sum_in = sum(v_in)
        sum_out = sum(v_out)
        if sum_in > 0 and sum_out > 0:
            v_out_adjusted = [x * (sum_in / sum_out) for x in v_out]
        else:
            v_out_adjusted = v_out
            
        values = v_in + v_out_adjusted
        
        fig_sk = go.Figure(data=[go.Sankey(
            node = dict(
                pad = 35, 
                thickness = 30,
                line = dict(color = "black", width = 1.0),
                label = nodes,
                color = colors
            ),
            link = dict(
                source = sources,
                target = targets,
                value = values,
                color = "rgba(200, 200, 200, 0.4)" 
            )
        )])
        
        fig_sk.update_traces(textfont=dict(size=14, color="black", family="Arial Black"))
        fig_sk.update_layout(
            title_text=f"최근 {period_sk} 주도 테마 순환매 흐름 ({datetime.now().strftime('%Y.%m.%d')} 기준)", 
            height=600
        )
        
        st.plotly_chart(fig_sk, use_container_width=True)
        
        st.info(f"💡 **실시간 데이터 분석:** 최근 {period_sk} 동안 **[{', '.join(losers['테마'].tolist())}]** 섹터에서 차익 실현된 자금이 유출되어, **[{', '.join(winners['테마'].tolist())}]** 섹터의 상승을 주도하고 있는 것으로 추정됩니다.")
    else:
        st.error("테마별 시장 데이터를 불러오지 못했습니다.")

elif selected_menu == "🏛️ DART: 국민연금 코어픽 5%":
    st.markdown("## 🏛️ DART 공시 연동: 국민연금 코어 픽(Core Pick)")
    nps_df = get_nps_holdings_mock()
    
    tab_nps1, tab_nps2 = st.tabs(["📋 국민연금 5% 대량보유 현황", "🌟 황금 콤보 스캐너 (장기 가치 + 단기 수급)"])
    
    with tab_nps1:
        st.write("*(참고: 이 데이터는 DART Open API 연동을 위한 Mock 데이터 프레임워크입니다.)*")
        st.dataframe(nps_df, use_container_width=True, hide_index=True)
        
    with tab_nps2:
        st.markdown("### 🌟 황금 콤보 전략")
        st.write("**`[조건]`** 국민연금이 5% 이상 보유하여 **기본적인 펀더멘털이 검증된 종목** 중, 최근 시장에서 **기관이 다시 3일 이상 순매수를 시작**하며 단기 모멘텀이 붙기 시작한 종목을 스캔합니다.")
        
        if st.button("🚀 황금 콤보 교차 스캔 시작", type="primary"):
            with st.spinner("수급 패턴 교차 분석 중..."):
                combo_results = []
                progress_bar2 = st.progress(0)
                completed2, total2 = 0, len(nps_df)
                
                for idx, row in nps_df.iterrows():
                    res = analyze_technical_pattern(row['종목명'], row['티커'])
                    if res and res.get('연기금연속순매수', 0) >= 2: 
                        res['NPS_비중'] = row['보유비중']
                        combo_results.append(res)
                    completed2 += 1
                    progress_bar2.progress(completed2 / total2)
                    
                if combo_results:
                    st.success(f"🎯 펀더멘털과 수급이 완벽하게 일치하는 황금 콤보 {len(combo_results)}개 종목 포착!")
                    for i, res in enumerate(combo_results):
                        st.markdown(f"#### 🏆 국민연금 비중: {res['NPS_비중']}")
                        draw_stock_card(res, api_key_str=api_key_input, is_expanded=True, key_suffix=f"combo_{i}")
                else:
                    st.warning("현재 황금 콤보 조건에 부합하는 종목이 없습니다.")

elif selected_menu == "🚀 실시간 퀀트 스캐너 & 백테스팅":
    st.markdown("## 🚀 실시간 조건 검색 및 1년 백테스팅 시뮬레이터")
    
    scan_tab, backtest_tab = st.tabs(["🚀 실시간 조건 검색 스캐너", "🧪 1년 전략 백테스팅"])
    
    with scan_tab:
        show_beginner_guide()
        show_trading_guidelines()
        
        col_c1, col_c2, col_c3, col_c4 = st.columns(4)
        with col_c1: cond_golden = st.checkbox("✨ 골든크로스 / 정배열 초입"); cond_pullback = st.checkbox("✅ 20일선 눌림목 (타점 근접)", value=True)
        with col_c2: cond_rsi_bottom = st.checkbox("🔵 RSI 30 이하 (낙폭과대)"); cond_vol_spike = st.checkbox("🔥 최근 거래량 급증 (세력 의심)")
        with col_c3: cond_twin_buy = st.checkbox("🐋 외인/기관 쌍끌이 순매수")
        with col_c4: cond_pension = st.checkbox("👴 연기금 3일 연속 순매수")
        
        scan_limit = st.selectbox("스캔할 상위 종목 수", [50, 100, 200, 300], index=1)
        
        if st.button("🚀 쾌속 병렬 스캔 시작", type="primary", use_container_width=True):
            with st.spinner(f"⚡ {scan_limit}개 종목 고속 필터링 중..."):
                targets = get_scan_targets(scan_limit)
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
        st.write("과거 1년 데이터를 기반으로 '5일-20일 이평선 골든크로스 매수, 데드크로스 매도' 시의 실제 수익률을 검증합니다.")
        
        market_choice_bt = st.radio("시장 선택 (백테스트)", ["🇰🇷 국내 주식", "🇺🇸 미국 주식"], horizontal=True, label_visibility="collapsed")
        
        t_code = None
        if market_choice_bt == "🇰🇷 국내 주식":
            krx_df = get_krx_stocks()
            opts = ["🔍 테스트할 종목 검색"] + (krx_df['Name'].astype(str) + " (" + krx_df['Code'].astype(str) + ")").tolist() if not krx_df.empty else ["005930"]
            test_query = st.selectbox("백테스트 종목:", opts)
            if test_query != "🔍 테스트할 종목 검색":
                t_code = test_query.rsplit("(", 1)[-1].replace(")", "").strip() if "(" in test_query else "005930"
        else:
            us_bt_query = st.text_input("🔍 미국 주식 종목명(한/영) 또는 티커 (예: 애플, TSLA)")
            if us_bt_query:
                with st.spinner("야후 파이낸스 검색 중..."):
                    us_bt_results = search_us_ticker(us_bt_query)
                if us_bt_results:
                    sel_us_bt = st.selectbox("🎯 정확한 종목 선택:", ["선택하세요"] + us_bt_results)
                    if sel_us_bt != "선택하세요":
                        t_code = sel_us_bt.split(" ")[0]
                else:
                    st.error("검색 결과가 없습니다.")
        
        if t_code and st.button("▶️ 시뮬레이션 돌리기", type="primary"):
            with st.spinner("과거 1년 데이터 백테스팅 중..."):
                bt_df = get_historical_data(t_code, 365)
                if not bt_df.empty:
                    bt_df['MA5'] = bt_df['Close'].rolling(5).mean()
                    bt_df['MA20'] = bt_df['Close'].rolling(20).mean()
                    
                    bt_df['Signal'] = 0
                    bt_df.loc[bt_df['MA5'] > bt_df['MA20'], 'Signal'] = 1
                    bt_df['Position'] = bt_df['Signal'].shift(1).fillna(0)
                    bt_df['Daily_Return'] = bt_df['Close'].pct_change()
                    bt_df['Strategy_Return'] = bt_df['Position'] * bt_df['Daily_Return']
                    
                    bt_df['Cumulative_Market'] = (1 + bt_df['Daily_Return']).cumprod()
                    bt_df['Cumulative_Strategy'] = (1 + bt_df['Strategy_Return']).cumprod()
                    
                    fig = go.Figure()
                    x_axis = bt_df.index
                    fig.add_trace(go.Scatter(x=x_axis, y=bt_df['Cumulative_Market'], name="단순 보유 (Buy & Hold)", line=dict(color='gray')))
                    fig.add_trace(go.Scatter(x=x_axis, y=bt_df['Cumulative_Strategy'], name="골든크로스 전략", line=dict(color='#ff4b4b', width=2)))
                    fig.update_layout(title="전략 누적 수익률 비교", height=400)
                    
                    st.plotly_chart(fig, use_container_width=True)
                    
                    final_market = (bt_df['Cumulative_Market'].iloc[-1] - 1) * 100
                    final_strat = (bt_df['Cumulative_Strategy'].iloc[-1] - 1) * 100
                    
                    c1, c2 = st.columns(2)
                    c1.metric("단순 보유 시 수익률", f"{final_market:.2f}%")
                    c2.metric("골든크로스 전략 적용 수익률", f"{final_strat:.2f}%", f"{final_strat - final_market:.2f}%p 대비")
                else:
                    st.error("❌ 데이터를 가져오지 못했습니다. (API 제한 또는 지원하지 않는 티커)")

elif selected_menu == "🔥 🇺🇸 미국 급등주":
    st.markdown("## 🔥 오버나이트 모멘텀 & 밸류체인 스캐너")
    st.write("미국발 훈풍이 한국 증시에 미치는 파급력을 분석합니다. (노이즈 제거, 핵심 섹터 및 공급망 추적, 장초반 갭상승 대응 시나리오)")

    col_sec, col_gain = st.columns([1, 1.2], gap="large")

    with col_sec:
        st.subheader("📊 1. 미 증시 주도 섹터 (ETF)")
        st.caption("간밤에 미국 시장에서 돈이 몰린 핵심 섹터입니다.")
        with st.spinner("섹터 ETF 등락률 산출 중..."):
            etf_df = get_us_sector_etfs()
            if not etf_df.empty:
                etf_df['등락률'] = etf_df['등락률'].apply(lambda x: f"{'+' if x>0 else ''}{x:.2f}%")
                st.dataframe(etf_df, use_container_width=True, hide_index=True)

        st.subheader("🚀 2. 글로벌 급등주 필터링")
        st.caption("간밤에 급등한 미국주식 목록입니다. 밸류체인 분석을 원하는 종목을 선택하세요.")
        if not st.session_state.gainers_df.empty:
            display_df = st.session_state.gainers_df[['종목코드', '기업명', '현재가', '등락률']].copy()
            st.dataframe(display_df, use_container_width=True, hide_index=True)
            
            opts = ["🔍 종목 선택"] + [f"{r['종목코드']} ({r['기업명']})" for _, r in display_df.iterrows()]
            sel_opt = st.selectbox("#### 🎯 분석할 주도주 선택", opts)
            sel_tick = "N/A" if sel_opt == "🔍 종목 선택" else sel_opt.split(" ")[0]
        else:
            sel_tick = "N/A"
            st.error("❌ 현재 급등주 데이터를 불러올 수 없습니다. 야후 파이낸스 서버 오류일 수 있습니다.")

    with col_gain:
        st.subheader("🔗 3. 글로벌 밸류체인 & 갭상승 대응 시나리오")
        if sel_tick != "N/A" and api_key_input:
            comp_name = sel_opt.split(" (")[1].replace(")", "")
            
            with st.spinner(f"✨ AI가 '{sel_tick}'의 공급망과 국장 수혜주를 입체적으로 분석 중입니다..."):
                prompt = f"""
                당신은 월스트리트와 여의도를 넘나드는 최고의 글로벌 매크로/퀀트 애널리스트입니다.
                간밤에 미국 증시에서 '{comp_name}({sel_tick})' 종목이 급등했습니다.
                다음 4가지 관점에서 한국장 시초가 대응 리포트를 마크다운으로 작성해주세요.

                1. 🏢 **급등 사유 & 모멘텀**: 이 기업이 왜 올랐는지 핵심만 2줄 요약. (시총이 너무 작은 잡주/바이오 임상 테마 등 국장 영향력이 없다고 판단되면 단호하게 "한국 증시 파급력 없음"이라고 명시할 거)
                2. 🕸️ **글로벌 밸류체인 매핑**: 이 기업의 사업 모델과 직접적으로 연결되는 한국 코스피/코스닥의 핵심 수혜주 3~5개 및 그 이유 (예: A사 - 카메라 모듈 공급, B사 - 관련 장비 독점).
                3. 📈 **섹터 파급력**: 오늘 한국 증시에서 어떤 테마에 돈이 몰릴지 전망.
                4. ⏰ **장초반 갭상승 대응 시나리오**: 추천한 국장 수혜주들이 시가에 갭을 크게 띄울 경우, 추격 매수해야 할지, 아니면 시가 고점(음봉)을 주의하고 눌림목을 기다려야 할지 구체적인 트레이딩 전략 제시.
                """
                report = ask_gemini(prompt, api_key_input)
                st.success("✅ 밸류체인 및 대응 시나리오 분석 완료!")
                st.markdown(report)
                
            st.divider()
            st.subheader("🎯 추천된 국장 수혜주 타점 즉시 확인")
            st.write("위 리포트에서 언급된 종목의 현재 타점이 궁금하다면 아래에서 바로 검색하세요.")
            krx_df = get_krx_stocks()
            if not krx_df.empty:
                opts_krx = ["🔍 종목명 검색 후 엔터"] + (krx_df['Name'].astype(str) + " (" + krx_df['Code'].astype(str) + ")").tolist()
                us_sub_query = st.selectbox("수혜주 차트 상태 확인:", opts_krx, key="us_sub_scan")
                if us_sub_query != "🔍 종목명 검색 후 엔터":
                    q_name = us_sub_query.rsplit(" (", 1)[0]
                    q_code = us_sub_query.rsplit("(", 1)[-1].replace(")", "").strip()
                    with st.spinner("차트 타점 분석 중..."):
                        res = analyze_technical_pattern(q_name, q_code)
                        if res: draw_stock_card(res, api_key_str=api_key_input, is_expanded=True, key_suffix="us_val_chain")
                        else: st.error("❌ 해당 종목 데이터를 불러올 수 없습니다.")

elif selected_menu == "💎 장기 가치주 스캐너":
    st.markdown("## 💎 여의도 데스크: 기관급 가치주/성장주 스캐너")
    st.write("단순 테마가 아닌 실제 재무제표와 기업 가치를 분석하는 펀드매니저용 조건 검색기입니다.")
    
    col_v1, col_v2 = st.columns([2, 1])
    with col_v1:
        expert_strategy = st.selectbox("🧠 펀드매니저 투자 전략 선택:", [
            "👑 벤저민 그레이엄형 (안전마진 + 딥밸류: 초저PER & PBR)",
            "📈 피터 린치형 (GARP: 합리적 가격의 우량 성장주)",
            "🏰 워런 버핏형 (경제적 해자 + 독점력 + 높은 ROE)",
            "🔄 턴어라운드 & 배당 (실적 바닥 탈출 또는 고배당 방어주)"
        ])
    with col_v2: 
        cap_size = st.selectbox("🏢 기업 규모 선택:", ["대/중/소형 상관없음", "코스피 대형우량주만", "코스닥 중소형 숨은진주"], index=0)
        
    if "그레이엄" in expert_strategy:
        max_per, max_pbr = 10.0, 1.0
    elif "피터 린치" in expert_strategy:
        max_per, max_pbr = 20.0, 3.0
    elif "워런 버핏" in expert_strategy:
        max_per, max_pbr = 30.0, 5.0
    else:
        max_per, max_pbr = 999.0, 3.0
        
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
                        except: pass
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

elif selected_menu == "🔬 기업 정밀 분석기":
    st.markdown("## 🔬 기업 정밀 분석기 (차트/수급/비전 AI)")
    
    ana_tab1, ana_tab2 = st.tabs(["📊 티커 검색 분석", "👁️ 차트 이미지 AI 비전 분석"])
    
    with ana_tab1:
        market_choice = st.radio("시장 선택", ["🇰🇷 국내 주식", "🇺🇸 미국 주식"], horizontal=True)
        
        if market_choice == "🇰🇷 국내 주식":
            krx_df = get_krx_stocks()
            if not krx_df.empty:
                opts = ["🔍 분석할 국내 종목을 입력하세요."] + (krx_df['Name'].astype(str) + " (" + krx_df['Code'].astype(str) + ")").tolist()
                query = st.selectbox("👇 종목명 또는 초성을 입력하여 검색하세요:", opts)
                if query != "🔍 분석할 국내 종목을 입력하세요.":
                    searched_name = query.rsplit(" (", 1)[0]
                    searched_code = query.rsplit("(", 1)[-1].replace(")", "").strip()
                    with st.spinner(f"📡 '{searched_name}' 타점 분석 중..."):
                        res = analyze_technical_pattern(searched_name, searched_code)
                    if res: draw_stock_card(res, api_key_str=api_key_input, is_expanded=True, key_suffix="t4_kr")
                    else: st.error("❌ 분석할 수 없는 종목입니다.")
        else:
            us_query = st.text_input("👇 미국 주식 종목명(한글/영문) 또는 티커를 입력하세요 (예: 테슬라, Microsoft, AAPL):")
            if us_query:
                with st.spinner(f"📡 '{us_query}' 글로벌 종목 검색 중..."):
                    us_results = search_us_ticker(us_query)
                    
                if us_results:
                    sel_us_opt = st.selectbox("🎯 정확한 종목을 선택해주세요:", ["선택하세요"] + us_results, key="us_deep_search")
                    if sel_us_opt != "선택하세요":
                        us_ticker = sel_us_opt.split(" ")[0]
                        with st.spinner(f"📡 '{us_ticker}' 타점 및 재무 분석 중..."):
                            res = analyze_technical_pattern(us_ticker, us_ticker)
                        if res: draw_stock_card(res, api_key_str=api_key_input, is_expanded=True, key_suffix="t4_us")
                        else: st.error("❌ 해당 티커의 데이터를 찾을 수 없거나 아직 지원되지 않는 종목입니다.")
                else:
                    st.error("❌ 해당 키워드로 미국 주식을 찾을 수 없습니다.")

    with ana_tab2:
        st.markdown("### 👁️ AI Vision: 인간의 눈으로 보는 차트 분석")
        
        st.warning("⚠️ **[브라우저 보안 안내]** 크롬, 웨일, 엣지 등 최신 브라우저는 보안상 웹페이지 빈 공간에서의 'Ctrl+V(붙여넣기)'를 차단합니다.")
        st.info("💡 **가장 확실하게 이미지를 넣는 2가지 방법:**\n1. 아래 **[Drag and drop file here]** 회색 점선 박스 정중앙을 마우스로 **정확히 1번 클릭**한 뒤 `Ctrl+V`를 누르세요.\n2. 차트 위에서 우클릭 후 **'이미지 주소 복사'**를 하여 우측 텍스트 칸에 `Ctrl+V` 하시는 것이 가장 빠르고 오류가 없습니다.")
        
        upload_col, url_col = st.columns(2)
        with upload_col:
            uploaded_chart = st.file_uploader("📸 1. 점선 박스 안을 클릭 후 Ctrl+V (또는 파일 직접 첨부)", type=["png", "jpg", "jpeg"])
        with url_col:
            image_url = st.text_input("🔗 2. 이미지 주소(URL) 붙여넣기", placeholder="https://example.com/chart.png")
            st.caption("인터넷 차트 이미지 우클릭 -> '이미지 주소 복사' 후 붙여넣기")
            
        img_to_analyze = None
        
        if uploaded_chart:
            img_to_analyze = PIL.Image.open(uploaded_chart)
            st.image(img_to_analyze, caption="✅ 정상적으로 인식된 차트 이미지", use_container_width=True)
            
        elif image_url:
            try:
                img_to_analyze = PIL.Image.open(requests.get(image_url, stream=True).raw)
                st.image(img_to_analyze, caption="✅ URL에서 성공적으로 불러온 차트", use_container_width=True)
            except Exception as e:
                st.error("❌ 이미지 URL을 불러올 수 없습니다. 권한이 막혀있지 않은 올바른 주소인지 확인해주세요.")

        if img_to_analyze:
            st.divider()
            if st.button("🤖 Gemini Vision 정밀 분석 시작", type="primary", use_container_width=True):
                if not api_key_input:
                    st.error("좌측 사이드바에 API 키를 먼저 입력해주세요.")
                else:
                    with st.spinner("AI가 차트의 패턴, 지지/저항선, 엘리어트 파동 등을 시각적으로 해독 중입니다... (약 10초 소요)"):
                        prompt = """
                        당신은 월스트리트의 전설적인 차트 분석가입니다. 
                        제시된 차트 이미지를 분석하여 다음 3가지를 도출해주세요:
                        1. 현재 캔들 패턴 및 전반적인 추세 (상승/하락/횡보)
                        2. 시각적으로 보이는 주요 지지선과 저항선 추정 구간
                        3. 이 패턴이 의미하는 향후 예상 시나리오와 단기 대응 전략
                        마크다운 형식으로 가독성 좋게 작성해주세요.
                        """
                        result = ask_gemini_vision(prompt, img_to_analyze, api_key_input)
                        st.markdown("### 📊 AI 차트 해독 리포트")
                        st.success(result)

elif selected_menu == "⚡ 메가트렌드 & 테마 발굴기":
    st.markdown("## ⚡ 메가트렌드 & 주도 테마 밸류체인 스캐너")
    st.write("단순 관련주 나열을 넘어, AI가 테마의 핵심 모멘텀을 분석하고 전체 밸류체인 내의 수혜주 타점을 병렬로 초고속 스크리닝합니다.")
    
    hot_themes_tab5 = get_trending_themes_with_ai(api_key_input) if api_key_input else ["AI 반도체", "데이터센터", "바이오", "로봇"]
    cols_d = st.columns(4)
    
    for idx, theme in enumerate(hot_themes_tab5[:4]):
        if cols_d[idx].button(f"🔥 {theme}", use_container_width=True): 
            st.session_state.deep_tech_query = theme
            st.session_state.deep_tech_results = None 
            st.session_state.deep_tech_brief = None
            st.session_state.deep_tech_input = ""
            st.rerun()
            
    st.markdown("**직접 테마 입력:**")
    with st.form(key="theme_search_form", clear_on_submit=False):
        col_in1, col_in2 = st.columns([8, 2])
        custom_query = col_in1.text_input("테마입력", label_visibility="collapsed", value=st.session_state.deep_tech_input, placeholder="예: 양자암호, 전고체 배터리, 비만치료제")
        submit_btn = col_in2.form_submit_button("🔍 대장주 발굴", use_container_width=True)
        
        if submit_btn and custom_query:
            st.session_state.deep_tech_query = custom_query
            st.session_state.deep_tech_results = None
            st.session_state.deep_tech_brief = None
            st.session_state.deep_tech_input = custom_query
            st.rerun()

    if st.session_state.deep_tech_query and st.session_state.deep_tech_results is None and api_key_input:
        st.markdown(f"### 🔎 '{st.session_state.deep_tech_query}' 테마/섹터 정밀 분석")
        
        with st.spinner("AI가 해당 테마의 시장 모멘텀과 핵심 촉매(Catalyst)를 분석 중입니다..."):
            theme_brief_prompt = f"당신은 여의도 테마주/섹터 전문 퀀트 애널리스트입니다. '{st.session_state.deep_tech_query}' 테마에 대해 1) 최근 시장에서 주목받는 이유(핵심 모멘텀), 2) 향후 전망 및 트레이딩 관점에서의 리스크를 마크다운 형태의 3줄 이내로 핵심만 요약해주세요."
            st.session_state.deep_tech_brief = ask_gemini(theme_brief_prompt, api_key_input)

        with st.spinner(f"✨ '{st.session_state.deep_tech_query}' 핵심 대장주 및 밸류체인 수혜주 발굴 중..."):
            theme_stocks = get_theme_stocks_with_ai(st.session_state.deep_tech_query, api_key_input)
            
            if theme_stocks:
                progress_bar = st.progress(0)
                status_text = st.empty()
                theme_res_list = []
                completed, total = 0, len(theme_stocks)
                
                def process_theme_stock(item):
                    name, code = item
                    time.sleep(0.1)
                    return analyze_technical_pattern(name, code)
                
                with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
                    for future in concurrent.futures.as_completed({executor.submit(process_theme_stock, t): t for t in theme_stocks}):
                        res = future.result()
                        completed += 1
                        if res: theme_res_list.append(res)
                        progress_bar.progress(completed / total)
                        status_text.text(f"⚡ 차트 및 수급 데이터 초고속 파싱 중... ({completed}/{total}) - {len(theme_res_list)}개 종목 분석 완료")
                        
                st.session_state.deep_tech_results = theme_res_list
                st.rerun()
            else:
                st.error(f"❌ '{st.session_state.deep_tech_query}' 관련 종목을 찾지 못했습니다.")
                st.session_state.deep_tech_query = None 
                
    if st.session_state.deep_tech_results is not None:
        if st.session_state.get('deep_tech_brief'):
            st.info(f"**💡 AI 테마 인사이트:**\n{st.session_state.deep_tech_brief}")
        display_sorted_results(st.session_state.deep_tech_results, tab_key="t5", api_key=api_key_input)

elif selected_menu == "🚨 상/하한가 분석":
    st.subheader("🚨 오늘의 상/하한가 및 테마 분석")
    with st.spinner("데이터 수집 중..."): 
        upper_df, lower_df = get_limit_stocks()
    
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
            
            sel_u = st.selectbox("상한가 종목 타점 확인:", ["선택"] + upper_df['Name'].tolist(), key="sel_u")
            if sel_u != "선택":
                krx_df_local = get_krx_stocks()
                match_row = krx_df_local[krx_df_local['Name'] == sel_u]
                if not match_row.empty:
                    k_code = match_row['Code'].iloc[0]
                    if res := analyze_technical_pattern(sel_u, k_code): draw_stock_card(res, api_key_str=api_key_input, is_expanded=True, key_suffix="t6_u")
                else:
                    st.error(f"❌ '{sel_u}' 종목의 코드를 찾을 수 없어 분석할 수 없습니다. (신규 상장/이름 변경 가능성)")
        else:
            st.info("현재 상한가 종목이 없습니다.")
            
    with col_l:
        st.markdown("### 🔵 하한가 종목")
        if not lower_df.empty: 
            display_lower = lower_df[['Name', 'Sector', 'Amount_Ouk']].copy()
            display_lower.columns = ['종목명', '섹터', '거래대금(억)']
            display_lower['거래대금(억)'] = display_lower['거래대금(억)'].apply(lambda x: f"{x:,}")
            st.dataframe(display_lower, use_container_width=True, hide_index=True)
        else:
            st.info("현재 하한가 종목이 없습니다.")

elif selected_menu == "🚦 거래량 급증 & 시장경보":
    st.markdown("## 🚦 거래량 급증/급감 & 투자자 보호(시장경보)")
    
    tab_vol, tab_warn = st.tabs(["📊 거래량 급증/급감", "🛡️ 관리종목 및 시장경보"])
    
    with tab_vol:
        st.write("네이버 금융 기준 거래량 급증 및 급감 상위 20개 종목입니다.")
        with st.spinner("데이터 스크래핑 중..."):
            surge_df, drop_df = get_volume_surge_drop()
        
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
        st.write("한국거래소(KRX) 및 네이버 금융 기준 투자자 보호 지정 종목입니다.")
        with st.spinner("시장경보 데이터 스크래핑 중..."):
            mgmt_df, alert_df = get_market_warnings()
            
        st.markdown("### 🛑 관리종목 (상장폐지 위험)")
        if not mgmt_df.empty: st.dataframe(mgmt_df, use_container_width=True, hide_index=True)
        else: st.success("현재 지정된 관리종목이 없습니다.")
        
        st.markdown("### ⚠️ 투자주의/경고/위험 종목")
        if not alert_df.empty: st.dataframe(alert_df, use_container_width=True, hide_index=True)
        else: st.success("현재 지정된 시장경보 종목이 없습니다.")

elif selected_menu == "📰 실시간 속보/리포트":
    st.subheader("📰 실시간 속보 및 증권사 리포트 터미널")
    news_sub1, news_sub2 = st.tabs(["🚨 실시간 특징주/속보", "📋 증권사 종목 리포트"])
    
    with news_sub1:
        if st.button("🔄 속보 리로드"): 
            get_latest_naver_news.clear(); st.session_state.news_data = []; st.rerun()
        with st.spinner("뉴스를 불러오는 중..."): update_news_state()
        
        krx_dict = {row['Name']: row['Code'] for _, row in get_krx_stocks().iterrows() if len(str(row['Name'])) > 1}
        news_aliases = {
            "삼전": "삼성전자", "두산에너빌": "두산에너빌리티", "LG엔솔": "LG에너지솔루션", 
            "엘지엔솔": "LG에너지솔루션", "에코프로BM": "에코프로비엠", "에코머티": "에코프로머티리얼즈",
            "한화에어로": "한화에어로스페이스", "SK이노": "SK이노베이션", "카뱅": "카카오뱅크",
            "카페": "카카오페이", "엔씨": "엔씨소프트", "현차": "현대차", "기아차": "기아",
            "포홀": "POSCO홀딩스", "셀트": "셀트리온", "한화오션": "한화오션", "KAI": "한국항공우주"
        }
        sorted_names = sorted(krx_dict.keys(), key=len, reverse=True)
        
        for i, news in enumerate(st.session_state.news_data[:50]):
            title = news['title']
            found_comps = []
            
            for alias, real_name in news_aliases.items():
                if alias in title and real_name in krx_dict:
                    found_comps.append((real_name, krx_dict[real_name]))
                    break
            
            if not found_comps:
                for name in sorted_names:
                    # 👈 [업데이트 v5.7] 식품회사 '대상' 오작동 방지용 예외 처리
                    if name == "대상" and any(x in title for x in ["투자대상", "수상대상", "평가대상", "조사대상", "지원대상", "관리대상"]):
                        continue
                    if name in title:
                        found_comps.append((name, krx_dict[name]))
                        break 
            
            with st.container(border=True):
                cols = st.columns([1, 6, 2, 1])
                cols[0].markdown(f"**🕒 {news['time']}**")
                cols[1].markdown(f"{title}")
                
                with cols[2]:
                    if found_comps:
                        btn_key = f"qa_{i}"
                        if st.button(f"🔍 {found_comps[0][0]} 분석", key=btn_key):
                            st.session_state[f"news_analyze_{i}"] = not st.session_state.get(f"news_analyze_{i}", False)
                cols[3].link_button("원문🔗", news['link'])
                
            if st.session_state.get(f"news_analyze_{i}", False):
                st.divider()
                with st.spinner(f"'{found_comps[0][0]}' 차트 및 타점 분석 중..."):
                    res = analyze_technical_pattern(found_comps[0][0], found_comps[0][1])
                    if res: draw_stock_card(res, api_key_str=api_key_input, is_expanded=True, key_suffix=f"news_qa_{i}")
                    else: st.error("❌ 분석 불가 종목입니다.")
                
    with news_sub2:
        st.markdown("### 📋 오늘의 실시간 증권사 리포트")
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

elif selected_menu == "🧪 v5.0 AI 포트폴리오 랩":
    if 'price_scan_results' not in st.session_state:
        st.session_state.price_scan_results = None

    st.markdown("## 🧪 v5.0 차세대 퀀트 & 포트폴리오 랩 (Beta)")
    st.write("단일 종목 분석을 넘어선 'AI 멀티 에이전트, 포트폴리오 상관관계, 대안 데이터(Sentiment), 커스텀 팩터, 조건 검색' 기반의 하이엔드 기능을 테스트합니다.")
    
    v5_tab1, v5_tab2, v5_tab3, v5_tab4, v5_tab5 = st.tabs([
        "🤖 1. AI 멀티 에이전트 토론", 
        "🛡️ 2. 리스크 상관계수 맵", 
        "👥 3. 군중 심리(FOMO) 트래커", 
        "⚙️ 4. 팩터 커스텀 스튜디오",
        "💰 5. 금액대별 종목 스캐너"
    ])
    
    # ----------------------------------------------------
    # 1. AI 멀티 에이전트 난상토론
    # ----------------------------------------------------
    with v5_tab1:
        st.markdown("### 🤖 AI 전문가 3인방 난상토론 & 스코어링")
        st.caption("차트 전문가, 가치투자 매니저, 매크로 이코노미스트가 한 종목을 두고 각자의 시각에서 평가합니다.")
        
        with st.form(key="debate_form"):
            debate_ticker = st.text_input("분석할 종목명 또는 티커 입력 (예: 삼성전자, 005930, AAPL)").upper()
            debate_btn = st.form_submit_button("🔥 난상토론 시작", type="primary", use_container_width=True)
        
        if debate_btn:
            if not api_key_input:
                st.error("좌측 사이드바에 API 키를 입력해주세요.")
            elif not debate_ticker:
                st.warning("종목을 입력해주세요.")
            else:
                with st.spinner("3명의 AI 전문가가 데이터를 분석하고 토론을 준비 중입니다... (약 10~15초 소요)"):
                    prompt = f"""
                    당신은 3명의 자아가 부여된 주식 토론 시스템입니다. '{debate_ticker}' 종목에 대해 다음 3가지 관점에서 의견을 내고, 마지막에 종합 점수를 도출하세요.
                    반드시 아래 지정된 마크다운 포맷을 지켜주세요.
                    
                    **[차트 & 모멘텀 전문가]**
                    - (기술적 분석, 수급 추세 기반의 짧은 코멘트 2줄)
                    
                    **[가치투자 펀드매니저]**
                    - (실적, PER/PBR 밸류에이션, 해자 기반의 짧은 코멘트 2줄)
                    
                    **[매크로 이코노미스트]**
                    - (금리, 환율, 산업 사이클 등 거시경제 기반 짧은 코멘트 2줄)
                    
                    **[최종 매력도 점수]**
                    - (0에서 100 사이의 숫자만 단답으로 적으세요. 예: 75)
                    """
                    response = ask_gemini(prompt, api_key_input)
                    
                    try:
                        parts = response.split("**[최종 매력도 점수]**")
                        debate_text = parts[0].strip()
                        score_str = re.sub(r'[^0-9]', '', parts[1])
                        score = int(score_str) if score_str else 50
                        
                        col_text, col_score = st.columns([2, 1])
                        with col_text:
                            st.info(debate_text)
                        with col_score:
                            fig_gauge = go.Figure(go.Indicator(
                                mode = "gauge+number",
                                value = score,
                                title = {'text': "<b>최종 투자 매력도</b>"},
                                gauge = {
                                    'axis': {'range': [0, 100]},
                                    'bar': {'color': "black", 'thickness': 0.2},
                                    'steps': [
                                        {'range': [0, 40], 'color': "#ffcccb"},
                                        {'range': [40, 60], 'color': "#fff9c4"},
                                        {'range': [60, 100], 'color': "#c8e6c9"}
                                    ]
                                }
                            ))
                            fig_gauge.update_layout(height=250, margin=dict(l=10, r=10, t=60, b=10))
                            st.plotly_chart(fig_gauge, use_container_width=True)
                            
                    except Exception as e:
                        st.markdown(response)
                        
    # ----------------------------------------------------
    # 2. 포트폴리오 상관계수 히트맵
    # ----------------------------------------------------
    with v5_tab2:
        st.markdown("### 🛡️ 내 계좌 리스크 (상관계수) 히트맵")
        st.write("보유 종목들이 얼마나 비슷하게 움직이는지(동조화 현상) 확인하여, 계좌가 한 번에 박살나는 것을 방지하세요. (빨간색일수록 같이 움직이고, 파란색일수록 반대로 움직입니다.)")
        
        with st.form(key="corr_form"):
            default_tickers = "삼성전자, 현대차, SK하이닉스, AAPL, TSLA"
            port_input = st.text_input("분석할 종목들을 쉼표(,)로 구분해 입력하세요 (국장/미장 혼합 가능)", value=default_tickers)
            corr_btn = st.form_submit_button("📊 상관계수 분석", type="primary", use_container_width=True)
        
        if corr_btn:
            port_tickers = [t.strip() for t in port_input.split(",") if t.strip()]
            if len(port_tickers) < 2:
                st.warning("최소 2개 이상의 종목을 입력해주세요.")
            else:
                with st.spinner("과거 1년치 주가 데이터를 수집하여 상관관계를 연산 중입니다..."):
                    try:
                        price_dict = {}
                        for t in port_tickers:
                            df_h = get_historical_data(t, 365)
                            if not df_h.empty:
                                df_h.index = pd.to_datetime(df_h.index).tz_localize(None)
                                df_h = df_h[~df_h.index.duplicated(keep='first')]
                                price_dict[t] = df_h['Close']
                        
                        if len(price_dict) < 2:
                            st.error("데이터를 충분히 불러오지 못했습니다. 종목명을 정확히 입력해주세요.")
                        else:
                            data = pd.DataFrame(price_dict).ffill().dropna()
                            corr_matrix = data.pct_change().corr().round(2)
                            
                            fig_corr = px.imshow(
                                corr_matrix, 
                                text_auto=True, 
                                color_continuous_scale='RdBu_r', 
                                zmin=-1, zmax=1,
                                labels=dict(color="상관계수")
                            )
                            fig_corr.update_layout(height=500)
                            st.plotly_chart(fig_corr, use_container_width=True)
                            
                            st.caption("💡 **해석 팁:** 1.0에 가까울수록 똑같이 움직이며(위험 분산 안 됨), 0에 가까우면 따로 움직이고, 음수(-)면 반대로 움직여 훌륭한 헷징 수단이 됩니다.")
                    except Exception as e:
                        st.error(f"오류 발생: {e}")

    # ----------------------------------------------------
    # 3. 군중 심리(FOMO) 트래커
    # ----------------------------------------------------
    with v5_tab3:
        st.markdown("### 👥 군중 심리 트래커 (FOMO vs FUD)")
        st.write("최신 금융 뉴스 헤드라인들을 AI가 자연어 처리(NLP)하여 현재 대중들의 탐욕(FOMO)과 공포(FUD) 수준을 측정합니다.")
        
        with st.form(key="senti_form"):
            senti_ticker = st.text_input("심리 분석을 원하는 종목명 또는 티커 (예: 에코프로, PLTR, 삼성전자)")
            senti_btn = st.form_submit_button("🧠 심리 지수 추출", type="primary", use_container_width=True)
        
        if senti_btn:
            if not api_key_input: st.error("API 키가 필요합니다.")
            elif not senti_ticker: st.warning("종목을 입력하세요.")
            else:
                with st.spinner(f"'{senti_ticker}' 관련 최신 뉴스를 스크래핑 및 AI 감성 분석 중..."):
                    try:
                        senti_ticker_clean = senti_ticker.strip()
                        krx_df = get_krx_stocks()
                        name_to_code = dict(zip(krx_df['Name'], krx_df['Code']))
                        
                        is_kr = False
                        kr_code = ""
                        
                        if senti_ticker_clean in name_to_code:
                            is_kr = True
                            kr_code = name_to_code[senti_ticker_clean]
                        elif re.match(r'^\d{6}$', senti_ticker_clean):
                            is_kr = True
                            kr_code = senti_ticker_clean

                        titles = []
                        if is_kr:
                            url = f"https://finance.naver.com/item/news_news.naver?code={kr_code}"
                            res = requests.get(url, headers={"User-Agent": "Mozilla/5.0"})
                            soup = BeautifulSoup(res.content.decode('euc-kr', 'replace'), 'html.parser')
                            links = soup.select('.tit')
                            titles = [link.text.strip() for link in links[:10]]
                        else:
                            news_items = yf.Ticker(senti_ticker_clean).news
                            titles = [n['title'] for n in news_items[:10]] if news_items else []

                        if not titles:
                            st.error("최근 뉴스 데이터를 찾을 수 없습니다.")
                        else:
                            titles_str = "\n".join(titles)
                            
                            prompt = f"""
                            당신은 행동재무학(Behavioral Finance) 퀀트입니다. 
                            다음은 '{senti_ticker_clean}' 종목에 대한 최근 뉴스 헤드라인들입니다.
                            이 헤드라인들을 바탕으로 현재 시장 참여자들의 심리 상태를 0부터 100 사이의 'FOMO 지수'로 평가하세요.
                            (0 = 극단적 공포/절망/FUD, 50 = 중립, 100 = 극단적 탐욕/맹신/FOMO)
                            
                            [뉴스 헤드라인]
                            {titles_str}
                            
                            답변은 반드시 다음 형식을 지켜주세요.
                            점수: [여기에 숫자만]
                            이유: [2줄 요약]
                            """
                            senti_res = ask_gemini(prompt, api_key_input)
                            
                            score_match = re.search(r'점수:\s*(\d+)', senti_res)
                            senti_score = int(score_match.group(1)) if score_match else 50
                            
                            s_col1, s_col2 = st.columns([1, 2])
                            with s_col1:
                                fig_senti = go.Figure(go.Indicator(
                                    mode = "gauge+number",
                                    value = senti_score,
                                    title = {'text': "<b>FOMO / FUD Index</b>"},
                                    gauge = {
                                        'axis': {'range': [0, 100]},
                                        'bar': {'color': "black", 'thickness': 0.2},
                                        'steps': [
                                            {'range': [0, 30], 'color': "royalblue", 'name': "FUD (공포)"},
                                            {'range': [30, 70], 'color': "lightgray"},
                                            {'range': [70, 100], 'color': "tomato", 'name': "FOMO (탐욕)"}
                                        ]
                                    }
                                ))
                                fig_senti.update_layout(height=300, margin=dict(l=10, r=10, t=60, b=10))
                                st.plotly_chart(fig_senti, use_container_width=True)
                            with s_col2:
                                st.markdown("#### 📰 수집된 최신 헤드라인 요약 및 AI 의견")
                                st.info(senti_res)
                                with st.expander("원문 헤드라인 보기"):
                                    for t in titles: st.write(f"- {t}")
                    except Exception as e:
                        st.error(f"오류가 발생했습니다: {e}")

    # ----------------------------------------------------
    # 4. 커스텀 팩터 랩 (백테스팅 스튜디오)
    # ----------------------------------------------------
    with v5_tab4:
        st.markdown("### ⚙️ 나만의 퀀트 팩터 커스텀 스튜디오")
        st.write("단순한 골든크로스를 넘어, RSI와 단기/장기 이평선을 내 마음대로 조작하여 최적의 승률을 찾아내는 시뮬레이터입니다.")
        
        with st.form(key="factor_form"):
            c_fac1, c_fac2, c_fac3 = st.columns(3)
            with c_fac1: custom_ticker = st.text_input("테스트 종목 (국/미장 모두 가능)", value="삼성전자")
            with c_fac2: short_ma = st.number_input("단기 이평선 (일)", min_value=3, max_value=20, value=5)
            with c_fac3: long_ma = st.number_input("중장기 이평선 (일)", min_value=20, max_value=200, value=20)
            
            rsi_limit = st.slider("RSI 필터 (이 값 아래일 때만 매수 신호 발생)", min_value=20, max_value=80, value=50)
            factor_btn = st.form_submit_button("🚀 커스텀 전략 시뮬레이션 돌리기", type="primary", use_container_width=True)
            
        if factor_btn:
            with st.spinner(f"과거 2년치 데이터로 [{short_ma}일/{long_ma}일 교차 & RSI < {rsi_limit}] 전략 백테스팅 중..."):
                try:
                    df = get_historical_data(custom_ticker.strip(), 730)
                    if df.empty:
                        st.error("데이터를 가져오지 못했습니다. 종목명을 정확히 입력해주세요.")
                    else:
                        if isinstance(df.columns, pd.MultiIndex):
                            df = df['Close'].to_frame()
                            df.columns = ['Close']
                            
                        df['MA_S'] = df['Close'].rolling(window=short_ma).mean()
                        df['MA_L'] = df['Close'].rolling(window=long_ma).mean()
                        
                        delta = df['Close'].diff()
                        gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
                        loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
                        rs = gain / loss
                        df['RSI'] = 100 - (100 / (1 + rs))
                        
                        df['Signal'] = 0
                        cond_buy = (df['MA_S'] > df['MA_L']) & (df['RSI'] < rsi_limit)
                        df.loc[cond_buy, 'Signal'] = 1
                        
                        df['Position'] = df['Signal'].shift(1).fillna(0)
                        df['Daily_Return'] = df['Close'].pct_change()
                        df['Strategy_Return'] = df['Position'] * df['Daily_Return']
                        
                        df['Cum_Market'] = (1 + df['Daily_Return']).cumprod()
                        df['Cum_Strategy'] = (1 + df['Strategy_Return']).cumprod()
                        
                        fig_bt = go.Figure()
                        fig_bt.add_trace(go.Scatter(x=df.index, y=df['Cum_Market'], name="단순 존버 (Buy & Hold)", line=dict(color='gray', dash='dot')))
                        fig_bt.add_trace(go.Scatter(x=df.index, y=df['Cum_Strategy'], name="커스텀 팩터 전략", line=dict(color='#ff4b4b', width=2.5)))
                        fig_bt.update_layout(title=f"[{custom_ticker}] 나만의 커스텀 전략 누적 수익률 비교", height=400, hovermode="x unified")
                        st.plotly_chart(fig_bt, use_container_width=True)
                        
                        final_market = (df['Cum_Market'].iloc[-1] - 1) * 100
                        final_strat = (df['Cum_Strategy'].iloc[-1] - 1) * 100
                        
                        res1, res2 = st.columns(2)
                        res1.metric("단순 존버 시 누적 수익률", f"{final_market:.2f}%")
                        res2.metric("커스텀 전략 적용 수익률", f"{final_strat:.2f}%", f"{final_strat - final_market:.2f}%p 대비")
                        
                        if final_strat > final_market:
                            st.success("🎉 축하합니다! 하락장 방어와 매수 타점 조절을 통해 단순 보유보다 더 뛰어난 알파(Alpha) 수익 창출에 성공했습니다.")
                        else:
                            st.warning("🤔 잦은 매매 시그널로 인해 오히려 수익률이 깎였습니다. 이평선 길이를 늘리거나 RSI 조건을 완화해 보세요.")

                except Exception as e:
                    st.error(f"시뮬레이션 중 오류 발생: {str(e)}")

    # ----------------------------------------------------
    # 5. 금액대별 종목 스캐너
    # ----------------------------------------------------
    with v5_tab5:
        st.markdown("### 💰 금액대별 실시간 종목 스캐너")
        st.write("원하는 가격대의 주식을 빠르게 검색하고 기술적 타점을 분석합니다.")
        
        with st.form("price_scan_form"):
            c_p1, c_p2 = st.columns(2)
            with c_p1:
                market_choice = st.selectbox("시장 선택", ["🇰🇷 국내 주식", "🇺🇸 미국 주식"])
            with c_p2:
                unit_label = "원" if market_choice == "🇰🇷 국내 주식" else "달러($)"
                price_range = st.slider(f"검색할 가격대 ({unit_label})", min_value=1000 if market_choice == "🇰🇷 국내 주식" else 1.0, 
                                        max_value=1000000 if market_choice == "🇰🇷 국내 주식" else 1000.0, 
                                        value=(10000, 50000) if market_choice == "🇰🇷 국내 주식" else (50.0, 200.0),
                                        step=1000 if market_choice == "🇰🇷 국내 주식" else 5.0)
            
            scan_limit = st.number_input("최대 검색 종목 수", min_value=10, max_value=100, value=30, step=10)
            scan_btn = st.form_submit_button("🚀 가격대별 초고속 병렬 스캔 시작", type="primary", use_container_width=True)

        if scan_btn:
            with st.spinner(f"설정된 가격대({price_range[0]:,} ~ {price_range[1]:,} {unit_label})의 종목을 병렬 스캔 중입니다..."):
                found_stocks = []
                
                if market_choice == "🇰🇷 국내 주식":
                    krx_df = get_krx_stocks()
                    if not krx_df.empty:
                        sample_stocks = krx_df.sample(n=min(len(krx_df), 300)).values.tolist()
                        progress_bar = st.progress(0)
                        status_text = st.empty()
                        
                        def check_price(stock):
                            name, code, _ = stock
                            try:
                                df = get_historical_data(code, 5)
                                if not df.empty:
                                    current_price = float(df['Close'].iloc[-1])
                                    if price_range[0] <= current_price <= price_range[1]:
                                        return analyze_technical_pattern(name, code)
                            except: pass
                            return None
                            
                        completed = 0
                        with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
                            for future in concurrent.futures.as_completed({executor.submit(check_price, s): s for s in sample_stocks}):
                                res = future.result()
                                completed += 1
                                if res: 
                                    found_stocks.append(res)
                                progress_bar.progress(min(completed / len(sample_stocks), 1.0))
                                status_text.text(f"스캔 진행 중... {len(found_stocks)}개 포착")
                                if len(found_stocks) >= scan_limit: 
                                    break 
                else:
                    st.info("미국 주식은 실시간 급등주 목록(Yahoo Finance) 중에서 해당 가격대를 필터링합니다.")
                    us_df, _, _ = get_us_top_gainers()
                    if not us_df.empty:
                        progress_bar = st.progress(0)
                        status_text = st.empty()
                        us_targets = us_df[['종목코드', '기업명']].values.tolist()
                        
                        def check_us_price(stock):
                            ticker, name = stock
                            try:
                                df = get_historical_data(ticker, 5)
                                if not df.empty:
                                    current_price = float(df['Close'].iloc[-1])
                                    if price_range[0] <= current_price <= price_range[1]:
                                        return analyze_technical_pattern(name, ticker)
                            except: pass
                            return None
                            
                        completed = 0
                        with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
                            for future in concurrent.futures.as_completed({executor.submit(check_us_price, s): s for s in us_targets}):
                                res = future.result()
                                completed += 1
                                if res: 
                                    found_stocks.append(res)
                                progress_bar.progress(min(completed / len(us_targets), 1.0))
                                status_text.text(f"미국장 스캔 진행 중... {len(found_stocks)}개 포착")
                                if len(found_stocks) >= scan_limit: 
                                    break

                st.session_state.price_scan_results = found_stocks
                st.rerun()

        if st.session_state.get('price_scan_results') is not None:
            res_list = st.session_state.price_scan_results
            if not res_list:
                st.warning("조건에 맞는 종목을 찾지 못했습니다. 가격 범위를 조절해보세요.")
            else:
                st.success(f"🎯 지정한 가격대에서 총 {len(res_list)}개의 종목을 찾았습니다!")
                
                sort_opt = st.radio("⬇️ 결과 정렬 방식", ["기본 (검색순)", "현재가 낮은순 🔽", "현재가 높은순 🔼", "RSI 낮은순 (바닥)"], horizontal=True, key="price_scan_sort")
                
                display_list = res_list.copy()
                if sort_opt == "현재가 낮은순 🔽":
                    display_list.sort(key=lambda x: x['현재가'])
                elif sort_opt == "현재가 높은순 🔼":
                    display_list.sort(key=lambda x: x['현재가'], reverse=True)
                elif sort_opt == "RSI 낮은순 (바닥)":
                    display_list.sort(key=lambda x: x['RSI'])
                    
                for i, res in enumerate(display_list):
                    draw_stock_card(res, api_key_str=api_key_input, is_expanded=False, key_suffix=f"price_scan_{i}")
