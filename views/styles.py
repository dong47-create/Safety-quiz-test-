"""앱 전체 CSS. 한 번만 주입한다.

- Streamlit 내부 클래스(st-emotion-cache-...)에는 의존하지 않는다.
  data-testid, 컨테이너 key로 생기는 .st-key-<key> 클래스, 직접 만든 qz- 클래스만 사용한다.
- 색은 라이트/다크 모두에서 읽히도록 반투명 배경 + 글자색 상속(currentColor)을 기본으로 한다.
"""

from __future__ import annotations

import streamlit as st

# 의미 색 (라이트/다크 공통으로 대비가 충분한 중간 밝기)
ACCENT = "#F5B700"  # 강조 노랑
CORRECT = "#1F9D55"
WRONG = "#D64545"
TIMEOUT = "#E07B00"
TIMER_FILL = "#3B6FD8"

CSS = f"""
<style>
/* ---------- 공통 ---------- */
/* 위쪽은 사이드바 열기 버튼(») 영역에 가리지 않도록 여유를 둔다 */
.block-container {{ padding-top: 3.75rem; padding-bottom: 4rem; }}
p, li {{ font-size: 1rem; line-height: 1.65; }}

/* 버튼: 손가락으로 누르기 쉽게 (최소 48px) */
[data-testid^="stBaseButton"] {{ min-height: 3rem; font-size: 1.0625rem; font-weight: 600; }}

/* ---------- 상단 소개 ---------- */
.qz-hero {{ border-left: 6px solid {ACCENT}; padding: .25rem 0 .25rem 1rem; margin-bottom: 1rem; }}
.qz-hero h1 {{ margin: 0; padding: 0; font-size: 1.9rem; font-weight: 800; }}
.qz-hero p {{ margin: .35rem 0 0; opacity: .8; }}
.qz-eyebrow {{ font-size: .85rem; font-weight: 700; letter-spacing: .02em; color: {ACCENT}; margin: 0; }}

/* ---------- 대상자 카드 ---------- */
[class*="st-key-target_card_"] {{ height: 100%; }}
.qz-card-icon {{ font-size: 2rem; line-height: 1; }}
.qz-card-title {{ font-size: 1.2rem; font-weight: 800; margin: .5rem 0 .15rem; }}
.qz-card-desc {{ font-size: .9rem; opacity: .8; margin: 0 0 .6rem; min-height: 2.9em; }}
ul.qz-topics {{ margin: 0 0 .75rem !important; padding: 0 !important; list-style: none !important; min-height: 4.6em; }}
ul.qz-topics li {{ font-size: .9rem; padding-left: 1.1rem; margin: 0 0 .15rem !important; position: relative;
                  line-height: 1.5; list-style: none !important; }}
.qz-topics li::before {{ content: "•"; color: {ACCENT}; font-weight: 800; position: absolute; left: .2rem; }}
.qz-level {{ display: inline-block; font-size: .8rem; font-weight: 700; padding: .1rem .55rem;
            border-radius: 999px; border: 1px solid currentColor; opacity: .85; }}
.qz-stat {{ font-size: .85rem; opacity: .75; margin: .5rem 0 .25rem; min-height: 1.4em; }}

/* ---------- 이어 풀기 배너 ---------- */
.st-key-resume_banner {{ border: 2px solid {ACCENT} !important; background: rgba(245, 183, 0, .10); }}
.qz-resume-title {{ font-weight: 800; margin: 0; }}

/* ---------- 퀴즈 상단 ---------- */
.qz-quiz-meta {{ display: flex; justify-content: space-between; align-items: baseline; gap: .5rem; flex-wrap: wrap; }}
.qz-quiz-meta .qz-count {{ font-weight: 800; font-size: 1.05rem; }}
.qz-quiz-meta .qz-count small {{ opacity: .6; font-weight: 600; }}
.qz-question {{ font-size: 1.3rem; font-weight: 700; line-height: 1.55; margin: .5rem 0 1rem; word-break: keep-all; }}

/* ---------- 타이머 ---------- */
.qz-timer {{ display: flex; align-items: center; gap: .75rem; margin: .25rem 0 1rem; }}
.qz-timer-label {{ font-size: .85rem; font-weight: 700; opacity: .75; white-space: nowrap; }}
.qz-timer-num {{ font-size: 2rem; font-weight: 800; min-width: 3.4ch; text-align: right; font-variant-numeric: tabular-nums; }}
.qz-timer-num small {{ font-size: 1rem; font-weight: 700; margin-left: .1rem; }}
.qz-timer-track {{ flex: 1; height: .75rem; border-radius: 999px; background: rgba(128, 128, 128, .22); overflow: hidden; }}
.qz-timer-fill {{ height: 100%; border-radius: 999px; background: {TIMER_FILL}; transition: width .9s linear; }}
.qz-timer.warn .qz-timer-num {{ color: {WRONG}; }}
.qz-timer.warn .qz-timer-fill {{ background: {WRONG}; }}
.qz-timer-hint {{ font-size: .8rem; font-weight: 700; color: {WRONG}; }}

/* ---------- 보기 (라디오) ---------- */
/* Streamlit은 라디오 영역을 내용 폭에 맞추므로, 바깥 컨테이너부터 화면 폭으로 넓힌다 */
[data-testid="stElementContainer"]:has(> [data-testid="stRadio"]),
[data-testid="stRadio"] {{ width: 100% !important; }}
[data-testid="stRadio"] [role="radiogroup"] {{ gap: .6rem; width: 100%; align-items: stretch !important; }}
[data-testid="stRadio"] [role="radiogroup"] > label {{
    width: 100%; min-height: 3.25rem; margin: 0; padding: .75rem 1rem; box-sizing: border-box;
    border: 2px solid rgba(128, 128, 128, .30); border-radius: .75rem; align-items: center; cursor: pointer;
}}
[data-testid="stRadio"] [role="radiogroup"] > label:hover {{ border-color: rgba(128, 128, 128, .6); }}
[data-testid="stRadio"] [role="radiogroup"] > label:has(input:checked) {{
    border-color: {ACCENT}; background: rgba(245, 183, 0, .12);
}}
[data-testid="stRadio"] [role="radiogroup"] > label p {{ font-size: 1.0625rem; }}

/* ---------- 채점 후 보기 표시 ---------- */
ul.qz-review {{ list-style: none !important; margin: .75rem 0 1rem !important; padding: 0 !important; display: grid; gap: .5rem; }}
ul.qz-review li {{ margin: 0 !important; }}
.qz-review li {{ display: flex; gap: .6rem; align-items: flex-start; padding: .7rem 1rem;
                border: 2px solid rgba(128, 128, 128, .22); border-radius: .75rem; line-height: 1.5; }}
.qz-review .qz-mark {{ flex: none; font-weight: 800; min-width: 3.6rem; font-size: .85rem; padding-top: .1rem; }}
.qz-review li.correct {{ border-color: {CORRECT}; background: rgba(31, 157, 85, .10); }}
.qz-review li.correct .qz-mark {{ color: {CORRECT}; }}
.qz-review li.wrong {{ border-color: {WRONG}; background: rgba(214, 69, 69, .10); }}
.qz-review li.wrong .qz-mark {{ color: {WRONG}; }}
.qz-review li.muted {{ opacity: .65; }}

/* ---------- 근거 조문 인용 박스 ---------- */
.qz-ref {{ border-left: 4px solid {ACCENT}; background: rgba(128, 128, 128, .10);
          padding: .6rem .9rem; border-radius: 0 .5rem .5rem 0; margin: .5rem 0 1rem; font-size: .95rem; }}
.qz-ref b {{ margin-right: .35rem; }}

/* ---------- 결과 점수 ---------- */
.qz-score {{ text-align: center; padding: 1.5rem 1rem; border-radius: 1rem;
            border: 2px solid rgba(128, 128, 128, .22); margin-bottom: 1rem; }}
.qz-score-num {{ font-size: 4rem; font-weight: 800; line-height: 1.1; font-variant-numeric: tabular-nums; }}
.qz-score-num small {{ font-size: 1.5rem; margin-left: .15rem; }}
.qz-grade {{ display: inline-block; margin-top: .5rem; padding: .3rem 1rem; border-radius: 999px;
            font-weight: 800; border: 2px solid currentColor; }}
.qz-grade.excellent {{ color: {CORRECT}; }}
.qz-grade.good {{ color: {TIMER_FILL}; }}
.qz-grade.retry {{ color: {WRONG}; }}

/* ---------- 오답노트 ---------- */
.qz-summary-chips {{ display: flex; gap: .5rem; flex-wrap: wrap; margin: .25rem 0 1rem; }}
.qz-chip {{ padding: .3rem .8rem; border-radius: 999px; font-size: .9rem; font-weight: 700;
           background: rgba(128, 128, 128, .14); }}
.qz-chip.done {{ background: rgba(31, 157, 85, .14); }}
.qz-empty {{ text-align: center; padding: 2.5rem 1rem; border: 2px dashed rgba(128, 128, 128, .3);
            border-radius: 1rem; margin: 1rem 0; }}
.qz-empty .qz-empty-icon {{ font-size: 2.5rem; }}
.qz-empty p {{ margin: .4rem 0 0; opacity: .8; }}

/* ---------- 사이드바 ---------- */
.qz-code {{ font-family: ui-monospace, monospace; font-size: 1.6rem; font-weight: 800; letter-spacing: .12em; }}
.qz-side-note {{ font-size: .8rem; opacity: .75; line-height: 1.55; }}

/* ---------- 좁은 화면 (휴대폰) ---------- */
@media (max-width: 640px) {{
    .block-container {{ padding-left: 1rem; padding-right: 1rem; padding-top: 4rem; }}
    .qz-hero h1 {{ font-size: 1.5rem; }}
    .qz-question {{ font-size: 1.15rem; }}
    .qz-score-num {{ font-size: 3.25rem; }}
    .qz-card-desc {{ min-height: 0; }}
    .qz-timer-hint {{ display: none; }}
    .qz-timer-num {{ font-size: 1.6rem; }}
}}
.qz-timer-hint {{ white-space: nowrap; }}

/* 움직임 줄이기 설정을 존중 */
@media (prefers-reduced-motion: reduce) {{
    .qz-timer-fill {{ transition: none; }}
}}
</style>
"""


def inject_css() -> None:
    """앱 실행마다 한 번 호출한다. st.html은 style만 있는 경우 화면 공간을 차지하지 않는다."""
    st.html(CSS)
