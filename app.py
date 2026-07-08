import streamlit as st
import pandas as pd
import numpy as np
import requests
from bs4 import BeautifulSoup
from io import StringIO
import yfinance as yf
import FinanceDataReader as fdr
from datetime import datetime, timedelta
from google import genai as _genai          # 신규 SDK (google-genai) — 구버전 google-generativeai 폐기 대응
from google.genai import types as _gtypes
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
import jaemini_alert_center as alert_center  # [v7.1] 통합 경보 센터 모듈

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

# [속도개선 2순위] 자동 새로고침은 '실시간 데이터가 필요한 페이지'에서만 동작시킨다.
#  기존: 전 페이지를 5분마다 통째로 재실행 → 계산기/시뮬레이터/스캐너/리스트 등에서도
#        불필요한 rerun + 짧은 TTL 캐시 만료로 인한 재요청이 발생.
#  변경: 아래 LIVE_REFRESH_PAGES 에 속한 페이지에서만 호출(실제 호출은 메인 로직에서 selected_menu 확정 후).
AUTOREFRESH_MS = 300000  # 5분. 갱신 주기를 바꾸려면 이 값만 조정하면 된다.
LIVE_REFRESH_PAGES = {
    "🚨 통합 경보 센터 (뉴스·차트·일정)",
    "🎛️ 홈: 종합 대시보드",
    "⭐ 내 관심종목 모니터링",
    "🗺️ 시장 주도주 자금 히트맵",
    "🕸️ 실시간 섹터 순환매 추적",
    "🚨 당일 상/하한가 분석",
    "🚦 거래량 급증 & 시장 경보",
    "📰 실시간 특징주 속보 & 리포트",
}

st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;700&display=swap');
.stMetricValue, .stMetricDelta, table, .stDataFrame { font-family: 'JetBrains Mono', monospace !important; }
th { font-weight: 700 !important; background-color: rgba(100, 100, 100, 0.05) !important; }

/* ── 카드 내 '팝업/분석 실행' 버튼 강조 (가독성 포인트) ──────────────
   기본 회색 외곽선 버튼이 잘 안 보여서, 각 카드 헤더 색과 맞춘
   그라데이션 + 흰 글씨 + 그림자 + hover 효과로 또렷하게 만든다.
   (key 기반 .st-key-* 클래스를 사용 — Streamlit 1.39+) */
[class*="st-key-ai_btn_"] button,
[class*="st-key-biz_btn_"] button,
[class*="st-key-btn_tf_ai_"] button,
[class*="st-key-chat_open_"] button,
[class*="st-key-vptm_open_"] button {
    color:#fff !important;
    font-weight:800 !important;
    border:none !important;
    border-radius:10px !important;
    padding:0.62rem 0.9rem !important;
    letter-spacing:.2px;
    text-shadow:0 1px 2px rgba(0,0,0,.18);
    transition:transform .12s ease, filter .12s ease, box-shadow .12s ease !important;
}
[class*="st-key-ai_btn_"] button p,
[class*="st-key-biz_btn_"] button p,
[class*="st-key-btn_tf_ai_"] button p,
[class*="st-key-chat_open_"] button p,
[class*="st-key-vptm_open_"] button p { color:#fff !important; font-weight:800 !important; }

/* 1) 차트·수급·재무 정밀 진단 → 블루 */
[class*="st-key-ai_btn_"] button   { background:linear-gradient(135deg,#3b82f6,#1d4ed8) !important; box-shadow:0 3px 10px rgba(37,99,235,.32) !important; }
/* 2) 기업 심층 분석 → 에메랄드 */
[class*="st-key-biz_btn_"] button  { background:linear-gradient(135deg,#10b981,#047857) !important; box-shadow:0 3px 10px rgba(5,150,105,.32) !important; }
/* 3) 주기별 AI 차트 분석 → 바이올렛 */
[class*="st-key-btn_tf_ai_"] button{ background:linear-gradient(135deg,#8b5cf6,#6d28d9) !important; box-shadow:0 3px 10px rgba(124,58,237,.32) !important; }
/* 4) 전문가 AI 질의응답 → 인디고 (카드 헤더와 동일 계열) */
[class*="st-key-chat_open_"] button{ background:linear-gradient(135deg,#6366f1,#4338ca) !important; box-shadow:0 3px 10px rgba(67,56,202,.32) !important; }
/* 5) 매물대 지도·종목 타임머신 → 앰버 (카드 헤더와 동일 계열) */
[class*="st-key-vptm_open_"] button{ background:linear-gradient(135deg,#f59e0b,#d97706) !important; box-shadow:0 3px 10px rgba(217,119,6,.34) !important; }

/* 공통 hover / active */
[class*="st-key-ai_btn_"] button:hover,
[class*="st-key-biz_btn_"] button:hover,
[class*="st-key-btn_tf_ai_"] button:hover,
[class*="st-key-chat_open_"] button:hover,
[class*="st-key-vptm_open_"] button:hover { transform:translateY(-1px); filter:brightness(1.06); }
[class*="st-key-ai_btn_"] button:active,
[class*="st-key-biz_btn_"] button:active,
[class*="st-key-btn_tf_ai_"] button:active,
[class*="st-key-chat_open_"] button:active,
[class*="st-key-vptm_open_"] button:active { transform:translateY(0); filter:brightness(.96); }
</style>
""", unsafe_allow_html=True)

# 세션 상태 초기화
for key in ['seen_links', 'seen_titles', 'news_data']:
    if key not in st.session_state: st.session_state[key] = set() if 'seen' in key else []
if 'watchlist' not in st.session_state: st.session_state.watchlist = load_watchlist()
if 'quick_analyze_news' not in st.session_state: st.session_state.quick_analyze_news = None
if 'scan_results' not in st.session_state: st.session_state.scan_results = None
if 'value_scan_results' not in st.session_state: st.session_state.value_scan_results = None
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
def _gtx_translate_en_ko(text):
    """단일 문장 영→한 번역 (구글 무료 gtx 엔드포인트). 실패 시 원문 반환.
    스레드에서 호출되므로 st.cache_data를 직접 달지 않는다(상위 함수에서 캐시)."""
    t = (text or "").strip()
    if not t:
        return text
    # 이미 한글이 섞여 있으면 번역 불필요
    if re.search(r'[가-힣]', t):
        return text
    try:
        res = requests.get(
            "https://translate.googleapis.com/translate_a/single",
            params={"client": "gtx", "sl": "en", "tl": "ko", "dt": "t", "q": t},
            headers={"User-Agent": "Mozilla/5.0"},
            timeout=4,
        )
        if res.status_code == 200:
            data = res.json()
            # data[0] = [[번역문, 원문, ...], ...]  → 분할된 조각을 이어붙임
            parts = [seg[0] for seg in (data[0] or []) if seg and seg[0]]
            ko = "".join(parts).strip()
            return ko or text
    except Exception:
        pass
    return text


@st.cache_data(ttl=86400, show_spinner=False)
def translate_poly_questions(questions, _api_key=None):
    """
    영문 질문/선택지 목록을 한국어로 일괄 번역.
    [변경] 항목별로 구글 무료 번역 엔드포인트를 병렬 호출한다.
      - 일부만 번역되고 나머지가 누락되던 문제(LLM 일괄 번역의 줄 누락/병합)를 근본 해결.
      - API 키 불필요. 결과는 하루(ttl) 캐시되어 이후 재호출 없음.
    반환: {원문: 한글번역} 딕셔너리. (실패 항목만 원문 유지)
    """
    uniq = [q for q in dict.fromkeys(questions) if q and q.strip()]
    if not uniq:
        return {}
    mapping = {}
    try:
        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as ex:
            for q, ko in zip(uniq, ex.map(_gtx_translate_en_ko, uniq)):
                mapping[q] = ko or q
    except Exception:
        for q in uniq:
            mapping[q] = _gtx_translate_en_ko(q)
    # 누락분은 원문으로 보강
    for q in uniq:
        mapping.setdefault(q, q)
    return mapping

@st.cache_data(ttl=86400)
def get_krx_etf_list():
    try:
        return fdr.StockListing('ETF/KR')
    except Exception:
        return pd.DataFrame()

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

        def fetch_detail(row_tuple):
            link, title = row_tuple
            try:
                time.sleep(0.1)
                detail_res = requests.get(link, headers={'User-Agent': 'Mozilla/5.0'}, timeout=3)
                detail_soup = BeautifulSoup(detail_res.content.decode('euc-kr', 'replace'), 'html.parser')
                detail_text = detail_soup.get_text(separator=' ', strip=True)
                real_price = parse_target_price(detail_text)
                real_opinion = standardize_opinion(detail_text)
                change_status, change_pct = classify_tp_change(title, detail_text, real_price)
                return real_price, real_opinion, change_status, change_pct
            except Exception:
                return 0, "N/A", "유지/신규", 0.0

        results = []
        link_title_pairs = list(zip(df['원문링크'], df['제목']))
        with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
            for r in executor.map(fetch_detail, link_title_pairs):
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
    # 순차 yf.Ticker 호출 → yf.download 배치 1회로 변경 (요청 1번에 전 종목 병렬 수집)
    us_data = []
    tickers = list(us_etfs)
    if not tickers:
        return pd.DataFrame(us_data)
    try:
        data = yf.download(tickers, period="5d", group_by="ticker",
                           threads=True, progress=False)
    except Exception:
        return pd.DataFrame(us_data)
    for ticker in tickers:
        try:
            df = data[ticker] if len(tickers) > 1 else data
            close_s = df['Close'].dropna()
            if len(close_s) >= 2:
                close = close_s.iloc[-1]
                prev = close_s.iloc[-2]
                pct = ((close - prev) / prev) * 100
                vol_s = df['Volume'].dropna()
                vol = int(vol_s.iloc[-1]) if len(vol_s) else 0
                us_data.append({"티커": ticker, "현재가": f"${close:.2f}", "등락률": f"{pct:+.2f}%", "거래량": f"{vol:,}"})
        except Exception: pass
    return pd.DataFrame(us_data)

@st.cache_data(ttl=86400)
def get_nps_holdings(dart_key=""):
    targets = [('삼성전자', '005930'), ('SK하이닉스', '000660'), ('LG에너지솔루션', '373220'), ('삼성바이오로직스', '207940'), ('현대차', '005380'), ('기아', '000270'), ('셀트리온', '068270'), ('POSCO홀딩스', '005490'), ('NAVER', '035420'), ('KB금융', '105560'), ('신한지주', '055550'), ('삼성물산', '028260'), ('현대모비스', '012330'), ('LG화학', '051910'), ('카카오', '035720'), ('삼성SDI', '006400'), ('하나금융지주', '086790'), ('메리츠금융지주', '138040'), ('한국전력', '015760'), ('HMM', '011200'), ('KT&G', '033780'), ('우리금융지주', '316140'), ('기업은행', '024110')]
    nps_data = []
    # DART 키가 있으면 corp_code 매핑을 스레딩 전에 1회만 구축 (스레드별 중복 다운로드 방지)
    corp_map = get_dart_corp_map(dart_key) if dart_key else None

    def fetch_nps(target):
        name, code = target
        try:
            # [v-우회] FnGuide 차단 대응: DART(키 보유 시) → FnGuide → WiseReport 체인으로 조회
            r, src = _fetch_nps_stake_multi(code, dart_key=dart_key, corp_map=corp_map)
            if r and r["지분율"] is not None and r["지분율"] >= 4.0:
                return {"종목명": name, "티커": code, "보유비중": f"{r['지분율']:.2f}%", "비고": f"{src} 실시간"}
        except Exception: pass
        return None
        
    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
        for r in executor.map(fetch_nps, targets):
            if r: nps_data.append(r)
            
    if nps_data:
        return pd.DataFrame(nps_data).sort_values('보유비중', ascending=False).reset_index(drop=True)
        
    # 실시간 파싱 실패 시: 가짜(하드코딩) 보유종목을 만들지 않고 '빈 결과'를 반환한다.
    #   (이전 버전은 하드코딩 더미를 돌려줬는데, 표 형태라 실제 국민연금 지분으로 오인될 위험이 커서 제거.
    #    화면에서는 빈 결과면 "데이터 없음" 경고를 띄운다.)
    return pd.DataFrame(columns=["종목명", "티커", "보유비중", "비고"])

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

    # 실시간 스크래핑 실패 시: 가짜(하드코딩) 13F를 만들지 않고 '빈 결과'를 반환한다.
    #   (정밀해 보이는 더미 수치가 실제 포트폴리오로 오인될 위험이 커서 제거. 화면에서 "데이터 없음" 경고.)
    return pd.DataFrame(columns=["종목명", "티커", "포트폴리오 비중", "보유주식수", "가치(달러)", "비고"])

# ==========================================
# 🔍 [NEW] 국민연금 지분율 — 단일 종목 실시간 검색
#   소스 체인: DART 오픈API(키 보유 시) → FnGuide → WiseReport
#   (FnGuide가 클라우드 IP를 차단해도 WiseReport/DART로 우회)
# ==========================================
_NPS_SCRAPE_HEADERS_BASE = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
    'Accept-Language': 'ko-KR,ko;q=0.9,en-US;q=0.8',
}
NPS_STAKE_SOURCES = [
    ("FnGuide", "https://comp.fnguide.com/SVO2/ASP/SVD_Invest.asp?pGB=1&gicode=A{code}", "https://comp.fnguide.com/"),
    ("WiseReport", "https://comp.wisereport.co.kr/company/c1070001.aspx?cmp_cd={code}", "https://comp.wisereport.co.kr/"),
]

def _extract_nps_stake_from_html(html_text):
    """주주 테이블 HTML에서 국민연금 지분율(%)·표기명 추출.
    반환: {"지분율": float, "주주표기": str} / {"지분율": None, ...}(정상 페이지·국민연금 미표기) / None(파싱 불가)"""
    try:
        tables = pd.read_html(StringIO(html_text))
    except Exception:
        return None
    parsed_any = False
    for df in tables:
        if not any('주주' in str(c) for c in df.columns):
            continue
        parsed_any = True
        row_mask = df.apply(lambda r: r.astype(str).str.contains('국민연금', na=False).any(), axis=1)
        match = df[row_mask]
        if match.empty:
            continue
        # 지분율 컬럼 선택: '변동지분'·'보유주식수' 같은 함정 컬럼 제외 (WiseReport 대응)
        pct_cols = [c for c in df.columns
                    if any(k in str(c) for k in ('지분', '비율', '보유'))
                    and '변동' not in str(c) and '주식수' not in str(c)]
        if not pct_cols:
            continue
        val = str(match[pct_cols[-1]].iloc[0]).replace('%', '').replace(',', '').strip()
        try:
            pct = float(val)
        except ValueError:
            continue
        disp = ""
        for c in df.columns:
            cell = str(match[c].iloc[0])
            if '국민연금' in cell:
                disp = cell.strip()
                break
        return {"지분율": pct, "주주표기": disp}
    return {"지분율": None, "주주표기": ""} if parsed_any else None

@st.cache_data(ttl=86400)
def get_dart_corp_map(dart_key):
    """DART 고유번호(corp_code) ↔ 종목코드 매핑. corpCode.xml(zip) 다운로드 후 파싱. 실패 시 빈 dict."""
    if not dart_key:
        return {}
    try:
        import zipfile
        import io as _io
        import xml.etree.ElementTree as _ET
        r = requests.get("https://opendart.fss.or.kr/api/corpCode.xml",
                         params={"crtfc_key": dart_key}, timeout=15)
        if r.status_code != 200 or not r.content[:2] == b'PK':   # zip 시그니처 확인 (오류 시 XML 에러문 반환됨)
            return {}
        with zipfile.ZipFile(_io.BytesIO(r.content)) as zf:
            with zf.open(zf.namelist()[0]) as f:
                tree = _ET.parse(f)
        cmap = {}
        for el in tree.getroot().iter('list'):
            stk = (el.findtext('stock_code') or '').strip()
            if stk:
                cmap[stk.zfill(6)] = (el.findtext('corp_code') or '').strip()
        return cmap
    except Exception:
        return {}

def _fetch_nps_stake_dart(code, dart_key, corp_map=None):
    """DART 오픈API 대량보유 상황보고(majorstock)에서 국민연금 최신 보고 지분율 조회.
    반환: {"지분율","주주표기","기준일"} / {"지분율": None}(보고 없음) / None(호출 실패·키 오류)"""
    try:
        cmap = corp_map if corp_map is not None else get_dart_corp_map(dart_key)
        corp_code = cmap.get(str(code).zfill(6))
        if not corp_code:
            return None
        r = requests.get("https://opendart.fss.or.kr/api/majorstock.json",
                         params={"crtfc_key": dart_key, "corp_code": corp_code}, timeout=7)
        j = r.json()
        if j.get("status") == "013":   # 조회된 데이터 없음 (대량보유 보고 자체가 없는 회사)
            return {"지분율": None, "주주표기": "", "기준일": ""}
        if j.get("status") != "000":
            return None
        rows = [x for x in j.get("list", []) if '국민연금' in str(x.get("repror", ""))]
        if not rows:
            return {"지분율": None, "주주표기": "", "기준일": ""}
        rows.sort(key=lambda x: str(x.get("rcept_no", "")), reverse=True)   # 최신 보고 우선
        top = rows[0]
        pct = float(str(top.get("stkrt", "")).replace(",", "").strip())
        return {"지분율": pct, "주주표기": str(top.get("repror", "")).strip(),
                "기준일": str(top.get("rcept_dt", "")).strip()}
    except Exception:
        return None

def _fetch_nps_stake_multi(code, dart_key="", corp_map=None):
    """소스 체인 순회. 반환: (결과 dict, 소스명) 또는 (None, None).
    지분율이 확인되면 즉시 반환, '미표기'는 다른 소스도 확인 후 판단."""
    none_result, none_src = None, None
    if dart_key:
        r = _fetch_nps_stake_dart(code, dart_key, corp_map)
        if r is not None:
            if r["지분율"] is not None:
                return r, "DART 공시"
            none_result, none_src = r, "DART 공시"
    for src_name, url_tpl, referer in NPS_STAKE_SOURCES:
        try:
            headers = dict(_NPS_SCRAPE_HEADERS_BASE, Referer=referer)
            res = requests.get(url_tpl.format(code=code), headers=headers, timeout=7)
            if res.status_code != 200:
                continue
            parsed = _extract_nps_stake_from_html(res.text)
            if parsed is None:
                continue
            if parsed["지분율"] is not None:
                return parsed, src_name
            if none_result is None:
                none_result, none_src = parsed, src_name
        except Exception:
            continue
    if none_result is not None:
        return none_result, none_src
    return None, None

@st.cache_data(ttl=1800)
def search_nps_holding(code, name="", dart_key=""):
    """단일 종목의 국민연금 지분율을 실시간 조회 (DART → FnGuide → WiseReport 체인).
    반환:
      {"종목명","티커","지분율"(float),"주주표기","출처","기준일"} : 지분 확인됨
      {"종목명","티커","지분율": None, "출처": 응답한 소스} : 소스는 응답했으나 국민연금 미표기(지분 없음 또는 5% 미만 가능성)
      None : 모든 소스 요청 실패(차단/타임아웃)"""
    r, src = _fetch_nps_stake_multi(code, dart_key=dart_key)
    if r is None:
        return None
    return {"종목명": name or code, "티커": code, "지분율": r["지분율"],
            "주주표기": r.get("주주표기", ""), "출처": src, "기준일": r.get("기준일", "")}

@st.cache_data(ttl=86400)
def get_krx_name_code_list():
    """종목명 검색용 KRX 전체 상장사 (코드·종목명) 목록. 실패 시 빈 DF 반환."""
    try:
        df = fdr.StockListing('KRX')
        if df is not None and not df.empty and 'Code' in df.columns and 'Name' in df.columns:
            out = df[['Code', 'Name']].dropna().copy()
            out['Code'] = out['Code'].astype(str).str.zfill(6)
            out['Name'] = out['Name'].astype(str)
            return out.reset_index(drop=True)
    except Exception:
        pass
    return pd.DataFrame(columns=['Code', 'Name'])


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
    [확정] FOMC·한은 금통위·ECB·BOJ(각국 중앙은행 공식 일정, 결정은 회의 2일차) / 미 CPI·고용(BLS 확정) / FOMC 의사록(회의 약 3주 후).
    [추정] PCE·소매판매·ISM·한국 CPI·중국 PMI·한국 수출입 — 통상 발표 시기 기준. 기관이 매월 확정하므로 실제 날짜는 1~2일 다를 수 있음.
    실제 자동 수집은 환경 제약으로 어려워, 확정 일정은 직접 입력하고 추정 항목은 명시한다.
    ※ css_class는 캘린더 페이지 스타일과 호환되도록 기존 4종(fomc/cpi/jobs/bok)만 재사용한다."""
    events = {}
    def _add(day, label, cls):
        if day:
            events.setdefault(day, []).append((label, cls))

    def _nth_bday(y, m, n):
        """해당 월의 n번째 영업일(주말 제외, 공휴일 미반영) 일자. 추정용."""
        cnt = 0
        for d in range(1, 29):
            try:
                if datetime(y, m, d).weekday() < 5:
                    cnt += 1
                    if cnt == n:
                        return d
            except Exception:
                break
        return None

    if year != 2026:
        return events

    # ───────── 美 통화정책 ─────────
    # FOMC 금리결정일 (회의 2일차, 공식 확정)
    fomc_2026 = {1: [28], 3: [18], 4: [29], 6: [17], 7: [29], 9: [16], 10: [28], 12: [9]}
    for d in fomc_2026.get(month, []):
        _add(d, "🏛️ 🇺🇸FOMC 금리결정", "evt-econ-fomc")
    # FOMC 의사록 (회의 약 3주 후 수요일, 확정)
    fomc_minutes_2026 = {2: 18, 4: 8, 5: 20, 7: 8, 8: 19, 10: 7, 11: 18, 12: 30}
    if month in fomc_minutes_2026:
        _add(fomc_minutes_2026[month], "📝 🇺🇸FOMC 의사록", "evt-econ-fomc")

    # ───────── 美 물가 ─────────
    # CPI (BLS 공식 확정 2026) — 1월은 셧다운으로 2/13 연기됐으나 표준 일정 사용
    cpi_2026 = {1: 13, 2: 11, 3: 11, 4: 10, 5: 12, 6: 10, 7: 14, 8: 12, 9: 11, 10: 14, 11: 10, 12: 10}
    if month in cpi_2026:
        _add(cpi_2026[month], "📊 🇺🇸CPI 물가", "evt-econ-cpi")
    # PCE 물가 (연준 선호 지표, 통상 월말·추정)
    pce_2026 = {1: 30, 2: 27, 3: 27, 4: 30, 5: 29, 6: 26, 7: 31, 8: 28, 9: 25, 10: 30, 11: 25, 12: 23}
    if month in pce_2026:
        _add(pce_2026[month], "📈 🇺🇸PCE 물가(연준선호)", "evt-econ-cpi")

    # ───────── 美 실물경기 ─────────
    # 고용지표(비농업, BLS 공식 확정 2026)
    jobs_2026 = {1: 9, 2: 6, 3: 6, 4: 3, 5: 8, 6: 5, 7: 2, 8: 7, 9: 4, 10: 2, 11: 6, 12: 4}
    if month in jobs_2026:
        _add(jobs_2026[month], "👷 🇺🇸고용지표", "evt-econ-jobs")
    # ISM 제조업 PMI (통상 1영업일·추정)
    _add(_nth_bday(year, month, 1), "🏭 🇺🇸ISM 제조업 PMI", "evt-econ-jobs")
    # 소매판매 (통상 월 중순·추정)
    retail_2026 = {1: 15, 2: 17, 3: 16, 4: 15, 5: 15, 6: 16, 7: 16, 8: 14, 9: 16, 10: 15, 11: 17, 12: 15}
    if month in retail_2026:
        _add(retail_2026[month], "🛒 🇺🇸소매판매", "evt-econ-jobs")

    # ───────── 韓 ─────────
    # 한은 금통위 통화정책방향 결정회의 (2026 공식 확정)
    bok_2026 = {1: 15, 2: 26, 4: 10, 5: 28, 7: 16, 8: 27, 10: 22, 11: 26}
    if month in bok_2026:
        _add(bok_2026[month], "🏦 🇰🇷한은 금통위", "evt-econ-bok")
    # 한국 소비자물가(CPI) (통계청, 통상 월초 2영업일·추정)
    _add(_nth_bday(year, month, 2), "📊 🇰🇷소비자물가(CPI)", "evt-econ-cpi")
    # 한국 수출입동향 (관세청, 매월 1일) — 수출 주도 경제, KOSPI 직접 동인
    _add(1, "🚢 🇰🇷수출입동향", "evt-econ-jobs")

    # ───────── 글로벌(韓 영향 큰 일정) ─────────
    # ECB 통화정책회의 (2일차 결정, 2026 공식 확정)
    ecb_2026 = {3: 19, 4: 30, 6: 11, 7: 23, 9: 10, 10: 29, 12: 17}
    if month in ecb_2026:
        _add(ecb_2026[month], "🏛️ 🇪🇺ECB 통화정책", "evt-econ-fomc")
    # BOJ 금융정책결정회의 (2일차 결정, 2026 공식 확정) — 엔/원 환율·엔캐리 민감
    boj_2026 = {1: 23, 3: 19, 4: 28, 6: 16, 7: 31, 9: 18, 10: 30, 12: 18}
    if month in boj_2026:
        _add(boj_2026[month], "🏯 🇯🇵BOJ 금융정책", "evt-econ-fomc")
    # 중국 제조업 PMI (NBS 월말/차이신 월초, 통상 1일·추정) — 수출 수요 선행
    _add(1, "🏭 🇨🇳제조업 PMI", "evt-econ-jobs")

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

# ── 증권사 리포트 공통 파싱 헬퍼 (의견 표준화·목표가·종전가) ─────────────
def standardize_opinion(text):
    """리포트 원문에서 투자의견을 5단계로 표준화. 국문/영문/하우스별 표현 모두 흡수.
    반환: '강력매수' | '매수' | '중립' | '매도' | 'N/A'"""
    if not text:
        return "N/A"
    t = str(text).upper()
    if 'STRONG BUY' in t or '강력매수' in t:
        return '강력매수'
    if any(k in t for k in ('BUY', '매수', 'OVERWEIGHT', 'OUTPERFORM', '비중확대')):
        return '매수'
    if any(k in t for k in ('SELL', '매도', 'UNDERWEIGHT', 'UNDERPERFORM', '비중축소', '축소')):
        return '매도'
    if any(k in t for k in ('HOLD', '중립', 'NEUTRAL', 'MARKETPERFORM', 'MARKET PERFORM', '시장수익률')):
        return '중립'
    return 'N/A'


def parse_target_price(text):
    """목표가/목표주가/적정주가/적정가격/TP 뒤의 금액(원)을 추출. 없으면 0."""
    if not text:
        return 0
    m = re.search(r'(?:목표\s*주?가|적정\s*주?가격?|TP)\s*[:\s]*([0-9][0-9,]{2,})', str(text))
    return int(m.group(1).replace(',', '')) if m else 0


def parse_prev_target_price(text):
    """종전/기존 목표가 금액을 추출. 없으면 0."""
    if not text:
        return 0
    m = re.search(r'(?:종전|기존)\s*(?:목표\s*주?가)?\s*[:\s]*([0-9][0-9,]{2,})', str(text))
    return int(m.group(1).replace(',', '')) if m else 0


def classify_tp_change(title, detail_text, real_price):
    """목표가 변동(상향/하향/유지·신규) 및 변동률 산출.
    1순위: 종전가 대비 실제 % 계산  2순위: 제목/본문의 '상향'·'하향' 키워드."""
    change_status, change_pct = "유지/신규", 0.0
    prev_price = parse_prev_target_price((detail_text or "")[:600])
    if prev_price > 0 and real_price > 0:
        change_pct = (real_price - prev_price) / prev_price * 100
        change_status = "상향" if change_pct > 0 else ("하향" if change_pct < 0 else "유지/신규")
    else:
        head = (title or "") + " " + (detail_text or "")[:300]
        if '상향' in head:
            change_status = "상향"
        elif '하향' in head:
            change_status = "하향"
    return change_status, change_pct


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
                        real_price = parse_target_price(detail_text)
                        real_opinion = standardize_opinion(detail_text)
                            
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
def _genai_generate(prompt, api_key, *, grounding=False, image=None,
                    model_name="gemini-3.1-flash-lite"):
    """신규 google-genai SDK 공통 래퍼. 원시 response 객체를 반환한다.
    - grounding=True  → 구글 검색(Google Search) 도구 사용 (Gemini 3.x 정식 문법)
    - image 지정       → 멀티모달(비전) 입력
    """
    client = _genai.Client(api_key=api_key)
    contents = prompt if image is None else [prompt, image]
    config = None
    if grounding:
        config = _gtypes.GenerateContentConfig(
            tools=[_gtypes.Tool(google_search=_gtypes.GoogleSearch())]
        )
    return client.models.generate_content(
        model=model_name, contents=contents, config=config,
    )


def ask_gemini(prompt, _api_key, grounding=False):
    if not _api_key: return "API 키가 필요합니다."
    try:
        now_kst = datetime.utcnow() + timedelta(hours=9)
        today_str = now_kst.strftime("%Y년 %m월 %d일")
        system_date_instruction = f"🚨 [시스템 필수 지침]: 오늘 날짜는 정확히 {today_str}입니다. 분석 시점은 반드시 오늘을 기준으로 하며, 과거 데이터를 현재 상황으로 오인하여 답변하지 마세요.\n\n"
        
        full_prompt = system_date_instruction + prompt

        response = _genai_generate(full_prompt, _api_key, grounding=grounding)

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
        response = _genai_generate(system_date_instruction + prompt, _api_key, image=image_obj)
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
    위 팩트 데이터를 바탕으로, 아래 3개 항목만 마크다운으로 간결하게 작성하세요.
    - 맨 위에 별도의 큰 제목이나 인사말은 넣지 말고, 바로 첫 항목부터 시작하세요.
    - 각 항목의 제목은 반드시 '## ' 로 시작하세요.

    ## 🌍 글로벌 시황
    간밤 미국 증시(3대 지수·반도체 SOX·美 10년물 금리·유가)와 위험자산 선호 심리를 2~3줄로 요약.

    ## 🇰🇷 국내 시황
    위 미국장 결과와 환율·금리가 오늘 코스피/코스닥 수급 및 외국인 자금 방향에 미칠 영향을 2~3줄로 분석.

    ## 🎯 오늘의 픽 (주목할 섹터)
    **🌍 글로벌:** 미국 시장에서 자금이 쏠릴 것으로 예상되는 섹터 1~2개와 근거를 1줄로.
    **🇰🇷 국내:** 위 글로벌 흐름의 수혜가 예상되는 국내 섹터 1~2개와 근거를 1줄로.
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
    prompt = f"""당신은 글로벌 테마주 발굴 전문가입니다.
'{theme}' 테마의 실제 수혜주를 **한국(KRX)과 미국(US) 양쪽 시장에서 골고루** 발굴하세요.
이 테마의 제품·기술·밸류체인(소재·부품·장비·서비스)에 직접적인 사업 연관이 있는 종목만 포함합니다.

[규칙]
1. 테마와 '직접' 관련된 진짜 종목만. 개수를 채우려고 관련 없는 대형주(예: 테슬라, 엔비디아)나 엉뚱한 종목을 끼워넣지 마세요.
2. **반드시 한국 종목과 미국 종목을 둘 다 포함**하세요. 대부분의 글로벌 테마는 양쪽 시장에 실제 수혜주가
   있으니 미국·글로벌 종목도 적극적으로 찾으세요. (정말로 한쪽 시장에 진짜 관련주가 없을 때만 생략)
3. 가능하면 한국과 미국 비중을 비슷하게 맞추세요.
4. 정확한 코드만 — 한국은 정확한 6자리 KRX 코드, 미국은 정확한 실제 티커(예: NVDA). 불확실하거나 비상장이면 제외.
5. 관련도가 높은 순서로, 최대 30개.

[출력 형식]
- "종목명,종목코드" 형식, 한 줄에 하나씩. 미국 종목도 종목명은 자유롭게 쓰되 코드는 영문 티커. (예: 삼성전자,005930 / 엔비디아,NVDA)
- 번호·부연 설명·마크다운 기호(-, * 등) 금지. 종목명 안에는 쉼표(,)를 쓰지 마세요. 오직 종목 데이터만.
"""
    try:
        res = ask_gemini(prompt, api_key, grounding=True)
        stocks, seen = [], set()
        for line in res.split('\n'):
            line = line.strip()
            if ',' not in line:
                continue
            parts = line.split(',')
            code = parts[-1].strip().upper().replace(" ", "")          # 코드는 항상 마지막 토큰
            name = ",".join(parts[:-1]).strip().lstrip("-*• ").strip()  # 이름에 쉼표가 있어도 보존
            if not name or len(name) > 40:
                continue
            is_kr = (len(code) == 6 and code.isdigit() and code != "000000")
            is_us = (code.isascii() and code.isalpha() and 1 <= len(code) <= 5)
            if (is_kr or is_us) and code not in seen:
                seen.add(code)
                stocks.append((name, code))
        return stocks[:30]
    except Exception:
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
        if krx_df.empty:
            return [(n, c) for n, c in dict.fromkeys(raw_list) if not is_kr_etf_etn(n, c)][:20]
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
        validated = [(n, c) for n, c in validated if not is_kr_etf_etn(n, c)]
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


def _value_factors(m):
    """get_value_metrics 결과에서 파생 팩터 계산: PEG(PER÷이익성장), 이익수익률(1/PER), 검증 팩터 수."""
    per = m.get("per"); growth = m.get("growth")
    peg = (per / growth) if (per and per > 0 and growth and growth > 0) else None
    ey = (100.0 / per) if (per and per > 0) else None        # 이익수익률(%) = 1/PER
    core = ["per", "pbr", "div", "roe", "debt", "growth"]
    cov_n = sum(1 for k in core if m.get(k) is not None)
    return {"peg": (round(peg, 2) if peg is not None else None),
            "ey": (round(ey, 1) if ey is not None else None),
            "cov_n": cov_n, "cov_total": len(core)}

def _value_rank(passed):
    """통과 종목을 '가치 점수'로 내림차순 랭킹. 각 시장 내 백분위 기준으로 결합.
    점수 = 저평가(PER·PBR·PEG, 낮을수록↑) 45% + 퀄리티(ROE) 20% + 인컴(배당) 15%
           + 안전(부채, 낮을수록↑) 12% + 모멘텀(6M) 8%.
    각 항목에 _vscore / _vrank / _factors 부여 후 정렬해 반환."""
    if not passed:
        return passed
    ms = [p["m"] for p in passed]
    fac = [_value_factors(x) for x in ms]
    p_per = _leader_pctl([x.get("per") for x in ms])
    p_pbr = _leader_pctl([x.get("pbr") for x in ms])
    p_peg = _leader_pctl([f["peg"] for f in fac])
    p_roe = _leader_pctl([x.get("roe") for x in ms])
    p_div = _leader_pctl([x.get("div") for x in ms])
    p_debt = _leader_pctl([x.get("debt") for x in ms])
    p_mom = _leader_pctl([x.get("mom6") for x in ms])
    for i, p in enumerate(passed):
        cheap = ((1 - p_per[i]) + (1 - p_pbr[i]) + (1 - p_peg[i])) / 3.0   # PER·PBR·PEG 낮을수록 좋음
        score = 100.0 * (0.45 * cheap + 0.20 * p_roe[i] + 0.15 * p_div[i]
                         + 0.12 * (1 - p_debt[i]) + 0.08 * p_mom[i])       # 부채는 낮을수록 좋음
        p["_vscore"] = round(score, 1)
        p["_factors"] = fac[i]
    passed.sort(key=lambda x: x["_vscore"], reverse=True)
    for rk, p in enumerate(passed, 1):
        p["_vrank"] = rk
    return passed

@st.cache_data(ttl=3600)
def get_macro_indicators():
    # 순차 yf.Ticker 호출 → yf.download 배치 1회로 변경 (홈 화면 첫 로딩 단축)
    results = {}
    tickers = {"VIX": "^VIX", "美 10년물 국채": "^TNX", "필라델피아 반도체": "^SOX", "WTI 원유": "CL=F", "원/달러 환율": "KRW=X"}
    try:
        data = yf.download(list(tickers.values()), period="5d", group_by="ticker",
                           threads=True, progress=False)
    except Exception:
        return None
    for name, ticker in tickers.items():
        try:
            close = data[ticker]['Close'].dropna()
            if len(close) >= 2:
                results[name] = {"value": float(close.iloc[-1]), "delta": float(close.iloc[-1] - close.iloc[-2]), "prev": float(close.iloc[-2])}
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
def get_market_map():
    """종목코드 → 시장구분(코스피/코스닥/코넥스) 매핑. FDR StockListing의 Market 컬럼 활용."""
    try:
        df = fdr.StockListing('KRX')
        if df.empty or 'Code' not in df.columns or 'Market' not in df.columns:
            return {}
        df = df.copy()
        df['Code'] = df['Code'].astype(str).str.zfill(6)
        label = {
            'KOSPI': '코스피', 'KOSDAQ': '코스닥', 'KONEX': '코넥스',
            'KOSDAQ GLOBAL': '코스닥', 'KOSDAQ_GLOBAL': '코스닥',
        }
        return {
            row['Code']: label.get(str(row['Market']).upper().strip(), str(row['Market']))
            for _, row in df.iterrows() if pd.notna(row['Market'])
        }
    except Exception:
        return {}


def get_market_label(ticker_code):
    """종목코드의 시장 구분 라벨을 반환. 미국/실패 시 빈 문자열."""
    if not str(ticker_code).isdigit():
        return ""
    return get_market_map().get(str(ticker_code).zfill(6), "")


@st.cache_data(ttl=600)
def get_stock_list_by_market():
    """코스피/코스닥 전체 종목 리스트(시세·시총·업종 포함) — 종목 리스트 페이지용.
    반환: 정규화된 DataFrame[시장, 종목코드, 종목명, 현재가, 등락률, 거래대금(억), 시가총액(억), 업종]
    fdr.StockListing('KRX')가 막히면 _kr_market_snapshot(fdr 개별시장 → pykrx) 폴백으로 실데이터를 복구한다."""
    label = {'KOSPI': '코스피', 'KOSDAQ': '코스닥', 'KONEX': '코넥스',
             'KOSDAQ GLOBAL': '코스닥', 'KOSDAQ_GLOBAL': '코스닥'}

    def _merge_sector(out):
        # 업종 병합 (get_krx_stocks의 정제된 Sector) — 기존 로직과 동일
        try:
            krx = get_krx_stocks()
            if not krx.empty:
                out = pd.merge(out, krx[['Code', 'Sector']].rename(columns={'Code': '종목코드', 'Sector': '업종'}),
                               on='종목코드', how='left')
            else:
                out['업종'] = '-'
        except Exception:
            out['업종'] = '-'
        out['업종'] = out['업종'].fillna('-')
        # 🌐 [업종 복구 v2] get_krx_stocks가 비었거나 병합에 실패해 '-'로 남은 종목은 네이버 업종맵으로 최종 보강
        _miss = out['업종'].isin(['-', '기타/분류불가'])
        if _miss.any():
            _nsmap = _naver_sector_map()
            if _nsmap:
                out.loc[_miss, '업종'] = out.loc[_miss, '종목코드'].map(_nsmap).fillna(out.loc[_miss, '업종'])
        out = out[out['시장'].isin(['코스피', '코스닥', '코넥스'])]
        return out.reset_index(drop=True)

    # --- 1차: fdr 'KRX' 통합 (정상 시 기존과 동일한 출력) ---
    try:
        df = fdr.StockListing('KRX')
        if df is not None and not df.empty and 'Market' in df.columns:
            df = df.copy()
            df['Code'] = df['Code'].astype(str).str.zfill(6)

            def _num(col):
                if col not in df.columns:
                    return 0
                return pd.to_numeric(df[col].astype(str).str.replace(r'[^\d\.\-]', '', regex=True), errors='coerce').fillna(0)

            out = pd.DataFrame()
            out['시장'] = df['Market'].astype(str).str.upper().str.strip().map(lambda m: label.get(m, m))
            out['종목코드'] = df['Code']
            out['종목명'] = df['Name'] if 'Name' in df.columns else ''
            out['현재가'] = _num('Close').astype(int)
            out['등락률'] = _num('ChagesRatio').round(2)
            out['거래대금(억)'] = (_num('Amount') / 100000000).astype(int)
            out['시가총액(억)'] = (_num('Marcap') / 100000000).astype(int)
            return _merge_sector(out)
    except Exception:
        pass

    # --- 폴백: 다중소스 스냅샷(fdr 개별시장 → pykrx)으로 실데이터 복구 ---
    try:
        snap = _kr_market_snapshot()
        if not snap.empty:
            out = pd.DataFrame()
            out['시장'] = snap['Market']
            out['종목코드'] = snap['Code'].astype(str).str.zfill(6)
            out['종목명'] = snap['Name']
            out['현재가'] = pd.to_numeric(snap['Close'], errors='coerce').fillna(0).astype(int)
            out['등락률'] = pd.to_numeric(snap['ChagesRatio'], errors='coerce').fillna(0).round(2)
            out['거래대금(억)'] = (pd.to_numeric(snap['Amount'], errors='coerce').fillna(0) / 100000000).astype(int)
            out['시가총액(억)'] = (pd.to_numeric(snap['Marcap'], errors='coerce').fillna(0) / 100000000).astype(int)
            return _merge_sector(out)
    except Exception:
        pass

    return pd.DataFrame()


@st.cache_data(ttl=3600, show_spinner=False)
def _krx_list_from_naver(max_pages=22):
    """FDR 실패 시 폴백: 네이버 시가총액 페이지에서 종목명+코드 목록 구성(코스피+코스닥)."""
    rows, seen = [], set()
    for sosok in (0, 1):   # 0=코스피, 1=코스닥
        mkt_name = "코스피" if sosok == 0 else "코스닥"
        for page in range(1, max_pages + 1):
            try:
                url = f"https://finance.naver.com/sise/sise_market_sum.naver?sosok={sosok}&page={page}"
                res = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=5)
                soup = BeautifulSoup(res.content.decode("euc-kr", "replace"), "html.parser")
                table = soup.select_one("table.type_2")
                if not table:
                    break
                added = 0
                for a in table.select("a.tltle"):   # 종목명 링크 (네이버 클래스명 'tltle')
                    href = a.get("href", "")
                    m = re.search(r"code=(\d{6})", href)
                    if not m:
                        continue
                    code = m.group(1)
                    name = a.get_text(strip=True)
                    if not name or code in seen:
                        continue
                    seen.add(code)
                    rows.append({"Name": name, "Code": code, "Sector": "기타/분류불가", "Market": mkt_name})
                    added += 1
                if added == 0:
                    break   # 빈 페이지면 해당 시장 종료
            except Exception:
                break
    if rows:
        return pd.DataFrame(rows)
    return pd.DataFrame(columns=["Name", "Code", "Sector", "Market"])


# ── [NEW] 국내 ETF 전체 목록 로더 (우주항공·방산 등 테마 ETF 검색 지원) ──────
def _get_etf_list():
    """국내 상장 ETF 전체 목록을 DataFrame(Name, Code, Sector, Market)으로 반환.
    1) FinanceDataReader → 2) 네이버 ETF API → 3) pykrx 순서로 폴백."""
    # 1차: FinanceDataReader
    try:
        etf = fdr.StockListing('ETF/KR')
        if etf is not None and not etf.empty:
            code_col = next((c for c in ['Symbol', 'Code', 'symbol', 'code'] if c in etf.columns), None)
            name_col = next((c for c in ['Name', 'name'] if c in etf.columns), None)
            if code_col and name_col:
                out = etf[[name_col, code_col]].copy()
                out.columns = ['Name', 'Code']
                out['Code'] = out['Code'].astype(str).str.zfill(6)
                out['Sector'] = 'ETF'
                out['Market'] = 'ETF'
                return out.dropna(subset=['Name']).drop_duplicates(subset=['Code']).reset_index(drop=True)
    except Exception:
        pass
    # 2차: 네이버 ETF 시세 API (JSON)
    try:
        url = "https://finance.naver.com/api/sise/etfItemList.nhn"
        res = requests.get(url, headers={'User-Agent': 'Mozilla/5.0'}, timeout=5)
        items = res.json().get('result', {}).get('etfItemList', [])
        if items:
            rows = [{'Name': it.get('itemname'), 'Code': str(it.get('itemcode')).zfill(6),
                     'Sector': 'ETF', 'Market': 'ETF'} for it in items if it.get('itemcode')]
            if rows:
                return pd.DataFrame(rows).dropna(subset=['Name']).drop_duplicates(subset=['Code']).reset_index(drop=True)
    except Exception:
        pass
    # 3차: pykrx
    try:
        from pykrx import stock as _pykrx_stock
        tickers = _pykrx_stock.get_etf_ticker_list()
        rows = []
        for t in tickers:
            try:
                rows.append({'Name': _pykrx_stock.get_etf_ticker_name(t), 'Code': str(t).zfill(6),
                             'Sector': 'ETF', 'Market': 'ETF'})
            except Exception:
                continue
        if rows:
            return pd.DataFrame(rows).dropna(subset=['Name']).drop_duplicates(subset=['Code']).reset_index(drop=True)
    except Exception:
        pass
    return pd.DataFrame(columns=['Name', 'Code', 'Sector', 'Market'])

@st.cache_data(ttl=86400, show_spinner=False)
def _naver_sector_map():
    """🌐 [업종 복구 엔진 v2] 네이버 '업종별 시세' 그룹(~80개)을 병렬 크롤링해
    {6자리 종목코드: 업종명} '전 종목' 맵을 구성 (하루 1회 캐시).
    KRX(fdr 'KRX-DESC')가 클라우드 IP를 차단해 업종이 통째로 비는 문제의 최종 폴백. 실패 시 {}."""
    base = "https://finance.naver.com"
    headers = {'User-Agent': 'Mozilla/5.0'}
    try:
        res = requests.get(f"{base}/sise/sise_group.naver?type=upjong", headers=headers, timeout=6)
        soup = BeautifulSoup(res.content.decode('euc-kr', errors='replace'), 'html.parser')
        groups, seen = [], set()
        for a in soup.select('a[href*="sise_group_detail.naver"]'):
            m = re.search(r'no=(\d+)', a.get('href', ''))
            name = a.get_text(strip=True)
            if m and name and m.group(1) not in seen:
                seen.add(m.group(1))
                groups.append((m.group(1), name))
        if not groups:
            return {}

        def _fetch_group(item):
            no, name = item
            codes = []
            try:
                r = requests.get(f"{base}/sise/sise_group_detail.naver?type=upjong&no={no}",
                                 headers=headers, timeout=6)
                s = BeautifulSoup(r.content.decode('euc-kr', errors='replace'), 'html.parser')
                for a in s.select('a[href*="/item/main.naver?code="]'):
                    m2 = re.search(r'code=(\d{6})', a.get('href', ''))
                    if m2:
                        codes.append(m2.group(1))
            except Exception:
                pass
            return name, codes

        sector_map = {}
        with concurrent.futures.ThreadPoolExecutor(max_workers=10) as ex:
            for name, codes in ex.map(_fetch_group, groups):
                for c in codes:
                    sector_map.setdefault(c, name)
        return sector_map
    except Exception:
        return {}


@st.cache_data(ttl=86400)  # [속도개선] 전체 종목 리스트는 하루 1회만 네트워크 수집. 기존 무(無)캐시 → 매 렌더마다 fdr 2회 호출 + 2,800행 apply 가 반복되던 것을 제거.
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

            # 🌐 [업종 복구 v2] KRX-DESC가 막혀 업종이 비면 네이버 '업종별 시세' 전체맵으로 채움 (하루 1회 캐시)
            _miss = df['Sector'].isin(['기타/분류불가', '-', ''])
            if _miss.any():
                _nsmap = _naver_sector_map()
                if _nsmap:
                    df.loc[_miss, 'Sector'] = df.loc[_miss, 'Code'].map(_nsmap).fillna('기타/분류불가')

            # 시장 구분(코스피/코스닥/코넥스) 컬럼 추가
            mkt_col = next((c for c in ['Market', 'market', 'MarketId', 'Marketid'] if c in df.columns), None)
            if mkt_col:
                _mmap = {"KOSPI": "코스피", "KOSDAQ": "코스닥", "KOSDAQ GLOBAL": "코스닥",
                         "KONEX": "코넥스", "KOSPI200": "코스피"}
                df['Market'] = df[mkt_col].astype(str).str.upper().str.strip().map(_mmap).fillna(df[mkt_col].astype(str))
            else:
                df['Market'] = ""

            df = df[['Name', 'Code', 'Sector', 'Market']].copy()
            df['Code'] = df['Code'].astype(str).str.zfill(6)
            
            # 🛰️ [NEW] ETF 목록 병합 (우주항공·방산·반도체 등 테마 ETF 검색 가능하게)
            #    → 주식 목록 '뒤'에 붙여서, 시총 상위 N개 스캔 등 기존 로직(head)에는 영향 없음
            etf_df = _get_etf_list()
            if not etf_df.empty:
                df = pd.concat([df, etf_df], ignore_index=True)
            
            return df.drop_duplicates(subset=['Name']).reset_index(drop=True)
            
    except Exception: 
        pass
        
    # FDR 실패/빈 결과 → 네이버 시가총액 폴백으로 목록 구성
    nv = _krx_list_from_naver()
    etf_df = _get_etf_list()
    if not nv.empty:
        if not etf_df.empty:
            nv = pd.concat([nv, etf_df], ignore_index=True).drop_duplicates(subset=['Name']).reset_index(drop=True)
        return nv
    if not etf_df.empty:
        return etf_df
    return pd.DataFrame(columns=['Name', 'Code', 'Sector', 'Market'])

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
    
    name_str = str(eng_name).strip()
    # 1. 티커 완전 일치 검사
    if name_str.upper() in ko_dict:
        return ko_dict[name_str.upper()]

    # 2. 회사 '이름' 키만 부분 일치 (티커 키 'V','MA','KO' 등이 'adVanced' 같은 단어에
    #    부분 매칭되어 AMD→비자 가 되던 버그 방지: 소문자가 포함된 이름형 키만, 단어 경계로 매칭)
    low = name_str.lower()
    for key, val in ko_dict.items():
        if any(ch.islower() for ch in key) and re.search(r"\b" + re.escape(key.lower()) + r"\b", low):
            return val

    # 사전에 없으면 원래 영문 이름 그대로 반환
    return name_str

@st.cache_data(ttl=300, show_spinner=False)
def _kr_market_snapshot():
    """fdr.StockListing('KRX')가 막혔을 때를 위한 폴백 시세 스냅샷.
    소스를 순차 시도하여 실데이터([Code, Name, Close, ChagesRatio, Amount, Marcap, Market])를 확보한다.
      1) fdr를 KOSPI/KOSDAQ로 분할 시도 ('KRX' 통합이 막혀도 개별은 되는 경우가 있음)
      2) pykrx (KRX의 다른 엔드포인트 — fdr이 죽어도 살아있는 경우가 많음)
    어떤 경우에도 예외를 밖으로 던지지 않으며, 모두 실패하면 빈 DataFrame을 반환한다(→ 기존 동작 이하로 떨어지지 않음)."""
    def _num(df, col):
        if col not in df.columns:
            return pd.Series([0] * len(df))
        return pd.to_numeric(df[col].astype(str).str.replace(r'[^\d\.\-]', '', regex=True), errors='coerce').fillna(0)

    # --- 소스 1: FDR 개별 시장 ---
    def _from_fdr():
        frames = []
        for mcode, kname in [("KOSPI", "코스피"), ("KOSDAQ", "코스닥")]:
            try:
                d = fdr.StockListing(mcode)
                if d is None or d.empty:
                    continue
                d = d.copy()
                d['__mkt'] = kname
                frames.append(d)
            except Exception:
                continue
        if not frames:
            return pd.DataFrame()
        df = pd.concat(frames, ignore_index=True)
        out = pd.DataFrame()
        out['Code'] = (df['Code'].astype(str).str.zfill(6)) if 'Code' in df.columns else ""
        out['Name'] = df['Name'] if 'Name' in df.columns else ""
        out['Close'] = _num(df, 'Close')
        out['ChagesRatio'] = _num(df, 'ChagesRatio')
        out['Amount'] = _num(df, 'Amount')
        out['Marcap'] = _num(df, 'Marcap')
        out['Market'] = df['__mkt']
        return out[out['Code'].astype(str).str.len() == 6].reset_index(drop=True)

    # --- 소스 2: pykrx ---
    def _from_pykrx():
        if not HAS_PYKRX:
            return pd.DataFrame()
        import datetime as _dt
        frames = []
        for mcode, kname in [("KOSPI", "코스피"), ("KOSDAQ", "코스닥")]:
            ohlcv, used = None, None
            for back in range(0, 8):   # 주말/공휴일이면 직전 거래일로 후퇴
                ds = (_dt.datetime.now() - _dt.timedelta(days=back)).strftime("%Y%m%d")
                try:
                    t = pykrx_stock.get_market_ohlcv_by_ticker(ds, market=mcode)
                    if t is not None and not t.empty and float(pd.to_numeric(t['종가'], errors='coerce').fillna(0).sum()) > 0:
                        ohlcv, used = t, ds
                        break
                except Exception:
                    continue
            if ohlcv is None:
                continue
            o = ohlcv.reset_index().rename(columns={ohlcv.index.name or 'index': 'Code'})
            o = o.rename(columns={o.columns[0]: 'Code'})   # 인덱스(티커) → Code 보장
            try:
                cap = pykrx_stock.get_market_cap_by_ticker(used, market=mcode).reset_index()
                cap = cap.rename(columns={cap.columns[0]: 'Code'})
                o = pd.merge(o, cap[['Code', '시가총액']], on='Code', how='left')
            except Exception:
                o['시가총액'] = 0
            o['__mkt'] = kname
            frames.append(o)
        if not frames:
            return pd.DataFrame()
        df = pd.concat(frames, ignore_index=True)
        out = pd.DataFrame()
        out['Code'] = df['Code'].astype(str).str.zfill(6)
        out['Close'] = pd.to_numeric(df.get('종가', 0), errors='coerce').fillna(0)
        out['ChagesRatio'] = pd.to_numeric(df.get('등락률', 0), errors='coerce').fillna(0)
        out['Amount'] = pd.to_numeric(df.get('거래대금', 0), errors='coerce').fillna(0)
        out['Marcap'] = pd.to_numeric(df.get('시가총액', 0), errors='coerce').fillna(0)
        out['Market'] = df['__mkt']
        # 종목명은 get_krx_stocks(이름↔코드 매핑)에서 병합 (pykrx OHLCV엔 이름이 없음)
        try:
            krx = get_krx_stocks()
            if not krx.empty:
                out = pd.merge(out, krx[['Code', 'Name']], on='Code', how='left')
        except Exception:
            pass
        if 'Name' not in out.columns:
            out['Name'] = ""
        out['Name'] = out['Name'].fillna("")
        return out.reset_index(drop=True)

    for _src in (_from_fdr, _from_pykrx):
        try:
            snap = _src()
            if snap is not None and not snap.empty and float(snap['Close'].abs().sum()) > 0:
                return snap.reset_index(drop=True)
        except Exception:
            continue
    return pd.DataFrame(columns=['Code', 'Name', 'Close', 'ChagesRatio', 'Amount', 'Marcap', 'Market'])


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

    # 🚨 1차 소스(fdr 'KRX') 실패 → 다중소스 스냅샷(fdr 개별시장 → pykrx)으로 '실제 등락률·거래대금' 복구
    snap = _kr_market_snapshot()
    if not snap.empty:
        fb = snap.copy()
        # 1차 경로와 동일 기준으로 ETF/스팩/선물 등 제외
        mask = fb['Name'].astype(str).str.contains('KODEX|TIGER|KBSTAR|KOSEF|ARIRANG|HANARO|ACE|스팩|ETN|선물|인버스|레버리지', na=False)
        fb = fb[~mask].copy()
        fb = fb.sort_values('Amount', ascending=False).head(limit)
        fb['Amount_Ouk'] = (fb['Amount'] / 100000000).astype(int)
        try:
            krx = get_krx_stocks()
            if not krx.empty:
                fb = pd.merge(fb, krx[['Code', 'Sector']], on='Code', how='left')
            if 'Sector' not in fb.columns:
                fb['Sector'] = '기타/분류불가'
            fb['Sector'] = fb['Sector'].fillna('기타/분류불가')
        except Exception:
            fb['Sector'] = '기타/분류불가'
        return fb[['Code', 'Name', 'Close', 'ChagesRatio', 'Amount_Ouk', 'Sector']]

    # 🚨 모든 시세 소스 실패 시: 이름만이라도 표시(등락률 0). 빈 결과면 빈 DF 반환.
    fallback_df = get_krx_stocks().head(limit)
    if fallback_df.empty:
        return pd.DataFrame(columns=['Code', 'Name', 'Close', 'ChagesRatio', 'Amount_Ouk', 'Sector'])
    fallback_df = fallback_df.copy()
    fallback_df['Close'] = 0
    fallback_df['ChagesRatio'] = 0.0
    fallback_df['Amount_Ouk'] = 1000
    return fallback_df[['Code', 'Name', 'Close', 'ChagesRatio', 'Amount_Ouk', 'Sector']]

# ─────────────────────────────────────────────────────────────────────
# [신규] ETF·ETN·레버리지/인버스/선물 등 '상품' 판별
#   → 차트 기술분석 대상이 아니므로 스캐너 유니버스(단기스윙·낙폭과대·AI발굴기·장기가치)에서 제외.
#   브랜드 접두어 + 키워드 + 네이버 ETF 코드목록(클라우드 호환)으로 판정.
# ─────────────────────────────────────────────────────────────────────
_KR_ETF_BRANDS = (
    "KODEX", "TIGER", "KBSTAR", "RISE", "KINDEX", "ACE", "ARIRANG", "PLUS",
    "HANARO", "KOSEF", "KIWOOM", "SOL", "TIMEFOLIO", "WOORI", "TREX", "KOACT",
    "KCGI", "FOCUS", "히어로즈", "마이티",
)
_KR_PRODUCT_KEYWORDS = ("ETF", "ETN", "레버리지", "인버스", "선물", "액티브", "커버드콜")


@st.cache_data(ttl=86400, show_spinner=False)
def _get_kr_etf_codes():
    """네이버 etfItemList(+etnItemList) → 전체 ETF/ETN 종목코드 집합(클라우드 호환).
    Content-Type에 의존하지 않고 직접 파싱. 실패 시 빈 set."""
    import json as _json
    codes = set()
    for url, key in (
        ("https://finance.naver.com/api/sise/etfItemList.nhn", "etfItemList"),
        ("https://finance.naver.com/api/sise/etnItemList.nhn", "etnItemList"),
    ):
        try:
            r = requests.get(url, headers={"User-Agent": "Mozilla/5.0",
                                           "Referer": "https://finance.naver.com/sise/etf.naver"},
                             timeout=7)
            if r.status_code != 200:
                continue
            try:
                j = r.json()
            except Exception:
                j = _json.loads(r.text)
            items = ((j or {}).get("result") or {}).get(key) or []
            for it in items:
                c = str(it.get("itemcode", "")).strip()
                if c.isdigit():
                    codes.add(c.zfill(6))
        except Exception:
            continue
    return codes


def is_kr_etf_etn(name, code=""):
    """국내 ETF·ETN·레버리지/인버스/선물 등 '상품' 여부 (차트 기술분석 비대상 → 스캐너 제외)."""
    s = str(name or "").upper().replace(" ", "")
    if s:
        if any(s.startswith(b) for b in _KR_ETF_BRANDS):
            return True
        if any(k in s for k in _KR_PRODUCT_KEYWORDS):
            return True
    try:
        c = str(code or "").strip()
        if c.isdigit() and c.zfill(6) in _get_kr_etf_codes():
            return True
    except Exception:
        pass
    return False


@st.cache_data(ttl=300)
def get_scan_targets(limit=50):
    def _drop_products(lst):
        return [(n, c) for n, c in lst if not is_kr_etf_etn(n, c)]
    try:
        df_fdr = fdr.StockListing('KRX')
        if not df_fdr.empty:
            mask = df_fdr['Name'].str.contains('KODEX|TIGER|KBSTAR|KOSEF|ARIRANG|HANARO|ACE|스팩|ETN|선물|인버스|레버리지', na=False)
            df_fdr = df_fdr[~mask].drop_duplicates(subset=['Name'])
            if 'Amount' in df_fdr.columns:
                df_fdr['Amount'] = pd.to_numeric(df_fdr['Amount'].astype(str).str.replace(r'[^\d\.]', '', regex=True), errors='coerce').fillna(0.0)
                df_fdr = df_fdr.sort_values('Amount', ascending=False)
            targets = _drop_products(df_fdr.head(limit * 2)[['Name', 'Code']].values.tolist())[:limit]
            if targets: return targets
    except Exception: pass

    # 🚨 중복 현상 해결: limit 개수를 채우기 위해 억지로 리스트를 곱하여 복사하는 로직 제거
    fallback_targets = _drop_products(get_krx_stocks()[['Name', 'Code']].values.tolist())
    if fallback_targets:
        return fallback_targets[:limit] # 준비된 예비 데이터만큼만 중복 없이 반환
    return []


@st.cache_data(ttl=900, show_spinner=False)
def get_drawdown_info(code, lookback="52주", rebound_days=120):
    """현재가·기간내 최고가·낙폭(%)·RSI 계산(가벼움). 실패 시 None.
    fdr.DataReader는 국내(6자리)·미국(티커) 모두 지원. lookback: '52주' 또는 '전체'."""
    try:
        if lookback == "52주":
            start = (datetime.now() - timedelta(days=370)).strftime("%Y-%m-%d")
            df = fdr.DataReader(str(code), start)
        else:
            df = fdr.DataReader(str(code))
        if df is None or df.empty or "Close" not in df.columns:
            return None
        close = df["Close"].dropna()
        if len(close) < 20:
            return None
        cur = float(close.iloc[-1])
        if cur <= 0:
            return None
        high_series = df["High"].dropna() if ("High" in df.columns and df["High"].notna().any()) else close
        hi = float(high_series.max())
        if hi <= 0:
            return None
        dd = round((cur / hi - 1) * 100, 1)
        try:
            hd = high_series.idxmax()
            high_date = hd.strftime("%y.%m.%d") if hasattr(hd, "strftime") else str(hd)[:10]
        except Exception:
            high_date = ""
        rsi = None
        try:
            d = close.diff()
            up = d.clip(lower=0).rolling(14).mean()
            dn = (-d.clip(upper=0)).rolling(14).mean()
            rs = up / dn
            val = rs.iloc[-1]
            if pd.notna(val):
                rsi = round(float(100 - 100 / (1 + val)), 0)
        except Exception:
            pass
        # 최근 저점 대비 반등률(바닥 확인용)
        # 최근 저점 대비 반등률 (바닥 확인용, 기간 조절 가능)
        try:
            rb = max(5, int(rebound_days))
            lo = float(close.tail(rb).min())
            rebound = round((cur / lo - 1) * 100, 1) if lo > 0 else None
        except Exception:
            rebound = None
        
        # 🩹 [NEW] 회복 신호 6종 — 이미 받아온 데이터만 사용 (추가 네트워크 0건)
        sig = {"ma20_recover": False, "golden5_20": False, "higher_low": False,
               "vol_revive": False, "obv_rise": False, "ma60_up": False}
        try:
            ma5 = close.rolling(5).mean()
            ma20 = close.rolling(20).mean()
            ma60 = close.rolling(60).mean()
            if pd.notna(ma20.iloc[-1]):
                sig["ma20_recover"] = bool(cur > float(ma20.iloc[-1]))                     # 20일선 회복
            if pd.notna(ma5.iloc[-1]) and pd.notna(ma20.iloc[-1]):
                sig["golden5_20"] = bool(float(ma5.iloc[-1]) > float(ma20.iloc[-1]))       # 단기 골든(5>20)
            if len(close) >= 40:
                _lo_recent = float(close.tail(20).min())
                _lo_prev = float(close.tail(40).head(20).min())
                sig["higher_low"] = bool(_lo_recent > _lo_prev * 1.005)                    # 저점 높이기
            if len(ma60.dropna()) >= 11:
                sig["ma60_up"] = bool(float(ma60.iloc[-1]) > float(ma60.iloc[-11]))        # 60일선 상승 전환
            if "Volume" in df.columns and df["Volume"].notna().any():
                vol = df["Volume"].dropna()
                if len(vol) >= 40:
                    _v_recent = float(vol.tail(10).mean())
                    _v_base = float(vol.tail(40).head(30).mean())
                    sig["vol_revive"] = bool(_v_base > 0 and _v_recent > _v_base * 1.3)    # 거래량 회복(+30%)
                # OBV(매집) 20일 증가
                _common = close.index.intersection(vol.index)
                if len(_common) >= 21:
                    _c2, _v2 = close.loc[_common], vol.loc[_common]
                    obv = (np.sign(_c2.diff()).fillna(0) * _v2).cumsum()
                    sig["obv_rise"] = bool(float(obv.iloc[-1]) > float(obv.iloc[-21]))
        except Exception:
            pass
        
        return {"current": cur, "high": hi, "high_date": high_date,
                "drawdown": dd, "rsi": rsi, "rebound": rebound, **sig}
    except Exception:
        return None


# ── 🩹 [NEW] 낙폭과대 '회복 가능성' 진단 보조 함수들 ─────────────────────────
@st.cache_data(ttl=900, show_spinner=False)
def get_kr_sector_heat():
    """네이버 업종별 시세에서 {업종명: 전일대비 등락률%} 맵 구성 (HTTP 1회, 15분 캐시)."""
    try:
        url = "https://finance.naver.com/sise/sise_group.naver?type=upjong"
        res = requests.get(url, headers={'User-Agent': 'Mozilla/5.0'}, timeout=5)
        tables = pd.read_html(StringIO(res.content.decode('euc-kr', errors='replace')))
        for t in tables:
            cols = [str(c) for c in t.columns]
            if any('업종명' in c for c in cols):
                name_col = next(c for c in t.columns if '업종명' in str(c))
                chg_col = next((c for c in t.columns if '전일대비' in str(c) or '등락' in str(c)), None)
                if chg_col is None:
                    continue
                heat = {}
                for _, r in t.dropna(subset=[name_col]).iterrows():
                    nm = str(r[name_col]).strip()
                    try:
                        v = float(str(r[chg_col]).replace('%', '').replace('+', '').strip())
                        if nm and nm != '업종명':
                            heat[nm] = v
                    except Exception:
                        continue
                if heat:
                    return heat
    except Exception:
        pass
    return {}

@st.cache_data(ttl=900, show_spinner=False)
def get_us_sector_heat():
    """미국 섹터 SPDR ETF의 최근 5거래일 수익률(%) 맵 — {한글섹터명: %} (15분 캐시)."""
    etf_map = {"IT/기술": "XLK", "금융": "XLF", "헬스케어/바이오": "XLV", "임의소비재": "XLY",
               "산업재": "XLI", "통신/플랫폼": "XLC", "필수소비재": "XLP", "에너지": "XLE",
               "소재": "XLB", "부동산": "XLRE", "유틸리티": "XLU"}
    heat = {}
    start = (datetime.now() - timedelta(days=20)).strftime("%Y-%m-%d")
    for sec_kr, etf in etf_map.items():
        try:
            d = fdr.DataReader(etf, start)
            c = d["Close"].dropna()
            if len(c) >= 6:
                heat[sec_kr] = round((float(c.iloc[-1]) / float(c.iloc[-6]) - 1) * 100, 2)
        except Exception:
            continue
    return heat

def match_sector_heat(sector, kr_heat, us_heat, is_kr):
    """종목 섹터 문자열 ↔ 온기 맵 베스트 매칭. 실패 시 None."""
    s = str(sector or "").strip()
    if not s or s in ("-", "기타/분류불가", "ETF"):
        return None
    heat = kr_heat if is_kr else us_heat
    if not heat:
        return None
    if s in heat:
        return heat[s]
    # 부분 일치 (양방향 contains, 2글자 이상)
    for k, v in heat.items():
        if len(s) >= 2 and (s in k or k in s):
            return v
    return None

def calc_recovery_score(row, heat_val):
    """낙폭 종목의 '회복 가능성' 점수(0~100)·등급·근거 산출.
    기술 신호(20일선 회복·저점 높이기·거래량/OBV 등) + 반등 위치 + RSI 구간 + 테마 온기 합산."""
    score, reasons = 0, []
    rb = row.get("rebound")
    if rb is not None:
        if 5 <= rb <= 40: score += 20; reasons.append("바닥 확인+반등 초입")
        elif 0 <= rb < 5: score += 5; reasons.append("바닥권(반등 미확인)")
        elif 40 < rb <= 70: score += 10; reasons.append("반등 진행 중")
        elif rb > 70: score -= 10; reasons.append("반등 후반(늦은 진입 주의)")
    rsi = row.get("rsi")
    if rsi is not None:
        if 35 <= rsi <= 60: score += 15; reasons.append("RSI 회복 구간")
        elif 30 <= rsi < 35: score += 10; reasons.append("RSI 과매도 탈출 시도")
        elif rsi < 25: score -= 10; reasons.append("⚠️ 하락 진행형(떨어지는 칼날)")
        elif rsi > 70: score -= 5; reasons.append("단기 과열")
    if row.get("ma20_recover"): score += 15; reasons.append("20일선 회복")
    if row.get("golden5_20"): score += 10; reasons.append("단기 골든(5>20)")
    if row.get("higher_low"): score += 15; reasons.append("저점 높이기")
    if row.get("vol_revive"): score += 10; reasons.append("거래량 회복")
    if row.get("obv_rise"): score += 10; reasons.append("OBV(매집) 증가")
    if row.get("ma60_up"): score += 5; reasons.append("60일선 상승 전환")
    if heat_val is not None:
        if heat_val >= 1.0: score += 10; reasons.append(f"🔥 업종 온기 +{heat_val:.1f}%")
        elif heat_val >= 0: score += 5; reasons.append(f"업종 보합({heat_val:+.1f}%)")
        elif heat_val <= -1.0: score -= 5; reasons.append(f"🥶 업종 냉각({heat_val:.1f}%)")
    score = max(0, min(100, score))
    if score >= 70: grade = "🟢 회복 유력"
    elif score >= 50: grade = "🟡 회복 조짐"
    elif score >= 30: grade = "⚪ 관찰"
    else: grade = "🔴 바닥 미확인"
    return score, grade, " · ".join(reasons) if reasons else "신호 없음"


@st.cache_data(ttl=86400, show_spinner=False)
def get_stock_sector_kr(code):
    """종목 하나의 업종명을 네이버에서 조회. 인코딩 자동 판별 + 깨진(한자/모지바케) 결과는 거부.
    낙폭 스캐너에서 FDR 업종이 비었을 때 '결과 종목만' 보강용. 실패 시 None."""
    code = str(code).strip()
    if not code.isdigit():
        return None

    def _ok(s):
        """정상 한글 업종명만 통과: CJK 한자(깨짐 신호) 있으면 거부, 한글 비중 과반 요구."""
        if not s:
            return None
        s = str(s).strip()
        if not s or len(s) > 30:
            return None
        if any('\u3400' <= ch <= '\u9fff' for ch in s):   # CJK 한자 → 인코딩 깨짐
            return None
        han = sum(1 for ch in s if '가' <= ch <= '힣')
        return s if han >= max(1, int(len(s) * 0.5)) else None

    # ① 모바일 통합 API (JSON — UTF-8)
    try:
        data = _naver_json(f"https://m.stock.naver.com/api/stock/{code}/integration")
        if isinstance(data, dict):
            cands = []
            for k in ("industryCodeName", "industryGroupKor", "industryName", "upjongName", "sectorName"):
                if data.get(k):
                    cands.append(data[k])
            for sub in ("stockInfo", "industryInfo", "summary"):
                si = data.get(sub)
                if isinstance(si, dict):
                    for k in ("industryName", "industryGroupKor", "industry", "sectorName"):
                        if si.get(k):
                            cands.append(si[k])
            for c in cands:
                v = _ok(c)
                if v:
                    return v
    except Exception:
        pass

    # ② 메인 페이지 업종 링크 (EUC-KR/UTF-8 자동 판별)
    try:
        res = requests.get(f"https://finance.naver.com/item/main.naver?code={code}",
                           headers={"User-Agent": "Mozilla/5.0"}, timeout=4)
        for enc in ("euc-kr", "utf-8"):
            try:
                soup = BeautifulSoup(res.content.decode(enc, "replace"), "html.parser")
            except Exception:
                continue
            for a in soup.select("a"):
                href = a.get("href", "")
                if "sise_group_detail" in href and "upjong" in href:
                    v = _ok(a.get_text(strip=True))
                    if v:
                        return v
    except Exception:
        pass
    return None


@st.cache_data(ttl=86400)
def get_us_sector_map():
    """S&P500 위키 표에서 {티커: 한글 섹터} 매핑 구성(낙폭 스캐너 표시용)."""
    try:
        url = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"
        res = requests.get(url, headers={'User-Agent': 'Mozilla/5.0'})
        df = pd.read_html(StringIO(res.text))[0]
        sec_col = next((c for c in df.columns if 'Sector' in str(c)), None)
        if not sec_col or 'Symbol' not in df.columns:
            return {}
        kmap = {"Information Technology": "IT/기술", "Financials": "금융", "Health Care": "헬스케어",
                "Consumer Discretionary": "임의소비재", "Consumer Staples": "필수소비재",
                "Industrials": "산업재", "Energy": "에너지", "Materials": "소재",
                "Real Estate": "부동산", "Utilities": "유틸리티", "Communication Services": "커뮤니케이션"}
        out = {}
        for _, row in df.iterrows():
            sym = str(row['Symbol']).replace('.', '-')
            sec = str(row[sec_col]).strip()
            out[sym] = kmap.get(sec, sec)
        return out
    except Exception:
        return {}


# =====================================================================
# [신규] 지금 뜨는 섹터 (국장·미장) — 테마별 대표 종목 평균 등락률
#   curated 테마→티커 맵 → 오늘 등락률 배치 조회 → 테마 평균으로 강세 순 정렬
# =====================================================================
US_THEME_MAP = {
    "HBM/메모리": ["MU", "WDC", "STX", "SIMO", "FORM", "AMKR"],
    "반도체 장비": ["AMAT", "LRCX", "KLAC", "ASML", "ONTO", "COHU", "ACLS"],
    "반도체": ["NVDA", "AMD", "AVGO", "QCOM", "ARM", "INTC", "MRVL", "TSM"],
    "AI 데이터센터/인프라": ["VRT", "ANET", "SMCI", "DELL", "COHR", "NBIS", "CIEN"],
    "전력/유틸리티(AI 수요)": ["VST", "CEG", "NRG", "TLN", "GEV", "NEE"],
    "원자력/SMR/핵융합": ["CCJ", "SMR", "OKLO", "LEU", "UEC", "NNE", "BWXT"],
    "전력 인프라/송배전": ["ETN", "PWR", "GEV", "VRT", "EMR", "HUBB"],
    "양자컴퓨팅": ["IONQ", "RGTI", "QBTS", "QUBT", "ARQQ"],
    "휴머노이드 로봇": ["TER", "ISRG", "ZBRA", "CGNX"],
    "드론/eVTOL": ["ACHR", "JOBY", "EH", "KTOS", "AVAV"],
    "우주/위성": ["RKLB", "ASTS", "LUNR", "PL", "BKSY"],
    "위성통신": ["ASTS", "IRDM", "GSAT", "GILT", "VSAT"],
    "비만치료제(GLP-1)": ["LLY", "NVO", "VKTX", "AMGN", "ALT"],
    "유전자편집/치료": ["CRSP", "NTLA", "BEAM", "EDIT", "RXRX"],
    "원격의료/디지털헬스": ["HIMS", "DXCM", "TDOC", "PODD", "GH"],
    "헬스케어": ["UNH", "JNJ", "LLY", "ABBV", "MRK", "PFE"],
    "크립토/채굴": ["MARA", "RIOT", "CLSK", "CIFR", "IREN", "HUT", "BTBT"],
    "스테이블코인/RWA": ["COIN", "MSTR", "HOOD", "GLXY"],
    "핀테크/결제": ["SQ", "SOFI", "AFRM", "HOOD", "FOUR", "BILL", "PYPL"],
    "전기차": ["TSLA", "RIVN", "LCID", "LI", "NIO", "XPEV"],
    "2차전지/충전": ["ALB", "CHPT", "BLNK", "QS", "LAC", "EVGO"],
    "태양광": ["FSLR", "ENPH", "RUN", "ARRY", "SHLS", "JKS", "CSIQ"],
    "수소/연료전지": ["PLUG", "BE", "BLDP", "FCEL", "LIN"],
    "금/광물/희토류": ["NEM", "GOLD", "AEM", "CDE", "MP", "FCX", "SCCO"],
    "농업/비료/식량": ["NTR", "MOS", "CF", "ADM", "BG", "TSN"],
    "정유/가스": ["XOM", "CVX", "COP", "OXY", "DVN", "SLB", "EOG"],
    "항공우주/방산": ["LMT", "RTX", "NOC", "GD", "BA", "LDOS", "CW"],
    "여행/항공/크루즈": ["CCL", "RCL", "NCLH", "DAL", "UAL", "LUV", "ABNB"],
    "사이버보안": ["CRWD", "PANW", "ZS", "FTNT", "NET", "S", "GEN"],
    "AI 소프트웨어/에이전트": ["PLTR", "NOW", "AI", "SNOW", "DDOG", "HUBS"],
    "소셜/디지털광고": ["META", "GOOGL", "PINS", "SNAP", "APP", "TTD"],
    "소비/엔터/스트리밍": ["NFLX", "DIS", "ROKU", "SPOT"],
    "이커머스/리테일": ["AMZN", "WMT", "COST", "TGT", "CHWY", "ETSY"],
    "게임/메타버스": ["RBLX", "EA", "TTWO", "U", "PLTK", "NTES"],
    "중국 빅테크": ["BABA", "PDD", "JD", "BIDU", "LI", "FUTU"],
    "금융": ["JPM", "BAC", "WFC", "GS", "MS", "SCHW", "BLK"],
    "리츠/배당": ["O", "PLD", "AMT", "SPG", "WELL", "STAG"],
    "빅테크(M7)": ["AAPL", "MSFT", "GOOGL", "AMZN", "META", "NVDA", "TSLA"],
    "필수소비/식음료": ["KO", "PEP", "MDLZ", "CMG", "GIS", "SBUX"],
}

KR_THEME_MAP = {
    "반도체": ["삼성전자", "SK하이닉스", "한미반도체", "DB하이텍", "리노공업"],
    "HBM/반도체 소부장": ["한미반도체", "리노공업", "주성엔지니어링", "원익IPS", "솔브레인", "ISC", "하나마이크론", "테크윙"],
    "2차전지": ["LG에너지솔루션", "삼성SDI", "LG화학", "에코프로비엠", "에코프로", "엘앤에프", "포스코퓨처엠"],
    "자동차/부품": ["현대차", "기아", "현대모비스", "한국타이어앤테크놀로지", "현대위아", "HL만도"],
    "바이오/제약": ["삼성바이오로직스", "셀트리온", "알테오젠", "유한양행", "SK바이오팜", "HLB", "리가켐바이오"],
    "인터넷/플랫폼": ["NAVER", "카카오", "카카오페이", "카카오뱅크", "더존비즈온"],
    "게임": ["엔씨소프트", "넷마블", "크래프톤", "펄어비스", "위메이드", "카카오게임즈", "시프트업"],
    "방산/우주항공": ["한화에어로스페이스", "한국항공우주", "LIG넥스원", "현대로템", "한화시스템"],
    "조선": ["HD한국조선해양", "삼성중공업", "한화오션", "HD현대미포", "HD현대중공업"],
    "원자력/SMR": ["두산에너빌리티", "한전기술", "한전KPS", "비에이치아이", "우진"],
    "전력기기/전선": ["HD현대일렉트릭", "LS ELECTRIC", "LS", "대한전선", "제룡전기", "일진전기"],
    "금융지주/보험": ["KB금융", "신한지주", "하나금융지주", "우리금융지주", "메리츠금융지주", "삼성생명", "삼성화재"],
    "증권": ["미래에셋증권", "삼성증권", "키움증권", "NH투자증권", "한국금융지주"],
    "철강/비철금속": ["POSCO홀딩스", "현대제철", "고려아연", "풍산", "동국제강"],
    "화학/정유": ["LG화학", "롯데케미칼", "S-Oil", "SK이노베이션", "금호석유", "한화솔루션"],
    "엔터/미디어": ["하이브", "에스엠", "JYP Ent.", "와이지엔터테인먼트", "CJ ENM"],
    "화장품/뷰티": ["아모레퍼시픽", "LG생활건강", "코스맥스", "한국콜마", "에이피알", "실리콘투"],
    "음식료": ["CJ제일제당", "오리온", "농심", "롯데칠성", "삼양식품"],
    "로봇": ["두산로보틱스", "레인보우로보틱스", "로보티즈", "유진로봇", "에스피지"],
    "의료기기/미용": ["클래시스", "휴젤", "제이시스메디칼", "파마리서치", "루닛", "뷰노"],
    "풍력/신재생": ["씨에스윈드", "씨에스베어링", "유니슨", "대명에너지"],
    "건설/플랜트": ["현대건설", "대우건설", "GS건설", "DL이앤씨", "삼성E&A"],
    "지주/통신": ["SK", "LG", "삼성물산", "SK텔레콤", "KT", "LG유플러스"],
    "우주/위성": ["한국항공우주", "쎄트렉아이", "켄코아에어로스페이스", "AP위성", "인텔리안테크"],
    "AI 반도체/팹리스": ["파두", "오픈엣지테크놀로지", "가온칩스", "칩스앤미디어", "에이디테크놀로지"],
}


@st.cache_data(ttl=600)
def get_kr_universe_naver(per_market=200):
    """네이버 모바일 API 시총 상위 → DataFrame[종목코드,종목명,등락률,현재가] (코스피+코스닥).
    fdr.StockListing('KRX')가 클라우드에서 막혀도 동작하는 네이버 기반 유니버스."""
    rows = []
    for mkt in ("KOSPI", "KOSDAQ"):
        got = 0
        for page in range(1, 6):
            data = _naver_json(f"https://m.stock.naver.com/api/stocks/marketValue/{mkt}?page={page}&pageSize=100")
            stocks = (data or {}).get("stocks") or []
            if not stocks:
                break
            for s in stocks:
                code = str(s.get("itemCode", "")).zfill(6)
                if not code or code == "000000":
                    continue
                pct = _num(s.get("fluctuationsRatio"))
                rows.append({
                    "종목코드": code,
                    "종목명": s.get("stockName", ""),
                    "등락률": float(pct) if pct is not None else 0.0,
                    "현재가": _num(s.get("closePrice")) or 0,
                })
                got += 1
            if got >= per_market or len(stocks) < 100:
                break
    if not rows:
        return pd.DataFrame()
    return pd.DataFrame(rows).drop_duplicates(subset=["종목코드"]).reset_index(drop=True)


def _kr_change_map():
    """{종목명: 오늘 등락률(%)} — 네이버 모바일 API(클라우드 호환) 우선, fdr 폴백."""
    df = get_kr_universe_naver()
    if df is None or df.empty:
        try:
            df = get_stock_list_by_market()
        except Exception:
            df = None
    if df is None or df.empty or "종목명" not in df.columns or "등락률" not in df.columns:
        return {}
    m = {}
    for nm, rt in zip(df["종목명"], df["등락률"]):
        try:
            m[str(nm).strip()] = float(rt)
        except Exception:
            continue
    return m


@st.cache_data(ttl=1800, show_spinner=False)
def get_trending_sectors(market="US"):
    """테마별 대표 종목 평균 등락률(강세 순). market: 'US'(yfinance) | 'KR'(네이버 모바일 API)."""
    if market == "KR":
        chg = _kr_change_map()
        if not chg:
            return []
        theme_map = KR_THEME_MAP
    else:
        import yfinance as yf
        uniq = sorted({t for lst in US_THEME_MAP.values() for t in lst})
        try:
            data = yf.download(uniq, period="5d", interval="1d",
                               group_by="ticker", threads=True, progress=False)
        except Exception:
            return []
        if data is None or len(data) == 0:
            return []
        multi = isinstance(data.columns, pd.MultiIndex)
        chg = {}
        for tk in uniq:
            try:
                d = data[tk] if multi else data
                c = d["Close"].dropna()
                if len(c) >= 2:
                    chg[tk] = (float(c.iloc[-1]) / float(c.iloc[-2]) - 1) * 100
            except Exception:
                continue
        theme_map = US_THEME_MAP

    out = []
    for theme, tickers in theme_map.items():
        members = [(t, chg[t]) for t in tickers if t in chg]
        if not members:
            continue
        members.sort(key=lambda x: x[1], reverse=True)
        avg = sum(p for _, p in members) / len(members)
        out.append({"theme": theme, "avg": avg, "members": members, "n": len(members)})
    out.sort(key=lambda x: x["avg"], reverse=True)
    return out


def render_trending_sectors(sectors, limit=None):
    if not sectors:
        st.info("섹터 데이터를 일시적으로 불러오지 못했어요.")
        return
    data = sectors[:limit] if limit else sectors

    def _chip(tk, pct):
        cc = "#ef4444" if pct > 0 else ("#3b82f6" if pct < 0 else "#64748b")
        return ("<span style='background:#f8fafc;border:1px solid #eef2f7;border-radius:8px;"
                "padding:3px 9px;font-size:12px;white-space:nowrap;'>"
                f"<b style='color:#334155;'>{tk}</b> "
                f"<span style='color:{cc};font-weight:600;'>{pct:+.2f}%</span></span>")

    rows = []
    for s in data:
        avg = s["avg"]
        c = "#ef4444" if avg > 0 else ("#3b82f6" if avg < 0 else "#64748b")
        top3 = s["members"][:3]
        more = s["n"] - len(top3)
        chips = "".join(_chip(t, p) for t, p in top3)
        more_chip = ("<span style='background:#f1f5f9;border-radius:8px;padding:3px 9px;"
                     f"font-size:12px;color:#94a3b8;align-self:center;'>+{more}</span>") if more > 0 else ""
        rows.append(
            "<div style='padding:11px 0;border-bottom:1px solid #f1f5f9;'>"
            "<div style='display:flex;justify-content:space-between;align-items:center;margin-bottom:7px;gap:8px;'>"
            f"<span style='font-weight:700;color:#1e293b;font-size:14px;'>{s['theme']}</span>"
            f"<span style='font-weight:700;color:{c};font-size:14px;white-space:nowrap;'>{avg:+.2f}%</span></div>"
            f"<div style='display:flex;flex-wrap:wrap;gap:6px;'>{chips}{more_chip}</div></div>"
        )
    st.markdown(
        "<div style='background:#fff;border:1px solid #e9eef3;border-radius:14px;padding:4px 16px;'>"
        + "".join(rows) + "</div>", unsafe_allow_html=True)


# =====================================================================
# [신규] 국장 수급 분석 (외국인·기관·개인 순매수) — 네이버 기반 (클라우드 호환)
#   순매수/순매도 TOP · 개미 vs 스마트머니 · 수급 주체 손바뀜(전환)
#   거래대금 상위 종목을 네이버(frgn.naver)에서 스캔 → 외국인·기관 순매매량×종가 → 억 환산
#   개인 ≈ -(외국인+기관). pykrx/KRX 불필요 → 클라우드에서도 동작.
# =====================================================================
def _fetch_stock_investor_2d(code):
    """frgn.naver → 오늘/어제 외국인·기관 순매매량 + 오늘 종가. 실패 시 None."""
    try:
        res = requests.get(f"https://finance.naver.com/item/frgn.naver?code={code}",
                           headers={"User-Agent": "Mozilla/5.0"}, timeout=5)
        soup = BeautifulSoup(res.text, "html.parser")
        tables = soup.select("table.type2")
        if len(tables) < 2:
            return None
        recs = []
        for row in tables[1].select("tr"):
            tds = row.select("td")
            if len(tds) < 9 or not tds[0].get_text(strip=True):
                continue

            def _n(i):
                t = tds[i].get_text(strip=True).replace(",", "").replace("+", "")
                if not t or t == "-":
                    return 0
                try:
                    return int(float(t))
                except Exception:
                    return 0
            recs.append({"close": _n(1), "inst": _n(5), "forn": _n(6)})
            if len(recs) >= 2:
                break
        if not recs:
            return None
        t0 = recs[0]
        t1 = recs[1] if len(recs) >= 2 else {"inst": 0, "forn": 0}
        return {"price": t0["close"], "inst": t0["inst"], "forn": t0["forn"],
                "inst_prev": t1["inst"], "forn_prev": t1["forn"]}
    except Exception:
        return None


@st.cache_data(ttl=1800, show_spinner=False)
def get_kr_investor_flows(universe_n=150):
    """시총 상위 종목의 외국인/기관/개인 순매수(억) + 전일 스마트머니 부호. 네이버 기반."""
    base = get_kr_universe_naver()
    if base is None or base.empty:
        try:
            b2 = get_stock_list_by_market()
            if b2 is not None and not b2.empty and "거래대금(억)" in b2.columns:
                base = b2[b2["시장"].isin(["코스피", "코스닥"])].sort_values("거래대금(억)", ascending=False)
        except Exception:
            base = None
    if base is None or base.empty or "종목코드" not in base.columns:
        return pd.DataFrame()
    base = base.head(universe_n)
    chg_map = {}
    if "등락률" in base.columns:
        for c, rt in zip(base["종목코드"], base["등락률"]):
            try:
                chg_map[str(c).zfill(6)] = float(rt)
            except Exception:
                pass
    targets = [(str(c).zfill(6), str(n)) for c, n in zip(base["종목코드"], base["종목명"])]

    def _work(item):
        code, name = item
        d = _fetch_stock_investor_2d(code)
        if not d:
            return None
        price = d["price"] or 0
        forn = d["forn"] * price / 1e8
        inst = d["inst"] * price / 1e8
        return {"티커": code, "종목명": name, "등락률": chg_map.get(code, float("nan")),
                "외국인": forn, "기관": inst, "개인": -(forn + inst),
                "스마트머니": forn + inst,
                "스마트머니_전일": float(d["forn_prev"] + d["inst_prev"])}

    rows = []
    import concurrent.futures as _cf
    try:
        with _cf.ThreadPoolExecutor(max_workers=12) as ex:
            for r in ex.map(_work, targets):
                if r:
                    rows.append(r)
    except Exception:
        for it in targets:
            r = _work(it)
            if r:
                rows.append(r)
    return pd.DataFrame(rows) if rows else pd.DataFrame()


def _su_amt(v):
    return f"{v:+,.0f}억"


def _render_netbuy_list(df, col, ascending=False, n=10):
    if df is None or df.empty or col not in df.columns:
        st.info("데이터 없음"); return
    d = df[df[col] != 0].sort_values(col, ascending=ascending).head(n).reset_index(drop=True)
    if d.empty:
        st.info("해당 데이터 없음"); return
    rows = []
    for i, r in d.iterrows():
        amt = r[col]; ac = "#ef4444" if amt > 0 else "#3b82f6"
        chg = r.get("등락률", float("nan"))
        if pd.isna(chg):
            chg_html = "<span style='width:64px;'></span>"
        else:
            cc = "#ef4444" if chg > 0 else ("#3b82f6" if chg < 0 else "#64748b")
            ar = "▲" if chg > 0 else ("▼" if chg < 0 else "")
            chg_html = f"<span style='width:64px;text-align:right;color:{cc};font-size:12px;font-weight:600;'>{ar}{abs(chg):.2f}%</span>"
        rows.append(
            "<div style='display:flex;align-items:center;gap:8px;padding:7px 0;border-bottom:1px solid #f1f5f9;'>"
            f"<span style='width:18px;color:#94a3b8;font-weight:700;font-size:12px;'>{i+1}</span>"
            f"<span style='flex:1;min-width:0;font-weight:700;color:#1e293b;font-size:13px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;'>{r['종목명']}</span>"
            + chg_html +
            f"<span style='width:92px;text-align:right;color:{ac};font-weight:700;font-size:13px;'>{_su_amt(amt)}</span></div>"
        )
    st.markdown("<div style='background:#fff;border:1px solid #e9eef3;border-radius:12px;padding:2px 14px;'>"
                + "".join(rows) + "</div>", unsafe_allow_html=True)


def _render_flow_chips(df, n=10, sort_col="스마트머니", ascending=False):
    """개미 vs 스마트머니 등에서 한 줄 = 종목 + (외/기/개) 3주체 금액."""
    if df is None or df.empty:
        st.info("해당 조건의 종목이 없습니다."); return
    d = df.sort_values(sort_col, ascending=ascending).head(n).reset_index(drop=True)
    if d.empty:
        st.info("해당 조건의 종목이 없습니다."); return
    def amt_span(label, v):
        c = "#ef4444" if v > 0 else ("#3b82f6" if v < 0 else "#64748b")
        return (f"<span style='font-size:11px;color:#94a3b8;'>{label}</span> "
                f"<span style='font-size:12px;color:{c};font-weight:600;'>{v:+,.0f}</span>")
    rows = []
    for i, r in d.iterrows():
        rows.append(
            "<div style='padding:8px 0;border-bottom:1px solid #f1f5f9;'>"
            "<div style='display:flex;justify-content:space-between;align-items:center;'>"
            f"<span style='font-weight:700;color:#1e293b;font-size:13px;'>{i+1}. {r['종목명']}</span></div>"
            "<div style='display:flex;gap:14px;margin-top:3px;'>"
            f"{amt_span('외국인', r['외국인'])} {amt_span('기관', r['기관'])} {amt_span('개인', r['개인'])}"
            "</div></div>"
        )
    st.markdown("<div style='background:#fff;border:1px solid #e9eef3;border-radius:12px;padding:2px 14px;'>"
                + "".join(rows) + "</div>", unsafe_allow_html=True)


def _render_handover(df, n=15):
    """스마트머니(외인+기관) 기준 어제 순매도 → 오늘 순매수 전환(바닥 신호)."""
    if df is None or df.empty or "스마트머니_전일" not in df.columns:
        st.info("전일 데이터가 없어 손바뀜을 계산할 수 없어요."); return
    cand = df[(df["스마트머니_전일"] < 0) & (df["스마트머니"] > 0)].sort_values(
        "스마트머니", ascending=False).head(n).reset_index(drop=True)
    if cand.empty:
        st.info("오늘 '순매도 → 순매수' 전환 종목이 없습니다."); return
    rows = []
    for i, r in cand.iterrows():
        ts = float(r["스마트머니"])
        rows.append(
            "<div style='display:flex;align-items:center;gap:8px;padding:8px 0;border-bottom:1px solid #f1f5f9;'>"
            f"<span style='width:18px;color:#94a3b8;font-weight:700;font-size:12px;'>{i+1}</span>"
            f"<span style='flex:1;font-weight:700;color:#1e293b;font-size:13px;'>{r['종목명']}</span>"
            "<span style='font-size:12px;color:#94a3b8;'>전일 <span style='color:#3b82f6;'>순매도</span> → "
            f"오늘 <span style='color:#ef4444;font-weight:700;'>{ts:+,.0f}억</span></span>"
            "<span style='margin-left:8px;background:#fee2e2;color:#dc2626;border-radius:10px;padding:2px 9px;font-size:11px;font-weight:700;'>전환</span></div>"
        )
    st.markdown("<div style='background:#fff;border:1px solid #e9eef3;border-radius:12px;padding:2px 14px;'>"
                + "".join(rows) + "</div>", unsafe_allow_html=True)


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


# =====================================================================
# [신규] 미장(US) 거래량 급증/급감 — 주요 대형주 유니버스 기준
#   '오늘 거래량 ÷ 최근 20일 평균 거래량' 배율로 산출 (>1 급증 / <1 급감)
# =====================================================================
US_VOL_UNIVERSE = [
    ("Apple","AAPL"),("Microsoft","MSFT"),("Nvidia","NVDA"),("Amazon","AMZN"),("Alphabet","GOOGL"),
    ("Meta","META"),("Tesla","TSLA"),("Broadcom","AVGO"),("AMD","AMD"),("Netflix","NFLX"),
    ("Berkshire","BRK-B"),("JPMorgan","JPM"),("Visa","V"),("Mastercard","MA"),("UnitedHealth","UNH"),
    ("Eli Lilly","LLY"),("Johnson & Johnson","JNJ"),("Exxon","XOM"),("Chevron","CVX"),("Walmart","WMT"),
    ("Costco","COST"),("Home Depot","HD"),("Procter & Gamble","PG"),("Coca-Cola","KO"),("PepsiCo","PEP"),
    ("Adobe","ADBE"),("Salesforce","CRM"),("Oracle","ORCL"),("Cisco","CSCO"),("Intel","INTC"),
    ("Qualcomm","QCOM"),("Texas Instruments","TXN"),("Micron","MU"),("Applied Materials","AMAT"),("Lam Research","LRCX"),
    ("ASML","ASML"),("ARM","ARM"),("Palantir","PLTR"),("Super Micro","SMCI"),("Arista","ANET"),
    ("ServiceNow","NOW"),("Uber","UBER"),("Airbnb","ABNB"),("PayPal","PYPL"),("Block","SQ"),
    ("Shopify","SHOP"),("Snowflake","SNOW"),("CrowdStrike","CRWD"),("Datadog","DDOG"),("Zscaler","ZS"),
    ("Disney","DIS"),("Comcast","CMCSA"),("Verizon","VZ"),("AT&T","T"),("T-Mobile","TMUS"),
    ("Boeing","BA"),("Caterpillar","CAT"),("Deere","DE"),("GE Aerospace","GE"),("Honeywell","HON"),
    ("Lockheed","LMT"),("RTX","RTX"),("Ford","F"),("General Motors","GM"),("Rivian","RIVN"),
    ("Lucid","LCID"),("Marvell","MRVL"),("Coinbase","COIN"),("MicroStrategy","MSTR"),("Robinhood","HOOD"),
    ("SoFi","SOFI"),("Bank of America","BAC"),("Wells Fargo","WFC"),("Goldman Sachs","GS"),("Morgan Stanley","MS"),
    ("Citigroup","C"),("Pfizer","PFE"),("Merck","MRK"),("AbbVie","ABBV"),("Moderna","MRNA"),
    ("Gilead","GILD"),("Amgen","AMGN"),("Starbucks","SBUX"),("McDonald's","MCD"),("Nike","NKE"),
    ("GE Vernova","GEV"),("Vistra","VST"),("Constellation Energy","CEG"),("First Solar","FSLR"),("Enphase","ENPH"),
    ("Plug Power","PLUG"),("Cleveland-Cliffs","CLF"),("Freeport","FCX"),("Occidental","OXY"),("ConocoPhillips","COP"),
    ("Devon","DVN"),("Halliburton","HAL"),("Schlumberger","SLB"),("Micron2","MU"),("Intel2","INTC"),
]

@st.cache_data(ttl=1800)
def get_us_volume_surge_drop(top_n=20):
    import yfinance as yf
    seen, targets = set(), []
    for nm, tk in US_VOL_UNIVERSE:
        if tk not in seen:
            seen.add(tk); targets.append((nm, tk))
    tickers = [t[1] for t in targets]
    name_map = {t[1]: t[0] for t in targets}
    try:
        data = yf.download(tickers, period="2mo", interval="1d",
                           group_by="ticker", threads=True, progress=False)
    except Exception:
        return pd.DataFrame(), pd.DataFrame()
    if data is None or len(data) == 0:
        return pd.DataFrame(), pd.DataFrame()
    multi = isinstance(data.columns, pd.MultiIndex)
    rows = []
    for tk in tickers:
        try:
            d = data[tk] if multi else data
            vol = d["Volume"].dropna(); close = d["Close"].dropna()
            if len(vol) < 7 or len(close) < 2:
                continue
            today_v = float(vol.iloc[-1])
            base = vol.iloc[-21:-1] if len(vol) >= 21 else vol.iloc[:-1]
            avg_v = float(base.mean())
            if avg_v <= 0 or today_v <= 0:
                continue
            rows.append({
                "종목": f"{name_map.get(tk, tk)} ({tk})",
                "현재가": float(close.iloc[-1]),
                "등락률": (float(close.iloc[-1]) / float(close.iloc[-2]) - 1) * 100,
                "거래량 배율": today_v / avg_v,
            })
        except Exception:
            continue
    if not rows:
        return pd.DataFrame(), pd.DataFrame()
    alldf = pd.DataFrame(rows)
    surge = alldf.sort_values("거래량 배율", ascending=False).head(top_n).reset_index(drop=True)
    drop_ = alldf.sort_values("거래량 배율", ascending=True).head(top_n).reset_index(drop=True)
    for x in (surge, drop_):
        x.index = x.index + 1; x.index.name = "순위"
    return surge, drop_


def style_us_volume_table(df, kind="surge"):
    if df is None or df.empty:
        return None
    def color_updown(v):
        if pd.isna(v): return ''
        if v > 0: return 'color:#e74c3c;font-weight:700;'
        if v < 0: return 'color:#2e86de;font-weight:700;'
        return 'color:gray;'
    sty = df.style.format({"현재가": "${:,.2f}", "등락률": "{:+.2f}%", "거래량 배율": "{:.1f}×"})
    try:
        sty = sty.map(color_updown, subset=["등락률"])
    except Exception:
        pass
    bar_color = '#ffd8a8' if kind == "surge" else '#a5d8ff'
    try:
        sty = sty.bar(subset=["거래량 배율"], color=bar_color, vmin=0)
    except Exception:
        pass
    sty = sty.set_properties(**{'font-size': '14px', 'text-align': 'center'})
    try:
        sty = sty.set_properties(subset=['종목'], **{'text-align': 'left', 'font-weight': '600'})
    except Exception:
        pass
    return sty


def render_main_volume_top10():
    """메인(대시보드)용 — 국장 거래량 급증/급감 TOP10 요약 + 경보탭 안내."""
    with st.spinner("거래량 급증/급감 데이터 수집 중..."):
        s_df, d_df = get_volume_surge_drop()
    st.caption("🇰🇷 국장 기준 · 🔴빨강=상승 / 🔵파랑=하락 · 막대가 길수록 거래량이 더 터진 종목")
    cc1, cc2 = st.columns(2)
    with cc1:
        st.markdown("**🔥 거래량 급증 TOP10**")
        sty, _ = style_volume_table(s_df.head(10), "surge")
        if sty is not None:
            st.dataframe(sty, use_container_width=True, height=388)
        elif not s_df.empty:
            st.dataframe(s_df.head(10), use_container_width=True, hide_index=True)
        else:
            st.caption("데이터를 일시적으로 불러오지 못했어요.")
    with cc2:
        st.markdown("**❄️ 거래량 급감 TOP10**")
        sty2, _ = style_volume_table(d_df.head(10), "drop")
        if sty2 is not None:
            st.dataframe(sty2, use_container_width=True, height=388)
        elif not d_df.empty:
            st.dataframe(d_df.head(10), use_container_width=True, hide_index=True)
        else:
            st.caption("데이터를 일시적으로 불러오지 못했어요.")
    st.info("📊 **TOP20 전체 · 🇺🇸 미장(US) 거래량 · 관리종목/시장경보**는 좌측 메뉴 "
            "**‘🚦 거래량 급증 & 시장 경보’** 탭에서 확인하세요.")


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


def _market_flows_html(card, title):
    """한 시장(코스피/코스닥)의 투자자별 순매매 3줄 블록(외국인/기관/개인)."""
    f_v = card.get("forgn") if card else None
    i_v = card.get("inst") if card else None
    p_v = card.get("indiv") if card else None
    bars = (
        _flow_bar_html("외국인", f_v)
        + _flow_bar_html("기관", i_v)
        + _flow_bar_html("개인", p_v)
    )
    return (
        f'<div style="font-weight:800;font-size:14px;color:#334155;margin:4px 0 2px;">{title}</div>'
        f'{bars}'
    )


# =====================================================================
# [신규] '눌러서 펼치는' 내용을 팝업 창(st.dialog)으로 보여주는 공용 헬퍼
#   _popup_button(label, name, title, key): expander 대체 버튼 → 누르면 모달 팝업.
#   내용은 _register_popup(name, fn)으로 등록된 렌더 함수가 그림. (구버전은 인라인 폴백)
# =====================================================================
_POPUP_RENDERERS = {}

def _register_popup(name, fn):
    _POPUP_RENDERERS[name] = fn

def _run_popup_renderer():
    _name = st.session_state.get("_popup_name")
    _title = st.session_state.get("_popup_title")
    if _title:
        st.markdown(f"#### {_title}")
    _fn = _POPUP_RENDERERS.get(_name)
    if _fn:
        try:
            _fn()
        except Exception as _e:
            st.error(f"표시 중 오류가 발생했어요: {_e}")
    else:
        st.info("표시할 내용을 불러오지 못했어요. 창을 닫고 다시 시도해 주세요.")

if hasattr(st, "dialog"):
    try:
        @st.dialog("　", width="large")
        def _universal_popup():
            _run_popup_renderer()
    except TypeError:
        @st.dialog("　")
        def _universal_popup():
            _run_popup_renderer()

def _open_popup(name, title):
    st.session_state["_popup_name"] = name
    st.session_state["_popup_title"] = title
    if hasattr(st, "dialog"):
        _universal_popup()
    else:
        st.session_state["_popup_inline_open"] = True

def _popup_button(label, name, title, key=None, use_container_width=True):
    if st.button(label, key=key, use_container_width=use_container_width):
        _open_popup(name, title)
    if (not hasattr(st, "dialog")) and st.session_state.get("_popup_inline_open") and st.session_state.get("_popup_name") == name:
        with st.container(border=True):
            _run_popup_renderer()


def render_main_index_panel():
    """[추가] 메인페이지 상단 — 네이버 모바일 스타일 코스피/코스닥 + 오늘의 시장 + 투자자별 순매매."""
    data = get_kr_index_panel()
    if not data:
        st.warning("📊 지수 패널을 일시적으로 불러오지 못했습니다 (네이버 응답 지연). 잠시 후 다시 시도해 주세요.")
        if st.button("🔄 다시 시도", key="retry_index_panel"):
            get_kr_index_panel.clear()
            st.rerun()
        def _prc_diag_index():
            _diag_index_endpoints()
        _register_popup("diag_index", _prc_diag_index)
        _popup_button("🔧 진단: 어떤 응답이 오는지 확인", "diag_index", "🔧 진단: 인덱스 응답 확인", key="btn_diag_index")
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

    # 투자자별 순매매: 코스피 + 코스닥 각각 표시
    def _has_flow(c):
        return bool(c) and any(
            c.get(k) is not None for k in ("forgn", "inst", "indiv")
        )

    flows = ""
    if _has_flow(kospi):
        flows += _market_flows_html(kospi, "📈 코스피")
    if _has_flow(kosdaq):
        if flows:
            flows += '<div style="height:1px;background:#fcdcdc;margin:12px 0;"></div>'
        flows += _market_flows_html(kosdaq, "📊 코스닥")

    # [폴백] 둘 다 수급값이 없으면 가용한 쪽이라도 한 블록 표시
    if not flows:
        src = kospi if kospi else kosdaq
        title = "📈 코스피" if kospi else "📊 코스닥"
        flows = _market_flows_html(src, title)

    st.markdown(
        f"""
        <div style="background:#fff;border:1px solid #e9eef3;border-radius:16px;
                    padding:6px 18px 14px;box-shadow:0 1px 3px rgba(0,0,0,0.04);">
          {cards}
        </div>
        <div style="background:#fff5f5;border:1px solid #fcdcdc;border-radius:16px;
                    padding:14px 18px;margin-top:10px;">
          <div style="font-weight:800;font-size:14px;color:#b91c1c;margin-bottom:8px;">💰 투자자별 순매매 (수급)</div>
          <div>{flows}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    st.caption("💡 외국인·기관·개인 순매매(억원)는 코스피·코스닥 각 시장 전체 기준 · 빨강=순매수 / 파랑=순매도. 장중 잠정치이며 마감 후 거래소가 확정합니다.")

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
        f'padding:2px 14px;box-sizing:border-box;overflow:hidden;">{body}</div>',
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

@st.cache_data(ttl=600)
def get_institution_buy_trend(code):
    """기관(전체) 최근 5거래일 순매수 합계 & 연속 순매수 일수 — 네이버 모바일 trend API.
    (기존 frgn HTML 스크래핑은 캐시도 없고 종목마다 순차 호출돼 느렸음 → JSON API + 캐시로 교체)
    ※ '연기금'이 아니라 '기관 전체(organ)' 기준이다. 반환: (기관5일합:주, 연속순매수일수)"""
    if not str(code).isdigit():
        return 0, 0
    try:
        url = f"https://m.stock.naver.com/api/stock/{code}/trend"
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            "Referer": f"https://m.stock.naver.com/domestic/stock/{code}/total",
            "Accept": "application/json",
        }
        res = requests.get(url, headers=headers, timeout=5)
        if res.status_code != 200:
            return 0, 0
        rows = res.json()
        if isinstance(rows, dict):
            for k in ("trends", "result", "list", "data"):
                if isinstance(rows.get(k), list):
                    rows = rows[k]; break
        if not isinstance(rows, list):
            return 0, 0

        def _num(v):
            if v is None: return None
            s = str(v).replace(',', '').replace('+', '').strip()
            return int(s) if s.lstrip('-').isdigit() else None

        inst_sum, streak, broke, count = 0, 0, False, 0
        for row in rows:
            i_val = _num(row.get("organPureBuyQuant"))
            if i_val is None:
                continue
            inst_sum += i_val
            if i_val > 0 and not broke:
                streak += 1
            elif i_val <= 0:
                broke = True
            count += 1
            if count >= 5:
                break
        return inst_sum, streak
    except Exception:
        return 0, 0


# 하위 호환 별칭 — 기존 호출부(get_pension_fund_trend)를 그대로 유지하기 위함.
# 실제로는 '연기금'이 아니라 '기관 전체' 추세이며, 명칭은 점진적으로 정리한다.
get_pension_fund_trend = get_institution_buy_trend

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

# ── [NEW] AI 적정주가 (PER·PBR 멀티팩터 밸류에이션) ──────────────────────
@st.cache_data(ttl=3600)
def get_sector_per(ticker_code):
    """네이버 증권 메인 페이지에서 '동일업종 PER'을 긁어온다. (국내 전용, 1시간 캐시)"""
    if not str(ticker_code).isdigit():
        return None
    try:
        url = f"https://finance.naver.com/item/main.naver?code={ticker_code}"
        res = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=5)
        soup = BeautifulSoup(res.text, 'html.parser')
        for th in soup.find_all('th'):
            if '동일업종 PER' in th.get_text():
                td = th.find_next('td')
                if td:
                    m = re.search(r'([\d,]+\.?\d*)', td.get_text(strip=True).replace(',', ''))
                    if m:
                        v = float(m.group(1))
                        if 0 < v < 500:
                            return v
        return None
    except Exception:
        return None

def calc_ai_target_price(per, pbr, current_price, ticker_code, use_sector_per=True):
    """PER·PBR 역산(EPS·BPS·ROE)으로 AI 적정주가를 산출.
    ① 그레이엄 공식: √(22.5 × EPS × BPS)
    ② S-RIM(잔여이익모델 약식): BPS × (ROE ÷ 요구수익률 8%)
    ③ 업종 상대가치(국내): EPS × 동일업종 PER  ※ use_sector_per=True일 때만 (HTTP 1회 발생)
    → 산출 가능한 방법들의 평균값을 반환. 실패 시 (None, 사유) 반환.
    ⚡ 스캐너 등 대량 호출 경로에서는 use_sector_per=False로 호출해 네트워크 부하를 0으로 유지."""
    try:
        curr = float(current_price)
        if curr <= 0:
            return None, "현재가 오류"
        per_v = float(str(per).replace(',', ''))
        pbr_v = float(str(pbr).replace(',', ''))
        if per_v <= 0:
            return None, "적자 기업 (PER 음수/없음)"
        if pbr_v <= 0:
            return None, "PBR 데이터 없음"

        eps = curr / per_v          # 주당순이익 역산
        bps = curr / pbr_v          # 주당순자산 역산
        roe = (eps / bps) * 100.0   # ROE(%) = PBR/PER × 100

        methods = []
        details = []

        # ① 그레이엄 공식
        graham = (22.5 * eps * bps) ** 0.5
        methods.append(graham)
        details.append(f"그레이엄 {graham:,.0f}")

        # ② S-RIM 약식 (요구수익률 8%, ROE 40% 초과 시 과대평가 방지 캡)
        roe_capped = min(roe, 40.0)
        srim = bps * (roe_capped / 8.0)
        methods.append(srim)
        details.append(f"S-RIM {srim:,.0f}")

        # ③ 업종 PER 상대가치 (국내 종목만 · 상세 카드에서만 조회해 스캔 부하 방지)
        sec_per = get_sector_per(ticker_code) if use_sector_per else None
        if sec_per:
            rel = eps * sec_per
            methods.append(rel)
            details.append(f"업종PER {rel:,.0f}")

        ai_target = sum(methods) / len(methods)
        # 극단값 방어: 현재가 대비 ±70% 범위로 클리핑
        ai_target = max(curr * 0.3, min(ai_target, curr * 1.7))

        detail_str = f"EPS {eps:,.0f} · BPS {bps:,.0f} · ROE {roe:.1f}%" + (f" · 업종PER {sec_per:.1f}배" if sec_per else "")
        return ai_target, detail_str
    except Exception:
        return None, "산출 불가"

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
# [신규] 매물대 지도 (Volume-by-Price) + 종목 타임머신 (과거 유사패턴)
#  - 둘 다 일봉 OHLCV(get_historical_data 결과)만으로 계산. 틱 데이터 불필요.
#  - 카드에서 토글로 '열 때만' 계산 → 평소 렌더 속도에 영향 없음.
# =====================================================================
def nb_volume_profile(df, bins=12, current_price=None):
    """일봉 거래량을 그날 [Low, High] 범위에 겹치는 만큼 비례 배분해 가격대별로 합산."""
    try:
        d = df[['High', 'Low', 'Volume']].dropna().copy()
    except Exception:
        return None
    if d.empty:
        return None
    lo = float(d['Low'].min()); hi = float(d['High'].max())
    if hi <= lo:
        hi = lo * 1.001 + 1e-9
    edges = np.linspace(lo, hi, bins + 1)
    vol = np.zeros(bins)
    H = d['High'].to_numpy(float); L = d['Low'].to_numpy(float); V = d['Volume'].to_numpy(float)
    for h, l, v in zip(H, L, V):
        if v <= 0 or h < l:
            continue
        if h - l <= 0:
            idx = min(bins - 1, max(0, int(np.searchsorted(edges, l, "right") - 1)))
            vol[idx] += v; continue
        lows = np.maximum(edges[:-1], l); highs = np.minimum(edges[1:], h)
        overlap = np.clip(highs - lows, 0, None); tot = overlap.sum()
        if tot > 0:
            vol += v * (overlap / tot)
    total = vol.sum()
    pct = (vol / total * 100) if total > 0 else vol
    centers = (edges[:-1] + edges[1:]) / 2
    order = list(range(bins))[::-1]   # 위(고가) → 아래(저가)
    levels = [{"price_low": float(edges[i]), "price_high": float(edges[i + 1]),
               "price_mid": float(centers[i]), "pct": float(pct[i])} for i in order]
    poc_bin = int(np.argmax(vol)); poc_index = order.index(poc_bin)
    if current_price is None and "Close" in df.columns:
        try: current_price = float(df["Close"].dropna().iloc[-1])
        except Exception: current_price = None
    current_index = None
    if current_price is not None:
        cb = min(bins - 1, max(0, int(np.searchsorted(edges, current_price, "right") - 1)))
        current_index = order.index(cb)
    return {"levels": levels, "poc_index": poc_index, "current_index": current_index}


def nb_time_machine(close, dates=None, window=20, horizons=(5, 20), top_k=10, min_gap=5):
    """지금의 최근 window일 '모양'과 닮은 과거 구간을 상관계수로 찾아 이후 수익률 집계."""
    c = np.asarray(close, dtype=float)
    mask = ~np.isnan(c); c = c[mask]
    if dates is not None:
        dates = np.asarray(dates)[mask]
    n = len(c); Hmax = max(horizons)
    if n < window + Hmax + 30:
        return None
    cur = c[-window:]
    if np.any(cur <= 0):
        return None
    cur_z = cur / cur[0]; cur_z = cur_z - cur_z.mean()
    cur_norm = np.sqrt((cur_z ** 2).sum())
    if cur_norm == 0:
        return None
    cand_min = window - 1; cand_max = n - 1 - Hmax; exclude_from = n - window - min_gap
    results = []
    for t in range(cand_min, cand_max + 1):
        if t >= exclude_from:
            continue
        w = c[t - window + 1: t + 1]
        if np.any(w <= 0):
            continue
        wz = w / w[0]; wz = wz - wz.mean()
        denom = cur_norm * np.sqrt((wz ** 2).sum())
        if denom == 0:
            continue
        corr = float((cur_z * wz).sum() / denom)
        sim = (corr + 1) / 2 * 100
        end_price = c[t]
        fwd = {h: (c[t + h] / end_price - 1) * 100 for h in horizons}
        item = {"end_index": int(t), "similarity": sim, "forward": fwd}
        if dates is not None:
            item["end_date"] = dates[t]
        results.append(item)
    if not results:
        return None
    results.sort(key=lambda r: r["similarity"], reverse=True)
    top = results[:top_k]
    agg = {}
    for h in horizons:
        vals = [r["forward"][h] for r in top]
        agg[h] = {"avg": float(np.mean(vals)),
                  "up": int(sum(v > 0 for v in vals)),
                  "down": int(sum(v <= 0 for v in vals))}
    return {"matches": top, "aggregate": agg, "window": window,
            "horizons": list(horizons), "n_candidates": len(results)}


def _nb_won(v):
    """가격 표기: 국내는 원, 미국(소수)도 자연스럽게."""
    try:
        v = float(v)
    except Exception:
        return str(v)
    if v >= 1000:
        return f"₩{v:,.0f}" if v == int(v) or v > 5000 else f"₩{v:,.0f}"
    return f"${v:,.2f}"


def nb_render_volume_profile(df, current_price=None, bins=12):
    """매물대 지도 렌더 (인라인 스타일 HTML 막대)."""
    vp = nb_volume_profile(df.tail(120), bins=bins, current_price=current_price)
    if not vp:
        st.info("매물대를 계산할 일봉 데이터가 부족해요."); return
    levels = vp["levels"]
    mx = max((l["pct"] for l in levels), default=0) or 1
    st.markdown("#### 🏛️ 매물대 지도 &nbsp;<span style='color:#94a3b8;font-size:0.78em;font-weight:400;'>일봉 근사 · 최근 120일</span>",
                unsafe_allow_html=True)
    rows = []
    for i, lv in enumerate(levels):
        w = lv["pct"] / mx * 100
        is_poc = (i == vp["poc_index"]); is_now = (i == vp["current_index"])
        bar = "#c79a3a" if is_poc else ("#64748b" if is_now else "#cbd5e1")
        price_style = "font-weight:700;color:#0f172a;" if is_now else "color:#334155;"
        tag = "<span style='background:#0f172a;color:#fff;border-radius:10px;padding:1px 7px;font-size:0.72em;margin-left:5px;'>현재</span>" if is_now else ""
        rows.append(
            "<div style=\"display:flex;align-items:center;gap:8px;margin:3px 0;font-size:0.86rem;\">"
            "<span style=\"width:96px;text-align:right;font-variant-numeric:tabular-nums;" + price_style + "\">"
            + _nb_won(lv["price_mid"]) + tag + "</span>"
            "<span style=\"flex:1;background:#eef2f6;border-radius:6px;height:17px;overflow:hidden;\">"
            "<span style=\"display:block;width:" + f"{w:.1f}" + "%;height:100%;background:" + bar + ";border-radius:6px;\"></span></span>"
            "<span style=\"width:50px;text-align:right;color:#475569;font-variant-numeric:tabular-nums;\">"
            + f"{lv['pct']:.1f}" + "%</span></div>"
        )
    st.markdown("".join(rows), unsafe_allow_html=True)

    # 자동 인사이트 (POC = 가장 두꺼운 매물대가 지지냐 저항이냐)
    poc = levels[vp["poc_index"]]
    msg = f"가장 두꺼운 매물대는 **{_nb_won(poc['price_low'])}~{_nb_won(poc['price_high'])}** 구간(전체의 {poc['pct']:.1f}%)이에요. "
    if current_price is not None:
        if poc["price_mid"] < float(current_price):
            msg += "현재가보다 **아래**라 눌릴 때 **받침(지지)** 역할을 할 가능성이 커요."
        else:
            msg += "현재가보다 **위**라 오를 때 **매물벽(저항)** 으로 작용할 수 있어요."
        ci = vp["current_index"]
        if ci is not None and ci - 1 >= 0:
            up = levels[ci - 1]
            if up["pct"] >= 3:
                msg += f" 바로 위 {_nb_won(up['price_low'])}~{_nb_won(up['price_high'])}({up['pct']:.1f}%)이 1차 저항이에요."
    with st.container(border=True):
        st.markdown(msg)
    st.caption("일봉 고가~저가에 거래량을 나눠 담은 근사치예요 (틱 데이터 아님) · 구조 참고용이며 매수·매도 권유가 아닙니다.")


def nb_render_time_machine(df, window=20, horizons=(5, 20), top_k=10):
    """종목 타임머신 렌더."""
    try:
        close = df["Close"].to_numpy(float); dates = df.index.values
    except Exception:
        st.info("타임머신을 계산할 데이터가 부족해요."); return
    tm = nb_time_machine(close, dates=dates, window=window, horizons=horizons, top_k=top_k)
    if not tm:
        st.info(f"타임머신은 최소 {window + max(horizons) + 30}거래일 이상이 필요해요. 상장 기간이 짧은 종목은 표시되지 않아요.")
        return
    h0, h1 = tm["horizons"][0], tm["horizons"][-1]
    a = tm["aggregate"][h0]
    st.markdown(f"#### ⏳ 종목 타임머신 &nbsp;<span style='color:#94a3b8;font-size:0.78em;font-weight:400;'>최근 {window}일 패턴 · 과거 검색</span>",
                unsafe_allow_html=True)
    col_a = "#dc2626" if a["avg"] >= 0 else "#2563eb"
    dots = "🔴" * a["up"] + "🔵" * a["down"]
    with st.container(border=True):
        st.markdown(
            f"<div style='display:flex;justify-content:space-between;align-items:center;'>"
            f"<div>닮은 구간 <b>{len(tm['matches'])}번</b>의 {h0}일 뒤<br>"
            f"<span style='font-size:0.92em;'>{dots} &nbsp;<span style='color:#dc2626;'>{a['up']}번 상승</span> · <span style='color:#2563eb;'>{a['down']}번 하락</span></span></div>"
            f"<div style='text-align:right;'><span style='font-size:1.5rem;font-weight:800;color:{col_a};'>{a['avg']:+.2f}%</span><br>"
            f"<span style='color:#94a3b8;font-size:0.8em;'>평균 수익률</span></div></div>",
            unsafe_allow_html=True)
        rows = []
        msim = max((m["similarity"] for m in tm["matches"]), default=100) or 100
        for m in tm["matches"][:3]:
            try:
                dlabel = pd.to_datetime(str(m["end_date"])).strftime("%Y.%m.%d")
            except Exception:
                dlabel = f"#{m['end_index']}"
            f0, f1 = m["forward"][h0], m["forward"][h1]
            c0 = "#dc2626" if f0 >= 0 else "#2563eb"; c1 = "#dc2626" if f1 >= 0 else "#2563eb"
            bw = m["similarity"] / msim * 100
            rows.append(
                "<div style=\"display:flex;align-items:center;gap:10px;margin:6px 0;font-size:0.86rem;\">"
                "<span style=\"width:82px;color:#475569;font-variant-numeric:tabular-nums;\">" + dlabel + "</span>"
                "<span style=\"flex:1;background:#f1f5f9;border-radius:5px;height:14px;overflow:hidden;\">"
                "<span style=\"display:block;width:" + f"{bw:.0f}" + "%;height:100%;background:#c79a3a;border-radius:5px;\"></span></span>"
                "<span style=\"width:40px;text-align:right;color:#475569;\">" + f"{m['similarity']:.0f}" + "%</span>"
                "<span style=\"width:64px;text-align:right;color:" + c0 + ";font-weight:600;\">" + f"{f0:+.2f}" + "%</span>"
                "<span style=\"width:64px;text-align:right;color:" + c1 + ";font-weight:600;\">" + f"{f1:+.2f}" + "%</span></div>"
            )
        st.markdown("<div style='margin-top:8px;border-top:1px solid #e2e8f0;padding-top:6px;'>"
                    "<div style='display:flex;gap:10px;font-size:0.74em;color:#94a3b8;'>"
                    "<span style='width:82px;'>유사 시점</span><span style='flex:1;'>유사도</span>"
                    f"<span style='width:40px;text-align:right;'></span><span style='width:64px;text-align:right;'>{h0}일 뒤</span>"
                    f"<span style='width:64px;text-align:right;'>{h1}일 뒤</span></div>" + "".join(rows) + "</div>",
                    unsafe_allow_html=True)
    st.caption("이 종목 자신의 과거 가격 패턴 기록이에요 — 예측이 아니라 과거 사실이며, 표본이 적어 참고용입니다. 매수·매도 권유가 아닙니다.")


def nb_render_briefing(briefing_text, ts_label):
    """AI 모닝 브리핑을 '작은 폰트 + 블루 카드'로 렌더.
    AI가 돌려준 마크다운의 #/## 헤더가 거대하게 뜨던 문제를 자체 변환으로 해결해
    제목 16px / 소제목 14px / 본문 13.5px 로 가독성 있게 통일한다."""
    import re as _re, html as _html
    out = []; in_ul = False
    def _inline(s):
        s = _html.escape(s)
        s = _re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", s)
        s = _re.sub(r"(?<!\*)\*(?!\*)([^*]+?)\*(?!\*)", r"<em>\1</em>", s)
        s = _re.sub(r"`([^`]+?)`", r"<code style='background:#e0e7ff;padding:1px 4px;border-radius:4px;font-size:0.92em;'>\1</code>", s)
        return s
    for raw in str(briefing_text).split("\n"):
        line = raw.rstrip()
        if not line.strip():
            if in_ul: out.append("</ul>"); in_ul = False
            continue
        mh = _re.match(r"^\s*(#{1,6})\s+(.*)$", line)
        if mh:
            if in_ul: out.append("</ul>"); in_ul = False
            lvl = len(mh.group(1)); txt = _inline(mh.group(2))
            if lvl <= 2:
                out.append(f"<div style='font-size:16px;font-weight:700;color:#0f172a;margin:13px 0 5px;'>{txt}</div>")
            else:
                out.append(f"<div style='font-size:14px;font-weight:700;color:#1d4ed8;margin:12px 0 4px;'>{txt}</div>")
            continue
        mb = _re.match(r"^\s*[-*•]\s+(.*)$", line)
        if mb:
            if not in_ul: out.append("<ul style='margin:5px 0;padding-left:18px;'>"); in_ul = True
            out.append(f"<li style='margin:4px 0;'>{_inline(mb.group(1))}</li>")
            continue
        if in_ul: out.append("</ul>"); in_ul = False
        out.append(f"<p style='margin:5px 0;'>{_inline(line)}</p>")
    if in_ul: out.append("</ul>")
    st.markdown(
        "<div style=\"background:#eff6ff;border:1px solid #bfdbfe;border-left:4px solid #3b82f6;"
        "border-radius:12px;padding:14px 17px;font-size:13.5px;line-height:1.65;color:#1e293b;\">"
        "<div style=\"font-size:12px;color:#2563eb;font-weight:700;margin-bottom:8px;\">"
        "💡 [" + _html.escape(str(ts_label)) + " KST 기준]</div>"
        + "".join(out) + "</div>", unsafe_allow_html=True)


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
@st.cache_data(ttl=180)
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
# [홈 리디자인] '여의도 모닝 데스크' 전용 컴팩트 위젯
#   - 기존 홈의 정보 중복(시장국면 3회·환율 3회·VIX 2회·등락종목수 2회)을 제거하고
#     전문 트레이더의 아침 점검 흐름(간밤→국면→지수/수급→자금→심리→일정→내종목)으로 재구성.
#   - 무거운 plotly 게이지 2개 → 슬림 HTML 타일로 교체(정보 밀도↑, 로딩 부담↓).
# =====================================================================
_UP_C, _DN_C, _FLAT_C = "#ef4444", "#3b82f6", "#94a3b8"   # 한국식 색: 상승=빨강 / 하락=파랑


def _sign_of(x):
    try:
        return 1 if x > 0 else (-1 if x < 0 else 0)
    except Exception:
        return 0


def _chg_color(sign):
    return _UP_C if sign > 0 else (_DN_C if sign < 0 else "#64748b")


def render_regime_hero():
    """① 오늘의 시장 국면 — 최상단 '결정 배너'. 신호등 + 한줄 가이드 + 코스피/코스닥 + 시장 폭."""
    try:
        reg = get_market_regime()
    except Exception:
        reg = {}
    light, title, desc = reg.get('verdict', ("🟡", "데이터 지연", "지수 데이터를 불러오는 중입니다."))
    accent, bg, brd = {
        "🟢": ("#15803d", "linear-gradient(135deg,#f0fdf4,#ffffff)", "#bbf7d0"),
        "🟡": ("#b45309", "linear-gradient(135deg,#fffbeb,#ffffff)", "#fde68a"),
        "🔴": ("#b91c1c", "linear-gradient(135deg,#fef2f2,#ffffff)", "#fecaca"),
    }.get(light, ("#475569", "#f8fafc", "#e2e8f0"))

    chips = ""
    # [동기화] 시장 국면 배너의 '현재가·등락률'을 아래 '실시간 & 수급' 패널과 동일한 소스(네이버 get_kr_index_panel)에서 읽어 통일한다.
    #   - 원인: get_market_regime은 fdr 일봉 종가를 쓰는데, 장중에는 일봉이 아직 당일 봉을 안 만들어 '전일 종가'가 잡혀 실시간 패널과 값이 달라짐.
    #   - 정배열/역배열·점수·RSI는 일봉 분석이 필요하므로 그대로 두고, 화면 표시 숫자(price·pct)만 실시간으로 맞춘다.
    try:
        live_panel = get_kr_index_panel() or {}
    except Exception:
        live_panel = {}

    for k in ("KOSPI", "KOSDAQ"):
        d = reg.get(k)
        if isinstance(d, dict):
            d = dict(d)  # 캐시 원본 보호용 사본
            lv = live_panel.get(k)
            if isinstance(lv, dict) and lv.get("price") is not None:
                d["price"] = lv["price"]                      # 실시간 현재가로 교체
                if lv.get("pct") is not None:                 # 네이버 pct는 절댓값 + 별도 sign → 부호 결합
                    d["pct"] = abs(lv["pct"]) * (1 if lv.get("sign", 0) >= 0 else -1)
                elif lv.get("sign") is not None:
                    d["pct"] = abs(d.get("pct", 0)) * (1 if lv["sign"] >= 0 else -1)
            sign = _sign_of(d.get("pct", 0))
            c = _chg_color(sign)
            arrow = "▲" if sign > 0 else ("▼" if sign < 0 else "·")
            chips += (
                f'<div style="flex:1;min-width:118px;background:#fff;border:1px solid {brd};'
                f'border-radius:12px;padding:10px 12px;">'
                f'<div style="font-size:11.5px;color:#64748b;font-weight:700;">{d.get("light","")} {d.get("name","")}'
                f'<span style="color:#94a3b8;font-weight:600;"> · {d.get("align","")}</span></div>'
                f'<div style="display:flex;align-items:baseline;gap:7px;margin-top:2px;">'
                f'<span style="font-size:18px;font-weight:800;color:#0f172a;">{d.get("price",0):,.2f}</span>'
                f'<span style="font-size:13px;font-weight:800;color:{c};">{arrow} {abs(d.get("pct",0)):.2f}%</span></div></div>'
            )
    b = reg.get("breadth")
    if b:
        ratio = b.get("up_ratio", 0)
        bc = _UP_C if ratio >= 55 else (_DN_C if ratio <= 45 else "#64748b")
        chips += (
            f'<div style="flex:1;min-width:118px;background:#fff;border:1px solid {brd};'
            f'border-radius:12px;padding:10px 12px;">'
            f'<div style="font-size:11.5px;color:#64748b;font-weight:700;">📊 시장 폭(상승비율)</div>'
            f'<div style="display:flex;align-items:baseline;gap:7px;margin-top:2px;">'
            f'<span style="font-size:18px;font-weight:800;color:{bc};">{ratio:.0f}%</span>'
            f'<span style="font-size:11.5px;color:#64748b;">↗{b.get("up",0):,} ↘{b.get("down",0):,}</span></div></div>'
        )

    st.markdown(
        f"""
        <div style="background:{bg};border:1px solid {brd};border-radius:18px;
                    padding:16px 20px;box-shadow:0 2px 8px rgba(15,23,42,0.05);">
          <div style="display:flex;align-items:center;gap:12px;flex-wrap:wrap;">
            <span style="font-size:30px;line-height:1;">{light}</span>
            <span style="font-size:21px;font-weight:900;color:{accent};letter-spacing:-0.5px;">오늘의 시장 국면 · {title}</span>
          </div>
          <div style="font-size:13.5px;color:#475569;margin:8px 0 14px;line-height:1.5;">{desc}</div>
          <div style="display:flex;gap:10px;flex-wrap:wrap;">{chips}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_overnight_tape():
    """② 간밤 글로벌 — 美3대지수 + 필반(SOX) + 美10년물 + WTI를 한 줄 압축 타일로."""
    ov = {d["label"]: d for d in (get_overnight_us_market() or [])}
    macro = get_macro_indicators() or {}

    tiles = []   # (라벨, 값, 변동, 부호)
    for key, short in (("나스닥", "나스닥"), ("S&P500", "S&P 500"), ("다우", "다우")):
        d = ov.get(key)
        if d:
            s = _sign_of(d["pct"])
            tiles.append((short, f"{d['value']:,.0f}", f"{'+' if s>=0 else '-'}{abs(d['pct']):.2f}%", s))
    if "필라델피아 반도체" in macro:
        m = macro["필라델피아 반도체"]; base = m["prev"] or 1
        pct = (m["delta"] / base) * 100; s = _sign_of(pct)
        tiles.append(("필라델피아 반도체", f"{m['value']:,.1f}", f"{'+' if s>=0 else '-'}{abs(pct):.2f}%", s))
    if "美 10년물 국채" in macro:
        m = macro["美 10년물 국채"]; s = _sign_of(m["delta"])
        tiles.append(("美 10년물", f"{m['value']:.3f}%", f"{'+' if s>=0 else ''}{m['delta']:.3f}%p", s))
    if "WTI 원유" in macro:
        m = macro["WTI 원유"]; base = m["prev"] or 1
        pct = (m["delta"] / base) * 100; s = _sign_of(pct)
        tiles.append(("WTI 원유", f"${m['value']:,.2f}", f"{'+' if s>=0 else '-'}{abs(pct):.2f}%", s))

    if not tiles:
        st.caption("⚠️ 간밤 글로벌 지표를 일시적으로 불러오지 못했습니다.")
        return

    cells = ""
    for label, vstr, cstr, sign in tiles:
        c = _chg_color(sign)
        cells += (
            f'<div style="flex:1;min-width:104px;text-align:center;padding:11px 6px;border-right:1px solid #f1f5f9;">'
            f'<div style="font-size:11.5px;color:#64748b;font-weight:700;white-space:nowrap;">{label}</div>'
            f'<div style="font-size:17px;font-weight:800;color:#0f172a;margin-top:3px;white-space:nowrap;">{vstr}</div>'
            f'<div style="font-size:12px;font-weight:800;color:{c};margin-top:1px;white-space:nowrap;">{cstr}</div></div>'
        )
    st.markdown(
        f'<div style="display:flex;flex-wrap:wrap;background:#fff;border:1px solid #e9eef3;'
        f'border-radius:14px;overflow:hidden;box-shadow:0 1px 3px rgba(0,0,0,0.04);">{cells}</div>',
        unsafe_allow_html=True,
    )


def render_sentiment_strip(fg_data, macro_data):
    """⑤ 투자 심리 — VIX + CNN 공포·탐욕 지수를 슬림 타일로(기존 거대 게이지 2개 대체)."""
    vix_html = ""
    if macro_data and "VIX" in macro_data:
        v = macro_data["VIX"]["value"]; dv = macro_data["VIX"]["delta"]
        if v < 15: vc, vlab = "#16a34a", "안정"
        elif v < 20: vc, vlab = "#ca8a04", "주의"
        elif v < 30: vc, vlab = "#ea580c", "경계"
        else: vc, vlab = "#dc2626", "공포"
        ds = _sign_of(dv)
        dcol = "#dc2626" if ds > 0 else ("#16a34a" if ds < 0 else "#64748b")   # VIX는 상승이 위험
        vix_html = (
            f'<div style="flex:1;min-width:160px;background:#fff;border:1px solid #e9eef3;border-radius:14px;padding:12px 16px;">'
            f'<div style="font-size:12px;color:#64748b;font-weight:700;">😱 VIX 변동성(美 공포지수)</div>'
            f'<div style="display:flex;align-items:baseline;gap:8px;margin-top:4px;">'
            f'<span style="font-size:24px;font-weight:900;color:{vc};">{v:.2f}</span>'
            f'<span style="font-size:13px;font-weight:800;color:{vc};">{vlab}</span>'
            f'<span style="font-size:12px;font-weight:700;color:{dcol};">{"+" if ds>0 else ""}{dv:.2f}</span></div>'
            f'<div style="font-size:10.5px;color:#94a3b8;margin-top:3px;">20↑ 변동성 확대 · 30↑ 공포 국면</div></div>'
        )

    fg_html = ""
    if fg_data:
        score = fg_data.get("score", 50); rating = fg_data.get("rating", ""); delta = fg_data.get("delta", 0)
        if score >= 75: fc = "#16a34a"
        elif score >= 55: fc = "#65a30d"
        elif score >= 45: fc = "#ca8a04"
        elif score >= 25: fc = "#ea580c"
        else: fc = "#dc2626"
        pos = min(max(score, 0), 100)
        fg_html = (
            f'<div style="flex:2;min-width:250px;background:#fff;border:1px solid #e9eef3;border-radius:14px;padding:12px 16px;">'
            f'<div style="display:flex;justify-content:space-between;align-items:baseline;">'
            f'<span style="font-size:12px;color:#64748b;font-weight:700;">🧭 CNN 공포·탐욕 지수</span>'
            f'<span style="font-size:13px;font-weight:800;color:{fc};">{score} · {rating}</span></div>'
            f'<div style="position:relative;height:10px;border-radius:6px;margin:11px 0 5px;'
            f'background:linear-gradient(90deg,#dc2626,#f59e0b,#16a34a);">'
            f'<span style="position:absolute;left:{pos}%;top:-3px;width:16px;height:16px;border-radius:50%;'
            f'background:#fff;border:2.5px solid {fc};transform:translateX(-50%);box-shadow:0 1px 3px rgba(0,0,0,0.2);"></span></div>'
            f'<div style="display:flex;justify-content:space-between;font-size:10.5px;color:#94a3b8;">'
            f'<span>극단적 공포 0</span><span>중립 50</span><span>100 극단적 탐욕</span></div></div>'
        )

    if not (vix_html or fg_html):
        st.caption("⚠️ 투자 심리 지표를 일시적으로 불러오지 못했습니다.")
        return
    st.markdown(
        f'<div style="display:flex;gap:10px;flex-wrap:wrap;">{vix_html}{fg_html}</div>',
        unsafe_allow_html=True,
    )


def render_week_catalysts():
    """⑥ 향후 1개월 핵심 일정 — 중앙은행(FOMC·ECB·BOJ·한은)·물가(CPI·PCE)·경기(고용·PMI·소매판매·수출입)·수급(동시만기)을 압축 표시."""
    now_kst = (datetime.utcnow() + timedelta(hours=9)).date()

    def _add_one_month(d):
        # 같은 날짜 한 달 뒤(다음 달에 같은 일자가 없으면 말일로 보정: 예 1/31→2월 말일)
        y, m = (d.year + 1, 1) if d.month == 12 else (d.year, d.month + 1)
        last = calendar.monthrange(y, m)[1]
        return d.replace(year=y, month=m, day=min(d.day, last))

    # 오늘부터 약 1개월(같은 날짜 다음 달)까지를 조회 구간으로 사용
    end_date = _add_one_month(now_kst)
    days = [now_kst + timedelta(days=i) for i in range((end_date - now_kst).days + 1)]
    dow_kr = ["월", "화", "수", "목", "금", "토", "일"]

    def _evt_color(label):
        # 카테고리별 색: 중앙은행=보라 / 물가=주황 / 고용=파랑 / 경기=청록 / 수급·만기=핑크
        if any(k in label for k in ("FOMC", "금통위", "ECB", "BOJ", "통화정책", "금융정책", "의사록")): return "#7c3aed"
        if any(k in label for k in ("CPI", "PCE", "PPI", "물가")): return "#ea580c"
        if "고용" in label or "실업" in label: return "#2563eb"
        if any(k in label for k in ("PMI", "소매판매", "수출", "무역", "GDP", "산업생산")): return "#0d9488"
        if any(k in label for k in ("만기", "네마녀", "위칭", "MSCI")): return "#db2777"
        return "#475569"

    def _events_for(d):
        # 경제지표(get_economic_events) + 선물옵션 동시만기(3·6·9·12월 둘째 목요일)를 병합.
        # 동시만기는 캘린더 페이지가 자체 로직으로 별도 표기하므로 여기서만 규칙으로 주입(중복 방지).
        evs = list(get_economic_events(d.year, d.month).get(d.day, []))
        if d.month in (3, 6, 9, 12) and d.weekday() == 3 and 8 <= d.day <= 14:
            evs.append(("🌗 🇰🇷선물옵션 동시만기(네마녀)", "evt-econ-expiry"))
        return evs

    rows = [(d, evs) for d in days if (evs := _events_for(d))]

    if not rows:
        st.markdown(
            '<div style="background:#fff;border:1px solid #e9eef3;border-radius:14px;padding:14px 16px;'
            'color:#64748b;font-size:13px;">📭 향후 1개월간 예정된 주요 매크로·수급 일정이 없습니다.</div>',
            unsafe_allow_html=True)
        return

    body = ""
    cur_month = None
    for d, evs in rows:
        # 달이 바뀌면 가벼운 월 구분선 삽입(1개월 구간이 두 달에 걸칠 때 가독성↑)
        if d.month != cur_month:
            cur_month = d.month
            body += (
                f'<div style="padding:8px 10px 4px;font-size:11px;font-weight:800;'
                f'color:#94a3b8;letter-spacing:0.3px;">{d.year}년 {d.month}월</div>'
            )
        is_today = (d == now_kst)
        date_bg = "#fef2f2" if is_today else "transparent"
        date_c = "#dc2626" if is_today else "#0f172a"
        tag = ' <span style="font-size:10px;color:#dc2626;font-weight:800;">● 오늘</span>' if is_today else ""
        chips = "".join(
            f'<span style="display:inline-block;background:#f8fafc;color:{_evt_color(lab)};'
            f'border:1px solid #eef2f6;border-radius:8px;padding:3px 9px;margin:0 5px 0 0;font-size:12px;font-weight:700;">{lab}</span>'
            for (lab, _c) in evs
        )
        body += (
            f'<div style="display:flex;align-items:center;gap:12px;padding:9px 10px;'
            f'background:{date_bg};border-bottom:1px solid #f1f5f9;">'
            f'<div style="min-width:78px;font-size:13px;font-weight:800;color:{date_c};">'
            f'{d.month}/{d.day}({dow_kr[d.weekday()]}){tag}</div>'
            f'<div style="flex:1;">{chips}</div></div>'
        )
    st.markdown(
        f'<div style="background:#fff;border:1px solid #e9eef3;border-radius:14px;padding:4px 14px;'
        f'box-shadow:0 1px 3px rgba(0,0,0,0.04);">{body}</div>',
        unsafe_allow_html=True,
    )
    st.caption("💡 발표 당일은 변동성이 커집니다. 중앙은행(FOMC·ECB·BOJ·한은)·물가(CPI·PCE)·경기(고용·PMI·소매판매·수출입)·동시만기 전후 포지션에 유의하세요. "
               "(중앙은행·의사록·동시만기=확정 / 지표 발표일=통상 시기 기준 추정)")


def render_watchlist_signals():
    """⑦ 내 관심종목 신호 — 손절/익절/홀딩 자동 감시(기존 로직 동일, 카드 표현만 개선)."""
    wl = st.session_state.get("watchlist", [])
    if not wl:
        st.info("⭐ '내 관심종목' 탭에서 종목을 추가하면, 여기서 손절·익절 도달 여부를 자동으로 감시합니다.")
        return
    # level: 0 손절위험 / 1 익절도달 / 2 홀딩 / 3 조회불가
    alerts = []
    for item in wl:
        res = analyze_technical_pattern(item["종목명"], item["티커"])
        if not res:
            alerts.append((3, item["종목명"], "데이터 조회 지연"))
            continue
        is_us = not str(item["티커"]).isdigit()
        cur = f"${res['현재가']:,.2f}" if is_us else f"{int(res['현재가']):,}원"
        sl = f"${res['손절가']:,.2f}" if is_us else f"{int(res['손절가']):,}원"
        tg = f"${res['목표가1']:,.2f}" if is_us else f"{int(res['목표가1']):,}원"
        if res["현재가"] <= res["손절가"]:
            alerts.append((0, item["종목명"], f"손절선 이탈 위험 · 현재 {cur} / 손절 {sl}"))
        elif res["현재가"] >= res["목표가1"] * 0.98:
            alerts.append((1, item["종목명"], f"1차 익절 구간 도달 · 현재 {cur} / 목표 {tg}"))
        else:
            alerts.append((2, item["종목명"], f"홀딩 · 현재 {cur} (손절 {sl})"))
    alerts.sort(key=lambda x: x[0])

    style = {
        0: ("🔴", "#fef2f2", "#fecaca", "#b91c1c"),
        1: ("🟢", "#f0fdf4", "#bbf7d0", "#15803d"),
        2: ("🟡", "#fffbeb", "#fde68a", "#b45309"),
        3: ("⚪", "#f8fafc", "#e2e8f0", "#64748b"),
    }
    n_risk = sum(1 for a in alerts if a[0] == 0)
    n_take = sum(1 for a in alerts if a[0] == 1)
    st.caption(f"총 {len(alerts)}개 감시 중 · 🔴 손절경보 {n_risk} · 🟢 익절도달 {n_take}")
    cards = ""
    for lv, name, msg in alerts:
        ic, bg, brd, tc = style[lv]
        cards += (
            f'<div style="display:flex;align-items:center;gap:10px;background:{bg};border:1px solid {brd};'
            f'border-radius:11px;padding:9px 13px;margin-bottom:6px;">'
            f'<span style="font-size:15px;">{ic}</span>'
            f'<span style="font-weight:800;color:#0f172a;min-width:104px;">{name}</span>'
            f'<span style="font-size:13px;color:{tc};font-weight:600;">{msg}</span></div>'
        )
    st.markdown(cards, unsafe_allow_html=True)


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
                    scale = 100.0 if latest <= 1.5 else 1.0
                    latest *= scale; avg5 *= scale
                    out['short_vol_ratio'] = round(latest, 2)
                    out['short_vol_avg5'] = round(avg5, 2)
                    out['short_vol_trend'] = "📈 증가" if latest > avg5 * 1.1 else ("📉 감소" if latest < avg5 * 0.9 else "➖ 유지")
                    # 미니차트용 일별 시계열 (최근 30일)
                    out['short_vol_series'] = [(str(i)[:10], round(float(v) * scale, 2))
                                               for i, v in ratio.tail(30).items()]
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
                    out['short_bal_series'] = [(str(i)[:10], round(float(v), 2))
                                               for i, v in br.tail(30).items()]
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
                name = quote.get('shortname') or quote.get('longname') or 'Unknown'
                # 티커로 먼저 매핑(정확) → 실패 시 영문 회사명으로
                ko_name = get_korean_name(sym)
                if not ko_name or ko_name == sym:
                    ko_name = get_korean_name(name)
                exch = quote.get('exchDisp', 'US')
                results.append(f"{sym} ({ko_name} / {exch})")
        return results
    except Exception: return []

@st.cache_data(ttl=3600)
# === [전문가 보조지표 계산] ==================================================
def _calc_expert_metrics(adf):
    """가격 DF에서 전문가 보조지표 계산 → dict 반환. (네트워크 호출 없음, 부족하면 항목별 None)
    - 고점대비52주: 최근 252거래일 고점 대비 % (0에 가까울수록 신고가권)
    - 이격도20: 20일선 대비 괴리 % (과열/눌림 판단)
    - 수익률20일: 시장 상대강도(RS) 계산용 최근 20일 수익률 %
    - MFI: 14일 자금흐름지수(거래량 가중 RSI)
    - 평균거래대금20일: 종가×거래량 20일 평균 (유동성 필터, 통화 단위 그대로)
    - 변동성20일: 일간 수익률 20일 표준편차 %/일"""
    out = {"고점대비52주": None, "이격도20": None, "수익률20일": None,
           "MFI": None, "평균거래대금20일": None, "변동성20일": None}
    try:
        close = pd.to_numeric(adf["Close"], errors="coerce").dropna()
        if len(close) < 21:
            return out
        cur = float(close.iloc[-1])
        if cur <= 0:
            return out
        hi_src = adf["High"] if ("High" in adf.columns and adf["High"].notna().any()) else close
        hi = float(pd.to_numeric(hi_src, errors="coerce").tail(252).max())
        if hi > 0:
            out["고점대비52주"] = round((cur / hi - 1) * 100, 1)
        if "MA20" in adf.columns and pd.notna(adf["MA20"].iloc[-1]):
            ma20 = float(adf["MA20"].iloc[-1])
        else:
            ma20 = float(close.rolling(20).mean().iloc[-1])
        if ma20 > 0:
            out["이격도20"] = round((cur / ma20 - 1) * 100, 1)
        out["수익률20일"] = round((cur / float(close.iloc[-21]) - 1) * 100, 1)
        if {"High", "Low", "Volume"}.issubset(adf.columns):
            h = pd.to_numeric(adf["High"], errors="coerce")
            lo = pd.to_numeric(adf["Low"], errors="coerce")
            c = pd.to_numeric(adf["Close"], errors="coerce")
            v = pd.to_numeric(adf["Volume"], errors="coerce")
            tp = (h + lo + c) / 3.0
            mf = tp * v
            dtp = tp.diff()
            pos = mf.where(dtp > 0, 0.0).rolling(14).sum()
            neg = mf.where(dtp < 0, 0.0).rolling(14).sum()
            denom = neg.replace(0, float("nan"))
            mfi = 100 - 100 / (1 + pos / denom)
            val = mfi.iloc[-1]
            if pd.notna(val):
                out["MFI"] = round(float(val), 1)
        if "Volume" in adf.columns:
            v = pd.to_numeric(adf["Volume"], errors="coerce")
            amt = (pd.to_numeric(adf["Close"], errors="coerce") * v).rolling(20).mean()
            val = amt.iloc[-1]
            if pd.notna(val) and val > 0:
                out["평균거래대금20일"] = float(val)
        vol = close.pct_change().rolling(20).std().iloc[-1]
        if pd.notna(vol):
            out["변동성20일"] = round(float(vol) * 100, 2)
    except Exception:
        pass
    return out
# === [/전문가 보조지표 계산] =================================================


def analyze_technical_pattern(stock_name, ticker_code, offset_days=0):
    if not ticker_code: return None
    is_us = not str(ticker_code).isdigit()
    if is_us: stock_name = get_korean_name(stock_name)
    try:
        df = get_historical_data(ticker_code, 260)   # 52주 신고가 계산을 위해 260일 조회
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
        ai_target_val, ai_target_detail = calc_ai_target_price(per, pbr, current_price, ticker_code, use_sector_per=False)  # ⚡ 스캔 경로: 네트워크 추가 0건
        
        target_1 = float(latest['Bollinger_Upper'])
        recent_high = float(analysis_df['Close'].tail(150).max())   # 목표가 로직은 기존(150일) 기준 유지
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
            "시장": get_market_label(ticker_code), "기준일": (analysis_df.index[-1] if len(analysis_df) else None),
            "진입가_가이드": ma20_val, "목표가1": target_1, "목표가2": target_2, "목표가3": target_3, "손절가": ma20_val * 0.97,
            "거래량 급증": "🔥 거래량 터짐" if analysis_df.iloc[-10:]['Volume'].max() > (analysis_df.iloc[-10:]['Vol_MA20'].mean() * 2) else "평이함",
            "RSI": latest['RSI'], "배열상태": align_status, "주봉추세": weekly_trend,
            "기관수급": inst_vol, "외인수급": forgn_vol, "개인수급": ind_vol, "장중잠정수급": intraday_est,
            "기관연속순매수": inst_streak, "외인연속순매수": forgn_streak,
            "연기금추정순매수": pension_sum, "연기금연속순매수": pension_streak,
            "PER": per, "PBR": pbr, "FCF": fcf, "Shares": shares, "목표가_컨센서스": target_price,
            "AI목표가": ai_target_val, "AI목표가_근거": ai_target_detail,
            "OBV": analysis_df['OBV'].tail(20), "차트 데이터": analysis_df.tail(20), 
            **_calc_expert_metrics(analysis_df),
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
        response = _genai_generate(prompt, api_key)

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
    def _prc_guide_terms():
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
    _register_popup("guide_terms", _prc_guide_terms)
    _popup_button("🐥 [주린이 필독] 주식 용어 & 매매 타점 완벽 가이드", "guide_terms", "🐥 주식 용어 & 매매 타점 가이드", key="btn_guide_terms")

def show_trading_guidelines():
    def _prc_guide_4step():
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
    _register_popup("guide_4step", _prc_guide_4step)
    _popup_button("🎯 [필독] 실전 매매 4STEP 시나리오 (단기 스윙)", "guide_4step", "🎯 실전 매매 4STEP 시나리오", key="btn_guide_4step")

# =====================================================================
# [신규] 카드 내 두 기능을 '팝업 창(st.dialog)'으로 — 전문가 AI 질의응답 / 매물대·타임머신
#   퀀트 비서와 동일 패턴: 버튼 클릭 시 다이얼로그 등록 → 내부 상호작용은 Streamlit이 자동 유지.
#   채팅은 컨테이너에 즉시 출력(st.rerun 미사용) → 내장 X 버튼으로 정상 닫힘. (구버전은 인라인 폴백)
# =====================================================================
def _expert_chat_body():
    ctx = st.session_state.get("_chat_ctx") or {}
    stock_name = ctx.get("stock_name", "종목"); ticker_code = ctx.get("ticker_code", "")
    is_us = ctx.get("is_us", False); sector = ctx.get("sector", ""); tf = ctx.get("tf", "일봉")
    curr = ctx.get("curr", 0); tech_result = ctx.get("tech_result", {}); api_key_str = ctx.get("api_key_str", "")
    chat_state_key = f"expert_chat_{ticker_code}"
    if chat_state_key not in st.session_state:
        st.session_state[chat_state_key] = []

    def _fp(v):
        try:
            val = float(v); return f"${val:,.2f}" if is_us else f"{int(val):,}원"
        except Exception:
            return str(v)

    if not api_key_str:
        st.info("🔑 좌측 사이드바에 Gemini API 키를 입력하면 전문가 질의응답을 사용할 수 있어요.")
        return

    st.caption(f"‘{stock_name}’ 종목·시황 무엇이든 물어보세요. (시황·뉴스는 실시간 검색으로 확인 후 답변)")
    if st.session_state[chat_state_key]:
        if st.button("🗑️ 대화 지우기", key="exp_chat_clr", use_container_width=True):
            st.session_state[chat_state_key] = []

    _hist = st.session_state[chat_state_key]
    box = st.container(height=360)
    if not _hist:
        box.caption("예시 — “지금 들어가도 돼? 분할매수 전략 짜줘” · “최근 급등/급락 이유?” · “경쟁사 대비 밸류에이션은?”")
    for _m in _hist[-12:]:
        box.chat_message("user" if _m["role"] == "user" else "assistant").markdown(_m["content"])

    with st.form(key="exp_chat_form", clear_on_submit=True):
        _q_col, _b_col = st.columns([5, 1], vertical_alignment="bottom")
        user_q = _q_col.text_input("질문 입력", placeholder=f"‘{stock_name}’ 종목이나 시황에 대해 무엇이든…",
                                   label_visibility="collapsed", key="exp_chat_in")
        chat_sent = _b_col.form_submit_button("💬 전송", use_container_width=True, type="primary")

    if chat_sent and user_q.strip():
        _uq = user_q.strip()
        _hist.append({"role": "user", "content": _uq})
        box.chat_message("user").markdown(_uq)
        _ai_tp_ctx = tech_result.get("AI목표가")
        _ctx_txt = f"""[시스템 실측 데이터 — '{stock_name}' 분석 결과, 답변의 1차 근거로 사용할 것]
- 티커: {ticker_code} ({'미국' if is_us else '국내'}) / 섹터: {sector}
- 현재가: {_fp(curr)} / 진단: {tech_result.get('상태', '-')} / 이평 배열: {tech_result.get('배열상태', '-')} / 주봉 추세: {tech_result.get('주봉추세', '-')}
- RSI: {tech_result.get('RSI', '-')} / PER: {tech_result.get('PER', '-')} / PBR: {tech_result.get('PBR', '-')}
- 타점 가이드: 진입 {_fp(tech_result.get('진입가_가이드', 0))} · 1차 목표 {_fp(tech_result.get('목표가1', 0))} · 2차 {_fp(tech_result.get('목표가2', 0))} · 손절 {_fp(tech_result.get('손절가', 0))}
- AI 적정주가: {_fp(_ai_tp_ctx) if _ai_tp_ctx else '산출 불가'} / 증권가 컨센서스: {tech_result.get('목표가_컨센서스', '-')}
- 수급: 외국인 {tech_result.get('외인수급', '-')} / 기관 {tech_result.get('기관수급', '-')}
- 사용자가 보고 있는 차트 주기: {tf}"""
        _conv_txt = "\n".join(
            f"{'사용자' if m['role'] == 'user' else '전문가AI'}: {m['content']}"
            for m in _hist[-9:-1]) or "(첫 질문)"
        _chat_prompt = f"""당신은 20년 경력의 주식·시황 전문 애널리스트 AI입니다. 사용자와 '{stock_name}' 종목에 대해 1:1 대화 중입니다.

[답변 원칙]
1. 아래 [실측 데이터]를 1차 근거로 사용하고, 거기 없는 수치는 절대 지어내지 말 것.
2. 최신 시황·뉴스·실적·업황이 필요한 질문은 반드시 구글 검색으로 확인 후 답할 것. 확인 불가하면 '확인 불가'라고 명시.
3. 한국어로 친근하되 전문적으로, 핵심 위주 5~8줄 이내. 매매 관련 질문엔 [의견 + 근거 + 리스크] 구조로.
4. 직전 대화 맥락을 이어서 답할 것.
5. 마지막 줄에 '※ 투자 판단의 참고용이며 최종 책임은 투자자 본인에게 있습니다.' 표기.

{_ctx_txt}

[직전 대화]
{_conv_txt}

[사용자의 새 질문]
{_uq}"""
        with st.spinner("🧑‍💼 전문가 AI가 데이터와 최신 시황을 확인하며 답변 작성 중..."):
            _ans = None
            try:
                _gr = _genai_generate(_chat_prompt, api_key_str, grounding=True)
                if _gr.candidates and _gr.candidates[0].content.parts:
                    _ans = _gr.text
            except Exception:
                _ans = None
            if not _ans:
                _ans = ask_gemini(_chat_prompt + "\n\n(검색 불가 상태이니 실측 데이터 기반으로만 답하고, 최신 뉴스성 내용은 '확인 불가'로 표기)", api_key_str)
        _hist.append({"role": "assistant", "content": _ans})
        box.chat_message("assistant").markdown(_ans)
        st.session_state[chat_state_key] = _hist[-20:]


def _vptm_body():
    ctx = st.session_state.get("_vptm_ctx") or {}
    ticker_code = ctx.get("ticker_code", ""); curr = ctx.get("curr", 0)
    with st.spinner("일봉 데이터로 매물대·과거 패턴 계산 중..."):
        _hist_df = get_historical_data(ticker_code, 800)
    if _hist_df is None or _hist_df.empty or len(_hist_df) < 40:
        st.info("이 종목은 매물대/타임머신을 계산할 일봉 데이터가 부족해요 (상장 기간이 짧거나 조회 실패).")
    else:
        nb_render_volume_profile(_hist_df, current_price=curr)
        st.markdown("<div style='height:8px;'></div>", unsafe_allow_html=True)
        nb_render_time_machine(_hist_df)


if hasattr(st, "dialog"):
    try:
        @st.dialog("💬 전문가 AI 질의응답", width="large")
        def _expert_chat_dialog():
            _expert_chat_body()

        @st.dialog("📊 매물대 지도 · 종목 타임머신", width="large")
        def _vptm_dialog():
            _vptm_body()
    except TypeError:
        @st.dialog("💬 전문가 AI 질의응답")
        def _expert_chat_dialog():
            _expert_chat_body()

        @st.dialog("📊 매물대 지도 · 종목 타임머신")
        def _vptm_dialog():
            _vptm_body()


def _open_expert_chat(ctx):
    st.session_state["_chat_ctx"] = ctx
    if hasattr(st, "dialog"):
        _expert_chat_dialog()
    else:
        st.session_state["_chat_inline_open"] = True


def _open_vptm(ctx):
    st.session_state["_vptm_ctx"] = ctx
    if hasattr(st, "dialog"):
        _vptm_dialog()
    else:
        st.session_state["_vptm_inline_open"] = True


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
    market_label = tech_result.get('시장', '')
    price_with_market = f"{fmt_price(curr)} ({market_label})" if market_label else fmt_price(curr)
    card_title = f"{stock_name} / {core_theme} / {sector} / 현재가: {price_with_market} / {detail_str}"

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

        curr = tech_result['현재가']
        # 진입가/현재가 기준일 라벨 (최신 일봉 날짜)
        _base_dt = tech_result.get('기준일')
        try:
            _base_label = pd.to_datetime(_base_dt).strftime('%m/%d') if _base_dt is not None else ''
        except Exception:
            _base_label = ''
        _base_txt = f" ({_base_label} 기준)" if _base_label else ""

        # 현재가 — 크게/가독성 있게 (타임머신 모드는 위 배너에 이미 표시되므로 생략)
        if not tech_result.get('과거검증'):
            st.markdown(
                "<div style='display:flex;align-items:baseline;flex-wrap:wrap;gap:10px;"
                "background:#f8fafc;border:1px solid #e9eef3;border-radius:12px;padding:10px 16px;margin:4px 0 12px;'>"
                "<span style='font-size:14px;color:#64748b;font-weight:700;'>현재가</span>"
                "<span style='font-size:32px;font-weight:800;color:#1e293b;line-height:1;"
                f"font-family:\"JetBrains Mono\",monospace;'>{fmt_price(curr)}</span>"
                f"<span style='font-size:13px;color:#94a3b8;'>{_base_txt}</span>"
                "</div>", unsafe_allow_html=True)

        c1, c2, c3, c4 = st.columns(4)
        c1.metric(f"📌 진입 기준가{_base_txt}", fmt_price(tech_result['진입가_가이드']), fmt_price(tech_result['진입가_가이드'] - curr, True) + " (대비)", delta_color="off")
        c2.metric("🎯 1차 (볼밴상단)", fmt_price(tech_result['목표가1']), fmt_price(tech_result['목표가1'] - curr, True), delta_color="normal")
        c3.metric("🚀 2차 (스윙전고)", fmt_price(tech_result['목표가2']), fmt_price(tech_result['목표가2'] - curr, True), delta_color="normal")
        c4.metric("🌌 3차 (오버슈팅)", fmt_price(tech_result['목표가3']), fmt_price(tech_result['목표가3'] - curr, True), delta_color="normal")
        st.caption(f"ℹ️ 진입 기준가 = 20일 이동평균선 · 현재가·지표는 {_base_label + ' ' if _base_label else ''}일봉 종가 기준 (최대 1시간 캐시)")
        
        st.markdown("---")
        
        c5, c6, c6b, c7, c8 = st.columns([1.1, 1.1, 1.1, 0.9, 2.3]) 
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
        
        # [NEW] 🤖 AI 적정주가 (PER·PBR 멀티팩터 밸류에이션)
        ai_tp = tech_result.get("AI목표가")
        ai_tp_detail = tech_result.get("AI목표가_근거", "")
        # 🔍 상세 카드에서만 업종 PER 포함 정밀 재계산 (티커당 1회 HTTP, 1시간 캐시 → 스캔 속도에 영향 없음)
        if not is_us:
            try:
                _ai_precise, _ai_precise_d = calc_ai_target_price(
                    tech_result.get('PER'), tech_result.get('PBR'), curr, ticker_code, use_sector_per=True)
                if _ai_precise:
                    ai_tp, ai_tp_detail = _ai_precise, _ai_precise_d
            except Exception:
                pass
        _ai_help = ("PER·PBR을 역산한 EPS·BPS·ROE 기반 멀티팩터 적정주가입니다.\n"
                    "① 그레이엄 공식 √(22.5×EPS×BPS)\n"
                    "② S-RIM 약식: BPS×(ROE÷요구수익률 8%)\n"
                    "③ 업종 PER 상대가치(국내): EPS×동일업종 PER\n"
                    "→ 산출 가능한 방법들의 평균 (현재가 ±70% 클리핑)\n"
                    f"{('산출 근거: ' + ai_tp_detail) if ai_tp else ''}")
        if ai_tp:
            c6b.metric("🤖 AI 적정주가", fmt_price(ai_tp), fmt_price(ai_tp - curr, True) + " (괴리)", delta_color="normal", help=_ai_help)
        else:
            c6b.metric("🤖 AI 적정주가", "산출 불가", ai_tp_detail, delta_color="off", help=_ai_help)
            
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

            # ── 차트·수급·재무 정밀 진단 결과 렌더러 (팝업) ──
            def _prc_aidiag():
                if st.session_state.get(ai_res_key) == "loading":
                    with st.spinner("AI가 차트 및 재무 데이터를 바탕으로 종합 분석 중입니다... (약 5~10초 소요)"):
                        if str(tech_result['티커']).isdigit():
                            fin_df, peer_df, cons = get_financial_deep_data(tech_result['티커'])
                            fin_text = fin_df.to_string() if fin_df is not None and not fin_df.empty else "재무 데이터 없음"
                            peer_text = peer_df.to_string() if peer_df is not None and not peer_df.empty else "비교 데이터 없음"
                            prompt = f"""당신은 여의도 최고의 퀀트 애널리스트이자 펀드매니저입니다. '{tech_result['종목명']}' 분석 리포트를 마크다운으로 작성하세요.
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
4. 💡 **최종 투자 코멘트**: 3줄 요약."""
                            st.session_state[ai_res_key] = ask_gemini(prompt, api_key_str)
                        else:
                            prompt = f"전문 트레이더 관점에서 '{tech_result['종목명']}'을(를) 분석해주세요.\n[데이터] 현재가:{fmt_price(curr)}, 20일선:{fmt_price(tech_result['진입가_가이드'])}, RSI:{tech_result['RSI']:.1f}\n1. ⚡ 단기 트레이딩 관점\n2. 🛡️ 스윙/가치 투자 관점\n3. 🎯 종합 요약 (1줄):"
                            st.session_state[ai_res_key] = ask_gemini(prompt, api_key_str)
                st.success("✅ AI 기술적 정밀 분석 완료!")
                st.markdown(st.session_state.get(ai_res_key, ""))
                if not is_us:
                    st.caption("📊 분석에 쓰인 재무·컨센서스 원본은 창을 닫은 뒤 카드의 ‘로우 데이터’ 버튼에서 볼 수 있어요.")
                if st.button("🔄 다시 분석하기", key=f"re_{ai_btn_key}", use_container_width=True):
                    st.session_state[ai_res_key] = "loading"
            _register_popup(f"aidiag_{key_suffix}", _prc_aidiag)

            # ── 기업 심층 분석 결과 렌더러 (팝업) ──
            def _prc_bizdeep():
                if st.session_state.get(biz_res_key) == "loading":
                    with st.spinner(f"AI가 '{tech_result['종목명']}'의 방대한 기업 정보와 비즈니스 모델을 분석 중입니다... (약 10초 소요)"):
                        prompt = f"""당신은 여의도 최고의 기업 분석 리서치 센터장입니다. '{tech_result['종목명']}' 기업에 대해 심층 분석 리포트를 마크다운으로 작성하세요.
1. 🏭 **무엇을 하는 회사인가? (기업 개요)**: 회사가 구체적으로 어떤 비즈니스 모델을 가지며 어떻게 수익을 창출하는지 초보자도 알기 쉽게 설명.
2. 📊 **사업 구성 및 밸류체인**: 회사의 핵심 매출 파이프라인(주력 사업 비중)과 시장 내에서의 경쟁력 (독점력, 경제적 해자 등).
3. 🚀 **향후 전망 및 모멘텀 (Catalyst)**: 회사의 미래 성장 동력, 신사업 확장 가능성, 그리고 투자자가 반드시 주의해야 할 핵심 리스크 요인.
4. 💡 **한 줄 평**: 이 기업의 본질적인 가치와 투자 매력도에 대한 직관적인 한 줄 요약.
단순 주가 예측이 아닌 '비즈니스 모델'과 '기업의 본질적인 펀더멘털'에 집중하여 통찰력 있게 작성해 주세요."""
                        st.session_state[biz_res_key] = ask_gemini(prompt, api_key_str)
                st.success("✅ AI 비즈니스 심층 분석 완료!")
                st.markdown(st.session_state.get(biz_res_key, ""))
                if st.button("🔄 다시 분석하기", key=f"re_{biz_btn_key}", use_container_width=True):
                    st.session_state[biz_res_key] = "loading"
            _register_popup(f"bizdeep_{key_suffix}", _prc_bizdeep)

            with col_ai1:
                if st.button(f"🤖 차트·수급·재무 정밀 진단 (일봉 6개월)", key=ai_btn_key, type="primary", use_container_width=True):
                    if st.session_state.get(ai_res_key) in (None, "loading"):
                        st.session_state[ai_res_key] = "loading"
                    _open_popup(f"aidiag_{key_suffix}", "🤖 차트·수급·재무 정밀 진단 (일봉 6개월)")
            with col_ai2:
                if st.button(f"🏢 기업 심층 분석 (비즈니스/전망)", key=biz_btn_key, type="primary", use_container_width=True):
                    if st.session_state.get(biz_res_key) in (None, "loading"):
                        st.session_state[biz_res_key] = "loading"
                    _open_popup(f"bizdeep_{key_suffix}", "🏢 기업 심층 분석 (비즈니스/전망)")

            # ── 로우 데이터 버튼 (정밀 진단을 한 번 실행한 뒤 카드에 표시; 팝업) ──
            if not is_us and st.session_state.get(ai_res_key) and st.session_state.get(ai_res_key) != "loading":
                def _prc_rawdata():
                    fin_df, peer_df, cons = get_financial_deep_data(tech_result['티커'])
                    st.write("✅ **증권사 목표가 컨센서스:**", cons)
                    if fin_df is not None: st.dataframe(fin_df, use_container_width=True)
                    if peer_df is not None: st.dataframe(peer_df, use_container_width=True)
                _register_popup(f"rawdata_{key_suffix}", _prc_rawdata)
                _popup_button(f"📊 '{tech_result['종목명']}' 로우 데이터(Raw Data) 보기", f"rawdata_{key_suffix}", f"📊 '{tech_result['종목명']}' 로우 데이터 (Raw Data)", key=f"btn_rawdata_{key_suffix}")
        
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

                # ── 선택한 차트 주기(tf) 기반 AI 분석 ───────────────────────────
                # ── 선택한 차트 주기(tf) 기반 AI 분석 (팝업) ───────────────────
                tf_ai_key = f"tf_ai_{tech_result['티커']}_{tf}_{key_suffix}"
                tf_pop_name = f"tfai_{tech_result['티커']}_{tf}_{key_suffix}"
                st.caption(f"💡 아래 버튼은 위에서 선택한 **‘{tf}’ 주기** 차트를 기준으로 AI가 분석합니다. "
                           "(상단 ‘AI 기술적 정밀 분석’은 일봉 기준 — 주기를 바꿔 비교해 보세요.)")

                def _prc_tfai():
                    if st.session_state.get(tf_ai_key) == "loading":
                        with st.spinner(f"AI가 ‘{tf}’ 주기 차트를 분석 중입니다..."):
                            _d = long_df['Close'].diff()
                            _rs = (_d.where(_d > 0, 0.0).rolling(14).mean()) / (-_d.where(_d < 0, 0.0).rolling(14).mean())
                            _rsi_series = 100 - (100 / (1 + _rs))
                            last = long_df.iloc[-1]
                            rsi_tf = float(_rsi_series.iloc[-1]) if pd.notna(_rsi_series.iloc[-1]) else None
                            close_tf = float(last['Close'])
                            ma20_tf = float(last['MA20']) if pd.notna(last['MA20']) else None
                            bb_tf = float(last['Bollinger_Upper']) if pd.notna(last['Bollinger_Upper']) else None
                            obv_trend = "상승" if long_df['OBV'].iloc[-1] > long_df['OBV'].iloc[-min(5, len(long_df))] else "하락/횡보"
                            recent_closes = long_df['Close'].tail(12).round(2).tolist()
                            ma20_str = f"{ma20_tf:,.2f}" if ma20_tf else "계산불가"
                            bb_str = f"{bb_tf:,.2f}" if bb_tf else "계산불가"
                            rsi_str = f"{rsi_tf:.1f}" if rsi_tf is not None else "계산불가"
                            tf_prompt = f"""당신은 단기 트레이딩에 정통한 차트 분석 전문가입니다.
'{tech_result['종목명']}'의 '{tf}' 주기 차트를 분석하세요.

[{tf} 차트 데이터]
- 현재가(최근 봉 종가): {close_tf:,.2f}
- 20봉 이동평균: {ma20_str}
- 볼린저밴드 상단: {bb_str}
- RSI(14): {rsi_str}
- OBV(거래량 누적) 추세: {obv_trend}
- 피보나치 되돌림: 고점 {max_p:,.2f} / 0.382 {f_382:,.2f} / 0.500 {f_500:,.2f} / 0.618 {f_618:,.2f} / 저점 {min_p:,.2f}
- 최근 종가 흐름: {recent_closes}

다음을 마크다운으로 간결하게 작성하세요(이 '{tf}' 주기에 한정해서 판단):
1. 📈 **현재 추세**: 이 주기에서의 추세 방향과 위치(이평선·볼밴·피보 대비).
2. ⚡ **단기 매매 포인트**: 이 주기 트레이더 기준 진입/관망/청산 의견과 근거.
3. ⚠️ **주의할 신호**: RSI 과열·침체, 거래량 다이버전스 등 경고 신호.
3줄 이내의 핵심 위주로, 이 시간 프레임에 맞는 호흡(예: 30분봉은 단타, 주봉은 중장기)으로 해석하세요."""
                            st.session_state[tf_ai_key] = ask_gemini(tf_prompt, api_key_str)
                    st.success(f"✅ ‘{tf}’ 주기 AI 분석 완료")
                    st.markdown(st.session_state.get(tf_ai_key, ""))
                    if st.button("🔄 다시 분석하기", key=f"re_btn_{tf_ai_key}", use_container_width=True):
                        st.session_state[tf_ai_key] = "loading"
                _register_popup(tf_pop_name, _prc_tfai)

                if api_key_str:
                    if st.button(f"🤖 ‘{tf}’ 주기 AI 차트 분석", key=f"btn_{tf_ai_key}", type="primary", use_container_width=True):
                        if st.session_state.get(tf_ai_key) in (None, "loading"):
                            st.session_state[tf_ai_key] = "loading"
                        _open_popup(tf_pop_name, f"🤖 ‘{tf}’ 주기 AI 차트 분석")

                # ── 💬 종목·시황 전문가 AI 질의응답 (팝업 창) ───────────────────
                st.markdown("---")
                st.markdown(
                    "<div style=\"display:flex;align-items:center;gap:9px;flex-wrap:wrap;"
                    "background:linear-gradient(90deg,#eef2ff,#faf5ff);border:1px solid #c7d2fe;"
                    "border-left:5px solid #6366f1;border-radius:11px;padding:10px 14px;margin:2px 0 7px;"
                    "box-shadow:0 1px 5px rgba(99,102,241,.13);\">"
                    "<span style=\"font-size:1.2em;\">💬</span>"
                    "<span style=\"font-weight:800;color:#4338ca;font-size:1.02em;\">전문가 AI 질의응답</span>"
                    "<span style=\"color:#6366f1;font-size:0.86em;\">이 종목·시황 무엇이든 물어보세요 · 팝업 창</span>"
                    "</div>", unsafe_allow_html=True)
                if st.button(f"💬 전문가 AI와 ‘{stock_name}’ 질의응답 열기", key=f"chat_open_{key_suffix}", type="primary", use_container_width=True):
                    _open_expert_chat({"stock_name": stock_name, "ticker_code": ticker_code, "is_us": is_us,
                                       "sector": sector, "tf": tf, "curr": curr, "tech_result": tech_result,
                                       "api_key_str": api_key_str})
                if not hasattr(st, "dialog") and st.session_state.get("_chat_inline_open"):
                    with st.container(border=True):
                        _expert_chat_body()

                # ── 📊 매물대 지도 & ⏳ 종목 타임머신 (팝업 창) ─────────────────
                st.markdown("---")
                st.markdown(
                    "<div style=\"display:flex;align-items:center;gap:9px;flex-wrap:wrap;"
                    "background:linear-gradient(90deg,#fffbeb,#fef9c3);border:1px solid #fde68a;"
                    "border-left:5px solid #d97706;border-radius:11px;padding:10px 14px;margin:2px 0 7px;"
                    "box-shadow:0 1px 5px rgba(217,119,6,.13);\">"
                    "<span style=\"font-size:1.2em;\">📊</span>"
                    "<span style=\"font-weight:800;color:#b45309;font-size:1.02em;\">매물대 지도 · 종목 타임머신</span>"
                    "<span style=\"color:#d97706;font-size:0.86em;\">가격대별 거래량 + 과거 유사패턴 · 팝업 창</span>"
                    "</div>", unsafe_allow_html=True)
                if st.button(f"📊 ‘{stock_name}’ 매물대 지도 · 종목 타임머신 열기", key=f"vptm_open_{key_suffix}", type="primary", use_container_width=True):
                    _open_vptm({"ticker_code": ticker_code, "curr": curr})
                if not hasattr(st, "dialog") and st.session_state.get("_vptm_inline_open"):
                    with st.container(border=True):
                        _vptm_body()

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
                            def _prc_sugupdiag():
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
                            _register_popup(f"sugupdiag_{key_suffix}", _prc_sugupdiag)
                            _popup_button("🔍 장중 수급 미표시 원인 진단 보기", f"sugupdiag_{key_suffix}", "🔍 장중 수급 미표시 원인 진단 (rt-v2)", key=f"btn_sugupdiag_{key_suffix}")
                    else: 
                        st.caption("수급 데이터를 제공하지 않는 종목입니다.")
            else: 
                st.error("데이터를 불러오지 못했습니다.")
                 
# ============================================================
# 🏆 테마 대장주 랭킹 — 검색한 테마의 '대장주'와 그 뒤 순위를 산출/표시
#   대장주 점수 = 거래대금(0.45) + 시가총액(0.25) + 20일 모멘텀(0.20) + 자금유입강도(0.10)
#   * 통화가 다르므로(원/달러) 반드시 '시장(KR/US)별'로 나눠 각 시장 안에서 백분위 랭킹.
#   * analyze_technical_pattern() 결과 dict의 기존 필드만 사용 — 추가 네트워크 호출 0건.
# ============================================================
_LEADER_MED = {1: "🥇", 2: "🥈", 3: "🥉"}

def _leader_num(x):
    """float 변환. 실패·비유한(NaN/inf)이면 None."""
    try:
        v = float(x)
        return v if np.isfinite(v) else None
    except Exception:
        return None

def _leader_metrics(res):
    """한 종목의 대장주 판정용 원자료 추출(통화는 원본 그대로: KR=원, US=달러)."""
    price = _leader_num(res.get('현재가'))
    sh = _leader_num(res.get('Shares'))                 # 상장주식수(백만주 단위)
    cap = price * sh * 1_000_000 if (price and sh) else None   # 시가총액 = 현재가 × 주식수
    return {
        'cap': cap,
        'amt': _leader_num(res.get('평균거래대금20일')),  # 20일 평균 거래대금
        'mom': _leader_num(res.get('수익률20일')),        # 최근 20일 수익률(%)
        'mfi': _leader_num(res.get('MFI')),               # 자금흐름지수
        'surge': '🔥' in str(res.get('거래량 급증', '')),  # 거래량 급증 여부
    }

def _leader_pctl(vals):
    """None 제외, 최저=0 ~ 최고=1 백분위(동점은 평균 순위). 유효값 1개 이하면 전부 0.5(중립)."""
    valid = [v for v in vals if v is not None]
    n = len(valid)
    if n <= 1:
        return [0.5] * len(vals)
    srt = sorted(valid)
    rank_of, i = {}, 0
    while i < n:                       # 동점 구간은 평균 순위로 묶는다
        j = i
        while j + 1 < n and srt[j + 1] == srt[i]:
            j += 1
        rank_of[srt[i]] = (i + j) / 2.0
        i = j + 1
    return [0.5 if v is None else rank_of[v] / (n - 1) for v in vals]

def _theme_leader_ranking(rows):
    """종목 리스트를 시장(KR/US)별로 나눠 '대장주 점수' 내림차순 랭킹.
    반환: {'KR': [row..], 'US': [row..]} — 각 row는 표시에 필요한 값만 담은 경량 dict(원본 미변경)."""
    groups = {'KR': [], 'US': []}
    for r in rows:
        mkt = 'US' if not str(r.get('티커', '')).isdigit() else 'KR'
        groups[mkt].append(r)

    ranked = {'KR': [], 'US': []}
    for mkt, items in groups.items():
        if not items:
            continue
        met = [_leader_metrics(r) for r in items]
        p_amt = _leader_pctl([m['amt'] for m in met])
        p_cap = _leader_pctl([m['cap'] for m in met])
        p_mom = _leader_pctl([m['mom'] for m in met])
        out = []
        for r, m, pa, pc, pm in zip(items, met, p_amt, p_cap, p_mom):
            heat = (0.5 if m['surge'] else 0.0)
            if m['mfi'] is not None:
                heat += max(0.0, min(1.0, m['mfi'] / 100.0)) * 0.5   # 0~1
            score = 100.0 * (0.45 * pa + 0.25 * pc + 0.20 * pm + 0.10 * heat)
            out.append({
                'name': str(r.get('종목명', '?')), 'ticker': str(r.get('티커', '')),
                'is_us': (mkt == 'US'), 'price': _leader_num(r.get('현재가')),
                'mom': m['mom'], 'amt': m['amt'], 'cap': m['cap'], 'surge': m['surge'],
                'score': round(score, 1),
            })
        out.sort(key=lambda x: x['score'], reverse=True)
        for rk, row in enumerate(out, 1):
            row['rank'] = rk
        ranked[mkt] = out
    return ranked

def _leader_fmt_price(v, is_us):
    if v is None:
        return "—"
    return f"${v:,.2f}" if is_us else f"{v:,.0f}원"

def _leader_fmt_big(v, is_us):
    """거래대금/시가총액 큰 금액 표기(시장별 통화·단위)."""
    if v is None or v <= 0:
        return "—"
    if is_us:
        if v >= 1e9: return f"${v/1e9:,.2f}B"
        if v >= 1e6: return f"${v/1e6:,.0f}M"
        return f"${v:,.0f}"
    if v >= 1e12: return f"{v/1e12:,.1f}조"
    if v >= 1e8:  return f"{v/1e8:,.0f}억"
    return f"{v:,.0f}원"

def _leader_fmt_mom(v):
    if v is None:
        return "—", "#64748b"
    color = "#e11d48" if v > 0 else ("#2563eb" if v < 0 else "#64748b")  # 한국 관례: 상승=빨강
    return f"{v:+.1f}%", color

def _leader_callout_html(top, label):
    is_us = top['is_us']
    mom_txt, mom_col = _leader_fmt_mom(top['mom'])
    return (
        "<div style='border:1px solid #fcd34d;background:linear-gradient(135deg,#fffbeb,#fef3c7);"
        "border-radius:14px;padding:14px 16px;margin:6px 0 10px;'>"
        f"<div style='font-size:12px;font-weight:800;color:#b45309;letter-spacing:.3px;'>🥇 {label} 대장주</div>"
        f"<div style='font-size:21px;font-weight:800;color:#0f172a;margin:2px 0 6px;'>{top['name']} "
        f"<span style='font-size:13px;color:#94a3b8;font-weight:600;'>{top['ticker']}</span></div>"
        "<div style='font-size:13px;color:#334155;line-height:1.7;'>"
        f"현재가 <b>{_leader_fmt_price(top['price'], is_us)}</b> &nbsp;·&nbsp; "
        f"20일 <b style='color:{mom_col};'>{mom_txt}</b> &nbsp;·&nbsp; "
        f"거래대금 <b>{_leader_fmt_big(top['amt'], is_us)}</b> &nbsp;·&nbsp; "
        f"시총 <b>{_leader_fmt_big(top['cap'], is_us)}</b> &nbsp;·&nbsp; "
        f"대장주 점수 <b style='color:#b45309;'>{top['score']:.1f}</b></div>"
        "</div>"
    )

def _leaders_table_html(rows):
    head = (
        "<table style='width:100%;border-collapse:collapse;font-size:13px;'>"
        "<thead><tr style='background:rgba(100,116,139,0.08);'>"
        "<th style='padding:7px 8px;text-align:center;'>순위</th>"
        "<th style='padding:7px 8px;text-align:left;'>종목명</th>"
        "<th style='padding:7px 8px;text-align:right;'>현재가</th>"
        "<th style='padding:7px 8px;text-align:right;'>20일 모멘텀</th>"
        "<th style='padding:7px 8px;text-align:right;'>거래대금(20일 평균)</th>"
        "<th style='padding:7px 8px;text-align:right;'>시가총액</th>"
        "<th style='padding:7px 8px;text-align:left;'>대장주 점수</th>"
        "</tr></thead><tbody>"
    )
    body = []
    for row in rows:
        is_us = row['is_us']
        medal = _LEADER_MED.get(row['rank'], f"<b>{row['rank']}</b>")
        mom_txt, mom_col = _leader_fmt_mom(row['mom'])
        surge_tag = " 🔥" if row['surge'] else ""
        row_bg = "background:rgba(245,158,11,0.10);" if row['rank'] == 1 else ""
        bar_w = max(2.0, min(100.0, row['score']))
        score_cell = (
            "<div style='display:flex;align-items:center;gap:6px;'>"
            "<div style='flex:1;height:7px;background:#e2e8f0;border-radius:4px;overflow:hidden;min-width:56px;'>"
            f"<div style='width:{bar_w:.0f}%;height:100%;background:linear-gradient(90deg,#f59e0b,#d97706);'></div></div>"
            f"<span style='font-weight:700;color:#b45309;min-width:36px;text-align:right;'>{row['score']:.1f}</span></div>"
        )
        body.append(
            f"<tr style='border-bottom:1px solid #eef2f7;{row_bg}'>"
            f"<td style='padding:7px 8px;text-align:center;font-size:15px;'>{medal}</td>"
            f"<td style='padding:7px 8px;'><b>{row['name']}</b> "
            f"<span style='color:#94a3b8;font-size:11px;'>{row['ticker']}</span>{surge_tag}</td>"
            f"<td style='padding:7px 8px;text-align:right;'>{_leader_fmt_price(row['price'], is_us)}</td>"
            f"<td style='padding:7px 8px;text-align:right;color:{mom_col};font-weight:700;'>{mom_txt}</td>"
            f"<td style='padding:7px 8px;text-align:right;'>{_leader_fmt_big(row['amt'], is_us)}</td>"
            f"<td style='padding:7px 8px;text-align:right;'>{_leader_fmt_big(row['cap'], is_us)}</td>"
            f"<td style='padding:7px 8px;min-width:150px;'>{score_cell}</td>"
            "</tr>"
        )
    return head + "".join(body) + "</tbody></table>"

def render_theme_leaders(results_list, tab_key):
    """검색한 테마의 대장주(1위)와 그 뒤 순위를 시장별로 표시."""
    ranked = _theme_leader_ranking(results_list)
    present = [(k, lab) for k, lab in [("KR", "🇰🇷 국내"), ("US", "🇺🇸 미국")] if ranked.get(k)]
    if not present:
        return
    st.markdown("### 🏆 테마 대장주 랭킹")
    st.caption("💡 **대장주 점수** = 거래대금(45%) · 시가총액(25%) · 20일 모멘텀(20%) · 자금 유입 강도(10%)를 "
               "각 시장 안에서 종합한 값입니다. 돈이 몰리고 대표성이 큰(=테마를 주도하는) 종목일수록 높습니다.")
    blocks = st.columns(len(present)) if len(present) == 2 else [st.container()]
    for col, (mkt, lab) in zip(blocks, present):
        rows = ranked[mkt]
        with col:
            st.markdown(f"**{lab} 대장주 순위 · {len(rows)}종목**")
            st.markdown(_leader_callout_html(rows[0], lab), unsafe_allow_html=True)
            st.markdown(_leaders_table_html(rows), unsafe_allow_html=True)
    st.caption("※ 대장주 판단은 시세·거래대금·모멘텀 기반의 참고 지표이며, 투자 권유가 아닙니다. "
               "시가총액은 상장주식수 데이터가 있는 종목만 표시됩니다.")
    st.divider()


def display_sorted_results(results_list, tab_key, api_key="", show_leader_rank=False):
    if not results_list:
        st.info("조건에 부합하는 종목이 없습니다.")
        return
        
    st.success(f"🎯 총 {len(results_list)}개 종목 포착 완료!")

    # [추가] 테마 대장주 랭킹 — 메가트렌드/국민성장펀드 등 '테마 대장주 발굴' 탭에서만 표시
    if show_leader_rank:
        render_theme_leaders(results_list, tab_key)
    
    _has_score = any(('_score' in r) for r in results_list)
    
    # --- 🌟 [추가됨] 시장 필터 및 정렬 옵션을 2열로 깔끔하게 배치 ---
    col_f1, col_f2 = st.columns(2)
    with col_f1:
        market_filter = st.radio("🌍 시장 필터", ["전체 보기", "🇰🇷 국내 주식만", "🇺🇸 미국 주식만"], horizontal=True, key=f"market_filter_{tab_key}")
    with col_f2:
        _sort_opts = (["🏆 스캔 점수 높은순"] if _has_score else []) + \
                     ["기본 (검색순)", "RSI 낮은순 (바닥줍기)", "기관 연속 순매수 긴 순서",
                      "🤖 AI 적정주가 괴리율 높은순", "🏦 컨센서스 괴리율 높은순"]
        sort_opt = st.radio("⬇️ 결과 정렬 방식", _sort_opts, horizontal=True, key=f"sort_radio_{tab_key}")
    
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

    # 괴리율 헬퍼 (목표가 ÷ 현재가 − 1) — 산출 불가 종목은 맨 뒤로
    def _gap(res, key):
        try:
            _t = float(str(res.get(key)))
            _c = float(res.get('현재가', 0))
            if _t > 0 and _c > 0:
                return (_t / _c) - 1.0
        except Exception:
            pass
        return -999.0

    # 2. 정렬 방식 적용
    if "스캔 점수" in sort_opt:
        sorted_res = sorted(display_list, key=lambda x: (x.get('_score', 0), -float(x.get('RSI', 100) or 100)), reverse=True)
    elif "RSI 낮은순" in sort_opt: 
        sorted_res = sorted(display_list, key=lambda x: x['RSI'])
    elif "기관 연속" in sort_opt: 
        sorted_res = sorted(display_list, key=lambda x: x.get('기관연속순매수', 0), reverse=True)
    elif "AI 적정주가" in sort_opt:
        sorted_res = sorted(display_list, key=lambda x: _gap(x, 'AI목표가'), reverse=True)
    elif "컨센서스" in sort_opt:
        sorted_res = sorted(display_list, key=lambda x: _gap(x, '목표가_컨센서스'), reverse=True)
    else: 
        sorted_res = display_list

    # --- 💾 [NEW] 결과 한눈에 보기 표 + CSV 다운로드 ---
    _export_cols = ['종목명', '티커', '시장', '섹터', '스캔점수', '충족조건', '현재가', '상태', '배열상태', '주봉추세',
                    'RSI', '진입가_가이드', '목표가1', '목표가2', '목표가3', '손절가',
                    'AI목표가', '목표가_컨센서스', 'PER', 'PBR', '기관수급', '외인수급']
    _export_rows = []
    for _r in sorted_res:
        _row = {c: _r.get(c) for c in _export_cols if c in _r}
        for _numc in ('현재가', '진입가_가이드', '목표가1', '목표가2', '목표가3', '손절가', 'AI목표가', 'RSI'):
            if _numc in _row and _row[_numc] is not None:
                try: _row[_numc] = round(float(_row[_numc]), 2)
                except Exception: pass
        _export_rows.append(_row)
    _export_df = pd.DataFrame(_export_rows)
    _dl_col1, _dl_col2 = st.columns([3, 1], vertical_alignment="center")
    with _dl_col1:
        st.caption(f"📋 정렬 결과 {len(sorted_res)}개 — 아래 카드는 상위 {min(len(sorted_res), 20)}개만 표시됩니다. (전체는 표/CSV로 확인)")
    with _dl_col2:
        st.download_button("💾 결과 CSV 저장", _export_df.to_csv(index=False).encode('utf-8-sig'),
                           file_name=f"스캔결과_{datetime.now().strftime('%Y%m%d_%H%M')}.csv", mime="text/csv",
                           use_container_width=True, key=f"scan_csv_{tab_key}")
    def _prc_fullres():
        st.dataframe(_export_df, use_container_width=True, hide_index=True, height=min(420, 40 + 35 * len(_export_df)))
    _register_popup(f"fullres_{tab_key}", _prc_fullres)
    _popup_button(f"📑 전체 결과 표로 보기 ({len(sorted_res)}개)", f"fullres_{tab_key}", f"📑 전체 결과 표 ({len(sorted_res)}개)", key=f"btn_fullres_{tab_key}")

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

    # 3. 최종 결과 카드 출력 — ⚡ 렌더링 부하 방지: 상위 20개만 카드, 나머지는 위 표에서 확인
    _MAX_CARDS = 20
    for i, res in enumerate(sorted_res[:_MAX_CARDS]):
        # (스캔 점수 캡션은 카드 사이마다 반복되어 가독성을 해쳐 제거. 점수/충족조건은 위의 전체 결과 표·CSV에 그대로 있음)
        draw_stock_card(res, api_key_str=api_key, is_expanded=False, key_suffix=f"{tab_key}_{i}")
    if len(sorted_res) > _MAX_CARDS:
        st.info(f"⚡ 화면 성능을 위해 카드형 상세 보기는 상위 {_MAX_CARDS}개까지만 표시했습니다. 나머지 {len(sorted_res) - _MAX_CARDS}개는 위의 '전체 결과 표' 또는 CSV에서 확인하세요. (정렬 방식을 바꾸면 카드에 올라오는 종목도 바뀝니다)")

# ============================================================
# 🧭 AI 통합 투자 발굴기 (Unified Finder) — 엔진
#   시장분위기 + 테마/정치 + 차트 + 펀더멘털 → 단기/중기/장기 자동 분류
#   * 무거운 분석(analyze_technical_pattern / get_value_metrics)은
#     파인더 전용 캐시 래퍼로 감싸 재실행/재렌더 시 재호출을 막는다.
# ============================================================

# NOTE: 스레드 내부에서 호출되므로 @st.cache_data 를 직접 달지 않는다.
#  (내부의 get_historical_data·get_investor_trend 등이 이미 캐시되어 재실행 시 빠르고,
#   파이프라인 결과는 session_state 에 보관해 재렌더 시 재계산하지 않는다.)
def _finder_tech(name, code):
    """파인더 전용: 기술적 분석 래퍼."""
    return analyze_technical_pattern(name, code)


def _finder_value(code):
    """파인더 전용: 가치/펀더멘털 지표 래퍼."""
    return get_value_metrics(code)


def _finder_risk(code):
    """파인더 전용: 공매도 + 신용(빚투) 리스크 통합 (국내 전용).
    반환 dict 예: {short_vol_ratio, short_bal_ratio, short_vol_trend, short_bal_trend,
                   level(emoji,text), credit_ratio} | None"""
    if not str(code).isdigit():
        return None
    out = {}
    try:
        s = get_short_selling_risk(code)
        if isinstance(s, dict):
            out.update(s)
    except Exception:
        pass
    try:
        c = get_credit_balance_naver(code)
        if isinstance(c, dict) and c.get("credit_ratio") is not None:
            out["credit_ratio"] = c["credit_ratio"]
    except Exception:
        pass
    return out or None


def _google_news_rss(query, limit=5):
    """구글 뉴스 RSS로 키워드 관련 최신 기사 수집(키 불필요, 차단 적음).
    반환: list[{title, link, date, source}]"""
    import xml.etree.ElementTree as ET
    from email.utils import parsedate_to_datetime
    q = (query or "").strip()
    if not q:
        return []
    try:
        url = ("https://news.google.com/rss/search?q=" + urllib.parse.quote(q)
               + "&hl=ko&gl=KR&ceid=KR:ko")
        res = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=5)
        if res.status_code != 200:
            return []
        root = ET.fromstring(res.content)
        out = []
        for it in root.iter("item"):
            title = (it.findtext("title") or "").strip()
            link = (it.findtext("link") or "").strip()
            if not title:
                continue
            src = ""
            src_el = it.find("source")
            if src_el is not None and src_el.text:
                src = src_el.text.strip()
            # 구글뉴스 제목은 거의 항상 "제목 - 언론사" 형태 → 끝의 언론사 제거
            if " - " in title:
                base, tail = title.rsplit(" - ", 1)
                title = base.strip()
                if not src:
                    src = tail.strip()
            date = ""
            pub = it.findtext("pubDate") or ""
            try:
                date = parsedate_to_datetime(pub).strftime("%Y-%m-%d")
            except Exception:
                date = pub[:16]
            out.append({"title": title.strip(), "link": link, "date": date, "source": src})
            if len(out) >= limit:
                break
        return out
    except Exception:
        return []


@st.cache_data(ttl=900, show_spinner=False)
def get_stock_news(code, name="", limit=5):
    """종목별 최신 뉴스 N건. 미국=yfinance(+구글RSS 폴백), 국내=네이버 모바일 API→구글 뉴스 RSS→HTML.
    반환: list[{title, link, date, source}]"""
    code = str(code).strip()
    is_us = not code.isdigit()
    items = []
    if is_us:
        try:
            raw = yf.Ticker(code).news or []
            for n in raw[:limit + 3]:
                content = n.get("content") if isinstance(n.get("content"), dict) else n
                title = content.get("title") or n.get("title")
                # 링크
                link = ""
                cu = content.get("canonicalUrl")
                if isinstance(cu, dict):
                    link = cu.get("url", "")
                if not link:
                    cl = content.get("clickThroughUrl")
                    if isinstance(cl, dict):
                        link = cl.get("url", "")
                link = link or n.get("link", "")
                # 출처
                src = ""
                prov = content.get("provider")
                if isinstance(prov, dict):
                    src = prov.get("displayName", "")
                src = src or n.get("publisher", "")
                # 날짜
                date = ""
                pub = content.get("pubDate") or content.get("displayTime")
                ts = n.get("providerPublishTime")
                if pub:
                    date = str(pub)[:10]
                elif ts:
                    try:
                        date = datetime.fromtimestamp(ts).strftime("%Y-%m-%d")
                    except Exception:
                        date = ""
                if title:
                    items.append({"title": str(title).strip(), "link": link,
                                  "date": date, "source": src})
                if len(items) >= limit:
                    break
        except Exception:
            pass
        if not items:   # yfinance 비면 구글 뉴스 RSS 폴백
            try:
                items = _google_news_rss(f"{name or code} stock", limit) or _google_news_rss(code, limit)
            except Exception:
                items = []
        return items[:limit]
    # 국내: ① 네이버 모바일 뉴스 JSON API → ② 구글 뉴스 RSS → ③ 데스크톱 HTML
    seen = set()
    # ① 모바일 JSON API
    try:
        data = _naver_json(f"https://m.stock.naver.com/api/news/stock/{code}?pageSize=20&page=1", timeout=3.5)
        groups = data if isinstance(data, list) else (
            data.get("newsList") if isinstance(data, dict) else None)
        if groups:
            for g in groups:
                cand = g.get("items") if (isinstance(g, dict) and isinstance(g.get("items"), list)) else ([g] if isinstance(g, dict) else [])
                for it in cand:
                    if not isinstance(it, dict):
                        continue
                    title = re.sub("<.*?>", "", str(it.get("title") or it.get("articleTitle") or "")).strip()
                    if not title or title in seen:
                        continue
                    office_id = it.get("officeId") or it.get("officeid")
                    article_id = it.get("articleId") or it.get("articleid")
                    link = it.get("linkUrl") or it.get("bodyUrl") or it.get("officeUrl") or ""
                    if not link and office_id and article_id:
                        link = f"https://n.news.naver.com/mnews/article/{office_id}/{article_id}"
                    dt = str(it.get("datetime") or it.get("dt") or "")
                    date = (f"{dt[0:4]}-{dt[4:6]}-{dt[6:8]}" if len(dt) >= 8 and dt[:8].isdigit() else dt[:10])
                    src = it.get("officeName") or it.get("office") or ""
                    body = re.sub(r"\s+", " ", re.sub("<.*?>", "", str(it.get("body") or it.get("bodyText") or ""))).strip()
                    seen.add(title)
                    items.append({"title": title, "link": link, "date": date,
                                  "source": src, "excerpt": body[:320]})
                    if len(items) >= limit:
                        break
                if len(items) >= limit:
                    break
    except Exception:
        pass
    # ② 구글 뉴스 RSS 폴백 (회사명 기반, 키 불필요)
    if not items:
        for q in ([f"{name} 주가", name] if name else [code]):
            g = _google_news_rss(q, limit)
            if g:
                for n in g:
                    if n["title"] in seen:
                        continue
                    seen.add(n["title"])
                    items.append(n)
                break
    # ③ HTML 폴백 (셀렉터 완화 — 제목 셀의 모든 링크 허용)
    if not items:
        try:
            url = f"https://finance.naver.com/item/news_news.naver?code={code}&page=1"
            res = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=4)
            soup = BeautifulSoup(res.content.decode('euc-kr', 'replace'), 'html.parser')
            for a in soup.select("td.title a, .title a, a.tit"):
                title = a.get_text(strip=True)
                href = a.get("href", "")
                if not title or title in seen or not href:
                    continue
                link = ("https://finance.naver.com" + href) if href.startswith("/") else href
                tr = a.find_parent("tr")
                info = tr.select_one("td.info") if tr else None
                date_el = tr.select_one("td.date") if tr else None
                seen.add(title)
                items.append({
                    "title": title, "link": link,
                    "date": date_el.get_text(strip=True) if date_el else "",
                    "source": info.get_text(strip=True) if info else "",
                })
                if len(items) >= limit:
                    break
        except Exception:
            pass
    return items[:limit]


@st.cache_data(ttl=3600, show_spinner=False)
def fetch_article_excerpt(url, max_chars=320):
    """기사 본문 일부를 추출(베스트에포트). 실패 시 ''. 네이버 금융/뉴스·일반 언론사 모두 대응.
    여러 본문 컨테이너 선택자를 순차 시도하고, 없으면 페이지 전체 텍스트에서 발췌."""
    if not url or not str(url).startswith("http"):
        return ""
    try:
        res = requests.get(url, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}, timeout=3)
        if res.status_code != 200:
            return ""
        enc = (res.encoding or "").lower()
        if not enc or enc == "iso-8859-1":
            enc = res.apparent_encoding or "utf-8"
        html = res.content.decode(enc, "replace")
        soup = BeautifulSoup(html, "html.parser")
        for tag in soup(["script", "style", "iframe", "header", "footer", "nav", "aside", "form"]):
            tag.decompose()
        body = None
        for sel in ["#dic_area", "#newsct_article", ".newsct_article", "#news_read",
                    ".articleCont", "#articleBody", ".article_body", "#articeBody",
                    "#article-view-content-div", "#content"]:
            el = soup.select_one(sel)
            if el and len(el.get_text(strip=True)) > 80:
                body = el
                break
        text = (body.get_text(separator=" ", strip=True) if body
                else soup.get_text(separator=" ", strip=True))
        text = re.sub(r"\s+", " ", text).strip()
        # 흔한 잡음 컷
        text = re.sub(r"(무단\s*전재.*$|저작권자.*$|ⓒ.*$)", "", text).strip()
        return text[:max_chars]
    except Exception:
        return ""


@st.cache_data(ttl=1800, show_spinner=False)
def get_consensus_signal(code):
    """증권사 리포트 '목록'만으로 컨센서스 리비전을 근사(상세 미조회 → 빠름·국내 전용).
    제목의 상향/하향 키워드와 최근 35일 커버리지 빈도를 집계.
    반환: {revision_dir(상향/중립/하향), up, dn, report_count_30d, report_total} | None"""
    if not str(code).isdigit():
        return None
    try:
        url = f"https://finance.naver.com/research/company_list.naver?searchType=itemCode&itemCode={code}"
        res = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=4)
        soup = BeautifulSoup(res.content.decode("euc-kr", "replace"), "html.parser")
        table = soup.find("table", {"class": "type_1"})
        if not table:
            return None
        now = datetime.now()
        up = dn = recent = total = 0
        for tr in table.find_all("tr"):
            tds = tr.find_all("td")
            if len(tds) < 5:
                continue
            a = tds[1].find("a")
            if not a:
                continue
            title = a.text.strip()
            date_s = tds[4].text.strip()
            total += 1
            try:
                d = datetime.strptime(date_s, "%y.%m.%d")
                if (now - d).days <= 35:
                    recent += 1
            except Exception:
                pass
            if any(k in title for k in ["상향", "상향조정", "눈높이 상향", "목표가 상향", "목표주가 상향"]):
                up += 1
            if any(k in title for k in ["하향", "하향조정", "눈높이 하향", "목표가 하향", "목표주가 하향"]):
                dn += 1
        if total == 0:
            return None
        rev = "상향" if up > dn else ("하향" if dn > up else "중립")
        return {"revision_dir": rev, "up": up, "dn": dn,
                "report_count_30d": recent, "report_total": total}
    except Exception:
        return None


@st.cache_data(ttl=1800, show_spinner=False)
def get_finder_exclusion_set():
    """관리종목 + 투자경보(투자경고/위험/주의)·거래정지·정리매매 종목명 집합을 한 번에 수집.
    반환: (names_set, reason_map[name]=사유). 하드필터(후보 제외)용."""
    names, reason = set(), {}
    try:
        mgmt_df, alert_df = get_market_warnings()
    except Exception:
        return names, reason

    def _ingest(df, default_reason):
        if df is None or getattr(df, "empty", True):
            return
        name_col = next((c for c in df.columns if "종목" in str(c)), None)
        reason_col = next((c for c in df.columns if ("사유" in str(c)) or ("구분" in str(c)) or ("지정" in str(c))), None)
        if not name_col:
            return
        for _, row in df.iterrows():
            nm = re.sub(r"\s+", "", str(row[name_col])).strip()
            if not nm or nm == "종목명":
                continue
            rs = str(row[reason_col]).strip() if reason_col else default_reason
            names.add(nm)
            reason.setdefault(nm, rs or default_reason)

    _ingest(mgmt_df, "관리종목")
    _ingest(alert_df, "투자경보")
    return names, reason


@st.cache_data(ttl=900, show_spinner=False)
def classify_news_sentiment(_api_key, items):
    """종목별 '개별 기사 제목'을 AI가 호재/중립/악재로 판정하고 종목 단위로 집계.
    items: tuple of (code, name, articles_tuple) — articles_tuple은 (title, excerpt) 튜플들.
    반환: {code: {label, score(-2~2), confidence(0~1), auto_neutral(bool),
                  reason, article_labels: [(label, score), ...]}}  # 입력 기사 순서
    집계: 기사 score×신뢰가중(상1.0/중0.6/하0.3) 합산. 방향 일치도×신호강도로 종목 신뢰도를 내고,
    신뢰도가 낮거나 호·악재가 엇갈리면 종목 판정을 자동 중립(score 0)으로 만든다.
    제목뿐 아니라 본문 발췌까지 함께 보고 판정하므로 단순 제목 판정보다 정확하다."""
    if not _api_key or not items:
        return {}
    flat, lines, gid = [], [], 1   # flat: (gid, code, art_idx, title)
    for code, name, articles in items:
        for ai_idx, art in enumerate(articles):
            if isinstance(art, (list, tuple)):
                title = (art[0] or "").strip() if len(art) > 0 else ""
                excerpt = (art[1] or "").strip() if len(art) > 1 else ""
            else:
                title, excerpt = (art or "").strip(), ""
            if not title:
                continue
            flat.append((gid, code, ai_idx, title))
            body = f" — 본문: {excerpt}" if excerpt else ""
            lines.append(f"{gid}. [{name}] 제목: {title}{body}")
            gid += 1
    if not flat:
        return {}
    block = "\n".join(lines)
    prompt = (
        "너는 한국 주식 뉴스 애널리스트다. 아래 '개별 기사'(제목 + 본문 발췌)마다 그 종목 주가에 미칠 "
        "영향을 호재/중립/악재로 판정하라. 제목이 애매해도 본문 발췌의 사실(수주·실적·소송·증설·계약·"
        "규제·인수 등)을 근거로 판단하라.\n"
        "JSON 배열만 출력(설명·마크다운·코드펜스 금지). 각 원소는 "
        '{"i":번호,"label":"호재|중립|악재","score":정수,"conf":"상|중|하"}.\n'
        "score: 강한호재 2, 호재 1, 중립 0, 악재 -1, 강한악재 -2. "
        "conf(판정 확신도): 본문 근거가 분명하면 상, 보통이면 중, 모호·단순시황·전망성이면 하.\n\n"
        f"{block}"
    )
    art = {}   # gid -> (label, score, conf)
    try:
        raw = ask_gemini(prompt, _api_key)
        txt = (raw or "").strip().replace("```json", "").replace("```", "").strip()
        m = re.search(r"\[.*\]", txt, re.DOTALL)
        if m:
            txt = m.group(0)
        for it in json.loads(txt):
            if not isinstance(it, dict):
                continue
            i = it.get("i")
            if i is None:
                continue
            label = str(it.get("label", "중립")).strip()
            if label not in ("호재", "중립", "악재"):
                label = "중립"
            try:
                sc = max(-2, min(2, int(round(float(it.get("score", 0))))))
            except Exception:
                sc = {"호재": 1, "악재": -1}.get(label, 0)
            conf = str(it.get("conf", "중")).strip()
            if conf not in ("상", "중", "하"):
                conf = "중"
            art[int(i)] = (label, sc, conf)
    except Exception:
        art = {}

    W = {"상": 1.0, "중": 0.6, "하": 0.3}
    grouped = {}   # code -> [(gid, title), ...]
    for gid_, code, ai_idx, title in flat:
        grouped.setdefault(code, []).append((gid_, title))

    out = {}
    for code, lst in grouped.items():
        article_labels, contrib = [], []
        pos_w = neg_w = 0.0
        dom = (0.0, "")   # (영향 크기, 제목)
        for gid_, title in lst:
            label, sc, conf = art.get(gid_, ("중립", 0, "중"))
            article_labels.append((label, sc))
            w = W.get(conf, 0.6)
            contrib.append(sc * w)
            if sc > 0:
                pos_w += w
            elif sc < 0:
                neg_w += w
            mag = abs(sc) * w
            if mag > dom[0]:
                dom = (mag, title)
        n = len(lst)
        total = sum(contrib)
        avg = total / n if n else 0.0
        denom = pos_w + neg_w
        agreement = abs(pos_w - neg_w) / denom if denom > 0 else 0.0   # 1=한 방향, 0=엇갈림
        strength = min(1.0, abs(avg))
        confidence = round(agreement * strength, 2)
        if denom == 0 or confidence < 0.35:
            label, score, auto = "중립", 0, True
            reason = "기사 신호가 약하거나 호·악재가 엇갈려 중립 처리"
        else:
            score = max(-2, min(2, int(round(avg))))
            if score == 0:
                score = 1 if total > 0 else -1
            label = "호재" if score > 0 else "악재"
            auto = False
            reason = (f"‘{dom[1][:28]}…’ 등 기사 근거" if dom[1] else "")
        out[code] = {"label": label, "score": score, "confidence": confidence,
                     "auto_neutral": auto, "reason": reason, "article_labels": article_labels}
    return out


def _short_trend_figure(risk):
    """공매도 추세 미니차트(거래비중 막대 + 잔고비중 선). 데이터 없으면 None."""
    if not isinstance(risk, dict):
        return None
    vser = risk.get("short_vol_series") or []
    bser = risk.get("short_bal_series") or []
    if not vser and not bser:
        return None
    fig = go.Figure()
    if vser:
        fig.add_trace(go.Bar(
            x=[d for d, _ in vser], y=[v for _, v in vser],
            name="공매도 거래비중(%)", marker_color="rgba(239,68,68,0.40)",
            hovertemplate="%{x}<br>거래비중 %{y:.1f}%<extra></extra>"))
    if bser:
        fig.add_trace(go.Scatter(
            x=[d for d, _ in bser], y=[v for _, v in bser],
            name="공매도 잔고비중(%)", yaxis="y2", mode="lines",
            line=dict(color="#b91c1c", width=2),
            hovertemplate="%{x}<br>잔고비중 %{y:.2f}%<extra></extra>"))
    fig.update_layout(
        height=180, margin=dict(l=8, r=8, t=8, b=8),
        showlegend=True,
        legend=dict(orientation="h", yanchor="bottom", y=1.02, x=0, font=dict(size=10)),
        yaxis=dict(tickfont=dict(size=9), title=None),
        yaxis2=dict(overlaying="y", side="right", showgrid=False, tickfont=dict(size=9)),
        xaxis=dict(tickfont=dict(size=9), nticks=6),
        bargap=0.25, hovermode="x unified",
    )
    return fig


def get_market_mood():
    """시장 분위기 종합 → dict(light, title, desc, risk_on[-1~1], vix, fng, breadth...).
    risk_on: 위험선호도. +1에 가까울수록 공격적(단기 모멘텀 우호), -1에 가까울수록 방어적(장기/가치 우호)."""
    mood = {
        "light": "🟡", "title": "중립", "desc": "",
        "risk_on": 0.0, "vix": None, "fng": None, "fng_rating": None,
        "kospi": None, "kosdaq": None, "breadth_up": None,
    }
    try:
        reg = get_market_regime()
        l, t, d = reg.get("verdict", ("🟡", "중립", ""))
        mood["light"], mood["title"], mood["desc"] = l, t, d
        for k in ("KOSPI", "KOSDAQ"):
            v = reg.get(k)
            if isinstance(v, dict):
                mood[k.lower()] = {"price": v.get("price"), "pct": v.get("pct"),
                                   "align": v.get("align"), "light": v.get("light")}
        b = reg.get("breadth")
        if isinstance(b, dict):
            mood["breadth_up"] = b.get("up_ratio")
    except Exception:
        pass
    try:
        macro = get_macro_indicators()
        if macro and macro.get("VIX"):
            mood["vix"] = round(float(macro["VIX"]["value"]), 1)
    except Exception:
        pass
    try:
        fg = get_fear_and_greed()
        if fg:
            mood["fng"] = fg.get("score")
            mood["fng_rating"] = fg.get("rating")
    except Exception:
        pass
    # 위험선호(risk-on) 점수 [-1, 1] 합성
    s = 0.0
    s += {"🟢": 0.6, "🔴": -0.6}.get(mood["light"], 0.0)
    if mood["vix"] is not None:
        if mood["vix"] < 16: s += 0.2
        elif mood["vix"] > 25: s -= 0.3
    if mood["breadth_up"] is not None:
        if mood["breadth_up"] >= 60: s += 0.2
        elif mood["breadth_up"] <= 40: s -= 0.2
    if mood["fng"] is not None:
        if mood["fng"] >= 65: s += 0.1
        elif mood["fng"] <= 30: s -= 0.1
    mood["risk_on"] = max(-1.0, min(1.0, round(s, 2)))
    return mood


@st.cache_data(ttl=900, show_spinner=False)
def get_theme_politics_radar(_api_key, news_titles=None, poly_lines=None):
    """뉴스 헤드라인 + 폴리마켓(정치/매크로)을 AI로 종합 →
    핵심 테마/이벤트(+권장 투자기간, 종목검색 키워드) + 한 줄 분위기 코멘트(JSON)."""
    fallback = {"mood_comment": "", "themes": []}
    if not _api_key:
        return fallback
    news_block = "\n".join(f"- {t}" for t in (news_titles or [])[:18]) or "(뉴스 없음)"
    poly_block = "\n".join(f"- {p}" for p in (poly_lines or [])[:10]) or "(예측시장 없음)"
    prompt = (
        "너는 한국 주식시장 전략가다. 아래 '실시간 국내 증시 뉴스 헤드라인'과 "
        "'글로벌 예측시장(정치·매크로) 확률'을 종합해, 지금 시장을 움직이는 핵심 테마/이벤트를 도출하라.\n\n"
        f"[증시 뉴스]\n{news_block}\n\n[예측시장]\n{poly_block}\n\n"
        "아래 JSON만 출력하라(설명·마크다운·코드펜스 금지):\n"
        '{"mood_comment":"오늘 시장 분위기 한 줄 요약",'
        '"themes":[{"theme":"테마명","horizon":"단기|중기|장기",'
        '"reason":"왜 지금 부각되는지 한 문장","keywords":"종목 검색용 핵심 키워드"}]}\n'
        "규칙: themes 는 3~5개. horizon 은 그 테마 성격상 가장 적합한 투자기간 하나로 정하라. "
        "정치/정책/단발 이벤트성→단기, 산업 사이클·실적 모멘텀→중기, 구조적 성장·저평가 재평가→장기."
    )
    try:
        raw = ask_gemini(prompt, _api_key)
        txt = (raw or "").strip().replace("```json", "").replace("```", "").strip()
        m = re.search(r"\{.*\}", txt, re.DOTALL)
        if m:
            txt = m.group(0)
        data = json.loads(txt)
        if isinstance(data, dict) and isinstance(data.get("themes"), list):
            clean = []
            for it in data["themes"][:5]:
                if not isinstance(it, dict):
                    continue
                hz = str(it.get("horizon", "")).strip()
                hz = hz if hz in ("단기", "중기", "장기") else "중기"
                clean.append({
                    "theme": str(it.get("theme", "")).strip()[:40],
                    "horizon": hz,
                    "reason": str(it.get("reason", "")).strip()[:140],
                    "keywords": str(it.get("keywords", it.get("theme", ""))).strip()[:60],
                })
            return {"mood_comment": str(data.get("mood_comment", "")).strip()[:180],
                    "themes": clean}
    except Exception:
        pass
    return fallback


@st.cache_data(ttl=600, show_spinner=False)
def get_news_issue_impact(_api_key, news_titles, top_n=3):
    """[뉴스 이슈 → 영향 관계] 실시간 헤드라인 + 구글 검색 그라운딩으로 '오늘의 핵심 증시 이슈
    TOP N'을 선별·요약하고, 각 이슈가 어떤 업종/종목에 호재(긍정)·악재(부정)·중립으로
    작용하는지 '영향 관계'를 JSON으로 생성한다.
    반환: {"issues":[{rank,title,summary,points[],sources[],
                     impacts[{target,kind,sentiment,reason,tickers[{name,code}]}]}],
           "generated_at":"HH:MM"}"""
    now_kst = datetime.utcnow() + timedelta(hours=9)
    fallback = {"issues": [], "generated_at": now_kst.strftime("%H:%M")}
    if not _api_key:
        return fallback
    head_block = "\n".join(f"- {t}" for t in (news_titles or [])[:25]) or "(헤드라인 없음)"
    prompt = (
        "너는 한국 주식시장 전략가다. 지금 한국 증시에서 가장 영향력 있는 핵심 뉴스 이슈를 선별하고, "
        "각 이슈가 어떤 업종/종목에 호재(긍정)·악재(부정)·중립으로 작용하는지 '영향 관계'를 정리하라.\n"
        "반드시 '구글 검색'으로 오늘 시점의 최신 보도를 직접 확인한 뒤 작성하라.\n\n"
        f"[참고용 실시간 증시 헤드라인]\n{head_block}\n\n"
        f"아래 JSON만 출력하라(설명·마크다운·코드펜스 금지). 이슈는 영향력 큰 순으로 정확히 {int(top_n)}개:\n"
        '{"issues":[{'
        '"title":"이슈 제목(12자 내외 핵심 명사구)",'
        '"summary":"무슨 일인지 + 증시에 왜 중요한지 2~3문장. \'~해요\' 체로 부드럽게.",'
        '"points":["주목할 포인트 1","2","3"],'
        '"sources":["실제 참고한 언론사명1","언론사명2"],'
        '"impacts":[{"target":"영향받는 업종 또는 테마/종목","kind":"섹터|종목|자산",'
        '"sentiment":"긍정|부정|중립","reason":"왜 그렇게 영향받는지 한 문장",'
        '"tickers":[{"name":"대표 종목명","code":"6자리 코드(모르면 빈 문자열)"}]}]'
        '}]}\n'
        "규칙: 1) impacts 는 이슈당 2~5개, 호재와 악재를 균형 있게 포함. "
        "2) tickers 는 각 영향마다 1~3개 한국 상장 대표주, code 는 6자리 숫자를 정확히(불확실하면 빈 문자열). "
        "3) sources 는 실제 검색에서 확인한 매체명만(과장 금지). "
        "4) 정치·정책·수급·실적·매크로 등 '증시에 직접 영향 주는' 이슈만. 연예/스포츠 등 비증시 이슈 제외."
    )
    try:
        raw = ask_gemini(prompt, _api_key, grounding=True)
        txt = (raw or "").strip().replace("```json", "").replace("```", "").strip()
        m = re.search(r"\{.*\}", txt, re.DOTALL)
        if m:
            txt = m.group(0)
        data = json.loads(txt)
        issues_in = data.get("issues") if isinstance(data, dict) else None
        if not isinstance(issues_in, list):
            return fallback
        _SENT_OK = {"긍정", "부정", "중립"}
        clean_issues = []
        for i, it in enumerate(issues_in[:int(top_n)]):
            if not isinstance(it, dict):
                continue
            title = str(it.get("title", "")).strip()[:40]
            if not title:
                continue
            impacts = []
            for im in (it.get("impacts") or [])[:6]:
                if not isinstance(im, dict):
                    continue
                tgt = str(im.get("target", "")).strip()[:24]
                if not tgt:
                    continue
                sent = str(im.get("sentiment", "")).strip()
                sent = sent if sent in _SENT_OK else "중립"
                tks = []
                for tk in (im.get("tickers") or [])[:3]:
                    if isinstance(tk, dict):
                        nm = str(tk.get("name", "")).strip()[:20]
                        cd = re.sub(r"\D", "", str(tk.get("code", "")))[:6]
                        if nm:
                            tks.append({"name": nm, "code": cd})
                impacts.append({
                    "target": tgt,
                    "kind": (str(im.get("kind", "섹터")).strip()[:6] or "섹터"),
                    "sentiment": sent,
                    "reason": str(im.get("reason", "")).strip()[:120],
                    "tickers": tks,
                })
            srcs = [str(s).strip()[:24] for s in (it.get("sources") or []) if str(s).strip()][:12]
            clean_issues.append({
                "rank": i + 1,
                "title": title,
                "summary": str(it.get("summary", "")).strip()[:400],
                "points": [str(p).strip()[:120] for p in (it.get("points") or []) if str(p).strip()][:5],
                "sources": srcs,
                "impacts": impacts,
            })
        return {"issues": clean_issues, "generated_at": now_kst.strftime("%H:%M")}
    except Exception:
        return fallback


# ---------- 점수화 보조 ----------
def _f_num(x):
    try:
        return float(str(x).replace(",", "").replace("%", "").strip())
    except Exception:
        return None


def _align_flags(tech):
    a = str(tech.get("배열상태", ""))
    return {"정배열": "정배열" in a, "골든": "골든크로스" in a, "역배열": "역배열" in a}


def _is_pos_flow(x):
    return "+" in str(x)


def _clip(v, lo=0.0, hi=100.0):
    return max(lo, min(hi, v))


def macro_tilt_for(sector, macro):
    """매크로 지표(환율·금리·SOX·유가·VIX)의 방향을 종목 '섹터'에 대입해 틸트 점수 산출.
    반환: (points(-12~12), notes[]). macro = get_macro_indicators() 결과."""
    if not macro:
        return 0.0, []
    S = str(sector or "")
    has = lambda *kw: any(k in S for k in kw)
    pts, notes = 0.0, []

    def d(name):
        m = macro.get(name)
        return (m.get("delta") if isinstance(m, dict) else None)

    fx, ust, sox, wti = d("원/달러 환율"), d("美 10년물 국채"), d("필라델피아 반도체"), d("WTI 원유")
    vix_m = macro.get("VIX") if isinstance(macro.get("VIX"), dict) else None

    # 환율: 원화 약세(상승) → 수출주 우호 / 내수·항공 부담
    if fx is not None:
        if fx > 0:
            if has("반도체", "전자", "IT", "기술", "디스플레이", "자동차", "조선", "기계", "소재"):
                pts += 6; notes.append("원화약세 수혜(수출)")
            if has("항공", "여행", "유통", "소매", "음식료", "호텔", "레저", "필수"):
                pts -= 4; notes.append("원화약세 부담(내수/항공)")
        elif fx < 0:
            if has("항공", "여행", "유통", "소매"):
                pts += 3
            if has("반도체", "자동차", "조선"):
                pts -= 2
    # 금리: 상승 → 금융 우호 / 성장·리츠 부담
    if ust is not None:
        if ust > 0:
            if has("은행", "금융", "보험", "증권", "지주"):
                pts += 6; notes.append("금리상승 수혜(금융)")
            if has("바이오", "제약", "의약", "리츠", "부동산", "소프트", "인터넷", "게임", "이차", "2차", "배터리", "유틸"):
                pts -= 4; notes.append("금리상승 부담(성장/리츠)")
        elif ust < 0:
            if has("바이오", "소프트", "인터넷", "게임", "이차", "2차", "배터리"):
                pts += 3; notes.append("금리하락 수혜(성장)")
            if has("은행", "보험"):
                pts -= 2
    # 반도체 업황(SOX)
    if sox is not None:
        if sox > 0 and has("반도체", "전자", "IT", "기술", "장비", "디스플레이"):
            pts += 5; notes.append("반도체 업황 강세")
        elif sox < 0 and has("반도체", "전자"):
            pts -= 3
    # 유가
    if wti is not None:
        if wti > 0:
            if has("정유", "에너지", "화학", "석유", "가스", "조선"):
                pts += 5; notes.append("유가상승 수혜")
            if has("항공", "운송", "해운"):
                pts -= 4; notes.append("유가상승 부담(항공/운송)")
        elif wti < 0:
            if has("항공", "운송", "해운"):
                pts += 3
            if has("정유", "에너지"):
                pts -= 2
    # 변동성(VIX): 공포 국면 → 방어주 선호
    if vix_m:
        lvl, up = vix_m.get("value"), (vix_m.get("delta") or 0) > 0
        if lvl is not None and (lvl > 25 or up):
            if has("음식료", "필수", "유틸", "전력", "통신", "담배"):
                pts += 4; notes.append("위험회피 방어주 선호")
            if has("게임", "인터넷", "소프트", "이차", "2차", "배터리", "바이오"):
                pts -= 3
    return max(-12.0, min(12.0, pts)), notes[:3]


def macro_regime_notes(macro):
    """매크로 방향을 시장 배너용 한 줄 메모 리스트로 요약."""
    if not macro:
        return []
    out = []

    def d(name):
        m = macro.get(name)
        return (m.get("delta") if isinstance(m, dict) else None)

    fx, ust, sox, wti = d("원/달러 환율"), d("美 10년물 국채"), d("필라델피아 반도체"), d("WTI 원유")
    vix_m = macro.get("VIX") if isinstance(macro.get("VIX"), dict) else None
    if fx is not None:
        out.append("📈 원화 약세 → 수출주(반도체·자동차) 우호" if fx > 0 else "📉 원화 강세 → 내수주 우호")
    if ust is not None:
        out.append("📈 금리 상승 → 금융 우호·성장/리츠 부담" if ust > 0 else "📉 금리 하락 → 성장주 우호")
    if sox is not None and sox > 0:
        out.append("🔥 반도체 업황 강세")
    if wti is not None:
        out.append("🛢️ 유가 상승 → 정유·조선 우호/항공 부담" if wti > 0 else "🛢️ 유가 하락 → 항공·운송 우호")
    if vix_m and (vix_m.get("value", 0) or 0) > 25:
        out.append("⚠️ 변동성 확대 → 방어주 선호")
    return out


def score_one(tech, vm, mood, theme_hit=False, risk=None, news_sent=None,
              sector_tilt=0.0, consensus=None, dilution=False):
    """한 종목의 단기/중기/장기 적합도(0~100) 산출 + 자동 분류 + 사유.
    공매도/신용(빚투) 리스크가 있으면 감점(단기>중기>장기 순). AI 뉴스 판정(news_sent:-2~2)도
    점수에 반영(단기에 가장 크게). 반환: (scores, horizon, top, grade, reasons, risk_flags)"""
    al = _align_flags(tech)
    rsi = _f_num(tech.get("RSI"))
    vol_spike = "터짐" in str(tech.get("거래량 급증", ""))
    status = str(tech.get("상태", ""))
    near_entry = "타점 근접" in status
    over_ext = "이격 과다" in status
    broke = "이탈" in status
    weekly_up = "상승추세" in str(tech.get("주봉추세", ""))
    f_pos = _is_pos_flow(tech.get("외인수급"))
    i_pos = _is_pos_flow(tech.get("기관수급"))
    pension = int(tech.get("연기금연속순매수", 0) or 0)

    per = (vm or {}).get("per")
    if per is None:
        per = _f_num(tech.get("PER"))
    pbr = (vm or {}).get("pbr")
    if pbr is None:
        pbr = _f_num(tech.get("PBR"))
    roe = (vm or {}).get("roe")
    div = (vm or {}).get("div")
    debt = (vm or {}).get("debt")
    mom3 = (vm or {}).get("mom3")
    mom6 = (vm or {}).get("mom6")
    off_high = (vm or {}).get("off_high")

    r_s, r_m, r_l = [], [], []

    # ===== 단기(스윙/모멘텀) =====
    s = 0.0
    if al["정배열"]: s += 25; r_s.append("정배열")
    elif al["골든"]: s += 20; r_s.append("골든크로스")
    elif al["역배열"]: s -= 18
    if vol_spike: s += 16; r_s.append("거래량 급증")
    if near_entry: s += 14; r_s.append("매수타점 근접")
    elif over_ext: s += 2
    elif broke: s -= 10
    if f_pos and i_pos: s += 18; r_s.append("외인·기관 쌍끌이")
    elif f_pos or i_pos: s += 8; r_s.append("수급 유입")
    if pension >= 3: s += 7; r_s.append(f"기관 {pension}일 연속매수")
    if rsi is not None:
        if 50 <= rsi <= 68: s += 10
        elif 40 <= rsi < 50 or 68 < rsi <= 78: s += 5
        elif rsi > 82: s -= 8
        elif rsi < 28: s -= 3
    if mom3 is not None:
        s += min(8.0, mom3 / 5.0) if mom3 > 0 else -5.0
    s += 8.0 * max(0.0, mood["risk_on"])      # 위험선호일 때 단기 가산
    if theme_hit: s += 8; r_s.append("주도 테마")
    short = _clip(s)

    # ===== 중기(추세+테마+합리적 밸류) =====
    m = 0.0
    if weekly_up: m += 25; r_m.append("주봉 상승추세")
    if al["정배열"]: m += 12; r_m.append("정배열 유지")
    elif al["골든"]: m += 8
    if mom6 is not None and mom3 is not None:
        if mom6 > 0 and mom3 > 0:
            m += 18; r_m.append("3·6개월 동반 상승")
            if mom3 > 60: m -= 8                 # 단기 과열 감점
        elif mom6 < -15:
            m -= 8
    if theme_hit: m += 20; r_m.append("주도 테마 편입")
    if per is not None:
        if 0 < per <= 25: m += 8
        elif per > 40: m -= 3
    if pbr is not None and pbr <= 4: m += 5
    if f_pos or i_pos: m += 8; r_m.append("수급 우호")
    if roe is not None and roe >= 8: m += 6
    m += 4.0 * mood["risk_on"]
    mid = _clip(m)

    # ===== 장기(가치+퀄리티+인컴) =====
    l = 0.0
    if per is not None:
        if 0 < per <= 10: l += 25; r_l.append(f"저PER {per:.0f}")
        elif per <= 15: l += 18; r_l.append(f"PER {per:.0f}")
        elif per <= 25: l += 8
        elif per > 40: l -= 5
    if pbr is not None:
        if pbr <= 1.0: l += 20; r_l.append(f"저PBR {pbr:.2f}")
        elif pbr <= 1.5: l += 12; r_l.append(f"PBR {pbr:.2f}")
        elif pbr <= 3: l += 5
    if roe is not None:
        if roe >= 15: l += 18; r_l.append(f"고ROE {roe:.0f}%")
        elif roe >= 10: l += 10; r_l.append(f"ROE {roe:.0f}%")
    if div is not None:
        if div >= 4: l += 12; r_l.append(f"고배당 {div:.1f}%")
        elif div >= 2: l += 7; r_l.append(f"배당 {div:.1f}%")
    if debt is not None:
        if debt <= 100: l += 8
        elif debt > 180: l -= 5
    if off_high is not None and off_high <= -30 and not al["역배열"]:
        l += 10; r_l.append("고점대비 낙폭(저평가)")
    if weekly_up or al["정배열"]: l += 8
    elif al["역배열"]: l -= 10
    if theme_hit: l += 5
    l -= 6.0 * max(0.0, mood["risk_on"])      # 위험선호↑ → 장기 가치 매력 상대적↓
    l += 6.0 * max(0.0, -mood["risk_on"])     # 위험회피 구간 → 장기 가산
    longs = _clip(l)

    # ===== 공매도 / 신용(빚투) 리스크 감점 =====
    # 단기에 가장 큰 하방 압력, 중기 중간, 장기는 상대적으로 영향 작게 반영.
    risk_flags = []
    if isinstance(risk, dict) and risk:
        ps = pm = pl = 0.0
        sbr = risk.get("short_bal_ratio")      # 공매도 잔고 비중(%)
        svr = risk.get("short_vol_ratio")      # 당일 공매도 거래 비중(%)
        cr = risk.get("credit_ratio")          # 신용잔고율(%)
        if sbr is not None:
            if sbr >= 3.0: ps += 12; pm += 8; pl += 4; risk_flags.append(f"🩸공매도잔고 {sbr:.1f}%")
            elif sbr >= 1.5: ps += 6; pm += 4; pl += 2
        if svr is not None:
            if svr >= 20: ps += 10; pm += 5; risk_flags.append(f"🩸당일공매도 {svr:.0f}%")
            elif svr >= 10: ps += 5; pm += 2
        # 공매도 추세 증가 = 추가 하방
        if str(risk.get("short_vol_trend", "")).startswith("📈") or str(risk.get("short_bal_trend", "")).startswith("📈"):
            ps += 4; pm += 2
            if "🩸공매도↑" not in risk_flags:
                risk_flags.append("🩸공매도↑")
        if cr is not None:
            if cr >= 10: ps += 8; pm += 5; pl += 2; risk_flags.append(f"⚠️신용잔고 {cr:.1f}%")
            elif cr >= 5: ps += 4; pm += 2
        short = _clip(short - ps)
        mid = _clip(mid - pm)
        longs = _clip(longs - pl)

    # ===== AI 뉴스 호재/악재 반영 (단기 영향 가장 큼) =====
    if news_sent is not None:
        try:
            ns = max(-2, min(2, int(news_sent)))
        except Exception:
            ns = 0
        if ns != 0:
            short = _clip(short + ns * 6)
            mid = _clip(mid + ns * 3)
            longs = _clip(longs + ns * 1)

    # ===== 컨센서스 리비전 (목표가 괴리 + 상/하향) =====
    target = _f_num(tech.get("목표가_컨센서스"))
    cur = _f_num(tech.get("현재가"))
    upside = ((target / cur) - 1) * 100 if (target and cur and cur > 0) else None
    cs = ms = ls = 0.0
    if upside is not None:
        if upside >= 30:
            ms += 10; ls += 8; cs += 6; r_m.append(f"기대수익 +{upside:.0f}%"); r_l.append(f"목표가 괴리 +{upside:.0f}%")
        elif upside >= 15:
            ms += 6; ls += 5; cs += 3; r_m.append(f"기대수익 +{upside:.0f}%")
        elif upside < 0:
            ms -= 4; ls -= 4; cs -= 3   # 주가가 컨센 목표가 위 → 과열
    if isinstance(consensus, dict):
        rev = consensus.get("revision_dir")
        if rev == "상향":
            cs += 6; ms += 5; r_s.append("목표가 상향"); r_m.append("목표가 상향")
        elif rev == "하향":
            cs -= 6; ms -= 4
        if (consensus.get("report_count_30d") or 0) >= 2:
            ms += 2
    short = _clip(short + cs); mid = _clip(mid + ms); longs = _clip(longs + ls)

    # ===== 매크로 → 섹터 틸트 (단기·중기 위주) =====
    if sector_tilt:
        short = _clip(short + sector_tilt)
        mid = _clip(mid + sector_tilt * 0.7)
        longs = _clip(longs + sector_tilt * 0.2)
        if sector_tilt >= 4:
            r_s.append("매크로 순풍(섹터)")
        elif sector_tilt <= -4:
            r_s.append("매크로 역풍(섹터)")

    # ===== 증자/CB 희석 리스크 (뉴스 감지 시) =====
    if dilution:
        short = _clip(short - 14)
        mid = _clip(mid - 8)
        longs = _clip(longs - 6)

    # ===== [전문가 보강] 시장 상대강도(RS)·52주 신고가·MFI·이격/유동성/변동성 =====
    is_kr = str(tech.get("티커", "")).isdigit()
    _idx20 = mood.get("_idx20") if isinstance(mood, dict) else None
    _iret = (_idx20 or {}).get("kr" if is_kr else "us")
    _sret = _f_num(tech.get("수익률20일"))
    rs20 = (_sret - _iret) if (_sret is not None and _iret is not None) else None
    if rs20 is not None:                      # 시장 대비 20일 초과수익(%p) — 오닐式 상대강도
        if rs20 >= 7:
            short = _clip(short + 8); mid = _clip(mid + 5)
            r_s.append(f"시장대비 강세 RS +{rs20:.0f}%p"); r_m.append(f"상대강도 우위 +{rs20:.0f}%p")
        elif rs20 >= 3:
            short = _clip(short + 4)
        elif rs20 <= -7:
            short = _clip(short - 7); mid = _clip(mid - 4)
    off52 = _f_num(tech.get("고점대비52주"))
    if off52 is not None:                     # 신고가 근접 = 주도주 모멘텀
        if off52 >= -3:
            short = _clip(short + 7); mid = _clip(mid + 7)
            r_s.append("52주 신고가권"); r_m.append("52주 신고가권(주도주)")
        elif off52 >= -10:
            mid = _clip(mid + 4)
    mfi = _f_num(tech.get("MFI"))
    if mfi is not None:                       # 거래량 가중 자금흐름
        if 55 <= mfi <= 80:
            mid = _clip(mid + 4); r_m.append(f"자금 유입(MFI {mfi:.0f})")
        elif mfi > 85:
            short = _clip(short - 5); risk_flags.append(f"🌡️MFI 과열 {mfi:.0f}")
        elif mfi < 20:
            short = _clip(short - 2)
    gap20 = _f_num(tech.get("이격도20"))
    if gap20 is not None and gap20 >= 18:     # 20일선 과이격 = 추격매수 위험
        short = _clip(short - 8); risk_flags.append(f"🌡️20일선 이격 +{gap20:.0f}%")
    vol20 = _f_num(tech.get("변동성20일"))
    if vol20 is not None and vol20 >= 4.5:    # 일변동성 과대
        short = _clip(short - 4); risk_flags.append(f"🎢고변동성 {vol20:.1f}%/일")
    amt20 = _f_num(tech.get("평균거래대금20일"))
    if is_kr and amt20 is not None:           # 유동성 필터(국내): 20일 평균 거래대금
        _eok = amt20 / 1e8
        if _eok < 10:
            short = _clip(short - 12); mid = _clip(mid - 8); longs = _clip(longs - 4)
            risk_flags.append(f"💧유동성 부족({_eok:.0f}억/일)")
        elif _eok < 30:
            short = _clip(short - 5); mid = _clip(mid - 3)

    scores = {"단기": round(short, 1), "중기": round(mid, 1), "장기": round(longs, 1)}
    ranked = sorted(scores.items(), key=lambda kv: kv[1], reverse=True)
    horizon = ranked[0][0]
    # 근소차(≤6점)는 시장 분위기로 타이브레이크
    if len(ranked) >= 2 and (ranked[0][1] - ranked[1][1]) <= 6:
        if mood["risk_on"] >= 0.3: pref = ["단기", "중기", "장기"]
        elif mood["risk_on"] <= -0.3: pref = ["장기", "중기", "단기"]
        else: pref = ["중기", "단기", "장기"]
        cand = [k for k, _ in ranked[:2]]
        horizon = min(cand, key=lambda k: pref.index(k))
    top = scores[horizon]
    reasons = {"단기": r_s, "중기": r_m, "장기": r_l}[horizon][:4]
    if top >= 70: grade = "🟢 강력"
    elif top >= 50: grade = "🟡 양호"
    else: grade = "⚪ 약함"
    return scores, horizon, round(top, 1), grade, reasons, risk_flags


@st.cache_data(ttl=900, show_spinner=False)
def get_index_ret20():
    """시장 상대강도(RS) 기준선: 코스피·S&P500의 최근 20거래일 수익률(%). 실패 항목은 None."""
    out = {"kr": None, "us": None}
    for key, sym in (("kr", "KS11"), ("us", "US500")):
        try:
            s = fdr.DataReader(sym, (datetime.now() - timedelta(days=70)).strftime("%Y-%m-%d"))["Close"].dropna()
            if len(s) >= 21:
                out[key] = round(float(s.iloc[-1] / s.iloc[-21] - 1) * 100, 2)
        except Exception:
            pass
    return out


# ── [발굴기 표시 보조] 손익비(R:R) · 필터/정렬 · 내보내기 유틸 ──────────────
def _finder_rr(r):
    """현재가 진입 기준 손익비(R:R)와 상/하방 %.
    R:R = (목표가1 − 현재가) ÷ (현재가 − 손절가). 반환 {rr, up, dn, tag} | None."""
    cur = _f_num(r.get("현재가")); tgt = _f_num(r.get("목표가1")); stop = _f_num(r.get("손절가"))
    if not (cur and tgt and stop) or cur <= 0:
        return None
    dn = (cur - stop) / cur * 100.0        # 손절까지 하방 %
    up = (tgt - cur) / cur * 100.0         # 1차 목표까지 상방 %
    risk = cur - stop
    rr = ((tgt - cur) / risk) if risk > 0 else None
    tag = ("손절선 이탈" if risk <= 0 else ("목표 도달(과열)" if up <= 0 else None))
    return {"rr": rr, "up": up, "dn": dn, "tag": tag}

def _finder_hide(r, hide_bad_news, hide_risk, hide_illiq):
    """필터 토글에 따라 이 종목을 숨길지 여부."""
    flags = r.get("_risk_flags") or []
    if hide_bad_news and r.get("_news_label") == "악재" and not r.get("_news_auto_neutral"):
        return True
    if hide_illiq and any("💧" in f for f in flags):
        return True
    if hide_risk:
        if r.get("_dilution"):
            return True
        if any(("🩸" in f) or ("⚠️" in f) for f in flags):
            return True
        lvl = (r.get("_risk") or {}).get("level")
        if isinstance(lvl, (list, tuple)) and lvl and "🔴" in str(lvl[0]):
            return True
    return False

def _finder_sort_val(r, mode):
    """정렬 기준값(내림차순 사용). 값이 없으면 맨 뒤로 밀리도록 매우 작은 값."""
    if mode.startswith("기대수익"):
        v = r.get("_upside");                 return v if v is not None else -1e9
    if mode.startswith("손익비"):
        v = (_finder_rr(r) or {}).get("rr");  return v if v is not None else -1e9
    if "모멘텀" in mode:
        v = _f_num(r.get("수익률20일"));       return v if v is not None else -1e9
    return r.get("_top", 0)                    # 기본: 기간 적합도 점수

def _finder_export_df(buckets):
    """단기/중기/장기 버킷 → 내보내기용 DataFrame(분석 전체)."""
    rows = []
    for hz in ("단기", "중기", "장기"):
        for rk, r in enumerate(buckets.get(hz, []), 1):
            _rr = _finder_rr(r) or {}
            _cons = r.get("_consensus") or {}
            _lvl = (r.get("_risk") or {}).get("level")
            _risk_txt = ((_lvl[0] if isinstance(_lvl, (list, tuple)) and _lvl else "")
                         + " " + " ".join(r.get("_risk_flags") or [])).strip()
            rows.append({
                "기간분류": hz, "순위": rk,
                "등급": re.sub(r"[🟢🟡⚪]", "", str(r.get("_grade") or "")).strip(),
                "적합도점수": r.get("_top"), "종목명": r.get("종목명"), "티커": r.get("티커"),
                "시장": r.get("시장", ""), "테마/섹터": (r.get("_theme") or r.get("섹터") or ""),
                "현재가": round(_f_num(r.get("현재가")) or 0, 2),
                "RSI": (round(_f_num(r.get("RSI")), 1) if _f_num(r.get("RSI")) is not None else None),
                "20일수익률(%)": _f_num(r.get("수익률20일")),
                "52주고점대비(%)": _f_num(r.get("고점대비52주")),
                "기대수익_컨센(%)": (round(r.get("_upside"), 1) if r.get("_upside") is not None else None),
                "목표가리비전": _cons.get("revision_dir", ""),
                "손익비(R:R)": (round(_rr.get("rr"), 2) if _rr.get("rr") is not None else None),
                "진입가": round(_f_num(r.get("진입가_가이드")) or 0, 2),
                "목표가1": round(_f_num(r.get("목표가1")) or 0, 2),
                "목표가2": round(_f_num(r.get("목표가2")) or 0, 2),
                "목표가3": round(_f_num(r.get("목표가3")) or 0, 2),
                "손절가": round(_f_num(r.get("손절가")) or 0, 2),
                "공매도/신용": _risk_txt,
                "뉴스판정": r.get("_news_label", ""),
                "핵심근거": " · ".join(r.get("_reasons") or []),
            })
    return pd.DataFrame(rows)


def build_finder_candidates(api_key, scope, theme_focus, radar_themes, kr_n, us_n, want_long):
    """후보 풀 구성: ① 시총 상위 기술 유니버스 ② 테마 리더(사용자키워드+AI레이더) ③ 가치 후보.
    반환: dict  code -> {"name":str, "theme":str|None, "src":set}"""
    pool = {}

    def add(name, code, theme=None, src="tech"):
        code = str(code).strip()
        name = str(name).strip()
        if not code or not name:
            return
        if is_kr_etf_etn(name, code):   # ETF·ETN·상품 제외 (차트 기술분석 비대상)
            return
        if scope == "kr" and not code.isdigit():   # 국내 전용 모드면 미국 티커 제외
            return
        if scope == "us" and code.isdigit():        # 미국 전용 모드면 국내 티커 제외
            return
        if code not in pool:
            pool[code] = {"name": name, "theme": theme, "src": {src}}
        else:
            pool[code]["src"].add(src)
            if theme and not pool[code]["theme"]:
                pool[code]["theme"] = theme

    # ① 기술 유니버스 (시가총액/거래대금 상위)
    if scope in ("kr", "kr_us"):
        try:
            for nm, cd in (get_scan_targets(kr_n) or []):
                add(nm, cd, src="tech")
        except Exception:
            pass
    if scope in ("kr_us", "us"):
        try:
            for nm, cd in (get_us_scan_targets(us_n) or []):
                add(nm, cd, src="tech")
        except Exception:
            pass

    # ② 테마 리더 (사용자 키워드 + AI 레이더 상위 2개 테마) — 검색쿼리/표시명 분리
    theme_jobs = []  # (검색쿼리, 표시명)
    if theme_focus and theme_focus.strip():
        theme_jobs.append((theme_focus.strip(), theme_focus.strip()))
    for t in (radar_themes or [])[:2]:
        disp = (t.get("theme") or t.get("keywords") or "").strip()
        kw = (t.get("keywords") or t.get("theme") or "").strip()
        if kw:
            theme_jobs.append((kw, disp or kw))
    seen_q = set()
    for q, disp in theme_jobs:
        if q in seen_q:
            continue
        seen_q.add(q)
        try:
            for nm, cd in (get_theme_stocks_with_ai(q, api_key) or []):
                add(nm, cd, theme=disp, src="theme")
        except Exception:
            pass

    # ③ 가치 후보 (장기/자동 포함 시, 국내 전용 데이터 → 국내 포함 모드에서만)
    if want_long and scope in ("kr", "kr_us"):
        try:
            for nm, cd in (get_longterm_value_stocks_with_ai(
                    "저평가 우량 가치주(저PER·저PBR·고ROE·재무안정 + 주주환원)",
                    "대/중/소형 상관없음", api_key) or []):
                add(nm, cd, src="value")
        except Exception:
            pass

    return pool


def get_finder_briefing(_api_key, mood, radar, bucket_tops):
    """시장분위기 + 테마 + 기간별 상위픽을 묶어 '오늘의 통합 전략 브리핑' 생성."""
    if not _api_key:
        return ""
    lines = []
    for hz in ("단기", "중기", "장기"):
        picks = bucket_tops.get(hz) or []
        if picks:
            lines.append(f"[{hz}] " + ", ".join(f"{n}({s:.0f}점)" for n, s in picks[:3]))
    picks_block = "\n".join(lines) or "(선별된 종목 없음)"
    themes_block = ", ".join(t["theme"] for t in (radar.get("themes") or [])[:5]) or "-"
    prompt = (
        "너는 여의도 시니어 전략가다. 아래 데이터로 개인투자자용 '오늘의 통합 투자 전략'을 한국어로 작성하라.\n"
        f"- 시장국면: {mood['light']} {mood['title']} (위험선호 {mood['risk_on']:+.2f}, "
        f"VIX {mood.get('vix')}, 공포탐욕 {mood.get('fng')})\n"
        f"- 핵심 테마: {themes_block}\n"
        f"- 기간별 상위 후보:\n{picks_block}\n\n"
        "형식:\n"
        "1) 한 줄 총평(지금 시장 성격과 대응 톤)\n"
        "2) 단기/중기/장기 각각 1~2문장 대응 전략(왜 이 분위기에서 그 기간이 유효/불리한지 포함)\n"
        "3) 리스크 관리 한 줄\n"
        "과장 금지, 투자 권유가 아닌 참고 정보임을 전제. 불릿/번호로 간결하게."
    )
    try:
        return ask_gemini(prompt, _api_key)
    except Exception:
        return ""


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

    # 실시간 현재 날짜·시간 (KST) — 브라우저에서 초 단위로 갱신, 모든 페이지에서 표시
    components.html(
        """
        <div id="kst-clock" style="
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
            background: linear-gradient(135deg, #1e293b, #334155);
            color: #e2e8f0; border: 1px solid #475569; border-radius: 10px;
            padding: 10px 12px; text-align: center; margin: 2px 0 8px 0;">
            <div style="font-size: 12px; color:#94a3b8; letter-spacing:0.5px;">🇰🇷 한국 시간 (KST)</div>
            <div id="kst-date" style="font-size: 15px; font-weight:600; margin-top:3px;">--</div>
            <div id="kst-time" style="font-size: 22px; font-weight:700; font-variant-numeric: tabular-nums; color:#f8fafc;">--:--:--</div>
        </div>
        <script>
        function updateKST() {
            const now = new Date();
            // 사용자 로컬과 무관하게 KST(UTC+9) 고정 계산
            const kst = new Date(now.getTime() + (now.getTimezoneOffset() * 60000) + (9 * 3600000));
            const days = ['일','월','화','수','목','금','토'];
            const y = kst.getFullYear();
            const mo = String(kst.getMonth()+1).padStart(2,'0');
            const d = String(kst.getDate()).padStart(2,'0');
            const dow = days[kst.getDay()];
            const h = String(kst.getHours()).padStart(2,'0');
            const mi = String(kst.getMinutes()).padStart(2,'0');
            const s = String(kst.getSeconds()).padStart(2,'0');
            const de = document.getElementById('kst-date');
            const te = document.getElementById('kst-time');
            if (de) de.textContent = `${y}.${mo}.${d} (${dow})`;
            if (te) te.textContent = `${h}:${mi}:${s}`;
        }
        updateKST();
        setInterval(updateKST, 1000);
        </script>
        """,
        height=92,
    )

    menu_options = [
        "📂 [ 홈 & 자산 관리 ]",
        " ┣ 🎛️ 홈: 종합 대시보드",
        " ┣ 💼 내 계좌 & 포트폴리오 진단",
        " ┗ ⭐ 내 관심종목 모니터링",
        " ", 
        "📂 [ 퀀트 스캐너 & 종목 발굴 ]",
        " ┣ 🔬 개별 기업 정밀 진단 (AI 비전)",
        " ┣ 🧭 AI 통합 투자 발굴기 (테스트)",
        " ┣ 🚀 단기 스윙 퀀트 스캐너",
        " ┣ 💎 장기 우량주 & 가치주 발굴",
        " ┣ 📉 낙폭과대 스캐너 (고점대비 -30%↓)",
        " ┣ 🏛️ 국민연금 5% 대량보유 픽",
        " ┣ ⚡ 메가트렌드 & 테마 대장주",
        " ┣ 🇰🇷 국민성장펀드 12대 산업 수혜주",
        " ┗ 📋 코스피·코스닥 종목 리스트",
        "  ", 
        "📂 [ 시장 흐름 & 매크로 ]",
        " ┣ 🌍 글로벌 매크로 & AI 분석 (v6.0)",
        " ┣ 🗺️ 시장 주도주 자금 히트맵",
        " ┣ 🕸️ 실시간 섹터 순환매 추적",
        " ┣ 🔥 지금 뜨는 섹터 (국장·미장)",
        " ┣ 💰 국장 수급 분석 (외국인·기관·개인)",
        " ┣ 📅 핵심 증시 일정 & IPO 달력",
        " ┗ 🔮 폴리마켓 예측시장 (금리·경제·정치)",
        "   ", 
        "📂 [ 트레이딩 & 시장 경보 ]",
        " ┣ 🗞️ 뉴스 이슈 TOP & 영향 분석",
        " ┣ 🚨 통합 경보 센터 (뉴스·차트·일정)",
        " ┣ 🔥 간밤의 미국 급등주 & 수혜주",
        " ┣ 🚨 당일 상/하한가 분석",
        " ┣ 🚦 거래량 급증 & 시장 경보",
        " ┗ 📰 실시간 특징주 속보 & 리포트",
        "    ", 
        "📂 [ 심층 분석 & 도구 ]",
        " ┣ 👴 노후 준비 ETF 시뮬레이터 (v2.0)",
        " ┣ 📊 국내외 핵심 ETF 분석",
        " ┣ 💰 고배당주 파이프라인 (TOP 300)",
        " ┣ 🎯 증권사 목표가 컨센서스",
        " ┣ ⚖️ 적정 주가 계산기 (버핏 모델)",
        " ┗ 👁️ 차트 이미지 AI 비전 분석",
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


# === [포트폴리오 파일 업로드 파서] ===========================================
def parse_portfolio_upload(uploaded_file):
    """증권사 잔고 엑셀/CSV 또는 샘플 양식을 읽어 (DataFrame[종목명,진입단가,보유수량], 안내문) 반환.
    - 인코딩(utf-8/cp949)·구분자(쉼표/탭/세미콜론) 조합을 자동 시도해 '컬럼 매핑이 성공하는' 해석을 채택
    - 머리글 행 자동 탐색(파일 위쪽의 제목/계좌정보 줄 무시)
    - 컬럼 자동 매핑: 종목명·상품명 / 보유수량·잔고수량·수량 / 매입단가·평균단가·평단가 ...
    - 단가 컬럼이 없고 '매입금액'만 있으면 금액÷수량으로 환산
    - 종목코드가 있으면 KRX 정식 종목명으로 보정(엑셀에서 잘린 앞자리 0 복원)
    - 같은 종목 여러 줄(분할 매수)은 가중평균 단가로 자동 합산
    실패 시 ValueError(사용자 안내 메시지)를 발생시킨다."""
    import io as _io, re as _re

    def _norm(x):
        return _re.sub(r"[\s_()\[\]]", "", str(x)).lower()

    NAME_KEYS  = ["종목명", "상품명", "종목", "name", "ticker", "티커"]
    CODE_KEYS  = ["종목코드", "단축코드", "종목번호", "code", "symbol"]
    QTY_KEYS   = ["보유수량", "잔고수량", "결제잔고", "보유량", "주식수", "수량", "qty", "quantity", "shares"]
    PRICE_KEYS = ["진입단가", "매입단가", "평균단가", "평균매입가", "매입평균가", "평단가",
                  "매수단가", "매입가", "avgprice", "averageprice", "buyprice"]
    AMT_KEYS   = ["매입금액", "매수금액", "투자원금", "투자금액", "매입원금"]

    def _find_col(cols_norm, keys):
        for k in keys:
            kk = _norm(k)
            for i, c in enumerate(cols_norm):
                if kk and kk in c:
                    return i
        return None

    def _map_columns(df0):
        """머리글 행 탐색 + 컬럼 매핑. 성공 시 dict, 실패 시 None."""
        if df0 is None or df0.empty:
            return None
        for r in range(min(15, len(df0))):
            cells = [_norm(v) for v in df0.iloc[r].tolist()]
            has_name = any(any(_norm(k) in c for c in cells) for k in (NAME_KEYS + CODE_KEYS))
            has_qty  = any(any(_norm(k) in c for c in cells) for k in QTY_KEYS)
            if not (has_name and has_qty):
                continue
            header = ["" if v is None else str(v) for v in df0.iloc[r].tolist()]
            cn = [_norm(h) for h in header]
            i_name, i_code = _find_col(cn, NAME_KEYS), _find_col(cn, CODE_KEYS)
            i_qty = _find_col(cn, QTY_KEYS)
            i_price, i_amt = _find_col(cn, PRICE_KEYS), _find_col(cn, AMT_KEYS)
            if i_qty is None or (i_name is None and i_code is None):
                continue
            if i_price is None and i_amt is None:
                continue
            # 제목들이 한 칸에 뭉쳐 있으면(구분자 오인식) 이 해석은 무효
            if len({x for x in (i_name, i_code, i_qty, i_price, i_amt) if x is not None}) < 2:
                continue
            body = df0.iloc[r + 1:].reset_index(drop=True)
            body.columns = range(len(header))
            return dict(header=header, body=body, i_name=i_name, i_code=i_code,
                        i_qty=i_qty, i_price=i_price, i_amt=i_amt)
        return None

    fname = (getattr(uploaded_file, "name", "") or "").lower()
    raw = uploaded_file.getvalue()
    mapped = None
    if fname.endswith((".xlsx", ".xlsm", ".xls")):
        try:
            df0 = pd.read_excel(_io.BytesIO(raw), header=None, dtype=str)
        except Exception as e:
            raise ValueError(f"엑셀 파일을 여는 데 실패했습니다 ({e}). CSV로 저장해 다시 올려보세요.")
        mapped = _map_columns(df0)
    else:
        tried = set()
        for _enc in ("utf-8-sig", "cp949", "euc-kr", "utf-8", "latin1"):
            for _sep in (",", "\t", ";", "|"):
                try:
                    df0 = pd.read_csv(_io.BytesIO(raw), header=None, dtype=str, encoding=_enc,
                                      sep=_sep, engine="python", names=list(range(64)),
                                      skip_blank_lines=True)
                except Exception:
                    continue
                df0 = df0.dropna(axis=1, how="all")
                sig = (df0.shape, str(df0.head(2).values.tolist())[:300])
                if sig in tried:
                    continue
                tried.add(sig)
                mapped = _map_columns(df0)
                if mapped:
                    break
            if mapped:
                break
    if mapped is None:
        raise ValueError("머리글 행을 찾지 못했습니다. 첫 줄에 '종목명, 진입단가, 보유수량' 같은 "
                         "제목이 필요합니다. (옆의 샘플 양식을 받아 그대로 채우면 가장 쉽습니다)")

    header, body = mapped["header"], mapped["body"]
    i_name, i_code = mapped["i_name"], mapped["i_code"]
    i_qty, i_price, i_amt = mapped["i_qty"], mapped["i_price"], mapped["i_amt"]

    def _num(v):
        s = _re.sub(r"[,₩원\s$]", "", str(v))
        if s in ("", "-", "nan", "none", "None", "NaN"):
            return None
        try:
            return float(s)
        except Exception:
            return None

    krx = None
    try:
        krx = get_krx_stocks()
    except Exception:
        krx = None  # 시세망 문제 시에도 이름 기반으로는 계속 진행

    rows, skipped = [], 0
    for _, r in body.iterrows():
        qty = _num(r[i_qty])
        name = "" if i_name is None else str(r[i_name]).strip()
        code_raw = "" if i_code is None else str(r[i_code]).strip()
        if name.lower() in ("nan", "none"):
            name = ""
        if code_raw.lower() in ("nan", "none"):
            code_raw = ""
        if (qty is None or qty <= 0) and not name and not code_raw:
            continue  # 완전 빈 줄
        if qty is None or qty <= 0:
            skipped += 1  # 합계·예수금 등 수량 없는 줄
            continue
        price = _num(r[i_price]) if i_price is not None else None
        if (price is None or price <= 0) and i_amt is not None:
            amt = _num(r[i_amt])
            if amt and amt > 0:
                price = amt / qty
        if code_raw:  # 종목코드 → KRX 정식 종목명 보정 (앞자리 0 복원)
            digits = _re.sub(r"\D", "", code_raw)
            if digits and krx is not None and not krx.empty:
                code6 = digits.zfill(6)[-6:]
                hit = krx[krx["Code"].astype(str).str.zfill(6) == code6]
                if not hit.empty:
                    name = str(hit["Name"].iloc[0])
            if not name:
                name = code_raw  # 숫자 아닌 코드(미국 티커 등)는 그대로 사용
        if not name or price is None or price <= 0:
            skipped += 1
            continue
        rows.append({"종목명": name, "진입단가": round(float(price), 2), "보유수량": int(qty)})

    if not rows:
        raise ValueError("불러올 수 있는 보유 종목이 없습니다. 수량과 단가 값이 채워져 있는지 확인해 주세요.")

    out = pd.DataFrame(rows, columns=["종목명", "진입단가", "보유수량"])
    if out["종목명"].duplicated().any():  # 분할 매수 → 가중평균 합산
        out["_금액"] = out["진입단가"] * out["보유수량"]
        g = out.groupby("종목명", as_index=False).agg({"_금액": "sum", "보유수량": "sum"})
        g["진입단가"] = (g["_금액"] / g["보유수량"]).round(2)
        out = g[["종목명", "진입단가", "보유수량"]]

    used = []
    if i_name is not None:
        used.append(f"종목명←'{header[i_name]}'")
    if i_code is not None and i_code != i_name:
        used.append(f"종목코드←'{header[i_code]}'")
    used.append(f"수량←'{header[i_qty]}'")
    if i_price is not None:
        used.append(f"단가←'{header[i_price]}'")
    elif i_amt is not None:
        used.append(f"단가←'{header[i_amt]}'÷수량")
    msg = f"✅ {len(out)}개 종목을 불러왔습니다"
    if skipped:
        msg += f" (합계·빈 줄 등 {skipped}행 건너뜀)"
    msg += " · 인식한 컬럼: " + ", ".join(used)
    return out, msg
# === [/포트폴리오 파일 업로드 파서] ==========================================


# ==========================================
# 5. 메인 로직 
# ==========================================

# [속도개선 2순위] 실시간 페이지일 때만 5분 자동 새로고침 타이머를 등록한다.
#  그 외 페이지(계산기·시뮬레이터·스캐너·리스트 등)는 자동 rerun 되지 않아
#  불필요한 재요청/화면 튐/스크롤 점프가 사라진다. 페이지 추가/제외는 LIVE_REFRESH_PAGES 만 수정하면 된다.
# =====================================================================
# [신규] 퀀트 비서 — 전역 팝업(st.dialog). 어느 페이지에서나 작은 버튼으로 호출.
# =====================================================================
def _quant_assistant_body():
        try:
            macro_data = get_macro_indicators()
        except Exception:
            macro_data = None
        st.caption("장중 궁금한 시장 이슈나 신작 출시 일정 등을 퀀트 비서에게 직접 물어보세요.")

        chat_container = st.container(height=380)
        for msg in st.session_state.v4_chat_history:
            chat_container.chat_message(msg["role"]).write(msg["content"])

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
                # ── 종목 해석(국내): 프롬프트에서 종목명/6자리코드 추출 ──
                def _resolve_kr_stock(text):
                    try:
                        krx = get_krx_stocks()
                    except Exception:
                        return None, None
                    if krx is None or krx.empty:
                        return None, None
                    for m in re.findall(r"\d{6}", str(text)):
                        hit = krx[krx["Code"].astype(str).str.zfill(6) == m]
                        if not hit.empty:
                            return str(hit.iloc[0]["Name"]), m
                    best = None
                    for _, r in krx.iterrows():
                        nm = str(r["Name"]).strip()
                        if len(nm) >= 2 and nm in str(text):
                            if best is None or len(nm) > len(best[0]):
                                best = (nm, str(r["Code"]).zfill(6))
                    return (best[0], best[1]) if best else (None, None)

                # ── 앱의 '실데이터 함수'만으로 종목 팩트시트 구성(없는 값은 '데이터 없음') ──
                def _fmt(v, fmt=None, suf=""):
                    try:
                        if v is None or (isinstance(v, float) and pd.isna(v)):
                            return "데이터 없음"
                        return (fmt.format(v) if fmt else str(v)) + suf
                    except Exception:
                        return "데이터 없음"

                def _build_stock_factsheet(name, code):
                    L = [f"[검증된 실데이터 — {name} ({code}) · 출처: 시스템 수집(fdr·네이버)]"]
                    try:
                        t = analyze_technical_pattern(name, code)
                    except Exception:
                        t = None
                    if t:
                        L.append(f"- 현재가 {_fmt(t.get('현재가'),'{:,.0f}','원')} · 상태 {t.get('상태','데이터 없음')} · 거래량 {t.get('거래량 급증','데이터 없음')}")
                        L.append(f"- RSI {_fmt(t.get('RSI'),'{:.1f}')} · 이평배열 {t.get('배열상태','데이터 없음')} · 주봉추세 {t.get('주봉추세','데이터 없음')}")
                        L.append(f"- 20일선(진입가이드) {_fmt(t.get('진입가_가이드'),'{:,.0f}','원')} · 손절가 {_fmt(t.get('손절가'),'{:,.0f}','원')} · 목표가 {_fmt(t.get('목표가1'),'{:,.0f}')}/{_fmt(t.get('목표가2'),'{:,.0f}')}/{_fmt(t.get('목표가3'),'{:,.0f}')}")
                        L.append(f"- PER {t.get('PER','데이터 없음')} · PBR {t.get('PBR','데이터 없음')} · 증권사 컨센서스 목표가 {_fmt(t.get('목표가_컨센서스'),'{:,.0f}','원')}")
                        L.append(f"- 최근 거래일 수급: 기관 {_fmt(t.get('기관수급'))} · 외국인 {_fmt(t.get('외인수급'))} · 개인 {_fmt(t.get('개인수급'))}")
                        L.append(f"- 연속 순매수(일): 기관 {_fmt(t.get('기관연속순매수'))} · 외국인 {_fmt(t.get('외인연속순매수'))} · 연기금 {_fmt(t.get('연기금연속순매수'))}")
                    else:
                        L.append("- 기술적·수급·밸류에이션: 데이터 없음(시세 조회 실패)")
                    try:
                        c = get_consensus_signal(code)
                    except Exception:
                        c = None
                    if c:
                        L.append(f"- 증권사 리포트(최근35일): 방향 {c['revision_dir']}(상향 {c['up']}/하향 {c['dn']}) · 최근30일 {c['report_count_30d']}건/총 {c['report_total']}건")
                    else:
                        L.append("- 증권사 리포트 리비전: 데이터 없음")
                    try:
                        ns = get_stock_news(code, name, limit=5) or []
                    except Exception:
                        ns = []
                    if ns:
                        L.append("- 최신 뉴스(네이버):")
                        for n in ns[:5]:
                            tt = str(n.get("title", "")).strip()
                            if tt:
                                L.append(f"    · {tt}")
                    else:
                        L.append("- 최신 뉴스: 데이터 없음")
                    return "\n".join(L)

                with chat_container.chat_message("assistant"):
                    now_kst2 = datetime.utcnow() + timedelta(hours=9)
                    today_str = now_kst2.strftime("%Y년 %m월 %d일")
                    macro_context = "현재 거시경제: " + ", ".join([f"{k} {v['value']}" for k, v in macro_data.items()]) if macro_data else "데이터 없음"

                    with st.spinner("종목 실데이터(시세·수급·컨센서스·뉴스)를 확인하는 중..."):
                        s_name, s_code = _resolve_kr_stock(prompt)
                        factsheet = _build_stock_factsheet(s_name, s_code) if s_code else ""

                    if s_code:
                        sys_prompt = f"""당신은 여의도 최고의 주식 애널리스트입니다. 오늘 날짜는 {today_str}입니다.
아래 [검증된 실데이터]는 우리 시스템이 실제로 수집한 수치입니다. 여기에 더해 반드시 '구글 검색(Google Search)'을 실행해 최신 뉴스·공시·이벤트를 확인하세요.

[절대 규칙 — 위반 금지]
1) 답변의 모든 숫자·사실은 (a) 아래 [검증된 실데이터] 또는 (b) 방금 구글 검색으로 확인한 '출처 있는' 정보, 둘 중 하나여야 한다.
2) 학습 데이터에 의존한 추측·일반론·기억 속 수치 사용 금지. 특히 현재가·목표가·실적을 기억으로 지어내지 말 것.
3) 데이터에 없는 항목은 '데이터 없음'이라고 솔직히 쓰고, 빈칸을 그럴듯한 추정치로 메우지 말 것.
4) 견해(매수/관망/매도)는 반드시 위 검증 데이터에 근거해 '왜'를 설명할 것.

[검증된 실데이터]
{factsheet}

[매크로 환경] {macro_context}
[사용자 질문] {prompt}

애널리스트 수준으로 ①핵심 요약 ②기술적·수급 ③밸류에이션·컨센서스 ④최신 이슈(구글 검색) ⑤리스크 포함 균형 잡힌 견해 순서로, 검증된 사실만으로 답하라. 마지막 줄에 '※ 투자 조언이 아닌 참고용'을 적을 것."""
                    else:
                        sys_prompt = f"""당신은 여의도 퀀트 비서입니다. 오늘 날짜는 {today_str}입니다.
반드시 '구글 검색(Google Search)'을 실행해 최신 사실을 확인하고, 검색으로 확인된 '출처 있는' 정보만으로 답하라.
[절대 규칙] 학습 데이터에 의존한 추측·일반론·기억 속 수치 사용 금지. 확인 안 된 것은 '확인 불가'로 표기. 확정된 사실만 3~5줄로 요약.
[매크로 환경] {macro_context}
[사용자 질문] {prompt}"""

                    reply = None
                    grounded_ok = False
                    with st.spinner("구글 검색으로 최신 팩트를 교차 확인하는 중..."):
                        try:
                            response = _genai_generate(sys_prompt, api_key_input, grounding=True)
                            if response.candidates and response.candidates[0].content.parts:
                                reply = response.text
                                grounded_ok = True
                        except Exception:
                            grounded_ok = False

                    if not grounded_ok:
                        # 검색/그라운딩 실패 → 학습데이터로 지어내지 않는다(할루시네이션 방지).
                        if s_code and factsheet:
                            try:
                                strict = f"""아래는 우리 시스템이 수집한 '{s_name}({s_code})'의 검증된 실데이터다. 오늘은 {today_str}.
이 데이터 안의 사실만 사용해 애널리스트 요약을 작성하라. 데이터에 없는 수치·전망을 새로 지어내지 말고, 없으면 '데이터 없음'이라고 쓰라.
{factsheet}
[사용자 질문] {prompt}
마지막 줄에 '※ 실시간 검색 실패 — 시스템 실데이터 기준(최신 뉴스 일부 미반영), 투자 조언 아님'을 적을 것."""
                                reply = "⚠️ 실시간 구글 검색에 실패해, 시스템이 수집한 검증된 실데이터만으로 요약합니다.\n\n" + ask_gemini(strict, api_key_input)
                            except Exception:
                                reply = "⚠️ 검색과 요약에 모두 실패했습니다. 아래는 수집된 실데이터 원본입니다(미검증 추정 없음):\n\n" + factsheet
                        else:
                            reply = ("⚠️ 실시간 검색에 실패했습니다. 검증되지 않은(기억에 의존한) 답변을 드리지 않기 위해 응답을 보류합니다.\n"
                                     "잠시 후 다시 시도하시거나, 종목명을 정확히 포함해 질문해 주세요. (예: '삼성전자 어때?')")
                    st.write(reply)

                st.session_state.v4_chat_history.append({"role": "assistant", "content": reply})

if hasattr(st, "dialog"):
    @st.dialog("💬 퀀트 비서 · 실시간 검색 연동", width="large")
    def _quant_assistant_dialog():
        _quant_assistant_body()

def _open_quant_assistant():
    if hasattr(st, "dialog"):
        _quant_assistant_dialog()
    else:
        st.session_state["_qa_inline_open"] = True

def render_global_quant_button():
    _qa_sp, _qa_bt = st.columns([5, 2])
    with _qa_bt:
        if st.button("💬 퀀트 비서에게 묻기", key="global_qa_open", use_container_width=True,
                     help="어느 페이지에서나 시장·종목을 실시간 검색·질문하세요"):
            _open_quant_assistant()
    if not hasattr(st, "dialog") and st.session_state.get("_qa_inline_open"):
        with st.container(border=True):
            _qc1, _qc2 = st.columns([6, 1])
            _qc1.markdown("#### 💬 퀀트 비서")
            if _qc2.button("✕ 닫기", key="qa_inline_close"):
                st.session_state["_qa_inline_open"] = False
                st.rerun()
            _quant_assistant_body()


render_global_quant_button()

if selected_menu in LIVE_REFRESH_PAGES:
    st_autorefresh(interval=AUTOREFRESH_MS, limit=None, key="news_autorefresh")

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

    now_kst = datetime.utcnow() + timedelta(hours=9)
    st.markdown(
        f"""
        <div style="display:flex;align-items:baseline;justify-content:space-between;flex-wrap:wrap;margin-bottom:2px;">
          <span style="font-size:25px;font-weight:900;color:#0f172a;letter-spacing:-1px;">🖥️ 여의도 모닝 데스크</span>
          <span style="font-size:13px;color:#94a3b8;font-weight:600;">{now_kst.strftime('%Y.%m.%d')} ({['월','화','수','목','금','토','일'][now_kst.weekday()]}) {now_kst.strftime('%H:%M')} KST · 5분 자동 갱신</span>
        </div>
        <div style="font-size:13px;color:#64748b;margin-bottom:14px;">간밤 글로벌 → 오늘의 국면 → 지수·수급 → 자금 흐름 → 심리 → 일정 → 내 종목 순으로, 매매에 필요한 핵심만 모았습니다.</div>
        """,
        unsafe_allow_html=True,
    )

    # ── ① 오늘의 시장 국면 (결정 배너) ──
    with st.spinner("시장 국면 분석 중..."):
        render_regime_hero()

    # ── ② 간밤 글로벌 (오늘 국장 방향타) ──
    st.markdown("##### 🌙 간밤 글로벌 — 오늘 국장의 방향타")
    with st.spinner("간밤 미국 지수·금리·유가 수집 중..."):
        render_overnight_tape()
    st.caption("💡 VIX 급등·美 금리 급등·환율 급등 시엔 국장도 위험회피로 기울 수 있어, 좋은 종목이 있어도 보수적으로 접근하는 편이 유리합니다.")

    st.divider()

    # ── [이동] 📰 AI 모닝 브리핑 (간밤 글로벌 바로 아래로 배치) ──
    st.markdown("##### 📰 AI 모닝 브리핑 (Global → Local)")
    if api_key_input:
        with st.spinner("AI가 글로벌 매크로 데이터로 모닝 브리핑을 작성 중입니다..."):
            top_gainers_names = st.session_state.gainers_df['기업명'].tolist()[:5] if not st.session_state.gainers_df.empty else []
            briefing_text = get_daily_market_briefing(macro_data, top_gainers_names, api_key_input)
            nb_render_briefing(briefing_text, now_kst.strftime('%Y-%m-%d %H:%M'))
            st.caption("※ 본 브리핑은 24시간 단위로 캐시가 갱신됩니다.")
    else:
        st.warning("좌측 사이드바에 API 키를 입력하시면, AI가 작성하는 글로벌→국내 모닝 브리핑을 볼 수 있습니다.")

    st.divider()

    # ── ③ 코스피·코스닥 실시간 & 투자자별 수급 ──
    st.markdown("##### 📈 코스피·코스닥 실시간 & 수급 (외국인·기관·개인)")
    with st.spinner("지수·투자자별 수급 수집 중..."):
        render_main_index_panel()

    st.divider()

    # ── ④ 오늘의 자금 흐름: 시총 TOP & 업종 등락 ──
    st.markdown("##### 💰 오늘의 자금 흐름 (주도주·섹터)")
    # 헤더+컨트롤 행과 표 행을 분리 → 라디오 높이에 상관없이 두 표의 시작점이 자동 정렬됨(단차 제거)
    h_mc, h_ind = st.columns(2)
    with h_mc:
        st.markdown("**🏆 시가총액 TOP 10**")
        mc_market = st.radio("시장", ["KOSPI", "KOSDAQ"], horizontal=True,
                             label_visibility="collapsed", key="mcap_market_radio")
    with h_ind:
        st.markdown("**🔥 업종별 등락률 (강세 순)**")

    t_mc, t_ind = st.columns(2)
    with t_mc:
        with st.spinner("시가총액 상위 수집 중..."):
            render_marketcap_top(mc_market, 10)
    with t_ind:
        with st.spinner("업종별 등락 수집 중..."):
            render_industry_changes(12)

    st.divider()

    # ── ④-c 지금 뜨는 섹터 TOP5 (국장·미장) ──
    st.markdown("##### 🔥 지금 뜨는 섹터 TOP5")
    _sec_kr_col, _sec_us_col = st.columns(2)
    with _sec_kr_col:
        st.markdown("**🇰🇷 국장 TOP5**")
        with st.spinner("국장 섹터 분석 중..."):
            _sec_kr = get_trending_sectors("KR")
        if _sec_kr:
            render_trending_sectors(_sec_kr, limit=5)
        else:
            st.caption("국장 섹터 데이터를 일시적으로 불러오지 못했어요.")
    with _sec_us_col:
        st.markdown("**🇺🇸 미장 TOP5**")
        with st.spinner("미장 섹터 분석 중..."):
            _sec_us = get_trending_sectors("US")
        if _sec_us:
            render_trending_sectors(_sec_us, limit=5)
        else:
            st.caption("미장 섹터 데이터를 일시적으로 불러오지 못했어요.")
    st.caption("전체 테마는 좌측 **‘🔥 지금 뜨는 섹터 (국장·미장)’** 메뉴에서 확인하세요.")

    st.divider()

    # ── ④-b 거래량 급증·급감 TOP10 (국장) — 자세히는 경보 탭 ──
    st.markdown("##### 🔥 거래량 급증·급감 TOP10 (국장)")
    render_main_volume_top10()

    st.divider()

    # ── ⑤ 투자 심리 (VIX + 공포·탐욕) ──
    st.markdown("##### 🧭 투자 심리 (변동성·투자자 심리)")
    render_sentiment_strip(fg_data, macro_data)

    st.divider()

    # ── ⑥ 향후 1개월 핵심 매크로 일정 ──
    st.markdown("##### 🗓️ 향후 1개월 핵심 일정 (중앙은행·물가·경기·수급)")
    render_week_catalysts()

    st.divider()

    # ── ⑦ 내 관심종목 신호 (액션) ──
    st.markdown("##### 🚦 내 관심종목 신호 (손절·익절 자동 감시)")
    with st.spinner("관심종목 기술적 점검 중..."):
        render_watchlist_signals()



elif selected_menu == "💼 내 계좌 & 포트폴리오 진단":
    st.markdown("## 💼 내 계좌 & 포트폴리오 진단")
    st.write("현재 보유 중인 종목들을 표에 입력하면, 단순 개별 분석이 아닌 **계좌 전체의 자산 배분(비중)과 리스크를 고려한 종합 리밸런싱 전략**을 AI가 진단해 드립니다.")

    if "portfolio_df" not in st.session_state:
        st.session_state.portfolio_df = pd.DataFrame([{"종목명": "", "진입단가": 0, "보유수량": 0}])
    if "pf_editor_ver" not in st.session_state:
        st.session_state.pf_editor_ver = 0

    st.markdown("### 📊 1. 내 포트폴리오 입력")

    up_col, sample_col = st.columns([3, 2])
    with up_col:
        up_file = st.file_uploader(
            "📤 파일을 여기로 끌어다 놓으면 표가 한 번에 채워집니다 (엑셀/CSV)",
            type=["csv", "xlsx", "xlsm", "xls"],
            key="pf_upload",
            help="증권사(키움·미래에셋·삼성 등) 잔고 화면에서 내려받은 엑셀도 그대로 올리면 종목명·수량·매입단가 컬럼을 자동으로 찾아 읽습니다.",
        )
    with sample_col:
        st.caption("처음이라면 👇 샘플 양식을 받아 숫자만 바꿔 올리세요.")
        _sample_df = pd.DataFrame({
            "종목명": ["삼성전자", "SK하이닉스", "AAPL"],
            "진입단가": [71000, 180000, 210],
            "보유수량": [10, 5, 3],
        })
        st.download_button("📑 샘플 양식 받기 (CSV)", _sample_df.to_csv(index=False).encode("utf-8-sig"),
                           file_name="포트폴리오_샘플.csv", mime="text/csv", use_container_width=True)
        try:
            import io as _io
            _xbuf = _io.BytesIO()
            _sample_df.to_excel(_xbuf, index=False)
            st.download_button("📑 샘플 양식 받기 (엑셀)", _xbuf.getvalue(), file_name="포트폴리오_샘플.xlsx",
                               mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                               use_container_width=True)
        except Exception:
            pass  # openpyxl 미설치 환경에서는 CSV 샘플만 제공

    if up_file is not None:
        _file_key = (up_file.name, up_file.size)
        if st.session_state.get("pf_loaded_key") != _file_key:
            try:
                _pf_new, _pf_msg = parse_portfolio_upload(up_file)
                st.session_state.portfolio_df = _pf_new
                st.session_state.pf_loaded_key = _file_key
                st.session_state.pf_upload_msg = _pf_msg
                st.session_state.pf_editor_ver += 1
                st.rerun()
            except ValueError as _e:
                st.error(f"⚠️ {_e}")
            except Exception as _e:
                st.error(f"⚠️ 파일을 해석하지 못했습니다: {_e}")
    if st.session_state.get("pf_upload_msg"):
        st.success(st.session_state.pf_upload_msg)

    # 🔎 [NEW] 종목 검색해서 담기 (장바구니 방식) — 체크한 종목이 아래 표에 행으로 자동 추가됩니다.
    with st.container(border=True):
        st.markdown("**🔎 종목 검색해서 담기** — 검색 후 체크만 하면 아래 표에 자동으로 담깁니다. (담은 뒤 표에서 **단가·수량**만 입력하세요)")
        if "pf_search_query" not in st.session_state:
            st.session_state.pf_search_query = ""

        _s_cols = st.columns([4, 1], vertical_alignment="bottom")
        with _s_cols[0]:
            pf_search_input = st.text_input(
                "종목 검색", placeholder=" 🔍 검색어를 입력하세요. (예: 우주항공, 삼성전자, AAPL)",
                label_visibility="collapsed", key="pf_search_in").strip()
        with _s_cols[1]:
            pf_search_clicked = st.button("종목 검색", type="primary", use_container_width=True, key="pf_search_btn")

        if pf_search_clicked:
            if pf_search_input:
                st.session_state.pf_search_query = pf_search_input
            else:
                st.warning("⚠️ 검색어를 먼저 입력해주세요!")

        if st.session_state.pf_search_query:
            _q = st.session_state.pf_search_query
            pf_options = []
            with st.spinner("데이터베이스에서 종목을 찾는 중입니다..."):
                _krx_s = get_krx_stocks()   # 국내 주식 + ETF 포함
                if not _krx_s.empty:
                    _m = _krx_s[_krx_s['Name'].str.contains(_q, case=False, na=False)]
                    for _, _r in _m.head(60).iterrows():
                        pf_options.append(f"{_r['Name']} [{_r['Code']}]")
                if re.search('[a-zA-Z]', _q):   # 영문 포함 시 미국 주식/ETF 검색
                    try:
                        for _res_us in search_us_ticker(_q):
                            _sym = _res_us.split(" ")[0]
                            _ko = _res_us.split(" (")[1].split(" /")[0]
                            pf_options.append(f"{_ko} [{_sym}]")
                    except Exception:
                        pass

            if pf_options:
                with st.form(key="pf_add_form", clear_on_submit=True):
                    st.success(f"🎉 '{_q}' 검색 결과 총 **{len(pf_options)}개**를 찾았습니다!")
                    pf_selected = st.multiselect("👇 결과 목록에서 포트폴리오에 담을 종목을 모두 골라주세요:", options=pf_options)
                    pf_submit = st.form_submit_button("🛒 선택한 종목 포트폴리오 표에 추가하기", use_container_width=True)

                    if pf_submit:
                        if pf_selected:
                            _cur = st.session_state.portfolio_df.copy()
                            _existing = set(_cur["종목명"].astype(str).str.strip().str.upper())
                            _new_rows = []
                            for _sel in pf_selected:
                                _nm = str(_sel).strip()   # "이름 [코드]" 형식 그대로 저장 → 진단 시 코드 우선 인식(모호 매칭 방지)
                                if _nm.upper() in _existing:
                                    continue
                                _new_rows.append({"종목명": _nm, "진입단가": 0, "보유수량": 0})
                                _existing.add(_nm.upper())
                            if _new_rows:
                                # 비어 있는 placeholder 행은 제거 후 합치기
                                _mask_empty = (_cur["종목명"].astype(str).str.strip() == "") \
                                              & (pd.to_numeric(_cur["진입단가"], errors="coerce").fillna(0) == 0) \
                                              & (pd.to_numeric(_cur["보유수량"], errors="coerce").fillna(0) == 0)
                                _cur = _cur[~_mask_empty]
                                st.session_state.portfolio_df = pd.concat(
                                    [_cur, pd.DataFrame(_new_rows)], ignore_index=True)
                                st.session_state.pf_editor_ver += 1   # data_editor 강제 새로고침
                                st.toast(f"✅ {len(_new_rows)}개 종목을 표에 담았습니다! 단가·수량을 입력해주세요.", icon="🛒")
                            st.session_state.pf_search_query = ""
                            st.rerun()
                        else:
                            st.warning("⚠️ 추가할 종목을 위에서 먼저 선택해주세요.")
            else:
                st.error("앗! 검색 결과가 없습니다. 🥲 다른 키워드로 다시 검색해보세요.")

    st.caption("표는 직접 고칠 수 있고, 엑셀에서 복사한 표를 셀에 붙여넣기(Ctrl+V)해도 됩니다. 행 추가는 표 맨 아래 ➕ 버튼.")
    edited_df = st.data_editor(
        st.session_state.portfolio_df,
        num_rows="dynamic",
        column_config={
            "종목명": st.column_config.TextColumn("종목명 또는 티커", required=True),
            "진입단가": st.column_config.NumberColumn("내 진입단가", min_value=0, step=1, format="%d"),
            "보유수량": st.column_config.NumberColumn("보유 수량", min_value=0, step=1, format="%d"),
        },
        use_container_width=True,
        key=f"pf_editor_{st.session_state.pf_editor_ver}",
    )
    st.session_state.portfolio_df = edited_df

    _save_col, _clear_col = st.columns([3, 1])
    with _save_col:
        _valid_save = edited_df[
            (edited_df["종목명"].astype(str).str.strip() != "")
            & (pd.to_numeric(edited_df["진입단가"], errors="coerce").fillna(0) > 0)
            & (pd.to_numeric(edited_df["보유수량"], errors="coerce").fillna(0) > 0)
        ]
        st.download_button(
            "💾 내 포트폴리오 저장 (CSV) — 다음에 이 파일만 다시 올리면 그대로 복원돼요",
            _valid_save.to_csv(index=False).encode("utf-8-sig"),
            file_name="내_포트폴리오.csv", mime="text/csv",
            use_container_width=True, disabled=_valid_save.empty,
        )
    with _clear_col:
        if st.button("🗑️ 표 비우기", use_container_width=True):
            st.session_state.portfolio_df = pd.DataFrame([{"종목명": "", "진입단가": 0, "보유수량": 0}])
            st.session_state.pf_editor_ver += 1
            st.session_state.pf_loaded_key = None
            st.session_state.pf_upload_msg = ""
            st.session_state.pop("pf_upload", None)
            st.rerun()

    valid_rows = edited_df[(edited_df["종목명"].astype(str).str.strip() != "") & (edited_df["진입단가"] > 0) & (edited_df["보유수량"] > 0)]

    st.markdown("### 💧 2. 개별 종목 물타기 시뮬레이터 (선택 사항)")
    def _prc_avgcalc():
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
    _register_popup("avgcalc", _prc_avgcalc)
    _popup_button("🧮 평단가(물타기) 계산기 열기", "avgcalc", "🧮 평단가(물타기) 계산기", key="btn_avgcalc")

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
                    
                    # 🛒 [NEW] '이름 [코드]' 형식(검색해서 담기)이면 코드를 우선 인식 → 이름 모호 매칭(예: KO→KODEX) 방지
                    _br = re.search(r'\[([A-Za-z0-9.\-]{1,12})\]\s*$', pos_name)
                    if _br:
                        _code = _br.group(1).strip()
                        pos_name_kr = pos_name[:_br.start()].strip() or _code
                        search_ticker = _code
                        is_us = not _code.isdigit()   # 6자리 숫자면 국내, 아니면 미국 티커
                    
                    # 💡 [핵심 로직 수정] 영어 포함 여부가 아니라, '한국 주식 DB(KRX)'에 있는지 먼저 확인!
                    krx_df = get_krx_stocks()
                    if search_ticker:
                        pass   # 위에서 코드로 확정됨 → 이름 검색 생략
                    # 1. 한국 종목 중에 정확히 일치하는 이름이 있는지 먼저 확인 (대소문자 무시)
                    elif not (exact_match := krx_df[krx_df['Name'].str.upper() == pos_name.upper()]).empty:
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
                    # 순차 yf.Ticker 호출 → yf.download 배치 1회 (4종목 동시 수집)
                    _macro_dl = yf.download(list(tickers.values()), period="6mo",
                                            group_by="ticker", threads=True, progress=False)
                    for name, ticker in tickers.items():
                        try:
                            df_hist = _macro_dl[ticker].dropna(how="all") if len(tickers) > 1 else _macro_dl
                        except Exception:
                            continue
                        if not df_hist.empty:
                            # yf.download 일봉은 tz-naive로 올 수 있어 tz_localize 전에 방어
                            if getattr(df_hist.index, "tz", None) is not None:
                                df_hist.index = df_hist.index.tz_localize(None)
                            df_hist.index = df_hist.index.normalize()
                            close = df_hist['Close'].dropna()
                            if close.empty:
                                continue
                            normalized = (close / close.iloc[0] - 1) * 100
                            normalized = normalized[~normalized.index.duplicated(keep='first')]
                            series_dict[name] = normalized
                    if series_dict:
                        macro_df = pd.DataFrame(series_dict).ffill().dropna()
                        st.markdown("#### 🥇 원자재 & 암호화폐 슈퍼사이클 트래커 (6개월 상대수익률 %)")
                        fig_macro = px.line(macro_df, x=macro_df.index, y=macro_df.columns)
                        fig_macro.update_layout(height=400, yaxis_title="수익률 (%)", xaxis_title="날짜", hovermode="x unified")
                        st.plotly_chart(fig_macro, use_container_width=True)
                    
                    # 순차 yf.Ticker 2회 → yf.download 배치 1회 (^TNX, ^IRX 동시 수집)
                    _yc_dl = yf.download(["^TNX", "^IRX"], period="6mo",
                                         group_by="ticker", threads=True, progress=False)
                    try:
                        df_10y = _yc_dl["^TNX"].dropna(how="all")
                        df_2y = _yc_dl["^IRX"].dropna(how="all")
                    except Exception:
                        df_10y, df_2y = pd.DataFrame(), pd.DataFrame()
                    if not df_10y.empty and not df_2y.empty:
                        for _d in (df_10y, df_2y):
                            if getattr(_d.index, "tz", None) is not None:
                                _d.index = _d.index.tz_localize(None)
                            _d.index = _d.index.normalize()
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
                        # 순차 yf.Ticker 호출 → yf.download 배치 1회 (컬럼 순서=tickers_m 보존, 라벨 일치 보장)
                        data_m = pd.DataFrame()
                        try:
                            _dl = yf.download(tickers_m, period="1y", threads=True, progress=False)["Close"]
                            if isinstance(_dl, pd.Series):
                                _dl = _dl.to_frame(tickers_m[0])
                            for t in tickers_m:
                                if t in _dl.columns and not _dl[t].dropna().empty:
                                    data_m[t] = _dl[t]
                        except Exception:
                            pass
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
            "<span style='background:#ede7f6;color:#4527a0;padding:2px 6px;border-radius:3px;'>🏛️ 중앙은행(FOMC·ECB·BOJ·의사록)</span> "
            "<span style='background:#fff8e1;color:#ff6f00;padding:2px 6px;border-radius:3px;'>📊 물가(CPI·PCE)</span> "
            "<span style='background:#e0f7fa;color:#006064;padding:2px 6px;border-radius:3px;'>👷 경기(고용·PMI·소매판매·수출입)</span> "
            "<span style='background:#fce4ec;color:#880e4f;padding:2px 6px;border-radius:3px;'>🏦 한은 금통위</span> "
            "<span style='background:#ffebee;color:#c62828;padding:2px 6px;border-radius:3px;'>🔴 옵션만기</span> "
            "<span style='background:#e3f2fd;color:#1565c0;padding:2px 6px;border-radius:3px;'>🔹 위클리만기</span>"
            "</div>",
            unsafe_allow_html=True,
        )
        st.caption(
            "ℹ️ **확정 일정(2026)** — 중앙은행(FOMC·한은·ECB·BOJ)·FOMC 의사록, 미 CPI·고용지표(BLS 공식), "
            "옵션만기(미 셋째 금요일·한국 둘째 목요일, 규칙 기반). "
            "**추정 일정** — PCE·소매판매·ISM·한국 CPI·중국 PMI·한국 수출입은 통상 발표 시기 기준이라 실제 발표일과 1~2일 차이날 수 있습니다. "
            "정부 셧다운 등으로 발표일이 사후 연기될 수 있으니 중대한 매매 전엔 원출처를 확인하세요."
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

elif selected_menu == "📋 코스피·코스닥 종목 리스트":
    st.markdown("## 📋 코스피·코스닥 종목 리스트")
    st.write("국내 전체 상장 종목을 시장별로 검색·정렬해서 볼 수 있습니다.")

    with st.spinner("거래소 종목 데이터를 불러오는 중..."):
        all_stocks = get_stock_list_by_market()

    if all_stocks.empty:
        st.error("❌ 종목 데이터를 불러오지 못했습니다. 잠시 후 다시 시도해 주세요.")
    else:
        # ── 🎛️ 필터 패널 (테두리 카드로 묶어 시각적 구분) ─────────────────
        with st.container(border=True):
            c1, c2, c3 = st.columns([1.5, 1, 1])
            with c1:
                market_pick = st.radio("시장 구분", ["전체", "코스피", "코스닥", "코넥스"], horizontal=True)
            with c2:
                sort_by = st.selectbox("정렬 기준", ["시가총액(억)", "거래대금(억)", "등락률", "현재가", "종목명"])
            with c3:
                sort_desc = st.radio("정렬 순서", ["내림차순", "오름차순"], horizontal=True)

            c4, c5 = st.columns([1.5, 2])
            with c4:
                _sector_opts = sorted(s for s in all_stocks['업종'].dropna().unique()
                                      if s not in ('-', '기타/분류불가'))
                sector_pick = st.selectbox("🏷️ 업종 필터", ["전체 업종"] + _sector_opts)
            with c5:
                keyword = st.text_input("🔍 종목명 또는 종목코드 검색", placeholder="예: 삼성전자 / 005930")

        view = all_stocks.copy()
        if market_pick != "전체":
            view = view[view['시장'] == market_pick]
        if sector_pick != "전체 업종":
            view = view[view['업종'] == sector_pick]
        if keyword.strip():
            kw = keyword.strip()
            view = view[view['종목명'].str.contains(kw, case=False, na=False) | view['종목코드'].str.contains(kw, na=False)]

        ascending = (sort_desc == "오름차순")
        if sort_by == "종목명":
            view = view.sort_values("종목명", ascending=ascending, kind="stable")
        else:
            view = view.sort_values(sort_by, ascending=ascending, kind="stable")

        # ── 📊 요약 메트릭 (검색 결과의 시장 온도를 한눈에) ─────────────────
        _up = int((view['등락률'] > 0).sum())
        _down = int((view['등락률'] < 0).sum())
        _avg = float(view['등락률'].mean()) if len(view) else 0.0
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("검색 결과", f"{len(view):,}개")
        m2.metric("🔺 상승", f"{_up:,}개")
        m3.metric("🔻 하락", f"{_down:,}개")
        m4.metric("평균 등락률", f"{_avg:+.2f}%")

        # ── 📋 종목 테이블 ────────────────────────────────────────────────
        #   숫자 컬럼을 '숫자 그대로' 유지 + Styler로 표시만 포맷 → 헤더 클릭 정렬이
        #   사전순("9,900" > "10,000")으로 꼬이던 문제 해결. 등락률은 상승=빨강/하락=파랑.
        show = view[['시장', '종목코드', '종목명', '현재가', '등락률', '거래대금(억)', '시가총액(억)', '업종']].copy()
        show['차트'] = "https://finance.naver.com/item/main.naver?code=" + show['종목코드'].astype(str)

        def _updown_css(v):
            try:
                v = float(v)
            except (TypeError, ValueError):
                return ""
            if v > 0:
                return "color:#e03131;font-weight:600"
            if v < 0:
                return "color:#1971c2;font-weight:600"
            return "color:#868e96"

        sty = show.style.format({
            '현재가': '{:,.0f}원', '등락률': '{:+.2f}%',
            '거래대금(억)': '{:,.0f}', '시가총액(억)': '{:,.0f}',
        })
        # pandas 2.1+ 는 Styler.map, 구버전은 applymap (양쪽 호환)
        sty = (sty.map if hasattr(sty, "map") else sty.applymap)(_updown_css, subset=['등락률'])

        st.dataframe(
            sty,
            use_container_width=True, hide_index=True, height=620,
            column_config={
                "시장": st.column_config.TextColumn("시장", width="small"),
                "종목코드": st.column_config.TextColumn("코드", width="small"),
                "종목명": st.column_config.TextColumn("종목명", width="medium"),
                "업종": st.column_config.TextColumn("업종", width="medium"),
                "차트": st.column_config.LinkColumn("차트", display_text="📈 보기", width="small",
                                                  help="네이버 증권 종목 페이지 새 창으로 열기"),
            },
        )

        csv = view.to_csv(index=False).encode('utf-8-sig')
        st.download_button("⬇️ 현재 목록 CSV 다운로드", data=csv,
                           file_name=f"종목리스트_{market_pick}.csv", mime="text/csv")
        st.caption("💡 시세·시가총액은 거래소 마감 기준(약 10분 캐시) · 업종은 KRX 차단 시 네이버 업종별 시세로 자동 복구됩니다. 표 헤더를 클릭해도 정렬돼요.")

elif selected_menu == "🚀 단기 스윙 퀀트 스캐너":
    st.markdown("## 🚀 단기 스윙 퀀트 스캐너")
    scan_tab, backtest_tab = st.tabs(["🚀 실시간 조건 검색 스캐너", "🧪 전략 백테스팅 (비용·거래단위 통계)"])
    
    with scan_tab:
        show_beginner_guide()
        show_trading_guidelines()
        
        scan_market = st.radio("시장 선택 (스캐너)", ["🇰🇷 국내 주식", "🇺🇸 미국 주식"], horizontal=True)
        _is_kr_scan = scan_market.startswith("🇰🇷")

        # 체크박스 기본값(프리셋으로 일괄 세팅하기 위해 key + session_state 사용)
        for _k, _dv in [("sc_golden", False), ("sc_pullback", True), ("sc_rsi", False),
                        ("sc_vol", False), ("sc_twin", False), ("sc_pension", False),
                        ("sc_weekly", False), ("sc_high52", False), ("sc_mfi", False)]:
            st.session_state.setdefault(_k, _dv)

        # ⚡ 조건 프리셋 원클릭 (on_click 콜백은 위젯 생성 전에 실행돼 안전하게 상태를 세팅)
        def _apply_scan_preset(on_keys):
            for _k in ["sc_golden", "sc_pullback", "sc_rsi", "sc_vol", "sc_twin",
                       "sc_pension", "sc_weekly", "sc_high52", "sc_mfi"]:
                st.session_state[_k] = (_k in on_keys)
        st.caption("⚡ **빠른 프리셋** — 한 번에 조건 세팅:")
        _pc1, _pc2, _pc3, _pc4 = st.columns(4)
        _pc1.button("🚀 돌파형", use_container_width=True, help="정배열/골든 + 52주 신고가권 + 거래량 급증 + 자금유입",
                    on_click=_apply_scan_preset, args=(["sc_golden", "sc_high52", "sc_vol", "sc_mfi"],))
        _pc2.button("📉 낙폭 반등형", use_container_width=True, help="RSI 과매도 + 20일선 눌림목",
                    on_click=_apply_scan_preset, args=(["sc_rsi", "sc_pullback"],))
        _pc3.button("🐋 세력주형", use_container_width=True, help="외인·기관 쌍끌이 + 거래량 급증 + 기관 연속매수",
                    on_click=_apply_scan_preset, args=(["sc_twin", "sc_vol", "sc_pension"],))
        _pc4.button("♻️ 조건 초기화", use_container_width=True, on_click=_apply_scan_preset, args=([],))

        col_c1, col_c2, col_c3, col_c4 = st.columns(4)
        with col_c1:
            cond_golden = st.checkbox("✨ 골든크로스 / 정배열 초입", key="sc_golden")
            cond_pullback = st.checkbox("✅ 20일선 눌림목 (타점 근접)", key="sc_pullback")
        with col_c2:
            cond_rsi_bottom = st.checkbox("🔵 RSI 30 이하 (낙폭과대)", key="sc_rsi")
            cond_vol_spike = st.checkbox("🔥 최근 거래량 급증 (세력 의심)", key="sc_vol")
        with col_c3:
            cond_twin_buy = st.checkbox("🐋 외인/기관 쌍끌이 순매수", key="sc_twin")
            cond_high52 = st.checkbox("🚀 52주 신고가권 (주도주)", key="sc_high52",
                                      help="현재가가 52주 최고가 대비 -3% 이내 (신고가 돌파 모멘텀)")
        with col_c4:
            cond_pension = st.checkbox("👴 기관 3일 연속 순매수", key="sc_pension")
            cond_weekly = st.checkbox("📅 주봉도 상승 추세만 (멀티TF)", key="sc_weekly")
            cond_mfi = st.checkbox("💰 MFI 자금 유입 (55~80)", key="sc_mfi",
                                   help="거래량 가중 자금흐름지표(MFI) 55~80 — 과열 전 건강한 매집 구간")

        _sc_col1, _sc_col2 = st.columns([2.2, 1.8])
        with _sc_col1:
            scan_mode = st.radio("🔬 검색 방식", ["🎯 조건 필터 (체크한 조건 전부 충족)", "🏆 점수 랭킹 (충족 개수로 정렬·1개 이상)"],
                                 horizontal=True,
                                 help="조건 필터: AND 방식 — 깐깐하지만 결과가 0개일 수 있음.\n점수 랭킹: 체크한 조건 중 몇 개를 충족하는지 점수화해 많이 충족한 순으로 보여줌 — 장이 안 좋은 날에도 상대적 상위 종목 발굴 가능.")
        with _sc_col2:
            scan_limit = st.selectbox("스캔할 상위 종목 수", [50, 100, 200, 300], index=3)

        # 💧 유동성·가격·과열 하드필터 (선택한 조건과 별개로 항상 적용, 0 = 미적용)
        with st.container(border=True):
            st.caption("💧 **유동성·가격 필터** — 실제로 사고팔 수 있는 종목만 남깁니다 (0=미적용):")
            _fl1, _fl2, _fl3 = st.columns(3)
            if _is_kr_scan:
                with _fl1:
                    _min_amt_disp = st.number_input("최소 거래대금 (억)", 0, 100000, 0, 10,
                                                    help="20일 평균 거래대금 하한. 저유동성·동전주 제외 (예: 30억)")
                with _fl2:
                    _min_price = st.number_input("최소 주가 (원)", 0, 2000000, 0, 100, help="동전주 제외")
                _min_amt_raw = _min_amt_disp * 1e8
            else:
                with _fl1:
                    _min_amt_disp = st.number_input("최소 거래대금 ($M)", 0.0, 200000.0, 0.0, 5.0,
                                                    help="20일 평균 거래대금 하한(백만달러). 저유동성 제외")
                with _fl2:
                    _min_price = st.number_input("최소 주가 ($)", 0.0, 100000.0, 0.0, 1.0, help="페니주 제외")
                _min_amt_raw = _min_amt_disp * 1e6
            with _fl3:
                _excl_overext = st.checkbox("🚫 과이격(추격) 종목 제외", value=False,
                                            help="20일선 대비 +15% 이상 벌어진 과열 종목 제외 (추격매수 방지)")
        
        # 📋 체크박스 → (라벨, 판정함수) 레지스트리로 일원화 (필터/점수 모드 공용)
        scan_checks = []
        if cond_golden: scan_checks.append(("✨ 정배열/골든크로스", lambda r: ("🔥 완벽 정배열" in str(r.get('배열상태', ''))) or ("✨ 5-20 골든크로스" in str(r.get('배열상태', '')))))
        if cond_pullback: scan_checks.append(("✅ 눌림목 타점", lambda r: r.get('상태') == "✅ 타점 근접 (분할 매수)"))
        if cond_rsi_bottom: scan_checks.append(("🔵 RSI≤30", lambda r: float(r.get('RSI', 100)) <= 30))
        if cond_vol_spike: scan_checks.append(("🔥 거래량 급증", lambda r: r.get('거래량 급증') == "🔥 거래량 터짐"))
        if cond_twin_buy: scan_checks.append(("🐋 쌍끌이 매수", lambda r: ("+" in str(r.get('기관수급', ''))) and ("+" in str(r.get('외인수급', '')))))
        if cond_pension: scan_checks.append(("👴 기관 3일 연속", lambda r: r.get('연기금연속순매수', 0) >= 3))
        if cond_weekly: scan_checks.append(("📅 주봉 상승", lambda r: "상승추세" in str(r.get('주봉추세', ''))))
        if cond_high52: scan_checks.append(("🚀 52주 신고가권", lambda r: (_f_num(r.get('고점대비52주')) is not None and _f_num(r.get('고점대비52주')) >= -3)))
        if cond_mfi: scan_checks.append(("💰 MFI 자금유입", lambda r: (_f_num(r.get('MFI')) is not None and 55 <= _f_num(r.get('MFI')) <= 80)))
        
        if st.button("🚀 쾌속 병렬 스캔 시작", type="primary", use_container_width=True):
            if not scan_checks:
                st.warning("⚠️ 검색 조건을 최소 1개 이상 체크해주세요. (조건 없이 스캔하면 전 종목이 쏟아져 화면이 멈출 수 있어요)")
            else:
                with st.spinner(f"⚡ {scan_limit}개 종목 고속 필터링 중..."):
                    if scan_market == "🇰🇷 국내 주식": targets = get_scan_targets(scan_limit)
                    else: targets = get_us_scan_targets(scan_limit)
                        
                    if not targets: st.error("❌ 종목 데이터를 불러오지 못했습니다.")
                    else:
                        _is_score_mode = scan_mode.startswith("🏆")
                        progress_bar = st.progress(0)
                        status_text = st.empty()
                        found_results = []
                        completed, total = 0, len(targets)
                        def process_stock(target):
                            name, code = target
                            time.sleep(0.1) 
                            res = analyze_technical_pattern(name, code, offset_days=0)
                            if not res: return None
                            # 💧 유동성·가격·과열 하드필터 (선택 조건과 별개로 우선 적용)
                            if _min_amt_raw > 0:
                                _a = _f_num(res.get('평균거래대금20일'))
                                if _a is None or _a < _min_amt_raw: return None
                            if _min_price > 0:
                                _p = _f_num(res.get('현재가'))
                                if _p is None or _p < _min_price: return None
                            if _excl_overext:
                                _g = _f_num(res.get('이격도20'))
                                if _g is not None and _g >= 15: return None
                            passed = []
                            for _lbl, _fn in scan_checks:
                                try:
                                    if _fn(res): passed.append(_lbl)
                                except Exception:
                                    pass
                            if _is_score_mode:
                                if not passed: return None          # 점수 모드: 1개 이상 충족만
                            else:
                                if len(passed) < len(scan_checks): return None   # 필터 모드: 전부 충족
                            res['_score'] = len(passed)
                            res['스캔점수'] = f"{len(passed)}/{len(scan_checks)}"
                            res['충족조건'] = " · ".join(passed)
                            return res
                        with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
                            for future in concurrent.futures.as_completed({executor.submit(process_stock, t): t for t in targets}):
                                res = future.result()
                                completed += 1
                                if res: found_results.append(res)
                                progress_bar.progress(completed / total)
                                status_text.text(f"⚡ 스캔 진행 중... ({completed}/{total}) - {len(found_results)}개 포착")
                        if _is_score_mode:
                            found_results.sort(key=lambda r: r.get('_score', 0), reverse=True)
                        st.session_state.scan_results = found_results
                        st.session_state.scan_results_meta = {
                            "time": datetime.now().strftime("%Y-%m-%d %H:%M"),
                            "market": scan_market, "mode": "점수 랭킹" if _is_score_mode else "조건 필터",
                            "conds": " · ".join(lbl for lbl, _ in scan_checks), "limit": scan_limit,
                            "filters": (" · ".join([f for f in [
                                (f"거래대금≥{_min_amt_disp}{'억' if _is_kr_scan else '$M'}" if _min_amt_disp else ""),
                                (f"주가≥{_min_price}{'원' if _is_kr_scan else '$'}" if _min_price else ""),
                                ("과이격 제외" if _excl_overext else ""),
                            ] if f]) or "없음"),
                        }
                        st.rerun()
        if st.session_state.scan_results is not None:
            _meta = st.session_state.get("scan_results_meta") or {}
            _info_col, _clear_col = st.columns([5, 1], vertical_alignment="center")
            with _info_col:
                if _meta:
                    st.caption(f"🕒 스캔 시각: **{_meta.get('time','-')}** ｜ {_meta.get('market','')} 상위 {_meta.get('limit','')}개 ｜ 방식: {_meta.get('mode','')} ｜ 조건: {_meta.get('conds','')} ｜ 필터: {_meta.get('filters','없음')}")
            with _clear_col:
                if st.button("🗑️ 결과 지우기", key="scan_clear_btn", use_container_width=True):
                    st.session_state.scan_results = None
                    st.session_state.scan_results_meta = None
                    st.rerun()
            if st.session_state.scan_results is not None:
                display_sorted_results(st.session_state.scan_results, tab_key="t2", api_key=api_key_input)

    with backtest_tab:
        st.markdown("### 🧪 단기 스윙 전략 시뮬레이터")
        st.write("과거 데이터를 기반으로 다양한 퀀트 전략의 실제 수익률과 타점을 검증합니다. (실제 분석 기간은 결과 리포트에 표시됩니다)")
        
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
        
        _bt_c1, _bt_c2 = st.columns([2.5, 1.5])
        with _bt_c1:
            strategy_sel = st.selectbox("🎯 백테스트 퀀트 전략 선택", [
                "5-20 이평선 골든크로스", "RSI 과매도 매수 (RSI < 30)", "볼린저밴드 하단 매수", "MACD 교차"
            ])
        with _bt_c2:
            bt_cost_pct = st.number_input("💸 왕복 거래비용 (%)", min_value=0.0, max_value=2.0, value=0.25, step=0.05,
                                          help="수수료+거래세+슬리피지를 합친 왕복(매수+매도) 비용. 국내 일반계좌 기준 약 0.2~0.4%, 미국 주식은 0.05~0.2% 수준을 권장합니다. 0으로 두면 비용 미반영(기존 방식).")

        # 🛡️ [개선] 손절·익절·보유상한 청산 규칙 (0 = 미적용 → 기존 신호 청산만)
        _bt_e1, _bt_e2, _bt_e3 = st.columns(3)
        with _bt_e1:
            bt_stop = st.number_input("🛑 손절 (%)", min_value=0.0, max_value=50.0, value=0.0, step=0.5,
                                      help="진입가 대비 이만큼 하락하면 청산. 0=미적용(신호로만 청산). 앱 권장 손절은 20일선 -3% 수준.")
        with _bt_e2:
            bt_target = st.number_input("🎯 익절 (%)", min_value=0.0, max_value=200.0, value=0.0, step=1.0,
                                        help="진입가 대비 이만큼 상승하면 청산. 0=미적용.")
        with _bt_e3:
            bt_maxhold = st.number_input("📆 최대 보유일", min_value=0, max_value=250, value=0, step=1,
                                         help="진입 후 이 영업일수를 넘기면 강제 청산. 0=미적용.")
        st.caption("💡 손절·익절·보유상한은 신호 청산보다 **우선** 적용됩니다. 셋 다 0이면 기존처럼 ‘신호 On=진입 / Off=청산’만 검증합니다. "
                   "일봉 종가 기준이라 장중 터치는 반영하지 않습니다(보수적 측정).")

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

                    bt_df['Daily_Return'] = bt_df['Close'].pct_change()

                    # 🛡️ [개선] 손절·익절·보유상한 청산을 반영한 이벤트 기반 시뮬레이션.
                    #   진입: 관망(flat) 중 신호 발생일 종가 매수 → 다음날부터 수익 귀속(기존과 동일)
                    #   청산 우선순위: 손절 → 익절 → 보유상한 → 신호종료.
                    #   손절/익절/보유상한 청산 후에는 신호가 한 번 꺼졌다 다시 켜져야 재진입(휩쏘 방지).
                    #   신호종료 청산이면 즉시 재진입 가능(기존 동작과 동일).
                    _sig = bt_df['Signal'].fillna(0).values
                    _closes = bt_df['Close'].values
                    _dates = bt_df.index
                    _n = len(_closes)
                    _stop_f = (bt_stop / 100.0) if bt_stop > 0 else None
                    _tgt_f = (bt_target / 100.0) if bt_target > 0 else None
                    _maxh = int(bt_maxhold) if bt_maxhold > 0 else None
                    _oneway_cost = (bt_cost_pct / 2.0) / 100.0
                    _rt_cost = bt_cost_pct / 100.0

                    _pos = np.zeros(_n)
                    trade_records = []
                    _armed = True
                    _entry_i = None
                    _idx = 0
                    while _idx < _n:
                        if _entry_i is None:                       # 관망 상태
                            if _armed and _sig[_idx] == 1:
                                _entry_i = _idx                    # 신호일 종가 매수
                            elif _sig[_idx] == 0:
                                _armed = True
                            _idx += 1
                            continue
                        _entry_px = _closes[_entry_i]
                        _exit_i, _reason = None, None
                        _j = _entry_i + 1
                        while _j < _n:
                            _pos[_j] = 1                           # 보유일 표시
                            _chg = _closes[_j] / _entry_px - 1.0
                            if _stop_f is not None and _chg <= -_stop_f:
                                _exit_i, _reason = _j, "손절"; break
                            if _tgt_f is not None and _chg >= _tgt_f:
                                _exit_i, _reason = _j, "익절"; break
                            if _maxh is not None and (_j - _entry_i) >= _maxh:
                                _exit_i, _reason = _j, "보유상한"; break
                            if _sig[_j] == 0:
                                _exit_i, _reason = _j, "신호종료"; break
                            _j += 1
                        if _exit_i is None:                        # 기간 끝까지 보유 중
                            _exit_i, _reason, _open_trade = _n - 1, "보유중", True
                        else:
                            _open_trade = False
                        _ret = (_closes[_exit_i] / _entry_px - 1.0) - _rt_cost
                        trade_records.append({
                            "진입일": _dates[_entry_i].strftime("%y/%m/%d"),
                            "청산일": _dates[_exit_i].strftime("%y/%m/%d") + (" (보유중)" if _open_trade else ""),
                            "청산사유": _reason,
                            "보유일": max((_dates[_exit_i] - _dates[_entry_i]).days, 1),
                            "수익률(%)": _ret * 100.0,
                        })
                        _armed = (_reason == "신호종료")           # 신호종료면 즉시 재진입 가능
                        _entry_i = None
                        _idx = _exit_i + 1

                    bt_df['Position'] = _pos
                    bt_df['Trade_Mark'] = bt_df['Position'].diff().fillna(0)
                    # 💸 왕복 거래비용: 진입/청산 발생일마다 편도 비용 차감
                    bt_df['Strategy_Return'] = (bt_df['Position'] * bt_df['Daily_Return']) - (bt_df['Trade_Mark'].abs() * _oneway_cost)
                    bt_df['Cumulative_Market'] = (1 + bt_df['Daily_Return']).cumprod()
                    bt_df['Cumulative_Strategy'] = (1 + bt_df['Strategy_Return']).cumprod()

                    bt_df['Cum_Max'] = bt_df['Cumulative_Strategy'].cummax()
                    bt_df['Drawdown'] = (bt_df['Cumulative_Strategy'] - bt_df['Cum_Max']) / bt_df['Cum_Max']
                    mdd = bt_df['Drawdown'].min() * 100

                    # 📈 '매수→매도' 거래 단위 통계
                    total_trades = len(trade_records)
                    _wins = [t for t in trade_records if t["수익률(%)"] > 0]
                    _losses = [t for t in trade_records if t["수익률(%)"] <= 0]
                    win_rate = (len(_wins) / total_trades * 100.0) if total_trades > 0 else 0.0
                    avg_win = (sum(t["수익률(%)"] for t in _wins) / len(_wins)) if _wins else 0.0
                    avg_loss = (sum(t["수익률(%)"] for t in _losses) / len(_losses)) if _losses else 0.0
                    _gross_win = sum(t["수익률(%)"] for t in _wins)
                    _gross_loss = abs(sum(t["수익률(%)"] for t in _losses))
                    profit_factor = (_gross_win / _gross_loss) if _gross_loss > 0 else (float('inf') if _gross_win > 0 else 0.0)
                    avg_hold = (sum(t["보유일"] for t in trade_records) / total_trades) if total_trades > 0 else 0.0

                    # 📐 샤프지수 (연환산, 무위험수익률 0 가정)
                    _sr_std = bt_df['Strategy_Return'].std()
                    sharpe = (bt_df['Strategy_Return'].mean() / _sr_std * (252 ** 0.5)) if _sr_std and _sr_std > 0 else 0.0
                    # 🎲 기대값(회당 평균) · 평균 손익비(Payoff) · 시장 노출도 · CAGR
                    expectancy = (sum(t["수익률(%)"] for t in trade_records) / total_trades) if total_trades > 0 else 0.0
                    payoff = (avg_win / abs(avg_loss)) if avg_loss < 0 else (float('inf') if avg_win > 0 else 0.0)
                    exposure = (float(_pos.sum()) / _n * 100.0) if _n > 0 else 0.0
                    _cum_final = float(bt_df['Cumulative_Strategy'].iloc[-1])
                    _years = _n / 252.0
                    cagr = ((_cum_final ** (1.0 / _years) - 1.0) * 100.0) if (_cum_final > 0 and _years > 0) else 0.0
                    _exit_counts = {}
                    for _t in trade_records:
                        _exit_counts[_t["청산사유"]] = _exit_counts.get(_t["청산사유"], 0) + 1
                    
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
                    
                    _period_str = f"{bt_df.index[0].strftime('%Y.%m.%d')} ~ {bt_df.index[-1].strftime('%Y.%m.%d')} (영업일 {len(bt_df)}일)"
                    st.markdown("### 📊 백테스트 성과 리포트")
                    st.caption(f"🗓️ 실제 분석 기간: **{_period_str}** ｜ 💸 왕복 거래비용 **{bt_cost_pct:.2f}%** 반영 ｜ 승률·손익은 '매수→매도' **거래 단위** 기준")
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

                    with c1: st.markdown(metric_card("전략 누적 수익률", f"{final_strat:.2f}%", f"단순 보유 대비 {final_strat - final_market:+.2f}%p (비용 차감 후)", is_red=(final_strat>0), is_green=(final_strat<0)), unsafe_allow_html=True) 
                    with c2: st.markdown(metric_card("최대 낙폭 (MDD)", f"{mdd:.2f}%", "계좌 최대 하락률", is_green=(mdd<-20)), unsafe_allow_html=True)
                    with c3: st.markdown(metric_card("거래별 승률", f"{win_rate:.1f}%", f"총 {total_trades}건 중 {len(_wins)}건 수익", is_red=(win_rate>50)), unsafe_allow_html=True)
                    with c4: st.markdown(metric_card("Profit Factor", "∞" if profit_factor == float('inf') else f"{profit_factor:.2f}", "총수익 ÷ 총손실 (1 초과 = 우위)", is_red=(profit_factor>1)), unsafe_allow_html=True)
                    
                    c5, c6, c7, c8 = st.columns(4)
                    with c5: st.markdown(metric_card("평균 수익 거래", f"+{avg_win:.2f}%", "수익 거래의 평균 수익률", is_red=(avg_win>0)), unsafe_allow_html=True)
                    with c6: st.markdown(metric_card("평균 손실 거래", f"{avg_loss:.2f}%", "손실 거래의 평균 손실률", is_green=(avg_loss<0)), unsafe_allow_html=True)
                    with c7: st.markdown(metric_card("평균 보유 기간", f"{avg_hold:.1f}일", "거래당 평균 보유일"), unsafe_allow_html=True)
                    with c8: st.markdown(metric_card("샤프 지수 (연환산)", f"{sharpe:.2f}", "1 이상이면 양호한 위험 대비 수익"), unsafe_allow_html=True)

                    c9, c10, c11, c12 = st.columns(4)
                    with c9: st.markdown(metric_card("기대값 (회당)", f"{expectancy:+.2f}%", "거래 1회 평균 손익(비용 후)", is_red=(expectancy>0), is_green=(expectancy<0)), unsafe_allow_html=True)
                    with c10: st.markdown(metric_card("CAGR (연환산)", f"{cagr:+.2f}%", "전략 연환산 복리 수익률", is_red=(cagr>0), is_green=(cagr<0)), unsafe_allow_html=True)
                    with c11: st.markdown(metric_card("평균 손익비", "∞" if payoff == float('inf') else f"{payoff:.2f}", "평균수익 ÷ 평균손실 (Payoff)", is_red=(payoff>=1 and payoff!=float('inf')) or payoff==float('inf')), unsafe_allow_html=True)
                    with c12: st.markdown(metric_card("시장 노출도", f"{exposure:.0f}%", "전체 기간 중 실제 보유일 비중"), unsafe_allow_html=True)

                    if _exit_counts:
                        _ec_txt = " · ".join(f"{k} {v}건" for k, v in sorted(_exit_counts.items(), key=lambda x: -x[1]))
                        _rule_txt = " · ".join([x for x in [
                            (f"손절 {bt_stop:.1f}%" if bt_stop > 0 else ""),
                            (f"익절 {bt_target:.1f}%" if bt_target > 0 else ""),
                            (f"보유상한 {int(bt_maxhold)}일" if bt_maxhold > 0 else ""),
                        ] if x])
                        if _rule_txt:
                            st.caption(f"🚪 청산 사유 분포: {_ec_txt}  ｜  적용 규칙: {_rule_txt}")
                        else:
                            st.caption(f"🚪 청산 사유 분포: {_ec_txt}  (손절·익절 미적용 — 신호 청산만)")

                    if trade_records:
                        def _prc_trades():
                            _tr_df = pd.DataFrame(trade_records)
                            _tr_df["수익률(%)"] = _tr_df["수익률(%)"].map(lambda v: round(v, 2))
                            st.dataframe(_tr_df, use_container_width=True, hide_index=True)
                            st.caption("※ 진입가 = 신호 발생일 종가, 청산가 = 청산일 종가(손절·익절도 일봉 종가 기준). "
                                       "'청산사유'로 손절/익절/보유상한/신호종료를 구분합니다. '(보유중)'은 기간 종료까지 미청산 → 마지막 종가로 평가한 거래입니다.")
                        _register_popup("trades", _prc_trades)
                        _popup_button(f"📜 전체 거래 내역 보기 ({total_trades}건)", "trades", f"📜 전체 거래 내역 ({total_trades}건)", key="btn_trades")
                    else:
                        st.info("해당 기간에 전략 조건을 충족한 거래가 없었습니다.")
                else: st.error("❌ 데이터를 가져오지 못했습니다.")

elif selected_menu == "📉 낙폭과대 스캐너 (고점대비 -30%↓)":
    st.markdown("## 📉 낙폭과대 스캐너")
    st.caption("고점 대비 크게 하락한 종목만 추려냅니다. 낙폭과대 반등(역추세) 후보 발굴용 — "
               "**'떨어진 데는 이유가 있을 수 있으니'** 펀더멘털·뉴스를 반드시 함께 확인하세요.")

    if "dd_results" not in st.session_state:
        st.session_state.dd_results = None
        st.session_state.dd_meta = None

    c1, c2, c3 = st.columns(3)
    with c1:
        dd_scope_label = st.radio("🌍 시장", ["🇰🇷 국내", "🇺🇸 미국", "🇰🇷+🇺🇸 모두"], horizontal=True)
    with c2:
        min_fall = st.slider("📉 최소 낙폭 (고점 대비)", 20, 70, 30, step=5, format="%d%%")
    with c3:
        lookback = st.radio("📅 고점 기준", ["52주", "전체기간"], horizontal=True)
    c4, c5 = st.columns(2)
    with c4:
        dd_depth = st.select_slider("🔬 스캔 범위 (거래대금/시총 상위)",
                                    options=["상위 100", "상위 200", "상위 400"], value="상위 200")
    with c5:
        rb_label = st.select_slider("📈 ‘저점대비 반등’ 측정 기간",
                                    options=["1개월", "3개월", "6개월", "1년"], value="6개월")
    depth_n = {"상위 100": 100, "상위 200": 200, "상위 400": 400}[dd_depth]
    rebound_days = {"1개월": 21, "3개월": 63, "6개월": 126, "1년": 252}[rb_label]
    lb = "52주" if lookback == "52주" else "전체"
    st.caption("⏳ 범위가 넓을수록 1~3분 걸릴 수 있어요(종목별 시세 조회). 결과는 캐시되어 재실행이 빠릅니다.")

    def _prc_indicators():
        st.markdown(
            f"""
- **낙폭 (고점 대비)** — 선택한 기간({lookback})의 **최고가에서 현재가가 얼마나 떨어졌는지**. 예: -40%면 천장 대비 40% 하락. 값이 클수록(−쪽으로) 많이 빠진 것.
- **저점대비 반등** — 최근 **{rb_label}** 동안의 **가장 낮은 가격(바닥)에서 현재가가 얼마나 올라왔는지**. 바닥을 찍고 회복이 시작됐는지 보는 지표입니다.
    - **+0% 근처** → 아직 신저가 부근, 바닥 확인 안 됨 (떨어지는 칼날 주의 🔪)
    - **+10~30%** → 바닥 다지고 반등 초입일 가능성 (역추세 매매 관심 구간 ⭐)
    - **+100% 이상** → 이미 반등이 많이 진행됨 (늦었을 수 있음)
- **RSI** — 0~100 사이 과매수/과매도 지표. **30 이하면 🧊과매도**(단기 반등 기대 구간이나 추세 하락 지속 위험도 큼).
- **고점일** — 위 ‘최고가’가 기록된 날짜.
- **🩹 회복점수 (0~100)** — ‘많이 빠진 것’과 ‘회복이 시작된 것’은 다릅니다. 기술 신호(20일선 회복·단기 골든크로스·**저점 높이기**·거래량 회복·OBV 매집·60일선 상승 전환) + 반등 위치(바닥 확인 후 초입 구간 가점) + RSI 구간 + **테마 온기**(소속 업종/섹터가 살아나는 중인지)를 합산한 종합 점수입니다. 🟢70↑ 회복 유력 · 🟡50↑ 회복 조짐 · ⚪30↑ 관찰 · 🔴30↓ 바닥 미확인.
- **테마온기(%)** — 국내는 네이버 업종 전일 등락률, 미국은 섹터 ETF 최근 5거래일 수익률. 종목 혼자가 아니라 **업종 전체가 돌아서는지**(테마적 회복) 확인하는 지표.

💡 **활용 팁**: ‘많이 빠졌으면서(낙폭 큼) + 바닥 다지고 살짝 고개 든(반등 +10~30%) + 회복점수 높은’ 종목이 반등 매매에선 매력적입니다. 표 아래 **🤖 AI 회복 검증** 버튼을 누르면 상위 종목의 하락 원인이 일회성인지 구조적인지 실시간 검색으로 교차 확인해줍니다.
표의 **각 컬럼 머리글을 클릭하면 오름차순/내림차순 정렬**됩니다 (숫자 정렬).
"""
        )
    _register_popup("indicators", _prc_indicators)
    _popup_button("📖 지표 설명 보기 (꼭 읽어보세요)", "indicators", "📖 지표 설명", key="btn_indicators")

    if st.button("🔎 낙폭 스캔 시작", type="primary", use_container_width=True):
        scope = ("kr" if dd_scope_label.startswith("🇰🇷 국내")
                 else "us" if dd_scope_label.startswith("🇺🇸 미국") else "both")
        # 시장(코스피/코스닥)·섹터 룩업 준비
        kr_meta = {}
        if scope in ("kr", "both"):
            try:
                kdf = get_krx_stocks()
                if not kdf.empty:
                    for _, rr in kdf.iterrows():
                        kr_meta[str(rr["Code"]).zfill(6)] = (
                            (rr.get("Market") if "Market" in kdf.columns else "") or "국내",
                            (rr.get("Sector") if "Sector" in kdf.columns else "") or "-")
            except Exception:
                pass
        us_sec = get_us_sector_map() if scope in ("us", "both") else {}

        universe = []
        if scope in ("kr", "both"):
            try:
                for n, c in (get_scan_targets(depth_n) or []):
                    c = str(c).zfill(6)
                    mk, sec = kr_meta.get(c, ("국내", "-"))
                    universe.append((n, c, mk or "국내", sec or "-"))
            except Exception:
                pass
        if scope in ("us", "both"):
            try:
                for n, c in (get_us_scan_targets(min(depth_n, 500)) or []):
                    c = str(c)
                    universe.append((n, c, "미국", us_sec.get(c, "-")))
            except Exception:
                pass
        seen, uni = set(), []
        for n, c, mk, sec in universe:
            if c in seen:
                continue
            seen.add(c); uni.append((n, c, mk, sec))
        if not uni:
            st.error("❌ 종목 유니버스를 불러오지 못했습니다. 잠시 후 다시 시도해 주세요.")
        else:
            prog = st.progress(0.0); status = st.empty()
            done, total, rows = 0, len(uni), []

            def _dd_work(item):
                n, c, mk, sec = item
                return n, c, mk, sec, get_drawdown_info(c, lb, rebound_days)

            with concurrent.futures.ThreadPoolExecutor(max_workers=8) as ex:
                for fut in concurrent.futures.as_completed({ex.submit(_dd_work, it): it for it in uni}):
                    try:
                        n, c, mk, sec, info = fut.result()
                        if info and info["drawdown"] is not None and info["drawdown"] <= -min_fall:
                            rows.append({"name": n, "code": c, "market": mk, "sector": sec, **info})
                    except Exception:
                        pass
                    done += 1
                    prog.progress(min(1.0, done / total))
                    status.text(f"📉 낙폭 스캔 중... ({done}/{total})")
            prog.empty(); status.empty()
            rows.sort(key=lambda r: r["drawdown"])   # 가장 많이 빠진 순

            # 업종 보강 — FDR 업종이 비어 '기타/분류불가'인 결과 종목만 네이버에서 개별 조회(가벼움)
            need_sec = [r for r in rows if str(r["code"]).isdigit()
                        and (not r.get("sector") or r["sector"] in ("-", "기타/분류불가"))]
            if need_sec:
                ss = st.empty(); ss.text(f"🏷️ 업종 분류 중... ({len(need_sec)}종목)")
                with concurrent.futures.ThreadPoolExecutor(max_workers=8) as ex:
                    fsec = {ex.submit(get_stock_sector_kr, r["code"]): r for r in need_sec}
                    for f in concurrent.futures.as_completed(fsec):
                        r = fsec[f]
                        try:
                            s = f.result()
                            if s:
                                r["sector"] = s
                        except Exception:
                            pass
                ss.empty()

            st.session_state.dd_results = rows
            st.session_state.dd_meta = (dd_scope_label, min_fall, lookback, len(uni), rb_label)

    # ===== 결과 렌더 =====
    rows = st.session_state.dd_results
    if rows is not None:
        meta = st.session_state.dd_meta
        if not rows:
            st.warning(f"조건(고점 대비 -{meta[1]}% 이하)을 만족하는 종목이 없습니다. 낙폭 기준을 낮춰보세요.")
        else:
            st.success(f"✅ {meta[3]}개 스캔 중 **{len(rows)}개** 포착 — 고점({meta[2]}) 대비 **-{meta[1]}% 이하** · 반등기준 {meta[4] if len(meta) > 4 else '6개월'}")
            
            # 🩹 [NEW] 회복 가능성 점수 산출 (테마 온기 + 기술 신호 합산)
            _any_kr = any(str(r["code"]).isdigit() for r in rows)
            _any_us = any(not str(r["code"]).isdigit() for r in rows)
            with st.spinner("🩹 업종/섹터 온기 조회 및 회복 점수 계산 중..."):
                _kr_heat = get_kr_sector_heat() if _any_kr else {}
                _us_heat = get_us_sector_heat() if _any_us else {}
                for r in rows:
                    _is_kr = str(r["code"]).isdigit()
                    _hv = match_sector_heat(r.get("sector"), _kr_heat, _us_heat, _is_kr)
                    r["_heat"] = _hv
                    r["_rec_score"], r["_rec_grade"], r["_rec_why"] = calc_recovery_score(r, _hv)
            
            _dd_sort = st.radio("⬇️ 정렬 기준", ["🩹 회복점수 높은순 (추천)", "📉 낙폭 깊은순", "📈 저점대비 반등 높은순"],
                                horizontal=True, key="dd_sort_radio")
            if _dd_sort.startswith("🩹"):
                rows = sorted(rows, key=lambda r: (r.get("_rec_score", 0), -abs(r.get("drawdown") or 0)), reverse=True)
            elif _dd_sort.startswith("📈"):
                rows = sorted(rows, key=lambda r: (r.get("rebound") if r.get("rebound") is not None else -999), reverse=True)
            else:
                rows = sorted(rows, key=lambda r: r["drawdown"])
            
            # 시장 구성으로 가격 단위 판별(정렬 가능하도록 숫자 컬럼 유지)
            codes = [str(r["code"]) for r in rows]
            all_kr = all(c.isdigit() for c in codes)
            all_us = all(not c.isdigit() for c in codes)
            price_label = "현재가(원)" if all_kr else ("현재가($)" if all_us else "현재가")
            high_label = "최고가(원)" if all_kr else ("최고가($)" if all_us else "최고가")

            df_rows = []
            for i, r in enumerate(rows, 1):
                rsi = r.get("rsi")
                _sec = str(r.get("sector") or "-")
                if len(_sec) > 16:
                    _sec = _sec[:16] + "…"
                df_rows.append({
                    "순위": i,
                    "종목명": r["name"],
                    "시장": r["market"],
                    "테마/섹터": _sec,
                    "🩹회복점수": r.get("_rec_score", 0),
                    "회복판정": r.get("_rec_grade", "-"),
                    "테마온기(%)": (round(float(r["_heat"]), 1) if r.get("_heat") is not None else None),
                    price_label: round(float(r["current"]), 2),
                    high_label: round(float(r["high"]), 2),
                    "고점일": (r.get("high_date") or "-"),
                    "낙폭(%)": round(float(r["drawdown"]), 1),
                    "저점대비반등(%)": (round(float(r["rebound"]), 1) if r.get("rebound") is not None else None),
                    "RSI": (int(rsi) if rsi is not None else None),
                    "회복근거": r.get("_rec_why", "-"),
                })
            dd_df = pd.DataFrame(df_rows)
            price_fmt = "%.0f" if all_kr else ("$%.2f" if all_us else "%.2f")
            if hasattr(st, "column_config"):
                st.dataframe(
                    dd_df, use_container_width=True, hide_index=True,
                    height=min(640, 80 + len(df_rows) * 35),
                    column_config={
                        "순위": st.column_config.NumberColumn("순위", format="%d", width="small"),
                        "🩹회복점수": st.column_config.ProgressColumn("🩹회복점수", min_value=0, max_value=100, format="%d",
                            help="기술 신호(20일선 회복·저점 높이기·거래량/OBV 회복 등) + 반등 위치 + RSI 구간 + 업종 온기를 합산한 0~100점. 70↑ 회복 유력 / 50↑ 회복 조짐 / 30↓ 바닥 미확인."),
                        "테마온기(%)": st.column_config.NumberColumn("테마온기(%)", format="%+.1f%%",
                            help="국내: 네이버 업종 전일 등락률 ｜ 미국: 섹터 ETF 최근 5거래일 수익률. 업종이 살아나는 중인지(테마적 회복) 확인."),
                        price_label: st.column_config.NumberColumn(price_label, format=price_fmt),
                        high_label: st.column_config.NumberColumn(high_label, format=price_fmt),
                        "낙폭(%)": st.column_config.NumberColumn("낙폭(%)", format="%.1f%%",
                            help="고점 대비 하락률 (현재가÷최고가−1). 음수일수록 많이 빠진 것."),
                        "저점대비반등(%)": st.column_config.NumberColumn("저점대비반등(%)", format="%+.1f%%",
                            help="선택 기간 내 최저가(바닥) 대비 현재가 상승률. 바닥 회복 정도."),
                        "RSI": st.column_config.NumberColumn("RSI", format="%d",
                            help="0~100 과매수/과매도 지표. 30 이하면 과매도."),
                        "회복근거": st.column_config.TextColumn("회복근거", width="large",
                            help="회복점수에 반영된 신호 목록"),
                    },
                )
            else:
                # 구버전 Streamlit: 숫자 컬럼이면 머리글 클릭 정렬이 숫자로 동작(서식만 미적용)
                st.dataframe(dd_df, use_container_width=True, hide_index=True,
                             height=min(640, 80 + len(df_rows) * 35))
            st.caption("💡 컬럼 머리글을 클릭하면 **숫자 기준 오름차순/내림차순 정렬**됩니다. "
                       "🩹회복점수 = 기술 신호 + 반등 위치 + RSI + 테마 온기 종합 (🟢70↑ 유력 · 🟡50↑ 조짐 · ⚪30↑ 관찰 · 🔴30↓ 바닥 미확인). "
                       "상세 차트·수급·재무는 '🔬 개별 기업 정밀 진단' 탭에서 확인하세요.")
            st.download_button("⬇️ 결과 CSV 저장", dd_df.to_csv(index=False).encode("utf-8-sig"),
                               "낙폭과대_스캔.csv", "text/csv")
            
            # 🤖 [NEW] AI 회복 검증 — 상위 후보의 '하락 원인(일회성 vs 구조적)'과 테마 회복 가능성을 검색으로 교차 확인
            st.markdown("---")
            _top_n = min(10, len(rows))
            _top_rows = sorted(rows, key=lambda r: r.get("_rec_score", 0), reverse=True)[:_top_n]
            if st.button(f"🤖 AI 회복 검증 — 회복점수 상위 {_top_n}개 종목의 하락 원인·테마 전망 분석 (실시간 검색)",
                         use_container_width=True, key="dd_ai_btn"):
                if not api_key_input:
                    st.error("좌측 사이드바에 Gemini API 키를 입력해주세요.")
                else:
                    _facts = "\n".join(
                        f"- {r['name']} ({r['code']}/{r['market']}/{r.get('sector','-')}): "
                        f"낙폭 {r['drawdown']:.1f}% · 저점대비반등 {r.get('rebound','-')}% · RSI {r.get('rsi','-')} · "
                        f"회복점수 {r.get('_rec_score',0)}점 · 신호[{r.get('_rec_why','-')}] · 업종온기 {r.get('_heat','-')}%"
                        for r in _top_rows)
                    _prompt = f"""당신은 낙폭과대 역발상(컨트래리언) 전략 전문 펀드매니저입니다. 아래는 우리 시스템이 실측한 낙폭과대 종목 데이터입니다.

[검증된 실데이터]
{_facts}

반드시 '구글 검색(Google Search)'으로 각 종목의 최근 뉴스·공시를 확인한 뒤, 종목별로 아래 형식의 마크다운 표 한 줄씩 작성하세요:
| 종목명 | 하락 원인 (검색 근거) | 원인 성격 | 테마/업황 회복 전망 | 회복 가능성 |
- '원인 성격'은 [일회성 악재 / 수급·시장 동반 하락 / 구조적 악화] 중 택1.
- '회복 가능성'은 [상/중/하] + 5단어 이내 근거.
- 구조적 악화(실적 붕괴·산업 사양화·재무 위험)로 판단되면 회복 가능성 '하'로 솔직하게 평가할 것.
- 검색으로 확인 안 되는 내용은 '확인 불가'로 적고 지어내지 말 것.
표 아래에 '🏆 최종 회복 유력 TOP 3'를 이유와 함께 3줄로 요약. 마지막 줄에 '※ 투자 조언이 아닌 참고용' 표기."""
                    with st.spinner("🔍 AI가 종목별 하락 원인과 테마 전망을 실시간 검색으로 교차 확인 중... (10~20초)"):
                        _ai_out = None
                        try:
                            _g_res = _genai_generate(_prompt, api_key_input, grounding=True)
                            if _g_res.candidates and _g_res.candidates[0].content.parts:
                                _ai_out = _g_res.text
                        except Exception:
                            _ai_out = None
                        if not _ai_out:   # 그라운딩 실패 → 일반 모델 폴백 (지어내기 방지 지침 포함)
                            _ai_out = "⚠️ 실시간 검색 연동에 실패해 시스템 실데이터 기준으로만 평가합니다.\n\n" + ask_gemini(
                                _prompt + "\n\n(검색이 불가하니 위 실데이터의 기술 신호만으로 보수적으로 평가하고, 뉴스성 내용은 '확인 불가'로 표기할 것)", api_key_input)
                    st.session_state.dd_ai_result = _ai_out
            if st.session_state.get("dd_ai_result"):
                with st.container(border=True):
                    st.markdown("#### 🤖 AI 회복 검증 리포트")
                    st.markdown(st.session_state.dd_ai_result)

elif selected_menu == "🧭 AI 통합 투자 발굴기 (테스트)":
    st.markdown("## 🧭 AI 통합 투자 발굴기  <span style='font-size:0.5em;color:#94a3b8;'>BETA</span>", unsafe_allow_html=True)
    st.caption("시장 분위기(신호등·VIX·공포탐욕) + 테마/정치 + 차트 + 펀더멘털 + 공매도/신용 + 뉴스 본문 AI 판정 + "
               "**실적·목표가 컨센서스 + 매크로→섹터 틸트 + 52주 신고가·시장 상대강도(RS)·MFI 자금흐름·유동성/변동성 필터**를 한 번에 융합하고, **관리종목·거래정지·투자경보는 자동 제외**한 뒤 "
               "**단기·중기·장기 투자 후보를 자동 분류**합니다.")

    # 세션 상태 초기화
    for _k, _v in [("finder_results", None), ("finder_mood", None),
                   ("finder_radar", None), ("finder_brief", None), ("finder_meta", None),
                   ("finder_excluded", None), ("finder_macro", None), ("finder_news_diag", None),
                   ("finder_new_codes", None), ("finder_prev_codes", None)]:
        if _k not in st.session_state:
            st.session_state[_k] = _v

    # ── 0) 오늘의 시장 분위기 한 줄 ──
    with st.spinner("시장 분위기 진단 중..."):
        mood = get_market_mood()
    _mc = {"🟢": "#16a34a", "🟡": "#f59e0b", "🔴": "#dc2626"}.get(mood["light"], "#888")
    _risk_txt = ("공격적(위험선호)" if mood["risk_on"] >= 0.3
                 else "방어적(위험회피)" if mood["risk_on"] <= -0.3 else "중립")
    mc1, mc2, mc3, mc4 = st.columns(4)
    mc1.metric(f"{mood['light']} 시장 국면", mood["title"], _risk_txt, delta_color="off")
    if isinstance(mood.get("kospi"), dict):
        mc2.metric(f"{mood['kospi']['light']} 코스피", f"{mood['kospi']['price']:,.1f}", f"{mood['kospi']['pct']:+.2f}%")
    if isinstance(mood.get("kosdaq"), dict):
        mc3.metric(f"{mood['kosdaq']['light']} 코스닥", f"{mood['kosdaq']['price']:,.1f}", f"{mood['kosdaq']['pct']:+.2f}%")
    _fng = mood.get("fng")
    mc4.metric("😨 공포탐욕 / VIX", f"{_fng if _fng is not None else '-'} · VIX {mood.get('vix') if mood.get('vix') is not None else '-'}",
               mood.get("fng_rating") or "-", delta_color="off")

    st.divider()

    # ── 1) 검색 조건 ──
    fc1, fc2 = st.columns([1, 1])
    with fc1:
        horizon_focus = st.radio(
            "⏱️ 투자 기간",
            ["🧠 전체 (자동 분류)", "🔥 단기 (스윙)", "⚖️ 중기 (추세·테마)", "💎 장기 (가치·우량)"],
            help="‘전체’를 고르면 모든 후보를 단기/중기/장기로 자동 분류해 한 번에 보여줍니다.",
        )
    with fc2:
        scope_label = st.radio("🌍 시장 범위", ["🇰🇷 국내만", "🇰🇷+🇺🇸 국내·미국", "🇺🇸 미국만"], horizontal=True)
    scope = ("kr" if scope_label.startswith("🇰🇷 국내만")
             else "us" if scope_label.startswith("🇺🇸 미국만")
             else "kr_us")

    fc3, fc4 = st.columns([2, 1])
    with fc3:
        theme_focus = st.text_input("🎯 관심 테마·키워드 (선택)", placeholder="예: AI 반도체 / 방산 / 원자력 / 로봇 / 바이오")
    with fc4:
        depth = st.selectbox("🔬 탐색 깊이", ["빠르게 (TOP 100)", "표준 (TOP 200)", "정밀 (TOP 300)"], index=2)
    # (국내 거래대금 상위 N, 미국 상위 N, 펀더멘털 보강 상한, 뉴스 수집 종목 수)
    depth_cfg = {
        "빠르게 (TOP 100)": (100, 25, 70, 12),
        "표준 (TOP 200)": (200, 40, 110, 20),
        "정밀 (TOP 300)": (300, 60, 150, 28),
    }[depth]
    kr_n, us_n, phaseb_cap, news_n = depth_cfg

    want_long = ("전체" in horizon_focus) or ("장기" in horizon_focus)

    st.caption("⏳ 기본값인 정밀(TOP 300)은 거래대금 상위 300종목의 차트·펀더멘털·공매도·뉴스 본문까지 한 번에 수집해 3~6분 걸릴 수 있어요. 결과·기사 본문은 캐시되어 재실행은 훨씬 빠릅니다.")

    if st.button("🧭 통합 검색 시작", type="primary", use_container_width=True):
        if not api_key_input:
            st.warning("⚠️ AI 테마 분석·후보 발굴을 위해 좌측 사이드바에 Gemini API 키가 필요합니다.")
        else:
            # 1) 뉴스 + 폴리마켓(정치/매크로) 수집
            with st.spinner("실시간 뉴스·예측시장(정치/매크로) 수집 중..."):
                try:
                    news_titles = [a["title"] for a in (get_latest_naver_news() or [])][:18]
                except Exception:
                    news_titles = []
                poly_lines = []
                try:
                    pm = fetch_polymarket_markets(
                        search="election president fed rate cut tariff war ceasefire recession", limit=20)
                    for m in (pm.get("data") or [])[:12]:
                        q = m.get("question", "")
                        yp = m.get("yes_prob")
                        ko = _gtx_translate_en_ko(q) if q else q
                        poly_lines.append(f"{ko} (확률 {yp:.0f}%)" if yp is not None else ko)
                except Exception:
                    poly_lines = []

            # 2) AI 테마/정치 레이더
            with st.spinner("AI가 오늘의 핵심 테마·정치 이벤트를 종합하는 중..."):
                radar = get_theme_politics_radar(api_key_input, tuple(news_titles), tuple(poly_lines))

            # 3) 후보 풀 구성
            with st.spinner("후보 종목 풀 구성 중 (시총 상위 + 테마 리더 + 가치주)..."):
                pool = build_finder_candidates(
                    api_key_input, scope, theme_focus, radar.get("themes"),
                    kr_n, us_n, want_long)
            if not pool:
                st.error("❌ 후보 종목을 구성하지 못했습니다. 잠시 후 다시 시도해 주세요.")
            else:
                # 3-1) 리스크 하드필터 — 관리종목·투자경보·거래정지 종목은 후보에서 제외
                excluded = []
                try:
                    excl_names, excl_reason = get_finder_exclusion_set()
                except Exception:
                    excl_names, excl_reason = set(), {}
                if excl_names:
                    for cd in list(pool.keys()):
                        nm = re.sub(r"\s+", "", str(pool[cd]["name"]))
                        if nm in excl_names:
                            excluded.append((pool[cd]["name"], excl_reason.get(nm, "관리/경보")))
                            pool.pop(cd, None)
                st.session_state["finder_excluded"] = excluded

                # 매크로 지표(섹터 틸트용) — 1회 수집
                macro_ind = get_macro_indicators() or {}
                st.session_state["finder_macro"] = macro_ind
                mood["_idx20"] = get_index_ret20()   # 시장 상대강도(RS) 기준선(코스피·S&P 20일 수익률)

                items = list(pool.items())  # [(code, info)]
                # 4) Phase A — 기술적 분석 (병렬)
                progressA = st.progress(0.0)
                statusA = st.empty()
                techs = {}
                doneA, totalA = 0, len(items)

                def _runA(it):
                    code, info = it
                    return code, _finder_tech(info["name"], code)

                with concurrent.futures.ThreadPoolExecutor(max_workers=8) as ex:
                    for fut in concurrent.futures.as_completed({ex.submit(_runA, it): it for it in items}):
                        code, res = fut.result()
                        doneA += 1
                        if res:
                            techs[code] = res
                        progressA.progress(min(1.0, doneA / totalA))
                        statusA.text(f"📈 1/2 차트·수급 분석 중... ({doneA}/{totalA})")
                progressA.empty(); statusA.empty()

                # 사전 점수(밸류 미반영) → Phase B(가치 보강) 우선순위 선정
                prelim = {}
                for code, tech in techs.items():
                    th = pool[code].get("theme") is not None
                    _sc, _, top, _, _, _ = score_one(tech, None, mood, theme_hit=th)
                    prelim[code] = top
                kr_codes = [c for c in techs if str(c).isdigit()]
                must = [c for c in kr_codes if {"theme", "value"} & pool[c]["src"]]   # 테마/가치 후보는 반드시 보강
                rest = sorted([c for c in kr_codes if c not in must],
                              key=lambda c: prelim.get(c, 0), reverse=True)
                phaseb = (must + rest)[:phaseb_cap]

                # 5) Phase B — 가치/펀더멘털 + 공매도·신용 + 컨센서스 리비전 보강 (국내, 병렬)
                vmap, rmap, cmap = {}, {}, {}
                if phaseb:
                    progressB = st.progress(0.0)
                    statusB = st.empty()
                    doneB, totalB = 0, len(phaseb)

                    def _runB(c):
                        return c, _finder_value(c), _finder_risk(c), get_consensus_signal(c)

                    with concurrent.futures.ThreadPoolExecutor(max_workers=6) as ex:
                        for fut in concurrent.futures.as_completed({ex.submit(_runB, c): c for c in phaseb}):
                            try:
                                c, vm, rk, cs = fut.result()
                                vmap[c] = vm
                                rmap[c] = rk
                                cmap[c] = cs
                            except Exception:
                                pass
                            doneB += 1
                            progressB.progress(min(1.0, doneB / totalB))
                            statusB.text(f"💎 2/2 펀더멘털·공매도·신용·컨센서스 보강 중... ({doneB}/{totalB})")
                    progressB.empty(); statusB.empty()

                # 6) 1차 점수 + 자동 분류 (리스크·컨센서스·매크로틸트 반영, 뉴스 전)
                enriched = []
                by_code = {}
                for code, tech in techs.items():
                    th_name = pool[code].get("theme")
                    th = th_name is not None
                    tilt_pts, tilt_notes = macro_tilt_for(tech.get("섹터", ""), macro_ind)
                    cons = cmap.get(code)
                    scores, horizon, top, grade, reasons, risk_flags = score_one(
                        tech, vmap.get(code), mood, theme_hit=th, risk=rmap.get(code),
                        sector_tilt=tilt_pts, consensus=cons)
                    r = dict(tech)
                    r["_scores"] = scores
                    r["_horizon"] = horizon
                    r["_top"] = top
                    r["_grade"] = grade
                    r["_reasons"] = reasons
                    r["_theme"] = th_name
                    r["_risk"] = rmap.get(code)
                    r["_risk_flags"] = risk_flags
                    r["_tilt"] = tilt_pts
                    r["_tilt_notes"] = tilt_notes
                    r["_consensus"] = cons
                    r["_upside"] = (((_f_num(tech.get("목표가_컨센서스")) / _f_num(tech.get("현재가"))) - 1) * 100
                                    if (_f_num(tech.get("목표가_컨센서스")) and _f_num(tech.get("현재가")) and _f_num(tech.get("현재가")) > 0) else None)
                    enriched.append(r)
                    by_code[code] = r

                # 6-1) 표시 대상(기간별 상위 10, 재정렬 여유분 포함)에 최신 뉴스 자동 첨부
                def _rebucket(lst):
                    b = {"단기": [], "중기": [], "장기": []}
                    for x in lst:
                        b[x["_horizon"]].append(x)
                    for hz in b:
                        b[hz].sort(key=lambda x: x["_top"], reverse=True)
                    return b

                buckets_full = _rebucket(enriched)
                news_targets, excerpt_codes = [], set()
                for hz in ("단기", "중기", "장기"):
                    for i, r in enumerate(buckets_full[hz][:news_n]):
                        tk = r.get("티커")
                        news_targets.append(tk)
                        if i < 10:               # 본문 발췌는 상위 10개만(속도)
                            excerpt_codes.add(tk)
                news_targets = list(dict.fromkeys([t for t in news_targets if t]))
                if news_targets:
                    code2name = {r.get("티커"): r.get("종목명") for r in enriched}
                    newsmap = {}
                    progressN = st.progress(0.0)
                    statusN = st.empty()
                    doneN, totalN = 0, len(news_targets)
                    # [속도개선] 워커 확대(6→12) + 전체 시간 상한(deadline). 일부 종목의 뉴스 API가
                    #            먹통이어도 그 '느린 꼬리'가 수집 전체를 붙잡지 않도록, 22초 안에 못 받은
                    #            종목은 빈 뉴스로 처리하고 즉시 다음 단계로 넘어간다.
                    exN = concurrent.futures.ThreadPoolExecutor(max_workers=12)
                    fmap = {exN.submit(get_stock_news, c, code2name.get(c, ""), 4): c for c in news_targets}
                    try:
                        for fut in concurrent.futures.as_completed(fmap, timeout=22):
                            c = fmap[fut]
                            try:
                                newsmap[c] = fut.result()
                            except Exception:
                                newsmap[c] = []
                            doneN += 1
                            progressN.progress(min(1.0, doneN / totalN))
                            statusN.text(f"📰 종목별 최신 뉴스 수집 중... ({doneN}/{totalN})")
                    except concurrent.futures.TimeoutError:
                        statusN.text(f"📰 뉴스 수집 시간 초과 — 받은 {doneN}/{totalN}건으로 진행합니다.")
                    for c in news_targets:          # 시간 내 못 받은 종목은 빈 뉴스 처리
                        newsmap.setdefault(c, [])
                    exN.shutdown(wait=False)        # 남은 작업은 백그라운드에 두고 UI는 즉시 진행
                    progressN.empty(); statusN.empty()
                    for c in newsmap:
                        if c in by_code:
                            by_code[c]["_news"] = newsmap[c]

                    # 6-1b) 기사 본문 발췌 병렬 수집 → 판정 정확도 향상 (상위 종목만)
                    link_set = []
                    for c in news_targets:
                        if c not in excerpt_codes:
                            continue
                        for n in (newsmap.get(c) or []):
                            lk = n.get("link")
                            if lk:
                                link_set.append(lk)
                    link_set = list(dict.fromkeys(link_set))
                    excerpt_map = {}
                    if link_set:
                        progressE = st.progress(0.0)
                        statusE = st.empty()
                        doneE, totalE = 0, len(link_set)
                        # [속도개선] 본문 발췌도 워커 확대(8→14) + 전체 시간 상한(18초).
                        #            본문은 호재/악재 '판정 정확도 보강용'이라 일부 누락돼도 분석은 정상 진행된다.
                        exE = concurrent.futures.ThreadPoolExecutor(max_workers=14)
                        emap = {exE.submit(fetch_article_excerpt, lk): lk for lk in link_set}
                        try:
                            for fut in concurrent.futures.as_completed(emap, timeout=18):
                                lk = emap[fut]
                                try:
                                    excerpt_map[lk] = fut.result()
                                except Exception:
                                    excerpt_map[lk] = ""
                                doneE += 1
                                progressE.progress(min(1.0, doneE / totalE))
                                statusE.text(f"📄 기사 본문 분석 중... ({doneE}/{totalE})")
                        except concurrent.futures.TimeoutError:
                            statusE.text(f"📄 본문 분석 시간 초과 — 받은 {doneE}/{totalE}건으로 진행합니다.")
                        exE.shutdown(wait=False)
                        progressE.empty(); statusE.empty()
                        # 발췌를 뉴스 항목에 부착 (모바일 API가 준 발췌가 있으면 보존, 본문 추출 성공 시 갱신)
                        for c in newsmap:
                            for n in (newsmap.get(c) or []):
                                fetched = excerpt_map.get(n.get("link"))
                                if fetched:
                                    n["excerpt"] = fetched

                    # 6-2) AI 뉴스 호재/악재 판정 (제목 + 본문 발췌, 개별 기사 단위) → 점수 재반영
                    sent_items = []
                    for c in news_targets:
                        nz = newsmap.get(c) or []
                        arts = tuple(
                            ((n.get("title") or "").strip(), (excerpt_map.get(n.get("link")) or n.get("excerpt") or ""))
                            for n in nz if n.get("title")
                        )
                        if arts:
                            sent_items.append((c, code2name.get(c, ""), arts))
                    if sent_items:
                        with st.spinner("AI가 제목·본문을 함께 읽고 호재/악재를 판정하는 중..."):
                            sentmap = classify_news_sentiment(api_key_input, tuple(sent_items))
                        for c, info in (sentmap or {}).items():
                            r = by_code.get(c)
                            if not r:
                                continue
                            r["_news_label"] = info.get("label")
                            r["_news_score"] = info.get("score")
                            r["_news_reason"] = info.get("reason")
                            r["_news_conf"] = info.get("confidence")
                            r["_news_auto_neutral"] = info.get("auto_neutral", False)
                            # 개별 기사 라벨을 해당 뉴스 항목에 부착 (입력 순서 일치)
                            al = info.get("article_labels") or []
                            nz = r.get("_news") or []
                            titled = [n for n in nz if n.get("title")]
                            for k, art in enumerate(al):
                                if k < len(titled):
                                    titled[k]["label"] = art[0]
                                    titled[k]["score"] = art[1]
                            # 증자/CB 희석 리스크 — 최근 기사 제목/본문에서 감지
                            _dil = False
                            for n in (r.get("_news") or []):
                                blob = (str(n.get("title", "")) + " " + str(n.get("excerpt", "")))
                                if any(k in blob for k in ["유상증자", "전환사채", "신주인수권", "BW 발행", "CB 발행", "주주배정 증자", "제3자배정"]):
                                    _dil = True
                                    n["dilution"] = True
                            r["_dilution"] = _dil
                            # 뉴스 점수·매크로틸트·컨센서스·증자리스크 반영해 재채점 (자동중립이면 score 0)
                            th_name = pool[c].get("theme")
                            _tilt_pts, _ = macro_tilt_for(techs[c].get("섹터", ""), macro_ind)
                            scores, horizon, top, grade, reasons, risk_flags = score_one(
                                techs[c], vmap.get(c), mood, theme_hit=(th_name is not None),
                                risk=rmap.get(c), news_sent=info.get("score"),
                                sector_tilt=_tilt_pts, consensus=cmap.get(c), dilution=_dil)
                            r["_scores"] = scores
                            r["_horizon"] = horizon
                            r["_top"] = top
                            r["_grade"] = grade
                            r["_reasons"] = reasons

                st.session_state.finder_results = enriched
                # [신규 종목 추적] 직전 검색에 없던 티커 = 이번 검색의 신규 진입
                _cur_codes = {r.get("티커") for r in enriched if r.get("티커")}
                _prev_codes = st.session_state.get("finder_prev_codes")
                st.session_state["finder_new_codes"] = (_cur_codes - _prev_codes) if _prev_codes else set()
                st.session_state["finder_prev_codes"] = _cur_codes
                st.session_state.finder_mood = mood
                st.session_state.finder_radar = radar
                st.session_state.finder_meta = (scope, depth, theme_focus, len(enriched), news_n)
                # 뉴스 수집/판정 진단 (왜 비는지 확인용)
                _n_targets = len(news_targets)
                _n_with_news = sum(1 for r in enriched if r.get("_news"))
                _n_articles = sum(len(r.get("_news") or []) for r in enriched)
                _n_labeled = sum(1 for r in enriched if r.get("_news_label"))
                st.session_state["finder_news_diag"] = (_n_targets, _n_with_news, _n_articles, _n_labeled)

                # 7) AI 통합 브리핑
                buckets_tmp = {"단기": [], "중기": [], "장기": []}
                for r in enriched:
                    buckets_tmp[r["_horizon"]].append((r.get("종목명"), r["_top"]))
                for hz in buckets_tmp:
                    buckets_tmp[hz].sort(key=lambda x: x[1], reverse=True)
                with st.spinner("AI 통합 전략 브리핑 작성 중..."):
                    st.session_state.finder_brief = get_finder_briefing(
                        api_key_input, mood, radar, buckets_tmp)

    # ── 결과 렌더 ──
    radar = st.session_state.get("finder_radar")
    if radar and radar.get("themes"):
        st.markdown("### 🛰️ 오늘의 테마·정치 레이더")
        if radar.get("mood_comment"):
            st.info(f"🗣️ {radar['mood_comment']}")
        _hz_color = {"단기": "#dc2626", "중기": "#2563eb", "장기": "#16a34a"}
        rcols = st.columns(min(len(radar["themes"]), 5) or 1)
        for i, t in enumerate(radar["themes"][:5]):
            with rcols[i % len(rcols)]:
                c = _hz_color.get(t["horizon"], "#888")
                st.markdown(
                    f"<div style='border:1px solid #e5e7eb;border-left:4px solid {c};border-radius:10px;"
                    f"padding:10px 12px;margin-bottom:8px;background:#fff;'>"
                    f"<div style='font-weight:800;font-size:14px;color:#1e293b;'>{t['theme']}</div>"
                    f"<div style='display:inline-block;font-size:11px;font-weight:700;color:#fff;background:{c};"
                    f"border-radius:6px;padding:1px 7px;margin:4px 0;'>{t['horizon']}</div>"
                    f"<div style='font-size:12px;color:#475569;line-height:1.4;'>{t['reason']}</div></div>",
                    unsafe_allow_html=True)

    if st.session_state.get("finder_brief"):
        with st.expander("🧠 AI 통합 투자 전략 브리핑", expanded=True):
            st.markdown(st.session_state.finder_brief)
            st.caption("※ 본 내용은 투자 권유가 아닌 참고 정보이며, 최종 판단과 책임은 투자자 본인에게 있습니다.")

    results = st.session_state.get("finder_results")
    if results:
        buckets = {"단기": [], "중기": [], "장기": []}
        for r in results:
            buckets[r["_horizon"]].append(r)
        for hz in buckets:
            buckets[hz].sort(key=lambda x: x["_top"], reverse=True)

        meta = st.session_state.get("finder_meta")
        if meta:
            st.success(f"✅ 총 {meta[3]}개 종목 분석 완료 — 단기 {len(buckets['단기'])} · 중기 {len(buckets['중기'])} · 장기 {len(buckets['장기'])}개로 자동 분류")

        # 매크로 → 섹터 틸트 배너 (오늘 매크로가 어느 섹터에 유·불리한지)
        _mnotes = macro_regime_notes(st.session_state.get("finder_macro") or get_macro_indicators())
        if _mnotes:
            st.info("🧭 **오늘의 매크로 → 섹터 틸트** (점수에 반영): " + " ｜ ".join(_mnotes))

        # 하드필터로 제외된 위험 종목 안내
        _excl = st.session_state.get("finder_excluded") or []
        if _excl:
            def _prc_excluded():
                st.caption("아래 종목은 상장폐지·거래정지 등 고위험으로 분류돼 후보에서 제외됐습니다.")
                st.dataframe(pd.DataFrame([{"종목명": n, "사유": rs} for n, rs in _excl]),
                             use_container_width=True, hide_index=True)
            _register_popup("excluded", _prc_excluded)
            _popup_button(f"🛑 리스크 하드필터 제외 종목 {len(_excl)}개 보기", "excluded", f"🛑 제외된 종목 {len(_excl)}개", key="btn_excluded")

        # 뉴스 수집/판정 진단 (뉴스가 비는 원인 확인)
        _diag = st.session_state.get("finder_news_diag")
        if _diag:
            _t, _wn, _na, _lb = _diag
            if _na == 0:
                st.warning(f"📰 뉴스 진단: 대상 {_t}종목에서 **기사 0건 수집** — 뉴스 소스가 현재 환경에서 차단된 상태입니다. (테마/점수는 정상)")
            elif _lb == 0:
                st.warning(f"📰 뉴스 진단: 기사 {_na}건 수집됐으나 **AI 판정 0건** — Gemini API 키/호출을 확인하세요.")
            else:
                st.caption(f"📰 뉴스 진단: 대상 {_t}종목 · 기사 {_na}건 수집 · {_wn}종목에 부착 · AI 판정 {_lb}종목")

        # ── [발굴기 확장] 결과 내보내기 · 신규 종목 · 필터/정렬 ─────────────
        _all_buckets = {hz: list(buckets[hz]) for hz in buckets}   # 필터 전 전체(내보내기·신규 판정용)

        # (1) 결과 내보내기 (CSV·엑셀) — 화면 필터와 무관하게 분석된 전체 종목 저장
        _exp_df = _finder_export_df(_all_buckets)
        if not _exp_df.empty:
            _xlsx_bytes = None
            try:
                import io as _io
                _buf = _io.BytesIO()
                with pd.ExcelWriter(_buf, engine="openpyxl") as _xw:
                    for _hz in ("단기", "중기", "장기"):
                        _dfh = _exp_df[_exp_df["기간분류"] == _hz].drop(columns=["기간분류"])
                        (_dfh if not _dfh.empty else pd.DataFrame({"안내": ["해당 종목 없음"]})).to_excel(_xw, sheet_name=_hz, index=False)
                _xlsx_bytes = _buf.getvalue()
            except Exception:
                _xlsx_bytes = None
            _stamp = datetime.now().strftime("%Y%m%d_%H%M")
            _ec1, _ec2, _ec3 = st.columns([1, 1, 2.6], vertical_alignment="center")
            _ec1.download_button("💾 CSV 내보내기", _exp_df.to_csv(index=False).encode("utf-8-sig"),
                                 file_name=f"통합발굴_{_stamp}.csv", mime="text/csv",
                                 use_container_width=True, key="finder_csv")
            if _xlsx_bytes:
                _ec2.download_button("📊 엑셀(xlsx)", _xlsx_bytes, file_name=f"통합발굴_{_stamp}.xlsx",
                                     mime="application/vnd.openpyxlformats-officedocument.spreadsheetml.sheet",
                                     use_container_width=True, key="finder_xlsx")
            else:
                _ec2.caption("엑셀 엔진 미설치 → CSV 이용")
            _ec3.caption(f"📋 분석된 전체 {len(_exp_df)}종목 저장(엑셀은 단기·중기·장기 시트 분리). 아래 화면 필터와 무관하게 전량 내보냅니다.")

        # (2) 직전 검색 대비 신규 진입 종목
        _new_codes = st.session_state.get("finder_new_codes") or set()
        if _new_codes:
            _new_names = list(dict.fromkeys(
                r.get("종목명") for hz in _all_buckets for r in _all_buckets[hz] if r.get("티커") in _new_codes))
            if _new_names:
                _shown = ", ".join(_new_names[:12])
                _more = f" 외 {len(_new_names) - 12}개" if len(_new_names) > 12 else ""
                st.success(f"🆕 **직전 검색 대비 신규 진입 {len(_new_names)}종목** — {_shown}{_more}  "
                           "*(같은 조건으로 다시 돌릴수록 정확합니다)*")

        # (3) 결과 필터 · 정렬
        with st.container(border=True):
            _fc_a, _fc_b = st.columns([2, 3])
            with _fc_a:
                _sort_mode = st.selectbox("⬇️ 정렬 기준",
                                          ["적합도 점수", "기대수익(컨센)", "손익비(R:R)", "20일 모멘텀"], key="finder_sort")
            with _fc_b:
                _cb1, _cb2, _cb3 = st.columns(3)
                _hide_bad = _cb1.checkbox("🔴 악재 숨기기", key="finder_hide_bad")
                _hide_risk = _cb2.checkbox("🩸 고위험 숨기기", key="finder_hide_risk",
                                           help="공매도 과다·신용 과다·증자/CB·리스크 적색 종목 제외")
                _hide_illiq = _cb3.checkbox("💧 저유동성 숨기기", key="finder_hide_illiq")
            _min_score = st.slider("최소 적합도 점수", 0, 80, 0, 5, key="finder_min_score")

        # 필터·정렬 적용 → 이후 탭/카드는 이 결과를 사용
        _filtered = {}
        for _hz in buckets:
            _lst = [r for r in buckets[_hz]
                    if (r.get("_top", 0) or 0) >= _min_score and not _finder_hide(r, _hide_bad, _hide_risk, _hide_illiq)]
            _lst.sort(key=lambda r: _finder_sort_val(r, _sort_mode), reverse=True)
            _filtered[_hz] = _lst
        _removed = sum(len(buckets[h]) for h in buckets) - sum(len(_filtered[h]) for h in _filtered)
        if _removed > 0:
            st.caption(f"🔎 필터로 {_removed}종목 숨김 · 정렬 기준: {_sort_mode}")
        buckets = _filtered

        # 기간 포커스에 따라 기본 탭 순서 조정
        order = ["단기", "중기", "장기"]
        if "단기" in horizon_focus: order = ["단기", "중기", "장기"]
        elif "중기" in horizon_focus: order = ["중기", "단기", "장기"]
        elif "장기" in horizon_focus: order = ["장기", "중기", "단기"]
        tab_labels = {"단기": "🔥 단기 (스윙)", "중기": "⚖️ 중기 (추세·테마)", "장기": "💎 장기 (가치·우량)"}
        # 뉴스가 붙는 상위 종목만 표시 (표 전체에 뉴스 판정이 일관되게 나오도록)
        _disp_n = meta[4] if (meta and len(meta) > 4) else 20
        tabs = st.tabs([f"{tab_labels[h]}  ·  {min(len(buckets[h]), _disp_n)}" for h in order])

        for tab, hz in zip(tabs, order):
            with tab:
                picks = buckets[hz][:_disp_n]
                if not picks:
                    st.info(f"현재 분위기에서 '{hz}' 적합 종목이 충분히 포착되지 않았습니다. 탐색 깊이를 높이거나 테마 키워드를 바꿔보세요.")
                    continue
                # 요약 표
                rows = []
                for rk, r in enumerate(picks, 1):
                    _rk = r.get("_risk") or {}
                    _lvl = _rk.get("level")
                    risk_cell = (_lvl[0] if isinstance(_lvl, (list, tuple)) and _lvl else "")
                    if r.get("_risk_flags"):
                        risk_cell = (risk_cell + " " + " ".join(r["_risk_flags"])).strip()
                    if not risk_cell:
                        risk_cell = ("🟢" if str(r.get("티커", "")).isdigit() else "—")
                    _nl = r.get("_news_label")
                    news_cell = {"호재": "🟢 호재", "악재": "🔴 악재", "중립": "⚪ 중립"}.get(_nl, "—")
                    if _nl and r.get("_news_auto_neutral"):
                        news_cell = "⚪ 중립(저신뢰)"
                    # 컨센서스 셀: 목표가 상/하향 + 기대수익(괴리율)
                    _cons = r.get("_consensus") or {}
                    _up = r.get("_upside")
                    _rev = _cons.get("revision_dir")
                    _cons_cell = {"상향": "🔼상향", "하향": "🔽하향", "중립": "≈중립"}.get(_rev, "")
                    if _up is not None:
                        _cons_cell = (_cons_cell + f" {_up:+.0f}%").strip()
                    if not _cons_cell:
                        _cons_cell = "—"
                    if r.get("_dilution"):
                        _cons_cell += " 🔻증자"
                    _theme_cell = (r.get("_theme") or r.get("섹터") or "-")
                    _theme_cell = str(_theme_cell)
                    if len(_theme_cell) > 14:
                        _theme_cell = _theme_cell[:14] + "…"
                    _rr = _finder_rr(r)
                    if _rr and _rr.get("rr") is not None:
                        _rr_cell = f"{_rr['rr']:.1f}배 (▲{_rr['up']:.0f}%/▼{_rr['dn']:.0f}%)"
                    elif _rr and _rr.get("tag"):
                        _rr_cell = _rr["tag"]
                    else:
                        _rr_cell = "—"
                    _nm_cell = ("🆕 " if r.get("티커") in _new_codes else "") + str(r.get("종목명") or "")
                    rows.append({
                        "순위": rk, "등급": r["_grade"], f"{hz}점수": r["_top"],
                        "종목명": _nm_cell, "시장": r.get("시장", ""),
                        "테마/섹터": _theme_cell,
                        "현재가": (f"${r['현재가']:,.2f}" if not str(r.get('티커','')).isdigit() else f"{int(r.get('현재가',0)):,}원"),
                        "RSI": (f"{r['RSI']:.0f}" if _f_num(r.get('RSI')) is not None else "-"),
                        "손익비(R:R)": _rr_cell,
                        "컨센서스": _cons_cell,
                        "공매도/신용": risk_cell,
                        "뉴스(AI)": news_cell,
                        "핵심근거": " · ".join(r.get("_reasons", [])) or "-",
                    })
                st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
                st.caption("⚖️ 손익비(R:R) = 현재가 진입 시 1차목표까지 상방(▲) ÷ 손절까지 하방(▼), 클수록 유리 · 🆕=직전 검색 대비 신규 진입 · "
                           "🔼/🔽 목표가 상·하향 · +%는 컨센서스 기대수익(괴리율) · 🔻증자=유상증자/CB · 🩸공매도/⚠️신용=하방 리스크 (모두 점수 반영). 컨센서스·공매도·신용은 국내만 제공.")
                st.markdown("##### 📈 상세 카드 (상위 8종목)")
                for idx, r in enumerate(picks[:8]):
                    _new_badge = "🆕 " if r.get("티커") in _new_codes else ""
                    st.markdown(
                        f"**{idx+1}. {_new_badge}{r.get('종목명')}** · {r['_grade']} · {hz} 적합도 **{r['_top']:.0f}점**  "
                        + (f"· 🏷️ {r['_theme']}" if r.get("_theme") else "")
                    )
                    if r.get("_reasons"):
                        st.caption("근거: " + " · ".join(r["_reasons"]))
                    # 손익비(R:R) + 컨센서스 + 매크로 틸트 + 증자리스크 한 줄
                    _cparts = []
                    _rr = _finder_rr(r)
                    if _rr and _rr.get("rr") is not None:
                        _cparts.append(f"⚖️ 손익비 {_rr['rr']:.1f}배 (▲{_rr['up']:.0f}% / ▼{_rr['dn']:.0f}%)")
                    elif _rr and _rr.get("tag"):
                        _cparts.append(f"⚖️ {_rr['tag']}")
                    _cons = r.get("_consensus") or {}
                    _up = r.get("_upside")
                    if _up is not None:
                        _cparts.append(f"🎯 기대수익 {_up:+.0f}% (컨센 목표가)")
                    if _cons.get("revision_dir") in ("상향", "하향"):
                        _arrow = "🔼" if _cons["revision_dir"] == "상향" else "🔽"
                        _cparts.append(f"{_arrow} 목표가 {_cons['revision_dir']}(최근 {_cons.get('report_total', 0)}건)")
                    if r.get("_tilt_notes"):
                        _t = r.get("_tilt") or 0
                        _tmark = "🟢" if _t > 0 else ("🔴" if _t < 0 else "⚪")
                        _cparts.append(f"{_tmark} 매크로: " + ", ".join(r["_tilt_notes"]))
                    if r.get("_dilution"):
                        _cparts.append("🔻 증자/CB 희석 리스크")
                    if _cparts:
                        st.caption(" ｜ ".join(_cparts))
                    # 공매도/신용 리스크 한 줄
                    _rk = r.get("_risk") or {}
                    if _rk:
                        parts = []
                        _lvl = _rk.get("level")
                        if isinstance(_lvl, (list, tuple)) and len(_lvl) == 2:
                            parts.append(f"{_lvl[0]} {_lvl[1]}")
                        if _rk.get("short_bal_ratio") is not None:
                            parts.append(f"공매도잔고 {_rk['short_bal_ratio']:.2f}%{(' '+_rk['short_bal_trend']) if _rk.get('short_bal_trend') else ''}")
                        if _rk.get("short_vol_ratio") is not None:
                            parts.append(f"당일공매도 {_rk['short_vol_ratio']:.1f}%{(' '+_rk['short_vol_trend']) if _rk.get('short_vol_trend') else ''}")
                        if _rk.get("credit_ratio") is not None:
                            parts.append(f"신용잔고율 {_rk['credit_ratio']:.2f}%")
                        if parts:
                            st.caption("🩸 리스크: " + " ｜ ".join(parts))
                    # AI 뉴스 호재/악재 판정 (종목 단위 + 신뢰도)
                    if r.get("_news_label"):
                        _emo = {"호재": "🟢", "악재": "🔴", "중립": "⚪"}.get(r["_news_label"], "⚪")
                        _ns = r.get("_news_score")
                        _sgn = f" ({_ns:+d})" if isinstance(_ns, int) and _ns != 0 else ""
                        _cf = r.get("_news_conf")
                        _cf_txt = f" · 신뢰도 {_cf:.2f}" if isinstance(_cf, (int, float)) else ""
                        _auto = " · 🔸자동 중립(저신뢰)" if r.get("_news_auto_neutral") else ""
                        _rsn = f" — {r['_news_reason']}" if r.get("_news_reason") else ""
                        st.caption(f"📰 AI 뉴스 판정: {_emo} **{r['_news_label']}**{_sgn}{_cf_txt}{_auto}{_rsn}")
                    # 공매도 추세 미니차트
                    _fig = _short_trend_figure(r.get("_risk"))
                    if _fig is not None:
                        st.plotly_chart(_fig, use_container_width=True)
                    draw_stock_card(r, api_key_str=api_key_input, is_expanded=False, key_suffix=f"finder_{hz}_{idx}")
                    # 종목별 최신 뉴스 (기사별 호재/악재 라벨 포함)
                    _news = r.get("_news")
                    if _news:
                        def _prc_news(_news=_news):
                            for nws in _news:
                                meta = " · ".join([x for x in [nws.get("source"), nws.get("date")] if x])
                                title = nws.get("title", "")
                                link = nws.get("link", "")
                                _alabel = nws.get("label")
                                _atag = {"호재": "🟢호재", "악재": "🔴악재", "중립": "⚪중립"}.get(_alabel, "")
                                _badge = f"`{_atag}` " if _atag else ""
                                _exc = (nws.get("excerpt") or "").strip()
                                _exc_html = ""
                                if _exc:
                                    _snip = _exc[:120] + ("…" if len(_exc) > 120 else "")
                                    _exc_html = f"  \n  <span style='color:#64748b;font-size:12px;'>📄 {_snip}</span>"
                                _meta_html = f"  \n  <span style='color:#94a3b8;font-size:12px;'>{meta}</span>" if meta else ""
                                if link:
                                    st.markdown(f"- {_badge}[{title}]({link})" + _meta_html + _exc_html, unsafe_allow_html=True)
                                else:
                                    st.markdown(f"- {_badge}{title}" + _meta_html + _exc_html, unsafe_allow_html=True)
                        _register_popup(f"news_{hz}_{idx}", _prc_news)
                        _popup_button(f"📰 {r.get('종목명')} 최신 뉴스 {len(_news)}건 보기", f"news_{hz}_{idx}", f"📰 {r.get('종목명')} 최신 뉴스", key=f"btn_news_{hz}_{idx}")
                    elif "_news" in r:
                        st.caption("📰 최근 뉴스를 찾지 못했습니다.")
                    st.markdown("")
    else:
        st.info("위에서 조건을 고르고 **‘통합 검색 시작’**을 누르면, 시장 분위기·테마·차트·펀더멘털을 종합해 기간별 투자 후보를 찾아드립니다.")


elif selected_menu == "🏛️ 국민연금 5% 대량보유 픽":
    st.markdown("## 🏛️ 국민연금 5% 대량보유 픽")
    st.write("국민연금이 대량 보유한 국내/해외 핵심 기업 포트폴리오를 실시간 스크래핑하여 추적합니다.")

    # 🔑 [NEW] DART 오픈API 키 (선택) — FnGuide/WiseReport가 모두 차단될 때 공식 DART 공시로 조회
    with st.expander("🔑 DART 오픈API 키 설정 (선택 — 차단 우회용 공식 소스)"):
        st.caption("무료 발급: [opendart.fss.or.kr](https://opendart.fss.or.kr) → 인증키 신청 (일 20,000건 한도). "
                   "키를 입력하면 금융감독원 공식 '대량보유 상황보고' API를 최우선 소스로 사용합니다. "
                   "키는 이 세션에만 유지되며 파일로 저장되지 않습니다.")
        st.text_input("DART API 인증키 (40자)", type="password", key="dart_api_key",
                      placeholder="발급받은 인증키를 붙여넣으세요")
    _dart_key = (st.session_state.get("dart_api_key") or "").strip()

    # 🔍 [NEW] 실시간 종목 검색 — 고정 리스트에 없는 종목도 국민연금 지분율을 즉시 조회
    st.markdown("#### 🔍 종목 실시간 검색")
    st.caption("종목명 또는 6자리 코드를 입력하면 해당 종목의 국민연금 지분율을 실시간 조회합니다. "
               "아래 고정 리스트에 없는 코스피/코스닥 종목도 검색 가능합니다. "
               "(소스 체인: DART 공시(키 보유 시) → FnGuide → WiseReport 순으로 자동 우회)")
    nps_sc1, nps_sc2 = st.columns([7, 3])
    nps_q = nps_sc1.text_input("종목명 또는 6자리 코드", placeholder="예: 삼성전자 / 005930 / 에코프로",
                               key="nps_search_q", label_visibility="collapsed")
    _nps_target = None  # (종목명, 코드)
    if nps_q and nps_q.strip():
        _qs = nps_q.strip()
        _listing = get_krx_name_code_list()
        if re.fullmatch(r"\d{6}", _qs):
            _nm = _qs
            if not _listing.empty:
                _hit = _listing[_listing['Code'] == _qs]
                if not _hit.empty:
                    _nm = _hit['Name'].iloc[0]
            _nps_target = (_nm, _qs)
        elif _listing.empty:
            st.warning("⚠️ 종목 목록을 불러오지 못했습니다 (FDR 응답 없음). 6자리 종목코드로 검색해 주세요.")
        else:
            _exact = _listing[_listing['Name'].str.lower() == _qs.lower()]
            _cand = _exact if not _exact.empty else _listing[_listing['Name'].str.contains(re.escape(_qs), case=False, na=False)]
            if _cand.empty:
                st.warning(f"'{_qs}' 검색 결과가 없습니다. 종목명 철자 또는 6자리 코드를 확인해 주세요.")
            elif len(_cand) == 1:
                _nps_target = (_cand['Name'].iloc[0], _cand['Code'].iloc[0])
            else:
                _cand = _cand.head(20)
                _pick = st.selectbox(f"검색 결과 {len(_cand)}건 — 종목을 선택하세요 (최대 20건 표시)",
                                     [f"{r.Name} ({r.Code})" for r in _cand.itertuples()], key="nps_search_pick")
                _pm = re.search(r"\((\d{6})\)$", _pick)
                if _pm:
                    _nps_target = (_pick[:_pick.rfind("(")].strip(), _pm.group(1))
    if nps_sc2.button("📡 지분율 조회", type="primary", use_container_width=True,
                      key="nps_search_btn", disabled=_nps_target is None) and _nps_target:
        with st.spinner(f"{_nps_target[0]} 국민연금 지분율 실시간 조회 중... (DART→FnGuide→WiseReport)"):
            _sr = search_nps_holding(_nps_target[1], _nps_target[0], _dart_key)
        st.session_state.nps_search_result = {"r": _sr, "name": _nps_target[0], "code": _nps_target[1],
                                              "t": datetime.now().strftime("%Y-%m-%d %H:%M")}
    _saved = st.session_state.get("nps_search_result")
    if _saved:
        _sr, _snm, _scd = _saved["r"], _saved["name"], _saved["code"]
        if _sr is None:
            st.error(f"❌ {_snm}({_scd}) 조회 실패 — FnGuide·WiseReport 모두 응답 없음/차단. "
                     "위 '🔑 DART 오픈API 키'를 설정하면 공식 공시 API로 우회 조회할 수 있습니다.")
        elif _sr["지분율"] is None:
            _src_txt = f" (확인 소스: {_sr['출처']})" if _sr.get("출처") else ""
            st.info(f"ℹ️ **{_snm}({_scd})** — 주요주주/대량보유 내역에서 국민연금이 확인되지 않습니다{_src_txt}. "
                    "지분이 없거나 5% 미만(공시 의무 미발생)일 가능성이 큽니다.")
        else:
            _pct = _sr["지분율"]
            st.markdown(f"##### 📌 {_snm} ({_scd})")
            _rm1, _rm2, _rm3 = st.columns(3)
            _rm1.metric("국민연금 지분율", f"{_pct:.2f}%", help=f"표기: {_sr['주주표기']}")
            _rm2.metric("5% 대량보유 공시 대상", "✅ 해당 (5%↑)" if _pct >= 5.0 else "➖ 미해당 (5% 미만)")
            _src_lbl = _sr.get("출처") or "-"
            if _sr.get("기준일"):
                _src_lbl += f" · 보고일 {_sr['기준일']}"
            _rm3.metric("데이터 출처", _src_lbl, help=f"조회 시각: {_saved['t']}")
            st.caption(f"🔗 원본 확인: [FnGuide 지분현황](https://comp.fnguide.com/SVO2/ASP/SVD_Invest.asp?pGB=1&gicode=A{_scd}) · "
                       f"[WiseReport 지분현황](https://comp.wisereport.co.kr/company/c1070001.aspx?cmp_cd={_scd}) · "
                       "[DART 전자공시](https://dart.fss.or.kr)에서 '국민연금공단' 검색 시 대량보유 보고서 원문 확인 가능")
    st.divider()

    col_btn1, col_btn2 = st.columns([2, 8])
    if col_btn1.button("🔄 실시간 스크래핑 시도", type="primary", use_container_width=True):
        get_nps_holdings.clear()
        get_nps_us_portfolio.clear()
        search_nps_holding.clear()
        get_dart_corp_map.clear()
        st.session_state.pop("nps_search_result", None)
        st.rerun()
        
    with st.spinner("국민연금 보유현황을 실시간으로 파싱 중입니다. (서버 차단 시 표시되지 않을 수 있습니다)"):
        nps_kr_df = get_nps_holdings(_dart_key)
        nps_us_df = get_nps_us_portfolio()
    
    tab_nps1, tab_nps2, tab_nps3 = st.tabs(["🇰🇷 한국 주식 5% 이상 보유 현황", "🇺🇸 미국 주식 핵심 포트폴리오 (13F)", "🌟 황금 콤보 스캐너 (장기 가치 + 단기 수급)"])
    
    with tab_nps1:
        st.write("*(주요 기업의 국민연금 지분율을 DART 공시(키 보유 시)·FnGuide·WiseReport 체인으로 추출한 데이터입니다. '비고'에서 종목별 실제 소스를 확인할 수 있습니다.)*")
        if nps_kr_df is None or nps_kr_df.empty:
            st.warning("⚠️ 국민연금 국내 지분 데이터를 실시간으로 불러오지 못했습니다 (FnGuide·WiseReport 모두 응답 없음/차단). "
                       "상단 '🔑 DART 오픈API 키'를 설정하면 공식 공시 API로 우회 조회할 수 있습니다. "
                       "부정확한 캐시를 보여주지 않기 위해 표시를 생략합니다 — 잠시 후 새로고침해 주세요.")
        else:
            _f_kr = st.text_input("🔎 표 내 검색 (종목명/티커)", key="nps_kr_tbl_filter",
                                  placeholder="예: 삼성 / 005930 — 입력 즉시 필터링")
            _vdf_kr = nps_kr_df
            if _f_kr and _f_kr.strip():
                _mask_kr = nps_kr_df.astype(str).apply(
                    lambda c: c.str.contains(re.escape(_f_kr.strip()), case=False, na=False)).any(axis=1)
                _vdf_kr = nps_kr_df[_mask_kr]
                st.caption(f"검색 결과: {len(_vdf_kr)}건 / 전체 {len(nps_kr_df)}건")
            st.dataframe(_vdf_kr, use_container_width=True, hide_index=True)
         
    with tab_nps2:
        st.write("*(WhaleWisdom 등 미국 SEC 13F 공시 트래커를 기반으로 파싱된 국민연금 미국 주식 포트폴리오입니다.)*")
        if nps_us_df is None or nps_us_df.empty:
            st.warning("⚠️ 국민연금 미국 13F 데이터를 실시간으로 불러오지 못했습니다 (Dataroma 응답 없음/차단). "
                       "부정확한 캐시를 보여주지 않기 위해 표시를 생략합니다 — 잠시 후 새로고침해 주세요.")
        else:
            _f_us = st.text_input("🔎 표 내 검색 (종목명/티커)", key="nps_us_tbl_filter",
                                  placeholder="예: NVDA / Apple — 입력 즉시 필터링")
            _vdf_us = nps_us_df
            if _f_us and _f_us.strip():
                _mask_us = nps_us_df.astype(str).apply(
                    lambda c: c.str.contains(re.escape(_f_us.strip()), case=False, na=False)).any(axis=1)
                _vdf_us = nps_us_df[_mask_us]
                st.caption(f"검색 결과: {len(_vdf_us)}건 / 전체 {len(nps_us_df)}건")
            st.dataframe(_vdf_us, use_container_width=True, hide_index=True)
        
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

    # 🎛️ 임계값 직접 조정(고급) — 선택한 전략의 하드필터 기준을 슬라이더로 덮어쓰기
    with st.expander("🎛️ 임계값 직접 조정 (고급)"):
        _use_custom = st.checkbox("이 전략의 기준을 직접 조정", value=False,
                                  help="선택한 전략의 임계값을 슬라이더로 덮어씁니다. 끄면 전략 기본값 사용. (해당 전략이 쓰는 항목만 노출)")
        _ov = {}
        if _use_custom:
            _oc1, _oc2, _oc3, _oc4 = st.columns(4)
            if strat["per"] is not None:
                with _oc1: _ov["per"] = st.slider("PER 상한 ≤", 3, 100, int(strat["per"]))
            if strat["pbr"] is not None:
                with _oc2: _ov["pbr"] = st.slider("PBR 상한 ≤", 0.3, 10.0, float(strat["pbr"]), 0.1)
            if strat["div"] is not None:
                with _oc3: _ov["div"] = st.slider("배당 하한 ≥ (%)", 0.0, 10.0, float(strat["div"]), 0.5)
            if strat["roe"] is not None:
                with _oc4: _ov["roe"] = st.slider("ROE 하한 ≥ (%)", 0, 40, int(strat["roe"]))
            if not _ov:
                st.caption("이 전략은 조정 가능한 수치 기준(PER·PBR·배당·ROE)이 없습니다.")
    eff_strat = dict(strat); eff_strat.update(_ov)   # 유효 전략 = 전략 기본값 + 오버라이드

    cond = []
    if eff_strat["per"] is not None: cond.append(f"PER ≤ {eff_strat['per']}")
    if eff_strat["pbr"] is not None: cond.append(f"PBR ≤ {eff_strat['pbr']}")
    if eff_strat["div"] is not None: cond.append(f"배당 ≥ {eff_strat['div']}%")
    if eff_strat["roe"] is not None: cond.append(f"ROE ≥ {eff_strat['roe']}%")
    if eff_strat["debt"] is not None: cond.append(f"부채비율 ≤ {eff_strat['debt']}")
    if eff_strat["growth"] is not None: cond.append(f"이익성장 ≥ {eff_strat['growth']}%")
    if eff_strat["mom"] == "strong": cond.append("강세 모멘텀(3·6M 상승)")
    if eff_strat["mom"] == "weak": cond.append("낙폭과대(고점 -25%↓)")
    _custom_tag = " · 🎛️ 커스텀 임계값 적용" if _ov else ""
    st.info(f"**{strat['name']}** — {strat['desc']}{_custom_tag}\n\n**적용 필터:** " + " ｜ ".join(cond) + "\n\n※ PER·PBR·모멘텀은 하드 필터, ROE·배당·부채·성장은 데이터가 있을 때만 적용(소프트)됩니다.")

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
                    if not value_passes(m, eff_strat):
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
                    passed = _value_rank(passed)   # 🏆 가치 점수 계산 + 내림차순 정렬(베스트 밸류 순)
                    def _fmt(v, suf="", plus=False):
                        if v is None: return "-"
                        return (f"{v:+.1f}{suf}" if plus else f"{v:.1f}{suf}")
                    summary = pd.DataFrame([{
                        "순위": p["_vrank"], "가치점수": p["_vscore"],
                        "종목명": p["name"], "코드": p["code"],
                        "PER": _fmt(p["m"]["per"]), "이익수익%": _fmt(p["_factors"]["ey"], plus=False),
                        "PBR": (f"{p['m']['pbr']:.2f}" if p["m"]["pbr"] else "-"),
                        "PEG": (f"{p['_factors']['peg']:.2f}" if p["_factors"]["peg"] is not None else "-"),
                        "배당%": _fmt(p["m"]["div"]), "ROE%": (f"{p['m']['roe']:.0f}" if p["m"]["roe"] is not None else "-"),
                        "부채비율": (f"{p['m']['debt']:.0f}" if p["m"]["debt"] is not None else "-"),
                        "성장%": _fmt(p["m"]["growth"], plus=True),
                        "3M%": _fmt(p["m"]["mom3"], plus=True), "6M%": _fmt(p["m"]["mom6"], plus=True),
                        "고점대비%": _fmt(p["m"]["off_high"], plus=True),
                        "검증팩터": f"{p['_factors']['cov_n']}/{p['_factors']['cov_total']}",
                    } for p in passed])
                    st.session_state.value_scan_summary = summary
                    st.session_state.value_scan_top = passed[0]   # 베스트 밸류(1위) 콜아웃용
                    st.session_state.value_scan_results = [p["res"] for p in passed if p["res"]]
                else:
                    st.session_state.value_scan_summary = None
                    st.session_state.value_scan_top = None
                    st.session_state.value_scan_results = []
                st.session_state.value_scan_meta = (strat["name"], total, len(passed))

    meta = st.session_state.get("value_scan_meta")
    if meta:
        if meta[2] > 0:
            st.success(f"✅ {meta[1]}개 후보 중 **{meta[2]}개** 종목이 '{meta[0]}' 조건을 통과했습니다.")
        else:
            st.warning(f"'{meta[0]}' 조건을 통과한 종목이 없습니다. 위험 성향을 바꾸거나 다른 전략을 시도해보세요.")
    if st.session_state.get("value_scan_summary") is not None:
        _vtop = st.session_state.get("value_scan_top")
        if _vtop:
            _tm = _vtop["m"]; _tf = _vtop["_factors"]
            def _cv(v, suf="", d=1):
                return "—" if v is None else f"{v:.{d}f}{suf}"
            st.markdown(
                "<div style='border:1px solid #34d399;background:linear-gradient(135deg,#ecfdf5,#d1fae5);"
                "border-radius:14px;padding:14px 16px;margin:4px 0 10px;'>"
                f"<div style='font-size:12px;font-weight:800;color:#047857;'>💎 베스트 밸류 (가치 점수 {_vtop['_vscore']:.1f})</div>"
                f"<div style='font-size:21px;font-weight:800;color:#0f172a;margin:2px 0 6px;'>{_vtop['name']} "
                f"<span style='font-size:13px;color:#94a3b8;font-weight:600;'>{_vtop['code']}</span></div>"
                "<div style='font-size:13px;color:#334155;line-height:1.7;'>"
                f"PER <b>{_cv(_tm['per'])}</b> &nbsp;·&nbsp; PBR <b>{_cv(_tm['pbr'],'',2)}</b> &nbsp;·&nbsp; "
                f"PEG <b>{_cv(_tf['peg'],'',2)}</b> &nbsp;·&nbsp; ROE <b>{_cv(_tm['roe'],'%',0)}</b> &nbsp;·&nbsp; "
                f"배당 <b>{_cv(_tm['div'],'%')}</b> &nbsp;·&nbsp; 검증 <b>{_tf['cov_n']}/{_tf['cov_total']}</b></div>"
                "</div>", unsafe_allow_html=True)
        st.markdown("#### 📋 조건 통과 종목 요약 (가치 점수 순)")
        _vsum = st.session_state.value_scan_summary
        st.dataframe(_vsum, use_container_width=True, hide_index=True)
        st.caption("💡 **가치 점수** = 저평가(PER·PBR·PEG) 45% + 퀄리티(ROE) 20% + 인컴(배당) 15% + 안전(부채) 12% + 모멘텀(6M) 8%, "
                   "통과 종목 내 상대평가. **PEG**=PER÷이익성장(1 미만이면 성장 대비 저평가), **이익수익%**=1/PER, "
                   "**검증팩터**=실제 데이터가 확인된 팩터 수(값 없는 팩터는 소프트 통과). ROE·배당·부채·성장은 국내 데이터 특성상 일부 결측될 수 있습니다.")
        _vstamp = datetime.now().strftime("%Y%m%d_%H%M")
        st.download_button("💾 스크리닝 결과 CSV 저장", _vsum.to_csv(index=False).encode("utf-8-sig"),
                           file_name=f"가치스크리닝_{_vstamp}.csv", mime="text/csv", key="value_csv")
    if st.session_state.value_scan_results:
        st.markdown("#### 📈 통과 종목 차트·타점 정밀 분석")
        display_sorted_results(st.session_state.value_scan_results, tab_key="t3", api_key=api_key_input)

elif selected_menu == "⚡ 메가트렌드 & 테마 대장주":
        st.markdown("## ⚡ 메가트렌드 & 테마 대장주")
        st.write("AI가 최신 트렌드를 분석하여, 숨겨진 글로벌 텐배거(10배 상승) 후보와 한·미 양국의 핵심 수혜주를 동시에 발굴합니다.")

        # [버그수정] 이 페이지로 '새로 진입'했는데 결과 없는 '미완료 검색어'가 남아 있으면 정리한다.
        #  이전에 검색하다 만 deep_tech_query 가 재진입 시 자동 재실행되어 '종목을 찾지 못했습니다' 오류가
        #  잠깐 떴다 사라지던 현상을 방지. (이미 완료된 결과 deep_tech_results 는 그대로 보존)
        if _nav_changed and st.session_state.get("deep_tech_results") is None:
            st.session_state.deep_tech_query = None
            st.session_state.deep_tech_brief = None

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
                display_sorted_results(st.session_state.deep_tech_results, tab_key="t5", api_key=api_key_input, show_leader_rank=True)

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
            display_sorted_results(st.session_state.gf_results, tab_key="gf", api_key=api_key_input, show_leader_rank=True)

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

elif selected_menu == "💰 국장 수급 분석 (외국인·기관·개인)":
    st.markdown("## 💰 국장 수급 분석 (외국인·기관·개인)")
    st.caption("최근 거래일 기준 · 거래대금 상위 종목 스캔 · 단위: 억원 · 🔴빨강=순매수/상승 · 🔵파랑=순매도/하락")
    with st.spinner("네이버 투자자별 순매수 데이터 수집 중... (첫 조회는 십수 초, 이후 30분 캐시)"):
        flows = get_kr_investor_flows()
    if flows is None or flows.empty:
        st.error("❌ 수급 데이터를 불러오지 못했습니다. 잠시 후 다시 시도해주세요.")
    else:
        st.caption(f"📊 거래대금 상위 {len(flows)}개 종목 분석 · 개인은 외국인·기관의 반대값으로 추정")
        t_top, t_smart, t_hand = st.tabs(
            ["🏆 순매수·순매도 TOP", "🧠 개미 vs 스마트머니", "🔄 수급 주체 손바뀜"])
        with t_top:
            for emoji, inv, note in [("🦅", "외국인", ""), ("🏛️", "기관", ""), ("🐜", "개인", " (추정)")]:
                st.markdown(f"#### {emoji} {inv}{note}")
                cb, cs = st.columns(2)
                with cb:
                    st.markdown("**🔴 순매수 TOP10**")
                    _render_netbuy_list(flows, inv, ascending=False)
                with cs:
                    st.markdown("**🔵 순매도 TOP10**")
                    _render_netbuy_list(flows, inv, ascending=True)
                st.markdown("<div style='height:6px;'></div>", unsafe_allow_html=True)
        with t_smart:
            st.caption("스마트머니 = 외국인+기관 합산. (네이버 데이터 특성상 개인은 외국인·기관의 반대값으로 추정)")
            c1, c2 = st.columns(2)
            with c1:
                st.markdown("#### 🧠 스마트머니 매집")
                st.caption("외국인+기관 순매수 상위 (개미는 반대편)")
                _render_flow_chips(flows[flows["스마트머니"] > 0], sort_col="스마트머니", ascending=False)
            with c2:
                st.markdown("#### 🐜 개미 우위")
                st.caption("외국인+기관 순매도 상위 (개미가 받아낸 종목)")
                _render_flow_chips(flows[flows["스마트머니"] < 0], sort_col="스마트머니", ascending=True)
            st.markdown("#### 🤝 외국인·기관 동반 순매수")
            st.caption("외국인·기관이 둘 다 순매수한 종목 (가장 강한 수급 신호)")
            _render_flow_chips(flows[(flows["외국인"] > 0) & (flows["기관"] > 0)],
                               sort_col="스마트머니", ascending=False)
        with t_hand:
            st.caption("어제 순매도 → 오늘 순매수로 전환된 종목 (스마트머니 기준 · 흔히 '바닥 신호'로 해석)")
            _render_handover(flows)
    st.caption("데이터: 네이버 금융 · 정보 제공용이며 매수·매도 추천이 아닙니다. 투자 판단과 책임은 본인에게 있습니다.")

elif selected_menu == "🔥 지금 뜨는 섹터 (국장·미장)":
    st.markdown("## 🔥 지금 뜨는 섹터")
    st.caption("대표 종목 평균 등락률 순 · 🔴빨강=상승 / 🔵파랑=하락")

    def _render_sector_market(market, spinner_msg):
        with st.spinner(spinner_msg):
            sectors = get_trending_sectors(market)
        if not sectors:
            who = "국장" if market == "KR" else "미장"
            st.error(f"❌ {who} 섹터 데이터를 불러올 수 없습니다. 잠시 후 다시 시도해주세요.")
            return
        hot = sum(1 for s in sectors if s["avg"] > 0)
        cc1, cc2, cc3 = st.columns(3)
        cc1.metric("강세 테마", f"{hot} / {len(sectors)}")
        cc2.metric("🔥 최강 테마", sectors[0]["theme"], f"{sectors[0]['avg']:+.2f}%")
        cc3.metric("🧊 최약 테마", sectors[-1]["theme"], f"{sectors[-1]['avg']:+.2f}%")
        st.markdown("#### 테마별 평균 등락 (강세 순)")
        render_trending_sectors(sectors)

    tab_kr, tab_us = st.tabs(["🇰🇷 국장 (KOSPI·KOSDAQ)", "🇺🇸 미장 (US)"])
    with tab_kr:
        _render_sector_market("KR", "국장 테마별 등락 수집 중...")
    with tab_us:
        _render_sector_market("US", "미장 테마별 등락 수집 중... (첫 조회는 수십 초, 이후 30분 캐시)")
    st.caption("대표 종목 평균 등락률 기준이며, 테마 구성은 참고용입니다. 투자 권유가 아닙니다.")

elif selected_menu == "🚦 거래량 급증 & 시장 경보":
    st.markdown("## 🚦 거래량 급증 & 시장 경보")
    tab_vol, tab_warn = st.tabs(["📊 거래량 급증/급감", "🛡️ 관리종목 및 시장경보"])

    with tab_vol:
        st.caption("💡 **거래량 폭증** = 평소보다 돈·관심이 몰린 종목 (세력 의심 / 급등 후보). "
                   "색상은 한국식 — 🔴빨강=상승, 🔵파랑=하락. 막대가 길수록 거래량이 더 터진 종목입니다.")
        sub_kr, sub_us = st.tabs(["🇰🇷 국장 (KRX) TOP20", "🇺🇸 미장 (US) TOP20"])

        with sub_kr:
            with st.spinner("국장 거래량 데이터 스크래핑 중..."): surge_df, drop_df = get_volume_surge_drop()
            c_surge, c_drop = st.columns(2)
            with c_surge:
                st.markdown("#### 🔥 거래량 급증 TOP20")
                sty_s, _ = style_volume_table(surge_df, "surge")
                if sty_s is not None:
                    st.dataframe(sty_s, use_container_width=True, height=740)
                elif not surge_df.empty:
                    st.dataframe(surge_df, use_container_width=True, hide_index=True)
                else:
                    st.error("❌ 현재 데이터를 불러올 수 없습니다.")
            with c_drop:
                st.markdown("#### ❄️ 거래량 급감 TOP20")
                sty_d, _ = style_volume_table(drop_df, "drop")
                if sty_d is not None:
                    st.dataframe(sty_d, use_container_width=True, height=740)
                elif not drop_df.empty:
                    st.dataframe(drop_df, use_container_width=True, hide_index=True)
                else:
                    st.error("❌ 현재 데이터를 불러올 수 없습니다.")

        with sub_us:
            st.caption("🇺🇸 주요 미국 대형주 유니버스 기준 · **오늘 거래량 ÷ 최근 20일 평균** 배율(>1 급증 / <1 급감) · "
                       "첫 조회는 수십 초 걸릴 수 있어요(이후 30분 캐시).")
            with st.spinner("미장 거래량 데이터 수집 중... (야후 파이낸스)"):
                us_surge, us_drop = get_us_volume_surge_drop()
            if us_surge.empty and us_drop.empty:
                st.error("❌ 미국 거래량 데이터를 불러올 수 없습니다. 잠시 후 다시 시도해주세요.")
            else:
                uc1, uc2 = st.columns(2)
                with uc1:
                    st.markdown("#### 🔥 거래량 급증 TOP20")
                    s = style_us_volume_table(us_surge, "surge")
                    st.dataframe(s if s is not None else us_surge, use_container_width=True, height=740)
                with uc2:
                    st.markdown("#### ❄️ 거래량 급감 TOP20")
                    d = style_us_volume_table(us_drop, "drop")
                    st.dataframe(d if d is not None else us_drop, use_container_width=True, height=740)
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
        
        # iterrows 제거: 2,800여 행을 매 새로고침마다 순회하던 것을 컬럼 벡터화로 대체
        _krx_df = get_krx_stocks()
        _name_ok = _krx_df['Name'].astype(str).str.len() > 1
        krx_dict = dict(zip(_krx_df.loc[_name_ok, 'Name'], _krx_df.loc[_name_ok, 'Code']))
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
        with st.spinner("당일 리포트의 투자의견·목표가를 분석 중입니다..."):
            res_df = get_today_research_details()
        if not res_df.empty:
            if api_key_input and st.button("🤖 AI 당일 리포트 종합 의견 및 섹터 요약", use_container_width=True, type="primary"):
                with st.spinner("당일 발간된 리포트들을 분석하여 시장 분위기와 유망 섹터를 요약 중입니다..."):
                    report_text = "\n".join([f"- [{r['증권사']}] {r['종목명']} (의견:{r['투자의견']}): {r['제목']}" for _, r in res_df.head(30).iterrows()])
                    prompt = f"당신은 증권사 리서치 센터장입니다. 오늘 발간된 다음 증권사 리포트 제목들을 분석하여, 1) 오늘 증권가가 가장 주목하는 핵심 섹터/테마 2개와 그 이유, 2) 시장의 전반적인 투자의견 요약을 마크다운으로 작성해주세요.\n\n[오늘의 리포트]\n{report_text}"
                    st.info(ask_gemini(prompt, api_key_input), icon="💡")

            show_df = res_df[['종목명', '증권사', '제목', '투자의견', '목표가', '변동', '작성일', '원문링크']].copy()
            show_df['목표가'] = show_df['목표가'].apply(lambda x: f"{int(x):,}원" if x and x > 0 else "-")
            st.dataframe(
                show_df,
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
                        # 투자의견은 standardize_opinion으로 '강력매수/매수/중립/매도/N/A' 정규화됨
                        op = today_reports['투자의견'].astype(str)
                        buy_mask = op.isin(['강력매수', '매수'])
                        sell_mask = op.eq('매도')
                        buys = int(buy_mask.sum())
                        sells = int(sell_mask.sum())
                        holds = len(today_reports) - buys - sells

                        st.markdown("#### 📊 오늘의 증권가 투자의견 요약 (Verdict)")
                        c1, c2, c3, c4 = st.columns(4)
                        c1.metric("총 발간 리포트", f"{len(today_reports)}건")
                        c2.metric("BUY (매수·강력매수)", f"{buys}건")
                        c3.metric("HOLD/기타", f"{holds}건")
                        c4.metric("SELL (매도)", f"{sells}건")

                        # 매수의견 종목 목록 — 'BUY n건'이 어떤 종목인지 바로 확인
                        if buys > 0:
                            def _prc_buyops():
                                buy_tbl = today_reports[buy_mask][['종목명', '증권사', '투자의견', '목표가', '제목']].copy()
                                buy_tbl['목표가'] = buy_tbl['목표가'].apply(lambda x: f"{int(x):,}원" if x and x > 0 else "-")
                                st.dataframe(buy_tbl, use_container_width=True, hide_index=True)
                            _register_popup("buyops", _prc_buyops)
                            _popup_button(f"🔴 매수의견 종목 {buys}건 보기", "buyops", f"🔴 매수의견 종목 {buys}건", key="btn_buyops")

                        st.markdown("#### 📈 당일 목표가(TP) 상/하향 랭킹")
                        st.caption("💡 증권사가 직전 리포트 대비 목표가를 올렸으면 🔴상향, 내렸으면 🔵하향. "
                                   "원문에 '종전 목표가'가 없으면 `유지/신규`로 분류되어 이 랭킹에는 나오지 않습니다. "
                                   "따라서 위 BUY 건수와 아래 상향 건수는 서로 다른 지표입니다.")
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
    st.caption("👁️ 차트 이미지(캡처) AI 비전 분석은 사이드바 **[심층 분석 & 도구] → 👁️ 차트 이미지 AI 비전 분석** 메뉴로 이동했습니다.")
    market_choice = st.radio("시장 선택", ["🇰🇷 국내 주식", "🇺🇸 미국 주식"], horizontal=True)
    if market_choice == "🇰🇷 국내 주식":
        krx_df = get_krx_stocks()
        searched_name = searched_code = None
        do_analyze = False
        if not krx_df.empty:
            opts = ["🔍 분석할 국내 종목을 검색/선택하세요"] + (krx_df['Name'].astype(str) + " (" + krx_df['Code'].astype(str) + ")").tolist()
            col_s1, col_s2 = st.columns([8, 2])
            with col_s1: kr_query = st.selectbox("👇 종목명/코드 검색:", opts, label_visibility="collapsed")
            with col_s2: kr_search_btn = st.button("📊 분석 시작", use_container_width=True)
            if kr_query != "🔍 분석할 국내 종목을 검색/선택하세요" and (kr_query or kr_search_btn):
                searched_name = kr_query.rsplit(" (", 1)[0]
                searched_code = kr_query.rsplit("(", 1)[-1].replace(")", "").strip()
                do_analyze = True
        else:
            # 폴백: 종목 목록 로드 실패 시 종목코드 직접 입력
            st.warning("⚠️ 국내 종목 목록을 일시적으로 불러오지 못했습니다. 아래에 **종목코드 6자리**를 직접 입력해 분석하세요. (예: 005930)")
            col_s1, col_s2 = st.columns([8, 2])
            with col_s1: kr_manual = st.text_input("종목코드/이름 입력:", placeholder="예: 005930  또는  005930 삼성전자", label_visibility="collapsed", key="kr_manual_in")
            with col_s2: kr_manual_btn = st.button("📊 분석 시작", use_container_width=True, key="kr_manual_btn")
            if kr_manual:
                m = re.search(r"\d{6}", kr_manual)
                if m:
                    searched_code = m.group()
                    searched_name = kr_manual.replace(searched_code, "").strip() or searched_code
                    do_analyze = True
                elif kr_manual_btn:
                    st.error("6자리 종목코드를 포함해 입력해 주세요. 예: 005930")
        if do_analyze and searched_code:
            with st.spinner(f"📡 '{searched_name}' 타점 분석 중..."):
                res = analyze_technical_pattern(searched_name, searched_code)
                if res:
                    # 🌟 다중 테마 뷰어 출력 (국내 주식) 🌟
                    render_single_stock_themes(searched_name, api_key_input)
                    draw_stock_card(res, api_key_str=api_key_input, is_expanded=True, key_suffix="t4_kr")
                else:
                    st.error("❌ 데이터 로드 실패 — 종목코드를 확인해 주세요.")
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
                    _res_us = analyze_technical_pattern(us_ticker, us_ticker)
                st.session_state.indiv_result_us = {"res": _res_us, "ticker": us_ticker} if _res_us else None
                if not _res_us:
                    st.error("❌ 데이터 로드 실패 — 종목을 확인해 주세요.")
            # 분석 결과를 세션에 보존 → 질의응답 토글 등 리런에도 카드가 사라지지 않음
            _ir_us = st.session_state.get("indiv_result_us")
            if _ir_us and _ir_us.get("res"):
                render_single_stock_themes(_ir_us["ticker"], api_key_input)
                draw_stock_card(_ir_us["res"], api_key_str=api_key_input, is_expanded=True, key_suffix="t4_us")


elif selected_menu == "👁️ 차트 이미지 AI 비전 분석":
    st.markdown("## 👁️ 차트 이미지 AI 비전 분석")
    st.info("💡 차트를 캡처(Windows: `Win+Shift+S` / Mac: `Cmd+Shift+4`)한 뒤 **📋 클립보드 붙여넣기 버튼**만 누르면 바로 들어옵니다. 파일 업로드와 이미지 URL 방식도 그대로 지원해요.")
    paste_col, upload_col, url_col = st.columns([1, 1, 1])
    with paste_col:
        st.markdown("**📋 클립보드 캡처 붙여넣기**")
        try:
            from streamlit_paste_button import paste_image_button as _paste_image_button
            _paste_res = _paste_image_button(label="📋 캡처한 차트 붙여넣기", key="vision_paste_btn", errors="ignore")
            if _paste_res is not None and getattr(_paste_res, "image_data", None) is not None:
                st.session_state["vision_pasted_img"] = _paste_res.image_data
        except ImportError:
            st.warning("📦 클립보드 붙여넣기에는 `streamlit-paste-button` 패키지가 필요합니다. "
                       "requirements.txt에 추가해 두었으니 재배포(또는 `pip install streamlit-paste-button`)하면 버튼이 활성화돼요.")
        if st.session_state.get("vision_pasted_img") is not None:
            if st.button("🗑️ 붙여넣은 이미지 지우기", key="vision_paste_clear", use_container_width=True):
                st.session_state["vision_pasted_img"] = None
                st.rerun()
    with upload_col:
        uploaded_chart = st.file_uploader("📸 이미지 파일 업로드", type=["png", "jpg", "jpeg"])
    with url_col:
        image_url = st.text_input("🔗 이미지 주소(URL) 붙여넣기", placeholder="https://example.com/chart.png")

    img_to_analyze = None
    if st.session_state.get("vision_pasted_img") is not None:
        img_to_analyze = st.session_state["vision_pasted_img"]
        st.image(img_to_analyze, caption="📋 클립보드에서 붙여넣은 차트", use_container_width=True)
    elif uploaded_chart:
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
                        
                        # 투자의견 표준화 → 파이차트용 라벨(영문 병기). 분류는 전역 헬퍼로 통일.
                        def opinion_pie_label(op):
                            std = standardize_opinion(op)  # '강력매수/매수/중립/매도/N/A'
                            return {
                                '강력매수': '강력매수 (Strong Buy)',
                                '매수': '매수 (Buy)',
                                '중립': '중립 (Hold)',
                                '매도': '매도 (Sell)',
                            }.get(std, str(op).strip().upper())

                        history_df['투자의견_표준화'] = history_df['투자의견'].apply(opinion_pie_label)
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
        years, inv_list, val_list = [], [], []
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
            years.append(y); inv_list.append(float(inv_y)); val_list.append(float(val_y))
        # 연차를 숫자 x축으로 두어 정렬을 보장하고(문자열 정렬 시 0,10,11,…,1,20,2 로 꼬임)
        # 눈금 라벨만 'N년'으로 표시
        fig_growth = go.Figure()
        fig_growth.add_trace(go.Scatter(
            x=years, y=val_list, name="평가액", mode="lines",
            line=dict(color="#93c5fd", width=1.5), fill="tozeroy",
            fillcolor="rgba(147,197,253,0.45)",
            hovertemplate="%{x}년<br>평가액 %{y:,.0f}원<extra></extra>"))
        fig_growth.add_trace(go.Scatter(
            x=years, y=inv_list, name="투입 원금", mode="lines",
            line=dict(color="#3b82f6", width=1.5), fill="tozeroy",
            fillcolor="rgba(59,130,246,0.55)",
            hovertemplate="%{x}년<br>투입 원금 %{y:,.0f}원<extra></extra>"))
        fig_growth.update_layout(
            height=380, margin=dict(l=10, r=10, t=10, b=10),
            hovermode="x unified",
            legend=dict(orientation="h", yanchor="bottom", y=1.02, x=0),
            xaxis=dict(tickmode="array", tickvals=years,
                       ticktext=[f"{y}년" for y in years], title=None),
            yaxis=dict(title=None, tickformat=","),
        )
        st.plotly_chart(fig_growth, use_container_width=True)

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
    def _prc_zeroerr():
        errs = [it for it in etf_data if it.get('price', 0) == 0]
        if errs:
            st.error(f"현재 총 {len(errs)}개 종목의 데이터 수집이 지연되고 있습니다.")
            st.table(pd.DataFrame([{'테마': i['theme'], '종목': i['name'], '코드': i['code']} for i in errs]))
        else: 
            st.success("🎉 현재 시스템상 가격이 0원으로 조회되는 오류 종목이 단 하나도 없습니다! (무결점 상태)")
    _register_popup("zeroerr", _prc_zeroerr)
    _popup_button("⚠️ 데이터 통신 지연 종목 확인 (0원 에러 검출기)", "zeroerr", "⚠️ 0원 에러 검출기", key="btn_zeroerr")

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
                                     help="폴리마켓 질문/선택지를 한국어로 번역해 보여줍니다. (끄면 영어 원문 · 별도 키 불필요)")
            trans_map = {}
            if show_ko:
                # 번역 대상: 표에 보이는 모든 질문 + 상세(상위)에 쓰이는 선택지
                to_translate = [m["question"] for m in markets]
                for m in markets[:12]:
                    for o in (m["outcomes"] or []):
                        if o not in ("Yes", "No"):   # Yes/No 는 아래서 자체 처리
                            to_translate.append(o)
                with st.spinner("질문을 한글로 번역하는 중... (최초 1회만, 이후 캐시)"):
                    trans_map = translate_poly_questions(tuple(to_translate))

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


# ==========================================
# 🗞️ 뉴스 이슈 TOP & 영향 분석
#   오늘의 핵심 증시 이슈를 AI(구글검색 그라운딩)로 선별·요약 → 영향받는 섹터/종목을
#   호재(긍정)·악재(부정)·중립으로 분기해 '영향 관계도'로 시각화.
# ==========================================
elif selected_menu == "🗞️ 뉴스 이슈 TOP & 영향 분석":
    st.markdown("## 🗞️ 오늘의 뉴스 이슈 TOP & 영향 분석  "
                "<span style='font-size:0.5em;color:#94a3b8;'>BETA</span>", unsafe_allow_html=True)
    st.caption("지금 증시를 움직이는 핵심 뉴스 이슈를 AI가 선별·요약하고, 각 이슈가 어떤 업종·종목에 "
               "호재/악재로 작용하는지 '영향 관계도'로 보여줍니다. (구글 검색 그라운딩 · 무료)")

    if "news_issue_data" not in st.session_state:
        st.session_state.news_issue_data = None

    ctop1, ctop2, ctop3 = st.columns([1, 1, 1], vertical_alignment="bottom")
    ni_topn = ctop1.selectbox("표시할 이슈 수", [3, 5], index=0, key="ni_topn")
    ni_run = ctop2.button("🔎 오늘의 이슈 분석", type="primary", use_container_width=True, key="ni_run")
    if ctop3.button("🔄 새로고침(캐시 비우기)", use_container_width=True, key="ni_refresh"):
        try:
            get_news_issue_impact.clear()
        except Exception:
            pass
        st.session_state.news_issue_data = None
        st.rerun()

    if ni_run:
        if not api_key_input:
            st.warning("⚠️ AI 분석을 위해 좌측 사이드바에 Gemini API 키가 필요합니다.")
        else:
            with st.spinner("실시간 증시 헤드라인 수집 중..."):
                try:
                    _ni_titles = tuple(a["title"] for a in (get_latest_naver_news() or []))[:25]
                except Exception:
                    _ni_titles = tuple()
            with st.spinner("AI가 핵심 이슈와 영향 관계를 분석 중입니다... (구글 검색 → 최초 1회 다소 소요)"):
                st.session_state.news_issue_data = get_news_issue_impact(api_key_input, _ni_titles, ni_topn)

    _ni_data = st.session_state.get("news_issue_data")
    if not _ni_data or not _ni_data.get("issues"):
        st.info("위 **‘🔎 오늘의 이슈 분석’** 버튼을 누르면, 지금 증시를 움직이는 핵심 뉴스 이슈와 그 파급 효과를 분석해 드려요.")
    else:
        # 긍정=빨강(호재), 부정=파랑(악재), 중립=회색 — 한국 증시 색 관례
        _SENT_STYLE = {
            "긍정": ("#e11d48", "rgba(225,29,72,0.07)", "📈", "수혜"),
            "부정": ("#2563eb", "rgba(37,99,235,0.07)", "📉", "타격"),
            "중립": ("#64748b", "rgba(100,116,139,0.07)", "⚖️", "중립"),
        }
        _gen = _ni_data.get("generated_at", "")
        for _iss in _ni_data["issues"]:
            _rank = _iss.get("rank", 1)
            _src_n = len(_iss.get("sources") or [])

            # ── 이슈 헤더 카드 ──
            st.markdown(
                f"<div style='font-size:13px;font-weight:800;color:#6366f1;margin-bottom:2px;'>뉴스 이슈 {_rank}위</div>"
                f"<div style='font-size:24px;font-weight:800;color:#0f172a;line-height:1.25;margin-bottom:10px;'>{_iss['title']}</div>",
                unsafe_allow_html=True)
            if _iss.get("summary"):
                st.markdown(
                    f"<div style='border-left:4px solid #cbd5e1;padding:2px 0 2px 14px;color:#334155;"
                    f"font-size:15.5px;line-height:1.7;margin-bottom:6px;'>{_iss['summary']}</div>",
                    unsafe_allow_html=True)
            if _iss.get("points"):
                with st.expander("📌 주목할 포인트"):
                    for _p in _iss["points"]:
                        st.markdown(f"- {_p}")
            _meta = []
            if _src_n:
                _meta.append(f"📰 {_src_n}개 출처")
            if _gen:
                _meta.append(f"🕒 {_gen} 기준")
            if _iss.get("sources"):
                _meta.append("· " + ", ".join(_iss["sources"][:6]))
            if _meta:
                st.caption("   ".join(_meta))

            # ── 영향 관계도 ──
            st.markdown("<div style='font-size:17px;font-weight:800;color:#0f172a;margin:14px 0 4px;'>"
                        "어떤 영향을 줄까?</div>", unsafe_allow_html=True)
            _impacts = _iss.get("impacts") or []
            if not _impacts:
                st.caption("영향 관계 데이터가 없습니다.")
            else:
                _order = {"긍정": 0, "중립": 1, "부정": 2}
                _impacts = sorted(_impacts, key=lambda x: _order.get(x["sentiment"], 1))
                _chips = []
                for _im in _impacts:
                    _color, _bg, _emo, _tag = _SENT_STYLE.get(_im["sentiment"], _SENT_STYLE["중립"])
                    _tk_html = ""
                    if _im.get("tickers"):
                        _tk_html = "".join(
                            "<span style='display:inline-block;font-size:11px;color:#475569;background:#f1f5f9;"
                            "border-radius:5px;padding:1px 7px;margin:4px 5px 0 0;'>"
                            + _t["name"] + (f" · {_t['code']}" if _t.get("code") else "") + "</span>"
                            for _t in _im["tickers"]
                        )
                    _chips.append(
                        f"<div style='border:1px solid {_color}33;border-left:4px solid {_color};background:{_bg};"
                        f"border-radius:12px;padding:10px 14px;margin:8px 0;'>"
                        f"<div><span style='font-weight:800;color:#0f172a;font-size:15px;'>{_emo} {_im['target']}</span>"
                        f"<span style='font-size:11.5px;font-weight:800;color:#fff;background:{_color};"
                        f"border-radius:6px;padding:1px 8px;margin-left:9px;'>{_im['sentiment']}</span>"
                        f"<span style='font-size:11px;color:#94a3b8;margin-left:7px;'>{_im['kind']} · {_tag}</span></div>"
                        f"<div style='font-size:13px;color:#475569;line-height:1.5;margin-top:4px;'>{_im['reason']}</div>"
                        + (f"<div style='margin-top:4px;'>{_tk_html}</div>" if _tk_html else "")
                        + "</div>"
                    )
                st.markdown(
                    "<div style='display:flex;gap:14px;align-items:stretch;'>"
                    "<div style='flex:0 0 132px;display:flex;align-items:center;justify-content:center;text-align:center;"
                    "background:linear-gradient(135deg,#eef2ff,#e0e7ff);border:1px solid #c7d2fe;border-radius:14px;"
                    f"padding:12px;font-weight:800;color:#3730a3;font-size:14px;line-height:1.35;'>{_iss['title']}</div>"
                    "<div style='flex:1;min-width:0;'>" + "".join(_chips) + "</div>"
                    "</div>",
                    unsafe_allow_html=True)

                # 영향받는 종목을 '이 자리에서' 바로 정밀 진단 (페이지 이동 없이 인라인 표시)
                _codes_seen, _opts = set(), {}
                for _im in _impacts:
                    for _t in (_im.get("tickers") or []):
                        if _t.get("code") and _t["code"] not in _codes_seen:
                            _codes_seen.add(_t["code"])
                            _opts[f"{_t['name']} ({_t['code']}) · {_im['sentiment']}"] = (_t["name"], _t["code"])
                if _opts:
                    _pick = st.selectbox("🔬 이 이슈의 관련 종목 — 선택하면 바로 아래에 정밀 진단이 표시됩니다",
                                         ["(선택)"] + list(_opts.keys()), key=f"ni_pick_{_rank}")
                    if _pick != "(선택)":
                        _nm, _cd = _opts[_pick]
                        with st.container(border=True):
                            st.markdown(f"#### 🔬 {_nm} ({_cd}) 정밀 진단")
                            with st.spinner(f"📡 '{_nm}' 타점·수급 분석 중..."):
                                _res_ni = analyze_technical_pattern(_nm, _cd)
                            if _res_ni:
                                try:
                                    render_single_stock_themes(_nm, api_key_input)
                                except Exception:
                                    pass
                                draw_stock_card(_res_ni, api_key_str=api_key_input,
                                                is_expanded=True, key_suffix=f"ni_{_rank}_{_cd}")
                            else:
                                st.error(f"❌ '{_nm}({_cd})' 데이터를 불러오지 못했어요. 종목코드를 확인해 주세요.")
            st.divider()

        st.caption("※ AI가 실시간 검색으로 생성한 분석으로, 부정확하거나 지연될 수 있습니다. "
                   "호재/악재·영향 판단은 참고용이며, 최종 투자 판단과 책임은 투자자 본인에게 있습니다.")


# ==========================================
# [v7.1] 🚨 통합 경보 센터 (뉴스·차트·일정)
#   - jaemini_alert_center.py 의 함수에 기존 앱 함수들을 '주입'해서 렌더
# ==========================================
elif selected_menu == "🚨 통합 경보 센터 (뉴스·차트·일정)":
    alert_center.render_alert_center({
        "analyze_technical_pattern": analyze_technical_pattern,
        "get_latest_naver_news": get_latest_naver_news,
        "get_economic_events": get_economic_events,
        "get_kr_index_panel": get_kr_index_panel,
        "fetch_polymarket_markets": fetch_polymarket_markets,
        "get_krx_stocks": get_krx_stocks,
        "ask_gemini": ask_gemini,
        "api_key": api_key_input,
    })


# =====================================================================
# [공통] 전 페이지 하단 면책 푸터 — 어떤 메뉴든 화면 맨 아래에 항상 표시
#   (메뉴 분기 바깥 최상위에 두어 매 실행마다 렌더됨)
# =====================================================================
st.markdown(
    "<div style=\"margin-top:46px;padding:16px 20px;border-top:1px solid #e2e8f0;"
    "background:#f8fafc;border-radius:12px;text-align:center;\">"
    "<div style=\"font-size:12.5px;color:#64748b;line-height:1.75;\">"
    "⚠️ 본 서비스의 모든 정보·점수·신호·AI 분석은 <b>투자 권유가 아닌 참고 자료</b>이며, "
    "데이터는 지연되거나 오류가 있을 수 있습니다.<br>"
    "모든 투자 판단과 그 결과에 대한 책임은 <b>전적으로 이용자 본인</b>에게 있습니다."
    "</div>"
    "<div style=\"font-size:11px;color:#94a3b8;margin-top:7px;\">"
    "정보 제공 목적 · 매수·매도 추천이 아닙니다 · © 2026</div>"
    "</div>", unsafe_allow_html=True)
