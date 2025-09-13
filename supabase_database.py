from supabase import create_client, Client
from typing import List, Dict, Any, Optional, Tuple
from models import (
    VocabEntry, CEFRLevel, UserVocabList, UserVocabEntry, VocabEntryWithUserData,
    FlashcardSession, FlashcardProgress, FlashcardStats, FlashcardCard, 
    StudyMode, DifficultyRating, SpacedRepetitionSettings, StudyReminder,
    SessionType, FlashcardSessionRequest, FlashcardAnswerRequest, 
    FlashcardAchievement, StudySessionAnalytics
)
import os
from dotenv import load_dotenv
import json
from datetime import datetime, timedelta
import re

load_dotenv(override=True)

class SupabaseVocabDatabase:
    def __init__(self):
        """Initialize Supabase client"""
        self.supabase_url = os.getenv("SUPABASE_URL")
        self.supabase_key = os.getenv("SUPABASE_ANON_KEY")
        
        if not self.supabase_url or not self.supabase_key:
            raise ValueError("SUPABASE_URL and SUPABASE_ANON_KEY must be set in environment variables")
        
        self.client: Client = create_client(self.supabase_url, self.supabase_key)
    
    def _parse_date(self, date_str: str) -> Optional[datetime]:
        """Parse various date formats from Supabase"""
        if not date_str:
            return None
        
        try:
            # Handle different date formats
            if date_str.endswith('Z'):
                return datetime.fromisoformat(date_str.replace('Z', '+00:00'))
            elif '+' in date_str or date_str.count('-') > 2:
                return datetime.fromisoformat(date_str)
            else:
                # Handle format like '2025-09-07T21:29:27.33124' (microseconds without timezone)
                # Remove extra microseconds digits if present
                if '.' in date_str and 'T' in date_str:
                    # Split on the dot and keep only 6 digits for microseconds
                    parts = date_str.split('.')
                    if len(parts) == 2:
                        date_part = parts[0]
                        microsecond_part = parts[1]
                        # Keep only first 6 digits of microseconds
                        if len(microsecond_part) > 6:
                            microsecond_part = microsecond_part[:6]
                        date_str = f"{date_part}.{microsecond_part}"
                
                return datetime.fromisoformat(date_str)
        except ValueError as e:
            print(f"Warning: Could not parse date {date_str}: {e}")
            return None
    
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
        result = self.client.table("categories").select("id").eq("name", category_name).execute()
        return result.data[0]["id"] if result.data else None
    
    def create_topic_if_not_exists(self, topic_name: str, category_name: str = None) -> str:
        """Create a topic if it doesn't exist and return the topic ID"""
        # Check if topic already exists
        existing_topic_id = self.get_topic_id(topic_name, category_name)
        if existing_topic_id:
            return existing_topic_id
        
        # Create new topic
        topic_data = {
            "name": topic_name,
            "created_at": datetime.now().isoformat()
        }
        
        # Add category_id if category_name is provided
        if category_name:
            category_result = self.client.table("categories").select("id").eq("name", category_name).execute()
            if category_result.data:
                topic_data["category_id"] = category_result.data[0]["id"]
            else:
                # Create category if it doesn't exist
                category_data = {
                    "name": category_name,
                    "created_at": datetime.now().isoformat()
                }
                category_result = self.client.table("categories").insert(category_data).execute()
                if category_result.data:
                    topic_data["category_id"] = category_result.data[0]["id"]
        
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
        category_id = self.get_category_id(category_name)
        if not category_id:
            return []
        
        result = self.client.table("topics").select("*").eq("category_id", category_id).execute()
        return result.data if result.data else []
    
    def get_all_categories(self) -> List[Dict[str, Any]]:
        """Get all categories"""
        result = self.client.table("categories").select("*").execute()
        return result.data if result.data else [] 

    # =========== USER VOCABULARY MANAGEMENT ===========
    
    def get_user_vocab_entries_with_pagination(
        self, 
        user_id: str,
        page: int = 1,
        limit: int = 20,
        show_favorites_only: bool = False,
        show_hidden: bool = False,
        topic_name: str = None,
        category_name: str = None,
        level: CEFRLevel = None,
        search_term: str = None
    ) -> Dict[str, Any]:
        """
        Get vocabulary entries with user data, pagination, and filtering
        """
        offset = (page - 1) * limit
        
        # For now, let's get all vocab entries and filter in Python
        # This is a simpler approach until we figure out the proper Supabase join syntax
        query = self.client.table("vocab_entries").select("*")
        
        # Apply basic filters
        if topic_name:
            topic_id = self.get_topic_id(topic_name, category_name)
            if topic_id:
                query = query.eq("topic_id", topic_id)
        
        if level:
            query = query.eq("level", level.value)
        
        if search_term:
            # Search in word, definition, or translation
            query = query.or_(f"word.ilike.%{search_term}%,definition.ilike.%{search_term}%,translation.ilike.%{search_term}%")
        
        if topic_name:
            topic_id = self.get_topic_id(topic_name, category_name)
            if topic_id:
                query = query.eq("topic_id", topic_id)
        
        if level:
            query = query.eq("level", level.value)
        
        if search_term:
            # Search in word, definition, or translation
            query = query.or_(f"word.ilike.%{search_term}%,definition.ilike.%{search_term}%,translation.ilike.%{search_term}%")
        
        # Get total count first
        count_query = query
        count_result = count_query.execute()
        total_count = len(count_result.data) if count_result.data else 0
        
        # Apply pagination
        query = query.range(offset, offset + limit - 1).order("created_at", desc=True)
        
        result = query.execute()
        
        if not result.data:
            return {
                "vocabularies": [],
                "total_count": 0,
                "page": page,
                "limit": limit,
                "has_more": False
            }
        
        # Get user data for these vocab entries
        vocab_ids = [row["id"] for row in result.data]
        user_data_query = self.client.table("user_vocab_entries").select("*").eq("user_id", user_id).in_("vocab_entry_id", vocab_ids)
        user_data_result = user_data_query.execute()
        
        # Create a mapping of vocab_id to user_data
        user_data_map = {}
        if user_data_result.data:
            for user_row in user_data_result.data:
                user_data_map[user_row["vocab_entry_id"]] = user_row
        
        # Transform the data
        vocabularies = []
        for row in result.data:
            user_data = user_data_map.get(row["id"], {})
            
            # Apply user-specific filters
            if show_favorites_only and not user_data.get("is_favorite", False):
                continue
            if not show_hidden and user_data.get("is_hidden", False):
                continue
            
            vocab_entry = VocabEntryWithUserData(
                id=row["id"],
                word=row["word"],
                definition=row["definition"],
                translation=row["translation"],
                example=row["example"],
                example_translation=row["example_translation"],
                level=row["level"],
                part_of_speech=row["part_of_speech"],
                topic_id=row["topic_id"],
                target_language=row["target_language"],
                original_language=row["original_language"],
                created_at=row["created_at"],
                is_favorite=user_data.get("is_favorite", False),
                is_hidden=user_data.get("is_hidden", False),
                hidden_until=user_data.get("hidden_until"),
                personal_notes=user_data.get("personal_notes"),
                difficulty_rating=user_data.get("difficulty_rating"),
                last_reviewed=user_data.get("last_reviewed"),
                review_count=user_data.get("review_count", 0)
            )
            vocabularies.append(vocab_entry)
        
        return {
            "vocabularies": vocabularies,
            "total_count": total_count,
            "page": page,
            "limit": limit,
            "has_more": offset + limit < total_count
        }
    
    def toggle_favorite(self, user_id: str, vocab_entry_id: str) -> bool:
        """Toggle favorite status for a vocabulary entry"""
        try:
            # Check if user vocab entry exists
            existing = self.client.table("user_vocab_entries").select("*").eq("user_id", user_id).eq("vocab_entry_id", vocab_entry_id).execute()
            
            if existing.data:
                # Update existing entry
                current_favorite = existing.data[0]["is_favorite"]
                result = self.client.table("user_vocab_entries").update({
                    "is_favorite": not current_favorite,
                    "updated_at": datetime.now().isoformat()
                }).eq("user_id", user_id).eq("vocab_entry_id", vocab_entry_id).execute()
                
                return not current_favorite
            else:
                # Create new entry as favorite
                result = self.client.table("user_vocab_entries").insert({
                    "user_id": user_id,
                    "vocab_entry_id": vocab_entry_id,
                    "is_favorite": True,
                    "created_at": datetime.now().isoformat(),
                    "updated_at": datetime.now().isoformat()
                }).execute()
                
                return True
                
        except Exception as e:
            print(f"Error toggling favorite: {e}")
            raise
    
    def hide_vocab_entry(self, user_id: str, vocab_entry_id: str, hide_duration_days: int = 7) -> bool:
        """Hide a vocabulary entry for a specified duration"""
        try:
            hidden_until = datetime.now() + timedelta(days=hide_duration_days)
            
            # Check if user vocab entry exists
            existing = self.client.table("user_vocab_entries").select("*").eq("user_id", user_id).eq("vocab_entry_id", vocab_entry_id).execute()
            
            if existing.data:
                # Update existing entry
                result = self.client.table("user_vocab_entries").update({
                    "is_hidden": True,
                    "hidden_until": hidden_until.isoformat(),
                    "updated_at": datetime.now().isoformat()
                }).eq("user_id", user_id).eq("vocab_entry_id", vocab_entry_id).execute()
            else:
                # Create new entry as hidden
                result = self.client.table("user_vocab_entries").insert({
                    "user_id": user_id,
                    "vocab_entry_id": vocab_entry_id,
                    "is_hidden": True,
                    "hidden_until": hidden_until.isoformat(),
                    "created_at": datetime.now().isoformat(),
                    "updated_at": datetime.now().isoformat()
                }).execute()
            
            return True
                
        except Exception as e:
            print(f"Error hiding vocab entry: {e}")
            raise
    
    def unhide_vocab_entry(self, user_id: str, vocab_entry_id: str) -> bool:
        """Unhide a vocabulary entry"""
        try:
            result = self.client.table("user_vocab_entries").update({
                "is_hidden": False,
                "hidden_until": None,
                "updated_at": datetime.now().isoformat()
            }).eq("user_id", user_id).eq("vocab_entry_id", vocab_entry_id).execute()
            
            return True
                
        except Exception as e:
            print(f"Error unhiding vocab entry: {e}")
            raise
    
    def add_personal_note(self, user_id: str, vocab_entry_id: str, note: str) -> bool:
        """Add or update personal notes for a vocabulary entry"""
        try:
            # Check if user vocab entry exists
            existing = self.client.table("user_vocab_entries").select("*").eq("user_id", user_id).eq("vocab_entry_id", vocab_entry_id).execute()
            
            if existing.data:
                # Update existing entry
                result = self.client.table("user_vocab_entries").update({
                    "personal_notes": note,
                    "updated_at": datetime.now().isoformat()
                }).eq("user_id", user_id).eq("vocab_entry_id", vocab_entry_id).execute()
            else:
                # Create new entry with note
                result = self.client.table("user_vocab_entries").insert({
                    "user_id": user_id,
                    "vocab_entry_id": vocab_entry_id,
                    "personal_notes": note,
                    "created_at": datetime.now().isoformat(),
                    "updated_at": datetime.now().isoformat()
                }).execute()
            
            return True
                
        except Exception as e:
            print(f"Error adding personal note: {e}")
            raise
    
    def rate_difficulty(self, user_id: str, vocab_entry_id: str, rating: int) -> bool:
        """Rate the difficulty of a vocabulary entry (1-5 scale)"""
        if not 1 <= rating <= 5:
            raise ValueError("Rating must be between 1 and 5")
        
        try:
            # Check if user vocab entry exists
            existing = self.client.table("user_vocab_entries").select("*").eq("user_id", user_id).eq("vocab_entry_id", vocab_entry_id).execute()
            
            if existing.data:
                # Update existing entry
                result = self.client.table("user_vocab_entries").update({
                    "difficulty_rating": rating,
                    "updated_at": datetime.now().isoformat()
                }).eq("user_id", user_id).eq("vocab_entry_id", vocab_entry_id).execute()
            else:
                # Create new entry with rating
                result = self.client.table("user_vocab_entries").insert({
                    "user_id": user_id,
                    "vocab_entry_id": vocab_entry_id,
                    "difficulty_rating": rating,
                    "created_at": datetime.now().isoformat(),
                    "updated_at": datetime.now().isoformat()
                }).execute()
            
            return True
                
        except Exception as e:
            print(f"Error rating difficulty: {e}")
            raise
    
    def mark_as_reviewed(self, user_id: str, vocab_entry_id: str) -> bool:
        """Mark a vocabulary entry as reviewed"""
        try:
            # Check if user vocab entry exists
            existing = self.client.table("user_vocab_entries").select("*").eq("user_id", user_id).eq("vocab_entry_id", vocab_entry_id).execute()
            
            current_review_count = 0
            if existing.data:
                current_review_count = existing.data[0].get("review_count", 0)
            
            if existing.data:
                # Update existing entry
                result = self.client.table("user_vocab_entries").update({
                    "last_reviewed": datetime.now().isoformat(),
                    "review_count": current_review_count + 1,
                    "updated_at": datetime.now().isoformat()
                }).eq("user_id", user_id).eq("vocab_entry_id", vocab_entry_id).execute()
            else:
                # Create new entry
                result = self.client.table("user_vocab_entries").insert({
                    "user_id": user_id,
                    "vocab_entry_id": vocab_entry_id,
                    "last_reviewed": datetime.now().isoformat(),
                    "review_count": 1,
                    "created_at": datetime.now().isoformat(),
                    "updated_at": datetime.now().isoformat()
                }).execute()
            
            return True
                
        except Exception as e:
            print(f"Error marking as reviewed: {e}")
            raise
    
    def undo_review(self, user_id: str, vocab_entry_id: str) -> bool:
        """Undo review - reset review count to 0"""
        try:
            result = self.client.table("user_vocab_entries").update({
                "last_reviewed": None,
                "review_count": 0,
                "updated_at": datetime.now().isoformat()
            }).eq("user_id", user_id).eq("vocab_entry_id", vocab_entry_id).execute()
            
            return True
                
        except Exception as e:
            print(f"Error undoing review: {e}")
            raise

    # =========== USER VOCABULARY LISTS ===========
    
    def create_user_vocab_list(self, user_id: str, list_name: str, description: str = None, is_public: bool = False) -> str:
        """Create a new user vocabulary list"""
        try:
            data = {
                "user_id": user_id,
                "list_name": list_name,
                "description": description,
                "is_public": is_public,
                "created_at": datetime.now().isoformat(),
                "updated_at": datetime.now().isoformat()
            }
            
            result = self.client.table("user_vocab_lists").insert(data).execute()
            
            if result.data:
                return result.data[0]["id"]
            else:
                raise ValueError("Failed to create user vocab list")
                
        except Exception as e:
            print(f"Error creating user vocab list: {e}")
            raise
    
    def get_user_vocab_lists(self, user_id: str) -> List[Dict[str, Any]]:
        """Get all vocabulary lists for a user"""
        try:
            result = self.client.table("user_vocab_lists").select("*").eq("user_id", user_id).order("created_at", desc=True).execute()
            return result.data if result.data else []
        except Exception as e:
            print(f"Error getting user vocab lists: {e}")
            raise
    
    def add_vocab_to_list(self, list_id: str, vocab_entry_id: str) -> bool:
        """Add a vocabulary entry to a user's list"""
        try:
            data = {
                "list_id": list_id,
                "vocab_entry_id": vocab_entry_id,
                "added_at": datetime.now().isoformat()
            }
            
            result = self.client.table("user_vocab_list_items").insert(data).execute()
            return bool(result.data)
                
        except Exception as e:
            print(f"Error adding vocab to list: {e}")
            raise
    
    def remove_vocab_from_list(self, list_id: str, vocab_entry_id: str) -> bool:
        """Remove a vocabulary entry from a user's list"""
        try:
            result = self.client.table("user_vocab_list_items").delete().eq("list_id", list_id).eq("vocab_entry_id", vocab_entry_id).execute()
            return True
        except Exception as e:
            print(f"Error removing vocab from list: {e}")
            raise 

    # =========== USER PERSONAL VOCABULARY MANAGEMENT ===========
    
    def save_vocab_to_user(self, user_id: str, vocab_entry, topic_name: str = None, 
                          category_name: str = None, target_language: str = "English", 
                          original_language: str = "Vietnamese") -> str:
        """Save a vocabulary entry to the user's personal vocabulary"""
        try:
            # First, ensure the user exists in profiles table
            try:
                self.client.table("profiles").select("id").eq("id", user_id).execute()
            except:
                # Create minimal user record if doesn't exist
                self.client.table("profiles").insert({
                    "id": user_id,
                    "email": f"test-{user_id}@example.com",
                    "created_at": datetime.now().isoformat(),
                    "updated_at": datetime.now().isoformat()
                }).execute()
            
            # Get or create topic ID if topic name is provided
            topic_id = None
            if topic_name:
                try:
                    topic_id = self.create_topic_if_not_exists(topic_name, category_name)
                except Exception as e:
                    print(f"Error with topic '{topic_name}': {e}")
                    topic_id = None
            
            # Check if this vocabulary entry already exists for this user
            existing_user_vocab = self.client.table("user_vocab_entries").select("*").eq("user_id", user_id).execute()
            
            # Check if the word already exists in vocab_entries (more comprehensive check)
            existing_vocab = self.client.table("vocab_entries").select("*").eq("word", vocab_entry.word).eq("level", vocab_entry.level.value).eq("definition", vocab_entry.definition).execute()
            
            vocab_entry_id = None
            
            if existing_vocab.data:
                # Use existing vocab entry
                vocab_entry_id = existing_vocab.data[0]["id"]
                print(f"Using existing vocab entry for '{vocab_entry.word}'")
            else:
                # Prepare data for vocab_entries table
                vocab_data = {
                    "word": vocab_entry.word,
                    "definition": vocab_entry.definition,
                    "translation": vocab_entry.translation,
                    "example": vocab_entry.example,
                    "example_translation": vocab_entry.example_translation,
                    "level": vocab_entry.level.value,
                    "part_of_speech": vocab_entry.part_of_speech.value if vocab_entry.part_of_speech else None,
                    "topic_id": topic_id,
                    "target_language": target_language,
                    "original_language": original_language
                }
                
                # Insert into vocab_entries table
                vocab_result = self.client.table("vocab_entries").insert(vocab_data).execute()
                
                if not vocab_result.data:
                    raise ValueError("Failed to insert vocabulary entry")
                
                vocab_entry_id = vocab_result.data[0]["id"]
                print(f"Created new vocab entry for '{vocab_entry.word}'")
            
            # Check if user already has this vocab entry
            existing_user_entry = None
            if existing_user_vocab.data:
                for entry in existing_user_vocab.data:
                    if entry["vocab_entry_id"] == vocab_entry_id:
                        existing_user_entry = entry
                        break
            
            if existing_user_entry:
                print(f"User {user_id} already has vocabulary '{vocab_entry.word}'")
                return vocab_entry_id
            
            # Create user relationship in user_vocab_entries table
            user_vocab_data = {
                "user_id": user_id,
                "vocab_entry_id": vocab_entry_id,
                "is_favorite": False,
                "is_hidden": False,
                "created_at": datetime.now().isoformat(),
                "updated_at": datetime.now().isoformat()
            }
            
            user_result = self.client.table("user_vocab_entries").insert(user_vocab_data).execute()
            
            if not user_result.data:
                raise ValueError("Failed to create user vocabulary relationship")
            
            print(f"Saved vocabulary '{vocab_entry.word}' to user {user_id}")
            return vocab_entry_id
            
        except Exception as e:
            print(f"Error saving vocab to user: {e}")
            raise
    
    def get_user_saved_vocab_entries(self, user_id: str, show_hidden: bool = False) -> List[Dict[str, Any]]:
        """Get all vocabulary entries saved by a user"""
        try:
            # First get user's vocab entry relationships
            user_vocab_query = self.client.table("user_vocab_entries").select("*").eq("user_id", user_id)
            
            # Apply hidden filter if not showing hidden items
            if not show_hidden:
                # Filter out hidden items that haven't expired yet
                current_time = datetime.now().isoformat()
                user_vocab_query = user_vocab_query.or_(
                    f"is_hidden.eq.false,hidden_until.lt.{current_time}"
                )
            
            user_vocab_result = user_vocab_query.execute()
            
            if not user_vocab_result.data:
                return []
            
            # Get the vocab entry IDs
            vocab_entry_ids = [row["vocab_entry_id"] for row in user_vocab_result.data]
            
            # Get the actual vocabulary entries
            vocab_result = self.client.table("vocab_entries").select("*").in_("id", vocab_entry_ids).execute()
            
            if not vocab_result.data:
                return []
            
            # Create a mapping of vocab_id to vocab_data
            vocab_map = {row["id"]: row for row in vocab_result.data}
            
            # Combine user data with vocab data
            vocabularies = []
            for user_row in user_vocab_result.data:
                vocab_id = user_row["vocab_entry_id"]
                if vocab_id in vocab_map:
                    vocab_data = vocab_map[vocab_id]
                    user_data = {
                        "vocab_entry_id": user_row["vocab_entry_id"],
                        "is_favorite": user_row["is_favorite"],
                        "is_hidden": user_row["is_hidden"],
                        "hidden_until": user_row["hidden_until"],
                        "personal_notes": user_row["personal_notes"],
                        "difficulty_rating": user_row["difficulty_rating"],
                        "last_reviewed": user_row["last_reviewed"],
                        "review_count": user_row["review_count"],
                        "saved_at": user_row["created_at"]
                    }
                    
                    # Combine vocab data with user data
                    combined_data = {**vocab_data, **user_data}
                    vocabularies.append(combined_data)
            
            return vocabularies
            
        except Exception as e:
            print(f"Error getting user saved vocab entries: {e}")
            raise

    # =========== ADVANCED FLASHCARD SYSTEM ===========
    
    def create_flashcard_session(self, user_id: str, request: FlashcardSessionRequest) -> str:
        """Create a new flashcard study session with advanced features"""
        try:
            # Get vocabulary cards for the session
            cards = self._get_flashcard_cards_advanced(
                user_id=user_id,
                topic_name=request.topic_name,
                category_name=request.category_name,
                level=request.level,
                max_cards=request.max_cards,
                include_reviewed=request.include_reviewed,
                include_favorites=request.include_favorites,
                difficulty_filter=request.difficulty_filter,
                smart_selection=request.smart_selection
            )
            
            if not cards:
                raise ValueError("No vocabulary cards available for this session")
            
            # Create session
            session_data = {
                "user_id": user_id,
                "session_name": request.session_name,
                "session_type": request.session_type.value,
                "study_mode": request.study_mode.value,
                "topic_name": request.topic_name,
                "category_name": request.category_name,
                "level": request.level.value if request.level else None,
                "max_cards": request.max_cards,
                "time_limit_minutes": request.time_limit_minutes,
                "total_cards": len(cards),
                "current_card_index": 0,
                "correct_answers": 0,
                "incorrect_answers": 0,
                "skipped_cards": 0,
                "hints_used": 0,
                "total_time_seconds": 0,
                "is_active": True,
                "created_at": datetime.now().isoformat(),
                "started_at": datetime.now().isoformat()
            }
            
            result = self.client.table("flashcard_sessions").insert(session_data).execute()
            
            if not result.data:
                raise ValueError("Failed to create flashcard session")
            
            session_id = result.data[0]["id"]
            
            # Create progress entries for each card
            progress_entries = []
            for i, card in enumerate(cards):
                progress_entry = {
                    "user_id": user_id,
                    "vocab_entry_id": card["vocab_entry_id"],
                    "session_id": session_id,
                    "card_index": i,
                    "correct_answer": self._get_correct_answer_for_mode(card, request.study_mode),
                    "created_at": datetime.now().isoformat()
                }
                progress_entries.append(progress_entry)
            
            if progress_entries:
                progress_result = self.client.table("flashcard_progress").insert(progress_entries).execute()
                if not progress_result.data:
                    print(f"Warning: Failed to create progress entries for session {session_id}")
                else:
                    print(f"Created {len(progress_result.data)} progress entries for session {session_id}")
            
            print(f"Created advanced flashcard session '{request.session_name}' with {len(cards)} cards")
            return session_id
            
        except Exception as e:
            print(f"Error creating flashcard session: {e}")
            raise
    
    def create_test_flashcard_session(self, user_id: str, request: FlashcardSessionRequest) -> str:
        """Create a test flashcard session that works with existing vocabulary entries"""
        try:
            # Get vocabulary cards using AI curation for more interesting sessions
            cards = self._get_ai_curated_flashcard_cards(
                topic_name=request.topic_name,
                category_name=request.category_name,
                level=request.level,
                max_cards=request.max_cards
            )
            
            if not cards:
                raise ValueError("No vocabulary cards available for this test session")
            
            # Create session
            session_data = {
                "user_id": user_id,
                "session_name": request.session_name,
                "session_type": request.session_type.value,
                "study_mode": request.study_mode.value,
                "topic_name": request.topic_name,
                "category_name": request.category_name,
                "level": request.level.value if request.level else None,
                "max_cards": request.max_cards,
                "time_limit_minutes": request.time_limit_minutes,
                "total_cards": len(cards),
                "current_card_index": 0,
                "correct_answers": 0,
                "incorrect_answers": 0,
                "skipped_cards": 0,
                "hints_used": 0,
                "total_time_seconds": 0,
                "is_active": True,
                "created_at": datetime.now().isoformat(),
                "started_at": datetime.now().isoformat()
            }
            
            result = self.client.table("flashcard_sessions").insert(session_data).execute()
            
            if not result.data:
                raise ValueError("Failed to create test flashcard session")
            
            session_id = result.data[0]["id"]
            
            # Create progress entries for each card
            progress_entries = []
            for i, card in enumerate(cards):
                progress_entry = {
                    "user_id": user_id,
                    "vocab_entry_id": card["vocab_entry_id"],
                    "session_id": session_id,
                    "card_index": i,
                    "correct_answer": self._get_correct_answer_for_mode(card, request.study_mode),
                    "created_at": datetime.now().isoformat()
                }
                progress_entries.append(progress_entry)
            
            if progress_entries:
                progress_result = self.client.table("flashcard_progress").insert(progress_entries).execute()
                if not progress_result.data:
                    print(f"Warning: Failed to create progress entries for test session {session_id}")
                else:
                    print(f"Created {len(progress_result.data)} progress entries for test session {session_id}")
            
            print(f"Created test flashcard session '{request.session_name}' with {len(cards)} cards")
            return session_id
            
        except Exception as e:
            print(f"Error creating test flashcard session: {e}")
            raise
    
    def _get_flashcard_cards_advanced(self, user_id: str, topic_name: str = None, 
                                    category_name: str = None, level: CEFRLevel = None,
                                    max_cards: int = 20, include_reviewed: bool = False,
                                    include_favorites: bool = False,
                                    difficulty_filter: List[DifficultyRating] = None,
                                    smart_selection: bool = True) -> List[Dict[str, Any]]:
        """Get vocabulary cards for flashcard session with advanced selection"""
        try:
            # Get user's vocabulary entries with filters
            query = self.client.table("vocab_entries").select("""
                id, word, definition, translation, example, example_translation,
                level, part_of_speech, topic_id, target_language, original_language
            """)
            
            # Apply filters
            if topic_name:
                topic_id = self.get_topic_id(topic_name, category_name)
                if topic_id:
                    query = query.eq("topic_id", topic_id)
            
            if level:
                query = query.eq("level", level.value)
            
            # Get user's saved vocabulary with advanced filtering
            user_vocab_query = self.client.table("user_vocab_entries").select("*").eq("user_id", user_id)
            
            # Apply user-specific filters
            if not include_reviewed:
                # Only include cards that haven't been reviewed recently or have low review count
                user_vocab_query = user_vocab_query.or_("review_count.lt.3,last_reviewed.is.null")
            
            if include_favorites:
                user_vocab_query = user_vocab_query.eq("is_favorite", True)
            
            user_vocab_result = user_vocab_query.execute()
            
            if not user_vocab_result.data:
                # FALLBACK: If user has no saved vocabulary, use AI-curated vocabulary pool
                print(f"User {user_id} has no saved vocabulary. Using AI-curated vocabulary pool.")
                return self._get_ai_curated_flashcard_cards(
                    topic_name=topic_name,
                    category_name=category_name,
                    level=level,
                    max_cards=max_cards
                )
            
            # Get vocab entry IDs
            vocab_ids = [row["vocab_entry_id"] for row in user_vocab_result.data]
            query = query.in_("id", vocab_ids)
            
            result = query.limit(max_cards * 2).execute()  # Get more for smart selection
            
            if not result.data:
                return []
            
            # Combine with user data
            user_data_map = {row["vocab_entry_id"]: row for row in user_vocab_result.data}
            
            cards = []
            seen_words = set()  # Track unique words to avoid duplicates
            
            for vocab_row in result.data:
                # Skip if we've already seen this word (case-insensitive)
                word_lower = vocab_row["word"].lower()
                if word_lower in seen_words:
                    continue
                seen_words.add(word_lower)
                
                user_data = user_data_map.get(vocab_row["id"], {})
                card = {
                    "vocab_entry_id": vocab_row["id"],
                    "word": vocab_row["word"],
                    "definition": vocab_row["definition"],
                    "translation": vocab_row["translation"],
                    "example": vocab_row["example"],
                    "example_translation": vocab_row["example_translation"],
                    "part_of_speech": vocab_row["part_of_speech"],
                    "level": vocab_row["level"],
                    "topic_name": topic_name,
                    "is_favorite": user_data.get("is_favorite", False),
                    "review_count": user_data.get("review_count", 0),
                    "last_reviewed": user_data.get("last_reviewed"),
                    "difficulty_rating": user_data.get("difficulty_rating"),
                    "personal_notes": user_data.get("personal_notes"),
                    "mastery_level": self._calculate_mastery_level(user_data),
                    "next_review_date": self._calculate_next_review_date(user_data)
                }
                cards.append(card)
            
            # Apply smart selection if enabled
            if smart_selection:
                cards = self._apply_smart_selection(cards, max_cards)
            else:
                cards = cards[:max_cards]
            
            return cards
            
        except Exception as e:
            print(f"Error getting flashcard cards: {e}")
            raise
    
    def _calculate_mastery_level(self, user_data: Dict[str, Any]) -> float:
        """Calculate mastery level based on user performance"""
        review_count = user_data.get("review_count", 0)
        difficulty_rating = user_data.get("difficulty_rating", 3)
        
        if review_count == 0:
            return 0.0
        
        # Simple mastery calculation
        base_mastery = min(1.0, review_count * 0.2)
        
        # Handle None difficulty_rating
        if difficulty_rating is None:
            difficulty_rating = 3  # Default to medium difficulty
        
        difficulty_factor = (6 - difficulty_rating) / 5  # Lower difficulty = higher mastery
        
        return min(1.0, base_mastery * difficulty_factor)
    
    def _calculate_next_review_date(self, user_data: Dict[str, Any]) -> Optional[datetime]:
        """Calculate next review date based on spaced repetition"""
        last_reviewed = user_data.get("last_reviewed")
        review_count = user_data.get("review_count", 0)
        
        if not last_reviewed or review_count == 0:
            from datetime import timezone
            return datetime.now(timezone.utc)
        
        # Simple spaced repetition calculation
        if review_count == 1:
            interval = 1  # 1 day
        elif review_count == 2:
            interval = 3  # 3 days
        elif review_count == 3:
            interval = 7  # 1 week
        else:
            interval = 14  # 2 weeks
        
        # Handle different datetime formats
        try:
            if last_reviewed.endswith('Z'):
                last_review = datetime.fromisoformat(last_reviewed.replace('Z', '+00:00'))
            elif '+' in last_reviewed or last_reviewed.count('-') > 2:
                # Already has timezone info
                last_review = datetime.fromisoformat(last_reviewed)
            else:
                # No timezone info, assume UTC
                last_review = datetime.fromisoformat(last_reviewed + '+00:00')
        except ValueError:
            # Fallback: try parsing without microseconds
            try:
                last_review = datetime.fromisoformat(last_reviewed.split('.')[0] + '+00:00')
            except ValueError:
                # Final fallback: use current time
                from datetime import timezone
                last_review = datetime.now(timezone.utc)
        
        return last_review + timedelta(days=interval)
    
    def _apply_smart_selection(self, cards: List[Dict[str, Any]], max_cards: int) -> List[Dict[str, Any]]:
        """Apply smart selection algorithm to choose optimal cards"""
        from datetime import timezone
        now = datetime.now(timezone.utc)
        
        # Categorize cards
        overdue_cards = []
        new_cards = []
        review_cards = []
        mastered_cards = []
        
        for card in cards:
            if card["review_count"] == 0:
                new_cards.append(card)
            elif card["next_review_date"]:
                # Ensure both datetimes are timezone-aware for comparison
                next_review = card["next_review_date"]
                if next_review.tzinfo is None:
                    # Make timezone-naive datetime timezone-aware (assume UTC)
                    next_review = next_review.replace(tzinfo=timezone.utc)
                if next_review <= now:
                    overdue_cards.append(card)
                elif card["mastery_level"] >= 0.8:
                    mastered_cards.append(card)
                else:
                    review_cards.append(card)
            elif card["mastery_level"] >= 0.8:
                mastered_cards.append(card)
            else:
                review_cards.append(card)
        
        # Smart selection: prioritize overdue, then new, then review, then mastered
        selected = []
        
        # 40% overdue cards
        overdue_count = min(len(overdue_cards), int(max_cards * 0.4))
        selected.extend(overdue_cards[:overdue_count])
        
        # 30% new cards
        new_count = min(len(new_cards), int(max_cards * 0.3))
        selected.extend(new_cards[:new_count])
        
        # 20% review cards
        review_count = min(len(review_cards), int(max_cards * 0.2))
        selected.extend(review_cards[:review_count])
        
        # 10% mastered cards
        mastered_count = min(len(mastered_cards), max_cards - len(selected))
        selected.extend(mastered_cards[:mastered_count])
        
        # Fill remaining slots with any available cards
        remaining = max_cards - len(selected)
        if remaining > 0:
            all_cards = overdue_cards + new_cards + review_cards + mastered_cards
            for card in all_cards:
                if card not in selected and len(selected) < max_cards:
                    selected.append(card)
        
        return selected[:max_cards]
    
    def _get_global_flashcard_cards(self, topic_name: str = None, category_name: str = None,
                                   level: CEFRLevel = None, max_cards: int = 20) -> List[Dict[str, Any]]:
        """Get vocabulary cards from global vocabulary pool (for users with no saved vocabulary)"""
        try:
            # Get vocabulary entries directly from vocab_entries table
            query = self.client.table("vocab_entries").select("""
                id, word, definition, translation, example, example_translation,
                level, part_of_speech, topic_id, target_language, original_language
            """)
            
            # Apply filters
            if topic_name:
                topic_id = self.get_topic_id(topic_name, category_name)
                if topic_id:
                    query = query.eq("topic_id", topic_id)
            
            if level:
                query = query.eq("level", level.value)
            
            # Get more entries than needed for random selection
            result = query.limit(max_cards * 3).execute()
            
            if not result.data:
                return []
            
            # Randomly shuffle and select cards for variety
            import random
            random.shuffle(result.data)
            selected_data = result.data[:max_cards]
            
            # Convert to card format
            cards = []
            for vocab_row in selected_data:
                card = {
                    "vocab_entry_id": vocab_row["id"],
                    "word": vocab_row["word"],
                    "definition": vocab_row["definition"],
                    "translation": vocab_row["translation"],
                    "example": vocab_row["example"],
                    "example_translation": vocab_row["example_translation"],
                    "part_of_speech": vocab_row["part_of_speech"],
                    "level": vocab_row["level"],
                    "topic_name": topic_name,
                    "is_favorite": False,
                    "review_count": 0,
                    "last_reviewed": None,
                    "difficulty_rating": None,
                    "personal_notes": None,
                    "mastery_level": 0.0,
                    "next_review_date": datetime.now()
                }
                cards.append(card)
            
            return cards
            
        except Exception as e:
            print(f"Error getting global flashcard cards: {e}")
            raise

    def _get_test_flashcard_cards(self, topic_name: str = None, category_name: str = None,
                                 level: CEFRLevel = None, max_cards: int = 20) -> List[Dict[str, Any]]:
        """Get vocabulary cards directly from vocab_entries table for testing"""
        try:
            # Get vocabulary entries directly from vocab_entries table
            query = self.client.table("vocab_entries").select("""
                id, word, definition, translation, example, example_translation,
                level, part_of_speech, topic_id, target_language, original_language
            """)
            
            # Apply filters
            if topic_name:
                topic_id = self.get_topic_id(topic_name, category_name)
                if topic_id:
                    query = query.eq("topic_id", topic_id)
            
            if level:
                query = query.eq("level", level.value)
            
            # Get more entries than needed for random selection
            result = query.limit(max_cards * 3).execute()
            
            if not result.data:
                return []
            
            # Randomly shuffle and select cards for variety
            import random
            random.shuffle(result.data)
            selected_data = result.data[:max_cards]
            
            # Convert to card format
            cards = []
            for vocab_row in selected_data:
                card = {
                    "vocab_entry_id": vocab_row["id"],
                    "word": vocab_row["word"],
                    "definition": vocab_row["definition"],
                    "translation": vocab_row["translation"],
                    "example": vocab_row["example"],
                    "example_translation": vocab_row["example_translation"],
                    "part_of_speech": vocab_row["part_of_speech"],
                    "level": vocab_row["level"],
                    "topic_name": topic_name,
                    "is_favorite": False,
                    "review_count": 0,
                    "last_reviewed": None,
                    "difficulty_rating": None,
                    "personal_notes": None,
                    "mastery_level": 0.0,
                    "next_review_date": datetime.now()
                }
                cards.append(card)
            
            return cards
            
        except Exception as e:
            print(f"Error getting test flashcard cards: {e}")
            raise
    
    def _get_ai_curated_flashcard_cards(self, topic_name: str = None, category_name: str = None,
                                       level: CEFRLevel = None, max_cards: int = 20, 
                                       use_ai_curation: bool = True) -> List[Dict[str, Any]]:
        """Get AI-curated vocabulary cards for more interesting and diverse sessions"""
        try:
            # First get a larger pool of vocabulary
            query = self.client.table("vocab_entries").select("""
                id, word, definition, translation, example, example_translation,
                level, part_of_speech, topic_id, target_language, original_language
            """)
            
            # Apply filters
            if topic_name:
                topic_id = self.get_topic_id(topic_name, category_name)
                if topic_id:
                    query = query.eq("topic_id", topic_id)
            
            if level:
                query = query.eq("level", level.value)
            
            # Get a larger pool for AI curation
            result = query.limit(max_cards * 5).execute()
            
            if not result.data or len(result.data) < max_cards:
                # Fallback to random selection if not enough data
                return self._get_global_flashcard_cards(topic_name, category_name, level, max_cards)
            
            # Skip AI curation if requested (for faster random selection)
            if not use_ai_curation:
                import random
                random.shuffle(result.data)
                selected_data = result.data[:max_cards]
                
                cards = []
                for vocab_row in selected_data:
                    card = {
                        "vocab_entry_id": vocab_row["id"],
                        "word": vocab_row["word"],
                        "definition": vocab_row["definition"],
                        "translation": vocab_row["translation"],
                        "example": vocab_row["example"],
                        "example_translation": vocab_row["example_translation"],
                        "part_of_speech": vocab_row["part_of_speech"],
                        "level": vocab_row["level"],
                        "topic_name": topic_name,
                        "is_favorite": False,
                        "review_count": 0,
                        "last_reviewed": None,
                        "difficulty_rating": None,
                        "personal_notes": None,
                        "mastery_level": 0.0,
                        "next_review_date": datetime.now()
                    }
                    cards.append(card)
                
                return cards
            
            # Use AI to curate an interesting mix (with timeout fallback)
            try:
                from semantic_validator import semantic_validator
                import time
                
                # Create a prompt for AI curation
                vocab_list = []
                for vocab_row in result.data:
                    vocab_list.append(f"- {vocab_row['word']} ({vocab_row['part_of_speech']}): {vocab_row['definition']}")
                
                # Add randomness to the prompt to get different selections
                import random
                random.shuffle(vocab_list)  # Shuffle the vocabulary list first
                
                # Create different prompts for variety
                prompt_variations = [
                    "Create an engaging mix of practical and interesting vocabulary",
                    "Focus on commonly used words that are essential for daily communication", 
                    "Select vocabulary that builds confidence and encourages learning",
                    "Choose words that are memorable and fun to learn",
                    "Pick vocabulary that covers different aspects of the topic"
                ]
                
                selected_prompt_style = random.choice(prompt_variations)
                
                curation_prompt = f"""You are an expert language teacher curating a diverse and engaging vocabulary session.

Available vocabulary for {topic_name or 'general topics'} (CEFR level {level.value if level else 'mixed'}):
{chr(10).join(vocab_list[:50])}  # Limit to first 50 for prompt length

{selected_prompt_style}. Please select {max_cards} vocabulary items that would create the most interesting and educational flashcard session. Consider:

1. **Diversity**: Mix of parts of speech (nouns, verbs, adjectives, etc.)
2. **Difficulty variety**: Include both easier and more challenging words
3. **Practical relevance**: Words that are useful and commonly used
4. **Learning progression**: Words that build upon each other
5. **Engagement**: Interesting and memorable vocabulary

Return ONLY the words you select, one per line, in this exact format:
word1
word2
word3
...

Do not include any other text or explanations."""

                # Get AI curation
                ai_response = semantic_validator.llm.invoke(curation_prompt)
                selected_words = [word.strip() for word in ai_response.content.strip().split('\n') if word.strip()]
                
                # Filter the original data to only include AI-selected words
                selected_cards = []
                for vocab_row in result.data:
                    if vocab_row['word'] in selected_words and len(selected_cards) < max_cards:
                        card = {
                            "vocab_entry_id": vocab_row["id"],
                            "word": vocab_row["word"],
                            "definition": vocab_row["definition"],
                            "translation": vocab_row["translation"],
                            "example": vocab_row["example"],
                            "example_translation": vocab_row["example_translation"],
                            "part_of_speech": vocab_row["part_of_speech"],
                            "level": vocab_row["level"],
                            "topic_name": topic_name,
                            "is_favorite": False,
                            "review_count": 0,
                            "last_reviewed": None,
                            "difficulty_rating": None,
                            "personal_notes": None,
                            "mastery_level": 0.0,
                            "next_review_date": datetime.now()
                        }
                        selected_cards.append(card)
                
                # If AI didn't select enough, fill with random selection
                if len(selected_cards) < max_cards:
                    remaining_needed = max_cards - len(selected_cards)
                    remaining_cards = [vocab_row for vocab_row in result.data 
                                     if vocab_row['word'] not in selected_words]
                    import random
                    random.shuffle(remaining_cards)
                    
                    for vocab_row in remaining_cards[:remaining_needed]:
                        card = {
                            "vocab_entry_id": vocab_row["id"],
                            "word": vocab_row["word"],
                            "definition": vocab_row["definition"],
                            "translation": vocab_row["translation"],
                            "example": vocab_row["example"],
                            "example_translation": vocab_row["example_translation"],
                            "part_of_speech": vocab_row["part_of_speech"],
                            "level": vocab_row["level"],
                            "topic_name": topic_name,
                            "is_favorite": False,
                            "review_count": 0,
                            "last_reviewed": None,
                            "difficulty_rating": None,
                            "personal_notes": None,
                            "mastery_level": 0.0,
                            "next_review_date": datetime.now()
                        }
                        selected_cards.append(card)
                
                return selected_cards[:max_cards]
                
            except Exception as ai_error:
                print(f"AI curation failed, falling back to random selection: {ai_error}")
                # Fallback to random selection
                import random
                random.shuffle(result.data)
                selected_data = result.data[:max_cards]
                
                cards = []
                for vocab_row in selected_data:
                    card = {
                        "vocab_entry_id": vocab_row["id"],
                        "word": vocab_row["word"],
                        "definition": vocab_row["definition"],
                        "translation": vocab_row["translation"],
                        "example": vocab_row["example"],
                        "example_translation": vocab_row["example_translation"],
                        "part_of_speech": vocab_row["part_of_speech"],
                        "level": vocab_row["level"],
                        "topic_name": topic_name,
                        "is_favorite": False,
                        "review_count": 0,
                        "last_reviewed": None,
                        "difficulty_rating": None,
                        "personal_notes": None,
                        "mastery_level": 0.0,
                        "next_review_date": datetime.now()
                    }
                    cards.append(card)
                
                return cards
            
        except Exception as e:
            print(f"Error getting AI-curated flashcard cards: {e}")
            # Final fallback to basic method
            return self._get_global_flashcard_cards(topic_name, category_name, level, max_cards)
    
    def _get_correct_answer_for_mode(self, card: Dict[str, Any], study_mode: StudyMode) -> str:
        """Get correct answer based on study mode"""
        if study_mode == StudyMode.REVIEW:
            return card["word"]
        elif study_mode == StudyMode.PRACTICE:
            return card["definition"]

        # Will implement later
        elif study_mode == StudyMode.WRITE:
            return card["word"]
        elif study_mode == StudyMode.SPELLING:
            return card["word"]
        elif study_mode == StudyMode.LISTEN:
            return card["word"]
        else:  # Default to word
            return card["word"]
    
    def _validate_answer(self, user_answer: str, correct_answer: str, study_mode: str, 
                        word: str = None, context: str = None) -> Tuple[bool, float, str]:
        """
        AI-powered intelligent answer validation that handles different ways of expressing the same meaning
        
        Returns:
            Tuple of (is_correct, confidence_score, reasoning)
        """
        if not user_answer or not correct_answer:
            return False, 0.0, "Empty answer provided"
        
        user_answer = user_answer.strip()
        correct_answer = correct_answer.strip()
        
        # Use AI-powered semantic validation as the ONLY method
        try:
            from semantic_validator import semantic_validator
            
            # Determine question type based on study mode
            if study_mode in ["review", "write", "spelling", "listen"]:
                question_type = "word"
            elif study_mode == "practice":
                question_type = "definition"
            else:
                question_type = "general"
            
            # Use AI-powered semantic validation
            result = semantic_validator.validate_answer(
                user_answer=user_answer,
                correct_answer=correct_answer,
                question_type=question_type,
                study_mode=study_mode,
                word=word,
                context=context
            )
            
            # Return enhanced feedback including encouragement and learning tips
            enhanced_reasoning = result.reasoning
            if result.feedback:
                enhanced_reasoning += f"\n\n💡 Learning Tip: {result.feedback}"
            if result.encouragement:
                enhanced_reasoning += f"\n\n🌟 {result.encouragement}"
            
            return result.is_correct, result.confidence_score, enhanced_reasoning
            
        except ImportError as e:
            print(f"Error: Semantic validator not available: {e}")
            raise ValueError(f"AI validation is required but not available: {e}")
        except Exception as e:
            print(f"Error in AI validation: {e}")
            raise ValueError(f"AI validation failed: {e}")
    
    def _validate_answer_basic(self, user_answer: str, correct_answer: str, study_mode: str) -> bool:
        """Basic fallback validation when AI is not available"""
        if not user_answer or not correct_answer:
            return False
        
        user_answer = user_answer.strip()
        correct_answer = correct_answer.strip()
        
        # For word-based answers (REVIEW, WRITE, SPELLING, LISTEN modes)
        if study_mode in ["review", "write", "spelling", "listen"]:
            return self._validate_word_answer(user_answer, correct_answer)
        
        # For definition-based answers (PRACTICE mode)
        elif study_mode == "practice":
            return self._validate_definition_answer(user_answer, correct_answer)
        
        # For other modes, use word validation as default
        else:
            return self._validate_word_answer(user_answer, correct_answer)
    
    def _validate_word_answer(self, user_answer: str, correct_answer: str) -> bool:
        """Validate word-based answers with fuzzy matching"""
        if not user_answer or not correct_answer:
            return False
            
        user_lower = user_answer.lower().strip()
        correct_lower = correct_answer.lower().strip()
        
        # Exact match (case-insensitive)
        if user_lower == correct_lower:
            return True
        
        # Remove common punctuation and extra spaces
        import re
        user_clean = re.sub(r'[^\w\s]', '', user_lower).strip()
        correct_clean = re.sub(r'[^\w\s]', '', correct_lower).strip()
        
        # Check exact match after cleaning
        if user_clean == correct_clean:
            return True
        
        # More lenient fuzzy matching for typos (lowered threshold)
        if self._fuzzy_match(user_clean, correct_clean, threshold=0.7):
            return True
        
        # Check for common variations (plurals, verb forms, etc.)
        if self._check_word_variations(user_clean, correct_clean):
            return True
        
        # Additional check: if the cleaned answers are very similar (just minor differences)
        if len(user_clean) > 0 and len(correct_clean) > 0:
            # Check if one is contained in the other (for compound words or phrases)
            if user_clean in correct_clean or correct_clean in user_clean:
                return True
        
        return False
    
    def _validate_definition_answer(self, user_answer: str, correct_answer: str) -> bool:
        """Validate definition-based answers using semantic similarity"""
        if not user_answer or not correct_answer:
            return False
            
        user_lower = user_answer.lower().strip()
        correct_lower = correct_answer.lower().strip()
        
        # Exact match (case-insensitive)
        if user_lower == correct_lower:
            return True
        
        # Remove common punctuation and extra spaces
        import re
        user_clean = re.sub(r'[^\w\s]', ' ', user_lower).strip()
        correct_clean = re.sub(r'[^\w\s]', ' ', correct_lower).strip()
        
        # Normalize whitespace
        user_clean = re.sub(r'\s+', ' ', user_clean)
        correct_clean = re.sub(r'\s+', ' ', correct_clean)
        
        # Check exact match after cleaning
        if user_clean == correct_clean:
            return True
        
        # Keyword-based matching - check if key concepts are present
        if self._check_keyword_similarity(user_clean, correct_clean):
            return True
        
        # Semantic similarity using word overlap
        if self._check_semantic_similarity(user_clean, correct_clean):
            return True
        
        # Check for paraphrases and synonyms
        if self._check_paraphrase_similarity(user_clean, correct_clean):
            return True
        
        return False
    
    def _fuzzy_match(self, str1: str, str2: str, threshold: float = 0.8) -> bool:
        """Improved fuzzy string matching using character similarity"""
        if not str1 or not str2:
            return False
        
        # Simple character-based similarity
        max_len = max(len(str1), len(str2))
        if max_len == 0:
            return True
        
        # Count matching characters in order
        matches = 0
        min_len = min(len(str1), len(str2))
        
        for i in range(min_len):
            if str1[i] == str2[i]:
                matches += 1
        
        # Also check for transpositions (swapped characters)
        transpositions = 0
        for i in range(min_len - 1):
            if (str1[i] == str2[i+1] and str1[i+1] == str2[i] and 
                str1[i] != str2[i] and str1[i+1] != str2[i+1]):
                transpositions += 1
        
        # Boost score for transpositions (common typing errors)
        similarity = (matches + transpositions * 0.5) / max_len
        return similarity >= threshold
    
    def _check_word_variations(self, user_word: str, correct_word: str) -> bool:
        """Check for common word variations (plurals, verb forms, etc.)"""
        # Simple plural/singular variations
        if user_word.endswith('s') and not correct_word.endswith('s'):
            if user_word[:-1] == correct_word:
                return True
        elif correct_word.endswith('s') and not user_word.endswith('s'):
            if correct_word[:-1] == user_word:
                return True
        
        # Common verb variations (simple cases)
        verb_endings = ['ed', 'ing', 'er', 'est']
        for ending in verb_endings:
            if user_word.endswith(ending) and not correct_word.endswith(ending):
                if user_word[:-len(ending)] == correct_word:
                    return True
            elif correct_word.endswith(ending) and not user_word.endswith(ending):
                if correct_word[:-len(ending)] == user_word:
                    return True
        
        return False
    
    def _check_keyword_similarity(self, user_text: str, correct_text: str) -> bool:
        """Check if key concepts/words are present in both texts"""
        user_words = set(user_text.split())
        correct_words = set(correct_text.split())
        
        # Remove common stop words
        stop_words = {'a', 'an', 'the', 'is', 'are', 'was', 'were', 'be', 'been', 'being', 
                     'have', 'has', 'had', 'do', 'does', 'did', 'will', 'would', 'could', 
                     'should', 'may', 'might', 'can', 'to', 'of', 'in', 'on', 'at', 'by', 
                     'for', 'with', 'from', 'up', 'about', 'into', 'through', 'during', 
                     'before', 'after', 'above', 'below', 'between', 'among', 'and', 'or', 'but'}
        
        user_keywords = user_words - stop_words
        correct_keywords = correct_words - stop_words
        
        if not user_keywords or not correct_keywords:
            return False
        
        # Check if at least 50% of keywords match (lowered threshold)
        intersection = user_keywords.intersection(correct_keywords)
        similarity_ratio = len(intersection) / max(len(user_keywords), len(correct_keywords))
        
        # Also accept if at least 2 important keywords match
        if len(intersection) >= 2:
            return True
        
        return similarity_ratio >= 0.5
    
    def _check_semantic_similarity(self, user_text: str, correct_text: str) -> bool:
        """Check semantic similarity using word overlap and context"""
        user_words = user_text.split()
        correct_words = correct_text.split()
        
        if not user_words or not correct_words:
            return False
        
        # Remove stop words for better comparison
        stop_words = {'a', 'an', 'the', 'is', 'are', 'was', 'were', 'be', 'been', 'being', 
                     'have', 'has', 'had', 'do', 'does', 'did', 'will', 'would', 'could', 
                     'should', 'may', 'might', 'can', 'to', 'of', 'in', 'on', 'at', 'by', 
                     'for', 'with', 'from', 'up', 'about', 'into', 'through', 'during', 
                     'before', 'after', 'above', 'below', 'between', 'among', 'and', 'or', 'but'}
        
        user_set = set(user_words) - stop_words
        correct_set = set(correct_words) - stop_words
        
        if not user_set or not correct_set:
            return False
        
        # Calculate word overlap ratio
        intersection = user_set.intersection(correct_set)
        union = user_set.union(correct_set)
        
        if len(union) == 0:
            return False
        
        jaccard_similarity = len(intersection) / len(union)
        
        # Also check if most important words match
        important_words = intersection
        if len(important_words) >= 2:  # At least 2 important words match
            return True
        
        # Require at least 40% word overlap for semantic similarity (lowered threshold)
        return jaccard_similarity >= 0.4
    
    def _check_paraphrase_similarity(self, user_text: str, correct_text: str) -> bool:
        """Check for paraphrases using synonym detection"""
        # Enhanced synonym mapping for common words and phrases
        synonyms = {
            'big': ['large', 'huge', 'enormous', 'massive'],
            'small': ['little', 'tiny', 'miniature', 'compact'],
            'good': ['great', 'excellent', 'wonderful', 'fantastic'],
            'bad': ['terrible', 'awful', 'horrible', 'poor'],
            'fast': ['quick', 'rapid', 'swift', 'speedy'],
            'slow': ['sluggish', 'gradual', 'leisurely'],
            'happy': ['joyful', 'cheerful', 'glad', 'pleased'],
            'sad': ['unhappy', 'depressed', 'gloomy', 'melancholy'],
            'smart': ['intelligent', 'clever', 'bright', 'wise'],
            'stupid': ['foolish', 'dumb', 'silly', 'unintelligent'],
            'beautiful': ['pretty', 'lovely', 'gorgeous', 'attractive'],
            'ugly': ['unattractive', 'hideous', 'repulsive'],
            'easy': ['simple', 'effortless', 'straightforward', 'very easy', 'extremely easy', 'super easy', 'really easy', 'quite easy'],
            'hard': ['difficult', 'challenging', 'tough', 'complex', 'very hard', 'extremely hard', 'super hard', 'really hard', 'quite hard'],
            'new': ['fresh', 'recent', 'modern', 'latest'],
            'old': ['ancient', 'aged', 'elderly', 'vintage']
        }
        
        # Multi-word phrase synonyms (idioms and expressions)
        phrase_synonyms = {
            'piece of cake': ['very easy', 'extremely easy', 'super easy', 'really easy', 'quite easy', 'easy', 'simple', 'effortless', 'straightforward', 'walk in the park', 'breeze', 'no problem', 'childs play'],
            'walk in the park': ['piece of cake', 'very easy', 'easy', 'simple', 'effortless', 'breeze'],
            'breeze': ['piece of cake', 'walk in the park', 'very easy', 'easy', 'simple', 'effortless'],
            'no problem': ['piece of cake', 'very easy', 'easy', 'simple', 'effortless'],
            'childs play': ['piece of cake', 'very easy', 'easy', 'simple', 'effortless'],
            'very easy': ['piece of cake', 'walk in the park', 'breeze', 'no problem', 'childs play', 'easy', 'simple', 'effortless', 'straightforward'],
            'extremely easy': ['piece of cake', 'very easy', 'easy', 'simple', 'effortless'],
            'super easy': ['piece of cake', 'very easy', 'easy', 'simple', 'effortless'],
            'really easy': ['piece of cake', 'very easy', 'easy', 'simple', 'effortless'],
            'quite easy': ['piece of cake', 'very easy', 'easy', 'simple', 'effortless']
        }
        
        user_words = user_text.split()
        correct_words = correct_text.split()
        
        # First check for exact phrase matches in phrase_synonyms
        user_phrase = user_text.lower().strip()
        correct_phrase = correct_text.lower().strip()
        
        # Check if either phrase is in the phrase synonyms
        for phrase, synonyms_list in phrase_synonyms.items():
            if user_phrase == phrase and correct_phrase in synonyms_list:
                return True
            if correct_phrase == phrase and user_phrase in synonyms_list:
                return True
        
        # Check if words are synonyms (single word matching)
        for user_word in user_words:
            for correct_word in correct_words:
                if user_word in synonyms and correct_word in synonyms[user_word]:
                    return True
                if correct_word in synonyms and user_word in synonyms[correct_word]:
                    return True
        
        return False
    
    def submit_flashcard_answer_advanced(self, session_id: str, request: FlashcardAnswerRequest) -> Dict[str, Any]:
        """Submit an answer for a flashcard with advanced processing"""
        try:
            # Get session
            session = self.get_flashcard_session(session_id)
            if not session:
                raise ValueError("Session not found")
            
            # Get current card progress
            progress_result = self.client.table("flashcard_progress").select("*").eq("session_id", session_id).eq("vocab_entry_id", request.vocab_entry_id).execute()
            
            if not progress_result.data:
                # Debug: Check what cards are actually in the session
                all_progress = self.client.table("flashcard_progress").select("vocab_entry_id").eq("session_id", session_id).execute()
                session_cards = [p["vocab_entry_id"] for p in all_progress.data] if all_progress.data else []
                
                print(f"Debug: Session {session_id} has cards: {session_cards}")
                print(f"Debug: Looking for card: {request.vocab_entry_id}")
                
                raise ValueError(f"Card {request.vocab_entry_id} not found in session {session_id}. Available cards: {session_cards}")
            
            progress = progress_result.data[0]
            correct_answer = progress["correct_answer"]
            
            # Get the vocabulary word for context
            vocab_entry_id = progress["vocab_entry_id"]
            vocab_result = self.client.table("vocab_entries").select("word, definition").eq("id", vocab_entry_id).execute()
            word_context = None
            if vocab_result.data:
                word_context = f"Word: {vocab_result.data[0]['word']}, Definition: {vocab_result.data[0]['definition']}"
            
            # Check if answer is correct using AI-powered semantic validation
            is_correct, ai_confidence, reasoning = self._validate_answer(
                request.user_answer, 
                correct_answer, 
                session["study_mode"],
                word=vocab_result.data[0]['word'] if vocab_result.data else None,
                context=word_context
            )
            
            # Use AI confidence as base, then adjust based on other factors
            base_confidence = ai_confidence
            confidence_score = self._calculate_confidence_score_enhanced(
                is_correct, base_confidence, request.response_time_seconds, 
                request.hints_used, request.confidence_level, reasoning
            )
            
            # Update progress
            progress_update = {
                "user_answer": request.user_answer,
                "response_time_seconds": request.response_time_seconds,
                "hints_used": request.hints_used,
                "is_correct": is_correct,
                "difficulty_rating": request.difficulty_rating.value if request.difficulty_rating else None,
                "confidence_level": request.confidence_level,
                "confidence_score": confidence_score,
                "attempts": progress.get("attempts", 0) + 1
            }
            
            self.client.table("flashcard_progress").update(progress_update).eq("id", progress["id"]).execute()
            
            # Update session stats
            session_update = {}
            if is_correct:
                session_update["correct_answers"] = session["correct_answers"] + 1
            else:
                session_update["incorrect_answers"] = session["incorrect_answers"] + 1
            
            session_update["hints_used"] = session["hints_used"] + request.hints_used
            session_update["total_time_seconds"] = session["total_time_seconds"] + int(request.response_time_seconds)
            
            # Move to next card
            session_update["current_card_index"] = session["current_card_index"] + 1
            
            # Check if session is complete
            if session_update["current_card_index"] >= session["total_cards"]:
                session_update["is_active"] = False
                session_update["completed_at"] = datetime.now().isoformat()
            
            self.client.table("flashcard_sessions").update(session_update).eq("id", session_id).execute()
            
            # Update user vocabulary review count and mastery level if correct
            if is_correct:
                self._update_vocab_mastery(session["user_id"], request.vocab_entry_id, confidence_score)
            
            return {
                "is_correct": is_correct,
                "correct_answer": correct_answer,
                "user_answer": request.user_answer,
                "response_time_seconds": request.response_time_seconds,
                "confidence_score": confidence_score,
                "feedback": reasoning,  # Enhanced feedback with learning tips and encouragement
                "session_complete": session_update.get("current_card_index", 0) >= session["total_cards"],
                "progress": {
                    "correct_answers": session_update.get("correct_answers", session["correct_answers"]),
                    "incorrect_answers": session_update.get("incorrect_answers", session["incorrect_answers"]),
                    "current_card": session_update.get("current_card_index", session["current_card_index"]),
                    "total_cards": session["total_cards"],
                    "hints_used": session_update.get("hints_used", session["hints_used"]),
                    "total_time_seconds": session_update.get("total_time_seconds", session["total_time_seconds"])
                }
            }
            
        except Exception as e:
            print(f"Error submitting flashcard answer: {e}")
            raise
    
    def _calculate_confidence_score_enhanced(self, is_correct: bool, ai_confidence: float, 
                                           response_time: float, hints_used: int, 
                                           confidence_level: Optional[int], reasoning: str) -> float:
        """Calculate enhanced confidence score using AI confidence as base"""
        
        # Start with AI confidence as the base
        score = ai_confidence
        
        # Adjust based on response time (but don't penalize too much)
        if response_time < 1.0:  # Too fast, might be guessing
            score *= 0.9
        elif response_time < 2.0:  # Very fast but acceptable
            score *= 0.95
        elif response_time > 60.0:  # Too slow, might indicate confusion
            score *= 0.8
        
        # Adjust based on hints used
        if hints_used > 0:
            score *= (1.0 - (hints_used * 0.1))  # Reduce by 10% per hint
        
        # Adjust based on user confidence (if provided)
        if confidence_level:
            if confidence_level >= 4:
                score *= 1.05  # Slight boost for high confidence
            elif confidence_level <= 2:
                score *= 0.9   # Slight reduction for low confidence
        
        # Ensure score stays within bounds
        return min(1.0, max(0.0, score))
    
    def _calculate_confidence_score(self, is_correct: bool, response_time: float, 
                                  hints_used: int, confidence_level: Optional[int]) -> float:
        """Calculate confidence score based on multiple factors"""
        
        score = 0.0
        
        # Base score from correctness
        if is_correct:
            score += 0.5
        else:
            score += 0.1
        
        # Response time factor (faster = more confident)
        if response_time < 5:
            score += 0.3
        elif response_time < 15:
            score += 0.2
        elif response_time < 30:
            score += 0.1
        
        # Hints factor (fewer hints = more confident)
        if hints_used == 0:
            score += 0.2
        elif hints_used == 1:
            score += 0.1
        
        # User confidence level
        if confidence_level:
            score += (confidence_level - 1) * 0.05  # 1-5 scale to 0-0.2
        
        return min(1.0, max(0.0, score))
    
    def _update_vocab_mastery(self, user_id: str, vocab_entry_id: str, confidence_score: float):
        """Update vocabulary mastery level based on performance"""
        try:
            # Get current user vocab entry
            result = self.client.table("user_vocab_entries").select("*").eq("user_id", user_id).eq("vocab_entry_id", vocab_entry_id).execute()
            
            if result.data:
                current_data = result.data[0]
                current_review_count = current_data.get("review_count", 0)
                
                # Update review count and mastery
                mastery_delta = confidence_score * 0.1  # 0.0 to 0.1
                new_mastery = min(1.0, (current_data.get("mastery_level", 0.0) or 0.0) + mastery_delta)
                
                update_data = {
                    "review_count": current_review_count + 1,
                    "last_reviewed": datetime.now().isoformat(),
                    "mastery_level": new_mastery,
                    "updated_at": datetime.now().isoformat()
                }
                
                self.client.table("user_vocab_entries").update(update_data).eq("user_id", user_id).eq("vocab_entry_id", vocab_entry_id).execute()
                
        except Exception as e:
            print(f"Error updating vocab mastery: {e}")
    
    def get_flashcard_analytics(self, user_id: str, days: int = 30) -> Dict[str, Any]:
        """Get comprehensive flashcard analytics"""
        try:
            # Get sessions from last N days
            cutoff_date = datetime.now() - timedelta(days=days)
            
            sessions_result = self.client.table("flashcard_sessions").select("*").eq("user_id", user_id).gte("created_at", cutoff_date.isoformat()).execute()
            sessions = sessions_result.data if sessions_result.data else []
            
            # Get progress entries
            progress_result = self.client.table("flashcard_progress").select("*").eq("user_id", user_id).gte("created_at", cutoff_date.isoformat()).execute()
            progress_entries = progress_result.data if progress_result.data else []
            
            # Calculate analytics
            total_sessions = len(sessions)
            total_cards = len(progress_entries)
            correct_answers = sum(1 for p in progress_entries if p.get("is_correct") is True)
            incorrect_answers = sum(1 for p in progress_entries if p.get("is_correct") is False)
            
            accuracy = (correct_answers / total_cards * 100) if total_cards > 0 else 0
            
            # Response time analysis
            response_times = [p.get("response_time_seconds") for p in progress_entries if p.get("response_time_seconds")]
            avg_response_time = sum(response_times) / len(response_times) if response_times else 0
            
            # Study mode distribution
            study_modes = [s.get("study_mode") for s in sessions if s.get("study_mode")]
            mode_distribution = {}
            for mode in study_modes:
                mode_distribution[mode] = mode_distribution.get(mode, 0) + 1
            
            # Time of day analysis
            time_distribution = {}
            for session in sessions:
                created_at = session.get("created_at")
                if created_at:
                    dt = self._parse_date(created_at)
                    if dt:
                        hour = dt.hour
                        time_slot = f"{hour//4*4:02d}-{(hour//4*4+4)%24:02d}"
                        time_distribution[time_slot] = time_distribution.get(time_slot, 0) + 1
            
            # Performance trends
            daily_performance = {}
            for session in sessions:
                created_at = session.get("created_at")
                if created_at:
                    dt = self._parse_date(created_at)
                    if dt:
                        date = dt.date()
                        if date not in daily_performance:
                            daily_performance[date] = {"sessions": 0, "correct": 0, "total": 0}
                        
                        daily_performance[date]["sessions"] += 1
                        
                        daily_performance[date]["correct"] += session.get("correct_answers", 0)
                        daily_performance[date]["total"] += session.get("total_cards", 0)
            
            return {
                "period_days": days,
                "total_sessions": total_sessions,
                "total_cards_studied": total_cards,
                "correct_answers": correct_answers,
                "incorrect_answers": incorrect_answers,
                "accuracy_percentage": round(accuracy, 2),
                "average_response_time": round(avg_response_time, 2),
                "study_mode_distribution": mode_distribution,
                "time_distribution": time_distribution,
                "daily_performance": daily_performance,
                "improvement_trend": self._calculate_improvement_trend(daily_performance),
                "recommendations": self._generate_analytics_recommendations(accuracy, avg_response_time, mode_distribution)
            }
            
        except Exception as e:
            print(f"Error getting flashcard analytics: {e}")
            raise
    
    def _calculate_improvement_trend(self, daily_performance: Dict) -> str:
        """Calculate improvement trend from daily performance"""
        if len(daily_performance) < 2:
            return "insufficient_data"
        
        # Get recent vs older performance
        sorted_dates = sorted(daily_performance.keys())
        recent_dates = sorted_dates[-3:]  # Last 3 days
        older_dates = sorted_dates[:-3] if len(sorted_dates) > 3 else sorted_dates[:2]
        
        recent_accuracy = sum(daily_performance[d]["correct"] / max(1, daily_performance[d]["total"]) for d in recent_dates) / len(recent_dates)
        older_accuracy = sum(daily_performance[d]["correct"] / max(1, daily_performance[d]["total"]) for d in older_dates) / len(older_dates)
        
        if recent_accuracy > older_accuracy + 0.05:
            return "improving"
        elif recent_accuracy < older_accuracy - 0.05:
            return "declining"
        else:
            return "stable"
    
    def _generate_analytics_recommendations(self, accuracy: float, avg_response_time: float, 
                                          mode_distribution: Dict) -> List[str]:
        """Generate recommendations based on analytics"""
        recommendations = []
        
        if accuracy < 60:
            recommendations.append("Consider reviewing easier vocabulary or using more hints")
        
        if avg_response_time > 30:
            recommendations.append("Try to think faster or use hints when stuck")
        
        if len(mode_distribution) == 1:
            recommendations.append("Try different study modes for variety")
        
        if not recommendations:
            recommendations.append("Great performance! Keep up the good work")
        
        return recommendations
    
    def get_flashcard_stats(self, user_id: str) -> Dict[str, Any]:
        """Get flashcard statistics for a user"""
        try:
            # Get all sessions
            sessions_result = self.client.table("flashcard_sessions").select("*").eq("user_id", user_id).execute()
            sessions = sessions_result.data if sessions_result.data else []
            
            # Get all progress entries
            progress_result = self.client.table("flashcard_progress").select("*").eq("user_id", user_id).execute()
            progress_entries = progress_result.data if progress_result.data else []
            
            # Calculate stats
            total_sessions = len(sessions)
            total_cards_studied = len(progress_entries)
            total_correct = sum(1 for p in progress_entries if p.get("is_correct") is True)
            total_incorrect = sum(1 for p in progress_entries if p.get("is_correct") is False)
            total_skipped = sum(s.get("skipped_cards", 0) for s in sessions)
            
            # Calculate average response time
            response_times = [p.get("response_time_seconds") for p in progress_entries if p.get("response_time_seconds")]
            average_response_time = sum(response_times) / len(response_times) if response_times else None
            
            # Calculate accuracy
            accuracy_percentage = (total_correct / total_cards_studied * 100) if total_cards_studied > 0 else 0
            
            # Get favorite study mode
            study_modes = [s.get("study_mode") for s in sessions if s.get("study_mode")]
            favorite_study_mode = max(set(study_modes), key=study_modes.count) if study_modes else None
            
            # Get last study date
            last_study_date = None
            if sessions:
                last_session = max(sessions, key=lambda x: x.get("created_at", ""))
                last_study_date = last_session.get("created_at")
            
            # Calculate streak (simplified - consecutive days with study sessions)
            streak_days = self._calculate_study_streak(sessions)
            
            # Calculate improvement rate (simplified)
            improvement_rate = 0.0
            if len(sessions) > 1:
                recent_sessions = sorted(sessions, key=lambda x: x.get("created_at", ""))[-5:]
                if len(recent_sessions) >= 2:
                    recent_accuracy = sum(s.get("correct_answers", 0) / max(1, s.get("total_cards", 1)) for s in recent_sessions[-3:]) / 3
                    older_accuracy = sum(s.get("correct_answers", 0) / max(1, s.get("total_cards", 1)) for s in recent_sessions[:2]) / 2
                    improvement_rate = (recent_accuracy - older_accuracy) * 100
            
            return {
                "total_sessions": total_sessions,
                "total_cards_studied": total_cards_studied,
                "total_correct": total_correct,
                "total_incorrect": total_incorrect,
                "total_skipped": total_skipped,
                "average_response_time": average_response_time,
                "accuracy_percentage": round(accuracy_percentage, 2),
                "streak_days": streak_days,
                "last_study_date": last_study_date,
                "favorite_study_mode": favorite_study_mode,
                "most_difficult_level": None,  # Would need more complex calculation
                "most_difficult_topic": None,   # Would need more complex calculation
                "improvement_rate": round(improvement_rate, 2),
                "total_study_time_minutes": sum(s.get("total_time_seconds", 0) for s in sessions) // 60
            }
            
        except Exception as e:
            print(f"Error getting flashcard stats: {e}")
            raise
    
    def _calculate_study_streak(self, sessions: List[Dict[str, Any]]) -> int:
        """Calculate consecutive days with study sessions"""
        try:
            if not sessions:
                return 0
            
            # Get unique study dates
            study_dates = set()
            for session in sessions:
                created_at = session.get("created_at")
                if created_at:
                    dt = self._parse_date(created_at)
                    if dt:
                        study_date = dt.date()
                        study_dates.add(study_date)
            
            if not study_dates:
                return 0
            
            # Sort dates
            sorted_dates = sorted(study_dates, reverse=True)
            
            # Calculate streak
            streak = 0
            current_date = datetime.now().date()
            
            for date in sorted_dates:
                if date == current_date or date == current_date - timedelta(days=1):
                    streak += 1
                    current_date = date
                else:
                    break
            
            return streak
            
        except Exception as e:
            print(f"Error calculating study streak: {e}")
            return 0
    
    def get_cards_for_review(self, user_id: str, limit: int = 20) -> List[Dict[str, Any]]:
        """Get cards that are due for review based on spaced repetition"""
        try:
            # Get user's vocabulary with review data
            user_vocab_result = self.client.table("user_vocab_entries").select("""
                *, vocab_entries(
                    id, word, definition, translation, example, example_translation,
                    level, part_of_speech, target_language, original_language
                )
            """).eq("user_id", user_id).execute()
            
            if not user_vocab_result.data:
                return []
            
            # Filter cards that need review
            cards_for_review = []
            current_time = datetime.now()
            
            for user_vocab in user_vocab_result.data:
                vocab = user_vocab.get("vocab_entries")
                if not vocab:
                    continue
                last_reviewed = user_vocab.get("last_reviewed")
                review_count = user_vocab.get("review_count", 0)
                
                # Simple spaced repetition logic
                needs_review = False
                
                if not last_reviewed:
                    # Never reviewed
                    needs_review = True
                else:
                    last_review_date = datetime.fromisoformat(last_reviewed.replace('Z', '+00:00'))
                    days_since_review = (current_time - last_review_date).days
                    
                    # Calculate next review interval based on review count
                    if review_count == 0:
                        next_interval = 1  # 1 day
                    elif review_count == 1:
                        next_interval = 3  # 3 days
                    elif review_count == 2:
                        next_interval = 7  # 1 week
                    elif review_count == 3:
                        next_interval = 14  # 2 weeks
                    else:
                        next_interval = 30  # 1 month
                    
                    needs_review = days_since_review >= next_interval
                
                if needs_review:
                    card = {
                        "vocab_entry_id": vocab["id"],
                        "word": vocab["word"],
                        "definition": vocab["definition"],
                        "translation": vocab["translation"],
                        "example": vocab["example"],
                        "example_translation": vocab["example_translation"],
                        "part_of_speech": vocab["part_of_speech"],
                        "level": vocab["level"],
                        "review_count": review_count,
                        "last_reviewed": last_reviewed,
                        "is_favorite": user_vocab.get("is_favorite", False),
                        "difficulty_rating": user_vocab.get("difficulty_rating"),
                        "personal_notes": user_vocab.get("personal_notes"),
                        "mastery_level": user_vocab.get("mastery_level", 0.0)
                    }
                    cards_for_review.append(card)
            
            # Sort by priority (never reviewed first, then by days since last review)
            cards_for_review.sort(key=lambda x: (x["review_count"], x["last_reviewed"] or ""))
            
            return cards_for_review[:limit]
            
        except Exception as e:
            print(f"Error getting cards for review: {e}")
            raise
    
    def get_flashcard_sessions(self, user_id: str, limit: int = 50) -> List[Dict[str, Any]]:
        """Get user's flashcard sessions"""
        try:
            result = self.client.table("flashcard_sessions").select("*").eq("user_id", user_id).order("created_at", desc=True).limit(limit).execute()
            return result.data if result.data else []
        except Exception as e:
            print(f"Error getting flashcard sessions: {e}")
            raise
    
    def get_flashcard_session(self, session_id: str) -> Optional[Dict[str, Any]]:
        """Get a specific flashcard session by ID"""
        try:
            result = self.client.table("flashcard_sessions").select("*").eq("id", session_id).execute()
            return result.data[0] if result.data else None
        except Exception as e:
            print(f"Error getting flashcard session: {e}")
            raise
    
    def get_current_flashcard(self, session_id: str) -> Optional[Dict[str, Any]]:
        """Get the current flashcard for a session"""
        try:
            # Get the session
            session = self.get_flashcard_session(session_id)
            if not session:
                return None
            
            current_index = session.get("current_card_index", 0)
            total_cards = session.get("total_cards", 0)
            
            if current_index >= total_cards:
                return None  # Session completed
            
            # Get the current card from flashcard_progress table (the correct way)
            progress_result = self.client.table("flashcard_progress").select("vocab_entry_id, card_index").eq("session_id", session_id).eq("card_index", current_index).execute()
            
            if not progress_result.data:
                return None
            
            progress = progress_result.data[0]
            vocab_entry_id = progress["vocab_entry_id"]
            
            # Get the vocabulary details
            vocab_result = self.client.table("vocab_entries").select("*").eq("id", vocab_entry_id).execute()
            
            if not vocab_result.data:
                return None
            
            vocab_data = vocab_result.data[0]
            
            # Build the card response
            card = {
                "vocab_entry_id": vocab_data["id"],
                "word": vocab_data["word"],
                "definition": vocab_data["definition"],
                "translation": vocab_data["translation"],
                "example": vocab_data["example"],
                "example_translation": vocab_data["example_translation"],
                "part_of_speech": vocab_data["part_of_speech"],
                "level": vocab_data["level"],
                "card_index": current_index,
                "total_cards": total_cards
            }
            
            return card
            
        except Exception as e:
            print(f"Error getting current flashcard: {e}")
            return None
    
    def delete_flashcard_session(self, session_id: str, user_id: str) -> bool:
        """Delete a flashcard session and its associated progress"""
        try:
            # First, delete all progress entries for this session
            self.client.table("flashcard_progress").delete().eq("session_id", session_id).execute()
            
            # Then delete the session
            result = self.client.table("flashcard_sessions").delete().eq("id", session_id).eq("user_id", user_id).execute()
            
            return bool(result.data)
            
        except Exception as e:
            print(f"Error deleting flashcard session: {e}")
            return False
