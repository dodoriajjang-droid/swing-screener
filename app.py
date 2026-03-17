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

# ==========================================
# 1. 초기 설정 
# ==========================================
st.set_page_config(page_title="Jaemini 주식 검색기", layout="wide", page_icon="📈")
st_autorefresh(interval=300000, limit=None, key="news_autorefresh")

for key in ['seen_links', 'seen_titles', 'news_data', 'watchlist']:
    if key not in st.session_state:
        st.session_state[key] = set() if 'seen' in key else []
        
if 'quick_analyze_news' not in st.session_state:
    st.session_state.quick_analyze_news = None

if 'scan_results' not in st.session_state:
    st.session_state.scan_results = None

if 'value_scan_results' not in st.session_state:
    st.session_state.value_scan_results = None

# ==========================================
# 2. 통합 AI 호출 엔진
# ==========================================
@st.cache_data(ttl=3600)
def ask_gemini(prompt, _api_key):
    if not _api_key: return "API 키가 필요합니다."
    try:
        genai.configure(api_key=_api_key)
        return genai.GenerativeModel('gemini-2.5-flash').generate_content(prompt).text
    except Exception as e: return f"AI 분석 오류: {str(e)}"

@st.cache_data(ttl=3600)
def get_quick_ai_opinion(stock_name, curr, ma20, rsi, _api_key):
    if not _api_key: return "AI미연동"
    try:
        prompt = f"당신은 실전 스윙 트레이더입니다. '{stock_name}'의 단기 매매 의견을 다음 4개 중 딱 1개로만 답변하세요: [적극매수, 분할매수, 관망, 매수금지]. 다른 부연 설명은 절대 금지.\n데이터: 현재가 {curr}원, 20일선 {ma20}원, RSI {rsi:.1f}"
        res = ask_gemini(prompt, _api_key).replace(".", "").replace("\n", "").strip()
        for kw in ["적극매수", "분할매수", "관망", "매수금지"]:
            if kw in res: return kw
        return "관망"
    except:
        return "오류"

# ==========================================
# 3. 데이터 수집 및 분석 함수들
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

@st.cache_data(ttl=1800)
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
    except: pass
    try:
        proxy_url = f"https://api.allorigins.win/get?url={urllib.parse.quote(url)}"
        res2 = requests.get(proxy_url, headers={"User-Agent": "Mozilla/5.0"}, timeout=5)
        if res2.status_code == 200:
            data = json.loads(res2.json()['contents'])
            return {"score": round(data['fear_and_greed']['score']), "delta": round(data['fear_and_greed']['score'] - data['fear_and_greed']['previous_close']), "rating": data['fear_and_greed']['rating'].capitalize()}
    except: pass
    try:
        proxy_url3 = f"https://api.codetabs.com/v1/proxy?quest={urllib.parse.quote(url)}"
        res3 = requests.get(proxy_url3, headers={"User-Agent": "Mozilla/5.0"}, timeout=5)
        if res3.status_code == 200:
            data = res3.json()
            return {"score": round(data['fear_and_greed']['score']), "delta": round(data['fear_and_greed']['score'] - data['fear_and_greed']['previous_close']), "rating": data['fear_and_greed']['rating'].capitalize()}
    except: pass
    return None

@st.cache_data(ttl=3600)
def get_us_top_gainers():
    try:
        response = requests.get('https://finance.yahoo.com/gainers', headers={'User-Agent': 'Mozilla/5.0'})
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
        if df.empty: return pd.DataFrame(), 1350.0
        df = df.sort_values('등락률', ascending=False).head(15)
        try: ex_rate = float(yf.Ticker("KRW=X").history(period="5d")['Close'].iloc[-1])
        except: ex_rate = 1350.0 
        def get_korean_name(n):
            try:
                res = requests.get(f"https://translate.googleapis.com/translate_a/single?client=gtx&sl=en&tl=ko&dt=t&q={urllib.parse.quote(n)}", timeout=2)
                ko_name = res.json()[0][0][0]
                return f"{n} / {ko_name}" if ko_name.lower() != n.lower() else n
            except: return n
        df['기업명'] = df['기업명'].apply(get_korean_name)
        df['현재가'] = df['현재가'].apply(lambda x: f"${float(x.replace(',', '')):.2f} (약 {int(float(x.replace(',', '')) * ex_rate):,}원)" if x and x.replace('.', '', 1).replace(',', '').isdigit() else str(x))
        df['등락률'] = df['등락률'].apply(lambda x: f"+{x:.2f}%")
        return df, ex_rate
    except: return pd.DataFrame(), 1350.0

@st.cache_data(ttl=86400)
def get_krx_stocks():
    try:
        url = 'http://kind.krx.co.kr/corpgeneral/corpList.do?method=download&searchType=13'
        res = requests.get(url, headers={'User-Agent': 'Mozilla/5.0'}, timeout=10)
        df = pd.read_html(StringIO(res.content.decode('euc-kr')), header=0)[0]
        df = df[['회사명', '종목코드', '업종']]
        df.columns = ['Name', 'Code', 'Sector']
        df['Code'] = df['Code'].astype(str).str.zfill(6)
        df = df.drop_duplicates(subset=['Name']).reset_index(drop=True)
        return df
    except: return pd.DataFrame(columns=['Name', 'Code', 'Sector'])

def fetch_naver_volume(sosok, pages=1):
    df_list = []
    try:
        for page in range(1, pages + 1):
            url = f"https://finance.naver.com/sise/sise_quant.naver?sosok={sosok}&page={page}"
            res = requests.get(url, headers={'User-Agent': 'Mozilla/5.0'}, timeout=5)
            html = res.content.decode('euc-kr', errors='replace')
            tables = pd.read_html(StringIO(html))
            for t in tables:
                if '종목명' in t.columns and '현재가' in t.columns and '거래량' in t.columns:
                    df = t.dropna(subset=['종목명']).copy()
                    df = df[df['종목명'] != '종목명']
                    df_list.append(df)
                    break
    except: pass
    if df_list: return pd.concat(df_list, ignore_index=True).drop_duplicates(subset=['종목명'])
    return pd.DataFrame()

@st.cache_data(ttl=300)
def get_trading_value_kings():
    try:
        df_kpi = fetch_naver_volume(0, 1)
        df_kdq = fetch_naver_volume(1, 1)
        df = pd.concat([df_kpi, df_kdq], ignore_index=True)
        if df.empty: return pd.DataFrame()
        
        mask = df['종목명'].str.contains('KODEX|TIGER|KBSTAR|KOSEF|ARIRANG|HANARO|ACE|스팩|ETN|선물|인버스|레버리지', na=False)
        df = df[~mask].copy()
        
        def extract_num(x):
            try:
                val = re.sub(r'[^\d\.\-]', '', str(x))
                if val in ['', '-']: return 0.0
                return float(val)
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
    except: return pd.DataFrame()

@st.cache_data(ttl=300)
def get_scan_targets(limit=50):
    try:
        df_fdr = fdr.StockListing('KRX')
        if not df_fdr.empty:
            df_fdr['Amount'] = pd.to_numeric(df_fdr['Amount'].astype(str).str.replace(r'[^\d\.]', '', regex=True), errors='coerce').fillna(0.0)
            if df_fdr['Amount'].max() > 0:
                mask = df_fdr['Name'].str.contains('KODEX|TIGER|KBSTAR|KOSEF|ARIRANG|HANARO|ACE|스팩|ETN|선물|인버스|레버리지', na=False)
                df_fdr = df_fdr[~mask].drop_duplicates(subset=['Name']).sort_values('Amount', ascending=False)
                targets = df_fdr.head(limit)[['Name', 'Code']].values.tolist()
                if len(targets) >= limit or len(targets) > 100:
                    return targets
    except: pass
    
    try:
        df_kpi = fetch_naver_volume(0, pages=3) 
        df_kdq = fetch_naver_volume(1, pages=3)
        df = pd.concat([df_kpi, df_kdq], ignore_index=True)
        if df.empty: return []
        
        mask = df['종목명'].str.contains('KODEX|TIGER|KBSTAR|KOSEF|ARIRANG|HANARO|ACE|스팩|ETN|선물|인버스|레버리지', na=False)
        df = df[~mask].drop_duplicates(subset=['종목명']).copy()
        
        def extract_num(x):
            try:
                val = re.sub(r'[^\d\.\-]', '', str(x))
                if val in ['', '-']: return 0.0
                return float(val)
            except: return 0.0
            
        df['Close'] = df['현재가'].apply(extract_num)
        df['Volume'] = df['거래량'].apply(extract_num)
        df['Amount'] = df['Close'] * df['Volume']
        
        df = df.sort_values('Amount', ascending=False).head(limit)
        
        krx = get_krx_stocks()
        if not krx.empty:
            df = pd.merge(df, krx[['Name', 'Code']], left_on='종목명', right_on='Name', how='inner')
            return df[['Name', 'Code']].values.tolist()
        return []
    except: return []

@st.cache_data(ttl=300)
def get_limit_stocks():
    def fetch_naver_limit(url, is_upper):
        try:
            res = requests.get(url, headers={'User-Agent': 'Mozilla/5.0'}, timeout=5)
            html_str = res.content.decode('euc-kr', errors='replace')
            tables = pd.read_html(StringIO(html_str))
            for t in tables:
                if '종목명' in t.columns and '현재가' in t.columns:
                    t = t.dropna(subset=['종목명', '현재가'])
                    t = t[t['종목명'].apply(lambda x: isinstance(x, str))]
                    t = t[t['종목명'] != '종목명']
                    t = t[~t['종목명'].str.contains('스팩|ETN|선물|인버스|레버리지', na=False)]
                    if not t.empty:
                        res_df = pd.DataFrame()
                        res_df['Name'] = t['종목명']
                        def to_f(x):
                            try:
                                s = str(x).replace(',', '').replace('%', '').replace('+', '').strip()
                                if s in ['', 'nan', 'NaN', '-']: return 0.0
                                return float(s)
                            except: return 0.0
                        res_df['Close'] = t['현재가'].apply(to_f)
                        chg = t['전일비'].apply(to_f)
                        res_df['Changes'] = chg if is_upper else -chg
                        rat = t['등락률'].apply(to_f)
                        res_df['ChagesRatio'] = rat if is_upper else -rat
                        vol = t['거래량'].apply(to_f)
                        res_df['Amount_Ouk'] = (res_df['Close'] * vol / 100000000).astype(int)
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

    for col in ['Code', 'Sector', 'Close', 'Changes', 'ChagesRatio', 'Amount_Ouk', 'PrevClose', 'Name']:
        if col not in upper_df.columns: upper_df[col] = "기타" if col == 'Sector' else 0
        if col not in lower_df.columns: lower_df[col] = "기타" if col == 'Sector' else 0
        
    return upper_df.sort_values('Amount_Ouk', ascending=False), lower_df.sort_values('Amount_Ouk', ascending=False)

@st.cache_data(ttl=120)
def get_latest_naver_news():
    try:
        ts = int(datetime.now().timestamp())
        url = f"https://finance.naver.com/news/news_list.naver?mode=LSS2D&section_id=101&section_id2=258&_ts={ts}"
        res = requests.get(url, headers={"User-Agent": "Mozilla/5.0"})
        soup = BeautifulSoup(res.content.decode('euc-kr', errors='replace'), 'html.parser')
        articles = []
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
                    date_part = match.group(1)
                    time_part = match.group(2)
                    today_str = (datetime.utcnow() + timedelta(hours=9)).strftime("%Y-%m-%d")
                    if date_part == today_str: pub_time = time_part
                    else: pub_time = f"{date_part[5:].replace('-', '/')} {time_part}"
                else:
                    match_time = re.search(r'(\d{2}:\d{2})', raw_date)
                    if match_time: pub_time = match_time.group(1)
            if not pub_time: pub_time = (datetime.utcnow() + timedelta(hours=9)).strftime("%H:%M")
            articles.append({"title": title, "link": link, "time": pub_time})
        return articles
    except: return []

def update_news_state():
    items = get_latest_naver_news()
    for item in reversed(items): 
        if item['link'] not in st.session_state.seen_links and item['title'] not in st.session_state.seen_titles:
            st.session_state.news_data.insert(0, item)
            st.session_state.seen_links.add(item['link'])
            st.session_state.seen_titles.add(item['title'])

@st.cache_data(ttl=3600)
def get_all_sector_info(tickers, _api_key):
    results = {t: ("분석 대기", "분석 대기") for t in tickers}
    if not _api_key: return results
    try:
        response = ask_gemini(f"당신은 월스트리트 주식 전문가입니다.\n다음 미국 주식 티커들의 섹터(Sector)와 세부 산업(Industry)을 '한국어'로 분류해주세요.\n반드시 '티커|섹터|산업' 형태로만 답변하세요.\n[티커 목록]\n{chr(10).join(tickers)}", _api_key)
        for line in response.strip().split('\n'):
            parts = line.split('|')
            if len(parts) >= 3 and parts[0].strip().replace('*', '').replace('-', '') in results:
                results[parts[0].strip().replace('*', '').replace('-', '')] = (parts[1].strip(), parts[2].strip())
        return results
    except: return results

@st.cache_data(ttl=3600)
def get_company_summary(ticker, _api_key):
    try:
        biz_summary = yf.Ticker(ticker).info.get('longBusinessSummary', '')
        prompt = f"미국 주식 {ticker}의 영문 개요를 읽고, '무엇을 만들고 어떻게 돈을 버는지' 한국어로 2줄 요약해 주세요. [개요]: {biz_summary[:1500]}" if biz_summary else f"미국 주식 '{ticker}' 핵심 비즈니스 모델을 한국어로 2~3줄 요약해 주세요."
        return ask_gemini(prompt, _api_key)
    except: return "기업 정보를 요약하는 중 오류가 발생했습니다."

@st.cache_data(ttl=3600)
def analyze_news_with_gemini(ticker, _api_key):
    try:
        news_list = yf.Ticker(ticker).news
        if not news_list: return "최근 관련 뉴스를 찾을 수 없습니다."
        news_text = "\n".join([f"[{n.get('publisher')}] {n.get('title')}" for n in news_list[:3]])
        prompt = f"한국 주식 스윙 전문 애널리스트입니다. 미국 주식 '{ticker}' 영문 헤드라인을 바탕으로 한국 테마주에 미칠 영향을 분석하세요.\n{news_text}\n* 시장 센티먼트:\n* 재료 지속성:\n* 투자 코멘트:"
        return ask_gemini(prompt, _api_key)
    except: return "뉴스 분석 중 오류가 발생했습니다."

@st.cache_data(ttl=3600)
def get_ai_matched_stocks(ticker, sector, industry, comp_name, _api_key):
    if not _api_key: return []
    try:
        response = ask_gemini(f"미국 주식 '{comp_name}' (티커: {ticker}, 섹터: {sector}, 산업: {industry})와 비즈니스 모델이 유사하거나, 같은 테마로 움직일 수 있는 한국 코스피/코스닥 상장사 20개를 찾아주세요. 반드시 파이썬 리스트로만 답변하세요. 예시: [('삼성전자', '005930')]", _api_key)
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

@st.cache_data(ttl=10800)
def get_trending_themes_with_ai(_api_key):
    default_themes = ["AI 반도체", "비만치료제", "저PBR/밸류업", "전력 설비", "로봇/자동화"]
    if not _api_key: return default_themes
    try:
        response = ask_gemini("최근 한국 증시 가장 핫한 주도 테마 5개만 쉼표로 구분해서 1줄로 출력하세요. 번호/부연설명 절대 금지.", _api_key)
        valid_themes = [t.strip() for t in response.replace('\n', '').replace('*', '').split(',')]
        return valid_themes[:5] if len(valid_themes) >= 5 else default_themes
    except: return default_themes

@st.cache_data(ttl=3600)
def get_longterm_value_stocks_with_ai(theme, cap_size, _api_key):
    if not _api_key: return []
    try:
        prompt = f"한국 증시(코스피/코스닥)에서 '{theme}' 관련 독보적이고 핵심적인 기술을 보유한 유망 기업 중 '{cap_size}'에 해당하는 주식 20개를 찾아주세요. 테마주가 아닌 실제 기술을 개발하거나 관련 사업을 영위하는 장기 투자 관점의 종목이어야 합니다. 반드시 파이썬 리스트로만 답변하세요. 예시: [('삼성전자', '005930')]"
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

def get_fundamentals(ticker_code):
    if ticker_code.isdigit():
        try:
            url = f"https://finance.naver.com/item/main.naver?code={ticker_code}"
            res = requests.get(url, headers={"User-Agent": "Mozilla/5.0"})
            soup = BeautifulSoup(res.text, 'html.parser')
            per = soup.select_one('#_per').text if soup.select_one('#_per') else 'N/A'
            pbr = soup.select_one('#_pbr').text if soup.select_one('#_pbr') else 'N/A'
            return per, pbr
        except: return 'N/A', 'N/A'
    else:
        try:
            info = yf.Ticker(ticker_code).info
            per = round(info.get('trailingPE', 0), 2) if info.get('trailingPE') else 'N/A'
            pbr = round(info.get('priceToBook', 0), 2) if info.get('priceToBook') else 'N/A'
            return per, pbr
        except: return 'N/A', 'N/A'

@st.cache_data(ttl=3600)
def get_historical_data(ticker, days):
    try:
        return fdr.DataReader(ticker, (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d'))
    except: return pd.DataFrame()

@st.cache_data(ttl=3600)
def analyze_technical_pattern(stock_name, ticker_code, offset_days=0):
    if not ticker_code: return None
    try:
        df = fdr.DataReader(ticker_code, (datetime.now() - timedelta(days=150)).strftime('%Y-%m-%d'))
        if len(df) < 20 + offset_days: return None
        
        today_close = int(df['Close'].iloc[-1]) 
        
        if offset_days > 0:
            analysis_df = df.iloc[:-offset_days].copy()
        else:
            analysis_df = df.copy()
            
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
        
        current_price = int(latest['Close']) 
        
        if pd.notna(latest['MA60']) and latest['MA5'] > latest['MA20'] > latest['MA60']: align_status = "🔥 완벽 정배열 (상승 추세)"
        elif pd.notna(latest['MA60']) and latest['MA5'] < latest['MA20'] < latest['MA60']: align_status = "❄️ 역배열 (하락 추세)"
        elif latest['MA5'] > latest['MA20'] and prev['MA5'] <= prev['MA20']: align_status = "✨ 5-20 골든크로스"
        else: align_status = "🌀 혼조세/횡보"
        
        ma20_val = latest['MA20']
        if (ma20_val * 0.97) <= current_price <= (ma20_val * 1.03): status = "✅ 타점 근접 (분할 매수)"
        elif current_price > (ma20_val * 1.03): status = "⚠️ 이격 과다 (눌림목 대기)"
        else: status = "🛑 20일선 이탈 (관망)"
        
        inst_vol, forgn_vol = get_investor_trend(ticker_code)
        per, pbr = get_fundamentals(ticker_code)
        
        target_1 = int(latest['Bollinger_Upper'])
        recent_high = int(analysis_df['Close'].max())
        target_2 = recent_high if recent_high > (target_1 * 1.02) else int(target_1 * 1.05)
        target_3 = int(target_2 * 1.08)
        
        pnl_pct = ((today_close - current_price) / current_price) * 100 if offset_days > 0 and current_price > 0 else 0.0
        
        return {
            "종목명": stock_name, "티커": ticker_code, "현재가": current_price, "상태": status,
            "진입가_가이드": int(ma20_val), 
            "목표가1": target_1, "목표가2": target_2, "목표가3": target_3,
            "손절가": int(ma20_val * 0.97),
            "거래량 급증": "🔥 거래량 터짐" if analysis_df.iloc[-10:]['Volume'].max() > (analysis_df.iloc[-10:]['Vol_MA20'].mean() * 2) else "평이함",
            "RSI": latest['RSI'], "배열상태": align_status, "기관수급": inst_vol, "외인수급": forgn_vol,
            "PER": per, "PBR": pbr, "OBV": analysis_df['OBV'].tail(20),
            "종가 데이터": analysis_df['Close'].tail(20), "거래량 데이터": analysis_df['Volume'].tail(20),
            "오늘현재가": today_close, "수익률": pnl_pct, "과거검증": offset_days > 0
        }
    except: return None

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
                    if item.text.strip(): events_data.append({"날짜": f"{day}일", "일정": item.text.strip()})
            if events_data: return pd.DataFrame(events_data)
    except: pass
    return pd.DataFrame()

@st.cache_data(ttl=43200) 
def get_dividend_portfolio():
    portfolio = {
        "KRX": [("088980.KS", "맥쿼리인프라", "반기", "6.0~6.5%"),("024110.KS", "기업은행", "결산", "7.5~8.5%"),("316140.KS", "우리금융지주", "분기", "8.0~9.0%"),("033780.KS", "KT&G", "반기/결산", "6.0~7.0%"),("017670.KS", "SK텔레콤", "분기", "6.5~7.0%"),("055550.KS", "신한지주", "분기", "5.5~6.5%"),("086790.KS", "하나금융지주", "분기/결산", "6.0~7.5%"),("105560.KS", "KB금융", "분기", "5.0~6.0%"),("138040.KS", "메리츠금융지주", "결산", "4.5~5.5%"),("139130.KS", "DGB금융지주", "결산", "8.0~9.0%"),("175330.KS", "JB금융지주", "반기/결산", "8.0~9.0%"),("138930.KS", "BNK금융지주", "결산", "8.0~9.0%"),("016360.KS", "삼성증권", "결산", "7.0~8.0%"),("005940.KS", "NH투자증권", "결산", "7.0~8.0%"),("051600.KS", "한전KPS", "결산", "5.5~6.5%"),("030200.KS", "KT", "분기", "5.5~6.5%"),("000815.KS", "삼성화재우", "결산", "6.5~7.5%"),("053800.KS", "현대차2우B", "분기/결산", "6.0~7.5%"),("030000.KS", "제일기획", "결산", "5.5~6.5%"),("040420.KS", "정상제이엘에스", "결산", "6.0~7.0%")],
        "US": [("O", "Realty Income", "월배당", "5.5~6.0%"),("MO", "Altria Group", "분기", "9.0~9.5%"),("VZ", "Verizon", "분기", "6.0~6.5%"),("T", "AT&T", "분기", "6.0~6.5%"),("PM", "Philip Morris", "분기", "5.0~5.5%"),("KO", "Coca-Cola", "분기", "3.0~3.5%"),("PEP", "PepsiCo", "분기", "2.8~3.2%"),("JNJ", "Johnson & Johnson", "분기", "3.0~3.5%"),("PG", "Procter & Gamble", "분기", "2.3~2.8%"),("ABBV", "AbbVie", "분기", "3.8~4.2%"),("PFE", "Pfizer", "분기", "5.5~6.0%"),("CVX", "Chevron", "분기", "4.0~4.5%"),("XOM", "Exxon Mobil", "분기", "3.0~3.5%"),("MMM", "3M", "분기", "5.5~6.5%"),("IBM", "IBM", "분기", "3.5~4.0%"),("ENB", "Enbridge", "분기", "7.0~7.5%"),("WPC", "W. P. Carey", "분기", "6.0~6.5%"),("MAIN", "Main Street", "월배당", "6.0~6.5%"),("ARCC", "Ares Capital", "분기", "9.0~9.5%"),("KMI", "Kinder Morgan", "분기", "6.0~6.5%")],
        "ETF": [("SCHD", "미국 SCHD (고배당)", "분기", "3.4~3.8%"),("JEPI", "미국 JEPI (S&P 프리미엄)", "월배당", "7.0~8.0%"),("JEPQ", "미국 JEPQ (나스닥 프리미엄)", "월배당", "8.5~9.5%"),("VYM", "미국 VYM (고배당)", "분기", "2.8~3.2%"),("SPYD", "미국 SPYD (S&P500 고배당)", "분기", "4.5~5.0%"),("DGRO", "미국 DGRO (배당성장)", "분기", "2.2~2.6%"),("QYLD", "미국 QYLD (커버드콜)", "월배당", "11.0~12.0%"),("XYLD", "미국 XYLD (S&P 커버드콜)", "월배당", "9.0~10.0%"),("DIVO", "미국 DIVO (배당+옵션)", "월배당", "4.5~5.0%"),("VNQ", "미국 VNQ (리츠)", "분기", "4.0~4.5%"),("458730.KS", "TIGER 미국배당다우존스", "월배당", "3.5~4.0%"),("161510.KS", "ARIRANG 고배당주", "결산", "6.0~7.0%"),("458760.KS", "TIGER 미국배당+7%", "월배당", "10.0~11.0%"),("448550.KS", "ACE 미국배당다우존스", "월배당", "3.5~4.0%"),("466950.KS", "KODEX 미국배당프리미엄", "월배당", "7.0~8.0%"),("329200.KS", "TIGER 부동산인프라", "분기", "6.5~7.5%"),("091220.KS", "KODEX 은행", "결산", "6.0~7.0%"),("211560.KS", "TIGER 배당성장", "분기", "4.0~5.0%"),("271560.KS", "ARIRANG 미국고배당", "분기", "3.5~4.5%"),("433330.KS", "TIMEFOLIO 코리아플러스", "월배당", "5.0~6.0%")]
    }
    
    all_tickers = [t for cat in portfolio.values() for t, n, p, y in cat]
    price_dict = {}
    try:
        data = yf.download(all_tickers, period="5d", progress=False)
        if isinstance(data.columns, pd.MultiIndex):
            close_data = data['Close']
        elif 'Close' in data:
            close_data = pd.DataFrame(data['Close'])
        else:
            close_data = pd.DataFrame()
            
        for t in all_tickers:
            if t in close_data.columns:
                val = close_data[t].dropna()
                if not val.empty: price_dict[t] = float(val.iloc[-1])
    except: pass

    results = {"KRX": [], "US": [], "ETF": []}
    for category, stocks in portfolio.items():
        for t_code, name, period, est_yield in stocks:
            p_val = price_dict.get(t_code)
            p_str = f"{int(p_val):,}원" if p_val and ".KS" in t_code else f"${p_val:,.2f}" if p_val else "조회 지연"
            results[category].append({"티커/코드": t_code.replace(".KS", ""), "종목명": name, "현재가": p_str, "배당수익률(예상)": est_yield, "배당주기": period})
                
    return {k: pd.DataFrame(v) for k, v in results.items()}

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

# 👈 [개선 1] 타이틀에서 AI 묻는 것을 빼고 직관적인 핵심 포맷 적용
def draw_stock_card(tech_result, api_key_str="", is_expanded=False, key_suffix="default", show_longterm_chart=False):
    status_emoji = tech_result['상태'].split(' ')[0]
    
    expander_title = f"{status_emoji} {tech_result['종목명']} ({tech_result['현재가']:,}원) ｜ RSI: {tech_result['RSI']:.1f} ｜ (진단: {tech_result['상태']} ｜ 수급: {tech_result['거래량 급증']} ｜ PER: {tech_result['PER']} ｜ PBR: {tech_result['PBR']})"
    
    with st.expander(expander_title, expanded=is_expanded):
        
        # 만약 AI 필터 토글을 켜서 계산된 'AI단기'가 있다면 카드 안쪽에 띄워줌
        if 'AI단기' in tech_result:
            st.markdown(f"**🤖 AI 퀵 진단 의견:** `{tech_result['AI단기']}`")
            
        if tech_result.get('과거검증'):
            pnl = tech_result['수익률']
            color = "#ff4b4b" if pnl > 0 else "#1f77b4"
            bg_color = "rgba(255, 75, 75, 0.1)" if pnl > 0 else "rgba(31, 119, 180, 0.1)"
            st.markdown(f"""
            <div style="background-color: {bg_color}; padding: 15px; border-radius: 10px; margin-bottom: 15px; border: 1px solid {color};">
                <h3 style="margin:0; color: {color};">⏰ 타임머신 검증 결과</h3>
                <p style="margin:5px 0 0 0; font-size: 16px;">스캔 당시 가격 <b>{tech_result['현재가']:,}원</b> ➡️ 오늘 현재 가격 <b>{tech_result['오늘현재가']:,}원</b> 
                <span style="font-size: 20px; font-weight: bold; color: {color};">({pnl:+.2f}%)</span></p>
            </div>
            """, unsafe_allow_html=True)
            
        col_btn1, col_btn2 = st.columns([8, 2])
        col_btn1.markdown(f"**상세 진단:** {tech_result['배열상태']}")
        
        is_in_wl = any(x['티커'] == tech_result['티커'] for x in st.session_state.watchlist)
        if col_btn2.button("⭐ 관심종목 추가" if not is_in_wl else "🌟 추가됨", disabled=is_in_wl, key=f"star_{tech_result['티커']}_{key_suffix}"):
            st.session_state.watchlist.append({'종목명': tech_result['종목명'], '티커': tech_result['티커']})
            st.rerun()

        c1, c2, c3, c4 = st.columns(4)
        curr = tech_result['현재가']
        c1.metric("📌 진입 기준가", f"{tech_result['진입가_가이드']:,}원", f"{tech_result['진입가_가이드'] - curr:,}원 (대비)", delta_color="off")
        c2.metric("🎯 1차 (볼밴상단)", f"{tech_result['목표가1']:,}원", f"+{tech_result['목표가1'] - curr:,}원", delta_color="normal")
        c3.metric("🚀 2차 (스윙전고)", f"{tech_result['목표가2']:,}원", f"+{tech_result['목표가2'] - curr:,}원", delta_color="normal")
        c4.metric("🌌 3차 (오버슈팅)", f"{tech_result['목표가3']:,}원", f"+{tech_result['목표가3'] - curr:,}원", delta_color="normal")
        
        st.markdown("---")
        c5, c6, c7 = st.columns([1, 1, 2])
        c5.metric("🛑 손절 라인", f"{tech_result['손절가']:,}원", f"{tech_result['손절가'] - curr:,}원 (리스크)", delta_color="normal")
        c6.metric("📊 RSI (상대강도)", f"{tech_result['RSI']:.1f}", "🔴 과열" if tech_result['RSI'] >= 70 else "🔵 바닥" if tech_result['RSI'] <= 30 else "⚪ 보통", delta_color="inverse" if tech_result['RSI'] >= 70 else "normal")
        with c7: st.markdown(f"🕵️ **당시 수급 동향 (5일 누적)**<br>**외국인:** `{tech_result['외인수급']}` ｜ **기관:** `{tech_result['기관수급']}`", unsafe_allow_html=True)
        
        if api_key_str:
            st.markdown("<br>", unsafe_allow_html=True)
            if st.button(f"🤖 '{tech_result['종목명']}' 상세 AI 적정가 판단 및 매매 의견", key=f"ai_btn_{tech_result['티커']}_{key_suffix}"):
                with st.spinner("AI가 차트, 가치 평가, 그리고 향후 모멘텀 일정을 분석 중입니다..."):
                    prompt = f"전문 트레이더 관점에서 '{tech_result['종목명']}'을(를) 분석해주세요.\n[데이터] 현재가:{curr}원, 20일선:{tech_result['진입가_가이드']}원, RSI:{tech_result['RSI']:.1f}, PER:{tech_result['PER']}, PBR:{tech_result['PBR']}\n\n1. ⚡ 단기 트레이딩 관점 (차트/모멘텀 중심)\n- 의견 (적극매수/분할매수/관망/매수금지 중 택 1)\n- 이유:\n\n2. 🛡️ 스윙/가치 투자 관점 (재무/가치 중심)\n- 의견 (적극매수/분할매수/관망/매수금지 중 택 1)\n- 이유:\n\n3. 📅 핵심 모멘텀 및 예정된 일정\n- 해당 기업의 주가에 영향을 줄 수 있는 단기/중장기 호재성 일정이나 악재(실적발표, 신제품 출시, 임상, 수주 계약, 산업 트렌드 등)를 아는 대로 요약해주세요.\n\n4. 🎯 종합 요약 (1줄):"
                    st.success(ask_gemini(prompt, api_key_str))
        
        if show_longterm_chart:
            tf = st.radio("📅 차트 기간 선택", ["1개월", "3개월", "1년", "5년"], horizontal=True, key=f"tf_{key_suffix}", index=2)
            days_dict = {"1개월": 30, "3개월": 90, "1년": 365, "5년": 1825}
            with st.spinner(f"{tf} 차트 데이터 불러오는 중..."):
                long_df = get_historical_data(tech_result['티커'], days_dict[tf])
                if not long_df.empty:
                    long_df = long_df.reset_index()
                    long_df['OBV'] = (np.sign(long_df['Close'].diff()) * long_df['Volume']).fillna(0).cumsum()
                    if tf in ["1개월", "3개월"]:
                        long_df['Date_Str'] = long_df['Date'].dt.strftime('%m월 %d일')
                        x_col, x_type = 'Date_Str', 'category'
                    else:
                        x_col, x_type = 'Date', 'date' 
                    ch1, ch2 = st.columns(2)
                    with ch1:
                        st.caption(f"📈 주가 흐름 ({tf})")
                        fig_price = px.line(long_df, x=x_col, y='Close')
                        fig_price.update_layout(margin=dict(l=0, r=0, t=10, b=0), xaxis_title="", yaxis_title="", yaxis_tickformat=",", hovermode="x unified", xaxis=dict(showgrid=False, type=x_type), height=250)
                        fig_price.update_traces(line_color="#FF4B4B", hovertemplate="<b>%{y:,}원</b>")
                        st.plotly_chart(fig_price, use_container_width=True, config={'displayModeBar': False}, key=f"lp_{tech_result['티커']}_{key_suffix}")
                    with ch2:
                        st.caption(f"📊 거래량 & OBV ({tf})")
                        fig_vol = go.Figure()
                        fig_vol.add_trace(go.Bar(x=long_df[x_col], y=long_df['Volume'], name="거래량", marker_color="#1f77b4", hovertemplate="<b>%{y:,}주</b>"))
                        fig_vol.add_trace(go.Scatter(x=long_df[x_col], y=long_df['OBV'], name="OBV", yaxis="y2", line=dict(color="orange", width=2)))
                        fig_vol.update_layout(
                            margin=dict(l=0, r=0, t=10, b=0), xaxis=dict(showgrid=False, type=x_type), hovermode="x unified", height=250, showlegend=False,
                            yaxis=dict(title="", showgrid=False, tickformat=","), yaxis2=dict(title="", overlaying="y", side="right", showgrid=False, showticklabels=False)
                        )
                        st.plotly_chart(fig_vol, use_container_width=True, config={'displayModeBar': False}, key=f"lv_{tech_result['티커']}_{key_suffix}")
                else: st.error("데이터를 불러오지 못했습니다.")
        else:
            ch1, ch2 = st.columns(2)
            price_df = tech_result["종가 데이터"].reset_index()
            price_df['Date_Str'] = price_df['Date'].dt.strftime('%m월 %d일') 
            vol_df = tech_result["거래량 데이터"].reset_index()
            vol_df['Date_Str'] = vol_df['Date'].dt.strftime('%m월 %d일')
            with ch1:
                st.caption("📈 주가 흐름 (최근 20일)")
                fig_price = px.line(price_df, x='Date_Str', y='Close', markers=True)
                fig_price.update_layout(margin=dict(l=0, r=0, t=10, b=0), xaxis_title="", yaxis_title="", yaxis_tickformat=",", hovermode="x unified", xaxis=dict(showgrid=False, type='category'), height=220)
                fig_price.update_traces(line_color="#FF4B4B", hovertemplate="<b>%{y:,}원</b>")
                st.plotly_chart(fig_price, use_container_width=True, config={'displayModeBar': False}, key=f"p_{tech_result['티커']}_{key_suffix}")
            with ch2:
                st.caption("📊 거래량 (막대) & OBV 누적 (꺾은선)")
                fig_vol = go.Figure()
                fig_vol.add_trace(go.Bar(x=vol_df['Date_Str'], y=vol_df['Volume'], name="거래량", marker_color="#1f77b4", hovertemplate="<b>%{y:,}주</b>"))
                fig_vol.add_trace(go.Scatter(x=vol_df['Date_Str'], y=tech_result['OBV'], name="OBV", yaxis="y2", line=dict(color="orange", width=2)))
                fig_vol.update_layout(
                    margin=dict(l=0, r=0, t=10, b=0), xaxis=dict(showgrid=False, type='category'), hovermode="x unified", height=220, showlegend=False,
                    yaxis=dict(title="", showgrid=False, tickformat=","), yaxis2=dict(title="", overlaying="y", side="right", showgrid=False, showticklabels=False)
                )
                st.plotly_chart(fig_vol, use_container_width=True, config={'displayModeBar': False}, key=f"v_{tech_result['티커']}_{key_suffix}")

# 👈 [개선 2 & 3] 정렬(Sorting) 및 'AI 매수 추천 종목만 추려보기' 필터 통합 렌더링
def display_sorted_results(results_list, tab_key, show_longterm=False, api_key=""):
    if not results_list:
        st.info("조건에 부합하는 종목이 없습니다.")
        return

    st.success(f"🎯 총 {len(results_list)}개 종목 포착 완료!")
    
    # 상단 패널: 왼쪽은 정렬 라디오 버튼, 오른쪽은 AI 매수 추천 스위치
    col1, col2 = st.columns([3, 1])
    with col1:
        sort_opt = st.radio("⬇️ 결과 정렬 방식 선택", ["기본 (검색순)", "RSI 낮은순 (바닥줍기)", "RSI 높은순 (과열/돌파)", "PER 낮은순 (저평가)", "PBR 낮은순 (자산가치)"], horizontal=True, key=f"sort_radio_{tab_key}")
    with col2:
        st.write("") # 줄맞춤용 빈 공간
        ai_filter = st.toggle("🤖 AI 매수 추천(적극/분할)만 보기", key=f"ai_filter_{tab_key}")
        
    display_list = results_list.copy()
    
    # 토글을 켰을 때만 AI에게 의견을 물어보고 필터링 진행
    if ai_filter:
        if not api_key:
            st.warning("API 키를 먼저 입력해주세요.")
        else:
            with st.spinner("🤖 AI가 종목별 매수 의견을 판독하여 필터링 중입니다..."):
                filtered = []
                for res in display_list:
                    op = get_quick_ai_opinion(res['종목명'], res['현재가'], res['진입가_가이드'], res['RSI'], api_key)
                    if "매수" in op: # '적극매수' 또는 '분할매수'인 경우만 통과
                        res['AI단기'] = op
                        filtered.append(res)
                display_list = filtered
                
                if not display_list:
                    st.warning("AI가 '매수' 의견을 제시한 종목이 없습니다.")
                    return
                else:
                    st.success(f"🔥 AI 매수 추천 종목 {len(display_list)}개로 압축 완료!")

    # 정렬 실행
    def get_safe_float(val, default=9999.0):
        try:
            if pd.isna(val) or str(val).strip() in ['N/A', 'None', '', '-']: return default
            return float(str(val).replace(',', ''))
        except: return default

    if "RSI 낮은순" in sort_opt:
        sorted_res = sorted(display_list, key=lambda x: get_safe_float(x['RSI'], 100))
    elif "RSI 높은순" in sort_opt:
        sorted_res = sorted(display_list, key=lambda x: get_safe_float(x['RSI'], 0), reverse=True)
    elif "PER 낮은순" in sort_opt:
        sorted_res = sorted(display_list, key=lambda x: get_safe_float(x['PER'], 9999))
    elif "PBR 낮은순" in sort_opt:
        sorted_res = sorted(display_list, key=lambda x: get_safe_float(x['PBR'], 9999))
    else:
        sorted_res = display_list

    # 최종 렌더링
    for i, res in enumerate(sorted_res):
        draw_stock_card(res, api_key_str=api_key, is_expanded=False, key_suffix=f"{tab_key}_{i}", show_longterm_chart=show_longterm)

# ==========================================
# 4. 메인 화면 시작
# ==========================================
st.title("📈 Jaemini PRO 트레이딩 대시보드")
st.markdown("단기 스윙 매매를 위한 **수급 추적** 및 **실시간 타점 모니터링** 시스템입니다.")

macro_data = get_macro_indicators()
fg_data = get_fear_and_greed()

m_col1, m_col2, m_col3 = st.columns([1, 1, 2])

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
    if st.button("🔄 증시 데이터 리로드", type="primary", use_container_width=True): 
        get_latest_naver_news.clear()
        st.cache_data.clear()
        st.session_state.news_data = []
        st.session_state.seen_links = set()
        st.session_state.seen_titles = set()
        st.rerun()
    st.divider()
    st.header("🧠 AI 엔진 연결 상태")
    
    api_key_input = ""
    if "GEMINI_API_KEY" in st.secrets:
        val = st.secrets["GEMINI_API_KEY"]
        api_key_input = str(val) if isinstance(val, str) else str(list(val.values())[0])
        st.success("✅ 시스템 연동 완료 (정상)")
    else:
        api_key_input = st.text_input("Gemini API Key를 입력하세요", type="password")
        if api_key_input: 
            api_key_input = str(api_key_input)
            st.success("✅ 시스템 연동 완료 (정상)")

if "gainers_df" not in st.session_state:
    with st.spinner('📡 글로벌 증시 데이터를 수집하는 중입니다...'):
        df, ex_rate = get_us_top_gainers()
        st.session_state.gainers_df = df
        st.session_state.ex_rate = ex_rate

tab1, tab2, tab3, tab4, tab5, tab6, tab7, tab8, tab9, tab10, tab11 = st.tabs([
    "🔥 🇺🇸 미국 급등주 (+5% 이상)", 
    "🚀 조건 검색 스캐너", 
    "💎 장기 가치주 스캐너", 
    "🎯 국내 타점 진단", 
    "💡 AI 테마 검색", 
    "🚨 상/하한가 분석", 
    "📰 실시간 뉴스 터미널", 
    "📅 증시 캘린더", 
    "💸 자금 흐름(히트맵)", 
    "💰 배당주(TOP 60)", 
    "⭐ 내 관심종목"
])

with tab1:
    st.markdown("<br>", unsafe_allow_html=True)
    col1, col2 = st.columns([1, 1.2], gap="large")
    with col1:
        st.subheader("🔥 미국장 급등주 (+5% 이상)")
        if not st.session_state.gainers_df.empty:
            tickers_list = st.session_state.gainers_df['종목코드'].tolist()
            if api_key_input:
                with st.spinner("🤖 AI가 30개 종목의 섹터 정보를 일괄 분석 중입니다..."):
                    sector_dict = get_all_sector_info(tuple(tickers_list), api_key_input)
            else:
                sector_dict = {t: ("분석 대기", "분석 대기") for t in tickers_list}
                
            display_df = st.session_state.gainers_df.copy()
            opts = ["🔍 종목 선택"]
            for i, row in display_df.iterrows():
                sec, ind = sector_dict.get(row['종목코드'], ("분석 불가", "분석 불가"))
                opts.append(f"{row['종목코드']} ({row['기업명'].split(' / ')[-1] if ' / ' in row['기업명'] else row['기업명']}) - ({sec} / {ind})")
            st.dataframe(display_df, use_container_width=True, hide_index=True, height=400)
            sel_opt = st.selectbox("#### 🔍 분석 대상 종목 선택", opts)
            sel_tick = "N/A" if sel_opt == "🔍 종목 선택" else sel_opt.split(" ")[0]
        else: sel_tick = "N/A"; st.info("현재 +5% 이상 급등한 종목이 없습니다.")
    
    with col2:
        st.subheader("🎯 연관 테마 매칭 및 타점 진단")
        show_trading_guidelines() 
        if sel_tick != "N/A" and api_key_input:
            sec, ind = sector_dict.get(sel_tick, ("분석 불가", "분석 불가"))
            st.markdown(f"**🏷️ 섹터 정보:** `{sec}` / `{ind}`")
            with st.spinner(f"🔍 기업 개요 및 분석 중..."):
                with st.container(border=True):
                    st.markdown(f"**🏢 비즈니스 모델 요약**\n> {get_company_summary(sel_tick, api_key_input)}")
                    st.markdown(f"**📰 최근 뉴스 AI 판독**\n> {analyze_news_with_gemini(sel_tick, api_key_input)}")
            with st.spinner('✨ AI가 연관된 한국 수혜주를 샅샅이 검색하고 타점을 계산 중입니다...'):
                kor_stocks = get_ai_matched_stocks(sel_tick, sec, ind, sel_opt.split(" - ")[0], api_key_input)
                if kor_stocks:
                    st.markdown("### ✨ AI 추천 국내 수혜주 (클릭하여 타점 및 의견 확인)")
                    theme_res_list = []
                    for i, (name, code) in enumerate(kor_stocks):
                        res = analyze_technical_pattern(name, code)
                        if res: theme_res_list.append(res)
                    display_sorted_results(theme_res_list, tab_key="t1", show_longterm=False, api_key=api_key_input)
                else: st.error("❌ 연관된 국내 주식을 찾는 데 실패했습니다. 서버 연결 상태를 확인해 주세요.")

with tab2:
    st.markdown("<br>", unsafe_allow_html=True)
    st.subheader("🚀 실시간 조건 검색 스캐너 & 과거 타점 검증기")
    st.write("시장 주도주 중 상승 확률이 높은 타점에 온 종목을 초고속 스레드로 찾아내고, 과거 타점의 수익률을 검증할 수 있습니다.")
    
    with st.expander("💡 [필독] 스캐너 조건 및 승률 극대화 '황금 조합' 가이드", expanded=False):
        st.markdown("""
        **🔍 1. 개별 조건 가이드**
        * **✨ 골든크로스/정배열:** 하락/횡보를 끝내고 이제 막 상승 추세로 방향을 튼 종목 (추세 초입).
        * **✅ 20일선 눌림목:** 강하게 오르던 주식이 숨을 고르며 20일선 근처까지 내려온 안전한 반등 자리 (스윙 매매의 핵심).
        * **🔵 RSI 30 이하:** 시장 폭락이나 악재로 비이성적으로 과하게 떨어진 과매도 종목 (V자 틈새 반등 노리기).
        * **🔥 거래량 급증:** 시장의 거대한 돈(스마트 머니)이 들어온 진짜 주도주 (다른 조건과 조합하여 신뢰도를 높이는 필터 역할).
        """)
    
    col_c1, col_c2 = st.columns(2)
    with col_c1:
        cond_golden = st.checkbox("✨ 5일-20일 골든크로스 또는 정배열 초입")
        cond_pullback = st.checkbox("✅ 20일선 눌림목 (진입 타점 근접)", value=True)
    with col_c2:
        cond_rsi_bottom = st.checkbox("🔵 RSI 30 이하 (과대 낙폭/바닥권)")
        cond_vol_spike = st.checkbox("🔥 최근 거래량 급증 (세력 개입 의심)")
        
    st.markdown("#### 📊 스캔 범위 및 검증 시점 선택")
    scan_c1, scan_c2 = st.columns(2)
    with scan_c1:
        scan_limit = st.selectbox("거래대금이 많이 터진 상위 몇 개의 종목을 스캔할까요?", [50, 100, 200, 300], index=1)
    
    with scan_c2:
        offset_options = {"현재 (실시간 스캔)": 0, "3일 전 (타임머신 검증)": 3, "5일 전 (타임머신 검증)": 5, "10일 전 (타임머신 검증)": 10}
        selected_offset_label = st.selectbox("⏰ 타임머신 검증 모드 (당시 타점과 오늘 가격 비교)", list(offset_options.keys()))
        offset_days = offset_options[selected_offset_label]
        
    if st.button(f"🚀 쾌속 병렬 스캔 시작 (상위 {scan_limit}종목)", type="primary", use_container_width=True):
        with st.spinner(f"⚡ 멀티스레드 엔진을 가동하여 {scan_limit}개 종목을 고속 필터링 중입니다..."):
            targets = get_scan_targets(scan_limit)
            if not targets: st.error("종목 데이터를 불러오지 못했습니다.")
            else:
                progress_bar = st.progress(0)
                status_text = st.empty()
                found_results = []
                total = len(targets)
                completed = 0
                
                # AI 검색 로직 제거하여 속도 극대화
                def process_stock(target):
                    name, code = target
                    time.sleep(0.1) 
                    res = analyze_technical_pattern(name, code, offset_days=offset_days)
                    if res:
                        match = True
                        if cond_golden and res['배열상태'] not in ["🔥 완벽 정배열 (상승 추세)", "✨ 5-20 골든크로스"]: match = False
                        if cond_pullback and res['상태'] != "✅ 타점 근접 (분할 매수)": match = False
                        if cond_rsi_bottom and res['RSI'] > 30: match = False
                        if cond_vol_spike and res['거래량 급증'] != "🔥 거래량 터짐": match = False
                        if match: return res
                    return None
                
                with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
                    future_to_target = {executor.submit(process_stock, t): t for t in targets}
                    for future in concurrent.futures.as_completed(future_to_target):
                        res = future.result()
                        completed += 1
                        if res: found_results.append(res)
                        progress_bar.progress(completed / total)
                        status_text.text(f"⚡ 병렬 스캔 진행 중... ({completed}/{total}) - 현재 {len(found_results)}개 포착")

                status_text.text(f"✅ 초고속 스캔 완료! 총 {len(found_results)}개 종목 포착")
                st.session_state.scan_results = found_results
                st.rerun()

    st.divider()
    if st.session_state.scan_results is not None:
        display_sorted_results(st.session_state.scan_results, tab_key="t2", show_longterm=False, api_key=api_key_input)

with tab3:
    st.markdown("<br>", unsafe_allow_html=True)
    st.subheader("💎 장기 투자 가치주 & 텐배거 유망주 스캐너")
    st.write("AI가 미래 핵심 기업을 찾아내고, 병렬 재무 스캔을 통해 '진흙 속의 진주'를 초고속으로 발굴합니다.")
    
    hot_themes = get_trending_themes_with_ai(api_key_input) if api_key_input else []
    mega_trends = ["전고체 배터리", "온디바이스 AI", "자율주행/로봇", "양자컴퓨팅", "비만/치매 치료제", "우주항공(UAM)"]
    all_themes = list(dict.fromkeys(hot_themes + mega_trends))
    
    col_v1, col_v2 = st.columns([2, 1])
    with col_v1:
        selected_theme = st.selectbox("💡 미래 유망 기술 선택:", all_themes + ["✏️ 직접 입력..."])
        if selected_theme == "✏️ 직접 입력...": tech_keyword = st.text_input("직접 입력:", placeholder="예: 6G 통신")
        else: tech_keyword = selected_theme
    with col_v2:
        cap_size = st.selectbox("🏢 기업 규모 선택:", ["상관없음 (모두 스캔)", "안정적인 대형주", "폭발력 있는 중소형주"], index=0)

    val_strictness = st.radio("투자 성향 선택", [
        "💎 **[흙 속의 진주]** 수익/자산 좋고 주가는 바닥인 우량 가치주", 
        "🚀 **[성장 프리미엄]** 비싸도 기술력이 압도적인 성장주",
        "🔥 **[오직 기술력만]** 적자여도 미래만 보는 야수의 심장"
    ])
    
    if "진주" in val_strictness: max_per, max_pbr = 15.0, 1.5
    elif "성장" in val_strictness: max_per, max_pbr = 40.0, 4.0
    else: max_per, max_pbr = 9999.0, 9999.0 

    if st.button("💎 병렬 가치주 스캔 시작", type="primary", use_container_width=True):
        if not api_key_input: st.warning("API 키를 입력해주세요.")
        elif not tech_keyword: st.warning("테마를 입력해 주세요.")
        else:
            with st.spinner(f"'{tech_keyword}' 관련 기업을 전수 조사 중입니다..."):
                candidates = get_longterm_value_stocks_with_ai(tech_keyword, cap_size, api_key_input)
                if not candidates: st.error("관련 기업을 찾지 못했습니다.")
                else:
                    st.info(f"AI가 {len(candidates)}개의 후보를 찾았습니다. ⚡멀티스레드로 재무제표를 스캔합니다.")
                    progress_bar = st.progress(0)
                    status_text = st.empty()
                    value_results = []
                    total = len(candidates)
                    completed = 0
                    
                    def process_fundamental(target):
                        name, code = target
                        time.sleep(0.1) 
                        per_str, pbr_str = get_fundamentals(code)
                        try:
                            per_val = float(str(per_str).replace(',', '')) if str(per_str) not in ['N/A', 'None', ''] else 9999.0
                            pbr_val = float(str(pbr_str).replace(',', '')) if str(pbr_str) not in ['N/A', 'None', ''] else 9999.0
                            if (0 < per_val <= max_per) and (0 < pbr_val <= max_pbr):
                                return analyze_technical_pattern(name, code)
                        except: pass
                        return None

                    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
                        future_to_cand = {executor.submit(process_fundamental, c): c for c in candidates}
                        for future in concurrent.futures.as_completed(future_to_cand):
                            res = future.result()
                            completed += 1
                            if res: value_results.append(res)
                            progress_bar.progress(completed / total)
                            status_text.text(f"⚡ 병렬 재무 스캔 중... ({completed}/{total})")

                    status_text.text(f"✅ 필터링 완료! 최종 {len(value_results)}개 발굴")
                    st.session_state.value_scan_results = value_results
                    st.rerun()

    st.divider()
    if st.session_state.value_scan_results is not None:
        display_sorted_results(st.session_state.value_scan_results, tab_key="t3", show_longterm=True, api_key=api_key_input)

with tab4:
    st.markdown("<br>", unsafe_allow_html=True)
    st.subheader("🔍 국내 개별 종목 정밀 타점 진단기")
    show_trading_guidelines() 
    krx_df = get_krx_stocks()
    if not krx_df.empty:
        opts = ["🔍 검색 종목을 입력하세요."] + (krx_df['Name'].astype(str) + " (" + krx_df['Code'].astype(str) + ")").tolist()
        query = st.selectbox("👇 종목명 또는 초성을 입력하여 검색하세요:", opts)
        
        if query != "🔍 검색 종목을 입력하세요.":
            searched_name = query.rsplit(" (", 1)[0]
            searched_code = query.rsplit("(", 1)[-1].replace(")", "").strip()
            
            with st.spinner(f"📡 '{searched_name}' 타점 분석 중..."):
                res = analyze_technical_pattern(searched_name, searched_code)
            
            if res: draw_stock_card(res, api_key_str=api_key_input, is_expanded=True, key_suffix="t4")
            else: st.error("❌ 분석 불가: 데이터가 없습니다.")

with tab5:
    st.markdown("<br>", unsafe_allow_html=True)
    st.subheader("💡 테마 및 관련주 실시간 AI 발굴기")
    show_trading_guidelines() 
    st.markdown("🔥 **AI가 감지한 오늘의 실시간 주도 테마**")
    
    with st.spinner("📡 핫 테마를 스캔 중입니다..."):
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
                st.success(f"🎯 '{query}' 관련주 진단 완료!")
                theme_res_list = []
                for i, (name, code) in enumerate(theme_stocks):
                    res = analyze_technical_pattern(name, code)
                    if res: theme_res_list.append(res)
                display_sorted_results(theme_res_list, tab_key="t5", show_longterm=False, api_key=api_key_input)
            else: st.error("❌ 관련주를 찾지 못했습니다.")

with tab6:
    st.markdown("<br>", unsafe_allow_html=True)
    st.subheader("🚨 오늘의 상/하한가 및 테마 분석")
    st.write("당일 가장 강력한 자금이 몰린 상/하한가 종목을 파악하고, 주도 테마를 AI로 분석합니다.")
    
    with st.spinner("거래소 실시간 상/하한가 데이터를 수집 중입니다..."):
        upper_df, lower_df = get_limit_stocks()
        
    if api_key_input and not upper_df.empty:
        if st.button("🤖 AI 상한가 테마 즉시 분석", type="primary", use_container_width=True):
            with st.spinner("AI가 상한가 종목들의 공통 테마를 분석 중입니다..."):
                stock_list = upper_df['Name'].tolist()
                prompt = f"오늘 한국 증시에서 상한가를 기록한 종목들입니다: {stock_list}\n이 종목들이 어떤 공통된 테마나 이슈로 묶였는지 3줄 요약 분석해 주세요."
                st.success(ask_gemini(prompt, api_key_input))
        
    st.divider()
    col_u, col_l = st.columns(2)
    with col_u:
        st.markdown("### 🔴 오늘 상한가 종목")
        if upper_df.empty: st.info("현재 상한가 종목이 없습니다.")
        else:
            display_upper = upper_df.copy()
            display_upper['가격 흐름'] = display_upper.apply(lambda row: f"{int(row['PrevClose']):,}원 ➡️ {int(row['Close']):,}원 (+{row['ChagesRatio']:.2f}%)", axis=1)
            display_upper = display_upper[['Name', 'Sector', '가격 흐름', 'Amount_Ouk']]
            display_upper.columns = ['종목명', '섹터/테마', '가격 흐름 (전일➡️오늘)', '거래대금(억)']
            st.dataframe(display_upper, use_container_width=True, hide_index=True)
            
            opts_u = ["🔍 종목을 선택하세요."] + upper_df['Name'].tolist()
            sel_u = st.selectbox("상한가 종목 타점 확인:", opts_u, key="sel_u")
            if sel_u != "🔍 종목을 선택하세요.":
                with st.spinner(f"📡 '{sel_u}' 분석 중..."):
                    k_code = get_krx_stocks()[get_krx_stocks()['Name'] == sel_u]['Code'].iloc[0] if not get_krx_stocks()[get_krx_stocks()['Name'] == sel_u].empty else ""
                    if k_code:
                        res = analyze_technical_pattern(sel_u, k_code)
                        if res: draw_stock_card(res, api_key_str=api_key_input, is_expanded=True, key_suffix="t6_u")
                
    with col_l:
        st.markdown("### 🔵 오늘 하한가 종목")
        if lower_df.empty: st.info("현재 하한가 종목이 없습니다.")
        else:
            display_lower = lower_df.copy()
            display_lower['가격 흐름'] = display_lower.apply(lambda row: f"{int(row['PrevClose']):,}원 ➡️ {int(row['Close']):,}원 ({row['ChagesRatio']:.2f}%)", axis=1)
            display_lower = display_lower[['Name', 'Sector', '가격 흐름', 'Amount_Ouk']]
            display_lower.columns = ['종목명', '섹터/테마', '가격 흐름 (전일➡️오늘)', '거래대금(억)']
            st.dataframe(display_lower, use_container_width=True, hide_index=True)

with tab7:
    st.markdown("<br>", unsafe_allow_html=True)
    cols_top = st.columns([4, 1])
    cols_top[0].subheader("📰 프로 트레이더용 실시간 속보 터미널")
    if cols_top[1].button("🔄 속보 리로드", use_container_width=True): 
        get_latest_naver_news.clear()
        st.session_state.news_data = []
        st.session_state.seen_links = set()
        st.session_state.seen_titles = set()
        st.rerun()
    
    keywords_input = st.text_input("🎯 핵심 키워드 하이라이트 (쉼표 구분):", value="AI, 반도체, 데이터센터, 원전, 로봇, 바이오, 수주, 상한가, 단독")
    keywords = [k.strip() for k in keywords_input.split(",") if k.strip()]
    only_kw = st.checkbox("🔥 위 키워드가 포함된 핵심 뉴스만 보기", value=False)
    update_news_state()
    st.divider()

    if st.session_state.quick_analyze_news:
        qa_name, qa_code = st.session_state.quick_analyze_news
        st.success(f"⚡ **{qa_name}** 뉴스 감지! 즉시 타점을 진단합니다.")
        with st.spinner(f"'{qa_name}' 정밀 분석 중..."):
            res = analyze_technical_pattern(qa_name, qa_code)
            if res: draw_stock_card(res, api_key_str=api_key_input, is_expanded=True, key_suffix="news_qa")
        if st.button("닫기 ❌", key="close_qa"):
            st.session_state.quick_analyze_news = None
            st.rerun()
        st.divider()

    krx_dict = {row['Name']: row['Code'] for _, row in get_krx_stocks().iterrows() if len(str(row['Name'])) > 1}
    pinned_news, regular_news = [], []
    for news in st.session_state.news_data[:60]:
        has_kw = any(k.lower() in news['title'].lower() for k in keywords)
        if only_kw and not has_kw: continue
        if has_kw and any(kw in news['title'] for kw in ['단독', '특징주', '상한가', '수주', '최대']) and len(pinned_news) < 2:
            pinned_news.append(news)
        else: regular_news.append(news)

    if pinned_news:
        st.markdown("### 🚨 실시간 메인 헤드라인 (특징주/단독)")
        cols_pin = st.columns(len(pinned_news))
        for idx, p_news in enumerate(pinned_news):
            with cols_pin[idx]:
                with st.container(border=True):
                    st.caption(f"⏱️ {p_news['time']}")
                    st.markdown(f"#### {p_news['title']}")
                    if st.button("🤖 AI 팩트체크", key=f"pin_ai_{idx}") and api_key_input:
                        st.info(ask_gemini(f"속보 분석: {p_news['title']}\n1.팩트 2.선반영 3.전략", api_key_input))
                    st.link_button("원문 읽기 🔗", p_news['link'], use_container_width=True)
        st.markdown("---")

    good_kws = ['돌파', '최대', '흑자', '승인', '급등', '수주', '상한가', '호실적', 'MOU']
    bad_kws = ['하락', '적자', '배임', '블록딜', '급락', '횡령', '상장폐지', '주의']
    for i, news in enumerate(regular_news[:40]):
        title = news['title']
        prefix = ""
        if '단독' in title: prefix += "🚨**[단독]** "
        if '특징주' in title: prefix += "💡**[특징주]** "
        if any(kw in title for kw in good_kws): prefix += "🔴`[호재]` "
        elif any(kw in title for kw in bad_kws): prefix += "🔵`[악재]` "
        
        found_comps = []
        for name, code in krx_dict.items():
            if name in title:
                found_comps.append((name, code))
                if len(found_comps) >= 1: break
        
        with st.container(border=True):
            cols = st.columns([1, 5.5, 2, 1.5, 1])
            cols[0].markdown(f"**🕒 {news['time']}**")
            cols[1].markdown(f"{prefix}{title}")
            with cols[2]:
                for c_name, c_code in found_comps:
                    if st.button(f"🔍 {c_name} 타점보기", key=f"qa_{c_code}_{i}"):
                        st.session_state.quick_analyze_news = (c_name, c_code)
                        st.rerun()
            if cols[3].button("🤖 AI 판독", key=f"n_ai_{i}"):
                if api_key_input: st.info(ask_gemini(f"속보 분석: {title}\n1. 팩트\n2. 선반영\n3. 전략", api_key_input))
            cols[4].link_button("원문🔗", news['link'], use_container_width=True)

with tab8:
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

with tab9:
    st.markdown("<br>", unsafe_allow_html=True)
    st.subheader("💸 시장 주도주 & 자금 흐름 히트맵")
    with st.spinner("네이버 금융에서 실시간 거래대금 데이터를 긁어옵니다..."):
        t_kings = get_trading_value_kings()
        
    if not t_kings.empty:
        merged_df = t_kings.copy()
        
        merged_df['display_text'] = (
            "<span style='font-size:18px; font-weight:bold;'>" + merged_df['Name'] + "</span><br>" +
            "<span style='font-size:14px'>" + merged_df['ChagesRatio'].map("{:+.2f}%".format) + "</span><br>" +
            "<span style='font-size:13px'>" + merged_df['Amount_Ouk'].map("{:,}억".format) + "</span>"
        )
        
        finviz_colors = [
            (0.0, '#f63538'),  
            (0.45, '#802f2f'),  
            (0.5, '#414554'),  
            (0.55, '#31693d'),  
            (1.0, '#30cc5a')   
        ]
        
        fig_tree = px.treemap(
            merged_df, 
            path=[px.Constant("🔥 당일 거래대금 TOP 20"), 'Sector', 'Name'], 
            values='Amount_Ouk', 
            color='ChagesRatio', 
            color_continuous_scale=finviz_colors, 
            color_continuous_midpoint=0,
            range_color=[-30, 30], 
            custom_data=['ChagesRatio', 'Amount_Ouk', 'display_text']
        )
        
        fig_tree.update_layout(
            margin=dict(t=30, l=10, r=10, b=10), 
            height=650,
            paper_bgcolor="#111111", 
            plot_bgcolor="#111111"
        )
        
        fig_tree.update_traces(
            textinfo="text",
            texttemplate="%{customdata[2]}", 
            textfont=dict(color="white", size=15),
            hovertemplate="<b>%{label}</b><br>등락률: %{customdata[0]:+.2f}%<br>거래대금: %{customdata[1]:,}억원<extra></extra>",
            marker=dict(line=dict(width=1.5, color='#111111'))
        )
        st.plotly_chart(fig_tree, use_container_width=True)
        
        st.markdown("### 🎯 주도주 즉시 타점 진단")
        opts = ["🔍 종목을 선택하세요."] + (t_kings['Name'].astype(str) + " (" + t_kings['Code'].astype(str) + ")").tolist()
        sel_king = st.selectbox("목록에서 타점을 확인할 종목 고르기:", opts)
        
        if sel_king != "🔍 종목을 선택하세요.":
            k_name = sel_king.rsplit(" (", 1)[0]
            k_code = sel_king.rsplit("(", 1)[-1].replace(")", "").strip()
            with st.spinner(f"📡 '{k_name}'의 타점 분석 중..."):
                res = analyze_technical_pattern(k_name, k_code)
            if res: draw_stock_card(res, api_key_str=api_key_input, is_expanded=True, key_suffix="t9_map")

with tab10:
    st.markdown("<br>", unsafe_allow_html=True)
    st.subheader("💰 고배당주 & ETF 파이프라인 (TOP 60)")
    with st.spinner("야후 파이낸스에서 60개 종목의 최신 실시간 데이터를 다운로드 중입니다..."):
        div_dfs = get_dividend_portfolio()
    dt1, dt2, dt3 = st.tabs(["🇰🇷 국장 (배당주 TOP 20)", "🇺🇸 미장 (배당주 TOP 20)", "📈 배당 ETF (국내/해외 TOP 20)"])
    with dt1: st.dataframe(div_dfs["KRX"], use_container_width=True, hide_index=True)
    with dt2: st.dataframe(div_dfs["US"], use_container_width=True, hide_index=True)
    with dt3: st.dataframe(div_dfs["ETF"], use_container_width=True, hide_index=True)

with tab11:
    st.markdown("<br>", unsafe_allow_html=True)
    st.subheader("⭐ 나만의 관심종목 (Watchlist)")
    if st.button("🗑️ 관심종목 모두 지우기"):
        st.session_state.watchlist = []
        st.rerun()
        
    if not st.session_state.watchlist:
        st.info("아직 추가된 관심종목이 없습니다. 다른 탭에서 타점을 분석하고 '⭐ 관심종목 추가' 버튼을 눌러주세요.")
    else:
        for i, item in enumerate(st.session_state.watchlist):
            res = analyze_technical_pattern(item['종목명'], item['티커'])
            if res: draw_stock_card(res, api_key_str=api_key_input, is_expanded=False, key_suffix=f"wl_{i}")
