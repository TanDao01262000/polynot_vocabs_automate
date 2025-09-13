from pydantic import BaseModel
from enum import Enum
from typing import List, Optional, Dict
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

# =========== FLASHCARD SYSTEM MODELS ===========

class StudyMode(str, Enum):
    REVIEW = "review"  # Show definition, guess word
    PRACTICE = "practice"  # Show word, guess definition  
    TEST = "test"  # Multiple choice questions
    WRITE = "write"  # Type the answer
    LISTEN = "listen"  # Audio pronunciation
    MIXED = "mixed"  # Random combination
    SPELLING = "spelling"  # Spelling practice
    SYNONYMS = "synonyms"  # Find synonyms
    ANTONYMS = "antonyms"  # Find antonyms
    CONTEXT = "context"  # Fill in context

class DifficultyRating(str, Enum):
    EASY = "easy"
    MEDIUM = "medium" 
    HARD = "hard"
    AGAIN = "again"

class SessionType(str, Enum):
    DAILY_REVIEW = "daily_review"
    TOPIC_FOCUS = "topic_focus"
    LEVEL_PROGRESSION = "level_progression"
    WEAK_AREAS = "weak_areas"
    RANDOM = "random"
    CUSTOM = "custom"

class FlashcardSession(BaseModel):
    """A flashcard study session"""
    id: Optional[str] = None
    user_id: str
    session_name: str
    session_type: SessionType
    study_mode: StudyMode
    topic_name: Optional[str] = None
    category_name: Optional[str] = None
    level: Optional[CEFRLevel] = None
    max_cards: int = 20
    time_limit_minutes: Optional[int] = None
    created_at: Optional[datetime] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    is_active: bool = True
    current_card_index: int = 0
    total_cards: int = 0
    correct_answers: int = 0
    incorrect_answers: int = 0
    skipped_cards: int = 0
    hints_used: int = 0
    total_time_seconds: int = 0

class FlashcardProgress(BaseModel):
    """Progress tracking for individual vocabulary in flashcard sessions"""
    id: Optional[str] = None
    user_id: str
    vocab_entry_id: str
    session_id: str
    card_index: int
    difficulty_rating: Optional[DifficultyRating] = None
    response_time_seconds: Optional[float] = None
    is_correct: Optional[bool] = None
    user_answer: Optional[str] = None
    correct_answer: str
    hints_used: int = 0
    attempts: int = 1
    created_at: Optional[datetime] = None

class FlashcardStats(BaseModel):
    """Statistics for flashcard performance"""
    total_sessions: int = 0
    total_cards_studied: int = 0
    total_correct: int = 0
    total_incorrect: int = 0
    total_skipped: int = 0
    average_response_time: Optional[float] = None
    accuracy_percentage: float = 0.0
    streak_days: int = 0
    last_study_date: Optional[datetime] = None
    favorite_study_mode: Optional[StudyMode] = None
    most_difficult_level: Optional[CEFRLevel] = None
    most_difficult_topic: Optional[str] = None
    improvement_rate: float = 0.0
    total_study_time_minutes: int = 0

class FlashcardSessionRequest(BaseModel):
    """Request to create a new flashcard session"""
    session_name: str
    session_type: SessionType = SessionType.RANDOM
    study_mode: StudyMode
    topic_name: Optional[str] = None
    category_name: Optional[str] = None
    level: Optional[CEFRLevel] = None
    max_cards: int = 20
    time_limit_minutes: Optional[int] = None
    include_reviewed: bool = False
    include_favorites: bool = False
    difficulty_filter: Optional[List[DifficultyRating]] = None
    smart_selection: bool = True  # Use AI to select optimal cards

class FlashcardAnswerRequest(BaseModel):
    """Request to submit an answer for a flashcard"""
    vocab_entry_id: Optional[str] = None  # Optional - system can determine from session
    user_answer: str
    response_time_seconds: float
    hints_used: int = 0
    difficulty_rating: Optional[DifficultyRating] = None
    confidence_level: Optional[int] = None  # 1-5 scale

class FlashcardSessionResponse(BaseModel):
    """Response for flashcard session operations"""
    success: bool
    message: str
    session: Optional[FlashcardSession] = None
    current_card: Optional[dict] = None
    progress: Optional[dict] = None

class FlashcardCard(BaseModel):
    """A single flashcard with all necessary information"""
    vocab_entry_id: str
    word: str
    definition: str
    translation: str
    example: str
    example_translation: str
    part_of_speech: Optional[str] = None
    level: str
    topic_name: Optional[str] = None
    is_favorite: bool = False
    review_count: int = 0
    last_reviewed: Optional[datetime] = None
    difficulty_rating: Optional[int] = None
    personal_notes: Optional[str] = None
    mastery_level: float = 0.0  # 0.0 to 1.0
    next_review_date: Optional[datetime] = None

class SpacedRepetitionSettings(BaseModel):
    """Settings for spaced repetition algorithm"""
    initial_interval_days: int = 1
    easy_multiplier: float = 2.5
    medium_multiplier: float = 1.5
    hard_multiplier: float = 1.2
    again_multiplier: float = 0.5
    max_interval_days: int = 365
    min_interval_days: int = 1
    algorithm: str = "sm2"  # sm2, sm17, or custom

class StudyReminder(BaseModel):
    """Study reminder settings"""
    id: Optional[str] = None
    user_id: str
    is_enabled: bool = True
    reminder_time: str  # HH:MM format
    days_of_week: List[int]  # 0=Monday, 6=Sunday
    min_cards_to_review: int = 5
    notification_method: str = "push"  # push, email, both
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

class FlashcardAchievement(BaseModel):
    """Achievement system for flashcards"""
    id: Optional[str] = None
    user_id: str
    achievement_type: str  # streak, accuracy, speed, etc.
    achievement_name: str
    description: str
    earned_at: Optional[datetime] = None
    progress: float = 0.0  # 0.0 to 1.0
    is_earned: bool = False

class StudySessionAnalytics(BaseModel):
    """Analytics for study sessions"""
    session_id: str
    user_id: str
    session_duration_minutes: float
    cards_per_minute: float
    accuracy_by_mode: Dict[str, float]
    difficulty_distribution: Dict[str, int]
    time_of_day: str
    day_of_week: str
    performance_trend: str  # improving, stable, declining
    recommendations: List[str]

# =========== END OF FLASHCARD MODELS ===========
