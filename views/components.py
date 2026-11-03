"""화면 조각(HTML)을 만드는 도우미. 문항 내용은 반드시 escape해서 넣는다.

정답/오답/시간 초과는 색만이 아니라 기호(✓ ✗ ⏰)와 글자로도 구분한다 (색각 이상 사용자 배려).
"""

from __future__ import annotations

from html import escape

import streamlit as st

from core.models import Question, Source, Target

SOURCE_BADGE_COLORS: dict[Source, str] = {
    Source.ACT: "blue",
    Source.DECREE: "violet",
    Source.RULE: "green",
    Source.STANDARD: "orange",
}

TARGET_ICONS: dict[Target, str] = {
    Target.WORKER: "👷",
    Target.SUPERVISOR: "🦺",
    Target.MANAGER: "🏢",
}


def source_badge_markdown(source: Source) -> str:
    """출처 배지 마크다운 (출처마다 다른 색, 라이트/다크 자동 대응)."""
    return f":{SOURCE_BADGE_COLORS[source]}-badge[{source.label}]"


def hero(title: str, subtitle: str, eyebrow: str = "산업안전보건 학습") -> None:
    st.html(
        f'<div class="qz-hero"><p class="qz-eyebrow">{escape(eyebrow)}</p>'
        f"<h1>{escape(title)}</h1><p>{escape(subtitle)}</p></div>"
    )


def timer(remaining: float, limit: int, warning_seconds: int) -> None:
    seconds = max(0, int(-(-remaining // 1)))  # 올림
    percent = 0 if limit <= 0 else max(0.0, min(100.0, remaining / limit * 100))
    warn = seconds <= warning_seconds
    hint = '<span class="qz-timer-hint">서둘러 주세요!</span>' if warn and seconds > 0 else ""
    st.html(
        f'<div class="qz-timer{" warn" if warn else ""}">'
        f'<span class="qz-timer-label">⏱ 남은 시간</span>'
        f'<span class="qz-timer-num">{seconds}<small>초</small></span>'
        f'<div class="qz-timer-track" role="progressbar" aria-label="남은 시간" '
        f'aria-valuemin="0" aria-valuemax="{limit}" aria-valuenow="{seconds}">'
        f'<div class="qz-timer-fill" style="width:{percent:.1f}%"></div></div>{hint}</div>'
    )


def answer_review(question: Question, order: list[str], selected: str | None) -> None:
    """채점 후 모든 보기를 보여주며 정답과 내 답을 표시한다."""
    items = []
    for choice_id in order:
        choice = question.choice_by_id(choice_id)
        if choice is None:
            continue
        if choice_id == question.answer:
            cls, mark = "correct", "✓ 정답"
        elif choice_id == selected:
            cls, mark = "wrong", "✗ 내 답"
        else:
            cls, mark = "muted", ""
        items.append(
            f'<li class="{cls}"><span class="qz-mark">{mark}</span><span>{escape(choice.text)}</span></li>'
        )
    st.html(f'<ul class="qz-review">{"".join(items)}</ul>')


def reference(text: str) -> None:
    st.html(f'<div class="qz-ref"><b>📖 근거</b>{escape(text)}</div>')


def score_card(score: int, grade: str) -> None:
    grade_class = {"우수": "excellent", "양호": "good"}.get(grade, "retry")
    grade_icon = {"우수": "🏆", "양호": "👍"}.get(grade, "📚")
    st.html(
        f'<div class="qz-score"><div class="qz-score-num">{score}<small>점</small></div>'
        f'<span class="qz-grade {grade_class}">{grade_icon} {escape(grade)}</span></div>'
    )


def empty_state(icon: str, title: str, body: str) -> None:
    st.html(
        f'<div class="qz-empty"><div class="qz-empty-icon">{icon}</div>'
        f"<strong>{escape(title)}</strong><p>{escape(body)}</p></div>"
    )
