# Kate-Cortex 云端多用户版镜像
# 构建：docker build -t kate-cortex .
# 运行：见 docker-compose.yml（数据卷 /data，账号库 users.sqlite + 每用户独立 vault）

# ---------- 阶段 1：前端静态产物（纯 Web 构建，跳过 Electron） ----------
FROM node:22-alpine AS web
RUN corepack enable
WORKDIR /build
COPY frontend/package.json frontend/pnpm-lock.yaml ./
RUN ELECTRON_SKIP_BINARY_DOWNLOAD=1 pnpm install --frozen-lockfile
COPY frontend/ ./
RUN pnpm run build:web

# ---------- 阶段 2：后端运行时 + 静态托管 ----------
FROM python:3.12-slim
WORKDIR /app

# 国内服务器构建慢可换镜像：--build-arg PIP_INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple
ARG PIP_INDEX_URL=https://pypi.org/simple
ENV PIP_INDEX_URL=${PIP_INDEX_URL} \
    PYTHONUNBUFFERED=1 \
    KATE_DATA_DIR=/data \
    KATE_FRONTEND_DIR=/app/web

COPY backend/ ./backend/
RUN pip install --no-cache-dir ./backend

COPY --from=web /build/dist ./web

# 账号库与全部用户数据都在这里，备份 = 备份这个目录
VOLUME ["/data"]
EXPOSE 8000
CMD ["uvicorn", "kate_cortex.main:app", "--host", "0.0.0.0", "--port", "8000"]
