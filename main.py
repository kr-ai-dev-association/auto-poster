import sys
import json
import os
from dotenv import load_dotenv
from scraper import fetch_html_content, parse_content, get_google_doc_id
from linkedin_poster import LinkedInPoster
from summarizer import GeminiSummarizer

load_dotenv()

def main():
    default_urls = {}
    contents_path = '/Volumes/Transcend/Projects/auto-poster/contents.json'
    try:
        print(f"Loading URLs from {contents_path}...")
        with open(contents_path, 'r', encoding='utf-8') as f:
            default_urls = json.load(f)
    except FileNotFoundError:
        print("contents.json not found. Using hardcoded default URL.")
        default_urls = {
            "ko": {"url": "https://tony.banya.ai/wiki/1lPawlS0GR_sU1uAGlOYZkTloAljWCNARZS83OhPoBhY"},
            "en": {"url": "https://tony.banya.ai/wiki/1q4JBTP0H1mp0EkK-b0mA-hBda2xbmPJebhvB8GEQyew"}
        }

    poster = LinkedInPoster()
    if not poster.person_urn:
        print("Person URN not found in .env, trying to fetch from API...")
        me = poster.get_me()
        if me:
            poster.person_urn = f"urn:li:person:{me['id']}"
        else:
            print("Failed to get Person URN. Exiting.")
            return

    for lang, data_entry in default_urls.items():
        url = data_entry.get("url")
        if not url:
            print(f"Skipping {lang} as URL is missing in contents.json")
            continue

        print(f"\n[{lang.upper()}] 콘텐츠 읽는 중: {url}")
        
        # Check if it's a wiki URL and convert to Google Doc export URL
        doc_id = get_google_doc_id(url)
        if doc_id:
            google_doc_url = f"https://docs.google.com/document/d/{doc_id}/export?format=html"
            print(f"Detected wiki URL, fetching from Google Doc: {google_doc_url}")
            html = fetch_html_content(google_doc_url)
        else:
            html = fetch_html_content(url)

        if not html:
            print(f"[{lang.upper()}] Failed to fetch HTML content for {url}.")
            continue

        data = parse_content(html, url) 
        if not data:
            print(f"[{lang.upper()}] Failed to parse content for {url}.")
            continue

        print(f"Title found: {data['title']}")
        
        print(f"Generating {lang} summary with Gemini...")
        summarizer = GeminiSummarizer()
        post_text = summarizer.summarize(data['title'], data['content'], lang=lang)
        
        uploaded_image_urn = None
        if data['images']:
            print("Found image, uploading to LinkedIn...")
            # For simplicity, take the first image found
            uploaded_image_urn = poster.upload_image(data['images'][0])
            if uploaded_image_urn:
                print(f"Successfully uploaded image: {uploaded_image_urn}")
            else:
                print("Failed to upload image.")

        print("-" * 30)
        print(f"Post Preview ({lang.upper()}):")
        if uploaded_image_urn:
            print(f"[Image Attached: {data['images'][0][:100]}...]") 
        print(post_text)
        print(f"\n출처: {url}")
        print("-" * 30)

        confirm = input(f"Do you want to post this ({lang.upper()}) to LinkedIn? (y/n): ")
        if confirm.lower() == 'y':
            result = poster.post_text(post_text, title=data['title'], original_url=url, uploaded_image_urn=uploaded_image_urn)
            if result:
                print(f"[{lang.upper()}] Post successful!")
            else:
                print(f"[{lang.upper()}] Post failed. Check your tokens and permissions.")
        else:
            print(f"[{lang.upper()}] Post cancelled.")

if __name__ == "__main__":
    main()

