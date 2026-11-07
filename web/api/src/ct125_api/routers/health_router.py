"""GET /api/health：動いているかの確認。ログイン不要（API Gateway でも認証を掛けない）。"""

from fastapi import APIRouter

from ..schemas.responses import HealthResponse

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse(status="ok")
