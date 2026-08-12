# -*- coding: utf-8 -*-
"""💼 내 계좌 & 포트폴리오 진단

app.py 라우팅에서 분리된 페이지. 함수 라이브러리는 core 에서 가져온다.
"""
from core import *


def render(ctx):
    _nav_changed = ctx['_nav_changed']
    api_key_input = ctx['api_key_input']

    st.markdown("## 💼 내 계좌 & 포트폴리오 진단")
    st.write("현재 보유 중인 종목들을 표에 입력하면, 단순 개별 분석이 아닌 **계좌 전체의 자산 배분(비중)과 리스크를 고려한 종합 리밸런싱 전략**을 AI가 진단해 드립니다.")

    if "portfolio_df" not in st.session_state:
        st.session_state.portfolio_df = pd.DataFrame([{"종목명": "", "진입단가": 0, "보유수량": 0}])
    if "pf_editor_ver" not in st.session_state:
        st.session_state.pf_editor_ver = 0

    st.markdown("### 📊 1. 내 포트폴리오 입력")

    up_col, sample_col = st.columns([3, 2])
    with up_col:
        up_file = st.file_uploader(
            "📤 파일을 여기로 끌어다 놓으면 표가 한 번에 채워집니다 (엑셀/CSV)",
            type=["csv", "xlsx", "xlsm", "xls"],
            key="pf_upload",
            help="증권사(키움·미래에셋·삼성 등) 잔고 화면에서 내려받은 엑셀도 그대로 올리면 종목명·수량·매입단가 컬럼을 자동으로 찾아 읽습니다.",
        )
    with sample_col:
        st.caption("처음이라면 👇 샘플 양식을 받아 숫자만 바꿔 올리세요.")
        _sample_df = pd.DataFrame({
            "종목명": ["삼성전자", "SK하이닉스", "AAPL"],
            "진입단가": [71000, 180000, 210],
            "보유수량": [10, 5, 3],
        })
        st.download_button("📑 샘플 양식 받기 (CSV)", _sample_df.to_csv(index=False).encode("utf-8-sig"),
                           file_name="포트폴리오_샘플.csv", mime="text/csv", use_container_width=True)
        try:
            import io as _io
            _xbuf = _io.BytesIO()
            _sample_df.to_excel(_xbuf, index=False)
            st.download_button("📑 샘플 양식 받기 (엑셀)", _xbuf.getvalue(), file_name="포트폴리오_샘플.xlsx",
                               mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                               use_container_width=True)
        except Exception as _dg_e:
            _diag_note("<module>", _dg_e)
            pass  # openpyxl 미설치 환경에서는 CSV 샘플만 제공

    if up_file is not None:
        _file_key = (up_file.name, up_file.size)
        if st.session_state.get("pf_loaded_key") != _file_key:
            try:
                _pf_new, _pf_msg = parse_portfolio_upload(up_file)
                st.session_state.portfolio_df = _pf_new
                st.session_state.pf_loaded_key = _file_key
                st.session_state.pf_upload_msg = _pf_msg
                st.session_state.pf_editor_ver += 1
                st.rerun()
            except ValueError as _e:
                st.error(f"⚠️ {_e}")
            except Exception as _e:
                st.error(f"⚠️ 파일을 해석하지 못했습니다: {_e}")
    if st.session_state.get("pf_upload_msg"):
        st.success(st.session_state.pf_upload_msg)

    # 🔎 [NEW] 종목 검색해서 담기 (장바구니 방식) — 체크한 종목이 아래 표에 행으로 자동 추가됩니다.
    with st.container(border=True):
        st.markdown("**🔎 종목 검색해서 담기** — 검색 후 체크만 하면 아래 표에 자동으로 담깁니다. (담은 뒤 표에서 **단가·수량**만 입력하세요)")
        if "pf_search_query" not in st.session_state:
            st.session_state.pf_search_query = ""

        _s_cols = st.columns([4, 1], vertical_alignment="bottom")
        with _s_cols[0]:
            pf_search_input = st.text_input(
                "종목 검색", placeholder=" 🔍 검색어를 입력하세요. (예: 우주항공, 삼성전자, AAPL)",
                label_visibility="collapsed", key="pf_search_in").strip()
        with _s_cols[1]:
            pf_search_clicked = st.button("종목 검색", type="primary", use_container_width=True, key="pf_search_btn")

        if pf_search_clicked:
            if pf_search_input:
                st.session_state.pf_search_query = pf_search_input
            else:
                st.warning("⚠️ 검색어를 먼저 입력해주세요!")

        if st.session_state.pf_search_query:
            _q = st.session_state.pf_search_query
            pf_options = []
            with st.spinner("데이터베이스에서 종목을 찾는 중입니다..."):
                _krx_s = get_krx_stocks()   # 국내 주식 + ETF 포함
                if not _krx_s.empty:
                    _m = _krx_s[_krx_s['Name'].str.contains(_q, case=False, na=False)]
                    for _, _r in _m.head(60).iterrows():
                        pf_options.append(f"{_r['Name']} [{_r['Code']}]")
                if re.search('[a-zA-Z]', _q):   # 영문 포함 시 미국 주식/ETF 검색
                    try:
                        for _res_us in search_us_ticker(_q):
                            _sym = _res_us.split(" ")[0]
                            _ko = _res_us.split(" (")[1].split(" /")[0]
                            pf_options.append(f"{_ko} [{_sym}]")
                    except Exception as _dg_e:
                        _diag_note("<module>", _dg_e)
                        pass

            if pf_options:
                with st.form(key="pf_add_form", clear_on_submit=True):
                    st.success(f"🎉 '{_q}' 검색 결과 총 **{len(pf_options)}개**를 찾았습니다!")
                    pf_selected = st.multiselect("👇 결과 목록에서 포트폴리오에 담을 종목을 모두 골라주세요:", options=pf_options)
                    pf_submit = st.form_submit_button("🛒 선택한 종목 포트폴리오 표에 추가하기", use_container_width=True)

                    if pf_submit:
                        if pf_selected:
                            _cur = st.session_state.portfolio_df.copy()
                            _existing = set(_cur["종목명"].astype(str).str.strip().str.upper())
                            _new_rows = []
                            for _sel in pf_selected:
                                _nm = str(_sel).strip()   # "이름 [코드]" 형식 그대로 저장 → 진단 시 코드 우선 인식(모호 매칭 방지)
                                if _nm.upper() in _existing:
                                    continue
                                _new_rows.append({"종목명": _nm, "진입단가": 0, "보유수량": 0})
                                _existing.add(_nm.upper())
                            if _new_rows:
                                # 비어 있는 placeholder 행은 제거 후 합치기
                                _mask_empty = (_cur["종목명"].astype(str).str.strip() == "") \
                                              & (pd.to_numeric(_cur["진입단가"], errors="coerce").fillna(0) == 0) \
                                              & (pd.to_numeric(_cur["보유수량"], errors="coerce").fillna(0) == 0)
                                _cur = _cur[~_mask_empty]
                                st.session_state.portfolio_df = pd.concat(
                                    [_cur, pd.DataFrame(_new_rows)], ignore_index=True)
                                st.session_state.pf_editor_ver += 1   # data_editor 강제 새로고침
                                st.toast(f"✅ {len(_new_rows)}개 종목을 표에 담았습니다! 단가·수량을 입력해주세요.", icon="🛒")
                            st.session_state.pf_search_query = ""
                            st.rerun()
                        else:
                            st.warning("⚠️ 추가할 종목을 위에서 먼저 선택해주세요.")
            else:
                st.error("앗! 검색 결과가 없습니다. 🥲 다른 키워드로 다시 검색해보세요.")

    st.caption("표는 직접 고칠 수 있고, 엑셀에서 복사한 표를 셀에 붙여넣기(Ctrl+V)해도 됩니다. 행 추가는 표 맨 아래 ➕ 버튼.")
    edited_df = st.data_editor(
        st.session_state.portfolio_df,
        num_rows="dynamic",
        column_config={
            "종목명": st.column_config.TextColumn("종목명 또는 티커", required=True),
            "진입단가": st.column_config.NumberColumn("내 진입단가", min_value=0, step=1, format="%d"),
            "보유수량": st.column_config.NumberColumn("보유 수량", min_value=0, step=1, format="%d"),
        },
        use_container_width=True,
        key=f"pf_editor_{st.session_state.pf_editor_ver}",
    )
    st.session_state.portfolio_df = edited_df

    _save_col, _clear_col = st.columns([3, 1])
    with _save_col:
        _valid_save = edited_df[
            (edited_df["종목명"].astype(str).str.strip() != "")
            & (pd.to_numeric(edited_df["진입단가"], errors="coerce").fillna(0) > 0)
            & (pd.to_numeric(edited_df["보유수량"], errors="coerce").fillna(0) > 0)
        ]
        st.download_button(
            "💾 내 포트폴리오 저장 (CSV) — 다음에 이 파일만 다시 올리면 그대로 복원돼요",
            _valid_save.to_csv(index=False).encode("utf-8-sig"),
            file_name="내_포트폴리오.csv", mime="text/csv",
            use_container_width=True, disabled=_valid_save.empty,
        )
    with _clear_col:
        if st.button("🗑️ 표 비우기", use_container_width=True):
            st.session_state.portfolio_df = pd.DataFrame([{"종목명": "", "진입단가": 0, "보유수량": 0}])
            st.session_state.pf_editor_ver += 1
            st.session_state.pf_loaded_key = None
            st.session_state.pf_upload_msg = ""
            st.session_state.pop("pf_upload", None)
            st.rerun()

    valid_rows = edited_df[(edited_df["종목명"].astype(str).str.strip() != "") & (edited_df["진입단가"] > 0) & (edited_df["보유수량"] > 0)]

    st.markdown("### 💧 2. 개별 종목 물타기 시뮬레이터 (선택 사항)")
    def _prc_avgcalc():
        col_m1, col_m2, col_m3, col_m4 = st.columns(4)
        with col_m1:
            sim_opts = ["직접 입력"] + valid_rows["종목명"].tolist() if not valid_rows.empty else ["직접 입력"]
            sim_sel = st.selectbox("물타기 할 종목", sim_opts)
        with col_m2:
            sim_name = st.text_input("종목명", value="" if sim_sel == "직접 입력" else sim_sel, label_visibility="collapsed" if sim_sel != "직접 입력" else "visible")
        with col_m3:
            sim_add_price = st.number_input("추가 매수 단가", min_value=0, step=1, format="%d", key="sim_p")
        with col_m4:
            sim_add_qty = st.number_input("추가 매수 수량", min_value=0, step=1, format="%d", key="sim_q")
        
        if st.button("🧮 평단가 계산하기"):
            if sim_name and sim_add_price > 0 and sim_add_qty > 0:
                orig_row = valid_rows[valid_rows["종목명"] == sim_name]
                if not orig_row.empty:
                    orig_price = int(orig_row.iloc[0]["진입단가"])
                    orig_qty = int(orig_row.iloc[0]["보유수량"])
                    orig_invest = orig_price * orig_qty
                    add_invest = sim_add_price * sim_add_qty
                    new_qty = orig_qty + sim_add_qty
                    new_avg = int((orig_invest + add_invest) / new_qty)
                    st.info(f"💡 **[{sim_name} 시뮬레이션]** 기존 {orig_qty}주(평단 {orig_price:,}) + 추가 {sim_add_qty}주(단가 {sim_add_price:,}) ➡️ **총 {new_qty}주, 조정 평단가: {new_avg:,}**")
                else:
                    st.warning("위 포트폴리오 표에 등록된 종목을 선택해야 기존 데이터와 합산하여 정확한 계산이 가능합니다.")
    _register_popup("avgcalc", _prc_avgcalc)
    _popup_button("🧮 평단가(물타기) 계산기 열기", "avgcalc", "🧮 평단가(물타기) 계산기", key="btn_avgcalc")

    if st.button("📊 계좌 전체 종합 진단 및 AI 리밸런싱", type="primary", use_container_width=True):
        if valid_rows.empty:
            st.warning("종목명과 진입단가, 보유수량을 최소 1개 이상 표에 정확히 입력해주세요.")
        elif not api_key_input:
            st.error("좌측 사이드바에 API 키를 입력해주세요.")
        else:
            with st.spinner("전체 포트폴리오 구성 종목의 현재가 조회 및 자산 배분 비중을 분석 중입니다..."):
                portfolio_summary = []
                total_invested_all = 0
                total_current_all = 0
                ex_rate = st.session_state.get('ex_rate', 1350.0)
                
                for idx, row in valid_rows.iterrows():
                    pos_name = str(row["종목명"]).strip()
                    entry_price = int(row["진입단가"])
                    quantity = int(row["보유수량"])
                    
                    search_ticker = None
                    pos_name_kr = pos_name
                    is_us = False
                    
                    # 🛒 [NEW] '이름 [코드]' 형식(검색해서 담기)이면 코드를 우선 인식 → 이름 모호 매칭(예: KO→KODEX) 방지
                    _br = re.search(r'\[([A-Za-z0-9.\-]{1,12})\]\s*$', pos_name)
                    if _br:
                        _code = _br.group(1).strip()
                        pos_name_kr = pos_name[:_br.start()].strip() or _code
                        search_ticker = _code
                        is_us = not _code.isdigit()   # 6자리 숫자면 국내, 아니면 미국 티커
                    
                    # 💡 [핵심 로직 수정] 영어 포함 여부가 아니라, '한국 주식 DB(KRX)'에 있는지 먼저 확인!
                    krx_df = get_krx_stocks()
                    if search_ticker:
                        pass   # 위에서 코드로 확정됨 → 이름 검색 생략
                    # 1. 한국 종목 중에 정확히 일치하는 이름이 있는지 먼저 확인 (대소문자 무시)
                    elif not (exact_match := krx_df[krx_df['Name'].str.upper() == pos_name.upper()]).empty:
                        is_us = False
                        search_ticker = exact_match['Code'].iloc[0]
                        pos_name_kr = exact_match['Name'].iloc[0]
                    else:
                        # 2. 정확히 일치하는 게 없으면, 입력한 단어를 포함하는 한국 종목이 있는지 2차 확인
                        contains_match = krx_df[krx_df['Name'].str.contains(pos_name, case=False, na=False)]
                        if not contains_match.empty:
                            is_us = False
                            search_ticker = contains_match['Code'].iloc[0]
                            pos_name_kr = contains_match['Name'].iloc[0]
                        else:
                            # 3. 한국 주식 DB에 아예 없으면 그제서야 미국 주식으로 간주!
                            is_us = True
                            us_results = search_us_ticker(pos_name)
                            if us_results:
                                search_ticker = us_results[0].split(" ")[0]
                                pos_name_kr = us_results[0].split(" (")[1].split(" /")[0]
                            else:
                                search_ticker = pos_name
                                pos_name_kr = pos_name

                    if search_ticker:
                        time.sleep(0.2) 
                        res = analyze_technical_pattern(pos_name_kr, search_ticker)
                        if res:
                            current_price = res['현재가']
                            invested = entry_price * quantity
                            current_val = current_price * quantity
                            
                            # 💡 환율 곱셈 로직 정상화 (미국장에만 1350원 곱하기)
                            if is_us:
                                invested_krw = invested * ex_rate
                                current_val_krw = current_val * ex_rate
                            else:
                                invested_krw = invested
                                current_val_krw = current_val
                            
                            total_invested_all += invested_krw
                            total_current_all += current_val_krw
                            pnl_pct = ((current_price - entry_price) / entry_price) * 100
                            
                            portfolio_summary.append({
                                "종목명": pos_name_kr, "티커": search_ticker, "시장": "미국" if is_us else "한국",
                                "진입단가": entry_price, "현재가": current_price, "수익률(%)": pnl_pct,
                                "평가금액(원환산)": current_val_krw, "상태": res['상태'], "섹터": res.get('섹터', '기타')
                            })
                        else: st.error(f"'{pos_name}' 데이터를 수집할 수 없어 분석에서 제외되었습니다.")
                    else: st.error(f"'{pos_name}' 종목을 찾을 수 없어 분석에서 제외되었습니다.")
                        
                if portfolio_summary:
                    overall_pnl_pct = ((total_current_all - total_invested_all) / total_invested_all) * 100 if total_invested_all > 0 else 0
                    overall_pnl_amt = total_current_all - total_invested_all
                    
                    st.markdown("---")
                    st.markdown("### 🏦 종합 포트폴리오 대시보드")
                    
                    m1, m2, m3, m4 = st.columns(4)
                    m1.metric("총 매수 금액 (원화 환산)", f"{int(total_invested_all):,}원")
                    m2.metric("총 평가 금액 (원화 환산)", f"{int(total_current_all):,}원")
                    m3.metric("총 평가 손익", f"{int(overall_pnl_amt):,}원", f"{overall_pnl_pct:+.2f}%", delta_color="normal" if overall_pnl_amt > 0 else "inverse")
                    m4.metric("보유 종목 수", f"{len(portfolio_summary)}개")
                    
                    summary_df = pd.DataFrame(portfolio_summary)
                    summary_df["비중(%)"] = (summary_df["평가금액(원환산)"] / total_current_all) * 100
                    
                    display_cols = ["종목명", "시장", "섹터", "수익률(%)", "비중(%)", "상태"]
                    st.dataframe(summary_df[display_cols].style.format({"수익률(%)": "{:+.1f}%", "비중(%)": "{:.1f}%"}), use_container_width=True)

                    with st.spinner("AI가 자산 배분 비중과 개별 종목 상태를 종합하여 포트폴리오 리밸런싱 전략을 수립 중입니다..."):
                        now_kst = datetime.utcnow() + timedelta(hours=9)
                        today_str = now_kst.strftime("%Y년 %m월 %d일")
                        port_details_str = ""
                        for item in portfolio_summary:
                            weight = (item["평가금액(원환산)"] / total_current_all) * 100
                            port_details_str += f"- {item['종목명']} ({item['시장']}, {item['섹터']}): 계좌 내 비중 {weight:.1f}%, 수익률 {item['수익률(%)']:+.1f}%, 현재 차트상태: {item['상태']}\n"

                        ai_plan_prompt = f"""
                        당신은 여의도의 냉철한 펀드매니저이자 자산 배분 전문가입니다.
                        🚨 [시스템 필수 지침]: 오늘 날짜는 {today_str}입니다. 
                        [포트폴리오 전체 요약] 총 투자금액: {int(total_invested_all):,}원, 총 평가금액: {int(total_current_all):,}원, 계좌 전체 수익률: {overall_pnl_pct:+.2f}%
                        [개별 구성 종목 상세 (비중 및 상태)]\n{port_details_str}
                        위 포트폴리오를 '개별 종목'이 아닌 '전체 계좌' 관점에서 분석하여 마크다운으로 답변하세요.
                        1. 🏦 **포트폴리오 종합 진단**: 현재 계좌의 자산 배분(특정 섹터에 쏠렸는지 등) 및 전체 수익/리스크 상태에 대한 평가.
                        2. ⚖️ **비중 조절 & 리밸런싱 조언**: 
                           - 현재 비중이 너무 높거나 리스크가 큰 종목은 얼마나 덜어낼 거신가?
                           - 현금화해야 할 종목과 계속 홀딩할 종목 구분.
                        3. 🛡️ **종목별 액션 플랜 요약**: 각 종목별로 유지(Hold), 비중축소(Reduce), 손절(Cut) 여부와 간략한 이유 명시.
                        """
                        plan_result = ask_gemini(ai_plan_prompt, api_key_input)
                        st.success("✅ AI 포트폴리오 종합 진단 및 리밸런싱 플랜 수립 완료!")
                        st.markdown(plan_result)
