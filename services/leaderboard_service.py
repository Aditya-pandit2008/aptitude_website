from typing import List, Optional
from sqlalchemy import func
from models import db, LeaderboardEntry, TestAttempt, User


def update_leaderboard(user_id: int) -> None:
    """Recompute and persist leaderboard metrics for a single user and update ranks."""
    # Aggregate user's test stats
    stats = (
        db.session.query(
            func.coalesce(func.sum(TestAttempt.xp_earned), 0),
            func.count(TestAttempt.id),
            func.coalesce(func.avg(TestAttempt.accuracy), 0),
        )
        .filter(TestAttempt.user_id == user_id)
        .one()
    )

    total_xp_sum, tests_taken, avg_accuracy = stats

    # Use user's total_xp as the authoritative total score if available
    user = db.session.get(User, user_id)
    total_score = float(user.total_xp or total_xp_sum or 0)

    entry = LeaderboardEntry.query.filter_by(user_id=user_id).first()
    if not entry:
        entry = LeaderboardEntry(user_id=user_id)
        db.session.add(entry)

    entry.total_score = total_score
    entry.tests_taken = int(tests_taken or 0)
    entry.avg_accuracy = float(avg_accuracy or 0.0)

    db.session.flush()

    # Recompute ranks for all entries ordered by total_score desc, then tests_taken desc
    entries = LeaderboardEntry.query.order_by(LeaderboardEntry.total_score.desc(), LeaderboardEntry.tests_taken.desc()).all()
    for idx, e in enumerate(entries, start=1):
        e.rank = idx

    db.session.commit()


def get_top_n(n: int = 10) -> List[dict]:
    entries = (
        LeaderboardEntry.query.order_by(LeaderboardEntry.rank.asc()).limit(n).all()
    )
    return [e.to_dict() for e in entries]


def get_user_rank(user_id: int) -> Optional[dict]:
    e = LeaderboardEntry.query.filter_by(user_id=user_id).first()
    return e.to_dict() if e else None
