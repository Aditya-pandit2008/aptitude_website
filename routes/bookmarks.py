"""
routes/bookmarks.py
Bookmark (saved questions) blueprint.

Endpoints:
    GET    /api/v1/bookmarks/           – list all bookmarks for current user
    POST   /api/v1/bookmarks/           – save a question
    DELETE /api/v1/bookmarks/<id>       – remove a bookmark
    PUT    /api/v1/bookmarks/<id>       – update the note on a bookmark
"""

from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from sqlalchemy.exc import IntegrityError

from models import db, Bookmark, Question

bookmarks_bp = Blueprint("bookmarks", __name__)


@bookmarks_bp.route("/", methods=["GET"])
@jwt_required()
def list_bookmarks():
    """
    Return all bookmarked questions for the current user.

    Query params:
        page     (int, default 1)
        per_page (int, default 20, max 50)
    """
    user_id  = get_jwt_identity()
    page     = request.args.get("page", 1, type=int)
    per_page = min(request.args.get("per_page", 20, type=int), 50)

    paginated = (
        Bookmark.query
        .filter_by(user_id=user_id)
        .order_by(Bookmark.created_at.desc())
        .paginate(page=page, per_page=per_page, error_out=False)
    )

    return jsonify({
        "bookmarks": [b.to_dict() for b in paginated.items],
        "total": paginated.total,
        "page": paginated.page,
        "pages": paginated.pages,
    }), 200


@bookmarks_bp.route("/", methods=["POST"])
@jwt_required()
def save_bookmark():
    """
    Save a question to the user's bookmarks.

    Request body:
        question_id (int, required)
        note        (str, optional)
    """
    user_id = get_jwt_identity()
    data = request.get_json(silent=True) or {}

    question_id = data.get("question_id")
    if not question_id:
        return jsonify({"error": "question_id is required."}), 422

    # Verify question exists
    question = Question.query.filter_by(id=question_id, is_active=True).first()
    if not question:
        return jsonify({"error": "Question not found."}), 404

    bookmark = Bookmark(
        user_id=user_id,
        question_id=question_id,
        note=data.get("note"),
    )
    db.session.add(bookmark)

    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        return jsonify({"error": "Question already bookmarked."}), 409

    return jsonify({"message": "Question bookmarked.", "bookmark": bookmark.to_dict()}), 201


@bookmarks_bp.route("/<int:bookmark_id>", methods=["PUT"])
@jwt_required()
def update_bookmark(bookmark_id):
    """
    Update the personal note on a bookmark.

    Request body:
        note (str)
    """
    user_id  = get_jwt_identity()
    bookmark = Bookmark.query.filter_by(id=bookmark_id, user_id=user_id).first_or_404()
    data     = request.get_json(silent=True) or {}

    bookmark.note = data.get("note", bookmark.note)
    db.session.commit()

    return jsonify({"message": "Bookmark updated.", "bookmark": bookmark.to_dict()}), 200


@bookmarks_bp.route("/<int:bookmark_id>", methods=["DELETE"])
@jwt_required()
def remove_bookmark(bookmark_id):
    """Remove a bookmark. Users can only delete their own bookmarks."""
    user_id  = get_jwt_identity()
    bookmark = Bookmark.query.filter_by(id=bookmark_id, user_id=user_id).first_or_404()

    db.session.delete(bookmark)
    db.session.commit()

    return jsonify({"message": "Bookmark removed."}), 200
