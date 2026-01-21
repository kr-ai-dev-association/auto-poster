"""
PDF to MP4 변환 서비스
PDF 파일을 MP4 영상으로 변환하는 기능을 제공합니다.
NVENC GPU 가속을 직접 사용합니다.
"""

import os
import tempfile
import shutil
import uuid
from datetime import datetime
from typing import Optional, List, Dict, Any
from dataclasses import dataclass
import subprocess

# PDF to Image
from pdf2image import convert_from_bytes
import io

# PDF text extraction
try:
    import PyPDF2
    PYPDF_AVAILABLE = True
except ImportError:
    PYPDF_AVAILABLE = False

# PaddleOCR for image-based PDF text extraction
try:
    from paddleocr import PaddleOCR
    PADDLEOCR_AVAILABLE = True
except ImportError:
    PADDLEOCR_AVAILABLE = False
    print("Warning: PaddleOCR not installed. OCR-based text extraction will not be available.")

from PIL import Image
import numpy as np
import re
from difflib import SequenceMatcher

# Whisper for Smart mode (optional)
try:
    import whisper
    WHISPER_AVAILABLE = True
except ImportError:
    WHISPER_AVAILABLE = False
    print("Warning: openai-whisper not installed. Smart mode will not be available.")


@dataclass
class ConversionConfig:
    """변환 설정"""
    page_duration: float = 5.0
    transition_duration: float = 0.5
    transition_type: str = 'fade'
    fps: int = 30
    width: int = 1920
    height: int = 1080
    dpi: int = 200


class PDF2MP4Service:
    """PDF를 MP4 영상으로 변환하는 서비스 (NVENC 직접 사용)"""

    TRANSITIONS = ['fade', 'slide_left', 'slide_right', 'slide_up', 'slide_down', 'zoom', 'none']
    AUDIO_FORMATS = ['.mp3', '.wav', '.m4a', '.aac', '.ogg']
    _progress_store: Dict[str, Dict[str, Any]] = {}

    def __init__(self):
        self.output_dir = os.path.join(
            os.path.dirname(__file__),
            '..', '..', 'generated_videos'
        )
        self.pdf_dir = os.path.join(
            os.path.dirname(__file__),
            '..', '..', 'generated_pdfs'
        )
        os.makedirs(self.output_dir, exist_ok=True)
        os.makedirs(self.pdf_dir, exist_ok=True)
        self._whisper_model = None
        self._paddleocr = None

    @property
    def paddleocr(self):
        """PaddleOCR 모델 (지연 로딩)"""
        if self._paddleocr is None and PADDLEOCR_AVAILABLE:
            print("Loading PaddleOCR model...")
            self._paddleocr = PaddleOCR(use_angle_cls=True, lang='en', show_log=False)
        return self._paddleocr

    @classmethod
    def get_progress(cls, video_id: str) -> Optional[Dict[str, Any]]:
        return cls._progress_store.get(video_id)

    @classmethod
    def update_progress(cls, video_id: str, stage: str, progress: int, message: str, eta: Optional[int] = None):
        cls._progress_store[video_id] = {
            'video_id': video_id,
            'stage': stage,
            'progress': progress,
            'message': message,
            'eta': eta,
            'timestamp': datetime.now().isoformat()
        }

    @classmethod
    def clear_progress(cls, video_id: str):
        if video_id in cls._progress_store:
            del cls._progress_store[video_id]

    @property
    def whisper_model(self):
        if self._whisper_model is None and WHISPER_AVAILABLE:
            import torch
            device = "cuda" if torch.cuda.is_available() else "cpu"
            print(f"Loading Whisper model (base) on {device}...")
            self._whisper_model = whisper.load_model("base", device=device)
        return self._whisper_model

    def _resize_image(self, img: Image.Image, width: int, height: int, logo_img: Image.Image = None) -> np.ndarray:
        """이미지를 지정된 크기로 리사이즈 (종횡비 유지, 검은 배경, 로고 합성)"""
        orig_width, orig_height = img.size
        ratio = min(width / orig_width, height / orig_height)
        new_width = int(orig_width * ratio)
        new_height = int(orig_height * ratio)

        img_resized = img.resize((new_width, new_height), Image.Resampling.LANCZOS)
        background = Image.new('RGB', (width, height), (0, 0, 0))
        offset_x = (width - new_width) // 2
        offset_y = (height - new_height) // 2
        background.paste(img_resized, (offset_x, offset_y))

        # 로고 합성 (영상 프레임 우측 하단 끝에 맞춤)
        if logo_img is not None:
            # 로고 크기 조정 (문서 너비의 약 15%)
            logo_target_width = int(new_width * 0.15)
            logo_ratio = logo_target_width / logo_img.width
            logo_new_height = int(logo_img.height * logo_ratio)
            logo_resized = logo_img.resize((logo_target_width, logo_new_height), Image.Resampling.LANCZOS)

            # 영상 프레임 우측 하단 끝에 로고 배치
            logo_x = width - logo_target_width
            logo_y = height - logo_new_height

            # 알파 채널이 있으면 투명도 적용하여 합성
            if logo_resized.mode == 'RGBA':
                background.paste(logo_resized, (logo_x, logo_y), logo_resized)
            else:
                background.paste(logo_resized, (logo_x, logo_y))

        return np.array(background)

    def _extract_pdf_page_texts(self, pdf_content: bytes) -> List[str]:
        """PDF 각 페이지에서 텍스트 추출 (PyPDF2 실패 시 OCR 사용)"""
        page_texts = []

        # 1. PyPDF2로 텍스트 추출 시도
        if PYPDF_AVAILABLE:
            try:
                pdf_reader = PyPDF2.PdfReader(io.BytesIO(pdf_content))
                for page in pdf_reader.pages:
                    text = page.extract_text() or ""
                    text = text.lower()
                    text = re.sub(r'[^\w\s]', ' ', text)
                    text = ' '.join(text.split())
                    page_texts.append(text)

                # 텍스트가 추출되었는지 확인
                total_text = ''.join(page_texts)
                if len(total_text) > 50:  # 충분한 텍스트가 있으면 반환
                    print(f"PyPDF2로 텍스트 추출 성공: {len(total_text)} 문자")
                    return page_texts
                else:
                    print(f"PyPDF2 텍스트 부족 ({len(total_text)} 문자), OCR 시도...")
                    page_texts = []  # 리셋
            except Exception as e:
                print(f"PyPDF2 텍스트 추출 오류: {e}")

        return page_texts

    def _extract_text_with_ocr(self, images: List[Image.Image], video_id: str = "") -> List[str]:
        """PaddleOCR을 사용하여 이미지에서 텍스트 추출"""
        if not PADDLEOCR_AVAILABLE or self.paddleocr is None:
            print(f"[{video_id}] PaddleOCR 사용 불가")
            return []

        page_texts = []
        print(f"[{video_id}] 🔍 PaddleOCR로 {len(images)}개 페이지 텍스트 추출 시작")

        for i, img in enumerate(images):
            try:
                # PIL Image를 numpy array로 변환
                img_array = np.array(img.convert('RGB'))

                # OCR 수행 (PaddleOCR 2.x)
                result = self.paddleocr.ocr(img_array, cls=True)

                # 텍스트 추출
                texts = []
                if result and result[0]:
                    for line in result[0]:
                        if line and len(line) >= 2:
                            text = line[1][0] if isinstance(line[1], tuple) else line[1]
                            texts.append(text)

                # 정규화
                page_text = ' '.join(texts).lower()
                page_text = re.sub(r'[^\w\s]', ' ', page_text)
                page_text = ' '.join(page_text.split())
                page_texts.append(page_text)

                if (i + 1) % 5 == 0 or i == len(images) - 1:
                    print(f"[{video_id}]   OCR 진행: {i + 1}/{len(images)} 페이지")

            except Exception as e:
                print(f"[{video_id}] OCR 오류 (페이지 {i + 1}): {e}")
                page_texts.append("")

        return page_texts

    def _extract_keywords_from_page(self, text: str, min_length: int = 4) -> List[str]:
        """페이지 텍스트에서 중요 키워드 추출"""
        # 일반적인 불용어
        stopwords = {
            'the', 'and', 'for', 'that', 'this', 'with', 'from', 'have', 'has',
            'are', 'was', 'were', 'been', 'being', 'will', 'would', 'could',
            'should', 'may', 'might', 'must', 'shall', 'can', 'need', 'does',
            'did', 'done', 'doing', 'just', 'only', 'also', 'very', 'much',
            'more', 'most', 'such', 'like', 'than', 'then', 'when', 'where',
            'which', 'what', 'who', 'whom', 'whose', 'how', 'why', 'all',
            'each', 'every', 'both', 'few', 'many', 'some', 'any', 'other',
            'into', 'through', 'during', 'before', 'after', 'above', 'below',
            'between', 'under', 'again', 'further', 'once', 'here', 'there',
            'about', 'over', 'these', 'those', 'their', 'them', 'they', 'your',
            'page', 'slide', 'copyright', 'reserved', 'rights'
        }

        words = text.split()
        keywords = []

        for word in words:
            if len(word) >= min_length and word not in stopwords:
                keywords.append(word)

        # 중복 제거하면서 순서 유지
        seen = set()
        unique_keywords = []
        for kw in keywords:
            if kw not in seen:
                seen.add(kw)
                unique_keywords.append(kw)

        return unique_keywords[:30]  # 상위 30개 키워드

    def _find_keyword_in_transcript(
        self,
        keyword: str,
        segments: List[Dict],
        search_start: float = 0
    ) -> Optional[float]:
        """트랜스크립트에서 키워드가 처음 등장하는 시간 찾기"""
        keyword_lower = keyword.lower()

        for segment in segments:
            if segment['start'] < search_start:
                continue

            segment_text = segment.get('text', '').lower()
            # 정규화
            segment_text = re.sub(r'[^\w\s]', ' ', segment_text)

            if keyword_lower in segment_text:
                return segment['start']

            # 부분 매칭 (Fuzzy matching)
            for word in segment_text.split():
                if len(word) >= 4:
                    ratio = SequenceMatcher(None, keyword_lower, word).ratio()
                    if ratio > 0.8:  # 80% 이상 유사
                        return segment['start']

        return None

    def _find_best_segment_for_keywords(
        self,
        keywords: List[str],
        segments: List[Dict],
        search_start: float = 0,
        window_size: int = 5
    ) -> tuple[Optional[float], List[str], int]:
        """
        여러 키워드를 검색하여 가장 많은 키워드가 매칭되는 구간 찾기

        Args:
            keywords: 검색할 키워드 목록
            segments: Whisper 세그먼트 목록
            search_start: 검색 시작 시간
            window_size: 연속 세그먼트 윈도우 크기

        Returns:
            (매칭 시간, 매칭된 키워드 목록, 매칭 수)
        """
        if not keywords or not segments:
            return None, [], 0

        best_time = None
        best_matched_keywords = []
        best_match_count = 0

        # 검색 시작 위치 찾기
        start_idx = 0
        for i, seg in enumerate(segments):
            if seg['start'] >= search_start:
                start_idx = i
                break

        # 슬라이딩 윈도우로 연속 세그먼트 검색
        for i in range(start_idx, len(segments)):
            # 윈도우 내 텍스트 결합
            window_end = min(i + window_size, len(segments))
            window_text = ' '.join(
                seg.get('text', '') for seg in segments[i:window_end]
            ).lower()
            window_text = re.sub(r'[^\w\s]', ' ', window_text)
            window_words = set(window_text.split())

            # 키워드 매칭 수 계산
            matched_keywords = []
            for kw in keywords:
                kw_lower = kw.lower()
                # 정확 매칭
                if kw_lower in window_text:
                    matched_keywords.append(kw)
                    continue
                # 부분 매칭 (fuzzy)
                for word in window_words:
                    if len(word) >= 4:
                        ratio = SequenceMatcher(None, kw_lower, word).ratio()
                        if ratio > 0.8:
                            matched_keywords.append(kw)
                            break

            # 최소 2개 이상 매칭되어야 유효한 결과
            if len(matched_keywords) >= 2 and len(matched_keywords) > best_match_count:
                best_match_count = len(matched_keywords)
                best_matched_keywords = matched_keywords
                best_time = segments[i]['start']

        return best_time, best_matched_keywords, best_match_count

    def _encode_video_nvenc(
        self,
        images: List[np.ndarray],
        timings: List[Dict[str, float]],
        audio_path: Optional[str],
        output_path: str,
        fps: int,
        width: int,
        height: int,
        video_id: str
    ) -> bool:
        """NVENC를 직접 사용하여 영상 인코딩"""

        # ffmpeg 명령어 구성
        ffmpeg_cmd = [
            'ffmpeg', '-y',
            '-f', 'rawvideo',
            '-vcodec', 'rawvideo',
            '-s', f'{width}x{height}',
            '-pix_fmt', 'rgb24',
            '-r', str(fps),
            '-i', '-',
        ]

        if audio_path:
            ffmpeg_cmd.extend(['-i', audio_path])

        ffmpeg_cmd.extend([
            '-c:v', 'h264_nvenc',
            '-preset', 'p4',  # 빠른 프리셋
            '-rc', 'vbr',
            '-cq', '23',
            '-pix_fmt', 'yuv420p',
        ])

        if audio_path:
            ffmpeg_cmd.extend(['-c:a', 'aac', '-b:a', '192k'])
        else:
            ffmpeg_cmd.extend(['-an'])

        ffmpeg_cmd.append(output_path)

        # ffmpeg 프로세스 시작
        process = subprocess.Popen(
            ffmpeg_cmd,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE
        )

        # 총 프레임 수 계산
        total_duration = timings[-1]['start'] + timings[-1]['duration'] if timings else 0
        total_frames = int(total_duration * fps)

        print(f"[{video_id}] 🎬 NVENC 인코딩 시작: {total_frames} 프레임, {total_duration:.1f}초")

        # 프레임 생성 및 전송
        frame_count = 0
        current_image_idx = 0

        try:
            for frame_idx in range(total_frames):
                t = frame_idx / fps

                # 현재 시간에 해당하는 이미지 찾기
                while current_image_idx < len(timings) - 1:
                    next_start = timings[current_image_idx + 1]['start']
                    if t >= next_start:
                        current_image_idx += 1
                    else:
                        break

                # 이미지 프레임 쓰기
                frame = images[min(current_image_idx, len(images) - 1)]
                process.stdin.write(frame.astype(np.uint8).tobytes())
                frame_count += 1

                # 진행률 업데이트 (5% 단위)
                if frame_count % max(1, total_frames // 20) == 0:
                    progress = int((frame_count / total_frames) * 100)
                    eta = int((total_frames - frame_count) / fps * 0.05)  # NVENC는 매우 빠름
                    self.update_progress(video_id, 'encoding', min(95, 60 + progress * 0.35),
                                       f'🎬 인코딩 중... {progress}%', eta)
                    print(f"[{video_id}] 진행: {progress}% ({frame_count}/{total_frames})")
        except BrokenPipeError:
            # ffmpeg가 일찍 종료됨 - stderr 확인
            stderr = process.stderr.read()
            print(f"[{video_id}] FFmpeg가 조기 종료됨: {stderr.decode()}")
            process.wait()
            return False

        process.stdin.close()
        process.wait()

        stderr_output = process.stderr.read().decode() if process.stderr else ""

        if process.returncode != 0:
            print(f"[{video_id}] FFmpeg 오류 (코드 {process.returncode}): {stderr_output}")
            return False

        print(f"[{video_id}] ✅ NVENC 인코딩 완료: {frame_count} 프레임")
        return True

    async def convert_basic(
        self,
        pdf_content: bytes,
        filename: str,
        audio_content: Optional[bytes] = None,
        audio_filename: Optional[str] = None,
        page_duration: float = 5.0,
        transition: str = 'fade',
        transition_duration: float = 0.5,
        width: int = 1920,
        height: int = 1080,
        fps: int = 30,
        dpi: int = 200,
        auto_duration: bool = False,
        logo_path: Optional[str] = None
    ) -> Dict[str, Any]:
        """Basic 모드: 고정 시간 간격으로 PDF를 영상으로 변환"""
        video_id = str(uuid.uuid4())[:8]
        temp_dir = tempfile.mkdtemp(prefix=f'pdf2mp4_{video_id}_')

        try:
            print(f"[{video_id}] Starting Basic conversion for: {filename}")

            # 1. PDF를 이미지로 변환
            print(f"[{video_id}] Converting PDF to images (DPI: {dpi})...")
            images = convert_from_bytes(pdf_content, dpi=dpi)
            print(f"[{video_id}] Extracted {len(images)} pages")

            # 로고 이미지 로드
            logo_img = None
            if logo_path and os.path.exists(logo_path):
                logo_img = Image.open(logo_path).convert('RGBA')
                print(f"[{video_id}] Logo loaded: {logo_path}")

            # 2. 이미지 리사이즈 (로고 합성 포함)
            resized_images = []
            for img in images:
                resized = self._resize_image(img, width, height, logo_img)
                resized_images.append(resized)

            # 3. 오디오 처리
            audio_path = None
            audio_duration = 0
            if audio_content:
                audio_ext = os.path.splitext(audio_filename or '.mp3')[1].lower()
                audio_path = os.path.join(temp_dir, f'audio{audio_ext}')
                with open(audio_path, 'wb') as f:
                    f.write(audio_content)

                # ffprobe로 오디오 길이 확인
                result = subprocess.run(
                    ['ffprobe', '-v', 'error', '-show_entries', 'format=duration',
                     '-of', 'default=noprint_wrappers=1:nokey=1', audio_path],
                    capture_output=True, text=True
                )
                audio_duration = float(result.stdout.strip()) if result.stdout.strip() else 0
                print(f"[{video_id}] Audio loaded: {audio_duration:.2f}s")

                if auto_duration and audio_duration > 0:
                    page_duration = audio_duration / len(images)
                    print(f"[{video_id}] Auto page duration: {page_duration:.2f}s")

            # 4. 타이밍 계산
            timings = []
            for i in range(len(resized_images)):
                start_time = i * page_duration
                timings.append({'start': start_time, 'duration': page_duration})

            # 오디오에 맞게 조정
            if audio_duration > 0:
                total_video_duration = len(images) * page_duration
                if audio_duration > total_video_duration:
                    # 마지막 이미지 연장
                    extra = audio_duration - total_video_duration + 2.0  # 2초 마진
                    timings[-1]['duration'] += extra

            # 5. 영상 출력
            output_filename = f"{os.path.splitext(filename)[0]}_{video_id}.mp4"
            output_path = os.path.join(self.output_dir, output_filename)
            video_duration = timings[-1]['start'] + timings[-1]['duration']

            print(f"[{video_id}] 🎬 NVENC GPU 가속 인코딩 시작")
            print(f"[{video_id}] 📊 영상 길이: {video_duration:.1f}초")

            success = self._encode_video_nvenc(
                resized_images, timings, audio_path, output_path, fps, width, height, video_id
            )

            if not success:
                raise Exception("NVENC encoding failed")

            # 6. 원본 PDF 저장 (YouTube Poster에서 재사용 가능)
            pdf_filename = f"{os.path.splitext(filename)[0]}_{video_id}.pdf"
            pdf_path = os.path.join(self.pdf_dir, pdf_filename)
            with open(pdf_path, 'wb') as f:
                f.write(pdf_content)
            print(f"[{video_id}] 📄 원본 PDF 저장: {pdf_filename}")

            video_info = {
                'id': video_id,
                'filename': output_filename,
                'original_pdf': filename,
                'pdf_path': pdf_path,
                'mode': 'basic',
                'page_count': len(images),
                'duration': video_duration,
                'resolution': f'{width}x{height}',
                'transition': transition,
                'page_duration': page_duration,
                'created_at': datetime.utcnow().isoformat(),
                'file_path': output_path,
                'file_size': os.path.getsize(output_path)
            }

            print(f"[{video_id}] Conversion completed successfully")
            return {'status': 'success', 'video': video_info}

        except Exception as e:
            print(f"[{video_id}] Conversion failed: {str(e)}")
            import traceback
            traceback.print_exc()
            return {'status': 'error', 'message': str(e)}
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)

    async def convert_smart(
        self,
        pdf_content: bytes,
        filename: str,
        audio_content: bytes,
        audio_filename: str,
        transition: str = 'fade',
        transition_duration: float = 0.5,
        width: int = 1920,
        height: int = 1080,
        fps: int = 30,
        dpi: int = 200,
        logo_path: Optional[str] = None
    ) -> Dict[str, Any]:
        """Smart 모드: Whisper로 오디오 분석, 자동 페이지 타이밍 결정"""
        if not WHISPER_AVAILABLE:
            return {
                'status': 'error',
                'message': 'Whisper not installed. Smart mode requires openai-whisper package.'
            }

        if not audio_content:
            return {
                'status': 'error',
                'message': 'Smart mode requires an audio file.'
            }

        video_id = str(uuid.uuid4())[:8]
        temp_dir = tempfile.mkdtemp(prefix=f'pdf2mp4_smart_{video_id}_')

        try:
            print(f"[{video_id}] Starting Smart conversion for: {filename}")
            self.update_progress(video_id, 'init', 0, '변환 시작...', None)

            # 1. 오디오 파일 저장 및 전사
            audio_ext = os.path.splitext(audio_filename)[1].lower()
            audio_path = os.path.join(temp_dir, f'audio{audio_ext}')
            with open(audio_path, 'wb') as f:
                f.write(audio_content)

            self.update_progress(video_id, 'whisper', 10, '🎤 Whisper로 오디오 분석 중...', None)
            print(f"[{video_id}] Transcribing audio with Whisper...")
            result = self.whisper_model.transcribe(audio_path)
            transcript_text = result.get('text', '')
            segments = result.get('segments', [])
            print(f"[{video_id}] Transcription complete: {len(segments)} segments")
            self.update_progress(video_id, 'whisper_done', 30, f'✅ 오디오 분석 완료 ({len(segments)}개 세그먼트)', None)

            # 2. PDF를 이미지로 변환
            self.update_progress(video_id, 'pdf', 35, '📄 PDF를 이미지로 변환 중...', None)
            print(f"[{video_id}] Converting PDF to images...")
            images = convert_from_bytes(pdf_content, dpi=dpi)
            num_pages = len(images)
            print(f"[{video_id}] Extracted {num_pages} pages")
            self.update_progress(video_id, 'pdf_done', 40, f'✅ PDF 변환 완료 ({num_pages}페이지)', None)

            # 3. PDF 텍스트 추출 (키워드 매칭용)
            self.update_progress(video_id, 'text_extract', 42, '📝 PDF 텍스트 추출 중...', None)
            print(f"[{video_id}] Extracting text from PDF pages...")
            page_texts = self._extract_pdf_page_texts(pdf_content)

            # PyPDF2가 실패했거나 텍스트가 부족하면 OCR 사용
            total_text_len = sum(len(t) for t in page_texts)
            if total_text_len < 50 and PADDLEOCR_AVAILABLE:
                print(f"[{video_id}] PyPDF2 텍스트 부족 ({total_text_len} 문자), OCR 사용")
                self.update_progress(video_id, 'ocr', 43, '🔍 OCR로 텍스트 추출 중...', None)
                page_texts = self._extract_text_with_ocr(images, video_id)

            print(f"[{video_id}] Extracted text from {len(page_texts)} pages (총 {sum(len(t) for t in page_texts)} 문자)")

            # 로고 이미지 로드
            logo_img = None
            if logo_path and os.path.exists(logo_path):
                logo_img = Image.open(logo_path).convert('RGBA')
                print(f"[{video_id}] Logo loaded: {logo_path}")

            # 4. 이미지 리사이즈 (로고 합성 포함)
            resized_images = []
            for img in images:
                resized = self._resize_image(img, width, height, logo_img)
                resized_images.append(resized)

            # 5. 오디오 길이 확인
            result_probe = subprocess.run(
                ['ffprobe', '-v', 'error', '-show_entries', 'format=duration',
                 '-of', 'default=noprint_wrappers=1:nokey=1', audio_path],
                capture_output=True, text=True
            )
            total_duration = float(result_probe.stdout.strip()) if result_probe.stdout.strip() else 0

            # 6. 페이지 타이밍 계산 (키워드 기반)
            self.update_progress(video_id, 'timing', 45, '🔍 키워드 기반 타이밍 계산 중...', None)
            page_timings = self._calculate_smart_timings(
                segments, num_pages, total_duration, page_texts, video_id
            )
            print(f"[{video_id}] Page timings: {page_timings}")
            self.update_progress(video_id, 'timing_done', 50, '⏱️ 페이지 타이밍 계산 완료', None)

            # 6. 마지막 페이지 연장 (오디오 끝까지 + 마진)
            audio_margin = 2.0
            target_duration = total_duration + audio_margin
            if page_timings:
                last_end = page_timings[-1]['start'] + page_timings[-1]['duration']
                if last_end < target_duration:
                    page_timings[-1]['duration'] = target_duration - page_timings[-1]['start']

            # 7. 영상 출력
            output_filename = f"{os.path.splitext(filename)[0]}_smart_{video_id}.mp4"
            output_path = os.path.join(self.output_dir, output_filename)

            video_duration = page_timings[-1]['start'] + page_timings[-1]['duration'] if page_timings else 0
            eta_seconds = int(video_duration * 0.05)  # NVENC는 빠름
            self.update_progress(video_id, 'encoding', 55, f'🎬 NVENC 인코딩 중... (예상 {eta_seconds}초)', eta_seconds)

            print(f"[{video_id}] 🎬 NVENC GPU 가속 인코딩 시작")
            print(f"[{video_id}] 📊 영상 길이: {video_duration:.1f}초")

            success = self._encode_video_nvenc(
                resized_images, page_timings, audio_path, output_path, fps, width, height, video_id
            )

            if not success:
                raise Exception("NVENC encoding failed")

            # 6. 원본 PDF 저장 (YouTube Poster에서 재사용 가능)
            pdf_filename = f"{os.path.splitext(filename)[0]}_{video_id}.pdf"
            pdf_path = os.path.join(self.pdf_dir, pdf_filename)
            with open(pdf_path, 'wb') as f:
                f.write(pdf_content)
            print(f"[{video_id}] 📄 원본 PDF 저장: {pdf_filename}")

            self.update_progress(video_id, 'complete', 100, '✅ 변환 완료!', 0)

            video_info = {
                'id': video_id,
                'filename': output_filename,
                'original_pdf': filename,
                'pdf_path': pdf_path,
                'mode': 'smart',
                'page_count': num_pages,
                'duration': video_duration,
                'resolution': f'{width}x{height}',
                'transition': transition,
                'page_timings': page_timings,
                'transcript_preview': transcript_text[:500] if transcript_text else None,
                'created_at': datetime.utcnow().isoformat(),
                'file_path': output_path,
                'file_size': os.path.getsize(output_path)
            }

            print(f"[{video_id}] Smart conversion completed successfully")
            return {'status': 'success', 'video': video_info}

        except Exception as e:
            print(f"[{video_id}] Smart conversion failed: {str(e)}")
            import traceback
            traceback.print_exc()
            return {'status': 'error', 'message': str(e)}
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)

    def _calculate_smart_timings(
        self,
        segments: List[Dict],
        num_pages: int,
        total_duration: float,
        page_texts: Optional[List[str]] = None,
        video_id: str = ""
    ) -> List[Dict[str, float]]:
        """PDF 페이지 키워드와 Whisper 트랜스크립트를 매칭하여 페이지 타이밍 계산"""

        # 기본 폴백: 균등 분배
        if not segments or num_pages <= 0:
            page_duration = total_duration / max(num_pages, 1)
            return [
                {'start': i * page_duration, 'duration': page_duration}
                for i in range(num_pages)
            ]

        # 키워드 기반 매칭이 불가능한 경우 균등 분배
        if not page_texts or len(page_texts) != num_pages:
            print(f"[{video_id}] 키워드 매칭 불가 - 균등 분배 사용")
            return self._calculate_equal_timings(segments, num_pages, total_duration)

        print(f"[{video_id}] 🔍 키워드 기반 페이지 매칭 시작")

        # 디버그: 첫 3개 세그먼트 출력
        print(f"[{video_id}] 📝 Whisper 세그먼트 샘플:")
        for seg in segments[:5]:
            print(f"[{video_id}]   [{seg['start']:.1f}s] {seg.get('text', '')[:80]}")

        # 디버그: 각 페이지 키워드 출력
        print(f"[{video_id}] 📄 페이지별 키워드:")
        for i, pt in enumerate(page_texts[:3]):
            kws = self._extract_keywords_from_page(pt)[:10]
            print(f"[{video_id}]   페이지 {i+1}: {kws}")

        # 각 페이지별 매칭 시간 찾기
        page_start_times = [0.0]  # 첫 페이지는 항상 0초부터 시작
        last_match_time = 0.0
        min_page_duration = 3.0  # 최소 페이지 표시 시간 (초)

        # 이미 사용된 키워드 추적 (같은 키워드로 여러 페이지가 매칭되는 것 방지)
        used_keywords = set()

        for page_idx in range(1, num_pages):
            page_text = page_texts[page_idx]
            keywords = self._extract_keywords_from_page(page_text)

            if not keywords:
                # 키워드 없으면 이전 페이지 이후 적절한 시간에 배치
                page_start_times.append(None)  # 나중에 보간
                continue

            # 이미 사용된 키워드 제외
            available_keywords = [kw for kw in keywords if kw not in used_keywords]

            if not available_keywords:
                # 모든 키워드가 이미 사용됨, 보간으로 처리
                page_start_times.append(None)
                continue

            # 1차 시도: 다중 키워드 매칭 (더 정확한 방법)
            multi_match_time, matched_kws, match_count = self._find_best_segment_for_keywords(
                available_keywords[:20],  # 상위 20개 키워드 사용
                segments,
                search_start=last_match_time + min_page_duration,
                window_size=5  # 5개 연속 세그먼트 윈도우
            )

            if multi_match_time is not None and match_count >= 2:
                # 다중 키워드 매칭 성공
                print(f"[{video_id}]   페이지 {page_idx + 1}: {matched_kws[:3]} ({match_count}개 매칭) @ {multi_match_time:.1f}초")
                page_start_times.append(multi_match_time)
                last_match_time = multi_match_time
                # 매칭된 키워드들을 사용됨으로 표시
                for kw in matched_kws:
                    used_keywords.add(kw)
            else:
                # 2차 시도: 단일 키워드 매칭 (폴백)
                best_match_time = None
                matched_keyword = None

                for keyword in available_keywords[:15]:
                    match_time = self._find_keyword_in_transcript(
                        keyword, segments, search_start=last_match_time + min_page_duration
                    )
                    if match_time is not None:
                        if best_match_time is None or match_time < best_match_time:
                            best_match_time = match_time
                            matched_keyword = keyword

                if best_match_time is not None:
                    print(f"[{video_id}]   페이지 {page_idx + 1}: '{matched_keyword}' (단일) @ {best_match_time:.1f}초")
                    page_start_times.append(best_match_time)
                    last_match_time = best_match_time
                    used_keywords.add(matched_keyword)
                else:
                    page_start_times.append(None)  # 매칭 실패, 나중에 보간

        # 매칭되지 않은 페이지들 보간 처리
        page_start_times = self._interpolate_missing_times(
            page_start_times, total_duration, min_page_duration, video_id
        )

        # 타이밍 생성
        timings = []
        for i in range(num_pages):
            start_time = page_start_times[i]
            if i < num_pages - 1:
                end_time = page_start_times[i + 1]
            else:
                end_time = total_duration

            timings.append({
                'start': start_time,
                'duration': max(end_time - start_time, min_page_duration)
            })

        return timings

    def _calculate_equal_timings(
        self,
        segments: List[Dict],
        num_pages: int,
        total_duration: float
    ) -> List[Dict[str, float]]:
        """세그먼트 균등 분배 방식 (폴백)"""
        segment_count = len(segments)
        segments_per_page = max(1, segment_count // num_pages)

        timings = []
        for i in range(num_pages):
            start_idx = i * segments_per_page
            end_idx = min(start_idx + segments_per_page, segment_count)

            if i == num_pages - 1:
                end_idx = segment_count

            if start_idx < segment_count:
                start_time = segments[start_idx]['start']
                if end_idx < segment_count:
                    end_time = segments[end_idx]['start']
                else:
                    end_time = total_duration

                timings.append({
                    'start': start_time,
                    'duration': end_time - start_time
                })
            else:
                if timings:
                    last_end = timings[-1]['start'] + timings[-1]['duration']
                    remaining = total_duration - last_end
                    pages_left = num_pages - i
                    duration = remaining / pages_left
                    timings.append({
                        'start': last_end,
                        'duration': duration
                    })

        return timings

    def _interpolate_missing_times(
        self,
        page_start_times: List[Optional[float]],
        total_duration: float,
        min_duration: float,
        video_id: str
    ) -> List[float]:
        """매칭되지 않은 페이지 시간을 보간"""
        result = page_start_times.copy()
        num_pages = len(result)

        # None 값들을 선형 보간
        i = 0
        while i < num_pages:
            if result[i] is None:
                # None 시퀀스의 시작과 끝 찾기
                start_idx = i
                while i < num_pages and result[i] is None:
                    i += 1
                end_idx = i

                # 보간을 위한 시작/끝 시간 결정
                if start_idx == 0:
                    prev_time = 0.0
                else:
                    prev_time = result[start_idx - 1]

                if end_idx >= num_pages:
                    next_time = total_duration
                else:
                    next_time = result[end_idx]

                # 선형 보간
                gap_count = end_idx - start_idx + 1
                time_step = (next_time - prev_time) / gap_count

                for j in range(start_idx, end_idx):
                    result[j] = prev_time + time_step * (j - start_idx + 1)
                    print(f"[{video_id}]   페이지 {j + 1}: (보간) @ {result[j]:.1f}초")
            else:
                i += 1

        # 최소 간격 보장
        for i in range(1, num_pages):
            if result[i] < result[i-1] + min_duration:
                result[i] = result[i-1] + min_duration

        return result

    def get_video_list(self) -> List[Dict[str, Any]]:
        """생성된 영상 목록 조회"""
        videos = []
        if os.path.exists(self.output_dir):
            for f in os.listdir(self.output_dir):
                if f.endswith('.mp4'):
                    path = os.path.join(self.output_dir, f)
                    parts = f.rsplit('_', 1)
                    video_id = parts[1].replace('.mp4', '') if len(parts) > 1 else f.replace('.mp4', '')

                    videos.append({
                        'id': video_id,
                        'filename': f,
                        'file_path': path,
                        'file_size': os.path.getsize(path),
                        'created_at': datetime.fromtimestamp(os.path.getctime(path)).isoformat()
                    })

        return sorted(videos, key=lambda x: x['created_at'], reverse=True)

    def get_video_path(self, video_id: str) -> Optional[str]:
        if not os.path.exists(self.output_dir):
            return None
        for f in os.listdir(self.output_dir):
            if video_id in f and f.endswith('.mp4'):
                return os.path.join(self.output_dir, f)
        return None

    def get_video_info(self, video_id: str) -> Optional[Dict[str, Any]]:
        path = self.get_video_path(video_id)
        if path and os.path.exists(path):
            filename = os.path.basename(path)
            return {
                'id': video_id,
                'filename': filename,
                'file_path': path,
                'file_size': os.path.getsize(path),
                'created_at': datetime.fromtimestamp(os.path.getctime(path)).isoformat()
            }
        return None

    def delete_video(self, video_id: str) -> bool:
        path = self.get_video_path(video_id)
        if path and os.path.exists(path):
            os.remove(path)
            # 연관된 PDF도 삭제
            pdf_path = self.get_pdf_path(video_id)
            if pdf_path and os.path.exists(pdf_path):
                os.remove(pdf_path)
            return True
        return False

    def get_pdf_list(self) -> List[Dict[str, Any]]:
        """저장된 PDF 목록 조회"""
        pdfs = []
        if os.path.exists(self.pdf_dir):
            for f in os.listdir(self.pdf_dir):
                if f.endswith('.pdf'):
                    path = os.path.join(self.pdf_dir, f)
                    parts = f.rsplit('_', 1)
                    pdf_id = parts[1].replace('.pdf', '') if len(parts) > 1 else f.replace('.pdf', '')

                    pdfs.append({
                        'id': pdf_id,
                        'filename': f,
                        'original_name': parts[0] + '.pdf' if len(parts) > 1 else f,
                        'file_path': path,
                        'file_size': os.path.getsize(path),
                        'created_at': datetime.fromtimestamp(os.path.getctime(path)).isoformat()
                    })

        return sorted(pdfs, key=lambda x: x['created_at'], reverse=True)

    def get_pdf_path(self, pdf_id: str) -> Optional[str]:
        """PDF 파일 경로 조회"""
        if not os.path.exists(self.pdf_dir):
            return None
        for f in os.listdir(self.pdf_dir):
            if pdf_id in f and f.endswith('.pdf'):
                return os.path.join(self.pdf_dir, f)
        return None

    def get_pdf_info(self, pdf_id: str) -> Optional[Dict[str, Any]]:
        """PDF 파일 정보 조회"""
        path = self.get_pdf_path(pdf_id)
        if path and os.path.exists(path):
            filename = os.path.basename(path)
            parts = filename.rsplit('_', 1)
            return {
                'id': pdf_id,
                'filename': filename,
                'original_name': parts[0] + '.pdf' if len(parts) > 1 else filename,
                'file_path': path,
                'file_size': os.path.getsize(path),
                'created_at': datetime.fromtimestamp(os.path.getctime(path)).isoformat()
            }
        return None

    def get_transitions(self) -> List[str]:
        return self.TRANSITIONS.copy()

    def is_smart_mode_available(self) -> bool:
        return WHISPER_AVAILABLE
