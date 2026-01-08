"""
보안 파일 암호화/복호화 서비스
슈퍼 관리자의 키 프레이즈를 사용하여 민감한 파일을 암호화하여 DB에 저장
"""
import os
import base64
import hashlib
from cryptography.fernet import Fernet
from dotenv import load_dotenv

load_dotenv()

class CryptoService:
    """
    Fernet 대칭키 암호화를 사용한 보안 파일 관리
    """
    
    @staticmethod
    def _derive_key_from_phrase(key_phrase: str) -> bytes:
        """
        키 프레이즈로부터 32바이트 Fernet 키 생성
        PBKDF2 대신 간단한 SHA256 해시 사용 (더 강력한 보안이 필요하면 PBKDF2 사용)
        """
        # SHA256으로 해시하여 32바이트 키 생성
        hash_obj = hashlib.sha256(key_phrase.encode('utf-8'))
        # Fernet은 base64로 인코딩된 32바이트 키를 요구
        return base64.urlsafe_b64encode(hash_obj.digest())
    
    @staticmethod
    def encrypt_file(file_content: bytes, key_phrase: str) -> bytes:
        """
        파일 내용을 암호화
        
        Args:
            file_content: 암호화할 파일의 바이트 데이터
            key_phrase: 슈퍼 관리자의 키 프레이즈
        
        Returns:
            암호화된 바이트 데이터
        """
        key = CryptoService._derive_key_from_phrase(key_phrase)
        fernet = Fernet(key)
        encrypted_data = fernet.encrypt(file_content)
        return encrypted_data
    
    @staticmethod
    def decrypt_file(encrypted_content: bytes, key_phrase: str) -> bytes:
        """
        암호화된 파일 내용을 복호화
        
        Args:
            encrypted_content: 암호화된 바이트 데이터
            key_phrase: 슈퍼 관리자의 키 프레이즈
        
        Returns:
            복호화된 바이트 데이터
        
        Raises:
            cryptography.fernet.InvalidToken: 잘못된 키 프레이즈인 경우
        """
        key = CryptoService._derive_key_from_phrase(key_phrase)
        fernet = Fernet(key)
        decrypted_data = fernet.decrypt(encrypted_content)
        return decrypted_data
    
    @staticmethod
    def get_master_key_phrase() -> str:
        """
        .env에서 마스터 키 프레이즈를 가져옴
        (초기 설정용, 실제 운영에서는 슈퍼 관리자가 직접 입력)
        """
        # SUPER_ADMIN_ID + SUPER_ADMIN_PW 조합을 키 프레이즈로 사용
        admin_id = os.getenv("SUPER_ADMIN_ID", "")
        admin_pw = os.getenv("SUPER_ADMIN_PW", "")
        return f"{admin_id}:{admin_pw}"
    
    @staticmethod
    def get_decrypted_file_from_db(file_name: str, db_session=None, allow_fallback: bool = None) -> bytes:
        """
        DB에서 암호화된 파일을 읽어 복호화하여 반환
        
        Args:
            file_name: 파일명 (예: 'serviceAccountKey.json')
            db_session: SQLAlchemy 세션 (없으면 새로 생성)
            allow_fallback: 로컬 파일 폴백 허용 여부 (None이면 ENVIRONMENT 환경 변수 확인)
        
        Returns:
            복호화된 파일의 바이트 데이터
        
        Raises:
            FileNotFoundError: DB에 파일이 없는 경우
            Exception: 복호화 실패 시
        """
        from core import database, models
        
        # 환경 확인 (프로덕션에서는 폴백 금지)
        if allow_fallback is None:
            environment = os.getenv("ENVIRONMENT", "development").lower()
            allow_fallback = (environment == "development")
        
        # 세션이 없으면 새로 생성
        if db_session is None:
            db_session = database.SessionLocal()
            close_session = True
        else:
            close_session = False
        
        try:
            # DB에서 파일 조회
            secure_file = db_session.query(models.SecureFile).filter(
                models.SecureFile.file_name == file_name
            ).first()
            
            if not secure_file:
                error_msg = f"DB에 '{file_name}' 파일이 없습니다."
                if not allow_fallback:
                    error_msg += " [PRODUCTION] 보안 파일 관리 페이지에서 반드시 업로드해야 합니다."
                raise FileNotFoundError(error_msg)
            
            # 마스터 키 프레이즈로 복호화
            key_phrase = CryptoService.get_master_key_phrase()
            decrypted_content = CryptoService.decrypt_file(secure_file.encrypted_content, key_phrase)
            
            return decrypted_content
        
        finally:
            if close_session:
                db_session.close()
    
    @staticmethod
    def get_decrypted_file_path(file_name: str, temp_dir: str = "/tmp") -> str:
        """
        DB에서 복호화한 파일을 임시 디렉토리에 저장하고 경로 반환
        
        Args:
            file_name: 파일명
            temp_dir: 임시 디렉토리 경로
        
        Returns:
            저장된 파일의 절대 경로
        """
        import os
        import tempfile
        
        decrypted_content = CryptoService.get_decrypted_file_from_db(file_name)
        
        # 임시 파일로 저장
        temp_path = os.path.join(temp_dir, file_name)
        with open(temp_path, 'wb') as f:
            f.write(decrypted_content)
        
        return temp_path
    
    @staticmethod
    def load_env_from_db():
        """
        DB에서 암호화된 .env 파일을 복호화하여 환경 변수로 로드
        로컬 .env 파일이 있으면 폴백 (개발 환경만)
        
        Returns:
            bool: 성공 여부
        """
        # 먼저 로컬 .env를 임시로 로드하여 ENVIRONMENT 확인
        from dotenv import load_dotenv
        load_dotenv()
        
        environment = os.getenv("ENVIRONMENT", "development").lower()
        
        try:
            # 1. DB에서 .env 복호화 시도
            env_content = CryptoService.get_decrypted_file_from_db('.env', allow_fallback=True)
            
            # 환경 변수로 파싱 및 로드
            for line in env_content.decode('utf-8').splitlines():
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    key, value = line.split('=', 1)
                    os.environ[key.strip()] = value.strip()
            
            print(f"✅ [{environment.upper()}] Environment variables loaded from encrypted DB")
            return True
            
        except FileNotFoundError:
            # 2. 로컬 .env 파일 폴백 (개발 환경만)
            if environment == "production":
                print("❌ [PRODUCTION] .env 파일이 DB에 없습니다. /admin/secure-files에서 업로드해야 합니다.")
                return False
            
            if load_dotenv():
                print(f"⚠️ [{environment.upper()}] No encrypted .env in DB, using local file...")
                return True
            else:
                print("❌ No .env file found in DB or locally")
                return False
        except Exception as e:
            print(f"❌ Error loading .env: {e}")
            return False

