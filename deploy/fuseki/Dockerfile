FROM eclipse-temurin:21.0.8_9-jre-jammy@sha256:db1689535962d757a5adabf57387584ed543d38c0b9d1fe870123ea362ad73b0
ARG JENA_VERSION=5.3.0
ARG JENA_SHA512=5204eefefb921ec029346139f5cb768fe298c816c8642ab590c9bdcee4f24cfacfb15c4266f7acf020d0d5232eea909e4af876f1d5162231ea4b8f8fe0feb3cf
RUN apt-get update && apt-get install -y --no-install-recommends curl ca-certificates python3 python3-pip \
    && rm -rf /var/lib/apt/lists/* \
    && pip3 install --no-cache-dir cryptography==46.0.7 rdflib==7.6.0 pyshacl==0.40.1 \
    && curl --fail --show-error --location --retry 3 \
       "https://archive.apache.org/dist/jena/binaries/apache-jena-fuseki-${JENA_VERSION}.tar.gz" \
       --output /tmp/fuseki.tar.gz \
    && printf '%s  %s\n' "$JENA_SHA512" /tmp/fuseki.tar.gz | sha512sum --check - \
    && mkdir /opt/fuseki /fuseki \
    && tar --extract --gzip --file /tmp/fuseki.tar.gz --strip-components=1 --directory /opt/fuseki \
    && rm /tmp/fuseki.tar.gz \
    && groupadd --gid 10002 fuseki && useradd --uid 10002 --gid fuseki --no-create-home fuseki \
    && mkdir /fuseki/releases && touch /fuseki/publication.lock \
    && chown -R fuseki:fuseki /fuseki
ENV FUSEKI_HOME=/opt/fuseki FUSEKI_BASE=/tmp/fuseki-base PYTHONDONTWRITEBYTECODE=1
COPY deploy/fuseki/config.ttl /etc/fuseki/config.ttl
COPY deploy/fuseki/entrypoint.sh /usr/local/bin/fuseki-entrypoint
COPY deploy/fuseki/runtime.py /opt/fuseki/runtime.py
COPY ontology /opt/ontology
COPY scripts/graph_releases.py /opt/scripts/graph_releases.py
USER 10002:10002
WORKDIR /fuseki
EXPOSE 3030
ENTRYPOINT ["/usr/local/bin/fuseki-entrypoint"]
