# -*- coding: utf-8 -*-
"""
데이터 수집 · 파싱  (core_data.py)
=====================================================================
네이버 금융·KRX(pykrx)·야후·OpenDART·폴리마켓 등 외부 소스 접근과 파싱.
대부분 @st.cache_data 로 캐시된다.

계층 순서: constants → utils → data → ai → scoring → render
위 방향으로만 의존한다(순환 없음). core.py 가 전부를 합쳐 다시 내보낸다.
"""
from core_constants import *
from core_utils import *


def load_watchlist():
    return app_state.load("watchlist", [])

def save_watchlist(wl):
    app_state.save("watchlist", wl)

def _poly_parse_list(val):
    """outcomes/outcomePrices 가 JSON 문자열로 오는 경우를 안전하게 리스트로 변환."""
    if isinstance(val, list):
        return val
    if isinstance(val, str):
        try:
            return json.loads(val)
        except Exception as _dg_e:
            _diag_note("_poly_parse_list", _dg_e)
            return []
    return []

def _poly_num(x):
    try:
        return float(x)
    except Exception as _dg_e:
        _diag_note("_poly_num", _dg_e)
        return 0.0

@st.cache_data(ttl=300)
def fetch_polymarket_markets(search=None, limit=80):
    """
    활성/미마감 마켓을 24시간 거래량 순으로 가져온다.
    search 가 주어지면 질문 텍스트로 한 번 더 필터링.
    반환: list[dict] (질문, 확률, 거래량 등 정규화된 형태)
    """
    headers = {"User-Agent": "Mozilla/5.0", "Accept": "application/json"}
    params = {
        "active": "true",
        "closed": "false",
        "archived": "false",
        "order": "volume24hr",
        "ascending": "false",
        "limit": int(limit),
    }
    try:
        res = requests.get(f"{POLY_GAMMA}/markets", params=params,
                           headers=headers, timeout=12)
        res.raise_for_status()
        raw = res.json()
    except Exception as e:
        _diag_note("fetch_polymarket_markets", e)
        return {"error": f"{type(e).__name__}: {e}", "data": []}

    rows = []
    for m in raw:
        try:
            outcomes = _poly_parse_list(m.get("outcomes"))
            prices = _poly_parse_list(m.get("outcomePrices"))
            # 가장 대표적인 'Yes' 또는 첫 번째 결과의 확률
            yes_prob = None
            if outcomes and prices and len(outcomes) == len(prices):
                pair = dict(zip(outcomes, prices))
                if "Yes" in pair:
                    yes_prob = _poly_num(pair["Yes"]) * 100
                else:
                    yes_prob = _poly_num(prices[0]) * 100
            elif prices:
                yes_prob = _poly_num(prices[0]) * 100

            row = {
                "question": m.get("question") or m.get("title") or "(제목 없음)",
                "yes_prob": round(yes_prob, 1) if yes_prob is not None else None,
                "outcomes": outcomes,
                "prices": [round(_poly_num(p) * 100, 1) for p in prices],
                "volume24hr": _poly_num(m.get("volume24hr")),
                "volume": _poly_num(m.get("volume") or m.get("volumeNum")),
                "liquidity": _poly_num(m.get("liquidity") or m.get("liquidityNum")),
                "end_date": (m.get("endDate") or "")[:10],
                "slug": m.get("slug", ""),
                "category": m.get("category", ""),
            }
            rows.append(row)
        except Exception as _dg_e:
            _diag_note("fetch_polymarket_markets", _dg_e)
            continue

    if search:
        kw = [s.strip().lower() for s in search.split() if s.strip()]
        if kw:
            rows = [r for r in rows
                    if any(k in r["question"].lower() for k in kw)]
    return {"error": None, "data": rows}

@st.cache_data(ttl=86400, show_spinner=False)
def _gtx_translate_en_ko(text):
    """단일 문장 영→한 번역 (구글 무료 gtx 엔드포인트). 실패 시 원문 반환.
    스레드에서 호출되므로 st.cache_data를 직접 달지 않는다(상위 함수에서 캐시)."""
    t = (text or "").strip()
    if not t:
        return text
    # 이미 한글이 섞여 있으면 번역 불필요
    if re.search(r'[가-힣]', t):
        return text
    try:
        res = requests.get(
            "https://translate.googleapis.com/translate_a/single",
            params={"client": "gtx", "sl": "en", "tl": "ko", "dt": "t", "q": t},
            headers={"User-Agent": "Mozilla/5.0"},
            timeout=4,
        )
        if res.status_code == 200:
            data = res.json()
            # data[0] = [[번역문, 원문, ...], ...]  → 분할된 조각을 이어붙임
            parts = [seg[0] for seg in (data[0] or []) if seg and seg[0]]
            ko = "".join(parts).strip()
            return ko or text
    except Exception as _dg_e:
        _diag_note("_gtx_translate_en_ko", _dg_e)
        pass
    return text


@st.cache_data(ttl=86400, show_spinner=False)
def translate_poly_questions(questions, _api_key=None):
    """
    영문 질문/선택지 목록을 한국어로 일괄 번역.
    [변경] 항목별로 구글 무료 번역 엔드포인트를 병렬 호출한다.
      - 일부만 번역되고 나머지가 누락되던 문제(LLM 일괄 번역의 줄 누락/병합)를 근본 해결.
      - API 키 불필요. 결과는 하루(ttl) 캐시되어 이후 재호출 없음.
    반환: {원문: 한글번역} 딕셔너리. (실패 항목만 원문 유지)
    """
    uniq = [q for q in dict.fromkeys(questions) if q and q.strip()]
    if not uniq:
        return {}
    mapping = {}
    try:
        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as ex:
            for q, ko in zip(uniq, ex.map(_gtx_translate_en_ko, uniq)):
                mapping[q] = ko or q
    except Exception:
        for q in uniq:
            mapping[q] = _gtx_translate_en_ko(q)
    # 누락분은 원문으로 보강
    for q in uniq:
        mapping.setdefault(q, q)
    return mapping

@st.cache_data(ttl=86400)
def get_krx_etf_list():
    try:
        return fdr.StockListing('ETF/KR')
    except Exception:
        return pd.DataFrame()

@st.cache_data(ttl=3600)
def get_today_research_details():
    try:
        url = "https://finance.naver.com/research/company_list.naver"
        res = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=5)
        soup = BeautifulSoup(res.content.decode('euc-kr', 'replace'), 'html.parser')
        table = soup.find('table', {'class': 'type_1'})
        rows = []
        if table:
            trs = table.find_all('tr')
            for tr in trs:
                tds = tr.find_all('td')
                if len(tds) >= 5:
                    stock_name = tds[0].text.strip()
                    if not stock_name: continue
                    title_a = tds[1].find('a')
                    if not title_a: continue
                    real_title = title_a.text.strip()
                    real_link = "https://finance.naver.com/research/" + title_a['href']
                    real_broker = tds[2].text.strip()
                    real_date = tds[4].text.strip()
                    rows.append({"종목명": stock_name, "제목": real_title, "증권사": real_broker, "작성일": real_date, "원문링크": real_link})
        
        df = pd.DataFrame(rows[:30]) # 상위 30개만 파싱 (속도 및 차단 방지)
        if df.empty: return df

        def fetch_detail(row_tuple):
            link, title = row_tuple
            try:
                time.sleep(0.1)
                detail_res = requests.get(link, headers={'User-Agent': 'Mozilla/5.0'}, timeout=3)
                detail_soup = BeautifulSoup(detail_res.content.decode('euc-kr', 'replace'), 'html.parser')
                detail_text = detail_soup.get_text(separator=' ', strip=True)
                real_price = parse_target_price(detail_text)
                real_opinion = standardize_opinion(detail_text)
                change_status, change_pct = classify_tp_change(title, detail_text, real_price)
                return real_price, real_opinion, change_status, change_pct
            except Exception as _dg_e:
                _diag_note("fetch_detail", _dg_e)
                return 0, "N/A", "유지/신규", 0.0

        results = []
        link_title_pairs = list(zip(df['원문링크'], df['제목']))
        with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
            for r in executor.map(fetch_detail, link_title_pairs):
                results.append(r)
        
        df['목표가'] = [r[0] for r in results]
        df['투자의견'] = [r[1] for r in results]
        df['변동'] = [r[2] for r in results]
        df['변동률'] = [r[3] for r in results]
        return df
    except Exception:
        return pd.DataFrame()

@st.cache_data(ttl=3600)
def get_us_etf_summary(us_etfs):
    # 순차 yf.Ticker 호출 → yf.download 배치 1회로 변경 (요청 1번에 전 종목 병렬 수집)
    us_data = []
    tickers = list(us_etfs)
    if not tickers:
        return pd.DataFrame(us_data)
    try:
        data = yf.download(tickers, period="5d", group_by="ticker",
                           threads=True, progress=False)
    except Exception:
        return pd.DataFrame(us_data)
    for ticker in tickers:
        try:
            df = data[ticker] if len(tickers) > 1 else data
            close_s = df['Close'].dropna()
            if len(close_s) >= 2:
                close = close_s.iloc[-1]
                prev = close_s.iloc[-2]
                pct = ((close - prev) / prev) * 100
                vol_s = df['Volume'].dropna()
                vol = int(vol_s.iloc[-1]) if len(vol_s) else 0
                us_data.append({"티커": ticker, "현재가": f"${close:.2f}", "등락률": f"{pct:+.2f}%", "거래량": f"{vol:,}"})
        except Exception as _dg_e: _diag_note("get_us_etf_summary", _dg_e); pass
    return pd.DataFrame(us_data)

@st.cache_data(ttl=86400)
def get_nps_holdings(dart_key=""):
    targets = [('삼성전자', '005930'), ('SK하이닉스', '000660'), ('LG에너지솔루션', '373220'), ('삼성바이오로직스', '207940'), ('현대차', '005380'), ('기아', '000270'), ('셀트리온', '068270'), ('POSCO홀딩스', '005490'), ('NAVER', '035420'), ('KB금융', '105560'), ('신한지주', '055550'), ('삼성물산', '028260'), ('현대모비스', '012330'), ('LG화학', '051910'), ('카카오', '035720'), ('삼성SDI', '006400'), ('하나금융지주', '086790'), ('메리츠금융지주', '138040'), ('한국전력', '015760'), ('HMM', '011200'), ('KT&G', '033780'), ('우리금융지주', '316140'), ('기업은행', '024110')]
    nps_data = []
    # DART 키가 있으면 corp_code 매핑을 스레딩 전에 1회만 구축 (스레드별 중복 다운로드 방지)
    corp_map = get_dart_corp_map(dart_key) if dart_key else None

    def fetch_nps(target):
        name, code = target
        try:
            # [v-우회] FnGuide 차단 대응: DART(키 보유 시) → FnGuide → WiseReport 체인으로 조회
            r, src = _fetch_nps_stake_multi(code, dart_key=dart_key, corp_map=corp_map)
            if r and r["지분율"] is not None and r["지분율"] >= 4.0:
                return {"종목명": name, "티커": code, "보유비중": f"{r['지분율']:.2f}%", "비고": f"{src} 실시간"}
        except Exception as _dg_e: _diag_note("fetch_nps", _dg_e); pass
        return None
        
    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
        for r in executor.map(fetch_nps, targets):
            if r: nps_data.append(r)
            
    if nps_data:
        return pd.DataFrame(nps_data).sort_values('보유비중', ascending=False).reset_index(drop=True)
        
    # 실시간 파싱 실패 시: 가짜(하드코딩) 보유종목을 만들지 않고 '빈 결과'를 반환한다.
    #   (이전 버전은 하드코딩 더미를 돌려줬는데, 표 형태라 실제 국민연금 지분으로 오인될 위험이 커서 제거.
    #    화면에서는 빈 결과면 "데이터 없음" 경고를 띄운다.)
    return pd.DataFrame(columns=["종목명", "티커", "보유비중", "비고"])

@st.cache_data(ttl=86400 * 7)
def get_nps_us_portfolio():
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8'
    }
    
    try:
        url = "https://www.dataroma.com/m/holdings.php?m=NPS"
        res = requests.get(url, headers=headers, timeout=5)
        if res.status_code == 200:
            tables = pd.read_html(StringIO(res.text))
            df2 = tables[0]
            res_df = pd.DataFrame()
            res_df['종목명'] = df2.iloc[:, 1] if len(df2.columns) > 1 else df2['Stock']
            res_df['티커'] = df2['Stock'] if 'Stock' in df2.columns else df2.iloc[:, 0]
            res_df['포트폴리오 비중'] = df2['% of Portfolio'].astype(str) + "%" if '% of Portfolio' in df2.columns else "-"
            res_df['보유주식수'] = df2['Shares'] if 'Shares' in df2.columns else "-"
            res_df['가치(달러)'] = df2['Value'] if 'Value' in df2.columns else "-"
            res_df['비고'] = "Dataroma 실시간 스크래핑"
            if not res_df.empty: return res_df.head(30)
    except Exception as _dg_e: _diag_note("get_nps_us_portfolio", _dg_e); pass

    # 실시간 스크래핑 실패 시: 가짜(하드코딩) 13F를 만들지 않고 '빈 결과'를 반환한다.
    #   (정밀해 보이는 더미 수치가 실제 포트폴리오로 오인될 위험이 커서 제거. 화면에서 "데이터 없음" 경고.)
    return pd.DataFrame(columns=["종목명", "티커", "포트폴리오 비중", "보유주식수", "가치(달러)", "비고"])

def _extract_nps_stake_from_html(html_text):
    """주주 테이블 HTML에서 국민연금 지분율(%)·표기명 추출.
    반환: {"지분율": float, "주주표기": str} / {"지분율": None, ...}(정상 페이지·국민연금 미표기) / None(파싱 불가)"""
    try:
        tables = pd.read_html(StringIO(html_text))
    except Exception as _dg_e:
        _diag_note("_extract_nps_stake_from_html", _dg_e)
        return None
    parsed_any = False
    for df in tables:
        if not any('주주' in str(c) for c in df.columns):
            continue
        parsed_any = True
        row_mask = df.apply(lambda r: r.astype(str).str.contains('국민연금', na=False).any(), axis=1)
        match = df[row_mask]
        if match.empty:
            continue
        # 지분율 컬럼 선택: '변동지분'·'보유주식수' 같은 함정 컬럼 제외 (WiseReport 대응)
        pct_cols = [c for c in df.columns
                    if any(k in str(c) for k in ('지분', '비율', '보유'))
                    and '변동' not in str(c) and '주식수' not in str(c)]
        if not pct_cols:
            continue
        val = str(match[pct_cols[-1]].iloc[0]).replace('%', '').replace(',', '').strip()
        try:
            pct = float(val)
        except ValueError as _dg_e:
            _diag_note("_extract_nps_stake_from_html", _dg_e)
            continue
        disp = ""
        for c in df.columns:
            cell = str(match[c].iloc[0])
            if '국민연금' in cell:
                disp = cell.strip()
                break
        return {"지분율": pct, "주주표기": disp}
    return {"지분율": None, "주주표기": ""} if parsed_any else None

@st.cache_data(ttl=86400)
def get_dart_corp_map(dart_key):
    """DART 고유번호(corp_code) ↔ 종목코드 매핑. corpCode.xml(zip) 다운로드 후 파싱. 실패 시 빈 dict."""
    if not dart_key:
        return {}
    try:
        import zipfile
        import io as _io
        import xml.etree.ElementTree as _ET
        r = requests.get("https://opendart.fss.or.kr/api/corpCode.xml",
                         params={"crtfc_key": dart_key}, timeout=15)
        if r.status_code != 200 or not r.content[:2] == b'PK':   # zip 시그니처 확인 (오류 시 XML 에러문 반환됨)
            return {}
        with zipfile.ZipFile(_io.BytesIO(r.content)) as zf:
            with zf.open(zf.namelist()[0]) as f:
                tree = _ET.parse(f)
        cmap = {}
        for el in tree.getroot().iter('list'):
            stk = (el.findtext('stock_code') or '').strip()
            if stk:
                cmap[stk.zfill(6)] = (el.findtext('corp_code') or '').strip()
        return cmap
    except Exception as _dg_e:
        _diag_note("get_dart_corp_map", _dg_e)
        return {}

def _fetch_nps_stake_dart(code, dart_key, corp_map=None):
    """DART 오픈API 대량보유 상황보고(majorstock)에서 국민연금 최신 보고 지분율 조회.
    반환: {"지분율","주주표기","기준일"} / {"지분율": None}(보고 없음) / None(호출 실패·키 오류)"""
    try:
        cmap = corp_map if corp_map is not None else get_dart_corp_map(dart_key)
        corp_code = cmap.get(str(code).zfill(6))
        if not corp_code:
            return None
        r = requests.get("https://opendart.fss.or.kr/api/majorstock.json",
                         params={"crtfc_key": dart_key, "corp_code": corp_code}, timeout=7)
        j = r.json()
        if j.get("status") == "013":   # 조회된 데이터 없음 (대량보유 보고 자체가 없는 회사)
            return {"지분율": None, "주주표기": "", "기준일": ""}
        if j.get("status") != "000":
            return None
        rows = [x for x in j.get("list", []) if '국민연금' in str(x.get("repror", ""))]
        if not rows:
            return {"지분율": None, "주주표기": "", "기준일": ""}
        rows.sort(key=lambda x: str(x.get("rcept_no", "")), reverse=True)   # 최신 보고 우선
        top = rows[0]
        pct = float(str(top.get("stkrt", "")).replace(",", "").strip())
        return {"지분율": pct, "주주표기": str(top.get("repror", "")).strip(),
                "기준일": str(top.get("rcept_dt", "")).strip()}
    except Exception as _dg_e:
        _diag_note("_fetch_nps_stake_dart", _dg_e)
        return None

def _fetch_nps_stake_multi(code, dart_key="", corp_map=None):
    """소스 체인 순회. 반환: (결과 dict, 소스명) 또는 (None, None).
    지분율이 확인되면 즉시 반환, '미표기'는 다른 소스도 확인 후 판단."""
    none_result, none_src = None, None
    if dart_key:
        r = _fetch_nps_stake_dart(code, dart_key, corp_map)
        if r is not None:
            if r["지분율"] is not None:
                return r, "DART 공시"
            none_result, none_src = r, "DART 공시"
    for src_name, url_tpl, referer in NPS_STAKE_SOURCES:
        try:
            headers = dict(_NPS_SCRAPE_HEADERS_BASE, Referer=referer)
            res = requests.get(url_tpl.format(code=code), headers=headers, timeout=7)
            if res.status_code != 200:
                continue
            parsed = _extract_nps_stake_from_html(res.text)
            if parsed is None:
                continue
            if parsed["지분율"] is not None:
                return parsed, src_name
            if none_result is None:
                none_result, none_src = parsed, src_name
        except Exception as _dg_e:
            _diag_note("_fetch_nps_stake_multi", _dg_e)
            continue
    if none_result is not None:
        return none_result, none_src
    return None, None

@st.cache_data(ttl=1800)
def search_nps_holding(code, name="", dart_key=""):
    """단일 종목의 국민연금 지분율을 실시간 조회 (DART → FnGuide → WiseReport 체인).
    반환:
      {"종목명","티커","지분율"(float),"주주표기","출처","기준일"} : 지분 확인됨
      {"종목명","티커","지분율": None, "출처": 응답한 소스} : 소스는 응답했으나 국민연금 미표기(지분 없음 또는 5% 미만 가능성)
      None : 모든 소스 요청 실패(차단/타임아웃)"""
    r, src = _fetch_nps_stake_multi(code, dart_key=dart_key)
    if r is None:
        return None
    return {"종목명": name or code, "티커": code, "지분율": r["지분율"],
            "주주표기": r.get("주주표기", ""), "출처": src, "기준일": r.get("기준일", "")}

@st.cache_data(ttl=86400)
def get_krx_name_code_list():
    """종목명 검색용 KRX 전체 상장사 (코드·종목명) 목록. 실패 시 빈 DF 반환."""
    try:
        df = fdr.StockListing('KRX')
        if df is not None and not df.empty and 'Code' in df.columns and 'Name' in df.columns:
            out = df[['Code', 'Name']].dropna().copy()
            out['Code'] = out['Code'].astype(str).str.zfill(6)
            out['Name'] = out['Name'].astype(str)
            return out.reset_index(drop=True)
    except Exception as _dg_e:
        _diag_note("get_krx_name_code_list", _dg_e)
        pass
    return pd.DataFrame(columns=['Code', 'Name'])


@st.cache_data(ttl=1800)
def get_us_sector_etfs():
    # [v7.0] 하드코딩 더미 → yfinance 실데이터로 교체 (전일 종가 대비 등락률)
    sectors = [
        ("기술(Technology)", "XLK"), ("금융(Financials)", "XLF"),
        ("헬스케어(Healthcare)", "XLV"), ("에너지(Energy)", "XLE"),
        ("임의소비재(Consumer)", "XLY"), ("필수소비재(Staples)", "XLP"),
        ("산업재(Industrials)", "XLI"), ("반도체(Semicon)", "SMH"),
        ("커뮤니케이션(Comm)", "XLC"), ("유틸리티(Utilities)", "XLU"),
    ]
    def fetch_one(item):
        name, tk = item
        try:
            h = yf.Ticker(tk).history(period="5d")
            if len(h) >= 2:
                close = float(h['Close'].iloc[-1])
                pct = (close / float(h['Close'].iloc[-2]) - 1) * 100
                return {"섹터": name, "ETF": tk, "현재가": round(close, 2), "등락률": round(pct, 2)}
        except Exception as _dg_e:
            _diag_note("fetch_one", _dg_e)
            pass
        return None
    rows = []
    try:
        with concurrent.futures.ThreadPoolExecutor(max_workers=10) as ex:
            for r in ex.map(fetch_one, sectors):
                if r: rows.append(r)
    except Exception as _dg_e:
        _diag_note("get_us_sector_etfs", _dg_e)
        pass
    if rows:
        return pd.DataFrame(rows).sort_values('등락률', ascending=False).reset_index(drop=True)
    # 통신 실패 시 안전 폴백 (값 없음 표시)
    return pd.DataFrame({'섹터': [s[0] for s in sectors], 'ETF': [s[1] for s in sectors],
                         '현재가': [0] * len(sectors), '등락률': [0.0] * len(sectors)})


@st.cache_data(ttl=600)
def get_overnight_us_market():
    """간밤 미국 주요 지수·VIX·환율 스냅샷 (전일 대비 %)."""
    targets = [("나스닥", "^IXIC"), ("S&P500", "^GSPC"), ("다우", "^DJI"),
               ("VIX(공포지수)", "^VIX"), ("원/달러", "KRW=X")]
    out = []
    def fetch(item):
        label, tk = item
        try:
            h = yf.Ticker(tk).history(period="5d")
            if len(h) >= 2:
                last = float(h['Close'].iloc[-1]); prev = float(h['Close'].iloc[-2])
                pct = (last / prev - 1) * 100 if prev else 0
                return {"label": label, "ticker": tk, "value": last, "pct": pct}
        except Exception as _dg_e:
            _diag_note("fetch", _dg_e)
            pass
        return None
    try:
        with concurrent.futures.ThreadPoolExecutor(max_workers=5) as ex:
            for r in ex.map(fetch, targets):
                if r: out.append(r)
    except Exception as _dg_e:
        _diag_note("get_overnight_us_market", _dg_e)
        pass
    order = {t[1]: i for i, t in enumerate(targets)}
    out.sort(key=lambda x: order.get(x['ticker'], 99))
    return out

def get_economic_events(year, month):
    """[추가] 해당 연·월의 주요 경제지표 일정을 {일: [(label, css_class), ...]} 형태로 반환.
    [확정] FOMC·한은 금통위·ECB·BOJ(각국 중앙은행 공식 일정, 결정은 회의 2일차) / 미 CPI·고용(BLS 확정) / FOMC 의사록(회의 약 3주 후).
    [추정] PCE·소매판매·ISM·한국 CPI·중국 PMI·한국 수출입 — 통상 발표 시기 기준. 기관이 매월 확정하므로 실제 날짜는 1~2일 다를 수 있음.
    실제 자동 수집은 환경 제약으로 어려워, 확정 일정은 직접 입력하고 추정 항목은 명시한다.
    ※ css_class는 캘린더 페이지 스타일과 호환되도록 기존 4종(fomc/cpi/jobs/bok)만 재사용한다."""
    events = {}
    def _add(day, label, cls):
        if day:
            events.setdefault(day, []).append((label, cls))

    def _nth_bday(y, m, n):
        """해당 월의 n번째 영업일(주말 제외, 공휴일 미반영) 일자. 추정용."""
        cnt = 0
        for d in range(1, 29):
            try:
                if datetime(y, m, d).weekday() < 5:
                    cnt += 1
                    if cnt == n:
                        return d
            except Exception:
                break
        return None

    if year != 2026:
        return events

    # ───────── 美 통화정책 ─────────
    # FOMC 금리결정일 (회의 2일차, 공식 확정)
    fomc_2026 = {1: [28], 3: [18], 4: [29], 6: [17], 7: [29], 9: [16], 10: [28], 12: [9]}
    for d in fomc_2026.get(month, []):
        _add(d, "🏛️ 🇺🇸FOMC 금리결정", "evt-econ-fomc")
    # FOMC 의사록 (회의 약 3주 후 수요일, 확정)
    fomc_minutes_2026 = {2: 18, 4: 8, 5: 20, 7: 8, 8: 19, 10: 7, 11: 18, 12: 30}
    if month in fomc_minutes_2026:
        _add(fomc_minutes_2026[month], "📝 🇺🇸FOMC 의사록", "evt-econ-fomc")

    # ───────── 美 물가 ─────────
    # CPI (BLS 공식 확정 2026) — 1월은 셧다운으로 2/13 연기됐으나 표준 일정 사용
    cpi_2026 = {1: 13, 2: 11, 3: 11, 4: 10, 5: 12, 6: 10, 7: 14, 8: 12, 9: 11, 10: 14, 11: 10, 12: 10}
    if month in cpi_2026:
        _add(cpi_2026[month], "📊 🇺🇸CPI 물가", "evt-econ-cpi")
    # PCE 물가 (연준 선호 지표, 통상 월말·추정)
    pce_2026 = {1: 30, 2: 27, 3: 27, 4: 30, 5: 29, 6: 26, 7: 31, 8: 28, 9: 25, 10: 30, 11: 25, 12: 23}
    if month in pce_2026:
        _add(pce_2026[month], "📈 🇺🇸PCE 물가(연준선호)", "evt-econ-cpi")

    # ───────── 美 실물경기 ─────────
    # 고용지표(비농업, BLS 공식 확정 2026)
    jobs_2026 = {1: 9, 2: 6, 3: 6, 4: 3, 5: 8, 6: 5, 7: 2, 8: 7, 9: 4, 10: 2, 11: 6, 12: 4}
    if month in jobs_2026:
        _add(jobs_2026[month], "👷 🇺🇸고용지표", "evt-econ-jobs")
    # ISM 제조업 PMI (통상 1영업일·추정)
    _add(_nth_bday(year, month, 1), "🏭 🇺🇸ISM 제조업 PMI", "evt-econ-jobs")
    # 소매판매 (통상 월 중순·추정)
    retail_2026 = {1: 15, 2: 17, 3: 16, 4: 15, 5: 15, 6: 16, 7: 16, 8: 14, 9: 16, 10: 15, 11: 17, 12: 15}
    if month in retail_2026:
        _add(retail_2026[month], "🛒 🇺🇸소매판매", "evt-econ-jobs")

    # ───────── 韓 ─────────
    # 한은 금통위 통화정책방향 결정회의 (2026 공식 확정)
    bok_2026 = {1: 15, 2: 26, 4: 10, 5: 28, 7: 16, 8: 27, 10: 22, 11: 26}
    if month in bok_2026:
        _add(bok_2026[month], "🏦 🇰🇷한은 금통위", "evt-econ-bok")
    # 한국 소비자물가(CPI) (통계청, 통상 월초 2영업일·추정)
    _add(_nth_bday(year, month, 2), "📊 🇰🇷소비자물가(CPI)", "evt-econ-cpi")
    # 한국 수출입동향 (관세청, 매월 1일) — 수출 주도 경제, KOSPI 직접 동인
    _add(1, "🚢 🇰🇷수출입동향", "evt-econ-jobs")

    # ───────── 글로벌(韓 영향 큰 일정) ─────────
    # ECB 통화정책회의 (2일차 결정, 2026 공식 확정)
    ecb_2026 = {3: 19, 4: 30, 6: 11, 7: 23, 9: 10, 10: 29, 12: 17}
    if month in ecb_2026:
        _add(ecb_2026[month], "🏛️ 🇪🇺ECB 통화정책", "evt-econ-fomc")
    # BOJ 금융정책결정회의 (2일차 결정, 2026 공식 확정) — 엔/원 환율·엔캐리 민감
    boj_2026 = {1: 23, 3: 19, 4: 28, 6: 16, 7: 31, 9: 18, 10: 30, 12: 18}
    if month in boj_2026:
        _add(boj_2026[month], "🏯 🇯🇵BOJ 금융정책", "evt-econ-fomc")
    # 중국 제조업 PMI (NBS 월말/차이신 월초, 통상 1일·추정) — 수출 수요 선행
    _add(1, "🏭 🇨🇳제조업 PMI", "evt-econ-jobs")

    return events


@st.cache_data(ttl=3600)
def analyze_theme_trends():
    """국내 대표 섹터 ETF의 1·3·6개월 수익률을 실측해 섹터 순환매 분석용 DataFrame 반환.
       컬럼: 테마, 1M수익률, 3M수익률, 6M수익률 (단위: %)"""
    sector_etfs = {
        "반도체": "091160",
        "2차전지": "305720",
        "자동차": "091180",
        "은행": "091170",
        "증권": "102970",
        "건설": "117700",
        "에너지화학": "117460",
        "철강": "117680",
        "헬스케어": "266420",
        "미디어/엔터": "266360",
        "기계장비": "102960",
        "운송": "140710",
    }
    end = datetime.now()
    start = end - timedelta(days=240)

    def _calc(item):
        name, c = item
        try:
            df = fdr.DataReader(c, start.strftime('%Y-%m-%d'), end.strftime('%Y-%m-%d'))
            if df is None or df.empty or 'Close' not in df.columns:
                return None
            s = df['Close'].dropna()
            if len(s) < 5:
                return None
            last = float(s.iloc[-1])
            def _ret(days):
                target = s.index[-1] - pd.Timedelta(days=days)
                past = s[s.index <= target]
                if past.empty:
                    past = s
                base = float(past.iloc[0]) if past is s else float(past.iloc[-1])
                return round((last / base - 1) * 100, 2) if base > 0 else 0.0
            return {"테마": name, "1M수익률": _ret(30), "3M수익률": _ret(90), "6M수익률": _ret(180)}
        except Exception as _dg_e:
            _diag_note("_calc", _dg_e)
            return None

    rows = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as executor:
        for r in executor.map(_calc, list(sector_etfs.items())):
            if r:
                rows.append(r)
    return pd.DataFrame(rows)


@st.cache_data(ttl=3600)
def _parse_ipo_enddate(s):
    """청약일정 문자열에서 종료 날짜를 파싱 (예: '26.05.22~05.26' → 2026-05-26)."""
    s = str(s).strip()
    full = re.findall(r'(\d{2,4})[.\-/](\d{1,2})[.\-/](\d{1,2})', s)
    if not full:
        return None
    y, m, d = full[0]
    y = int(y); y = (2000 + y) if y < 100 else y
    try:
        start = datetime(y, int(m), int(d))
    except Exception as _dg_e:
        _diag_note("_parse_ipo_enddate", _dg_e)
        return None
    end = start
    rng = re.search(r'[~∼\-]\s*(?:(\d{1,2})[.\-/])?(\d{1,2})\s*$', s)
    if rng:
        em, ed = rng.groups()
        try:
            end = datetime(y, int(em) if em else int(m), int(ed))
        except Exception:
            end = start
    return end


def _clean_ipo_df(df):
    """IPO 표 후처리: 가비지 제거 + 컬럼 검증 + 공모가 포맷 + 다가오는 일정 정렬/필터 + 중복 제거."""
    if df is None or df.empty:
        return pd.DataFrame()
    df = df.copy()
    base_cols = ['시장', '종목명', '청약일정', '상장일', '공모가', '주관사', '경쟁률', '업종']
    for c in base_cols:
        if c not in df.columns:
            df[c] = '-'
    df = df[base_cols]
    for c in base_cols:
        df[c] = df[c].fillna('-').astype(str).str.strip().replace({'nan': '-', 'None': '-', 'NaN': '-', '': '-'})

    # 1) 가비지 행 제거 (종목명이 안내문장)
    df = df[df['종목명'].str.len().between(1, 25)]
    df = df[~df['종목명'].str.contains('공모함|수요예측|기관투자|파악|결정됨|청약을|투자자의', na=False)]

    # 2) 청약일정 검증 — 날짜 형태가 아니면(예: 경쟁률 '747:1') '-' 처리
    def valid_date(s):
        s = str(s)
        if re.search(r'\d{1,2}\s*:\s*1', s):      # 경쟁률 패턴
            return '-'
        if re.search(r'\d{1,4}[.\-/]\d{1,2}', s):  # 날짜 패턴
            return s
        return '-'
    df['청약일정'] = df['청약일정'].apply(valid_date)
    df['상장일'] = df['상장일'].apply(lambda x: x if (re.search(r'\d{1,4}[.\-/]\d{1,2}', str(x)) or '미정' in str(x)) else '-')

    # 3) 공모가 포맷 (숫자만 → '12,300원', 범위 → '10,000~12,000원')
    def clean_price(v):
        s = str(v).strip()
        if not s or s == '-':
            return '-'
        if re.search(r'결정|파악|수요|공모함|기관|투자자', s) or re.search(r'[가-힣]{4,}', s):
            return '-'
        nums = re.findall(r'\d[\d,]*', s)
        if not nums:
            return '-'
        def fmt(n):
            n = n.replace(',', '')
            return f"{int(n):,}" if n.isdigit() else None
        a = fmt(nums[0]); b = fmt(nums[1]) if len(nums) > 1 else None
        if a and b and a != b:
            return f"{a}~{b}원"
        return f"{a}원" if a else '-'
    df['공모가'] = df['공모가'].apply(clean_price)

    # 4) 종목명 중복 제거 (실데이터 많은 행 우선)
    def score(row):
        return sum(1 for c in ['청약일정', '상장일', '공모가', '주관사', '경쟁률', '업종']
                   if str(row[c]).strip() not in ('-', '', 'nan'))
    df['_score'] = df.apply(score, axis=1)
    df = (df.sort_values('_score', ascending=False)
            .drop_duplicates(subset=['종목명'], keep='first')
            .drop(columns=['_score']))

    # 5) 날짜 파싱 → 다가오는(또는 최근) 일정만, 빠른 순 정렬
    df['_end'] = df['청약일정'].apply(_parse_ipo_enddate)
    today = datetime.now()
    recent_or_future = df[df['_end'].notna() & (df['_end'] >= today - timedelta(days=5))]
    if len(recent_or_future) >= 1:
        dated = recent_or_future.sort_values('_end', ascending=True)           # 다가오는 순
        undated = df[df['_end'].isna()]
        out = pd.concat([dated, undated])
    else:
        # 다가오는 게 없으면(소스에 과거만 있으면) 최근 날짜 순으로라도 보여줌
        out = df.sort_values('_end', ascending=False, na_position='last')
    out = out.drop(columns=['_end']).reset_index(drop=True)
    return out.head(20)


@st.cache_data(ttl=3600)
def get_naver_ipo_data():
    # [v7.0] 표 기반(38.co.kr → 네이버 read_html) 우선, _clean_ipo_df로 정제 후 반환.

    def priority_pick(cols, cands, exclude=None):
        for cand in cands:                       # 우선순위 순
            for c in cols:
                if exclude and any(x in c for x in exclude):
                    continue
                if cand in c:
                    return c
        return None

    # ── 소스 A: 38커뮤니케이션 공모청약 일정 ──
    try:
        url = "http://www.38.co.kr/html/fund/index.htm?o=k"
        res = requests.get(url, headers={'User-Agent': 'Mozilla/5.0'}, timeout=5)
        res.encoding = 'euc-kr'
        tables = pd.read_html(StringIO(res.text))
        for t in tables:
            cols = [str(c) for c in t.columns]
            if not any(('기업명' in c or '종목명' in c) for c in cols):
                continue
            t = t.copy(); t.columns = cols
            name_c = priority_pick(cols, ['기업명', '종목명'])
            if not name_c:
                continue
            res_df = pd.DataFrame()
            res_df['종목명'] = t[name_c]
            res_df['시장'] = '-'
            # 청약일정: '경쟁률/률' 들어간 컬럼은 제외하고 날짜 컬럼만
            sub_c = priority_pick(cols, ['공모청약일', '공모주일정', '청약일정', '청약일', '청약', '일정'], exclude=['경쟁', '률'])
            res_df['청약일정'] = t[sub_c] if sub_c else '-'
            res_df['상장일'] = (lambda c: t[c] if c else '-')(priority_pick(cols, ['상장일', '상장'], exclude=['주가', '수익']))
            res_df['공모가'] = (lambda c: t[c] if c else '-')(priority_pick(cols, ['확정공모가', '공모가', '희망공모가']))
            res_df['주관사'] = (lambda c: t[c] if c else '-')(priority_pick(cols, ['주간사', '주관사']))
            res_df['경쟁률'] = (lambda c: t[c] if c else '-')(priority_pick(cols, ['청약경쟁률', '경쟁률']))
            res_df['업종'] = (lambda c: t[c] if c else '-')(priority_pick(cols, ['업종', '업태']))
            cleaned = _clean_ipo_df(res_df)
            if not cleaned.empty:
                return cleaned
    except Exception as _dg_e:
        _diag_note("get_naver_ipo_data", _dg_e)
        pass

    # ── 소스 B: 네이버 IPO 표 ──
    try:
        url = "https://finance.naver.com/sise/ipo.naver"
        res = requests.get(url, headers={'User-Agent': 'Mozilla/5.0'}, timeout=5)
        html_text = res.content.decode('euc-kr', 'replace')
        tables = pd.read_html(StringIO(html_text))
        for t in tables:
            t_str = t.to_string()
            if '공모가' in t_str and ('청약' in t_str or '상장일' in t_str):
                cols = [str(c) for c in t.columns]
                t = t.copy(); t.columns = cols
                name_col = priority_pick(cols, ['종목', '기업', '회사']) or cols[0]
                t = t.dropna(subset=[name_col]).copy()
                t = t[t[name_col].astype(str) != str(name_col)]

                def extract_market(x):
                    x = str(x).replace(' ', '')
                    for m in ['코스닥', '유가증권', '코넥스']:
                        if x.startswith(m):
                            return m
                    return '-'
                def clean_name(x):
                    x = str(x).strip()
                    for m in ['코스닥', '유가증권', '코넥스']:
                        if x.startswith(m):
                            return x[len(m):].strip()
                    return x

                res_df = pd.DataFrame()
                res_df['시장'] = t[name_col].apply(extract_market)
                res_df['종목명'] = t[name_col].apply(clean_name)
                sub_c = priority_pick(cols, ['공모청약일', '청약일', '청약', '일정'], exclude=['경쟁', '률'])
                res_df['청약일정'] = t[sub_c] if sub_c else '-'
                res_df['상장일'] = (lambda c: t[c] if c else '-')(priority_pick(cols, ['상장일']))
                res_df['공모가'] = (lambda c: t[c] if c else '-')(priority_pick(cols, ['확정공모가', '공모가']))
                res_df['주관사'] = (lambda c: t[c] if c else '-')(priority_pick(cols, ['주관', '주간']))
                res_df['경쟁률'] = (lambda c: t[c] if c else '-')(priority_pick(cols, ['경쟁률']))
                res_df['업종'] = (lambda c: t[c] if c else '-')(priority_pick(cols, ['업종']))
                cleaned = _clean_ipo_df(res_df)
                if not cleaned.empty:
                    return cleaned
    except Exception as _dg_e:
        _diag_note("get_naver_ipo_data", _dg_e)
        pass

    return pd.DataFrame()


@st.cache_data(ttl=86400)
def get_dividend_portfolio(ex_rate):
    # =========================================================
    # [공용] yfinance 견고 수집기 : (현재가, 연간배당금, 이름) 반환
    #   - Yahoo 차단/지연 대비 세션 위장 + 다중 폴백
    #   - 연간배당금은 "최근 12개월 실배당 합계"를 최우선으로 사용
    # =========================================================
    def _yf_fetch_one(ticker_code):
        try:
            import yfinance as yf
        except Exception as _dg_e:
            _diag_note("_yf_fetch_one", _dg_e)
            return ticker_code, 0.0, 0.0, ticker_code, "—"

        t = None
        try:
            sess = requests.Session()
            sess.headers.update({'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'})
            t = yf.Ticker(ticker_code, session=sess)
        except Exception:
            try:
                t = yf.Ticker(ticker_code)
            except Exception as _dg_e:
                _diag_note("_yf_fetch_one", _dg_e)
                return ticker_code, 0.0, 0.0, ticker_code, "—"

        price = 0.0
        annual_div = 0.0
        name = ticker_code
        freq = "—"   # 배당 주기 (월/분기/반기/연배당) — 아래 배당내역에서 추정

        # 1) 현재가 (fast_info → info → 최근 종가 순)
        try:
            fi = t.fast_info
            price = float(fi.get('lastPrice') or fi.get('last_price') or 0) or 0.0
        except Exception:
            price = 0.0

        info = {}
        try:
            info = t.info or {}
        except Exception:
            info = {}

        if not price:
            price = float(info.get('currentPrice') or info.get('regularMarketPrice')
                          or info.get('previousClose') or 0) or 0.0
        if not price:
            try:
                h = t.history(period="5d")
                if not h.empty:
                    price = float(h['Close'].dropna().iloc[-1])
            except Exception as _dg_e:
                _diag_note("_yf_fetch_one", _dg_e)
                pass

        name = info.get('shortName') or info.get('longName') or ticker_code

        # 2) 연간 배당금 — 최근 12개월 실지급 배당 합계 (가장 신뢰도 높음)
        try:
            divs = t.dividends
            if divs is not None and len(divs) > 0:
                idx = divs.index
                try:
                    cutoff = pd.Timestamp.now(tz=idx.tz) - pd.Timedelta(days=365)
                except Exception:
                    cutoff = pd.Timestamp.now() - pd.Timedelta(days=365)
                recent = divs[idx >= cutoff]
                if len(recent) > 0:
                    annual_div = float(recent.sum())
                    # 최근 12개월 '실제 지급 횟수 + 지급 월'로 배당 주기 추정
                    try:
                        n_pay = int(len(recent))
                        months = sorted(set(int(m) for m in recent.index.month))
                        mtxt = "·".join(str(m) for m in months) + "월"
                        if n_pay >= 7:
                            freq = "월배당 (매월)"
                        elif n_pay >= 3:
                            freq = f"분기배당 ({mtxt})"
                        elif n_pay == 2:
                            freq = f"반기배당 ({mtxt})"
                        else:
                            freq = f"연배당 ({mtxt})"
                    except Exception as _dg_e:
                        _diag_note("_yf_fetch_one", _dg_e)
                        pass
        except Exception as _dg_e:
            _diag_note("_yf_fetch_one", _dg_e)
            pass

        # 폴백 A : info 의 배당금 필드
        if not annual_div:
            annual_div = float(info.get('dividendRate') or info.get('trailingAnnualDividendRate') or 0) or 0.0

        # 폴백 B : 배당수익률 × 현재가
        if not annual_div and price:
            dy = info.get('dividendYield') or info.get('trailingAnnualDividendYield') or 0
            try:
                dy = float(dy)
                if dy > 1:           # 일부 버전은 퍼센트(예: 3.5)로 반환
                    dy = dy / 100.0
                if dy:
                    annual_div = price * dy
            except Exception as _dg_e:
                _diag_note("_yf_fetch_one", _dg_e)
                pass

        return ticker_code, float(price or 0), float(annual_div or 0), name, freq

    def _yf_fetch_many(tickers, max_workers=8):
        out = {}
        try:
            with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as ex:
                for tk, pr, dv, nm, fq in ex.map(_yf_fetch_one, tickers):
                    out[tk] = (pr, dv, nm, fq)
        except Exception:
            for tk in tickers:
                try:
                    _, pr, dv, nm, fq = _yf_fetch_one(tk)
                    out[tk] = (pr, dv, nm, fq)
                except Exception:
                    out[tk] = (0.0, 0.0, tk, "—")
        return out

    # ----- 조회 대상 종목 -----
    kr_tickers = [
        "024110.KS", "316140.KS", "086790.KS", "105560.KS", "055550.KS", "033780.KS",
        "017670.KS", "030200.KS", "032640.KS", "090430.KS", "000810.KS", "058300.KS",
        "001450.KS", "032830.KS", "029780.KS", "005930.KS", "005935.KS", "000270.KS",
        "005380.KS", "004800.KS", "003550.KS", "034730.KS", "078930.KS", "010130.KS",
        "010950.KS", "053690.KS", "000400.KS",
        # --- 추가 확장분 (pykrx 차단 시 폴백용 대형 배당주) ---
        "000660.KS", "005490.KS", "051910.KS", "006400.KS", "035420.KS", "035720.KS",
        "028260.KS", "012330.KS", "068270.KS", "051900.KS", "097950.KS", "271560.KS",
        "011170.KS", "096770.KS", "015760.KS", "036460.KS", "009540.KS", "010140.KS",
        "011200.KS", "086280.KS", "000120.KS", "003490.KS", "138040.KS", "088350.KS",
        "005830.KS", "005385.KS", "071050.KS", "016360.KS", "006800.KS", "039490.KS",
        "004170.KS", "023530.KS", "069960.KS", "161390.KS", "009150.KS", "018260.KS",
        "010120.KS", "006260.KS", "001120.KS", "012450.KS", "047810.KS", "267250.KS",
        "004020.KS", "001040.KS", "002790.KS", "000150.KS", "064350.KS", "272210.KS"
    ]
    kr_names = {
        "024110.KS": "기업은행", "316140.KS": "우리금융지주", "086790.KS": "하나금융지주",
        "105560.KS": "KB금융", "055550.KS": "신한지주", "033780.KS": "KT&G",
        "017670.KS": "SK텔레콤", "030200.KS": "KT", "032640.KS": "LG유플러스",
        "090430.KS": "맥쿼리인프라", "000810.KS": "삼성화재", "058300.KS": "DB손해보험",
        "001450.KS": "현대해상", "032830.KS": "삼성생명", "029780.KS": "삼성카드",
        "005930.KS": "삼성전자", "005935.KS": "삼성전자우", "000270.KS": "기아",
        "005380.KS": "현대차", "004800.KS": "효성", "003550.KS": "LG",
        "034730.KS": "SK", "078930.KS": "GS", "010130.KS": "고려아연",
        "010950.KS": "S-Oil", "053690.KS": "LX인터내셔널", "000400.KS": "제일기획"
    }
    us_tickers = ["AAPL", "MSFT", "JNJ", "XOM", "JPM", "PG", "CVX", "HD", "ABBV", "MRK",
                  "KO", "PEP", "BAC", "PFE", "TMO", "CSCO", "MCD", "WMT", "TXN", "IBM",
                  "VZ", "MMM", "MO", "CAT", "UPS", "T", "KMB", "CL", "CLX", "K",
                  "ADP", "EMR", "ITW", "GD", "LMT", "NOC", "RTX", "HON", "SHW", "APD",
                  "LIN", "NEE", "DUK", "SO", "D", "AEP", "O", "PLD", "AMT", "PSA",
                  "ABT", "MDT", "BMY", "AMGN", "LLY", "UNH", "CVS", "TGT", "LOW", "COST",
                  "TJX", "KR", "HSY", "MDLZ", "STZ", "PM", "KDP", "COP", "EOG", "SLB",
                  "PSX", "MPC", "VLO", "OKE", "KMI", "WMB", "NUE", "WFC", "C", "USB",
                  "PNC", "TFC", "AXP", "BLK", "SPGI", "TROW", "GS", "PRU", "TRV", "QCOM",
                  "AVGO", "AMAT", "INTC", "NKE", "SBUX", "CMCSA", "UNP", "FDX", "MMC", "WM"]
    etf_tickers = ["SCHD", "JEPI", "VYM", "VIG", "SPYD", "JEPQ", "DGRO", "NOBL", "DVY", "SDY",
                   "HDV", "PFF", "TLT", "HYG", "LQD", "VNQ", "DGRW", "FVD", "RDVY", "PEY",
                   "DHS", "DLN", "DTD", "DON", "DES", "FDVV", "SPHD", "DIV", "SCHY", "VYMI",
                   "IDV", "DWX", "DEM", "DGS", "HDEF", "QYLD", "XYLD", "RYLD", "DIVO", "QYLG",
                   "XYLG", "NUSI", "SPYI", "QQQI", "GPIX", "GPIQ", "JEPY", "FEPI", "BALI", "SVOL",
                   "TLTW", "HYGW", "PFFD", "PGX", "PGF", "VRP", "PFXF", "FPE", "PFFA", "PFFR",
                   "PFLD", "IEF", "IEI", "SHY", "GOVT", "BND", "AGG", "VCIT", "VCSH", "VCLT",
                   "JNK", "USHY", "SHYG", "SJNK", "EMB", "BNDX", "MUB", "TFI", "HYD", "BAB",
                   "ANGL", "FALN", "BIL", "SGOV", "USFR", "FLOT", "JAAA", "BINC", "SCHH", "RWR",
                   "IYR", "REM", "MORT", "SRET", "KBWY", "SDIV", "KBWD", "YYY"]

    # =========================================================
    # 1. 🇰🇷 한국 주식 (KRX)
    # =========================================================
    krx_list = []

    # (1-A) pykrx 공식 API (국내 IP / 로컬에서 최상)
    try:
        from pykrx import stock
        b_days = stock.get_business_days_dates(datetime.today() - timedelta(days=10), datetime.today())
        last_bday = b_days[-1].strftime("%Y%m%d")
        fund_df = stock.get_market_fundamental(last_bday, market="ALL")
        ohlcv_df = stock.get_market_ohlcv(last_bday, market="ALL")
        kr_df = pd.concat([ohlcv_df['종가'], fund_df['DPS']], axis=1).dropna()
        kr_df = kr_df[kr_df['DPS'] > 0].sort_values('DPS', ascending=False).head(300)
        for ticker, row in kr_df.iterrows():
            name = stock.get_market_ticker_name(ticker)
            krx_list.append({
                '종목명': name,
                '현재가': f"{int(row['종가']):,}원",
                '예상 배당금': float(row['DPS']),
                '배당주기': '연 1회(추정)',
                '비고': 'KRX 공식 데이터'
            })
    except Exception as _dg_e:
        _diag_note("get_dividend_portfolio", _dg_e)
        pass

    # (1-B) yfinance 우회 — 클라우드 IP에서 pykrx 가 막혔을 때 (가장 안정적)
    if not krx_list:
        kr_res = _yf_fetch_many(kr_tickers)
        for t_code in kr_tickers:
            pr, dv, nm, fq = kr_res.get(t_code, (0.0, 0.0, t_code, "—"))
            if pr > 0 and dv > 0:
                krx_list.append({
                    '종목명': kr_names.get(t_code) or nm or t_code,
                    '현재가': f"{int(pr):,}원",
                    '예상 배당금': float(dv),
                    '배당주기': fq,
                    '비고': 'Yahoo(yfinance) 우회'
                })

    # (1-C) yahooquery 우회 — 최후의 폴백
    if not krx_list:
        try:
            from yahooquery import Ticker as yq_Ticker
            yq_kr = yq_Ticker(kr_tickers)
            kr_details = yq_kr.summary_detail
            kr_prices = yq_kr.price
            for t_code in kr_tickers:
                try:
                    d = kr_details.get(t_code, {})
                    p = kr_prices.get(t_code, {})
                    if isinstance(d, str): continue
                    price = p.get('regularMarketPrice', 0)
                    div_rate = d.get('dividendRate', 0)
                    if (not div_rate or div_rate == 0) and price > 0:
                        div_yield = d.get('yield', d.get('trailingAnnualDividendYield', 0))
                        if div_yield: div_rate = price * div_yield
                    if price > 0 and div_rate > 0:
                        krx_list.append({
                            '종목명': kr_names.get(t_code) or p.get('shortName') or p.get('longName') or t_code,
                            '현재가': f"{int(price):,}원",
                            '예상 배당금': float(div_rate),
                            '배당주기': '—',
                            '비고': 'yahooquery 우회'
                        })
                except Exception as _dg_e:
                    _diag_note("get_dividend_portfolio", _dg_e)
                    pass
        except Exception as _dg_e:
            _diag_note("get_dividend_portfolio", _dg_e)
            pass

    krx_df = pd.DataFrame(krx_list)
    if not krx_df.empty:
        krx_df = krx_df.sort_values('예상 배당금', ascending=False)
        krx_df['예상 배당금'] = krx_df['예상 배당금'].apply(lambda x: f"{int(x):,}원" if isinstance(x, (int, float)) else str(x))

    # =========================================================
    # 2. 🇺🇸 미국 주식 & 📈 ETF
    # =========================================================
    us_list, etf_list = [], []

    def _build_us_row(ticker, pr, dv, nm, src, freq="—"):
        if pr > 0 and dv > 0:
            name_ko = ticker
            if 'get_korean_name' in globals():
                name_ko = get_korean_name(nm)
                if name_ko == nm:          # 사전 미매칭 → 티커로 재시도
                    name_ko = get_korean_name(ticker)
            return {
                '종목명': f"{name_ko} ({ticker})",
                '현재가': f"${pr:,.2f} ({int(pr * ex_rate):,}원)",
                '예상 배당금': float(dv),
                '표시 배당금': f"${dv:,.2f} ({int(dv * ex_rate):,}원)",
                '배당주기': freq,
                '비고': src
            }
        return None

    # (2-A) yfinance 우선 (이 앱에서 검증된 경로)
    yf_res = _yf_fetch_many(us_tickers + etf_tickers)
    for tk in us_tickers:
        pr, dv, nm, fq = yf_res.get(tk, (0.0, 0.0, tk, "—"))
        row = _build_us_row(tk, pr, dv, nm, 'yfinance', freq=fq)
        if row: us_list.append(row)
    for tk in etf_tickers:
        pr, dv, nm, fq = yf_res.get(tk, (0.0, 0.0, tk, "—"))
        row = _build_us_row(tk, pr, dv, nm, 'yfinance', freq=fq)
        if row: etf_list.append(row)

    # (2-B) yahooquery 폴백 — yfinance 가 비었을 때만
    if not us_list or not etf_list:
        try:
            from yahooquery import Ticker as yq_Ticker
            need = ([] if us_list else us_tickers) + ([] if etf_list else etf_tickers)
            if need:
                yq = yq_Ticker(need)
                details = yq.summary_detail
                prices = yq.price

                def _yq_row(ticker):
                    try:
                        detail = details.get(ticker, {})
                        price_info = prices.get(ticker, {})
                        if isinstance(detail, str): return None
                        price = price_info.get('regularMarketPrice', 0)
                        div_rate = detail.get('dividendRate', 0)
                        if not div_rate or div_rate == 0:
                            dy = detail.get('yield', detail.get('trailingAnnualDividendYield', 0))
                            if dy and price > 0: div_rate = price * dy
                        nm = price_info.get('shortName', ticker)
                        return _build_us_row(ticker, price, div_rate, nm, 'yahooquery')
                    except Exception as _dg_e:
                        _diag_note("_yq_row", _dg_e)
                        return None

                if not us_list:
                    for tk in us_tickers:
                        r = _yq_row(tk)
                        if r: us_list.append(r)
                if not etf_list:
                    for tk in etf_tickers:
                        r = _yq_row(tk)
                        if r: etf_list.append(r)
        except Exception as _dg_e:
            _diag_note("get_dividend_portfolio", _dg_e)
            pass

    us_df = pd.DataFrame(us_list)
    etf_df = pd.DataFrame(etf_list)

    if not us_df.empty:
        us_df = us_df.sort_values('예상 배당금', ascending=False)
        us_df['예상 배당금'] = us_df['표시 배당금']
        us_df = us_df.drop(columns=['표시 배당금'])
    if not etf_df.empty:
        etf_df = etf_df.sort_values('예상 배당금', ascending=False)
        etf_df['예상 배당금'] = etf_df['표시 배당금']
        etf_df = etf_df.drop(columns=['표시 배당금'])

    return {"KRX": krx_df, "US": us_df, "ETF": etf_df}

# ── 증권사 리포트 공통 파싱 헬퍼 (의견 표준화·목표가·종전가) ─────────────
def standardize_opinion(text):
    """리포트 원문에서 투자의견을 5단계로 표준화. 국문/영문/하우스별 표현 모두 흡수.
    반환: '강력매수' | '매수' | '중립' | '매도' | 'N/A'"""
    if not text:
        return "N/A"
    t = str(text).upper()
    if 'STRONG BUY' in t or '강력매수' in t:
        return '강력매수'
    if any(k in t for k in ('BUY', '매수', 'OVERWEIGHT', 'OUTPERFORM', '비중확대')):
        return '매수'
    if any(k in t for k in ('SELL', '매도', 'UNDERWEIGHT', 'UNDERPERFORM', '비중축소', '축소')):
        return '매도'
    if any(k in t for k in ('HOLD', '중립', 'NEUTRAL', 'MARKETPERFORM', 'MARKET PERFORM', '시장수익률')):
        return '중립'
    return 'N/A'


def parse_target_price(text):
    """목표가/목표주가/적정주가/적정가격/TP 뒤의 금액(원)을 추출. 없으면 0."""
    if not text:
        return 0
    m = re.search(r'(?:목표\s*주?가|적정\s*주?가격?|TP)\s*[:\s]*([0-9][0-9,]{2,})', str(text))
    return int(m.group(1).replace(',', '')) if m else 0


def parse_prev_target_price(text):
    """종전/기존 목표가 금액을 추출. 없으면 0."""
    if not text:
        return 0
    m = re.search(r'(?:종전|기존)\s*(?:목표\s*주?가)?\s*[:\s]*([0-9][0-9,]{2,})', str(text))
    return int(m.group(1).replace(',', '')) if m else 0


def classify_tp_change(title, detail_text, real_price):
    """목표가 변동(상향/하향/유지·신규) 및 변동률 산출.
    1순위: 종전가 대비 실제 % 계산  2순위: 제목/본문의 '상향'·'하향' 키워드."""
    change_status, change_pct = "유지/신규", 0.0
    prev_price = parse_prev_target_price((detail_text or "")[:600])
    if prev_price > 0 and real_price > 0:
        change_pct = (real_price - prev_price) / prev_price * 100
        change_status = "상향" if change_pct > 0 else ("하향" if change_pct < 0 else "유지/신규")
    else:
        head = (title or "") + " " + (detail_text or "")[:300]
        if '상향' in head:
            change_status = "상향"
        elif '하향' in head:
            change_status = "하향"
    return change_status, change_pct


@st.cache_data(ttl=3600)
def get_stock_research_history(code, stock_name=""):
    try:
        search_url = f"https://finance.naver.com/research/company_list.naver?searchType=itemCode&itemCode={code}"
        res = requests.get(search_url, headers={'User-Agent': 'Mozilla/5.0'}, timeout=5)
        soup = BeautifulSoup(res.content.decode('euc-kr', 'replace'), 'html.parser')
        
        table = soup.find('table', {'class': 'type_1'})
        rows = []
        
        if table:
            trs = table.find_all('tr')
            for tr in trs:
                tds = tr.find_all('td')
                if len(tds) >= 5:
                    title_tag = tds[1].find('a')
                    if not title_tag: continue
                    
                    real_title = title_tag.text.strip()
                    real_link = "https://finance.naver.com/research/" + title_tag['href']
                    real_broker = tds[2].text.strip()
                    real_date = tds[4].text.strip()
                    
                    real_price = 0
                    real_opinion = "-"
                    
                    try:
                        time.sleep(0.1) 
                        detail_res = requests.get(real_link, headers={'User-Agent': 'Mozilla/5.0'}, timeout=3)
                        detail_soup = BeautifulSoup(detail_res.content.decode('euc-kr', 'replace'), 'html.parser')
                        
                        detail_text = detail_soup.get_text(separator=' ', strip=True)
                        real_price = parse_target_price(detail_text)
                        real_opinion = standardize_opinion(detail_text)
                            
                    except Exception as _dg_e:
                        _diag_note("get_stock_research_history", _dg_e)
                        pass 
                        
                    rows.append({
                        "종목명": stock_name if stock_name else code,
                        "제목": real_title,
                        "증권사": real_broker,
                        "적정가격": real_price,
                        "투자의견": real_opinion,
                        "작성일": real_date,
                        "원문링크": real_link
                    })
        
        if rows:
            return pd.DataFrame(rows)
        else:
            return pd.DataFrame()
            
    except Exception: 
        return pd.DataFrame()

@st.cache_data(ttl=3600)
def get_value_metrics(code):
    """멀티팩터 스캐너용 지표 수집. 반환 dict: per,pbr,div,roe,debt,growth,mom3,mom6,off_high"""
    out = {"per": None, "pbr": None, "div": None, "roe": None, "debt": None,
           "growth": None, "mom3": None, "mom6": None, "off_high": None}
    # 1) PER/PBR (네이버 - 신뢰도 높음)
    try:
        per_str, pbr_str, _, _, _ = get_fundamentals(code)
        def _f(x):
            try:
                v = float(str(x).replace(",", ""))
                return v if v != 0 else None
            except Exception as _dg_e:
                _diag_note("_f", _dg_e)
                return None
        out["per"], out["pbr"] = _f(per_str), _f(pbr_str)
    except Exception as _dg_e:
        _diag_note("get_value_metrics", _dg_e)
        pass
    # 2) ROE/배당/부채/성장 (yfinance - KR 커버리지 편차 있어 소프트 처리)
    try:
        t = yf.Ticker(f"{code}.KS")
        info = t.info
        if not info or (info.get("currentPrice") is None and info.get("regularMarketPrice") is None):
            t = yf.Ticker(f"{code}.KQ")
            info = t.info
        def _pct(v):
            if v is None:
                return None
            v = float(v)
            return round(v * 100, 1) if abs(v) < 5 else round(v, 1)
        out["roe"] = _pct(info.get("returnOnEquity"))
        out["growth"] = _pct(info.get("earningsGrowth"))
        dy = info.get("dividendYield")
        if dy is not None:
            dy = float(dy)
            out["div"] = round(dy * 100, 2) if dy < 1 else round(dy, 2)
        de = info.get("debtToEquity")
        out["debt"] = round(float(de), 1) if de is not None else None
    except Exception as _dg_e:
        _diag_note("get_value_metrics", _dg_e)
        pass
    # 3) 모멘텀 (fdr 가격 - 신뢰도 높음)
    try:
        end = datetime.now()
        start = end - timedelta(days=400)
        df = fdr.DataReader(code, start.strftime("%Y-%m-%d"), end.strftime("%Y-%m-%d"))
        if df is not None and not df.empty and "Close" in df.columns:
            s = df["Close"].dropna()
            if len(s) > 20:
                last = float(s.iloc[-1])
                def _ret(days):
                    tgt = s.index[-1] - pd.Timedelta(days=days)
                    past = s[s.index <= tgt]
                    base = float(past.iloc[-1]) if not past.empty else float(s.iloc[0])
                    return round((last / base - 1) * 100, 1) if base > 0 else None
                out["mom3"], out["mom6"] = _ret(90), _ret(180)
                hi = float(s.max())
                out["off_high"] = round((last / hi - 1) * 100, 1) if hi > 0 else None
    except Exception as _dg_e:
        _diag_note("get_value_metrics", _dg_e)
        pass
    return out

@st.cache_data(ttl=3600)
def get_macro_indicators():
    # 순차 yf.Ticker 호출 → yf.download 배치 1회로 변경 (홈 화면 첫 로딩 단축)
    results = {}
    tickers = {"VIX": "^VIX", "美 10년물 국채": "^TNX", "필라델피아 반도체": "^SOX", "WTI 원유": "CL=F", "원/달러 환율": "KRW=X"}
    try:
        data = yf.download(list(tickers.values()), period="5d", group_by="ticker",
                           threads=True, progress=False)
    except Exception as _dg_e:
        _diag_note("get_macro_indicators", _dg_e)
        return None
    for name, ticker in tickers.items():
        try:
            close = data[ticker]['Close'].dropna()
            if len(close) >= 2:
                results[name] = {"value": float(close.iloc[-1]), "delta": float(close.iloc[-1] - close.iloc[-2]), "prev": float(close.iloc[-2])}
        except Exception as _dg_e: _diag_note("get_macro_indicators", _dg_e); pass
    return results if results else None

@st.cache_data(ttl=1800)
def get_fear_and_greed():
    url = "https://production.dataviz.cnn.io/index/fearandgreed/graphdata"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Accept": "application/json", "Origin": "https://edition.cnn.com", "Referer": "https://edition.cnn.com/"
    }
    try:
        res = requests.get(url, headers=headers, timeout=4)
        if res.status_code == 200:
            data = res.json()
            score = round(data['fear_and_greed']['score'])
            prev_score = round(data['fear_and_greed']['previous_close'])
            return {"score": score, "delta": score - prev_score, "rating": data['fear_and_greed']['rating'].capitalize()}
    except Exception as _dg_e: _diag_note("get_fear_and_greed", _dg_e); pass
    
    try:
        vix_df = yf.Ticker("^VIX").history(period="2d")
        if len(vix_df) >= 2:
            current_vix = float(vix_df['Close'].iloc[-1])
            prev_vix = float(vix_df['Close'].iloc[-2])
            
            est_score = max(0, min(100, int(100 - ((current_vix - 12) * 3.5))))
            est_prev = max(0, min(100, int(100 - ((prev_vix - 12) * 3.5))))
            
            if est_score >= 75: rating = "Extreme Greed"
            elif est_score >= 55: rating = "Greed"
            elif est_score >= 45: rating = "Neutral"
            elif est_score >= 25: rating = "Fear"
            else: rating = "Extreme Fear"
            
            return {"score": est_score, "delta": est_score - est_prev, "rating": f"{rating} (추정)"}
    except Exception as _dg_e: _diag_note("get_fear_and_greed", _dg_e); pass
    
    return {"score": 50, "delta": 0, "rating": "Neutral"}

@st.cache_data(ttl=3600)
def get_us_top_gainers():
    fetch_time = (datetime.utcnow() + timedelta(hours=9)).strftime("%Y-%m-%d %H:%M:%S")
    empty_df = pd.DataFrame(columns=['종목코드', '기업명', '현재가', '환산(원)', '등락률', '등락금액', '거래량'])
    try:
        response = requests.get('https://finance.yahoo.com/gainers', headers={'User-Agent': 'Mozilla/5.0'}, timeout=5)
        tables = pd.read_html(StringIO(response.text))
        raw_df = tables[0]
        result_data = []
        for _, row in raw_df.iterrows():
            row_vals = row.dropna().astype(str).tolist()
            if len(row_vals) >= 3:
                sym = row_vals[0].split()[0]
                name = row_vals[1]
                price_str, change_str, pct_str, vol_str = "", "", "", "-"
                for val in row_vals[2:]:
                    if "%" in val and ("+" in val or "-" in val):
                        parts = val.split()
                        if len(parts) >= 3:
                            price_str, change_str, pct_str = parts[0], parts[1], parts[2].replace("(", "").replace(")", "")
                            break
                if not price_str:
                    try: price_str, change_str, pct_str = str(row.iloc[2]), str(row.iloc[3]), str(row.iloc[4])
                    except Exception as _dg_e: _diag_note("get_us_top_gainers", _dg_e); pass
                try: pct_val = float(re.sub(r'[^\d\.\+\-]', '', pct_str))
                except Exception: pct_val = 0.0
                if pct_val >= 5.0:
                    if change_str.startswith('+'): change_str = f"+${change_str[1:]}"
                    elif change_str.startswith('-'): change_str = f"-${change_str[1:]}"
                    elif change_str and change_str != "nan": change_str = f"${change_str}"
                    else: change_str = "-"
                    result_data.append({"종목코드": sym, "기업명": name, "현재가": price_str, "등락금액": change_str, "등락률": pct_val, "거래량": vol_str})
        df = pd.DataFrame(result_data)
        if df.empty: return empty_df, 1350.0, fetch_time
        df = df.sort_values('등락률', ascending=False).head(30)
        try: ex_rate = float(yf.Ticker("KRW=X").history(period="5d")['Close'].iloc[-1])
        except Exception: ex_rate = 1350.0 
        def get_clean_korean_name(n):
            try:
                res = requests.get(f"https://translate.googleapis.com/translate_a/single?client=gtx&sl=en&tl=ko&dt=t&q={urllib.parse.quote(n)}", timeout=2)
                ko_name = res.json()[0][0][0]
                return re.sub(r'(?i)(,?\s*Inc\.|,?\s*Corp\.|,?\s*Corporation|,?\s*Ltd\.|,?\s*Holdings|\(주\))', '', ko_name).strip()
            except Exception as _dg_e: _diag_note("get_clean_korean_name", _dg_e); return n
        df['기업명'] = df['기업명'].apply(get_clean_korean_name)
        df['환산(원)'] = df['현재가'].apply(lambda x: f"{int(float(x.replace(',', '')) * ex_rate):,}원" if x and x.replace('.', '', 1).replace(',', '').isdigit() else "-")
        df['현재가'] = df['현재가'].apply(lambda x: f"${float(x.replace(',', '')):.2f}" if x and x.replace('.', '', 1).replace(',', '').isdigit() else str(x))
        df['등락률'] = df['등락률'].apply(lambda x: f"+{x:.2f}%")
        return df, ex_rate, fetch_time
    except Exception as _dg_e: _diag_note("get_us_top_gainers", _dg_e); return empty_df, 1350.0, fetch_time

@st.cache_data(ttl=86400)
def get_market_map():
    """종목코드 → 시장구분(코스피/코스닥/코넥스) 매핑. FDR StockListing의 Market 컬럼 활용."""
    try:
        df = fdr.StockListing('KRX')
        if df.empty or 'Code' not in df.columns or 'Market' not in df.columns:
            return {}
        df = df.copy()
        df['Code'] = df['Code'].astype(str).str.zfill(6)
        label = {
            'KOSPI': '코스피', 'KOSDAQ': '코스닥', 'KONEX': '코넥스',
            'KOSDAQ GLOBAL': '코스닥', 'KOSDAQ_GLOBAL': '코스닥',
        }
        return {
            row['Code']: label.get(str(row['Market']).upper().strip(), str(row['Market']))
            for _, row in df.iterrows() if pd.notna(row['Market'])
        }
    except Exception as _dg_e:
        _diag_note("get_market_map", _dg_e)
        return {}


def get_market_label(ticker_code):
    """종목코드의 시장 구분 라벨을 반환. 미국/실패 시 빈 문자열."""
    if not str(ticker_code).isdigit():
        return ""
    return get_market_map().get(str(ticker_code).zfill(6), "")


@st.cache_data(ttl=600)
def get_stock_list_by_market():
    """코스피/코스닥 전체 종목 리스트(시세·시총·업종 포함) — 종목 리스트 페이지용.
    반환: 정규화된 DataFrame[시장, 종목코드, 종목명, 현재가, 등락률, 거래대금(억), 시가총액(억), 업종]
    fdr.StockListing('KRX')가 막히면 _kr_market_snapshot(fdr 개별시장 → pykrx) 폴백으로 실데이터를 복구한다."""
    label = {'KOSPI': '코스피', 'KOSDAQ': '코스닥', 'KONEX': '코넥스',
             'KOSDAQ GLOBAL': '코스닥', 'KOSDAQ_GLOBAL': '코스닥'}

    def _merge_sector(out):
        # 업종 병합 (get_krx_stocks의 정제된 Sector) — 기존 로직과 동일
        try:
            krx = get_krx_stocks()
            if not krx.empty:
                out = pd.merge(out, krx[['Code', 'Sector']].rename(columns={'Code': '종목코드', 'Sector': '업종'}),
                               on='종목코드', how='left')
            else:
                out['업종'] = '-'
        except Exception:
            out['업종'] = '-'
        out['업종'] = out['업종'].fillna('-')
        # 🌐 [업종 복구 v2] get_krx_stocks가 비었거나 병합에 실패해 '-'로 남은 종목은 네이버 업종맵으로 최종 보강
        _miss = out['업종'].isin(['-', '기타/분류불가'])
        if _miss.any():
            _nsmap = _naver_sector_map()
            if _nsmap:
                out.loc[_miss, '업종'] = out.loc[_miss, '종목코드'].map(_nsmap).fillna(out.loc[_miss, '업종'])
        out = out[out['시장'].isin(['코스피', '코스닥', '코넥스'])]
        return out.reset_index(drop=True)

    # --- 1차: fdr 'KRX' 통합 (정상 시 기존과 동일한 출력) ---
    try:
        df = fdr.StockListing('KRX')
        if df is not None and not df.empty and 'Market' in df.columns:
            df = df.copy()
            df['Code'] = df['Code'].astype(str).str.zfill(6)

            def _num(col):
                if col not in df.columns:
                    return 0
                return pd.to_numeric(df[col].astype(str).str.replace(r'[^\d\.\-]', '', regex=True), errors='coerce').fillna(0)

            out = pd.DataFrame()
            out['시장'] = df['Market'].astype(str).str.upper().str.strip().map(lambda m: label.get(m, m))
            out['종목코드'] = df['Code']
            out['종목명'] = df['Name'] if 'Name' in df.columns else ''
            out['현재가'] = _num('Close').astype(int)
            out['등락률'] = _num('ChagesRatio').round(2)
            out['거래대금(억)'] = (_num('Amount') / 100000000).astype(int)
            out['시가총액(억)'] = (_num('Marcap') / 100000000).astype(int)
            return _merge_sector(out)
    except Exception as _dg_e:
        _diag_note("get_stock_list_by_market", _dg_e)
        pass

    # --- 폴백: 다중소스 스냅샷(fdr 개별시장 → pykrx)으로 실데이터 복구 ---
    try:
        snap = _kr_market_snapshot()
        if not snap.empty:
            out = pd.DataFrame()
            out['시장'] = snap['Market']
            out['종목코드'] = snap['Code'].astype(str).str.zfill(6)
            out['종목명'] = snap['Name']
            out['현재가'] = pd.to_numeric(snap['Close'], errors='coerce').fillna(0).astype(int)
            out['등락률'] = pd.to_numeric(snap['ChagesRatio'], errors='coerce').fillna(0).round(2)
            out['거래대금(억)'] = (pd.to_numeric(snap['Amount'], errors='coerce').fillna(0) / 100000000).astype(int)
            out['시가총액(억)'] = (pd.to_numeric(snap['Marcap'], errors='coerce').fillna(0) / 100000000).astype(int)
            return _merge_sector(out)
    except Exception as _dg_e:
        _diag_note("get_stock_list_by_market", _dg_e)
        pass

    return pd.DataFrame()


@st.cache_data(ttl=3600, show_spinner=False)
def _krx_list_from_naver(max_pages=22):
    """FDR 실패 시 폴백: 네이버 시가총액 페이지에서 종목명+코드 목록 구성(코스피+코스닥)."""
    rows, seen = [], set()
    for sosok in (0, 1):   # 0=코스피, 1=코스닥
        mkt_name = "코스피" if sosok == 0 else "코스닥"
        for page in range(1, max_pages + 1):
            try:
                url = f"https://finance.naver.com/sise/sise_market_sum.naver?sosok={sosok}&page={page}"
                res = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=5)
                soup = BeautifulSoup(res.content.decode("euc-kr", "replace"), "html.parser")
                table = soup.select_one("table.type_2")
                if not table:
                    break
                added = 0
                for a in table.select("a.tltle"):   # 종목명 링크 (네이버 클래스명 'tltle')
                    href = a.get("href", "")
                    m = re.search(r"code=(\d{6})", href)
                    if not m:
                        continue
                    code = m.group(1)
                    name = a.get_text(strip=True)
                    if not name or code in seen:
                        continue
                    seen.add(code)
                    rows.append({"Name": name, "Code": code, "Sector": "기타/분류불가", "Market": mkt_name})
                    added += 1
                if added == 0:
                    break   # 빈 페이지면 해당 시장 종료
            except Exception:
                break
    if rows:
        return pd.DataFrame(rows)
    return pd.DataFrame(columns=["Name", "Code", "Sector", "Market"])


# ── [NEW] 국내 ETF 전체 목록 로더 (우주항공·방산 등 테마 ETF 검색 지원) ──────
def _get_etf_list():
    """국내 상장 ETF 전체 목록을 DataFrame(Name, Code, Sector, Market)으로 반환.
    1) FinanceDataReader → 2) 네이버 ETF API → 3) pykrx 순서로 폴백."""
    # 1차: FinanceDataReader
    try:
        etf = fdr.StockListing('ETF/KR')
        if etf is not None and not etf.empty:
            code_col = next((c for c in ['Symbol', 'Code', 'symbol', 'code'] if c in etf.columns), None)
            name_col = next((c for c in ['Name', 'name'] if c in etf.columns), None)
            if code_col and name_col:
                out = etf[[name_col, code_col]].copy()
                out.columns = ['Name', 'Code']
                out['Code'] = out['Code'].astype(str).str.zfill(6)
                out['Sector'] = 'ETF'
                out['Market'] = 'ETF'
                return out.dropna(subset=['Name']).drop_duplicates(subset=['Code']).reset_index(drop=True)
    except Exception as _dg_e:
        _diag_note("_get_etf_list", _dg_e)
        pass
    # 2차: 네이버 ETF 시세 API (JSON)
    try:
        url = "https://finance.naver.com/api/sise/etfItemList.nhn"
        res = requests.get(url, headers={'User-Agent': 'Mozilla/5.0'}, timeout=5)
        items = res.json().get('result', {}).get('etfItemList', [])
        if items:
            rows = [{'Name': it.get('itemname'), 'Code': str(it.get('itemcode')).zfill(6),
                     'Sector': 'ETF', 'Market': 'ETF'} for it in items if it.get('itemcode')]
            if rows:
                return pd.DataFrame(rows).dropna(subset=['Name']).drop_duplicates(subset=['Code']).reset_index(drop=True)
    except Exception as _dg_e:
        _diag_note("_get_etf_list", _dg_e)
        pass
    # 3차: pykrx
    try:
        from pykrx import stock as _pykrx_stock
        tickers = _pykrx_stock.get_etf_ticker_list()
        rows = []
        for t in tickers:
            try:
                rows.append({'Name': _pykrx_stock.get_etf_ticker_name(t), 'Code': str(t).zfill(6),
                             'Sector': 'ETF', 'Market': 'ETF'})
            except Exception as _dg_e:
                _diag_note("_get_etf_list", _dg_e)
                continue
        if rows:
            return pd.DataFrame(rows).dropna(subset=['Name']).drop_duplicates(subset=['Code']).reset_index(drop=True)
    except Exception as _dg_e:
        _diag_note("_get_etf_list", _dg_e)
        pass
    return pd.DataFrame(columns=['Name', 'Code', 'Sector', 'Market'])

@st.cache_data(ttl=86400, show_spinner=False)
def _naver_sector_map():
    """🌐 [업종 복구 엔진 v2] 네이버 '업종별 시세' 그룹(~80개)을 병렬 크롤링해
    {6자리 종목코드: 업종명} '전 종목' 맵을 구성 (하루 1회 캐시).
    KRX(fdr 'KRX-DESC')가 클라우드 IP를 차단해 업종이 통째로 비는 문제의 최종 폴백. 실패 시 {}."""
    base = "https://finance.naver.com"
    headers = {'User-Agent': 'Mozilla/5.0'}
    try:
        res = requests.get(f"{base}/sise/sise_group.naver?type=upjong", headers=headers, timeout=6)
        soup = BeautifulSoup(res.content.decode('euc-kr', errors='replace'), 'html.parser')
        groups, seen = [], set()
        for a in soup.select('a[href*="sise_group_detail.naver"]'):
            m = re.search(r'no=(\d+)', a.get('href', ''))
            name = a.get_text(strip=True)
            if m and name and m.group(1) not in seen:
                seen.add(m.group(1))
                groups.append((m.group(1), name))
        if not groups:
            return {}

        def _fetch_group(item):
            no, name = item
            codes = []
            try:
                r = requests.get(f"{base}/sise/sise_group_detail.naver?type=upjong&no={no}",
                                 headers=headers, timeout=6)
                s = BeautifulSoup(r.content.decode('euc-kr', errors='replace'), 'html.parser')
                for a in s.select('a[href*="/item/main.naver?code="]'):
                    m2 = re.search(r'code=(\d{6})', a.get('href', ''))
                    if m2:
                        codes.append(m2.group(1))
            except Exception as _dg_e:
                _diag_note("_fetch_group", _dg_e)
                pass
            return name, codes

        sector_map = {}
        with concurrent.futures.ThreadPoolExecutor(max_workers=10) as ex:
            for name, codes in ex.map(_fetch_group, groups):
                for c in codes:
                    sector_map.setdefault(c, name)
        return sector_map
    except Exception as _dg_e:
        _diag_note("_naver_sector_map", _dg_e)
        return {}


@st.cache_data(ttl=86400)  # [속도개선] 전체 종목 리스트는 하루 1회만 네트워크 수집. 기존 무(無)캐시 → 매 렌더마다 fdr 2회 호출 + 2,800행 apply 가 반복되던 것을 제거.
def get_krx_stocks():
    try:
        # 1. 한국 주식 기본 데이터 가져오기
        df = fdr.StockListing('KRX')
        
        # 2. 상세 데이터(KRX-DESC)에서 'Sector(업종)' 정보 가져오기
        try:
            df_desc = fdr.StockListing('KRX-DESC')
            
            if not df_desc.empty and 'Symbol' in df_desc.columns and 'Sector' in df_desc.columns:
                df_desc = df_desc.rename(columns={'Symbol': 'Code'})
                
                df['Code'] = df['Code'].astype(str).str.zfill(6)
                df_desc['Code'] = df_desc['Code'].astype(str).str.zfill(6)
                
                # 🔥 [핵심 1] 기존 데이터에 불량 Sector가 있다면 꼬이지 않게 통째로 날려버림
                if 'Sector' in df.columns:
                    df = df.drop(columns=['Sector'])
                    
                # 정확한 KRX-DESC의 Sector로만 깔끔하게 병합
                df = pd.merge(df, df_desc[['Code', 'Sector']], on='Code', how='left')
        except Exception as _dg_e:
            _diag_note("get_krx_stocks", _dg_e)
            pass

        if not df.empty:
            if 'Sector' not in df.columns: 
                df['Sector'] = '기타/분류불가'
            
            # 🔥 [핵심 2] API가 보내는 악성 빈칸('')이나 띄어쓰기(' ')를 잡아내 결측치로 강제 변환
            df['Sector'] = df['Sector'].replace('', np.nan).replace(' ', np.nan)
            df['Sector'] = df['Sector'].fillna('기타/분류불가') 
            
            # 🛡️ [핵심 3: 최후의 방어막] API 서버가 죽더라도 주요 대장주 섹터는 무조건 살려내는 하드코딩
            major_sectors = {
                '005930': '반도체', '000660': '반도체', '005380': '자동차', '000270': '자동차',
                '373220': '2차전지', '207940': '바이오', '068270': '바이오', '035420': 'IT/플랫폼',
                '035720': 'IT/플랫폼', '105560': '금융지주', '055550': '금융지주', '028260': '지주사',
                '051910': '화학/2차전지', '006400': '2차전지', '012330': '자동차부품', '005490': '철강'
            }
            def safe_sector(row):
                if row['Code'] in major_sectors and row['Sector'] == '기타/분류불가':
                    return major_sectors[row['Code']]
                return row['Sector']
                
            df['Sector'] = df.apply(safe_sector, axis=1)

            # 🌐 [업종 복구 v2] KRX-DESC가 막혀 업종이 비면 네이버 '업종별 시세' 전체맵으로 채움 (하루 1회 캐시)
            _miss = df['Sector'].isin(['기타/분류불가', '-', ''])
            if _miss.any():
                _nsmap = _naver_sector_map()
                if _nsmap:
                    df.loc[_miss, 'Sector'] = df.loc[_miss, 'Code'].map(_nsmap).fillna('기타/분류불가')

            # 시장 구분(코스피/코스닥/코넥스) 컬럼 추가
            mkt_col = next((c for c in ['Market', 'market', 'MarketId', 'Marketid'] if c in df.columns), None)
            if mkt_col:
                _mmap = {"KOSPI": "코스피", "KOSDAQ": "코스닥", "KOSDAQ GLOBAL": "코스닥",
                         "KONEX": "코넥스", "KOSPI200": "코스피"}
                df['Market'] = df[mkt_col].astype(str).str.upper().str.strip().map(_mmap).fillna(df[mkt_col].astype(str))
            else:
                df['Market'] = ""

            df = df[['Name', 'Code', 'Sector', 'Market']].copy()
            df['Code'] = df['Code'].astype(str).str.zfill(6)
            
            # 🛰️ [NEW] ETF 목록 병합 (우주항공·방산·반도체 등 테마 ETF 검색 가능하게)
            #    → 주식 목록 '뒤'에 붙여서, 시총 상위 N개 스캔 등 기존 로직(head)에는 영향 없음
            etf_df = _get_etf_list()
            if not etf_df.empty:
                df = pd.concat([df, etf_df], ignore_index=True)
            
            return df.drop_duplicates(subset=['Name']).reset_index(drop=True)
            
    except Exception as _dg_e: 
        _diag_note("get_krx_stocks", _dg_e)
        pass
        
    # FDR 실패/빈 결과 → 네이버 시가총액 폴백으로 목록 구성
    nv = _krx_list_from_naver()
    etf_df = _get_etf_list()
    if not nv.empty:
        if not etf_df.empty:
            nv = pd.concat([nv, etf_df], ignore_index=True).drop_duplicates(subset=['Name']).reset_index(drop=True)
        return nv
    if not etf_df.empty:
        return etf_df
    return pd.DataFrame(columns=['Name', 'Code', 'Sector', 'Market'])

def fetch_naver_volume(sosok, pages=1):
    df_list = []
    try:
        for page in range(1, pages + 1):
            url = f"https://finance.naver.com/sise/sise_quant.naver?sosok={sosok}&page={page}"
            res = requests.get(url, headers={'User-Agent': 'Mozilla/5.0'}, timeout=5)
            tables = pd.read_html(StringIO(res.content.decode('euc-kr', errors='replace')))
            for t in tables:
                if '종목명' in t.columns and '현재가' in t.columns:
                    df = t.dropna(subset=['종목명']).copy()
                    df_list.append(df[df['종목명'] != '종목명'])
                    break
    except Exception as _dg_e: _diag_note("fetch_naver_volume", _dg_e); pass
    if df_list: return pd.concat(df_list, ignore_index=True).drop_duplicates(subset=['종목명'])
    return pd.DataFrame()
    
# 🇺🇸 미국 주식 영문명 -> 한글명 자동 변환 함수
def get_korean_name(eng_name):
    if not eng_name:
        return ""
        
    ko_dict = {
        "AAPL": "애플", "MSFT": "마이크로소프트", "AMZN": "아마존", "GOOGL": "구글", "GOOG": "구글", 
        "META": "메타", "TSLA": "테슬라", "NVDA": "엔비디아", "JPM": "JP모건", "V": "비자",
        "JNJ": "존슨앤존슨", "XOM": "엑슨모빌", "PG": "P&G", "HD": "홈디포", "MA": "마스터카드",
        "CVX": "쉐브론", "ABBV": "애브비", "MRK": "머크", "KO": "코카콜라", "PEP": "펩시",
        "BAC": "뱅크오브아메리카", "WMT": "월마트", "PFE": "화이자", "MCD": "맥도날드",
        "CSCO": "시스코", "VZ": "버라이즌", "TMO": "써모피셔", "ABT": "애보트", "CRM": "세일즈포스",
        "DIS": "디즈니", "NFLX": "넷플릭스", "AMD": "AMD", "INTC": "인텔", "QCOM": "퀄컴",
        "SCHD": "SCHD ETF", "JEPI": "JEPI ETF", "SPY": "SPY ETF", "QQQ": "QQQ ETF",
        "Apple": "애플", "Microsoft": "마이크로소프트", "NVIDIA": "엔비디아", "Tesla": "테슬라"
    }
    
    name_str = str(eng_name).strip()
    # 1. 티커 완전 일치 검사
    if name_str.upper() in ko_dict:
        return ko_dict[name_str.upper()]

    # 2. 회사 '이름' 키만 부분 일치 (티커 키 'V','MA','KO' 등이 'adVanced' 같은 단어에
    #    부분 매칭되어 AMD→비자 가 되던 버그 방지: 소문자가 포함된 이름형 키만, 단어 경계로 매칭)
    low = name_str.lower()
    for key, val in ko_dict.items():
        if any(ch.islower() for ch in key) and re.search(r"\b" + re.escape(key.lower()) + r"\b", low):
            return val

    # 사전에 없으면 원래 영문 이름 그대로 반환
    return name_str

@st.cache_data(ttl=300, show_spinner=False)
def _kr_market_snapshot():
    """fdr.StockListing('KRX')가 막혔을 때를 위한 폴백 시세 스냅샷.
    소스를 순차 시도하여 실데이터([Code, Name, Close, ChagesRatio, Amount, Marcap, Market])를 확보한다.
      1) fdr를 KOSPI/KOSDAQ로 분할 시도 ('KRX' 통합이 막혀도 개별은 되는 경우가 있음)
      2) pykrx (KRX의 다른 엔드포인트 — fdr이 죽어도 살아있는 경우가 많음)
    어떤 경우에도 예외를 밖으로 던지지 않으며, 모두 실패하면 빈 DataFrame을 반환한다(→ 기존 동작 이하로 떨어지지 않음)."""
    def _num(df, col):
        if col not in df.columns:
            return pd.Series([0] * len(df))
        return pd.to_numeric(df[col].astype(str).str.replace(r'[^\d\.\-]', '', regex=True), errors='coerce').fillna(0)

    # --- 소스 1: FDR 개별 시장 ---
    def _from_fdr():
        frames = []
        for mcode, kname in [("KOSPI", "코스피"), ("KOSDAQ", "코스닥")]:
            try:
                d = fdr.StockListing(mcode)
                if d is None or d.empty:
                    continue
                d = d.copy()
                d['__mkt'] = kname
                frames.append(d)
            except Exception as _dg_e:
                _diag_note("_from_fdr", _dg_e)
                continue
        if not frames:
            return pd.DataFrame()
        df = pd.concat(frames, ignore_index=True)
        out = pd.DataFrame()
        out['Code'] = (df['Code'].astype(str).str.zfill(6)) if 'Code' in df.columns else ""
        out['Name'] = df['Name'] if 'Name' in df.columns else ""
        out['Close'] = _num(df, 'Close')
        out['ChagesRatio'] = _num(df, 'ChagesRatio')
        out['Amount'] = _num(df, 'Amount')
        out['Marcap'] = _num(df, 'Marcap')
        out['Market'] = df['__mkt']
        return out[out['Code'].astype(str).str.len() == 6].reset_index(drop=True)

    # --- 소스 2: pykrx ---
    def _from_pykrx():
        if not HAS_PYKRX:
            return pd.DataFrame()
        import datetime as _dt
        frames = []
        for mcode, kname in [("KOSPI", "코스피"), ("KOSDAQ", "코스닥")]:
            ohlcv, used = None, None
            for back in range(0, 8):   # 주말/공휴일이면 직전 거래일로 후퇴
                ds = (_dt.datetime.now() - _dt.timedelta(days=back)).strftime("%Y%m%d")
                try:
                    t = pykrx_stock.get_market_ohlcv_by_ticker(ds, market=mcode)
                    if t is not None and not t.empty and float(pd.to_numeric(t['종가'], errors='coerce').fillna(0).sum()) > 0:
                        ohlcv, used = t, ds
                        break
                except Exception as _dg_e:
                    _diag_note("_from_pykrx", _dg_e)
                    continue
            if ohlcv is None:
                continue
            o = ohlcv.reset_index().rename(columns={ohlcv.index.name or 'index': 'Code'})
            o = o.rename(columns={o.columns[0]: 'Code'})   # 인덱스(티커) → Code 보장
            try:
                cap = pykrx_stock.get_market_cap_by_ticker(used, market=mcode).reset_index()
                cap = cap.rename(columns={cap.columns[0]: 'Code'})
                o = pd.merge(o, cap[['Code', '시가총액']], on='Code', how='left')
            except Exception:
                o['시가총액'] = 0
            o['__mkt'] = kname
            frames.append(o)
        if not frames:
            return pd.DataFrame()
        df = pd.concat(frames, ignore_index=True)
        out = pd.DataFrame()
        out['Code'] = df['Code'].astype(str).str.zfill(6)
        out['Close'] = pd.to_numeric(df.get('종가', 0), errors='coerce').fillna(0)
        out['ChagesRatio'] = pd.to_numeric(df.get('등락률', 0), errors='coerce').fillna(0)
        out['Amount'] = pd.to_numeric(df.get('거래대금', 0), errors='coerce').fillna(0)
        out['Marcap'] = pd.to_numeric(df.get('시가총액', 0), errors='coerce').fillna(0)
        out['Market'] = df['__mkt']
        # 종목명은 get_krx_stocks(이름↔코드 매핑)에서 병합 (pykrx OHLCV엔 이름이 없음)
        try:
            krx = get_krx_stocks()
            if not krx.empty:
                out = pd.merge(out, krx[['Code', 'Name']], on='Code', how='left')
        except Exception as _dg_e:
            _diag_note("_from_pykrx", _dg_e)
            pass
        if 'Name' not in out.columns:
            out['Name'] = ""
        out['Name'] = out['Name'].fillna("")
        return out.reset_index(drop=True)

    for _src in (_from_fdr, _from_pykrx):
        try:
            snap = _src()
            if snap is not None and not snap.empty and float(snap['Close'].abs().sum()) > 0:
                return snap.reset_index(drop=True)
        except Exception as _dg_e:
            _diag_note("_kr_market_snapshot", _dg_e)
            continue
    return pd.DataFrame(columns=['Code', 'Name', 'Close', 'ChagesRatio', 'Amount', 'Marcap', 'Market'])


@st.cache_data(ttl=300)
def get_trading_value_kings(limit=50):
    try:
        df_fdr = fdr.StockListing('KRX')
        if not df_fdr.empty and 'Amount' in df_fdr.columns:
            mask = df_fdr['Name'].str.contains('KODEX|TIGER|KBSTAR|KOSEF|ARIRANG|HANARO|ACE|스팩|ETN|선물|인버스|레버리지', na=False)
            df_fdr = df_fdr[~mask].copy()
            df_fdr['Amount'] = pd.to_numeric(df_fdr['Amount'].astype(str).str.replace(r'[^\d\.]', '', regex=True), errors='coerce').fillna(0)
            df_fdr['Close'] = pd.to_numeric(df_fdr['Close'].astype(str).str.replace(r'[^\d\.]', '', regex=True), errors='coerce').fillna(0)
            df_fdr['ChagesRatio'] = pd.to_numeric(df_fdr['ChagesRatio'].astype(str).str.replace(r'[^\d\.\-]', '', regex=True), errors='coerce').fillna(0)
            df_fdr = df_fdr.sort_values('Amount', ascending=False).head(limit)
            df_fdr['Amount_Ouk'] = (df_fdr['Amount'] / 100000000).astype(int)
            krx = get_krx_stocks()
            if not krx.empty:
                df_fdr = pd.merge(df_fdr, krx[['Name', 'Sector']], on='Name', how='left')
                df_fdr['Sector'] = df_fdr['Sector'].fillna('기타/분류불가')
            else: 
                df_fdr['Sector'] = '기타/분류불가'
            
            # 🔥 [히트맵 섹터 복구 엔진] 거래소 서버 차단 시, 네이버 증권에서 쾌속 병렬 처리로 업종을 구출해옵니다.
            missing_mask = df_fdr['Sector'] == '기타/분류불가'
            if missing_mask.any():
                missing_codes = df_fdr.loc[missing_mask, 'Code'].tolist()
                
                def rescue_sector(code):
                    try:
                        res = requests.get(f"https://finance.naver.com/item/main.naver?code={code}", headers={'User-Agent': 'Mozilla/5.0'}, timeout=2)
                        soup = BeautifulSoup(res.text, 'html.parser')
                        
                        # 🛠️ [핵심 수정] 여기도 동일하게 a 태그만 정확하게 타겟팅합니다.
                        tag = soup.select_one('a[href*="/sise/sise_group_detail.naver"]')
                        return code, tag.text.strip() if tag else '기타'
                    except Exception as _dg_e: _diag_note("rescue_sector", _dg_e); return code, '기타'
                
                with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
                    rescued_sectors = dict(executor.map(rescue_sector, missing_codes))
                
                df_fdr.loc[missing_mask, 'Sector'] = df_fdr.loc[missing_mask, 'Code'].map(rescued_sectors).fillna('기타')
                
            return df_fdr[['Code', 'Name', 'Close', 'ChagesRatio', 'Amount_Ouk', 'Sector']]
    except Exception as _dg_e: _diag_note("get_trading_value_kings", _dg_e); pass

    # 🚨 1차 소스(fdr 'KRX') 실패 → 다중소스 스냅샷(fdr 개별시장 → pykrx)으로 '실제 등락률·거래대금' 복구
    snap = _kr_market_snapshot()
    if not snap.empty:
        fb = snap.copy()
        # 1차 경로와 동일 기준으로 ETF/스팩/선물 등 제외
        mask = fb['Name'].astype(str).str.contains('KODEX|TIGER|KBSTAR|KOSEF|ARIRANG|HANARO|ACE|스팩|ETN|선물|인버스|레버리지', na=False)
        fb = fb[~mask].copy()
        fb = fb.sort_values('Amount', ascending=False).head(limit)
        fb['Amount_Ouk'] = (fb['Amount'] / 100000000).astype(int)
        try:
            krx = get_krx_stocks()
            if not krx.empty:
                fb = pd.merge(fb, krx[['Code', 'Sector']], on='Code', how='left')
            if 'Sector' not in fb.columns:
                fb['Sector'] = '기타/분류불가'
            fb['Sector'] = fb['Sector'].fillna('기타/분류불가')
        except Exception:
            fb['Sector'] = '기타/분류불가'
        return fb[['Code', 'Name', 'Close', 'ChagesRatio', 'Amount_Ouk', 'Sector']]

    # 🚨 모든 시세 소스 실패 시: 이름만이라도 표시(등락률 0). 빈 결과면 빈 DF 반환.
    fallback_df = get_krx_stocks().head(limit)
    if fallback_df.empty:
        return pd.DataFrame(columns=['Code', 'Name', 'Close', 'ChagesRatio', 'Amount_Ouk', 'Sector'])
    fallback_df = fallback_df.copy()
    fallback_df['Close'] = 0
    fallback_df['ChagesRatio'] = 0.0
    fallback_df['Amount_Ouk'] = 1000
    return fallback_df[['Code', 'Name', 'Close', 'ChagesRatio', 'Amount_Ouk', 'Sector']]


@st.cache_data(ttl=86400, show_spinner=False)
def _get_kr_etf_codes():
    """네이버 etfItemList(+etnItemList) → 전체 ETF/ETN 종목코드 집합(클라우드 호환).
    Content-Type에 의존하지 않고 직접 파싱. 실패 시 빈 set."""
    import json as _json
    codes = set()
    for url, key in (
        ("https://finance.naver.com/api/sise/etfItemList.nhn", "etfItemList"),
        ("https://finance.naver.com/api/sise/etnItemList.nhn", "etnItemList"),
    ):
        try:
            r = requests.get(url, headers={"User-Agent": "Mozilla/5.0",
                                           "Referer": "https://finance.naver.com/sise/etf.naver"},
                             timeout=7)
            if r.status_code != 200:
                continue
            try:
                j = r.json()
            except Exception:
                j = _json.loads(r.text)
            items = ((j or {}).get("result") or {}).get(key) or []
            for it in items:
                c = str(it.get("itemcode", "")).strip()
                if c.isdigit():
                    codes.add(c.zfill(6))
        except Exception as _dg_e:
            _diag_note("_get_kr_etf_codes", _dg_e)
            continue
    return codes


def is_kr_etf_etn(name, code=""):
    """국내 ETF·ETN·레버리지/인버스/선물 등 '상품' 여부 (차트 기술분석 비대상 → 스캐너 제외)."""
    s = str(name or "").upper().replace(" ", "")
    if s:
        if any(s.startswith(b) for b in _KR_ETF_BRANDS):
            return True
        if any(k in s for k in _KR_PRODUCT_KEYWORDS):
            return True
    try:
        c = str(code or "").strip()
        if c.isdigit() and c.zfill(6) in _get_kr_etf_codes():
            return True
    except Exception as _dg_e:
        _diag_note("is_kr_etf_etn", _dg_e)
        pass
    return False


@st.cache_data(ttl=300)
def get_scan_targets(limit=50):
    def _drop_products(lst):
        return [(n, c) for n, c in lst if not is_kr_etf_etn(n, c)]
    try:
        df_fdr = fdr.StockListing('KRX')
        if not df_fdr.empty:
            mask = df_fdr['Name'].str.contains('KODEX|TIGER|KBSTAR|KOSEF|ARIRANG|HANARO|ACE|스팩|ETN|선물|인버스|레버리지', na=False)
            df_fdr = df_fdr[~mask].drop_duplicates(subset=['Name'])
            if 'Amount' in df_fdr.columns:
                df_fdr['Amount'] = pd.to_numeric(df_fdr['Amount'].astype(str).str.replace(r'[^\d\.]', '', regex=True), errors='coerce').fillna(0.0)
                df_fdr = df_fdr.sort_values('Amount', ascending=False)
            targets = _drop_products(df_fdr.head(limit * 2)[['Name', 'Code']].values.tolist())[:limit]
            if targets: return targets
    except Exception as _dg_e: _diag_note("get_scan_targets", _dg_e); pass

    # 🚨 중복 현상 해결: limit 개수를 채우기 위해 억지로 리스트를 곱하여 복사하는 로직 제거
    fallback_targets = _drop_products(get_krx_stocks()[['Name', 'Code']].values.tolist())
    if fallback_targets:
        return fallback_targets[:limit] # 준비된 예비 데이터만큼만 중복 없이 반환
    return []


@st.cache_data(ttl=900, show_spinner=False)
def get_drawdown_info(code, lookback="52주", rebound_days=120):
    """현재가·기간내 최고가·낙폭(%)·RSI 계산(가벼움). 실패 시 None.
    fdr.DataReader는 국내(6자리)·미국(티커) 모두 지원. lookback: '52주' 또는 '전체'."""
    try:
        if lookback == "52주":
            start = (datetime.now() - timedelta(days=370)).strftime("%Y-%m-%d")
            df = fdr.DataReader(str(code), start)
        else:
            df = fdr.DataReader(str(code))
        if df is None or df.empty or "Close" not in df.columns:
            return None
        close = df["Close"].dropna()
        if len(close) < 20:
            return None
        cur = float(close.iloc[-1])
        if cur <= 0:
            return None
        high_series = df["High"].dropna() if ("High" in df.columns and df["High"].notna().any()) else close
        hi = float(high_series.max())
        if hi <= 0:
            return None
        dd = round((cur / hi - 1) * 100, 1)
        try:
            hd = high_series.idxmax()
            high_date = hd.strftime("%y.%m.%d") if hasattr(hd, "strftime") else str(hd)[:10]
        except Exception:
            high_date = ""
        rsi = None
        try:
            d = close.diff()
            up = d.clip(lower=0).rolling(14).mean()
            dn = (-d.clip(upper=0)).rolling(14).mean()
            rs = up / dn
            val = rs.iloc[-1]
            if pd.notna(val):
                rsi = round(float(100 - 100 / (1 + val)), 0)
        except Exception as _dg_e:
            _diag_note("get_drawdown_info", _dg_e)
            pass
        # 최근 저점 대비 반등률(바닥 확인용)
        # 최근 저점 대비 반등률 (바닥 확인용, 기간 조절 가능)
        try:
            rb = max(5, int(rebound_days))
            lo = float(close.tail(rb).min())
            rebound = round((cur / lo - 1) * 100, 1) if lo > 0 else None
        except Exception:
            rebound = None
        
        # 🩹 [NEW] 회복 신호 6종 — 이미 받아온 데이터만 사용 (추가 네트워크 0건)
        sig = {"ma20_recover": False, "golden5_20": False, "higher_low": False,
               "vol_revive": False, "obv_rise": False, "ma60_up": False}
        try:
            ma5 = close.rolling(5).mean()
            ma20 = close.rolling(20).mean()
            ma60 = close.rolling(60).mean()
            if pd.notna(ma20.iloc[-1]):
                sig["ma20_recover"] = bool(cur > float(ma20.iloc[-1]))                     # 20일선 회복
            if pd.notna(ma5.iloc[-1]) and pd.notna(ma20.iloc[-1]):
                sig["golden5_20"] = bool(float(ma5.iloc[-1]) > float(ma20.iloc[-1]))       # 단기 골든(5>20)
            if len(close) >= 40:
                _lo_recent = float(close.tail(20).min())
                _lo_prev = float(close.tail(40).head(20).min())
                sig["higher_low"] = bool(_lo_recent > _lo_prev * 1.005)                    # 저점 높이기
            if len(ma60.dropna()) >= 11:
                sig["ma60_up"] = bool(float(ma60.iloc[-1]) > float(ma60.iloc[-11]))        # 60일선 상승 전환
            if "Volume" in df.columns and df["Volume"].notna().any():
                vol = df["Volume"].dropna()
                if len(vol) >= 40:
                    _v_recent = float(vol.tail(10).mean())
                    _v_base = float(vol.tail(40).head(30).mean())
                    sig["vol_revive"] = bool(_v_base > 0 and _v_recent > _v_base * 1.3)    # 거래량 회복(+30%)
                # OBV(매집) 20일 증가
                _common = close.index.intersection(vol.index)
                if len(_common) >= 21:
                    _c2, _v2 = close.loc[_common], vol.loc[_common]
                    obv = (np.sign(_c2.diff()).fillna(0) * _v2).cumsum()
                    sig["obv_rise"] = bool(float(obv.iloc[-1]) > float(obv.iloc[-21]))
        except Exception as _dg_e:
            _diag_note("get_drawdown_info", _dg_e)
            pass
        
        return {"current": cur, "high": hi, "high_date": high_date,
                "drawdown": dd, "rsi": rsi, "rebound": rebound, **sig}
    except Exception as _dg_e:
        _diag_note("get_drawdown_info", _dg_e)
        return None


# ── 🩹 [NEW] 낙폭과대 '회복 가능성' 진단 보조 함수들 ─────────────────────────
@st.cache_data(ttl=900, show_spinner=False)
def get_kr_sector_heat():
    """네이버 업종별 시세에서 {업종명: 전일대비 등락률%} 맵 구성 (HTTP 1회, 15분 캐시)."""
    try:
        url = "https://finance.naver.com/sise/sise_group.naver?type=upjong"
        res = requests.get(url, headers={'User-Agent': 'Mozilla/5.0'}, timeout=5)
        tables = pd.read_html(StringIO(res.content.decode('euc-kr', errors='replace')))
        for t in tables:
            cols = [str(c) for c in t.columns]
            if any('업종명' in c for c in cols):
                name_col = next(c for c in t.columns if '업종명' in str(c))
                chg_col = next((c for c in t.columns if '전일대비' in str(c) or '등락' in str(c)), None)
                if chg_col is None:
                    continue
                heat = {}
                for _, r in t.dropna(subset=[name_col]).iterrows():
                    nm = str(r[name_col]).strip()
                    try:
                        v = float(str(r[chg_col]).replace('%', '').replace('+', '').strip())
                        if nm and nm != '업종명':
                            heat[nm] = v
                    except Exception as _dg_e:
                        _diag_note("get_kr_sector_heat", _dg_e)
                        continue
                if heat:
                    return heat
    except Exception as _dg_e:
        _diag_note("get_kr_sector_heat", _dg_e)
        pass
    return {}

@st.cache_data(ttl=900, show_spinner=False)
def get_us_sector_heat():
    """미국 섹터 SPDR ETF의 최근 5거래일 수익률(%) 맵 — {한글섹터명: %} (15분 캐시)."""
    etf_map = {"IT/기술": "XLK", "금융": "XLF", "헬스케어/바이오": "XLV", "임의소비재": "XLY",
               "산업재": "XLI", "통신/플랫폼": "XLC", "필수소비재": "XLP", "에너지": "XLE",
               "소재": "XLB", "부동산": "XLRE", "유틸리티": "XLU"}
    heat = {}
    start = (datetime.now() - timedelta(days=20)).strftime("%Y-%m-%d")
    for sec_kr, etf in etf_map.items():
        try:
            d = fdr.DataReader(etf, start)
            c = d["Close"].dropna()
            if len(c) >= 6:
                heat[sec_kr] = round((float(c.iloc[-1]) / float(c.iloc[-6]) - 1) * 100, 2)
        except Exception as _dg_e:
            _diag_note("get_us_sector_heat", _dg_e)
            continue
    return heat


@st.cache_data(ttl=86400, show_spinner=False)
def get_stock_sector_kr(code):
    """종목 하나의 업종명을 네이버에서 조회. 인코딩 자동 판별 + 깨진(한자/모지바케) 결과는 거부.
    낙폭 스캐너에서 FDR 업종이 비었을 때 '결과 종목만' 보강용. 실패 시 None."""
    code = str(code).strip()
    if not code.isdigit():
        return None

    def _ok(s):
        """정상 한글 업종명만 통과: CJK 한자(깨짐 신호) 있으면 거부, 한글 비중 과반 요구."""
        if not s:
            return None
        s = str(s).strip()
        if not s or len(s) > 30:
            return None
        if any('\u3400' <= ch <= '\u9fff' for ch in s):   # CJK 한자 → 인코딩 깨짐
            return None
        han = sum(1 for ch in s if '가' <= ch <= '힣')
        return s if han >= max(1, int(len(s) * 0.5)) else None

    # ① 모바일 통합 API (JSON — UTF-8)
    try:
        data = _naver_json(f"https://m.stock.naver.com/api/stock/{code}/integration")
        if isinstance(data, dict):
            cands = []
            for k in ("industryCodeName", "industryGroupKor", "industryName", "upjongName", "sectorName"):
                if data.get(k):
                    cands.append(data[k])
            for sub in ("stockInfo", "industryInfo", "summary"):
                si = data.get(sub)
                if isinstance(si, dict):
                    for k in ("industryName", "industryGroupKor", "industry", "sectorName"):
                        if si.get(k):
                            cands.append(si[k])
            for c in cands:
                v = _ok(c)
                if v:
                    return v
    except Exception as _dg_e:
        _diag_note("get_stock_sector_kr", _dg_e)
        pass

    # ② 메인 페이지 업종 링크 (EUC-KR/UTF-8 자동 판별)
    try:
        res = requests.get(f"https://finance.naver.com/item/main.naver?code={code}",
                           headers={"User-Agent": "Mozilla/5.0"}, timeout=4)
        for enc in ("euc-kr", "utf-8"):
            try:
                soup = BeautifulSoup(res.content.decode(enc, "replace"), "html.parser")
            except Exception as _dg_e:
                _diag_note("get_stock_sector_kr", _dg_e)
                continue
            for a in soup.select("a"):
                href = a.get("href", "")
                if "sise_group_detail" in href and "upjong" in href:
                    v = _ok(a.get_text(strip=True))
                    if v:
                        return v
    except Exception as _dg_e:
        _diag_note("get_stock_sector_kr", _dg_e)
        pass
    return None


@st.cache_data(ttl=86400)
def get_us_sector_map():
    """S&P500 위키 표에서 {티커: 한글 섹터} 매핑 구성(낙폭 스캐너 표시용)."""
    try:
        url = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"
        res = requests.get(url, headers={'User-Agent': 'Mozilla/5.0'})
        df = pd.read_html(StringIO(res.text))[0]
        sec_col = next((c for c in df.columns if 'Sector' in str(c)), None)
        if not sec_col or 'Symbol' not in df.columns:
            return {}
        kmap = {"Information Technology": "IT/기술", "Financials": "금융", "Health Care": "헬스케어",
                "Consumer Discretionary": "임의소비재", "Consumer Staples": "필수소비재",
                "Industrials": "산업재", "Energy": "에너지", "Materials": "소재",
                "Real Estate": "부동산", "Utilities": "유틸리티", "Communication Services": "커뮤니케이션"}
        out = {}
        for _, row in df.iterrows():
            sym = str(row['Symbol']).replace('.', '-')
            sec = str(row[sec_col]).strip()
            out[sym] = kmap.get(sec, sec)
        return out
    except Exception as _dg_e:
        _diag_note("get_us_sector_map", _dg_e)
        return {}


@st.cache_data(ttl=600)
def get_kr_universe_naver(per_market=200):
    """네이버 모바일 API 시총 상위 → DataFrame[종목코드,종목명,등락률,현재가] (코스피+코스닥).
    fdr.StockListing('KRX')가 클라우드에서 막혀도 동작하는 네이버 기반 유니버스."""
    rows = []
    for mkt in ("KOSPI", "KOSDAQ"):
        got = 0
        for page in range(1, 6):
            data = _naver_json(f"https://m.stock.naver.com/api/stocks/marketValue/{mkt}?page={page}&pageSize=100")
            stocks = (data or {}).get("stocks") or []
            if not stocks:
                break
            for s in stocks:
                code = str(s.get("itemCode", "")).zfill(6)
                if not code or code == "000000":
                    continue
                pct = _num(s.get("fluctuationsRatio"))
                rows.append({
                    "종목코드": code,
                    "종목명": s.get("stockName", ""),
                    "등락률": float(pct) if pct is not None else 0.0,
                    "현재가": _num(s.get("closePrice")) or 0,
                })
                got += 1
            if got >= per_market or len(stocks) < 100:
                break
    if not rows:
        return pd.DataFrame()
    return pd.DataFrame(rows).drop_duplicates(subset=["종목코드"]).reset_index(drop=True)


def _kr_change_map():
    """{종목명: 오늘 등락률(%)} — 네이버 모바일 API(클라우드 호환) 우선, fdr 폴백."""
    df = get_kr_universe_naver()
    if df is None or df.empty:
        try:
            df = get_stock_list_by_market()
        except Exception:
            df = None
    if df is None or df.empty or "종목명" not in df.columns or "등락률" not in df.columns:
        return {}
    m = {}
    for nm, rt in zip(df["종목명"], df["등락률"]):
        try:
            m[str(nm).strip()] = float(rt)
        except Exception as _dg_e:
            _diag_note("_kr_change_map", _dg_e)
            continue
    return m


@st.cache_data(ttl=1800, show_spinner=False)
def get_trending_sectors(market="US"):
    """테마별 대표 종목 평균 등락률(강세 순). market: 'US'(yfinance) | 'KR'(네이버 모바일 API)."""
    if market == "KR":
        chg = _kr_change_map()
        if not chg:
            return []
        theme_map = KR_THEME_MAP
    else:
        import yfinance as yf
        uniq = sorted({t for lst in US_THEME_MAP.values() for t in lst})
        try:
            data = yf.download(uniq, period="5d", interval="1d",
                               group_by="ticker", threads=True, progress=False)
        except Exception as _dg_e:
            _diag_note("get_trending_sectors", _dg_e)
            return []
        if data is None or len(data) == 0:
            return []
        multi = isinstance(data.columns, pd.MultiIndex)
        chg = {}
        for tk in uniq:
            try:
                d = data[tk] if multi else data
                c = d["Close"].dropna()
                if len(c) >= 2:
                    chg[tk] = (float(c.iloc[-1]) / float(c.iloc[-2]) - 1) * 100
            except Exception as _dg_e:
                _diag_note("get_trending_sectors", _dg_e)
                continue
        theme_map = US_THEME_MAP

    out = []
    for theme, tickers in theme_map.items():
        members = [(t, chg[t]) for t in tickers if t in chg]
        if not members:
            continue
        members.sort(key=lambda x: x[1], reverse=True)
        avg = sum(p for _, p in members) / len(members)
        out.append({"theme": theme, "avg": avg, "members": members, "n": len(members)})
    out.sort(key=lambda x: x["avg"], reverse=True)
    return out


# =====================================================================
# [신규] 국장 수급 분석 (외국인·기관·개인 순매수) — 네이버 기반 (클라우드 호환)
#   순매수/순매도 TOP · 개미 vs 스마트머니 · 수급 주체 손바뀜(전환)
#   거래대금 상위 종목을 네이버(frgn.naver)에서 스캔 → 외국인·기관 순매매량×종가 → 억 환산
#   개인 ≈ -(외국인+기관). pykrx/KRX 불필요 → 클라우드에서도 동작.
# =====================================================================
def _fetch_stock_investor_2d(code):
    """frgn.naver → 오늘/어제 외국인·기관 순매매량 + 오늘 종가. 실패 시 None."""
    try:
        res = requests.get(f"https://finance.naver.com/item/frgn.naver?code={code}",
                           headers={"User-Agent": "Mozilla/5.0"}, timeout=5)
        soup = BeautifulSoup(res.text, "html.parser")
        tables = soup.select("table.type2")
        if len(tables) < 2:
            return None
        recs = []
        for row in tables[1].select("tr"):
            tds = row.select("td")
            if len(tds) < 9 or not tds[0].get_text(strip=True):
                continue

            def _n(i):
                t = tds[i].get_text(strip=True).replace(",", "").replace("+", "")
                if not t or t == "-":
                    return 0
                try:
                    return int(float(t))
                except Exception as _dg_e:
                    _diag_note("_n", _dg_e)
                    return 0
            recs.append({"close": _n(1), "inst": _n(5), "forn": _n(6)})
            if len(recs) >= 2:
                break
        if not recs:
            return None
        t0 = recs[0]
        t1 = recs[1] if len(recs) >= 2 else {"inst": 0, "forn": 0}
        return {"price": t0["close"], "inst": t0["inst"], "forn": t0["forn"],
                "inst_prev": t1["inst"], "forn_prev": t1["forn"]}
    except Exception as _dg_e:
        _diag_note("_fetch_stock_investor_2d", _dg_e)
        return None


@st.cache_data(ttl=1800, show_spinner=False)
def get_kr_investor_flows(universe_n=150):
    """시총 상위 종목의 외국인/기관/개인 순매수(억) + 전일 스마트머니 부호. 네이버 기반."""
    base = get_kr_universe_naver()
    if base is None or base.empty:
        try:
            b2 = get_stock_list_by_market()
            if b2 is not None and not b2.empty and "거래대금(억)" in b2.columns:
                base = b2[b2["시장"].isin(["코스피", "코스닥"])].sort_values("거래대금(억)", ascending=False)
        except Exception:
            base = None
    if base is None or base.empty or "종목코드" not in base.columns:
        return pd.DataFrame()
    base = base.head(universe_n)
    chg_map = {}
    if "등락률" in base.columns:
        for c, rt in zip(base["종목코드"], base["등락률"]):
            try:
                chg_map[str(c).zfill(6)] = float(rt)
            except Exception as _dg_e:
                _diag_note("get_kr_investor_flows", _dg_e)
                pass
    targets = [(str(c).zfill(6), str(n)) for c, n in zip(base["종목코드"], base["종목명"])]

    def _work(item):
        code, name = item
        d = _fetch_stock_investor_2d(code)
        if not d:
            return None
        price = d["price"] or 0
        forn = d["forn"] * price / 1e8
        inst = d["inst"] * price / 1e8
        return {"티커": code, "종목명": name, "등락률": chg_map.get(code, float("nan")),
                "외국인": forn, "기관": inst, "개인": -(forn + inst),
                "스마트머니": forn + inst,
                "스마트머니_전일": float(d["forn_prev"] + d["inst_prev"])}

    rows = []
    import concurrent.futures as _cf
    try:
        with _cf.ThreadPoolExecutor(max_workers=12) as ex:
            for r in ex.map(_work, targets):
                if r:
                    rows.append(r)
    except Exception:
        for it in targets:
            r = _work(it)
            if r:
                rows.append(r)
    return pd.DataFrame(rows) if rows else pd.DataFrame()


@st.cache_data(ttl=86400)
def get_us_scan_targets(limit=300):
    try:
        url = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"
        res = requests.get(url, headers={'User-Agent': 'Mozilla/5.0'})
        df = pd.read_html(StringIO(res.text))[0]
        targets = df[['Security', 'Symbol']].head(limit).values.tolist()
        return [(row[0], str(row[1]).replace('.', '-')) for row in targets]
    except Exception:
        return [('Apple', 'AAPL'), ('Microsoft', 'MSFT'), ('Nvidia', 'NVDA'), ('Tesla', 'TSLA')] * (limit // 4 + 1)

@st.cache_data(ttl=300)
def get_limit_stocks():
    def fetch_naver_limit(url, is_upper):
        try:
            res = requests.get(url, headers={'User-Agent': 'Mozilla/5.0'}, timeout=5)
            tables = pd.read_html(StringIO(res.content.decode('euc-kr', errors='replace')))
            for t in tables:
                if '종목명' in t.columns and '현재가' in t.columns:
                    t = t.dropna(subset=['종목명', '현재가'])
                    t = t[t['종목명'] != '종목명']
                    t = t[~t['종목명'].str.contains('스팩|ETN|선물|인버스|레버리지', na=False, regex=True)]
                    if not t.empty:
                        res_df = pd.DataFrame()
                        res_df['Name'] = t['종목명']
                        def to_f(x):
                            try: return float(str(x).replace(',', '').replace('%', '').replace('+', '').strip())
                            except Exception as _dg_e: _diag_note("to_f", _dg_e); return 0.0
                        res_df['Close'] = t['현재가'].apply(to_f)
                        res_df['Changes'] = t['전일비'].apply(to_f) if is_upper else -t['전일비'].apply(to_f)
                        if '등락률' in t.columns: res_df['ChagesRatio'] = t['등락률'].apply(to_f) if is_upper else -t['등락률'].apply(to_f)
                        else: res_df['ChagesRatio'] = 0.0
                        if '거래량' in t.columns: res_df['Amount_Ouk'] = (res_df['Close'] * t['거래량'].apply(to_f) / 100000000).astype(int)
                        else: res_df['Amount_Ouk'] = 0
                        res_df['PrevClose'] = res_df['Close'] - res_df['Changes']
                        res_df['Code'] = ""
                        return res_df.drop_duplicates(subset=['Name'])
        except Exception as _dg_e: _diag_note("fetch_naver_limit", _dg_e); pass
        return pd.DataFrame()

    upper_df = fetch_naver_limit("https://finance.naver.com/sise/sise_upper.naver", True)
    lower_df = fetch_naver_limit("https://finance.naver.com/sise/sise_lower.naver", False)
    krx = get_krx_stocks()
    empty_cols = ['Code', 'Sector', 'Close', 'Changes', 'ChagesRatio', 'Amount_Ouk', 'PrevClose', 'Name']
    
    if not upper_df.empty and not krx.empty:
        upper_df = pd.merge(upper_df, krx[['Name', 'Code', 'Sector']], on='Name', how='left')
        upper_df['Sector'] = upper_df['Sector'].fillna('개별이슈/기타')
    elif upper_df.empty: upper_df = pd.DataFrame(columns=empty_cols)
        
    if not lower_df.empty and not krx.empty:
        lower_df = pd.merge(lower_df, krx[['Name', 'Code', 'Sector']], on='Name', how='left')
        lower_df['Sector'] = lower_df['Sector'].fillna('개별이슈/기타')
    elif lower_df.empty: lower_df = pd.DataFrame(columns=empty_cols)

    for col in empty_cols:
        if col not in upper_df.columns: upper_df[col] = 0
        if col not in lower_df.columns: lower_df[col] = 0

    return upper_df.sort_values('Amount_Ouk', ascending=False), lower_df.sort_values('Amount_Ouk', ascending=False)

@st.cache_data(ttl=60)
def get_volume_surge_drop():
    def fetch_vol_table(url):
        try:
            res = requests.get(url, headers={'User-Agent': 'Mozilla/5.0'}, timeout=5)
            tables = pd.read_html(StringIO(res.content.decode('euc-kr', 'replace')))
            for t in tables:
                if '종목명' in t.columns and '현재가' in t.columns:
                    df = t.dropna(subset=['종목명', '현재가']).copy()
                    df = df[df['종목명'] != '종목명']
                    df = df[~df['종목명'].str.contains('스팩|ETN|선물|인버스|레버리지', na=False, regex=True)]
                    return df.dropna(axis=1, how='all').head(20).reset_index(drop=True)
        except Exception as _dg_e: _diag_note("fetch_vol_table", _dg_e); pass
        return pd.DataFrame()
    ts = int(time.time())
    surge_df = fetch_vol_table(f"https://finance.naver.com/sise/sise_quant_high.naver?_ts={ts}")
    drop_df = fetch_vol_table(f"https://finance.naver.com/sise/sise_quant_low.naver?_ts={ts}")
    return surge_df, drop_df

@st.cache_data(ttl=1800)
def get_us_volume_surge_drop(top_n=20):
    import yfinance as yf
    seen, targets = set(), []
    for nm, tk in US_VOL_UNIVERSE:
        if tk not in seen:
            seen.add(tk); targets.append((nm, tk))
    tickers = [t[1] for t in targets]
    name_map = {t[1]: t[0] for t in targets}
    try:
        data = yf.download(tickers, period="2mo", interval="1d",
                           group_by="ticker", threads=True, progress=False)
    except Exception as _dg_e:
        _diag_note("get_us_volume_surge_drop", _dg_e)
        return pd.DataFrame(), pd.DataFrame()
    if data is None or len(data) == 0:
        return pd.DataFrame(), pd.DataFrame()
    multi = isinstance(data.columns, pd.MultiIndex)
    rows = []
    for tk in tickers:
        try:
            d = data[tk] if multi else data
            vol = d["Volume"].dropna(); close = d["Close"].dropna()
            if len(vol) < 7 or len(close) < 2:
                continue
            today_v = float(vol.iloc[-1])
            base = vol.iloc[-21:-1] if len(vol) >= 21 else vol.iloc[:-1]
            avg_v = float(base.mean())
            if avg_v <= 0 or today_v <= 0:
                continue
            rows.append({
                "종목": f"{name_map.get(tk, tk)} ({tk})",
                "현재가": float(close.iloc[-1]),
                "등락률": (float(close.iloc[-1]) / float(close.iloc[-2]) - 1) * 100,
                "거래량 배율": today_v / avg_v,
            })
        except Exception as _dg_e:
            _diag_note("get_us_volume_surge_drop", _dg_e)
            continue
    if not rows:
        return pd.DataFrame(), pd.DataFrame()
    alldf = pd.DataFrame(rows)
    surge = alldf.sort_values("거래량 배율", ascending=False).head(top_n).reset_index(drop=True)
    drop_ = alldf.sort_values("거래량 배율", ascending=True).head(top_n).reset_index(drop=True)
    for x in (surge, drop_):
        x.index = x.index + 1; x.index.name = "순위"
    return surge, drop_


@st.cache_data(ttl=3600)
def get_market_warnings():
    def fetch_warning_table(url):
        try:
            res = requests.get(url, headers={'User-Agent': 'Mozilla/5.0'}, timeout=5)
            tables = pd.read_html(StringIO(res.content.decode('euc-kr', 'replace')))
            for t in tables:
                if '종목명' in t.columns:
                    df = t.dropna(subset=['종목명']).copy()
                    df = df[df['종목명'] != '종목명']
                    return df.dropna(axis=1, how='all').reset_index(drop=True)
        except Exception as _dg_e: _diag_note("fetch_warning_table", _dg_e); pass
        return pd.DataFrame()
    mgmt_df = fetch_warning_table("https://finance.naver.com/sise/management.naver")
    alert_df = fetch_warning_table("https://finance.naver.com/sise/investment_alert.naver")
    return mgmt_df, alert_df

def _norm_etf_name(s):
    s = str(s).upper()
    for b in _ETF_BRANDS:
        s = s.replace(b.upper(), '')
    return re.sub(r'[^가-힣A-Z0-9]', '', s)   # 공백·특수문자 제거

def resolve_etf_codes(etf_data, live_df):
    """live_df(실시간 ETF 목록: Code,Name)에서 이름으로 정확한 코드를 찾아 보정.
    리브랜딩(예: HANARO→PLUS)·오타 코드를 자동 교정하고, 매칭 시 정식 이름으로 갱신."""
    if live_df is None or live_df.empty:
        return etf_data
    exact, normed = {}, {}
    for _, r in live_df.iterrows():
        code = str(r['Code']).zfill(6)
        nm = str(r['Name'])
        exact[re.sub(r'\s+', '', nm)] = code
        k = _norm_etf_name(nm)
        if not k:
            continue
        if k in normed:
            if normed[k] is not None and normed[k][0] != code:
                normed[k] = None        # 정규화 이름이 모호하면 사용 안 함
        else:
            normed[k] = (code, nm)
    for item in etf_data:
        if not str(item.get('code', '')).isdigit():   # 미국·맞춤종목은 건드리지 않음
            continue
        nm_ws = re.sub(r'\s+', '', str(item['name']))
        if nm_ws in exact:                              # 1순위: 정확 일치
            item['code'] = exact[nm_ws]
            continue
        k = _norm_etf_name(item['name'])                # 2순위: 브랜드 무시 정규화 일치(모호하지 않을 때만)
        if k and normed.get(k):
            item['code'], item['name'] = normed[k][0], normed[k][1]
    return etf_data


# [v7.0] AI 밸류체인 리포트에서 '한국 수혜주' 종목명만 추출 → KRX 코드 매칭
def extract_beneficiary_stocks(report_text, krx_df, max_n=8):
    if not report_text or krx_df is None or krx_df.empty:
        return []
    name_to_code = dict(zip(krx_df['Name'].astype(str), krx_df['Code'].astype(str)))
    names_sorted = sorted(name_to_code.keys(), key=len, reverse=True)  # 긴 이름 우선(부분 오매칭 방지)
    found, seen = [], set()

    def add_match(cand):
        cand = re.sub(r'\(.*?\)', '', str(cand)).strip().strip('*•-· ')
        if not cand:
            return
        if cand in name_to_code and cand not in seen:          # 정확 일치
            found.append((cand, name_to_code[cand])); seen.add(cand); return
        for nm in names_sorted:                                # 부분 일치(긴 이름 우선)
            if len(nm) >= 2 and nm in cand and nm not in seen:
                found.append((nm, name_to_code[nm])); seen.add(nm); return

    # 1) AI가 마지막에 넣어준 '[수혜주]: A, B, C' 라인 우선 파싱
    m = re.search(r'\[?\s*수혜주[^\]:：]*\]?\s*[:：]\s*(.+)', report_text)
    if m:
        line = m.group(1).split('\n')[0]
        for c in re.split(r'[,/·、|]+', line):
            add_match(c)
            if len(found) >= max_n:
                return found[:max_n]

    # 2) 폴백: 리포트 본문 전체에서 KRX 종목명 직접 스캔 (3글자 이상만, 과매칭 방지)
    if len(found) < 2:
        for nm in names_sorted:
            if len(nm) >= 3 and nm in report_text and nm not in seen:
                found.append((nm, name_to_code[nm])); seen.add(nm)
                if len(found) >= max_n:
                    break
    return found[:max_n]

@st.cache_data(ttl=60)
def get_latest_naver_news():
    articles = []
    now_kst = datetime.utcnow() + timedelta(hours=9)
    three_hours_ago = now_kst - timedelta(hours=3)
    ts = int(now_kst.timestamp())
    def fetch_page(page):
        try:
            url = f"https://finance.naver.com/news/news_list.naver?mode=LSS2D&section_id=101&section_id2=258&page={page}&_ts={ts}"
            res = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=2.5) 
            if res.status_code != 200: return []
            soup = BeautifulSoup(res.content.decode('euc-kr', 'replace'), 'html.parser')
            page_articles = []
            for dl in soup.select("dl"):
                subject = dl.select_one(".articleSubject a")
                if not subject: continue
                title = subject.get_text(strip=True)
                link = "https://finance.naver.com" + subject['href'] if subject['href'].startswith("/") else subject['href']
                pub_time = ""
                wdate = dl.select_one(".wdate")
                if wdate:
                    raw_date = wdate.get_text(strip=True)
                    match = re.search(r'(\d{4}-\d{2}-\d{2})\s+(\d{2}:\d{2})', raw_date)
                    if match:
                        news_dt_str = f"{match.group(1)} {match.group(2)}"
                        try:
                            news_dt = datetime.strptime(news_dt_str, "%Y-%m-%d %H:%M")
                            if news_dt < three_hours_ago: continue 
                        except Exception as _dg_e: _diag_note("fetch_page", _dg_e); pass
                        pub_time = match.group(2) if match.group(1) == now_kst.strftime("%Y-%m-%d") else f"{match.group(1)[5:].replace('-', '/')} {match.group(2)}"
                    else:
                        match_time = re.search(r'(\d{2}:\d{2})', raw_date)
                        if match_time: pub_time = match_time.group(1)
                if not pub_time: pub_time = now_kst.strftime("%H:%M")
                page_articles.append({"title": title, "link": link, "time": pub_time})
            return page_articles
        except Exception as _dg_e: _diag_note("fetch_page", _dg_e); return []
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
        results = executor.map(fetch_page, [1, 2, 3]) 
        for res in results: articles.extend(res)
    return articles

def update_news_state():
    items = get_latest_naver_news()
    for item in reversed(items): 
        if item['link'] not in st.session_state.seen_links and item['title'] not in st.session_state.seen_titles:
            st.session_state.news_data.insert(0, item)
            st.session_state.seen_links.add(item['link'])
            st.session_state.seen_titles.add(item['title'])

@st.cache_data(ttl=3600)
def get_naver_research():
    try:
        url = "https://finance.naver.com/research/company_list.naver"
        res = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=3)
        soup = BeautifulSoup(res.content.decode('euc-kr', 'replace'), 'html.parser')
        table = soup.find('table', {'class': 'type_1'})
        rows = []
        for tr in table.find_all('tr'):
            tds = tr.find_all('td')
            if len(tds) >= 5:
                stock_name = tds[0].get_text(strip=True)
                if not stock_name: continue
                title_a = tds[1].find('a')
                title = title_a.get_text(strip=True) if title_a else tds[1].get_text(strip=True)
                link = "https://finance.naver.com/research/" + title_a['href'] if title_a and 'href' in title_a.attrs else ""
                broker = tds[2].get_text(strip=True)
                date = tds[4].get_text(strip=True)
                rows.append({"종목명": stock_name, "제목": title, "증권사": broker, "작성일": date, "원문링크": link})
        return pd.DataFrame(rows).head(30)
    except Exception: return pd.DataFrame()

@st.cache_data(ttl=86400)
def get_financial_deep_data(code):
    try:
        url = f"https://finance.naver.com/item/main.naver?code={code}"
        res = requests.get(url, headers={'User-Agent': 'Mozilla/5.0'}, timeout=4)
        tables = pd.read_html(StringIO(res.text))
        fin_df, peer_df = None, None
        for t in tables:
            str_t = str(t)
            if '매출액' in str_t and '영업이익' in str_t and '당기순이익' in str_t and fin_df is None: fin_df = t
            if '종목명' in str_t and '현재가' in str_t and 'PER' in str_t and peer_df is None: peer_df = t
        soup = BeautifulSoup(res.text, 'html.parser')
        c_area = soup.select_one('.r_cmp_area .f_up em')
        consensus = c_area.text if c_area else "증권사 목표가 추정치 없음"
        return fin_df, peer_df, consensus
    except Exception as _dg_e: _diag_note("get_financial_deep_data", _dg_e); return None, None, "데이터 스크래핑 오류"

@st.cache_data(ttl=120)
def get_intraday_estimate(code):
    """투자자별(외국인·기관·개인) 순매매 수량 — 네이버 모바일 증권 trend API.
    레거시 frgn HTML 페이지가 Streamlit Cloud IP에서 403/구조변경으로 불안정하여
    안정적인 m.stock.naver.com JSON API로 교체했다.
    ※ 분단위 장중 잠정치가 아니라 '가장 최근 거래일(확정)' 수치이며, 단위는 '주식 수'.
    반환: {"time": "MM/DD", "forgn": 외인순매수주, "inst": 기관순매수주,
           "indiv": 개인순매수주, "is_daily": True} | None (실패 시)"""
    if not str(code).isdigit():
        return None
    try:
        url = f"https://m.stock.naver.com/api/stock/{code}/trend"
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            "Referer": f"https://m.stock.naver.com/domestic/stock/{code}/total",
            "Accept": "application/json",
        }
        res = requests.get(url, headers=headers, timeout=5)
        if res.status_code != 200:
            return None
        data = res.json()
        # 응답은 최신 거래일이 [0]인 리스트 (혹은 dict로 감싸진 경우 대비)
        if isinstance(data, dict):
            for k in ("trends", "result", "list", "data"):
                if isinstance(data.get(k), list):
                    data = data[k]; break
        if not isinstance(data, list) or not data:
            return None
        row = data[0]

        def _num(v):
            """'+5,314,304' / '-1,061,741' → int. 파싱 실패 시 None."""
            if v is None:
                return None
            s = str(v).replace(',', '').replace('+', '').strip()
            return int(s) if s.lstrip('-').isdigit() else None

        f_val = _num(row.get("foreignerPureBuyQuant"))
        i_val = _num(row.get("organPureBuyQuant"))
        d_val = _num(row.get("individualPureBuyQuant"))
        if f_val is None and i_val is None:
            return None

        # 날짜 YYYYMMDD → MM/DD (기존 UI의 'time' 자리에 표기)
        bd = str(row.get("bizdate", ""))
        time_label = f"{bd[4:6]}/{bd[6:8]}" if len(bd) == 8 and bd.isdigit() else "최근"

        return {
            "time": time_label,
            "forgn": f_val or 0,
            "inst": i_val or 0,
            "indiv": d_val or 0,
            "is_daily": True,
        }
    except Exception as _dg_e:
        _diag_note("get_intraday_estimate", _dg_e)
        return None


@st.cache_data(ttl=120)
def get_intraday_estimate_debug(code):
    """장중 잠정치가 왜 안 잡히는지 진단용 — 네이버 응답/표 구조를 그대로 보여준다."""
    info = {"http": None, "tables": 0, "summaries": [], "cand_via": "없음", "rows": [], "foreign_rows": [], "err": ""}
    try:
        url = f"https://finance.naver.com/item/frgn.naver?code={code}"
        res = requests.get(url, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}, timeout=4)
        info["http"] = res.status_code
        res.encoding = 'euc-kr'
        soup = BeautifulSoup(res.text, 'html.parser')
        all_t = soup.find_all('table')
        info["tables"] = len(all_t)
        info["summaries"] = [((t.get('summary', '') or '').strip())[:40] for t in all_t][:10]
        # '외국계' 가 들어간 행(거래원 추정합) 원본도 수집 → 파서 정합성 확인용
        for tr in soup.find_all('tr'):
            txt = tr.get_text(" ", strip=True)
            if '외국계' in txt:
                info["foreign_rows"].append(txt[:120])
            if len(info["foreign_rows"]) >= 4:
                break
        cand = None
        for t in all_t:
            if '잠정' in (t.get('summary', '') or ''):
                cand = t; info["cand_via"] = "summary:잠정"; break
        if cand is None:
            t2 = soup.select('table.type2')
            if t2:
                cand = t2[0]; info["cand_via"] = "type2[0] 폴백"
        if cand is not None:
            for tr in cand.find_all('tr')[:6]:
                tds = tr.find_all('td')
                if tds:
                    info["rows"].append(" | ".join(td.get_text(strip=True) for td in tds)[:90])
    except Exception as e:
        info["err"] = f"{type(e).__name__}: {e}"
    return info


@st.cache_data(ttl=120)
def get_foreign_broker_estimate(code):
    """장중 실시간 '외국계 거래원 순매수 추정'(KRX 거래원 기준).
    네이버 frgn 페이지의 '거래원 동향' 표에서 '외국계 거래원 매수/매도량 추정합'을 뽑는다.
    외국인 '확정 순매수'와는 다른 '외국계 창구 추정치'지만, 장중 외국인 매매를 가늠하는
    실시간 프록시로 널리 쓰인다. 반환: {"sell":매도추정, "buy":매수추정, "net":순매수추정} | None"""
    if not str(code).isdigit():
        return None
    try:
        url = f"https://finance.naver.com/item/frgn.naver?code={code}"
        res = requests.get(url, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}, timeout=4)
        res.encoding = 'euc-kr'
        soup = BeautifulSoup(res.text, 'html.parser')
        sell = buy = None
        for tr in soup.find_all('tr'):
            txt = tr.get_text(" ", strip=True)
            if '외국계' in txt and '추정' in txt:
                nums = [int(n.replace(',', '')) for n in re.findall(r'-?[\d,]{2,}', txt)
                        if n.replace(',', '').lstrip('-').isdigit()]
                if '매도' in txt and '매수' in txt and len(nums) >= 2:
                    sell, buy = nums[0], nums[1]
                    break
                elif '매도' in txt and nums and sell is None:
                    sell = nums[0]
                elif '매수' in txt and nums and buy is None:
                    buy = nums[0]
        if sell is not None and buy is not None:
            return {"sell": sell, "buy": buy, "net": buy - sell}
        return None
    except Exception as _dg_e:
        _diag_note("get_foreign_broker_estimate", _dg_e)
        return None


@st.cache_data(ttl=120)
def get_kr_market_breadth():
    """국내(코스피+코스닥) 등락 종목 수(상승/보합/하락) — 네이버 지수 페이지에서 합산.
    ★속도 핵심: 개별 종목 2,600여 개를 받지 않고, 네이버가 '집계해 둔' 종목 수만
      가볍게 2회 요청(각 timeout 3.5s) + 2분 캐시 → 대시보드 부하 거의 없음. 실패 시 None."""
    def _one(mkt):
        try:
            url = f"https://finance.naver.com/sise/sise_index.naver?code={mkt}"
            res = requests.get(url, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}, timeout=3.5)
            res.encoding = 'euc-kr'
            text = BeautifulSoup(res.text, 'html.parser').get_text(" ", strip=True)
            def f(kw):
                # '상승 243' / '상승종목 243' / '상승 종목수 243' 모두 매칭, '상승률 1.2'·'상한 0'은 회피
                m = re.search(kw + r'(?:\s*종목수?)?\s*([\d,]+)', text)
                return int(m.group(1).replace(',', '')) if m else None
            up, flat, down = f('상승'), f('보합'), f('하락')
            if up is None or down is None:
                return None
            return (up, flat or 0, down)
        except Exception as _dg_e:
            _diag_note("_one", _dg_e)
            return None
    parts = [r for r in (_one('KOSPI'), _one('KOSDAQ')) if r]
    if not parts:
        return None
    up = sum(p[0] for p in parts)
    flat = sum(p[1] for p in parts)
    down = sum(p[2] for p in parts)
    total = up + flat + down
    if not (50 <= total <= 6000):   # 비정상 파싱이면 실패 처리
        return None
    return {"up": up, "flat": flat, "down": down, "total": total, "markets": len(parts)}


def _naver_json(url, timeout=7):
    """네이버 증권 API GET → JSON. 실패/비-JSON이면 None. (일시적 지연 대비 타임아웃 7초)"""
    try:
        r = requests.get(url, headers=NAVER_API_HDRS, timeout=timeout)
        if r.status_code != 200 or "json" not in r.headers.get("Content-Type", "").lower():
            return None
        return r.json()
    except Exception as _dg_e:
        _diag_note("_naver_json", _dg_e)
        return None


def _diag_index_endpoints():
    """[추가] 진단 도구: 후보 API에 직접 요청해 status code와 응답 앞부분을 화면에 출력.
    4개 신규 기능(미니차트/주요지수/시총TOP/업종등락)에 쓸 엔드포인트를 한 번에 점검한다."""
    HDRS = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36",
        "Referer": "https://m.stock.naver.com/",
        "Accept": "application/json, text/plain, */*",
    }
    groups = {
        "① 지수 시세/수급 (이미 작동)": [
            "https://m.stock.naver.com/api/index/KOSPI/basic",
            "https://m.stock.naver.com/api/index/KOSPI/integration",
            "https://m.stock.naver.com/api/index/KOSPI/trend",
        ],
        "② 지수 미니차트(일봉 스파크라인)": [
            "https://m.stock.naver.com/api/index/KOSPI/price?pageSize=30&page=1",
            "https://api.stock.naver.com/chart/domestic/index/KOSPI?periodType=dayCandle&count=30",
            "https://m.stock.naver.com/api/chart/domestic/index/KOSPI?periodType=dayCandle&count=30",
        ],
        "③ 주요지수/환율/유가 바": [
            "https://m.stock.naver.com/api/home/majorIndex",
            "https://m.stock.naver.com/api/index/KPI200/basic",
            "https://m.stock.naver.com/api/marketindex/exchange/FX_USDKRW",
            "https://api.stock.naver.com/marketindex/exchange/FX_USDKRW",
            "https://api.stock.naver.com/marketindex/oil/OIL_CL",
        ],
        "④ 시가총액 TOP 종목": [
            "https://m.stock.naver.com/api/stocks/marketValue/KOSPI?page=1&pageSize=10",
            "https://api.stock.naver.com/stock/marketValue/KOSPI?page=1&pageSize=10",
        ],
        "⑤ 업종/테마 등락률": [
            "https://m.stock.naver.com/api/stocks/industry?page=1&pageSize=20",
            "https://api.stock.naver.com/industry",
            "https://m.stock.naver.com/api/home/industry",
        ],
    }
    for title, urls in groups.items():
        st.markdown(f"### {title}")
        for u in urls:
            try:
                r = requests.get(u, headers=HDRS, timeout=5)
                ct = r.headers.get("Content-Type", "")
                ok = r.status_code == 200 and "json" in ct.lower()
                badge = "✅" if ok else "⚠️"
                body = r.text[:700] if r.text else ""
                st.markdown(f"{badge} **`{u}`** → `{r.status_code}` · `{ct}`")
                if body:
                    st.code(body, language="json")
            except Exception as e:
                st.markdown(f"❌ **`{u}`** → `{type(e).__name__}: {e}`")
    st.caption("✅ 표시된 URL의 JSON 응답(특히 키 이름)을 복사해 주시면, 4개 기능을 정확한 키로 완성하겠습니다.")


@st.cache_data(ttl=120)
def get_kr_index_panel():
    """[추가] 네이버 모바일 스타일 메인 지수 패널 데이터.
    코스피·코스닥 각각: 지수값/등락률/등락폭/상승·보합·하락 종목수 + 전체 투자자별 순매매(외국인/기관/개인).
    확인된 네이버 API 키 사용:
      - /index/{KOSPI|KOSDAQ}/basic   → closePrice, compareToPreviousClosePrice, fluctuationsRatio, compareToPreviousPrice.name(RISING/FALLING)
      - /index/{KOSPI|KOSDAQ}/trend   → personalValue(개인), foreignValue(외국인), institutionalValue(기관)  (단위: 억원, 부호 포함 문자열)
    상승/보합/하락 종목수는 지수 basic/integration에 없어 기존 get_kr_market_breadth() 폴백 사용."""
    def _scrape(mkt):
        price = diff = pct = None
        sign = 0
        forgn = inst = indiv = None

        # 1) 시세
        basic = _naver_json(f"https://m.stock.naver.com/api/index/{mkt}/basic")
        if basic:
            price = _num(basic.get("closePrice"))
            diff = _num(basic.get("compareToPreviousClosePrice"))
            pct = _num(basic.get("fluctuationsRatio"))
            nm = (basic.get("compareToPreviousPrice") or {}).get("name", "")
            sign = 1 if nm == "RISING" else (-1 if nm == "FALLING" else 0)
            if sign == 0 and diff is not None:
                sign = 1 if diff > 0 else (-1 if diff < 0 else 0)
            if diff is not None:
                diff = abs(diff)
            if pct is not None:
                pct = abs(pct)

        # 2) 투자자별 순매매 (억원)
        trend = _naver_json(f"https://m.stock.naver.com/api/index/{mkt}/trend")
        if trend:
            indiv = _num(trend.get("personalValue"))
            forgn = _num(trend.get("foreignValue"))
            inst = _num(trend.get("institutionalValue"))

        forgn = int(round(forgn)) if forgn is not None else None
        inst = int(round(inst)) if inst is not None else None
        indiv = int(round(indiv)) if indiv is not None else None

        # [폴백] 시세 실패 시 구형 finance.naver.com
        if price is None:
            try:
                fres = requests.get(
                    f"https://finance.naver.com/sise/sise_index.naver?code={mkt}",
                    headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"},
                    timeout=4,
                )
                fres.encoding = 'euc-kr'
                fsoup = BeautifulSoup(fres.text, 'html.parser')
                now_el = fsoup.select_one('#now_value')
                if now_el:
                    price = _num(now_el.get_text(strip=True))
                chg_el = fsoup.select_one('#change_value_and_rate')
                if chg_el:
                    nums = re.findall(r'[\d,]+\.\d+', chg_el.get_text(" ", strip=True))
                    if len(nums) >= 2:
                        if diff is None:
                            diff = _num(nums[0])
                        if pct is None:
                            pct = _num(nums[1])
                    cls = ' '.join(chg_el.get('class') or [])
                    if sign == 0:
                        sign = -1 if 'down' in cls else (1 if 'up' in cls else 0)
            except Exception as _dg_e:
                _diag_note("_scrape", _dg_e)
                pass

        if price is None:
            return None
        return {
            "name": "코스피" if mkt == "KOSPI" else "코스닥",
            "price": price, "diff": diff, "pct": pct, "sign": sign,
            "up": None, "flat": None, "down": None,   # 종목수는 렌더에서 breadth 폴백으로 채움
            "forgn": forgn, "inst": inst, "indiv": indiv,
        }

    kospi = _scrape("KOSPI")
    kosdaq = _scrape("KOSDAQ")
    if not kospi and not kosdaq:
        return None
    return {"KOSPI": kospi, "KOSDAQ": kosdaq}


@st.cache_data(ttl=300)
def get_index_spark(mkt, n=30):
    """[추가] 지수 일봉 종가 배열(최신 n개) — 미니차트(스파크라인)용.
    /api/index/{mkt}/price 는 최신순 배열. 오래된→최신 순으로 정렬해 종가 리스트 반환."""
    data = _naver_json(f"https://m.stock.naver.com/api/index/{mkt}/price?pageSize={n}&page=1")
    if not isinstance(data, list) or not data:
        return None
    rows = []
    for it in data:
        c = _num(it.get("closePrice"))
        d = it.get("localTradedAt")
        if c is not None:
            rows.append((d, c))
    if len(rows) < 2:
        return None
    rows.reverse()  # 과거 → 현재
    return [c for _, c in rows]


@st.cache_data(ttl=120)
def get_major_indices():
    """[추가] 주요 지표 바: 코스피200 + 원/달러 환율. (유가 엔드포인트는 없어 제외)"""
    out = []
    kpi = _naver_json("https://m.stock.naver.com/api/index/KPI200/basic")
    if kpi:
        nm = (kpi.get("compareToPreviousPrice") or {}).get("name", "")
        out.append({
            "label": "코스피200",
            "value": _num(kpi.get("closePrice")),
            "pct": _num(kpi.get("fluctuationsRatio")),
            "sign": 1 if nm == "RISING" else (-1 if nm == "FALLING" else 0),
            "fmt": "{:,.2f}",
        })
    fx = _naver_json("https://api.stock.naver.com/marketindex/exchange/FX_USDKRW")
    if fx:
        info = fx.get("exchangeInfo", fx)
        nm = (info.get("fluctuationsType") or {}).get("name", "")
        out.append({
            "label": "원/달러",
            "value": _num(info.get("closePrice")),
            "pct": _num(info.get("fluctuationsRatio")),
            "sign": 1 if nm == "RISING" else (-1 if nm == "FALLING" else 0),
            "fmt": "{:,.2f}원",
        })
    return out or None


@st.cache_data(ttl=120)
def get_marketcap_top(mkt="KOSPI", n=10):
    """[추가] 시가총액 TOP 종목 — /api/stocks/marketValue/{mkt}."""
    data = _naver_json(f"https://m.stock.naver.com/api/stocks/marketValue/{mkt}?page=1&pageSize={n}")
    if not data or "stocks" not in data:
        return None
    rows = []
    for s in data["stocks"][:n]:
        nm = (s.get("compareToPreviousPrice") or {}).get("name", "")
        rows.append({
            "code": s.get("itemCode"),
            "name": s.get("stockName"),
            "price": _num(s.get("closePrice")),
            "pct": _num(s.get("fluctuationsRatio")),
            "sign": 1 if nm == "RISING" else (-1 if nm == "FALLING" else 0),
            "cap": s.get("marketValueHangeul"),
        })
    return rows or None


@st.cache_data(ttl=180)
def get_industry_changes(n=20):
    """[추가] 업종별 등락률 — /api/stocks/industry. changeRate 기준 정렬돼 옴."""
    data = _naver_json(f"https://m.stock.naver.com/api/stocks/industry?page=1&pageSize={n}")
    if not data or "groups" not in data:
        return None
    rows = []
    for g in data["groups"]:
        rows.append({
            "name": g.get("name"),
            "rate": _num(g.get("changeRate")),
            "rise": g.get("riseCount"),
            "fall": g.get("fallCount"),
            "total": g.get("totalCount"),
        })
    return rows or None


@st.cache_data(ttl=3600)
def get_investor_trend(code):
    try:
        res = requests.get(f"https://finance.naver.com/item/frgn.naver?code={code}", headers={"User-Agent": "Mozilla/5.0"}, timeout=3)
        soup = BeautifulSoup(res.text, 'html.parser')
        rows = soup.select('table.type2')[1].select('tr')
        i_vals, f_vals, p_vals = [], [], []
        for row in rows:
            tds = row.select('td')
            if len(tds) < 9 or not tds[0].text.strip(): continue 
            try:
                i_val = int(tds[5].text.strip().replace(',', '').replace('+', ''))
                f_val = int(tds[6].text.strip().replace(',', '').replace('+', ''))
                p_val = -(i_val + f_val) 
                i_vals.append(i_val)
                f_vals.append(f_val)
                p_vals.append(p_val)
            except Exception as _dg_e: _diag_note("get_investor_trend", _dg_e); pass
            if len(i_vals) >= 5: break 
            
        def calc_trend(vals):
            if not vals: return "0 (➖중립)", 0
            total = sum(vals)
            buy_streak, sell_streak = 0, 0
            for v in vals:
                if v > 0: buy_streak += 1
                else: break
            for v in vals:
                if v < 0: sell_streak += 1
                else: break
            if total > 0: desc = f"🔥{buy_streak}일 연속 매집" if buy_streak >= 3 else "🔥매집"
            elif total < 0: desc = f"💧{sell_streak}일 연속 매도" if sell_streak >= 3 else "💧매도"
            else: desc = "➖중립"
            base = f"+{total:,}" if total > 0 else f"{total:,}"
            return f"{base} ({desc})", buy_streak

        i_str, i_streak = calc_trend(i_vals)
        f_str, f_streak = calc_trend(f_vals)
        p_str, _ = calc_trend(p_vals)
        return i_str, f_str, p_str, i_streak, f_streak
    except Exception as _dg_e: _diag_note("get_investor_trend", _dg_e); return "조회불가", "조회불가", "조회불가", 0, 0

@st.cache_data(ttl=600)
def get_institution_buy_trend(code):
    """기관(전체) 최근 5거래일 순매수 합계 & 연속 순매수 일수 — 네이버 모바일 trend API.
    (기존 frgn HTML 스크래핑은 캐시도 없고 종목마다 순차 호출돼 느렸음 → JSON API + 캐시로 교체)
    ※ '연기금'이 아니라 '기관 전체(organ)' 기준이다. 반환: (기관5일합:주, 연속순매수일수)"""
    if not str(code).isdigit():
        return 0, 0
    try:
        url = f"https://m.stock.naver.com/api/stock/{code}/trend"
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            "Referer": f"https://m.stock.naver.com/domestic/stock/{code}/total",
            "Accept": "application/json",
        }
        res = requests.get(url, headers=headers, timeout=5)
        if res.status_code != 200:
            return 0, 0
        rows = res.json()
        if isinstance(rows, dict):
            for k in ("trends", "result", "list", "data"):
                if isinstance(rows.get(k), list):
                    rows = rows[k]; break
        if not isinstance(rows, list):
            return 0, 0

        def _num(v):
            if v is None: return None
            s = str(v).replace(',', '').replace('+', '').strip()
            return int(s) if s.lstrip('-').isdigit() else None

        inst_sum, streak, broke, count = 0, 0, False, 0
        for row in rows:
            i_val = _num(row.get("organPureBuyQuant"))
            if i_val is None:
                continue
            inst_sum += i_val
            if i_val > 0 and not broke:
                streak += 1
            elif i_val <= 0:
                broke = True
            count += 1
            if count >= 5:
                break
        return inst_sum, streak
    except Exception as _dg_e:
        _diag_note("get_institution_buy_trend", _dg_e)
        return 0, 0


# 하위 호환 별칭 — 기존 호출부(get_pension_fund_trend)를 그대로 유지하기 위함.
# 실제로는 '연기금'이 아니라 '기관 전체' 추세이며, 명칭은 점진적으로 정리한다.
get_pension_fund_trend = get_institution_buy_trend

@st.cache_data(ttl=3600)
def get_daily_sise_and_investor(code):
    """일별 시세 + 투자자별 순매매(외국인·기관·개인) — 네이버 모바일 trend API.
    종가·전일비·등락률·수급을 '같은 소스의 같은 날짜 확정치'로 받아 표 정합성을 보장한다.
    (기존 frgn HTML은 개인을 -(외인+기관) 추정으로 채워 첫 행과 어긋나는 문제가 있었음)
    수급 단위는 '주식 수'."""
    if not str(code).isdigit():
        return pd.DataFrame()
    try:
        url = f"https://m.stock.naver.com/api/stock/{code}/trend"
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            "Referer": f"https://m.stock.naver.com/domestic/stock/{code}/total",
            "Accept": "application/json",
        }
        res = requests.get(url, headers=headers, timeout=5)
        if res.status_code != 200:
            return pd.DataFrame()
        rows = res.json()
        if isinstance(rows, dict):
            for k in ("trends", "result", "list", "data"):
                if isinstance(rows.get(k), list):
                    rows = rows[k]; break
        if not isinstance(rows, list) or not rows:
            return pd.DataFrame()

        def _num(v):
            if v is None: return None
            s = str(v).replace(',', '').replace('+', '').strip()
            return int(s) if s.lstrip('-').isdigit() else None

        def fmt_vol(v):
            if v is None: return "-"
            if v > 0: return f"🔴 +{v:,}"
            if v < 0: return f"🔵 {v:,}"
            return "0"

        data = []
        for row in rows[:10]:
            bd = str(row.get("bizdate", ""))
            date = f"{bd[0:4]}.{bd[4:6]}.{bd[6:8]}" if len(bd) == 8 and bd.isdigit() else bd
            close = str(row.get("closePrice", "")).strip()
            chg = _num(row.get("compareToPreviousClosePrice"))
            sign_txt = (row.get("compareToPreviousPrice") or {}).get("text", "")
            diff = f"{sign_txt} {abs(chg):,}" if chg is not None else "-"
            close_n = _num(close)
            if close_n is not None and chg is not None and (close_n - chg) != 0:
                rate = f"{'+' if chg > 0 else ''}{chg / (close_n - chg) * 100:.2f}%"
            else:
                rate = "-"
            f_v = _num(row.get("foreignerPureBuyQuant"))
            i_v = _num(row.get("organPureBuyQuant"))
            d_v = _num(row.get("individualPureBuyQuant"))
            data.append({
                "날짜": date, "종가": close, "전일비": diff, "등락률": rate,
                "외국인": fmt_vol(f_v), "기관": fmt_vol(i_v), "개인": fmt_vol(d_v),
            })
        return pd.DataFrame(data)
    except Exception:
        return pd.DataFrame()

def get_fundamentals(ticker_code):
    if str(ticker_code).isdigit():
        per, pbr, target_price = 'N/A', 'N/A', 'N/A'
        try:
            url = f"https://finance.naver.com/item/main.naver?code={ticker_code}"
            res = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=5)
            soup = BeautifulSoup(res.text, 'html.parser')
            per = soup.select_one('#_per').text if soup.select_one('#_per') else 'N/A'
            pbr = soup.select_one('#_pbr').text if soup.select_one('#_pbr') else 'N/A'
            for tr in soup.find_all('tr'):
                th = tr.find('th')
                if th and '목표주가' in th.text:
                    td = tr.find('td')
                    if td:
                        text_content = td.get_text(separator=' ', strip=True)
                        possible_prices = []
                        for n_str in re.findall(r'[0-9,]+', text_content):
                            clean_n = n_str.replace(',', '')
                            if clean_n.isdigit(): possible_prices.append(int(clean_n))
                        if possible_prices:
                            max_val = max(possible_prices)
                            if max_val > 10: target_price = str(max_val)
                    break
        except Exception as _dg_e: _diag_note("get_fundamentals", _dg_e); pass

        fcf, shares = None, None
        try:
            t_obj = yf.Ticker(f"{ticker_code}.KS")
            info = t_obj.info
            
            if not info or 'sharesOutstanding' not in info:
                t_obj = yf.Ticker(f"{ticker_code}.KQ")
                info = t_obj.info

            raw_shares = info.get('sharesOutstanding')
            if raw_shares: shares = raw_shares / 1000000.0

            cf = t_obj.cash_flow
            if cf is not None and not cf.empty and 'Free Cash Flow' in cf.index:
                fcf_raw = cf.loc['Free Cash Flow'].iloc[0]
                if pd.notna(fcf_raw): fcf = fcf_raw / 100000000.0 
        except Exception as _dg_e: _diag_note("get_fundamentals", _dg_e); pass

        return per, pbr, fcf, shares, target_price
        
    else:
        try:
            t_obj = yf.Ticker(ticker_code)
            info = t_obj.info
            per = round(info.get('trailingPE', 0), 2) if info.get('trailingPE') else 'N/A'
            pbr = round(info.get('priceToBook', 0), 2) if info.get('priceToBook') else 'N/A'
            target_price = info.get('targetMeanPrice', 'N/A')
            fcf, shares = None, None

            raw_shares = info.get('sharesOutstanding')
            if raw_shares: shares = raw_shares / 1000000.0

            try:
                cf = t_obj.cash_flow
                if cf is not None and not cf.empty and 'Free Cash Flow' in cf.index:
                    fcf_raw = cf.loc['Free Cash Flow'].iloc[0]
                    if pd.notna(fcf_raw): fcf = fcf_raw / 100000000.0 
            except Exception as _dg_e: _diag_note("get_fundamentals", _dg_e); pass
            
            return per, pbr, fcf, shares, target_price
        except Exception as _dg_e: 
            _diag_note("get_fundamentals", _dg_e)
            return 'N/A', 'N/A', None, None, 'N/A'

# ── [NEW] AI 적정주가 (PER·PBR 멀티팩터 밸류에이션) ──────────────────────
@st.cache_data(ttl=3600)
def get_sector_per(ticker_code):
    """네이버 증권 메인 페이지에서 '동일업종 PER'을 긁어온다. (국내 전용, 1시간 캐시)"""
    if not str(ticker_code).isdigit():
        return None
    try:
        url = f"https://finance.naver.com/item/main.naver?code={ticker_code}"
        res = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=5)
        soup = BeautifulSoup(res.text, 'html.parser')
        for th in soup.find_all('th'):
            if '동일업종 PER' in th.get_text():
                td = th.find_next('td')
                if td:
                    m = re.search(r'([\d,]+\.?\d*)', td.get_text(strip=True).replace(',', ''))
                    if m:
                        v = float(m.group(1))
                        if 0 < v < 500:
                            return v
        return None
    except Exception as _dg_e:
        _diag_note("get_sector_per", _dg_e)
        return None

def calc_ai_target_price(per, pbr, current_price, ticker_code, use_sector_per=True):
    """PER·PBR 역산(EPS·BPS·ROE)으로 AI 적정주가를 산출.
    ① 그레이엄 공식: √(22.5 × EPS × BPS)
    ② S-RIM(잔여이익모델 약식): BPS × (ROE ÷ 요구수익률 8%)
    ③ 업종 상대가치(국내): EPS × 동일업종 PER  ※ use_sector_per=True일 때만 (HTTP 1회 발생)
    → 산출 가능한 방법들의 평균값을 반환. 실패 시 (None, 사유) 반환.
    ⚡ 스캐너 등 대량 호출 경로에서는 use_sector_per=False로 호출해 네트워크 부하를 0으로 유지."""
    try:
        curr = float(current_price)
        if curr <= 0:
            return None, "현재가 오류"
        per_v = float(str(per).replace(',', ''))
        pbr_v = float(str(pbr).replace(',', ''))
        if per_v <= 0:
            return None, "적자 기업 (PER 음수/없음)"
        if pbr_v <= 0:
            return None, "PBR 데이터 없음"

        eps = curr / per_v          # 주당순이익 역산
        bps = curr / pbr_v          # 주당순자산 역산
        roe = (eps / bps) * 100.0   # ROE(%) = PBR/PER × 100

        methods = []
        details = []

        # ① 그레이엄 공식
        graham = (22.5 * eps * bps) ** 0.5
        methods.append(graham)
        details.append(f"그레이엄 {graham:,.0f}")

        # ② S-RIM 약식 (요구수익률 8%, ROE 40% 초과 시 과대평가 방지 캡)
        roe_capped = min(roe, 40.0)
        srim = bps * (roe_capped / 8.0)
        methods.append(srim)
        details.append(f"S-RIM {srim:,.0f}")

        # ③ 업종 PER 상대가치 (국내 종목만 · 상세 카드에서만 조회해 스캔 부하 방지)
        sec_per = get_sector_per(ticker_code) if use_sector_per else None
        if sec_per:
            rel = eps * sec_per
            methods.append(rel)
            details.append(f"업종PER {rel:,.0f}")

        ai_target = sum(methods) / len(methods)
        # 극단값 방어: 현재가 대비 ±70% 범위로 클리핑
        ai_target = max(curr * 0.3, min(ai_target, curr * 1.7))

        detail_str = f"EPS {eps:,.0f} · BPS {bps:,.0f} · ROE {roe:.1f}%" + (f" · 업종PER {sec_per:.1f}배" if sec_per else "")
        return ai_target, detail_str
    except Exception as _dg_e:
        _diag_note("calc_ai_target_price", _dg_e)
        return None, "산출 불가"

@st.cache_data(ttl=3600)
def get_historical_data(ticker_code, days):
    if str(ticker_code).isdigit():
        try:
            url = f"https://fchart.stock.naver.com/sise.nhn?symbol={ticker_code}&timeframe=day&count={days}&requestType=0"
            res = requests.get(url, headers={'User-Agent': 'Mozilla/5.0'}, timeout=5)
            soup = BeautifulSoup(res.text, 'html.parser')
            items = soup.find_all('item')
            data = []
            for item in items:
                val = item.get('data')
                if val:
                    parts = val.split('|')
                    data.append([pd.to_datetime(parts[0]), float(parts[1]), float(parts[2]), float(parts[3]), float(parts[4]), float(parts[5])])
            if data:
                df = pd.DataFrame(data, columns=['Date', 'Open', 'High', 'Low', 'Close', 'Volume'])
                df.set_index('Date', inplace=True)
                return df
        except Exception as _dg_e: _diag_note("get_historical_data", _dg_e); pass
        
        try:
            df = yf.Ticker(f"{ticker_code}.KS").history(period=f"{days}d")
            if not df.empty:
                df.index = df.index.tz_localize(None)
                return df
        except Exception as _dg_e: _diag_note("get_historical_data", _dg_e); pass
        
    else:
        # 💡 [핵심 우회] 미국 주식 연속 조회 시 차단 방어 (세션 위장 + yahooquery 2중 콤보)
        try:
            session = requests.Session()
            session.headers.update({'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'})
            df = yf.Ticker(ticker_code, session=session).history(period=f"{days}d")
            if not df.empty:
                df.index = df.index.tz_localize(None)
                return df
        except Exception as _dg_e: _diag_note("get_historical_data", _dg_e); pass
        
        try:
            from yahooquery import Ticker as yq_Ticker
            yq_t = yq_Ticker(ticker_code)
            df = yq_t.history(period=f"{days}d")
            if isinstance(df, pd.DataFrame) and not df.empty:
                df = df.reset_index()
                df = df.rename(columns={'date': 'Date', 'open': 'Open', 'high': 'High', 'low': 'Low', 'close': 'Close', 'volume': 'Volume'})
                df.set_index('Date', inplace=True)
                df.index = pd.to_datetime(df.index).tz_localize(None)
                return df[['Open', 'High', 'Low', 'Close', 'Volume']]
        except Exception as _dg_e: _diag_note("get_historical_data", _dg_e); pass
        
    return pd.DataFrame()

# =====================================================================
# [신규] 매물대 지도 (Volume-by-Price) + 종목 타임머신 (과거 유사패턴)
#  - 둘 다 일봉 OHLCV(get_historical_data 결과)만으로 계산. 틱 데이터 불필요.
#  - 카드에서 토글로 '열 때만' 계산 → 평소 렌더 속도에 영향 없음.
# =====================================================================
def nb_volume_profile(df, bins=12, current_price=None):
    """일봉 거래량을 그날 [Low, High] 범위에 겹치는 만큼 비례 배분해 가격대별로 합산."""
    try:
        d = df[['High', 'Low', 'Volume']].dropna().copy()
    except Exception as _dg_e:
        _diag_note("nb_volume_profile", _dg_e)
        return None
    if d.empty:
        return None
    lo = float(d['Low'].min()); hi = float(d['High'].max())
    if hi <= lo:
        hi = lo * 1.001 + 1e-9
    edges = np.linspace(lo, hi, bins + 1)
    vol = np.zeros(bins)
    H = d['High'].to_numpy(float); L = d['Low'].to_numpy(float); V = d['Volume'].to_numpy(float)
    for h, l, v in zip(H, L, V):
        if v <= 0 or h < l:
            continue
        if h - l <= 0:
            idx = min(bins - 1, max(0, int(np.searchsorted(edges, l, "right") - 1)))
            vol[idx] += v; continue
        lows = np.maximum(edges[:-1], l); highs = np.minimum(edges[1:], h)
        overlap = np.clip(highs - lows, 0, None); tot = overlap.sum()
        if tot > 0:
            vol += v * (overlap / tot)
    total = vol.sum()
    pct = (vol / total * 100) if total > 0 else vol
    centers = (edges[:-1] + edges[1:]) / 2
    order = list(range(bins))[::-1]   # 위(고가) → 아래(저가)
    levels = [{"price_low": float(edges[i]), "price_high": float(edges[i + 1]),
               "price_mid": float(centers[i]), "pct": float(pct[i])} for i in order]
    poc_bin = int(np.argmax(vol)); poc_index = order.index(poc_bin)
    if current_price is None and "Close" in df.columns:
        try: current_price = float(df["Close"].dropna().iloc[-1])
        except Exception: current_price = None
    current_index = None
    if current_price is not None:
        cb = min(bins - 1, max(0, int(np.searchsorted(edges, current_price, "right") - 1)))
        current_index = order.index(cb)
    return {"levels": levels, "poc_index": poc_index, "current_index": current_index}


def nb_time_machine(close, dates=None, window=20, horizons=(5, 20), top_k=10, min_gap=5):
    """지금의 최근 window일 '모양'과 닮은 과거 구간을 상관계수로 찾아 이후 수익률 집계."""
    c = np.asarray(close, dtype=float)
    mask = ~np.isnan(c); c = c[mask]
    if dates is not None:
        dates = np.asarray(dates)[mask]
    n = len(c); Hmax = max(horizons)
    if n < window + Hmax + 30:
        return None
    cur = c[-window:]
    if np.any(cur <= 0):
        return None
    cur_z = cur / cur[0]; cur_z = cur_z - cur_z.mean()
    cur_norm = np.sqrt((cur_z ** 2).sum())
    if cur_norm == 0:
        return None
    cand_min = window - 1; cand_max = n - 1 - Hmax; exclude_from = n - window - min_gap
    results = []
    for t in range(cand_min, cand_max + 1):
        if t >= exclude_from:
            continue
        w = c[t - window + 1: t + 1]
        if np.any(w <= 0):
            continue
        wz = w / w[0]; wz = wz - wz.mean()
        denom = cur_norm * np.sqrt((wz ** 2).sum())
        if denom == 0:
            continue
        corr = float((cur_z * wz).sum() / denom)
        sim = (corr + 1) / 2 * 100
        end_price = c[t]
        fwd = {h: (c[t + h] / end_price - 1) * 100 for h in horizons}
        item = {"end_index": int(t), "similarity": sim, "forward": fwd}
        if dates is not None:
            item["end_date"] = dates[t]
        results.append(item)
    if not results:
        return None
    results.sort(key=lambda r: r["similarity"], reverse=True)
    top = results[:top_k]
    agg = {}
    for h in horizons:
        vals = [r["forward"][h] for r in top]
        agg[h] = {"avg": float(np.mean(vals)),
                  "up": int(sum(v > 0 for v in vals)),
                  "down": int(sum(v <= 0 for v in vals))}
    return {"matches": top, "aggregate": agg, "window": window,
            "horizons": list(horizons), "n_candidates": len(results)}


# =====================================================================
# [v7.0 신규] ① 멀티 타임프레임 — 주봉 추세 판정
# 일봉 df를 주봉으로 리샘플링 → 주봉 이평선 배열로 큰 추세를 확인.
# "일봉 타점 + 주봉 상승"이 겹칠 때 가짜 신호가 크게 줄어듭니다.
# =====================================================================
def get_weekly_trend(daily_df):
    try:
        if daily_df is None or daily_df.empty or len(daily_df) < 35:
            return "❔ 주봉 데이터 부족"
        # 일봉 OHLCV → 주봉(매주 금요일 기준) 리샘플링
        wdf = daily_df.resample('W-FRI').agg({
            'Open': 'first', 'High': 'max', 'Low': 'min', 'Close': 'last', 'Volume': 'sum'
        }).dropna()
        if len(wdf) < 11:
            return "❔ 주봉 데이터 부족"
        wdf['WMA5'] = wdf['Close'].rolling(5).mean()
        wdf['WMA10'] = wdf['Close'].rolling(10).mean()
        wdf['WMA20'] = wdf['Close'].rolling(20).mean()
        last = wdf.iloc[-1]
        w5, w10, w20 = last['WMA5'], last['WMA10'], last['WMA20']
        price = last['Close']
        # 20주선이 없으면(데이터 짧음) 5/10주선만으로 판정
        if pd.isna(w20):
            if pd.notna(w5) and pd.notna(w10):
                if price > w5 > w10: return "🔥 주봉 상승추세"
                elif price < w5 < w10: return "❄️ 주봉 하락추세"
            return "🌀 주봉 중립"
        if w5 > w10 > w20: return "🔥 주봉 상승추세"
        elif w5 < w10 < w20: return "❄️ 주봉 하락추세"
        else: return "🌀 주봉 중립"
    except Exception as _dg_e:
        _diag_note("get_weekly_trend", _dg_e)
        return "❔ 주봉 분석불가"


# =====================================================================
# [v7.0 신규] ② 시장 국면 대시보드 — "지금 매매해도 되는 장인가?"
# KOSPI/KOSDAQ 지수의 이평선 배열·추세 + 시장 폭(상승/하락 종목 비율)으로
# 🟢매수우호 / 🟡중립 / 🔴위험 신호등을 산출합니다.
# =====================================================================
@st.cache_data(ttl=900)
@st.cache_data(ttl=180)
def get_market_regime():
    result = {}

    def analyze_index(code, name):
        try:
            df = fdr.DataReader(code)
            if df.empty or len(df) < 65:
                return None
            df = df.tail(120).copy()
            df['MA5'] = df['Close'].rolling(5).mean()
            df['MA20'] = df['Close'].rolling(20).mean()
            df['MA60'] = df['Close'].rolling(60).mean()
            last = df.iloc[-1]
            ma20_prev = df['MA20'].iloc[-6]  # 5거래일 전 20일선 (기울기)
            price, ma5, ma20, ma60 = last['Close'], last['MA5'], last['MA20'], last['MA60']
            ma20_rising = ma20 > ma20_prev

            # RSI(14)
            delta = df['Close'].diff()
            gain = delta.where(delta > 0, 0.0).rolling(14).mean()
            loss = (-delta.where(delta < 0, 0.0)).rolling(14).mean()
            rs = gain / loss.replace(0, np.nan)
            rsi = float((100 - (100 / (1 + rs))).iloc[-1])

            # 점수화: 정배열·이평선 위·우상향일수록 가산
            score = 0
            if ma5 > ma20 > ma60: score += 2     # 완전 정배열
            elif ma5 > ma20: score += 1
            if price > ma20: score += 1
            if ma20_rising: score += 1
            if ma5 < ma20 < ma60: score -= 2     # 역배열
            elif ma5 < ma20: score -= 1
            if price < ma20: score -= 1

            if score >= 3: light = "🟢"
            elif score <= -2: light = "🔴"
            else: light = "🟡"

            pct = (price / df['Close'].iloc[-2] - 1) * 100 if len(df) > 1 else 0
            return {
                "name": name, "light": light, "score": score,
                "price": float(price), "pct": float(pct), "rsi": rsi,
                "ma20_rising": ma20_rising, "above_ma20": price > ma20,
                "align": "정배열" if ma5 > ma20 > ma60 else ("역배열" if ma5 < ma20 < ma60 else "혼조"),
            }
        except Exception as _dg_e:
            _diag_note("analyze_index", _dg_e)
            return None

    result['KOSPI'] = analyze_index('KS11', 'KOSPI')
    result['KOSDAQ'] = analyze_index('KQ11', 'KOSDAQ')

    # 시장 폭(Breadth): 상승 vs 하락 종목 비율
    breadth = None
    try:
        listing = fdr.StockListing('KOSPI')
        chg_col = next((c for c in ['ChagesRatio', 'ChangesRatio', 'ChangeRatio', 'Changes'] if c in listing.columns), None)
        if chg_col:
            vals = pd.to_numeric(listing[chg_col], errors='coerce').dropna()
            up = int((vals > 0).sum())
            down = int((vals < 0).sum())
            flat = int((vals == 0).sum())
            total = up + down + flat
            if total > 0:
                breadth = {"up": up, "down": down, "flat": flat,
                           "up_ratio": round(up / total * 100, 1)}
    except Exception:
        breadth = None
    result['breadth'] = breadth

    # 종합 신호등
    scores = [v['score'] for k, v in result.items() if isinstance(v, dict) and 'score' in v]
    avg = sum(scores) / len(scores) if scores else 0
    if breadth:
        if breadth['up_ratio'] >= 60: avg += 0.5
        elif breadth['up_ratio'] <= 40: avg -= 0.5
    if avg >= 2:
        result['verdict'] = ("🟢", "매수 우호적인 장", "추세·타점 신호가 나오면 적극 대응 가능한 환경입니다.")
    elif avg <= -1:
        result['verdict'] = ("🔴", "위험 — 신규 진입 자제", "시장이 약합니다. 현금 비중을 늘리고 손절을 타이트하게 가져가세요.")
    else:
        result['verdict'] = ("🟡", "중립 / 혼조", "선별적으로만 대응하세요. 강한 신호(정배열+거래량+수급)만 골라 진입.")
    return result


# =====================================================================
# [v7.0 신규] ③ 공매도 & 빚투(신용) 리스크 진단 — 한국 시장 특화
# 공매도: pykrx로 거래 비중 + 잔고 비중 산출 (신뢰도 높음)
# 신용잔고: 무료 공개 소스가 제한적이라 네이버 베스트에포트(환경 따라 조정 필요)
# =====================================================================
def _krx_retry(fn, *args, retries=3, **kwargs):
    """pykrx(→KRX) 호출 우회/안정화 래퍼.
    KRX 는 해외·클라우드 IP 를 자주 차단/지연시키므로:
      ① 일시적 통신 지연 → 짧은 백오프로 재시도
      ② 하드 IP 차단     → st.secrets['KRX_PROXY'] 또는 환경변수 KRX_PROXY 가
                            설정돼 있으면 '한국 IP 프록시'로 우회 시도
    프록시 미설정 시 기존과 동일하게 직접 호출(재시도만 적용)."""
    proxy = None
    try:
        proxy = st.secrets.get("KRX_PROXY")
    except Exception:
        proxy = None
    proxy = proxy or os.environ.get("KRX_PROXY")

    keys = ("HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy")
    saved = {}
    if proxy:
        for k in keys:
            saved[k] = os.environ.get(k)
            os.environ[k] = proxy
    try:
        for i in range(max(1, retries)):
            try:
                res = fn(*args, **kwargs)
                # DataFrame 은 '비어있지 않을 때'만 성공으로 간주
                if res is not None and not getattr(res, "empty", False):
                    return res
            except Exception as _dg_e:
                _diag_note("_krx_retry", _dg_e)
                pass
            time.sleep(0.7 * (i + 1))
        return None
    finally:
        if proxy:   # 환경변수 원복 (yfinance 등 다른 요청에 영향 없도록)
            for k in keys:
                v = saved.get(k)
                if v is None:
                    os.environ.pop(k, None)
                else:
                    os.environ[k] = v


@st.cache_data(ttl=3600)
def get_short_selling_risk(code):
    if not str(code).isdigit() or not HAS_PYKRX:
        return None
    try:
        today = datetime.now()
        frm = (today - timedelta(days=40)).strftime("%Y%m%d")
        to = today.strftime("%Y%m%d")

        out = {}
        # (1) 공매도 거래 비중 — 오늘 거래량 중 공매도 비율
        try:
            vol = _krx_retry(pykrx_stock.get_shorting_volume_by_date, frm, to, code)
            if vol is not None and not vol.empty and '비중' in vol.columns:
                ratio = vol['비중'].dropna()  # 0~1 또는 % 형태 (라이브러리 버전차)
                if not ratio.empty:
                    latest = float(ratio.iloc[-1])
                    avg5 = float(ratio.tail(5).mean())
                    # 0~1 스케일이면 %로 변환
                    scale = 100.0 if latest <= 1.5 else 1.0
                    latest *= scale; avg5 *= scale
                    out['short_vol_ratio'] = round(latest, 2)
                    out['short_vol_avg5'] = round(avg5, 2)
                    out['short_vol_trend'] = "📈 증가" if latest > avg5 * 1.1 else ("📉 감소" if latest < avg5 * 0.9 else "➖ 유지")
                    # 미니차트용 일별 시계열 (최근 30일)
                    out['short_vol_series'] = [(str(i)[:10], round(float(v) * scale, 2))
                                               for i, v in ratio.tail(30).items()]
        except Exception as _dg_e:
            _diag_note("get_short_selling_risk", _dg_e)
            pass

        # (2) 공매도 잔고 비중 — 전체 주식 중 공매도로 잠긴 비율
        try:
            bal = _krx_retry(pykrx_stock.get_shorting_balance_by_date, frm, to, code)
            if bal is not None and not bal.empty and '비중' in bal.columns:
                br = bal['비중'].dropna()
                if not br.empty:
                    out['short_bal_ratio'] = round(float(br.iloc[-1]), 2)
                    if len(br) >= 5:
                        out['short_bal_trend'] = "📈 증가" if br.iloc[-1] > br.tail(5).mean() else "📉 감소"
                    out['short_bal_series'] = [(str(i)[:10], round(float(v), 2))
                                               for i, v in br.tail(30).items()]
        except Exception as _dg_e:
            _diag_note("get_short_selling_risk", _dg_e)
            pass

        if not out:
            return None

        # 위험도 종합 판정
        svr = out.get('short_vol_ratio', 0)
        sbr = out.get('short_bal_ratio', 0)
        if svr >= 20 or sbr >= 3.0:
            out['level'] = ("🔴", "공매도 과열 — 단기 하락 압력 큼 (단, 숏스퀴즈 반등 가능성도)")
        elif svr >= 10 or sbr >= 1.5:
            out['level'] = ("🟡", "공매도 보통 — 흐름 주시 필요")
        else:
            out['level'] = ("🟢", "공매도 부담 낮음")
        return out
    except Exception as _dg_e:
        _diag_note("get_short_selling_risk", _dg_e)
        return None


@st.cache_data(ttl=3600)
def get_credit_balance_naver(code):
    """신용잔고(빚투) 베스트에포트 스크래핑. 실패 시 None.
    ※ 무료 소스가 불안정하여 환경에 따라 조정이 필요할 수 있습니다."""
    if not str(code).isdigit():
        return None
    try:
        url = f"https://finance.naver.com/item/coinfo.naver?code={code}"
        res = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=3)
        text = BeautifulSoup(res.text, 'html.parser').get_text(separator=' ', strip=True)
        m = re.search(r'신용[가-힣]*잔고[율]?\s*([0-9.]+)\s*%', text)
        if m:
            return {"credit_ratio": float(m.group(1))}
    except Exception as _dg_e:
        _diag_note("get_credit_balance_naver", _dg_e)
        pass
    return None


@st.cache_data(ttl=300)
def get_advanced_chart_data(ticker_code, timeframe):
    is_us = not str(ticker_code).isdigit()
    yf_ticker = ticker_code if is_us else f"{ticker_code}.KS"
    try:
        if timeframe == "30분": df = yf.Ticker(yf_ticker).history(period="1mo", interval="30m")
        elif timeframe == "1시간": df = yf.Ticker(yf_ticker).history(period="1mo", interval="60m")
        elif timeframe == "4시간":
            df = yf.Ticker(yf_ticker).history(period="2mo", interval="60m")
            if not df.empty: df = df.resample('4h').agg({'Open': 'first', 'High': 'max', 'Low': 'min', 'Close': 'last', 'Volume': 'sum'}).dropna()
        elif timeframe == "일봉": df = yf.Ticker(yf_ticker).history(period="6mo", interval="1d")
        elif timeframe == "주봉": df = yf.Ticker(yf_ticker).history(period="2y", interval="1wk")
        elif timeframe == "1년": df = yf.Ticker(yf_ticker).history(period="1y", interval="1d")
        elif timeframe == "5년": df = yf.Ticker(yf_ticker).history(period="5y", interval="1wk")
        elif timeframe == "10년": df = yf.Ticker(yf_ticker).history(period="10y", interval="1mo")
        else: df = yf.Ticker(yf_ticker).history(period="6mo", interval="1d")
            
        if not df.empty:
            df.index = df.index.tz_localize(None)
            if df.index.name == 'Datetime': df.index.name = 'Date'
        return df
    except Exception as e:
        return pd.DataFrame()

@st.cache_data(ttl=3600)
def search_us_ticker(query):
    if not query: return []
    if re.search('[가-힣]', query):
        try:
            res = requests.get(f"https://translate.googleapis.com/translate_a/single?client=gtx&sl=ko&tl=en&dt=t&q={urllib.parse.quote(query)}", timeout=2)
            search_term = res.json()[0][0][0]
        except Exception: search_term = query
    else: search_term = query
    try:
        url = f"https://query2.finance.yahoo.com/v1/finance/search?q={urllib.parse.quote(search_term)}&quotesCount=5"
        headers = {'User-Agent': 'Mozilla/5.0'}
        response = requests.get(url, headers=headers, timeout=5)
        data = response.json()
        results = []
        for quote in data.get('quotes', []):
            if quote.get('quoteType') in ['EQUITY', 'ETF']:
                sym = quote.get('symbol')
                name = quote.get('shortname') or quote.get('longname') or 'Unknown'
                # 티커로 먼저 매핑(정확) → 실패 시 영문 회사명으로
                ko_name = get_korean_name(sym)
                if not ko_name or ko_name == sym:
                    ko_name = get_korean_name(name)
                exch = quote.get('exchDisp', 'US')
                results.append(f"{sym} ({ko_name} / {exch})")
        return results
    except Exception as _dg_e: _diag_note("search_us_ticker", _dg_e); return []

@st.cache_data(ttl=3600)
# === [전문가 보조지표 계산] ==================================================
def _calc_expert_metrics(adf):
    """가격 DF에서 전문가 보조지표 계산 → dict 반환. (네트워크 호출 없음, 부족하면 항목별 None)
    - 고점대비52주: 최근 252거래일 고점 대비 % (0에 가까울수록 신고가권)
    - 이격도20: 20일선 대비 괴리 % (과열/눌림 판단)
    - 수익률20일: 시장 상대강도(RS) 계산용 최근 20일 수익률 %
    - MFI: 14일 자금흐름지수(거래량 가중 RSI)
    - 평균거래대금20일: 종가×거래량 20일 평균 (유동성 필터, 통화 단위 그대로)
    - 변동성20일: 일간 수익률 20일 표준편차 %/일"""
    out = {"고점대비52주": None, "이격도20": None, "수익률20일": None,
           "MFI": None, "평균거래대금20일": None, "변동성20일": None}
    try:
        close = pd.to_numeric(adf["Close"], errors="coerce").dropna()
        if len(close) < 21:
            return out
        cur = float(close.iloc[-1])
        if cur <= 0:
            return out
        hi_src = adf["High"] if ("High" in adf.columns and adf["High"].notna().any()) else close
        hi = float(pd.to_numeric(hi_src, errors="coerce").tail(252).max())
        if hi > 0:
            out["고점대비52주"] = round((cur / hi - 1) * 100, 1)
        if "MA20" in adf.columns and pd.notna(adf["MA20"].iloc[-1]):
            ma20 = float(adf["MA20"].iloc[-1])
        else:
            ma20 = float(close.rolling(20).mean().iloc[-1])
        if ma20 > 0:
            out["이격도20"] = round((cur / ma20 - 1) * 100, 1)
        out["수익률20일"] = round((cur / float(close.iloc[-21]) - 1) * 100, 1)
        if {"High", "Low", "Volume"}.issubset(adf.columns):
            h = pd.to_numeric(adf["High"], errors="coerce")
            lo = pd.to_numeric(adf["Low"], errors="coerce")
            c = pd.to_numeric(adf["Close"], errors="coerce")
            v = pd.to_numeric(adf["Volume"], errors="coerce")
            tp = (h + lo + c) / 3.0
            mf = tp * v
            dtp = tp.diff()
            pos = mf.where(dtp > 0, 0.0).rolling(14).sum()
            neg = mf.where(dtp < 0, 0.0).rolling(14).sum()
            denom = neg.replace(0, float("nan"))
            mfi = 100 - 100 / (1 + pos / denom)
            val = mfi.iloc[-1]
            if pd.notna(val):
                out["MFI"] = round(float(val), 1)
        if "Volume" in adf.columns:
            v = pd.to_numeric(adf["Volume"], errors="coerce")
            amt = (pd.to_numeric(adf["Close"], errors="coerce") * v).rolling(20).mean()
            val = amt.iloc[-1]
            if pd.notna(val) and val > 0:
                out["평균거래대금20일"] = float(val)
        vol = close.pct_change().rolling(20).std().iloc[-1]
        if pd.notna(vol):
            out["변동성20일"] = round(float(vol) * 100, 2)
    except Exception as _dg_e:
        _diag_note("_calc_expert_metrics", _dg_e)
        pass
    return out
# === [/전문가 보조지표 계산] =================================================


def analyze_technical_pattern(stock_name, ticker_code, offset_days=0):
    if not ticker_code: return None
    is_us = not str(ticker_code).isdigit()
    if is_us: stock_name = get_korean_name(stock_name)
    try:
        df = get_historical_data(ticker_code, 260)   # 52주 신고가 계산을 위해 260일 조회
        if df.empty or len(df) < 20 + offset_days: return None
        
        today_close = float(df['Close'].iloc[-1]) 
        if offset_days > 0: analysis_df = df.iloc[:-offset_days].copy()
        else: analysis_df = df.copy()
            
        analysis_df['MA5'] = analysis_df['Close'].rolling(window=5).mean()
        analysis_df['MA20'] = analysis_df['Close'].rolling(window=20).mean()
        analysis_df['MA60'] = analysis_df['Close'].rolling(window=60).mean()
        analysis_df['Vol_MA20'] = analysis_df['Volume'].rolling(window=20).mean()
        analysis_df['Std_20'] = analysis_df['Close'].rolling(window=20).std()
        analysis_df['Bollinger_Upper'] = analysis_df['MA20'] + (analysis_df['Std_20'] * 2)
        
        delta = analysis_df['Close'].diff()
        rs = (delta.where(delta > 0, 0.0).rolling(14).mean()) / (-delta.where(delta < 0, 0.0).rolling(14).mean())
        analysis_df['RSI'] = 100 - (100 / (1 + rs))
        analysis_df['OBV'] = (np.sign(analysis_df['Close'].diff()) * analysis_df['Volume']).fillna(0).cumsum()
        
        latest = analysis_df.iloc[-1]
        prev = analysis_df.iloc[-2] if len(analysis_df) > 1 else latest
        current_price = float(latest['Close']) 
        
        if pd.notna(latest['MA60']) and latest['MA5'] > latest['MA20'] > latest['MA60']: align_status = "🔥 완벽 정배열 (상승 추세) ｜ 💡 기준: 5일선 > 20일선 > 60일선"
        elif pd.notna(latest['MA60']) and latest['MA5'] < latest['MA20'] < latest['MA60']: align_status = "❄️ 역배열 (하락 추세) ｜ 💡 기준: 5일선 < 20일선 < 60일선"
        elif latest['MA5'] > latest['MA20'] and prev['MA5'] <= prev['MA20']: align_status = "✨ 5-20 골든크로스 ｜ 💡 기준: 5일선이 20일선을 상향 돌파"
        else: align_status = "🌀 혼조세/횡보 ｜ 💡 기준: 이평선 얽힘 (방향 탐색중)"
        
        ma20_val = float(latest['MA20'])
        if (ma20_val * 0.97) <= current_price <= (ma20_val * 1.03): status = "✅ 타점 근접 (분할 매수)"
        elif current_price > (ma20_val * 1.03): status = "⚠️ 이격 과다 (눌림목 대기)"
        else: status = "🛑 20일선 이탈 (관망)"

        # [v7.0] 멀티 타임프레임: 주봉 추세 판정
        weekly_trend = get_weekly_trend(analysis_df)
        
        is_us = not str(ticker_code).isdigit()
        if is_us:
            inst_vol, forgn_vol, ind_vol, inst_streak, forgn_streak = "조회불가", "조회불가", "조회불가", 0, 0
            intraday_est = None
            pension_sum, pension_streak = 0, 0
        else:
            inst_vol, forgn_vol, ind_vol, inst_streak, forgn_streak = get_investor_trend(ticker_code)
            intraday_est = get_intraday_estimate(ticker_code) 
            pension_sum, pension_streak = get_pension_fund_trend(ticker_code)
            
        per, pbr, fcf, shares, target_price = get_fundamentals(ticker_code)
        ai_target_val, ai_target_detail = calc_ai_target_price(per, pbr, current_price, ticker_code, use_sector_per=False)  # ⚡ 스캔 경로: 네트워크 추가 0건
        
        target_1 = float(latest['Bollinger_Upper'])
        recent_high = float(analysis_df['Close'].tail(150).max())   # 목표가 로직은 기존(150일) 기준 유지
        target_2 = float(recent_high) if recent_high > (target_1 * 1.02) else float(target_1 * 1.05)
        target_3 = float(target_2 * 1.08)
        
        pnl_pct = ((today_close - current_price) / current_price) * 100 if offset_days > 0 and current_price > 0 else 0.0
        
        krx_df = get_krx_stocks()
        sector_val = "기타/분류불가"
        if not krx_df.empty and not is_us:
            match_sec = krx_df[krx_df['Code'] == ticker_code]['Sector']
            if not match_sec.empty and pd.notna(match_sec.iloc[0]):
                raw_sec = str(match_sec.iloc[0])
                sector_val = raw_sec.replace(" 및 공급업", "").replace(" 제조업", "").replace(" 제조 및", "").replace(" 도매업", "").replace(" 소매업", "")
        
        # 🔥 [강력한 해결책] KRX 서버가 막혀서 '기타/분류불가'가 뜨면, 네이버 증권에서 실시간으로 섹터를 긁어옵니다.
        if not is_us and sector_val in ['기타/분류불가', 'ETF/미국주식/분류없음', '기타', '']:
            try:
                url = f"https://finance.naver.com/item/main.naver?code={ticker_code}"
                res = requests.get(url, headers={'User-Agent': 'Mozilla/5.0'}, timeout=3)
                soup = BeautifulSoup(res.text, 'html.parser')
                
                # 🛠️ [핵심 수정] 재무정보가 딸려오지 않게, 업종 전용 링크 태그(a)만 핀포인트로 타겟팅합니다.
                sec_tag = soup.select_one('a[href*="/sise/sise_group_detail.naver"]')
                if sec_tag:
                    sector_val = sec_tag.text.strip()
            except Exception:
                sector_val = "개별이슈/기타"
                
# 👇 수정된 미국 주식 섹터 파싱 로직
        if is_us:
            try:
                info = yf.Ticker(ticker_code).info
                raw_sector = info.get('sector', '미국주식')
                
                # 영문 섹터명을 한글로 매핑
                sector_map = {
                    "Technology": "IT/기술", 
                    "Financial Services": "금융", 
                    "Healthcare": "헬스케어/바이오", 
                    "Consumer Cyclical": "임의소비재",
                    "Industrials": "산업재", 
                    "Communication Services": "통신/플랫폼",
                    "Consumer Defensive": "필수소비재", 
                    "Energy": "에너지",
                    "Basic Materials": "소재", 
                    "Real Estate": "부동산", 
                    "Utilities": "유틸리티"
                }
                sector_val = sector_map.get(raw_sector, raw_sector)
            except Exception:
                sector_val = "미국주식"
        
        return {
            "종목명": stock_name, "티커": ticker_code, "섹터": sector_val, "현재가": current_price, "상태": status,
            "시장": get_market_label(ticker_code), "기준일": (analysis_df.index[-1] if len(analysis_df) else None),
            "진입가_가이드": ma20_val, "목표가1": target_1, "목표가2": target_2, "목표가3": target_3, "손절가": ma20_val * 0.97,
            "거래량 급증": "🔥 거래량 터짐" if analysis_df.iloc[-10:]['Volume'].max() > (analysis_df.iloc[-10:]['Vol_MA20'].mean() * 2) else "평이함",
            "RSI": latest['RSI'], "배열상태": align_status, "주봉추세": weekly_trend,
            "기관수급": inst_vol, "외인수급": forgn_vol, "개인수급": ind_vol, "장중잠정수급": intraday_est,
            "기관연속순매수": inst_streak, "외인연속순매수": forgn_streak,
            "연기금추정순매수": pension_sum, "연기금연속순매수": pension_streak,
            "PER": per, "PBR": pbr, "FCF": fcf, "Shares": shares, "목표가_컨센서스": target_price,
            "AI목표가": ai_target_val, "AI목표가_근거": ai_target_detail,
            "OBV": analysis_df['OBV'].tail(20), "차트 데이터": analysis_df.tail(20), 
            **_calc_expert_metrics(analysis_df),
            "오늘현재가": today_close, "수익률": pnl_pct, "과거검증": offset_days > 0
        }
    except Exception as e: 
        print(f"Technical Analysis Error for {ticker_code}: {e}")
        return None


@st.cache_data(ttl=900, show_spinner=False)
def get_stock_news(code, name="", limit=5):
    """종목별 최신 뉴스 N건. 미국=yfinance(+구글RSS 폴백), 국내=네이버 모바일 API→구글 뉴스 RSS→HTML.
    반환: list[{title, link, date, source}]"""
    code = str(code).strip()
    is_us = not code.isdigit()
    items = []
    if is_us:
        try:
            raw = yf.Ticker(code).news or []
            for n in raw[:limit + 3]:
                content = n.get("content") if isinstance(n.get("content"), dict) else n
                title = content.get("title") or n.get("title")
                # 링크
                link = ""
                cu = content.get("canonicalUrl")
                if isinstance(cu, dict):
                    link = cu.get("url", "")
                if not link:
                    cl = content.get("clickThroughUrl")
                    if isinstance(cl, dict):
                        link = cl.get("url", "")
                link = link or n.get("link", "")
                # 출처
                src = ""
                prov = content.get("provider")
                if isinstance(prov, dict):
                    src = prov.get("displayName", "")
                src = src or n.get("publisher", "")
                # 날짜
                date = ""
                pub = content.get("pubDate") or content.get("displayTime")
                ts = n.get("providerPublishTime")
                if pub:
                    date = str(pub)[:10]
                elif ts:
                    try:
                        date = datetime.fromtimestamp(ts).strftime("%Y-%m-%d")
                    except Exception:
                        date = ""
                if title:
                    items.append({"title": str(title).strip(), "link": link,
                                  "date": date, "source": src})
                if len(items) >= limit:
                    break
        except Exception as _dg_e:
            _diag_note("get_stock_news", _dg_e)
            pass
        if not items:   # yfinance 비면 구글 뉴스 RSS 폴백
            try:
                items = _google_news_rss(f"{name or code} stock", limit) or _google_news_rss(code, limit)
            except Exception:
                items = []
        return items[:limit]
    # 국내: ① 네이버 모바일 뉴스 JSON API → ② 구글 뉴스 RSS → ③ 데스크톱 HTML
    seen = set()
    # ① 모바일 JSON API
    try:
        data = _naver_json(f"https://m.stock.naver.com/api/news/stock/{code}?pageSize=20&page=1", timeout=3.5)
        groups = data if isinstance(data, list) else (
            data.get("newsList") if isinstance(data, dict) else None)
        if groups:
            for g in groups:
                cand = g.get("items") if (isinstance(g, dict) and isinstance(g.get("items"), list)) else ([g] if isinstance(g, dict) else [])
                for it in cand:
                    if not isinstance(it, dict):
                        continue
                    title = re.sub("<.*?>", "", str(it.get("title") or it.get("articleTitle") or "")).strip()
                    if not title or title in seen:
                        continue
                    office_id = it.get("officeId") or it.get("officeid")
                    article_id = it.get("articleId") or it.get("articleid")
                    link = it.get("linkUrl") or it.get("bodyUrl") or it.get("officeUrl") or ""
                    if not link and office_id and article_id:
                        link = f"https://n.news.naver.com/mnews/article/{office_id}/{article_id}"
                    dt = str(it.get("datetime") or it.get("dt") or "")
                    date = (f"{dt[0:4]}-{dt[4:6]}-{dt[6:8]}" if len(dt) >= 8 and dt[:8].isdigit() else dt[:10])
                    src = it.get("officeName") or it.get("office") or ""
                    body = re.sub(r"\s+", " ", re.sub("<.*?>", "", str(it.get("body") or it.get("bodyText") or ""))).strip()
                    seen.add(title)
                    items.append({"title": title, "link": link, "date": date,
                                  "source": src, "excerpt": body[:320]})
                    if len(items) >= limit:
                        break
                if len(items) >= limit:
                    break
    except Exception as _dg_e:
        _diag_note("get_stock_news", _dg_e)
        pass
    # ② 구글 뉴스 RSS 폴백 (회사명 기반, 키 불필요)
    if not items:
        for q in ([f"{name} 주가", name] if name else [code]):
            g = _google_news_rss(q, limit)
            if g:
                for n in g:
                    if n["title"] in seen:
                        continue
                    seen.add(n["title"])
                    items.append(n)
                break
    # ③ HTML 폴백 (셀렉터 완화 — 제목 셀의 모든 링크 허용)
    if not items:
        try:
            url = f"https://finance.naver.com/item/news_news.naver?code={code}&page=1"
            res = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=4)
            soup = BeautifulSoup(res.content.decode('euc-kr', 'replace'), 'html.parser')
            for a in soup.select("td.title a, .title a, a.tit"):
                title = a.get_text(strip=True)
                href = a.get("href", "")
                if not title or title in seen or not href:
                    continue
                link = ("https://finance.naver.com" + href) if href.startswith("/") else href
                tr = a.find_parent("tr")
                info = tr.select_one("td.info") if tr else None
                date_el = tr.select_one("td.date") if tr else None
                seen.add(title)
                items.append({
                    "title": title, "link": link,
                    "date": date_el.get_text(strip=True) if date_el else "",
                    "source": info.get_text(strip=True) if info else "",
                })
                if len(items) >= limit:
                    break
        except Exception as _dg_e:
            _diag_note("get_stock_news", _dg_e)
            pass
    return items[:limit]


@st.cache_data(ttl=3600, show_spinner=False)
def fetch_article_excerpt(url, max_chars=320):
    """기사 본문 일부를 추출(베스트에포트). 실패 시 ''. 네이버 금융/뉴스·일반 언론사 모두 대응.
    여러 본문 컨테이너 선택자를 순차 시도하고, 없으면 페이지 전체 텍스트에서 발췌."""
    if not url or not str(url).startswith("http"):
        return ""
    try:
        res = requests.get(url, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}, timeout=3)
        if res.status_code != 200:
            return ""
        enc = (res.encoding or "").lower()
        if not enc or enc == "iso-8859-1":
            enc = res.apparent_encoding or "utf-8"
        html = res.content.decode(enc, "replace")
        soup = BeautifulSoup(html, "html.parser")
        for tag in soup(["script", "style", "iframe", "header", "footer", "nav", "aside", "form"]):
            tag.decompose()
        body = None
        for sel in ["#dic_area", "#newsct_article", ".newsct_article", "#news_read",
                    ".articleCont", "#articleBody", ".article_body", "#articeBody",
                    "#article-view-content-div", "#content"]:
            el = soup.select_one(sel)
            if el and len(el.get_text(strip=True)) > 80:
                body = el
                break
        text = (body.get_text(separator=" ", strip=True) if body
                else soup.get_text(separator=" ", strip=True))
        text = re.sub(r"\s+", " ", text).strip()
        # 흔한 잡음 컷
        text = re.sub(r"(무단\s*전재.*$|저작권자.*$|ⓒ.*$)", "", text).strip()
        return text[:max_chars]
    except Exception as _dg_e:
        _diag_note("fetch_article_excerpt", _dg_e)
        return ""


@st.cache_data(ttl=1800, show_spinner=False)
def get_consensus_signal(code):
    """증권사 리포트 '목록'만으로 컨센서스 리비전을 근사(상세 미조회 → 빠름·국내 전용).
    제목의 상향/하향 키워드와 최근 35일 커버리지 빈도를 집계.
    반환: {revision_dir(상향/중립/하향), up, dn, report_count_30d, report_total} | None"""
    if not str(code).isdigit():
        return None
    try:
        url = f"https://finance.naver.com/research/company_list.naver?searchType=itemCode&itemCode={code}"
        res = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=4)
        soup = BeautifulSoup(res.content.decode("euc-kr", "replace"), "html.parser")
        table = soup.find("table", {"class": "type_1"})
        if not table:
            return None
        now = datetime.now()
        up = dn = recent = total = 0
        for tr in table.find_all("tr"):
            tds = tr.find_all("td")
            if len(tds) < 5:
                continue
            a = tds[1].find("a")
            if not a:
                continue
            title = a.text.strip()
            date_s = tds[4].text.strip()
            total += 1
            try:
                d = datetime.strptime(date_s, "%y.%m.%d")
                if (now - d).days <= 35:
                    recent += 1
            except Exception as _dg_e:
                _diag_note("get_consensus_signal", _dg_e)
                pass
            if any(k in title for k in ["상향", "상향조정", "눈높이 상향", "목표가 상향", "목표주가 상향"]):
                up += 1
            if any(k in title for k in ["하향", "하향조정", "눈높이 하향", "목표가 하향", "목표주가 하향"]):
                dn += 1
        if total == 0:
            return None
        rev = "상향" if up > dn else ("하향" if dn > up else "중립")
        return {"revision_dir": rev, "up": up, "dn": dn,
                "report_count_30d": recent, "report_total": total}
    except Exception as _dg_e:
        _diag_note("get_consensus_signal", _dg_e)
        return None


@st.cache_data(ttl=1800, show_spinner=False)
def get_finder_exclusion_set():
    """관리종목 + 투자경보(투자경고/위험/주의)·거래정지·정리매매 종목명 집합을 한 번에 수집.
    반환: (names_set, reason_map[name]=사유). 하드필터(후보 제외)용."""
    names, reason = set(), {}
    try:
        mgmt_df, alert_df = get_market_warnings()
    except Exception as _dg_e:
        _diag_note("get_finder_exclusion_set", _dg_e)
        return names, reason

    def _ingest(df, default_reason):
        if df is None or getattr(df, "empty", True):
            return
        name_col = next((c for c in df.columns if "종목" in str(c)), None)
        reason_col = next((c for c in df.columns if ("사유" in str(c)) or ("구분" in str(c)) or ("지정" in str(c))), None)
        if not name_col:
            return
        for _, row in df.iterrows():
            nm = re.sub(r"\s+", "", str(row[name_col])).strip()
            if not nm or nm == "종목명":
                continue
            rs = str(row[reason_col]).strip() if reason_col else default_reason
            names.add(nm)
            reason.setdefault(nm, rs or default_reason)

    _ingest(mgmt_df, "관리종목")
    _ingest(alert_df, "투자경보")
    return names, reason


def get_market_mood():
    """시장 분위기 종합 → dict(light, title, desc, risk_on[-1~1], vix, fng, breadth...).
    risk_on: 위험선호도. +1에 가까울수록 공격적(단기 모멘텀 우호), -1에 가까울수록 방어적(장기/가치 우호)."""
    mood = {
        "light": "🟡", "title": "중립", "desc": "",
        "risk_on": 0.0, "vix": None, "fng": None, "fng_rating": None,
        "kospi": None, "kosdaq": None, "breadth_up": None,
    }
    try:
        reg = get_market_regime()
        l, t, d = reg.get("verdict", ("🟡", "중립", ""))
        mood["light"], mood["title"], mood["desc"] = l, t, d
        for k in ("KOSPI", "KOSDAQ"):
            v = reg.get(k)
            if isinstance(v, dict):
                mood[k.lower()] = {"price": v.get("price"), "pct": v.get("pct"),
                                   "align": v.get("align"), "light": v.get("light")}
        b = reg.get("breadth")
        if isinstance(b, dict):
            mood["breadth_up"] = b.get("up_ratio")
    except Exception as _dg_e:
        _diag_note("get_market_mood", _dg_e)
        pass
    try:
        macro = get_macro_indicators()
        if macro and macro.get("VIX"):
            mood["vix"] = round(float(macro["VIX"]["value"]), 1)
    except Exception as _dg_e:
        _diag_note("get_market_mood", _dg_e)
        pass
    try:
        fg = get_fear_and_greed()
        if fg:
            mood["fng"] = fg.get("score")
            mood["fng_rating"] = fg.get("rating")
    except Exception as _dg_e:
        _diag_note("get_market_mood", _dg_e)
        pass
    # 위험선호(risk-on) 점수 [-1, 1] 합성
    s = 0.0
    s += {"🟢": 0.6, "🔴": -0.6}.get(mood["light"], 0.0)
    if mood["vix"] is not None:
        if mood["vix"] < 16: s += 0.2
        elif mood["vix"] > 25: s -= 0.3
    if mood["breadth_up"] is not None:
        if mood["breadth_up"] >= 60: s += 0.2
        elif mood["breadth_up"] <= 40: s -= 0.2
    if mood["fng"] is not None:
        if mood["fng"] >= 65: s += 0.1
        elif mood["fng"] <= 30: s -= 0.1
    mood["risk_on"] = max(-1.0, min(1.0, round(s, 2)))
    return mood


@st.cache_data(ttl=900, show_spinner=False)
def get_index_ret20():
    """시장 상대강도(RS) 기준선: 코스피·S&P500의 최근 20거래일 수익률(%). 실패 항목은 None."""
    out = {"kr": None, "us": None}
    for key, sym in (("kr", "KS11"), ("us", "US500")):
        try:
            s = fdr.DataReader(sym, (datetime.now() - timedelta(days=70)).strftime("%Y-%m-%d"))["Close"].dropna()
            if len(s) >= 21:
                out[key] = round(float(s.iloc[-1] / s.iloc[-21] - 1) * 100, 2)
        except Exception as _dg_e:
            _diag_note("get_index_ret20", _dg_e)
            pass
    return out


# === [포트폴리오 파일 업로드 파서] ===========================================
def parse_portfolio_upload(uploaded_file):
    """증권사 잔고 엑셀/CSV 또는 샘플 양식을 읽어 (DataFrame[종목명,진입단가,보유수량], 안내문) 반환.
    - 인코딩(utf-8/cp949)·구분자(쉼표/탭/세미콜론) 조합을 자동 시도해 '컬럼 매핑이 성공하는' 해석을 채택
    - 머리글 행 자동 탐색(파일 위쪽의 제목/계좌정보 줄 무시)
    - 컬럼 자동 매핑: 종목명·상품명 / 보유수량·잔고수량·수량 / 매입단가·평균단가·평단가 ...
    - 단가 컬럼이 없고 '매입금액'만 있으면 금액÷수량으로 환산
    - 종목코드가 있으면 KRX 정식 종목명으로 보정(엑셀에서 잘린 앞자리 0 복원)
    - 같은 종목 여러 줄(분할 매수)은 가중평균 단가로 자동 합산
    실패 시 ValueError(사용자 안내 메시지)를 발생시킨다."""
    import io as _io, re as _re

    def _norm(x):
        return _re.sub(r"[\s_()\[\]]", "", str(x)).lower()

    NAME_KEYS  = ["종목명", "상품명", "종목", "name", "ticker", "티커"]
    CODE_KEYS  = ["종목코드", "단축코드", "종목번호", "code", "symbol"]
    QTY_KEYS   = ["보유수량", "잔고수량", "결제잔고", "보유량", "주식수", "수량", "qty", "quantity", "shares"]
    PRICE_KEYS = ["진입단가", "매입단가", "평균단가", "평균매입가", "매입평균가", "평단가",
                  "매수단가", "매입가", "avgprice", "averageprice", "buyprice"]
    AMT_KEYS   = ["매입금액", "매수금액", "투자원금", "투자금액", "매입원금"]

    def _find_col(cols_norm, keys):
        for k in keys:
            kk = _norm(k)
            for i, c in enumerate(cols_norm):
                if kk and kk in c:
                    return i
        return None

    def _map_columns(df0):
        """머리글 행 탐색 + 컬럼 매핑. 성공 시 dict, 실패 시 None."""
        if df0 is None or df0.empty:
            return None
        for r in range(min(15, len(df0))):
            cells = [_norm(v) for v in df0.iloc[r].tolist()]
            has_name = any(any(_norm(k) in c for c in cells) for k in (NAME_KEYS + CODE_KEYS))
            has_qty  = any(any(_norm(k) in c for c in cells) for k in QTY_KEYS)
            if not (has_name and has_qty):
                continue
            header = ["" if v is None else str(v) for v in df0.iloc[r].tolist()]
            cn = [_norm(h) for h in header]
            i_name, i_code = _find_col(cn, NAME_KEYS), _find_col(cn, CODE_KEYS)
            i_qty = _find_col(cn, QTY_KEYS)
            i_price, i_amt = _find_col(cn, PRICE_KEYS), _find_col(cn, AMT_KEYS)
            if i_qty is None or (i_name is None and i_code is None):
                continue
            if i_price is None and i_amt is None:
                continue
            # 제목들이 한 칸에 뭉쳐 있으면(구분자 오인식) 이 해석은 무효
            if len({x for x in (i_name, i_code, i_qty, i_price, i_amt) if x is not None}) < 2:
                continue
            body = df0.iloc[r + 1:].reset_index(drop=True)
            body.columns = range(len(header))
            return dict(header=header, body=body, i_name=i_name, i_code=i_code,
                        i_qty=i_qty, i_price=i_price, i_amt=i_amt)
        return None

    fname = (getattr(uploaded_file, "name", "") or "").lower()
    raw = uploaded_file.getvalue()
    mapped = None
    if fname.endswith((".xlsx", ".xlsm", ".xls")):
        try:
            df0 = pd.read_excel(_io.BytesIO(raw), header=None, dtype=str)
        except Exception as e:
            raise ValueError(f"엑셀 파일을 여는 데 실패했습니다 ({e}). CSV로 저장해 다시 올려보세요.")
        mapped = _map_columns(df0)
    else:
        tried = set()
        for _enc in ("utf-8-sig", "cp949", "euc-kr", "utf-8", "latin1"):
            for _sep in (",", "\t", ";", "|"):
                try:
                    df0 = pd.read_csv(_io.BytesIO(raw), header=None, dtype=str, encoding=_enc,
                                      sep=_sep, engine="python", names=list(range(64)),
                                      skip_blank_lines=True)
                except Exception as _dg_e:
                    _diag_note("parse_portfolio_upload", _dg_e)
                    continue
                df0 = df0.dropna(axis=1, how="all")
                sig = (df0.shape, str(df0.head(2).values.tolist())[:300])
                if sig in tried:
                    continue
                tried.add(sig)
                mapped = _map_columns(df0)
                if mapped:
                    break
            if mapped:
                break
    if mapped is None:
        raise ValueError("머리글 행을 찾지 못했습니다. 첫 줄에 '종목명, 진입단가, 보유수량' 같은 "
                         "제목이 필요합니다. (옆의 샘플 양식을 받아 그대로 채우면 가장 쉽습니다)")

    header, body = mapped["header"], mapped["body"]
    i_name, i_code = mapped["i_name"], mapped["i_code"]
    i_qty, i_price, i_amt = mapped["i_qty"], mapped["i_price"], mapped["i_amt"]

    def _num(v):
        s = _re.sub(r"[,₩원\s$]", "", str(v))
        if s in ("", "-", "nan", "none", "None", "NaN"):
            return None
        try:
            return float(s)
        except Exception as _dg_e:
            _diag_note("_num", _dg_e)
            return None

    krx = None
    try:
        krx = get_krx_stocks()
    except Exception:
        krx = None  # 시세망 문제 시에도 이름 기반으로는 계속 진행

    rows, skipped = [], 0
    for _, r in body.iterrows():
        qty = _num(r[i_qty])
        name = "" if i_name is None else str(r[i_name]).strip()
        code_raw = "" if i_code is None else str(r[i_code]).strip()
        if name.lower() in ("nan", "none"):
            name = ""
        if code_raw.lower() in ("nan", "none"):
            code_raw = ""
        if (qty is None or qty <= 0) and not name and not code_raw:
            continue  # 완전 빈 줄
        if qty is None or qty <= 0:
            skipped += 1  # 합계·예수금 등 수량 없는 줄
            continue
        price = _num(r[i_price]) if i_price is not None else None
        if (price is None or price <= 0) and i_amt is not None:
            amt = _num(r[i_amt])
            if amt and amt > 0:
                price = amt / qty
        if code_raw:  # 종목코드 → KRX 정식 종목명 보정 (앞자리 0 복원)
            digits = _re.sub(r"\D", "", code_raw)
            if digits and krx is not None and not krx.empty:
                code6 = digits.zfill(6)[-6:]
                hit = krx[krx["Code"].astype(str).str.zfill(6) == code6]
                if not hit.empty:
                    name = str(hit["Name"].iloc[0])
            if not name:
                name = code_raw  # 숫자 아닌 코드(미국 티커 등)는 그대로 사용
        if not name or price is None or price <= 0:
            skipped += 1
            continue
        rows.append({"종목명": name, "진입단가": round(float(price), 2), "보유수량": int(qty)})

    if not rows:
        raise ValueError("불러올 수 있는 보유 종목이 없습니다. 수량과 단가 값이 채워져 있는지 확인해 주세요.")

    out = pd.DataFrame(rows, columns=["종목명", "진입단가", "보유수량"])
    if out["종목명"].duplicated().any():  # 분할 매수 → 가중평균 합산
        out["_금액"] = out["진입단가"] * out["보유수량"]
        g = out.groupby("종목명", as_index=False).agg({"_금액": "sum", "보유수량": "sum"})
        g["진입단가"] = (g["_금액"] / g["보유수량"]).round(2)
        out = g[["종목명", "진입단가", "보유수량"]]

    used = []
    if i_name is not None:
        used.append(f"종목명←'{header[i_name]}'")
    if i_code is not None and i_code != i_name:
        used.append(f"종목코드←'{header[i_code]}'")
    used.append(f"수량←'{header[i_qty]}'")
    if i_price is not None:
        used.append(f"단가←'{header[i_price]}'")
    elif i_amt is not None:
        used.append(f"단가←'{header[i_amt]}'÷수량")
    msg = f"✅ {len(out)}개 종목을 불러왔습니다"
    if skipped:
        msg += f" (합계·빈 줄 등 {skipped}행 건너뜀)"
    msg += " · 인식한 컬럼: " + ", ".join(used)
    return out, msg


# `from core_data import *` 로 넘어갈 이름 (언더스코어 포함, 자동 생성)
_EXPORTED = [
    "_calc_expert_metrics",
    "_clean_ipo_df",
    "_diag_index_endpoints",
    "_extract_nps_stake_from_html",
    "_fetch_nps_stake_dart",
    "_fetch_nps_stake_multi",
    "_fetch_stock_investor_2d",
    "_get_etf_list",
    "_get_kr_etf_codes",
    "_gtx_translate_en_ko",
    "_kr_change_map",
    "_kr_market_snapshot",
    "_krx_list_from_naver",
    "_krx_retry",
    "_naver_json",
    "_naver_sector_map",
    "_norm_etf_name",
    "_parse_ipo_enddate",
    "_poly_num",
    "_poly_parse_list",
    "analyze_technical_pattern",
    "analyze_theme_trends",
    "calc_ai_target_price",
    "classify_tp_change",
    "extract_beneficiary_stocks",
    "fetch_article_excerpt",
    "fetch_naver_volume",
    "fetch_polymarket_markets",
    "get_advanced_chart_data",
    "get_consensus_signal",
    "get_credit_balance_naver",
    "get_daily_sise_and_investor",
    "get_dart_corp_map",
    "get_dividend_portfolio",
    "get_drawdown_info",
    "get_economic_events",
    "get_fear_and_greed",
    "get_financial_deep_data",
    "get_finder_exclusion_set",
    "get_foreign_broker_estimate",
    "get_fundamentals",
    "get_historical_data",
    "get_index_ret20",
    "get_index_spark",
    "get_industry_changes",
    "get_institution_buy_trend",
    "get_intraday_estimate",
    "get_intraday_estimate_debug",
    "get_investor_trend",
    "get_korean_name",
    "get_kr_index_panel",
    "get_kr_investor_flows",
    "get_kr_market_breadth",
    "get_kr_sector_heat",
    "get_kr_universe_naver",
    "get_krx_etf_list",
    "get_krx_name_code_list",
    "get_krx_stocks",
    "get_latest_naver_news",
    "get_limit_stocks",
    "get_macro_indicators",
    "get_major_indices",
    "get_market_label",
    "get_market_map",
    "get_market_mood",
    "get_market_regime",
    "get_market_warnings",
    "get_marketcap_top",
    "get_naver_ipo_data",
    "get_naver_research",
    "get_nps_holdings",
    "get_nps_us_portfolio",
    "get_overnight_us_market",
    "get_pension_fund_trend",
    "get_scan_targets",
    "get_sector_per",
    "get_short_selling_risk",
    "get_stock_list_by_market",
    "get_stock_news",
    "get_stock_research_history",
    "get_stock_sector_kr",
    "get_today_research_details",
    "get_trading_value_kings",
    "get_trending_sectors",
    "get_us_etf_summary",
    "get_us_scan_targets",
    "get_us_sector_etfs",
    "get_us_sector_heat",
    "get_us_sector_map",
    "get_us_top_gainers",
    "get_us_volume_surge_drop",
    "get_value_metrics",
    "get_volume_surge_drop",
    "get_weekly_trend",
    "is_kr_etf_etn",
    "load_watchlist",
    "nb_time_machine",
    "nb_volume_profile",
    "parse_portfolio_upload",
    "parse_prev_target_price",
    "parse_target_price",
    "resolve_etf_codes",
    "save_watchlist",
    "search_nps_holding",
    "search_us_ticker",
    "standardize_opinion",
    "translate_poly_questions",
    "update_news_state",
]

__all__ = [_n for _n in _EXPORTED if _n in globals()]
