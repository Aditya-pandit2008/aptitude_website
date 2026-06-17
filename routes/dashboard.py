"""
routes/dashboard.py
Analytics dashboard blueprint.

Endpoints:
    GET /api/v1/dashboard/           – full analytics summary for current user
    GET /api/v1/dashboard/streak     – current daily streak info
    GET /api/v1/dashboard/daily      – today's daily challenge
"""

from datetime import date, timedelta
from flask import Blueprint, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from sqlalchemy import func

from models import db, User, TestAttempt, TestAnswer, Question, Category, DailyChallenge
from services.recommendation import get_recommendations

dashboard_bp = Blueprint("dashboard", __name__)


@dashboard_bp.route("/", methods=["GET"])
@jwt_required()
def get_dashboard():
    """
    Return a comprehensive analytics summary for the authenticated user.

    Includes:
        - Total tests taken
        - Total questions answered
        - Overall accuracy percentage
        - Total XP and current streak
        - Weak and strong topics
        - Topic-level breakdown
        - Recent 5 test attempts
    """
    user_id = get_jwt_identity()
    user = db.session.get(User, user_id)
    if not user:
        return jsonify({"error": "User not found."}), 404

    # ── Aggregate stats from all test attempts ─────────────────────────────
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

    # ── Category-level accuracy breakdown ─────────────────────────────────
    category_breakdown = _get_category_breakdown(user_id)

    # ── Recommendations (weak / strong topics) ─────────────────────────────
    recommendations = get_recommendations(user_id)

    # ── Recent 5 attempts ─────────────────────────────────────────────────
    recent_attempts = (
        TestAttempt.query
        .filter_by(user_id=user_id)
        .order_by(TestAttempt.completed_at.desc())
        .limit(5)
        .all()
    )

    return jsonify({
        "user": {
            "id": user.id,
            "username": user.username,
            "total_xp": user.total_xp,
            "daily_streak": user.daily_streak,
        },
        "stats": {
            "total_tests": total_tests,
            "total_questions_solved": total_questions,
            "total_correct": total_correct,
            "accuracy_percentage": avg_accuracy,
        },
        "category_breakdown": category_breakdown,
        "weak_topics": recommendations["weak_topics"],
        "strong_topics": recommendations["strong_topics"],
        "recommendations": recommendations["recommended"],
        "recent_attempts": [a.to_dict() for a in recent_attempts],
    }), 200


@dashboard_bp.route("/streak", methods=["GET"])
@jwt_required()
def get_streak():
    """Return streak information and XP for the current user."""
    user_id = get_jwt_identity()
    user = db.session.get(User, user_id)
    if not user:
        return jsonify({"error": "User not found."}), 404

    # Determine if the streak is at risk (no activity today)
    today = date.today()
    at_risk = (
        user.last_active_date is None or
        (today - user.last_active_date).days >= 1
    )

    return jsonify({
        "daily_streak": user.daily_streak,
        "last_active": user.last_active_date.isoformat() if user.last_active_date else None,
        "streak_at_risk": at_risk and user.daily_streak > 0,
        "total_xp": user.total_xp,
    }), 200


@dashboard_bp.route("/daily", methods=["GET"])
@jwt_required()
def get_daily_challenge():
    """Return today's daily challenge question, if one exists."""
    today = date.today()
    challenge = DailyChallenge.query.filter_by(challenge_date=today).first()
    if not challenge:
        return jsonify({"message": "No daily challenge for today.", "challenge": None}), 200
    return jsonify({"challenge": challenge.to_dict()}), 200


# ─────────────────────────────────────────────────────────────────────────────
# Private helpers
# ─────────────────────────────────────────────────────────────────────────────

def _get_category_breakdown(user_id: int) -> list[dict]:
    """
    Compute per-category accuracy from the user's entire history.

    Returns:
        List of dicts with category_id, category_name, attempted, correct, accuracy.
    """
    rows = (
        db.session.query(
            Category.id,
            Category.name,
            func.count(TestAnswer.id).label("attempted"),
            func.sum(TestAnswer.is_correct.cast(db.Integer)).label("correct"),
        )
        .join(Question, Question.id == TestAnswer.question_id)
        .join(Category, Category.id == Question.category_id)
        .join(TestAttempt, TestAttempt.id == TestAnswer.attempt_id)
        .filter(TestAttempt.user_id == user_id)
        .group_by(Category.id, Category.name)
        .all()
    )

    return [
        {
            "category_id": r.id,
            "category_name": r.name,
            "attempted": r.attempted,
            "correct": int(r.correct or 0),
            "accuracy": round((int(r.correct or 0) / r.attempted * 100) if r.attempted else 0, 1),
        }
        for r in rows
    ]
