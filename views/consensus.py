# -*- coding: utf-8 -*-
"""🎯 증권사 목표가 컨센서스

app.py 라우팅에서 분리된 페이지. 함수 라이브러리는 core 에서 가져온다.
"""
from core import *


def render(ctx):
    _nav_changed = ctx['_nav_changed']
    api_key_input = ctx['api_key_input']

    st.markdown("## 🎯 증권사 목표가 컨센서스")
    st.write("특정 종목에 대한 여러 증권사의 최근 6개월 목표가 추이와 투자의견 분포를 시각적으로 분석합니다.")
    
    krx_df = get_krx_stocks()
    if not krx_df.empty:
        opts = ["🔍 종목을 선택하세요"] + (krx_df['Name'].astype(str) + " (" + krx_df['Code'].astype(str) + ")").tolist()
        cons_query = st.selectbox("컨센서스를 분석할 종목:", opts)
        
        if cons_query != "🔍 종목을 선택하세요":
            q_name = cons_query.rsplit(" (", 1)[0]
            q_code = cons_query.rsplit("(", 1)[-1].replace(")", "").strip()
            
            with st.spinner(f"'{q_name}' 증권사 리포트 및 현재가 데이터 연산 중..."):
                history_df = get_stock_research_history(q_code, q_name)
                # 💡 추가됨: 현재 주가 가져오기
                tech_res = analyze_technical_pattern(q_name, q_code)
                curr_price = int(tech_res['현재가']) if tech_res else 0
            
            if history_df.empty:
                st.warning("최근 6개월 내 발간된 증권사 리포트가 없어 컨센서스를 산출할 수 없습니다.")
            else:
                valid_df = history_df[history_df['적정가격'] > 0].copy()
                
                if valid_df.empty:
                    st.warning("목표가가 제시된 리포트가 없습니다.")
                else:
                    avg_price = int(valid_df['적정가격'].mean())
                    median_price = int(valid_df['적정가격'].median())
                    max_price = int(valid_df['적정가격'].max())
                    min_price = int(valid_df['적정가격'].min())
                    report_count = len(valid_df)
                    
                    max_broker = valid_df[valid_df['적정가격'] == max_price]['증권사'].iloc[0]
                    min_broker = valid_df[valid_df['적정가격'] == min_price]['증권사'].iloc[0]
                    
                    # 💡 추가됨: 현재가 대비 평균 목표가 괴리율(기대수익률) 계산
                    upside_pct = ((avg_price - curr_price) / curr_price * 100) if curr_price > 0 else 0
                    
                    with st.container(border=True):
                        st.markdown(f"### {q_name} <span style='font-size: 16px; color: gray;'>{q_code}</span>", unsafe_allow_html=True)
                        
                        # 💡 수정됨: 6열로 변경하고 맨 앞에 현재 주가 배치
                        c0, c1, c2, c3, c4, c5 = st.columns(6)
                        if curr_price > 0:
                            c0.metric("현재 주가", f"{curr_price:,}원")
                            c1.metric("평균 목표가", f"{avg_price:,}원", f"{upside_pct:+.1f}% (괴리율)", delta_color="normal")
                        else:
                            c0.metric("현재 주가", "조회불가")
                            c1.metric("평균 목표가", f"{avg_price:,}원")
                            
                        c2.metric("중앙값", f"{median_price:,}원", f"증권사 {len(valid_df['증권사'].unique())}곳")
                        c3.metric("최고가", f"{max_price:,}원", max_broker, delta_color="normal")
                        c4.metric("최저가", f"{min_price:,}원", min_broker, delta_color="inverse")
                        c5.metric("수집 리포트", f"{report_count}건")
                        
                    st.divider()
                    
                    col_chart1, col_chart2 = st.columns([7, 3])
                    
                    with col_chart1:
                        st.markdown("#### 📈 목표주가 시계열 (최근 6개월)")
                        valid_df['Date'] = pd.to_datetime(valid_df['작성일'], format="%y.%m.%d")
                        valid_df = valid_df.sort_values('Date')
                        
                        fig_line = px.line(valid_df, x='Date', y='적정가격', color='증권사', markers=True, 
                                           title=f"{q_name} 증권사별 목표가 추이",
                                           labels={"Date": "발간일", "적정가격": "목표주가 (원)"})
                        
                        fig_line.add_hline(y=avg_price, line_dash="dash", line_color="rgba(255,0,0,0.5)", annotation_text=f"평균 {avg_price:,}원")
                        # 💡 추가됨: 차트에 현재 주가 기준선 추가
                        if curr_price > 0:
                            fig_line.add_hline(y=curr_price, line_dash="dot", line_color="rgba(0,0,255,0.5)", annotation_text=f"현재 주가 {curr_price:,}원")
                            
                        fig_line.update_layout(hovermode="x unified", height=400, template="plotly_white")
                        st.plotly_chart(fig_line, use_container_width=True)
                        
                    with col_chart2:
                        st.markdown("#### 📊 투자의견 분포")
                        
                        # 투자의견 표준화 → 파이차트용 라벨(영문 병기). 분류는 전역 헬퍼로 통일.
                        def opinion_pie_label(op):
                            std = standardize_opinion(op)  # '강력매수/매수/중립/매도/N/A'
                            return {
                                '강력매수': '강력매수 (Strong Buy)',
                                '매수': '매수 (Buy)',
                                '중립': '중립 (Hold)',
                                '매도': '매도 (Sell)',
                            }.get(std, str(op).strip().upper())

                        history_df['투자의견_표준화'] = history_df['투자의견'].apply(opinion_pie_label)
                        opinion_counts = history_df['투자의견_표준화'].value_counts().reset_index()
                        opinion_counts.columns = ['투자의견', '건수']
                        
                        fig_pie = px.pie(opinion_counts, values='건수', names='투자의견', hole=0.5,
                                         color='투자의견', 
                                         color_discrete_map={
                                            '강력매수 (Strong Buy)': '#003300', 
                                            '매수 (Buy)': '#1b5e20', 
                                            '중립 (Hold)': '#ff7f0e', 
                                            '매도 (Sell)': '#d62728'
                                         })
                        fig_pie.update_layout(height=400, showlegend=True, legend=dict(orientation="h", yanchor="bottom", y=-0.2, xanchor="center", x=0.5))
                        st.plotly_chart(fig_pie, use_container_width=True)
                        
                    st.markdown("#### 📋 증권사별 최신 컨센서스")
                    latest_df = valid_df.sort_values('Date', ascending=False).drop_duplicates(subset=['증권사'], keep='first')
                    
                    display_latest = latest_df[['증권사', '투자의견', '적정가격', '작성일', '원문링크']].copy()
                    display_latest['적정가격'] = display_latest['적정가격'].apply(lambda x: f"{x:,}원")
                    st.dataframe(
                        display_latest,
                        column_config={"원문링크": st.column_config.LinkColumn("리포트 보기")},
                        use_container_width=True, hide_index=True
                    )
                    
                    st.divider()
                    if api_key_input and st.button(f"🤖 '{q_name}' 애널리스트 갑론을박 (Debate) 분석", type="primary", use_container_width=True):
                        with st.spinner(f"최근 발간된 '{q_name}' 리포트들의 강세/약세 논리를 분석 중입니다..."):
                            report_texts = "\n".join([f"- [{r['증권사']}] 투자의견: {r['투자의견']}, 목표가: {r['적정가격']}\n제목: {r['제목']}" for _, r in history_df.head(10).iterrows()])
                            prompt = f"""
                            당신은 애널리스트입니다. '{q_name}'에 대한 최근 증권사 리포트들을 바탕으로 시장의 '갑론을박(Debate)'을 분석해주세요.
                            [리포트 요약]
                            {report_texts}
                            
                            다음 형식으로 마크다운 작성:
                            1. 🟢 **강세 논리 (Bull Case)**: 긍정적인 전망과 목표가 상향의 주된 근거 (2~3줄)
                            2. 🔴 **약세/보수적 논리 (Bear Case)**: 우려 사항, 리스크, 목표가 하향/유지의 주된 근거 (2~3줄)
                            3. 💡 **핵심 쟁점 (Key Controversy)**: 가장 의견이 엇갈리는 포인트 (1줄)
                            """
                            st.success(ask_gemini(prompt, api_key_input))
