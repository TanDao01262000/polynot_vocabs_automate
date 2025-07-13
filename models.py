from pydantic import BaseModel
from enum import Enum

class CEFRLevel(str, Enum):
    A1 = "A1"
    A2 = "A2"
    B1 = "B1"
    B2 = "B2"
    C1 = "C1"
    C2 = "C2"

class VocabRequest(BaseModel):
    """
    Request body for generating vocabularies.
    """
    topic: str
    target_language: str  
    level: CEFRLevel      


class VocabEntry(BaseModel):
    """
    Vocab return from AI Agent
    """
    word: str
    definition:str
    translation: str
    example: str
    example_translation: str
    level: CEFRLevel
