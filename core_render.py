# -*- coding: utf-8 -*-
"""
Streamlit 렌더  (core_render.py)
=====================================================================
화면을 그리는 함수들. 가장 위 계층이라 아래 계층을 자유롭게 쓴다.

계층 순서: constants → utils → data → ai → scoring → render
위 방향으로만 의존한다(순환 없음). core.py 가 전부를 합쳐 다시 내보낸다.
"""
from core_constants import *
from core_utils import *
from core_data import *
from core_ai import *
from core_scoring import *



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
        if v > 0: return 'color:#dc2626;font-weight:700;'   # 빨강=상승(한국식)
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
        except Exception as _dg_e:
            _diag_note("style_volume_table", _dg_e)
            pass
    sty = sty.set_properties(**{'font-size': '14px', 'text-align': 'center'})
    sty = sty.set_properties(subset=['종목명'], **{'text-align': 'left', 'font-weight': '600'})
    return sty, rate_name


def style_us_volume_table(df, kind="surge"):
    if df is None or df.empty:
        return None
    def color_updown(v):
        if pd.isna(v): return ''
        if v > 0: return 'color:#dc2626;font-weight:700;'
        if v < 0: return 'color:#2e86de;font-weight:700;'
        return 'color:gray;'
    sty = df.style.format({"현재가": "${:,.2f}", "등락률": "{:+.2f}%", "거래량 배율": "{:.1f}×"})
    try:
        sty = sty.map(color_updown, subset=["등락률"])
    except Exception as _dg_e:
        _diag_note("style_us_volume_table", _dg_e)
        pass
    bar_color = '#ffd8a8' if kind == "surge" else '#a5d8ff'
    try:
        sty = sty.bar(subset=["거래량 배율"], color=bar_color, vmin=0)
    except Exception as _dg_e:
        _diag_note("style_us_volume_table", _dg_e)
        pass
    sty = sty.set_properties(**{'font-size': '14px', 'text-align': 'center'})
    try:
        sty = sty.set_properties(subset=['종목'], **{'text-align': 'left', 'font-weight': '600'})
    except Exception as _dg_e:
        _diag_note("style_us_volume_table", _dg_e)
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
        if v > 0: return 'color:#dc2626;font-weight:700;'
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
        if v > 0.05: return 'color:#dc2626;font-weight:700;'
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
        except Exception as _dg_e:
            _diag_note("style_report_table", _dg_e)
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
        if v > 0: return 'color:#dc2626;font-weight:700;'
        if v < 0: return 'color:#2e86de;font-weight:700;'
        return 'color:gray;'

    fmt = {}
    if '현재가' in out.columns: fmt['현재가'] = lambda x: f"${x:,.2f}" if pd.notna(x) and x > 0 else "-"
    if '등락률' in out.columns: fmt['등락률'] = lambda x: f"{x:+.2f}%" if pd.notna(x) else "-"
    sty = out.style.format(fmt)
    if '등락률' in out.columns:
        sty = sty.map(color_updown, subset=['등락률'])
        try: sty = sty.bar(subset=['등락률'], color=['#a5d8ff', '#ffd8a8'], align='zero')
        except Exception as _dg_e: _diag_note("style_sector_etf_table", _dg_e); pass
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
            return 'color:#dc2626;font-weight:700;'
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
    except Exception as _dg_e:
        _diag_note("render_main_index_panel", _dg_e)
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


def render_market_regime_banner():
    """홈/경보 화면 상단에 시장 국면 신호등 배너를 그립니다."""
    try:
        reg = get_market_regime()
    except Exception as _dg_e:
        _diag_note("render_market_regime_banner", _dg_e)
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
    # [속도개선] 관심종목을 하나씩 순차 조회하던 것을 병렬로 바꿨다.
    #   analyze_technical_pattern 은 종목당 시세·수급·펀더멘털을 모두 받아와 수 초가 걸려,
    #   10종목이면 홈 화면 마지막에서 30초 넘게 멈춰 있었다.
    #   ex.map 은 입력 순서를 유지하므로 기존 정렬 동작은 그대로다.
    def _wl_one(item):
        try:
            return item, analyze_technical_pattern(item["종목명"], item["티커"])
        except Exception as e:
            _diag_note("render_watchlist_signals", e, detail=str(item.get("종목명", "")))
            return item, None

    try:
        with concurrent.futures.ThreadPoolExecutor(max_workers=5) as _ex:
            _pairs = list(_ex.map(_wl_one, wl))
    except Exception as e:
        _diag_note("render_watchlist_signals", e)
        _pairs = [(it, None) for it in wl]

    alerts = []
    for item, res in _pairs:
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

def render_multi_theme_dataframe(df: pd.DataFrame, api_key: str):
    st.subheader("🔍 종목별 디테일 업종/테마 분석")
    st.caption("AI가 각 기업의 세부 밸류체인을 분석하여 속해있는 모든 업종과 테마를 찾아냅니다.")
    
    display_df = df.copy()
    
    if "업종/테마" not in display_df.columns:
        progress_text = "AI가 종목별 세부 업종/테마를 스캐닝 중입니다..."
        progress_bar = st.progress(0, text=progress_text)
        
        # [속도개선] 행마다 AI를 순차 호출하고 0.5초씩 쉬던 것을 병렬 호출로 교체.
        #   20행이면 대기만 10초 + 순차 호출 시간이 더해져 1분을 넘기기도 했다.
        #   get_granular_themes 는 24시간 캐시라 같은 종목은 다시 호출되지 않는다.
        #   워커를 4개로 묶은 건 Gemini 무료 등급의 분당 요청 한도를 넘기지 않기 위해서다.
        # [버그수정] 진행률을 DataFrame 인덱스(i)로 계산해, 인덱스가 행 개수보다 크면
        #   100을 넘겨 st.progress 가 예외를 던졌다. 완료 개수를 세는 방식으로 바꿨다.
        _names = display_df['종목명'].astype(str).tolist()
        total_rows = max(1, len(_names))
        theme_lists = [[] for _ in _names]
        _done = 0
        try:
            with concurrent.futures.ThreadPoolExecutor(max_workers=4) as _ex:
                _futs = {_ex.submit(get_granular_themes, n, api_key): i for i, n in enumerate(_names)}
                for _fut in concurrent.futures.as_completed(_futs):
                    _i = _futs[_fut]
                    try:
                        theme_lists[_i] = _fut.result()
                    except Exception as _dg_e:
                        _diag_note("render_multi_theme_dataframe", _dg_e, detail=_names[_i])
                    _done += 1
                    progress_bar.progress(min(100, int(_done / total_rows * 100)),
                                          text=f"{progress_text} ({_done}/{len(_names)})")
        except Exception as _dg_e:
            _diag_note("render_multi_theme_dataframe", _dg_e)

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
        except Exception as _dg_e:
            _diag_note("draw_stock_card", _dg_e)
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
            except Exception as _dg_e: _diag_note("is_float", _dg_e); return False
            
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
            except Exception as _dg_e:
                _diag_note("draw_stock_card", _dg_e)
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
        except Exception as _dg_e:
            _diag_note("_gap", _dg_e)
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
                except Exception as _dg_e: _diag_note("display_sorted_results", _dg_e); pass
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
        # [v7.2] 사이드바 전역 대신 세션에서 키를 읽는다 (모듈 분리 후에도 동작)
        api_key_input = st.session_state.get("_api_key", "")
        try:
            macro_data = get_macro_indicators()
        except Exception as _dg_e:
            _diag_note("_quant_assistant_body", _dg_e)
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
                    except Exception as _dg_e:
                        _diag_note("_resolve_kr_stock", _dg_e)
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
                    except Exception as _dg_e:
                        _diag_note("_fmt", _dg_e)
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


def render_score_why(why, horizon=None, total=None):
    """explain_score 결과를 접이식으로 표시. 값이 없으면 아무것도 그리지 않는다."""
    if not why:
        return
    head = "이 점수의 근거"
    if horizon and total is not None:
        head = f"이 점수의 근거 — {horizon} {total}점"
    with st.expander(f"❓ {head}", expanded=False):
        for label, pts in why:
            color = "#b3261e" if pts > 0 else "#1a4fa0"   # 국내 관행: 빨강=상승 요인
            sign = "+" if pts > 0 else ""
            st.markdown(
                f"<div style='display:flex;justify-content:space-between;padding:3px 0;"
                f"border-bottom:1px solid #eef1f5;'><span>{label}</span>"
                f"<b style='color:{color};font-variant-numeric:tabular-nums;'>{sign}{pts}</b></div>",
                unsafe_allow_html=True)
        st.caption("각 항목은 '그 요인이 없었다면 몇 점이었을까'를 되짚어 계산한 **근사치**입니다. "
                   "점수는 단계마다 0~100으로 잘리기 때문에 합계가 총점과 정확히 같지는 않습니다. "
                   "가중치는 `scoring_weights.py` 에 있고, **🧪 전략 백테스트**에서 검증할 수 있습니다.")

# `from core_render import *` 로 넘어갈 이름 (언더스코어 포함, 자동 생성)
_EXPORTED = [
    "_expert_chat_body",
    "_expert_chat_dialog",
    "_flow_bar_html",
    "_index_card_html",
    "_leader_callout_html",
    "_leader_fmt_big",
    "_leader_fmt_mom",
    "_leader_fmt_price",
    "_leaders_table_html",
    "_market_flows_html",
    "_open_expert_chat",
    "_open_popup",
    "_open_quant_assistant",
    "_open_vptm",
    "_popup_button",
    "_quant_assistant_body",
    "_quant_assistant_dialog",
    "_register_popup",
    "_render_flow_chips",
    "_render_handover",
    "_render_netbuy_list",
    "_run_popup_renderer",
    "_short_trend_figure",
    "_sparkline_svg",
    "_universal_popup",
    "_vptm_body",
    "_vptm_dialog",
    "display_sorted_results",
    "draw_stock_card",
    "nb_render_briefing",
    "nb_render_time_machine",
    "nb_render_volume_profile",
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
    "render_score_why",
    "render_sentiment_strip",
    "render_single_stock_themes",
    "render_theme_leaders",
    "render_trending_sectors",
    "render_watchlist_signals",
    "render_week_catalysts",
    "show_beginner_guide",
    "show_trading_guidelines",
    "style_ipo_table",
    "style_report_table",
    "style_sector_etf_table",
    "style_us_gainers_table",
    "style_us_volume_table",
    "style_volume_table",
    "style_warning_table",
]

__all__ = [_n for _n in _EXPORTED if _n in globals()]
