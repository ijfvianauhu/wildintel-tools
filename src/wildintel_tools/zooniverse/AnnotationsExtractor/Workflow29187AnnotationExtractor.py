from wildintel_tools.zooniverse.AnnotationsExtractor.AnnotationsExtractor import AnnotationsExtractor


class Workflow29187AnnotationExtractor(AnnotationsExtractor):
    """
    Extract annotations specific to workflow 29187 (Tatra National Park │ 91.8).
    """

    zoo_to_trapper = {
        "NOANIMAL": "blank",
        "HUMANORVEHICLE": "human",
        "OTHERSPECIES": "animal",
        "UNRECOGNIZABLE": "unknown",

        "REDDEER": "Cervus elaphus",
        "ROEDEER": "Capreolus capreolus",
        "CERVIDREDORROEDEER": "Cervidae",
        "REDFOX": "Vulpes vulpes",
        "REDSQUIRREL": "Sciurus vulgaris",
        "BROWNBEAR": "Ursus arctos",
        "PINEMARTEN": "Martes martes",
        "MARTENPINEORSTONEMARTEN": "Martes",
        "STONEMARTEN": "Martes foina",
        "CHAMOIS": "Rupicapra rupicapra",
        "EURASIANLYNX": "Lynx lynx",
        "WOLF": "Canis lupus",
        "EUROPEANBADGER": "Meles meles",
        "MARMOT": "Marmota marmota",
        "WILDBOAR": "Sus scrofa",
        "EUROPEANHARE": "Lepus europaeus",
        "DOMESTICDOG": "Canis familiaris",
        "DOMESTICCAT": "Felis catus",
        "STOAT": "Mustela erminea",
        "WEASEL": "Mustela nivalis",
        "MUSTELID": "Mustelidae",
        "BIRDGENERAL": "Aves",
    }
