import os
import asyncio
from typing import List, Optional, Dict, Any
from io import BytesIO
from datetime import datetime
import httpx
from elevenlabs.client import ElevenLabs
from elevenlabs import Voice, VoiceSettings

from config import Config
from models import (
    VoiceCloneRequest, VoiceCloneResponse, UserVoiceProfile, 
    VoiceCloneStatus, VoiceProvider, TTSRequest, TTSResponse
)
from supabase_database import SupabaseVocabDatabase
from audio_storage import AudioStorageService


class VoiceCloningService:
    """Service for managing voice cloning with ElevenLabs"""
    
    def __init__(self, db: SupabaseVocabDatabase, audio_storage: AudioStorageService):
        self.db = db
        self.audio_storage = audio_storage
        self._elevenlabs_client = None
        self._init_elevenlabs()
        self._init_service_role_db()
    
    def _init_elevenlabs(self):
        """Initialize ElevenLabs client"""
        try:
            if Config.ELEVENLABS_API_KEY:
                # Initialize with API key and optionally base_url if needed
                client_kwargs = {"api_key": Config.ELEVENLABS_API_KEY}
                if Config.ELEVENLABS_BASE_URL and Config.ELEVENLABS_BASE_URL != "https://api.elevenlabs.io/v1":
                    client_kwargs["base_url"] = Config.ELEVENLABS_BASE_URL
                self._elevenlabs_client = ElevenLabs(**client_kwargs)
                print("✅ ElevenLabs client initialized successfully")
            else:
                print("⚠️ ElevenLabs API key not found")
        except Exception as e:
            print(f"❌ Failed to initialize ElevenLabs: {e}")
            self._elevenlabs_client = None
    
    def _init_service_role_db(self):
        """Initialize service role database for backend operations"""
        # PRODUCTION ARCHITECTURE: Use service role key for backend operations
        # - Frontend: Anon key + RLS for user operations
        # - Backend: Service role key for system operations (voice cloning, file storage, etc.)
        try:
            from supabase import create_client
            if Config.SUPABASE_SERVICE_ROLE_KEY:
                self.service_db = create_client(Config.SUPABASE_URL, Config.SUPABASE_SERVICE_ROLE_KEY)
                print("✅ Service role database initialized for backend operations")
            else:
                print("⚠️ Service role key not found, backend operations may fail")
                self.service_db = None
        except Exception as e:
            print(f"❌ Failed to initialize service role database: {e}")
            self.service_db = None
    
    @property
    def is_configured(self) -> bool:
        """Check if ElevenLabs is properly configured"""
        return self._elevenlabs_client is not None
    
    async def create_voice_clone(
        self, 
        user_id: str, 
        voice_name: str, 
        audio_files: List[bytes],
        description: Optional[str] = None
    ) -> VoiceCloneResponse:
        """
        Create an instant voice clone using ElevenLabs API
        
        Real-world production flow:
        1. Save uploaded files to Supabase Storage
        2. Get file URLs from storage
        3. Use URLs with ElevenLabs API
        4. Store voice profile with file references
        
        Args:
            user_id: User ID
            voice_name: Name for the cloned voice
            audio_files: List of audio file bytes for training
            description: Optional description for the voice
            
        Returns:
            VoiceCloneResponse with voice_id and status
        """
        if not self.is_configured:
            return VoiceCloneResponse(
                success=False,
                message="ElevenLabs not configured",
                voice_profile=None
            )
        
        try:
            # Step 1: Save uploaded files to Supabase Storage first
            print(f"📁 Step 1: Saving {len(audio_files)} audio files to Supabase Storage...")
            stored_files = []
            
            for i, audio_data in enumerate(audio_files):
                # Generate very short filename for storage (Supabase has strict key length limits)
                # Add microseconds to ensure unique timestamps
                timestamp = datetime.now().strftime("%Y%m%d%H%M%S") + f"{datetime.now().microsecond//1000:03d}"
                # Use only first 8 chars of voice_name and remove special characters
                safe_voice_name = ''.join(c for c in voice_name[:8] if c.isalnum())
                # Use last 6 chars of user_id only
                short_user_id = user_id[-6:] if len(user_id) > 6 else user_id
                filename = f"{short_user_id}_{safe_voice_name}_{i+1}_{timestamp}.m4a"
                
                # Add small delay to prevent rapid uploads that might cause issues
                if i > 0:
                    import asyncio
                    await asyncio.sleep(0.1)  # 100ms delay between uploads
                
                # Save to Supabase Storage with custom filename
                result = await self.audio_storage.save_audio_file(
                    user_id=short_user_id,  # Use shorter user_id for path
                    audio_data=audio_data,
                    provider="voice_clone_upload",
                    text_hash=None,  # We'll handle filename generation above
                    custom_filename=filename  # Use our custom filename
                )
                
                if result.get("success"):
                    stored_files.append({
                        "filename": result.get("filename"),
                        "file_url": result.get("file_url"),
                        "file_path": result.get("file_path"),
                        "file_size": result.get("file_size")
                    })
                    print(f"   ✅ Saved file {i+1}: {result.get('filename')}")
                else:
                    print(f"   ❌ Failed to save file {i+1}: {result.get('error')}")
                    return VoiceCloneResponse(
                        success=False,
                        message=f"Failed to save audio file {i+1} to storage",
                        voice_profile=None
                    )
            
            # Step 2: Download files from Supabase Storage for ElevenLabs
            print(f"🔗 Step 2: Downloading files from Supabase Storage for ElevenLabs...")
            import tempfile
            import requests
            from pydub import AudioSegment
            import io
            
            temp_files = []
            for i, file_info in enumerate(stored_files):
                try:
                    # Download file from Supabase Storage
                    response = requests.get(file_info["file_url"])
                    response.raise_for_status()
                    
                    print(f"   🔍 Downloaded {len(response.content)} bytes for file {i+1}")
                    
                    # Convert M4A to WAV for better compatibility with ElevenLabs
                    try:
                        # Load audio with pydub
                        audio_segment = AudioSegment.from_file(io.BytesIO(response.content), format="m4a")
                        
                        # Convert to WAV format (better compatibility)
                        wav_io = io.BytesIO()
                        audio_segment.export(wav_io, format="wav", parameters=["-ac", "1", "-ar", "22050"])  # Mono, 22kHz
                        wav_data = wav_io.getvalue()
                        
                        # Create temporary WAV file
                        temp_file = tempfile.NamedTemporaryFile(delete=False, suffix='.wav')
                        temp_file.write(wav_data)
                        temp_file.close()
                        temp_files.append(temp_file.name)
                        
                        print(f"   ✅ Converted and saved file {i+1}: {file_info['filename']} -> WAV ({len(wav_data)} bytes)")
                        
                    except Exception as audio_error:
                        print(f"   ⚠️ Audio conversion failed for file {i+1}: {audio_error}")
                        print(f"   🔄 Trying direct M4A file...")
                        
                        # Fallback: Save M4A directly if conversion fails
                        temp_file = tempfile.NamedTemporaryFile(delete=False, suffix='.m4a')
                        temp_file.write(response.content)
                        temp_file.close()
                        temp_files.append(temp_file.name)
                        
                        print(f"   ✅ Saved M4A file {i+1}: {file_info['filename']}")
                    
                except Exception as e:
                    print(f"   ❌ Failed to download file {i+1}: {e}")
                    return VoiceCloneResponse(
                        success=False,
                        message=f"Failed to download audio file {i+1} from storage",
                        voice_profile=None
                    )
            
            # Step 3: Create voice clone using ElevenLabs API with temp files
            print(f"🎭 Step 3: Creating voice clone with ElevenLabs...")
            
            # Debug: Check available methods
            print(f"🔍 DEBUG: Available voices methods: {dir(self._elevenlabs_client.voices)}")
            
            # Step 3: Create voice clone using ElevenLabs IVC API (Instant Voice Cloning)
            try:
                print("🔍 Creating voice clone with ElevenLabs IVC API...")
                
                # Prepare file objects for ElevenLabs API
                # The API expects file objects or tuples with (filename, file_data, content_type)
                file_objects = []
                for temp_file_path in temp_files:
                    with open(temp_file_path, 'rb') as f:
                        file_data = f.read()
                        # Create tuple format: (filename, file_data, content_type)
                        file_name = f"voice_sample_{len(file_objects)+1}.wav"
                        file_objects.append((file_name, file_data, "audio/wav"))
                
                print(f"   📁 Prepared {len(file_objects)} file objects for ElevenLabs")
                
                # Create voice clone using IVC API with correct parameters
                voice = self._elevenlabs_client.voices.ivc.create(
                    name=voice_name,
                    files=file_objects,  # Use prepared file objects
                    description=description or f"Voice clone for {voice_name}",
                    remove_background_noise=True  # Optional: improve audio quality
                )
                
                print(f"✅ Voice clone created successfully!")
                print(f"   🆔 Voice ID: {voice.voice_id}")
                print(f"   📝 Voice Name: {voice_name}")
                
            except Exception as ivc_error:
                print(f"❌ Error with IVC API: {ivc_error}")
                
                # Try alternative file format - just file paths as strings
                try:
                    print("🔄 Retrying with file paths as strings...")
                    voice = self._elevenlabs_client.voices.ivc.create(
                        name=voice_name,
                        files=temp_files,  # Use file paths directly
                        description=description or f"Voice clone for {voice_name}",
                        remove_background_noise=True
                    )
                    print(f"✅ Voice clone created successfully with file paths!")
                    print(f"   🆔 Voice ID: {voice.voice_id}")
                    
                except Exception as ivc_error2:
                    print(f"❌ Error with file paths: {ivc_error2}")
                    
                    # Try with file handles
                    try:
                        print("🔄 Retrying with open file handles...")
                        file_handles = []
                        for temp_file_path in temp_files:
                            file_handles.append(open(temp_file_path, 'rb'))
                        
                        voice = self._elevenlabs_client.voices.ivc.create(
                            name=voice_name,
                            files=file_handles,
                            description=description or f"Voice clone for {voice_name}",
                            remove_background_noise=True
                        )
                        
                        # Close file handles
                        for fh in file_handles:
                            fh.close()
                            
                        print(f"✅ Voice clone created successfully with file handles!")
                        print(f"   🆔 Voice ID: {voice.voice_id}")
                        
                    except Exception as ivc_error3:
                        print(f"❌ All IVC methods failed:")
                        print(f"   - File objects error: {ivc_error}")
                        print(f"   - File paths error: {ivc_error2}")
                        print(f"   - File handles error: {ivc_error3}")
                        raise Exception(f"Voice cloning failed after trying all methods. Last error: {ivc_error3}")
            
            # Clean up temporary files
            for temp_file in temp_files:
                try:
                    os.unlink(temp_file)
                except:
                    pass
            
            # Step 4: Ensure user exists in profiles table first
            print(f"👤 Step 4: Ensuring user exists in profiles table...")
            try:
                # Check if user exists
                user_check = self.db.client.table('profiles').select('id').eq('id', user_id).execute()
                if not user_check.data:
                    # Create user profile
                    user_profile = {
                        'id': user_id,
                        'email': f'user-{user_id}@example.com',
                        'created_at': datetime.now().isoformat(),
                        'updated_at': datetime.now().isoformat()
                    }
                    # PRODUCTION: Use service role key for backend operations
                    if self.service_db:
                        self.service_db.table('profiles').insert(user_profile).execute()
                    else:
                        self.db.client.table('profiles').insert(user_profile).execute()
                    print(f"   ✅ Created user profile for {user_id}")
                else:
                    print(f"   ✅ User profile already exists")
            except Exception as e:
                print(f"   ⚠️ Warning: Could not ensure user profile: {e}")
            
            # Step 5: Save voice profile to database with file references
            print(f"💾 Step 5: Saving voice profile to database...")
            voice_profile = UserVoiceProfile(
                user_id=user_id,
                voice_name=voice_name,
                provider=VoiceProvider.ELEVENLABS,
                voice_id=voice.voice_id,
                status=VoiceCloneStatus.COMPLETED,
                audio_samples=[file_info["file_url"] for file_info in stored_files],  # Store file URLs
                is_active=True
            )
            
            # Insert into database using service role client (exclude id to let DB generate it)
            profile_data = voice_profile.dict()
            profile_data.pop('id', None)  # Remove id to let database generate it
            
            # PRODUCTION: Use service role key for backend operations
            if self.service_db:
                result = self.service_db.table('user_voice_profiles').insert(
                    profile_data
                ).execute()
            else:
                result = self.db.client.table('user_voice_profiles').insert(
                    profile_data
                ).execute()
            
            if result.data:
                print(f"   ✅ Voice profile saved to database")
                print(f"   🆔 Voice ID: {voice.voice_id}")
                print(f"   📁 Files stored: {len(stored_files)} files")
                print(f"   👤 User ID: {user_id}")
                print(f"   🎯 Voice profile created and active")
                
                return VoiceCloneResponse(
                    success=True,
                    message="Voice clone created successfully",
                    voice_profile=voice_profile
                )
            else:
                print(f"   ❌ Failed to save voice profile to database")
                return VoiceCloneResponse(
                    success=False,
                    message="Failed to save voice profile to database",
                    voice_profile=None
                )
                
        except Exception as e:
            print(f"❌ Error creating voice clone: {e}")
            return VoiceCloneResponse(
                success=False,
                message=f"Error creating voice clone: {str(e)}",
                voice_profile=None
            )
    
    async def get_user_voice_profiles(self, user_id: str) -> List[UserVoiceProfile]:
        """Get all voice profiles for a user"""
        try:
            result = self.db.client.table('user_voice_profiles').select('*').eq(
                'user_id', user_id
            ).eq('is_active', True).execute()
            
            if result.data:
                return [UserVoiceProfile(**profile) for profile in result.data]
            return []
            
        except Exception as e:
            print(f"❌ Error fetching voice profiles: {e}")
            return []
    
    async def delete_voice_profile(self, user_id: str, voice_id: str) -> bool:
        """Delete a voice profile"""
        try:
            result = self.db.client.table('user_voice_profiles').update(
                {'is_active': False}
            ).eq('user_id', user_id).eq('voice_id', voice_id).execute()
            
            return bool(result.data)
            
        except Exception as e:
            print(f"❌ Error deleting voice profile: {e}")
            return False
    
    async def generate_tts_with_cloned_voice(
        self, 
        text: str, 
        user_id: str, 
        voice_id: Optional[str] = None,
        language: str = "en",
        speed: float = 1.0
    ) -> TTSResponse:
        """
        Generate TTS using a cloned voice
        
        Args:
            text: Text to convert to speech
            user_id: User ID
            voice_id: Specific voice ID to use (if None, uses user's default)
            language: Language code
            speed: Speech speed multiplier
            
        Returns:
            TTSResponse with audio data
        """
        if not self.is_configured:
            return TTSResponse(
                success=False,
                message="ElevenLabs not configured",
                audio_data=None,
                audio_url=None,
                duration=None
            )
        
        try:
            # Get user's voice profiles if no specific voice_id provided
            if not voice_id:
                voice_profiles = await self.get_user_voice_profiles(user_id)
                if not voice_profiles:
                    return TTSResponse(
                        success=False,
                        message="No voice profiles found for user",
                        audio_data=None,
                        audio_url=None,
                        duration=None
                    )
                voice_id = voice_profiles[0].voice_id
            
            # Generate TTS using cloned voice
            audio_generator = self._elevenlabs_client.text_to_speech.convert(
                text=text,
                voice_id=voice_id,
                model_id="eleven_multilingual_v2",
                output_format="mp3_44100_128"
            )
            
            # Convert generator to bytes
            audio_data = b''.join(audio_generator)
            
            # Save audio file
            result = await self.audio_storage.save_audio_file(
                user_id=user_id,
                audio_data=audio_data,
                provider="elevenlabs"
            )
            audio_url = result.get("file_url") if result.get("success") else None
            
            # Estimate duration (rough calculation)
            duration = len(audio_data) / 16000  # Assuming 16kHz sample rate
            
            return TTSResponse(
                success=True,
                message="TTS generated successfully with cloned voice",
                audio_url=audio_url,
                duration_seconds=duration
            )
            
        except Exception as e:
            print(f"❌ Error generating TTS with cloned voice: {e}")
            return TTSResponse(
                success=False,
                message=f"Error generating TTS: {str(e)}",
                audio_data=None,
                audio_url=None,
                duration=None
            )
    
    async def test_voice_clone(self, voice_id: str, test_text: str = "Hello, this is a test of my cloned voice.") -> TTSResponse:
        """Test a voice clone with sample text"""
        if not self.is_configured:
            return TTSResponse(
                success=False,
                message="ElevenLabs not configured",
                audio_data=None,
                audio_url=None,
                duration=None
            )
        
        try:
            # Generate test audio
            audio_generator = self._elevenlabs_client.text_to_speech.convert(
                text=test_text,
                voice_id=voice_id,
                model_id="eleven_multilingual_v2",
                output_format="mp3_44100_128"
            )
            
            # Convert generator to bytes
            audio_data = b''.join(audio_generator)
            
            # Save test audio
            result = await self.audio_storage.save_audio_file(
                user_id="test_user",
                audio_data=audio_data,
                provider="elevenlabs"
            )
            audio_url = result.get("file_url") if result.get("success") else None
            
            # Estimate duration
            duration = len(audio_data) / 16000
            
            return TTSResponse(
                success=True,
                message="Test audio generated successfully",
                audio_url=audio_url,
                duration_seconds=duration
            )
            
        except Exception as e:
            print(f"❌ Error testing voice clone: {e}")
            return TTSResponse(
                success=False,
                message=f"Error testing voice clone: {str(e)}",
                audio_data=None,
                audio_url=None,
                duration=None
            )
