from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Dict, Tuple, Any, Optional, Callable, Literal
import csv, json, statistics
import logging, os
import time as time_module
import tempfile
import re
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.error import URLError, HTTPError

from pydantic import BaseModel, validator, HttpUrl
from tenacity import stop_after_attempt, wait_exponential, before_sleep_log, retry, RetryError
from trapper_client.TrapperClient import TrapperClient
from trapper_client.Schemas import (
    TrapperMediaList,
    TrapperObservationList,
    Pagination,
    TrapperObservationResultsTrapper,
    TrapperClassificationResultsList,
    TrapperResource,
)

from wildintel_tools.zooniverse.AnnotationsVoter.AnnotationsVoter import AnnotationsVoter
from wildintel_tools.zooniverse.AnnotationsExtractor.AnnotationsExtractor import AnnotationsExtractor
from wildintel_tools.reports import Report
from wildintel_tools.zooniverse.Schemas import SubjectSetResults, WorkflowData, Zoo2TrapperObservation

import urllib


from wildintel_tools.zooniverse.ZooniverseClient import ZooniverseClient, UploadingException


class DownloadException(Exception):
    """Raised when a media download fails after retries."""


class MediaObservationEntry(BaseModel):
    filePath: HttpUrl
    filePublic: bool
    fileName: str
    timestamp: Optional[datetime]
    deploymentID: str
    fileMediatype : str
    observations: List[str]

    @validator("timestamp", pre=True, always=True)
    def parse_timestamp(cls, v):
        """
        Convierte cadenas vacías en None.
        Si es una cadena no vacía, intenta parsearla como datetime.
        """
        if not v:  # None, "" o valores falsy
            return None
        if isinstance(v, datetime):
            return v
        try:
            return datetime.fromisoformat(v)
        except Exception:
            # opcional: lanzar error o devolver None si no se puede parsear
            return None

class TrapperZooniverseConnector:
    """
    Clase para subir imágenes a Zooniverse y obtener resultados de un SubjectSet.
    """

    def __init__(self, zoo: ZooniverseClient, trapper: TrapperClient):
        """
        Initializes a new instance of the class with project credentials and identifier.

        Parameters
        ----------
        project_id : str
            Unique identifier of the project associated with this instance.
        username : str
            Username used for authentication.
        password : str
            Password associated with the given username.
        """
        self.zoo     = zoo
        self.trapper = trapper

        self.date_format = "%Y:%m:%d %H:%M:%S"
        self.logger = logging.getLogger(__name__)

    def _notify(
        self,
        progress_callback: Optional[
            Callable[[str, str, int, Optional[int], Optional[str], bool, Optional[str], Optional[str]], None]
        ],
        task_name: str,
        state: str,
        advance: int = 1,
        total: Optional[int] = None,
        description: Optional[str] = None,
        set_total: bool = False,
        item_name: Optional[str] = None,
        item_status: Optional[Literal["start", "end", "fail"]] = None,
        item_description: str | None = None,
    ) -> None:
        """Send progress events while logging a concise status message."""
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
        if advance is not None:
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

    def upload_collection(
            self,
            subjectset_name: str,
            collection:int,
            classification_project:int,
            deployments:List[int]=None,
            blacklisted_deployments: Optional[List[int]]=None,
            n_images_seq=5,
            max_interval=90,
            attempts=5,
            delay=15,
            max_attempts_per_subject=5,
            delay_seconds_per_subject=30,
            progress_callback: Optional[Callable[[str, str, int, Optional[int], Optional[str], bool, Optional[str], Optional[str]], None]] = None,
            dry_run: bool = False,
            skip_if_exists: bool = False,
            uploaded_media_ids: Optional[set] = None,
            max_workers: int = 4,
            media_ids: Optional[List[int]] = None,
            excluded_media_ids: Optional[List[int]] = None,
    ) -> Report:

        deployments = list(deployments) if deployments is not None else None

        if deployments is None:
            depl = self.trapper.deployments.get_all(query={"classification_project":classification_project})
            depl = depl.results
            depl = {
                item.pk: item.deployment_id
                for item in depl
                if item.pk is not None and item.deployment_id
            }
            collection_obj = self.trapper.collections.get_by_id(collection)
            if len(collection_obj.results) > 0:
                collection_obj = collection_obj.results[0]
                prefix =f"{collection_obj.name}-".lower()
                deployments = list({pk: name for pk, name in depl.items() if name.lower().startswith(prefix)}.keys())

        deployments = deployments or []

        if blacklisted_deployments:
            blacklist = set(blacklisted_deployments)
            original_total = len(deployments)
            deployments = [dep for dep in deployments if dep not in blacklist]
            skipped = original_total - len(deployments)
            if skipped:
                self.logger.info(f"Skipping {skipped} deployments due to blacklist")

        report = Report(
            f"Collection {collection} and deployments {','.join([str(d) for d in deployments]) if deployments else 'auto-detected'}"
            f" from {self.trapper.base_url}",
            type="UploadMediaReport",
        )

        self.logger.debug(f"Starting upload_collection at {datetime.now().isoformat()}")

        for deployment in deployments:
            self._notify(progress_callback, "getting_media", state="start",
                                  description=f"Getting media for classification project {classification_project}, "
                                              f"collection {collection} and deployment {deployment}...")

            media: TrapperMediaList = self.trapper.media.get_by_collection(
                classification_project, collection, {"deployment": deployment, "private_human": "False", "private_vehicle": "False"}
            )
            self._notify(progress_callback, "getting_media", state="end", set_total=True, total=len(media.results))
            self._notify(progress_callback, "getting_observations", state="start",
                description=f"Getting observations from classification project {classification_project}, "
                            f"collection {collection} and deployment {deployment}...")

            observations: TrapperClassificationResultsList = (
                self.trapper.observations.results.get_by_collection(classification_project, collection, query={"deployment": deployment}))

            self._notify(progress_callback, "getting_observations", state="end", set_total=True,
                         total=len(observations.results))

            self._notify(progress_callback, "filtering_observations", state="start",
                         description="Filtering classified observations...")

            filtered_observations = [
                obs for obs in observations.results
                if obs.observationType and obs.observationType != "unclassified"
            ]

            if len(filtered_observations) == 0:
                self.logger.warning(f"No observations found after filtering for collection {collection} and"
                                    f" classification project {classification_project}.")

            observations = TrapperClassificationResultsList(
                **{
                    "results": filtered_observations,
                    "pagination": Pagination(
                        page=1,
                        page_size=len(filtered_observations),
                        pages=1,
                        count=len(filtered_observations)
                    )
                }
            )

            self._notify(progress_callback, "filtering_observations", state="end", set_total=True,
                         total=len(observations.results))

            self._notify(progress_callback, "getting_url", state="start", description=f"Getting url for medias classified...")

            media_map=self._merge_media_and_observations(media, observations)
            public_media_map = {media_id: entry for media_id, entry in media_map.items() if entry.filePublic}

            if len(media_map.keys()) == 0:
                self.logger.debug(f"No valid observations found for collection {collection} and classification project {classification_project}.")

            self._notify(progress_callback, "getting_url", state="end", set_total=True, total=len(public_media_map.keys()))
            self._notify(progress_callback, "preparing_sequences", state="start", description=f"Preparing sequences...")

            sequences = self._generate_zoo_images_from_media_map(public_media_map, max_interval, n_images_seq,
                                                             filter_middle_humans=True)
            self._notify(progress_callback, "preparing_sequences", state="end", set_total=True, total=len(sequences))

            # Crear SubjectSet antes de comenzar
            if dry_run:
                self.logger.info(f"[DRY-RUN] Skipping subjectset creation: '{subjectset_name}'")
                subjectset = None
            else:
                self.logger.debug(f"Creando SubjectSet {subjectset_name} en Zooniverse")
                subjectset = self.zoo.subjectsets.create(subjectset_name)

            flat_media = [media for seq in sequences for media in seq]

            # --- media whitelist / blacklist ---
            if media_ids is not None:
                allowed = set(media_ids)
                before = len(flat_media)
                flat_media = [m for m in flat_media if m["mediaID"] in allowed]
                self.logger.info(
                    f"media_ids whitelist: kept {len(flat_media)}/{before} media items"
                )
            if excluded_media_ids is not None:
                blocked = set(excluded_media_ids)
                before = len(flat_media)
                flat_media = [m for m in flat_media if m["mediaID"] not in blocked]
                self.logger.info(
                    f"excluded_media_ids blacklist: kept {len(flat_media)}/{before} media items"
                )

            total = len(flat_media)

            self._notify(progress_callback, "synchronizing_images", state="start",
                     description=f"Synchronizing {total} images...",
                    total=total, set_total=True)

            with tempfile.TemporaryDirectory() as temp_dir:

                def process_one(media):
                    media_id = media['mediaID']
                    name = self._get_zoo_filename(media)
                    local_path = os.path.join(temp_dir, name)

                    if uploaded_media_ids and media_id in uploaded_media_ids:
                        self._notify(progress_callback, "synchronizing_images",
                                     state="running", advance=1,
                                     item_name=f"{media_id}", item_status="end",
                                     item_description="Already uploaded, skipped")
                        report.add_success(f"{media_id}@media", "upload_skipped", **{"reason": "already uploaded"})
                        return

                    self._notify(progress_callback, "synchronizing_images",
                                 state="running", advance=0,
                                 item_description=f"↓↓ Downloading media to {str(Path(temp_dir) / name)}",
                                 item_name=f"{media_id}", item_status="start")

                    try:
                        if dry_run:
                            self.logger.info(f"[DRY-RUN] Skipping download of media {media_id}")
                            self._notify(
                                progress_callback, "synchronizing_images",
                                state="running", advance=0,
                                item_description=f"[DRY-RUN] Simulated download of {str(Path(temp_dir) / name)}",
                                item_name=f"{media_id}", item_status="end",
                            )
                            report.add_success(f"{media_id}@media", "download_simulated", **{"path": local_path})
                        else:
                            self._download_image_safe(str(media['filePath']), str(Path(temp_dir) / name),
                                                      attempts=attempts, delay_seconds=delay)
                            # Advance bar as soon as download completes so the user
                            # sees immediate progress even while uploads are in flight.
                            self._notify(
                                progress_callback, "synchronizing_images",
                                state="running", advance=1,
                                item_description=f"↓↓ Downloaded {str(Path(temp_dir) / name)}",
                                item_name=f"{media_id}", item_status="end",
                            )
                            report.add_success(f"{media_id}@media", "download", **{"path": local_path})

                        if dry_run:
                            self.logger.info(f"[DRY-RUN] Skipping upload of media {media_id} to Zooniverse")
                            self._notify(
                                progress_callback, "synchronizing_images",
                                state="running", advance=1,
                                item_description=f"[DRY-RUN] Simulated upload to Zooniverse subject {subjectset_name}",
                                item_name=f"{media_id}", item_status="end",
                            )
                            report.add_success(f"{media_id}@media", "upload_simulated", **{"subject_id": "dry-run", "path": local_path})
                        else:
                            self._notify(
                                progress_callback, "synchronizing_images",
                                state="running", advance=0,
                                item_description=f"↑↑↑ Uploading to Zooniverse subject {subjectset_name}",
                                item_name=f"{media_id}", item_status="start",
                            )
                            subject_metadata = self._build_metadata_from_trapper(
                                self.trapper, media_id, media["fileName"]
                            )
                            subject = self.zoo.subjects.create(
                                local_path, subjectset, subject_metadata,
                                max_attempts_per_subject, delay_seconds_per_subject,
                                skip_if_exists=skip_if_exists,
                            )
                            report.add_success(f"{media_id}@media", "upload",
                                              **{"subject_id": subject.id, "path": local_path})
                            if os.path.exists(local_path):
                                os.remove(local_path)
                                self.logger.debug(f"Removed temporary file {local_path}")
                            # advance=0: already counted when download finished
                            self._notify(
                                progress_callback, "synchronizing_images",
                                state="running", advance=0,
                                item_description=f"↑↑↑ Uploaded to Zooniverse ({subject.id})",
                                item_name=f"{media_id}", item_status="end",
                            )

                    except DownloadException as e:
                        # Download failed → advance bar now (it wasn't advanced yet)
                        self._notify(
                            progress_callback, "synchronizing_images",
                            state="running", advance=1,
                            item_description=f"Download failed: {e}",
                            item_name=f"{media_id}", item_status="fail",
                        )
                        report.add_error(f"{media_id}@media", "download", str(e),
                                        **{"path": str(media['filePath'])})
                    except UploadingException as e:
                        # Download already advanced the bar → advance=0 here
                        self._notify(
                            progress_callback, "synchronizing_images",
                            state="running", advance=0,
                            item_description=f"Upload failed: {e}",
                            item_name=f"{media_id}", item_status="fail",
                        )
                        report.add_error(f"{media_id}@media", "upload", str(e),
                                        **{"path": local_path})
                    finally:
                        if os.path.exists(local_path):
                            os.remove(local_path)

                with ThreadPoolExecutor(max_workers=max_workers) as executor:
                    futures = {executor.submit(process_one, media): media for media in flat_media}
                    for f in as_completed(futures):
                        pass

            self._notify(progress_callback, "synchronizing_images", state="end")
        report.finish()
        return report

    def update_subject_metadata(
        self,
        subjectset_id: int,
        classification_project: int,
        progress_callback: Optional[Callable[[str, str, int, Optional[int], Optional[str], bool, Optional[str], Optional[str]], None]] = None,
        dry_run: bool = False,
        white_list: Optional[List[int]] = None,
        black_list: Optional[List[int]] = None,
        attempts: int = 5,
        delay_seconds: int = 15,
        max_workers: int = 1,
    ) -> Report:
        """
        Update metadata of all subjects in a Zooniverse SubjectSet using Trapper media info.

        It extracts ``media_id`` from each subject filename, fetches media from Trapper,
        builds metadata with the same schema used during uploads, and updates each subject.
        """
        report = Report(
            f"Update subject metadata for subjectset {subjectset_id} from {self.trapper.base_url}",
            type="UpdateSubjectMetadataReport",
        )

        attempts = max(1, int(attempts))
        delay_seconds = max(0, int(delay_seconds))

        included_set = set(white_list) if white_list else None
        excluded_set = set(black_list or [])

        subjects_iter = self.zoo.subjects.get_by_subjectset(subjectset_id, to_list=False)

        self._notify(
            progress_callback,
            "updating_subjects",
            state="start",
            description=f"Updating metadata for subjects in subjectset {subjectset_id}...",
        )

        report_lock = threading.Lock()

        def _is_selected_subject(s) -> bool:
            sid = getattr(s, "id", None)
            if sid in excluded_set:
                return False
            if included_set is not None and sid not in included_set:
                return False
            return True

        def _process_subject_once(s):
            sid = str(getattr(s, "id", "unknown"))
            resource_id = self._get_trapper_resource_id_from_subjec(s)
            if resource_id is None:
                raise ValueError(f"Could not find media_id in subject {sid}")

            self._notify(
                progress_callback,
                "updating_subjects",
                state="running",
                advance=0,
                item_name=sid,
                item_status="start",
                item_description=f"Resolving resource {resource_id} from Trapper",
            )

            resource_list = self.trapper.resources.get_by_pk(resource_id)
            if not resource_list.results:
                raise ValueError(f"Could not find resource with id {resource_id} in Trapper")

            resource: TrapperResource = resource_list.results[0]
            deployment_id = resource.name.split("-")[0] if resource.name and "-" in resource.name else ""
            zoo_name = self._get_zoo_filename(
                {
                    "mediaID": resource_id,
                    "deploymentID": deployment_id,
                    "fileName": resource.name,
                }
            )

            new_metadata = self._build_subject_metadata(resource_id, zoo_name)
            new_metadata["Filename"] = zoo_name

            if dry_run:
                with report_lock:
                    report.add_success(f"{sid}@subject", "update_metadata_simulated", **{"media_id": resource_id})
            else:
                self.zoo.subjects.update_one_metadata(s.id, new_metadata)
                with report_lock:
                    report.add_success(f"{sid}@subject", "update_metadata", **{"media_id": resource_id})

            self._notify(
                progress_callback,
                "updating_subjects",
                state="running",
                advance=1,
                item_name=sid,
                item_status="end",
                item_description=f"Metadata updated from resource {resource_id}",
            )

        def _process_subject(s):
            sid = str(getattr(s, "id", "unknown"))

            @retry(
                stop=stop_after_attempt(attempts),
                wait=wait_exponential(multiplier=delay_seconds, min=delay_seconds),
                reraise=True,
                before_sleep=before_sleep_log(self.logger, logging.WARNING),
            )
            def _run_with_retry():
                return _process_subject_once(s)

            try:
                _run_with_retry()
            except Exception as last_error:
                with report_lock:
                    report.add_error(f"{sid}@subject", "update_metadata", str(last_error))
                self._notify(
                    progress_callback,
                    "updating_subjects",
                    state="running",
                    advance=1,
                    item_name=sid,
                    item_status="fail",
                    item_description=str(last_error),
                )

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {
                executor.submit(_process_subject, s): s
                for s in subjects_iter
                if _is_selected_subject(s)
            }
            for f in as_completed(futures):
                pass

        self._notify(progress_callback, "updating_subjects", state="end")
        report.finish()
        return report

    def upload_annotations(
          self,
          subjectset_id: int,
          wf_id: int,
          collection_id: int,
          cp_id: int,
          output_dir: Path = None,
          deployments:List[int] = None,
          blacklisted_deployments: Optional[List[int]] = None,
          progress_callback: Optional[Callable[[str, str, int, Optional[int], Optional[str], bool, Optional[str], Optional[str]], None]] = None,
          max_workers: int = 4,
          save_zoo_annotations: bool = True,
          max_subjects: Optional[int] = None,
          classified_by: Optional[str] = None,
  ):
        """
        Gerenates csv file with annotations from Zooniverse ready to import y Trapper.

        :param subjectset_id:
        :param wf_id:
        :param collection_id:
        :param cp_id:
        :param output_dir:
        :param deployments:
        :param blacklisted_deployments:
        :param progress_callback:
        :return:
        """
        all_deployments_mode = deployments is None and not blacklisted_deployments

        if not all_deployments_mode:
            deployments = list(deployments) if deployments is not None else None

            if deployments is None:
                depl = self.trapper.deployments.get_all(query={"classification_project":cp_id})
                depl = depl.results
                depl = {
                    item.pk: item.deployment_id
                    for item in depl
                    if item.pk is not None and item.deployment_id
                }
                collection_obj = self.trapper.collections.get_by_id(collection_id)
                if len(collection_obj.results) > 0:
                    collection_obj = collection_obj.results[0]
                    prefix =f"{collection_obj.name}-".lower()
                    deployments = list({pk: name for pk, name in depl.items() if name.lower().startswith(prefix)}.keys())

            deployments = deployments or []

            if blacklisted_deployments:
                blacklist = set(blacklisted_deployments)
                original_total = len(deployments)
                deployments = [dep for dep in deployments if dep not in blacklist]
                skipped = original_total - len(deployments)
                if skipped:
                    self.logger.info(f"Skipping {skipped} deployments due to blacklist")

        report = Report(f"Annotation from  {subjectset_id} to  classification project {cp_id}", type="DownloadAnnotations" )

        self._notify(progress_callback, "fetching_annotations", "start",
                     description=f"Fetching Zooniverse annotations for workflow {wf_id} and subjectb set {subjectset_id}...")
        self.zoo.connect()
        zoo_annotations: SubjectSetResults = self.zoo.annotations.get_by_workflow(wf_id)

        if len(zoo_annotations.workflows) == 0:
            self._notify(progress_callback, "fetching_annotations", "fail",
                         description="No annotations found")
            raise ValueError(f"No annotations found for subjectset {subjectset_id}")

        wf = self.zoo.workflows.get_by_id(wf_id)
        wf_key = f"{wf.id}:{wf.display_name}"

        if wf_key not in zoo_annotations.workflows:
            self._notify(progress_callback, "fetching_annotations", "fail",
                         description=f"Workflow key {wf_key} not found")
            raise ValueError(f"Workflow key {wf_key} not found in annotations")

        wf_annotations: WorkflowData = zoo_annotations.workflows[wf_key]
        self._notify(progress_callback, "fetching_annotations", "end",
                     description=f"Fetched {len(wf_annotations.data)} Zooniverse annotations for workflow {wf_id} and subjectb set {subjectset_id}"
                     )

        (extractor, voter) = self._get_extrator_vote(wf.id)
        flat_results: List[TrapperObservationResultsTrapper] = []
        all_zoo_opinions: List[tuple] = []

        subject_items = list(wf_annotations.data.items())
        if max_subjects is not None:
            subject_items = subject_items[:max_subjects]
        n_subjects = len(subject_items)

        iter_deployments = [None] if all_deployments_mode else deployments
        for depl in iter_deployments:
            depl_label = "all" if depl is None else str(depl)
            query = {"camtrapdp": "False"}
            if depl is not None:
                query["deployment"] = depl
            self._notify(
                progress_callback, "fetching_trapper_classifications", "start",
                description=f"Fetching Trapper classifications — cp {cp_id}, collection {collection_id}, deployment {depl_label}...",
            )
            collections = self.trapper.raw.get_all_pages(
                endpoint=f"/media_classification/api/project/{cp_id}/collections"
            )
            collection_inter_id = [r["pk"] for r in collections["results"] if r["collection_pk"] == collection_id]
            query["collection"] = ",".join(map(str, collection_inter_id))
            raw_observations = self.trapper.raw.get_all_pages(
                endpoint=f"/media_classification/api/classifications/results/{cp_id}", query=query
            )
            self._notify(
                progress_callback, "fetching_trapper_classifications", "end",
                description=f"Fetched {len(raw_observations['results'])} Trapper classifications — cp {cp_id}, collection {collection_id}, deployment {depl_label}",
            )
            self._notify(progress_callback, "processing_subjects", "start",
                         total=n_subjects, set_total=True,
                         description=f"Processing {n_subjects} subjects...")
            _valid_keys = (
                set(TrapperObservationResultsTrapper.model_fields)
                | {info.alias for info in TrapperObservationResultsTrapper.model_fields.values() if info.alias}
            )
            trapper_observations_by_media: Dict[str, List[TrapperObservationResultsTrapper]] = defaultdict(list)
            for _o in raw_observations["results"]:
                filtered = {k: v for k, v in _o.items() if k in _valid_keys}
                if "bboxes" in filtered:
                    import json as _json
                    bboxes_val = filtered["bboxes"]
                    if isinstance(bboxes_val, str) and bboxes_val not in ("", "null"):
                        try:
                            bboxes_val = _json.loads(bboxes_val)
                        except Exception:
                            bboxes_val = None
                    if isinstance(bboxes_val, list):
                        bboxes_val = [b for b in bboxes_val if b is not None] or None
                    filtered["bboxes"] = bboxes_val
                trapper_observations_by_media[str(_o["mediaID"])].append(
                    TrapperObservationResultsTrapper.model_validate(filtered)
                )

            lock = threading.Lock()

            def _process_subject(item):
                key, users_ss_opinions = item
                subject_id, media_id = key.split(":")
                if not media_id.isdigit():
                    return

                all_media_observations: List[TrapperObservationResultsTrapper] = \
                    trapper_observations_by_media.get(media_id, [])
                all_media_observations_ids = list(
                    {obj.id for obj in all_media_observations if obj.id is not None}
                )

                if len(all_media_observations_ids) == 0:
                    with lock:
                        report.add_error(
                            f"subject:{subject_id}",
                            "getting_decision",
                            f"No Trapper observations found for media {media_id} in collection {collection_id}",
                        )
                        self._notify(progress_callback, "processing_subjects", "progress",
                                     advance=1, item_name=f"media:{media_id}",
                                     item_status="fail",
                                     item_description="No Trapper observations found")
                    return

                extracted_user_opinions = extractor.run(users_ss_opinions)
                decisions: List[Zoo2TrapperObservation] = voter.run(extracted_user_opinions)

                if not decisions:
                    with lock:
                        report.add_error(
                            f"subject:{subject_id}",
                            "getting_decision",
                            f"No decisions produced for media {media_id} from Zooniverse votes",
                        )
                        self._notify(progress_callback, "processing_subjects", "progress",
                                     advance=1, item_name=f"media:{media_id}",
                                     item_status="fail",
                                     item_description="No decisions from voter")
                    return

                base_fields = {
                    k: v for k, v in all_media_observations[0].__dict__.items()
                    if not k.startswith("_")
                }
                local_obs = []
                for decision in decisions:
                    for obser_id in all_media_observations_ids:
                        merged_fields = {
                            **base_fields,
                            **decision.model_dump(),
                            "id": obser_id,
                            "bboxes": None,
                            "classificationTimestamp": datetime.now(timezone.utc),
                            "classifiedBy": classified_by or self.trapper.user_name,
                            "classificationMethod": "human",
                            #"observationComments": f"Automatically classified by Zooniverse in workflow {wf_key} for subject {subject_id}",
                        }
                        local_obs.append((
                            TrapperObservationResultsTrapper.model_construct(**merged_fields),
                            f"subject:{subject_id}",
                            f"Added an observation for resource {media_id} with {decision.scientificName}",
                        ))

                with lock:
                    all_zoo_opinions.extend(extracted_user_opinions)
                    for obs, subj_key, msg in local_obs:
                        flat_results.append(obs)
                        report.add_success(subj_key, "getting_decision", msg)

                self._notify(progress_callback, "processing_subjects", "progress",
                             advance=1, item_name=f"media:{media_id}",
                             item_status="end",
                             item_description=f"{len(decisions)} decision(s)")

            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                futures = [
                    executor.submit(_process_subject, item)
                    for item in subject_items
                ]
                for future in as_completed(futures):
                    future.result()

        self._notify(progress_callback, "processing_subjects", "end",
                     description=f"Processed {n_subjects} subjects")

        if output_dir:
            csv_path = Path(output_dir)
            if csv_path.is_dir():
                csv_path = csv_path / f"annotations_{subjectset_id}_{wf_id}.csv"
            self.logger.debug(f"Saving observations to CSV in {csv_path}")
            self._trapper_observations_to_csv(
                flat_results,
                csv_path,
                ["observationType", "scientificName", "count", "classifiedBy",
                 "classificationMethod", "observationComments", "_id"],
            )
            if save_zoo_annotations and all_zoo_opinions:
                zoo_csv_path = csv_path.parent / f"zoo_annotations_{csv_path.name}"
                self.logger.debug(f"Saving zoo annotations to CSV in {zoo_csv_path}")
                self._zoo_opinions_to_csv(all_zoo_opinions, zoo_csv_path)

        return report

    def _get_zoo_filename(self, media):
        return f"{media['mediaID']}_x_{media['deploymentID']}_x_{media['fileName']}"

    @staticmethod
    def _extract_subject_filename(subject: Any) -> Optional[str]:
        metadata = getattr(subject, "metadata", {}) or {}
        for key in ("Filename", "filename", "file_name", "name", "display_name"):
            value = metadata.get(key)
            if value:
                return str(value)

        for attr in ("display_name", "name"):
            value = getattr(subject, attr, None)
            if value:
                return str(value)
        return None

    @staticmethod
    def _extract_media_id_from_filename(filename: str) -> Optional[int]:
        basename = Path(filename).name
        match = re.match(r"(\d+)(?=_x_)", basename)
        if match:
            return int(match.group(1))

        fallback = re.search(r"(\d+)", basename)
        if fallback:
            return int(fallback.group(1))
        return None

    @staticmethod
    def _build_metadata_from_trapper(trapper_client: TrapperClient, media_id: int, image_name: str) -> Dict[str, Any]:
        base_url = str(trapper_client.base_url)
        if not base_url.endswith("/"):
            base_url = base_url + "/"
        return {
            "external_id": f"{base_url}:media:{media_id}",
            "preview": f"{base_url}storage/resource/media/{media_id}/pfile/",
            "link": f"{base_url}storage/resource/media/{media_id}/file/",
            "thumbnail": f"{base_url}storage/resource/media/{media_id}/tfile/",
            "origin": f"{base_url}",
            "license": "http://creativecommons.org/licenses/by-nc/4.0/legalcode",
            "image_name": image_name,
        }

    def _build_subject_metadata(self, media_id: int, image_name: str) -> Dict[str, Any]:
        return self._build_metadata_from_trapper(self.trapper, media_id, image_name)

    def _get_extrator_vote(self, workflow_id) -> Tuple[AnnotationsExtractor, AnnotationsVoter]:
        import importlib

        extractor_class_name = f"Workflow{workflow_id}AnnotationExtractor"
        voter_class_name = f"Workflow{workflow_id}AnnotationsVoter"

        extractor_module = importlib.import_module(f"wildintel_tools.zooniverse.AnnotationsExtractor.{extractor_class_name}")
        voter_module = importlib.import_module(f"wildintel_tools.zooniverse.AnnotationsVoter.{voter_class_name}")

        ExtractorClass = getattr(extractor_module, extractor_class_name)
        VoterClass = getattr(voter_module, voter_class_name)

        return ExtractorClass(), VoterClass

    def _download_image(self, url: str, dest_path: str, attempts=5, delay_seconds=60) -> bool:
        """Descarga una imagen desde una URL con reintentos."""
        @retry(
            stop=stop_after_attempt(attempts),
            wait=wait_exponential(multiplier=delay_seconds, min=delay_seconds),
            reraise=False,
            before_sleep=before_sleep_log(logging.getLogger(__name__), logging.WARNING),
        )
        def _do_download():
            urllib.request.urlretrieve(url, dest_path)
            return True

        return _do_download()

    def _download_image_safe(self, url: str, dest_path: str, attempts=5, delay_seconds=60) -> bool:
        """Wrapper that raises DownloadException when retries are exhausted."""
        try:
            return self._download_image(url, dest_path, attempts=attempts, delay_seconds=delay_seconds)
        except RetryError as e:
            cause = e.last_attempt.exception() if e.last_attempt else e
            raise DownloadException(f"Failed downloading {url}") from cause
        except (URLError, HTTPError, OSError) as e:
            raise DownloadException(f"Failed downloading {url}") from e

    def _merge_media_and_observations( self,
            media :TrapperMediaList,
            observations: TrapperObservationList
    ) -> Dict[str, MediaObservationEntry]:
        """
        Merge media and observations into a single dictionary keyed by mediaID.

        Parameters
        ----------
        results : tuple
            Tuple containing (media, observations) results, usually from run_tasks_with_progress.
        cp_pk : int
            Classification project ID (for logging purposes).
        collection : int
            Collection ID (for logging purposes).

        Returns
        -------
        Dict[str, MediaObservationEntry]
            Dictionary mapping mediaID to its media data and associated observation types.
        """

        media_map: Dict[str, MediaObservationEntry] = {}
        media_ids = { m.mediaID for m in getattr(media, "results", []) }

        for obs in getattr(observations, "results", []):
            media_id = str(obs.mediaID)

            if obs.mediaID in media_ids:
                obs_type = getattr(obs, "observationType", None)

                if obs.mediaID not in media_map:
                    media_info = [m for m in media.results if m.mediaID ==  obs.mediaID]

                    media_map[obs.mediaID] = MediaObservationEntry(**{
                        "filePath": media_info[0].filePath,
                        "filePublic": media_info[0].filePublic,
                        "fileName": media_info[0].fileName,
                        "deploymentID": media_info[0].deploymentID,
                        "fileMediatype": media_info[0].fileMediatype,
                        "timestamp": media_info[0].timestamp,
                        "observations": []
                    }
                    )

                if obs_type:

                    if isinstance(obs_type, list):
                        media_map[obs.mediaID].observations.extend(obs_type)
                    else:
                        media_map[obs.mediaID].observations.append(obs_type)
            else:
                self.logger.warning(f"No  encontré información sobre el media {media_id} asociado a la observacion")

        if len(media_ids - set(media_map.keys())) > 0 :
            self.logger.debug("Hay media sin observaciones aprobadas")

        return media_map

    def _show_sequences_as_json(self,sequences):
        """
        Muestra una lista de secuencias (por ejemplo, listas de MediaObservationEntry)
        formateadas en JSON con indentación jerárquica.
        """

        # Si los objetos tienen campos datetime, los convertimos a string
        def default_serializer(obj):
            if hasattr(obj, "isoformat"):
                return obj.isoformat()
            return str(obj)

        import json
        return (json.dumps(sequences, indent=4, default=default_serializer))

    def _generate_zoo_images_from_media_map(self, media_map: Dict[str, MediaObservationEntry], max_interval : int,
            n_images_seq:int, filter_middle_humans: bool =True) -> List[Dict[str, Any]]:
        """
        Given a set of media and its observations, generates a set of images sequences. Each sequence is a list of images
        taken within max_interval seconds. Each sequences is uniform sampling of n_images_seq images from the sequence.

        Parameters
        ----------
        media_map : Dict[str, MediaObservationEntry]
            Dictionary mapping mediaID to its media data and associated observation types.
        max_interval : int
            Maximum time interval (in seconds) between consecutive images in a sequence.
        n_images_seq : int
            Number of images to sample from each sequence.
        filter_middle_humans : bool
            If True, removes media classified as 'human' from intermediate sequences (not the first or last sequence of a deployment). Defaults to True.

        Returns
        -------
        List[Dict[str, Any]]
            List of sampled image dictionaries ready for upload to Zooniverse, grouped by deployment and filtered
        """

        rows = self._convert_timestamps_from_media_map(media_map)
        self.logger.debug(("Agrupando media por deployment"))
        grouped = self._group_by_deployment(rows)

        sampled_sequences = []

        for group in grouped.values():
            ordered = sorted(group, key=lambda x: x['timestamp'])

            # Generamos las secuencias, una secuencia es un conjunto de imágenes tomadas
            # en instantes de tiempo consecutivos, separados por menos de max_interval segundos.

            sequences = []
            current_seq = [ordered[0]]

            for prev, curr in zip(ordered, ordered[1:]):
                delta = (curr['timestamp'] - prev['timestamp']).total_seconds()
                if delta <= max_interval:
                    current_seq.append(curr)
                else:
                    # Cierra la secuencia actual y empieza una nueva
                    sequences.append(current_seq)
                    current_seq = [curr]

            sequences.append(current_seq)
            #self.logger.debug(f"Secuencias obtenidas {len(sequences)}: {self._show_sequences_as_json(sequences)}")
            self.logger.debug(f"Secuencias obtenidas {len(sequences)}")

            if filter_middle_humans:
                self.logger.debug(f"Filtering humans...")
                sequences = self._filter_human_media_from_middle_sequences(sequences)


            # Muestreamos cada scuencias
            for seq in sequences:
                self.logger.debug(f"Muestreando secuencias con {len(seq)} imagenes...")
                sampled = self._sample_sequence(seq, n_images_seq)
                self.logger.debug(f"Obtenido muestreo de {len(sampled)} imagenes...")
                sampled_sequences.append(sampled)

            #self.logger.debug(f"Secuencias muestreadas {self._show_sequences_as_json(sampled_sequences)}")

        return sampled_sequences

    def _filter_human_media_from_middle_sequences(
        self, sequences: List[List[Dict[str, Any]]]
    ) -> List[List[Dict[str, Any]]]:
        """
        Elimina los medias clasificados como 'human' de las secuencias intermedias.
        La primera y la última secuencia se mantienen intactas.
        """

        if len(sequences) <= 2:
            return sequences

        filtered_sequences = []

        for i, seq in enumerate(sequences):
            # Primera y última secuencia → intactas
            if i == 0 or i == len(sequences) - 1:
                filtered_sequences.append(seq)
                continue

            # Secuencias intermedias → eliminar medias con 'human'
            filtered_seq = [
                media
                for media in seq
                if not ("observations" in media and media["observations"] and "human" in media["observations"])
            ]

            filtered_sequences.append(filtered_seq)

        return filtered_sequences

    def _sample_sequence(self, rows: List[Dict], n_images_seq) -> List[Dict]:
        """Selecciona un subconjunto de imágenes distribuidas uniformemente."""
        if len(rows) <= n_images_seq:
            return rows
        step = (len(rows) - 1) / (n_images_seq - 1) if n_images_seq > 1 else 0
        indices = [round(i * step) for i in range(n_images_seq)]
        return [rows[i] for i in indices]

    def _count_until_threshold(self, differences: List[float], max_interval) -> Tuple[int, List[float]]:
        """Cuenta cuántas imágenes están dentro del umbral de tiempo."""
        for i, val in enumerate(differences):
            if val > max_interval:
                return i, differences[i:]
        return len(differences), []

    def _convert_timestamps_from_media_map(self, media_map: Dict[str, MediaObservationEntry]) -> List[Dict]:
        """Convierte timestamps ISO8601 a objetos datetime (in place)."""
        rows = []
        for mid, data in media_map.items():
            try:
                data.timestamp= datetime.fromisoformat(data.timestamp)
            except Exception as e:
                pass  # si no se puede convertir, se deja como está

            rows.append({**data.model_dump(), "mediaID": mid})
        return rows

    def _group_by_deployment(self, rows: List[Dict]) -> Dict[str, List[Dict]]:
        """Agrupa las imágenes por deploymentID."""
        groups = defaultdict(list)
        for row in rows:
            deployment = row.get('deploymentID', 'unknown')
            groups[deployment].append(row)
        return groups

    def _get_trapper_resource_id_from_subjec(self, s:"Subject"):
        metadata = (s.raw or {}).get("metadata") or {}
        resource_id = None

        filename = metadata.get("Filename") or metadata.get("filename")
        if isinstance(filename, str):
            m = re.match(r"^(\d+)_x_", filename)
            if m:
                resource_id = int(m.group(1))

        if resource_id is None:
            image_name = metadata.get("image_name")
            if isinstance(image_name, str):
                m = re.match(r"^(\d+)_x_", image_name)
                if m:
                    resource_id = int(m.group(1))

        if resource_id is None:
            external_id = metadata.get("external_id")
            if isinstance(external_id, str):
                m = re.search(r":(\d+)$", external_id)
                if m:
                    resource_id = int(m.group(1))

        return resource_id

    def _trapper_observations_to_csv(self, observations: List[TrapperObservationResultsTrapper]
                                     , path: Path,
                                     fields: Optional[List[str]] = None):
        import csv

        def format_datetime(value):
            if isinstance(value, datetime):
                return value.strftime("%Y-%m-%dT%H:%M:%S%z")
            return value

        # Convertir modelos a dicts
        data = [obs.model_dump(by_alias=True) for obs in observations]

        # Formatear las fechas
        for row in data:
            for key, value in row.items():
                row[key] = format_datetime(value)

        # Filtrar solo los campos indicados, si se proporcionan
        if fields:
            data = [{k: v for k, v in row.items() if k in fields} for row in data]
            fieldnames = fields
        else:
            fieldnames = data[0].keys() if data else []
        with path.open("w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(data)

    @staticmethod
    def _zoo_opinions_to_csv(opinions: List[tuple], path: Path) -> None:
        import csv, json
        rows = []
        for k_majority, sid, choices in opinions:
            for name, answers in choices:
                rows.append({
                    "subject_id": sid,
                    "k_majority": k_majority,
                    "scientific_name": name,
                    "answers": json.dumps(answers) if isinstance(answers, dict) else str(answers),
                })
        if not rows:
            return
        with path.open("w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=["subject_id", "k_majority", "scientific_name", "answers"])
            writer.writeheader()
            writer.writerows(rows)

    @staticmethod
    def _load_uploaded_files_list(path: str) -> list[str]:
        """
        Lee un archivo de texto que contiene rutas de archivos (uno por línea)
        y devuelve una lista con esos paths.
        Se usa para mantener registro de las imágenes ya subidas o con errores.
        """
        if not os.path.exists(path):
            return []
        with open(path, 'r', encoding='utf-8') as f:
            return [line.strip() for line in f if line.strip()]

    # ------------------------------------------------------------------
    # Subject-export analysis helpers
    # ------------------------------------------------------------------

    _MEDIA_ID_RE = re.compile(r":media:(\d+)\s*$")

    @staticmethod
    def _iter_subject_export_rows(csv_path: Path, subject_set_id: Optional[int] = None):
        """Yield parsed rows from a Zooniverse subjects export (CSV or TSV), optionally filtered by subject_set_id."""
        with open(csv_path, newline="", encoding="utf-8") as f:
            first_line = f.readline()
            f.seek(0)
            delimiter = "\t" if "\t" in first_line else ","
            reader = csv.DictReader(f, delimiter=delimiter)
            for row in reader:
                if subject_set_id is not None:
                    try:
                        if int(row.get("subject_set_id", "").strip()) != subject_set_id:
                            continue
                    except (ValueError, TypeError):
                        continue
                yield row

    @classmethod
    def _media_id_from_subject_row(cls, row: dict) -> Optional[int]:
        """Return the Trapper media_id from a subject export row, checking origin then external_id."""
        raw = row.get("metadata", "")
        try:
            metadata = json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            return None
        for key in ("origin", "external_id"):
            value = metadata.get(key) or ""
            m = cls._MEDIA_ID_RE.search(value.strip())
            if m:
                return int(m.group(1))
        return None

    @classmethod
    def uploaded_media_id(
        cls,
        csv_path: Path,
        subject_set_id: Optional[int] = None,
    ) -> dict[int, int]:
        """Return a mapping of media_id → subject_id from a Zooniverse subjects export.

        Only rows for which a media_id can be extracted are included.
        When the same media_id appears more than once the last subject_id wins.
        """
        result: dict[int, int] = {}
        for row in cls._iter_subject_export_rows(csv_path, subject_set_id):
            mid = cls._media_id_from_subject_row(row)
            if mid is None:
                continue
            try:
                sid = int(row.get("subject_id", "").strip())
            except (ValueError, TypeError):
                continue
            result[mid] = sid
        return result

    def unmatched_subject_id(
        self,
        csv_path: Path,
        subject_set_id: Optional[int] = None,
        progress_callback: Optional[Callable] = None,
    ) -> list[int]:
        """Return the list of subject_ids for which no media_id could be extracted."""
        task_name = "scanning_unmatched"

        rows = list(self._iter_subject_export_rows(csv_path, subject_set_id))
        total = len(rows)

        self._notify(
            progress_callback, task_name, "start", 0, total,
            f"Scanning {total} subjects for missing media IDs…", True,
        )

        result: list[int] = []
        for row in rows:
            if self._media_id_from_subject_row(row) is not None:
                self._notify(progress_callback, task_name, "running", 1)
                continue
            try:
                sid = int(row.get("subject_id", "").strip())
            except (ValueError, TypeError):
                self._notify(progress_callback, task_name, "running", 1)
                continue
            result.append(sid)
            self._notify(
                progress_callback, task_name, "running", 1,
                item_name=str(sid), item_status="fail",
                item_description="no media_id extractable",
            )

        self._notify(progress_callback, task_name, "end", 0)

        return result

    def duplicated_media_id(
        self,
        csv_path: Path,
        subject_set_id: Optional[int] = None,
        progress_callback: Optional[Callable] = None,
    ) -> dict[int, list[int]]:
        """Return a mapping of media_id → [subject_id, ...] for media_ids that appear more than once."""
        task_name = "scanning_duplicates"

        rows = list(self._iter_subject_export_rows(csv_path, subject_set_id))
        total = len(rows)

        self._notify(
            progress_callback, task_name, "start", 0, total,
            f"Scanning {total} subjects for duplicate media IDs…", True,
        )

        counts: dict[int, list[int]] = defaultdict(list)
        for row in rows:
            mid = self._media_id_from_subject_row(row)
            if mid is None:
                self._notify(progress_callback, task_name, "running", 1)
                continue
            try:
                sid = int(row.get("subject_id", "").strip())
            except (ValueError, TypeError):
                self._notify(progress_callback, task_name, "running", 1)
                continue
            counts[mid].append(sid)
            self._notify(progress_callback, task_name, "running", 1)

        self._notify(progress_callback, task_name, "end", 0)

        return {mid: sids for mid, sids in counts.items() if len(sids) > 1}

    def estimate_upload(
        self,
        collection: int,
        classification_project: int,
        deployments: Optional[List[int]] = None,
        blacklisted_deployments: Optional[List[int]] = None,
        n_images_seq: int = 5,
        max_interval: int = 90,
        uploaded_media_ids: Optional[set] = None,
        excluded_media_ids: Optional[set] = None,
        progress_callback: Optional[Callable] = None,
        max_workers: int = 1,
    ) -> List[Dict[str, Any]]:
        """Estimate the number of images to upload per deployment.

        Applies the same selection logic as upload_collection and returns one
        row per deployment with deploymentID, locationID, _id and estimated_photos.
        """
        all_deployments = self.trapper.deployments.get_all(query={"classification_project": classification_project})
        depl_map = {
            item.pk: item
            for item in all_deployments.results
            if item.pk is not None and item.deployment_id
        }

        if deployments is None:
            collection_obj = self.trapper.collections.get_by_id(collection)
            if collection_obj.results:
                prefix = f"{collection_obj.results[0].name}-".lower()
                deployment_pks = [pk for pk, d in depl_map.items() if d.deployment_id.lower().startswith(prefix)]
            else:
                deployment_pks = list(depl_map.keys())
        else:
            deployment_pks = list(deployments)

        if blacklisted_deployments:
            blacklist = set(blacklisted_deployments)
            deployment_pks = [pk for pk in deployment_pks if pk not in blacklist]

        def _process_deployment(pk: int) -> Optional[Dict[str, Any]]:
            depl = depl_map.get(pk)
            if depl is None:
                return None
            self._notify(progress_callback, "estimating", state="start",
                         description=f"Estimating deployment {depl.deployment_id}...")

            media = self.trapper.media.get_by_collection(
                classification_project, collection,
                {"deployment": pk, "private_human": "False", "private_vehicle": "False"},
            )
            observations = self.trapper.observations.results.get_by_collection(
                classification_project, collection, query={"deployment": pk}
            )
            filtered_obs = [
                obs for obs in observations.results
                if obs.observationType and obs.observationType != "unclassified"
            ]
            obs_list = TrapperClassificationResultsList(
                results=filtered_obs,
                pagination=Pagination(page=1, page_size=len(filtered_obs), pages=1, count=len(filtered_obs)),
            )
            media_map = self._merge_media_and_observations(media, obs_list)
            public_media_map = {mid: entry for mid, entry in media_map.items() if entry.filePublic}

            if uploaded_media_ids:
                public_media_map = {mid: e for mid, e in public_media_map.items() if int(mid) not in uploaded_media_ids}
            if excluded_media_ids:
                public_media_map = {mid: e for mid, e in public_media_map.items() if int(mid) not in excluded_media_ids}

            sequences = self._generate_zoo_images_from_media_map(
                public_media_map, max_interval, n_images_seq, filter_middle_humans=True
            )
            n_sequences = len(sequences)
            estimated_photos = sum(len(seq) for seq in sequences)

            durations = [
                (seq[-1]["timestamp"] - seq[0]["timestamp"]).total_seconds()
                for seq in sequences if len(seq) >= 2
            ]
            seq_duration_mean = round(statistics.mean(durations), 1) if durations else 0.0
            seq_duration_max = round(max(durations), 1) if durations else 0.0
            seq_duration_min = round(min(durations), 1) if durations else 0.0
            seq_duration_variance = round(statistics.variance(durations), 1) if len(durations) >= 2 else 0.0

            self._notify(progress_callback, "estimating", state="end",
                         description=f"Deployment {depl.deployment_id}: {estimated_photos} images in {n_sequences} sequences")
            return {
                "deploymentID": depl.deployment_id,
                "locationID": depl.location_id,
                "_id": pk,
                "total_media": len(media_map),
                "n_sequences": n_sequences,
                "estimated_photos": estimated_photos,
                "seq_duration_mean_s": seq_duration_mean,
                "seq_duration_max_s": seq_duration_max,
                "seq_duration_min_s": seq_duration_min,
                "seq_duration_variance_s2": seq_duration_variance,
            }

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {executor.submit(_process_deployment, pk): pk for pk in deployment_pks}
            rows = [r for f in as_completed(futures) if (r := f.result()) is not None]

        rows.sort(key=lambda r: r["deploymentID"])
        return rows

    def analyze_sequences(
        self,
        collection: int,
        classification_project: int,
        deployments: Optional[List[int]] = None,
        blacklisted_deployments: Optional[List[int]] = None,
        n_images_seq: int = 5,
        max_interval: int = 90,
        progress_callback: Optional[Callable] = None,
        max_workers: int = 1,
    ) -> List[Dict[str, Any]]:
        """Return one row per sequence with media IDs, dates and duration.

        Applies the same filtering and sequence-splitting logic as estimate_upload
        but returns sequence-level detail instead of per-deployment aggregates.
        """
        all_deployments = self.trapper.deployments.get_all(query={"classification_project": classification_project})
        depl_map = {
            item.pk: item
            for item in all_deployments.results
            if item.pk is not None and item.deployment_id
        }

        if deployments is None:
            collection_obj = self.trapper.collections.get_by_id(collection)
            if collection_obj.results:
                prefix = f"{collection_obj.results[0].name}-".lower()
                deployment_pks = [pk for pk, d in depl_map.items() if d.deployment_id.lower().startswith(prefix)]
            else:
                deployment_pks = list(depl_map.keys())
        else:
            deployment_pks = list(deployments)

        if blacklisted_deployments:
            blacklist = set(blacklisted_deployments)
            deployment_pks = [pk for pk in deployment_pks if pk not in blacklist]

        def _process_deployment(pk: int) -> List[Dict[str, Any]]:
            depl = depl_map.get(pk)
            if depl is None:
                return []
            self._notify(progress_callback, "analyzing", state="start",
                         description=f"Analyzing deployment {depl.deployment_id}...")

            media = self.trapper.media.get_by_collection(
                classification_project, collection,
                {"deployment": pk, "private_human": "False", "private_vehicle": "False"},
            )
            observations = self.trapper.observations.results.get_by_collection(
                classification_project, collection, query={"deployment": pk}
            )
            filtered_obs = [
                obs for obs in observations.results
                if obs.observationType and obs.observationType != "unclassified"
            ]
            obs_list = TrapperClassificationResultsList(
                results=filtered_obs,
                pagination=Pagination(page=1, page_size=len(filtered_obs), pages=1, count=len(filtered_obs)),
            )
            media_map = self._merge_media_and_observations(media, obs_list)
            public_media_map = {mid: entry for mid, entry in media_map.items() if entry.filePublic}

            rows_converted = self._convert_timestamps_from_media_map(public_media_map)
            grouped = self._group_by_deployment(rows_converted)

            seq_rows = []
            for group in grouped.values():
                ordered = sorted(group, key=lambda x: x["timestamp"])
                sequences: List[List[Dict]] = []
                current_seq = [ordered[0]]
                for prev, curr in zip(ordered, ordered[1:]):
                    delta = (curr["timestamp"] - prev["timestamp"]).total_seconds()
                    if delta <= max_interval:
                        current_seq.append(curr)
                    else:
                        sequences.append(current_seq)
                        current_seq = [curr]
                sequences.append(current_seq)
                sequences = self._filter_human_media_from_middle_sequences(sequences)

                for seq_n, seq in enumerate(sequences, start=1):
                    seq_sorted = sorted(seq, key=lambda x: x["timestamp"])
                    first_ts = seq_sorted[0]["timestamp"]
                    last_ts = seq_sorted[-1]["timestamp"]
                    duration = (last_ts - first_ts).total_seconds()
                    sampled = self._sample_sequence(seq_sorted, n_images_seq)
                    media_ids = "|".join(str(img["mediaID"]) for img in sampled)
                    seq_rows.append({
                        "deploymentID": depl.deployment_id,
                        "locationID": depl.location_id,
                        "_id": pk,
                        "sequence_n": seq_n,
                        "total_images": len(seq_sorted),
                        "media_ids": media_ids,
                        "first_date": first_ts.isoformat(),
                        "last_date": last_ts.isoformat(),
                        "duration_s": round(duration, 1),
                    })

            self._notify(progress_callback, "analyzing", state="end",
                         description=f"Deployment {depl.deployment_id}: {len(seq_rows)} sequences")
            return seq_rows

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {executor.submit(_process_deployment, pk): pk for pk in deployment_pks}
            all_rows: List[Dict[str, Any]] = []
            for f in as_completed(futures):
                all_rows.extend(f.result())

        all_rows.sort(key=lambda r: (r["deploymentID"], r["sequence_n"]))
        return all_rows

    def _build_expected_media_ids(
        self,
        collection: int,
        classification_project: int,
        deployments: Optional[List[int]] = None,
        blacklisted_deployments: Optional[List[int]] = None,
        n_images_seq: int = 5,
        max_interval: int = 90,
        progress_callback: Optional[Callable] = None,
    ) -> set[int]:
        """Return the set of media_ids that Trapper expects to be in Zooniverse.

        Follows the same selection logic as upload_collection: public media only,
        classified observations only (non-unclassified), grouped into sequences,
        humans filtered from middle frames.
        """
        deployments = list(deployments) if deployments is not None else None

        if deployments is None:
            depl = self.trapper.deployments.get_all(query={"classification_project": classification_project})
            depl = {
                item.pk: item.deployment_id
                for item in depl.results
                if item.pk is not None and item.deployment_id
            }
            collection_obj = self.trapper.collections.get_by_id(collection)
            if collection_obj.results:
                collection_obj = collection_obj.results[0]
                prefix = f"{collection_obj.name}-".lower()
                deployments = [pk for pk, name in depl.items() if name.lower().startswith(prefix)]

        deployments = deployments or []

        if blacklisted_deployments:
            blacklist = set(blacklisted_deployments)
            deployments = [dep for dep in deployments if dep not in blacklist]

        expected: set[int] = set()

        for deployment in deployments:
            self._notify(progress_callback, "getting_media", state="start",
                         description=f"Getting media for deployment {deployment}...")
            media = self.trapper.media.get_by_collection(
                classification_project, collection,
                {"deployment": deployment, "private_human": "False", "private_vehicle": "False"},
            )
            self._notify(progress_callback, "getting_media", state="end",
                         set_total=True, total=len(media.results))

            self._notify(progress_callback, "getting_observations", state="start",
                         description=f"Getting observations for deployment {deployment}...")
            observations = self.trapper.observations.results.get_by_collection(
                classification_project, collection, query={"deployment": deployment}
            )
            self._notify(progress_callback, "getting_observations", state="end",
                         set_total=True, total=len(observations.results))

            filtered = [
                obs for obs in observations.results
                if obs.observationType and obs.observationType != "unclassified"
            ]
            observations = TrapperClassificationResultsList(
                results=filtered,
                pagination=Pagination(page=1, page_size=len(filtered), pages=1, count=len(filtered)),
            )

            media_map = self._merge_media_and_observations(media, observations)
            public_media_map = {mid: entry for mid, entry in media_map.items() if entry.filePublic}
            sequences = self._generate_zoo_images_from_media_map(
                public_media_map, max_interval, n_images_seq, filter_middle_humans=True
            )
            for seq in sequences:
                for item in seq:
                    expected.add(item["mediaID"])

        return expected

    def missing_media_id(
        self,
        subjects_csv: Path,
        collection: int,
        classification_project: int,
        subject_set_id: Optional[int] = None,
        deployments: Optional[List[int]] = None,
        blacklisted_deployments: Optional[List[int]] = None,
        n_images_seq: int = 5,
        max_interval: int = 90,
        progress_callback: Optional[Callable] = None,
    ) -> set[int]:
        """Return media_ids that Trapper expects to be in Zooniverse but are absent from the CSV.

        Uses the same selection logic as upload_collection to build the expected set,
        then compares it against the media_ids found in the subjects export CSV.
        """
        expected = self._build_expected_media_ids(
            collection, classification_project,
            deployments, blacklisted_deployments,
            n_images_seq, max_interval,
            progress_callback,
        )
        uploaded_set = set(self.uploaded_media_id(subjects_csv, subject_set_id).keys())
        return expected - uploaded_set

    def validate_subject_set(
        self,
        subjects_csv: Path,
        collection: int,
        classification_project: int,
        subject_set_id: Optional[int] = None,
        deployments: Optional[List[int]] = None,
        blacklisted_deployments: Optional[List[int]] = None,
        n_images_seq: int = 5,
        max_interval: int = 90,
        progress_callback: Optional[Callable] = None,
    ) -> dict:
        """Compare what Trapper expects to upload against what is in a subjects export CSV.

        Returns a dict with keys:
          - expected (set[int]): media_ids that should be in the subject set
          - uploaded (dict[int, int]): media_id → subject_id from the CSV
          - missing (set[int]): expected but absent from the CSV
          - extra (set[int]): present in the CSV but not expected from Trapper
          - duplicated (dict[int, list[int]]): media_id → [subject_ids] for media uploaded more than once
          - unmatched (list[int]): subject_ids with no extractable media_id
          - metadata_issues (list[dict]): subjects whose metadata failed validation
        """
        expected = self._build_expected_media_ids(
            collection, classification_project,
            deployments, blacklisted_deployments,
            n_images_seq, max_interval,
            progress_callback,
        )

        uploaded = self.uploaded_media_id(subjects_csv, subject_set_id)
        uploaded_set = set(uploaded.keys())

        duplicated = self.duplicated_media_id(subjects_csv, subject_set_id, progress_callback)
        unmatched = self.unmatched_subject_id(subjects_csv, subject_set_id, progress_callback)
        all_metadata = self.check_subject_metadata(subjects_csv, subject_set_id, self.trapper, progress_callback)

        return {
            "expected": expected,
            "uploaded": uploaded,
            "missing": expected - uploaded_set,
            "extra": uploaded_set - expected,
            "duplicated": duplicated,
            "unmatched": unmatched,
            "metadata_issues": [r for r in all_metadata if r["issues"]],
        }

    REQUIRED_METADATA_FIELDS: tuple[str, ...] = (
        "external_id", "preview", "link", "thumbnail", "origin", "license", "image_name",
    )

    def check_subject_metadata(
        self,
        csv_path: Path,
        subject_set_id: Optional[int] = None,
        trapper_client: Optional["TrapperClient"] = None,
        progress_callback: Optional[Callable] = None,
    ) -> list[dict]:
        """Validate metadata for each subject in a Zooniverse subjects export.

        When *trapper_client* is provided the expected metadata is built with
        :meth:`_build_metadata_from_trapper` and every field except ``image_name``
        is compared against the actual value stored in the CSV.  Without it only
        presence of required fields and media_id extractability are checked.

        Returns a list of dicts with keys:
          - subject_id (int)
          - subject_set_id (str)
          - media_id (int | None)
          - issues (list[str]) — empty when the subject passes all checks
        """
        task_name = "checking_metadata"

        # Collect all rows upfront so we can report a meaningful total.
        rows = list(self._iter_subject_export_rows(csv_path, subject_set_id))
        total = len(rows)

        self._notify(
            progress_callback,
            task_name, "start", 0, total,
            f"Checking metadata for {total} subjects…", True,
        )

        results: list[dict] = []
        for row in rows:
            try:
                sid = int(row.get("subject_id", "").strip())
            except (ValueError, TypeError):
                self._notify(progress_callback, task_name, "running", 1)
                continue

            ssid = row.get("subject_set_id", "")
            raw = row.get("metadata", "")
            issues: list[str] = []

            try:
                metadata: dict = json.loads(raw) if raw else {}
            except (json.JSONDecodeError, TypeError):
                results.append({"subject_id": sid, "subject_set_id": ssid, "media_id": None,
                                 "issues": ["metadata is not valid JSON"]})
                self._notify(
                    progress_callback, task_name, "running", 1,
                    item_name=str(sid), item_status="fail",
                    item_description="metadata is not valid JSON",
                )
                continue

            missing = [f for f in self.REQUIRED_METADATA_FIELDS if not metadata.get(f)]
            if missing:
                issues.append(f"missing fields: {', '.join(missing)}")

            media_id = self._media_id_from_subject_row(row)
            if media_id is None:
                issues.append("no media_id extractable from external_id or origin")
            elif trapper_client is not None:
                expected = self._build_metadata_from_trapper(trapper_client, media_id, "")
                for field, expected_value in expected.items():
                    if field == "image_name":
                        continue
                    actual = metadata.get(field, "")
                    if actual != expected_value:
                        issues.append(f"{field}: expected '{expected_value}', got '{actual}'")

            results.append({
                "subject_id": sid,
                "subject_set_id": ssid,
                "media_id": media_id,
                "issues": issues,
            })

            item_status = "fail" if issues else "end"
            item_desc = "; ".join(issues) if issues else "OK"
            self._notify(
                progress_callback, task_name, "running", 1,
                item_name=str(sid), item_status=item_status,
                item_description=item_desc,
            )

        self._notify(progress_callback, task_name, "end", 0)

        return results