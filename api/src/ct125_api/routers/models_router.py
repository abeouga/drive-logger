"""モデルの記録と切り替え（#17）。応答の形は contracts/api/models.schema.json と contracts/records/model.schema.json。

GET /api/models                    モデルの版の一覧と、今使っている版
GET /api/models/{version}          その版の記録（model.json：使った走行・使わなかった理由・設定・ライブラリの版）
GET /api/models/{version}/notes    その版のナレッジ（notes.md）
PUT /api/models/current            今使うモデルを切り替える（admin。全走行の点数付けし直しは処理の Lambda が行う）
"""

from fastapi import APIRouter, Depends, Response
from pydantic import BaseModel, Field

from ..dependencies import get_current_user, get_ride_service
from ..domain.user import User
from ..services.ride_service import RideService

router = APIRouter(prefix="/models", tags=["models"])


class UseModelRequest(BaseModel):
    version: str = Field(description="切り替えるモデルの版")


@router.get("")
def list_models(user: User = Depends(get_current_user), service: RideService = Depends(get_ride_service)) -> dict:
    return service.list_models()


@router.put("/current", status_code=202)
def use_model(body: UseModelRequest, user: User = Depends(get_current_user), service: RideService = Depends(get_ride_service)) -> dict:
    return service.use_model(user, body.version)


@router.get("/{version}")
def model(version: str, user: User = Depends(get_current_user), service: RideService = Depends(get_ride_service)) -> dict:
    return service.model(version)


@router.get("/{version}/notes")
def model_notes(version: str, user: User = Depends(get_current_user), service: RideService = Depends(get_ride_service)) -> Response:
    return Response(content=service.model_notes(version), media_type="text/markdown; charset=utf-8")
