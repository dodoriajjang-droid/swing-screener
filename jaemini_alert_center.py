# -*- coding: utf-8 -*-
"""
🚨 Jaemini PRO 통합 경보 센터 (Alert Center)  v1.0
====================================================
기존 app__4_.py 의 함수들을 '그대로 재사용'해서, 매매에 바로 참고할 수 있는
3트랙 경보 시스템을 하나의 페이지로 묶는 모듈입니다.

  1) 📰 뉴스·정세 경보   : 실시간 뉴스 헤드라인을 악재/호재 키워드로 자동 분류 + 폴리마켓 정세
  2) 📉 차트 패턴 경보   : 관심종목을 analyze_technical_pattern 으로 돌려 룰 기반 경보 생성
  3) 🗓️ 시기·일정 경보   : FOMC/CPI/만기일 D-day + 직접 등록한 종목 '재료(호재) 소멸' 경보

이 파일은 app 의 함수를 직접 import 하지 않습니다.
대신 render_alert_center(deps) 로 필요한 함수만 '주입'받아 결합도를 낮춥니다.
(연동 방법은 파일 하단 USAGE 주석 참고)
"""

import os
import json
from datetime import datetime, date, timedelta

import streamlit as st
import pandas as pd

try:
    import numpy as np
except Exception:  # numpy 없어도 동작은 하도록
    np = None


# ==========================================================================
# 0. 키워드 사전  (뉴스 헤드라인 자동 분류용)
#    - strong : 단독으로도 강한 신호 (가중치 2)
#    - normal : 일반 신호 (가중치 1)
#    한국 증시 뉴스 표현에 맞춰 구성. 필요하면 자유롭게 추가/삭제하세요.
# ==========================================================================
DANGER_STRONG = [
    "폭락", "급락", "어닝쇼크", "쇼크", "횡령", "배임", "상장폐지", "거래정지",
    "부도", "파산", "회생절차", "디폴트", "감자", "분식", "리콜", "결함",
    "유상증자", "대규모 손실", "사기", "구속", "압수수색", "전쟁", "디폴트",
]
DANGER_NORMAL = [
    "하락", "약세", "적자", "손실", "부진", "둔화", "침체", "감소", "위축",
    "소송", "피소", "제재", "규제", "과징금", "벌금", "조사", "경고", "주의",
    "블록딜", "매각", "구조조정", "감원", "철수", "지연", "차질", "악재",
    "하향", "목표가 하향", "투자의견 하향", "매도", "공매도", "고평가", "거품",
    "관세", "분쟁", "긴장", "제동", "반발", "리스크", "우려", "불안", "충격",
]
GOOD_STRONG = [
    "폭등", "급등", "어닝서프라이즈", "서프라이즈", "사상최대", "역대최대", "역대급",
    "신고가", "최고가", "흑자전환", "대규모 수주", "초대형 계약", "FDA 승인",
    "신약 승인", "인수", "합병", "M&A", "독점 공급",
]
GOOD_NORMAL = [
    "상승", "강세", "호실적", "호재", "수혜", "수주", "계약", "공급", "납품",
    "흑자", "개선", "확대", "성장", "증가", "회복", "반등", "돌파", "돌파구",
    "승인", "허가", "신제품", "출시", "수출", "체결", "협력", "파트너십",
    "자사주", "배당", "증액", "상향", "목표가 상향", "투자의견 상향", "매수",
    "최대 실적", "기대감", "모멘텀", "낙수효과",
]


# ==========================================================================
# 1. 종목 '재료(호재) 소멸' 트래커 영구 저장소
#    watchlist.json 과 동일한 방식으로 catalysts.json 에 저장합니다.
#    레코드: {"종목명","티커","재료","예정일(YYYY-MM-DD)","메모"}
# ==========================================================================
CATALYST_FILE = "catalysts.json"


def load_catalysts():
    if os.path.exists(CATALYST_FILE):
        try:
            with open(CATALYST_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                return data if isinstance(data, list) else []
        except Exception:
            return []
    return []


def save_catalysts(items):
    try:
        with open(CATALYST_FILE, "w", encoding="utf-8") as f:
            json.dump(items, f, ensure_ascii=False, indent=2)
    except Exception as e:
        st.error(f"재료 일정 저장 실패: {e}")


# ==========================================================================
# 2. 룰 엔진
# ==========================================================================
def _count_hits(title, words):
    return [w for w in words if w in title]


def classify_news_headline(title: str) -> dict:
    """헤드라인 1건을 악재/호재/중립으로 분류.
    반환: {"level": danger|good|neutral, "score": int, "icon", "tag", "hits":[...]}"""
    title = str(title or "")
    d_strong = _count_hits(title, DANGER_STRONG)
    d_normal = _count_hits(title, DANGER_NORMAL)
    g_strong = _count_hits(title, GOOD_STRONG)
    g_normal = _count_hits(title, GOOD_NORMAL)

    d_score = len(d_strong) * 2 + len(d_normal)
    g_score = len(g_strong) * 2 + len(g_normal)

    if d_score == 0 and g_score == 0:
        return {"level": "neutral", "score": 0, "icon": "⚪", "tag": "중립", "hits": []}

    # 위험 우선(동점이면 악재로): 리스크 관리가 먼저
    if d_score >= g_score:
        strong = len(d_strong) > 0
        return {
            "level": "danger",
            "score": d_score,
            "icon": "🔴" if strong or d_score >= 3 else "🟠",
            "tag": "강한 악재" if strong else "악재 신호",
            "hits": d_strong + d_normal,
        }
    else:
        strong = len(g_strong) > 0
        return {
            "level": "good",
            "score": g_score,
            "icon": "🟢" if strong or g_score >= 3 else "🟡",
            "tag": "강한 호재" if strong else "호재 신호",
            "hits": g_strong + g_normal,
        }


def _safe_float(x):
    try:
        if x is None:
            return None
        if np is not None and isinstance(x, float) and np.isnan(x):
            return None
        v = float(x)
        if v != v:  # NaN
            return None
        return v
    except Exception:
        return None


def evaluate_chart_alerts(res: dict) -> list:
    """analyze_technical_pattern() 결과 dict 1개 → 차트 경보 리스트.
    각 경보: {"dir": bear|bull, "level": 위험|주의|관심|호재, "icon", "title", "detail"}"""
    alerts = []
    if not res:
        return alerts

    align = str(res.get("배열상태", ""))
    status = str(res.get("상태", ""))
    vol = str(res.get("거래량 급증", ""))
    weekly = str(res.get("주봉추세", ""))
    rsi = _safe_float(res.get("RSI"))
    price = _safe_float(res.get("현재가"))
    guide = _safe_float(res.get("진입가_가이드"))  # 20일선
    gap = None
    if price and guide and guide > 0:
        gap = (price - guide) / guide * 100.0  # 20일선 대비 이격(%)

    # ---------- 🔴 하락(매도/관망) 경보 ----------
    if "역배열" in align:
        alerts.append({"dir": "bear", "level": "위험", "icon": "🔴",
                       "title": "역배열 하락추세",
                       "detail": "5<20<60일선 — 추세적 하락. 신규 진입보단 관망/비중축소 구간."})
    if "이탈" in status:
        alerts.append({"dir": "bear", "level": "위험", "icon": "🔴",
                       "title": "20일선 이탈",
                       "detail": "단기 생명선(20MA) 아래로 이탈 — 지지 회복 전까지 보수적 대응."})
    if rsi is not None and rsi >= 75:
        alerts.append({"dir": "bear", "level": "주의", "icon": "🟠",
                       "title": f"RSI 과열 ({rsi:.0f})",
                       "detail": "단기 과매수 구간(≥75) — 분할 익절/추격매수 자제 신호."})
    if "이격 과다" in status:
        msg = "20일선과 괴리가 큼 — 눌림목 대기 권장."
        if gap is not None:
            msg = f"20일선 대비 +{gap:.1f}% 이격 — 단기 과열, 눌림목 대기 권장."
        alerts.append({"dir": "bear", "level": "주의", "icon": "🟠",
                       "title": "이격 과다(고점 추격 주의)", "detail": msg})

    # ---------- 🟢 상승(매수/관심) 경보 ----------
    if "정배열" in align:
        alerts.append({"dir": "bull", "level": "호재", "icon": "🟢",
                       "title": "완벽 정배열",
                       "detail": "5>20>60일선 — 상승추세 양호. 눌림목마다 분할매수 유효 구간."})
    if "골든크로스" in align:
        alerts.append({"dir": "bull", "level": "관심", "icon": "🟢",
                       "title": "골든크로스 발생",
                       "detail": "5일선이 20일선 상향 돌파 — 단기 추세 전환 초입 가능성."})
    if rsi is not None and rsi <= 30:
        alerts.append({"dir": "bull", "level": "관심", "icon": "🔵",
                       "title": f"RSI 과매도 ({rsi:.0f})",
                       "detail": "낙폭과대(≤30) — 기술적 반등 후보. 추세 확인 후 분할 접근."})
    if "타점 근접" in status:
        alerts.append({"dir": "bull", "level": "관심", "icon": "🟢",
                       "title": "매수 타점 근접",
                       "detail": "20일선 ±3% 지지권 — 분할매수 1차 타점."})
    if "거래량 터짐" in vol:
        alerts.append({"dir": "bull", "level": "관심", "icon": "🔥",
                       "title": "거래량 급증",
                       "detail": "최근 평균 대비 거래량 폭증 — 수급/세력 유입 가능성(방향 확인 필요)."})

    return alerts


def days_until(date_str) -> int:
    """'YYYY-MM-DD' → 오늘로부터 남은 일수(D-N). 과거면 음수. 파싱 실패 시 None."""
    try:
        d = date.fromisoformat(str(date_str).strip())
        return (d - date.today()).days
    except Exception:
        return None


def evaluate_catalyst(item: dict, chart_gap: float = None) -> dict:
    """등록된 재료 1건 → '호재 소멸' 경보 판정.
    chart_gap: (현재가-20일선)/20일선*100. 이미 많이 오른 종목이면 소멸 위험 가중."""
    dleft = days_until(item.get("예정일"))
    base = {"dleft": dleft}

    if dleft is None:
        base.update({"level": "info", "icon": "❔", "tag": "날짜 확인 필요",
                     "msg": "예정일 형식이 올바르지 않습니다 (YYYY-MM-DD)."})
        return base

    # 선반영(이미 많이 오름) 여부
    pre_priced = chart_gap is not None and chart_gap >= 8.0

    if dleft < 0:
        base.update({"level": "danger", "icon": "⚫", "tag": "재료 소멸(노출 완료)",
                     "msg": f"예정일 {abs(dleft)}일 경과 — 재료 노출 완료. "
                            "'소문에 사서 뉴스에 판다' 구간. 모멘텀 둔화/차익실현 점검."})
    elif dleft == 0:
        base.update({"level": "danger", "icon": "🔴", "tag": "D-DAY (오늘)",
                     "msg": "오늘이 재료 발생일 — 노출 당일은 변동성 극대. "
                            + ("이미 선반영 폭이 커 '호재 소멸' 급락 위험 높음." if pre_priced
                               else "결과 확인 후 대응 권장.")})
    elif dleft <= 3:
        msg = f"D-{dleft} — 재료 노출 임박. 선반영分 차익실현 매물 주의 구간."
        if pre_priced:
            msg += " ⚠️ 20일선 대비 이격이 커(선반영) 고점 차익실현 위험이 특히 높음."
        base.update({"level": "warn", "icon": "🟠", "tag": "노출 임박(D-3 이내)", "msg": msg})
    elif dleft <= 10:
        base.update({"level": "watch", "icon": "🟡", "tag": "관심(D-10 이내)",
                     "msg": f"D-{dleft} — 재료 기대 구간. 기대감 선반영 시작 가능. 분할 접근 검토."})
    else:
        base.update({"level": "good", "icon": "🟢", "tag": "대기",
                     "msg": f"D-{dleft} — 아직 여유. 재료 대기 중."})
    return base


# ------- 매크로/파생 일정 임박 스캔 -------
def _classify_macro_label(label: str) -> dict:
    """경제 이벤트 라벨 → 변동성 성격 분류."""
    t = str(label)
    if any(k in t for k in ["FOMC", "금통위", "ECB", "BOJ", "금리"]):
        return {"icon": "🔴", "kind": "금리·통화정책", "note": "양방향 변동성 큼(매매 전 포지션 점검)"}
    if any(k in t for k in ["CPI", "PCE", "물가"]):
        return {"icon": "🟠", "kind": "물가지표", "note": "서프라이즈 시 지수 급변"}
    if any(k in t for k in ["고용", "PMI", "소매판매", "수출입"]):
        return {"icon": "🟡", "kind": "경기지표", "note": "추세/심리 확인용"}
    if any(k in t for k in ["만기", "네마녀"]):
        return {"icon": "🟣", "kind": "파생 수급", "note": "만기일 수급 변동성·핀닝 주의"}
    return {"icon": "⚪", "kind": "기타 일정", "note": ""}


def _nth_weekday(year, month, weekday, n):
    """해당 월 n번째 특정 요일(weekday: 월=0..일=6)의 날짜(date) 반환."""
    d = date(year, month, 1)
    offset = (weekday - d.weekday()) % 7
    day = 1 + offset + (n - 1) * 7
    try:
        return date(year, month, day)
    except Exception:
        return None


def scan_upcoming_events(get_economic_events, within_days=10) -> list:
    """오늘~within_days 안의 매크로 + 파생만기 일정 리스트(가까운 순)."""
    out = []
    today = date.today()

    months = []
    y, m = today.year, today.month
    for _ in range(3):  # 이번달 + 다음 2개월
        months.append((y, m))
        m += 1
        if m == 13:
            m = 1
            y += 1

    seen = set()
    for (yy, mm) in months:
        # 1) 경제지표 (앱의 get_economic_events 재사용)
        if callable(get_economic_events):
            try:
                ev = get_economic_events(yy, mm) or {}
            except Exception:
                ev = {}
            for day_num, items in ev.items():
                try:
                    edate = date(yy, mm, int(day_num))
                except Exception:
                    continue
                dleft = (edate - today).days
                if 0 <= dleft <= within_days:
                    for (label, _cls) in items:
                        key = (edate.isoformat(), label)
                        if key in seen:
                            continue
                        seen.add(key)
                        meta = _classify_macro_label(label)
                        out.append({"date": edate, "dleft": dleft, "label": label, **meta})

        # 2) 파생 옵션만기 (규칙 기반: 미 3째 금요일, 한 2째 목요일)
        us_opex = _nth_weekday(yy, mm, 4, 3)   # 금요일=4
        kr_opex = _nth_weekday(yy, mm, 3, 2)   # 목요일=3
        for edate, label in [(us_opex, "🇺🇸 옵션만기(변동성)"), (kr_opex, "🇰🇷 옵션만기(수급)")]:
            if not edate:
                continue
            dleft = (edate - today).days
            if 0 <= dleft <= within_days:
                key = (edate.isoformat(), label)
                if key in seen:
                    continue
                seen.add(key)
                meta = _classify_macro_label(label)
                out.append({"date": edate, "dleft": dleft, "label": label, **meta})

    out.sort(key=lambda x: (x["dleft"], x["label"]))
    return out


# ==========================================================================
# 3. 메인 렌더러
# ==========================================================================
def render_alert_center(deps: dict):
    """
    deps 로 주입받는 키 (없으면 해당 기능만 비활성화):
      - analyze_technical_pattern(name, ticker)   [차트 경보용]
      - get_latest_naver_news()                    [뉴스 경보용]
      - get_economic_events(year, month)           [일정 경보용]
      - fetch_polymarket_markets(search, limit)     [정세 게이지용·선택]
      - get_krx_stocks()                            [뉴스→종목 매핑·선택]
      - ask_gemini(prompt, api_key)                 [AI 요약·선택]
      - api_key (str)                               [AI 요약용·선택]
    """
    analyze_technical_pattern = deps.get("analyze_technical_pattern")
    get_latest_naver_news = deps.get("get_latest_naver_news")
    get_economic_events = deps.get("get_economic_events")
    fetch_polymarket_markets = deps.get("fetch_polymarket_markets")
    get_krx_stocks = deps.get("get_krx_stocks")
    ask_gemini = deps.get("ask_gemini")
    api_key = deps.get("api_key", "")

    st.title("🚨 통합 경보 센터")
    st.caption("뉴스·정세 / 차트 패턴 / 시기·일정(호재 소멸)을 한 화면에서 감시하는 매매 경보기입니다. "
               "각 신호는 '참고용'이며 매매 판단은 본인 책임입니다.")

    # ---------------- 상단 종합 요약 배너 ----------------
    summary_box = st.container()

    tabs = st.tabs([
        "📰 뉴스·정세 경보",
        "📉 차트 패턴 경보",
        "🗓️ 시기·일정 경보 (호재 소멸)",
    ])

    # 요약 배너에 채워 넣을 카운터
    cnt = {"news_bad": 0, "news_good": 0, "chart_bear": 0, "chart_bull": 0, "evt_soon": 0, "cat_risk": 0}

    # =====================================================================
    # TAB 1 — 뉴스·정세 경보
    # =====================================================================
    with tabs[0]:
        st.markdown("#### 📰 실시간 뉴스 악재/호재 자동 분류")
        st.caption("네이버 금융 실시간 속보를 키워드로 분석해 🔴악재 / 🟢호재 / ⚪중립으로 자동 태깅합니다.")

        cset = st.columns([1.2, 1, 1, 2])
        only_signal = cset[0].toggle("신호만 보기(중립 숨김)", value=True, key="ac_news_only_sig")
        max_news = cset[1].selectbox("표시 건수", [30, 50, 80], index=1, key="ac_news_max")
        if cset[2].button("🔄 뉴스 새로고침", key="ac_news_reload"):
            try:
                if hasattr(get_latest_naver_news, "clear"):
                    get_latest_naver_news.clear()
            except Exception:
                pass
            st.rerun()

        news_items = []
        if callable(get_latest_naver_news):
            with st.spinner("뉴스를 불러와 분석 중..."):
                try:
                    news_items = get_latest_naver_news() or []
                except Exception as e:
                    st.error(f"뉴스 수집 실패: {e}")
        else:
            st.info("뉴스 수집 함수가 연결되지 않았습니다. (get_latest_naver_news)")

        # 종목명→코드 매핑(선택, 상위 항목만)
        name_map = {}
        sorted_names = []
        if callable(get_krx_stocks):
            try:
                kdf = get_krx_stocks()
                ok = kdf["Name"].astype(str).str.len() > 1
                name_map = dict(zip(kdf.loc[ok, "Name"], kdf.loc[ok, "Code"]))
                sorted_names = sorted(name_map.keys(), key=len, reverse=True)
            except Exception:
                name_map = {}

        # 분류
        classified = []
        for n in news_items[: int(max_news)]:
            title = n.get("title", "")
            c = classify_news_headline(title)
            matched_stock = None
            if c["level"] != "neutral" and sorted_names:
                for nm in sorted_names:
                    if nm in title and len(nm) >= 2:
                        matched_stock = (nm, name_map[nm])
                        break
            classified.append((n, c, matched_stock))

        bad = [x for x in classified if x[1]["level"] == "danger"]
        good = [x for x in classified if x[1]["level"] == "good"]
        cnt["news_bad"], cnt["news_good"] = len(bad), len(good)

        # 시장 분위기 게이지
        m1, m2, m3 = st.columns(3)
        m1.metric("🔴 악재 신호", f"{len(bad)} 건")
        m2.metric("🟢 호재 신호", f"{len(good)} 건")
        total_sig = len(bad) + len(good)
        if total_sig > 0:
            mood = good and len(good) / total_sig or 0
            mood_label = "🟢 호재 우위" if mood > 0.6 else ("🔴 악재 우위" if mood < 0.4 else "⚪ 혼조")
            m3.metric("뉴스 분위기", mood_label, f"호재 {len(good)} : 악재 {len(bad)}")
            st.progress(min(max(mood, 0.0), 1.0),
                        text=f"뉴스 호재 비중 {mood*100:.0f}%")
        else:
            m3.metric("뉴스 분위기", "데이터 없음")

        st.divider()

        show_list = classified if not only_signal else [x for x in classified if x[1]["level"] != "neutral"]
        if not show_list:
            st.success("현재 분류된 강한 악재/호재 신호가 없습니다. (시장 조용)")
        for idx, (n, c, ms) in enumerate(show_list):
            with st.container(border=True):
                cc = st.columns([0.6, 1, 6, 1.2])
                cc[0].markdown(f"### {c['icon']}")
                cc[1].markdown(f"**🕒 {n.get('time','')}**\n\n`{c['tag']}`")
                hit_str = (" · 키워드: " + ", ".join(c["hits"][:4])) if c["hits"] else ""
                stock_str = f"  〔📌 {ms[0]}〕" if ms else ""
                cc[2].markdown(f"{n.get('title','')}{stock_str}")
                if hit_str:
                    cc[2].caption(hit_str.strip(" ·"))
                if n.get("link"):
                    cc[3].link_button("원문🔗", n["link"], use_container_width=True)

        # AI 종합 + 폴리마켓 정세
        st.divider()
        st.markdown("#### 🌐 정세 게이지 (폴리마켓 매크로 확률)")
        if callable(fetch_polymarket_markets):
            with st.spinner("정세 데이터 로딩..."):
                try:
                    res = fetch_polymarket_markets(
                        search="fed rate cut recession war ceasefire tariff", limit=40)
                    poly = res.get("data", []) if isinstance(res, dict) else []
                except Exception:
                    poly = []
            if poly:
                poly = sorted(poly, key=lambda x: -(x.get("volume24hr") or 0))[:6]
                pcols = st.columns(min(3, len(poly)))
                for i, mkt in enumerate(poly):
                    with pcols[i % len(pcols)]:
                        prob = mkt.get("yes_prob")
                        q = (mkt.get("question") or "")[:60]
                        st.metric(q, f"{prob:.0f}%" if prob is not None else "다중")
                        if prob is not None:
                            st.progress(min(max(prob / 100, 0), 1.0))
            else:
                st.caption("정세 데이터를 불러오지 못했습니다. (네트워크/차단 가능)")
        else:
            st.caption("폴리마켓 함수가 연결되지 않았습니다. (fetch_polymarket_markets)")

        if callable(ask_gemini):
            if st.button("🤖 AI: 오늘 뉴스·정세 종합 위험도 브리핑", key="ac_news_ai",
                         type="primary", use_container_width=True):
                if not api_key:
                    st.error("사이드바에 API 키를 먼저 입력해주세요.")
                else:
                    bad_titles = "\n".join([f"- {x[0].get('title','')}" for x in bad[:15]]) or "- (없음)"
                    good_titles = "\n".join([f"- {x[0].get('title','')}" for x in good[:15]]) or "- (없음)"
                    prompt = (
                        "너는 한국 증시 리스크 매니저다. 아래는 실시간 뉴스 헤드라인을 키워드로 분류한 결과다.\n\n"
                        f"[악재 신호]\n{bad_titles}\n\n[호재 신호]\n{good_titles}\n\n"
                        "다음을 한국어로 간결히:\n"
                        "1. 오늘 시장 전반 위험도 (1~5단계)와 한 줄 근거\n"
                        "2. 주목할 악재 테마/종목 2가지와 영향\n"
                        "3. 수혜 가능 테마/종목 2가지\n"
                        "4. ⚠️ 키워드 분류의 한계(맥락 미반영 가능)도 한 줄 명시"
                    )
                    with st.spinner("AI가 뉴스 위험도를 평가 중..."):
                        st.info(ask_gemini(prompt, api_key))

    # =====================================================================
    # TAB 2 — 차트 패턴 경보
    # =====================================================================
    with tabs[1]:
        st.markdown("#### 📉 관심종목 차트 패턴 경보 스캐너")
        st.caption("관심종목(또는 직접 입력 종목)을 분석해 데드크로스·RSI 과열/과매도·정배열·거래량 급증 등을 "
                   "🔴하락 / 🟢상승 경보로 자동 변환합니다.")

        if not callable(analyze_technical_pattern):
            st.warning("차트 분석 함수가 연결되지 않았습니다. (analyze_technical_pattern)")
        else:
            watch = list(st.session_state.get("watchlist", []))
            cset = st.columns([2, 1])
            with cset[0]:
                manual = st.text_input(
                    "➕ 직접 종목 추가 (티커, 쉼표로 여러 개)",
                    key="ac_chart_manual",
                    placeholder="예: 005930, 000660, AAPL")
            with cset[1]:
                dir_filter = st.radio("필터", ["전체", "🔴 하락경보만", "🟢 상승경보만"],
                                      key="ac_chart_filter", horizontal=False)

            targets = []
            for w in watch:
                nm = w.get("종목명") or w.get("티커")
                tk = w.get("티커")
                if tk:
                    targets.append((nm, str(tk)))
            for tk in [t.strip() for t in (manual or "").split(",") if t.strip()]:
                if tk not in [t[1] for t in targets]:
                    targets.append((tk, tk))

            if not targets:
                st.info("관심종목이 없습니다. 위에 티커를 직접 입력하거나, 다른 메뉴에서 관심종목을 추가하세요.")
            else:
                bear_rows, bull_rows = [], []
                detail_cards = []
                prog = st.progress(0.0, text="차트 스캔 중...")
                for i, (nm, tk) in enumerate(targets):
                    try:
                        res = analyze_technical_pattern(nm, tk)
                    except Exception:
                        res = None
                    prog.progress((i + 1) / len(targets),
                                  text=f"차트 스캔 중... ({nm})")
                    if not res:
                        continue
                    alerts = evaluate_chart_alerts(res)
                    if not alerts:
                        continue
                    has_bear = any(a["dir"] == "bear" for a in alerts)
                    has_bull = any(a["dir"] == "bull" for a in alerts)
                    if has_bear:
                        cnt["chart_bear"] += 1
                    if has_bull:
                        cnt["chart_bull"] += 1
                    detail_cards.append((res, alerts))

                    rsi = _safe_float(res.get("RSI"))
                    base_row = {
                        "종목": res.get("종목명", nm),
                        "현재가": res.get("현재가"),
                        "RSI": round(rsi, 1) if rsi is not None else None,
                        "배열": str(res.get("배열상태", "")).split(" ｜ ")[0],
                        "신호": " / ".join(f"{a['icon']}{a['title']}" for a in alerts),
                    }
                    if has_bear:
                        bear_rows.append(base_row)
                    if has_bull:
                        bull_rows.append(base_row)
                prog.empty()

                b1, b2 = st.columns(2)
                b1.metric("🔴 하락경보 종목", f"{cnt['chart_bear']} 개")
                b2.metric("🟢 상승경보 종목", f"{cnt['chart_bull']} 개")
                st.divider()

                if dir_filter != "🟢 상승경보만":
                    st.markdown("##### 🔴 하락/주의 경보")
                    if bear_rows:
                        st.dataframe(pd.DataFrame(bear_rows), use_container_width=True, hide_index=True)
                    else:
                        st.success("하락 경보 종목이 없습니다.")
                if dir_filter != "🔴 하락경보만":
                    st.markdown("##### 🟢 상승/관심 경보")
                    if bull_rows:
                        st.dataframe(pd.DataFrame(bull_rows), use_container_width=True, hide_index=True)
                    else:
                        st.info("상승 경보 종목이 없습니다.")

                st.divider()
                st.markdown("##### 🔍 종목별 경보 상세")
                for res, alerts in detail_cards:
                    if dir_filter == "🔴 하락경보만":
                        alerts = [a for a in alerts if a["dir"] == "bear"]
                    elif dir_filter == "🟢 상승경보만":
                        alerts = [a for a in alerts if a["dir"] == "bull"]
                    if not alerts:
                        continue
                    with st.container(border=True):
                        head = st.columns([3, 1, 1])
                        head[0].markdown(f"**{res.get('종목명','')}** · {res.get('섹터','')}")
                        cur = res.get("현재가")
                        head[1].markdown(f"현재가\n\n**{cur:,.0f}**" if isinstance(cur, (int, float)) else "")
                        head[2].markdown(f"주봉\n\n{res.get('주봉추세','')}")
                        for a in alerts:
                            st.markdown(f"{a['icon']} **[{a['level']}] {a['title']}** — {a['detail']}")

                if callable(ask_gemini) and detail_cards:
                    if st.button("🤖 AI: 관심종목 경보 종합 액션플랜", key="ac_chart_ai",
                                 type="primary", use_container_width=True):
                        if not api_key:
                            st.error("사이드바에 API 키를 먼저 입력해주세요.")
                        else:
                            lines = []
                            for res, alerts in detail_cards:
                                sigs = "; ".join(f"{a['title']}" for a in alerts)
                                lines.append(f"- {res.get('종목명','')}: {sigs}")
                            block = "\n".join(lines)
                            prompt = (
                                "너는 단기 스윙 트레이더 코치다. 아래는 관심종목들의 차트 경보 신호다.\n\n"
                                f"{block}\n\n"
                                "각 종목에 대해 1줄로 (보유/관망/분할매수/익절 중 택1 + 근거) 액션을 제시하고, "
                                "마지막에 오늘의 우선순위 1~2종목을 골라줘. 과도한 단정은 피하고 확률적으로 서술."
                            )
                            with st.spinner("AI가 경보를 종합 중..."):
                                st.info(ask_gemini(prompt, api_key))

    # =====================================================================
    # TAB 3 — 시기·일정 경보 (호재 소멸)
    # =====================================================================
    with tabs[2]:
        st.markdown("#### 🗓️ 매크로·파생 일정 임박 경보")
        st.caption("FOMC·CPI·금통위·고용지표·옵션만기 등 변동성 이벤트가 며칠 남았는지 D-day로 알려줍니다.")

        within = st.slider("앞으로 며칠 이내 일정 표시", 3, 21, 10, key="ac_evt_within")
        evts = scan_upcoming_events(get_economic_events, within_days=within)
        cnt["evt_soon"] = sum(1 for e in evts if e["dleft"] <= 3)

        if not evts:
            st.success(f"앞으로 {within}일 이내 주요 변동성 일정이 없습니다.")
        else:
            rows = []
            for e in evts:
                dd = "D-DAY" if e["dleft"] == 0 else f"D-{e['dleft']}"
                rows.append({
                    "D-day": dd,
                    "날짜": e["date"].strftime("%m/%d (%a)"),
                    "": e["icon"],
                    "이벤트": e["label"],
                    "성격": e["kind"],
                    "유의": e["note"],
                })
            st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
            soon = [e for e in evts if e["dleft"] <= 3]
            if soon:
                names = ", ".join(f"{e['label']}(D-{e['dleft']})" for e in soon)
                st.warning(f"⚠️ 3일 이내 임박: {names} — 단기 변동성 확대 대비(레버리지/풀매수 자제).")

        st.divider()

        # ---------------- 종목 재료(호재) 소멸 트래커 ----------------
        st.markdown("#### 🎯 종목 재료(호재) '소멸' 트래커")
        st.caption("실적발표·수주기대·FDA승인·신제품공개 등 '재료 예정일'을 등록하면, "
                   "D-day가 다가올 때 **선반영分 차익실현·호재 소멸 급락** 위험을 경보합니다. "
                   "('소문에 사서 뉴스에 판다' 패턴 감시)")

        if "ac_catalysts" not in st.session_state:
            st.session_state.ac_catalysts = load_catalysts()
        catalysts = st.session_state.ac_catalysts

        with st.expander("➕ 재료 일정 등록 / 관리", expanded=not catalysts):
            f = st.columns([1.4, 1, 1.6, 1.2])
            in_name = f[0].text_input("종목명", key="ac_cat_name", placeholder="예: 삼성전자")
            in_tk = f[1].text_input("티커(선택)", key="ac_cat_tk", placeholder="005930")
            in_cat = f[2].text_input("재료 내용", key="ac_cat_what", placeholder="예: 3분기 실적발표")
            in_date = f[3].date_input("예정일", key="ac_cat_date")
            if st.button("등록", key="ac_cat_add", type="primary"):
                if in_name.strip() and in_date:
                    catalysts.append({
                        "종목명": in_name.strip(),
                        "티커": in_tk.strip(),
                        "재료": in_cat.strip() or "(미입력)",
                        "예정일": in_date.isoformat(),
                        "메모": "",
                    })
                    st.session_state.ac_catalysts = catalysts
                    save_catalysts(catalysts)
                    st.success(f"'{in_name.strip()}' 재료 일정 등록 완료")
                    st.rerun()
                else:
                    st.error("종목명과 예정일은 필수입니다.")

        if not catalysts:
            st.info("등록된 재료 일정이 없습니다. 위에서 추가해보세요. "
                    "(예: 종목 '에코프로', 재료 '수주 발표 기대', 예정일 선택)")
        else:
            # D-day 가까운 순 정렬
            order = sorted(range(len(catalysts)),
                           key=lambda i: (days_until(catalysts[i].get("예정일")) is None,
                                          days_until(catalysts[i].get("예정일")) if days_until(catalysts[i].get("예정일")) is not None else 9999))
            for i in order:
                item = catalysts[i]
                # 차트 이격(선반영) 보정값 계산 (티커 있고 함수 있으면)
                gap = None
                tk = str(item.get("티커", "")).strip()
                if tk and callable(analyze_technical_pattern):
                    try:
                        r = analyze_technical_pattern(item.get("종목명", tk), tk)
                        if r:
                            price = _safe_float(r.get("현재가"))
                            guide = _safe_float(r.get("진입가_가이드"))
                            if price and guide and guide > 0:
                                gap = (price - guide) / guide * 100.0
                    except Exception:
                        gap = None

                verdict = evaluate_catalyst(item, chart_gap=gap)
                if verdict["level"] in ("danger", "warn"):
                    cnt["cat_risk"] += 1

                with st.container(border=True):
                    cc = st.columns([0.6, 3.2, 1, 0.8])
                    cc[0].markdown(f"### {verdict['icon']}")
                    gap_str = f" · 20일선 대비 {gap:+.1f}%(선반영 점검)" if gap is not None else ""
                    cc[1].markdown(
                        f"**{item.get('종목명','')}**  〔{item.get('재료','')}〕\n\n"
                        f"📅 {item.get('예정일','')} · `{verdict['tag']}`{gap_str}\n\n"
                        f"{verdict['msg']}")
                    dleft = verdict.get("dleft")
                    cc[2].markdown(("**D-DAY**" if dleft == 0 else (f"**D-{dleft}**" if isinstance(dleft, int) and dleft > 0
                                    else (f"D+{abs(dleft)}" if isinstance(dleft, int) else "—"))))
                    if cc[3].button("🗑️", key=f"ac_cat_del_{i}", help="삭제"):
                        catalysts.pop(i)
                        st.session_state.ac_catalysts = catalysts
                        save_catalysts(catalysts)
                        st.rerun()

            if callable(ask_gemini):
                if st.button("🤖 AI: 임박 재료 매매 전략(소멸 vs 추세)", key="ac_cat_ai",
                             type="primary", use_container_width=True):
                    if not api_key:
                        st.error("사이드바에 API 키를 먼저 입력해주세요.")
                    else:
                        lines = []
                        for item in catalysts:
                            dl = days_until(item.get("예정일"))
                            lines.append(f"- {item.get('종목명','')} / 재료: {item.get('재료','')} / "
                                         f"예정일: {item.get('예정일','')} (D-{dl})")
                        block = "\n".join(lines)
                        prompt = (
                            "너는 이벤트 드리븐 트레이더다. 아래는 종목별 '재료 예정일' 목록이다.\n\n"
                            f"{block}\n\n"
                            "각 종목에 대해: (1) 재료 노출 전 선반영 매수 vs (2) 노출 후 소멸 회피 중 "
                            "어떤 전략이 유효한지 1~2줄로 제시하고, '소문에 사서 뉴스에 판다' 관점에서 "
                            "차익실현 타이밍을 코멘트해줘. 확률적으로 서술하고 단정은 피할 것."
                        )
                        with st.spinner("AI가 이벤트 전략을 작성 중..."):
                            st.info(ask_gemini(prompt, api_key))

    # =====================================================================
    # 상단 종합 요약 배너 채우기 (탭 계산 끝난 뒤)
    # =====================================================================
    with summary_box:
        total_red = cnt["news_bad"] + cnt["chart_bear"] + cnt["evt_soon"] + cnt["cat_risk"]
        if total_red >= 6:
            level_txt, level_color = "🔴 경계 (위험 신호 다수)", "#c62828"
        elif total_red >= 3:
            level_txt, level_color = "🟠 주의", "#e65100"
        elif total_red >= 1:
            level_txt, level_color = "🟡 관심", "#f9a825"
        else:
            level_txt, level_color = "🟢 안정", "#2e7d32"

        st.markdown(
            f"<div style='background:{level_color}1a;border-left:6px solid {level_color};"
            f"padding:12px 16px;border-radius:8px;margin-bottom:8px;'>"
            f"<span style='font-size:18px;font-weight:700;'>오늘의 종합 경보 등급: {level_txt}</span>"
            f"</div>",
            unsafe_allow_html=True,
        )
        s = st.columns(5)
        s[0].metric("🔴 악재 뉴스", cnt["news_bad"])
        s[1].metric("🟢 호재 뉴스", cnt["news_good"])
        s[2].metric("📉 차트 하락경보", cnt["chart_bear"])
        s[3].metric("🗓️ 임박 이벤트(D-3)", cnt["evt_soon"])
        s[4].metric("🎯 재료 소멸위험", cnt["cat_risk"])
        st.caption("※ 위 등급은 악재 뉴스·차트 하락경보·임박 이벤트·재료 소멸위험 건수를 합산한 단순 휴리스틱입니다. 참고용.")


# ==========================================================================
# USAGE — app__4_.py 에 4곳만 연결하면 됩니다
# ==========================================================================
"""
[1] 파일 상단 import 영역에 추가:
        import jaemini_alert_center as alert_center

[2] 사이드바 menu_options 의 '트레이딩 & 시장 경보' 묶음에 메뉴 한 줄 추가
    (예: 📰 실시간 특징주 속보 윗줄):
        " ┣ 🚨 통합 경보 센터 (뉴스·차트·일정)",

[3] LIVE_REFRESH_PAGES 집합에 추가(자동 새로고침 대상으로):
        "🚨 통합 경보 센터 (뉴스·차트·일정)",

[4] 메인 if/elif 메뉴 분기(맨 끝 부근)에 블록 추가:

elif selected_menu == "🚨 통합 경보 센터 (뉴스·차트·일정)":
    alert_center.render_alert_center({
        "analyze_technical_pattern": analyze_technical_pattern,
        "get_latest_naver_news": get_latest_naver_news,
        "get_economic_events": get_economic_events,
        "fetch_polymarket_markets": fetch_polymarket_markets,
        "get_krx_stocks": get_krx_stocks,
        "ask_gemini": ask_gemini,
        "api_key": api_key_input,
    })

끝. jaemini_alert_center.py 를 app__4_.py 와 같은 폴더에 두기만 하면 됩니다.
"""
