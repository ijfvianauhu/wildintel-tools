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
    Extract annotations specific to workflow 29187 (Tatra National Park  │ 91.8).

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

        "REDDEER" : "Cervus elaphus",
        "ROEDEER" : "Capreolus capreolus",
        "CERVIDREDORROEDEER": "Cervidae",
        "REDFOX": "Vulpes vulpes",
        "REDSQUIRREL": "Sciurus vulgaris",
        "BROWNBEAR" : "Ursus arctos",
        "PINEMARTEN": "Martes martes",
        "MARTENPINEORSTONEMARTEN" : "Martes",
        "STONEMARTEN" : "Martes foina",
        "CHAMOIS" : "Rupicapra rupicapra",
        "EURASIANLYNX" : "Lynx lynx",
        "WOLF" : "Canis lupus",
        "EUROPEANBADGER" : "Meles meles",
        "MARMOT" : "Marmota marmota",
        "WILDBOAR" : "Sus scrofa",
        "EUROPEANHARE" : "Lepus europaeus",
        "DOMESTICDOG" : "Canis familiaris",
        "DOMESTICCAT" : "Felis catus",
        "STOAT" :  "Mustela erminea",
        "WEASEL" : "Mustela nivalis",
        "MUSTELID" : "Mustelidae",
        "BIRDGENERAL" :"Aves",
    }

    @staticmethod
    def run(classifications:List[ClassificationInfo]) -> List[Any]:
        """
        For each classification, extract the choice, answers, and total of choices.

        :param classifications:
        :return:
        """

        def trapper_name(choice):
            return Workflow29186AnnotationExtractor.zoo_to_trapper.get(choice, "unknown")
        choices = []
        k_list = []
        k_max = 3  # max number of choices allowed per user and subject (photo)
        sid = None

        for classifications_x_user in classifications:
            pattern = r"'choice':\s*'([^']+)'.*?'answers':\s*(\{[^}]*\})"
            # get all choice, answers pairs
            matches = re.findall(pattern, str(classifications_x_user.annotations))
            # total of choices for this user classification
            k_list.append(len(matches))
            sid = classifications_x_user.sid

            results = [(choice, ast.literal_eval(answers)) for choice, answers in matches]
            #results = [(trapper_name(choice), ast.literal_eval(answers)) for choice, answers in matches]
            choices.extend(results)

        logger.debug(f"valores de k {k_list}")

        # k_majoritary is k value(s) most voted among users, but not higher than k_max. If multiple modes, take max
        k_majority = max([m for m in multimode(k_list) if m <= k_max])
        
        return [(k_majority,sid, choices)]