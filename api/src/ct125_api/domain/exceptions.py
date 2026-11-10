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


# ------------------------------------------------------------------ 走行の台帳・処理の記録・モデル（#16・#17）
class InvalidRequestError(DomainError):
    """ID の形が違うなど、要求の中身が決まりに合わない。"""


class ForbiddenError(DomainError):
    """ログインしているが、その操作をする権限が無い（admin でない）。"""


class RideNotFoundError(DomainError):
    """台帳に無い走行（または、見せない走行）。"""


class RunNotFoundError(DomainError):
    """その走行の処理の記録に無い処理。"""


class ModelNotFoundError(DomainError):
    """無いモデルの版。"""


class RunNotPublishableError(DomainError):
    """失敗した処理の結果は公開できない。"""


class LedgerConflictError(DomainError):
    """台帳をほかの処理が続けて書き換えていて、書けなかった（読み直してやり直す）。"""


class RideNotInTrashError(DomainError):
    """ゴミ箱に入っていない走行は、完全に削除できない（先にゴミ箱へ移す）。"""


class PurgeIncompleteError(DomainError):
    """完全に削除の途中で S3 の削除に失敗した。台帳からは除いてあるので、残りはログを見て消す。"""
