from fastapi import FastAPI, HTTPException, BackgroundTasks, Depends, Header
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Optional
import uvicorn
from datetime import datetime, timedelta
import uuid
import hashlib
import secrets
import os

# Import your existing modules
from vocab_agent_react import generate_vocab_with_react_agent, generate_vocab
from vocab_agent import run_single_topic_generation, run_continuous_vocab_generation, view_saved_topic_lists
from models import (
    CEFRLevel, VocabListViewRequest, VocabListViewResponse, VocabEntryActionRequest, 
    VocabListRequest, VocabListResponse, FlashcardSessionRequest, FlashcardAnswerRequest,
    FlashcardSessionResponse, StudyMode, DifficultyRating, FlashcardCard, FlashcardStats,
    SessionType, SpacedRepetitionSettings, StudyReminder, FlashcardAchievement,
    # TTS Models
    TTSRequest, TTSResponse, VoiceCloneRequest, VoiceCloneResponse, 
    UserVoiceProfile, UserSubscription, SubscriptionPlan,
    # Pronunciation Models
    PronunciationRequest, PronunciationResponse, VocabPronunciation, PronunciationType
)
from config import Config
from topics import get_categories, get_topics_by_category, get_topic_list
from supabase_database import SupabaseVocabDatabase
from tts_service import TTSService
from pronunciation_service import pronunciation_service
from voice_cloning_api import router as voice_cloning_router
# from tts_api import router as tts_router  # Commented out due to path conflict

# Import points integration
from points_integration import vocab_points, flashcard_points

# Initialize FastAPI app
app = FastAPI(
    title="AI Vocabulary Generator API - Comprehensive",
    description="Complete API for generating vocabulary content with all available methods",
    version="2.0.0",
    docs_url="/docs",
    redoc_url="/redoc"
)

# Add CORS middleware for Flutter frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure this properly for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize database and services
db = SupabaseVocabDatabase()

# =========== User Vocabulary Tracking Functions ===========

def get_user_seen_vocabularies(user_id: str, days_lookback: int = 5, db_instance=None) -> set:
    """Get vocabulary words that user has recently seen/generated from generation history only"""
    try:
        from datetime import datetime, timedelta
        from config import Config
        from supabase import create_client
        
        # Calculate cutoff date
        cutoff_date = datetime.now() - timedelta(days=days_lookback)
        
        seen_words = set()
        
        # Use service role client to bypass RLS for system operations
        if Config.SUPABASE_SERVICE_ROLE_KEY:
            service_client = create_client(Config.SUPABASE_URL, Config.SUPABASE_SERVICE_ROLE_KEY)
            
            # Get words from generation history (if table exists)
            try:
                history_result = service_client.table("user_generation_history").select("word").eq("user_id", user_id).gte("generated_at", cutoff_date.isoformat()).execute()
                if history_result.data:
                    for item in history_result.data:
                        seen_words.add(item["word"].lower())
            except Exception as e:
                print(f"⚠️ Generation history table not available: {e}")
        else:
            print("⚠️ Service role key not available for user seen vocabularies")
        
        print(f"Found {len(seen_words)} vocabularies seen by user in last {days_lookback} days")
        return seen_words
        
    except Exception as e:
        print(f"Error getting user seen vocabularies: {e}")
        return set()

def filter_user_seen_duplicates(entries: list, user_id: str, lookback_days: int = 5) -> list:
    """Filter out vocabulary entries that user has recently seen"""
    if not user_id:
        return entries
    
    seen_words = get_user_seen_vocabularies(user_id, lookback_days)
    
    if not seen_words:
        return entries
    
    filtered_entries = []
    for entry in entries:
        if entry.word.lower() not in seen_words:
            filtered_entries.append(entry)
        else:
            print(f"Filtered user-seen word: {entry.word} (seen in last {lookback_days} days)")
    
    print(f"User deduplication: {len(entries)} → {len(filtered_entries)} entries (removed {len(entries) - len(filtered_entries)} recently seen)")
    return filtered_entries

def track_generated_vocabularies(user_id: str, vocabularies: list, topic: str, level, session_id: str = None) -> bool:
    """Track vocabularies that were generated and shown to a user"""
    try:
        if not user_id or not vocabularies:
            return False
            
        import uuid
        from datetime import datetime
        
        if not session_id:
            session_id = str(uuid.uuid4())
        
        # Prepare batch insert data
        generation_records = []
        for vocab in vocabularies:
            record = {
                "user_id": user_id,
                "word": vocab.word.lower(),
                "topic": topic,
                "level": level.value if hasattr(level, 'value') else str(level),
                "generated_at": datetime.now().isoformat(),
                "session_id": session_id
            }
            generation_records.append(record)
        
        # Try to insert to user_generation_history table
        try:
            from config import Config
            from supabase import create_client
            
            # Use service role client to bypass RLS for system operations
            if Config.SUPABASE_SERVICE_ROLE_KEY:
                service_client = create_client(Config.SUPABASE_URL, Config.SUPABASE_SERVICE_ROLE_KEY)
                service_client.table("user_generation_history").insert(generation_records).execute()
                print(f"✅ Tracked {len(generation_records)} generated vocabularies for user")
                return True
            else:
                print("⚠️ Service role key not available for tracking")
                return False
                
        except Exception as e:
            print(f"⚠️ Could not track generation history: {e}")
            return False
            
    except Exception as e:
        print(f"Error tracking generated vocabularies: {e}")
        return False
tts_service = TTSService()

# Include voice cloning router
app.include_router(voice_cloning_router)
# app.include_router(tts_router)  # Commented out due to path conflict

# In-memory session storage (in production, use Redis or database)
active_sessions = {}

# =========== AUTHENTICATION HELPER ===========

# Auth endpoints removed - use main auth server on port 8000
# /auth/login, /auth/register, /auth/logout are handled by the main server



async def get_current_user(authorization: Optional[str] = Header(None)) -> str:
    """Extract and validate user from Supabase Auth token"""
    if not authorization:
        print("❌ AUTH: No authorization header provided")
        raise HTTPException(
            status_code=401, 
            detail="Authorization header required",
            headers={"error_code": "NO_TOKEN"}
        )
    
    try:
        # Extract token
        if not authorization.startswith("Bearer "):
            print(f"❌ AUTH: Invalid header format: {authorization[:20]}...")
            raise HTTPException(
                status_code=401,
                detail="Invalid authorization header format. Expected: Bearer <token>",
                headers={"error_code": "INVALID_HEADER"}
            )
        
        token = authorization[7:]  # Remove "Bearer " prefix
        print(f"🔍 AUTH: Validating token (length: {len(token)}): {token[:20]}...{token[-20:]}")
        
        # Validate token directly with Supabase
        try:
            user_response = db.client.auth.get_user(token)
            
            if not user_response or not user_response.user:
                print("❌ AUTH: Supabase returned empty user response")
                raise HTTPException(
                    status_code=401,
                    detail="Invalid or expired token",
                    headers={"error_code": "INVALID_TOKEN"}
                )
            
            user = user_response.user
            user_id = user.id
            email = getattr(user, 'email', None)
            
            print(f"✅ AUTH: Token validated successfully - User ID: {user_id}, Email: {email}")
            
            # Ensure user exists in vocab database
            await ensure_user_exists(user_id, email)
            
            return user_id
            
        except HTTPException:
            raise
        except Exception as auth_error:
            error_msg = str(auth_error).lower()
            print(f"❌ AUTH: Supabase validation error: {auth_error}")
            
            # Check for specific error types
            if "expired" in error_msg or "jwt expired" in error_msg:
                raise HTTPException(
                    status_code=401,
                    detail="Token expired. Please refresh your session.",
                    headers={"error_code": "TOKEN_EXPIRED"}
                )
            elif "invalid" in error_msg or "403" in error_msg:
                raise HTTPException(
                    status_code=401,
                    detail="Invalid token. Please login again.",
                    headers={"error_code": "INVALID_TOKEN"}
                )
            else:
                raise HTTPException(
                    status_code=401,
                    detail=f"Authentication failed: {auth_error}",
                    headers={"error_code": "AUTH_FAILED"}
                )
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"❌ AUTH: Unexpected error: {e}")
        raise HTTPException(
            status_code=401,
            detail=f"Authentication error: {str(e)}",
            headers={"error_code": "AUTH_ERROR"}
        )

async def get_current_user_and_client(authorization: Optional[str] = Header(None)) -> tuple[str, any]:
    """Extract and validate user from Supabase Auth token, return user_id and authenticated client"""
    if not authorization:
        raise HTTPException(status_code=401, detail="Authorization header required")
    
    try:
        # Extract token
        if authorization.startswith("Bearer "):
            token = authorization[7:]  # Remove "Bearer " prefix
        else:
            token = authorization
        
        # Validate token directly with Supabase
        user_response = db.client.auth.get_user(token)
        
        if not user_response or not user_response.user:
            raise HTTPException(status_code=401, detail="Invalid Supabase Auth token")
        
        user = user_response.user
        user_id = user.id
        
        # Ensure user exists in vocab database
        await ensure_user_exists(user_id, user.email)
        
        # Return user_id and None for authenticated_client (not needed for current setup)
        return user_id, None
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=401, detail=f"Authentication verification failed: {str(e)}")

async def ensure_user_exists(user_id: str, email: str = None) -> bool:
    """Ensure user exists in the profiles table, create if necessary"""
    try:
        # Check if user exists
        result = db.client.table("profiles").select("id").eq("id", user_id).execute()
        
        if not result.data:
            # User doesn't exist, create basic profile
            user_data = {
                "id": user_id,
                "email": email or f"user_{user_id}@example.com",
                "created_at": datetime.now().isoformat(),
                "updated_at": datetime.now().isoformat()
            }
            
            # Add username from email if available
            if email:
                user_data["user_name"] = email.split("@")[0]
            
            db.client.table("profiles").insert(user_data).execute()
            print(f"Created user profile for {user_id}")
            return True
        else:
            print(f"User {user_id} already exists in profiles")
            return True
            
    except Exception as e:
        print(f"Error ensuring user exists: {e}")
        # Don't raise exception, just log the error
        return False

# =========== Pydantic Models ===========

class GenerateSingleRequest(BaseModel):
    topic: str
    level: CEFRLevel = CEFRLevel.A2
    language_to_learn: str = "English"
    learners_native_language: str = "Vietnamese"
    vocab_per_batch: int = 10
    phrasal_verbs_per_batch: int = 5
    idioms_per_batch: int = 5
    delay_seconds: int = 3
    save_topic_list: bool = False
    topic_list_name: Optional[str] = None

class GenerateMultipleRequest(BaseModel):
    topics: List[str]
    level: CEFRLevel = CEFRLevel.A2
    language_to_learn: str = "English"
    learners_native_language: str = "Vietnamese"
    vocab_per_batch: int = 10
    phrasal_verbs_per_batch: int = 5
    idioms_per_batch: int = 5
    delay_seconds: int = 3
    save_topic_list: bool = False
    topic_list_name: Optional[str] = None

class GenerateCategoryRequest(BaseModel):
    category: str
    level: CEFRLevel = CEFRLevel.A2
    language_to_learn: str = "English"
    learners_native_language: str = "Vietnamese"
    vocab_per_batch: int = 10
    phrasal_verbs_per_batch: int = 5
    idioms_per_batch: int = 5
    delay_seconds: int = 3

class VocabEntryResponse(BaseModel):
    id: str  # Unique identifier for frontend
    word: str
    definition: str
    translation: str  # Include translation
    part_of_speech: str
    example: str
    example_translation: str
    level: str
    topic_name: Optional[str] = None  # Include topic name
    target_language: Optional[str] = None  # Include target language
    original_language: Optional[str] = None  # Include original language
    is_duplicate: bool = False

class GenerateResponse(BaseModel):
    success: bool
    message: str
    method: str
    details: dict
    generated_vocabulary: List[VocabEntryResponse]
    total_generated: int
    new_entries_saved: int
    duplicates_found: int

class TopicListResponse(BaseModel):
    topics: List[str]
    description: str

class CategoryResponse(BaseModel):
    categories: List[str]

# =========== NEW USER VOCABULARY MANAGEMENT ENDPOINTS ===========

@app.get("/vocab/list", response_model=VocabListViewResponse, tags=["User Vocabulary"])
async def get_vocab_list(
    request: VocabListViewRequest = Depends(),
    current_user: str = Depends(get_current_user)
):
    """Get vocabulary list with pagination and filtering"""
    try:
        result = db.get_user_vocab_entries_with_pagination(
            user_id=current_user,
            page=request.page,
            limit=request.limit,
            show_favorites_only=request.show_favorites_only,
            show_hidden=request.show_hidden,
            topic_name=request.topic_name,
            category_name=request.category_name,
            level=request.level,
            search_term=request.search_term
        )
        
        return VocabListViewResponse(
            success=True,
            message=f"Retrieved {len(result['vocabularies'])} vocabulary entries",
            vocabularies=result['vocabularies'],
            total_count=result['total_count'],
            page=result['page'],
            limit=result['limit'],
            has_more=result['has_more']
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get vocabulary list: {str(e)}")

@app.get("/vocab/user-saved", tags=["User Vocabulary"])
async def get_user_saved_vocab(
    show_hidden: bool = False,
    current_user: str = Depends(get_current_user)
):
    """Get all vocabulary entries saved by the current user"""
    try:
        # Get user's saved vocabulary entries with hidden filter
        result = db.get_user_saved_vocab_entries(current_user, show_hidden=show_hidden)
        
        return {
            "success": True,
            "message": f"Retrieved {len(result)} saved vocabulary entries",
            "vocabularies": result
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get user saved vocabulary: {str(e)}")

@app.post("/vocab/save-to-user", tags=["User Vocabulary"])
async def save_vocab_to_user(
    request: dict,
    current_user: str = Depends(get_current_user)
):
    """Save a vocabulary entry to the user's personal vocabulary"""
    try:
        # Extract vocabulary data from request
        vocab_data = {
            "word": request["word"],
            "definition": request["definition"],
            "translation": request["translation"],
            "example": request["example"],
            "example_translation": request["example_translation"],
            "level": request["level"],
            "part_of_speech": request["part_of_speech"],
            "topic_name": request.get("topic_name"),
            "category_name": request.get("category_name"),
            "target_language": request.get("target_language", "English"),
            "original_language": request.get("original_language", "Vietnamese")
        }
        
        # Create VocabEntry object
        from models import VocabEntry, CEFRLevel, PartOfSpeech
        vocab_entry = VocabEntry(
            word=vocab_data["word"],
            definition=vocab_data["definition"],
            translation=vocab_data["translation"],
            example=vocab_data["example"],
            example_translation=vocab_data["example_translation"],
            level=CEFRLevel(vocab_data["level"]),
            part_of_speech=PartOfSpeech(vocab_data["part_of_speech"]) if vocab_data["part_of_speech"] else None
        )
        
        # Save to user's personal vocabulary
        saved_id = db.save_vocab_to_user(
            user_id=current_user,
            vocab_entry=vocab_entry,
            topic_name=vocab_data["topic_name"],
            category_name=vocab_data["category_name"],
            target_language=vocab_data["target_language"],
            original_language=vocab_data["original_language"]
        )
        
        return {
            "success": True,
            "message": f"Vocabulary '{vocab_data['word']}' saved to your personal vocabulary",
            "vocab_entry_id": saved_id
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to save vocabulary: {str(e)}")

@app.post("/vocab/favorite", tags=["User Vocabulary"])
async def toggle_favorite(
    request: VocabEntryActionRequest,
    current_user: str = Depends(get_current_user)
):
    """Toggle favorite status for a vocabulary entry"""
    try:
        # Ensure user exists in profiles table
        await ensure_user_exists(current_user)
        
        is_favorite = db.toggle_favorite(current_user, request.vocab_entry_id)
        
        return {
            "success": True,
            "message": f"Vocabulary {'favorited' if is_favorite else 'unfavorited'} successfully",
            "is_favorite": is_favorite
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to toggle favorite: {str(e)}")

@app.post("/vocab/hide", tags=["User Vocabulary"])
async def hide_vocab_entry(
    request: VocabEntryActionRequest,
    current_user: str = Depends(get_current_user)
):
    """Hide or unhide a vocabulary entry based on action"""
    try:
        # Ensure user exists in profiles table
        await ensure_user_exists(current_user)
        
        # Check if this is a hide or unhide action
        if request.action == "unhide":
            # Unhide the vocabulary entry
            db.unhide_vocab_entry(current_user, request.vocab_entry_id)
            
            return {
                "success": True,
                "message": "Vocabulary unhidden successfully",
                "hidden_until": None
            }
        else:
            # Hide the vocabulary entry
            # Parse hide duration from value (default 7 days)
            hide_duration = 7
            if request.value:
                try:
                    hide_duration = int(request.value)
                except ValueError:
                    pass
            
            db.hide_vocab_entry(current_user, request.vocab_entry_id, hide_duration)
            
            return {
                "success": True,
                "message": f"Vocabulary hidden for {hide_duration} days",
                "hidden_until": (datetime.now() + timedelta(days=hide_duration)).isoformat()
            }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to hide/unhide vocabulary: {str(e)}")

@app.post("/vocab/unhide", tags=["User Vocabulary"])
async def unhide_vocab_entry(
    request: VocabEntryActionRequest,
    current_user: str = Depends(get_current_user)
):
    """Unhide a vocabulary entry"""
    try:
        db.unhide_vocab_entry(current_user, request.vocab_entry_id)
        
        return {
            "success": True,
            "message": "Vocabulary unhidden successfully"
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to unhide vocabulary: {str(e)}")

@app.post("/vocab/hide-toggle", tags=["User Vocabulary"])
async def hide_toggle_vocab_entry(
    request: dict,
    current_user: str = Depends(get_current_user)
):
    """Toggle hide/unhide status for a vocabulary entry"""
    try:
        # Ensure user exists in profiles table
        await ensure_user_exists(current_user)
        
        vocab_entry_id = request.get("vocab_entry_id")
        action = request.get("action", "hide")  # Default to hide
        hide_duration = request.get("hide_duration", 7)  # Default 7 days
        
        if action == "unhide":
            # Unhide the vocabulary entry
            db.unhide_vocab_entry(current_user, vocab_entry_id)
            
            return {
                "success": True,
                "message": "Vocabulary unhidden successfully",
                "hidden_until": None,
                "is_hidden": False
            }
        else:
            # Hide the vocabulary entry
            db.hide_vocab_entry(current_user, vocab_entry_id, hide_duration)
            
            hidden_until = datetime.now() + timedelta(days=hide_duration)
            
            return {
                "success": True,
                "message": f"Vocabulary hidden for {hide_duration} days",
                "hidden_until": hidden_until.isoformat(),
                "is_hidden": True
            }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to toggle hide status: {str(e)}")

@app.post("/vocab/note", tags=["User Vocabulary"])
async def add_personal_note(
    request: VocabEntryActionRequest,
    current_user: str = Depends(get_current_user)
):
    """Add or update personal notes for a vocabulary entry"""
    try:
        if not request.value:
            raise HTTPException(status_code=400, detail="Note content is required")
        
        # Ensure user exists in profiles table
        await ensure_user_exists(current_user)
        
        db.add_personal_note(current_user, request.vocab_entry_id, request.value)
        
        return {
            "success": True,
            "message": "Personal note added successfully"
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to add note: {str(e)}")

@app.post("/vocab/rate", tags=["User Vocabulary"])
async def rate_difficulty(
    request: VocabEntryActionRequest,
    current_user: str = Depends(get_current_user)
):
    """Rate the difficulty of a vocabulary entry (1-5 scale)"""
    try:
        if not request.value:
            raise HTTPException(status_code=400, detail="Rating value is required")
        
        try:
            rating = int(request.value)
            if not 1 <= rating <= 5:
                raise ValueError("Rating must be between 1 and 5")
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))
        
        # Ensure user exists in profiles table
        await ensure_user_exists(current_user)
        
        db.rate_difficulty(current_user, request.vocab_entry_id, rating)
        
        return {
            "success": True,
            "message": f"Difficulty rated as {rating}/5"
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to rate difficulty: {str(e)}")

@app.post("/vocab/review", tags=["User Vocabulary"])
async def mark_as_reviewed(
    request: VocabEntryActionRequest,
    current_user: str = Depends(get_current_user)
):
    """Mark or unmark a vocabulary entry as reviewed based on action"""
    try:
        # Ensure user exists in profiles table
        await ensure_user_exists(current_user)
        
        # Check if this is a review or unreview action
        if request.action == "unreview":
            # Unmark as reviewed (reset review count to 0)
            db.undo_review(current_user, request.vocab_entry_id)
            
            return {
                "success": True,
                "message": "Vocabulary unmarked as reviewed",
                "review_count": 0,
                "last_reviewed": None
            }
        else:
            # Mark as reviewed (increment review count)
            db.mark_as_reviewed(current_user, request.vocab_entry_id)
            
            return {
                "success": True,
                "message": "Vocabulary marked as reviewed",
                "review_count": 1,  # This will be the actual count from database
                "last_reviewed": datetime.now().isoformat()
            }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to mark/unmark as reviewed: {str(e)}")

# =========== USER VOCABULARY LISTS ENDPOINTS ===========

@app.post("/vocab/lists", tags=["User Vocabulary Lists"])
async def create_vocab_list(
    request: VocabListRequest,
    current_user: str = Depends(get_current_user)
):
    """Create a new vocabulary list"""
    try:
        # Ensure user exists in profiles table
        await ensure_user_exists(current_user)
        
        list_id = db.create_user_vocab_list(
            user_id=current_user,
            list_name=request.list_name,
            description=request.description,
            is_public=request.is_public
        )
        
        return {
            "success": True,
            "message": "Vocabulary list created successfully",
            "list_id": list_id
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to create list: {str(e)}")

@app.get("/vocab/lists", tags=["User Vocabulary Lists"])
async def get_user_vocab_lists(current_user: str = Depends(get_current_user)):
    """Get all vocabulary lists for the current user"""
    try:
        lists = db.get_user_vocab_lists(current_user)
        
        return {
            "success": True,
            "message": f"Retrieved {len(lists)} vocabulary lists",
            "lists": lists
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get lists: {str(e)}")

@app.post("/vocab/lists/{list_id}/add", tags=["User Vocabulary Lists"])
async def add_vocab_to_list(
    list_id: str,
    request: VocabEntryActionRequest,
    current_user: str = Depends(get_current_user)
):
    """Add a vocabulary entry to a list"""
    try:
        db.add_vocab_to_list(list_id, request.vocab_entry_id)
        
        return {
            "success": True,
            "message": "Vocabulary added to list successfully"
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to add to list: {str(e)}")

@app.delete("/vocab/lists/{list_id}/remove", tags=["User Vocabulary Lists"])
async def remove_vocab_from_list(
    list_id: str,
    request: VocabEntryActionRequest,
    current_user: str = Depends(get_current_user)
):
    """Remove a vocabulary entry from a list"""
    try:
        db.remove_vocab_from_list(list_id, request.vocab_entry_id)
        
        return {
            "success": True,
            "message": "Vocabulary removed from list successfully"
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to remove from list: {str(e)}")

# =========== Generation Functions ===========

def generate_single_topic_sync(
    topic: str,
    level: CEFRLevel,
    language_to_learn: str,
    learners_native_language: str,
    vocab_per_batch: int,
    phrasal_verbs_per_batch: int,
    idioms_per_batch: int,
    delay_seconds: int,
    save_topic_list: bool,
    topic_list_name: Optional[str],
    user_id: Optional[str] = None,
):
    """Generate vocabulary for a single topic synchronously"""
    try:
        print(f"Starting single topic generation for: {topic}")
        
        # Import here to avoid circular imports
        from vocab_agent_react import generate_vocab_with_react_agent
        from vocab_agent import db, filter_duplicates, validate_topic_relevance, get_existing_combinations_for_topic
        
        # Direct vocabulary generation (search functionality removed)
        print(f"\n📚 STANDARD GENERATION")
        
        # Get existing combinations
        existing_combinations = get_existing_combinations_for_topic(topic)
        print(f"Found {len(existing_combinations)} existing combinations")
        
        # Build enhanced prompt for direct generation
        base_prompt = f'''You are an expert {language_to_learn} language teacher creating engaging vocabulary content for {topic}.'''
        print(f"\n📝 STANDARD AI PROMPT")

        prompt = f'''{base_prompt}

Generate diverse and interesting {language_to_learn} vocabulary for CEFR level {level.value}:

1. {vocab_per_batch} {language_to_learn} vocabulary words (nouns, verbs, adjectives, adverbs)
2. {phrasal_verbs_per_batch} {language_to_learn} phrasal verbs/expressions  
3. {idioms_per_batch} {language_to_learn} idioms/proverbs

CRITICAL REQUIREMENTS:
- All words must be relevant to "{topic}"
- Include clear definitions in {language_to_learn} (the target learning language)
- Provide example sentences in {language_to_learn}
- Translate examples to {learners_native_language}
- Ensure appropriate difficulty for {level.value} level
- Focus on topic-specific vocabulary, not generic words
- If context provided above, prioritize vocabulary from those materials

Format as JSON with vocabularies, phrasal_verbs, and idioms arrays.'''

        # DEBUG: Show final prompt structure
        print(f"\n🔍 FINAL PROMPT ANALYSIS:")
        print(f"📏 Total prompt length: {len(prompt)} characters")
        if "IMPORTANT CONTEXT" in prompt:
            print("✅ Search context IS included in prompt")
            context_start = prompt.find("IMPORTANT CONTEXT")
            context_section = prompt[context_start:context_start+300] + "..."
            print(f"📄 Context section: {context_section}")
        else:
            print("❌ Search context NOT found in prompt")
        print(f"🎯 Prompt starts with: {prompt[:150]}...")
        print(f"🏁 Prompt ends with: ...{prompt[-100:]}")

        # NEW: Search once, then generate multiple times with the same context
        print(f"\n🚀 USING SEARCH-ONCE APPROACH")
        print(f"📋 Parameters:")
        print(f"   Topic: {topic}")
        print(f"   Level: {level.value}")
        print(f"   Target: {vocab_per_batch} vocab + {phrasal_verbs_per_batch} phrasal + {idioms_per_batch} idioms = {vocab_per_batch + phrasal_verbs_per_batch + idioms_per_batch} total")
        
        # Calculate target total
        target_total = vocab_per_batch + phrasal_verbs_per_batch + idioms_per_batch
        
        # STEP 1: Direct generation (search removed)
        print(f"\n🔍 STEP 1: Direct vocabulary generation")
        
        # STEP 2: Pre-filter - check what already exists
        print(f"\n🔍 STEP 2: Pre-filtering - checking existing entries")
        existing_combinations = get_existing_combinations_for_topic(topic)
        print(f"Found {len(existing_combinations)} existing combinations for topic '{topic}'")
        
        # Get user seen words (if user authenticated)
        user_seen_words = set()
        if user_id:
            user_seen_words = get_user_seen_vocabularies(user_id, days_lookback=7)
            print(f"Found {len(user_seen_words)} user-seen words")
        
        # STEP 3: Generate using React Agent
        print(f"\n🚀 STEP 3: Using React Agent for generation")
        
        # Use react agent for generation
        response = generate_vocab_with_react_agent(
            topic=topic,
            level=level,
            target_language=language_to_learn,
            original_language=learners_native_language,
            vocab_per_batch=vocab_per_batch,
            phrasal_verbs_per_batch=phrasal_verbs_per_batch,
            idioms_per_batch=idioms_per_batch,
            user_id=user_id or "default_user",
            ai_role="Language Teacher"
        )
        
        # Extract all entries from the response
        attempt_entries = response.vocabularies + response.phrasal_verbs + response.idioms
        print(f"✅ React agent generated {len(attempt_entries)} entries")
        
        # Filter out duplicates and user-seen words
        filtered_entries = []
        for entry in attempt_entries:
            # Check if word is user-seen
            if user_id and entry.word.lower() in user_seen_words:
                print(f"Filtered user-seen: {entry.word}")
                continue
            
            # Check if word exists in database
            entry_key = (entry.word.lower(), entry.level.value, entry.part_of_speech.value if entry.part_of_speech else None)
            if entry_key in [(combo[0].lower(), combo[1], combo[2]) for combo in existing_combinations]:
                print(f"Filtered duplicate: {entry.word}")
                continue
            
            # Add to filtered list
            filtered_entries.append(entry)
        
        vocab_entries = filtered_entries
        print(f"✅ Final result: {len(vocab_entries)} entries after filtering")
        
        if not vocab_entries:
            print("⚠️ No vocabulary entries generated by LangGraph workflow")
            return {
                "vocabulary": [],
                "total_generated": 0,
                "new_entries_saved": 0,
                "duplicates_found": 0,
            }
        
        # No post-processing needed - filtering is done during generation
        filtered_entries = vocab_entries
        print(f"Final result: {len(filtered_entries)} entries (pre-filtered during generation)")
        
        # Save new vocabulary entries to vocab_entries table (but not to user's personal lists)
        inserted_result = None
        if filtered_entries:
            inserted_result = db.insert_vocab_entries(
                entries=filtered_entries,
                topic_name=topic,
                category_name=None,  # Will be determined by topic
                target_language=language_to_learn,
                original_language=learners_native_language
            )
            print(f"Saved {inserted_result['inserted_count']} new vocabulary entries to database")
        
        # Create response entries with actual database IDs and duplicate flags
        response_entries = []
        inserted_entries_map = {}
        
        # Create a map of inserted entries by word for quick lookup
        if inserted_result and inserted_result['inserted_entries']:
            for item in inserted_result['inserted_entries']:
                inserted_entries_map[item['entry'].word] = item['id']
        
        # Get existing entries from database for duplicates
        existing_entries_map = {}
        if filtered_entries:  # If we have entries to process, get existing entries from database
            existing_entries = db.get_vocab_entries(topic_name=topic, limit=1000)
            for existing_entry in existing_entries:
                existing_entries_map[existing_entry['word'].lower()] = existing_entry['id']
        
        for entry in filtered_entries:
            is_duplicate = False  # All entries from loop are unique
            # Use actual database ID if available (new or existing), otherwise generate a UUID
            if entry.word in inserted_entries_map:
                entry_id = inserted_entries_map[entry.word]
            elif is_duplicate and entry.word.lower() in existing_entries_map:
                entry_id = existing_entries_map[entry.word.lower()]
            else:
                entry_id = str(uuid.uuid4())
            
            response_entries.append(VocabEntryResponse(
                id=entry_id,  # Use actual database ID
                word=entry.word,
                definition=entry.definition,
                translation=entry.translation,  # Include translation
                part_of_speech=entry.part_of_speech.value if entry.part_of_speech else "unknown",
                example=entry.example,
                example_translation=entry.example_translation,
                level=entry.level.value,
                topic_name=topic,  # Include topic name
                target_language=language_to_learn,  # Include target language
                original_language=learners_native_language,  # Include original language
                is_duplicate=is_duplicate
            ))
        
        # Note: Vocabulary is saved to vocab_entries table but NOT to user's personal lists
        # Users must explicitly add items to their personal lists
        print(f"Generated {len(response_entries)} entries (saved to vocab_entries, not to personal lists)")
        
        # NEW: Track vocabularies shown to user for future deduplication
        if user_id and response_entries:
            session_id = str(uuid.uuid4())
            track_generated_vocabularies(user_id, filtered_entries, topic, level, session_id)
            
        return {
            "vocabulary": response_entries,
            "total_generated": len(response_entries),
            "new_entries_saved": len(filtered_entries),  # Count of new entries saved to vocab_entries
            "duplicates_found": len(response_entries) - len(filtered_entries),
        }
            
    except Exception as e:
        print(f"Error in single topic generation: {e}")
        raise

def generate_multiple_topics_sync(
    topics: List[str],
    level: CEFRLevel,
    language_to_learn: str,
    learners_native_language: str,
    vocab_per_batch: int,
    phrasal_verbs_per_batch: int,
    idioms_per_batch: int,
    delay_seconds: int,
    save_topic_list: bool,
    topic_list_name: Optional[str]
):
    """Generate vocabulary for multiple topics synchronously"""
    try:
        print(f"Starting multiple topics generation for: {', '.join(topics)}")
        
        # Import here to avoid circular imports
        from vocab_agent import structured_llm, db, filter_duplicates, validate_topic_relevance, get_existing_combinations_for_topic
        
        all_response_entries = []
        total_new_saved = 0
        total_duplicates = 0
        
        for topic in topics:
            print(f"\nProcessing topic: {topic}")
            
            # Get existing combinations
            existing_combinations = get_existing_combinations_for_topic(topic)
            print(f"Found {len(existing_combinations)} existing combinations")
            
            # Create prompt
            prompt = f'''You are an expert {language_to_learn} language teacher creating engaging vocabulary content for {topic}.

Generate diverse and interesting {language_to_learn} vocabulary for CEFR level {level.value}:

1. {vocab_per_batch} {language_to_learn} vocabulary words (nouns, verbs, adjectives, adverbs)
2. {phrasal_verbs_per_batch} {language_to_learn} phrasal verbs/expressions  
3. {idioms_per_batch} {language_to_learn} idioms/proverbs

Requirements:
- All words must be relevant to "{topic}"
- Include clear definitions in {language_to_learn} (the target learning language)
- Provide example sentences in {language_to_learn}
- Translate examples to {learners_native_language}
- Ensure appropriate difficulty for {level.value} level
- Avoid generic words not specific to the topic

Format as JSON with vocabularies, phrasal_verbs, and idioms arrays.'''

            # Generate vocabulary
            res = structured_llm.invoke(prompt)
            
            # Combine all entries
            all_entries = res.vocabularies + res.phrasal_verbs + res.idioms
            
            print(f"Generated {len(all_entries)} entries")
            
            # Validate topic relevance
            relevant_entries = validate_topic_relevance(all_entries, topic)
            print(f"Topic-relevant entries: {len(relevant_entries)}")
            
            # Filter out duplicates for database storage only
            filtered_entries = filter_duplicates(relevant_entries, existing_combinations)
            
            # Save new vocabulary entries to vocab_entries table (but not to user's personal lists)
            inserted_result = None
            if filtered_entries:
                inserted_result = db.insert_vocab_entries(
                    entries=filtered_entries,
                    topic_name=topic,
                    category_name=None,  # Will be determined by topic
                    target_language=language_to_learn,
                    original_language=learners_native_language
                )
                print(f"Saved {inserted_result['inserted_count']} new vocabulary entries to database")
            
            # Create response entries with actual database IDs and duplicate flags
            inserted_entries_map = {}
            
            # Create a map of inserted entries by word for quick lookup
            if inserted_result and inserted_result['inserted_entries']:
                for item in inserted_result['inserted_entries']:
                    inserted_entries_map[item['entry'].word] = item['id']
            
            # Create response entries with duplicate flags
            for entry in relevant_entries:
                is_duplicate = entry not in filtered_entries
                # Use actual database ID if available, otherwise generate a UUID
                entry_id = inserted_entries_map.get(entry.word, str(uuid.uuid4()))
                
                all_response_entries.append(VocabEntryResponse(
                    id=entry_id,  # Use actual database ID
                    word=entry.word,
                    definition=entry.definition,
                    translation=entry.translation,  # Include translation
                    part_of_speech=entry.part_of_speech.value if entry.part_of_speech else "unknown",
                    example=entry.example,
                    example_translation=entry.example_translation,
                    level=entry.level.value,
                    topic_name=topic,  # Include topic name
                    target_language=language_to_learn,  # Include target language
                    original_language=learners_native_language,  # Include original language
                    is_duplicate=is_duplicate
                ))
            
            # Note: Generated vocabulary is NOT automatically saved
            # Users must explicitly save items they want to keep
            print(f"Generated {len(relevant_entries)} entries for topic '{topic}' (not auto-saved)")
            
            total_duplicates += len(relevant_entries) - len(filtered_entries)
                
        return {
            "vocabulary": all_response_entries,
            "total_generated": len(all_response_entries),
            "new_entries_saved": 0,  # No automatic saving
            "duplicates_found": total_duplicates
        }
                
    except Exception as e:
        print(f"Error in multiple topics generation: {e}")
        raise

def generate_category_sync(
    category: str,
    level: CEFRLevel,
    language_to_learn: str,
    learners_native_language: str,
    vocab_per_batch: int,
    phrasal_verbs_per_batch: int,
    idioms_per_batch: int,
    delay_seconds: int
):
    """Generate vocabulary for category synchronously"""
    try:
        print(f"Starting category generation for: {category}")
        
        # Get topics for this category
        topics = get_topic_list(category)
        print(f"Found {len(topics)} topics in category '{category}'")
        
        # Import here to avoid circular imports
        from vocab_agent import structured_llm, db, filter_duplicates, validate_topic_relevance, get_existing_combinations_for_topic
        
        all_response_entries = []
        total_new_saved = 0
        total_duplicates = 0
        
        for topic in topics:
            print(f"\nProcessing topic: {topic}")
            
            # Get existing combinations
            existing_combinations = get_existing_combinations_for_topic(topic)
            print(f"Found {len(existing_combinations)} existing combinations")
            
            # Create prompt
            prompt = f'''You are an expert {language_to_learn} language teacher creating engaging vocabulary content for {topic}.

Generate diverse and interesting {language_to_learn} vocabulary for CEFR level {level.value}:

1. {vocab_per_batch} {language_to_learn} vocabulary words (nouns, verbs, adjectives, adverbs)
2. {phrasal_verbs_per_batch} {language_to_learn} phrasal verbs/expressions  
3. {idioms_per_batch} {language_to_learn} idioms/proverbs

Requirements:
- All words must be relevant to "{topic}"
- Include clear definitions in {language_to_learn} (the target learning language)
- Provide example sentences in {language_to_learn}
- Translate examples to {learners_native_language}
- Ensure appropriate difficulty for {level.value} level
- Avoid generic words not specific to the topic

Format as JSON with vocabularies, phrasal_verbs, and idioms arrays.'''

            # Generate vocabulary
            res = structured_llm.invoke(prompt)
            
            # Combine all entries
            all_entries = res.vocabularies + res.phrasal_verbs + res.idioms
            
            print(f"Generated {len(all_entries)} entries")
            
            # Validate topic relevance
            relevant_entries = validate_topic_relevance(all_entries, topic)
            print(f"Topic-relevant entries: {len(relevant_entries)}")
            
            # Filter out duplicates for database storage only
            filtered_entries = filter_duplicates(relevant_entries, existing_combinations)
            
            # Save new vocabulary entries to vocab_entries table (but not to user's personal lists)
            if filtered_entries:
                db.insert_vocab_entries(
                    entries=filtered_entries,
                    topic_name=topic,
                    category_name=category,  # Include category name
                    target_language=language_to_learn,
                    original_language=learners_native_language
                )
                print(f"Saved {len(filtered_entries)} new vocabulary entries to database for topic '{topic}'")
                total_new_saved += len(filtered_entries)
            
            # Create response entries with duplicate flags and include all necessary info
            for entry in relevant_entries:
                is_duplicate = entry not in filtered_entries
                all_response_entries.append(VocabEntryResponse(
                    id=str(uuid.uuid4()),  # Generate unique ID for frontend
                    word=entry.word,
                    definition=entry.definition,
                    translation=entry.translation,  # Include translation
                    part_of_speech=entry.part_of_speech.value if entry.part_of_speech else "unknown",
                    example=entry.example,
                    example_translation=entry.example_translation,
                    level=entry.level.value,
                    topic_name=topic,  # Include topic name
                    target_language=language_to_learn,  # Include target language
                    original_language=learners_native_language,  # Include original language
                    is_duplicate=is_duplicate
                ))
            
            # Note: Vocabulary is saved to vocab_entries table but NOT to user's personal lists
            # Users must explicitly add items to their personal lists
            print(f"Generated {len(relevant_entries)} entries for topic '{topic}' (saved to vocab_entries, not to personal lists)")
            
            total_duplicates += len(relevant_entries) - len(filtered_entries)
                
        return {
            "vocabulary": all_response_entries,
            "total_generated": len(all_response_entries),
            "new_entries_saved": total_new_saved,  # Count of new entries saved to vocab_entries
            "duplicates_found": total_duplicates
        }
                
    except Exception as e:
        print(f"Error in category generation: {e}")
        raise

# =========== API Endpoints ===========

@app.get("/", tags=["Root"])
async def root():
    """Root endpoint with API information"""
    return {
        "message": "AI Vocabulary Generator API - Comprehensive",
        "version": "11.0.0",
        "docs": "/docs",
        "status": "running",
        "available_endpoints": [
            "POST /generate/single - Generate for single topic",
            "POST /generate/multiple - Generate for multiple topics",
            "POST /generate/category - Generate for category",
            "GET /categories - Get all categories",
            "GET /topics/{category} - Get topics by category",
            "GET /topics - Get all topics"
        ]
    }

@app.get("/health", tags=["Health"])
async def health_check():
    """Health check endpoint"""
    return {"status": "healthy", "timestamp": "2025-08-02T16:00:00.000Z"}

@app.post("/test/create-user", tags=["Testing"])
async def create_test_user(current_user: str = Depends(get_current_user)):
    """Create a test user for testing purposes"""
    try:
        # Check if user already exists
        result = db.client.table("profiles").select("id").eq("id", current_user).execute()
        
        if result.data:
            return {
                "success": True,
                "message": "User already exists",
                "user_id": current_user
            }
        
        # Create test user
        user_data = {
            "id": current_user,
            "email": f"test-{current_user}@example.com",
            "created_at": datetime.now().isoformat(),
            "updated_at": datetime.now().isoformat()
        }
        
        result = db.client.table("profiles").insert(user_data).execute()
        
        if result.data:
            return {
                "success": True,
                "message": "Test user created successfully",
                "user_id": current_user
            }
        else:
            raise HTTPException(status_code=500, detail="Failed to create test user")
            
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error creating test user: {str(e)}")

@app.post("/generate/single", response_model=GenerateResponse, tags=["Generation"])
async def generate_single_topic(
    request: GenerateSingleRequest,
    current_user: str = Depends(get_current_user)
):
    """Generate vocabulary for a single topic with user deduplication"""
    try:
        # Generate vocabulary synchronously with user context
        result = generate_single_topic_sync(
            topic=request.topic,
            level=request.level,
            language_to_learn=request.language_to_learn,
            learners_native_language=request.learners_native_language,
            vocab_per_batch=request.vocab_per_batch,
            phrasal_verbs_per_batch=request.phrasal_verbs_per_batch,
            idioms_per_batch=request.idioms_per_batch,
            delay_seconds=request.delay_seconds,
            save_topic_list=request.save_topic_list,
            topic_list_name=request.topic_list_name,
            user_id=current_user,
        )
        
        # Award points for vocabulary generation
        points_result = vocab_points.award_vocab_generation_points(
            user_name=current_user,
            words_generated=result["total_generated"],
            level=request.level.value,
            session_duration=0  # Could be calculated from start/end time
        )
        
        return GenerateResponse(
            success=True,
            message=f"Generated vocabulary for topic '{request.topic}' at {request.level.value} level",
            method="single_topic",
            details={
                "topic": request.topic,
                "level": request.level.value,
                "language_to_learn": request.language_to_learn,
                "learners_native_language": request.learners_native_language,
                "points_awarded": points_result.get("points", 0) if points_result.get("success") else 0
            },
            generated_vocabulary=result["vocabulary"],
            total_generated=result["total_generated"],
            new_entries_saved=result["new_entries_saved"],
            duplicates_found=result["duplicates_found"],
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Generation failed: {str(e)}")

@app.post("/generate/multiple", response_model=GenerateResponse, tags=["Generation"])
async def generate_multiple_topics(request: GenerateMultipleRequest):
    """Generate vocabulary for multiple topics"""
    try:
        # Generate vocabulary synchronously
        result = generate_multiple_topics_sync(
            topics=request.topics,
            level=request.level,
            language_to_learn=request.language_to_learn,
            learners_native_language=request.learners_native_language,
            vocab_per_batch=request.vocab_per_batch,
            phrasal_verbs_per_batch=request.phrasal_verbs_per_batch,
            idioms_per_batch=request.idioms_per_batch,
            delay_seconds=request.delay_seconds,
            save_topic_list=request.save_topic_list,
            topic_list_name=request.topic_list_name
        )
        
        # Award points for vocabulary generation (multiple topics)
        points_result = vocab_points.award_vocab_generation_points(
            user_name="system",  # Multiple topics don't have a specific user
            words_generated=result["total_generated"],
            level=request.level.value,
            session_duration=0
        )
        
        return GenerateResponse(
            success=True,
            message=f"Generated vocabulary for {len(request.topics)} topics at {request.level.value} level",
            method="multiple_topics",
            details={
                "topics": request.topics,
                "level": request.level.value,
                "language_to_learn": request.language_to_learn,
                "learners_native_language": request.learners_native_language,
                "points_awarded": points_result.get("points", 0) if points_result.get("success") else 0
            },
            generated_vocabulary=result["vocabulary"],
            total_generated=result["total_generated"],
            new_entries_saved=result["new_entries_saved"],
            duplicates_found=result["duplicates_found"]
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Generation failed: {str(e)}")

@app.post("/generate/category", response_model=GenerateResponse, tags=["Generation"])
async def generate_category(request: GenerateCategoryRequest):
    """Generate vocabulary for all topics in a category"""
    try:
        # Validate category
        categories = get_categories()
        if request.category not in categories:
            raise HTTPException(
                status_code=400, 
                detail=f"Invalid category '{request.category}'. Available categories: {categories}"
            )
        
        # Generate vocabulary synchronously
        result = generate_category_sync(
            category=request.category,
            level=request.level,
            language_to_learn=request.language_to_learn,
            learners_native_language=request.learners_native_language,
            vocab_per_batch=request.vocab_per_batch,
            phrasal_verbs_per_batch=request.phrasal_verbs_per_batch,
            idioms_per_batch=request.idioms_per_batch,
            delay_seconds=request.delay_seconds
        )
        
        # Award points for vocabulary generation (category)
        points_result = vocab_points.award_vocab_generation_points(
            user_name="system",  # Category generation doesn't have a specific user
            words_generated=result["total_generated"],
            level=request.level.value,
            session_duration=0
        )
        
        return GenerateResponse(
            success=True,
            message=f"Generated vocabulary for category '{request.category}' at {request.level.value} level",
            method="category",
            details={
                "category": request.category,
                "level": request.level.value,
                "language_to_learn": request.language_to_learn,
                "learners_native_language": request.learners_native_language,
                "points_awarded": points_result.get("points", 0) if points_result.get("success") else 0
            },
            generated_vocabulary=result["vocabulary"],
            total_generated=result["total_generated"],
            new_entries_saved=result["new_entries_saved"],
            duplicates_found=result["duplicates_found"]
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Generation failed: {str(e)}")

@app.get("/categories", response_model=CategoryResponse, tags=["Topics"])
async def get_categories_endpoint():
    """Get all available topic categories"""
    try:
        categories = get_categories()
        return CategoryResponse(categories=categories)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get categories: {str(e)}")

@app.get("/topics/{category}", response_model=TopicListResponse, tags=["Topics"])
async def get_topics_by_category_endpoint(category: str):
    """Get topics for a specific category"""
    try:
        topic_list = get_topics_by_category(category)
        return TopicListResponse(
            topics=topic_list.topics,
            description=topic_list.description
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get topics: {str(e)}")

@app.get("/topics", response_model=TopicListResponse, tags=["Topics"])
async def get_all_topics_endpoint():
    """Get all available topics"""
    try:
        all_topics = get_topic_list()
        return TopicListResponse(
            topics=all_topics,
            description="All available topics from all categories"
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get topics: {str(e)}")

@app.post("/vocab/save", tags=["User Vocabulary"])
async def save_vocab_entry(
    request: dict,
    current_user: str = Depends(get_current_user)
):
    """Save a vocabulary entry to the database"""
    try:
        # Extract vocabulary data from request
        vocab_data = {
            "word": request["word"],
            "definition": request["definition"],
            "translation": request["translation"],
            "example": request["example"],
            "example_translation": request["example_translation"],
            "level": request["level"],
            "part_of_speech": request["part_of_speech"],
            "topic_name": request.get("topic_name"),
            "category_name": request.get("category_name"),
            "target_language": request.get("target_language", "English"),
            "original_language": request.get("original_language", "Vietnamese")
        }
        
        # Create VocabEntry object
        from models import VocabEntry, CEFRLevel, PartOfSpeech
        vocab_entry = VocabEntry(
            word=vocab_data["word"],
            definition=vocab_data["definition"],
            translation=vocab_data["translation"],
            example=vocab_data["example"],
            example_translation=vocab_data["example_translation"],
            level=CEFRLevel(vocab_data["level"]),
            part_of_speech=PartOfSpeech(vocab_data["part_of_speech"]) if vocab_data["part_of_speech"] else None
        )
        
        # Save to database using the new user-specific method
        saved_id = db.save_vocab_to_user(
            user_id=current_user,
            vocab_entry=vocab_entry,
            topic_name=vocab_data["topic_name"],
            category_name=vocab_data["category_name"],
            target_language=vocab_data["target_language"],
            original_language=vocab_data["original_language"]
        )
        
        return {
            "success": True,
            "message": f"Vocabulary '{vocab_data['word']}' saved successfully",
            "vocab_entry_id": saved_id
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to save vocabulary: {str(e)}")

@app.post("/vocab/save-by-id", tags=["User Vocabulary"])
async def save_vocab_by_id(
    request: dict,
    current_user: str = Depends(get_current_user)
):
    """Save an existing vocabulary entry to user's personal vocabulary by ID"""
    try:
        vocab_entry_id = request["vocab_entry_id"]
        
        # Get the vocabulary entry from the database
        result = db.client.table("vocab_entries").select("*").eq("id", vocab_entry_id).execute()
        
        if not result.data:
            raise HTTPException(status_code=404, detail="Vocabulary entry not found")
        
        vocab_data = result.data[0]
        
        # Create VocabEntry object
        from models import VocabEntry, CEFRLevel, PartOfSpeech
        
        vocab_entry = VocabEntry(
            word=vocab_data["word"],
            definition=vocab_data["definition"],
            translation=vocab_data["translation"],
            example=vocab_data["example"],
            example_translation=vocab_data["example_translation"],
            level=CEFRLevel(vocab_data["level"]),
            part_of_speech=PartOfSpeech(vocab_data["part_of_speech"]) if vocab_data["part_of_speech"] else None
        )
        
        # Save to user's vocabulary
        saved_id = db.save_vocab_to_user(
            user_id=current_user,
            vocab_entry=vocab_entry,
            topic_name=vocab_data.get("topic_name"),
            category_name=vocab_data.get("category_name"),
            target_language=vocab_data.get("target_language", "English"),
            original_language=vocab_data.get("original_language", "Vietnamese")
        )
        
        return {
            "success": True,
            "message": f"Vocabulary '{vocab_data['word']}' saved to your personal vocabulary",
            "vocab_entry_id": saved_id
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to save vocabulary: {str(e)}")

@app.post("/vocab/test-save", tags=["Testing"])
async def test_save_vocab(current_user: str = Depends(get_current_user)):
    """Test endpoint to save a sample vocabulary entry"""
    try:
        # Create a test vocabulary entry
        from models import VocabEntry, CEFRLevel, PartOfSpeech
        
        test_vocab = VocabEntry(
            word="test_word",
            definition="A test definition",
            translation="Test translation",
            example="This is a test example.",
            example_translation="Đây là một ví dụ thử nghiệm.",
            level=CEFRLevel.A2,
            part_of_speech=PartOfSpeech.NOUN
        )
        
        # Save to user's vocabulary
        saved_id = db.save_vocab_to_user(
            user_id=current_user,
            vocab_entry=test_vocab,
            topic_name="Testing",
            category_name="Test Category",
            target_language="English",
            original_language="Vietnamese"
        )
        
        return {
            "success": True,
            "message": "Test vocabulary saved successfully",
            "vocab_entry_id": saved_id,
            "user_id": current_user
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Test save failed: {str(e)}")

@app.get("/vocab/test-list", tags=["Testing"])
async def test_list_vocab(current_user: str = Depends(get_current_user)):
    """Test endpoint to list user's saved vocabulary"""
    try:
        # Get user's saved vocabulary
        result = db.get_user_saved_vocab_entries(current_user)
        
        return {
            "success": True,
            "message": f"Found {len(result)} saved vocabulary entries",
            "vocabularies": result,
            "user_id": current_user
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Test list failed: {str(e)}")

@app.get("/vocab/test-list-hidden", tags=["Testing"])
async def test_list_vocab_with_hidden(current_user: str = Depends(get_current_user)):
    """Test endpoint to list user's saved vocabulary including hidden items"""
    try:
        # Get user's saved vocabulary including hidden items
        result = db.get_user_saved_vocab_entries(current_user, show_hidden=True)
        
        return {
            "success": True,
            "message": f"Found {len(result)} saved vocabulary entries (including hidden)",
            "vocabularies": result,
            "user_id": current_user
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Test list with hidden failed: {str(e)}")

@app.post("/vocab/test-review", tags=["Testing"])
async def test_review_vocab(
    request: dict,
    current_user: str = Depends(get_current_user)
):
    """Test endpoint to mark vocabulary as reviewed"""
    try:
        vocab_entry_id = request.get("vocab_entry_id")
        action = request.get("action", "review")
        
        if action == "unreview":
            db.undo_review(current_user, vocab_entry_id)
            message = "Test: Vocabulary unmarked as reviewed"
        else:
            db.mark_as_reviewed(current_user, vocab_entry_id)
            message = "Test: Vocabulary marked as reviewed"
        
        return {
            "success": True,
            "message": message,
            "vocab_entry_id": vocab_entry_id,
            "action": action,
            "user_id": current_user
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Test review failed: {str(e)}")

@app.post("/vocab/review/undo", tags=["User Vocabulary"])
async def undo_review(
    request: VocabEntryActionRequest,
    current_user: str = Depends(get_current_user)
):
    """Undo review - reset review count to 0"""
    try:
        db.undo_review(current_user, request.vocab_entry_id)
        
        return {
            "success": True,
            "message": "Review progress reset to 0"
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to undo review: {str(e)}")

@app.post("/vocab/review-toggle", tags=["User Vocabulary"])
async def review_toggle_vocab_entry(
    request: dict,
    current_user: str = Depends(get_current_user)
):
    """Toggle review status for a vocabulary entry"""
    try:
        # Ensure user exists in profiles table
        await ensure_user_exists(current_user)
        
        vocab_entry_id = request.get("vocab_entry_id")
        action = request.get("action", "review")  # Default to review
        
        if action == "unreview":
            # Unmark as reviewed (reset review count to 0)
            db.undo_review(current_user, vocab_entry_id)
            
            return {
                "success": True,
                "message": "Vocabulary unmarked as reviewed",
                "review_count": 0,
                "last_reviewed": None,
                "is_reviewed": False
            }
        else:
            # Mark as reviewed (increment review count)
            db.mark_as_reviewed(current_user, vocab_entry_id)
            
            # Get the updated review count from database
            try:
                user_vocab_result = db.client.table("user_vocab_entries").select("review_count, last_reviewed").eq("user_id", current_user).eq("vocab_entry_id", vocab_entry_id).execute()
                if user_vocab_result.data:
                    review_count = user_vocab_result.data[0].get("review_count", 1)
                    last_reviewed = user_vocab_result.data[0].get("last_reviewed")
                else:
                    review_count = 1
                    last_reviewed = datetime.now().isoformat()
            except:
                review_count = 1
                last_reviewed = datetime.now().isoformat()
            
            return {
                "success": True,
                "message": "Vocabulary marked as reviewed",
                "review_count": review_count,
                "last_reviewed": last_reviewed,
                "is_reviewed": True
            }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to toggle review status: {str(e)}")

# =========== ADVANCED FLASHCARD SYSTEM ENDPOINTS ===========

@app.post("/flashcard/session/create", response_model=FlashcardSessionResponse, tags=["Flashcards"])
async def create_flashcard_session(
    request: FlashcardSessionRequest,
    current_user: str = Depends(get_current_user)
):
    """Create a new advanced flashcard study session"""
    try:
        # Ensure user exists in profiles table
        await ensure_user_exists(current_user)
        
        session_id = db.create_flashcard_session(current_user, request)
        
        # Get the created session
        session_data = db.get_flashcard_session(session_id)
        
        # Get the first card
        current_card = db.get_current_flashcard(session_id)
        
        return FlashcardSessionResponse(
            success=True,
            message=f"Advanced flashcard session '{request.session_name}' created successfully",
            session=session_data,
            current_card=current_card,
            progress={
                "current_card": 0,
                "total_cards": session_data["total_cards"] if session_data else 0,
                "correct_answers": 0,
                "incorrect_answers": 0,
                "skipped_cards": 0
            }
        )
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to create flashcard session: {str(e)}")

@app.post("/test/flashcard/session/create", tags=["Testing"])
async def create_test_flashcard_session(
    request: FlashcardSessionRequest,
    current_user: str = Depends(get_current_user)
):
    """Create a test flashcard session that works with existing vocabulary entries"""
    try:
        # Use the current authenticated user instead of hardcoded test user
        await ensure_user_exists(current_user)
        
        session_id = db.create_test_flashcard_session(current_user, request)
        
        # Get the created session
        session_data = db.get_flashcard_session(session_id)
        
        # Get the first card
        current_card = db.get_current_flashcard(session_id)
        
        return {
            "success": True,
            "message": f"Test flashcard session '{request.session_name}' created successfully",
            "session_id": session_id,
            "session": session_data,
            "current_card": current_card,
            "progress": {
                "current_card": 0,
                "total_cards": session_data["total_cards"] if session_data else 0,
                "correct_answers": 0,
                "incorrect_answers": 0,
                "skipped_cards": 0
            }
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to create test flashcard session: {str(e)}")

@app.get("/test/flashcard/answer", tags=["Testing"])
async def test_flashcard_answer_validation(
    user_answer: str,
    correct_answer: str,
    study_mode: str = "practice"
):
    """Test the flashcard answer validation logic without database"""
    try:
        # Test the validation logic directly
        is_correct = db._validate_answer(user_answer, correct_answer, study_mode)
        
        return {
            "success": True,
            "user_answer": user_answer,
            "correct_answer": correct_answer,
            "study_mode": study_mode,
            "is_correct": is_correct,
            "message": "Answer validation test completed"
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to test answer validation: {str(e)}")

@app.get("/flashcard/session/{session_id}/current", tags=["Flashcards"])
async def get_current_flashcard_endpoint(
    session_id: str,
    current_user: str = Depends(get_current_user)
):
    """Get the current flashcard for a session"""
    try:
        # Verify session belongs to user
        session = db.get_flashcard_session(session_id)
        if not session or session["user_id"] != current_user:
            raise HTTPException(status_code=404, detail="Session not found")
        
        current_card = db.get_current_flashcard(session_id)
        
        if not current_card:
            return {
                "success": True,
                "message": "Session completed",
                "session_complete": True,
                "progress": {
                    "current_card": session["current_card_index"],
                    "total_cards": session["total_cards"],
                    "correct_answers": session["correct_answers"],
                    "incorrect_answers": session["incorrect_answers"],
                    "skipped_cards": session["skipped_cards"]
                }
            }
        
        return {
            "success": True,
            "message": "Current flashcard retrieved",
            "current_card": current_card,
            "session_complete": False
        }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get current flashcard: {str(e)}")

@app.post("/flashcard/session/{session_id}/answer", tags=["Flashcards"])
async def submit_flashcard_answer(
    session_id: str,
    request: FlashcardAnswerRequest,
    current_user: str = Depends(get_current_user)
):
    """Submit an answer for a flashcard with advanced processing"""
    try:
        # Verify session belongs to user
        session = db.get_flashcard_session(session_id)
        if not session or session["user_id"] != current_user:
            raise HTTPException(status_code=404, detail="Session not found")
        
        # If vocab_entry_id is not provided, get it from the current card
        if not request.vocab_entry_id:
            current_card = db.get_current_flashcard(session_id)
            if not current_card:
                raise HTTPException(status_code=400, detail="No current card available")
            request.vocab_entry_id = current_card["vocab_entry_id"]
        
        result = db.submit_flashcard_answer_advanced(session_id, request)
        
        # Check if session is completed and award points
        if result.get("session_complete", False):
            session = db.get_flashcard_session(session_id)
            if session:
                # Calculate difficulty based on session settings
                difficulty = "medium"  # Default difficulty
                if hasattr(request, 'difficulty') and request.difficulty:
                    difficulty = request.difficulty.value.lower()
                
                # Award points for flashcard review
                points_result = flashcard_points.award_flashcard_review_points(
                    user_name=current_user,
                    cards_reviewed=session.get("total_cards", 0),
                    difficulty=difficulty,
                    mastery_achieved=session.get("correct_answers", 0) >= session.get("total_cards", 0) * 0.8,
                    streak_days=0  # Could be calculated from user's streak data
                )
                
                # Add points info to result
                result["points_awarded"] = points_result.get("points", 0) if points_result.get("success") else 0
                result["points_success"] = points_result.get("success", False)
        
        return {
            "success": True,
            "message": "Answer submitted successfully",
            "result": result
        }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to submit answer: {str(e)}")

@app.get("/flashcard/analytics", tags=["Flashcards"])
async def get_flashcard_analytics(
    days: int = 30,
    current_user: str = Depends(get_current_user)
):
    """Get comprehensive flashcard analytics"""
    try:
        analytics = db.get_flashcard_analytics(current_user, days)
        
        return {
            "success": True,
            "message": f"Analytics for last {days} days",
            "analytics": analytics
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get analytics: {str(e)}")

@app.get("/flashcard/study-modes", tags=["Flashcards"])
async def get_study_modes():
    """Get available study modes with descriptions"""
    return {
        "success": True,
        "message": "Available study modes",
        "study_modes": [
            {
                "value": StudyMode.REVIEW.value,
                "name": "Review Mode",
                "description": "Show definition, guess the word",
                "icon": "🔍"
            },
            {
                "value": StudyMode.PRACTICE.value,
                "name": "Practice Mode", 
                "description": "Show word, guess the definition",
                "icon": "💭"
            },
            {
                "value": StudyMode.TEST.value,
                "name": "Test Mode",
                "description": "Multiple choice questions",
                "icon": "📝"
            },
            {
                "value": StudyMode.WRITE.value,
                "name": "Write Mode",
                "description": "Type the answer",
                "icon": "✍️"
            },
            {
                "value": StudyMode.LISTEN.value,
                "name": "Listen Mode",
                "description": "Audio pronunciation practice",
                "icon": "🎧"
            },
            {
                "value": StudyMode.SPELLING.value,
                "name": "Spelling Mode",
                "description": "Spell the word correctly",
                "icon": "🔤"
            },
            {
                "value": StudyMode.SYNONYMS.value,
                "name": "Synonyms Mode",
                "description": "Find synonyms for the word",
                "icon": "🔄"
            },
            {
                "value": StudyMode.ANTONYMS.value,
                "name": "Antonyms Mode",
                "description": "Find antonyms for the word",
                "icon": "↔️"
            },
            {
                "value": StudyMode.CONTEXT.value,
                "name": "Context Mode",
                "description": "Fill in the blank in context",
                "icon": "📖"
            },
            {
                "value": StudyMode.MIXED.value,
                "name": "Mixed Mode",
                "description": "Random combination of all modes",
                "icon": "🎲"
            }
        ]
    }

@app.get("/flashcard/session-types", tags=["Flashcards"])
async def get_session_types():
    """Get available session types"""
    return {
        "success": True,
        "message": "Available session types",
        "session_types": [
            {
                "value": SessionType.DAILY_REVIEW.value,
                "name": "Daily Review",
                "description": "Review overdue and new cards",
                "icon": "📅"
            },
            {
                "value": SessionType.TOPIC_FOCUS.value,
                "name": "Topic Focus",
                "description": "Focus on specific topic vocabulary",
                "icon": "🎯"
            },
            {
                "value": SessionType.LEVEL_PROGRESSION.value,
                "name": "Level Progression",
                "description": "Progressive difficulty levels",
                "icon": "📈"
            },
            {
                "value": SessionType.WEAK_AREAS.value,
                "name": "Weak Areas",
                "description": "Focus on difficult vocabulary",
                "icon": "💪"
            },
            {
                "value": SessionType.RANDOM.value,
                "name": "Random",
                "description": "Random selection of cards",
                "icon": "🎲"
            },
            {
                "value": SessionType.CUSTOM.value,
                "name": "Custom",
                "description": "Customized session settings",
                "icon": "⚙️"
            }
        ]
    }

@app.get("/flashcard/difficulty-ratings", tags=["Flashcards"])
async def get_difficulty_ratings():
    """Get available difficulty ratings"""
    return {
        "success": True,
        "message": "Available difficulty ratings",
        "difficulty_ratings": [
            {
                "value": DifficultyRating.EASY.value,
                "name": "Easy",
                "description": "I knew this well",
                "color": "green",
                "icon": "😊"
            },
            {
                "value": DifficultyRating.MEDIUM.value,
                "name": "Medium",
                "description": "I knew this but took some time",
                "color": "yellow",
                "icon": "😐"
            },
            {
                "value": DifficultyRating.HARD.value,
                "name": "Hard",
                "description": "I struggled with this",
                "color": "orange",
                "icon": "😰"
            },
            {
                "value": DifficultyRating.AGAIN.value,
                "name": "Again",
                "description": "I need to review this again soon",
                "color": "red",
                "icon": "😵"
            }
        ]
    }

@app.post("/flashcard/quick-session", tags=["Flashcards"])
async def create_quick_flashcard_session(
    request: dict,
    current_user: str = Depends(get_current_user)
):
    """Create a quick flashcard session with smart defaults"""
    try:
        # Ensure user exists in profiles table
        await ensure_user_exists(current_user)
        
        # Create request with smart defaults
        session_request = FlashcardSessionRequest(
            session_name=f"Quick Session - {datetime.now().strftime('%H:%M')}",
            session_type=SessionType(request.get("session_type", "daily_review")),
            study_mode=StudyMode(request.get("study_mode", "mixed")),
            topic_name=request.get("topic_name"),
            category_name=request.get("category_name"),
            level=CEFRLevel(request.get("level")) if request.get("level") else None,
            max_cards=request.get("max_cards", 10),
            time_limit_minutes=request.get("time_limit_minutes"),
            include_reviewed=request.get("include_reviewed", False),
            include_favorites=request.get("include_favorites", False),
            smart_selection=request.get("smart_selection", True)
        )
        
        session_id = db.create_flashcard_session(current_user, session_request)
        
        # Get the created session and first card
        session_data = db.get_flashcard_session(session_id)
        current_card = db.get_current_flashcard(session_id)
        
        return {
            "success": True,
            "message": f"Quick {session_request.study_mode.value} session created",
            "session_id": session_id,
            "session": session_data,
            "current_card": current_card
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to create quick session: {str(e)}")

@app.get("/flashcard/sessions", tags=["Flashcards"])
async def get_flashcard_sessions(
    limit: int = 50,
    current_user: str = Depends(get_current_user)
):
    """Get user's flashcard sessions"""
    try:
        sessions = db.get_flashcard_sessions(current_user, limit)
        
        return {
            "success": True,
            "message": f"Retrieved {len(sessions)} flashcard sessions",
            "sessions": sessions
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get flashcard sessions: {str(e)}")

@app.get("/flashcard/session/{session_id}", tags=["Flashcards"])
async def get_flashcard_session(
    session_id: str,
    current_user: str = Depends(get_current_user)
):
    """Get a specific flashcard session"""
    try:
        session = db.get_flashcard_session(session_id)
        
        if not session or session["user_id"] != current_user:
            raise HTTPException(status_code=404, detail="Session not found")
        
        return {
            "success": True,
            "message": "Session retrieved successfully",
            "session": session
        }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get session: {str(e)}")

@app.delete("/flashcard/session/{session_id}", tags=["Flashcards"])
async def delete_flashcard_session(
    session_id: str,
    current_user: str = Depends(get_current_user)
):
    """Delete a flashcard session"""
    try:
        success = db.delete_flashcard_session(session_id, current_user)
        
        if not success:
            raise HTTPException(status_code=404, detail="Session not found")
        
        return {
            "success": True,
            "message": "Session deleted successfully"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to delete session: {str(e)}")

@app.get("/flashcard/stats", response_model=FlashcardStats, tags=["Flashcards"])
async def get_flashcard_stats(current_user: str = Depends(get_current_user)):
    """Get flashcard statistics for the user"""
    try:
        stats = db.get_flashcard_stats(current_user)
        
        return FlashcardStats(**stats)
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get flashcard stats: {str(e)}")

@app.get("/user/profile", tags=["User Management"])
async def get_user_profile(current_user: str = Depends(get_current_user)):
    """Get current user profile information"""
    try:
        # Ensure user exists
        await ensure_user_exists(current_user)
        
        # Get user profile
        result = db.client.table("profiles").select("*").eq("id", current_user).execute()
        
        if result.data:
            return {
                "success": True,
                "message": "User profile retrieved successfully",
                "user_id": current_user,
                "profile": result.data[0]
            }
        else:
            raise HTTPException(status_code=404, detail="User profile not found")
            
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get user profile: {str(e)}")

@app.get("/vocab/discover", tags=["Vocabulary Discovery"])
async def discover_vocabulary(
    topic_name: str = None,
    category_name: str = None,
    level: str = None,
    limit: int = 20,
    current_user: str = Depends(get_current_user)
):
    """Discover vocabulary from global pool that user hasn't saved yet"""
    try:
        await ensure_user_exists(current_user)
        
        # Get global vocabulary entries
        from models import CEFRLevel
        level_enum = CEFRLevel(level) if level else None
        
        result = db.get_vocab_entries(
            topic_name=topic_name,
            category_name=category_name,
            level=level_enum,
            limit=limit * 2  # Get more to filter out user's saved ones
        )
        
        if not result:
            return {
                "success": True,
                "message": "No vocabulary found for the specified criteria",
                "vocabulary": [],
                "total_found": 0
            }
        
        # Get user's saved vocabulary IDs to filter them out
        user_saved_result = db.client.table("user_vocab_entries").select("vocab_entry_id").eq("user_id", current_user).execute()
        user_saved_ids = {row["vocab_entry_id"] for row in user_saved_result.data} if user_saved_result.data else set()
        
        # Filter out already saved vocabulary
        available_vocab = []
        for entry in result:
            if entry["id"] not in user_saved_ids:
                available_vocab.append({
                    "id": entry["id"],
                    "word": entry["word"],
                    "definition": entry["definition"],
                    "translation": entry["translation"],
                    "example": entry["example"],
                    "example_translation": entry["example_translation"],
                    "level": entry["level"],
                    "part_of_speech": entry["part_of_speech"],
                    "topic_name": topic_name,
                    "target_language": entry.get("target_language"),
                    "original_language": entry.get("original_language")
                })
                
                if len(available_vocab) >= limit:
                    break
        
        return {
            "success": True,
            "message": f"Found {len(available_vocab)} new vocabulary items to discover",
            "vocabulary": available_vocab,
            "total_found": len(available_vocab)
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to discover vocabulary: {str(e)}")

@app.get("/flashcard/review-cards", tags=["Flashcards"])
async def get_cards_for_review(
    limit: int = 20,
    current_user: str = Depends(get_current_user)
):
    """Get cards that are due for review based on spaced repetition"""
    try:
        cards = db.get_cards_for_review(current_user, limit)
        
        return {
            "success": True,
            "message": f"Found {len(cards)} cards due for review",
            "cards": cards
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get review cards: {str(e)}")

# =========== CACHE MANAGEMENT ENDPOINTS ===========

@app.get("/cache/stats", tags=["Cache Management"])
async def get_cache_statistics():
    """Get validation cache performance statistics"""
    try:
        from semantic_validator import semantic_validator
        stats = semantic_validator.get_cache_stats()
        
        return {
            "success": True,
            "message": "Cache statistics retrieved successfully",
            "cache_stats": stats
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get cache statistics: {str(e)}")

@app.post("/cache/clear", tags=["Cache Management"])
async def clear_validation_cache(older_than_hours: Optional[int] = None):
    """Clear validation cache entries"""
    try:
        from semantic_validator import semantic_validator
        
        if older_than_hours:
            semantic_validator.clear_cache(older_than_hours)
            message = f"Cleared cache entries older than {older_than_hours} hours"
        else:
            semantic_validator.clear_cache()
            message = "Cleared all cache entries"
        
        return {
            "success": True,
            "message": message
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to clear cache: {str(e)}")

@app.post("/cache/cleanup", tags=["Cache Management"])
async def cleanup_expired_cache():
    """Remove expired entries from validation cache"""
    try:
        from semantic_validator import semantic_validator
        semantic_validator.cleanup_expired_cache()
        
        return {
            "success": True,
            "message": "Expired cache entries cleaned up successfully"
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to cleanup cache: {str(e)}")

@app.get("/cache/performance", tags=["Cache Management"])
async def get_cache_performance_summary():
    """Get a summary of cache performance and cost savings"""
    try:
        from semantic_validator import semantic_validator
        stats = semantic_validator.get_cache_stats()
        
        # Calculate cost savings (assuming $0.01 per AI call)
        ai_calls = stats.get('ai_calls', 0)
        total_requests = stats.get('total_requests', 0)
        cache_hit_rate = stats.get('cache_hit_rate', 0)
        
        # Estimate cost savings
        estimated_cost_per_call = 0.01  # $0.01 per AI call
        total_ai_calls_without_cache = total_requests
        actual_ai_calls = ai_calls
        cost_savings = (total_ai_calls_without_cache - actual_ai_calls) * estimated_cost_per_call
        
        return {
            "success": True,
            "message": "Cache performance summary retrieved successfully",
            "performance_summary": {
                "total_requests": total_requests,
                "ai_calls_made": actual_ai_calls,
                "cache_hit_rate": f"{cache_hit_rate:.1f}%",
                "ai_call_reduction": f"{((total_requests - actual_ai_calls) / total_requests * 100):.1f}%" if total_requests > 0 else "0%",
                "estimated_cost_savings": f"${cost_savings:.2f}",
                "exact_matches": stats.get('exact_matches', 0),
                "similarity_matches": stats.get('similarity_matches', 0),
                "memory_cache_hits": stats.get('memory_hits', 0),
                "database_cache_hits": stats.get('db_hits', 0),
                "memory_cache_size": stats.get('memory_cache_size', 0),
                "database_cache_size": stats.get('db_cache_size', 0)
            }
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get performance summary: {str(e)}")

@app.get("/cache/quality", tags=["Cache Management"])
async def validate_cache_quality(sample_size: int = 100):
    """Validate cache quality to ensure fairness and accuracy across different answer variations"""
    try:
        from semantic_validator import semantic_validator
        quality_report = semantic_validator.validate_cache_quality(sample_size)
        
        return {
            "success": True,
            "message": "Cache quality validation completed",
            "quality_report": quality_report
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to validate cache quality: {str(e)}")

# =========== TTS (TEXT-TO-SPEECH) ENDPOINTS ===========

@app.post("/tts/generate", response_model=TTSResponse, tags=["TTS"])
async def generate_tts(
    request: TTSRequest,
    auth_data: tuple = Depends(get_current_user_and_client)
):
    """Generate TTS audio for vocabulary or custom text"""
    try:
        current_user, authenticated_client = auth_data
        response = await tts_service.generate_tts(request, current_user, authenticated_client)
        return response
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"TTS generation failed: {str(e)}")

@app.post("/tts/generate-vocab/{vocab_entry_id}", response_model=TTSResponse, tags=["TTS"])
async def generate_vocab_tts(
    vocab_entry_id: str,
    current_user: str = Depends(get_current_user),
    voice_id: Optional[str] = None,
    language: str = "en-US"
):
    """Generate TTS audio for a specific vocabulary entry"""
    try:
        # Get vocabulary entry
        result = db.client.table("vocab_entries").select("*").eq("id", vocab_entry_id).execute()
        if not result.data:
            raise HTTPException(status_code=404, detail="Vocabulary entry not found")
        
        vocab_entry = result.data[0]
        
        # Use pronunciation service instead of direct TTS service
        pronunciation_request = PronunciationRequest(
            vocab_entry_id=vocab_entry_id,
            text=vocab_entry["word"],
            language=language,
            versions=[PronunciationType.NORMAL],
            voice_id=voice_id
        )
        
        pronunciation_response = await pronunciation_service.generate_pronunciations(pronunciation_request, current_user)
        
        if not pronunciation_response.success:
            raise HTTPException(status_code=500, detail=pronunciation_response.message)
        
        # Convert pronunciation response to TTS response format
        if pronunciation_response.pronunciations and pronunciation_response.pronunciations.versions:
            normal_version = pronunciation_response.pronunciations.versions.get(PronunciationType.NORMAL)
            if normal_version:
                return TTSResponse(
                    success=True,
                    message="TTS generated successfully",
                    audio_url=normal_version.audio_url,
                    duration_seconds=normal_version.duration_seconds,
                    provider=normal_version.provider,
                    voice_id=normal_version.voice_id
                )
        
        raise HTTPException(status_code=500, detail="No pronunciation version generated")
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Vocabulary TTS generation failed: {str(e)}")

@app.post("/tts/voice-clone", response_model=VoiceCloneResponse, tags=["TTS"])
async def create_voice_clone(
    request: VoiceCloneRequest,
    current_user: str = Depends(get_current_user)
):
    """Create a voice clone for the user"""
    try:
        result = await tts_service.create_voice_clone(
            user_id=current_user,
            voice_name=request.voice_name,
            audio_files=request.audio_files
        )
        
        return VoiceCloneResponse(
            success=result["success"],
            message=result["message"],
            estimated_processing_time=result.get("estimated_processing_time")
        )
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Voice cloning failed: {str(e)}")

@app.get("/tts/voice-profiles", response_model=List[UserVoiceProfile], tags=["TTS"])
async def get_voice_profiles(
    current_user: str = Depends(get_current_user)
):
    """Get all voice profiles for the current user"""
    try:
        profiles = await tts_service.get_user_voice_profiles(current_user)
        return profiles
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get voice profiles: {str(e)}")

@app.get("/tts/subscription", response_model=UserSubscription, tags=["TTS"])
async def get_user_subscription(
    current_user: str = Depends(get_current_user)
):
    """Get user's subscription information"""
    try:
        subscription = await tts_service.get_user_subscription(current_user)
        return subscription
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get subscription: {str(e)}")

@app.get("/tts/quota", tags=["TTS"])
async def get_tts_quota(
    current_user: str = Depends(get_current_user)
):
    """Get user's TTS quota information including voice clone usage"""
    try:
        subscription = await tts_service.get_user_subscription(current_user)
        has_quota = await tts_service.check_tts_quota(current_user)
        
        # Get today's TTS usage
        today = datetime.now().date()
        result = db.client.table("tts_usage").select("*").eq("user_id", current_user).eq("date", today.isoformat()).execute()
        usage_count = len(result.data) if result.data else 0
        
        # Get voice clone usage (count of active voice profiles)
        # Use service role client for backend operations to bypass RLS
        try:
            from config import Config
            from supabase import create_client
            
            if Config.SUPABASE_SERVICE_ROLE_KEY:
                service_client = create_client(Config.SUPABASE_URL, Config.SUPABASE_SERVICE_ROLE_KEY)
                voice_profiles_result = service_client.table("user_voice_profiles").select("*").eq(
                    "user_id", current_user
                ).eq("is_active", True).execute()
            else:
                # Fallback to regular client
                voice_profiles_result = db.client.table("user_voice_profiles").select("*").eq(
                    "user_id", current_user
                ).eq("is_active", True).execute()
                
            voice_clones_used = len(voice_profiles_result.data) if voice_profiles_result.data else 0
        except Exception as e:
            print(f"❌ Error querying voice profiles: {e}")
            voice_clones_used = 0
        
        # Debug logging for voice clone counting
        print(f"🔍 DEBUG: User {current_user} voice clone usage:")
        print(f"   📊 Raw query result: {voice_profiles_result.data}")
        print(f"   🔢 Voice clones found: {voice_clones_used}")
        print(f"   📋 Subscription plan: {subscription.plan.value}")
        
        # Calculate quota limits
        if subscription.plan == SubscriptionPlan.FREE:
            max_requests = Config.MAX_FREE_TTS_REQUESTS_PER_DAY
            voice_clones_limit = Config.MAX_FREE_VOICE_CLONES
        elif subscription.plan == SubscriptionPlan.PREMIUM:
            max_requests = Config.MAX_PREMIUM_TTS_REQUESTS_PER_DAY
            voice_clones_limit = Config.MAX_PREMIUM_VOICE_CLONES
        else:
            max_requests = Config.MAX_PREMIUM_TTS_REQUESTS_PER_DAY
            voice_clones_limit = Config.MAX_PRO_VOICE_CLONES
        
        return {
            "success": True,
            "plan": subscription.plan.value,
            "usage_today": usage_count,
            "max_requests": max_requests,
            "remaining_requests": max_requests - usage_count,
            "has_quota": has_quota,
            "voice_clones_used": voice_clones_used,
            "voice_clones_limit": voice_clones_limit,
            "voice_clones_remaining": voice_clones_limit - voice_clones_used,
            "features": subscription.features
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get quota information: {str(e)}")

@app.delete("/tts/voice-profiles/{voice_profile_id}", tags=["TTS"])
async def delete_voice_profile(
    voice_profile_id: str,
    current_user: str = Depends(get_current_user)
):
    """Delete a voice profile"""
    try:
        # Verify ownership
        result = db.client.table("user_voice_profiles").select("*").eq("id", voice_profile_id).eq("user_id", current_user).execute()
        if not result.data:
            raise HTTPException(status_code=404, detail="Voice profile not found")
        
        # Deactivate the voice profile
        db.client.table("user_voice_profiles").update({
            "is_active": False,
            "updated_at": datetime.now().isoformat()
        }).eq("id", voice_profile_id).execute()
        
        return {
            "success": True,
            "message": "Voice profile deleted successfully"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to delete voice profile: {str(e)}")

# =========== TTS PRONUNCIATION ENDPOINTS ===========

@app.post("/tts/pronunciation/generate", response_model=PronunciationResponse, tags=["TTS"])
async def generate_pronunciations(
    request: PronunciationRequest,
    current_user: str = Depends(get_current_user)
):
    """Generate multiple pronunciation versions for a vocabulary entry"""
    try:
        response = await pronunciation_service.generate_pronunciations(request, current_user)
        
        # Award points for pronunciation practice
        if response and response.success:
            # Get vocabulary entry to determine level
            vocab_result = db.client.table("vocab_entries").select("level").eq("id", request.vocab_entry_id).execute()
            level = vocab_result.data[0]["level"] if vocab_result.data else "A2"
            
            # Award points for pronunciation practice
            points_result = vocab_points.award_pronunciation_points(
                user_name=current_user,
                level=level,
                practice_duration=1  # Assume 1 minute of practice per generation
            )
            
            # Add points info to response
            if hasattr(response, 'details'):
                response.details = response.details or {}
                response.details["points_awarded"] = points_result.get("points", 0) if points_result.get("success") else 0
                response.details["points_success"] = points_result.get("success", False)
        
        return response
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Pronunciation generation failed: {str(e)}")

@app.get("/tts/pronunciation/{vocab_entry_id}", response_model=VocabPronunciation, tags=["TTS"])
async def get_pronunciations(
    vocab_entry_id: str,
    current_user: str = Depends(get_current_user)
):
    """Get pronunciations for a vocabulary entry"""
    try:
        pronunciations = await pronunciation_service.get_pronunciations(vocab_entry_id)
        if not pronunciations:
            raise HTTPException(status_code=404, detail="Pronunciations not found")
        return pronunciations
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get pronunciations: {str(e)}")

@app.post("/tts/pronunciation/ensure/{vocab_entry_id}", tags=["TTS"])
async def ensure_pronunciations(
    vocab_entry_id: str,
    current_user: str = Depends(get_current_user),
    versions: List[PronunciationType] = [PronunciationType.NORMAL, PronunciationType.SLOW]
):
    """Ensure that required pronunciation versions exist for a vocabulary entry"""
    try:
        success = await pronunciation_service.ensure_pronunciations_exist(
            vocab_entry_id=vocab_entry_id,
            user_id=current_user,
            required_versions=versions
        )
        
        return {
            "success": success,
            "message": "Pronunciations ensured" if success else "Failed to ensure pronunciations",
            "vocab_entry_id": vocab_entry_id,
            "required_versions": [v.value for v in versions]
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to ensure pronunciations: {str(e)}")

@app.post("/tts/pronunciation/batch", tags=["TTS"])
async def generate_pronunciations_batch(
    vocab_entry_ids: List[str],
    current_user: str = Depends(get_current_user),
    versions: List[PronunciationType] = [PronunciationType.NORMAL, PronunciationType.SLOW]
):
    """Generate pronunciations for multiple vocabulary entries"""
    try:
        results = await pronunciation_service.generate_pronunciations_for_batch(
            vocab_entry_ids=vocab_entry_ids,
            user_id=current_user,
            versions=versions
        )
        
        return {
            "success": True,
            "message": f"Processed {len(vocab_entry_ids)} vocabulary entries",
            "results": results,
            "total_processed": len(vocab_entry_ids),
            "successful": sum(1 for r in results.values() if r.success),
            "failed": sum(1 for r in results.values() if not r.success)
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Batch pronunciation generation failed: {str(e)}")

@app.delete("/tts/pronunciation/{vocab_entry_id}", tags=["TTS"])
async def delete_pronunciations(
    vocab_entry_id: str,
    current_user: str = Depends(get_current_user)
):
    """Delete pronunciations for a vocabulary entry"""
    try:
        success = await pronunciation_service.delete_pronunciations(vocab_entry_id)
        
        return {
            "success": success,
            "message": "Pronunciations deleted successfully" if success else "Failed to delete pronunciations",
            "vocab_entry_id": vocab_entry_id
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to delete pronunciations: {str(e)}")

# =========== Main Application ===========

if __name__ == "__main__":
    # Validate configuration
    try:
        Config.validate()
        print("✅ Configuration validated successfully")
    except Exception as e:
        print(f"❌ Configuration validation failed: {e}")
        exit(1)
    
    # Run the API server with auto-reload
    uvicorn.run(
        "vocab_api:app",
        host="0.0.0.0",
        port=8001,
        reload=True,  # This enables auto-reload
        reload_dirs=["./"],  # Watch current directory for changes
        reload_excludes=["*.pyc", "__pycache__", ".git"],  # Exclude these from watching
        log_level="info"
    ) 