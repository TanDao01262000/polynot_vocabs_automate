#!/usr/bin/env python3
"""
AI Vocabulary Generator - Main Application
Examples and test cases for vocabulary generation
"""

from vocab_agent import (
    run_single_topic_generation, 
    run_continuous_vocab_generation, 
    view_saved_topic_lists
)
from models import CEFRLevel

def main():
    """Main function with various examples"""
    
    print("AI Vocabulary Generator - Examples")
    print("=" * 50)
    
    # Example 1: Single topic generation (not saved to topic_lists)
    print("\n=== Example 1: Single Topic Generation ===")
    run_single_topic_generation(
        topic="technology",
        level=CEFRLevel.B2,
        vocab_per_batch=12,
        phrasal_verbs_per_batch=6,
        idioms_per_batch=4
    )
    
    # Example 2: Single topic with saving to topic_lists
    print("\n=== Example 2: Single Topic (Saved to Topic Lists) ===")
    run_single_topic_generation(
        topic="shopping",
        level=CEFRLevel.A2,
        save_topic_list=True,
        topic_list_name="my_shopping_topic"
    )
    
    # Example 3: Generate for a specific category (not saved)
    print("\n=== Example 3: Category-based Generation ===")
    run_continuous_vocab_generation(
        category="daily_life",
        level=CEFRLevel.A2,
        vocab_per_batch=8,
        phrasal_verbs_per_batch=4,
        idioms_per_batch=3,
        delay_seconds=2
    )
    
    # Example 4: Generate for custom topics and save the list
    print("\n=== Example 4: Custom Topics (Saved) ===")
    run_continuous_vocab_generation(
        topics=["gameshow", "video game", "music"],
        level=CEFRLevel.B1,
        vocab_per_batch=15,
        phrasal_verbs_per_batch=3,
        idioms_per_batch=2,
        delay_seconds=1,
        save_topic_list=True,  # Save this custom list
        topic_list_name="my_custom_list"
    )
    
    # Example 5: View all saved topic lists
    print("\n=== Example 5: View Saved Topic Lists ===")
    view_saved_topic_lists()
    
    # Example 6: Advanced example with different language settings
    print("\n=== Example 6: Advanced Settings ===")
    run_single_topic_generation(
        topic="business",
        level=CEFRLevel.C1,
        language_to_learn="Vietnamese",
        learners_native_language="English",
        vocab_per_batch=20,
        phrasal_verbs_per_batch=8,
        idioms_per_batch=6,
        delay_seconds=1,
        save_topic_list=True,
        topic_list_name="business_advanced"
    )

def quick_test():
    """Quick test function for basic functionality"""
    print("Quick Test - Basic Functionality")
    print("=" * 40)
    
    # Simple single topic test
    run_single_topic_generation(
        topic="food",
        level=CEFRLevel.A1,
        vocab_per_batch=5,
        phrasal_verbs_per_batch=2,
        idioms_per_batch=1,
        delay_seconds=1
    )

def view_database():
    """View database contents"""
    print("Database Contents")
    print("=" * 30)
    
    # View saved topic lists
    view_saved_topic_lists()

if __name__ == "__main__":
    import sys
    
    if len(sys.argv) > 1:
        command = sys.argv[1].lower()
        
        if command == "test":
            quick_test()
        elif command == "view":
            view_database()
        elif command == "help":
            print("Available commands:")
            print("  python main.py          - Run all examples")
            print("  python main.py test     - Quick test")
            print("  python main.py view     - View database contents")
            print("  python main.py help     - Show this help")
        else:
            print(f"Unknown command: {command}")
            print("Use 'python main.py help' for available commands")
    else:
        # Run main examples
        main()
