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

## ⚙️ Configuration

## ⚡ Usage

Once you’ve installed [Wildintel-tools](https://github.com/ijfvianauhu/wildintel-tools), you can start using it 
right away from the command line. Here’s what a typical first session looks like from a user’s perspective.


### Create TrapperClient instance

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