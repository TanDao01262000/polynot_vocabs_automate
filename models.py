from pydantic import BaseModel
from enum import Enum
from typing import List, Optional
from datetime import datetime

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
    topic_name: str
    category_name: Optional[str] = None
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

class VocabGenerationResponse(BaseModel):
    """
    Structured response containing multiple vocab entries for AI generation
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

# New models for user vocabulary management
class UserVocabList(BaseModel):
    """
    User's personal vocabulary list
    """
    id: Optional[str] = None
    user_id: str
    list_name: str
    description: Optional[str] = None
    is_public: bool = False
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

class UserVocabEntry(BaseModel):
    """
    User's interaction with a vocabulary entry
    """
    id: Optional[str] = None
    user_id: str
    vocab_entry_id: str
    is_favorite: bool = False
    is_hidden: bool = False
    hidden_until: Optional[datetime] = None
    personal_notes: Optional[str] = None
    difficulty_rating: Optional[int] = None  # 1-5 scale
    last_reviewed: Optional[datetime] = None
    review_count: int = 0
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

class VocabEntryWithUserData(BaseModel):
    """
    Vocabulary entry with user-specific data
    """
    # Original vocab entry data
    id: str
    word: str
    definition: str
    translation: str
    example: str
    example_translation: str
    level: str
    part_of_speech: Optional[str] = None
    topic_id: Optional[str] = None
    target_language: str
    original_language: str
    created_at: Optional[datetime] = None
    
    # User-specific data
    is_favorite: bool = False
    is_hidden: bool = False
    hidden_until: Optional[datetime] = None
    personal_notes: Optional[str] = None
    difficulty_rating: Optional[int] = None
    last_reviewed: Optional[datetime] = None
    review_count: int = 0

class VocabListRequest(BaseModel):
    """
    Request to create or update a vocabulary list
    """
    list_name: str
    description: Optional[str] = None
    is_public: bool = False

class VocabEntryActionRequest(BaseModel):
    """
    Request to perform actions on vocabulary entries
    """
    vocab_entry_id: str
    action: str  # "favorite", "unfavorite", "hide", "unhide", "add_note", "rate_difficulty"
    value: Optional[str] = None  # For notes, difficulty rating, etc.

class VocabListResponse(BaseModel):
    """
    Response for vocabulary list operations
    """
    success: bool
    message: str
    data: Optional[dict] = None

class VocabListViewRequest(BaseModel):
    """
    Request for vocabulary list view with pagination and filters
    """
    page: int = 1
    limit: int = 20
    show_favorites_only: bool = False
    show_hidden: bool = False
    topic_name: Optional[str] = None
    category_name: Optional[str] = None
    level: Optional[CEFRLevel] = None
    search_term: Optional[str] = None

class VocabListViewResponse(BaseModel):
    """
    Response for vocabulary list view
    """
    success: bool
    message: str
    vocabularies: List[VocabEntryWithUserData]
    total_count: int
    page: int
    limit: int
    has_more: bool

class VocabSaveRequest(BaseModel):
    """
    Request to save a vocabulary entry to the database
    """
    word: str
    definition: str
    translation: str
    example: str
    example_translation: str
    level: CEFRLevel
    part_of_speech: Optional[PartOfSpeech] = None
    topic_name: Optional[str] = None
    category_name: Optional[str] = None
    target_language: str = "English"
    original_language: str  # Required field, no default value
