"""GET /api/data/{file_name}：ログイン中のユーザーのデータセットから、ファイルを 1 つ返す。

例：/api/data/rides.json、/api/data/ride_ride_004.json、/api/data/spec_ride_004.png
"""

from fastapi import APIRouter, Depends, Response

from ..dependencies import get_current_user, get_data_file_service
from ..domain.user import User
from ..services.data_file_service import DataFileService

router = APIRouter(tags=["data"])

# 走行データはログインした人だけのもの。ブラウザや CloudFront に残さない
NO_STORE_HEADERS = {"Cache-Control": "private, no-store"}


@router.get("/data/{file_name}")
def read_data_file(
    file_name: str,
    user: User = Depends(get_current_user),
    service: DataFileService = Depends(get_data_file_service),
) -> Response:
    data_file = service.read_file(user, file_name)
    return Response(content=data_file.content, media_type=data_file.media_type, headers=NO_STORE_HEADERS)
