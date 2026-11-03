"""오답노트 화면 (F6): 필터, 요약, 문항 카드, 다시 풀기, 삭제."""

from __future__ import annotations

import random
import time

import streamlit as st

from core import quiz_service
from core.models import QuestionBank, Source, Target
from core.storage import Storage
from views import components
from views.common import AppContext, flash, format_kst, home_button, safe_callback

ALL = "전체"


@safe_callback
def _on_delete_note(storage: Storage, uid: str, question_id: str) -> None:
    storage.delete_wrong_note(uid, question_id)
    flash("오답노트에서 삭제했습니다.", "success")


@safe_callback
def _on_delete_all_notes(storage: Storage, uid: str) -> None:
    storage.delete_all_wrong_notes(uid)
    flash("오답노트를 모두 삭제했습니다.", "success")


@safe_callback
def _on_retry(
    storage: Storage,
    bank: QuestionBank,
    uid: str,
    target: Target | None,
    source: Source | None,
    fallback_target: Target,
) -> None:
    entries = quiz_service.wrong_note_entries(storage, bank, uid, target, source)
    session = quiz_service.retry_wrong_notes(
        storage, bank, uid, entries, target or fallback_target, time.time(), random.Random()
    )
    if session is None:
        flash("다시 풀 문제가 없습니다. (학습 완료 문항은 제외됩니다)", "warning")


@st.dialog("오답노트 전체 삭제")
def _confirm_delete_all(storage: Storage, uid: str) -> None:
    st.write("오답노트를 모두 삭제할까요? 되돌릴 수 없습니다.")
    col_ok, col_cancel = st.columns(2)
    if col_ok.button("삭제", type="primary", width="stretch", on_click=_on_delete_all_notes, args=(storage, uid)):
        st.rerun()
    if col_cancel.button("취소", width="stretch"):
        st.rerun()


def _render_entry(ctx: AppContext, entry: quiz_service.WrongNoteEntry) -> None:
    note, question = entry.note, entry.question
    status = " · :green-badge[✓ 학습 완료]" if note.mastered else ""
    title = f"{components.source_badge_markdown(question.source)} {question.question}"
    with st.expander(title, icon=":material/check_circle:" if note.mastered else ":material/edit_note:"):
        st.markdown(
            f":gray-badge[{note.target.label}] :red-badge[틀린 횟수 {note.wrong_count}회]{status}  \n"
            f"마지막으로 틀린 날: {format_kst(note.last_wrong_at)}"
        )
        if note.last_timed_out or not note.last_selected:
            st.warning("지난번에는 **시간 초과**로 답을 내지 못했어요.", icon="⏰")
        components.answer_review(question, [c.id for c in question.choices], None if note.last_timed_out else note.last_selected)
        st.info(f"**해설**  \n{question.explanation}", icon=":material/lightbulb:")
        components.reference(question.reference)
        st.button(
            "이 문항 삭제",
            key=f"wn_delete_{question.id}",
            icon=":material/delete:",
            on_click=_on_delete_note,
            args=(ctx.storage, ctx.user.uid, question.id),
        )


def render(ctx: AppContext) -> None:
    components.hero("오답노트", "틀린 문제를 다시 확인하고, 다시 풀어서 맞히면 학습 완료로 표시됩니다.", eyebrow="📒 복습")

    col_target, col_source = st.columns(2)
    target_choice = col_target.selectbox(
        "대상자", [ALL, *Target], format_func=lambda t: t if t == ALL else t.label, key="wn_target"
    )
    source_choice = col_source.selectbox(
        "출처", [ALL, *Source], format_func=lambda s: s if s == ALL else s.label, key="wn_source"
    )
    target = None if target_choice == ALL else target_choice
    source = None if source_choice == ALL else source_choice

    entries = quiz_service.wrong_note_entries(ctx.storage, ctx.bank, ctx.user.uid, target, source)
    mastered = sum(1 for e in entries if e.note.mastered)
    st.html(
        '<div class="qz-summary-chips">'
        f'<span class="qz-chip">📒 오답 {len(entries)}개</span>'
        f'<span class="qz-chip done">✓ 학습 완료 {mastered}개</span>'
        f'<span class="qz-chip">남은 문제 {len(entries) - mastered}개</span>'
        "</div>"
    )

    if not entries:
        if target is None and source is None:
            components.empty_state("🎉", "아직 틀린 문제가 없어요", "퀴즈를 풀다가 틀린 문제는 여기에 자동으로 모입니다.")
        else:
            components.empty_state("🔍", "조건에 맞는 오답이 없어요", "대상자나 출처 필터를 바꿔 보세요.")
    else:
        fallback_target = ctx.user.selected_target or entries[0].note.target
        st.button(
            "오답 다시 풀기 (학습 완료 제외, 최대 10문제)",
            key="wn_retry",
            type="primary",
            icon=":material/replay:",
            width="stretch",
            disabled=len(entries) == mastered,
            on_click=_on_retry,
            args=(ctx.storage, ctx.bank, ctx.user.uid, target, source, fallback_target),
        )
        for entry in entries:
            _render_entry(ctx, entry)

    st.divider()
    if ctx.storage.get_wrong_notes(ctx.user.uid):
        if st.button("오답노트 전체 삭제", key="wn_delete_all", icon=":material/delete_sweep:", width="stretch"):
            _confirm_delete_all(ctx.storage, ctx.user.uid)
    home_button(ctx, "wrong_notes_home")
