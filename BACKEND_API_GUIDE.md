# 🚀 AI Vocabulary Generator - Backend API Guide for Frontend Developers

## 📋 Table of Contents
1. [Authentication](#authentication)
2. [Base URL & Headers](#base-url--headers)
3. [Core Features](#core-features)
4. [API Endpoints](#api-endpoints)
5. [Request/Response Examples](#requestresponse-examples)
6. [Error Handling](#error-handling)

---

## 🔐 Authentication

**All endpoints require authentication via Authorization header:**
```http
Authorization: Bearer <user_id>
```

**Note:** Currently using simple user ID authentication. Replace `<user_id>` with actual user identifier.

---

## 🌐 Base URL & Headers

**Base URL:** `http://localhost:8001` (Development)  
**Production URL:** `https://your-production-domain.com`

**Required Headers:**
```http
Content-Type: application/json
Authorization: Bearer <user_id>
```

---

## ✨ Core Features

### 🎯 **1. Vocabulary Generation**
- Single topic generation
- Multiple topics generation  
- Category-based generation
- Custom topic lists

### 📚 **2. User Vocabulary Management**
- Save vocabulary to personal collection
- Create custom vocabulary lists
- Favorite/unfavorite words
- Hide/show words
- Add personal notes
- Rate difficulty (1-5 scale)
- Mark as reviewed

### 🎴 **3. Advanced Flashcard System**
- Multiple study modes (review, practice, test, etc.)
- Session management with progress tracking
- Analytics and statistics
- Spaced repetition algorithm
- Difficulty-based card selection

### 📖 **4. Topic & Category System**
- 10+ categories (daily_life, business, technology, etc.)
- 145+ topics
- Hierarchical organization

---

## 🔌 API Endpoints

### 🏠 **Root Endpoints**

#### GET `/`
**Description:** API information and version  
**Headers:** None required  
**Response:**
```json
{
  "message": "AI Vocabulary Generator API",
  "version": "11.0.0",
  "status": "running"
}
```

#### GET `/health`
**Description:** Health check  
**Headers:** None required  
**Response:**
```json
{
  "status": "healthy",
  "timestamp": "2025-08-02T16:00:00.000Z"
}
```

---

### 🎯 **Generation Endpoints**

#### POST `/generate/single`
**Description:** Generate vocabulary for a single topic  
**Request Body:**
```json
{
  "topic": "technology",
  "level": "B2",
  "language_to_learn": "English",
  "learners_native_language": "Spanish",
  "vocab_per_batch": 10,
  "phrasal_verbs_per_batch": 5,
  "idioms_per_batch": 3,
  "delay_seconds": 1,
  "save_topic_list": true,
  "topic_list_name": "My Tech Vocab"
}
```

**Response:**
```json
{
  "success": true,
  "message": "Vocabulary generated successfully",
  "data": {
    "vocabularies": [
      {
        "word": "artificial intelligence",
        "definition": "The simulation of human intelligence in machines",
        "translation": "inteligencia artificial",
        "example": "AI is transforming healthcare.",
        "example_translation": "La IA está transformando la atención médica.",
        "level": "B2",
        "part_of_speech": "noun"
      }
    ],
    "phrasal_verbs": [...],
    "idioms": [...],
    "total_generated": 18,
    "topic_list_id": "uuid-here"
  }
}
```

#### POST `/generate/multiple`
**Description:** Generate vocabulary for multiple topics  
**Request Body:**
```json
{
  "topics": ["technology", "business", "health"],
  "level": "B1",
  "language_to_learn": "English",
  "learners_native_language": "Spanish",
  "vocab_per_batch": 8,
  "phrasal_verbs_per_batch": 4,
  "idioms_per_batch": 2,
  "delay_seconds": 1
}
```

#### POST `/generate/category`
**Description:** Generate vocabulary for all topics in a category  
**Request Body:**
```json
{
  "category": "daily_life",
  "level": "A2",
  "language_to_learn": "English",
  "learners_native_language": "Spanish",
  "vocab_per_batch": 6,
  "phrasal_verbs_per_batch": 3,
  "idioms_per_batch": 2,
  "delay_seconds": 1
}
```

---

### 📚 **User Vocabulary Management**

#### GET `/vocab/list`
**Description:** Get user's vocabulary with filters  
**Query Parameters:**
```
?topic=technology&level=B2&limit=20&offset=0&show_hidden=false
```

**Response:**
```json
{
  "success": true,
  "message": "Vocabulary retrieved successfully",
  "data": {
    "vocabularies": [
      {
        "id": "uuid-here",
        "word": "algorithm",
        "definition": "A set of rules or instructions",
        "translation": "algoritmo",
        "example": "The search algorithm is very efficient.",
        "example_translation": "El algoritmo de búsqueda es muy eficiente.",
        "level": "B2",
        "part_of_speech": "noun",
        "topic_name": "technology",
        "is_favorite": false,
        "is_hidden": false,
        "review_count": 0,
        "last_reviewed": null,
        "difficulty_rating": null,
        "personal_notes": null,
        "created_at": "2025-01-02T10:00:00Z"
      }
    ],
    "total_count": 150,
    "has_more": true
  }
}
```

#### POST `/vocab/save-to-user`
**Description:** Save vocabulary entry to user's collection  
**Request Body:**
```json
{
  "word": "blockchain",
  "definition": "A distributed ledger technology",
  "translation": "cadena de bloques",
  "example": "Bitcoin uses blockchain technology.",
  "example_translation": "Bitcoin usa tecnología de cadena de bloques.",
  "level": "B2",
  "part_of_speech": "noun",
  "topic_name": "technology"
}
```

**Response:**
```json
{
  "success": true,
  "message": "Vocabulary saved successfully",
  "vocab_entry_id": "uuid-here"
}
```

#### POST `/vocab/favorite`
**Description:** Toggle favorite status of vocabulary  
**Request Body:**
```json
{
  "vocab_entry_id": "uuid-here"
}
```

#### POST `/vocab/hide`
**Description:** Hide vocabulary entry  
**Request Body:**
```json
{
  "vocab_entry_id": "uuid-here"
}
```

#### POST `/vocab/note`
**Description:** Add personal note to vocabulary  
**Request Body:**
```json
{
  "vocab_entry_id": "uuid-here",
  "value": "This word is tricky to remember"
}
```

#### POST `/vocab/rate`
**Description:** Rate vocabulary difficulty (1-5)  
**Request Body:**
```json
{
  "vocab_entry_id": "uuid-here",
  "value": "3"
}
```

#### POST `/vocab/review`
**Description:** Mark vocabulary as reviewed  
**Request Body:**
```json
{
  "vocab_entry_id": "uuid-here"
}
```

---

### 📋 **Vocabulary Lists Management**

#### POST `/vocab/lists`
**Description:** Create a new vocabulary list  
**Request Body:**
```json
{
  "list_name": "My Business Vocabulary",
  "description": "Important business terms for meetings",
  "is_public": false
}
```

**Response:**
```json
{
  "success": true,
  "message": "Vocabulary list created successfully",
  "list_id": "uuid-here"
}
```

#### GET `/vocab/lists`
**Description:** Get all user's vocabulary lists  
**Response:**
```json
{
  "success": true,
  "message": "Retrieved 3 vocabulary lists",
  "lists": [
    {
      "id": "uuid-here",
      "list_name": "My Business Vocabulary",
      "description": "Important business terms",
      "is_public": false,
      "vocab_count": 25,
      "created_at": "2025-01-02T10:00:00Z"
    }
  ]
}
```

#### POST `/vocab/lists/{list_id}/add`
**Description:** Add vocabulary to a list  
**Request Body:**
```json
{
  "vocab_entry_id": "uuid-here"
}
```

#### DELETE `/vocab/lists/{list_id}/remove`
**Description:** Remove vocabulary from a list  
**Request Body:**
```json
{
  "vocab_entry_id": "uuid-here"
}
```

---

### 🎴 **Flashcard System**

#### GET `/flashcard/study-modes`
**Description:** Get available study modes  
**Response:**
```json
{
  "success": true,
  "study_modes": [
    {
      "value": "review",
      "name": "Review Mode",
      "description": "Show definition, guess the word"
    },
    {
      "value": "practice",
      "name": "Practice Mode", 
      "description": "Show word, guess the definition"
    },
    {
      "value": "test",
      "name": "Test Mode",
      "description": "Multiple choice questions"
    },
    {
      "value": "write",
      "name": "Writing Mode",
      "description": "Type the word from definition"
    },
    {
      "value": "listen",
      "name": "Listening Mode",
      "description": "Listen and identify the word"
    }
  ]
}
```

#### GET `/flashcard/session-types`
**Description:** Get available session types  
**Response:**
```json
{
  "success": true,
  "session_types": [
    {
      "value": "daily_review",
      "name": "Daily Review",
      "description": "Review overdue and new cards"
    },
    {
      "value": "topic_focus",
      "name": "Topic Focus",
      "description": "Focus on specific topic vocabulary"
    },
    {
      "value": "level_progression",
      "name": "Level Progression",
      "description": "Progressive difficulty levels"
    }
  ]
}
```

#### GET `/flashcard/difficulty-ratings`
**Description:** Get available difficulty ratings  
**Response:**
```json
{
  "success": true,
  "difficulty_ratings": [
    {
      "value": "easy",
      "name": "Easy",
      "description": "I knew this well"
    },
    {
      "value": "medium", 
      "name": "Medium",
      "description": "I knew this but took some time"
    },
    {
      "value": "hard",
      "name": "Hard",
      "description": "I struggled with this"
    },
    {
      "value": "again",
      "name": "Again",
      "description": "I need to review this again soon"
    }
  ]
}
```

#### POST `/flashcard/session/create`
**Description:** Create a new flashcard session  
**Request Body:**
```json
{
  "session_name": "Daily Review Session",
  "session_type": "daily_review",
  "study_mode": "mixed",
  "topic_name": "technology",
  "category_name": null,
  "level": "B2",
  "max_cards": 20,
  "time_limit_minutes": 15,
  "include_reviewed": false,
  "include_favorites": true,
  "difficulty_filter": ["easy", "medium"],
  "smart_selection": true
}
```

**Response:**
```json
{
  "success": true,
  "session_id": "uuid-here",
  "session_name": "Daily Review Session",
  "total_cards": 15,
  "study_mode": "mixed",
  "session_type": "daily_review"
}
```

#### GET `/flashcard/session/{session_id}/current`
**Description:** Get current card in session  
**Response:**
```json
{
  "success": true,
  "card": {
    "vocab_entry_id": "uuid-here",
    "word": "algorithm",
    "definition": "A set of rules or instructions",
    "translation": "algoritmo",
    "example": "The search algorithm is efficient.",
    "example_translation": "El algoritmo de búsqueda es eficiente.",
    "part_of_speech": "noun",
    "level": "B2",
    "card_index": 1,
    "total_cards": 15
  }
}
```

#### POST `/flashcard/session/{session_id}/answer`
**Description:** Submit answer for current card  
**Request Body:**
```json
{
  "vocab_entry_id": "uuid-here",
  "user_answer": "algorithm",
  "response_time_seconds": 3.5,
  "hints_used": 0,
  "confidence_level": 0.8,
  "difficulty_rating": "easy"
}
```

**Response:**
```json
{
  "success": true,
  "correct": true,
  "confidence_score": 0.95,
  "session_complete": false,
  "next_card_available": true,
  "session_stats": {
    "correct_answers": 8,
    "incorrect_answers": 2,
    "cards_remaining": 5
  }
}
```

#### GET `/flashcard/stats`
**Description:** Get user's flashcard statistics  
**Response:**
```json
{
  "total_sessions": 25,
  "cards_studied": 150,
  "accuracy_percentage": 78.5,
  "current_streak": 7,
  "longest_streak": 15,
  "favorite_study_mode": "practice",
  "average_session_duration": 12.5
}
```

#### GET `/flashcard/analytics`
**Description:** Get flashcard analytics  
**Query Parameters:** `?days=30`

**Response:**
```json
{
  "period_days": 30,
  "total_sessions": 25,
  "cards_studied": 150,
  "accuracy_percentage": 78.5,
  "improvement_trend": "positive",
  "study_time_minutes": 312,
  "most_studied_topics": ["technology", "business"],
  "difficulty_breakdown": {
    "easy": 45,
    "medium": 80,
    "hard": 25
  }
}
```

#### GET `/flashcard/sessions`
**Description:** Get user's flashcard sessions  
**Query Parameters:** `?limit=50`

**Response:**
```json
{
  "success": true,
  "sessions": [
    {
      "id": "uuid-here",
      "session_name": "Daily Review",
      "session_type": "daily_review",
      "study_mode": "mixed",
      "total_cards": 15,
      "correct_answers": 12,
      "accuracy_percentage": 80.0,
      "duration_minutes": 8.5,
      "created_at": "2025-01-02T10:00:00Z",
      "is_active": false
    }
  ]
}
```

#### DELETE `/flashcard/session/{session_id}`
**Description:** Delete a flashcard session  
**Response:**
```json
{
  "success": true,
  "message": "Session deleted successfully"
}
```

---

### 📖 **Topics & Categories**

#### GET `/categories`
**Description:** Get all available categories  
**Response:**
```json
{
  "success": true,
  "categories": [
    {
      "name": "daily_life",
      "display_name": "Daily Life",
      "description": "Everyday vocabulary and expressions",
      "topic_count": 25
    },
    {
      "name": "business",
      "display_name": "Business",
      "description": "Professional and business terminology",
      "topic_count": 18
    }
  ]
}
```

#### GET `/topics/{category}`
**Description:** Get topics for a specific category  
**Response:**
```json
{
  "success": true,
  "category": "daily_life",
  "topics": [
    {
      "name": "shopping",
      "display_name": "Shopping",
      "description": "Shopping and retail vocabulary"
    },
    {
      "name": "cooking",
      "display_name": "Cooking",
      "description": "Kitchen and cooking terminology"
    }
  ]
}
```

#### GET `/topics`
**Description:** Get all available topics  
**Response:**
```json
{
  "success": true,
  "topics": [
    {
      "name": "technology",
      "display_name": "Technology",
      "description": "Modern technology vocabulary",
      "category": "business"
    }
  ]
}
```

---

## ❌ Error Handling

### Standard Error Response Format:
```json
{
  "detail": "Error message description"
}
```

### Common HTTP Status Codes:
- **200**: Success
- **400**: Bad Request (invalid parameters)
- **401**: Unauthorized (missing/invalid auth)
- **404**: Not Found (resource doesn't exist)
- **500**: Internal Server Error

### Example Error Responses:

#### 400 Bad Request:
```json
{
  "detail": "Rating value is required"
}
```

#### 401 Unauthorized:
```json
{
  "detail": "Authorization header required"
}
```

#### 404 Not Found:
```json
{
  "detail": "Session not found"
}
```

#### 500 Internal Server Error:
```json
{
  "detail": "Failed to create flashcard session: Database connection error"
}
```

---

## 🚀 Frontend Integration Tips

### 1. **Authentication Flow**
```javascript
// Set user ID in headers for all requests
const headers = {
  'Content-Type': 'application/json',
  'Authorization': `Bearer ${userId}`
};
```

### 2. **Error Handling**
```javascript
try {
  const response = await fetch('/api/endpoint', {
    method: 'POST',
    headers: headers,
    body: JSON.stringify(requestData)
  });
  
  if (!response.ok) {
    const error = await response.json();
    throw new Error(error.detail);
  }
  
  const data = await response.json();
  return data;
} catch (error) {
  console.error('API Error:', error.message);
  // Handle error in UI
}
```

### 3. **Flashcard Session Flow**
```javascript
// 1. Create session
const session = await createFlashcardSession(sessionRequest);

// 2. Get current card
const card = await getCurrentCard(session.session_id);

// 3. Submit answer
const result = await submitAnswer(session.session_id, answerRequest);

// 4. Continue until session complete
if (result.session_complete) {
  // Show session results
}
```

### 4. **Real-time Updates**
Consider implementing WebSocket connections for:
- Live flashcard session updates
- Real-time vocabulary generation progress
- Session statistics updates

---

## 📱 Mobile App Considerations

### **Offline Support**
- Cache user vocabulary locally
- Store flashcard sessions for offline review
- Sync when connection restored

### **Performance Optimization**
- Implement pagination for large vocabulary lists
- Use lazy loading for flashcard sessions
- Cache frequently accessed data (categories, topics)

### **User Experience**
- Show loading states during vocabulary generation
- Implement progress indicators for flashcard sessions
- Provide offline mode indicators

---

## 🔧 Development & Testing

### **Testing Endpoints**
Use the `/test/*` endpoints for development:
- `POST /test/create-user` - Create test user
- `GET /vocab/test-list` - List test vocabulary
- `POST /vocab/test-save` - Save test vocabulary

### **API Documentation**
- Interactive docs: `http://localhost:8001/docs`
- ReDoc: `http://localhost:8001/redoc`

---

## 📞 Support

For API issues or questions:
1. Check the interactive documentation at `/docs`
2. Review error responses for specific details
3. Test with the provided test endpoints
4. Contact the backend development team

---

**Last Updated:** January 2, 2025  
**API Version:** 11.0.0

