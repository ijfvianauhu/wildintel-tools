import subprocess
import os
import argparse
from pathlib import Path

LOCALES_ROOT = Path(__file__).resolve().parent.parent / "src" / "wildintel_tools" / "locales"

def extract_translations():
    """
    Genera el archivo POT a partir de las cadenas marcadas en el proyecto.
    """
    pot_path = LOCALES_ROOT / "messages.pot"
    subprocess.run([
        "pybabel",
        "extract",
        "-F", "babel.cfg",
        "-o", str(pot_path),
        "."
    ], check=True)
    print(f"✅ Archivo POT generado en {pot_path}")


def init_translation(lang="en_GB"):
    """
    Genera el archivo PO para el idioma especificado a partir del POT.
    Si el PO ya existe, actualiza su contenido.
    """
    po_dir = LOCALES_ROOT / lang / "LC_MESSAGES"
    po_file = po_dir / "messages.po"

    os.makedirs(po_dir, exist_ok=True)

    pot_path = LOCALES_ROOT / "messages.pot"

    if not os.path.exists(po_file):
        # Inicializar archivo PO si no existe
        subprocess.run([
            "pybabel",
            "init",
            "-i", str(pot_path),
            "-d", str(LOCALES_ROOT),
            "-l", lang
        ], check=True)
        print(f"✅ Archivo PO creado para idioma '{lang}' en {po_file}")
    else:
        # Actualizar PO existente
        subprocess.run([
            "pybabel",
            "update",
            "-i", str(pot_path),
            "-d", str(LOCALES_ROOT),
            "-l", lang
        ], check=True)
        print(f"🔄 Archivo PO actualizado para idioma '{lang}' en {po_file}")


def compile_translations():
    """
    Compila todos los archivos PO a MO para que Python pueda usarlos.
    """
    subprocess.run([
        "pybabel",
        "compile",
        "-d", str(LOCALES_ROOT)
    ], check=True)
    print(f"✅ Todos los archivos PO han sido compilados a MO en {LOCALES_ROOT}")


def main():
    parser = argparse.ArgumentParser(
        description="Herramienta para gestionar traducciones con Babel."
    )

    parser.add_argument(
        "action",
        choices=["pot", "po", "mo"],
        help="Acción a ejecutar: 'pot' para extraer, 'po' para inicializar/actualizar, 'mo' para compilar."
    )

    parser.add_argument(
        "--lang",
        "-l",
        default="en",
        help="Idioma a inicializar o actualizar (solo necesario con 'po')."
    )

    args = parser.parse_args()

    if args.action == "pot":
        extract_translations()
    elif args.action == "po":
        init_translation(args.lang)
    elif args.action == "mo":
        compile_translations()


if __name__ == "__main__":
    main()

