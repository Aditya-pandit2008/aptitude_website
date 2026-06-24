import uuid
import time
from collections import deque, defaultdict
from typing import List, Dict, Any

# Adaptive difficulty tracking per user (last 10 outcomes)
_DIFFICULTY_HISTORY: defaultdict[str, deque] = defaultdict(lambda: deque(maxlen=10))

def record_outcome(user_id: str, correct: bool) -> None:
    """Record whether the user's answer was correct for difficulty adaptation."""
    _DIFFICULTY_HISTORY[user_id].append(correct)

def get_adaptive_difficulty(user_id: str, base: str | None = None) -> str:
    """Return an adjusted difficulty level based on recent performance.
    Levels: easy < medium < hard.
    If base is provided, start from it; otherwise default to 'medium'.
    """
    levels = ["easy", "medium", "hard"]
    cur = base if base in levels else "medium"
    hist = list(_DIFFICULTY_HISTORY[user_id])
    if hist:
        correct = sum(hist)
        if correct >= 8:
            cur = levels[min(levels.index(cur) + 1, 2)]
        elif correct <= 4:
            cur = levels[max(levels.index(cur) - 1, 0)]
    return cur

# Simple in‑memory quiz session store
_QUIZ_SESSIONS: dict[str, Dict[str, Any]] = {}

def create_quiz_session(user_id: str, questions: List[Dict[str, Any]]) -> str:
    session_id = str(uuid.uuid4())
    _QUIZ_SESSIONS[session_id] = {
        "user_id": user_id,
        "questions": questions,
        "answers": {},  # q_index -> answer
        "start": time.time(),
    }
    return session_id

def submit_quiz_answer(session_id: str, q_index: int, answer: Any) -> None:
    sess = _QUIZ_SESSIONS.get(session_id)
    if sess:
        sess["answers"][q_index] = answer

def finish_quiz_session(session_id: str) -> Dict[str, Any]:
    sess = _QUIZ_SESSIONS.pop(session_id, None)
    if not sess:
        return {}
    questions = sess["questions"]
    answers = sess["answers"]
    correct = 0
    results = []
    for idx, q in enumerate(questions):
        user_ans = answers.get(idx)
        is_correct = user_ans == q.get("correct_option")
        if is_correct:
            correct += 1
        results.append({"question_id": idx, "user_answer": user_ans, "correct": is_correct})
        # record outcome for adaptive difficulty
        record_outcome(str(sess["user_id"]), is_correct)
    score = correct / len(questions) if questions else 0
    return {"score": score, "total": len(questions), "correct": correct, "results": results}
