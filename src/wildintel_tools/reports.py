"""
Module for recording and exporting the results of media processing or upload operations.

Defines:
    - ReportStatus: Enumeration of possible report outcomes.
    - Report: Dataclass for recording detailed results (successes and errors)
      and exporting them to YAML.
"""
import atexit
import logging
import os
import time
import tempfile
import threading
from dataclasses import dataclass, field, asdict
from datetime import datetime
from enum import Enum
from pathlib import Path
import json
import yaml
from typing import Any, cast
from wildintel_tools.ui.typer.i18n import _

logger = logging.getLogger(__name__)


class ReportWriter:
    """
    Utility class to export Report instances to YAML files.
    """

    @staticmethod
    def to_yaml(report: "Report", path: Path | None) -> str:
        """
        Writes the given Report instance to a YAML file.

        :param report: The Report object to serialize.
        :param path: Destination path for the YAML file. If None, only returns the string.
        """

        def convert(obj):
            if isinstance(obj, dict):
                return {k: convert(v) for k, v in obj.items()}
            elif isinstance(obj, list):
                return [convert(v) for v in obj]
            elif isinstance(obj, Path):
                return str(obj)
            else:
                return obj

        data = asdict(report)
        # Exclude internal/runtime fields from the serialized output.
        # _lock is assigned via object.__setattr__ so asdict never includes it,
        # but the rest must still be removed.
        for key in ("autosave_path", "autosave_every", "autosave_interval_secs",
                    "_pending_saves", "_last_autosave_time"):
            data.pop(key, None)
        data = convert(data)
        yaml_str = yaml.safe_dump(data, sort_keys=False, allow_unicode=True)

        if path is not None:
            with open(path, "w", encoding="utf-8") as f:
                f.write(yaml_str)

        return yaml_str


class ReportReader:
    """
    Utility class to load Report instances from YAML files.
    """

    @classmethod
    def from_yaml(cls, path: Path) -> "Report":
        """
        Loads a Report instance from a YAML file.

        :param path: Path to the YAML file.
        :return: A Report instance populated with the file content.
        """
        with open(path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)

        # Reconstruct datetime fields if they were serialized as strings
        for key in ("start_time", "end_time"):
            val = data.get(key)
            if isinstance(val, str):
                try:
                    data[key] = datetime.fromisoformat(val)
                except ValueError:
                    pass

        # Runtime fields are not stored in YAML; remove them so __post_init__ reinitialises them
        for key in ("autosave_path", "autosave_every", "autosave_interval_secs",
                    "_pending_saves", "_last_autosave_time"):
            data.pop(key, None)

        return Report(**data)


class ReportStatus(str, Enum):
    """
    Enumeration of possible states of a report.

    Each value represents the global outcome of a processing or upload operation:

    - ``success``: All actions completed successfully.
    - ``failed``: All actions failed.
    - ``partial``: Some actions succeeded, others failed.
    - ``empty``: No actions recorded.

    This class inherits from :class:`str` and :class:`Enum` so its members behave
    both as strings and as enumeration values.
    """
    SUCCESS = "success"
    FAILED = "failed"
    PARTIAL = "partial"
    EMPTY = "empty"


@dataclass()
class Report:
    """
    Records the results of a media upload or processing operation.

    Each identifier (e.g., image, subject, or file) can have multiple actions
    with associated successes or errors. The report tracks all these events,
    computes an overall status, and can export/import its contents as YAML.

    Thread-safe: all public methods are protected by an internal ``RLock``.

    :ivar title: Descriptive title of the report.
    :vartype title: str
    :ivar start_time: Time when the report was created or started.
    :vartype start_time: datetime
    :ivar end_time: Time when the report was finished, or ``None`` if still active.
    :vartype end_time: datetime | None
    :ivar errors: Map of identifiers to lists of error entries.
    :vartype errors: dict[str, list[dict[str, Any]]]
    :ivar successes: Map of identifiers to lists of success entries.
    :vartype successes: dict[str, list[dict[str, Any]]]
    :ivar autosave_every: Number of additions between autosave writes. Default 1 (save every time).
        Must be >= 1. Set to a higher value to reduce I/O.
    :vartype autosave_every: int
    :ivar autosave_interval_secs: Minimum seconds between autosave writes. Default 0 (disabled).
        An autosave is triggered when *either* ``autosave_every`` or ``autosave_interval_secs``
        threshold is reached, whichever comes first.
    :vartype autosave_interval_secs: float
    """
    title: str
    type: str = "generic"
    start_time: datetime = field(default_factory=datetime.now)
    end_time: datetime | None = None
    autosave_path: Path | None = field(default=None, repr=False, compare=False)
    autosave_every: int = field(default=1, repr=False, compare=False)
    autosave_interval_secs: float = field(default=0.0, repr=False, compare=False)

    errors: dict[str, list[dict[str, Any]]] = field(default_factory=dict)
    successes: dict[str, list[dict[str, Any]]] = field(default_factory=dict)

    # Internal counters — excluded from serialisation and equality checks
    _pending_saves: int = field(default=0, init=False, repr=False, compare=False)
    _last_autosave_time: float = field(default=0.0, init=False, repr=False, compare=False)
    # _lock is intentionally NOT a dataclass field so asdict() never tries to
    # serialise or deepcopy it. It is injected in __post_init__ via object.__setattr__.

    def __post_init__(self):
        if self.autosave_every < 1:
            raise ValueError(f"autosave_every must be >= 1, got {self.autosave_every}")
        if self.autosave_interval_secs < 0:
            raise ValueError(f"autosave_interval_secs must be >= 0, got {self.autosave_interval_secs}")

        # Create the RLock outside the dataclass field machinery so asdict() never sees it.
        object.__setattr__(self, '_lock', threading.RLock())
        # Expose the type to static analysers without declaring a field.
        self._lock: threading.RLock = cast(threading.RLock, self.__dict__['_lock'])

        if self.autosave_path is None:
            tmp = tempfile.NamedTemporaryFile(delete=False, prefix="report_", suffix=".yaml")
            autosave_path: Path = Path(tmp.name)
            self.autosave_path = autosave_path
            tmp.close()
            # Remove the temp file when the process exits normally
            atexit.register(_cleanup_temp_file, autosave_path)

        self._last_autosave_time = time.monotonic()

    def __repr__(self) -> str:
        total_errors = sum(len(v) for v in self.errors.values())
        total_successes = sum(len(v) for v in self.successes.values())
        return (
            f"Report(title={self.title!r}, type={self.type!r}, "
            f"status={self.get_status().value!r}, "
            f"successes={total_successes}, errors={total_errors})"
        )

    @property
    def total_entries(self) -> int:
        """
        Total number of recorded entries (successes + errors).

        :return: Combined count of all success and error entries.
        :rtype: int
        """
        with self._lock:
            return (
                sum(len(v) for v in self.successes.values()) +
                sum(len(v) for v in self.errors.values())
            )

    def add_error(self, identifier: str, action: str, message: str, **extra) -> None:
        """
        Adds an error record for a specific identifier and action.

        :param identifier: Unique identifier (e.g., file name or ID).
        :param action: The operation that failed (e.g., ``"upload"``).
        :param message: A human-readable description of the error.
        :param extra: Optional keyword arguments with additional metadata.
        """
        with self._lock:
            entry = {k: v for k, v in {"action": action, "message": message, **extra}.items() if v is not None}
            self.errors.setdefault(identifier, []).append(entry)
            self._autosave()

    def add_success(self, identifier: str, action: str, message: str | None = None, **extra) -> None:
        """
        Adds a success record for a specific identifier and action.

        :param identifier: Unique identifier (e.g., file name or ID).
        :param action: The operation that succeeded (e.g., ``"upload"``).
        :param message: Optional message describing the success.
        :param extra: Optional keyword arguments with additional metadata.
        """
        with self._lock:
            entry = {k: v for k, v in {"action": action, "message": message, **extra}.items() if v is not None}
            self.successes.setdefault(identifier, []).append(entry)
            self._autosave()

    def finish(self) -> None:
        """Marks the report as finished by setting the end time and flushing any pending autosave."""
        with self._lock:
            self.end_time = datetime.now()
            self._flush()

    def get_status(self) -> ReportStatus:
        """
        Determines the overall report status based on recorded results.

        Uses actual entry counts to avoid false positives from empty lists.

        :return: One of ``"success"``, ``"failed"``, ``"partial"`` or ``"empty"``.
        :rtype: ReportStatus
        """
        with self._lock:
            has_errors = any(bool(v) for v in self.errors.values())
            has_successes = any(bool(v) for v in self.successes.values())

            if has_successes and not has_errors:
                return ReportStatus.SUCCESS
            elif has_errors and not has_successes:
                return ReportStatus.FAILED
            elif has_errors and has_successes:
                return ReportStatus.PARTIAL
            else:
                return ReportStatus.EMPTY

    def is_success(self) -> bool:
        """
        Checks if the report completed successfully (no errors, at least one success).

        :return: ``True`` if the report status is :data:`ReportStatus.SUCCESS`, otherwise ``False``.
        """
        return self.get_status() == ReportStatus.SUCCESS

    def is_failed(self) -> bool:
        """
        Checks if the report contains only errors and no successes.

        :return: ``True`` if the report status is :data:`ReportStatus.FAILED`, otherwise ``False``.
        """
        return self.get_status() == ReportStatus.FAILED

    def is_partial(self) -> bool:
        """
        Checks if the report contains both successes and errors.

        :return: ``True`` if the report status is :data:`ReportStatus.PARTIAL`, otherwise ``False``.
        """
        return self.get_status() == ReportStatus.PARTIAL

    def is_empty(self) -> bool:
        """
        Checks if the report contains no recorded actions.

        :return: ``True`` if the report status is :data:`ReportStatus.EMPTY`, otherwise ``False``.
        """
        return self.get_status() == ReportStatus.EMPTY

    def get_by_action(self, action: str) -> dict[str, dict[str, list[dict[str, Any]]]]:
        """
        Retrieves all entries (successes and errors) associated with a specific action.

        :param action: The action name to filter by (e.g., ``"upload"``).
        :return: A dictionary with two keys:
            - ``"errors"``: Matching error entries grouped by identifier.
            - ``"successes"``: Matching success entries grouped by identifier.
        """
        with self._lock:
            filtered_errors = {
                identifier: [err for err in entries if err.get("action") == action]
                for identifier, entries in self.errors.items()
                if any(err.get("action") == action for err in entries)
            }

            filtered_successes = {
                identifier: [succ for succ in entries if succ.get("action") == action]
                for identifier, entries in self.successes.items()
                if any(succ.get("action") == action for succ in entries)
            }

        return {"errors": filtered_errors, "successes": filtered_successes}

    def get_actions(self) -> list[str]:
        """
        Lists all distinct actions recorded in both errors and successes.

        :return: Sorted list of unique action names.
        """
        with self._lock:
            actions = set()
            for entries in list(self.errors.values()) + list(self.successes.values()):
                for e in entries:
                    if "action" in e and e["action"]:
                        actions.add(e["action"])
        return sorted(actions)

    def summary(self) -> str:
        """
        Generates a human-readable summary of the report, including timestamps,
        duration, total counts, and overall status.

        All values are captured atomically under the lock to ensure a consistent snapshot.

        :return: Multiline summary string suitable for console or log output.
        """
        # Capture all values under the lock so the snapshot is consistent across threads
        with self._lock:
            title = self.title
            start_time = self.start_time
            end_time = self.end_time
            total_errors = sum(len(v) for v in self.errors.values())
            total_successes = sum(len(v) for v in self.successes.values())
            # get_status also acquires _lock; since it's an RLock this is safe
            status = self.get_status()

        duration = (end_time - start_time).total_seconds() if end_time else None

        # Separate translatable labels from dynamic values so babel can extract them
        summary_lines = [
            f"{_('Report')} '{title}'",
            f"  {_('Start')}: {start_time}",
            f"  {_('End')}: {end_time or _('in progress')}",
            f"  {_('Status')}: {status}",
        ]
        if duration:
            summary_lines.append(f"  {_('Duration')}: {duration:.2f}s")
        summary_lines.append(f"  {_('Successes')}: {total_successes}")
        summary_lines.append(f"  {_('Errors')}: {total_errors}")

        return "\n".join(summary_lines)

    @classmethod
    def from_yaml(cls, filepath: Path) -> "Report":
        """
        Creates a :class:`Report` instance from a YAML file.

        :param filepath: Path to the YAML file containing the report data.
        :return: A new :class:`Report` instance populated with the loaded data.
        """
        return ReportReader.from_yaml(filepath)

    def to_yaml(self, filepath: Path | None = None) -> str:
        """
        Converts the current report to a YAML string and optionally saves it to a file.

        Serialisation happens inside the lock (for a consistent snapshot); the actual
        disk write happens outside the lock to minimise contention.

        :param filepath: If provided, the YAML will be written to this file.
            If ``None``, saves to the autosave path if available.
        :return: The YAML representation of the report.

        .. note::
           - Uses :func:`dataclasses.asdict` for serialization.
           - Runtime fields (``autosave_path``, ``autosave_every``, etc.) are excluded from output.
           - Preserves Unicode and does not sort keys.
        """
        with self._lock:
            save_path = filepath or self.autosave_path
            # Serialise to a string inside the lock (consistent snapshot), but don't
            # hold the lock during the actual disk write.
            yaml_str = ReportWriter.to_yaml(self, None)
            self._pending_saves = 0
            self._last_autosave_time = time.monotonic()

            # Determine whether to clean up the tmp autosave file
            cleanup_path: Path | None = None
            if filepath and self.autosave_path and self.autosave_path != filepath:
                cleanup_path = self.autosave_path
                self.autosave_path = None

        # Write to disk outside the lock
        if save_path is not None:
            with open(save_path, "w", encoding="utf-8") as f:
                f.write(yaml_str)

        if cleanup_path is not None:
            try:
                os.remove(str(cleanup_path))
            except FileNotFoundError:
                pass

        return yaml_str

    def extend(self, *others: "Report") -> None:
        """
        Merges the results of one or more reports into the current one.

        All reports (``self`` and every entry in ``others``) are locked during the
        merge to prevent race conditions. Locks are acquired in a consistent order
        (by ``id``) to prevent deadlocks.

        .. note::
            The pending autosave counters of the source reports are not affected.

        :param others: One or more Report instances whose records will be merged in.
        :raises TypeError: If any item in ``others`` is not a :class:`Report` instance.
        """
        for other in others:
            if not isinstance(other, Report):
                raise TypeError(f"All arguments must be Report instances, got {type(other)!r}")

        # Acquire all locks in a consistent order to prevent deadlock
        all_reports = [self] + list(others)
        sorted_reports = sorted(all_reports, key=id)
        locks = [r._lock for r in sorted_reports]

        def acquire_all(lock_list):
            """Recursively acquire locks to use nested ``with`` statements."""
            if not lock_list:
                return _do_merge()
            with lock_list[0]:
                return acquire_all(lock_list[1:])

        def _do_merge():
            def _entry_key(entry: dict[str, Any]) -> str:
                return json.dumps(entry, sort_keys=True, default=str)

            def _merge_entries(target_attr, source_attr):
                for identifier, entries in source_attr.items():
                    bucket = target_attr.setdefault(identifier, [])
                    seen = {_entry_key(existing) for existing in bucket}
                    for entry in entries:
                        key = _entry_key(entry)
                        if key not in seen:
                            bucket.append(entry.copy())
                            seen.add(key)

            for other in others:
                _merge_entries(self.errors, other.errors)
                _merge_entries(self.successes, other.successes)
                if other.start_time and other.start_time < self.start_time:
                    self.start_time = other.start_time
                if other.end_time and (self.end_time is None or other.end_time > self.end_time):
                    self.end_time = other.end_time

            self._flush()

        acquire_all(locks)

    def _autosave(self) -> None:
        """
        Increments the pending counter and triggers a save if either condition is met:

        - The number of pending additions has reached ``autosave_every``, **OR**
        - The time elapsed since the last save has exceeded ``autosave_interval_secs``
          (only evaluated when ``autosave_interval_secs > 0``).

        Must be called while ``self._lock`` is already held.
        """
        if not self.autosave_path:
            return
        self._pending_saves += 1
        count_reached = self._pending_saves >= self.autosave_every
        time_reached = (
            self.autosave_interval_secs > 0
            and (time.monotonic() - self._last_autosave_time) >= self.autosave_interval_secs
        )
        if count_reached or time_reached:
            self._flush()

    def _flush(self) -> None:
        """
        Forces an immediate write to the autosave path and resets both counters.

        I/O errors (e.g. disk full) are logged as warnings and never propagate to
        the caller, ensuring ``add_error`` / ``add_success`` are never interrupted.

        Must be called while ``self._lock`` is already held.
        """
        if not self.autosave_path:
            return
        try:
            yaml_str = ReportWriter.to_yaml(self, None)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Report serialisation failed for '%s': %s", self.title, exc)
            return
        finally:
            self._pending_saves = 0
            self._last_autosave_time = time.monotonic()

        try:
            with open(self.autosave_path, "w", encoding="utf-8") as f:
                f.write(yaml_str)
        except OSError as exc:
            logger.warning("Report autosave failed (%s): %s", self.autosave_path, exc)


def _cleanup_temp_file(path: Path) -> None:
    """``atexit`` handler: silently remove a temporary autosave file on process exit."""
    try:
        path.unlink(missing_ok=True)
    except OSError:
        pass

