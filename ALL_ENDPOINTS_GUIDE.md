# Complete API Endpoints Guide

## Base URL
```
http://localhost:8001
```

## Authentication
Most endpoints require authentication. Include the Bearer token in the Authorization header:
```javascript
headers: {
  "Authorization": "Bearer YOUR_JWT_TOKEN",
  "Content-Type": "application/json"
}
```

---

## 📚 **Documentation Endpoints** (No Auth Required)

### 1. API Documentation
- **GET** `/docs` - Interactive Swagger UI documentation
- **GET** `/redoc` - ReDoc documentation interface
- **GET** `/openapi.json` - OpenAPI specification

---

## 🏥 **Health & System Endpoints**

### 2. Health Check
- **GET** `/health` - System health check
  ```json
  {
    "status": "healthy",
    "timestamp": "2025-08-02T16:00:00.000Z"
  }
  ```

### 3. Root Endpoint
- **GET** `/` - API information and status

---

## 🧪 **Testing Endpoints** (Development Only)

### 4. User Testing
- **POST** `/test/create-user` - Create a test user for testing purposes

### 5. Vocabulary Testing
- **POST** `/vocab/test-save` - Test endpoint to save a sample vocabulary entry
- **GET** `/vocab/test-list` - Test endpoint to list user's saved vocabulary
- **GET** `/vocab/test-list-hidden` - Test endpoint to list vocabulary including hidden items
- **POST** `/vocab/test-review` - Test vocabulary review functionality

### 6. Flashcard Testing
- **POST** `/test/flashcard/session/create` - Create a test flashcard session
- **GET** `/test/flashcard/answer` - Test flashcard answer validation

---

## 🗄️ **Cache Management Endpoints** (Admin/System)

### 7. Cache Statistics
- **GET** `/cache/stats` - Get validation cache performance statistics
  ```json
  {
    "total_entries": 1500,
    "hit_rate": 0.85,
    "miss_rate": 0.15,
    "cache_size_mb": 25.6,
    "last_cleanup": "2024-01-01T00:00:00Z"
  }
  ```

### 8. Cache Operations
- **POST** `/cache/clear` - Clear validation cache entries
  - Query param: `older_than_hours` (optional)
- **POST** `/cache/cleanup` - Remove expired entries from validation cache
- **GET** `/cache/performance` - Get cache performance and cost savings summary
- **GET** `/cache/quality` - Validate cache quality for fairness and accuracy
  - Query param: `sample_size` (default: 100)

---

## 📝 **Vocabulary Generation Endpoints**

### 9. Core Generation
- **POST** `/generate/single` - Generate vocabulary for a single topic
- **POST** `/generate/multiple` - Generate vocabulary for multiple topics
- **POST** `/generate/category` - Generate vocabulary for a category

### 10. Topics & Categories
- **GET** `/categories` - Get all available categories
- **GET** `/topics` - Get all available topics

---

## 👤 **User Vocabulary Management**

### 11. Vocabulary Lists
- **GET** `/vocab/list` - Get user's vocabulary with pagination and filtering
  - Query params: `page`, `limit`, `show_favorites_only`, `show_hidden`, `topic_name`, `category_name`, `level`, `search_term`
- **GET** `/vocab/user-saved` - Get all vocabulary entries saved by the user
- **POST** `/vocab/save-to-user` - Save a vocabulary entry to user's personal list

### 12. Vocabulary Actions
- **POST** `/vocab/favorite` - Mark/unmark vocabulary as favorite
- **POST** `/vocab/hide` - Hide/unhide vocabulary entry
- **POST** `/vocab/hide-toggle` - Toggle hide/unhide status
- **POST** `/vocab/note` - Add/update personal notes
- **POST** `/vocab/rate` - Rate difficulty (1-5 scale)
- **POST** `/vocab/review` - Mark as reviewed/unreviewed

### 13. Vocabulary Lists Management
- **POST** `/vocab/lists` - Create a new vocabulary list
- **GET** `/vocab/lists` - Get user's vocabulary lists
- **POST** `/vocab/lists/{list_id}/add` - Add vocabulary to a list
- **DELETE** `/vocab/lists/{list_id}/remove` - Remove vocabulary from a list
- **DELETE** `/vocab/lists/{list_id}` - Delete a vocabulary list

---

## 🎤 **TTS & Pronunciation Endpoints**

### 14. Core TTS
- **POST** `/tts/generate` - Generate TTS audio for custom text
- **POST** `/tts/generate-vocab/{vocab_entry_id}` - Generate TTS for vocabulary entry

### 15. Pronunciation Management
- **POST** `/tts/pronunciation/generate` - Generate multiple pronunciation versions
- **GET** `/tts/pronunciation/{vocab_entry_id}` - Get existing pronunciations
- **POST** `/tts/pronunciation/ensure/{vocab_entry_id}` - Ensure pronunciations exist
- **POST** `/tts/pronunciation/batch` - Batch generate pronunciations
- **DELETE** `/tts/pronunciation/{vocab_entry_id}` - Delete pronunciations

### 16. Voice Management
- **POST** `/tts/voice-clone` - Create a voice clone
- **GET** `/tts/voice-profiles` - Get user's voice profiles
- **DELETE** `/tts/voice-profiles/{voice_profile_id}` - Delete voice profile

### 17. TTS Subscription & Usage
- **GET** `/tts/subscription` - Get user's subscription information
- **GET** `/tts/quota` - Get TTS usage quota information

---

## 🎭 **Voice Cloning Endpoints**

### 18. Voice Cloning (Separate Router)
- **POST** `/voice-cloning/create-voice-clone` - Create voice clone from audio files
- **GET** `/voice-cloning/status/{voice_id}` - Get voice cloning status
- **DELETE** `/voice-cloning/delete/{voice_id}` - Delete voice clone

---

## 🃏 **Flashcard System Endpoints**

### 19. Flashcard Sessions
- **POST** `/flashcard/session/create` - Create a new flashcard session
- **GET** `/flashcard/session/{session_id}` - Get session details
- **POST** `/flashcard/session/{session_id}/answer` - Submit flashcard answer
- **POST** `/flashcard/session/{session_id}/complete` - Complete session

### 20. Flashcard Analytics
- **GET** `/flashcard/analytics` - Get flashcard analytics
  - Query param: `days` (default: 30)
- **GET** `/flashcard/stats` - Get user's flashcard statistics

---

## 🔍 **Endpoint Categories Summary**

| Prefix | Purpose | Auth Required | Frontend Use |
|--------|---------|---------------|--------------|
| `/docs`, `/redoc` | Documentation | ❌ | Reference only |
| `/health` | System health | ❌ | Health checks |
| `/test/*` | Testing/Development | ✅ | Development only |
| `/cache/*` | Cache management | ❌ | Admin/system use |
| `/generate/*` | Vocabulary generation | ✅ | Core feature |
| `/vocab/*` | User vocabulary | ✅ | Core feature |
| `/tts/*` | Text-to-speech | ✅ | Core feature |
| `/voice-cloning/*` | Voice cloning | ✅ | Premium feature |
| `/flashcard/*` | Flashcard system | ✅ | Study feature |

---

## 🚀 **Frontend Integration Priority**

### **High Priority** (Core Features):
1. **Authentication**: Login/logout endpoints
2. **Vocabulary Generation**: `/generate/single`
3. **Vocabulary Management**: `/vocab/list`, `/vocab/save-to-user`
4. **Pronunciation**: `/tts/pronunciation/generate`, `/tts/pronunciation/{id}`
5. **TTS Generation**: `/tts/generate-vocab/{id}`

### **Medium Priority** (Enhanced Features):
1. **Voice Cloning**: `/voice-cloning/*`
2. **Flashcards**: `/flashcard/*`
3. **User Actions**: `/vocab/favorite`, `/vocab/note`, `/vocab/rate`

### **Low Priority** (Admin/System):
1. **Cache Management**: `/cache/*`
2. **Testing Endpoints**: `/test/*`
3. **Analytics**: `/flashcard/analytics`

---

## ⚠️ **Important Notes**

1. **Testing Endpoints**: Only use in development environment
2. **Cache Endpoints**: Primarily for system administration
3. **Documentation**: Use `/docs` for interactive API exploration
4. **Error Handling**: All endpoints return consistent error formats
5. **Rate Limiting**: TTS endpoints may have usage limits based on subscription

---

## 🔧 **Quick Reference**

```javascript
// Most common frontend calls
const endpoints = {
  // Authentication
  login: 'POST /auth/login',
  
  // Vocabulary
  generateVocab: 'POST /generate/single',
  getVocabList: 'GET /vocab/list',
  saveVocab: 'POST /vocab/save-to-user',
  
  // Pronunciation
  generatePronunciations: 'POST /tts/pronunciation/generate',
  getPronunciations: 'GET /tts/pronunciation/{id}',
  
  // TTS
  generateTTS: 'POST /tts/generate-vocab/{id}',
  
  // Health
  healthCheck: 'GET /health'
};
```

All endpoints are production-ready and fully tested! 🎉
