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

import diagnostics as diag   # [v7.2] 수집 실패 진단 — 조용히 삼키던 예외를 기록
import app_state             # [v7.2] 재료 일정 세션 저장 + 백업/복원
_diag_note = diag.note

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
CATALYST_FILE = app_state.FILES["catalysts"]   # 하위 호환용


def load_catalysts():
    """[v7.2] 세션 우선 저장. 기존 catalysts.json 이 있으면 그대로 읽어와 이어 쓴다."""
    return app_state.load("catalysts", [])


def save_catalysts(items):
    app_state.save("catalysts", items)


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
    except Exception as _dg_e:
        _diag_note("_safe_float", _dg_e)
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
    except Exception as _dg_e:
        _diag_note("days_until", _dg_e)
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
    except Exception as _dg_e:
        _diag_note("_nth_weekday", _dg_e)
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
                except Exception as _dg_e:
                    _diag_note("scan_upcoming_events", _dg_e)
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
        # 3·6·9·12월 둘째 목요일은 '네마녀'(선물·옵션 동시만기) — '핵심 일정' 표기와 통일
        kr_label = "🌗 🇰🇷선물옵션 동시만기(네마녀)" if mm in (3, 6, 9, 12) else "🇰🇷 옵션만기(수급)"
        for edate, label in [(us_opex, "🇺🇸 옵션만기(변동성)"), (kr_opex, kr_label)]:
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


def _kr_index_drop(panel):
    """오늘 코스피·코스닥 '실제' 등락률 → (위험 가점, 최대 낙폭%, [(시장명, 등락률%), ...]).
    ※ 실현된 '오늘' 지수에만 적용 — 미래일은 예측 불가하므로 호출하지 않는다(가점 0).
       종합 등급이 지수 급락을 못 잡던 문제를 보완: 지수가 크게 빠진 날은 단독으로도 상위 등급이 되게 한다."""
    worst = 0.0
    parts = []
    if isinstance(panel, dict):
        for key, nm in (("KOSPI", "코스피"), ("KOSDAQ", "코스닥")):
            d = panel.get(key)
            if isinstance(d, dict) and d.get("pct") is not None:
                sp = abs(d["pct"]) * (1 if d.get("sign", 0) >= 0 else -1)   # 네이버 pct(절댓값)+sign → 부호 결합
                parts.append((nm, sp))
                if sp < worst:
                    worst = sp
    if   worst <= -3.0: pts = 6   # 폭락 → 단독으로도 경계권
    elif worst <= -2.0: pts = 4
    elif worst <= -1.5: pts = 3
    elif worst <= -1.0: pts = 2
    elif worst <= -0.7: pts = 1
    else:               pts = 0
    return pts, worst, parts


# ════════════════════════════════════════════════════════════════════════
#  금리 결정 '시장 예상(서프라이즈)' 설정 — 예보 달력의 중앙은행 결정일 위험 보정용
# ════════════════════════════════════════════════════════════════════════
#  ▸ 왜? "금리 결정일"을 무조건 고위험으로 두면 부정확. 시장이 결정을 얼마나 확실히 예상하는지에 따라
#       실제 변동성이 다르다. ①동결/변경이 '거의 확실'(예: FedWatch 95%+)하면 서프라이즈가 작아 변동성↓,
#       ②'불확실/격론'(50:50 부근, 분열 의결)이면 변동성↑. ('priced-in'된 결정은 시장 반응이 작음)
#  ▸ 한계: CME FedWatch·다국 내재확률을 무료로 '자동 수집'할 안정적 API가 없음
#       (FedWatch는 클린 API 부재, yfinance Fed Funds 선물은 미국 전용·사용자 환경에서만 가능).
#       → 분기당 회의가 몇 건뿐이므로 '수동 갱신' 테이블로 운영(관리 부담 적음).
#  ▸ 주의: FOMC는 동결이 확실해도 점도표(SEP)·기자회견 '가이던스'로 변동성이 남을 수 있음 → 'low'는 한 단계만↓.
#  ▸ 값: 'low'(시장 예상 거의 확실 → 위험 -1) / 'normal'(기본) / 'high'(불확실·격론 → 위험 +1)
#  ▸ 갱신 출처: FedWatch(cmegroup.com/markets/interest-rates/cme-fedwatch-tool.html),
#       각국 OIS/스왑 내재확률·중앙은행 코멘트. ── 마지막 갱신: 2026-06-08
RATE_DECISION_OUTLOOK = {
    # (중앙은행, 연, 월): (stance, 메모)
    ("FOMC", 2026, 6): ("low",    "FedWatch ~98~99% 동결(3.50–3.75%) — 결정은 거의 확실. 단 점도표·8-4 분열·매파 분위기로 가이던스 변동성 잔존"),
    ("ECB",  2026, 6): ("normal", "25bp 인상 폭넓게 예상되나 경기-물가 딜레마로 양방향 논쟁적"),
    ("BOJ",  2026, 6): ("normal", "점진적 정상화·데이터 의존 — 엔/원 환율·엔캐리 서프라이즈 여지"),
    # ── 창 밖(7월 이후)·갱신 자리 (확보되면 stance 갱신) ──
    ("FOMC", 2026, 7): ("normal", "하반기 인하 가능성 — 데이터 의존"),
    ("BOK",  2026, 7): ("normal", ""),
    ("ECB",  2026, 7): ("normal", ""),
    ("BOJ",  2026, 7): ("normal", ""),
}

# ════════════════════════════════════════════════════════════════════════
#  (선택) FOMC 확률 '자동 산출' — yfinance Fed Funds 선물(ZQ) → 시장 내재 stance
# ════════════════════════════════════════════════════════════════════════
#  ▸ 켜기/끄기: FED_AUTO_FETCH=True면 위 표의 FOMC stance를 '실시간 선물 값'으로 덮어씀(실패 시 표로 폴백).
#  ▸ 원리(CME FedWatch 약식): 30일 Fed Funds 선물은 '그 달 일평균 실효금리'로 정산 →
#       내재 월평균금리 = 100 − 종가.  회의는 월 중간에 열리고 결정은 '익일' 발효되므로
#         월평균 = (회의일까지 일수/총일수)×현행금리 + (회의 익일~말일 일수/총일수)×결정후금리
#       에서 '결정후금리'를 역산 → 현행 대비 예상 변동폭 → 25bp 1스텝 확률 → 결정 '확실성'으로 stance.
#       (확실성 = max(p, 1−p): 한쪽으로 확실하면 서프라이즈↓ → 'low', 접전이면 'high')
#  ▸ 현행 목표금리(중간값) FED_TARGET_RATE_PCT: 연준이 실제로 움직일 때만 갱신(드묾).
#  ▸ ★ 한계/검증: 이 코드는 야후 접속이 되는 '사용자 환경'에서만 동작(개발 샌드박스에선 야후 차단).
#       야후 선물 심볼 표기가 환경마다 달라질 수 있어 _zq_symbol_candidates 를 여러 형식으로 시도하며,
#       첫 실행 시 반드시 FedWatch 실제 수치와 대조해 보정하세요. 안 맞거나 불확실하면 FED_AUTO_FETCH=False로
#       끄면 위 수동 표만 사용합니다. 어떤 경우에도 실패하면 자동으로 표로 폴백하므로 앱이 깨지진 않습니다.
FED_AUTO_FETCH = True                 # ← 자동 산출 사용 여부 (False면 RATE_DECISION_OUTLOOK 표만 사용)
FED_TARGET_RATE_PCT = 3.625           # 현행 FOMC 목표금리 중간값(3.50–3.75%) — Fed 변경 시 갱신
_CME_MONTH_CODE = {1: "F", 2: "G", 3: "H", 4: "J", 5: "K", 6: "M",
                   7: "N", 8: "Q", 9: "U", 10: "V", 11: "X", 12: "Z"}


def _zq_symbol_candidates(year, month):
    """야후에서 시도할 ZQ(Fed Funds) 월물 심볼 후보(환경별 표기 차 대응)."""
    code = _CME_MONTH_CODE.get(month, "")
    yy = year % 100
    return [f"ZQ{code}{yy:02d}.CBT", f"ZQ{code}{yy:02d}.CME", f"ZQ{code}{yy:02d}.NYB"]


# yfinance 네트워크 호출은 1시간 캐시(달력 렌더가 여러 번 _day_level을 호출해도 1회만 fetch)
try:
    _cache_deco = st.cache_data(ttl=3600, show_spinner=False)
except Exception:
    def _cache_deco(f):
        return f


@_cache_deco
def _fetch_zq_implied_rate(symbols_tuple):
    """ZQ 선물 후보 심볼들을 순서대로 시도 → '내재 월평균금리(=100−종가)' 반환. 모두 실패 시 None."""
    try:
        import yfinance as yf
    except Exception as _dg_e:
        _diag_note("_fetch_zq_implied_rate", _dg_e)
        return None
    for sym in symbols_tuple:
        try:
            h = yf.Ticker(sym).history(period="7d")
            if h is None or len(h) == 0:
                continue
            closes = h["Close"].dropna()
            if len(closes) == 0:
                continue
            px = float(closes.iloc[-1])
            if 90.0 <= px <= 100.5:            # 정상 가격대(금리 0~10% 수준)만 채택
                return 100.0 - px
        except Exception as _dg_e:
            _diag_note("_fetch_zq_implied_rate", _dg_e)
            continue
    return None


def _fed_live_stance(meeting_date):
    """Fed Funds 선물로 FOMC 결정 '서프라이즈' stance(low/normal/high) 산출. 실패·불확실 시 None(→표 폴백)."""
    if not FED_AUTO_FETCH:
        return None
    try:
        import calendar as _cal
        y, m, day = meeting_date.year, meeting_date.month, meeting_date.day
        N = _cal.monthrange(y, m)[1]
        n1, n2 = day, N - day               # 회의일까지(현행) / 회의 익일~말일(결정후)
        if n1 < 3 or n2 < 3:                 # 월초·월말 회의는 추정 노이즈 큼 → 폴백
            return None
        avg = _fetch_zq_implied_rate(tuple(_zq_symbol_candidates(y, m)))
        if avg is None:
            return None
        r0 = FED_TARGET_RATE_PCT
        r_end = (avg - (n1 / N) * r0) * (N / n2)   # 결정후금리 역산
        change = r_end - r0
        if abs(change) > 0.60:               # 한 회의 ±60bp 초과는 비현실적 → 데이터 의심 → 폴백
            return None
        p_move = min(abs(change) / 0.25, 1.0)      # 25bp 1스텝 확률(근사)
        certainty = max(p_move, 1.0 - p_move)      # 0.5(완전 접전) ~ 1.0(완전 확실)
        if certainty >= 0.85:
            return "low"                     # 결과가 한쪽으로 확실 → 서프라이즈↓
        if certainty <= 0.62:
            return "high"                    # 접전(≈35~65%) → 서프라이즈↑
        return "normal"
    except Exception as _dg_e:
        _diag_note("_fed_live_stance", _dg_e)
        return None


def render_grade_forecast_calendar(get_economic_events, get_kr_index_panel=None):
    """📅 다가오는 ~1개월간 '종합 경보 등급'을 달력 형태로 예보.

    ※ 예측의 한계: 종합 등급 구성요소 중 '뉴스(악재/호재)'와 '차트 하락경보'는 아직 일어나지 않은
       일이라 예측 불가. 예측 가능한 건 '예정된 매크로·파생 일정'뿐이다. 따라서 이 달력은 그날 예정된
       이벤트로 인한 '예상 변동성 위험'을 등급화한 이벤트 기반 예보다.
    """
    if not callable(get_economic_events):
        st.info("📅 일정 예보 달력은 경제 일정 데이터(get_economic_events)가 연결되어야 표시됩니다.")
        return

    today = date.today()

    # 오늘 '실제' 지수 급락 가점 (실현된 오늘만 — 미래일은 예측 불가) → 오늘 칸 등급에 반영
    idx_pts_today, idx_worst_today, idx_parts_today = 0, 0.0, []
    if callable(get_kr_index_panel):
        try:
            idx_pts_today, idx_worst_today, idx_parts_today = _kr_index_drop(get_kr_index_panel())
        except Exception:
            idx_pts_today, idx_worst_today, idx_parts_today = 0, 0.0, []

    # 급락 '여진': 큰 급락 다음 1~3거래일은 '변동성'이 확대되는 경향(변동성 클러스터링).
    #   ── 과거 1년 실측(코스피 -3%↑ 급락 n=15): +1일 변동성 평소의 약 2.3배(코스닥 ~3배), +2일 ~1.9배, +3일 ~1.25배.
    #      방향은 +1~2일 평균 '반등'(+1.5%), +3일 되돌림 → 추가하락이 아니라 '양방향 변동성↑'가 본질.
    #   오늘 실현된 낙폭에만 기반(미래 시세는 모름) · 날이 갈수록 감쇠.
    aftershock = {}   # {date: 가점}
    if idx_worst_today <= -1.5:
        if   idx_worst_today <= -5.0: base = 5     # 극단 급락(-5%↑): 다음날 경계급
        elif idx_worst_today <= -3.0: base = 4
        elif idx_worst_today <= -2.0: base = 3
        else:                         base = 2
        cur, step = today, 0
        while step < 3:
            cur += timedelta(days=1)
            if cur.weekday() < 5:            # 거래일(월~금)만 카운트 → 금요일 급락 시 월요일부터 반영
                step += 1
                pts = base - (step - 1)      # 1일째=base, 2일째=base-1, 3일째=base-2
                if pts > 0:
                    aftershock[cur] = pts

    # 네마녀(둘째 목, 3·6·9·12월) '다음 거래일' 소폭 가점 — 위칭 '언와인드'.
    #   ── 과거 1년 실측: 네마녀 다음날은 평균적으론 오히려 잠잠하나(변동성 1.38%<평소 1.59%),
    #      '하락 마감' 네마녀 뒤에는 며칠 약세·변동성 잔존(특히 +3일 1.93%) → 작게(+1=관심) 반영.
    #   (반면 FOMC·CPI 다음날은 실측상 정상화 → 별도 가점 없음)
    event_spillover = {}   # {date: 가점}
    _s = today - timedelta(days=7)
    while _s <= today + timedelta(days=40):
        if _s.month in (3, 6, 9, 12) and _s.weekday() == 3 and 8 <= _s.day <= 14:   # 네마녀
            _nd = _s + timedelta(days=1)
            while _nd.weekday() >= 5:        # 다음 거래일
                _nd += timedelta(days=1)
            event_spillover[_nd] = 1
        _s += timedelta(days=1)

    # ── 1) 향후 ~40일 이벤트를 날짜별로 수집 (센터의 다른 지표와 동일 소스: scan_upcoming_events) ──
    by_date = {}
    try:
        for e in scan_upcoming_events(get_economic_events, within_days=40):
            by_date.setdefault(e["date"], []).append(e)
    except Exception:
        by_date = {}

    # 주말(토·일) 일정은 국장 휴장이므로 '다음 거래일(월요일)'로 접는다 — 영향은 월요일 개장에 반영.
    #   (예: 일부 미국·중국·한국 지표가 주말/월초에 잡히면 월요일 칸에 '주말' 표시와 함께 노출)
    _folded = {}
    for _d, _evs in by_date.items():
        if _d.weekday() >= 5:                                  # 토(5)·일(6)
            _mon = _d + timedelta(days=(7 - _d.weekday()))     # 다음 월요일
            for _e in _evs:
                _e2 = dict(_e); _e2["_weekend"] = _d           # 원래 주말 날짜 보관
                _folded.setdefault(_mon, []).append(_e2)
        else:
            _folded.setdefault(_d, []).extend(_evs)
    by_date = _folded

    # ── 2) 이벤트 영향도 가중치 → 일자별 점수 → 4단계 등급 ──
    #    (※ 가중치·임계값은 여기서 조절: 숫자가 크면 더 쉽게 상위 등급으로 올라감)
    def _impact(label):
        t = str(label)
        if any(k in t for k in ("FOMC 금리", "금통위", "ECB 통화", "BOJ 금융", "금리결정")): return 3  # 중앙은행 금리결정
        if any(k in t for k in ("CPI", "PCE", "고용지표")):                                   return 3  # 최상위 지표(물가·고용)
        if any(k in t for k in ("네마녀", "동시만기")):                                        return 3  # 쿼드러플위칭
        if "옵션만기" in t:                                                                    return 2  # 일반 월물 만기
        if "의사록" in t:                                                                      return 1
        return 1                                                                                          # PMI·소매판매·수출입 등

    def _is_quad_witching(d):   # 3·6·9·12월 둘째 목요일 = 네마녀(국내 선물·옵션 동시만기)
        return d.month in (3, 6, 9, 12) and d.weekday() == 3 and 8 <= d.day <= 14

    def _rate_outlook_adj(label, d):
        # 중앙은행 '결정일' 한정(의사록 제외) → 시장 예상(서프라이즈) 보정값.
        #   동결/변경 거의 확실 → -1(변동성↓), 불확실·격론 → +1(변동성↑), 기본 0.
        #   FOMC는 yfinance Fed Funds 선물 실시간값을 우선 적용(실패 시 RATE_DECISION_OUTLOOK 표로 폴백).
        t = str(label)
        if "의사록" in t:                       return 0          # 의사록은 결정이 아님 → 제외
        if "FOMC 금리" in t:
            stance = _fed_live_stance(d)                          # ① 선물 실시간
            if stance is None:                                    # ② 폴백: 수동 표
                stance, _memo = RATE_DECISION_OUTLOOK.get(("FOMC", d.year, d.month), ("normal", ""))
        elif "금통위"   in t:    stance, _ = RATE_DECISION_OUTLOOK.get(("BOK", d.year, d.month), ("normal", ""))
        elif "ECB 통화"  in t:    stance, _ = RATE_DECISION_OUTLOOK.get(("ECB", d.year, d.month), ("normal", ""))
        elif "BOJ 금융"  in t:    stance, _ = RATE_DECISION_OUTLOOK.get(("BOJ", d.year, d.month), ("normal", ""))
        else:                                   return 0
        return -1 if stance == "low" else (1 if stance == "high" else 0)

    def _day_level(d):
        evs = by_date.get(d, [])
        score = sum(_impact(e["label"]) for e in evs)
        if evs and _is_quad_witching(d):   # 만기일(네마녀)이면 변동성 가중
            score += 1
        score += sum(_rate_outlook_adj(e["label"], d) for e in evs)  # 금리결정 '시장 예상' 보정
        score += event_spillover.get(d, 0)  # 네마녀 '다음 거래일' 소폭 가점(위칭 언와인드)
        if d == today:                     # 오늘은 '실제' 지수 급락도 반영(예측이 아닌 실현값)
            score += idx_pts_today
        else:                              # 미래 칸은 최근 급락의 '여진'만 반영(이벤트 외 시세는 예측 불가)
            score += aftershock.get(d, 0)
        score = max(score, 0)              # 보정으로 음수가 되지 않도록
        if score == 0:  return 0, evs
        if score <= 2:  return 1, evs
        if score <= 4:  return 2, evs
        return 3, evs

    LEVELS = {   # 등급: (라벨, 진한색, 옅은배경)  ← 상단 종합경보 배너 색과 통일
        0: ("안정", "#2e7d32", "#f0fdf4"),
        1: ("관심", "#b88300", "#fffbeb"),
        2: ("주의", "#c2410c", "#fff7ed"),
        3: ("경계", "#b91c1c", "#fef2f2"),
    }
    DOTS = {0: "🟢", 1: "🟡", 2: "🟠", 3: "🔴"}

    # ── 3) 달력 범위: 거래주(월~금)만 — 국장 휴장인 토·일 열은 제외 ──
    start = today - timedelta(days=today.weekday())                                 # 이번 주 월요일
    end_anchor = today + timedelta(days=30)                                         # 1개월 경계
    end = (end_anchor - timedelta(days=end_anchor.weekday())) + timedelta(days=4)   # end_anchor 주의 금요일

    dow = ["월", "화", "수", "목", "금"]
    head = "".join(
        f'<div style="text-align:center;font-size:11px;font-weight:800;color:#64748b;padding:3px 0;">{w}</div>'
        for w in dow
    )

    cells = ""
    d = start
    while d <= end:
        if d.weekday() >= 5:               # 토(5)·일(6)은 렌더하지 않음(국장 휴장)
            d += timedelta(days=1)
            continue
        is_today = (d == today)
        if d < today or d > end_anchor:     # 범위 밖(이번 주 지난 거래일 / 1개월 초과) → 흐리게
            cells += (
                f'<div style="min-height:76px;border:1px dashed #eef2f6;border-radius:9px;'
                f'background:#fbfcfd;padding:6px 7px;opacity:.5;">'
                f'<div style="font-size:12px;font-weight:700;color:#cbd5e1;">{d.day}</div></div>'
            )
            d += timedelta(days=1)
            continue

        lvl, evs = _day_level(d)
        lab, col, bgc = LEVELS[lvl]
        brd = col if lvl >= 2 else "#e9eef3"
        ring = f"box-shadow:0 0 0 2px {col} inset;" if is_today else ""
        chips = ""
        for e in evs[:3]:
            wk = e.get("_weekend")          # 주말에서 접혀온 일정 → '주말(날짜)' 표시
            suffix = (f' <span style="color:#94a3b8;font-weight:600;">(주말 {wk.month}/{wk.day})</span>'
                      if wk else "")
            chips += (
                f'<div style="font-size:9.5px;line-height:1.25;color:{col};font-weight:700;'
                f'white-space:nowrap;overflow:hidden;text-overflow:ellipsis;">{e["label"]}{suffix}</div>'
            )
        if len(evs) > 3:
            chips += f'<div style="font-size:9px;color:#94a3b8;">+{len(evs) - 3}건</div>'
        # 금리 결정일: 시장 예상(서프라이즈) 보정 표시
        _radj = sum(_rate_outlook_adj(e["label"], d) for e in evs)
        if _radj < 0:
            chips += ('<div style="font-size:9px;color:#0369a1;font-weight:800;white-space:nowrap;'
                      'overflow:hidden;text-overflow:ellipsis;">🏦 시장 예상 확실(변동성↓)</div>')
        elif _radj > 0:
            chips += (f'<div style="font-size:9px;color:{col};font-weight:800;white-space:nowrap;'
                      f'overflow:hidden;text-overflow:ellipsis;">🏦 결정 불확실(변동성↑)</div>')
        # 오늘은 '실제' 지수 급락을 사유로 표시
        if is_today and idx_pts_today > 0 and idx_parts_today:
            w = min(idx_parts_today, key=lambda x: x[1])   # 가장 큰 낙폭 시장
            chips += (f'<div style="font-size:9px;color:{col};font-weight:800;white-space:nowrap;'
                      f'overflow:hidden;text-overflow:ellipsis;">📉 {w[0]} {w[1]:+.1f}% 급락</div>')
        # 미래 칸: 최근 급락 여진(양방향 변동성↑) / 네마녀 다음날 사유 표시
        elif (not is_today) and aftershock.get(d):
            chips += (f'<div style="font-size:9px;color:{col};font-weight:800;white-space:nowrap;'
                      f'overflow:hidden;text-overflow:ellipsis;">📊 변동성 여진(급락 후)</div>')
        elif (not is_today) and event_spillover.get(d):
            chips += (f'<div style="font-size:9px;color:{col};font-weight:800;white-space:nowrap;'
                      f'overflow:hidden;text-overflow:ellipsis;">🌗 네마녀 다음날</div>')

        today_tag = ' <span style="font-size:8.5px;color:#dc2626;font-weight:900;">●오늘</span>' if is_today else ""
        cells += (
            f'<div style="min-height:82px;border:1px solid {brd};border-radius:9px;'
            f'background:{bgc};padding:6px 7px;{ring}">'
            f'<div style="font-size:12.5px;font-weight:800;color:#0f172a;">{d.day}{today_tag}</div>'
            f'<div style="font-size:10px;font-weight:800;color:{col};margin:1px 0 2px;">{DOTS[lvl]} {lab}</div>'
            f'<div>{chips}</div></div>'
        )
        d += timedelta(days=1)

    period = (f"{start.year}년 {start.month}월" if start.month == end.month
              else f"{start.year}년 {start.month}~{end.month}월")
    st.markdown(f"##### 📅 다가오는 1개월 종합 경보 등급 예보 · {period} (거래일 월~금)")
    st.markdown(
        f'<div style="background:#fff;border:1px solid #e9eef3;border-radius:16px;padding:12px 14px;'
        f'box-shadow:0 1px 3px rgba(0,0,0,0.04);">'
        f'<div style="display:grid;grid-template-columns:repeat(5,1fr);gap:5px;margin-bottom:5px;">{head}</div>'
        f'<div style="display:grid;grid-template-columns:repeat(5,1fr);gap:5px;">{cells}</div></div>',
        unsafe_allow_html=True,
    )

    legend = "".join(
        f'<span style="margin-right:13px;font-size:11.5px;color:#475569;">{DOTS[k]} {LEVELS[k][0]}</span>'
        for k in (0, 1, 2, 3)
    )
    st.markdown(
        f'<div style="margin-top:7px;">{legend}'
        f'<span style="font-size:11px;color:#94a3b8;"> · 국장 휴장인 토·일은 제외 / 주말 일정은 다음 월요일 칸에 "(주말)"로 표시</span></div>',
        unsafe_allow_html=True,
    )

    # 주의 이상 예보일 요약
    dow_k = ["월", "화", "수", "목", "금", "토", "일"]
    alert_days = []
    d = today
    while d <= end_anchor:
        lvl, evs = _day_level(d)
        if lvl >= 2:
            reason = ", ".join(
                (f'{e["label"]}(주말 {e["_weekend"].month}/{e["_weekend"].day})' if e.get("_weekend") else e["label"])
                for e in evs
            )
            if d == today and idx_pts_today > 0 and idx_parts_today:   # 오늘 급락 사유 덧붙임
                w = min(idx_parts_today, key=lambda x: x[1])
                drop_txt = f"📉 지수 급락(오늘 {w[0]} {w[1]:+.1f}%)"
                reason = f"{drop_txt} · {reason}" if reason else drop_txt
            elif d != today and aftershock.get(d):                     # 급락 여진(양방향 변동성↑)
                shock_txt = "📊 급락 여진(변동성 확대·양방향)"
                reason = f"{shock_txt} · {reason}" if reason else shock_txt
            elif d != today and event_spillover.get(d):                # 네마녀 다음날
                wt_txt = "🌗 네마녀 다음날(위칭 언와인드)"
                reason = f"{wt_txt} · {reason}" if reason else wt_txt
            _radj = sum(_rate_outlook_adj(e["label"], d) for e in evs)  # 금리결정 시장 예상 메모
            if _radj < 0:
                reason = f"{reason} · 🏦 시장 예상 확실(변동성↓)"
            elif _radj > 0:
                reason = f"{reason} · 🏦 결정 불확실(변동성↑)"
            tag = " (오늘·실시간)" if d == today else ""
            alert_days.append((d, lvl, reason + tag))
        d += timedelta(days=1)
    if alert_days:
        items = "".join(
            f'<div style="font-size:12px;color:#475569;margin:2px 0;">{DOTS[lvl]} '
            f'<b>{dd.month}/{dd.day}({dow_k[dd.weekday()]})</b> '
            f'<span style="color:{LEVELS[lvl][1]};font-weight:800;">{LEVELS[lvl][0]}</span> — {nm}</div>'
            for dd, lvl, nm in alert_days
        )
        st.markdown(
            f'<div style="background:#fffaf5;border:1px solid #fed7aa;border-radius:12px;padding:10px 14px;margin-top:8px;">'
            f'<div style="font-size:12.5px;font-weight:800;color:#c2410c;margin-bottom:5px;">⚠️ 주의 이상 예보일 · {len(alert_days)}일</div>'
            f'{items}</div>', unsafe_allow_html=True)

    st.caption("※ 미래 칸 등급은 '예정 일정 + 최근 충격 여진 + 금리 결정 시장예상' 기반 예보입니다 — '안정'은 시장이 잠잠하다는 뜻이 아니라 '예정된 큰 이벤트가 없음'을 뜻합니다. "
               "여진 가중치는 과거 1년 코스피·코스닥 실측에 맞춰 보정: ①3%↑ 급락 후 1~3거래일 변동성 평소의 2~3배(양방향, 추가하락 아님)로 확대 → '급락 여진' 반영, "
               "②네마녀 다음날은 평균적으론 잠잠하나 약세 잔존 가능 → 소폭 반영, ③FOMC·CPI 다음날은 실측상 정상화 → 가점 없음. "
               "또 금리 결정일은 시장 예상(예: FedWatch)을 반영 — 동결/변경이 거의 확실하면 서프라이즈가 작아 위험을 한 단계 낮추고(🏦 변동성↓), 불확실·격론이면 높입니다(🏦 변동성↑). "
               "단 어떤 지표도 내일의 시세·뉴스를 정확히 예측하진 못합니다 — 금리 예상은 RATE_DECISION_OUTLOOK 표에서 수동 갱신(FedWatch 등 참고)하는 참고용입니다.")
    st.divider()


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
    get_kr_index_panel = deps.get("get_kr_index_panel")   # [추가] 코스피·코스닥 실시간 등락률(등급·예보에 지수 급락 반영)
    fetch_polymarket_markets = deps.get("fetch_polymarket_markets")
    get_krx_stocks = deps.get("get_krx_stocks")
    ask_gemini = deps.get("ask_gemini")
    api_key = deps.get("api_key", "")

    st.title("🚨 통합 경보 센터")
    st.caption("뉴스·정세 / 차트 패턴 / 시기·일정(호재 소멸)을 한 화면에서 감시하는 매매 경보기입니다. "
               "각 신호는 '참고용'이며 매매 판단은 본인 책임입니다.")

    # ---------------- 상단 종합 요약 배너 ----------------
    summary_box = st.container()

    # 📅 다가오는 1개월 '종합 경보 등급' 예보 (이벤트 기반 달력) — 배너 바로 아래·탭 위에 표시
    render_grade_forecast_calendar(get_economic_events, get_kr_index_panel)

    tabs = st.tabs([
        "📰 뉴스·정세 경보",
        "📉 차트 패턴 경보",
        "🗓️ 시기·일정 경보 (호재 소멸)",
    ])

    # 요약 배너에 채워 넣을 카운터
    #  - evt_month: 향후 1개월(30일) 이벤트 → 배너 '표기' + 종합 '등급' 산정 모두 사용
    #  - evt_soon : 임박(D-3) 이벤트 → 참고용(현재 등급식엔 미사용. 필요 시 활용 가능)
    cnt = {"news_bad": 0, "news_good": 0, "chart_bear": 0, "chart_bull": 0,
           "evt_soon": 0, "evt_month": 0, "cat_risk": 0}

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
            except Exception as _dg_e:
                _diag_note("render_alert_center", _dg_e)
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

        within = st.slider("앞으로 며칠 이내 일정 표시", 3, 30, 10, key="ac_evt_within")
        # 1개월(30일) 전체를 한 번 스캔한 뒤, 슬라이더 범위만 상세 표시 (가까운 순 정렬 유지)
        evts_month = scan_upcoming_events(get_economic_events, within_days=30)
        evts = [e for e in evts_month if e["dleft"] <= within]
        cnt["evt_month"] = len(evts_month)                               # 배너 표기 + 등급 산정용: 향후 1개월 이벤트 수
        cnt["evt_soon"] = sum(1 for e in evts_month if e["dleft"] <= 3)  # 참고용: 임박(D-3) 건수 (등급식엔 미사용)

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

        catalysts = load_catalysts()           # [v7.2] 세션 저장소에서 로드(없으면 파일 seed)
        app_state.render_backup_ui("catalysts", "재료 일정")

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
                    save_catalysts(catalysts)      # 세션 + (가능하면) 파일 동시 저장
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
        # 1개월 이벤트는 연중 ~14건이 '기본 부하'(EVT_BASELINE). 그 위에 뉴스·차트·재료 위험을 더하고,
        # '오늘 실제 지수 급락'(코스피·코스닥)도 더해 등급을 매긴다. 임계값 = baseline + (6/3/1).
        #   ※ 지수 급락 반영 전에는 −6% 폭락에도 악재뉴스·차트경보가 적으면 '관심'에 머무는 문제가 있었음.
        EVT_BASELINE = 14
        idx_pts, idx_worst, idx_parts = 0, 0.0, []
        if callable(get_kr_index_panel):
            try:
                idx_pts, idx_worst, idx_parts = _kr_index_drop(get_kr_index_panel())
            except Exception:
                idx_pts, idx_worst, idx_parts = 0, 0.0, []
        total_red = cnt["news_bad"] + cnt["chart_bear"] + cnt["evt_month"] + cnt["cat_risk"] + idx_pts
        if total_red >= EVT_BASELINE + 6:     # 기본 부하 + 추가 위험 다수
            level_txt, level_color = "🔴 경계 (위험 신호 다수)", "#b91c1c"
        elif total_red >= EVT_BASELINE + 3:
            level_txt, level_color = "🟠 주의", "#e65100"
        elif total_red >= EVT_BASELINE + 1:
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
        # 오늘 지수 등락 + 급락 반영분 표시(왜 등급이 올랐는지 투명하게)
        if idx_parts:
            idx_txt = " · ".join(f"{nm} {sp:+.2f}%" for nm, sp in idx_parts)
            note_c = "#b91c1c" if idx_pts >= 4 else ("#e65100" if idx_pts >= 2 else "#64748b")
            extra = f" → 시장 급락 위험 <b>+{idx_pts}</b> 반영" if idx_pts > 0 else ""
            st.markdown(
                f"<div style='font-size:12.5px;color:{note_c};font-weight:700;margin:-2px 0 8px;'>"
                f"📊 오늘 지수: {idx_txt}{extra}</div>", unsafe_allow_html=True)
        s = st.columns(5)
        s[0].metric("🔴 악재 뉴스", cnt["news_bad"])
        s[1].metric("🟢 호재 뉴스", cnt["news_good"])
        s[2].metric("📉 차트 하락경보", cnt["chart_bear"])
        s[3].metric("🗓️ 1개월내 이벤트", cnt["evt_month"])
        s[4].metric("🎯 재료 소멸위험", cnt["cat_risk"])
        st.caption("※ 등급은 악재 뉴스·차트 하락경보·1개월내 이벤트·재료 소멸위험 건수에 '오늘 실제 지수 급락'을 더한 단순 휴리스틱입니다. "
                   "이벤트는 매달 ~14건이 기본 부하라 이를 기준점으로 두고, 그 위의 추가 위험(뉴스·차트·재료·지수 급락)으로 등급을 매깁니다. 참고용.")


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
