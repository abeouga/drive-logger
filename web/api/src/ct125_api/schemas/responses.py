"""API が返す JSON の形。/api/docs の説明書にもこの形が載る。"""

from pydantic import BaseModel, Field


class HealthResponse(BaseModel):
    status: str = Field(description="動いていれば ok")


class MeResponse(BaseModel):
    username: str = Field(description="ログイン中のユーザー名")
    groups: list[str] = Field(description="Cognito のグループ")
    dataset: str = Field(description="このユーザーが見るデータセット（今は全員 shared）")
