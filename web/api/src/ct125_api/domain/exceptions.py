"""業務上の失敗。HTTP のステータスへの対応は errors.py が受け持つ。"""


class DomainError(Exception):
    """このアプリの業務上の失敗の親クラス。"""


class InvalidFileNameError(DomainError):
    """使えない文字や拡張子を含むファイル名。"""


class DataFileNotFoundError(DomainError):
    """データセットの中に、指定したファイルがない。"""


class NotAuthenticatedError(DomainError):
    """ログインしたユーザーの情報がない。"""
