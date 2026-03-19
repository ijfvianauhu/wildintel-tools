import os
import tempfile
import time
import logging
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path
from queue import Queue
from typing import List, Tuple, Optional, Union, Dict, Callable, Any
import json
import requests
from panoptes_client import SubjectSet, Subject, Project, Workflow, ProjectRole, User, Classification, Panoptes
from panoptes_client.panoptes import PanoptesAPIException

from wildintel_tools.zooniverse.Schemas import SubjectSetResults
from pathlib import PurePath
#from wildintel_tools.i18n import setup_i18n, _
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type, RetryError
import panoptes_client as pc
from wildintel_tools.reports import Report

class UploadingException(Exception):
    """Raised when a media download fails after retries."""

class ZooniverseClientComponent:
    """Clase base para componentes del cliente de Zooniverse (Workflows, Subjects, etc.)."""

    def __init__(self, client=None):
        self.client = client

    def _ensure_connection(self):
        """Garantiza que el cliente esté conectado antes de ejecutar operaciones."""
        if self.client and not getattr(self.client, "_connected", False):
            self.client.logger.debug("🔄 Reconnecting automatically before operation...")
            self.client.connect()
#
# Workflow
#
#

class WorkflowsComponent(ZooniverseClientComponent):

    def get_all(
        self,
        query: Optional[Dict[str, Any]] = None,
        **filters: Any,
    ) -> List[SubjectSet]:
        """
        Retrieve subject sets associated with the current Zooniverse project, with optional filters.

        Parameters
        ----------
        query : dict[str, Any], optional
            Dictionary of filters to pass to ``SubjectSet.where``.
        **filters : Any
            Additional filter keyword arguments. These override duplicated keys in ``query``.

        Returns
        -------
        List[Workflow]
            List of matching subject sets.
        """
        self.client._ensure_connection()
        project = Project.find(self.client.project_id)

        where_filters: Dict[str, Any] = {"project_id": project.id}
        if query:
            where_filters.update(query)
        if filters:
            where_filters.update(filters)

        subject_sets = Workflow.where(**where_filters)
        return list(subject_sets)

    def get_by_id(self, id:int) -> Workflow:
        self.client._ensure_connection()
        return Workflow.find(id)

    def get_by_subjectset(self, subjectset_id:int) -> List[Workflow]:
        self.client._ensure_connection()
        subject_set = SubjectSet.find(subjectset_id)
        print(subject_set.__dict__)
        workflow_ids = subject_set.raw["links"].get("workflows", [])
        workflows = [Workflow.find(wid) for wid in workflow_ids]

        return list(workflows)
#
# SubjectSetsComponent
#

class SubjectSetsComponent(ZooniverseClientComponent):

    def __init__(self, client: "ZooniverseClient"):
        self.client = client
        self.logger = client.logger

    def get_all(
        self,
        query: Optional[Dict[str, Any]] = None,
        **filters: Any,
    ) -> List[SubjectSet]:
        """
        Retrieve subject sets associated with the current Zooniverse project, with optional filters.

        Parameters
        ----------
        query : dict[str, Any], optional
            Dictionary of filters to pass to ``SubjectSet.where``.
        **filters : Any
            Additional filter keyword arguments. These override duplicated keys in ``query``.

        Returns
        -------
        List[SubjectSet]
            List of matching subject sets.
        """
        self.client._ensure_connection()
        project = Project.find(self.client.project_id)

        where_filters: Dict[str, Any] = {"project_id": project.id}
        if query:
            where_filters.update(query)
        if filters:
            where_filters.update(filters)

        subject_sets = SubjectSet.where(**where_filters)
        return list(subject_sets)

    def get_by_id(self, subject_set_id: int) -> SubjectSet:
        """
        Recupera un SubjectSet por su ID.

        Parameters
        ----------
        subject_set_id : int
            ID del SubjectSet a recuperar.

        Returns
        -------
        SubjectSet
            El SubjectSet correspondiente al ID proporcionado.

        Raises
        ------
        ValueError
            Si no se encuentra un SubjectSet con el ID dado.
        """
        self.client._ensure_connection()
        subject_set = SubjectSet.find(subject_set_id)
        if not subject_set:
            raise ValueError(f"SubjectSet with ID {subject_set_id} not found.")
        return subject_set

    def get_subject_sets_from_workflow(
        self,
        workflow_id: int,
        query: Optional[Dict[str, Any]] = None,
        **filters: Any,
    ) -> List[SubjectSet]:
        """Retrieve subject sets linked to a workflow, with optional extra filters.

        Args:
            workflow_id: ID of the workflow whose subject sets will be retrieved.
            query: Optional dictionary of filters to pass to ``SubjectSet.where``.
            **filters: Additional keyword filters passed to ``SubjectSet.where``.
                These override duplicated keys in ``query``.

        Returns:
            List[SubjectSet]: Subject sets associated with the workflow and matching filters.

        Raises:
            ValueError: If ``workflow_id`` is missing/invalid.
        """
        self.client._ensure_connection()

        if workflow_id is None:
            raise ValueError("workflow_id is required")

        project = Project.find(self.client.project_id)

        where_filters: Dict[str, Any] = {"project_id": project.id}
        if query:
            where_filters.update(query)
        if filters:
            where_filters.update(filters)

        subject_sets = SubjectSet.where(**where_filters)

        workflow_id_str = str(workflow_id)
        res: List[SubjectSet] = []
        for ss in subject_sets:
            links = ss.raw.get("links", {}) if getattr(ss, "raw", None) else {}
            wf_links = links.get("workflows", []) or []
            wf_links_str = [str(wid) for wid in wf_links]
            if workflow_id_str in wf_links_str:
                res.append(ss)

        return res

    def exists(self, name: str) -> bool:
        """
        Comprueba si existe un SubjectSet con el nombre dado en el proyecto.

        Parameters
        ----------
        name : str
            Nombre del SubjectSet a buscar.

        Returns
        -------
        bool
            True si existe, False en caso contrario.
        """
        self.client._ensure_connection()
        subject_sets = self.get_all()
        return any(ss.display_name == name for ss in subject_sets)

    def create(self, name:str):
        """
        Crea un SubjectSet por nombre. Si existe, no lo crea.

        Args:
            name (str): Nombre del SubjectSet.
        Returns:
            pc.SubjectSet: El SubjectSet existente o recién creado.
        """

        self.client._ensure_connection()
        existing_sets = [ss for ss in self.get_all() if ss.display_name == name]

        if existing_sets:
            return existing_sets[0]

        subject_set = pc.SubjectSet()
        subject_set.links.project = self.client.project_id
        subject_set.display_name = name
        subject_set.save()

        return subject_set

    def delete(self, subject_set_id: int) -> bool:
        """
        Elimina un SubjectSet por su ID.

        Args:
            subject_set_id (int): ID del SubjectSet a eliminar.

        Returns:
            bool: True si se eliminó correctamente, False si no se pudo eliminar.

        Raises:
            ValueError: Si no existe un SubjectSet con el ID dado.
        """
        self.client._ensure_connection()

        try:
            subject_set = SubjectSet.find(subject_set_id)
            if not subject_set:
                raise ValueError(f"SubjectSet con ID {subject_set_id} no encontrado.")

            subject_set.delete()
            self.client.logger.debug(f"SubjectSet {subject_set_id} eliminado correctamente.")
            return True

        except Exception as e:
            self.client.logger.error(f"Error eliminando SubjectSet {subject_set_id}: {e}")
            return False

    def with_results(self) -> List:
        """
        Devuelve los subjetsts que tienen resultados.

        Parameters
        ----------
        name : str
            Nombre del SubjectSet a buscar.

        Returns
        -------
        bool
            True si existe, False en caso contrario.
        """
        self.client._ensure_connection()
        subject_sets = self.get_all()
        selected = []
        for ss in subject_sets:
            # Check if classifications export exists
            try:
                ss.get_export("classifications", wait=False)  # don't wait for generation
                selected.append(ss)
            except Exception as e:
                pass

        return selected

    def with_exports(self) -> List:
        return self.with_results()

    def download(self, subject_set_id: int, output_folder: Path,
                 max_workers: int = 4, overwrite: bool = False,callback: callable = None) -> Report:

        self.client._ensure_connection()
        self.client.logger.debug(f"Starting SubjectSet  {subject_set_id} download.")
        print(max_workers)
        report: Report = Report(
            f"Bulk Download Report for subjectset {subject_set_id}, project {self.client.project_id}"
        )

        self.client.logger.debug(f"Creating  output folder...")
        output_folder.mkdir(parents=True, exist_ok=True)
        subject_set = SubjectSet.find(subject_set_id)
        if not subject_set:
            self.client.logger.warning(f"SubjectSet with ID {subject_set_id} not found.")
            raise ValueError(f"SubjectSet with ID {subject_set_id} not found.")
        self.client.logger.debug(f"Obtained info for  SubjectSet  {subject_set_id}")

        if not subject_set.subjects:
            self.client.logger.warning(f"SubjectSet {subject_set_id} no contiene subjects.")
            report.finish()
            return report

        def _notify(event: str, sid: int, name, total=None, step=None):
            if callback:
                try:
                    callback(event, sid, name, total, step)
                except Exception:
                    self.client.logger.debug("Callback raised an exception", exc_info=True)

        def download_one(subj):
            sid = getattr(subj, "id", None)
            name = getattr(subj, "display_name", getattr(subj, "name", f"subject_{sid}"))
            self.client.logger.debug(f"Sending start notification for subjet {subj}")
            _notify("start", sid, f"Downloading subject {name}", None)
            try:
                s_cmp = SubjectsComponent(self.client)

                @retry(
                    stop=stop_after_attempt(3),
                    wait=wait_exponential(multiplier=5, min=5, max=60),
                    reraise=True,
                )
                def _download_with_retry():
                    return s_cmp.download(sid, save_path=str(output_folder), overwrite=overwrite)

                path = _download_with_retry()
                report.add_success(sid, "download", str(path))
                self.client.logger.debug(f"Sending end notification for subjet  {subj}")
                _notify("end", sid, f"Download completed successfully in {str(path)}")
                return sid
            except Exception as exc:
                report.add_error(sid, "download", str(exc))
                self.client.logger.debug(f"Sending fail notification for subjet {subj}: {str(exc)}")
                _notify("fail", sid, f"Download completed with errors {str(exc)}")
                self.client.logger.warning(f"Error downloading subject {sid}: {exc}")
                return None

        self.client.logger.debug(f"Preparing pool for {max_workers} workers and {subject_set.subjects} subjects")

        with ThreadPoolExecutor(max_workers=max_workers) as pool:
            for _ in pool.map(download_one, subject_set.subjects):
               pass

        return report
#
# SubjectsComponent
#

class SubjectsComponent(ZooniverseClientComponent):

    def get_by_id(self, id) -> List:
        self.client._ensure_connection()
        return Subject.find(id)

    def get_by_subjectset(self, subject_set_id) -> List:
        """
        Retrieve all subjects associated with a given SubjectSet.

        Parameters
        ----------
        subject_set_id : int
            The ID of the SubjectSet to fetch subjects from.

        Returns
        -------
        List
            A list of Subject objects from the SubjectSet.
        """
        # Connect to Zooniverse

        #Panoptes.connect(username=username, password=password)

        # Find the SubjectSet
        subject_set = SubjectSet.find(subject_set_id)

        # Return the subjects as a list
        return list(subject_set.subjects)

    def subject_exists(
        self,
        subject_set: Optional[Union[int, SubjectSet]],
        subject_identifier: Union[int, str, Subject],
    ) -> bool:
        """
        Check whether a subject already belongs to one or more SubjectSets.

        Parameters
        ----------
        subject_set : int | SubjectSet | None
            Target SubjectSet (instance or ID). If ``None``, every available set in the
            current project will be scanned.
        subject_identifier : int | str | Subject
            Identifier to match. Accepts numeric ID, name, metadata ``origin`` or an
            actual ``Subject`` instance.

        Returns
        -------
        bool
            ``True`` if a matching subject is found, otherwise ``False``.
        """
        self.client._ensure_connection()

        def _normalize(value: Optional[str]) -> Optional[str]:
            return str(value).strip().lower() if value is not None else None

        def _extract_name(subj: Subject) -> Optional[str]:
            name = getattr(subj, "display_name", None) or getattr(subj, "name", None)
            if not name:
                metadata = getattr(subj, "metadata", {}) or {}
                for key in ("Filename", "filename", "file_name", "name", "display_name"):
                    if metadata.get(key):
                        name = metadata[key]
                        break
            return str(name) if name else None

        def _extract_origin(subj: Subject) -> Optional[str]:
            metadata = getattr(subj, "metadata", {}) or {}
            origin_val = metadata.get("origin") or metadata.get("Origin")
            return str(origin_val) if origin_val else None

        candidate_id: Optional[int] = None
        candidate_name: Optional[str] = None
        candidate_origin: Optional[str] = None

        if isinstance(subject_identifier, Subject):
            candidate_id = getattr(subject_identifier, "id", None)
            candidate_name = _normalize(_extract_name(subject_identifier))
            candidate_origin = _normalize(_extract_origin(subject_identifier))
        elif isinstance(subject_identifier, int):
            candidate_id = subject_identifier
        elif isinstance(subject_identifier, str):
            stripped = subject_identifier.strip()
            if stripped.isdigit():
                candidate_id = int(stripped)
            candidate_name = _normalize(stripped)
            candidate_origin = candidate_name
        else:
            raise TypeError("subject_identifier must be Subject, int or str")

        def _iter_subject_sets() -> List[SubjectSet]:
            if subject_set is None:
                sets = self.client.subjectsets.get_all()
                if not sets:
                    self.client.logger.debug("No SubjectSets available to search for duplicates.")
                return sets
            if isinstance(subject_set, SubjectSet):
                return [subject_set]
            found = SubjectSet.find(subject_set)
            if not found:
                raise ValueError("SubjectSet not found for the provided identifier.")
            return [found]

        for ss in _iter_subject_sets():
            for subj in ss.subjects:
                subj_id = getattr(subj, "id", None)
                if candidate_id is not None and subj_id == candidate_id:
                    return True

                subj_name = _normalize(_extract_name(subj))
                subj_origin = _normalize(_extract_origin(subj))

                if candidate_name and subj_name and subj_name == candidate_name:
                    return True

                if candidate_origin and subj_origin and subj_origin == candidate_origin:
                    return True

        return False

    def create(self, path: str, subject_set : SubjectSet, metadata : Dict =None, attempts: int = 5
               , delay_seconds: int = 60, skip_if_exists: bool = False,
               exists_identifier: Optional[Union[int, str, Subject]] = None):
        """
        Upload a single subject to a Zooniverse SubjectSet with retries.

        :param path: Path to the file to upload.
        :param subject_set: Instance of SubjectSet to which the subject will be added.
        :param metadata: Optional metadata dictionary to attach to the subject.
        :param attempts: Number of retry attempts.
        :param delay_seconds: Delay in seconds between retries.
        :param skip_if_exists: When True, skip the upload if the subject is already present in the set.
        :param exists_identifier: Identifier (id or name) to use for existence checks. Defaults to file name.
        :return: The created Subject instance, or None if upload failed or skipped.
        """
        self.client._ensure_connection()

        identifier = exists_identifier
        if identifier is None:
            identifier = (metadata or {}).get("origin")
        if identifier is None:
            identifier = os.path.basename(path)

        if skip_if_exists and identifier is not None:
            try:
                if self.subject_exists(subject_set, identifier):
                    self.client.logger.debug("Skipping upload for %s because it already exists (%s)", path, identifier)
                    return None
            except ValueError:
                pass

        @retry(
            stop=stop_after_attempt(attempts),
            wait=wait_exponential(multiplier=delay_seconds, min=delay_seconds),
            reraise=False,
        )
        def _upload_subject():
            retry_state = _upload_subject.retry.statistics
            attempt_number = retry_state.get("attempt_number", 1)
            self.client.logger.debug(f"[Attempt {attempt_number}/{attempts}] Uploading... {path}")

            subject = Subject()
            subject.links.project = self.client.project_id
            if metadata:
                subject.metadata["Filename"] = metadata.get("image_name", os.path.basename(path))
                subject.external_id = metadata.get("external_id", "")
                for k, v in metadata.items():
                    subject.metadata[k] = v
            else:
                subject.metadata["Filename"] = os.path.basename(path)

            #if metadata:
            #    subject.external_id = metadata.get("external_id", "")
            #    for k, v in metadata.items():
            #        subject.metadata[k] = v

            subject.add_location(path)
            subject.save()
            subject_set.add(subject)
            self.client.logger.debug("✅ Successfully uploaded %s", path)
            return subject

        try:
            return _upload_subject()
        except RetryError as e:
            cause = e.last_attempt.exception() if e.last_attempt else e
            raise UploadingException(f"Failed Uploading {path}") from cause


    def download(self,  subject_id: Union[int, Subject], save_path: str = None, max_retries: int = 5, delay_seconds: int = 15, overwrite = False) -> str:
        """
        Download the image associated with a Zooniverse Subject by its ID.
        :param subject_id: ID of the Subject to download.
        :param save_path: Optional path to save the downloaded image. If a directory is provided,
                          the image will be saved with a filename based on subject ID and original filename.
                          If None, saves in current working directory with a generated filename.
        :param max_retries: Maximum number of retry attempts for downloading.
        :param delay_seconds: Base delay in seconds between retry attempts.
        :return: Path to the downloaded image file.
        """

        subject_obj = subject_id if isinstance(subject_id, Subject) else None
        sid = subject_obj.id if subject_obj else subject_id

        self.client._ensure_connection()
        self.client.logger.debug(f"Downloading subject: {subject_id}")

        if subject_obj is None:
            subject_obj = Subject.find(sid)
        if not subject_obj:
            raise ValueError(f"Subject con ID {sid} no encontrado.")

        locations = subject_obj.locations
        if not locations or not isinstance(locations, list):
            raise ValueError(f"Subject {subject_id} no tiene imágenes asociadas.")

        image_url = locations[0].get("image/png") or locations[0].get("image/jpg") or locations[0].get("image/jpeg")
        if not image_url:
            raise ValueError(f"Subject {subject_id} no tiene URL válida para la imagen.")

        metadata = subject_obj.metadata or {}
        name_candidates = ["Filename", "filename", "file_name", "name", "display_name"]
        original_filename = None
        for k in name_candidates:
            if k in metadata:
                original_filename = str(metadata[k])
                break

        if not original_filename:
            original_filename = os.path.basename(image_url)
        else:
            original_filename = str(PurePath(original_filename).name)

        self.client.logger.debug(f"Original filename: {original_filename}")

        # Resolver ruta destino
        if save_path is None:
            filename = f"{subject_id}_{original_filename}"
            target_path = Path(os.getcwd()) / filename
        else:
            target = Path(save_path)
            if target.is_dir():
                filename = f"{subject_id}_{original_filename}"
                target_path = target / filename
            else:
                target_path = target

        target_path.parent.mkdir(parents=True, exist_ok=True)

        if target_path.exists() and not overwrite:
            self.client.logger.debug(f"Skipping download for subject {subject_id}: file already exists.")
            return str(target_path)

        @retry(
            stop=stop_after_attempt(max_retries),
            wait=wait_exponential(multiplier=delay_seconds, min=delay_seconds, max=delay_seconds * 16),
            retry=retry_if_exception_type(requests.RequestException),
            reraise=True,
        )
        def _fetch(url: str, timeout: int = 10) -> requests.Response:
            resp = requests.get(url, stream=True, timeout=timeout)
            resp.raise_for_status()
            return resp

        try:
            resp = _fetch(image_url, timeout=10)

            # escribir en fichero temporal dentro del mismo directorio y mover atómicamente
            with tempfile.NamedTemporaryFile(delete=False, dir=str(target_path.parent)) as tmpf:
                tmp_name = tmpf.name
                for chunk in resp.iter_content(8192):
                    if chunk:
                        tmpf.write(chunk)

            os.replace(tmp_name, str(target_path))
            return str(target_path)

        except Exception as err:
            # tenacity ya re-lanzará la última excepción si agota intentos
            raise Exception(f"No se pudo descargar la imagen tras {max_retries} intentos: {err}")

# AnnotationsComponent
#


class AnnotationsComponent(ZooniverseClientComponent):

    @staticmethod
    def calculate_annotations_summary(data):
        from collections import Counter

        for workflow_key, subjects in data.items():
            for sid, classifications in subjects.items():
                all_choices = []

                # Recorrer cada clasificación
                for cl in classifications:
                    for ann in cl.get("annotations", []):
                        for val in ann.get("value", []):
                            # 'val' puede ser un dict con 'choice' si es un task tipo multiple choice
                            if isinstance(val, dict) and "choice" in val:
                                all_choices.append(val["choice"])
                            elif isinstance(val, str):
                                all_choices.append(val)

                # Contar apariciones
                choice_counts = Counter(all_choices)
                if choice_counts:
                    # Elección mayoritaria
                    majority_choice = choice_counts.most_common(1)[0][0]
                else:
                    majority_choice = None

                # Guardar resumen dentro de cada subject
                summary = {
                    "all_choices": dict(choice_counts),
                    "majority_choice": majority_choice
                }

                # Si quieres, puedes añadirlo al diccionario de cada subject
                # Si las clasificaciones están en lista:
                subjects[sid + "_summary"] = summary

    @staticmethod
    def _safe_load_json(value: str, default=None):
        if default is None:
            default = []
        if not value:
            return default
        try:
            return json.loads(value)
        except Exception:
            try:
                return json.loads(value.replace("'", '"'))
            except Exception:
                return default

    @staticmethod
    def _parse_subject_ids(value: str) -> List[int]:
        """Normaliza varios formatos comunes y devuelve lista de ints."""
        if value is None:
            return []
        v = value.strip()
        if v == "":
            return []
        # Caso típico "123" o "123,456"
        if "," in v:
            parts = [p.strip() for p in v.split(",") if p.strip()]
        # Caso forma JSON "['123','456']" o "[123,456]"
        elif v.startswith("[") and v.endswith("]"):
            try:
                parsed = json.loads(v.replace("'", '"'))  # reemplaza comillas simples
                parts = [str(x).strip() for x in parsed]
            except Exception:
                parts = [v.strip("[] \t\n'\"")]
        else:
            parts = [v]
        ids = []
        for p in parts:
            try:
                ids.append(int(p))
            except ValueError:
                # intenta extraer dígitos si hay ruido
                digits = ''.join(ch for ch in p if ch.isdigit())
                if digits:
                    ids.append(int(digits))
        return ids

    def get_export_dates_by_project(self) -> Dict[str, Optional[str]]:
        """
        Devuelve las fechas del último export disponible por tipo (classifications, subjects, etc.)
        para un proyecto de Zooniverse.

        Parameters
        ----------
        project_id : str
            ID del proyecto en Zooniverse.

        Returns
        -------
        Dict[str, Optional[str]]
            Diccionario con las fechas ISO de los últimos exports o '—' si no existen.
        """
        self.client._ensure_connection()

        project = Project.find(self.client.project_id)
        base_url = "https://panoptes.zooniverse.org/api/projects"
        print(project.get_export(export_type="classifications", wait=False))
        exit(1)

        panoptes = getattr(Panoptes, "_instance", None)
        session = getattr(panoptes, "session", None) if panoptes else None
        headers = session.headers if session else {}

        # Tipos posibles de export
        export_types = [
            "classifications",
            "subjects",
            "aggregations",
            "workflow_contents",
            "subject_sets",
        ]

        export_dates = {t: "—" for t in export_types}

        for export_type in export_types:
            url = f"{base_url}/{project.id}/exports/{export_type}"
            response = requests.get(url, headers=headers)
            print(url)
            print(response)
            if response.status_code == 200:
                data = response.json()
                print(data)
                # El export puede estar vacío si nunca se generó
                if "exports" in data and data["exports"]:
                    created_at = data["exports"][0].get("created_at")
                    if created_at:
                        try:
                            dt = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
                            export_dates[export_type] = dt.strftime("%Y-%m-%d %H:%M:%S")
                        except Exception as e:
                            print(e)
                            export_dates[export_type] = created_at

        return export_dates

    def get_last_exports_date_by_workflow(self) -> List[Tuple[int, str, Union[str, None]]]:
        """
        Devuelve la fecha del último export de clasificaciones por cada workflow del proyecto.

        Returns
        -------
        List[Tuple[int, str, str]]
            Lista de tuplas con (workflow_id, workflow_name, last_export_date o '-')
        """
        self.client._ensure_connection()

        project = Project.find(self.client.project_id)
        workflows = Workflow.where(project_id=project.id)
        results = []

        for wf in workflows:
            try:
                export = wf.get_export("classifications", wait=False)
                if export:
                    # La fecha puede venir en export.metadata['updated_at'] o 'created_at'
                    metadata = getattr(export, "raw", {}).get("metadata", {})
                    last_export_date = (
                        metadata.get("updated_at")
                        or metadata.get("created_at")
                        or "-"
                    )

                    # Normaliza formato
                    if last_export_date != "-":
                        try:
                            dt = datetime.fromisoformat(last_export_date.replace("Z", "+00:00"))
                            last_export_date = dt.strftime("%Y-%m-%d %H:%M:%S")
                        except Exception:
                            pass

                    results.append((wf.id, wf.display_name or "—", last_export_date))
                    self.client.logger.debug(
                        f"Workflow {wf.display_name} export last updated at {last_export_date}"
                    )
                else:
                    results.append((wf.id, wf.display_name or "—", "-"))
                    self.client.logger.debug(f"Workflow {wf.display_name} has no export.")
            except Exception as e:
                self.client.logger.debug(f"Workflow {wf.display_name} error getting export: {e}")
                results.append((wf.id, wf.display_name or "—", "-"))

        return results

    def get_all(self) ->List[Tuple[int, Optional[str]]]:
        self.client._ensure_connection()

        project = Project.find(self.client.project_id)
        subject_sets = SubjectSet.where(project_id=project.id)
        anotations = []

        for subject_set in subject_sets:
            try:
                export = subject_set.get_export("classifications", wait=False)  # don't wait for generation
                if export:
                    self.client.logger.debug(f"SubjectSet {subject_set.display_name} has classifications export.")
                    anotations.append((subject_set.id, export))
                else:
                    self.client.logger.debug(f"SubjectSet {subject_set.display_name} has no classifications export.")
            except Exception as e:
                self.client.logger.debug(f"SubjectSet {subject_set.display_name} has no classifications export.")

        return anotations

    def get_by_workflow(self, workflow_id: int, generate: bool=False, subject_filter: Optional[Callable[
        [Any], bool]] = None) -> List[dict]:
        self.client._ensure_connection()

        workflow = Workflow.find(workflow_id)

        try:
            # download last export
            classification_export = workflow.get_export("classifications", wait=True, wait_timeout=600)
        except PanoptesAPIException as e:
            classification_export = workflow.get_export(
                "classifications", generate=True, wait=True, wait_timeout=600
        )

        reader = classification_export.csv_dictreader()  # esto ya es un DictReader
        rows = list(reader)

        results = defaultdict(
            lambda: {"summary": {"total_subjects": 0, "retired_subjects": 0}, "data": defaultdict(list)}
        )

        for row in rows:

            wname = row.get("workflow_name") or "unknown_workflow"
            wid = row.get("workflow_id") or "unknown_id"
            wver = row.get("workflow_version") or ""
            workflow_key = f"{wid}:{wname}:{wver}"

            subject_ids = AnnotationsComponent._parse_subject_ids(row.get("subject_ids", ""))

            if not subject_ids:
                raise ValueError(f"No se pudieron parsear subject_ids en la fila: {row}")

            subject_data_raw = row.get("subject_data") or ""
            subject_data_parsed = {}

            if subject_data_raw:
                try:
                    subject_data_parsed = json.loads(subject_data_raw)
                except Exception:
                    # Algunos exports usan comillas simples o están mal escapados
                    try:
                        subject_data_parsed = json.loads(subject_data_raw.replace("'", '"'))
                    except Exception:
                        raise
                        #subject_data_parsed = {}
            else:
                logging.info("No subject_data found in row.", subject_ids)

            for sid in subject_ids:
                if subject_filter is not None and not subject_filter(sid):
                    logging.info(f"{sid} skipped", subject_ids)
                    continue

                results[workflow_key]["summary"]["total_subjects"] += 1

                subject_data = subject_data_parsed[str(sid)]
                retired =  subject_data["retired"]["retirement_reason"] if "retired" in subject_data else None

                if retired:
                    results[workflow_key]["summary"]["retired_subjects"] += 1

                subject_name = None
                for k in ("filename", "Filename", "file_name", "name", "display_name"):
                    if isinstance(subject_data, dict) and k in subject_data:
                        subject_name = subject_data[k]
                        break

                # Busco el media_id de la imagen original, me baso en el nombre de la imagen
                # si consulto los metadato se eterniza el proceso.
                # a=SubjectsComponent(self.client)
                # a.get_by_id(sid)
                media_id = self._get_media_id(subject_name)

                annotations = AnnotationsComponent._safe_load_json(row.get("annotations", "[]"), default=[])

                classification_info = {
                    "classification_id": row.get("classification_id"),
                    "user_name": row.get("user_name"),
                    "user_id": row.get("user_id"),
                    "subject_name": subject_name,
                    "retired": retired is not None,
                    "retirement_reason": retired,
                    "annotations": annotations,
                    "sid": sid
                }

                results[workflow_key]["data"][f"{sid}:{media_id}"].append(classification_info)

        return SubjectSetResults(workflows=results)

    def get_by_subjectset(self, workflow_id, subjectset_id: int, votes: bool=True) -> SubjectSetResults:
        """
        Fetches the results of all subjects in a SubjectSet as Pydantic models.

        :param subject_set_id: Zooniverse SubjectSet ID
        :param votes: If True, calculate the most , wait_timeout=600common annotation per subject
        :return: SubjectSetResults
        """
        self.client._ensure_connection()

        def fix_encoding(s):
            if isinstance(s, str):
                try:
                    return s.encode("latin1").decode("utf-8")
                except Exception:
                    return s
            elif isinstance(s, dict):
                return {fix_encoding(k): fix_encoding(v) for k, v in s.items()}
            elif isinstance(s, list):
                return [fix_encoding(x) for x in s]
            return s

        print(f"Fetching results for SubjectSet {subjectset_id} in Workflow {workflow_id}...")
        subject_set : SubjectSet = SubjectSet.find(subjectset_id)
        # Slow method: build set of subject IDs in the subject set
        # get subjects from subjec is not supported directly in panoptes-client
        subject_ids = {s.id for s in subject_set.subjects}

        def subject_filter(sid:int) -> bool:
            return sid in subject_ids

        return self.get_by_workflow(workflow_id, False, subject_filter)

        for subject in subject_set.subjects:
            print(subject.id, subject.metadata)

        #try:
            # download last export
        #    classification_export=subject_set.get_export('classifications', wait=True, wait_timeout=600)
        #except PanoptesAPIException as e:
        #    classification_export = subject_set.get_export("classifications", generate=True, wait=True, wait_timeout=600)

        #classification_export_csv=classification_export.csv_dictreader()

        #from collections import defaultdict

        # Fix utf-8 encoding issues
        #classifications = fix_encoding(list(classification_export_csv))

        #results = defaultdict(lambda: {"summary": {"total_subjects": 0, "retired_subjects": 0},
        #                               "data": defaultdict(list)})
        #for row in classifications:
        #    wname = row.get('workflow_name') or 'unknown_workflow'
        #    wid = row.get('workflow_id') or 'unknown_id'
        #    wver = row.get('workflow_version') or ''
        #    workflow_key = f"{wid}:{wname}:{wver}"

        #    subject_ids = AnnotationsComponent._parse_subject_ids(row.get('subject_ids', ""))

            # --- Nombre del subject (si existe en metadata o subject_data)

        #    subject_data_raw = row.get("subject_data") or ""
        #    subject_data_parsed = {}
        #    if subject_data_raw:
        #        try:
        #            subject_data_parsed = json.loads(subject_data_raw)
        #        except Exception:
        #            subject_data_parsed = json.loads(subject_data_raw.replace("'", '"'))

        #    for sid in subject_ids:
        #        results[workflow_key]["summary"]["total_subjects"] += 1

        #        sid_str = str(sid)
        #        subdata = subject_data_parsed.get(sid_str, {})

                # Intentar deducir un nombre legible
        #        subject_name = None
        #        for k in ("filename", "Filename", "file_name", "name", "display_name"):
        #            if isinstance(subdata, dict) and k in subdata:
        #                subject_name = subdata[k]
        #                break

                # get MEDIA_ID

        #        def get_media_id(s:str):
        #            import re

        #            s = "R0034/R0034-DONA_0066/R0034-DONA_0066__20250101_7436.JPG"

        #            # 1️⃣ Última parte del path
        #            filename = s.split('/')[-1]
                    #print(filename)  # R0034-DONA_0066__20250101_7436.JPG

                    # 2️⃣ Número después de __
        #            match = re.search(r'__(\d+)', filename)
        #            number = match.group(1) if match else None
        #            return number

        #        media_id = get_media_id(subject_name)

        #        if not subject_name:
                    # Si no encontramos un nombre, guardamos el subdata completo
        #            subject_name = json.dumps(subdata, ensure_ascii=False)

                # --- Retired y razón de retiro
        #        retired_info = subdata.get("retired", {})
        #        is_retired = bool(retired_info)  # True si hay un objeto de retired
        #        retirement_reason = retired_info.get("retirement_reason") if is_retired else None

        #        if is_retired:
        #            results[workflow_key]["summary"]["retired_subjects"] += 1

        #        annotations = AnnotationsComponent._safe_load_json(row.get('annotations', '[]'), default=[])

        #        classification_info = {
        #            "classification_id": row.get('classification_id'),
        #            "user_name": row.get('user_name'),
        #            "user_id": row.get('user_id'),
        #            "subject_name": subject_name,
        #            "retired": is_retired,
        #            "retirement_reason" : retirement_reason,
        #            "annotations": annotations
        #        }
        #
        #        results[workflow_key]["data"][f"{sid}:{media_id}"].append(classification_info)

        return SubjectSetResults(workflows=results)

    def _get_media_id(self,fullfilename:str):
        import re

        basename = os.path.basename(fullfilename)

        match = re.match(r"(\d+)(?=_x_)", basename)
        if match:
            first_number = match.group(1)
            return first_number
        else:
            None

    def _get_or_generate_export(self, obj, export_type: str = "classifications", wait: bool = True, timeout: int = 600):
        """
        Obtiene (o genera si no existe) un export para un objeto de Zooniverse
        (Project, Workflow o SubjectSet).

        Parameters
        ----------
        obj : Project | Workflow | SubjectSet
            Objeto de Zooniverse (ya obtenido con Panoptes).
        export_type : str
            Tipo de export ("classifications", "subjects", etc.)
        wait : bool
            Si True, espera hasta que el export esté disponible.
        timeout : int
            Tiempo máximo de espera en segundos.

        Returns
        -------
        dict
            {
                "id": int,
                "type": str,
                "object_type": str,
                "ready": bool,
                "url": str | None,
                "created_at": datetime | None,
                "message": str
            }
        """
        self.client._ensure_connection()

        if isinstance(obj, Project):
            object_type = "Project"
        elif isinstance(obj, Workflow):
            object_type = "Workflow"
        elif isinstance(obj, SubjectSet):
            object_type = "SubjectSet"
        else:
            raise TypeError("El objeto debe ser Project, Workflow o SubjectSet")

        export = None
        message = f"Checking for existing {export_type} export for {object_type} {obj.id}..."

        # Intentar obtener un export existente
        try:
            export = obj.get_export(export_type, wait=False)
            message = f"Found existing {export_type} export for {object_type} {obj.id}."
        except Exception:
            message = f"No existing {export_type} export found for {object_type} {obj.id}. Generating new one..."

        print(message)
        # Si no existe, generarlo
        if not export or isinstance(export, dict) or not hasattr(export, "url"):
            try:
                export = obj.generate_export(export_type, wait=False)
                message = f"Generated new {export_type} export for {object_type} {obj.id}."
            except Exception as e:
                return {
                    "id": obj.id,
                    "object_type": object_type,
                    "type": export_type,
                    "ready": False,
                    "url": None,
                    "created_at": None,
                    "message": f"Error generating export: {e}"
                }

        # Si lo que tenemos es una Response (HTTP)
        print(export.__dict__)
        if hasattr(export, "json"):
            try:
                export_data = export.json()
                url = export_data.get("url")
                created_at = export_data.get("created_at")
            except Exception:
                url = None
                created_at = None
        else:
            url = getattr(export, "url", None)
            created_at = getattr(export, "created_at", None)

        # Esperar si es necesario
        if wait and hasattr(export, "ready"):
            start = time.time()
            while not export.ready and (time.time() - start < timeout):
                time.sleep(10)
                export.reload()

        if isinstance(created_at, str):
            created_at = datetime.fromisoformat(created_at.replace("Z", "+00:00"))

        return {
            "id": obj.id,
            "object_type": object_type,
            "type": export_type,
            "ready": getattr(export, "ready", bool(url)),
            "url": url,
            "created_at": created_at,
            "message": message if url else f"{message} (still processing)"
        }

class ZooniverseClient:
    def __init__(self, project_id: str, username: str, password: str):
        self.project_id = project_id
        self.username = username
        self.password = password

        if not project_id:
            raise ValueError("project_id must be provided and cannot be empty.")
        if not username:
            raise ValueError("username must be provided and cannot be empty.")
        if not password:
            raise ValueError("password must be provided and cannot be empty.")

        self._connected = False

        self.logger = logging.getLogger(__name__)

        # Componentes
        self.subjectsets = SubjectSetsComponent(self)
        self.subjects = SubjectsComponent(self)
        self.annotations = AnnotationsComponent(self)
        self.workflows = WorkflowsComponent(self)

    def connect(self):
        if self._connected:
            return

        self.logger.debug(f"Connecting to Zooniverse... {self.username}")
        Panoptes.connect(username=self.username, password=self.password)
        self._connected = True
        self.logger.debug("Connected successfully.")

    def _ensure_connection(self):
        if not self._connected:
            logging.info("Nos volvemos a conectar automáticamente antes de la operación...")
            self.connect()

    def disconnect(self):
        """Desconecta del servicio Panoptes limpiando la instancia interna."""
        if self._connected:
            self.logger.info("Disconnecting from Zooniverse Panoptes API...")
            try:
                # Limpiar instancia singleton de Panoptes
                if hasattr(Panoptes, "_instance"):
                    Panoptes._instance = None

                self._connected = False
                self.logger.debug("📴 Disconnected from Zooniverse.")
            except Exception as e:
                self.logger.error(f"Error during disconnect: {e}")

    @classmethod
    def from_environment(cls, temp_folder: str = "temp_images") -> "ZooniverseClient":
        """
        Creates an instance using environment variables.

        This method retrieves the following environment variables:
        - ``ZOONIVERSE_PROJECT_ID``
        - ``ZOONIVERSE_USERNAME``
        - ``ZOONIVERSE_PASSWORD``

        Parameters
        ----------
        temp_folder : str, optional
            Name of the temporary folder used to store images, by default "temp_images".

        Returns
        -------
        cls
            An instance of the class initialized with the credentials and project ID.

        Raises
        ------
        ValueError
            If any of the required environment variables are not set.
        """
        project_id = os.getenv("ZOONIVERSE_PROJECT_ID")
        username = os.getenv("ZOONIVERSE_USERNAME")
        password = os.getenv("ZOONIVERSE_PASSWORD")

        if not all([project_id, username, password]):
            raise ValueError(
                "Environment variables ZOONIVERSE_PROJECT_ID, ZOONIVERSE_USERNAME and ZOONIVERSE_PASSWORD must be set."
            )
        return cls(project_id, username, password)

    def _get_current_user_role(self, project_id: int) -> list[str]:
        """
        Devuelve una lista con los roles del usuario autenticado en un proyecto.
        Si no tiene roles, devuelve una lista vacía.
        """
        # Obtener el usuario autenticado
        current_user = User.me()
        current_user_id = str(current_user.id)

        roles = []

        for pr in ProjectRole.where(project_id=project_id):
            links = pr.raw.get("links", {})

            for role_type, user_info in links.items():
                if role_type == "project":
                    continue

                user_id = user_info.get("id")
                if user_id == current_user_id:
                    roles.append(role_type)

        return roles

