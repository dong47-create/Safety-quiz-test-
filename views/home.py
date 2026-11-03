"""시작 화면 (F1-1, F1-3, F1-4): 이어 풀기 배너, 대상자 카드, 대상자별 기록."""

from __future__ import annotations

from dataclasses import dataclass
from html import escape

import streamlit as st

from core import quiz_service
from core.models import Target, View
from views import components
from views.common import AppContext, abandon_quiz, navigate


@dataclass(frozen=True)
class TargetInfo:
    description: str
    topics: tuple[str, str, str]
    level: str


TARGET_INFO: dict[Target, TargetInfo] = {
    Target.WORKER: TargetInfo(
        "현장에서 직접 작업하는 근로자",
        ("근로자의 의무와 작업중지권", "보호구 지급과 착용", "근로자 안전보건교육"),
        "기초",
    ),
    Target.SUPERVISOR: TargetInfo(
        "작업을 직접 지휘·감독하는 부서장, 직장, 반장",
        ("관리감독자의 업무", "작업 전 점검과 위험성평가", "관리감독자 교육"),
        "중급",
    ),
    Target.MANAGER: TargetInfo(
        "사업장을 실질적으로 총괄 관리하는 사람",
        ("안전보건관리책임자의 업무", "산업안전보건위원회", "중대재해·산업재해 보고"),
        "고급",
    ),
}


def _render_resume_banner(ctx: AppContext) -> None:
    session = ctx.storage.get_active_session(ctx.user.uid)
    if session is None:
        return
    with st.container(border=True, key="resume_banner"):
        st.html(
            f'<p class="qz-resume-title">⏯ 풀던 퀴즈가 있어요</p>'
            f"<p>{escape(session.target.label)} · {session.current_index + 1}번 / 전체 {len(session.question_ids)}문제. "
            "그동안에도 제한시간은 흘러가요.</p>"
        )
        col_resume, col_new = st.columns(2)
        col_resume.button(
            "이어 풀기",
            key="resume_quiz",
            type="primary",
            icon=":material/play_arrow:",
            width="stretch",
            on_click=navigate,
            args=(ctx.storage, ctx.user.uid, View.QUIZ, session.target),
        )
        col_new.button(
            "그만두고 새로 시작",
            key="abandon_quiz",
            icon=":material/restart_alt:",
            width="stretch",
            on_click=abandon_quiz,
            args=(ctx.storage, ctx.user.uid),
        )


def _render_target_card(ctx: AppContext, target: Target, stat: quiz_service.TargetStats) -> None:
    info = TARGET_INFO[target]
    topics = "".join(f"<li>{escape(t)}</li>" for t in info.topics)
    if stat.count:
        stat_text = f"응시 {stat.count}회 · 최고 {stat.best}점 · 최근 {stat.latest}점"
    else:
        stat_text = "아직 응시 기록이 없어요"
    with st.container(border=True, key=f"target_card_{target.value}"):
        st.html(
            f'<div class="qz-card-icon" aria-hidden="true">{components.TARGET_ICONS[target]}</div>'
            f'<p class="qz-card-title">{escape(target.label)}</p>'
            f'<p class="qz-card-desc">{escape(info.description)}</p>'
            f'<ul class="qz-topics">{topics}</ul>'
            f'<span class="qz-level">난이도 {escape(info.level)}</span>'
            f'<p class="qz-stat">{escape(stat_text)}</p>'
        )
        st.button(
            f"{target.label} 선택",
            key=f"select_{target.value}",
            type="primary",
            width="stretch",
            on_click=navigate,
            args=(ctx.storage, ctx.user.uid, View.GUIDE, target),
        )


def render(ctx: AppContext) -> None:
    components.hero("안전보건 법령 퀴즈", "내 역할에 맞는 산업안전보건 법령 문제 10개를 풀고, 틀린 문제는 오답노트로 복습하세요.")
    _render_resume_banner(ctx)

    st.subheader("누구를 위한 퀴즈를 풀까요?")
    stats = quiz_service.target_stats(ctx.storage, ctx.user.uid)
    # 넓은 화면은 3열, 좁은 화면(640px 이하)은 Streamlit이 자동으로 1열로 쌓는다
    for column, target in zip(st.columns(3), Target):
        with column:
            _render_target_card(ctx, target, stats[target])
