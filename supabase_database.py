from supabase import create_client, Client
from typing import List, Dict, Any, Optional
from models import VocabEntry, CEFRLevel
import os
from dotenv import load_dotenv
import json
from datetime import datetime

load_dotenv(override=True)

class SupabaseVocabDatabase:
    def __init__(self):
        """Initialize Supabase client"""
        self.supabase_url = os.getenv("SUPABASE_URL")
        self.supabase_key = os.getenv("SUPABASE_ANON_KEY")
        
        if not self.supabase_url or not self.supabase_key:
            raise ValueError("SUPABASE_URL and SUPABASE_ANON_KEY must be set in environment variables")
        
        self.client: Client = create_client(self.supabase_url, self.supabase_key)
    
    def insert_vocab_entries(self, entries: List[VocabEntry], topic: str = None, 
                           target_language: str = None, original_language: str = None):
        """Insert multiple vocab entries into Supabase, skipping duplicates"""
        inserted_count = 0
        skipped_count = 0
        
        for entry in entries:
            try:
                # Prepare data for insertion
                data = {
                    "word": entry.word,
                    "definition": entry.definition,
                    "translation": entry.translation,
                    "example": entry.example,
                    "example_translation": entry.example_translation,
                    "level": entry.level.value,
                    "part_of_speech": entry.part_of_speech.value if entry.part_of_speech else None,
                    "topic": topic,
                    "target_language": target_language,
                    "original_language": original_language
                }
                
                # Insert into Supabase
                result = self.client.table("vocab_entries").insert(data).execute()
                
                if result.data:
                    inserted_count += 1
                else:
                    skipped_count += 1
                    
            except Exception as e:
                # Check if it's a unique constraint violation
                if "duplicate key" in str(e).lower() or "unique" in str(e).lower():
                    skipped_count += 1
                    print(f"Skipped duplicate: {entry.word} (topic: {topic}, level: {entry.level.value})")
                else:
                    print(f"Error inserting {entry.word}: {e}")
                    raise
        
        print(f"Inserted {inserted_count} new vocab entries, skipped {skipped_count} duplicates")
    
    def get_vocab_entries(self, topic: str = None, level: CEFRLevel = None, limit: int = 100) -> List[Dict[str, Any]]:
        """Retrieve vocab entries from Supabase with optional filters"""
        query = self.client.table("vocab_entries").select("*")
        
        if topic:
            query = query.eq("topic", topic)
        
        if level:
            query = query.eq("level", level.value)
        
        query = query.limit(limit).order("created_at", desc=True)
        
        result = query.execute()
        return result.data if result.data else []
    
    def get_existing_combinations(self, topic: str = None) -> List[tuple]:
        """Get existing word combinations for a topic to avoid duplicates"""
        query = self.client.table("vocab_entries").select("word, level, part_of_speech")
        
        if topic:
            query = query.eq("topic", topic)
        
        result = query.execute()
        
        if not result.data:
            return []
        
        # Convert to tuple format for compatibility
        combinations = []
        for row in result.data:
            combinations.append((
                row["word"],
                row["level"],
                row["part_of_speech"]
            ))
        
        return combinations
    
    def save_topic_list(self, topics: List[str], list_name: str = None, 
                       category: str = None, level: CEFRLevel = CEFRLevel.A2,
                       target_language: str = "Vietnamese", original_language: str = "English"):
        """Save a topic list to Supabase"""
        if not list_name:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            list_name = f"topic_list_{timestamp}"
        
        data = {
            "list_name": list_name,
            "topics": json.dumps(topics),  # Store as JSONB
            "category": category,
            "level": level.value,
            "target_language": target_language,
            "original_language": original_language
        }
        
        try:
            result = self.client.table("topic_lists").insert(data).execute()
            print(f"Saved topic list: {list_name}")
            return result.data[0] if result.data else None
        except Exception as e:
            print(f"Error saving topic list: {e}")
            raise
    
    def get_topic_lists(self) -> List[dict]:
        """Get all saved topic lists from Supabase"""
        result = self.client.table("topic_lists").select("*").order("created_at", desc=True).execute()
        
        if not result.data:
            return []
        
        # Parse JSONB topics back to list
        topic_lists = []
        for row in result.data:
            topic_list = dict(row)
            # Parse the JSONB topics field back to a list
            if isinstance(topic_list["topics"], str):
                topic_list["topics"] = json.loads(topic_list["topics"])
            topic_lists.append(topic_list)
        
        return topic_lists
    
    def get_vocab_stats(self, topic: str = None) -> Dict[str, Any]:
        """Get statistics about vocab entries"""
        query = self.client.table("vocab_entries").select("*", count="exact")
        
        if topic:
            query = query.eq("topic", topic)
        
        result = query.execute()
        total_count = result.count if hasattr(result, 'count') else len(result.data or [])
        
        # Get level distribution
        level_query = self.client.table("vocab_entries").select("level")
        if topic:
            level_query = level_query.eq("topic", topic)
        
        level_result = level_query.execute()
        level_distribution = {}
        if level_result.data:
            for row in level_result.data:
                level = row["level"]
                level_distribution[level] = level_distribution.get(level, 0) + 1
        
        return {
            "total_entries": total_count,
            "level_distribution": level_distribution,
            "topic": topic
        }
    
    def delete_vocab_entries(self, topic: str = None, level: CEFRLevel = None):
        """Delete vocab entries with optional filters"""
        query = self.client.table("vocab_entries").delete()
        
        if topic:
            query = query.eq("topic", topic)
        
        if level:
            query = query.eq("level", level.value)
        
        result = query.execute()
        print(f"Deleted vocab entries: {len(result.data) if result.data else 0}")
        return result.data
    
    def search_vocab_entries(self, search_term: str, topic: str = None, limit: int = 50) -> List[Dict[str, Any]]:
        """Search vocab entries by word or definition"""
        query = self.client.table("vocab_entries").select("*")
        
        # Use text search (PostgreSQL full-text search)
        query = query.text_search("word", search_term)
        
        if topic:
            query = query.eq("topic", topic)
        
        query = query.limit(limit).order("created_at", desc=True)
        
        result = query.execute()
        return result.data if result.data else [] 