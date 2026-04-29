# wildintel-tools

**wildintel-tools** is a command-line interface (CLI) for validating, preparing, and managing wildlife monitoring data in the [WildINTEL](https://wildintel.uhu.es) project and the [Trapper](https://trapper-project.org) camera-trap platform.

## Features

- Validate collection and deployment folder structures before ingesting data into Trapper.
- Prepare image sequences and generate Trapper-ready packages.
- Upload collections from Trapper to Zooniverse for citizen-science classification.
- Export Zooniverse annotation results back to Trapper as observations.
- Synchronise subject metadata between Trapper and Zooniverse.
- Query Epicollect project entries and generate field sheets.
- Manage project configuration files with a built-in settings system.

## Quick start

```bash
# Initialize a new project configuration
wildintel config init

# Check your Trapper connection
wildintel helpers test-connection <url> <user>

# Validate a collection
wildintel wildintel check-collections --data-path /path/to/collections

# Import a collection to Zooniverse
wildintel zooniverse import <collection_id> <subjectset_name> --rp <rp_id> --cp <cp_id>

# Export Zooniverse annotations back to Trapper
wildintel zooniverse export --wf <workflow_id> --ss <subjectset_id> --cp <cp_id> --collection <collection_id>
```

## Command groups

| Group | Description |
|---|---|
| [`config`](commands/config.md) | Create, view, and edit project configuration files |
| [`reports`](commands/reports.md) | List, inspect, archive, and remove report files |
| [`logger`](commands/logger.md) | View and archive project log files |
| [`helpers`](commands/helpers.md) | Test Trapper connections and list projects/locations |
| [`wildintel`](commands/wildintel.md) | Validate and prepare collections for Trapper |
| [`epicollect`](commands/epicollect.md) | Query Epicollect project entries and field sheets |
| [`zooniverse`](commands/zooniverse.md) | Import/export data between Trapper and Zooniverse |

## Installation

See the [Installation guide](installation.md) for instructions on how to install and set up wildintel-tools.

## Configuration

See the [Configuration guide](configuration.md) for instructions on configuring wildintel-tools for your project.
