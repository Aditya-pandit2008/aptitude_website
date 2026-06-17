"""
backend/ai_service.py  (legacy shim — delegates to services/ai_service.py)

Fix applied (2026-06-11):
    Replaced raw urllib HTTP calls with the official `groq` Python SDK.
    Raw urllib was blocked by Cloudflare with error 403 / code 1010.
"""

from services.ai_service import (   # noqa: F401  (re-export for backwards compat)
    explain_question,
    generate_similar_questions,
    generate_aptitude_questions,
    generate_study_plan,
    generate_interview_questions,
)
