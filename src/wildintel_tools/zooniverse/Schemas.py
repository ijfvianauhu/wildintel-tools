from typing import Optional, List, Any, Dict, Literal
from pydantic import BaseModel, Field

class ClassificationInfo(BaseModel):
    """Información de una clasificación individual hecha por un usuario en Zoo."""
    classification_id: Optional[str]
    user_name: Optional[str]
    user_id: Optional[str]
    annotations: List[Any] = Field(default_factory=list)
    subject_name: Optional[str]
    retired: bool = False
    retirement_reason: Optional[str] = None
    sid:int

class Zoo2TrapperObservation(BaseModel):
    """Anotacion individual extraída de zoo para poder ser importada en Trapper."""
    observationType: Literal["animal", "human", "vehicle", "black", "unclassified", "unknown"]
    scientificName: Optional[str] = None
    count: Optional[int] = None
    countNew: Optional[int] = None
    lifeStage: Optional[str] = None
    sex: Optional[str] = None
    behavior: Optional[str] = None
    individualID: Optional[str] = None
    observationTags: Optional[str] = None
    observationComments: Optional[str] = None

class WorkflowSummary(BaseModel):
    """Resumen general de un workflow."""
    total_subjects: int = 0
    retired_subjects: int = 0
    retired_pct: Optional[float] = None

class WorkflowData(BaseModel):
    """Datos y resumen asociados a un workflow."""
    summary: WorkflowSummary
    data: Dict[str, List[ClassificationInfo]]

class SubjectSetResults(BaseModel):
    """Resultado completo del SubjectSet agrupado por workflow."""
    workflows: Dict[str, WorkflowData]