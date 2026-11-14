# Deploy

Three containers on the Hostinger VPS (KVM 2: 2 vCPU, 8 GB): `caddy` (TLS, the only public ports; serves the web UI from `./web`), `api` (Rust, SQLite on the `api-data` volume), `worker` (Python stages, models on the `hf-cache` volume). Images are built by `.github/workflows/deploy.yml` and pulled from GHCR; nothing is compiled on the VPS.

## One-time VPS setup
```sh
# Docker template on the VPS already has docker + compose. Then:
fallocate -l 4G /swapfile && chmod 600 /swapfile && mkswap /swapfile && swapon /swapfile
echo '/swapfile none swap sw 0 0' >> /etc/fstab
ufw allow 22,80,443/tcp && ufw allow 443/udp && ufw enable    # or the hPanel firewall
mkdir -p /opt/junction && cd /opt/junction
# .env: copy from the team vault (LLM_*, provider keys) and add the public hostname:
echo 'SITE_ADDRESS=srvNNNNNN.hstgr.cloud' >> .env
# While the repo is private: a GitHub PAT with read:packages.
echo "$PAT" | docker login ghcr.io -u <github-user> --password-stdin
```

GitHub repo settings → Secrets and variables → Actions:
- variables: `DEPLOY_HOST` (the hostname above), optional `DEPLOY_USER` (default `root`), `DEPLOY_DIR` (default `/opt/junction`);
- secrets: `DEPLOY_SSH_KEY` (private key whose public half is in the VPS `authorized_keys`), `DEPLOY_KNOWN_HOSTS` (`ssh-keyscan <host>`).

Deploys start on every push to `main` once `DEPLOY_HOST` is set. The job ends with a smoke check of `https://$DEPLOY_HOST/api/health` that passes only when the worker answers and no stage failed to import, so a merge that breaks the pipeline turns the deploy red.

## What a deploy does to running work
- The worker listens only once its models are loaded (up to a few minutes). Stage calls wait for it (`WORKER_CONNECT_WAIT_SECS`, 180), so analyses submitted during a deploy are slow, not failed.
- Analyses that were running in the API when it restarted are marked failed ("interrupted by a server restart") and run again on the next submission.
- `PIPELINE_VERSION` is the image tag, so every deploy empties the result cache. After the last deploy before a demo, submit the demo inputs once; replays of them are then instant (`GET /api/analyses/{id}/events?replay=true` plays a stored analysis back step by step without calling any source).

## Web UI
Once `web/package.json` exists, the deploy runs `bun run build` in `web/` and copies `web/dist` to `/opt/junction/web`, which Caddy serves at `/` with `index.html` as the fallback. The UI calls the API with relative `/api/...` URLs (same origin, no CORS). Until then `/` redirects to the API docs.

## Operate
```sh
cd /opt/junction
docker compose --env-file .env --env-file release.env ps
docker compose --env-file .env --env-file release.env logs -f api worker   # JSON logs; grep an analysis id
curl -s https://$HOST/api/health | jq    # worker up? any stage with an import error?
curl -s https://$HOST/api/stats | jq     # submissions, cache hits, p50/p95 per stage
```
- **Settings** (in `.env`, then `docker compose … up -d`; defaults in `compose.yaml`): `RATE_LIMIT_PER_MINUTE` (30 new analyses per client; cached results are free), `MAX_ANALYSES_PER_HOUR` (600 in total: the spend cap), `STAGE_TIMEOUT_SECS` (120), `ANALYSIS_TIMEOUT_SECS` (300), `MAX_CONCURRENT_ANALYSES` (4), `MAX_CONCURRENT_INFERENCE` (1).
- **Kill switch**: `STAGES_DISABLED=explain,retrieve` in `.env` skips those stages ("switched off by the operator") without a rebuild; the scores abstain as designed.
- **A stage failed for one analysis** (throttled source, LLM timeout): `curl -X POST "https://$HOST/api/analyses/<id>/rerun?from=<stage>"` runs it again from that stage on the stored output of the earlier ones. A result with a failed step is never served from the cache.
- **Stage errors**: the record shows only a public message ("the stage failed (TimeoutError)"); the exception and traceback are in `logs worker`.
- **Rollback**: set `IMAGE_TAG=sha-<previous>` in `release.env`, then `docker compose --env-file .env --env-file release.env up -d`.
- **Models**: the worker downloads Hugging Face weights into `hf-cache` the first time a stage loads them; start it once before the demo so no download happens live.
- **Backups**: the API writes a consistent copy of the database to `/app/data/backups/` every `BACKUP_INTERVAL_MINS` (15) and keeps the newest four. They sit in the same volume: they cover a bad migration or a corrupted file, not a lost disk. Copy one off the VPS with `docker compose cp api:/app/data/backups ./backups`; restore by stopping the API and putting a copy at `/app/data/app.db` (remove `app.db-wal` and `app.db-shm`).

## Local
`mise run dev` runs worker and API without containers. To try the Caddyfile locally: `SITE_ADDRESS=:8088 API_UPSTREAM=127.0.0.1:8080 WEB_ROOT=web/dist caddy run --config deploy/Caddyfile`.

Eval runs go against a local API, not the VPS: `RATE_LIMIT_PER_MINUTE=0 MAX_ANALYSES_PER_HOUR=0 MAX_CONCURRENT_ANALYSES=8 MAX_CONCURRENT_INFERENCE=4 mise run dev`. To measure a change in the signals, the combiner or the explanation on the same retrieved context, re-run the stored analyses from that stage instead of submitting the inputs again.
