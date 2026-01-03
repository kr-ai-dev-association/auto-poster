import sys
import json
import os
import re
import requests
from dotenv import load_dotenv
from googleapiclient.discovery import build

# Add project root to path to import from core
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from core.linkedin_poster import LinkedInPoster
from core.summarizer import GeminiSummarizer

load_dotenv()

def extract_video_id(url):
    """
    Extract the video ID from a YouTube URL.
    """
    patterns = [
        r'(?:v=|\/)([0-9A-Za-z_-]{11}).*',
        r'youtu\.be\/([0-9A-Za-z_-]{11})',
        r'embed\/([0-9A-Za-z_-]{11})',
        r'shorts\/([0-9A-Za-z_-]{11})'
    ]
    for pattern in patterns:
        match = re.search(pattern, url)
        if match:
            return match.group(1)
    return None

def get_youtube_metadata(video_id, api_key):
    """
    Fetch YouTube video metadata using the Data API v3.
    """
    youtube = build('youtube', 'v3', developerKey=api_key)
    request = youtube.videos().list(
        part="snippet,contentDetails,statistics",
        id=video_id
    )
    response = request.execute()
    
    if not response['items']:
        return None
    
    item = response['items'][0]
    snippet = item['snippet']
    
    # Get the best available thumbnail
    thumbnails = snippet.get('thumbnails', {})
    thumbnail_url = (
        thumbnails.get('maxres', {}).get('url') or 
        thumbnails.get('high', {}).get('url') or 
        thumbnails.get('medium', {}).get('url') or 
        thumbnails.get('default', {}).get('url')
    )
    
    return {
        'title': snippet.get('title'),
        'description': snippet.get('description'),
        'thumbnail_url': thumbnail_url,
        'tags': snippet.get('tags', [])
    }

def main():
    youtube_api_key = os.getenv("YOUTUBE_API_KEY")
    if not youtube_api_key:
        print("Error: YOUTUBE_API_KEY not found in .env file.")
        return

    # Find youtube.json in the same directory
    config_path = os.path.join(os.path.dirname(__file__), 'youtube.json')
    try:
        print(f"Loading YouTube URL from {config_path}...")
        with open(config_path, 'r', encoding='utf-8') as f:
            config = json.load(f)
    except FileNotFoundError:
        print(f"Error: {config_path} not found.")
        return

    url = config.get("url")
    if not url:
        print(f"Error: 'url' is missing in {config_path}. Exiting.")
        return

    video_id = extract_video_id(url)
    if not video_id:
        print(f"Error: Could not extract video ID from {url}.")
        return

    print(f"Fetching metadata for video ID: {video_id}")
    metadata = get_youtube_metadata(video_id, youtube_api_key)
    if not metadata:
        print(f"Error: Failed to fetch metadata for video ID {video_id}.")
        return

    poster = LinkedInPoster()
    if not poster.person_urn:
        print("Person URN not found in .env, trying to fetch from API...")
        me = poster.get_me()
        if me:
            poster.person_urn = f"urn:li:person:{me['id']}"
        else:
            print("Failed to get Person URN. Exiting.")
            return

    summarizer = GeminiSummarizer()
    
    # Process both English and Korean
    for lang in ["en", "ko"]:
        print(f"Generating {lang} summary for video...")
        
        # We use title and description for summarization
        # Combined content for better context
        content_for_ai = f"Title: {metadata['title']}\n\nDescription: {metadata['description']}"
        generated_summary = summarizer.summarize(metadata['title'], content_for_ai, lang=lang)
        
        if lang == 'en':
            post_text = f"{generated_summary}\n\n\n📺 Watch the full video:\n{url}"
        else:
            post_text = f"{generated_summary}\n\n\n📺 전체 영상 보기:\n{url}"

        # Handle thumbnail image
        local_image_path = None
        if metadata['thumbnail_url']:
            print(f"Downloading thumbnail: {metadata['thumbnail_url']}")
            img_res = requests.get(metadata['thumbnail_url'])
            if img_res.status_code == 200:
                temp_thumb = "temp_youtube_thumb.jpg"
                with open(temp_thumb, 'wb') as f:
                    f.write(img_res.content)
                local_image_path = temp_thumb

        uploaded_image_urn = None
        if local_image_path:
            print(f"Uploading thumbnail to LinkedIn...")
            uploaded_image_urn = poster.upload_image(local_image_path)
            # Cleanup temp file
            if os.path.exists(local_image_path):
                os.remove(local_image_path)

        print("-" * 30)
        print(f"YouTube Post Preview ({lang.upper()}):")
        print(post_text)
        print("-" * 30)

        confirm = input(f"Do you want to post this ({lang.upper()}) to LinkedIn? (y/n): ")
        if confirm.lower() == 'y':
            result = poster.post_text(post_text, title=metadata['title'], original_url=url, uploaded_image_urn=uploaded_image_urn)
            if result:
                print(f"[{lang.upper()}] Post successful!")
            else:
                print(f"[{lang.upper()}] Post failed.")
        else:
            print(f"[{lang.upper()}] Post cancelled.")

if __name__ == "__main__":
    main()

