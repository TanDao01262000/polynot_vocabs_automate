"""
Text-to-Speech Service
Handles TTS generation using Google TTS for free users and ElevenLabs for paid users
"""

import os
import base64
import io
import tempfile
from typing import Optional, Dict, Any, List
from datetime import datetime, timedelta
import requests
import json

# Google TTS
from google.cloud import texttospeech
from google.oauth2 import service_account

# ElevenLabs
from elevenlabs import Voice, VoiceSettings, generate, clone, set_api_key

# Audio processing
from pydub import AudioSegment
import librosa
import soundfile as sf

from models import (
    TTSRequest, TTSResponse, VoiceProvider, VoiceCloneStatus, 
    UserVoiceProfile, SubscriptionPlan, UserSubscription
)
from config import Config
from supabase_database import SupabaseVocabDatabase
from audio_storage import audio_storage


class TTSService:
    """Text-to-Speech service with support for Google TTS and ElevenLabs voice cloning"""
    
    def __init__(self):
        self.db = SupabaseVocabDatabase()
        self._google_client = None
        self._elevenlabs_configured = False
        
        # Create service role database for TTS operations
        self._init_service_role_db()
        
        # Initialize providers
        self._init_google_tts()
        self._init_elevenlabs()
    
    def _init_service_role_db(self):
        """Initialize service role database for TTS operations"""
        try:
            if Config.SUPABASE_SERVICE_ROLE_KEY:
                from supabase import create_client
                service_client = create_client(Config.SUPABASE_URL, Config.SUPABASE_SERVICE_ROLE_KEY)
                
                # Create a simple wrapper
                class ServiceRoleDatabase:
                    def __init__(self, client):
                        self.client = client
                
                self.service_db = ServiceRoleDatabase(service_client)
                print("Service role database initialized for TTS operations")
            else:
                self.service_db = None
                print("Service role key not found, using regular database")
        except Exception as e:
            self.service_db = None
            print(f"Failed to initialize service role database: {e}")
    
    def _init_google_tts(self):
        """Initialize Google TTS client"""
        try:
            if Config.GOOGLE_TTS_API_KEY:
                # For API key authentication, we'll use the REST API directly
                # The google-cloud-texttospeech library doesn't support API key auth directly
                # So we'll set up the client but use REST API for actual calls
                self._google_client = None  # We'll use REST API instead
                self._google_api_key = Config.GOOGLE_TTS_API_KEY
                self._google_project_id = Config.GOOGLE_TTS_PROJECT_ID
                print("Google TTS configured for API key authentication (REST API)")
            else:
                print("Google TTS API key not found")
                print("Please set GOOGLE_TTS_API_KEY in your .env file")
        except Exception as e:
            print(f"Failed to initialize Google TTS: {e}")
            import traceback
            traceback.print_exc()
    
    def _init_elevenlabs(self):
        """Initialize ElevenLabs client"""
        try:
            if Config.ELEVENLABS_API_KEY:
                set_api_key(Config.ELEVENLABS_API_KEY)
                self._elevenlabs_configured = True
                print("ElevenLabs initialized successfully")
            else:
                print("ElevenLabs API key not found")
        except Exception as e:
            print(f"Failed to initialize ElevenLabs: {e}")
    
    async def get_user_subscription(self, user_id: str) -> UserSubscription:
        """Get user's subscription information"""
        try:
            result = self.db.client.table("user_subscriptions").select("*").eq("user_id", user_id).execute()
            
            if result.data:
                data = result.data[0]
                return UserSubscription(
                    user_id=data["user_id"],
                    plan=SubscriptionPlan(data["plan"]),
                    is_active=data["is_active"],
                    expires_at=datetime.fromisoformat(data["expires_at"]) if data["expires_at"] else None,
                    created_at=datetime.fromisoformat(data["created_at"]) if data["created_at"] else None,
                    updated_at=datetime.fromisoformat(data["updated_at"]) if data["updated_at"] else None,
                    features=data.get("features", {})
                )
            else:
                # Default to free plan
                return UserSubscription(
                    user_id=user_id,
                    plan=SubscriptionPlan.FREE,
                    features={
                        "voice_cloning": False,
                        "unlimited_tts": False,
                        "custom_voices": False,
                        "high_quality_audio": False
                    }
                )
        except Exception as e:
            print(f"Error getting user subscription: {e}")
            # Return free plan as fallback
            return UserSubscription(
                user_id=user_id,
                plan=SubscriptionPlan.FREE,
                features={
                    "voice_cloning": False,
                    "unlimited_tts": False,
                    "custom_voices": False,
                    "high_quality_audio": False
                }
            )
    
    async def check_tts_quota(self, user_id: str) -> bool:
        """Check if user has remaining TTS quota"""
        try:
            subscription = await self.get_user_subscription(user_id)
            
            # Get today's usage
            today = datetime.now().date()
            result = self.db.client.table("tts_usage").select("*").eq("user_id", user_id).eq("date", today.isoformat()).execute()
            
            usage_count = len(result.data) if result.data else 0
            
            # Check quota based on subscription
            if subscription.plan == SubscriptionPlan.FREE:
                return usage_count < Config.MAX_FREE_TTS_REQUESTS_PER_DAY
            else:
                return usage_count < Config.MAX_PREMIUM_TTS_REQUESTS_PER_DAY
                
        except Exception as e:
            print(f"Error checking TTS quota: {e}")
            return False
    
    async def record_tts_usage(self, user_id: str, provider: VoiceProvider, text_length: int):
        """Record TTS usage for quota tracking"""
        try:
            usage_data = {
                "user_id": user_id,
                "provider": provider.value,
                "text_length": text_length,
                "date": datetime.now().date().isoformat(),
                "created_at": datetime.now().isoformat()
            }
            
            # Use service role database if available
            db_client = self.service_db.client if self.service_db else self.db.client
            db_client.table("tts_usage").insert(usage_data).execute()
        except Exception as e:
            print(f"Error recording TTS usage: {e}")
    
    async def generate_tts(self, request: TTSRequest, user_id: str) -> TTSResponse:
        """Generate TTS audio based on user's subscription"""
        try:
            # Check quota
            if not await self.check_tts_quota(user_id):
                return TTSResponse(
                    success=False,
                    message="Daily TTS quota exceeded. Please upgrade your plan or try again tomorrow."
                )
            
            # Get user subscription
            subscription = await self.get_user_subscription(user_id)
            
            # Choose provider based on subscription and request
            if subscription.plan == SubscriptionPlan.FREE or not request.voice_id:
                # Use Google TTS for free users or when no custom voice specified
                return await self._generate_google_tts(request, user_id)
            else:
                # Use ElevenLabs for paid users with custom voice
                return await self._generate_elevenlabs_tts(request, user_id)
                
        except Exception as e:
            return TTSResponse(
                success=False,
                message=f"TTS generation failed: {str(e)}"
            )
    
    async def _generate_google_tts(self, request: TTSRequest, user_id: str) -> TTSResponse:
        """Generate TTS using Google TTS REST API"""
        try:
            if not hasattr(self, '_google_api_key') or not self._google_api_key:
                return TTSResponse(
                    success=False,
                    message="Google TTS API key not available"
                )
            
            import httpx
            import base64
            
            # Prepare the request payload
            payload = {
                "input": {"text": request.text},
                "voice": {
                    "languageCode": request.language,
                    "ssmlGender": "NEUTRAL"
                },
                "audioConfig": {
                    "audioEncoding": "MP3",
                    "speakingRate": request.speed,
                    "pitch": request.pitch,
                    "volumeGainDb": 20 * request.volume - 20
                }
            }
            
            # Make the API request
            url = f"https://texttospeech.googleapis.com/v1/text:synthesize?key={self._google_api_key}"
            
            async with httpx.AsyncClient() as client:
                response = await client.post(url, json=payload)
                response.raise_for_status()
                result = response.json()
            
            # Decode the audio content
            audio_content = base64.b64decode(result["audioContent"])
            
            # Record usage
            await self.record_tts_usage(user_id, VoiceProvider.GOOGLE_TTS, len(request.text))
            
            # Save audio file and get URL
            audio_url = await self._save_audio_file(user_id, audio_content, "google_tts", request.text)
            
            return TTSResponse(
                success=True,
                message="TTS generated successfully",
                audio_url=audio_url,
                audio_data=audio_content,
                provider=VoiceProvider.GOOGLE_TTS,
                voice_id="google_default"
            )
            
        except Exception as e:
            return TTSResponse(
                success=False,
                message=f"Google TTS generation failed: {str(e)}"
            )
    
    async def _generate_elevenlabs_tts(self, request: TTSRequest, user_id: str) -> TTSResponse:
        """Generate TTS using ElevenLabs"""
        try:
            if not self._elevenlabs_configured:
                return TTSResponse(
                    success=False,
                    message="ElevenLabs service not available"
                )
            
            # Get user's voice profile
            voice_profile = await self._get_user_voice_profile(user_id, request.voice_id)
            if not voice_profile or voice_profile.status != VoiceCloneStatus.COMPLETED:
                return TTSResponse(
                    success=False,
                    message="Custom voice not available or not ready"
                )
            
            # Configure voice settings
            voice_settings = VoiceSettings(
                stability=0.5,
                similarity_boost=0.5,
                style=0.0,
                use_speaker_boost=True
            )
            
            # Generate audio
            audio = generate(
                text=request.text,
                voice=Voice(voice_id=voice_profile.voice_id),
                voice_settings=voice_settings
            )
            
            # Record usage
            await self.record_tts_usage(user_id, VoiceProvider.ELEVENLABS, len(request.text))
            
            # Save audio file and get URL
            audio_url = await self._save_audio_file(user_id, audio, "elevenlabs", request.text)
            
            return TTSResponse(
                success=True,
                message="TTS generated successfully",
                audio_url=audio_url,
                audio_data=audio,
                provider=VoiceProvider.ELEVENLABS,
                voice_id=voice_profile.voice_id
            )
            
        except Exception as e:
            return TTSResponse(
                success=False,
                message=f"ElevenLabs TTS generation failed: {str(e)}"
            )
    
    async def _get_user_voice_profile(self, user_id: str, voice_id: Optional[str] = None) -> Optional[UserVoiceProfile]:
        """Get user's voice profile"""
        try:
            query = self.db.client.table("user_voice_profiles").select("*").eq("user_id", user_id).eq("is_active", True)
            
            if voice_id:
                query = query.eq("voice_id", voice_id)
            
            result = query.execute()
            
            if result.data:
                data = result.data[0]
                return UserVoiceProfile(
                    id=data["id"],
                    user_id=data["user_id"],
                    voice_name=data["voice_name"],
                    provider=VoiceProvider(data["provider"]),
                    voice_id=data["voice_id"],
                    status=VoiceCloneStatus(data["status"]),
                    audio_samples=data.get("audio_samples"),
                    created_at=datetime.fromisoformat(data["created_at"]) if data["created_at"] else None,
                    updated_at=datetime.fromisoformat(data["updated_at"]) if data["updated_at"] else None,
                    is_active=data["is_active"]
                )
            
            return None
            
        except Exception as e:
            print(f"Error getting user voice profile: {e}")
            return None
    
    async def _save_audio_file(self, user_id: str, audio_data: bytes, provider: str, text: str = None) -> str:
        """Save audio file and return URL"""
        try:
            # Generate text hash for caching
            text_hash = audio_storage.generate_text_hash(text) if text else None
            
            # Save audio file using storage service
            storage_result = await audio_storage.save_audio_file(
                user_id=user_id,
                audio_data=audio_data,
                provider=provider,
                text_hash=text_hash
            )
            
            if not storage_result["success"]:
                print(f"Failed to save audio file: {storage_result.get('error')}")
                return ""
            
            # Store metadata in database
            audio_metadata = {
                "user_id": user_id,
                "filename": storage_result["filename"],
                "file_url": storage_result["file_url"],
                "file_size": storage_result["file_size"],
                "mime_type": "audio/mpeg",
                "created_at": datetime.now().isoformat()
            }
            
            # Use service role database if available
            db_client = self.service_db.client if self.service_db else self.db.client
            db_client.table("audio_files").insert(audio_metadata).execute()
            
            return storage_result["file_url"]
            
        except Exception as e:
            print(f"Error saving audio file: {e}")
            return ""
    
    async def create_voice_clone(self, user_id: str, voice_name: str, audio_files: List[str]) -> Dict[str, Any]:
        """Create a voice clone using ElevenLabs"""
        try:
            if not self._elevenlabs_configured:
                return {
                    "success": False,
                    "message": "ElevenLabs service not available"
                }
            
            # Check if user has voice cloning feature
            subscription = await self.get_user_subscription(user_id)
            if not subscription.features.get("voice_cloning", False):
                return {
                    "success": False,
                    "message": "Voice cloning not available in your current plan"
                }
            
            # Create voice profile in database
            voice_profile_data = {
                "user_id": user_id,
                "voice_name": voice_name,
                "provider": VoiceProvider.ELEVENLABS.value,
                "status": VoiceCloneStatus.PROCESSING.value,
                "audio_samples": audio_files,
                "created_at": datetime.now().isoformat(),
                "updated_at": datetime.now().isoformat(),
                "is_active": True
            }
            
            result = self.db.client.table("user_voice_profiles").insert(voice_profile_data).execute()
            voice_profile_id = result.data[0]["id"] if result.data else None
            
            # Process audio files and create voice clone
            # This is a simplified version - in production, you'd handle file uploads properly
            try:
                # For demo purposes, we'll simulate the voice cloning process
                # In reality, you'd upload the audio files to ElevenLabs
                voice_id = f"cloned_voice_{voice_profile_id}"
                
                # Update voice profile with voice ID
                self.db.client.table("user_voice_profiles").update({
                    "voice_id": voice_id,
                    "status": VoiceCloneStatus.COMPLETED.value,
                    "updated_at": datetime.now().isoformat()
                }).eq("id", voice_profile_id).execute()
                
                return {
                    "success": True,
                    "message": "Voice clone created successfully",
                    "voice_id": voice_id,
                    "estimated_processing_time": 5  # minutes
                }
                
            except Exception as e:
                # Update status to failed
                self.db.client.table("user_voice_profiles").update({
                    "status": VoiceCloneStatus.FAILED.value,
                    "updated_at": datetime.now().isoformat()
                }).eq("id", voice_profile_id).execute()
                
                return {
                    "success": False,
                    "message": f"Voice cloning failed: {str(e)}"
                }
                
        except Exception as e:
            return {
                "success": False,
                "message": f"Voice cloning failed: {str(e)}"
            }
    
    async def get_user_voice_profiles(self, user_id: str) -> List[UserVoiceProfile]:
        """Get all voice profiles for a user"""
        try:
            result = self.db.client.table("user_voice_profiles").select("*").eq("user_id", user_id).eq("is_active", True).execute()
            
            profiles = []
            for data in result.data:
                profile = UserVoiceProfile(
                    id=data["id"],
                    user_id=data["user_id"],
                    voice_name=data["voice_name"],
                    provider=VoiceProvider(data["provider"]),
                    voice_id=data["voice_id"],
                    status=VoiceCloneStatus(data["status"]),
                    audio_samples=data.get("audio_samples"),
                    created_at=datetime.fromisoformat(data["created_at"]) if data["created_at"] else None,
                    updated_at=datetime.fromisoformat(data["updated_at"]) if data["updated_at"] else None,
                    is_active=data["is_active"]
                )
                profiles.append(profile)
            
            return profiles
            
        except Exception as e:
            print(f"Error getting user voice profiles: {e}")
            return []
