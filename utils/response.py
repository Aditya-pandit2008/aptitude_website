"""
utils/response.py
Consistent JSON response helpers used across all route blueprints.

Usage:
    from utils.response import success, error

    return success({"user": user.to_dict()}, 200)
    return error("Email already registered.", 409)
    return error("Validation failed.", 422, details=errors)
"""

from flask import jsonify


def success(data: dict | list | None = None, status: int = 200):
    """
    Return a standardised success envelope.

    Shape:
        {
            "success": true,
            "data": { ... }
        }
    """
    body = {"success": True}
    if data is not None:
        body["data"] = data
    return jsonify(body), status


def error(message: str, status: int = 400, details=None):
    """
    Return a standardised error envelope.

    Shape:
        {
            "success": false,
            "error":   "Human-readable message",
            "details": [...]   // optional list of validation errors
        }
    """
    body: dict = {"success": False, "error": message}
    if details is not None:
        body["details"] = details
    return jsonify(body), status


def paginated(items: list, total: int, page: int, pages: int, per_page: int,
              status: int = 200):
    """
    Return a standardised paginated list envelope.

    Shape:
        {
            "success": true,
            "data": [...],
            "pagination": {
                "total": 120,
                "page": 1,
                "pages": 12,
                "per_page": 10
            }
        }
    """
    return jsonify({
        "success": True,
        "data": items,
        "pagination": {
            "total":    total,
            "page":     page,
            "pages":    pages,
            "per_page": per_page,
        },
    }), status
