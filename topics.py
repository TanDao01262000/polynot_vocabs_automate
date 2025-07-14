from models import TopicList
from typing import Dict, List

# Comprehensive topic lists organized by categories
TOPIC_CATEGORIES = {
    "daily_life": [
        "shopping", "food", "family", "home", "work", "school", "transportation",
        "health", "entertainment", "sports", "hobbies", "relationships", "communication"
    ],
    
    "business_professional": [
        "business", "marketing", "finance", "management", "entrepreneurship", 
        "corporate culture", "negotiation", "sales", "customer service", "project management",
        "leadership", "teamwork", "presentation", "meetings", "networking"
    ],
    
    "academic_education": [
        "education", "learning methods", "academic subjects", "study skills", 
        "research", "teaching", "student life", "university", "library", "exams",
        "writing", "reading", "mathematics", "science", "history", "literature"
    ],
    
    "technology_digital": [
        "technology", "software", "hardware", "programming", "digital communication",
        "artificial intelligence", "cybersecurity", "social media", "e-commerce",
        "mobile apps", "cloud computing", "data science", "web development"
    ],
    
    "travel_tourism": [
        "travel", "transportation", "accommodation", "tourism", "destinations",
        "travel planning", "cultural experiences", "airports", "hotels", "restaurants",
        "sightseeing", "adventure", "vacation", "backpacking", "business travel"
    ],
    
    "health_wellness": [
        "health", "medical care", "fitness", "mental health", "nutrition", 
        "wellness", "preventive care", "exercise", "diet", "meditation",
        "therapy", "pharmacy", "hospital", "doctor", "emergency"
    ],
    
    "entertainment_media": [
        "entertainment", "movies", "music", "gaming", "performing arts", 
        "media", "leisure activities", "television", "books", "theater",
        "concerts", "festivals", "art", "photography", "dance"
    ],
    
    "sports_fitness": [
        "sports", "team sports", "individual sports", "fitness training",
        "competition", "athletic performance", "gym", "yoga", "running",
        "swimming", "cycling", "tennis", "football", "basketball"
    ],
    
    "social_relationships": [
        "relationships", "friendship", "dating", "marriage", "parenting",
        "social media", "communication", "conflict resolution", "empathy",
        "networking", "community", "social events", "parties", "celebrations"
    ],
    
    "environment_nature": [
        "environment", "nature", "climate change", "sustainability", "recycling",
        "wildlife", "plants", "weather", "geography", "oceans", "mountains",
        "forests", "parks", "gardening", "outdoor activities"
    ]
}

def get_topic_list(category: str = None) -> List[str]:
    """Get topics from a specific category or all topics"""
    if category and category in TOPIC_CATEGORIES:
        return TOPIC_CATEGORIES[category]
    else:
        # Return all topics from all categories
        all_topics = []
        for topics in TOPIC_CATEGORIES.values():
            all_topics.extend(topics)
        return all_topics

def get_categories() -> List[str]:
    """Get all available categories"""
    return list(TOPIC_CATEGORIES.keys())

def get_topics_by_category(category: str) -> TopicList:
    """Get topics for a specific category as a TopicList object"""
    if category not in TOPIC_CATEGORIES:
        raise ValueError(f"Category '{category}' not found. Available categories: {get_categories()}")
    
    return TopicList(
        topics=TOPIC_CATEGORIES[category],
        description=f"Topics related to {category.replace('_', ' ')}"
    )

if __name__ == "__main__":
    print("Available categories:")
    for category in get_categories():
        print(f"- {category}")
    
    print("\nDaily life topics:")
    daily_topics = get_topic_list("daily_life")
    for topic in daily_topics:
        print(f"- {topic}") 