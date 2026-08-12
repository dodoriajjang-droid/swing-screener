# -*- coding: utf-8 -*-
"""
AI(Gemini) 계층  (core_ai.py)
=====================================================================
google-genai 호출과 프롬프트. 데이터 계층을 이용한다.

계층 순서: constants → utils → data → ai → scoring → render
위 방향으로만 의존한다(순환 없음). core.py 가 전부를 합쳐 다시 내보낸다.
"""
from core_constants import *
from core_utils import *
from core_data import *


@st.cache_data(ttl=3600)
def _genai_generate(prompt, api_key, *, grounding=False, image=None,
                    model_name="gemini-3.1-flash-lite"):
    """신규 google-genai SDK 공통 래퍼. 원시 response 객체를 반환한다.
    - grounding=True  → 구글 검색(Google Search) 도구 사용 (Gemini 3.x 정식 문법)
    - image 지정       → 멀티모달(비전) 입력
    """
    client = _genai.Client(api_key=api_key)
    contents = prompt if image is None else [prompt, image]
    config = None
    if grounding:
        config = _gtypes.GenerateContentConfig(
            tools=[_gtypes.Tool(google_search=_gtypes.GoogleSearch())]
        )
    return client.models.generate_content(
        model=model_name, contents=contents, config=config,
    )


def ask_gemini(prompt, _api_key, grounding=False):
    if not _api_key: return "API 키가 필요합니다."
    try:
        now_kst = datetime.utcnow() + timedelta(hours=9)
        today_str = now_kst.strftime("%Y년 %m월 %d일")
        system_date_instruction = f"🚨 [시스템 필수 지침]: 오늘 날짜는 정확히 {today_str}입니다. 분석 시점은 반드시 오늘을 기준으로 하며, 과거 데이터를 현재 상황으로 오인하여 답변하지 마세요.\n\n"
        
        full_prompt = system_date_instruction + prompt

        response = _genai_generate(full_prompt, _api_key, grounding=grounding)

        if not response.candidates or not response.candidates[0].content.parts:
            reason = response.candidates[0].finish_reason if response.candidates else "Unknown"
            return f"🚨 AI 응답 생성에 실패했습니다. (사유: {reason}). 다시 시도하거나 질문을 수정해주세요."
        return response.text
    except Exception as e: 
        if "429" in str(e) or "quota" in str(e).lower() or "spending cap" in str(e).lower():
            return "🚨 AI API 무료 한도가 초과되었거나 결제 한도에 도달했습니다."
        return f"AI 분석 오류: {str(e)}"

def ask_gemini_vision(prompt, image_obj, _api_key):
    if not _api_key: return "API 키가 필요합니다."
    try:
        now_kst = datetime.utcnow() + timedelta(hours=9)
        today_str = now_kst.strftime("%Y년 %m월 %d일")
        system_date_instruction = f"🚨 [시스템 필수 지침]: 오늘 날짜는 {today_str}입니다. 과거 데이터로 답변하지 마세요.\n\n"
        response = _genai_generate(system_date_instruction + prompt, _api_key, image=image_obj)
        return response.text
    except Exception as e: return f"🚨 비전 분석 오류: {str(e)}"

@st.cache_data(ttl=86400)
def get_daily_market_briefing(macro_data, top_gainers, _api_key):
    if not _api_key: return "API 키가 필요합니다."
    vix = f"{macro_data['VIX']['value']:.2f}" if macro_data and 'VIX' in macro_data else 'N/A'
    sox = f"{macro_data['필라델피아 반도체']['value']:.2f}" if macro_data and '필라델피아 반도체' in macro_data else 'N/A'
    krw = f"{macro_data['원/달러 환율']['value']:.1f}" if macro_data and '원/달러 환율' in macro_data else 'N/A'
    tnx = f"{macro_data['美 10년물 국채']['value']:.3f}" if macro_data and '美 10년물 국채' in macro_data else 'N/A'
    gainers_str = ", ".join(top_gainers) if top_gainers else '데이터 없음'

    prompt = f"""
    당신은 여의도 최고의 시황 애널리스트입니다. 오늘 아침 실전 트레이더들을 위한 '모닝 브리핑'을 작성해주세요.
    [현재 글로벌 매크로 및 수급 데이터]
    - VIX(공포지수): {vix}
    - 필라델피아 반도체 지수: {sox}
    - 원/달러 환율: {krw}원
    - 美 10년물 국채금리: {tnx}%
    - 전일 미국장 주요 급등주: {gainers_str}
    위 팩트 데이터를 바탕으로, 아래 3개 항목만 마크다운으로 간결하게 작성하세요.
    - 맨 위에 별도의 큰 제목이나 인사말은 넣지 말고, 바로 첫 항목부터 시작하세요.
    - 각 항목의 제목은 반드시 '## ' 로 시작하세요.

    ## 🌍 글로벌 시황
    간밤 미국 증시(3대 지수·반도체 SOX·美 10년물 금리·유가)와 위험자산 선호 심리를 2~3줄로 요약.

    ## 🇰🇷 국내 시황
    위 미국장 결과와 환율·금리가 오늘 코스피/코스닥 수급 및 외국인 자금 방향에 미칠 영향을 2~3줄로 분석.

    ## 🎯 오늘의 픽 (주목할 섹터)
    **🌍 글로벌:** 미국 시장에서 자금이 쏠릴 것으로 예상되는 섹터 1~2개와 근거를 1줄로.
    **🇰🇷 국내:** 위 글로벌 흐름의 수혜가 예상되는 국내 섹터 1~2개와 근거를 1줄로.
    """
    return ask_gemini(prompt, _api_key)

# 👇 [업그레이드 1] 한미 통합 듀얼 엔진으로 시장 주도 테마를 추출하는 함수
@st.cache_data(ttl=10800) # 3시간마다 캐시 갱신
def get_trending_themes_with_ai(api_key):
        if not api_key: return ["테스트 테마 A", "테스트 테마 B", "테스트 테마 C", "테스트 테마 D"]
        
        market_context = ""
        try:
            # 1. 한국 시장 (KRX) 거래대금 상위 종목 추출
            krx_df = fdr.StockListing('KRX')
            if 'Volume' in krx_df.columns and 'Close' in krx_df.columns:
                krx_df['Amount'] = krx_df['Volume'] * krx_df['Close']
                top_kr = krx_df.sort_values('Amount', ascending=False).head(30)
                kr_tickers = ", ".join(top_kr['Name'].tolist())
                market_context += f"🔥 [한국 증시(KRX) 거래대금 상위 30종목]: {kr_tickers}\n"
            
            # 2. 미국 시장 (US) S&P500 등 주요 종목 거래량 급증 탐지 (yfinance 활용)
            # (시간 관계상 S&P500 대표 종목군 리스트를 활용하여 빠른 스캔)
            us_major_tickers = ["NVDA", "AAPL", "MSFT", "AMZN", "META", "GOOGL", "TSLA", "LLY", "AVGO", "TSM", "AMD", "SMCI"]
            us_active = []
            import yfinance as yf
            import concurrent.futures
            
            def check_us_volume(ticker):
                try:
                    hist = yf.Ticker(ticker).history(period="5d")
                    if len(hist) >= 2:
                        # 최근 거래량이 5일 평균보다 급증했는지 확인 (단순 지표)
                        vol_today = hist['Volume'].iloc[-1]
                        vol_avg = hist['Volume'].mean()
                        if vol_today > vol_avg * 1.2:  # 20% 이상 거래량 폭발 시
                            return ticker
                except Exception as _dg_e: _diag_note("check_us_volume", _dg_e); pass
                return None

            with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
                for res in executor.map(check_us_volume, us_major_tickers):
                    if res: us_active.append(res)
            
            if us_active:
                market_context += f"🦅 [미국 증시(US) 거래량 급증 주요 티커]: {', '.join(us_active)}\n"

        except Exception as e:
            market_context = "시장 데이터를 불러오는 중 오류 발생 (AI 자체 판단 필요)"

        # 👇 [업그레이드 2] AI에게 글로벌(한+미) 시각으로 분석하도록 프롬프트 전면 수정
        prompt = f"""
        당신은 월스트리트와 여의도를 아우르는 글로벌 퀀트 애널리스트입니다.
        아래는 오늘 한국 증시(KRX) 거래대금 상위 종목과 미국 증시(US) 거래량 급증 종목 데이터입니다.
        
        {market_context}
        
        이 데이터를 바탕으로, 현재 전 세계 주식시장을 관통하고 있는 '가장 뜨거운 메가트렌드 및 핵심 주도 테마' 4가지를 추출하세요.
        반드시 쉼표(,)로만 구분된 텍스트로 출력해야 합니다.
        예시: 차세대 AI 반도체, 비만치료제(GLP-1), 전력 인프라 및 변압기, 자율주행 및 로보택시
        """
        try:
            res = ask_gemini(prompt, api_key)
            themes = [t.strip() for t in res.split(',') if t.strip()]
            return themes[:4] if len(themes) >= 4 else (themes + ["추가 테마 분석 필요"] * 4)[:4]
        except Exception as _dg_e:
            _diag_note("get_trending_themes_with_ai", _dg_e)
            return ["글로벌 AI 반도체", "비만치료제 및 K-바이오", "전력기기 및 K-방산", "자율주행 및 로보틱스"]

# 👇 [업그레이드 3] 테마 검색 시, 미국(US) 텐배거 대장주까지 함께 발굴하도록 수정
@st.cache_data(ttl=3600)
def get_theme_stocks_with_ai(theme, api_key):
    prompt = f"""당신은 글로벌 테마주 발굴 전문가입니다.
'{theme}' 테마의 실제 수혜주를 **한국(KRX)과 미국(US) 양쪽 시장에서 골고루** 발굴하세요.
이 테마의 제품·기술·밸류체인(소재·부품·장비·서비스)에 직접적인 사업 연관이 있는 종목만 포함합니다.

[규칙]
1. 테마와 '직접' 관련된 진짜 종목만. 개수를 채우려고 관련 없는 대형주(예: 테슬라, 엔비디아)나 엉뚱한 종목을 끼워넣지 마세요.
2. **반드시 한국 종목과 미국 종목을 둘 다 포함**하세요. 대부분의 글로벌 테마는 양쪽 시장에 실제 수혜주가
   있으니 미국·글로벌 종목도 적극적으로 찾으세요. (정말로 한쪽 시장에 진짜 관련주가 없을 때만 생략)
3. 가능하면 한국과 미국 비중을 비슷하게 맞추세요.
4. 정확한 코드만 — 한국은 정확한 6자리 KRX 코드, 미국은 정확한 실제 티커(예: NVDA). 불확실하거나 비상장이면 제외.
5. 관련도가 높은 순서로, 최대 30개.

[출력 형식]
- "종목명,종목코드" 형식, 한 줄에 하나씩. 미국 종목도 종목명은 자유롭게 쓰되 코드는 영문 티커. (예: 삼성전자,005930 / 엔비디아,NVDA)
- 번호·부연 설명·마크다운 기호(-, * 등) 금지. 종목명 안에는 쉼표(,)를 쓰지 마세요. 오직 종목 데이터만.
"""
    try:
        res = ask_gemini(prompt, api_key, grounding=True)
        stocks, seen = [], set()
        for line in res.split('\n'):
            line = line.strip()
            if ',' not in line:
                continue
            parts = line.split(',')
            code = parts[-1].strip().upper().replace(" ", "")          # 코드는 항상 마지막 토큰
            name = ",".join(parts[:-1]).strip().lstrip("-*• ").strip()  # 이름에 쉼표가 있어도 보존
            if not name or len(name) > 40:
                continue
            is_kr = (len(code) == 6 and code.isdigit() and code != "000000")
            is_us = (code.isascii() and code.isalpha() and 1 <= len(code) <= 5)
            if (is_kr or is_us) and code not in seen:
                seen.add(code)
                stocks.append((name, code))
        return stocks[:30]
    except Exception as _dg_e:
        _diag_note("get_theme_stocks_with_ai", _dg_e)
        return []

@st.cache_data(ttl=3600)
def get_growth_fund_stocks_with_ai(sector_query, _api_key):
    """국민성장펀드 특정 첨단전략산업의 국내(KRX) 수혜 대장주를 AI로 발굴"""
    if not _api_key:
        return []
    prompt = f"""당신은 한국 정책펀드(국민성장펀드, 150조원) 전문 애널리스트입니다.
정부가 첨단전략산업으로 지정한 '{sector_query}' 분야에서, 국민성장펀드 투자 및 정책 수혜가 기대되는
한국 증시(KRX) 상장 핵심 대장주 및 밸류체인(소재·부품·장비) 종목 20개를 선정하세요.
[필수 조건]
1. 반드시 한국 증시(KRX)에 상장된 종목만 선정하세요.
2. 출력 형식은 반드시 "종목명,종목코드(6자리 숫자)" 입니다. (예: 삼성전자,005930)
3. 번호, 부연 설명, 마크다운 기호(-, * 등) 없이 오직 종목 데이터만 한 줄에 하나씩 출력하세요."""
    try:
        res = ask_gemini(prompt, _api_key)
        stocks = []
        seen = set()
        for line in res.split("\n"):
            parts = line.split(",")
            if len(parts) >= 2:
                name = parts[0].strip().replace("-", "").replace("*", "").strip()
                code = parts[1].strip()
                if len(code) == 6 and code.isdigit() and code not in seen:
                    seen.add(code)
                    stocks.append((name, code))
        return stocks[:20]
    except Exception as _dg_e:
        _diag_note("get_growth_fund_stocks_with_ai", _dg_e)
        return []



@st.cache_data(ttl=3600)
def get_longterm_value_stocks_with_ai(strategy, cap_size, _api_key):
    if not _api_key: return []
    try:
        prompt = f"당신은 여의도의 15년차 시니어 펀드매니저입니다. 한국 증시에서 다음 투자 전략에 가장 완벽하게 부합하는 숨겨진 우량주 20개를 발굴해주세요.\n- 투자 전략: {strategy}\n- 기업 규모: {cap_size}\n반드시 파이썬 리스트로만 답변하세요. 예시: [('삼성전자', '005930')]"
        response = ask_gemini(prompt, _api_key)
        raw_list = re.findall(r"['\"]([^'\"]+)['\"]\s*,\s*['\"]([0-9]{6})['\"]", response)
        krx_df = get_krx_stocks()
        if krx_df.empty:
            return [(n, c) for n, c in dict.fromkeys(raw_list) if not is_kr_etf_etn(n, c)][:20]
        name_to_code = dict(zip(krx_df['Name'], krx_df['Code']))
        code_to_name = dict(zip(krx_df['Code'], krx_df['Name']))
        validated = []
        seen = set()
        for name, code in raw_list:
            clean_name = name.replace('(주)', '').strip()
            final_name, final_code = None, None
            if clean_name in name_to_code: final_name, final_code = clean_name, name_to_code[clean_name]
            elif code in code_to_name: final_name, final_code = code_to_name[code], code
            if final_name and final_code and final_code not in seen:
                seen.add(final_code)
                validated.append((final_name, final_code))
        validated = [(n, c) for n, c in validated if not is_kr_etf_etn(n, c)]
        return validated[:20]
    except Exception as _dg_e: _diag_note("get_longterm_value_stocks_with_ai", _dg_e); return []
        
@st.cache_data(ttl=86400, max_entries=500)
def get_granular_themes(stock_name: str, api_key: str) -> list:
    if not api_key:
        return ["API_KEY_MISSING"]
    
    try:
        prompt = f"""
        대상 기업: [{stock_name}]
        이 기업의 핵심 사업 모델과 현재 주식 시장에서 편입되어 있는 구체적인 테마/섹터를 3~5개의 단어로 추출하세요.
        - 지시사항 1: 'IT', '제조' 같은 포괄적인 단어는 제외합니다.
        - 지시사항 2: 'AI 데이터센터 인프라', 'HBM', '전력기기', '토큰증권', '온디바이스 AI' 등 실전 투자에서 쓰이는 구체적인 밸류체인 용어를 사용하세요.
        - 지시사항 3: 반드시 아래의 JSON 배열 형식으로만 출력하세요. 마크다운 기호나 추가 설명은 절대 포함하지 마세요.
        
        출력 예시:
        ["메모리 반도체", "파운드리", "온디바이스 AI"]
        """
        
        # 시스템 통합 모델 버전 적용
        response = _genai_generate(prompt, api_key)

        text = response.text.strip()
        if text.startswith("```json"):
            text = text[7:-3].strip()
        elif text.startswith("```"):
            text = text[3:-3].strip()
            
        themes = json.loads(text)
        
        if isinstance(themes, list):
            return themes
        else:
            return ["분류 오류"]
            
    except Exception as e:
        import logging
        logging.error(f"[{stock_name}] 테마 추출 실패: {e}")
        return ["데이터 확인 필요"]


@st.cache_data(ttl=900, show_spinner=False)
def classify_news_sentiment(_api_key, items):
    """종목별 '개별 기사 제목'을 AI가 호재/중립/악재로 판정하고 종목 단위로 집계.
    items: tuple of (code, name, articles_tuple) — articles_tuple은 (title, excerpt) 튜플들.
    반환: {code: {label, score(-2~2), confidence(0~1), auto_neutral(bool),
                  reason, article_labels: [(label, score), ...]}}  # 입력 기사 순서
    집계: 기사 score×신뢰가중(상1.0/중0.6/하0.3) 합산. 방향 일치도×신호강도로 종목 신뢰도를 내고,
    신뢰도가 낮거나 호·악재가 엇갈리면 종목 판정을 자동 중립(score 0)으로 만든다.
    제목뿐 아니라 본문 발췌까지 함께 보고 판정하므로 단순 제목 판정보다 정확하다."""
    if not _api_key or not items:
        return {}
    flat, lines, gid = [], [], 1   # flat: (gid, code, art_idx, title)
    for code, name, articles in items:
        for ai_idx, art in enumerate(articles):
            if isinstance(art, (list, tuple)):
                title = (art[0] or "").strip() if len(art) > 0 else ""
                excerpt = (art[1] or "").strip() if len(art) > 1 else ""
            else:
                title, excerpt = (art or "").strip(), ""
            if not title:
                continue
            flat.append((gid, code, ai_idx, title))
            body = f" — 본문: {excerpt}" if excerpt else ""
            lines.append(f"{gid}. [{name}] 제목: {title}{body}")
            gid += 1
    if not flat:
        return {}
    block = "\n".join(lines)
    prompt = (
        "너는 한국 주식 뉴스 애널리스트다. 아래 '개별 기사'(제목 + 본문 발췌)마다 그 종목 주가에 미칠 "
        "영향을 호재/중립/악재로 판정하라. 제목이 애매해도 본문 발췌의 사실(수주·실적·소송·증설·계약·"
        "규제·인수 등)을 근거로 판단하라.\n"
        "JSON 배열만 출력(설명·마크다운·코드펜스 금지). 각 원소는 "
        '{"i":번호,"label":"호재|중립|악재","score":정수,"conf":"상|중|하"}.\n'
        "score: 강한호재 2, 호재 1, 중립 0, 악재 -1, 강한악재 -2. "
        "conf(판정 확신도): 본문 근거가 분명하면 상, 보통이면 중, 모호·단순시황·전망성이면 하.\n\n"
        f"{block}"
    )
    art = {}   # gid -> (label, score, conf)
    try:
        raw = ask_gemini(prompt, _api_key)
        txt = (raw or "").strip().replace("```json", "").replace("```", "").strip()
        m = re.search(r"\[.*\]", txt, re.DOTALL)
        if m:
            txt = m.group(0)
        for it in json.loads(txt):
            if not isinstance(it, dict):
                continue
            i = it.get("i")
            if i is None:
                continue
            label = str(it.get("label", "중립")).strip()
            if label not in ("호재", "중립", "악재"):
                label = "중립"
            try:
                sc = max(-2, min(2, int(round(float(it.get("score", 0))))))
            except Exception:
                sc = {"호재": 1, "악재": -1}.get(label, 0)
            conf = str(it.get("conf", "중")).strip()
            if conf not in ("상", "중", "하"):
                conf = "중"
            art[int(i)] = (label, sc, conf)
    except Exception:
        art = {}

    W = {"상": 1.0, "중": 0.6, "하": 0.3}
    grouped = {}   # code -> [(gid, title), ...]
    for gid_, code, ai_idx, title in flat:
        grouped.setdefault(code, []).append((gid_, title))

    out = {}
    for code, lst in grouped.items():
        article_labels, contrib = [], []
        pos_w = neg_w = 0.0
        dom = (0.0, "")   # (영향 크기, 제목)
        for gid_, title in lst:
            label, sc, conf = art.get(gid_, ("중립", 0, "중"))
            article_labels.append((label, sc))
            w = W.get(conf, 0.6)
            contrib.append(sc * w)
            if sc > 0:
                pos_w += w
            elif sc < 0:
                neg_w += w
            mag = abs(sc) * w
            if mag > dom[0]:
                dom = (mag, title)
        n = len(lst)
        total = sum(contrib)
        avg = total / n if n else 0.0
        denom = pos_w + neg_w
        agreement = abs(pos_w - neg_w) / denom if denom > 0 else 0.0   # 1=한 방향, 0=엇갈림
        strength = min(1.0, abs(avg))
        confidence = round(agreement * strength, 2)
        if denom == 0 or confidence < 0.35:
            label, score, auto = "중립", 0, True
            reason = "기사 신호가 약하거나 호·악재가 엇갈려 중립 처리"
        else:
            score = max(-2, min(2, int(round(avg))))
            if score == 0:
                score = 1 if total > 0 else -1
            label = "호재" if score > 0 else "악재"
            auto = False
            reason = (f"‘{dom[1][:28]}…’ 등 기사 근거" if dom[1] else "")
        out[code] = {"label": label, "score": score, "confidence": confidence,
                     "auto_neutral": auto, "reason": reason, "article_labels": article_labels}
    return out


@st.cache_data(ttl=900, show_spinner=False)
def get_theme_politics_radar(_api_key, news_titles=None, poly_lines=None):
    """뉴스 헤드라인 + 폴리마켓(정치/매크로)을 AI로 종합 →
    핵심 테마/이벤트(+권장 투자기간, 종목검색 키워드) + 한 줄 분위기 코멘트(JSON)."""
    fallback = {"mood_comment": "", "themes": []}
    if not _api_key:
        return fallback
    news_block = "\n".join(f"- {t}" for t in (news_titles or [])[:18]) or "(뉴스 없음)"
    poly_block = "\n".join(f"- {p}" for p in (poly_lines or [])[:10]) or "(예측시장 없음)"
    prompt = (
        "너는 한국 주식시장 전략가다. 아래 '실시간 국내 증시 뉴스 헤드라인'과 "
        "'글로벌 예측시장(정치·매크로) 확률'을 종합해, 지금 시장을 움직이는 핵심 테마/이벤트를 도출하라.\n\n"
        f"[증시 뉴스]\n{news_block}\n\n[예측시장]\n{poly_block}\n\n"
        "아래 JSON만 출력하라(설명·마크다운·코드펜스 금지):\n"
        '{"mood_comment":"오늘 시장 분위기 한 줄 요약",'
        '"themes":[{"theme":"테마명","horizon":"단기|중기|장기",'
        '"reason":"왜 지금 부각되는지 한 문장","keywords":"종목 검색용 핵심 키워드"}]}\n'
        "규칙: themes 는 3~5개. horizon 은 그 테마 성격상 가장 적합한 투자기간 하나로 정하라. "
        "정치/정책/단발 이벤트성→단기, 산업 사이클·실적 모멘텀→중기, 구조적 성장·저평가 재평가→장기."
    )
    try:
        raw = ask_gemini(prompt, _api_key)
        txt = (raw or "").strip().replace("```json", "").replace("```", "").strip()
        m = re.search(r"\{.*\}", txt, re.DOTALL)
        if m:
            txt = m.group(0)
        data = json.loads(txt)
        if isinstance(data, dict) and isinstance(data.get("themes"), list):
            clean = []
            for it in data["themes"][:5]:
                if not isinstance(it, dict):
                    continue
                hz = str(it.get("horizon", "")).strip()
                hz = hz if hz in ("단기", "중기", "장기") else "중기"
                clean.append({
                    "theme": str(it.get("theme", "")).strip()[:40],
                    "horizon": hz,
                    "reason": str(it.get("reason", "")).strip()[:140],
                    "keywords": str(it.get("keywords", it.get("theme", ""))).strip()[:60],
                })
            return {"mood_comment": str(data.get("mood_comment", "")).strip()[:180],
                    "themes": clean}
    except Exception as _dg_e:
        _diag_note("get_theme_politics_radar", _dg_e)
        pass
    return fallback


@st.cache_data(ttl=600, show_spinner=False)
def get_news_issue_impact(_api_key, news_titles, top_n=3):
    """[뉴스 이슈 → 영향 관계] 실시간 헤드라인 + 구글 검색 그라운딩으로 '오늘의 핵심 증시 이슈
    TOP N'을 선별·요약하고, 각 이슈가 어떤 업종/종목에 호재(긍정)·악재(부정)·중립으로
    작용하는지 '영향 관계'를 JSON으로 생성한다.
    반환: {"issues":[{rank,title,summary,points[],sources[],
                     impacts[{target,kind,sentiment,reason,tickers[{name,code}]}]}],
           "generated_at":"HH:MM"}"""
    now_kst = datetime.utcnow() + timedelta(hours=9)
    fallback = {"issues": [], "generated_at": now_kst.strftime("%H:%M")}
    if not _api_key:
        return fallback
    head_block = "\n".join(f"- {t}" for t in (news_titles or [])[:25]) or "(헤드라인 없음)"
    prompt = (
        "너는 한국 주식시장 전략가다. 지금 한국 증시에서 가장 영향력 있는 핵심 뉴스 이슈를 선별하고, "
        "각 이슈가 어떤 업종/종목에 호재(긍정)·악재(부정)·중립으로 작용하는지 '영향 관계'를 정리하라.\n"
        "반드시 '구글 검색'으로 오늘 시점의 최신 보도를 직접 확인한 뒤 작성하라.\n\n"
        f"[참고용 실시간 증시 헤드라인]\n{head_block}\n\n"
        f"아래 JSON만 출력하라(설명·마크다운·코드펜스 금지). 이슈는 영향력 큰 순으로 정확히 {int(top_n)}개:\n"
        '{"issues":[{'
        '"title":"이슈 제목(12자 내외 핵심 명사구)",'
        '"summary":"무슨 일인지 + 증시에 왜 중요한지 2~3문장. \'~해요\' 체로 부드럽게.",'
        '"points":["주목할 포인트 1","2","3"],'
        '"sources":["실제 참고한 언론사명1","언론사명2"],'
        '"impacts":[{"target":"영향받는 업종 또는 테마/종목","kind":"섹터|종목|자산",'
        '"sentiment":"긍정|부정|중립","reason":"왜 그렇게 영향받는지 한 문장",'
        '"tickers":[{"name":"대표 종목명","code":"6자리 코드(모르면 빈 문자열)"}]}]'
        '}]}\n'
        "규칙: 1) impacts 는 이슈당 2~5개, 호재와 악재를 균형 있게 포함. "
        "2) tickers 는 각 영향마다 1~3개 한국 상장 대표주, code 는 6자리 숫자를 정확히(불확실하면 빈 문자열). "
        "3) sources 는 실제 검색에서 확인한 매체명만(과장 금지). "
        "4) 정치·정책·수급·실적·매크로 등 '증시에 직접 영향 주는' 이슈만. 연예/스포츠 등 비증시 이슈 제외."
    )
    try:
        raw = ask_gemini(prompt, _api_key, grounding=True)
        txt = (raw or "").strip().replace("```json", "").replace("```", "").strip()
        m = re.search(r"\{.*\}", txt, re.DOTALL)
        if m:
            txt = m.group(0)
        data = json.loads(txt)
        issues_in = data.get("issues") if isinstance(data, dict) else None
        if not isinstance(issues_in, list):
            return fallback
        _SENT_OK = {"긍정", "부정", "중립"}
        clean_issues = []
        for i, it in enumerate(issues_in[:int(top_n)]):
            if not isinstance(it, dict):
                continue
            title = str(it.get("title", "")).strip()[:40]
            if not title:
                continue
            impacts = []
            for im in (it.get("impacts") or [])[:6]:
                if not isinstance(im, dict):
                    continue
                tgt = str(im.get("target", "")).strip()[:24]
                if not tgt:
                    continue
                sent = str(im.get("sentiment", "")).strip()
                sent = sent if sent in _SENT_OK else "중립"
                tks = []
                for tk in (im.get("tickers") or [])[:3]:
                    if isinstance(tk, dict):
                        nm = str(tk.get("name", "")).strip()[:20]
                        cd = re.sub(r"\D", "", str(tk.get("code", "")))[:6]
                        if nm:
                            tks.append({"name": nm, "code": cd})
                impacts.append({
                    "target": tgt,
                    "kind": (str(im.get("kind", "섹터")).strip()[:6] or "섹터"),
                    "sentiment": sent,
                    "reason": str(im.get("reason", "")).strip()[:120],
                    "tickers": tks,
                })
            srcs = [str(s).strip()[:24] for s in (it.get("sources") or []) if str(s).strip()][:12]
            clean_issues.append({
                "rank": i + 1,
                "title": title,
                "summary": str(it.get("summary", "")).strip()[:400],
                "points": [str(p).strip()[:120] for p in (it.get("points") or []) if str(p).strip()][:5],
                "sources": srcs,
                "impacts": impacts,
            })
        return {"issues": clean_issues, "generated_at": now_kst.strftime("%H:%M")}
    except Exception as _dg_e:
        _diag_note("get_news_issue_impact", _dg_e)
        return fallback


def get_finder_briefing(_api_key, mood, radar, bucket_tops):
    """시장분위기 + 테마 + 기간별 상위픽을 묶어 '오늘의 통합 전략 브리핑' 생성."""
    if not _api_key:
        return ""
    lines = []
    for hz in ("단기", "중기", "장기"):
        picks = bucket_tops.get(hz) or []
        if picks:
            lines.append(f"[{hz}] " + ", ".join(f"{n}({s:.0f}점)" for n, s in picks[:3]))
    picks_block = "\n".join(lines) or "(선별된 종목 없음)"
    themes_block = ", ".join(t["theme"] for t in (radar.get("themes") or [])[:5]) or "-"
    prompt = (
        "너는 여의도 시니어 전략가다. 아래 데이터로 개인투자자용 '오늘의 통합 투자 전략'을 한국어로 작성하라.\n"
        f"- 시장국면: {mood['light']} {mood['title']} (위험선호 {mood['risk_on']:+.2f}, "
        f"VIX {mood.get('vix')}, 공포탐욕 {mood.get('fng')})\n"
        f"- 핵심 테마: {themes_block}\n"
        f"- 기간별 상위 후보:\n{picks_block}\n\n"
        "형식:\n"
        "1) 한 줄 총평(지금 시장 성격과 대응 톤)\n"
        "2) 단기/중기/장기 각각 1~2문장 대응 전략(왜 이 분위기에서 그 기간이 유효/불리한지 포함)\n"
        "3) 리스크 관리 한 줄\n"
        "과장 금지, 투자 권유가 아닌 참고 정보임을 전제. 불릿/번호로 간결하게."
    )
    try:
        return ask_gemini(prompt, _api_key)
    except Exception as _dg_e:
        _diag_note("get_finder_briefing", _dg_e)
        return ""


# `from core_ai import *` 로 넘어갈 이름 (언더스코어 포함, 자동 생성)
_EXPORTED = [
    "_genai_generate",
    "ask_gemini",
    "ask_gemini_vision",
    "classify_news_sentiment",
    "get_daily_market_briefing",
    "get_finder_briefing",
    "get_granular_themes",
    "get_growth_fund_stocks_with_ai",
    "get_longterm_value_stocks_with_ai",
    "get_news_issue_impact",
    "get_theme_politics_radar",
    "get_theme_stocks_with_ai",
    "get_trending_themes_with_ai",
]

__all__ = [_n for _n in _EXPORTED if _n in globals()]
