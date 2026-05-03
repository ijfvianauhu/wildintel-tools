Configuring WildIntel Tools
============================

Docker-based installation and `DATA_PATH`
----------------------------------------
When installing or running the application using Docker, you must define the environment variable `DATA_PATH`. This
variable must point to a valid directory on the host filesystem where the Docker container will store and generate data.
The `docker-compose.yml` file reads `DATA_PATH` and mounts the host path into the container (in the `/data` directory).

Recommended methods to define `DATA_PATH`:

Using a `.env` file (recommended)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Create or edit the `.env` file next to your `docker-compose.yml` and add:

.. code-block:: text

   # .env
   DATA_PATH=./wildintel-tools-data/

This approach is persistent and used automatically by `docker compose`.

Exporting in a Unix shell (temporary)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Export the variable in the current shell session before running Docker Compose:

.. code-block:: bash

   export DATA_PATH=/home/youruser/wildintel-tools-data
   docker compose up -d

PowerShell example (temporary)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Set the environment variable for the current PowerShell session:

.. code-block:: powershell

   $env:DATA_PATH = "C:\wildintel-tools-data"
   docker compose up -d

Persistent system-wide on Windows (optional)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
To persist the variable for future sessions, use `setx` in an elevated PowerShell:

.. code-block:: powershell

   setx DATA_PATH "C:\wildintel-tools-data"

.. note::
   - Ensure the host directory exists and has appropriate permissions so the container user can read/write data.
   - The container will expose the host path at `/data` inside the container. You can verify the mount:

   .. code-block:: bash

      docker compose up -d
      docker compose exec wildintel-tools ls -la /data

   - Place the `.env` file in the same directory as `docker-compose.yml` so Compose picks it up automatically.

Application configuration
=========================

Configuration overview
----------------------
WildIntel Tools stores project settings in TOML files. Each project has a separate configuration file that controls
connection details, paths and processing options. Configuration is managed via the CLI helper command:

.. code-block:: bash

   wildintel-tools config <command> [OPTIONS]

The default settings directory is platform-dependent; use the `--settings-dir` option or the `--project` flag to select
a specific named configuration.

Managing configurations with `wildintel-tools config`
----------------------------------------------------
Create a new configuration (interactive)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
To generate a new configuration file for the current user and project run:

.. code-block:: bash

   wildintel-tools config init

This command creates a TOML file for the current project (default name `default`) and populates it with sensible
defaults. Use `--template` to initialize from a custom template, or `--project` to name the project.

Show and validate configuration
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
To display and validate the active project configuration:

.. code-block:: bash

   wildintel-tools config show
   wildintel-tools --project myproject config show

This prints the parsed configuration and reports missing or malformed keys.

List available configurations
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
To list all saved project configurations:

.. code-block:: bash

   wildintel-tools config list

Edit configuration
~~~~~~~~~~~~~~~~~~
Open the active project's configuration file in the default editor:

.. code-block:: bash

   wildintel-tools config edit

Get and set single values
~~~~~~~~~~~~~~~~~~~~~~~~~
Read a single setting:

.. code-block:: bash

   wildintel-tools config get <SECTION>.<KEY>

Set or change a single setting (persists to the TOML file):

.. code-block:: bash

   wildintel-tools config set <SECTION>.<KEY> <VALUE>
   # Example
   wildintel-tools config set GENERAL.data_dir /data/wildintel-tools-data

Configuration sections and common options
-----------------------------------------
The configuration file is structured in sections. Common sections and options include:

- `LOGGER`:
  - `loglevel`: integer (0=error, 1=info, 2=debug).
  - `filename`: optional path for a log file.

- `GENERAL`:
  - `host`: URL of the Trapper server (for integration).
  - `login`: username for the Trapper server.
  - `password`: password (store with care).
  - `project_id`: numeric project identifier on the Trapper server.
  - `verify_ssl`: boolean, whether to verify TLS/SSL.
  - `ffmpeg`: path or command name for `ffmpeg` (used for media processing).
  - `exiftool`: path or command name for `exiftool` (used for metadata extraction).
  - `data_dir`: path to the main data directory on the host (used when not using `DATA_PATH`).
  - `output_dir`: path where processed collections are written (e.g., collections-ready-to-trapper).

- `WILDINTEL`:
  - `rp_name`: repository or project display name.
  - `coverage`: textual description of coverage (e.g., protected area).
  - `publisher`: publisher name included in metadata.
  - `owner`: owner name included in metadata.
  - `tolerance_hours`: integer, tolerance when validating deployment time ranges (hours).
  - `resize_img`: boolean, whether to resize images during preparation.
  - `resize_img_size`: array of two integers \[width, height\] used when `resize_img` is true.
  - `overwrite`: boolean, allow overwriting existing output directories.

.. note::

    - Use `wildintel-tools config init` to create a baseline config, then `config edit` to fine-tune values.
    - Prefer absolute paths for `data_dir` and `output_dir` to avoid surprises.
    - Sensitive values (passwords) are stored in the TOML file; protect your settings directory with appropriate
      filesystem permissions.
    - For Docker deployments, prefer setting `DATA_PATH` via the `.env` file. The `GENERAL.data_dir` setting is used when
      running the application outside Docker or when overriding the environment variable.
