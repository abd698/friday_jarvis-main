import json
import logging
import asyncio
import re
from datetime import datetime
from dotenv import load_dotenv

from livekit import agents
from livekit.agents import AgentSession, Agent, RoomInputOptions, ChatContext
from livekit.plugins import google
from prompts import AGENT_INSTRUCTION, SESSION_INSTRUCTION, SENTENCES_TEACHING_PROMPT, ENGLISH_CONVERSATION_PROMPT
from tools import get_weather, search_web, send_email
from supabase_client import supabase_manager
# from sentences import get_sentences_prompt  # تم نقل prompt إلى prompts.py

load_dotenv()

# تقليل مستوى اللوج لتجنب رسائل transcription غير المرغوبة
logging.getLogger("livekit").setLevel(logging.WARNING)


class Assistant(Agent):
    def __init__(self, chat_ctx: ChatContext = None, user_id: str = None, user_name: str = "المستخدم", mode: str = "normal", voice_name: str = "Aoede") -> None:
        """
        معلم الإنجليزية بالذكاء الاصطناعي
        
        Args:
            voice_name: اسم الصوت (Aoede أو Kore للأنثى، Puck أو Charon أو Fenrir للذكر)
        """
        # اختيار التعليمات بناءً على الوضع
        if mode == "sentences_learning":
            instructions = SENTENCES_TEACHING_PROMPT
            print(f"[agent] استخدام وضع تعليم الجمل البسيطة")
        elif mode == "english_conversation":
            # سيتم تحديث الـ prompt لاحقاً بذاكرة البودكاست
            self.base_conversation_prompt = ENGLISH_CONVERSATION_PROMPT
            instructions = ENGLISH_CONVERSATION_PROMPT.replace("{podcast_memory}", "")
            print(f"[agent] استخدام وضع المحادثة الإنجليزية")
        else:
            instructions = AGENT_INSTRUCTION
            print(f"[agent] استخدام الوضع العادي")
        
        # التحقق من صحة الصوت
        valid_voices = ["Aoede", "Kore", "Puck", "Charon", "Fenrir"]
        if voice_name not in valid_voices:
            print(f"⚠️ صوت غير صالح: {voice_name}. استخدام Aoede")
            voice_name = "Aoede"
        
        print(f"🎤 استخدام صوت: {voice_name}")
            
        # تهيئة المساعد بدون speech_config
        super().__init__(
            chat_ctx=chat_ctx,
            instructions=instructions,
            llm=google.beta.realtime.RealtimeModel(
                voice=voice_name,
                temperature=0.8,
            ),
            tools=[
                get_weather,
                search_web,
                send_email
            ],
        )
        self.voice_name = voice_name
        self.mode = mode
        self.user_id = user_id
        self.user_name = user_name
        self.user_progress = None
        self.personal_context = None  # السياق الشخصي للمستخدم
        self._last_context_save = None  # للـ rate limiting
        
        # 🎯 الأنظمة الجديدة
        self.level_assessment = None  # تقييم المستوى
        self.achievements = None  # الإنجازات
        self.session_start_time = datetime.now()  # وقت بدء الجلسة
        self.words_learned_session = []  # كلمات هذه الجلسة
        self.session_correct_answers = 0
        self.session_total_attempts = 0
        
        self.session_data = {
            "session_id": str(datetime.now().timestamp()),
            "start_time": datetime.now().isoformat(),
            "words_discussed": [],
            "topics_covered": [],
            "current_topic": "",
            "last_position": ""
        }
        self._message_count = 0
        
        # 📚 متغيرات وضع تعليم الجمل - تهيئة افتراضية لتجنب AttributeError
        self.sentences_session_id = f"sentences_{int(datetime.now().timestamp())}"
        self.sentences_progress = None
        self.current_sentences = []
        self.sentences_completed = 0
        self.current_level = 1
        self.current_sentence_index = 0
        self.learned_sentences_history = []
        
        # سيتم ربط معالجات الأحداث لاحقاً مع الجلسة
    
    async def load_sentences_progress(self):
        """تحميل تقدم الجمل للمستخدم في وضع الجمل ودمجه في الذاكرة"""
        if not self.user_id or self.mode != "sentences_learning":
            return
            
        try:
            # جلب آخر جلسة نشطة أو إنشاء جديدة
            self.sentences_progress = await supabase_manager.get_sentences_progress(self.user_id)
            
            if not self.sentences_progress:
                # إنشاء جلسة جديدة
                result = await supabase_manager.create_sentences_session(
                    self.user_id, 
                    self.sentences_session_id
                )
                self.sentences_progress = result.get("data")
                
                # ✅ تهيئة المتغيرات للجلسة الجديدة
                self.current_sentences = []
                self.sentences_completed = 0
                self.current_level = 1
                self.current_sentence_index = 0
                self.learned_sentences_history = []
                
                print(f"[agent] تم إنشاء جلسة جمل جديدة: {self.sentences_session_id}")
            else:
                # استخدام الجلسة اقوجودة
                self.sentences_session_id = self.sentences_progress["session_id"]
                self.current_sentences = self.sentences_progress.get("generated_sentences", [])
                self.sentences_completed = self.sentences_progress.get("completed_sentences", 0)
                # تحميل المستوى الحالي وتاريخ الجمل
                self.current_level = self.sentences_progress.get("current_level", 1)
                self.learned_sentences_history = self.sentences_progress.get("learned_sentences_history", [])
                # تحديث current_sentence_index للاستكمال من الجملة الصحيحة (يشير للجملة التالية غير المكتملة)
                # إذا أكمل 2 جمل، المؤشر يجب أن يكون 2 (للجملة رقم 3)
                self.current_sentence_index = self.sentences_progress.get("current_sentence_index", self.sentences_completed)
                
                # إصلاح العدد الإجمالي إذا كان غير صحيح
                current_total = self.sentences_progress.get("total_sentences", 0)
                actual_total = len(self.current_sentences)
                if current_total != actual_total and actual_total > 0:
                    await supabase_manager.update_sentences_progress(
                        self.user_id,
                        self.sentences_session_id,
                        total_sentences=actual_total
                    )
                    self.sentences_progress["total_sentences"] = actual_total
                    print(f"[agent] تم إصلاح العدد الإجمالي من {current_total} إلى {actual_total}")
                
                print(f"[agent] تم تحميل جلسة جمل موجودة: {self.sentences_session_id}")
                print(f"[agent] الجمل المُكتملة: {self.sentences_completed}, الجملة التالية: {self.current_sentence_index}")
                print(f"[agent] المستوى الحالي: {self.current_level}, عدد الجمل المتعلمة تاريخياً: {len(self.learned_sentences_history)}")
            
            # دمج ذاكرة الجمل في سياق المحادثة
            if self.sentences_progress and self.chat_ctx:
                sentences_memory_context = self._build_sentences_memory_context()
                if sentences_memory_context:
                    # إنشاء نسخة جديدة من السياق وتحديثها
                    new_ctx = self.chat_ctx.copy()
                    new_ctx.add_message(role="system", content=sentences_memory_context)
                    await self.update_chat_ctx(new_ctx)
                    print(f"[agent] تم دمج ذاكرة الجمل في السياق بنجاح")
                
        except Exception as e:
            print(f"[agent] خطأ في تحميل تقدم الجمل: {e}")

    async def save_sentence_progress(self, sentence_text: str, sentence_index: int, completed: bool = False):
        """حفظ تقدم جملة محددة"""
        if not self.user_id or self.mode != "sentences_learning" or not self.sentences_session_id:
            return
            
        try:
            sentence_data = {
                "sentence": sentence_text,
                "completed": completed,
                "timestamp": datetime.now().isoformat(),
                "attempts": 1
            }
            
            await supabase_manager.save_sentences_data(
                self.user_id, 
                self.sentences_session_id, 
                sentence_data, 
                sentence_index
            )
            print(f"[agent] تم حفظ تقدم الجملة {sentence_index}")
            
        except Exception as e:
            print(f"[agent] خطأ في حفظ تقدم الجملة: {e}")

    async def process_sentences_response(self, agent_text: str):
        """معالجة رد المساعد في وضع الجمل وحفظ البيانات"""
        if not self.user_id or self.mode != "sentences_learning":
            return
        
        # ✅ التحقق من وجود sentences_session_id قبل الحفظ
        if not hasattr(self, 'sentences_session_id') or not self.sentences_session_id:
            print(f"[agent] ⚠️ sentences_session_id غير موجود، لن يتم حفظ الجمل")
            return
            
        try:
            # البحث عن الجمل الإنجليزية المُولدة في الرد
            # نبحث عن أنماط مثل: "1. **I am happy.**" أو "**I am happy.**"
            sentence_patterns = [
                r'\*\*([A-Z][^*]+\.)\*\*',  # **I am happy.**
                r'[\d]+\.\s*\*\*([A-Z][^*]+\.)\*\*',  # 1. **I am happy.**
                r'"([A-Z][^"]+\.)"',  # "I am happy."
            ]
            
            found_sentences = []
            for pattern in sentence_patterns:
                matches = re.findall(pattern, agent_text)
                found_sentences.extend(matches)
            
            # حفظ الجمل المُولدة إذا وُجدت
            if found_sentences:
                # تحديث قائمة الجمل الحالية
                if not hasattr(self, 'current_sentences') or not self.current_sentences:
                    self.current_sentences = []
                
                # مقارنة دقيقة للجمل - تنظيف الجمل للمقارنة الصحيحة
                normalized_current = [s.lower().replace('.', '').replace(',', '').strip() for s in self.current_sentences]
                
                new_sentences = []
                for sentence in found_sentences:
                    clean_sentence = sentence.strip()
                    normalized_new = clean_sentence.lower().replace('.', '').replace(',', '').strip()
                    
                    # تحقق من عدم وجود الجملة مسبقاً (مقارنة بالنص المنظف)
                    if normalized_new not in normalized_current and clean_sentence:
                        new_sentences.append(clean_sentence)
                        normalized_current.append(normalized_new)  # إضافة للمقارنة اللاحقة
                
                if new_sentences:
                    self.current_sentences.extend(new_sentences)
                    # إضافة الجمل الجديدة لتاريخ التعلم (مع التحقق من وجوده)
                    if not hasattr(self, 'learned_sentences_history'):
                        self.learned_sentences_history = []
                    self.learned_sentences_history.extend(new_sentences)
                    
                    # حفظ الجمل الجديدة في قاعدة البيانات مع المستوى الحالي
                    await supabase_manager.update_sentences_progress(
                        self.user_id,
                        self.sentences_session_id,
                        generated_sentences=self.current_sentences,
                        total_sentences=len(self.current_sentences),
                        current_level=self.current_level,
                        learned_sentences_history=self.learned_sentences_history
                    )
                    print(f"[agent] 💾 تم حفظ {len(new_sentences)} جملة جديدة (المستوى {self.current_level}). إجمالي: {len(self.current_sentences)} جملة")
                    print(f"[agent] ✨ الجمل الجديدة: {new_sentences}")
                else:
                    print(f"[agent] تم تجاهل {len(found_sentences)} جملة مكررة: {found_sentences}")
            
            # البحث عن إشارات إكمال جملة
            completion_indicators = [
                "ممتاز", "أحسنت", "جيد جداً", "excellent", "great", "perfect"
            ]
            
            if any(indicator in agent_text.lower() for indicator in completion_indicators):
                # زيادة عدد الجمل المُكتملة
                self.sentences_completed = getattr(self, 'sentences_completed', 0) + 1
                # تحديث current_sentence_index للجملة التالية (يجب أن يساوي sentences_completed)
                self.current_sentence_index = self.sentences_completed
                
                print(f"[agent] جملة مكتملة! العدد المكتمل: {self.sentences_completed}, المؤشر التالي: {self.current_sentence_index}")
                
                # حفظ التقدم الجديد مع العدد الإجمالي الصحيح
                current_total = len(getattr(self, 'current_sentences', []))
                
                # إذا أكمل المستخدم كل جمل المستوى الحالي، انتقل للمستوى التالي
                sentences_per_level = 20  # عدد الجمل في كل مستوى (حسب prompts.py)
                if (self.sentences_completed % sentences_per_level == 0 and 
                    self.sentences_completed > 0 and 
                    self.current_level < 5):
                    self.current_level += 1
                    print(f"[agent] 🎉 مبروك! الانتقال للمستوى {self.current_level} - أكملت {self.sentences_completed} جملة!")
                
                await supabase_manager.update_sentences_progress(
                    self.user_id,
                    self.sentences_session_id,
                    completed_sentences=self.sentences_completed,
                    current_sentence_index=self.current_sentence_index,
                    generated_sentences=self.current_sentences,  # ✅ إضافة الجمل المُنشأة
                    total_sentences=current_total,
                    current_level=self.current_level,
                    learned_sentences_history=getattr(self, 'learned_sentences_history', [])
                )
                print(f"[agent] ✅ تم تحديث التقدم: {self.sentences_completed}/{current_total} جملة مُكتملة (المستوى {self.current_level})")
                
        except Exception as e:
            print(f"[agent] خطأ في معالجة رد الجمل: {e}")

    async def load_podcast_progress(self):
        """تحميل تقدم البودكاست للمستخدم ودمجه في الذاكرة"""
        if not self.user_id or self.mode != "english_conversation":
            return
            
        try:
            # جلب تقدم البودكاست أو إنشاؤه
            # تحميل صامت للبيانات
            self.podcast_progress = await supabase_manager.get_or_create_podcast_progress(self.user_id)
            
            if self.podcast_progress:
                
                # دمج ذاكرة البودكاست في سياق المحادثة
                if self.chat_ctx:
                    podcast_memory_context = self._build_podcast_memory_context()
                    if podcast_memory_context:
                        new_ctx = self.chat_ctx.copy()
                        new_ctx.add_message(role="system", content=podcast_memory_context)
                
        except Exception as e:
            pass  # تجاهل الأخطاء بصمت
    
    def _build_podcast_memory_context(self) -> str:
        """بناء سياق الذاكرة لوضع البودكاست"""
        if not self.podcast_progress:
            return ""
        
        last_topic = self.podcast_progress.get('last_topic', '')
        last_position = self.podcast_progress.get('last_position', '')
        last_context = self.podcast_progress.get('last_context', '')
        conversation_summary = self.podcast_progress.get('conversation_summary', '')
        topics_discussed = self.podcast_progress.get('topics_discussed', [])
        total_conversations = self.podcast_progress.get('total_conversations', 0)
        fluency_level = self.podcast_progress.get('fluency_level', 'beginner')
        common_mistakes = self.podcast_progress.get('common_mistakes', [])
        improvements = self.podcast_progress.get('improvements', [])
        
        context = f"""
=== Podcast Conversation Memory for: {self.user_name} ===
📊 Statistics:
- Total conversations: {total_conversations}
- Fluency level: {fluency_level}
- Topics discussed: {', '.join(topics_discussed[-5:]) if topics_discussed else 'None yet'}

📍 Last Session:
- Topic: {last_topic or 'First conversation'}
- Position: {last_position or 'Starting fresh'}
- Context: {last_context or 'No previous context'}
- Summary: {conversation_summary or 'This is our first conversation'}

🎯 Common Mistakes to Address:
{chr(10).join([f"- {mistake}" for mistake in common_mistakes[-5:]]) if common_mistakes else "- No mistakes recorded yet"}

✨ Noticed Improvements:
{chr(10).join([f"- {improvement}" for improvement in improvements[-5:]]) if improvements else "- First session"}

🔥 CRITICAL INSTRUCTIONS FOR RETURNING USER:
1. If there was a previous topic ({last_topic}), acknowledge it naturally:
   "Hey! Last time we were talking about {last_topic}. {last_position}"
   "Would you like to continue that conversation or talk about something new?"

2. Reference their progress naturally:
   - Mention improvements you've noticed
   - Gently correct recurring mistakes
   - Build on previous conversations

3. Adapt to their fluency level ({fluency_level}):
   - Beginner: Simple vocabulary, more support
   - Intermediate: Mix complexity, gentle corrections
   - Advanced: Natural flow, minimal interruptions

4. Make the conversation feel continuous and personal!
"""
        
        return context
    
    async def load_personal_context(self):
        """تحميل السياق الشخصي للمستخدم"""
        if not self.user_id:
            return
        
        try:
            # جلب السياق الشخصي
            self.personal_context = await supabase_manager.get_or_create_personal_context(self.user_id)
            
            if self.personal_context:
                # تسجيل السياق الشخصي
                personal_memory = self._build_personal_context_memory()
                if personal_memory:
                    logging.info(f"[agent] ✅ تم تحميل السياق الشخصي (اكتمال: {self.personal_context.get('context_completeness', 0)}%)")
        except Exception as e:
            logging.error(f"[agent] خطأ في تحميل السياق الشخصي: {e}")
    
    async def load_gamification_data(self):
        """تحميل بيانات التحفيز والإنجازات"""
        if not self.user_id:
            return
        
        try:
            # جلب التقييم والإنجازات
            self.level_assessment = await supabase_manager.get_or_create_level_assessment(self.user_id)
            self.achievements = await supabase_manager.get_or_create_achievements(self.user_id)
            
            # تحديث الـ streak
            await supabase_manager.update_streak(self.user_id)
            
            # تسجيل معلومات التحفيز
            if self.achievements:
                logging.info(f"[agent] ✅ تم تحميل بيانات التحفيز:")
                logging.info(f"  - Level: {self.achievements.get('current_level', 1)}")
                logging.info(f"  - Points: {self.achievements.get('total_points', 0)}")
                logging.info(f"  - Streak: {self.achievements.get('current_streak', 0)} days")
                logging.info(f"  - Words: {self.achievements.get('total_words_learned', 0)}")
        except Exception as e:
            logging.error(f"[agent] خطأ في تحميل بيانات التحفيز: {e}")
    
    async def track_new_word(self, word: str, translation: str = "", example: str = "", topic: str = ""):
        """تتبع كلمة جديدة لنظام المراجعة"""
        if not self.user_id or not word:
            return
        
        try:
            # إضافة لـ vocabulary_cards
            result = await supabase_manager.add_vocabulary_card(self.user_id, word, translation, example, topic)
            
            # إذا كانت كلمة جديدة (ليست موجودة مسبقاً)
            if result.get("success") and not result.get("exists"):
                self.words_learned_session.append(word)
                
                # تحديث عداد الكلمات في user_achievements
                if self.achievements:
                    from supabase_client import supabase_manager as sm
                    client = sm.service_client if sm.service_client else sm.client
                    client.table("user_achievements").update({
                        "total_words_learned": self.achievements.get("total_words_learned", 0) + 1,
                        "updated_at": datetime.now().isoformat()
                    }).eq("user_id", self.user_id).execute()
                
                logging.info(f"[agent] 📚 تمت إضافة كلمة جديدة: {word}")
        except Exception as e:
            logging.error(f"[agent] خطأ في تتبع الكلمة: {e}")
    
    async def award_points(self, points: int, reason: str = ""):
        """منح نقاط للمستخدم"""
        if not self.user_id:
            return
        
        try:
            result = await supabase_manager.award_points(self.user_id, points, reason)
            
            if result.get("level_up"):
                # المستخدم ارتقى!
                new_level = result.get("new_level")
                celebration = f"🎉 LEVEL UP! You reached Level {new_level}! 🎉"
                logging.info(f"[agent] 🎆 LEVEL UP: {self.user_id} -> Level {new_level}")
                # يمكن إرسال رسالة للمستخدم هنا
        except Exception as e:
            logging.error(f"[agent] خطأ في منح النقاط: {e}")
    
    async def track_answer(self, correct: bool):
        """تتبع إجابة لتحديث الإحصائيات"""
        self.session_total_attempts += 1
        if correct:
            self.session_correct_answers += 1
            # منح نقاط
            await self.award_points(5, "correct answer")
        
        # 📊 تحديث daily_stats فورياً بدلاً من الانتظار لنهاية الجلسة
        if self.user_id:
            try:
                accuracy = (self.session_correct_answers / self.session_total_attempts * 100) if self.session_total_attempts > 0 else 0
                await supabase_manager.update_daily_stats(self.user_id, {
                    "correct_answers": self.session_correct_answers,
                    "total_attempts": self.session_total_attempts,
                    "daily_accuracy": accuracy
                })
            except Exception as e:
                pass  # تجاهل الأخطاء بصمت
    
    async def end_session_summary(self):
        """ملخص نهاية الجلسة"""
        if not self.user_id:
            return
        
        try:
            # حساب مدة الجلسة
            duration = (datetime.now() - self.session_start_time).seconds // 60
            
            # حساب الدقة
            accuracy = 0
            if self.session_total_attempts > 0:
                accuracy = (self.session_correct_answers / self.session_total_attempts) * 100
            
            # تحديث الإحصائيات اليومية
            await supabase_manager.update_daily_stats(self.user_id, {
                "minutes_studied": duration,
                "words_learned": len(self.words_learned_session),
                "correct_answers": self.session_correct_answers,
                "total_attempts": self.session_total_attempts
            })
            
            logging.info(f"[agent] 📊 جلسة منتهية: {duration}د, {len(self.words_learned_session)} كلمة, {accuracy:.1f}% دقة")
        except Exception as e:
            logging.error(f"[agent] خطأ في ملخص الجلسة: {e}")
    
    def _build_personal_context_memory(self) -> str:
        """بناء سياق الذاكرة الشخصية للمستخدم"""
        if not self.personal_context:
            return ""
        
        context = f"""
=== 🌟 PERSONAL CONTEXT FOR: {self.user_name} ===

USE THIS INFORMATION TO CREATE PERSONALIZED, REAL-LIFE EXAMPLES!

👤 **Basic Info:**
- Name: {self.personal_context.get('first_name', 'Unknown')}
- Age: {self.personal_context.get('age', 'Unknown')}
- Occupation: {self.personal_context.get('occupation', 'Unknown')}
- City: {self.personal_context.get('city', 'Unknown')}

👨‍👩‍👧‍👦 **Family & Friends:**
- Family members: {', '.join([f"{k}: {v}" for k, v in self.personal_context.get('family_members', {}).items()]) or 'Not yet collected'}
- Friends: {', '.join(self.personal_context.get('friends', [])) or 'Not yet collected'}
- Pets: {', '.join([f"{p.get('name')} ({p.get('type')})" for p in self.personal_context.get('pets', [])]) or 'None'}

❤️ **Interests & Preferences:**
- Hobbies: {', '.join(self.personal_context.get('hobbies', [])) or 'Not yet collected'}
- Favorite foods: {', '.join(self.personal_context.get('favorite_foods', [])) or 'Not yet collected'}
- Favorite colors: {', '.join(self.personal_context.get('favorite_colors', [])) or 'Not yet collected'}

🏠 **Environment:**
- Objects around: {', '.join(self.personal_context.get('objects_around', [])) or 'Not yet collected'}
- Home items: {', '.join(self.personal_context.get('home_items', [])) or 'Not yet collected'}
- Room: {self.personal_context.get('room_description', 'Not described yet')}

🎯 **Goals & Dreams:**
- Learning goals: {', '.join(self.personal_context.get('learning_goals', [])) or 'Not yet discussed'}
- Dream job: {self.personal_context.get('dream_job', 'Not shared yet')}
- Want to visit: {', '.join(self.personal_context.get('places_want_to_visit', [])) or 'Not shared yet'}

📊 **Context Completeness: {self.personal_context.get('context_completeness', 0)}%**

⚠️ **CRITICAL INSTRUCTIONS:**

1. **IF INFO IS MISSING**: Ask naturally during the lesson!
   - Example: "Before we continue, what's your name?" (if name is missing)
   - Example: "Tell me, what objects do you see around you?" (when teaching nouns)

2. **USE THEIR ACTUAL INFO IN EXAMPLES**:
   - ❌ DON'T SAY: "John has a book"
   - ✅ DO SAY: "{self.personal_context.get('first_name', 'You')} has a {self.personal_context.get('objects_around', ['phone'])[0] if self.personal_context.get('objects_around') else 'phone'}"

3. **MAKE IT PERSONAL AND ENGAGING**:
   - Use their family names, friend names, hobbies, favorite things
   - Reference their daily life, environment, goals
   - Make them the HERO of every example!

4. **UPDATE AS YOU GO**:
   - When they mention new info, use it immediately
   - Keep the context fresh and current

**Remember**: This is THEIR English learning journey, not a generic textbook!
"""
        return context
    
    def _extract_personal_info_from_text(self, text: str) -> dict:
        """استخراج معلومات شخصية من نص المستخدم"""
        if not text:
            return {}
        
        text_lower = text.lower()
        updates = {}
        
        # استخراج الاسم
        name_patterns = [
            r"(?:my name is|i'm|i am|call me|\u0627\u0633\u0645\u064a|\u0623\u0646\u0627)\s+([\u0627-\u064a\u0621-\u064a\w]+)",
            r"^([\u0627-\u064a\u0621-\u064a\w]+)$"  # إذا كانت إجابة بكلمة واحدة فقط
        ]
        for pattern in name_patterns:
            match = re.search(pattern, text, re.IGNORECASE | re.UNICODE)
            if match and len(match.group(1)) > 1 and len(match.group(1)) < 20:
                potential_name = match.group(1).strip()
                # تجنب الكلمات الشائعة غير الأسماء
                excluded = ['yes', 'no', 'okay', 'sure', 'hello', 'hi', 'thanks', 'thank', 'نعم', 'لا', 'شوكرا', 'مرحبا']
                if potential_name.lower() not in excluded:
                    updates['first_name'] = potential_name.title()
                    break
        
        # استخراج العمر
        age_match = re.search(r'(?:\u0639\u0645\u0631\u064a|age|i am|i\'m|\u0623\u0646\u0627)\s*(\d{1,2})(?:\s*(?:year|\u0633\u0646\u0629|\u0639\u0627\u0645))?', text, re.IGNORECASE | re.UNICODE)
        if age_match:
            age = int(age_match.group(1))
            if 5 <= age <= 100:  # عمر منطقي
                updates['age'] = age
        
        # استخراج المدينة
        city_patterns = [
            r'(?:from|in|live in|\u0645\u0646|\u0641\u064a|\u0623\u0633\u0643\u0646 \u0641\u064a)\s+([\u0627-\u064a\u0621-\u064a\w\s]+?)(?:\.|,|$)',
            r'(?:city|\u0645\u062f\u064a\u0646\u0629|\u0645\u062f\u064a\u0646\u062a\u064a)\s+(?:is|:)?\s*([\u0627-\u064a\u0621-\u064a\w\s]+?)(?:\.|,|$)'
        ]
        for pattern in city_patterns:
            match = re.search(pattern, text, re.IGNORECASE | re.UNICODE)
            if match:
                city = match.group(1).strip()
                if len(city) > 2 and len(city) < 30:
                    updates['city'] = city.title()
                    break
        
        # استخراج المهنة
        occupation_patterns = [
            r'(?:i\'m a|i am a|i work as|\u0623ن\u0627|\u0639مل\u064a)\s+(student|teacher|engineer|doctor|developer|designer|\u0637\u0627\u0644\u0628|\u0645ه\u0646\u062f\u0633|\u0637\u0628\u064a\u0628|\u0645\u0639\u0644\u0645|\u0645\u0628\u0631\u0645\u062c)',
            r'(?:job|work|occupation|\u0645\u0647\u0646\u0629|\u0639\u0645\u0644)\s*(?:is|:)?\s*([\u0627-\u064a\u0621-\u064a\w]+)'
        ]
        for pattern in occupation_patterns:
            match = re.search(pattern, text, re.IGNORECASE | re.UNICODE)
            if match:
                updates['occupation'] = match.group(1).strip()
                break
        
        # استخراج الهوايات
        hobby_keywords = ['football', 'soccer', 'reading', 'cooking', 'gaming', 'music', 'swimming', 'running',
                         'قراءة', 'كرة', 'طبخ', 'ألعاب', 'موسيقى', 'سباحة', 'جري']
        found_hobbies = []
        for hobby in hobby_keywords:
            if hobby in text_lower:
                found_hobbies.append(hobby)
        
        # استخراج قوائم بشكل عام
        list_match = re.findall(r'([\u0627-\u064a\u0621-\u064a\w]+)\s*(?:,|\u0648)\s*([\u0627-\u064a\u0621-\u064a\w]+)', text, re.UNICODE)
        if list_match and not updates.get('first_name'):  # إذا لم يتم العثور علأ اسم
            items = [item for pair in list_match for item in pair]
            # قد تكون أسماء أشياء محيطة
            if any(word in text_lower for word in ['see', 'have', 'around', 'حول', 'عندي', 'أرى']):
                found_hobbies.extend(items[:3])  # أول 3 عناصر
        
        if found_hobbies:
            updates['hobbies'] = found_hobbies[:5]  # أقصى 5
        
        return updates
    
    async def update_personal_context_from_conversation(self, detected_info: dict):
        """تحديث السياق الشخصي من المحادثة"""
        if not self.user_id or not detected_info:
            return
        
        try:
            # تحديث المعلومات في قاعدة البيانات
            await supabase_manager.update_personal_context(self.user_id, detected_info)
            # تحديث الذاكرة المحلية
            if self.personal_context:
                self.personal_context.update(detected_info)
                print(f"[agent] ✅ تم تحديث السياق الشخصي: {list(detected_info.keys())}")
        except Exception as e:
            print(f"[agent] خطأ في تحديث السياق: {e}")
    
    async def _auto_extract_and_save_context(self, user_message: str):
        """استخراج وحفظ تلقائي للمعلومات من رسالة المستخدم"""
        if not user_message or not self.user_id:
            return
        
        try:
            # استخراج المعلومات
            extracted = self._extract_personal_info_from_text(user_message)
            
            if extracted:
                # حفظ فوراً
                await self.update_personal_context_from_conversation(extracted)
        except Exception as e:
            # خطأ صامت - لا نريد إيقاف المحادثة
            pass
    
    async def load_user_memory(self):
        """تحميل ذاكرة المستخدم من قاعدة البيانات"""
        if not self.user_id:
            return
        
        # تحميل السياق الشخصي أولاً (لجميع الأوضاع)
        await self.load_personal_context()
        
        # تحميل بيانات التحفيز (لجميع الأوضاع)
        await self.load_gamification_data()
            
        # إذا كان في وضع تعليم الجمل، حمل تقدم الجمل فقط
        if self.mode == "sentences_learning":
            await self.load_sentences_progress()
            return  # لا نحتاج لتحميل user_progress في هذا الوضع
        
        # إذا كان في وضع البودكاست، حمل تقدم البودكاست
        if self.mode == "english_conversation":
            await self.load_podcast_progress()
            return
        
        try:
            # تحميل صامت للبيانات بدون طباعة لتسريع البداية
            self.user_progress = await supabase_manager.get_or_create_user_progress(self.user_id)
            
            # تحديث سياق المحادثة بالذاكرة فقط (بدون تطبيق البيانات على الجلسة الحالية)
            if self.user_progress:
                memory_context = self._build_memory_context()
                
                # إنشاء نسخة جديدة من السياق وتحديثها
                new_ctx = self.chat_ctx.copy()
                new_ctx.add_message(role="system", content=memory_context)
                await self.update_chat_ctx(new_ctx)
                
        except Exception as e:
            # تجاهل الأخطاء بصمت لتسريع البداية
            pass
    
    def _build_memory_context(self) -> str:
        """بناء سياق الذاكرة للمحادثة - يدعم الوضع العادي ووضع تعليم الجمل"""
        
        # وضع تعليم الجمل - بناء سياق مختلف
        if self.mode == "sentences_learning":
            return self._build_sentences_memory_context()
        
        # الوضع العادي
        if not self.user_progress:
            return ""
        
        # بناء قائمة الكلمات المتعلمة
        vocabulary = self.user_progress.get('vocabulary', {})
        learned_words = list(vocabulary.keys())[:10]  # أول 10 كلمات
        
        # تحديد حالة الموضوع الحالي
        current_topic = self.user_progress.get('current_topic', '')
        progress_percentage = self.user_progress.get('progress_percentage', 0)
        is_topic_incomplete = current_topic and progress_percentage < 100
        
        context = f"""
=== ذاكرة المستخدم: {self.user_name} ===
📊 إحصائيات التعلم:
- عدد الكلمات المتعلمة: {self.user_progress.get('words_learned', 0)}
- نسبة التقدم: {progress_percentage}%
- آخر جلسة: {self.user_progress.get('last_session_at', 'لا توجد جلسات سابقة')}

📚 الموضوع الحالي: {current_topic or 'لم يبدأ بعد'}
📍 آخر نقطة توقف: {self.user_progress.get('last_position', 'البداية')}
✅ المواضيع المكتملة: {', '.join(self.user_progress.get('topics_completed', [])) or 'لا توجد'}

🔤 بعض الكلمات المتعلمة: {', '.join(learned_words) if learned_words else 'لا توجد كلمات بعد'}

🎯 تعليمات مهمة للمساعد:
{"⚠️ هناك موضوع غير مكتمل!" if is_topic_incomplete else "✅ لا يوجد موضوع معلق"}

CRITICAL INSTRUCTIONS FOR RETURNING USER:
1. إذا كان هناك موضوع حالي غير مكتمل ({current_topic}), يجب أن تسأل المستخدم:
   "أهلاً بك مرة أخرى! أرى أنك كنت تدرس موضوع {current_topic} وتوقفت عند {self.user_progress.get('last_position', 'البداية')}"
   "هل تريد أن نكمل من حيث توقفنا، أم تفضل البدء بموضوع جديد؟"

2. انتظر إجابة المستخدم قبل المتابعة - لا تفترض أي شيء!

3. إذا اختار "نكمل":
   - استكمل من آخر نقطة توقف
   - راجع الكلمات السابقة بسرعة
   - تابع الشرح من النقطة المحفوظة

4. إذا اختار "موضوع جديد":
   - اقترح الموضوع التالي المناسب
   - امسح بيانات الجلسة القديمة
   - ابدأ بتقييم سريع إذا لزم الأمر

5. للمستخدمين الجدد: ابدأ بالتقييم المعتاد (5 أسئلة) ثم موضوع الأسماء

6. احفظ التقدم باستمرار أثناء الجلسة
"""
        
        # إضافة تاريخ المحادثات الأخيرة مع تفاصيل أكثر
        conversation_history = self.user_progress.get('conversation_history', {})
        if conversation_history:
            recent_sessions = list(conversation_history.items())[-2:]  # آخر جلستين
            context += "\n📝 آخر المحادثات:\n"
            for session_id, session_data in recent_sessions:
                topic = session_data.get('topic', 'غير محدد')
                words_count = len(session_data.get('words_discussed', []))
                last_pos = session_data.get('last_position', '')
                context += f"- {topic}: {words_count} كلمة، توقف عند: {last_pos}\n"
        
        context += "\n⚠️ مهم: استخدم هذه المعلومات لتقديم تجربة تعليمية متواصلة ومخصصة!\n"
        
        return context
    
    def _build_sentences_memory_context(self) -> str:
        """بناء سياق الذاكرة لوضع تعليم الجمل"""
        if not self.sentences_progress:
            return ""
        
        # بناء قائمة الجمل المتعلمة
        learned_sentences_history = self.sentences_progress.get('learned_sentences_history', [])
        current_sentences = self.sentences_progress.get('generated_sentences', [])
        completed_sentences = self.sentences_progress.get('completed_sentences', 0)
        current_level = self.sentences_progress.get('current_level', 1)
        current_sentence_index = self.sentences_progress.get('current_sentence_index', 0)
        total_sentences = len(current_sentences)
        
        # آخر 10 جمل متعلمة
        recent_learned = learned_sentences_history[-10:] if learned_sentences_history else []
        
        # الجمل الحالية في الجلسة
        remaining_sentences = current_sentences[current_sentence_index:current_sentence_index + 5] if current_sentences else []
        
        context = f"""
=== ذاكرة تعليم الجمل للمستخدم: {self.user_name} ===
📊 إحصائيات الجلسة:
- المستوى الحالي: {current_level}
- الجمل المكتملة: {completed_sentences}
- إجمالي الجمل في الجلسة: {total_sentences}
- الجملة التالية: {current_sentence_index + 1}

📝 آخر 10 جمل تعلمها المستخدم:
{chr(10).join([f"- {sentence}" for sentence in recent_learned]) if recent_learned else "- لا توجد جمل متعلمة بعد"}

🎯 الجمل التالية في الجلسة:
{chr(10).join([f"- {sentence}" for sentence in remaining_sentences]) if remaining_sentences else "- لا توجد جمل جديدة"}

🔥 تعليمات مهمة للمساعد في وضع الجمل:
1. أنت في وضع تعليم الجمل البسيطة - ركز على الجمل فقط
2. المستخدم تعلم بالفعل {len(learned_sentences_history)} جملة في المجموع
3. يجب عليك تذكر الجمل التي تعلمها وتجنب تكرارها
4. ابدأ من المستوى {current_level} واستمر في التدرج
5. استخدم الجمل المتعلمة كمرجع لبناء جمل جديدة
6. انتبه للتقدم التدريجي من البسيط للمعقد

⚠️ CRITICAL: تذكر الجمل المحددة أعلاه - لا تكررها!
"""
        
        return context
    
    async def save_session_progress(self, topic: str = "", words_discussed: list = None, progress_made: int = 0, last_position: str = "", session_summary: str = ""):
        """حفظ تقدم الجلسة الحالية - منفصل للوضع العادي ووضع الجمل ووضع البودكاست"""
        if not self.user_id:
            return
            
        # في وضع الجمل، لا نحفظ في user_progress - نظام منفصل
        if self.mode == "sentences_learning":
            print(f"[agent] وضع الجمل - تم تجاهل حفظ user_progress")
            return
        
        # في وضع البودكاست، نحفظ في podcast_progress
        if self.mode == "english_conversation":
            await self.save_podcast_progress(topic, words_discussed, last_position, session_summary)
            return
        
        try:
            # تحديث بيانات الجلسة الحالية
            if topic:
                self.session_data["current_topic"] = topic
            if words_discussed:
                self.session_data["words_discussed"] = words_discussed
            if last_position:
                self.session_data["last_position"] = last_position
            
            conversation_data = {
                "session_id": self.session_data["session_id"],
                "topic": topic or self.session_data.get("current_topic", ""),
                "words_discussed": words_discussed or self.session_data.get("words_discussed", []),
                "progress_made": progress_made,
                "last_position": last_position or self.session_data.get("last_position", ""),
                "session_summary": session_summary,
                "session_data": self.session_data
            }
            
            # حفظ بيانات المحادثة (باستثناء وضع البودكاست المعزول)
            if self.mode != "english_conversation":
                await supabase_manager.save_conversation_data(self.user_id, conversation_data)
            
            # تحديث نسبة التقدم والموضع فقط (للوضع العادي فقط)
            current_words_count = len(set(self.session_data.get("words_discussed", [])))
            current_topic = self.session_data.get("current_topic", "")
            last_position = self.session_data.get("last_position", "")
            
            # فحص وجود بيانات للحفظ
            if current_words_count > 0 or current_topic or last_position:
                await supabase_manager.update_user_progress(
                    user_id=self.user_id,
                    current_topic=current_topic or "General",  # موضوع افتراضي
                    last_position=last_position or "In progress",  # موضع افتراضي
                    progress_percentage=min(100, current_words_count * 2)  # كل كلمة = 2%
                )
                # رسالة تشخيصية
                print(f"[SAVE] ✅ حفظ التقدم: الموضوع={current_topic or 'N/A'}, الموضع={last_position or 'N/A'}, الكلمات={current_words_count}")
            
        except Exception as e:
            pass  # تجاهل الأخطاء
    
    async def save_podcast_progress(self, topic: str = "", words_discussed: list = None, last_position: str = "", session_summary: str = ""):
        """حفظ تقدم محادثة البودكاست في قاعدة البيانات المنفصلة"""
        if not self.user_id or self.mode != "english_conversation":
            return
        
        try:
            # حساب مدة المحادثة
            duration_minutes = 0
            if hasattr(self, 'conversation_start_time'):
                duration_minutes = int((datetime.now() - self.conversation_start_time).total_seconds() / 60)
            
            # استخراج الموضوع من المحادثة إذا لم يُحدد
            if not topic:
                topic = self.session_data.get("current_topic", "")
            
            # إذا لم يكن هناك موضوع، حاول استخراجه من الكلمات
            if not topic and hasattr(self, 'session_data'):
                words = self.session_data.get("words_discussed", [])
                # البحث عن مواضيع شائعة في الكلمات
                topic_keywords = {
                    'technology': ['technology', 'computer', 'phone', 'internet', 'software', 'hardware'],
                    'travel': ['travel', 'trip', 'vacation', 'flight', 'hotel', 'tourism'],
                    'food': ['food', 'eat', 'meal', 'restaurant', 'cook', 'recipe'],
                    'sports': ['sport', 'football', 'basketball', 'tennis', 'gym', 'exercise'],
                    'work': ['work', 'job', 'office', 'career', 'business', 'company']
                }
                
                for topic_name, keywords in topic_keywords.items():
                    if any(word in words for word in keywords):
                        topic = topic_name.capitalize()
                        self.session_data["current_topic"] = topic
                        break
            
            # جمع المفردات المستخدمة
            vocabulary = words_discussed or self.conversation_vocabulary or []
            
            # تحديد مستوى الطلاقة بناءً على الأداء
            fluency_level = self.podcast_progress.get('fluency_level', 'beginner') if self.podcast_progress else 'beginner'
            
            # تحديد السياق والموقف بالإنجليزية
            if topic:
                context = f"Discussing {topic}"
                if not last_position:
                    last_position = f"In the middle of talking about {topic}"
            else:
                context = "General conversation"
                last_position = "General English practice"
            
            # إعداد بيانات المحادثة للحفظ
            conversation_data = {
                "topic": topic,
                "context": context,
                "position": last_position,
                "summary": session_summary or f"Discussed {topic or 'various topics'} for {duration_minutes} minutes",
                "duration_minutes": duration_minutes,
                "vocabulary": vocabulary,
                "mistakes": self.conversation_mistakes if hasattr(self, 'conversation_mistakes') else [],
                "improvements": self.conversation_improvements if hasattr(self, 'conversation_improvements') else [],
                "fluency_level": fluency_level
            }
            
            # حفظ في قاعدة البيانات
            result = await supabase_manager.save_podcast_conversation(self.user_id, conversation_data)
            
            # رسالة تشخيصية
            if result.get("success"):
                print(f"[agent] ✅ تم حفظ البودكاست: الموضوع={topic}, الموقف={last_position}")
            else:
                print(f"[agent] ⚠️ فشل الحفظ: {result.get('error', 'Unknown')}")
            
        except Exception as e:
            print(f"[agent] ❌ خطأ في حفظ البودكاست: {e}")
            import traceback
            traceback.print_exc()
    
    def update_session_data(self, topic: str = None, words: list = None, position: str = None):
        """تحديث بيانات الجلسة الحالية"""
        if topic:
            self.session_data["current_topic"] = topic
        if words:
            self.session_data["words_discussed"].extend(words)
        if position:
            self.session_data["last_position"] = position
    
    async def auto_save_progress(self):
        """حفظ التقدم تلقائياً كل فترة - منفصل للأوضاع الثلاثة"""
        # تأجيل الحفظ في أول 30 ثانية لتحسين الأداء في البداية
        if not hasattr(self, '_session_start_time'):
            self._session_start_time = datetime.now()
        
        elapsed = (datetime.now() - self._session_start_time).total_seconds()
        if elapsed < 30:
            return  # لا تحفظ في أول 30 ثانية
        
        # debouncing: تجنب الحفظ المتكرر (كل 10 ثوانٍ على الأقل)
        if hasattr(self, '_last_auto_save'):
            time_since_last_save = (datetime.now() - self._last_auto_save).total_seconds()
            if time_since_last_save < 10:
                return
        
        # في وضع الجمل، نستخدم نظام حفظ الجمل المخصص
        if self.mode == "sentences_learning":
            return  # الحفظ يتم عبر process_sentences_response
        
        # في وضع البودكاست، نحفظ في podcast_progress
        if self.mode == "english_conversation":
            if self.session_data.get("current_topic") or self.session_data.get("words_discussed"):
                await self.save_podcast_progress(
                    topic=self.session_data.get("current_topic", "General conversation"),
                    words_discussed=self.session_data.get("words_discussed", []),
                    last_position=self.session_data.get("last_position", "In conversation"),
                    session_summary="Auto-save during conversation"
                )
                self._last_auto_save = datetime.now()
            return
            
        # الوضع العادي فقط
        if self.session_data.get("current_topic") or self.session_data.get("words_discussed"):
            await self.save_session_progress(
                topic=self.session_data.get("current_topic", ""),
                words_discussed=self.session_data.get("words_discussed", []),
                last_position=self.session_data.get("last_position", ""),
                session_summary="حفظ تلقائي"
            )
            self._last_auto_save = datetime.now()
    
    async def _on_user_input_transcribed(self, event):
        """معالج نسخ كلام المستخدم"""
        try:
            # التأكد من أن النسخ نهائي
            if not event.is_final:
                return
                
            user_text = event.transcript
            # تم إزالة رسالة التشخيص
            
            # 💾 استخراج وحفظ المعلومات الشخصية من كلام المستخدم
            await self._auto_extract_and_save_context(user_text)
            
            # في وضع الجمل، نعالج محاولات المستخدم
            if self.mode == "sentences_learning":
                await self.process_user_sentence_attempt(user_text)
            
            # في وضع البودكاست، نستخرج الموضوع من كلام المستخدم أيضاً
            if self.mode == "english_conversation":
                common_topics = ['technology', 'phones', 'computers', 'travel', 'food', 'sports', 
                               'movies', 'music', 'work', 'study', 'hobbies', 'family', 'weather']
                
                for topic in common_topics:
                    if topic in user_text.lower():
                        if not self.session_data.get("current_topic"):
                            self.session_data["current_topic"] = topic.capitalize()
                            print(f"[DEBUG] موضوع من المستخدم: {topic.capitalize()}")
                            # حفظ فوري للموضوع
                            await self.save_podcast_progress(
                                topic=topic.capitalize(),
                                last_position=f"User mentioned {topic}"
                            )
                        break
            
            # البحث عن مؤشرات اختيار المستخدم
            if any(keyword in user_text.lower() for keyword in ['متابعة', 'استئناف', 'من حيث توقفت']):
                # المستخدم يريد متابعة الموضوع السابق
                await self.continue_previous_topic()
                # المستخدم اختار متابعة الموضوع السابق
            elif any(keyword in user_text.lower() for keyword in ['موضوع جديد', 'بدء جديد', 'شيء جديد', 'موضوع آخر']):
                # المستخدم يريد بدء موضوع جديد
                # استخراج اسم الموضوع الجديد من النص
                new_topic_match = re.search(r'(?:موضوع|\btعلم|\bدرس)\s*(?:جديد|\bعن)?\s*[:؟]?\s*(.+)', user_text)
                if new_topic_match:
                    new_topic = new_topic_match.group(1).strip().rstrip('.,!?؟،')
                    if new_topic and len(new_topic) > 2:
                        await self.start_new_topic(new_topic)
                        # المستخدم اختار موضوعاً جديداً
                else:
                    # إذا لم نتمكن من استخراج الموضوع، نبدأ بجلسة جديدة
                    await self.start_new_topic("موضوع جديد")
                    # المستخدم اختار بدء موضوع جديد
            elif any(keyword in user_text.lower() for keyword in ['موضوع', 'درس', 'تعلم', 'كلمة']):
                # حفظ عادي للتقدم
                await self.auto_save_progress()
                
        except Exception as e:
            pass  # تجاهل الأخطاء بصمت
    
    async def _on_conversation_item_added(self, event):
        """معالج إضافة عنصر جديد للمحادثة"""
        try:
            # التحقق من نوع الرسالة
            item = event.item
            agent_text = ""  # تعريف المتغير في البداية
            
            # إذا كانت الرسالة من المساعد
            if item.role == "assistant":
                agent_text = item.text_content or ""
                # تم إزالة رسالة التشخيص
                
                # في وضع الجمل، نحتاج لحفظ الجمل المُولدة والتقدم
                if self.mode == "sentences_learning":
                    await self.process_sentences_response(agent_text)
                
                # 🎯 تتبع الإجابات الصحيحة/الخاطئة بناءً على رد المساعد
                correct_indicators = ['excellent', 'great', 'perfect', 'correct', 'right', 'well done',
                                     'ممتاز', 'رائع', 'صحيح', 'أحسنت', 'جيد جداً']
                wrong_indicators = ['incorrect', 'wrong', 'not quite', 'try again', 'mistake',
                                   'خطأ', 'غير صحيح', 'حاول مرة أخرى']
                
                agent_lower = agent_text.lower()
                if any(indicator in agent_lower for indicator in correct_indicators):
                    await self.track_answer(correct=True)
                elif any(indicator in agent_lower for indicator in wrong_indicators):
                    await self.track_answer(correct=False)
                
                # في وضع البودكاست، نستخرج الموضوع من المحادثة
                if self.mode == "english_conversation":
                    # استخراج الموضوع الأساسي من الكلمات المذكورة
                    common_topics = ['technology', 'phones', 'computers', 'travel', 'food', 'sports', 
                                   'movies', 'music', 'work', 'study', 'hobbies', 'family', 'weather']
                    
                    for topic in common_topics:
                        if topic in agent_text.lower():
                            if not self.session_data.get("current_topic"):
                                self.session_data["current_topic"] = topic.capitalize()
                                print(f"[DEBUG] استخرجت الموضوع: {topic.capitalize()}")
                            break
                
                # البحث عن كلمات إنجليزية جديدة في الرد
                english_words = re.findall(r'\b[A-Za-z]{3,}\b', agent_text)
                if english_words:
                    # إضافة الكلمات الجديدة للقائمة
                    current_words = self.session_data.get("words_discussed", [])
                    new_words = [word.lower() for word in english_words if word.lower() not in current_words]
                    if new_words:
                        current_words.extend(new_words)
                        self.session_data["words_discussed"] = current_words
                
                # البحث عن مؤشرات الموضوع بالإنجليزية والعربية - محسّنة
                topic_patterns = [
                    # English patterns - مواضيع مباشرة
                    r"\b(Nouns|Verbs|Adjectives|Adverbs|Pronouns|Prepositions|Conjunctions|Articles|Tenses|Grammar)\b",
                    r"(?:topic|subject)\s+(?:is|are|will be)\s+([A-Z][A-Za-z\s]+)",
                    r"(?:studying|learning|teaching|discussing)\s+([A-Z][A-Za-z\s]+)",
                    r"(?:Let's|let's)\s+(?:learn|study|talk about|discuss)\s+([A-Z][A-Za-z\s]+)",
                    r"(?:Today's topic|Our topic|The topic)\s+(?:is|will be)?:?\s*([A-Z][A-Za-z\s]+)",
                    r"(?:chapter|lesson|section)\s+(?:on|about)\s+([A-Z][A-Za-z\s]+)",
                    # Arabic patterns
                    r'الموضوع\s+(?:الحالي|اليوم)[:؟]?\s*(.+)',
                    r'سنتعلم\s+(?:عن|موضوع)\s*(.+)',
                    r'دعنا\s+نتحدث\s+عن\s*(.+)',
                    r'موضوع\s+الأسماء'  # "موضوع الأسماء" -> Nouns
                ]
                
                for pattern in topic_patterns:
                    matches = re.findall(pattern, agent_text, re.IGNORECASE)
                    if matches:
                        new_topic = matches[0].strip().rstrip('.,!?؟،')
                        if new_topic and len(new_topic) > 3 and new_topic != self.session_data.get("current_topic"):
                            self.session_data["current_topic"] = new_topic
                            # تم إزالة رسالة التشخيص
                            break
            
            # البحث عن نقطة التوقف بالإنجليزية والعربية - محسّنة
            if agent_text:
                position_patterns = [
                    # English patterns - مواضع محددة
                    r"\b(types of nouns|common nouns|proper nouns|abstract nouns|collective nouns|countable nouns|uncountable nouns)\b",
                    r"\b(present tense|past tense|future tense|verb forms|irregular verbs)\b",
                    r"\b(definition|examples|usage|rules|exceptions)\b",
                    r"(?:We were|You were)\s+(?:discussing|talking about|learning)\s+([A-Za-z][A-Za-z\s]+)",
                    r"(?:Last time|Previously|Earlier).*?(?:about|discussing|studying)\s+([A-Za-z][A-Za-z\s]+)",
                    r"(?:stopped at|paused at|left off at|ended with)\s+([A-Za-z][A-Za-z\s]+)",
                    r"(?:covered|finished|completed)\s+([A-Za-z][A-Za-z\s]+)",
                    # Arabic patterns  
                    r'نقطة\s+التوقف[:؟]?\s*(.+)',
                    r'وصلنا\s+إلى\s*(.+)',
                    r'انتهينا\s+من\s*(.+)',
                    r'تعلمنا\s+عن\s*(.+)'
                ]
                
                for pattern in position_patterns:
                    matches = re.findall(pattern, agent_text, re.IGNORECASE)
                    if matches:
                        new_position = matches[0].strip().rstrip('.,!?؟،')
                        if new_position and len(new_position) > 3:
                            self.session_data["last_position"] = new_position
                            # تم إزالة رسالة التشخيص
                            break
                    
            # حفظ التقدم كل 3 رسائل تقريباً
            self._message_count += 1
            if self._message_count % 3 == 0:
                await self.auto_save_progress()
                
        except Exception as e:
            pass  # تجاهل الأخطاء بصمت
    
    async def force_save_progress(self, topic: str = None, words: list = None, position: str = None):
        """حفظ فوري للتقدم - منفصل للوضعين"""
        try:
            # في وضع الجمل، نتجاهل الحفظ الفوري للنظام القديم
            if self.mode == "sentences_learning":
                # وضع الجمل - تم تجاهل الحفظ الفوري
                return
                
            if topic:
                self.session_data["current_topic"] = topic
            if words:
                self.session_data["words_discussed"] = words
            if position:
                self.session_data["last_position"] = position
            
            # حفظ فوري صامت
            
            await self.save_session_progress(
                topic=self.session_data.get("current_topic", ""),
                words_discussed=self.session_data.get("words_discussed", []),
                last_position=self.session_data.get("last_position", ""),
                session_summary=f"حفظ فوري - {len(self.session_data.get('words_discussed', []))} كلمة"
            )
            
        except Exception as e:
            pass  # تجاهل الأخطاء
    
    async def continue_previous_topic(self):
        """متابعة الموضوع السابق من آخر نقطة توقف"""
        if not self.user_progress:
            return
        
        try:
            # تطبيق بيانات الموضوع السابق
            if self.user_progress.get('current_topic'):
                self.session_data["current_topic"] = self.user_progress.get('current_topic')
            if self.user_progress.get('last_position'):
                self.session_data["last_position"] = self.user_progress.get('last_position')
            if self.user_progress.get('vocabulary'):
                # استرجاع الكلمات المتعلمة سابقاً
                learned_words = list(self.user_progress.get('vocabulary', {}).keys())
                self.session_data["words_discussed"] = learned_words
            
            print(f"[agent] تم استئناف الموضوع السابق: {self.session_data.get('current_topic')} من {self.session_data.get('last_position')}")
            
            # زيادة عداد الرسائل والحفظ التلقائي كل 3 رسائل
            self._message_count += 1
            if self._message_count % 3 == 0:
                await self.auto_save_progress()
                print(f"[agent] حفظ تلقائي بعد {self._message_count} رسائل")
                
            # الحفظ الفوري إذا تم اكتشاف موضوع أو كلمات جديدة
            if (self.session_data.get("current_topic") and 
                self.session_data.get("words_discussed")):
                await self.force_save_progress(
                    topic=self.session_data.get("current_topic"),
                    words=self.session_data.get("words_discussed"),
                    position=self.session_data.get("last_position", "")
                )
            
        except Exception as e:
            print(f"[agent] خطأ في استئناف الموضوع السابق: {e}")
    
    async def start_new_topic(self, new_topic: str):
        """بدء موضوع جديد ومسح بيانات الجلسة القديمة"""
        try:
            # حفظ التقدم الحالي قبل المسح (إذا كان هناك تقدم)
            if self.session_data.get("current_topic") or self.session_data.get("words_discussed"):
                await self.save_session_progress(
                    topic=self.session_data.get("current_topic", ""),
                    words_discussed=self.session_data.get("words_discussed", []),
                    last_position=self.session_data.get("last_position", ""),
                    session_summary=f"انتهاء الموضوع السابق - {len(self.session_data.get('words_discussed', []))} كلمة"
                )
            
            # مسح بيانات الجلسة وبدء جديد
            self.session_data = {
                "session_id": str(datetime.now().timestamp()),
                "start_time": datetime.now().isoformat(),
                "words_discussed": [],
                "topics_covered": [],
                "current_topic": new_topic,
                "last_position": "بداية الموضوع"
            }
            
            # إعادة تعيين عداد الرسائل
            self._message_count = 0
            
            print(f"[agent] تم بدء موضوع جديد: {new_topic}")
            
        except Exception as e:
            print(f"[agent] خطأ في بدء الموضوع الجديد: {e}")


async def entrypoint(ctx: agents.JobContext):
    print("[agent] entrypoint: starting")
    
    # استخراج معلومات المستخدم من job metadata
    user_name = "المستخدم"  # قيمة افتراضية
    full_name = ""
    user_id = None
    mode = "normal"  # الوضع الافتراضي
    voice_name = "Aoede"  # 🎤 الصوت الافتراضي
    
    try:
        # محاولة قراءة metadata من job أولاً
        if ctx.job.metadata:
            print(f"[agent] job metadata موجود: {ctx.job.metadata}")
            metadata = json.loads(ctx.job.metadata)
            user_name = metadata.get("username", "المستخدم")
            full_name = metadata.get("full_name", user_name)
            user_id = metadata.get("user_id")
            mode = metadata.get("mode", "normal")
            voice_name = metadata.get("voice_name", "Aoede")  # 🎤 استخراج الصوت
            print(f"[agent] معلومات المستخدم من job: الاسم={user_name}, المعرف={user_id}, الوضع={mode}, الصوت={voice_name}")
        else:
            print("[agent] لا يوجد job metadata، محاولة قراءة room metadata...")
    except (json.JSONDecodeError, TypeError) as e:
        print(f"[agent] تعذر قراءة job metadata: {e}")
    
    # إذا لم نحصل على معلومات من job metadata، نحاول room metadata
    if user_name == "المستخدم":
        try:
            await ctx.connect()
            print("[agent] control plane connected")
            
            # محاولة قراءة room metadata
            room_metadata = ctx.room.metadata
            if room_metadata:
                print(f"[agent] room metadata موجود: {room_metadata}")
                metadata = json.loads(room_metadata)
                user_name = metadata.get("username", "المستخدم")
                full_name = metadata.get("full_name", user_name)
                user_id = metadata.get("user_id")
                mode = metadata.get("mode", "normal")
                voice_name = metadata.get("voice_name", "Aoede")  # 🎤 استخراج الصوت
                print(f"[agent] معلومات المستخدم من room: الاسم={user_name}, المعرف={user_id}, الوضع={mode}, الصوت={voice_name}")
            else:
                print("[agent] لا يوجد room metadata أيضاً")
        except Exception as room_error:
            print(f"[agent] تعذر قراءة room metadata: {room_error}")
    else:
        # افتح اتصال التحكم إذا لم يكن مفتوحاً بعد
        print(f"[agent] 🔍 DEBUG: URL={ctx._info.url}")
        print(f"[agent] 🔍 DEBUG: Room={ctx.room.name}")
        await ctx.connect()
        print("[agent] control plane connected")

    session = AgentSession()
    
    # إنشاء سياق محادثة أولي مع معلومات المستخدم
    initial_ctx = ChatContext()
    initial_ctx.add_message(
        role="system", 
        content=f"""معلومات المستخدم:
- الاسم الكامل: {full_name or user_name}
- معرف المستخدم: {user_id}
- أنت Friday، مساعد صوتي ذكي لتعليم اللغة الإنجليزية
- مهمتك الأساسية: تعليم اللغة الإنجليزية بطريقة تفاعلية وممتعة
- يجب أن تتذكر تقدم المستخدم وتستكمل من حيث توقف
- استخدم اسم المستخدم في جميع ردودك لجعل المحادثة شخصية
- كن مفيداً ومهذباً واستخدم الأدوات المتاحة عند الحاجة
- احتفظ بسجل الكلمات الجديدة والمواضيع المكتملة"""
    )

    # إنشاء مساعد مع نظام الذاكرة
    assistant = Assistant(
        chat_ctx=initial_ctx, 
        user_id=user_id, 
        user_name=full_name or user_name, 
        mode=mode,
        voice_name=voice_name  # 🎤 تمرير الصوت المختار
    )
    
    # تحميل ذاكرة المستخدم حسب الوضع
    if mode == "sentences_learning":
        await assistant.load_sentences_progress()
    elif mode == "english_conversation":
        print("[agent] وضع البودكاست - تحميل ذاكرة البودكاست")
        await assistant.load_podcast_progress()
    else:
        await assistant.load_user_memory()

    print("[agent] starting session for room")
    await session.start(
        room=ctx.room,
        agent=assistant,
        room_input_options=RoomInputOptions(
            # LiveKit Cloud enhanced noise cancellation
            # - If self-hosting, omit this parameter
            # - For telephony applications, use `BVCTelephony` for best results
            video_enabled=True,
            noise_cancellation=noise_cancellation.BVC(),
        ),
    )
    print("[agent] session started")

    # تحديد الرسالة الترحيبية بناءً على الوضع
    if mode == "english_conversation":
        # رسالة البودكاست تعتمد على التقدم المحمل
        if assistant.podcast_progress and assistant.podcast_progress.get('total_conversations', 0) > 0:
            # مستخدم عائد - استخدام البيانات المحملة
            last_topic = assistant.podcast_progress.get('last_topic', '')
            last_position = assistant.podcast_progress.get('last_position', '')
            total_conversations = assistant.podcast_progress.get('total_conversations', 0)
            
            if last_topic:
                welcome_message = f"Welcome back {full_name or user_name}! Last time we were talking about {last_topic}. {last_position} Would you like to continue that conversation or talk about something new?"
            else:
                welcome_message = f"Hello again {full_name or user_name}! Great to have you back for conversation #{total_conversations + 1}! What would you like to talk about today?"
        else:
            # مستخدم جديد - أول محادثة
            welcome_message = f"Hello {full_name or user_name}! I'm Friday, your English conversation partner. Let's practice speaking English together in a natural, friendly way. How are you feeling today? What would you like to talk about?"
    elif mode == "sentences_learning":
        # رسالة خاصة لتعليم الجمل البسيطة مع التحقق من التقدم
        welcome_message = f"مرحباً {full_name or user_name}! أنا Friday، مدرسك لتعليم الجمل الإنجليزية البسيطة.\n\n"
        
        # إضافة معلومات المستوى الحالي للسياق
        current_level = getattr(assistant, 'current_level', 1)
        learned_history = getattr(assistant, 'learned_sentences_history', [])
        
        # التحقق من وجود تقدم سابق في الجمل
        has_sentences_progress = (
            assistant.sentences_progress and 
            assistant.sentences_progress.get('completed_sentences', 0) > 0
        )
        
        if has_sentences_progress:
            completed = assistant.sentences_progress.get('completed_sentences', 0)
            generated_sentences = assistant.sentences_progress.get('generated_sentences', [])
            actual_total = len(generated_sentences)
            
            # التحقق من وجود جمل غير مكتملة
            has_incomplete_sentences = completed < actual_total
            
            if has_incomplete_sentences:
                # لا تزال هناك جمل لم تكتمل
                # استخدام current_sentence_index بدلاً من completed
                current_index = assistant.sentences_progress.get('current_sentence_index', completed)
                
                # تنظيف الجمل وإزالة أي عناصر فارغة أو مكررة
                clean_sentences = []
                seen_normalized = set()
                for sentence in generated_sentences:
                    if sentence and sentence.strip():
                        normalized = sentence.lower().replace('.', '').replace(',', '').strip()
                        if normalized not in seen_normalized:
                            clean_sentences.append(sentence.strip())
                            seen_normalized.add(normalized)
                
                # تحديث القائمة المنظفة
                if len(clean_sentences) != len(generated_sentences):
                    generated_sentences = clean_sentences
                    await supabase_manager.update_sentences_progress(
                        assistant.user_id,
                        assistant.sentences_session_id,
                        generated_sentences=generated_sentences,
                        total_sentences=len(generated_sentences)
                    )
                    print(f"[agent] تم تنظيف قائمة الجمل من {len(assistant.sentences_progress.get('generated_sentences', []))} إلى {len(generated_sentences)}")
                
                # عدم عرض الجمل القديمة - بدء بجمل جديدة مباشرة
                welcome_message += f"Welcome back! لقد تعلمت {completed} جملة في الجلسات السابقة. You're at level {current_level}!"
                welcome_message += "Let's continue with new sentences! لنبدأ بجمل جديدة..."
            else:
                # اكتمال جميع الجمل الموجودة
                total_learned = len(learned_history)
                welcome_message += f"Welcome back! Great progress! لقد أكملت {total_learned} جملة. You're at level {current_level}!"
                welcome_message += "Let's learn new sentences today! لنتعلم جمل جديدة..."
        else:
            welcome_message += "اليوم سنتعلم معاً جمل إنجليزية بسيطة ومفيدة. سأولد لك مجموعة من الجمل، وأعلمك كل جملة، وأطلب منك تكرارها. يمكنك طلب المزيد من الجمل في أي وقت!\n\n"
            welcome_message += "هل أنت جاهز لنبدأ بالجملة الأولى؟"
    else:
        # الرسالة الترحيبية العادية
        welcome_message = f"مرحباً {full_name or user_name}، اسمي Friday، مساعدك الشخصي لتعليم اللغة الإنجليزية."
        
        # التحقق من وجود تقدم سابق للمستخدم
        has_previous_progress = (
            assistant.user_progress and 
            assistant.user_progress.get('words_learned', 0) > 0 and
            assistant.user_progress.get('conversation_history')
        )
        
        if has_previous_progress:
            words_learned = assistant.user_progress.get('words_learned', 0)
            # البحث عن آخر موضوع من تاريخ المحادثات
            conversation_history = assistant.user_progress.get('conversation_history', {})
            last_topic = ""
            
            if conversation_history:
                # الحصول على آخر جلسة
                # عدم عرض الجمل القديمة - بدء بجمل جديدة مباشرة
                welcome_message += f" أهلاً بعودتك! لقد تعلمت {words_learned} كلمة حتى الآن."
                welcome_message += "هل تريد:1. متابعة من حيث توقفنا2. أم بدء موضوع جديدقل لي 'متابعة' أو 'موضوع جديد'."
        else:
            welcome_message += " مرحباً بك! سنبدأ رحلة تعلم الإنجليزية مع موضوع الأسماء (Nouns)."

    # إرسال الرسالة الترحيبية مباشرة عبر generate_reply
    print(f"[agent] إرسال الرسالة الترحيبية: {welcome_message}")
    await session.generate_reply(
        instructions=f"""قل هذه الرسالة بالضبط للمستخدم:
        "{welcome_message}"
        
        🔥🔥🔥 مهم جداً - توقف هنا تماماً! 🔥🔥🔥
        
        بعد قول الرسالة أعلاه:
        1. توقف عن الكلام تماماً
        2. انتظر رد المستخدم
        3. لا تتحدث مرة أخرى حتى يرد المستخدم
        4. لا تختار له ولا تفترض أي شيء
        5. اصمت تماماً وانتظر
        
        عندما يرد المستخدم، استمع بعناية لاختياره ثم تابع حسب اختياره فقط.""",
    )
    
    # ⚠️ مهم: لا نستدعي generate_reply مرة أخرى هنا!
    # السبب: AgentSession سيتعامل تلقائياً مع ردود المستخدم عبر معالجات الأحداث
    # إذا استدعينا generate_reply هنا، سيرسل AI رسالة ثانية فوراً قبل أن يرد المستخدم
    
    # إضافة معالج لحفظ التقدم عند انتهاء الجلسة
    def on_session_end():
        """حفظ التقدم عند انتهاء الجلسة (معالج متزامن)"""
        import asyncio
        
        async def save_progress():
            try:
                print("[agent] الجلسة تنتهي، حفظ التقدم النهائي...")
                
                # حفظ إحصائيات الجلسة (daily_stats)
                await assistant.end_session_summary()
                
                # حفظ التقدم العادي
                await assistant.auto_save_progress()
                
                # حفظ ملخص نهائي للجلسة
                final_summary = f"انتهت الجلسة - الموضوع: {assistant.session_data.get('current_topic', 'غير محدد')}, الكلمات المتعلمة: {len(assistant.session_data.get('words_discussed', []))}"
                await assistant.save_session_progress(session_summary=final_summary)
                print("[agent] ✅ تم حفظ جميع البيانات بنجاح")
            except Exception as e:
                print(f"[agent] خطأ في حفظ التقدم النهائي: {e}")
        
        # تشغيل الحفظ كمهمة غير متزامنة
        asyncio.create_task(save_progress())
    
    # ربط معالج انتهاء الجلسة ومعالجات الأحداث
    session.on("disconnected", on_session_end)
    
    # ربط معالجات الأحداث مع الجلسة بعد بدء الجلسة
    try:
        # استيراد أنواع الأحداث المطلوبة
        from livekit.agents import UserInputTranscribedEvent, ConversationItemAddedEvent
        
        # ربط معالج نسخ كلام المستخدم
        @session.on("user_input_transcribed")
        def on_user_input_transcribed(event: UserInputTranscribedEvent):
            import asyncio
            asyncio.create_task(assistant._on_user_input_transcribed(event))
        
        # ربط معالج إضافة عناصر المحادثة
        @session.on("conversation_item_added")
        def on_conversation_item_added(event: ConversationItemAddedEvent):
            import asyncio
            asyncio.create_task(assistant._on_conversation_item_added(event))
        
        assistant._events_bound = True
        print("[agent] تم ربط معالجات الأحداث الحديثة بنجاح مع الجلسة")
    except Exception as e:
        print(f"[agent] خطأ في ربط معالجات الأحداث: {e}")
        print("[agent] سيتم استخدام الحفظ الدوري فقط")
    
    # إضافة حفظ دوري تلقائي كل 60 ثانية (تحسين الأداء)
    import asyncio
    
    async def periodic_save():
        """حفظ دوري للتقدم - غير متزامن لتجنب مقاطعة الصوت"""
        # تأخير 60 ثانية قبل البدء لتحسين أداء البداية
        await asyncio.sleep(60)
        
        while True:
            try:
                await asyncio.sleep(60)  # كل 60 ثانية
                if assistant.session_data.get("current_topic") or assistant.session_data.get("words_discussed"):
                    # إنشاء task منفصل لعدم مقاطعة المحادثة
                    asyncio.create_task(assistant.auto_save_progress())
            except Exception as e:
                # تجاهل الأخطاء بصمت
                break
    
    # تشغيل الحفظ الدوري في الخلفية
    asyncio.create_task(periodic_save())
    
    # تم إزالة البيانات التجريبية - النظام سيتتبع التقدم الفعلي فقط


if __name__ == "__main__":
    agents.cli.run_app(
        agents.WorkerOptions(
            entrypoint_fnc=entrypoint,
            # اسم العامل ليتمكن الخادم من عمل Dispatch صريح له
            agent_name="sci-agent",  # ضروري لاستقبال dispatch requests!
            # منع تعارض منفذ خادم الصحة الافتراضي 8081 على ويندوز
            # 0 يعني اختيار منفذ حر تلقائياً
            port=0,
        )
    )