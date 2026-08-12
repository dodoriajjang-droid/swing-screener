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
# 전역 부트스트랩 — import 시 1회 실행 (분리 전 app.py 상단에서 하던 일)
# =====================================================================
# -*- coding: utf-8 -*-
"""
📚 Jaemini PRO 코어 라이브러리
=====================================================================
app.py 가 13,000줄을 넘어가면서 "무엇이 바뀌었는지" 를 커밋 로그로도, 눈으로도
추적할 수 없게 되어 분리했다. 이 파일은 **데이터 수집·분석·점수·렌더 함수**와
앱 전역 설정(페이지 설정·CSS·세션 초기화)을 담는다.

  core.py   ← 함수 라이브러리 + 전역 설정   (이 파일)
  app.py    ← 사이드바 + 페이지 라우팅      (진입점)
  views/    ← 메뉴별 페이지                 (2단계 분할)

app.py 는 `from core import *` 로 이 파일의 모든 이름을 그대로 승계한다.
따라서 기존 코드의 호출 관계는 하나도 바뀌지 않는다.

주의: 이 파일을 import 하는 즉시 st.set_page_config() 등 전역 설정이 실행된다.
      (분리 전 app.py 최상단에서 실행되던 것과 동일한 순서)
"""

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
if 'smart_cal_year' not in st.session_state: st.session_state.smart_cal_year = now.year
if 'smart_cal_month' not in st.session_state: st.session_state.smart_cal_month = now.month

if 'dcf_target_ticker' not in st.session_state: st.session_state.dcf_target_ticker = "AAPL"
if 'dcf_target_price' not in st.session_state: st.session_state.dcf_target_price = 150.0
if 'dcf_target_fcf' not in st.session_state: st.session_state.dcf_target_fcf = 1000.0
if 'dcf_target_shares' not in st.session_state: st.session_state.dcf_target_shares = 100.0


if "gainers_df" not in st.session_state or '환산(원)' not in st.session_state.gainers_df.columns:
    df, ex_rate, fetch_time = get_us_top_gainers()
    st.session_state.gainers_df = df
    st.session_state.ex_rate = ex_rate
    st.session_state.us_fetch_time = fetch_time


# =====================================================================
# 재수출 — app.py 와 views/ 가 `from core import *` 로 전부 승계한다.
#   조건부 바인딩(PyPDF2 등)이 있어 실제 존재하는 이름만 내보낸다.
# =====================================================================
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
