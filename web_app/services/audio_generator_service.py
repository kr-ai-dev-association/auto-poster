import os
import io
import json
import base64
import tempfile
import logging
import asyncio
import uuid
from typing import Optional, Dict, Any, List
from google import genai
from google.genai import types
from pdf2image import convert_from_path, convert_from_bytes
from PIL import Image
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)


# 백그라운드 태스크 상태 저장소
_audio_task_store: Dict[str, Dict[str, Any]] = {}


class AudioGeneratorService:
    """PDF에서 대본을 생성하고 TTS로 오디오를 생성하는 서비스"""

    def __init__(self):
        self._client = None
        self.script_model = 'gemini-2.5-flash'
        self.tts_model = 'gemini-2.5-flash-preview-tts'
        self.voice_name = 'Leda'  # 여성 음성

        # 출력 디렉토리 설정
        self.output_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), 'generated_audio')
        os.makedirs(self.output_dir, exist_ok=True)

    @property
    def client(self):
        """Lazy initialization of Gemini client"""
        if self._client is None:
            api_key = os.getenv("GEMINI_API_KEY")
            if api_key:
                self._client = genai.Client(api_key=api_key)
                logger.info("Gemini client initialized for AudioGeneratorService")
            else:
                logger.error("GEMINI_API_KEY not found.")
        return self._client

    @property
    def async_client(self):
        """Get async client for non-blocking API calls"""
        if self.client:
            return self.client.aio
        return None

    def _pdf_to_images(self, pdf_path: str, dpi: int = 150) -> List[Image.Image]:
        """PDF를 이미지 리스트로 변환"""
        try:
            images = convert_from_path(pdf_path, dpi=dpi)
            return images
        except Exception as e:
            logger.error(f"PDF to images conversion failed: {e}")
            raise

    def _pdf_bytes_to_images(self, pdf_bytes: bytes, dpi: int = 150) -> List[Image.Image]:
        """PDF 바이트를 이미지 리스트로 변환"""
        try:
            images = convert_from_bytes(pdf_bytes, dpi=dpi)
            return images
        except Exception as e:
            logger.error(f"PDF bytes to images conversion failed: {e}")
            raise

    def _image_to_base64(self, image: Image.Image) -> str:
        """PIL Image를 base64로 변환"""
        buffer = io.BytesIO()
        image.save(buffer, format='JPEG', quality=85)
        return base64.b64encode(buffer.getvalue()).decode('utf-8')

    async def generate_script_from_pdf(
        self,
        pdf_path: str = None,
        pdf_bytes: bytes = None,
        language: str = 'ko',
        style: str = 'educational'
    ) -> Dict[str, Any]:
        """
        PDF에서 YouTube 영상용 대본을 생성합니다.

        Args:
            pdf_path: PDF 파일 경로
            pdf_bytes: PDF 바이트 데이터
            language: 대본 언어 ('ko' 또는 'en')
            style: 대본 스타일 ('educational', 'casual', 'professional')

        Returns:
            Dict containing script and metadata
        """
        if not self.client:
            raise ValueError("Gemini client not initialized. Check GEMINI_API_KEY.")

        # PDF를 이미지로 변환
        if pdf_path:
            images = self._pdf_to_images(pdf_path)
        elif pdf_bytes:
            images = self._pdf_bytes_to_images(pdf_bytes)
        else:
            raise ValueError("Either pdf_path or pdf_bytes must be provided")

        page_count = len(images)
        logger.info(f"Generating script from PDF with {page_count} pages")

        # 이미지를 Gemini에 전달할 형식으로 준비
        image_parts = []
        for i, img in enumerate(images):
            img_base64 = self._image_to_base64(img)
            image_parts.append(
                types.Part.from_bytes(
                    data=base64.b64decode(img_base64),
                    mime_type="image/jpeg"
                )
            )

        # 언어 및 스타일에 따른 프롬프트 설정
        if language == 'ko':
            lang_instruction = "한국어로 대본을 작성하세요."
            style_instructions = {
                'educational': "교육적이고 명확한 톤으로 설명하세요. 청취자가 쉽게 이해할 수 있도록 친절하게 설명해주세요.",
                'casual': "친근하고 캐주얼한 톤으로 설명하세요. 마치 친구에게 설명하듯이 대화체로 작성하세요.",
                'professional': "전문적이고 격식있는 톤으로 설명하세요. 정확하고 신뢰감 있게 전달하세요."
            }
        else:
            lang_instruction = "Write the script in English."
            style_instructions = {
                'educational': "Use an educational and clear tone. Explain in a friendly manner so listeners can easily understand.",
                'casual': "Use a friendly and casual tone. Write as if explaining to a friend in conversational style.",
                'professional': "Use a professional and formal tone. Deliver accurately and with authority."
            }

        style_instruction = style_instructions.get(style, style_instructions['educational'])

        # 한국어일 때 외화 변환 안내 추가
        currency_instruction = ""
        if language == 'ko':
            currency_instruction = """
9. 외화 금액(달러, 유로, 엔화 등)이 등장할 경우, 원화 환산 금액을 함께 언급하세요.
   - 예시: "$100" → "백 달러, 한화로 약 십사만 원"
   - 예시: "€50" → "오십 유로, 한화로 약 칠만 오천 원"
   - 예시: "¥10,000" → "만 엔, 한화로 약 구만 원"
   - 대략적인 환율 기준: 1달러=1,400원, 1유로=1,500원, 100엔=900원
   - 금액은 한글로 자연스럽게 읽히도록 작성하세요."""

        prompt = f"""당신은 전문 YouTube 영상 대본 작가입니다.
주어진 PDF 슬라이드를 분석하고, 이를 기반으로 YouTube 영상에 사용할 음성 대본을 작성해주세요.

{lang_instruction}
{style_instruction}

## 대본 작성 규칙:
1. 각 슬라이드의 핵심 내용을 자연스러운 설명으로 변환하세요.
2. TTS로 읽을 것이므로 읽기 쉽고 자연스러운 문장을 사용하세요.
3. 슬라이드 간 자연스러운 전환을 위한 연결어를 사용하세요.
4. 너무 짧거나 너무 길지 않게, 각 슬라이드당 적절한 분량을 유지하세요.
5. 청취자의 이해를 돕기 위해 필요한 경우 추가 설명을 포함하세요.
6. 인사말이나 마무리 멘트는 간결하게 작성하세요.
7. 괄호, 특수문자, 약어는 TTS가 읽기 어려우므로 풀어서 작성하세요.
8. 숫자는 읽는 방식 그대로 작성하세요 (예: "2024년" 대신 "이천이십사년").{currency_instruction}

## 출력 형식:
대본 텍스트만 출력하세요. 슬라이드 번호나 구분 표시 없이 하나의 연속된 대본으로 작성하세요.
"""

        # Gemini에 요청
        contents = [prompt] + image_parts

        try:
            response = await self.async_client.models.generate_content(
                model=self.script_model,
                contents=contents,
                config=types.GenerateContentConfig(
                    temperature=0.7,
                    max_output_tokens=8192
                )
            )

            script = response.text.strip()

            # 예상 읽기 시간 계산 (한국어 평균 분당 300자, 영어 평균 분당 150단어)
            if language == 'ko':
                estimated_duration = len(script) / 300 * 60  # 초 단위
            else:
                word_count = len(script.split())
                estimated_duration = word_count / 150 * 60  # 초 단위

            return {
                'status': 'success',
                'script': script,
                'page_count': page_count,
                'char_count': len(script),
                'estimated_duration': round(estimated_duration, 1),
                'language': language,
                'style': style
            }

        except Exception as e:
            logger.error(f"Script generation failed: {e}")
            return {
                'status': 'error',
                'message': str(e)
            }

    async def generate_audio_from_script(
        self,
        script: str,
        output_filename: str = None,
        voice: str = None,
        language: str = 'ko',
        metadata: Dict[str, Any] = None,
        content_id: str = None
    ) -> Dict[str, Any]:
        """
        대본에서 TTS를 사용하여 오디오를 생성합니다.

        Args:
            script: 읽을 대본 텍스트
            output_filename: 출력 파일명 (확장자 제외)
            voice: 음성 이름 (기본값: Leda)
            language: 언어 코드
            metadata: 저장할 메타데이터 (language, style, pdf_filename 등)
            content_id: 통합 콘텐츠 ID (파이프라인에서 전달)

        Returns:
            Dict containing audio file path and metadata
        """
        if not self.client:
            raise ValueError("Gemini client not initialized. Check GEMINI_API_KEY.")

        voice = voice or self.voice_name

        # content_id가 있으면 통합 ID 기반 파일명 사용
        if content_id:
            output_filename = content_id
        elif not output_filename:
            import uuid
            output_filename = f"audio_{uuid.uuid4().hex[:8]}"

        output_path = os.path.join(self.output_dir, f"{output_filename}.wav")

        logger.info(f"Generating audio with voice '{voice}' for script ({len(script)} chars)")

        try:
            # Gemini TTS 요청 (비동기)
            response = await self.async_client.models.generate_content(
                model=self.tts_model,
                contents=script,
                config=types.GenerateContentConfig(
                    response_modalities=["AUDIO"],
                    speech_config=types.SpeechConfig(
                        voice_config=types.VoiceConfig(
                            prebuilt_voice_config=types.PrebuiltVoiceConfig(
                                voice_name=voice
                            )
                        )
                    )
                )
            )

            # 오디오 데이터 추출
            inline_data = response.candidates[0].content.parts[0].inline_data
            audio_data = inline_data.data
            mime_type = inline_data.mime_type if hasattr(inline_data, 'mime_type') else 'audio/pcm'

            logger.info(f"TTS response mime_type: {mime_type}, data size: {len(audio_data)} bytes")

            # WAV 헤더가 없는 PCM 데이터인지 확인 (어떤 mime_type이든 RIFF 헤더가 없으면 추가)
            if audio_data[:4] != b'RIFF':
                # PCM 데이터에 WAV 헤더 추가 (24kHz, 16-bit, mono - Gemini TTS 기본값)
                import struct
                sample_rate = 24000
                bits_per_sample = 16
                num_channels = 1
                byte_rate = sample_rate * num_channels * bits_per_sample // 8
                block_align = num_channels * bits_per_sample // 8
                data_size = len(audio_data)

                wav_header = struct.pack(
                    '<4sI4s4sIHHIIHH4sI',
                    b'RIFF',
                    36 + data_size,
                    b'WAVE',
                    b'fmt ',
                    16,  # fmt chunk size
                    1,   # audio format (PCM)
                    num_channels,
                    sample_rate,
                    byte_rate,
                    block_align,
                    bits_per_sample,
                    b'data',
                    data_size
                )
                audio_data = wav_header + audio_data
                logger.info(f"Added WAV header to PCM data (original mime_type: {mime_type})")

            # MP3 형식인 경우 확장자 변경
            if 'mp3' in mime_type:
                output_path = output_path.replace('.wav', '.mp3')

            with open(output_path, 'wb') as f:
                f.write(audio_data)

            # 파일 크기 확인
            file_size = os.path.getsize(output_path)

            # 재생 시간 계산
            duration = 0
            if output_path.endswith('.wav'):
                import wave
                try:
                    with wave.open(output_path, 'rb') as wav_file:
                        frames = wav_file.getnframes()
                        rate = wav_file.getframerate()
                        duration = frames / float(rate)
                except Exception as wav_err:
                    logger.warning(f"Could not read WAV duration: {wav_err}")
                    # 파일 크기로 대략적인 재생 시간 추정 (24kHz, 16-bit, mono)
                    duration = file_size / (24000 * 2)
            else:
                # MP3 등 다른 형식의 경우 대략적 추정
                duration = file_size / 16000  # 대략적 추정

            logger.info(f"Audio generated: {output_path} ({duration:.1f}s, {file_size} bytes)")

            # 실제 저장된 파일명 추출
            actual_filename = os.path.basename(output_path)

            # 메타데이터 JSON 파일 저장
            meta_path = output_path.rsplit('.', 1)[0] + '.json'
            meta_data = {
                'filename': actual_filename,
                'duration': round(duration, 1),
                'file_size': file_size,
                'voice': voice,
                'script': script,
                'language': language,
                **(metadata or {})
            }
            # content_id가 있으면 추가
            if content_id:
                meta_data['content_id'] = content_id
            with open(meta_path, 'w', encoding='utf-8') as f:
                json.dump(meta_data, f, ensure_ascii=False, indent=2)
            logger.info(f"Metadata saved: {meta_path}")

            result = {
                'status': 'success',
                'audio_path': output_path,
                'filename': actual_filename,
                'duration': round(duration, 1),
                'file_size': file_size,
                'voice': voice
            }
            if content_id:
                result['content_id'] = content_id
            return result

        except Exception as e:
            logger.error(f"Audio generation failed: {e}")
            return {
                'status': 'error',
                'message': str(e)
            }

    async def generate_audio_from_pdf(
        self,
        pdf_path: str = None,
        pdf_bytes: bytes = None,
        output_filename: str = None,
        language: str = 'ko',
        style: str = 'educational',
        voice: str = None
    ) -> Dict[str, Any]:
        """
        PDF에서 직접 오디오를 생성합니다 (대본 생성 + TTS).

        Args:
            pdf_path: PDF 파일 경로
            pdf_bytes: PDF 바이트 데이터
            output_filename: 출력 파일명 (확장자 제외)
            language: 대본 언어
            style: 대본 스타일
            voice: TTS 음성

        Returns:
            Dict containing script, audio file path and metadata
        """
        # 1. 대본 생성
        script_result = await self.generate_script_from_pdf(
            pdf_path=pdf_path,
            pdf_bytes=pdf_bytes,
            language=language,
            style=style
        )

        if script_result['status'] != 'success':
            return script_result

        script = script_result['script']

        # 2. 오디오 생성
        audio_result = await self.generate_audio_from_script(
            script=script,
            output_filename=output_filename,
            voice=voice
        )

        if audio_result['status'] != 'success':
            return {
                'status': 'error',
                'message': f"Script generated but audio failed: {audio_result.get('message', 'Unknown error')}",
                'script': script
            }

        # 결과 병합
        return {
            'status': 'success',
            'script': script,
            'audio_path': audio_result['audio_path'],
            'filename': audio_result['filename'],
            'audio_duration': audio_result['duration'],
            'file_size': audio_result['file_size'],
            'page_count': script_result['page_count'],
            'char_count': script_result['char_count'],
            'language': language,
            'style': style,
            'voice': audio_result['voice']
        }

    def get_available_voices(self) -> List[Dict[str, str]]:
        """사용 가능한 TTS 음성 목록을 반환합니다."""
        return [
            {'name': 'Leda', 'gender': 'female', 'description': '따뜻하고 친근한 여성 음성'},
            {'name': 'Zephyr', 'gender': 'male', 'description': '차분하고 신뢰감 있는 남성 음성'},
            {'name': 'Aoede', 'gender': 'female', 'description': '밝고 활기찬 여성 음성'},
            {'name': 'Charon', 'gender': 'male', 'description': '깊고 무게감 있는 남성 음성'},
            {'name': 'Fenrir', 'gender': 'male', 'description': '젊고 역동적인 남성 음성'},
            {'name': 'Kore', 'gender': 'female', 'description': '부드럽고 세련된 여성 음성'},
            {'name': 'Puck', 'gender': 'male', 'description': '캐주얼하고 친근한 남성 음성'},
            {'name': 'Orbit', 'gender': 'female', 'description': '전문적이고 명확한 여성 음성'}
        ]

    def list_generated_audio(self) -> List[Dict[str, Any]]:
        """생성된 오디오 파일 목록을 반환합니다."""
        audio_files = []

        if not os.path.exists(self.output_dir):
            return audio_files

        for filename in os.listdir(self.output_dir):
            if filename.endswith('.wav') or filename.endswith('.mp3'):
                filepath = os.path.join(self.output_dir, filename)
                stat = os.stat(filepath)

                # 재생 시간 계산 (WAV 파일만)
                duration = 0
                if filename.endswith('.wav'):
                    try:
                        import wave
                        with wave.open(filepath, 'rb') as wav_file:
                            frames = wav_file.getnframes()
                            rate = wav_file.getframerate()
                            duration = frames / float(rate)
                    except Exception:
                        pass

                # 메타데이터 JSON 파일 로드
                meta_path = filepath.rsplit('.', 1)[0] + '.json'
                metadata = {}
                if os.path.exists(meta_path):
                    try:
                        with open(meta_path, 'r', encoding='utf-8') as f:
                            metadata = json.load(f)
                    except Exception:
                        pass

                audio_files.append({
                    'filename': filename,
                    'filepath': filepath,
                    'size': stat.st_size,
                    'duration': round(duration, 1),
                    'created_at': stat.st_mtime,
                    'language': metadata.get('language'),
                    'style': metadata.get('style'),
                    'voice': metadata.get('voice'),
                    'pdf_filename': metadata.get('pdf_filename'),
                    'script': metadata.get('script')
                })

        # 생성일 기준 정렬 (최신순)
        audio_files.sort(key=lambda x: x['created_at'], reverse=True)

        return audio_files

    def delete_audio(self, filename: str) -> bool:
        """오디오 파일과 메타데이터를 삭제합니다."""
        filepath = os.path.join(self.output_dir, filename)
        deleted = False

        if os.path.exists(filepath):
            os.remove(filepath)
            deleted = True
            logger.info(f"Deleted audio file: {filename}")

        # 메타데이터 JSON 파일도 삭제
        meta_path = filepath.rsplit('.', 1)[0] + '.json'
        if os.path.exists(meta_path):
            os.remove(meta_path)
            logger.info(f"Deleted metadata file: {meta_path}")

        return deleted

    # ========== 백그라운드 태스크 관리 ==========

    @staticmethod
    def create_task(task_type: str, metadata: Dict[str, Any] = None) -> str:
        """새 백그라운드 태스크를 생성합니다."""
        task_id = str(uuid.uuid4())[:8]
        _audio_task_store[task_id] = {
            'task_id': task_id,
            'type': task_type,
            'status': 'pending',
            'progress': 0,
            'message': '대기 중...',
            'result': None,
            'error': None,
            'metadata': metadata or {}
        }
        return task_id

    @staticmethod
    def update_task(task_id: str, status: str = None, progress: int = None,
                   message: str = None, result: Dict = None, error: str = None):
        """태스크 상태를 업데이트합니다."""
        if task_id in _audio_task_store:
            if status:
                _audio_task_store[task_id]['status'] = status
            if progress is not None:
                _audio_task_store[task_id]['progress'] = progress
            if message:
                _audio_task_store[task_id]['message'] = message
            if result:
                _audio_task_store[task_id]['result'] = result
            if error:
                _audio_task_store[task_id]['error'] = error

    @staticmethod
    def get_task(task_id: str) -> Optional[Dict[str, Any]]:
        """태스크 상태를 조회합니다."""
        return _audio_task_store.get(task_id)

    @staticmethod
    def delete_task(task_id: str):
        """완료된 태스크를 삭제합니다."""
        if task_id in _audio_task_store:
            del _audio_task_store[task_id]

    async def run_script_generation_task(
        self,
        task_id: str,
        pdf_bytes: bytes,
        language: str = 'ko',
        style: str = 'educational'
    ):
        """백그라운드에서 대본 생성을 실행합니다."""
        try:
            self.update_task(task_id, status='running', progress=10, message='PDF 분석 중...')

            result = await self.generate_script_from_pdf(
                pdf_bytes=pdf_bytes,
                language=language,
                style=style
            )

            if result.get('status') == 'success':
                self.update_task(
                    task_id,
                    status='completed',
                    progress=100,
                    message='대본 생성 완료!',
                    result=result
                )
            else:
                self.update_task(
                    task_id,
                    status='error',
                    progress=0,
                    message=f"오류: {result.get('message', 'Unknown error')}",
                    error=result.get('message')
                )
        except Exception as e:
            logger.error(f"Script generation task failed: {e}")
            self.update_task(
                task_id,
                status='error',
                progress=0,
                message=f"오류: {str(e)}",
                error=str(e)
            )

    async def run_audio_generation_task(
        self,
        task_id: str,
        script: str,
        voice: str = 'Leda',
        filename: str = None,
        metadata: Dict[str, Any] = None
    ):
        """백그라운드에서 오디오 생성을 실행합니다."""
        try:
            self.update_task(task_id, status='running', progress=10, message='오디오 생성 중...')

            result = await self.generate_audio_from_script(
                script=script,
                output_filename=filename,
                voice=voice,
                metadata=metadata
            )

            if result.get('status') == 'success':
                self.update_task(
                    task_id,
                    status='completed',
                    progress=100,
                    message='오디오 생성 완료!',
                    result=result
                )
            else:
                self.update_task(
                    task_id,
                    status='error',
                    progress=0,
                    message=f"오류: {result.get('message', 'Unknown error')}",
                    error=result.get('message')
                )
        except Exception as e:
            logger.error(f"Audio generation task failed: {e}")
            self.update_task(
                task_id,
                status='error',
                progress=0,
                message=f"오류: {str(e)}",
                error=str(e)
            )


# 싱글톤 인스턴스
audio_generator = AudioGeneratorService()
