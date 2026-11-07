"""GET /api/me：ログイン中のユーザーと、そのユーザーが見るデータセット。"""

from fastapi import APIRouter, Depends

from ..dependencies import get_current_user, get_data_file_service
from ..domain.user import User
from ..schemas.responses import MeResponse
from ..services.data_file_service import DataFileService

router = APIRouter(tags=["me"])


@router.get("/me", response_model=MeResponse)
def me(
    user: User = Depends(get_current_user),
    service: DataFileService = Depends(get_data_file_service),
) -> MeResponse:
    dataset = service.dataset_for(user)
    return MeResponse(username=user.username, groups=list(user.groups), dataset=dataset.value)
