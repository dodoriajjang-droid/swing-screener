# -*- coding: utf-8 -*-
"""
nomura_theme.py — Jaemini PRO 'LIVE EQUITY RESEARCH' 다크 터미널 테마
=====================================================================
글로벌 IB 리서치 카드(블랙 + 그린 + 앰버, 모노스페이스) 무드를 Streamlit 전역에 입힙니다.

구성:
  1) inject_nomura_theme()  : 전역 CSS 1회 주입 (위젯·표·버튼·탭·사이드바 등 전부)
  2) set_plotly_nomura()    : Plotly 기본 템플릿을 다크 리서치 톤으로 교체
  3) 리포트 컴포넌트 헬퍼   : nmr_topbar / nmr_masthead / nmr_section / nmr_note / nmr_badge / nmr_end
  4) NMR                    : 색상 토큰 dict (앱 코드에서 재사용)

사용법(app.py 상단, st.set_page_config 직후):
    from nomura_theme import inject_nomura_theme, set_plotly_nomura, \
        nmr_topbar, nmr_masthead, nmr_section, nmr_note, nmr_badge, nmr_end, NMR
    inject_nomura_theme()
    set_plotly_nomura()

※ st.dataframe(글라이드 그리드)·셀렉트박스 팝오버 색은 CSS가 닿지 않으므로
   .streamlit/config.toml 의 [theme] 설정(동봉)과 함께 써야 완성됩니다.
"""

import streamlit as st

# ──────────────────────────────────────────────────────────────────────
# 0. 색상 토큰 (리서치 카드 팔레트)
# ──────────────────────────────────────────────────────────────────────
NMR = {
    "bg":      "#0A0A0A",   # 페이지 배경 (피치 블랙)
    "bg2":     "#070707",   # 사이드바/탑바
    "card":    "#0E0E0E",   # 카드 배경
    "card2":   "#101010",   # 카드 배경(살짝 밝게)
    "line":    "#1F1F1F",   # 기본 보더
    "line2":   "#2A2A2A",   # 강조 보더
    "txt":     "#E8E8E8",   # 본문
    "mut":     "#8B9097",   # 보조 텍스트
    "dim":     "#5C6168",   # 흐린 텍스트
    "green":   "#00E676",   # 브랜드 그린 (BUY / LIVE)
    "green_d": "#041007",   # 그린 배지 위 잉크
    "amber":   "#FFB000",   # 가격·섹션 헤더 앰버
    "blue":    "#4D9FFF",
    "red":     "#FF4D4F",
    "up":      "#FF5252",   # 한국식 상승(빨강)
    "dn":      "#54A0FF",   # 한국식 하락(파랑)
    "purple":  "#B287FF",
    "teal":    "#2DD4BF",
    "pink":    "#FF6BBD",
}

_FONT = "'JetBrains Mono','Noto Sans KR',ui-monospace,Menlo,Consolas,monospace"


# ──────────────────────────────────────────────────────────────────────
# 1. 전역 CSS 주입
# ──────────────────────────────────────────────────────────────────────
def inject_nomura_theme():
    if st.session_state.get("_nmr_css_done"):
        # rerun 마다 다시 그려도 무해하지만, 마크다운 노드 수를 줄이기 위해 1회만.
        pass
    st.session_state["_nmr_css_done"] = True

    st.markdown(f"""
<style>
@import url('https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;500;700;800&family=Noto+Sans+KR:wght@400;500;700;900&display=swap');

:root {{
  --nmr-bg:{NMR['bg']}; --nmr-card:{NMR['card']}; --nmr-card2:{NMR['card2']};
  --nmr-line:{NMR['line']}; --nmr-line2:{NMR['line2']};
  --nmr-txt:{NMR['txt']}; --nmr-mut:{NMR['mut']}; --nmr-dim:{NMR['dim']};
  --nmr-green:{NMR['green']}; --nmr-amber:{NMR['amber']};
  --nmr-blue:{NMR['blue']}; --nmr-red:{NMR['red']};
}}

/* ── 캔버스 ───────────────────────────────────────────── */
html, body, .stApp, [data-testid="stAppViewContainer"] {{
  background: var(--nmr-bg) !important;
  color: var(--nmr-txt);
  font-family: {_FONT};
}}
[data-testid="stHeader"] {{ background: rgba(10,10,10,.85) !important; border-bottom: 1px solid var(--nmr-line); backdrop-filter: blur(4px); }}
[data-testid="stToolbar"] {{ right: 0.5rem; }}
.block-container {{ padding-top: 1.2rem; max-width: 1180px; }}
* {{ scrollbar-width: thin; scrollbar-color: #2c2c2c var(--nmr-bg); }}
*::-webkit-scrollbar {{ width: 9px; height: 9px; }}
*::-webkit-scrollbar-thumb {{ background: #262626; border-radius: 0; border: 2px solid var(--nmr-bg); }}
*::-webkit-scrollbar-track {{ background: var(--nmr-bg); }}
::selection {{ background: rgba(0,230,118,.25); color: #fff; }}
a, a:visited {{ color: var(--nmr-green); text-decoration: none; }}
a:hover {{ text-decoration: underline; }}
hr, [data-testid="stDivider"] hr {{ border-color: var(--nmr-line) !important; margin: 1.1rem 0; }}

/* ── 타이포그래피: 리서치 헤더 ───────────────────────── */
h1, h2, h3, h4, h5, h6 {{ font-family: {_FONT}; }}
h1 {{ color:#fff; font-weight:800; letter-spacing:-0.5px; border-bottom:1px solid var(--nmr-line); padding-bottom:.45rem; }}
h2 {{ color:#fff; font-weight:800; letter-spacing:-0.3px; border-bottom:1px solid var(--nmr-line); padding-bottom:.4rem; }}
h3 {{ color:#f1f1f1; font-weight:700; }}
/* ####, ##### 헤더 → 앰버 섹션 라벨 (이미지의 '—[01]…' 톤) */
h4, h5 {{
  color: var(--nmr-amber) !important; font-weight:800;
  font-size: .95rem; letter-spacing: .04em;
  margin-top: 1.1rem;
}}
h4::before, h5::before {{ content:"— "; color:#4a4a4a; }}
h6 {{ color: var(--nmr-mut); font-weight:700; letter-spacing:.06em; }}
[data-testid="stCaptionContainer"], .stCaption, small {{ color: var(--nmr-dim) !important; }}
strong, b {{ color:#f3f3f3; }}
code {{ background:#141414; color: var(--nmr-amber); border:1px solid var(--nmr-line); border-radius:2px; padding:0 .3em; font-family:{_FONT}; }}
pre, .stCode, [data-testid="stCodeBlock"] {{ background:#0c0c0c !important; border:1px solid var(--nmr-line); border-radius:2px; }}

/* ── 메트릭: TARGET PRICE 카드 ───────────────────────── */
[data-testid="stMetric"] {{
  background: var(--nmr-card); border:1px solid var(--nmr-line);
  border-radius:2px; padding:12px 14px 10px;
}}
[data-testid="stMetric"]:hover {{ border-color:#2e2e2e; }}
[data-testid="stMetricLabel"] {{ color: var(--nmr-mut) !important; }}
[data-testid="stMetricLabel"] p {{ font-size:.72rem !important; letter-spacing:.08em; font-weight:700; color:var(--nmr-mut) !important; }}
[data-testid="stMetricValue"] {{ color: var(--nmr-amber) !important; font-family:{_FONT}; font-weight:800; }}
[data-testid="stMetricDelta"] {{ font-family:{_FONT}; font-weight:700; }}

/* ── 표 (st.table / markdown / HTML) ─────────────────── */
table {{ border-collapse:collapse !important; font-family:{_FONT}; }}
thead tr th, th {{
  background:#0D0D0D !important; color: var(--nmr-amber) !important;
  border:1px solid #232323 !important; font-size:.74rem !important;
  letter-spacing:.08em; font-weight:700 !important; text-transform:uppercase;
  padding:8px 10px !important;
}}
tbody tr td, td {{
  background: var(--nmr-card) !important; color:#D6D6D6 !important;
  border:1px solid var(--nmr-line) !important; font-size:.84rem;
  padding:7px 10px !important;
}}
tbody tr:hover td {{ background:#121212 !important; }}
[data-testid="stTable"] {{ border:1px solid var(--nmr-line); border-radius:2px; }}
[data-testid="stDataFrame"] {{ border:1px solid var(--nmr-line); border-radius:2px; }}

/* ── 버튼: 터미널 키 ─────────────────────────────────── */
.stButton > button, .stDownloadButton > button, [data-testid="stLinkButton"] a, .stFormSubmitButton > button {{
  background: #101010 !important; color:#D6D6D6 !important;
  border:1px solid var(--nmr-line2) !important; border-radius:2px !important;
  font-family:{_FONT} !important; font-weight:700; font-size:.83rem;
  letter-spacing:.03em; box-shadow:none !important; transition:all .12s ease;
}}
.stButton > button:hover, .stDownloadButton > button:hover, [data-testid="stLinkButton"] a:hover, .stFormSubmitButton > button:hover {{
  border-color: var(--nmr-green) !important; color: var(--nmr-green) !important;
  background: rgba(0,230,118,.07) !important;
}}
.stButton > button[kind="primary"], .stFormSubmitButton > button[kind="primary"] {{
  background: var(--nmr-green) !important; color:{NMR['green_d']} !important;
  border-color: var(--nmr-green) !important; font-weight:800;
}}
.stButton > button[kind="primary"]:hover {{ filter:brightness(1.1); color:{NMR['green_d']} !important; }}

/* ── 입력류 ──────────────────────────────────────────── */
[data-baseweb="input"], [data-baseweb="textarea"], .stTextArea textarea,
[data-baseweb="select"] > div, [data-testid="stNumberInputContainer"] {{
  background:#0F0F0F !important; border-color: var(--nmr-line2) !important;
  color: var(--nmr-txt) !important; border-radius:2px !important; font-family:{_FONT};
}}
[data-baseweb="input"] input, .stTextArea textarea, [data-baseweb="select"] input {{ color: var(--nmr-txt) !important; font-family:{_FONT}; }}
[data-baseweb="input"]:focus-within, [data-baseweb="select"] > div:focus-within, .stTextArea textarea:focus {{
  border-color: var(--nmr-green) !important; box-shadow:0 0 0 1px rgba(0,230,118,.35) !important;
}}
[data-testid="stWidgetLabel"] p {{ color: var(--nmr-mut) !important; font-size:.8rem; font-weight:700; letter-spacing:.02em; }}

/* ── 탭: 리서치 인덱스 ───────────────────────────────── */
.stTabs [data-baseweb="tab-list"] {{ gap:2px; border-bottom:1px solid var(--nmr-line); }}
.stTabs [data-baseweb="tab"] {{
  background:transparent; color: var(--nmr-mut); font-family:{_FONT};
  font-weight:700; font-size:.84rem; letter-spacing:.02em; border-radius:0;
}}
.stTabs [aria-selected="true"] {{ color: var(--nmr-green) !important; }}
.stTabs [data-baseweb="tab-highlight"] {{ background-color: var(--nmr-green); height:2px; }}
.stTabs [data-baseweb="tab-border"] {{ background-color: var(--nmr-line); }}

/* ── 익스팬더 / 알림 / 챗 ────────────────────────────── */
[data-testid="stExpander"] {{ background: var(--nmr-card); border:1px solid var(--nmr-line) !important; border-radius:2px !important; }}
[data-testid="stExpander"] summary {{ font-family:{_FONT}; font-weight:700; color:#cfcfcf; }}
[data-testid="stExpander"] summary:hover {{ color: var(--nmr-green); }}
[data-testid="stAlert"], [data-testid="stAlertContainer"] {{
  background:#101010 !important; border:1px solid var(--nmr-line) !important;
  border-left:3px solid var(--nmr-amber) !important; border-radius:2px !important;
  color:#d6d6d6 !important;
}}
[data-testid="stAlert"] p, [data-testid="stAlertContainer"] p {{ color:#d6d6d6 !important; font-family:{_FONT}; font-size:.86rem; }}
[data-testid="stChatMessage"] {{ background: var(--nmr-card); border:1px solid var(--nmr-line); border-radius:2px; }}
[data-testid="stChatInput"] {{ background:#0F0F0F; border-color: var(--nmr-line2); }}

/* ── 라디오/체크/프로그레스 ──────────────────────────── */
[data-testid="stRadio"] label p, [data-testid="stCheckbox"] label p {{ color:#c9c9c9 !important; font-size:.84rem; }}
.stProgress > div > div > div {{ background-color: var(--nmr-green) !important; }}
[data-testid="stContainerWithBorder"], [data-testid="stVerticalBlockBorderWrapper"] > div > div[data-testid="stVerticalBlock"] {{ border-color: var(--nmr-line) !important; }}

/* ── 사이드바: 단말기 패널 ───────────────────────────── */
[data-testid="stSidebar"] {{
  background: {NMR['bg2']} !important; border-right:1px solid #181818;
}}
[data-testid="stSidebar"] [data-testid="stRadio"] label p {{ font-size:.8rem !important; }}
[data-testid="stSidebar"] [data-testid="stRadio"] label:hover p {{ color: var(--nmr-green) !important; }}
.nmr-side-brand {{ padding:6px 2px 10px; border-bottom:1px solid var(--nmr-line); margin-bottom:8px; }}
.nmr-side-brand-top {{ font-family:{_FONT}; font-weight:800; font-size:1.05rem; color:#fff; letter-spacing:.5px; }}
.nmr-side-brand-top .sq {{ color: var(--nmr-green); }}
.nmr-side-brand-sub {{ font-family:{_FONT}; color: var(--nmr-green); font-size:.66rem; font-weight:700; letter-spacing:.18em; margin-top:4px; }}
.nmr-side-brand-sub .v {{ color: var(--nmr-amber); letter-spacing:.04em; }}
.nmr-side-brand-desc {{ color: var(--nmr-dim); font-size:.74rem; margin-top:5px; }}

/* ── 리포트 컴포넌트 ─────────────────────────────────── */
.nmr-topbar {{
  display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; gap:6px;
  background:#050505; border:1px solid var(--nmr-line); border-radius:2px;
  padding:7px 12px; margin-bottom:10px;
  font-family:{_FONT}; font-size:.7rem; font-weight:700; letter-spacing:.14em;
}}
.nmr-topbar .l {{ color: var(--nmr-green); }}
.nmr-topbar .r {{ color: var(--nmr-mut); letter-spacing:.08em; }}
.nmr-topbar .live {{ color: var(--nmr-green); margin-left:10px; animation:nmrblink 1.6s infinite; }}
@keyframes nmrblink {{ 0%,100%{{opacity:1}} 50%{{opacity:.35}} }}

.nmr-mast {{
  background: linear-gradient(180deg, #0D0D0D, #0A0A0A);
  border:1px solid var(--nmr-line); border-radius:2px;
  padding:18px 20px 16px; margin-bottom:16px;
}}
.nmr-mast-row {{ display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; gap:6px; margin-bottom:10px; }}
.nmr-brand {{ font-family:{_FONT}; font-weight:800; letter-spacing:.22em; font-size:.8rem; color:#fff; }}
.nmr-brand .sq {{ color: var(--nmr-green); margin-right:6px; }}
.nmr-kicker {{ font-family:{_FONT}; color: var(--nmr-green); font-size:.66rem; font-weight:700; letter-spacing:.22em; }}
.nmr-title {{ font-family:{_FONT}; font-weight:800; font-size:2.05rem; line-height:1.12; letter-spacing:-.5px; color:#fff; margin:2px 0 10px; }}
.nmr-title .amber {{ color: var(--nmr-amber); }}
.nmr-desc {{ color: var(--nmr-mut); font-size:.84rem; line-height:1.55; max-width:760px; }}
.nmr-desc b, .nmr-desc strong {{ color: var(--nmr-amber); }}
.nmr-stance {{ display:flex; align-items:center; gap:0; flex-wrap:wrap; margin-top:14px; font-family:{_FONT}; }}
.nmr-stance-pill {{
  border:1px solid var(--nmr-green); color: var(--nmr-green);
  font-size:.7rem; font-weight:800; letter-spacing:.14em;
  padding:5px 11px; border-radius:2px; background:rgba(0,230,118,.06);
}}
.nmr-meta {{
  color: var(--nmr-mut); font-size:.7rem; font-weight:700; letter-spacing:.1em;
  padding:5px 11px; border:1px solid var(--nmr-line); border-left:none; border-radius:2px;
}}

.nmr-sec {{
  font-family:{_FONT}; color: var(--nmr-amber);
  font-weight:800; font-size:.86rem; letter-spacing:.08em;
  margin:26px 0 10px; padding-bottom:7px;
  border-bottom:1px dashed #242424;
}}
.nmr-sec .no {{ color: var(--nmr-amber); }}
.nmr-sec .dash {{ color:#4a4a4a; }}
.nmr-sec .en {{ color: var(--nmr-amber); opacity:.65; font-size:.74rem; letter-spacing:.16em; }}

.nmr-note {{
  background:#101010; border:1px solid var(--nmr-line);
  border-left:3px solid var(--nmr-amber); border-radius:2px;
  padding:12px 15px; margin:8px 0 12px;
  color:#c9c9c9; font-size:.84rem; line-height:1.6; font-family:{_FONT};
}}
.nmr-note.green {{ border-left-color: var(--nmr-green); }}
.nmr-note.red {{ border-left-color: var(--nmr-red); }}
.nmr-note b {{ color: var(--nmr-amber); }}

.nmr-badge {{
  display:inline-block; font-family:{_FONT}; font-weight:800; font-size:.68rem;
  letter-spacing:.1em; padding:3px 9px; border-radius:2px; vertical-align:middle;
}}
.nmr-badge.buy {{ background: var(--nmr-green); color:{NMR['green_d']}; }}
.nmr-badge.sell {{ background: var(--nmr-red); color:#1a0404; }}
.nmr-badge.hold {{ background: var(--nmr-amber); color:#1a1000; }}
.nmr-badge.ghost-green {{ background:rgba(0,230,118,.1); color:var(--nmr-green); border:1px solid rgba(0,230,118,.4); }}
.nmr-badge.ghost-red {{ background:rgba(255,77,79,.1); color:var(--nmr-red); border:1px solid rgba(255,77,79,.4); }}
.nmr-badge.ghost-amber {{ background:rgba(255,176,0,.1); color:var(--nmr-amber); border:1px solid rgba(255,176,0,.4); }}

.nmr-end {{
  text-align:center; font-family:{_FONT}; color:#3f3f3f;
  font-size:.7rem; font-weight:700; letter-spacing:.34em;
  border-top:1px solid var(--nmr-line); padding:14px 0 4px; margin-top:30px;
}}
</style>
""", unsafe_allow_html=True)


# ──────────────────────────────────────────────────────────────────────
# 2. Plotly 전역 다크 템플릿
# ──────────────────────────────────────────────────────────────────────
def set_plotly_nomura():
    """모든 plotly 차트의 기본 템플릿을 리서치 다크 톤으로 교체.
    개별 차트가 색을 직접 지정한 경우는 그대로 존중됩니다."""
    try:
        import plotly.io as pio
        import plotly.graph_objects as go
    except Exception:
        return
    if "nomura_dark" in pio.templates:
        pio.templates.default = "nomura_dark"
        return
    tpl = go.layout.Template()
    tpl.layout = go.Layout(
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=dict(family="JetBrains Mono, Noto Sans KR, monospace",
                  color="#C9C9C9", size=12),
        title=dict(font=dict(color="#EDEDED", size=15)),
        colorway=[NMR["green"], NMR["amber"], NMR["blue"], NMR["up"],
                  NMR["purple"], NMR["teal"], NMR["pink"], "#A3E635"],
        xaxis=dict(gridcolor="#1D1D1D", zerolinecolor="#2A2A2A",
                   linecolor="#2A2A2A", tickcolor="#2A2A2A"),
        yaxis=dict(gridcolor="#1D1D1D", zerolinecolor="#2A2A2A",
                   linecolor="#2A2A2A", tickcolor="#2A2A2A"),
        legend=dict(bgcolor="rgba(0,0,0,0)", bordercolor="#1F1F1F",
                    font=dict(color="#A8ADB4")),
        hoverlabel=dict(bgcolor="#141414", bordercolor="#2A2A2A",
                        font=dict(family="JetBrains Mono, Noto Sans KR, monospace",
                                  color="#E8E8E8")),
        margin=dict(t=46, r=18, b=40, l=52),
    )
    pio.templates["nomura_dark"] = tpl
    pio.templates.default = "nomura_dark"


# ──────────────────────────────────────────────────────────────────────
# 3. 리포트 컴포넌트 헬퍼
# ──────────────────────────────────────────────────────────────────────
def nmr_topbar(left="JAEMINI GLOBAL TERMINAL", right="", live=True):
    """이미지 최상단의 얇은 티커 바."""
    live_html = '<span class="live">● LIVE</span>' if live else ""
    st.markdown(
        f'<div class="nmr-topbar"><span class="l">{left}</span>'
        f'<span class="r">{right}{live_html}</span></div>',
        unsafe_allow_html=True,
    )


def nmr_masthead(brand="JAEMINI PRO", kicker="LIVE EQUITY TERMINAL",
                 title_top="", title_accent="", desc="",
                 stance=None, metas=None):
    """리포트 머리(브랜드 → 대제목 2줄 → 설명 → STANCE 라인)."""
    metas = metas or []
    stance_html = ""
    if stance or metas:
        pill = f'<span class="nmr-stance-pill">{stance}</span>' if stance else ""
        meta = "".join(f'<span class="nmr-meta">{m}</span>' for m in metas)
        stance_html = f'<div class="nmr-stance">{pill}{meta}</div>'
    accent_html = f'<br><span class="amber">{title_accent}</span>' if title_accent else ""
    st.markdown(f"""
<div class="nmr-mast">
  <div class="nmr-mast-row">
    <span class="nmr-brand"><span class="sq">■</span>{brand}</span>
    <span class="nmr-kicker">● {kicker}</span>
  </div>
  <div class="nmr-title">{title_top}{accent_html}</div>
  <div class="nmr-desc">{desc}</div>
  {stance_html}
</div>""", unsafe_allow_html=True)


def nmr_section(num: str, kr: str, en: str = ""):
    """섹션 헤더: —[01]핵심 결론 / EXECUTIVE SUMMARY"""
    en_html = f' <span class="en">/ {en}</span>' if en else ""
    st.markdown(
        f'<div class="nmr-sec"><span class="dash">—</span>'
        f'<span class="no">[{num}]</span>{kr}{en_html}</div>',
        unsafe_allow_html=True,
    )


def nmr_note(html: str, tone: str = "amber"):
    """좌측 보더 인용 박스(이미지의 해석/체크포인트 박스)."""
    cls = {"amber": "", "green": " green", "red": " red"}.get(tone, "")
    st.markdown(f'<div class="nmr-note{cls}">{html}</div>', unsafe_allow_html=True)


def nmr_badge(text: str, tone: str = "buy") -> str:
    """인라인 배지 HTML 반환(BUY/SELL/HOLD/ghost-*). st.markdown에 끼워 사용."""
    return f'<span class="nmr-badge {tone}">{text}</span>'


def nmr_end():
    """리포트 푸터: — END OF REPORT —"""
    st.markdown('<div class="nmr-end">—&nbsp;&nbsp;E N D&nbsp;&nbsp;O F&nbsp;&nbsp;R E P O R T&nbsp;&nbsp;—</div>',
                unsafe_allow_html=True)
