"""저장소 인터페이스와 SQLite 구현 (PRD 6.7, F7).

새로고침해도 데이터가 남도록 모든 상태는 DB에 저장한다.
PostgreSQL 구현은 3단계 배포 시 Storage 인터페이스에 맞춰 추가한다.
"""

from __future__ import annotations

import json
import os
import sqlite3
from abc import ABC, abstractmethod
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

from core.models import (
    Answer,
    QuizSession,
    SessionMode,
    SessionPhase,
    Target,
    User,
    View,
    WrongNote,
)

DEFAULT_DB_PATH = Path(__file__).resolve().parent.parent / "data" / "quiz.db"
HISTORY_LIMIT = 50


class StorageError(RuntimeError):
    """DB 연결·쿼리 실패. 화면에서는 안내 문구와 재시도 버튼으로 처리한다."""


def get_db_path() -> Path:
    """DB 파일 경로. 환경변수 QUIZ_DB_PATH가 있으면 그 값을 사용한다."""
    env_path = os.environ.get("QUIZ_DB_PATH")
    return Path(env_path) if env_path else DEFAULT_DB_PATH


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _to_text(value: datetime | None) -> str | None:
    return value.isoformat() if value else None


def _to_datetime(value: str | None) -> datetime | None:
    return datetime.fromisoformat(value) if value else None


class Storage(ABC):
    """저장소 인터페이스. SQLite / PostgreSQL 구현이 이 메서드를 모두 제공해야 한다."""

    # --- 사용자 ---
    @abstractmethod
    def create_user(self, uid: str) -> User: ...

    @abstractmethod
    def get_user(self, uid: str) -> User | None: ...

    @abstractmethod
    def touch_user(self, uid: str) -> None:
        """마지막 접속 시각 갱신."""

    @abstractmethod
    def update_user_view(self, uid: str, view: View, selected_target: Target | None) -> None:
        """현재 화면과 선택한 대상자 저장 (새로고침 복원용)."""

    @abstractmethod
    def delete_user_data(self, uid: str) -> None:
        """사용자의 모든 기록 삭제 (F7-7). 사용자 행 자체는 남기고 화면은 처음으로 되돌린다."""

    @abstractmethod
    def find_uids_by_prefix(self, prefix: str, limit: int = 2) -> list[str]:
        """학습 코드(uid 앞부분)로 사용자 찾기 (F7-5). prefix는 호출 전에 형식을 검증한다."""

    # --- 퀴즈 회차 ---
    @abstractmethod
    def save_session(self, session: QuizSession) -> None:
        """회차 저장 (없으면 추가, 있으면 갱신)."""

    @abstractmethod
    def get_session(self, session_id: str) -> QuizSession | None: ...

    @abstractmethod
    def delete_session(self, session_id: str) -> None:
        """회차와 그 답안 삭제 (중간에 그만둔 회차 정리용)."""

    @abstractmethod
    def get_active_session(self, uid: str) -> QuizSession | None:
        """진행 중(finished_at 없음)인 회차. 사용자당 최대 1개."""

    @abstractmethod
    def get_finished_sessions(
        self, uid: str, target: Target | None = None, limit: int = HISTORY_LIMIT
    ) -> list[QuizSession]:
        """완료된 회차 목록 (최근 순)."""

    # --- 답안 ---
    @abstractmethod
    def save_answer(self, answer: Answer) -> bool:
        """답안 저장. 같은 문항에 이미 답이 있으면 저장하지 않고 False (F4-4)."""

    @abstractmethod
    def get_answers(self, session_id: str) -> list[Answer]: ...

    # --- 오답노트 ---
    @abstractmethod
    def save_wrong_note(self, note: WrongNote) -> None:
        """오답노트 항목 저장 (없으면 추가, 있으면 덮어쓰기). 누적 계산은 호출하는 쪽에서 한다."""

    @abstractmethod
    def get_wrong_note(self, uid: str, question_id: str) -> WrongNote | None: ...

    @abstractmethod
    def get_wrong_notes(self, uid: str) -> list[WrongNote]:
        """오답노트 전체 (마지막으로 틀린 순)."""

    @abstractmethod
    def delete_wrong_note(self, uid: str, question_id: str) -> None: ...

    @abstractmethod
    def delete_all_wrong_notes(self, uid: str) -> None: ...


SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    uid              TEXT PRIMARY KEY,
    created_at       TEXT NOT NULL,
    last_seen        TEXT NOT NULL,
    view             TEXT NOT NULL DEFAULT 'home',
    selected_target  TEXT
);

CREATE TABLE IF NOT EXISTS quiz_sessions (
    session_id     TEXT PRIMARY KEY,
    uid            TEXT NOT NULL REFERENCES users(uid),
    target         TEXT NOT NULL,
    mode           TEXT NOT NULL,
    question_ids   TEXT NOT NULL,
    choice_order   TEXT NOT NULL,
    current_index  INTEGER NOT NULL,
    phase          TEXT NOT NULL,
    deadline_at    REAL,
    started_at     TEXT NOT NULL,
    finished_at    TEXT,
    score          INTEGER
);
CREATE INDEX IF NOT EXISTS idx_sessions_uid ON quiz_sessions(uid, finished_at);

CREATE TABLE IF NOT EXISTS answers (
    session_id   TEXT NOT NULL REFERENCES quiz_sessions(session_id),
    question_id  TEXT NOT NULL,
    selected     TEXT,
    is_correct   INTEGER NOT NULL,
    timed_out    INTEGER NOT NULL,
    elapsed_sec  REAL NOT NULL,
    answered_at  TEXT NOT NULL,
    PRIMARY KEY (session_id, question_id)
);

CREATE TABLE IF NOT EXISTS wrong_notes (
    uid             TEXT NOT NULL REFERENCES users(uid),
    question_id     TEXT NOT NULL,
    target          TEXT NOT NULL,
    wrong_count     INTEGER NOT NULL DEFAULT 1,
    last_selected   TEXT,
    last_timed_out  INTEGER NOT NULL,
    last_wrong_at   TEXT NOT NULL,
    mastered        INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (uid, question_id)
);
"""


class SQLiteStorage(Storage):
    """SQLite 저장소. Streamlit은 요청마다 다른 스레드에서 실행되므로 작업마다 새 연결을 연다."""

    def __init__(self, db_path: Path, create_schema: bool = True) -> None:
        self.db_path = db_path
        if create_schema:
            self.create_schema()

    def create_schema(self) -> None:
        """DB 파일과 테이블을 만든다 (이미 있으면 그대로 둔다)."""
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as conn:
            conn.executescript(SCHEMA)

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        """연결을 열고, 정상 종료 시 커밋·예외 시 롤백한 뒤 닫는다."""
        try:
            conn = sqlite3.connect(self.db_path, timeout=10)
        except sqlite3.Error as exc:
            raise StorageError(str(exc)) from exc
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        try:
            yield conn
            conn.commit()
        except sqlite3.IntegrityError:
            # 중복 제출 등 호출하는 쪽에서 처리하는 제약 위반은 그대로 전달
            conn.rollback()
            raise
        except sqlite3.Error as exc:
            conn.rollback()
            raise StorageError(str(exc)) from exc
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    # --- 행 → 모델 변환 ---
    @staticmethod
    def _row_to_user(row: sqlite3.Row) -> User:
        return User(
            uid=row["uid"],
            created_at=_to_datetime(row["created_at"]),
            last_seen=_to_datetime(row["last_seen"]),
            view=View(row["view"]),
            selected_target=Target(row["selected_target"]) if row["selected_target"] else None,
        )

    @staticmethod
    def _row_to_session(row: sqlite3.Row) -> QuizSession:
        return QuizSession(
            session_id=row["session_id"],
            uid=row["uid"],
            target=Target(row["target"]),
            mode=SessionMode(row["mode"]),
            question_ids=json.loads(row["question_ids"]),
            choice_order=json.loads(row["choice_order"]),
            current_index=row["current_index"],
            phase=SessionPhase(row["phase"]),
            started_at=_to_datetime(row["started_at"]),
            deadline_at=row["deadline_at"],
            finished_at=_to_datetime(row["finished_at"]),
            score=row["score"],
        )

    @staticmethod
    def _row_to_answer(row: sqlite3.Row) -> Answer:
        return Answer(
            session_id=row["session_id"],
            question_id=row["question_id"],
            selected=row["selected"],
            is_correct=bool(row["is_correct"]),
            timed_out=bool(row["timed_out"]),
            elapsed_sec=row["elapsed_sec"],
            answered_at=_to_datetime(row["answered_at"]),
        )

    @staticmethod
    def _row_to_wrong_note(row: sqlite3.Row) -> WrongNote:
        return WrongNote(
            uid=row["uid"],
            question_id=row["question_id"],
            target=Target(row["target"]),
            wrong_count=row["wrong_count"],
            last_selected=row["last_selected"],
            last_timed_out=bool(row["last_timed_out"]),
            last_wrong_at=_to_datetime(row["last_wrong_at"]),
            mastered=bool(row["mastered"]),
        )

    # --- 사용자 ---
    def create_user(self, uid: str) -> User:
        now = utc_now()
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO users (uid, created_at, last_seen, view) VALUES (?, ?, ?, ?)",
                (uid, _to_text(now), _to_text(now), View.HOME.value),
            )
        return User(uid=uid, created_at=now, last_seen=now)

    def get_user(self, uid: str) -> User | None:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM users WHERE uid = ?", (uid,)).fetchone()
        return self._row_to_user(row) if row else None

    def touch_user(self, uid: str) -> None:
        with self._connect() as conn:
            conn.execute("UPDATE users SET last_seen = ? WHERE uid = ?", (_to_text(utc_now()), uid))

    def update_user_view(self, uid: str, view: View, selected_target: Target | None) -> None:
        with self._connect() as conn:
            conn.execute(
                "UPDATE users SET view = ?, selected_target = ? WHERE uid = ?",
                (view.value, selected_target.value if selected_target else None, uid),
            )

    def delete_user_data(self, uid: str) -> None:
        with self._connect() as conn:
            conn.execute(
                "DELETE FROM answers WHERE session_id IN (SELECT session_id FROM quiz_sessions WHERE uid = ?)",
                (uid,),
            )
            conn.execute("DELETE FROM quiz_sessions WHERE uid = ?", (uid,))
            conn.execute("DELETE FROM wrong_notes WHERE uid = ?", (uid,))
            conn.execute(
                "UPDATE users SET view = ?, selected_target = NULL WHERE uid = ?",
                (View.HOME.value, uid),
            )

    def find_uids_by_prefix(self, prefix: str, limit: int = 2) -> list[str]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT uid FROM users WHERE uid LIKE ? ORDER BY uid LIMIT ?", (prefix + "%", limit)
            ).fetchall()
        return [r["uid"] for r in rows]

    # --- 퀴즈 회차 ---
    def delete_session(self, session_id: str) -> None:
        with self._connect() as conn:
            conn.execute("DELETE FROM answers WHERE session_id = ?", (session_id,))
            conn.execute("DELETE FROM quiz_sessions WHERE session_id = ?", (session_id,))

    def save_session(self, session: QuizSession) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO quiz_sessions (
                    session_id, uid, target, mode, question_ids, choice_order, current_index,
                    phase, deadline_at, started_at, finished_at, score
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(session_id) DO UPDATE SET
                    question_ids = excluded.question_ids,
                    choice_order = excluded.choice_order,
                    current_index = excluded.current_index,
                    phase = excluded.phase,
                    deadline_at = excluded.deadline_at,
                    finished_at = excluded.finished_at,
                    score = excluded.score
                """,
                (
                    session.session_id,
                    session.uid,
                    session.target.value,
                    session.mode.value,
                    json.dumps(session.question_ids),
                    json.dumps(session.choice_order),
                    session.current_index,
                    session.phase.value,
                    session.deadline_at,
                    _to_text(session.started_at),
                    _to_text(session.finished_at),
                    session.score,
                ),
            )

    def get_session(self, session_id: str) -> QuizSession | None:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM quiz_sessions WHERE session_id = ?", (session_id,)).fetchone()
        return self._row_to_session(row) if row else None

    def get_active_session(self, uid: str) -> QuizSession | None:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT * FROM quiz_sessions
                WHERE uid = ? AND finished_at IS NULL
                ORDER BY started_at DESC LIMIT 1
                """,
                (uid,),
            ).fetchone()
        return self._row_to_session(row) if row else None

    def get_finished_sessions(
        self, uid: str, target: Target | None = None, limit: int = HISTORY_LIMIT
    ) -> list[QuizSession]:
        sql = "SELECT * FROM quiz_sessions WHERE uid = ? AND finished_at IS NOT NULL"
        params: list[object] = [uid]
        if target is not None:
            sql += " AND target = ?"
            params.append(target.value)
        sql += " ORDER BY finished_at DESC LIMIT ?"
        params.append(limit)
        with self._connect() as conn:
            rows = conn.execute(sql, params).fetchall()
        return [self._row_to_session(r) for r in rows]

    # --- 답안 ---
    def save_answer(self, answer: Answer) -> bool:
        try:
            with self._connect() as conn:
                conn.execute(
                    """
                    INSERT INTO answers (
                        session_id, question_id, selected, is_correct, timed_out, elapsed_sec, answered_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        answer.session_id,
                        answer.question_id,
                        answer.selected,
                        int(answer.is_correct),
                        int(answer.timed_out),
                        answer.elapsed_sec,
                        _to_text(answer.answered_at),
                    ),
                )
        except sqlite3.IntegrityError:
            # 기본키 (session_id, question_id) 중복 = 이미 제출한 문항
            return False
        return True

    def get_answers(self, session_id: str) -> list[Answer]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM answers WHERE session_id = ? ORDER BY answered_at", (session_id,)
            ).fetchall()
        return [self._row_to_answer(r) for r in rows]

    # --- 오답노트 ---
    def save_wrong_note(self, note: WrongNote) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO wrong_notes (
                    uid, question_id, target, wrong_count, last_selected, last_timed_out, last_wrong_at, mastered
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(uid, question_id) DO UPDATE SET
                    target = excluded.target,
                    wrong_count = excluded.wrong_count,
                    last_selected = excluded.last_selected,
                    last_timed_out = excluded.last_timed_out,
                    last_wrong_at = excluded.last_wrong_at,
                    mastered = excluded.mastered
                """,
                (
                    note.uid,
                    note.question_id,
                    note.target.value,
                    note.wrong_count,
                    note.last_selected,
                    int(note.last_timed_out),
                    _to_text(note.last_wrong_at),
                    int(note.mastered),
                ),
            )

    def get_wrong_note(self, uid: str, question_id: str) -> WrongNote | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM wrong_notes WHERE uid = ? AND question_id = ?", (uid, question_id)
            ).fetchone()
        return self._row_to_wrong_note(row) if row else None

    def get_wrong_notes(self, uid: str) -> list[WrongNote]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM wrong_notes WHERE uid = ? ORDER BY last_wrong_at DESC", (uid,)
            ).fetchall()
        return [self._row_to_wrong_note(r) for r in rows]

    def delete_wrong_note(self, uid: str, question_id: str) -> None:
        with self._connect() as conn:
            conn.execute("DELETE FROM wrong_notes WHERE uid = ? AND question_id = ?", (uid, question_id))

    def delete_all_wrong_notes(self, uid: str) -> None:
        with self._connect() as conn:
            conn.execute("DELETE FROM wrong_notes WHERE uid = ?", (uid,))
