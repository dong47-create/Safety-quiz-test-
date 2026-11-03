"""안전보건 법령 퀴즈 진입점.

실행 순서: 사용자 식별(uid) → DB에서 상태 읽기 → 저장된 화면(view)에 맞는 화면 그리기.
상태 변경은 각 화면 버튼의 on_click 콜백에서만 일어난다 (PRD 6.3).
"""

from __future__ import annotations

import time
import uuid
from collections.abc import Callable
from pathlib import Path

import streamlit as st

from core import quiz_service
from core.models import User, View
from core.question_bank import get_question_bank
from core.storage import SQLiteStorage, Storage, StorageError, get_db_path
from views import home, quiz, result, wrong_notes
from views.common import AppContext, render_sidebar, show_flashes
from views.styles import inject_css

st.set_page_config(page_title="안전보건 법령 퀴즈", page_icon="🦺", layout="centered")


@st.cache_resource
def _init_db(db_path: str) -> None:
    """DB 파일과 테이블 생성은 서버당 한 번만 한다."""
    SQLiteStorage(Path(db_path)).create_schema()


def get_storage() -> Storage:
    """실행마다 가벼운 저장소 객체를 새로 만든다.

    저장소 객체 자체를 st.cache_resource로 캐시하면, 개발 중 코드가 다시 불러와질 때
    캐시된 객체가 옛 클래스(Enum)를 계속 써서 `is` 비교가 어긋나는 문제가 생긴다.
    """
    db_path = get_db_path()
    _init_db(str(db_path))
    return SQLiteStorage(db_path, create_schema=False)


def _is_valid_uid(value: str | None) -> bool:
    if not value:
        return False
    try:
        uuid.UUID(value, version=4)
    except ValueError:
        return False
    return True


def resolve_user(storage: Storage) -> User:
    """URL의 uid로 사용자를 찾는다. 없거나 모르는 값이면 새로 발급한다 (F7-1, F7-6)."""
    uid = st.query_params.get("uid")
    if _is_valid_uid(uid):
        user = storage.get_user(uid)
        if user is not None:
            storage.touch_user(uid)
            return user

    new_uid = str(uuid.uuid4())
    user = storage.create_user(new_uid)
    st.query_params["uid"] = new_uid
    return user


ROUTES: dict[View, Callable[[AppContext], None]] = {
    View.HOME: home.render,
    View.GUIDE: quiz.render_guide,
    View.QUIZ: quiz.render_quiz,
    View.RESULT: result.render,
    View.WRONG_NOTES: wrong_notes.render,
}


def main() -> None:
    try:
        storage = get_storage()
        bank = get_question_bank()
        user = resolve_user(storage)
        # 새로고침·재접속 시 DB 상태 바로잡기 (마감 지난 문항 시간 초과 처리 등)
        user, messages = quiz_service.reconcile(storage, bank, user, time.time())
        ctx = AppContext(storage=storage, bank=bank, user=user)

        inject_css()
        render_sidebar(ctx)
        for message in messages:
            st.warning(message, icon=":material/warning:")
        show_flashes()
        ROUTES.get(user.view, home.render)(ctx)
    except StorageError:
        st.error("저장소에 연결하지 못했습니다. 잠시 후 다시 시도해 주세요. 마지막으로 저장된 기록은 그대로 남아 있습니다.")
        st.button("다시 시도", type="primary")


main()
