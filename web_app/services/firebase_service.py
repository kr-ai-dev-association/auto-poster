import os
import glob
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
            
        # 서비스 계정 키 경로 (절대 경로로 계산하여 실행 위치 관계없이 작동)
        base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        self.service_account_path = os.path.join(base_dir, '1_md_converter', 'serviceAccountKey.json')
        
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
        if not os.path.exists(self.service_account_path):
            print(f"❌ Error: Service account key not found at {self.service_account_path}")
            return

        try:
            credentials = service_account.Credentials.from_service_account_file(self.service_account_path)
            
            # Firestore (기본 프로젝트 사용)
            self.db = firestore.Client(credentials=credentials)
            
            # Storage (이미지 호스팅용 프로젝트 명시)
            storage_client = storage.Client(credentials=credentials, project=self.image_project_id)
            self.bucket = storage_client.bucket(self.image_bucket_name)
            
            print("✅ Firebase/GCS Clients Initialized")
        except Exception as e:
            print(f"❌ Firebase Initialization Failed: {e}")

    def get_id_map(self):
        """Firestore에서 ID 매핑 정보를 가져옵니다."""
        if not self.db:
            return {}
        try:
            doc_ref = self.db.collection('system-metadata').document('wiki-id-map')
            doc = doc_ref.get()
            return doc.to_dict() if doc.exists else {}
        except Exception as e:
            print(f"⚠️ Failed to fetch ID map: {e}")
            return {}

    def save_id_map(self, id_map):
        """ID 매핑 정보를 Firestore에 저장합니다."""
        if not self.db:
            return
        try:
            doc_ref = self.db.collection('system-metadata').document('wiki-id-map')
            doc_ref.set(id_map, merge=True)
            print("✅ ID map updated.")
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

    def save_wiki_content(self, wiki_id, title_ko, title_en, last_updated, html_ko, html_en, thumbnail_url):
        """변환된 위키 콘텐츠를 Firestore에 저장합니다."""
        if not self.db:
            return False

        try:
            doc_ref = self.db.collection('static-wiki').document(wiki_id)
            doc_data = {
                'id': wiki_id,
                'titles': { 'ko': title_ko, 'en': title_en },
                'content': { 'ko': html_ko, 'en': html_en },
                'thumbnailUrl': thumbnail_url,
                'lastUpdated': last_updated,
                'type': 'firestore-content',
                'createdAt': firestore.SERVER_TIMESTAMP
            }
            doc_ref.set(doc_data, merge=True)
            return True
        except Exception as e:
            print(f"❌ Firestore save failed: {e}")
            return False

