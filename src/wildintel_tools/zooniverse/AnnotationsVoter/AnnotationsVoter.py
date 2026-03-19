from typing import List, Optional, Any
from abc import ABC, abstractmethod
from wildintel_tools.zooniverse.Schemas import Zoo2TrapperObservation

class AnnotationsVoter(ABC):
    """
    This class processes the classification data of a subject set obtained by an AnnotationExtractor and returns the
    final classification or classifications that the subject will receive.

    For example, given a list of observations extracted from multiple classifications for a subject ('oth sp_4.jpeg'):

    [('unknown', {}), ('unknown', {}),('Genetta genetta', {'HOWMANY': '1'})]

    This could returns the following voted observations:

    [
        Zoo2TrapperObservation(
            observationType='unknown',
            scientificName=None,
            count=None,
            countNew=None,
            lifeStage=None,
            lifeStage: Optional[str] = None
            sex: Optional[str] = None
            behavior: Optional[str] = None
            individualID: Optional[str] = None
            observationTags: Optional[str] = None
        )
    ]
    """
    @staticmethod
    @abstractmethod
    def run(classifications:List[Any]) -> Optional[List[Zoo2TrapperObservation]]:
        pass