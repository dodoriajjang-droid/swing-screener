# -*- coding: utf-8 -*-
"""
🩺 데이터 수집 진단 (Diagnostics)
=====================================================================
왜 필요한가
  이 앱은 네이버 금융·KRX·야후 등 '비공식 스크래핑'에 크게 의존한다.
  기존 코드는 실패를 `except Exception: pass` 로 조용히 넘겼기 때문에,
  사이트 구조가 바뀌면 **에러 없이 빈 화면이 정상처럼** 표시됐다.
  투자 판단에 쓰는 도구에서 '데이터 없음'과 '수집 실패'가 구분되지 않는 건 위험하다.

무엇을 하나
  - 실패를 삼키던 자리에서 note() 를 호출해 (소스, 예외종류, 메시지, 시각) 을 남긴다.
  - 화면에는 render_badge() / render_panel() 로 "지금 몇 건 실패 중인지" 를 보여준다.

스레드 안전
  수집 함수 다수가 ThreadPoolExecutor 안에서 돌아간다. 워커 스레드에서는
  st.session_state 접근이 불안정하므로, 모듈 전역 deque + Lock 을 쓴다.
  (단일 사용자 로컬/개인용 전제. 여러 명이 붙는 배포라면 세션 분리가 필요하다.)
"""

import threading
from collections import Counter, deque
from datetime import datetime

MAX_EVENTS = 400

_LOCK = threading.Lock()
_EVENTS = deque(maxlen=MAX_EVENTS)
_COUNTS = Counter()          # (session_id, source) -> 횟수


def _session_id():
    """현재 Streamlit 세션 ID. 워커 스레드에는 컨텍스트가 없어 None 이 나온다.

    저장소는 프로세스 전역이라 여러 명이 접속하면 기록이 섞인다. 그래서 기록 시점에
    세션을 표시해 두고, 화면에는 '내 세션 + 스레드에서 난 것'만 보여준다.
    """
    try:
        from streamlit.runtime.scriptrunner import get_script_run_ctx
        ctx = get_script_run_ctx()
        return ctx.session_id if ctx is not None else None
    except Exception:
        return None


def note(source, err=None, detail="", level="warn"):
    """수집/파싱 실패 1건 기록.

    source : 실패한 지점 이름 (보통 함수명). 예: "get_krx_stocks"
    err    : 잡은 예외 객체 (없으면 None)
    detail : 추가 설명 (종목코드, URL 등)
    level  : "warn" (폴백으로 계속 진행) | "error" (해당 기능 사용 불가)
    """
    try:
        etype = type(err).__name__ if err is not None else "-"
        emsg = str(err)[:200] if err is not None else ""
        sid = _session_id()
        with _LOCK:
            _EVENTS.append({
                "시각": datetime.now().strftime("%H:%M:%S"),
                "지점": str(source),
                "종류": etype,
                "메시지": emsg,
                "상세": str(detail)[:120],
                "level": level,
                "_sid": sid,
            })
            _COUNTS[(sid, str(source))] += 1
    except Exception:
        # 진단 코드가 앱을 죽이면 안 된다 — 여기서만은 조용히 통과.
        pass


def _mine(sid, cur):
    """내 세션 것이거나, 스레드에서 나 세션을 알 수 없는 것(None)이면 내 것으로 본다."""
    return sid is None or cur is None or sid == cur


def events(limit=None):
    cur = _session_id()
    with _LOCK:
        out = [e for e in _EVENTS if _mine(e.get("_sid"), cur)]
    return out[-limit:] if limit else out


def counts():
    cur = _session_id()
    with _LOCK:
        c = Counter()
        for (sid, source), n in _COUNTS.items():
            if _mine(sid, cur):
                c[source] += n
    return dict(c)


def total():
    return sum(counts().values())


def clear():
    with _LOCK:
        _EVENTS.clear()
        _COUNTS.clear()


def top_sources(n=5):
    return Counter(counts()).most_common(n)


# ---------------------------------------------------------------------
# Streamlit 표출 (import 시점에 streamlit 이 없어도 모듈은 동작하도록 지연 import)
# ---------------------------------------------------------------------
def render_badge():
    """사이드바용 한 줄 요약. 실패가 없으면 초록, 있으면 건수와 상위 원인."""
    import streamlit as st
    t = total()
    if t == 0:
        st.caption("🩺 데이터 수집: ✅ 이상 없음")
        return
    tops = ", ".join(f"{s}({c})" for s, c in top_sources(3))
    st.caption(f"🩺 데이터 수집: ⚠️ **{t}건 실패** — {tops}")


def render_panel(expanded=False):
    """상세 패널. 어떤 수집 지점이 몇 번 실패했는지 + 최근 이벤트 목록."""
    import streamlit as st
    t = total()
    with st.expander(f"🩺 데이터 수집 진단 ({t}건 실패)" if t else "🩺 데이터 수집 진단 (이상 없음)",
                     expanded=expanded):
        if t == 0:
            st.success("이번 세션에서 감지된 수집 실패가 없습니다.")
            st.caption("※ 앱을 새로 켜면 기록이 초기화됩니다. 캐시가 살아 있으면 재수집 자체가 일어나지 않아 0건일 수 있습니다.")
            return
        st.caption(
            "아래는 **조용히 넘어갔던 실패**입니다. 화면에 데이터가 비어 보인다면 여기서 원인을 먼저 확인하세요. "
            "특정 지점이 반복 실패하면 해당 사이트의 구조가 바뀌었을 가능성이 큽니다."
        )
        try:
            import pandas as pd
            c = counts()
            st.dataframe(
                pd.DataFrame(sorted(c.items(), key=lambda kv: -kv[1]), columns=["수집 지점", "실패 횟수"]),
                use_container_width=True, hide_index=True, height=min(300, 40 + 35 * len(c)),
            )
            ev = events()
            st.markdown("**최근 실패 상세**")
            st.dataframe(pd.DataFrame(ev[::-1]).drop(columns=["level"], errors="ignore"),
                         use_container_width=True, hide_index=True, height=260)
        except Exception as e:
            st.write(counts())
            st.caption(f"(표 렌더 실패: {type(e).__name__})")
        if st.button("🧹 진단 기록 지우기", key="diag_clear"):
            clear()
            st.rerun()
