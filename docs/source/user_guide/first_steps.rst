First steps
===========

Directory structure and restrictions
------------------------------------
Base layout
~~~~~~~~~~~
WildIntel expects a single host directory that contains all collections and the processed output. Common layout:

.. code-block:: text

   wildintel-tools-data/
   ├── collections/
   │   ├── R0001/
   │   │   ├── R0001-LOC01/
   │   │   │   ├── IMG_0001.JPG
   │   │   │   ├── IMG_0002.JPG
   │   │   ├── R0001_FileTimestampLog.csv
   │   ├── R0002/
   ├── collections-ready-to-trapper/

Naming rules and restrictions
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
- Collection names must follow the pattern: letter `R` followed by four digits (example: `R0033`).
- Deployment folder names must be the concatenation of the collection code, a hyphen, and the deployment/location identifier (example: `R0033-DONA_0007_B`).
- Each collection root must include a timestamps CSV file named `<COLLECTION>_FileTimestampLog.csv` (example: `R0001_FileTimestampLog.csv`).
- The CSV must have one line per deployment and include these columns in order: `Deployment,StartDate,StartTime,EndDate,EndTime`.
- Deployment folders should contain only media files (images, videos) and no nested collection directories.
- Filenames should be unique within a deployment and preserve chronological order when sorted by filename if timestamps are missing.
- Ensure correct host filesystem permissions so the application (or Docker container) can read and write the host path.

Initial configuration
----------------------
Set the main folders
~~~~~~~~~~~~~~~~~~~~
- If using Docker, set the host data directory via the `DATA_PATH` environment variable (for example in a `.env` file placed next to `docker-compose.yml`):

.. code-block:: text

   # .env
   DATA_PATH=./wildintel-tools-data/
   OUTPUT_PATH=./collections-ready-to-trapper/

- If running outside Docker, set `GENERAL.data_dir` and `GENERAL.output_dir` in the project TOML configuration (see examples below) or override with `--data-path` / `--output-path` command options.

Login and password
~~~~~~~~~~~~~~~~~~
- Provide Trapper server credentials in the configuration under `GENERAL.login` and `GENERAL.password`.
- Prefer using `wildintel-tools config init` then `wildintel-tools config edit` (or `wildintel-tools config set`) to populate credentials.
- Protect the settings directory (file permissions) because credentials are stored in plain TOML by default.

Metadata variables
~~~~~~~~~~~~~~~~~~
Define project metadata under the `WILDINTEL` and `GENERAL` configuration sections. Example TOML snippet:

.. code-block:: toml

   [GENERAL]
   data_dir = "/data/wildintel-tools-data"
   output_dir = "/data/collections-ready-to-trapper"
   login = "username@example.com"
   password = "secret"

   [WILDINTEL]
   rp_name = "WildINTEL"
   coverage = "Doñana National Park"
   publisher = "University of Huelva"
   owner = "University of Huelva"
   tolerance_hours = 1
   resize_img = false
   resize_img_size = [800, 600]
   overwrite = false

- `rp_name`, `publisher`, `owner`, `coverage`: values embedded in output metadata.
- `tolerance_hours`: allowed tolerance (hours) when validating first/last image timestamps.
- `resize_img` and `resize_img_size`: control image resizing during preparation.
- `overwrite`: allow replacing existing output directories when preparing collections.

Validating collections
----------------------
Command
~~~~~~~
Use:

.. code-block:: bash

   wildintel-tools wildintel check-collections [COLLECTIONS...] [--data-path PATH]

What it checks
~~~~~~~~~~~~~~
- Collection and deployment naming conventions.
- Existence of the `<COLLECTION>_FileTimestampLog.csv` file.
- Basic CSV format and presence of entries for each declared deployment.
- Reports missing collections or CSV mismatches.

Outputs
~~~~~~~
- Human-readable summary on the console.
- Detailed reports saved in the application's reports directory; listable with `wildintel-tools reports list` and viewable with `wildintel-tools reports info`.

Validating deployments
----------------------
Command
~~~~~~~
Use:

.. code-block:: bash

   wildintel-tools wildintel check-deployments [COLLECTIONS...] [--data-path PATH] [--tolerance-hours N] [--deployments DEP1,DEP2]

What it checks
~~~~~~~~~~~~~~
- Each deployment folder exists and is readable.
- Media files exist and are in expected chronological order.
- Image/video timestamps vs. StartDate/EndDate from the collection CSV, allowing `tolerance_hours`.
- Presence of required media types and minimal file counts (if configured).

Common results
~~~~~~~~~~~~~~
- Success: deployment passes all checks.
- Warnings: minor issues (missing metadata, non-consecutive timestamps).
- Errors: missing files, timestamp outside allowed range, malformed CSV rows.

Preparing collections for Trapper
--------------------------------
Command
~~~~~~~
Use:

.. code-block:: bash

   wildintel-tools wildintel prepare-for-trapper [COLLECTIONS...] [--data-path PATH] [--output-path PATH] [--overwrite] [--deployments DEP1,DEP2]

What it does
~~~~~~~~~~~~~
- Flattens each deployment into the structure expected by `trapper-tools`.
- Optionally resizes images according to `WILDINTEL.resize_img` and `resize_img_size`.
- Embeds XMP metadata (using `exiftool`) with values from `WILDINTEL` and `GENERAL`.
- Renames files if required and writes outputs into `GENERAL.output_dir` or `OUTPUT_PATH`.

Options and behavior
~~~~~~~~~~~~~~~~~~~~
- `--overwrite`: replace existing prepared deployment directories if present.
- `--deployments`: limit processing to a subset of deployments.
- Output is placed under the host `collections-ready-to-trapper` path; verify permissions and available space before running.

Quick verification
------------------
- After preparation, inspect the output folder and check generated XMP metadata using `exiftool -G -a -s <file>` or similar tools.
- Use `wildintel-tools reports list` and `wildintel-tools reports info <report>` to inspect any issues generated during processing.
