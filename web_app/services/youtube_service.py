import os
import sys
import json
import shutil
import importlib.util
from fastapi.responses import FileResponse

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
        self.poster = YouTubeAutoPoster()
        self.base_v_dir = os.path.join(project_root, 'youtube_poster', 'v_source')

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
        # 임시 파일로 PDF 저장
        temp_pdf = os.path.join(self.base_v_dir, category, "temp_metadata_source.pdf")
        with open(temp_pdf, "wb") as f:
            f.write(pdf_content)

        # 템플릿 읽기
        desc_path = os.path.join(self.base_v_dir, category, f'desc_{lang}.md')
        if not os.path.exists(desc_path):
            desc_path = os.path.join(self.base_v_dir, category, 'desc.md')
        
        desc_template = ""
        if os.path.exists(desc_path):
            with open(desc_path, 'r', encoding='utf-8') as f:
                desc_template = f.read()

        metadata = self.poster.generate_youtube_metadata(temp_pdf, lang=lang, desc_template=desc_template)
        
        # 임시 파일 삭제
        if os.path.exists(temp_pdf):
            os.remove(temp_pdf)
            
        return metadata

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

            metadata = self.poster.generate_youtube_metadata(pdf_path, lang=lang, desc_template=desc_template)

            # 3. 자막 생성 (옵션)
            srt_path = None
            if gen_sub:
                srt_path = self.poster.generate_subtitles(video_path, lang=lang)

            # 4. 로고 및 자막 합성
            logo_path = self.get_logo_path(category)
            if not logo_path:
                raise Exception("Logo not found for category " + category)

            final_video_path = os.path.join(v_dir, f"final_{filename}")
            success = self.poster.add_logo_and_subs_to_video(video_path, logo_path, srt_path, final_video_path)
            
            if not success:
                raise Exception("Video processing failed")

            # 5. 유튜브 업로드
            video_id = self.poster.upload_video(final_video_path, metadata)
            
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

