# ---- build the React frontend ----
FROM node:22-alpine AS frontend
WORKDIR /app/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY frontend/ ./
RUN npm run build

# ---- Python app ----
FROM python:3.11-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PORT=8000 \
    DATABASE_URL=sqlite:////data/study.db
WORKDIR /app
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY backend/ backend/
COPY sim/ sim/
COPY docs/ docs/
COPY --from=frontend /app/frontend/dist frontend/dist
RUN mkdir -p /data
EXPOSE 8000
# One worker: per-participant generation locks and round-robin numbering live in-process.
CMD ["sh", "-c", "uvicorn backend.app.main:app --host 0.0.0.0 --port ${PORT} --workers 1 --proxy-headers --forwarded-allow-ips='*'"]
