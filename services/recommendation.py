"""
services/recommendation.py
Recommendation engine: analyses past performance and suggests focus areas.

Algorithm:
    1. Aggregate per-category accuracy from the user's last N test attempts.
    2. Categories below the weak threshold → weak topics (need practice).
    3. Categories above the strong threshold → strong topics (maintain).
    4. Return ordered recommendation list with reasoning.
"""

from flask import current_app
from sqlalchemy import func

from models import db, TestAttempt, TestAnswer, Question, Category


_RECENT_ATTEMPTS = 10   # look-back window


def get_recommendations(user_id: int) -> dict:
    """
    Analyse the user's recent test performance and return topic recommendations.

    Args:
        user_id: The authenticated user's primary key.

    Returns:
        dict containing:
            weak_topics      – list of category dicts with low accuracy
            strong_topics    – list of category dicts with high accuracy
            recommended      – ordered practice list (weakest first)
            summary          – human-readable summary string
    """
    cfg = current_app.config
    threshold = cfg.get("PASSING_ACCURACY_THRESHOLD", 70)

    # ── Pull recent attempts ───────────────────────────────────────────────────
    recent_attempt_ids = (
        db.session.query(TestAttempt.id)
        .filter_by(user_id=user_id)
        .order_by(TestAttempt.completed_at.desc())
        .limit(_RECENT_ATTEMPTS)
        .subquery()
    )

    # ── Aggregate per-category accuracy via TestAnswer → Question → Category ──
    rows = (
        db.session.query(
            Category.id,
            Category.name,
            func.count(TestAnswer.id).label("total"),
            func.sum(TestAnswer.is_correct.cast(db.Integer)).label("correct"),
        )
        .join(Question, Question.id == TestAnswer.question_id)
        .join(Category, Category.id == Question.category_id)
        .filter(TestAnswer.attempt_id.in_(recent_attempt_ids))
        .group_by(Category.id, Category.name)
        .all()
    )

    if not rows:
        return _empty_recommendations()

    category_stats = []
    for row in rows:
        total = row.total or 0
        correct = int(row.correct or 0)
        accuracy = (correct / total * 100) if total else 0.0
        category_stats.append({
            "category_id": row.id,
            "category_name": row.name,
            "questions_attempted": total,
            "correct": correct,
            "accuracy": round(accuracy, 1),
        })

    # ── Classify ──────────────────────────────────────────────────────────────
    weak = [c for c in category_stats if c["accuracy"] < threshold]
    strong = [c for c in category_stats if c["accuracy"] >= threshold]

    # Sort weakest first for recommendations
    recommended = sorted(weak, key=lambda x: x["accuracy"])

    # If no weak areas, surface moderate topics
    if not recommended:
        recommended = sorted(category_stats, key=lambda x: x["accuracy"])

    summary = _build_summary(weak, strong, threshold)

    return {
        "weak_topics": weak,
        "strong_topics": strong,
        "recommended": recommended[:5],   # top-5 recommendations
        "summary": summary,
    }


def _build_summary(weak: list, strong: list, threshold: int) -> str:
    """Generate a plain-English performance summary."""
    if not weak and not strong:
        return "Not enough data yet. Complete a few more tests to see recommendations."
    parts = []
    if strong:
        names = ", ".join(c["category_name"] for c in strong[:3])
        parts.append(f"You're performing well in: {names}.")
    if weak:
        names = ", ".join(c["category_name"] for c in weak[:3])
        parts.append(f"Focus your practice on: {names} (below {threshold}% accuracy).")
    return " ".join(parts)


def _empty_recommendations() -> dict:
    return {
        "weak_topics": [],
        "strong_topics": [],
        "recommended": [],
        "summary": "No test history found. Start a test to get personalised recommendations.",
    }
