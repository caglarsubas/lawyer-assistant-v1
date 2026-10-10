# Build against an existing local API image with --pull=false --network=none.
# Use a separate fixed staging tag; never retag or restart the deployed API.
FROM lawyer-assistant-api:0.1.0
COPY --chown=10001:10001 backend/app /app/backend/app
