from dynaconf import ValidationError
import typer
from src.wildintel_tools.ui.typer.i18n import _
from src.wildintel_tools.ui.typer.TyperUtils import TyperUtils

app = typer.Typer(
    help=_("Manage project logger"),
    short_help=_("Manage project logger")
)

@app.callback()
def main_callback(ctx: typer.Context,
      ):
    pass


@app.command("show", help=_("Show log file content"), short_help=_("Show log file content"))
def show_logger(
    follow: bool = typer.Option(False, help=_("Follow file content (like tail -f)")),
):
    config:AppConfig= config_manager.load_config()
    log_path = config.logger.logfilename

    if log_path.exists():
        with log_path.open("r") as f:
            if follow:
                # Ir al final del archivo
                f.seek(0, 2)
            else:
                # Mostrar todo el contenido existente
                for line in f:
                    print(line, end="")
                exit()
            try:
                while True:
                    line = f.readline()
                    if line:
                        print(line, end="")  # `end=""` para no duplicar saltos de línea
                    else:
                        time.sleep(0.5)  # Espera antes de volver a leer
            except KeyboardInterrupt:
                TyperUtils.info(_("\nStopped following the log."))
    else:
        TyperUtils.fatal(_(f"Log file not found: {log_path}"))

@app.command("logger-archive", help=_("Compress the log file and remove the original"), short_help=_("Compress and archive log"))
def logger_archive():
    # Cargar configuración

    config: AppConfig = config_manager.load_config()
    log_path = config.logger.logfilename

    if not log_path.exists():
        TyperUtils.fatal(_(f"Log file not found: {log_path}"))

    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    archive_path = log_path.with_name(f"{log_path.stem}_{timestamp}{log_path.suffix}.gz")

    with log_path.open("rb") as f_in, gzip.open(archive_path, "wb") as f_out:
        shutil.copyfileobj(f_in, f_out)

    log_path.unlink()

    TyperUtils.success(_(f"Log archived to: {archive_path}"))

