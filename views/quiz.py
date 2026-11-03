"""안내 화면(F1-2)과 퀴즈 화면(F2~F4): 타이머, 보기 선택, 제출, 피드백."""

from __future__ import annotations

import time
from html import escape

import streamlit as st

from core import quiz_service
from core.grading import time_limit_for, type_time_limit
from core.models import Question, QuestionBank, QuestionType, QuizSession, SessionMode, SessionPhase
from core.question_bank import QUIZ_SIZE
from core.storage import Storage
from views import components
from views.common import AppContext, flash, home_button, safe_callback, start_quiz

_NEED_CHOICE_KEY = "_need_choice"
WARNING_SECONDS = 5


# ---------------------------------------------------------------------------
# 안내 화면
# ---------------------------------------------------------------------------

def render_guide(ctx: AppContext) -> None:
    target = ctx.user.selected_target
    if target is None:  # reconcile에서 처음 화면으로 보내므로 보통 오지 않음
        home_button(ctx, "guide_home_fallback")
        return

    count = min(QUIZ_SIZE, len(ctx.bank.for_target(target)))
    components.hero(f"{target.label} 퀴즈", "시작하기 전에 아래 규칙을 확인해 주세요.", eyebrow=f"{components.TARGET_ICONS[target]} 퀴즈 안내")

    with st.container(border=True):
        st.markdown(
            f"""
- 📝 총 **{count}문제**를 풉니다.
- ⏱ 문제마다 제한시간이 있습니다. 4지선다 **{type_time_limit(QuestionType.MULTIPLE)}초**, O/X **{type_time_limit(QuestionType.OX)}초**
- ⏰ 시간 안에 제출하지 않으면 **오답(시간 초과)** 으로 처리됩니다.
- 📖 제출하면 바로 정답, 해설, 근거 조문을 확인할 수 있습니다.
- 📒 틀린 문제는 오답노트에 자동으로 모입니다.
"""
        )
    if count == 0:
        st.error("출제할 문항이 없습니다.", icon=":material/error:")
        home_button(ctx, "guide_home_empty")
        return
    if count < QUIZ_SIZE:
        st.warning(f"문항이 부족해 {count}문제만 출제됩니다.", icon=":material/info:")
    if ctx.storage.get_active_session(ctx.user.uid) is not None:
        st.warning("풀던 퀴즈가 있습니다. 시작하면 풀던 퀴즈는 종료됩니다.", icon=":material/warning:")

    st.button(
        "퀴즈 시작",
        key="guide_start",
        type="primary",
        icon=":material/play_arrow:",
        width="stretch",
        on_click=start_quiz,
        args=(ctx.storage, ctx.bank, ctx.user.uid, target),
    )
    home_button(ctx, "guide_home", label="대상자 다시 고르기")


# ---------------------------------------------------------------------------
# 콜백
# ---------------------------------------------------------------------------

STALE_MESSAGE = "다른 탭이나 기기에서 퀴즈가 먼저 진행되어 처리하지 않았어요. 최신 문제로 화면을 바꿨습니다."


@safe_callback
def _on_submit(storage: Storage, bank: QuestionBank, session_id: str, question_id: str, radio_key: str) -> None:
    """question_id는 이 제출 버튼을 그릴 때의 문항. 서버의 현재 문항과 다르면 처리하지 않는다 (BUG-01)."""
    selected = st.session_state.get(radio_key)
    if selected is None:
        st.session_state[_NEED_CHOICE_KEY] = True
        return
    try:
        quiz_service.submit_answer(
            storage, bank, session_id, selected, time.time(), expected_question_id=question_id
        )
    except quiz_service.StaleViewError:
        flash(STALE_MESSAGE, "warning")


@safe_callback
def _on_next(storage: Storage, bank: QuestionBank, session_id: str, question_id: str) -> None:
    try:
        quiz_service.go_next(storage, bank, session_id, time.time(), expected_question_id=question_id)
    except quiz_service.StaleViewError:
        flash(STALE_MESSAGE, "warning")


# ---------------------------------------------------------------------------
# 타이머 (F3-2 ~ F3-4)
# ---------------------------------------------------------------------------

@st.fragment(run_every=1.0)
def _countdown(storage: Storage, bank: QuestionBank, session_id: str, deadline_at: float, limit: int) -> None:
    """타이머 영역만 1초마다 다시 그린다. 보기 선택값은 그대로 유지된다.

    남은 시간은 DB의 마감 시각 기준으로 계산하므로 새로고침해도 이어진다.
    시간이 다 되면 시간 초과로 기록하고 전체 화면을 다시 그린다 (on_click 밖에서 상태를 바꾸는 예외).
    """
    remaining = max(0.0, deadline_at - time.time())
    components.timer(remaining, limit, WARNING_SECONDS)
    if remaining <= 0:
        quiz_service.mark_timeout(storage, bank, session_id, time.time())
        st.rerun(scope="app")


# ---------------------------------------------------------------------------
# 퀴즈 화면
# ---------------------------------------------------------------------------

def _render_header(session: QuizSession, question: Question) -> None:
    total = len(session.question_ids)
    number = session.current_index + 1
    done = session.current_index + (1 if session.phase is SessionPhase.FEEDBACK else 0)
    title = f"{components.TARGET_ICONS[session.target]} {session.target.label}"
    if session.mode is SessionMode.RETRY_WRONG:
        title += " · 오답 다시 풀기"

    st.html(
        f'<div class="qz-quiz-meta"><span>{escape(title)}</span>'
        f'<span class="qz-count">{number} / {total}</span></div>'
    )
    st.progress(done / total)
    st.markdown(f"{components.source_badge_markdown(question.source)} :gray-badge[{question.type.label}]")
    st.html(f'<p class="qz-question">Q{number}. {escape(question.question)}</p>')


def _render_answering(ctx: AppContext, session: QuizSession, question: Question) -> None:
    labels = {c.id: c.text for c in question.choices}
    if session.deadline_at is not None:
        _countdown(ctx.storage, ctx.bank, session.session_id, session.deadline_at, time_limit_for(question))

    radio_key = f"answer_{session.session_id}_{question.id}"
    st.radio(
        "답을 고르세요",
        options=session.choice_order[question.id],
        index=None,
        format_func=lambda cid: labels[cid],
        key=radio_key,
        label_visibility="collapsed",
    )
    if st.session_state.pop(_NEED_CHOICE_KEY, False):
        st.warning("답을 고른 뒤 제출해 주세요.", icon=":material/touch_app:")

    st.button(
        "제출",
        key=f"submit_{session.session_id}_{question.id}",
        type="primary",
        icon=":material/check:",
        width="stretch",
        on_click=_on_submit,
        args=(ctx.storage, ctx.bank, session.session_id, question.id, radio_key),
    )


def _render_feedback(ctx: AppContext, session: QuizSession, question: Question) -> None:
    answer = quiz_service.find_answer(ctx.storage, session.session_id, question.id)

    if answer is None or answer.timed_out:
        st.warning("**시간 초과** — 오답으로 처리되었습니다.", icon="⏰")
    elif answer.is_correct:
        st.success("**정답입니다!**", icon="✅")
    else:
        st.error("**오답입니다.**", icon="❌")

    components.answer_review(question, session.choice_order[question.id], answer.selected if answer else None)
    st.info(f"**해설**  \n{question.explanation}", icon=":material/lightbulb:")
    components.reference(question.reference)

    is_last = session.current_index + 1 >= len(session.question_ids)
    st.button(
        "결과 보기" if is_last else "다음 문제",
        key=f"next_{session.session_id}_{question.id}",
        type="primary",
        icon=":material/flag:" if is_last else ":material/arrow_forward:",
        width="stretch",
        on_click=_on_next,
        args=(ctx.storage, ctx.bank, session.session_id, question.id),
    )


def render_quiz(ctx: AppContext) -> None:
    session = ctx.storage.get_active_session(ctx.user.uid)
    if session is None:  # reconcile에서 처음 화면으로 보내므로 보통 오지 않음
        st.info("진행 중인 퀴즈가 없습니다.")
        home_button(ctx, "quiz_home_fallback")
        return

    question = quiz_service.current_question(ctx.bank, session)
    _render_header(session, question)

    if session.phase is SessionPhase.ANSWERING:
        _render_answering(ctx, session, question)
    else:
        _render_feedback(ctx, session, question)

    st.write("")
    with st.expander("퀴즈 그만두기", icon=":material/logout:"):
        st.caption("처음 화면으로 돌아갑니다. 진행 상황은 저장되어 나중에 이어 풀 수 있지만, 그동안에도 제한시간은 흘러갑니다.")
        home_button(ctx, "quiz_home")
