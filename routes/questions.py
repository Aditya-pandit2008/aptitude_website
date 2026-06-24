"""
routes/questions.py
Question management blueprint.

Endpoints:
    GET    /api/v1/questions/           – list questions (filterable, paginated)
    POST   /api/v1/questions/           – add a question (admin)
    GET    /api/v1/questions/<id>       – get single question
    PUT    /api/v1/questions/<id>       – update question (admin)
    DELETE /api/v1/questions/<id>       – soft-delete question (admin)
    GET    /api/v1/questions/categories – list all categories
    POST   /api/v1/questions/categories – create a category (admin)
    GET    /api/v1/questions/random     – fetch random questions for a test
"""

import random

from flask import Blueprint, request
from flask_jwt_extended import jwt_required, get_jwt_identity
from sqlalchemy import func

from models import db, Question, Category
from utils.auth_utils import admin_required
from utils.validators import validate_question
from utils.response import success, error, paginated

questions_bp = Blueprint("questions", __name__)


# ─────────────────────────────────────────────────────────────────────────────
# Category routes
# ─────────────────────────────────────────────────────────────────────────────

@questions_bp.route("/categories", methods=["GET"])
def list_categories():
    """
    Return all categories with question counts.

    Fix: previous version called self.questions.count() per row — N+1 query.
    Now fetches all counts in a single aggregation query.
    """
    # Single query: count active questions per category
    count_subq = (
        db.session.query(
            Question.category_id,
            func.count(Question.id).label("q_count"),
        )
        .filter_by(is_active=True)
        .group_by(Question.category_id)
        .subquery()
    )

    rows = (
        db.session.query(Category, count_subq.c.q_count)
        .outerjoin(count_subq, Category.id == count_subq.c.category_id)
        .order_by(Category.id)
        .all()
    )

    categories = [
        cat.to_dict(question_count=int(cnt or 0))
        for cat, cnt in rows
    ]
    return success({"categories": categories}, 200)


@questions_bp.route("/categories", methods=["POST"])
@admin_required
def create_category():
    """
    Create a new category. Admin only.
    Request body: {name, description?, icon?}
    """
    data = request.get_json(silent=True) or {}
    name = (data.get("name") or "").strip()
    if not name:
        return error("Category name is required.", 422)

    if Category.query.filter_by(name=name).first():
        return error("Category already exists.", 409)

    category = Category(
        name=name,
        description=data.get("description"),
        icon=data.get("icon"),
    )
    db.session.add(category)
    db.session.commit()
    return success({"message": "Category created.", "category": category.to_dict(question_count=0)}, 201)


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
    difficulty  = request.args.get("difficulty")
    search      = request.args.get("search", "").strip()
    page        = request.args.get("page", 1, type=int)
    per_page    = min(request.args.get("per_page", 20, type=int), 100)

    q = Question.query.filter_by(is_active=True)

    if category_id:
        q = q.filter_by(category_id=category_id)
    if difficulty and difficulty in Question.DIFFICULTY_LEVELS:
        q = q.filter_by(difficulty=difficulty)
    if search:
        q = q.filter(Question.text.ilike(f"%{search}%"))

    p = q.order_by(Question.id.desc()).paginate(
        page=page, per_page=per_page, error_out=False
    )

    return paginated(
        items=[q.to_dict() for q in p.items],
        total=p.total,
        page=p.page,
        pages=p.pages,
        per_page=per_page,
    )


@questions_bp.route("/random", methods=["GET"])
@jwt_required()
def get_random_questions():
    """
    Fetch a random set of questions (used to start a test).

    Fix: replaced ORDER BY RANDOM() (table scan + sort) with offset-based
    sampling — O(log n) instead of O(n log n) on large tables.

    Query params:
        category_id (int)          – filter by category (optional)
        difficulty  (str)          – filter by difficulty (optional)
        count       (int, 1-50)    – number of questions, default 10
    """
    category_id = request.args.get("category_id", type=int)
    difficulty  = request.args.get("difficulty")
    count       = min(request.args.get("count", 10, type=int), 50)
    if difficulty == "adaptive":
        from models import User
        user_id = get_jwt_identity()
        user = db.session.get(User, int(user_id)) if user_id else None
        if user:
            skill = user.current_skill_level or 0.5
            if skill < 0.35:
                difficulty = "easy"
            elif skill <= 0.70:
                difficulty = "medium"
            else:
                difficulty = "hard"
        else:
            difficulty = "medium"

    q = Question.query.filter_by(is_active=True)
    if category_id:
        q = q.filter_by(category_id=category_id)
    if difficulty and difficulty in Question.DIFFICULTY_LEVELS:
        q = q.filter_by(difficulty=difficulty)

    total = q.count()
    if total == 0:
        return success({"questions": [], "count": 0}, 200)

    if total <= count:
        # Pool is smaller than requested — return all
        questions = q.all()
    else:
        # Randomly sample 'count' offsets, fetch only those rows
        offsets   = random.sample(range(total), count)
        ids       = [q.offset(off).limit(1).with_entities(Question.id).scalar()
                     for off in offsets]
        ids       = [i for i in ids if i is not None]
        questions = Question.query.filter(Question.id.in_(ids)).all()
        # Re-shuffle since IN() ordering is not guaranteed
        random.shuffle(questions)

    return success({
        "questions": [qs.to_dict() for qs in questions],
        "count":     len(questions),
    }, 200)


@questions_bp.route("/<int:question_id>", methods=["GET"])
@jwt_required()
def get_question(question_id):
    """Return a single question by ID (without revealing the correct answer)."""
    question = Question.query.filter_by(id=question_id, is_active=True).first_or_404()
    return success({"question": question.to_dict()}, 200)


@questions_bp.route("/", methods=["POST"])
@admin_required
def create_question():
    """
    Add a new question. Admin only.

    Request body:
        {
            category_id, text, options (list), correct_option (int),
            difficulty?, explanation?, tags?
        }
    """
    data   = request.get_json(silent=True) or {}
    errors = validate_question(data)
    if errors:
        return error("Validation failed.", 422, details=errors)

    category = db.session.get(Category, data["category_id"])
    if not category:
        return error("Category not found.", 404)

    user_id  = int(get_jwt_identity())
    question = Question(
        category_id    = data["category_id"],
        text           = data["text"].strip(),
        correct_option = data["correct_option"],
        explanation    = data.get("explanation"),
        difficulty     = data.get("difficulty", "medium"),
        tags           = ",".join(data["tags"]) if isinstance(data.get("tags"), list)
                         else data.get("tags", ""),
        created_by     = user_id,
    )
    question.options = data["options"]

    db.session.add(question)
    db.session.commit()
    return success({"message": "Question created.", "question": question.to_dict(include_answer=True)}, 201)


@questions_bp.route("/<int:question_id>", methods=["PUT"])
@admin_required
def update_question(question_id):
    """Update an existing question (partial update). Admin only."""
    question = db.session.get(Question, question_id)
    if not question:
        return error("Question not found.", 404)

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
            return error(f"Invalid difficulty. Use: {Question.DIFFICULTY_LEVELS}", 422)
        question.difficulty = data["difficulty"]
    if "category_id" in data:
        if not db.session.get(Category, data["category_id"]):
            return error("Category not found.", 404)
        question.category_id = data["category_id"]
    if "tags" in data:
        question.tags = ",".join(data["tags"]) if isinstance(data["tags"], list) else data["tags"]

    db.session.commit()
    return success({"message": "Question updated.", "question": question.to_dict(include_answer=True)}, 200)


@questions_bp.route("/<int:question_id>", methods=["DELETE"])
@admin_required
def delete_question(question_id):
    """Soft-delete a question by setting is_active = False. Admin only."""
    question = db.session.get(Question, question_id)
    if not question:
        return error("Question not found.", 404)
    question.is_active = False
    db.session.commit()
    return success({"message": "Question deactivated."}, 200)
@questions_bp.route("/<int:question_id>/flag", methods=["POST"])
@jwt_required()
def flag_question(question_id):
    """Flag a question for administrator moderation."""
    question = db.session.get(Question, question_id)
    if not question:
        return error("Question not found.", 404)
    data = request.get_json(silent=True) or {}
    reason = data.get("reason", "").strip()
    if not reason:
        return error("Reason for flagging is required.", 422)
    question.is_flagged = True
    question.flag_reason = reason
    db.session.commit()
    return success({"message": "Question flagged successfully.", "question": question.to_dict()}, 200)
