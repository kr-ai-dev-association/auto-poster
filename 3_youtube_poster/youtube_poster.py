import os
import sys
import json
import pickle
import subprocess
import re
import tempfile
import shutil
from PyPDF2 import PdfReader
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
        self.client_secrets_file = os.path.join(os.path.dirname(__file__), client_secrets_file)
        self.token_file = os.path.join(os.path.dirname(__file__), 'token.pickle')
        self.scopes = ['https://www.googleapis.com/auth/youtube.upload']
        self.youtube = self._get_authenticated_service()
        self.summarizer = GeminiSummarizer()

    def _get_authenticated_service(self):
        creds = None
        if os.path.exists(self.token_file):
            with open(self.token_file, 'rb') as token:
                creds = pickle.load(token)
        
        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
            else:
                if not os.path.exists(self.client_secrets_file):
                    print(f"Error: {self.client_secrets_file} not found.")
                    print("Please download your client_secrets.json from Google Cloud Console.")
                    sys.exit(1)
                flow = InstalledAppFlow.from_client_secrets_file(self.client_secrets_file, self.scopes)
                creds = flow.run_local_server(port=0)
            
            with open(self.token_file, 'wb') as token:
                pickle.dump(creds, token)
        
        return build('youtube', 'v3', credentials=creds)

    def generate_youtube_metadata(self, pdf_path, lang='ko', desc_template=""):
        """Upload PDF to Gemini and generate Title, Description, and Tags with marketing focus."""
        print(f"Uploading PDF to Gemini for analysis (Language: {lang}): {pdf_path}")
        
        try:
            # 1. Upload the file to Gemini
            with open(pdf_path, 'rb') as f:
                pdf_data = f.read()
            
            lang_str = "Korean" if lang == 'ko' else "English"
            
            prompt = f"""
            You are a world-class YouTube Marketing Specialist and SEO expert. 
            Analyze the attached PDF document and generate a highly engaging, viral-ready YouTube metadata in {lang_str}.
            
            [Requirements]
            1. Title: Create a high-CTR, curiosity-inducing, and benefit-driven title (under 100 characters). Use powerful words.
            2. Description: 
               - **IMPORTANT: DO NOT USE MARKDOWN SYMBOLS like **, __, #, or [text](url). YouTube does not support them.**
               - **Marketing Hook**: Start with a provocative question or a shocking insight from the PDF.
               - **Deep Insight**: Provide a structured summary using emojis for bullet points.
               - **Emphasis**: For highlighting important keywords, use Unicode Bold characters (e.g., 𝗔𝗜, 𝗞𝗼𝗿𝗲𝗮) instead of markdown.
               - **Call to Action (CTA)**: Encourage viewers to like, subscribe, and check out the links below.
               - **Hashtags**: Include 20+ trending hashtags at the bottom.
               - **MANDATORY - Links & Info**: Convert any markdown links from the following template into a simple 'Name: URL' format so they become clickable on YouTube:
               
               {desc_template}
               
            3. Tags: 20-30 highly relevant SEO keywords.
            
            IMPORTANT: Return ONLY a valid JSON object. No other text.
            The values in the JSON MUST be in {lang_str}.
            """
            
            # Use the SDK to send the PDF file along with the prompt
            response = self.summarizer.client.models.generate_content(
                model=self.summarizer.model_id,
                contents=[
                    prompt,
                    types.Part.from_bytes(data=pdf_data, mime_type='application/pdf')
                ]
            )
            
            metadata_text = response.text.strip()
            # More robust JSON extraction
            match = re.search(r'\{.*\}', metadata_text, re.DOTALL)
            if match:
                metadata_text = match.group(0)
            
            metadata = json.loads(metadata_text)
            print(f"Successfully analyzed PDF and generated marketing metadata in {lang_str}.")
            return metadata
            
        except Exception as e:
            print(f"Error analyzing PDF with Gemini: {e}")
            if lang == 'ko':
                return {
                    "title": "AI 기술 심층 분석: 프로메테우스의 불",
                    "description": "제공된 분석 보고서를 바탕으로 한 AI 기술의 발전과 지능의 진화에 대한 심층 분석입니다.",
                    "tags": ["AI", "인공지능", "기술", "딥러닝", "미래기술"]
                }
            else:
                return {
                    "title": "AI Technical Deep Dive: The Stolen Fire",
                    "description": "An in-depth analysis of AI technologies and the evolution of intelligence based on the provided synthesis.",
                    "tags": ["AI", "Technology", "Deep Learning", "Artificial Intelligence"]
                }

    def upload_video(self, video_path, metadata):
        """Upload video to YouTube."""
        print(f"Uploading video: {video_path}")
        body = {
            'snippet': {
                'title': metadata['title'],
                'description': metadata['description'],
                'tags': metadata['tags'],
                'categoryId': '28'  # Science & Technology
            },
            'status': {
                'privacyStatus': 'public',  # or 'unlisted'
                'selfDeclaredMadeForKids': False
            }
        }

        media = MediaFileUpload(video_path, chunksize=-1, resumable=True)
        request = self.youtube.videos().insert(
            part=','.join(body.keys()),
            body=body,
            media_body=media
        )

        response = None
        while response is None:
            status, response = request.next_chunk()
            if status:
                print(f"Uploaded {int(status.progress() * 100)}%")
        
        print(f"Video uploaded successfully! Video ID: {response['id']}")
        return response['id']

    def get_video_info(self, video_path):
        """Returns the duration and resolution of a video."""
        cmd = [
            'ffprobe', '-v', 'error', '-select_streams', 'v:0',
            '-show_entries', 'format=duration:stream=width,height',
            '-of', 'json', video_path
        ]
        try:
            output = subprocess.check_output(cmd, text=True).strip()
            data = json.loads(output)
            duration = float(data['format']['duration'])
            width = int(data['streams'][0]['width'])
            height = int(data['streams'][0]['height'])
            return duration, width, height
        except Exception as e:
            print(f"Error getting video info: {e}")
            return 0, 1280, 720

    def generate_subtitles(self, video_path, lang='ko'):
        """Upload video to Gemini and generate SRT subtitles."""
        print(f"\n🎙️ Generating subtitles using Gemini (Language: {lang})...")
        print(f"   Analyzing video: {video_path}")
        
        try:
            # 1. Upload the video file to Gemini
            with open(video_path, 'rb') as f:
                video_data = f.read()
            
            lang_str = "Korean" if lang == 'ko' else "English"
            
            prompt = f"""
            Analyze the audio and visual content of this video and generate professional SRT subtitles in {lang_str}.
            
            [Requirements]
            1. Format: Standard SRT format with sequence numbers and timestamps (00:00:00,000 --> 00:00:00,000).
            2. Accuracy: Ensure the timing matches the speech perfectly.
            3. Style: Clear, concise, and professional.
            4. Language: Translate or transcribe everything into {lang_str}.
            
            IMPORTANT: Return ONLY the raw SRT content. No other text or markdown code blocks.
            """
            
            response = self.summarizer.client.models.generate_content(
                model=self.summarizer.model_id,
                contents=[
                    prompt,
                    types.Part.from_bytes(data=video_data, mime_type='video/mp4')
                ]
            )
            
            srt_content = response.text.strip()
            # Clean up potential markdown formatting
            srt_content = re.sub(r'^```(srt)?\s*', '', srt_content)
            srt_content = re.sub(r'\s*```$', '', srt_content)
            
            srt_path = video_path.rsplit('.', 1)[0] + f"_{lang}.srt"
            with open(srt_path, 'w', encoding='utf-8') as f:
                f.write(srt_content)
                
            print(f"✅ Subtitles generated and saved to: {srt_path}")
            return srt_path
            
        except Exception as e:
            print(f"❌ Error generating subtitles: {e}")
            return None

    def add_logo_and_subs_to_video(self, video_input, logo_input, srt_input, video_output, margin=30, logo_width=180):
        """Adds static logo, outro animation, and burns in subtitles."""
        if not os.path.exists(video_input):
            print(f"Error: Video file not found: {video_input}")
            return False
        
        duration, width, height = self.get_video_info(video_input)
        if duration == 0:
            return False
        
        outro_start = max(0, duration - 3)
        font_path = "/System/Library/Fonts/Supplemental/Arial Italic.ttf"
        # For subtitles, we'll use a standard font
        sub_font_path = "/System/Library/Fonts/AppleSDGothicNeo.ttc"
        
        print(f"\n🎬 Processing video (Logo + Animation + Subtitles)...")
        
        # Subtitles filter: we need to escape path for ffmpeg
        if srt_input and os.path.exists(srt_input):
            srt_esc = srt_input.replace(":", "\\:").replace("'", "'\\''")
            sub_filter = f"subtitles='{srt_esc}':force_style='FontSize=20,Alignment=2,Outline=1'[v_sub];"
            overlay_input = "[v_sub]"
        else:
            sub_filter = ""
            overlay_input = "[0:v]"
        
        filter_complex = (
            f"[1:v]split[static][animated];"
            f"[static]scale={logo_width}:-1[st_logo];"
            f"[animated]scale='if(gte(t,{outro_start}), min(800, 800*(t-{outro_start})/2.0), 0)':-1:eval=frame[out_logo];"
            f"color=c=white:s={width}x{height}:d=3[white_src];"
            f"[white_src]fade=t=in:st=0:d=1.5:alpha=1[white_bg];"
            f"{sub_filter}"
            f"{overlay_input}[st_logo]overlay=W-w-{margin}:H-h-{margin}[v1];"
            f"[v1][white_bg]overlay=enable='gte(t,{outro_start})'[v2];"
            f"[v2]drawtext=text='https\\://banya.ai':fontfile='{font_path}':fontsize=45:fontcolor=black:x=(w-tw)/2:y=(h/2)+130:enable='gte(t,{outro_start})'[v3];"
            f"[v3][out_logo]overlay=(W-w)/2:(H-h)/2:enable='gte(t,{outro_start})'"
        )
        
        cmd = [
            'ffmpeg', '-y',
            '-i', video_input,
            '-i', logo_input,
            '-filter_complex', filter_complex,
            '-c:a', 'copy',
            video_output
        ]
        
        try:
            process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            stdout, stderr = process.communicate()
            
            if process.returncode == 0:
                print(f"✅ Successfully created final video: {video_output}")
                return True
            else:
                print(f"❌ Error in ffmpeg processing: {stderr}")
                return False
        except Exception as e:
            print(f"❌ Exception during video editing: {e}")
            return False

def main():
    poster = YouTubeAutoPoster()
    
    # Path settings
    v_source_dir = os.path.join(os.path.dirname(__file__), 'v_source')
    pdf_files = sorted([f for f in os.listdir(v_source_dir) if f.endswith('.pdf')], reverse=True)
    # Filter out already processed videos to avoid ffmpeg in-place error
    mp4_files = sorted([f for f in os.listdir(v_source_dir) if f.endswith('.mp4') and 'preview' not in f and 'final_video' not in f], reverse=True)
    logo_files = [f for f in os.listdir(v_source_dir) if f.endswith('.png') and 'logo' in f.lower()]
    
    if not pdf_files or not mp4_files:
        print("Error: Missing PDF or MP4 file in v_source directory.")
        return

    pdf_path = os.path.join(v_source_dir, pdf_files[0])
    video_path = os.path.join(v_source_dir, mp4_files[0])
    logo_path = os.path.join(v_source_dir, logo_files[0]) if logo_files else None
    
    # Read desc.md for marketing template
    desc_template = ""
    desc_md_path = os.path.join(v_source_dir, "desc.md")
    if os.path.exists(desc_md_path):
        with open(desc_md_path, 'r', encoding='utf-8') as f:
            desc_template = f.read()

    # 0. Select Language
    print("\nSelect language for YouTube metadata:")
    print("1. Korean (ko)")
    print("2. English (en)")
    choice = input("Enter choice (1 or 2, default is 1): ").strip()
    lang = 'en' if choice == '2' else 'ko'

    # 1. Generate Metadata by uploading PDF to Gemini
    metadata = poster.generate_youtube_metadata(pdf_path, lang=lang, desc_template=desc_template)
    print(f"\n--- Generated Metadata ({lang}) ---")
    print(f"Title: {metadata['title']}")
    print(f"Description: {metadata['description'][:100]}...")
    print(f"Tags: {', '.join(metadata['tags'])}")
    
    # 2. Generate Subtitles
    srt_path = poster.generate_subtitles(video_path, lang=lang)
    
    # 3. Add Logo and Subtitles if logo exists
    final_video_path = video_path
    temp_dir = None
    
    if logo_path:
        temp_dir = tempfile.mkdtemp()
        processed_video_path = os.path.join(temp_dir, "final_video_with_logo_subs.mp4")
        # If subtitles exist, use the combined method
        if srt_path:
            if poster.add_logo_and_subs_to_video(video_path, logo_path, srt_path, processed_video_path):
                final_video_path = processed_video_path
        else:
            # Fallback to just logo if subtitles failed
            # We need to temporarily define add_logo_to_video back or modify current
            # For simplicity, let's assume subtitles are needed for the preview
            print("⚠️ Subtitles missing, trying to process without subtitles...")
            # We'll re-add the old method or handle it in the new one
            if poster.add_logo_and_subs_to_video(video_path, logo_path, "", processed_video_path):
                final_video_path = processed_video_path

    try:
        confirm = input("\nDo you want to upload this video to YouTube? (y/n): ")
        if confirm.lower() == 'y':
            poster.upload_video(final_video_path, metadata)
        else:
            print("Upload cancelled.")
    finally:
        # Cleanup temporary directory
        if temp_dir and os.path.exists(temp_dir):
            print(f"\n🧹 Cleaning up temporary files in {temp_dir}...")
            shutil.rmtree(temp_dir)
            print("✅ Cleanup complete.")

if __name__ == "__main__":
    main()
