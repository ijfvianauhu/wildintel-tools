import subprocess
import os

# === Constantes base del proyecto ===
BASE_PATH = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(BASE_PATH, "../.."))  # Ajusta según tu estructura
LOCALES_DIR = os.path.join(PROJECT_ROOT, "wildintel_tools", "locales")
POT_FILE = os.path.join(LOCALES_DIR, "messages.pot")

# === Idiomas disponibles ===
LANGUAGES = ["en_GB", "es_ES"]  # Añade aquí los códigos de idioma que quieras gestionar


def extract_translations():
    """
    Genera el archivo POT a partir de las cadenas marcadas en el proyecto.
    """
    subprocess.run([
        "pybabel",
        "extract",
        "-F", "babel.cfg",
        "-o", POT_FILE,
        PROJECT_ROOT
    ], check=True)
    print(f"✅ Archivo POT generado en {POT_FILE}")


def init_translations():
    """
    Genera o actualiza los archivos PO para todos los idiomas definidos en LANGUAGES.
    """
    for lang in LANGUAGES:
        po_dir = os.path.join(LOCALES_DIR, lang, "LC_MESSAGES")
        po_file = os.path.join(po_dir, "messages.po")

        # Crear carpeta si no existe
        os.makedirs(po_dir, exist_ok=True)

        if not os.path.exists(po_file):
            # Inicializar archivo PO si no existe
            subprocess.run([
                "pybabel",
                "init",
                "-i", POT_FILE,
                "-d", LOCALES_DIR,
                "-l", lang
            ], check=True)
            print(f"✅ Archivo PO creado para idioma '{lang}' en {po_file}")
        else:
            # Actualizar PO existente
            subprocess.run([
                "pybabel",
                "update",
                "-i", POT_FILE,
                "-d", LOCALES_DIR,
                "-l", lang
            ], check=True)
            print(f"🔄 Archivo PO actualizado para idioma '{lang}' en {po_file}")


def compile_translations():
    """
    Compila los archivos PO a MO solo para los idiomas definidos en LANGUAGES.
    """
    for lang in LANGUAGES:
        print(f"⚙️  Compilando idioma '{lang}'...")
        subprocess.run([
            "pybabel",
            "compile",
            "-d", LOCALES_DIR,
            "-l", lang
        ], check=True)
    print(f"💾 Archivos MO compilados para los idiomas: {', '.join(LANGUAGES)}")

