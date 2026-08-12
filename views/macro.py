# -*- coding: utf-8 -*-
"""🌍 글로벌 매크로 & AI 분석 (v6.0)

app.py 라우팅에서 분리된 페이지. 함수 라이브러리는 core 에서 가져온다.
"""
from core import *


def render(ctx):
    _nav_changed = ctx['_nav_changed']
    api_key_input = ctx['api_key_input']

    st.markdown("## 🌍 글로벌 매크로 & AI 분석 (v6.0)")
    st.write("기관 프랍 트레이더 수준의 거시경제 분석, AI 어닝 리포트 해독, 포트폴리오 최적화 등 하이엔드 기능을 제공합니다.")
    v6_t1, v6_t2, v6_t3, v6_t4, v6_t5 = st.tabs(["🌍 1. 글로벌 매크로 관제소", "💼 2. 스마트머니 & 밸류업 추적", "🧠 3. AI PDF 리포트 해독", "🏆 4. 마코위츠 포트폴리오 최적화", "⚡ 5. 체결강도 & 틱(Tick) 분석"])
    
    with v6_t1:
        st.markdown("### 🌍 글로벌 매크로 & 지정학적 리스크 관제소 (The All-Seeing Eye)")
        if st.button("📊 실시간 글로벌 매크로 데이터 연동", type="primary"):
            with st.spinner("Yahoo Finance에서 원자재 및 국채 금리 데이터를 수집 중입니다..."):
                try:
                    tickers = {"금 (Gold)": "GC=F", "은 (Silver)": "SI=F", "구리 (닥터 코퍼)": "HG=F", "비트코인 (BTC)": "BTC-USD"}
                    series_dict = {}
                    # 순차 yf.Ticker 호출 → yf.download 배치 1회 (4종목 동시 수집)
                    _macro_dl = yf.download(list(tickers.values()), period="6mo",
                                            group_by="ticker", threads=True, progress=False)
                    for name, ticker in tickers.items():
                        try:
                            df_hist = _macro_dl[ticker].dropna(how="all") if len(tickers) > 1 else _macro_dl
                        except Exception as _dg_e:
                            _diag_note("<module>", _dg_e)
                            continue
                        if not df_hist.empty:
                            # yf.download 일봉은 tz-naive로 올 수 있어 tz_localize 전에 방어
                            if getattr(df_hist.index, "tz", None) is not None:
                                df_hist.index = df_hist.index.tz_localize(None)
                            df_hist.index = df_hist.index.normalize()
                            close = df_hist['Close'].dropna()
                            if close.empty:
                                continue
                            normalized = (close / close.iloc[0] - 1) * 100
                            normalized = normalized[~normalized.index.duplicated(keep='first')]
                            series_dict[name] = normalized
                    if series_dict:
                        macro_df = pd.DataFrame(series_dict).ffill().dropna()
                        st.markdown("#### 🥇 원자재 & 암호화폐 슈퍼사이클 트래커 (6개월 상대수익률 %)")
                        fig_macro = px.line(macro_df, x=macro_df.index, y=macro_df.columns)
                        fig_macro.update_layout(height=400, yaxis_title="수익률 (%)", xaxis_title="날짜", hovermode="x unified")
                        st.plotly_chart(fig_macro, use_container_width=True)
                    
                    # 순차 yf.Ticker 2회 → yf.download 배치 1회 (^TNX, ^IRX 동시 수집)
                    _yc_dl = yf.download(["^TNX", "^IRX"], period="6mo",
                                         group_by="ticker", threads=True, progress=False)
                    try:
                        df_10y = _yc_dl["^TNX"].dropna(how="all")
                        df_2y = _yc_dl["^IRX"].dropna(how="all")
                    except Exception:
                        df_10y, df_2y = pd.DataFrame(), pd.DataFrame()
                    if not df_10y.empty and not df_2y.empty:
                        for _d in (df_10y, df_2y):
                            if getattr(_d.index, "tz", None) is not None:
                                _d.index = _d.index.tz_localize(None)
                            _d.index = _d.index.normalize()
                        df_spread = (df_10y['Close'] - df_2y['Close']).dropna()
                        st.markdown("#### 📉 미국채 10년-2년 장단기 금리차 (Yield Curve Spread)")
                        fig_spread = go.Figure()
                        fig_spread.add_trace(go.Scatter(x=df_spread.index, y=df_spread.values, mode='lines', name='10Y-2Y Spread', line=dict(color='purple', width=2)))
                        fig_spread.add_hline(y=0, line_dash="dash", line_color="red", annotation_text="금리 역전 기준선")
                        fig_spread.update_layout(height=300, yaxis_title="금리차 (%)", xaxis_title="날짜")
                        st.plotly_chart(fig_spread, use_container_width=True)
                        
                        current_spread = df_spread.iloc[-1]
                        if current_spread < 0: st.error(f"🚨 **현재 장단기 금리차: {current_spread:.2f}%** (금리 역전 상태 - 잠재적 경기침체 경고)")
                        else: st.success(f"✅ **현재 장단기 금리차: {current_spread:.2f}%** (정상 커브)")
                        
                    if api_key_input:
                        st.divider()
                        prompt = f"당신은 수석 이코노미스트입니다. 현재 장단기 금리차가 {df_spread.iloc[-1] if not df_spread.empty else '알수없음'}%이고, 금, 은, 구리, 비트코인 차트를 보았을 때 현재 시장이 '인플레이션 베팅'인지 '경기침체 우려'인지 3줄로 명확하게 판단해주세요."
                        st.info("💡 **AI 매크로 종합 해석:**\n" + ask_gemini(prompt, api_key_input))
                except Exception as e: st.error(f"매크로 데이터 수집 중 오류 발생: {e}")

    with v6_t2:
        st.markdown("### 💼 스마트머니 딥(Deep) 트래커: 밸류업 & 파생 수급")
        sub_t1, sub_t2 = st.tabs(["🔥 옵션 Put/Call 비율 (US)", "🚀 한국 밸류업 스캐너 (KR)"])
        with sub_t1:
            pc_ticker = st.text_input("분석할 미국 티커 (예: AAPL, NVDA)", value="NVDA").upper()
            if st.button("⚖️ Put/Call 비율 연산"):
                with st.spinner("옵션 체인 데이터 수집 중..."):
                    try:
                        tk = yf.Ticker(pc_ticker)
                        expirations = tk.options
                        if not expirations: st.error("해당 종목의 옵션 데이터가 없습니다.")
                        else:
                            opt = tk.option_chain(expirations[0])
                            call_vol = opt.calls['volume'].sum()
                            put_vol = opt.puts['volume'].sum()
                            if call_vol > 0: pc_ratio = put_vol / call_vol
                            c1, c2, c3 = st.columns(3)
                            c1.metric("총 Call 거래량", f"{int(call_vol):,}")
                            c2.metric("총 Put 거래량", f"{int(put_vol):,}")
                            c3.metric("Put/Call Ratio", f"{pc_ratio:.2f}", "1.0 초과 시 약세 심리", delta_color="inverse" if pc_ratio > 1 else "normal")
                            fig_pc = px.pie(values=[call_vol, put_vol], names=['Call (상승 기대)', 'Put (하락 기대)'], hole=0.5, color_discrete_sequence=['#2ca02c', '#d62728'])
                            st.plotly_chart(fig_pc, use_container_width=True)
                    except Exception as e: st.error(f"옵션 연산 실패: {e}")
        with sub_t2:
            if st.button("🚀 밸류업(Value-up) 잠재주 스캔"):
                with st.spinner("재무제표 및 수익성 스크리닝 중..."):
                    candidates = get_longterm_value_stocks_with_ai("PBR 0.8 이하이면서 ROE 10% 이상인 주주환원 유력 후보", "코스피/코스닥 대형주", api_key_input)
                    if candidates:
                        st.success(f"🎯 AI 밸류업 잠재 기업 포착")
                        for name, code in candidates:
                            res = analyze_technical_pattern(name, code)
                            if res: draw_stock_card(res, api_key_str=api_key_input, is_expanded=False, key_suffix=f"vup_{code}")
                    else: st.error("후보를 찾지 못했습니다.")

    with v6_t3:
        st.markdown("### 🧠 AI 어닝콜 & 공시 원문(PDF) 딥리딩 룸")
        if not HAS_PYPDF: st.warning("⚠️ PyPDF2 모듈이 없습니다. 텍스트를 직접 복사해서 넣어주세요.")
        pdf_file = st.file_uploader("📄 PDF 리포트 업로드", type=["pdf"])
        raw_text = ""
        if pdf_file and HAS_PYPDF:
            with st.spinner("PDF 텍스트 추출 중..."):
                pdf_reader = PyPDF2.PdfReader(pdf_file)
                for page in pdf_reader.pages: raw_text += page.extract_text() + "\n"
        elif not HAS_PYPDF: raw_text = st.text_area("📄 텍스트 직접 붙여넣기:", height=150)
        if raw_text and api_key_input:
            if st.button("🤖 Gemini 리포트 해독 시작", type="primary"):
                with st.spinner("AI 분석 중..."):
                    prompt = f"당신은 리서치 애널리스트입니다. 다음 원문에서 1)목표주가 2)핵심투자포인트 3가지 3)리스크 2가지를 요약해주세요.\n\n{raw_text[:15000]}"
                    st.info(ask_gemini(prompt, api_key_input))

    with v6_t4:
        st.markdown("### 🏆 노벨상 수상 알고리즘: '마코위츠' 포트폴리오 최적화 엔진")
        port_input_m = st.text_input("포트폴리오 종목 (예: AAPL, MSFT, TSLA)", value="AAPL, MSFT, GOOGL, NVDA, TSLA")
        if st.button("⚙️ 몬테카를로 시뮬레이션 (1,000번 반복)", type="primary"):
            tickers_m = [t.strip() for t in port_input_m.split(",") if t.strip()]
            if len(tickers_m) >= 2:
                with st.spinner("최적 가중치 연산 중..."):
                    try:
                        # 순차 yf.Ticker 호출 → yf.download 배치 1회 (컬럼 순서=tickers_m 보존, 라벨 일치 보장)
                        data_m = pd.DataFrame()
                        try:
                            _dl = yf.download(tickers_m, period="1y", threads=True, progress=False)["Close"]
                            if isinstance(_dl, pd.Series):
                                _dl = _dl.to_frame(tickers_m[0])
                            for t in tickers_m:
                                if t in _dl.columns and not _dl[t].dropna().empty:
                                    data_m[t] = _dl[t]
                        except Exception as _dg_e:
                            _diag_note("<module>", _dg_e)
                            pass
                        data_m = data_m.dropna()
                        if not data_m.empty:
                            returns = data_m.pct_change().dropna()
                            mean_returns = returns.mean() * 252
                            cov_matrix = returns.cov() * 252
                            num_portfolios = 1000
                            results_m = np.zeros((3, num_portfolios))
                            weights_record = []
                            for i in range(num_portfolios):
                                weights = np.random.random(len(tickers_m))
                                weights /= np.sum(weights)
                                weights_record.append(weights)
                                portfolio_return = np.sum(mean_returns * weights)
                                portfolio_std_dev = np.sqrt(np.dot(weights.T, np.dot(cov_matrix, weights)))
                                results_m[0,i] = portfolio_return
                                results_m[1,i] = portfolio_std_dev
                                results_m[2,i] = (portfolio_return - 0.02) / portfolio_std_dev
                            results_df = pd.DataFrame(results_m.T, columns=['Return', 'Volatility', 'Sharpe'])
                            max_sharpe_idx = results_df['Sharpe'].idxmax()
                            max_sharpe_port = results_df.iloc[max_sharpe_idx]
                            opt_weights = weights_record[max_sharpe_idx]
                            fig_ef = px.scatter(results_df, x='Volatility', y='Return', color='Sharpe', title="효율적 전선 (Efficient Frontier)")
                            fig_ef.add_trace(go.Scatter(x=[max_sharpe_port['Volatility']], y=[max_sharpe_port['Return']], mode='markers', marker=dict(color='red', size=15, symbol='star'), name='최적점'))
                            st.plotly_chart(fig_ef, use_container_width=True)
                            col_w, col_s = st.columns([1, 1])
                            with col_w:
                                weight_df = pd.DataFrame({'종목': tickers_m, '비율(%)': (opt_weights * 100).round(2)})
                                fig_w = px.pie(weight_df, values='비율(%)', names='종목', hole=0.4)
                                st.plotly_chart(fig_w, use_container_width=True)
                            with col_s:
                                st.metric("예상 연평균 수익률", f"{max_sharpe_port['Return']*100:.2f}%")
                                st.metric("예상 연 변동성", f"{max_sharpe_port['Volatility']*100:.2f}%")
                                st.metric("샤프 지수", f"{max_sharpe_port['Sharpe']:.2f}")
                    except Exception as e: st.error(f"오류: {e}")

    with v6_t5:
        st.markdown("### ⚡ 실시간 호가창 체결강도 & 모멘텀 (1분봉 틱 분석)")
        tick_ticker = st.text_input("종목 티커 입력 (예: TSLA - 야후 파이낸스 1m 데이터)", value="TSLA").upper()
        if st.button("🔎 1분봉 누적 거래량 델타(CVD) 분석"):
            with st.spinner("야후 파이낸스 1분봉 데이터 추출 중..."):
                try:
                    df_tick = yf.Ticker(tick_ticker).history(period="1d", interval="1m")
                    if df_tick.empty: st.error("1분봉 데이터가 없습니다.")
                    else:
                        delta_direction = np.sign(df_tick['Close'] - df_tick['Open'])
                        delta_direction = delta_direction.replace(0, method='ffill').fillna(1)
                        df_tick['CVD'] = (df_tick['Volume'] * delta_direction).cumsum()
                        fig_tick = go.Figure()
                        fig_tick.add_trace(go.Scatter(x=df_tick.index, y=df_tick['Close'], name='주가', line=dict(color='blue', width=2)))
                        fig_tick.add_trace(go.Scatter(x=df_tick.index, y=df_tick['CVD'], name='누적 매수압력(CVD)', yaxis='y2', line=dict(color='orange', width=2, dash='dot')))
                        fig_tick.update_layout(title=f"[{tick_ticker}] 당일 1분봉 주가 vs 누적 매수 압력(CVD)", yaxis=dict(title="주가"), yaxis2=dict(title="CVD", overlaying="y", side="right"), height=400, hovermode="x unified")
                        st.plotly_chart(fig_tick, use_container_width=True)
                except Exception as e: st.error(f"분석 실패: {e}")
