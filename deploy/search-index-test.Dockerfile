# Operator qualification only. Never use this test image as the production API.
ARG API_IMAGE=lawyer-assistant-api:r02-search
FROM ${API_IMAGE}
USER root
RUN uv sync --frozen --extra dev --no-install-project
COPY backend/tests /app/backend/tests
USER 10001:10001
