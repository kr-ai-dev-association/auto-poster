import os
import sys
import json
import pickle
import subprocess
import re
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
               - **Marketing Hook**: Start with a provocative question or a shocking insight from the PDF that stops the scroll.
               - **Deep Insight**: Provide a structured, emoji-rich summary of the most valuable insights from the PDF. Make it look professional yet exciting.
               - **Call to Action (CTA)**: Encourage viewers to like, subscribe, and check out the links below.
               - **Hashtags**: Include 20+ highly trending and relevant hashtags (e.g., #AI #Technology #DeepLearning...).
               - **MANDATORY - Links & Info**: You MUST append the following contact and promotional information at the VERY END. Ensure the URLs are kept as plain text so YouTube can automatically make them clickable:
               
               {desc_template}
               
            3. Tags: 20-30 highly relevant SEO keywords for maximum reach.
            
            IMPORTANT: Return ONLY a valid JSON object. No other text.
            The values in the JSON MUST be in {lang_str}.
            
            Format:
            {{
                "title": "...",
                "description": "...",
                "tags": ["tag1", "tag2", ...]
            }}
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

    def add_logo_to_video(self, video_input, logo_input, video_output, margin=30, logo_width=180):
        """Adds a logo to the bottom-right corner of a video using ffmpeg."""
        if not os.path.exists(video_input):
            print(f"Error: Video file not found: {video_input}")
            return False
        if not os.path.exists(logo_input):
            print(f"Error: Logo file not found: {logo_input}")
            return False

        print(f"\n🎬 Adding logo to video...")
        print(f"   Input: {video_input}")
        print(f"   Logo: {logo_input}")
        
        cmd = [
            'ffmpeg', '-y',
            '-i', video_input,
            '-i', logo_input,
            '-filter_complex', f"[1:v]scale={logo_width}:-1 [logo]; [0:v][logo]overlay=W-w-{margin}:H-h-{margin}",
            '-c:a', 'copy',
            video_output
        ]
        
        try:
            process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            stdout, stderr = process.communicate()
            
            if process.returncode == 0:
                print(f"✅ Successfully created video with logo: {video_output}")
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
    mp4_files = sorted([f for f in os.listdir(v_source_dir) if f.endswith('.mp4') and 'preview' not in f], reverse=True)
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
    
    # 2. Add Logo if exists
    final_video_path = video_path
    if logo_path:
        processed_video_path = os.path.join(v_source_dir, "final_video_with_logo.mp4")
        if poster.add_logo_to_video(video_path, logo_path, processed_video_path):
            final_video_path = processed_video_path
        else:
            print("⚠️ Proceeding with original video without logo due to error.")

    confirm = input("\nDo you want to upload this video to YouTube? (y/n): ")
    if confirm.lower() == 'y':
        poster.upload_video(final_video_path, metadata)
    else:
        print("Upload cancelled.")

if __name__ == "__main__":
    main()
