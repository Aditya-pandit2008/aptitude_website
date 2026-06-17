"""
routes/profile.py
Profile and Settings blueprint.
"""
from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from sqlalchemy import func, desc

from models import db, User, TestAttempt, TestAnswer, Bookmark, LeaderboardEntry

profile_bp = Blueprint("profile", __name__)


@profile_bp.route("/", methods=["GET"])
@jwt_required()
def get_profile():
    user_id = int(get_jwt_identity())
    user = db.session.get(User, user_id)
    if not user:
        return jsonify({"error": "User not found"}), 404

    # Aggregate stats
    agg = db.session.query(
        func.count(TestAttempt.id).label("total_tests"),
        func.sum(TestAttempt.total_questions).label("total_questions"),
        func.sum(TestAttempt.correct_answers).label("total_correct"),
        func.avg(TestAttempt.accuracy).label("avg_accuracy"),
    ).filter_by(user_id=user_id).first()

    total_tests = int(agg.total_tests or 0)
    total_questions = int(agg.total_questions or 0)
    total_correct = int(agg.total_correct or 0)
    avg_accuracy = round(float(agg.avg_accuracy or 0), 1)
    total_incorrect = total_questions - total_correct

    # Bookmark count
    bookmarks_count = Bookmark.query.filter_by(user_id=user_id).count()

    # Leaderboard rank
    lb = LeaderboardEntry.query.filter_by(user_id=user_id).first()
    rank = lb.rank if lb else None

    # Recent 10 attempts
    recent = TestAttempt.query.filter_by(user_id=user_id)\
        .order_by(desc(TestAttempt.completed_at)).limit(10).all()

    return jsonify({
        "user": {
            "id": user.id,
            "username": user.username,
            "email": user.email,
            "role": user.role,
            "total_xp": user.total_xp,
            "daily_streak": user.daily_streak,
            "created_at": user.created_at.isoformat() if user.created_at else None,
        },
        "stats": {
            "total_tests": total_tests,
            "total_questions": total_questions,
            "total_correct": total_correct,
            "total_incorrect": total_incorrect,
            "avg_accuracy": avg_accuracy,
            "bookmarks_count": bookmarks_count,
            "rank": rank,
        },
        "recent_attempts": [a.to_dict() for a in recent],
    }), 200


@profile_bp.route("/settings", methods=["GET"])
@jwt_required()
def get_settings():
    user_id = int(get_jwt_identity())
    user = db.session.get(User, user_id)
    if not user:
        return jsonify({"error": "User not found"}), 404
    return jsonify({
        "user": {
            "id": user.id,
            "username": user.username,
            "email": user.email,
            "role": user.role,
        }
    }), 200


@profile_bp.route("/settings", methods=["PUT"])
@jwt_required()
def update_settings():
    user_id = int(get_jwt_identity())
    user = db.session.get(User, user_id)
    if not user:
        return jsonify({"error": "User not found"}), 404

    data = request.get_json(silent=True) or {}

    if "username" in data:
        new_username = data["username"].strip()
        if len(new_username) < 3:
            return jsonify({"error": "Username must be at least 3 characters"}), 422
        existing = User.query.filter_by(username=new_username).first()
        if existing and existing.id != user.id:
            return jsonify({"error": "Username already taken"}), 409
        user.username = new_username

    if "new_password" in data:
        if not data.get("old_password"):
            return jsonify({"error": "old_password is required to change password"}), 422
        if not user.check_password(data["old_password"]):
            return jsonify({"error": "Current password is incorrect"}), 401
        if len(data["new_password"]) < 8:
            return jsonify({"error": "New password must be at least 8 characters"}), 422
        user.set_password(data["new_password"])

    try:
        db.session.commit()
        return jsonify({"message": "Settings updated successfully", "user": {
            "id": user.id,
            "username": user.username,
            "email": user.email,
        }}), 200
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": str(e)}), 500


@profile_bp.route("/data-export", methods=["GET"])
@jwt_required()
def export_data():
    """Export user's data as JSON."""
    user_id = int(get_jwt_identity())
    user = db.session.get(User, user_id)
    if not user:
        return jsonify({"error": "User not found"}), 404

    attempts = TestAttempt.query.filter_by(user_id=user_id).all()
    bookmarks = Bookmark.query.filter_by(user_id=user_id).all()

    return jsonify({
        "exported_at": __import__('datetime').datetime.utcnow().isoformat(),
        "user": {
            "username": user.username,
            "email": user.email,
            "total_xp": user.total_xp,
            "daily_streak": user.daily_streak,
            "joined": user.created_at.isoformat() if user.created_at else None,
        },
        "test_attempts": [a.to_dict() for a in attempts],
        "bookmarks_count": len(bookmarks),
    }), 200
