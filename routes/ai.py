"""
routes/ai.py
AI-powered features blueprint (Groq integration).

Endpoints:
    POST /api/v1/ai/explain              – explain a question step-by-step
    POST /api/v1/ai/similar              – generate similar questions
    POST /api/v1/ai/aptitude-questions   – generate fresh aptitude MCQs
    POST /api/v1/ai/study-plan           – generate personalised study plan
    POST /api/v1/ai/interview-questions  – generate mock interview questions

Security:
    - Rate limited (20 requests/hour per IP) on all endpoints
    - User-supplied strings are sanitized before prompt injection
"""

import re

from flask import Blueprint, request, current_app
from flask_jwt_extended import jwt_required, get_jwt_identity

from extensions import limiter
from models import db, Category, Question
from services import ai_service, recommendation as rec_service
from utils.response import success, error

ai_bp = Blueprint("ai", __name__)

# Max lengths for user-supplied strings that are injected into prompts
_MAX_ROLE_LEN     = 80
_MAX_CATEGORY_LEN = 100
_MAX_TEXT_LEN     = 1000

# Patterns that could be used to escape or override prompt context
_INJECTION_RE = re.compile(
    r"(system\s*:|ignore\s+previous|ignore\s+all|<\|im_start\|>|"
    r"<\|im_end\|>|\[INST\]|\[/INST\]|###\s*instruction)",
    re.IGNORECASE,
)


def _sanitize(text: str, max_len: int = 200) -> str:
    """
    Sanitize a user-supplied string before injecting it into an AI prompt.
    - Strips leading/trailing whitespace
    - Truncates to max_len characters
    - Removes known prompt injection patterns
    - Removes null bytes and control characters
    """
    if not isinstance(text, str):
        return ""
    text = text.strip()[:max_len]
    text = _INJECTION_RE.sub("", text)
    text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", text)
    return text.strip()


def _ai_error(exc: Exception):
    """Return a standardised AI-error JSON response."""
    msg = str(exc)
    current_app.logger.error("AI service error: %s", msg)
    if "GROQ_API_KEY" in msg or "api_key" in msg.lower():
        return error("AI service is not configured. Please set GROQ_API_KEY.", 503)
    if any(code in msg for code in ["Groq API error 401", "Groq API error 403", "error code: 1010"]):
        return error(
            "Groq rejected the request. Check GROQ_API_KEY or network permissions.",
            502,
        )
    return error("AI service temporarily unavailable.", 502)


# ─────────────────────────────────────────────────────────────────────────────
# Explain question
# ─────────────────────────────────────────────────────────────────────────────

@ai_bp.route("/explain", methods=["POST"])
@jwt_required()
@limiter.limit("20 per hour")
def explain_question():
    """
    Generate a step-by-step explanation for a given question.

    Request body:
        question_id (int)  – ID of an existing question  ─┐ one of
        OR                                                  │ these
        question_text (str), options (list), correct_option (int)  ─┘
    """
    data = request.get_json(silent=True) or {}

    question_id = data.get("question_id")
    if question_id:
        q        = Question.query.filter_by(id=question_id, is_active=True).first_or_404()
        text     = q.text
        options  = q.options
        correct  = q.correct_option
        category = q.category.name if q.category else ""
    else:
        text     = _sanitize(data.get("question_text", ""), _MAX_TEXT_LEN)
        options  = data.get("options", [])
        correct  = data.get("correct_option")
        category = _sanitize(data.get("category", ""), _MAX_CATEGORY_LEN)

        if not text or not options or correct is None:
            return error("question_text, options, and correct_option are required.", 422)
        if not isinstance(options, list) or len(options) < 2:
            return error("options must be a list with at least 2 items.", 422)

    try:
        explanation = ai_service.explain_question(text, options, correct, category)
    except Exception as exc:
        return _ai_error(exc)

    return success({"explanation": explanation}, 200)


# ─────────────────────────────────────────────────────────────────────────────
# Generate similar questions
# ─────────────────────────────────────────────────────────────────────────────

@ai_bp.route("/similar", methods=["POST"])
@jwt_required()
@limiter.limit("20 per hour")
def generate_similar():
    """
    Generate MCQ questions similar to an existing one.

    Request body:
        question_id (int)      – source question ID
        count       (int, 1-5) – number of questions to generate (default 3)
    """
    data        = request.get_json(silent=True) or {}
    question_id = data.get("question_id")
    count       = min(int(data.get("count", 3)), 5)

    if not question_id:
        return error("question_id is required.", 422)

    question = Question.query.filter_by(id=question_id, is_active=True).first_or_404()

    try:
        questions = ai_service.generate_similar_questions(
            question_text = question.text,
            category      = question.category.name if question.category else "General",
            difficulty    = question.difficulty,
            count         = count,
        )
    except Exception as exc:
        return _ai_error(exc)

    return success({
        "source_question_id": question_id,
        "generated_questions": questions,
        "count":              len(questions),
    }, 200)


# ─────────────────────────────────────────────────────────────────────────────
# Aptitude question generator
# ─────────────────────────────────────────────────────────────────────────────

@ai_bp.route("/aptitude-questions", methods=["POST"])
@jwt_required()
@limiter.limit("20 per hour")
def generate_aptitude_questions():
    """
    Generate fresh Groq AI aptitude MCQs for the test page.

    Request body:
        category   (str)       – topic/category name
        difficulty (str)       – easy | medium | hard
        count      (int, 1-10) – number of questions
    """
    data        = request.get_json(silent=True) or {}
    category    = _sanitize(data.get("category") or "Mixed Aptitude", _MAX_CATEGORY_LEN)
    category_id = data.get("category_id")
    difficulty  = _sanitize(data.get("difficulty") or "medium", 10).lower()
    count       = min(max(int(data.get("count", 5)), 1), 10)
    user_id = get_jwt_identity()
    if difficulty == "adaptive" and user_id:
        from models import User
        user = db.session.get(User, int(user_id))
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

    if difficulty not in {"easy", "medium", "hard"}:
        difficulty = "medium"

    try:
        questions = ai_service.generate_aptitude_questions(category, difficulty, count)
    except Exception as exc:
        return _ai_error(exc)

    if not questions:
        return error("AI could not generate valid questions. Please try again.", 502)

    # Resolve DB category
    db_category = None
    if category_id:
        db_category = db.session.get(Category, int(category_id))
    if not db_category:
        db_category = Category.query.filter(Category.name.ilike(category)).first()
    if not db_category:
        db_category = (Category.query.filter_by(name="Quantitative Aptitude").first()
                       or Category.query.first())

    saved = []
    for item in questions:
        q = Question(
            category_id    = db_category.id,
            text           = item["text"].strip(),
            correct_option = int(item["correct_option"]),
            explanation    = item.get("explanation", ""),
            difficulty     = item.get("difficulty", difficulty),
            tags           = "groq-ai,generated",
        )
        q.options = item["options"]
        db.session.add(q)
        saved.append(q)

    db.session.commit()

    return success({
        "questions": [q.to_dict(include_answer=True) for q in saved],
        "count":     len(saved),
        "source":    "groq",
    }, 200)


# ─────────────────────────────────────────────────────────────────────────────
# Study plan generator
# ─────────────────────────────────────────────────────────────────────────────

@ai_bp.route("/study-plan", methods=["POST"])
@jwt_required()
@limiter.limit("10 per hour")
def generate_study_plan():
    """
    Generate a personalised study plan based on the user's performance.

    Request body (optional):
        days          (int, 1-30)  – plan duration (default 7)
        weak_topics   (list[str])  – override automatic detection
        strong_topics (list[str])  – override automatic detection
    """
    user_id = int(get_jwt_identity())
    data    = request.get_json(silent=True) or {}
    days    = min(max(int(data.get("days", 7)), 1), 30)

    if data.get("weak_topics") or data.get("strong_topics"):
        weak_topics   = [_sanitize(t, 80) for t in data.get("weak_topics", [])]
        strong_topics = [_sanitize(t, 80) for t in data.get("strong_topics", [])]
    else:
        recs          = rec_service.get_recommendations(user_id)
        weak_topics   = [t["category_name"] for t in recs["weak_topics"]]
        strong_topics = [t["category_name"] for t in recs["strong_topics"]]

    try:
        plan = ai_service.generate_study_plan(weak_topics, strong_topics, days)
    except Exception as exc:
        return _ai_error(exc)

    return success({
        "study_plan":   plan,
        "days":         days,
        "weak_topics":  weak_topics,
        "strong_topics": strong_topics,
    }, 200)


# ─────────────────────────────────────────────────────────────────────────────
# Interview question generator
# ─────────────────────────────────────────────────────────────────────────────

@ai_bp.route("/interview-questions", methods=["POST"])
@jwt_required()
@limiter.limit("10 per hour")
def generate_interview_questions():
    """
    Generate mock interview questions for a specified role.

    Request body:
        role         (str)  – e.g. 'Software Engineer', 'Data Analyst'
        company_type (str)  – 'product' | 'service' | 'startup' (default 'product')
        count        (int)  – number of questions (default 10, max 20)
    """
    data         = request.get_json(silent=True) or {}
    role         = _sanitize(data.get("role") or "", _MAX_ROLE_LEN)
    company_type = _sanitize(data.get("company_type", "product"), 20)
    count        = min(int(data.get("count", 10)), 20)

    if not role:
        return error("role is required.", 422)

    if company_type not in {"product", "service", "startup"}:
        company_type = "product"

    try:
        questions = ai_service.generate_interview_questions(role, company_type, count)
    except Exception as exc:
        return _ai_error(exc)

    return success({
        "role":         role,
        "company_type": company_type,
        "questions":    questions,
        "count":        len(questions),
    }, 200)