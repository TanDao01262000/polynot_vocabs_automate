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
            
            # Generate missing pronunciations
            generated_versions = []
            pronunciation_versions = {}
            
            for version_type in request.versions:
                # Check if this version already exists
                if version_type in existing_pronunciations:
                    pronunciation_versions[version_type] = existing_pronunciations[version_type]
                    continue
                
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
                created_at=datetime.now()
            )
            
            return pronunciation_version
            
        except Exception as e:
            print(f"Error generating pronunciation for {version_type}: {e}")
            return None
    
    async def _get_vocab_entry(self, vocab_entry_id: str) -> Optional[Dict]:
        """Get vocabulary entry from database"""
        try:
            result = self.db.client.table("vocab_entries").select("*").eq("id", vocab_entry_id).execute()
            return result.data[0] if result.data else None
        except Exception as e:
            print(f"Error getting vocab entry: {e}")
            return None
    
    async def _get_existing_pronunciations(self, vocab_entry_id: str) -> Dict[PronunciationType, PronunciationVersion]:
        """Get existing pronunciations for a vocabulary entry"""
        try:
            # Use service role database if available
            db_client = self.service_db.client if self.service_db else self.db.client
            result = db_client.table("vocab_pronunciations").select("*").eq("vocab_entry_id", vocab_entry_id).execute()
            
            if not result.data:
                return {}
            
            pronunciation_data = result.data[0]
            versions = {}
            
            # Parse versions from JSON
            if pronunciation_data.get("versions"):
                for version_type_str, version_data in pronunciation_data["versions"].items():
                    version_type = PronunciationType(version_type_str)
                    versions[version_type] = PronunciationVersion(
                        type=version_type,
                        audio_url=version_data["audio_url"],
                        provider=VoiceProvider(version_data["provider"]),
                        voice_id=version_data.get("voice_id"),
                        speed=version_data.get("speed", 1.0),
                        created_at=datetime.fromisoformat(version_data["created_at"]) if version_data.get("created_at") else None
                    )
            
            return versions
            
        except Exception as e:
            print(f"Error getting existing pronunciations: {e}")
            return {}
    
    async def _save_pronunciations(self, vocab_pronunciation: VocabPronunciation):
        """Save pronunciations to database"""
        try:
            # Convert versions to JSON format
            versions_json = {}
            for version_type, version in vocab_pronunciation.versions.items():
                versions_json[version_type.value] = {
                    "audio_url": version.audio_url,
                    "provider": version.provider.value,
                    "voice_id": version.voice_id,
                    "speed": version.speed,
                    "created_at": version.created_at.isoformat() if version.created_at else None
                }
            
            # Prepare data for database
            pronunciation_data = {
                "vocab_entry_id": vocab_pronunciation.vocab_entry_id,
                "word": vocab_pronunciation.word,
                "versions": versions_json,
                "status": vocab_pronunciation.status,
                "created_at": vocab_pronunciation.created_at.isoformat() if vocab_pronunciation.created_at else None,
                "updated_at": vocab_pronunciation.updated_at.isoformat() if vocab_pronunciation.updated_at else None
            }
            
            # Check if record exists
            # Use service role database if available
            db_client = self.service_db.client if self.service_db else self.db.client
            existing = db_client.table("vocab_pronunciations").select("id").eq("vocab_entry_id", vocab_pronunciation.vocab_entry_id).execute()
            
            if existing.data:
                # Update existing record
                db_client.table("vocab_pronunciations").update(pronunciation_data).eq("vocab_entry_id", vocab_pronunciation.vocab_entry_id).execute()
            else:
                # Insert new record
                db_client.table("vocab_pronunciations").insert(pronunciation_data).execute()
                
        except Exception as e:
            print(f"Error saving pronunciations: {e}")
    
    async def get_pronunciations(self, vocab_entry_id: str) -> Optional[VocabPronunciation]:
        """Get pronunciations for a vocabulary entry"""
        try:
            # Use service role database if available
            db_client = self.service_db.client if self.service_db else self.db.client
            result = db_client.table("vocab_pronunciations").select("*").eq("vocab_entry_id", vocab_entry_id).execute()
            
            if not result.data:
                return None
            
            pronunciation_data = result.data[0]
            
            # Parse versions
            versions = {}
            if pronunciation_data.get("versions"):
                for version_type_str, version_data in pronunciation_data["versions"].items():
                    version_type = PronunciationType(version_type_str)
                    versions[version_type] = PronunciationVersion(
                        type=version_type,
                        audio_url=version_data["audio_url"],
                        provider=VoiceProvider(version_data["provider"]),
                        voice_id=version_data.get("voice_id"),
                        speed=version_data.get("speed", 1.0),
                        created_at=datetime.fromisoformat(version_data["created_at"]) if version_data.get("created_at") else None
                    )
            
            return VocabPronunciation(
                vocab_entry_id=pronunciation_data["vocab_entry_id"],
                word=pronunciation_data["word"],
                versions=versions,
                status=pronunciation_data["status"],
                created_at=datetime.fromisoformat(pronunciation_data["created_at"]) if pronunciation_data.get("created_at") else None,
                updated_at=datetime.fromisoformat(pronunciation_data["updated_at"]) if pronunciation_data.get("updated_at") else None
            )
            
        except Exception as e:
            print(f"Error getting pronunciations: {e}")
            return None
    
    async def delete_pronunciations(self, vocab_entry_id: str) -> bool:
        """Delete pronunciations for a vocabulary entry"""
        try:
            # Use service role database if available
            db_client = self.service_db.client if self.service_db else self.db.client
            db_client.table("vocab_pronunciations").delete().eq("vocab_entry_id", vocab_entry_id).execute()
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
