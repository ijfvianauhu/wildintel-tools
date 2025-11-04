Installation
============

WildIntel Tools can be installed in two different ways: using **Docker** (recommended) or locally via **uv**.

------------------------------------
Option 1 — Install using Docker
------------------------------------

1. Install Docker
   Follow the instructions for your operating system from the `Docker website <https://www.docker.com/get-started>`_.

2. Clone the repository::

      git clone https://github.com/ijfvianauhu/wildintel-tools.git
      cd wildintel-tools

3. Set up your data directory::

      export DATA_PATH=/path/to/camera_trap_data   # Linux
      $env:DATA_PATH="C:\\path\\to\\camera_trap_data"  # Windows PowerShell

4. Start the container::

      docker compose up -d
      docker compose exec --user trapper trapper-tools bash

5. Test the installation::

      wildintel-tools --help

------------------------------------
Option 2 — Install using ``uv``
------------------------------------

Install required dependencies first:

*Linux / macOS*::

    sudo apt install libimage-exiftool-perl ffmpeg

*Windows (PowerShell)*::

    winget install -e --id OliverBetz.ExifTool
    winget install -e --id Gyan.FFmpeg

Then install ``uv`` and clone the repository::

    curl -LsSf https://astral.sh/uv/install.sh | sh
    git clone https://github.com/ijfvianauhu/wildintel-tools.git
    cd wildintel-tools
    uv run wildintel-tools --help
