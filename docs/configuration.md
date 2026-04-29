# Configuration

wildintel-tools uses [Dynaconf](https://www.dynaconf.com/) to manage per-project YAML configuration files. Each project has its own settings file stored in `~/.wildintel-tools/settings/`.

---

## Creating a configuration

### Interactive wizard

The quickest way to configure the tool is through the setup wizard:

```bash
wildintel wildintel wizard setup
```

The wizard will prompt you for all required values, test the Trapper connection, and save the configuration automatically.

### CLI command

```bash
wildintel config init
```

This creates a new YAML file for the active project (`default` by default). You can pass `--template` to use a custom template file.

---

## Configuration sections

### `GENERAL`

| Key | Description |
|---|---|
| `host` | Base URL of the Trapper server (e.g. `https://trapper.example.org/`) |
| `login` | Your login email for Trapper |
| `password` | Your Trapper password |
| `project_id` | Default Trapper classification project ID |
| `data_dir` | Root directory for raw collection data |
| `ffmpeg` | Path to the `ffmpeg` binary |
| `exiftool` | Path to the `exiftool` binary |

### `WILDINTEL`

| Key | Description |
|---|---|
| `output_dir` | Output directory for prepared Trapper packages |
| `rp_name` | Research project name embedded in XMP metadata |
| `coverage` | Coverage area embedded in XMP metadata |
| `owner` | Resource owner embedded in XMP metadata |
| `publisher` | Resource publisher embedded in XMP metadata |
| `timezone` | IANA timezone name used for timestamp normalisation (e.g. `UTC`, `Europe/Madrid`) |
| `ignore_dst` | Whether to ignore daylight saving time adjustments |
| `convert_to_utc` | Whether to convert all timestamps to UTC |
| `tolerance_hours` | Allowed time deviation (hours) when verifying image timestamps against deployment dates |

### `ZOONIVERSE`

| Key | Description |
|---|---|
| `zooniverse_project_id` | Zooniverse project ID (numeric or `owner/project-name`) |
| `zooniverse_username` | Zooniverse username |
| `zooniverse_password` | Zooniverse password |

### `TRAPPER`

| Key | Description |
|---|---|
| `trapper_username` | Secondary Trapper username (used by the Zooniverse connector) |
| `trapper_password` | Secondary Trapper password |

### `ZOONIVERSE_CONNECTOR`

| Key | Description |
|---|---|
| `upload_collection_max_interval` | Maximum interval (seconds) between images in a sequence during upload |
| `upload_collection_n_images_seq` | Number of images per sequence during upload |

### `LOGGER`

| Key | Description |
|---|---|
| `filename` | Path to the application log file |

---

## Viewing and editing settings

```bash
# Show the current project settings
wildintel config show

# Edit the settings file in your default editor
wildintel config edit

# Read a single value
wildintel config get GENERAL.host

# Update a single value
wildintel config set GENERAL.host https://new-trapper.example.org/
```

---

## Multiple projects

wildintel-tools supports multiple named project configurations:

```bash
# List available configurations
wildintel config list

# Use a named project
wildintel --project myproject config show
```

Each project corresponds to a separate YAML file in the settings directory.
