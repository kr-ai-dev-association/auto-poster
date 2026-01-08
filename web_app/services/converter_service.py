import os
import re
import io
import shutil
import datetime
import logging
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

    async def process_markdown(self, file_content: str, filename: str):
        """
        마크다운 내용을 받아 변환, 이미지 생성, 업로드까지 수행하는 메인 로직
        file_content: 마크다운 텍스트
        filename: 원본 파일명 (예: '2025 전망.md')
        """
        if not self.client:
            return {"status": "error", "message": "Gemini Client not initialized"}

        base_name = os.path.splitext(filename)[0]
        logger.info(f"Processing: {base_name}")

        # 1. ID 결정 (매핑 확인)
        id_map = self.firebase.get_id_map()
        is_new_id = False
        
        if base_name in id_map:
            wiki_id = id_map[base_name]
            logger.info(f"Found existing ID: {wiki_id}")
        else:
            # 새 ID 생성
            wiki_id = self._generate_id(base_name)
            is_new_id = True
            logger.info(f"Generated new ID: {wiki_id}")

        # 2. 영문 제목 생성 (메타데이터용)
        title_en = self._generate_english_title(base_name, wiki_id)

        # 3. 요약 이미지 생성
        # 임시 작업 디렉토리 생성
        temp_dir = f"temp_{wiki_id}"
        os.makedirs(temp_dir, exist_ok=True)
        images_dir = os.path.join(temp_dir, "images")
        os.makedirs(images_dir, exist_ok=True)

        image_url = None
        try:
            image_path = self._generate_summary_image(file_content, wiki_id, images_dir)
            if image_path:
                # GCS 업로드
                dest_path = f"wiki-images/{wiki_id}/{os.path.basename(image_path)}"
                image_url = self.firebase.upload_image(image_path, dest_path)
        except Exception as e:
            logger.error(f"Image generation failed: {e}")

        # 이미지 HTML 태그
        image_html = ""
        if image_url:
            image_html = f'<div class="my-6 rounded-lg overflow-hidden border border-[#a2a9b1] shadow-sm"><img src="{image_url}" alt="Summary Image" class="w-full h-auto object-cover" style="aspect-ratio: 16/9;"></div>'

        # 4. HTML 변환 (KO / EN)
        html_ko = self._convert_to_html(file_content, "ko", image_html, wiki_id)
        html_en = self._convert_to_html(file_content, "en", image_html, wiki_id)

        # 5. Firestore 저장
        current_date = datetime.date.today().isoformat()
        success = self.firebase.save_wiki_content(
            wiki_id=wiki_id,
            title_ko=base_name,
            title_en=title_en,
            last_updated=current_date,
            html_ko=html_ko,
            html_en=html_en,
            thumbnail_url=image_url
        )

        # 6. ID 매핑 업데이트
        if success and is_new_id:
            id_map[base_name] = wiki_id
            self.firebase.save_id_map(id_map)

        # 7. 정리
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

