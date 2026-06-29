"""
TrapperNavigator
================

Clase para automatizar la navegación en la interfaz web de Trapper
usando Playwright (navegación headless/headful).

Cada método público corresponde a una acción concreta sobre la interfaz
web de Trapper que no está expuesta en la API REST.

Métodos disponibles
-------------------
upload_expert_classifications(csv_files, project_id, ...)
    Sube uno o varios CSV con resultados de clasificación humana
    a través del formulario de importación de Trapper.

upload_deployments(csv_file, research_project_id, timezone, ...)
    Sube un CSV con deployments a través del formulario de importación
    en /geomap/deployment/import/.

Uso básico
----------
::

    from wildintel_tools.navigator import TrapperNavigator

    nav = TrapperNavigator(
        base_url="https://wildintel-trap.uhu.es",
        username="admin",
        password="secret",
    )
    report = nav.upload_expert_classifications(
        csv_files=[Path("results.csv")],
        project_id=7,
    )
    print(report)

    report = nav.upload_deployments(
        csv_file=Path("deployments.csv"),
        research_project_id=7,
        timezone="Europe/Madrid",
        create_locations=True,
    )
    print(report)
"""

from __future__ import annotations

import logging
import subprocess
import sys
from pathlib import Path
from typing import Callable, List, Literal, Optional

from wildintel_tools.reports import Report


# ── Constantes por defecto ────────────────────────────────────────────────────

_DEFAULT_TIMEOUT_MS = 30 * 60 * 1000  # 30 min


# ── Clase principal ───────────────────────────────────────────────────────────


class TrapperNavigator:
    """
    Automatiza la navegación en la interfaz web de Trapper usando Playwright.

    Parameters
    ----------
    base_url : str
        URL base de la instancia de Trapper,
        p. ej. ``"https://wildintel-trap.uhu.es"``.
    username : str
        Nombre de usuario para autenticarse.
    password : str
        Contraseña asociada al usuario.
    headless : bool, optional
        Si es ``True`` (valor por defecto) el navegador se ejecuta en segundo
        plano sin ventana visible.  Pasa ``False`` para ver la navegación en
        pantalla (útil para depuración).
    timeout_ms : int, optional
        Tiempo máximo de espera en milisegundos para cada operación del
        navegador.  Por defecto 30 minutos.
    """

    # ── Rutas de la interfaz web de Trapper ───────────────────────────────────
    _LOGIN_PATH            = "/account/login/"
    _IMPORT_PATH           = "/media_classification/classification/import/"
    _DEPLOYMENT_IMPORT_PATH = "/geomap/deployment/import/"

    def __init__(
        self,
        base_url: str,
        username: str,
        password: str,
        headless: bool = True,
        timeout_ms: int = _DEFAULT_TIMEOUT_MS,
    ) -> None:
        self.base_url   = base_url.rstrip("/")
        self.username   = username
        self.password   = password
        self.headless   = headless
        self.timeout_ms = timeout_ms
        self.logger     = logging.getLogger(__name__)

    # ── Método público: subir clasificaciones de expertos ────────────────────

    def upload_expert_classifications(
        self,
        csv_files: List[Path],
        project_id: int,
        progress_callback: Optional[
            Callable[
                [str, str, int, Optional[int], Optional[str], bool,
                 Optional[str], Optional[str], Optional[str]],
                None,
            ]
        ] = None,
        delay_between_uploads: float = 0.0,
    ) -> Report:
        """
        Sube uno o varios CSV con clasificaciones humanas a Trapper.

        Navega automáticamente al formulario de importación de Trapper,
        selecciona el proyecto indicado, adjunta el CSV y configura las
        casillas de verificación del formulario:

        * ✔ **Import expert classifications**
        * ✘ Import AI classifications
        * ✘ Approve
        * ✘ Import bboxes

        Parameters
        ----------
        csv_files : list[Path]
            Lista de rutas a los ficheros CSV a importar.  Se suben
            secuencialmente en el mismo orden.
        project_id : int
            Identificador (PK) del proyecto de clasificación de Trapper
            en el que se importarán los resultados.
        delay_between_uploads : float, optional
            Segundos de espera entre subidas consecutivas. Por defecto 0 (sin espera).
        progress_callback : callable, optional
            Función de progreso con la firma::

                callback(task_name, state, advance, total, description,
                         set_total, item_name, item_status, item_description)

            Sigue el mismo contrato que en ``TrapperZooniverseConnector``.

        Returns
        -------
        Report
            Informe con los resultados de la operación: éxitos y errores
            por cada fichero procesado.

        Raises
        ------
        ImportError
            Si ``playwright`` no está instalado en el entorno.
        RuntimeError
            Si el login falla (credenciales incorrectas).
        """
        # ── Validaciones previas ──────────────────────────────────────────────
        if not csv_files:
            raise ValueError("csv_files no puede estar vacío.")

        # Comprobamos que playwright esté disponible antes de empezar
        try:
            from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout
        except ImportError:
            sys.exit(
                "\nERROR: playwright no está instalado.\n"
                "  Instálalo con:  pip install playwright\n"
                "  Y luego:        playwright install chromium\n"
            )

        # Comprobamos que Chromium esté instalado; si no, lo instalamos
        self._ensure_chromium()

        report = Report(
            f"Upload expert classifications to project {project_id} at {self.base_url}",
            type="UploadExpertClassificationsReport",
        )

        login_url  = f"{self.base_url}{self._LOGIN_PATH}"
        import_url = f"{self.base_url}{self._IMPORT_PATH}"
        total      = len(csv_files)

        self._notify(
            progress_callback,
            task_name="upload_expert_classifications",
            state="start",
            total=total,
            set_total=True,
            description=f"Subiendo {total} fichero(s) al proyecto {project_id}...",
        )

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=self.headless)
            context = browser.new_context()
            page    = context.new_page()
            page.set_default_timeout(self.timeout_ms)

            # ── 1. Login ──────────────────────────────────────────────────────
            self.logger.debug(f"Abriendo {login_url}...")
            self._notify(
                progress_callback,
                task_name="upload_expert_classifications",
                state="running",
                advance=0,
                item_name="login",
                item_status="start",
                item_description=f"Iniciando sesión como {self.username}...",
            )

            try:
                page.goto(login_url, timeout=self.timeout_ms)
                page.locator("#id_login").wait_for(state="visible", timeout=self.timeout_ms)
                page.locator("#id_login").fill(self.username)
                page.locator("#id_password").fill(self.password)
                page.locator('button[type="submit"]').click()
                page.wait_for_load_state("load", timeout=self.timeout_ms)

                if self._LOGIN_PATH in page.url:
                    browser.close()
                    raise RuntimeError(
                        f"Login fallido para {self.username}@{self.base_url}. "
                        "Comprueba el usuario y la contraseña."
                    )
            except Exception as exc:
                browser.close()
                self._notify(
                    progress_callback,
                    task_name="upload_expert_classifications",
                    state="running",
                    advance=0,
                    item_name="login",
                    item_status="fail",
                    item_description=str(exc),
                )
                report.add_error("login", "login", str(exc))
                report.finish()
                return report

            self.logger.debug(f"✓ Sesión iniciada como {self.username}")
            self._notify(
                progress_callback,
                task_name="upload_expert_classifications",
                state="running",
                advance=0,
                item_name="login",
                item_status="end",
                item_description=f"Sesión iniciada como {self.username}",
            )

            # ── 2. Subir cada fichero ─────────────────────────────────────────
            for idx, csv_path in enumerate(csv_files, start=1):
                csv_path = Path(csv_path)
                label    = csv_path.name

                self.logger.debug(f"[{idx}/{total}] Subiendo {label}...")
                self._notify(
                    progress_callback,
                    task_name="upload_expert_classifications",
                    state="running",
                    advance=0,
                    item_name=label,
                    item_status="start",
                    item_description=f"Navegando al formulario de importación...",
                )

                try:
                    page.goto(import_url, wait_until="load", timeout=self.timeout_ms)
                    page.locator("#id_project").wait_for(
                        state="visible", timeout=self.timeout_ms
                    )

                    # Seleccionar proyecto por PK
                    try:
                        page.select_option(
                            "#id_project",
                            value=str(project_id),
                            timeout=self.timeout_ms,
                        )
                    except PWTimeout:
                        raise ValueError(
                            f"No se encontró el proyecto con id={project_id} "
                            "en el selector del formulario."
                        )

                    # Adjuntar fichero CSV
                    page.locator("#id_observations_csv").set_input_files(
                        str(csv_path.resolve())
                    )

                    # Configurar casillas de verificación
                    self._set_checkbox(page, "#id_import_expert_classifications", True)
                    self._set_checkbox(page, "#id_import_ai_classifications",     False)
                    self._set_checkbox(page, "#id_approve",                       False)
                    self._set_checkbox(page, "#id_import_bboxes",                 False)

                    # Enviar formulario
                    page.locator('button[type="submit"]').click()
                    page.wait_for_load_state("load", timeout=self.timeout_ms)

                    # Comprobar si el servidor devolvió un error
                    if self._IMPORT_PATH in page.url:
                        msg = (
                            f"El servidor devolvió un error al procesar {label}. "
                            "Comprueba el formulario manualmente."
                        )
                        self.logger.warning(f"  ⚠  {msg}")
                        self._notify(
                            progress_callback,
                            task_name="upload_expert_classifications",
                            state="running",
                            advance=1,
                            item_name=label,
                            item_status="fail",
                            item_description=msg,
                        )
                        report.add_error(label, "upload", msg)
                    else:
                        self.logger.debug(f"  ✓ {label}  →  {page.url}")
                        self._notify(
                            progress_callback,
                            task_name="upload_expert_classifications",
                            state="running",
                            advance=1,
                            item_name=label,
                            item_status="end",
                            item_description=f"Importado correctamente → {page.url}",
                        )
                        report.add_success(label, "upload", f"redirect → {page.url}")

                        if delay_between_uploads > 0 and idx < total:
                            self.logger.debug(f"  Esperando {delay_between_uploads}s antes de la siguiente subida...")
                            page.wait_for_timeout(delay_between_uploads * 1000)

                except Exception as exc:
                    self.logger.error(f"  ERROR procesando {label}: {exc}")
                    self._notify(
                        progress_callback,
                        task_name="upload_expert_classifications",
                        state="running",
                        advance=1,
                        item_name=label,
                        item_status="fail",
                        item_description=str(exc),
                    )
                    report.add_error(label, "upload", str(exc))

            browser.close()

        self._notify(
            progress_callback,
            task_name="upload_expert_classifications",
            state="end",
            description=f"Completado: {total} fichero(s) procesado(s).",
        )
        report.finish()
        return report

    # ── Método público: importar deployments ─────────────────────────────────

    def upload_deployments(
        self,
        csv_file: Path,
        research_project_id: int,
        timezone: str,
        classification_project_id: Optional[int] = None,
        update: bool = False,
        create_locations: bool = False,
        ignore_dst: bool = False,
        progress_callback: Optional[
            Callable[
                [str, str, int, Optional[int], Optional[str], bool,
                 Optional[str], Optional[str], Optional[str]],
                None,
            ]
        ] = None,
    ) -> Report:
        """
        Importa un CSV con deployments en Trapper.

        Navega automáticamente al formulario de importación de deployments
        en ``/geomap/deployment/import/``, selecciona el proyecto de
        investigación, adjunta el CSV y configura las opciones del formulario.

        Parameters
        ----------
        csv_file : Path
            Ruta al fichero CSV con los deployments a importar.
            El CSV debe estar separado por comas.
        research_project_id : int
            Identificador (PK) del proyecto de investigación al que
            asociar los deployments.
        timezone : str
            Zona horaria para interpretar las marcas de tiempo del CSV,
            p. ej. ``"Europe/Madrid"`` o ``"UTC"``.
        classification_project_id : int, optional
            Identificador (PK) del proyecto de clasificación al que
            vincular los deployments.  Si se omite, el campo queda
            vacío (``---------``).
        update : bool, optional
            Si es ``True`` se activa la casilla *Update deployments*;
            el CSV debe incluir una columna ``_id`` con las PK de los
            deployments a actualizar.  Por defecto ``False``.
        create_locations : bool, optional
            Si es ``True`` se activa la casilla *Create locations*;
            el CSV debe incluir las columnas ``locationID``, ``longitude``
            y ``latitude``.  Por defecto ``False``.
        ignore_dst : bool, optional
            Si es ``True`` se activa la casilla *Locations ignore DST*.
            Por defecto ``False``.
        progress_callback : callable, optional
            Función de progreso con la misma firma que en
            ``upload_expert_classifications``.

        Returns
        -------
        Report
            Informe con el resultado de la operación.

        Raises
        ------
        ImportError
            Si ``playwright`` no está instalado en el entorno.
        RuntimeError
            Si el login falla (credenciales incorrectas).
        ValueError
            Si ``csv_file`` no existe o alguno de los IDs no se
            encuentra en el selector del formulario.
        """
        csv_file = Path(csv_file)
        if not csv_file.exists():
            raise ValueError(f"El fichero CSV no existe: {csv_file}")

        try:
            from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout
        except ImportError:
            sys.exit(
                "\nERROR: playwright no está instalado.\n"
                "  Instálalo con:  pip install playwright\n"
                "  Y luego:        playwright install chromium\n"
            )

        self._ensure_chromium()

        report = Report(
            f"Upload deployments from {csv_file.name} to research project "
            f"{research_project_id} at {self.base_url}",
            type="UploadDeploymentsReport",
        )

        login_url  = f"{self.base_url}{self._LOGIN_PATH}"
        import_url = f"{self.base_url}{self._DEPLOYMENT_IMPORT_PATH}"
        label      = csv_file.name

        self._notify(
            progress_callback,
            task_name="upload_deployments",
            state="start",
            total=1,
            set_total=True,
            description=f"Importando deployments desde {label}...",
        )

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=self.headless)
            context = browser.new_context()
            page    = context.new_page()
            page.set_default_timeout(self.timeout_ms)

            # ── 1. Login ──────────────────────────────────────────────────────
            self._notify(
                progress_callback,
                task_name="upload_deployments",
                state="running",
                advance=0,
                item_name="login",
                item_status="start",
                item_description=f"Iniciando sesión como {self.username}...",
            )

            try:
                page.goto(login_url, timeout=self.timeout_ms)
                page.locator("#id_login").wait_for(state="visible", timeout=self.timeout_ms)
                page.locator("#id_login").fill(self.username)
                page.locator("#id_password").fill(self.password)
                page.locator('button[type="submit"]').click()
                page.wait_for_load_state("load", timeout=self.timeout_ms)

                if self._LOGIN_PATH in page.url:
                    browser.close()
                    raise RuntimeError(
                        f"Login fallido para {self.username}@{self.base_url}. "
                        "Comprueba el usuario y la contraseña."
                    )
            except Exception as exc:
                browser.close()
                self._notify(
                    progress_callback,
                    task_name="upload_deployments",
                    state="running",
                    advance=0,
                    item_name="login",
                    item_status="fail",
                    item_description=str(exc),
                )
                report.add_error("login", "login", str(exc))
                report.finish()
                return report

            self.logger.debug(f"✓ Sesión iniciada como {self.username}")
            self._notify(
                progress_callback,
                task_name="upload_deployments",
                state="running",
                advance=0,
                item_name="login",
                item_status="end",
                item_description=f"Sesión iniciada como {self.username}",
            )

            # ── 2. Rellenar y enviar el formulario ────────────────────────────
            self._notify(
                progress_callback,
                task_name="upload_deployments",
                state="running",
                advance=0,
                item_name=label,
                item_status="start",
                item_description="Navegando al formulario de importación de deployments...",
            )

            try:
                page.goto(import_url, wait_until="load", timeout=self.timeout_ms)

                # Seleccionar proyecto de investigación
                rp_selector = "#id_research_project"
                page.locator(rp_selector).wait_for(state="visible", timeout=self.timeout_ms)
                try:
                    page.select_option(
                        rp_selector,
                        value=str(research_project_id),
                        timeout=self.timeout_ms,
                    )
                except PWTimeout:
                    raise ValueError(
                        f"No se encontró el research project con id={research_project_id} "
                        "en el selector del formulario."
                    )

                # Seleccionar proyecto de clasificación (opcional)
                if classification_project_id is not None:
                    try:
                        page.select_option(
                            "#id_classification_project",
                            value=str(classification_project_id),
                            timeout=self.timeout_ms,
                        )
                    except PWTimeout:
                        raise ValueError(
                            f"No se encontró el classification project con "
                            f"id={classification_project_id} en el selector del formulario."
                        )

                # Adjuntar fichero CSV
                page.locator("#id_csv_file").set_input_files(str(csv_file.resolve()))

                # Seleccionar zona horaria
                try:
                    page.select_option(
                        "#id_timezone",
                        value=timezone,
                        timeout=self.timeout_ms,
                    )
                except PWTimeout:
                    raise ValueError(
                        f"La zona horaria '{timezone}' no existe en el selector del formulario."
                    )

                # Configurar casillas de verificación
                self._set_checkbox(page, "#id_update",           update)
                self._set_checkbox(page, "#id_create_locations", create_locations)
                self._set_checkbox(page, "#id_ignore_DST",       ignore_dst)

                # Enviar formulario
                page.locator('button[type="submit"]').click()
                page.wait_for_load_state("load", timeout=self.timeout_ms)

                # Comprobar si el servidor devolvió un error (permanece en la misma URL)
                if self._DEPLOYMENT_IMPORT_PATH in page.url:
                    msg = (
                        f"El servidor devolvió un error al procesar {label}. "
                        "Comprueba el formulario manualmente."
                    )
                    self.logger.warning(f"  ⚠  {msg}")
                    self._notify(
                        progress_callback,
                        task_name="upload_deployments",
                        state="running",
                        advance=1,
                        item_name=label,
                        item_status="fail",
                        item_description=msg,
                    )
                    report.add_error(label, "upload", msg)
                else:
                    self.logger.debug(f"  ✓ {label}  →  {page.url}")
                    self._notify(
                        progress_callback,
                        task_name="upload_deployments",
                        state="running",
                        advance=1,
                        item_name=label,
                        item_status="end",
                        item_description=f"Importado correctamente → {page.url}",
                    )
                    report.add_success(label, "upload", f"redirect → {page.url}")

            except Exception as exc:
                self.logger.error(f"  ERROR procesando {label}: {exc}")
                self._notify(
                    progress_callback,
                    task_name="upload_deployments",
                    state="running",
                    advance=1,
                    item_name=label,
                    item_status="fail",
                    item_description=str(exc),
                )
                report.add_error(label, "upload", str(exc))

            browser.close()

        self._notify(
            progress_callback,
            task_name="upload_deployments",
            state="end",
            description=f"Completado: {label} procesado.",
        )
        report.finish()
        return report

    # ── Helpers privados ──────────────────────────────────────────────────────

    def _ensure_chromium(self) -> None:
        """
        Comprueba si el navegador Chromium de Playwright está instalado.

        Cuando se distribuye el programa como ejecutable (PyInstaller) o en un
        entorno limpio, los binarios del navegador no se incluyen y hay que
        instalarlos aparte.  Este método los detecta y, si no están, ejecuta
        ``playwright install chromium`` automáticamente.

        La detección usa la API interna de Playwright para localizar el
        ejecutable esperado; si no existe en disco, se lanza la instalación.
        """
        try:
            from playwright.sync_api import sync_playwright
        except ImportError:
            return  # ya controlado antes de llamar a este método

        chromium_found = False
        try:
            with sync_playwright() as p:
                # executable_path devuelve la ruta donde Playwright espera
                # encontrar el binario; si el fichero existe, ya está instalado.
                exec_path = p.chromium.executable_path
                chromium_found = Path(exec_path).exists()
        except Exception:
            # Cualquier error aquí (p. ej. el binario no existe y playwright
            # lanza una excepción) se interpreta como «no instalado».
            chromium_found = False

        if chromium_found:
            self.logger.debug("✓ Chromium de Playwright ya está instalado.")
            return

        self.logger.info(
            "Chromium no encontrado. Instalando con 'playwright install chromium'..."
        )
        print(
            "⏳ Chromium no está instalado. Instalando automáticamente "
            "(puede tardar unos minutos la primera vez)..."
        )

        try:
            result = subprocess.run(
                [sys.executable, "-m", "playwright", "install", "chromium"],
                check=True,
                capture_output=True,
                text=True,
            )
            self.logger.debug(result.stdout)
            print("✓ Chromium instalado correctamente.")
        except subprocess.CalledProcessError as exc:
            raise RuntimeError(
                "No se pudo instalar Chromium automáticamente.\n"
                f"  stdout: {exc.stdout}\n"
                f"  stderr: {exc.stderr}\n"
                "  Instálalo manualmente con:\n"
                "    playwright install chromium"
            ) from exc

    @staticmethod
    def _set_checkbox(page, selector: str, checked: bool) -> None:
        """Asegura que una casilla de verificación está en el estado deseado."""
        cb = page.locator(selector)
        if cb.count() == 0:
            return
        if checked and not cb.is_checked():
            cb.check()
        elif not checked and cb.is_checked():
            cb.uncheck()

    def _notify(
        self,
        progress_callback: Optional[
            Callable[
                [str, str, int, Optional[int], Optional[str], bool,
                 Optional[str], Optional[str], Optional[str]],
                None,
            ]
        ],
        task_name: str,
        state: str,
        advance: int = 0,
        total: Optional[int] = None,
        description: Optional[str] = None,
        set_total: bool = False,
        item_name: Optional[str] = None,
        item_status: Optional[Literal["start", "end", "fail"]] = None,
        item_description: Optional[str] = None,
    ) -> None:
        """Emite un evento de progreso y registra un mensaje de log conciso."""
        log_parts = [f"task={task_name}", f"state={state}"]
        if description:
            log_parts.append(description)
        if item_name:
            log_parts.append(f"item={item_name}")
        if item_status:
            log_parts.append(f"item_status={item_status}")
        if item_description:
            log_parts.append(f"item_description={item_description}")
        if total is not None:
            log_parts.append(f"total={total}")
        if advance:
            log_parts.append(f"advance={advance}")
        if set_total:
            log_parts.append("set_total")
        self.logger.debug(" | ".join(log_parts))

        if progress_callback:
            progress_callback(
                task_name,
                state,
                advance,
                total,
                description,
                set_total,
                item_name,
                item_status,
                item_description,
            )
