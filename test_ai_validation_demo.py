#!/usr/bin/env python3
"""
Demo script to showcase the AI-powered semantic answer validation with intelligent caching
This demonstrates how the new system correctly handles different types of answers
and shows the performance benefits of the caching system.
"""

import sys
sys.path.append('.')
from supabase_database import SupabaseVocabDatabase
from models import FlashcardAnswerRequest, DifficultyRating
from semantic_validator import semantic_validator
import time

def test_answer_validation():
    """Test various answer scenarios to demonstrate AI validation with caching"""
    
    print("🧠 AI-Powered Semantic Answer Validation Demo with Intelligent Caching")
    print("=" * 80)
    print("This demo shows how the new AI system correctly evaluates answers")
    print("based on semantic meaning rather than just string matching.")
    print("It also demonstrates the performance benefits of intelligent caching.\n")
    
    # Initialize database
    db = SupabaseVocabDatabase()
    
    # Clear cache to start fresh
    print("🧹 Clearing cache to start fresh...")
    semantic_validator.clear_cache()
    print("✅ Cache cleared\n")
    
    # Test scenarios
    test_cases = [
        {
            "name": "Exact Match",
            "user_answer": "A piece of furniture for sleeping on",
            "correct_answer": "A piece of furniture for sleeping on",
            "expected": "Should be correct with high confidence"
        },
        {
            "name": "Semantic Equivalent",
            "user_answer": "Furniture used for sleeping",
            "correct_answer": "A piece of furniture for sleeping on",
            "expected": "Should be correct with high confidence"
        },
        {
            "name": "Paraphrase",
            "user_answer": "A bed is furniture where you sleep",
            "correct_answer": "A piece of furniture for sleeping on",
            "expected": "Should be correct with high confidence"
        },
        {
            "name": "Partially Correct",
            "user_answer": "Furniture for sleeping",
            "correct_answer": "A piece of furniture for sleeping on",
            "expected": "Should be correct with good confidence"
        },
        {
            "name": "Meaningless Answer",
            "user_answer": "asdfghjkl qwerty",
            "correct_answer": "A piece of furniture for sleeping on",
            "expected": "Should be incorrect with very low confidence"
        },
        {
            "name": "Random Words",
            "user_answer": "purple monkey dishwasher",
            "correct_answer": "A piece of furniture for sleeping on",
            "expected": "Should be incorrect with very low confidence"
        },
        {
            "name": "Wrong but Related",
            "user_answer": "A chair for sitting on",
            "correct_answer": "A piece of furniture for sleeping on",
            "expected": "Should be incorrect but with some confidence (furniture context)"
        }
    ]
    
    print("Testing various answer scenarios (First Pass - Cache Misses Expected):\n")
    
    start_time = time.time()
    
    for i, test_case in enumerate(test_cases, 1):
        print(f"Test {i}: {test_case['name']}")
        print(f"Expected: {test_case['expected']}")
        print(f"User Answer: '{test_case['user_answer']}'")
        print(f"Correct Answer: '{test_case['correct_answer']}'")
        
        # Test the validation
        is_correct, confidence, reasoning = db._validate_answer(
            user_answer=test_case['user_answer'],
            correct_answer=test_case['correct_answer'],
            study_mode='practice',
            word='bed',
            context='Word: bed, Definition: A piece of furniture for sleeping on'
        )
        
        print(f"Result: {'✅ CORRECT' if is_correct else '❌ INCORRECT'}")
        print(f"Confidence: {confidence:.2f}")
        print(f"Reasoning: {reasoning}")
        print("-" * 60)
        
        # Small delay to avoid rate limiting
        time.sleep(0.5)
    
    first_pass_time = time.time() - start_time
    
    # Show cache stats after first pass
    print("\n📊 Cache Statistics After First Pass:")
    cache_stats = semantic_validator.get_cache_stats()
    print(f"Total Requests: {cache_stats['total_requests']}")
    print(f"AI Calls Made: {cache_stats['ai_calls']}")
    print(f"Cache Hit Rate: {cache_stats['cache_hit_rate']:.1f}%")
    print(f"Exact Matches: {cache_stats['exact_matches']}")
    print(f"Similarity Matches: {cache_stats['similarity_matches']}")
    print(f"Memory Cache Size: {cache_stats['memory_cache_size']}")
    print(f"Database Cache Size: {cache_stats['db_cache_size']}")
    
    print(f"\n⏱️  First Pass Time: {first_pass_time:.2f} seconds")
    
    # Now test the same cases again to show cache benefits
    print("\n" + "="*80)
    print("🔄 Testing Same Scenarios Again (Second Pass - Cache Hits Expected):")
    print("="*80)
    
    start_time = time.time()
    
    for i, test_case in enumerate(test_cases, 1):
        print(f"Test {i}: {test_case['name']} (Cached)")
        print(f"User Answer: '{test_case['user_answer']}'")
        
        # Test the validation again
        is_correct, confidence, reasoning = db._validate_answer(
            user_answer=test_case['user_answer'],
            correct_answer=test_case['correct_answer'],
            study_mode='practice',
            word='bed',
            context='Word: bed, Definition: A piece of furniture for sleeping on'
        )
        
        print(f"Result: {'✅ CORRECT' if is_correct else '❌ INCORRECT'}")
        print(f"Confidence: {confidence:.2f}")
        print(f"Reasoning: {reasoning[:100]}..." if len(reasoning) > 100 else f"Reasoning: {reasoning}")
        print("-" * 40)
        
        # No delay needed for cached results
        time.sleep(0.1)
    
    second_pass_time = time.time() - start_time
    
    # Show final cache stats
    print("\n📊 Final Cache Statistics:")
    final_cache_stats = semantic_validator.get_cache_stats()
    print(f"Total Requests: {final_cache_stats['total_requests']}")
    print(f"AI Calls Made: {final_cache_stats['ai_calls']}")
    print(f"Cache Hit Rate: {final_cache_stats['cache_hit_rate']:.1f}%")
    print(f"Memory Cache Hits: {final_cache_stats['memory_hits']}")
    print(f"Database Cache Hits: {final_cache_stats['db_hits']}")
    print(f"Exact Matches: {final_cache_stats['exact_matches']}")
    print(f"Similarity Matches: {final_cache_stats['similarity_matches']}")
    
    print(f"\n⏱️  Second Pass Time: {second_pass_time:.2f} seconds")
    print(f"🚀 Speed Improvement: {((first_pass_time - second_pass_time) / first_pass_time * 100):.1f}% faster")
    
    # Calculate cost savings
    ai_calls_saved = final_cache_stats['total_requests'] - final_cache_stats['ai_calls']
    estimated_cost_per_call = 0.01  # $0.01 per AI call
    cost_savings = ai_calls_saved * estimated_cost_per_call
    
    print(f"\n💰 Cost Savings:")
    print(f"AI Calls Saved: {ai_calls_saved}")
    print(f"Estimated Cost Savings: ${cost_savings:.2f}")
    print(f"AI Call Reduction: {(ai_calls_saved / final_cache_stats['total_requests'] * 100):.1f}%")
    
    print("\n🎯 Key Improvements:")
    print("✅ Semantic understanding: Recognizes equivalent meanings")
    print("✅ Meaningless detection: Correctly identifies nonsensical answers")
    print("✅ Partial credit: Gives appropriate scores for partially correct answers")
    print("✅ Context awareness: Considers the vocabulary word being tested")
    print("✅ Detailed reasoning: Provides explanations for validation decisions")
    print("✅ Intelligent caching: Reduces API costs and improves performance")
    print("✅ Multi-layer optimization: Exact match, similarity, and AI validation")
    print("✅ Persistent storage: Results cached across sessions")
    
    print("\n🚀 The flashcard system now provides much more accurate and fair")
    print("   answer validation that focuses on understanding rather than memorization!")
    print("   Plus intelligent caching reduces costs and improves response times!")
    
    print("\n💡 Cache Benefits Demonstrated:")
    print("   • Exact matches are detected instantly without AI calls")
    print("   • High similarity answers are validated without AI calls")
    print("   • AI validation results are cached for future use")
    print("   • Memory cache provides fastest access to frequent validations")
    print("   • Database cache persists across application restarts")
    print("   • Automatic cleanup removes expired entries")

if __name__ == "__main__":
    test_answer_validation()


