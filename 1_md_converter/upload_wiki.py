import os
import glob
import datetime
import mimetypes
from bs4 import BeautifulSoup
from google.cloud import storage, firestore
from google.oauth2 import service_account

# ==========================================================
# 🔧 설정 (CONFIG)
# ==========================================================
SERVICE_ACCOUNT_PATH = '1_md_converter/serviceAccountKey.json' # 서비스 계정 키 경로
# BUCKET_NAME은 initialize_firebase()에서 자동으로 찾거나 설정합니다.
BUCKET_NAME = 'banya_public2' # 구글 클라우드 스토리지 버킷 이름
# ==========================================================

def initialize_firebase():
    """Firestore 및 Storage 클라이언트 초기화"""
    if not os.path.exists(SERVICE_ACCOUNT_PATH):
        print(f"❌ Error: Service account key not found at {SERVICE_ACCOUNT_PATH}")
        return None, None, None

    credentials = service_account.Credentials.from_service_account_file(SERVICE_ACCOUNT_PATH)
    
    # Firestore는 서비스 계정의 기본 프로젝트(tonys-tech-note) 사용
    firestore_client = firestore.Client(credentials=credentials)
    
    # Storage는 이미지가 있는 프로젝트(banya2025)를 명시적으로 지정
    # 주의: 서비스 계정이 banya2025 프로젝트의 해당 버킷에 대한 접근 권한이 있어야 함
    storage_client = storage.Client(credentials=credentials, project='banya2025')

    # 버킷 확인 (이미지 업로드용)
    bucket = None
    try:
        # get_bucket() 대신 bucket() 생성자를 사용하여 메타데이터 조회 권한(storage.buckets.get) 없이도
        # 버킷 객체를 생성합니다. 실제 접근(업로드 등) 시점에 권한이 확인됩니다.
        bucket = storage_client.bucket(BUCKET_NAME)
        print(f"✅ Configured bucket object: {BUCKET_NAME} (Access will be verified during upload)")
    except Exception as e:
        print(f"❌ Error creating bucket object: {e}")

    return firestore_client, storage_client, bucket

def get_id_map(db):
    """Firestore에서 ID 매핑 정보를 가져옵니다."""
    try:
        doc_ref = db.collection('system-metadata').document('wiki-id-map')
        doc = doc_ref.get()
        if doc.exists:
            return doc.to_dict()
        else:
            return {}
    except Exception as e:
        print(f"⚠️ Failed to fetch ID map from Firestore: {e}")
        return {}

def save_id_map(db, id_map):
    """ID 매핑 정보를 Firestore에 저장합니다."""
    try:
        doc_ref = db.collection('system-metadata').document('wiki-id-map')
        doc_ref.set(id_map, merge=True)
        print("✅ ID map updated in Firestore.")
    except Exception as e:
        print(f"⚠️ Failed to save ID map to Firestore: {e}")

def upload_file_to_storage(bucket, local_path, destination_path):
    """파일(이미지)을 Storage에 업로드하고 Public URL을 반환"""
    if not bucket:
        return None
    
    if not os.path.exists(local_path):
        print(f"⚠️  File not found: {local_path}")
        return None

    blob = bucket.blob(destination_path)
    
    mime_type, _ = mimetypes.guess_type(local_path)
    if mime_type:
        blob.content_type = mime_type

    print(f"Uploading image {local_path} -> {destination_path}...")
    try:
        blob.upload_from_filename(local_path)
        try:
            blob.make_public()
        except Exception:
            pass # Public Access Prevention 등으로 실패해도 일단 진행
        return blob.public_url
    except Exception as e:
        print(f"❌ Image upload failed: {e}")
        return None

def process_html_content(html_path, image_urls):
    """HTML 내 이미지 경로 치환 후 HTML 문자열 반환"""
    if not os.path.exists(html_path):
        return None

    with open(html_path, 'r', encoding='utf-8') as f:
        soup = BeautifulSoup(f, 'html.parser')

    # 이미지 태그 찾아서 src 교체
    images = soup.find_all('img')
    for img in images:
        src = img.get('src')
        if not src:
            continue
        
        filename = os.path.basename(src)
        if filename in image_urls:
            print(f"🔄 Replacing image src: {src} -> {image_urls[filename]}")
            img['src'] = image_urls[filename]
    
    return str(soup)

def upload_wiki_entry(wiki_id, title_ko, title_en, last_updated, html_ko_path, html_en_path, image_dir):
    print(f"\n🚀 Starting Wiki Upload for: {wiki_id}")
    
    # 1. 초기화
    db, _, bucket = initialize_firebase()
    if not db:
        print("❌ Failed to initialize Firestore. Aborting.")
        return

    # 2. 이미지 업로드 (Storage 사용)
    image_urls = {}
    if bucket:
        image_files = []
        for ext in ['*.png', '*.jpg', '*.jpeg', '*.gif', '*.webp']:
            image_files.extend(glob.glob(os.path.join(image_dir, ext)))
        
        print(f"📸 Found {len(image_files)} images to upload.")

        for img_path in image_files:
            filename = os.path.basename(img_path)
            dest_path = f"wiki-images/{wiki_id}/{filename}"
            url = upload_file_to_storage(bucket, img_path, dest_path)
            if url:
                image_urls[filename] = url
    else:
        print("⚠️  Skipping image upload (No bucket available).")

    # 3. HTML 처리 (파일 업로드 X -> Firestore 저장용 문자열 생성)
    print("\n📝 Processing HTML content...")
    html_content_ko = process_html_content(html_ko_path, image_urls)
    html_content_en = process_html_content(html_en_path, image_urls)

    if not html_content_ko and not html_content_en:
        print("❌ Both HTML files failed to process. Aborting.")
        return

    # 4. 썸네일 결정
    thumbnail_url = None
    for filename, url in image_urls.items():
        if 'summary' in filename.lower():
            thumbnail_url = url
            break
    if not thumbnail_url and image_urls:
        thumbnail_url = list(image_urls.values())[0]

    # 5. Firestore 업데이트 (HTML 내용을 'content' 필드에 직접 저장)
    print("\n💾 Updating Firestore...")
    doc_ref = db.collection('static-wiki').document(wiki_id)
    
    doc_data = {
        'id': wiki_id,
        'titles': {
            'ko': title_ko,
            'en': title_en
        },
        # HTML 파일 URL 대신 실제 HTML 내용을 저장
        'content': {
            'ko': html_content_ko,
            'en': html_content_en
        },
        'thumbnailUrl': thumbnail_url,
        'lastUpdated': last_updated,
        'type': 'firestore-content', # 타입을 변경하여 프론트엔드에서 구분 가능하도록 함
        'createdAt': firestore.SERVER_TIMESTAMP
    }
    
    doc_ref.set(doc_data, merge=True)
    
    print("\n✨ Upload Complete Successfully!")
    print(f"🔗 Report Link: https://tonys-tech-note.web.app/report/{wiki_id}")

def main():
    # 테스트용 더미 데이터 (직접 실행 시 사용)
    test_wiki_id = 'test-wiki-id'
    print("⚠️  This script is designed to be imported by md_to_html_converter.py")
    print(f"    Running in test mode for {test_wiki_id}...")
    
    # upload_wiki_entry(test_wiki_id, ...) # 테스트가 필요하면 주석 해제하여 사용

if __name__ == '__main__':
    main()
