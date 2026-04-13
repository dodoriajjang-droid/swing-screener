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
import random

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
st.set_page_config(page_title="Jaemini PRO 터미널 v4.0", layout="wide", page_icon="📈")
st_autorefresh(interval=300000, limit=None, key="news_autorefresh")

# 세션 상태 초기화
for key in ['seen_links', 'seen_titles', 'news_data']:
    if key not in st.session_state: st.session_state[key] = set() if 'seen' in key else []
if 'watchlist' not in st.session_state: st.session_state.watchlist = load_watchlist()
if 'quick_analyze_news' not in st.session_state: st.session_state.quick_analyze_news = None
if 'scan_results' not in st.session_state: st.session_state.scan_results = None
if 'value_scan_results' not in st.session_state: st.session_state.value_scan_results = None
if 'pension_scan_results' not in st.session_state: st.session_state.pension_scan_results = None

if 'deep_tech_query' not in st.session_state: st.session_state.deep_tech_query = None
if 'deep_tech_results' not in st.session_state: st.session_state.deep_tech_results = None
if 'deep_tech_input' not in st.session_state: st.session_state.deep_tech_input = ""

now = datetime.now()
if 'smart_cal_year' not in st.session_state: st.session_state.smart_cal_year = now.year
if 'smart_cal_month' not in st.session_state: st.session_state.smart_cal_month = now.month

# ==========================================
# 2. 통합 데이터 수집 & AI 함수 모음
# ==========================================
@st.cache_data(ttl=3600)
def ask_gemini(prompt, _api_key):
    if not _api_key: return "API 키가 필요합니다."
    try:
        genai.configure(api_key=_api_key)
        # 👈 모델 gemini-3.1-flash-lite-preview 적용 완
        return genai.GenerativeModel('gemini-3.1-flash-lite-preview').generate_content(prompt).text
    except Exception as e: 
        if "429" in str(e) or "quota" in str(e).lower() or "spending cap" in str(e).lower():
            return "🚨 AI API 무료 한도가 초과되었거나 결제 한도에 도달했습니다."
        return f"AI 분석 오류: {str(e)}"

# 👈 AI 브리핑 생성 시간 및 3시간 단위 캐싱 적용 완
@st.cache_data(ttl=10800)
def get_daily_market_briefing(macro_data, top_gainers, _api_key):
    if not _api_key: return "API 키가 필요합니다.", ""
    
    vix = f"{macro_data['VIX']['value']:.2f}" if macro_data and 'VIX' in macro_data else 'N/A'
    sox = f"{macro_data['필라델피아 반도체']['value']:.2f}" if macro_data and '필라델피아 반도체' in macro_data else 'N/A'
    krw = f"{macro_data['원/달러 환율']['value']:.1f}" if macro_data and '원/달러 환율' in macro_data else 'N/A'
    tnx = f"{macro_data['美 10년물 국채']['value']:.3f}" if macro_data and '美 10년물 국채' in macro_data else 'N/A'
    gainers_str = ", ".join(top_gainers) if top_gainers else '데이터 없음'

    prompt = f"""
    당신은 여의도 최고의 시황 애널리스트(여의도 데스크)입니다. 오늘 아침 실전 트레이더들을 위한 '모닝 브리핑'을 작성해주세요.
    
    [현재 글로벌 매크로 및 수급 데이터]
    - VIX(공포지수): {vix}
    - 필라델피아 반도체 지수: {sox}
    - 원/달러 환율: {krw}원
    - 美 10년물 국채금리: {tnx}%
    - 전일 미국장 주요 급등주: {gainers_str}
    
    위 팩트 데이터를 바탕으로 다음 3가지 항목을 마크다운 포맷으로 가독성 좋게 작성해주세요. 
    (시작말: "안녕하십니까. 여의도 데스크입니다. 오늘 아침 시장 대응을 위한 핵심 전략 전달합니다.")
    
    1. 🇺🇸 **간밤의 미 증시 요약**: 매크로 데이터와 급등주를 바탕으로 한 전일 미국장 요약 (2~3줄)
    2. 🇰🇷 **국내 증시 투자의견**: 미 증시 결과와 환율/금리가 오늘 한국 코스피/코스닥 수급에 미칠 영향 (2~3줄)
    3. 🎯 **오늘의 픽 (주목할 섹터)**: 위 데이터를 볼 때, 오늘 장중 자금이 쏠릴 것으로 예상되는 국내 수혜 섹터 1~2개와 그 이유 (1줄)
    """
    gen_time = datetime.now().strftime("%Y년 %m월 %d일 %H시 %M분")
    return ask_gemini(prompt, _api_key), gen_time

@st.cache_data(ttl=3600)
def get_company_summary(ticker, comp_name, _api_key):
    if not _api_key: return "API 키가 필요합니다."
    prompt = f"""
    당신은 글로벌 주식 펀드매니저입니다. 미국 급등주 '{comp_name} (티커: {ticker})'에 대해 아래 내용을 마크다운으로 작성해주세요.
    1. 🏢 **핵심 비즈니스 & 모멘텀**: 이 기업의 주가 상승을 견인한 비즈니스 모델과 최신 모멘텀을 2~3줄로 브리핑하세요.
    2. 🇰🇷 **국내 증시 대비 포인트**: 이 기업의 상승과 연관하여, 오늘 한국 증시에서 반드시 주목해야 할 연관 테마 및 섹터를 2줄로 직관적으로 제시하세요.
    """
    return ask_gemini(prompt, _api_key)

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
        prompt = "최근 한국 증시에서 가장 자금이 많이 몰리고 상승세가 강한 주도 테마 4개만 정확히 쉼표(,)로 구분해서 단어 형태로 1줄로 출력하세요. 부연설명, 번호표, 특수문자 절대 금지. 예시: 반도체장비, 2차전지, 제약바이오, 원자력"
        response = ask_gemini(prompt, _api_key)
        valid_themes = [t.strip() for t in response.replace('\n', '').replace('*', '').replace('-', '').replace('.', '').split(',') if t.strip()]
        return valid_themes[:4] if len(valid_themes) >= 4 else default_themes[:4]
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
    headers = {"User-Agent": "Mozilla/5.0"}
    try:
        res = requests.get(url, headers=headers, timeout=4)
        if res.status_code == 200:
            data = res.json()
            return {"score": round(data['fear_and_greed']['score']), "delta": round(data['fear_and_greed']['score'] - data['fear_and_greed']['previous_close']), "rating": data['fear_and_greed']['rating'].capitalize()}
    except: pass
    try:
        proxy_url = f"https://api.allorigins.win/raw?url={urllib.parse.quote(url)}"
        res = requests.get(proxy_url, timeout=5)
        if res.status_code == 200:
            data = res.json()
            return {"score": round(data['fear_and_greed']['score']), "delta": round(data['fear_and_greed']['score'] - data['fear_and_greed']['previous_close']), "rating": data['fear_and_greed']['rating'].capitalize()}
    except: pass
    return {"score": 50, "delta": 0, "rating": "Neutral (서버차단 방어)"}

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
        df = df.sort_values('등락률', ascending=False).head(15)
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

# 👈 거래대금 및 거래량 급증 데이터 스크래핑 추가 완
@st.cache_data(ttl=300)
def get_volume_rankings():
    headers = {'User-Agent': 'Mozilla/5.0'}
    df_quant = pd.DataFrame()
    df_spike = pd.DataFrame()
    try:
        # 거래대금/거래량 상위 (sise_quant.naver)
        res1 = requests.get("https://finance.naver.com/sise/sise_quant.naver", headers=headers, timeout=5)
        dfs1 = pd.read_html(StringIO(res1.content.decode('euc-kr', 'replace')))
        for df in dfs1:
            if '종목명' in df.columns:
                df = df.dropna(subset=['종목명'])
                df = df[df['종목명'] != '종목명']
                df_quant = df
                break
                
        # 거래량 급증 상위 (sise_quant_high.naver)
        res2 = requests.get("https://finance.naver.com/sise/sise_quant_high.naver", headers=headers, timeout=5)
        dfs2 = pd.read_html(StringIO(res2.content.decode('euc-kr', 'replace')))
        for df in dfs2:
            if '종목명' in df.columns:
                df = df.dropna(subset=['종목명'])
                df = df[df['종목명'] != '종목명']
                df_spike = df
                break
                
        return df_quant, df_spike
    except:
        return pd.DataFrame(), pd.DataFrame()

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
    for col in ['Code', 'Sector', 'Close', 'Changes', 'ChagesRatio', 'Amount_Ouk', 'PrevClose', 'Name']:
        if col not in upper_df.columns: upper_df[col] = "기타" if col == 'Sector' else 0
        if col not in lower_df.columns: lower_df[col] = "기타" if col == 'Sector' else 0
    return upper_df.sort_values('Amount_Ouk', ascending=False), lower_df.sort_values('Amount_Ouk', ascending=False)

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
        inst_sum, forgn_sum, ind_sum = 0, 0, 0
        inst_streak, forgn_streak, ind_streak = 0, 0, 0
        inst_break, forgn_break, ind_break = False, False, False
        count = 0
        for row in rows:
            tds = row.select('td')
            if len(tds) < 9 or not tds[0].text.strip(): continue 
            try:
                i_val = int(tds[5].text.strip().replace(',', '').replace('+', ''))
                f_val = int(tds[6].text.strip().replace(',', '').replace('+', ''))
                p_val = -(i_val + f_val) 
                inst_sum += i_val
                forgn_sum += f_val
                ind_sum += p_val
                if i_val > 0 and not inst_break: inst_streak += 1
                elif i_val <= 0: inst_break = True
                if f_val > 0 and not forgn_break: forgn_streak += 1
                elif f_val <= 0: forgn_break = True
                if p_val > 0 and not ind_break: ind_streak += 1
                elif p_val <= 0: ind_break = True
                count += 1
            except: pass
            if count >= 5: break 
        def fmt(v, streak): 
            base = f"+{v:,}" if v > 0 else f"{v:,}"
            if streak >= 3: return f"{base} (🔥{streak}일 연속 매집)"
            return f"{base} ({'🔥매집' if v>0 else '💧매도' if v<0 else '➖중립'})"
        return fmt(inst_sum, inst_streak), fmt(forgn_sum, forgn_streak), fmt(ind_sum, ind_streak), inst_streak, forgn_streak
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

# 👈 [투자자 보호 시스템] 관리종목, 시장경보 실시간 체커 추가 완
@st.cache_data(ttl=3600)
def get_stock_protection_status(code):
    try:
        url = f"https://finance.naver.com/item/main.naver?code={code}"
        res = requests.get(url, headers={'User-Agent': 'Mozilla/5.0'}, timeout=2)
        soup = BeautifulSoup(res.text, 'html.parser')
        status_area = soup.select_one('.wrap_company')
        if not status_area: return ""
        text = status_area.text
        tags = []
        if '관리종목' in text: tags.append('🚨관리종목')
        if '투자경고' in text or '투자위험' in text: tags.append('🔴위험/경고')
        elif '투자주의' in text: tags.append('⚠️투자주의')
        if '환기종목' in text: tags.append('⚠️환기종목')
        return " ".join(tags)
    except: return ""

def get_fundamentals(ticker_code):
    if ticker_code.isdigit():
        try:
            url = f"https://finance.naver.com/item/main.naver?code={ticker_code}"
            res = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=5)
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
def get_historical_data(ticker_code, days):
    start_date = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d')
    df = pd.DataFrame()
    if ticker_code.isdigit():
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
def analyze_technical_pattern(stock_name, ticker_code, offset_days=0):
    if not ticker_code: return None
    try:
        df = get_historical_data(ticker_code, 150)
        if df.empty or len(df) < 20 + offset_days: return None
        
        today_close = int(df['Close'].iloc[-1]) 
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
        current_price = int(latest['Close']) 
        
        if pd.notna(latest['MA60']) and latest['MA5'] > latest['MA20'] > latest['MA60']: align_status = "🔥 완벽 정배열 (상승 추세) ｜ 💡 기준: 5일선 > 20일선 > 60일선"
        elif pd.notna(latest['MA60']) and latest['MA5'] < latest['MA20'] < latest['MA60']: align_status = "❄️ 역배열 (하락 추세) ｜ 💡 기준: 5일선 < 20일선 < 60일선"
        elif latest['MA5'] > latest['MA20'] and prev['MA5'] <= prev['MA20']: align_status = "✨ 5-20 골든크로스 ｜ 💡 기준: 5일선이 20일선을 상향 돌파"
        else: align_status = "🌀 혼조세/횡보 ｜ 💡 기준: 이평선 얽힘 (방향 탐색중)"
        
        ma20_val = latest['MA20']
        if (ma20_val * 0.97) <= current_price <= (ma20_val * 1.03): status = "✅ 타점 근접 (분할 매수)"
        elif current_price > (ma20_val * 1.03): status = "⚠️ 이격 과다 (눌림목 대기)"
        else: status = "🛑 20일선 이탈 (관망)"
        
        inst_vol, forgn_vol, ind_vol, inst_streak, forgn_streak = get_investor_trend(ticker_code)
        intraday_est = get_intraday_estimate(ticker_code) 
        pension_sum, pension_streak = get_pension_fund_trend(ticker_code)
        per, pbr = get_fundamentals(ticker_code)
        
        # 보호상태 통합
        prot_status = get_stock_protection_status(ticker_code)
        full_name = f"{stock_name} {prot_status}".strip() if prot_status else stock_name
        
        target_1 = int(latest['Bollinger_Upper'])
        recent_high = int(analysis_df['Close'].max())
        target_2 = recent_high if recent_high > (target_1 * 1.02) else int(target_1 * 1.05)
        target_3 = int(target_2 * 1.08)
        
        pnl_pct = ((today_close - current_price) / current_price) * 100 if offset_days > 0 and current_price > 0 else 0.0
        
        krx_df = get_krx_stocks()
        sector_val = "ETF/분류없음"
        if not krx_df.empty:
            match_sec = krx_df[krx_df['Code'] == ticker_code]['Sector']
            if not match_sec.empty and pd.notna(match_sec.iloc[0]):
                raw_sec = str(match_sec.iloc[0])
                sector_val = raw_sec.replace(" 및 공급업", "").replace(" 제조업", "").replace(" 제조 및", "").replace(" 도매업", "").replace(" 소매업", "")
        
        return {
            "종목명": full_name, "티커": ticker_code, "섹터": sector_val, "현재가": current_price, "상태": status,
            "진입가_가이드": int(ma20_val), "목표가1": target_1, "목표가2": target_2, "목표가3": target_3, "손절가": int(ma20_val * 0.97),
            "거래량 급증": "🔥 거래량 터짐" if analysis_df.iloc[-10:]['Volume'].max() > (analysis_df.iloc[-10:]['Vol_MA20'].mean() * 2) else "평이함",
            "RSI": latest['RSI'], "배열상태": align_status, 
            "기관수급": inst_vol, "외인수급": forgn_vol, "개인수급": ind_vol, "장중잠정수급": intraday_est,
            "기관연속순매수": inst_streak, "외인연속순매수": forgn_streak,
            "연기금추정순매수": pension_sum, "연기금연속순매수": pension_streak,
            "PER": per, "PBR": pbr, "OBV": analysis_df['OBV'].tail(20), "차트 데이터": analysis_df.tail(20), 
            "오늘현재가": today_close, "수익률": pnl_pct, "과거검증": offset_days > 0, "보호상태": prot_status
        }
    except: return None

@st.cache_data(ttl=3600)
def analyze_theme_trends():
    theme_proxies = {
        "반도체": "091160", "2차전지": "305720", "바이오/헬스케어": "244580", "인터넷/플랫폼": "157490",
        "자동차/모빌리티": "091230", "금융/지주": "091220", "미디어/엔터": "266360", "로봇/AI": "417270",
        "K-방산": "449450", "조선/중공업": "139240", "원자력/전력기기": "102960", "화장품/미용": "228790",
        "게임": "300610", "건설/인프라": "117700", "철강/소재": "117680"
    }
    results = []
    for theme_name, ticker in theme_proxies.items():
        try:
            df = get_historical_data(ticker, 250) 
            if df.empty or len(df) < 20: continue
            current_price = float(df['Close'].iloc[-1])
            def get_stats(days):
                slice_len = min(days, len(df))
                period_df = df.iloc[-slice_len:]
                start_price = float(period_df['Close'].iloc[0])
                if start_price == 0: return 0, 0
                ret = ((current_price - start_price) / start_price) * 100
                vol_sum = (period_df['Volume'] * period_df['Close']).sum() / 100000000
                return ret, vol_sum
            r_1m, v_1m = get_stats(20)   
            r_3m, v_3m = get_stats(60)   
            r_6m, v_6m = get_stats(120)  
            results.append({"테마": theme_name, "1M수익률": r_1m, "1M거래대금": v_1m, "3M수익률": r_3m, "3M거래대금": v_3m, "6M수익률": r_6m, "6M거래대금": v_6m})
        except: pass
    return pd.DataFrame(results)

# 👈 IPO 파싱 완벽 수정본
@st.cache_data(ttl=10800)
def get_naver_ipo_data():
    try:
        url = "https://finance.naver.com/sise/ipo.naver"
        res = requests.get(url, headers={'User-Agent': 'Mozilla/5.0'}, timeout=5)
        dfs = pd.read_html(StringIO(res.content.decode('euc-kr', 'replace')))
        for df in dfs:
            if '종목명' in df.columns:
                df = df.dropna(subset=['종목명'])
                df = df[df['종목명'] != '종목명']
                cols = [c for c in ['종목명', '현재가', '공모희망가', '공모가', '청약일', '상장일', '주간사'] if c in df.columns]
                return df[cols].head(15).reset_index(drop=True)
        return pd.DataFrame()
    except: return pd.DataFrame()

# 토큰 절약을 위한 딕셔너리 최적화 배치 (150개 이상)
@st.cache_data(ttl=43200) 
def get_dividend_portfolio(ex_rate=1350.0):
    portfolio = {
        "KRX": [
            ("088980.KS","맥쿼리인프라","반기","6.2%"), ("024110.KS","기업은행","결산","8.1%"), ("316140.KS","우리금융지주","분기","8.5%"),
            ("033780.KS","KT&G","분기","6.5%"), ("017670.KS","SK텔레콤","분기","6.8%"), ("055550.KS","신한지주","분기","6.0%"),
            ("086790.KS","하나금융지주","분기","7.1%"), ("105560.KS","KB금융","분기","5.5%"), ("138040.KS","메리츠금융지주","결산","5.0%"),
            ("139130.KS","DGB금융지주","결산","8.5%"), ("175330.KS","JB금융지주","반기","8.8%"), ("138930.KS","BNK금융지주","결산","8.6%"),
            ("016360.KS","삼성증권","결산","7.5%"), ("005940.KS","NH투자증권","결산","7.4%"), ("051600.KS","한전KPS","결산","6.0%"),
            ("030200.KS","KT","분기","6.0%"), ("000815.KS","삼성화재우","결산","7.0%"), ("053800.KS","현대차2우B","분기","6.8%"),
            ("030000.KS","제일기획","결산","6.0%"), ("040420.KS","정상제이엘에스","결산","6.5%"), ("010950.KS","S-Oil","결산","5.5%"),
            ("005935.KS","삼성전자우","분기","2.8%"), ("005490.KS","POSCO홀딩스","분기","4.8%"), ("071050.KS","한국금융지주","결산","6.0%"),
            ("003540.KS","대신증권","결산","8.0%"), ("039490.KS","키움증권","결산","4.5%"), ("005830.KS","DB손해보험","결산","5.5%"),
            ("001450.KS","현대해상","결산","6.0%"), ("000810.KS","삼성생명","결산","5.0%"), ("003690.KS","코리안리","결산","5.5%"),
            ("108670.KS","LX인터내셔널","결산","7.0%"), ("078930.KS","GS","결산","6.0%"), ("004800.KS","효성","결산","6.5%"),
            ("011500.KS","E1","결산","5.5%"), ("004020.KS","고려아연","결산","4.0%"), ("001230.KS","동국제강","결산","6.0%"),
            ("001430.KS","세아베스틸지주","결산","5.5%"), ("267250.KS","HD현대","결산","5.5%"), ("002960.KS","한국쉘석유","결산","6.5%"),
            ("001720.KS","신영증권","결산","7.0%"), ("000060.KS","동양생명","결산","6.5%"), ("036530.KS","LS","결산","3.5%"),
            ("034730.KS","SK","결산","4.0%"), ("000880.KS","한화","결산","3.5%"), ("069260.KS","TKG휴켐스","결산","5.5%")
        ],
        "US": [
            ("O","Realty Income","월배당","5.8%"), ("MO","Altria Group","분기","9.2%"), ("VZ","Verizon","분기","6.2%"),
            ("T","AT&T","분기","6.1%"), ("PM","Philip Morris","분기","5.2%"), ("KO","Coca-Cola","분기","3.2%"),
            ("PEP","PepsiCo","분기","3.0%"), ("JNJ","Johnson & Johnson","분기","3.1%"), ("PG","Procter & Gamble","분기","2.5%"),
            ("ABBV","AbbVie","분기","4.0%"), ("PFE","Pfizer","분기","5.8%"), ("CVX","Chevron","분기","4.2%"),
            ("XOM","Exxon Mobil","분기","3.3%"), ("MMM","3M","분기","6.0%"), ("IBM","IBM","분기","3.8%"),
            ("ENB","Enbridge","분기","7.2%"), ("WPC","W. P. Carey","분기","6.3%"), ("MAIN","Main Street","월배당","6.2%"),
            ("ARCC","Ares Capital","분기","9.3%"), ("KMI","Kinder Morgan","분기","6.2%"), ("CSCO","Cisco Systems","분기","3.2%"),
            ("HD","Home Depot","분기","2.8%"), ("MRK","Merck","분기","2.8%"), ("MCD","McDonald's","분기","2.2%"),
            ("WMT","Walmart","분기","1.8%"), ("TGT","Target","분기","2.8%"), ("CAT","Caterpillar","분기","1.8%"),
            ("LOW","Lowe's","분기","1.8%"), ("SBUX","Starbucks","분기","2.8%"), ("CL","Colgate-Palmolive","분기","2.2%"),
            ("K","Kellanova","분기","3.8%"), ("GIS","General Mills","분기","3.2%"), ("HSY","Hershey","분기","2.8%"),
            ("KMB","Kimberly-Clark","분기","3.8%"), ("GPC","Genuine Parts","분기","2.8%"), ("ED","Consolidated Edison","분기","3.8%"),
            ("SO","Southern Company","분기","3.8%"), ("DUK","Duke Energy","분기","4.2%"), ("NEE","NextEra Energy","분기","2.8%")
        ],
        "ETF": [
            ("SCHD","US SCHD (고배당)","분기","3.6%"), ("JEPI","US JEPI (프리미엄)","월배당","7.5%"), ("JEPQ","US JEPQ (프리미엄)","월배당","9.0%"),
            ("VYM","US VYM (고배당)","분기","3.0%"), ("SPYD","US SPYD (S&P500 고배당)","분기","4.8%"), ("DGRO","US DGRO (배당성장)","분기","2.4%"),
            ("QYLD","US QYLD (커버드콜)","월배당","11.5%"), ("XYLD","US XYLD (S&P 커버드콜)","월배당","9.5%"), ("RYLD","US RYLD (러셀 커버드콜)","월배당","12.0%"),
            ("DIVO","US DIVO (배당+옵션)","월배당","4.8%"), ("VNQ","US VNQ (리츠)","분기","4.2%"), ("VIG","US VIG (배당성장)","분기","2.0%"),
            ("NOBL","US NOBL (배당귀족)","분기","2.2%"), ("SDY","US SDY (배당귀족)","분기","2.8%"), ("HDV","US HDV (핵심배당)","분기","3.8%"),
            ("PEY","US PEY (고배당)","월배당","4.8%"), ("DHS","US DHS (고배당)","월배당","3.8%"), ("DVY","US DVY (우량배당)","분기","3.8%"),
            ("458730.KS","TIGER 미국배당다우존스","월배당","3.8%"), ("161510.KS","ARIRANG 고배당주","결산","6.5%"), ("458760.KS","TIGER 미국배당+7%","월배당","10.5%")
        ]
    }
    all_tickers = [t for cat in portfolio.values() for t, n, p, y in cat]
    price_dict = {}
    try:
        data = yf.download(all_tickers, period="5d", progress=False)
        if isinstance(data.columns, pd.MultiIndex): close_data = data['Close']
        elif 'Close' in data: close_data = pd.DataFrame(data['Close'])
        else: close_data = pd.DataFrame()
        for t in all_tickers:
            if t in close_data.columns:
                val = close_data[t].dropna()
                if not val.empty: price_dict[t] = float(val.iloc[-1])
    except: pass
    results = {"KRX": [], "US": [], "ETF": []}
    for category, stocks in portfolio.items():
        for t_code, name, period, est_yield in stocks:
            p_val = price_dict.get(t_code)
            p_str, div_str = "조회 지연", est_yield
            if p_val:
                if ".KS" in t_code: p_str, krw_price = f"{int(p_val):,}원", p_val
                else: p_str, krw_price = f"${p_val:,.2f}", p_val * ex_rate
                try:
                    pcts = [float(x) for x in re.findall(r"[\d\.]+", est_yield)]
                    if len(pcts) >= 2: div_str = f"{est_yield} (약 {int(krw_price * (pcts[0] / 100)):,}~{int(krw_price * (pcts[1] / 100)):,}원)"
                    elif len(pcts) == 1: div_str = f"{est_yield} (약 {int(krw_price * (pcts[0] / 100)):,}원)"
                except: pass
            results[category].append({"티커/코드": t_code.replace(".KS", ""), "종목명": name, "현재가": p_str, "배당수익률(예상)": div_str, "배당주기": period})
    return {k: pd.DataFrame(v) for k, v in results.items()}

@st.cache_data(ttl=86400)
def get_nps_holdings_mock():
    return pd.DataFrame([
        {"종목명": "삼성전자", "티커": "005930", "보유비중": "7.52%", "최근변동": "유지"},
        {"종목명": "SK하이닉스", "티커": "000660", "보유비중": "8.12%", "최근변동": "확대"},
        {"종목명": "현대차", "티커": "005380", "보유비중": "7.35%", "최근변동": "확대"},
        {"종목명": "NAVER", "티커": "035420", "보유비중": "8.99%", "최근변동": "유지"},
        {"종목명": "카카오", "티커": "035720", "보유비중": "5.41%", "최근변동": "축소"}
    ])

# ==========================================
# 3. UI 렌더링 가이드 및 카드 함수
# ==========================================
def show_beginner_guide():
    with st.expander("🐥 [주린이 필독] 주식 용어 & 매매 타점 완벽 가이드", expanded=False):
        st.markdown("""### 1. 📊 차트 상태 (상세 진단 기준 & 이평선)\n* **🔥 완벽 정배열:** 5일선 > 20일선 > 60일선\n* **✨ 5-20 골든크로스:** 단기선(5일)이 중기선(20일) 상향 돌파""")

def show_trading_guidelines():
    with st.expander("🎯 [필독] 실전 매매 시나리오 (단기 스윙 전략)", expanded=True):
        st.markdown("**1️⃣ 주도 테마 선점** -> **2️⃣ 스캐너 황금 콤보(눌림목+거래량+스마트머니) 포착** -> **3️⃣ 기계적 대응**")

def draw_stock_card(tech_result, api_key_str="", is_expanded=False, key_suffix="default"):
    status_emoji = tech_result['상태'].split(' ')[0]
    align_status_short = tech_result['배열상태'].split(' ｜ ')[0]
    base_info = f"(진단: {tech_result['상태']} ｜ 상세: {align_status_short} ｜ 외인: {tech_result['외인수급']} ｜ 기관: {tech_result['기관수급']} ｜ RSI: {tech_result['RSI']:.1f})"
    header_block = f"{status_emoji} {tech_result['종목명']} / {tech_result.get('섹터','기타')} / {tech_result['현재가']:,}원"
    
    with st.expander(f"{header_block} ｜ {base_info}", expanded=is_expanded):
        if tech_result.get('과거검증'):
            st.markdown(f"**⏰ 타임머신 검증 결과:** 스캔 당시 **{tech_result['현재가']:,}원** ➡️ 오늘 **{tech_result['오늘현재가']:,}원** ({tech_result['수익률']:+.2f}%)")
            
        c_b1, c_b2 = st.columns([8, 2])
        c_b1.markdown(f"**상세 진단:** {tech_result['배열상태']}")
        is_in_wl = any(x['티커'] == tech_result['티커'] for x in st.session_state.watchlist)
        if not is_in_wl:
            if c_b2.button("⭐ 관심종목 추가", key=f"star_add_{tech_result['티커']}_{key_suffix}"):
                st.session_state.watchlist.append({'종목명': tech_result['종목명'], '티커': tech_result['티커']}); save_watchlist(st.session_state.watchlist); st.rerun()
        else:
            if c_b2.button("❌ 관심종목 삭제", key=f"star_del_{tech_result['티커']}_{key_suffix}"):
                st.session_state.watchlist = [x for x in st.session_state.watchlist if x['티커'] != tech_result['티커']]; save_watchlist(st.session_state.watchlist); st.rerun()

        c1, c2, c3, c4 = st.columns(4)
        c1.metric("📌 진입가", f"{tech_result['진입가_가이드']:,}원", f"{tech_result['진입가_가이드']-tech_result['현재가']:,}원", delta_color="off")
        c2.metric("🎯 1차목표", f"{tech_result['목표가1']:,}원", f"+{tech_result['목표가1']-tech_result['현재가']:,}원")
        c3.metric("🛑 손절가", f"{tech_result['손절가']:,}원", f"{tech_result['손절가']-tech_result['현재가']:,}원")
        c4.metric("📊 RSI", f"{tech_result['RSI']:.1f}", "과열" if tech_result['RSI']>=70 else "바닥", delta_color="inverse")
        
        st.markdown(f"🕵️ **5일 수급 동향:** 외국인 `{tech_result['외인수급']}` ｜ 기관 `{tech_result['기관수급']}`")
        if tech_result.get('연기금연속순매수', 0) >= 3: st.markdown(f"👴 **스마트머니 시그널:** <span style='color:orange;'>🔥 기관(연기금 추정) {tech_result['연기금연속순매수']}일 연속 순매수</span>", unsafe_allow_html=True)
        
        if api_key_str:
            if st.button(f"🤖 '{tech_result['종목명']}' AI 딥다이브 분석", key=f"ai_btn_{tech_result['티커']}_{key_suffix}"):
                with st.spinner("AI 분석 중..."):
                    if str(tech_result['티커']).isdigit():
                        fin_df, peer_df, cons = get_financial_deep_data(tech_result['티커'])
                        p = f"[{tech_result['종목명']}] 현재가 {tech_result['현재가']}, 20일선 {tech_result['진입가_가이드']}, RSI {tech_result['RSI']:.1f}, 컨센: {cons}\n재무/수급 분석 및 투자 전략 3줄 요약."
                        st.info(ask_gemini(p, api_key_str))
                    else: st.info(ask_gemini(f"[{tech_result['종목명']}] 기술적 분석 및 대응 전략 3줄 요약.", api_key_str))
        
        df_hist = get_historical_data(tech_result['티커'], 60)
        if not df_hist.empty:
            df_hist = df_hist.reset_index()
            df_hist['Date_Str'] = df_hist['Date'].dt.strftime('%m/%d')
            fig = go.Figure(data=[go.Candlestick(x=df_hist['Date_Str'], open=df_hist['Open'], high=df_hist['High'], low=df_hist['Low'], close=df_hist['Close'])])
            fig.update_layout(margin=dict(l=0, r=0, t=10, b=0), xaxis_rangeslider_visible=False, height=200)
            st.plotly_chart(fig, use_container_width=True, key=f"cht_{tech_result['티커']}_{key_suffix}")

def display_sorted_results(results_list, tab_key, api_key=""):
    if not results_list: return st.info("조건에 부합하는 종목이 없습니다.")
    st.success(f"🎯 총 {len(results_list)}개 종목 포착 완료!")
    sort_opt = st.radio("⬇️ 결과 정렬 방식", ["기본 (검색순)", "RSI 낮은순 (바닥줍기)", "연기금 순매수 긴 순서"], horizontal=True, key=f"sort_radio_{tab_key}")
    display_list = results_list.copy()
    if "RSI 낮은순" in sort_opt: sorted_res = sorted(display_list, key=lambda x: x['RSI'])
    elif "연기금 순매수 긴 순서" in sort_opt: sorted_res = sorted(display_list, key=lambda x: x.get('연기금연속순매수', 0), reverse=True)
    else: sorted_res = display_list
    for i, res in enumerate(sorted_res): draw_stock_card(res, api_key, False, f"{tab_key}_{i}")

if "gainers_df" not in st.session_state or '환산(원)' not in st.session_state.gainers_df.columns:
    df, ex_rate, fetch_time = get_us_top_gainers()
    st.session_state.gainers_df = df
    st.session_state.ex_rate = ex_rate
    st.session_state.us_fetch_time = fetch_time

# ==========================================
# 4. 메인 화면 & 사이드바 메뉴 
# ==========================================
with st.sidebar:
    st.title("📈 Jaemini PRO v4.0")
    st.markdown("단기 스윙 & 스마트머니 추적 시스템")
    st.divider()
    
    menu_list = [
        "🎛️ 메인 대시보드",
        "💸 거래대금/급증 랭킹", 
        "👨‍🦳 연기금 그림자 매매 스캐너", 
        "🗺️ 시장 자금 & 스마트머니 히트맵", 
        "🏛️ DART: 국민연금 코어픽 5%", 
        "🚀 조건 검색 스캐너 (기본)",
        "🔥 🇺🇸 미국 급등주",
        "💎 장기 가치주 스캐너", 
        "🔬 기업 정밀 분석기", 
        "⚡ 딥테크 & 테마", 
        "🚨 상/하한가 분석", 
        "📰 실시간 속보/리포트", 
        "📅 IPO / 증시 일정", 
        "👑 기간별 테마 트렌드", 
        "💰 배당 파이프라인 (TOP 300)", 
        "📊 글로벌 ETF 분석", 
        "⭐ 내 관심종목"
    ]
    selected_menu = st.radio("📌 메뉴 이동", menu_list)
    st.divider()
    api_key_input = st.secrets.get("GEMINI_API_KEY", st.text_input("Gemini API Key", type="password"))
    if api_key_input: st.success("✅ 시스템 연동 완료")
    if st.button("🔄 화면 새로고침", use_container_width=True): st.cache_data.clear(); st.rerun()

# ==========================================
# 각 탭별 실행 내용
# ==========================================

if selected_menu == "🎛️ 메인 대시보드":
    macro_data = get_macro_indicators()
    fg_data = get_fear_and_greed()
    
    st.markdown("## 🎛️ 트레이딩 관제 센터")
    m_col1, m_col2, m_col3 = st.columns([1, 1, 2])
    def draw_g(val, prev, title, steps):
        return go.Figure(go.Indicator(mode="gauge+number+delta", value=val, title={'text': title}, delta={'reference': prev}, gauge={'axis': {'range': [0, steps[-1]['range'][1]]}, 'steps': steps}))
    
    with m_col1:
        sv = [{'range':[0,15],'color':"rgba(0,255,0,0.3)"}, {'range':[15,20],'color':"rgba(255,255,0,0.3)"}, {'range':[20,50],'color':"rgba(255,0,0,0.3)"}]
        fig_v = draw_g(macro_data['VIX']['value'], macro_data['VIX']['prev'], "VIX (공포지수)", sv) if macro_data else go.Figure()
        fig_v.update_layout(margin=dict(l=10, r=10, t=60, b=10), height=200); st.plotly_chart(fig_v, use_container_width=True)
    with m_col2:
        sf = [{'range':[0,25],'color':"rgba(255,0,0,0.4)"}, {'range':[25,75],'color':"rgba(255,255,0,0.4)"}, {'range':[75,100],'color':"rgba(0,128,0,0.4)"}]
        fig_f = draw_g(fg_data['score'], fg_data['score']-fg_data['delta'], "CNN 탐욕지수", sf) if fg_data else go.Figure()
        fig_f.update_layout(margin=dict(l=10, r=10, t=60, b=10), height=200); st.plotly_chart(fig_f, use_container_width=True)
    with m_col3:
        with st.container(border=True):
            c1, c2 = st.columns(2)
            if macro_data:
                if '美 10년물 국채' in macro_data: c1.metric("🏦 美 10년물 국채", f"{macro_data['美 10년물 국채']['value']:.3f}%", f"{macro_data['美 10년물 국채']['delta']:.3f}%", delta_color="inverse")
                if '원/달러 환율' in macro_data: c2.metric("💱 원/달러 환율", f"{macro_data['원/달러 환율']['value']:.1f}원", f"{macro_data['원/달러 환율']['delta']:.1f}원", delta_color="inverse")
                c3, c4 = st.columns(2)
                if '필라델피아 반도체' in macro_data: c3.metric("💻 SOX 반도체지수", f"{macro_data['필라델피아 반도체']['value']:.1f}", f"{macro_data['필라델피아 반도체']['delta']:.1f}")
                if 'WTI 원유' in macro_data: c4.metric("🛢️ WTI 원유", f"{macro_data['WTI 원유']['value']:.2f}", f"{macro_data['WTI 원유']['delta']:.2f}")

    st.divider()
    st.subheader("📰 AI 모닝 브리핑 (Global to Local)")
    if api_key_input:
        with st.spinner("AI가 모닝 브리핑을 작성 중입니다..."):
            top_gainers = st.session_state.gainers_df['기업명'].tolist()[:5] if not st.session_state.gainers_df.empty else []
            briefing_text, gen_time = get_daily_market_briefing(macro_data, top_gainers, api_key_input)
            st.caption(f"🕒 브리핑 생성 일시: {gen_time} (API 과금 방지를 위해 3시간 주기로 갱신됩니다.)")
            st.info(briefing_text, icon="💡")
            
    st.divider()
    col_d1, col_d2 = st.columns([1, 1])
    with col_d1:
        st.subheader("⚡ 퀵 오더")
        krx_df = get_krx_stocks()
        if not krx_df.empty:
            q_opt = st.selectbox("종목 검색", ["선택"] + krx_df['Name'].tolist())
            if q_opt != "선택":
                q_code = krx_df[krx_df['Name'] == q_opt]['Code'].iloc[0]
                st.link_button(f"🛒 '{q_opt}' 네이버 호가창 바로가기", f"https://finance.naver.com/item/main.naver?code={q_code}")
                if res := analyze_technical_pattern(q_opt, q_code):
                    st.markdown(f"**상태:** {res['상태']} ｜ **진입가:** {res['진입가_가이드']:,}원 ｜ **손절가:** {res['손절가']:,}원")
    with col_d2:
        st.subheader("🚦 내 관심종목 리스크 모니터링")
        for item in st.session_state.watchlist:
            if res := analyze_technical_pattern(item['종목명'], item['티커']):
                if res['현재가'] <= res['손절가']: st.error(f"🔴 손절 이탈 위험: {item['종목명']}")
                elif res['현재가'] >= res['목표가1'] * 0.98: st.success(f"🟢 익절 도달: {item['종목명']}")

# 👈 [업데이트] 거래대금 / 급증 랭킹 추가
elif selected_menu == "💸 거래대금/급증 랭킹":
    st.subheader("💸 실시간 거래대금 및 거래량 급증 랭킹")
    headers = {'User-Agent': 'Mozilla/5.0'}
    
    t1, t2 = st.tabs(["🔥 거래대금 상위 (주도주)", "⚡ 거래량 급증 (세력 매집)"])
    with t1:
        with st.spinner("거래대금 데이터 갱신 중..."):
            try:
                res1 = requests.get("https://finance.naver.com/sise/sise_quant.naver", headers=headers, timeout=5)
                df_quant = pd.read_html(StringIO(res1.content.decode('euc-kr', 'replace')))[1].dropna(subset=['종목명'])
                df_quant = df_quant[df_quant['종목명'] != '종목명']
                st.dataframe(df_quant[['N', '종목명', '현재가', '전일비', '등락률', '거래량', '거래대금']], use_container_width=True, hide_index=True)
            except: st.warning("데이터를 불러오지 못했습니다.")
    with t2:
        with st.spinner("거래량 급증 데이터 갱신 중..."):
            try:
                res2 = requests.get("https://finance.naver.com/sise/sise_quant_high.naver", headers=headers, timeout=5)
                df_spike = pd.read_html(StringIO(res2.content.decode('euc-kr', 'replace')))[1].dropna(subset=['종목명'])
                df_spike = df_spike[df_spike['종목명'] != '종목명']
                st.dataframe(df_spike[['N', '종목명', '현재가', '전일비', '등락률', '이전거래량', '현재거래량', '급증비율']], use_container_width=True, hide_index=True)
            except: st.warning("데이터를 불러오지 못했습니다.")

elif selected_menu == "👨‍🦳 연기금 그림자 매매 스캐너":
    st.markdown("## 👨‍🦳 연기금 그림자 매매 스캐너")
    show_trading_guidelines()
    c1, c2 = st.columns(2)
    p_streak = c1.slider("최소 기관 연속 순매수 일수", 1, 5, 3)
    p_pull = c2.checkbox("✅ 20일선 눌림목만 보기", True)
    scan_limit = st.selectbox("스캔할 상위 종목 수", [50, 100], index=1)
    if st.button("🚀 스캔 시작", type="primary"):
        with st.spinner("수급 동향 파싱 중..."):
            targets = get_scan_targets(scan_limit)
            found = []
            for t in targets:
                res = analyze_technical_pattern(t[0], t[1])
                if res and res.get('연기금연속순매수',0) >= p_streak:
                    if not p_pull or "✅ 타점 근접" in res['상태']: found.append(res)
            st.session_state.pension_scan_results = found; st.rerun()
    display_sorted_results(st.session_state.pension_scan_results, "pen", api_key_input)

elif selected_menu == "🗺️ 시장 자금 & 스마트머니 히트맵":
    st.subheader("🗺️ 시장 주도주 & 스마트머니 유입 섹터 히트맵")
    t_kings = get_trading_value_kings()
    if not t_kings.empty:
        t_kings = t_kings.head(30)
        p_streaks = [get_pension_fund_trend(r['Code'])[1] for _, r in t_kings.iterrows()]
        t_kings['연속매수'] = p_streaks
        t_kings['수급상태'] = t_kings['연속매수'].apply(lambda x: "🔥매집" if x>=2 else "일반")
        t_kings['txt'] = t_kings['Name'] + "<br>" + t_kings['ChagesRatio'].map("{:+.2f}%".format) + "<br>" + t_kings['수급상태']
        fig = px.treemap(t_kings, path=[px.Constant("K-Market"), 'Sector', 'Name'], values='Amount_Ouk', color='ChagesRatio',
                         color_continuous_scale=[(0.0, '#f63538'), (0.5, '#414554'), (1.0, '#30cc5a')], color_continuous_midpoint=0, custom_data=['txt'])
        fig.update_traces(textinfo="text", texttemplate="%{customdata[0]}")
        st.plotly_chart(fig, use_container_width=True)

elif selected_menu == "🏛️ DART: 국민연금 코어픽 5%":
    st.markdown("## 🏛️ DART 연동: 국민연금 코어 픽")
    nps_df = get_nps_holdings_mock()
    t1, t2 = st.tabs(["📋 대량보유 현황", "🌟 황금 콤보 스캐너"])
    with t1: st.dataframe(nps_df, use_container_width=True, hide_index=True)
    with t2:
        if st.button("🚀 황금 콤보 교차 스캔 시작", type="primary"):
            res_list = []
            for _, r in nps_df.iterrows():
                tech = analyze_technical_pattern(r['종목명'], r['티커'])
                if tech and tech.get('연기금연속순매수',0) >= 2: res_list.append(tech)
            st.session_state.nps_combo = res_list
        display_sorted_results(st.session_state.get('nps_combo', []), "nps", api_key_input)

elif selected_menu == "🚀 조건 검색 스캐너 (기본)":
    st.subheader("🚀 실시간 조건 검색 스캐너 & 타점 검증기")
    show_beginner_guide()
    c1, c2, c3 = st.columns(3)
    cond_golden = c1.checkbox("✨ 골든크로스 / 정배열")
    cond_pullback = c2.checkbox("✅ 20일선 눌림목", True)
    cond_rsi_bottom = c3.checkbox("🔵 RSI 30 이하")
    scan_limit = st.selectbox("스캔 종목 수", [50, 100, 200])
    if st.button("🚀 병렬 스캔 시작", type="primary"):
        with st.spinner("필터링 중..."):
            targets = get_scan_targets(scan_limit)
            found = []
            for t in targets:
                res = analyze_technical_pattern(t[0], t[1])
                if res:
                    if cond_golden and "정배열" not in res['배열상태'] and "골든" not in res['배열상태']: continue
                    if cond_pullback and "✅ 타점 근접" not in res['상태']: continue
                    if cond_rsi_bottom and res['RSI'] > 30: continue
                    found.append(res)
            st.session_state.scan_results = found; st.rerun()
    display_sorted_results(st.session_state.scan_results, "basic", api_key_input)

elif selected_menu == "🔥 🇺🇸 미국 급등주":
    st.markdown("## 🔥 미국장 급등주 (+5% 이상)")
    if not st.session_state.gainers_df.empty:
        st.dataframe(st.session_state.gainers_df, use_container_width=True, hide_index=True)
        sel_opt = st.selectbox("#### 🔍 분석 대상 종목 선택", ["선택"] + st.session_state.gainers_df['종목코드'].tolist())
        if sel_opt != "선택" and api_key_input:
            c_name = st.session_state.gainers_df[st.session_state.gainers_df['종목코드']==sel_opt]['기업명'].iloc[0]
            st.info(get_company_summary(sel_opt, c_name, api_key_input))
            if st.button("✨ 국내 수혜주 매칭"):
                k_stocks = get_ai_matched_stocks(sel_opt, "N/A", "N/A", c_name, api_key_input)
                r_list = [analyze_technical_pattern(n, c) for n, c in k_stocks if analyze_technical_pattern(n, c)]
                st.session_state.us_match = r_list
            display_sorted_results(st.session_state.get('us_match', []), "us", api_key_input)

elif selected_menu == "💎 장기 가치주 스캐너":
    st.subheader("💎 장기 투자 가치주 스캐너")
    kwd = st.text_input("💡 미래 유망 기술 입력 (예: 6G, 전고체)")
    if st.button("💎 발굴 시작", type="primary") and api_key_input:
        with st.spinner("AI 텐배거 스캔 중..."):
            cands = get_longterm_value_stocks_with_ai(kwd, "상관없음", api_key_input)
            r_list = [analyze_technical_pattern(n, c) for n, c in cands if analyze_technical_pattern(n, c)]
            st.session_state.val_scan = r_list
    display_sorted_results(st.session_state.get('val_scan', []), "val", api_key_input)

elif selected_menu == "🔬 기업 정밀 분석기":
    st.subheader("🔬 기업 정밀 분석기")
    krx = get_krx_stocks()
    opts = ["🔍 종목명을 입력하세요"] + krx['Name'].tolist()
    sel = st.selectbox("종목 선택", opts)
    if sel != "🔍 종목명을 입력하세요":
        code = krx[krx['Name'] == sel]['Code'].iloc[0]
        if res := analyze_technical_pattern(sel, code): draw_stock_card(res, api_key_input, True, "detail")

# 👈 UI 정렬 문제 완벽 해결 (label_visibility="collapsed")
elif selected_menu == "⚡ 딥테크 & 테마":
    st.subheader("⚡ 딥테크 & 테마 주도주 실시간 발굴")
    cols = st.columns(4)
    themes = ["AI 반도체", "데이터센터", "바이오", "로봇"]
    for i, t in enumerate(themes):
        if cols[i].button(f"🔥 {t}", use_container_width=True): st.session_state.deep_tech_input = t; st.rerun()
    
    with st.form(key="theme_form", clear_on_submit=False):
        c1, c2 = st.columns([8, 2])
        query = c1.text_input("테마명", value=st.session_state.deep_tech_input, label_visibility="collapsed")
        submit = c2.form_submit_button("🔍 관련주 발굴", use_container_width=True)
        if submit and query:
            st.session_state.deep_tech_query = query
            with st.spinner(f"'{query}' 관련주 분석 중..."):
                t_stocks = get_theme_stocks_with_ai(query, api_key_input)
                r_list = [analyze_technical_pattern(n, c) for n, c in t_stocks if analyze_technical_pattern(n, c)]
                st.session_state.deep_tech_results = r_list
    display_sorted_results(st.session_state.deep_tech_results, "theme", api_key_input)

elif selected_menu == "🚨 상/하한가 분석":
    st.subheader("🚨 오늘의 상/하한가 분석")
    u_df, l_df = get_limit_stocks()
    cu, cl = st.columns(2)
    with cu:
        st.markdown("### 🔴 상한가 종목")
        if not u_df.empty: st.dataframe(u_df[['Name', 'Sector', 'Amount_Ouk']], use_container_width=True, hide_index=True)
        else: st.info("현재 상한가 종목이 없습니다.")
    with cl:
        st.markdown("### 🔵 하한가 종목")
        if not l_df.empty: st.dataframe(l_df[['Name', 'Sector', 'Amount_Ouk']], use_container_width=True, hide_index=True)
        else: st.info("현재 하한가 종목이 없습니다.")

# 👈 [업데이트] 실시간 증권사 리포트 종합 의견 및 원문 링크 추가
elif selected_menu == "📰 실시간 속보/리포트":
    st.subheader("📰 실시간 속보 & 리포트")
    t1, t2 = st.tabs(["🚨 특징주/속보", "📋 증권사 리포트"])
    with t1:
        update_news_state()
        for news in st.session_state.news_data[:20]: st.markdown(f"- **{news['time']}** [{news['title']}]({news['link']})")
    with t2:
        r_df = get_naver_research()
        if not r_df.empty:
            if api_key_input and st.button("🤖 AI 당일 리포트 종합 의견 및 섹터 요약", type="primary"):
                with st.spinner("리포트 종합 분석 중..."):
                    rt = "\n".join([f"[{r['증권사']}] {r['종목명']}: {r['제목']}" for _, r in r_df.head(30).iterrows()])
                    st.info(ask_gemini(f"오늘 증권가 리포트 요약:\n{rt}\n1) 핵심 섹터 2개, 2) 시장 투자의견 브리핑.", api_key_input))
            st.dataframe(r_df, column_config={"원문링크": st.column_config.LinkColumn("원문 보기")}, use_container_width=True, hide_index=True)

elif selected_menu == "📅 IPO / 증시 일정":
    st.subheader("📅 핵심 증시 일정 & 스마트머니 달력")
    t1, t2, t3 = st.tabs(["🌍 경제 지표", "🇰🇷 IPO 분석", "🧠 스마트머니 수급 달력"])
    with t1: components.html("""<iframe src="https://sslecal.investing.com?columns=exc_flags,exc_currency,exc_importance,exc_actual,exc_forecast,exc_previous&importance=2,3&features=datepicker,timezone&countries=5&calType=day&timeZone=88&lang=18" width="100%" height="600" frameborder="0"></iframe>""", height=600)
    with t2:
        # 👈 파싱 로직 업데이트
        ipo_df = get_naver_ipo_data()
        if not ipo_df.empty: st.dataframe(ipo_df, use_container_width=True, hide_index=True)
        else: st.warning("현재 IPO 일정이 없거나 데이터 구조 변경으로 수집이 지연되고 있습니다.")
    with t3:
        # 달력 네비게이션
        cc1, cc2, cc3 = st.columns([1, 8, 1])
        if cc1.button("◀ 이전 달"): st.session_state.smart_cal_month -= 1; st.rerun()
        cc2.markdown(f"<h3 style='text-align: center;'>{st.session_state.smart_cal_year}년 {st.session_state.smart_cal_month}월</h3>", unsafe_allow_html=True)
        if cc3.button("다음 달 ▶"): st.session_state.smart_cal_month += 1; st.rerun()
        
        y, m = st.session_state.smart_cal_year, st.session_state.smart_cal_month
        cal_obj = calendar.Calendar(firstweekday=6) # 일요일 시작
        weeks = cal_obj.monthdayscalendar(y, m)
        fridays = [w[5] for w in weeks if w[5] != 0]
        opex = fridays[2] if len(fridays)>=3 else fridays[-1]
        
        html = '<style>.cg{display:grid;grid-template-columns:repeat(7,1fr);gap:2px;background:#eee;border:1px solid #ccc;}.c{background:white;min-height:90px;padding:5px;font-size:12px;}.h{font-weight:bold;text-align:center;background:#f8f9fa;padding:10px;}.up{background:#e8f5e9;color:green;border-left:3px solid green;margin-top:2px;padding:2px;}.dn{background:#ffebee;color:red;border-left:3px solid red;margin-top:2px;padding:2px;}.wn{background:#fff3e0;color:orange;border-left:3px solid orange;margin-top:2px;padding:2px;}</style>'
        html += '<div class="cg"><div class="h" style="color:red;">일</div><div class="h">월</div><div class="h">화</div><div class="h">수</div><div class="h">목</div><div class="h">금</div><div class="h" style="color:blue;">토</div>'
        for w in weeks:
            for i, d in enumerate(w):
                if d == 0: html += '<div class="c"></div>'
                else:
                    ev = ""
                    if i not in [0, 6]: # 평일만 이벤트
                        if d in range(10,15): ev += '<div class="wn">⚠️ 매크로 관망</div>'
                        if d == opex: ev += '<div class="dn">🔴 美 옵션만기(하락)</div>'
                        elif d in [opex-4, opex-3, opex-2, opex-1]: ev += '<div class="wn">⚠️ 옵션만기 주간(핀닝)</div>'
                        if d in [opex+3, opex+4]: ev += '<div class="up">🟢 헤지청산(슈팅)</div>'
                    c_col = "red" if i==0 else "blue" if i==6 else "black"
                    html += f'<div class="c"><b style="color:{c_col};">{d}</b>{ev}</div>'
        html += '</div>'
        st.markdown(html, unsafe_allow_html=True)

elif selected_menu == "👑 기간별 테마 트렌드":
    st.subheader("👑 기간별 주도 테마 트렌드")
    trend_df = analyze_theme_trends()
    if not trend_df.empty: st.dataframe(trend_df, use_container_width=True, hide_index=True)

elif selected_menu == "💰 배당 파이프라인 (TOP 300)":
    st.subheader("💰 고배당 파이프라인 (TOP 300)")
    div_dfs = get_dividend_portfolio()
    t1, t2, t3 = st.tabs(["🇰🇷 국장", "🇺🇸 미장", "📈 ETF"])
    with t1: st.dataframe(div_dfs["KRX"], use_container_width=True, hide_index=True)
    with t2: st.dataframe(div_dfs["US"], use_container_width=True, hide_index=True)
    with t3: st.dataframe(div_dfs["ETF"], use_container_width=True, hide_index=True)

elif selected_menu == "📊 글로벌 ETF 분석":
    st.subheader("📊 핵심 ETF 분석")
    st.info("ETF 분석 기능 활성화 대기 중...")

elif selected_menu == "⭐ 내 관심종목":
    st.subheader("⭐ 내 관심종목")
    if st.session_state.watchlist:
        for item in st.session_state.watchlist:
            if res := analyze_technical_pattern(item['종목명'], item['티커']): draw_stock_card(res, api_key_input, False, "wl")
    else: st.info("등록된 종목이 없습니다.")
