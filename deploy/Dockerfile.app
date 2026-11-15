FROM node:24-alpine AS web
WORKDIR /build/web
COPY web/package.json web/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY web/ ./
RUN npm run build

FROM python:3.12-slim
ARG LORE_LLM_TRANSPORT=anthropic
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 LORE_ROOT=/app \
    FACTORY_DROID_AUTO_UPDATE_ENABLED=false
WORKDIR /app
COPY pyproject.toml LICENSE DATA_LICENSE.md ./
COPY lore/ ./lore/
COPY deploy/hf/droid_runtime.py deploy/hf/FACTORY_NOTICE.md /opt/lore-droid/
RUN if [ "$LORE_LLM_TRANSPORT" = factory ]; then \
        pip install --no-cache-dir '.[factory]'; \
    else pip install --no-cache-dir .; fi \
    && useradd --uid 10002 --create-home app \
    && if [ "$LORE_LLM_TRANSPORT" = factory ]; then \
        python -c "import sys; from pathlib import Path; sys.path.insert(0, '/opt/lore-droid'); from droid_runtime import provision_droid; Path('/usr/local/bin/droid').symlink_to(provision_droid(Path('/opt/lore-droid/runtime')))"; \
    fi \
    && mkdir -p /app/state \
    && chown -R app:app /app/state /opt/lore-droid \
    && chmod 700 /app/state
COPY seeds/ ./seeds/
COPY results/ ./results/
COPY --from=web /build/web/dist ./web/dist/
USER app
EXPOSE 8000
CMD ["python", "-m", "uvicorn", "lore.api:app", "--host", "0.0.0.0", "--port", "8000", "--limit-concurrency", "64", "--proxy-headers", "--forwarded-allow-ips", "*", "--no-access-log"]
