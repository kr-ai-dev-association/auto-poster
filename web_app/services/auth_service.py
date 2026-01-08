import os
import re
from datetime import datetime, timedelta
from typing import Optional
from jose import JWTError, jwt
from passlib.context import CryptContext
from sqlalchemy.orm import Session
from core import models
from dotenv import load_dotenv

load_dotenv()

# JWT 설정
SECRET_KEY = os.getenv("SECRET_KEY", "banya_secret_key_2026_super_secure")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24  # 1일

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

def verify_password(plain_password, hashed_password):
    return pwd_context.verify(plain_password, hashed_password)

def get_password_hash(password):
    return pwd_context.hash(password)

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None):
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=15)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt

def validate_password_strength(password: str) -> bool:
    """
    영문 대소문자, 숫자, 특수문자 조합으로 8자리 이상인지 확인
    """
    if len(password) < 8:
        return False
    if not re.search("[a-z]", password):
        return False
    if not re.search("[A-Z]", password):
        return False
    if not re.search("[0-9]", password):
        return False
    if not re.search("[_@$!%*#?&]", password):
        return False
    return True

def init_super_admin(db: Session):
    """
    .env에서 수퍼 관리자 계정을 읽어 DB에 등록
    """
    super_id = os.getenv("SUPER_ADMIN_ID")
    super_pw = os.getenv("SUPER_ADMIN_PW")

    if not super_id or not super_pw:
        print("⚠️ SUPER_ADMIN_ID or SUPER_ADMIN_PW not set in .env")
        return

    # 이미 존재하는지 확인
    user = db.query(models.User).filter(models.User.email == super_id).first()
    if not user:
        new_user = models.User(
            name="Super Admin",
            email=super_id,
            password_hash=get_password_hash(super_pw),
            is_active=True,
            is_super_admin=True
        )
        db.add(new_user)
        db.commit()
        db.refresh(new_user)
        print(f"✅ Super Admin created: {super_id}")
    else:
        # 비밀번호 업데이트 (필요시)
        user.password_hash = get_password_hash(super_pw)
        user.is_active = True
        user.is_super_admin = True
        db.commit()
        print(f"✅ Super Admin info updated: {super_id}")

