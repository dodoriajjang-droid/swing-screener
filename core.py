# -*- coding: utf-8 -*-
"""
📚 Jaemini PRO 코어 (계층 합본 + 전역 부트스트랩)
=====================================================================
함수 라이브러리는 아래 6개 계층으로 나뉘어 있고, 이 파일이 전부를 합쳐
`from core import *` 한 줄로 쓸 수 있게 다시 내보낸다.

  core_constants.py  전역 상수 · 공용 import · set_page_config
  core_utils.py      작은 공용 헬퍼
  core_data.py       데이터 수집 · 파싱
  core_ai.py         Gemini 호출
  core_scoring.py    점수 · 랭킹 · 발굴
  core_render.py     Streamlit 렌더

의존은 위에서 아래 한 방향뿐이다(순환 없음).
이 파일 하단의 부트스트랩(CSS 주입·세션 초기화)은 import 즉시 실행된다.
"""
from core_constants import *
from core_utils import *
from core_data import *
from core_ai import *
from core_scoring import *
from core_render import *


# =====================================================================
# 전역 부트스트랩 — app.py 가 **매 실행마다** 호출한다.
#
# ⚠️ 모듈 최상위에 두면 안 된다.
#    파이썬은 모듈을 프로세스당 한 번만 실행하지만, st.session_state 는
#    접속(세션)마다 비어 있고 CSS 도 실행마다 다시 주입해야 한다.
#    최상위에 두면 '서버가 뜬 뒤 첫 접속'에만 적용되고, 그 뒤 접속한 사람은
#    세션 키가 없어 AttributeError 로 페이지가 죽는다.
#    (분할 직후 배포판에서 gainers_df 로 실제 발생한 문제 — 2026-08-12 수정)
# =====================================================================
def bootstrap():
    """CSS 주입 + 세션 상태 초기화. 실행(rerun)마다 호출해야 한다."""
    st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;700&display=swap');

/* =====================================================================
   [v7.3] 타이포 · 간격 · 색 토큰
   구조를 정리한 뒤의 시각 정리. 색은 이미 대부분 같은 램프(slate/blue/red)를
   쓰고 있어 새로 칠하기보다 '기준'을 세우고 리듬을 맞추는 데 집중한다.
   ===================================================================== */
:root {
  /* 화면 색 — 한국 증시 관행: 빨강=상승, 파랑=하락 */
  --jm-ink:      #0f172a;   /* 본문 최다크 */
  --jm-ink-2:    #334155;   /* 보조 텍스트 */
  --jm-muted:    #64748b;   /* 설명·캡션 */
  --jm-faint:    #94a3b8;   /* 라벨·단위 */
  --jm-rule:     #e2e8f0;   /* 구분선 */
  --jm-rule-soft:#eef2f6;
  --jm-surface:  #f8fafc;   /* 옅은 배경 */
  --jm-up:       #dc2626;   /* 상승·순매수 */
  --jm-down:     #2563eb;   /* 하락·순매도 */
  --jm-accent:   #1d4ed8;   /* 강조·링크 */
  --jm-warn:     #b45309;
}

/* 한글 가독성 — 시스템에 있는 한글 폰트를 우선 잡는다.
   (웹폰트를 추가로 받지 않아 첫 화면이 늦어지지 않는다) */
html, body, .stMarkdown, .stMarkdown *, button, input, select, textarea,
[data-testid="stWidgetLabel"], [data-testid="stMetricLabel"],
[data-testid="stCaptionContainer"], [data-testid="stExpander"] summary {
  font-family: "Pretendard", -apple-system, BlinkMacSystemFont, "Segoe UI",
               "Apple SD Gothic Neo", "Malgun Gothic", "맑은 고딕", sans-serif;
}

/* ⚠️ 아이콘에는 위 폰트를 적용하면 안 된다.
   Streamlit 의 접기 화살표 등은 'Material Symbols' 리거처 — 아이콘 '이름'을
   글자로 써 두고 아이콘 폰트가 그림으로 바꿔주는 방식이다. 폰트를 덮어쓰면
   'keyboard_arrow_right' 라는 글자가 그대로 보인다.
   (처음에 [class*="st-"] 로 싹 지정했다가 실제로 이 증상이 났다 — 2026-08-12 수정) */
[data-testid="stIconMaterial"], .material-icons, .material-symbols-rounded,
[class*="material-symbols"], [class*="material-icons"],
[data-testid="stExpander"] summary svg, [data-testid="stExpander"] summary span[class*="icon"] {
  font-family: 'Material Symbols Rounded', 'Material Symbols Outlined',
               'Material Icons', sans-serif !important;
}

/* 숫자는 자리를 맞춰 세로로 읽히게 — 표·지표에서 특히 중요 */
.stMetric, .stMetric *, table, .stDataFrame, [data-testid="stMetricValue"],
[data-testid="stMetricDelta"] {
  font-variant-numeric: tabular-nums;
}
[data-testid="stMetricValue"] {
  font-family: 'JetBrains Mono', ui-monospace, monospace !important;
  letter-spacing: -0.01em;
}
[data-testid="stMetricLabel"] { color: var(--jm-muted) !important; font-size: 0.82rem !important; }
[data-testid="stMetricDelta"] { font-size: 0.82rem !important; }

/* 제목 위계 — 한글은 라틴만큼 자간을 좁히면 답답해져 -0.01em 선에서 멈춘다 */
.stMarkdown h2 { font-size: 1.55rem; font-weight: 800; letter-spacing: -0.01em;
                 margin: 0.2rem 0 0.5rem; color: var(--jm-ink); }
.stMarkdown h3 { font-size: 1.2rem;  font-weight: 700; letter-spacing: -0.005em;
                 margin: 1.1rem 0 0.4rem; color: var(--jm-ink); }
.stMarkdown h4 { font-size: 1.02rem; font-weight: 700; margin: 0.9rem 0 0.35rem; }
.stMarkdown h5 { font-size: 0.95rem; font-weight: 800; margin: 0.8rem 0 0.3rem;
                 color: var(--jm-ink-2); }

/* 섹션 리듬 — 구분선이 너무 진하고 촘촘해 화면이 잘려 보이던 것을 완화 */
hr, [data-testid="stDivider"] { margin: 1.15rem 0 !important; border-color: var(--jm-rule) !important; }

/* 캡션·도움말 — 본문과 대비를 확실히 해 '설명'임이 드러나게 */
[data-testid="stCaptionContainer"], .stCaption { color: var(--jm-muted) !important; line-height: 1.6; }

/* 접기(expander) — 지금은 접힌 그룹이 많아졌으므로 헤더가 눌러야 할 것처럼 보여야 한다 */
[data-testid="stExpander"] details { border: 1px solid var(--jm-rule) !important;
                                     border-radius: 10px !important; background: #fff; }
[data-testid="stExpander"] summary { font-weight: 700 !important; color: var(--jm-ink-2) !important; }
[data-testid="stExpander"] summary:hover { color: var(--jm-accent) !important; }

/* 탭 — 통합으로 탭이 늘었으니 현재 위치가 분명해야 한다 */
.stTabs [data-baseweb="tab"] { font-weight: 700; color: var(--jm-muted); }
.stTabs [aria-selected="true"] { color: var(--jm-accent) !important; }

/* 표 — 머리행을 눌러 앉히고 본문과 분리 */
th { font-weight: 700 !important; background-color: var(--jm-surface) !important;
     color: var(--jm-ink-2) !important; }
table, .stDataFrame { font-family: 'JetBrains Mono', ui-monospace, monospace !important; }

/* 사이드바 — 2단 메뉴가 되면서 항목 간격이 중요해졌다 */
section[data-testid="stSidebar"] label { line-height: 1.5; }
section[data-testid="stSidebar"] [data-testid="stCaptionContainer"] { margin-top: 0.2rem; }

/* ── 버튼 ─────────────────────────────────────────────────────────
   [v7.3] 예전에는 버튼마다 다른 그라데이션(블루·에메랄드·바이올렛·인디고·앰버)을
   깔았다. 다섯 개가 서로 다른 색으로 동등하게 소리치니 색이 의미를 잃고 장식이 됐고,
   정작 중요한 가격·등락률이 가장 조용해졌다.
   지금은 색을 등락(빨강 상승 / 파랑 하락)에만 남기고, 버튼은 무채색으로 둔다.
   한 화면에서 주인공은 primary 하나뿐이다. */
.stButton > button, .stDownloadButton > button, .stFormSubmitButton > button {
    border-radius: 8px !important;
    font-weight: 700 !important;
    letter-spacing: -0.005em;
    transition: background .12s ease, border-color .12s ease, color .12s ease !important;
}
/* 보조 버튼 — 조용한 외곽선 */
.stButton > button[kind="secondary"], .stDownloadButton > button {
    background: #fff !important; color: var(--jm-ink-2) !important;
    border: 1px solid var(--jm-rule) !important;
}
.stButton > button[kind="secondary"]:hover, .stDownloadButton > button:hover {
    border-color: #c9d0da !important; color: var(--jm-ink) !important; background: var(--jm-surface) !important;
}
/* 주 버튼 — 진한 무채색. 화면당 하나가 원칙 */
.stButton > button[kind="primary"], .stFormSubmitButton > button {
    background: #1b2129 !important; color: #fff !important; border: 1px solid #1b2129 !important;
}
.stButton > button[kind="primary"]:hover, .stFormSubmitButton > button:hover {
    background: #2b333e !important; border-color: #2b333e !important;
}

/* 사이드바 메뉴 타일 — 선택은 배경 + 좌측 바로 보여준다(라디오 점 없이)
   .st-key-<key> 로 범위를 좁혀, 같은 사이드바의 새로고침 버튼 등은 건드리지 않는다 */
section[data-testid="stSidebar"] [class*="st-key-navbtn__"] button {
    text-align: left !important; justify-content: flex-start !important;
    padding: 7px 11px !important; font-size: 13.5px !important; font-weight: 600 !important;
    border-radius: 8px !important; position: relative; min-height: 0 !important;
}
section[data-testid="stSidebar"] [class*="st-key-navbtn__"] button[kind="tertiary"] {
    color: var(--jm-ink-2) !important; background: transparent !important; border: none !important;
}
section[data-testid="stSidebar"] [class*="st-key-navbtn__"] button[kind="tertiary"]:hover {
    background: rgba(15,23,42,.05) !important; color: var(--jm-ink) !important;
}
section[data-testid="stSidebar"] [class*="st-key-navbtn__"] button[kind="primary"] {
    background: #1b2129 !important; color: #fff !important; font-weight: 700 !important;
    border: none !important;
}
section[data-testid="stSidebar"] [class*="st-key-navbtn__"] button[kind="primary"]::before {
    content: ""; position: absolute; left: 3px; top: 8px; bottom: 8px; width: 2px;
    border-radius: 2px; background: rgba(255,255,255,.55);
}
/* 메뉴 타일 사이 간격을 좁혀 목록처럼 읽히게 */
section[data-testid="stSidebar"] [class*="st-key-navbtn__"] { margin-bottom: -8px; }

/* 분류 세그먼트 — 메뉴 타일보다 한 단계 조용하게
   (Streamlit 의 segmented_control 은 data-testid="stButtonGroup" 으로 렌더된다) */
section[data-testid="stSidebar"] [data-testid="stButtonGroup"] button {
    font-size: 11.5px !important; font-weight: 700 !important; padding: 3px 9px !important;
    min-height: 0 !important;
}

</style>
""", unsafe_allow_html=True)

    # 세션 상태 초기화
    _now = datetime.now()      # 모듈 로드 시각이 아니라 '이번 실행' 시각을 쓴다
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
    if 'smart_cal_year' not in st.session_state: st.session_state.smart_cal_year = _now.year
    if 'smart_cal_month' not in st.session_state: st.session_state.smart_cal_month = _now.month

    if 'dcf_target_ticker' not in st.session_state: st.session_state.dcf_target_ticker = "AAPL"
    if 'dcf_target_price' not in st.session_state: st.session_state.dcf_target_price = 150.0
    if 'dcf_target_fcf' not in st.session_state: st.session_state.dcf_target_fcf = 1000.0
    if 'dcf_target_shares' not in st.session_state: st.session_state.dcf_target_shares = 100.0

    # [속도개선] 미국 급등주 스냅샷은 여기서 미리 받지 않는다.
    #   이 데이터를 쓰는 화면은 두 곳뿐인데(홈의 AI 브리핑·간밤의 미국 급등주),
    #   여기서 받으면 계산기나 ETF 화면을 열 때도 수집이 끝날 때까지 화면이 뜨지 않았다.
    #   필요한 화면에서 ensure_us_gainers() 를 호출한다.


# =====================================================================
# 재수출 — app.py 와 views/ 가 `from core import *` 로 전부 승계한다.
#   조건부 바인딩(PyPDF2 등)이 있어 실제 존재하는 이름만 내보낸다.
# =====================================================================
_EXPORTED = [
    "bootstrap",          # 매 실행마다 app.py 가 호출하는 부트스트랩
    "ensure_us_gainers",  # 미국 급등주 스냅샷 지연 로딩
    "prefetch_home_data", # 홈 대시보드 데이터 병렬 프리페치
    # 메뉴 구조 (core_constants.MENU_TREE 에서 파생) — 사이드바·라우팅이 쓴다
    "EXPLAIN_GROUPS",
    "explain_score",
    "render_score_why",
    "ICON_OF_MENU",
    "MENU_TREE",
    "MENU_CATEGORIES",
    "MENUS_BY_CATEGORY",
    "VIEW_MODULES",
    "CATEGORY_OF_MENU",
    "AUTOREFRESH_MS",
    "BeautifulSoup",
    "FINDER_HISTORY_FILE",
    "GROWTH_FUND_ALLOC",
    "GROWTH_FUND_SECTORS",
    "HAS_PYKRX",
    "HAS_PYPDF",
    "KR_THEME_MAP",
    "LIVE_REFRESH_PAGES",
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
    "_align_flags",
    "_calc_expert_metrics",
    "_chg_color",
    "_clean_ipo_df",
    "_clip",
    "_deep_find_number",
    "_diag_index_endpoints",
    "_diag_note",
    "_expert_chat_body",
    "_expert_chat_dialog",
    "_extract_nps_stake_from_html",
    "_f_num",
    "_fetch_nps_stake_dart",
    "_fetch_nps_stake_multi",
    "_fetch_stock_investor_2d",
    "_finder_export_df",
    "_finder_hide",
    "_finder_history_load",
    "_finder_risk",
    "_finder_rr",
    "_finder_sort_val",
    "_finder_tech",
    "_finder_value",
    "_flow_bar_html",
    "_genai",
    "_genai_generate",
    "_get_etf_list",
    "_get_kr_etf_codes",
    "_google_news_rss",
    "_gtx_translate_en_ko",
    "_gtypes",
    "_index_card_html",
    "_is_pos_flow",
    "_kr_change_map",
    "_kr_market_snapshot",
    "_krx_list_from_naver",
    "_krx_retry",
    "_leader_callout_html",
    "_leader_fmt_big",
    "_leader_fmt_mom",
    "_leader_fmt_price",
    "_leader_metrics",
    "_leader_num",
    "_leader_pctl",
    "_leaders_table_html",
    "_market_flows_html",
    "_naver_json",
    "_naver_sector_map",
    "_nb_won",
    "_norm_etf_name",
    "_num",
    "_open_expert_chat",
    "_open_popup",
    "_open_quant_assistant",
    "_open_vptm",
    "_parse_ipo_enddate",
    "_poly_num",
    "_poly_parse_list",
    "_popup_button",
    "_quant_assistant_body",
    "_quant_assistant_dialog",
    "_register_popup",
    "_render_flow_chips",
    "_render_handover",
    "_render_netbuy_list",
    "_run_popup_renderer",
    "_short_trend_figure",
    "_sign_of",
    "_sparkline_svg",
    "_su_amt",
    "_theme_leader_ranking",
    "_to_eok",
    "_universal_popup",
    "_value_factors",
    "_value_rank",
    "_vptm_body",
    "_vptm_dialog",
    "alert_center",
    "analyze_technical_pattern",
    "analyze_theme_trends",
    "app_state",
    "ask_gemini",
    "ask_gemini_vision",
    "build_finder_candidates",
    "calc_ai_target_price",
    "calc_recovery_score",
    "calendar",
    "classify_news_sentiment",
    "classify_tp_change",
    "components",
    "concurrent",
    "datetime",
    "df",
    "diag",
    "display_sorted_results",
    "draw_stock_card",
    "ex_rate",
    "extract_beneficiary_stocks",
    "fdr",
    "fetch_article_excerpt",
    "fetch_naver_volume",
    "fetch_polymarket_markets",
    "fetch_time",
    "finder_history_append",
    "finder_history_perf",
    "get_advanced_chart_data",
    "get_consensus_signal",
    "get_credit_balance_naver",
    "get_daily_market_briefing",
    "get_daily_sise_and_investor",
    "get_dart_corp_map",
    "get_dividend_portfolio",
    "get_drawdown_info",
    "get_economic_events",
    "get_fear_and_greed",
    "get_financial_deep_data",
    "get_finder_briefing",
    "get_finder_exclusion_set",
    "get_foreign_broker_estimate",
    "get_fundamentals",
    "get_granular_themes",
    "get_growth_fund_stocks_with_ai",
    "get_historical_data",
    "get_index_ret20",
    "get_index_spark",
    "get_industry_changes",
    "get_institution_buy_trend",
    "get_intraday_estimate",
    "get_intraday_estimate_debug",
    "get_investor_trend",
    "get_korean_name",
    "get_kr_index_panel",
    "get_kr_investor_flows",
    "get_kr_market_breadth",
    "get_kr_sector_heat",
    "get_kr_universe_naver",
    "get_krx_etf_list",
    "get_krx_name_code_list",
    "get_krx_stocks",
    "get_latest_naver_news",
    "get_limit_stocks",
    "get_longterm_value_stocks_with_ai",
    "get_macro_indicators",
    "get_major_indices",
    "get_market_label",
    "get_market_map",
    "get_market_mood",
    "get_market_regime",
    "get_market_warnings",
    "get_marketcap_top",
    "get_naver_ipo_data",
    "get_naver_research",
    "get_news_issue_impact",
    "get_nps_holdings",
    "get_nps_us_portfolio",
    "get_overnight_us_market",
    "get_pension_fund_trend",
    "get_scan_targets",
    "get_sector_per",
    "get_short_selling_risk",
    "get_stock_list_by_market",
    "get_stock_news",
    "get_stock_research_history",
    "get_stock_sector_kr",
    "get_theme_politics_radar",
    "get_theme_stocks_with_ai",
    "get_today_research_details",
    "get_trading_value_kings",
    "get_trending_sectors",
    "get_trending_themes_with_ai",
    "get_us_etf_summary",
    "get_us_scan_targets",
    "get_us_sector_etfs",
    "get_us_sector_heat",
    "get_us_sector_map",
    "get_us_top_gainers",
    "get_us_volume_surge_drop",
    "get_value_metrics",
    "get_volume_surge_drop",
    "get_weekly_trend",
    "go",
    "is_kr_etf_etn",
    "json",
    "key",
    "load_watchlist",
    "macro_regime_notes",
    "macro_tilt_for",
    "make_weights",
    "match_sector_heat",
    "nb_render_briefing",
    "nb_render_time_machine",
    "nb_render_volume_profile",
    "nb_time_machine",
    "nb_volume_profile",
    "now",
    "np",
    "os",
    "parse_portfolio_upload",
    "parse_prev_target_price",
    "parse_target_price",
    "pd",
    "px",
    "pykrx_stock",
    "re",
    "render_global_quant_button",
    "render_industry_changes",
    "render_kr_market_breadth",
    "render_main_index_panel",
    "render_main_volume_top10",
    "render_major_indices_bar",
    "render_market_regime_banner",
    "render_marketcap_top",
    "render_multi_theme_dataframe",
    "render_overnight_banner",
    "render_overnight_tape",
    "render_regime_hero",
    "render_sentiment_strip",
    "render_single_stock_themes",
    "render_theme_leaders",
    "render_trending_sectors",
    "render_watchlist_signals",
    "render_week_catalysts",
    "requests",
    "resolve_etf_codes",
    "save_watchlist",
    "score_one",
    "search_nps_holding",
    "search_us_ticker",
    "show_beginner_guide",
    "show_trading_guidelines",
    "st",
    "st_autorefresh",
    "standardize_opinion",
    "style_ipo_table",
    "style_report_table",
    "style_sector_etf_table",
    "style_us_gainers_table",
    "style_us_volume_table",
    "style_volume_table",
    "style_warning_table",
    "time",
    "timedelta",
    "traceback",
    "translate_poly_questions",
    "tunable_keys",
    "update_news_state",
    "urllib",
    "value_passes",
    "yf",
]

__all__ = [_n for _n in _EXPORTED if _n in globals()]
