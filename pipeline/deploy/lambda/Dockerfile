# 走行データの処理（ct125.cloud）を AWS Lambda で動かすコンテナ。
# ビルドはリポジトリのルートで：scripts/build-pipeline-image.ps1
# 学習済みモデル（skops）を学習したときと同じ版で読むため、Python とライブラリはローカルの .venv と同じ版にそろえる（requirements.txt）。
FROM public.ecr.aws/lambda/python:3.12

COPY deploy/lambda/requirements.txt ${LAMBDA_TASK_ROOT}/requirements.txt
RUN pip install --no-cache-dir -r ${LAMBDA_TASK_ROOT}/requirements.txt

# 設定の既定値とコードだけを入れる（data/ や config/local.yaml は .dockerignore で入らない）
COPY config/default.yaml ${LAMBDA_TASK_ROOT}/config/default.yaml
COPY src/ct125 ${LAMBDA_TASK_ROOT}/src/ct125
ENV PYTHONPATH=${LAMBDA_TASK_ROOT}/src

# 処理の記録（run.json）とモデルの記録（model.json）に残すコードのコミット。scripts/build-pipeline-image.ps1 が渡す
ARG GIT_COMMIT=unknown
ENV CT125_COMMIT=${GIT_COMMIT}

CMD ["ct125.cloud.lambda_handler.handler"]
