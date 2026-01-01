import os
import sys
import json
import pickle
from PyPDF2 import PdfReader
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
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

    def extract_text_from_pdf(self, pdf_path):
        """Extract text content from a PDF file."""
        print(f"Extracting text from PDF: {pdf_path}")
        reader = PdfReader(pdf_path)
        text = ""
        for page in reader.pages:
            text += page.extract_text() or ""
        return text

    def generate_youtube_metadata(self, pdf_text):
        """Use Gemini to generate Title, Description, and Tags."""
        print("Generating YouTube metadata using Gemini...")
        prompt = f"""
        You are a YouTube SEO expert. Based on the following technical content from a PDF, 
        generate professional YouTube metadata.
        
        [Requirements]
        1. Title: Catchy but professional (under 100 characters).
        2. Description: Detailed summary of the video content, including key points.
        3. Tags: 10-15 relevant keywords.
        
        Format the output as a JSON object:
        {{
            "title": "...",
            "description": "...",
            "tags": ["tag1", "tag2", ...]
        }}
        
        Content:
        {pdf_text[:5000]}
        """
        
        try:
            # Using the existing summarizer's client to generate content
            response = self.summarizer.client.models.generate_content(
                model=self.summarizer.model_id,
                contents=prompt
            )
            metadata_text = response.text.strip()
            # Clean up potential markdown formatting
            metadata_text = re.sub(r'^```json\s*', '', metadata_text)
            metadata_text = re.sub(r'\s*```$', '', metadata_text)
            return json.loads(metadata_text)
        except Exception as e:
            print(f"Error generating metadata: {e}")
            return {
                "title": "AI Technical Deep Dive",
                "description": "An in-depth analysis of AI technologies.",
                "tags": ["AI", "Technology", "Deep Learning"]
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

import re

def main():
    poster = YouTubeAutoPoster()
    
    # Path settings
    v_source_dir = os.path.join(os.path.dirname(__file__), 'v_source')
    pdf_files = [f for f in os.listdir(v_source_dir) if f.endswith('.pdf')]
    mp4_files = [f for f in os.listdir(v_source_dir) if f.endswith('.mp4')]
    
    if not pdf_files or not mp4_files:
        print("Error: Missing PDF or MP4 file in v_source directory.")
        return

    pdf_path = os.path.join(v_source_dir, pdf_files[0])
    video_path = os.path.join(v_source_dir, mp4_files[0])

    # 1. Extract info from PDF
    pdf_text = poster.extract_text_from_pdf(pdf_path)
    
    # 2. Generate Metadata
    metadata = poster.generate_youtube_metadata(pdf_text)
    print(f"\n--- Generated Metadata ---")
    print(f"Title: {metadata['title']}")
    print(f"Description: {metadata['description'][:100]}...")
    print(f"Tags: {', '.join(metadata['tags'])}")
    
    confirm = input("\nDo you want to upload this video to YouTube? (y/n): ")
    if confirm.lower() == 'y':
        poster.upload_video(video_path, metadata)
    else:
        print("Upload cancelled.")

if __name__ == "__main__":
    main()
