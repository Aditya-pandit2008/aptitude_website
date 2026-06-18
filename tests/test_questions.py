import json
from models import Question, Category, db

def test_list_categories(client):
    response = client.get("/api/v1/questions/categories")
    assert response.status_code == 200
    data = response.get_json()
    assert data["success"] is True
    assert len(data["data"]["categories"]) == 9
    assert data["data"]["categories"][0]["name"] == "Quantitative Aptitude"

def test_create_question_admin(client, admin_headers, app):
    with app.app_context():
        category = Category.query.first()
        cat_id = category.id

    payload = {
        "category_id": cat_id,
        "text": "What is 2 + 2?",
        "options": ["3", "4", "5", "6"],
        "correct_option": 1,
        "difficulty": "easy",
        "explanation": "2 + 2 equals 4",
        "tags": ["math", "easy"]
    }
    response = client.post("/api/v1/questions/", json=payload, headers=admin_headers)
    assert response.status_code == 201
    data = response.get_json()
    assert data["success"] is True
    assert data["data"]["question"]["text"] == "What is 2 + 2?"

def test_create_question_student_denied(client, auth_headers, app):
    with app.app_context():
        cat_id = Category.query.first().id

    payload = {
        "category_id": cat_id,
        "text": "What is 2 + 2?",
        "options": ["3", "4", "5", "6"],
        "correct_option": 1
    }
    response = client.post("/api/v1/questions/", json=payload, headers=auth_headers)
    assert response.status_code == 403

def test_list_questions(client, auth_headers, app):
    with app.app_context():
        cat = Category.query.first()
        q1 = Question(category_id=cat.id, text="Q1", correct_option=0, difficulty="easy")
        q1.options = ["A", "B", "C", "D"]
        q2 = Question(category_id=cat.id, text="Q2", correct_option=1, difficulty="hard")
        q2.options = ["A", "B", "C", "D"]
        db.session.add_all([q1, q2])
        db.session.commit()

    # Get list
    response = client.get("/api/v1/questions/", headers=auth_headers)
    assert response.status_code == 200
    data = response.get_json()
    assert data["success"] is True
    assert len(data["data"]) == 2

    # Filter by difficulty
    response_filtered = client.get("/api/v1/questions/?difficulty=hard", headers=auth_headers)
    assert response_filtered.status_code == 200
    data_filtered = response_filtered.get_json()
    assert len(data_filtered["data"]) == 1
    assert data_filtered["data"][0]["text"] == "Q2"
