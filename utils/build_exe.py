import platform
import subprocess
import sys

def get_artifact_name() -> str:
    system = platform.system().lower()

    if system == "windows":
        return "wildintel-tools.exe"
    elif system == "darwin":
        return "wildintel-tools-macos"
    elif system == "linux":
        return "wildintel-tools-linux"
    else:
        raise RuntimeError(f"Sistema operativo no soportado: {system}")

def main():
    artifact_name = get_artifact_name()

    command = [
#        "uv", "run",
        "pyinstaller",
        "--onefile",
        "--name", artifact_name,
        "src/wildintel_tools/ui/typer/main.py"
    ]

    print("🔧 Building binary with command:")
    print(" ".join(command))

    try:
        subprocess.run(command, check=True)
        print(f"✅ Build completado: {artifact_name}")
    except subprocess.CalledProcessError as e:
        print("❌ Error durante el build")
        sys.exit(e.returncode)


if __name__ == "__main__":
    main()
