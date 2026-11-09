"""AI order insights endpoint (batch 10, D9; AI-01…AI-09).

    POST /api/v1/insights/question   customer only; the model context is
                                     always the caller's own orders.

Security notes (D9):
- Role check only (customer); the *resource* is the caller's own order
  history by construction — there is no cross-user resource here, because
  the customer ID is the token's subject, not a request parameter.
- The OpenAI key is backend-only; responses and logs never contain it.
- Without a configured key: 200 with ``provider="unconfigured"``,
  ``answer=None`` and the exact app-computed stats (clear degradation, no
  fake AI output).
"""
from typing import Annotated, Callable, Optional

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ...core import constants as C
from ...core.config import Settings
from ...core.deps import build_get_current_user, build_require_roles
from ...db.models import User
from ...db.session import SessionFactory
from ...schemas.insights import InsightIn, InsightOut
from ...services.insights import build_insights_service


def build_insights_router(
    session_factory: SessionFactory,
    settings: Settings,
    openai_client_factory: Optional[Callable[[], object]] = None,
) -> APIRouter:
    router = APIRouter()
    get_current_user = build_get_current_user(session_factory, settings)
    require_customer = build_require_roles(get_current_user, C.ROLE_CUSTOMER)
    service = build_insights_service(settings, openai_client_factory=openai_client_factory)
    Db = Annotated[Session, Depends(session_factory.get)]
    UserDep = Annotated[User, Depends(require_customer)]

    @router.post(
        "/insights/question",
        response_model=InsightOut,
        responses={
            403: {"description": "ROLE_FORBIDDEN — customers only"},
            422: {"description": "QUESTION_EMPTY / QUESTION_TOO_LONG"},
            429: {"description": "RATE_LIMITED (app) / AI_UPSTREAM_RATE_LIMITED (provider)"},
            502: {"description": "AI_UPSTREAM_ERROR"},
            504: {"description": "AI_TIMEOUT"},
        },
    )
    def question(payload: InsightIn, user: UserDep, db: Db) -> InsightOut:
        result = service.answer_question(db, user, payload.question)
        return InsightOut(answer=result.answer, provider=result.provider, stats=result.stats)

    return router
