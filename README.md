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
- **Prepare deployments**: Prepares the directory structure required to import collections using the Trapper tools application. The images are resized and enriched with additional XMP metadata.

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

To use wildintel-tools effectively, store all your raw camera trap data in a main project directory. Organize collections 
(e.g., recording sessions) as subdirectories, and group files by deployments (e.g., individual camera locations) in 
further subfolders. Ensure these folder names match the deployment codes in your TRAPPER database, as this will be 
validated during the packaging step. The expected structure of multimedia files and subdirectories in the root (project)
directory is as follows:

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

wildintel-tools uses TOML configuration files to manage project settings. Each project can have its own configuration. 
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
> The .env file can also include your wildintel-tools global settings. See the example provided in this repository: env.example.

#### Step 4: Start the Docker container and open a terminal inside it

```
docker compose up -d
docker compose exec --user trapper trapper-tools bash
```

#### Step 5: Run trapper-tools commands

You can now run wildintel-tools commands inside the container. Refer to the [Usage section](#-usage) for available commands. For now, 
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

Once the required applications are installed, we can install `uv`:

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

To simplify the creation and management of configuration files, wildintel-tools provides the config command."

```bash
uv run wildintel-tools config --help  
                                                                                                                           
Usage: wildintel-tools config [OPTIONS] COMMAND [ARGS]...                                                                 
                                                                                                                           
Manage project configurations                                                                                             
                                                                                                                           
╭─ Options ───────────────────────────────────────────────────────────────────────────────────────────────────────────────╮
│ --help          Show this message and exit.                                                                             │
╰─────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────╯
╭─ Commands ──────────────────────────────────────────────────────────────────────────────────────────────────────────────╮
│ init   Initialize a new project configuration                                                                           │
│ show   Validate and show current project settings                                                                       │
│ list   List all available project configurations                                                                        │
│ edit   Edit settings file in default editor                                                                             │
│ get    Display a project setting                                                                                        │
│ set    Set a project setting                                                                                            │
╰─────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────╯
```

### Examples

```bash
# Create new default configuration at ~/.trapper-tools/default.toml
wildintel-tools config init 

# Create new configuration with named project
wildintel-tools --project myproject config init 

# Edit configuration file for a specific project
wildintel-tools --project myproject config edit

# Export configuration to custom location using template
wildintel-tools config init --template /path/to/template.toml

# Show configuration
wildintel-tools --project myproject config show

# List available configurations
wildintel-tools config list

# Use custom settings directory
trapper-tools --settings-dir /path/to/settings config init
```

### Configuration File Structure
TODO

## ⚡ Usage

Once you’ve installed [Wildintel-tools](https://github.com/ijfvianauhu/wildintel-tools), you can start using it 
right away from the command line. Here’s what a typical first session looks like from a user’s perspective.

> *Note*: If the installation was done using uv, it is necessary to activate the virtual environment by running 
> `source .venv/bin/activate.`

### Configure 

First of all, initialize the configuration file by running:

```python
wildintel-tools config init
```

Once this is done, edit it and modify the environment variables (typically the username and password") by running:
```python
wildintel-tools config edit
```
You can find a detailed description of each configuration option in [configuración section](#-configuration)

### check collections

After creating the configuration file, we proceed to check the names of the collections and deployments.

```python

```python
wildintel-tools wildintel check-collections  --data-path $HOME/Download/trapper-collections/
```

You can check the help for this command:

```python
wildintel-tools wildintel check-collections --help
                                                                                                                           
 Usage: wildintel-tools wildintel check-collections [OPTIONS] [COLLECTIONS]...                                             
                                                                                                                           
 Validates the names of collections and deployments within a given data directory. It checks that collection folders       
 follow the 'RNNNN' format and that deployment folders use the '<COLLECTION>-<LOCATION>_<SUFFIX>' pattern. Reports errors  
 and successes for each validation step.                                                                                   
                                                                                                                           
╭─ Arguments ─────────────────────────────────────────────────────────────────────────────────────────────────────────────╮
│   collections      [COLLECTIONS]...  Collections to process (sub-dirs in root data path)                                │
╰─────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────╯
╭─ Options ───────────────────────────────────────────────────────────────────────────────────────────────────────────────╮
│ --data-path          DIRECTORY  Root data path                                                                          │
│ --report-file        PATH       File to save the report                                                                 │
│ --help                          Show this message and exit.                                                             │
╰─────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────╯

```

### check deployments

Next, we will check whether the contents of each deployment are correct. The tool will verify the dates and the sequence of 
the media in each deployment based on the data provided in the field sheet — a CSV file per collection that contains 
information about each deployment.

```python
wildintel-tools wildintel check-deployments --data-path $HOME/Download/trapper-collections/ 
```
This command accepts additional options, which you can view by running

```
wildintel check-deployments --help
                                                                                                                           
 Usage: wildintel-tools wildintel check-deployments [OPTIONS] [COLLECTIONS]...                                             
                                                                                                                           
 Validates the structure and content of deployment folders within the specified collections. Checks that image files       
 exist, follow the expected chronological order, and that their timestamps are within the expected start and end ranges.   
 Also generates a '.validated' file for successfully verified deployments.                                                 
                                                                                                                           
╭─ Arguments ─────────────────────────────────────────────────────────────────────────────────────────────────────────────╮
│   collections      [COLLECTIONS]...  Collections to process (sub-dirs in root data path)                                │
╰─────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────╯
╭─ Options ───────────────────────────────────────────────────────────────────────────────────────────────────────────────╮
│ --data-path              DIRECTORY                                      Root data path                                  │
│ --report-file            PATH                                           File to save the report                         │
│ --tolerance-hours        INTEGER                                        Allowed time deviation (in hours) when          │
│                                                                         comparing the first and last image timestamps   │
│                                                                         against the expected deployment start and end   │
│                                                                         times.                                          │
│ --extensions             [.png|.jpg|.jpeg|.gif|.webp|.mp4|.mpeg|.mov|.  File extension to process                       │
│                          avi]                                                                                           │
│ --help                                                                  Show this message and exit.                     │
╰─────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────╯
```

### prepare collections for trapper

The final step of our workflow is responsible for 'flattening' each deployment and making several modifications to each media file.
Specifically, it resizes, renames, and adds various pieces of information in XMP format.

```python
wildintel-tools wildintel prepare-for-trapper --data-path $HOME/Descargas/trapper-collections/ --output-path /tmp/trapper/
```

```
wildintel-tools wildintel prepare-for-trapper --help
                                                                                                                           
 Usage: wildintel-tools wildintel prepare-for-trapper [OPTIONS]                                                            
                                                      [COLLECTIONS]...                                                     
                                                                                                                           
 Validate the internal structure of a collection by checking that all its deployments are correctly named, contain the     
 expected files, and match their associated metadata. The validation also ensures that deployment folders correspond to    
 the entries defined in the collection's CSV log and that image timestamps fall within the expected date ranges.           
                                                                                                                           
╭─ Arguments ─────────────────────────────────────────────────────────────────────────────────────────────────────────────╮
│   collections      [COLLECTIONS]...  Collections to process (sub-dirs in root data path)                                │
╰─────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────╯
╭─ Options ───────────────────────────────────────────────────────────────────────────────────────────────────────────────╮
│ --data-path          DIRECTORY                                        Root data path                                    │
│ --output-path        DIRECTORY                                        Root output path                                  │
│ --report-file        PATH                                             File to save the report                           │
│ --deployments        TEXT                                             Deployments to process (sub-dirs in collections   │
│                                                                       path)                                             │
│ --extensions         [.png|.jpg|.jpeg|.gif|.webp|.mp4|.mpeg|.mov|.av  File extension to process                         │
│                      i]                                                                                                 │
│ --owner              TEXT                                             Resource owner                                    │
│ --publisher          TEXT                                             Resource publisher                                │
│ --coverage           TEXT                                             Resource publisher                                │
│ --rp-name            TEXT                                             Research project name                             │
│ --help                                                                Show this message and exit.                       │
╰─────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────╯
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