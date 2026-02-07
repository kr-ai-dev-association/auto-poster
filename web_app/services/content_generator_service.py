import os
import io
import json
import base64
import uuid
import logging
import asyncio
import re
import aiohttp
from typing import Optional, Dict, Any, List
from datetime import datetime
from urllib.parse import urljoin, urlparse
from google import genai
from google.genai import types
from PIL import Image, ImageDraw, ImageFont
import textwrap
from reportlab.lib.pagesizes import landscape, A4
from reportlab.pdfgen import canvas
from reportlab.lib.utils import ImageReader
from PyPDF2 import PdfReader, PdfWriter
from dotenv import load_dotenv
from bs4 import BeautifulSoup

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
        self.image_model = 'gemini-3-pro-image-preview'  # Nano Banana Pro

        # 출력 디렉토리 설정
        self.output_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), 'generated_content')
        self.pdf_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), 'generated_pdfs')
        self.web_images_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), 'generated_content', 'web_images')
        os.makedirs(self.output_dir, exist_ok=True)
        os.makedirs(self.pdf_dir, exist_ok=True)
        os.makedirs(self.web_images_dir, exist_ok=True)

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

    async def scrape_images_from_url(self, url: str, min_width: int = 400, min_height: int = 300, max_images: int = 5) -> List[Dict[str, Any]]:
        """
        URL에서 이미지를 스크래핑합니다.

        Args:
            url: 스크래핑할 웹 페이지 URL
            min_width: 최소 이미지 너비 (작은 아이콘 제외)
            min_height: 최소 이미지 높이
            max_images: 최대 가져올 이미지 수

        Returns:
            List of image info dicts with 'url', 'alt', 'width', 'height'
        """
        images = []
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5'
        }

        try:
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=15)) as session:
                async with session.get(url, headers=headers, ssl=False) as response:
                    if response.status != 200:
                        logger.warning(f"Failed to fetch URL {url}: status {response.status}")
                        return images

                    html = await response.text()
                    soup = BeautifulSoup(html, 'html.parser')

                    # img 태그 찾기
                    for img in soup.find_all('img'):
                        if len(images) >= max_images:
                            break

                        img_url = img.get('src') or img.get('data-src') or img.get('data-lazy-src')
                        if not img_url:
                            continue

                        # 상대 경로를 절대 경로로 변환
                        img_url = urljoin(url, img_url)

                        # 데이터 URI 스킵
                        if img_url.startswith('data:'):
                            continue

                        # 작은 이미지 스킵 (아이콘, 로고 등)
                        width = img.get('width', '')
                        height = img.get('height', '')

                        try:
                            w = int(str(width).replace('px', '')) if width else 0
                            h = int(str(height).replace('px', '')) if height else 0
                            if (w > 0 and w < min_width) or (h > 0 and h < min_height):
                                continue
                        except ValueError:
                            pass

                        # SVG 스킵
                        if '.svg' in img_url.lower():
                            continue

                        images.append({
                            'url': img_url,
                            'alt': img.get('alt', ''),
                            'width': width,
                            'height': height
                        })

                    # og:image 메타 태그도 체크
                    og_image = soup.find('meta', property='og:image')
                    if og_image and og_image.get('content'):
                        og_url = urljoin(url, og_image['content'])
                        if not any(i['url'] == og_url for i in images):
                            images.insert(0, {
                                'url': og_url,
                                'alt': 'Open Graph Image',
                                'width': '',
                                'height': ''
                            })

        except asyncio.TimeoutError:
            logger.warning(f"Timeout while scraping {url}")
        except Exception as e:
            logger.warning(f"Error scraping images from {url}: {e}")

        return images[:max_images]

    async def download_web_image(self, image_url: str, plan_id: str, slide_number: int) -> Optional[str]:
        """
        웹에서 이미지를 다운로드하여 저장합니다.

        Args:
            image_url: 이미지 URL
            plan_id: 기획안 ID
            slide_number: 슬라이드 번호

        Returns:
            저장된 이미지 경로 또는 None
        """
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'image/*,*/*;q=0.8'
        }

        try:
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=30)) as session:
                async with session.get(image_url, headers=headers, ssl=False) as response:
                    if response.status != 200:
                        logger.warning(f"Failed to download image {image_url}: status {response.status}")
                        return None

                    content_type = response.headers.get('content-type', '')
                    if not content_type.startswith('image/'):
                        logger.warning(f"Not an image: {content_type}")
                        return None

                    image_data = await response.read()

                    # 이미지 검증 및 처리
                    img = Image.open(io.BytesIO(image_data))

                    # 너무 작은 이미지 필터링
                    if img.width < 200 or img.height < 200:
                        logger.warning(f"Image too small: {img.width}x{img.height}")
                        return None

                    # PNG로 저장
                    filename = f"{plan_id}_web_{slide_number:02d}.png"
                    filepath = os.path.join(self.web_images_dir, filename)

                    # RGB로 변환 (RGBA, P 등 처리)
                    if img.mode in ('RGBA', 'P', 'LA'):
                        background = Image.new('RGB', img.size, (255, 255, 255))
                        if img.mode == 'P':
                            img = img.convert('RGBA')
                        background.paste(img, mask=img.split()[-1] if img.mode == 'RGBA' else None)
                        img = background
                    elif img.mode != 'RGB':
                        img = img.convert('RGB')

                    img.save(filepath, 'PNG', quality=95)
                    logger.info(f"Downloaded web image: {filepath}")

                    return filepath

        except asyncio.TimeoutError:
            logger.warning(f"Timeout downloading image {image_url}")
        except Exception as e:
            logger.warning(f"Error downloading image {image_url}: {e}")

        return None

    async def search_and_download_images_for_slide(
        self,
        search_query: str,
        plan_id: str,
        slide_number: int,
        max_attempts: int = 3
    ) -> Optional[str]:
        """
        Google Search로 찾은 URL에서 관련 이미지를 검색하고 다운로드합니다.

        Args:
            search_query: 검색 쿼리 (슬라이드 관련 키워드)
            plan_id: 기획안 ID
            slide_number: 슬라이드 번호
            max_attempts: 최대 시도 횟수

        Returns:
            다운로드된 이미지 경로 또는 None
        """
        if not self.client:
            return None

        try:
            # Google Search로 관련 웹페이지 찾기
            tools = [types.Tool(google_search=types.GoogleSearch())]

            search_prompt = f"""Find high-quality images related to: {search_query}

Search for web pages that might contain relevant images (news articles, official websites, etc.).
Return ONLY the top 3 most relevant URLs, one per line, no other text."""

            response = await self.async_client.models.generate_content(
                model=self.research_model,
                contents=search_prompt,
                config=types.GenerateContentConfig(
                    tools=tools,
                    temperature=0.1,
                    max_output_tokens=500
                )
            )

            response_text = response.text.strip()

            # URL 추출
            url_pattern = r'https?://[^\s<>"{}|\\^`\[\]]+'
            urls = re.findall(url_pattern, response_text)

            # 이미지 검색 및 다운로드 시도
            for url in urls[:max_attempts]:
                try:
                    # URL에서 이미지 스크래핑
                    images = await self.scrape_images_from_url(url, max_images=3)

                    for img_info in images:
                        downloaded_path = await self.download_web_image(
                            img_info['url'],
                            plan_id,
                            slide_number
                        )
                        if downloaded_path:
                            logger.info(f"Successfully downloaded image for slide {slide_number} from {url}")
                            return downloaded_path

                except Exception as e:
                    logger.warning(f"Error processing URL {url}: {e}")
                    continue

        except Exception as e:
            logger.warning(f"Error in search_and_download_images: {e}")

        return None

    async def generate_content_plan(
        self,
        topic: str,
        category: str = 'educational',
        target_slides: int = 15,
        language: str = 'ko',
        additional_instructions: str = '',
        content_id: str = None
    ) -> Dict[str, Any]:
        """
        주제를 기반으로 슬라이드 콘텐츠 기획을 생성합니다.

        Args:
            topic: 콘텐츠 주제/기획 아이디어
            category: 카테고리 (educational, entertainment, tech, gaming 등)
            target_slides: 목표 슬라이드 수 (10-20)
            language: 출력 언어
            additional_instructions: 추가 지시사항
            content_id: 통합 콘텐츠 ID (파이프라인에서 전달, None이면 자동 생성)

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

        # Google Search 도구 설정
        tools = [types.Tool(google_search=types.GoogleSearch())]

        # 언어별 프롬프트 완전 분리
        if language == 'en':
            prompt = f"""You are a YouTube video content planning expert and professional editorial writer.
Create a **high-quality content plan** with {target_slides} slides based on the following topic.

**CRITICAL: ALL content MUST be written in ENGLISH. This includes title, description, all slide titles, content, narrations, hook, call_to_action, and tags. Do NOT use any Korean or other languages.**

**VERY IMPORTANT - FOLLOW USER'S SLIDE STRUCTURE:**
If the user has provided a detailed slide scenario/structure in the topic (e.g., "슬라이드 1:", "Slide 1:", numbered list), you MUST:
1. Follow the EXACT slide structure, titles, and content themes provided
2. Use the user's slide titles as-is (translate to English if needed)
3. Expand the user's content descriptions into full narrations
4. Generate image_prompt based on each slide's specific content and theme
5. Do NOT create your own slide structure - strictly follow the user's outline

**Important:** If the topic requires real-time information or latest news, you MUST use the provided Google Search tool to search for and include the latest information. Include trends and news from 2024 onwards.

## Topic/Idea:
{topic}

## Category: {category}
## Style Guide: {style_guide}

{f"## Additional Instructions: {additional_instructions}" if additional_instructions else ""}

## Narration Quality Standard (MUST follow):
Each slide's narration must be written at a **professional editorial level**:
- **2+ paragraphs**, minimum 300 characters (30-45 seconds per slide)
- **Paragraph 1**: Core concept explanation + background knowledge, historical context, or scientific principles with in-depth analysis
- **Paragraph 2**: Practical applications, expert tips, or actionable insights the viewer can immediately use
- NOT a simple list — write as a **narrative with logical flow** and **professional analysis**

### Narration Quality Example:
❌ Bad: "Tomato spaghetti is a popular dish. Let's learn how to make it."
✅ Good: "Tomato spaghetti transcends its role as a simple carbohydrate dish — it is a cultural icon that originated in southern Naples, Italy, and has become a standard in kitchens worldwide. The modern home cooking trend pursues what might be called 'professional amateurism,' aiming to transplant restaurant-level precision into the domestic kitchen. This guide presents the most efficient yet gastronomically valuable tomato spaghetti recipe achievable at home."

## Image Prompt Quality Standard (MUST follow):
image_prompt must be written at a **professional photography direction** level:
- **Composition**: wide shot, close-up, flat-lay, macro, etc.
- **Lighting**: golden hour, studio lighting, dramatic side light, etc.
- **Camera**: camera model, lens type, aperture (e.g., Phase One XF, 80mm, f/2.8)
- **Mood/Color**: warm tones, moody atmosphere, vibrant colors, etc.
- **Resolution**: 8k resolution, photorealistic, hyper-realistic texture
- **3+ sentences** of detailed visual description

### Image Prompt Quality Example:
❌ Bad: "A plate of tomato spaghetti on a table"
✅ Good: "A wide, cinematic shot of a warm, sunlit rustic Italian kitchen. In the foreground, a beautifully plated tomato spaghetti with a glossy sauce and a fresh basil leaf sits on a dark, textured stone table. Soft steam is rising from the plate. The lighting is natural golden hour window light, creating long, soft shadows. Captured with a Phase One XF camera, 80mm lens, f/2.8, hyper-realistic texture, 8k resolution."

## Output Format (Must output in JSON format):
```json
{{
  "title": "Video title (attractive and click-inducing)",
  "description": "Video description (2-3 sentences)",
  "category": "{category}",
  "target_audience": "Target audience",
  "estimated_duration": "Estimated video length (minutes)",
  "slides": [
    {{
      "slide_number": 1,
      "title": "Slide title (subtitle: specific title with core keyword)",
      "content": "ONE SHORT sentence (max 15 words) - key message displayed at bottom of slide",
      "narration": "Professional editorial-level narration script (for TTS, natural conversational tone, 2+ paragraphs, minimum 300 characters, 30-45 seconds). Include background knowledge, expert analysis, and practical insights.",
      "image_prompt": "Professional photography-level image prompt (English, 3+ sentences). Specify composition, lighting, camera/lens, mood, and resolution. If web_image_keyword is specified, MUST include instruction to prominently feature that element.",
      "web_image_keyword": "Specific image/element to search and MUST appear in the final image (e.g., 'Tesla Model 3 car', 'Elon Musk portrait', 'iPhone 16 product photo'). Leave empty string if not needed.",
      "web_image_query": "Web search query for real photos/images (English, specific search terms)",
      "use_web_image": true/false,
      "duration_seconds": estimated_display_time_seconds
    }},
    ...
  ],
  "hook": "Video opening hook (0-30 seconds, grab viewer attention)",
  "call_to_action": "Like/Subscribe/Comment prompt",
  "tags": ["relevant", "tag", "list"]
}}
```

## Guidelines:
1. Each slide's narration is a TTS script, so write in natural conversational English while maintaining **professional depth**
2. **CRITICAL: Each narration must be at least 300 characters, 2+ paragraphs (30-45 seconds). Total video should be 7-10+ minutes with substantial script content**
3. **CRITICAL: "content" field is displayed on screen - must be ONE SHORT sentence (max 15 words). Put all details in "narration" instead.**
4. **image_prompt must be at professional photography direction level** - MUST include composition, lighting, camera/lens, mood, and resolution. 3+ sentences.
5. First slide should be a strong intro, last slide should include CTA outro
6. Include teasers/previews in the middle to maintain viewer retention
7. **ALL content must be in English (only image_prompt, web_image_keyword, and web_image_query are always in English)**
8. Content should be based on the latest facts from search results
9. **web_image_keyword**: The SPECIFIC image element that MUST appear in the generated image. Examples: 'OpenAI logo', 'Samsung Galaxy S25 phone', 'Taylor Swift photo'. This image will be searched, downloaded, and Gemini will be instructed to prominently feature it in the generated slide.
10. web_image_query: The search query to find the web_image_keyword (e.g., "OpenAI logo high resolution", "Samsung Galaxy S25 official product photo")
11. use_web_image: Set to true if web_image_keyword is specified and a real image reference is needed
12. **Total narration should be at least 4000 characters (approximately 7-10 minutes)**
13. **Include a subtitle in the title field for a professional feel** (e.g., "The Red Temptation: Cultural Value and Legacy of Tomato Spaghetti")
"""
        else:
            prompt = f"""당신은 YouTube 영상 콘텐츠 기획 전문가이자 전문 에디토리얼 작가입니다.
다음 주제를 기반으로 {target_slides}개의 슬라이드로 구성된 **고품질 콘텐츠 기획안**을 작성해주세요.

**중요: 모든 콘텐츠는 반드시 한국어로 작성해야 합니다. title, description, 슬라이드의 title, content, narration, hook, call_to_action, tags 모두 한국어로 작성하세요.**

**매우 중요 - 사용자의 슬라이드 구성을 반드시 따르세요:**
사용자가 주제에 상세한 슬라이드 시나리오/구성을 제공한 경우 (예: "슬라이드 1:", "Slide 1:", 번호 목록 등):
1. 사용자가 제공한 슬라이드 구조, 제목, 내용 주제를 **정확히** 따르세요
2. 사용자의 슬라이드 제목을 그대로 사용하세요
3. 사용자가 작성한 내용 설명을 바탕으로 상세한 나레이션을 확장하세요
4. 각 슬라이드의 **구체적인 내용과 주제**에 맞는 image_prompt를 생성하세요
5. 사용자의 구성을 무시하고 새로운 구조를 만들지 마세요 - 사용자의 아웃라인을 엄격히 따르세요

**중요:** 실시간 정보나 최신 뉴스가 필요한 주제라면 반드시 제공된 구글 검색 도구(Google Search)를 사용하여 최신 정보를 검색하고 반영해주세요. 2024년 이후의 최신 트렌드나 뉴스를 적극적으로 포함해야 합니다.

## 주제/기획 아이디어:
{topic}

## 카테고리: {category}
## 스타일 가이드: {style_guide}

{f"## 추가 지시사항: {additional_instructions}" if additional_instructions else ""}

## 나레이션 품질 기준 (반드시 준수):
각 슬라이드의 narration은 **전문 에디토리얼 수준**으로 작성해야 합니다:
- **2문단 이상**, 최소 300자 이상 (30-45초 분량)
- **1문단**: 핵심 개념 설명 + 배경 지식/역사적 맥락/과학적 원리 등 깊이 있는 분석
- **2문단**: 실용적 적용 방법, 전문가 팁, 또는 시청자가 바로 활용할 수 있는 인사이트
- 단순 나열이 아닌, **논리적 흐름**과 **전문적 분석**이 포함된 서술형 대본

### 나레이션 품질 예시:
❌ 나쁜 예: "토마토 스파게티는 인기 있는 요리입니다. 만드는 방법을 알아보겠습니다."
✅ 좋은 예: "토마토 스파게티는 단순한 탄수화물 섭취를 위한 수단을 넘어, 이탈리아 남부 나폴리에서 시작되어 전 세계 주방의 표준이 된 문화적 아이콘입니다. 현대의 홈 쿠킹 트렌드는 레스토랑 수준의 정교한 기술을 가정 내 조리 환경에 이식하려는 '전문가적 아마추어리즘'을 지향합니다. 본 기획안은 집에서 수행할 수 있는 가장 효율적이면서도 미식적 가치가 높은 레시피를 제안하고자 합니다."

## 이미지 프롬프트 품질 기준 (반드시 준수):
image_prompt는 **프로페셔널 포토그래피 디렉션** 수준으로 작성해야 합니다:
- **구도**: wide shot, close-up, flat-lay, macro 등 구체적 촬영 구도
- **조명**: golden hour, studio lighting, dramatic side light 등 조명 지시
- **카메라**: 카메라 모델, 렌즈 종류, 조리개 값 (예: Phase One XF, 80mm, f/2.8)
- **분위기/색감**: warm tones, moody atmosphere, vibrant colors 등
- **해상도**: 8k resolution, photorealistic, hyper-realistic texture
- **3문장 이상**의 상세한 시각적 묘사

### 이미지 프롬프트 품질 예시:
❌ 나쁜 예: "A plate of tomato spaghetti on a table"
✅ 좋은 예: "A wide, cinematic shot of a warm, sunlit rustic Italian kitchen. In the foreground, a beautifully plated tomato spaghetti with a glossy sauce and a fresh basil leaf sits on a dark, textured stone table. Soft steam is rising from the plate. The lighting is natural golden hour window light, creating long, soft shadows. Captured with a Phase One XF camera, 80mm lens, f/2.8, hyper-realistic texture, 8k resolution."

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
      "title": "슬라이드 제목 (부제: 핵심 키워드를 포함한 구체적 제목)",
      "content": "화면 하단에 표시될 핵심 메시지 한 문장 (최대 15단어)",
      "narration": "전문 에디토리얼 수준의 나레이션 대본 (TTS용, 자연스러운 구어체, 2문단 이상, 최소 300자 이상, 30-45초 분량). 배경 지식, 전문적 분석, 실용적 인사이트를 포함하여 깊이 있게 작성.",
      "image_prompt": "프로페셔널 포토그래피 수준의 이미지 프롬프트 (영어, 3문장 이상). 구도/조명/카메라/렌즈/분위기/해상도를 구체적으로 지시. web_image_keyword가 지정된 경우 해당 요소를 반드시 눈에 띄게 포함.",
      "web_image_keyword": "검색하여 최종 이미지에 반드시 나타나야 할 구체적인 이미지/요소 (예: 'Tesla Model 3 car', 'Elon Musk portrait'). 필요 없으면 빈 문자열.",
      "web_image_query": "이 슬라이드에 사용할 실제 사진/이미지를 웹에서 검색할 쿼리 (영어, 구체적인 검색어)",
      "use_web_image": true/false,
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
1. 각 슬라이드의 narration은 TTS로 읽을 대본이므로 자연스러운 구어체로 작성하되, **전문적 깊이**를 유지
2. **핵심: 각 narration은 반드시 300자 이상, 2문단 이상으로 작성 (30-45초 분량). 전체 영상이 7-10분 이상이 되도록 충분한 분량의 대본 작성 필수**
3. **핵심: "content" 필드는 화면에 표시됩니다 - 반드시 한 문장(최대 15단어)으로 작성. 상세 내용은 모두 "narration"에 작성하세요.**
4. **image_prompt는 프로페셔널 포토그래피 디렉션 수준으로 작성** - 구도, 조명, 카메라/렌즈, 분위기, 해상도를 반드시 포함. 3문장 이상.
5. 첫 슬라이드는 강력한 인트로, 마지막은 CTA 포함 아웃트로
6. 중간에 시청 유지를 위한 티저/예고 포함
7. **반드시 한국어로 title, description, content, narration, hook, call_to_action, tags 작성 (image_prompt, web_image_keyword, web_image_query만 영어)**
8. 검색된 정보의 출처나 시점을 명확히 알 필요는 없지만, 내용은 최신 사실에 기반해야 함
9. **web_image_keyword**: 생성된 이미지에 **반드시 나타나야 할** 구체적인 이미지 요소. 예: 'OpenAI logo', 'Samsung Galaxy S25 phone', 'Taylor Swift photo'. 이 이미지는 웹에서 검색/다운로드되어 Gemini가 생성하는 슬라이드에 눈에 띄게 포함됩니다.
10. web_image_query: web_image_keyword를 찾기 위한 검색 쿼리 (예: "OpenAI logo high resolution", "Samsung Galaxy S25 official product photo")
11. use_web_image: web_image_keyword가 지정되어 실제 이미지 참조가 필요한 경우 true로 설정
12. **전체 narration 합계가 최소 4000자 이상이 되도록 작성 (약 7-10분 분량)**
13. **title 필드에 부제를 포함하여 구체적이고 전문적인 느낌을 부여** (예: "인류의 미각을 사로잡은 붉은 유혹: 토마토 스파게티의 문화적 가치")
"""

        try:
            # 비동기 클라이언트 사용하여 이벤트 루프 차단 방지
            # 주의: Google Search 도구와 response_mime_type="application/json"은 동시 사용 불가
            # Search 도구 사용 시 JSON 모드를 비활성화하고 수동으로 JSON 추출
            response = await self.async_client.models.generate_content(
                model=self.research_model,
                contents=prompt,
                config=types.GenerateContentConfig(
                    tools=tools,  # 구글 검색 도구 추가
                    temperature=0.2,
                    max_output_tokens=16384
                    # response_mime_type 제거 - Search 도구와 호환 불가
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

            # 기획안 저장 (content_id가 있으면 사용, 없으면 기존 방식)
            if content_id:
                plan_id = content_id
            else:
                plan_id = uuid.uuid4().hex[:8]
            plan_filename = f"plan_{plan_id}.json"
            plan_path = os.path.join(self.output_dir, plan_filename)

            content_plan['plan_id'] = plan_id
            content_plan['content_id'] = plan_id  # 통합 ID로도 저장
            content_plan['created_at'] = datetime.now().isoformat()
            content_plan['language'] = language
            content_plan['category'] = category  # 사용자가 선택한 카테고리로 강제 설정

            with open(plan_path, 'w', encoding='utf-8') as f:
                json.dump(content_plan, f, ensure_ascii=False, indent=2)

            logger.info(f"Content plan saved: {plan_path}")

            return {
                'status': 'success',
                'plan_id': plan_id,
                'content_id': plan_id,  # 통합 ID 반환
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
        language: str = 'ko',
        reference_images: List[str] = None,
        web_image_keyword: str = ''
    ) -> Dict[str, Any]:
        """
        슬라이드용 이미지를 생성합니다.
        Nano Banana Pro (Gemini 3) 모델을 사용하여 고품질 배경 이미지를 생성하고,
        Python PIL을 사용하여 텍스트를 합성합니다 (한글 렌더링 품질 확보).

        Args:
            image_prompt: 이미지 생성 프롬프트
            slide_number: 슬라이드 번호
            plan_id: 기획안 ID
            style: 이미지 스타일
            title: 슬라이드 제목
            narration: 대본 텍스트
            content: 슬라이드 콘텐츠 (핵심 내용)
            language: 텍스트 언어 (ko/en)
            web_image_keyword: 반드시 이미지에 포함되어야 할 웹 이미지 키워드
            reference_images: 참조 이미지 파일 경로 리스트 (웹에서 다운로드한 이미지)

        Returns:
            Dict containing image path
        """
        if not self.client:
            raise ValueError("Gemini client not initialized.")

        # 참조 이미지가 있는 경우 프롬프트 수정
        has_reference = reference_images and len(reference_images) > 0

        if has_reference:
            # web_image_keyword가 있으면 해당 요소를 반드시 포함하도록 강조
            keyword_instruction = ""
            if web_image_keyword:
                keyword_instruction = f"""
## CRITICAL - MUST INCLUDE THIS ELEMENT:
The reference image shows "{web_image_keyword}". You MUST prominently feature this element in the generated image.
- The "{web_image_keyword}" from the reference image should be clearly visible and recognizable
- Place it in a visually prominent position (center or key focal point)
- Maintain the authentic appearance of the "{web_image_keyword}" as shown in the reference
"""

            enhanced_prompt = f"""Based on the reference images provided, create a high-quality presentation slide background image.
{keyword_instruction}
## Visual Description:
{image_prompt}

## Reference Images Integration:
- The reference image contains "{web_image_keyword or 'visual elements'}" that MUST appear in the final image
- Incorporate the key subject from the reference image prominently, not just as inspiration
- The reference subject should be clearly recognizable in the generated image

## Style Requirements:
- Style: {style}, 16:9 aspect ratio (1920x1080)
- Minimalist, clean, and professional background
- Composition should allow space for text overlay (top and bottom)
- High aesthetic quality, detailed textures, cinematic lighting
- Feature the reference image subject prominently while maintaining slide aesthetics

## IMPORTANT:
- DO NOT include any text, words, letters, or numbers in the image.
- This image will be used as a background, so keep areas for text overlay clean.
- The key subject from the reference MUST be visible and recognizable.
"""
        else:
            enhanced_prompt = f"""Generate a high-quality background image for a presentation slide.

## Visual Description:
{image_prompt}

## Style Requirements:
- Style: {style}, 16:9 aspect ratio (1920x1080)
- Minimalist, clean, and professional
- Vibrant and engaging colors
- Composition should allow space for text overlay (top and bottom)
- High aesthetic quality, detailed textures, cinematic lighting

## IMPORTANT:
- DO NOT include any text, words, letters, or numbers in the image.
- This image will be used as a background, so keep the central area relatively clean or balanced.
- Pure visual representation of the concept.
"""

        logger.info(f"Generating image for slide {slide_number}: {title[:30] if title else image_prompt[:30]}... (refs: {len(reference_images) if reference_images else 0})")

        try:
            # contents 구성: 참조 이미지가 있으면 이미지와 텍스트 함께 전송
            if has_reference:
                contents = []
                # 참조 이미지 추가 (최대 3개)
                for ref_path in reference_images[:3]:
                    try:
                        if os.path.exists(ref_path):
                            with open(ref_path, 'rb') as f:
                                img_bytes = f.read()
                            # 이미지 파트 추가
                            contents.append(types.Part.from_bytes(
                                data=img_bytes,
                                mime_type='image/png'
                            ))
                            logger.info(f"Added reference image: {ref_path}")
                    except Exception as e:
                        logger.warning(f"Failed to load reference image {ref_path}: {e}")

                # 프롬프트 텍스트 추가
                contents.append(enhanced_prompt)
            else:
                contents = enhanced_prompt

            # Gemini 사용 (비동기 클라이언트)
            # 모델ID: gemini-3-pro-image-preview
            response = await self.async_client.models.generate_content(
                model=self.image_model,
                contents=contents,
                config=types.GenerateContentConfig(
                    response_modalities=['IMAGE']
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

            # 이미지 처리
            image_filename = f"{plan_id}_slide_{slide_number:02d}.png"
            image_path = os.path.join(self.output_dir, image_filename)

            # PIL로 이미지 로드
            img = Image.open(io.BytesIO(image_data))
            img = img.convert('RGB')

            # 16:9 비율로 리사이즈 (1920x1080)
            target_width, target_height = 1920, 1080
            img = img.resize((target_width, target_height), Image.Resampling.LANCZOS)
            
            # 텍스트 오버레이 합성 (한글 렌더링 해결)
            img = self._add_text_overlay(img, slide_number, title, content)

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
        progress_callback=None,
        use_web_images: bool = True
    ) -> Dict[str, Any]:
        """
        기획안의 모든 슬라이드 이미지를 생성합니다.
        웹 이미지 다운로드를 우선 시도하고, 실패 시 AI 생성 이미지를 사용합니다.

        Args:
            plan_id: 기획안 ID
            progress_callback: 진행 상황 콜백 함수
            use_web_images: 웹 이미지 다운로드 사용 여부

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
        web_image_count = 0

        for i, slide in enumerate(slides):
            slide_number = slide.get('slide_number', i + 1)
            title = slide.get('title', '')
            content = slide.get('content', '')

            if progress_callback:
                progress_callback(i + 1, total_slides, f"Processing image {i + 1}/{total_slides}")

            reference_images = []

            # 웹 이미지 다운로드 시도 (use_web_image가 true인 슬라이드)
            if use_web_images and slide.get('use_web_image', False):
                web_query = slide.get('web_image_query', '')
                if web_query:
                    logger.info(f"Searching web images for slide {slide_number}: {web_query[:50]}")

                    if progress_callback:
                        progress_callback(i + 1, total_slides, f"Searching web image {i + 1}/{total_slides}")

                    # 웹 이미지 다운로드 (참조용으로 사용)
                    web_image_path = await self.search_and_download_images_for_slide(
                        search_query=web_query,
                        plan_id=plan_id,
                        slide_number=slide_number
                    )

                    if web_image_path:
                        reference_images.append(web_image_path)
                        web_image_count += 1
                        logger.info(f"Web image downloaded for slide {slide_number} as reference")

            # AI 이미지 생성 (웹 이미지가 있으면 참조로 사용)
            if progress_callback:
                if reference_images:
                    progress_callback(i + 1, total_slides, f"Generating AI image with reference {i + 1}/{total_slides}")
                else:
                    progress_callback(i + 1, total_slides, f"Generating AI image {i + 1}/{total_slides}")

            result = await self.generate_slide_image(
                image_prompt=slide.get('image_prompt', ''),
                slide_number=slide_number,
                plan_id=plan_id,
                title=title,
                narration=slide.get('narration', ''),
                content=content,
                language=language,
                reference_images=reference_images if reference_images else None,
                web_image_keyword=slide.get('web_image_keyword', '')
            )
            result['source'] = 'ai_with_ref' if reference_images else 'ai'
            result['reference_count'] = len(reference_images)

            results.append(result)

            # API 레이트 리밋 방지
            if i < total_slides - 1:
                await asyncio.sleep(2)

        # 성공한 이미지 수 계산
        success_count = sum(1 for r in results if r['status'] == 'success')
        with_ref_count = sum(1 for r in results if r.get('reference_count', 0) > 0 and r['status'] == 'success')

        return {
            'status': 'success' if success_count == total_slides else 'partial',
            'plan_id': plan_id,
            'total': total_slides,
            'success': success_count,
            'web_references_used': web_image_count,
            'ai_with_reference': with_ref_count,
            'ai_only': success_count - with_ref_count,
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

        # PDF 생성 (content_id 기반 파일명 사용)
        # plan_id가 content_id 형식이면 그대로 사용, 아니면 기존 방식
        if plan_id.startswith('pipe_') or '_' in plan_id and len(plan_id) > 16:
            # 통합 ID 형식: {content_id}.pdf
            pdf_filename = f"{plan_id}.pdf"
        else:
            # 기존 형식: {safe_title}_{plan_id}.pdf
            safe_title = "".join(c for c in pdf_title if c.isalnum() or c in (' ', '-', '_')).strip()[:50]
            pdf_filename = f"{safe_title}_{plan_id}.pdf"
        pdf_path = os.path.join(self.pdf_dir, pdf_filename)

        # 16:9 비율의 PDF 페이지 크기 (1920x1080 픽셀 기준)
        page_width = 1920 * 0.75  # 포인트로 변환 (약 1440pt)
        page_height = 1080 * 0.75  # 약 810pt

        # 나레이션 텍스트 수집 (슬라이드 번호 순서대로)
        narrations = []
        for slide_num, _ in image_files:
            slide_data = next((s for s in slides if s.get('slide_number') == slide_num), None)
            narrations.append(slide_data.get('narration', '') if slide_data else '')

        # 임시 PDF 파일 경로
        temp_pdf_path = pdf_path + '.temp'

        c = canvas.Canvas(temp_pdf_path, pagesize=(page_width, page_height))

        for slide_num, image_path in image_files:
            img = Image.open(image_path)
            img_reader = ImageReader(img)
            c.drawImage(img_reader, 0, 0, width=page_width, height=page_height)
            c.showPage()

        c.save()

        # PyPDF2로 PDF에 나레이션 메타데이터 임베드
        reader = PdfReader(temp_pdf_path)
        writer = PdfWriter()

        # 모든 페이지 복사
        for page in reader.pages:
            writer.add_page(page)

        # 나레이션을 JSON으로 직렬화하여 메타데이터에 저장
        narrations_json = json.dumps(narrations, ensure_ascii=False)
        writer.add_metadata({
            '/Title': pdf_title,
            '/Author': 'Auto-Poster',
            '/Subject': plan.get('category', 'educational'),
            '/Keywords': plan.get('language', 'ko'),
            '/Creator': 'Auto-Poster Content Generator',
            '/Narrations': narrations_json,  # 커스텀 메타데이터: 슬라이드별 나레이션
            '/ContentId': plan_id,
            '/SlideCount': str(len(image_files))
        })

        # 최종 PDF 저장
        with open(pdf_path, 'wb') as f:
            writer.write(f)

        # 임시 파일 삭제
        os.remove(temp_pdf_path)

        # 메타데이터 JSON도 저장 (하위 호환성)
        meta_path = pdf_path.rsplit('.', 1)[0] + '.json'
        meta_data = {
            'plan_id': plan_id,
            'content_id': plan_id,  # 통합 ID
            'title': pdf_title,
            'filename': pdf_filename,
            'slide_count': len(image_files),
            'created_at': datetime.now().isoformat(),
            'language': plan.get('language', 'ko'),
            'category': plan.get('category', 'educational'),
            'narrations': narrations
        }
        with open(meta_path, 'w', encoding='utf-8') as f:
            json.dump(meta_data, f, ensure_ascii=False, indent=2)

        logger.info(f"PDF created: {pdf_path}")

        return {
            'status': 'success',
            'pdf_path': pdf_path,
            'filename': pdf_filename,
            'slide_count': len(image_files),
            'plan_id': plan_id,
            'content_id': plan_id  # 통합 ID 반환
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

    def delete_plan(self, plan_id: str, force: bool = False) -> dict:
        """기획안과 관련 파일들을 삭제합니다.

        Args:
            plan_id: 삭제할 기획안 ID
            force: True면 사용 중이어도 강제 삭제

        Returns:
            dict: {'success': bool, 'message': str, 'deleted_files': list}
        """
        deleted_files = []
        errors = []

        # 실행 중인 파이프라인에서 사용 중인지 확인
        if not force:
            from .auto_pipeline_service import auto_pipeline
            for pipeline in auto_pipeline.pipelines.values():
                if pipeline.get('status') in ['starting', 'running']:
                    result = pipeline.get('result', {})
                    if result.get('plan_id') == plan_id or pipeline.get('id') == plan_id:
                        return {
                            'success': False,
                            'message': f'기획안이 실행 중인 파이프라인 ({pipeline.get("id")})에서 사용 중입니다.',
                            'deleted_files': []
                        }

        # 기획안 JSON 삭제
        plan_path = os.path.join(self.output_dir, f"plan_{plan_id}.json")
        if os.path.exists(plan_path):
            try:
                os.remove(plan_path)
                deleted_files.append(plan_path)
            except Exception as e:
                errors.append(f"기획안 파일 삭제 실패: {e}")

        # 관련 이미지 삭제
        if os.path.exists(self.output_dir):
            try:
                for filename in os.listdir(self.output_dir):
                    if filename.startswith(f"{plan_id}_slide_"):
                        filepath = os.path.join(self.output_dir, filename)
                        try:
                            os.remove(filepath)
                            deleted_files.append(filepath)
                        except Exception as e:
                            errors.append(f"이미지 삭제 실패 ({filename}): {e}")
            except Exception as e:
                errors.append(f"디렉토리 읽기 실패: {e}")

        # 웹 이미지 삭제
        web_images_dir = os.path.join(self.output_dir, 'web_images')
        if os.path.exists(web_images_dir):
            try:
                for filename in os.listdir(web_images_dir):
                    if filename.startswith(f"{plan_id}_web_"):
                        filepath = os.path.join(web_images_dir, filename)
                        try:
                            os.remove(filepath)
                            deleted_files.append(filepath)
                        except Exception as e:
                            errors.append(f"웹 이미지 삭제 실패 ({filename}): {e}")
            except Exception as e:
                errors.append(f"웹 이미지 디렉토리 읽기 실패: {e}")

        if errors:
            return {
                'success': len(deleted_files) > 0,
                'message': f'일부 파일 삭제 실패: {"; ".join(errors)}',
                'deleted_files': deleted_files
            }

        return {
            'success': len(deleted_files) > 0,
            'message': f'{len(deleted_files)}개 파일 삭제됨' if deleted_files else '삭제할 파일 없음',
            'deleted_files': deleted_files
        }

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


    def _split_title_subtitle(self, title: str):
        """제목에서 메인 타이틀과 부제를 분리합니다.
        형식: '메인 제목 : 부제' 또는 '메인 제목: 부제'
        """
        import re
        # ' : ' 또는 ': ' 패턴으로 분리 (첫 번째 콜론 기준)
        match = re.split(r'\s*:\s*', title, maxsplit=1)
        if len(match) == 2 and len(match[1].strip()) > 0:
            return match[0].strip(), match[1].strip()
        return title.strip(), None

    def _add_text_overlay(self, img: Image.Image, slide_number: int, title: str, content: str) -> Image.Image:
        """이미지 위에 텍스트(제목, 부제, 내용, 번호)를 합성합니다."""
        draw = ImageDraw.Draw(img)
        width, height = img.size

        # 폰트 로드 (설치된 NotoSansCJK 사용)
        try:
            # 폰트 크기 설정 (1920x1080 기준)
            title_font_size = 60
            subtitle_font_size = 32
            content_font_size = 40
            badge_font_size = 30

            font_bold = ImageFont.truetype("/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc", title_font_size)
            font_subtitle = ImageFont.truetype("/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc", subtitle_font_size)
            font_regular = ImageFont.truetype("/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc", content_font_size)
            font_badge = ImageFont.truetype("/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc", badge_font_size)
        except OSError:
            logger.warning("Korean font not found, using default. Text might not render correctly.")
            font_bold = ImageFont.load_default()
            font_subtitle = ImageFont.load_default()
            font_regular = ImageFont.load_default()
            font_badge = ImageFont.load_default()

        # 제목/부제 분리
        main_title, subtitle = self._split_title_subtitle(title)

        # 1. 슬라이드 번호 배지 (좌측 상단)
        badge_text = f"#{slide_number}"
        badge_padding = 15
        bbox = draw.textbbox((0, 0), badge_text, font=font_badge)
        badge_w = bbox[2] - bbox[0] + badge_padding * 2
        badge_h = bbox[3] - bbox[1] + badge_padding * 2

        # 배지 배경 (반투명 검정)
        overlay = Image.new('RGBA', img.size, (0, 0, 0, 0))
        draw_overlay = ImageDraw.Draw(overlay)

        draw_overlay.rounded_rectangle(
            [(20, 20), (20 + badge_w, 20 + badge_h)],
            radius=10, fill=(0, 0, 0, 160)
        )

        # 2. 제목 영역 (상단) - 메인 타이틀 + 부제
        wrapped_title = textwrap.fill(main_title, width=30)

        # 제목 높이 계산
        title_bbox = draw.multiline_textbbox((0, 0), wrapped_title, font=font_bold, spacing=10)
        title_h = title_bbox[3] - title_bbox[1] + 60

        # 부제 높이 계산
        subtitle_h = 0
        wrapped_subtitle = None
        if subtitle:
            wrapped_subtitle = textwrap.fill(subtitle, width=45)
            sub_bbox = draw.multiline_textbbox((0, 0), wrapped_subtitle, font=font_subtitle, spacing=6)
            subtitle_h = sub_bbox[3] - sub_bbox[1] + 30

        # 상단 오버레이 (부제 공간 포함)
        draw_overlay.rectangle(
            [(0, 0), (width, 150 + title_h + subtitle_h)],
            fill=(0, 0, 0, 100)
        )

        # 3. 내용 영역 (하단) - 한 문장만 표시
        if content:
            if isinstance(content, list):
                content_text = content[0] if content else ""
            else:
                content_text = content

            content_text = content_text.strip()
            if len(content_text) > 80:
                content_text = content_text[:77] + "..."

            wrapped_content = content_text

            content_bbox = draw.textbbox((0, 0), wrapped_content, font=font_regular)
            content_h = content_bbox[3] - content_bbox[1] + 40

            draw_overlay.rectangle(
                [(0, height - content_h - 30), (width, height)],
                fill=(0, 0, 0, 160)
            )

        # 오버레이 합성
        img = Image.alpha_composite(img.convert('RGBA'), overlay)
        draw = ImageDraw.Draw(img)

        # 텍스트 그리기

        # 배지 텍스트
        draw.text((20 + badge_padding, 20 + badge_padding), badge_text, font=font_badge, fill="white", anchor="lt")

        # 메인 제목 (흰색, 60pt)
        title_y = 100
        draw.multiline_text(
            (width/2, title_y),
            wrapped_title,
            font=font_bold,
            fill="white",
            anchor="ma",
            align="center",
            spacing=10
        )

        # 부제 (밝은 노란색, 32pt, 메인 제목 아래)
        if subtitle and wrapped_subtitle:
            # 메인 제목의 실제 렌더링 높이 계산
            title_rendered_bbox = draw.multiline_textbbox((width/2, title_y), wrapped_title, font=font_bold, spacing=10, anchor="ma")
            subtitle_y = title_rendered_bbox[3] + 20  # 제목 아래 20px 여백

            draw.multiline_text(
                (width/2, subtitle_y),
                wrapped_subtitle,
                font=font_subtitle,
                fill=(255, 255, 102),  # 밝은 노란색
                anchor="ma",
                align="center",
                spacing=6
            )

        # 내용 텍스트 (하단 중앙)
        if content:
            draw.text(
                (width/2, height - 50),
                wrapped_content,
                font=font_regular,
                fill="white",
                anchor="mm"
            )

        return img.convert('RGB')


# 싱글톤 인스턴스
content_generator = ContentGeneratorService()
