from wildintel_tools.zooniverse.AnnotationsExtractor.AnnotationsExtractor import AnnotationsExtractor


class Workflow29186AnnotationExtractor(AnnotationsExtractor):
    """
    Extract annotations specific to workflow 29186 (Doñana National Park │ 63.4).
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
        "DOMESTICDOG": "Canis familiaris",
    }