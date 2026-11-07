"""ログインしているユーザー。"""

from dataclasses import dataclass


@dataclass(frozen=True)
class User:
    """Cognito のユーザー。

    user_id は Cognito の sub（変わらない ID）、username は表示用の名前、
    groups は Cognito のグループ（例：admin）。
    """

    user_id: str
    username: str
    groups: tuple[str, ...] = ()

    def belongs_to(self, group: str) -> bool:
        return group in self.groups
