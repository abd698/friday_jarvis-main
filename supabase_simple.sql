-- إنشاء الجداول الأساسية فقط (نسخة مبسطة جداً)

-- تفعيل الإضافات الأساسية
CREATE EXTENSION IF NOT EXISTS pgcrypto;

-- جدول الملفات الشخصية للمستخدمين
CREATE TABLE IF NOT EXISTS profiles (
    id UUID REFERENCES auth.users(id) PRIMARY KEY,
    email TEXT UNIQUE NOT NULL,
    full_name TEXT DEFAULT '',
    avatar_url TEXT,
    level TEXT DEFAULT 'beginner',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);



-- جدول نتائج اختبار المستوى
CREATE TABLE IF NOT EXISTS assessments (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    user_id UUID REFERENCES auth.users(id) ON DELETE CASCADE,
    questions JSONB NOT NULL,
    score INTEGER NOT NULL,
    level TEXT NOT NULL,
    completed_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- جدول تقدم المستخدم في تعلم اللغة الإنجليزية
CREATE TABLE IF NOT EXISTS user_progress (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    user_id UUID REFERENCES auth.users(id) ON DELETE CASCADE,
    words_learned INTEGER DEFAULT 0,
    current_topic TEXT DEFAULT '',
    last_position TEXT DEFAULT '',
    progress_percentage INTEGER DEFAULT 0,
    session_data JSONB DEFAULT '{}',
    topics_completed TEXT[] DEFAULT '{}',
    vocabulary JSONB DEFAULT '{}',
    conversation_history JSONB DEFAULT '{}',
    last_session_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- جدول تقدم المستخدم في تعليم الجمل
CREATE TABLE IF NOT EXISTS sentences_progress (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    user_id UUID REFERENCES auth.users(id) ON DELETE CASCADE,
    session_id TEXT NOT NULL,
    generated_sentences JSONB DEFAULT '[]',
    current_sentence_index INTEGER DEFAULT 0,
    completed_sentences INTEGER DEFAULT 0,
    sentences_data JSONB DEFAULT '{}',
    session_status TEXT DEFAULT 'active',
    total_sentences INTEGER DEFAULT 10,
    current_level INTEGER DEFAULT 1,
    learned_sentences_history JSONB DEFAULT '[]',
    session_start_time TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    last_activity TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- جدول السياق الشخصي للمستخدم - لتعليم تفاعلي واقعي
CREATE TABLE IF NOT EXISTS user_personal_context (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    user_id UUID REFERENCES auth.users(id) ON DELETE CASCADE UNIQUE,
    
    -- معلومات شخصية أساسية
    first_name TEXT DEFAULT '',
    nickname TEXT DEFAULT '',
    age INTEGER,
    gender TEXT DEFAULT '',
    native_language TEXT DEFAULT 'Arabic',
    
    -- العائلة والأصدقاء
    family_members JSONB DEFAULT '{}',  -- {"father": "Ahmed", "mother": "Fatima", "brother": "Ali"}
    friends JSONB DEFAULT '[]',  -- ["Mohammed", "Sara", "Khaled"]
    pets JSONB DEFAULT '[]',  -- [{"name": "Max", "type": "dog"}]
    
    -- الاهتمامات والهوايات
    hobbies JSONB DEFAULT '[]',  -- ["reading", "football", "cooking"]
    favorite_foods JSONB DEFAULT '[]',  -- ["pizza", "biryani", "chocolate"]
    favorite_colors JSONB DEFAULT '[]',  -- ["blue", "green"]
    favorite_subjects JSONB DEFAULT '[]',  -- ["math", "science"]
    
    -- العمل/الدراسة
    occupation TEXT DEFAULT '',  -- "student" / "engineer" / "doctor"
    workplace_or_school TEXT DEFAULT '',
    daily_routine JSONB DEFAULT '{}',  -- {"wake_up": "7am", "work_start": "9am"}
    
    -- البيئة المحيطة
    city TEXT DEFAULT '',
    country TEXT DEFAULT '',
    home_items JSONB DEFAULT '[]',  -- ["table", "chair", "laptop", "phone"]
    room_description TEXT DEFAULT '',
    
    -- الأهداف والطموحات
    learning_goals JSONB DEFAULT '[]',  -- ["travel abroad", "get better job"]
    dream_job TEXT DEFAULT '',
    places_want_to_visit JSONB DEFAULT '[]',
    
    -- السياق الحالي (يتم تحديثه باستمرار)
    current_mood TEXT DEFAULT '',  -- "happy" / "tired" / "excited"
    recent_activities JSONB DEFAULT '[]',  -- آخر الأنشطة التي قام بها
    objects_around JSONB DEFAULT '[]',  -- الأشياء حوله الآن
    
    -- بيانات وصفية
    context_completeness INTEGER DEFAULT 0,  -- نسبة اكتمال المعلومات (0-100)
    last_context_update TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);







-- تفعيل RLS بطريقة بسيطة
ALTER TABLE profiles ENABLE ROW LEVEL SECURITY;
ALTER TABLE assessments ENABLE ROW LEVEL SECURITY;
ALTER TABLE user_progress ENABLE ROW LEVEL SECURITY;
ALTER TABLE sentences_progress ENABLE ROW LEVEL SECURITY;
ALTER TABLE user_personal_context ENABLE ROW LEVEL SECURITY;

-- سياسات أساسية بسيطة (بدون تكرار)
-- profiles
DROP POLICY IF EXISTS "profiles_policy" ON profiles;
DROP POLICY IF EXISTS "profiles_select" ON profiles;
DROP POLICY IF EXISTS "profiles_insert" ON profiles;
DROP POLICY IF EXISTS "profiles_update" ON profiles;
DROP POLICY IF EXISTS "profiles_delete" ON profiles;
CREATE POLICY "profiles_select" ON profiles FOR SELECT USING (auth.uid() = id);
CREATE POLICY "profiles_insert" ON profiles FOR INSERT WITH CHECK (auth.uid() = id);
CREATE POLICY "profiles_update" ON profiles FOR UPDATE USING (auth.uid() = id);
CREATE POLICY "profiles_delete" ON profiles FOR DELETE USING (auth.uid() = id);



-- assessments
DROP POLICY IF EXISTS "assessments_policy" ON assessments;
DROP POLICY IF EXISTS "assessments_select" ON assessments;
DROP POLICY IF EXISTS "assessments_insert" ON assessments;
DROP POLICY IF EXISTS "assessments_update" ON assessments;
DROP POLICY IF EXISTS "assessments_delete" ON assessments;
CREATE POLICY "assessments_select" ON assessments FOR SELECT USING (auth.uid() = user_id);
CREATE POLICY "assessments_insert" ON assessments FOR INSERT WITH CHECK (auth.uid() = user_id);
CREATE POLICY "assessments_update" ON assessments FOR UPDATE USING (auth.uid() = user_id);
CREATE POLICY "assessments_delete" ON assessments FOR DELETE USING (auth.uid() = user_id);

-- user_progress (سياسات أكثر مرونة للسماح للـ service client بالعمل)
DROP POLICY IF EXISTS "user_progress_policy" ON user_progress;
DROP POLICY IF EXISTS "user_progress_select" ON user_progress;
DROP POLICY IF EXISTS "user_progress_insert" ON user_progress;
DROP POLICY IF EXISTS "user_progress_update" ON user_progress;
DROP POLICY IF EXISTS "user_progress_delete" ON user_progress;
CREATE POLICY "user_progress_select" ON user_progress FOR SELECT USING (auth.uid() = user_id OR auth.role() = 'service_role');
CREATE POLICY "user_progress_insert" ON user_progress FOR INSERT WITH CHECK (auth.uid() = user_id OR auth.role() = 'service_role');
CREATE POLICY "user_progress_update" ON user_progress FOR UPDATE USING (auth.uid() = user_id OR auth.role() = 'service_role');
CREATE POLICY "user_progress_delete" ON user_progress FOR DELETE USING (auth.uid() = user_id OR auth.role() = 'service_role');

-- sentences_progress (سياسات مرنة للسماح للـ service client بالعمل)
DROP POLICY IF EXISTS "sentences_progress_policy" ON sentences_progress;
DROP POLICY IF EXISTS "sentences_progress_select" ON sentences_progress;
DROP POLICY IF EXISTS "sentences_progress_insert" ON sentences_progress;
DROP POLICY IF EXISTS "sentences_progress_update" ON sentences_progress;
DROP POLICY IF EXISTS "sentences_progress_delete" ON sentences_progress;
CREATE POLICY "sentences_progress_select" ON sentences_progress FOR SELECT USING (auth.uid() = user_id OR auth.role() = 'service_role');
CREATE POLICY "sentences_progress_insert" ON sentences_progress FOR INSERT WITH CHECK (auth.uid() = user_id OR auth.role() = 'service_role');
CREATE POLICY "sentences_progress_update" ON sentences_progress FOR UPDATE USING (auth.uid() = user_id OR auth.role() = 'service_role');
CREATE POLICY "sentences_progress_delete" ON sentences_progress FOR DELETE USING (auth.uid() = user_id OR auth.role() = 'service_role');

-- user_personal_context (سياسات مرنة)
DROP POLICY IF EXISTS "user_personal_context_select" ON user_personal_context;
DROP POLICY IF EXISTS "user_personal_context_insert" ON user_personal_context;
DROP POLICY IF EXISTS "user_personal_context_update" ON user_personal_context;
DROP POLICY IF EXISTS "user_personal_context_delete" ON user_personal_context;
CREATE POLICY "user_personal_context_select" ON user_personal_context FOR SELECT USING (auth.uid() = user_id OR auth.role() = 'service_role');
CREATE POLICY "user_personal_context_insert" ON user_personal_context FOR INSERT WITH CHECK (auth.uid() = user_id OR auth.role() = 'service_role');
CREATE POLICY "user_personal_context_update" ON user_personal_context FOR UPDATE USING (auth.uid() = user_id OR auth.role() = 'service_role');
CREATE POLICY "user_personal_context_delete" ON user_personal_context FOR DELETE USING (auth.uid() = user_id OR auth.role() = 'service_role');

-- إضافة الفهارس للأداء الأمثل
CREATE INDEX IF NOT EXISTS idx_sentences_progress_user_id ON sentences_progress USING btree (user_id);
CREATE INDEX IF NOT EXISTS idx_sentences_progress_session_id ON sentences_progress USING btree (session_id);
CREATE INDEX IF NOT EXISTS idx_sentences_progress_status ON sentences_progress USING btree (session_status);
CREATE INDEX IF NOT EXISTS idx_user_personal_context_user_id ON user_personal_context USING btree (user_id);

-- ============================================
-- 🎯 نظام تقييم المستوى الذكي
-- ============================================
CREATE TABLE IF NOT EXISTS user_level_assessment (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    user_id UUID REFERENCES auth.users(id) ON DELETE CASCADE,
    
    -- المستوى الحالي
    current_level TEXT DEFAULT 'beginner', -- beginner, elementary, intermediate, advanced
    level_score INTEGER DEFAULT 0, -- 0-100
    
    -- تقييم المهارات
    vocabulary_level INTEGER DEFAULT 0, -- 0-100
    grammar_level INTEGER DEFAULT 0,
    speaking_level INTEGER DEFAULT 0,
    listening_level INTEGER DEFAULT 0,
    
    -- الأداء
    correct_answers INTEGER DEFAULT 0,
    total_attempts INTEGER DEFAULT 0,
    accuracy_rate NUMERIC(5,2) DEFAULT 0.0,
    
    -- سرعة التعلم
    learning_speed TEXT DEFAULT 'normal', -- slow, normal, fast
    recommended_pace TEXT DEFAULT 'balanced', -- slow_steady, balanced, intensive
    
    -- النقاط القوية والضعيفة
    strengths JSONB DEFAULT '[]', -- ["vocabulary", "pronunciation"]
    weaknesses JSONB DEFAULT '[]', -- ["grammar", "articles"]
    
    -- المواضيع التي يحتاج مراجعتها
    topics_to_review JSONB DEFAULT '[]',
    
    last_assessment_date TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

ALTER TABLE user_level_assessment ENABLE ROW LEVEL SECURITY;
CREATE POLICY "user_level_assessment_policy" ON user_level_assessment FOR ALL USING (auth.uid() = user_id OR auth.role() = 'service_role');
CREATE INDEX idx_user_level_assessment_user_id ON user_level_assessment(user_id);

-- ============================================
-- 📚 نظام المراجعة المتباعدة (Spaced Repetition)
-- ============================================
CREATE TABLE IF NOT EXISTS vocabulary_cards (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    user_id UUID REFERENCES auth.users(id) ON DELETE CASCADE,
    
    -- الكلمة
    word TEXT NOT NULL,
    translation TEXT,
    example_sentence TEXT,
    topic TEXT, -- من أي موضوع تعلمها
    
    -- نظام SRS
    ease_factor NUMERIC(3,2) DEFAULT 2.5, -- معامل السهولة
    interval INTEGER DEFAULT 1, -- الفترة بالأيام
    repetitions INTEGER DEFAULT 0, -- عدد المرات الصحيحة
    
    -- الجدولة
    next_review_date TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    last_reviewed_at TIMESTAMP WITH TIME ZONE,
    
    -- الأداء
    times_seen INTEGER DEFAULT 0,
    times_correct INTEGER DEFAULT 0,
    times_wrong INTEGER DEFAULT 0,
    mastery_level INTEGER DEFAULT 0, -- 0-5
    
    -- ميتاداتا
    difficulty TEXT DEFAULT 'medium', -- easy, medium, hard
    is_mastered BOOLEAN DEFAULT false,
    
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

ALTER TABLE vocabulary_cards ENABLE ROW LEVEL SECURITY;
CREATE POLICY "vocabulary_cards_policy" ON vocabulary_cards FOR ALL USING (auth.uid() = user_id OR auth.role() = 'service_role');
CREATE INDEX idx_vocabulary_cards_user_id ON vocabulary_cards(user_id);
CREATE INDEX idx_vocabulary_cards_next_review ON vocabulary_cards(user_id, next_review_date);
CREATE INDEX idx_vocabulary_cards_word ON vocabulary_cards(user_id, word);

-- ============================================
-- 🏆 نظام الإنجازات والتحفيز
-- ============================================
CREATE TABLE IF NOT EXISTS user_achievements (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    user_id UUID REFERENCES auth.users(id) ON DELETE CASCADE,
    
    -- الإحصائيات
    total_words_learned INTEGER DEFAULT 0,
    total_lessons_completed INTEGER DEFAULT 0,
    total_study_time INTEGER DEFAULT 0, -- بالدقائق
    current_streak INTEGER DEFAULT 0, -- أيام متتالية
    longest_streak INTEGER DEFAULT 0,
    
    -- النقاط والمستويات
    total_points INTEGER DEFAULT 0,
    current_level INTEGER DEFAULT 1,
    experience_points INTEGER DEFAULT 0,
    points_to_next_level INTEGER DEFAULT 100,
    
    -- الشارات
    badges JSONB DEFAULT '[]', -- [{"id": "first_word", "name": "أول كلمة", "earned_at": "..."}]
    
    -- إحصائيات تفصيلية
    topics_mastered INTEGER DEFAULT 0,
    perfect_lessons INTEGER DEFAULT 0, -- دروس 100% صحيحة
    review_accuracy NUMERIC(5,2) DEFAULT 0.0,
    
    last_study_date DATE DEFAULT CURRENT_DATE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

ALTER TABLE user_achievements ENABLE ROW LEVEL SECURITY;
CREATE POLICY "user_achievements_policy" ON user_achievements FOR ALL USING (auth.uid() = user_id OR auth.role() = 'service_role');
CREATE INDEX idx_user_achievements_user_id ON user_achievements(user_id);

-- ============================================
-- 📈 إحصائيات يومية مفصلة
-- ============================================
CREATE TABLE IF NOT EXISTS daily_stats (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    user_id UUID REFERENCES auth.users(id) ON DELETE CASCADE,
    date DATE DEFAULT CURRENT_DATE,
    
    -- النشاط
    minutes_studied INTEGER DEFAULT 0,
    words_learned INTEGER DEFAULT 0,
    words_reviewed INTEGER DEFAULT 0,
    lessons_completed INTEGER DEFAULT 0,
    
    -- الأداء
    correct_answers INTEGER DEFAULT 0,
    total_attempts INTEGER DEFAULT 0,
    daily_accuracy NUMERIC(5,2) DEFAULT 0.0,
    
    -- النقاط
    points_earned INTEGER DEFAULT 0,
    
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    
    UNIQUE(user_id, date)
);

ALTER TABLE daily_stats ENABLE ROW LEVEL SECURITY;
CREATE POLICY "daily_stats_policy" ON daily_stats FOR ALL USING (auth.uid() = user_id OR auth.role() = 'service_role');
CREATE INDEX idx_daily_stats_user_date ON daily_stats(user_id, date DESC);








