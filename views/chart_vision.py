# -*- coding: utf-8 -*-
"""👁️ 차트 이미지 AI 비전 분석

app.py 라우팅에서 분리된 페이지. 함수 라이브러리는 core 에서 가져온다.
"""
from core import *


def render(ctx):
    _nav_changed = ctx['_nav_changed']
    api_key_input = ctx['api_key_input']

    st.markdown("## 👁️ 차트 이미지 AI 비전 분석")
    st.info("💡 차트를 캡처(Windows: `Win+Shift+S` / Mac: `Cmd+Shift+4`)한 뒤 **📋 클립보드 붙여넣기 버튼**만 누르면 바로 들어옵니다. 파일 업로드와 이미지 URL 방식도 그대로 지원해요.")
    paste_col, upload_col, url_col = st.columns([1, 1, 1])
    with paste_col:
        st.markdown("**📋 클립보드 캡처 붙여넣기**")
        try:
            from streamlit_paste_button import paste_image_button as _paste_image_button
            _paste_res = _paste_image_button(label="📋 캡처한 차트 붙여넣기", key="vision_paste_btn", errors="ignore")
            if _paste_res is not None and getattr(_paste_res, "image_data", None) is not None:
                st.session_state["vision_pasted_img"] = _paste_res.image_data
        except ImportError:
            st.warning("📦 클립보드 붙여넣기에는 `streamlit-paste-button` 패키지가 필요합니다. "
                       "requirements.txt에 추가해 두었으니 재배포(또는 `pip install streamlit-paste-button`)하면 버튼이 활성화돼요.")
        if st.session_state.get("vision_pasted_img") is not None:
            if st.button("🗑️ 붙여넣은 이미지 지우기", key="vision_paste_clear", use_container_width=True):
                st.session_state["vision_pasted_img"] = None
                st.rerun()
    with upload_col:
        uploaded_chart = st.file_uploader("📸 이미지 파일 업로드", type=["png", "jpg", "jpeg"])
    with url_col:
        image_url = st.text_input("🔗 이미지 주소(URL) 붙여넣기", placeholder="https://example.com/chart.png")

    img_to_analyze = None
    if st.session_state.get("vision_pasted_img") is not None:
        img_to_analyze = st.session_state["vision_pasted_img"]
        st.image(img_to_analyze, caption="📋 클립보드에서 붙여넣은 차트", use_container_width=True)
    elif uploaded_chart:
        img_to_analyze = PIL.Image.open(uploaded_chart)
        st.image(img_to_analyze, use_container_width=True)
    elif image_url:
        try:
            img_to_analyze = PIL.Image.open(requests.get(image_url, stream=True).raw)
            st.image(img_to_analyze, use_container_width=True)
        except Exception: st.error("❌ 이미지 URL 오류")

    if img_to_analyze and st.button("🤖 Gemini Vision 정밀 분석 시작", type="primary", use_container_width=True):
        if not api_key_input: st.error("API 키가 필요합니다.")
        else:
            with st.spinner("AI가 차트를 시각적으로 해독 중입니다..."):
                prompt = "전설적인 차트 분석가로서 차트의 패턴, 지지/저항선, 단기 대응 전략을 마크다운으로 분석해주세요."
                result = ask_gemini_vision(prompt, img_to_analyze, api_key_input)
                st.success(result)
