"""
routes/leaderboard.py
Leaderboard blueprint.

Endpoints:
    GET /api/v1/leaderboard/          – top-10 users
    GET /api/v1/leaderboard/me        – current user's rank
    GET /api/v1/leaderboard/top/<n>   – top-N users (max 50)
"""

from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity

from services import leaderboard_service

leaderboard_bp = Blueprint("leaderboard", __name__)


@leaderboard_bp.route("/", methods=["GET"])
@jwt_required()
def get_top_leaderboard():
    """Return the top-10 leaderboard entries."""
    timeframe = request.args.get("timeframe", "all_time").lower()
    entries = leaderboard_service.get_top_n_timebound(n=10, timeframe=timeframe)
    return jsonify({"leaderboard": entries, "count": len(entries), "timeframe": timeframe}), 200


@leaderboard_bp.route("/top/<int:n>", methods=["GET"])
@jwt_required()
def get_top_n(n):
    """
    Return the top-N leaderboard entries.
    N is capped at 50 to prevent abuse.
    """
    n = min(n, 50)
    timeframe = request.args.get("timeframe", "all_time").lower()
    entries = leaderboard_service.get_top_n_timebound(n=n, timeframe=timeframe)
    return jsonify({"leaderboard": entries, "count": len(entries), "timeframe": timeframe}), 200


@leaderboard_bp.route("/me", methods=["GET"])
@jwt_required()
def get_my_rank():
    """Return the current user's leaderboard rank and stats."""
    user_id = get_jwt_identity()
    timeframe = request.args.get("timeframe", "all_time").lower()
    entry = leaderboard_service.get_user_rank_timebound(int(user_id), timeframe=timeframe)
    if not entry:
        return jsonify({
            "message": "No leaderboard entry yet in this timeframe. Complete a test to appear.",
            "entry": None,
            "timeframe": timeframe,
        }), 200
    return jsonify({"entry": entry, "timeframe": timeframe}), 200
