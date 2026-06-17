"""
routes/admin.py
Admin panel blueprint: manage questions, users, and system settings.
Enhanced with full analytics endpoints.
"""

from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from sqlalchemy import func, desc
from datetime import datetime, timedelta, timezone

from models import db, User, Question, Category, TestAttempt, TestAnswer, LeaderboardEntry
from utils.validators import validate_question_data

admin_bp = Blueprint("admin", __name__)


def _check_admin():
    user_id = get_jwt_identity()
    if not user_id:
        return None
    user = User.query.get(user_id)
    if not user or user.role != "admin":
        return None
    return user


# ─── Admin Dashboard Analytics ───────────────────────────────────────────────

@admin_bp.route("/dashboard", methods=["GET"])
@jwt_required()
def admin_dashboard():
    admin = _check_admin()
    if not admin:
        return jsonify({"error": "Unauthorized: admin access required"}), 403

    now = datetime.now(timezone.utc)
    seven_days_ago = now - timedelta(days=7)
    thirty_days_ago = now - timedelta(days=30)

    # Core stats
    total_users = User.query.count()
    total_questions = Question.query.count()
    total_tests = TestAttempt.query.count()
    total_categories = Category.query.count()
    admin_users = User.query.filter_by(role="admin").count()
    student_users = User.query.filter_by(role="student").count()

    # New users last 7 days
    new_users_7d = User.query.filter(User.created_at >= seven_days_ago).count()
    new_users_30d = User.query.filter(User.created_at >= thirty_days_ago).count()

    # Tests last 7 days
    tests_7d = TestAttempt.query.filter(TestAttempt.completed_at >= seven_days_ago).count()

    # Average accuracy across all tests
    avg_acc = db.session.query(func.avg(TestAttempt.accuracy)).scalar() or 0

    # Active questions
    active_questions = Question.query.filter_by(is_active=True).count()

    # Daily registrations last 14 days (for chart)
    daily_registrations = []
    for i in range(13, -1, -1):
        day_start = now - timedelta(days=i+1)
        day_end = now - timedelta(days=i)
        count = User.query.filter(
            User.created_at >= day_start,
            User.created_at < day_end
        ).count()
        daily_registrations.append({
            "date": day_end.strftime("%b %d"),
            "count": count
        })

    # Daily tests last 14 days (for chart)
    daily_tests = []
    for i in range(13, -1, -1):
        day_start = now - timedelta(days=i+1)
        day_end = now - timedelta(days=i)
        count = TestAttempt.query.filter(
            TestAttempt.completed_at >= day_start,
            TestAttempt.completed_at < day_end
        ).count()
        daily_tests.append({
            "date": day_end.strftime("%b %d"),
            "count": count
        })

    # Questions by category
    cat_stats = db.session.query(
        Category.name,
        func.count(Question.id).label("count")
    ).join(Question, Question.category_id == Category.id, isouter=True)\
     .group_by(Category.id, Category.name).all()

    questions_by_category = [{"category": r.name, "count": r.count or 0} for r in cat_stats]

    # Questions by difficulty
    diff_stats = db.session.query(
        Question.difficulty,
        func.count(Question.id).label("count")
    ).group_by(Question.difficulty).all()
    questions_by_difficulty = [{"difficulty": r.difficulty, "count": r.count} for r in diff_stats]

    # Top 5 users by XP
    top_users = User.query.order_by(desc(User.total_xp)).limit(5).all()
    top_users_data = [{"username": u.username, "xp": u.total_xp, "role": u.role} for u in top_users]

    # Recent activity (last 10 test attempts)
    recent_tests = TestAttempt.query.order_by(desc(TestAttempt.completed_at)).limit(10).all()
    recent_activity = []
    for t in recent_tests:
        recent_activity.append({
            "user": t.user.username if t.user else "Unknown",
            "category": t.category.name if t.category else "Mixed",
            "score": round(t.accuracy, 1),
            "xp": t.xp_earned,
            "date": t.completed_at.strftime("%b %d, %H:%M") if t.completed_at else ""
        })

    return jsonify({
        "stats": {
            "total_users": total_users,
            "total_questions": total_questions,
            "total_tests": total_tests,
            "total_categories": total_categories,
            "admin_users": admin_users,
            "student_users": student_users,
            "new_users_7d": new_users_7d,
            "new_users_30d": new_users_30d,
            "tests_7d": tests_7d,
            "avg_accuracy": round(float(avg_acc), 1),
            "active_questions": active_questions,
        },
        "charts": {
            "daily_registrations": daily_registrations,
            "daily_tests": daily_tests,
            "questions_by_category": questions_by_category,
            "questions_by_difficulty": questions_by_difficulty,
        },
        "top_users": top_users_data,
        "recent_activity": recent_activity,
    }), 200


# ─── Questions Management ─────────────────────────────────────────────────────

@admin_bp.route("/questions", methods=["POST"])
@jwt_required()
def create_question():
    admin = _check_admin()
    if not admin:
        return jsonify({"error": "Unauthorized: admin access required"}), 403

    data = request.get_json(silent=True) or {}
    errors = validate_question_data(data)
    if errors:
        return jsonify({"errors": errors}), 422

    try:
        category = Category.query.get(data["category_id"])
        if not category:
            return jsonify({"error": "Category not found"}), 404

        question = Question(
            category_id=data["category_id"],
            text=data["text"].strip(),
            options=data["options"],
            correct_option=int(data["correct_option"]),
            explanation=data.get("explanation", "").strip(),
            difficulty=data.get("difficulty", "medium"),
            tags=data.get("tags", ""),
            is_active=True,
            created_by=admin.id,
        )

        db.session.add(question)
        db.session.commit()

        return jsonify({
            "message": "Question created successfully",
            "question": question.to_dict(include_answer=True),
        }), 201

    except Exception as e:
        db.session.rollback()
        return jsonify({"error": str(e)}), 500


@admin_bp.route("/questions", methods=["GET"])
@jwt_required()
def get_questions():
    admin = _check_admin()
    if not admin:
        return jsonify({"error": "Unauthorized: admin access required"}), 403

    page = request.args.get("page", 1, type=int)
    per_page = request.args.get("per_page", 20, type=int)
    category_id = request.args.get("category_id", None, type=int)
    difficulty = request.args.get("difficulty", None, type=str)
    search = request.args.get("search", "", type=str).strip()

    query = Question.query

    if category_id:
        query = query.filter_by(category_id=category_id)
    if difficulty:
        query = query.filter_by(difficulty=difficulty)
    if search:
        query = query.filter(Question.text.ilike(f"%{search}%"))

    paginated = query.order_by(desc(Question.created_at)).paginate(page=page, per_page=per_page, error_out=False)

    return jsonify({
        "questions": [q.to_dict(include_answer=True) for q in paginated.items],
        "total": paginated.total,
        "page": page,
        "per_page": per_page,
        "pages": paginated.pages,
    }), 200


@admin_bp.route("/questions/<int:question_id>", methods=["PUT"])
@jwt_required()
def update_question(question_id):
    admin = _check_admin()
    if not admin:
        return jsonify({"error": "Unauthorized: admin access required"}), 403

    question = Question.query.get(question_id)
    if not question:
        return jsonify({"error": "Question not found"}), 404

    data = request.get_json(silent=True) or {}

    try:
        if "text" in data:
            question.text = data["text"].strip()
        if "options" in data:
            question.options = data["options"]
        if "correct_option" in data:
            question.correct_option = int(data["correct_option"])
        if "explanation" in data:
            question.explanation = data["explanation"].strip()
        if "difficulty" in data:
            question.difficulty = data["difficulty"]
        if "tags" in data:
            question.tags = data["tags"]
        if "is_active" in data:
            question.is_active = bool(data["is_active"])
        if "category_id" in data:
            category = Category.query.get(data["category_id"])
            if not category:
                return jsonify({"error": "Category not found"}), 404
            question.category_id = data["category_id"]

        db.session.commit()

        return jsonify({
            "message": "Question updated successfully",
            "question": question.to_dict(include_answer=True),
        }), 200

    except Exception as e:
        db.session.rollback()
        return jsonify({"error": str(e)}), 500


@admin_bp.route("/questions/<int:question_id>", methods=["DELETE"])
@jwt_required()
def delete_question(question_id):
    admin = _check_admin()
    if not admin:
        return jsonify({"error": "Unauthorized: admin access required"}), 403

    question = Question.query.get(question_id)
    if not question:
        return jsonify({"error": "Question not found"}), 404

    try:
        db.session.delete(question)
        db.session.commit()
        return jsonify({"message": "Question deleted successfully"}), 200
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": str(e)}), 500


# ─── Users Management ─────────────────────────────────────────────────────────

@admin_bp.route("/users", methods=["GET"])
@jwt_required()
def get_users():
    admin = _check_admin()
    if not admin:
        return jsonify({"error": "Unauthorized: admin access required"}), 403

    page = request.args.get("page", 1, type=int)
    per_page = request.args.get("per_page", 20, type=int)
    role = request.args.get("role", None, type=str)
    search = request.args.get("search", "", type=str).strip()

    query = User.query

    if role:
        query = query.filter_by(role=role)
    if search:
        query = query.filter(
            (User.username.ilike(f"%{search}%")) | (User.email.ilike(f"%{search}%"))
        )

    paginated = query.order_by(desc(User.created_at)).paginate(page=page, per_page=per_page, error_out=False)

    users_data = []
    for u in paginated.items:
        tests_count = TestAttempt.query.filter_by(user_id=u.id).count()
        users_data.append({
            "id": u.id,
            "username": u.username,
            "email": u.email,
            "role": u.role,
            "total_xp": u.total_xp,
            "daily_streak": u.daily_streak,
            "tests_taken": tests_count,
            "created_at": u.created_at.isoformat() if u.created_at else None,
        })

    return jsonify({
        "users": users_data,
        "total": paginated.total,
        "page": page,
        "per_page": per_page,
        "pages": paginated.pages,
    }), 200


@admin_bp.route("/users/<int:user_id>", methods=["DELETE"])
@jwt_required()
def delete_user(user_id):
    admin = _check_admin()
    if not admin:
        return jsonify({"error": "Unauthorized: admin access required"}), 403

    if user_id == int(get_jwt_identity()):
        return jsonify({"error": "Cannot delete your own account"}), 400

    user = User.query.get(user_id)
    if not user:
        return jsonify({"error": "User not found"}), 404

    try:
        db.session.delete(user)
        db.session.commit()
        return jsonify({"message": "User deleted successfully"}), 200
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": str(e)}), 500


@admin_bp.route("/users/<int:user_id>/role", methods=["PUT"])
@jwt_required()
def update_user_role(user_id):
    admin = _check_admin()
    if not admin:
        return jsonify({"error": "Unauthorized: admin access required"}), 403

    if user_id == admin.id:
        return jsonify({"error": "Cannot modify own role"}), 400

    user = User.query.get(user_id)
    if not user:
        return jsonify({"error": "User not found"}), 404

    data = request.get_json(silent=True) or {}
    new_role = data.get("role", "").strip().lower()

    if new_role not in ("student", "admin"):
        return jsonify({"error": "Invalid role. Must be 'student' or 'admin'"}), 422

    try:
        user.role = new_role
        db.session.commit()
        return jsonify({
            "message": f"User role updated to {new_role}",
            "user": user.to_dict(),
        }), 200
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": str(e)}), 500


# ─── Categories Management ────────────────────────────────────────────────────

@admin_bp.route("/categories", methods=["GET"])
@jwt_required()
def get_categories():
    admin = _check_admin()
    if not admin:
        return jsonify({"error": "Unauthorized: admin access required"}), 403

    categories = Category.query.all()
    return jsonify({"categories": [c.to_dict() for c in categories]}), 200


@admin_bp.route("/categories", methods=["POST"])
@jwt_required()
def create_category():
    admin = _check_admin()
    if not admin:
        return jsonify({"error": "Unauthorized: admin access required"}), 403

    data = request.get_json(silent=True) or {}
    name = data.get("name", "").strip()
    if not name:
        return jsonify({"error": "Category name is required"}), 422

    if Category.query.filter_by(name=name).first():
        return jsonify({"error": "Category already exists"}), 409

    try:
        cat = Category(
            name=name,
            description=data.get("description", ""),
            icon=data.get("icon", "📚")
        )
        db.session.add(cat)
        db.session.commit()
        return jsonify({"message": "Category created", "category": cat.to_dict()}), 201
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": str(e)}), 500


# ─── Analytics Export ─────────────────────────────────────────────────────────

@admin_bp.route("/analytics/summary", methods=["GET"])
@jwt_required()
def analytics_summary():
    admin = _check_admin()
    if not admin:
        return jsonify({"error": "Unauthorized: admin access required"}), 403

    # Per-category performance analytics
    cat_performance = db.session.query(
        Category.name,
        func.count(TestAttempt.id).label("attempts"),
        func.avg(TestAttempt.accuracy).label("avg_accuracy"),
        func.avg(TestAttempt.xp_earned).label("avg_xp"),
    ).join(TestAttempt, TestAttempt.category_id == Category.id, isouter=True)\
     .group_by(Category.id, Category.name).all()

    return jsonify({
        "category_performance": [
            {
                "category": r.name,
                "attempts": r.attempts or 0,
                "avg_accuracy": round(float(r.avg_accuracy or 0), 1),
                "avg_xp": round(float(r.avg_xp or 0), 1),
            }
            for r in cat_performance
        ]
    }), 200
