import os
import json
from typing import List
from models import VocabEntry, CEFRLevel
from supabase import create_client, Client
from dotenv import load_dotenv

load_dotenv()

class VocabDatabase:
    def __init__(self):
        """Initialize Supabase client"""
        url: str = os.getenv("SUPABASE_URL")
        key: str = os.getenv("SUPABASE_ANON_KEY")
        
        if not url or not key:
            raise ValueError("SUPABASE_URL and SUPABASE_ANON_KEY must be set in environment variables")
        
        self.supabase: Client = create_client(url, key)
        self.init_database()
    
    def init_database(self):
        """Initialize the database with required tables
        
        Note: You need to create these tables in your Supabase dashboard first.
        Here are the SQL commands to run in Supabase SQL editor:
        
        CREATE TABLE IF NOT EXISTS vocab_entries (
            id BIGSERIAL PRIMARY KEY,
            word TEXT NOT NULL,
            definition TEXT NOT NULL,
            translation TEXT NOT NULL,
            example TEXT NOT NULL,
            example_translation TEXT NOT NULL,
            level TEXT NOT NULL,
            part_of_speech TEXT,
            topic TEXT,
            target_language TEXT,
            original_language TEXT,
            created_at TIMESTAMPTZ DEFAULT NOW(),
            UNIQUE(word, topic, level, part_of_speech)
        );
        
        CREATE TABLE IF NOT EXISTS topic_lists (
            id BIGSERIAL PRIMARY KEY,
            list_name TEXT NOT NULL,
            topics JSONB NOT NULL,
            category TEXT,
            level TEXT NOT NULL,
            target_language TEXT,
            original_language TEXT,
            created_at TIMESTAMPTZ DEFAULT NOW()
        );
        """
        # Tables should be created via Supabase dashboard/SQL editor
        # This method is kept for interface compatibility
        print("Database tables should be created via Supabase dashboard")
        print("See the docstring above for the SQL commands to run")
    
    def insert_vocab_entries(self, entries: List[VocabEntry], topic: str = None, 
                           target_language: str = None, original_language: str = None):
        """Insert multiple vocab entries into the database, skipping duplicates"""
        inserted_count = 0
        skipped_count = 0
        
        for entry in entries:
            try:
                data = {
                    "word": entry.word,
                    "definition": entry.definition,
                    "translation": entry.translation,
                    "example": entry.example,
                    "example_translation": entry.example_translation,
                    "level": entry.level.value,
                    "part_of_speech": getattr(entry, 'part_of_speech', None),
                    "topic": topic,
                    "target_language": target_language,
                    "original_language": original_language
                }
                
                # Check if entry already exists
                existing = self.supabase.table("vocab_entries").select("id").eq("word", entry.word).eq("topic", topic).eq("level", entry.level.value).eq("part_of_speech", getattr(entry, 'part_of_speech', None)).execute()
                
                if existing.data:
                    skipped_count += 1
                    print(f"Skipped duplicate: {entry.word} (topic: {topic}, level: {entry.level.value})")
                else:
                    result = self.supabase.table("vocab_entries").insert(data).execute()
                    inserted_count += 1
                    
            except Exception as e:
                print(f"Error inserting {entry.word}: {str(e)}")
                skipped_count += 1
        
        print(f"Inserted {inserted_count} new vocab entries, skipped {skipped_count} duplicates")
    
    def get_vocab_entries(self, topic: str = None, level: CEFRLevel = None, limit: int = 100):
        """Retrieve vocab entries from database with optional filters"""
        query = self.supabase.table("vocab_entries").select("*")
        
        if topic:
            query = query.eq("topic", topic)
        
        if level:
            query = query.eq("level", level.value)
        
        query = query.order("created_at", desc=True).limit(limit)
        
        result = query.execute()
        
        entries = []
        for row in result.data:
            entry = VocabEntry(
                word=row["word"],
                definition=row["definition"],
                translation=row["translation"],
                example=row["example"],
                example_translation=row["example_translation"],
                level=CEFRLevel(row["level"])
            )
            entries.append(entry)
        
        return entries 

    def get_existing_combinations(self, topic: str = None) -> List[tuple]:
        """Get existing word combinations to avoid duplicates"""
        query = self.supabase.table("vocab_entries").select("word,level,part_of_speech")
        
        if topic:
            query = query.eq("topic", topic)
        
        result = query.execute()
        
        return [(row["word"], row["level"], row["part_of_speech"]) for row in result.data]
    
    def save_topic_list(self, topics: List[str], list_name: str = None, 
                       category: str = None, level: CEFRLevel = CEFRLevel.A2,
                       target_language: str = "Vietnamese", original_language: str = "English"):
        """Save a custom topic list to the database"""
        # Generate list name if not provided
        if not list_name:
            list_name = f"custom_list_{len(topics)}_topics"
        
        data = {
            "list_name": list_name,
            "topics": topics,  # Supabase handles JSON serialization
            "category": category,
            "level": level.value,
            "target_language": target_language,
            "original_language": original_language
        }
        
        result = self.supabase.table("topic_lists").insert(data).execute()
        print(f"Saved topic list '{list_name}' with {len(topics)} topics")
    
    def get_topic_lists(self) -> List[dict]:
        """Get all saved topic lists"""
        result = self.supabase.table("topic_lists").select("*").order("created_at", desc=True).execute()
        
        topic_lists = []
        for row in result.data:
            topic_lists.append({
                "list_name": row["list_name"],
                "topics": row["topics"],  # Already parsed from JSON
                "category": row["category"],
                "level": row["level"],
                "target_language": row["target_language"],
                "original_language": row["original_language"],
                "created_at": row["created_at"]
            })
        
        return topic_lists 