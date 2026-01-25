import os
import io
import json
import base64
import uuid
import logging
import asyncio
from typing import Optional, Dict, Any, List
from datetime import datetime
from google import genai
from google.genai import types
from PIL import Image
from reportlab.lib.pagesizes import landscape, A4
from reportlab.pdfgen import canvas
from reportlab.lib.utils import ImageReader
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)


def extract_first_json(text: str) -> Optional[str]:
    """Finds the first valid JSON object in the text using brace counting."""
    text = text.strip()
    start_idx = text.find('{')
    if start_idx == -1:
        return None
    
    brace_count = 0
    in_string = False
    escape = False
    
    for i in range(start_idx, len(text)):
        char = text[i]
        
        if in_string:
            if escape:
                escape = False
            elif char == '\\':
                escape = True
            elif char == '"':
                in_string = False
        else:
            if char == '"':
                in_string = True
            elif char == '{':
                brace_count += 1
            elif char == '}':
                brace_count -= 1
                if brace_count == 0:
                    return text[start_idx:i+1]
    
    return None


class ContentGeneratorService:
    """콘텐츠 기획 및 이미지 생성, PDF 출력 서비스"""

    def __init__(self):
        self._client = None
        self.research_model = 'gemini-2.0-flash'  # Stable version for JSON output
        self.image_model = 'gemini-2.0-flash-exp'  # 이미지 생성용 (Imagen 3)

        # 출력 디렉토리 설정
        self.output_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), 'generated_content')
        self.pdf_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), 'generated_pdfs')
        os.makedirs(self.output_dir, exist_ok=True)
        os.makedirs(self.pdf_dir, exist_ok=True)

    @property
    def client(self):
        """Lazy initialization of Gemini client (sync)"""
        if self._client is None:
            api_key = os.getenv("GEMINI_API_KEY")
            if api_key:
                self._client = genai.Client(api_key=api_key)
                logger.info("Gemini client initialized for ContentGeneratorService")
            else:
                logger.error("GEMINI_API_KEY not found.")
        return self._client

    @property
    def async_client(self):
        """Get async client for non-blocking API calls"""
        if self.client:
            return self.client.aio
        return None

    async def generate_content_plan(
        self,
        topic: str,
        category: str = 'educational',
        target_slides: int = 15,
        language: str = 'ko',
        additional_instructions: str = ''
    ) -> Dict[str, Any]:
        """
        주제를 기반으로 슬라이드 콘텐츠 기획을 생성합니다.

        Args:
            topic: 콘텐츠 주제/기획 아이디어
            category: 카테고리 (educational, entertainment, tech, gaming 등)
            target_slides: 목표 슬라이드 수 (10-20)
            language: 출력 언어
            additional_instructions: 추가 지시사항

        Returns:
            Dict containing content plan with slides
        """
        if not self.client:
            raise ValueError("Gemini client not initialized. Check GEMINI_API_KEY.")

        logger.info(f"Generating content plan for topic: {topic[:50]}...")

        # 카테고리별 스타일 가이드
        style_guides = {
            'educational': "교육적이고 정보가 풍부한 스타일. 단계별 설명과 핵심 개념 강조.",
            'entertainment': "재미있고 흥미진진한 스타일. 시각적 임팩트와 호기심 유발.",
            'tech': "기술적이고 전문적인 스타일. 데이터와 트렌드 중심.",
            'gaming': "게이머 친화적 스타일. 팁, 코드, 공략 정보 중심.",
            'lifestyle': "라이프스타일 중심. 실용적인 팁과 영감을 주는 콘텐츠."
        }

        style_guide = style_guides.get(category, style_guides['educational'])

        prompt = f"""당신은 YouTube 영상 콘텐츠 기획 전문가입니다.
다음 주제를 기반으로 {target_slides}개의 슬라이드로 구성된 콘텐츠 기획안을 작성해주세요.

## 주제/기획 아이디어:
{topic}

## 카테고리: {category}
## 스타일 가이드: {style_guide}

{f"## 추가 지시사항: {additional_instructions}" if additional_instructions else ""}

## 출력 형식 (반드시 JSON 형식으로 출력):
```json
{{
  "title": "영상 제목 (매력적이고 클릭을 유도하는)",
  "description": "영상 설명 (2-3문장)",
  "category": "{category}",
  "target_audience": "타겟 시청자층",
  "estimated_duration": "예상 영상 길이 (분)",
  "slides": [
    {{
      "slide_number": 1,
      "title": "슬라이드 제목",
      "content": "슬라이드에서 다룰 내용 (2-3문장)",
      "narration": "이 슬라이드에서 읽을 나레이션 대본 (TTS용, 자연스러운 구어체)",
      "image_prompt": "이 슬라이드용 이미지 생성 프롬프트 (영어, 구체적이고 시각적인 설명)",
      "duration_seconds": 예상_표시_시간_초
    }},
    ...
  ],
  "hook": "영상 시작 후크 (0-30초, 시청자 주목 끌기)",
  "call_to_action": "좋아요/구독/댓글 유도 멘트",
  "tags": ["관련", "태그", "목록"]
}}
```

## 주의사항:
1. 각 슬라이드의 narration은 TTS로 읽을 대본이므로 자연스러운 구어체로 작성
2. image_prompt는 반드시 영어로, AI 이미지 생성에 적합한 구체적인 설명
3. 첫 슬라이드는 강력한 인트로, 마지막은 CTA 포함 아웃트로
4. 중간에 시청 유지를 위한 티저/예고 포함
5. {'한국어' if language == 'ko' else 'English'}로 title, content, narration 작성
"""

        try:
            # 비동기 클라이언트 사용하여 이벤트 루프 차단 방지
            response = await self.async_client.models.generate_content(
                model=self.research_model,
                contents=prompt,
                config=types.GenerateContentConfig(
                    temperature=0.2,
                    max_output_tokens=8192,
                    response_mime_type="application/json"  # Gemini 1.5/2.0 JSON mode 지원
                )
            )

            response_text = response.text.strip()

            # JSON 추출 (Markdown 코드 블록 지원 강화 + Brace Counting Fallback)
            import re
            json_str = ""
            # 1. ```json ... ``` 패턴 시도
            json_match = re.search(r'```json\s*(\{.*?\})\s*```', response_text, re.DOTALL)
            if json_match:
                json_str = json_match.group(1)
            else:
                # 2. ``` ... ``` 패턴 시도 (언어 지정 없을 때)
                json_match = re.search(r'```\s*(\{.*?\})\s*```', response_text, re.DOTALL)
                if json_match:
                    json_str = json_match.group(1)
                else:
                    # 3. Brace Counting으로 정확한 JSON 객체 추출
                    extracted = extract_first_json(response_text)
                    if extracted:
                        json_str = extracted
                    else:
                        logger.error(f"Failed to extract JSON. Raw response start: {response_text[:1000]}")
                        raise ValueError("Failed to extract JSON from response: No JSON object found")

            # JSON 파싱
            try:
                content_plan = json.loads(json_str)
            except json.JSONDecodeError as e:
                # 파싱 실패 시 로깅 강화
                logger.error(f"JSON Decode Error. Extracted text preview: {json_str[:200]}...")
                raise ValueError(f"Failed to parse extracted JSON: {e}")

            # 기획안 저장
            plan_id = uuid.uuid4().hex[:8]
            plan_filename = f"plan_{plan_id}.json"
            plan_path = os.path.join(self.output_dir, plan_filename)

            content_plan['plan_id'] = plan_id
            content_plan['created_at'] = datetime.now().isoformat()
            content_plan['language'] = language

            with open(plan_path, 'w', encoding='utf-8') as f:
                json.dump(content_plan, f, ensure_ascii=False, indent=2)

            logger.info(f"Content plan saved: {plan_path}")

            return {
                'status': 'success',
                'plan_id': plan_id,
                'plan': content_plan
            }

        except json.JSONDecodeError as e:
            logger.error(f"JSON parsing failed: {e}")
            return {
                'status': 'error',
                'message': f"Failed to parse content plan: {str(e)}"
            }
        except Exception as e:
            logger.error(f"Content plan generation failed: {e}")
            return {
                'status': 'error',
                'message': str(e)
            }

    async def generate_slide_image(
        self,
        image_prompt: str,
        slide_number: int,
        plan_id: str,
        style: str = 'digital art',
        title: str = '',
        narration: str = '',
        content: str = '',
        language: str = 'ko'
    ) -> Dict[str, Any]:
        """
        슬라이드용 이미지를 생성합니다.

        Args:
            image_prompt: 이미지 생성 프롬프트
            slide_number: 슬라이드 번호
            plan_id: 기획안 ID
            style: 이미지 스타일
            title: 슬라이드 제목
            narration: 대본 텍스트
            content: 슬라이드 콘텐츠 (핵심 내용)
            language: 텍스트 언어 (ko/en)

        Returns:
            Dict containing image path
        """
        if not self.client:
            raise ValueError("Gemini client not initialized.")

        # 슬라이드 텍스트 정보 구성
        text_info = ""
        if title:
            text_info += f"Title: {title}\n"
        if content:
            # content가 리스트인 경우 불릿 포인트로 변환
            if isinstance(content, list):
                content_text = "\n".join([f"• {item}" for item in content])
            else:
                content_text = content
            text_info += f"Key Points:\n{content_text}\n"
        if narration:
            # narration은 요약해서 포함 (너무 길면 자르기)
            narration_summary = narration[:200] + "..." if len(narration) > 200 else narration
            text_info += f"Context: {narration_summary}\n"

        # 이미지 프롬프트 강화 - 텍스트 포함 지시
        lang_instruction = "한국어" if language == 'ko' else "English"

        enhanced_prompt = f"""Create a professional YouTube video slide image with the following specifications:

## Visual Content:
{image_prompt}

## Text Overlay Requirements:
The image MUST include the following text elements rendered directly on the image:

1. **Slide Number Badge**: Display "#{slide_number}" in a small rounded badge at the top-left corner with semi-transparent dark background.

2. **Title Area** (top section with semi-transparent dark gradient overlay):
   - Title text in {lang_instruction}: "{title}"
   - Use large, bold, white text that is clearly readable
   - Position at the top of the image

3. **Content Area** (bottom section with semi-transparent dark gradient overlay):
{f'   - Display key points in {lang_instruction}:' if content else ''}
{content_text if content and isinstance(content, str) else ''}
{chr(10).join([f"   • {item}" for item in content]) if content and isinstance(content, list) else ''}
   - Use medium-sized white text
   - Position at the bottom of the image

## Style Requirements:
- Style: {style}, high quality, 16:9 aspect ratio (1920x1080)
- Professional YouTube thumbnail/slide aesthetic
- Vibrant, engaging colors for the background visual
- Semi-transparent dark overlays (gradient) for text areas to ensure readability
- Clean, modern typography
- Text must be {lang_instruction} and perfectly legible
- The visual content should complement the text, not compete with it

## Important:
- ALL text MUST be included and clearly readable in the final image
- Use appropriate font sizes: large for title, medium for content
- Ensure high contrast between text and background"""

        logger.info(f"Generating image for slide {slide_number}: {title[:30] if title else image_prompt[:30]}...")

        try:
            # Gemini 사용 (비동기 클라이언트)
            response = await self.async_client.models.generate_content(
                model="gemini-2.0-flash-exp",
                contents=enhanced_prompt,
                config=types.GenerateContentConfig(
                    response_modalities=['TEXT', 'IMAGE']
                )
            )

            # 이미지 데이터 추출
            image_data = None
            for part in response.candidates[0].content.parts:
                if hasattr(part, 'inline_data') and part.inline_data:
                    image_data = part.inline_data.data
                    break

            if not image_data:
                raise ValueError("No image generated")

            # 이미지 저장
            image_filename = f"{plan_id}_slide_{slide_number:02d}.png"
            image_path = os.path.join(self.output_dir, image_filename)

            # PIL로 이미지 처리 및 16:9 리사이즈
            img = Image.open(io.BytesIO(image_data))
            img = img.convert('RGB')

            # 16:9 비율로 리사이즈 (1920x1080)
            target_width, target_height = 1920, 1080
            img = img.resize((target_width, target_height), Image.Resampling.LANCZOS)

            img.save(image_path, 'PNG', quality=95)

            logger.info(f"Image saved: {image_path}")

            return {
                'status': 'success',
                'slide_number': slide_number,
                'image_path': image_path,
                'filename': image_filename
            }

        except Exception as e:
            logger.error(f"Image generation failed for slide {slide_number}: {e}")
            return {
                'status': 'error',
                'slide_number': slide_number,
                'message': str(e)
            }

    async def generate_all_images(
        self,
        plan_id: str,
        progress_callback=None
    ) -> Dict[str, Any]:
        """
        기획안의 모든 슬라이드 이미지를 생성합니다.

        Args:
            plan_id: 기획안 ID
            progress_callback: 진행 상황 콜백 함수

        Returns:
            Dict containing all image paths
        """
        # 기획안 로드
        plan_path = os.path.join(self.output_dir, f"plan_{plan_id}.json")
        if not os.path.exists(plan_path):
            return {'status': 'error', 'message': 'Plan not found'}

        with open(plan_path, 'r', encoding='utf-8') as f:
            plan = json.load(f)

        slides = plan.get('slides', [])
        language = plan.get('language', 'ko')
        total_slides = len(slides)
        results = []

        for i, slide in enumerate(slides):
            if progress_callback:
                progress_callback(i + 1, total_slides, f"Generating image {i + 1}/{total_slides}")

            result = await self.generate_slide_image(
                image_prompt=slide.get('image_prompt', ''),
                slide_number=slide.get('slide_number', i + 1),
                plan_id=plan_id,
                title=slide.get('title', ''),
                narration=slide.get('narration', ''),
                content=slide.get('content', ''),
                language=language
            )
            results.append(result)

            # API 레이트 리밋 방지
            if i < total_slides - 1:
                await asyncio.sleep(2)

        # 성공한 이미지 수 계산
        success_count = sum(1 for r in results if r['status'] == 'success')

        return {
            'status': 'success' if success_count == total_slides else 'partial',
            'plan_id': plan_id,
            'total': total_slides,
            'success': success_count,
            'results': results
        }

    async def create_pdf_from_plan(
        self,
        plan_id: str,
        title: str = None
    ) -> Dict[str, Any]:
        """
        생성된 이미지들을 PDF로 합칩니다.

        Args:
            plan_id: 기획안 ID
            title: PDF 제목 (없으면 기획안 제목 사용)

        Returns:
            Dict containing PDF path
        """
        # 기획안 로드
        plan_path = os.path.join(self.output_dir, f"plan_{plan_id}.json")
        if not os.path.exists(plan_path):
            return {'status': 'error', 'message': 'Plan not found'}

        with open(plan_path, 'r', encoding='utf-8') as f:
            plan = json.load(f)

        slides = plan.get('slides', [])
        pdf_title = title or plan.get('title', f'Content_{plan_id}')

        # 이미지 파일 수집
        image_files = []
        for slide in slides:
            slide_num = slide.get('slide_number', 0)
            image_filename = f"{plan_id}_slide_{slide_num:02d}.png"
            image_path = os.path.join(self.output_dir, image_filename)
            if os.path.exists(image_path):
                image_files.append((slide_num, image_path))

        if not image_files:
            return {'status': 'error', 'message': 'No images found for this plan'}

        # 슬라이드 번호순 정렬
        image_files.sort(key=lambda x: x[0])

        # PDF 생성
        safe_title = "".join(c for c in pdf_title if c.isalnum() or c in (' ', '-', '_')).strip()[:50]
        pdf_filename = f"{safe_title}_{plan_id}.pdf"
        pdf_path = os.path.join(self.pdf_dir, pdf_filename)

        # 16:9 비율의 PDF 페이지 크기 (1920x1080 픽셀 기준)
        page_width = 1920 * 0.75  # 포인트로 변환 (약 1440pt)
        page_height = 1080 * 0.75  # 약 810pt

        c = canvas.Canvas(pdf_path, pagesize=(page_width, page_height))

        for slide_num, image_path in image_files:
            img = Image.open(image_path)
            img_reader = ImageReader(img)
            c.drawImage(img_reader, 0, 0, width=page_width, height=page_height)
            c.showPage()

        c.save()

        # 메타데이터 저장
        meta_path = pdf_path.rsplit('.', 1)[0] + '.json'
        meta_data = {
            'plan_id': plan_id,
            'title': pdf_title,
            'filename': pdf_filename,
            'slide_count': len(image_files),
            'created_at': datetime.now().isoformat(),
            'language': plan.get('language', 'ko'),
            'category': plan.get('category', 'educational'),
            'narrations': [slide.get('narration', '') for slide in slides]
        }
        with open(meta_path, 'w', encoding='utf-8') as f:
            json.dump(meta_data, f, ensure_ascii=False, indent=2)

        logger.info(f"PDF created: {pdf_path}")

        return {
            'status': 'success',
            'pdf_path': pdf_path,
            'filename': pdf_filename,
            'slide_count': len(image_files),
            'plan_id': plan_id
        }

    def list_generated_pdfs(self) -> List[Dict[str, Any]]:
        """생성된 PDF 목록을 반환합니다."""
        pdf_files = []

        if not os.path.exists(self.pdf_dir):
            return pdf_files

        for filename in os.listdir(self.pdf_dir):
            if filename.endswith('.pdf'):
                filepath = os.path.join(self.pdf_dir, filename)
                stat = os.stat(filepath)

                # 메타데이터 로드
                meta_path = filepath.rsplit('.', 1)[0] + '.json'
                metadata = {}
                if os.path.exists(meta_path):
                    try:
                        with open(meta_path, 'r', encoding='utf-8') as f:
                            metadata = json.load(f)
                    except Exception:
                        pass

                pdf_files.append({
                    'filename': filename,
                    'filepath': filepath,
                    'size': stat.st_size,
                    'created_at': stat.st_mtime,
                    'title': metadata.get('title', filename),
                    'plan_id': metadata.get('plan_id'),
                    'slide_count': metadata.get('slide_count', 0),
                    'language': metadata.get('language'),
                    'category': metadata.get('category')
                })

        # 생성일 기준 정렬 (최신순)
        pdf_files.sort(key=lambda x: x['created_at'], reverse=True)

        return pdf_files

    def get_plan(self, plan_id: str) -> Optional[Dict[str, Any]]:
        """기획안을 로드합니다."""
        plan_path = os.path.join(self.output_dir, f"plan_{plan_id}.json")
        if os.path.exists(plan_path):
            with open(plan_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        return None

    def list_plans(self) -> List[Dict[str, Any]]:
        """기획안 목록을 반환합니다."""
        plans = []

        if not os.path.exists(self.output_dir):
            return plans

        # 이미지 파일 목록 먼저 수집 (plan_id별 개수 계산용)
        image_counts = {}
        for filename in os.listdir(self.output_dir):
            if filename.endswith('.png') and '_slide_' in filename:
                plan_id = filename.split('_slide_')[0]
                image_counts[plan_id] = image_counts.get(plan_id, 0) + 1

        for filename in os.listdir(self.output_dir):
            if filename.startswith('plan_') and filename.endswith('.json'):
                filepath = os.path.join(self.output_dir, filename)
                try:
                    with open(filepath, 'r', encoding='utf-8') as f:
                        plan = json.load(f)
                        plan_id = plan.get('plan_id')
                        plans.append({
                            'plan_id': plan_id,
                            'title': plan.get('title'),
                            'category': plan.get('category'),
                            'slide_count': len(plan.get('slides', [])),
                            'image_count': image_counts.get(plan_id, 0),
                            'created_at': plan.get('created_at'),
                            'language': plan.get('language')
                        })
                except Exception:
                    pass

        # 생성일 기준 정렬 (최신순)
        plans.sort(key=lambda x: x.get('created_at', ''), reverse=True)

        return plans

    def delete_plan(self, plan_id: str) -> bool:
        """기획안과 관련 파일들을 삭제합니다."""
        deleted = False

        # 기획안 JSON 삭제
        plan_path = os.path.join(self.output_dir, f"plan_{plan_id}.json")
        if os.path.exists(plan_path):
            os.remove(plan_path)
            deleted = True

        # 관련 이미지 삭제
        for filename in os.listdir(self.output_dir):
            if filename.startswith(f"{plan_id}_slide_"):
                os.remove(os.path.join(self.output_dir, filename))
                deleted = True

        return deleted

    def delete_pdf(self, filename: str) -> bool:
        """PDF와 메타데이터를 삭제합니다."""
        filepath = os.path.join(self.pdf_dir, filename)
        deleted = False

        if os.path.exists(filepath):
            os.remove(filepath)
            deleted = True

        # 메타데이터 삭제
        meta_path = filepath.rsplit('.', 1)[0] + '.json'
        if os.path.exists(meta_path):
            os.remove(meta_path)

        return deleted

    def list_images_for_plan(self, plan_id: str) -> List[Dict[str, Any]]:
        """특정 기획안의 생성된 이미지 목록을 반환합니다."""
        images = []

        if not os.path.exists(self.output_dir):
            return images

        for filename in os.listdir(self.output_dir):
            if filename.startswith(f"{plan_id}_slide_") and filename.endswith('.png'):
                filepath = os.path.join(self.output_dir, filename)
                stat = os.stat(filepath)

                # 슬라이드 번호 추출
                try:
                    slide_num = int(filename.split('_slide_')[1].split('.')[0])
                except (IndexError, ValueError):
                    slide_num = 0

                images.append({
                    'filename': filename,
                    'filepath': filepath,
                    'size': stat.st_size,
                    'slide_number': slide_num,
                    'created_at': stat.st_mtime
                })

        # 슬라이드 번호순 정렬
        images.sort(key=lambda x: x['slide_number'])

        return images


# 싱글톤 인스턴스
content_generator = ContentGeneratorService()
