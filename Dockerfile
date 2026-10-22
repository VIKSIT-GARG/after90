# Build the browser bundle without shipping Node.js or development dependencies.
FROM node:22-bookworm-slim AS frontend-build
WORKDIR /app/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --include=optional
COPY frontend/ ./
RUN npm run build

FROM python:3.12-slim AS runtime
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1
WORKDIR /app

COPY backend/requirements.txt /tmp/requirements.txt
RUN python -m pip install --no-cache-dir -r /tmp/requirements.txt \
    && groupadd --system matchlens \
    && useradd --system --gid matchlens --home-dir /app matchlens

COPY backend/ ./backend/
COPY data/ ./data/
COPY --from=frontend-build /app/frontend/dist/ ./frontend/dist/

USER matchlens
EXPOSE 8000
CMD ["uvicorn", "backend.matchlens.api:app", "--host", "0.0.0.0", "--port", "8000"]
