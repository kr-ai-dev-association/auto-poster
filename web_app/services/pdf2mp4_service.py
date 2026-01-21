"""
PDF to MP4 변환 서비스
PDF 파일을 MP4 영상으로 변환하는 기능을 제공합니다.
"""

import os
import tempfile
import shutil
import uuid
from datetime import datetime
from typing import Optional, List, Dict, Any
from dataclasses import dataclass

# PDF to Image
from pdf2image import convert_from_bytes

# Video processing (moviepy 2.x compatible)
from moviepy import (
    ImageClip,
    concatenate_videoclips,
    AudioFileClip,
    CompositeVideoClip
)
from PIL import Image
import numpy as np

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
    page_duration: float = 5.0          # 페이지당 표시 시간 (초)
    transition_duration: float = 0.5     # 전환 효과 시간 (초)
    transition_type: str = 'fade'        # 전환 효과 타입
    fps: int = 30                        # 프레임 레이트
    width: int = 1920                    # 출력 너비
    height: int = 1080                   # 출력 높이
    dpi: int = 200                       # PDF 렌더링 DPI


class PDF2MP4Service:
    """PDF를 MP4 영상으로 변환하는 서비스"""

    # 지원하는 전환 효과
    TRANSITIONS = ['fade', 'slide_left', 'slide_right', 'slide_up', 'slide_down', 'zoom', 'none']

    # 지원하는 오디오 포맷
    AUDIO_FORMATS = ['.mp3', '.wav', '.m4a', '.aac', '.ogg']

    def __init__(self):
        # 출력 디렉토리 설정
        self.output_dir = os.path.join(
            os.path.dirname(__file__),
            '..', '..', 'generated_videos'
        )
        os.makedirs(self.output_dir, exist_ok=True)

        # Whisper 모델 (지연 로딩)
        self._whisper_model = None

    @property
    def whisper_model(self):
        """Whisper 모델 지연 로딩"""
        if self._whisper_model is None and WHISPER_AVAILABLE:
            print("Loading Whisper model (base)...")
            self._whisper_model = whisper.load_model("base")
        return self._whisper_model

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
        auto_duration: bool = False
    ) -> Dict[str, Any]:
        """
        Basic 모드: 고정 시간 간격으로 PDF를 영상으로 변환

        Args:
            pdf_content: PDF 파일 바이트
            filename: 원본 파일명
            audio_content: 오디오 파일 바이트 (옵션)
            audio_filename: 오디오 파일명 (옵션)
            page_duration: 페이지당 표시 시간 (초)
            transition: 전환 효과 타입
            transition_duration: 전환 효과 시간 (초)
            width: 출력 너비
            height: 출력 높이
            fps: 프레임 레이트
            dpi: PDF 렌더링 DPI
            auto_duration: 오디오 길이에 맞춰 자동 조절

        Returns:
            변환 결과 딕셔너리
        """
        video_id = str(uuid.uuid4())[:8]
        temp_dir = tempfile.mkdtemp(prefix=f'pdf2mp4_{video_id}_')

        try:
            print(f"[{video_id}] Starting Basic conversion for: {filename}")

            # 1. PDF를 이미지로 변환
            print(f"[{video_id}] Converting PDF to images (DPI: {dpi})...")
            images = convert_from_bytes(
                pdf_content,
                dpi=dpi
            )
            print(f"[{video_id}] Extracted {len(images)} pages")

            # 2. 이미지 리사이즈
            resized_images = []
            for i, img in enumerate(images):
                resized = self._resize_image(img, width, height)
                resized_images.append(resized)

            # 3. 오디오 처리 (있는 경우)
            audio_clip = None
            if audio_content:
                audio_ext = os.path.splitext(audio_filename or '.mp3')[1].lower()
                audio_path = os.path.join(temp_dir, f'audio{audio_ext}')
                with open(audio_path, 'wb') as f:
                    f.write(audio_content)
                audio_clip = AudioFileClip(audio_path)
                print(f"[{video_id}] Audio loaded: {audio_clip.duration:.2f}s")

                # 오디오 길이에 맞춰 페이지 시간 자동 계산
                if auto_duration:
                    page_duration = self._calculate_page_duration(
                        audio_clip.duration,
                        len(images),
                        transition_duration
                    )
                    print(f"[{video_id}] Auto page duration: {page_duration:.2f}s")

            # 4. 비디오 클립 생성
            if transition != 'none' and transition_duration > 0:
                final_clip = self._create_video_with_transitions(
                    resized_images,
                    page_duration,
                    transition_duration,
                    transition,
                    width,
                    height
                )
            else:
                final_clip = self._create_video_simple(resized_images, page_duration)

            # 5. 오디오 추가
            if audio_clip:
                audio_margin = 2.0  # 오디오 끝 부분 잘림 방지를 위한 마진
                target_audio_duration = audio_clip.duration + audio_margin

                # 비디오와 오디오 길이 맞추기
                if audio_clip.duration < final_clip.duration:
                    # 오디오가 짧으면 비디오를 오디오 길이에 맞춤
                    final_clip = final_clip.subclip(0, audio_clip.duration)
                elif target_audio_duration > final_clip.duration:
                    # 오디오 + 마진이 비디오보다 길면 마지막 이미지로 비디오 연장 (잘림 방지)
                    print(f"[{video_id}] Extending video from {final_clip.duration:.2f}s to {target_audio_duration:.2f}s (audio: {audio_clip.duration:.2f}s + {audio_margin}s margin)")
                    extension_duration = target_audio_duration - final_clip.duration
                    last_img = resized_images[-1]
                    extension_clip = ImageClip(last_img, duration=extension_duration).with_start(final_clip.duration)
                    final_clip = CompositeVideoClip([final_clip, extension_clip])
                final_clip = final_clip.with_audio(audio_clip)

            # 6. 영상 출력
            output_filename = f"{os.path.splitext(filename)[0]}_{video_id}.mp4"
            output_path = os.path.join(self.output_dir, output_filename)

            print(f"[{video_id}] Rendering video to: {output_path}")

            # duration 저장 (close 전에)
            video_duration = final_clip.duration

            final_clip.write_videofile(
                output_path,
                fps=fps,
                codec='libx264',
                audio_codec='aac',
                verbose=False,
                logger=None
            )

            # 7. 리소스 정리
            final_clip.close()
            if audio_clip:
                audio_clip.close()

            # 8. 결과 반환
            video_info = {
                'id': video_id,
                'filename': output_filename,
                'original_pdf': filename,
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
            return {
                'status': 'success',
                'video': video_info
            }

        except Exception as e:
            print(f"[{video_id}] Conversion failed: {str(e)}")
            import traceback
            traceback.print_exc()
            return {
                'status': 'error',
                'message': str(e)
            }
        finally:
            # 임시 디렉토리 정리
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
        dpi: int = 200
    ) -> Dict[str, Any]:
        """
        Smart 모드: Whisper로 오디오 분석, 자동 페이지 타이밍 결정

        Args:
            pdf_content: PDF 파일 바이트
            filename: 원본 파일명
            audio_content: 오디오 파일 바이트 (필수)
            audio_filename: 오디오 파일명
            transition: 전환 효과 타입
            transition_duration: 전환 효과 시간 (초)
            width: 출력 너비
            height: 출력 높이
            fps: 프레임 레이트
            dpi: PDF 렌더링 DPI

        Returns:
            변환 결과 딕셔너리
        """
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

            # 1. 오디오 파일 저장 및 전사
            audio_ext = os.path.splitext(audio_filename)[1].lower()
            audio_path = os.path.join(temp_dir, f'audio{audio_ext}')
            with open(audio_path, 'wb') as f:
                f.write(audio_content)

            print(f"[{video_id}] Transcribing audio with Whisper...")
            result = self.whisper_model.transcribe(audio_path)
            transcript_text = result.get('text', '')
            segments = result.get('segments', [])
            print(f"[{video_id}] Transcription complete: {len(segments)} segments")

            # 2. PDF를 이미지로 변환
            print(f"[{video_id}] Converting PDF to images...")
            images = convert_from_bytes(pdf_content, dpi=dpi)
            num_pages = len(images)
            print(f"[{video_id}] Extracted {num_pages} pages")

            # 3. 이미지 리사이즈
            resized_images = []
            for img in images:
                resized = self._resize_image(img, width, height)
                resized_images.append(resized)

            # 4. 오디오 클립 로드
            audio_clip = AudioFileClip(audio_path)
            total_duration = audio_clip.duration

            # 5. 페이지 타이밍 계산 (세그먼트 기반)
            page_timings = self._calculate_smart_timings(
                segments,
                num_pages,
                total_duration
            )
            print(f"[{video_id}] Page timings: {page_timings}")

            # 6. 비디오 클립 생성 (타이밍 기반)
            final_clip = self._create_video_with_timings(
                resized_images,
                page_timings,
                transition,
                transition_duration,
                width,
                height
            )

            # 7. 비디오 길이를 오디오 길이에 맞춤 (잘림 방지, 2초 마진)
            audio_margin = 2.0  # 오디오 끝 부분 잘림 방지를 위한 마진
            target_duration = total_duration + audio_margin

            if final_clip.duration < target_duration:
                # 비디오가 목표 길이보다 짧으면 마지막 프레임을 연장
                print(f"[{video_id}] Extending video from {final_clip.duration:.2f}s to {target_duration:.2f}s (audio: {total_duration:.2f}s + {audio_margin}s margin)")
                # 마지막 이미지로 나머지 시간 채우기
                last_img = resized_images[-1]
                extension_duration = target_duration - final_clip.duration
                extension_clip = ImageClip(last_img, duration=extension_duration).with_start(final_clip.duration)
                final_clip = CompositeVideoClip([final_clip, extension_clip])

            # 8. 오디오 추가
            final_clip = final_clip.with_audio(audio_clip)

            # 8. 영상 출력
            output_filename = f"{os.path.splitext(filename)[0]}_smart_{video_id}.mp4"
            output_path = os.path.join(self.output_dir, output_filename)

            print(f"[{video_id}] Rendering video to: {output_path}")
            final_clip.write_videofile(
                output_path,
                fps=fps,
                codec='libx264',
                audio_codec='aac',
                verbose=False,
                logger=None
            )

            # 9. 리소스 정리
            final_clip.close()
            audio_clip.close()

            # 10. 결과 반환
            video_info = {
                'id': video_id,
                'filename': output_filename,
                'original_pdf': filename,
                'mode': 'smart',
                'page_count': num_pages,
                'duration': total_duration,
                'resolution': f'{width}x{height}',
                'transition': transition,
                'page_timings': page_timings,
                'transcript_preview': transcript_text[:500] if transcript_text else None,
                'created_at': datetime.utcnow().isoformat(),
                'file_path': output_path,
                'file_size': os.path.getsize(output_path)
            }

            print(f"[{video_id}] Smart conversion completed successfully")
            return {
                'status': 'success',
                'video': video_info
            }

        except Exception as e:
            print(f"[{video_id}] Smart conversion failed: {str(e)}")
            import traceback
            traceback.print_exc()
            return {
                'status': 'error',
                'message': str(e)
            }
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)

    def _resize_image(self, img: Image.Image, width: int, height: int) -> np.ndarray:
        """이미지를 지정된 크기로 리사이즈 (종횡비 유지, 검은 배경)"""
        # 원본 크기
        orig_width, orig_height = img.size

        # 종횡비 계산
        ratio = min(width / orig_width, height / orig_height)
        new_width = int(orig_width * ratio)
        new_height = int(orig_height * ratio)

        # 리사이즈
        img_resized = img.resize((new_width, new_height), Image.Resampling.LANCZOS)

        # 검은 배경에 중앙 정렬
        background = Image.new('RGB', (width, height), (0, 0, 0))
        offset = ((width - new_width) // 2, (height - new_height) // 2)
        background.paste(img_resized, offset)

        return np.array(background)

    def _create_video_simple(
        self,
        images: List[np.ndarray],
        page_duration: float
    ) -> CompositeVideoClip:
        """전환 효과 없이 단순 영상 생성"""
        clips = []
        for img in images:
            clip = ImageClip(img, duration=page_duration)
            clips.append(clip)
        return concatenate_videoclips(clips, method="compose")

    def _create_video_with_transitions(
        self,
        images: List[np.ndarray],
        page_duration: float,
        transition_duration: float,
        transition_type: str,
        width: int,
        height: int
    ) -> CompositeVideoClip:
        """전환 효과를 적용한 영상 생성 (moviepy 2.x 호환)"""
        clips = []

        for i, img in enumerate(images):
            clip = ImageClip(img, duration=page_duration)

            # 시작 시간 설정 (전환 겹침 고려)
            if i > 0:
                start_time = i * (page_duration - transition_duration)
                clip = clip.with_start(start_time)

            clips.append(clip)

        # moviepy 2.x에서는 crossfade를 다르게 처리해야 함
        # 단순 합성으로 처리 (오버랩 방식)
        return CompositeVideoClip(clips)

    def _create_video_with_timings(
        self,
        images: List[np.ndarray],
        timings: List[Dict[str, float]],
        transition: str,
        transition_duration: float,
        width: int,
        height: int
    ) -> CompositeVideoClip:
        """타이밍 기반 영상 생성 (Smart 모드용)"""
        clips = []

        for i, (img, timing) in enumerate(zip(images, timings)):
            start_time = timing['start']
            duration = timing['duration']

            clip = ImageClip(img, duration=duration).with_start(start_time)

            # 전환 효과 적용 (moviepy 2.x에서는 crossfadein이 다르게 동작)
            # 단순화를 위해 전환 효과는 생략

            clips.append(clip)

        return CompositeVideoClip(clips)

    def _apply_zoom_in(
        self,
        clip,
        duration: float,
        width: int,
        height: int
    ):
        """줌 인 전환 효과 적용"""
        def zoom_effect(get_frame, t):
            frame = get_frame(t)
            if t < duration:
                # 1.2배에서 1.0배로 줌 아웃
                scale = 1.2 - (0.2 * t / duration)
                h, w = frame.shape[:2]
                new_h, new_w = int(h * scale), int(w * scale)

                # 크기 조정
                from PIL import Image
                img = Image.fromarray(frame)
                img = img.resize((new_w, new_h), Image.Resampling.LANCZOS)

                # 중앙 크롭
                left = (new_w - w) // 2
                top = (new_h - h) // 2
                img = img.crop((left, top, left + w, top + h))

                return np.array(img)
            return frame

        return clip.fl(zoom_effect)

    def _calculate_page_duration(
        self,
        audio_duration: float,
        num_pages: int,
        transition_duration: float
    ) -> float:
        """오디오 길이에 맞춰 페이지 시간 계산"""
        # 전환 겹침을 고려한 계산
        # 총 시간 = n * page_duration - (n-1) * transition_duration
        # page_duration = (총 시간 + (n-1) * transition_duration) / n
        if num_pages <= 1:
            return audio_duration

        page_duration = (audio_duration + (num_pages - 1) * transition_duration) / num_pages
        return max(1.0, page_duration)  # 최소 1초

    def _calculate_smart_timings(
        self,
        segments: List[Dict],
        num_pages: int,
        total_duration: float
    ) -> List[Dict[str, float]]:
        """Whisper 세그먼트를 기반으로 페이지 타이밍 계산"""
        if not segments or num_pages <= 0:
            # 세그먼트가 없으면 균등 분배
            page_duration = total_duration / num_pages
            return [
                {'start': i * page_duration, 'duration': page_duration}
                for i in range(num_pages)
            ]

        # 간단한 방식: 세그먼트를 페이지 수로 나누어 배분
        segment_count = len(segments)
        segments_per_page = max(1, segment_count // num_pages)

        timings = []
        for i in range(num_pages):
            start_idx = i * segments_per_page
            end_idx = min(start_idx + segments_per_page, segment_count)

            if i == num_pages - 1:
                # 마지막 페이지는 남은 모든 세그먼트 포함
                end_idx = segment_count

            if start_idx < segment_count:
                start_time = segments[start_idx]['start']
                if end_idx < segment_count:
                    end_time = segments[end_idx]['start']
                else:
                    # 마지막 페이지: 오디오 전체 길이까지 연장 (마진 추가)
                    end_time = total_duration

                timings.append({
                    'start': start_time,
                    'duration': end_time - start_time
                })
            else:
                # 세그먼트가 부족한 경우
                if timings:
                    last_end = timings[-1]['start'] + timings[-1]['duration']
                    remaining = total_duration - last_end
                    pages_left = num_pages - i
                    duration = remaining / pages_left
                    timings.append({
                        'start': last_end,
                        'duration': duration
                    })

        # 마지막 페이지의 duration을 오디오 끝까지 연장 (잘림 방지)
        if timings:
            last_timing = timings[-1]
            expected_end = last_timing['start'] + last_timing['duration']
            if expected_end < total_duration:
                # 마지막 페이지를 오디오 전체 길이까지 연장
                timings[-1]['duration'] = total_duration - last_timing['start']

        return timings

    def get_video_list(self) -> List[Dict[str, Any]]:
        """생성된 영상 목록 조회"""
        videos = []
        if os.path.exists(self.output_dir):
            for f in os.listdir(self.output_dir):
                if f.endswith('.mp4'):
                    path = os.path.join(self.output_dir, f)
                    # 파일명에서 ID 추출 (예: filename_abc12345.mp4)
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
        """영상 파일 경로 조회"""
        if not os.path.exists(self.output_dir):
            return None

        for f in os.listdir(self.output_dir):
            if video_id in f and f.endswith('.mp4'):
                return os.path.join(self.output_dir, f)
        return None

    def get_video_info(self, video_id: str) -> Optional[Dict[str, Any]]:
        """영상 정보 조회"""
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
        """영상 삭제"""
        path = self.get_video_path(video_id)
        if path and os.path.exists(path):
            os.remove(path)
            return True
        return False

    def get_transitions(self) -> List[str]:
        """지원하는 전환 효과 목록"""
        return self.TRANSITIONS.copy()

    def is_smart_mode_available(self) -> bool:
        """Smart 모드 사용 가능 여부"""
        return WHISPER_AVAILABLE
