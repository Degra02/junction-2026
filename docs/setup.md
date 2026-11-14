# Setup

## Every teammate
1. Install [mise](https://mise.jdx.dev/getting-started.html) and activate it in your shell.
2. In the repo: `mise trust && mise run setup` — installs the pinned tools from `mise.toml` (including Rust 1.100 via rustup and cargo-nextest), sets `core.hooksPath=.githooks` and runs `uv sync`.
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
- Those directories must exist before launch (nono skips grants for missing paths): `mkdir -p ~/.npm ~/.bun ~/.local/share/uv ~/.cargo/registry ~/.cargo/git`.
- Rust: the profile also needs write access to `~/.cargo/registry` and `~/.cargo/git` (crate downloads) and read access to `~/.rustup` (toolchains). Install the toolchain outside the sandbox first (`mise install`); `target/` lives in the repo.
- Verified inside the sandbox: pinned node/python/bun/uv/gitleaks run, `uv add`, `bun add`, `npm i`, `mise run check`.
- Inside the sandbox the agent **cannot**: install new mise tools (`~/.local/share/mise` is read-only → run `mise install` outside), read `gh` credentials or keyrings (agents commit, humans push), run podman.
- Parallel agents on one machine: use separate `git clone`s. A sibling `git worktree` fails inside the sandbox (`fatal: gitfile does not point to a valid repository`) because its `.git` points outside the granted directory.
- Each clone has a different directory name, so give each its own profile (copy `omp-junction-2026.json` to `omp-<clone-dirname>.json`) or launch nono with `--profile omp-junction-2026` directly.

## Accounts and keys
Only what the decided plan uses (D7, D8, D12, D15); names in `.env.example`.
- [ ] Hostinger AI Router key (hPanel → AI Router): `LLM_BASE_URL`, `LLM_API_KEY`, `LLM_MODEL`; set a per-key spend limit
- [ ] Gemini API key (AI Studio) for grounded search: `GEMINI_API_KEY`
- [ ] Google Fact Check Tools API key: `GOOGLE_FACTCHECK_API_KEY`
- [ ] Oxylabs $500 Flexible plan with code `JUNCTION2026`; AI Studio API key: `OXYLABS_TOKEN`. **Cancel right after the event** or month two is charged
- [ ] GitHub repo under a team org; protect `main` (PR required, CI must pass)
- [ ] Junction Discord; shared password manager vault for keys

## After the event
Rotate every key that was ever in a `.env`: the repo becomes public under MIT.
