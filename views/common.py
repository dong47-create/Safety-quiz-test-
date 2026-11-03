"""여러 화면이 함께 쓰는 컨텍스트, 콜백 도우미, 안내 문구, 사이드바."""

from __future__ import annotations

import functools
import random
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, ParamSpec

import streamlit as st

from core import quiz_service
from core.models import QuestionBank, Target, User, View
from core.storage import Storage, StorageError

DISCLAIMER = "본 퀴즈는 학습용이며, 정확한 내용은 현행 법령 원문을 확인하세요."
KST = timezone(timedelta(hours=9))
_FLASH_KEY = "_flash_messages"

P = ParamSpec("P")


@dataclass
class AppContext:
    """한 번의 화면 실행에서 각 화면에 넘겨주는 공통 객체."""

    storage: Storage
    bank: QuestionBank
    user: User


# ---------------------------------------------------------------------------
# 안내 문구 (콜백에서 남기고 다음 화면 그릴 때 한 번 보여줌)
# ---------------------------------------------------------------------------

def flash(message: str, kind: str = "info") -> None:
    st.session_state.setdefault(_FLASH_KEY, []).append((kind, message))


_FLASH_STYLES = {
    "success": (st.success, ":material/check_circle:"),
    "warning": (st.warning, ":material/warning:"),
    "error": (st.error, ":material/error:"),
    "info": (st.info, ":material/info:"),
}


def show_flashes() -> None:
    for kind, message in st.session_state.pop(_FLASH_KEY, []):
        show, icon = _FLASH_STYLES.get(kind, _FLASH_STYLES["info"])
        show(message, icon=icon)


def safe_callback(func: Callable[P, Any]) -> Callable[P, None]:
    """콜백에서 DB 오류가 나면 앱이 멈추지 않도록 안내 문구로 바꾼다."""

    @functools.wraps(func)
    def wrapper(*args: P.args, **kwargs: P.kwargs) -> None:
        try:
            func(*args, **kwargs)
        except StorageError:
            flash("저장소에 연결하지 못했습니다. 잠시 후 다시 시도해 주세요.", "error")

    return wrapper


# ---------------------------------------------------------------------------
# 공통 콜백 (상태 변경은 on_click 콜백에서만, PRD 6.3)
# ---------------------------------------------------------------------------

@safe_callback
def navigate(storage: Storage, uid: str, view: View, target: Target | None = None) -> None:
    """화면 이동. DB에 저장하므로 새로고침해도 유지된다."""
    storage.update_user_view(uid, view, target)


@safe_callback
def start_quiz(storage: Storage, bank: QuestionBank, uid: str, target: Target) -> None:
    """새 회차 시작 (진행 중 회차는 버림)."""
    session = quiz_service.start_session(storage, bank, uid, target, time.time(), random.Random())
    if session is None:
        flash("출제할 문항이 없습니다.", "warning")


@safe_callback
def abandon_quiz(storage: Storage, uid: str) -> None:
    quiz_service.abandon_active_session(storage, uid)
    flash("진행 중이던 퀴즈를 종료했습니다.")


def home_button(ctx: AppContext, key: str, label: str = "처음으로") -> None:
    st.button(
        label,
        key=key,
        icon=":material/home:",
        width="stretch",
        on_click=navigate,
        args=(ctx.storage, ctx.user.uid, View.HOME, None),
    )


def format_kst(value: datetime) -> str:
    return value.astimezone(KST).strftime("%Y-%m-%d %H:%M")


def format_duration(seconds: float) -> str:
    minutes, secs = divmod(int(round(seconds)), 60)
    return f"{minutes}분 {secs}초" if minutes else f"{secs}초"


# ---------------------------------------------------------------------------
# 사이드바 (학습 코드, 기록 불러오기·삭제, 법령 기준일)
# ---------------------------------------------------------------------------

@safe_callback
def _load_by_code(storage: Storage, key: str) -> None:
    code = str(st.session_state.get(key, ""))
    uid = quiz_service.find_uid_by_code(storage, code)
    if uid is None:
        flash("학습 코드를 찾지 못했습니다. 8자리 이상 정확히 입력해 주세요.", "warning")
        return
    st.query_params["uid"] = uid
    st.session_state[key] = ""
    flash("기록을 불러왔습니다.", "success")


@safe_callback
def _delete_all_user_data(storage: Storage, uid: str) -> None:
    storage.delete_user_data(uid)
    flash("모든 기록을 삭제했습니다.", "success")


@st.dialog("내 기록 모두 삭제")
def _confirm_delete_all_data(storage: Storage, uid: str) -> None:
    st.write("응시 기록, 진행 중인 퀴즈, 오답노트가 모두 삭제됩니다. 되돌릴 수 없습니다.")
    col_ok, col_cancel = st.columns(2)
    if col_ok.button("삭제", type="primary", width="stretch", on_click=_delete_all_user_data, args=(storage, uid)):
        st.rerun()
    if col_cancel.button("취소", width="stretch"):
        st.rerun()


def render_sidebar(ctx: AppContext) -> None:
    with st.sidebar:
        st.markdown("#### 🦺 안전보건 법령 퀴즈")
        st.button(
            "처음 화면",
            key="sidebar_home",
            icon=":material/home:",
            width="stretch",
            on_click=navigate,
            args=(ctx.storage, ctx.user.uid, View.HOME, None),
        )
        st.button(
            "오답노트",
            key="sidebar_wrong_notes",
            icon=":material/menu_book:",
            width="stretch",
            on_click=navigate,
            args=(ctx.storage, ctx.user.uid, View.WRONG_NOTES, ctx.user.selected_target),
        )

        st.divider()
        st.caption("내 학습 코드")
        st.html(f'<div class="qz-code">{ctx.user.learning_code}</div>')
        st.html(
            '<p class="qz-side-note">지금 주소(URL)를 저장해 두면 언제든 기록을 이어서 볼 수 있어요. '
            "주소를 다른 사람과 공유하면 기록도 함께 공유됩니다.</p>"
        )

        with st.expander("다른 기기의 기록 불러오기", icon=":material/sync:"):
            st.text_input("학습 코드", key="load_code_input", placeholder="예: 72016051")
            st.button(
                "불러오기",
                key="load_code_button",
                width="stretch",
                on_click=_load_by_code,
                args=(ctx.storage, "load_code_input"),
            )
        with st.expander("기록 관리", icon=":material/settings:"):
            if st.button("내 기록 모두 삭제", key="sidebar_delete_all", icon=":material/delete_forever:", width="stretch"):
                _confirm_delete_all_data(ctx.storage, ctx.user.uid)

        st.divider()
        st.html(
            f'<p class="qz-side-note">📅 법령 기준일: <b>{ctx.bank.law_base_date}</b><br>{DISCLAIMER}</p>'
        )
