# wildintel

Utilities for validating, preparing, and uploading wildlife monitoring collections to Trapper.

---

## check-collections

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

## check-deployments

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

## prepare-for-trapper

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

## create-trapper-package

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

## upload-trapper-package

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

## pipeline

Run the full `check-collections` → `check-deployments` → `prepare-for-trapper` pipeline for each collection in sequence. Skips subsequent steps if a previous step fails.

```bash
wildintel wildintel pipeline [COLLECTIONS...] [OPTIONS]
```

Accepts the combined options of `check-collections`, `check-deployments`, and `prepare-for-trapper`.

---

## wizard

Interactive wizard for guided task completion.

```bash
wildintel wildintel wizard WIZARD
```

| Wizard | Description |
|---|---|
| `config` / `setup` | Initial application configuration: Trapper URL, credentials, project, directories |
| `import_deployment` | Step-by-step import of a new camera-trap deployment from an image folder |
