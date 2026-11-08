"""機器からの生データのアップロードの流れ。

1. start   ：送るファイルの一覧を受け付け、走行名を付け、ファイルごとの PUT 用 URL を返す
             （途中で切れた機器が同じ走行名で呼べば、URL を出し直す。
              同じ SD の走行を送り終えていれば、新しく作らずにその走行名を返す。送るファイルは無し）
2. （機器が URL に直接 PUT する。ここは通らない）
3. complete：置かれたファイルの大きさが申告どおりかを確かめ、完了の合図を置く
"""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime

from ..domain.device import Device
from ..domain.exceptions import UploadConflictError, UploadNotFoundError
from ..domain.raw_upload import (
    UploadSession,
    check_local_session,
    check_ride_id,
    fingerprint,
    parse_file_list,
    ride_id_candidates,
)
from ..repositories.raw_upload_repository import RawUploadRepository


@dataclass(frozen=True)
class UploadTicket:
    """機器に返すもの：走行名と、ファイルごとの PUT 用 URL。"""

    ride_id: str
    expires_in: int
    urls: dict[str, str]
    # new：新しい走行／resumed：途中から／already_uploaded：同じ SD の走行を送り終えている（送るものは無い）
    status: str = "new"


class RawUploadService:
    def __init__(self, repository: RawUploadRepository, now: Callable[[], datetime], url_seconds: int) -> None:
        self._repository = repository
        self._now = now
        self._url_seconds = url_seconds

    # ---------------------------------------------------------------- 1. 受け付け
    def start(self, device: Device, local_session: str, files: list[tuple[str, int]], ride_id: str | None = None) -> UploadTicket:
        if ride_id:
            session = self._resume(device, check_ride_id(ride_id))
            return self._ticket_for(session, "resumed")
        local_session = check_local_session(local_session)
        raw_files = parse_file_list(files)
        existing = self._repository.find_fingerprint(fingerprint(local_session, raw_files))
        if existing and self._repository.is_complete(existing):
            return UploadTicket(ride_id=existing, expires_in=self._url_seconds, urls={}, status="already_uploaded")
        return self._ticket_for(self._create(device, local_session, raw_files), "new")

    def _create(self, device: Device, local_session: str, raw_files: tuple) -> UploadSession:
        now = self._now()
        for candidate in ride_id_candidates(now):
            session = UploadSession(candidate, device.device_id, local_session, raw_files, now.isoformat())
            if self._repository.create_session(session):
                return session
        raise UploadConflictError("走行名を決められませんでした。少し待ってからやり直してください")

    def _resume(self, device: Device, ride_id: str) -> UploadSession:
        session = self._owned_session(device, ride_id)
        if self._repository.is_complete(ride_id):
            raise UploadConflictError(f"{ride_id} は送信済みです")
        return session

    def _ticket_for(self, session: UploadSession, status: str) -> UploadTicket:
        urls = {file.name: self._repository.upload_url(session.ride_id, file.name, self._url_seconds) for file in session.files}
        return UploadTicket(ride_id=session.ride_id, expires_in=self._url_seconds, urls=urls, status=status)

    # ---------------------------------------------------------------- 3. 完了
    def complete(self, device: Device, ride_id: str) -> bool:
        """完了の合図を置く。既に完了していれば何もせず False（機器がやり直しても困らないように）。"""
        session = self._owned_session(device, check_ride_id(ride_id))
        mark = fingerprint(session.local_session, session.files)
        if self._repository.is_complete(ride_id):
            self._repository.save_fingerprint(mark, session)  # 印を付ける前に送り終えた走行にも付ける（何度呼んでも同じ）
            return False
        mismatches = self._size_mismatches(session)
        if mismatches:
            raise UploadConflictError(f"申告と違うファイルがあります：{', '.join(mismatches)}")
        self._repository.mark_complete(session)
        self._repository.save_fingerprint(mark, session)
        return True

    def _size_mismatches(self, session: UploadSession) -> list[str]:
        mismatches = []
        for file in session.files:
            actual = self._repository.uploaded_size(session.ride_id, file.name)
            if actual != file.size:
                mismatches.append(f"{file.name}（申告 {file.size}、実際 {actual if actual is not None else 'なし'}）")
        return mismatches

    # ---------------------------------------------------------------- 共通
    def _owned_session(self, device: Device, ride_id: str) -> UploadSession:
        session = self._repository.find_session(ride_id)
        if session is None or not session.belongs_to(device.device_id):
            # ほかの機器の走行かどうかは教えない
            raise UploadNotFoundError(f"{ride_id} の受け付けがありません")
        return session
