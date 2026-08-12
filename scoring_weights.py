# -*- coding: utf-8 -*-
"""
📐 점수 엔진 가중치 상수  (Jaemini PRO)
=====================================================================
`score_one()` 과 `macro_tilt_for()` 가 쓰던 하드코딩 숫자를 전부 이 파일로 옮긴 것.

왜 분리했나
  - 기존에는 13,000줄짜리 app.py 안에 +25, -18, 3.0 같은 숫자가 흩어져 있어
    "이 점수가 왜 나왔는지" 추적도, 조정도, 검증도 불가능했다.
  - 여기에 모아두면 (1) 한눈에 보이고 (2) 백테스트에서 값을 바꿔가며
    실제 수익률과 대조해 검증할 수 있다.

쓰는 법
    from scoring_weights import DEFAULT_WEIGHTS, make_weights
    score_one(tech, vm, mood)                          # 기본값 사용
    score_one(tech, vm, mood, weights=make_weights({"S_ALIGN_PERFECT": 30}))

주의
  - 값 이름 접두사:  S_=단기, M_=중기, L_=장기, R_=리스크감점, N_=뉴스,
                     C_=컨센서스, T_=섹터틸트, D_=희석, X_=전문가지표, G_=등급판정
  - `_TH` 로 끝나면 가중치가 아니라 '기준값(threshold)'이다. 점수가 아니라
    조건 분기에 쓰이므로 바꾸면 의미 자체가 달라진다.
"""

DEFAULT_WEIGHTS = {
    # =================================================================
    # 단기 (스윙/모멘텀)
    # =================================================================
    "S_ALIGN_PERFECT": 25.0,        # 완벽 정배열
    "S_ALIGN_GOLDEN": 20.0,         # 5-20 골든크로스
    "S_ALIGN_DEAD": -18.0,          # 역배열
    "S_VOL_SPIKE": 16.0,            # 거래량 급증
    "S_NEAR_ENTRY": 14.0,           # 20일선 타점 근접
    "S_OVER_EXT": 2.0,              # 이격 과다
    "S_BROKE": -10.0,               # 20일선 이탈
    "S_FLOW_BOTH": 18.0,            # 외인·기관 쌍끌이
    "S_FLOW_ONE": 8.0,              # 한쪽만 순매수
    "S_PENSION_STREAK": 7.0,        # 연기금 연속 순매수
    "S_PENSION_DAYS_TH": 3,         # ↑ 적용 최소 연속일수
    "S_RSI_SWEET": 10.0,            # RSI 50~68
    "S_RSI_OK": 5.0,                # RSI 40~50 또는 68~78
    "S_RSI_HOT": -8.0,              # RSI > 82
    "S_RSI_COLD": -3.0,             # RSI < 28
    "S_RSI_SWEET_LO_TH": 50.0,
    "S_RSI_SWEET_HI_TH": 68.0,
    "S_RSI_OK_LO_TH": 40.0,
    "S_RSI_OK_HI_TH": 78.0,
    "S_RSI_HOT_TH": 82.0,
    "S_RSI_COLD_TH": 28.0,
    "S_MOM3_DIV": 5.0,              # 3개월 모멘텀 ÷ 이 값 = 가산점
    "S_MOM3_CAP": 8.0,              # ↑ 가산 상한
    "S_MOM3_NEG": -5.0,             # 3개월 모멘텀 음수일 때
    "S_RISKON_MULT": 8.0,           # × max(0, risk_on)
    "S_THEME": 8.0,                 # 주도 테마 편입

    # =================================================================
    # 중기 (추세 + 테마 + 합리적 밸류)
    # =================================================================
    "M_WEEKLY_UP": 25.0,            # 주봉 상승추세
    "M_ALIGN_PERFECT": 12.0,
    "M_ALIGN_GOLDEN": 8.0,
    "M_MOM_BOTH_UP": 18.0,          # 3·6개월 동반 상승
    "M_MOM3_OVERHEAT": -8.0,        # ↑ 중 3개월이 과열이면 차감
    "M_MOM3_OVERHEAT_TH": 60.0,
    "M_MOM6_WEAK": -8.0,            # 6개월 모멘텀 부진
    "M_MOM6_WEAK_TH": -15.0,
    "M_THEME": 20.0,
    "M_PER_OK": 8.0,                # 0 < PER <= 25
    "M_PER_OK_TH": 25.0,
    "M_PER_HIGH": -3.0,             # PER > 40
    "M_PER_HIGH_TH": 40.0,
    "M_PBR_OK": 5.0,
    "M_PBR_OK_TH": 4.0,
    "M_FLOW": 8.0,                  # 외인 또는 기관 순매수
    "M_ROE_OK": 6.0,
    "M_ROE_OK_TH": 8.0,
    "M_RISKON_MULT": 4.0,

    # =================================================================
    # 장기 (가치 + 퀄리티 + 인컴)
    # =================================================================
    "L_PER_DEEP": 25.0,             # PER <= 10
    "L_PER_DEEP_TH": 10.0,
    "L_PER_GOOD": 18.0,             # PER <= 15
    "L_PER_GOOD_TH": 15.0,
    "L_PER_FAIR": 8.0,              # PER <= 25
    "L_PER_FAIR_TH": 25.0,
    "L_PER_HIGH": -5.0,             # PER > 40
    "L_PER_HIGH_TH": 40.0,
    "L_PBR_DEEP": 20.0,             # PBR <= 1.0
    "L_PBR_DEEP_TH": 1.0,
    "L_PBR_GOOD": 12.0,             # PBR <= 1.5
    "L_PBR_GOOD_TH": 1.5,
    "L_PBR_FAIR": 5.0,              # PBR <= 3
    "L_PBR_FAIR_TH": 3.0,
    "L_ROE_HIGH": 18.0,             # ROE >= 15%
    "L_ROE_HIGH_TH": 15.0,
    "L_ROE_OK": 10.0,               # ROE >= 10%
    "L_ROE_OK_TH": 10.0,
    "L_DIV_HIGH": 12.0,             # 배당수익률 >= 4%
    "L_DIV_HIGH_TH": 4.0,
    "L_DIV_OK": 7.0,                # >= 2%
    "L_DIV_OK_TH": 2.0,
    "L_DEBT_LOW": 8.0,              # 부채비율 <= 100%
    "L_DEBT_LOW_TH": 100.0,
    "L_DEBT_HIGH": -5.0,            # > 180%
    "L_DEBT_HIGH_TH": 180.0,
    "L_OFFHIGH": 10.0,              # 고점대비 -30% 이하 & 역배열 아님
    "L_OFFHIGH_TH": -30.0,
    "L_TREND_OK": 8.0,              # 주봉 상승 또는 정배열
    "L_TREND_BAD": -10.0,           # 역배열
    "L_THEME": 5.0,
    "L_RISKON_MULT": -6.0,          # × max(0, risk_on)  — 위험선호↑ → 장기 매력↓
    "L_RISKOFF_MULT": 6.0,          # × max(0, -risk_on) — 위험회피 → 장기 가산

    # =================================================================
    # 공매도 / 신용(빚투) 리스크 감점   (단기 > 중기 > 장기)
    # =================================================================
    "R_SHORTBAL_HI_TH": 3.0,        # 공매도 잔고 비중(%)
    "R_SHORTBAL_HI_S": 12.0,
    "R_SHORTBAL_HI_M": 8.0,
    "R_SHORTBAL_HI_L": 4.0,
    "R_SHORTBAL_MID_TH": 1.5,
    "R_SHORTBAL_MID_S": 6.0,
    "R_SHORTBAL_MID_M": 4.0,
    "R_SHORTBAL_MID_L": 2.0,
    "R_SHORTVOL_HI_TH": 20.0,       # 당일 공매도 거래 비중(%)
    "R_SHORTVOL_HI_S": 10.0,
    "R_SHORTVOL_HI_M": 5.0,
    "R_SHORTVOL_MID_TH": 10.0,
    "R_SHORTVOL_MID_S": 5.0,
    "R_SHORTVOL_MID_M": 2.0,
    "R_SHORT_TREND_S": 4.0,         # 공매도 증가 추세
    "R_SHORT_TREND_M": 2.0,
    "R_CREDIT_HI_TH": 10.0,         # 신용잔고율(%)
    "R_CREDIT_HI_S": 8.0,
    "R_CREDIT_HI_M": 5.0,
    "R_CREDIT_HI_L": 2.0,
    "R_CREDIT_MID_TH": 5.0,
    "R_CREDIT_MID_S": 4.0,
    "R_CREDIT_MID_M": 2.0,

    # =================================================================
    # AI 뉴스 호재/악재  (news_sent: -2 ~ +2 에 곱함)
    # =================================================================
    "N_SENT_S": 6.0,
    "N_SENT_M": 3.0,
    "N_SENT_L": 1.0,

    # =================================================================
    # 증권사 컨센서스 (목표가 괴리 + 리비전)
    # =================================================================
    "C_UPSIDE_BIG_TH": 30.0,        # 목표가 괴리(%)
    "C_UPSIDE_BIG_S": 6.0,
    "C_UPSIDE_BIG_M": 10.0,
    "C_UPSIDE_BIG_L": 8.0,
    "C_UPSIDE_MID_TH": 15.0,
    "C_UPSIDE_MID_S": 3.0,
    "C_UPSIDE_MID_M": 6.0,
    "C_UPSIDE_MID_L": 5.0,
    "C_UPSIDE_NEG_S": -3.0,         # 주가가 컨센 목표가 위 = 과열
    "C_UPSIDE_NEG_M": -4.0,
    "C_UPSIDE_NEG_L": -4.0,
    "C_REV_UP_S": 6.0,              # 목표가 상향
    "C_REV_UP_M": 5.0,
    "C_REV_DOWN_S": -6.0,           # 목표가 하향
    "C_REV_DOWN_M": -4.0,
    "C_REPORTS_M": 2.0,             # 30일 내 리포트 2건 이상
    "C_REPORTS_TH": 2,

    # =================================================================
    # 매크로 → 섹터 틸트 (단기·중기 위주)
    # =================================================================
    "T_TILT_S_MULT": 1.0,
    "T_TILT_M_MULT": 0.7,
    "T_TILT_L_MULT": 0.2,
    "T_TILT_NOTE_TH": 4.0,          # ±이 값 이상이면 '매크로 순풍/역풍' 사유 표기

    # =================================================================
    # 증자/CB 희석 리스크
    # =================================================================
    "D_DILUTION_S": -14.0,
    "D_DILUTION_M": -8.0,
    "D_DILUTION_L": -6.0,

    # =================================================================
    # 전문가 보강 지표 (상대강도·신고가·MFI·이격·변동성·유동성)
    # =================================================================
    "X_RS_STRONG_TH": 7.0,          # 시장 대비 20일 초과수익(%p)
    "X_RS_STRONG_S": 8.0,
    "X_RS_STRONG_M": 5.0,
    "X_RS_OK_TH": 3.0,
    "X_RS_OK_S": 4.0,
    "X_RS_WEAK_TH": -7.0,
    "X_RS_WEAK_S": -7.0,
    "X_RS_WEAK_M": -4.0,
    "X_HIGH52_NEAR_TH": -3.0,       # 52주 고점 대비(%)
    "X_HIGH52_NEAR_S": 7.0,
    "X_HIGH52_NEAR_M": 7.0,
    "X_HIGH52_OK_TH": -10.0,
    "X_HIGH52_OK_M": 4.0,
    "X_MFI_IN_LO_TH": 55.0,         # 자금 유입 구간
    "X_MFI_IN_HI_TH": 80.0,
    "X_MFI_IN_M": 4.0,
    "X_MFI_HOT_TH": 85.0,
    "X_MFI_HOT_S": -5.0,
    "X_MFI_COLD_TH": 20.0,
    "X_MFI_COLD_S": -2.0,
    "X_GAP20_TH": 18.0,             # 20일선 과이격(%)
    "X_GAP20_S": -8.0,
    "X_VOL20_TH": 4.5,              # 일 변동성(%)
    "X_VOL20_S": -4.0,
    "X_LIQ_BAD_TH": 10.0,           # 20일 평균 거래대금(억) — 국내만
    "X_LIQ_BAD_S": -12.0,
    "X_LIQ_BAD_M": -8.0,
    "X_LIQ_BAD_L": -4.0,
    "X_LIQ_THIN_TH": 30.0,
    "X_LIQ_THIN_S": -5.0,
    "X_LIQ_THIN_M": -3.0,

    # =================================================================
    # 등급 판정 / 기간 타이브레이크
    # =================================================================
    "G_TIE_GAP_TH": 6.0,            # 1·2위 점수차가 이 이내면 시장 분위기로 결정
    "G_RISKON_HI_TH": 0.3,          # risk_on 이 이 이상 → 단기 우선
    "G_RISKON_LO_TH": -0.3,         # 이 이하 → 장기 우선
    "G_STRONG_TH": 70.0,            # 🟢 강력
    "G_GOOD_TH": 50.0,              # 🟡 양호
    "G_REASON_MAX": 4,              # 사유 표시 개수
}


def make_weights(overrides=None):
    """기본 가중치에 일부만 덮어쓴 새 dict 반환. 백테스트 스윕용.

    >>> w = make_weights({"S_VOL_SPIKE": 20.0})
    >>> w["S_VOL_SPIKE"], w["S_ALIGN_PERFECT"]
    (20.0, 25.0)
    """
    w = dict(DEFAULT_WEIGHTS)
    if overrides:
        unknown = set(overrides) - set(DEFAULT_WEIGHTS)
        if unknown:
            raise KeyError(f"알 수 없는 가중치 키: {sorted(unknown)}")
        w.update(overrides)
    return w


# 가중치만(기준값 _TH 제외) 골라내는 헬퍼 — 스윕 대상 목록 만들 때 사용
def tunable_keys():
    """점수 가감에 직접 쓰이는 키 목록 (기준값 `_TH`, 개수 제한 제외)."""
    return [k for k in DEFAULT_WEIGHTS
            if not k.endswith("_TH") and k not in ("G_REASON_MAX", "S_PENSION_DAYS_TH")]
