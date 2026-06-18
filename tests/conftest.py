import pytest
from app import create_app
from models import db, User, Category, Question
from flask_jwt_extended import create_access_token

@pytest.fixture
def app():
    app = create_app("testing")
    with app.app_context():
        yield app
        db.session.remove()
        db.drop_all()

@pytest.fixture
def client(app):
    return app.test_client()

@pytest.fixture
def runner(app):
    return app.test_cli_runner()

@pytest.fixture
def test_user(app):
    with app.app_context():
        user = User(username="testuser", email="test@example.com")
        user.set_password("password123")
        db.session.add(user)
        db.session.commit()
        # Fetch fresh copy from session
        db.session.refresh(user)
        return user

@pytest.fixture
def auth_headers(app, test_user):
    with app.app_context():
        token = create_access_token(identity=str(test_user.id))
        return {"Authorization": f"Bearer {token}"}

@pytest.fixture
def admin_user(app):
    with app.app_context():
        user = User(username="adminuser", email="admin@example.com", role="admin")
        user.set_password("password123")
        db.session.add(user)
        db.session.commit()
        db.session.refresh(user)
        return user

@pytest.fixture
def admin_headers(app, admin_user):
    with app.app_context():
        token = create_access_token(identity=str(admin_user.id))
        return {"Authorization": f"Bearer {token}"}
