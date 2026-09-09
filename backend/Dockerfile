# 本地 Docker Compose 用（見 docker-compose.yml）；正式環境走 Render（見 render.yaml），
# 兩邊各自獨立設定，不互相依賴這份 Dockerfile。
FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
