# Deploy

Three containers on the Hostinger VPS (KVM 2: 2 vCPU, 8 GB): `caddy` (TLS, the only public ports), `api` (Rust, SQLite on the `api-data` volume), `worker` (Python stages, models on the `hf-cache` volume). Images are built by `.github/workflows/deploy.yml` and pulled from GHCR; nothing is compiled on the VPS.

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

Deploys start on every push to `main` once `DEPLOY_HOST` is set; the job ends with a check of `https://$DEPLOY_HOST/api/health`.

## Operate
```sh
cd /opt/junction
docker compose --env-file .env --env-file release.env ps
docker compose --env-file .env --env-file release.env logs -f api worker   # JSON logs; grep an analysis id
```
- **Rollback**: set `IMAGE_TAG=sha-<previous>` in `release.env`, then `docker compose --env-file .env --env-file release.env up -d`.
- **Models**: the worker downloads Hugging Face weights into `hf-cache` the first time a stage loads them; start it once before the demo so no download happens live.
- **Backups**: SQLite runs in WAL mode, so copy the whole directory with the API stopped: `docker compose stop api && docker compose cp api:/app/data ./backup-$(date +%s) && docker compose start api` (add the `--env-file` flags as above).

## Local
`mise run dev` runs worker and API without containers. To try the Caddyfile locally: `SITE_ADDRESS=:8088 API_UPSTREAM=127.0.0.1:8080 caddy run --config deploy/Caddyfile`.
