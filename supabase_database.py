from supabase import create_client, Client
from typing import List, Dict, Any, Optional
from models import VocabEntry, CEFRLevel, UserVocabList, UserVocabEntry, VocabEntryWithUserData
import os
from dotenv import load_dotenv
import json
from datetime import datetime, timedelta

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
        """Get topic ID by name and optionally category"""
        query = self.client.table("topics").select("id")
        
        if category_name:
            # Get category ID first
            category_result = self.client.table("categories").select("id").eq("name", category_name).execute()
            if not category_result.data:
                return None
            category_id = category_result.data[0]["id"]
            query = query.eq("name", topic_name).eq("category_id", category_id)
        else:
            query = query.eq("name", topic_name)
        
        result = query.execute()
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
        
        # Get or create topic ID if topic name is provided
        topic_id = None
        if topic_name:
            try:
                topic_id = self.create_topic_if_not_exists(topic_name, category_name)
            except Exception as e:
                print(f"Error with topic '{topic_name}': {e}")
                # Continue without topic_id if topic creation fails
                topic_id = None
        
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
            
            # Check if the word already exists in vocab_entries
            existing_vocab = self.client.table("vocab_entries").select("*").eq("word", vocab_entry.word).eq("level", vocab_entry.level.value).execute()
            
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