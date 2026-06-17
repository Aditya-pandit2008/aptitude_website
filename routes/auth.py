"""
routes/auth.py
Authentication blueprint: register, login, refresh token, profile.

Endpoints:
    POST /api/v1/auth/register   – create a new user account
    POST /api/v1/auth/login      – authenticate and receive JWT tokens
    POST /api/v1/auth/refresh    – exchange refresh token for new access token
    GET  /api/v1/auth/me         – return the authenticated user's profile
    PUT  /api/v1/auth/me         – update username or password
"""

from flask import Blueprint, request, jsonify
from flask_jwt_extended import (
    create_access_token, create_refresh_token,
    jwt_required, get_jwt_identity,
    verify_jwt_in_request,
)

from models import db, User
from utils.validators import validate_registration, validate_login

auth_bp = Blueprint("auth", __name__)


# ─────────────────────────────────────────────────────────────────────────────
# Register
# ─────────────────────────────────────────────────────────────────────────────

@auth_bp.route("/register", methods=["POST"])
def register():
    """
    Register a new user.

    Request body (JSON):
        username (str): 3-80 chars
        email    (str): valid email
        password (str): min 8 chars

    Returns 201 with user data + tokens on success.
    """
    data = request.get_json(silent=True) or {}
    errors = validate_registration(data)
    if errors:
        return jsonify({"errors": errors}), 422

    username = data["username"].strip()
    email = data["email"].strip().lower()

    # Uniqueness checks
    if User.query.filter_by(email=email).first():
        return jsonify({"error": "Email already registered."}), 409
    if User.query.filter_by(username=username).first():
        return jsonify({"error": "Username already taken."}), 409

    user = User(username=username, email=email)
    user.set_password(data["password"])
    db.session.add(user)
    db.session.commit()

    access_token = create_access_token(identity=str(user.id))
    refresh_token = create_refresh_token(identity=str(user.id))

    return jsonify({
        "message": "Account created successfully.",
        "user": user.to_dict(include_sensitive=True),
        "access_token": access_token,
        "refresh_token": refresh_token,
    }), 201


# ─────────────────────────────────────────────────────────────────────────────
# Login
# ─────────────────────────────────────────────────────────────────────────────

@auth_bp.route("/login", methods=["POST"])
def login():
    """
    Authenticate a user and return JWT tokens.

    Request body (JSON):
        email    (str)
        password (str)
    """
    data = request.get_json(silent=True) or {}
    errors = validate_login(data)
    if errors:
        return jsonify({"errors": errors}), 422

    user = User.query.filter_by(email=data["email"].strip().lower()).first()

    if not user or not user.check_password(data["password"]):
        return jsonify({"error": "Invalid email or password."}), 401

    access_token = create_access_token(identity=str(user.id))
    refresh_token = create_refresh_token(identity=str(user.id))

    return jsonify({
        "message": "Login successful.",
        "user": user.to_dict(include_sensitive=True),
        "access_token": access_token,
        "refresh_token": refresh_token,
    }), 200


# ─────────────────────────────────────────────────────────────────────────────
# Refresh token
# ─────────────────────────────────────────────────────────────────────────────

@auth_bp.route("/refresh", methods=["POST"])
@jwt_required(refresh=True)
def refresh():
    """
    Exchange a valid refresh token for a new access token.
    Requires Bearer refresh token in the Authorization header.
    """
    user_id = get_jwt_identity()
    new_access = create_access_token(identity=user_id)
    return jsonify({"access_token": new_access}), 200


# ─────────────────────────────────────────────────────────────────────────────
# Profile – read & update
# ─────────────────────────────────────────────────────────────────────────────

@auth_bp.route("/me", methods=["GET"])
@jwt_required()
def get_profile():
    """Return the authenticated user's profile (including email)."""
    user_id = get_jwt_identity()
    user = db.session.get(User, user_id)
    if not user:
        return jsonify({"error": "User not found."}), 404
    return jsonify({"user": user.to_dict(include_sensitive=True)}), 200


@auth_bp.route("/me", methods=["PUT"])
@jwt_required()
def update_profile():
    """
    Update username and/or password.

    Request body (JSON, all optional):
        username    (str)
        old_password (str) – required when changing password
        new_password (str) – min 8 chars
    """
    user_id = get_jwt_identity()
    user = db.session.get(User, user_id)
    if not user:
        return jsonify({"error": "User not found."}), 404
    data = request.get_json(silent=True) or {}

    if "username" in data:
        new_username = data["username"].strip()
        if len(new_username) < 3:
            return jsonify({"error": "Username must be at least 3 characters."}), 422
        existing = User.query.filter_by(username=new_username).first()
        if existing and existing.id != user.id:
            return jsonify({"error": "Username already taken."}), 409
        user.username = new_username

    if "new_password" in data:
        if not data.get("old_password"):
            return jsonify({"error": "old_password is required to change password."}), 422
        if not user.check_password(data["old_password"]):
            return jsonify({"error": "Current password is incorrect."}), 401
        if len(data["new_password"]) < 8:
            return jsonify({"error": "New password must be at least 8 characters."}), 422
        user.set_password(data["new_password"])

    db.session.commit()
    return jsonify({"message": "Profile updated.", "user": user.to_dict(include_sensitive=True)}), 200


@auth_bp.route("/me", methods=["DELETE"])
@jwt_required()
def delete_profile():
    """Delete the currently authenticated user's account."""
    user_id = get_jwt_identity()
    user = db.session.get(User, user_id)
    if not user:
        return jsonify({"error": "User not found."}), 404

    db.session.delete(user)
    db.session.commit()
    return jsonify({"message": "Account deleted successfully."}), 200


# ─────────────────────────────────────────────────────────────────────────────
# Admin self-promotion (secured by ADMIN_SECRET_KEY env variable)
# ─────────────────────────────────────────────────────────────────────────────

@auth_bp.route("/make-admin", methods=["POST"])
@jwt_required()
def make_admin():
    """
    Promote the currently logged-in user to admin.
    Requires the ADMIN_SECRET_KEY to be passed in the request body.

    Request body (JSON):
        secret_key (str): must match ADMIN_SECRET_KEY env variable
    """
    import os
    secret = os.getenv("ADMIN_SECRET_KEY", "").strip()
    if not secret:
        return jsonify({"error": "Admin promotion is disabled on this server."}), 403

    data = request.get_json(silent=True) or {}
    provided = data.get("secret_key", "").strip()

    if provided != secret:
        return jsonify({"error": "Invalid secret key."}), 403

    user_id = get_jwt_identity()
    user = db.session.get(User, user_id)
    if not user:
        return jsonify({"error": "User not found."}), 404

    user.role = "admin"
    db.session.commit()
    return jsonify({
        "message": f"{user.username} is now an admin.",
        "user": user.to_dict(include_sensitive=True),
    }), 200
