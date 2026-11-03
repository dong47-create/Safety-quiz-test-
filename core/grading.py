"""채점, 시간 초과 판정, 점수·등급 계산 (PRD F3, F5).

시간 관련 함수는 현재 시각(now)을 인자로 받아 sleep 없이 테스트할 수 있게 한다.
"""

from __future__ import annotations

import os

from core.models import Answer, Question, QuestionType

# 유형별 기본 제한시간(초) (F3-1)
DEFAULT_TIME_LIMITS: dict[QuestionType, int] = {
    QuestionType.MULTIPLE: 30,
    QuestionType.OX: 20,
}
# 마감 후 정상 제출로 인정하는 네트워크 지연 허용 시간(초) (F3-5)
GRACE_SECONDS = 2.0
TIME_LIMIT_OVERRIDE_ENV = "QUIZ_TIME_LIMIT_OVERRIDE"


def _time_limit_override() -> int | None:
    """테스트용 환경변수 QUIZ_TIME_LIMIT_OVERRIDE(초). 양의 정수가 아니면 무시한다."""
    raw = os.environ.get(TIME_LIMIT_OVERRIDE_ENV)
    if not raw:
        return None
    try:
        value = int(raw)
    except ValueError:
        return None
    return value if value > 0 else None


def time_limit_for(question: Question) -> int:
    """문항의 제한시간(초). 우선순위: 환경변수 → 문항의 time_limit → 유형별 기본값."""
    return _time_limit_override() or question.time_limit or DEFAULT_TIME_LIMITS[question.type]


def type_time_limit(question_type: QuestionType) -> int:
    """안내 화면에 보여줄 유형별 제한시간 (환경변수 반영)."""
    return _time_limit_override() or DEFAULT_TIME_LIMITS[question_type]


def is_expired(deadline_at: float, now: float) -> bool:
    """화면 타이머 기준으로 시간이 다 됐는지 (자동 시간 초과 처리에 사용)."""
    return now >= deadline_at


def is_timed_out(deadline_at: float, now: float) -> bool:
    """사용자가 제출한 답안이 시간 초과인지 (F3-5). 마감 후 GRACE_SECONDS까지는 인정한다."""
    return now > deadline_at + GRACE_SECONDS


def calculate_score(answers: list[Answer], total: int) -> int:
    """100점 만점 점수. 10문제면 문제당 10점이고, 문항이 적으면 비율로 환산한다."""
    if total <= 0:
        return 0
    correct = sum(1 for a in answers if a.is_correct)
    return round(correct * 100 / total)


def grade_label(score: int) -> str:
    """등급 (F5-2): 90 이상 우수 / 70 이상 양호 / 그 미만 재학습 필요."""
    if score >= 90:
        return "우수"
    if score >= 70:
        return "양호"
    return "재학습 필요"
