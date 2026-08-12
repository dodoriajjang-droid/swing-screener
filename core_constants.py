# -*- coding: utf-8 -*-
"""
전역 상수 · 공용 import  (core_constants.py)
=====================================================================
모든 계층이 이 모듈을 star import 한다. st.set_page_config() 도 여기서 실행해
어떤 st 명령보다 먼저 호출되도록 보장한다.

계층 순서: constants → utils → data → ai → scoring → render
위 방향으로만 의존한다(순환 없음). core.py 가 전부를 합쳐 다시 내보낸다.
"""

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
from scoring_weights import DEFAULT_WEIGHTS as SCORE_W, make_weights, tunable_keys  # [v7.2] 점수 가중치 상수 분리
import diagnostics as diag                  # [v7.2] 수집 실패 진단
import app_state                            # [v7.2] 관심종목·히스토리 세션 저장 + 백업/복원

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
# 1. 초기 설정
# ==========================================
# ⚠️ st.set_page_config() 는 여기가 아니라 app.py 최상단에서 호출한다.
#    (1) 그 실행에서 '가장 먼저 나오는 st 명령'이어야 하고,
#    (2) 모듈은 프로세스당 한 번만 실행되므로 여기 두면 두 번째 접속부터는
#        아예 호출되지 않아 제목·레이아웃이 기본값으로 돌아간다.



# 예외를 조용히 삼키던 자리에서 호출된다. 실패해도 앱은 계속 돌지만 기록은 남는다.
# 화면 표출은 사이드바 diag.render_badge() / 홈의 diag.render_panel() 참고.
_diag_note = diag.note

# ==========================================
# 0. 관심종목 저장소  [v7.2] 세션 기반으로 전환
#    - 원본은 st.session_state (사용자별 분리). 로컬에서 쓰기 가능하면 파일에도 자동 저장.
#    - 클라우드처럼 파일을 못 쓰는 환경에서는 자동으로 세션 저장만 하고,
#      '⭐ 내 관심종목 모니터링' 페이지의 백업 UI 로 직접 내보내기/불러오기 한다.
#    - 기존 watchlist.json 은 그대로 읽어들이므로 쓰던 데이터는 유지된다.
# ==========================================
WATCHLIST_FILE = app_state.FILES["watchlist"]   # 하위 호환용 (경로 참조하는 코드가 있어 유지)

# [속도개선 2순위] 자동 새로고침은 '실시간 데이터가 필요한 페이지'에서만 동작시킨다.
#  기존: 전 페이지를 5분마다 통째로 재실행 → 계산기/시뮬레이터/스캐너/리스트 등에서도
#        불필요한 rerun + 짧은 TTL 캐시 만료로 인한 재요청이 발생.
#  변경: 아래 LIVE_REFRESH_PAGES 에 속한 페이지에서만 호출(실제 호출은 메인 로직에서 selected_menu 확정 후).
AUTOREFRESH_MS = 300000  # 5분. 갱신 주기를 바꾸려면 이 값만 조정하면 된다.


# =====================================================================
# 메뉴 구조 — 단일 원천
# =====================================================================
# (카테고리, [(메뉴 라벨, views/ 모듈명, 5분 자동갱신 여부)])
#
# 사이드바 표시·페이지 라우팅·자동갱신 대상이 전부 이 하나에서 파생된다.
# 예전에는 같은 문자열이 app.py 의 menu_options / VIEW_MODULES /
# LIVE_REFRESH_PAGES 세 곳에 흩어져 있어서, 메뉴 이름을 바꾸면 라우팅이
# 조용히 끊기거나(빈 화면) 자동갱신이 사라졌다.
#
# 라벨 규칙
#   - 버전·상태 표기(v6.0, 테스트)는 넣지 않는다. 쓰는 사람에게 의미가 없고
#     '(테스트)'는 기능을 못 믿게 만든다.
#   - 이모지는 메뉴마다 겹치지 않게. 아이콘이 같으면 아이콘으로 찾을 수 없다.
#   - 내부 구현(TOP 300)이나 조건(-30%↓)은 라벨이 아니라 화면 안에서 설명한다.
MENU_TREE = [
    ("홈 · 내 자산", [
        ("🎛️ 홈: 종합 대시보드",            "home_dashboard",    True),
        ("💼 내 계좌 & 포트폴리오 진단",      "portfolio",         False),
        ("⭐ 내 관심종목 모니터링",           "watchlist",         True),
    ]),
    ("종목 발굴", [
        # [통합] 개별 기업 정밀 진단 + 적정 주가 계산기 + 증권사 목표가 컨센서스.
        #   셋 다 '같은 종목의 다른 면'인데 입구가 따로여서, 한 종목을 보려면
        #   세 화면에서 세 번 검색해야 했다. 지금은 한 번 고르고 탭으로 바꿔 본다.
        ("🔬 종목 상세",                    "stock_detail",      False),
        ("🧭 AI 종목 발굴",                 "ai_finder",         False),
        ("🚀 단기 스윙 퀀트 스캐너",          "swing_scanner",     False),
        ("💎 장기 우량주 & 가치주 발굴",      "value_finder",      False),
        ("📉 낙폭과대 스캐너",               "drawdown_scanner",  False),
        ("🏛️ 국민연금 5% 대량보유 픽",       "nps_picks",         False),
        ("⚡ 메가트렌드 & 테마 대장주",       "theme_leaders",     False),
        ("🇰🇷 국민성장펀드 12대 산업 수혜주",  "growth_fund",       False),
        ("📋 코스피·코스닥 종목 리스트",      "stock_list",        False),
    ]),
    ("시장 흐름", [
        ("🌍 글로벌 매크로",                "macro",             False),
        ("🗺️ 시장 주도주 자금 히트맵",       "money_heatmap",     True),
        ("🕸️ 실시간 섹터 순환매 추적",       "sector_rotation",   True),
        ("🔥 지금 뜨는 섹터",               "hot_sectors",       False),
        ("🐋 국장 수급 분석",               "investor_flows",    False),
        ("📅 핵심 증시 일정 & IPO 달력",     "calendar_ipo",      False),
        ("🔮 폴리마켓 예측시장",             "polymarket",        False),
    ]),
    ("뉴스 · 경보", [
        ("🗞️ 뉴스 이슈 TOP & 영향 분석",     "news_impact",       False),
        ("🚨 통합 경보 센터",               "alert_center_page", True),
        ("🌅 간밤의 미국 급등주 & 수혜주",    "us_overnight",      False),
        ("🔺 당일 상/하한가 분석",           "limit_moves",       True),
        ("🚦 거래량 급증 & 시장 경보",        "volume_alerts",     True),
        ("📰 실시간 특징주 속보 & 리포트",     "news_flash",        True),
    ]),
    ("분석 도구", [
        ("👴 노후 준비 시뮬레이터",          "retirement_sim",    False),
        ("📊 국내외 핵심 ETF 분석",          "etf_analysis",      False),
        ("💰 고배당주",                     "dividend_pipeline", False),
        # 🎯 증권사 목표가 컨센서스 · ⚖️ 적정 주가 계산기 → '🔬 종목 상세' 탭으로 통합
        ("👁️ 차트 이미지 AI 비전 분석",      "chart_vision",      False),
    ]),
]

MENU_CATEGORIES = [c for c, _ in MENU_TREE]
MENUS_BY_CATEGORY = {c: [label for label, _, _ in items] for c, items in MENU_TREE}
VIEW_MODULES = {label: f"views.{mod}" for _, items in MENU_TREE for label, mod, _ in items}
LIVE_REFRESH_PAGES = {label for _, items in MENU_TREE for label, _, live in items if live}
CATEGORY_OF_MENU = {label: c for c, items in MENU_TREE for label, _, _ in items}

# ⚠️ `now = datetime.now()` 를 여기 두면 안 된다.
#    모듈은 프로세스당 한 번만 실행되므로 그 값은 '서버가 뜬 시각'에 얼어붙는다.
#    분할 전 app.py 에서는 실행마다 새로 계산되던 값이었다.
#    현재 시각이 필요하면 쓰는 쪽에서 datetime.now() 를 직접 호출할 것.

# ==========================================
# 2. 통합 데이터 수집 & AI 함수 모음
# ==========================================
# ==========================================
# [v7.0] 폴리마켓(Polymarket) 예측시장 데이터
#   - Gamma API (공개, 키 불필요): https://gamma-api.polymarket.com
#   - 시장 참여자들이 '실제 돈'을 걸고 만든 확률 → 금리/경제/정치 선행지표
# ==========================================
POLY_GAMMA = "https://gamma-api.polymarket.com"

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
    # XYZ = 옛 SQ(Block Inc.). 티커 변경으로 SQ 는 상장폐지 취급이라 yfinance 가
    # 매번 재시도하며 시간을 버렸다 (2026-08-12 확인 후 교체).
    "핀테크/결제": ["XYZ", "SOFI", "AFRM", "HOOD", "FOUR", "BILL", "PYPL"],
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
    ("ServiceNow","NOW"),("Uber","UBER"),("Airbnb","ABNB"),("PayPal","PYPL"),("Block","XYZ"),
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


# [v7.0] 하드코딩된 ETF 코드가 틀렸을 때, 이름으로 실시간 목록에서 정확한 코드를 자동 보정
_ETF_BRANDS = ['KODEX', 'TIGER', 'PLUS', 'ARIRANG', 'HANARO', 'SOL', 'RISE', 'KBSTAR', 'KB STAR',
               'ACE', 'KOSEF', 'TIMEFOLIO', 'WON', '히어로즈', '마이다스', 'TREX', 'FOCUS',
               '파워', 'BNK', 'HK', '네비게이터', '우리', '신한', '하나', '미래에셋']


NAVER_API_HDRS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36",
    "Referer": "https://m.stock.naver.com/",
    "Accept": "application/json, text/plain, */*",
}


# =====================================================================
# [신규] '눌러서 펼치는' 내용을 팝업 창(st.dialog)으로 보여주는 공용 헬퍼
#   _popup_button(label, name, title, key): expander 대체 버튼 → 누르면 모달 팝업.
#   내용은 _register_popup(name, fn)으로 등록된 렌더 함수가 그림. (구버전은 인라인 폴백)
# =====================================================================
_POPUP_RENDERERS = {}


# =====================================================================
# [홈 리디자인] '여의도 모닝 데스크' 전용 컴팩트 위젯
#   - 기존 홈의 정보 중복(시장국면 3회·환율 3회·VIX 2회·등락종목수 2회)을 제거하고
#     전문 트레이더의 아침 점검 흐름(간밤→국면→지수/수급→자금→심리→일정→내종목)으로 재구성.
#   - 무거운 plotly 게이지 2개 → 슬림 HTML 타일로 교체(정보 밀도↑, 로딩 부담↓).
# =====================================================================
_UP_C, _DN_C, _FLAT_C = "#ef4444", "#3b82f6", "#94a3b8"   # 한국식 색: 상승=빨강 / 하락=파랑
                 
# ============================================================
# 🏆 테마 대장주 랭킹 — 검색한 테마의 '대장주'와 그 뒤 순위를 산출/표시
#   대장주 점수 = 거래대금(0.45) + 시가총액(0.25) + 20일 모멘텀(0.20) + 자금유입강도(0.10)
#   * 통화가 다르므로(원/달러) 반드시 '시장(KR/US)별'로 나눠 각 시장 안에서 백분위 랭킹.
#   * analyze_technical_pattern() 결과 dict의 기존 필드만 사용 — 추가 네트워크 호출 0건.
# ============================================================
_LEADER_MED = {1: "🥇", 2: "🥈", 3: "🥉"}


# ── 📌 [발굴기 확장] 픽 히스토리 & 성과 추적 (발굴기 적중률 검증) ──────────
FINDER_HISTORY_FILE = app_state.FILES["finder_history"]   # 하위 호환용


# `from core_constants import *` 로 넘어갈 이름 (언더스코어 포함, 자동 생성)
_EXPORTED = [
    "AUTOREFRESH_MS",
    "BeautifulSoup",
    "FINDER_HISTORY_FILE",
    "GROWTH_FUND_ALLOC",
    "GROWTH_FUND_SECTORS",
    "HAS_PYKRX",
    "HAS_PYPDF",
    "KR_THEME_MAP",
    "LIVE_REFRESH_PAGES",
    "MENU_TREE",
    "MENU_CATEGORIES",
    "MENUS_BY_CATEGORY",
    "VIEW_MODULES",
    "CATEGORY_OF_MENU",
    "NAVER_API_HDRS",
    "NPS_STAKE_SOURCES",
    "PIL",
    "POLY_GAMMA",
    "PYKRX_IMPORT_ERR",
    "PyPDF2",
    "SCORE_W",
    "StringIO",
    "US_THEME_MAP",
    "US_VOL_UNIVERSE",
    "VALUE_STRATEGIES",
    "WATCHLIST_FILE",
    "_DN_C",
    "_ETF_BRANDS",
    "_FLAT_C",
    "_KR_ETF_BRANDS",
    "_KR_PRODUCT_KEYWORDS",
    "_LEADER_MED",
    "_NPS_SCRAPE_HEADERS_BASE",
    "_POPUP_RENDERERS",
    "_UP_C",
    "_diag_note",
    "_genai",
    "_gtypes",
    "alert_center",
    "app_state",
    "calendar",
    "components",
    "concurrent",
    "datetime",
    "diag",
    "fdr",
    "go",
    "json",
    "make_weights",
    "now",
    "np",
    "os",
    "pd",
    "px",
    "pykrx_stock",
    "re",
    "requests",
    "st",
    "st_autorefresh",
    "time",
    "timedelta",
    "traceback",
    "tunable_keys",
    "urllib",
    "yf",
]

__all__ = [_n for _n in _EXPORTED if _n in globals()]
