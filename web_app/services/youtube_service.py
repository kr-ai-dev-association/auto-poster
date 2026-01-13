import os
import sys
import json
import shutil
import re
import importlib.util
from fastapi.responses import FileResponse
from google.genai import types

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

class YouTubeService:
    def __init__(self):
        self._poster = None  # 지연 초기화
        self.base_v_dir = os.path.join(project_root, 'youtube_poster', 'v_source')
    
    @property
    def poster(self):
        """필요할 때만 YouTubeAutoPoster 인스턴스 생성"""
        if self._poster is None:
            self._poster = YouTubeAutoPoster()
        return self._poster

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

    def save_logo(self, category, file_content, filename):
        v_dir = os.path.join(self.base_v_dir, category)
        if not os.path.exists(v_dir):
            os.makedirs(v_dir, exist_ok=True)

        # 기존 로고들 백업 또는 삭제
        existing_logos = [f for f in os.listdir(v_dir) if f.lower().endswith('.png') and 'logo' in f.lower()]
        for f in existing_logos:
            os.remove(os.path.join(v_dir, f))

        # 새 로고 저장 (이름을 logo.png 등으로 고정하거나 원본 이름 유지)
        # youtube_poster.py가 'logo' 단어를 찾으므로 이름에 포함시킴
        save_path = os.path.join(v_dir, f"logo_{filename}")
        with open(save_path, "wb") as f:
            f.write(file_content)
        
        return save_path

    async def generate_metadata(self, pdf_content, category, lang='ko'):
        """PDF 분석을 통해 유튜브 메타데이터를 생성합니다. YouTube API 인증 없이 Gemini만 사용."""
        from core.summarizer import GeminiSummarizer
        
        # PDF 내용 확인
        if not pdf_content or len(pdf_content) == 0:
            raise Exception("PDF 파일이 비어있거나 전달되지 않았습니다.")
        
        print(f"📄 PDF 파일 수신: {len(pdf_content)} bytes")
        
        # 템플릿 읽기
        desc_path = os.path.join(self.base_v_dir, category, f'desc_{lang}.md')
        if not os.path.exists(desc_path):
            desc_path = os.path.join(self.base_v_dir, category, 'desc.md')
        
        desc_template = ""
        if os.path.exists(desc_path):
            with open(desc_path, 'r', encoding='utf-8') as f:
                desc_template = f.read()

        # GeminiSummarizer 사용 (YouTube API 인증 불필요)
        summarizer = GeminiSummarizer()
        if not summarizer.client:
            raise Exception("GEMINI_API_KEY가 설정되지 않았습니다.")
        
        lang_str = "Korean" if lang == 'ko' else "English"
        
        # YouTube 메타데이터 생성 프롬프트
        prompt = f"""
        Analyze the attached PDF and generate YouTube-optimized metadata in {lang_str}.
        
        [CRITICAL INSTRUCTIONS]
        1. Title: Create a click-worthy, dramatic title based on the PDF content.
        2. Description: Use the provided [TEMPLATE] below as a reference for style, tone, and structure.
           - Keep the dramatic storytelling opening.
           - Integrate the CORE findings and value propositions from the PDF into the middle section.
           - Keep the 'Service & Contact' information at the bottom exactly as in the template.
           - Use Emojis and Unicode bold characters for emphasis (YouTube doesn't support markdown bold).
           - Ensure URLs are plain text so they become clickable on YouTube.
        3. Tags: Generate 20+ highly relevant hashtags and keywords in {lang_str} based on the PDF content.
        
        [TEMPLATE]
        {desc_template}
        
        IMPORTANT: You MUST analyze the PDF content thoroughly and extract key information from it. Do not use generic content.
        
             Return ONLY a valid JSON object with NO markdown code blocks, NO explanations, NO extra text.
             The JSON must be valid and parseable. Follow these strict rules:
             1. All strings must be properly escaped (use \\n for newlines, \\" for quotes)
             2. All array items and object properties must be separated by commas
             3. No trailing commas
             4. All special characters in strings must be escaped
             
             Example format:
             {{
               "title": "Your title here",
               "description": "Your description here with \\n for line breaks",
               "tags": ["tag1", "tag2", "tag3"]
             }}
             
             Return ONLY the JSON object, nothing else.
             """
        
        try:
            print(f"🤖 Gemini API 호출 중... (PDF 크기: {len(pdf_content)} bytes)")
            response = summarizer.client.models.generate_content(
                model=summarizer.model_id,
                contents=[prompt, types.Part.from_bytes(data=pdf_content, mime_type='application/pdf')]
            )
            print(f"✅ Gemini API 응답 수신")
            
            # 원본 응답 로깅 (디버깅용)
            raw_text = response.text.strip()
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
            
            return metadata
        except Exception as e:
            print(f"❌ Error generating metadata: {e}")
            import traceback
            traceback.print_exc()
            # Fallback metadata는 사용하지 않고 에러를 전파
            raise Exception(f"메타데이터 생성 실패: {str(e)}")

    async def process_and_upload(self, video_content, filename, pdf_content, category, lang='ko', gen_sub=False):
        """영상을 처리하고 유튜브에 업로드합니다."""
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

        try:
            # 2. 메타데이터 생성
            desc_path = os.path.join(v_dir, f'desc_{lang}.md')
            if not os.path.exists(desc_path):
                desc_path = os.path.join(v_dir, 'desc.md')
            
            desc_template = ""
            if os.path.exists(desc_path):
                with open(desc_path, 'r', encoding='utf-8') as f:
                    desc_template = f.read()

            print(f"📝 메타데이터 생성 시작 (PDF: {pdf_path})")
            # YouTube API 인증 없이 메타데이터 생성 (generate_metadata 메서드 사용)
            with open(pdf_path, 'rb') as f:
                pdf_content = f.read()
            metadata = await self.generate_metadata(pdf_content, category, lang)
            print(f"✅ 메타데이터 생성 완료: {metadata.get('title', 'N/A')[:50]}...")

            # 3. 자막 생성 (옵션)
            srt_path = None
            if gen_sub:
                print(f"📝 자막 생성 시작...")
                try:
                    srt_path = self.poster.generate_subtitles(video_path, lang=lang)
                    print(f"✅ 자막 생성 완료: {srt_path}")
                except Exception as e:
                    print(f"❌ 자막 생성 실패: {e}")
                    import traceback
                    traceback.print_exc()
                    raise

            # 4. 로고 및 자막 합성
            print(f"🎨 로고 및 자막 합성 시작...")
            logo_path = self.get_logo_path(category)
            if not logo_path:
                raise Exception("Logo not found for category " + category)
            print(f"   로고 경로: {logo_path}")
            print(f"   비디오 경로: {video_path}")
            print(f"   최종 비디오 경로: {os.path.join(v_dir, f'final_{filename}')}")
            print(f"   자막 경로: {srt_path if srt_path else '없음'}")

            final_video_path = os.path.join(v_dir, f"final_{filename}")
            try:
                success = self.poster.add_logo_and_subs_to_video(video_path, logo_path, srt_path, final_video_path)
                print(f"✅ 비디오 편집 완료: {success}")
                if not success:
                    error_msg = "비디오 편집이 실패했습니다. FFmpeg 에러 로그를 확인하세요."
                    print(f"❌ {error_msg}")
                    raise Exception(error_msg)
            except Exception as e:
                print(f"❌ 비디오 편집 실패: {e}")
                import traceback
                traceback.print_exc()
                raise

            # 5. 유튜브 업로드
            print(f"📤 YouTube 업로드 시작...")
            try:
                video_id = self.poster.upload_video(final_video_path, metadata)
                print(f"✅ YouTube 업로드 완료: {video_id}")
            except Exception as e:
                print(f"❌ YouTube 업로드 실패: {e}")
                import traceback
                traceback.print_exc()
                raise
            
            if not video_id:
                raise Exception("YouTube upload failed")

            # 6. 정리
            for f in [video_path, pdf_path, srt_path, final_video_path]:
                if f and os.path.exists(f):
                    os.remove(f)

            return {
                "status": "success",
                "video_id": video_id,
                "link": f"https://youtu.be/{video_id}",
                "metadata": metadata
            }

        except Exception as e:
            # 오류 발생 시에도 임시 파일 정리
            for f in [video_path, pdf_path]:
                if f and os.path.exists(f):
                    os.remove(f)
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

