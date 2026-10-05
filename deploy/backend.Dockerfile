FROM python:3.12.11-slim-bookworm@sha256:519591d6871b7bc437060736b9f7456b8731f1499a57e22e6c285135ae657bf7

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 UV_LINK_MODE=copy \
    PATH=/app/backend/.venv/bin:$PATH
RUN apt-get update && apt-get install -y --no-install-recommends \
      tesseract-ocr tesseract-ocr-tur tesseract-ocr-eng poppler-utils antiword age \
    && rm -rf /var/lib/apt/lists/* \
    && pip install --no-cache-dir uv==0.8.15 \
    && groupadd --gid 10001 app && useradd --uid 10001 --gid app --no-create-home app \
    && mkdir -p /data /app /public-sources && chown app:app /data /app /public-sources
WORKDIR /app/backend
COPY backend/pyproject.toml backend/uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project
COPY backend/app ./app
RUN uv sync --frozen --no-dev
COPY ontology /app/ontology
COPY scripts /app/scripts
COPY qualification/source-catalog.json qualification/asset-catalog.json qualification/analysis-fixture.json qualification/scenario-fixture.json qualification/research-dossier.json /app/qualification/
COPY deploy/volume_archive.py /app/deploy/volume_archive.py
USER 10001:10001
EXPOSE 8000
CMD ["uvicorn", "app.main:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000", "--no-access-log"]
