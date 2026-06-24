'''services/leaderboard.py'''
"""Compatibility shim for legacy imports.

The original code referenced ``services.leaderboard`` with functions
``record_score`` and ``get_top_scores``. In the refactored project the
actual implementation lives in :pymod:`services.leaderboard_service` and
exposes richer helpers such as ``update_leaderboard`` and ``get_top_n``.

To avoid breaking existing imports (e.g. in ``routes.coding``) we provide
a thin wrapper module that re‑exports the expected names while delegating
to the new service implementation.
"""



from typing import List, Dict

# Import the new service functions
from .leaderboard_service import (
    update_leaderboard as _update_leaderboard,
    get_top_n as _get_top_n,
)


def record_score(user_id: int) -> None:
    """Record a user's latest XP score.

    The historic API expected a ``record_score`` call that would recompute
    the leaderboard entry for the supplied user. Internally we simply call
    :func:`services.leaderboard_service.update_leaderboard` which performs
    the aggregation and rank recomputation.
    """
    _update_leaderboard(user_id)


def get_top_scores(limit: int = 10) -> List[Dict]:
    """Return the top *limit* users ordered by total score.

    This mirrors the previous ``get_top_scores`` helper. It forwards the
    request to :func:`services.leaderboard_service.get_top_n`.
    """
    return _get_top_n(limit)

__all__ = ["record_score", "get_top_scores"]
