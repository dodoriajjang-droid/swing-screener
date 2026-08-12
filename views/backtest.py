# -*- coding: utf-8 -*-
"""🧪 전략 백테스트 — 과거 데이터로 전략과 점수 엔진을 검증한다.

[분리] 단기 스윙 스캐너 화면의 두 번째 탭이었다. 후보를 '찾는' 작업과
전략이 실제로 통했는지 '검증하는' 작업은 쓰는 목적도 시점도 달라 메뉴를 나눴다.
계산식은 그대로다.
"""
from core import *


def render(ctx):
    api_key_input = ctx.get('api_key_input', "")

    st.markdown("### 🧪 단기 스윙 전략 시뮬레이터")
    st.write("과거 데이터를 기반으로 다양한 퀀트 전략의 실제 수익률과 타점을 검증합니다. (실제 분석 기간은 결과 리포트에 표시됩니다)")

    market_choice_bt = st.radio("시장 선택 (백테스트)", ["🇰🇷 국내 주식", "🇺🇸 미국 주식"], horizontal=True, label_visibility="collapsed")
    t_code = None
    if market_choice_bt == "🇰🇷 국내 주식":
        krx_df = get_krx_stocks()
        opts = ["🔍 테스트할 종목 검색"] + (krx_df['Name'].astype(str) + " (" + krx_df['Code'].astype(str) + ")").tolist() if not krx_df.empty else ["005930"]
        test_query = st.selectbox("백테스트 종목:", opts)
        if test_query != "🔍 테스트할 종목 검색":
            t_code = test_query.rsplit("(", 1)[-1].replace(")", "").strip() if "(" in test_query else "005930"
    else:
        with st.form("bt_us_form"):
            us_bt_query = st.text_input("🔍 미국 주식 종목명/티커 (예: AAPL):")
            us_bt_search_btn = st.form_submit_button("검색")
        if us_bt_search_btn and us_bt_query:
            with st.spinner("검색 중..."): us_bt_results = search_us_ticker(us_bt_query)
            if us_bt_results: st.session_state.us_bt_results = us_bt_results
            else: st.error("검색 결과가 없습니다.")
        if "us_bt_results" in st.session_state and st.session_state.us_bt_results:
            sel_us_bt = st.selectbox("🎯 정확한 종목 선택:", ["선택하세요"] + st.session_state.us_bt_results)
            if sel_us_bt != "선택하세요": t_code = sel_us_bt.split(" ")[0]

    _bt_c1, _bt_c2 = st.columns([2.5, 1.5])
    with _bt_c1:
        strategy_sel = st.selectbox("🎯 백테스트 퀀트 전략 선택", [
            "5-20 이평선 골든크로스", "RSI 과매도 매수 (RSI < 30)", "볼린저밴드 하단 매수", "MACD 교차"
        ])
    with _bt_c2:
        bt_cost_pct = st.number_input("💸 왕복 거래비용 (%)", min_value=0.0, max_value=2.0, value=0.25, step=0.05,
                                      help="수수료+거래세+슬리피지를 합친 왕복(매수+매도) 비용. 국내 일반계좌 기준 약 0.2~0.4%, 미국 주식은 0.05~0.2% 수준을 권장합니다. 0으로 두면 비용 미반영(기존 방식).")

    # 🛡️ [개선] 손절·익절·보유상한 청산 규칙 (0 = 미적용 → 기존 신호 청산만)
    _bt_e1, _bt_e2, _bt_e3 = st.columns(3)
    with _bt_e1:
        bt_stop = st.number_input("🛑 손절 (%)", min_value=0.0, max_value=50.0, value=0.0, step=0.5,
                                  help="진입가 대비 이만큼 하락하면 청산. 0=미적용(신호로만 청산). 앱 권장 손절은 20일선 -3% 수준.")
    with _bt_e2:
        bt_target = st.number_input("🎯 익절 (%)", min_value=0.0, max_value=200.0, value=0.0, step=1.0,
                                    help="진입가 대비 이만큼 상승하면 청산. 0=미적용.")
    with _bt_e3:
        bt_maxhold = st.number_input("📆 최대 보유일", min_value=0, max_value=250, value=0, step=1,
                                     help="진입 후 이 영업일수를 넘기면 강제 청산. 0=미적용.")
    st.caption("💡 손절·익절·보유상한은 신호 청산보다 **우선** 적용됩니다. 셋 다 0이면 기존처럼 ‘신호 On=진입 / Off=청산’만 검증합니다. "
               "일봉 종가 기준이라 장중 터치는 반영하지 않습니다(보수적 측정).")

    if t_code and st.button("▶️ 시뮬레이션 돌리기", type="primary"):
        with st.spinner("과거 1년 데이터 백테스팅 중..."):
            bt_df = get_historical_data(t_code, 365)
            if not bt_df.empty:
                bt_df['MA5'] = bt_df['Close'].rolling(5).mean()
                bt_df['MA20'] = bt_df['Close'].rolling(20).mean()
                bt_df['Std_20'] = bt_df['Close'].rolling(window=20).std()
                bt_df['Bollinger_Lower'] = bt_df['MA20'] - (bt_df['Std_20'] * 2)
                delta = bt_df['Close'].diff()
                rs = (delta.where(delta > 0, 0.0).rolling(14).mean()) / (-delta.where(delta < 0, 0.0).rolling(14).mean())
                bt_df['RSI'] = 100 - (100 / (1 + rs))
                exp1 = bt_df['Close'].ewm(span=12, adjust=False).mean()
                exp2 = bt_df['Close'].ewm(span=26, adjust=False).mean()
                bt_df['MACD'] = exp1 - exp2
                bt_df['Signal_Line'] = bt_df['MACD'].ewm(span=9, adjust=False).mean()

                bt_df['Signal'] = 0
                if strategy_sel == "5-20 이평선 골든크로스": bt_df.loc[bt_df['MA5'] > bt_df['MA20'], 'Signal'] = 1
                elif strategy_sel == "RSI 과매도 매수 (RSI < 30)": bt_df.loc[bt_df['RSI'] < 30, 'Signal'] = 1
                elif strategy_sel == "볼린저밴드 하단 매수": bt_df.loc[bt_df['Close'] < bt_df['Bollinger_Lower'], 'Signal'] = 1
                elif strategy_sel == "MACD 교차": bt_df.loc[bt_df['MACD'] > bt_df['Signal_Line'], 'Signal'] = 1

                bt_df['Daily_Return'] = bt_df['Close'].pct_change()

                # 🛡️ [개선] 손절·익절·보유상한 청산을 반영한 이벤트 기반 시뮬레이션.
                #   진입: 관망(flat) 중 신호 발생일 종가 매수 → 다음날부터 수익 귀속(기존과 동일)
                #   청산 우선순위: 손절 → 익절 → 보유상한 → 신호종료.
                #   손절/익절/보유상한 청산 후에는 신호가 한 번 꺼졌다 다시 켜져야 재진입(휩쏘 방지).
                #   신호종료 청산이면 즉시 재진입 가능(기존 동작과 동일).
                _sig = bt_df['Signal'].fillna(0).values
                _closes = bt_df['Close'].values
                _dates = bt_df.index
                _n = len(_closes)
                _stop_f = (bt_stop / 100.0) if bt_stop > 0 else None
                _tgt_f = (bt_target / 100.0) if bt_target > 0 else None
                _maxh = int(bt_maxhold) if bt_maxhold > 0 else None
                _oneway_cost = (bt_cost_pct / 2.0) / 100.0
                _rt_cost = bt_cost_pct / 100.0

                _pos = np.zeros(_n)
                trade_records = []
                _armed = True
                _entry_i = None
                _idx = 0
                while _idx < _n:
                    if _entry_i is None:                       # 관망 상태
                        if _armed and _sig[_idx] == 1:
                            _entry_i = _idx                    # 신호일 종가 매수
                        elif _sig[_idx] == 0:
                            _armed = True
                        _idx += 1
                        continue
                    _entry_px = _closes[_entry_i]
                    _exit_i, _reason = None, None
                    _j = _entry_i + 1
                    while _j < _n:
                        _pos[_j] = 1                           # 보유일 표시
                        _chg = _closes[_j] / _entry_px - 1.0
                        if _stop_f is not None and _chg <= -_stop_f:
                            _exit_i, _reason = _j, "손절"; break
                        if _tgt_f is not None and _chg >= _tgt_f:
                            _exit_i, _reason = _j, "익절"; break
                        if _maxh is not None and (_j - _entry_i) >= _maxh:
                            _exit_i, _reason = _j, "보유상한"; break
                        if _sig[_j] == 0:
                            _exit_i, _reason = _j, "신호종료"; break
                        _j += 1
                    if _exit_i is None:                        # 기간 끝까지 보유 중
                        _exit_i, _reason, _open_trade = _n - 1, "보유중", True
                    else:
                        _open_trade = False
                    _ret = (_closes[_exit_i] / _entry_px - 1.0) - _rt_cost
                    trade_records.append({
                        "진입일": _dates[_entry_i].strftime("%y/%m/%d"),
                        "청산일": _dates[_exit_i].strftime("%y/%m/%d") + (" (보유중)" if _open_trade else ""),
                        "청산사유": _reason,
                        "보유일": max((_dates[_exit_i] - _dates[_entry_i]).days, 1),
                        "수익률(%)": _ret * 100.0,
                    })
                    _armed = (_reason == "신호종료")           # 신호종료면 즉시 재진입 가능
                    _entry_i = None
                    _idx = _exit_i + 1

                bt_df['Position'] = _pos
                bt_df['Trade_Mark'] = bt_df['Position'].diff().fillna(0)
                # 💸 왕복 거래비용: 진입/청산 발생일마다 편도 비용 차감
                bt_df['Strategy_Return'] = (bt_df['Position'] * bt_df['Daily_Return']) - (bt_df['Trade_Mark'].abs() * _oneway_cost)
                bt_df['Cumulative_Market'] = (1 + bt_df['Daily_Return']).cumprod()
                bt_df['Cumulative_Strategy'] = (1 + bt_df['Strategy_Return']).cumprod()

                bt_df['Cum_Max'] = bt_df['Cumulative_Strategy'].cummax()
                bt_df['Drawdown'] = (bt_df['Cumulative_Strategy'] - bt_df['Cum_Max']) / bt_df['Cum_Max']
                mdd = bt_df['Drawdown'].min() * 100

                # 📈 '매수→매도' 거래 단위 통계
                total_trades = len(trade_records)
                _wins = [t for t in trade_records if t["수익률(%)"] > 0]
                _losses = [t for t in trade_records if t["수익률(%)"] <= 0]
                win_rate = (len(_wins) / total_trades * 100.0) if total_trades > 0 else 0.0
                avg_win = (sum(t["수익률(%)"] for t in _wins) / len(_wins)) if _wins else 0.0
                avg_loss = (sum(t["수익률(%)"] for t in _losses) / len(_losses)) if _losses else 0.0
                _gross_win = sum(t["수익률(%)"] for t in _wins)
                _gross_loss = abs(sum(t["수익률(%)"] for t in _losses))
                profit_factor = (_gross_win / _gross_loss) if _gross_loss > 0 else (float('inf') if _gross_win > 0 else 0.0)
                avg_hold = (sum(t["보유일"] for t in trade_records) / total_trades) if total_trades > 0 else 0.0

                # 📐 샤프지수 (연환산, 무위험수익률 0 가정)
                _sr_std = bt_df['Strategy_Return'].std()
                sharpe = (bt_df['Strategy_Return'].mean() / _sr_std * (252 ** 0.5)) if _sr_std and _sr_std > 0 else 0.0
                # 🎲 기대값(회당 평균) · 평균 손익비(Payoff) · 시장 노출도 · CAGR
                expectancy = (sum(t["수익률(%)"] for t in trade_records) / total_trades) if total_trades > 0 else 0.0
                payoff = (avg_win / abs(avg_loss)) if avg_loss < 0 else (float('inf') if avg_win > 0 else 0.0)
                exposure = (float(_pos.sum()) / _n * 100.0) if _n > 0 else 0.0
                _cum_final = float(bt_df['Cumulative_Strategy'].iloc[-1])
                _years = _n / 252.0
                cagr = ((_cum_final ** (1.0 / _years) - 1.0) * 100.0) if (_cum_final > 0 and _years > 0) else 0.0
                _exit_counts = {}
                for _t in trade_records:
                    _exit_counts[_t["청산사유"]] = _exit_counts.get(_t["청산사유"], 0) + 1

                fig = go.Figure()
                x_axis = bt_df.index
                fig.add_trace(go.Scatter(x=x_axis, y=bt_df['Close'], name="주가 (Close)", line=dict(color='#3b82f6', width=1.5)))
                buy_idx = bt_df[bt_df['Trade_Mark'] == 1].index
                fig.add_trace(go.Scatter(x=buy_idx, y=bt_df.loc[buy_idx, 'Close'], mode='markers', name='Buy (매수)', marker=dict(symbol='triangle-up', size=14, color='#ef4444', line=dict(width=1, color='darkred'))))
                sell_idx = bt_df[bt_df['Trade_Mark'] == -1].index
                fig.add_trace(go.Scatter(x=sell_idx, y=bt_df.loc[sell_idx, 'Close'], mode='markers', name='Sell (매도)', marker=dict(symbol='triangle-down', size=14, color='#3b82f6', line=dict(width=1, color='darkblue'))))

                fig.update_layout(title=f"'{t_code}' 백테스트 타점 시각화 ({strategy_sel})", height=500, hovermode="x unified", legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1))
                st.plotly_chart(fig, use_container_width=True)

                final_market = (bt_df['Cumulative_Market'].iloc[-1] - 1) * 100
                final_strat = (bt_df['Cumulative_Strategy'].iloc[-1] - 1) * 100

                _period_str = f"{bt_df.index[0].strftime('%Y.%m.%d')} ~ {bt_df.index[-1].strftime('%Y.%m.%d')} (영업일 {len(bt_df)}일)"
                st.markdown("### 📊 백테스트 성과 리포트")
                st.caption(f"🗓️ 실제 분석 기간: **{_period_str}** ｜ 💸 왕복 거래비용 **{bt_cost_pct:.2f}%** 반영 ｜ 승률·손익은 '매수→매도' **거래 단위** 기준")
                c1, c2, c3, c4 = st.columns(4)
                def metric_card(title, value, delta=None, is_red=False, is_green=False):
                    bg_color = "rgba(100, 100, 100, 0.05)"
                    border_color = "#888"
                    if is_red:
                        bg_color = "rgba(220, 38, 38, 0.08)"
                        border_color = "#dc2626"
                    elif is_green:
                        bg_color = "rgba(22, 163, 74, 0.08)"
                        border_color = "#16a34a"
                    delta_html = f"<div style='font-size:0.85em; margin-top:5px; color:#555;'>{delta}</div>" if delta else ""
                    return f"<div style='background-color: {bg_color}; padding: 15px; border-radius: 8px; border-left: 4px solid {border_color}; margin-bottom: 10px;'><div style='font-size:0.9em; color:#555; font-weight:bold;'>{title}</div><div style='font-size:1.6em; font-weight:bold; font-variant-numeric:tabular-nums; margin-top:5px;'>{value}</div>{delta_html}</div>"

                with c1: st.markdown(metric_card("전략 누적 수익률", f"{final_strat:.2f}%", f"단순 보유 대비 {final_strat - final_market:+.2f}%p (비용 차감 후)", is_red=(final_strat>0), is_green=(final_strat<0)), unsafe_allow_html=True) 
                with c2: st.markdown(metric_card("최대 낙폭 (MDD)", f"{mdd:.2f}%", "계좌 최대 하락률", is_green=(mdd<-20)), unsafe_allow_html=True)
                with c3: st.markdown(metric_card("거래별 승률", f"{win_rate:.1f}%", f"총 {total_trades}건 중 {len(_wins)}건 수익", is_red=(win_rate>50)), unsafe_allow_html=True)
                with c4: st.markdown(metric_card("Profit Factor", "∞" if profit_factor == float('inf') else f"{profit_factor:.2f}", "총수익 ÷ 총손실 (1 초과 = 우위)", is_red=(profit_factor>1)), unsafe_allow_html=True)

                c5, c6, c7, c8 = st.columns(4)
                with c5: st.markdown(metric_card("평균 수익 거래", f"+{avg_win:.2f}%", "수익 거래의 평균 수익률", is_red=(avg_win>0)), unsafe_allow_html=True)
                with c6: st.markdown(metric_card("평균 손실 거래", f"{avg_loss:.2f}%", "손실 거래의 평균 손실률", is_green=(avg_loss<0)), unsafe_allow_html=True)
                with c7: st.markdown(metric_card("평균 보유 기간", f"{avg_hold:.1f}일", "거래당 평균 보유일"), unsafe_allow_html=True)
                with c8: st.markdown(metric_card("샤프 지수 (연환산)", f"{sharpe:.2f}", "1 이상이면 양호한 위험 대비 수익"), unsafe_allow_html=True)

                c9, c10, c11, c12 = st.columns(4)
                with c9: st.markdown(metric_card("기대값 (회당)", f"{expectancy:+.2f}%", "거래 1회 평균 손익(비용 후)", is_red=(expectancy>0), is_green=(expectancy<0)), unsafe_allow_html=True)
                with c10: st.markdown(metric_card("CAGR (연환산)", f"{cagr:+.2f}%", "전략 연환산 복리 수익률", is_red=(cagr>0), is_green=(cagr<0)), unsafe_allow_html=True)
                with c11: st.markdown(metric_card("평균 손익비", "∞" if payoff == float('inf') else f"{payoff:.2f}", "평균수익 ÷ 평균손실 (Payoff)", is_red=(payoff>=1 and payoff!=float('inf')) or payoff==float('inf')), unsafe_allow_html=True)
                with c12: st.markdown(metric_card("시장 노출도", f"{exposure:.0f}%", "전체 기간 중 실제 보유일 비중"), unsafe_allow_html=True)

                if _exit_counts:
                    _ec_txt = " · ".join(f"{k} {v}건" for k, v in sorted(_exit_counts.items(), key=lambda x: -x[1]))
                    _rule_txt = " · ".join([x for x in [
                        (f"손절 {bt_stop:.1f}%" if bt_stop > 0 else ""),
                        (f"익절 {bt_target:.1f}%" if bt_target > 0 else ""),
                        (f"보유상한 {int(bt_maxhold)}일" if bt_maxhold > 0 else ""),
                    ] if x])
                    if _rule_txt:
                        st.caption(f"🚪 청산 사유 분포: {_ec_txt}  ｜  적용 규칙: {_rule_txt}")
                    else:
                        st.caption(f"🚪 청산 사유 분포: {_ec_txt}  (손절·익절 미적용 — 신호 청산만)")

                if trade_records:
                    def _prc_trades():
                        _tr_df = pd.DataFrame(trade_records)
                        _tr_df["수익률(%)"] = _tr_df["수익률(%)"].map(lambda v: round(v, 2))
                        st.dataframe(_tr_df, use_container_width=True, hide_index=True)
                        st.caption("※ 진입가 = 신호 발생일 종가, 청산가 = 청산일 종가(손절·익절도 일봉 종가 기준). "
                                   "'청산사유'로 손절/익절/보유상한/신호종료를 구분합니다. '(보유중)'은 기간 종료까지 미청산 → 마지막 종가로 평가한 거래입니다.")
                    _register_popup("trades", _prc_trades)
                    _popup_button(f"📜 전체 거래 내역 보기 ({total_trades}건)", "trades", f"📜 전체 거래 내역 ({total_trades}건)", key="btn_trades")
                else:
                    st.info("해당 기간에 전략 조건을 충족한 거래가 없었습니다.")
            else: st.error("❌ 데이터를 가져오지 못했습니다.")

    # =====================================================================
    # 🧪 [v7.2] 점수 엔진 검증 (스코어 백테스트)
    #   위 시뮬레이터는 '이평선/RSI 같은 단일 전략'을 검증한다.
    #   여기서는 앱 전반이 쓰는 score_one() 점수 자체가 실제 수익률과
    #   관계가 있는지를 검증한다. 과거 시점(offset_days)의 기술적 상태로
    #   점수를 매기고, 그 이후 실제 수익률과 대조한다.
    # =====================================================================
    st.divider()
    with st.expander("🧪 점수 엔진 검증 — 이 앱의 '점수'가 실제 수익률과 관계있는지 확인", expanded=False):
        st.caption(
            "발굴기·스캐너가 쓰는 **score_one() 점수**를 과거 시점 기준으로 매긴 뒤, 그 이후 실제 주가 수익률과 대조합니다. "
            "점수가 높은 그룹의 평균 수익률이 낮은 그룹보다 높게 나와야 점수 엔진이 의미가 있습니다. "
            "가중치는 `scoring_weights.py` 에서 조정할 수 있고, 아래에서 값을 바꿔 즉시 재검증할 수 있습니다."
        )

        _sb1, _sb2, _sb3 = st.columns(3)
        with _sb1:
            sb_market = st.radio("시장", ["🇰🇷 국내", "🇺🇸 미국"], horizontal=True, key="sb_market")
        with _sb2:
            sb_offset = st.selectbox("검증 시점 (며칠 전 기준으로 점수를 매길지)", [20, 40, 60, 90], index=1,
                                     key="sb_offset",
                                     help="예: 40 → 40영업일 전 시점의 차트 상태로 점수를 매기고, 그 이후 오늘까지의 실제 수익률과 비교합니다.")
        with _sb3:
            sb_n = st.selectbox("표본 종목 수", [30, 50, 100, 200], index=1, key="sb_n",
                                help="많을수록 통계가 안정되지만 그만큼 오래 걸립니다(종목당 약 0.3~1초).")

        sb_lookahead = st.checkbox(
            "수급·밸류·컨센서스도 점수에 포함 (⚠️ 룩어헤드 있음)", value=False, key="sb_lookahead",
            help="수급·PER/PBR·목표가는 '지금' 값만 조회할 수 있어 과거 시점 점수에 넣으면 미래 정보가 섞입니다(룩어헤드 편향). "
                 "기본값(끔)은 순수 기술적 지표만으로 점수를 매겨 편향 없이 검증합니다.")

        _w_json = st.text_area(
            "가중치 덮어쓰기 (JSON, 비우면 기본값)", value="", height=68, key="sb_weights",
            placeholder='예: {"S_ALIGN_PERFECT": 30, "S_VOL_SPIKE": 10}',
            help="scoring_weights.py 의 DEFAULT_WEIGHTS 키만 사용할 수 있습니다. 값을 바꿔 돌려보면서 어떤 가중치가 성과를 개선하는지 확인하세요.")

        if st.button("🧪 점수 엔진 검증 실행", type="primary", use_container_width=True, key="sb_run"):
            _w_over = None
            _w_err = None
            if _w_json.strip():
                try:
                    _w_over = make_weights(json.loads(_w_json))
                except Exception as e:
                    _w_err = f"{type(e).__name__}: {e}"
            if _w_err:
                st.error(f"❌ 가중치 JSON 오류 — {_w_err}\n\n사용 가능한 키는 {len(tunable_keys())}개입니다. scoring_weights.py 를 참고하세요.")
            else:
                _sb_targets = get_scan_targets(sb_n) if sb_market == "🇰🇷 국내" else get_us_scan_targets(sb_n)
                if not _sb_targets:
                    st.error("❌ 종목 리스트를 불러오지 못했습니다.")
                else:
                    # 과거 시점 점수에 '지금 값'이 섞이지 않도록 제거할 필드
                    _LEAK_KEYS = ("외인수급", "기관수급", "개인수급", "장중잠정수급",
                                  "기관연속순매수", "외인연속순매수", "연기금추정순매수", "연기금연속순매수",
                                  "PER", "PBR", "목표가_컨센서스", "AI목표가")
                    _sb_mood = {"risk_on": 0.0, "_idx20": None}   # 과거 시장 분위기는 복원 불가 → 중립 고정

                    def _sb_one(target):
                        name, code = target
                        time.sleep(0.1)
                        res = analyze_technical_pattern(name, code, offset_days=int(sb_offset))
                        if not res:
                            return None
                        fwd = _f_num(res.get("수익률"))
                        if fwd is None:
                            return None
                        tech = dict(res)
                        if not sb_lookahead:
                            for k in _LEAK_KEYS:
                                tech.pop(k, None)
                        try:
                            sc, hz, top, grade, _rs, _rf = score_one(
                                tech, None, _sb_mood, weights=_w_over)
                        except Exception as _dg_e:
                            _diag_note("_sb_one", _dg_e)
                            return None
                        return {"종목명": name, "코드": code, "점수": top, "구간": hz, "등급": grade,
                                "단기": sc["단기"], "중기": sc["중기"], "장기": sc["장기"],
                                f"이후 {sb_offset}일 수익률(%)": round(fwd, 2)}

                    _sb_rows, _done = [], 0
                    _pb, _stat = st.progress(0), st.empty()
                    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as ex:
                        for fut in concurrent.futures.as_completed(
                                {ex.submit(_sb_one, t): t for t in _sb_targets}):
                            r = fut.result()
                            _done += 1
                            if r: _sb_rows.append(r)
                            _pb.progress(_done / len(_sb_targets))
                            _stat.text(f"🧪 검증 중... ({_done}/{len(_sb_targets)}) — {len(_sb_rows)}개 유효")
                    _pb.empty(); _stat.empty()
                    st.session_state["sb_result"] = {
                        "rows": _sb_rows, "offset": int(sb_offset), "market": sb_market,
                        "n_req": len(_sb_targets), "lookahead": bool(sb_lookahead),
                        "weights": ("사용자 지정" if _w_over else "기본값"),
                        "time": datetime.now().strftime("%Y-%m-%d %H:%M"),
                    }

        _sb_res = st.session_state.get("sb_result")
        if _sb_res and _sb_res["rows"]:
            _off = _sb_res["offset"]
            _rcol = f"이후 {_off}일 수익률(%)"
            sb_df = pd.DataFrame(_sb_res["rows"])
            if _rcol not in sb_df.columns:      # 이전 실행 결과(다른 기간)와 컬럼명이 다를 때
                _rcol = [c for c in sb_df.columns if c.startswith("이후 ")][0]

            st.caption(f"📌 {_sb_res['time']} · {_sb_res['market']} · 요청 {_sb_res['n_req']}종목 중 "
                       f"**{len(sb_df)}종목 유효** · 가중치 {_sb_res['weights']} · "
                       f"{'⚠️ 룩어헤드 포함' if _sb_res['lookahead'] else '✅ 기술적 지표만(편향 없음)'}")

            # --- 순위상관 (Spearman): 점수 순위와 수익률 순위가 같이 움직이는가 ---
            _s = sb_df["점수"].rank()
            _r = sb_df[_rcol].rank()
            _rho = float(np.corrcoef(_s, _r)[0, 1]) if len(sb_df) > 2 and _s.std() > 0 and _r.std() > 0 else float("nan")

            # --- 점수 구간별 성과 ---
            _bins = [0, 40, 50, 60, 70, 100.01]
            _labels = ["~40 (약함)", "40~50", "50~60", "60~70", "70~ (강력)"]
            sb_df["_구간"] = pd.cut(sb_df["점수"], bins=_bins, labels=_labels, right=False)
            _agg = sb_df.groupby("_구간", observed=False).agg(
                종목수=(_rcol, "size"),
                평균수익률=(_rcol, "mean"),
                중앙값=(_rcol, "median"),
                승률=(_rcol, lambda s: (s > 0).mean() * 100 if len(s) else np.nan),
            ).reset_index().rename(columns={"_구간": "점수구간"})
            _agg = _agg[_agg["종목수"] > 0]
            for _c in ("평균수익률", "중앙값", "승률"):
                _agg[_c] = _agg[_c].astype(float).round(2)

            _m1, _m2, _m3 = st.columns(3)
            _hi = sb_df[sb_df["점수"] >= 60][_rcol]
            _lo = sb_df[sb_df["점수"] < 50][_rcol]
            _spread = (_hi.mean() - _lo.mean()) if (len(_hi) and len(_lo)) else float("nan")
            with _m1:
                st.metric("순위상관 (Spearman ρ)", "N/A" if _rho != _rho else f"{_rho:+.3f}",
                          help="점수 순위와 이후 수익률 순위의 상관. +0.1~0.2만 되어도 실무적으로 의미 있는 신호로 봅니다. 0 근처면 점수가 무의미하다는 뜻입니다.")
            with _m2:
                st.metric("고점수(60↑) − 저점수(50↓) 수익률 차", "N/A" if _spread != _spread else f"{_spread:+.2f}%p",
                          help="점수 엔진이 실제로 잘 고르는지 보여주는 가장 직관적인 수치. 음수면 점수가 거꾸로 작동하고 있다는 뜻입니다.")
            with _m3:
                st.metric("전체 평균 수익률", f"{sb_df[_rcol].mean():+.2f}%",
                          help="표본 전체 평균. 개별 구간 성과는 이 값과 비교해서 봐야 합니다(시장 전체가 오른 기간일 수 있음).")

            st.dataframe(_agg, use_container_width=True, hide_index=True)

            try:
                _fig_sb = px.bar(_agg, x="점수구간", y="평균수익률", text="평균수익률",
                                 color="평균수익률", color_continuous_scale=["#dc2626", "#94a3b8", "#16a34a"],
                                 title=f"점수 구간별 이후 {_off}영업일 평균 수익률")
                _fig_sb.update_traces(texttemplate="%{text:.2f}%", textposition="outside")
                _fig_sb.update_layout(height=330, showlegend=False, coloraxis_showscale=False,
                                      margin=dict(t=50, b=10))
                st.plotly_chart(_fig_sb, use_container_width=True)
            except Exception as e:
                _diag_note("score_backtest_chart", e)

            with st.expander(f"📋 종목별 상세 ({len(sb_df)}건)"):
                st.dataframe(sb_df.drop(columns=["_구간"]).sort_values("점수", ascending=False),
                             use_container_width=True, hide_index=True)

            st.info(
                "**해석 주의**\n"
                f"- 표본 {len(sb_df)}종목·단일 기간({_off}영업일) 결과라 그대로 일반화하면 안 됩니다. 기간과 표본을 바꿔가며 반복 검증하세요.\n"
                "- 검증 시점 이후 상장폐지·거래정지된 종목은 애초에 리스트에 없어 **생존 편향**이 있습니다.\n"
                "- 표본은 '현재 거래대금 상위' 종목이라, 그 사이 거래대금이 늘어난 종목이 과대 대표됩니다.\n"
                "- 시장 전체가 오른 기간이면 모든 구간이 플러스로 나옵니다. **구간 간 차이**를 보세요."
            )
        elif _sb_res:
            st.warning("유효한 결과가 없습니다. 표본 수를 늘리거나 검증 시점을 짧게 잡아보세요.")
