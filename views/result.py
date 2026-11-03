"""결과 화면 (F5): 점수, 등급, 맞힌 개수·소요 시간·시간 초과, 출처별 정답률, 이동 버튼."""

from __future__ import annotations

import random
import time

import altair as alt
import streamlit as st

from core import quiz_service
from core.models import QuestionBank, SessionMode, View
from core.storage import Storage
from views import components
from views.common import AppContext, flash, format_duration, home_button, navigate, safe_callback
from views.styles import TIMER_FILL


@safe_callback
def _on_retry_wrong(storage: Storage, bank: QuestionBank, uid: str) -> None:
    if quiz_service.retry_last_wrong(storage, bank, uid, time.time(), random.Random()) is None:
        flash("다시 풀 문제가 없습니다.", "warning")


def _source_chart(summary: quiz_service.ResultSummary) -> alt.Chart:
    """출처별 정답률 가로 막대그래프.

    '맞힌 수/문항 수 · 정답률'은 막대 끝 글자 대신 축 라벨에 넣는다.
    축 라벨은 라이트/다크 테마 색을 따르고, 100% 막대에서도 잘리지 않는다.
    """
    rows = []
    for source, (correct, total) in summary.by_source.items():
        rate = round(correct * 100 / total)
        rows.append({"항목": f"{source.label}  {correct}/{total} · {rate}%", "정답률": rate})
    return (
        alt.Chart(alt.Data(values=rows))
        .mark_bar(cornerRadiusEnd=6, height=22, color=TIMER_FILL)
        .encode(
            y=alt.Y("항목:N", sort=None, title=None, axis=alt.Axis(labelFontSize=14, labelLimit=240)),
            x=alt.X("정답률:Q", title="정답률 (%)", scale=alt.Scale(domain=[0, 100]), axis=alt.Axis(tickCount=5)),
            tooltip=[alt.Tooltip("항목:N", title="출처"), alt.Tooltip("정답률:Q", title="정답률(%)")],
        )
        .properties(height=max(120, 48 * len(rows)), padding={"right": 16})
    )


def render(ctx: AppContext) -> None:
    session = quiz_service.latest_finished_session(ctx.storage, ctx.user.uid)
    if session is None:  # reconcile에서 처음 화면으로 보내므로 보통 오지 않음
        home_button(ctx, "result_home_fallback")
        return

    summary = quiz_service.build_result(ctx.storage, ctx.bank, session)
    eyebrow = f"{components.TARGET_ICONS[session.target]} {session.target.label}"
    if session.mode is SessionMode.RETRY_WRONG:
        eyebrow += " · 오답 다시 풀기"
    components.hero(f"{session.target.label} 결과", "수고하셨습니다! 결과를 확인하고 틀린 문제를 복습해 보세요.", eyebrow=eyebrow)

    components.score_card(summary.score, summary.grade)

    col_correct, col_time, col_timeout = st.columns(3)
    col_correct.metric("맞힌 개수", f"{summary.correct_count} / {summary.total}", border=True)
    col_time.metric("소요 시간", format_duration(summary.duration_sec), border=True)
    col_timeout.metric("시간 초과", f"{summary.timeout_count}문항", border=True)

    st.subheader("출처별 정답률")
    if summary.by_source:
        st.altair_chart(_source_chart(summary), width="stretch")

    st.button(
        "오답노트 보기",
        key="result_wrong_notes",
        type="primary",
        icon=":material/menu_book:",
        width="stretch",
        on_click=navigate,
        args=(ctx.storage, ctx.user.uid, View.WRONG_NOTES, session.target),
    )
    st.button(
        "틀린 문제 다시 풀기" if summary.wrong_question_ids else "틀린 문제가 없어요",
        key="result_retry",
        icon=":material/replay:",
        width="stretch",
        disabled=not summary.wrong_question_ids,
        on_click=_on_retry_wrong,
        args=(ctx.storage, ctx.bank, ctx.user.uid),
    )
    home_button(ctx, "result_home")
