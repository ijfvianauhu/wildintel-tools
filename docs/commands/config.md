# config

Manage project configuration files. Each project has its own YAML settings file stored in `~/.wildintel-tools/settings/`.

---

## init

Create a new project configuration file.

```bash
wildintel config init [OPTIONS]
```

| Option | Type | Default | Description |
|---|---|---|---|
| `--template PATH` | Path | `None` | Path to a custom settings template file |
| `--env-file / --no-env-file` | bool | `False` | Load environment variables from a `.env` file to pre-fill settings |

**Example**

```bash
wildintel config init
wildintel config init --template ~/my_template.yaml
```

---

## show

Validate the current project settings and display their values grouped by section.

```bash
wildintel config show
```

Exits with an error if configuration validation fails.

---

## list

List the names of all available project configuration files.

```bash
wildintel config list
```

---

## edit

Open the configuration file for a specific project in the system's default editor. The configuration is validated automatically when the editor is closed.

```bash
wildintel config edit [PROJECT_NAME]
```

| Argument | Type | Default | Description |
|---|---|---|---|
| `PROJECT_NAME` | str | `default` | Name of the project configuration to edit |

**Example**

```bash
wildintel config edit
wildintel config edit myproject
```

---

## get

Display the value of a specific configuration parameter.

```bash
wildintel config get [OPTIONS] PARAM
```

| Argument / Option | Type | Default | Description |
|---|---|---|---|
| `PARAM` | str | required | Parameter to read, in `GROUP.key` format (e.g. `GENERAL.host`) |
| `--project-name TEXT` | str | `default` | Project from which to read the setting |

**Example**

```bash
wildintel config get GENERAL.host
wildintel config get ZOONIVERSE.zooniverse_username
```

---

## set

Update or create a configuration parameter within a project. The configuration is validated after the change.

```bash
wildintel config set [OPTIONS] PARAM_NAME PARAM_VALUE
```

| Argument / Option | Type | Default | Description |
|---|---|---|---|
| `PARAM_NAME` | str | required | Parameter to set, in `GROUP.key` format |
| `PARAM_VALUE` | str | required | New value for the parameter |
| `--project-name TEXT` | str | `default` | Project whose configuration will be modified |

**Example**

```bash
wildintel config set GENERAL.host https://trapper.example.org/
wildintel config set WILDINTEL.timezone Europe/Madrid
```
