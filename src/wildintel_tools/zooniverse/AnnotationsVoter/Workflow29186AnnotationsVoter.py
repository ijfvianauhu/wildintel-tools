import math
from statistics import median
from typing import Any
from collections import Counter, defaultdict
from typing import List, Optional

from trapper_zooniverse.AnnotationsVoter.AnnotationsVoter import AnnotationsVoter
from trapper_zooniverse.Schemas import Zoo2TrapperObservation

class Workflow29186AnnotationsVoter(AnnotationsVoter):

    observationTypeMap = {
        "UNRECOGNIZABLE": "black",
        "NOANIMAL": "human",
        "HUMAN": "human",
    }

    """
    Extrae las anotaciones específicas del workflow 17553 (IberianCameraTrapR1_1_2_3).
    """
    @staticmethod
    def run(observations: List[Any]) -> Optional[List[Zoo2TrapperObservation]]:

        if not observations:
            return None

        # Agrupar HOWMANY por especie
        species_howmany = defaultdict(list)
        k, sid, user_opinions = observations[0]
        for species, attrs in user_opinions:
            val = attrs.get("HOWMANY")
            if val is not None and str(val).isdigit():
                species_howmany[species].append(int(val))
            else:
                species_howmany[species].append(None)

        # Contar votos por especie, si k > 1 no tenemos en cuenta NOANIMAL
        species_count = Counter(species for species, _ in user_opinions if not (k > 1 and species == "NOANIMAL"))
        sorted_species = species_count.most_common()
        top_k_species = sorted_species[: max(1, k+1)]

        result = []

        for idx, (species, votes) in enumerate(top_k_species):
            # MEDIANA howmany
            valid_howmany = [x for x in species_howmany[species] if x is not None]
            howmany_median = math.ceil(median(valid_howmany)) if valid_howmany else None

            # Votos que tiene la siguiente especie en el ranking de las k más votadas
            if idx + 1 < len(top_k_species):
                votes_next = top_k_species[idx + 1][1]
            else:
                votes_next = None  # última especie no tiene "siguiente"

            if votes_next is None or votes_next <= 0:
                confidence = 1.0
            else:
                confidence = votes / (votes + votes_next)

            # Mapear observationType

            if species == "Homo sapiens":
                observationType = "human"
            elif species in ["vehicle", "blank", "unclassified", "unknown"]:
                observationType = species
                species = ""
            elif species == "animal":
                observationType = "animal"
                species = ""
            else:
                observationType = "animal"

            obs = Zoo2TrapperObservation(
                observationType=observationType,
                scientificName=species,  # <---- aquí puedes mapear a nombre científico real
                count=howmany_median,  # <---- count = mediana de HOWMANY
                countNew=None,
                lifeStage=None,
                sex=None,
                behavior=None,
                individualID=None,
                observationTags=None,
                observationComments=f"Automatically classified by Zooniverse for subject {sid} with confidence {confidence:.2f}",
            )

            result.append(obs)

        return result