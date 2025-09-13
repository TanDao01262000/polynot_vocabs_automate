"""
AI-Powered Semantic Answer Validation for Flashcard System
This module provides intelligent answer validation using OpenAI's GPT models
to understand semantic meaning rather than just string matching.
Now includes intelligent caching to reduce API costs and improve performance.
"""

from typing import Dict, Any, Optional, Tuple
from langchain_openai import ChatOpenAI
from pydantic import BaseModel
from config import Config
from validation_cache import validation_cache, ValidationCacheEntry
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
    feedback: Optional[str] = None  # Constructive feedback for learning
    encouragement: Optional[str] = None  # Positive reinforcement

class SemanticValidator:
    """AI-powered semantic answer validator for flashcard system"""
    
    def __init__(self, confidence_threshold: float = 0.55):
        """Initialize the semantic validator with OpenAI model"""
        self.llm = ChatOpenAI(
            model=Config.LLM_MODEL,
            temperature=0.1,  # Low temperature for consistent validation
            api_key=Config.OPENAI_API_KEY
        )
        self.confidence_threshold = confidence_threshold
    
    def validate_answer(self, 
                       user_answer: str, 
                       correct_answer: str, 
                       question_type: str = "definition",
                       study_mode: str = "practice",
                       word: Optional[str] = None,
                       context: Optional[str] = None) -> ValidationResult:
        """
        Validate a user's answer using AI-powered semantic analysis with intelligent caching
        
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
        
        # Check cache first (includes exact match and similarity checks)
        cached_result = validation_cache.get_cached_result(
            user_answer, correct_answer, question_type, study_mode, word, context
        )
        
        if cached_result:
            # Convert cached entry to ValidationResult
            return ValidationResult(
                is_correct=cached_result.is_correct,
                confidence_score=cached_result.confidence_score,
                reasoning=cached_result.reasoning,
                semantic_similarity=cached_result.semantic_similarity,
                is_meaningful=cached_result.is_meaningful,
                suggested_correction=cached_result.suggested_correction,
                feedback=cached_result.feedback,
                encouragement=cached_result.encouragement
            )
        
        # If not in cache, use AI for semantic validation
        result = self._ai_semantic_validation(
            user_answer, correct_answer, question_type, study_mode, word, context
        )
        
        # Cache the result for future use
        validation_cache.cache_result(
            user_answer, correct_answer, question_type, study_mode, word, context, result
        )
        
        # Update AI call statistics
        validation_cache.stats['ai_calls'] += 1
        
        return result
    
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

Please analyze the student's answer in TWO STEPS:

STEP 1 - MEANING EVALUATION (Primary):
1. **Core Understanding**: Does the student demonstrate understanding of the key concepts?
2. **Semantic Correctness**: Does the student's answer convey the same essential meaning as the expected answer?
3. **Meaningfulness**: Does the student's answer make sense and show comprehension?
4. **Relevance**: Is the answer relevant to the question being asked?

STEP 2 - GRAMMAR/COMPLETENESS (Secondary):
1. **Grammar**: Are there minor grammatical issues (missing articles, prepositions, etc.)?
2. **Completeness**: Are there missing words that don't affect core meaning?

IMPORTANT: 
- PRIORITIZE MEANING over grammar - if the core concept is understood, the answer should be considered correct
- Accept answers that convey the essential meaning even if they omit minor words like "to", "the", "a", "light", etc.
- Focus on whether the student understands the concept, not on perfect wording
- Grammar issues should only reduce confidence, not make the answer incorrect
- BE GENEROUS: If the student shows understanding of the core concept, mark as correct even with confidence as low as 0.6
- Accept "furniture for sleeping" as equivalent to "a piece of furniture for sleeping on"
- Accept "furniture for sleep" as equivalent to "a piece of furniture for sleeping on"
- Accept missing articles, prepositions, and minor grammatical errors if the meaning is clear

FEEDBACK GUIDELINES:
- For correct answers: Provide encouragement and explain why it's good
- For partially correct answers: Acknowledge what's right, then gently guide toward improvement
- For incorrect answers: Be supportive and explain the concept clearly
- Always be encouraging and constructive, never harsh or critical
- Help the student understand the concept better
- Provide specific, actionable feedback when possible

FEEDBACK EXAMPLES:
- "You're close! You understand the main idea, but try to include..."
- "Great start! You've got the right concept, now let's add..."
- "I can see you understand this! To make it even better, consider..."
- "You're on the right track! The key thing to remember is..."
- "Excellent! You've captured the essence perfectly. Keep it up!"
- "Good thinking! You understand the concept well. For extra clarity..."

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
    "suggested_correction": "If incorrect, suggest a better answer (or null if correct)",
    "feedback": "Constructive feedback to help the student learn and improve",
    "encouragement": "Positive reinforcement or encouragement for the student"
}}

Guidelines:
- Be generous with semantic correctness - accept different ways of expressing the same meaning
- Accept degree modifiers (very, extremely, super, really, quite) as equivalent to base words
- Accept idiomatic expressions that mean the same thing (e.g., "piece of cake" = "very easy")
- Accept synonyms and paraphrases that convey the same concept
- Accept minor grammatical differences (e.g., "on the sky" vs "in the sky")
- Accept answers that convey the core meaning even if they omit minor details
- Accept implied meanings (e.g., "shines" implies "bright")
- Accept answers that are factually correct even if not perfectly worded
- Penalize meaningless or nonsensical answers heavily
- Consider cultural and linguistic variations
- Focus on understanding rather than memorization
- If the answer is partially correct, provide a confidence score between 0.0 and 1.0

Examples of acceptable semantic equivalences:
- "piece of cake" = "very easy" = "easy" = "simple" = "effortless"
- "walk in the park" = "breeze" = "no problem" = "child's play"
- "very difficult" = "hard" = "challenging" = "tough"
- "extremely happy" = "very happy" = "happy" = "joyful"
- "twinkling" = "shine with flickering" = "to shine with a flickering light" (missing words like "to" and "light" are acceptable if core meaning is clear)
- "object on the sky and shines" = "bright object in the sky and shines at night" (both describe stars)
- "try to be better and get higher achievements" = "aim high and try to achieve great things"
"""

        try:
            # Get AI response with retry logic
            max_retries = 3
            for attempt in range(max_retries):
                try:
                    response = self.llm.invoke(prompt)
                    response_text = response.content.strip()
                    break
                except Exception as e:
                    if attempt == max_retries - 1:
                        print(f"AI validation failed after {max_retries} attempts: {e}")
                        raise ValueError(f"AI validation service unavailable: {e}")
                    print(f"AI validation attempt {attempt + 1} failed, retrying...")
                    import time
                    time.sleep(1)  # Brief delay before retry
                    continue
            
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
                ai_is_correct = bool(result_data.get("is_correct", False))
                confidence_score = float(result_data.get("confidence_score", 0.0))
                is_meaningful = bool(result_data.get("is_meaningful", False))
                
                # Apply confidence threshold: if confidence is above threshold and answer is meaningful, mark as correct
                final_is_correct = ai_is_correct or (confidence_score >= self.confidence_threshold and is_meaningful)
                
                # If we're overriding the AI decision due to threshold, update reasoning
                reasoning = str(result_data.get("reasoning", "No reasoning provided"))
                if not ai_is_correct and final_is_correct:
                    reasoning += f"\n\n✅ Threshold Override: Answer marked as correct due to {confidence_score:.2f} confidence (≥{self.confidence_threshold:.2f} threshold) and meaningful content."
                
                return ValidationResult(
                    is_correct=final_is_correct,
                    confidence_score=confidence_score,
                    reasoning=reasoning,
                    semantic_similarity=float(result_data.get("semantic_similarity", 0.0)),
                    is_meaningful=is_meaningful,
                    suggested_correction=result_data.get("suggested_correction"),
                    feedback=result_data.get("feedback"),
                    encouragement=result_data.get("encouragement")
                )
                
            except (json.JSONDecodeError, ValueError, KeyError) as e:
                # AI response is malformed - this is a critical error
                print(f"Error parsing AI response: {e}")
                print(f"Raw response: {response_text[:200]}...")
                raise ValueError(f"AI validation failed - malformed response: {e}")
                
        except Exception as e:
            print(f"Error in AI semantic validation: {e}")
            raise ValueError(f"AI validation failed: {e}")
    
    def get_cache_stats(self) -> Dict[str, Any]:
        """Get cache performance statistics"""
        return validation_cache.get_cache_stats()
    
    def clear_cache(self, older_than_hours: Optional[int] = None):
        """Clear validation cache"""
        validation_cache.clear_cache(older_than_hours)
    
    def cleanup_expired_cache(self):
        """Remove expired entries from cache"""
        validation_cache.cleanup_expired_entries()
    
    def validate_cache_quality(self, sample_size: int = 100) -> Dict[str, Any]:
        """
        Validate cache quality to ensure fairness and accuracy
        
        This method addresses concerns about maintaining quality by analyzing:
        1. Consistency of exact matches
        2. Accuracy of similarity thresholds
        3. Reasonableness of AI confidence scores
        4. Proper context isolation
        """
        return validation_cache.validate_cache_quality(sample_size)

# Global instance with 55% confidence threshold
semantic_validator = SemanticValidator(confidence_threshold=0.55)
