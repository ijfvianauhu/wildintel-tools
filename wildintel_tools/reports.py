from dataclasses import dataclass, field, asdict
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Dict, List, Any, Optional
import yaml
from wildintel_tools.ui.typer.i18n import _

class ReportStatus(str, Enum):
    """Possible states of a report."""
    SUCCESS = "success"
    FAILED = "failed"
    PARTIAL = "partial"
    EMPTY = "empty"

@dataclass()
class Report:
    """
    Class to record the result of a media upload process.
    Each identifier (e.g., image, subject, or file) can have multiple
    actions with associated successes or errors.
    """
    title: str
    start_time: datetime = field(default_factory=datetime.now)
    end_time: Optional[datetime] = None

    errors: Dict[str, List[Dict[str, Any]]] = field(default_factory=dict)
    successes: Dict[str, List[Dict[str, Any]]] = field(default_factory=dict)

    def add_error(self, identifier: str, action: str, message: str, **extra: Any) -> None:
        """Adds an error related to a specific identifier and action."""
        entry = {"action": action, "message": message, **extra}
        self.errors.setdefault(identifier, []).append(entry)

    def add_success(self, identifier: str, action: str, **extra: Any) -> None:
        """Adds a success related to a specific identifier and action."""
        entry = {"action": action, **extra}
        self.successes.setdefault(identifier, []).append(entry)

    def finish(self) -> None:
        """Marks the report as finished by setting the end time."""
        self.end_time = datetime.now()

    def get_status(self) -> str:
        """Returns the overall status of the report."""
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
        """True if report finished successfully."""
        return self.get_status() ==  ReportStatus.SUCCESS

    def is_failed(self) -> bool:
        """True if report finished with only errors."""
        return self.get_status() ==  ReportStatus.FAILED

    def is_partial(self) -> bool:
        """True if report finished partially successful."""
        return self.get_status() == ReportStatus.PARTIAL

    def is_empty(self) -> bool:
        """True if report contains no results."""
        return self.get_status() == ReportStatus.EMPTY

    # -----------------------------
    # ✅ Get entries filtered by action
    # -----------------------------
    def get_by_action(self, action: str) -> Dict[str, Dict[str, List[Dict[str, Any]]]]:
        """
        Returns all errors and successes corresponding to a specific action.
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

    # -----------------------------
    # ✅ NEW: Get all unique actions
    # -----------------------------
    def get_actions(self) -> List[str]:
        """
        Returns a sorted list of all distinct actions
        found in both errors and successes.

        Example:
            >>> report.get_actions()
            ['upload', 'validate', 'convert']
        """
        actions = set()

        for entries in list(self.errors.values()) + list(self.successes.values()):
            for e in entries:
                if "action" in e and e["action"]:
                    actions.add(e["action"])

        return sorted(actions)

    # -----------------------------
    # ✅ Summary
    # -----------------------------
    def summary(self) -> str:
        """Returns a readable summary of the report."""
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

    # -----------------------------
    # ✅ Load from YAML
    # -----------------------------
    @classmethod
    def from_yaml(cls, filepath: Path) -> "Report":
        """Creates a Report instance from a YAML file."""
        with open(filepath, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
        return cls(**data)

    def to_yaml(self, filepath: Path | None = None) -> str:
        """Convert the Report instance to a YAML string and optionally save it to a file.

        Parameters:
            filepath (Path | None): Path where the YAML will be written. If `None`, no file
                is written and only the YAML string is returned.

        Returns:
            str: The YAML representation of the Report instance.

        Behavior:
            - Uses `asdict` to convert the dataclass to a dictionary.
            - Produces YAML with `yaml.safe_dump` (preserves Unicode and does not sort keys).
            - If `filepath` is provided, writes the YAML to that file using UTF-8 encoding.
            - Always returns the resulting YAML string, even when the file is written.

        Note:
            `datetime` objects are preserved and will be serialized by PyYAML using its
            default datetime representation.
        """
        data = asdict(self)
        yaml_str = yaml.safe_dump(data, sort_keys=False, allow_unicode=True)

        if filepath is not None:
            with open(filepath, "w", encoding="utf-8") as f:
                f.write(yaml_str)

        return yaml_str
