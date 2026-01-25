import os
import json
import logging
import asyncio
import uuid
from typing import Optional, Dict, Any, Callable
from datetime import datetime
from .content_generator_service import content_generator
from .audio_generator_service import audio_generator
from .pdf2mp4_service import PDF2MP4Service
from .youtube_service import YouTubeService
from .slack_service import slack_service
from .content_id_service import content_id_service

logger = logging.getLogger(__name__)


class AutoPipelineService:
    """
    전체 자동화 파이프라인 서비스
    기획 -> 이미지 생성 -> PDF 생성 -> 대본 생성 -> 오디오 생성 -> 비디오 생성 -> YouTube 업로드
    """

    def __init__(self):
        self.pipelines: Dict[str, Dict[str, Any]] = {}  # 진행 중인 파이프라인 상태 추적

    def get_pipeline_status(self, pipeline_id: str) -> Optional[Dict[str, Any]]:
        """파이프라인 상태를 조회합니다."""
        return self.pipelines.get(pipeline_id)

    def list_pipelines(self) -> list:
        """모든 파이프라인 목록을 반환합니다."""
        return list(self.pipelines.values())

    async def run_full_pipeline(
        self,
        topic: str,
        category: str = 'educational',
        target_slides: int = 15,
        language: str = 'ko',
        additional_instructions: str = '',
        voice: str = 'Kore',
        script_style: str = 'educational',
        youtube_privacy: str = 'private',
        progress_callback: Callable = None,
        user_id: int = None
    ) -> Dict[str, Any]:
        """
        전체 파이프라인을 실행합니다.

        Args:
            topic: 콘텐츠 주제
            category: 카테고리
            target_slides: 목표 슬라이드 수
            language: 언어 (ko/en)
            additional_instructions: 추가 지시사항
            voice: TTS 음성
            script_style: 대본 스타일
            youtube_privacy: YouTube 공개 설정
            progress_callback: 진행 상황 콜백
            user_id: 사용자 ID

        Returns:
            Dict containing pipeline result
        """
        # 통합 콘텐츠 ID 생성 (전체 파이프라인에서 일관되게 사용)
        content_id = content_id_service.generate_content_id('pipe')
        pipeline_id = content_id  # pipeline_id도 content_id와 동일하게 사용
        start_time = datetime.now()

        # 파이프라인 상태 초기화
        self.pipelines[pipeline_id] = {
            'id': pipeline_id,
            'content_id': content_id,  # 통합 ID 저장
            'topic': topic,
            'category': category,
            'language': language,
            'status': 'running',
            'current_step': 'initializing',
            'progress': 0,
            'steps_completed': [],
            'error': None,
            'result': {},
            'started_at': start_time.isoformat(),
            'user_id': user_id
        }

        def update_status(step: str, progress: int, message: str = ''):
            self.pipelines[pipeline_id]['current_step'] = step
            self.pipelines[pipeline_id]['progress'] = progress
            if message:
                self.pipelines[pipeline_id]['message'] = message
            if progress_callback:
                progress_callback(pipeline_id, step, progress, message)

        try:
            # ===== Step 1: 기획안 생성 =====
            update_status('plan_generation', 5, '기획안 생성 중...')
            logger.info(f"[Pipeline {pipeline_id}] Step 1: Generating content plan")

            plan_result = await content_generator.generate_content_plan(
                topic=topic,
                category=category,
                target_slides=target_slides,
                language=language,
                additional_instructions=additional_instructions,
                content_id=content_id  # 통합 ID 전달
            )

            if plan_result.get('status') != 'success':
                raise Exception(f"Plan generation failed: {plan_result.get('message')}")

            plan_id = plan_result['plan_id']
            plan = plan_result['plan']
            title = plan.get('title', topic)

            self.pipelines[pipeline_id]['result']['plan_id'] = plan_id
            self.pipelines[pipeline_id]['result']['title'] = title
            self.pipelines[pipeline_id]['steps_completed'].append('plan_generation')

            # ===== Step 2: 이미지 생성 =====
            update_status('image_generation', 15, '슬라이드 이미지 생성 중...')
            logger.info(f"[Pipeline {pipeline_id}] Step 2: Generating slide images")

            def image_progress(current, total, msg):
                base_progress = 15
                step_progress = int((current / total) * 30)  # 15-45%
                update_status('image_generation', base_progress + step_progress, f'이미지 생성 중 ({current}/{total})')

            image_result = await content_generator.generate_all_images(
                plan_id=plan_id,
                progress_callback=image_progress,
                use_web_images=True
            )

            if image_result.get('status') == 'error':
                raise Exception(f"Image generation failed: {image_result.get('message')}")

            self.pipelines[pipeline_id]['result']['images'] = {
                'total': image_result.get('total'),
                'success': image_result.get('success'),
                'web_references': image_result.get('web_references_used', 0)
            }
            self.pipelines[pipeline_id]['steps_completed'].append('image_generation')

            # ===== Step 3: PDF 생성 =====
            update_status('pdf_generation', 50, 'PDF 생성 중...')
            logger.info(f"[Pipeline {pipeline_id}] Step 3: Creating PDF")

            pdf_result = await content_generator.create_pdf_from_plan(
                plan_id=plan_id,
                title=title
            )

            if pdf_result.get('status') != 'success':
                raise Exception(f"PDF generation failed: {pdf_result.get('message')}")

            pdf_path = pdf_result['pdf_path']
            pdf_filename = pdf_result['filename']

            self.pipelines[pipeline_id]['result']['pdf'] = {
                'filename': pdf_filename,
                'path': pdf_path
            }
            self.pipelines[pipeline_id]['steps_completed'].append('pdf_generation')

            # ===== Step 4: 대본 생성 =====
            update_status('script_generation', 55, '대본 생성 중...')
            logger.info(f"[Pipeline {pipeline_id}] Step 4: Generating script")

            # 기획안의 narration들을 합쳐서 대본으로 사용
            slides = plan.get('slides', [])
            narrations = [slide.get('narration', '') for slide in slides]
            full_script = '\n\n'.join(narrations)

            self.pipelines[pipeline_id]['result']['script'] = {
                'length': len(full_script),
                'slide_count': len(narrations)
            }
            self.pipelines[pipeline_id]['steps_completed'].append('script_generation')

            # ===== Step 5: 오디오 생성 =====
            update_status('audio_generation', 60, 'TTS 오디오 생성 중...')
            logger.info(f"[Pipeline {pipeline_id}] Step 5: Generating audio")

            audio_result = await audio_generator.generate_audio_from_script(
                script=full_script,
                voice=voice,
                language=language,
                content_id=content_id  # 통합 ID 전달 (파일명으로 사용됨)
            )

            if audio_result.get('status') != 'success':
                raise Exception(f"Audio generation failed: {audio_result.get('message')}")

            audio_path = audio_result['audio_path']
            audio_duration = audio_result.get('duration', 0)

            self.pipelines[pipeline_id]['result']['audio'] = {
                'path': audio_path,
                'duration': audio_duration
            }
            self.pipelines[pipeline_id]['steps_completed'].append('audio_generation')

            # ===== Step 6: 비디오 생성 =====
            update_status('video_generation', 70, '비디오 생성 중...')
            logger.info(f"[Pipeline {pipeline_id}] Step 6: Generating video")

            # PDF와 오디오 파일 읽기
            with open(pdf_path, 'rb') as f:
                pdf_content = f.read()
            with open(audio_path, 'rb') as f:
                audio_content = f.read()

            # 서비스 인스턴스 생성
            pdf2mp4_svc = PDF2MP4Service()
            youtube_svc = YouTubeService()

            # 로고 경로 설정
            logo_path = youtube_svc.get_logo_path(category)

            # Smart 모드로 비디오 생성 (통합 ID 전달)
            video_result = await pdf2mp4_svc.convert_smart(
                pdf_content=pdf_content,
                filename=pdf_filename,
                audio_content=audio_content,
                audio_filename=os.path.basename(audio_path),
                logo_path=logo_path,
                category=category,
                created_by=str(user_id) if user_id else '',
                content_id=content_id  # 통합 ID 전달
            )

            if video_result.get('status') != 'success':
                raise Exception(f"Video generation failed: {video_result.get('message')}")

            video_path = video_result.get('output_path')
            video_id = video_result.get('video_id')
            video_filename = os.path.basename(video_path) if video_path else f"auto_{plan_id}.mp4"

            self.pipelines[pipeline_id]['result']['video'] = {
                'id': video_id,
                'path': video_path,
                'filename': video_filename,
                'duration': video_result.get('duration')
            }
            self.pipelines[pipeline_id]['steps_completed'].append('video_generation')

            # ===== Step 7: YouTube 업로드 =====
            update_status('youtube_upload', 85, 'YouTube 업로드 중...')
            logger.info(f"[Pipeline {pipeline_id}] Step 7: Uploading to YouTube")

            youtube_url = None
            try:
                # 비디오 파일 읽기
                with open(video_path, 'rb') as f:
                    video_content = f.read()

                # YouTube 업로드 (process_and_upload 사용)
                # 대본(full_script)을 전달하여 메타데이터 생성 시 활용
                upload_id = uuid.uuid4().hex[:8]
                await youtube_svc.process_and_upload(
                    video_content=video_content,
                    filename=video_filename,
                    pdf_content=pdf_content,  # 썸네일 생성용
                    category=category,
                    lang=language,
                    use_thumbnail=True,
                    upload_id=upload_id,
                    text_content=full_script  # 대본을 메타데이터 생성에 활용
                )

                # 업로드 결과 폴링
                for _ in range(120):  # 최대 2분 대기
                    await asyncio.sleep(1)
                    progress = YouTubeService.get_upload_progress(upload_id)
                    if progress:
                        if progress.get('step') == 'complete':
                            yt_video_id = progress.get('video_id')
                            youtube_url = f"https://www.youtube.com/watch?v={yt_video_id}"
                            self.pipelines[pipeline_id]['result']['youtube'] = {
                                'video_id': yt_video_id,
                                'url': youtube_url
                            }
                            self.pipelines[pipeline_id]['steps_completed'].append('youtube_upload')
                            break
                        elif progress.get('step') == 'error':
                            raise Exception(progress.get('message', 'Upload failed'))

                if not youtube_url:
                    logger.warning("YouTube upload timed out")
                    self.pipelines[pipeline_id]['result']['youtube'] = {
                        'error': 'Upload timed out'
                    }

            except Exception as yt_error:
                logger.warning(f"YouTube upload error: {yt_error}")
                self.pipelines[pipeline_id]['result']['youtube'] = {
                    'error': str(yt_error)
                }

            # ===== 완료 =====
            end_time = datetime.now()
            duration = str(end_time - start_time).split('.')[0]  # 초 단위까지만

            update_status('completed', 100, '파이프라인 완료!')
            self.pipelines[pipeline_id]['status'] = 'completed'
            self.pipelines[pipeline_id]['completed_at'] = end_time.isoformat()
            self.pipelines[pipeline_id]['duration'] = duration

            logger.info(f"[Pipeline {pipeline_id}] Completed successfully in {duration}")

            # 파이프라인 결과를 파일로 저장 (통합 ID로 추적 가능)
            pipeline_result = {
                'status': 'success',
                'content_id': content_id,
                'pipeline_id': pipeline_id,
                'title': title,
                'topic': topic,
                'category': category,
                'language': language,
                'youtube_url': youtube_url,
                'duration': duration,
                'steps_completed': self.pipelines[pipeline_id]['steps_completed'],
                'result': self.pipelines[pipeline_id]['result'],
                'started_at': start_time.isoformat(),
                'completed_at': end_time.isoformat()
            }
            content_id_service.save_pipeline_result(content_id, pipeline_result)

            # Slack 알림 전송
            await slack_service.notify_pipeline_complete(
                title=title,
                youtube_url=youtube_url,
                plan_id=plan_id,
                video_filename=video_filename,
                duration=duration,
                category=category
            )

            return {
                'status': 'success',
                'content_id': content_id,  # 통합 ID 반환
                'pipeline_id': pipeline_id,
                'title': title,
                'plan_id': plan_id,
                'youtube_url': youtube_url,
                'duration': duration,
                'steps_completed': self.pipelines[pipeline_id]['steps_completed']
            }

        except Exception as e:
            end_time = datetime.now()
            duration = str(end_time - start_time).split('.')[0]

            error_msg = str(e)
            logger.error(f"[Pipeline {pipeline_id}] Failed: {error_msg}")

            self.pipelines[pipeline_id]['status'] = 'failed'
            self.pipelines[pipeline_id]['error'] = error_msg
            self.pipelines[pipeline_id]['completed_at'] = end_time.isoformat()
            self.pipelines[pipeline_id]['duration'] = duration

            # 실패 알림 전송
            await slack_service.notify_pipeline_complete(
                title=topic,
                plan_id=self.pipelines[pipeline_id]['result'].get('plan_id'),
                duration=duration,
                category=category,
                error=error_msg
            )

            # 실패 결과도 저장
            error_result = {
                'status': 'error',
                'content_id': content_id,
                'pipeline_id': pipeline_id,
                'topic': topic,
                'category': category,
                'error': error_msg,
                'steps_completed': self.pipelines[pipeline_id]['steps_completed'],
                'started_at': start_time.isoformat(),
                'completed_at': end_time.isoformat(),
                'duration': duration
            }
            content_id_service.save_pipeline_result(content_id, error_result)

            return {
                'status': 'error',
                'content_id': content_id,  # 통합 ID 반환
                'pipeline_id': pipeline_id,
                'message': error_msg,
                'steps_completed': self.pipelines[pipeline_id]['steps_completed'],
                'duration': duration
            }

    def _get_youtube_category_id(self, category: str) -> str:
        """카테고리를 YouTube 카테고리 ID로 변환합니다."""
        category_map = {
            'educational': '27',  # Education
            'entertainment': '24',  # Entertainment
            'tech': '28',  # Science & Technology
            'gaming': '20',  # Gaming
            'lifestyle': '22',  # People & Blogs
            'news': '25',  # News & Politics
            'beauty': '26',  # Howto & Style
        }
        return category_map.get(category, '22')  # 기본값: People & Blogs

    def cancel_pipeline(self, pipeline_id: str) -> bool:
        """파이프라인을 취소합니다."""
        if pipeline_id in self.pipelines:
            if self.pipelines[pipeline_id]['status'] == 'running':
                self.pipelines[pipeline_id]['status'] = 'cancelled'
                self.pipelines[pipeline_id]['error'] = 'Cancelled by user'
                return True
        return False


# 싱글톤 인스턴스
auto_pipeline = AutoPipelineService()
