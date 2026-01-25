"""
통합 콘텐츠 ID 관리 서비스

모든 파이프라인 산출물에 일관된 ID 체계를 적용합니다.

ID 형식: {prefix}_{YYYYMMDD}_{random_hex}
예: pipe_20260125_a1b2c3d4

디렉토리 구조:
├── generated_content/
│   ├── plan_{content_id}.json        # 기획안
│   ├── {content_id}_slide_01.png     # 슬라이드 이미지
│   └── web_images/
│       └── {content_id}_web_01.png   # 웹 참조 이미지
├── generated_pdfs/
│   └── {content_id}.pdf              # PDF
├── generated_audio/
│   ├── {content_id}.wav              # 오디오
│   └── {content_id}.json             # 오디오 메타 (script 포함)
├── generated_videos/
│   ├── {content_id}.mp4              # 비디오
│   ├── {content_id}_timing.json      # 타이밍/트랜스크립트
│   └── {content_id}_meta.json        # 비디오 메타
└── pipeline_results/
    └── {content_id}_pipeline.json    # 전체 파이프라인 결과
"""

import os
import json
import uuid
from datetime import datetime
from typing import Optional, Dict, Any, List


class ContentIDService:
    """통합 콘텐츠 ID 관리 서비스"""

    def __init__(self):
        self.base_dir = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
        self.content_dir = os.path.join(self.base_dir, 'generated_content')
        self.pdf_dir = os.path.join(self.base_dir, 'generated_pdfs')
        self.audio_dir = os.path.join(self.base_dir, 'generated_audio')
        self.video_dir = os.path.join(self.base_dir, 'generated_videos')
        self.pipeline_dir = os.path.join(self.base_dir, 'pipeline_results')

        # 디렉토리 생성
        for d in [self.content_dir, self.pdf_dir, self.audio_dir, self.video_dir, self.pipeline_dir]:
            os.makedirs(d, exist_ok=True)

    def generate_content_id(self, prefix: str = 'pipe') -> str:
        """
        새로운 콘텐츠 ID를 생성합니다.

        Args:
            prefix: ID 접두사 (기본값: 'pipe')

        Returns:
            형식: {prefix}_{YYYYMMDD}_{random_hex}
        """
        date_str = datetime.now().strftime('%Y%m%d')
        random_hex = uuid.uuid4().hex[:8]
        return f"{prefix}_{date_str}_{random_hex}"

    def get_paths(self, content_id: str) -> Dict[str, str]:
        """
        콘텐츠 ID에 해당하는 모든 파일 경로를 반환합니다.

        Args:
            content_id: 콘텐츠 ID

        Returns:
            Dict containing all possible file paths
        """
        return {
            # 기획안
            'plan': os.path.join(self.content_dir, f'plan_{content_id}.json'),

            # PDF
            'pdf': os.path.join(self.pdf_dir, f'{content_id}.pdf'),

            # 오디오
            'audio_wav': os.path.join(self.audio_dir, f'{content_id}.wav'),
            'audio_meta': os.path.join(self.audio_dir, f'{content_id}.json'),

            # 비디오
            'video': os.path.join(self.video_dir, f'{content_id}.mp4'),
            'video_timing': os.path.join(self.video_dir, f'{content_id}_timing.json'),
            'video_meta': os.path.join(self.video_dir, f'{content_id}_meta.json'),

            # 파이프라인 결과
            'pipeline': os.path.join(self.pipeline_dir, f'{content_id}_pipeline.json'),
        }

    def get_slide_image_path(self, content_id: str, slide_number: int) -> str:
        """슬라이드 이미지 경로를 반환합니다."""
        return os.path.join(self.content_dir, f'{content_id}_slide_{slide_number:02d}.png')

    def get_web_image_path(self, content_id: str, slide_number: int) -> str:
        """웹 참조 이미지 경로를 반환합니다."""
        web_images_dir = os.path.join(self.content_dir, 'web_images')
        os.makedirs(web_images_dir, exist_ok=True)
        return os.path.join(web_images_dir, f'{content_id}_web_{slide_number:02d}.png')

    def get_existing_files(self, content_id: str) -> Dict[str, bool]:
        """
        콘텐츠 ID에 해당하는 파일들의 존재 여부를 확인합니다.

        Returns:
            Dict with file type as key and existence as value
        """
        paths = self.get_paths(content_id)
        return {key: os.path.exists(path) for key, path in paths.items()}

    def get_transcript(self, content_id: str) -> Optional[str]:
        """
        콘텐츠 ID에 해당하는 트랜스크립트/대본을 반환합니다.

        우선순위:
        1. audio_meta.json의 script 필드 (가장 완전한 대본)
        2. video_timing.json의 transcript_segments
        3. video_timing.json의 page_texts (OCR)
        4. plan.json의 narrations 합침

        Returns:
            트랜스크립트 텍스트 또는 None
        """
        paths = self.get_paths(content_id)

        # 1. 오디오 메타데이터에서 대본 찾기
        if os.path.exists(paths['audio_meta']):
            try:
                with open(paths['audio_meta'], 'r', encoding='utf-8') as f:
                    audio_data = json.load(f)
                    script = audio_data.get('script', '')
                    if script and len(script) >= 100:
                        return script
            except Exception:
                pass

        # 2. 비디오 타이밍에서 Whisper 트랜스크립트 찾기
        if os.path.exists(paths['video_timing']):
            try:
                with open(paths['video_timing'], 'r', encoding='utf-8') as f:
                    timing_data = json.load(f)

                    # Whisper 세그먼트
                    segments = timing_data.get('transcript_segments', [])
                    if segments:
                        text = ' '.join([s.get('text', '').strip() for s in segments])
                        if text and len(text) >= 100:
                            return text

                    # OCR 텍스트
                    page_texts = timing_data.get('page_texts', [])
                    if page_texts:
                        text = '\n\n'.join([t.strip() for t in page_texts if t.strip()])
                        if text and len(text) >= 100:
                            return text
            except Exception:
                pass

        # 3. 기획안에서 나레이션 합치기
        if os.path.exists(paths['plan']):
            try:
                with open(paths['plan'], 'r', encoding='utf-8') as f:
                    plan_data = json.load(f)
                    slides = plan_data.get('slides', [])
                    narrations = [s.get('narration', '') for s in slides if s.get('narration')]
                    if narrations:
                        text = '\n\n'.join(narrations)
                        if len(text) >= 100:
                            return text
            except Exception:
                pass

        return None

    def get_content_info(self, content_id: str) -> Optional[Dict[str, Any]]:
        """
        콘텐츠 ID에 해당하는 모든 정보를 수집합니다.

        Returns:
            Dict containing all available content information
        """
        paths = self.get_paths(content_id)
        existing = self.get_existing_files(content_id)

        if not any(existing.values()):
            return None

        info = {
            'content_id': content_id,
            'files': existing,
            'paths': {k: v for k, v in paths.items() if existing.get(k)},
        }

        # 기획안 정보
        if existing.get('plan'):
            try:
                with open(paths['plan'], 'r', encoding='utf-8') as f:
                    plan = json.load(f)
                    info['title'] = plan.get('title', '')
                    info['category'] = plan.get('category', '')
                    info['language'] = plan.get('language', 'ko')
                    info['slide_count'] = len(plan.get('slides', []))
            except Exception:
                pass

        # 오디오 정보
        if existing.get('audio_meta'):
            try:
                with open(paths['audio_meta'], 'r', encoding='utf-8') as f:
                    audio = json.load(f)
                    info['audio_duration'] = audio.get('duration', 0)
                    info['voice'] = audio.get('voice', '')
            except Exception:
                pass

        # 비디오 정보
        if existing.get('video_meta'):
            try:
                with open(paths['video_meta'], 'r', encoding='utf-8') as f:
                    video = json.load(f)
                    info['video_category'] = video.get('category', '')
                    info['video_stage'] = video.get('stage', '')
            except Exception:
                pass

        # 파이프라인 결과
        if existing.get('pipeline'):
            try:
                with open(paths['pipeline'], 'r', encoding='utf-8') as f:
                    pipeline = json.load(f)
                    info['pipeline_status'] = pipeline.get('status', '')
                    info['youtube_url'] = pipeline.get('youtube_url', '')
                    info['completed_at'] = pipeline.get('completed_at', '')
            except Exception:
                pass

        return info

    def save_pipeline_result(self, content_id: str, result: Dict[str, Any]) -> str:
        """
        파이프라인 결과를 저장합니다.

        Returns:
            저장된 파일 경로
        """
        path = self.get_paths(content_id)['pipeline']
        result['content_id'] = content_id
        result['saved_at'] = datetime.now().isoformat()

        with open(path, 'w', encoding='utf-8') as f:
            json.dump(result, f, ensure_ascii=False, indent=2)

        return path

    def list_contents(self, prefix: str = None, limit: int = 50) -> List[Dict[str, Any]]:
        """
        저장된 콘텐츠 목록을 반환합니다.

        Args:
            prefix: 필터링할 접두사 (예: 'pipe', 'manual')
            limit: 최대 반환 개수

        Returns:
            List of content info dicts
        """
        contents = []
        seen_ids = set()

        # 파이프라인 결과 디렉토리에서 찾기
        if os.path.exists(self.pipeline_dir):
            for f in os.listdir(self.pipeline_dir):
                if f.endswith('_pipeline.json'):
                    content_id = f.replace('_pipeline.json', '')
                    if prefix and not content_id.startswith(prefix):
                        continue
                    if content_id not in seen_ids:
                        seen_ids.add(content_id)
                        info = self.get_content_info(content_id)
                        if info:
                            contents.append(info)

        # 기획안 디렉토리에서 찾기
        if os.path.exists(self.content_dir):
            for f in os.listdir(self.content_dir):
                if f.startswith('plan_') and f.endswith('.json'):
                    content_id = f.replace('plan_', '').replace('.json', '')
                    if prefix and not content_id.startswith(prefix):
                        continue
                    if content_id not in seen_ids:
                        seen_ids.add(content_id)
                        info = self.get_content_info(content_id)
                        if info:
                            contents.append(info)

        # 날짜순 정렬 (최신순)
        contents.sort(key=lambda x: x.get('content_id', ''), reverse=True)

        return contents[:limit]

    def delete_content(self, content_id: str) -> Dict[str, List[str]]:
        """
        콘텐츠 ID에 해당하는 모든 파일을 삭제합니다.

        Returns:
            Dict with 'deleted' and 'failed' lists
        """
        result = {'deleted': [], 'failed': []}
        paths = self.get_paths(content_id)

        # 기본 파일들 삭제
        for key, path in paths.items():
            if os.path.exists(path):
                try:
                    os.remove(path)
                    result['deleted'].append(path)
                except Exception as e:
                    result['failed'].append(f"{path}: {e}")

        # 슬라이드 이미지 삭제
        for i in range(1, 100):
            slide_path = self.get_slide_image_path(content_id, i)
            if os.path.exists(slide_path):
                try:
                    os.remove(slide_path)
                    result['deleted'].append(slide_path)
                except Exception as e:
                    result['failed'].append(f"{slide_path}: {e}")
            else:
                break

        # 웹 이미지 삭제
        for i in range(1, 100):
            web_path = self.get_web_image_path(content_id, i)
            if os.path.exists(web_path):
                try:
                    os.remove(web_path)
                    result['deleted'].append(web_path)
                except Exception as e:
                    result['failed'].append(f"{web_path}: {e}")
            else:
                break

        return result


# 싱글톤 인스턴스
content_id_service = ContentIDService()
