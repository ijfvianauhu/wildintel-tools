# logger

Manage the application log file. The log path is defined in the `LOGGER.filename` setting of the active project configuration.

---

## show

Display the contents of the current log file. Can optionally follow new log entries in real time (like `tail -f`).

```bash
wildintel logger show [OPTIONS]
```

| Option | Type | Default | Description |
|---|---|---|---|
| `--follow / --no-follow` | bool | `False` | If enabled, continuously stream new log entries as they are written (press Ctrl+C to stop). |

**Examples**

```bash
# Print the entire log file
wildintel logger show

# Follow new entries in real time
wildintel logger show --follow
```

---

## logger-archive

Compress the current log file into a `.gz` archive with a timestamped filename and remove the original.

```bash
wildintel logger logger-archive
```

The archive is placed in the same directory as the original log file. The filename follows the pattern:

```
<log_stem>_<YYYY-MM-DD_HH-MM-SS><log_suffix>.gz
```

**Example**

If the log file is `app.log`, the archive will be named `app_2025-10-31_16-45-02.log.gz`.
