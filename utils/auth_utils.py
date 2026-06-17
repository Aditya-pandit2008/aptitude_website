"""
utils/auth_utils.py
Authentication utility decorators and helpers.
"""

from functools import wraps
from flask import jsonify
from flask_jwt_extended import verify_jwt_in_request, get_jwt_identity

from models import db, User


def admin_required(fn):
    """
    Decorator: requires a valid JWT AND the user's role to be 'admin'.
    Returns 403 otherwise.
    """
    @wraps(fn)
    def wrapper(*args, **kwargs):
        verify_jwt_in_request()
        user_id = get_jwt_identity()
        user = db.session.get(User, user_id)
        if not user or user.role != "admin":
            return jsonify({"error": "Admin privileges required"}), 403
        return fn(*args, **kwargs)
    return wrapper


def get_current_user() -> User | None:
    """
    Return the User object for the current JWT identity, or None.
    Must be called inside a request context with a valid JWT.
    """
    user_id = get_jwt_identity()
    return db.session.get(User, user_id)
