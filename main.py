import sys
import json
import os
import glob
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

    dest_dir = "/Volumes/Transcend/Projects/tech-blog/html"
    
    for lang, data_entry in default_urls.items():
        url = data_entry.get("url")
        if not url:
            print(f"Skipping {lang} as URL is missing in contents.json")
            continue

        # Try to find local content first if it exists, otherwise check deployment dir
        url_slug = url.split('/')[-1]
        
        # Possible locations to check
        search_dirs = ["html", dest_dir]
        local_html_path = None
        
        for base_dir in search_dirs:
            if lang == 'ko':
                potential_ko_path = os.path.join(base_dir, "ko", f"{url_slug}_ko.html")
                if os.path.exists(potential_ko_path):
                    local_html_path = potential_ko_path
                    break
                else:
                    # Fallback: search for any _ko.html file
                    ko_files = glob.glob(os.path.join(base_dir, "ko", "*_ko.html"))
                    if ko_files:
                        ko_files.sort(key=os.path.getmtime, reverse=True)
                        local_html_path = ko_files[0]
                        break
            else:
                potential_en_path = os.path.join(base_dir, "en", f"{url_slug}_en.html")
                if os.path.exists(potential_en_path):
                    local_html_path = potential_en_path
                    break
        
        data = None
        if local_html_path and os.path.exists(local_html_path):
            print(f"[{lang.upper()}] Found local HTML content: {local_html_path}")
            with open(local_html_path, 'r', encoding='utf-8') as f:
                local_html = f.read()
            data = parse_content(local_html, url)
        
        if not data:
            print(f"[{lang.upper()}] 콘텐츠 읽는 중: {url}")
            # ... (rest of the fetching logic)

        if not data or not data['content']:
            print(f"[{lang.upper()}] Failed to parse content for {url}.")
            continue

        print(f"Title found: {data['title']}")
        
        # Check for local summary image if no images found or as priority
        local_image_path = None
        url_slug = url.split('/')[-1]
        
        # Check in both local and deployment image directories
        for base_dir in ["html", dest_dir]:
            potential_local_path = os.path.join(base_dir, "images", f"{url_slug}_summary.png")
            if os.path.exists(potential_local_path):
                print(f"Found local summary image: {potential_local_path}")
                local_image_path = potential_local_path
                break
        
        if not local_image_path and data['images']:
            print(f"Using first image found on page: {data['images'][0][:50]}...")
            local_image_path = data['images'][0]

        print(f"Generating {lang} summary with Gemini...")
        summarizer = GeminiSummarizer()
        generated_summary = summarizer.summarize(data['title'], data['content'], lang=lang)
        
        # Append the blog link at the end with more spacing
        if lang == 'en':
            post_text = f"{generated_summary}\n\n\n👉 Read more:\n{url}"
        else:
            post_text = f"{generated_summary}\n\n\n👉 자세히 보기:\n{url}"
        
        uploaded_image_urn = None
        if local_image_path:
            print(f"Uploading image to LinkedIn: {local_image_path}")
            uploaded_image_urn = poster.upload_image(local_image_path)
            if uploaded_image_urn:
                print(f"Successfully uploaded image: {uploaded_image_urn}")
            else:
                print("Failed to upload image.")
        else:
            print("No image found to upload.")

        print("-" * 30)
        print(f"Post Preview ({lang.upper()}):")
        if uploaded_image_urn:
            print(f"[Image Attached: {local_image_path}]") 
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

