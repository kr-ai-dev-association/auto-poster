import os
import sys
import glob
import logging
from dotenv import load_dotenv
from bs4 import BeautifulSoup

# core 및 2_blog_poster 모듈 import를 위한 경로 설정
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(os.path.dirname(current_dir)) # 루트
sys.path.append(project_root)
sys.path.append(os.path.join(project_root, '2_blog_poster'))

# 기존 core 모듈 재사용
from core.linkedin_poster import LinkedInPoster
from core.summarizer import GeminiSummarizer
from scraper import parse_content

load_dotenv()
logger = logging.getLogger(__name__)

class LinkedinService:
    def __init__(self):
        self.poster = LinkedInPoster()
        self.summarizer = GeminiSummarizer()
        
        # Person URN 확인 및 갱신
        if not self.poster.person_urn:
            logger.info("Person URN not found in .env, trying to fetch from API...")
            me = self.poster.get_me()
            if me:
                self.poster.person_urn = f"urn:li:person:{me['id']}"
            else:
                logger.error("Failed to get Person URN.")

    async def share_wiki(self, wiki_id: str, wiki_url: str, lang: str = "ko"):
        """
        위키 콘텐츠를 분석하여 LinkedIn에 공유합니다.
        wiki_id: 위키 문서 ID
        wiki_url: 배포된 위키 URL (예: https://tony.banya.ai/report/...)
        lang: 포스팅 언어 ('ko' or 'en')
        """
        logger.info(f"Preparing to share on LinkedIn: {wiki_url} ({lang})")
        
        try:
            # FirestoreService를 통해 콘텐츠 가져오기 (가장 정확)
            from .firebase_service import FirebaseService
            fb_service = FirebaseService()
            
            # wiki_id가 정확해야 함
            doc_ref = fb_service.db.collection('static-wiki').document(wiki_id)
            doc = doc_ref.get()
            
            if not doc.exists:
                return {"status": "error", "message": "Document not found in Firestore"}
            
            data = doc.to_dict()
            title = data['titles'].get(lang, data['titles'].get('en'))
            content_html = data['content'].get(lang, data['content'].get('en'))
            image_url = data.get('thumbnailUrl')
            
            # HTML 태그 제거하고 텍스트만 추출 (간단한 요약용)
            soup = BeautifulSoup(content_html, 'html.parser')
            text_content = soup.get_text()
            
            # 요약 생성
            summary = self.summarizer.summarize(title, text_content[:5000], lang=lang)
            
            # 포스팅 텍스트 구성
            if lang == 'en':
                post_text = f"{summary}\n\n\n👉 Read more:\n{wiki_url}"
            else:
                post_text = f"{summary}\n\n\n👉 자세히 보기:\n{wiki_url}"

            # 이미지 처리
            uploaded_image_urn = None
            if image_url:
                # GCS URL이므로 다운로드 후 업로드 필요
                import requests
                import tempfile
                
                try:
                    img_data = requests.get(image_url).content
                    with tempfile.NamedTemporaryFile(delete=False, suffix=".png") as tf:
                        tf.write(img_data)
                        temp_img_path = tf.name
                    
                    logger.info(f"Downloaded image to {temp_img_path}, uploading to LinkedIn...")
                    uploaded_image_urn = self.poster.upload_image(temp_img_path)
                    os.remove(temp_img_path) # 정리
                except Exception as e:
                    logger.error(f"Failed to process image from URL: {e}")

            # 포스팅 실행
            result = self.poster.post_text(
                post_text, 
                title=title, 
                original_url=wiki_url, 
                uploaded_image_urn=uploaded_image_urn
            )
            
            if result:
                return {"status": "success", "message": "Posted to LinkedIn successfully"}
            else:
                return {"status": "error", "message": "Failed to post to LinkedIn"}

        except Exception as e:
            logger.error(f"Error in share_wiki: {e}")
            return {"status": "error", "message": str(e)}
