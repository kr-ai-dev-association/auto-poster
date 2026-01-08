from sqlalchemy import Column, Integer, String, Boolean, DateTime, LargeBinary, Text
from sqlalchemy.sql import func
from .database import Base

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String)
    email = Column(String, unique=True, index=True)
    password_hash = Column(String)
    is_active = Column(Boolean, default=False)  # 승인 대기 상태 (False)
    is_super_admin = Column(Boolean, default=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

class SecureFile(Base):
    """
    암호화된 보안 파일 저장용 테이블
    """
    __tablename__ = "secure_files"

    id = Column(Integer, primary_key=True, index=True)
    file_name = Column(String, unique=True, index=True)  # 예: 'serviceAccountKey.json'
    file_type = Column(String)  # 'firebase', 'youtube', 'env'
    encrypted_content = Column(LargeBinary)  # 암호화된 파일 내용
    description = Column(Text, nullable=True)  # 파일 설명
    uploaded_by = Column(Integer)  # 업로드한 관리자의 User ID
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

