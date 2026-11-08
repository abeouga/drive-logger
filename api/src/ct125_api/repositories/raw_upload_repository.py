"""生データの置き場所（raw/<走行>/）の約束。サービスはここだけを知り、S3 かどうかは知らない。"""

from typing import Protocol

from ..domain.raw_upload import UploadSession


class RawUploadRepository(Protocol):
    def create_session(self, session: UploadSession) -> bool:
        """受け付けを新しく記録する。同じ走行名が既にあれば何もせず False。"""
        ...

    def find_session(self, ride_id: str) -> UploadSession | None: ...

    def is_complete(self, ride_id: str) -> bool:
        """完了の合図（upload_complete.json）が置かれているか。"""
        ...

    def upload_url(self, ride_id: str, file_name: str, expires_seconds: int) -> str:
        """そのファイル専用の PUT 用 URL（期限付き）。"""
        ...

    def uploaded_size(self, ride_id: str, file_name: str) -> int | None:
        """置かれたファイルの大きさ。まだ無ければ None。"""
        ...

    def mark_complete(self, session: UploadSession) -> None:
        """完了の合図を置く（これで AWS 側の自動処理が始まる）。"""
        ...

    def find_fingerprint(self, fingerprint: str) -> str | None:
        """同じ SD の走行を前に送り終えていれば、その走行名。"""
        ...

    def save_fingerprint(self, fingerprint: str, session: UploadSession) -> None:
        """送り終えた走行の印を残す（次に同じ走行が来たら、新しく作らない）。"""
        ...
