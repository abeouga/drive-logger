<div align="center">
<h2>ドライブロガー<br>https://drive.herdio-system.com/</h2>
バイクにマイコンを装着し、走行中のエンジンと環境から取得できる <ins>ECU、加速度、GPS</ins> を記録し、<br>
AWS でデータの前処理・機械学習モデルの作成をして<ins>地図とタイムラインで可視化するプロジェクト</ins>です。
</div>

# プレビュー
### 走行の詳細画面

<img width="1905" height="1079" alt="image" src="https://github.com/user-attachments/assets/a2e84b51-20f8-4f49-8105-749e89fe7e80" />

### マイコン装着例
>熱をもつエンジン本体に加速度センサーをつけられない都合上、<br>センサーはエンジンより15cm上に位置するフレームにテープで巻きつけています。

<img width="1391" height="1043" alt="image" src="https://github.com/user-attachments/assets/537432bf-10f5-4a9c-81a3-543833cb0eaa" />

## 何をしているか

1. 走行中にESP32 が ECUのデータ、加速度、GPSを microSD にリアルタイム書き込み
2. 走行後にBOOT ボタンを押すことで、自宅のWi-Fi経由でデータをS3 に送信。
3. Lambdaが前処理として各データを1秒で区切り、rpmと振動特徴量と GPS の結合をする。
4. 異常検知モデルの作成 → 画面表示用データの書き出しを行う
5. [4]で作成されたデータを走行一覧、地図とタイムラインとスペクトログラムが連動する走行ページとして表示する。

## インフラ
S3・CloudFront・ACM・Cognito・API Gateway・Lambda×3・ECR・Terraform
