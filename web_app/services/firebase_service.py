import os
import glob
import json
import tempfile
import mimetypes
from bs4 import BeautifulSoup
from google.cloud import storage, firestore
from google.oauth2 import service_account

class FirebaseService:
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(FirebaseService, cls).__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
            
        # 설정값
        self.image_bucket_name = 'banya_public2'
        self.image_project_id = 'banya2025'
        self.firestore_project_id = 'tonys-tech-note'
        
        self.db = None
        self.bucket = None
        self._initialize_clients()
        self._initialized = True

    def _initialize_clients(self):
        """Firestore 및 Storage 클라이언트를 초기화합니다."""
        environment = os.getenv("ENVIRONMENT", "development").lower()
        
        try:
            # 1. DB에서 서비스 계정 키 복호화 시도
            try:
                from .crypto_service import CryptoService
                service_account_content = CryptoService.get_decrypted_file_from_db('serviceAccountKey.json')
                service_account_info = json.loads(service_account_content.decode('utf-8'))
                credentials = service_account.Credentials.from_service_account_info(service_account_info)
                print(f"✅ [{environment.upper()}] Firebase credentials loaded from encrypted DB")
            except FileNotFoundError as e:
                # 2. DB에 없으면 로컬 파일 폴백 (개발 환경만)
                if environment == "production":
                    print(f"❌ [PRODUCTION] {str(e)}")
                    print("💡 프로덕션에서는 /admin/secure-files에서 반드시 업로드해야 합니다.")
                    return
                
                print(f"⚠️ [{environment.upper()}] No encrypted credentials in DB, falling back to local file...")
                base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
                service_account_path = os.path.join(base_dir, 'secrets', 'serviceAccountKey.json')
                
                if not os.path.exists(service_account_path):
                    print(f"❌ Error: Service account key not found at {service_account_path}")
                    print("💡 Tip: Upload the key through /admin/secure-files")
                    return
                
                credentials = service_account.Credentials.from_service_account_file(service_account_path)
                print(f"✅ [{environment.upper()}] Firebase credentials loaded from local file")
            
            # Firestore (기본 프로젝트 사용)
            self.db = firestore.Client(credentials=credentials)
            
            # Storage (이미지 호스팅용 프로젝트 명시)
            storage_client = storage.Client(credentials=credentials, project=self.image_project_id)
            self.bucket = storage_client.bucket(self.image_bucket_name)
            
            print("✅ Firebase/GCS Clients Initialized")
        except Exception as e:
            print(f"❌ Firebase Initialization Failed: {e}")

    def get_id_map(self, category='tech'):
        """
        Firestore에서 ID 매핑 정보를 가져옵니다.
        category: 'tech' 또는 'news'
        """
        if not self.db:
            return {}
        try:
            doc_id = f'wiki-id-map-{category}'
            doc_ref = self.db.collection('system-metadata').document(doc_id)
            doc = doc_ref.get()
            return doc.to_dict() if doc.exists else {}
        except Exception as e:
            print(f"⚠️ Failed to fetch ID map: {e}")
            return {}

    def save_id_map(self, id_map, category='tech'):
        """
        ID 매핑 정보를 Firestore에 저장합니다.
        category: 'tech' 또는 'news'
        """
        if not self.db:
            return
        try:
            doc_id = f'wiki-id-map-{category}'
            doc_ref = self.db.collection('system-metadata').document(doc_id)
            doc_ref.set(id_map, merge=True)
            print(f"✅ ID map updated (category: {category}).")
        except Exception as e:
            print(f"⚠️ Failed to save ID map: {e}")

    def upload_image(self, local_path, destination_path):
        """이미지를 GCS에 업로드하고 Public URL을 반환합니다."""
        if not self.bucket or not os.path.exists(local_path):
            return None

        blob = self.bucket.blob(destination_path)
        mime_type, _ = mimetypes.guess_type(local_path)
        if mime_type:
            blob.content_type = mime_type

        try:
            blob.upload_from_filename(local_path)
            # Public Access Prevention 정책이 있을 수 있으므로 실패해도 무시
            try: blob.make_public() 
            except: pass
            
            # GCS Public URL 형식 반환
            return f"https://storage.googleapis.com/{self.image_bucket_name}/{destination_path}"
        except Exception as e:
            print(f"❌ Image upload failed: {e}")
            return None

    def save_wiki_content(self, wiki_id, title_ko, title_en, last_updated, html_ko, html_en, thumbnail_url, category='tech'):
        """
        변환된 위키 콘텐츠를 Firestore에 저장합니다.
        category: 'tech' (Tech Wiki -> static-wiki) 또는 'news' (Banya Official News -> banya-official-news)
        
        데이터 구조:
        - id: wiki_id
        - titles: { ko: title_ko, en: title_en }
        - content: { ko: html_ko, en: html_en }
        - thumbnailUrl: thumbnail_url
        - lastUpdated: ISO 날짜 문자열 (예: "2025-01-15")
        - type: 'firestore-content'
        - createdAt: ISO 타임스탬프 문자열 (예: "2025-01-15T10:30:00.000Z")
        """
        if not self.db:
            print(f"❌ Firestore DB not initialized")
            return False

        try:
            from datetime import datetime
            
            # 카테고리에 따라 컬렉션 선택
            collection_name = 'banya-official-news' if category == 'news' else 'static-wiki'
            print(f"📝 Saving to collection: {collection_name} (category: {category}, wiki_id: {wiki_id})")
            doc_ref = self.db.collection(collection_name).document(wiki_id)
            
            # createdAt을 ISO 타임스탬프 문자열로 생성 (예시 코드와 동일한 형식)
            created_at = datetime.utcnow().isoformat() + 'Z'
            
            doc_data = {
                'id': wiki_id,
                'titles': { 'ko': title_ko, 'en': title_en },
                'content': { 'ko': html_ko, 'en': html_en },
                'thumbnailUrl': thumbnail_url or '',
                'lastUpdated': last_updated,
                'type': 'firestore-content',
                'createdAt': created_at
            }
            doc_ref.set(doc_data, merge=True)
            print(f"✅ Content saved to {collection_name}/{wiki_id}")
            return True
        except Exception as e:
            print(f"❌ Firestore save failed: {e}")
            import traceback
            traceback.print_exc()
            return False

