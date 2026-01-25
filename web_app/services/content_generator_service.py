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

        prompt = f"""당신은 YouTube 영상 콘텐츠 기획 전문가입니다.
다음 주제를 기반으로 {target_slides}개의 슬라이드로 구성된 콘텐츠 기획안을 작성해주세요.

**중요:** 실시간 정보나 최신 뉴스가 필요한 주제라면 반드시 제공된 구글 검색 도구(Google Search)를 사용하여 최신 정보를 검색하고 반영해주세요. 2024년 이후의 최신 트렌드나 뉴스를 적극적으로 포함해야 합니다.

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
      "content": "슬라이드에서 다룰 내용 (2-3문장). 최신 검색 정보를 바탕으로 구체적인 수치나 사례를 포함.",
      "narration": "이 슬라이드에서 읽을 나레이션 대본 (TTS용, 자연스러운 구어체, 최소 150자 이상, 20-30초 분량)",
      "image_prompt": "이 슬라이드용 이미지 생성 프롬프트 (영어, 구체적이고 시각적인 설명)",
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
1. 각 슬라이드의 narration은 TTS로 읽을 대본이므로 자연스러운 구어체로 작성
2. **중요: 각 narration은 반드시 150자 이상으로 작성 (20-30초 분량). 전체 영상이 5-7분 이상이 되도록 충분한 분량의 대본 작성 필수**
3. image_prompt는 반드시 영어로, AI 이미지 생성에 적합한 구체적인 설명
4. 첫 슬라이드는 강력한 인트로, 마지막은 CTA 포함 아웃트로
5. 중간에 시청 유지를 위한 티저/예고 포함
6. {'한국어' if language == 'ko' else 'English'}로 title, content, narration 작성
7. 검색된 정보의 출처나 시점을 명확히 알 필요는 없지만, 내용은 최신 사실에 기반해야 함
8. web_image_query: 실제 사진이 필요한 슬라이드에 대해 웹 검색 쿼리를 작성 (예: 제품 사진, 유명인, 장소, 이벤트 등)
9. use_web_image: 해당 슬라이드에 AI 생성 이미지 대신 웹에서 다운로드한 실제 이미지를 사용할지 여부 (실제 사진이 더 적합한 경우 true)
10. **전체 narration 합계가 최소 2500자 이상이 되도록 작성 (약 5분 분량)**
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
                    max_output_tokens=8192
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
        reference_images: List[str] = None
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
            reference_images: 참조 이미지 파일 경로 리스트 (웹에서 다운로드한 이미지)

        Returns:
            Dict containing image path
        """
        if not self.client:
            raise ValueError("Gemini client not initialized.")

        # 참조 이미지가 있는 경우 프롬프트 수정
        has_reference = reference_images and len(reference_images) > 0

        if has_reference:
            enhanced_prompt = f"""Based on the reference images provided, create a high-quality presentation slide background image.

## Visual Description:
{image_prompt}

## Reference Images:
Use the provided reference images as inspiration for style, color palette, and visual elements.
Incorporate relevant visual elements from the references while creating a cohesive slide background.

## Style Requirements:
- Style: {style}, 16:9 aspect ratio (1920x1080)
- Minimalist, clean, and professional
- Composition should allow space for text overlay (top and bottom)
- High aesthetic quality, detailed textures, cinematic lighting
- Blend the reference image aesthetics with the slide concept

## IMPORTANT:
- DO NOT include any text, words, letters, or numbers in the image.
- This image will be used as a background, so keep the central area relatively clean or balanced.
- Pure visual representation of the concept inspired by the references.
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
                reference_images=reference_images if reference_images else None
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
            'content_id': plan_id,  # 통합 ID
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


    def _add_text_overlay(self, img: Image.Image, slide_number: int, title: str, content: str) -> Image.Image:
        """이미지 위에 텍스트(제목, 내용, 번호)를 합성합니다."""
        draw = ImageDraw.Draw(img)
        width, height = img.size
        
        # 폰트 로드 (설치된 NotoSansCJK 사용)
        try:
            # 폰트 크기 설정 (1920x1080 기준)
            title_font_size = 60
            content_font_size = 40
            badge_font_size = 30
            
            font_bold = ImageFont.truetype("/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc", title_font_size)
            font_regular = ImageFont.truetype("/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc", content_font_size)
            font_badge = ImageFont.truetype("/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc", badge_font_size)
        except OSError:
            logger.warning("Korean font not found, using default. Text might not render correctly.")
            font_bold = ImageFont.load_default()
            font_regular = ImageFont.load_default()
            font_badge = ImageFont.load_default()

        # 1. 슬라이드 번호 배지 (좌측 상단)
        badge_text = f"#{slide_number}"
        badge_padding = 15
        bbox = draw.textbbox((0, 0), badge_text, font=font_badge)
        badge_w = bbox[2] - bbox[0] + badge_padding * 2
        badge_h = bbox[3] - bbox[1] + badge_padding * 2
        
        # 배지 배경 (반투명 검정)
        # PIL draw.rectangle은 투명도 지원 안함 -> 별도 레이어 필요
        overlay = Image.new('RGBA', img.size, (0, 0, 0, 0))
        draw_overlay = ImageDraw.Draw(overlay)
        
        draw_overlay.rounded_rectangle(
            [(20, 20), (20 + badge_w, 20 + badge_h)],
            radius=10, fill=(0, 0, 0, 160)
        )
        
        # 2. 제목 영역 (상단) - 그라데이션 대신 반투명 박스
        # 제목 줄바꿈
        wrapped_title = textwrap.fill(title, width=30) # 대략적인 글자수 제한
        
        # 제목 높이 계산
        title_bbox = draw.multiline_textbbox((0, 0), wrapped_title, font=font_bold, spacing=10)
        title_h = title_bbox[3] - title_bbox[1] + 60 # 여백 포함
        
        # 상단 오버레이
        draw_overlay.rectangle(
            [(0, 0), (width, 150 + title_h)], # 넉넉하게
            fill=(0, 0, 0, 100) # 전체 상단 어둡게
        )
        
        # 3. 내용 영역 (하단)
        if content:
            # 리스트인 경우 텍스트로 변환
            if isinstance(content, list):
                content_text = "\n".join([f"• {item}" for item in content])
            else:
                content_text = content
                
            wrapped_content = ""
            for line in content_text.split('\n'):
                wrapped_content += textwrap.fill(line, width=50) + "\n"
            
            # 하단 오버레이 (그라데이션 효과를 위해 여러 겹 또는 단순히 박스)
            # 여기서는 심플하게 하단 박스
            content_bbox = draw.multiline_textbbox((0, 0), wrapped_content, font=font_regular, spacing=15)
            content_h = content_bbox[3] - content_bbox[1] + 80
            
            draw_overlay.rectangle(
                [(0, height - content_h - 50), (width, height)],
                fill=(0, 0, 0, 140)
            )

        # 오버레이 합성
        img = Image.alpha_composite(img.convert('RGBA'), overlay)
        draw = ImageDraw.Draw(img) # 다시 draw 생성 (합성된 이미지용)

        # 텍스트 그리기 (흰색)
        
        # 배지 텍스트
        draw.text((20 + badge_padding, 20 + badge_padding), badge_text, font=font_badge, fill="white", anchor="lt")
        
        # 제목 텍스트 (중앙 정렬 또는 좌측 정렬)
        # 상단 영역 중앙
        draw.multiline_text(
            (width/2, 100), 
            wrapped_title, 
            font=font_bold, 
            fill="white", 
            anchor="ma", 
            align="center",
            spacing=10
        )
        
        # 내용 텍스트 (하단 중앙)
        if content:
            draw.multiline_text(
                (width/2, height - 100),
                wrapped_content,
                font=font_regular,
                fill="white",
                anchor="md", # middle-down (하단 기준)
                align="center",
                spacing=15
            )
            
        return img.convert('RGB')


# 싱글톤 인스턴스
content_generator = ContentGeneratorService()
