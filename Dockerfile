FROM python:3.12-slim
WORKDIR /app
COPY . .
# 平台會以 PORT 環境變數指定埠;程式會自動綁 0.0.0.0
CMD ["python", "chips_server.py"]
