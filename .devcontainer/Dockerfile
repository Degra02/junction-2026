FROM mcr.microsoft.com/devcontainers/base:ubuntu-24.04

# mise owns the toolchain: versions are pinned in mise.toml, not here.
ARG USERNAME=vscode
ENV MISE_DATA_DIR=/home/${USERNAME}/.local/share/mise \
    MISE_CACHE_DIR=/home/${USERNAME}/.cache/mise \
    PATH=/home/${USERNAME}/.local/share/mise/shims:/home/${USERNAME}/.local/bin:${PATH}

USER ${USERNAME}
RUN curl -fsSL https://mise.run | sh \
    # Pre-create volume mount points so the named volumes inherit vscode ownership.
    && mkdir -p "$MISE_DATA_DIR" "$MISE_CACHE_DIR" /home/${USERNAME}/.cache/uv /home/${USERNAME}/.bun/install/cache \
    && echo 'eval "$(~/.local/bin/mise activate bash)"' >> ~/.bashrc \
    && echo 'eval "$(~/.local/bin/mise activate zsh)"' >> ~/.zshrc
