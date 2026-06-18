import json
from models import Question, Category, TestAttempt, db

def test_submit_test_success(client, auth_headers, app):
    with app.app_context():
        cat = Category.query.first()
        q1 = Question(category_id=cat.id, text="Q1", correct_option=0, difficulty="easy")
        q1.options = ["A", "B", "C", "D"]
        q2 = Question(category_id=cat.id, text="Q2", correct_option=1, difficulty="easy")
        q2.options = ["A", "B", "C", "D"]
        db.session.add_all([q1, q2])
        db.session.commit()
        q1_id = q1.id
        q2_id = q2.id
        cat_id = cat.id

    payload = {
        "answers": [
            {"question_id": q1_id, "selected_option": 0, "time_spent": 10},
            {"question_id": q2_id, "selected_option": 1, "time_spent": 15}
        ],
        "time_taken": 25,
        "category_id": cat_id
    }
    response = client.post("/api/v1/tests/submit", json=payload, headers=auth_headers)
    assert response.status_code == 201
    data = response.get_json()
    assert data["success"] is True
    assert data["data"]["result"]["correct_answers"] == 2
    assert data["data"]["result"]["accuracy"] == 100.0

def test_get_history(client, auth_headers, app, test_user):
    with app.app_context():
        # Re-attach user to current session
        user_attached = db.session.get(test_user.__class__, test_user.id)
        attempt = TestAttempt(user_id=user_attached.id, total_questions=2, correct_answers=1, accuracy=50.0)
        db.session.add(attempt)
        db.session.commit()

    response = client.get("/api/v1/tests/history", headers=auth_headers)
    assert response.status_code == 200
    data = response.get_json()
    assert data["success"] is True
    assert len(data["data"]) == 1
    assert data["data"][0]["accuracy"] == 50.0
