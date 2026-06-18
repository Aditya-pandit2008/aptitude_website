from datetime import date, timedelta
from models import Question, Category, User, db
from services.evaluation import evaluate_test

def test_evaluate_test_logic(app, test_user):
    with app.app_context():
        # Re-fetch the user inside the active transaction context
        db_user = db.session.get(User, test_user.id)
        cat = Category.query.first()
        q1 = Question(category_id=cat.id, text="Q1", correct_option=0, difficulty="easy")
        q1.options = ["A", "B", "C", "D"]
        db.session.add(q1)
        db.session.commit()
        
        q1_id = q1.id
        db.session.refresh(db_user)

        # Evaluate test
        payload = [{"question_id": q1_id, "selected_option": 0, "time_spent": 10}]
        result = evaluate_test(db_user, payload, time_taken=10, category_id=cat.id)

        assert result["correct_answers"] == 1
        assert result["accuracy"] == 100.0
        # XP_PER_CORRECT_ANSWER = 10, XP_PER_TEST_COMPLETION = 25 -> 35 XP
        assert result["xp_earned"] == 35
        assert db_user.total_xp == 35
        assert db_user.daily_streak == 1

def test_evaluate_test_streak_bonus(app, test_user):
    with app.app_context():
        db_user = db.session.get(User, test_user.id)
        # Set last active to yesterday to check streak increment
        db_user.last_active_date = date.today() - timedelta(days=1)
        db_user.daily_streak = 1
        db_user.total_xp = 10
        db.session.commit()

        cat = Category.query.first()
        q1 = Question(category_id=cat.id, text="Q1", correct_option=0, difficulty="easy")
        q1.options = ["A", "B", "C", "D"]
        db.session.add(q1)
        db.session.commit()

        q1_id = q1.id
        db.session.refresh(db_user)

        payload = [{"question_id": q1_id, "selected_option": 0, "time_spent": 10}]
        evaluate_test(db_user, payload, time_taken=10, category_id=cat.id)

        # Streak becomes 2.
        # Base XP: 10 (correct) + 25 (completion) = 35 XP
        # Streak bonus: 5 (bonus) * 2 (streak) = 10 XP
        # Total added: 45 XP
        assert db_user.daily_streak == 2
        assert db_user.total_xp == 10 + 45
