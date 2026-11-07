"""リクエストから、ログインしているユーザーを取り出す。

API Gateway の JWT オーソライザーが Cognito のアクセストークンを検証し、
中身（claims）を Lambda のイベントに入れて渡してくる。ここではそれを読むだけで、署名は検証しない。
（API Gateway を通らない経路では claims が無いので、ログインしていない扱いになる）
"""

from typing import Any

from fastapi import Request

from ..domain.exceptions import NotAuthenticatedError
from ..domain.user import User

# ALLOW_LOCAL_USER=true のときだけ使う、ローカル開発用のユーザー
LOCAL_DEVELOPER = User(user_id="local-developer", username="local-developer", groups=("admin",))


def read_user(request: Request, allow_local_user: bool) -> User:
    claims = _claims_from(request)
    if claims:
        return user_from_claims(claims)
    if allow_local_user:
        return LOCAL_DEVELOPER
    raise NotAuthenticatedError("ログインしていません")


def user_from_claims(claims: dict[str, Any]) -> User:
    user_id = str(claims.get("sub", ""))
    if not user_id:
        raise NotAuthenticatedError("トークンにユーザー ID（sub）がありません")
    username = str(claims.get("username") or claims.get("cognito:username") or user_id)
    groups = parse_groups(claims.get("cognito:groups"))
    return User(user_id=user_id, username=username, groups=groups)


def parse_groups(raw: Any) -> tuple[str, ...]:
    """Cognito のグループを tuple にする。

    API Gateway は配列の claim を "[admin viewer]" という文字列で渡してくるので、両方の形に対応する。
    """
    if raw is None:
        return ()
    if isinstance(raw, list):
        return tuple(str(group) for group in raw)
    text = str(raw).strip().strip("[]")
    return tuple(group for group in text.split() if group)


def _claims_from(request: Request) -> dict[str, Any]:
    """Mangum が scope に入れた Lambda のイベントから、JWT の claims を取り出す。"""
    event = request.scope.get("aws.event") or {}
    authorizer = event.get("requestContext", {}).get("authorizer", {})
    return authorizer.get("jwt", {}).get("claims", {})
