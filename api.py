import os
import sys
import time
import requests
import subprocess
from typing import Optional
import re
import unicodedata
from datetime import datetime

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Response, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, PlainTextResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from fastapi import File, UploadFile, Depends

# 🛡️ Security & Monitoring
import logging
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware

# LiveKit Python Server SDK (token generation)
# Docs: https://docs.livekit.io/python/livekit/api/access_token.html
from livekit import api

# Supabase and Auth imports
from supabase_client import supabase_manager
from auth import get_current_user, get_user_id_from_token

# Load environment variables from .env in project root
load_dotenv()

# ============================================
# 📝 Logging Configuration - تسجيل كل الأحداث
# ============================================
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('friday.log', encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# ============================================
# 🛡️ Rate Limiting - حماية من الهجمات
# ============================================
limiter = Limiter(key_func=get_remote_address, default_limits=["100/hour"])

logger.info("🚀 Friday API Server Starting...")
logger.info(f"🛡️ Rate Limiting: Enabled (100 requests/hour per IP)")
logger.info(f"📝 Logging: Enabled (friday.log)")

LIVEKIT_URL = os.getenv("LIVEKIT_URL")
LIVEKIT_API_KEY = os.getenv("LIVEKIT_API_KEY")
LIVEKIT_API_SECRET = os.getenv("LIVEKIT_API_SECRET")

# دعم LiveKit المحلي والكلاود
# إذا كان URL يبدأ بـ ws:// فهو محلي، إذا كان wss:// فهو كلاود
IS_LOCAL_LIVEKIT = LIVEKIT_URL and LIVEKIT_URL.startswith("ws://") if LIVEKIT_URL else False
if IS_LOCAL_LIVEKIT:
    print("\n" + "="*60)
    print("🏠 [LiveKit] يعمل على سيرفر محلي")
    print(f"📍 العنوان: {LIVEKIT_URL}")
    print("💰 التكلفة: $0 (مجاني!)")
    print("="*60 + "\n")
else:
    print(f"☁️ [LiveKit] يعمل على الكلاود - {LIVEKIT_URL}")

def sanitize_email(email: str) -> str:
    """تنظيف البريد الإلكتروني"""
    if not email:
        return ""
    
    # تحويل إلى نص وإزالة الفراغات
    email = str(email).strip()
    
    # تطبيع Unicode
    try:
        email = unicodedata.normalize('NFKC', email)
    except:
        pass
    
    # إزالة المحارف الخاصة والمسافات الإضافية
    email = re.sub(r'\s+', '', email)  # إزالة جميع المسافات
    email = re.sub(r'[^\w@.-]', '', email)  # الاحتفاظ فقط بالأحرف والأرقام و @ و . و -
    
    return email.lower()
# CORS Origins - يدعم localhost والنطاقات المنشورة
ALLOWED_ORIGINS = os.getenv(
    "ALLOWED_ORIGINS", 
    "http://localhost:5173,http://127.0.0.1:5173,http://localhost:8000,http://127.0.0.1:8000,https://*.railway.app,https://*.onrender.com,https://*.fly.dev"
)

app = FastAPI(title="SCI Token API", version="0.1.0")

# ============================================
# 🛡️ Security Middleware
# ============================================

# 1. Rate Limiting
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
app.add_middleware(SlowAPIMiddleware)

# 2. CORS setup (allow only specified origins for security)
origins = [o.strip() for o in ALLOWED_ORIGINS.split(",") if o.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,  # Only allow specified origins - SECURE
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 3. HTTPS Enforcement (Production only)
ENVIRONMENT = os.getenv("ENVIRONMENT", "development")
if ENVIRONMENT == "production":
    logger.info("🔒 HTTPS: Required in production mode")
    
    @app.middleware("http")
    async def enforce_https(request: Request, call_next):
        # إلزام HTTPS في الProduction
        if request.url.scheme != "https" and "localhost" not in request.url.hostname:
            logger.warning(f"⚠️ HTTP request blocked: {request.url}")
            return JSONResponse(
                status_code=403,
                content={"error": "HTTPS required. Please use https://"}
            )
        return await call_next(request)
else:
    logger.info("🛠️ Development mode: HTTPS not enforced")

# 4. Global Exception Handler
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.error(f"❌ Unhandled error: {exc}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={"error": "حدث خطأ غير متوقع. يرجى المحاولة لاحقاً."}
    )

logger.info(f"✅ Security configured: CORS={len(origins)} origins, Rate Limiting=ON, HTTPS={ENVIRONMENT}")

# تقديم الملفات الثابتة (CSS, JS, وغيرها)
app.mount("/static", StaticFiles(directory="."), name="static")

# تقديم ملفات CSS و JS مباشرة من المجلد الجذر
@app.get("/client.css")
async def get_client_css():
    return FileResponse("client.css", media_type="text/css")

@app.get("/client.js")
async def get_client_js():
    return FileResponse("client.js", media_type="application/javascript")

# ==================== LiveKit Agent Worker (embedded) ====================
_AGENT_PROC: Optional[subprocess.Popen] = None

def _spawn_agent_worker() -> None:
    global _AGENT_PROC
    try:
        if _AGENT_PROC is not None and _AGENT_PROC.poll() is None:
            return  # already running
        here = os.path.dirname(os.path.abspath(__file__))
        agent_path = os.path.join(here, "agent.py")
        # استخدم "start" لتشغيل العامل كـ worker إنتاجي (dev للّوغ التطويري)
        cmd = [sys.executable, agent_path, "start"]
        _AGENT_PROC = subprocess.Popen(
            cmd,
            cwd=here,
            env=os.environ.copy(),
            creationflags=0,
        )
        print(f"[startup] launched LiveKit agent worker (pid={_AGENT_PROC.pid})")
    except Exception as e:
        print(f"[startup] failed to launch agent worker: {e}")

def _stop_agent_worker() -> None:
    global _AGENT_PROC
    if _AGENT_PROC is None:
        return
    try:
        if _AGENT_PROC.poll() is None:
            _AGENT_PROC.terminate()
            try:
                _AGENT_PROC.wait(timeout=5)
            except Exception:
                _AGENT_PROC.kill()
        print("[shutdown] agent worker stopped")
    except Exception as e:
        print(f"[shutdown] error stopping agent worker: {e}")
    finally:
        _AGENT_PROC = None

@app.on_event("startup")
async def _on_startup():
    _spawn_agent_worker()

@app.on_event("shutdown")
async def _on_shutdown():
    _stop_agent_worker()

@app.get("/api/agent/status")
def agent_status() -> dict:
    """حالة عامل LiveKit المدمج."""
    pid = None
    running = False
    try:
        if _AGENT_PROC is not None:
            pid = _AGENT_PROC.pid
            running = _AGENT_PROC.poll() is None
    except Exception:
        pass
    return {"running": running, "pid": pid}


def _sanitize_email_text(value: Optional[str]) -> str:
    """
    تنقية قوية للبريد الإلكتروني:
    - Normalize NFKC
    - إزالة محارف الاتجاه (LRM/RLM/embeddings/isolates/ALM)
    - إزالة المحارف غير المرئية: ZERO-WIDTH (200B/200C/200D), FEFF, WORD JOINER (2060), 180E
    - إزالة كل الفراغات بما فيها NBSP
    - إزالة علامات الاقتباس المحيطة إن وجدت
    - trim + lower
    """
    if not value:
        return ""
    v = unicodedata.normalize('NFKC', value)
    # إزالة محارف الاتجاه
    bidi_codes = [
        0x200E, 0x200F,       # LRM, RLM
        0x202A, 0x202B, 0x202C, 0x202D, 0x202E,  # embeddings/overrides
        0x2066, 0x2067, 0x2068, 0x2069,          # isolates
        0x061C,                                    # ALM
    ]
    # إزالة محارف غير مرئية إضافية
    zero_width = [0x200B, 0x200C, 0x200D, 0xFEFF, 0x2060, 0x180E]
    tbl = {cp: None for cp in (bidi_codes + zero_width)}
    v = v.translate(tbl)
    # إزالة جميع الفراغات بما فيها NBSP
    v = re.sub(r"[\u00A0\s]+", "", v)
    # إزالة علامات اقتباس محيطة إن وُجدت
    v = re.sub(r"^['\"]+|['\"]+$", "", v)
    return v.strip().lower()


class TokenRequest(BaseModel):
    room: str
    identity: str
    name: Optional[str] = None

class StartVoiceAgentRequest(BaseModel):
    user_id: Optional[str] = None
    username: str
    full_name: Optional[str] = None
    room_name: Optional[str] = None
    mode: Optional[str] = "normal"  # إضافة حقل الوضع
    voice_name: Optional[str] = "Aoede"  # 🎤 الصوت المختار

class LiveKitTokenRequest(BaseModel):
    username: str
    room_name: str
    user_id: Optional[str] = None

# ==================== Supabase Auth Models ====================

class UserSignUpRequest(BaseModel):
    email: str
    password: str
    full_name: Optional[str] = ""

class UserSignInRequest(BaseModel):
    email: str
    password: str

class FeedbackRequest(BaseModel):
    rating: int
    comment: str = ""
    user_email: str = "anonymous"
    user_name: str = "anonymous"
    session_date: str
    room: str = "unknown"


@app.get("/")
def root():
    """يخدم صفحة العميل الرئيسية"""
    here = os.path.dirname(os.path.abspath(__file__))
    html_path = os.path.join(here, "client.html")
    return FileResponse(html_path)

@app.get("/client.html")
def client_page():
    """يخدم صفحة client.html"""
    here = os.path.dirname(os.path.abspath(__file__))
    html_path = os.path.join(here, "client.html")
    return FileResponse(html_path)

@app.get("/login")
def login_page():
    """يخدم صفحة تسجيل الدخول"""
    here = os.path.dirname(os.path.abspath(__file__))
    html_path = os.path.join(here, "login.html")
    return FileResponse(html_path)

@app.get("/login.html")
def login_html():
    """يخدم صفحة تسجيل الدخول"""
    here = os.path.dirname(os.path.abspath(__file__))
    html_path = os.path.join(here, "login.html")
    return FileResponse(html_path)

@app.get("/test_endpoints.html")
def test_endpoints():
    here = os.path.dirname(os.path.abspath(__file__))
    html_path = os.path.join(here, "test_endpoints.html")
    return FileResponse(html_path)

@app.get("/3000-sentences.html")
def sentences_3000_page():
    """يخدم صفحة 3000 جملة"""
    here = os.path.dirname(os.path.abspath(__file__))
    html_path = os.path.join(here, "3000-sentences.html")
    return FileResponse(html_path)

@app.get("/podcast.html")
def podcast_page():
    """يخدم صفحة البودكاست"""
    here = os.path.dirname(os.path.abspath(__file__))
    html_path = os.path.join(here, "podcast.html")
    return FileResponse(html_path)

@app.get("/sentences-client.js")
def sentences_client_js():
    """يخدم ملف JavaScript الخاص بصفحة الجمل"""
    here = os.path.dirname(os.path.abspath(__file__))
    js_path = os.path.join(here, "sentences-client.js")
    return FileResponse(js_path, media_type="application/javascript")

@app.get("/podcast-client.js")
def podcast_client_js():
    """يخدم ملف JavaScript الخاص بصفحة المحادثة الإنجليزية"""
    here = os.path.dirname(os.path.abspath(__file__))
    js_path = os.path.join(here, "podcast-client.js")
    return FileResponse(js_path, media_type="application/javascript")

# ==================== PWA Support ====================
@app.get("/manifest.json")
def serve_manifest():
    """يخدم PWA manifest"""
    here = os.path.dirname(os.path.abspath(__file__))
    manifest_path = os.path.join(here, "manifest.json")
    return FileResponse(manifest_path, media_type="application/json")

@app.get("/service-worker.js")
def serve_service_worker():
    """يخدم Service Worker"""
    here = os.path.dirname(os.path.abspath(__file__))
    sw_path = os.path.join(here, "service-worker.js")
    return FileResponse(sw_path, media_type="application/javascript")

@app.get("/api/simple-sentences")
def get_simple_sentences():
    """إرجاع قائمة الجمل البسيطة العشرة"""
    from sentences import get_sentences
    return {"success": True, "sentences": get_sentences()}

@app.get("/health")
def health() -> dict:
    return {"status": "ok"}

@app.post("/api/feedback")
async def save_feedback(feedback: FeedbackRequest) -> dict:
    """حفظ تقييم المستخدم"""
    try:
        # حفظ في Supabase
        result = await supabase_manager.save_feedback({
            "rating": feedback.rating,
            "comment": feedback.comment,
            "user_email": feedback.user_email,
            "user_name": feedback.user_name,
            "session_date": feedback.session_date,
            "room": feedback.room
        })
        
        return {"success": True, "message": "تم حفظ التقييم بنجاح"}
    except Exception as e:
        logger.error(f"خطأ في حفظ التقييم: {e}")
        return {"success": True, "message": "شكراً"}

@app.post("/api/reset_progress/{user_id}")
async def reset_user_progress(user_id: str) -> dict:
    """مسح وإعادة تعيين تقدم المستخدم"""
    try:
        # إعادة تعيين التقدم باستخدام تحديث البيانات بقيم فارغة
        reset_data = {
            "words_learned": 0,
            "current_topic": "",
            "last_position": "",
            "progress_percentage": 0,
            "session_data": {},
            "topics_completed": [],
            "vocabulary": {},
            "conversation_history": {}
        }
        
        # محاولة تحديث السجل الموجود أولاً
        try:
            result = await supabase_manager.update_user_progress_dict(user_id, reset_data)
            return {"success": True, "message": "تم إعادة تعيين تقدم المستخدم بنجاح", "progress": result.get("progress")}
        except:
            # إذا لم يكن السجل موجود، إنشاء سجل جديد
            result = await supabase_manager.create_user_progress(user_id)
            if result and result.get("success"):
                return {"success": True, "message": "تم إعادة تعيين تقدم المستخدم بنجاح", "progress": result.get("progress")}
            else:
                raise Exception("فشل في إعادة تعيين التقدم")
            
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"خطأ في إعادة تعيين التقدم: {str(e)}")


@app.get("/favicon.ico")
def favicon() -> Response:
    # silence 404 in dev; browsers often request this automatically
    return Response(status_code=204)


@app.get("/sw.js")
def service_worker() -> PlainTextResponse:
    # silence 404 in dev; some environments try to load a service worker
    return PlainTextResponse("/* no-op service worker */", media_type="application/javascript")


@app.get("/livekit-client.esm.min.js")
def serve_livekit_client() -> FileResponse:
    """
    يخدم نسخة محلية من livekit-client.esm.min.js.
    إذا لم تكن موجودة، يحاول تنزيلها من CDN وحفظها بالجذر لتجاوز حجب المتصفح.
    """
    here = os.path.dirname(os.path.abspath(__file__))
    js_path = os.path.join(here, "livekit-client.esm.min.js")
    if not os.path.exists(js_path) or os.path.getsize(js_path) < 10_000:
        sources = [
            "https://cdn.jsdelivr.net/npm/livekit-client@2.15.4/dist/livekit-client.esm.min.js",
            "https://unpkg.com/livekit-client@2.15.4/dist/livekit-client.esm.min.js",
        ]
        last_err = None
        for u in sources:
            try:
                r = requests.get(u, timeout=20)
                r.raise_for_status()
                with open(js_path, "wb") as f:
                    f.write(r.content)
                break
            except Exception as e:
                last_err = e
        if not os.path.exists(js_path):
            raise HTTPException(status_code=502, detail=f"Failed to fetch LiveKit client: {last_err}")
    return FileResponse(js_path, media_type="application/javascript")


@app.post("/api/start_voice_agent")
async def start_voice_agent(req: StartVoiceAgentRequest) -> dict:
    """تهيئة غرفة وطلب Dispatch صريح لعامل LiveKit باسم sci-agent.

    - إن أرسل العميل room_name نستخدمه بعد تنقيته، وإلا ننشئ اسمًا فريدًا.
    المخرجات:
    - success: نجاح العملية من عدمه
    - room_name: اسم الغرفة المستهدفة/الجاهزة
    - dispatched: هل تم إرسال طلب Dispatch بنجاح
    - dispatch_error: رسالة الخطأ إن وجد
    """
    logger.info(f"🎤 Voice session request: user={req.username}, mode={req.mode}")
    username = (req.username or "user").strip()
    safe_user = "".join(c for c in username if c.isalnum() or c in ("_", "-")).strip("_-") or "user"
    # استخدم room_name القادم من العميل إن وُجد وإلا أنشئ اسمًا فريدًا
    requested_room = (req.room_name or "").strip()
    base_room = requested_room if requested_room else f"abedin_{safe_user}_{int(time.time())}"
    room_name = "".join(c for c in base_room if c.isalnum() or c in ("_", "-")).strip("_-") or f"abedin_{safe_user}_{int(time.time())}"

    # محاولة عمل Dispatch للعامل "sci-agent" إذا كانت بيانات LiveKit مهيأة
    dispatched = False
    dispatch_error = None
    if LIVEKIT_URL and LIVEKIT_API_KEY and LIVEKIT_API_SECRET:
        try:
            # إنشاء عميل LiveKit API واستدعاء AgentDispatchService
            lkapi = api.LiveKitAPI(url=LIVEKIT_URL, api_key=LIVEKIT_API_KEY, api_secret=LIVEKIT_API_SECRET)
            
            # تحضير metadata المستخدم للذكاء الاصطناعي
            import json
            user_metadata = {
                "username": req.username,
                "full_name": req.full_name or req.username,
                "user_id": req.user_id,
                "mode": req.mode or "normal",  # إضافة الوضع للـ metadata
                "voice_name": req.voice_name or "Aoede"  # 🎤 الصوت المختار
            }
            
            # إنشاء طلب Dispatch باستخدام أنواع livekit.api مباشرةً (وفق التوثيق الرسمي)
            req_obj = api.CreateAgentDispatchRequest(
                room=room_name,
                agent_name="sci-agent",
                metadata=json.dumps(user_metadata)  # تمرير معلومات المستخدم كـ JSON string
            )
            print(f"[API] إرسال dispatch request: room={room_name}, agent=sci-agent")
            dispatch_response = await lkapi.agent_dispatch.create_dispatch(req_obj)
            print(f"[API] ✅ Dispatch نجح! Response: {dispatch_response}")
            
            # إضافة metadata للغرفة أيضاً كطريقة احتياطية
            try:
                room_service = lkapi.room
                await room_service.update_room_metadata(
                    api.UpdateRoomMetadataRequest(
                        room=room_name,
                        metadata=json.dumps(user_metadata)
                    )
                )
                print(f"[API] تم حفظ metadata المستخدم في الغرفة: {user_metadata}")
            except Exception as room_error:
                print(f"[API] تعذر حفظ room metadata: {room_error}")
            
            dispatched = True
            print(f"[API] ✅ Dispatch أكتمل بنجاح")
        except Exception as e:
            # لا نفشل إنشاء الغرفة بسبب فشل dispatch؛ نُرجع الخطأ فقط
            dispatch_error = str(e)
            print(f"[API] ❌ Dispatch فشل: {e}")
            import traceback
            traceback.print_exc()
    else:
        dispatch_error = "LiveKit credentials are missing"

    # لاحقًا: يمكن الحفظ في قاعدة بيانات (Supabase) هنا
    return {
        "success": True,
        "room_name": room_name,
        "dispatched": dispatched,
        "dispatch_error": dispatch_error,
    }


@app.post("/api/livekit/token")
def get_livekit_token(req: LiveKitTokenRequest) -> dict:
    """إصدار توكن LiveKit للانضمام لغرفة معينة."""
    if not (LIVEKIT_URL and LIVEKIT_API_KEY and LIVEKIT_API_SECRET):
        raise HTTPException(status_code=500, detail="LiveKit credentials are not configured in environment variables")
    try:
        grants = api.VideoGrants(room_join=True, room_create=True, room=req.room_name)
        at = (
            api.AccessToken(LIVEKIT_API_KEY, LIVEKIT_API_SECRET)
            .with_grants(grants)
            .with_identity(req.username)
        )
        token = at.to_jwt()
        return {"success": True, "token": token, "url": LIVEKIT_URL, "room_name": req.room_name}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to create token: {e}")

@app.get("/livekit-client.min.js")
def serve_livekit_client_umd() -> FileResponse:
    """
    يخدم نسخة UMD من livekit-client محليًا.
    إذا لم تكن موجودة، يحاول تنزيلها من CDN وحفظها بالجذر.
    """
    here = os.path.dirname(os.path.abspath(__file__))
    js_path = os.path.join(here, "livekit-client.min.js")
    if not os.path.exists(js_path) or os.path.getsize(js_path) < 10_000:
        sources = [
            "https://cdn.jsdelivr.net/npm/livekit-client@2.15.4/dist/livekit-client.min.js",
            "https://unpkg.com/livekit-client@2.15.4/dist/livekit-client.min.js",
        ]
        last_err = None
        for u in sources:
            try:
                r = requests.get(u, timeout=20)
                r.raise_for_status()
                with open(js_path, "wb") as f:
                    f.write(r.content)
                break
            except Exception as e:
                last_err = e
        if not os.path.exists(js_path):
            raise HTTPException(status_code=502, detail=f"Failed to fetch LiveKit UMD client: {last_err}")
    return FileResponse(js_path, media_type="application/javascript")


@app.post("/token")
def create_token(req: TokenRequest) -> dict:
    if not (LIVEKIT_URL and LIVEKIT_API_KEY and LIVEKIT_API_SECRET):
        raise HTTPException(status_code=500, detail="LiveKit credentials are not configured in environment variables")

    try:
        grants = api.VideoGrants(room_join=True, room_create=True, room=req.room)
        # You can also set room_create=True if you want the client to be able to create the room on join
        at = (
            api.AccessToken(LIVEKIT_API_KEY, LIVEKIT_API_SECRET)
            .with_grants(grants)
            .with_identity(req.identity)
        )
        if req.name:
            at = at.with_name(req.name)
        token = at.to_jwt()
        return {"token": token, "url": LIVEKIT_URL}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to create token: {e}")


# ==================== Supabase Auth Endpoints ====================

@app.post("/api/auth/signup")
@limiter.limit("5/minute")  # 5 تسجيلات كل دقيقة
async def sign_up_user(request: Request, req: UserSignUpRequest) -> dict:
    """تسجيل مستخدم جديد في Supabase"""
    logger.info(f"👤 Signup attempt: {req.email}")
    try:
        # تنظيف البريد وكلمة المرور من أي مسافات/محارف اتجاه
        clean_email = _sanitize_email_text(req.email)
        clean_password = (req.password or "").strip()
        clean_name = (req.full_name or "").strip()

        # تسجيل المستخدم في Supabase Auth
        print(f"محاولة تسجيل مستخدم: {clean_email}")
        auth_result = await supabase_manager.sign_up_user(
            email=clean_email,
            password=clean_password,
            user_data={"full_name": clean_name}
        )
        
        print(f"نتيجة التسجيل: {auth_result}")
        
        if auth_result["success"] and auth_result["user"]:
            user = auth_result["user"]
            print(f"بيانات المستخدم: {user}")
            print(f"نوع بيانات المستخدم: {type(user)}")
            
            # إنشاء ملف شخصي في قاعدة البيانات
            try:
                await supabase_manager.create_user_profile(
                    user_id=str(user.id),
                    email=clean_email,
                    full_name=clean_name
                )
            except Exception as profile_error:
                # إذا فشل إنشاء الملف الشخصي، لا نفشل العملية كلها
                print(f"تحذير: فشل في إنشاء الملف الشخصي: {profile_error}")
            
            # الحصول على access_token من الجلسة
            access_token = None
            if auth_result.get("session"):
                session = auth_result["session"]
                access_token = getattr(session, 'access_token', None)
            
            return {
                "success": True,
                "message": "تم تسجيل المستخدم بنجاح",
                "user_id": str(user.id),
                "email": str(user.email),
                "access_token": access_token
            }
        else:
            raise HTTPException(status_code=400, detail="فشل في تسجيل المستخدم")
            
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"خطأ في الخادم: {str(e)}")

@app.post("/api/auth/signin")
async def sign_in_user(req: UserSignInRequest) -> dict:
    """تسجيل دخول المستخدم"""
    try:
        clean_email = sanitize_email(req.email)
        clean_password = req.password.strip()
        
        if not clean_email or not clean_password:
            raise HTTPException(status_code=400, detail="البريد الإلكتروني وكلمة المرور مطلوبان")
        
        auth_result = await supabase_manager.sign_in_user(clean_email, clean_password)
        
        if auth_result["success"] and auth_result["user"]:
            user = auth_result["user"]
            
            # جلب بيانات الملف الشخصي
            user_profile = None
            try:
                print(f"محاولة جلب الملف الشخصي للمستخدم: {str(user.id)}")
                user_profile = await supabase_manager.get_user_profile(str(user.id))
                print(f"نتيجة جلب الملف الشخصي: {user_profile}")
            except Exception as profile_error:
                print(f"تحذير: فشل في جلب الملف الشخصي: {profile_error}")
            
            # الحصول على access_token من الجلسة
            access_token = None
            if auth_result.get("session"):
                session = auth_result["session"]
                access_token = getattr(session, 'access_token', None)
            
            return {
                "success": True,
                "message": "تم تسجيل الدخول بنجاح",
                "user_id": str(user.id),
                "email": str(user.email),
                "full_name": user_profile.get("full_name") if user_profile and isinstance(user_profile, dict) else None,
                "access_token": access_token
            }
        else:
            raise HTTPException(status_code=400, detail="بيانات الدخول غير صحيحة")
            
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"خطأ في الخادم: {str(e)}")

# ==================== LiveKit Endpoints ====================

class LiveKitTokenRequest(BaseModel):
    username: str
    room_name: str
    user_id: Optional[str] = None

@app.post("/api/livekit/token")
async def get_livekit_token(req: LiveKitTokenRequest) -> dict:
    """الحصول على توكن LiveKit للاتصال"""
    try:
        if not LIVEKIT_URL or not LIVEKIT_API_KEY or not LIVEKIT_API_SECRET:
            raise HTTPException(status_code=500, detail="إعدادات LiveKit غير مكتملة")
        
        # إنشاء توكن LiveKit
        token = api.AccessToken(LIVEKIT_API_KEY, LIVEKIT_API_SECRET) \
            .with_identity(req.username) \
            .with_name(req.username) \
            .with_grants(api.VideoGrants(
                room_join=True,
                room=req.room_name,
                can_publish=True,
                can_subscribe=True
            )).to_jwt()
        
        return {
            "token": token,
            "url": LIVEKIT_URL,
            "room_name": req.room_name
        }
        
    except Exception as e:
        print(f"خطأ في إنشاء توكن LiveKit: {e}")
        raise HTTPException(status_code=500, detail=f"خطأ في إنشاء التوكن: {str(e)}")

@app.get("/api/auth/profile")
async def get_user_profile(current_user: dict = Depends(get_current_user)) -> dict:
    """الحصول على الملف الشخصي للمستخدم الحالي"""
    try:
        return {
            "success": True,
            "user": {
                "id": current_user.id,
                "email": current_user.email,
                "user_metadata": current_user.user_metadata,
                "created_at": current_user.created_at
            }
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"خطأ في الحصول على الملف الشخصي: {str(e)}")

# ==================== Assessment Endpoints ====================

@app.post("/api/assessment/save")
async def save_assessment(
    questions: list,
    score: int,
    level: str,
    user_id: str = Depends(get_user_id_from_token)
):
    """حفظ نتيجة اختبار المستوى"""
    try:
        result = await supabase_manager.save_assessment_result(user_id, questions, score, level)
        return {
            "success": True,
            "message": "تم حفظ نتيجة الاختبار بنجاح",
            "assessment": result.get("assessment")
        }
    except HTTPException as e:
        raise e
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"خطأ في حفظ الاختبار: {str(e)}")

@app.get("/api/assessment/list")
async def list_user_assessments(user_id: str = Depends(get_user_id_from_token)):
    """الحصول على قائمة اختبارات المستخدم"""
    try:
        assessments = await supabase_manager.get_user_assessments(user_id)
        return {
            "success": True,
            "assessments": assessments
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"خطأ في جلب الاختبارات: {str(e)}")

# ==================== User Progress Endpoints ====================

class ConversationDataRequest(BaseModel):
    session_id: Optional[str] = None
    topic: str
    words_discussed: list = []
    progress_made: int = 0
    last_position: str = ""
    session_summary: str = ""
    session_data: dict = {}

@app.get("/api/progress/get")
async def get_user_progress(user_id: str = Depends(get_user_id_from_token)):
    """جلب تقدم المستخدم في تعلم اللغة الإنجليزية"""
    try:
        progress = await supabase_manager.get_or_create_user_progress(user_id)
        return {
            "success": True,
            "progress": progress
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"خطأ في جلب تقدم المستخدم: {str(e)}")

@app.post("/api/progress/update")
async def update_user_progress_endpoint(
    progress_data: dict,
    user_id: str = Depends(get_user_id_from_token)
):
    """تحديث تقدم المستخدم"""
    try:
        result = await supabase_manager.update_user_progress_dict(user_id, progress_data)
        return {
            "success": True,
            "message": "تم تحديث التقدم بنجاح",
            "progress": result.get("progress")
        }
    except HTTPException as e:
        raise e
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"خطأ في تحديث التقدم: {str(e)}")

@app.post("/api/progress/conversation")
async def save_conversation_data_endpoint(
    req: ConversationDataRequest,
    user_id: str = Depends(get_user_id_from_token)
):
    """حفظ بيانات المحادثة الصوتية"""
    try:
        conversation_data = req.dict()
        result = await supabase_manager.save_conversation_data(user_id, conversation_data)
        return {
            "success": True,
            "message": "تم حفظ بيانات المحادثة بنجاح",
            "progress": result.get("progress")
        }
    except HTTPException as e:
        raise e
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"خطأ في حفظ بيانات المحادثة: {str(e)}")

@app.get("/api/progress/conversation-history")
async def get_conversation_history(user_id: str = Depends(get_user_id_from_token)):
    """جلب تاريخ المحادثات الصوتية"""
    try:
        progress = await supabase_manager.get_user_progress(user_id)
        if not progress:
            return {
                "success": True,
                "conversation_history": {}
            }
        
        return {
            "success": True,
            "conversation_history": progress.get("conversation_history", {}),
            "current_topic": progress.get("current_topic", ""),
            "last_position": progress.get("last_position", ""),
            "words_learned": progress.get("words_learned", 0),
            "progress_percentage": progress.get("progress_percentage", 0)
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"خطأ في جلب تاريخ المحادثات: {str(e)}")

# ==================== Debug Endpoints ====================

@app.post("/api/debug/test-database")
async def test_database_connection():
    """اختبار الاتصال بقاعدة البيانات وإرسال بيانات تجريبية"""
    try:
        # اختبار 1: الاتصال الأساسي
        test_results = {
            "connection_test": "failed",
            "insert_test": "failed", 
            "select_test": "failed",
            "service_client_test": "failed",
            "details": {}
        }
        
        # اختبار الاتصال الأساسي
        try:
            result = supabase_manager.client.table("profiles").select("id").limit(1).execute()
            test_results["connection_test"] = "success"
            test_results["details"]["basic_connection"] = "يعمل بشكل صحيح"
        except Exception as e:
            test_results["details"]["basic_connection_error"] = str(e)
        
        # اختبار service client
        if supabase_manager.service_client:
            try:
                result = supabase_manager.service_client.table("profiles").select("id").limit(1).execute()
                test_results["service_client_test"] = "success"
                test_results["details"]["service_client"] = "يعمل بشكل صحيح"
            except Exception as e:
                test_results["details"]["service_client_error"] = str(e)
        else:
            test_results["details"]["service_client"] = "غير متوفر - لا يوجد SUPABASE_SERVICE_ROLE_KEY"
        
        # اختبار إدراج بيانات تجريبية (بدون RLS)
        test_user_id = "test-user-123"
        test_data = {
            "user_id": test_user_id,
            "words_learned": 5,
            "current_topic": "اختبار الألوان",
            "last_position": "الدرس الأول",
            "progress_percentage": 25,
            "session_data": {"test": True},
            "topics_completed": ["التحيات"],
            "vocabulary": {"hello": "مرحبا"},
            "conversation_history": {"session1": {"test": "data"}}
        }
        
        try:
            # محاولة الإدراج بـ service client أولاً
            if supabase_manager.service_client:
                insert_result = supabase_manager.service_client.table("user_progress").insert(test_data).execute()
                test_results["insert_test"] = "success"
                test_results["details"]["insert_result"] = "تم الإدراج بنجاح بـ service client"
                
                # اختبار الاستعلام
                select_result = supabase_manager.service_client.table("user_progress").select("*").eq("user_id", test_user_id).execute()
                if select_result.data:
                    test_results["select_test"] = "success"
                    test_results["details"]["select_result"] = select_result.data[0]
                    
                    # حذف البيانات التجريبية
                    supabase_manager.service_client.table("user_progress").delete().eq("user_id", test_user_id).execute()
                    test_results["details"]["cleanup"] = "تم حذف البيانات التجريبية"
                else:
                    test_results["details"]["select_error"] = "لم يتم العثور على البيانات المدرجة"
            else:
                # محاولة بـ client عادي
                insert_result = supabase_manager.client.table("user_progress").insert(test_data).execute()
                test_results["insert_test"] = "success"
                test_results["details"]["insert_result"] = "تم الإدراج بنجاح بـ client عادي"
                
        except Exception as e:
            test_results["details"]["insert_error"] = str(e)
        
        return {
            "success": True,
            "message": "تم تشغيل اختبارات قاعدة البيانات",
            "test_results": test_results
        }
        
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "message": "فشل في تشغيل اختبارات قاعدة البيانات"
        }

@app.get("/api/debug/check-env")
async def check_environment_variables():
    """فحص متغيرات البيئة المطلوبة"""
    env_check = {
        "SUPABASE_URL": "✓" if os.getenv("SUPABASE_URL") else "✗",
        "SUPABASE_ANON_KEY": "✓" if os.getenv("SUPABASE_ANON_KEY") else "✗", 
        "SUPABASE_SERVICE_ROLE_KEY": "✓" if os.getenv("SUPABASE_SERVICE_ROLE_KEY") else "✗",
        "LIVEKIT_URL": "✓" if os.getenv("LIVEKIT_URL") else "✗",
        "LIVEKIT_API_KEY": "✓" if os.getenv("LIVEKIT_API_KEY") else "✗",
        "LIVEKIT_API_SECRET": "✓" if os.getenv("LIVEKIT_API_SECRET") else "✗"
    }
    
    return {
        "success": True,
        "environment_variables": env_check,
        "supabase_manager_status": {
            "client_initialized": supabase_manager.client is not None,
            "service_client_initialized": supabase_manager.service_client is not None,
            "url": supabase_manager.url[:50] + "..." if supabase_manager.url else None
        }
    }

# تم حذف الدالة المكررة - الدالة الأصلية موجودة في السطر 339
