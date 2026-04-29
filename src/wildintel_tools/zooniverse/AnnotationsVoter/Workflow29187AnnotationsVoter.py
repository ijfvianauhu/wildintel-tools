import math
from statistics import median
from typing import Any
from collections import Counter, defaultdict
from typing import List, Optional, Tuple

from wildintel_tools.zooniverse.AnnotationsVoter.AnnotationsVoter import AnnotationsVoter
from wildintel_tools.zooniverse.Schemas import Zoo2TrapperObservation


class Workflow29187AnnotationsVoter(AnnotationsVoter):
    """
    Extrae las anotaciones específicas del workflow 29187 (Tatra).
    """

    @staticmethod
    def _group_howmany(user_opinions: List) -> defaultdict:
        species_howmany = defaultdict(list)
        for species, attrs in user_opinions:
            val = attrs.get("HOWMANY")
            species_howmany[species].append(int(val) if val is not None and str(val).isdigit() else None)
        return species_howmany

    @staticmethod
    def _top_k_species(user_opinions: List, k: int) -> List[Tuple[str, int]]:
        species_count = Counter(
            species for species, _ in user_opinions
            if not (k > 1 and species == "NOANIMAL")
        )
        sorted_species = sorted(species_count.items(), key=lambda x: (-x[1], x[0]))
        return sorted_species[:k]

    @staticmethod
    def _howmany_median(species_howmany: defaultdict, species: str) -> Optional[int]:
        valid = [x for x in species_howmany[species] if x is not None]
        return math.ceil(median(valid)) if valid else None

    @staticmethod
    def _confidences(idx: int, votes: int, top_k_species: List, accumulated_conf: float) -> Tuple[float, float]:
        if idx + 1 < len(top_k_species):
            votes_next = top_k_species[idx + 1][1]
            pre_conf = votes / (votes + votes_next)
        else:
            pre_conf = 1.0
        libre_conf = 1.0 - accumulated_conf
        return pre_conf, pre_conf * libre_conf

    @staticmethod
    def _to_observation(species: str, count: Optional[int], pre_conf: float, confidence: float, sid) -> Zoo2TrapperObservation:
        observation_type = "animal"
        if species.lower() in ["animal", "human", "vehicle", "blank", "unclassified", "unknown"]:
            observation_type = species
            species = "" if species.lower() != "human" else "Homo Sapiens"
        return Zoo2TrapperObservation(
            observationType=observation_type,
            scientificName=species,
            count=count,
            countNew=None,
            lifeStage=None,
            sex=None,
            behavior=None,
            individualID=None,
            observationTags=None,
            observationComments=f"Automatically classified by Zooniverse for subject {sid} with confidences {pre_conf:.2f} {confidence:.2f}",
        )

    @staticmethod
    def run(observations: List[Any]) -> Optional[List[Zoo2TrapperObservation]]:
        if not observations:
            return None

        k, sid, user_opinions = observations[0]
        # Contamos números de individuo por especie
        species_howmany = Workflow29187AnnotationsVoter._group_howmany(user_opinions)
        # Contamos el número de votos que tienes cada especie nos quedamos con las k que tengan mśs
        top_k_species = Workflow29187AnnotationsVoter._top_k_species(user_opinions, k)

        result = []
        accumulated_conf = 0.0

        for idx, (species, votes) in enumerate(top_k_species):
            howmany_median = Workflow29187AnnotationsVoter._howmany_median(species_howmany, species)
            pre_conf, confidence = Workflow29187AnnotationsVoter._confidences(idx, votes, top_k_species, accumulated_conf)
            accumulated_conf += confidence
            obs = Workflow29187AnnotationsVoter._to_observation(species, howmany_median, pre_conf, confidence, sid)
            result.append(obs)

        return result
