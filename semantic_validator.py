"""
AI-Powered Semantic Answer Validation for Flashcard System
This module provides intelligent answer validation using OpenAI's GPT models
to understand semantic meaning rather than just string matching.
"""

from typing import Dict, Any, Optional, Tuple
from langchain_openai import ChatOpenAI
from pydantic import BaseModel
from config import Config
import json
import re

class ValidationResult(BaseModel):
    """Result of semantic answer validation"""
    is_correct: bool
    confidence_score: float  # 0.0 to 1.0
    reasoning: str
    semantic_similarity: float  # 0.0 to 1.0
    is_meaningful: bool  # Whether the answer has semantic meaning
    suggested_correction: Optional[str] = None

class SemanticValidator:
    """AI-powered semantic answer validator for flashcard system"""
    
    def __init__(self):
        """Initialize the semantic validator with OpenAI model"""
        self.llm = ChatOpenAI(
            model=Config.LLM_MODEL,
            temperature=0.1,  # Low temperature for consistent validation
            api_key=Config.OPENAI_API_KEY
        )
    
    def validate_answer(self, 
                       user_answer: str, 
                       correct_answer: str, 
                       question_type: str = "definition",
                       study_mode: str = "practice",
                       word: Optional[str] = None,
                       context: Optional[str] = None) -> ValidationResult:
        """
        Validate a user's answer using AI-powered semantic analysis
        
        Args:
            user_answer: The user's answer
            correct_answer: The correct answer
            question_type: Type of question (definition, word, translation, etc.)
            study_mode: The study mode (practice, review, write, etc.)
            word: The vocabulary word being tested (for context)
            context: Additional context about the question
        
        Returns:
            ValidationResult with detailed analysis
        """
        
        if not user_answer or not correct_answer:
            return ValidationResult(
                is_correct=False,
                confidence_score=0.0,
                reasoning="Empty answer provided",
                semantic_similarity=0.0,
                is_meaningful=False
            )
        
        # Clean inputs
        user_answer = user_answer.strip()
        correct_answer = correct_answer.strip()
        
        # First check for exact matches (fast path)
        if user_answer.lower() == correct_answer.lower():
            return ValidationResult(
                is_correct=True,
                confidence_score=1.0,
                reasoning="Exact match found",
                semantic_similarity=1.0,
                is_meaningful=True
            )
        
        # Use AI for semantic validation
        return self._ai_semantic_validation(
            user_answer, correct_answer, question_type, study_mode, word, context
        )
    
    def _ai_semantic_validation(self, 
                               user_answer: str, 
                               correct_answer: str, 
                               question_type: str,
                               study_mode: str,
                               word: Optional[str],
                               context: Optional[str]) -> ValidationResult:
        """Perform AI-powered semantic validation"""
        
        # Build context for the AI
        context_info = ""
        if word:
            context_info += f"Vocabulary word: {word}\n"
        if context:
            context_info += f"Additional context: {context}\n"
        
        # Create the validation prompt
        prompt = f"""You are an expert language teacher evaluating a student's answer. Your task is to determine if the student's answer is semantically correct, even if it's not word-for-word identical to the expected answer.

{context_info}
Question type: {question_type}
Study mode: {study_mode}

Expected answer: "{correct_answer}"
Student's answer: "{user_answer}"

Please analyze the student's answer and provide a detailed evaluation. Consider:

1. **Semantic Correctness**: Does the student's answer convey the same meaning as the expected answer?
2. **Meaningfulness**: Does the student's answer make sense and show understanding?
3. **Relevance**: Is the answer relevant to the question being asked?
4. **Language Quality**: Is the answer grammatically correct and well-formed?

For each criterion, provide a score from 0.0 to 1.0, where:
- 1.0 = Perfect/Excellent
- 0.8-0.9 = Very good with minor issues
- 0.6-0.7 = Good with some issues
- 0.4-0.5 = Acceptable but with significant issues
- 0.2-0.3 = Poor but shows some understanding
- 0.0-0.1 = Incorrect or meaningless

Respond in JSON format:
{{
    "is_correct": true/false,
    "confidence_score": 0.0-1.0,
    "reasoning": "Detailed explanation of your evaluation",
    "semantic_similarity": 0.0-1.0,
    "is_meaningful": true/false,
    "suggested_correction": "If incorrect, suggest a better answer (or null if correct)"
}}

Guidelines:
- Be generous with semantic correctness - accept different ways of expressing the same meaning
- Penalize meaningless or nonsensical answers heavily
- Consider cultural and linguistic variations
- Focus on understanding rather than memorization
- If the answer is partially correct, provide a confidence score between 0.0 and 1.0
"""

        try:
            # Get AI response
            response = self.llm.invoke(prompt)
            response_text = response.content.strip()
            
            # Parse JSON response
            try:
                # Extract JSON from response (in case there's extra text)
                json_match = re.search(r'\{.*\}', response_text, re.DOTALL)
                if json_match:
                    json_text = json_match.group()
                    result_data = json.loads(json_text)
                else:
                    raise ValueError("No JSON found in response")
                
                # Validate and create result
                return ValidationResult(
                    is_correct=bool(result_data.get("is_correct", False)),
                    confidence_score=float(result_data.get("confidence_score", 0.0)),
                    reasoning=str(result_data.get("reasoning", "No reasoning provided")),
                    semantic_similarity=float(result_data.get("semantic_similarity", 0.0)),
                    is_meaningful=bool(result_data.get("is_meaningful", False)),
                    suggested_correction=result_data.get("suggested_correction")
                )
                
            except (json.JSONDecodeError, ValueError, KeyError) as e:
                # Fallback to basic validation if AI response is malformed
                print(f"Error parsing AI response: {e}")
                return self._fallback_validation(user_answer, correct_answer)
                
        except Exception as e:
            print(f"Error in AI semantic validation: {e}")
            return self._fallback_validation(user_answer, correct_answer)
    
    def _fallback_validation(self, user_answer: str, correct_answer: str) -> ValidationResult:
        """Fallback validation when AI is unavailable"""
        
        user_lower = user_answer.lower().strip()
        correct_lower = correct_answer.lower().strip()
        
        # Basic similarity check
        if user_lower == correct_lower:
            return ValidationResult(
                is_correct=True,
                confidence_score=1.0,
                reasoning="Exact match (fallback validation)",
                semantic_similarity=1.0,
                is_meaningful=True
            )
        
        # Check for partial matches
        user_words = set(user_lower.split())
        correct_words = set(correct_lower.split())
        
        if user_words and correct_words:
            overlap = len(user_words.intersection(correct_words))
            similarity = overlap / max(len(user_words), len(correct_words))
            
            if similarity > 0.5:
                return ValidationResult(
                    is_correct=True,
                    confidence_score=similarity,
                    reasoning=f"Partial match with {similarity:.2f} similarity (fallback)",
                    semantic_similarity=similarity,
                    is_meaningful=True
                )
        
        return ValidationResult(
            is_correct=False,
            confidence_score=0.0,
            reasoning="No significant similarity found (fallback validation)",
            semantic_similarity=0.0,
            is_meaningful=len(user_answer.strip()) > 0
        )

# Global instance
semantic_validator = SemanticValidator()
