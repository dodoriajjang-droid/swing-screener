# -*- coding: utf-8 -*-
"""⚡ 메가트렌드 & 테마 대장주

app.py 라우팅에서 분리된 페이지. 함수 라이브러리는 core 에서 가져온다.
"""
from core import *


def render(ctx):
        _nav_changed = ctx['_nav_changed']
        api_key_input = ctx['api_key_input']

        st.markdown("## ⚡ 메가트렌드 & 테마 대장주")
        st.write("AI가 최신 트렌드를 분석하여, 숨겨진 글로벌 텐배거(10배 상승) 후보와 한·미 양국의 핵심 수혜주를 동시에 발굴합니다.")

        # [버그수정] 이 페이지로 '새로 진입'했는데 결과 없는 '미완료 검색어'가 남아 있으면 정리한다.
        #  이전에 검색하다 만 deep_tech_query 가 재진입 시 자동 재실행되어 '종목을 찾지 못했습니다' 오류가
        #  잠깐 떴다 사라지던 현상을 방지. (이미 완료된 결과 deep_tech_results 는 그대로 보존)
        if _nav_changed and st.session_state.get("deep_tech_results") is None:
            st.session_state.deep_tech_query = None
            st.session_state.deep_tech_brief = None

        # ... (이하 해당 블록 내용 전체)
        
        if not api_key_input:
            st.warning("⚠️ 사이드바에 Gemini API 키를 입력하시면 글로벌 AI 스캐너가 활성화됩니다.")
        else:
            st.markdown("### 🔥 현재 글로벌 시장 주도 테마 (AI 자동 추출)")
            with st.spinner("한국(KRX) 및 미국(US) 주요 증시의 거래 데이터를 분석하여 핵심 테마를 추출 중입니다..."):
                hot_themes_tab5 = get_trending_themes_with_ai(api_key_input)
                
            cols_d = st.columns(4) 
            for idx, theme in enumerate(hot_themes_tab5[:4]):
                if cols_d[idx].button(f"🔥 {theme}", key=f"hot_theme_btn_{idx}", use_container_width=True):
                    st.session_state.deep_tech_query = theme
                    st.session_state.deep_tech_results = None
                    st.session_state.deep_tech_brief = None

            st.markdown("### 🔎 직접 글로벌 테마 검색")
            with st.form(key="theme_search_form", clear_on_submit=False):
                col_in1, col_in2 = st.columns([8, 2], vertical_alignment="bottom")
                with col_in1:
                    custom_query = st.text_input(
                        "분석할 메가트렌드나 테마를 입력하세요", 
                        label_visibility="collapsed", 
                        key="deep_tech_input", 
                        placeholder="예: AI 데이터센터 전력, 비만치료제, 우주항공"
                    )
                with col_in2:
                    submit_btn = st.form_submit_button("🚀 글로벌 대장주 발굴", use_container_width=True)
                    
                if submit_btn:
                    if custom_query.strip():
                        st.session_state.deep_tech_query = custom_query.strip()
                        st.session_state.deep_tech_results = None
                        st.session_state.deep_tech_brief = None
                    else:
                        st.warning("테마 키워드를 입력해주세요!")

            if st.session_state.deep_tech_query and st.session_state.deep_tech_results is None:
                st.divider()
                st.markdown(f"### 🎯 '{st.session_state.deep_tech_query}' 글로벌 밸류체인 정밀 분석")
                
                with st.spinner("AI가 해당 테마의 월스트리트 모멘텀과 글로벌 핵심 촉매를 분석 중입니다..."):
                    theme_brief_prompt = f"당신은 글로벌 퀀트 애널리스트입니다.\n'{st.session_state.deep_tech_query}' 테마가 한국과 미국 시장을 주도하는 이유와 향후 글로벌 전망을 3줄로 명확하게 요약하세요."
                    st.session_state.deep_tech_brief = ask_gemini(theme_brief_prompt, api_key_input)
                    
                with st.spinner(f"✨ '{st.session_state.deep_tech_query}' 테마의 한·미 핵심 대장주 및 밸류체인 수혜주를 필터링 중입니다..."):
                    theme_stocks = get_theme_stocks_with_ai(st.session_state.deep_tech_query, api_key_input)
                    if theme_stocks:
                        progress_bar = st.progress(0.0)
                        status_text = st.empty()
                        theme_res_list = []
                        completed, total = 0, len(theme_stocks)
                        
                        def process_theme_stock(item):
                            if len(item) == 2:
                                name, code = item
                                time.sleep(0.1)
                                return analyze_technical_pattern(name, code)
                            return None
                            
                        with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
                            for future in concurrent.futures.as_completed({executor.submit(process_theme_stock, t): t for t in theme_stocks}):
                                res = future.result()
                                completed += 1
                                if res: theme_res_list.append(res)
                                progress_bar.progress(min(1.0, completed / total))
                                status_text.text(f"⚡ 한·미 증시 재무/차트 데이터 파싱 중... ({completed}/{total}) - {len(theme_res_list)}개 타점 확보")
                        
                        st.session_state.deep_tech_results = theme_res_list
                    else:
                        st.error(f"❌ '{st.session_state.deep_tech_query}' 테마와 관련된 종목을 찾지 못했습니다.")
                        st.session_state.deep_tech_query = None

            if st.session_state.deep_tech_results is not None:
                if st.session_state.get('deep_tech_brief'):
                    st.info(f"**💡 글로벌 AI 퀀트 인사이트:**\n{st.session_state.deep_tech_brief}")
                display_sorted_results(st.session_state.deep_tech_results, tab_key="t5", api_key=api_key_input, show_leader_rank=True)
