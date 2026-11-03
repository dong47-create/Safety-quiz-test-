"""퀴즈 진행 로직: 회차 시작·답안 제출·시간 초과·다음 문제·종료·오답노트·복원 (PRD F1~F7).

화면(views)은 이 모듈의 함수만 호출한다. 모든 함수는 현재 시각(now, epoch 초)을 인자로 받는다.
각 함수는 DB에서 회차를 다시 읽어서 처리하므로, 탭을 여러 개 열어도 DB 상태가 기준이 된다.
"""

from __future__ import annotations

import random
import re
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone

from core.grading import calculate_score, grade_label, is_expired, is_timed_out, time_limit_for
from core.models import (
    Answer,
    Question,
    QuestionBank,
    QuizSession,
    SessionMode,
    SessionPhase,
    Source,
    Target,
    User,
    View,
    WrongNote,
)
from core.question_bank import QUIZ_SIZE, select_questions, shuffle_choices
from core.storage import Storage

LEARNING_CODE_PATTERN = re.compile(r"^[0-9a-f-]{8,36}$")


class StaleViewError(RuntimeError):
    """화면에 그려진 문항과 DB의 현재 문항이 다를 때. 같은 퀴즈가 다른 탭·기기에서 먼저 진행된 경우다."""

    def __init__(self, expected_question_id: str, current_question_id: str) -> None:
        super().__init__(f"화면의 문항 {expected_question_id} ≠ 현재 문항 {current_question_id}")
        self.expected_question_id = expected_question_id
        self.current_question_id = current_question_id


def _dt(now: float) -> datetime:
    return datetime.fromtimestamp(now, timezone.utc)


# ---------------------------------------------------------------------------
# 회차 조회
# ---------------------------------------------------------------------------

def current_question(bank: QuestionBank, session: QuizSession) -> Question:
    """회차의 현재 문항. 유효성은 reconcile에서 미리 확인한다."""
    question = bank.by_id(session.question_ids[session.current_index])
    if question is None:
        raise LookupError(f"문제은행에 없는 문항: {session.question_ids[session.current_index]}")
    return question


def is_session_valid(bank: QuestionBank, session: QuizSession) -> bool:
    """회차의 모든 문항이 문제은행에 있고, 저장된 보기 순서가 현재 보기와 일치하는지."""
    if not session.question_ids or not 0 <= session.current_index < len(session.question_ids):
        return False
    for qid in session.question_ids:
        question = bank.by_id(qid)
        if question is None:
            return False
        if sorted(session.choice_order.get(qid, [])) != sorted(c.id for c in question.choices):
            return False
    return True


def _last_normal_session(storage: Storage, uid: str, target: Target) -> QuizSession | None:
    sessions = storage.get_finished_sessions(uid, target=target)
    return next((s for s in sessions if s.mode is SessionMode.NORMAL), None)


def latest_finished_session(storage: Storage, uid: str) -> QuizSession | None:
    sessions = storage.get_finished_sessions(uid, limit=1)
    return sessions[0] if sessions else None


# ---------------------------------------------------------------------------
# 회차 시작·중단
# ---------------------------------------------------------------------------

def abandon_active_session(storage: Storage, uid: str) -> None:
    """진행 중인 회차를 버린다 (F1-3 '새로 시작'). 끝나지 않은 회차는 기록·오답노트에 남기지 않는다."""
    session = storage.get_active_session(uid)
    if session is not None:
        storage.delete_session(session.session_id)


def start_session(
    storage: Storage,
    bank: QuestionBank,
    uid: str,
    target: Target,
    now: float,
    rng: random.Random,
    mode: SessionMode = SessionMode.NORMAL,
    question_ids: list[str] | None = None,
) -> QuizSession | None:
    """새 회차를 만들고 퀴즈 화면으로 이동한다. 출제할 문항이 없으면 None.

    - NORMAL: 출처 비율대로 10문제, 직전 회차 문항은 가능하면 제외 (F2-1, F2-5)
    - RETRY_WRONG: question_ids 중 문제은행에 있는 것만 최대 10문제 (F5-5, F6-4)
    """
    if mode is SessionMode.NORMAL:
        last = _last_normal_session(storage, uid, target)
        exclude = set(last.question_ids) if last else set()
        questions = select_questions(bank, target, rng, exclude_ids=exclude)
    else:
        questions = [q for qid in dict.fromkeys(question_ids or []) if (q := bank.by_id(qid))]
        rng.shuffle(questions)
        questions = questions[:QUIZ_SIZE]

    if not questions:
        return None

    abandon_active_session(storage, uid)
    session = QuizSession(
        session_id=str(uuid.uuid4()),
        uid=uid,
        target=target,
        mode=mode,
        question_ids=[q.id for q in questions],
        choice_order={q.id: shuffle_choices(q, rng) for q in questions},
        current_index=0,
        phase=SessionPhase.ANSWERING,
        started_at=_dt(now),
        deadline_at=now + time_limit_for(questions[0]),
    )
    storage.save_session(session)
    storage.update_user_view(uid, View.QUIZ, target)
    return session


# ---------------------------------------------------------------------------
# 답안 제출·시간 초과
# ---------------------------------------------------------------------------

def _record_answer(
    storage: Storage,
    session: QuizSession,
    question: Question,
    selected: str | None,
    timed_out: bool,
    now: float,
) -> Answer:
    """답안을 저장하고 회차를 피드백 단계로 바꾼다. 이미 답이 있으면 기존 답을 돌려준다 (F4-4)."""
    limit = time_limit_for(question)
    question_started = (session.deadline_at or now) - limit
    answer = Answer(
        session_id=session.session_id,
        question_id=question.id,
        selected=None if timed_out else selected,
        is_correct=not timed_out and selected == question.answer,
        timed_out=timed_out,
        elapsed_sec=round(min(max(now - question_started, 0.0), float(limit)), 2),
        answered_at=_dt(now),
    )
    if not storage.save_answer(answer):
        answer = find_answer(storage, session.session_id, question.id) or answer

    session.phase = SessionPhase.FEEDBACK
    session.deadline_at = None  # 피드백 중에는 타이머 정지 (F3-6)
    storage.save_session(session)
    return answer


def submit_answer(
    storage: Storage,
    bank: QuestionBank,
    session_id: str,
    selected: str,
    now: float,
    *,
    expected_question_id: str,
) -> Answer | None:
    """사용자가 고른 답을 채점한다 (F4-1). 이미 답한 문항이거나 진행 중이 아니면 None (F4-4).

    expected_question_id는 사용자가 보고 있던(화면에 그려진) 문항이다. DB의 현재 문항과 다르면
    다른 탭·기기에서 이미 진행된 것이므로 StaleViewError를 낸다 (BUG-01).
    보기 ID(a~d, o/x)는 문항마다 같아서, 이 확인이 없으면 다른 문항에 답이 저장된다.

    서버 시간 기준으로 마감 + 2초가 지났으면 시간 초과로 처리한다 (F3-5).
    """
    session = storage.get_session(session_id)
    if session is None or session.is_finished:
        return None
    question = current_question(bank, session)
    if question.id != expected_question_id:
        raise StaleViewError(expected_question_id, question.id)
    if session.phase is not SessionPhase.ANSWERING:
        return None  # 같은 문항을 두 번 제출 (더블클릭 등)
    if question.choice_by_id(selected) is None:
        return None
    timed_out = session.deadline_at is not None and is_timed_out(session.deadline_at, now)
    return _record_answer(storage, session, question, selected, timed_out, now)


def mark_timeout(storage: Storage, bank: QuestionBank, session_id: str, now: float) -> Answer | None:
    """마감 시각이 지났으면 현재 문항을 시간 초과로 처리한다 (F3-3). 아직이면 None."""
    session = storage.get_session(session_id)
    if (
        session is None
        or session.is_finished
        or session.phase is not SessionPhase.ANSWERING
        or session.deadline_at is None
        or not is_expired(session.deadline_at, now)
    ):
        return None
    question = current_question(bank, session)
    return _record_answer(storage, session, question, None, True, now)


def find_answer(storage: Storage, session_id: str, question_id: str) -> Answer | None:
    return next((a for a in storage.get_answers(session_id) if a.question_id == question_id), None)


# ---------------------------------------------------------------------------
# 다음 문제·회차 종료
# ---------------------------------------------------------------------------

def go_next(
    storage: Storage, bank: QuestionBank, session_id: str, now: float, *, expected_question_id: str
) -> None:
    """피드백 화면에서 다음 문제로 이동한다. 마지막 문제였으면 회차를 끝낸다.

    expected_question_id는 사용자가 피드백을 보고 있던 문항이다.
    - 바로 다음 문제로 이미 넘어가 답하는 중이면 같은 탭의 더블클릭으로 보고 조용히 무시한다.
    - 그 밖에 DB의 현재 문항과 다르면 StaleViewError를 낸다. 다른 탭에서 진행된 문항을 건너뛰지 않게 한다 (BUG-01).
    """
    session = storage.get_session(session_id)
    if session is None or session.is_finished:
        return
    question = current_question(bank, session)
    if question.id != expected_question_id:
        previous_id = session.question_ids[session.current_index - 1] if session.current_index > 0 else None
        if session.phase is SessionPhase.ANSWERING and previous_id == expected_question_id:
            return
        raise StaleViewError(expected_question_id, question.id)
    if session.phase is not SessionPhase.FEEDBACK:
        return
    if session.current_index + 1 >= len(session.question_ids):
        finish_session(storage, bank, session, now)
        return
    session.current_index += 1
    session.phase = SessionPhase.ANSWERING
    session.deadline_at = now + time_limit_for(current_question(bank, session))
    storage.save_session(session)


def finish_session(storage: Storage, bank: QuestionBank, session: QuizSession, now: float) -> None:
    """점수를 매기고 오답노트를 갱신한 뒤 결과 화면으로 이동한다 (F5, F6-2, F6-4)."""
    answers = storage.get_answers(session.session_id)
    session.score = calculate_score(answers, len(session.question_ids))
    session.phase = SessionPhase.FINISHED
    session.finished_at = _dt(now)
    session.deadline_at = None
    storage.save_session(session)

    _update_wrong_notes(storage, bank, session, answers, now)
    storage.update_user_view(session.uid, View.RESULT, session.target)


def _update_wrong_notes(
    storage: Storage, bank: QuestionBank, session: QuizSession, answers: list[Answer], now: float
) -> None:
    """틀린 문항은 누적하고, 오답 다시 풀기에서 맞힌 문항은 학습 완료로 표시한다."""
    for answer in answers:
        question = bank.by_id(answer.question_id)
        existing = storage.get_wrong_note(session.uid, answer.question_id)
        if answer.is_correct:
            if existing and session.mode is SessionMode.RETRY_WRONG and not existing.mastered:
                existing.mastered = True
                storage.save_wrong_note(existing)
            continue

        target = existing.target if existing else (
            session.target if question is None or session.target in question.targets else question.targets[0]
        )
        storage.save_wrong_note(
            WrongNote(
                uid=session.uid,
                question_id=answer.question_id,
                target=target,
                last_selected=answer.selected,
                last_timed_out=answer.timed_out,
                last_wrong_at=_dt(now),
                wrong_count=(existing.wrong_count + 1) if existing else 1,
                mastered=False,
            )
        )


# ---------------------------------------------------------------------------
# 새로고침 복원 (F7-4, PRD 9장)
# ---------------------------------------------------------------------------

def reconcile(storage: Storage, bank: QuestionBank, user: User, now: float) -> tuple[User, list[str]]:
    """화면을 그리기 전에 DB 상태를 바로잡는다. (바뀐 사용자 정보, 사용자에게 보여줄 안내 문구)를 돌려준다.

    on_click 밖에서 상태를 바꾸는 유일한 곳이다. 새로고침·재접속 시점에 처리해야 하는 일만 한다.
    - 문제은행이 바뀌어 진행 중 회차의 문항이 없어졌으면 회차 종료
    - 진행 중 문항의 마감 시각이 지났으면 시간 초과 처리
    - 저장된 화면이 현재 상태와 맞지 않으면 처음 화면으로
    """
    messages: list[str] = []
    session = storage.get_active_session(user.uid)

    if session is not None and not is_session_valid(bank, session):
        storage.delete_session(session.session_id)
        session = None
        messages.append("문제은행이 바뀌어 진행 중이던 퀴즈를 종료했습니다. 다시 시작해 주세요.")

    if session is not None and session.phase is SessionPhase.ANSWERING:
        mark_timeout(storage, bank, session.session_id, now)

    view = user.view
    if (
        (view is View.QUIZ and session is None)
        or (view is View.RESULT and latest_finished_session(storage, user.uid) is None)
        or (view is View.GUIDE and user.selected_target is None)
    ):
        storage.update_user_view(user.uid, View.HOME, None)

    refreshed = storage.get_user(user.uid) or user
    return refreshed, messages


# ---------------------------------------------------------------------------
# 결과·통계 (F1-4, F5)
# ---------------------------------------------------------------------------

@dataclass
class ResultSummary:
    session: QuizSession
    answers: list[Answer]
    total: int
    correct_count: int
    score: int
    grade: str
    timeout_count: int
    duration_sec: float
    # 출처별 (맞힌 수, 출제 수)
    by_source: dict[Source, tuple[int, int]] = field(default_factory=dict)

    @property
    def wrong_question_ids(self) -> list[str]:
        return [a.question_id for a in self.answers if not a.is_correct]


def build_result(storage: Storage, bank: QuestionBank, session: QuizSession) -> ResultSummary:
    answers = storage.get_answers(session.session_id)
    by_source: dict[Source, tuple[int, int]] = {}
    answer_map = {a.question_id: a for a in answers}
    for qid in session.question_ids:
        question = bank.by_id(qid)
        if question is None:
            continue
        correct, total = by_source.get(question.source, (0, 0))
        answer = answer_map.get(qid)
        by_source[question.source] = (correct + int(bool(answer and answer.is_correct)), total + 1)

    score = session.score if session.score is not None else calculate_score(answers, len(session.question_ids))
    end = session.finished_at or session.started_at
    return ResultSummary(
        session=session,
        answers=answers,
        total=len(session.question_ids),
        correct_count=sum(1 for a in answers if a.is_correct),
        score=score,
        grade=grade_label(score),
        timeout_count=sum(1 for a in answers if a.timed_out),
        duration_sec=(end - session.started_at).total_seconds(),
        by_source={s: by_source[s] for s in Source if s in by_source},
    )


@dataclass
class TargetStats:
    count: int = 0
    best: int | None = None
    latest: int | None = None


def target_stats(storage: Storage, uid: str) -> dict[Target, TargetStats]:
    """대상자별 응시 횟수·최고 점수·최근 점수 (일반 회차만 집계, 오답 다시 풀기 제외)."""
    stats = {t: TargetStats() for t in Target}
    for session in storage.get_finished_sessions(uid):  # 최근 순
        if session.mode is not SessionMode.NORMAL or session.score is None:
            continue
        s = stats[session.target]
        s.count += 1
        s.best = session.score if s.best is None else max(s.best, session.score)
        if s.latest is None:
            s.latest = session.score
    return stats


# ---------------------------------------------------------------------------
# 오답 다시 풀기·오답노트 (F5-5, F6)
# ---------------------------------------------------------------------------

def retry_last_wrong(
    storage: Storage, bank: QuestionBank, uid: str, now: float, rng: random.Random
) -> QuizSession | None:
    """가장 최근 결과에서 틀린 문제만 다시 풀기."""
    last = latest_finished_session(storage, uid)
    if last is None:
        return None
    wrong_ids = build_result(storage, bank, last).wrong_question_ids
    return start_session(
        storage, bank, uid, last.target, now, rng, mode=SessionMode.RETRY_WRONG, question_ids=wrong_ids
    )


@dataclass
class WrongNoteEntry:
    note: WrongNote
    question: Question


def wrong_note_entries(
    storage: Storage,
    bank: QuestionBank,
    uid: str,
    target: Target | None = None,
    source: Source | None = None,
) -> list[WrongNoteEntry]:
    """화면에 보여줄 오답노트. 문제은행에서 사라진 문항은 숨긴다 (PRD 9장)."""
    entries: list[WrongNoteEntry] = []
    for note in storage.get_wrong_notes(uid):
        question = bank.by_id(note.question_id)
        if question is None:
            continue
        if target is not None and note.target is not target:
            continue
        if source is not None and question.source is not source:
            continue
        entries.append(WrongNoteEntry(note=note, question=question))
    return entries


def retry_wrong_notes(
    storage: Storage,
    bank: QuestionBank,
    uid: str,
    entries: list[WrongNoteEntry],
    fallback_target: Target,
    now: float,
    rng: random.Random,
) -> QuizSession | None:
    """오답노트에서 학습 완료가 아닌 문항만 모아 다시 풀기 (F6-4)."""
    pending = [e for e in entries if not e.note.mastered]
    if not pending:
        return None
    targets = {e.note.target for e in pending}
    target = targets.pop() if len(targets) == 1 else fallback_target
    return start_session(
        storage,
        bank,
        uid,
        target,
        now,
        rng,
        mode=SessionMode.RETRY_WRONG,
        question_ids=[e.question.id for e in pending],
    )


# ---------------------------------------------------------------------------
# 학습 코드 (F7-5)
# ---------------------------------------------------------------------------

def find_uid_by_code(storage: Storage, code: str) -> str | None:
    """학습 코드(uid 앞 8자리 이상)로 사용자 uid를 찾는다. 없거나 여러 명이면 None."""
    normalized = code.strip().lower()
    if not LEARNING_CODE_PATTERN.match(normalized):
        return None
    uids = storage.find_uids_by_prefix(normalized, limit=2)
    return uids[0] if len(uids) == 1 else None
