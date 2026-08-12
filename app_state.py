# -*- coding: utf-8 -*-
"""
💾 사용자 상태 저장 (App State)
=====================================================================
왜 필요한가
  기존에는 관심종목·재료일정·발굴기 이력을 작업 디렉터리의 JSON 파일에 직접 썼다.
  이 방식은 로컬 단일 사용자에게만 맞고, 배포 환경에서 두 가지가 깨진다.
    1) Streamlit Cloud 등은 파일시스템이 휘발성 → 재시작하면 관심종목이 사라진다.
    2) 여러 명이 접속하면 한 파일을 공유 → 남의 관심종목이 보인다.

무엇이 바뀌었나
  - **세션(st.session_state)이 원본**이다. 사용자마다 완전히 분리된다.
  - 로컬 파일은 '있으면 읽어와 seed 하고, 쓸 수 있으면 자동 저장'하는 보조 수단이다.
    (기존 watchlist.json / catalysts.json 을 쓰던 사용자는 그대로 이어서 쓴다)
  - 파일에 쓸 수 없는 환경이면 자동으로 꺼지고, 사용자가 **직접 내려받고/올리는**
    export / import 로 데이터를 지킬 수 있다. → render_backup_ui()

쓰는 법
    import app_state
    wl = app_state.load("watchlist", default=[])
    app_state.save("watchlist", wl)
    app_state.render_backup_ui("watchlist", "⭐ 관심종목")
"""

import json
import os

import streamlit as st

try:
    import diagnostics as diag
except Exception:      # 진단 모듈이 없어도 상태 저장은 동작해야 한다
    diag = None

# 컬렉션 이름 → 기존 파일명 (하위 호환)
FILES = {
    "watchlist": "watchlist.json",
    "catalysts": "catalysts.json",
    "finder_history": "finder_history.json",
}

_SS_PREFIX = "_state_"
_SEEDED = "_state_seeded_"
_AUTOSAVE = "_state_autosave"

# 앱이 이미 특정 session_state 키를 직접 읽고 쓰는 경우, 사본이 두 벌 생기지 않도록
# 그 키를 그대로 쓴다. (예: app.py 전반이 st.session_state.watchlist 를 직접 참조)
SS_KEYS = {
    "watchlist": "watchlist",          # app.py 전반
    "catalysts": "ac_catalysts",       # jaemini_alert_center.py 재료 트래커
}


def _ss_key(key):
    return SS_KEYS.get(key, _SS_PREFIX + key)


def _note(source, err=None, detail=""):
    if diag is not None:
        diag.note(source, err, detail)


def _path(key):
    return FILES.get(key, f"{key}.json")


def autosave_enabled():
    """로컬 파일 자동 저장 여부. 기본값은 '쓸 수 있으면 켬'."""
    if _AUTOSAVE not in st.session_state:
        st.session_state[_AUTOSAVE] = _probe_writable()
    return bool(st.session_state[_AUTOSAVE])


def set_autosave(flag):
    st.session_state[_AUTOSAVE] = bool(flag)


def _probe_writable():
    """작업 디렉터리에 실제로 쓸 수 있는지 1회 확인 (클라우드 판별용)."""
    probe = ".state_write_probe"
    try:
        with open(probe, "w", encoding="utf-8") as f:
            f.write("1")
        os.remove(probe)
        return True
    except Exception as e:
        _note("app_state._probe_writable", e, "로컬 파일 저장 불가 — 세션 저장만 사용")
        return False


def _read_file(key, default):
    p = _path(key)
    if not os.path.exists(p):
        return default
    try:
        with open(p, "r", encoding="utf-8") as f:
            data = json.load(f)
        if default is not None and not isinstance(data, type(default)):
            return default
        return data
    except Exception as e:
        _note(f"app_state.load[{key}]", e, p)
        return default


def _write_file(key, value):
    if not autosave_enabled():
        return False
    try:
        with open(_path(key), "w", encoding="utf-8") as f:
            json.dump(value, f, ensure_ascii=False, indent=2)
        return True
    except Exception as e:
        _note(f"app_state.save[{key}]", e, _path(key))
        set_autosave(False)       # 한 번 실패하면 이후엔 세션 저장만
        return False


def load(key, default=None):
    """세션에 있으면 세션 값을, 없으면 로컬 파일에서 1회 seed 해서 반환."""
    if default is None:
        default = []
    sk, seeded = _ss_key(key), _SEEDED + key
    if sk not in st.session_state:
        # seeded 플래그가 이미 있으면(= 사용자가 비운 것) 파일을 다시 읽지 않는다
        st.session_state[sk] = default if st.session_state.get(seeded) else _read_file(key, default)
        st.session_state[seeded] = True
    return st.session_state[sk]


def save(key, value):
    """세션에 저장하고, 가능하면 로컬 파일에도 기록. 반환: 파일 기록 성공 여부."""
    st.session_state[_ss_key(key)] = value
    st.session_state[_SEEDED + key] = True
    return _write_file(key, value)


def clear(key):
    st.session_state.pop(_ss_key(key), None)
    st.session_state.pop(_SEEDED + key, None)


# ---------------------------------------------------------------------
# 내보내기 / 불러오기 UI
# ---------------------------------------------------------------------
def render_backup_ui(key, label, default=None):
    """JSON 내려받기 + 올리기 UI. 파일 자동 저장이 불가능한 환경에서 유일한 보존 수단."""
    data = load(key, default if default is not None else [])
    auto = autosave_enabled()

    with st.expander(f"💾 {label} 백업 · 복원 ({len(data)}건)", expanded=False):
        if auto:
            st.caption(f"✅ 이 환경에서는 `{_path(key)}` 에 자동 저장됩니다. 아래 백업은 추가 안전장치입니다.")
        else:
            st.warning(
                "⚠️ 이 환경에서는 파일 자동 저장이 불가능합니다(클라우드 등). "
                "**브라우저를 새로고침하거나 앱이 재시작되면 사라집니다.** "
                "아래에서 JSON으로 내려받아 두었다가, 다음에 올려서 복원하세요.")

        c1, c2 = st.columns(2)
        with c1:
            st.download_button(
                f"⬇️ {label} 내려받기 (JSON)",
                data=json.dumps(data, ensure_ascii=False, indent=2).encode("utf-8"),
                file_name=_path(key), mime="application/json",
                use_container_width=True, key=f"dl_{key}", disabled=not data)
        with c2:
            up = st.file_uploader(f"⬆️ {label} 올리기", type=["json"], key=f"ul_{key}",
                                  label_visibility="collapsed")
            if up is not None:
                try:
                    loaded = json.loads(up.getvalue().decode("utf-8"))
                    if not isinstance(loaded, (list, dict)):
                        raise ValueError("JSON 최상위가 리스트/딕셔너리가 아닙니다")
                    mode = st.radio("복원 방식", ["기존에 추가(병합)", "기존을 덮어쓰기"],
                                    horizontal=True, key=f"ulmode_{key}")
                    if st.button("복원 실행", key=f"ulgo_{key}", type="primary"):
                        if mode.startswith("기존을") or not isinstance(data, list) or not isinstance(loaded, list):
                            merged = loaded
                        else:
                            merged = data + [x for x in loaded if x not in data]
                        save(key, merged)
                        st.success(f"✅ 복원 완료 — {len(merged)}건")
                        st.rerun()
                except Exception as e:
                    st.error(f"❌ 파일을 읽지 못했습니다: {type(e).__name__} — {e}")

        st.checkbox("이 폴더에 자동 저장", value=auto, key=f"as_{key}",
                    on_change=lambda: set_autosave(st.session_state[f"as_{key}"]),
                    help="끄면 세션 안에서만 유지됩니다(앱 종료 시 사라짐). 공용 PC에서는 꺼두세요.")
