"""
services/evaluation.py
Core test-evaluation service.

Responsibilities:
    - Grade submitted answers against correct options
    - Calculate score, accuracy, XP earned
    - Persist TestAttempt + TestAnswer rows
    - Update user XP and daily streak
"""

from datetime import date, timezone, datetime
from flask import current_app

from models import db, User, Question, TestAttempt, TestAnswer


def evaluate_test(user: User, answers_payload: list[dict], time_taken: int = 0,
                  category_id: int = None) -> dict:
    """
    Evaluate a submitted test and persist results.

    Args:
        user:            The authenticated User model instance.
        answers_payload: List of dicts with 'question_id' and 'selected_option'.
        time_taken:      Total time in seconds the user spent on the test.
        category_id:     Optional category to tag the attempt.

    Returns:
        dict with attempt summary (id, score, accuracy, xp_earned, …).
    """
    cfg = current_app.config

    total = len(answers_payload)
    correct_count = 0
    answer_rows = []

    for item in answers_payload:
        q_id = item.get("question_id")
        selected = item.get("selected_option")   # may be None (skipped)

        question = Question.query.filter_by(id=q_id, is_active=True).first()
        if not question:
            continue   # skip deleted/inactive questions silently

        is_correct = (selected is not None) and (selected == question.correct_option)
        if is_correct:
            correct_count += 1

        answer_rows.append(TestAnswer(
            question_id=q_id,
            selected_option=selected,
            is_correct=is_correct,
            time_spent=item.get("time_spent", 0),
        ))

    # ── Compute metrics ───────────────────────────────────────────────────────
    accuracy = (correct_count / total * 100) if total > 0 else 0.0
    xp_per_correct = cfg.get("XP_PER_CORRECT_ANSWER", 10)
    completion_xp = cfg.get("XP_PER_TEST_COMPLETION", 25)
    xp_earned = correct_count * xp_per_correct + completion_xp

    # ── Persist TestAttempt ───────────────────────────────────────────────────
    attempt = TestAttempt(
        user_id=user.id,
        category_id=category_id,
        total_questions=total,
        correct_answers=correct_count,
        score=float(correct_count * xp_per_correct),
        accuracy=accuracy,
        time_taken=time_taken,
        xp_earned=xp_earned,
    )
    db.session.add(attempt)
    db.session.flush()   # get attempt.id before committing

    for row in answer_rows:
        row.attempt_id = attempt.id
        db.session.add(row)

    # ── Update user XP and streak ─────────────────────────────────────────────
    _update_user_progress(user, xp_earned, cfg)

    db.session.commit()

    return attempt.to_dict()


def _update_user_progress(user: User, xp_earned: int, cfg):
    """
    Add XP to user and update daily streak.
    Streak increments if the user's last active date was yesterday;
    resets to 1 if it was more than 1 day ago; stays the same if already
    active today.
    """
    today = date.today()
    last = user.last_active_date

    if last is None or (today - last).days > 1:
        # First activity ever, or streak broken
        user.daily_streak = 1
    elif (today - last).days == 1:
        # Consecutive day
        user.daily_streak += 1
        xp_earned += cfg.get("XP_STREAK_BONUS", 5) * user.daily_streak
    # else: already active today — don't double-count streak

    user.last_active_date = today
    user.total_xp += xp_earned
