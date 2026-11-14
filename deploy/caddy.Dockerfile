# syntax=docker/dockerfile:1
# Build context: repo root. `docker build -f deploy/caddy.Dockerfile .`
# The public edge: Caddy with deploy/Caddyfile and the static build of web/ at /srv, versioned with
# the api and worker images. caddy.Dockerfile.dockerignore keeps the BuildKit context to web/,
# contracts/ts/ and the Caddyfile.

FROM docker.io/oven/bun:1.4.4-alpine AS web
WORKDIR /src
# Until web/package.json exists /out stays empty and the Caddyfile redirects / to the API docs.
# Only web/ and the generated types are copied, without a host node_modules/ or dist/: Podman
# does not apply ignore files to bind mounts.
RUN --mount=type=bind,target=/ctx \
    --mount=type=cache,target=/root/.bun/install/cache \
    mkdir -p /out contracts \
    && if [ -f /ctx/web/package.json ]; then \
         cp -a /ctx/web . \
         && cp -a /ctx/contracts/ts contracts/ \
         && rm -rf web/node_modules web/dist \
         && cd web \
         && bun install --frozen-lockfile \
         && bun run build \
         && cp -a dist/. /out/; \
       fi

FROM docker.io/library/caddy:2.11-alpine
COPY deploy/Caddyfile /etc/caddy/Caddyfile
COPY --from=web /out/ /srv/
# A Caddyfile that does not load fails the image build, so the PR, not the deploy.
RUN caddy validate --config /etc/caddy/Caddyfile --adapter caddyfile
