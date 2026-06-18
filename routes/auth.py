"""
routes/auth.py
Authentication blueprint: register, login, logout, refresh token, profile.

Endpoints:
    POST /api/v1/auth/register   – create a new user account
    POST /api/v1/auth/login      – authenticate and receive JWT tokens
    POST /api/v1/auth/logout     – revoke current access token (JWT blacklist)
    POST /api/v1/auth/refresh    – exchange refresh token for new access token
    GET  /api/v1/auth/me         – return the authenticated user's profile
    PUT  /api/v1/auth/me         – update username or password
    DELETE /api/v1/auth/me       – delete account
    POST /api/v1/auth/make-admin – self-promote to admin (requires ADMIN_SECRET_KEY)
"""

import hmac
import os

from flask import Blueprint, request, jsonify
from flask_jwt_extended import (
    create_access_token, create_refresh_token,
    jwt_required, get_jwt_identity, get_jwt,
)

from extensions import limiter
from models import db, User, TokenBlocklist
from utils.validators import validate_registration, validate_login
from utils.response import success, error

auth_bp = Blueprint("auth", __name__)


# ─────────────────────────────────────────────────────────────────────────────
# Register
# ─────────────────────────────────────────────────────────────────────────────

@auth_bp.route("/register", methods=["POST"])
@limiter.limit("10 per minute")
def register():
    """
    Register a new user.

    Request body (JSON):
        username (str): 3-80 chars
        email    (str): valid email
        password (str): min 8 chars

    Returns 201 with user data + tokens on success.
    """
    data   = request.get_json(silent=True) or {}
    errors = validate_registration(data)
    if errors:
        return error("Validation failed.", 422, details=errors)

    username = data["username"].strip()
    email    = data["email"].strip().lower()

    # Uniqueness checks
    if User.query.filter_by(email=email).first():
        return error("Email already registered.", 409)
    if User.query.filter_by(username=username).first():
        return error("Username already taken.", 409)

    user = User(username=username, email=email)
    user.set_password(data["password"])
    db.session.add(user)
    db.session.commit()

    access_token  = create_access_token(identity=str(user.id))
    refresh_token = create_refresh_token(identity=str(user.id))

    return success({
        "message":       "Account created successfully.",
        "user":          user.to_dict(include_sensitive=True),
        "access_token":  access_token,
        "refresh_token": refresh_token,
    }, 201)


# ─────────────────────────────────────────────────────────────────────────────
# Login
# ─────────────────────────────────────────────────────────────────────────────

@auth_bp.route("/login", methods=["POST"])
@limiter.limit("10 per minute")
def login():
    """
    Authenticate a user and return JWT tokens.

    Request body (JSON):
        email    (str)
        password (str)
    """
    data   = request.get_json(silent=True) or {}
    errors = validate_login(data)
    if errors:
        return error("Validation failed.", 422, details=errors)

    user = User.query.filter_by(email=data["email"].strip().lower()).first()

    # Use the same generic message for both "user not found" and "wrong password"
    # to prevent user enumeration attacks.
    if not user or not user.check_password(data["password"]):
        return error("Invalid email or password.", 401)

    access_token  = create_access_token(identity=str(user.id))
    refresh_token = create_refresh_token(identity=str(user.id))

    return success({
        "message":       "Login successful.",
        "user":          user.to_dict(include_sensitive=True),
        "access_token":  access_token,
        "refresh_token": refresh_token,
    }, 200)


# ─────────────────────────────────────────────────────────────────────────────
# Logout
# ─────────────────────────────────────────────────────────────────────────────

@auth_bp.route("/logout", methods=["POST"])
@jwt_required()
def logout():
    """
    Revoke the current access token by adding its JTI to the blocklist.
    The token will be rejected on all subsequent requests.
    """
    jwt_payload = get_jwt()
    jti         = jwt_payload.get("jti")
    token_type  = jwt_payload.get("type", "access")

    # Only add to blocklist if not already there
    if not TokenBlocklist.query.filter_by(jti=jti).first():
        db.session.add(TokenBlocklist(jti=jti, token_type=token_type))
        db.session.commit()

    return success({"message": "Successfully logged out."}, 200)


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
    user_id    = get_jwt_identity()
    new_access = create_access_token(identity=user_id)
    return success({"access_token": new_access}, 200)


# ─────────────────────────────────────────────────────────────────────────────
# Profile – read & update
# ─────────────────────────────────────────────────────────────────────────────

@auth_bp.route("/me", methods=["GET"])
@jwt_required()
def get_profile():
    """Return the authenticated user's profile (including email)."""
    user_id = int(get_jwt_identity())
    user    = db.session.get(User, user_id)
    if not user:
        return error("User not found.", 404)
    return success({"user": user.to_dict(include_sensitive=True)}, 200)


@auth_bp.route("/me", methods=["PUT"])
@jwt_required()
def update_profile():
    """
    Update username and/or password.

    Request body (JSON, all optional):
        username     (str)
        old_password (str) – required when changing password
        new_password (str) – min 8 chars
    """
    user_id = int(get_jwt_identity())
    user    = db.session.get(User, user_id)
    if not user:
        return error("User not found.", 404)

    data = request.get_json(silent=True) or {}

    if "username" in data:
        new_username = data["username"].strip()
        if len(new_username) < 3:
            return error("Username must be at least 3 characters.", 422)
        existing = User.query.filter_by(username=new_username).first()
        if existing and existing.id != user.id:
            return error("Username already taken.", 409)
        user.username = new_username

    if "new_password" in data:
        if not data.get("old_password"):
            return error("old_password is required to change password.", 422)
        if not user.check_password(data["old_password"]):
            return error("Current password is incorrect.", 401)
        if len(data["new_password"]) < 8:
            return error("New password must be at least 8 characters.", 422)
        user.set_password(data["new_password"])

    db.session.commit()
    return success({"message": "Profile updated.", "user": user.to_dict(include_sensitive=True)}, 200)


@auth_bp.route("/me", methods=["DELETE"])
@jwt_required()
def delete_profile():
    """Delete the currently authenticated user's account."""
    user_id = int(get_jwt_identity())
    user    = db.session.get(User, user_id)
    if not user:
        return error("User not found.", 404)

    db.session.delete(user)
    db.session.commit()
    return success({"message": "Account deleted successfully."}, 200)


# ─────────────────────────────────────────────────────────────────────────────
# Admin self-promotion (secured by ADMIN_SECRET_KEY env variable)
# ─────────────────────────────────────────────────────────────────────────────

@auth_bp.route("/make-admin", methods=["POST"])
@jwt_required()
@limiter.limit("5 per hour")
def make_admin():
    """
    Promote the currently logged-in user to admin.
    Requires the ADMIN_SECRET_KEY to be passed in the request body.

    Request body (JSON):
        secret_key (str): must match ADMIN_SECRET_KEY env variable
    """
    secret = os.getenv("ADMIN_SECRET_KEY", "").strip()
    if not secret:
        return error("Admin promotion is disabled on this server.", 403)

    data     = request.get_json(silent=True) or {}
    provided = data.get("secret_key", "").strip()

    # Constant-time comparison to prevent timing attacks
    if not hmac.compare_digest(provided, secret):
        return error("Invalid secret key.", 403)

    user_id = int(get_jwt_identity())
    user    = db.session.get(User, user_id)
    if not user:
        return error("User not found.", 404)

    user.role = "admin"
    db.session.commit()
    return success({
        "message": f"{user.username} is now an admin.",
        "user":    user.to_dict(include_sensitive=True),
    }, 200)


# ─────────────────────────────────────────────────────────────────────────────
# Forgot Password
# ─────────────────────────────────────────────────────────────────────────────

@auth_bp.route("/forgot-password", methods=["POST"])
@limiter.limit("5 per minute")
def forgot_password():
    """
    Reset user password by email.
    Request body (JSON):
        email        (str)
        new_password (str)
    """
    data = request.get_json(silent=True) or {}
    email = data.get("email", "").strip().lower()
    new_password = data.get("new_password", "")

    if not email or not new_password:
        return error("Email and new password are required.", 422)

    if len(new_password) < 8:
        return error("Password must be at least 8 characters long.", 422)

    user = User.query.filter_by(email=email).first()
    if not user:
        return error("No account associated with this email address.", 404)

    user.set_password(new_password)
    db.session.commit()
    return success({"message": "Password has been reset successfully."}, 200)

