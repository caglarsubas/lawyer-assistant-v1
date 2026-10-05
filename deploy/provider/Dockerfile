FROM python:3.12.11-slim-bookworm@sha256:519591d6871b7bc437060736b9f7456b8731f1499a57e22e6c285135ae657bf7
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
RUN apt-get update && apt-get install -y --no-install-recommends iptables gosu ca-certificates \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd --gid 10003 relay && useradd --uid 10003 --gid relay --no-create-home relay
WORKDIR /app
COPY deploy/provider/relay.py /app/relay.py
COPY --chmod=755 deploy/provider/entrypoint.sh /usr/local/bin/provider-entrypoint
ENTRYPOINT ["/usr/local/bin/provider-entrypoint"]
