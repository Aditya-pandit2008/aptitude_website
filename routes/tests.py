"""
routes/tests.py
Aptitude test engine blueprint.

Endpoints:
    POST /api/v1/tests/submit       – submit answers and receive evaluation
    GET  /api/v1/tests/history      – list the user's past test attempts
    GET  /api/v1/tests/<id>         – get full details of a single attempt
    GET  /api/v1/tests/<id>/answers – per-question breakdown of an attempt
"""

from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity

from models import TestAttempt, TestAnswer
from services.evaluation import evaluate_test
from services.leaderboard_service import update_leaderboard
from utils.auth_utils import get_current_user
from utils.validators import validate_test_submission

tests_bp = Blueprint("tests", __name__)


@tests_bp.route("/submit", methods=["POST"])
@jwt_required()
def submit_test():
    """
    Submit a completed test for evaluation.

    Request body (JSON):
        {
            "answers": [
                {"question_id": 1, "selected_option": 2, "time_spent": 30},
                {"question_id": 2, "selected_option": null}   // null = skipped
            ],
            "time_taken":  180,       // total seconds (optional)
            "category_id": 1          // optional category tag
        }

    Returns:
        201 with attempt summary including score, accuracy, XP earned.
    """
    data = request.get_json(silent=True) or {}
    errors = validate_test_submission(data)
    if errors:
        return jsonify({"errors": errors}), 422

    user = get_current_user()
    if not user:
        return jsonify({"error": "User not found."}), 404

    result = evaluate_test(
        user=user,
        answers_payload=data["answers"],
        time_taken=data.get("time_taken", 0),
        category_id=data.get("category_id"),
    )

    # Refresh leaderboard asynchronously-like (same request, lightweight)
    update_leaderboard(user.id)

    return jsonify({
        "message": "Test submitted successfully.",
        "result": result,
    }), 201


@tests_bp.route("/history", methods=["GET"])
@jwt_required()
def get_history():
    """
    Return paginated test history for the current user.

    Query params:
        page     (int, default 1)
        per_page (int, default 10, max 50)
    """
    user_id  = get_jwt_identity()
    page     = request.args.get("page", 1, type=int)
    per_page = min(request.args.get("per_page", 10, type=int), 50)

    paginated = (
        TestAttempt.query
        .filter_by(user_id=user_id)
        .order_by(TestAttempt.completed_at.desc())
        .paginate(page=page, per_page=per_page, error_out=False)
    )

    return jsonify({
        "attempts": [a.to_dict() for a in paginated.items],
        "total": paginated.total,
        "page": paginated.page,
        "pages": paginated.pages,
    }), 200


@tests_bp.route("/<int:attempt_id>", methods=["GET"])
@jwt_required()
def get_attempt(attempt_id):
    """
    Return the summary of a specific test attempt.
    Users can only access their own attempts.
    """
    user_id = get_jwt_identity()
    attempt = TestAttempt.query.filter_by(id=attempt_id, user_id=user_id).first_or_404()
    return jsonify({"attempt": attempt.to_dict()}), 200


@tests_bp.route("/<int:attempt_id>/answers", methods=["GET"])
@jwt_required()
def get_attempt_answers(attempt_id):
    """
    Return per-question breakdown for a specific attempt.
    Includes correct answer, selected answer, and whether it was correct.
    """
    user_id = get_jwt_identity()
    attempt = TestAttempt.query.filter_by(id=attempt_id, user_id=user_id).first_or_404()

    answers = TestAnswer.query.filter_by(attempt_id=attempt_id).all()
    return jsonify({
        "attempt_id": attempt_id,
        "summary": attempt.to_dict(),
        "answers": [a.to_dict() for a in answers],
    }), 200
