"""앱 전반에서 사용하는 도메인 모델 (PRD 6.5, 6.7)."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum


class Target(str, Enum):
    """퀴즈 대상자."""

    WORKER = "worker"
    SUPERVISOR = "supervisor"
    MANAGER = "manager"

    @property
    def label(self) -> str:
        """화면에 표시할 한글 이름."""
        return TARGET_LABELS[self]


class Source(str, Enum):
    """문항의 출처 법령."""

    ACT = "act"
    DECREE = "decree"
    RULE = "rule"
    STANDARD = "standard"

    @property
    def label(self) -> str:
        """화면에 표시할 약칭 (PRD 3장)."""
        return SOURCE_LABELS[self]

    @property
    def full_name(self) -> str:
        """법령 정식 명칭."""
        return SOURCE_FULL_NAMES[self]


class QuestionType(str, Enum):
    """문항 유형."""

    MULTIPLE = "multiple"
    OX = "ox"

    @property
    def label(self) -> str:
        return QUESTION_TYPE_LABELS[self]


class View(str, Enum):
    """사용자가 현재 보고 있는 화면. 새로고침 복원을 위해 DB(users.view)에 저장한다."""

    HOME = "home"
    GUIDE = "guide"
    QUIZ = "quiz"
    RESULT = "result"
    WRONG_NOTES = "wrong_notes"


class SessionPhase(str, Enum):
    """퀴즈 회차 안에서의 진행 단계 (quiz_sessions.phase)."""

    ANSWERING = "answering"
    FEEDBACK = "feedback"
    FINISHED = "finished"


class SessionMode(str, Enum):
    """퀴즈 회차 종류."""

    NORMAL = "normal"
    RETRY_WRONG = "retry_wrong"


TARGET_LABELS: dict[Target, str] = {
    Target.WORKER: "작업자",
    Target.SUPERVISOR: "관리감독자",
    Target.MANAGER: "안전보건관리책임자",
}

SOURCE_LABELS: dict[Source, str] = {
    Source.ACT: "법",
    Source.DECREE: "시행령",
    Source.RULE: "시행규칙",
    Source.STANDARD: "안전보건규칙",
}

SOURCE_FULL_NAMES: dict[Source, str] = {
    Source.ACT: "산업안전보건법",
    Source.DECREE: "산업안전보건법 시행령",
    Source.RULE: "산업안전보건법 시행규칙",
    Source.STANDARD: "산업안전보건기준에 관한 규칙",
}

QUESTION_TYPE_LABELS: dict[QuestionType, str] = {
    QuestionType.MULTIPLE: "4지선다",
    QuestionType.OX: "O/X",
}


@dataclass(frozen=True)
class Choice:
    """문항의 보기 하나."""

    id: str
    text: str


@dataclass(frozen=True)
class Question:
    """문제은행의 문항 하나."""

    id: str
    targets: tuple[Target, ...]
    source: Source
    type: QuestionType
    question: str
    choices: tuple[Choice, ...]
    answer: str
    explanation: str
    reference: str
    difficulty: int = 1
    time_limit: int | None = None

    def choice_by_id(self, choice_id: str) -> Choice | None:
        """보기 ID로 보기를 찾는다. 없으면 None."""
        return next((c for c in self.choices if c.id == choice_id), None)


@dataclass
class User:
    """사용자 (URL의 uid로 구분)."""

    uid: str
    created_at: datetime
    last_seen: datetime
    view: View = View.HOME
    selected_target: Target | None = None

    @property
    def learning_code(self) -> str:
        """화면에 보여줄 학습 코드 (uid 앞 8자리)."""
        return self.uid[:8]


@dataclass
class QuizSession:
    """퀴즈 회차 하나 (진행 중 또는 완료)."""

    session_id: str
    uid: str
    target: Target
    mode: SessionMode
    question_ids: list[str]
    choice_order: dict[str, list[str]]
    current_index: int
    phase: SessionPhase
    started_at: datetime
    deadline_at: float | None = None
    finished_at: datetime | None = None
    score: int | None = None

    @property
    def is_finished(self) -> bool:
        return self.finished_at is not None


@dataclass
class Answer:
    """문항별 답안."""

    session_id: str
    question_id: str
    selected: str | None
    is_correct: bool
    timed_out: bool
    elapsed_sec: float
    answered_at: datetime


@dataclass
class WrongNote:
    """누적 오답노트 항목 (사용자 + 문항 기준으로 하나)."""

    uid: str
    question_id: str
    target: Target
    last_selected: str | None
    last_timed_out: bool
    last_wrong_at: datetime
    wrong_count: int = 1
    mastered: bool = False


@dataclass
class QuestionBank:
    """검증을 통과한 문항 목록과 메타 정보."""

    law_base_date: str
    questions: tuple[Question, ...]
    errors: list[str] = field(default_factory=list)

    def by_id(self, question_id: str) -> Question | None:
        return next((q for q in self.questions if q.id == question_id), None)

    def for_target(self, target: Target) -> list[Question]:
        """해당 대상자가 풀 수 있는 문항 목록."""
        return [q for q in self.questions if target in q.targets]
