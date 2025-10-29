import subprocess
from pathlib import Path

def build_docs():
    """
    Generate Sphinx documentation automatically.
    """
    docs_source = Path("docs/source")
    docs_build = Path("docs/build/html")

    # Regenerar los archivos .rst
    subprocess.run(["sphinx-apidoc", "-f", "-o", str(docs_source), "trapper_zooniverse"], check=True)

    # Construir la documentación HTML
    subprocess.run(["sphinx-build", "-b", "html", str(docs_source), str(docs_build)], check=True)

    print(f"✅ Documentation built at {docs_build}")

