import os
from app import create_app
from models import db, Question, Category, CodeChallenge

app = create_app()
with app.app_context():
    # Map from challenge ID to correct topic tag
    topic_mapping = {
        1: "Data Structures",
        2: "Data Structures",
        3: "Algorithms",
        4: "Algorithms",
        5: "Data Structures",
        6: "Data Structures",
        7: "Data Structures",
        8: "Data Structures",
        9: "Algorithms",
        10: "Algorithms",
        11: "Algorithms",
        12: "Math",
        13: "Strings",
        14: "Algorithms",
        15: "Algorithms",
        16: "Strings",
        17: "Strings",
        18: "Strings"
    }

    # Fetch/verify database categories
    dsa_category = Category.query.filter(Category.name.ilike("%DSA%")).first()
    quant_category = Category.query.filter(Category.name.ilike("%Quantitative%")).first()

    rows = db.session.query(CodeChallenge, Question).join(Question, CodeChallenge.question_id == Question.id).all()
    
    updated_count = 0
    for challenge, question in rows:
        topic = topic_mapping.get(challenge.id)
        if topic:
            # Update tags
            new_tags = f"groq-ai,coding,{topic}"
            question.tags = new_tags
            
            # Map category_id in DB to proper Category (DSA for programming, Quantitative for Math)
            if topic == "Math":
                if quant_category:
                    question.category_id = quant_category.id
            else:
                if dsa_category:
                    question.category_id = dsa_category.id
            
            updated_count += 1
            print(f"Updated Challenge ID {challenge.id} ({challenge.title}) -> Topic: {topic}, Cat: {question.category.name if question.category else 'None'}")

    db.session.commit()
    print(f"Successfully migrated {updated_count} challenges.")
