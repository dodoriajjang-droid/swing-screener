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
    # [v7.3] 브랜드 — 이모지 제목 대신 아이콘 + 버전 배지.
    #   '🆕' 같은 이모지는 Windows 기본 폰트에 없어 두부(□)로 깨진다.
    st.markdown(
        '<div style="display:flex;align-items:center;gap:8px;padding:2px 0 10px;">'
        '<span style="font-size:20px;line-height:1;">'
        '<svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="#1B2129" '
        'stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round">'
        '<path d="M3 17l5-6 4 3 5-8"/><path d="M17 6h4v4"/></svg></span>'
        '<span style="font-weight:800;font-size:16px;letter-spacing:-.01em;color:#12161C;">Jaemini PRO</span>'
        '<span style="font-family:ui-monospace,monospace;font-size:10.5px;color:#79828F;'
        'border:1px solid #E4E8EE;border-radius:4px;padding:1px 5px;">v7.0</span>'
        '</div>', unsafe_allow_html=True)
    st.caption("단기 스윙 & 퀀트 추적 시스템")

    # 실시간 현재 날짜·시간 (KST) — 브라우저에서 초 단위로 갱신
    # [v7.3] 사이드바에서 혼자 다크였던 카드를 주변과 같은 재질로 맞췄다.
    components.html(
        """
        <div id="kst-clock" style="
            font-family: 'Pretendard', -apple-system, BlinkMacSystemFont, 'Segoe UI',
                         'Malgun Gothic', sans-serif;
            background: #F6F7F9; color: #12161C; border: 1px solid #E4E8EE;
            border-radius: 9px; padding: 8px 11px; margin: 4px 0 10px 0;">
            <div id="kst-date" style="font-family: ui-monospace, monospace; font-size: 10.5px;
                 letter-spacing:.08em; color:#79828F;">--</div>
            <div id="kst-time" style="font-family: ui-monospace, monospace; font-size: 20px;
                 font-weight:700; letter-spacing:-.02em; font-variant-numeric: tabular-nums;
                 margin-top:1px;">--:--:--</div>
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
            if (de) de.textContent = `KST · ${y}.${mo}.${d} (${dow})`;
            if (te) te.textContent = `${h}:${mi}:${s}`;
        }
        updateKST();
        setInterval(updateKST, 1000);
        </script>
        """,
        height=74,
    )

    # =================================================================
    # 메뉴 — 카테고리 선택 → 그 안의 메뉴 선택 (2단)
    #
    # 이전에는 라디오 하나에 40개 선택지를 넣고, 그중 카테고리 헤더 5개와
    # 빈 구분선 4개는 눌러도 페이지가 열리지 않고 경고만 띄웠다.
    # 라디오는 '고르면 그게 선택된다'는 약속을 가진 컨트롤이라, 눌렀는데
    # 아무 일도 없으면 쓰는 사람이 자기가 잘못 눌렀다고 느낀다.
    # 지금은 선택지가 전부 실제로 이동하는 항목이고, 한 번에 보이는 개수도
    # 31개에서 카테고리별 3~9개로 줄었다.
    #
    # 메뉴 목록의 원천은 core_constants.MENU_TREE 한 곳이다.
    # =================================================================
    # [v7.3] 분류는 세그먼트 컨트롤, 메뉴는 아이콘 타일.
    #   라디오는 '점 + 이모지 + 텍스트' 세 요소가 한 줄에서 경쟁했고,
    #   분류와 메뉴가 같은 생김새라 위계가 없었다. 세그먼트는 '여기서 고르면
    #   아래 목록이 바뀐다'는 성격이 형태로 드러나고, 타일은 선택을 배경으로
    #   보여줘 점이 필요 없다. 아이콘은 Streamlit 이 이미 싣고 있는 세트라
    #   플랫폼마다 다르게 그려지거나 깨지지 않는다.
    if "nav_category" not in st.session_state:
        st.session_state.nav_category = MENU_CATEGORIES[0]

    st.segmented_control("분류", MENU_CATEGORIES, key="nav_category",
                         label_visibility="collapsed", default=st.session_state.nav_category)
    _cat = st.session_state.nav_category or MENU_CATEGORIES[0]
    _menus = MENUS_BY_CATEGORY[_cat]

    # 카테고리마다 마지막에 보던 메뉴를 각자 기억한다
    _menu_key = f"nav_menu__{_cat}"
    if st.session_state.get(_menu_key) not in _menus:
        st.session_state[_menu_key] = _menus[0]
    selected_menu = st.session_state[_menu_key]

    st.caption(f"{_cat} · {len(_menus)}")
    for _m in _menus:
        _active = (_m == selected_menu)
        if st.button(_m, key=f"navbtn__{_cat}__{_m}", icon=f":material/{ICON_OF_MENU[_m]}:",
                     use_container_width=True,
                     type=("primary" if _active else "tertiary")):
            st.session_state[_menu_key] = _m
            st.rerun()
    clean_menu = selected_menu

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

    # [속도개선] 기존에는 이 버튼 하나가 st.cache_data.clear() 로 앱 전체 캐시를 비웠다.
    #   라벨은 '현재 화면 새로고침'인데 실제로는 종목 마스터·섹터 같은 무거운 캐시까지
    #   전부 날려서, 누른 뒤 첫 화면이 처음 접속처럼 수십 초 걸렸다.
    #   → 자주 바뀌는 시세성 데이터만 비우는 버튼과, 전체를 비우는 버튼을 분리했다.
    if st.button("🔄 시세 새로고침", use_container_width=True,
                 help="지수·수급·거래량·매크로 등 자주 바뀌는 데이터만 다시 받습니다. "
                      "종목 리스트·섹터맵 같은 무거운 캐시는 그대로 두어 빠릅니다."):
        for _fn in (get_kr_index_panel, get_kr_market_breadth, get_volume_surge_drop,
                    get_macro_indicators, get_fear_and_greed, get_market_regime,
                    get_overnight_us_market, get_major_indices, get_marketcap_top,
                    get_industry_changes, get_index_spark):
            try:
                _fn.clear()
            except Exception as _dg_e:
                _diag_note("refresh_live_cache", _dg_e)
        st.rerun()

    with st.expander("🧹 캐시 전체 비우기"):
        st.caption("종목 리스트·섹터맵 등 무거운 캐시까지 모두 비웁니다. "
                   "데이터가 이상할 때만 쓰세요 — 다음 화면이 처음 접속처럼 느려집니다.")
        if st.button("전체 비우고 새로고침", use_container_width=True, key="clear_all_cache"):
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
# 메뉴 → 페이지 모듈 매핑은 core_constants.MENU_TREE 에서 파생된다(VIEW_MODULES).
# 예전에는 이 목록이 사이드바 메뉴 문자열과 따로 관리돼, 라벨을 고치면
# 라우팅이 조용히 끊겨 빈 화면이 떴다.
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
