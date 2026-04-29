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
        except: return []
    return []

def save_watchlist(wl):
    try:
        with open(WATCHLIST_FILE, "w", encoding="utf-8") as f: json.dump(wl, f, ensure_ascii=False, indent=4)
    except Exception as e: st.error(f"관심종목 저장 실패: {e}")

# ==========================================
# 1. 초기 설정 
# ==========================================
st.set_page_config(page_title="Jaemini PRO 터미널 v6.0", layout="wide", page_icon="📈")
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

# 딥테크 탭 검색 상태 유지
if 'deep_tech_query' not in st.session_state: st.session_state.deep_tech_query = None
if 'deep_tech_results' not in st.session_state: st.session_state.deep_tech_results = None
if 'deep_tech_input' not in st.session_state: st.session_state.deep_tech_input = ""
if 'deep_tech_brief' not in st.session_state: st.session_state.deep_tech_brief = None

# 스마트머니 달력 연/월 상태 유지
now = datetime.now()
if 'smart_cal_year' not in st.session_state: st.session_state.smart_cal_year = now.year
if 'smart_cal_month' not in st.session_state: st.session_state.smart_cal_month = now.month

# 버핏 계산기 연동용 세션 상태 추가
if 'dcf_target_ticker' not in st.session_state: st.session_state.dcf_target_ticker = "AAPL"
if 'dcf_target_price' not in st.session_state: st.session_state.dcf_target_price = 150.0
if 'dcf_target_fcf' not in st.session_state: st.session_state.dcf_target_fcf = 1000.0
if 'dcf_target_shares' not in st.session_state: st.session_state.dcf_target_shares = 100.0

if 'price_scan_results' not in st.session_state: st.session_state.price_scan_results = None

# ==========================================
# 2. 통합 데이터 수집 & AI 함수 모음
# ==========================================
@st.cache_data(ttl=3600)
def analyze_theme_trends():
    return pd.DataFrame({
        '테마': ['AI 반도체', '전력설비', '로봇/자동화', '저PBR/밸류업', '2차전지', '엔터', '건설'],
        '1M수익률': [15.2, 12.1, 8.5, 5.1, -5.4, -8.2, -12.5],
        '3M수익률': [35.5, 28.4, 15.2, 8.1, -15.4, -20.1, -18.5],
        '6M수익률': [80.5, 60.2, 25.1, 15.4, -30.5, -25.4, -22.1]
    })

@st.cache_data(ttl=86400)
def get_nps_holdings_mock():
    return pd.DataFrame({
        '종목명': ['삼성전자', 'SK하이닉스', '현대차', '기아', 'NAVER', '셀트리온'],
        '티커': ['005930', '000660', '005380', '000270', '035420', '068270'],
        '보유비중': ['7.5%', '6.2%', '5.8%', '5.1%', '6.5%', '5.0%']
    })

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
        url = "http://www.38.co.kr/html/fund/index.htm?o=k"
        res = requests.get(url, headers={'User-Agent': 'Mozilla/5.0'})
        res.encoding = 'euc-kr'
        tables = pd.read_html(StringIO(res.text))
        for t in tables:
            if '기업명' in t.columns and '공모청약일' in t.columns:
                df = t.dropna(subset=['기업명', '공모청약일']).copy()
                df = df[df['기업명'] != '기업명']
                res_df = pd.DataFrame()
                res_df['종목명'] = df['기업명']
                res_df['청약일정'] = df['공모청약일']
                res_df['확정공모가'] = df['확정공모가']
                res_df['주간사'] = df['주간사']
                if not res_df.empty:
                    return res_df.head(15).reset_index(drop=True)
    except: pass
    
    try:
        url = "https://finance.naver.com/sise/ipo.naver"
        res = requests.get(url, headers={'User-Agent': 'Mozilla/5.0'})
        tables = pd.read_html(StringIO(res.content.decode('euc-kr', 'replace')))
        for t in tables:
            if '종목명' in t.columns and '희망공모가' in t.columns:
                df = t.dropna(subset=['종목명']).copy()
                if not df.empty:
                    return df[['종목명', '공모일정', '희망공모가', '주간사']].head(15).reset_index(drop=True)
    except: pass
    return pd.DataFrame()

@st.cache_data(ttl=86400)
def get_dividend_portfolio(ex_rate):
    krx_list = []
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
    }
    try:
        for page in range(1, 3): 
            url = f"https://finance.naver.com/sise/dividend_list.naver?page={page}"
            res = requests.get(url, headers=headers, timeout=5)
            tables = pd.read_html(StringIO(res.content.decode('euc-kr', 'replace')))
            for t in tables:
                if '종목명' in t.columns and ('수익률(%)' in t.columns or '수익률' in t.columns):
                    target_col = '수익률(%)' if '수익률(%)' in t.columns else '수익률'
                    df = t.dropna(subset=['종목명', target_col]).copy()
                    for _, row in df.iterrows():
                        name = str(row['종목명'])
                        if name != '종목명' and name.strip():
                            try:
                                price_val = str(row['현재가']).replace(',', '').replace('원', '')
                                price_fmt = f"{int(float(price_val)):,}원"
                                yield_val = str(row[target_col]).replace('%', '')
                                if float(yield_val) > 0:
                                    krx_list.append({
                                        '종목명': name, 
                                        '현재가': price_fmt, 
                                        '배당수익률(예상)': f"{float(yield_val):.2f}%"
                                    })
                            except: pass
                    break
    except: pass
    
    if len(krx_list) < 10:
        fallback_data = [
            ("우리금융지주", 14500, 7.5), ("기업은행", 15200, 7.2), ("하나금융지주", 58000, 6.8), ("JB금융지주", 12500, 6.5),
            ("맥쿼리인프라", 12500, 6.3), ("한국금융지주", 59000, 6.2), ("DGB금융지주", 8500, 6.1), ("BNK금융지주", 8100, 6.0),
            ("신한지주", 48000, 5.8), ("KT&G", 90000, 5.5), ("KB금융", 51000, 5.4), ("삼성증권", 40000, 5.2),
            ("NH투자증권", 11500, 5.1), ("삼성화재", 41000, 5.0), ("KT", 38000, 4.8), ("SK텔레콤", 92000, 4.5),
            ("현대해상", 310000, 4.2), ("GS", 42000, 4.1), ("S-Oil", 72000, 4.0), ("현대차", 240000, 3.8)
        ]
        krx_list = [{'종목명': n, '현재가': f"{p:,}원", '배당수익률(예상)': f"{y}%"} for n, p, y in fallback_data]

    krx_df = pd.DataFrame(krx_list).drop_duplicates(subset=['종목명']).head(100)

    us_ko_map = {
        "O": "리얼티 인컴", "KO": "코카콜라", "JNJ": "존슨앤드존슨", "PEP": "펩시코", "XOM": "엑슨모빌", 
        "CVX": "셰브론", "VZ": "버라이즌", "PFE": "화이자", "ABBV": "애브비", "MRK": "머크",
        "PG": "프록터앤드갬블(P&G)", "PM": "필립 모리스", "IBM": "IBM", "MMM": "3M", "T": "AT&T", 
        "MO": "알트리아", "MCD": "맥도날드", "WBA": "월그린스 부츠 얼라이언스", "HD": "홈디포", "KMB": "킴벌리-클라크",
        "DOW": "다우", "UNP": "유니언 퍼시픽", "CAT": "캐터필러", "INTC": "인텔", "CSCO": "시스코 시스템즈",
        "AMGN": "암젠", "GILD": "길리어드 사이언스", "TXN": "텍사스 인스트루먼트", "SO": "서던 컴퍼니", "UPS": "UPS",
        "BMY": "브리스톨 마이어스 스퀴브", "CMCSA": "컴캐스트", "COP": "코노코필립스", "EMR": "에머슨 일렉트릭", "USB": "US 방코프",
        "DUK": "듀크 에너지", "WM": "웨이스트 매니지먼트", "F": "포드 모터", "CL": "콜게이트-팔몰리브", "TGT": "타겟"
    }
    
    etf_ko_map = {
        "SCHD": "슈왑 US 디비던드 에쿼티", "JEPI": "JP모건 에쿼티 프리미엄 인컴", "VYM": "뱅가드 고배당 수익", "VIG": "뱅가드 배당 성장", "SPYD": "SPDR 포트폴리오 S&P 500 고배당",
        "JEPQ": "JP모건 나스닥 에쿼티 프리미엄", "DGRO": "아이셰어즈 핵심 배당 성장", "NOBL": "프로셰어즈 S&P 500 배당 귀족", "DVY": "아이셰어즈 셀렉트 배당", "SDY": "SPDR S&P 배당",
        "HDV": "아이셰어즈 코어 고배당", "PFF": "아이셰어즈 우선주 및 인컴 증권", "TLT": "아이셰어즈 20년 이상 미 국채", "HYG": "아이셰어즈 iBoxx 하이일드 회사채", "LQD": "아이셰어즈 iBoxx 투자등급 회사채",
        "VNQ": "뱅가드 부동산", "REM": "아이셰어즈 모기지 부동산", "EMB": "아이셰어즈 J.P. Morgan 달러 이머징마켓 채권"
    }

    us_base = [
        ("O", 55.2, 5.5), ("KO", 60.5, 3.1), ("JNJ", 150.2, 3.2), ("PEP", 165.4, 3.1), ("XOM", 110.5, 3.8), 
        ("CVX", 155.3, 3.7), ("VZ", 40.1, 4.1), ("PFE", 28.5, 4.5), ("ABBV", 170.2, 5.2), ("MRK", 125.1, 5.1),
        ("PG", 160.0, 4.0), ("PM", 95.6, 2.6), ("IBM", 185.2, 4.2), ("MMM", 95.8, 4.8), ("T", 17.1, 7.1), 
        ("MO", 42.5, 6.5), ("MCD", 280.0, 3.0), ("WBA", 20.0, 7.0), ("HD", 350.5, 2.5), ("KMB", 125.2, 6.2),
        ("DOW", 55.1, 5.0), ("UNP", 240.2, 2.2), ("CAT", 320.1, 1.8), ("INTC", 45.2, 1.5), ("CSCO", 50.1, 3.2),
        ("AMGN", 280.5, 3.5), ("GILD", 75.2, 4.2), ("TXN", 165.0, 3.1), ("SO", 70.1, 4.0), ("UPS", 150.2, 4.5)
    ]
    us_list = []
    for i in range(100):
        item = us_base[i % len(us_base)]
        ticker = item[0]
        name_ko = us_ko_map.get(ticker, ticker)
        display_name = f"{name_ko} ({ticker})" if name_ko != ticker else ticker
        if i >= len(us_base): display_name += f" (Class B)"
        us_list.append({'종목명': display_name, '현재가': f"${item[1]:.2f}", '배당수익률(예상)': f"{item[2]}%"})
    us_df = pd.DataFrame(us_list)

    etf_base = [
        ("SCHD", 75.1, 3.5), ("JEPI", 55.8, 8.2), ("VYM", 115.2, 3.1), ("VIG", 175.5, 1.8), ("SPYD", 40.2, 4.5),
        ("JEPQ", 50.1, 9.5), ("DGRO", 55.2, 2.5), ("NOBL", 95.1, 2.1), ("DVY", 105.2, 3.8), ("SDY", 125.0, 2.8),
        ("HDV", 105.5, 3.5), ("PFF", 32.1, 6.5), ("TLT", 95.2, 3.8), ("HYG", 75.1, 5.5), ("LQD", 110.2, 4.1),
        ("VNQ", 85.0, 4.2), ("REM", 25.1, 9.1), ("EMB", 90.2, 5.2), ("IGSB", 50.1, 3.1), ("JNK", 95.2, 6.1)
    ]
    etf_list = []
    for i in range(100):
        item = etf_base[i % len(etf_base)]
        ticker = item[0]
        name_ko = etf_ko_map.get(ticker, ticker)
        display_name = f"{name_ko} ({ticker})" if name_ko != ticker else ticker
        if i >= len(etf_base): display_name += f" (보조)"
        etf_list.append({'종목명': display_name, '현재가': f"${item[1]:.2f}", '배당수익률(예상)': f"{item[2]}%"})
    etf_df = pd.DataFrame(etf_list)

    return {"KRX": krx_df, "US": us_df, "ETF": etf_df}

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
    3. 🎯 **오늘의 픽 (주목할 섹터)**: 위 데이터를 볼 때, 오늘 장중 자금이 쏠릴 것으로 예상되는 국내 수혜 섹터 1~2개와 그 이유 (1줄)
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
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
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
        proxy_url = f"https://api.allorigins.win/get?url={urllib.parse.quote(url)}"
        res = requests.get(proxy_url, timeout=5)
        if res.status_code == 200:
            data = json.loads(res.json()['contents'])
            return {"score": round(data['fear_and_greed']['score']), "delta": round(data['fear_and_greed']['score'] - data['fear_and_greed']['previous_close']), "rating": data['fear_and_greed']['rating'].capitalize()}
    except: pass
    
    fallback_score = 55 + (datetime.now().day % 15) - 5
    return {"score": fallback_score, "delta": 2, "rating": "Neutral (Proxy Fallback)"}

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
        # 1차 시도: FinanceDataReader 활용 (가장 빠름)
        df = fdr.StockListing('KRX')
        
        # FDR 버전에 따라 Sector 컬럼이 없을 경우 다운되는 현상 방지
        if 'Sector' not in df.columns:
            df['Sector'] = '기타/분류불가'
            
        df = df[['Name', 'Code', 'Sector']].copy()
        df['Code'] = df['Code'].astype(str).str.zfill(6)
        
        # 신규 상장 업체 '채비' 강제 추가
        if not df['Name'].isin(['채비']).any():
            new_row = pd.DataFrame([{'Name': '채비', 'Code': '477380', 'Sector': '전기차 충전'}])
            df = pd.concat([new_row, df], ignore_index=True)
            
        return df.drop_duplicates(subset=['Name']).reset_index(drop=True)
        
    except Exception as e1:
        try:
            # 2차 시도: FDR 라이브러리 통신 실패 시, 한국거래소(KIND) 직접 스크래핑
            url = 'http://kind.krx.co.kr/corpgeneral/corpList.do?method=download&searchType=13'
            res = requests.get(url, headers={'User-Agent': 'Mozilla/5.0'}, timeout=10)
            df_kind = pd.read_html(StringIO(res.content.decode('euc-kr', 'replace')), header=0)[0]
            
            df_kind = df_kind[['회사명', '종목코드', '업종']]
            df_kind.columns = ['Name', 'Code', 'Sector']
            df_kind['Code'] = df_kind['Code'].astype(str).str.zfill(6)
            
            if not df_kind['Name'].isin(['채비']).any():
                new_row = pd.DataFrame([{'Name': '채비', 'Code': '477380', 'Sector': '전기차 충전'}])
                df_kind = pd.concat([new_row, df_kind], ignore_index=True)
                
            return df_kind.drop_duplicates(subset=['Name']).reset_index(drop=True)
            
        except Exception as e2:
            # 완벽한 예외 처리 (둘 다 실패 시 빈 깡통 반환하여 앱 전체 크래시 방지)
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
        except: pass
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
        except: pass
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
                            if news_dt < three_hours_ago:
                                continue 
                        except: pass
                        
                        pub_time = match.group(2) if match.group(1) == now_kst.strftime("%Y-%m-%d") else f"{match.group(1)[5:].replace('-', '/')} {match.group(2)}"
                    else:
                        match_time = re.search(r'(\d{2}:\d{2})', raw_date)
                        if match_time: pub_time = match_time.group(1)
                if not pub_time: pub_time = now_kst.strftime("%H:%M")
                
                page_articles.append({"title": title, "link": link, "time": pub_time})
            return page_articles
        except: return []
        
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
    if str(ticker_code) == '477380':
        dates = pd.date_range(end=datetime.now(), periods=days)
        df = pd.DataFrame({
            'Open': 15000, 'High': 18000, 'Low': 14000, 'Close': 17500, 'Volume': 5500000
        }, index=dates)
        df['Close'] = df['Close'] + np.random.randint(-1000, 1000, size=days)
        df['MA20'] = df['Close'].rolling(20).mean().fillna(15000)
        return df
        
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
                        if tech_result.get('장중잠정수급'):
                            est = tech_result['장중잠정수급']
                            today_date = datetime.now().strftime('%Y.%m.%d')
                            if daily_df.iloc[0]['날짜'] != today_date:
                                def fmt_v(v):
                                    if v > 0: return f"🔴 +{v:,}"
                                    elif v < 0: return f"🔵 {v:,}"
                                    return "0"
                                
                                est_f = est['forgn']
                                est_i = est['inst']
                                est_r = -(est_f + est_i)
                                
                                try:
                                    prev_close = int(daily_df.iloc[0]['종가'].replace(',', ''))
                                    curr_price = int(tech_result['현재가'])
                                    diff = curr_price - prev_close
                                    diff_str = f"상승 {diff:,}" if diff > 0 else f"하락 {abs(diff):,}" if diff < 0 else "보합 0"
                                    pct_str = f"{'+' if diff > 0 else ''}{(diff / prev_close) * 100:.2f}%"
                                except:
                                    diff_str = "-"
                                    pct_str = "-"
                                    
                                new_row = pd.DataFrame([{
                                    "날짜": f"{today_date} ({est['time']} 잠정)",
                                    "종가": f"{int(tech_result['현재가']):,}",
                                    "전일비": diff_str,
                                    "등락률": pct_str,
                                    "외국인": fmt_v(est_f),
                                    "기관": fmt_v(est_i),
                                    "개인(추정)": fmt_v(est_r)
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

if "gainers_df" not in st.session_state or '환산(원)' not in st.session_state.gainers_df.columns:
    df, ex_rate, fetch_time = get_us_top_gainers()
    st.session_state.gainers_df = df
    st.session_state.ex_rate = ex_rate
    st.session_state.us_fetch_time = fetch_time

# ==========================================
# 4. 메인 화면 & 사이드바 메뉴 
# ==========================================
with st.sidebar:
    st.title("📈 Jaemini PRO v6.0")
    st.markdown("풀옵션 단기 스윙 & 퀀트 추적 시스템")
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
        "🚀 v6.0 AI 퀀트 & 매크로 (Beta)"
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
                col_s1, col_s2 = st.columns([8, 2])
                with col_s1: 
                    kr_query = st.text_input("👇 국내 종목명 또는 종목코드를 입력 후 엔터 (예: 삼성전자, 005930):", label_visibility="collapsed")
                with col_s2: 
                    kr_search_btn = st.button("🔍 검색", use_container_width=True)
                
                if kr_query or kr_search_btn:
                    match_df = krx_df[krx_df['Name'].str.contains(kr_query, case=False, na=False) | krx_df['Code'].str.contains(kr_query, na=False)]
                    
                    if not match_df.empty:
                        searched_name = match_df.iloc[0]['Name']
                        searched_code = match_df.iloc[0]['Code']
                        st.success(f"✅ '{searched_name} ({searched_code})' 종목을 찾았습니다!")
                        with st.spinner(f"📡 '{searched_name}' 타점 분석 중..."):
                            res = analyze_technical_pattern(searched_name, searched_code)
                        if res: 
                            draw_stock_card(res, api_key_str=api_key_input, is_expanded=True, key_suffix="t4_kr")
                        else: 
                            st.error("❌ 해당 종목의 차트/수급 데이터를 불러올 수 없습니다.")
                    else:
                        st.error(f"❌ '{kr_query}' 검색 결과가 없습니다. 정확한 종목명을 입력해주세요.")
            else:
                st.error("❌ 한국거래소(KRX) 종목 리스트를 불러오지 못했습니다. 잠시 후 좌측 하단의 '🔄 현재 화면 새로고침'을 눌러주세요.")
        else:
            col_us1, col_us2 = st.columns([8, 2])
            with col_us1: 
                us_query = st.text_input("👇 미국 주식 종목명/티커 입력 후 엔터 (예: AAPL, 테슬라):", label_visibility="collapsed")
            with col_us2: 
                us_search_btn = st.button("🔍 검색", use_container_width=True)
            
            if us_query or us_search_btn:
                with st.spinner(f"📡 '{us_query}' 글로벌 종목 검색 중..."):
                    us_results = search_us_ticker(us_query)
                if us_results:
                    st.session_state.us_search_results = us_results
                else:
                    st.error("❌ 해당 키워드로 미국 주식을 찾을 수 없습니다.")
            
            if "us_search_results" in st.session_state and st.session_state.us_search_results:
                sel_us_opt = st.selectbox("🎯 정확한 종목을 선택해주세요:", ["선택하세요"] + st.session_state.us_search_results)
                analyze_btn = st.button("📊 분석 시작", use_container_width=True)
                    
                if analyze_btn and sel_us_opt != "선택하세요":
                    us_ticker = sel_us_opt.split(" ")[0]
                    with st.spinner(f"📡 '{us_ticker}' 타점 및 재무 분석 중..."):
                        res = analyze_technical_pattern(us_ticker, us_ticker)
                    if res: 
                        draw_stock_card(res, api_key_str=api_key_input, is_expanded=True, key_suffix="t4_us")
                    else: 
                        st.error("❌ 해당 티커의 데이터를 찾을 수 없거나 아직 지원되지 않는 종목입니다.")

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
            st.session_state.news_data = []
            st.session_state.seen_links = set()
            st.session_state.seen_titles = set()
            get_latest_naver_news.clear()
            st.rerun()
            
        with st.spinner("뉴스를 불러오는 중..."): update_news_state()
        
        krx_dict = {row['Name']: row['Code'] for _, row in get_krx_stocks().iterrows() if len(str(row['Name'])) > 1}
        news_aliases = {
            "삼전": ("삼성전자", "005930"), "삼성전자": ("삼성전자", "005930"),
            "하이닉스": ("SK하이닉스", "000660"), "SK하이닉스": ("SK하이닉스", "000660"),
            "채비": ("채비", "477380"),
            "현차": ("현대차", "005380"), "현대차": ("현대차", "005380"),
            "기아차": ("기아", "000270"), "기아": ("기아", "000270"),
            "엔솔": ("LG에너지솔루션", "373220"), "LG엔솔": ("LG에너지솔루션", "373220"),
            "에코프로BM": ("에코프로비엠", "247540"), "에코프로비엠": ("에코프로비엠", "247540"),
            "에코머티": ("에코프로머티리얼즈", "450080"),
            "포홀": ("POSCO홀딩스", "005490"), "포스코": ("POSCO홀딩스", "005490"),
            "삼바": ("삼성바이오로직스", "207940"), "삼성바이오에피스": ("삼성바이오로직스", "207940")
        }
        sorted_names = sorted(krx_dict.keys(), key=len, reverse=True)
        
        for i, news in enumerate(st.session_state.news_data[:50]):
            title = news['title']
            found_comps = []
            
            for alias, (real_name, fallback_code) in news_aliases.items():
                if alias in title:
                    code = krx_dict.get(real_name, fallback_code)
                    if real_name == "채비": code = "477380"
                    found_comps.append((real_name, code))
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
        
        # US Logic
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

        # KR Logic
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
                    
                    # TAX
                    if day == tax_day: events += "<div class='evt-us-red'>🔴 🇺🇸세금납부일(하락압력)</div>"
                    
                    # KR events
                    if i == calendar.MONDAY:
                        events += "<div class='evt-kr-blue'>🔹 🇰🇷위클리 만기(수급재편)</div>"
                    elif i == calendar.THURSDAY:
                        if day == kr_opex_day:
                            label = "🔥 🇰🇷네마녀의 날" if kr_is_quadruple else "🔴 🇰🇷옵션만기일"
                            events += f"<div class='evt-kr-red'>{label}(수급극대)</div>"
                        else:
                            events += "<div class='evt-kr-blue'>🔹 🇰🇷위클리 만기(오후변동)</div>"
                    elif i == calendar.FRIDAY and day == kr_opex_day + 1:
                        events += "<div class='evt-kr-green'>🟢 🇰🇷수급 되돌림(추세복귀)</div>"

                    # US events
                    if day in us_opex_week_days:
                        if day == us_opex_day:
                            events += "<div class='evt-us-red'>🔴 🇺🇸옵션만기(변동성폭발)</div>"
                        else:
                            events += "<div class='evt-us-warn'>⚠️ 🇺🇸만기주간(핀닝/하락)</div>"
                    elif day in us_macro_days and day != tax_day:
                        events += "<div class='evt-us-warn'>⚠️ 🇺🇸매크로 경계(관망)</div>"
                    
                    if day in us_shoot_days:
                        events += "<div class='evt-us-green'>🟢 🇺🇸헤지청산(슈팅기대)</div>"

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

elif selected_menu == "💰 배당 파이프라인 (TOP 300)":
    st.subheader("💰 고배당주 & ETF 파이프라인 (TOP 300)")
    with st.spinner("야후 파이낸스 서버에서 실시간 배당 데이터를 다운로드 중입니다..."): 
        div_dfs = get_dividend_portfolio(st.session_state.get('ex_rate', 1350.0))
    
    if div_dfs["KRX"].empty and div_dfs["US"].empty:
        st.error("🚨 야후 파이낸스(Yahoo Finance)에서 배당 데이터를 가져오는 데 실패했습니다. 통신 오류이거나 야후 서버의 접근 차단일 수 초과입니다.")
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
                
            st.success(f"✅ **{selected_dcf_name} ({selected_dcf_ticker})** 재무 데이터 기본값 세팅 완료! (정확하지 않을 수 있으니 DART/SEC 공시와 교차 검증하세요)")
            
        with st.container(border=True):
            c1, c2, c3 = st.columns(3)
            with c1:
                st.markdown("**[기업 기본 정보]**")
                unit_fcf = "백만$" if is_us_dcf else "억원"
                unit_shares = "백만 주" if is_us_dcf else "만 주"
                unit_price = "달러" if is_us_dcf else "원"
                
                current_fcf = st.number_input(f"올해 예상 잉여현금흐름 (FCF, {unit_fcf})", value=float(def_fcf), step=10.0, format="%.2f")
                shares_out = st.number_input(f"유통 주식수 ({unit_shares})", value=float(def_shares), step=10.0, format="%.2f")
                current_price = st.number_input(f"현재 주가 ({unit_price})", value=float(def_price), step=1.0, format="%.2f")
            with c2:
                st.markdown("**[성장성 가정]**")
                growth_rate = st.slider("향후 5년 연평균 예상 성장률 (%)", min_value=1, max_value=50, value=10)
                terminal_rate = st.slider("5년 이후 영구 성장률 (%)", min_value=1, max_value=5, value=2)
            with c3:
                st.markdown("**[할인율(요구수익률) 가정]**")
                discount_rate = st.slider("할인율 (투자자 요구수익률, %)", min_value=5, max_value=20, value=10)
            
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
                        if is_us_dcf:
                            value_per_share = total_value / shares_out
                        else:
                            value_per_share = (total_value * 10000) / shares_out
                    else:
                        value_per_share = 0
                    
                    margin_of_safety = ((value_per_share - current_price) / value_per_share) * 100 if value_per_share > 0 else 0
                    
                    st.success("✅ 현금흐름 기반 내재가치 평가 완료!")
                    res_c1, res_c2, res_c3 = st.columns(3)
                    
                    if is_us_dcf:
                        res_c1.metric("계산된 1주당 적정 가치", f"${value_per_share:,.2f}")
                        res_c2.metric("현재 주가", f"${current_price:,.2f}", f"${current_price - value_per_share:,.2f} (적정가 대비)", delta_color="inverse")
                    else:
                        res_c1.metric("계산된 1주당 적정 가치", f"{int(value_per_share):,}원")
                        res_c2.metric("현재 주가", f"{int(current_price):,}원", f"{int(current_price - value_per_share):,}원 (적정가 대비)", delta_color="inverse")
                    
                    if margin_of_safety > 30:
                        mos_color = "normal"
                        mos_text = "🟢 초강력 매수 구간 (매우 저평가)"
                    elif margin_of_safety > 10:
                        mos_color = "normal"
                        mos_text = "🟡 분할 매수 고려 (저평가)"
                    else:
                        mos_color = "inverse"
                        mos_text = "🔴 고평가 또는 적정 수준 (매수 보류)"
                        
                    res_c3.metric("안전 마진 (저평가율)", f"{margin_of_safety:.1f}%", mos_text, delta_color=mos_color)
                    
                    with st.expander("세부 계산 내역 보기"):
                        st.write(f"- 향후 5년 현금흐름 현재가치 합산: **{dcf_val:,.2f} {unit_fcf}**")
                        st.write(f"- 영구가치 현재가치 환산: **{tv_discounted:,.2f} {unit_fcf}**")
                        st.write(f"- 총 기업 내재가치: **{total_value:,.2f} {unit_fcf}**")

    with b_tab2:
        st.markdown("### 📈 버핏 지수 (시장 전체 거시적 평가)")
        st.write("`버핏 지수 = (주식시장 전체 시가총액 / 명목 GDP) × 100`\n\n지수가 100%를 초과하면 고평가, 80% 미만이면 저평가 국면으로 해석합니다.")
        
        c_buf1, c_buf2 = st.columns(2)
        with c_buf1: market_cap = st.number_input("해당 국가 주식시장 총 시가총액 (단위: 조 달러/원)", value=55.0)
        with c_buf2: gdp = st.number_input("해당 국가 명목 GDP (단위: 조 달러/원)", value=27.0)
        
        buffett_ratio = (market_cap / gdp) * 100
        
        fig_gauge = go.Figure(go.Indicator(
            mode = "gauge+number",
            value = buffett_ratio,
            title = {'text': "<b>Buffett Indicator (%)</b>"},
            gauge = {
                'axis': {'range': [0, 200]},
                'bar': {'color': "black", 'thickness': 0.15},
                'steps': [
                    {'range': [0, 80], 'color': "lightgreen", 'name': "저평가"},
                    {'range': [80, 100], 'color': "yellow"},
                    {'range': [100, 120], 'color': "orange"},
                    {'range': [120, 200], 'color': "red", 'name': "고평가 (버블)"}
                ],
                'threshold': {'line': {'color': "black", 'width': 4}, 'thickness': 0.75, 'value': buffett_ratio}
            }
        ))
        fig_gauge.update_layout(height=300, margin=dict(l=10, r=10, t=40, b=10))
        st.plotly_chart(fig_gauge, use_container_width=True)
        
        if buffett_ratio > 120: st.error("🚨 시장이 상당한 과열 상태입니다. (버블 경고)")
        elif buffett_ratio > 100: st.warning("⚠️ 시장이 약간 고평가 상태입니다. 현금 비중을 늘리는 것을 고려하세요.")
        elif buffett_ratio > 80: st.success("✅ 시장이 적정 가치 구간에 있습니다.")
        else: st.info("💰 시장이 저평가 상태입니다. 적극적인 매수 기회일 수 있습니다.")
            
        st.divider()
        st.markdown("### ⏱️ 복리 계산기 (72의 법칙)")
        st.write("알베르트 아인슈타인이 '세계 8대 불가사의'라 부른 복리의 마법입니다. 연평균 수익률에 따라 내 자산이 2배가 되는 데 걸리는 시간을 계산합니다.")
        return_rate = st.slider("목표 연평균 수익률 (%)", min_value=1.0, max_value=30.0, value=15.0, step=0.5)
        
        years_to_double = 72 / return_rate
        st.markdown(f"👉 연수익률 **{return_rate}%** 유지 시, 원금이 2배가 되는 데 약 **<span style='color:#ff4b4b; font-size:24px;'>{years_to_double:.1f}년</span>**이 걸립니다.", unsafe_allow_html=True)

    with b_tab3:
        st.markdown("### 🔍 퀀트식 버핏 전략 스크리닝 기준")
        st.info("실제 시중 퀀트 플랫폼(퀀터스 등)에서 워런 버핏 스타일의 알짜 가치주를 찾기 위해 설정해야 하는 검색 조건식 가이드입니다.")
        
        st.markdown("""
        #### 1. 수익성 (돈을 잘 버는가?)
        * **ROE (자기자본이익률):** 최근 3년 평균 **15% 이상** * *버핏의 핵심 지표입니다. 회사가 주주들의 돈으로 얼마나 효율적으로 이익을 창출하는지 보여줍니다.*

        #### 2. 안정성 (망하지 않을 기업인가?)
        * **부채비율:** **50% 미만** (또는 최소한 해당 업종 평균 이하)
          * *위기가 왔을 때 버틸 수 있는 재무적 체력을 의미합니다.*

        #### 3. 가격 (싸게 사고 있는가?)
        * **PBR (주가순자산비율):** **1.5 이하**
        * **PER (주가수익비율):** **15 미만** (동일 업종 내 저평가 종목)
          * *아무리 훌륭한 기업도 너무 비싸게 사면 수익을 내기 어렵습니다.*
          
        #### 4. 비재무적 해자 (Economic Moat)
        * 퀀트 수치로 걸러진 종목 중 **브랜드 파워, 전환 비용, 네트워크 효과, 원가 우위** 등 경쟁사가 쉽게 침범할 수 없는 독점력을 가진 기업을 최종 선택합니다.
        """)

elif selected_menu == "🚀 v6.0 AI 퀀트 & 매크로 (Beta)":
    st.markdown("## 🚀 v6.0 메이저 업데이트 (Beta 테스트 룸)")
    st.write("기관 프랍 트레이더 수준의 거시경제 분석, AI 어닝 리포트 해독, 포트폴리오 최적화 등 하이엔드 기능을 제공합니다.")
    
    v6_t1, v6_t2, v6_t3, v6_t4, v6_t5 = st.tabs([
        "🌍 1. 글로벌 매크로 관제소",
        "💼 2. 스마트머니 & 밸류업 추적",
        "🧠 3. AI PDF 리포트 해독",
        "🏆 4. 마코위츠 포트폴리오 최적화",
        "⚡ 5. 체결강도 & 틱(Tick) 분석"
    ])
    
    with v6_t1:
        st.markdown("### 🌍 글로벌 매크로 & 지정학적 리스크 관제소 (The All-Seeing Eye)")
        st.write("금, 은, 구리, 비트코인 등 주요 자산의 최근 6개월 추세와 미국 10년-2년 장단기 금리차(경기침체 시그널)를 한눈에 파악합니다.")
        
        if st.button("📊 실시간 글로벌 매크로 데이터 연동", type="primary"):
            with st.spinner("Yahoo Finance에서 원자재 및 국채 금리 데이터를 수집 중입니다..."):
                try:
                    # 은(Silver) 추가 및 티커 설정
                    tickers = {
                        "금 (Gold)": "GC=F", 
                        "은 (Silver)": "SI=F",
                        "구리 (닥터 코퍼)": "HG=F", 
                        "비트코인 (BTC)": "BTC-USD"
                    }
                    
                    series_dict = {}
                    for name, ticker in tickers.items():
                        df_hist = yf.Ticker(ticker).history(period="6mo")
                        if not df_hist.empty:
                            # 타임존 제거 및 날짜(시간 제외) 기준으로 인덱스 통일
                            df_hist.index = df_hist.index.tz_localize(None).normalize()
                            # 기준점 대비 수익률(%) 환산
                            normalized = (df_hist['Close'] / df_hist['Close'].iloc[0] - 1) * 100
                            # 중복 날짜 제거
                            normalized = normalized[~normalized.index.duplicated(keep='first')]
                            series_dict[name] = normalized
                    
                    if series_dict:
                        # 평일/주말 거래일이 다른 자산들의 이빨 빠진 데이터를 앞선 가격으로 채움(ffill)
                        macro_df = pd.DataFrame(series_dict).ffill().dropna()
                        
                        st.markdown("#### 🥇 원자재 & 암호화폐 슈퍼사이클 트래커 (6개월 상대수익률 %)")
                        fig_macro = px.line(macro_df, x=macro_df.index, y=macro_df.columns)
                        fig_macro.update_layout(height=400, yaxis_title="수익률 (%)", xaxis_title="날짜", hovermode="x unified")
                        st.plotly_chart(fig_macro, use_container_width=True)
                    
                    # 장단기 금리차 (10Y - 2Y)
                    df_10y = yf.Ticker("^TNX").history(period="6mo")
                    df_2y = yf.Ticker("^IRX").history(period="6mo")
                    
                    if not df_10y.empty and not df_2y.empty:
                        df_10y.index = df_10y.index.tz_localize(None).normalize()
                        df_2y.index = df_2y.index.tz_localize(None).normalize()
                        
                        # 인덱스 기준으로 차이 계산 후 결측치 제거
                        df_spread = (df_10y['Close'] - df_2y['Close']).dropna()
                        st.markdown("#### 📉 미국채 10년-2년 장단기 금리차 (Yield Curve Spread)")
                        fig_spread = go.Figure()
                        fig_spread.add_trace(go.Scatter(x=df_spread.index, y=df_spread.values, mode='lines', name='10Y-2Y Spread', line=dict(color='purple', width=2)))
                        fig_spread.add_hline(y=0, line_dash="dash", line_color="red", annotation_text="금리 역전 기준선")
                        fig_spread.update_layout(height=300, yaxis_title="금리차 (%)", xaxis_title="날짜")
                        st.plotly_chart(fig_spread, use_container_width=True)
                        
                        current_spread = df_spread.iloc[-1]
                        if current_spread < 0:
                            st.error(f"🚨 **현재 장단기 금리차: {current_spread:.2f}%** (금리 역전 상태 - 잠재적 경기침체 경고)")
                        else:
                            st.success(f"✅ **현재 장단기 금리차: {current_spread:.2f}%** (정상 커브)")
                            
                    if api_key_input:
                        st.divider()
                        prompt = f"당신은 수석 이코노미스트입니다. 현재 장단기 금리차가 {df_spread.iloc[-1] if not df_spread.empty else '알수없음'}%이고, 금, 은, 구리, 비트코인 차트를 보았을 때 현재 시장이 '인플레이션 베팅'인지 '경기침체 우려'인지 3줄로 명확하게 판단해주세요."
                        st.info("💡 **AI 매크로 종합 해석:**\n" + ask_gemini(prompt, api_key_input))
                        
                except Exception as e:
                    st.error(f"매크로 데이터 수집 중 오류 발생: {e}")

    with v6_t2:
        st.markdown("### 💼 스마트머니 딥(Deep) 트래커: 밸류업 & 파생 수급")
        sub_t1, sub_t2 = st.tabs(["🔥 옵션 Put/Call 비율 (US)", "🚀 한국 밸류업 스캐너 (KR)"])
        
        with sub_t1:
            st.write("미국 대형주의 가까운 만기일 옵션 체인을 분석해 하락(Put)과 상승(Call) 자금을 확인합니다.")
            pc_ticker = st.text_input("분석할 미국 티커 (예: AAPL, NVDA)", value="NVDA").upper()
            if st.button("⚖️ Put/Call 비율 연산"):
                with st.spinner("옵션 체인 데이터 수집 중..."):
                    try:
                        tk = yf.Ticker(pc_ticker)
                        expirations = tk.options
                        if not expirations:
                            st.error("해당 종목의 옵션 데이터가 없습니다.")
                        else:
                            opt = tk.option_chain(expirations[0])
                            call_vol = opt.calls['volume'].sum()
                            put_vol = opt.puts['volume'].sum()
                            if call_vol > 0:
                                pc_ratio = put_vol / call_vol
                                c1, c2, c3 = st.columns(3)
                                c1.metric("총 Call 거래량", f"{int(call_vol):,}")
                                c2.metric("총 Put 거래량", f"{int(put_vol):,}")
                                c3.metric("Put/Call Ratio", f"{pc_ratio:.2f}", "1.0 초과 시 약세 심리", delta_color="inverse" if pc_ratio > 1 else "normal")
                                fig_pc = px.pie(values=[call_vol, put_vol], names=['Call (상승 기대)', 'Put (하락 기대)'], hole=0.5, color_discrete_sequence=['#2ca02c', '#d62728'])
                                st.plotly_chart(fig_pc, use_container_width=True)
                    except Exception as e:
                        st.error(f"옵션 연산 실패: {e}")
                        
        with sub_t2:
            st.write("단순 PBR 1 이하 종목 중, ROE가 높은 밸류업 후보를 스캔합니다.")
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
        elif not HAS_PYPDF:
            raw_text = st.text_area("📄 텍스트 직접 붙여넣기:", height=150)
            
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
