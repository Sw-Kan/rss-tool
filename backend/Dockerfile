FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    DATA_DIR=/data

WORKDIR /app

COPY pyproject.toml ./
COPY app ./app
RUN pip install --no-cache-dir .

# 数据库与上传目录，compose 里挂 named volume
RUN mkdir -p /data

EXPOSE 8000

# 单进程：APScheduler 内嵌在应用里，多 worker 会重复调度
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
