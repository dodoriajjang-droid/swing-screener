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
import plotly.express as px
from streamlit_autorefresh import st_autorefresh

# ==========================================
# 1. 초기 설정 
# ==========================================
st.set_page_config(page_title="Jaemini 주식 검색기", layout="wide", page_icon="📈")

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
                if match: return float(match.group(1))
                return float(re.sub(r'[^\d\.\+\-]', '', str(x)))
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
            ex_rate_data = yf.Ticker("KRW=X").history(period="5d")
            ex_rate = ex_rate_data['Close'].iloc[-1]
        except:
            ex_rate = 1350.0 
            
        def format_price(x):
            try:
                val = float(str(x).split()[0].replace(',', ''))
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
        if not df.empty: return df[['Name', 'Code']]
    except: pass
    
    try:
        kospi = fdr.StockListing('KOSPI')
        kosdaq = fdr.StockListing('KOSDAQ')
        df = pd.concat([kospi, kosdaq], ignore_index=True)
        if not df.empty: return df[['Name', 'Code']]
    except: pass

    try:
        url = 'http://kind.krx.co.kr/corpgeneral/corpList.do?method=download&searchType=13'
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8'
        }
        res = requests.get(url, headers=headers, timeout=10)
        res.encoding = 'euc-kr' 
        df = pd.read_html(StringIO(res.text), header=0)[0]
        df = df[['회사명', '종목코드']]
        df.columns = ['Name', 'Code']
        df['Code'] = df['Code'].astype(str).str.zfill(6)
        return df
    except Exception as e:
        st.error(f"⚠️ 국내 주식 목록 서버(KRX) 통신 장애가 발생했습니다. (사유: {e})")
        return pd.DataFrame(columns=['Name', 'Code'])

def fetch_news():
    base_url = "https://finance.naver.com"
    list_url = f"{base_url}/news/news_list.naver?mode=LSS2D&section_id=101&section_id2=258"
    headers = {"User-Agent": "Mozilla/5.0"}
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
            st.session_state.news_data.insert(0, {
                "time": kst_now.strftime("%H:%M"), "title": title, "link": full_link
            })
            st.session_state.seen_links.add(full_link)
            new_items_count += 1
        return new_items_count
    except Exception:
        return 0

@st.cache_data(ttl=3600)
def get_all_sector_info(tickers, api_key):
    results = {t: ("분석 대기", "분석 대기") for t in tickers}
    if not api_key:
        return results
        
    try:
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel('gemini-2.5-flash')
        
        ticker_str = "\n".join(tickers)
        
        prompt = f"""
        당신은 월스트리트 주식 전문가입니다.
        다음 미국 주식 티커들의 섹터(Sector)와 세부 산업(Industry)을 '한국어'로 분류해주세요.
        반드시 아래 예시처럼 '티커|섹터|산업' 형태로만 답변하고 다른 말은 절대 하지 마세요.
        예시:
        AAPL|기술|소비자 가전
        TSLA|임의소비재|자동차 제조
        
        [티커 목록]
        {ticker_str}
        """
        
        response = model.generate_content(prompt)
        
        for line in response.text.strip().split('\n'):
            parts = line.split('|')
            if len(parts) >= 3:
                t = parts[0].strip().replace('*', '').replace('-', '')
                s = parts[1].strip()
                i = parts[2].strip()
                if t in results:
                    results[t] = (s, i)
        return results
    except Exception:
        return results

@st.cache_data(ttl=3600)
def get_ai_matched_stocks(ticker, sector, industry, comp_name, api_key):
    if not api_key: return []
    try:
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel('gemini-2.5-flash')
        prompt = f"""
        미국 주식 '{comp_name}' (티커: {ticker}, 섹터: {sector}, 산업: {industry})와 
        비즈니스 모델이 유사하거나, 같은 테마로 움직일 수 있는 한국 코스피/코스닥 상장사 20개를 찾아주세요.
        반드시 아래 형태의 파이썬 리스트로만 답변하세요. 
        예시: [('삼성전자', '005930'), ('카카오', '035720')]
        """
        response = model.generate_content(prompt)
        return re.findall(r"['\"]([^'\"]+)['\"]\s*,\s*['\"]([0-9]{6})['\"]", response.text)[:20]
    except Exception:
        return []

@st.cache_data(ttl=3600)
def get_theme_stocks_with_ai(theme_keyword, api_key):
    if not api_key: return []
    try:
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel('gemini-2.5-flash')
        prompt = f"""
        테마명: '{theme_keyword}'
        이 테마와 관련된 한국 코스피/코스닥 대장주 및 주요 관련주 20개를 찾아주세요.
        반드시 아래 형태의 파이썬 리스트로만 답변하세요.
        예시: [('에코프로', '086520')]
        """
        response = model.generate_content(prompt)
        return re.findall(r"['\"]([^'\"]+)['\"]\s*,\s*['\"]([0-9]{6})['\"]", response.text)[:20]
    except Exception:
        return []

def analyze_technical_pattern(stock_name, ticker_code):
    if not ticker_code: return None
    try:
        df = fdr.DataReader(ticker_code, (datetime.now() - timedelta(days=90)).strftime('%Y-%m-%d'))
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
            "종목명": stock_name, "현재가": int(current_price), "상태": status,
            "진입가_가이드": int(ma20_price), "목표가": int(target_price), "손절가": int(stop_loss_price),
            "최근_거래량": int(latest['Volume']), "거래량 급증": "🔥 거래량 급증" if is_volume_spike else "평이함",
            "종가 데이터": df['Close'].tail(20), "거래량 데이터": df['Volume'].tail(20)
        }
    except:
        return None

def get_company_summary(ticker, api_key):
    try:
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel('gemini-2.5-flash')
        
        biz_summary = ""
        try:
            biz_summary = yf.Ticker(ticker).info.get('longBusinessSummary', '')
        except: pass 
            
        if biz_summary:
            prompt = f"미국 주식 {ticker}의 영문 개요를 읽고, '무엇을 만들고 어떻게 돈을 버는지' 한국어로 2줄 요약해 주세요. [개요]: {biz_summary[:1500]}"
        else:
            prompt = f"미국 주식 티커 '{ticker}' 기업에 대해 아는 대로 '무엇을 만들고 어떻게 돈을 버는 기업인지' 핵심 비즈니스 모델을 한국어로 2~3줄로 요약해 주세요."
            
        response = model.generate_content(prompt)
        return response.text
    except Exception as e:
        return f"기업 정보를 요약하는 중 오류가 발생했습니다. (에러: {e})"

def analyze_news_with_gemini(ticker, api_key):
    try:
        genai.configure(api_key=api_key)
        news_list = []
        try:
            news_list = yf.Ticker(ticker).news
        except: pass
            
        if not news_list: return "최근 관련 뉴스를 찾을 수 없습니다."
        news_text = "\n".join([f"[{n.get('publisher')}] {n.get('title')}" for n in news_list[:3]])
        prompt = f"한국 주식 스윙 전문 애널리스트입니다. 미국 주식 '{ticker}' 영문 헤드라인을 바탕으로 한국 테마주에 미칠 영향을 분석하세요.\n{news_text}\n* 시장 센티먼트:\n* 재료 지속성:\n* 투자 코멘트:"
        return genai.GenerativeModel('gemini-2.5-flash').generate_content(prompt).text
    except Exception:
        return "뉴스 분석 중 오류가 발생했습니다."

def show_trading_guidelines():
    st.info("""
    **[매매 신호 및 타점 가이드]**
    * ✅ **타점 근접:** 주가가 20일선 근처에 위치 **(분할 매수 권장)**
    * ⚠️ **관심 집중:** 급등으로 인한 단기 이격 발생 **(눌림목 대기)**
    * 🛑 **추세 이탈:** 20일선 하향 이탈 **(손절 또는 접근 금지)**
    * 🎯 **1차 목표가:** 볼린저 밴드 상단 저항선 **(절반 수익 실현 권장)**
    """)

def draw_stock_card(tech_result, is_expanded=False):
    status_emoji = tech_result['상태'].split(' ')[0]
    
    with st.expander(f"{status_emoji} {tech_result['종목명']} (현재가: {tech_result['현재가']:,}원)", expanded=is_expanded):
        st.markdown(f"**진단 상태:** {tech_result['상태']} ｜ **수급 현황:** {tech_result['거래량 급증']}")
        
        c1, c2, c3 = st.columns(3)
        curr = tech_result['현재가']
        
        c1.metric("📌 진입 기준가", f"{tech_result['진입가_가이드']:,}원", f"{tech_result['진입가_가이드'] - curr:,}원 (현재가 대비)", delta_color="off")
        c2.metric("🎯 1차 목표가", f"{tech_result['목표가']:,}원", f"+{tech_result['목표가'] - curr:,}원 (기대 수익)")
        c3.metric("🛑 손절 라인", f"{tech_result['손절가']:,}원", f"{tech_result['손절가'] - curr:,}원 (리스크)", delta_color="normal")
        
        ch1, ch2 = st.columns(2)
        
        price_df = tech_result["종가 데이터"].reset_index()
        price_df.columns = ['Date', 'Price']
        price_df['Date_Str'] = price_df['Date'].dt.strftime('%m-%d')
        
        vol_df = tech_result["거래량 데이터"].reset_index()
        vol_df.columns = ['Date', 'Volume']
        vol_df['Date_Str'] = vol_df['Date'].dt.strftime('%m-%d')
        
        with ch1:
            st.caption("📈 주가 흐름 (최근 20일)")
            fig_price = px.line(price_df, x='Date_Str', y='Price', markers=True)
            fig_price.update_layout(
                margin=dict(l=0, r=0, t=10, b=0),
                xaxis_title="", yaxis_title="",
                yaxis_tickformat=",", 
                hovermode="x unified",
                xaxis=dict(showgrid=False, type='category'),
                yaxis=dict(showgrid=True, gridcolor='rgba(128,128,128,0.2)'),
                height=220
            )
            fig_price.update_traces(line_color="#FF4B4B", hovertemplate="<b>%{y:,}원</b>")
            st.plotly_chart(fig_price, use_container_width=True, config={'displayModeBar': False})
            
        with ch2:
            st.caption("📊 거래량 (최근 20일)")
            fig_vol = px.bar(vol_df, x='Date_Str', y='Volume')
            fig_vol.update_layout(
                margin=dict(l=0, r=0, t=10, b=0),
                xaxis_title="", yaxis_title="",
                yaxis_tickformat=",", 
                hovermode="x unified",
                xaxis=dict(showgrid=False, type='category'), 
                yaxis=dict(showgrid=True, gridcolor='rgba(128,128,128,0.2)'),
                height=220
            )
            fig_vol.update_traces(marker_color="#1f77b4", hovertemplate="<b>%{y:,}주</b>")
            st.plotly_chart(fig_vol, use_container_width=True, config={'displayModeBar': False})

# ==========================================
# 3. 사이드바 및 UI 화면 구성
# ==========================================
st.title("📈 Jaemini 스윙 트레이딩 대시보드")
st.markdown("단기 스윙 매매를 위한 **글로벌 주도주 분석** 및 **실시간 타점 모니터링** 시스템입니다.")

with st.sidebar:
    st.header("⚙️ 대시보드 컨트롤")
    fetch_button = st.button("🔄 증시 데이터 리로드", type="primary", use_container_width=True)
    st.divider()
    st.header("🧠 AI 엔진 연결 상태")
    if "GEMINI_API_KEY" in st.secrets:
        api_key_input = st.secrets["GEMINI_API_KEY"]
        st.success("✅ 시스템 연동 완료 (정상)")
    else:
        api_key_input = st.text_input("Gemini API Key를 입력하세요", type="password")

if fetch_button:
    get_us_top_gainers.clear()
    get_krx_stocks.clear()
    get_all_sector_info.clear()

if "gainers_df" not in st.session_state or fetch_button:
    with st.spinner('📡 글로벌 증시 데이터를 수집하는 중입니다...'):
        df, ex_rate = get_us_top_gainers()
        st.session_state.gainers_df = df
        st.session_state.ex_rate = ex_rate

tab1, tab2, tab3, tab4 = st.tabs(["🔥 🇺🇸 미국장 기반 테마 발굴", "🎯 국내 종목 정밀 진단", "💡 AI 테마/관련주 검색", "📰 실시간 금융 속보"])

# ------------------------------------------
# [탭 1]
# ------------------------------------------
with tab1:
    st.markdown("<br>", unsafe_allow_html=True)
    col1, col2 = st.columns([1, 1.2], gap="large")

    with col1:
        us_time = datetime.utcnow() - timedelta(hours=5) 
        st.subheader("🔥 미국장 폭등주 (+10% 이상)")
        st.caption(f"🗓️ **기준일:** {us_time.strftime('%Y-%m-%d')} (NYT) ｜ 💱 **적용 환율:** 1달러 = {int(st.session_state.get('ex_rate', 1350)):,}원")
        
        if not st.session_state.gainers_df.empty:
            tickers_list = st.session_state.gainers_df['종목코드'].tolist()
            
            # 💡 1. 표를 그리기 전에 AI 섹터 분석을 먼저 수행합니다.
            if api_key_input:
                with st.spinner("🤖 AI가 30개 종목의 섹터 정보를 일괄 분석 중입니다... (최초 1회 3초 소요)"):
                    sector_dict = get_all_sector_info(tuple(tickers_list), api_key_input)
            else:
                sector_dict = {t: ("분석 대기", "분석 대기") for t in tickers_list}
            
            # 💡 2. 표(Dataframe)에 들어갈 데이터 복사 후 기업명 수정
            display_df = st.session_state.gainers_df.copy()
            new_company_names = []
            
            PLACEHOLDER = "🔍 검색 종목을 선택해주세요."
            options = [PLACEHOLDER]
            
            for index, row in display_df.iterrows():
                t = row['종목코드']
                full_name = row['기업명']
                kor_name = full_name.split(' / ')[-1] if ' / ' in full_name else full_name
                sec, ind = sector_dict.get(t, ("분석 불가", "분석 불가"))
                
                # 표에 들어갈 이름: 회사명 (섹터 / 산업)
                table_name = f"{full_name} ({sec} / {ind})"
                new_company_names.append(table_name)
                
                # 드롭다운에 들어갈 이름
                options.append(f"{t} ({kor_name}) - ({sec} / {ind})")
                
            display_df['기업명'] = new_company_names
            
            # 💡 3. 수정한 데이터프레임(표) 출력! 이제 표 안에 섹터가 포함됩니다.
            st.dataframe(display_df, use_container_width=True, hide_index=True, height=400)
            
            # 💡 4. 드롭다운 선택창 출력
            st.markdown("#### 🔍 분석 대상 종목 선택")
            selected_option = st.selectbox("목록에서 주식을 선택하세요:", options, label_visibility="collapsed")
            
            if selected_option == PLACEHOLDER:
                selected_ticker = "N/A"
            else:
                selected_ticker = selected_option.split(" ")[0]
        else:
            selected_ticker = "N/A"
            st.info("현재 +10% 이상 급등한 종목이 없습니다.")

    with col2:
        st.subheader("🎯 연관 테마 매칭 및 타점 진단")
        show_trading_guidelines() 
        
        if selected_ticker != "N/A":
            sector, industry = sector_dict.get(selected_ticker, ("분석 불가", "분석 불가"))
            st.markdown(f"**🏷️ 섹터 정보:** `{sector}` / `{industry}`")

            if api_key_input:
                with st.spinner(f"🔍 '{selected_ticker}' 기업 정보 및 뉴스를 AI가 분석 중입니다..."):
                    with st.container(border=True):
                        st.markdown(f"**🏢 비즈니스 모델 요약 ({selected_ticker})**\n> {get_company_summary(selected_ticker, api_key_input)}")
                        st.markdown(f"**📰 AI 뉴스 판독**\n> {analyze_news_with_gemini(selected_ticker, api_key_input)}")
                
                with st.spinner('✨ AI가 연관된 한국 수혜주를 샅샅이 검색하고 타점을 계산 중입니다...'):
                    kor_stocks = get_ai_matched_stocks(selected_ticker, sector, industry, selected_option.split(" - ")[0], api_key_input)
                    if kor_stocks:
                        st.markdown("### ✨ AI 추천 국내 수혜주 (클릭하여 타점 확인)")
                        for stock_name, ticker_code in kor_stocks:
                            tech_result = analyze_technical_pattern(stock_name, ticker_code)
                            if tech_result: 
                                draw_stock_card(tech_result, is_expanded=False)
                    else:
                        st.error("❌ 연관된 국내 주식을 찾는 데 실패했습니다. 서버 연결 상태를 확인해 주세요.")
            else:
                st.warning("👈 좌측 사이드바에 API 키를 입력하시면 AI 분석이 시작됩니다.")

# ------------------------------------------
# [탭 2]
# ------------------------------------------
with tab2:
    st.markdown("<br>", unsafe_allow_html=True)
    st.subheader("🔍 국내 개별 종목 정밀 타점 진단기")
    st.write("관심 있는 국내 상장사를 검색하면 즉시 20일선 및 볼린저 밴드 기준 기술적 분석 타점을 계산합니다.")
    
    show_trading_guidelines() 
    
    krx_df = get_krx_stocks()
    if not krx_df.empty:
        krx_options = ["🔍 검색 종목을 선택해주세요."] + (krx_df['Name'] + " (" + krx_df['Code'] + ")").tolist()
        search_query = st.selectbox("👇 종목명 또는 초성을 입력하여 검색하세요:", krx_options)
        
        if search_query and search_query != "🔍 검색 종목을 선택해주세요.":
            searched_name = search_query.split(" (")[0]
            searched_code = search_query.split("(")[1].replace(")", "")
            
            with st.spinner(f"📡 증권사 서버에서 '{searched_name}' 과거 90일 치 데이터를 가져와 타점 분석 중입니다..."):
                tech_result = analyze_technical_pattern(searched_name, searched_code)
                
            if tech_result: 
                draw_stock_card(tech_result, is_expanded=True)
            else: 
                st.error("❌ 데이터를 불러올 수 없습니다. (신규 상장 등으로 20일 데이터가 부족할 수 있습니다)")
    else:
        st.error("❌ 국내 주식 목록을 불러오는 데 실패했습니다. 좌측 사이드바에서 [🔄 증시 데이터 리로드] 버튼을 눌러주세요.")

# ------------------------------------------
# [탭 3]
# ------------------------------------------
with tab3:
    st.markdown("<br>", unsafe_allow_html=True)
    st.subheader("💡 테마 및 관련주 실시간 AI 발굴기")
    st.write("검색할 테마/키워드 (예: `2차전지`, `엔비디아 관련주`)를 입력하세요. AI가 관련주를 찾아 즉시 타점을 진단합니다.")
    
    show_trading_guidelines() 
    
    theme_input = st.text_input("🔍 검색할 테마/키워드 입력:")
    
    if theme_input and api_key_input:
        with st.spinner(f"✨ AI가 증시 전체에서 '{theme_input}' 관련주를 발굴하고 타점을 진단하는 중입니다... (약 3~5초 소요)"):
            theme_stocks = get_theme_stocks_with_ai(theme_input, api_key_input)
            if theme_stocks:
                st.success(f"🎯 **'{theme_input}' 관련주 {len(theme_stocks)}개 발굴 및 진단 완료! (아래 종목을 클릭하세요)**")
                for stock_name, ticker_code in theme_stocks:
                    tech_result = analyze_technical_pattern(stock_name, ticker_code)
                    if tech_result: 
                        draw_stock_card(tech_result, is_expanded=False)
            else:
                st.error(f"❌ '{theme_input}' 테마에 대한 관련주를 찾지 못했거나 AI 응답 지연이 발생했습니다. 다시 시도해 주세요.")

# ------------------------------------------
# [탭 4]
# ------------------------------------------
with tab4:
    st.markdown("<br>", unsafe_allow_html=True)
    st.subheader("📰 실시간 금융 속보")
    with st.spinner('📡 네이버 금융 서버에서 최신 뉴스를 스캔하는 중입니다...'):
        fetch_news()
    if st.session_state.news_data:
        for news in st.session_state.news_data[:30]:
            with st.container(border=True):
                cols = st.columns([5, 1])
                cols[0].markdown(f"**🕒 {news['time']}** | {news['title']}")
                cols[1].link_button("원문 읽기 🔗", news['link'], use_container_width=True)
