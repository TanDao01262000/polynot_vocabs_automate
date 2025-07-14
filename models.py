from pydantic import BaseModel
from enum import Enum
from typing import List, Optional

class CEFRLevel(str, Enum):
    A1 = "A1"
    A2 = "A2"
    B1 = "B1"
    B2 = "B2"
    C1 = "C1"
    C2 = "C2"

class PartOfSpeech(str, Enum):
    NOUN = "noun"
    VERB = "verb"
    ADJECTIVE = "adjective"
    ADVERB = "adverb"
    PHRASAL_VERB = "phrasal_verb"
    IDIOM = "idiom"
    PHRASE = "phrase"

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
    definition: str
    translation: str
    example: str
    example_translation: str
    level: CEFRLevel
    part_of_speech: Optional[PartOfSpeech] = None

class VocabListResponse(BaseModel):
    """
    Structured response containing multiple vocab entries
    """
    vocabularies: List[VocabEntry]
    phrasal_verbs: List[VocabEntry]
    idioms: List[VocabEntry]

class TopicList(BaseModel):
    """
    List of topics to process
    """
    topics: List[str]
    description: Optional[str] = None
