"""
API endpoints for voice cloning functionality
"""

from fastapi import APIRouter, HTTPException, Depends, UploadFile, File
from typing import List, Optional
import asyncio

from voice_cloning_service import VoiceCloningService
from supabase_database import SupabaseVocabDatabase
from audio_storage import AudioStorageService
from models import (
    VoiceCloneRequest, VoiceCloneResponse, UserVoiceProfile,
    TTSRequest, TTSResponse
)

# Authentication function to avoid circular imports
from fastapi import Header
from typing import Optional
import jwt
import os
from dotenv import load_dotenv

load_dotenv(override=True)

async def get_current_user(authorization: Optional[str] = Header(None)) -> str:
    """Extract and validate user from Supabase Auth token"""
    if not authorization:
        raise HTTPException(status_code=401, detail="Authorization header required")
    
    try:
        # Extract token
        if authorization.startswith("Bearer "):
            token = authorization.split(" ")[1]
        else:
            token = authorization
        
        # Decode JWT token to get user ID
        # Note: In production, you should verify the JWT signature
        decoded_token = jwt.decode(token, options={"verify_signature": False})
        user_id = decoded_token.get("sub")
        
        if not user_id:
            raise HTTPException(status_code=401, detail="Invalid token: no user ID found")
        
        return user_id
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=401, detail=f"Authentication verification failed: {str(e)}")

# Create router
router = APIRouter(prefix="/voice-cloning", tags=["voice-cloning"])

# Initialize services
db = SupabaseVocabDatabase()
audio_storage = AudioStorageService()
voice_cloning_service = VoiceCloningService(db, audio_storage)


@router.post("/create-voice-clone", response_model=VoiceCloneResponse)
async def create_voice_clone(
    voice_name: str,
    audio_files: List[UploadFile] = File(...),
    description: Optional[str] = None,
    current_user: str = Depends(get_current_user)  # Use proper authentication
):
    """
    Create a voice clone using uploaded audio files
    
    Args:
        user_id: User ID
        voice_name: Name for the cloned voice
        audio_files: List of audio files for training
        description: Optional description for the voice
        
    Returns:
        VoiceCloneResponse with voice_id and status
    """
    try:
        # Validate audio files
        if not audio_files:
            raise HTTPException(status_code=400, detail="No audio files provided")
        
        if len(audio_files) < 1:
            raise HTTPException(status_code=400, detail="At least one audio file is required")
        
        # Read audio files
        audio_data_list = []
        for audio_file in audio_files:
            # Validate file type
            if not audio_file.content_type.startswith('audio/'):
                raise HTTPException(
                    status_code=400, 
                    detail=f"Invalid file type: {audio_file.content_type}. Only audio files are allowed."
                )
            
            # Read file content
            audio_data = await audio_file.read()
            audio_data_list.append(audio_data)
        
        # Create voice clone using authenticated user ID
        result = await voice_cloning_service.create_voice_clone(
            user_id=current_user,  # Use the authenticated user ID
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


@router.get("/voice-profiles", response_model=List[UserVoiceProfile])
async def get_user_voice_profiles(current_user: str = Depends(get_current_user)):
    """
    Get all voice profiles for a user
    
    Args:
        user_id: User ID
        
    Returns:
        List of UserVoiceProfile objects
    """
    try:
        profiles = await voice_cloning_service.get_user_voice_profiles(current_user)
        return profiles
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching voice profiles: {str(e)}")


@router.delete("/voice-profiles/{voice_id}")
async def delete_voice_profile(voice_id: str, current_user: str = Depends(get_current_user)):
    """
    Delete a voice profile
    
    Args:
        user_id: User ID
        voice_id: Voice ID to delete
        
    Returns:
        Success message
    """
    try:
        success = await voice_cloning_service.delete_voice_profile(current_user, voice_id)
        
        if not success:
            raise HTTPException(status_code=404, detail="Voice profile not found")
        
        return {"message": "Voice profile deleted successfully"}
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error deleting voice profile: {str(e)}")


@router.post("/generate-tts", response_model=TTSResponse)
async def generate_tts_with_cloned_voice(
    text: str,
    voice_id: Optional[str] = None,
    language: str = "en",
    speed: float = 1.0,
    current_user: str = Depends(get_current_user)
):
    """
    Generate TTS using a cloned voice
    
    Args:
        text: Text to convert to speech
        user_id: User ID
        voice_id: Specific voice ID to use (optional)
        language: Language code
        speed: Speech speed multiplier
        
    Returns:
        TTSResponse with audio data and URL
    """
    try:
        result = await voice_cloning_service.generate_tts_with_cloned_voice(
            text=text,
            user_id=current_user,
            voice_id=voice_id,
            language=language,
            speed=speed
        )
        
        if not result.success:
            raise HTTPException(status_code=500, detail=result.message)
        
        return result
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error generating TTS: {str(e)}")


@router.post("/test-voice-clone", response_model=TTSResponse)
async def test_voice_clone(
    voice_id: str,
    test_text: str = "Hello, this is a test of my cloned voice."
):
    """
    Test a voice clone with sample text
    
    Args:
        voice_id: Voice ID to test
        test_text: Text to use for testing
        
    Returns:
        TTSResponse with test audio
    """
    try:
        result = await voice_cloning_service.test_voice_clone(voice_id, test_text)
        
        if not result.success:
            raise HTTPException(status_code=500, detail=result.message)
        
        return result
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error testing voice clone: {str(e)}")


@router.get("/status")
async def get_voice_cloning_status():
    """
    Get the status of the voice cloning service
    
    Returns:
        Service status information
    """
    try:
        return {
            "service_configured": voice_cloning_service.is_configured,
            "elevenlabs_available": voice_cloning_service.is_configured,
            "message": "Voice cloning service is ready" if voice_cloning_service.is_configured else "ElevenLabs not configured"
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error getting service status: {str(e)}")


# Health check endpoint
@router.get("/health")
async def health_check():
    """Health check for voice cloning service"""
    return {
        "status": "healthy",
        "service": "voice-cloning",
        "configured": voice_cloning_service.is_configured
    }
