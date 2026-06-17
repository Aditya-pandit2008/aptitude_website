"""
routes/ai.py
AI-powered features blueprint (Groq integration).

Endpoints:
    POST /api/v1/ai/explain              – explain a question step-by-step
    POST /api/v1/ai/similar              – generate similar questions
    POST /api/v1/ai/study-plan           – generate personalised study plan
    POST /api/v1/ai/interview-questions  – generate mock interview questions
"""

from flask import Blueprint, request, jsonify, current_app
from flask_jwt_extended import jwt_required, get_jwt_identity

from models import db, Category, Question
from services import ai_service, recommendation as rec_service

ai_bp = Blueprint("ai", __name__)


def _ai_error(exc: Exception):
    """Return a standardised AI-error JSON response."""
    msg = str(exc)
    current_app.logger.error("AI service error: %s", msg)
    if "GROQ_API_KEY" in msg or "api_key" in msg.lower():
        return jsonify({"error": "AI service is not configured. Please set GROQ_API_KEY."}), 503
    if "Groq API error 401" in msg or "Groq API error 403" in msg or "error code: 1010" in msg:
        return jsonify({
            "error": "Groq rejected the request. Please check your GROQ_API_KEY, model access, or network permissions.",
            "details": msg,
        }), 502
    return jsonify({"error": "AI service temporarily unavailable.", "details": msg}), 502


# ─────────────────────────────────────────────────────────────────────────────
# Explain question
# ─────────────────────────────────────────────────────────────────────────────

@ai_bp.route("/explain", methods=["POST"])
@jwt_required()
def explain_question():
    """
    Generate a step-by-step explanation for a given question.

    Request body:
        question_id (int)  – ID of an existing question  ─┐ one of
        OR                                                  │ these
        question_text (str), options (list), correct_option (int)  ─┘

    Returns:
        explanation (str, markdown formatted)
    """
    data = request.get_json(silent=True) or {}

    question_id = data.get("question_id")
    if question_id:
        # Fetch from DB and include correct answer for the AI
        q = Question.query.filter_by(id=question_id, is_active=True).first_or_404()
        text    = q.text
        options = q.options
        correct = q.correct_option
        category = q.category.name if q.category else ""
    else:
        # Accept raw payload for ad-hoc questions
        text    = data.get("question_text", "").strip()
        options = data.get("options", [])
        correct = data.get("correct_option")
        category = data.get("category", "")

        if not text or not options or correct is None:
            return jsonify({"error": "question_text, options, and correct_option are required."}), 422

    try:
        explanation = ai_service.explain_question(text, options, correct, category)
    except Exception as exc:
        return _ai_error(exc)

    return jsonify({"explanation": explanation}), 200


# ─────────────────────────────────────────────────────────────────────────────
# Generate similar questions
# ─────────────────────────────────────────────────────────────────────────────

@ai_bp.route("/similar", methods=["POST"])
@jwt_required()
def generate_similar():
    """
    Generate MCQ questions similar to an existing one.

    Request body:
        question_id (int)           – source question ID
        count       (int, 1-5)      – number of questions to generate (default 3)
    """
    data = request.get_json(silent=True) or {}
    question_id = data.get("question_id")
    count       = min(int(data.get("count", 3)), 5)

    if not question_id:
        return jsonify({"error": "question_id is required."}), 422

    question = Question.query.filter_by(id=question_id, is_active=True).first_or_404()

    try:
        questions = ai_service.generate_similar_questions(
            question_text=question.text,
            category=question.category.name if question.category else "General",
            difficulty=question.difficulty,
            count=count,
        )
    except Exception as exc:
        return _ai_error(exc)

    return jsonify({
        "source_question_id": question_id,
        "generated_questions": questions,
        "count": len(questions),
    }), 200


@ai_bp.route("/aptitude-questions", methods=["POST"])
@jwt_required()
def generate_aptitude_questions():
    """
    Generate fresh Groq AI aptitude MCQs for the test page.

    Request body:
        category   (str)       - topic/category name
        difficulty (str)       - easy | medium | hard
        count      (int, 1-10) - number of questions
    """
    data = request.get_json(silent=True) or {}
    category = (data.get("category") or "Mixed Aptitude").strip()
    category_id = data.get("category_id")
    difficulty = (data.get("difficulty") or "medium").strip().lower()
    count = min(max(int(data.get("count", 5)), 1), 10)

    if difficulty not in {"easy", "medium", "hard"}:
        difficulty = "medium"

    try:
        questions = ai_service.generate_aptitude_questions(category, difficulty, count)
    except Exception as exc:
        return _ai_error(exc)

    if not questions:
        return jsonify({"error": "AI could not generate valid questions. Please try again."}), 502

    db_category = None
    if category_id:
        db_category = db.session.get(Category, category_id)
    if not db_category:
        db_category = Category.query.filter(Category.name.ilike(category)).first()
    if not db_category:
        db_category = Category.query.filter_by(name="Quantitative Aptitude").first() or Category.query.first()

    saved_questions = []
    for item in questions:
        question = Question(
            category_id=db_category.id,
            text=item["text"].strip(),
            correct_option=int(item["correct_option"]),
            explanation=item.get("explanation", ""),
            difficulty=item.get("difficulty", difficulty),
            tags="groq-ai,generated",
        )
        question.options = item["options"]
        db.session.add(question)
        saved_questions.append(question)

    db.session.commit()

    return jsonify({
        "questions": [question.to_dict(include_answer=True) for question in saved_questions],
        "count": len(saved_questions),
        "source": "groq",
    }), 200


# ─────────────────────────────────────────────────────────────────────────────
# Study plan generator
# ─────────────────────────────────────────────────────────────────────────────

@ai_bp.route("/study-plan", methods=["POST"])
@jwt_required()
def generate_study_plan():
    """
    Generate a personalised study plan based on the user's performance.

    Request body (optional):
        days           (int, 7-30)  – plan duration in days (default 7)
        weak_topics    (list[str])  – override automatic detection
        strong_topics  (list[str])  – override automatic detection
    """
    user_id = get_jwt_identity()
    data    = request.get_json(silent=True) or {}
    days    = min(max(int(data.get("days", 7)), 1), 30)

    # Use provided overrides, else auto-detect from performance data
    if data.get("weak_topics") or data.get("strong_topics"):
        weak_topics   = data.get("weak_topics", [])
        strong_topics = data.get("strong_topics", [])
    else:
        recs          = rec_service.get_recommendations(user_id)
        weak_topics   = [t["category_name"] for t in recs["weak_topics"]]
        strong_topics = [t["category_name"] for t in recs["strong_topics"]]

    try:
        plan = ai_service.generate_study_plan(weak_topics, strong_topics, days)
    except Exception as exc:
        return _ai_error(exc)

    return jsonify({
        "study_plan": plan,
        "days": days,
        "weak_topics": weak_topics,
        "strong_topics": strong_topics,
    }), 200


# ─────────────────────────────────────────────────────────────────────────────
# Interview question generator
# ─────────────────────────────────────────────────────────────────────────────

@ai_bp.route("/interview-questions", methods=["POST"])
@jwt_required()
def generate_interview_questions():
    """
    Generate mock interview questions for a specified role.

    Request body:
        role         (str)  – e.g. 'Software Engineer', 'Data Analyst'
        company_type (str)  – 'product' | 'service' | 'startup' (default 'product')
        count        (int)  – number of questions (default 10, max 20)
    """
    data = request.get_json(silent=True) or {}

    role = (data.get("role") or "").strip()
    if not role:
        return jsonify({"error": "role is required."}), 422

    company_type = data.get("company_type", "product")
    count        = min(int(data.get("count", 10)), 20)

    try:
        questions = ai_service.generate_interview_questions(role, company_type, count)
    except Exception as exc:
        return _ai_error(exc)

    return jsonify({
        "role": role,
        "company_type": company_type,
        "questions": questions,
        "count": len(questions),
    }), 200