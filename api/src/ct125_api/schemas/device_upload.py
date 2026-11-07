"""機器とのやりとりの JSON の形（ESP32 のファームウェアとの約束）。"""

from pydantic import BaseModel, Field


class UploadFile(BaseModel):
    name: str = Field(description="ファイル名（accel.csv・gps.csv・events.csv・status.csv・meta.json・memo.txt）")
    size: int = Field(description="バイト数")


class StartUploadRequest(BaseModel):
    local_session: str = Field(description="SD 上の走行名（例：ride_012）")
    files: list[UploadFile] = Field(description="送るファイルと大きさ")
    ride_id: str | None = Field(default=None, description="途中で切れたときだけ：前回もらった走行名")


class UploadTarget(BaseModel):
    name: str
    url: str = Field(description="このファイルを HTTP PUT で送る先（期限付き）")


class StartUploadResponse(BaseModel):
    ride_id: str = Field(description="サーバーが付けた走行名。SD に残し、完了の報告とやり直しで使う")
    expires_in: int = Field(description="URL の有効期間（秒）")
    uploads: list[UploadTarget]


class CompleteUploadResponse(BaseModel):
    ride_id: str
    status: str = Field(description="complete（今回完了）か already_complete（前に完了済み）")
