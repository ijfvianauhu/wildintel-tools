# helpers

Utilities for testing connections and querying information from a Trapper instance. Also tests availability of external tools (ffmpeg, exiftool).

Most commands accept `URL` and `USER` as positional arguments and `--password` / `--token` as options. When omitted, values are taken from the active project settings (`GENERAL.host`, `GENERAL.login`, `GENERAL.password`).

---

## test-connection

Test the connection to a Trapper server API.

```bash
wildintel helpers test-connection [URL] [USER] [OPTIONS]
```

Alias: `tc`

| Argument / Option | Type | Default | Description |
|---|---|---|---|
| `URL` | str | settings | Base URL of the Trapper server (e.g. `https://trapper.example.org`) |
| `USER` | str | settings | Username for authentication |
| `--password, -p` | str | `None` | Password (use only when not providing a token) |
| `--token, -t` | str | `None` | API access token (alternative to password) |
| `--project-id` | int | `None` | Classification project ID to include in the connection test |

**Example**

```bash
wildintel helpers test-connection https://trapper.example.org admin@example.org --password secret
```

---

## test-external-tools

Check that `ffmpeg` and `exiftool` are available at the paths defined in the active project settings.

```bash
wildintel helpers test-external-tools
```

Alias: `tet`

---

## classification-projects

Retrieve and display the list of classification projects from a Trapper instance.

```bash
wildintel helpers classification-projects [URL] [USER] [OPTIONS]
```

Alias: `cp`

| Argument / Option | Type | Default | Description |
|---|---|---|---|
| `URL` | str | settings | Trapper server base URL |
| `USER` | str | settings | Username for authentication |
| `--password, -p` | str | `None` | Password |
| `--token, -t` | str | `None` | API access token |

Displays columns: `pk`, `name`, `research_project`.

---

## research-projects

Retrieve and display the list of research projects from a Trapper instance.

```bash
wildintel helpers research-projects [URL] [USER] [OPTIONS]
```

Alias: `rp`

Same options as `classification-projects`. Displays columns: `pk`, `acronym`, `name`.

---

## locations

Retrieve and display the list of locations defined in a Trapper instance.

```bash
wildintel helpers locations [URL] [USER] [OPTIONS]
```

Alias: `loc`

Same options as `classification-projects`. Displays columns: `pk`, `location_id`, `research_project`, `timezone`, `ignoreDST`, `coordinates`.

---

## deployments

Retrieve and display the list of deployments from a Trapper instance.

```bash
wildintel helpers deployments [URL] [USER] [OPTIONS]
```

Alias: `dep`

Same options as `classification-projects`. Displays columns: `pk`, `deployment_id`, `research_project`, `location`, `location_id`, `start_date`, `end_date`.
