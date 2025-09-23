"""
TTS API endpoints for Flutter app integration
Supports both Google TTS (free) and ElevenLabs (premium) with voice cloning
"""

from fastapi import APIRouter, HTTPException, Depends, UploadFile, File, Form
from typing import List, Optional
import asyncio
from datetime import datetime

from tts_service import TTSService
from voice_cloning_service import VoiceCloningService
from supabase_database import SupabaseVocabDatabase
from audio_storage import AudioStorageService
from models import (
    TTSRequest, TTSResponse, VoiceCloneRequest, VoiceCloneResponse, 
    UserVoiceProfile, UserSubscription, SubscriptionPlan, VoiceProvider
)

# Create router
router = APIRouter(prefix="/tts", tags=["Text-to-Speech"])

# Initialize services
db = SupabaseVocabDatabase()
audio_storage = AudioStorageService()
tts_service = TTSService()
voice_cloning_service = VoiceCloningService(db, audio_storage)


# ============================================================================
# TTS GENERATION ENDPOINTS
# ============================================================================

@router.post("/generate", response_model=TTSResponse)
async def generate_tts(
    text: str = Form(...),
    user_id: str = Form(...),
    voice_id: Optional[str] = Form(None),
    language: str = Form("en"),
    speed: float = Form(1.0)
):
    """
    Generate TTS audio for text
    
    Args:
        text: Text to convert to speech
        user_id: User ID
        voice_id: Specific voice ID (optional, uses default based on subscription)
        language: Language code (en, vi, etc.)
        speed: Speech speed multiplier (0.5-2.0)
        
    Returns:
        TTSResponse with audio URL and metadata
    """
    try:
        # Validate input
        if not text.strip():
            raise HTTPException(status_code=400, detail="Text cannot be empty")
        
        if len(text) > 5000:
            raise HTTPException(status_code=400, detail="Text too long (max 5000 characters)")
        
        if speed < 0.5 or speed > 2.0:
            raise HTTPException(status_code=400, detail="Speed must be between 0.5 and 2.0")
        
        # Create TTS request
        request = TTSRequest(
            text=text,
            voice_id=voice_id,
            language=language,
            speed=speed
        )
        
        # Generate TTS
        result = await tts_service.generate_tts(request, user_id)
        
        if not result.success:
            raise HTTPException(status_code=500, detail=result.message)
        
        return result
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error generating TTS: {str(e)}")


@router.post("/generate-vocab-pronunciation", response_model=TTSResponse)
async def generate_vocab_pronunciation(
    vocab_entry_id: str = Form(...),
    user_id: str = Form(...),
    voice_id: Optional[str] = Form(None),
    provider: Optional[str] = Form(None),  # "google_tts" or "elevenlabs"
    language: str = Form("en"),
    speed: float = Form(1.0),  # Single speed value (0.25 to 4.0)
    pronunciation_type: str = Form("normal")  # "slow", "normal", "fast", "custom"
):
    """
    Generate a single pronunciation for a vocabulary entry
    Saves pronunciation data to database for real app usage
    
    Args:
        vocab_entry_id: ID of the vocabulary entry (can be UUID or simple text for testing)
        user_id: User ID
        voice_id: Specific voice ID (optional)
        provider: TTS provider ("google_tts" or "elevenlabs")
        language: Language code
        speed: Speech speed (0.25 to 4.0)
        pronunciation_type: Type of pronunciation ("slow", "normal", "fast", "custom")
        
    Returns:
        TTSResponse for the generated pronunciation
    """
    try:
        # Check if vocab_entry_id is a UUID (real database entry) or simple text (testing)
        import re
        uuid_pattern = r'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$'
        is_uuid = re.match(uuid_pattern, vocab_entry_id, re.IGNORECASE)
        
        if is_uuid:
            # Real database entry - get word from database
            word = await _get_vocab_word(vocab_entry_id)
            if not word:
                raise HTTPException(status_code=404, detail="Vocabulary entry not found")
        else:
            # Testing mode - use vocab_entry_id as the word
            word = vocab_entry_id
        
        # Create TTS request
        tts_request = TTSRequest(
            text=word,
            language=language,
            voice_id=voice_id,
            provider=VoiceProvider(provider) if provider else None,
            speed=speed
        )
        
        # Generate TTS
        result = await tts_service.generate_tts(tts_request, user_id)
        
        if not result.success:
            raise HTTPException(status_code=500, detail=f"TTS generation failed: {result.message}")
        
        # Update result message
        result.message = f"{pronunciation_type.title()} pronunciation for '{word}'"
        
        # Save pronunciation data to database (only for real UUID vocab entries)
        if is_uuid:
            await _save_single_pronunciation_to_database(
                vocab_entry_id=vocab_entry_id,
                word=word,
                user_id=user_id,
                language=language,
                voice_id=voice_id,
                provider=result.provider.value if result.provider else "elevenlabs",
                speed=speed,
                pronunciation_type=pronunciation_type,
                audio_url=result.audio_url,
                duration_seconds=result.duration_seconds
            )
        else:
            print(f"ℹ️  Skipping pronunciation data saving for non-UUID vocab_entry_id: {vocab_entry_id}")
            print(f"   For production use, provide a real vocabulary entry UUID")
        
        print(f"✅ Generated {pronunciation_type} pronunciation for '{word}' with {result.provider.value if result.provider else 'elevenlabs'}")
        
        return result
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error generating vocabulary pronunciation: {str(e)}")


async def _save_pronunciation_to_database(pronunciation_data: dict):
    """Save pronunciation data to the database"""
    try:
        # Use service role database if available
        db_client = tts_service.service_db if hasattr(tts_service, 'service_db') and tts_service.service_db else None
        
        if not db_client:
            # Fallback to regular database client
            from supabase_database import SupabaseVocabDatabase
            db = SupabaseVocabDatabase()
            db_client = db.client
        
        # Prepare data for vocab_pronunciations table
        vocab_pronunciation_record = {
            "vocab_entry_id": pronunciation_data["vocab_entry_id"],
            "word": pronunciation_data.get("word", pronunciation_data["vocab_entry_id"]),  # Use word or vocab_entry_id as fallback
            "versions": pronunciation_data["versions"],  # Store all versions as JSON
            "status": "completed",
            "created_at": datetime.now().isoformat(),
            "updated_at": datetime.now().isoformat()
        }
        
        # Check if record exists
        existing = db_client.table("vocab_pronunciations").select("id").eq("vocab_entry_id", pronunciation_data["vocab_entry_id"]).execute()
        
        if existing.data:
            # Update existing record
            db_client.table("vocab_pronunciations").update(vocab_pronunciation_record).eq("vocab_entry_id", pronunciation_data["vocab_entry_id"]).execute()
            print(f"✅ Updated pronunciation record for vocab_entry_id: {pronunciation_data['vocab_entry_id']}")
        else:
            # Insert new record
            db_client.table("vocab_pronunciations").insert(vocab_pronunciation_record).execute()
            print(f"✅ Created pronunciation record for vocab_entry_id: {pronunciation_data['vocab_entry_id']}")
        
        # Also save individual pronunciation versions to a separate table if it exists
        # This is optional - depends on your database schema
        for version_type, version_data in pronunciation_data["versions"].items():
            version_record = {
                "vocab_entry_id": pronunciation_data["vocab_entry_id"],
                "user_id": pronunciation_data["user_id"],
                "pronunciation_type": version_type,
                "audio_url": version_data["audio_url"],
                "duration_seconds": version_data["duration_seconds"],
                "provider": version_data["provider"],
                "voice_id": version_data["voice_id"],
                "speed": version_data["speed"],
                "created_at": datetime.now().isoformat()
            }
            
            # Try to insert into vocab_pronunciation_versions table (if it exists)
            try:
                db_client.table("vocab_pronunciation_versions").insert(version_record).execute()
                print(f"✅ Saved {version_type} pronunciation version to database")
            except Exception as e:
                # Table might not exist, that's okay
                print(f"ℹ️  Note: vocab_pronunciation_versions table not found (this is optional)")
                break
                
    except Exception as e:
        print(f"❌ Error saving pronunciation to database: {e}")
        # Don't raise exception - pronunciation generation succeeded, just database save failed


async def _save_single_pronunciation_to_database(
    vocab_entry_id: str,
    word: str,
    user_id: str,
    language: str,
    voice_id: str,
    provider: str,
    speed: float,
    pronunciation_type: str,
    audio_url: str,
    duration_seconds: float
):
    """Save a single pronunciation to the database with user-specific security"""
    try:
        # Use service role database if available
        db_client = tts_service.service_db if hasattr(tts_service, 'service_db') and tts_service.service_db else None
        
        if not db_client:
            # Fallback to regular database client
            from supabase_database import SupabaseVocabDatabase
            db = SupabaseVocabDatabase()
            db_client = db.client
        
        # Save to the new secure vocab_pronunciation_versions table
        version_record = {
            "vocab_entry_id": vocab_entry_id,
            "user_id": user_id,
            "pronunciation_type": pronunciation_type,
            "provider": provider,
            "voice_id": voice_id,
            "speed": speed,
            "language": language,
            "audio_url": audio_url,
            "duration_seconds": duration_seconds,
            "created_at": datetime.now().isoformat(),
            "updated_at": datetime.now().isoformat()
        }
        
        # Check if this exact version already exists
        existing = db_client.table("vocab_pronunciation_versions").select("id").eq("user_id", user_id).eq("vocab_entry_id", vocab_entry_id).eq("provider", provider).eq("pronunciation_type", pronunciation_type).execute()
        
        if existing.data:
            # Update existing version
            db_client.table("vocab_pronunciation_versions").update(version_record).eq("id", existing.data[0]["id"]).execute()
            print(f"✅ Updated {pronunciation_type} pronunciation for user {user_id} with {provider}")
        else:
            # Insert new version
            db_client.table("vocab_pronunciation_versions").insert(version_record).execute()
            print(f"✅ Created {pronunciation_type} pronunciation for user {user_id} with {provider}")
        
        # Also update the main vocab_pronunciations table for backward compatibility
        # Check if main record exists
        main_existing = db_client.table("vocab_pronunciations").select("id, versions").eq("vocab_entry_id", vocab_entry_id).eq("user_id", user_id).execute()
        
        if main_existing.data:
            # Update existing record - add new version to existing versions
            existing_versions = main_existing.data[0].get("versions", {})
            existing_versions[pronunciation_type] = {
                "audio_url": audio_url,
                "duration_seconds": duration_seconds,
                "provider": provider,
                "voice_id": voice_id,
                "speed": speed,
                "created_at": datetime.now().isoformat()
            }
            
            update_record = {
                "versions": existing_versions,
                "updated_at": datetime.now().isoformat()
            }
            
            db_client.table("vocab_pronunciations").update(update_record).eq("vocab_entry_id", vocab_entry_id).eq("user_id", user_id).execute()
            print(f"✅ Updated main pronunciation record for user {user_id}")
        else:
            # Create new main record
            new_versions = {
                pronunciation_type: {
                    "audio_url": audio_url,
                    "duration_seconds": duration_seconds,
                    "provider": provider,
                    "voice_id": voice_id,
                    "speed": speed,
                    "created_at": datetime.now().isoformat()
                }
            }
            
            new_record = {
                "vocab_entry_id": vocab_entry_id,
                "user_id": user_id,
                "word": word,
                "versions": new_versions,
                "status": "completed",
                "created_at": datetime.now().isoformat(),
                "updated_at": datetime.now().isoformat()
            }
            
            db_client.table("vocab_pronunciations").insert(new_record).execute()
            print(f"✅ Created main pronunciation record for user {user_id}")
                
    except Exception as e:
        print(f"❌ Error saving pronunciation to database: {e}")
        # Don't raise exception - pronunciation generation succeeded, just database save failed


@router.post("/generate-batch-vocab-pronunciations")
async def generate_batch_vocab_pronunciations(
    vocab_entry_ids: str = Form(...),  # Comma-separated list of IDs
    user_id: str = Form(...),
    voice_id: Optional[str] = Form(None),
    language: str = Form("en"),
    versions: Optional[str] = Form("slow,normal,fast")
):
    """
    Generate pronunciations for multiple vocabulary entries
    
    Args:
        vocab_entry_ids: Comma-separated list of vocabulary entry IDs
        user_id: User ID
        voice_id: Specific voice ID (optional)
        language: Language code
        versions: Comma-separated list of versions to generate
        
    Returns:
        Dictionary mapping vocab_entry_id to list of TTSResponse
    """
    try:
        # Parse vocab entry IDs
        entry_ids = [id.strip() for id in vocab_entry_ids.split(",")]
        
        results = {}
        
        for vocab_entry_id in entry_ids:
            print(f"🔄 Processing vocabulary entry: {vocab_entry_id}")
            
            # Generate pronunciations for this entry
            try:
                pronunciations = await generate_vocab_pronunciation(
                    vocab_entry_id=vocab_entry_id,
                    user_id=user_id,
                    voice_id=voice_id,
                    language=language,
                    versions=versions
                )
                results[vocab_entry_id] = pronunciations
                print(f"✅ Completed {vocab_entry_id}: {len(pronunciations)} pronunciations")
                
            except Exception as e:
                print(f"❌ Failed {vocab_entry_id}: {e}")
                results[vocab_entry_id] = {"error": str(e)}
        
        return {
            "success": True,
            "message": f"Processed {len(entry_ids)} vocabulary entries",
            "results": results
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error in batch processing: {str(e)}")


async def _get_vocab_word(vocab_entry_id: str) -> Optional[str]:
    """Get word from vocabulary entry in database"""
    try:
        # Use service role database if available
        db_client = tts_service.service_db if hasattr(tts_service, 'service_db') and tts_service.service_db else None
        
        if not db_client:
            # Fallback to regular database client
            from supabase_database import SupabaseVocabDatabase
            db = SupabaseVocabDatabase()
            db_client = db.client
        
        result = db_client.table("vocab_entries").select("word").eq("id", vocab_entry_id).execute()
        
        if result.data:
            return result.data[0].get("word")
        return None
        
    except Exception as e:
        print(f"❌ Error getting vocab word: {e}")
        return None


# ============================================================================
# VOICE CLONING ENDPOINTS
# ============================================================================

@router.post("/voice-clone/create", response_model=VoiceCloneResponse)
async def create_voice_clone(
    user_id: str = Form(...),
    voice_name: str = Form(...),
    audio_files: List[UploadFile] = File(...),
    description: Optional[str] = Form(None)
):
    """
    Create a voice clone using uploaded audio files
    
    Args:
        user_id: User ID
        voice_name: Name for the cloned voice
        audio_files: List of audio files for training (3-10 files recommended)
        description: Optional description for the voice
        
    Returns:
        VoiceCloneResponse with voice_id and status
    """
    try:
        # Validate input
        if not audio_files:
            raise HTTPException(status_code=400, detail="No audio files provided")
        
        if len(audio_files) < 3:
            raise HTTPException(status_code=400, detail="At least 3 audio files are required for voice cloning")
        
        if len(audio_files) > 10:
            raise HTTPException(status_code=400, detail="Maximum 10 audio files allowed")
        
        # Validate and read audio files
        audio_data_list = []
        for audio_file in audio_files:
            # Validate file type
            if not audio_file.content_type.startswith('audio/'):
                raise HTTPException(
                    status_code=400, 
                    detail=f"Invalid file type: {audio_file.content_type}. Only audio files are allowed."
                )
            
            # Check file size (max 10MB per file)
            audio_data = await audio_file.read()
            if len(audio_data) > 10 * 1024 * 1024:  # 10MB
                raise HTTPException(
                    status_code=400, 
                    detail=f"File {audio_file.filename} is too large. Maximum size is 10MB."
                )
            
            audio_data_list.append(audio_data)
        
        # Create voice clone
        result = await voice_cloning_service.create_voice_clone(
            user_id=user_id,
            voice_name=voice_name,
            audio_files=audio_data_list,
            description=description
        )
        
        if not result.success:
            raise HTTPException(status_code=500, detail=result.message)
        
        return result
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error creating voice clone: {str(e)}")


@router.get("/voice-clone/profiles/{user_id}", response_model=List[UserVoiceProfile])
async def get_user_voice_profiles(user_id: str):
    """
    Get all voice profiles for a user
    
    Args:
        user_id: User ID
        
    Returns:
        List of UserVoiceProfile objects
    """
    try:
        profiles = await voice_cloning_service.get_user_voice_profiles(user_id)
        return profiles
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching voice profiles: {str(e)}")


@router.delete("/voice-clone/profiles/{user_id}/{voice_id}")
async def delete_voice_profile(user_id: str, voice_id: str):
    """
    Delete a voice profile
    
    Args:
        user_id: User ID
        voice_id: Voice ID to delete
        
    Returns:
        Success message
    """
    try:
        success = await voice_cloning_service.delete_voice_profile(user_id, voice_id)
        
        if not success:
            raise HTTPException(status_code=404, detail="Voice profile not found")
        
        return {"message": "Voice profile deleted successfully"}
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error deleting voice profile: {str(e)}")


@router.post("/voice-clone/test", response_model=TTSResponse)
async def test_voice_clone(
    voice_id: str = Form(...),
    test_text: str = Form("Hello, this is a test of my cloned voice."),
    user_id: str = Form("test_user")
):
    """
    Test a voice clone with sample text
    
    Args:
        voice_id: Voice ID to test
        test_text: Text to use for testing
        user_id: User ID
        
    Returns:
        TTSResponse with test audio
    """
    try:
        result = await voice_cloning_service.test_voice_clone(voice_id, test_text)
        
        if not result.success:
            raise HTTPException(status_code=500, detail=result.message)
        
        return result
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error testing voice clone: {str(e)}")


# ============================================================================
# USER SUBSCRIPTION & QUOTA ENDPOINTS
# ============================================================================

@router.get("/subscription/{user_id}", response_model=UserSubscription)
async def get_user_subscription(user_id: str):
    """
    Get user's subscription information
    
    Args:
        user_id: User ID
        
    Returns:
        UserSubscription object
    """
    try:
        subscription = await tts_service.get_user_subscription(user_id)
        return subscription
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching subscription: {str(e)}")


@router.get("/quota/{user_id}")
async def get_tts_quota(user_id: str):
    """
    Get user's TTS quota information
    
    Args:
        user_id: User ID
        
    Returns:
        Quota information
    """
    try:
        subscription = await tts_service.get_user_subscription(user_id)
        quota_ok = await tts_service.check_tts_quota(user_id)
        
        # Get today's usage
        today = datetime.now().date()
        result = tts_service.service_db.table("tts_usage").select("*").eq("user_id", user_id).eq("date", today.isoformat()).execute()
        usage_count = len(result.data) if result.data else 0
        
        # Calculate limits based on subscription
        if subscription.plan == SubscriptionPlan.FREE:
            daily_limit = 50  # Free users get 50 TTS requests per day
        else:
            daily_limit = 1000  # Premium users get 1000 TTS requests per day
        
        return {
            "user_id": user_id,
            "subscription_plan": subscription.plan.value,
            "quota_ok": quota_ok,
            "daily_usage": usage_count,
            "daily_limit": daily_limit,
            "remaining_quota": max(0, daily_limit - usage_count),
            "features": subscription.features
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching quota: {str(e)}")


@router.get("/usage/{user_id}")
async def get_user_usage(user_id: str, limit: int = 50):
    """
    Get user's TTS usage history
    
    Args:
        user_id: User ID
        limit: Maximum number of records to return
        
    Returns:
        User's TTS usage history
    """
    try:
        # Use service role to access usage data
        db_client = tts_service.service_db if hasattr(tts_service, 'service_db') and tts_service.service_db else None
        
        if not db_client:
            raise HTTPException(status_code=500, detail="Service role not available")
        
        result = db_client.table('tts_usage').select('*').eq('user_id', user_id).order('date', desc=True).limit(limit).execute()
        
        return {
            "user_id": user_id,
            "total_requests": len(result.data),
            "requests": result.data
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error getting usage: {str(e)}")


@router.get("/audio-files/{user_id}")
async def get_user_audio_files(user_id: str, limit: int = 50):
    """
    Get user's audio files
    
    Args:
        user_id: User ID
        limit: Maximum number of files to return
        
    Returns:
        User's audio files
    """
    try:
        # Use service role to access audio files
        db_client = tts_service.service_db if hasattr(tts_service, 'service_db') and tts_service.service_db else None
        
        if not db_client:
            raise HTTPException(status_code=500, detail="Service role not available")
        
        result = db_client.table('audio_files').select('*').eq('user_id', user_id).order('created_at', desc=True).limit(limit).execute()
        
        return {
            "user_id": user_id,
            "total_files": len(result.data),
            "files": result.data
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error getting audio files: {str(e)}")


@router.get("/pronunciations/{user_id}/{vocab_entry_id}")
async def get_vocab_pronunciations(user_id: str, vocab_entry_id: str, provider: Optional[str] = None):
    """
    Get pronunciations for a specific vocabulary entry (user-specific and secure)
    
    Args:
        user_id: User ID
        vocab_entry_id: Vocabulary entry ID
        provider: Optional provider filter ("google_tts" or "elevenlabs")
        
    Returns:
        User's pronunciations for the vocabulary entry
    """
    try:
        # Use service role to access pronunciation data
        db_client = tts_service.service_db if hasattr(tts_service, 'service_db') and tts_service.service_db else None
        
        if not db_client:
            raise HTTPException(status_code=500, detail="Service role not available")
        
        # Build query with user-specific filtering
        query = db_client.table('vocab_pronunciation_versions').select('*').eq('user_id', user_id).eq('vocab_entry_id', vocab_entry_id)
        
        if provider:
            query = query.eq('provider', provider)
        
        result = query.order('created_at', desc=True).execute()
        
        # Group by pronunciation type for easier frontend consumption
        pronunciations = {}
        for record in result.data:
            pronunciation_type = record.get('pronunciation_type')
            if pronunciation_type not in pronunciations:
                pronunciations[pronunciation_type] = []
            
            pronunciations[pronunciation_type].append({
                "id": record.get('id'),
                "provider": record.get('provider'),
                "voice_id": record.get('voice_id'),
                "speed": record.get('speed'),
                "language": record.get('language'),
                "audio_url": record.get('audio_url'),
                "duration_seconds": record.get('duration_seconds'),
                "created_at": record.get('created_at')
            })
        
        return {
            "user_id": user_id,
            "vocab_entry_id": vocab_entry_id,
            "total_versions": len(result.data),
            "pronunciations": pronunciations
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error getting pronunciations: {str(e)}")


@router.get("/pronunciations/{user_id}")
async def get_all_user_pronunciations(user_id: str, limit: int = 100):
    """
    Get all pronunciations for a user (user-specific and secure)
    
    Args:
        user_id: User ID
        limit: Maximum number of records to return
        
    Returns:
        All user's pronunciations
    """
    try:
        # Use service role to access pronunciation data
        db_client = tts_service.service_db if hasattr(tts_service, 'service_db') and tts_service.service_db else None
        
        if not db_client:
            raise HTTPException(status_code=500, detail="Service role not available")
        
        result = db_client.table('vocab_pronunciation_versions').select('*').eq('user_id', user_id).order('created_at', desc=True).limit(limit).execute()
        
        return {
            "user_id": user_id,
            "total_pronunciations": len(result.data),
            "pronunciations": result.data
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error getting pronunciations: {str(e)}")


# ============================================================================
# AVAILABLE VOICES ENDPOINTS
# ============================================================================

@router.get("/voices/available")
async def get_available_voices():
    """
    Get list of available voices
    
    Returns:
        List of available voices
    """
    try:
        # Standard ElevenLabs voices
        standard_voices = [
            {
                "voice_id": "JBFqnCBsd6RMkjVDRZzb",
                "name": "Default Voice",
                "provider": "elevenlabs",
                "language": "en",
                "description": "High-quality default voice"
            },
            {
                "voice_id": "EXAVITQu4vr4xnSDxMaL",
                "name": "Bella",
                "provider": "elevenlabs", 
                "language": "en",
                "description": "Friendly and warm voice"
            },
            {
                "voice_id": "VR6AewLTigWG4xSOukaG",
                "name": "Josh",
                "provider": "elevenlabs",
                "language": "en", 
                "description": "Deep and authoritative voice"
            }
        ]
        
        return {
            "standard_voices": standard_voices,
            "voice_cloning_available": voice_cloning_service.is_configured,
            "message": "Use voice-clone/profiles/{user_id} to get user's cloned voices"
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching available voices: {str(e)}")


# ============================================================================
# HEALTH & STATUS ENDPOINTS
# ============================================================================

@router.get("/status")
async def get_tts_status():
    """
    Get TTS service status
    
    Returns:
        Service status information
    """
    try:
        return {
            "tts_service": "operational",
            "google_tts": hasattr(tts_service, '_google_api_key') and tts_service._google_api_key is not None,
            "elevenlabs": tts_service._elevenlabs_configured,
            "voice_cloning": voice_cloning_service.is_configured,
            "audio_storage": "operational",
            "message": "TTS service is ready"
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error getting service status: {str(e)}")


@router.get("/health")
async def health_check():
    """Health check for TTS service"""
    return {
        "status": "healthy",
        "service": "text-to-speech",
        "timestamp": datetime.now().isoformat(),
        "features": {
            "google_tts": hasattr(tts_service, '_google_api_key') and tts_service._google_api_key is not None,
            "elevenlabs": tts_service._elevenlabs_configured,
            "voice_cloning": voice_cloning_service.is_configured
        }
    }


