from fastapi import FastAPI, HTTPException, BackgroundTasks, Depends, Header
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Optional
import uvicorn
from datetime import datetime, timedelta
import uuid

# Import your existing modules
from vocab_agent import run_single_topic_generation, run_continuous_vocab_generation, view_saved_topic_lists
from models import CEFRLevel, VocabListViewRequest, VocabListViewResponse, VocabEntryActionRequest, VocabListRequest, VocabListResponse
from config import Config
from topics import get_categories, get_topics_by_category, get_topic_list
from supabase_database import SupabaseVocabDatabase

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

# Initialize database
db = SupabaseVocabDatabase()

# =========== AUTHENTICATION HELPER ===========

async def get_current_user(authorization: Optional[str] = Header(None)) -> str:
    """Extract user ID from authorization header"""
    if not authorization:
        raise HTTPException(status_code=401, detail="Authorization header required")
    
    # For now, we'll use a simple user ID extraction
    # In production, you should validate JWT tokens with Supabase
    try:
        # Assuming format: "Bearer user_id" or just "user_id"
        if authorization.startswith("Bearer "):
            user_id = authorization[7:]  # Remove "Bearer " prefix
        else:
            user_id = authorization
        
        # Validate that it's a valid UUID format
        import uuid
        uuid.UUID(user_id)
        
        return user_id
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid user ID format")

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
        # Ensure user exists in profiles table for testing
        try:
            db.client.table("profiles").select("id").eq("id", current_user).execute()
        except:
            # Create minimal user record for testing
            db.client.table("profiles").insert({
                "id": current_user,
                "email": f"test-{current_user}@example.com",
                "created_at": datetime.now().isoformat(),
                "updated_at": datetime.now().isoformat()
            }).execute()
        
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
        # Ensure user exists in profiles table for testing
        try:
            db.client.table("profiles").select("id").eq("id", current_user).execute()
        except:
            # Create minimal user record for testing
            db.client.table("profiles").insert({
                "id": current_user,
                "email": f"test-{current_user}@example.com",
                "created_at": datetime.now().isoformat(),
                "updated_at": datetime.now().isoformat()
            }).execute()
        
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
        # Ensure user exists in profiles table for testing
        try:
            db.client.table("profiles").select("id").eq("id", current_user).execute()
        except:
            # Create minimal user record for testing
            db.client.table("profiles").insert({
                "id": current_user,
                "email": f"test-{current_user}@example.com",
                "created_at": datetime.now().isoformat(),
                "updated_at": datetime.now().isoformat()
            }).execute()
        
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
        
        # Ensure user exists in profiles table for testing
        try:
            db.client.table("profiles").select("id").eq("id", current_user).execute()
        except:
            # Create minimal user record for testing
            db.client.table("profiles").insert({
                "id": current_user,
                "email": f"test-{current_user}@example.com",
                "created_at": datetime.now().isoformat(),
                "updated_at": datetime.now().isoformat()
            }).execute()
        
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
        
        # Ensure user exists in profiles table for testing
        try:
            db.client.table("profiles").select("id").eq("id", current_user).execute()
        except:
            # Create minimal user record for testing
            db.client.table("profiles").insert({
                "id": current_user,
                "email": f"test-{current_user}@example.com",
                "created_at": datetime.now().isoformat(),
                "updated_at": datetime.now().isoformat()
            }).execute()
        
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
        # Ensure user exists in profiles table for testing
        try:
            db.client.table("profiles").select("id").eq("id", current_user).execute()
        except:
            # Create minimal user record for testing
            db.client.table("profiles").insert({
                "id": current_user,
                "email": f"test-{current_user}@example.com",
                "created_at": datetime.now().isoformat(),
                "updated_at": datetime.now().isoformat()
            }).execute()
        
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
        # Ensure user exists in profiles table for testing
        try:
            db.client.table("profiles").select("id").eq("id", current_user).execute()
        except:
            # Create minimal user record for testing
            db.client.table("profiles").insert({
                "id": current_user,
                "email": f"test-{current_user}@example.com",
                "created_at": datetime.now().isoformat(),
                "updated_at": datetime.now().isoformat()
            }).execute()
        
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
    topic_list_name: Optional[str]
):
    """Generate vocabulary for a single topic synchronously"""
    try:
        print(f"Starting single topic generation for: {topic}")
        
        # Import here to avoid circular imports
        from vocab_agent import structured_llm, db, filter_duplicates, validate_topic_relevance, get_existing_combinations_for_topic
        
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
                category_name=None,  # Will be determined by topic
                target_language=language_to_learn,
                original_language=learners_native_language
            )
            print(f"Saved {len(filtered_entries)} new vocabulary entries to database")
        
        # Create response entries with duplicate flags and include all necessary info
        response_entries = []
        for entry in relevant_entries:
            is_duplicate = entry not in filtered_entries
            response_entries.append(VocabEntryResponse(
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
        print(f"Generated {len(response_entries)} entries (saved to vocab_entries, not to personal lists)")
            
        return {
            "vocabulary": response_entries,
            "total_generated": len(response_entries),
            "new_entries_saved": len(filtered_entries),  # Count of new entries saved to vocab_entries
            "duplicates_found": len(response_entries) - len(filtered_entries)
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
            
            # Create response entries with duplicate flags
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
async def generate_single_topic(request: GenerateSingleRequest):
    """Generate vocabulary for a single topic"""
    try:
        # Generate vocabulary synchronously
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
            topic_list_name=request.topic_list_name
        )
        
        return GenerateResponse(
            success=True,
            message=f"Generated vocabulary for topic '{request.topic}' at {request.level.value} level",
            method="single_topic",
            details={
                "topic": request.topic,
                "level": request.level.value,
                "language_to_learn": request.language_to_learn,
                "learners_native_language": request.learners_native_language
            },
            generated_vocabulary=result["vocabulary"],
            total_generated=result["total_generated"],
            new_entries_saved=result["new_entries_saved"],
            duplicates_found=result["duplicates_found"]
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
        
        return GenerateResponse(
            success=True,
            message=f"Generated vocabulary for {len(request.topics)} topics at {request.level.value} level",
            method="multiple_topics",
            details={
                "topics": request.topics,
                "level": request.level.value,
                "language_to_learn": request.language_to_learn,
                "learners_native_language": request.learners_native_language
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
        
        return GenerateResponse(
            success=True,
            message=f"Generated vocabulary for category '{request.category}' at {request.level.value} level",
            method="category",
            details={
                "category": request.category,
                "level": request.level.value,
                "language_to_learn": request.language_to_learn,
                "learners_native_language": request.learners_native_language
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
        # Ensure user exists in profiles table for testing
        try:
            db.client.table("profiles").select("id").eq("id", current_user).execute()
        except:
            # Create minimal user record for testing
            db.client.table("profiles").insert({
                "id": current_user,
                "email": f"test-{current_user}@example.com",
                "created_at": datetime.now().isoformat(),
                "updated_at": datetime.now().isoformat()
            }).execute()
        
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