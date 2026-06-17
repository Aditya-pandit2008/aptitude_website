"""
models.py
SQLAlchemy ORM models for the Placement Preparation Platform.

Models:
    User            – registered user with XP, streak, and role
    Category        – topic category (Quantitative, Verbal, Logical, …)
    Question        – aptitude / interview question with options
    TestAttempt     – a single test session with score history
    TestAnswer      – per-question answer within a test attempt
    Bookmark        – saved questions per user
    LeaderboardEntry– aggregated score / rank snapshot
    DailyChallenge  – one question featured per day
"""

from datetime import datetime, timezone
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash

db = SQLAlchemy()


# ─────────────────────────────────────────────────────────────────────────────
# Helper
# ─────────────────────────────────────────────────────────────────────────────

def utcnow():
    """Timezone-aware UTC timestamp helper."""
    return datetime.now(timezone.utc)


# ─────────────────────────────────────────────────────────────────────────────
# User
# ─────────────────────────────────────────────────────────────────────────────

class User(db.Model):
    """Registered platform user."""

    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False, index=True)
    email = db.Column(db.String(120), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(256), nullable=False)
    role = db.Column(db.String(20), default="student")   # student | admin

    # Gamification
    total_xp = db.Column(db.Integer, default=0)
    daily_streak = db.Column(db.Integer, default=0)
    last_active_date = db.Column(db.Date, nullable=True)

    # Timestamps
    created_at = db.Column(db.DateTime(timezone=True), default=utcnow)
    updated_at = db.Column(db.DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    # Relationships
    test_attempts = db.relationship("TestAttempt", back_populates="user", cascade="all, delete-orphan", lazy="dynamic")
    bookmarks = db.relationship("Bookmark", back_populates="user", cascade="all, delete-orphan", lazy="dynamic")
    leaderboard_entry = db.relationship("LeaderboardEntry", back_populates="user", cascade="all, delete-orphan", uselist=False)

    # ── Password helpers ──────────────────────────────────────────────────────

    def set_password(self, password: str):
        """Hash and store a plain-text password."""
        self.password_hash = generate_password_hash(password)

    def check_password(self, password: str) -> bool:
        """Return True if the given password matches the stored hash."""
        return check_password_hash(self.password_hash, password)

    def to_dict(self, include_sensitive=False) -> dict:
        """Serialize user to JSON-safe dict."""
        data = {
            "id": self.id,
            "username": self.username,
            "email": self.email if include_sensitive else None,
            "role": self.role,
            "total_xp": self.total_xp,
            "daily_streak": self.daily_streak,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
        if not include_sensitive:
            data.pop("email")
        return data

    def __repr__(self):
        return f"<User {self.username}>"


# ─────────────────────────────────────────────────────────────────────────────
# Category
# ─────────────────────────────────────────────────────────────────────────────

class Category(db.Model):
    """Topic category for questions (e.g. Quantitative, Verbal, Logical)."""

    __tablename__ = "categories"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), unique=True, nullable=False)
    description = db.Column(db.Text, nullable=True)
    icon = db.Column(db.String(50), nullable=True)   # emoji or icon name

    # Relationships
    questions = db.relationship("Question", back_populates="category", lazy="dynamic")

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "icon": self.icon,
            "question_count": self.questions.count(),
        }

    def __repr__(self):
        return f"<Category {self.name}>"


# ─────────────────────────────────────────────────────────────────────────────
# Question
# ─────────────────────────────────────────────────────────────────────────────

class Question(db.Model):
    """
    An aptitude / interview question.
    Options are stored as a JSON-serialised list; correct_option is 0-based index.
    """

    __tablename__ = "questions"

    DIFFICULTY_LEVELS = ("easy", "medium", "hard")

    id = db.Column(db.Integer, primary_key=True)
    category_id = db.Column(db.Integer, db.ForeignKey("categories.id"), nullable=False)
    text = db.Column(db.Text, nullable=False)

    # MCQ support – store options as pipe-separated string for SQLite compatibility
    # Format: "Option A|Option B|Option C|Option D"
    options_raw = db.Column(db.Text, nullable=True)
    correct_option = db.Column(db.Integer, nullable=False)   # 0-based index

    explanation = db.Column(db.Text, nullable=True)
    difficulty = db.Column(db.String(10), default="medium")
    tags = db.Column(db.String(255), nullable=True)          # comma-separated tags
    is_active = db.Column(db.Boolean, default=True)

    created_by = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    created_at = db.Column(db.DateTime(timezone=True), default=utcnow)
    updated_at = db.Column(db.DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    # Relationships
    category = db.relationship("Category", back_populates="questions")
    bookmarks = db.relationship("Bookmark", back_populates="question", lazy="dynamic")
    test_answers = db.relationship("TestAnswer", back_populates="question", lazy="dynamic")

    # ── Property helpers ──────────────────────────────────────────────────────

    @property
    def options(self) -> list:
        """Return options as a Python list."""
        if not self.options_raw:
            return []
        return self.options_raw.split("|")

    @options.setter
    def options(self, options_list: list):
        """Set options from a Python list."""
        self.options_raw = "|".join(str(o) for o in options_list)

    @property
    def tag_list(self) -> list:
        if not self.tags:
            return []
        return [t.strip() for t in self.tags.split(",") if t.strip()]

    def to_dict(self, include_answer=False) -> dict:
        data = {
            "id": self.id,
            "category_id": self.category_id,
            "category_name": self.category.name if self.category else None,
            "text": self.text,
            "options": self.options,
            "difficulty": self.difficulty,
            "tags": self.tag_list,
            "explanation": self.explanation,
            "is_active": self.is_active,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
        if include_answer:
            data["correct_option"] = self.correct_option
        return data

    def __repr__(self):
        return f"<Question {self.id}: {self.text[:40]}>"


# ─────────────────────────────────────────────────────────────────────────────
# TestAttempt
# ─────────────────────────────────────────────────────────────────────────────

class TestAttempt(db.Model):
    """A single test session taken by a user."""

    __tablename__ = "test_attempts"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    category_id = db.Column(db.Integer, db.ForeignKey("categories.id"), nullable=True)

    total_questions = db.Column(db.Integer, default=0)
    correct_answers = db.Column(db.Integer, default=0)
    score = db.Column(db.Float, default=0.0)          # raw score (XP)
    accuracy = db.Column(db.Float, default=0.0)       # percentage 0-100
    time_taken = db.Column(db.Integer, default=0)     # seconds
    xp_earned = db.Column(db.Integer, default=0)

    completed_at = db.Column(db.DateTime(timezone=True), default=utcnow)

    # Relationships
    user = db.relationship("User", back_populates="test_attempts")
    category = db.relationship("Category")
    answers = db.relationship("TestAnswer", back_populates="attempt",
                              cascade="all, delete-orphan", lazy="dynamic")

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "user_id": self.user_id,
            "category_id": self.category_id,
            "category_name": self.category.name if self.category else "Mixed",
            "total_questions": self.total_questions,
            "correct_answers": self.correct_answers,
            "score": self.score,
            "accuracy": round(self.accuracy, 2),
            "time_taken": self.time_taken,
            "xp_earned": self.xp_earned,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
        }

    def __repr__(self):
        return f"<TestAttempt {self.id} user={self.user_id} score={self.score}>"


# ─────────────────────────────────────────────────────────────────────────────
# TestAnswer
# ─────────────────────────────────────────────────────────────────────────────

class TestAnswer(db.Model):
    """Individual answer record within a TestAttempt."""

    __tablename__ = "test_answers"

    id = db.Column(db.Integer, primary_key=True)
    attempt_id = db.Column(db.Integer, db.ForeignKey("test_attempts.id"), nullable=False)
    question_id = db.Column(db.Integer, db.ForeignKey("questions.id"), nullable=False)
    selected_option = db.Column(db.Integer, nullable=True)  # None = skipped
    is_correct = db.Column(db.Boolean, default=False)
    time_spent = db.Column(db.Integer, default=0)            # seconds on this question

    # Relationships
    attempt = db.relationship("TestAttempt", back_populates="answers")
    question = db.relationship("Question", back_populates="test_answers")

    def to_dict(self) -> dict:
        question = self.question
        return {
            "question_id": self.question_id,
            "selected_option": self.selected_option,
            "correct_option": question.correct_option,
            "is_correct": self.is_correct,
            "time_spent": self.time_spent,
            "question": question.to_dict(include_answer=True) if question else None,
        }


# ─────────────────────────────────────────────────────────────────────────────
# Bookmark
# ─────────────────────────────────────────────────────────────────────────────

class Bookmark(db.Model):
    """A question saved by a user for later review."""

    __tablename__ = "bookmarks"
    __table_args__ = (
        db.UniqueConstraint("user_id", "question_id", name="uq_user_question_bookmark"),
    )

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    question_id = db.Column(db.Integer, db.ForeignKey("questions.id"), nullable=False)
    note = db.Column(db.Text, nullable=True)           # optional personal note
    created_at = db.Column(db.DateTime(timezone=True), default=utcnow)

    # Relationships
    user = db.relationship("User", back_populates="bookmarks")
    question = db.relationship("Question", back_populates="bookmarks")

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "question": self.question.to_dict(),
            "note": self.note,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


# ─────────────────────────────────────────────────────────────────────────────
# LeaderboardEntry
# ─────────────────────────────────────────────────────────────────────────────

class LeaderboardEntry(db.Model):
    """
    Aggregated leaderboard snapshot per user.
    Updated after every test attempt via leaderboard_service.
    """

    __tablename__ = "leaderboard"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), unique=True, nullable=False)
    total_score = db.Column(db.Float, default=0.0)
    tests_taken = db.Column(db.Integer, default=0)
    avg_accuracy = db.Column(db.Float, default=0.0)
    rank = db.Column(db.Integer, nullable=True)
    updated_at = db.Column(db.DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    # Relationships
    user = db.relationship("User", back_populates="leaderboard_entry")

    def to_dict(self) -> dict:
        return {
            "rank": self.rank,
            "user_id": self.user_id,
            "username": self.user.username if self.user else None,
            "total_score": round(self.total_score, 2),
            "tests_taken": self.tests_taken,
            "avg_accuracy": round(self.avg_accuracy, 2),
            "total_xp": self.user.total_xp if self.user else 0,
        }


# ─────────────────────────────────────────────────────────────────────────────
# DailyChallenge
# ─────────────────────────────────────────────────────────────────────────────

class DailyChallenge(db.Model):
    """One featured question per calendar day."""

    __tablename__ = "daily_challenges"

    id = db.Column(db.Integer, primary_key=True)
    question_id = db.Column(db.Integer, db.ForeignKey("questions.id"), nullable=False)
    challenge_date = db.Column(db.Date, unique=True, nullable=False)
    bonus_xp = db.Column(db.Integer, default=50)

    question = db.relationship("Question")

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "challenge_date": self.challenge_date.isoformat(),
            "bonus_xp": self.bonus_xp,
            "question": self.question.to_dict() if self.question else None,
        }
