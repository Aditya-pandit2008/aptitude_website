import os
from app import create_app
from models import db, CodeChallenge, Question, Category

app = create_app()
with app.app_context():
    rows = db.session.query(CodeChallenge, Question).join(Question, CodeChallenge.question_id == Question.id).all()
    print(f"Total challenges: {len(rows)}")
    for c, q in rows:
        cat_name = q.category.name if q.category else "None"
        print(f"ID: {c.id} | Title: {c.title} | Category: {cat_name} | Difficulty: {q.difficulty} | Tags: {q.tags}")
