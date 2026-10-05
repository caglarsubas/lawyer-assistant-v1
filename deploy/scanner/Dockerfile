FROM clamav/clamav-debian:1.4.6_base@sha256:a3cbbbc2b17a3871862689c0773bc9f5d70a1e4914ada7c8a05e157722ee8a9d

USER root
RUN apt-get update && apt-get install -y --no-install-recommends python3 \
    && rm -rf /var/lib/apt/lists/* \
    && mkdir -p /opt/scanner
COPY deploy/scanner/clamd.conf /etc/clamav/clamd.conf
COPY deploy/scanner/control.py /opt/scanner/control.py
COPY backend/app/scanner.py /opt/scanner/scanner.py
ENV TZ=UTC LC_ALL=C PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
USER 1000:1000
EXPOSE 3310
# Deliberately bypass vendor init: it can download signatures even with freshclam disabled.
ENTRYPOINT ["python3", "/opt/scanner/control.py"]
CMD ["start"]
