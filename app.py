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
st.set_page_config(page_title="Jaemini PRO 터미널 v3.2", layout="wide", page_icon="📈")
st_autorefresh(interval=300000, limit=None, key="news_autorefresh")

# 세션 상태 초기화
for key in ['seen_links', 'seen_titles', 'news_data']:
    if key not in st.session_state: st.session_state[key] = set() if 'seen' in key else []
if 'watchlist' not in st.session_state: st.session_state.watchlist = load_watchlist()
if 'quick_analyze_news' not in st.session_state: st.session_state.quick_analyze_news = None
if 'scan_results' not in st.session_state: st.session_state.scan_results = None
if 'value_scan_results' not in st.session_state: st.session_state.value_scan_results = None
if 'pension_scan_results' not in st.session_state: st.session_state.pension_scan_results = None

# 딥테크 탭 검색 상태 유지
if 'deep_tech_query' not in st.session_state: st.session_state.deep_tech_query = None
if 'deep_tech_results' not in st.session_state: st.session_state.deep_tech_results = None

# ==========================================
# 2. 통합 데이터 수집 & AI 함수 모음
# ==========================================
@st.cache_data(ttl=3600)
def ask_gemini(prompt, _api_key):
    if not _api_key: return "API 키가 필요합니다."
    try:
        genai.configure(api_key=_api_key)
        # 👈 요청하신 최신 Gemini 3.1 Flash Preview 모델로 변경
        return genai.GenerativeModel('gemini-3.1-flash').generate_content(prompt).text
    except Exception as e: 
        if "429" in str(e) or "quota" in str(e).lower() or "spending cap" in str(e).lower():
            return "🚨 AI API 무료 한도가 초과되었거나 결제 한도에 도달했습니다."
        return f"AI 분석 오류: {str(e)}"

@st.cache_data(ttl=10800)
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
    (말투는 명확하고 단호한 전문 트레이더의 시각으로 작성할 것)
    
    1. 🇺🇸 **간밤의 미 증시 요약**: 매크로 데이터와 급등주를 바탕으로 한 전일 미국장 요약 (2~3줄)
    2. 🇰🇷 **국내 증시 투자의견**: 미 증시 결과와 환율/금리가 오늘 한국 코스피/코스닥 수급에 미칠 영향 (2~3줄)
    3. 🎯 **오늘의 픽 (주목할 섹터)**: 위 데이터를 볼 때, 오늘 장중 자금이 쏠릴 것으로 예상되는 국내 수혜 섹터 1~2개와 그 이유 (1줄)
    """
    return ask_gemini(prompt, _api_key)

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
        df = pd.read_html(StringIO(str(table)))[0].dropna(subset=['종목명'])
        return df[['종목명', '제목', '증권사', '작성일']].head(30)
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
            "종목명": stock_name, "티커": ticker_code, "섹터": sector_val, "현재가": current_price, "상태": status,
            "진입가_가이드": int(ma20_val), "목표가1": target_1, "목표가2": target_2, "목표가3": target_3, "손절가": int(ma20_val * 0.97),
            "거래량 급증": "🔥 거래량 터짐" if analysis_df.iloc[-10:]['Volume'].max() > (analysis_df.iloc[-10:]['Vol_MA20'].mean() * 2) else "평이함",
            "RSI": latest['RSI'], "배열상태": align_status, 
            "기관수급": inst_vol, "외인수급": forgn_vol, "개인수급": ind_vol, "장중잠정수급": intraday_est,
            "기관연속순매수": inst_streak, "외인연속순매수": forgn_streak,
            "연기금추정순매수": pension_sum, "연기금연속순매수": pension_streak,
            "PER": per, "PBR": pbr, "OBV": analysis_df['OBV'].tail(20), "차트 데이터": analysis_df.tail(20), 
            "오늘현재가": today_close, "수익률": pnl_pct, "과거검증": offset_days > 0
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

@st.cache_data(ttl=10800)
def get_naver_ipo_data():
    try:
        url = "https://finance.naver.com/sise/ipo.naver"
        res = requests.get(url, headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/122.0.0.0 Safari/537.36'}, timeout=5)
        soup = BeautifulSoup(res.content.decode('euc-kr', 'replace'), 'html.parser')
        table = soup.find('table', class_='type_2')
        if not table: return pd.DataFrame()
        trs = table.find_all('tr')
        headers, data = [], []
        for tr in trs:
            ths = tr.find_all('th')
            if ths and not headers: headers = [th.text.strip() for th in ths]
            tds = tr.find_all('td')
            if tds:
                row = [td.text.strip() for td in tds]
                if len(row) == len(headers) and row[0] and row[0] != '종목명': data.append(row)
        if not headers or not data: return pd.DataFrame()
        df = pd.DataFrame(data, columns=headers)
        valid_cols = []
        target_cols = ['종목명', '현재가', '공모가', '청약일', '상장일', '주간사']
        for tc in target_cols:
            for hc in headers:
                if tc in hc: 
                    valid_cols.append(hc)
                    break
        df = df[valid_cols]
        df.columns = [c.replace(' ', '') for c in df.columns]
        return df.head(15).reset_index(drop=True)
    except: return pd.DataFrame()

@st.cache_data(ttl=43200) 
def get_dividend_portfolio(ex_rate=1350.0):
    portfolio = {
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
            ("001450.KS", "현대해상", "결산", "6.0%"), ("000810.KS", "삼성생명", "결산", "5.0%"), ("003690.KS", "코리안리", "결산", "5.5%"),
            ("108670.KS", "LX인터내셔널", "결산", "7.0%"), ("078930.KS", "GS", "결산", "6.0%"), ("004800.KS", "효성", "결산", "6.5%"),
            ("011500.KS", "E1", "결산", "5.5%"), ("004020.KS", "고려아연", "결산", "4.0%"), ("001230.KS", "동국제강", "결산", "6.0%"),
            ("001430.KS", "세아베스틸지주", "결산", "5.5%"), ("267250.KS", "HD현대", "결산", "5.5%"), ("002960.KS", "한국쉘석유", "결산", "6.5%"),
            ("001720.KS", "신영증권", "결산", "7.0%"), ("000060.KS", "동양생명", "결산", "6.5%"), ("036530.KS", "LS", "결산", "3.5%"),
            ("034730.KS", "SK", "결산", "4.0%"), ("000880.KS", "한화", "결산", "3.5%"), ("069260.KS", "TKG휴켐스", "결산", "5.5%"),
            ("001040.KS", "영원무역", "결산", "3.5%"), ("010780.KS", "아이에스동서", "결산", "4.5%"), ("002380.KS", "KCC", "결산", "2.5%"),
            ("039130.KS", "하나투어", "결산", "3.5%"), ("003410.KS", "쌍용C&E", "분기", "7.0%"), ("006360.KS", "GS건설", "결산", "4.5%"),
            ("002990.KS", "금호건설", "결산", "5.0%"), ("000720.KS", "현대건설", "결산", "4.0%"), ("029780.KS", "삼성카드", "결산", "6.5%"),
            ("006800.KS", "미래에셋증권", "결산", "6.0%"), ("001750.KS", "한양증권", "결산", "6.5%"), ("030610.KS", "교보증권", "결산", "5.5%"),
            ("003470.KS", "유안타증권", "결산", "5.0%"), ("029530.KS", "신도리코", "결산", "6.0%"), ("067280.KS", "멀티캠퍼스", "결산", "5.5%"),
            ("012700.KS", "리드코프", "결산", "8.5%"), ("122900.KS", "아이마켓코리아", "결산", "6.0%"), ("023800.KS", "인지컨트롤스", "결산", "5.0%"),
            ("100250.KS", "진양홀딩스", "결산", "6.5%"), ("267290.KS", "경동도시가스", "결산", "5.5%"), ("071320.KS", "지역난방공사", "결산", "4.5%"),
            ("004690.KS", "삼천리", "결산", "3.5%"), ("117580.KS", "대성에너지", "결산", "4.0%"), ("017390.KS", "서울가스", "결산", "3.0%"),
            ("036460.KS", "한국가스공사", "결산", "5.0%"), ("192400.KS", "쿠쿠홀딩스", "결산", "5.5%"), ("016590.KS", "신대양제지", "결산", "4.5%"),
            ("002310.KS", "아세아제지", "결산", "5.0%"), ("009580.KS", "무림P&P", "결산", "4.5%"), ("034830.KS", "한국토지신탁", "결산", "6.0%"),
            ("018120.KS", "진로발효", "결산", "5.5%"), ("000080.KS", "하이트진로", "결산", "4.0%"), ("004990.KS", "롯데지주", "결산", "4.5%"),
            ("086280.KS", "현대글로비스", "결산", "3.5%"), ("044450.KS", "KSS해운", "결산", "4.0%"), ("029960.KS", "코엔텍", "결산", "5.0%"),
            ("004360.KS", "세방", "결산", "4.5%"), ("034950.KS", "한국기업평가", "결산", "5.5%"), ("030000.KS", "NICE평가정보", "결산", "4.0%"),
            ("005960.KS", "동부건설", "결산", "6.0%"), ("012750.KS", "에스원", "결산", "4.5%"), ("024110.KS", "기업은행", "결산", "8.0%"),
            ("060980.KS", "한라홀딩스", "결산", "5.5%"), ("013120.KS", "동원개발", "결산", "5.0%"), ("032750.KS", "삼진", "결산", "4.5%"),
            ("003650.KS", "미창석유", "결산", "5.0%"), ("014530.KS", "극동유화", "결산", "4.5%"), ("025000.KS", "KPX케미칼", "결산", "5.5%"),
            ("051630.KS", "진양산업", "결산", "6.0%"), ("051630.KS", "진양화학", "결산", "5.5%"), ("092230.KS", "KPX홀딩스", "결산", "5.0%"),
            ("015860.KS", "일진홀딩스", "결산", "4.0%"), ("072710.KS", "농심홀딩스", "결산", "3.5%"), ("084690.KS", "대상홀딩스", "결산", "4.5%"),
            ("000140.KS", "하이트진로홀딩스", "결산", "5.0%")
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
            ("LOW", "Lowe's", "분기", "1.8%"), ("SBUX", "Starbucks", "분기", "2.8%"), ("CL", "Colgate-Palmolive", "분기", "2.2%"),
            ("K", "Kellanova", "분기", "3.8%"), ("GIS", "General Mills", "분기", "3.2%"), ("HSY", "Hershey", "분기", "2.8%"),
            ("KMB", "Kimberly-Clark", "분기", "3.8%"), ("GPC", "Genuine Parts", "분기", "2.8%"), ("ED", "Consolidated Edison", "분기", "3.8%"),
            ("SO", "Southern Company", "분기", "3.8%"), ("DUK", "Duke Energy", "분기", "4.2%"), ("NEE", "NextEra Energy", "분기", "2.8%"),
            ("D", "Dominion Energy", "분기", "5.2%"), ("EPD", "Enterprise Products", "분기", "7.2%"), ("PRU", "Prudential", "분기", "4.8%"),
            ("MET", "MetLife", "분기", "3.2%"), ("AFL", "Aflac", "분기", "2.2%"), ("GILD", "Gilead Sciences", "분기", "4.2%"),
            ("BMY", "Bristol-Myers Squibb", "분기", "4.8%"), ("AMGN", "Amgen", "분기", "3.2%"), ("TXN", "Texas Instruments", "분기", "2.8%"),
            ("LMT", "Lockheed Martin", "분기", "2.8%"), ("UPS", "United Parcel Service", "분기", "4.2%"), ("DOW", "Dow Inc.", "분기", "5.5%"),
            ("EMR", "Emerson Electric", "분기", "2.2%"), ("KHC", "Kraft Heinz", "분기", "4.5%"), ("SYY", "Sysco", "분기", "2.5%"),
            ("CAG", "Conagra Brands", "분기", "4.8%"), ("CPB", "Campbell Soup", "분기", "3.5%"), ("SJM", "J.M. Smucker", "분기", "3.2%"),
            ("TAP", "Molson Coors", "분기", "2.8%"), ("TRV", "Travelers", "분기", "2.0%"), ("ALL", "Allstate", "분기", "2.2%"),
            ("DFS", "Discover Financial", "분기", "2.5%"), ("HIG", "Hartford Financial", "분기", "2.0%"), ("PFG", "Principal Financial", "분기", "3.5%"),
            ("C", "Citigroup", "분기", "3.5%"), ("JPM", "JPMorgan Chase", "분기", "2.5%"), ("BAC", "Bank of America", "분기", "2.5%"),
            ("MS", "Morgan Stanley", "분기", "3.0%"), ("GS", "Goldman Sachs", "분기", "2.8%"), ("WFC", "Wells Fargo", "분기", "2.5%"),
            ("USB", "U.S. Bancorp", "분기", "4.5%"), ("PNC", "PNC Financial", "분기", "3.8%"), ("TFC", "Truist Financial", "분기", "5.2%"),
            ("FITB", "Fifth Third Bancorp", "분기", "4.0%"), ("KEY", "KeyCorp", "분기", "5.5%"), ("CF", "CF Industries", "분기", "2.5%"),
            ("MTB", "M&T Bank", "분기", "3.5%"), ("RF", "Regions Financial", "분기", "4.5%"), ("HBAN", "Huntington Bancshares", "분기", "4.8%"),
            ("CMA", "Comerica", "분기", "5.5%"), ("ZION", "Zions Bancorporation", "분기", "4.0%"), ("VLO", "Valero Energy", "분기", "2.5%"),
            ("COP", "ConocoPhillips", "분기", "3.0%"), ("PSX", "Phillips 66", "분기", "3.5%"), ("MPC", "Marathon Petroleum", "분기", "2.0%"),
            ("OKE", "ONEOK", "분기", "5.5%"), ("WMB", "Williams Companies", "분기", "5.0%"), ("ET", "Energy Transfer", "분기", "8.0%"),
            ("MMP", "Magellan Midstream", "분기", "6.5%"), ("LYB", "LyondellBasell", "분기", "5.0%"), ("DLR", "Digital Realty", "분기", "3.5%"),
            ("AVB", "AvalonBay", "분기", "3.0%"), ("EQIX", "Equinix", "분기", "2.0%"), ("PLD", "Prologis", "분기", "3.0%"),
            ("SPG", "Simon Property Group", "분기", "5.5%"), ("PSA", "Public Storage", "분기", "4.5%"), ("VTR", "Ventas", "분기", "4.0%"),
            ("EQR", "Equity Residential", "분기", "4.0%"), ("ESS", "Essex Property", "분기", "4.5%"), ("MAA", "Mid-America Apartment", "분기", "3.5%"),
            ("UDR", "UDR Inc.", "분기", "4.5%")
        ],
        "ETF": [
            ("SCHD", "US SCHD (고배당)", "분기", "3.6%"), ("JEPI", "US JEPI (프리미엄)", "월배당", "7.5%"), ("JEPQ", "US JEPQ (프리미엄)", "월배당", "9.0%"),
            ("VYM", "US VYM (고배당)", "분기", "3.0%"), ("SPYD", "US SPYD (S&P500 고배당)", "분기", "4.8%"), ("DGRO", "US DGRO (배당성장)", "분기", "2.4%"),
            ("QYLD", "US QYLD (커버드콜)", "월배당", "11.5%"), ("XYLD", "US XYLD (S&P 커버드콜)", "월배당", "9.5%"), ("RYLD", "US RYLD (러셀 커버드콜)", "월배당", "12.0%"),
            ("DIVO", "US DIVO (배당+옵션)", "월배당", "4.8%"), ("VNQ", "US VNQ (리츠)", "분기", "4.2%"), ("VIG", "US VIG (배당성장)", "분기", "2.0%"),
            ("NOBL", "US NOBL (배당귀족)", "분기", "2.2%"), ("SDY", "US SDY (배당귀족)", "분기", "2.8%"), ("HDV", "US HDV (핵심배당)", "분기", "3.8%"),
            ("PEY", "US PEY (고배당)", "월배당", "4.8%"), ("DHS", "US DHS (고배당)", "월배당", "3.8%"), ("DVY", "US DVY (우량배당)", "분기", "3.8%"),
            ("FVD", "US FVD (가치배당)", "분기", "2.2%"), ("SPHD", "US SPHD (저변동 고배당)", "월배당", "4.2%"), ("DIV", "US DIV (글로벌 배당)", "월배당", "6.2%"),
            ("RDIV", "US RDIV (리스크가중)", "분기", "4.2%"), ("ALTY", "US ALTY (대안수익)", "월배당", "7.5%"), ("VPU", "US VPU (유틸리티)", "분기", "3.2%"),
            ("XLU", "US XLU (유틸리티)", "분기", "3.2%"), ("PFF", "US PFF (우선주)", "월배당", "6.2%"), ("PGX", "US PGX (우선주)", "월배당", "6.0%"),
            ("KBWD", "US KBWD (금융 배당)", "월배당", "11.0%"), ("PGF", "US PGF (금융 우선주)", "월배당", "6.5%"), ("VRP", "US VRP (변동금리 우선주)", "월배당", "5.8%"),
            ("PFFD", "US PFFD (우선주)", "월배당", "6.2%"), ("FPE", "US FPE (우선주)", "월배당", "6.0%"), ("DGRW", "US DGRW (배당성장)", "월배당", "2.0%"),
            ("IGRO", "US IGRO (글로벌 배당성장)", "분기", "3.0%"), ("VMI", "US VMI (배당가치)", "분기", "3.5%"), ("VIGI", "US VIGI (인터내셔널 배당)", "분기", "2.2%"),
            ("VYMI", "US VYMI (인터내셔널 고배당)", "분기", "4.8%"), ("IDV", "US IDV (인터내셔널 고배당)", "분기", "5.5%"), ("PID", "US PID (인터내셔널 배당)", "분기", "4.0%"),
            ("DON", "US DON (중형주 배당)", "월배당", "3.2%"), ("DES", "US DES (소형주 배당)", "월배당", "3.5%"), ("DGRS", "US DGRS (소형주 배당성장)", "월배당", "2.5%"),
            ("DTD", "US DTD (총배당)", "월배당", "2.5%"), ("DTH", "US DTH (인터내셔널 고배당)", "월배당", "4.5%"), ("DWM", "US DWM (인터내셔널 배당)", "월배당", "3.5%"),
            ("DWMF", "US DWMF (멀티팩터 배당)", "분기", "3.0%"), ("DXJ", "US DXJ (일본 헷지 배당)", "분기", "3.2%"), ("EUDV", "US EUDV (유럽 배당)", "분기", "4.5%"),
            ("LVL", "US LVL (글로벌 배당)", "월배당", "6.0%"), ("HDEF", "US HDEF (인터내셔널 헷지 배당)", "분기", "5.5%"), ("IQLT", "US IQLT (인터내셔널 퀄리티)", "반기", "3.0%"),
            ("QDF", "US QDF (퀄리티 배당)", "분기", "2.5%"), ("REGL", "US REGL (중형주 배당귀족)", "분기", "2.8%"), ("SCHY", "US SCHY (인터내셔널 고배당)", "반기", "4.2%"),
            ("IHDG", "US IHDG (인터내셔널 헷지 배당성장)", "분기", "2.5%"), ("DIVZ", "US DIVZ (가치 배당)", "월배당", "3.5%"), ("IDVO", "US IDVO (인터내셔널 DIVO)", "월배당", "5.5%"),
            ("QDTE", "US QDTE (0DTE 나스닥)", "주배당", "20.0%"), ("XDTE", "US XDTE (0DTE S&P)", "주배당", "18.0%"), ("RDTE", "US RDTE (0DTE 러셀)", "주배당", "22.0%"),
            ("TSLY", "US TSLY (테슬라 커버드콜)", "월배당", "45.0%"), ("NVDY", "US NVDY (엔비디아 커버드콜)", "월배당", "50.0%"), ("AMZY", "US AMZY (아마존 커버드콜)", "월배당", "30.0%"),
            ("FBY", "US FBY (메타 커버드콜)", "월배당", "35.0%"), ("CONY", "US CONY (코인베이스 커버드콜)", "월배당", "60.0%"), ("GOOY", "US GOOY (구글 커버드콜)", "월배당", "25.0%"),
            ("MSFO", "US MSFO (MS 커버드콜)", "월배당", "20.0%"), ("NFLP", "US NFLP (넷플릭스 커버드콜)", "월배당", "25.0%"), ("YMAX", "US YMAX (커버드콜 펀드)", "월배당", "35.0%"),
            ("YMAG", "US YMAG (매그니피센트 커버드콜)", "월배당", "30.0%"), ("FEPI", "US FEPI (빅테크 커버드콜)", "월배당", "25.0%"),
            ("458730.KS", "TIGER 미국배당다우존스", "월배당", "3.8%"), ("161510.KS", "ARIRANG 고배당주", "결산", "6.5%"), ("458760.KS", "TIGER 미국배당+7%", "월배당", "10.5%"),
            ("448550.KS", "ACE 미국배당다우존스", "월배당", "3.8%"), ("466950.KS", "KODEX 미국배당프리미엄", "월배당", "7.5%"), ("329200.KS", "TIGER 부동산인프라", "분기", "7.0%"),
            ("091220.KS", "KODEX 은행", "결산", "6.5%"), ("211560.KS", "TIGER 배당성장", "분기", "4.5%"), ("271560.KS", "ARIRANG 미국고배당", "분기", "4.0%"),
            ("433330.KS", "TIMEFOLIO 코리아플러스", "월배당", "5.5%"), ("460330.KS", "SOL 미국배당다우존스", "월배당", "3.8%"), ("276970.KS", "KODEX 배당가치", "결산", "5.5%"),
            ("213610.KS", "TIGER 코스피고배당", "결산", "6.0%"), ("379800.KS", "KODEX 미국배당프리미엄액티브", "월배당", "7.5%"), ("104530.KS", "KODEX 고배당", "결산", "5.5%"),
            ("266140.KS", "TIGER 글로벌배당", "분기", "3.5%"), ("415920.KS", "TIGER 글로벌멀티에셋", "월배당", "4.5%"), ("402970.KS", "TIGER 미국배당+3%프리미엄", "월배당", "6.5%"),
            ("368590.KS", "KBSTAR 200고배당커버드콜", "월배당", "7.5%"), ("222170.KS", "ARIRANG 고배당저변동", "결산", "5.5%"), ("148020.KS", "KBSTAR 200고배당", "결산", "5.5%"),
            ("232080.KS", "TIGER 코스닥150", "결산", "1.5%"), ("256450.KS", "ARIRANG 퀄리티", "결산", "4.5%"), ("433320.KS", "TIGER 글로벌리츠", "분기", "4.5%"),
            ("357870.KS", "TIGER 부동산인프라고배당", "분기", "6.5%"), ("139260.KS", "TIGER 200 IT", "결산", "1.5%"), ("289040.KS", "KODEX FnKorea50", "결산", "2.0%"),
            ("304660.KS", "KODEX 미국채울트라30년선물(H)", "결산", "0.0%"), ("252650.KS", "KODEX 200선물인버스2X", "결산", "0.0%")
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
    base_info = f"(진단: {tech_result['상태']} ｜ 상세 진단: {align_status_short} ｜ 외인: {f_trend} ｜ 기관: {i_trend} ｜ 개인: {p_trend} ｜ RSI: {tech_result['RSI']:.1f})"
    header_block = f"{status_emoji} {tech_result['종목명']} / {sector_info} / {tech_result['현재가']:,}원"
    expander_title = f"{header_block} ｜ {base_info}"
    
    with st.expander(expander_title, expanded=is_expanded):
        if tech_result.get('과거검증'):
            pnl = tech_result['수익률']
            color = "#ff4b4b" if pnl > 0 else "#1f77b4"
            bg_color = "rgba(255, 75, 75, 0.1)" if pnl > 0 else "rgba(31, 119, 180, 0.1)"
            st.markdown(f"""<div style="background-color: {bg_color}; padding: 15px; border-radius: 10px; margin-bottom: 15px; border: 1px solid {color};">
                <h3 style="margin:0; color: {color};">⏰ 타임머신 검증 결과</h3>
                <p style="margin:5px 0 0 0; font-size: 16px;">스캔 당시 가격 <b>{tech_result['현재가']:,}원</b> ➡️ 오늘 현재 가격 <b>{tech_result['오늘현재가']:,}원</b> <span style="font-size: 20px; font-weight: bold; color: {color};">({pnl:+.2f}%)</span></p>
            </div>""", unsafe_allow_html=True)
            
        col_btn1, col_btn2 = st.columns([8, 2])
        col_btn1.markdown(f"**상세 진단:** {tech_result['배열상태']}")
        is_in_wl = any(x['티커'] == tech_result['티커'] for x in st.session_state.watchlist)
        if col_btn2.button("⭐ 관심종목 추가" if not is_in_wl else "🌟 추가됨", disabled=is_in_wl, key=f"star_{tech_result['티커']}_{key_suffix}"):
            st.session_state.watchlist.append({'종목명': tech_result['종목명'], '티커': tech_result['티커']})
            save_watchlist(st.session_state.watchlist)
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
        
        with c7: 
            st.markdown(f"🕵️ **당시 수급 동향 (5일 누적)**<br>**외국인:** `{tech_result['외인수급']}` ｜ **기관:** `{tech_result['기관수급']}` ｜ **개인:** `{tech_result.get('개인수급', '조회불가')}`", unsafe_allow_html=True)
            if tech_result.get('장중잠정수급'):
                id_data = tech_result['장중잠정수급']
                f_val_str = f"🔥+{id_data['forgn']:,}" if id_data['forgn'] > 0 else f"💧{id_data['forgn']:,}"
                i_val_str = f"🔥+{id_data['inst']:,}" if id_data['inst'] > 0 else f"💧{id_data['inst']:,}"
                st.markdown(f"⚡ **오늘 장중 실시간 수급 (잠정)**<br>외인 `{f_val_str}` ｜ 기관 `{i_val_str}` `({id_data['time']} 기준)`", unsafe_allow_html=True)
            if tech_result.get('연기금연속순매수', 0) >= 3:
                st.markdown(f"👴 **스마트머니 시그널:** <span style='color:orange; font-weight:bold;'>🔥 기관(연기금 추정) {tech_result['연기금연속순매수']}일 연속 순매수 포착</span>", unsafe_allow_html=True)
        
        if api_key_str:
            st.markdown("<br>", unsafe_allow_html=True)
            if st.button(f"🤖 '{tech_result['종목명']}' AI 딥다이브 정밀 분석 (차트+재무+컨센서스)", key=f"ai_btn_{tech_result['티커']}_{key_suffix}"):
                with st.spinner("AI가 차트, 수급, 재무제표 및 컨센서를 종합 분석 중입니다... (약 5~10초 소요)"):
                    if str(tech_result['티커']).isdigit():
                        fin_df, peer_df, cons = get_financial_deep_data(tech_result['티커'])
                        fin_text = fin_df.to_string() if fin_df is not None and not fin_df.empty else "재무 데이터 없음"
                        peer_text = peer_df.to_string() if peer_df is not None and not peer_df.empty else "비교 데이터 없음"
                        prompt = f"""
                        당신은 여의도 최고의 퀀트 애널리스트이자 펀드매니저입니다. '{tech_result['종목명']}' 분석 리포트를 마크다운으로 작성하세요.
                        [기술적 지표 및 수급]
                        - 현재가: {curr}원, 20일선: {tech_result['진입가_가이드']}원 (상태: {tech_result['상태']})
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
                        st.success("✅ AI 정밀 분석 완료!")
                        st.markdown(ask_gemini(prompt, api_key_str))
                        with st.expander(f"📊 '{tech_result['종목명']}' 수집된 로우 데이터 (Raw Data) 확인"):
                            st.write("✅ **증권사 목표가 컨센서스:**", cons)
                            if fin_df is not None: st.dataframe(fin_df)
                            if peer_df is not None: st.dataframe(peer_df)
                    else:
                        prompt = f"전문 트레이더 관점에서 '{tech_result['종목명']}'을(를) 분석해주세요.\n[데이터] 현재가:{curr}, 20일선:{tech_result['진입가_가이드']}, RSI:{tech_result['RSI']:.1f}\n1. ⚡ 단기 트레이딩 관점\n2. 🛡️ 스윙/가치 투자 관점\n3. 🎯 종합 요약 (1줄):"
                        st.success("✅ AI 분석 완료!")
                        st.markdown(ask_gemini(prompt, api_key_str))
        
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
                
                st.markdown("#### 📅 일별 시세 및 매매동향 (최근 10일)")
                daily_df = get_daily_sise_and_investor(tech_result['티커'])
                if not daily_df.empty: st.dataframe(daily_df, use_container_width=True, hide_index=True)
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

if "gainers_df" not in st.session_state or '환산(원)' not in st.session_state.gainers_df.columns:
    df, ex_rate, fetch_time = get_us_top_gainers()
    st.session_state.gainers_df = df
    st.session_state.ex_rate = ex_rate
    st.session_state.us_fetch_time = fetch_time

# ==========================================
# 4. 메인 화면 & 사이드바 메뉴 
# ==========================================
with st.sidebar:
    st.title("📈 Jaemini PRO v3.2")
    st.markdown("풀옵션 단기 스윙 & 스마트머니 추적 시스템")
    st.divider()
    
    menu_list = [
        "🎛️ 메인 대시보드",
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
# 각 탭별 실행 내용
# ==========================================

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
            st.info(briefing_text, icon="💡")
    else:
        st.warning("API 키를 입력하시면 AI가 작성하는 실시간 글로벌-국내 증시 브리핑을 볼 수 있습니다.")

    st.divider()
    
    col_dash1, col_dash2 = st.columns([1, 1])
    with col_dash1:
        st.subheader("⚡ 퀵 오더 (종목 직접 검색)")
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
                    else: st.caption("데이터 없음")

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
    st.write("거래대금이 터진 종목들 중 기관 매수세가 동반된 종목을 파악합니다.")
    
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

elif selected_menu == "🚀 조건 검색 스캐너 (기본)":
    st.subheader("🚀 실시간 조건 검색 스캐너 & 과거 타점 검증기")
    show_beginner_guide()
    show_trading_guidelines()
    
    col_c1, col_c2, col_c3 = st.columns(3)
    with col_c1: cond_golden = st.checkbox("✨ 골든크로스 / 정배열 초입"); cond_pullback = st.checkbox("✅ 20일선 눌림목 (타점 근접)", value=True)
    with col_c2: cond_rsi_bottom = st.checkbox("🔵 RSI 30 이하 (낙폭과대)"); cond_vol_spike = st.checkbox("🔥 최근 거래량 급증 (세력 의심)")
    with col_c3: cond_twin_buy = st.checkbox("🐋 외인/기관 쌍끌이 순매수")
    scan_c1, scan_c2 = st.columns(2)
    with scan_c1: scan_limit = st.selectbox("스캔할 상위 종목 수", [50, 100, 200, 300], index=1)
    with scan_c2:
        offset_options = {"현재 (실시간 스캔)": 0, "3일 전 (타임머신 검증)": 3, "5일 전 검증": 5}
        offset_days = offset_options[st.selectbox("⏰ 타임머신 검증 모드", list(offset_options.keys()))]
    if st.button("🚀 쾌속 병렬 스캔 시작", type="primary", use_container_width=True):
        with st.spinner(f"⚡ {scan_limit}개 종목 고속 필터링 중..."):
            targets = get_scan_targets(scan_limit)
            if not targets: st.error("종목 데이터를 불러오지 못했습니다.")
            else:
                progress_bar = st.progress(0)
                status_text = st.empty()
                found_results = []
                completed, total = 0, len(targets)
                def process_stock(target):
                    name, code = target
                    time.sleep(0.1) 
                    res = analyze_technical_pattern(name, code, offset_days=offset_days)
                    if res:
                        if cond_golden and "🔥 완벽 정배열" not in res['배열상태'] and "✨ 5-20 골든크로스" not in res['배열상태']: return None
                        if cond_pullback and res['상태'] != "✅ 타점 근접 (분할 매수)": return None
                        if cond_rsi_bottom and res['RSI'] > 30: return None
                        if cond_vol_spike and res['거래량 급증'] != "🔥 거래량 터짐": return None
                        if cond_twin_buy and ("+" not in str(res['기관수급']) or "+" not in str(res['외인수급'])): return None
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

elif selected_menu == "🔥 🇺🇸 미국 급등주":
    st.markdown("## 🔥 미국장 급등주 (+5% 이상)")
    col1, col2 = st.columns([1, 1.2], gap="large")
    with col1:
        if 'us_fetch_time' in st.session_state: st.caption(f"⏱️ {st.session_state.us_fetch_time} (한국시간)")
        if not st.session_state.gainers_df.empty:
            tickers_list = st.session_state.gainers_df['종목코드'].tolist()
            sector_dict = get_all_sector_info(tuple(tickers_list), api_key_input) if api_key_input else {t: ("분석 대기", "분석 대기") for t in tickers_list}
            display_df = st.session_state.gainers_df[['종목코드', '기업명', '현재가', '환산(원)', '등락률']].copy()
            opts = ["🔍 종목 선택"]
            for i, row in display_df.iterrows():
                sec, ind = sector_dict.get(row['종목코드'], ("분석 불가", "분석 불가"))
                opts.append(f"{row['종목코드']} ({row['기업명']}) - ({sec} / {ind})")
            st.dataframe(display_df, use_container_width=True, hide_index=True)
            sel_opt = st.selectbox("#### 🔍 분석 대상 종목 선택", opts)
            sel_tick = "N/A" if sel_opt == "🔍 종목 선택" else sel_opt.split(" ")[0]
        else: sel_tick = "N/A"; st.info("현재 +5% 이상 급등한 종목이 없습니다.")
    
    with col2:
        st.subheader("🎯 연관 테마 매칭 및 타점 진단")
        if sel_tick != "N/A" and api_key_input:
            sec, ind = sector_dict.get(sel_tick, ("분석 불가", "분석 불가"))
            comp_name = sel_opt.split(" - ")[0]
            st.markdown(f"**🏷️ 섹터 정보:** `{sec}` / `{ind}`")
            with st.spinner(f"🔍 기업 개요 및 분석 중..."):
                with st.container(border=True): st.markdown(f"**🏢 비즈니스 모델 요약**\n> {get_company_summary(sel_tick, comp_name, api_key_input)}")
            with st.spinner('✨ AI 추천 국내 수혜주 타점 정밀 분석 중... (병렬 처리)'):
                kor_stocks = get_ai_matched_stocks(sel_tick, sec, ind, comp_name, api_key_input)
                if kor_stocks:
                    theme_res_list = []
                    def fetch_and_analyze(item):
                        name, code = item
                        return analyze_technical_pattern(name, code)
                    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
                        for res in executor.map(fetch_and_analyze, kor_stocks):
                            if res: theme_res_list.append(res)
                    display_sorted_results(theme_res_list, tab_key="t1", api_key=api_key_input)

elif selected_menu == "💎 장기 가치주 스캐너":
    st.subheader("💎 장기 투자 가치주 & 텐배거 유망주 스캐너")
    hot_themes = get_trending_themes_with_ai(api_key_input) if api_key_input else []
    all_themes = list(dict.fromkeys(hot_themes + ["전고체 배터리", "온디바이스 AI", "자율주행", "우주항공(UAM)"]))
    col_v1, col_v2 = st.columns([2, 1])
    with col_v1:
        sel_t = st.selectbox("💡 미래 유망 기술 선택:", all_themes + ["✏️ 직접 입력..."])
        tech_keyword = st.text_input("직접 입력:", placeholder="예: 6G 통신") if sel_t == "✏️ 직접 입력..." else sel_t
    with col_v2: cap_size = st.selectbox("🏢 기업 규모 선택:", ["상관없음", "대형주", "중소형주"], index=0)
    val_strictness = st.radio("투자 성향", ["💎 수익/자산 좋고 바닥인 가치주", "🚀 기술력 압도적인 성장주", "🔥 적자여도 미래만 보는 야수의 심장"])
    max_per, max_pbr = (15.0, 1.5) if "가치주" in val_strictness else (40.0, 4.0) if "성장주" in val_strictness else (9999.0, 9999.0)

    if st.button("💎 병렬 가치주 스캔 시작", type="primary", use_container_width=True):
        if not api_key_input: st.warning("API 키를 입력해주세요.")
        else:
            with st.spinner("스캔 중..."):
                candidates = get_longterm_value_stocks_with_ai(tech_keyword, cap_size, api_key_input)
                if not candidates: st.error("관련 기업을 찾지 못했습니다.")
                else:
                    progress_bar = st.progress(0)
                    value_results = []
                    completed, total = 0, len(candidates)
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
                        for future in concurrent.futures.as_completed({executor.submit(process_fundamental, c): c for c in candidates}):
                            res = future.result()
                            completed += 1
                            if res: value_results.append(res)
                            progress_bar.progress(completed / total)
                    st.session_state.value_scan_results = value_results
                    st.rerun()
    if st.session_state.value_scan_results is not None: display_sorted_results(st.session_state.value_scan_results, tab_key="t3", api_key=api_key_input)

elif selected_menu == "🔬 기업 정밀 분석기":
    st.subheader("🔬 기업 정밀 분석기 (기술적 타점 + 펀더멘털)")
    krx_df = get_krx_stocks()
    if not krx_df.empty:
        opts = ["🔍 분석할 국내 종목을 입력하세요."] + (krx_df['Name'].astype(str) + " (" + krx_df['Code'].astype(str) + ")").tolist()
        query = st.selectbox("👇 종목명 또는 초성을 입력하여 검색하세요:", opts)
        if query != "🔍 분석할 국내 종목을 입력하세요.":
            searched_name = query.rsplit(" (", 1)[0]
            searched_code = query.rsplit("(", 1)[-1].replace(")", "").strip()
            with st.spinner(f"📡 '{searched_name}' 타점 분석 중..."):
                res = analyze_technical_pattern(searched_name, searched_code)
            if res: draw_stock_card(res, api_key_str=api_key_input, is_expanded=True, key_suffix="t4")

elif selected_menu == "⚡ 딥테크 & 테마":
    st.subheader("⚡ 딥테크 & 테마 주도주 실시간 발굴기")
    hot_themes_tab5 = get_trending_themes_with_ai(api_key_input) if api_key_input else ["AI 반도체", "데이터센터", "바이오", "로봇"]
    cols_d = st.columns(4)
    
    for idx, theme in enumerate(hot_themes_tab5[:4]):
        if cols_d[idx].button(f"🔥 {theme}", use_container_width=True): 
            st.session_state.deep_tech_query = theme
            st.session_state.deep_tech_results = None 
            st.rerun()
            
    custom_query = st.text_input("직접 테마 입력 (입력 후 엔터):", value="")
    if custom_query:
        st.session_state.deep_tech_query = custom_query
        st.session_state.deep_tech_results = None
        st.rerun()

    if st.session_state.deep_tech_query and st.session_state.deep_tech_results is None and api_key_input:
        with st.spinner(f"✨ '{st.session_state.deep_tech_query}' 수혜주 진단 중..."):
            theme_stocks = get_theme_stocks_with_ai(st.session_state.deep_tech_query, api_key_input)
            if theme_stocks:
                theme_res_list = [res for name, code in theme_stocks if (res := analyze_technical_pattern(name, code))]
                st.session_state.deep_tech_results = theme_res_list
                st.rerun()
                
    if st.session_state.deep_tech_results is not None:
        st.markdown(f"#### 🔎 '{st.session_state.deep_tech_query}' 관련주 분석 결과")
        display_sorted_results(st.session_state.deep_tech_results, tab_key="t5", api_key=api_key_input)

elif selected_menu == "🚨 상/하한가 분석":
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
            st.dataframe(display_upper, use_container_width=True, hide_index=True)
            sel_u = st.selectbox("상한가 종목 타점 확인:", ["선택"] + upper_df['Name'].tolist(), key="sel_u")
            if sel_u != "선택":
                k_code = get_krx_stocks()[get_krx_stocks()['Name'] == sel_u]['Code'].iloc[0]
                if res := analyze_technical_pattern(sel_u, k_code): draw_stock_card(res, api_key_str=api_key_input, is_expanded=True, key_suffix="t6_u")
    with col_l:
        st.markdown("### 🔵 하한가 종목")
        if not lower_df.empty: st.dataframe(lower_df[['Name', 'Sector', 'Amount_Ouk']], use_container_width=True, hide_index=True)

elif selected_menu == "📰 실시간 속보/리포트":
    st.subheader("📰 실시간 속보 및 증권사 리포트 터미널")
    news_sub1, news_sub2 = st.tabs(["🚨 실시간 특징주/속보", "📋 증권사 종목 리포트"])
    with news_sub1:
        if st.button("🔄 속보 리로드"): 
            get_latest_naver_news.clear(); st.session_state.news_data = []; st.rerun()
        with st.spinner("뉴스를 불러오는 중..."): update_news_state()
        krx_dict = {row['Name']: row['Code'] for _, row in get_krx_stocks().iterrows() if len(str(row['Name'])) > 1}
        for i, news in enumerate(st.session_state.news_data[:50]):
            title = news['title']
            found_comps = [(name, code) for name, code in krx_dict.items() if name in title][:1]
            with st.container(border=True):
                cols = st.columns([1, 6, 2, 1])
                cols[0].markdown(f"**🕒 {news['time']}**")
                cols[1].markdown(f"{title}")
                with cols[2]:
                    if found_comps:
                        if st.button(f"🔍 {found_comps[0][0]} 분석", key=f"qa_{i}"):
                            res = analyze_technical_pattern(found_comps[0][0], found_comps[0][1])
                            if res: draw_stock_card(res, api_key_str=api_key_input, is_expanded=True, key_suffix=f"news_qa_{i}")
                cols[3].link_button("원문🔗", news['link'])
    with news_sub2:
        st.markdown("### 📋 오늘의 실시간 증권사 리포트")
        st.dataframe(get_naver_research(), use_container_width=True, hide_index=True)

elif selected_menu == "📅 IPO / 증시 일정":
    st.subheader("📅 핵심 증시 일정 & IPO 공모주 분석")
    cal_tab1, cal_tab2 = st.tabs(["🌍 글로벌 주요 경제 지표", "🇰🇷 국내 신규 상장(IPO) 분석"])
    with cal_tab1: components.html("""<iframe scrolling="yes" allowtransparency="true" frameborder="0" src="https://s.tradingview.com/embed-widget/events/?locale=kr&importanceFilter=-1%2C0%2C1&currencyFilter=USD%2CKRW%2CCNY%2CEUR&colorTheme=light" style="box-sizing: border-box; height: 600px; width: 100%;"></iframe>""", height=600)
    with cal_tab2:
        with st.spinner("IPO 일정을 긁어오는 중..."):
            ipo_df = get_naver_ipo_data()
        if not ipo_df.empty:
            st.dataframe(ipo_df, use_container_width=True, hide_index=True)
            if api_key_input and st.button("🤖 AI 공모주 옥석 가리기", type="primary"):
                st.success(ask_gemini(f"다음 상장 일정: {ipo_df[['종목명', '상장일']].to_string()}\n가장 따상 가능성 높은 1~2개 꼽고 이유 3줄 평가.", api_key_input))
        else: st.error("IPO 데이터 수집 지연중. 네이버 금융 우회 시도 실패.")

elif selected_menu == "👑 기간별 테마 트렌드":
    st.subheader("👑 기간별 주도 테마 트렌드 (1M/3M/6M)")
    with st.spinner("역산 중..."): trend_df = analyze_theme_trends()
    if not trend_df.empty:
        period = st.radio("조회 기간", ["1M", "3M", "6M"], horizontal=True)
        col_c1, col_c2 = st.columns(2)
        v_col, r_col = f"{period}거래대금", f"{period}수익률"
        with col_c1:
            v_df = trend_df.sort_values(v_col, ascending=True).tail(10).copy()
            v_df['lbl'] = v_df[v_col].apply(lambda x: f"{int(round(x)):,}억")
            fig_v = px.bar(v_df, x=v_col, y='테마', orientation='h', text='lbl')
            fig_v.update_traces(marker_color='#1f77b4', textposition='outside')
            fig_v.update_layout(xaxis_title="거래대금", height=450)
            st.plotly_chart(fig_v, use_container_width=True)
        with col_c2:
            r_df = trend_df.sort_values(r_col, ascending=True).tail(10).copy()
            r_df['lbl'] = r_df[r_col].apply(lambda x: f"{int(round(x)):+}%")
            fig_r = px.bar(r_df, x=r_col, y='테마', orientation='h', text='lbl')
            fig_r.update_traces(marker_color=['#ff4b4b' if v>0 else '#1f77b4' for v in r_df[r_col]], textposition='outside')
            fig_r.update_layout(xaxis_title="수익률", height=450)
            st.plotly_chart(fig_r, use_container_width=True)

# 👈 [핵심 업데이트] 배당 파이프라인 정렬 로직 추가
elif selected_menu == "💰 배당 파이프라인 (TOP 300)":
    st.subheader("💰 고배당주 & ETF 파이프라인 (TOP 300)")
    with st.spinner("실시간 데이터 다운로드 중..."): 
        div_dfs = get_dividend_portfolio(st.session_state.get('ex_rate', 1350.0))
    
    sort_opt = st.radio("⬇️ 정렬 기준", ["기본 (분류순)", "배당수익률 높은순", "현재가 높은순", "현재가 낮은순"], horizontal=True)
    
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
            clean_ticker = selected_ticker.replace(".KS", "")
            res = analyze_technical_pattern(selected_etf_str.split(" (")[1].replace(")", ""), clean_ticker)
            if res: draw_stock_card(res, api_key_str=api_key_input, is_expanded=True)
            else: st.error("데이터를 불러오지 못했습니다.")

elif selected_menu == "⭐ 내 관심종목":
    st.subheader("⭐ 나만의 관심종목 (Watchlist)")
    if not st.session_state.watchlist: st.info("추가된 종목이 없습니다.")
    else:
        col1, col2 = st.columns([8, 2])
        if col2.button("🗑️ 관심종목 모두 지우기", use_container_width=True): 
            st.session_state.watchlist = []; save_watchlist([]); st.rerun()
        for i, item in enumerate(st.session_state.watchlist):
            if res := analyze_technical_pattern(item['종목명'], item['티커']):
                draw_stock_card(res, api_key_str=api_key_input, is_expanded=False, key_suffix=f"wl_{i}")
