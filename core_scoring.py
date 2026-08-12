# -*- coding: utf-8 -*-
"""
점수 · 랭킹 · 발굴 로직  (core_scoring.py)
=====================================================================
score_one 을 비롯한 판단 로직. 가중치 상수는 scoring_weights.py 참조.

계층 순서: constants → utils → data → ai → scoring → render
위 방향으로만 의존한다(순환 없음). core.py 가 전부를 합쳐 다시 내보낸다.
"""
from core_constants import *
from core_utils import *
from core_data import *
from core_ai import *


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

def _leader_num(x):
    """float 변환. 실패·비유한(NaN/inf)이면 None."""
    try:
        v = float(x)
        return v if np.isfinite(v) else None
    except Exception as _dg_e:
        _diag_note("_leader_num", _dg_e)
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
    except Exception as _dg_e:
        _diag_note("_finder_risk", _dg_e)
        pass
    try:
        c = get_credit_balance_naver(code)
        if isinstance(c, dict) and c.get("credit_ratio") is not None:
            out["credit_ratio"] = c["credit_ratio"]
    except Exception as _dg_e:
        _diag_note("_finder_risk", _dg_e)
        pass
    return out or None


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
              sector_tilt=0.0, consensus=None, dilution=False, weights=None):
    """한 종목의 단기/중기/장기 적합도(0~100) 산출 + 자동 분류 + 사유.
    공매도/신용(빚투) 리스크가 있으면 감점(단기>중기>장기 순). AI 뉴스 판정(news_sent:-2~2)도
    점수에 반영(단기에 가장 크게). 반환: (scores, horizon, top, grade, reasons, risk_flags)

    weights: scoring_weights.DEFAULT_WEIGHTS 형태의 dict. None이면 기본값.
             백테스트에서 가중치를 바꿔가며 검증할 때 주입한다."""
    W = weights if weights is not None else SCORE_W
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
    if al["정배열"]: s += W["S_ALIGN_PERFECT"]; r_s.append("정배열")
    elif al["골든"]: s += W["S_ALIGN_GOLDEN"]; r_s.append("골든크로스")
    elif al["역배열"]: s += W["S_ALIGN_DEAD"]
    if vol_spike: s += W["S_VOL_SPIKE"]; r_s.append("거래량 급증")
    if near_entry: s += W["S_NEAR_ENTRY"]; r_s.append("매수타점 근접")
    elif over_ext: s += W["S_OVER_EXT"]
    elif broke: s += W["S_BROKE"]
    if f_pos and i_pos: s += W["S_FLOW_BOTH"]; r_s.append("외인·기관 쌍끌이")
    elif f_pos or i_pos: s += W["S_FLOW_ONE"]; r_s.append("수급 유입")
    if pension >= W["S_PENSION_DAYS_TH"]: s += W["S_PENSION_STREAK"]; r_s.append(f"기관 {pension}일 연속매수")
    if rsi is not None:
        if W["S_RSI_SWEET_LO_TH"] <= rsi <= W["S_RSI_SWEET_HI_TH"]: s += W["S_RSI_SWEET"]
        elif W["S_RSI_OK_LO_TH"] <= rsi < W["S_RSI_SWEET_LO_TH"] or W["S_RSI_SWEET_HI_TH"] < rsi <= W["S_RSI_OK_HI_TH"]: s += W["S_RSI_OK"]
        elif rsi > W["S_RSI_HOT_TH"]: s += W["S_RSI_HOT"]
        elif rsi < W["S_RSI_COLD_TH"]: s += W["S_RSI_COLD"]
    if mom3 is not None:
        s += min(W["S_MOM3_CAP"], mom3 / W["S_MOM3_DIV"]) if mom3 > 0 else W["S_MOM3_NEG"]
    s += W["S_RISKON_MULT"] * max(0.0, mood["risk_on"])      # 위험선호일 때 단기 가산
    if theme_hit: s += W["S_THEME"]; r_s.append("주도 테마")
    short = _clip(s)

    # ===== 중기(추세+테마+합리적 밸류) =====
    m = 0.0
    if weekly_up: m += W["M_WEEKLY_UP"]; r_m.append("주봉 상승추세")
    if al["정배열"]: m += W["M_ALIGN_PERFECT"]; r_m.append("정배열 유지")
    elif al["골든"]: m += W["M_ALIGN_GOLDEN"]
    if mom6 is not None and mom3 is not None:
        if mom6 > 0 and mom3 > 0:
            m += W["M_MOM_BOTH_UP"]; r_m.append("3·6개월 동반 상승")
            if mom3 > W["M_MOM3_OVERHEAT_TH"]: m += W["M_MOM3_OVERHEAT"]   # 단기 과열 감점
        elif mom6 < W["M_MOM6_WEAK_TH"]:
            m += W["M_MOM6_WEAK"]
    if theme_hit: m += W["M_THEME"]; r_m.append("주도 테마 편입")
    if per is not None:
        if 0 < per <= W["M_PER_OK_TH"]: m += W["M_PER_OK"]
        elif per > W["M_PER_HIGH_TH"]: m += W["M_PER_HIGH"]
    if pbr is not None and pbr <= W["M_PBR_OK_TH"]: m += W["M_PBR_OK"]
    if f_pos or i_pos: m += W["M_FLOW"]; r_m.append("수급 우호")
    if roe is not None and roe >= W["M_ROE_OK_TH"]: m += W["M_ROE_OK"]
    m += W["M_RISKON_MULT"] * mood["risk_on"]
    mid = _clip(m)

    # ===== 장기(가치+퀄리티+인컴) =====
    l = 0.0
    if per is not None:
        if 0 < per <= W["L_PER_DEEP_TH"]: l += W["L_PER_DEEP"]; r_l.append(f"저PER {per:.0f}")
        elif per <= W["L_PER_GOOD_TH"]: l += W["L_PER_GOOD"]; r_l.append(f"PER {per:.0f}")
        elif per <= W["L_PER_FAIR_TH"]: l += W["L_PER_FAIR"]
        elif per > W["L_PER_HIGH_TH"]: l += W["L_PER_HIGH"]
    if pbr is not None:
        if pbr <= W["L_PBR_DEEP_TH"]: l += W["L_PBR_DEEP"]; r_l.append(f"저PBR {pbr:.2f}")
        elif pbr <= W["L_PBR_GOOD_TH"]: l += W["L_PBR_GOOD"]; r_l.append(f"PBR {pbr:.2f}")
        elif pbr <= W["L_PBR_FAIR_TH"]: l += W["L_PBR_FAIR"]
    if roe is not None:
        if roe >= W["L_ROE_HIGH_TH"]: l += W["L_ROE_HIGH"]; r_l.append(f"고ROE {roe:.0f}%")
        elif roe >= W["L_ROE_OK_TH"]: l += W["L_ROE_OK"]; r_l.append(f"ROE {roe:.0f}%")
    if div is not None:
        if div >= W["L_DIV_HIGH_TH"]: l += W["L_DIV_HIGH"]; r_l.append(f"고배당 {div:.1f}%")
        elif div >= W["L_DIV_OK_TH"]: l += W["L_DIV_OK"]; r_l.append(f"배당 {div:.1f}%")
    if debt is not None:
        if debt <= W["L_DEBT_LOW_TH"]: l += W["L_DEBT_LOW"]
        elif debt > W["L_DEBT_HIGH_TH"]: l += W["L_DEBT_HIGH"]
    if off_high is not None and off_high <= W["L_OFFHIGH_TH"] and not al["역배열"]:
        l += W["L_OFFHIGH"]; r_l.append("고점대비 낙폭(저평가)")
    if weekly_up or al["정배열"]: l += W["L_TREND_OK"]
    elif al["역배열"]: l += W["L_TREND_BAD"]
    if theme_hit: l += W["L_THEME"]
    l += W["L_RISKON_MULT"] * max(0.0, mood["risk_on"])      # 위험선호↑ → 장기 가치 매력 상대적↓
    l += W["L_RISKOFF_MULT"] * max(0.0, -mood["risk_on"])    # 위험회피 구간 → 장기 가산
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
            if sbr >= W["R_SHORTBAL_HI_TH"]:
                ps += W["R_SHORTBAL_HI_S"]; pm += W["R_SHORTBAL_HI_M"]; pl += W["R_SHORTBAL_HI_L"]
                risk_flags.append(f"🩸공매도잔고 {sbr:.1f}%")
            elif sbr >= W["R_SHORTBAL_MID_TH"]:
                ps += W["R_SHORTBAL_MID_S"]; pm += W["R_SHORTBAL_MID_M"]; pl += W["R_SHORTBAL_MID_L"]
        if svr is not None:
            if svr >= W["R_SHORTVOL_HI_TH"]:
                ps += W["R_SHORTVOL_HI_S"]; pm += W["R_SHORTVOL_HI_M"]; risk_flags.append(f"🩸당일공매도 {svr:.0f}%")
            elif svr >= W["R_SHORTVOL_MID_TH"]:
                ps += W["R_SHORTVOL_MID_S"]; pm += W["R_SHORTVOL_MID_M"]
        # 공매도 추세 증가 = 추가 하방
        if str(risk.get("short_vol_trend", "")).startswith("📈") or str(risk.get("short_bal_trend", "")).startswith("📈"):
            ps += W["R_SHORT_TREND_S"]; pm += W["R_SHORT_TREND_M"]
            if "🩸공매도↑" not in risk_flags:
                risk_flags.append("🩸공매도↑")
        if cr is not None:
            if cr >= W["R_CREDIT_HI_TH"]:
                ps += W["R_CREDIT_HI_S"]; pm += W["R_CREDIT_HI_M"]; pl += W["R_CREDIT_HI_L"]
                risk_flags.append(f"⚠️신용잔고 {cr:.1f}%")
            elif cr >= W["R_CREDIT_MID_TH"]:
                ps += W["R_CREDIT_MID_S"]; pm += W["R_CREDIT_MID_M"]
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
            short = _clip(short + ns * W["N_SENT_S"])
            mid = _clip(mid + ns * W["N_SENT_M"])
            longs = _clip(longs + ns * W["N_SENT_L"])

    # ===== 컨센서스 리비전 (목표가 괴리 + 상/하향) =====
    target = _f_num(tech.get("목표가_컨센서스"))
    cur = _f_num(tech.get("현재가"))
    upside = ((target / cur) - 1) * 100 if (target and cur and cur > 0) else None
    cs = ms = ls = 0.0
    if upside is not None:
        if upside >= W["C_UPSIDE_BIG_TH"]:
            ms += W["C_UPSIDE_BIG_M"]; ls += W["C_UPSIDE_BIG_L"]; cs += W["C_UPSIDE_BIG_S"]
            r_m.append(f"기대수익 +{upside:.0f}%"); r_l.append(f"목표가 괴리 +{upside:.0f}%")
        elif upside >= W["C_UPSIDE_MID_TH"]:
            ms += W["C_UPSIDE_MID_M"]; ls += W["C_UPSIDE_MID_L"]; cs += W["C_UPSIDE_MID_S"]
            r_m.append(f"기대수익 +{upside:.0f}%")
        elif upside < 0:
            ms += W["C_UPSIDE_NEG_M"]; ls += W["C_UPSIDE_NEG_L"]; cs += W["C_UPSIDE_NEG_S"]   # 주가가 컨센 목표가 위 → 과열
    if isinstance(consensus, dict):
        rev = consensus.get("revision_dir")
        if rev == "상향":
            cs += W["C_REV_UP_S"]; ms += W["C_REV_UP_M"]; r_s.append("목표가 상향"); r_m.append("목표가 상향")
        elif rev == "하향":
            cs += W["C_REV_DOWN_S"]; ms += W["C_REV_DOWN_M"]
        if (consensus.get("report_count_30d") or 0) >= W["C_REPORTS_TH"]:
            ms += W["C_REPORTS_M"]
    short = _clip(short + cs); mid = _clip(mid + ms); longs = _clip(longs + ls)

    # ===== 매크로 → 섹터 틸트 (단기·중기 위주) =====
    if sector_tilt:
        short = _clip(short + sector_tilt * W["T_TILT_S_MULT"])
        mid = _clip(mid + sector_tilt * W["T_TILT_M_MULT"])
        longs = _clip(longs + sector_tilt * W["T_TILT_L_MULT"])
        if sector_tilt >= W["T_TILT_NOTE_TH"]:
            r_s.append("매크로 순풍(섹터)")
        elif sector_tilt <= -W["T_TILT_NOTE_TH"]:
            r_s.append("매크로 역풍(섹터)")

    # ===== 증자/CB 희석 리스크 (뉴스 감지 시) =====
    if dilution:
        short = _clip(short + W["D_DILUTION_S"])
        mid = _clip(mid + W["D_DILUTION_M"])
        longs = _clip(longs + W["D_DILUTION_L"])

    # ===== [전문가 보강] 시장 상대강도(RS)·52주 신고가·MFI·이격/유동성/변동성 =====
    is_kr = str(tech.get("티커", "")).isdigit()
    _idx20 = mood.get("_idx20") if isinstance(mood, dict) else None
    _iret = (_idx20 or {}).get("kr" if is_kr else "us")
    _sret = _f_num(tech.get("수익률20일"))
    rs20 = (_sret - _iret) if (_sret is not None and _iret is not None) else None
    if rs20 is not None:                      # 시장 대비 20일 초과수익(%p) — 오닐式 상대강도
        if rs20 >= W["X_RS_STRONG_TH"]:
            short = _clip(short + W["X_RS_STRONG_S"]); mid = _clip(mid + W["X_RS_STRONG_M"])
            r_s.append(f"시장대비 강세 RS +{rs20:.0f}%p"); r_m.append(f"상대강도 우위 +{rs20:.0f}%p")
        elif rs20 >= W["X_RS_OK_TH"]:
            short = _clip(short + W["X_RS_OK_S"])
        elif rs20 <= W["X_RS_WEAK_TH"]:
            short = _clip(short + W["X_RS_WEAK_S"]); mid = _clip(mid + W["X_RS_WEAK_M"])
    off52 = _f_num(tech.get("고점대비52주"))
    if off52 is not None:                     # 신고가 근접 = 주도주 모멘텀
        if off52 >= W["X_HIGH52_NEAR_TH"]:
            short = _clip(short + W["X_HIGH52_NEAR_S"]); mid = _clip(mid + W["X_HIGH52_NEAR_M"])
            r_s.append("52주 신고가권"); r_m.append("52주 신고가권(주도주)")
        elif off52 >= W["X_HIGH52_OK_TH"]:
            mid = _clip(mid + W["X_HIGH52_OK_M"])
    mfi = _f_num(tech.get("MFI"))
    if mfi is not None:                       # 거래량 가중 자금흐름
        if W["X_MFI_IN_LO_TH"] <= mfi <= W["X_MFI_IN_HI_TH"]:
            mid = _clip(mid + W["X_MFI_IN_M"]); r_m.append(f"자금 유입(MFI {mfi:.0f})")
        elif mfi > W["X_MFI_HOT_TH"]:
            short = _clip(short + W["X_MFI_HOT_S"]); risk_flags.append(f"🌡️MFI 과열 {mfi:.0f}")
        elif mfi < W["X_MFI_COLD_TH"]:
            short = _clip(short + W["X_MFI_COLD_S"])
    gap20 = _f_num(tech.get("이격도20"))
    if gap20 is not None and gap20 >= W["X_GAP20_TH"]:     # 20일선 과이격 = 추격매수 위험
        short = _clip(short + W["X_GAP20_S"]); risk_flags.append(f"🌡️20일선 이격 +{gap20:.0f}%")
    vol20 = _f_num(tech.get("변동성20일"))
    if vol20 is not None and vol20 >= W["X_VOL20_TH"]:     # 일변동성 과대
        short = _clip(short + W["X_VOL20_S"]); risk_flags.append(f"🎢고변동성 {vol20:.1f}%/일")
    amt20 = _f_num(tech.get("평균거래대금20일"))
    if is_kr and amt20 is not None:           # 유동성 필터(국내): 20일 평균 거래대금
        _eok = amt20 / 1e8
        if _eok < W["X_LIQ_BAD_TH"]:
            short = _clip(short + W["X_LIQ_BAD_S"]); mid = _clip(mid + W["X_LIQ_BAD_M"]); longs = _clip(longs + W["X_LIQ_BAD_L"])
            risk_flags.append(f"💧유동성 부족({_eok:.0f}억/일)")
        elif _eok < W["X_LIQ_THIN_TH"]:
            short = _clip(short + W["X_LIQ_THIN_S"]); mid = _clip(mid + W["X_LIQ_THIN_M"])

    scores = {"단기": round(short, 1), "중기": round(mid, 1), "장기": round(longs, 1)}
    ranked = sorted(scores.items(), key=lambda kv: kv[1], reverse=True)
    horizon = ranked[0][0]
    # 근소차(≤6점)는 시장 분위기로 타이브레이크
    if len(ranked) >= 2 and (ranked[0][1] - ranked[1][1]) <= W["G_TIE_GAP_TH"]:
        if mood["risk_on"] >= W["G_RISKON_HI_TH"]: pref = ["단기", "중기", "장기"]
        elif mood["risk_on"] <= W["G_RISKON_LO_TH"]: pref = ["장기", "중기", "단기"]
        else: pref = ["중기", "단기", "장기"]
        cand = [k for k, _ in ranked[:2]]
        horizon = min(cand, key=lambda k: pref.index(k))
    top = scores[horizon]
    reasons = {"단기": r_s, "중기": r_m, "장기": r_l}[horizon][:W["G_REASON_MAX"]]
    if top >= W["G_STRONG_TH"]: grade = "🟢 강력"
    elif top >= W["G_GOOD_TH"]: grade = "🟡 양호"
    else: grade = "⚪ 약함"
    return scores, horizon, round(top, 1), grade, reasons, risk_flags


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
        except Exception as _dg_e:
            _diag_note("build_finder_candidates", _dg_e)
            pass
    if scope in ("kr_us", "us"):
        try:
            for nm, cd in (get_us_scan_targets(us_n) or []):
                add(nm, cd, src="tech")
        except Exception as _dg_e:
            _diag_note("build_finder_candidates", _dg_e)
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
        except Exception as _dg_e:
            _diag_note("build_finder_candidates", _dg_e)
            pass

    # ③ 가치 후보 (장기/자동 포함 시, 국내 전용 데이터 → 국내 포함 모드에서만)
    if want_long and scope in ("kr", "kr_us"):
        try:
            for nm, cd in (get_longterm_value_stocks_with_ai(
                    "저평가 우량 가치주(저PER·저PBR·고ROE·재무안정 + 주주환원)",
                    "대/중/소형 상관없음", api_key) or []):
                add(nm, cd, src="value")
        except Exception as _dg_e:
            _diag_note("build_finder_candidates", _dg_e)
            pass

    return pool

def _finder_history_load():
    """저장된 발굴기 검색 히스토리 로드. [v7.2] 세션 우선, 없으면 기존 파일에서 seed."""
    return app_state.load("finder_history", [])


def finder_history_append(enriched, scope_label, depth, theme_focus, top_n=5, keep_runs=30):
    """이번 검색의 기간별 상위 top_n 픽(이름·코드·가격·점수)을 로컬 JSON에 기록.
    최근 keep_runs회만 유지. 성과 추적('그때 픽이 지금 얼마?')의 기준 데이터."""
    buckets = {"단기": [], "중기": [], "장기": []}
    for r in (enriched or []):
        hz = r.get("_horizon")
        if hz in buckets:
            buckets[hz].append(r)
    picks = []
    for hz in ("단기", "중기", "장기"):
        for r in sorted(buckets[hz], key=lambda x: x.get("_top", 0), reverse=True)[:top_n]:
            cur = _f_num(r.get("현재가"))
            if not r.get("티커") or not cur:
                continue
            picks.append({"hz": hz, "name": str(r.get("종목명") or ""), "code": str(r.get("티커")),
                          "price": round(cur, 4), "score": r.get("_top"),
                          "grade": re.sub(r"[🟢🟡⚪]", "", str(r.get("_grade") or "")).strip()})
    if not picks:
        return
    runs = list(_finder_history_load())
    runs.append({"ts": datetime.now().strftime("%Y-%m-%d %H:%M"),
                 "scope": str(scope_label), "depth": str(depth),
                 "theme": str(theme_focus or "").strip(), "picks": picks})
    app_state.save("finder_history", runs[-keep_runs:])


def finder_history_perf(run):
    """저장된 검색 1회의 픽별 '픽 당시 가격 → 최근 종가' 수익률 계산 (병렬, 1시간 캐시 시세 사용).
    반환: rows(list[dict]) — 기간/종목/픽가격/현재가/수익률."""
    picks = (run or {}).get("picks") or []
    codes = list(dict.fromkeys(p["code"] for p in picks))

    def _last_close(code):
        try:
            df = get_historical_data(code, 5)
            if df is not None and not df.empty:
                return code, float(df['Close'].iloc[-1])
        except Exception as _dg_e:
            _diag_note("_last_close", _dg_e)
            pass
        return code, None

    last = {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as ex:
        for code, px in ex.map(_last_close, codes):
            last[code] = px
    rows = []
    for p in picks:
        cur = last.get(p["code"])
        base = p.get("price")
        ret = (round((cur / base - 1) * 100, 2) if (cur and base and base > 0) else None)
        is_kr = str(p["code"]).isdigit()
        fmt = (lambda v: (f"{v:,.0f}원" if is_kr else f"${v:,.2f}") if v else "-")
        rows.append({"기간": p["hz"], "종목명": p["name"], "티커": p["code"],
                     "점수": p.get("score"), "픽 당시": fmt(base), "현재": fmt(cur),
                     "수익률(%)": ret})
    return rows


# `from core_scoring import *` 로 넘어갈 이름 (언더스코어 포함, 자동 생성)
_EXPORTED = [
    "_finder_export_df",
    "_finder_hide",
    "_finder_history_load",
    "_finder_risk",
    "_finder_rr",
    "_finder_sort_val",
    "_finder_tech",
    "_finder_value",
    "_leader_metrics",
    "_leader_num",
    "_leader_pctl",
    "_theme_leader_ranking",
    "_value_factors",
    "_value_rank",
    "build_finder_candidates",
    "calc_recovery_score",
    "finder_history_append",
    "finder_history_perf",
    "macro_regime_notes",
    "macro_tilt_for",
    "match_sector_heat",
    "score_one",
    "value_passes",
]

__all__ = [_n for _n in _EXPORTED if _n in globals()]
