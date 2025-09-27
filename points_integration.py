#!/usr/bin/env python3
"""
Points Integration Module for AI Vocab and Flashcard Systems
Integrates with social API for points awarding
"""

import requests
import json
from typing import Dict, Any, Optional
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class PointsIntegration:
    """Points integration for AI Vocab and Flashcard servers"""
    
    def __init__(self, social_api_url: str = "http://localhost:8000"):
        self.social_api_url = social_api_url
        self.timeout = 10
        self.enabled = True  # Can be disabled for testing
    
    def award_points(self, user_name: str, points: int, reason: str, 
                    activity_type: str, **metadata) -> Dict[str, Any]:
        """
        Award points to a user
        
        Args:
            user_name: Username of the user
            points: Number of points to award
            reason: Description of why points are awarded
            activity_type: Type of activity (ai_vocab, flashcard, etc.)
            **metadata: Additional metadata about the activity
        
        Returns:
            API response with points awarded
        """
        
        if not self.enabled:
            logger.info(f"Points integration disabled - would award {points} points to {user_name}")
            return {"success": True, "disabled": True, "points": points}
        
        payload = {
            "points": points,
            "reason": reason,
            "activity_type": activity_type,
            "metadata": metadata
        }
        
        try:
            response = requests.post(
                f"{self.social_api_url}/social/users/{user_name}/points",
                json=payload,
                timeout=self.timeout
            )
            
            if response.status_code == 200:
                result = response.json()
                logger.info(f"Points awarded successfully: {points} to {user_name}")
                return result
            else:
                logger.error(f"Failed to award points: HTTP {response.status_code}: {response.text}")
                return {
                    "success": False, 
                    "error": f"HTTP {response.status_code}: {response.text}"
                }
                
        except requests.exceptions.RequestException as e:
            logger.error(f"Request failed for points awarding: {e}")
            return {"success": False, "error": f"Request failed: {e}"}
        except Exception as e:
            logger.error(f"Unexpected error in points awarding: {e}")
            return {"success": False, "error": f"Unexpected error: {e}"}
    
    def get_user_points(self, user_name: str) -> Dict[str, Any]:
        """Get user's current points and level"""
        try:
            response = requests.get(
                f"{self.social_api_url}/social/users/{user_name}/points",
                timeout=self.timeout
            )
            
            if response.status_code == 200:
                return response.json()
            else:
                return {"error": f"HTTP {response.status_code}: {response.text}"}
                
        except Exception as e:
            return {"error": str(e)}
    
    def get_leaderboard(self, user_name: Optional[str] = None, limit: int = 20) -> Dict[str, Any]:
        """Get current leaderboard"""
        try:
            params = {"limit": limit}
            if user_name:
                params["user_name"] = user_name
                
            response = requests.get(
                f"{self.social_api_url}/social/leaderboard",
                params=params,
                timeout=self.timeout
            )
            
            if response.status_code == 200:
                return response.json()
            else:
                return {"error": f"HTTP {response.status_code}: {response.text}"}
                
        except Exception as e:
            return {"error": str(e)}

# AI Vocab System Integration
class AIVocabPoints:
    """Points integration for AI Vocab System"""
    
    def __init__(self, social_api_url: str = "http://localhost:8000"):
        self.integration = PointsIntegration(social_api_url)
    
    def award_vocab_generation_points(self, user_name: str, words_generated: int, 
                                    level: str, session_duration: int = 0) -> Dict[str, Any]:
        """Award points for AI vocabulary generation"""
        
        # Calculate points based on level and words
        points = self._calculate_vocab_points(words_generated, level)
        
        reason = f"AI generated {words_generated} new {level} vocabulary words"
        
        return self.integration.award_points(
            user_name=user_name,
            points=points,
            reason=reason,
            activity_type="ai_vocab_generation",
            words_generated=words_generated,
            level=level,
            session_duration=session_duration,
            system="ai_vocab"
        )
    
    def award_pronunciation_points(self, user_name: str, level: str, 
                                 practice_duration: int) -> Dict[str, Any]:
        """Award points for AI pronunciation practice"""
        
        points = self._calculate_pronunciation_points(level, practice_duration)
        
        reason = f"AI pronunciation practice for {practice_duration} minutes"
        
        return self.integration.award_points(
            user_name=user_name,
            points=points,
            reason=reason,
            activity_type="ai_pronunciation",
            level=level,
            practice_duration=practice_duration,
            system="ai_pronunciation"
        )
    
    def _calculate_vocab_points(self, words_generated: int, level: str) -> int:
        """Calculate points for vocabulary generation"""
        base_points = {
            "A1": 15,
            "A2": 20,
            "B1": 25,
            "B2": 30,
            "C1": 40
        }
        
        multiplier = {
            "A1": 1.0,
            "A2": 1.2,
            "B1": 1.5,
            "B2": 1.8,
            "C1": 2.0
        }
        
        base = base_points.get(level, 20)
        mult = multiplier.get(level, 1.0)
        
        # Bonus for more words
        word_bonus = min(words_generated - 10, 20) * 0.5
        
        return int((base + word_bonus) * mult)
    
    def _calculate_pronunciation_points(self, level: str, duration: int) -> int:
        """Calculate points for pronunciation practice"""
        base_points = {
            "A1": 10,
            "A2": 15,
            "B1": 20,
            "B2": 25,
            "C1": 30
        }
        
        base = base_points.get(level, 15)
        duration_bonus = min(duration, 30) * 0.5
        
        return int(base + duration_bonus)

# Flashcard System Integration
class FlashcardPoints:
    """Points integration for Flashcard System"""
    
    def __init__(self, social_api_url: str = "http://localhost:8000"):
        self.integration = PointsIntegration(social_api_url)
    
    def award_flashcard_review_points(self, user_name: str, cards_reviewed: int,
                                    difficulty: str, mastery_achieved: bool = False,
                                    streak_days: int = 0) -> Dict[str, Any]:
        """Award points for flashcard review"""
        
        points = self._calculate_flashcard_points(cards_reviewed, difficulty, 
                                                 mastery_achieved, streak_days)
        
        reason = f"Reviewed {cards_reviewed} {difficulty} flashcards"
        if mastery_achieved:
            reason += " (Mastery achieved!)"
        
        return self.integration.award_points(
            user_name=user_name,
            points=points,
            reason=reason,
            activity_type="flashcard_review",
            cards_reviewed=cards_reviewed,
            difficulty=difficulty,
            mastery_achieved=mastery_achieved,
            streak_days=streak_days,
            system="flashcard"
        )
    
    def award_spaced_repetition_points(self, user_name: str, cards_reviewed: int,
                                     retention_rate: float) -> Dict[str, Any]:
        """Award points for spaced repetition"""
        
        points = self._calculate_spaced_repetition_points(cards_reviewed, retention_rate)
        
        reason = f"Spaced repetition: {cards_reviewed} cards, {retention_rate:.1%} retention"
        
        return self.integration.award_points(
            user_name=user_name,
            points=points,
            reason=reason,
            activity_type="spaced_repetition",
            cards_reviewed=cards_reviewed,
            retention_rate=retention_rate,
            system="flashcard"
        )
    
    def _calculate_flashcard_points(self, cards_reviewed: int, difficulty: str,
                                  mastery_achieved: bool, streak_days: int) -> int:
        """Calculate points for flashcard activities"""
        
        difficulty_multipliers = {
            "easy": 1.0,
            "medium": 1.2,
            "hard": 1.5,
            "expert": 2.0
        }
        
        base_points = min(cards_reviewed, 25)  # Cap at 25 cards
        multiplier = difficulty_multipliers.get(difficulty, 1.0)
        
        total_points = int(base_points * multiplier)
        
        # Add bonuses
        if mastery_achieved:
            total_points += 25
        
        if streak_days >= 7:
            total_points += 20
        elif streak_days >= 3:
            total_points += 10
        
        return total_points
    
    def _calculate_spaced_repetition_points(self, cards_reviewed: int, 
                                          retention_rate: float) -> int:
        """Calculate points for spaced repetition"""
        
        base_points = cards_reviewed * 1.5
        
        # Bonus for high retention rate
        if retention_rate >= 0.8:
            base_points += 15
        elif retention_rate >= 0.6:
            base_points += 10
        
        return int(base_points)

# Global instances for easy import
vocab_points = AIVocabPoints()
flashcard_points = FlashcardPoints()
