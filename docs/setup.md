# Setup

## Every teammate
1. Install [mise](https://mise.jdx.dev/getting-started.html) and activate it in your shell.
2. In the repo: `mise trust && mise run setup` — installs the pinned tools from `mise.toml` and sets `core.hooksPath=.githooks`.
3. `cp .env.example .env` and fill it from the team password manager. mise loads `.env` automatically.
4. `mise run check` must pass.

## Dev container (alternative to installing mise locally)
- VS Code: "Dev Containers: Reopen in Container". CLI: `devcontainer up --workspace-folder .`.
- The image only ships mise; `post-create.sh` creates `.env` from `.env.example` if missing, then runs `mise trust`, `mise run setup`, `mise run check`.
- Pinned tools and caches live in named volumes (`junction-2026-mise`, `-cache`, `-bun`), so rebuilds do not re-download them.
- Podman (rootless): set `"dev.containers.dockerPath": "podman"` in VS Code and add `"runArgs": ["--userns=keep-id"]` locally if files end up owned by the wrong user.

## Sandboxed agents (`jomp` = omp under nono)
- `jomp` picks `~/.config/nono/profiles/omp-<repo-dirname>.json` when it exists; for this repo that is `omp-junction-2026.json`.
- It extends `omp` (read/write the repo + `~/.omp`) with the `mise_manager`, `node_runtime`, `bun_runtime`, `python_runtime`, `user_caches_linux` groups and write access to `~/.npm`, `~/.bun`, `~/.local/share/uv`.
- Those directories must exist before launch (nono skips grants for missing paths): `mkdir -p ~/.npm ~/.bun ~/.local/share/uv`.
- Verified inside the sandbox: pinned node/python/bun/uv/gitleaks run, `uv add`, `bun add`, `npm i`, `mise run check`.
- Inside the sandbox the agent **cannot**: install new mise tools (`~/.local/share/mise` is read-only → run `mise install` outside), read `gh` credentials or keyrings (agents commit, humans push), run podman.
- Parallel agents on one machine: use separate `git clone`s. A sibling `git worktree` fails inside the sandbox (`fatal: gitfile does not point to a valid repository`) because its `.git` points outside the granted directory.
- Each clone has a different directory name, so give each its own profile (copy `omp-junction-2026.json` to `omp-<clone-dirname>.json`) or launch nono with `--profile omp-junction-2026` directly.

## Accounts and keys (before Friday)
- [ ] NVIDIA build.nvidia.com API key (`nvapi-…`), one test Nemotron call
- [ ] Modal: `uv tool install modal && modal setup`, invite 2 teammates (Starter: 3 seats), set a budget
- [ ] Gemini API key (AI Studio)
- [ ] OpenAI / Codex CLI (`npm i -g @openai/codex`) if anyone uses it
- [ ] Featherless, Exa, Context.dev, Cala API keys
- [ ] Cloudinary account (+ MCP server if media matters)
- [ ] Aiven free Postgres (pgvector) as the shared demo database
- [ ] Physical-AI only: Wendy CLI + Go2 sim; Qualia / Scailab waitlists
- [ ] Verda credits: coupon on the Junction Platform during the event (onboarding workshop Fri 20:30)
- [ ] GitHub repo under a team org; protect `main` (PR required, CI must pass)
- [ ] Junction Discord; shared password manager vault for keys

## After the event
Rotate every key that was ever in a `.env`: the repo becomes public under MIT.
