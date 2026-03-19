import ast
import re
from statistics import multimode
from typing import List, Any
import logging
from trapper_zooniverse.Schemas import ClassificationInfo
from trapper_zooniverse.AnnotationsExtractor.AnnotationsExtractor import AnnotationsExtractor

logger = logging.getLogger(__name__)

class Workflow29186AnnotationExtractor(AnnotationsExtractor):
    """
    Extract annotations specific to workflow 29186 (Doñana National Park │ 63.4).

    Extracts all user choices, counts how many choices each user made (K), finds the most frequent number of choices
    (not exceeding k_max) k_majority, and returns users choices and the highest k_majority (in case of multimodal).
    """

    """
    Mapping between possible responses given in zoo and the scientific species used by Trapper. If zoo volunteers detect
    something different to an animal or human, it must mapped to "unknown", "unclassified", "vehicle" or "black".
    """

    zoo_to_trapper = {
        "NOANIMAL": "blank",
        "HUMANORVEHICLE": "human",
        "OTHERSPECIES": "animal",
        "UNRECOGNIZABLE": "unknown",

        "REDDEER": "Cervus elaphus",
        "REDFOX": "Vulpes vulpes",
        "WILDBOAR": "Sus scrofa",
        "CERVIDREDORFALLOWDEER": "Cervidae",
        "COMMONGENET": "Genetta genetta",
        "COW": "Bos taurus",
        "EGYPTIANMONGOOSE": "Herpestes ichneumon",
        "EUROPEANBADGER": "Meles meles",
        "EUROPEANRABBIT": "Oryctolagus cuniculus",
        "FALLOWDEER": "Dama dama",
        "HORSE": "Equus caballus",
        "IBERIANHARE": "Lepus granatensis",
        "IBERIANLYNX": "Lynx pardinus",
        "LEPORIDRABBITORHARE": "Leporidae",
        "BIRD": "Aves",
        "DOMESTICDOG": "Canis familiaris"
    }

    @staticmethod
    def run(classifications:List[ClassificationInfo]) -> List[Any]:
        """
        For each classification, extract the choice, answers, and total of choices.

        :param classifications:
        :return:
        """

        def trapper_name(choice):
            return Workflow29186AnnotationExtractor.zoo_to_trapper.get(choice, choice)

        choices = []
        k_list = []
        k_max = 3  # max number of choices allowed per user and subject (photo)
        sid = None

        for classifications_x_user in classifications:
            pattern = r"'choice':\s*'([^']+)'.*?'answers':\s*(\{[^}]*\})"
            # get all choice, answers pairs
            matches = re.findall(pattern, str(classifications_x_user.annotations))

            if len(matches) == 0 or len(matches) > k_max:
                logger.debug("Skipping classification due to no matches or exceeding k_max")
                continue

            # total of choices for this user classification
            k_list.append(len(matches))
            sid = classifications_x_user.sid

            results = [(trapper_name(choice), ast.literal_eval(answers)) for choice, answers in matches]
            choices.extend(results)

        logger.debug(f"valores de k {k_list}")

        # k_majoritary is k value(s) most voted among users, but not higher than k_max. If multiple modes, take max
        k_majority = max([m for m in multimode(k_list) if m <= k_max])
        
        return [(k_majority,sid, choices)]