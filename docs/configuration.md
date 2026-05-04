# Configuration

WildIntel Tools stores configuration in **TOML files**, one per project, located in `~/.wildintel-tools/`.
Settings are managed with [Dynaconf](https://www.dynaconf.com/) and validated with Pydantic on every load.

---

## Docker container configuration

When running WildIntel Tools through Docker, the container needs to know where on the **host filesystem**
to store and read data. This is controlled by the `DATA_PATH` environment variable, which Docker Compose
mounts into the container at `/data`.

### Setting `DATA_PATH`

#### `.env` file (recommended)

Create or edit the `.env` file next to `docker-compose.yml`:

```text
DATA_PATH=./wildintel-tools-data/
```

Docker Compose reads this file automatically — no extra flags needed.

#### Shell export (Unix, temporary)

```bash
export DATA_PATH=/home/youruser/wildintel-tools-data
docker compose up -d
```

#### PowerShell (Windows, temporary)

```powershell
$env:DATA_PATH = "C:\wildintel-tools-data"
docker compose up -d
```

#### Persistent system-wide (Windows)

```powershell
setx DATA_PATH "C:\wildintel-tools-data"
```

!!! note
    - The host path is mounted at `/data` inside the container.
    - Ensure the directory exists and the container user has read/write access.
    - Verify the mount after starting the container:
      ```bash
      docker compose up -d
      docker compose exec wildintel-tools ls -la /data
      ```

---

## Application configuration

The application settings (Trapper credentials, paths, Zooniverse account, etc.) are stored in a TOML file
inside `~/.wildintel-tools/`. There are two ways to create or update them: the interactive **wizard**
(recommended for first-time setup) or the **CLI commands** (for automation or precise control).

### Option 1 — Interactive wizard (recommended)

The wizard guides you step by step, validates every value, and saves the file automatically.

#### General and Trapper settings

```console
$ wildintel-tools wildintel wizard setup
```

The wizard will ask for:

- **Trapper server URL** — base URL of your Trapper instance (e.g. `https://trapper.example.org/`).
- **Login e-mail and password** — credentials used to authenticate. The wizard tests the connection before
  continuing; if it fails, it lets you retry with different values.
- **Classification project** — select the default Trapper project from an interactive list.
- **Data directory** — local folder where downloaded Trapper collections are stored.
- **Research project name** — label embedded in generated metadata exports.
- **Coverage area** — geographic description included in exports (e.g. `Doñana National Park`).
- **Output directory** — folder where processed collections ready for upload are saved.
- **Timezone** — IANA timezone for camera-trap timestamps (e.g. `UTC`, `Europe/Madrid`).

#### Zooniverse settings

If you use the Zooniverse integration, run the Zooniverse setup wizard afterwards:

```console
$ wildintel-tools zooniverse wizard setup
```

This configures the Zooniverse username, password, project ID, and upload parameters (sequence length,
upload intervals, retry settings). See the [Zooniverse module documentation](commands/zooniverse.md) for
details.

---

### Option 2 — Manual configuration

#### Create a baseline configuration

```bash
wildintel-tools config init
```

This creates a TOML file with all default values for the active project (`default` by default).
Pass `--project <name>` to target a different project.

#### Edit the file

Open the file in your default editor (validates the result after saving):

```bash
wildintel-tools config edit
```

The raw TOML file is located at `~/.wildintel-tools/<project>.toml`. You can also edit it directly with
any text editor.

#### Set individual values

```bash
# Read a single value
wildintel-tools config get GENERAL.host

# Write a single value
wildintel-tools config set GENERAL.host https://trapper.example.org/
wildintel-tools config set GENERAL.login you@example.com
wildintel-tools config set WILDINTEL.timezone Europe/Madrid
```

#### Verify the result

```bash
wildintel-tools config show
```

This prints the full configuration and reports any validation errors.

---

## Configuration reference

### `GENERAL`

Trapper connection and local filesystem paths.

| Key | Type | Default | Description |
|---|---|---|---|
| `host` | URL | `https://wildintel-trap.uhu.es/` | Base URL of the Trapper server (trailing slash required) |
| `login` | email | `user@example.com` | E-mail address for Trapper authentication |
| `password` | string | — | Trapper account password |
| `project_id` | int | `123` | Default Trapper research project ID |
| `verify_ssl` | bool | `true` | Verify the server TLS certificate. Set to `false` only in development |
| `ffmpeg` | string | `ffmpeg` | Path or command name of the `ffmpeg` binary |
| `exiftool` | string | `exiftool` | Path or command name of the `exiftool` binary |
| `data_dir` | path | `~/.wildintel-tools/collections` | Directory where downloaded Trapper collections are stored |

### `WILDINTEL`

Processing options and metadata defaults.

| Key | Type | Default | Description |
|---|---|---|---|
| `rp_name` | string | `WildINTEL` | Research project name embedded in metadata exports |
| `coverage` | string | `Doñana National Park` | Geographic coverage area included in exports |
| `publisher` | string | `University of Huelva` | Publisher name included in exports |
| `owner` | string | `University of Huelva` | Dataset owner included in exports |
| `output_dir` | path | `~/.wildintel-tools/readycollections` | Directory where processed collections are saved |
| `timezone` | string | `UTC` | IANA timezone name for interpreting camera-trap timestamps |
| `ignore_dst` | bool | `false` | If `true`, Daylight Saving Time transitions are ignored |
| `convert_to_utc` | bool | `true` | Convert all timestamps to UTC before storing or exporting |
| `tolerance_hours` | int | `1` | Maximum time difference (hours) allowed when matching records |
| `resize_img` | bool | `false` | Resize images before uploading to Zooniverse |
| `resize_img_size` | int list | `[1024, 768]` | Target `[width, height]` in pixels when `resize_img` is `true` |
| `overwrite` | bool | `false` | Overwrite existing output files without prompting |
| `remove_zip` | bool | `true` | Delete ZIP archives after successful extraction |
| `trigger` | bool | `true` | Process only motion-triggered images; skip continuous captures |

### `ZOONIVERSE`

Zooniverse account credentials.

| Key | Type | Default | Description |
|---|---|---|---|
| `zooniverse_username` | string | — | Zooniverse account username |
| `zooniverse_password` | string | — | Zooniverse account password |
| `zooniverse_project_id` | string | — | Zooniverse project ID (numeric or `owner/project-slug`) |

### `ZOONIVERSE_CONNECTOR`

Upload behaviour when pushing media from Trapper to Zooniverse.

| Key | Type | Default | Description |
|---|---|---|---|
| `upload_collection_n_images_seq` | int | `5` | Number of images grouped into a single Zooniverse subject (sequence length) |
| `upload_collection_max_interval` | int | `90` | Maximum gap in seconds between images in the same sequence |
| `upload_collection_attempts` | int | `5` | Maximum retry attempts when downloading a media file from Trapper |
| `upload_collection_delay` | int | `15` | Seconds to wait between Trapper download retries |
| `upload_collection_max_attempts_per_subject` | int | `5` | Maximum retry attempts when uploading a single subject to Zooniverse |
| `upload_collection_delay_seconds_per_subject` | int | `30` | Seconds to wait between Zooniverse upload retries per subject |

### `TRAPPER`

Secondary Trapper credentials used by the Zooniverse connector when importing annotations.

| Key | Type | Default | Description |
|---|---|---|---|
| `trapper_username` | string | — | Secondary Trapper username (must match the Zooniverse account owner in Trapper) |
| `trapper_password` | string | — | Secondary Trapper password |

### `LOGGER`

| Key | Type | Default | Description |
|---|---|---|---|
| `loglevel` | int | `1` | Verbosity: `0` = error, `1` = info, `2` = debug |
| `filename` | string | `""` | Path to a log file. Leave empty to log to stdout only |

---

## Managing multiple projects

WildIntel Tools supports multiple named configurations — useful when working with different Trapper
instances or research projects simultaneously.

```bash
# List all saved configurations
wildintel-tools config list

# Create or initialise a named project
wildintel-tools --project tatra config init

# Use a named project for any command
wildintel-tools --project tatra config show
wildintel-tools --project tatra wildintel wizard setup
```

Each project corresponds to a separate file at `~/.wildintel-tools/<project>.toml`. The active project
defaults to `default` unless overridden with `--project`.
