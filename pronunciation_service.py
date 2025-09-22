"""
Pronunciation Service
Handles multiple pronunciation versions for vocabulary entries
"""

import asyncio
from typing import Dict, List, Optional, Any
from datetime import datetime

from models import (
    PronunciationType, PronunciationVersion, VocabPronunciation,
    PronunciationRequest, PronunciationResponse, VoiceProvider,
    TTSRequest, TTSResponse
)
from tts_service import TTSService
from supabase_database import SupabaseVocabDatabase


class PronunciationService:
    """Service for managing multiple pronunciation versions of vocabulary entries"""
    
    def __init__(self):
        self.tts_service = TTSService()
        self.db = SupabaseVocabDatabase()
        
        # Use service role database from TTS service if available
        self.service_db = getattr(self.tts_service, 'service_db', None)
        
        # Pronunciation settings for different types
        self.pronunciation_settings = {
            PronunciationType.SLOW: {
                "speed": 0.7,
                "description": "Slow pronunciation for learning"
            },
            PronunciationType.NORMAL: {
                "speed": 1.0,
                "description": "Normal speed pronunciation"
            },
            PronunciationType.FAST: {
                "speed": 1.3,
                "description": "Fast pronunciation for advanced learners"
            },
            PronunciationType.CUSTOM: {
                "speed": 1.0,
                "description": "Custom pronunciation with user's voice"
            }
        }
    
    async def generate_pronunciations(self, request: PronunciationRequest, user_id: str) -> PronunciationResponse:
        """Generate multiple pronunciation versions for a vocabulary entry"""
        try:
            # Get vocabulary entry
            vocab_entry = await self._get_vocab_entry(request.vocab_entry_id)
            if not vocab_entry:
                return PronunciationResponse(
                    success=False,
                    message="Vocabulary entry not found",
                    vocab_entry_id=request.vocab_entry_id
                )
            
            # Check if pronunciations already exist
            existing_pronunciations = await self._get_existing_pronunciations(request.vocab_entry_id)
            print(f"🔍 DEBUG: Found {len(existing_pronunciations)} existing pronunciations")
            print(f"🔍 DEBUG: Request voice_id: '{request.voice_id}'")
            
            # Generate missing pronunciations
            generated_versions = []
            pronunciation_versions = {}
            
            for version_type in request.versions:
                # Check if this version already exists with the same voice_id AND provider
                if version_type in existing_pronunciations:
                    existing_pronunciation = existing_pronunciations[version_type]
                    existing_voice_id = existing_pronunciation.voice_id
                    existing_provider = existing_pronunciation.provider
                    
                    print(f"🔍 DEBUG: Existing pronunciation voice_id: '{existing_voice_id}', provider: '{existing_provider}'")
                    print(f"🔍 DEBUG: Request voice_id: '{request.voice_id}'")
                    
                    # Check if both voice_id and provider match
                    voice_id_matches = existing_voice_id == request.voice_id
                    
                    # Determine expected provider based on voice_id
                    expected_provider = None
                    if request.voice_id and request.voice_id != "google_default" and not request.voice_id.startswith("google_"):
                        # Custom voice should use ElevenLabs
                        expected_provider = "elevenlabs"
                    else:
                        # Google voice should use Google TTS
                        expected_provider = "google_tts"
                    
                    provider_matches = existing_provider.value == expected_provider
                    
                    print(f"🔍 DEBUG: Expected provider: '{expected_provider}', voice_id_matches: {voice_id_matches}, provider_matches: {provider_matches}")
                    
                    if voice_id_matches and provider_matches:
                        # Both voice_id and provider match, use cached version
                        print(f"🔍 DEBUG: Using cached pronunciation (voice_id and provider match)")
                        pronunciation_versions[version_type] = existing_pronunciations[version_type]
                        continue
                    else:
                        # Either voice_id or provider doesn't match, need to regenerate
                        if not voice_id_matches:
                            print(f"🔄 Voice ID changed from '{existing_voice_id}' to '{request.voice_id}', regenerating pronunciation")
                        if not provider_matches:
                            print(f"🔄 Provider changed from '{existing_provider.value}' to '{expected_provider}', regenerating pronunciation")
                
                # Generate new pronunciation
                pronunciation_version = await self._generate_single_pronunciation(
                    vocab_entry=vocab_entry,
                    version_type=version_type,
                    user_id=user_id,
                    voice_id=request.voice_id,
                    language=request.language
                )
                
                if pronunciation_version:
                    pronunciation_versions[version_type] = pronunciation_version
                    generated_versions.append(version_type)
            
            # Create or update pronunciation record
            vocab_pronunciation = VocabPronunciation(
                vocab_entry_id=request.vocab_entry_id,
                user_id=user_id,
                word=vocab_entry["word"],
                versions=pronunciation_versions,
                status="completed" if pronunciation_versions else "failed",
                created_at=datetime.now(),
                updated_at=datetime.now()
            )
            
            # Save to database
            await self._save_pronunciations(vocab_pronunciation)
            
            return PronunciationResponse(
                success=True,
                message=f"Generated {len(generated_versions)} pronunciation versions",
                vocab_entry_id=request.vocab_entry_id,
                pronunciations=vocab_pronunciation,
                generated_versions=generated_versions
            )
            
        except Exception as e:
            return PronunciationResponse(
                success=False,
                message=f"Pronunciation generation failed: {str(e)}",
                vocab_entry_id=request.vocab_entry_id
            )
    
    async def _generate_single_pronunciation(self, vocab_entry: Dict, version_type: PronunciationType, 
                                           user_id: str, voice_id: Optional[str] = None, 
                                           language: str = "en-US") -> Optional[PronunciationVersion]:
        """Generate a single pronunciation version"""
        try:
            # Get pronunciation settings
            settings = self.pronunciation_settings.get(version_type, self.pronunciation_settings[PronunciationType.NORMAL])
            
            # Create TTS request
            tts_request = TTSRequest(
                text=vocab_entry["word"],
                vocab_entry_id=vocab_entry["id"],
                voice_id=voice_id,
                language=language,
                speed=settings["speed"],
                pitch=0.0,
                volume=1.0
            )
            
            # Generate TTS
            tts_response = await self.tts_service.generate_tts(tts_request, user_id)
            
            if not tts_response.success:
                print(f"Failed to generate TTS for {version_type}: {tts_response.message}")
                return None
            
            # Create pronunciation version
            pronunciation_version = PronunciationVersion(
                type=version_type,
                audio_url=tts_response.audio_url,
                provider=tts_response.provider,
                voice_id=tts_response.voice_id,
                speed=settings["speed"],
                duration_seconds=tts_response.duration_seconds,
                created_at=datetime.now()
            )
            
            return pronunciation_version
            
        except Exception as e:
            print(f"Error generating pronunciation for {version_type}: {e}")
            return None
    
    async def _get_vocab_entry(self, vocab_entry_id: str) -> Optional[Dict]:
        """Get vocabulary entry from database"""
        try:
            # Use service role database if available to bypass RLS policies
            db_client = self.service_db if self.service_db else self.db.client
            result = db_client.table("vocab_entries").select("*").eq("id", vocab_entry_id).execute()
            return result.data[0] if result.data else None
        except Exception as e:
            print(f"Error getting vocab entry: {e}")
            return None
    
    async def _get_existing_pronunciations(self, vocab_entry_id: str) -> Dict[PronunciationType, PronunciationVersion]:
        """Get existing pronunciations for a vocabulary entry"""
        try:
            # Use service role database if available
            db_client = self.service_db if self.service_db else self.db.client
            result = db_client.table("vocab_pronunciation_versions").select("*").eq("vocab_entry_id", vocab_entry_id).execute()
            
            if not result.data:
                return {}
            
            versions = {}
            
            # Parse individual version records - prefer most recent or best matching
            for version_data in result.data:
                try:
                    version_type = PronunciationType(version_data["pronunciation_type"])
                    
                    # If we already have a version for this type, check if this one is better
                    if version_type in versions:
                        existing = versions[version_type]
                        current_voice_id = version_data.get("voice_id")
                        existing_voice_id = existing.voice_id
                        
                        # Prefer records with non-None voice_id over None
                        if existing_voice_id is None and current_voice_id is not None:
                            print(f"🔄 Replacing pronunciation with None voice_id with one that has voice_id: '{current_voice_id}'")
                            versions[version_type] = PronunciationVersion(
                                type=version_type,
                                audio_url=version_data["audio_url"],
                                provider=VoiceProvider(version_data["provider"]),
                                voice_id=current_voice_id,
                                speed=version_data.get("speed", 1.0),
                                duration_seconds=version_data.get("duration_seconds"),
                                created_at=datetime.fromisoformat(version_data["created_at"]) if version_data.get("created_at") else None
                            )
                        # Prefer records with custom voice_id over google_default
                        elif existing_voice_id == "google_default" and current_voice_id and current_voice_id != "google_default":
                            print(f"🔄 Replacing google_default pronunciation with custom voice_id: '{current_voice_id}'")
                            versions[version_type] = PronunciationVersion(
                                type=version_type,
                                audio_url=version_data["audio_url"],
                                provider=VoiceProvider(version_data["provider"]),
                                voice_id=current_voice_id,
                                speed=version_data.get("speed", 1.0),
                                duration_seconds=version_data.get("duration_seconds"),
                                created_at=datetime.fromisoformat(version_data["created_at"]) if version_data.get("created_at") else None
                            )
                        # Otherwise keep the existing one
                        continue
                    
                    # First record for this version type
                    versions[version_type] = PronunciationVersion(
                        type=version_type,
                        audio_url=version_data["audio_url"],
                        provider=VoiceProvider(version_data["provider"]),
                        voice_id=version_data.get("voice_id"),
                        speed=version_data.get("speed", 1.0),
                        duration_seconds=version_data.get("duration_seconds"),
                        created_at=datetime.fromisoformat(version_data["created_at"]) if version_data.get("created_at") else None
                    )
                except (ValueError, KeyError) as e:
                    print(f"Error parsing pronunciation version: {e}")
                    continue
            
            return versions
            
        except Exception as e:
            print(f"Error getting existing pronunciations: {e}")
            return {}
    
    async def _save_pronunciations(self, vocab_pronunciation: VocabPronunciation):
        """Save pronunciations to database"""
        try:
            # Use service role database if available
            db_client = self.service_db if self.service_db else self.db.client
            
            # Save each version as a separate record in vocab_pronunciation_versions
            for version_type, version in vocab_pronunciation.versions.items():
                version_data = {
                    "vocab_entry_id": vocab_pronunciation.vocab_entry_id,
                    "user_id": vocab_pronunciation.user_id,
                    "pronunciation_type": version_type.value,
                    "provider": version.provider.value,
                    "voice_id": version.voice_id,
                    "speed": version.speed,
                    "language": "en",  # Default language
                    "audio_url": version.audio_url,
                    "duration_seconds": version.duration_seconds,
                    "created_at": version.created_at.isoformat() if version.created_at else None,
                    "updated_at": version.created_at.isoformat() if version.created_at else None
                }
                
                # Check if this specific version already exists
                existing = db_client.table("vocab_pronunciation_versions").select("id").eq("vocab_entry_id", vocab_pronunciation.vocab_entry_id).eq("pronunciation_type", version_type.value).execute()
                
                if existing.data:
                    # Update existing version
                    db_client.table("vocab_pronunciation_versions").update(version_data).eq("id", existing.data[0]["id"]).execute()
                else:
                    # Insert new version
                    db_client.table("vocab_pronunciation_versions").insert(version_data).execute()
                
        except Exception as e:
            print(f"Error saving pronunciations: {e}")
    
    async def get_pronunciations(self, vocab_entry_id: str) -> Optional[VocabPronunciation]:
        """Get pronunciations for a vocabulary entry"""
        try:
            # Use service role database if available
            db_client = self.service_db if self.service_db else self.db.client
            result = db_client.table("vocab_pronunciation_versions").select("*").eq("vocab_entry_id", vocab_entry_id).execute()
            
            if not result.data:
                return None
            
            # Parse individual version records
            versions = {}
            user_id = None
            word = None
            
            for version_data in result.data:
                try:
                    version_type = PronunciationType(version_data["pronunciation_type"])
                    versions[version_type] = PronunciationVersion(
                        type=version_type,
                        audio_url=version_data["audio_url"],
                        provider=VoiceProvider(version_data["provider"]),
                        voice_id=version_data.get("voice_id"),
                        speed=version_data.get("speed", 1.0),
                        duration_seconds=version_data.get("duration_seconds"),
                        created_at=datetime.fromisoformat(version_data["created_at"]) if version_data.get("created_at") else None
                    )
                    
                    # Get user_id and word from first record
                    if user_id is None:
                        user_id = version_data.get("user_id")
                    if word is None:
                        # Get word from vocab_entries table
                        vocab_result = db_client.table("vocab_entries").select("word").eq("id", vocab_entry_id).execute()
                        if vocab_result.data:
                            word = vocab_result.data[0]["word"]
                            
                except (ValueError, KeyError) as e:
                    print(f"Error parsing pronunciation version: {e}")
                    continue
            
            if not versions:
                return None
            
            return VocabPronunciation(
                vocab_entry_id=vocab_entry_id,
                user_id=user_id or "unknown",
                word=word or "unknown",
                versions=versions,
                status="completed",  # Default status since we have versions
                created_at=datetime.now(),
                updated_at=datetime.now()
            )
            
        except Exception as e:
            print(f"Error getting pronunciations: {e}")
            return None
    
    async def delete_pronunciations(self, vocab_entry_id: str) -> bool:
        """Delete pronunciations for a vocabulary entry"""
        try:
            # Use service role database if available
            db_client = self.service_db if self.service_db else self.db.client
            db_client.table("vocab_pronunciation_versions").delete().eq("vocab_entry_id", vocab_entry_id).execute()
            return True
        except Exception as e:
            print(f"Error deleting pronunciations: {e}")
            return False
    
    async def generate_pronunciations_for_batch(self, vocab_entry_ids: List[str], user_id: str, 
                                              versions: List[PronunciationType] = None) -> Dict[str, PronunciationResponse]:
        """Generate pronunciations for multiple vocabulary entries"""
        if versions is None:
            versions = [PronunciationType.NORMAL, PronunciationType.SLOW]
        
        results = {}
        
        for vocab_entry_id in vocab_entry_ids:
            request = PronunciationRequest(
                vocab_entry_id=vocab_entry_id,
                versions=versions
            )
            
            result = await self.generate_pronunciations(request, user_id)
            results[vocab_entry_id] = result
            
            # Add small delay to avoid overwhelming the TTS service
            await asyncio.sleep(0.1)
        
        return results
    
    async def ensure_pronunciations_exist(self, vocab_entry_id: str, user_id: str, 
                                        required_versions: List[PronunciationType] = None) -> bool:
        """Ensure that required pronunciation versions exist for a vocabulary entry"""
        if required_versions is None:
            required_versions = [PronunciationType.NORMAL, PronunciationType.SLOW]
        
        # Check existing pronunciations
        existing_pronunciations = await self._get_existing_pronunciations(vocab_entry_id)
        
        # Find missing versions
        missing_versions = [v for v in required_versions if v not in existing_pronunciations]
        
        if not missing_versions:
            return True  # All required versions exist
        
        # Generate missing versions
        request = PronunciationRequest(
            vocab_entry_id=vocab_entry_id,
            versions=missing_versions
        )
        
        result = await self.generate_pronunciations(request, user_id)
        return result.success


# Global instance
pronunciation_service = PronunciationService()
