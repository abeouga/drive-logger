"""走行の台帳と処理の記録（#16・#17）。応答の形は contracts/api/。

GET    /api/rides                              画面に出す走行の一覧（admin は include_deleted=true で消した走行も）
DELETE /api/rides/{ride_id}                    走行を画面と学習から外す（admin。生データは残す）
POST   /api/rides/{ride_id}/restore            外した走行を戻す（admin）
GET    /api/rides/{ride_id}/runs               その走行を処理した記録（新しい順）
PUT    /api/rides/{ride_id}/published-run      画面に出す結果を、前の処理の結果などに切り替える（admin）
"""

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field

from ..dependencies import get_current_user, get_ride_service
from ..domain.user import User
from ..services.ride_service import RideService

router = APIRouter(prefix="/rides", tags=["rides"])

NO_STORE_HEADERS = {"Cache-Control": "private, no-store"}


class PublishedRunRequest(BaseModel):
    run_id: str = Field(description="画面に出す処理の ID（その走行の処理の記録にあるもの）")


@router.get("")
def list_rides(
    include_deleted: bool = Query(False, description="admin だけ：消した走行と机上の走行も入れる"),
    user: User = Depends(get_current_user),
    service: RideService = Depends(get_ride_service),
) -> dict:
    return {"rides": service.list_rides(user, include_deleted)}


@router.delete("/{ride_id}")
def delete_ride(ride_id: str, user: User = Depends(get_current_user), service: RideService = Depends(get_ride_service)) -> dict:
    return service.delete(user, ride_id)


@router.post("/{ride_id}/restore")
def restore_ride(ride_id: str, user: User = Depends(get_current_user), service: RideService = Depends(get_ride_service)) -> dict:
    return service.restore(user, ride_id)


@router.get("/{ride_id}/runs")
def list_runs(ride_id: str, user: User = Depends(get_current_user), service: RideService = Depends(get_ride_service)) -> dict:
    return {"ride_id": ride_id, "runs": service.list_runs(user, ride_id)}


@router.put("/{ride_id}/published-run")
def set_published_run(
    ride_id: str,
    body: PublishedRunRequest,
    user: User = Depends(get_current_user),
    service: RideService = Depends(get_ride_service),
) -> dict:
    return service.set_published_run(user, ride_id, body.run_id)
