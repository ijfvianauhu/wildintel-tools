"""
Module for recording and exporting the results of media processing or upload operations.

Defines:
    - ReportStatus: Enumeration of possible report outcomes.
    - Report: Dataclass for recording detailed results (successes and errors)
      and exporting them to YAML.
"""

from dataclasses import dataclass, field, asdict
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Dict, List, Any, Optional
import yaml
from wildintel_tools.ui.typer.i18n import _

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

    :ivar title: Descriptive title of the report.
    :vartype title: str
    :ivar start_time: Time when the report was created or started.
    :vartype start_time: datetime
    :ivar end_time: Time when the report was finished, or ``None`` if still active.
    :vartype end_time: Optional[datetime]
    :ivar errors: Map of identifiers to lists of error entries.
    :vartype errors: Dict[str, List[Dict[str, Any]]]
    :ivar successes: Map of identifiers to lists of success entries.
    :vartype successes: Dict[str, List[Dict[str, Any]]]
    """
    title: str
    start_time: datetime = field(default_factory=datetime.now)
    end_time: Optional[datetime] = None

    errors: Dict[str, List[Dict[str, Any]]] = field(default_factory=dict)
    successes: Dict[str, List[Dict[str, Any]]] = field(default_factory=dict)

    def add_error(self, identifier: str, action: str, message: str, **extra: Any) -> None:
        """
        Adds an error record for a specific identifier and action.

        :param identifier: Unique identifier (e.g., file name or ID).
        :type identifier: str
        :param action: The operation that failed (e.g., ``"upload"``).
        :type action: str
        :param message: A human-readable description of the error.
        :type message: str
        :param extra: Optional keyword arguments with additional metadata (e.g., error code).
        :type extra: Any
        """
        entry = {"action": action, "message": message, **extra}
        self.errors.setdefault(identifier, []).append(entry)

    def add_success(self, identifier: str, action: str, message: str = None, **extra: Any) -> None:
        """
        Adds a success record for a specific identifier and action.

        :param identifier: Unique identifier (e.g., file name or ID).
        :type identifier: str
        :param action: The operation that succeeded (e.g., ``"upload"``).
        :type action: str
        :param message: Optional message describing the success.
        :type message: Optional[str]
        :param extra: Optional keyword arguments with additional metadata (e.g., timestamps).
        :type extra: Any
        """
        entry = {"action": action, "message": message, **extra}
        self.successes.setdefault(identifier, []).append(entry)

    def finish(self) -> None:
        """Marks the report as finished by setting the end time."""
        self.end_time = datetime.now()

    def get_status(self) -> ReportStatus:
        """
        Determines the overall report status based on recorded results.

        :return: One of ``"success"``, ``"failed"``, ``"partial"`` or ``"empty"``.
        :rtype: str
        """
        has_errors = any(self.errors.values())
        has_successes = any(self.successes.values())

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
        :rtype: bool
        """
        return self.get_status() ==  ReportStatus.SUCCESS

    def is_failed(self) -> bool:
        """
        Checks if the report contains only errors and no successes.

        :return: ``True`` if the report status is :data:`ReportStatus.FAILED`, otherwise ``False``.
        :rtype: bool
        """
        return self.get_status() ==  ReportStatus.FAILED

    def is_partial(self) -> bool:
        """
        Checks if the report contains both successes and errors.

        :return: ``True`` if the report status is :data:`ReportStatus.PARTIAL`, otherwise ``False``.
        :rtype: bool
        """
        return self.get_status() == ReportStatus.PARTIAL

    def is_empty(self) -> bool:
        """
        Checks if the report contains no recorded actions.

        :return: ``True`` if the report status is :data:`ReportStatus.EMPTY`, otherwise ``False``.
        :rtype: bool
        """
        return self.get_status() == ReportStatus.EMPTY

    def get_by_action(self, action: str) -> Dict[str, Dict[str, List[Dict[str, Any]]]]:
        """
        Retrieves all entries (successes and errors) associated with a specific action.

        :param action: The action name to filter by (e.g., ``"upload"``).
        :type action: str
        :return: A dictionary with two keys:
            - ``"errors"``: Matching error entries grouped by identifier.
            - ``"successes"``: Matching success entries grouped by identifier.
        :rtype: Dict[str, Dict[str, List[Dict[str, Any]]]]
        """
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

    def get_actions(self) -> List[str]:
        """
        Lists all distinct actions recorded in both errors and successes.

        :return: Sorted list of unique action names.
        :rtype: List[str]
        """
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

        :return: Multiline summary string suitable for console or log output.
        :rtype: str
        """
        duration = None
        if self.end_time:
            duration = (self.end_time - self.start_time).total_seconds()

        total_errors = sum(len(v) for v in self.errors.values())
        total_successes = sum(len(v) for v in self.successes.values())

        summary_lines = [
            _(f"Report '{self.title}'"),
            _(f"  Start: {self.start_time}"),
            _(f"  End: {self.end_time or 'in progress'}"),
            _(f"  Status: {self.get_status()}"),
        ]
        if duration:
            summary_lines.append(_(f"  Duration: {duration:.2f}s"))
        summary_lines.append(_(f"  Successes: {total_successes}"))
        summary_lines.append(_(f"  Errors: {total_errors}"))

        return "\n".join(summary_lines)

    @classmethod
    def from_yaml(cls, filepath: Path) -> "Report":
        """
        Creates a :class:`Report` instance from a YAML file.

        :param filepath: Path to the YAML file containing the report data.
        :type filepath: Path
        :return: A new :class:`Report` instance populated with the loaded data.
        :rtype: Report
        """
        with open(filepath, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
        return cls(**data)

    def to_yaml(self, filepath: Path | None = None) -> str:
        """
        Converts the current report to a YAML string and optionally saves it to a file.

        :param filepath: If provided, the YAML will also be written to this file
            using UTF-8 encoding. If ``None``, only the string is returned.
        :type filepath: Optional[Path]
        :return: The YAML representation of the report.
        :rtype: str

        .. note::
           - Uses :func:`dataclasses.asdict` for serialization.
           - Preserves Unicode and does not sort keys.
           - :class:`datetime` objects are serialized using PyYAML's default ISO format.
        """
        data = asdict(self)
        yaml_str = yaml.safe_dump(data, sort_keys=False, allow_unicode=True)

        if filepath is not None:
            with open(filepath, "w", encoding="utf-8") as f:
                f.write(yaml_str)

        return yaml_str

    def extend(self, other: "Report") -> None:
        """
        Fusiona en el informe actual los resultados de otro informe.

        :param other: Reporte cuyos registros se agregarán al actual.
        :raises TypeError: Si ``other`` no es una instancia de ``Report``.
        """
        if not isinstance(other, Report):
            raise TypeError("other must be an instance of Report")

        for attr in ("errors", "successes"):
            target = getattr(self, attr)
            source = getattr(other, attr)
            for identifier, entries in source.items():
                target.setdefault(identifier, []).extend(entries)

        if other.start_time and other.start_time < self.start_time:
            self.start_time = other.start_time
        if other.end_time and (self.end_time is None or other.end_time > self.end_time):
            self.end_time = other.end_time
