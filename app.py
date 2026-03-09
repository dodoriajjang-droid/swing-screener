import streamlit as st
import pandas as pd
import requests
from io import StringIO
import yfinance as yf
import FinanceDataReader as fdr
from datetime import datetime, timedelta
import google.generativeai as genai

# ==========================================
# 1. 데이터 수집 및 매칭 로직
# ==========================================
@st.cache_data(ttl=3600)
def get_us_top_gainers(top_n=15):
    try:
        url = 'https://finance.yahoo.com/gainers'
        headers = {'User-Agent': 'Mozilla/5.0'}
        response = requests.get(url, headers=headers)
        tables = pd.read_html(StringIO(response.text))
        gainers_df = tables[0].iloc[:, :6].head(top_n)
        return gainers_df
    except Exception as e:
        st.error(f"데이터 수집 중 오류 발생: {e}")
        return pd.DataFrame()

korea_theme_mapping = {
    # 1. 반도체 (종합 반도체 및 기존 설계/생산)
    "Semiconductors": [("SK하이닉스", "000660"), ("삼성전자", "005930"), ("리노공업", "058470"), ("ISC", "095340"), ("DB하이텍", "000990")],
    
    # 🌟 신규 추가: 반도체 소부장 (장비 및 소재 대장주)
    "Semiconductor Equipment & Materials": [("한미반도체", "042700"), ("HPSP", "403870"), ("이오테크닉스", "039200"), ("주성엔지니어링", "036930"), ("원익IPS", "240810"), ("동진쎄미켐", "005290"), ("솔브레인", "357780"), ("티씨케이", "064760"), ("하나마이크론", "067310"), ("피에스케이", "319660")],
    
    # 🌟 신규 추가: IT/전자 부품 (기판, 카메라, 적층세라믹콘덴서 등)
    "Electronic Components": [("삼성전기", "009150"), ("LG이노텍", "011070"), ("이수페타시스", "007660"), ("심텍", "222800"), ("대덕전자", "353200"), ("비에이치", "090460"), ("해성디에스", "195870"), ("아비코전자", "036010")],
    
    # 🌟 신규 추가: 2차전지 소재 및 특수 화학 (양극재, 전해액 등 배터리 소부장)
    "Specialty Chemicals": [("에코프로비엠", "247540"), ("포스코퓨처엠", "003670"), ("에코프로", "086520"), ("엘앤에프", "066970"), ("엔켐", "348370"), ("코스모신소재", "005070"), ("나노신소재", "121600"), ("대주전자재료", "078600"), ("천보", "278280")],
    # 2. 대형 기술주 및 IT 서비스 (클라우드, DX, 플랫폼)
    "Technology": [("네이버", "035420"), ("카카오", "035720"), ("삼성SDS", "018260"), ("현대오토에버", "307950"), ("포스코DX", "022100"), ("롯데정보통신", "286940"), ("다우기술", "023590"), ("카페24", "042000")],
    
    # 3. 소프트웨어 및 IT 인프라 (보안, B2B 솔루션 우량주)
    "Software - Infrastructure": [("아이티센글로벌", "124500"), ("더존비즈온", "012510"), ("엠로", "058970"), ("파수", "150900"), ("안랩", "053800"), ("지니언스", "263860"), ("이스트소프트", "047560"), ("엑스게이트", "356680"), ("파이오링크", "170790")],
    
    # 4. 인공지능 (의료AI, 문서AI 등 실제 매출 발생 유망주)
    "Artificial Intelligence": [("루닛", "328130"), ("크라우드웍스", "355390"), ("한글과컴퓨터", "030520"), ("폴라리스오피스", "041020"), ("솔트룩스", "304100"), ("뷰노", "338220"), ("제이엘케이", "322510"), ("코난테크놀로지", "402030")],
    
    # 5. 전력 인프라 및 신재생 (AI 데이터센터 슈퍼 사이클 수혜주)
    "Utilities - Renewable": [("HD현대일렉트릭", "267260"), ("LS ELECTRIC", "010120"), ("두산에너빌리티", "034020"), ("효성중공업", "298040"), ("제룡전기", "033100"), ("일진전기", "103590"), ("가온전선", "000500"), ("씨에스윈드", "112610")],
    
    # 6. 에너지 및 조선 (유가 및 LNG 인프라 우량주)
    "Energy": [("S-Oil", "010950"), ("SK이노베이션", "096770"), ("HD현대마린솔루션", "443060"), ("한국가스공사", "036460"), ("포스코인터내셔널", "047050"), ("GS", "078930"), ("HD현대중공업", "329180"), ("삼성중공업", "010140")],
    "Oil & Gas Drilling": [("HD현대중공업", "329180"), ("삼성중공업", "010140"), ("한화오션", "042660"), ("한국가스공사", "036460"), ("포스코인터내셔널", "047050"), ("HD현대마린솔루션", "443060")],
    
    # 7. 헬스케어 및 바이오 (글로벌 빅파마 수출 및 실적주)
    "Healthcare": [("삼성바이오로직스", "207940"), ("셀트리온", "068270"), ("유한양행", "000100"), ("한미약품", "128940"), ("종근당", "185750"), ("휴젤", "145020"), ("파마리서치", "214450"), ("클래시스", "214150")],
    "Biotechnology": [("알테오젠", "196170"), ("HLB", "028300"), ("리가켐바이오", "141080"), ("삼천당제약", "000250"), ("에이비엘바이오", "298380"), ("펩트론", "087010"), ("보로노이", "310210")],
    
    # 8. 산업재 및 기계 (수출 주도 방산 및 건설기계)
    "Industrials": [("한화에어로스페이스", "012450"), ("LIG넥스원", "079550"), ("현대로템", "064350"), ("한국항공우주", "047810"), ("HD현대건설기계", "267270"), ("두산밥캣", "241560"), ("LS", "006260"), ("효성첨단소재", "298050")],
    
    # 9. 소비재 및 소재 (💡 효성티앤씨 및 글로벌 K-뷰티/의류 추가)
    "Consumer Cyclical": [("효성티앤씨", "298020"), ("호텔신라", "008770"), ("파라다이스", "034230"), ("코스맥스", "192820"), ("아모레퍼시픽", "090430"), ("영원무역", "111110"), ("F&F", "383220"), ("실리콘투", "257720")],
    "Basic Materials": [("효성티앤씨", "298020"), ("LG화학", "051910"), ("포스코홀딩스", "005490"), ("금호석유", "011780"), ("롯데케미칼", "011170")],
    
    # 10. 통신 및 미디어/광고 (현금흐름 우수)
    "Communication Services": [("KT", "030200"), ("SK텔레콤", "017670"), ("LG유플러스", "032640"), ("서진시스템", "253010"), ("쏠리드", "050890"), ("제일기획", "030000"), ("에코마케팅", "236200"), ("나스미디어", "089600")],
    
    # 11. 자동차 및 부품 (글로벌 경쟁력 우량주)
    "Auto Manufacturers": [("현대차", "005380"), ("기아", "000270"), ("현대모비스", "012330"), ("HL만도", "204320"), ("현대위아", "011210"), ("서연이화", "200880"), ("성우하이텍", "015750"), ("화신", "010690")],
    
    # 12. 금융 (주주환원 우수 대형 금융주)
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

# ==========================================
# 2. 기술적 분석 (거래량 데이터 추가)
# ==========================================
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
            status = "🟢 타점 근접 (분할 매수 고려)"
        elif current_price > (ma20_price * 1.03):
            status = "🟡 관심 집중 (단기 급등, 눌림목 대기)"
        else:
            status = "🔴 추세 이탈 (관망/손절 구간)"
            
        return {
            "종목명": stock_name,
            "현재가": int(current_price),
            "상태": status,
            "진입가_가이드": int(ma20_price),
            "목표가": int(target_price),
            "손절가": int(stop_loss_price),
            "최근_거래량": int(latest['Volume']), # 💡 거래량 수치 추가
            "거래량 급증": "🔥 거래량 터짐" if is_volume_spike else "평이함",
            "종가 데이터": df['Close'].tail(20),
            "거래량 데이터": df['Volume'].tail(20) # 💡 거래량 차트용 데이터 추가
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
            
        prompt = f"""
        미국 주식 {name}({ticker})의 영문 기업 개요를 읽고, 
        이 회사가 도대체 '무엇을 만들고 어떻게 돈을 버는 기업인지' 한국어로 딱 2줄로 요약해 주세요.
        [영문 개요]: {biz_summary[:1500]}
        """
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
            
        prompt = f"""
        당신은 한국 주식 시장에서 단기 스윙 투자를 전문으로 하는 애널리스트입니다.
        미국 주식 '{ticker}'에 대한 최근 영문 뉴스 헤드라인입니다.
        이 이슈가 동조화되는 한국 관련 테마주에 미칠 영향을 분석해 주세요.
        [최신 뉴스 헤드라인]
        {news_text}
        
        아래 3가지 항목만 간결하게 한국어로 답변해 주세요.
        * **시장 센티먼트:** (강력 호재 / 약한 호재 / 중립 / 악재 중 택 1)
        * **재료의 지속성 예상:** (단발성 / 1주일 내외 / 1개월 이상 중 택 1)
        * **스윙 투자 코멘트:** (이 뉴스가 한국 관련 섹터에 줄 영향을 2~3줄로 요약)
        """
        model = genai.GenerativeModel('gemini-2.5-flash')
        response = model.generate_content(prompt)
        return response.text
    except Exception as e:
        return "뉴스 분석 중 오류가 발생했습니다."

# ==========================================
# 3. 웹 대시보드 화면 구성
# ==========================================
st.set_page_config(page_title="단기 스윙 주식 검색기", layout="wide")
st.title("📈 1주~2개월 단기 스윙 주식 검색기")

with st.sidebar:
    st.header("⚙️ 설정")
    top_n = st.slider("수집할 미국 급등주 개수", 5, 20, 20)
    fetch_button = st.button("데이터 업데이트 🔄", type="primary")
    
    st.divider()
    st.header("🧠 AI 뉴스 분석 설정")
    api_key_input = st.text_input("Gemini API Key를 입력하세요", type="password")

col1, col2 = st.columns([1, 1.2])

if "gainers_df" not in st.session_state or fetch_button:
    with st.spinner('미국장 데이터를 불러오는 중입니다...'):
        st.session_state.gainers_df = get_us_top_gainers(top_n)

with col1:
    st.subheader("🔥 미국장 급등 종목")
    if not st.session_state.gainers_df.empty:
        st.dataframe(st.session_state.gainers_df, use_container_width=True, hide_index=True)
        
        tickers_list = st.session_state.gainers_df['Symbol'].tolist()
        
        options = []
        with st.spinner("테마/섹터 정보를 불러오는 중입니다... (최초 1회 약 5초 소요)"):
            for t in tickers_list:
                sec, ind, _ = get_sector_info(t)
                options.append(f"{t} - ({sec} / {ind})")
                
        selected_option = st.selectbox("👉 분석할 미국 주식 테마를 선택하세요:", options)
        selected_ticker = selected_option.split(" - ")[0]
    else:
        selected_ticker = "N/A"

with col2:
    st.subheader("🎯 테마 매칭 및 타점 분석")
    if selected_ticker != "N/A":
        sector, industry, kor_stocks = get_sector_info(selected_ticker)
        st.write(f"- **분석 종목 티커:** {selected_ticker} ({sector} / {industry})")
        
        if api_key_input:
            with st.spinner('기업 정보를 한국어로 번역 및 요약 중입니다...'):
                company_desc = get_company_summary(selected_ticker, api_key_input)
                st.success(f"🏢 **어떤 기업인가요?**\n\n{company_desc}")
        else:
            st.info("👈 좌측 사이드바에 API 키를 넣으시면 어떤 기업인지 한글 요약을 볼 수 있습니다.")
        
        st.divider()
        st.subheader("🧠 Gemini 최신 뉴스 센티먼트 판독")
        
        if api_key_input:
            with st.spinner('최신 뉴스를 가져와 AI가 분석 중입니다...'):
                ai_analysis_result = analyze_news_with_gemini(selected_ticker, api_key_input)
                st.info(ai_analysis_result)
        
        st.divider()
        
        if not kor_stocks:
            st.warning(f"⚠️ `korea_theme_mapping`에 '{sector}' 또는 '{industry}' 관련 국내 주식을 추가해 주세요!")
        else:
            st.write("👇 **매칭된 국내 주식의 현재 기술적 위치 및 매매 가이드라인**")
            for stock_name, ticker_code in kor_stocks:
                tech_result = analyze_technical_pattern(stock_name, ticker_code)
                if tech_result:
                    status_emoji = tech_result['상태'].split(' ')[0]
                    with st.expander(f"{status_emoji} {stock_name} (현재가: {tech_result['현재가']:,}원)", expanded=True):
                        st.markdown(f"**진단 상태:** {tech_result['상태']}")
                        
                        p_col1, p_col2, p_col3 = st.columns(3)
                        p_col1.metric("💡 진입 기준가 (20일선)", f"{tech_result['진입가_가이드']:,}원")
                        p_col2.metric("🎯 1차 목표가 (볼린저 상단)", f"{tech_result['목표가']:,}원")
                        p_col3.metric("🛑 기계적 손절가", f"{tech_result['손절가']:,}원")
                        
                        st.divider()
                        
                        # 💡 신규: 실제 거래량 수치 및 상태 표시
                        st.metric("수급 분석 (최근 거래량)", f"{tech_result['최근_거래량']:,}주", tech_result["거래량 급증"])
                        
                        # 💡 신규: 주가 차트와 거래량 막대그래프를 나란히 배치
                        chart_col1, chart_col2 = st.columns(2)
                        with chart_col1:
                            st.caption("📈 최근 20일 주가 흐름 (Line Chart)")
                            st.line_chart(tech_result["종가 데이터"], height=150)
                        with chart_col2:
                            st.caption("📊 최근 20일 거래량 (Bar Chart)")
                            st.bar_chart(tech_result["거래량 데이터"], height=150)