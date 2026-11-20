# OSCOWL Q-Sim: one container = FastAPI API + built React UI (Cloud Run ready).
# Build:  docker build -t oscowl-qsim .
# GPU/TPU worker image: docker build --build-arg EXTRA_PIP="jax[cuda12]" -t oscowl-qsim-gpu .

# ---------- 1. build the React app ----------
FROM node:22-alpine AS web
WORKDIR /web
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY frontend/ ./
RUN npm run build

# ---------- 2. Python API serving the UI ----------
FROM python:3.12-slim
ARG EXTRA_PIP=""
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=8080 \
    STATIC_DIR=/app/static \
    BENCHMARK_RESULTS=/app/benchmark_results/latest.json
WORKDIR /app
COPY backend/requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt \
 && if [ -n "$EXTRA_PIP" ]; then pip install --no-cache-dir $EXTRA_PIP; fi
COPY backend/app ./app
COPY backend/adk_agents ./adk_agents
COPY benchmarks/results/ ./benchmark_results/
COPY --from=web /web/dist ./static
RUN useradd --create-home qsim && chown -R qsim /app
USER qsim
EXPOSE 8080
CMD ["sh", "-c", "exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT}"]
