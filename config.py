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
    
    # LLM Configuration
    LLM_MODEL = os.getenv("LLM_MODEL", "gpt-4o-mini")
    LLM_TEMPERATURE = float(os.getenv("LLM_TEMPERATURE", "0.7"))
    
    # Default Language Settings
    DEFAULT_TARGET_LANGUAGE = os.getenv("DEFAULT_TARGET_LANGUAGE", "Vietnamese")
    DEFAULT_ORIGINAL_LANGUAGE = os.getenv("DEFAULT_ORIGINAL_LANGUAGE", "English")
    
    # Generation Settings
    DEFAULT_VOCAB_PER_BATCH = int(os.getenv("DEFAULT_VOCAB_PER_BATCH", "10"))
    DEFAULT_PHRASAL_VERBS_PER_BATCH = int(os.getenv("DEFAULT_PHRASAL_VERBS_PER_BATCH", "5"))
    DEFAULT_IDIOMS_PER_BATCH = int(os.getenv("DEFAULT_IDIOMS_PER_BATCH", "5"))
    DEFAULT_DELAY_SECONDS = int(os.getenv("DEFAULT_DELAY_SECONDS", "3"))
    
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
        print(f"Target Language: {cls.DEFAULT_TARGET_LANGUAGE}")
        print(f"Original Language: {cls.DEFAULT_ORIGINAL_LANGUAGE}")
        print(f"Vocab per batch: {cls.DEFAULT_VOCAB_PER_BATCH}")
        print(f"Phrasal verbs per batch: {cls.DEFAULT_PHRASAL_VERBS_PER_BATCH}")
        print(f"Idioms per batch: {cls.DEFAULT_IDIOMS_PER_BATCH}")
        print(f"Delay seconds: {cls.DEFAULT_DELAY_SECONDS}")
        print(f"Supabase URL: {cls.SUPABASE_URL[:20]}..." if cls.SUPABASE_URL else "Not set")
        print(f"OpenAI API Key: {'Set' if cls.OPENAI_API_KEY else 'Not set'}")
        print("====================") 