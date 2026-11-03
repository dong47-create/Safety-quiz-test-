"""문제은행 로드·검증과 출제 (PRD 6.5, F2)."""

from __future__ import annotations

import json
import logging
import random
from pathlib import Path
from typing import Any

import streamlit as st

from core.models import Choice, Question, QuestionBank, QuestionType, Source, Target

logger = logging.getLogger(__name__)

QUESTIONS_PATH = Path(__file__).resolve().parent.parent / "data" / "questions.json"
QUIZ_SIZE = 10

# 대상자별 출제 비율 (PRD 3.1, 10문제 기준)
SOURCE_RATIOS: dict[Target, dict[Source, int]] = {
    Target.WORKER: {Source.ACT: 3, Source.DECREE: 1, Source.RULE: 2, Source.STANDARD: 4},
    Target.SUPERVISOR: {Source.ACT: 3, Source.DECREE: 2, Source.RULE: 2, Source.STANDARD: 3},
    Target.MANAGER: {Source.ACT: 4, Source.DECREE: 3, Source.RULE: 2, Source.STANDARD: 1},
}

REQUIRED_FIELDS = ("id", "targets", "source", "type", "question", "choices", "answer", "explanation", "reference")
OX_CHOICE_IDS = {"o", "x"}


class QuestionValidationError(ValueError):
    """문항 하나가 형식 검증을 통과하지 못했을 때 발생."""


def _parse_question(raw: Any) -> Question:
    """원본 dict 하나를 Question으로 변환한다. 형식이 잘못되면 QuestionValidationError."""
    if not isinstance(raw, dict):
        raise QuestionValidationError("문항이 객체 형식이 아닙니다")

    missing = [f for f in REQUIRED_FIELDS if raw.get(f) in (None, "", [])]
    if missing:
        raise QuestionValidationError(f"필수 항목 누락: {', '.join(missing)}")

    if not isinstance(raw["targets"], list):
        raise QuestionValidationError("targets는 배열이어야 합니다")
    try:
        targets = tuple(Target(t) for t in raw["targets"])
    except ValueError as exc:
        raise QuestionValidationError(f"잘못된 targets 값: {raw['targets']}") from exc

    try:
        source = Source(raw["source"])
    except ValueError as exc:
        raise QuestionValidationError(f"잘못된 source 값: {raw['source']}") from exc

    try:
        q_type = QuestionType(raw["type"])
    except ValueError as exc:
        raise QuestionValidationError(f"잘못된 type 값: {raw['type']}") from exc

    if not isinstance(raw["choices"], list):
        raise QuestionValidationError("choices는 배열이어야 합니다")
    try:
        choices = tuple(Choice(id=str(c["id"]), text=str(c["text"])) for c in raw["choices"])
    except (KeyError, TypeError) as exc:
        raise QuestionValidationError("보기에 id 또는 text가 없습니다") from exc

    choice_ids = [c.id for c in choices]
    if len(set(choice_ids)) != len(choice_ids):
        raise QuestionValidationError("보기 ID가 중복됩니다")
    if q_type is QuestionType.MULTIPLE and len(choices) < 2:
        raise QuestionValidationError("4지선다 문항은 보기가 2개 이상이어야 합니다")
    if q_type is QuestionType.OX and set(choice_ids) != OX_CHOICE_IDS:
        raise QuestionValidationError("O/X 문항의 보기 ID는 o, x 두 개여야 합니다")
    if raw["answer"] not in choice_ids:
        raise QuestionValidationError(f"정답 ID '{raw['answer']}'가 보기에 없습니다")

    difficulty = raw.get("difficulty", 1)
    if difficulty not in (1, 2, 3):
        raise QuestionValidationError("difficulty는 1~3이어야 합니다")

    time_limit = raw.get("time_limit")
    if time_limit is not None and (not isinstance(time_limit, int) or time_limit <= 0):
        raise QuestionValidationError("time_limit은 양의 정수여야 합니다")

    return Question(
        id=str(raw["id"]),
        targets=targets,
        source=source,
        type=q_type,
        question=str(raw["question"]),
        choices=choices,
        answer=str(raw["answer"]),
        explanation=str(raw["explanation"]),
        reference=str(raw["reference"]),
        difficulty=difficulty,
        time_limit=time_limit,
    )


def parse_question_bank(data: dict[str, Any]) -> QuestionBank:
    """JSON 데이터 전체를 검증해 QuestionBank로 만든다.

    잘못된 문항은 제외하고 errors에 사유를 남긴다. ID가 중복되면 먼저 나온 문항만 사용한다.
    """
    errors: list[str] = []
    questions: list[Question] = []
    seen_ids: set[str] = set()

    for index, raw in enumerate(data.get("questions", [])):
        label = raw.get("id", f"#{index}") if isinstance(raw, dict) else f"#{index}"
        try:
            question = _parse_question(raw)
        except QuestionValidationError as exc:
            errors.append(f"[{label}] {exc}")
            continue
        if question.id in seen_ids:
            errors.append(f"[{label}] 문항 ID가 중복됩니다")
            continue
        seen_ids.add(question.id)
        questions.append(question)

    for message in errors:
        logger.warning("문항 제외: %s", message)

    return QuestionBank(
        law_base_date=str(data.get("law_base_date", "미상")),
        questions=tuple(questions),
        errors=errors,
    )


def load_question_bank_file(path: Path) -> QuestionBank:
    """파일에서 문제은행을 읽어 검증한다."""
    with path.open(encoding="utf-8") as f:
        data = json.load(f)
    return parse_question_bank(data)


@st.cache_data(show_spinner=False)
def get_question_bank(path: str = str(QUESTIONS_PATH)) -> QuestionBank:
    """앱에서 사용하는 캐시된 문제은행. 파일은 한 번만 읽는다."""
    return load_question_bank_file(Path(path))


def select_questions(
    bank: QuestionBank,
    target: Target,
    rng: random.Random,
    exclude_ids: set[str] | None = None,
    size: int = QUIZ_SIZE,
) -> list[Question]:
    """대상자의 문항 중 출처 비율(SOURCE_RATIOS)에 맞춰 중복 없이 size개를 뽑는다 (F2-1, F2-5).

    - 부족한 출처는 같은 대상자의 다른 출처 문항으로 채운다.
    - exclude_ids(직전 회차 문항)는 가능하면 제외한다.
    - 문항이 size보다 적으면 있는 만큼만 반환한다.

    우선순위: ① 비율에 맞춘 새 문항 → ② 출처 무관 새 문항 → ③ 직전 회차 문항.
    """
    exclude_ids = exclude_ids or set()
    pool = bank.for_target(target)
    fresh = [q for q in pool if q.id not in exclude_ids]
    recent = [q for q in pool if q.id in exclude_ids]

    picked: list[Question] = []
    # ① 출처별 할당량만큼 새 문항에서 뽑기 (size가 10이 아니면 비율대로 환산)
    for source, ratio in SOURCE_RATIOS[target].items():
        quota = round(ratio * size / QUIZ_SIZE)
        candidates = [q for q in fresh if q.source is source]
        picked.extend(rng.sample(candidates, min(quota, len(candidates))))

    # ② 모자란 자리는 출처와 상관없이 남은 새 문항으로, ③ 그래도 모자라면 직전 회차 문항으로 채우기
    for leftovers in (fresh, recent):
        need = size - len(picked)
        if need <= 0:
            break
        remaining = [q for q in leftovers if q not in picked]
        picked.extend(rng.sample(remaining, min(need, len(remaining))))

    picked = picked[:size]
    rng.shuffle(picked)
    return picked


def shuffle_choices(question: Question, rng: random.Random) -> list[str]:
    """보기 ID 순서를 섞어 반환한다 (F2-2).

    O/X 문항은 섞으면 오히려 헷갈리므로 항상 O, X 순서로 둔다.
    """
    if question.type is QuestionType.OX:
        return ["o", "x"]
    order = [c.id for c in question.choices]
    rng.shuffle(order)
    return order
