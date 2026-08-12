# -*- coding: utf-8 -*-
"""메뉴별 페이지 모듈.

app.py 의 라우팅에서 selected_menu 에 맞는 모듈만 지연 import 해서
render(ctx) 를 호출한다. 각 모듈은 `from core import *` 로 함수 라이브러리를
승계하므로 분리 전과 동일한 이름을 그대로 쓴다.

주의: 폴더 이름을 `pages/` 로 바꾸면 Streamlit 멀티페이지 규약과 충돌해
      원치 않는 자동 네비게이션이 생긴다.
"""
