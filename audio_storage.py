"""
Audio Storage Service
Handles audio file storage with multiple backend options
"""

import os
import io
import tempfile
from typing import Optional, Dict, Any
from datetime import datetime
import hashlib
import mimetypes

# Cloud storage options
try:
    import boto3
    from botocore.exceptions import ClientError
    AWS_AVAILABLE = True
except ImportError:
    AWS_AVAILABLE = False

try:
    from google.cloud import storage
    GCS_AVAILABLE = True
except ImportError:
    GCS_AVAILABLE = False

from config import Config


class AudioStorageService:
    """Audio storage service with multiple backend support"""
    
    def __init__(self):
        self.storage_type = os.getenv("AUDIO_STORAGE_TYPE", "local")  # local, s3, gcs, supabase
        self._init_storage()
    
    def _init_storage(self):
        """Initialize storage backend"""
        if self.storage_type == "s3" and AWS_AVAILABLE:
            self._init_s3()
        elif self.storage_type == "gcs" and GCS_AVAILABLE:
            self._init_gcs()
        elif self.storage_type == "supabase":
            self._init_supabase()
        else:
            self._init_local()
    
    def _init_s3(self):
        """Initialize AWS S3 storage"""
        try:
            self.s3_client = boto3.client(
                's3',
                aws_access_key_id=os.getenv("AWS_ACCESS_KEY_ID"),
                aws_secret_access_key=os.getenv("AWS_SECRET_ACCESS_KEY"),
                region_name=os.getenv("AWS_REGION", "us-east-1")
            )
            self.bucket_name = os.getenv("AWS_S3_BUCKET")
            print("✅ AWS S3 storage initialized")
        except Exception as e:
            print(f"❌ Failed to initialize S3: {e}")
            self._init_local()
    
    def _init_gcs(self):
        """Initialize Google Cloud Storage"""
        try:
            self.gcs_client = storage.Client()
            self.bucket_name = os.getenv("GCS_BUCKET_NAME")
            self.bucket = self.gcs_client.bucket(self.bucket_name)
            print("✅ Google Cloud Storage initialized")
        except Exception as e:
            print(f"❌ Failed to initialize GCS: {e}")
            self._init_local()
    
    def _init_supabase(self):
        """Initialize Supabase storage"""
        try:
            from supabase import create_client
            self.supabase_url = os.getenv("SUPABASE_URL")
            
            # Use service role key for storage operations
            service_role_key = os.getenv("SUPABASE_SERVICE_ROLE_KEY")
            if service_role_key:
                self.supabase_key = service_role_key
                print("✅ Supabase storage initialized with service role key")
            else:
                self.supabase_key = os.getenv("SUPABASE_ANON_KEY")
                print("✅ Supabase storage initialized with anon key")
            
            self.supabase_client = create_client(self.supabase_url, self.supabase_key)
            self.bucket_name = "audio-files"
        except Exception as e:
            print(f"❌ Failed to initialize Supabase storage: {e}")
            self._init_local()
    
    def _init_local(self):
        """Initialize local file storage"""
        self.local_storage_path = os.getenv("LOCAL_AUDIO_PATH", "audio_files")
        os.makedirs(self.local_storage_path, exist_ok=True)
        print("✅ Local storage initialized")
    
    async def save_audio_file(self, user_id: str, audio_data: bytes, provider: str, 
                            text_hash: Optional[str] = None, custom_filename: Optional[str] = None) -> Dict[str, Any]:
        """Save audio file and return metadata"""
        try:
            # Use custom filename if provided, otherwise generate one
            if custom_filename:
                filename = custom_filename
            else:
                # Generate filename
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                if text_hash:
                    filename = f"tts_{user_id}_{provider}_{text_hash[:8]}_{timestamp}.mp3"
                else:
                    filename = f"tts_{user_id}_{provider}_{timestamp}.mp3"
            
            # Save based on storage type
            if self.storage_type == "s3":
                return await self._save_to_s3(user_id, audio_data, filename)
            elif self.storage_type == "gcs":
                return await self._save_to_gcs(user_id, audio_data, filename)
            elif self.storage_type == "supabase":
                return await self._save_to_supabase(user_id, audio_data, filename)
            else:
                return await self._save_to_local(user_id, audio_data, filename)
                
        except Exception as e:
            print(f"Error saving audio file: {e}")
            return {
                "success": False,
                "error": str(e),
                "filename": None,
                "file_url": None,
                "file_size": 0
            }
    
    async def _save_to_s3(self, user_id: str, audio_data: bytes, filename: str) -> Dict[str, Any]:
        """Save audio file to AWS S3"""
        try:
            key = f"tts/{user_id}/{filename}"
            
            # Upload to S3
            self.s3_client.put_object(
                Bucket=self.bucket_name,
                Key=key,
                Body=audio_data,
                ContentType="audio/mpeg",
                ACL="public-read"  # Make publicly accessible
            )
            
            # Generate public URL
            file_url = f"https://{self.bucket_name}.s3.amazonaws.com/{key}"
            
            return {
                "success": True,
                "filename": filename,
                "file_url": file_url,
                "file_size": len(audio_data),
                "storage_type": "s3",
                "key": key
            }
            
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "filename": filename,
                "file_url": None,
                "file_size": len(audio_data)
            }
    
    async def _save_to_gcs(self, user_id: str, audio_data: bytes, filename: str) -> Dict[str, Any]:
        """Save audio file to Google Cloud Storage"""
        try:
            blob_name = f"tts/{user_id}/{filename}"
            blob = self.bucket.blob(blob_name)
            
            # Upload to GCS
            blob.upload_from_string(
                audio_data,
                content_type="audio/mpeg"
            )
            
            # Make publicly accessible
            blob.make_public()
            
            # Generate public URL
            file_url = blob.public_url
            
            return {
                "success": True,
                "filename": filename,
                "file_url": file_url,
                "file_size": len(audio_data),
                "storage_type": "gcs",
                "blob_name": blob_name
            }
            
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "filename": filename,
                "file_url": None,
                "file_size": len(audio_data)
            }
    
    async def _save_to_supabase(self, user_id: str, audio_data: bytes, filename: str) -> Dict[str, Any]:
        """Save audio file to Supabase Storage"""
        try:
            # Use very short path to avoid Supabase key length limits (max ~100 chars)
            file_path = f"{user_id}/{filename}"
            
            # Debug: Print file path and filename details
            print(f"🔍 DEBUG: Uploading to Supabase Storage:")
            print(f"  📁 Bucket: {self.bucket_name}")
            print(f"  📄 File path: {file_path} (length: {len(file_path)})")
            print(f"  📊 File size: {len(audio_data)} bytes")
            
            # Check if file already exists and delete it first if it does
            try:
                existing_files = self.supabase_client.storage.from_(self.bucket_name).list(user_id)
                existing_filenames = [f.get('name', '') for f in existing_files if f.get('name')]
                if filename in existing_filenames:
                    print(f"🗑️  File exists, removing first: {filename}")
                    self.supabase_client.storage.from_(self.bucket_name).remove([file_path])
            except Exception as check_error:
                print(f"⚠️  Could not check/remove existing file: {check_error}")
            
            # Upload to Supabase Storage
            result = self.supabase_client.storage.from_(self.bucket_name).upload(
                file_path,
                audio_data,
                file_options={
                    "content-type": "audio/mpeg",
                    "cache-control": "3600"
                }
            )
            
            print(f"✅ Upload result: {result}")
            
            # Get public URL
            public_url = self.supabase_client.storage.from_(self.bucket_name).get_public_url(file_path)
            
            return {
                "success": True,
                "filename": filename,
                "file_url": public_url,
                "file_size": len(audio_data),
                "storage_type": "supabase",
                "file_path": file_path
            }
            
        except Exception as e:
            print(f"❌ Supabase storage error: {e}")
            print(f"❌ Error type: {type(e)}")
            # Try to extract more specific error info if available
            if hasattr(e, 'response'):
                print(f"❌ Response: {e.response}")
            if hasattr(e, 'message'):
                print(f"❌ Message: {e.message}")
            # For storage3.utils.StorageException, try to get more details
            if 'StorageException' in str(type(e)):
                print(f"❌ StorageException details: {vars(e) if hasattr(e, '__dict__') else 'No details'}")
                try:
                    # Try to get the actual error message from the exception
                    error_details = str(e)
                    print(f"❌ Full error string: {error_details}")
                except:
                    pass
            return {
                "success": False,
                "error": str(e),
                "filename": filename,
                "file_url": None,
                "file_size": len(audio_data)
            }
    
    async def _save_to_local(self, user_id: str, audio_data: bytes, filename: str) -> Dict[str, Any]:
        """Save audio file to local filesystem"""
        try:
            # Create user directory
            user_dir = os.path.join(self.local_storage_path, user_id)
            os.makedirs(user_dir, exist_ok=True)
            
            # Save file
            file_path = os.path.join(user_dir, filename)
            with open(file_path, 'wb') as f:
                f.write(audio_data)
            
            # Generate URL (you'll need to serve these files via your web server)
            file_url = f"/audio/{user_id}/{filename}"
            
            return {
                "success": True,
                "filename": filename,
                "file_url": file_url,
                "file_size": len(audio_data),
                "storage_type": "local",
                "file_path": file_path
            }
            
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "filename": filename,
                "file_url": None,
                "file_size": len(audio_data)
            }
    
    async def delete_audio_file(self, user_id: str, filename: str) -> bool:
        """Delete audio file from storage"""
        try:
            if self.storage_type == "s3":
                key = f"tts/{user_id}/{filename}"
                self.s3_client.delete_object(Bucket=self.bucket_name, Key=key)
            elif self.storage_type == "gcs":
                blob_name = f"tts/{user_id}/{filename}"
                blob = self.bucket.blob(blob_name)
                blob.delete()
            elif self.storage_type == "supabase":
                file_path = f"tts/{user_id}/{filename}"
                self.supabase_client.storage.from_(self.bucket_name).remove([file_path])
            else:
                file_path = os.path.join(self.local_storage_path, user_id, filename)
                if os.path.exists(file_path):
                    os.remove(file_path)
            
            return True
            
        except Exception as e:
            print(f"Error deleting audio file: {e}")
            return False
    
    def generate_text_hash(self, text: str) -> str:
        """Generate hash for text to enable caching"""
        return hashlib.md5(text.encode()).hexdigest()
    
    async def get_audio_file_info(self, user_id: str, filename: str) -> Optional[Dict[str, Any]]:
        """Get audio file information"""
        try:
            if self.storage_type == "s3":
                key = f"tts/{user_id}/{filename}"
                response = self.s3_client.head_object(Bucket=self.bucket_name, Key=key)
                return {
                    "file_size": response['ContentLength'],
                    "last_modified": response['LastModified'],
                    "content_type": response['ContentType']
                }
            elif self.storage_type == "gcs":
                blob_name = f"tts/{user_id}/{filename}"
                blob = self.bucket.blob(blob_name)
                if blob.exists():
                    blob.reload()
                    return {
                        "file_size": blob.size,
                        "last_modified": blob.updated,
                        "content_type": blob.content_type
                    }
            elif self.storage_type == "supabase":
                file_path = f"tts/{user_id}/{filename}"
                files = self.supabase_client.storage.from_(self.bucket_name).list(file_path)
                if files:
                    return {
                        "file_size": files[0].get('metadata', {}).get('size'),
                        "last_modified": files[0].get('updated_at'),
                        "content_type": "audio/mpeg"
                    }
            else:
                file_path = os.path.join(self.local_storage_path, user_id, filename)
                if os.path.exists(file_path):
                    stat = os.stat(file_path)
                    return {
                        "file_size": stat.st_size,
                        "last_modified": datetime.fromtimestamp(stat.st_mtime),
                        "content_type": "audio/mpeg"
                    }
            
            return None
            
        except Exception as e:
            print(f"Error getting audio file info: {e}")
            return None


# Global instance
audio_storage = AudioStorageService()
