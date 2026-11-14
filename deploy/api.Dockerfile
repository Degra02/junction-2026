# syntax=docker/dockerfile:1
# Build context: repo root. `docker build -f deploy/api.Dockerfile .`

FROM docker.io/lukemathwalker/cargo-chef:latest-rust-1.100-slim-trixie AS chef
WORKDIR /app

FROM chef AS planner
COPY . .
RUN cargo chef prepare --recipe-path recipe.json

FROM chef AS builder
COPY rust-toolchain.toml .
COPY --from=planner /app/recipe.json recipe.json
# Dependencies only: this layer is cached until Cargo.toml/Cargo.lock change.
RUN cargo chef cook --release --locked -p junction-api --recipe-path recipe.json
COPY . .
RUN cargo build --release --locked -p junction-api \
    && mkdir -p /out/data \
    && { cp evals/metrics.json /out/metrics.json 2>/dev/null || true; }

FROM gcr.io/distroless/cc-debian13:nonroot
COPY --from=builder /app/target/release/junction-api /usr/local/bin/junction-api
# Owned by the nonroot user so the named volume mounted here inherits a writable directory.
COPY --from=builder --chown=65532:65532 /out/ /app/
ENV API_ADDR=0.0.0.0:8080 \
    DATABASE_PATH=/app/data/app.db \
    METRICS_PATH=/app/metrics.json \
    LOG_FORMAT=json
EXPOSE 8080
ENTRYPOINT ["junction-api"]
CMD ["serve"]
