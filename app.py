import streamlit as st
import pandas as pd
import requests
from bs4 import BeautifulSoup
from io import StringIO
import yfinance as yf
import FinanceDataReader as fdr
from datetime import datetime, timedelta
import google.generativeai as genai
import urllib.parse
import re
from streamlit_autorefresh import st_autorefresh

# ==========================================
# 1. 초기 설정 및 세션 상태 초기화
# ==========================================
st.set_page_config(page_title="단기 스윙 주식 검색기", layout="wide")

st_autorefresh(interval=300000, limit=None, key="news_autorefresh")

if 'seen_links' not in st.session_state:
    st.session_state.seen_links = set()
if 'news_data' not in st.session_state:
    st.session_state.news_data = []

# ==========================================
# 2. 데이터 수집 및 분석 함수들
# ==========================================
@st.cache_data(ttl=3600)
def get_us_top_gainers():
    try:
        url = 'https://finance.yahoo.com/gainers'
        headers = {'User-Agent': 'Mozilla/5.0'}
        response = requests.get(url, headers=headers)
        tables = pd.read_html(StringIO(response.text))
        df = tables[0]
        
        df = df.loc[:, ~df.columns.str.contains('^Unnamed')]
        df = df.iloc[:, :6] 
        
        df.columns = ['종목코드', '기업명', '현재가', '등락금액', '등락률', '거래량']
        
        def extract_pct(x):
            try:
                match = re.search(r'([+-]?\d+\.?\d*)%', str(x))
                if match:
                    return float(match.group(1))
                clean = re.sub(r'[^\d\.\+\-]', '', str(x))
                return float(clean)
            except:
                return 0.0
                
        df['실제등락률'] = df['등락률'].apply(extract_pct)
        df = df[df['실제등락률'] >= 10.0] 
        df = df.drop(columns=['실제등락률']) 
        
        df['종목코드'] = df['종목코드'].astype(str).apply(lambda x: x.split()[0])
        
        def get_korean_name(name):
            try:
                encoded_name = urllib.parse.quote(name)
                api_url = f"https://translate.googleapis.com/translate_a/single?client=gtx&sl=en&tl=ko&dt=t&q={encoded_name}"
                res = requests.get(api_url, timeout=2)
                ko_name = res.json()[0][0][0]
                if ko_name.lower() != name.lower() and ko_name.strip():
                    return f"{name} / {ko_name}"
                return name
            except:
                return name
                
        df['기업명'] = df['기업명'].apply(get_korean_name)
        
        try:
            ex_rate_data = yf.Ticker("KRW=X").history(period="1d")
            ex_rate = ex_rate_data['Close'].iloc[-1]
        except:
            ex_rate = 1350.0 
            
        def format_price(x):
            try:
                clean_price_str = str(x).split()[0].replace(',', '')
                val = float(clean_price_str)
                return f"${val:.2f} (약 {int(val * ex_rate):,}원)"
            except:
                return str(x)
                
        df['현재가'] = df['현재가'].apply(format_price)
        return df, ex_rate
    except Exception as e:
        st.error(f"미국장 데이터 수집 중 오류 발생: {e}")
        return pd.DataFrame(), 1350.0

@st.cache_data(ttl=86400)
def get_krx_stocks():
    try:
        df = fdr.StockListing('KRX')
        return df[['Name', 'Code']]
    except Exception:
        try:
            url = 'http://kind.krx.co.kr/corpgeneral/corpList.do?method=download&searchType=13'
            headers = {'User-Agent': 'Mozilla/5.0'}
            res = requests.get(url, headers=headers)
            res.encoding = 'euc-kr' 
            
            df = pd.read_html(StringIO(res.text), header=0)[0]
            df = df[['회사명', '종목코드']]
            df.columns = ['Name', 'Code']
            df['Code'] = df['Code'].astype(str).str.zfill(6)
            return df
        except Exception as e:
            st.error(f"국내 주식 목록 수집 중 오류가 발생했습니다: {e}")
            return pd.DataFrame(columns=['Name', 'Code'])

def fetch_news():
    base_url = "https://finance.naver.com"
    list_url = f"{base_url}/news/news_list.naver?mode=LSS2D&section_id=101&section_id2=258"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    
    try:
        res = requests.get(list_url, headers=headers)
        res.raise_for_status()
        res.encoding = 'euc-kr'
        soup = BeautifulSoup(res.text, 'html.parser')
        
        subject_tags = soup.select("dl dd.articleSubject a")
        new_items_count = 0
        
        kst_now = datetime.utcnow() + timedelta(hours=9)
        
        for tag in subject_tags:
            title = tag.get_text(strip=True)
            link = tag['href']
            full_link = base_url + link if link.startswith("/") else link
            
            if full_link in st.session_state.seen_links:
                continue
                
            current_time = kst_now.strftime("%H:%M")
            st.session_state.news_data.insert(0, {
                "time": current_time,
                "title": title,
                "link": full_link
            })
            
            st.session_state.seen_links.add(full_link)
            new_items_count += 1
            
        return new_items_count
    except Exception as e:
        return 0

@st.cache_data(ttl=3600)
def get_basic_sector_info(ticker):
    try:
        stock = yf.Ticker(ticker)
        sector = stock.info.get('sector', 'Unknown')
        industry = stock.info.get('industry', 'Unknown')
        return sector, industry
    except:
        return "Unknown", "Unknown"

@st.cache_data(ttl=3600)
def get_ai_matched_stocks(ticker, sector, industry, comp_name, api_key):
    if not api_key: return []
    try:
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel('gemini-2.5-flash')
        prompt = f"""
        당신은 한국 주식 전문가입니다.
        미국 주식 '{comp_name}' (티커: {ticker}, 섹터: {sector}, 산업: {industry})와 
        비즈니스 모델이 유사하거나, 같은 테마로 움직일 수 있는 한국 코스피/코스닥 상장사 10개를 찾아주세요.
        정보가 부족하면 티커와 기업명을 바탕으로 유추해서라도 반드시 10개를 채워주세요.
        반드시 아래 예시와 같은 파이썬 리스트 형태로만 답변하세요. 부가 설명은 절대 금지입니다.
        예시: [('삼성전자', '005930'), ('카카오', '035720')]
        """
        response = model.generate_content(prompt)
        pattern = r"['\"]([^'\"]+)['\"]\s*,\s*['\"]([0-9]{6})['\"]"
        matches = re.findall(pattern, response.text)
        return matches[:10] if matches else []
    except Exception as e:
        return []

# 💡 신규: 직접 입력한 테마 키워드로 관련주를 찾아주는 AI 함수
@st.cache_data(ttl=3600)
def get_theme_stocks_with_ai(theme_keyword, api_key):
    if not api_key: return []
    try:
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel('gemini-2.5-flash')
        prompt = f"""
        당신은 한국 주식 전문가입니다.
        사용자가 입력한 테마명: '{theme_keyword}'
        이 테마와 관련된 한국 코스피/코스닥 대장주 및 주요 관련주 10개를 찾아주세요.
        반드시 아래 예시와 같은 파이썬 리스트 형태로만 답변하세요. 부가 설명이나 코멘트는 절대 금지입니다.
        예시: [('에코프로', '086520'), ('LG에너지솔루션', '373220')]
        """
        response = model.generate_content(prompt)
        pattern = r"['\"]([^'\"]+)['\"]\s*,\s*['\"]([0-9]{6})['\"]"
        matches = re.findall(pattern, response.text)
        return matches[:10] if matches else []
    except Exception as e:
        return []

def analyze_technical_pattern(stock_name, ticker_code):
    if not ticker_code: return None
    try:
        start_date = (datetime.now() - timedelta(days=90)).strftime('%Y-%m-%d')
        df = fdr.DataReader(ticker_code, start_date)
        if len(df) < 20: return None
        
        df['MA20'] = df['Close'].rolling(window=20).mean()
        df['Vol_MA20'] = df['Volume'].rolling(window=20).mean()
        df['Std_20'] = df['Close'].rolling(window=20).std()
        df['Bollinger_Upper'] = df['MA20'] + (df['Std_20'] * 2)
        
        latest = df.iloc[-1]
        recent_10_days = df.iloc[-10:]
        is_volume_spike = recent_10_days['Volume'].max() > (recent_10_days['Vol_MA20'].mean() * 2)
        
        current_price = latest['Close']
        ma20_price = latest['MA20']
        target_price = latest['Bollinger_Upper'] 
        stop_loss_price = ma20_price * 0.97      
        
        if (ma20_price * 0.97) <= current_price <= (ma20_price * 1.03):
            status = "✅ 타점 근접 (분할 매수 고려)"
        elif current_price > (ma20_price * 1.03):
            status = "⚠️ 관심 집중 (단기 급등, 눌림목 대기)"
        else:
            status = "🛑 추세 이탈 (관망/손절 구간)"
            
        return {
            "종목명": stock_name,
            "현재가": int(current_price),
            "상태": status,
            "진입가_가이드": int(ma20_price),
            "목표가": int(target_price),
            "손절가": int(stop_loss_price),
            "최근_거래량": int(latest['Volume']),
            "거래량 급증": "🔥 거래량 터짐" if is_volume_spike else "평이함",
            "종가 데이터": df['Close'].tail(20),
            "거래량 데이터": df['Volume'].tail(20)
        }
    except:
        return None

def get_company_summary(ticker, api_key):
    try:
        genai.configure(api_key=api_key)
        stock = yf.Ticker(ticker)
        info = stock.info
        name = info.get('longName', ticker)
        biz_summary = info.get('longBusinessSummary', '기업 정보가 없습니다.')
        if biz_summary == '기업 정보가 없습니다.':
            return f"**{name}**에 대한 상세 정보가 제공되지 않습니다."
        prompt = f"미국 주식 {name}({ticker})의 영문 기업 개요를 읽고, 이 회사가 도대체 '무엇을 만들고 어떻게 돈을 버는 기업인지' 한국어로 딱 2줄로 요약해 주세요. [영문 개요]: {biz_summary[:1500]}"
        model = genai.GenerativeModel('gemini-2.5-flash')
        response = model.generate_content(prompt)
        return f"**{name}**\n\n{response.text}"
    except Exception as e:
        return "기업 정보를 요약하는 중 오류가 발생했습니다."

def analyze_news_with_gemini(ticker, api_key):
    try:
        genai.configure(api_key=api_key)
        stock = yf.Ticker(ticker)
        news_list = stock.news
        if not news_list: return "최근 관련 뉴스를 찾을 수 없습니다."
        news_text = ""
        for i, news in enumerate(news_list[:3]):
            title = news.get('title', '제목 없음')
            publisher = news.get('publisher', '출처 없음')
            news_text += f"{i+1}. [{publisher}] {title}\n"
        prompt = f"당신은 한국 주식 시장에서 단기 스윙 투자를 전문으로 하는 애널리스트입니다. 미국 주식 '{ticker}'에 대한 최근 영문 뉴스 헤드라인입니다. 이 이슈가 동조화되는 한국 관련 테마주에 미칠 영향을 분석해 주세요. [최신 뉴스 헤드라인]\n{news_text}\n아래 3가지 항목만 간결하게 한국어로 답변해 주세요.\n* **시장 센티먼트:** (강력 호재 / 약한 호재 / 중립 / 악재 중 택 1)\n* **재료의 지속성 예상:** (단발성 / 1주일 내외 / 1개월 이상 중 택 1)\n* **스윙 투자 코멘트:** (이 뉴스가 한국 관련 섹터에 줄 영향을 2~3줄로 요약)"
        model = genai.GenerativeModel('gemini-2.5-flash')
        response = model.generate_content(prompt)
        return response.text
    except Exception as e:
        return "뉴스 분석 중 오류가 발생했습니다."

# ==========================================
# 3. 사이드바 및 UI 화면 구성 (탭 분리)
# ==========================================
st.title("📈 종합 스윙 트레이딩 대시보드")

with st.sidebar:
    st.header("⚙️ 설정")
    fetch_button = st.button("미국장 급등주 다시 불러오기 🔄", type="primary")
    st.divider()
    st.header("🧠 AI 뉴스 분석 설정")
    if "GEMINI_API_KEY" in st.secrets:
        api_key_input = st.secrets["GEMINI_API_KEY"]
        st.success("✅ 시스템 API 키가 자동으로 적용되었습니다.")
    else:
        api_key_input = st.text_input("Gemini API Key를 입력하세요", type="password")

if "gainers_df" not in st.session_state or fetch_button:
    with st.spinner('미국장 폭등주(+10% 이상) 데이터를 선별 중입니다...'):
        df, ex_rate = get_us_top_gainers()
        st.session_state.gainers_df = df
        st.session_state.ex_rate = ex_rate

# 💡 신규: 탭을 4개로 확장 (테마주 검색 탭 추가)
tab1, tab2, tab3, tab4 = st.tabs([
    "🇺🇸 미국 주도주 스윙 검색기", 
    "🎯 국내 개별 종목 검색", 
    "💡 테마/관련주 AI 발굴", 
    "📰 실시간 금융 속보"
])

# ------------------------------------------
# [탭 1] 미국장 기반 스윙 검색기
# ------------------------------------------
with tab1:
    col1, col2 = st.columns([1, 1.2])

    with col1:
        us_time = datetime.utcnow() - timedelta(hours=5) 
        us_date_str = us_time.strftime("%Y-%m-%d")
        
        st.subheader("🔥 미국장 급등 종목 (+10% 이상)")
        current_ex_rate = st.session_state.get('ex_rate', 1350.0)
        st.caption(f"**기준일:** {us_date_str} (뉴욕 시간) | **적용 환율:** 1달러 = {int(current_ex_rate):,}원")
        
        if not st.session_state.gainers_df.empty:
            st.dataframe(st.session_state.gainers_df, use_container_width=True, hide_index=True)
            tickers_list = st.session_state.gainers_df['종목코드'].tolist()
            options = []
            
            with st.spinner("테마/섹터 정보를 불러오는 중입니다..."):
                for index, row in st.session_state.gainers_df.iterrows():
                    t = row['종목코드']
                    full_name = row['기업명']
                    kor_name = full_name.split(' / ')[-1] if ' / ' in full_name else full_name
                    sec, ind = get_basic_sector_info(t)
                    options.append(f"{t} ({kor_name}) - ({sec} / {ind})")
                    
            selected_option = st.selectbox("👉 분석할 미국 주식 테마를 선택하세요:", options)
            selected_ticker = selected_option.split(" ")[0]
        else:
            selected_ticker = "N/A"
            st.info("현재 +10% 이상 급등한 종목이 없습니다.")

    with col2:
        st.subheader("🎯 테마 매칭 및 타점 분석")
        
        st.info("""
        **[매매 가이드라인 안내]**
        * ✅ **타점 근접:** 주가가 20일선 근처에 있어 **분할 매수하기 가장 좋은 위치**입니다.
        * ⚠️ **관심 집중:** 최근 급등하여 20일선과 벌어져 있습니다. (눌림목이 올 때까지 관망)
        * 🛑 **추세 이탈:** 20일선을 하향 이탈했습니다. (손절 또는 접근 금지)
        * 🎯 **1차 목표가 (볼린저 상단):** 단기 슈팅(급등) 시 통계적으로 강력한 저항을 받을 확률이 높은 가격대입니다.
        """)
        
        if selected_ticker != "N/A":
            sector, industry = get_basic_sector_info(selected_ticker)
            st.write(f"- **분석 종목 티커:** {selected_ticker} ({sector} / {industry})")
            
            if api_key_input:
                with st.spinner('기업 정보를 한국어로 요약 중입니다...'):
                    st.success(f"🏢 **어떤 기업인가요?**\n\n{get_company_summary(selected_ticker, api_key_input)}")
            else:
                st.info("👈 API 키를 넣으시면 기업 한글 요약을 볼 수 있습니다.")
            
            st.divider()
            st.subheader("🧠 Gemini 최신 뉴스 센티먼트 판독")
            
            if api_key_input:
                with st.spinner('최신 뉴스를 가져와 분석 중입니다...'):
                    st.info(analyze_news_with_gemini(selected_ticker, api_key_input))
            
            st.divider()
            
            kor_stocks = []
            is_ai_matched = False
            
            if api_key_input:
                with st.spinner('AI가 기업 정보를 분석하여 연관된 한국 주식을 최대 10개까지 실시간 발굴 중입니다...'):
                    comp_name = selected_option.split(" - ")[0]
                    kor_stocks = get_ai_matched_stocks(selected_ticker, sector, industry, comp_name, api_key_input)
                    if kor_stocks:
                        is_ai_matched = True
            
            if not kor_stocks:
                st.warning("⚠️ 매핑된 국내 주식이 없거나 AI 분석 중 오류가 발생했습니다. (사이드바에 API 키를 입력해 주세요!)")
            else:
                st.write("✨ **AI가 기업 정보를 바탕으로 실시간 발굴한 연관 국내 주식입니다!**")
                
                for stock_name, ticker_code in kor_stocks:
                    tech_result = analyze_technical_pattern(stock_name, ticker_code)
                    if tech_result:
                        status_emoji = tech_result['상태'].split(' ')[0]
                        with st.expander(f"{status_emoji} {stock_name} (현재가: {tech_result['현재가']:,}원)", expanded=False):
                            st.markdown(f"**진단 상태:** {tech_result['상태']}")
                            p_col1, p_col2, p_col3 = st.columns(3)
                            
                            p_col1.metric("💡 진입 기준가", f"{tech_result['진입가_가이드']:,}원")
                            p_col2.metric("🎯 1차 목표가 (볼린저 상단)", f"{tech_result['목표가']:,}원")
                            p_col3.metric("🛑 기계적 손절가", f"{tech_result['손절가']:,}원")
                            
                            st.divider()
                            st.metric("수급 분석", f"{tech_result['최근_거래량']:,}주", tech_result["거래량 급증"])
                            chart_col1, chart_col2 = st.columns(2)
                            with chart_col1:
                                st.caption("📈 최근 20일 주가 흐름")
                                st.line_chart(tech_result["종가 데이터"], height=150)
                            with chart_col2:
                                st.caption("📊 최근 20일 거래량")
                                st.bar_chart(tech_result["거래량 데이터"], height=150)

# ------------------------------------------
# [탭 2] 국내 개별 종목 타점 검색
# ------------------------------------------
with tab2:
    st.subheader("🔍 국내 개별 종목 타점 진단기")
    st.write("관심 있는 국내 주식을 검색하면 즉시 20일선 및 볼린저 밴드 기준 기술적 분석 타점을 제공합니다.")
    
    krx_df = get_krx_stocks()
    
    if not krx_df.empty:
        krx_options = [""] + (krx_df['Name'] + " (" + krx_df['Code'] + ")").tolist()
        search_query = st.selectbox("👇 종목명 또는 초성을 입력하여 검색하세요:", krx_options)
        
        if search_query:
            st.divider()
            st.info("**[매매 가이드라인 안내]**\n* ✅ **타점 근접:** 분할 매수하기 좋은 위치\n* ⚠️ **관심 집중:** 급등 후 이격 발생 (눌림목 대기)\n* 🛑 **추세 이탈:** 하향 이탈 (손절/접근 금지)")
            
            searched_name = search_query.split(" (")[0]
            searched_code = search_query.split("(")[1].replace(")", "")
            
            with st.spinner(f"'{searched_name}' 기술적 타점 분석 중..."):
                tech_result = analyze_technical_pattern(searched_name, searched_code)
                
            if tech_result:
                status_emoji = tech_result['상태'].split(' ')[0]
                with st.expander(f"{status_emoji} {searched_name} (현재가: {tech_result['현재가']:,}원)", expanded=True):
                    st.markdown(f"**진단 상태:** {tech_result['상태']}")
                    p_col1, p_col2, p_col3 = st.columns(3)
                    p_col1.metric("💡 진입 기준가", f"{tech_result['진입가_가이드']:,}원")
                    p_col2.metric("🎯 1차 목표가 (볼린저 상단)", f"{tech_result['목표가']:,}원")
                    p_col3.metric("🛑 기계적 손절가", f"{tech_result['손절가']:,}원")
                    st.divider()
                    st.metric("수급 분석", f"{tech_result['최근_거래량']:,}주", tech_result["거래량 급증"])
                    chart_col1, chart_col2 = st.columns(2)
                    with chart_col1:
                        st.caption("📈 최근 20일 주가 흐름")
                        st.line_chart(tech_result["종가 데이터"], height=200) 
                    with chart_col2:
                        st.caption("📊 최근 20일 거래량")
                        st.bar_chart(tech_result["거래량 데이터"], height=200)
            else:
                st.error("데이터를 불러올 수 없습니다. (최소 20일의 거래 데이터 필요)")

# ------------------------------------------
# [탭 3] 💡 신규: 테마/관련주 AI 검색
# ------------------------------------------
with tab3:
    st.subheader("💡 테마 및 관련주 실시간 AI 발굴기")
    st.write("관심 있는 테마나 키워드(예: `2차전지`, `비만치료제`, `초전도체`)를 입력하시면, AI가 대장주와 관련주를 찾아 즉시 타점을 진단합니다.")
    
    theme_input = st.text_input("🔍 검색할 테마/키워드를 자유롭게 입력하세요:")
    
    if theme_input:
        if not api_key_input:
            st.error("⚠️ 좌측 사이드바에 API 키를 먼저 입력해야 AI 테마 발굴 기능이 작동합니다.")
        else:
            st.divider()
            with st.spinner(f"'{theme_input}' 관련주를 AI가 샅샅이 뒤지고 있습니다... (약 3~5초 소요)"):
                theme_stocks = get_theme_stocks_with_ai(theme_input, api_key_input)
            
            if not theme_stocks:
                st.error(f"'{theme_input}' 테마에 대한 관련주를 찾지 못했습니다. 다른 키워드로 검색해 보세요.")
            else:
                st.success(f"✨ **'{theme_input}' 관련주 {len(theme_stocks)}개 발굴 완료!** (아래에서 타점을 확인하세요)")
                
                for stock_name, ticker_code in theme_stocks:
                    tech_result = analyze_technical_pattern(stock_name, ticker_code)
                    if tech_result:
                        status_emoji = tech_result['상태'].split(' ')[0]
                        # 💡 연관 테마주는 빠르게 훑어볼 수 있도록 닫혀있게 설정
                        with st.expander(f"{status_emoji} {stock_name} (현재가: {tech_result['현재가']:,}원)", expanded=False):
                            st.markdown(f"**진단 상태:** {tech_result['상태']}")
                            p_col1, p_col2, p_col3 = st.columns(3)
                            
                            p_col1.metric("💡 진입 기준가", f"{tech_result['진입가_가이드']:,}원")
                            p_col2.metric("🎯 1차 목표가 (볼린저 상단)", f"{tech_result['목표가']:,}원")
                            p_col3.metric("🛑 기계적 손절가", f"{tech_result['손절가']:,}원")
                            
                            st.divider()
                            st.metric("수급 분석", f"{tech_result['최근_거래량']:,}주", tech_result["거래량 급증"])
                            chart_col1, chart_col2 = st.columns(2)
                            with chart_col1:
                                st.caption("📈 최근 20일 주가 흐름")
                                st.line_chart(tech_result["종가 데이터"], height=150)
                            with chart_col2:
                                st.caption("📊 최근 20일 거래량")
                                st.bar_chart(tech_result["거래량 데이터"], height=150)

# ------------------------------------------
# [탭 4] 실시간 금융 뉴스 탭
# ------------------------------------------
with tab4:
    st.subheader("📰 네이버 금융 실시간 시황/전망 속보")
    kst_now = datetime.utcnow() + timedelta(hours=9)
    st.caption(f"마지막 업데이트 시간: {kst_now.strftime('%Y-%m-%d %H:%M:%S')} (5분 주기 자동 갱신 중)")
    
    with st.spinner('새로운 뉴스를 확인하는 중입니다...'):
        new_count = fetch_news()

    if new_count > 0:
        st.toast(f"새로운 실시간 뉴스 {new_count}건이 업데이트 되었습니다!", icon="✅")

    st.divider()

    if not st.session_state.news_data:
        st.info("현재 수집된 뉴스가 없습니다. 5분 뒤 자동으로 다시 확인합니다.")
    else:
        for news in st.session_state.news_data[:30]:
            with st.container():
                st.markdown(f"#### 🕒 [{news['time']}] {news['title']}")
                st.link_button("🔗 기사 원문 읽기", news['link'])
                st.write("---")
