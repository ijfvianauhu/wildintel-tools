# <img src="img/wildIntel_logo.webp" alt="Wildintel Tools Logo" height="60">  wildintel-tools

![Python](https://img.shields.io/badge/python-3.11-blue.svg)
![License](https://img.shields.io/badge/license-GPLv3-blue.svg)
[![WildINTEL](https://img.shields.io/badge/WildINTEL-v1.0-blue)](https://wildintel.eu/)
[![Trapper](https://img.shields.io/badge/Trapper-Server-green)](https://gitlab.com/trapper-project/trapper)

<hr>

## Utilities for managing and validating WildIntel data

## 🚀 Features

- **Check collectionss**: Validates the names of collections and deployments within a given data directory. 
- **Check deployments**: Validates the structure and content of deployment folders within the specified collections. Checks that image files exist, follow the expected chronological order, and that their "
        timestamps are within the expected start and end ranges. Also generates a '.validated' file for successfully verified deployments.
- **Prepare deployments**: Prepara la estructura de directorios necesaria para importar colleciones usando la aplicación Trapper tools. Las imágenes son redimensionadas y se le añade distinta información XMP.


## 📋 Requirements

* Python 3.12 or higher  
* uv (for dependency management and packaging)  
* Typer and rich (for CLI interface)  
* dynaconf (for configuration management)
* pyexiftool (for metadata extraction)
* Docker (optional, for running in a container)
* Access to a Trapper server instance

## 🧭 Overview

WildIntel Tools is a utility suite for validating and preparing wildlife monitoring data. It ensures that collection and 
deployment folders follow standardized naming conventions, verifies that images exist and are in chronological order, and 
marks validated deployments with a .validated file.

Once validated, it prepares collections for import into Trapper, flattening folder structures, resizing images, and 
embedding essential XMP metadata.

In short, WildIntel Tools streamlines the workflow from data quality control to ready-to-use datasets, keeping information 
consistent, traceable, and properly formatted for analysis.

To use trapper-tools effectively, store all your raw camera trap data in a main project directory. Organize collections (e.g., recording sessions) as subdirectories, and group files by deployments (e.g., individual camera locations) in further subfolders. Ensure these folder names match the deployment codes in your TRAPPER database, as this will be validated during the packaging step. The expected structure of multimedia files and subdirectories in the root (project) directory is as follows:

```
|- collection_name_1
|  |- deployment_id_1
|     |- filename_1
|     |- filename_2
|     |- filename_3
|     |- filename_4
|  |- deployment_id_2
|     |- filename_1
|     |- filename_2
|     |- filename_3
|     |- filename_4
|  |- ...
|- collection_name_2
|  |- deployment_id_3
|     |- ...
|  |- ...
|- ...
```

WildIntel Tools uses TOML configuration files to manage project settings. Each project can have its own configuration. 
See [Configuration](#configuration) section for details.

## 💻 Installation

WildIntel-trap can be installed either using Docker or via a traditional Python virtual environment (venv). Docker allows 
you to run the application in an isolated container with all dependencies included, while using a virtual environment lets 
you install and run it directly on your system.

### Install wildintel-tools using `docker`

The easiest way to install wildintel-tools is by using the provided Docker Compose file. Follow the steps below:

#### Step 1: Install Docker
Follow the instructions for your operating system on the Docker website.

#### Step 2: Download docker-compose.yml

You can download the `docker-compose.yml` file from here or clone this repository:

```
git clone https://github.com/ijfvianauhu/wildintel-tools.git
cd wildintel-tools
```

#### Step 3: Set up a directory with your camera trap data to mount into the container

On the host machine where Docker is running, you need to have a directory containing the images you want to process. To
make this directory accessible inside the Docker container, you must set the `DATA_PATH` environment variable to the path 
of that directory.

```
# Linux bash 
export DATA_PATH=/path/to/camera_trap_data

# Windows PowerShell
$env:DATA_PATH = "C:\path\to\camera_trap_data"
```

> **Note:** You can also define the DATA_PATH variable in a .env file located in the same directory as docker-compose.yml. 
> The .env file can also include your trapper-tools global settings. See the example provided in this repository: env.example.

#### Step 4: Set up a directory with your camera trap data to mount into the container

```
docker compose up -d
docker compose exec --user trapper trapper-tools bash
```

#### Step 5: Run trapper-tools commands

You can now run trapper-tools commands inside the container. Refer to the Usage section for available commands. For now, 
let's verify that everything is working by running:

```
trapper-tools --help
```

You should see the following output:

```
Usage: wildintel-tools [OPTIONS] COMMAND [ARGS]...                             
                                                                                
 WildINTEL CLI Tool                                                             
                                                                                
╭─ Options ────────────────────────────────────────────────────────────────────╮
│ --version                            Show program's version number and exit  │
│ --verbosity                 INTEGER  Logger level: 0 (error), 1 (info), 2    │
│                                      (debug).                                │
│                                      [default: 1]                            │
│ --logfile                   PATH     Path to the log file                    │
│                                      [default:                               │
│                                      /root/.config/wildintel-tools/app.log]  │
│ --locale                    TEXT     Language code (for example, “es”,       │
│                                      “en”). By default, the system language  │
│                                      is used.                                │
│                                      [default: C]                            │
│ --project                   TEXT     Project name for settings               │
│                                      [default: default]                      │
│ --env-file                           Load .env file with dotenv              │
│ --settings-dir              PATH     Directory containing settings files     │
│                                      [default:                               │
│                                      /root/.config/wildintel-tools]          │
│ --install-completion                 Install completion for the current      │
│                                      shell.                                  │
│ --show-completion                    Show completion for the current shell,  │
│                                      to copy it or customize the             │
│                                      installation.                           │
│ --help                               Show this message and exit.             │
╰──────────────────────────────────────────────────────────────────────────────╯
╭─ Commands ───────────────────────────────────────────────────────────────────╮
│ config      Manage project configurations                                    │
│ wildintel   Utilities for managing and validating WildIntel data             │
╰──────────────────────────────────────────────────────────────────────────────╯
```

### Install wildintel-tools using `uv`

wildintel-tools requires several system utilities to be installed before it can be properly set up using `uv`. These utilities 
are exiftool and ffmpeg. To install them run:

```bash
# 
# Install ExifTool
sudo apt install libimage-exiftool-perl
# MAC
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
brew install exiftool
# Windows 10/11
winget install -e --id Git.Git

**Git Bash for Windows**, install using `winget`: 
```bash
# Download from https://gitforwindows.org/
# Or install using winget:
winget install -e --id Git.Git
winget install -e --id OliverBetz.ExifTool
```

Alternative manual installation:
- FFmpeg: Download from [ffmpeg.org/download.html](https://ffmpeg.org/download.html)
- ExifTool: Download from [exiftool.org](https://exiftool.org)

After installation:
1. Add FFmpeg's bin directory to your system PATH (typically `C:\Program Files\ffmpeg\bin`)
2. Add ExifTool to your system PATH (typically `C:\Program Files\exiftool`)

Once the required applications are installed, we can install uv:

```
# Install uv if not already installed
curl -LsSf https://astral.sh/uv/install.sh | sh
git clone https://github.com/ijfvianauhu/wildintel-tools.git
cd wildintel-tools
uv run trapper-tools --help
```

## ⚙️ Configuration

Wildintel Tools uses [TOML](https://toml.io/en/) configuration files to manage project settings. Each project can have 
its own configuration, and every command performs strict validation, reporting missing or malformed keys with clear 
error messages. You can create multiple project configurations for different Trapper servers, projects, and settings, and 
switch between them using the `--project` flag.

```bash
wildintel-tools [OPTIONS] COMMAND [ARGS]...  
```

### Options

Root-level configuration arguments:
- --version   :                         Show program's version number and exit                                             │
- --verbosity : Logger level: 0 (error), 1 (info), 2 (debug). 
- --logfile   : Path to the log file
- --locale    : Language code (for example, “es”, “en”). By default, the system language is used.
- --project   : Project name for settings [default: default]                                       │
- --env-file  : Load .env file with dotenv                                                         │
- --settings-dir : Directory containing settings files                                                │
- --install-completion                 Install completion for the current shell.                                          │
- --show-completion                    Show completion for the current shell, to copy it or customize the installation.   │
- --help                               Show this message and exit.       

### Command

-  config      Manage project configurations│
-  wildintel   Utilities for managing and validating WildIntel data                                                        │

Configuration command arguments:
- `--init`: Create a new configuration file.
- `--list`: List available configurations.
- `--edit`: Open the configuration file in the default text editor (nano for Docker version).
- `--show`: Validate and display the current configuration.
- `--template`: Import settings from a custom TOML template file.


### Examples

```bash
# Create new default configuration at ~/.trapper-tools/default.toml
wildintel-tools config --init 

# Create new configuration with named project
wildintel-tools --project myproject config --init 

# Edit configuration file for a specific project
wildintel-tools --project myproject config --edit

# Export configuration to custom location using template
wildintel-tools config --template /path/to/template.toml --init

# Show configuration
wildintel-tools --project myproject config --show

# List available configurations
wildintel-tools config --list

# Use custom settings directory
trapper-tools --settings-dir /path/to/settings config --init
```

### Configuration File Structure

### Updating Configuration

Configuration edits are made directly in the TOML file. Use `trapper-tools config --edit` to open the file in the built-in
or your default editor, or provide a pre-built template with `--template`. All settings are validated before saving. Each 
time you run `config --show`, `convert`, `package`, `upload`, or `pipeline`, the configuration is validated and detailed errors 
are reported if any required variables are missing or have invalid values.


## ⚡ Usage

Once you’ve installed [Wildintel-tools](https://github.com/ijfvianauhu/wildintel-tools), you can start using it 
right away from the command line. Here’s what a typical first session looks like from a user’s perspective.


### Configure 

First of all, initialize the configuration file by running:

```python
wildintel-tools config init
```

Once this is done, edit it and modify the environment variables by running:
```python
wildintel-tools config edit
```
You can find a detailed description of each configuration option in configuración section

### check collections

```python

```python
uv run wildintel-tools wildintel check-collections $HOME/Download/trapper-collections/
```

### check deployments

```python
uv run wildintel-tools wildintel check-deployments $HOME/Download/trapper-collections/ 
```

### prepare collections for trapper

```python
uv run wildintel-tools wildintel prepare-for-trapper $HOME/Descargas/trapper-collections/ /tmp/trapper/
```

## 🤝 Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

## 📝 License

This project is licensed under the GNU General Public License v3.0 or later - see the [LICENSE](LICENSE) file for details.

This program is free software: you can redistribute it and/or modify it under the terms of the GNU General Public License as published by the Free Software Foundation, either version 3 of the License, or (at your option) any later version.


## 🏛️ Funding

This work is part of the [WildINTEL project](https://wildintel.eu/), funded by the Biodiversa+ Joint Research Call 2022-2023 “Improved
transnational monitoring of biodiversity and ecosystem change for science and society (BiodivMon)”. Biodiversa+ is the 
European co-funded biodiversity partnership supporting excellent research on biodiversity with an impact for policy and
society. Biodiversa+ is part of the European Biodiversity Strategy for 2030 that aims to put Europe’s biodiversity on a
path to recovery by 2030 and is co-funded by the European Commission. 