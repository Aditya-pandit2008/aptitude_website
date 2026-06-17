"""
utils/validators.py
Input validation helpers used across route blueprints.
"""

import re


# ── Constants ─────────────────────────────────────────────────────────────────

EMAIL_RE = re.compile(r"^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$")
ALLOWED_DIFFICULTIES = {"easy", "medium", "hard"}


# ── Auth validators ───────────────────────────────────────────────────────────

def validate_registration(data: dict) -> list[str]:
    """
    Validate user registration payload.

    Returns:
        List of error strings (empty list = valid).
    """
    errors = []

    username = (data.get("username") or "").strip()
    email = (data.get("email") or "").strip()
    password = data.get("password") or ""

    if not username or len(username) < 3:
        errors.append("Username must be at least 3 characters.")
    if len(username) > 80:
        errors.append("Username must be 80 characters or fewer.")

    if not email or not EMAIL_RE.match(email):
        errors.append("A valid email address is required.")

    if not password or len(password) < 8:
        errors.append("Password must be at least 8 characters.")

    return errors


def validate_login(data: dict) -> list[str]:
    """Validate login payload."""
    errors = []
    if not data.get("email"):
        errors.append("Email is required.")
    if not data.get("password"):
        errors.append("Password is required.")
    return errors


# ── Question validators ───────────────────────────────────────────────────────

def validate_question(data: dict) -> list[str]:
    """
    Validate question create/update payload.

    Returns:
        List of error strings.
    """
    errors = []

    if not (data.get("text") or "").strip():
        errors.append("Question text is required.")

    options = data.get("options", [])
    if not isinstance(options, list) or len(options) < 2:
        errors.append("At least 2 options are required.")

    correct = data.get("correct_option")
    if correct is None or not isinstance(correct, int):
        errors.append("correct_option (integer index) is required.")
    elif options and (correct < 0 or correct >= len(options)):
        errors.append("correct_option index is out of range.")

    difficulty = data.get("difficulty", "medium")
    if difficulty not in ALLOWED_DIFFICULTIES:
        errors.append(f"difficulty must be one of: {', '.join(ALLOWED_DIFFICULTIES)}.")

    if not data.get("category_id"):
        errors.append("category_id is required.")

    return errors


def validate_question_data(data: dict) -> list[str]:
    """Alias for validate_question for admin routes."""
    return validate_question(data)


# ── Test validators ───────────────────────────────────────────────────────────

def validate_test_submission(data: dict) -> list[str]:
    """
    Validate test submission payload.

    Expected shape:
        {
            "answers": [{"question_id": int, "selected_option": int|null}, ...],
            "time_taken": int   (seconds, optional)
        }
    """
    errors = []

    answers = data.get("answers")
    if not answers or not isinstance(answers, list):
        errors.append("answers must be a non-empty list.")
        return errors

    for i, ans in enumerate(answers):
        if not isinstance(ans, dict):
            errors.append(f"answers[{i}] must be an object.")
            continue
        if not isinstance(ans.get("question_id"), int):
            errors.append(f"answers[{i}].question_id must be an integer.")

    return errors
