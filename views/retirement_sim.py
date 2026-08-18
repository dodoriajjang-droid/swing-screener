# -*- coding: utf-8 -*-
"""👴 노후 준비 ETF 시뮬레이터 (v2.0)

app.py 라우팅에서 분리된 페이지. 함수 라이브러리는 core 에서 가져온다.
"""
from core import *


def render(ctx):
    _nav_changed = ctx['_nav_changed']
    api_key_input = ctx['api_key_input']

    st.markdown("## 👴 노후 준비 ETF 시뮬레이터")
    st.write("절세 계좌(연금저축/IRP/ISA) 활용법과 테마별 ETF 조합을 통해 은퇴 후 현금흐름을 설계합니다.")

    # --- 1. 절세 계좌 자동 배분 계산기 ---
    st.markdown("### 🎯 1. 월 투자금액별 절세 계좌 배분 최적화 가이드")
    
    st.info("""
    **💡 노후 자금은 왜 반드시 이 순서대로 계좌를 채워야 할까요? (절세 극대화 룰)**
    1. **1순위: 연금저축펀드 (연 600만 원 우선)** - 세액공제 및 수익률 극대화에 가장 유리합니다.
    2. **2순위: IRP (연 300만 원 추가)** - 연금저축과 합산해 총 900만 원까지 세액공제를 받습니다.
    3. **3순위: 중개형 ISA (연 2,000만 원 한도)** - 수익의 200~400만 원까지 비과세 혜택을 줍니다.
    4. **4순위: 일반/해외계좌** - 국가 절세 혜택을 소진한 뒤 남는 여유 현금을 굴리는 계좌입니다.
    """)

    with st.container(border=True):
        col_in, col_spacer = st.columns([2, 1])
        monthly_budget = col_in.number_input("월 총 노후대비 투자 가능 금액 (원)", min_value=0, step=100000, value=0)
        
        temp_budget = monthly_budget
        pension = min(500000, temp_budget) 
        temp_budget -= pension
        irp = min(250000, temp_budget)    
        temp_budget -= irp
        isa = min(1666666, temp_budget)   
        normal = max(0, temp_budget - isa)

        c1, c2, c3, c4 = st.columns(4)
        c1.metric("연금저축펀드", f"{int(pension):,}원", "연 600만 한도")
        c2.metric("IRP (퇴직연금)", f"{int(irp):,}원", "합산 900만 한도")
        c3.metric("중개형 ISA", f"{int(isa):,}원", "비과세 혜택")
        c4.metric("일반/해외계좌", f"{int(normal):,}원", "한도 초과분")

    # 👇 네이버 금융 실시간 API 직결 엔진
    @st.cache_data(ttl=3600)
    def get_naver_etf_and_stocks():
        res_dfs = []
        try:
            url = "https://finance.naver.com/api/sise/etfItemList.nhn"
            res = requests.get(url, timeout=5)
            if res.status_code == 200:
                etf_list = res.json().get('result', {}).get('etfItemList', [])
                if etf_list:
                    df_etf = pd.DataFrame(etf_list)[['itemcode', 'itemname', 'nowVal']].rename(
                        columns={'itemcode': 'Code', 'itemname': 'Name', 'nowVal': 'Price'})
                    res_dfs.append(df_etf)
        except Exception as _dg_e: _diag_note("get_naver_etf_and_stocks", _dg_e); pass
        try:
            df_stocks = fdr.StockListing('KRX')
            if not df_stocks.empty:
                df_s = df_stocks[['Code', 'Name', 'Close']].rename(columns={'Close': 'Price'}) if 'Close' in df_stocks.columns else df_stocks[['Code', 'Name']].assign(Price=0)
                res_dfs.append(df_s)
        except Exception as _dg_e: _diag_note("get_naver_etf_and_stocks", _dg_e); pass
        if res_dfs:
            df_final = pd.concat(res_dfs, ignore_index=True)
            df_final['Code'] = df_final['Code'].astype(str).str.zfill(6)
            df_final['Price'] = pd.to_numeric(df_final['Price'], errors='coerce').fillna(0)
            return df_final.sort_values('Price', ascending=False).drop_duplicates(subset=['Code']).reset_index(drop=True)
        return pd.DataFrame(columns=['Code', 'Name', 'Price'])

    # 고정 테마 대배열 명단 (맞춤 종목 메뉴 최하단 고정)
    theme_order = [
        "🌐 1. 시장 대표 지수 코어", 
        "💻 2. 반도체 & 빅테크 핵심 성장", 
        "🤖 3. AI·로봇 & 사이버보안 혁신",
        "🚀 4. 방산 & 우주항공 미래 테크",
        "🏦 5. 금융 지주 & 밸류업 모멘텀",
        "💰 6. 고배당 & 월배당 인컴 밸류업", 
        "🛡️ 7. 안전자산 채권 & 원자재 방어",
        "🌍 8. 해외 직상장 글로벌 메이저",
        "🚢 9. 조선 & 해운 슈퍼사이클",
        "⚡ 10. 전력 인프라 & 글로벌 에너지",
        "🔎 내가 추가한 맞춤 종목"
    ]

    # --- 2. 스마트 맞춤 종목 다중 검색 ---
    if 'custom_etfs' not in st.session_state or (len(st.session_state.custom_etfs) > 0 and isinstance(st.session_state.custom_etfs[0], str)):
        st.session_state.custom_etfs = []
    if 'search_query' not in st.session_state: st.session_state.search_query = ""

    st.markdown("### 🔎 2. 맞춤형 종목 검색 및 추가")
    with st.container(border=True):
        st.markdown("**✨ 원하는 종목을 직접 찾아 내 포트폴리오에 담아보세요.**")
        
        cols = st.columns([4, 1], vertical_alignment="bottom")
        with cols[0]:
            search_input = st.text_input(
                "검색어 입력", 
                placeholder=" 🔍 검색어를 입력하세요. (예: 반도체, 삼성전자, SCHD)", 
                label_visibility="collapsed"
            ).strip()
        with cols[1]:
            search_clicked = st.button("종목 검색", type="primary", use_container_width=True)

        if search_clicked:
            if search_input: st.session_state.search_query = search_input
            else: st.warning("⚠️ 검색어를 먼저 입력해주세요!")

        if st.session_state.search_query:
            query = st.session_state.search_query
            search_options = []
            with st.spinner("데이터베이스에서 종목을 찾는 중입니다..."):
                kr_assets_df = get_naver_etf_and_stocks()
                if not kr_assets_df.empty:
                    matches = kr_assets_df[kr_assets_df['Name'].str.contains(query, case=False, na=False)]
                    for _, row in matches.iterrows(): search_options.append(f"{row['Name']} [{row['Code']}]")
                if re.search('[a-zA-Z]', query):
                    try:
                        us_results = search_us_ticker(query)
                        if us_results:
                            for res in us_results:
                                search_options.append(f"{res.split(' (')[1].split(' /')[0]} [{res.split(' ')[0]}]")
                    except Exception as _dg_e: _diag_note("<module>", _dg_e); pass
            
            st.divider()
            if search_options:
                with st.form(key="add_stock_form", clear_on_submit=True):
                    st.success(f"🎉 '{query}' 검색 결과 총 **{len(search_options)}개**를 찾았습니다!")
                    selected_to_add = st.multiselect("👇 결과 목록에서 장바구니에 담을 종목을 모두 골라주세요:", options=search_options)
                    submit_btn = st.form_submit_button("🛒 선택한 종목 포트폴리오에 추가하기", use_container_width=True)
                    
                    if submit_btn:
                        if selected_to_add:
                            added_count = 0
                            for sel in selected_to_add:
                                parts = sel.split(" [")
                                parsed_name, parsed_code = parts[0].strip(), parts[1].replace("]", "").strip()
                                if not any(item['code'] == parsed_code for item in st.session_state.custom_etfs):
                                    # 👇 [핵심 조치 1] 다른 테마로 숨지 않도록 강제로 "🔎 내가 추가한 맞춤 종목" 메뉴로 배치
                                    st.session_state.custom_etfs.append({
                                        'theme': "🔎 내가 추가한 맞춤 종목", 
                                        'name': parsed_name, 
                                        'code': parsed_code, 
                                        'holdings': '관심 종목 (아래 버튼으로 편입종목을 확인하세요)'
                                    })
                                    added_count += 1
                            if added_count > 0: st.toast(f"✅ {added_count}개 종목 추가 완료!", icon="✅")
                            st.session_state.search_query = ""
                            st.rerun()
                        else: st.warning("⚠️ 추가할 종목을 위에서 먼저 선택해주세요.")
            else: st.error("앗! 검색 결과가 없습니다. 🥲")

    # 👇 고정 마스터 리스트 (6번 항목 미국 배당주 통합)
    raw_etf_data = [
        {"theme": "🌐 1. 시장 대표 지수 코어", "code": "069500", "name": "KODEX 200"},
        {"theme": "🌐 1. 시장 대표 지수 코어", "code": "102110", "name": "TIGER 200"},
        {"theme": "🌐 1. 시장 대표 지수 코어", "code": "229200", "name": "KODEX 코스닥150"},
        {"theme": "🌐 1. 시장 대표 지수 코어", "code": "360750", "name": "TIGER 미국S&P500"},
        {"theme": "🌐 1. 시장 대표 지수 코어", "code": "360200", "name": "ACE 미국S&P500"},
        {"theme": "🌐 1. 시장 대표 지수 코어", "code": "379780", "name": "RISE 미국S&P500"},
        {"theme": "🌐 1. 시장 대표 지수 코어", "code": "379800", "name": "KODEX 미국S&P500"},
        {"theme": "🌐 1. 시장 대표 지수 코어", "code": "133690", "name": "TIGER 미국나스닥100"},
        {"theme": "🌐 1. 시장 대표 지수 코어", "code": "379810", "name": "KODEX 미국나스닥100"},
        {"theme": "🌐 1. 시장 대표 지수 코어", "code": "453810", "name": "KODEX 인도Nifty50"},
        {"theme": "🌐 1. 시장 대표 지수 코어", "code": "241180", "name": "TIGER 일본니케이225"},

        {"theme": "💻 2. 반도체 & 빅테크 핵심 성장", "code": "381170", "name": "TIGER 미국테크TOP10 INDXX"},
        {"theme": "💻 2. 반도체 & 빅테크 핵심 성장", "code": "381180", "name": "TIGER 미국필라델피아반도체나스닥"},
        {"theme": "💻 2. 반도체 & 빅테크 핵심 성장", "code": "446770", "name": "ACE 글로벌반도체TOP4 Plus"},
        {"theme": "💻 2. 반도체 & 빅테크 핵심 성장", "code": "091160", "name": "KODEX 반도체"},
        {"theme": "💻 2. 반도체 & 빅테크 핵심 성장", "code": "091230", "name": "TIGER 반도체"},
        {"theme": "💻 2. 반도체 & 빅테크 핵심 성장", "code": "455850", "name": "SOL AI반도체소부장"},
        {"theme": "💻 2. 반도체 & 빅테크 핵심 성장", "code": "305720", "name": "KODEX 2차전지산업"},
        {"theme": "💻 2. 반도체 & 빅테크 핵심 성장", "code": "305540", "name": "TIGER 2차전지테마"},

        {"theme": "🤖 3. AI·로봇 & 사이버보안 혁신", "code": "456600", "name": "TIME 글로벌AI인공지능액티브"},
        {"theme": "🤖 3. AI·로봇 & 사이버보안 혁신", "code": "445290", "name": "KODEX 로봇액티브"},
        {"theme": "🤖 3. AI·로봇 & 사이버보안 혁신", "code": "464310", "name": "TIGER 글로벌AI&로보틱스 INDXX"},
        {"theme": "🤖 3. AI·로봇 & 사이버보안 혁신", "code": "469070", "name": "RISE AI&로봇"},
        {"theme": "🤖 3. AI·로봇 & 사이버보안 혁신", "code": "418670", "name": "TIGER 글로벌AI사이버보안"},
        {"theme": "🤖 3. AI·로봇 & 사이버보안 혁신", "code": "276990", "name": "KODEX 글로벌로봇(합성)"},
        {"theme": "🤖 3. AI·로봇 & 사이버보안 혁신", "code": "275980", "name": "TIGER 글로벌4차산업혁신기술(합성 H)"},

        {"theme": "🚀 4. 방산 & 우주항공 미래 테크", "code": "449450", "name": "PLUS K방산"},
        {"theme": "🚀 4. 방산 & 우주항공 미래 테크", "code": "463250", "name": "TIGER K방산&우주"},
        {"theme": "🚀 4. 방산 & 우주항공 미래 테크", "code": "421320", "name": "PLUS 우주항공"},
        {"theme": "🚀 4. 방산 & 우주항공 미래 테크", "code": "440910", "name": "WON 미국우주항공방산"},

        {"theme": "🏦 5. 금융 지주 & 밸류업 모멘텀", "code": "466940", "name": "TIGER 은행고배당플러스TOP10"},
        {"theme": "🏦 5. 금융 지주 & 밸류업 모멘텀", "code": "484880", "name": "SOL 금융지주플러스고배당"},
        {"theme": "🏦 5. 금융 지주 & 밸류업 모멘텀", "code": "091170", "name": "KODEX 은행"},
        {"theme": "🏦 5. 금융 지주 & 밸류업 모멘텀", "code": "495050", "name": "RISE 코리아밸류업"},
        {"theme": "🏦 5. 금융 지주 & 밸류업 모멘텀", "code": "495850", "name": "KODEX 코리아밸류업"},
        {"theme": "🏦 5. 금융 지주 & 밸류업 모멘텀", "code": "496080", "name": "TIGER 코리아밸류업"},
        {"theme": "🏦 5. 금융 지주 & 밸류업 모멘텀", "code": "138540", "name": "TIGER 현대차그룹플러스"},
        {"theme": "🏦 5. 금융 지주 & 밸류업 모멘텀", "code": "447430", "name": "ACE 주주환원가치주액티브"},
        {"theme": "🏦 5. 금융 지주 & 밸류업 모멘텀", "code": "157500", "name": "TIGER 증권"},

        {"theme": "💰 6. 고배당 & 월배당 인컴 밸류업", "code": "458730", "name": "TIGER 미국배당다우존스"},
        {"theme": "💰 6. 고배당 & 월배당 인컴 밸류업", "code": "489250", "name": "KODEX 미국배당다우존스"},
        {"theme": "💰 6. 고배당 & 월배당 인컴 밸류업", "code": "446720", "name": "SOL 미국배당다우존스"},
        {"theme": "💰 6. 고배당 & 월배당 인컴 밸류업", "code": "210780", "name": "TIGER 코스피고배당"},
        {"theme": "💰 6. 고배당 & 월배당 인컴 밸류업", "code": "279530", "name": "KODEX 고배당주"},
        {"theme": "💰 6. 고배당 & 월배당 인컴 밸류업", "code": "458760", "name": "TIGER 미국배당다우존스타겟커버드콜2호"},
        {"theme": "💰 6. 고배당 & 월배당 인컴 밸류업", "code": "SCHD", "name": "Schwab US Dividend Equity ETF"},
        {"theme": "💰 6. 고배당 & 월배당 인컴 밸류업", "code": "JEPI", "name": "JPMorgan Equity Premium Income ETF"},
        {"theme": "💰 6. 고배당 & 월배당 인컴 밸류업", "code": "JEPQ", "name": "JPMorgan Nasdaq Equity Premium Income ETF"},
        {"theme": "💰 6. 고배당 & 월배당 인컴 밸류업", "code": "O", "name": "Realty Income Corp"},
        {"theme": "💰 6. 고배당 & 월배당 인컴 밸류업", "code": "MAIN", "name": "Main Street Capital"},
        {"theme": "💰 6. 고배당 & 월배당 인컴 밸류업", "code": "VIG", "name": "Vanguard Dividend Appreciation ETF"},
        {"theme": "💰 6. 고배당 & 월배당 인컴 밸류업", "code": "VYM", "name": "Vanguard High Dividend Yield ETF"},
        {"theme": "💰 6. 고배당 & 월배당 인컴 밸류업", "code": "DGRW", "name": "WisdomTree US Quality Dividend Growth"},
        {"theme": "💰 6. 고배당 & 월배당 인컴 밸류업", "code": "SDY", "name": "SPDR S&P Dividend ETF"},
        {"theme": "💰 6. 고배당 & 월배당 인컴 밸류업", "code": "MO", "name": "Altria Group Inc"},
        {"theme": "💰 6. 고배당 & 월배당 인컴 밸류업", "code": "PM", "name": "Philip Morris International"},
        {"theme": "💰 6. 고배당 & 월배당 인컴 밸류업", "code": "VZ", "name": "Verizon Communications"},
        {"theme": "💰 6. 고배당 & 월배당 인컴 밸류업", "code": "T", "name": "AT&T Inc"},
        {"theme": "💰 6. 고배당 & 월배당 인컴 밸류업", "code": "CVX", "name": "Chevron Corp"},
        {"theme": "💰 6. 고배당 & 월배당 인컴 밸류업", "code": "XOM", "name": "Exxon Mobil Corp"},
        {"theme": "💰 6. 고배당 & 월배당 인컴 밸류업", "code": "PEP", "name": "PepsiCo Inc"},
        {"theme": "💰 6. 고배당 & 월배당 인컴 밸류업", "code": "KO", "name": "Coca-Cola Co"},
        {"theme": "💰 6. 고배당 & 월배당 인컴 밸류업", "code": "PG", "name": "Procter & Gamble Co"},
        {"theme": "💰 6. 고배당 & 월배당 인컴 밸류업", "code": "ABBV", "name": "AbbVie Inc"},
        {"theme": "💰 6. 고배당 & 월배당 인컴 밸류업", "code": "PFE", "name": "Pfizer Inc"},
        {"theme": "💰 6. 고배당 & 월배당 인컴 밸류업", "code": "MMM", "name": "3M Co"},
        {"theme": "💰 6. 고배당 & 월배당 인컴 밸류업", "code": "IBM", "name": "International Business Machines"},
        {"theme": "💰 6. 고배당 & 월배당 인컴 밸류업", "code": "HD", "name": "Home Depot Inc"},
        {"theme": "💰 6. 고배당 & 월배당 인컴 밸류업", "code": "LOW", "name": "Lowe's Companies Inc"},
        {"theme": "💰 6. 고배당 & 월배당 인컴 밸류업", "code": "CSCO", "name": "Cisco Systems Inc"},
        {"theme": "💰 6. 고배당 & 월배당 인컴 밸류업", "code": "TLT", "name": "iShares 20+ Year Treasury Bond ETF"},
        {"theme": "💰 6. 고배당 & 월배당 인컴 밸류업", "code": "DIVO", "name": "Amplify CWP Strategic Focus Equity ETF"},
        {"theme": "💰 6. 고배당 & 월배당 인컴 밸류업", "code": "STAG", "name": "STAG Industrial Inc"},
        {"theme": "💰 6. 고배당 & 월배당 인컴 밸류업", "code": "VICI", "name": "VICI Properties Inc"},
        {"theme": "💰 6. 고배당 & 월배당 인컴 밸류업", "code": "ADC", "name": "Agree Realty Corp"},

        {"theme": "🛡️ 7. 안전자산 채권 & 원자재 방어", "code": "273130", "name": "KODEX 종합채권(AA-이상)액티브"},
        {"theme": "🛡️ 7. 안전자산 채권 & 원자재 방어", "code": "423160", "name": "KODEX KOFR금리액티브(합성)"},
        {"theme": "🛡️ 7. 안전자산 채권 & 원자재 방어", "code": "411060", "name": "ACE KRX금현물"},
        {"theme": "🛡️ 7. 안전자산 채권 & 원자재 방어", "code": "132030", "name": "KODEX 골드선물(H)"},
        {"theme": "🛡️ 7. 안전자산 채권 & 원자재 방어", "code": "160580", "name": "TIGER 구리실물"},
        {"theme": "🛡️ 7. 안전자산 채권 & 원자재 방어", "code": "153130", "name": "KODEX 단기채권"},

        {"theme": "🌍 8. 해외 직상장 글로벌 메이저", "code": "SPY", "name": "SPDR S&P 500"},
        {"theme": "🌍 8. 해외 직상장 글로벌 메이저", "code": "VOO", "name": "Vanguard S&P 500"},
        {"theme": "🌍 8. 해외 직상장 글로벌 메이저", "code": "QQQ", "name": "Invesco QQQ"},
        {"theme": "🌍 8. 해외 직상장 글로벌 메이저", "code": "SOXX", "name": "iShares Semiconductor"},

        {"theme": "🚢 9. 조선 & 해운 슈퍼사이클", "code": "494670", "name": "TIGER 조선TOP10"},
        {"theme": "🚢 9. 조선 & 해운 슈퍼사이클", "code": "441540", "name": "HANARO Fn조선해운"},
        {"theme": "🚢 9. 조선 & 해운 슈퍼사이클", "code": "466920", "name": "SOL 조선TOP3플러스"},

        {"theme": "⚡ 10. 전력 인프라 & 글로벌 에너지", "code": "139250", "name": "TIGER 200 에너지화학"},
        {"theme": "⚡ 10. 전력 인프라 & 글로벌 에너지", "code": "117460", "name": "KODEX 에너지화학"},
        {"theme": "⚡ 10. 전력 인프라 & 글로벌 에너지", "code": "442320", "name": "RISE 글로벌원자력"},
        {"theme": "⚡ 10. 전력 인프라 & 글로벌 에너지", "code": "419650", "name": "PLUS 글로벌수소&차세대연료전지"},
        {"theme": "⚡ 10. 전력 인프라 & 글로벌 에너지", "code": "385510", "name": "KODEX 신재생에너지액티브"},
        {"theme": "⚡ 10. 전력 인프라 & 글로벌 에너지", "code": "XLU", "name": "Utilities Select Sector SPDR"},
        {"theme": "⚡ 10. 전력 인프라 & 글로벌 에너지", "code": "ICLN", "name": "iShares Global Clean Energy"}
    ]

    # 공식 명칭 동기화 및 덮어쓰기
    @st.cache_data(ttl=86400)
    def update_official_names(items):
        try:
            krx_df = get_naver_etf_and_stocks()
            krx_name_map = dict(zip(krx_df['Code'], krx_df['Name'])) if not krx_df.empty else {}
            us_tickers = [it['code'] for it in items if not (len(str(it['code'])) == 6 and any(char.isdigit() for char in str(it['code'])))]
            us_name_map = {}
            import yfinance as yf
            import concurrent.futures
            def get_us_name(ticker):
                try:
                    info = yf.Ticker(ticker).info
                    return ticker, info.get('longName', info.get('shortName', ticker))
                except Exception as _dg_e: _diag_note("get_us_name", _dg_e); return ticker, ticker
            if us_tickers:
                with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
                    for code, name in executor.map(get_us_name, us_tickers): us_name_map[code] = name
            updated_items = []
            for it in items:
                new_it = it.copy()
                code = str(it['code']).zfill(6) if str(it['code']).isdigit() else str(it['code'])
                is_kr = len(code) == 6 and code.isdigit()
                if is_kr and code in krx_name_map: new_it['name'] = krx_name_map[code]
                elif not is_kr and code in us_name_map and us_name_map[code] != code: new_it['name'] = us_name_map[code]
                new_it['code'] = code
                updated_items.append(new_it)
            return updated_items
        except Exception as _dg_e: _diag_note("update_official_names", _dg_e); return items 

    # 순서 중요: 코드 보정(이름 기준) → 이름 동기화(코드 기준).
    # 이름을 먼저 잘못된 코드의 정식 명칭으로 덮어쓰면 코드를 교정할 단서가 사라진다.
    etf_data = resolve_etf_codes(raw_etf_data, get_naver_etf_and_stocks())
    etf_data = update_official_names(etf_data)
    for item in etf_data:
        item.update({"price": 0, "cagr": "데이터없음", "list_date": "데이터없음", "holdings": "해당 테마 핵심 우량종목 (아래 버튼으로 검색 가능)"})

    # 사용자가 직접 추가한 종목도 리스트에 이식
    for custom_item in st.session_state.custom_etfs:
        if not any(item['code'] == custom_item['code'] for item in etf_data):
            etf_data.append({
                "theme": "🔎 내가 추가한 맞춤 종목",  # 무조건 고정
                "name": custom_item['name'], 
                "code": custom_item['code'], 
                "price": 0, 
                "cagr": "데이터없음", 
                "list_date": "데이터없음", 
                "holdings": "관심 종목 (아래 버튼으로 편입종목 검색 가능)"
            })

    # 👇 실시간 가격 및 백데이터 로딩 엔진
    import yfinance as yf
    import concurrent.futures
    @st.cache_data(ttl=3600)
    def fetch_realtime_data(codes, ex_rate):
        prices, cagrs = {}, {}
        kr_codes = [c for c in codes if len(str(c)) == 6 and any(char.isdigit() for char in str(c))]
        us_codes = [c for c in codes if c not in kr_codes]
        
        # 1) 국내 실시간 가격
        bulk_krx = get_naver_etf_and_stocks()
        if not bulk_krx.empty:
            p_dict = dict(zip(bulk_krx['Code'], bulk_krx['Price']))
            for c in kr_codes:
                if c in p_dict and int(p_dict[c]) > 0: prices[c] = int(p_dict[c])

        # 1-B) [0원 방어] 일괄 조회에서 누락(0원)된 국내 종목만 개별 보강
        def get_kr_price_fallback(c):
            # (a) 네이버 차트 API의 가장 최근 종가를 현재가로 사용
            try:
                url = f"https://fchart.stock.naver.com/sise.nhn?symbol={c}&timeframe=day&count=5&requestType=0"
                res = requests.get(url, headers={'User-Agent': 'Mozilla/5.0'}, timeout=5)
                if res.status_code == 200:
                    soup = BeautifulSoup(res.text, 'html.parser')
                    items = soup.find_all('item')
                    if items:
                        last_close = float(items[-1].get('data').split('|')[4])
                        if last_close > 0:
                            return c, int(last_close)
            except Exception as _dg_e: _diag_note("get_kr_price_fallback", _dg_e); pass
            # (b) FinanceDataReader 최근 종가로 2차 보강
            try:
                df = fdr.DataReader(c)
                if not df.empty:
                    last_close = float(df['Close'].iloc[-1])
                    if last_close > 0:
                        return c, int(last_close)
            except Exception as _dg_e: _diag_note("get_kr_price_fallback", _dg_e); pass
            return c, 0

        missing_kr = [c for c in kr_codes if prices.get(c, 0) == 0]
        if missing_kr:
            with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
                for c, p in executor.map(get_kr_price_fallback, missing_kr):
                    if p > 0: prices[c] = p

        # 2) 국내 백데이터
        def get_kr_historical_info(c):
            try:
                url = f"https://fchart.stock.naver.com/sise.nhn?symbol={c}&timeframe=month&count=1200&requestType=0"
                res = requests.get(url, headers={'User-Agent': 'Mozilla/5.0'}, timeout=5)
                if res.status_code == 200:
                    soup = BeautifulSoup(res.text, 'html.parser')
                    items = soup.find_all('item')
                    if len(items) > 12:
                        first_date, last_date = items[0].get('data').split('|')[0], items[-1].get('data').split('|')[0]
                        p_start, p_end = float(items[0].get('data').split('|')[4]), float(items[-1].get('data').split('|')[4])
                        days = (pd.to_datetime(last_date) - pd.to_datetime(first_date)).days
                        if days >= 365 and p_start > 0:
                            cagr = ((p_end / p_start) ** (365.25 / days) - 1) * 100
                            return c, round(cagr, 2), pd.to_datetime(first_date).strftime('%Y-%m-%d')
            except Exception as _dg_e: _diag_note("get_kr_historical_info", _dg_e); pass
            try:
                df = fdr.DataReader(c)
                if len(df) > 250:
                    p_start, p_end = float(df['Close'].iloc[0]), float(df['Close'].iloc[-1])
                    days = (df.index[-1] - df.index[0]).days
                    if days >= 365 and p_start > 0:
                        cagr = ((p_end / p_start) ** (365.25 / days) - 1) * 100
                        return c, round(cagr, 2), df.index[0].strftime('%Y-%m-%d')
            except Exception as _dg_e: _diag_note("get_kr_historical_info", _dg_e); pass
            return c, 0.0, "데이터없음"

        if kr_codes:
            with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
                for c, cg, dt in executor.map(get_kr_historical_info, kr_codes):
                    if dt != "데이터없음": cagrs[c] = {'cagr': cg, 'date': dt}

        # 3) 미국 실시간 가격 및 백데이터
        def get_us_info(c):
            try:
                hist = yf.Ticker(c).history(period="max", interval="1mo")
                if not hist.empty:
                    p = float(hist['Close'].iloc[-1])
                    p_start = float(hist['Close'].iloc[0])
                    days = (hist.index[-1] - hist.index[0]).days
                    cagr = ((p / p_start) ** (365.25 / days) - 1) * 100 if days > 365 else 0
                    return c, int(p * ex_rate), round(cagr, 2), hist.index[0].strftime('%Y-%m-%d')
            except Exception as _dg_e: _diag_note("get_us_info", _dg_e); pass
            return c, 0, 0, "데이터없음"

        if us_codes:
            with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
                for c, p, cg, dt in executor.map(get_us_info, us_codes):
                    if p > 0: prices[c] = p
                    if cg != 0: cagrs[c] = {'cagr': cg, 'date': dt}
        return prices, cagrs

    with st.spinner("최신 마켓 데이터를 전수 매칭하는 중입니다..."):
        ex_rate = st.session_state.get('ex_rate', 1350.0)
        real_prices, real_cagrs = fetch_realtime_data([item['code'] for item in etf_data], ex_rate)
        for item in etf_data:
            if item['code'] in real_prices: item['price'] = real_prices[item['code']]
            if item['code'] in real_cagrs:
                item['cagr'], item['list_date'] = real_cagrs[item['code']]['cagr'], real_cagrs[item['code']]['date']

    # --- 3. 포트폴리오 구성 UI ---
    st.markdown("### 🛒 3. 나만의 노후 포트폴리오 담기")
    if 'retirement_cart' not in st.session_state: st.session_state.retirement_cart = {}

    for theme in theme_order:
        theme_stocks = [item for item in etf_data if item['theme'] == theme]
        seen = set()
        unique_stocks = [s for s in theme_stocks if s['code'] not in seen and not seen.add(s['code'])]

        if unique_stocks:
            with st.expander(f"{theme} 선택", expanded=False):
                for idx, stock in enumerate(unique_stocks):
                    cols = st.columns([3, 1.5, 1.5, 1.5, 1.5, 1]) 
                    
                    with cols[0]: 
                        st.markdown(f"**{stock['name']}** ({stock['code']})")
                        
                        # 👇 [핵심 조치 2] 제한 없이 "모든 종목"에 대해 AI 편입종목 검색 기능 제공
                        current_holdings = st.session_state.get(f"holdings_{stock['code']}", stock['holdings'])
                        st.caption(f"🔍 {current_holdings}")
                        
                        if "💡 AI" not in current_holdings:
                            if st.button("🤖 편입종목 검색", key=f"ai_h_{stock['code']}_{idx}"):
                                if not api_key_input:
                                    st.error("좌측 사이드바에 API 키를 입력해주세요.")
                                else:
                                    with st.spinner("AI가 편입 종목을 분석 중입니다..."):
                                        ai_prompt = f"주식/ETF '{stock['name']} ({stock['code']})'가 가장 많이 편입하고 있는 핵심 종목 5~10개를 쉼표로 나열해줘. 다른 말은 하지 마."
                                        ai_holdings = ask_gemini(ai_prompt, api_key_input)
                                        st.session_state[f"holdings_{stock['code']}"] = "💡 AI 분석: " + ai_holdings
                                        st.rerun()

                    cols[1].markdown(f"현재가:<br>{stock['price']:,}원", unsafe_allow_html=True)
                    cols[2].markdown(f"상장일:<br>{stock.get('list_date', '데이터없음')}", unsafe_allow_html=True)
                    c_val = stock['cagr']
                    cols[3].markdown(f"수익률:<br>{c_val}%" if isinstance(c_val, (int, float)) else f"수익률:<br>{c_val}", unsafe_allow_html=True)
                    
                    qty = cols[4].number_input("수량", min_value=0, step=1, key=f"ret_qty_{theme}_{stock['code']}_{idx}", label_visibility="collapsed")
                    if qty > 0: st.session_state.retirement_cart[stock['code']] = {"name": stock['name'], "qty": qty, "price": stock['price'], "cagr": stock['cagr'] if isinstance(stock['cagr'], (int, float)) else 0}
                    elif stock['code'] in st.session_state.retirement_cart: del st.session_state.retirement_cart[stock['code']]
                    
                    # 맞춤 종목만 삭제 버튼 활성화
                    is_custom = any(c['code'] == stock['code'] for c in st.session_state.custom_etfs)
                    if is_custom:
                        if cols[5].button("🗑️ 삭제", key=f"del_{theme}_{stock['code']}_{idx}"):
                            st.session_state.custom_etfs = [x for x in st.session_state.custom_etfs if x['code'] != stock['code']]
                            if stock['code'] in st.session_state.retirement_cart: del st.session_state.retirement_cart[stock['code']]
                            st.rerun()

    # --- 4. 시뮬레이션 대시보드 ---
    st.divider()
    st.markdown("### 📊 4. 복리 성장 & 노후 현금흐름 시뮬레이션")
    cart = st.session_state.retirement_cart
    if cart:
        total_p = sum(v['qty'] * v['price'] for v in cart.values())
        w_cagr = sum(v['qty'] * v['price'] * v['cagr'] for v in cart.values()) / total_p if total_p > 0 else 0

        # 투자 방식 / 기간 / 월 적립금 입력
        opt1, opt2, opt3 = st.columns([1.3, 1, 1])
        invest_mode = opt1.radio("투자 방식", ["💰 거치식 (목돈 한 번)", "📅 적립식 (매달 추가)"], horizontal=False)
        yrs = opt2.select_slider("투자기간 (년)", options=[1, 3, 5, 10, 15, 20, 25, 30], value=20)
        default_monthly = int(monthly_budget) if 'monthly_budget' in dir() and monthly_budget else 0
        monthly_add = opt3.number_input("매달 추가 투자금 (원)", min_value=0, step=100000, value=default_monthly,
                                        help="위 1번에서 입력한 월 투자금이 기본값으로 들어옵니다. 적립식일 때 사용됩니다.")

        r = w_cagr / 100.0
        is_install = invest_mode.startswith("📅")
        # 미래가치 계산
        fv_lump = total_p * ((1 + r) ** yrs)
        if is_install and monthly_add > 0:
            r_m = r / 12.0
            n = yrs * 12
            fv_series = monthly_add * ((((1 + r_m) ** n) - 1) / r_m) if r_m != 0 else monthly_add * n
            fv = fv_lump + fv_series
            total_invested = total_p + monthly_add * n
        else:
            fv = fv_lump
            total_invested = total_p

        inflation = 0.025  # 연 2.5% 물가 가정
        real_fv = fv / ((1 + inflation) ** yrs)
        monthly_pension = fv * 0.04 / 12  # 4% 인출 룰 → 월 연금
        profit = fv - total_invested

        # 핵심 지표 4종
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("총 투자 원금", f"{int(total_invested):,}원",
                  f"수익 +{int(profit):,}원" if profit >= 0 else f"{int(profit):,}원", delta_color="normal")
        m2.metric(f"{yrs}년 후 예상 자산", f"{int(fv):,}원")
        m3.metric("실질가치 (오늘 돈 기준)", f"{int(real_fv):,}원", help="연 2.5% 물가상승률을 반영한 현재가치")
        m4.metric("은퇴 후 예상 월 연금", f"{int(monthly_pension):,}원", help="4% 인출 룰 기준 (자산의 연 4%를 매년 인출)")

        st.caption(f"📈 가중평균 수익률(CAGR) **{w_cagr:.2f}%** 가정 · "
                   f"{'매달 ' + format(monthly_add, ',') + '원씩 ' + str(yrs) + '년 적립' if is_install and monthly_add > 0 else '목돈 거치 ' + str(yrs) + '년'}")

        # 자산 성장 차트 (투입 원금 vs 평가액)
        years, inv_list, val_list = [], [], []
        for y in range(yrs + 1):
            lump_y = total_p * ((1 + r) ** y)
            if is_install and monthly_add > 0:
                r_m = r / 12.0; n_y = y * 12
                ser_y = monthly_add * ((((1 + r_m) ** n_y) - 1) / r_m) if r_m != 0 else monthly_add * n_y
                val_y = lump_y + ser_y
                inv_y = total_p + monthly_add * n_y
            else:
                val_y = lump_y
                inv_y = total_p
            years.append(y); inv_list.append(float(inv_y)); val_list.append(float(val_y))
        # 연차를 숫자 x축으로 두어 정렬을 보장하고(문자열 정렬 시 0,10,11,…,1,20,2 로 꼬임)
        # 눈금 라벨만 'N년'으로 표시
        fig_growth = go.Figure()
        fig_growth.add_trace(go.Scatter(
            x=years, y=val_list, name="평가액", mode="lines",
            line=dict(color="#93c5fd", width=1.5), fill="tozeroy",
            fillcolor="rgba(147,197,253,0.45)",
            hovertemplate="%{x}년<br>평가액 %{y:,.0f}원<extra></extra>"))
        fig_growth.add_trace(go.Scatter(
            x=years, y=inv_list, name="투입 원금", mode="lines",
            line=dict(color="#3b82f6", width=1.5), fill="tozeroy",
            fillcolor="rgba(59,130,246,0.55)",
            hovertemplate="%{x}년<br>투입 원금 %{y:,.0f}원<extra></extra>"))
        fig_growth.update_layout(
            height=380, margin=dict(l=10, r=10, t=10, b=10),
            hovermode="x unified",
            legend=dict(orientation="h", yanchor="bottom", y=1.02, x=0),
            xaxis=dict(tickmode="array", tickvals=years,
                       ticktext=[f"{y}년" for y in years], title=None),
            yaxis=dict(title=None, tickformat=","),
        )
        st.plotly_chart(fig_growth, use_container_width=True)

        # 포트폴리오 비중 (막대) + 명세서
        pf_col1, pf_col2 = st.columns([1, 1])
        with pf_col1:
            st.markdown("#### 🥧 포트폴리오 비중")
            wdf = pd.DataFrame([{"종목": v['name'], "비중": round(v['qty'] * v['price'] / total_p * 100, 1)}
                                for v in cart.values()]).sort_values("비중", ascending=False)
            wdf_show = wdf.set_index("종목")
            try:
                sty_w = wdf_show.style.format({"비중": "{:.1f}%"}).bar(subset=["비중"], color="#ffd8a8", vmin=0)
                st.dataframe(sty_w, use_container_width=True, height=300)
            except Exception:
                st.dataframe(wdf_show, use_container_width=True)
            if len(wdf) >= 1 and wdf.iloc[0]["비중"] >= 50:
                st.caption(f"⚠️ '{wdf.iloc[0]['종목']}' 비중이 {wdf.iloc[0]['비중']}%로 높아요. 분산을 권장합니다.")
        with pf_col2:
            st.markdown("#### 📝 내 포트폴리오 명세서")
            st.dataframe(pd.DataFrame([{'종목명': v['name'], '수량': f"{v['qty']}주",
                                        '현재가': f"{v['price']:,}원", '총액': f"{v['qty'] * v['price']:,}원",
                                        '연수익률': f"{v['cagr']}%"} for v in cart.values()]),
                         use_container_width=True, hide_index=True, height=300)
        st.caption("※ '데이터없음' 종목은 계산 안전을 위해 수익률 0%로 보수 적용 ｜ 4% 룰·물가 2.5%는 가정치이며 실제와 다를 수 있습니다.")

        st.markdown("---")
        if st.button("🤖 AI 노후 포트폴리오 정밀 진단 (클릭)", type="primary", use_container_width=True):
            if not api_key_input:
                st.error("사이드바에 API 키를 먼저 입력해주세요.")
            else:
                with st.spinner("AI가 은퇴 설계 전문가의 관점으로 포트폴리오를 분석 중입니다..."):
                    port_str = "".join([f"- {v['name']}: 비중 {(v['qty'] * v['price'] / total_p) * 100:.1f}%, 총액 {v['qty'] * v['price']:,}원\n" for v in cart.values()])
                    ai_prompt = (f"은퇴 설계 전문가로서 다음 포트폴리오를 진단해 주세요.\n"
                                 f"투자 방식: {'적립식(매달 ' + format(monthly_add, ',') + '원)' if is_install else '거치식'}\n"
                                 f"총 투자원금: {int(total_invested):,}원\n예상 CAGR: {w_cagr:.2f}%\n투자기간: {yrs}년\n"
                                 f"{yrs}년 후 예상자산(명목): {int(fv):,}원, 은퇴 후 월 연금(4%룰): {int(monthly_pension):,}원\n{port_str}\n"
                                 f"1.분산/리스크 진단 2.개선 제안 3.이 월 연금으로 노후가 충분한지 평가, 순으로 작성하세요.")
                    st.success("✅ 진단 완료!")
                    st.markdown(ask_gemini(ai_prompt, api_key_input))
    else:
        st.info("💡 위 리스트에서 수량을 입력하시면 시뮬레이션이 즉시 시작됩니다.")

    # 0원 검출기를 화면 맨 하단으로 깔끔하게 이동 배치
    st.divider()
    st.markdown("### 🚨 시스템 상태 분석기")
    def _prc_zeroerr():
        errs = [it for it in etf_data if it.get('price', 0) == 0]
        if errs:
            st.error(f"현재 총 {len(errs)}개 종목의 데이터 수집이 지연되고 있습니다.")
            st.table(pd.DataFrame([{'테마': i['theme'], '종목': i['name'], '코드': i['code']} for i in errs]))
        else: 
            st.success("🎉 현재 시스템상 가격이 0원으로 조회되는 오류 종목이 단 하나도 없습니다! (무결점 상태)")
    _register_popup("zeroerr", _prc_zeroerr)
    _popup_button("⚠️ 데이터 통신 지연 종목 확인 (0원 에러 검출기)", "zeroerr", "⚠️ 0원 에러 검출기", key="btn_zeroerr")
