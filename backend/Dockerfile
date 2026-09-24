FROM python:3.12-slim

# 用 uv 装依赖：直接读 pyproject 的 [project.dependencies]，
# 不触发 PEP 517 构建隔离（不需要为了装"项目本身"再下一遍 setuptools）。
COPY --from=ghcr.io/astral-sh/uv:0.9 /uv /usr/local/bin/uv

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    UV_SYSTEM_PYTHON=1 \
    DATA_DIR=/data

WORKDIR /app

# 依赖单独一层：只改业务代码时不会重装依赖
COPY pyproject.toml ./
RUN uv pip install --system --no-cache -r pyproject.toml

# app/ 直接以工作目录形式运行（uvicorn app.main:app），无需把项目装进 site-packages
COPY app ./app

# 数据库与上传目录，compose 里挂 named volume
RUN mkdir -p /data

EXPOSE 8000

# 单进程：APScheduler 内嵌在应用里，多 worker 会重复调度
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
