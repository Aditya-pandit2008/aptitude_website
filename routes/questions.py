"""
routes/questions.py
Question management blueprint.

Endpoints:
    GET    /api/v1/questions/               – list questions (filterable)
    POST   /api/v1/questions/               – add a question (admin)
    GET    /api/v1/questions/<id>           – get single question
    PUT    /api/v1/questions/<id>           – update question (admin)
    DELETE /api/v1/questions/<id>           – soft-delete question (admin)
    GET    /api/v1/questions/categories     – list all categories
    POST   /api/v1/questions/categories     – create a category (admin)
    GET    /api/v1/questions/random         – fetch random questions for a test
"""

from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity

from models import db, Question, Category
from utils.auth_utils import admin_required
from utils.validators import validate_question

questions_bp = Blueprint("questions", __name__)


# ─────────────────────────────────────────────────────────────────────────────
# Category routes
# ─────────────────────────────────────────────────────────────────────────────

@questions_bp.route("/categories", methods=["GET"])
def list_categories():
    """Return all active categories with question counts."""
    categories = Category.query.all()
    return jsonify({"categories": [c.to_dict() for c in categories]}), 200


@questions_bp.route("/categories", methods=["POST"])
@admin_required
def create_category():
    """
    Create a new category.
    Admin only.

    Request body: {name, description?, icon?}
    """
    data = request.get_json(silent=True) or {}
    name = (data.get("name") or "").strip()
    if not name:
        return jsonify({"error": "Category name is required."}), 422

    if Category.query.filter_by(name=name).first():
        return jsonify({"error": "Category already exists."}), 409

    category = Category(
        name=name,
        description=data.get("description"),
        icon=data.get("icon"),
    )
    db.session.add(category)
    db.session.commit()
    return jsonify({"message": "Category created.", "category": category.to_dict()}), 201


# ─────────────────────────────────────────────────────────────────────────────
# Question CRUD
# ─────────────────────────────────────────────────────────────────────────────

@questions_bp.route("/", methods=["GET"])
@jwt_required()
def list_questions():
    """
    List questions with optional filters.

    Query params:
        category_id (int)
        difficulty  (easy|medium|hard)
        page        (int, default 1)
        per_page    (int, default 20, max 100)
        search      (str) – substring match on question text
    """
    category_id = request.args.get("category_id", type=int)
    difficulty   = request.args.get("difficulty")
    search       = request.args.get("search", "")
    page         = request.args.get("page", 1, type=int)
    per_page     = min(request.args.get("per_page", 20, type=int), 100)

    q = Question.query.filter_by(is_active=True)

    if category_id:
        q = q.filter_by(category_id=category_id)
    if difficulty:
        q = q.filter_by(difficulty=difficulty)
    if search:
        q = q.filter(Question.text.ilike(f"%{search}%"))

    paginated = q.order_by(Question.id.desc()).paginate(
        page=page, per_page=per_page, error_out=False
    )

    return jsonify({
        "questions": [question.to_dict() for question in paginated.items],
        "total": paginated.total,
        "page": paginated.page,
        "pages": paginated.pages,
        "per_page": per_page,
    }), 200


@questions_bp.route("/random", methods=["GET"])
@jwt_required()
def get_random_questions():
    """
    Fetch a random set of questions (used to start a test).

    Query params:
        category_id (int)          – filter by category (optional)
        difficulty  (str)          – filter by difficulty (optional)
        count       (int, 1-50)    – number of questions, default 10
    """
    from sqlalchemy.sql.expression import func as sql_func

    category_id = request.args.get("category_id", type=int)
    difficulty   = request.args.get("difficulty")
    count        = min(request.args.get("count", 10, type=int), 50)

    q = Question.query.filter_by(is_active=True)
    if category_id:
        q = q.filter_by(category_id=category_id)
    if difficulty:
        q = q.filter_by(difficulty=difficulty)

    questions = q.order_by(sql_func.random()).limit(count).all()
    return jsonify({"questions": [question.to_dict() for question in questions],
                    "count": len(questions)}), 200


@questions_bp.route("/<int:question_id>", methods=["GET"])
@jwt_required()
def get_question(question_id):
    """Return a single question by ID (without revealing the correct answer)."""
    question = Question.query.filter_by(id=question_id, is_active=True).first_or_404()
    return jsonify({"question": question.to_dict()}), 200


@questions_bp.route("/", methods=["POST"])
@admin_required
def create_question():
    """
    Add a new question.
    Admin only.

    Request body:
        {
            category_id, text, options (list), correct_option (int),
            difficulty?, explanation?, tags?
        }
    """
    data = request.get_json(silent=True) or {}
    errors = validate_question(data)
    if errors:
        return jsonify({"errors": errors}), 422

    category = db.session.get(Category, data["category_id"])
    if not category:
        return jsonify({"error": "Category not found."}), 404

    user_id = get_jwt_identity()
    question = Question(
        category_id=data["category_id"],
        text=data["text"].strip(),
        correct_option=data["correct_option"],
        explanation=data.get("explanation"),
        difficulty=data.get("difficulty", "medium"),
        tags=",".join(data["tags"]) if isinstance(data.get("tags"), list) else data.get("tags", ""),
        created_by=user_id,
    )
    question.options = data["options"]

    db.session.add(question)
    db.session.commit()
    return jsonify({"message": "Question created.", "question": question.to_dict(include_answer=True)}), 201


@questions_bp.route("/<int:question_id>", methods=["PUT"])
@admin_required
def update_question(question_id):
    """
    Update an existing question (partial update supported).
    Admin only.
    """
    question = db.session.get(Question, question_id)
    if not question:
        return jsonify({"error": "Question not found."}), 404
    data = request.get_json(silent=True) or {}

    if "text" in data:
        question.text = data["text"].strip()
    if "options" in data:
        question.options = data["options"]
    if "correct_option" in data:
        question.correct_option = data["correct_option"]
    if "explanation" in data:
        question.explanation = data["explanation"]
    if "difficulty" in data:
        if data["difficulty"] not in Question.DIFFICULTY_LEVELS:
            return jsonify({"error": f"Invalid difficulty. Use: {Question.DIFFICULTY_LEVELS}"}), 422
        question.difficulty = data["difficulty"]
    if "category_id" in data:
        if not db.session.get(Category, data["category_id"]):
            return jsonify({"error": "Category not found."}), 404
        question.category_id = data["category_id"]
    if "tags" in data:
        question.tags = ",".join(data["tags"]) if isinstance(data["tags"], list) else data["tags"]

    db.session.commit()
    return jsonify({"message": "Question updated.", "question": question.to_dict(include_answer=True)}), 200


@questions_bp.route("/<int:question_id>", methods=["DELETE"])
@admin_required
def delete_question(question_id):
    """Soft-delete a question by setting is_active = False. Admin only."""
    question = db.session.get(Question, question_id)
    if not question:
        return jsonify({"error": "Question not found."}), 404
    question.is_active = False
    db.session.commit()
    return jsonify({"message": "Question deactivated."}), 200
