"""
نظام المصادقة للمشروع
يتضمن: JWT Bearer, Auth middleware, User verification
"""
import os
from typing import Optional, Dict, Any
from fastapi import HTTPException, Request, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from supabase_client import supabase_manager
import logging
from jose import jwt
from jose.exceptions import ExpiredSignatureError, JWTError

logger = logging.getLogger(__name__)

# إعدادات JWT
JWT_SECRET = os.getenv("SUPABASE_JWT_SECRET")
JWT_ALGORITHM = "HS256"

class JWTBearer(HTTPBearer):
    """فئة للتحقق من JWT Token في الطلبات"""
    
    def __init__(self, auto_error: bool = True):
        super(JWTBearer, self).__init__(auto_error=auto_error)
    
    async def __call__(self, request: Request) -> Optional[str]:
        credentials: HTTPAuthorizationCredentials = await super(JWTBearer, self).__call__(request)
        
        if credentials:
            if not credentials.scheme == "Bearer":
                raise HTTPException(
                    status_code=403, 
                    detail="نظام المصادقة غير صحيح. يجب استخدام Bearer Token"
                )
            
            if not self.verify_jwt(credentials.credentials):
                raise HTTPException(
                    status_code=403, 
                    detail="التوكن غير صالح أو منتهي الصلاحية"
                )
            
            return credentials.credentials
        else:
            raise HTTPException(
                status_code=403, 
                detail="رمز المصادقة مطلوب"
            )
    
    def verify_jwt(self, token: str) -> bool:
        """التحقق من صحة JWT Token"""
        try:
            if not JWT_SECRET:
                logger.error("SUPABASE_JWT_SECRET غير موجود في متغيرات البيئة")
                return False
            
            payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
            return payload is not None
            
        except ExpiredSignatureError:
            logger.warning("التوكن منتهي الصلاحية")
            return False
        except JWTError:
            logger.warning("التوكن غير صالح")
            return False
        except Exception as e:
            logger.error(f"خطأ في التحقق من التوكن: {e}")
            return False

# إنشاء مثيل للاستخدام
jwt_bearer = JWTBearer()

async def get_current_user(token: str = Depends(jwt_bearer)) -> Dict[str, Any]:
    """الحصول على المستخدم الحالي من التوكن"""
    try:
        user = await supabase_manager.get_user_from_token(token)
        if not user:
            raise HTTPException(
                status_code=401, 
                detail="لا يمكن العثور على المستخدم"
            )
        return user
    except Exception as e:
        logger.error(f"خطأ في الحصول على المستخدم الحالي: {e}")
        raise HTTPException(
            status_code=401, 
            detail="خطأ في التحقق من المستخدم"
        )

def decode_jwt_payload(token: str) -> Optional[Dict[str, Any]]:
    """فك تشفير JWT وإرجاع البيانات"""
    try:
        if not JWT_SECRET:
            return None
        
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        return payload
        
    except Exception as e:
        logger.error(f"خطأ في فك تشفير JWT: {e}")
        return None

async def get_user_id_from_token(token: str = Depends(jwt_bearer)) -> str:
    """الحصول على user_id من التوكن"""
    try:
        payload = decode_jwt_payload(token)
        if not payload:
            raise HTTPException(status_code=401, detail="التوكن غير صالح")
        
        user_id = payload.get("sub")
        if not user_id:
            raise HTTPException(status_code=401, detail="معرف المستخدم غير موجود في التوكن")
        
        return user_id
        
    except Exception as e:
        logger.error(f"خطأ في الحصول على معرف المستخدم: {e}")
        raise HTTPException(status_code=401, detail="خطأ في التحقق من المستخدم")

# Optional: دالة للتحقق من الأدوار (للاستخدام المستقبلي)
async def verify_user_role(token: str, required_role: str) -> bool:
    """التحقق من دور المستخدم"""
    try:
        payload = decode_jwt_payload(token)
        if not payload:
            return False
        
        user_metadata = payload.get("user_metadata", {})
        user_role = user_metadata.get("role", "user")
        
        return user_role == required_role or user_role == "admin"
        
    except Exception as e:
        logger.error(f"خطأ في التحقق من الدور: {e}")
        return False
