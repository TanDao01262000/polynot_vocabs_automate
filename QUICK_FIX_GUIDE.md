# 🚀 Quick Fix Guide for Pronunciation System

## 🔧 Issues Found & Solutions

### 1. **Google TTS Authentication** ❌
**Problem:** Google TTS needs a service account JSON file, not just an API key.

**Solution:**
1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Navigate to your project: `polynot-tts-472121`
3. Go to **IAM & Admin** → **Service Accounts**
4. Create a new service account or use existing one
5. Download the JSON key file
6. Update your `.env` file:

```bash
# Replace with the path to your downloaded JSON file
GOOGLE_APPLICATION_CREDENTIALS=/path/to/your/service-account-key.json

# Remove or comment out the old API key
# GOOGLE_TTS_API_KEY=AIzaSyBBWpBF4SE7uj0C8F5AOjp_Cq7bfzFGT9g
```

### 2. **Database Tables Missing** ❌
**Problem:** TTS tables not created in database.

**Solution:**
```bash
# Run the database setup script
python scripts/setup_tts_tables.py
```

### 3. **Supabase Storage Bucket Missing** ❌
**Problem:** No audio files bucket in Supabase Storage.

**Solution:**
1. Go to your Supabase dashboard
2. Navigate to **Storage**
3. Create a new bucket named `audio-files`
4. Set it as **Public**
5. Add this policy:

```sql
-- Allow authenticated users to upload files
CREATE POLICY "Allow authenticated users to upload audio files" ON storage.objects
FOR INSERT WITH CHECK (bucket_id = 'audio-files' AND auth.role() = 'authenticated');

-- Allow public access to read files
CREATE POLICY "Allow public access to audio files" ON storage.objects
FOR SELECT USING (bucket_id = 'audio-files');
```

### 4. **RLS Policies Blocking Access** ❌
**Problem:** Row Level Security policies preventing database operations.

**Solution:**
Run this SQL in your Supabase SQL editor:

```sql
-- Fix RLS policies for TTS tables
ALTER TABLE vocab_pronunciations ENABLE ROW LEVEL SECURITY;
ALTER TABLE audio_files ENABLE ROW LEVEL SECURITY;
ALTER TABLE user_subscriptions ENABLE ROW LEVEL SECURITY;
ALTER TABLE user_voice_profiles ENABLE ROW LEVEL SECURITY;
ALTER TABLE tts_usage ENABLE ROW LEVEL SECURITY;

-- Allow authenticated users to manage their own data
CREATE POLICY "Users can manage their own pronunciations" ON vocab_pronunciations
FOR ALL USING (auth.uid()::text = user_id);

CREATE POLICY "Users can manage their own audio files" ON audio_files
FOR ALL USING (auth.uid()::text = user_id);

CREATE POLICY "Users can manage their own subscriptions" ON user_subscriptions
FOR ALL USING (auth.uid()::text = user_id);

CREATE POLICY "Users can manage their own voice profiles" ON user_voice_profiles
FOR ALL USING (auth.uid()::text = user_id);

CREATE POLICY "Users can manage their own TTS usage" ON tts_usage
FOR ALL USING (auth.uid()::text = user_id);
```

## 🧪 **Test After Fixes**

1. **Update your .env file** with the service account JSON path
2. **Run database setup:**
   ```bash
   python scripts/setup_tts_tables.py
   ```
3. **Create Supabase Storage bucket** and policies
4. **Test the system:**
   ```bash
   python tests/fix_pronunciation_issues.py
   ```

## 📋 **Expected Results After Fixes**

✅ Google TTS initialized successfully  
✅ Database tables created  
✅ Supabase Storage bucket accessible  
✅ Pronunciation generation working  
✅ Audio files saved to database and storage  

## 🆘 **Still Having Issues?**

If you're still having problems:

1. **Check your .env file** - make sure paths are correct
2. **Verify Supabase connection** - test with a simple query
3. **Check Google Cloud permissions** - ensure TTS API is enabled
4. **Run the debug script** to see specific error messages

## 🎯 **Quick Test Command**

```bash
# Activate virtual environment
source .venv/bin/activate

# Run the fix script
python tests/fix_pronunciation_issues.py
```

This will show you exactly what's working and what needs to be fixed!
