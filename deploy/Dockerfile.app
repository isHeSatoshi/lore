FROM node:24-alpine AS web
WORKDIR /build/web
COPY web/package.json web/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY web/ ./
RUN npm run build

FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 LORE_ROOT=/app
WORKDIR /app
COPY pyproject.toml LICENSE ./
COPY lore/ ./lore/
RUN pip install --no-cache-dir . \
    && useradd --uid 10002 --create-home app \
    && mkdir -p /app/state \
    && chown app:app /app/state \
    && chmod 700 /app/state
COPY seeds/ ./seeds/
COPY results/ ./results/
COPY --from=web /build/web/dist ./web/dist/
USER app
EXPOSE 8000
CMD ["python", "-m", "uvicorn", "lore.api:app", "--host", "0.0.0.0", "--port", "8000", "--limit-concurrency", "64", "--proxy-headers", "--forwarded-allow-ips", "*", "--no-access-log"]
