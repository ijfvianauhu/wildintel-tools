# Installing WildIntel Tools

## Installation methods

WildIntel Tools can be installed in two main ways:

- **From source**: using `uv` (managed Python environment).
- **From binaries**: either using Docker (container) or downloading prebuilt executables from the project's GitHub [Releases](https://github.com/ijfvianauhu/wildintel-tools/releases) page.

---

## From source (using `uv`)

**Requirements:**

- Python 3.12 or higher
- `uv` (environment/runner)
- `git` and `exiftool` installed on the host

### Install ExifTool

`ExifTool` is required for metadata extraction.

=== "Linux (Debian / Ubuntu)"
    ```bash
    sudo apt install libimage-exiftool-perl
    ```

=== "Linux (Fedora / RHEL)"
    ```bash
    sudo dnf install perl-Image-ExifTool
    ```

=== "macOS (Homebrew)"
    ```bash
    /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
    brew install exiftool
    ```

=== "Windows (winget)"
    ```powershell
    winget install -e --id OliverBetz.ExifTool
    ```

!!! note
    - Ensure `exiftool` is available on your `PATH` after installation.
    - Alternative downloads available at [https://exiftool.org/](https://exiftool.org/).

---

### Install Git

`Git` is required to clone the repository.

=== "Linux (Debian / Ubuntu)"
    ```bash
    sudo apt install git
    git --version
    ```

=== "Linux (Fedora / RHEL)"
    ```bash
    sudo dnf install git
    git --version
    ```

=== "macOS (Homebrew)"
    ```bash
    brew install git
    git --version
    ```

=== "Windows (winget)"
    ```powershell
    winget install -e --id Git.Git
    git --version
    ```

---

### Install `uv`

Install `uv` (the Astral `uv` tool) to manage the project environment and run the CLI.

=== "Linux / macOS"
    ```bash
    # Install uv
    curl -LsSf https://astral.sh/uv/install.sh | sh

    # Ensure the installation bin directory is on your PATH
    export PATH="$HOME/.local/bin:$PATH"

    # Verify installation
    uv --version
    uv run wildintel-tools --help
    ```

=== "Windows (winget)"
    ```powershell
    # Install uv
    winget install -e --id astral-sh.uv

    # Verify installation
    uv --version
    uv run wildintel-tools --help
    ```

!!! note
    - If `uv` is not found after installation, restart your terminal or add the installation directory to your `PATH`.
    - On Linux/macOS the installer typically places binaries under `~/.local/bin`; adjust the `PATH` accordingly.
    - On Windows, `winget` normally updates the system `PATH` automatically; if not, restart PowerShell or sign out and sign in.

---

### Install wildintel-tools

After installing the dependencies, clone the repository and run the tool using `uv`.

```bash
# Clone and prepare the project
git clone https://github.com/ijfvianauhu/wildintel-tools.git
cd wildintel-tools

# (Optional) sync dependencies into the uv-managed environment
uv sync --all-extras --dev

# Run the CLI via uv
uv run wildintel-tools --help
```

!!! tip
    If you need to activate the virtual environment created by `uv`, run `source .venv/bin/activate` when required.

---

## From binaries

### Using Docker

The container is the recommended way to run the tool without installing local dependencies. First, ensure Docker is
installed on your system by following the instructions for your OS on the [Docker website](https://www.docker.com/get-started).

Then, obtain the `docker-compose.yml` from the repository and download it to your computer. In the directory where you
have the `docker-compose.yml`, run:

```bash
docker compose up -d
docker compose exec --user trapper wildintel-tools bash
```

Verify that the tool is available inside the container:

```bash
wildintel-tools --help
```

!!! note "Updating the Docker image"
    To update to the latest version, run the following commands in the directory where `docker-compose.yml` is located.
    This will pull the latest image and restart the container.

    ```bash
    docker compose pull
    docker compose up -d
    ```

---

### Prebuilt binaries (Releases)

Prebuilt executables for the main operating systems are published in the
[project's GitHub Releases page](https://github.com/ijfvianauhu/wildintel-tools/releases).

1. Go to the [Releases page](https://github.com/ijfvianauhu/wildintel-tools/releases).
2. Download the artifact that matches your OS/architecture (Linux, macOS x86_64/arm64, Windows).
3. Extract/move the executable and run it, or place it in a directory on your `PATH`.

!!! warning
    - Download the artifact that matches your architecture.
    - On Linux/macOS you may need `chmod +x` to make the file executable.
    - Prebuilt binaries do not include `exiftool` and `ffmpeg`; ensure these are installed as per the instructions above.

---

!!! info "Which method should I use?"
    - For **development or contributions**, prefer installation from source using `uv`.
    - For **production** or usage without managing local dependencies, prefer Docker or the prebuilt binaries from Releases.
    - Consult `README.md` for common commands and configuration details (`DATA_PATH`, `wildintel-tools-data` layout, etc.).