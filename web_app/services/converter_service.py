import os
import re
import io
import shutil
import datetime
import logging
import requests
import tempfile
from PIL import Image
from google import genai
from dotenv import load_dotenv
from bs4 import BeautifulSoup
from .firebase_service import FirebaseService

load_dotenv()
logger = logging.getLogger(__name__)

class ConverterService:
    def __init__(self):
        self.api_key = os.getenv("GEMINI_API_KEY")
        if self.api_key:
            self.client = genai.Client(api_key=self.api_key)
            self.model_id = 'gemini-3-flash-preview'
            self.image_model_id = 'models/gemini-2.5-flash-image'
        else:
            self.client = None
            logger.error("GEMINI_API_KEY not found.")
        
        self.firebase = FirebaseService()
        self.template_styles = self._get_template_styles()

    def _get_template_styles(self):
        """template.html에서 스타일 추출 (없으면 기본값)"""
        try:
            # web_app/templates/template.html 또는 루트의 template.html 참조
            # 여기서는 루트의 template.html을 참조한다고 가정하거나, web_app 내에 복사 필요
            template_path = "template.html" 
            if not os.path.exists(template_path):
                # web_app/templates/template.html 시도
                template_path = os.path.join(os.path.dirname(__file__), "../templates/template.html")
            
            if os.path.exists(template_path):
                with open(template_path, "r", encoding="utf-8") as f:
                    content = f.read()
                    style_match = re.search(r'<style>(.*?)</style>', content, re.DOTALL)
                    if style_match:
                        return style_match.group(1).strip()
        except Exception as e:
            logger.warning(f"Could not read template styles: {e}")
        return ""

    async def process_markdown(self, file_content: str, filename: str, image_mode: str = "auto", category: str = "tech"):
        """
        마크다운 내용을 받아 변환, 이미지 생성, 업로드까지 수행하는 메인 로직
        file_content: 마크다운 텍스트
        filename: 원본 파일명 (예: '2025 전망.md')
        image_mode: 'auto' (자동 생성) 또는 'manual' (수동 삽입)
        category: 'tech' (Tech Wiki) 또는 'news' (Banya Official News)
        """
        if not self.client:
            return {"status": "error", "message": "Gemini Client not initialized"}

        base_name = os.path.splitext(filename)[0]
        logger.info(f"Processing: {base_name} (image_mode: {image_mode}, category: {category})")

        # 1. ID 결정 (매핑 확인) - 카테고리별로 분리
        id_map = self.firebase.get_id_map(category=category)
        is_new_id = False
        
        # 카테고리별 키 생성 (카테고리 구분)
        map_key = f"{category}:{base_name}"
        if map_key in id_map:
            wiki_id = id_map[map_key]
            logger.info(f"Found existing ID: {wiki_id} (category: {category})")
        else:
            # 새 ID 생성
            wiki_id = self._generate_id(base_name)
            is_new_id = True
            logger.info(f"Generated new ID: {wiki_id} (category: {category})")

        # 2. 영문 제목 생성 (메타데이터용)
        title_en = self._generate_english_title(base_name, wiki_id)

        # 3. 요약 이미지 처리
        image_url = None
        image_html = ""
        
        if image_mode == "manual":
            # 수동 삽입 모드: MD 파일에서 이미지 링크 추출
            extracted_url = self._extract_image_from_markdown(file_content)
            if extracted_url:
                logger.info(f"Extracted image URL from markdown: {extracted_url}")
                # 구글 드라이브 링크인 경우 GCS에 업로드
                if 'drive.google.com' in extracted_url:
                    image_url = self._download_and_upload_google_drive_image(extracted_url, wiki_id, category)
                    if not image_url:
                        # 업로드 실패 시 변환된 URL 사용 (폴백)
                        image_url = self._convert_google_drive_link(extracted_url)
                        logger.warning(f"Failed to upload Google Drive image, using converted URL: {image_url}")
                else:
                    image_url = extracted_url
                
                if image_url:
                    image_html = f'<div class="my-6 rounded-lg overflow-hidden border border-[#a2a9b1] shadow-sm"><img src="{image_url}" alt="Summary Image" class="w-full h-auto object-cover" style="aspect-ratio: 16/9;"></div>'
            else:
                logger.warning("No image URL found in markdown content")
        else:
            # 자동 생성 모드: Gemini로 이미지 생성
            temp_dir = f"temp_{wiki_id}"
            os.makedirs(temp_dir, exist_ok=True)
            images_dir = os.path.join(temp_dir, "images")
            os.makedirs(images_dir, exist_ok=True)

            try:
                image_path = self._generate_summary_image(file_content, wiki_id, images_dir)
                if image_path:
                    # GCS 업로드 (카테고리별 경로)
                    if category == 'news':
                        dest_path = f"banya-news-images/{wiki_id}/{os.path.basename(image_path)}"
                    else:
                        dest_path = f"wiki-images/{wiki_id}/{os.path.basename(image_path)}"
                    image_url = self.firebase.upload_image(image_path, dest_path)
                    if image_url:
                        image_html = f'<div class="my-6 rounded-lg overflow-hidden border border-[#a2a9b1] shadow-sm"><img src="{image_url}" alt="Summary Image" class="w-full h-auto object-cover" style="aspect-ratio: 16/9;"></div>'
            except Exception as e:
                logger.error(f"Image generation failed: {e}")

        # 4. HTML 변환 (KO / EN)
        html_ko = self._convert_to_html(file_content, "ko", image_html, wiki_id)
        html_en = self._convert_to_html(file_content, "en", image_html, wiki_id)

        # 5. Firestore 저장
        current_date = datetime.date.today().isoformat()
        logger.info(f"Saving to Firestore with category: {category}, wiki_id: {wiki_id}")
        success = self.firebase.save_wiki_content(
            wiki_id=wiki_id,
            title_ko=base_name,
            title_en=title_en,
            last_updated=current_date,
            html_ko=html_ko,
            html_en=html_en,
            thumbnail_url=image_url,
            category=category
        )
        if not success:
            logger.error(f"Failed to save to Firestore (category: {category}, wiki_id: {wiki_id})")

        # 6. ID 매핑 업데이트 (카테고리별로 분리)
        if success and is_new_id:
            id_map[map_key] = wiki_id
            self.firebase.save_id_map(id_map, category=category)

        # 7. 정리 (자동 생성 모드일 때만 temp_dir 정리)
        if image_mode == "auto":
            temp_dir = f"temp_{wiki_id}"
        shutil.rmtree(temp_dir, ignore_errors=True)

        if success:
            return {
                "status": "success", 
                "wiki_id": wiki_id, 
                "link": f"https://tony.banya.ai/report/{wiki_id}",
                "preview_html_ko": html_ko,
                "preview_html_en": html_en
            }
        else:
            return {"status": "error", "message": "Firestore save failed"}

    def _generate_id(self, base_name):
        try:
            prompt = f"Translate this title into a concise, professional English filename (no extension, lowercase, use hyphens for spaces): {base_name}"
            response = self.client.models.generate_content(model=self.model_id, contents=prompt)
            translated = response.text.strip().lower().replace(" ", "-")
            return re.sub(r'[^\w\-_\.]', '', translated)
        except:
            return f"wiki-{datetime.date.today().isoformat()}"

    def _generate_english_title(self, base_name, default_id):
        try:
            prompt = f"Translate this title into a natural, professional English title (Capitalized Case, no special chars): {base_name}. STRICT: Return ONLY the title."
            response = self.client.models.generate_content(model=self.model_id, contents=prompt)
            return response.text.strip().replace('"', '')
        except:
            return default_id.replace("-", " ").title()

    def _extract_image_from_markdown(self, markdown_content: str) -> str:
        """
        마크다운 내용에서 첫 번째 이미지 URL을 추출합니다.
        지원 형식:
        - ![alt](url)
        - <img src="url" alt="alt">
        - <img src='url' alt='alt'>
        구글 드라이브 공유 링크는 자동으로 직접 이미지 URL로 변환됩니다.
        """
        if not markdown_content:
            return None
        
        url = None
        
        # 1. Markdown 이미지 형식: ![alt](url)
        markdown_pattern = r'!\[.*?\]\((.*?)\)'
        match = re.search(markdown_pattern, markdown_content)
        if match:
            url = match.group(1).strip()
        
        # 2. HTML img 태그 형식: <img src="url" ...>
        if not url:
            html_pattern = r'<img\s+[^>]*src=["\']([^"\']+)["\']'
            match = re.search(html_pattern, markdown_content, re.IGNORECASE)
            if match:
                url = match.group(1).strip()
        
        if not url or not (url.startswith('http://') or url.startswith('https://')):
            logger.warning("No valid image URL found in markdown content")
            return None
        
        # 3. 구글 드라이브 링크를 직접 이미지 URL로 변환
        url = self._convert_google_drive_link(url)
        
        return url
    
    def _convert_google_drive_link(self, url: str) -> str:
        """
        구글 드라이브 공유 링크를 직접 이미지 URL로 변환합니다.
        
        지원 형식:
        - https://drive.google.com/file/d/FILE_ID/view?usp=sharing
        - https://drive.google.com/file/d/FILE_ID/view
        - https://drive.google.com/open?id=FILE_ID
        - https://drive.google.com/uc?id=FILE_ID (이미 변환된 형식)
        
        변환 형식:
        - https://drive.google.com/uc?export=view&id=FILE_ID
        """
        if not url or 'drive.google.com' not in url:
            return url
        
        # FILE_ID 추출
        file_id = None
        
        # 형식 1: /file/d/FILE_ID/view?usp=sharing 또는 /file/d/FILE_ID/view
        # 더 정확한 패턴: /file/d/ 다음에 FILE_ID가 오고, 그 다음 /view 또는 끝
        match = re.search(r'/file/d/([a-zA-Z0-9_-]+)(?:/view|/|$|\?)', url)
        if match:
            file_id = match.group(1)
            logger.info(f"Extracted file ID from /file/d/ pattern: {file_id}")
        
        # 형식 2: ?id=FILE_ID 또는 &id=FILE_ID
        if not file_id:
            match = re.search(r'[?&]id=([a-zA-Z0-9_-]+)', url)
            if match:
                file_id = match.group(1)
                logger.info(f"Extracted file ID from ?id= pattern: {file_id}")
        
        # 형식 3: /uc?id=FILE_ID (이미 변환된 형식)
        if not file_id:
            match = re.search(r'/uc\?id=([a-zA-Z0-9_-]+)', url)
            if match:
                file_id = match.group(1)
                logger.info(f"Extracted file ID from /uc?id= pattern: {file_id}")
        
        if file_id:
            # 직접 이미지 URL로 변환 (여러 형식 시도)
            # 방법 1: uc?export=view (가장 일반적)
            converted_url = f"https://drive.google.com/uc?export=view&id={file_id}"
            # 방법 2: thumbnail (대안)
            # converted_url = f"https://drive.google.com/thumbnail?id={file_id}&sz=w1920-h1080"
            logger.info(f"Converted Google Drive link: {url[:80]}... -> {converted_url}")
            return converted_url
        
        # 변환 실패 시 원본 URL 반환
        logger.warning(f"Could not extract file ID from Google Drive link: {url}")
        return url
    
    def _download_and_upload_google_drive_image(self, drive_url: str, wiki_id: str, category: str) -> str:
        """
        구글 드라이브 이미지를 다운로드하여 GCS에 업로드합니다.
        이 방법이 직접 URL보다 더 안정적입니다.
        """
        try:
            # 구글 드라이브 링크에서 FILE_ID 추출
            file_id = None
            match = re.search(r'/file/d/([a-zA-Z0-9_-]+)', drive_url)
            if match:
                file_id = match.group(1)
            
            if not file_id:
                # 다른 형식 시도
                match = re.search(r'[?&]id=([a-zA-Z0-9_-]+)', drive_url)
                if match:
                    file_id = match.group(1)
            
            if not file_id:
                logger.warning(f"Could not extract file ID from Google Drive URL: {drive_url}")
                return None
            
            # 구글 드라이브 직접 다운로드 URL (파일이 공유 설정되어 있어야 함)
            download_url = f"https://drive.google.com/uc?export=download&id={file_id}"
            
            # 이미지 다운로드
            logger.info(f"Downloading Google Drive image: {download_url}")
            response = requests.get(download_url, allow_redirects=True, timeout=30)
            
            if response.status_code != 200:
                logger.warning(f"Failed to download image: HTTP {response.status_code}")
                return None
            
            # Content-Type 확인
            content_type = response.headers.get('Content-Type', '')
            if not content_type.startswith('image/'):
                # 구글 드라이브가 HTML 응답을 반환할 수 있음 (큰 파일의 경우)
                # 이 경우 확인 페이지를 건너뛰고 직접 다운로드 시도
                if 'text/html' in content_type:
                    # 직접 다운로드 URL 재시도
                    direct_url = f"https://drive.google.com/uc?export=download&confirm=t&id={file_id}"
                    response = requests.get(direct_url, allow_redirects=True, timeout=30)
                    content_type = response.headers.get('Content-Type', '')
                    if not content_type.startswith('image/'):
                        logger.warning(f"Downloaded content is not an image: {content_type}")
                        return None
            
            # 임시 파일로 저장
            file_ext = '.jpg'  # 기본 확장자
            if 'jpeg' in content_type or 'jpg' in content_type:
                file_ext = '.jpg'
            elif 'png' in content_type:
                file_ext = '.png'
            elif 'gif' in content_type:
                file_ext = '.gif'
            elif 'webp' in content_type:
                file_ext = '.webp'
            
            temp_dir = f"temp_{wiki_id}"
            os.makedirs(temp_dir, exist_ok=True)
            temp_file = os.path.join(temp_dir, f"drive_image_{file_id}{file_ext}")
            
            with open(temp_file, 'wb') as f:
                f.write(response.content)
            
            logger.info(f"Downloaded image to: {temp_file}")
            
            # GCS 업로드
            if category == 'news':
                dest_path = f"banya-news-images/{wiki_id}/drive_image_{file_id}{file_ext}"
            else:
                dest_path = f"wiki-images/{wiki_id}/drive_image_{file_id}{file_ext}"
            
            image_url = self.firebase.upload_image(temp_file, dest_path)
            
            # 임시 파일 정리
            try:
                os.remove(temp_file)
            except:
                pass
            
            if image_url:
                logger.info(f"Successfully uploaded Google Drive image to GCS: {image_url}")
                return image_url
            else:
                logger.warning("Failed to upload image to GCS")
                return None
                
        except Exception as e:
            logger.error(f"Error downloading/uploading Google Drive image: {e}")
            import traceback
            traceback.print_exc()
            return None

    def _generate_summary_image(self, content, base_name, output_dir):
        # (기존 md_to_html_converter의 _generate_summary_image 로직을 여기에 구현)
        # 간소화를 위해 핵심 로직만 복사 (프롬프트 생성 -> 이미지 생성 -> 저장)
        try:
            visual_prompt = f"Create a professional, high-resolution 16:9 technical illustration with NO TEXT based on: {content[:500]}"
            response = self.client.models.generate_content(model=self.image_model_id, contents=visual_prompt)
            
            image_data = None
            if response.candidates:
                for cand in response.candidates:
                    for part in cand.content.parts:
                        if part.inline_data:
                            image_data = part.inline_data.data
                            break
            
            if image_data:
                img = Image.open(io.BytesIO(image_data))
                # Crop logic (omitted for brevity, can add back if needed)
                filename = f"{base_name}_summary.png"
                path = os.path.join(output_dir, filename)
                img.save(path, format='PNG')
                return path
        except Exception as e:
            logger.error(f"Image gen error: {e}")
        return None

    def _convert_to_html(self, md_content, lang, image_html, title_ph):
        # (기존 convert_file 내부의 프롬프트 로직 재사용)
        lang_label = "Korean" if lang == "ko" else "English"
        trans_instruction = "IMPORTANT: First, translate the entire content into natural, professional technical English." if lang == "en" else ""
        
        prompt = f"""
        You are an expert web developer. {trans_instruction}
        Convert Markdown to HTML in {lang_label}.
        
        [CRITICAL: MOBILE OPTIMIZATION]
        1. Include <!DOCTYPE html> and a proper <head> section.
        2. MANDATORY: Include <meta name="viewport" content="width=device-width, initial-scale=1.0"> in the <head>.
        3. Use Tailwind CSS classes for a responsive layout.
        
        [Structure Requirement]
        <article class="wiki-content max-w-4xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
            <div class="flex flex-col sm:flex-row justify-between items-start border-b border-[#a2a9b1] pb-2 mb-6">
               <h1 class="text-2xl sm:text-3xl font-sans font-bold text-[#000] leading-tight">{{{{TITLE}}}}</h1>
            </div>
            {image_html}
            <div class="wiki-html-content prose prose-slate max-w-none text-[#202122] leading-relaxed overflow-x-hidden">
               <style>{self.template_styles}</style>
               {{{{CONTENT}}}}
            </div>
        </article>
        
        [MathJax] Preserve $...$ and $$...$$. Ensure formulas are responsive.
        [Output] Return a COMPLETE, valid HTML5 document. No markdown fences.
        
        Content:
        {md_content}
        """
        try:
            res = self.client.models.generate_content(model=self.model_id, contents=prompt)
            html = res.text.strip().replace("```html", "").replace("```", "")
            return self._post_process_math_spacing(html)
        except:
            return "<div>Error generating HTML</div>"

    def _post_process_math_spacing(self, html_content):
        # (기존 로직 복사)
        html_content = re.sub(r'<(p|div|span)[^>]*>\s*(\$[^\$]+\$)\s*</\1>', r' \2 ', html_content)
        return html_content

