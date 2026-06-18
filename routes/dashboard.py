"""
routes/dashboard.py
Analytics dashboard blueprint.

Endpoints:
    GET /api/v1/dashboard/       – full analytics summary for current user
    GET /api/v1/dashboard/streak – current daily streak info
    GET /api/v1/dashboard/daily  – today's daily challenge

Performance:
    _get_category_breakdown is cached per user for 5 minutes using TTLCache
    to avoid running the heavy multi-join aggregation on every page load.
"""

from datetime import date
from flask import Blueprint
from flask_jwt_extended import jwt_required, get_jwt_identity
from sqlalchemy import func
from cachetools import TTLCache

from models import db, User, TestAttempt, TestAnswer, Question, Category, DailyChallenge
from services.recommendation import get_recommendations
from utils.response import success, error

dashboard_bp = Blueprint("dashboard", __name__)

# In-process cache: up to 512 users, 5-minute TTL per entry
_breakdown_cache: TTLCache = TTLCache(maxsize=512, ttl=300)


def invalidate_breakdown_cache(user_id: int):
    """
    Call this after a test is submitted to flush the cached breakdown
    for that user so the dashboard reflects fresh data immediately.
    """
    _breakdown_cache.pop(user_id, None)


@dashboard_bp.route("/", methods=["GET"])
@jwt_required()
def get_dashboard():
    """
    Return a comprehensive analytics summary for the authenticated user.

    Includes:
        - Total tests taken, total questions, overall accuracy
        - Total XP and current streak
        - Weak and strong topics (with recommendations)
        - Category-level accuracy breakdown (cached 5 min)
        - Recent 5 test attempts
    """
    user_id = int(get_jwt_identity())
    user    = db.session.get(User, user_id)
    if not user:
        return error("User not found.", 404)

    # ── Aggregate stats ────────────────────────────────────────────────────────
    agg = (
        db.session.query(
            func.count(TestAttempt.id).label("total_tests"),
            func.sum(TestAttempt.total_questions).label("total_questions"),
            func.sum(TestAttempt.correct_answers).label("total_correct"),
            func.avg(TestAttempt.accuracy).label("avg_accuracy"),
        )
        .filter_by(user_id=user_id)
        .first()
    )

    total_tests     = int(agg.total_tests or 0)
    total_questions = int(agg.total_questions or 0)
    total_correct   = int(agg.total_correct or 0)
    avg_accuracy    = round(float(agg.avg_accuracy or 0), 2)

    # ── Category breakdown (cached) ────────────────────────────────────────────
    category_breakdown = _get_category_breakdown_cached(user_id)

    # ── Recommendations ────────────────────────────────────────────────────────
    recommendations = get_recommendations(user_id)

    # ── Recent 5 attempts ─────────────────────────────────────────────────────
    recent_attempts = (
        TestAttempt.query
        .filter_by(user_id=user_id)
        .order_by(TestAttempt.completed_at.desc())
        .limit(5)
        .all()
    )

    return success({
        "user": {
            "id":           user.id,
            "username":     user.username,
            "total_xp":     user.total_xp,
            "daily_streak": user.daily_streak,
        },
        "stats": {
            "total_tests":             total_tests,
            "total_questions_solved":  total_questions,
            "total_correct":           total_correct,
            "accuracy_percentage":     avg_accuracy,
        },
        "category_breakdown": category_breakdown,
        "weak_topics":        recommendations["weak_topics"],
        "strong_topics":      recommendations["strong_topics"],
        "recommendations":    recommendations["recommended"],
        "recent_attempts":    [a.to_dict() for a in recent_attempts],
    }, 200)


@dashboard_bp.route("/streak", methods=["GET"])
@jwt_required()
def get_streak():
    """Return streak information and XP for the current user."""
    user_id = int(get_jwt_identity())
    user    = db.session.get(User, user_id)
    if not user:
        return error("User not found.", 404)

    today   = date.today()
    at_risk = (
        user.last_active_date is None or
        (today - user.last_active_date).days >= 1
    )

    return success({
        "daily_streak":   user.daily_streak,
        "last_active":    user.last_active_date.isoformat() if user.last_active_date else None,
        "streak_at_risk": at_risk and user.daily_streak > 0,
        "total_xp":       user.total_xp,
    }, 200)


@dashboard_bp.route("/daily", methods=["GET"])
@jwt_required()
def get_daily_challenge():
    """Return today's daily challenge question, if one exists."""
    today     = date.today()
    challenge = DailyChallenge.query.filter_by(challenge_date=today).first()
    if not challenge:
        return success({"message": "No daily challenge for today.", "challenge": None}, 200)
    return success({"challenge": challenge.to_dict()}, 200)


# ─────────────────────────────────────────────────────────────────────────────
# Private helpers
# ─────────────────────────────────────────────────────────────────────────────

def _get_category_breakdown_cached(user_id: int) -> list[dict]:
    """Wrapper that caches _get_category_breakdown results per user."""
    cached = _breakdown_cache.get(user_id)
    if cached is not None:
        return cached
    result = _get_category_breakdown(user_id)
    _breakdown_cache[user_id] = result
    return result


def _get_category_breakdown(user_id: int) -> list[dict]:
    """
    Compute per-category accuracy from the user's entire history.

    Returns:
        List of dicts: category_id, category_name, attempted, correct, accuracy.
    """
    rows = (
        db.session.query(
            Category.id,
            Category.name,
            func.count(TestAnswer.id).label("attempted"),
            func.sum(TestAnswer.is_correct.cast(db.Integer)).label("correct"),
        )
        .join(Question,     Question.id     == TestAnswer.question_id)
        .join(Category,     Category.id     == Question.category_id)
        .join(TestAttempt,  TestAttempt.id  == TestAnswer.attempt_id)
        .filter(TestAttempt.user_id == user_id)
        .group_by(Category.id, Category.name)
        .all()
    )

    return [
        {
            "category_id":   r.id,
            "category_name": r.name,
            "attempted":     r.attempted,
            "correct":       int(r.correct or 0),
            "accuracy":      round(
                (int(r.correct or 0) / r.attempted * 100) if r.attempted else 0, 1
            ),
        }
        for r in rows
    ]
