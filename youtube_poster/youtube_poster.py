import os
import sys
import json
import pickle
import subprocess
import re
import shutil
import time
import stat
import tempfile
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from google.genai import types
from dotenv import load_dotenv

# Add project root to path to import from core
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from core.summarizer import GeminiSummarizer

load_dotenv()

class YouTubeAutoPoster:
    def __init__(self, client_secrets_file='client_secrets.json'):
        # 먼저 secrets/ 디렉토리 확인, 없으면 현재 디렉토리
        secrets_path = os.path.join(os.path.dirname(__file__), '..', 'secrets', client_secrets_file)
        if os.path.exists(secrets_path):
            self.client_secrets_file = secrets_path
        else:
            self.client_secrets_file = os.path.join(os.path.dirname(__file__), client_secrets_file)
        self.token_file = os.path.join(os.path.dirname(__file__), 'token.pickle')
        self.scopes = ['https://www.googleapis.com/auth/youtube.upload']
        self.youtube = self._get_authenticated_service()
        self.summarizer = GeminiSummarizer()

    def _get_client_secrets_path(self):
        """
        DB에서 암호화된 client_secrets.json 가져오기 또는 로컬 파일 사용
        """
        environment = os.getenv("ENVIRONMENT", "development").lower()
        
        try:
            # 1. DB에서 복호화 시도
            sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'web_app'))
            from services.crypto_service import CryptoService
            
            secrets_content = CryptoService.get_decrypted_file_from_db('client_secrets.json')
            
            # 임시 파일로 저장 (OAuth flow가 파일 경로를 요구함)
            temp_secrets_path = os.path.join(tempfile.gettempdir(), 'client_secrets.json')
            with open(temp_secrets_path, 'wb') as f:
                f.write(secrets_content)
            
            print(f"✅ [{environment.upper()}] YouTube client_secrets loaded from encrypted DB")
            return temp_secrets_path
            
        except (FileNotFoundError, ImportError) as e:
            # 2. 로컬 파일 폴백 (개발 환경만)
            if environment == "production":
                print(f"❌ [PRODUCTION] {str(e) if isinstance(e, FileNotFoundError) else 'client_secrets.json not in DB'}")
                print("💡 프로덕션에서는 /admin/secure-files에서 반드시 업로드해야 합니다.")
                sys.exit(1)
            
            if os.path.exists(self.client_secrets_file):
                print(f"⚠️ [{environment.upper()}] No encrypted YouTube secrets in DB, using local file...")
                return self.client_secrets_file
            else:
                print(f"❌ Error: client_secrets.json not found in DB or locally")
                print("💡 Tip: Upload via /admin/secure-files or place file in secrets/")
                sys.exit(1)

    def _get_authenticated_service(self):
        creds = None
        if os.path.exists(self.token_file):
            with open(self.token_file, 'rb') as token:
                creds = pickle.load(token)
        
        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                try:
                    creds.refresh(Request())
                    # 갱신된 토큰 저장
                    with open(self.token_file, 'wb') as token:
                        pickle.dump(creds, token)
                except Exception as e:
                    raise Exception(f"YouTube OAuth 토큰 갱신 실패: {str(e)}. 새로운 인증이 필요합니다.")
            else:
                # 서버 환경에서는 대화형 OAuth 플로우를 사용할 수 없음
                raise Exception(
                    "YouTube OAuth 인증이 필요합니다. "
                    "로컬 환경에서 먼저 인증을 완료하고 token.pickle 파일을 서버에 업로드하세요. "
                    "또는 refresh_token이 있는 유효한 토큰이 필요합니다."
                )
        
        return build('youtube', 'v3', credentials=creds)

    def generate_youtube_metadata(self, pdf_path, lang='ko', desc_template=""):
        print(f"🎙️ Analyzing PDF for marketing-focused metadata (Language: {lang})...")
        try:
            with open(pdf_path, 'rb') as f:
                pdf_data = f.read()
            lang_str = "Korean" if lang == 'ko' else "English"
            
            # Enhanced prompt to use the description template
            prompt = f"""
            Analyze the attached PDF and generate YouTube-optimized metadata in {lang_str}.
            
            [CRITICAL INSTRUCTIONS]
            1. Title: Create a click-worthy, dramatic title.
            2. Description: Use the provided [TEMPLATE] below as a reference for style, tone, and structure.
               - Keep the dramatic storytelling opening.
               - Integrate the CORE findings and value propositions from the PDF into the middle section.
               - Keep the 'Service & Contact' information at the bottom exactly as in the template.
               - Use Emojis and Unicode bold characters for emphasis (YouTube doesn't support markdown bold).
               - Ensure URLs are plain text so they become clickable on YouTube.
            3. Tags: Generate 20+ highly relevant hashtags and keywords in {lang_str}.
            
            [TEMPLATE]
            {desc_template}
            
            Return ONLY a valid JSON object:
            {{
              "title": "...",
              "description": "...",
              "tags": ["tag1", "tag2", ...]
            }}
            """
            response = self.summarizer.client.models.generate_content(
                model=self.summarizer.model_id,
                contents=[prompt, types.Part.from_bytes(data=pdf_data, mime_type='application/pdf')]
            )
            # Remove any markdown code block wrappers if present
            clean_text = re.sub(r'```json\s*|\s*```', '', response.text.strip())
            
            # Remove potential control characters that break json.loads
            # Especially actual newlines inside string values
            try:
                metadata = json.loads(clean_text)
            except json.JSONDecodeError:
                # Fallback: strict=False allows some control characters
                metadata = json.loads(clean_text, strict=False)
            
            return metadata
        except Exception as e:
            print(f"❌ Error generating metadata: {e}")
            return {"title": "Default Title", "description": desc_template, "tags": []}

    def upload_video(self, video_path, metadata, thumbnail_path=None):
        print(f"🚀 Uploading video to YouTube: {video_path}")
        body = {
            'snippet': {
                'title': metadata['title'],
                'description': metadata['description'],
                'tags': metadata['tags'],
                'categoryId': '28'  # Science & Technology
            },
            'status': {
                'privacyStatus': 'public',
                'selfDeclaredMadeForKids': False
            }
        }
        media = MediaFileUpload(video_path, chunksize=-1, resumable=True)
        request = self.youtube.videos().insert(part=','.join(body.keys()), body=body, media_body=media)

        try:
            response = None
            while response is None:
                status, response = request.next_chunk()
                if status:
                    print(f"   - Uploaded {int(status.progress() * 100)}%")
            video_id = response['id']
            print(f"✅ Video uploaded successfully! ID: {video_id}")

            # 썸네일 업로드 (있는 경우)
            if thumbnail_path and os.path.exists(thumbnail_path):
                self.set_thumbnail(video_id, thumbnail_path)

            return video_id
        except Exception as e:
            if "uploadLimitExceeded" in str(e):
                print("\n❌ YouTube Upload Limit Exceeded!")
                print("   - 일일 업로드 한도를 초과했습니다. 유튜브 정책에 따라 약 24시간 후 다시 시도해 주세요.")
                print("   - 채널 인증을 완료하면 한도가 늘어날 수 있습니다.")
            else:
                print(f"\n❌ YouTube Upload Error: {e}")
            return None

    def set_thumbnail(self, video_id, thumbnail_path):
        """YouTube 비디오에 썸네일 설정"""
        print(f"🖼️ Setting thumbnail for video {video_id}: {thumbnail_path}")
        try:
            media = MediaFileUpload(thumbnail_path, mimetype='image/jpeg')
            request = self.youtube.thumbnails().set(
                videoId=video_id,
                media_body=media
            )
            response = request.execute()
            print(f"✅ Thumbnail set successfully!")
            return True
        except Exception as e:
            print(f"⚠️ Failed to set thumbnail: {e}")
            # 썸네일 실패해도 업로드는 성공으로 처리
            return False

    def get_video_info(self, video_path):
        print(f"📹 비디오 정보 조회 시작: {video_path}")
        print(f"   파일 존재 여부: {os.path.exists(video_path)}")
        cmd = ['ffprobe', '-v', 'error', '-select_streams', 'v:0', '-show_entries', 'format=duration:stream=width,height', '-of', 'json', video_path]
        try:
            print(f"   FFprobe 명령어: {' '.join(cmd)}")
            output = subprocess.check_output(cmd, text=True).strip()
            data = json.loads(output)
            duration = float(data['format']['duration'])
            width = int(data['streams'][0]['width'])
            height = int(data['streams'][0]['height'])
            print(f"✅ 비디오 정보: duration={duration}s, width={width}, height={height}")
            return duration, width, height
        except Exception as e:
            print(f"❌ 비디오 정보 조회 실패: {e}")
            import traceback
            traceback.print_exc()
            import sys
            sys.stdout.flush()
            return 0, 1280, 720

    def generate_subtitles(self, video_path, lang='ko'):
        print(f"🎙️ Generating keyword-focused subtitles using Gemini (Language: {lang})...")
        try:
            with open(video_path, 'rb') as f:
                video_data = f.read()
            lang_str = "Korean" if lang == 'ko' else "English"
            examples = (
                '"AGI 시대의 새로운 패러다임 분석", "혁신적인 AI 아키텍처의 도약", "한국형 소브린 AI의 전략적 가치"'
                if lang == 'ko' else
                '"Analyzing the New Paradigm of AGI", "The Leap of Innovative AI Architecture", "Strategic Value of Sovereign AI"'
            )
            
            prompt = f"""
            Analyze the video and generate professional SRT subtitles in {lang_str}.
            
            [CRITICAL Subtitling Rules]
            - Identify the most important educational or marketing points throughout the entire video.
            - Generate AT LEAST 15-20 subtitle entries to cover the whole video duration.
            - Summarize the core message into concise, punchy phrases (max 8-10 words per entry) in {lang_str}.
            - Avoid long sentences; focus on immediate understanding.
            - Each subtitle entry MUST be a single line.
            - Timing MUST follow standard SRT: HH:MM:SS,mmm --> HH:MM:SS,mmm.
            - Ensure subtitles stay on screen for a readable duration (at least 2.5 - 3 seconds).
            
            Examples of good concise phrases in {lang_str}:
            {examples}
            
            Return ONLY the raw SRT content.
            """
            response = self.summarizer.client.models.generate_content(
                model=self.summarizer.model_id,
                contents=[prompt, types.Part.from_bytes(data=video_data, mime_type='video/mp4')]
            )
            srt_content = response.text.strip()
            
            # Remove markdown code blocks and any leading/trailing text
            srt_content = re.sub(r'^.*?```(?:srt)?\s*\n?', '', srt_content, flags=re.DOTALL)
            srt_content = re.sub(r'\n?\s*```.*?$', '', srt_content, flags=re.DOTALL)
            
            # Remove any explanatory text before the first subtitle number
            lines = srt_content.split('\n')
            start_idx = 0
            for i, line in enumerate(lines):
                if line.strip().isdigit():
                    start_idx = i
                    break
            srt_content = '\n'.join(lines[start_idx:]).strip()
            
            v_dir = os.path.dirname(video_path)
            srt_path = os.path.join(v_dir, f"subtitles_{lang}.srt")
            
            # Standardize format
            srt_content = srt_content.replace('\r\n', '\n').replace('\r', '\n')
            
            # Robust Regex to find all SRT blocks: Index \n Timing \n Content
            # Support content spanning multiple lines if necessary before joining
            blocks = re.findall(r'(\d+)\n(\d{1,2}:\d{2}:\d{2},\d{3}\s*-->\s*\d{1,2}:\d{2}:\d{2},\d{3})\n(.*?)(?=\n\d+\n|$)', srt_content, re.DOTALL)
            
            # If standard regex fails, try a more flexible one for messy input
            if not blocks:
                blocks = re.findall(r'(\d+)\s+(\d{1,2}:\d{2}:\d{2},\d{3}\s*-->\s*\d{1,2}:\d{2}:\d{2},\d{3})\s+(.*?)(?=\s+\d+\s+|$)', srt_content, re.DOTALL)

            final_srt = ""
            for i, (idx, timing, content) in enumerate(blocks):
                # Clean content: remove any embedded timing or indices
                clean_content = re.sub(r'\d{1,2}:\d{2}:\d{2},\d{3}\s*-->\s*\d{1,2}:\d{2}:\d{2},\d{3}', '', content)
                clean_content = " ".join(clean_content.split()).strip()
                
                # Ensure minimum duration (2.5s)
                try:
                    parts = timing.split('-->')
                    def to_ms(s_str):
                        h, m, s_ms = s_str.strip().split(':')
                        sec, ms = s_ms.split(',')
                        return (int(h)*3600 + int(m)*60 + int(sec))*1000 + int(ms)
                    
                    def from_ms(ms_val):
                        h = ms_val // 3600000
                        ms_val %= 3600000
                        m = ms_val // 60000
                        ms_val %= 60000
                        s = ms_val // 1000
                        ms_val %= 1000
                        return f"{h:02d}:{m:02d}:{s:02d},{ms_val:03d}"
                    
                    start_ms = to_ms(parts[0])
                    end_ms = to_ms(parts[1])
                    if (end_ms - start_ms) < 2500:
                        end_ms = start_ms + 2500
                    timing = f"{from_ms(start_ms)} --> {from_ms(end_ms)}"
                except:
                    pass
                
                final_srt += f"{i+1}\n{timing}\n{clean_content}\n\n"
            
            srt_content = final_srt.strip()
            with open(srt_path, 'w', encoding='utf-8') as f:
                f.write(srt_content)
                f.flush()
                os.fsync(f.fileno())
            
            print(f"✅ Subtitle file generated: {srt_path} ({os.path.getsize(srt_path)} bytes)")
            return srt_path
        except Exception as e:
            print(f"❌ Error generating subtitles: {e}")
            return None

    def ffmpeg_filter_escape(self, path):
        """Robustly escapes a file path for use in FFmpeg filters on macOS."""
        # On macOS, colons in absolute paths (/Volumes/...) must be escaped as \\:
        # Also need to escape backslashes and single quotes.
        return path.replace('\\', '\\\\').replace(':', '\\\\:').replace("'", "'\\\\''")

    def add_logo_and_subs_to_video(self, video_input, logo_input, srt_input, video_output, margin=30, logo_width=180):
        print(f"🎬 add_logo_and_subs_to_video 시작")
        print(f"   video_input: {video_input}")
        print(f"   logo_input: {logo_input}")
        print(f"   srt_input: {srt_input}")
        print(f"   video_output: {video_output}")
        import sys
        sys.stdout.flush()
        
        duration, width, height = self.get_video_info(video_input)
        if duration == 0:
            print(f"❌ 비디오 duration이 0입니다. 비디오 정보 조회 실패.")
            import sys
            sys.stdout.flush()
            return False
        
        outro_start = max(0, duration - 3)
        font_path = "/System/Library/Fonts/Supplemental/Arial Italic.ttf"
        
        sub_filter = ""
        overlay_input = "[0:v]"
        temp_srt_name = "sub.srt"
        video_dir = os.path.dirname(os.path.abspath(video_input))
        temp_srt_path = os.path.join(video_dir, temp_srt_name)
        
        if srt_input and os.path.exists(srt_input):
            try:
                # Copy SRT to video directory with simple name
                if os.path.exists(temp_srt_path):
                    os.remove(temp_srt_path)
                shutil.copy2(srt_input, temp_srt_path)
                
                # Ensure write is finished
                with open(temp_srt_path, 'r', encoding='utf-8') as f: f.read(1)
                os.fsync(os.open(temp_srt_path, os.O_RDONLY))
                time.sleep(0.5)
                
                # Stylish styling: White text on Semi-transparent Black Box
                # In BorderStyle=3, OutlineColour controls the box background color.
                # &H80000000: 80 is alpha (approx 50%), 000000 is Black.
                sub_style = (
                    "FontName=Apple SD Gothic Neo,"
                    "FontSize=18,"
                    "Alignment=2,"
                    "Outline=2,"                # Minimal padding
                    "Shadow=0,"
                    "BorderStyle=3,"            # Opaque/Transparent box background
                    "PrimaryColour=&H00FFFFFF," # White Text
                    "OutlineColour=&H80000000," # Semi-transparent Black Box
                    "BackColour=&H00000000,"    # Shadow (not used)
                    "MarginV=40"                # Closer to bottom
                )
                
                # Use ONLY the filename 'sub.srt' here, as we will chdir to video_dir
                # We still need to escape any special chars in the filename itself (unlikely for 'sub.srt')
                srt_name_esc = temp_srt_name.replace("'", "'\\''")
                sub_filter = f"[0:v]subtitles='{srt_name_esc}':force_style='{sub_style}'[v_sub];"
                overlay_input = "[v_sub]"
                
                print(f"✅ Prepared subtitles: {temp_srt_path}")
            except Exception as e:
                print(f"⚠️ Subtitle preparation error: {e}")

        font_path_esc = self.ffmpeg_filter_escape(font_path)
        filter_complex = (
            f"[1:v]split[static][animated];"
            f"[static]scale={logo_width}:-1[st_logo];"
            f"[animated]scale='if(gte(t,{outro_start}), min(800, 800*(t-{outro_start})/2.0), 0)':-1:eval=frame[out_logo];"
            f"color=c=white:s={width}x{height}:d=3[white_src];"
            f"[white_src]fade=t=in:st=0:d=1.5:alpha=1[white_bg];"
            f"{sub_filter}"
            f"{overlay_input}[st_logo]overlay=W-w-{margin}:H-h-{margin}[v1];"
            f"[v1][white_bg]overlay=enable='gte(t,{outro_start})'[v2];"
            f"[v2]drawtext=text='https\\://banya.ai':fontfile='{font_path_esc}':fontsize=45:fontcolor=black:x=(w-tw)/2:y=(h/2)+130:enable='gte(t,{outro_start})'[v3];"
            f"[v3][out_logo]overlay=(W-w)/2:(H-h)/2:enable='gte(t,{outro_start})'"
        )
        
        cmd = [
            'ffmpeg', '-y',
            '-i', os.path.basename(video_input), # Use basename
            '-i', os.path.abspath(logo_input),    # Logo can be absolute
            '-filter_complex', filter_complex,
            '-c:a', 'copy',
            os.path.abspath(video_output)
        ]
        
        print(f"🎬 Processing video...")
        print(f"   FFmpeg 명령어: {' '.join(cmd)}")
        original_cwd = os.getcwd()
        try:
            os.chdir(video_dir) # Change CWD to video directory
            print(f"   Working directory: {os.getcwd()}")
            print(f"   입력 비디오 파일 존재 여부: {os.path.exists(os.path.basename(video_input))}")
            print(f"   로고 파일 존재 여부: {os.path.exists(os.path.abspath(logo_input))}")
            result = subprocess.run(cmd, capture_output=True, text=True)
            if result.returncode == 0:
                print("✅ Done!")
                print(f"   출력 파일 생성 여부: {os.path.exists(os.path.abspath(video_output))}")
                return True
            else:
                print(f"❌ FFmpeg Error (code {result.returncode}):")
                print(f"   stdout: {result.stdout}")
                print(f"   stderr: {result.stderr}")
                import sys
                sys.stdout.flush()
                return False
        except Exception as e:
            print(f"❌ Exception: {e}")
            import traceback
            traceback.print_exc()
            import sys
            sys.stdout.flush()
            return False
        finally:
            os.chdir(original_cwd) # Restore CWD

def main():
    poster = YouTubeAutoPoster()
    base_v_dir = os.path.join(os.path.dirname(__file__), 'v_source')
    
    print("\nSelect Category:")
    print("1. tech (Default)")
    print("2. entertainment")
    cat_choice = input("Choice: ").strip()
    category = 'entertainment' if cat_choice == '2' else 'tech'
    
    v_dir = os.path.join(base_v_dir, category)
    if not os.path.exists(v_dir):
        print(f"❌ Category directory not found: {v_dir}")
        return

    try:
        pdf_file = sorted([f for f in os.listdir(v_dir) if f.endswith('.pdf')], reverse=True)[0]
        mp4_file = sorted([f for f in os.listdir(v_dir) if f.endswith('.mp4') and 'final' not in f], reverse=True)[0]
        # Look for logo file - case insensitive and specifically checking for PNG
        logo_files = [f for f in os.listdir(v_dir) if f.lower().endswith('.png') and 'logo' in f.lower()]
        if not logo_files:
            # Fallback to search any png if "logo" isn't in name
            logo_files = [f for f in os.listdir(v_dir) if f.lower().endswith('.png')]
        logo_file = logo_files[0]
    except (IndexError, FileNotFoundError):
        print(f"❌ Missing PDF, MP4, or Logo in {v_dir}.")
        return
    
    pdf_path = os.path.join(v_dir, pdf_file)
    video_path = os.path.join(v_dir, mp4_file)
    logo_path = os.path.join(v_dir, logo_file)
    
    print("\n1. ko / 2. en")
    choice = input("Choice (default 1): ").strip()
    lang = 'en' if choice == '2' else 'ko'
    
    # Read language-specific description template
    desc_filename = f'desc_{lang}.md'
    desc_path = os.path.join(v_dir, desc_filename)
    
    # Fallback to desc.md if language-specific one doesn't exist
    if not os.path.exists(desc_path):
        desc_path = os.path.join(v_dir, 'desc.md')
        
    desc_template = ""
    if os.path.exists(desc_path):
        with open(desc_path, 'r', encoding='utf-8') as f:
            desc_template = f.read()
        print(f"📖 Using template: {os.path.basename(desc_path)}")
    else:
        print(f"⚠️ No description template found ({desc_filename} or desc.md)")
    
    metadata = poster.generate_youtube_metadata(pdf_path, lang=lang, desc_template=desc_template)
    
    # Save metadata for re-upload if needed
    metadata_path = os.path.join(v_dir, f"metadata_{lang}.json")
    with open(metadata_path, 'w', encoding='utf-8') as f:
        json.dump(metadata, f, ensure_ascii=False, indent=2)
    print(f"📄 Metadata saved for backup: {metadata_path}")
    
    srt_path = poster.generate_subtitles(video_path, lang=lang)
    
    final_video = os.path.join(v_dir, f"final_youtube_post_{lang}.mp4")
    if poster.add_logo_and_subs_to_video(video_path, logo_path, srt_path, final_video):
        print(f"✅ Created: {final_video}")
        if input("\nUpload? (y/n): ").lower() == 'y':
            poster.upload_video(final_video, metadata)
            print("\n🚀 Process completed successfully!")
        
        # Cleanup intermediate files
        print("\n🧹 Cleaning up intermediate files...")
        temp_srt = os.path.join(v_dir, "sub.srt")
        files_to_delete = [srt_path, temp_srt, final_video]
        
        for f in files_to_delete:
            if f and os.path.exists(f):
                try:
                    os.remove(f)
                    print(f"   - Deleted: {os.path.basename(f)}")
                except Exception as e:
                    print(f"   - Failed to delete {os.path.basename(f)}: {e}")
    else:
        print("❌ Video processing failed.")

if __name__ == "__main__":
    main()
