import json
from models import User, TokenBlocklist, db

def test_register_success(client):
    payload = {
        "username": "newuser",
        "email": "newuser@example.com",
        "password": "password123"
    }
    response = client.post("/api/v1/auth/register", json=payload)
    assert response.status_code == 201
    data = response.get_json()
    assert data["success"] is True
    assert "access_token" in data["data"]
    assert data["data"]["user"]["username"] == "newuser"

def test_register_duplicate(client, test_user):
    payload = {
        "username": test_user.username,
        "email": "another@example.com",
        "password": "password123"
    }
    response = client.post("/api/v1/auth/register", json=payload)
    assert response.status_code == 409
    data = response.get_json()
    assert data["success"] is False

def test_login_success(client, test_user):
    payload = {
        "email": "test@example.com",
        "password": "password123"
    }
    response = client.post("/api/v1/auth/login", json=payload)
    assert response.status_code == 200
    data = response.get_json()
    assert data["success"] is True
    assert "access_token" in data["data"]

def test_login_invalid(client, test_user):
    payload = {
        "email": "test@example.com",
        "password": "wrongpassword"
    }
    response = client.post("/api/v1/auth/login", json=payload)
    assert response.status_code == 401
    data = response.get_json()
    assert data["success"] is False

def test_logout(client, auth_headers, app):
    # Call logout
    response = client.post("/api/v1/auth/logout", headers=auth_headers)
    assert response.status_code == 200
    data = response.get_json()
    assert data["success"] is True

    # Try to access protected route with revoked token
    response_me = client.get("/api/v1/auth/me", headers=auth_headers)
    assert response_me.status_code == 401

def test_get_profile(client, auth_headers):
    response = client.get("/api/v1/auth/me", headers=auth_headers)
    assert response.status_code == 200
    data = response.get_json()
    assert data["success"] is True
    assert data["data"]["user"]["username"] == "testuser"

def test_forgot_password_success(client, test_user):
    payload = {
        "email": "test@example.com",
        "new_password": "newpassword123"
    }
    response = client.post("/api/v1/auth/forgot-password", json=payload)
    assert response.status_code == 200
    data = response.get_json()
    assert data["success"] is True

    # Try logging in with the new password
    login_payload = {
        "email": "test@example.com",
        "password": "newpassword123"
    }
    login_res = client.post("/api/v1/auth/login", json=login_payload)
    assert login_res.status_code == 200
    assert login_res.get_json()["success"] is True

def test_forgot_password_failures(client, test_user):
    # Short password
    payload_short = {
        "email": "test@example.com",
        "new_password": "short"
    }
    res = client.post("/api/v1/auth/forgot-password", json=payload_short)
    assert res.status_code == 422

    # Non-existent email
    payload_missing = {
        "email": "nonexistent@example.com",
        "new_password": "newpassword123"
    }
    res = client.post("/api/v1/auth/forgot-password", json=payload_missing)
    assert res.status_code == 404

