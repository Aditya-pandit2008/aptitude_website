"""
services/evaluation.py
Core test-evaluation service.

Responsibilities:
    - Grade submitted answers against correct options
    - Calculate score, accuracy, XP earned
    - Persist TestAttempt + TestAnswer rows
    - Update user XP and daily streak

Performance fix:
    Previous version called Question.query.filter_by(id=q_id).first() inside a
    loop — one DB hit per answer (N+1). Now all questions are bulk-fetched in a
    single query and looked up via an in-memory dict.
"""

from datetime import date
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

    # ── Bulk-fetch all referenced questions (single query) ────────────────────
    question_ids = [
        item["question_id"]
        for item in answers_payload
        if isinstance(item.get("question_id"), int)
    ]
    question_map: dict[int, Question] = {
        q.id: q
        for q in Question.query.filter(
            Question.id.in_(question_ids),
            Question.is_active == True,  # noqa: E712
        ).all()
    } if question_ids else {}

    total         = 0
    correct_count = 0
    answer_rows   = []

    for item in answers_payload:
        q_id     = item.get("question_id")
        selected = item.get("selected_option")   # may be None (skipped)

        question = question_map.get(q_id)
        if not question:
            continue   # skip deleted/inactive questions silently

        total     += 1
        question_type = question.question_type or "mcq"
        
        submitted_code = item.get("submitted_code")
        submitted_text = item.get("submitted_text")
        language = item.get("language")
        ai_feedback = None

        if question_type == "mcq":
            is_correct = (selected is not None) and (int(selected) == question.correct_option)
        elif question_type == "open_ended":
            from services.ai_service import evaluate_open_ended
            res = evaluate_open_ended(question.text, submitted_text or "")
            is_correct = res["is_correct"]
            ai_feedback = res["feedback"]
        elif question_type == "coding":
            from services.ai_service import evaluate_coding_challenge
            test_cases = question.code_challenge.test_cases if question.code_challenge else []
            res = evaluate_coding_challenge(question.text, submitted_code or "", test_cases)
            is_correct = res["is_correct"]
            ai_feedback = res["feedback"]
        else:
            is_correct = False

        if is_correct:
            correct_count += 1

        answer_rows.append(TestAnswer(
            question_id     = q_id,
            selected_option = selected,
            submitted_code  = submitted_code,
            submitted_text  = submitted_text,
            ai_feedback     = ai_feedback,
            language        = language,
            is_correct      = is_correct,
            time_spent      = int(item.get("time_spent") or 0),
        ))

    # ── Compute metrics ───────────────────────────────────────────────────────
    accuracy       = (correct_count / total * 100) if total > 0 else 0.0
    xp_per_correct = cfg.get("XP_PER_CORRECT_ANSWER", 10)
    completion_xp  = cfg.get("XP_PER_TEST_COMPLETION", 25)
    xp_earned      = correct_count * xp_per_correct + completion_xp

    # ── Persist TestAttempt ───────────────────────────────────────────────────
    current_skill = user.current_skill_level or 0.5
    if current_skill < 0.35:
        diff_level = "easy"
    elif current_skill <= 0.70:
        diff_level = "medium"
    else:
        diff_level = "hard"

    attempt = TestAttempt(
        user_id         = user.id,
        category_id     = category_id,
        total_questions = total,
        correct_answers = correct_count,
        score           = float(correct_count * xp_per_correct),
        accuracy        = accuracy,
        time_taken      = time_taken,
        xp_earned       = xp_earned,
        difficulty_level = diff_level,
    )
    db.session.add(attempt)
    db.session.flush()   # get attempt.id before committing

    for row in answer_rows:
        row.attempt_id = attempt.id
        db.session.add(row)

    # ── Update user XP, streak, and adaptive skill level ──────────────────────
    _update_user_progress(user, xp_earned, accuracy, cfg)
    check_and_grant_badges(user, attempt)

    db.session.commit()

    return attempt.to_dict()


def _update_user_progress(user: User, xp_earned: int, accuracy: float, cfg):
    """
    Add XP to user, update daily streak, and adjust adaptive skill level based on test accuracy.
    Streak increments if the user's last active date was yesterday;
    resets to 1 if it was more than 1 day ago; stays the same if already
    active today.
    """
    today = date.today()
    last  = user.last_active_date

    if last is None or (today - last).days > 1:
        # First activity ever, or streak broken
        user.daily_streak = 1
    elif (today - last).days == 1:
        # Consecutive day
        user.daily_streak += 1
        xp_earned += cfg.get("XP_STREAK_BONUS", 5) * user.daily_streak
    # else: already active today — don't double-count streak

    user.last_active_date = today
    user.total_xp        += xp_earned

    # Adaptive skill level update
    learning_rate = user.learning_rate or 0.1
    current_skill = user.current_skill_level or 0.5
    perf_factor = accuracy / 100.0
    new_skill = current_skill + learning_rate * (perf_factor - current_skill)
    user.current_skill_level = max(0.0, min(1.0, new_skill))


def check_and_grant_badges(user: User, attempt: TestAttempt = None):
    """Check user metrics and award any newly unlocked badges."""
    from models import db, Badge, UserBadge

    # Fetch currently earned badge IDs
    earned_badge_ids = {ub.badge_id for ub in user.badges.all()}

    # Check all badges
    all_badges = Badge.query.all()

    for badge in all_badges:
        if badge.id in earned_badge_ids:
            continue

        eligible = False
        if badge.badge_type == "streak":
            if user.daily_streak >= badge.threshold:
                eligible = True
        elif badge.badge_type == "xp":
            if user.total_xp >= badge.threshold:
                eligible = True
        elif badge.badge_type == "perfect_score":
            if attempt and attempt.total_questions > 0 and attempt.accuracy >= 100.0:
                eligible = True

        if eligible:
            ub = UserBadge(user_id=user.id, badge_id=badge.id)
            db.session.add(ub)

