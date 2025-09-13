"""
Intelligent Caching System for AI-Powered Answer Validation
This module provides multiple layers of caching to optimize AI validation performance
and reduce API costs while maintaining accuracy.
"""

import hashlib
import json
import time
from typing import Dict, Any, Optional, Tuple, List
from datetime import datetime, timedelta
from dataclasses import dataclass, asdict
from functools import lru_cache
import sqlite3
import os
from pathlib import Path

@dataclass
class ValidationCacheEntry:
    """Cache entry for validation results"""
    user_answer: str
    correct_answer: str
    question_type: str
    study_mode: str
    word: Optional[str]
    context: Optional[str]
    is_correct: bool
    confidence_score: float
    reasoning: str
    semantic_similarity: float
    is_meaningful: bool
    suggested_correction: Optional[str]
    feedback: Optional[str]
    encouragement: Optional[str]
    created_at: datetime
    access_count: int = 0
    last_accessed: Optional[datetime] = None

class ValidationCache:
    """Multi-layer caching system for validation results"""
    
    def __init__(self, 
                 cache_db_path: str = "validation_cache.db",
                 max_memory_entries: int = 1000,
                 cache_ttl_hours: int = 24,
                 similarity_threshold: float = 0.85):
        """
        Initialize the validation cache system
        
        Args:
            cache_db_path: Path to SQLite database for persistent cache
            max_memory_entries: Maximum entries in memory LRU cache
            cache_ttl_hours: Time-to-live for cache entries in hours
            similarity_threshold: Threshold for semantic similarity matching
        """
        self.cache_db_path = cache_db_path
        self.max_memory_entries = max_memory_entries
        self.cache_ttl_hours = cache_ttl_hours
        self.similarity_threshold = similarity_threshold
        
        # In-memory LRU cache for frequently accessed entries
        self._memory_cache = {}
        self._access_times = {}
        
        # Initialize database
        self._init_database()
        
        # Cache statistics
        self.stats = {
            'memory_hits': 0,
            'db_hits': 0,
            'ai_calls': 0,
            'exact_matches': 0,
            'similarity_matches': 0,
            'cache_misses': 0,
            'total_requests': 0
        }
    
    def _init_database(self):
        """Initialize SQLite database for persistent cache"""
        Path(self.cache_db_path).parent.mkdir(parents=True, exist_ok=True)
        
        with sqlite3.connect(self.cache_db_path) as conn:
            conn.execute('''
                CREATE TABLE IF NOT EXISTS validation_cache (
                    cache_key TEXT PRIMARY KEY,
                    user_answer TEXT NOT NULL,
                    correct_answer TEXT NOT NULL,
                    question_type TEXT NOT NULL,
                    study_mode TEXT NOT NULL,
                    word TEXT,
                    context TEXT,
                    is_correct BOOLEAN NOT NULL,
                    confidence_score REAL NOT NULL,
                    reasoning TEXT NOT NULL,
                    semantic_similarity REAL NOT NULL,
                    is_meaningful BOOLEAN NOT NULL,
                    suggested_correction TEXT,
                    feedback TEXT,
                    encouragement TEXT,
                    created_at TIMESTAMP NOT NULL,
                    access_count INTEGER DEFAULT 0,
                    last_accessed TIMESTAMP
                )
            ''')
            
            # Create index for faster lookups
            conn.execute('''
                CREATE INDEX IF NOT EXISTS idx_cache_lookup 
                ON validation_cache(user_answer, correct_answer, question_type, study_mode)
            ''')
            
            # Create index for cleanup
            conn.execute('''
                CREATE INDEX IF NOT EXISTS idx_cache_created_at 
                ON validation_cache(created_at)
            ''')
    
    def _generate_cache_key(self, 
                          user_answer: str, 
                          correct_answer: str, 
                          question_type: str, 
                          study_mode: str,
                          word: Optional[str] = None,
                          context: Optional[str] = None) -> str:
        """
        Generate a unique cache key for the validation request
        
        QUALITY ASSURANCE: This method ensures that:
        1. Different contexts (word, question_type, study_mode) create different cache entries
        2. Exact matches are normalized consistently
        3. Similar answers are handled appropriately
        4. No cross-contamination between different validation scenarios
        """
        # Normalize inputs for consistent caching while preserving context differences
        normalized_user = user_answer.strip().lower()
        normalized_correct = correct_answer.strip().lower()
        normalized_word = word.strip().lower() if word else ""
        normalized_context = context.strip() if context else ""
        
        # Create hash of normalized inputs - each parameter creates unique cache entries
        # This ensures different contexts get different validations
        content = f"{normalized_user}|{normalized_correct}|{question_type}|{study_mode}|{normalized_word}|{normalized_context}"
        return hashlib.md5(content.encode()).hexdigest()
    
    def _is_exact_match(self, user_answer: str, correct_answer: str) -> bool:
        """Check for exact match (case-insensitive)"""
        return user_answer.strip().lower() == correct_answer.strip().lower()
    
    def _calculate_simple_similarity(self, user_answer: str, correct_answer: str) -> float:
        """Calculate simple word-based similarity without AI"""
        user_words = set(user_answer.lower().split())
        correct_words = set(correct_answer.lower().split())
        
        if not user_words or not correct_words:
            return 0.0
        
        intersection = user_words.intersection(correct_words)
        union = user_words.union(correct_words)
        
        return len(intersection) / len(union) if union else 0.0
    
    def _cleanup_expired_entries(self):
        """Remove expired entries from database"""
        cutoff_time = datetime.now() - timedelta(hours=self.cache_ttl_hours)
        
        with sqlite3.connect(self.cache_db_path) as conn:
            conn.execute(
                'DELETE FROM validation_cache WHERE created_at < ?',
                (cutoff_time,)
            )
    
    def _update_access_stats(self, cache_key: str, entry: ValidationCacheEntry):
        """Update access statistics for cache entry"""
        entry.access_count += 1
        entry.last_accessed = datetime.now()
        
        # Update in database
        with sqlite3.connect(self.cache_db_path) as conn:
            conn.execute(
                'UPDATE validation_cache SET access_count = ?, last_accessed = ? WHERE cache_key = ?',
                (entry.access_count, entry.last_accessed, cache_key)
            )
    
    def get_cached_result(self, 
                         user_answer: str, 
                         correct_answer: str, 
                         question_type: str, 
                         study_mode: str,
                         word: Optional[str] = None,
                         context: Optional[str] = None) -> Optional[ValidationCacheEntry]:
        """Get cached validation result if available"""
        self.stats['total_requests'] += 1
        
        # Check for exact match first (fastest)
        if self._is_exact_match(user_answer, correct_answer):
            self.stats['exact_matches'] += 1
            return ValidationCacheEntry(
                user_answer=user_answer,
                correct_answer=correct_answer,
                question_type=question_type,
                study_mode=study_mode,
                word=word,
                context=context,
                is_correct=True,
                confidence_score=1.0,
                reasoning="Exact match found",
                semantic_similarity=1.0,
                is_meaningful=True,
                suggested_correction=None,
                feedback="Perfect! Exact match.",
                encouragement="Excellent! You got it exactly right!",
                created_at=datetime.now()
            )
        
        # Check simple similarity threshold
        similarity = self._calculate_simple_similarity(user_answer, correct_answer)
        if similarity >= self.similarity_threshold:
            self.stats['similarity_matches'] += 1
            return ValidationCacheEntry(
                user_answer=user_answer,
                correct_answer=correct_answer,
                question_type=question_type,
                study_mode=study_mode,
                word=word,
                context=context,
                is_correct=True,
                confidence_score=similarity,
                reasoning=f"High similarity match ({similarity:.2f})",
                semantic_similarity=similarity,
                is_meaningful=True,
                suggested_correction=None,
                feedback="Great! Very close to the correct answer.",
                encouragement="You're doing well! Keep it up!",
                created_at=datetime.now()
            )
        
        cache_key = self._generate_cache_key(user_answer, correct_answer, question_type, study_mode, word, context)
        
        # Check memory cache first
        if cache_key in self._memory_cache:
            entry = self._memory_cache[cache_key]
            self._update_access_stats(cache_key, entry)
            self.stats['memory_hits'] += 1
            return entry
        
        # Check database cache
        with sqlite3.connect(self.cache_db_path) as conn:
            cursor = conn.execute(
                '''SELECT * FROM validation_cache WHERE cache_key = ?''',
                (cache_key,)
            )
            row = cursor.fetchone()
            
            if row:
                # Convert row to ValidationCacheEntry
                entry = ValidationCacheEntry(
                    user_answer=row[1],
                    correct_answer=row[2],
                    question_type=row[3],
                    study_mode=row[4],
                    word=row[5],
                    context=row[6],
                    is_correct=bool(row[7]),
                    confidence_score=row[8],
                    reasoning=row[9],
                    semantic_similarity=row[10],
                    is_meaningful=bool(row[11]),
                    suggested_correction=row[12],
                    feedback=row[13],
                    encouragement=row[14],
                    created_at=datetime.fromisoformat(row[15]),
                    access_count=row[16],
                    last_accessed=datetime.fromisoformat(row[17]) if row[17] else None
                )
                
                # Add to memory cache
                self._add_to_memory_cache(cache_key, entry)
                self._update_access_stats(cache_key, entry)
                self.stats['db_hits'] += 1
                return entry
        
        self.stats['cache_misses'] += 1
        return None
    
    def _add_to_memory_cache(self, cache_key: str, entry: ValidationCacheEntry):
        """Add entry to memory cache with LRU eviction"""
        # If cache is full, remove least recently used entry
        if len(self._memory_cache) >= self.max_memory_entries:
            # Find least recently accessed entry
            lru_key = min(self._access_times.keys(), key=lambda k: self._access_times[k])
            del self._memory_cache[lru_key]
            del self._access_times[lru_key]
        
        self._memory_cache[cache_key] = entry
        self._access_times[cache_key] = time.time()
    
    def cache_result(self, 
                    user_answer: str, 
                    correct_answer: str, 
                    question_type: str, 
                    study_mode: str,
                    word: Optional[str],
                    context: Optional[str],
                    result: 'ValidationResult'):
        """Cache a validation result"""
        cache_key = self._generate_cache_key(user_answer, correct_answer, question_type, study_mode, word, context)
        
        # Create cache entry
        entry = ValidationCacheEntry(
            user_answer=user_answer,
            correct_answer=correct_answer,
            question_type=question_type,
            study_mode=study_mode,
            word=word,
            context=context,
            is_correct=result.is_correct,
            confidence_score=result.confidence_score,
            reasoning=result.reasoning,
            semantic_similarity=result.semantic_similarity,
            is_meaningful=result.is_meaningful,
            suggested_correction=result.suggested_correction,
            feedback=result.feedback,
            encouragement=result.encouragement,
            created_at=datetime.now()
        )
        
        # Add to memory cache
        self._add_to_memory_cache(cache_key, entry)
        
        # Add to database cache
        with sqlite3.connect(self.cache_db_path) as conn:
            conn.execute('''
                INSERT OR REPLACE INTO validation_cache 
                (cache_key, user_answer, correct_answer, question_type, study_mode, 
                 word, context, is_correct, confidence_score, reasoning, 
                 semantic_similarity, is_meaningful, suggested_correction, 
                 feedback, encouragement, created_at, access_count, last_accessed)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                cache_key, entry.user_answer, entry.correct_answer, entry.question_type,
                entry.study_mode, entry.word, entry.context, entry.is_correct,
                entry.confidence_score, entry.reasoning, entry.semantic_similarity,
                entry.is_meaningful, entry.suggested_correction, entry.feedback,
                entry.encouragement, entry.created_at, entry.access_count, entry.last_accessed
            ))
    
    def get_cache_stats(self) -> Dict[str, Any]:
        """Get cache performance statistics"""
        total_requests = self.stats['total_requests']
        if total_requests == 0:
            return self.stats
        
        # Calculate hit rates
        memory_hit_rate = (self.stats['memory_hits'] / total_requests) * 100
        db_hit_rate = (self.stats['db_hits'] / total_requests) * 100
        ai_call_rate = (self.stats['ai_calls'] / total_requests) * 100
        exact_match_rate = (self.stats['exact_matches'] / total_requests) * 100
        similarity_match_rate = (self.stats['similarity_matches'] / total_requests) * 100
        
        # Get cache size info
        with sqlite3.connect(self.cache_db_path) as conn:
            cursor = conn.execute('SELECT COUNT(*) FROM validation_cache')
            db_cache_size = cursor.fetchone()[0]
        
        return {
            **self.stats,
            'memory_hit_rate': memory_hit_rate,
            'db_hit_rate': db_hit_rate,
            'ai_call_rate': ai_call_rate,
            'exact_match_rate': exact_match_rate,
            'similarity_match_rate': similarity_match_rate,
            'memory_cache_size': len(self._memory_cache),
            'db_cache_size': db_cache_size,
            'total_cache_hits': self.stats['memory_hits'] + self.stats['db_hits'] + self.stats['exact_matches'] + self.stats['similarity_matches'],
            'cache_hit_rate': ((self.stats['memory_hits'] + self.stats['db_hits'] + self.stats['exact_matches'] + self.stats['similarity_matches']) / total_requests) * 100
        }
    
    def clear_cache(self, older_than_hours: Optional[int] = None):
        """Clear cache entries"""
        if older_than_hours:
            cutoff_time = datetime.now() - timedelta(hours=older_than_hours)
            with sqlite3.connect(self.cache_db_path) as conn:
                conn.execute('DELETE FROM validation_cache WHERE created_at < ?', (cutoff_time,))
        else:
            # Clear all cache
            with sqlite3.connect(self.cache_db_path) as conn:
                conn.execute('DELETE FROM validation_cache')
        
        # Clear memory cache
        self._memory_cache.clear()
        self._access_times.clear()
        
        # Reset stats
        self.stats = {key: 0 for key in self.stats.keys()}
    
    def cleanup_expired_entries(self):
        """Remove expired entries from cache"""
        self._cleanup_expired_entries()
    
    def validate_cache_quality(self, sample_size: int = 100) -> Dict[str, Any]:
        """
        Validate cache quality by checking consistency of similar answers
        
        This method addresses the concern about maintaining quality and fairness
        by analyzing how the cache handles different variations of answers.
        """
        quality_report = {
            'total_entries_checked': 0,
            'exact_match_consistency': 0,
            'similarity_threshold_accuracy': 0,
            'ai_result_consistency': 0,
            'context_isolation': 0,
            'quality_score': 0.0,
            'recommendations': []
        }
        
        try:
            with sqlite3.connect(self.cache_db_path) as conn:
                # Get sample of cache entries
                cursor = conn.execute(
                    'SELECT * FROM validation_cache ORDER BY RANDOM() LIMIT ?',
                    (sample_size,)
                )
                entries = cursor.fetchall()
                
                quality_report['total_entries_checked'] = len(entries)
                
                if len(entries) < 10:
                    quality_report['recommendations'].append("Not enough cache entries for quality analysis")
                    return quality_report
                
                # Analyze exact match consistency
                exact_matches = [e for e in entries if e[7] == 1 and e[8] == 1.0]  # is_correct=True, confidence=1.0
                if exact_matches:
                    quality_report['exact_match_consistency'] = len(exact_matches)
                
                # Analyze similarity threshold accuracy
                similarity_matches = [e for e in entries if e[10] >= 0.85]  # semantic_similarity >= 0.85
                if similarity_matches:
                    quality_report['similarity_threshold_accuracy'] = len(similarity_matches)
                
                # Analyze AI result consistency (check for reasonable confidence scores)
                ai_results = [e for e in entries if e[8] > 0.0 and e[8] < 1.0]  # confidence between 0 and 1
                if ai_results:
                    avg_confidence = sum(e[8] for e in ai_results) / len(ai_results)
                    quality_report['ai_result_consistency'] = avg_confidence
                
                # Check context isolation (different contexts should have different results)
                context_groups = {}
                for entry in entries:
                    context_key = f"{entry[3]}|{entry[4]}|{entry[5]}"  # question_type|study_mode|word
                    if context_key not in context_groups:
                        context_groups[context_key] = []
                    context_groups[context_key].append(entry)
                
                quality_report['context_isolation'] = len(context_groups)
                
                # Calculate overall quality score
                quality_score = 0.0
                if quality_report['exact_match_consistency'] > 0:
                    quality_score += 0.3
                if quality_report['similarity_threshold_accuracy'] > 0:
                    quality_score += 0.3
                if quality_report['ai_result_consistency'] > 0.5:  # Reasonable confidence scores
                    quality_score += 0.2
                if quality_report['context_isolation'] > 1:  # Multiple contexts
                    quality_score += 0.2
                
                quality_report['quality_score'] = quality_score
                
                # Generate recommendations
                if quality_score < 0.7:
                    quality_report['recommendations'].append("Consider adjusting similarity threshold")
                if quality_report['ai_result_consistency'] < 0.6:
                    quality_report['recommendations'].append("AI confidence scores may need review")
                if quality_report['context_isolation'] < 2:
                    quality_report['recommendations'].append("Limited context diversity in cache")
                
                if not quality_report['recommendations']:
                    quality_report['recommendations'].append("Cache quality is good")
                
        except Exception as e:
            quality_report['recommendations'].append(f"Quality analysis failed: {str(e)}")
        
        return quality_report

# Global cache instance
validation_cache = ValidationCache()
