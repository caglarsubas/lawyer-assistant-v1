FROM node:22.16.0-alpine@sha256:41e4389f3d988d2ed55392df4db1420ad048ae53324a8e2b7c6d19508288107e AS build
WORKDIR /build
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend ./
RUN npm run build

FROM nginx:1.28.0-alpine@sha256:30f1c0d78e0ad60901648be663a710bdadf19e4c10ac6782c235200619158284
RUN apk add --no-cache iptables su-exec
COPY deploy/nginx.conf /etc/nginx/nginx.conf
COPY --chmod=755 deploy/web-entrypoint.sh /usr/local/bin/web-entrypoint
COPY --from=build /build/dist /usr/share/nginx/html
EXPOSE 80
ENTRYPOINT ["/usr/local/bin/web-entrypoint"]
