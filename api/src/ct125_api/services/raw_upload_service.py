"""機器からの生データのアップロードの流れ。

1. start   ：送るファイルの一覧を受け付け、走行名を付け、ファイルごとの PUT 用 URL を返す
             （途中で切れた機器が同じ走行名で呼べば、URL を出し直す。
              同じ SD の走行を送り終えていれば、新しく作らずにその走行名を返す。送るファイルは無し。
              同じ機器に同じ SD の走行の送りかけがあれば、新しく作らずにその続きを返す（#135））
2. （機器が URL に直接 PUT する。ここは通らない）
3. complete：置かれたファイルの大きさが申告どおりかを確かめ、完了の合図を置く

送り終えた走行に、後から書いた走行メモ（notes.md など）を足すときも同じ手順を通る（#100）：
start で同じ SD の走行と分かり、メモが置き場所と違えば、そのメモだけに URL を出す（memo_added）。
complete でメモの大きさを確かめ、完了の合図を置き直す（処理がもう一度動き、メモが画面と台帳に出る）。
"""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime

from ..domain.device import Device
from ..domain.exceptions import UploadConflictError, UploadNotFoundError
from ..domain.raw_upload import (
    MemoAddition,
    UploadSession,
    check_local_session,
    check_ride_id,
    fingerprint,
    memo_changes,
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
    # memo_added：同じ SD の走行を送り終えているが、走行メモが違う（メモだけを送る）
    status: str = "new"


# complete の結果
COMPLETED = "complete"
ALREADY_COMPLETE = "already_complete"
MEMO_ADDED = "memo_added"


class RawUploadService:
    def __init__(self, repository: RawUploadRepository, now: Callable[[], datetime], url_seconds: int) -> None:
        self._repository = repository
        self._now = now
        self._url_seconds = url_seconds

    # ---------------------------------------------------------------- 1. 受け付け
    def start(self, device: Device, local_session: str, files: list[tuple[str, int]], ride_id: str | None = None) -> UploadTicket:
        if ride_id:
            return self._resume(device, check_ride_id(ride_id))
        local_session = check_local_session(local_session)
        raw_files = parse_file_list(files)
        mark = fingerprint(local_session, raw_files)
        existing = self._completed_ride(mark)
        if existing:
            memos = memo_changes(raw_files, lambda name: self._repository.uploaded_size(existing, name))
            if not memos:
                return self._already_uploaded(existing)
            return self._memo_ticket(MemoAddition(existing, device.device_id, local_session, memos, self._now().isoformat()))
        pending = self._pending_session(device, mark)
        if pending:
            return self._ticket_for(pending, "resumed")
        session = self._create(device, local_session, raw_files)
        self._repository.save_pending(mark, session)
        return self._ticket_for(session, "new")

    def _create(self, device: Device, local_session: str, raw_files: tuple) -> UploadSession:
        now = self._now()
        for candidate in ride_id_candidates(now):
            session = UploadSession(candidate, device.device_id, local_session, raw_files, now.isoformat())
            if self._repository.create_session(session):
                return session
        raise UploadConflictError("走行名を決められませんでした。少し待ってからやり直してください")

    def _resume(self, device: Device, ride_id: str) -> UploadTicket:
        session = self._owned_session(device, ride_id)
        if self._repository.is_complete(ride_id):
            raise UploadConflictError(f"{ride_id} は送信済みです")
        # 送りかけの間に、同じ SD の走行をほかの経路（PC など）が送り終えていれば、続きは出さない（2 本にしない。#135）
        existing = self._completed_ride(fingerprint(session.local_session, session.files))
        if existing:
            return self._already_uploaded(existing)
        return self._ticket_for(session, "resumed")

    def _completed_ride(self, mark: str) -> str | None:
        """同じ SD の走行を送り終えていれば、その走行名。"""
        existing = self._repository.find_fingerprint(mark)
        return existing if existing and self._repository.is_complete(existing) else None

    def _pending_session(self, device: Device, mark: str) -> UploadSession | None:
        """この機器が同じ SD の走行を送りかけていれば、その受け付け（消された走行・完了した走行は除く）。"""
        ride_id = self._repository.find_pending(mark, device.device_id)
        if not ride_id:
            return None
        session = self._repository.find_session(ride_id)
        if session is None or not session.belongs_to(device.device_id) or self._repository.is_complete(ride_id):
            return None
        return session

    def _already_uploaded(self, ride_id: str) -> UploadTicket:
        return UploadTicket(ride_id=ride_id, expires_in=self._url_seconds, urls={}, status="already_uploaded")

    def _ticket_for(self, session: UploadSession, status: str) -> UploadTicket:
        urls = {file.name: self._repository.upload_url(session.ride_id, file.name, self._url_seconds) for file in session.files}
        return UploadTicket(ride_id=session.ride_id, expires_in=self._url_seconds, urls=urls, status=status)

    def _memo_ticket(self, addition: MemoAddition) -> UploadTicket:
        self._repository.save_addition(addition)
        urls = {file.name: self._repository.upload_url(addition.ride_id, file.name, self._url_seconds) for file in addition.files}
        return UploadTicket(ride_id=addition.ride_id, expires_in=self._url_seconds, urls=urls, status=MEMO_ADDED)

    # ---------------------------------------------------------------- 3. 完了
    def complete(self, device: Device, ride_id: str) -> str:
        """完了の合図を置き、complete を返す。

        既に完了していれば何もせず already_complete（機器がやり直しても困らないように）。
        この機器が走行メモを足している途中なら、メモの大きさを確かめて合図を置き直し、memo_added。
        """
        ride_id = check_ride_id(ride_id)
        addition = self._repository.find_addition(ride_id)
        if addition and addition.belongs_to(device.device_id) and self._repository.is_complete(ride_id):
            # 最初に送った機器でなくても、メモを足した機器なら完了を報告できる（足し終えた後のやり直しは already_complete）
            if addition.is_pending():
                return self._apply_addition(addition)
            if not self._is_owner(device, ride_id):
                return ALREADY_COMPLETE
        if self._repository.is_complete(ride_id) and not self._is_owner(device, ride_id):
            # 同じ SD の走行をほかの機器が送り終えていた（start が already_uploaded を返した）。報告は受けるだけ
            return ALREADY_COMPLETE
        session = self._owned_session(device, ride_id)
        mark = fingerprint(session.local_session, session.files)
        if self._repository.is_complete(ride_id):
            self._repository.save_fingerprint(mark, session)  # 印を付ける前に送り終えた走行にも付ける（何度呼んでも同じ）
            return ALREADY_COMPLETE
        other = self._completed_ride(mark)
        if other and other != ride_id:
            # URL を出した後で、同じ SD の走行をほかの経路が先に送り終えた。完了の合図を置かず、2 本にしない（#135）
            return ALREADY_COMPLETE
        mismatches = self._size_mismatches(ride_id, session.files)
        if mismatches:
            raise UploadConflictError(f"申告と違うファイルがあります：{', '.join(mismatches)}")
        self._repository.mark_complete(session)
        self._repository.save_fingerprint(mark, session)
        return COMPLETED

    def _apply_addition(self, addition: MemoAddition) -> str:
        mismatches = self._size_mismatches(addition.ride_id, addition.files)
        if mismatches:
            raise UploadConflictError(f"申告と違うファイルがあります：{', '.join(mismatches)}")
        now = self._now().isoformat()
        self._repository.mark_memo_added(addition.ride_id, tuple(file.name for file in addition.files), now)
        self._repository.save_addition(addition.applied(now))
        return MEMO_ADDED

    def _size_mismatches(self, ride_id: str, files) -> list[str]:
        mismatches = []
        for file in files:
            actual = self._repository.uploaded_size(ride_id, file.name)
            if actual != file.size:
                mismatches.append(f"{file.name}（申告 {file.size}、実際 {actual if actual is not None else 'なし'}）")
        return mismatches

    # ---------------------------------------------------------------- 共通
    def _is_owner(self, device: Device, ride_id: str) -> bool:
        session = self._repository.find_session(ride_id)
        return session is not None and session.belongs_to(device.device_id)

    def _owned_session(self, device: Device, ride_id: str) -> UploadSession:
        session = self._repository.find_session(ride_id)
        if session is None or not session.belongs_to(device.device_id):
            # ほかの機器の走行かどうかは教えない
            raise UploadNotFoundError(f"{ride_id} の受け付けがありません")
        return session
