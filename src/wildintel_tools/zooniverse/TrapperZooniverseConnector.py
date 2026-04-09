from collections import defaultdict
from datetime import datetime, time, timezone
from pathlib import Path
from typing import List, Dict, Tuple, Any, Optional, Callable, Literal
import logging, os
import tempfile
import re
from urllib.error import URLError, HTTPError

from pydantic import BaseModel, validator, HttpUrl
from tenacity import stop_after_attempt, wait_fixed, before_sleep_log, retry, RetryError
from trapper_client import Schemas
from trapper_client.TrapperClient import TrapperClient
from trapper_client.Schemas import TrapperMediaList, TrapperObservationList, Pagination, \
    TrapperObservationResultsTrapper, TrapperClassificationResultsList

from wildintel_tools.zooniverse.AnnotationsVoter import AnnotationsVoter
from wildintel_tools.zooniverse.AnnotationsExtractor import AnnotationsExtractor
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

        self.logger.info(" | ".join(log_parts))

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

            # private_* in query is for obtaining url media for non-public media,
            # de los media obtengo las url de la imágenes
            media :TrapperMediaList = self.trapper.media.get_by_collection(
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

            media_map=self._merge_media_and_observations(media,observations)
            public_media_map = {media_id: entry for media_id, entry in media_map.items() if entry.filePublic}

            if len(media_map.keys()) == 0:
                self.logger.debug(f"No valid observations found for collection {collection} and classification project {classification_project}.")

            self._notify(progress_callback, "getting_url", state="end", set_total=True, total=len(public_media_map.keys()))
            self._notify(progress_callback, "preparing_sequences", state="start", description=f"Preparing sequences...")

            sequences = self._generate_zoo_images_from_media_map(public_media_map, max_interval, n_images_seq,
                                                             filter_middle_humans=True)
            self._notify(progress_callback, "preparing_sequences", state="end", set_total=True, total=len(sequences))

            total = sum(len(sequence) for sequence in sequences)

            # Crear SubjectSet antes de comenzar
            if dry_run:
                self.logger.info(f"[DRY-RUN] Skipping subjectset creation: '{subjectset_name}'")
                subjectset = None
            else:
                self.logger.debug(f"Creando SubjectSet {subjectset_name} en Zooniverse")
                subjectset = self.zoo.subjectsets.create(subjectset_name)

            self._notify(progress_callback, "synchronizing_images", state="start",
                     description=f"Synchronizing {total} images...",
                    total=total, set_total=True)

            with (tempfile.TemporaryDirectory() as temp_dir):
                for idx, seq in enumerate(sequences):
                    for media in seq:
                        media_id = media['mediaID']
                        name = self._get_zoo_filename(media)
                        local_path = os.path.join(temp_dir, name)

                        self._notify(progress_callback, "synchronizing_images"
                                           , state="running"
                                           , advance=0
                                           , item_description=f"↓↓ Downloading media to {str(Path(temp_dir) / name)}"
                                           , item_name=f"{media_id}"
                                           , item_status="start")

                        try:
                            if dry_run:
                                self.logger.info(f"[DRY-RUN] Skipping download of media {media_id}")
                                self._notify(
                                    progress_callback,
                                    "synchronizing_images",
                                    state="running",
                                    advance=0,
                                    item_description=f"[DRY-RUN] Simulated download of {str(Path(temp_dir) / name)}",
                                    item_name=f"{media_id}",
                                    item_status="end",
                                )
                                report.add_success(f"{media_id}@media", "download_simulated", **{"path": local_path})
                            else:
                                self._download_image_safe(str(media['filePath']), str(Path(temp_dir) / name),
                                                          attempts=attempts, delay_seconds=delay)
                                self._notify(
                                    progress_callback,
                                    "synchronizing_images",
                                    state="running",
                                    advance=0,
                                    item_description=f"↓↓ Downloading media to {str(Path(temp_dir) / name)}",
                                    item_name=f"{media_id}",
                                    item_status="end",
                                )
                                report.add_success(f"{media_id}@media", "download", **{"path":local_path})

                            if dry_run:
                                self.logger.info(f"[DRY-RUN] Skipping upload of media {media_id} to Zooniverse")
                                self._notify(
                                    progress_callback,
                                    "synchronizing_images",
                                    state="running",
                                    advance=1,
                                    item_description=f"[DRY-RUN] Simulated upload to Zooniverse subject {subjectset_name}",
                                    item_name=f"{media_id}",
                                    item_status="end",
                                )
                                report.add_success(f"{media_id}@media", "upload_simulated", **{"subject_id": "dry-run", "path": local_path})
                            else:
                                self._notify(
                                    progress_callback,
                                    "synchronizing_images",
                                    state="running",
                                    advance=0,
                                    item_description=f"↑↑↑ Uploading media to Zooniverse subject {subjectset_name}",
                                    item_name=f"{media_id}",
                                    item_status="start",
                                )
                                #origin = f"{self.trapper.base_url}:media:{media_id}"
                                subject_metadata = {
                                    # "origin": origin
                                    "external_id": f"{self.trapper.base_url}:media:{media_id}",
                                    "preview": f"{self.trapper.base_url}storage/resource/media/{media_id}/pfile/",
                                    "link": f"{self.trapper.base_url}storage/resource/media/{media_id}/file/",
                                    "thumbnail": f"{self.trapper.base_url}storage/resource/media/{media_id}/tfile/",
                                    "origin": f"{self.trapper.base_url}",
                                    "license": "http://creativecommons.org/licenses/by-nc/4.0/legalcode",
                                    "image_name": media["fileName"],
                                }

                                subject = self.zoo.subjects.create(
                                    local_path,
                                    subjectset,
                                    subject_metadata,
                                    max_attempts_per_subject,
                                    delay_seconds_per_subject,
                                    skip_if_exists=False
                                )

                                report.add_success(f"{media_id}@media", "upload",
                                                  **{"subject_id": subject.id, "path": local_path})

                                if os.path.exists(local_path):
                                    os.remove(local_path)
                                    self.logger.debug(f"Removed temporary file {local_path}")

                                self._notify(
                                    progress_callback,
                                    "synchronizing_images",
                                    state="running",
                                    advance=1,
                                    item_description=f"↑↑↑ Uploading media to Zooniverse subject {subjectset_name}. {subject.id}",
                                    item_name=f"{media_id}",
                                    item_status="end",
                                )

                        except DownloadException as e:
                            self._notify(
                                progress_callback,
                                "synchronizing_images",
                                state="running",
                                advance=1,
                                item_description="Downloading media ↓",
                                item_name=f"{media_id}",
                                item_status="fail",
                            )
                            report.add_error(f"{media_id}@media", "download", str(e),
                                            **{"path":str(media['filePath'])})
                        except UploadingException as e:
                            self._notify(
                                    progress_callback,
                                    "synchronizing_images",
                                    state="running",
                                    advance=1,
                                    item_description=f"Uploading media {subject.id} ↑",
                                    item_name=f"{media_id}",
                                    item_status="false",
                                )
                            report.add_error(f"{media_id}@media", "upload", str(e),
                                            **{"path": local_path})
                        finally:
                            if os.path.exists(local_path):
                                os.remove(local_path)

            self._notify(progress_callback, "synchronizing_images", state="end")
        report.finish()
        return report

    def update_subject_metadata(
        self,
        subjectset_id: int,
        classification_project: int,
        progress_callback: Optional[Callable[[str, str, int, Optional[int], Optional[str], bool, Optional[str], Optional[str]], None]] = None,
        dry_run: bool = False,
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

        self._notify(
            progress_callback,
            "getting_subjects",
            state="start",
            description=f"Getting subjects from subjectset {subjectset_id}...",
        )
        subjects = self.zoo.subjects.get_by_subjectset(subjectset_id)
        self._notify(
            progress_callback,
            "getting_subjects",
            state="end",
            set_total=True,
            total=len(subjects),
        )

        self._notify(
            progress_callback,
            "updating_subjects",
            state="start",
            description=f"Updating metadata for {len(subjects)} subjects...",
            total=len(subjects),
            set_total=True,
        )

        for subject in subjects:
            sid = str(getattr(subject, "id", "unknown"))
            try:
                filename = self._extract_subject_filename(subject)
                if not filename:
                    raise ValueError("filename not found in subject metadata")

                media_id = self._extract_media_id_from_filename(filename)
                if media_id is None:
                    raise ValueError(f"could not extract media_id from filename '{filename}'")

                self._notify(
                    progress_callback,
                    "updating_subjects",
                    state="running",
                    advance=0,
                    item_name=sid,
                    item_status="start",
                    item_description=f"Resolving media {media_id} from Trapper",
                )

                media_list = self.trapper.media.get_by_media_id(classification_project, media_id)
                media_results = getattr(media_list, "results", []) or []
                if not media_results:
                    raise ValueError(f"no Trapper media found for media_id {media_id}")

                media = media_results[0]
                subject_metadata = self._build_subject_metadata(media_id, getattr(media, "fileName", filename))

                if dry_run:
                    report.add_success(f"{sid}@subject", "update_metadata_simulated", **{"media_id": media_id})
                else:
                    self.zoo.subjects.update_one_metadata(subject, subject_metadata)
                    report.add_success(f"{sid}@subject", "update_metadata", **{"media_id": media_id})

                self._notify(
                    progress_callback,
                    "updating_subjects",
                    state="running",
                    advance=1,
                    item_name=sid,
                    item_status="end",
                    item_description=f"Metadata updated from media {media_id}",
                )
            except Exception as e:
                report.add_error(f"{sid}@subject", "update_metadata", str(e))
                self._notify(
                    progress_callback,
                    "updating_subjects",
                    state="running",
                    advance=1,
                    item_name=sid,
                    item_status="fail",
                    item_description=str(e),
                )

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
          observation_map: Path = None,
          species_map: Path = None,
  ):
      report = Report(f"Annotation from  {subjectset_id} to  classification project {cp_id}", type="DownloadAnnotations" )
      self.logger.debug(f"Getting annotations for collection {cp_id} linked to {cp_id} classification project")
      self.zoo.connect()
      annotations: SubjectSetResults = self.zoo.annotations.get_by_workflow(wf_id)

      if len(annotations.workflows) == 0:
          raise ValueError(f"No annotations found for subjectset {subjectset_id}")

      self.logger.debug(f"Obtained {len(annotations.workflows)} workflows linked to subjectset {subjectset_id}")

      wf = self.zoo.workflows.get_by_id(wf_id)
      wf_key = f"{wf.id}:{wf.display_name}:{wf.version}"
      #if wf_key not in annotations.workflows:
      #    raise ValueError(f"Workflow key {wf_key} not found in annotations")
      #annotations: WorkflowData = annotations.workflows[wf_key]

      #annotations: WorkflowData = next(iter(annotations.workflows.values()))
      #print(annotations.data.keys())
      #print(len(annotations.data))
      #print(annotations.summary)

      #self.logger.debug(
      #    f"Obtained annotations fp{len(annotations.data)} annotations for subjectset {subjectset_id} and workflow {wf_id}"
      #)

      query = {"camtrapdp": "False"}

      trapper_observations : Schemas.TrapperClassificationResultsList = self.trapper.observations.results.get_by_collection(cp_id, collection_id, query=query)

      self.logger.debug(
          f"Obtained {len(trapper_observations.results)} observations for collection {collection_id} and research project {cp_id}")

      (extractor, voter) = self._get_extrator_vote(wf.id)

      flat_results : List[TrapperObservationResultsTrapper]= []

      for wf_fullid, wf_data in annotations.workflows.items():
          # for each subject-media annotation, extract observations and vote

          for key, user_opinions in wf_data.data.items():
              try:
                  subject_id, media_id = key.split(":")
                  self.logger.debug(f"Obteniendo las trapper observations para media {media_id} vinculado al subject {subject_id}")

                  all_media_observations: List[TrapperObservationResultsTrapper] =\
                          [o for o in trapper_observations.results if str(o.mediaID) == media_id]

                  # fake block
                  #if False and len(all_media_observations) == 0:
                  if len(all_media_observations) == 0:
                      self.logger.debug(f"No se han encontrado observaciones en Trapper para media {media_id} ")
                      report.add_error(
                          f"subject:{subject_id}",
                          "get_observations",
                          f"No observations found for resource {media_id} in Trapper classification project {cp_id}"
                      )
                  else:
                      all_media_observations_ids = list({obj.id for obj in all_media_observations if obj.id is not None})
                      # fake block
                      """
                      all_media_observations_ids = [10]
                      inst = TrapperObservationResultsTrapper(
                            _id="10",
                            observationID=1,
                            deploymentID="DEP-001",
                            mediaID=10,
                            eventID="EVT-001",
                            eventStart="2024-05-01T12:00:00",
                            eventEnd="2024-05-01T12:00:00",
                            observationLevel="image",
                            observationType="animal",
                            cameraSetupType="standard",
                            scientificName="Vulpes vulpes",
                            count=1,
                            lifeStage="adult",
                            sex="unknown",
                            behavior="standing",
                            individualID=None,
                            individualPositionRadius=None,
                            individualPositionAngle=None,
                            individualSpeed=None,
                            classificationMethod="AI",
                            classifiedBy="model_v1",
                            classificationTimestamp="2024-05-01T12:00:00",
                            classificationProbability=0.92,
                            observationTags="fox,night",
                            observationComments="Detected by model",
                            # Campos adicionales de la clase extendida
                            countNew=1,
                            englishName="Red fox",
                            bboxes=[[100.0, 150.0, 300.0, 400.0]],  # x1, y1, x2, y2
                        )
                      all_media_observations = [inst]
                      """
                      # end fake block
                      # Zooniverse decision
                      self.logger.debug(f"Invocando al extractor con {user_opinions}")
                      opinions = extractor.run(user_opinions)
                      self.logger.debug(f"Invocando al voter con {opinions}")
                      decisions : List[Zoo2TrapperObservation] = voter.run(opinions)
                      if not decisions:
                          report.add_error(f"subject:{subject_id}",
                                             "getting_decision",
                                             f"No decision found for subject {subject_id}")
                          self.logger.debug(f"No hay decision para subject_id {subject_id}")
                          continue
                      self.logger.debug(f"Asignando las decisiones {decisions} a las classifications en trapper {all_media_observations_ids}")
                      for decision in decisions:
                          for id in all_media_observations_ids:
                              new_obs: TrapperObservationResultsTrapper = all_media_observations[0].copy(
                                    update={
                                        **decision.model_dump(),
                                        "_id": id,
                                        "bboxes": None,
                                        "classificationTimestamp": datetime.now(timezone.utc),
                                        "classifiedBy": self.trapper.user_name,
                                        "classificationMethod": "human",
                                        "observationComments": f"Automatically classified by Zooniverse in workflow {wf_key} for subject {subject_id}",
                                    }
                              )
                              report.add_success(
                                    f"subject:{subject_id}",
                                    "getting_decision",
                                    f"Added an observation for resource {media_id} with {decision.scientificName}",
                              )

                              flat_results.append(new_obs)

              except Exception as e:
                self.logger.error("unknown", f"Error processing subject-media {key}: {e}")

          self.logger.debug(
            f"Generadas {len(flat_results)} observaciones para importar en Trapper por subject: "
          )

          # Guardar CSV si se indicó output_dir
          if output_dir:
            self.logger.debug(f"Saving observations to CSV in {output_dir}")
            self._trapper_observations_to_csv(flat_results,
                                              Path(output_dir),
                                                   ["observationType", "scientificName",
                                                            "count", "classifiedBy","classificationMethod",
                                                            "observationComments",
                                                            "_id"
                                                    ])

      return report

        #TODO subir usando el browser

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

    def _build_subject_metadata(self, media_id: int, image_name: str) -> Dict[str, Any]:
        base_url = str(self.trapper.base_url)
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

    def _get_extrator_vote(self, workflow_id) -> Tuple[AnnotationsExtractor, AnnotationsVoter]:
        import importlib

        extractor_class_name = f"Workflow{workflow_id}AnnotationExtractor"
        voter_class_name = f"Workflow{workflow_id}AnnotationsVoter"

        extractor_module = importlib.import_module(f"trapper_zooniverse.AnnotationsExtractor.{extractor_class_name}")
        voter_module = importlib.import_module(f"trapper_zooniverse.AnnotationsVoter.{voter_class_name}")

        ExtractorClass = getattr(extractor_module, extractor_class_name)
        VoterClass = getattr(voter_module, voter_class_name)

        return ExtractorClass, VoterClass

    @retry(
        stop=stop_after_attempt(5),
        wait=wait_fixed(60),
        reraise=False,
        before_sleep=before_sleep_log(logging.getLogger(__name__), logging.WARNING),
    )
    def _download_image(self, url: str, dest_path: str, attempts=5, delay_seconds=60) -> bool:
        """Descarga una imagen desde una URL con reintentos."""
        urllib.request.urlretrieve(url, dest_path)
        return True

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
