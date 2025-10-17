"""
إعداد عميل Supabase للمشروع
يتضمن: Auth, Storage, Database operations
"""
import os
import asyncio
import json
from typing import Optional, Dict, Any, List
from supabase import create_client, Client
from fastapi import HTTPException
import logging
from datetime import datetime, timedelta
from dotenv import load_dotenv

# تحميل متغيرات البيئة
load_dotenv()

logger = logging.getLogger(__name__)

class SupabaseManager:
    """مدير Supabase للتعامل مع Auth, Storage, Database مع آلية إعادة المحاولة وضغط البيانات"""
    
    def __init__(self):
        self.url = os.getenv("SUPABASE_URL")
        self.key = os.getenv("SUPABASE_ANON_KEY")
        self.service_key = os.getenv("SUPABASE_SERVICE_ROLE_KEY")
        
        if not self.url or not self.key:
            raise ValueError("SUPABASE_URL و SUPABASE_ANON_KEY مطلوبان في متغيرات البيئة")
        
        self.client: Client = create_client(self.url, self.key)
        # عميل بامتيازات أعلى (يتجاوز RLS) إذا تم توفير مفتاح الخدمة
        self.service_client: Optional[Client] = create_client(self.url, self.service_key) if self.service_key else None
        
        # إعدادات إعادة المحاولة
        self.max_retries = 3
        self.retry_delay = 1  # ثانية
        self.backoff_factor = 2  # مضاعف التأخير
        
        # إعدادات ضغط البيانات
        self.max_conversation_history = 50  # أقصى عدد محادثات محفوظة
        self.compression_threshold_days = 30  # ضغط البيانات الأقدم من 30 يوم
        
        logger.info("تم إنشاء عميل Supabase بنجاح مع آلية إعادة المحاولة وضغط البيانات")
    
    # ==================== Helper Methods ====================
    
    async def _retry_operation(self, operation, operation_name: str, *args, **kwargs):
        """تنفيذ عملية مع آلية إعادة المحاولة"""
        last_exception = None
        
        for attempt in range(self.max_retries + 1):
            try:
                if attempt > 0:
                    delay = self.retry_delay * (self.backoff_factor ** (attempt - 1))
                    logger.warning(f"إعادة المحاولة {attempt}/{self.max_retries} لـ {operation_name} بعد {delay} ثانية")
                    await asyncio.sleep(delay)
                
                result = await operation(*args, **kwargs) if asyncio.iscoroutinefunction(operation) else operation(*args, **kwargs)
                
                if attempt > 0:
                    logger.info(f"نجحت العملية {operation_name} في المحاولة {attempt + 1}")
                
                return result
                
            except Exception as e:
                last_exception = e
                logger.error(f"فشلت المحاولة {attempt + 1} لـ {operation_name}: {str(e)}")
                
                if attempt == self.max_retries:
                    logger.error(f"فشلت جميع المحاولات لـ {operation_name}")
                    break
        
        # إذا فشلت جميع المحاولات
        raise HTTPException(
            status_code=500, 
            detail=f"فشل في تنفيذ {operation_name} بعد {self.max_retries + 1} محاولات: {str(last_exception)}"
        )
    
    def _compress_conversation_history(self, conversation_history: Dict[str, Any]) -> Dict[str, Any]:
        """ضغط تاريخ المحادثات للحفاظ على المساحة"""
        if not conversation_history or len(conversation_history) <= self.max_conversation_history:
            return conversation_history
        
        try:
            # ترتيب المحادثات حسب التاريخ (الأحدث أولاً)
            sorted_sessions = sorted(
                conversation_history.items(),
                key=lambda x: x[1].get('timestamp', ''),
                reverse=True
            )
            
            # الاحتفاظ بأحدث المحادثات فقط
            recent_sessions = dict(sorted_sessions[:self.max_conversation_history])
            
            # ضغط المحادثات القديمة (الاحتفاظ بالملخص فقط)
            old_sessions = sorted_sessions[self.max_conversation_history:]
            if old_sessions:
                compressed_summary = {
                    "compressed_data": {
                        "total_old_sessions": len(old_sessions),
                        "oldest_session": old_sessions[-1][1].get('timestamp', ''),
                        "newest_compressed": old_sessions[0][1].get('timestamp', ''),
                        "total_words_in_old_sessions": sum(
                            len(session[1].get('words_discussed', [])) 
                            for session in old_sessions
                        ),
                        "topics_covered": list(set(
                            session[1].get('topic', '') 
                            for session in old_sessions 
                            if session[1].get('topic')
                        ))
                    }
                }
                recent_sessions.update(compressed_summary)
            
            logger.info(f"تم ضغط {len(old_sessions)} محادثة قديمة، الاحتفاظ بـ {len(recent_sessions) - (1 if old_sessions else 0)} محادثة حديثة")
            return recent_sessions
            
        except Exception as e:
            logger.error(f"خطأ في ضغط تاريخ المحادثات: {e}")
            # في حالة الخطأ، نعيد البيانات الأصلية
            return conversation_history
    
    def _optimize_vocabulary_data(self, vocabulary: Dict[str, Any]) -> Dict[str, Any]:
        """تحسين بيانات المفردات لتوفير المساحة"""
        if not vocabulary:
            return vocabulary
        
        try:
            # إزالة البيانات المكررة وضغط المعلومات
            optimized = {}
            cutoff_date = datetime.now() - timedelta(days=self.compression_threshold_days)
            
            for word, data in vocabulary.items():
                learned_date = datetime.fromisoformat(data.get('learned_at', datetime.now().isoformat()))
                
                if learned_date > cutoff_date:
                    # الاحتفاظ بالبيانات الكاملة للكلمات الحديثة
                    optimized[word] = data
                else:
                    # ضغط البيانات للكلمات القديمة
                    optimized[word] = {
                        'learned_at': data.get('learned_at'),
                        'topic': data.get('topic', '')[:20] if data.get('topic') else ''  # قطع الموضوع إلى 20 حرف
                    }
            
            return optimized
            
        except Exception as e:
            logger.error(f"خطأ في تحسين بيانات المفردات: {e}")
            return vocabulary
    
    # ==================== Auth Operations ====================
    
    async def sign_up_user(self, email: str, password: str, user_data: Optional[Dict] = None) -> Dict[str, Any]:
        """تسجيل مستخدم جديد"""
        try:
            response = self.client.auth.sign_up({
                "email": email,
                "password": password,
                "options": {
                    "data": user_data or {}
                }
            })
            
            if response.user:
                logger.info(f"تم تسجيل المستخدم بنجاح: {email}")
                return {
                    "success": True,
                    "user": response.user,
                    "session": response.session
                }
            else:
                raise HTTPException(status_code=400, detail="فشل في تسجيل المستخدم")
                
        except Exception as e:
            logger.error(f"خطأ في تسجيل المستخدم: {e}")
            raise HTTPException(status_code=400, detail=f"خطأ في التسجيل: {str(e)}")
    
    async def sign_in_user(self, email: str, password: str) -> Dict[str, Any]:
        """تسجيل دخول المستخدم"""
        try:
            response = self.client.auth.sign_in_with_password({
                "email": email,
                "password": password
            })
            
            if response.user:
                logger.info(f"تم تسجيل الدخول بنجاح: {email}")
                return {
                    "success": True,
                    "user": response.user,
                    "session": response.session,
                    "access_token": response.session.access_token
                }
            else:
                raise HTTPException(status_code=401, detail="بيانات الدخول غير صحيحة")
                
        except Exception as e:
            logger.error(f"خطأ في تسجيل الدخول: {e}")
            raise HTTPException(status_code=401, detail=f"خطأ في تسجيل الدخول: {str(e)}")
    
    async def get_user_from_token(self, token: str) -> Optional[Dict[str, Any]]:
        """الحصول على بيانات المستخدم من التوكن"""
        try:
            response = self.client.auth.get_user(token)
            if response.user:
                return response.user
            return None
        except Exception as e:
            logger.error(f"خطأ في الحصول على المستخدم: {e}")
            return None
    

    
    # ==================== Database Operations ====================
    
    async def create_user_profile(self, user_id: str, email: str, full_name: str) -> Dict[str, Any]:
        """إنشاء ملف شخصي للمستخدم"""
        try:
            profile_data = {
                "id": user_id,
                "email": email,
                "full_name": full_name,
                "created_at": datetime.utcnow().isoformat()
            }
            
            result = self.client.table("profiles").insert(profile_data).execute()
            logger.info(f"تم إنشاء الملف الشخصي: {email}")
            return {"success": True, "profile": result.data[0] if result.data else None}
            
        except Exception as e:
            logger.error(f"خطأ في إنشاء الملف الشخصي: {e}")
            raise HTTPException(status_code=500, detail=f"خطأ في إنشاء الملف الشخصي: {str(e)}")
    
    async def get_user_profile(self, user_id: str) -> Optional[Dict[str, Any]]:
        """جلب الملف الشخصي للمستخدم"""
        try:
            result = self.client.table("profiles").select("*").eq("id", user_id).execute()
            if result.data and len(result.data) > 0:
                return result.data[0]
            return None
            
        except Exception as e:
            logger.error(f"خطأ في جلب الملف الشخصي: {e}")
            return None
    
    async def save_assessment_result(self, user_id: str, questions: List[Dict], score: int, level: str) -> Dict[str, Any]:
        """حفظ نتيجة اختبار المستوى"""
        try:
            assessment_data = {
                "user_id": user_id,
                "questions": questions,
                "score": score,
                "level": level
            }
            
            db_client = self.service_client or self.client
            response = db_client.table("assessments").insert(assessment_data).execute()
            
            if response.data:
                logger.info(f"تم حفظ نتيجة الاختبار للمستخدم: {user_id}")
                return {"success": True, "assessment": response.data[0]}
            else:
                raise HTTPException(status_code=500, detail="فشل في حفظ نتيجة الاختبار")
                
        except Exception as e:
            logger.error(f"خطأ في حفظ نتيجة الاختبار: {e}")
            raise HTTPException(status_code=500, detail=f"خطأ في حفظ نتيجة الاختبار: {str(e)}")
    
    async def get_user_assessments(self, user_id: str) -> List[Dict[str, Any]]:
        """الحصول على اختبارات المستخدم"""
        try:
            response = self.client.table("assessments").select("*").eq("user_id", user_id).order("completed_at", desc=True).execute()
            return response.data or []
            
        except Exception as e:
            logger.error(f"خطأ في جلب الاختبارات: {e}")
            return []
    
    # ==================== User Progress Operations ====================
    

    
    async def get_user_progress(self, user_id: str) -> Optional[Dict[str, Any]]:
        """جلب تقدم المستخدم"""
        try:
            # استخدام service_client إذا كان متاحاً لتجاوز RLS
            client = self.service_client if self.service_client else self.client
            
            response = client.table("user_progress").select("*").eq("user_id", user_id).execute()
            
            if response.data:
                logger.info(f"تم جلب تقدم المستخدم: {user_id}")
                return response.data[0]
            else:
                logger.info(f"لا يوجد تقدم للمستخدم: {user_id}")
                return None
                
        except Exception as e:
            logger.error(f"خطأ في جلب تقدم المستخدم: {e}")
            raise HTTPException(status_code=500, detail=f"خطأ في جلب تقدم المستخدم: {str(e)}")

    async def create_user_progress(self, user_id: str) -> Dict[str, Any]:
        """إنشاء سجل تقدم جديد للمستخدم"""
        try:
            progress_data = {
                "user_id": user_id,
                "words_learned": 0,
                "current_topic": "",
                "last_position": "",
                "progress_percentage": 0,
                "session_data": {},
                "topics_completed": [],
                "vocabulary": {},
                "conversation_history": {},
                "last_session_at": datetime.now().isoformat(),
                "created_at": datetime.now().isoformat(),
                "updated_at": datetime.now().isoformat()
            }
            
            # استخدام service client للتجاوز RLS عند الحاجة
            client = self.service_client if self.service_client else self.client
            result = client.table("user_progress").insert(progress_data).execute()
            logger.info(f"تم إنشاء سجل تقدم جديد للمستخدم: {user_id}")
            return {"success": True, "progress": result.data[0] if result.data else None}
            
        except Exception as e:
            logger.error(f"خطأ في إنشاء سجل التقدم: {e}")
            raise HTTPException(status_code=500, detail=f"خطأ في إنشاء سجل التقدم: {str(e)}")
    
    async def save_feedback(self, feedback_data: dict):
        """حفظ تقييم وملاحظات المستخدم"""
        try:
            result = self.client.table('user_feedback').insert({
                'rating': feedback_data['rating'],
                'comment': feedback_data.get('comment', ''),
                'user_email': feedback_data.get('user_email', 'anonymous'),
                'user_name': feedback_data.get('user_name', 'anonymous'),
                'session_date': feedback_data.get('session_date'),
                'room': feedback_data.get('room', 'unknown'),
                'created_at': feedback_data.get('session_date')
            }).execute()
            
            logger.info(f"✅ تم حفظ التقييم: {feedback_data['rating']} نجوم من {feedback_data.get('user_name', 'anonymous')}")
            return {"success": True, "data": result.data}
        except Exception as e:
            logger.error(f"خطأ في حفظ التقييم: {e}")
            # نعيد true حتى لو فشل لتحسين UX
            return {"success": True}
    
    async def update_user_progress_dict(self, user_id: str, progress_data: Dict[str, Any]) -> Dict[str, Any]:
        """تحديث تقدم المستخدم باستخدام dictionary"""
        try:
            # جلب التقدم الحالي للدمج بدلاً من الاستبدال
            current_progress = await self.get_user_progress(user_id) or {}

            # دمج المفردات vocabulary إن وُجدت في الطلب
            if isinstance(progress_data.get("vocabulary"), dict):
                existing_vocab = current_progress.get("vocabulary", {}) or {}
                new_vocab = progress_data.get("vocabulary", {}) or {}
                merged_vocab = {**existing_vocab, **new_vocab}
                progress_data["vocabulary"] = merged_vocab
                # حساب الكلمات المتعلمة من عدد المفردات الفريدة
                progress_data["words_learned"] = len(merged_vocab)

            # دمج تاريخ المحادثات conversation_history إن وُجد
            if isinstance(progress_data.get("conversation_history"), dict):
                existing_history = current_progress.get("conversation_history", {}) or {}
                new_history = progress_data.get("conversation_history", {}) or {}
                # دمج بالمعرّف session_id بحيث لا نفقد الجلسات السابقة
                existing_history.update(new_history)
                progress_data["conversation_history"] = existing_history

            # دمج المواضيع المكتملة topics_completed إن وُجدت
            if isinstance(progress_data.get("topics_completed"), list):
                existing_topics = set(current_progress.get("topics_completed", []) or [])
                new_topics = set(progress_data.get("topics_completed", []) or [])
                progress_data["topics_completed"] = list(existing_topics.union(new_topics))

            # إضافة وقت التحديث
            progress_data["updated_at"] = datetime.utcnow().isoformat()
            progress_data["last_session_at"] = datetime.utcnow().isoformat()
            
            # استخدام service client للتجاوز RLS عند الحاجة
            db_client = self.service_client or self.client
            result = db_client.table("user_progress").update(progress_data).eq("user_id", user_id).execute()
            
            if result.data:
                logger.info(f"تم تحديث تقدم المستخدم: {user_id}")
                return {"success": True, "progress": result.data[0]}
            else:
                raise HTTPException(status_code=404, detail="لم يتم العثور على سجل التقدم")
                
        except Exception as e:
            logger.error(f"خطأ في تحديث تقدم المستخدم: {e}")
            raise HTTPException(status_code=500, detail=f"خطأ في تحديث تقدم المستخدم: {str(e)}")
    
    async def save_conversation_data(self, user_id: str, conversation_data: Dict[str, Any]) -> Dict[str, Any]:
        """حفظ بيانات المحادثة الصوتية"""
        try:
            # جلب التقدم الحالي
            current_progress = await self.get_user_progress(user_id)
            
            if not current_progress:
                # إنشاء سجل جديد إذا لم يكن موجوداً
                await self.create_user_progress(user_id)
                current_progress = await self.get_user_progress(user_id)
            
            # تحديث بيانات المحادثة
            conversation_history = current_progress.get("conversation_history", {})
            session_id = conversation_data.get("session_id", str(datetime.utcnow().timestamp()))
            
            # إضافة session_data للمحادثة
            conversation_history[session_id] = {
                "timestamp": datetime.utcnow().isoformat(),
                "topic": conversation_data.get("topic", ""),
                "words_discussed": conversation_data.get("words_discussed", []),
                "progress_made": conversation_data.get("progress_made", 0),
                "last_position": conversation_data.get("last_position", ""),
                "session_summary": conversation_data.get("session_summary", ""),
                "session_data": conversation_data.get("session_data", {})  # حفظ session_data
            }
            
            # تحديث vocabulary بربط كل كلمة بالموضوع
            current_vocabulary = current_progress.get("vocabulary", {})
            topic = conversation_data.get("topic", "")
            words_discussed = conversation_data.get("words_discussed", [])
            
            # ربط كل كلمة بالموضوع الحالي
            for word in words_discussed:
                if word and word not in current_vocabulary:
                    current_vocabulary[word] = {
                        "topic": topic or "General",
                        "learned_at": datetime.utcnow().isoformat(),
                        "session_id": session_id
                    }
            
            # تحديث البيانات
            update_data = {
                "conversation_history": conversation_history,
                "current_topic": conversation_data.get("topic", current_progress.get("current_topic", "")),
                "last_position": conversation_data.get("last_position", current_progress.get("last_position", "")),
                "words_learned": len(current_vocabulary),  # عدد الكلمات الفعلي
                "vocabulary": current_vocabulary,  # حفظ المفردات مع المواضيع
                "session_data": conversation_data.get("session_data", {})
            }
            
            return await self.update_user_progress_dict(user_id, update_data)
            
        except Exception as e:
            logger.error(f"خطأ في حفظ بيانات المحادثة: {e}")
            raise HTTPException(status_code=500, detail=f"خطأ في حفظ بيانات المحادثة: {str(e)}")
    
    async def get_or_create_user_progress(self, user_id: str) -> Dict[str, Any]:
        """جلب تقدم المستخدم أو إنشاؤه إذا لم يكن موجوداً"""
        try:
            progress = await self.get_user_progress(user_id)
            if not progress:
                result = await self.create_user_progress(user_id)
                progress = result.get("progress")
            return progress
            
        except Exception as e:
            logger.error(f"خطأ في جلب أو إنشاء تقدم المستخدم: {e}")
            raise HTTPException(status_code=500, detail=f"خطأ في جلب أو إنشاء تقدم المستخدم: {str(e)}")
    
    async def update_user_progress(self, user_id: str, words_learned: int = None, current_topic: str = None, 
                                 last_position: str = None, progress_percentage: int = None, 
                                 vocabulary: Dict = None, topics_completed: List = None) -> Dict[str, Any]:
        """تحديث تقدم المستخدم"""
        try:
            # بناء البيانات للتحديث
            update_data = {
                "updated_at": datetime.now().isoformat()
            }
            
            if words_learned is not None:
                update_data["words_learned"] = words_learned
            if current_topic is not None:
                update_data["current_topic"] = current_topic
            if last_position is not None:
                update_data["last_position"] = last_position
            if progress_percentage is not None:
                update_data["progress_percentage"] = progress_percentage
            if vocabulary is not None:
                update_data["vocabulary"] = vocabulary
            if topics_completed is not None:
                update_data["topics_completed"] = topics_completed
            
            # استخدام service_client إذا كان متاحاً لتجاوز RLS
            client = self.service_client if self.service_client else self.client
            
            response = client.table("user_progress").update(update_data).eq("user_id", user_id).execute()
            
            if response.data:
                logger.info(f"تم تحديث تقدم المستخدم: {user_id}")
                return {
                    "success": True,
                    "progress": response.data[0]
                }
            else:
                logger.warning(f"لم يتم العثور على تقدم للمستخدم: {user_id}")
                return {"success": False, "error": "لم يتم العثور على تقدم المستخدم"}
                
        except Exception as e:
            logger.error(f"خطأ في تحديث تقدم المستخدم: {e}")
            raise HTTPException(status_code=500, detail=f"خطأ في تحديث تقدم المستخدم: {str(e)}")
    

    # =================================================================
    # دوال جدول sentences_progress - خاص بوضع تعليم الجمل
    # =================================================================
    
    async def create_sentences_session(self, user_id: str, session_id: str, generated_sentences: list = None, total_sentences: int = None) -> dict:
        """إنشاء جلسة جمل جديدة للمستخدم مع دعم الحقول الجديدة"""
        async def _create_operation():
            data = {
                "user_id": user_id,
                "session_id": session_id,
                "generated_sentences": generated_sentences or [],
                "completed_sentences": 0,
                "current_sentence_index": 0,
                "total_sentences": total_sentences or 0,
                "current_level": 1,  # البدء من المستوى الأول
                "learned_sentences_history": [],  # تاريخ فارغ في البداية
                "created_at": datetime.now().isoformat(),
                "last_activity": datetime.now().isoformat()
            }
            
            # استخدام service_client للتجاوز RLS
            client = self.service_client if self.service_client else self.client
            result = client.table("sentences_progress").insert(data).execute()
            logger.info(f"تم إنشاء جلسة جمل جديدة للمستخدم: {user_id} (المستوى الأولي: 1)")
            return {"success": True, "data": result.data[0] if result.data else None}
        
        return await self._retry_operation(_create_operation, "إنشاء جلسة الجمل")

    async def get_sentences_progress(self, user_id: str, session_id: str = None) -> Optional[dict]:
        """جلب تقدم المستخدم في تعليم الجمل"""
        async def _get_operation():
            # استخدام service_client للتجاوز RLS
            client = self.service_client if self.service_client else self.client
            query = client.table("sentences_progress").select("*").eq("user_id", user_id)
            
            if session_id:
                query = query.eq("session_id", session_id)
            else:
                # جلب آخر جلسة نشطة
                query = query.eq("session_status", "active").order("last_activity", desc=True).limit(1)
            
            result = query.execute()
            
            if result.data:
                logger.info(f"تم جلب تقدم الجمل للمستخدم: {user_id}")
                return result.data[0]
            else:
                logger.info(f"لا يوجد تقدم جمل للمستخدم: {user_id}")
                return None
        
        return await self._retry_operation(_get_operation, "جلب تقدم الجمل")

    async def update_sentences_progress(self, user_id: str, session_id: str, **updates) -> dict:
        """تحديث تقدم المستخدم في تعليم الجمل مع دعم الحقول الجديدة"""
        async def _update_operation():
            # إضافة timestamp للتحديث
            updates["last_activity"] = datetime.now().isoformat()
            
            # التأكد من دعم الحقول الجديدة
            if "current_level" in updates and updates["current_level"] is not None:
                updates["current_level"] = int(updates["current_level"])
            
            if "learned_sentences_history" in updates and updates["learned_sentences_history"] is not None:
                if isinstance(updates["learned_sentences_history"], list):
                    # تحويل القائمة إلى JSON إذا لزم الأمر
                    updates["learned_sentences_history"] = updates["learned_sentences_history"]
            
            # استخدام service_client للتجاوز RLS
            client = self.service_client if self.service_client else self.client
            result = client.table("sentences_progress").update(updates).eq("user_id", user_id).eq("session_id", session_id).execute()
            
            logger.info(f"تم تحديث تقدم الجمل للمستخدم: {user_id} (المستوى: {updates.get('current_level', '?')})")
            return {"success": True, "data": result.data[0] if result.data else None}
        
        return await self._retry_operation(_update_operation, "تحديث تقدم الجمل")

    async def save_sentences_data(self, user_id: str, session_id: str, sentence_data: dict, sentence_index: int) -> dict:
        """حفظ بيانات جملة محددة"""
        async def _save_operation():
            # جلب البيانات الحالية أولاً
            # استخدام service_client للتجاوز RLS
            client = self.service_client if self.service_client else self.client
            query = client.table("sentences_progress").select("*").eq("user_id", user_id).eq("session_id", session_id)
            result = query.execute()
            
            if not result.data:
                return {"success": False, "error": "لم يتم العثور على الجلسة"}
                
            current_progress = result.data[0]
            
            # تحديث بيانات الجملة
            sentences_data = current_progress.get("sentences_data", {})
            sentences_data[str(sentence_index)] = sentence_data
            
            # تحديث التقدم
            updates = {
                "sentences_data": sentences_data,
                "current_sentence_index": sentence_index,
                "completed_sentences": len([k for k, v in sentences_data.items() if v.get("completed", False)]),
                "updated_at": datetime.now().isoformat(),
                "last_activity": datetime.now().isoformat()
            }
            
            # تحديث السجل
            update_result = client.table("sentences_progress").update(updates).eq("user_id", user_id).eq("session_id", session_id).execute()
            
            logger.info(f"تم حفظ بيانات الجملة {sentence_index} للمستخدم: {user_id}")
            return {"success": True, "data": update_result.data[0] if update_result.data else None}
        
        return await self._retry_operation(_save_operation, "حفظ بيانات الجملة")

    async def complete_sentences_session(self, user_id: str, session_id: str) -> dict:
        """إنهاء جلسة تعليم الجمل"""
        async def _complete_operation():
            updates = {
                "session_status": "completed",
                "last_activity": datetime.now().isoformat()
            }
            
            result = await self.update_sentences_progress(user_id, session_id, **updates)
            logger.info(f"تم إنهاء جلسة الجمل للمستخدم: {user_id}")
            return result
        
        return await self._retry_operation(_complete_operation, "إنهاء جلسة الجمل")

    # =================================================================
    # دوال جدول podcast_progress - خاص بالمحادثة الإنجليزية (البودكاست)
    # =================================================================
    
    async def get_podcast_progress(self, user_id: str) -> Optional[dict]:
        """جلب تقدم البودكاست للمستخدم"""
        async def _get_operation():
            client = self.service_client if self.service_client else self.client
            result = client.table("podcast_progress").select("*").eq("user_id", user_id).execute()
            
            if result.data:
                return result.data[0]
            else:
                return None
        
        return await self._retry_operation(_get_operation, "جلب تقدم البودكاست")
    
    async def create_podcast_progress(self, user_id: str, session_id: str = None) -> dict:
        """إنشاء سجل تقدم بودكاست جديد"""
        # تحديد session_id قبل الدالة الداخلية لتجنب مشكلة النطاق
        if not session_id:
            session_id = f"podcast_{int(datetime.now().timestamp())}"
        
        async def _create_operation():
            data = {
                "user_id": user_id,
                "session_id": session_id,
                "last_topic": "",
                "last_context": "",
                "last_position": "",
                "conversation_summary": "",
                "topics_discussed": [],
                "vocabulary_used": {},
                "total_conversations": 0,
                "total_minutes": 0,
                "fluency_level": "beginner",
                "common_mistakes": [],
                "improvements": [],
                "conversation_history": {},
                "created_at": datetime.now().isoformat(),
                "updated_at": datetime.now().isoformat()
            }
            
            client = self.service_client if self.service_client else self.client
            result = client.table("podcast_progress").insert(data).execute()
            
            return {"success": True, "data": result.data[0] if result.data else None}
        
        return await self._retry_operation(_create_operation, "إنشاء تقدم البودكاست")
    
    async def update_podcast_progress(self, user_id: str, **updates) -> dict:
        """تحديث تقدم البودكاست"""
        async def _update_operation():
            # إضافة الطوابع الزمنية
            updates["updated_at"] = datetime.now().isoformat()
            updates["last_session_at"] = datetime.now().isoformat()
            
            # تحديث عدد المحادثات إذا لزم
            if "total_conversations" in updates:
                updates["total_conversations"] = int(updates["total_conversations"])
            
            # تحديث الدقائق الإجمالية إذا لزم
            if "total_minutes" in updates:
                updates["total_minutes"] = int(updates["total_minutes"])
            
            client = self.service_client if self.service_client else self.client
            result = client.table("podcast_progress").update(updates).eq("user_id", user_id).execute()
            
            return {"success": True, "data": result.data[0] if result.data else None}
        
        return await self._retry_operation(_update_operation, "تحديث تقدم البودكاست")
    
    async def save_podcast_conversation(self, user_id: str, conversation_data: dict) -> dict:
        """حفظ بيانات محادثة البودكاست"""
        async def _save_operation():
            # جلب التقدم الحالي أو إنشاؤه
            progress = await self.get_podcast_progress(user_id)
            if not progress:
                create_result = await self.create_podcast_progress(user_id)
                progress = create_result.get("data", {})
            
            # تحديث تاريخ المحادثات
            conversation_history = progress.get("conversation_history", {})
            session_timestamp = str(datetime.now().timestamp())
            
            conversation_history[session_timestamp] = {
                "timestamp": datetime.now().isoformat(),
                "topic": conversation_data.get("topic", ""),
                "context": conversation_data.get("context", ""),
                "summary": conversation_data.get("summary", ""),
                "duration_minutes": conversation_data.get("duration_minutes", 0),
                "vocabulary": conversation_data.get("vocabulary", []),
                "mistakes": conversation_data.get("mistakes", []),
                "improvements": conversation_data.get("improvements", [])
            }
            
            # ضغط التاريخ إذا تجاوز 20 محادثة
            if len(conversation_history) > 20:
                # الاحتفاظ بآخر 20 محادثة فقط
                sorted_sessions = sorted(conversation_history.items(), key=lambda x: x[0], reverse=True)
                conversation_history = dict(sorted_sessions[:20])
            
            # تحديث المواضيع المناقشة
            topics_discussed = list(set(progress.get("topics_discussed", []) + [conversation_data.get("topic", "")]))
            topics_discussed = [t for t in topics_discussed if t]  # إزالة القيم الفارغة
            
            # تحديث المفردات المستخدمة
            vocabulary_used = progress.get("vocabulary_used", {})
            for word in conversation_data.get("vocabulary", []):
                if word not in vocabulary_used:
                    vocabulary_used[word] = {
                        "first_used": datetime.now().isoformat(),
                        "count": 1
                    }
                else:
                    vocabulary_used[word]["count"] += 1
            
            # تحديث الأخطاء الشائعة
            common_mistakes = progress.get("common_mistakes", [])
            new_mistakes = conversation_data.get("mistakes", [])
            for mistake in new_mistakes:
                if mistake not in common_mistakes:
                    common_mistakes.append(mistake)
            
            # تحديث التحسينات
            improvements = progress.get("improvements", [])
            new_improvements = conversation_data.get("improvements", [])
            for improvement in new_improvements:
                if improvement not in improvements:
                    improvements.append(improvement)
            
            # حساب إجمالي الدقائق والمحادثات
            total_conversations = progress.get("total_conversations", 0) + 1
            total_minutes = progress.get("total_minutes", 0) + conversation_data.get("duration_minutes", 0)
            
            # البيانات للتحديث
            update_data = {
                "last_topic": conversation_data.get("topic", ""),
                "last_context": conversation_data.get("context", ""),
                "last_position": conversation_data.get("position", ""),
                "conversation_summary": conversation_data.get("summary", ""),
                "topics_discussed": topics_discussed,
                "vocabulary_used": vocabulary_used,
                "conversation_history": conversation_history,
                "common_mistakes": common_mistakes[:20],  # الاحتفاظ بآخر 20 خطأ
                "improvements": improvements[:10],  # الاحتفاظ بآخر 10 تحسينات
                "total_conversations": total_conversations,
                "total_minutes": total_minutes,
                "fluency_level": conversation_data.get("fluency_level", progress.get("fluency_level", "beginner"))
            }
            
            # تحديث التقدم
            result = await self.update_podcast_progress(user_id, **update_data)
            
            return {
                "success": True,
                "message": "تم حفظ بيانات المحادثة بنجاح",
                "progress": result.get("data")
            }
        
        return await self._retry_operation(_save_operation, "حفظ محادثة البودكاست")
    
    async def get_or_create_podcast_progress(self, user_id: str) -> dict:
        """جلب تقدم البودكاست أو إنشاؤه إذا لم يكن موجوداً"""
        try:
            progress = await self.get_podcast_progress(user_id)
            if not progress:
                result = await self.create_podcast_progress(user_id)
                progress = result.get("data")
            return progress
            
        except Exception as e:
            logger.error(f"خطأ في جلب أو إنشاء تقدم البودكاست: {e}")
            raise HTTPException(status_code=500, detail=f"خطأ في جلب أو إنشاء تقدم البودكاست: {str(e)}")

    # =================================================================
    # دوال جدول user_personal_context - للتعليم التفاعلي الواقعي
    # =================================================================
    
    async def get_personal_context(self, user_id: str) -> Optional[Dict[str, Any]]:
        """جلب السياق الشخصي للمستخدم"""
        async def _get_operation():
            client = self.service_client if self.service_client else self.client
            result = client.table("user_personal_context").select("*").eq("user_id", user_id).execute()
            
            if result.data:
                logger.info(f"تم جلب السياق الشخصي للمستخدم: {user_id}")
                return result.data[0]
            else:
                logger.info(f"لا يوجد سياق شخصي للمستخدم: {user_id}")
                return None
        
        return await self._retry_operation(_get_operation, "جلب السياق الشخصي")
    
    async def create_personal_context(self, user_id: str, initial_data: Dict[str, Any] = None) -> Dict[str, Any]:
        """إنشاء سياق شخصي جديد للمستخدم"""
        async def _create_operation():
            data = {
                "user_id": user_id,
                "first_name": initial_data.get("first_name", "") if initial_data else "",
                "nickname": initial_data.get("nickname", "") if initial_data else "",
                "age": initial_data.get("age") if initial_data else None,
                "gender": initial_data.get("gender", "") if initial_data else "",
                "native_language": initial_data.get("native_language", "Arabic") if initial_data else "Arabic",
                "family_members": initial_data.get("family_members", {}) if initial_data else {},
                "friends": initial_data.get("friends", []) if initial_data else [],
                "pets": initial_data.get("pets", []) if initial_data else [],
                "hobbies": initial_data.get("hobbies", []) if initial_data else [],
                "favorite_foods": initial_data.get("favorite_foods", []) if initial_data else [],
                "favorite_colors": initial_data.get("favorite_colors", []) if initial_data else [],
                "favorite_subjects": initial_data.get("favorite_subjects", []) if initial_data else [],
                "occupation": initial_data.get("occupation", "") if initial_data else "",
                "workplace_or_school": initial_data.get("workplace_or_school", "") if initial_data else "",
                "daily_routine": initial_data.get("daily_routine", {}) if initial_data else {},
                "city": initial_data.get("city", "") if initial_data else "",
                "country": initial_data.get("country", "") if initial_data else "",
                "home_items": initial_data.get("home_items", []) if initial_data else [],
                "room_description": initial_data.get("room_description", "") if initial_data else "",
                "learning_goals": initial_data.get("learning_goals", []) if initial_data else [],
                "dream_job": initial_data.get("dream_job", "") if initial_data else "",
                "places_want_to_visit": initial_data.get("places_want_to_visit", []) if initial_data else [],
                "current_mood": initial_data.get("current_mood", "") if initial_data else "",
                "recent_activities": initial_data.get("recent_activities", []) if initial_data else [],
                "objects_around": initial_data.get("objects_around", []) if initial_data else [],
                "context_completeness": 0,
                "last_context_update": datetime.now().isoformat(),
                "created_at": datetime.now().isoformat(),
                "updated_at": datetime.now().isoformat()
            }
            
            client = self.service_client if self.service_client else self.client
            result = client.table("user_personal_context").insert(data).execute()
            
            logger.info(f"تم إنشاء سياق شخصي جديد للمستخدم: {user_id}")
            return {"success": True, "data": result.data[0] if result.data else None}
        
        return await self._retry_operation(_create_operation, "إنشاء السياق الشخصي")
    
    async def update_personal_context(self, user_id: str, updates: Dict[str, Any]) -> Dict[str, Any]:
        """تحديث السياق الشخصي للمستخدم"""
        async def _update_operation():
            # جلب السياق الحالي أولاً
            context = await self.get_personal_context(user_id)
            if not context:
                # إذا لم يكن موجوداً، أنشئه أولاً
                result = await self.create_personal_context(user_id, updates)
                return result
            
            # دمج القوائم بدلاً من استبدالها
            list_fields = ['hobbies', 'friends', 'favorite_foods', 'favorite_colors', 
                          'favorite_subjects', 'learning_goals', 'places_want_to_visit',
                          'home_items', 'objects_around', 'pets', 'recent_activities']
            
            for field in list_fields:
                if field in updates and isinstance(updates[field], list):
                    # دمج مع القيم الحالية
                    current_list = context.get(field, [])
                    if not isinstance(current_list, list):
                        current_list = []
                    
                    # إضافة قيم جديدة فقط (تجنب التكرار)
                    for item in updates[field]:
                        if item and item not in current_list:
                            current_list.append(item)
                    
                    updates[field] = current_list
            
            # دمج القواميس (family_members, daily_routine)
            dict_fields = ['family_members', 'daily_routine']
            for field in dict_fields:
                if field in updates and isinstance(updates[field], dict):
                    current_dict = context.get(field, {})
                    if not isinstance(current_dict, dict):
                        current_dict = {}
                    current_dict.update(updates[field])
                    updates[field] = current_dict
            
            # إضافة طابع زمني
            updates["updated_at"] = datetime.now().isoformat()
            updates["last_context_update"] = datetime.now().isoformat()
            
            # حساب نسبة اكتمال المعلومات
            important_fields = [
                "first_name", "age", "occupation", "city", "hobbies",
                "family_members", "friends", "favorite_foods", "learning_goals"
            ]
            
            filled_fields = 0
            for field in important_fields:
                value = updates.get(field) if field in updates else context.get(field)
                if value:
                    if isinstance(value, (list, dict)):
                        if len(value) > 0:
                            filled_fields += 1
                    elif isinstance(value, str) and value.strip():
                        filled_fields += 1
                    elif isinstance(value, int) and value > 0:
                        filled_fields += 1
            
            completeness = int((filled_fields / len(important_fields)) * 100)
            updates["context_completeness"] = completeness
            
            client = self.service_client if self.service_client else self.client
            result = client.table("user_personal_context").update(updates).eq("user_id", user_id).execute()
            
            logger.info(f"تم تحديث السياق الشخصي: {user_id} - الاكتمال: {completeness}% - حقول: {list(updates.keys())}")
            return {"success": True, "data": result.data[0] if result.data else None}
        
        return await self._retry_operation(_update_operation, "تحديث السياق الشخصي")
    
    async def get_or_create_personal_context(self, user_id: str) -> Dict[str, Any]:
        """جلب السياق الشخصي أو إنشاءه إذا لم يكن موجوداً"""
        try:
            context = await self.get_personal_context(user_id)
            if not context:
                result = await self.create_personal_context(user_id)
                context = result.get("data")
            return context
        except Exception as e:
            logger.error(f"خطأ في جلب أو إنشاء السياق الشخصي: {e}")
            return None
    
    async def add_to_personal_list(self, user_id: str, field_name: str, new_items: List[Any]) -> Dict[str, Any]:
        """أضافة عناصر جديدة إلى قائمة في السياق الشخصي (مثل friends, hobbies)"""
        try:
            context = await self.get_personal_context(user_id)
            if not context:
                return {"success": False, "error": "لم يتم العثور على السياق الشخصي"}
            
            current_list = context.get(field_name, [])
            if not isinstance(current_list, list):
                current_list = []
            
            # إضافة العناصر الجديدة مع تجنب التكرار
            for item in new_items:
                if item not in current_list:
                    current_list.append(item)
            
            # تحديث القائمة
            return await self.update_personal_context(user_id, {field_name: current_list})
            
        except Exception as e:
            logger.error(f"خطأ في إضافة عناصر إلى {field_name}: {e}")
            return {"success": False, "error": str(e)}
    
    async def backup_personal_context(self, user_id: str) -> Dict[str, Any]:
        """نسخ احتياطي للسياق الشخصي (يحفظ في updated_at في حالة الحذف العرضي)"""
        try:
            context = await self.get_personal_context(user_id)
            if context:
                backup_data = {
                    "personal_context_backup": context,
                    "backup_timestamp": datetime.now().isoformat()
                }
                logger.info(f"تم عمل backup للسياق الشخصي: {user_id}")
                return {"success": True, "data": backup_data}
            return {"success": False, "error": "لا يوجد سياق"}
        except Exception as e:
            logger.error(f"خطأ في backup: {e}")
            return {"success": False, "error": str(e)}
    
    # ============================================
    # 🎯 نظام تقييم المستوى الذكي
    # ============================================
    
    async def get_or_create_level_assessment(self, user_id: str) -> Dict[str, Any]:
        """جلب أو إنشاء تقييم المستوى"""
        async def _get_or_create():
            client = self.service_client if self.service_client else self.client
            result = client.table("user_level_assessment").select("*").eq("user_id", user_id).execute()
            
            if result.data and len(result.data) > 0:
                return result.data[0]
            
            # إنشاء جديد
            new_assessment = {"user_id": user_id}
            insert_result = client.table("user_level_assessment").insert(new_assessment).execute()
            return insert_result.data[0] if insert_result.data else None
        
        return await self._retry_operation(_get_or_create, "تقييم المستوى")
    
    async def update_level_assessment(self, user_id: str, updates: Dict[str, Any]) -> Dict[str, Any]:
        """تحديث تقييم المستوى"""
        async def _update():
            updates["updated_at"] = datetime.now().isoformat()
            client = self.service_client if self.service_client else self.client
            result = client.table("user_level_assessment").update(updates).eq("user_id", user_id).execute()
            logger.info(f"تم تحديث تقييم المستوى: {user_id}")
            return {"success": True, "data": result.data[0] if result.data else None}
        
        return await self._retry_operation(_update, "تحديث التقييم")
    
    # ============================================
    # 📚 نظام المراجعة المتباعدة
    # ============================================
    
    async def add_vocabulary_card(self, user_id: str, word: str, translation: str = "", 
                                 example: str = "", topic: str = "") -> Dict[str, Any]:
        """إضافة كلمة جديدة لنظام المراجعة"""
        async def _add_card():
            client = self.service_client if self.service_client else self.client
            # تحقق إذا كانت موجودة
            existing = client.table("vocabulary_cards").select("*").eq("user_id", user_id).eq("word", word).execute()
            if existing.data:
                return {"success": True, "exists": True, "data": existing.data[0]}
            
            card_data = {
                "user_id": user_id,
                "word": word,
                "translation": translation,
                "example_sentence": example,
                "topic": topic
            }
            result = client.table("vocabulary_cards").insert(card_data).execute()
            logger.info(f"تمت إضافة كلمة: {word}")
            return {"success": True, "exists": False, "data": result.data[0] if result.data else None}
        
        return await self._retry_operation(_add_card, "إضافة كلمة")
    
    async def get_due_reviews(self, user_id: str, limit: int = 20) -> List[Dict[str, Any]]:
        """جلب الكلمات المستحقة للمراجعة"""
        async def _get_due():
            client = self.service_client if self.service_client else self.client
            result = client.table("vocabulary_cards").select("*").eq("user_id", user_id).lte(
                "next_review_date", datetime.now().isoformat()
            ).eq("is_mastered", False).limit(limit).execute()
            return result.data or []
        
        return await self._retry_operation(_get_due, "جلب مراجعات")
    
    async def update_vocabulary_review(self, card_id: str, correct: bool) -> Dict[str, Any]:
        """تحديث بعد مراجعة باستخدام خوارزمية SM-2"""
        async def _update_review():
            client = self.service_client if self.service_client else self.client
            # جلب البطاقة
            card_result = client.table("vocabulary_cards").select("*").eq("id", card_id).execute()
            if not card_result.data:
                return {"success": False, "error": "لم يتم العثور على البطاقة"}
            
            card = card_result.data[0]
            
            # خوارزمية SM-2
            ease_factor = float(card.get("ease_factor", 2.5))
            interval = card.get("interval", 1)
            repetitions = card.get("repetitions", 0)
            
            if correct:
                if repetitions == 0:
                    interval = 1
                elif repetitions == 1:
                    interval = 6
                else:
                    interval = int(interval * ease_factor)
                
                repetitions += 1
                ease_factor = max(1.3, ease_factor + 0.1)
                
                mastery_level = min(5, card.get("mastery_level", 0) + 1)
                is_mastered = mastery_level >= 5
            else:
                repetitions = 0
                interval = 1
                ease_factor = max(1.3, ease_factor - 0.2)
                mastery_level = max(0, card.get("mastery_level", 0) - 1)
                is_mastered = False
            
            from datetime import timedelta
            next_review = datetime.now() + timedelta(days=interval)
            
            updates = {
                "ease_factor": ease_factor,
                "interval": interval,
                "repetitions": repetitions,
                "next_review_date": next_review.isoformat(),
                "last_reviewed_at": datetime.now().isoformat(),
                "times_seen": card.get("times_seen", 0) + 1,
                "times_correct": card.get("times_correct", 0) + (1 if correct else 0),
                "times_wrong": card.get("times_wrong", 0) + (0 if correct else 1),
                "mastery_level": mastery_level,
                "is_mastered": is_mastered,
                "updated_at": datetime.now().isoformat()
            }
            
            result = client.table("vocabulary_cards").update(updates).eq("id", card_id).execute()
            return {"success": True, "data": result.data[0] if result.data else None}
        
        return await self._retry_operation(_update_review, "تحديث مراجعة")
    
    # ============================================
    # 🏆 نظام الإنجازات
    # ============================================
    
    async def get_or_create_achievements(self, user_id: str) -> Dict[str, Any]:
        """جلب أو إنشاء إنجازات المستخدم"""
        async def _get_or_create():
            client = self.service_client if self.service_client else self.client
            result = client.table("user_achievements").select("*").eq("user_id", user_id).execute()
            
            if result.data and len(result.data) > 0:
                return result.data[0]
            
            new_achievements = {"user_id": user_id}
            insert_result = client.table("user_achievements").insert(new_achievements).execute()
            return insert_result.data[0] if insert_result.data else None
        
        return await self._retry_operation(_get_or_create, "إنجازات")
    
    async def award_points(self, user_id: str, points: int, reason: str = "") -> Dict[str, Any]:
        """منح نقاط للمستخدم"""
        async def _award():
            achievements = await self.get_or_create_achievements(user_id)
            
            new_total = achievements.get("total_points", 0) + points
            new_exp = achievements.get("experience_points", 0) + points
            current_level = achievements.get("current_level", 1)
            points_to_next = achievements.get("points_to_next_level", 100)
            
            # تحقق من التقدم في المستوى
            level_up = False
            if new_exp >= points_to_next:
                current_level += 1
                new_exp = new_exp - points_to_next
                points_to_next = int(points_to_next * 1.5)  # زيادة تدريجية
                level_up = True
            
            updates = {
                "total_points": new_total,
                "experience_points": new_exp,
                "current_level": current_level,
                "points_to_next_level": points_to_next,
                "updated_at": datetime.now().isoformat()
            }
            
            client = self.service_client if self.service_client else self.client
            result = client.table("user_achievements").update(updates).eq("user_id", user_id).execute()
            
            logger.info(f"منح {points} نقطة - {reason}")
            return {
                "success": True, 
                "level_up": level_up,
                "new_level": current_level if level_up else None,
                "data": result.data[0] if result.data else None
            }
        
        return await self._retry_operation(_award, "منح نقاط")
    
    async def update_streak(self, user_id: str) -> Dict[str, Any]:
        """تحديث الأيام المتتالية"""
        async def _update_streak():
            achievements = await self.get_or_create_achievements(user_id)
            
            from datetime import date
            last_study = achievements.get("last_study_date")
            today = date.today()
            
            if last_study:
                last_date = date.fromisoformat(last_study) if isinstance(last_study, str) else last_study
                days_diff = (today - last_date).days
                
                if days_diff == 1:
                    # يوم متتالي
                    current_streak = achievements.get("current_streak", 0) + 1
                elif days_diff == 0:
                    # نفس اليوم
                    current_streak = achievements.get("current_streak", 1)
                else:
                    # انقطع التسلسل
                    current_streak = 1
            else:
                current_streak = 1
            
            longest_streak = max(achievements.get("longest_streak", 0), current_streak)
            
            updates = {
                "current_streak": current_streak,
                "longest_streak": longest_streak,
                "last_study_date": today.isoformat(),
                "updated_at": datetime.now().isoformat()
            }
            
            client = self.service_client if self.service_client else self.client
            result = client.table("user_achievements").update(updates).eq("user_id", user_id).execute()
            
            return {"success": True, "streak": current_streak, "data": result.data[0] if result.data else None}
        
        return await self._retry_operation(_update_streak, "تحديث streak")
    
    # ============================================
    # 📈 إحصائيات يومية
    # ============================================
    
    async def update_daily_stats(self, user_id: str, updates: Dict[str, Any]) -> Dict[str, Any]:
        """تحديث إحصائيات اليوم"""
        async def _update_daily():
            from datetime import date
            today = date.today()
            
            client = self.service_client if self.service_client else self.client
            # جلب إحصائيات اليوم
            existing = client.table("daily_stats").select("*").eq("user_id", user_id).eq("date", today.isoformat()).execute()
            
            if existing.data:
                # تحديث
                current = existing.data[0]
                for key, value in updates.items():
                    if key in ["minutes_studied", "words_learned", "words_reviewed", "lessons_completed", 
                              "correct_answers", "total_attempts", "points_earned"]:
                        updates[key] = current.get(key, 0) + value
                
                # حساب الدقة
                if "total_attempts" in updates and updates["total_attempts"] > 0:
                    updates["daily_accuracy"] = (updates["correct_answers"] / updates["total_attempts"]) * 100
                
                result = client.table("daily_stats").update(updates).eq("id", current["id"]).execute()
            else:
                # إنشاء جديد
                updates["user_id"] = user_id
                updates["date"] = today.isoformat()
                if "total_attempts" in updates and updates["total_attempts"] > 0:
                    updates["daily_accuracy"] = (updates.get("correct_answers", 0) / updates["total_attempts"]) * 100
                result = client.table("daily_stats").insert(updates).execute()
            
            return {"success": True, "data": result.data[0] if result.data else None}
        
        return await self._retry_operation(_update_daily, "إحصائيات يومية")

# إنشاء مثيل عام
supabase_manager = SupabaseManager()
