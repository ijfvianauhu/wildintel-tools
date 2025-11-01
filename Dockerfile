# dockerfile
# Base image
FROM python:3.11-slim

# Environment variables
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    EDITOR=nano \
    VIRTUAL_ENV=/app/.venv \
    PATH="/app/.venv/bin:/usr/local/bin:$PATH"

# System dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    nano \
    curl \
    ffmpeg \
    libimage-exiftool-perl \
    git \
    unzip \
    && rm -rf /var/lib/apt/lists/*

# Download UV binary directly
RUN curl -L "https://github.com/astral-sh/uv/releases/latest/download/uv-x86_64-unknown-linux-gnu.tar.gz" \
    | tar -xz --strip-components=1 -C /usr/local/bin

# Copy app code
COPY . /app
WORKDIR /app

# Install Python dependencies via UV
# - Si existe `uv.lock`, usa build reproducible (--frozen)
# - Si no existe, crea el lock y luego sincroniza
RUN bash -lc 'if [ -f uv.lock ]; then uv sync --frozen --no-dev; else uv lock && uv sync --no-dev; fi'

# Create data directory
RUN mkdir -p /data
WORKDIR /data

# Create non-root user
RUN groupadd -g 1000 trapper && useradd -u 1000 -g 1000 -m -d /home/trapper trapper

# Shell completions
RUN echo '\''eval "$(wildintel-tools --print-completion bash)"'\'' >> /home/trapper/.bashrc

# Entrypoint
RUN chmod +x /app/entrypoint.sh
ENTRYPOINT ["/app/entrypoint.sh"]

# Default command
CMD ["bash", "-c", "source /app/.venv/bin/activate && exec bash"]
