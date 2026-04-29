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
            with open(WATCHLIST_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except:
            return []
    return []

def save_watchlist(wl):
    try:
        with open(WATCHLIST_FILE, "w", encoding="utf-8") as f:
            json.dump(wl, f, ensure_ascii=False, indent=4)
    except Exception as e:
        st.error(f"관심종목 저장 실패: {e}")

# ==========================================
# 1. 초기 설정 
# ==========================================
st.set_page_config(page_title="Jaemini PRO 터미널 v5.99", layout="wide", page_icon="📈")
st_autorefresh(interval=300000, limit=None, key="news_autorefresh")

# 세션 상태 초기화 모음
for key in ['seen_links', 'seen_titles', 'news_data']:
    if key not in st.session_state:
        st.session_state[key] = set() if 'seen' in key else []

if 'watchlist' not in st.session_state:
    st.session_state.watchlist = load_watchlist()

if 'v4_chat_history' not in st.session_state:
    st.session_state.v4_chat_history = [{"role": "assistant", "content": "안녕하세요! 여의도 퀀트 비서입니다. 오늘 시장 매크로 상황이나 투자 전략에 대해 무엇이든 물어보세요."}]

now = datetime.now()
if 'smart_cal_year' not in st.session_state:
    st.session_state.smart_cal_year = now.year
if 'smart_cal_month' not in st.session_state:
    st.session_state.smart_cal_month = now.month

if 'dcf_target_ticker' not in st.session_state:
    st.session_state.dcf_target_ticker = "AAPL"
if 'dcf_target_price' not in st.session_state:
    st.session_state.dcf_target_price = 150.0
if 'dcf_target_fcf' not in st.session_state:
    st.session_state.dcf_target_fcf = 1000.0
if 'dcf_target_shares' not in st.session_state:
    st.session_state.dcf_target_shares = 100.0

if 'price_scan_results' not in st.session_state:
    st.session_state.price_scan_results = None
if 'deep_tech_query' not in st.session_state:
    st.session_state.deep_tech_query = None
if 'deep_tech_results' not in st.session_state:
    st.session_state.deep_tech_results = None
if 'deep_tech_input' not in st.session_state:
    st.session_state.deep_tech_input = ""
if 'deep_tech_brief' not in st.session_state:
    st.session_state.deep_tech_brief = None

# ==========================================
# 2. 통합 데이터 수집 & AI 함수 모음
# ==========================================
@st.cache_data(ttl=3600)
def ask_gemini(prompt, _api_key):
    if not _api_key:
        return "API 키가 필요합니다."
    try:
        genai.configure(api_key=_api_key)
        return genai.GenerativeModel('gemini-3.1-flash-lite-preview').generate_content(prompt).text
    except Exception as e: 
        return f"🚨 AI 분석 오류: {str(e)}"

def ask_gemini_vision(prompt, image_obj, _api_key):
    if not _api_key:
        return "API 키가 필요합니다."
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
    
    [현재 글로벌 매크로 및 수급 데이터] 
    VIX:{vix} / SOX:{sox} / 환율:{krw} / 美국채:{tnx} / 미급등주:{gainers_str}
    
    위 데이터를 바탕으로 다음 3가지를 마크다운으로 가독성 좋게 요약하세요. 
    1. 🇺🇸 간밤의 미 증시 요약 (2~3줄) 
    2. 🇰🇷 국내 증시 투자의견 (2~3줄) 
    3. 🎯 오늘의 픽 (주목할 섹터 1~2개와 이유)
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
    if not _api_key:
        return default_themes
    try:
        prompt = "최근 한국 증시에서 가장 자금이 많이 몰리고 상승세가 강한 주도 테마 4개만 정확히 쉼표(,)로 구분해서 단어 형태로 1줄로 출력하세요. 부연설명 절대 금지."
        res = ask_gemini(prompt, _api_key)
        valid = [t.strip() for t in res.replace('\n', '').replace('*', '').replace('-', '').replace('.', '').split(',') if t.strip()]
        return valid[:4] if len(valid) >= 4 else default_themes[:4]
    except:
        return default_themes

@st.cache_data(ttl=3600)
def get_theme_stocks_with_ai(theme_keyword, _api_key):
    if not _api_key:
        return []
    try:
        res = ask_gemini(f"테마명: '{theme_keyword}'\n이 테마와 관련된 한국 코스피/코스닥 주요 관련주 20개를 파이썬 리스트로만 답변하세요. 예: [('에코프로', '086520')]", _api_key)
        raw_list = re.findall(r"['\"]([^'\"]+)['\"]\s*,\s*['\"]([0-9]{6})['\"]", res)
        krx_df = get_krx_stocks()
        if krx_df.empty:
            return list(dict.fromkeys(raw_list))[:20]
        
        n2c = dict(zip(krx_df['Name'], krx_df['Code']))
        c2n = dict(zip(krx_df['Code'], krx_df['Name']))
        val = []
        seen = set()
        
        for name, code in raw_list:
            c_name = name.replace('(주)', '').strip()
            f_name, f_code = None, None
            if c_name in n2c:
                f_name, f_code = c_name, n2c[c_name]
            elif code in c2n:
                f_name, f_code = c2n[code], code
                
            if f_name and f_code and f_code not in seen:
                seen.add(f_code)
                val.append((f_name, f_code))
        return val[:20]
    except:
        return []

@st.cache_data(ttl=3600)
def get_longterm_value_stocks_with_ai(strategy, cap_size, _api_key):
    if not _api_key:
        return []
    try:
        prompt = f"한국 증시에서 다음 투자 전략에 부합하는 우량주 20개를 발굴하세요. -전략: {strategy} -규모: {cap_size}. 단기테마 배제. 파이썬 리스트로만 답변: [('삼성전자', '005930')]"
        res = ask_gemini(prompt, _api_key)
        raw_list = re.findall(r"['\"]([^'\"]+)['\"]\s*,\s*['\"]([0-9]{6})['\"]", res)
        krx_df = get_krx_stocks()
        if krx_df.empty:
            return list(dict.fromkeys(raw_list))[:20]
            
        n2c = dict(zip(krx_df['Name'], krx_df['Code']))
        val = []
        seen = set()
        
        for name, code in raw_list:
            c_name = name.replace('(주)', '').strip()
            if c_name in n2c and n2c[c_name] not in seen:
                seen.add(n2c[c_name])
                val.append((c_name, n2c[c_name]))
        return val[:20]
    except:
        return []

@st.cache_data(ttl=3600)
def get_macro_indicators():
    results = {}
    tickers = {"VIX": "^VIX", "美 10년물 국채": "^TNX", "필라델피아 반도체": "^SOX", "WTI 원유": "CL=F", "원/달러 환율": "KRW=X"}
    for name, ticker in tickers.items():
        try:
            df = yf.Ticker(ticker).history(period="5d")
            if not df.empty and len(df) >= 2:
                results[name] = {
                    "value": float(df['Close'].iloc[-1]), 
                    "delta": float(df['Close'].iloc[-1] - df['Close'].iloc[-2]), 
                    "prev": float(df['Close'].iloc[-2])
                }
        except:
            pass
    return results if results else None

@st.cache_data(ttl=1800)
def get_fear_and_greed():
    url = "https://production.dataviz.cnn.io/index/fearandgreed/graphdata"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Accept": "application/json",
        "Referer": "https://edition.cnn.com/"
    }
    
    try:
        res = requests.get(url, headers=headers, timeout=4)
        if res.status_code == 200:
            data = res.json()
            return {
                "score": round(data['fear_and_greed']['score']), 
                "delta": round(data['fear_and_greed']['score'] - data['fear_and_greed']['previous_close']), 
                "rating": data['fear_and_greed']['rating'].capitalize()
            }
    except:
        pass
        
    try:
        vix_df = yf.Ticker("^VIX").history(period="5d")
        if not vix_df.empty and len(vix_df) >= 2:
            vix_val = float(vix_df['Close'].iloc[-1])
            vix_prev = float(vix_df['Close'].iloc[-2])
            
            syn_score = max(0, min(100, 100 - ((vix_val - 12) / 20) * 100))
            syn_prev = max(0, min(100, 100 - ((vix_prev - 12) / 20) * 100))
            
            if syn_score >= 75: rating = "Extreme Greed"
            elif syn_score >= 55: rating = "Greed"
            elif syn_score >= 45: rating = "Neutral"
            elif syn_score >= 25: rating = "Fear"
            else: rating = "Extreme Fear"
            
            return {
                "score": round(syn_score), 
                "delta": round(syn_score - syn_prev), 
                "rating": f"{rating} (VIX 추정)"
            }
    except:
        pass
        
    return {"score": 50, "delta": 0, "rating": "데이터 수집 불가"}

@st.cache_data(ttl=3600)
def get_us_top_gainers():
    fetch_time = (datetime.utcnow() + timedelta(hours=9)).strftime("%Y-%m-%d %H:%M:%S")
    empty_df = pd.DataFrame(columns=['종목코드', '기업명', '현재가', '환산(원)', '등락률', '등락금액', '거래량'])
    try:
        response = requests.get('https://finance.yahoo.com/gainers', headers={'User-Agent': 'Mozilla/5.0'}, timeout=5)
        raw_df = pd.read_html(StringIO(response.text))[0]
        res_data = []
        for _, row in raw_df.iterrows():
            vals = row.dropna().astype(str).tolist()
            if len(vals) >= 3:
                sym = vals[0].split()[0]
                name = vals[1]
                p_str, c_str, pct_str = "", "", ""
                for val in vals[2:]:
                    if "%" in val and ("+" in val or "-" in val):
                        parts = val.split()
                        if len(parts) >= 3:
                            p_str = parts[0]
                            c_str = parts[1]
                            pct_str = parts[2].replace("(", "").replace(")", "")
                            break
                try:
                    p_val = float(re.sub(r'[^\d\.\+\-]', '', pct_str))
                except:
                    p_val = 0.0
                    
                if p_val >= 5.0:
                    res_data.append({
                        "종목코드": sym, "기업명": name, "현재가": p_str, 
                        "등락금액": c_str, "등락률": p_val
                    })
                    
        df = pd.DataFrame(res_data).sort_values('등락률', ascending=False).head(30)
        
        try:
            ex_rate = float(yf.Ticker("KRW=X").history(period="5d")['Close'].iloc[-1])
        except:
            ex_rate = 1350.0 
            
        def get_clean_korean_name(n):
            try:
                res = requests.get(f"https://translate.googleapis.com/translate_a/single?client=gtx&sl=en&tl=ko&dt=t&q={urllib.parse.quote(n)}", timeout=2)
                ko_name = res.json()[0][0][0]
                return re.sub(r'(?i)(,?\s*Inc\.|,?\s*Corp\.|,?\s*Corporation|,?\s*Ltd\.|,?\s*Holdings|\(주\))', '', ko_name).strip()
            except:
                return n
                
        df['기업명'] = df['기업명'].apply(get_clean_korean_name)
        df['환산(원)'] = df['현재가'].apply(lambda x: f"{int(float(x.replace(',', '')) * ex_rate):,}원" if x and x.replace('.', '', 1).replace(',', '').isdigit() else "-")
        df['현재가'] = df['현재가'].apply(lambda x: f"${float(x.replace(',', '')):.2f}" if x and x.replace('.', '', 1).replace(',', '').isdigit() else str(x))
        df['등락률'] = df['등락률'].apply(lambda x: f"+{x:.2f}%")
        return df, ex_rate, fetch_time
    except:
        return empty_df, 1350.0, fetch_time

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
    except:
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
    except:
        pass
    if df_list:
        return pd.concat(df_list, ignore_index=True).drop_duplicates(subset=['종목명'])
    return pd.DataFrame()

@st.cache_data(ttl=300)
def get_trading_value_kings():
    try:
        df_kpi = fetch_naver_volume(0, 1)
        df_kdq = fetch_naver_volume(1, 1)
        df = pd.concat([df_kpi, df_kdq], ignore_index=True)
        if not df.empty:
            mask = df['종목명'].str.contains('KODEX|TIGER|KBSTAR|KOSEF|ARIRANG|HANARO|ACE|스팩|ETN|선물|인버스|레버리지', na=False)
            df = df[~mask].copy()
            
            def extract_num(x):
                try:
                    return float(re.sub(r'[^\d\.\-]', '', str(x)))
                except:
                    return 0.0
                    
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
    except:
        pass
    return pd.DataFrame()

@st.cache_data(ttl=300)
def get_scan_targets(limit=50):
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
                if targets:
                    return targets
    except:
        pass
        
    try:
        krx = get_krx_stocks()
        if not krx.empty:
            mask = krx['Name'].str.contains('KODEX|TIGER|KBSTAR|KOSEF|ARIRANG|HANARO|ACE|스팩|ETN|선물|인버스|레버리지', na=False)
            krx = krx[~mask].drop_duplicates(subset=['Name'])
            return krx.head(limit)[['Name', 'Code']].values.tolist()
    except:
        pass
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
                        res_df['Code'] = ""
                        return res_df.drop_duplicates(subset=['Name'])
        except:
            pass
        return pd.DataFrame()
        
    upper_df = fetch_naver_limit("https://finance.naver.com/sise/sise_upper.naver", True)
    lower_df = fetch_naver_limit("https://finance.naver.com/sise/sise_lower.naver", False)
    
    krx = get_krx_stocks()
    if not upper_df.empty and not krx.empty:
        upper_df = pd.merge(upper_df, krx[['Name', 'Code', 'Sector']], on='Name', how='left')
        upper_df['Sector'] = upper_df['Sector'].fillna('기타')
    if not lower_df.empty and not krx.empty:
        lower_df = pd.merge(lower_df, krx[['Name', 'Code', 'Sector']], on='Name', how='left')
        lower_df['Sector'] = lower_df['Sector'].fillna('기타')
        
    return upper_df.sort_values('Amount_Ouk', ascending=False) if not upper_df.empty else upper_df, lower_df.sort_values('Amount_Ouk', ascending=False) if not lower_df.empty else lower_df

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
        except:
            pass
        return pd.DataFrame()
        
    surge_df = fetch_vol_table("https://finance.naver.com/sise/sise_quant_high.naver")
    drop_df = fetch_vol_table("https://finance.naver.com/sise/sise_quant_low.naver")
    return surge_df, drop_df

@st.cache_data(ttl=3600)
def get_market_warnings():
    def fetch_w(url):
        try:
            res = requests.get(url, headers={'User-Agent': 'Mozilla/5.0'}, timeout=5)
            tables = pd.read_html(StringIO(res.content.decode('euc-kr', errors='replace')))
            for t in tables:
                if '종목명' in t.columns:
                    df = t.dropna(subset=['종목명']).copy()
                    return df[df['종목명'] != '종목명'].dropna(axis=1, how='all').reset_index(drop=True)
        except:
            pass
        return pd.DataFrame()
        
    return fetch_w("https://finance.naver.com/sise/management.naver"), fetch_w("https://finance.naver.com/sise/investment_alert.naver")

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
                sub = dl.select_one(".articleSubject a")
                if not sub: continue
                title = sub.get_text(strip=True)
                link = "https://finance.naver.com" + sub['href'] if sub['href'].startswith("/") else sub['href']
                pub_time = ""
                wd = dl.select_one(".wdate")
                if wd:
                    rd = wd.get_text(strip=True)
                    m = re.search(r'(\d{4}-\d{2}-\d{2})\s+(\d{2}:\d{2})', rd)
                    if m:
                        if m.group(1) == (datetime.utcnow() + timedelta(hours=9)).strftime("%Y-%m-%d"):
                            pub_time = m.group(2)
                        else:
                            pub_time = f"{m.group(1)[5:].replace('-', '/')} {m.group(2)}"
                if not pub_time:
                    pub_time = (datetime.utcnow() + timedelta(hours=9)).strftime("%H:%M")
                page_articles.append({"title": title, "link": link, "time": pub_time})
            return page_articles
        except:
            return []
            
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
        for res in executor.map(fetch_page, [1, 2]):
            articles.extend(res)
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
        rows = []
        for tr in soup.find('table', {'class': 'type_1'}).find_all('tr'):
            tds = tr.find_all('td')
            if len(tds) >= 5 and tds[0].get_text(strip=True):
                ta = tds[1].find('a')
                title = ta.get_text(strip=True) if ta else tds[1].get_text(strip=True)
                link = "https://finance.naver.com/research/" + ta['href'] if ta and 'href' in ta.attrs else ""
                rows.append({
                    "종목명": tds[0].get_text(strip=True), 
                    "제목": title, 
                    "증권사": tds[2].get_text(strip=True), 
                    "작성일": tds[4].get_text(strip=True), 
                    "원문링크": link
                })
        return pd.DataFrame(rows).head(30)
    except:
        return pd.DataFrame()

@st.cache_data(ttl=86400)
def get_financial_deep_data(code):
    try:
        res = requests.get(f"https://finance.naver.com/item/main.naver?code={code}", headers={'User-Agent': 'Mozilla/5.0'}, timeout=4)
        tables = pd.read_html(StringIO(res.text))
        f_df, p_df = None, None
        for t in tables:
            st_t = str(t)
            if '매출액' in st_t and '영업이익' in st_t and f_df is None:
                f_df = t
            if 'PER' in st_t and p_df is None:
                p_df = t
        ca = BeautifulSoup(res.text, 'html.parser').select_one('.r_cmp_area .f_up em')
        return f_df, p_df, ca.text if ca else "목표가 없음"
    except:
        return None, None, "에러"

@st.cache_data(ttl=300)
def get_intraday_estimate(code):
    if not code.isdigit():
        return None
    try:
        res = requests.get(f"https://finance.naver.com/item/frgn.naver?code={code}", headers={"User-Agent": "Mozilla/5.0"}, timeout=3)
        for t in BeautifulSoup(res.text, 'html.parser').find_all('table', {'class': 'type2'}):
            if '잠정치' in t.get('summary', ''):
                for tr in t.find_all('tr'):
                    tds = tr.find_all('td')
                    if len(tds) >= 3 and tds[0].text.strip():
                        return {
                            "time": tds[0].text.strip(), 
                            "forgn": int(tds[1].text.strip().replace(',', '').replace('+', '') or 0), 
                            "inst": int(tds[2].text.strip().replace(',', '').replace('+', '') or 0)
                        }
    except:
        pass
    return None

@st.cache_data(ttl=3600)
def get_investor_trend(code):
    try:
        res = requests.get(f"https://finance.naver.com/item/frgn.naver?code={code}", headers={"User-Agent": "Mozilla/5.0"}, timeout=3)
        i_v, f_v, p_v = [], [], []
        for r in BeautifulSoup(res.text, 'html.parser').select('table.type2')[1].select('tr'):
            t = r.select('td')
            if len(t) >= 9 and t[0].text.strip():
                try:
                    i = int(t[5].text.strip().replace(',', '').replace('+', ''))
                    f = int(t[6].text.strip().replace(',', '').replace('+', ''))
                    i_v.append(i)
                    f_v.append(f)
                    p_v.append(-(i+f))
                except:
                    pass
            if len(i_v) >= 5:
                break 
                
        def calc_trend(vs):
            if not vs: return "0 (➖중립)", 0
            tot = sum(vs)
            bs, ss = 0, 0
            for v in vs:
                if v > 0: bs += 1
                else: break
            for v in vs:
                if v < 0: ss += 1
                else: break
                
            if tot > 0: d = f"🔥{bs}일 연속 매집" if bs >= 3 else "🔥매집"
            elif tot < 0: d = f"💧{ss}일 연속 매도" if ss >= 3 else "💧매도"
            else: d = "➖중립"
            return f"{'+' if tot>0 else ''}{tot:,} ({d})", bs
            
        i_s, i_k = calc_trend(i_v)
        f_s, f_k = calc_trend(f_v)
        p_s, _ = calc_trend(p_v)
        return i_s, f_s, p_s, i_k, f_k
    except:
        return "조회불가", "조회불가", "조회불가", 0, 0

@st.cache_data(ttl=3600)
def get_pension_fund_trend(code):
    try:
        res = requests.get(f"https://finance.naver.com/item/frgn.naver?code={code}", headers={"User-Agent": "Mozilla/5.0"}, timeout=3)
        sm, st, br, ct = 0, 0, False, 0
        for r in BeautifulSoup(res.text, 'html.parser').select('table.type2')[1].select('tr'):
            t = r.select('td')
            if len(t) >= 9 and t[0].text.strip():
                try:
                    v = int(t[5].text.strip().replace(',', '').replace('+', ''))
                    sm += v
                    if v > 0 and not br: st += 1
                    elif v <= 0: br = True
                    ct += 1
                except:
                    pass
            if ct >= 5:
                break
        return sm, st
    except:
        return 0, 0

@st.cache_data(ttl=3600)
def get_daily_sise_and_investor(code):
    if not code.isdigit():
        return pd.DataFrame()
    try:
        res = requests.get(f"https://finance.naver.com/item/frgn.naver?code={code}", headers={"User-Agent": "Mozilla/5.0"}, timeout=4)
        data = []
        for r in BeautifulSoup(res.text, 'html.parser').select('table.type2')[1].select('tr'):
            t = r.select('td')
            if len(t) >= 9 and t[0].text.strip():
                try:
                    f = int(t[6].text.strip().replace(',', '').replace('+', ''))
                    i = int(t[5].text.strip().replace(',', '').replace('+', ''))
                    fv = lambda v: f"🔴 +{v:,}" if v>0 else f"🔵 {v:,}" if v<0 else "0"
                    data.append({
                        "날짜": t[0].text.strip(), 
                        "종가": t[1].text.strip(), 
                        "전일비": t[2].text.strip(), 
                        "등락률": t[3].text.strip(), 
                        "외국인": fv(f), 
                        "기관": fv(i), 
                        "개인(추정)": fv(-(f+i))
                    })
                except:
                    pass
            if len(data) >= 10:
                break
        return pd.DataFrame(data)
    except:
        return pd.DataFrame()

def get_fundamentals(ticker_code):
    if str(ticker_code).isdigit():
        try:
            res = requests.get(f"https://finance.naver.com/item/main.naver?code={ticker_code}", headers={"User-Agent": "Mozilla/5.0"}, timeout=5)
            soup = BeautifulSoup(res.text, 'html.parser')
            pe = soup.select_one('#_per').text if soup.select_one('#_per') else 'N/A'
            pb = soup.select_one('#_pbr').text if soup.select_one('#_pbr') else 'N/A'
            tp = 'N/A'
            for tr in soup.find_all('tr'):
                th = tr.find('th')
                if th and '목표주가' in th.text:
                    td = tr.find('td')
                    if td:
                        ps = [int(x.replace(',', '')) for x in re.findall(r'[0-9,]+', td.get_text(separator=' ', strip=True)) if x.replace(',', '').isdigit()]
                        if ps and max(ps) > 10: tp = str(max(ps))
                    break
            return pe, pb, None, None, tp
        except:
            return 'N/A', 'N/A', None, None, 'N/A'
    else:
        try:
            i = yf.Ticker(ticker_code).info
            pe = round(i.get('trailingPE', 0), 2) if i.get('trailingPE') else 'N/A'
            pb = round(i.get('priceToBook', 0), 2) if i.get('priceToBook') else 'N/A'
            tp = i.get('targetMeanPrice', 'N/A')
            fcf = None
            try:
                cf = yf.Ticker(ticker_code).cash_flow
                if cf is not None and not cf.empty and 'Free Cash Flow' in cf.index:
                    fcf = cf.loc['Free Cash Flow'].iloc[0]
            except:
                pass
            return pe, pb, fcf, i.get('sharesOutstanding'), tp
        except:
            return 'N/A', 'N/A', None, None, 'N/A'

@st.cache_data(ttl=3600)
def get_historical_data(ticker_code, days):
    sd = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d')
    df = pd.DataFrame()
    try:
        if str(ticker_code).isdigit():
            df = fdr.DataReader(ticker_code, sd)
        else:
            df = yf.Ticker(ticker_code).history(start=sd)
        if not df.empty:
            df.index = df.index.tz_localize(None)
    except:
        pass
        
    if df.empty and str(ticker_code).isdigit():
        try: 
            df = yf.Ticker(f"{ticker_code}.KS").history(start=sd)
            if not df.empty:
                df.index = df.index.tz_localize(None)
        except:
            pass
    return df

@st.cache_data(ttl=3600)
def search_us_ticker(query):
    if not query:
        return []
    sterm = query
    if re.search('[가-힣]', query):
        try:
            url = f"https://translate.googleapis.com/translate_a/single?client=gtx&sl=ko&tl=en&dt=t&q={urllib.parse.quote(query)}"
            sterm = requests.get(url, timeout=2).json()[0][0][0]
        except:
            pass
    try:
        data = requests.get(f"https://query2.finance.yahoo.com/v1/finance/search?q={urllib.parse.quote(sterm)}&quotesCount=5", headers={'User-Agent': 'Mozilla/5.0'}, timeout=5).json()
        return [f"{q.get('symbol')} ({q.get('shortname', 'Unknown')} / {q.get('exchDisp', 'US')})" for q in data.get('quotes', []) if q.get('quoteType') in ['EQUITY', 'ETF']]
    except:
        return []

@st.cache_data(ttl=3600)
def analyze_technical_pattern(stock_name, ticker_code, offset_days=0):
    if not ticker_code: return None
    try:
        df = get_historical_data(ticker_code, 150)
        if df.empty or len(df) < 20 + offset_days: return None
        
        tdc = float(df['Close'].iloc[-1]) 
        adf = df.iloc[:-offset_days].copy() if offset_days > 0 else df.copy()
            
        adf['MA5'] = adf['Close'].rolling(5).mean()
        adf['MA20'] = adf['Close'].rolling(20).mean()
        adf['MA60'] = adf['Close'].rolling(60).mean()
        adf['Vol_MA20'] = adf['Volume'].rolling(20).mean()
        adf['Bollinger_Upper'] = adf['MA20'] + (adf['Close'].rolling(20).std() * 2)
        
        dl = adf['Close'].diff()
        adf['RSI'] = 100 - (100 / (1 + (dl.where(dl>0, 0).rolling(14).mean() / -dl.where(dl<0, 0).rolling(14).mean())))
        adf['OBV'] = (np.sign(adf['Close'].diff()) * adf['Volume']).fillna(0).cumsum()
        
        la = adf.iloc[-1]
        pr = adf.iloc[-2] if len(adf) > 1 else adf.iloc[-1]
        cp = float(la['Close']) 
        
        if pd.notna(la['MA60']) and la['MA5'] > la['MA20'] > la['MA60']:
            ast = "🔥 완벽 정배열 (상승 추세) ｜ 💡 기준: 5일선 > 20일선 > 60일선"
        elif pd.notna(la['MA60']) and la['MA5'] < la['MA20'] < la['MA60']:
            ast = "❄️ 역배열 (하락 추세) ｜ 💡 기준: 5일선 < 20일선 < 60일선"
        elif la['MA5'] > la['MA20'] and pr['MA5'] <= pr['MA20']:
            ast = "✨ 5-20 골든크로스 ｜ 💡 기준: 5일선이 20일선을 상향 돌파"
        else:
            ast = "🌀 혼조세/횡보 ｜ 💡 기준: 이평선 얽힘 (방향 탐색중)"
        
        m2 = float(la['MA20'])
        if (m2 * 0.97) <= cp <= (m2 * 1.03): stt = "✅ 타점 근접 (분할 매수)"
        elif cp > (m2 * 1.03): stt = "⚠️ 이격 과다 (눌림목 대기)"
        else: stt = "🛑 20일선 이탈 (관망)"
        
        iu = not str(ticker_code).isdigit()
        
        if iu:
            iv, fv, pv, ik, fk = "조회불가", "조회불가", "조회불가", 0, 0
            ie, psm, pst = None, 0, 0
        else:
            iv, fv, pv, ik, fk = get_investor_trend(ticker_code)
            ie = get_intraday_estimate(ticker_code) 
            psm, pst = get_pension_fund_trend(ticker_code)
            
        pe, pb, fcf, shs, tp = get_fundamentals(ticker_code)
        
        t1 = float(la['Bollinger_Upper'])
        t2 = float(adf['Close'].max())
        t2 = t2 if t2 > (t1 * 1.02) else float(t1 * 1.05)
        
        sv = "ETF/미국주식/분류없음"
        if not iu:
            k_df = get_krx_stocks()
            if not k_df.empty:
                m_s = k_df[k_df['Code'] == ticker_code]['Sector']
                if not m_s.empty and pd.notna(m_s.iloc[0]):
                    sv = str(m_s.iloc[0]).replace(" 및 공급업", "").replace(" 제조업", "").replace(" 제조 및", "").replace(" 도매업", "").replace(" 소매업", "")
        
        return {
            "종목명": stock_name, "티커": ticker_code, "섹터": sv, "현재가": cp, "상태": stt,
            "진입가_가이드": m2, "목표가1": t1, "목표가2": t2, "목표가3": float(t2 * 1.08), "손절가": m2 * 0.97,
            "거래량 급증": "🔥 거래량 터짐" if adf.iloc[-10:]['Volume'].max() > (adf.iloc[-10:]['Vol_MA20'].mean() * 2) else "평이함",
            "RSI": la['RSI'], "배열상태": ast, "기관수급": iv, "외인수급": fv, "개인수급": pv, "장중잠정수급": ie,
            "기관연속순매수": ik, "외인연속순매수": fk, "연기금추정순매수": psm, "연기금연속순매수": pst,
            "PER": pe, "PBR": pb, "FCF": fcf, "Shares": shs, "목표가_컨센서스": tp,
            "OBV": adf['OBV'].tail(20), "차트 데이터": adf.tail(20), "오늘현재가": tdc, 
            "수익률": ((tdc - cp) / cp) * 100 if offset_days > 0 and cp > 0 else 0.0, "과거검증": offset_days > 0
        }
    except: return None

@st.cache_data(ttl=3600)
def analyze_theme_trends():
    tp = {
        "반도체": "091160", "2차전지": "305720", "바이오/헬스케어": "244580", 
        "인터넷/플랫폼": "157490", "자동차/모빌리티": "091230", "금융/지주": "091220", 
        "미디어/엔터": "266360", "로봇/AI": "417270", "K-방산": "449450", 
        "조선/중공업": "139240", "원자력/전력기기": "102960", "화장품/미용": "228790", 
        "게임": "300610", "건설/인프라": "117700", "철강/소재": "117680"
    }
    res = []
    for nm, tk in tp.items():
        try:
            df = get_historical_data(tk, 250) 
            if df.empty or len(df) < 20: continue
            cp = float(df['Close'].iloc[-1])
            def gs(ds):
                p_df = df.iloc[-min(ds, len(df)):]
                sp = float(p_df['Close'].iloc[0])
                if sp == 0: return 0, 0
                return ((cp - sp) / sp) * 100, (p_df['Volume'] * p_df['Close']).sum() / 100000000
            r1, v1 = gs(20)
            r3, v3 = gs(60)
            r6, v6 = gs(120)
            res.append({"테마": nm, "1M수익률": r1, "1M거래대금": v1, "3M수익률": r3, "3M거래대금": v3, "6M수익률": r6, "6M거래대금": v6})
        except: pass
    return pd.DataFrame(res)

@st.cache_data(ttl=43200) 
def get_naver_ipo_data():
    try:
        res = requests.get("https://finance.naver.com/sise/ipo.naver", headers={'User-Agent': 'Mozilla/5.0'}, timeout=5)
        soup = BeautifulSoup(res.content.decode('euc-kr', 'replace'), 'html.parser')
        tbl = soup.find('table', class_='type_2')
        if not tbl: return pd.DataFrame()
        hl, data = [], []
        for tr in tbl.find_all('tr'):
            ths = tr.find_all('th')
            if ths and not hl: hl = [th.text.strip() for th in ths]
            tds = tr.find_all('td')
            if tds:
                r = [td.text.strip() for td in tds]
                if len(r) == len(hl) and r[0] and r[0] != '종목명': data.append(r)
        if not hl or not data: return pd.DataFrame()
        df = pd.DataFrame(data, columns=hl)
        vc = [c for c in hl if any(t in c for t in ['종목명', '현재가', '공모가', '청약일', '상장일', '주간사'])]
        return df[vc].head(15).reset_index(drop=True) if vc else df.head(15).reset_index(drop=True)
    except: return pd.DataFrame()

@st.cache_data(ttl=43200) 
def get_dividend_portfolio(ex_rate=1350.0):
    port = {
        "KRX": [
            ("088980.KS", "맥쿼리인프라", "반기", "6.2%"), ("024110.KS", "기업은행", "결산", "8.1%"), ("316140.KS", "우리금융지주", "분기", "8.5%"),
            ("033780.KS", "KT&G", "분기", "6.5%"), ("017670.KS", "SK텔레콤", "분기", "6.8%"), ("055550.KS", "신한지주", "분기", "6.0%"),
            ("086790.KS", "하나금융지주", "분기", "7.1%"), ("105560.KS", "KB금융", "분기", "5.5%"), ("138040.KS", "메리츠금융지주", "결산", "5.0%"),
            ("139130.KS", "DGB금융지주", "결산", "8.5%"), ("175330.KS", "JB금융지주", "반기", "8.8%"), ("138930.KS", "BNK금융지주", "결산", "8.6%"),
            ("016360.KS", "삼성증권", "결산", "7.5%"), ("005940.KS", "NH투자증권", "결산", "7.4%"), ("051600.KS", "한전KPS", "결산", "6.0%"),
            ("030200.KS", "KT", "분기", "6.0%"), ("000815.KS", "삼성화재우", "결산", "7.0%"), ("053800.KS", "현대차2우B", "분기", "6.8%"),
            ("030000.KS", "제일기획", "결산", "6.0%"), ("040420.KS", "정상제이엘에스", "결산", "6.5%"), ("010950.KS", "S-Oil", "결산", "5.5%"),
            ("005935.KS", "삼성전자우", "분기", "2.8%"), ("005490.KS", "POSCO홀딩스", "분기", "4.8%"), ("071050.KS", "한국금융지주", "결산", "6.0%"),
            ("003540.KS", "대신증권", "결산", "8.0%"), ("039490.KS", "키움증권", "결산", "4.5%"), ("005830.KS", "DB손해보험", "결산", "5.5%"),
            ("001450.KS", "현대해상", "결산", "6.0%"), ("000810.KS", "삼성생명", "결산", "5.0%"), ("003690.KS", "코리안리", "결산", "5.5%")
        ],
        "US": [
            ("O", "Realty Income", "월배당", "5.8%"), ("MO", "Altria Group", "분기", "9.2%"), ("VZ", "Verizon", "분기", "6.2%"),
            ("T", "AT&T", "분기", "6.1%"), ("PM", "Philip Morris", "분기", "5.2%"), ("KO", "Coca-Cola", "분기", "3.2%"),
            ("PEP", "PepsiCo", "분기", "3.0%"), ("JNJ", "Johnson & Johnson", "분기", "3.1%"), ("PG", "Procter & Gamble", "분기", "2.5%"),
            ("ABBV", "AbbVie", "분기", "4.0%"), ("PFE", "Pfizer", "분기", "5.8%"), ("CVX", "Chevron", "분기", "4.2%"),
            ("XOM", "Exxon Mobil", "분기", "3.3%"), ("MMM", "3M", "분기", "6.0%"), ("IBM", "IBM", "분기", "3.8%"),
            ("ENB", "Enbridge", "분기", "7.2%"), ("WPC", "W. P. Carey", "분기", "6.3%"), ("MAIN", "Main Street", "월배당", "6.2%"),
            ("ARCC", "Ares Capital", "분기", "9.3%"), ("KMI", "Kinder Morgan", "분기", "6.2%"), ("CSCO", "Cisco Systems", "분기", "3.2%"),
            ("HD", "Home Depot", "분기", "2.8%"), ("MRK", "Merck", "분기", "2.8%"), ("MCD", "McDonald's", "분기", "2.2%"),
            ("WMT", "Walmart", "분기", "1.8%"), ("TGT", "Target", "분기", "2.8%"), ("CAT", "Caterpillar", "분기", "1.8%"),
            ("LOW", "Lowe's", "분기", "1.8%"), ("SBUX", "Starbucks", "분기", "2.8%"), ("CL", "Colgate-Palmolive", "분기", "2.2%")
        ],
        "ETF": [
            ("SCHD", "US SCHD (고배당)", "분기", "3.6%"), ("JEPI", "US JEPI (프리미엄)", "월배당", "7.5%"), ("JEPQ", "US JEPQ (프리미엄)", "월배당", "9.0%"),
            ("VYM", "US VYM (고배당)", "분기", "3.0%"), ("SPYD", "US SPYD (S&P500 고배당)", "분기", "4.8%"), ("DGRO", "US DGRO (배당성장)", "분기", "2.4%"),
            ("QYLD", "US QYLD (커버드콜)", "월배당", "11.5%"), ("XYLD", "US XYLD (S&P 커버드콜)", "월배당", "9.5%"), ("RYLD", "US RYLD (러셀 커버드콜)", "월배당", "12.0%"),
            ("DIVO", "US DIVO (배당+옵션)", "월배당", "4.8%"), ("VNQ", "US VNQ (리츠)", "분기", "4.2%"), ("VIG", "US VIG (배당성장)", "분기", "2.0%"),
            ("NOBL", "US NOBL (배당귀족)", "분기", "2.2%"), ("SDY", "US SDY (배당귀족)", "분기", "2.8%"), ("HDV", "US HDV (핵심배당)", "분기", "3.8%"),
            ("PEY", "US PEY (고배당)", "월배당", "4.8%"), ("DHS", "US DHS (고배당)", "월배당", "3.8%"), ("DVY", "US DVY (우량배당)", "분기", "3.8%"),
            ("FVD", "US FVD (가치배당)", "분기", "2.2%"), ("SPHD", "US SPHD (저변동 고배당)", "월배당", "4.2%"), ("DIV", "US DIV (글로벌 배당)", "월배당", "6.2%"),
            ("458730.KS", "TIGER 미국배당다우존스", "월배당", "3.8%"), ("161510.KS", "ARIRANG 고배당주", "결산", "6.5%"), ("458760.KS", "TIGER 미국배당+7%", "월배당", "10.5%"),
            ("448550.KS", "ACE 미국배당다우존스", "월배당", "3.8%"), ("466950.KS", "KODEX 미국배당프리미엄", "월배당", "7.5%"), ("329200.KS", "TIGER 부동산인프라", "분기", "7.0%"),
            ("091220.KS", "KODEX 은행", "결산", "6.5%"), ("211560.KS", "TIGER 배당성장", "분기", "4.5%"), ("271560.KS", "ARIRANG 미국고배당", "분기", "4.0%")
        ]
    }
    
    try:
        tickers_to_fetch = [t[0] for cat in port.values() for t in cat]
        d = yf.download(tickers_to_fetch, period="5d", progress=False)
        cd = d['Close'] if 'Close' in d else pd.DataFrame()
    except:
        cd = pd.DataFrame()
        
    res = {"KRX": [], "US": [], "ETF": []}
    for c, stks in port.items():
        for tk, nm, prd, ey in stks:
            pv = None
            if tk in cd.columns and not cd[tk].dropna().empty:
                pv = float(cd[tk].dropna().iloc[-1])
                
            ps, ds = "조회 지연", ey
            if pv:
                ps, kp = (f"{int(pv):,}원", pv) if ".KS" in tk else (f"${pv:,.2f}", pv * ex_rate)
                try:
                    pcts = [float(x) for x in re.findall(r"[\d\.]+", ey)]
                    if len(pcts) >= 2: ds = f"{ey} (약 {int(kp*(pcts[0]/100)):,}~{int(kp*(pcts[1]/100)):,}원)"
                    elif len(pcts) == 1: ds = f"{ey} (약 {int(kp*(pcts[0]/100)):,}원)"
                except: pass
            res[c].append({"티커/코드": tk.replace(".KS", ""), "종목명": nm, "현재가": ps, "배당수익률(예상)": ds, "배당주기": prd})
            
    return {k: pd.DataFrame(v) for k, v in res.items()}

@st.cache_data(ttl=86400)
def get_us_sector_etfs():
    secs = {
        "반도체 (SOXX)": "SOXX", "기술주 (XLK)": "XLK", "소비재 (XLY)": "XLY", 
        "헬스케어 (XLV)": "XLV", "금융 (XLF)": "XLF", "에너지 (XLE)": "XLE", "산업재 (XLI)": "XLI"
    }
    res = []
    try:
        d = yf.download(list(secs.values()), period="5d", progress=False)
        cd = d['Close'] if 'Close' in d else pd.DataFrame()
        for nm, tk in secs.items():
            if tk in cd.columns and len(cd[tk].dropna()) >= 2:
                cls = cd[tk].dropna()
                res.append({
                    "섹터": nm, 
                    "등락률": float((cls.iloc[-1] - cls.iloc[-2]) / cls.iloc[-2] * 100), 
                    "종가": float(cls.iloc[-1])
                })
        if res:
            return pd.DataFrame(res).sort_values("등락률", ascending=False)
    except: pass
    return pd.DataFrame()

@st.cache_data(ttl=86400)
def get_nps_holdings_mock():
    return pd.DataFrame([
        {"종목명": "삼성전자", "티커": "005930", "보유비중": "7.52%", "최근변동": "유지"}, 
        {"종목명": "SK하이닉스", "티커": "000660", "보유비중": "8.12%", "최근변동": "확대"},
        {"종목명": "현대차", "티커": "005380", "보유비중": "7.35%", "최근변동": "확대"}, 
        {"종목명": "NAVER", "티커": "035420", "보유비중": "8.99%", "최근변동": "유지"},
        {"종목명": "카카오", "티커": "035720", "보유비중": "5.41%", "최근변동": "축소"}, 
        {"종목명": "LG에너지솔루션", "티커": "373220", "보유비중": "5.01%", "최근변동": "유지"},
        {"종목명": "POSCO홀딩스", "티커": "005490", "보유비중": "6.71%", "최근변동": "유지"}, 
        {"종목명": "셀트리온", "티커": "068270", "보유비중": "6.22%", "최근변동": "확대"},
        {"종목명": "삼성SDI", "티커": "006400", "보유비중": "8.34%", "최근변동": "축소"}, 
        {"종목명": "LG화학", "티커": "051910", "보유비중": "7.15%", "최근변동": "유지"}
    ])

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
        if is_us: return f"{'+' if p>0 and delta else ''}${p:,.2f}"
        return f"{'+' if p>0 and delta else ''}{int(p):,}원"
            
    if is_us:
        base_info = f"(진단: {tech_result['상태']} ｜ 진단: {align_status_short} ｜ RSI: {tech_result['RSI']:.1f})"
    else:
        base_info = f"(진단: {tech_result['상태']} ｜ 진단: {align_status_short} ｜ 외인: {f_trend} ｜ 기관: {i_trend} ｜ RSI: {tech_result['RSI']:.1f})"
        
    expander_title = f"{status_emoji} {tech_result['종목명']} / {sector_info} / {fmt_price(tech_result['현재가'])} ｜ {base_info}"
    
    with st.expander(expander_title, expanded=is_expanded):
        if tech_result.get('과거검증'):
            pnl = tech_result['수익률']
            color = "#ff4b4b" if pnl > 0 else "#1f77b4"
            bg_color = "rgba(255, 75, 75, 0.1)" if pnl > 0 else "rgba(31, 119, 180, 0.1)"
            st.markdown(f"""
            <div style="background-color: {bg_color}; padding: 15px; border-radius: 10px; margin-bottom: 15px; border: 1px solid {color};">
                <h3 style="margin:0; color: {color};">⏰ 타임머신 검증 결과</h3>
                <p style="margin:5px 0 0 0; font-size: 16px;">
                    스캔 당시 가격 <b>{fmt_price(tech_result['현재가'])}</b> ➡️ 오늘 현재 가격 <b>{fmt_price(tech_result['오늘현재가'])}</b> 
                    <span style="font-size: 20px; font-weight: bold; color: {color};">({pnl:+.2f}%)</span>
                </p>
            </div>
            """, unsafe_allow_html=True)
            
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
        if str(cons_text).replace('.', '', 1).replace('-', '').isdigit():
            cons_val = float(str(cons_text))
            c6.metric("🏦 증권가 목표가", fmt_price(cons_val), fmt_price(cons_val - curr, True) + " (괴리)", delta_color="normal")
        else:
            c6.metric("🏦 증권가 목표가", "목표가 없음")
            
        c7.metric("📊 RSI (상대강도)", f"{tech_result['RSI']:.1f}", "🔴 과열" if tech_result['RSI'] >= 70 else "🔵 바닥" if tech_result['RSI'] <= 30 else "⚪ 보통", delta_color="inverse" if tech_result['RSI'] >= 70 else "normal")
        
        with c8:
            if not is_us:
                st.markdown(f"🕵️ **당시 수급 동향 (5일 누적)**<br>**외국인:** `{tech_result['외인수급']}` ｜ **기관:** `{tech_result['기관수급']}`", unsafe_allow_html=True)
                if tech_result.get('장중잠정수급'):
                    id_data = tech_result['장중잠정수급']
                    f_val_str = f"🔥+{id_data['forgn']:,}" if id_data['forgn'] > 0 else f"💧{id_data['forgn']:,}"
                    i_val_str = f"🔥+{id_data['inst']:,}" if id_data['inst'] > 0 else f"💧{id_data['inst']:,}"
                    st.markdown(f"⚡ **오늘 장중 실시간 수급 (잠정)**<br>외인 `{f_val_str}` ｜ 기관 `{i_val_str}` `({id_data['time']} 기준)`", unsafe_allow_html=True)
            else:
                st.markdown(f"🏢 **핵심 펀더멘털 (TTM)**<br>**PER:** `{tech_result.get('PER', 'N/A')}` ｜ **PBR:** `{tech_result.get('PBR', 'N/A')}`", unsafe_allow_html=True)
        
        if api_key_str:
            st.markdown("<br>", unsafe_allow_html=True)
            ai_btn_key = f"ai_btn_{tech_result['티커']}_{key_suffix}"
            ai_res_key = f"ai_res_{ai_btn_key}"
            
            if st.button(f"🤖 '{tech_result['종목명']}' AI 딥다이브 정밀 분석", key=ai_btn_key):
                st.session_state[ai_res_key] = "loading"
                
            if st.session_state.get(ai_res_key):
                if st.session_state[ai_res_key] == "loading":
                    with st.spinner("AI가 분석 중입니다..."):
                        if str(tech_result['티커']).isdigit():
                            fin_df, peer_df, cons = get_financial_deep_data(tech_result['티커'])
                            fin_text = fin_df.to_string() if fin_df is not None and not fin_df.empty else "재무 데이터 없음"
                            peer_text = peer_df.to_string() if peer_df is not None and not peer_df.empty else "비교 데이터 없음"
                            prompt = f"당신은 여의도 퀀트 애널리스트입니다. '{tech_result['종목명']}' 분석 리포트를 마크다운으로 작성하세요.\n[기술적 지표 및 수급]\n- 현재가: {fmt_price(curr)}, 20일선: {fmt_price(tech_result['진입가_가이드'])} (상태: {tech_result['상태']})\n- RSI: {tech_result['RSI']:.1f}, 추세: {tech_result['배열상태']}\n- 수급: 외인 {tech_result['외인수급']}, 기관 {tech_result['기관수급']}\n[목표가 컨센서스]: {cons}\n[재무제표 요약]\n{fin_text[:1500]}\n[경쟁사 비교]\n{peer_text[:1000]}\n1. 기술적 타점 & 수급 분석\n2. 실적 트렌드 & 밸류에이션\n3. 단기 매매 의견 및 목표가\n4. 3줄 요약"
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
        
        tf = st.radio("📅 차트 기간 선택", ["1개월", "3개월", "1년"], horizontal=True, key=f"tf_{key_suffix}")
        with st.spinner(f"{tf} 차트 데이터 불러오는 중..."):
            days_dict = {"1개월": 30, "3개월": 90, "1년": 365}
            long_df = get_historical_data(tech_result['티커'], days_dict[tf])
            if not long_df.empty:
                long_df = long_df.reset_index()
                long_df['OBV'] = (np.sign(long_df['Close'].diff()) * long_df['Volume']).fillna(0).cumsum()
                long_df['MA20'] = long_df['Close'].rolling(window=20).mean()
                long_df['Std_20'] = long_df['Close'].rolling(window=20).std()
                long_df['Bollinger_Upper'] = long_df['MA20'] + (long_df['Std_20'] * 2)
                
                x_col, x_type = ('Date_Str', 'category') if tf in ["1개월", "3개월"] else ('Date', 'date')
                if tf in ["1개월", "3개월"]:
                    long_df['Date_Str'] = long_df['Date'].dt.strftime('%m월 %d일')
                
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
                    else:
                        st.caption("수급 데이터를 제공하지 않는 종목입니다.")
            else:
                st.error("데이터를 불러오지 못했습니다.")

def display_sorted_results(results_list, tab_key, api_key=""):
    if not results_list:
        st.info("조건에 부합하는 종목이 없습니다.")
        return
    st.success(f"🎯 총 {len(results_list)}개 종목 포착 완료!")
    sort_opt = st.radio("⬇️ 결과 정렬 방식", ["기본 (검색순)", "RSI 낮은순 (바닥줍기)", "연기금 순매수 긴 순서"], horizontal=True, key=f"sort_radio_{tab_key}")
    display_list = results_list.copy()
    
    if "RSI 낮은순" in sort_opt:
        display_list.sort(key=lambda x: x['RSI'])
    elif "연기금 순매수 긴 순서" in sort_opt:
        display_list.sort(key=lambda x: x.get('연기금연속순매수', 0), reverse=True)

    for i, res in enumerate(display_list):
        draw_stock_card(res, api_key_str=api_key, is_expanded=False, key_suffix=f"{tab_key}_{i}")
        # 파트 2 시작 (파트 1 아랫줄에 이어서 붙여넣기)
elif selected_menu == "📅 IPO / 증시 일정":
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
        st.write("> **💡 핵심 전략:** 한국 시장(매월 2번째 목요일)과 미국 시장(매월 3번째 금요일)의 파생상품 만기일이 겹치는 구간의 수급 변동성을 하나의 달력에서 직관적으로 파악합니다.")
        
        cc1, cc2, cc3 = st.columns([1, 8, 1])
        with cc1:
            if st.button("◀ 이전 달", use_container_width=True, key="us_prev"):
                st.session_state.smart_cal_month -= 1
                if st.session_state.smart_cal_month == 0:
                    st.session_state.smart_cal_month = 12
                    st.session_state.smart_cal_year -= 1
                st.rerun()
        with cc2:
            st.markdown(f"<h3 style='text-align: center; margin:0;'>{st.session_state.smart_cal_year}년 {st.session_state.smart_cal_month}월</h3>", unsafe_allow_html=True)
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
                if day == 0:
                    html_parts.append("<div class='cal-cell' style='background:#fafafa;'></div>")
                else:
                    events = ""
                    if day == tax_day: events += "<div class='evt-us-red'>🔴 🇺🇸세금납부일(하락압력)</div>"
                    
                    if i == calendar.MONDAY: events += "<div class='evt-kr-blue'>🔹 🇰🇷위클리 만기(수급재편)</div>"
                    elif i == calendar.THURSDAY:
                        if day == kr_opex_day:
                            label = "🔥 🇰🇷네마녀의 날" if kr_is_quadruple else "🔴 🇰🇷옵션만기일"
                            events += f"<div class='evt-kr-red'>{label}(수급극대)</div>"
                        else: events += "<div class='evt-kr-blue'>🔹 🇰🇷위클리 만기(오후변동)</div>"
                    elif i == calendar.FRIDAY and day == kr_opex_day + 1:
                        events += "<div class='evt-kr-green'>🟢 🇰🇷수급 되돌림(추세복귀)</div>"

                    if day in us_opex_week_days:
                        if day == us_opex_day: events += "<div class='evt-us-red'>🔴 🇺🇸옵션만기(변동성폭발)</div>"
                        else: events += "<div class='evt-us-warn'>⚠️ 🇺🇸만기주간(핀닝/하락)</div>"
                    elif day in us_macro_days and day != tax_day:
                        events += "<div class='evt-us-warn'>⚠️ 🇺🇸매크로 경계(관망)</div>"
                    
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
                st.success(ask_gemini(f"다음 상장 일정: {ipo_df[['종목명', '상장일']].to_string()}\n따상 가능성 높은 1~2개 꼽고 이유 3줄 평가.", api_key_input))
        else: 
            st.error("❌ 현재 예정된 신규 상장(IPO) 일정이 없거나, 거래소 데이터를 불러올 수 없습니다.")

elif selected_menu == "💰 배당 파이프라인 (TOP 300)":
    st.subheader("💰 고배당주 & ETF 파이프라인 (TOP 300)")
    with st.spinner("야후 파이낸스 서버에서 실시간 배당 데이터를 다운로드 중입니다..."): 
        div_dfs = get_dividend_portfolio(st.session_state.get('ex_rate', 1350.0))
    
    if div_dfs["KRX"].empty and div_dfs["US"].empty:
        st.error("🚨 야후 파이낸스(Yahoo Finance)에서 배당 데이터를 가져오는 데 실패했습니다. 통신 오류이거나 야후 서버의 접근 차단일 수 있습니다.")
    else:
        sort_opt = st.radio("⬇ 정렬 기준", ["기본 (분류순)", "배당수익률 높은순", "현재가 높은순", "현재가 낮은순"], horizontal=True)
        
        def extract_val(val_str, is_yield=False):
            try:
                if is_yield:
                    nums = re.findall(r"[\d\.]+", str(val_str).split('(')[0])
                    return float(nums[-1]) if nums else 0.0
                else:
                    if val_str == "조회 지연": return 0.0
                    return float(str(val_str).replace('$', '').replace('원', '').replace(',', '').strip())
            except:
                return 0.0

        def apply_sort(df, opt):
            if df.empty: return df
            temp_df = df.copy()
            if opt == "배당수익률 높은순":
                temp_df['__sort'] = temp_df['배당수익률(예상)'].apply(lambda x: extract_val(x, True))
                return temp_df.sort_values('__sort', ascending=False).drop(columns=['__sort'])
            elif opt == "현재가 높은순":
                temp_df['__sort'] = temp_df['현재가'].apply(lambda x: extract_val(x, False))
                return temp_df.sort_values('__sort', ascending=False).drop(columns=['__sort'])
            elif opt == "현재가 낮은순":
                temp_df['__sort'] = temp_df['현재가'].apply(lambda x: extract_val(x, False))
                valid = temp_df[temp_df['__sort'] > 0].sort_values('__sort', ascending=True)
                invalid = temp_df[temp_df['__sort'] == 0]
                return pd.concat([valid, invalid]).drop(columns=['__sort'])
            return temp_df

        dt1, dt2, dt3 = st.tabs(["🇰🇷 국장 TOP 100", "🇺🇸 미장 TOP 100", "📈 배당 ETF TOP 100"])
        with dt1: st.dataframe(apply_sort(div_dfs["KRX"], sort_opt), use_container_width=True, hide_index=True)
        with dt2: st.dataframe(apply_sort(div_dfs["US"], sort_opt), use_container_width=True, hide_index=True)
        with dt3: st.dataframe(apply_sort(div_dfs["ETF"], sort_opt), use_container_width=True, hide_index=True)

elif selected_menu == "📊 글로벌 ETF 분석":
    st.subheader("📊 글로벌/국내 핵심 ETF & 포트폴리오 분석")
    st.write("주도 섹터와 대표 지수를 추종하는 국내외 핵심 ETF의 타점을 진단하고 AI 분석을 받아보세요.")
    
    etf_categories = {
        "📈 글로벌/국내 지수 대표": [
            ("SPY", "SPDR S&P 500"), ("QQQ", "Invesco QQQ (나스닥)"),
            ("069500", "KODEX 200"), ("232080", "TIGER 코스닥150"),
            ("360750", "TIGER 미국S&P500"), ("379800", "KODEX 미국나스닥100TR")
        ],
        "🚀 반도체 & 딥테크": [
            ("SOXX", "iShares Semiconductor"), ("XLK", "Technology Select Sector"),
            ("091160", "KODEX 반도체"), ("381180", "TIGER 미국필라델피아반도체나스닥"),
            ("446770", "TIGER 글로벌AI액티브")
        ],
        "💰 고배당 & 커버드콜": [
            ("SCHD", "Schwab US Dividend Equity"), ("JEPI", "JPMorgan Equity Premium Income"),
            ("458730", "TIGER 미국배당다우존스"), ("161510", "ARIRANG 고배당주"),
            ("466950", "KODEX 미국배당프리미엄액티브")
        ],
        "🛡️ 채권 & 방어주": [
            ("TLT", "iShares 20+ Year Treasury Bond"), ("GLD", "SPDR Gold Shares"),
            ("304660", "KODEX 미국채울트라30년선물(H)"), ("329200", "TIGER 부동산인프라고배당")
        ],
        "🧬 2차전지 & 바이오": [
            ("XLV", "Health Care Select Sector"),
            ("305720", "KODEX 2차전지산업"), ("244580", "KODEX 바이오")
        ]
    }
    
    c_cat, c_etf = st.columns([1, 1], gap="medium")
    with c_cat: selected_category = st.selectbox("📂 ETF 카테고리 선택:", list(etf_categories.keys()))
    etf_opts = ["🔍 분석할 ETF를 선택하세요."] + [f"{ticker} ({name})" for ticker, name in etf_categories[selected_category]]
    with c_etf: selected_etf_str = st.selectbox("🔍 분석할 ETF 선택:", etf_opts)
    
    st.divider()
    if selected_etf_str != "🔍 분석할 ETF를 선택하세요.":
        selected_ticker = selected_etf_str.split(" ")[0]
        with st.spinner(f"📡 '{selected_ticker}' 차트 및 기술적 지표 불러오는 중..."):
            try:
                clean_ticker = selected_ticker.replace(".KS", "")
                res = analyze_technical_pattern(selected_etf_str.split(" (")[1].replace(")", ""), clean_ticker)
                if res: 
                    draw_stock_card(res, api_key_str=api_key_input, is_expanded=True)
                else: 
                    st.error(f"❌ '{selected_ticker}' 데이터를 불러오지 못했습니다. (네트워크 오류 또는 지원 중단된 티커)")
            except Exception as e:
                st.error(f"❌ '{selected_ticker}' 분석 중 시스템 오류 발생: {str(e)}")

elif selected_menu == "⭐ 내 관심종목":
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
                    if res:
                        draw_stock_card(res, api_key_str=api_key_input, is_expanded=False, key_suffix=f"wl_{i}")
                    else:
                        st.error(f"❌ '{item['종목명']}' ({item['티커']}) 데이터를 불러오지 못했습니다. (일시적인 통신 오류이거나 상장폐지/티커변경일 수 있습니다.)")
                except Exception as e:
                    st.error(f"❌ '{item['종목명']}' 데이터 분석 중 치명적 오류 발생: {str(e)}")

elif selected_menu == "⚖️ 워런 버핏 퀀트 계산기":
    st.markdown("## ⚖️ 워런 버핏식 가치투자 퀀트 계산기")
    st.write("버핏의 투자 철학(ROE, 현금흐름, 경제적 해자, 안전마진)을 수치화하여 기업의 진짜 가치를 평가합니다.")
    
    b_tab1, b_tab2, b_tab3 = st.tabs(["📊 적정 주가 계산기 (DCF 모델)", "📈 버핏 지수 & 72의 법칙", "🔍 퀀트 스크리닝 가이드"])
    
    with b_tab1:
        st.markdown("### 📊 잉여현금흐름(FCF) 기반 내재가치 계산기")
        st.caption("기업이 벌어들일 미래의 잉여현금흐름을 현재 가치로 할인하여 이론적인 적정 주가를 산출합니다. 야후 파이낸스 연동을 통해 기본값이 채워집니다.")
        
        market_choice_dcf = st.radio("시장 선택 (가치평가)", ["🇰🇷 국내 주식", "🇺🇸 미국 주식"], horizontal=True, key="dcf_market")
        
        selected_dcf_ticker = None
        selected_dcf_name = ""
        is_us_dcf = (market_choice_dcf == "🇺🇸 미국 주식")
        
        if not is_us_dcf:
            krx_df = get_krx_stocks()
            if not krx_df.empty:
                opts = ["🔍 평가할 국내 종목을 선택하세요."] + (krx_df['Name'].astype(str) + " (" + krx_df['Code'].astype(str) + ")").tolist()
                query = st.selectbox("👇 종목명 검색:", opts, key="dcf_kr_search")
                if query != "🔍 평가할 국내 종목을 선택하세요.":
                    selected_dcf_name = query.rsplit(" (", 1)[0]
                    selected_dcf_ticker = query.rsplit("(", 1)[-1].replace(")", "").strip()
        else:
            us_query = st.text_input("👇 미국 주식 종목명(한/영) 또는 티커 (예: AAPL):", key="dcf_us_input")
            if us_query:
                with st.spinner("검색 중..."):
                    us_results = search_us_ticker(us_query)
                if us_results:
                    sel_us_opt = st.selectbox("🎯 정확한 종목 선택:", ["선택하세요"] + us_results, key="dcf_us_select")
                    if sel_us_opt != "선택하세요":
                        selected_dcf_ticker = sel_us_opt.split(" ")[0]
                        selected_dcf_name = sel_us_opt.split(" (")[1].split(" /")[0]
        
        def_price = st.session_state.dcf_target_price
        def_fcf = st.session_state.dcf_target_fcf
        def_shares = st.session_state.dcf_target_shares
        
        if selected_dcf_ticker and selected_dcf_ticker != st.session_state.dcf_target_ticker:
            with st.spinner("재무 데이터 연동 중..."):
                hist_df = get_historical_data(selected_dcf_ticker, 10)
                if not hist_df.empty:
                    def_price = float(hist_df['Close'].iloc[-1])
                    
                yf_ticker = selected_dcf_ticker if is_us_dcf else f"{selected_dcf_ticker}.KS"
                try:
                    t_obj = yf.Ticker(yf_ticker)
                    info = t_obj.info
                    shares = info.get('sharesOutstanding')
                    if shares:
                        def_shares = shares / 1000000 if is_us_dcf else shares / 10000
                        
                    cf = t_obj.cash_flow
                    if cf is not None and not cf.empty and 'Free Cash Flow' in cf.index:
                        fcf_raw = cf.loc['Free Cash Flow'].iloc[0]
                        if pd.notna(fcf_raw):
                            def_fcf = fcf_raw / 1000000 if is_us_dcf else fcf_raw / 100000000
                except: pass
                
                st.session_state.dcf_target_ticker = selected_dcf_ticker
                st.session_state.dcf_target_price = def_price
                st.session_state.dcf_target_shares = def_shares
                st.session_state.dcf_target_fcf = def_fcf
                
            st.success(f"✅ **{selected_dcf_name} ({selected_dcf_ticker})** 재무 데이터 기본값 세팅 완료!")
            
        with st.container(border=True):
            c1, c2, c3 = st.columns(3)
            with c1:
                st.markdown("**[기업 기본 정보]**")
                unit_fcf = "백만$" if is_us_dcf else "억원"
                unit_shares = "백만 주" if is_us_dcf else "만 주"
                unit_price = "달러" if is_us_dcf else "원"
                
                current_fcf = st.number_input(f"올해 예상 FCF ({unit_fcf})", value=float(def_fcf), step=10.0, format="%.2f")
                shares_out = st.number_input(f"유통 주식수 ({unit_shares})", value=float(def_shares), step=10.0, format="%.2f")
                current_price = st.number_input(f"현재 주가 ({unit_price})", value=float(def_price), step=1.0, format="%.2f")
            with c2:
                st.markdown("**[성장성 가정]**")
                growth_rate = st.slider("향후 5년 연평균 예상 성장률 (%)", min_value=1, max_value=50, value=10)
                terminal_rate = st.slider("5년 이후 영구 성장률 (%)", min_value=1, max_value=5, value=2)
            with c3:
                st.markdown("**[할인율 가정]**")
                discount_rate = st.slider("할인율 (요구수익률, %)", min_value=5, max_value=20, value=10)
            
            st.divider()
            if st.button("📈 기업 내재가치 산출하기", type="primary", use_container_width=True):
                dcf_val = 0
                cf = current_fcf
                
                for i in range(1, 6):
                    cf = cf * (1 + growth_rate/100)
                    dcf_val += cf / ((1 + discount_rate/100)**i)
                
                if discount_rate <= terminal_rate:
                    st.error("할인율은 영구 성장률보다 커야 계산이 가능합니다.")
                else:
                    tv = (cf * (1 + terminal_rate/100)) / ((discount_rate - terminal_rate)/100)
                    tv_discounted = tv / ((1 + discount_rate/100)**5)
                    
                    total_value = dcf_val + tv_discounted
                    
                    if shares_out > 0:
                        value_per_share = total_value / shares_out if is_us_dcf else (total_value * 10000) / shares_out
                    else:
                        value_per_share = 0
                    
                    margin_of_safety = ((value_per_share - current_price) / value_per_share) * 100 if value_per_share > 0 else 0
                    
                    st.success("✅ 현금흐름 기반 내재가치 평가 완료!")
                    res_c1, res_c2, res_c3 = st.columns(3)
                    
                    if is_us_dcf:
                        res_c1.metric("1주당 적정 가치", f"${value_per_share:,.2f}")
                        res_c2.metric("현재 주가", f"${current_price:,.2f}", f"${current_price - value_per_share:,.2f} (괴리)", delta_color="inverse")
                    else:
                        res_c1.metric("1주당 적정 가치", f"{int(value_per_share):,}원")
                        res_c2.metric("현재 주가", f"{int(current_price):,}원", f"{int(current_price - value_per_share):,}원 (괴리)", delta_color="inverse")
                    
                    if margin_of_safety > 30:
                        mos_color, mos_text = "normal", "🟢 초강력 매수 구간 (매우 저평가)"
                    elif margin_of_safety > 10:
                        mos_color, mos_text = "normal", "🟡 분할 매수 고려 (저평가)"
                    else:
                        mos_color, mos_text = "inverse", "🔴 고평가 또는 적정 수준 (관망)"
                        
                    res_c3.metric("안전 마진 (저평가율)", f"{margin_of_safety:.1f}%", mos_text, delta_color=mos_color)

    with b_tab2:
        st.markdown("### 📈 버핏 지수 (시장 전체 거시적 평가)")
        st.write("`버핏 지수 = (주식시장 전체 시가총액 / 명목 GDP) × 100`")
        
        c_buf1, c_buf2 = st.columns(2)
        with c_buf1: market_cap = st.number_input("해당 국가 주식시장 총 시가총액 (조)", value=55.0)
        with c_buf2: gdp = st.number_input("해당 국가 명목 GDP (조)", value=27.0)
        
        buffett_ratio = (market_cap / gdp) * 100
        
        fig_gauge = go.Figure(go.Indicator(
            mode = "gauge+number", value = buffett_ratio, title = {'text': "<b>Buffett Indicator (%)</b>"},
            gauge = {'axis': {'range': [0, 200]}, 'bar': {'color': "black", 'thickness': 0.15},
                     'steps': [{'range': [0, 80], 'color': "lightgreen"}, {'range': [80, 100], 'color': "yellow"},
                               {'range': [100, 120], 'color': "orange"}, {'range': [120, 200], 'color': "red"}]}
        ))
        fig_gauge.update_layout(height=300, margin=dict(l=10, r=10, t=40, b=10))
        st.plotly_chart(fig_gauge, use_container_width=True)
        
        if buffett_ratio > 120: st.error("🚨 시장이 상당한 과열 상태입니다. (버블 경고)")
        elif buffett_ratio > 100: st.warning("⚠️ 시장이 약간 고평가 상태입니다. 현금 비중을 늘리는 것을 고려하세요.")
        elif buffett_ratio > 80: st.success("✅ 시장이 적정 가치 구간에 있습니다.")
        else: st.info("💰 시장이 저평가 상태입니다. 적극적인 매수 기회일 수 있습니다.")
            
        st.divider()
        st.markdown("### ⏱️ 복리 계산기 (72의 법칙)")
        return_rate = st.slider("목표 연평균 수익률 (%)", min_value=1.0, max_value=30.0, value=15.0, step=0.5)
        st.markdown(f"👉 연수익률 **{return_rate}%** 유지 시, 원금이 2배가 되는 데 약 **<span style='color:#ff4b4b; font-size:24px;'>{72 / return_rate:.1f}년</span>**이 걸립니다.", unsafe_allow_html=True)

    with b_tab3:
        st.markdown("### 🔍 퀀트식 버핏 전략 스크리닝 기준")
        st.info("실제 퀀트 플랫폼에서 워런 버핏 스타일의 알짜 가치주를 찾기 위해 설정해야 하는 검색 조건식 가이드입니다.")
        st.markdown("""
        #### 1. 수익성 (돈을 잘 버는가?)
        * **ROE (자기자본이익률):** 최근 3년 평균 **15% 이상** #### 2. 안정성 (망하지 않을 기업인가?)
        * **부채비율:** **50% 미만** (또는 최소한 해당 업종 평균 이하)
        #### 3. 가격 (싸게 사고 있는가?)
        * **PBR (주가순자산비율):** **1.5 이하**
        * **PER (주가수익비율):** **15 미만** (동일 업종 내 저평가 종목)
        """)

elif selected_menu == "🧪 v5.0 AI 포트폴리오 랩":
    if 'price_scan_results' not in st.session_state:
        st.session_state.price_scan_results = None

    st.markdown("## 🧪 v5.0 차세대 퀀트 & 포트폴리오 랩 (Beta)")
    st.write("단일 종목 분석을 넘어선 'AI 멀티 에이전트, 포트폴리오 상관관계, 대안 데이터(Sentiment), 커스텀 팩터, 조건 검색' 기반의 하이엔드 기능을 테스트합니다.")
    
    v5_tab1, v5_tab2, v5_tab3, v5_tab4, v5_tab5 = st.tabs([
        "🤖 1. AI 멀티 에이전트 토론", "🛡️ 2. 리스크 상관계수 맵", "👥 3. 군중 심리(FOMO) 트래커", "⚙️ 4. 팩터 커스텀 스튜디오", "💰 5. 금액대별 종목 스캐너"
    ])
    
    with v5_tab1:
        st.markdown("### 🤖 AI 전문가 3인방 난상토론 & 스코어링")
        with st.form(key="debate_form"):
            debate_ticker = st.text_input("분석할 종목명 또는 티커 입력 (예: 삼성전자, 005930, AAPL)").upper()
            debate_btn = st.form_submit_button("🔥 난상토론 시작", type="primary", use_container_width=True)
        
        if debate_btn:
            if not api_key_input: st.error("좌측 사이드바에 API 키를 입력해주세요.")
            elif not debate_ticker: st.warning("종목을 입력해주세요.")
            else:
                with st.spinner("3명의 AI 전문가가 데이터를 분석하고 토론을 준비 중입니다... (약 10~15초 소요)"):
                    prompt = f"""
                    당신은 3명의 자아가 부여된 주식 토론 시스템입니다. '{debate_ticker}'에 대해 다음 3가지 관점에서 의견을 내고, 마지막에 종합 점수를 도출하세요.
                    **[차트 & 모멘텀 전문가]** (2줄 코멘트)
                    **[가치투자 펀드매니저]** (2줄 코멘트)
                    **[매크로 이코노미스트]** (2줄 코멘트)
                    **[최종 매력도 점수]** (0~100 숫자만)
                    """
                    response = ask_gemini(prompt, api_key_input)
                    try:
                        parts = response.split("**[최종 매력도 점수]**")
                        col_text, col_score = st.columns([2, 1])
                        with col_text: st.info(parts[0].strip())
                        with col_score:
                            score = int(re.sub(r'[^0-9]', '', parts[1])) if parts[1] else 50
                            fig_gauge = go.Figure(go.Indicator(mode="gauge+number", value=score, title={'text': "<b>최종 투자 매력도</b>"}, gauge={'axis': {'range': [0, 100]}, 'bar': {'color': "black", 'thickness': 0.2}, 'steps': [{'range': [0, 40], 'color': "#ffcccb"}, {'range': [40, 60], 'color': "#fff9c4"}, {'range': [60, 100], 'color': "#c8e6c9"}]}))
                            fig_gauge.update_layout(height=250, margin=dict(l=10, r=10, t=60, b=10))
                            st.plotly_chart(fig_gauge, use_container_width=True)
                    except: st.markdown(response)
                        
    with v5_tab2:
        st.markdown("### 🛡️ 내 계좌 리스크 (상관계수) 히트맵")
        with st.form(key="corr_form"):
            port_input = st.text_input("분석할 종목들을 쉼표(,)로 구분해 입력하세요 (국장/미장 혼합 가능)", value="삼성전자, 현대차, SK하이닉스, AAPL, TSLA")
            corr_btn = st.form_submit_button("📊 상관계수 분석", type="primary", use_container_width=True)
        
        if corr_btn:
            port_tickers = [t.strip() for t in port_input.split(",") if t.strip()]
            if len(port_tickers) < 2: st.warning("최소 2개 이상의 종목을 입력해주세요.")
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
                        if len(price_dict) < 2: st.error("데이터를 충분히 불러오지 못했습니다. 종목명을 정확히 입력해주세요.")
                        else:
                            data = pd.DataFrame(price_dict).ffill().dropna()
                            corr_matrix = data.pct_change().corr().round(2)
                            fig_corr = px.imshow(corr_matrix, text_auto=True, color_continuous_scale='RdBu_r', zmin=-1, zmax=1)
                            fig_corr.update_layout(height=500)
                            st.plotly_chart(fig_corr, use_container_width=True)
                    except Exception as e: st.error(f"오류 발생: {e}")

    with v5_tab3:
        st.markdown("### 👥 군중 심리 트래커 (FOMO vs FUD)")
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
                        is_kr, kr_code = False, ""
                        
                        if senti_ticker_clean in name_to_code:
                            is_kr, kr_code = True, name_to_code[senti_ticker_clean]
                        elif re.match(r'^\d{6}$', senti_ticker_clean):
                            is_kr, kr_code = True, senti_ticker_clean

                        titles = []
                        if is_kr:
                            res = requests.get(f"https://finance.naver.com/item/news_news.naver?code={kr_code}", headers={"User-Agent": "Mozilla/5.0"})
                            soup = BeautifulSoup(res.content.decode('euc-kr', 'replace'), 'html.parser')
                            titles = [link.text.strip() for link in soup.select('.tit')[:10]]
                        else:
                            news_items = yf.Ticker(senti_ticker_clean).news
                            titles = [n['title'] for n in news_items[:10]] if news_items else []

                        if not titles: st.error("최근 뉴스 데이터를 찾을 수 없습니다.")
                        else:
                            prompt = f"'{senti_ticker_clean}' 최근 헤드라인 기반 FOMO 지수(0~100) 점수 산출:\n{chr(10).join(titles)}\n\n형식:\n점수: [숫자]\n이유: [요약]"
                            senti_res = ask_gemini(prompt, api_key_input)
                            score_match = re.search(r'점수:\s*(\d+)', senti_res)
                            senti_score = int(score_match.group(1)) if score_match else 50
                            
                            s_col1, s_col2 = st.columns([1, 2])
                            with s_col1:
                                fig_senti = go.Figure(go.Indicator(mode="gauge+number", value=senti_score, title={'text': "<b>FOMO / FUD Index</b>"}, gauge={'axis': {'range': [0, 100]}, 'bar': {'color': "black", 'thickness': 0.2}, 'steps': [{'range': [0, 30], 'color': "royalblue"}, {'range': [30, 70], 'color': "lightgray"}, {'range': [70, 100], 'color': "tomato"}]}))
                                fig_senti.update_layout(height=300, margin=dict(l=10, r=10, t=60, b=10))
                                st.plotly_chart(fig_senti, use_container_width=True)
                            with s_col2:
                                st.info(senti_res)
                                with st.expander("원문 헤드라인"):
                                    for t in titles: st.write(f"- {t}")
                    except Exception as e: st.error(f"오류: {e}")

    with v5_tab4:
        st.markdown("### ⚙️ 나만의 퀀트 팩터 커스텀 스튜디오")
        with st.form(key="factor_form"):
            c_fac1, c_fac2, c_fac3 = st.columns(3)
            with c_fac1: custom_ticker = st.text_input("테스트 종목", value="삼성전자")
            with c_fac2: short_ma = st.number_input("단기 이평선", 3, 20, 5)
            with c_fac3: long_ma = st.number_input("중장기 이평선", 20, 200, 20)
            rsi_limit = st.slider("RSI 필터", 20, 80, 50)
            factor_btn = st.form_submit_button("🚀 커스텀 전략 돌리기", type="primary", use_container_width=True)
            
        if factor_btn:
            with st.spinner(f"[{short_ma}일/{long_ma}일 교차 & RSI < {rsi_limit}] 백테스팅 중..."):
                try:
                    df = get_historical_data(custom_ticker.strip(), 730)
                    if df.empty: st.error("종목명을 확인해주세요.")
                    else:
                        df['MA_S'] = df['Close'].rolling(short_ma).mean()
                        df['MA_L'] = df['Close'].rolling(long_ma).mean()
                        dl = df['Close'].diff()
                        df['RSI'] = 100 - (100 / (1 + (dl.where(dl>0, 0).rolling(14).mean() / -dl.where(dl<0, 0).rolling(14).mean())))
                        df['Signal'] = np.where((df['MA_S'] > df['MA_L']) & (df['RSI'] < rsi_limit), 1, 0)
                        df['Position'] = df['Signal'].shift(1).fillna(0)
                        df['DR'] = df['Close'].pct_change()
                        df['Cum_Market'] = (1 + df['DR']).cumprod()
                        df['Cum_Strategy'] = (1 + df['Position'] * df['DR']).cumprod()
                        
                        fig_bt = go.Figure()
                        fig_bt.add_trace(go.Scatter(x=df.index, y=df['Cum_Market'], name="존버", line=dict(color='gray', dash='dot')))
                        fig_bt.add_trace(go.Scatter(x=df.index, y=df['Cum_Strategy'], name="전략", line=dict(color='#ff4b4b', width=2.5)))
                        fig_bt.update_layout(title=f"[{custom_ticker}] 누적 수익률", height=400, hovermode="x unified")
                        st.plotly_chart(fig_bt, use_container_width=True)
                        
                        fm, fs = (df['Cum_Market'].iloc[-1]-1)*100, (df['Cum_Strategy'].iloc[-1]-1)*100
                        res1, res2 = st.columns(2)
                        res1.metric("존버 수익률", f"{fm:.2f}%")
                        res2.metric("전략 수익률", f"{fs:.2f}%", f"{fs - fm:.2f}%p 대비")
                except Exception as e: st.error(f"오류: {e}")

    with v5_tab5:
        st.markdown("### 💰 금액대별 실시간 종목 스캐너")
        with st.form("price_scan_form"):
            c_p1, c_p2 = st.columns(2)
            with c_p1: mc = st.selectbox("시장 선택", ["🇰🇷 국내 주식", "🇺🇸 미국 주식"])
            with c_p2:
                ul = "원" if mc == "🇰🇷 국내 주식" else "달러($)"
                pr = st.slider(f"가격대 ({ul})", 1000 if mc=="🇰🇷 국내 주식" else 1.0, 1000000 if mc=="🇰🇷 국내 주식" else 1000.0, (10000, 50000) if mc=="🇰🇷 국내 주식" else (50.0, 200.0), 1000 if mc=="🇰🇷 국내 주식" else 5.0)
            sl = st.number_input("최대 검색 수", 10, 100, 30, 10)
            s_btn = st.form_submit_button("🚀 병렬 스캔 시작", type="primary", use_container_width=True)

        if s_btn:
            with st.spinner("스캔 중..."):
                fs = []
                if mc == "🇰🇷 국내 주식":
                    kdf = get_krx_stocks()
                    if not kdf.empty:
                        ss = kdf.sample(n=min(len(kdf), 300)).values.tolist()
                        pb, stx = st.progress(0), st.empty()
                        def ck(t):
                            try:
                                if pr[0] <= float(get_historical_data(t[1], 5)['Close'].iloc[-1]) <= pr[1]: return analyze_technical_pattern(t[0], t[1])
                            except: pass
                            return None
                        c = 0
                        with concurrent.futures.ThreadPoolExecutor(max_workers=5) as ex:
                            for f in concurrent.futures.as_completed([ex.submit(ck, s) for s in ss]):
                                if r := f.result(): fs.append(r)
                                c += 1; pb.progress(min(c/len(ss), 1.0)); stx.text(f"스캔 중... {len(fs)}개 포착")
                                if len(fs) >= sl: break 
                else:
                    udf, _, _ = get_us_top_gainers()
                    if not udf.empty:
                        pb, stx, ut = st.progress(0), st.empty(), udf[['종목코드', '기업명']].values.tolist()
                        def cu(t):
                            try:
                                if pr[0] <= float(get_historical_data(t[0], 5)['Close'].iloc[-1]) <= pr[1]: return analyze_technical_pattern(t[1], t[0])
                            except: pass
                            return None
                        c = 0
                        with concurrent.futures.ThreadPoolExecutor(max_workers=5) as ex:
                            for f in concurrent.futures.as_completed([ex.submit(cu, s) for s in ut]):
                                if r := f.result(): fs.append(r)
                                c += 1; pb.progress(min(c/len(ut), 1.0)); stx.text(f"스캔 중... {len(fs)}개 포착")
                                if len(fs) >= sl: break
                st.session_state.price_scan_results = fs; st.rerun()

        if st.session_state.price_scan_results is not None:
            rl = st.session_state.price_scan_results
            if not rl: st.warning("종목을 찾지 못했습니다.")
            else:
                st.success(f"🎯 {len(rl)}개 포착!")
                so = st.radio("정렬", ["기본", "현재가 낮은순 🔽", "현재가 높은순 🔼", "RSI 낮은순"], horizontal=True)
                dl = rl.copy()
                if so == "현재가 낮은순 🔽": dl.sort(key=lambda x: x['현재가'])
                elif so == "현재가 높은순 🔼": dl.sort(key=lambda x: x['현재가'], reverse=True)
                elif so == "RSI 낮은순": dl.sort(key=lambda x: x['RSI'])
                for i, r in enumerate(dl): draw_stock_card(r, api_key_input, False, f"ps_{i}")
# 파트 2 끝
