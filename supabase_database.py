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
    
    def get_topic_id(self, topic_name: str, category_name: str = None) -> Optional[str]:
        """Get topic ID by name (category not used)."""
        result = self.client.table("topics").select("id").eq("name", topic_name).execute()
        return result.data[0]["id"] if result.data else None
    
    def get_topic_name(self, topic_id: str) -> Optional[str]:
        """Get topic name by ID"""
        result = self.client.table("topics").select("name").eq("id", topic_id).execute()
        return result.data[0]["name"] if result.data else None
    
    def get_category_id(self, category_name: str) -> Optional[str]:
        """Get category ID by name"""
        # Since we don't have a categories table, return None
        return None
    
    def create_topic_if_not_exists(self, topic_name: str, category_name: str = None) -> str:
        """Create a topic if it doesn't exist and return the topic ID"""
        # Check if topic already exists
        existing_topic_id = self.get_topic_id(topic_name, category_name)
        if existing_topic_id:
            return existing_topic_id
        
        # Create new topic
        topic_data = {"name": topic_name}
        
        try:
            result = self.client.table("topics").insert(topic_data).execute()
            if result.data:
                new_topic_id = result.data[0]["id"]
                print(f"Created new topic: '{topic_name}' with ID: {new_topic_id}")
                return new_topic_id
            else:
                raise ValueError(f"Failed to create topic '{topic_name}'")
        except Exception as e:
            print(f"Error creating topic '{topic_name}': {e}")
            raise

    def insert_vocab_entries(self, entries: List[VocabEntry], topic_name: str = None, 
                           category_name: str = None, target_language: str = None, 
                           original_language: str = None):
        """Insert multiple vocab entries into Supabase, skipping duplicates"""
        inserted_count = 0
        skipped_count = 0
        
        # Enforce that every vocab must be linked to a topic
        if not topic_name:
            raise ValueError("topic_name is required to insert vocab entries and must not be None")
        
        # Get or create topic ID
        topic_id = self.create_topic_if_not_exists(topic_name, category_name)
        if not topic_id:
            # Defensive: create_topic_if_not_exists should return an ID or raise
            raise RuntimeError(f"Failed to resolve topic_id for topic '{topic_name}'")
        
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
                    "topic_id": topic_id,
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
                    print(f"Skipped duplicate: {entry.word} (topic: {topic_name}, level: {entry.level.value})")
                else:
                    print(f"Error inserting {entry.word}: {e}")
                    raise
        
        print(f"Inserted {inserted_count} new vocab entries, skipped {skipped_count} duplicates")
    
    def get_vocab_entries(self, topic_name: str = None, category_name: str = None, 
                         level: CEFRLevel = None, limit: int = 100) -> List[Dict[str, Any]]:
        """Retrieve vocab entries from Supabase with optional filters"""
        query = self.client.table("vocab_entries").select("*")
        
        if topic_name:
            topic_id = self.get_topic_id(topic_name, category_name)
            if topic_id:
                query = query.eq("topic_id", topic_id)
        
        if level:
            query = query.eq("level", level.value)
        
        query = query.limit(limit).order("created_at", desc=True)
        
        result = query.execute()
        return result.data if result.data else []
    
    def get_existing_combinations(self, topic_name: str = None, category_name: str = None) -> List[tuple]:
        """Get existing word combinations for a topic to avoid duplicates"""
        query = self.client.table("vocab_entries").select("word, level, part_of_speech")
        
        if topic_name:
            topic_id = self.get_topic_id(topic_name, category_name)
            if topic_id:
                query = query.eq("topic_id", topic_id)
        
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
    
    def get_vocab_stats(self, topic_name: str = None, category_name: str = None) -> Dict[str, Any]:
        """Get statistics about vocab entries"""
        query = self.client.table("vocab_entries").select("*", count="exact")
        
        if topic_name:
            topic_id = self.get_topic_id(topic_name, category_name)
            if topic_id:
                query = query.eq("topic_id", topic_id)
        
        result = query.execute()
        total_count = result.count if hasattr(result, 'count') else len(result.data or [])
        
        # Get level distribution
        level_query = self.client.table("vocab_entries").select("level")
        if topic_name:
            topic_id = self.get_topic_id(topic_name, category_name)
            if topic_id:
                level_query = level_query.eq("topic_id", topic_id)
        
        level_result = level_query.execute()
        level_distribution = {}
        if level_result.data:
            for row in level_result.data:
                level = row["level"]
                level_distribution[level] = level_distribution.get(level, 0) + 1
        
        return {
            "total_entries": total_count,
            "level_distribution": level_distribution,
            "topic": topic_name
        }
    
    def delete_vocab_entries(self, topic_name: str = None, category_name: str = None, level: CEFRLevel = None):
        """Delete vocab entries with optional filters"""
        query = self.client.table("vocab_entries").delete()
        
        if topic_name:
            topic_id = self.get_topic_id(topic_name, category_name)
            if topic_id:
                query = query.eq("topic_id", topic_id)
        
        if level:
            query = query.eq("level", level.value)
        
        result = query.execute()
        print(f"Deleted vocab entries: {len(result.data) if result.data else 0}")
        return result.data
    
    def search_vocab_entries(self, search_term: str, topic_name: str = None, 
                           category_name: str = None, limit: int = 50) -> List[Dict[str, Any]]:
        """Search vocab entries by word or definition"""
        query = self.client.table("vocab_entries").select("*")
        
        # Use text search (PostgreSQL full-text search)
        query = query.text_search("word", search_term)
        
        if topic_name:
            topic_id = self.get_topic_id(topic_name, category_name)
            if topic_id:
                query = query.eq("topic_id", topic_id)
        
        query = query.limit(limit).order("created_at", desc=True)
        
        result = query.execute()
        return result.data if result.data else []
    
    def get_all_topics(self) -> List[Dict[str, Any]]:
        """Get all topics with their category information"""
        result = self.client.table("topics").select("*").execute()
        return result.data if result.data else []
    
    def get_topics_by_category(self, category_name: str) -> List[Dict[str, Any]]:
        """Get topics for a specific category"""
        # Since we don't have a categories table, we'll return empty for now
        # This can be enhanced later if needed
        return []
    
    def get_all_categories(self) -> List[Dict[str, Any]]:
        """Get all categories"""
        # Since we don't have a categories table, return empty list
        return [] 