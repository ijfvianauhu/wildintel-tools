# Installation

## Requirements

- Python 3.12 or higher
- [uv](https://docs.astral.sh/uv/) (recommended) or pip

### External tools (optional but required for some commands)

- **ffmpeg** — used by the `wildintel prepare-for-trapper` pipeline for image processing.
- **exiftool** — used to read and write XMP metadata on image files.

Both tools can be tested after installation with `wildintel helpers test-external-tools`.

---

## Install from source

Clone the repository and install the project with uv:

```bash
git clone https://github.com/ijfviana/wildintel-tools.git
cd wildintel-tools
uv sync
```

This installs the `wildintel` command in the project's virtual environment. Activate it or prefix commands with `uv run`:

```bash
uv run wildintel --help
```

---

## Install with pip

```bash
pip install wildintel-tools
```

---

## Verify the installation

```bash
wildintel --help
```

You should see the top-level help message listing all available command groups.

---

## Next step

Run the setup wizard to create your first project configuration:

```bash
wildintel wildintel wizard setup
```

Or create a configuration manually — see the [Configuration guide](configuration.md).
