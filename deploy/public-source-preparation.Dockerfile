# Build against an existing local API image with --pull=false --network=none.
# This separate tag does not rebuild or restart the deployed API/provider.
FROM lawyer-assistant-api:0.1.0
COPY --chown=10001:10001 backend/app /app/backend/app
