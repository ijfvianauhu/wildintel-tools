import ast
import re
from statistics import multimode
from typing import List, Any
import logging

from wildintel_tools.zooniverse.Schemas import ClassificationInfo

logger = logging.getLogger(__name__)


class AnnotationsExtractor:
    """
    Base class for extracting annotations from Zooniverse classifications.

    Subclasses must define `zoo_to_trapper` and may override `extract_matches`
    and `trapper_name` when the annotation format or species-name mapping differs.
    """

    zoo_to_trapper: dict = {}

    def __init__(self, k_max: int = 3):
        self.k_max = k_max

    def trapper_name(self, choice: str) -> str:
        return self.zoo_to_trapper.get(choice, "unknown")

    def extract_matches(self, annotations_str: str) -> list:
        pattern = r"'choice':\s*'([^']+)'.*?'answers':\s*(\{[^}]*\})"
        return re.findall(pattern, annotations_str)

    def run(self, classifications: List[ClassificationInfo]) -> List[Any]:
        choices = []
        k_list = []
        sid = None

        for classifications_x_user in classifications:
            matches = self.extract_matches(str(classifications_x_user.annotations))
            if len(matches) == 0 or len(matches) > self.k_max:
                logger.debug(
                    f"Discarding classification from {classifications_x_user.sid}: "
                    f"{len(matches)} matches (k_max={self.k_max})"
                )
                continue
            k_list.append(len(matches))
            sid = classifications_x_user.sid
            results = [(self.trapper_name(choice), ast.literal_eval(answers)) for choice, answers in matches]
            choices.extend(results)

        logger.debug(f"valores de k {k_list}")
        k_majority = max([m for m in multimode(k_list) if m <= self.k_max])
        return [(k_majority, sid, choices)]
