"""機器（ESP32）からのアップロードの入口。

POST /api/device/uploads                    送るファイルの一覧 → 走行名と PUT 用 URL
POST /api/device/uploads/{ride_id}/complete 送り終わった → 確かめて完了の合図を置く
どちらも Authorization: Device <機器ID>.<トークン> が必要。
"""

from fastapi import APIRouter, Depends

from ..device_dependencies import get_device, get_raw_upload_service
from ..domain.device import Device
from ..schemas.device_upload import CompleteUploadResponse, StartUploadRequest, StartUploadResponse, UploadTarget
from ..services.raw_upload_service import RawUploadService

router = APIRouter(prefix="/device", tags=["device"])


@router.post("/uploads", response_model=StartUploadResponse)
def start_upload(
    body: StartUploadRequest,
    device: Device = Depends(get_device),
    service: RawUploadService = Depends(get_raw_upload_service),
) -> StartUploadResponse:
    files = [(file.name, file.size) for file in body.files]
    ticket = service.start(device, body.local_session, files, body.ride_id)
    uploads = [UploadTarget(name=name, url=url) for name, url in ticket.urls.items()]
    return StartUploadResponse(ride_id=ticket.ride_id, expires_in=ticket.expires_in, uploads=uploads, status=ticket.status)


@router.post("/uploads/{ride_id}/complete", response_model=CompleteUploadResponse)
def complete_upload(
    ride_id: str,
    device: Device = Depends(get_device),
    service: RawUploadService = Depends(get_raw_upload_service),
) -> CompleteUploadResponse:
    completed_now = service.complete(device, ride_id)
    return CompleteUploadResponse(ride_id=ride_id, status="complete" if completed_now else "already_complete")
