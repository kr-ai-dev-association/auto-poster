import os
import sys
import json
import shutil
import re
import importlib.util
from typing import Dict, Any, Optional
from fastapi.responses import FileResponse
from google.genai import types
from pdf2image import convert_from_bytes
from PIL import Image

# 루트 경로 추가
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(os.path.dirname(current_dir))
sys.path.append(project_root)

# 숫자로 시작하는 디렉토리는 직접 import가 불가능하므로 importlib 사용
def load_youtube_poster():
    module_path = os.path.join(project_root, 'youtube_poster', 'youtube_poster.py')
    spec = importlib.util.spec_from_file_location("youtube_poster", module_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.YouTubeAutoPoster

YouTubeAutoPoster = load_youtube_poster()

class YouTubeMetadataValidator:
    """YouTube 메타데이터 검증기"""
    
    # YouTube API 제약사항
    MAX_TITLE_LENGTH = 100
    MAX_DESCRIPTION_LENGTH = 5000
    MAX_TAGS_COUNT = 500
    MAX_TAG_LENGTH = 30
    
    @staticmethod
    def validate(metadata):
        """
        YouTube 메타데이터를 검증합니다.
        
        Returns:
            tuple: (is_valid: bool, errors: list, warnings: list)
        """
        errors = []
        warnings = []
        
        if not isinstance(metadata, dict):
            errors.append("메타데이터는 딕셔너리 형식이어야 합니다.")
            return False, errors, warnings
        
        # 필수 필드 검증
        required_fields = ['title', 'description', 'tags']
        for field in required_fields:
            if field not in metadata:
                errors.append(f"필수 필드 '{field}'가 없습니다.")
        
        if errors:
            return False, errors, warnings
        
        # 제목 검증
        title = str(metadata['title']).strip()
        if not title:
            errors.append("제목이 비어있습니다.")
        elif len(title) > YouTubeMetadataValidator.MAX_TITLE_LENGTH:
            errors.append(f"제목이 너무 깁니다. (최대 {YouTubeMetadataValidator.MAX_TITLE_LENGTH}자, 현재 {len(title)}자)")
            # 자동 자르기 제안
            warnings.append(f"제목을 {YouTubeMetadataValidator.MAX_TITLE_LENGTH}자로 자르는 것을 권장합니다.")
        
        # 설명 검증
        description = str(metadata['description']).strip()
        if not description:
            errors.append("설명이 비어있습니다.")
        elif len(description) > YouTubeMetadataValidator.MAX_DESCRIPTION_LENGTH:
            errors.append(f"설명이 너무 깁니다. (최대 {YouTubeMetadataValidator.MAX_DESCRIPTION_LENGTH}자, 현재 {len(description)}자)")
            warnings.append(f"설명을 {YouTubeMetadataValidator.MAX_DESCRIPTION_LENGTH}자로 자르는 것을 권장합니다.")
        
        # 태그 검증
        tags = metadata['tags']
        if not isinstance(tags, list):
            errors.append("태그는 배열 형식이어야 합니다.")
        elif len(tags) == 0:
            warnings.append("태그가 없습니다. 검색 최적화를 위해 태그를 추가하는 것을 권장합니다.")
        else:
            if len(tags) > YouTubeMetadataValidator.MAX_TAGS_COUNT:
                errors.append(f"태그가 너무 많습니다. (최대 {YouTubeMetadataValidator.MAX_TAGS_COUNT}개, 현재 {len(tags)}개)")
                warnings.append(f"태그를 {YouTubeMetadataValidator.MAX_TAGS_COUNT}개로 줄이는 것을 권장합니다.")
            
            # 각 태그 검증
            invalid_tags = []
            for i, tag in enumerate(tags):
                tag_str = str(tag).strip()
                if not tag_str:
                    invalid_tags.append(f"태그 #{i+1}: 빈 태그")
                elif len(tag_str) > YouTubeMetadataValidator.MAX_TAG_LENGTH:
                    invalid_tags.append(f"태그 #{i+1} ('{tag_str[:20]}...'): {len(tag_str)}자 (최대 {YouTubeMetadataValidator.MAX_TAG_LENGTH}자)")
            
            if invalid_tags:
                errors.extend(invalid_tags)
        
        is_valid = len(errors) == 0
        return is_valid, errors, warnings
    
    @staticmethod
    def fix(metadata):
        """
        메타데이터를 자동으로 수정합니다 (제한 초과 시 자르기).
        
        Returns:
            dict: 수정된 메타데이터
        """
        fixed = metadata.copy()
        
        # 제목 자르기
        if 'title' in fixed:
            title = str(fixed['title']).strip()
            if len(title) > YouTubeMetadataValidator.MAX_TITLE_LENGTH:
                fixed['title'] = title[:YouTubeMetadataValidator.MAX_TITLE_LENGTH].strip()
                print(f"⚠️ 제목이 {len(title)}자에서 {len(fixed['title'])}자로 자동 자름")
        
        # 설명 자르기
        if 'description' in fixed:
            description = str(fixed['description']).strip()
            if len(description) > YouTubeMetadataValidator.MAX_DESCRIPTION_LENGTH:
                fixed['description'] = description[:YouTubeMetadataValidator.MAX_DESCRIPTION_LENGTH].strip()
                print(f"⚠️ 설명이 {len(description)}자에서 {len(fixed['description'])}자로 자동 자름")
        
        # 태그 정리
        if 'tags' in fixed and isinstance(fixed['tags'], list):
            import re
            fixed_tags = []
            for tag in fixed['tags']:
                tag_str = str(tag).strip()
                if tag_str:
                    # YouTube에서 허용하지 않는 문자 제거 (<, > 등)
                    tag_str = tag_str.replace('<', '').replace('>', '')
                    # 이모지 및 특수 유니코드 문자 제거 (알파벳, 숫자, 기본 문장부호만 허용)
                    tag_str = re.sub(r'[^\w\s\-\'\"\.\,\!\?\&\#\@\(\)\[\]\:\;\+\=\/\\]', '', tag_str, flags=re.UNICODE)
                    # 연속된 공백 정리
                    tag_str = ' '.join(tag_str.split())

                    if not tag_str:
                        continue

                    # 태그 길이 제한
                    if len(tag_str) > YouTubeMetadataValidator.MAX_TAG_LENGTH:
                        tag_str = tag_str[:YouTubeMetadataValidator.MAX_TAG_LENGTH].strip()
                        print(f"⚠️ 태그 '{tag_str}'가 자동으로 자름")
                    fixed_tags.append(tag_str)

            # 빈 태그 제거 및 중복 제거
            fixed_tags = list(dict.fromkeys([t for t in fixed_tags if t.strip()]))

            # 태그 개수 제한
            if len(fixed_tags) > YouTubeMetadataValidator.MAX_TAGS_COUNT:
                fixed_tags = fixed_tags[:YouTubeMetadataValidator.MAX_TAGS_COUNT]
                print(f"⚠️ 태그가 {len(fixed_tags)}개로 자동 제한")

            fixed['tags'] = fixed_tags
        
        return fixed

class YouTubeService:
    # 진행률 저장소 (클래스 변수)
    _upload_progress: Dict[str, Dict] = {}
    
    def __init__(self):
        self._poster = None  # 지연 초기화
        self.base_v_dir = os.path.join(project_root, 'youtube_poster', 'v_source')
    
    @classmethod
    def get_upload_progress(cls, upload_id: str):
        """업로드 진행률 조회"""
        return cls._upload_progress.get(upload_id)
    
    @classmethod
    def update_upload_progress(cls, upload_id: str, step: str, progress: int, message: str, result=None):
        """업로드 진행률 업데이트"""
        from datetime import datetime
        cls._upload_progress[upload_id] = {
            'upload_id': upload_id,
            'step': step,
            'progress': progress,
            'message': message,
            'timestamp': datetime.now().isoformat(),
            'result': result
        }
    
    @classmethod
    def clear_upload_progress(cls, upload_id: str):
        """업로드 진행률 삭제"""
        if upload_id in cls._upload_progress:
            del cls._upload_progress[upload_id]
    
    @property
    def poster(self):
        """필요할 때만 YouTubeAutoPoster 인스턴스 생성"""
        if self._poster is None:
            self._poster = YouTubeAutoPoster()
        return self._poster

    def get_categories(self):
        """사용 가능한 카테고리 목록을 반환합니다."""
        if not os.path.exists(self.base_v_dir):
            return []

        categories = []
        for item in os.listdir(self.base_v_dir):
            item_path = os.path.join(self.base_v_dir, item)
            if os.path.isdir(item_path) and not item.startswith('.'):
                categories.append(item)

        categories.sort()
        if 'tech' in categories:
            categories.remove('tech')
            categories.insert(0, 'tech')
        
        return categories

    def get_logo_path(self, category):
        v_dir = os.path.join(self.base_v_dir, category)
        if not os.path.exists(v_dir):
            return None

        logo_files = [f for f in os.listdir(v_dir) if f.lower().endswith('.png') and 'logo' in f.lower()]
        if not logo_files:
            logo_files = [f for f in os.listdir(v_dir) if f.lower().endswith('.png')]

        if logo_files:
            return os.path.join(v_dir, logo_files[0])
        return None

    def _compress_pdf(self, pdf_content: bytes) -> bytes:
        """PDF 파일을 압축합니다. 이미지 기반 PDF의 경우 이미지 품질을 낮춰서 압축합니다."""
        try:
            import PyPDF2
            import io
            import tempfile
            
            # 먼저 PyPDF2로 기본 압축 시도
            pdf_reader = PyPDF2.PdfReader(io.BytesIO(pdf_content))
            pdf_writer = PyPDF2.PdfWriter()
            
            for page in pdf_reader.pages:
                page.compress_content_streams()
                pdf_writer.add_page(page)
            
            if pdf_reader.metadata:
                pdf_writer.add_metadata(pdf_reader.metadata)
            
            output_buffer = io.BytesIO()
            pdf_writer.write(output_buffer)
            compressed_pdf = output_buffer.getvalue()
            output_buffer.close()
            
            # 기본 압축으로 충분하지 않으면 (10% 미만 감소) 이미지 압축 시도
            original_size = len(pdf_content)
            compressed_size = len(compressed_pdf)
            compression_ratio = (1 - compressed_size / original_size) * 100
            
            if compression_ratio < 10:  # 10% 미만 압축이면 이미지 압축 시도
                print(f"📦 기본 압축 효과 부족 ({compression_ratio:.1f}%). 이미지 압축을 시도합니다...")
                try:
                    # PDF를 이미지로 변환 (낮은 DPI로)
                    images = convert_from_bytes(pdf_content, dpi=150)  # 원본보다 낮은 DPI
                    
                    if not images:
                        print(f"⚠️ PDF를 이미지로 변환할 수 없습니다. 기본 압축 결과 사용.")
                        return compressed_pdf
                    
                    # img2pdf 사용 시도 (더 나은 압축)
                    try:
                        import img2pdf
                        
                        # 이미지를 압축된 JPEG로 변환
                        compressed_images = []
                        for img in images:
                            img_buffer = io.BytesIO()
                            # JPEG 품질 70%로 저장 (품질과 크기 균형)
                            img.convert('RGB').save(img_buffer, format='JPEG', quality=70, optimize=True)
                            img_buffer.seek(0)
                            compressed_images.append(img_buffer.getvalue())
                        
                        # img2pdf로 PDF 생성
                        compressed_pdf = img2pdf.convert(compressed_images)
                        
                        new_size_mb = len(compressed_pdf) / (1024 * 1024)
                        original_size_mb = original_size / (1024 * 1024)
                        new_ratio = (1 - len(compressed_pdf) / original_size) * 100
                        print(f"✅ 이미지 압축 완료 (img2pdf): {original_size_mb:.1f}MB → {new_size_mb:.1f}MB ({new_ratio:.1f}% 감소)")
                        
                        return compressed_pdf
                    except ImportError:
                        # img2pdf가 없으면 reportlab 시도
                        try:
                            from reportlab.pdfgen import canvas
                            from reportlab.lib.pagesizes import letter
                            from reportlab.lib.utils import ImageReader
                            
                            # 임시 파일로 압축된 PDF 생성
                            with tempfile.NamedTemporaryFile(suffix='.pdf', delete=False) as tmp_pdf:
                                tmp_pdf_path = tmp_pdf.name
                            
                            c = canvas.Canvas(tmp_pdf_path, pagesize=letter)
                            page_width, page_height = letter
                            
                            for img in images:
                                # 이미지 크기 조정 (페이지 크기에 맞춤)
                                img_width, img_height = img.size
                                aspect = img_height / img_width
                                
                                if aspect > 1:  # 세로가 더 긴 경우
                                    display_height = page_height
                                    display_width = page_height / aspect
                                else:  # 가로가 더 긴 경우
                                    display_width = page_width
                                    display_height = page_width * aspect
                                
                                # 중앙 정렬
                                x = (page_width - display_width) / 2
                                y = (page_height - display_height) / 2
                                
                                # 이미지 품질 낮춰서 추가 (JPEG 품질 70%)
                                img_buffer = io.BytesIO()
                                img.save(img_buffer, format='JPEG', quality=70, optimize=True)
                                img_buffer.seek(0)
                                
                                c.drawImage(ImageReader(img_buffer), x, y, width=display_width, height=display_height)
                                c.showPage()
                            
                            c.save()
                            
                            # 압축된 PDF 읽기
                            with open(tmp_pdf_path, 'rb') as f:
                                compressed_pdf = f.read()
                            
                            # 임시 파일 삭제
                            os.unlink(tmp_pdf_path)
                            
                            new_size_mb = len(compressed_pdf) / (1024 * 1024)
                            original_size_mb = original_size / (1024 * 1024)
                            new_ratio = (1 - len(compressed_pdf) / original_size) * 100
                            print(f"✅ 이미지 압축 완료 (reportlab): {original_size_mb:.1f}MB → {new_size_mb:.1f}MB ({new_ratio:.1f}% 감소)")
                            
                            return compressed_pdf
                        except ImportError:
                            print(f"⚠️ img2pdf와 reportlab이 모두 설치되지 않았습니다. 기본 압축 결과 사용.")
                            return compressed_pdf
                except Exception as e:
                    print(f"⚠️ 이미지 압축 실패: {e}. 기본 압축 결과 사용.")
                    import traceback
                    traceback.print_exc()
                    return compressed_pdf
            
            return compressed_pdf
        except Exception as e:
            print(f"⚠️ PDF 압축 중 오류 발생: {e}")
            import traceback
            traceback.print_exc()
            # 압축 실패 시 원본 반환
            return pdf_content

    async def generate_metadata(self, pdf_content, category, lang='ko', text_content: Optional[str] = None):
        """PDF 분석을 통해 유튜브 메타데이터를 생성합니다. YouTube API 인증 없이 Gemini만 사용."""
        from core.summarizer import GeminiSummarizer
        
        from typing import Optional
        import os
        import tempfile
        from google.genai import types as types_genai # types conflict avoidance
        import json
        import re
        import string

        # Input validation
        if not text_content and (not pdf_content or len(pdf_content) == 0):
            raise Exception("PDF 파일 또는 텍스트 내용이 비어있거나 전달되지 않았습니다.")

        if pdf_content:
            print(f"📄 PDF 파일 수신: {len(pdf_content)} bytes")

        # 템플릿 로드 (카테고리 폴더에서)
        v_dir = os.path.join(self.base_v_dir, category)
        desc_path = os.path.join(v_dir, f'desc_{lang}.md')
        if not os.path.exists(desc_path):
             desc_path = os.path.join(v_dir, 'desc.md')
        
        desc_template = ""
        if os.path.exists(desc_path):
            with open(desc_path, 'r', encoding='utf-8') as f:
                desc_template = f.read()

        lang_str = "Korean" if lang == 'ko' else "English"

        # 템플릿에서 고정 섹션 추출 (서비스 안내, SEO 키워드)
        fixed_section_ko = ""
        fixed_section_en = ""

        if desc_template:
            # 한국어 템플릿에서 고정 섹션 추출
            if "📢 서비스 및 협업 안내" in desc_template:
                idx = desc_template.find("📢 서비스 및 협업 안내")
                fixed_section_ko = desc_template[idx:].strip()
            # 영어 템플릿에서 고정 섹션 추출
            elif "📢 Service & Collaboration" in desc_template:
                idx = desc_template.find("📢 Service & Collaboration")
                fixed_section_en = desc_template[idx:].strip()

        fixed_section = fixed_section_ko or fixed_section_en

        # 프롬프트 구성
        prompt = f"""
        [CRITICAL] You MUST analyze the attached PDF/content and extract its ACTUAL topic, key points, and information.
        Generate YouTube-optimized metadata in {lang_str} based on the ACTUAL CONTENT of the PDF/text provided.

        [INSTRUCTIONS]
        1. Title: Create a click-worthy, dramatic title that reflects the ACTUAL CONTENT of the PDF.
           - The title must be about the specific topic covered in the PDF, not generic.

        2. Description STRUCTURE (MUST follow this exact format):

           PART 1 - CONTENT SECTION (Write based on PDF content):
           - Opening hook: A dramatic one-line quote or statement about the topic
           - Context paragraph: Explain the situation/problem from the PDF
           - Main content: Key points, findings, and value from the PDF (use emojis and formatting)
           - Call-to-action: Encourage viewers to watch

           PART 2 - FIXED SECTION (COPY EXACTLY as provided below):
           You MUST include this EXACT text at the end of the description, without any modifications:

           {fixed_section}

        3. Tags: Generate 20+ highly relevant hashtags and keywords in {lang_str} based on the PDF content.
           Include both topic-specific tags AND the fixed brand tags from the template.

        [REFERENCE TEMPLATE - for formatting style]
        {desc_template}

        [CRITICAL RULES]
        - The description MUST end with the exact fixed section provided above (Service & Collaboration, SEO & Keywords)
        - DO NOT modify, omit, or rewrite the fixed section - copy it EXACTLY
        - Only the content section (PART 1) should be written based on the PDF content
        - Use the same emoji style and formatting as the template
        - Ensure URLs are plain text so they become clickable on YouTube

        Return ONLY a valid JSON object:
        {{
          "title": "Specific title about the PDF content",
          "description": "Content section based on PDF...\\n\\n📢 서비스 및 협업 안내\\n... (exact fixed section)",
          "tags": ["relevant", "tags", "from", "pdf", "content", ...]
        }}
        """

        summarizer = self.poster.summarizer
        if not summarizer.client:
            raise Exception("GEMINI_API_KEY가 설정되지 않았습니다.")
        
        try:
            if text_content:
                print(f"🤖 Gemini API 호출 중... (텍스트 기반, 길이: {len(text_content)})")
                combined_prompt = f"{prompt}\n\n[CONTENT]\n{text_content}"
                response = summarizer.client.models.generate_content(
                    model=summarizer.model_id,
                    contents=combined_prompt
                )
            else:
                # PDF 처리 로직
                pdf_size_mb = len(pdf_content) / (1024 * 1024)
                print(f"🤖 Gemini API 호출 중... (PDF 크기: {pdf_size_mb:.1f}MB)")
                
                # 50MB 이상이면 압축 시도
                if pdf_size_mb > 50:
                    print(f"📦 PDF가 50MB를 초과합니다 ({pdf_size_mb:.1f}MB). 압축을 시도합니다...")
                    try:
                        pdf_content = self._compress_pdf(pdf_content)
                        compressed_size_mb = len(pdf_content) / (1024 * 1024)
                        print(f"✅ PDF 압축 완료: {pdf_size_mb:.1f}MB → {compressed_size_mb:.1f}MB ({((1 - compressed_size_mb/pdf_size_mb) * 100):.1f}% 감소)")
                        pdf_size_mb = compressed_size_mb
                    except Exception as e:
                        print(f"⚠️ PDF 압축 실패: {e}. 원본 파일로 진행합니다.")
                
                # 먼저 텍스트 추출 시도 (이미지 기반 PDF 확인용)
                extracted_text = ""
                try:
                    import PyPDF2
                    import io

                    pdf_reader = PyPDF2.PdfReader(io.BytesIO(pdf_content))

                    # 최대 50페이지까지만 추출
                    max_pages = min(50, len(pdf_reader.pages))
                    for i in range(max_pages):
                        page = pdf_reader.pages[i]
                        page_text = page.extract_text() or ""
                        extracted_text += f"\n[Page {i+1}]\n{page_text}\n"

                    extracted_text = extracted_text.strip()
                    print(f"📝 PDF 텍스트 추출 시도: {len(extracted_text)} 문자")
                except Exception as e:
                    print(f"⚠️ PDF 텍스트 추출 실패: {e}")
                    extracted_text = ""

                # 텍스트가 충분히 추출되었으면 (500자 이상) 텍스트 기반으로 처리
                if len(extracted_text) >= 500:
                    print(f"✅ 텍스트 기반 처리 (추출된 텍스트: {len(extracted_text)} 문자)")

                    if len(extracted_text) > 100000:  # 10만자 이상이면 자름
                        extracted_text = extracted_text[:100000] + "\n... (내용이 길어 일부만 표시됨)"

                    combined_prompt = f"{prompt}\n\n[CONTENT]\n{extracted_text}"
                    response = summarizer.client.models.generate_content(
                        model=summarizer.model_id,
                        contents=combined_prompt
                    )
                else:
                    # 텍스트가 부족하면 File API 사용 (압축 후 50MB 이하 또는 이미지 기반 PDF)
                    if pdf_size_mb > 50:
                        print(f"⚠️ 압축 후에도 PDF가 너무 큽니다 ({pdf_size_mb:.1f}MB). 이미지 기반 PDF라 텍스트 추출 불가.")
                        raise Exception(f"PDF 파일이 너무 큽니다 ({pdf_size_mb:.1f}MB). 압축 후에도 50MB를 초과합니다. 이미지 기반 PDF는 50MB 이하만 지원됩니다.")

                    print(f"📤 이미지 기반 PDF 감지. File API로 업로드 중... ({pdf_size_mb:.1f}MB)")

                    with tempfile.NamedTemporaryFile(suffix='.pdf', delete=False) as tmp_pdf:
                        tmp_pdf.write(pdf_content)
                        tmp_pdf_path = tmp_pdf.name

                    try:
                        print(f"📤 Uploading PDF to Gemini File API...")
                        pdf_file_ref = summarizer.client.files.upload(
                            file=tmp_pdf_path,
                            config={'mime_type': 'application/pdf'}
                        )
                        print(f"✅ PDF Uploaded: {pdf_file_ref.name}")

                        # File API로 업로드한 파일은 FileData 형식으로 변환해야 함
                        file_uri = getattr(pdf_file_ref, 'uri', None) or getattr(pdf_file_ref, 'name', None)
                        if not file_uri:
                            raise Exception("File API 응답에서 URI 또는 name을 찾을 수 없습니다.")

                        file_data = types_genai.FileData(file_uri=file_uri)
                        file_part = types_genai.Part(file_data=file_data)

                        # 파일을 먼저, 프롬프트를 나중에 전달해야 파일 내용을 분석함
                        response = summarizer.client.models.generate_content(
                            model=summarizer.model_id,
                            contents=[file_part, prompt]
                        )
                    except Exception as e:
                        print(f"❌ File API 실패: {e}")
                        raise Exception(f"이미지 기반 PDF 처리 실패. File API 에러: {str(e)}")
                    finally:
                        if os.path.exists(tmp_pdf_path):
                            os.unlink(tmp_pdf_path)
            
            print(f"✅ Gemini API 응답 수신")

            # 응답 검증
            if not response or not hasattr(response, 'text') or not response.text:
                # candidates 확인
                if hasattr(response, 'candidates') and response.candidates:
                    candidate = response.candidates[0]
                    if hasattr(candidate, 'finish_reason'):
                        print(f"⚠️ 응답 종료 이유: {candidate.finish_reason}")
                    if hasattr(candidate, 'content') and candidate.content:
                        if hasattr(candidate.content, 'parts') and candidate.content.parts:
                            texts = [p.text for p in candidate.content.parts if hasattr(p, 'text') and p.text]
                            if texts:
                                raw_text = ' '.join(texts).strip()
                                print(f"📝 Parts에서 텍스트 추출: {len(raw_text)} 문자")
                            else:
                                raise Exception("Gemini API 응답이 비어있습니다. (parts에 텍스트 없음)")
                        else:
                            raise Exception("Gemini API 응답이 비어있습니다. (parts 없음)")
                    else:
                        raise Exception("Gemini API 응답이 비어있습니다. (content 없음)")
                else:
                    raise Exception("Gemini API 응답이 비어있습니다. (candidates 없음)")
            else:
                raw_text = response.text.strip()

            # 빈 텍스트 체크
            if not raw_text:
                raise Exception("Gemini API 응답 텍스트가 비어있습니다.")

            # 원본 응답 로깅 (디버깅용)
            print(f"📝 원본 응답 (처음 500자): {raw_text[:500]}")
            
            # Remove any markdown code block wrappers if present
            clean_text = re.sub(r'```json\s*|\s*```', '', raw_text)
            clean_text = clean_text.strip()
            
            # JSON 객체 추출 함수 (중괄호 매칭)
            def extract_json_object(text):
                """중괄호를 정확히 매칭하여 JSON 객체 추출"""
                start_idx = text.find('{')
                if start_idx == -1:
                    return None
                
                depth = 0
                in_string = False
                escape_next = False
                
                for i in range(start_idx, len(text)):
                    char = text[i]
                    
                    if escape_next:
                        escape_next = False
                        continue
                    
                    if char == '\\':
                        escape_next = True
                        continue
                    
                    if char == '"' and not escape_next:
                        in_string = not in_string
                        continue
                    
                    if not in_string:
                        if char == '{':
                            depth += 1
                        elif char == '}':
                            depth -= 1
                            if depth == 0:
                                return text[start_idx:i+1]
                
                return None
            
            # JSON 객체 추출
            json_text = extract_json_object(clean_text)
            if json_text:
                clean_text = json_text
                print(f"📝 JSON 추출 완료 (길이: {len(clean_text)})")
            else:
                # 대체 방법: 정규식으로 추출
                json_match = re.search(r'\{.*\}', clean_text, re.DOTALL)
                if json_match:
                    clean_text = json_match.group(0)
                    print(f"📝 JSON 추출 완료 (정규식, 길이: {len(clean_text)})")
                else:
                    print(f"⚠️ JSON 객체를 찾을 수 없습니다. 원본 텍스트 사용")
        
            # JSON 파싱 시도 (여러 단계)
            metadata = None
            parse_attempts = [
                ("기본 파싱", lambda t: json.loads(t)),
                ("strict=False", lambda t: json.loads(t, strict=False)),
            ]
            
            for attempt_name, parse_func in parse_attempts:
                try:
                    metadata = parse_func(clean_text)
                    print(f"✅ JSON 파싱 성공 ({attempt_name})")
                    break
                except json.JSONDecodeError as e:
                    print(f"⚠️ JSON 파싱 실패 ({attempt_name}): {e}")
                    if attempt_name == "기본 파싱":
                        print(f"📝 파싱 시도한 텍스트 (처음 1000자): {clean_text[:1000]}")
            
            # 파싱 실패 시 추가 정리 시도
            if metadata is None:
                print(f"🔧 추가 정리 시도 중...")
                
                # 제어 문자 제거
                import string
                printable = set(string.printable)
                cleaned = ''.join(filter(lambda x: x in printable, clean_text))
                
                # 다시 JSON 추출
                json_text = extract_json_object(cleaned)
                if json_text:
                    cleaned = json_text
                else:
                    json_match = re.search(r'\{.*\}', cleaned, re.DOTALL)
                    if json_match:
                        cleaned = json_match.group(0)
                
                # 일반적인 JSON 오류 수정 시도
                def fix_json_strings(text):
                    """문자열 내부의 줄바꿈과 특수 문자를 이스케이프"""
                    result = []
                    in_string = False
                    escape_next = False
                    i = 0
                    
                    while i < len(text):
                        char = text[i]
                        
                        if escape_next:
                            result.append(char)
                            escape_next = False
                            i += 1
                            continue
                        
                        if char == '\\':
                            result.append(char)
                            escape_next = True
                            i += 1
                            continue
                        
                        if char == '"':
                            in_string = not in_string
                            result.append(char)
                            i += 1
                            continue
                        
                        if in_string:
                            # 문자열 내부: 줄바꿈과 탭을 이스케이프
                            if char == '\n':
                                result.append('\\n')
                            elif char == '\r':
                                result.append('\\r')
                            elif char == '\t':
                                result.append('\\t')
                            elif char == '"':  # 문자열 내부의 따옴표는 이스케이프
                                result.append('\\"')
                            elif ord(char) < 32:  # 제어 문자
                                result.append(f'\\u{ord(char):04x}')
                            else:
                                result.append(char)
                        else:
                            result.append(char)
                        
                        i += 1
                    
                    return ''.join(result)
                
                def fix_json_common_errors(text, error_line, error_col):
                    """에러 위치를 기반으로 일반적인 JSON 오류 수정"""
                    lines = text.split('\n')
                    if error_line > len(lines):
                        return text
                    
                    error_text = lines[error_line - 1]
                    
                    # 에러 위치 주변 텍스트 확인
                    start = max(0, error_col - 50)
                    end = min(len(error_text), error_col + 50)
                    context = error_text[start:end]
                    
                    print(f"🔧 에러 컨텍스트: {context}")
                    
                    # 일반적인 패턴 수정
                    fixed_text = text
                    
                    # 패턴 1: "value" "key" -> "value", "key"
                    fixed_text = re.sub(r'"\s+"([^"]+)"\s*:', r'", "\1":', fixed_text)
                    
                    # 패턴 2: } "key" -> }, "key"
                    fixed_text = re.sub(r'}\s+"([^"]+)"\s*:', r'}, "\1":', fixed_text)
                    
                    # 패턴 3: ] "key" -> ], "key"
                    fixed_text = re.sub(r']\s+"([^"]+)"\s*:', r'], "\1":', fixed_text)
                    
                    # 패턴 4: "value" 다음에 쉼표 없이 "key"가 오는 경우
                    fixed_text = re.sub(r'"\s*\n\s*"([^"]+)"\s*:', r'",\n    "\1":', fixed_text)
                    
                    # 패턴 5: 배열에서 ] 다음에 쉼표 없이 값이 오는 경우
                    fixed_text = re.sub(r']\s+(["\[])', r'], \1', fixed_text)
                    
                    return fixed_text
                
                # 1단계: 문자열 내부 특수 문자 이스케이프
                cleaned = fix_json_strings(cleaned)
                
                # 2단계: 구조 수정 없이 먼저 파싱 시도
                try:
                    test_parse = json.loads(cleaned, strict=False)
                    print(f"✅ JSON 파싱 성공 (문자열 수정 후)")
                    metadata = test_parse
                except json.JSONDecodeError as test_e:
                    # 구조 수정 시도
                    print(f"🔧 JSON 구조 수정 시도 중...")
                    if test_e.lineno and test_e.colno:
                        cleaned = fix_json_common_errors(cleaned, test_e.lineno, test_e.colno)
                
                # 마지막 파싱 시도
                if metadata is None:
                    try:
                        metadata = json.loads(cleaned, strict=False)
                        print(f"✅ JSON 파싱 성공 (추가 정리 후)")
                    except json.JSONDecodeError as e2:
                        print(f"❌ JSON 파싱 완전 실패: {e2}")
                        print(f"📝 최종 시도 텍스트 (처음 2000자): {cleaned[:2000]}")
                        print(f"📝 에러 위치: line {e2.lineno}, column {e2.colno}")
                        if e2.lineno and e2.colno:
                            lines = cleaned.split('\n')
                            if e2.lineno <= len(lines):
                                error_line = lines[e2.lineno - 1]
                                print(f"📝 에러 라인: {error_line}")
                                if e2.colno <= len(error_line):
                                    print(f"📝 에러 위치 표시: {error_line[:e2.colno-1]}>>>{error_line[e2.colno-1:min(e2.colno+20, len(error_line))]}")
                        raise Exception(f"JSON 파싱 실패: {str(e2)}. 응답 텍스트를 확인하세요.")
            
            # 메타데이터 검증
            print(f"🔍 메타데이터 검증 중...")
            is_valid, errors, warnings = YouTubeMetadataValidator.validate(metadata)
            
            if warnings:
                for warning in warnings:
                    print(f"⚠️ 경고: {warning}")
            
            if not is_valid:
                print(f"❌ 메타데이터 검증 실패:")
                for error in errors:
                    print(f"   - {error}")
                
                # 자동 수정 시도
                print(f"🔧 메타데이터 자동 수정 시도 중...")
                metadata = YouTubeMetadataValidator.fix(metadata)
                
                # 재검증
                is_valid, errors, warnings = YouTubeMetadataValidator.validate(metadata)
                if not is_valid:
                    error_msg = "메타데이터 검증 실패:\n" + "\n".join(f"  - {e}" for e in errors)
                    raise Exception(error_msg)
                else:
                    print(f"✅ 메타데이터 자동 수정 완료")
            else:
                print(f"✅ 메타데이터 검증 통과")
            
            return metadata
        except Exception as e:
            print(f"❌ Error generating metadata: {e}")
            import traceback
            traceback.print_exc()
            # Fallback metadata는 사용하지 않고 에러를 전파
            raise Exception(f"메타데이터 생성 실패: {str(e)}")

    def generate_thumbnail_from_pdf(self, pdf_content, output_path):
        """PDF 첫 페이지를 썸네일 이미지로 변환합니다."""
        try:
            print(f"🖼️ PDF 첫 페이지에서 썸네일 생성 중...")

            # PDF 첫 페이지를 이미지로 변환 (300 DPI)
            images = convert_from_bytes(pdf_content, first_page=1, last_page=1, dpi=300)

            if not images:
                print(f"⚠️ PDF에서 이미지를 추출할 수 없습니다.")
                return None

            img = images[0]

            # YouTube 썸네일 권장 크기: 1280x720 (16:9 비율)
            target_width = 1280
            target_height = 720

            # 원본 이미지 크기
            orig_width, orig_height = img.size

            # 비율 계산하여 리사이즈
            ratio = max(target_width / orig_width, target_height / orig_height)
            new_width = int(orig_width * ratio)
            new_height = int(orig_height * ratio)

            img = img.resize((new_width, new_height), Image.LANCZOS)

            # 중앙 크롭하여 정확히 1280x720으로 맞춤
            left = (new_width - target_width) // 2
            top = (new_height - target_height) // 2
            right = left + target_width
            bottom = top + target_height

            img = img.crop((left, top, right, bottom))

            # JPEG로 저장 (YouTube 썸네일은 2MB 미만이어야 함)
            img.save(output_path, 'JPEG', quality=95, optimize=True)

            file_size = os.path.getsize(output_path)
            print(f"✅ 썸네일 생성 완료: {output_path} ({file_size / 1024:.1f}KB)")

            return output_path

        except Exception as e:
            print(f"⚠️ 썸네일 생성 실패: {e}")
            import traceback
            traceback.print_exc()
            return None

    async def process_and_upload(self, video_content, filename, pdf_content, category, lang='ko', use_thumbnail=True, upload_id=None, gen_video_id=None, text_content=None):
        """영상을 처리하고 유튜브에 업로드합니다.

        Args:
            text_content: 대본 또는 나레이션 텍스트 (이 값이 있으면 PDF 대신 사용)
        """
        if upload_id:
            self.update_upload_progress(upload_id, 'init', 5, '업로드 준비 중...')
        v_dir = os.path.join(self.base_v_dir, category)
        if not os.path.exists(v_dir):
            os.makedirs(v_dir, exist_ok=True)

        # 1. 파일 저장
        video_path = os.path.join(v_dir, f"raw_{filename}")
        with open(video_path, "wb") as f:
            f.write(video_content)
        
        pdf_path = os.path.join(v_dir, "temp_metadata_source.pdf")
        with open(pdf_path, "wb") as f:
            f.write(pdf_content)

        # 썸네일 생성
        thumbnail_path = None
        if use_thumbnail:
            thumbnail_path = os.path.join(v_dir, "temp_thumbnail.jpg")
            thumbnail_path = self.generate_thumbnail_from_pdf(pdf_content, thumbnail_path)

        try:
            # 2. 메타데이터 생성
            desc_path = os.path.join(v_dir, f'desc_{lang}.md')
            if not os.path.exists(desc_path):
                desc_path = os.path.join(v_dir, 'desc.md')
            
            desc_template = ""
            if os.path.exists(desc_path):
                with open(desc_path, 'r', encoding='utf-8') as f:
                    desc_template = f.read()

            if upload_id:
                self.update_upload_progress(upload_id, 'metadata', 15, 'YouTube 메타데이터 생성 중 (AI 분석)...')

            # 대본(text_content)이 있으면 우선 사용, 없으면 PDF에서 추출
            if text_content and len(text_content) >= 100:
                print(f"📝 메타데이터 생성 시작 (대본 텍스트: {len(text_content)} 문자)")
                metadata = await self.generate_metadata(None, category, lang, text_content=text_content)
            else:
                print(f"📝 메타데이터 생성 시작 (PDF: {pdf_path})")
                # YouTube API 인증 없이 메타데이터 생성 (generate_metadata 메서드 사용)
                with open(pdf_path, 'rb') as f:
                    pdf_content = f.read()
                metadata = await self.generate_metadata(pdf_content, category, lang)
            print(f"✅ 메타데이터 생성 완료: {metadata.get('title', 'N/A')[:50]}...")
            
            if upload_id:
                self.update_upload_progress(upload_id, 'metadata_done', 40, '메타데이터 생성 완료, 검증 중...')
            
            # 업로드 전 태그 정제 및 검증
            print(f"🔧 메타데이터 정제 중 (태그 특수문자 제거 등)...")
            metadata = YouTubeMetadataValidator.fix(metadata)

            print(f"🔍 업로드 전 메타데이터 최종 검증 중...")
            is_valid, errors, warnings = YouTubeMetadataValidator.validate(metadata)

            if warnings:
                for warning in warnings:
                    print(f"⚠️ 경고: {warning}")

            if not is_valid:
                print(f"❌ 메타데이터 검증 실패:")
                for error in errors:
                    print(f"   - {error}")
                error_msg = "업로드 전 메타데이터 검증 실패:\n" + "\n".join(f"  - {e}" for e in errors)
                raise Exception(error_msg)
            else:
                print(f"✅ 메타데이터 최종 검증 통과")
            
            if upload_id:
                self.update_upload_progress(upload_id, 'uploading', 60, 'YouTube에 영상 업로드 중...')

            # 3. 로고 합성 제거됨 - Gen Video에서 이미 로고가 합성되므로 바로 업로드
            # 3. 로고 합성 제거됨 - Gen Video에서 이미 로고가 합성되므로 바로 업로드
            print(f"⏭️ [DEBUG] 로고 합성 건너뜀 (Gen Video에서 이미 합성됨)")
            print(f"   [DEBUG] 원본 비디오 경로: {video_path}")
            print(f"   [DEBUG] 원본 비디오 크기: {os.path.getsize(video_path)} bytes")
            
            # 혹시 모를 로고 파일 존재 여부 확인 (디버깅용)
            logo_path = self.get_logo_path(category)
            print(f"   [DEBUG] (참고) 해당 카테고리 로고 파일: {logo_path} (존재 여부: {os.path.exists(logo_path) if logo_path else False})")
            
            final_video_path = video_path
            print(f"   [DEBUG] 최종 업로드 파일: {final_video_path}")

            # 4. 유튜브 업로드
            print(f"📤 YouTube 업로드 시작...")
            if thumbnail_path:
                print(f"   썸네일 경로: {thumbnail_path}")
            try:
                video_id = self.poster.upload_video(final_video_path, metadata, thumbnail_path=thumbnail_path)
                print(f"✅ YouTube 업로드 완료: {video_id}")
            except Exception as e:
                print(f"❌ YouTube 업로드 실패: {e}")
                import traceback
                traceback.print_exc()
                if upload_id:
                    self.update_upload_progress(upload_id, 'error', 0, f'업로드 실패: {str(e)}')
                raise
            
            if not video_id:
                raise Exception("YouTube upload failed")

            # 5. 정리
            for f in [video_path, pdf_path, final_video_path, thumbnail_path]:
                if f and os.path.exists(f):
                    os.remove(f)

            result = {
                "status": "success",
                "video_id": video_id,
                "link": f"https://youtu.be/{video_id}",
                "metadata": metadata
            }
            
            if upload_id:
                self.update_upload_progress(upload_id, 'done', 100, '모든 작업 완료!', result)
            
            # Gen Video ID가 있으면 'posted' 상태로 업데이트
            if gen_video_id:
                try:
                    from services.pdf2mp4_service import PDF2MP4Service
                    service = PDF2MP4Service()
                    service.update_video_stage(gen_video_id, 'posted')
                    print(f"✅ Video stage updated to 'posted' for {gen_video_id}")
                except Exception as e:
                    print(f"⚠️ Failed to update video stage: {e}")

            return result

        except Exception as e:
            # 오류 발생 시에도 임시 파일 정리
            for f in [video_path, pdf_path, thumbnail_path]:
                if f and os.path.exists(f):
                    os.remove(f)
            
            if upload_id:
                self.update_upload_progress(upload_id, 'error', 0, f'처리 중 오류 발생: {str(e)}')
            raise e

    async def share_to_linkedin(self, video_id, video_url, lang='ko'):
        """유튜브 영상을 링크드인에 공유합니다."""
        import requests
        from core.linkedin_poster import LinkedInPoster
        from core.summarizer import GeminiSummarizer

        # 유튜브 API 키
        youtube_api_key = os.getenv("YOUTUBE_API_KEY")
        if not youtube_api_key:
            return {"status": "error", "message": "YOUTUBE_API_KEY not found"}

        # 1. 유튜브 메타데이터 가져오기
        from googleapiclient.discovery import build
        youtube_client = build('youtube', 'v3', developerKey=youtube_api_key)
        request = youtube_client.videos().list(
            part="snippet",
            id=video_id
        )
        response = request.execute()
        
        if not response['items']:
            return {"status": "error", "message": "Video not found"}
        
        item = response['items'][0]
        snippet = item['snippet']
        title = snippet.get('title')
        description = snippet.get('description')
        
        # 썸네일 URL
        thumbnails = snippet.get('thumbnails', {})
        thumbnail_url = (
            thumbnails.get('maxres', {}).get('url') or 
            thumbnails.get('high', {}).get('url') or 
            thumbnails.get('default', {}).get('url')
        )

        # 2. 요약 생성
        summarizer = GeminiSummarizer()
        content_for_ai = f"Title: {title}\n\nDescription: {description}"
        generated_summary = summarizer.summarize(title, content_for_ai, lang=lang)
        
        if lang == 'en':
            post_text = f"{generated_summary}\n\n\n📺 Watch the full video:\n{video_url}"
        else:
            post_text = f"{generated_summary}\n\n\n📺 전체 영상 보기:\n{video_url}"

        # 3. 링크드인 포스팅
        poster = LinkedInPoster()
        
        # 썸네일 처리
        local_image_path = None
        uploaded_image_urn = None
        if thumbnail_url:
            img_res = requests.get(thumbnail_url)
            if img_res.status_code == 200:
                local_image_path = f"temp_thumb_{video_id}.jpg"
                with open(local_image_path, 'wb') as f:
                    f.write(img_res.content)
                uploaded_image_urn = poster.upload_image(local_image_path)
                if os.path.exists(local_image_path):
                    os.remove(local_image_path)

        result = poster.post_text(post_text, title=title, original_url=video_url, uploaded_image_urn=uploaded_image_urn)
        
        if result:
            return {"status": "success", "message": f"LinkedIn에 성공적으로 포스팅되었습니다 ({lang})."}
        else:
            return {"status": "error", "message": "LinkedIn 포스팅에 실패했습니다."}

