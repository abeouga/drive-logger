"""業務上の失敗。HTTP のステータスへの対応は errors.py が受け持つ。"""


class DomainError(Exception):
    """このアプリの業務上の失敗の親クラス。"""


class InvalidFileNameError(DomainError):
    """使えない文字や拡張子を含むファイル名。"""


class DataFileNotFoundError(DomainError):
    """データセットの中に、指定したファイルがない。"""


class NotAuthenticatedError(DomainError):
    """ログインしたユーザーの情報がない。"""


# ------------------------------------------------------------------ 機器からのアップロード（C）
class InvalidDeviceCredentialError(DomainError):
    """機器のトークンが無い・形が違う・登録と一致しない。"""


class InvalidUploadRequestError(DomainError):
    """送ろうとしているファイルの一覧が決まりに合わない。"""


class UploadNotFoundError(DomainError):
    """指定した走行の受け付けがない（またはほかの機器のもの）。"""


class UploadConflictError(DomainError):
    """受け付けの状態と合わない（完了済み、または大きさが申告と違う）。"""
