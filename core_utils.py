# -*- coding: utf-8 -*-
"""
작은 공용 헬퍼  (core_utils.py)
=====================================================================
숫자/문자 변환, 클리핑 같은 최하위 유틸. 다른 계층에 의존하지 않는다.

계층 순서: constants → utils → data → ai → scoring → render
위 방향으로만 의존한다(순환 없음). core.py 가 전부를 합쳐 다시 내보낸다.
"""
from core_constants import *



def _su_amt(v):
    return f"{v:+,.0f}억"


def _num(s):
    """'8,367.43' / '+20,409' / '-0.53' / '2.23' → float. 실패 시 None."""
    if s is None:
        return None
    try:
        return float(str(s).replace(',', '').replace('+', '').replace('%', '').strip())
    except Exception as _dg_e:
        _diag_note("_num", _dg_e)
        return None


def _deep_find_number(obj, key_substrings, _depth=0):
    """[추가] 중첩 dict/list(JSON)에서 key 이름에 주어진 부분문자열이 들어간 첫 숫자값을 찾아 반환.
    네이버 API 응답의 정확한 필드명을 몰라도 '외국인/기관/개인' 같은 키를 자동 탐색하기 위함."""
    if _depth > 6 or obj is None:
        return None
    if isinstance(obj, dict):
        # 1) 이번 레벨에서 키 매칭 우선
        for k, v in obj.items():
            kl = str(k).lower()
            if any(s in kl for s in key_substrings) and isinstance(v, (int, float, str)):
                try:
                    n = float(str(v).replace(',', '').replace('+', '').replace('%', ''))
                    return n
                except Exception as _dg_e:
                    _diag_note("_deep_find_number", _dg_e)
                    pass
        # 2) 못 찾으면 하위로 재귀
        for v in obj.values():
            r = _deep_find_number(v, key_substrings, _depth + 1)
            if r is not None:
                return r
    elif isinstance(obj, list):
        for v in obj:
            r = _deep_find_number(v, key_substrings, _depth + 1)
            if r is not None:
                return r
    return None


def _to_eok(val):
    """순매매 값을 '억원' 정수로 정규화. 네이버 API가 원 단위(예: -1401600000000)면 억으로 환산.
    이미 억 단위(예: -14016)면 그대로 사용. 백만/천 단위 등 애매한 경우 자릿수로 추정."""
    if val is None:
        return None
    try:
        v = float(val)
    except Exception as _dg_e:
        _diag_note("_to_eok", _dg_e)
        return None
    a = abs(v)
    if a >= 1e11:          # 원 단위(조 단위) → 억으로
        return int(round(v / 1e8))
    if a >= 1e8:           # 원 단위(억~조) → 억으로
        return int(round(v / 1e8))
    if a >= 1e6:           # 백만원 단위로 들어온 경우 → 억(=100백만)
        return int(round(v / 1e2))
    return int(round(v))   # 이미 억 단위로 추정


def _nb_won(v):
    """가격 표기: 국내는 원, 미국(소수)도 자연스럽게."""
    try:
        v = float(v)
    except Exception:
        return str(v)
    if v >= 1000:
        return f"₩{v:,.0f}" if v == int(v) or v > 5000 else f"₩{v:,.0f}"
    return f"${v:,.2f}"


def _sign_of(x):
    try:
        return 1 if x > 0 else (-1 if x < 0 else 0)
    except Exception as _dg_e:
        _diag_note("_sign_of", _dg_e)
        return 0


def _chg_color(sign):
    return _UP_C if sign > 0 else (_DN_C if sign < 0 else "#64748b")


def _google_news_rss(query, limit=5):
    """구글 뉴스 RSS로 키워드 관련 최신 기사 수집(키 불필요, 차단 적음).
    반환: list[{title, link, date, source}]"""
    import xml.etree.ElementTree as ET
    from email.utils import parsedate_to_datetime
    q = (query or "").strip()
    if not q:
        return []
    try:
        url = ("https://news.google.com/rss/search?q=" + urllib.parse.quote(q)
               + "&hl=ko&gl=KR&ceid=KR:ko")
        res = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=5)
        if res.status_code != 200:
            return []
        root = ET.fromstring(res.content)
        out = []
        for it in root.iter("item"):
            title = (it.findtext("title") or "").strip()
            link = (it.findtext("link") or "").strip()
            if not title:
                continue
            src = ""
            src_el = it.find("source")
            if src_el is not None and src_el.text:
                src = src_el.text.strip()
            # 구글뉴스 제목은 거의 항상 "제목 - 언론사" 형태 → 끝의 언론사 제거
            if " - " in title:
                base, tail = title.rsplit(" - ", 1)
                title = base.strip()
                if not src:
                    src = tail.strip()
            date = ""
            pub = it.findtext("pubDate") or ""
            try:
                date = parsedate_to_datetime(pub).strftime("%Y-%m-%d")
            except Exception:
                date = pub[:16]
            out.append({"title": title.strip(), "link": link, "date": date, "source": src})
            if len(out) >= limit:
                break
        return out
    except Exception as _dg_e:
        _diag_note("_google_news_rss", _dg_e)
        return []


# ---------- 점수화 보조 ----------
def _f_num(x):
    try:
        return float(str(x).replace(",", "").replace("%", "").strip())
    except Exception as _dg_e:
        _diag_note("_f_num", _dg_e)
        return None


def _align_flags(tech):
    a = str(tech.get("배열상태", ""))
    return {"정배열": "정배열" in a, "골든": "골든크로스" in a, "역배열": "역배열" in a}


def _is_pos_flow(x):
    return "+" in str(x)


def _clip(v, lo=0.0, hi=100.0):
    return max(lo, min(hi, v))


# `from core_utils import *` 로 넘어갈 이름 (언더스코어 포함, 자동 생성)
_EXPORTED = [
    "_align_flags",
    "_chg_color",
    "_clip",
    "_deep_find_number",
    "_f_num",
    "_google_news_rss",
    "_is_pos_flow",
    "_nb_won",
    "_num",
    "_sign_of",
    "_su_amt",
    "_to_eok",
]

__all__ = [_n for _n in _EXPORTED if _n in globals()]
