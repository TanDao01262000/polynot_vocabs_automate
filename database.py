import sqlite3
from typing import List
from models import VocabEntry, CEFRLevel
import os

class VocabDatabase:
    def __init__(self, db_path: str = "vocab.db"):
        self.db_path = db_path
        self.init_database()
    
    def init_database(self):
        """Initialize the database with required tables"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            
            # Create vocab_entries table with composite unique constraint
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS vocab_entries (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
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
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(word, topic, level, part_of_speech)
                )
            ''')
            
            # Create topic_lists table to track custom topic lists
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS topic_lists (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    list_name TEXT NOT NULL,
                    topics TEXT NOT NULL,  -- JSON array of topics
                    category TEXT,         -- if from predefined category
                    level TEXT NOT NULL,
                    target_language TEXT,
                    original_language TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            conn.commit()
    
    def insert_vocab_entries(self, entries: List[VocabEntry], topic: str = None, 
                           target_language: str = None, original_language: str = None):
        """Insert multiple vocab entries into the database, skipping duplicates"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            
            inserted_count = 0
            skipped_count = 0
            
            for entry in entries:
                try:
                    cursor.execute('''
                        INSERT INTO vocab_entries 
                        (word, definition, translation, example, example_translation, level, part_of_speech, topic, target_language, original_language)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ''', (
                        entry.word,
                        entry.definition,
                        entry.translation,
                        entry.example,
                        entry.example_translation,
                        entry.level.value,
                        getattr(entry, 'part_of_speech', None),  # Handle if not in model yet
                        topic,
                        target_language,
                        original_language
                    ))
                    inserted_count += 1
                except sqlite3.IntegrityError:
                    # Duplicate combination of word, topic, level, part_of_speech
                    skipped_count += 1
                    print(f"Skipped duplicate: {entry.word} (topic: {topic}, level: {entry.level.value})")
            
            conn.commit()
            print(f"Inserted {inserted_count} new vocab entries, skipped {skipped_count} duplicates")
    
    def get_vocab_entries(self, topic: str = None, level: CEFRLevel = None, limit: int = 100):
        """Retrieve vocab entries from database with optional filters"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            
            query = "SELECT * FROM vocab_entries WHERE 1=1"
            params = []
            
            if topic:
                query += " AND topic = ?"
                params.append(topic)
            
            if level:
                query += " AND level = ?"
                params.append(level.value)
            
            query += " ORDER BY created_at DESC LIMIT ?"
            params.append(limit)
            
            cursor.execute(query, params)
            rows = cursor.fetchall()
            
            entries = []
            for row in rows:
                entry = VocabEntry(
                    word=row[1],
                    definition=row[2],
                    translation=row[3],
                    example=row[4],
                    example_translation=row[5],
                    level=CEFRLevel(row[6])
                )
                entries.append(entry)
            
            return entries 

    def get_existing_combinations(self, topic: str = None) -> List[tuple]:
        """Get existing word combinations to avoid duplicates"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            
            query = "SELECT word, level, part_of_speech FROM vocab_entries WHERE 1=1"
            params = []
            
            if topic:
                query += " AND topic = ?"
                params.append(topic)
            
            cursor.execute(query, params)
            rows = cursor.fetchall()
            
            return [(row[0], row[1], row[2]) for row in rows] 
    
    def save_topic_list(self, topics: List[str], list_name: str = None, 
                       category: str = None, level: CEFRLevel = CEFRLevel.A2,
                       target_language: str = "Vietnamese", original_language: str = "English"):
        """Save a custom topic list to the database"""
        import json
        
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            
            # Generate list name if not provided
            if not list_name:
                list_name = f"custom_list_{len(topics)}_topics"
            
            cursor.execute('''
                INSERT INTO topic_lists 
                (list_name, topics, category, level, target_language, original_language)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (
                list_name,
                json.dumps(topics),  
                category,
                level.value,
                target_language,
                original_language
            ))
            
            conn.commit()
            print(f"Saved topic list '{list_name}' with {len(topics)} topics")
    
    def get_topic_lists(self) -> List[dict]:
        """Get all saved topic lists"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            
            cursor.execute('''
                SELECT list_name, topics, category, level, target_language, original_language, created_at
                FROM topic_lists
                ORDER BY created_at DESC
            ''')
            
            rows = cursor.fetchall()
            import json
            
            topic_lists = []
            for row in rows:
                topic_lists.append({
                    "list_name": row[0],
                    "topics": json.loads(row[1]), 
                    "category": row[2],
                    "level": row[3],
                    "target_language": row[4],
                    "original_language": row[5],
                    "created_at": row[6]
                })
            
            return topic_lists 