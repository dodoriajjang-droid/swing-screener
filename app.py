# -*- coding: utf-8 -*-
"""
📈 Jaemini PRO — 진입점 (사이드바 + 페이지 라우팅)

함수 라이브러리는 core.py 에 있다. `from core import *` 로 전부 승계하므로
아래 라우팅 코드는 분리 전과 동일한 이름들을 그대로 쓴다.

이 파일은 Streamlit 이 **매 실행(rerun)마다** 처음부터 다시 돌린다.
반면 core 는 모듈이라 프로세스당 한 번만 실행된다. 그래서 실행마다 필요한 일
(페이지 설정·CSS·세션 초기화)은 반드시 여기서 호출한다.
"""
# set_page_config 는 그 실행의 첫 st 명령이어야 하므로 import 보다 먼저 부른다.
import streamlit as st
st.set_page_config(page_title="Jaemini PRO 터미널 v7.0", layout="wide", page_icon="📈")

from core import *      # 데이터·분석·점수·렌더 함수 (프로세스당 1회 로드)
import core             # 모듈 자체 참조가 필요할 때

bootstrap()             # CSS 주입 + 세션 상태 초기화 — 매 실행마다 필요

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
    # [v7.2 버그수정] secrets.toml 이 없으면 `in st.secrets` 자체가
    # StreamlitSecretNotFoundError 를 던져 앱 전체가 죽었다(로컬 실행 시 항상).
    # 클라우드에는 secrets 가 설정돼 있어 드러나지 않던 문제.
    _secret_key = None
    try:
        if "GEMINI_API_KEY" in st.secrets:
            _secret_key = st.secrets["GEMINI_API_KEY"]
    except Exception as _dg_e:
        _diag_note("st.secrets", _dg_e, detail="secrets.toml 없음 — 키 직접 입력으로 전환")

    if _secret_key is not None:
        api_key_input = str(_secret_key) if isinstance(_secret_key, str) else str(list(_secret_key.values())[0])
        st.success("✅ 시스템 연동 완료")
    else:
        api_key_input = st.text_input("Gemini API Key를 입력하세요", type="password")
        if api_key_input:
            api_key_input = str(api_key_input)
            st.success("✅ 시스템 연동 완료")
            
    # [v7.2] API 키를 세션에 게시 — 전역 변수(api_key_input)에 직접 의존하던
    #        퀀트 비서/팝업이 모듈로 분리돼도 동작하도록 결합을 끊는다.
    st.session_state["_api_key"] = api_key_input

    if st.button("🔄 현재 화면 새로고침", use_container_width=True):
        st.cache_data.clear()
        st.rerun()

    # [v7.2] 데이터 수집 상태 — 조용히 실패한 수집이 있으면 여기서 먼저 눈에 띈다
    st.divider()
    diag.render_badge()


render_global_quant_button()

if selected_menu in LIVE_REFRESH_PAGES:
    st_autorefresh(interval=AUTOREFRESH_MS, limit=None, key="news_autorefresh")

# =====================================================================
# 페이지 라우팅 — 선택된 메뉴의 모듈만 지연 import 해서 render(ctx) 호출
#   · 각 페이지는 views/ 아래 개별 파일 (분리 전에는 전부 app.py 안에 있었다)
#   · 지연 import 라서 안 쓰는 페이지는 아예 로드되지 않는다 (초기 구동 단축)
# =====================================================================
VIEW_MODULES = {
    '🎛️ 홈: 종합 대시보드': "views.home_dashboard",
    '💼 내 계좌 & 포트폴리오 진단': "views.portfolio",
    '⭐ 내 관심종목 모니터링': "views.watchlist",
    '🌍 글로벌 매크로 & AI 분석 (v6.0)': "views.macro",
    '🗺️ 시장 주도주 자금 히트맵': "views.money_heatmap",
    '🕸️ 실시간 섹터 순환매 추적': "views.sector_rotation",
    '📅 핵심 증시 일정 & IPO 달력': "views.calendar_ipo",
    '📋 코스피·코스닥 종목 리스트': "views.stock_list",
    '🚀 단기 스윙 퀀트 스캐너': "views.swing_scanner",
    '📉 낙폭과대 스캐너 (고점대비 -30%↓)': "views.drawdown_scanner",
    '🧭 AI 통합 투자 발굴기 (테스트)': "views.ai_finder",
    '🏛️ 국민연금 5% 대량보유 픽': "views.nps_picks",
    '💎 장기 우량주 & 가치주 발굴': "views.value_finder",
    '⚡ 메가트렌드 & 테마 대장주': "views.theme_leaders",
    '🇰🇷 국민성장펀드 12대 산업 수혜주': "views.growth_fund",
    '🔥 간밤의 미국 급등주 & 수혜주': "views.us_overnight",
    '🚨 당일 상/하한가 분석': "views.limit_moves",
    '💰 국장 수급 분석 (외국인·기관·개인)': "views.investor_flows",
    '🔥 지금 뜨는 섹터 (국장·미장)': "views.hot_sectors",
    '🚦 거래량 급증 & 시장 경보': "views.volume_alerts",
    '📰 실시간 특징주 속보 & 리포트': "views.news_flash",
    '🔬 개별 기업 정밀 진단 (AI 비전)': "views.company_deep_dive",
    '👁️ 차트 이미지 AI 비전 분석': "views.chart_vision",
    '📊 국내외 핵심 ETF 분석': "views.etf_analysis",
    '💰 고배당주 파이프라인 (TOP 300)': "views.dividend_pipeline",
    '🎯 증권사 목표가 컨센서스': "views.consensus",
    '⚖️ 적정 주가 계산기 (버핏 모델)': "views.fair_value",
    '👴 노후 준비 ETF 시뮬레이터 (v2.0)': "views.retirement_sim",
    '🔮 폴리마켓 예측시장 (금리·경제·정치)': "views.polymarket",
    '🗞️ 뉴스 이슈 TOP & 영향 분석': "views.news_impact",
    '🚨 통합 경보 센터 (뉴스·차트·일정)': "views.alert_center_page",
}

_ctx = {
    '_nav_changed': _nav_changed,
    'api_key_input': api_key_input,
}

_view_name = VIEW_MODULES.get(selected_menu)
if _view_name:
    import importlib
    try:
        importlib.import_module(_view_name).render(_ctx)
    except Exception as _e:
        _diag_note(_view_name, _e, detail=str(selected_menu), level="error")
        st.error(f"❌ 페이지를 여는 중 오류가 발생했습니다 — {type(_e).__name__}: {_e}")
        st.caption("사이드바 아래 '데이터 수집 진단'에서 자세한 내용을 볼 수 있습니다.")
        st.exception(_e)


# =====================================================================
# [v7.2] 데이터 수집 진단 패널 — 어떤 메뉴에서든 화면 하단에서 확인 가능
#   화면이 비어 보일 때 "데이터가 없는 것"인지 "수집이 실패한 것"인지 구분한다.
# =====================================================================
diag.render_panel()


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
