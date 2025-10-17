-- جدول تقدم البودكاست (المحادثة الإنجليزية)
-- منفصل تماماً عن باقي الجداول لحفظ تقدم المحادثة الحرة

CREATE TABLE IF NOT EXISTS podcast_progress (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    user_id UUID REFERENCES auth.users(id) ON DELETE CASCADE,
    
    -- معلومات الجلسة الحالية
    session_id TEXT NOT NULL,
    last_topic TEXT DEFAULT '',  -- آخر موضوع تم التحدث عنه
    last_context TEXT DEFAULT '', -- آخر سياق في المحادثة
    last_position TEXT DEFAULT '', -- آخر نقطة توقف تفصيلية
    
    -- ملخص المحادثة
    conversation_summary TEXT DEFAULT '', -- ملخص عن آخر محادثة
    topics_discussed TEXT[] DEFAULT '{}', -- قائمة المواضيع التي تمت مناقشتها
    vocabulary_used JSONB DEFAULT '{}', -- الكلمات المستخدمة في المحادثة
    
    -- معلومات التقدم
    total_conversations INTEGER DEFAULT 0, -- عدد المحادثات الكلي
    total_minutes INTEGER DEFAULT 0, -- إجمالي الدقائق
    fluency_level TEXT DEFAULT 'beginner', -- مستوى الطلاقة المقدر
    common_mistakes JSONB DEFAULT '[]', -- الأخطاء الشائعة
    improvements JSONB DEFAULT '[]', -- التحسينات الملحوظة
    
    -- تاريخ المحادثات
    conversation_history JSONB DEFAULT '{}', -- تاريخ مفصل للمحادثات
    
    -- الطوابع الزمنية
    last_session_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    
    -- فهرس فريد للمستخدم
    UNIQUE(user_id)
);

-- إضافة الفهارس للأداء
CREATE INDEX IF NOT EXISTS idx_podcast_progress_user_id ON podcast_progress(user_id);
CREATE INDEX IF NOT EXISTS idx_podcast_progress_session_id ON podcast_progress(session_id);
CREATE INDEX IF NOT EXISTS idx_podcast_progress_last_session ON podcast_progress(last_session_at DESC);

-- تفعيل RLS
ALTER TABLE podcast_progress ENABLE ROW LEVEL SECURITY;

-- سياسات الأمان
DROP POLICY IF EXISTS "podcast_progress_select" ON podcast_progress;
DROP POLICY IF EXISTS "podcast_progress_insert" ON podcast_progress;
DROP POLICY IF EXISTS "podcast_progress_update" ON podcast_progress;
DROP POLICY IF EXISTS "podcast_progress_delete" ON podcast_progress;

-- السماح للمستخدم بالوصول لبياناته فقط
CREATE POLICY "podcast_progress_select" ON podcast_progress 
    FOR SELECT USING (auth.uid() = user_id OR auth.role() = 'service_role');

CREATE POLICY "podcast_progress_insert" ON podcast_progress 
    FOR INSERT WITH CHECK (auth.uid() = user_id OR auth.role() = 'service_role');

CREATE POLICY "podcast_progress_update" ON podcast_progress 
    FOR UPDATE USING (auth.uid() = user_id OR auth.role() = 'service_role');

CREATE POLICY "podcast_progress_delete" ON podcast_progress 
    FOR DELETE USING (auth.uid() = user_id OR auth.role() = 'service_role');

-- دالة تحديث الطابع الزمني تلقائياً
CREATE OR REPLACE FUNCTION update_podcast_progress_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    NEW.last_session_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- ربط الدالة بالجدول
DROP TRIGGER IF EXISTS update_podcast_progress_timestamp ON podcast_progress;
CREATE TRIGGER update_podcast_progress_timestamp
    BEFORE UPDATE ON podcast_progress
    FOR EACH ROW
    EXECUTE FUNCTION update_podcast_progress_updated_at();

-- تعليق توضيحي
COMMENT ON TABLE podcast_progress IS 'جدول حفظ تقدم المحادثات الإنجليزية (البودكاست) - منفصل عن باقي أنظمة التعلم';
COMMENT ON COLUMN podcast_progress.last_topic IS 'آخر موضوع تم التحدث عنه في المحادثة';
COMMENT ON COLUMN podcast_progress.last_position IS 'آخر نقطة توقف تفصيلية مثل: كنا نتحدث عن السفر إلى باريس';
COMMENT ON COLUMN podcast_progress.conversation_summary IS 'ملخص آخر محادثة لتذكير المستخدم';
COMMENT ON COLUMN podcast_progress.fluency_level IS 'تقييم مستوى الطلاقة: beginner, intermediate, advanced';
