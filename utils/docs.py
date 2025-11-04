#!/usr/bin/env python3
"""
CLI helper for building Sphinx documentation using uv environments.
Usage examples:
  uv run python scripts/docs.py apidoc
  uv run python scripts/docs.py build
  uv run python scripts/docs.py serve
"""

import argparse
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / "docs"
SRC = ROOT / "src"


def run_command(cmd: list[str], description: str):
    print(f"\n📘 {description}...")
    result = subprocess.run(cmd)
    if result.returncode != 0:
        print(f"❌ Error: {description} failed with code {result.returncode}")
        sys.exit(result.returncode)
    print(f"✅ Done: {description}")


def apidoc():
    """Generate Sphinx API documentation from the Python source."""
    run_command(
        ["uv", "run", "sphinx-apidoc", "-o", str(DOCS / "source" / "api"), str(SRC)],
        "Generating API documentation",
    )


def build():
    """Build HTML documentation using Sphinx."""
    run_command(
        ["uv", "run", "sphinx-build", "-b", "html", str(DOCS / "source"), str(DOCS / "build")],
        "Building HTML documentation",
    )


def serve(port: int):
    """Serve the generated documentation locally."""
    print(f"🌐 Serving docs at http://127.0.0.1:{port}")
    subprocess.run(
        ["uv", "run", "python", "-m", "http.server", "--directory", str(DOCS / "build"), str(port)]
    )


def clean():
    """Clean the build directory."""
    if (DOCS / "build").exists():
        print("🧹 Cleaning build directory...")
        subprocess.run(["rm", "-rf", str(DOCS / "build")])
    else:
        print("No build directory found.")


def main():
    parser = argparse.ArgumentParser(
        description="Manage Sphinx documentation tasks inside uv environments."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # Subcommand: apidoc
    subparsers.add_parser("apidoc", help="Generate API documentation from source files.")

    # Subcommand: build
    subparsers.add_parser("build", help="Build HTML documentation with Sphinx.")

    # Subcommand: serve
    serve_parser = subparsers.add_parser("serve", help="Serve the built documentation locally.")
    serve_parser.add_argument("--port", type=int, default=8000, help="Port to serve docs on.")

    # Subcommand: clean
    subparsers.add_parser("clean", help="Remove generated documentation files.")

    args = parser.parse_args()

    if args.command == "apidoc":
        apidoc()
    elif args.command == "build":
        build()
    elif args.command == "serve":
        serve(args.port)
    elif args.command == "clean":
        clean()


if __name__ == "__main__":
    main()
