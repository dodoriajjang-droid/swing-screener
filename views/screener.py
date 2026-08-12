# -*- coding: utf-8 -*-
"""🔎 종목 스크리너 — 찾는 방식(프리셋)만 바꿔가며 후보를 뽑는다.

[통합] 예전에는 조건으로 종목을 거르는 화면이 셋으로 나뉘어 있었다.
  · 🚀 단기 스윙 퀀트 스캐너   — 기술적 조건 체크박스
  · 💎 장기 우량주 & 가치주 발굴 — 위험 성향 → 세부 전략
  · 📉 낙폭과대 스캐너          — 고점 대비 낙폭
세 화면 모두 '조건으로 후보를 추려 같은 결과 카드로 보여준다'는 같은 일을 한다.
차이는 조건 세트뿐이라, 메뉴 세 개 대신 프리셋 세 개로 합쳤다.

각 프리셋의 조건과 판정 로직은 기존 화면 그대로다.

여기 합치지 않은 것
  · ⚡ 메가트렌드 · 🇰🇷 국민성장펀드 — 조건으로 거르는 게 아니라 AI가 후보를
    만들어 내는 방식이라 성격이 다르다. 억지로 같은 프리셋 체계에 넣으면
    어떤 프리셋은 조건을 고르고 어떤 프리셋은 AI를 기다리는 화면이 된다.
  · 🧪 전략 백테스트 — 후보를 '찾는' 일이 아니라 전략이 통했는지 '검증'하는 일.
"""
from core import *

import views.swing_scanner as _swing
import views.value_finder as _value
import views.drawdown_scanner as _drawdown

PRESETS = {
    "🚀 단기 스윙": ("정배열·거래량·수급 등 기술적 조건으로 오늘 살 만한 종목을 찾습니다.", _swing.scan_panel),
    "💎 장기 가치": ("PER·PBR·ROE·배당 같은 재무 지표로 오래 들고 갈 종목을 찾습니다.", _value.scan_panel),
    "📉 낙폭 반등": ("고점 대비 많이 빠진 종목 중 되돌림 가능성이 있는 후보를 찾습니다.", _drawdown.scan_panel),
}


def render(ctx):
    st.markdown("## 🔎 종목 스크리너")

    preset = st.radio("찾는 방식", list(PRESETS), horizontal=True,
                      key="screener_preset", label_visibility="collapsed")
    desc, panel = PRESETS[preset]
    st.caption(desc)
    st.divider()

    panel(ctx)
