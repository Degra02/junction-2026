# Kubernetes (local)

`deploy/compose.yaml` for a local kind cluster, as Kustomize: the same three images (`caddy`, `api`, `worker`) built from `deploy/*.Dockerfile`. Production stays on the VPS with compose (`deploy/README.md`).

```sh
cp k8s/.env.example k8s/.env   # once, then fill in the worker's keys (git-ignored)
mise run k8s:up      # kind cluster `junction`, build + load the images (tag dev), apply, wait
kubectl --context kind-junction -n junction port-forward svc/caddy 8088:80   # http://127.0.0.1:8088
mise run k8s:down    # delete the cluster and its volumes
```

`k8s:up` uses Docker when its daemon answers, otherwise rootless podman (it creates the cluster inside a delegated systemd scope, which kind needs for the cpu controller). Hosts with a strict `/etc/containers/policy.json` (secureblue) reject the unsigned `kindest/node` image, the Dockerfile base images and `podman save`: run the steps of `k8s:up` by hand with `--signature-policy <file>` on `podman pull` (the node image digest kind prints), `podman build` and `podman save`, where the file holds `{"default":[{"type":"insecureAcceptAnything"}]}`; or use Docker.

kind also needs `fs.inotify.max_user_instances` of at least 512 (a desktop session can hold most of the default 128; kube-proxy then fails with `too many open files` and nothing schedules): `sysctl fs.inotify.max_user_instances=512` as root.

## What maps to what
|compose|here|
|---|---|
|`caddy` publishes 80/443, gets certificates|`caddy` Service (ClusterIP, plain HTTP `:80`), reached by port-forward; no TLS locally|
|`api`, no published ports, `api-data` volume|`api` Deployment, 1 replica, `Recreate`, PVC `api-data`; NetworkPolicy: only from caddy|
|`worker`, `hf-cache` volume, `mem_limit: 6g`|`worker` Deployment, 1 replica, `Recreate`, PVC `hf-cache`, memory limit 6Gi; NetworkPolicy: only from api|
|`.env` (worker secrets)|Secret `worker-env` generated from `k8s/.env`, provided by hand on the machine that applies (template `k8s/.env.example`, git-ignored)|
|API settings with defaults|ConfigMap `api-settings` in `kustomization.yaml`|
|`IMAGE_TAG`, `PIPELINE_VERSION`|`images:` in `kustomization.yaml`; `PIPELINE_VERSION` follows the api tag (replacement)|

- **One API replica, always.** SQLite (D11) on a ReadWriteOnce volume: a second pod would share neither the cache nor the job state. Do not add an HPA.
- **Worker probe** is a TCP check: the port opens once the models are loaded. No liveness probe, so a long CPU-bound stage is never killed for a slow `/health`.
- **First start** downloads the Hugging Face weights into `hf-cache`; the API waits up to `WORKER_CONNECT_WAIT_SECS` (180) for the worker.
- **Settings**: edit `api-settings` in `kustomization.yaml` and `kubectl apply -k k8s` (the generated name changes, so the API restarts). Kill switch: `STAGES_DISABLED=explain,retrieve`. Eval runs: `RATE_LIMIT_PER_MINUTE=0`, `MAX_ANALYSES_PER_HOUR=0`.
- **Logs**: `kubectl -n junction logs -f deploy/api` / `deploy/worker`. Health: `curl -s 127.0.0.1:8088/api/health | jq` through the port-forward.

## A real cluster
Caddy runs unchanged on Kubernetes. To make it the public edge as on the VPS: Service `type: LoadBalancer` with ports 80, 443 and 443/UDP, `SITE_ADDRESS` set to the hostname, and a PVC on `/data` (certificates; without it every restart requests new ones and hits Let's Encrypt limits); keep it at one replica, since the ACME state is per pod. With an Ingress controller and cert-manager instead, keep Caddy as it is here (plain HTTP behind the Ingress) and route all paths to the `caddy` Service; `X-Forwarded-For` then passes through two proxies, and the API's rate limiter sees the Ingress controller's address unless Caddy is told to trust it (`trusted_proxies`).
