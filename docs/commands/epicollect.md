# epicollect

Utilities for interacting with [Epicollect5](https://five.epicollect.net/) projects. Supports both public and private (OAuth) projects.

---

## search-project

Display information about a public Epicollect project.

```bash
wildintel epicollect search-project APP_SLUG
```

| Argument | Type | Description |
|---|---|---|
| `APP_SLUG` | str | The project slug as it appears in the Epicollect URL |

**Example**

```bash
wildintel epicollect search-project my-wildife-survey
```

---

## get-project

Display information about a private Epicollect project using OAuth credentials.

```bash
wildintel epicollect get-project APP_SLUG [OPTIONS]
```

| Argument / Option | Type | Description |
|---|---|---|
| `APP_SLUG` | str | Project slug |
| `--client-id TEXT` | str | OAuth client ID from the Epicollect app settings |
| `--client-secret TEXT` | str | OAuth client secret |

Access tokens are cached in `~/.wildintel-tools/access_token_<slug>.json` and reused on subsequent calls until they expire.

---

## get-entries

Retrieve all entries from a specific form and display them in a table or export them as CSV.

```bash
wildintel epicollect get-entries FORM_REF [APP_SLUG] [OPTIONS]
```

| Argument / Option | Type | Default | Description |
|---|---|---|---|
| `FORM_REF` | str | required | Form reference ID |
| `APP_SLUG` | str | `None` | Project slug |
| `--client-id TEXT` | str | `None` | OAuth client ID |
| `--client-secret TEXT` | str | `None` | OAuth client secret |
| `--to-csv / --no-to-csv` | bool | `None` | Export results to a CSV file |
| `--csv-file PATH` | Path | temp file | Output CSV path (only used when `--to-csv` is set) |
| `--filter TEXT` | list[str] | `None` | Post-filters in the form `FIELD==VALUE` or `FIELD==VALUE1\|VALUE2`. Repeatable. |
| `--fields TEXT` | list[str] | defaults | Fields to display in the output table. Repeatable. |

**Example**

```bash
# Show entries for a form
wildintel epicollect get-entries myFormRef123 my-project \
  --client-id abc --client-secret xyz \
  --filter "4_Sitio==A01"

# Export to CSV
wildintel epicollect get-entries myFormRef123 my-project \
  --client-id abc --client-secret xyz \
  --to-csv --csv-file /tmp/entries.csv
```

---

## entries-group-by-site

Retrieve form entries and display them grouped by site and session.

```bash
wildintel epicollect entries-group-by-site FORM_REF [APP_SLUG] [OPTIONS]
```

| Argument / Option | Type | Default | Description |
|---|---|---|---|
| `FORM_REF` | str | required | Form reference ID |
| `APP_SLUG` | str | `None` | Project slug |
| `--client-id TEXT` | str | `None` | OAuth client ID |
| `--client-secret TEXT` | str | `None` | OAuth client secret |
| `--filter TEXT` | list[str] | `None` | Post-filters (same format as `get-entries`) |
| `--fields TEXT` | list[str] | `None` | Fields to include |
| `--session-field TEXT` | str | `2_Sesion` | Form field used as the session identifier |
| `--site-field TEXT` | str | `4_Sitio` | Form field used as the site identifier |

---

## field-sheet

Generate a field sheet from Epicollect entries, grouped by site and session.

```bash
wildintel epicollect field-sheet FORM_REF [APP_SLUG] [OPTIONS]
```

Accepts the same options as `entries-group-by-site`.

---

## clean-tokens

Remove the cached OAuth access token for a project.

```bash
wildintel epicollect clean-tokens [APP_SLUG]
```

| Argument | Type | Description |
|---|---|---|
| `APP_SLUG` | str | Project slug whose token file will be deleted |
