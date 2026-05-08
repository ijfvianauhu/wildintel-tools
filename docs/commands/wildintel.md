# wildintel module

Utilities for validating, preparing, and uploading wildlife monitoring collections to Trapper.

The typical workflow consists of the following steps:

1. **Import deployment** — copy raw images into the correct collection/deployment folder structure and register the timestamp log.
2. **Check collections** — validate that collection and deployment folder names follow the expected naming conventions.
3. **Check deployments** — verify that image files exist, are in chronological order, and that timestamps are within the expected ranges.
4. **Prepare for Trapper** — flatten folder structure, resize images and embed XMP metadata.
5. **Create Trapper package** — generate ZIP packages ready for ingestion.
6. **Upload to Trapper** — send the packages to a Trapper server instance.

---

## Quick start

### Step 0 — Configuration

Before running any command, configure the connection to Trapper and the local data paths. There are two ways to do this:

#### Option A — Wizard (recommended)

```console
$ uv run wildintel-tools wildintel wizard config

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  Configure wildintel module
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

ℹ This wizard will guide you through the initial application configuration.

Continue? [y/N]:
```

The wizard will ask for:

- **Trapper URL** — URL of the Trapper server (e.g. `https://wildintel-trap.uhu.es`).
- **Trapper username and password** — credentials for your Trapper account.
- **Trapper project ID** — numeric ID of the Trapper project.
- **Data directory** — path to the root folder containing your raw collection data.
- **Output directory** — path where prepared collections will be saved.
- **Research project metadata** — name, publisher, owner and geographic coverage.

#### Option B — Manual

Initialize the configuration file, then edit it:

```bash
wildintel-tools config init
wildintel-tools config edit
```

To verify the configuration:

```bash
wildintel-tools config show
```

Once configured, check that the connection to Trapper is working:

```bash
wildintel-tools helpers test-connection
```

---

### Step 1 — Import deployment

Before running any validation, the raw images from a camera trap deployment must be placed in the correct folder
structure under the data directory. There are two ways to do this: using the **interactive wizard** (recommended)
or **manually** creating the folders and copying the files.

#### Option A — Wizard (recommended)

```console
$ uv run wildintel-tools wildintel wizard import_deployment

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  Import a new deployment
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

ℹ This wizard will guide you through importing a new deployment.

Continue? [y/N]:
```

The wizard will guide you through the following steps:

1. **Select a research project** — choose the Trapper research project this deployment belongs to.
2. **Enter the revision number** — numeric identifier of the collection revision (e.g. `1` → `R0001`).
3. **Select a location** — choose the camera trap location from the list of locations registered in Trapper.
4. **Provide the source images folder** — path to the directory containing the raw images to import.

The wizard then:

- Creates the collection folder `R{NNNN}/` inside the configured data directory.
- Creates the deployment subfolder `R{NNNN}-{LOCATION_ID}/` inside the collection folder.
- Copies all images from the source folder into the deployment subfolder.
- Appends an entry to the `R{NNNN}_FileTimestampLog.csv` in the collection root with the detected date range.

After completion a summary report is shown.

#### Option B — Manual

Create the following folder structure inside the configured data directory (`GENERAL.data_dir`):

```
data_dir/
├── R0001/                                  ← collection folder  (RNNNN format)
│   ├── R0001-LOCATION_ID/                  ← deployment folder  (COLLECTION-LOCATION format)
│   │   ├── image_001.jpg
│   │   ├── image_002.jpg
│   │   └── ...
│   └── R0001_FileTimestampLog.csv          ← timestamp log (one row per deployment)
├── R0002/
│   └── ...
```

**Naming rules:**

- Collection folders must match `RNNNN` (letter R followed by exactly four digits), e.g. `R0001`, `R0033`.
- Deployment folders must be named `<COLLECTION>-<LOCATION_ID>`, e.g. `R0001-DONA_0007_B`. The location ID must
  match a location registered in Trapper.

**Timestamp log (`R{NNNN}_FileTimestampLog.csv`):**

This CSV file must be placed in the collection root and must contain one row per deployment with the following
columns:

```
Deployment,StartDate,StartTime,EndDate,EndTime
R0001-DONA_0007_B,2024:09:04,13:10:00,2024:11:04,14:28:00
R0001-DONA_0008_A,2024:09:04,06:00:00,2024:11:04,18:00:00
```

The start/end dates and times define the expected temporal range during which images were taken.
They are used in the [check-deployments](#check-deployments) step to verify that image timestamps are consistent.

---

### Step 2 — Check collections

Validate that collection and deployment folder names follow the expected conventions
(`RNNNN` for collections, `<COLLECTION>-<LOCATION>_<SUFFIX>` for deployments) and
that each location exists in Trapper.

```bash
wildintel-tools wildintel check-collections
```

To check specific collections:

```bash
wildintel-tools wildintel check-collections R0033 R0034
```

To override the data path:

```bash
wildintel-tools wildintel check-collections --data-path $HOME/Downloads/trapper-collections/
```

After the validation, check the report:

```bash
wildintel-tools reports view
```

---

### Step 3 — Check deployments

Verify that the deployment folders contain image files, that the files are in chronological order,
and that their timestamps are within the expected start/end ranges defined in the
`<COLLECTION_NAME>_FileTimestampLog.csv` file located in each collection root.

```bash
wildintel-tools wildintel check-deployments
```

To check specific collections or deployments:

```bash
wildintel-tools wildintel check-deployments R0033
wildintel-tools wildintel check-deployments R0033 --deployments R0033-DONA_0007_B
```

To adjust the allowed time tolerance (default 1 hour):

```bash
wildintel-tools wildintel check-deployments R0033 --tolerance-hours 2
```

---

### Step 4 — Prepare collections for Trapper

Flatten each deployment's folder structure, resize images, rename files, and embed XMP metadata.
Results are saved to `OUTPUT_PATH`.

```bash
wildintel-tools wildintel prepare-for-trapper
```

To specify paths and collections explicitly:

```bash
wildintel-tools wildintel prepare-for-trapper R0033 \
  --data-path /data/collections \
  --output-path /data/collections-ready-to-trapper
```

To allow overwriting existing output directories:

```bash
wildintel-tools wildintel prepare-for-trapper R0033 --overwrite
```

To prepare a single deployment:

```bash
wildintel-tools wildintel prepare-for-trapper R0033 --deployments R0033-DONA_0007_B
```

---

### Step 5 — Create Trapper package

Generate ZIP packages from the prepared collections:

```bash
wildintel-tools wildintel create-trapper-package R0033
```

Each collection generates one or more `.zip` + `.yaml` pairs per deployment:

- The `.zip` file contains the images.
- The `.yaml` file contains the image metadata, collection name, and classification project assignment.

---

### Step 6 — Upload to Trapper

Upload the generated packages to the Trapper server:

```bash
wildintel-tools wildintel upload-trapper-package R0033
```

This creates the collections in Trapper and uploads all associated media and metadata automatically.

!!! tip
    You can run Steps 2–4 in one go using the `pipeline` command, which chains
    `check-collections` → `check-deployments` → `prepare-for-trapper` and stops on the first failure:

    ```bash
    wildintel-tools wildintel pipeline R0033
    ```

---

## Reference

### check-collections

Validate that collection and deployment folder names follow the expected conventions (`RNNNN` for collections, `<COLLECTION>-<LOCATION>_<SUFFIX>` for deployments). Optionally verify that each location exists in Trapper.

```bash
wildintel wildintel check-collections [COLLECTIONS...] [OPTIONS]
```

Alias: `cc`

| Argument / Option | Type | Default | Description |
|---|---|---|---|
| `COLLECTIONS` | list[str] | all | Collection folder names to validate (sub-directories of `--data-path`) |
| `--data-path PATH` | Path | settings | Root data directory containing collections (must exist) |
| `--report-file PATH` | Path | auto | File path to save the YAML report |
| `--url TEXT` | str | settings | Trapper server URL |
| `--user TEXT` | str | settings | Trapper username |
| `--password, -p` | str | `None` | Trapper password |
| `--token, -t` | str | `None` | Trapper API token |
| `--validate-locations / --no-validate-locations` | bool | `True` | Check that each location exists in Trapper |
| `--max-workers` | int | `4` | Number of parallel threads |

---

### check-deployments

Validate the structure of deployment folders: verifies that image files exist, are in chronological order, and that timestamps fall within the expected start/end ranges.

```bash
wildintel wildintel check-deployments [COLLECTIONS...] [OPTIONS]
```

Alias: `cd`

| Argument / Option | Type | Default | Description |
|---|---|---|---|
| `COLLECTIONS` | list[str] | all | Collection folder names to validate |
| `--data-path PATH` | Path | settings | Root data directory |
| `--report-file PATH` | Path | auto | Path to save the YAML report |
| `--tolerance-hours` | int | settings | Allowed deviation (hours) between first/last image timestamp and the declared deployment start/end |
| `--extensions` | list | `None` | File extensions to include (e.g. `jpg`, `mp4`) |
| `--deployments` | list[str] | all | Deployment names to process |
| `--max-workers` | int | `4` | Number of parallel threads |

---

### prepare-for-trapper

Prepare collections for ingestion into Trapper. Normalises folder structure, writes XMP metadata, scales images, and exports prepared artifacts to the output directory. Generates a deployment table CSV per collection for import into Trapper.

```bash
wildintel wildintel prepare-for-trapper [COLLECTIONS...] [OPTIONS]
```

Alias: `pt`

| Argument / Option | Type | Default | Description |
|---|---|---|---|
| `COLLECTIONS` | list[str] | all | Collections to process |
| `--data-path PATH` | Path | settings | Root data directory (must exist) |
| `--output-path PATH` | Path | settings | Destination directory for prepared outputs (must exist) |
| `--report-file PATH` | Path | auto | Path to save the YAML report |
| `--deployments` | list[str] | all | Deployments to process |
| `--extensions` | list | `None` | File extensions to include |
| `--owner TEXT` | str | settings | Resource owner metadata |
| `--publisher TEXT` | str | settings | Resource publisher metadata |
| `--coverage TEXT` | str | settings | Coverage area metadata |
| `--rp-name TEXT` | str | settings | Research project name metadata |
| `--scale / --no-scale` | bool | `True` | Scale images during preparation |
| `--overwrite / --no-overwrite` | bool | `False` | Overwrite existing output directories |
| `--timezone TEXT` | str | `UTC` | IANA timezone for timestamp normalisation |
| `--ignore-dst / --no-ignore-dst` | bool | `True` | Ignore daylight saving time |
| `--convert-to-utc / --no-convert-to-utc` | bool | `True` | Convert timestamps to UTC |
| `--create-deployment-table / --no-create-deployment-table` | bool | `True` | Generate the deployment table CSV |
| `--max-workers` | int | `4` | Number of parallel threads |

---

### create-trapper-package

Generate Trapper-ready ZIP packages from prepared collections.

```bash
wildintel wildintel create-trapper-package [COLLECTIONS...] [OPTIONS]
```

Alias: `ctp`

| Argument / Option | Type | Default | Description |
|---|---|---|---|
| `COLLECTIONS` | list[str] | all | Collections to package |
| `--data-path PATH` | Path | settings | Root data directory |
| `--output-path PATH` | Path | settings | Output directory for ZIP files |
| `--report-file PATH` | Path | auto | Path to save the YAML report |
| `--deployments` | list[str] | all | Deployments to include |
| `--extensions` | list | `None` | File extensions to include |
| `--project-id` | int | `None` | Classification project ID |
| `--overwrite / --no-overwrite` | bool | `False` | Overwrite existing packages |
| `--timezone TEXT` | str | `UTC` | IANA timezone |
| `--ignore-dst / --no-ignore-dst` | bool | `False` | Ignore daylight saving time |
| `--max-workers` | int | `4` | Number of parallel threads |
| `--max-zip-size` | int | `2000` | Maximum size (MB) per ZIP file |

---

### upload-trapper-package

Upload Trapper ZIP packages to a Trapper server.

```bash
wildintel wildintel upload-trapper-package [COLLECTIONS...] [OPTIONS]
```

Alias: `utp`

| Argument / Option | Type | Default | Description |
|---|---|---|---|
| `COLLECTIONS` | list[str] | all in output-path | Collections to upload |
| `--output-path PATH` | Path | required | Directory containing the ZIP packages |
| `--url TEXT` | str | settings | Trapper server URL |
| `--user TEXT` | str | settings | Trapper username |
| `--password, -p` | str | `None` | Trapper password |
| `--token, -t` | str | `None` | Trapper API token |
| `--trigger / --no-trigger` | bool | `True` | Trigger collection processing on the server after upload |
| `--remove-zip / --no-remove-zip` | bool | `True` | Delete the local ZIP after a successful upload |
| `--deployments` | list[str] | all | Deployments to include |
| `--report-file PATH` | Path | auto | Path to save the YAML report |

---

### pipeline

Run the full `check-collections` → `check-deployments` → `prepare-for-trapper` pipeline for each collection in sequence. Skips subsequent steps if a previous step fails.

```bash
wildintel wildintel pipeline [COLLECTIONS...] [OPTIONS]
```

Accepts the combined options of `check-collections`, `check-deployments`, and `prepare-for-trapper`.

---

### wizard

Interactive wizard for guided task completion.

```bash
wildintel wildintel wizard WIZARD
```

| Wizard | Description |
|---|---|
| `config` / `setup` | Initial application configuration: Trapper URL, credentials, project, directories |
| `import_deployment` | Step-by-step import of a new camera-trap deployment from an image folder |
