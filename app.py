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
def get_us_top_gainers(top_n=20):
    try:
        url = 'https://finance.yahoo.com/gainers'
        headers = {'User-Agent': 'Mozilla/5.0'}
        response = requests.get(url, headers=headers)
        tables = pd.read_html(StringIO(response.text))
        df = tables[0]
        
        df = df.loc[:, ~df.columns.str.contains('^Unnamed')]
        df = df.iloc[:, :6].head(top_n)
        
        df.columns = ['종목코드', '기업명', '현재가', '등락금액', '등락률', '거래량']
        
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
        
        # 💡 개선: 서버 위치와 상관없이 완벽한 한국 시간(UTC+9) 계산
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
        st.error(f"뉴스 크롤링 에러 발생: {e}")
        return 0

korea_theme_mapping = {
    "Semiconductors": [("SK하이닉스", "000660"), ("삼성전자", "005930"), ("리노공업", "058470"), ("ISC", "095340"), ("DB하이텍", "000990")],
    "Semiconductor Equipment & Materials": [("한미반도체", "042700"), ("HPSP", "403870"), ("이오테크닉스", "039200"), ("주성엔지니어링", "036930"), ("원익IPS", "240810"), ("동진쎄미켐", "005290"), ("솔브레인", "357780"), ("티씨케이", "064760"), ("하나마이크론", "067310"), ("피에스케이", "319660")],
    "Electronic Components": [("삼성전기", "009150"), ("LG이노텍", "011070"), ("이수페타시스", "007660"), ("심텍", "222800"), ("대덕전자", "353200"), ("비에이치", "090460"), ("해성디에스", "195870"), ("아비코전자", "036010")],
    "Specialty Chemicals": [("에코프로비엠", "247540"), ("포스코퓨처엠", "003670"), ("에코프로", "086520"), ("엘앤에프", "066970"), ("엔켐", "348370"), ("코스모신소재", "005070"), ("나노신소재", "121600"), ("대주전자재료", "078600"), ("천보", "278280")],
    "Technology": [("네이버", "035420"), ("카카오", "035720"), ("삼성SDS", "018260"), ("현대오토에버", "307950"), ("포스코DX", "022100"), ("롯데정보통신", "286940"), ("다우기술", "023590"), ("카페24", "042000")],
    "Software - Infrastructure": [("아이티센글로벌", "124500"), ("더존비즈온", "012510"), ("엠로", "058970"), ("파수", "150900"), ("안랩", "053800"), ("지니언스", "263860"), ("이스트소프트", "047560"), ("엑스게이트", "356680"), ("파이오링크", "170790")],
    "Artificial Intelligence": [("루닛", "328130"), ("크라우드웍스", "355390"), ("한글과컴퓨터", "030520"), ("폴라리스오피스", "041020"), ("솔트룩스", "304100"), ("뷰노", "338220"), ("제이엘케이", "322510"), ("코난테크놀로지", "402030")],
    "Utilities - Renewable": [("HD현대일렉트릭", "267260"), ("LS ELECTRIC", "010120"), ("두산에너빌리티", "034020"), ("효성중공업", "298040"), ("제룡전기", "033100"), ("일진전기", "103590"), ("가온전선", "000500"), ("씨에스윈드", "112610")],
    "Energy": [("S-Oil", "010950"), ("SK이노베이션", "096770"), ("HD현대마린솔루션", "443060"), ("한국가스공사", "036460"), ("포스코인터내셔널", "047050"), ("GS", "078930"), ("HD현대중공업", "329180"), ("삼성중공업", "010140")],
    "Oil & Gas Drilling": [("HD현대중공업", "329180"), ("삼성중공업", "010140"), ("한화오션", "042660"), ("한국가스공사", "036460"), ("포스코인터내셔널", "047050"), ("HD현대마린솔루션", "443060")],
    "Healthcare": [("삼성바이오로직스", "207940"), ("셀트리온", "068270"), ("유한양행", "000100"), ("한미약품", "128940"), ("종근당", "185750"), ("휴젤", "145020"), ("파마리서치", "214450"), ("클래시스", "214150")],
    "Biotechnology": [("알테오젠", "196170"), ("HLB", "028300"), ("리가켐바이오", "141080"), ("삼천당제약", "000250"), ("에이비엘바이오", "298380"), ("펩트론", "087010"), ("보로노이", "310210")],
    "Industrials": [("한화에어로스페이스", "012450"), ("LIG넥스원", "079550"), ("현대로템", "064350"), ("한국항공우주", "047810"), ("HD현대건설기계", "267270"), ("두산밥캣", "241560"), ("LS", "006260"), ("효성첨단소재", "298050")],
    "Consumer Cyclical": [("효성티앤씨", "298020"), ("호텔신라", "008770"), ("파라다이스", "034230"), ("코스맥스", "192820"), ("아모레퍼시픽", "090430"), ("영원무역", "111110"), ("F&F", "383220"), ("실리콘투", "257720")],
    "Basic Materials": [("효성티앤씨", "298020"), ("LG화학", "051910"), ("포스코홀딩스", "005490"), ("금호석유", "011780"), ("롯데케미칼", "011170")],
    "Communication Services": [("KT", "030200"), ("SK텔레콤", "017670"), ("LG유플러스", "032640"), ("서진시스템", "253010"), ("쏠리드", "050890"), ("제일기획", "030000"), ("에코마케팅", "236200"), ("나스미디어", "089600")],
    "Auto Manufacturers": [("현대차", "005380"), ("기아", "000270"), ("현대모비스", "012330"), ("HL만도", "204320"), ("현대위아", "011210"), ("서연이화", "200880"), ("성우하이텍", "015750"), ("화신", "010690")],
    "Financials": [("KB금융", "105560"), ("신한지주", "055550"), ("하나금융지주", "086790"), ("메리츠금융지주", "138040"), ("삼성생명", "032830"), ("삼성화재", "000810"), ("키움증권", "039490"), ("한국금융지주", "071050")]
}

@st.cache_data(ttl=3600)
def get_sector_info(ticker):
    try:
        stock = yf.Ticker(ticker)
        sector = stock.info.get('sector', 'Unknown')
        industry = stock.info.get('industry', 'Unknown')
        matched_stocks = korea_theme_mapping.get(industry) or korea_theme_mapping.get(sector, [])
        return sector, industry, matched_stocks
    except:
        return "Unknown", "Unknown", []

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
    top_n = st.slider("수집할 미국 급등주 개수", 5, 50, 20)
    fetch_button = st.button("데이터 업데이트 🔄", type="primary")
    st.divider()
    st.header("🧠 AI 뉴스 분석 설정")
    api_key_input = st.text_input("Gemini API Key를 입력하세요", type="password")

if "gainers_df" not in st.session_state or fetch_button:
    with st.spinner('미국장 데이터를 불러오고 번역 중입니다...'):
        df, ex_rate = get_us_top_gainers(top_n)
        st.session_state.gainers_df = df
        st.session_state.ex_rate = ex_rate

tab1, tab2 = st.tabs(["🇺🇸 미국 주도주 스윙 검색기", "📰 한국 시장 실시간 속보"])

# ------------------------------------------
# [탭 1] 기존 미국장 기반 스윙 검색기
# ------------------------------------------
with tab1:
    col1, col2 = st.columns([1, 1.2])

    with col1:
        # 💡 개선: 서버 위치 상관없이 미국 시간(EST)을 항상 정확하게 가져오도록 UTC 기준으로 -5시간 처리
        us_time = datetime.utcnow() - timedelta(hours=5) 
        us_date_str = us_time.strftime("%Y-%m-%d")
        
        st.subheader("🔥 미국장 급등 종목")
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
                    sec, ind, _ = get_sector_info(t)
                    options.append(f"{t} ({kor_name}) - ({sec} / {ind})")
                    
            selected_option = st.selectbox("👉 분석할 미국 주식 테마를 선택하세요:", options)
            selected_ticker = selected_option.split(" (")[0]
        else:
            selected_ticker = "N/A"

    with col2:
        st.subheader("🎯 테마 매칭 및 타점 분석")
        st.info("**[매매 신호 상태 안내]**\n* ✅ **타점 근접:** 분할 매수하기 좋은 20일선 근처\n* ⚠️ **관심 집중:** 급등 후 이격 발생 (눌림목 대기)\n* 🛑 **추세 이탈:** 20일선 하향 이탈 (손절/관망)")
        
        if selected_ticker != "N/A":
            sector, industry, kor_stocks = get_sector_info(selected_ticker)
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
            
            if not kor_stocks:
                st.warning(f"⚠️ 매핑된 국내 주식이 없습니다.")
            else:
                st.write("👇 **매칭된 국내 주식의 현재 기술적 위치**")
                for stock_name, ticker_code in kor_stocks:
                    tech_result = analyze_technical_pattern(stock_name, ticker_code)
                    if tech_result:
                        status_emoji = tech_result['상태'].split(' ')[0]
                        with st.expander(f"{status_emoji} {stock_name} (현재가: {tech_result['현재가']:,}원)", expanded=False):
                            st.markdown(f"**진단 상태:** {tech_result['상태']}")
                            p_col1, p_col2, p_col3 = st.columns(3)
                            p_col1.metric("💡 진입 기준가", f"{tech_result['진입가_가이드']:,}원")
                            p_col2.metric("🎯 1차 목표가", f"{tech_result['목표가']:,}원")
                            p_col3.metric("🛑 손절가", f"{tech_result['손절가']:,}원")
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
# [탭 2] 실시간 금융 뉴스 탭
# ------------------------------------------
with tab2:
    st.subheader("📰 네이버 금융 실시간 시황/전망 속보")
    # 💡 개선: 탭 2의 전체 시간도 완벽한 한국 시간(KST)으로 표기
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
