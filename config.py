import os
from dotenv import load_dotenv

load_dotenv(override=True)

class Config:
    """Configuration class for the application"""
    
    # OpenAI Configuration
    OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
    
    # LangSmith Configuration
    LANGSMITH_PROJECT = os.getenv("LANGSMITH_PROJECT", "polynot")
    LANGSMITH_API_KEY = os.getenv("LANGSMITH_API_KEY")
    
    # Supabase Configuration
    SUPABASE_URL = os.getenv("SUPABASE_URL")
    SUPABASE_ANON_KEY = os.getenv("SUPABASE_ANON_KEY")
    SUPABASE_SERVICE_ROLE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY")
    
    # LLM Configuration
    LLM_MODEL = os.getenv("LLM_MODEL", "gpt-4o-mini")
    LLM_TEMPERATURE = float(os.getenv("LLM_TEMPERATURE", "0.3"))  # Lower temperature for more focused generation
    
    # Topic Focus Configuration
    TOPIC_FOCUS_TEMPERATURE = float(os.getenv("TOPIC_FOCUS_TEMPERATURE", "0.2"))  # Even lower for topic-specific generation
    
    # Default Language Settings
    LANGUAGE_TO_LEARN = os.getenv("LANGUAGE_TO_LEARN", "English")  # What learners want to learn
    LEARNERS_NATIVE_LANGUAGE = os.getenv("LEARNERS_NATIVE_LANGUAGE", "Vietnamese")  # Learner's native language
    
    # Generation Settings
    DEFAULT_VOCAB_PER_BATCH = int(os.getenv("DEFAULT_VOCAB_PER_BATCH", "20"))  # Reduced from 50
    DEFAULT_PHRASAL_VERBS_PER_BATCH = int(os.getenv("DEFAULT_PHRASAL_VERBS_PER_BATCH", "10"))  # Reduced from 25
    DEFAULT_IDIOMS_PER_BATCH = int(os.getenv("DEFAULT_IDIOMS_PER_BATCH", "5"))  # Reduced from 25
    DEFAULT_DELAY_SECONDS = int(os.getenv("DEFAULT_DELAY_SECONDS", "3"))
    
    # TTS Configuration
    # Google TTS
    GOOGLE_TTS_API_KEY = os.getenv("GOOGLE_TTS_API_KEY")
    GOOGLE_TTS_PROJECT_ID = os.getenv("GOOGLE_TTS_PROJECT_ID")
    
    # ElevenLabs
    ELEVENLABS_API_KEY = os.getenv("ELEVENLABS_API_KEY")
    ELEVENLABS_BASE_URL = os.getenv("ELEVENLABS_BASE_URL", "https://api.elevenlabs.io/v1")
    
    # TTS Settings
    DEFAULT_TTS_LANGUAGE = os.getenv("DEFAULT_TTS_LANGUAGE", "en-US")
    MAX_FREE_TTS_REQUESTS_PER_DAY = int(os.getenv("MAX_FREE_TTS_REQUESTS_PER_DAY", "50"))
    MAX_PREMIUM_TTS_REQUESTS_PER_DAY = int(os.getenv("MAX_PREMIUM_TTS_REQUESTS_PER_DAY", "500"))
    TTS_AUDIO_FORMAT = os.getenv("TTS_AUDIO_FORMAT", "mp3")
    TTS_AUDIO_QUALITY = os.getenv("TTS_AUDIO_QUALITY", "high")  # low, medium, high
    
    # Audio Storage Configuration
    AUDIO_STORAGE_TYPE = os.getenv("AUDIO_STORAGE_TYPE", "local")  # local, s3, gcs, supabase
    LOCAL_AUDIO_PATH = os.getenv("LOCAL_AUDIO_PATH", "audio_files")
    
    # AWS S3 Configuration
    AWS_ACCESS_KEY_ID = os.getenv("AWS_ACCESS_KEY_ID")
    AWS_SECRET_ACCESS_KEY = os.getenv("AWS_SECRET_ACCESS_KEY")
    AWS_REGION = os.getenv("AWS_REGION", "us-east-1")
    AWS_S3_BUCKET = os.getenv("AWS_S3_BUCKET")
    
    # Google Cloud Storage Configuration
    GCS_BUCKET_NAME = os.getenv("GCS_BUCKET_NAME")
    GOOGLE_APPLICATION_CREDENTIALS = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
    
    @classmethod
    def validate(cls):
        """Validate that all required environment variables are set"""
        required_vars = [
            "OPENAI_API_KEY",
            "SUPABASE_URL", 
            "SUPABASE_ANON_KEY"
        ]
        
        missing_vars = []
        for var in required_vars:
            if not getattr(cls, var):
                missing_vars.append(var)
        
        if missing_vars:
            raise ValueError(f"Missing required environment variables: {', '.join(missing_vars)}")
        
        return True
    
    @classmethod
    def print_config(cls):
        """Print current configuration (without sensitive data)"""
        print("=== Configuration ===")
        print(f"LLM Model: {cls.LLM_MODEL}")
        print(f"LLM Temperature: {cls.LLM_TEMPERATURE}")
        print(f"Target Language: {cls.LANGUAGE_TO_LEARN}")
        print(f"Original Language: {cls.LEARNERS_NATIVE_LANGUAGE}")
        print(f"Vocab per batch: {cls.DEFAULT_VOCAB_PER_BATCH}")
        print(f"Phrasal verbs per batch: {cls.DEFAULT_PHRASAL_VERBS_PER_BATCH}")
        print(f"Idioms per batch: {cls.DEFAULT_IDIOMS_PER_BATCH}")
        print(f"Delay seconds: {cls.DEFAULT_DELAY_SECONDS}")
        print(f"Supabase URL: {cls.SUPABASE_URL[:20]}..." if cls.SUPABASE_URL else "Not set")
        print(f"OpenAI API Key: {'Set' if cls.OPENAI_API_KEY else 'Not set'}")
        print("====================") 