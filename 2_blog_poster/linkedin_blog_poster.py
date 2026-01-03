import sys
import json
import os
import glob
from dotenv import load_dotenv

# Add project root to path to import from core
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from scraper import fetch_html_content, parse_content, get_google_doc_id
from core.linkedin_poster import LinkedInPoster
from core.summarizer import GeminiSummarizer

load_dotenv()

def main():
    config = {}
    # Find blog.json in the same directory
    contents_path = os.path.join(os.path.dirname(__file__), 'blog.json')
    try:
        print(f"Loading URL from {contents_path}...")
        with open(contents_path, 'r', encoding='utf-8') as f:
            config = json.load(f)
    except FileNotFoundError:
        print(f"Error: {contents_path} not found. Please provide a valid blog.json file.")
        return

    url = config.get("url")
    if not url:
        print(f"Error: 'url' is missing in {contents_path}. Exiting.")
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

    dest_dir = "/Volumes/Transcend/Projects/tech-blog/html"
    
    # Process both Korean and English versions for the single URL
    for lang in ["en", "ko"]:
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
        
        # 1. Try to find local summary image using the slug
        for base_dir in ["html", dest_dir]:
            # Exact match first
            potential_local_path = os.path.join(base_dir, "images", f"{url_slug}_summary.png")
            if os.path.exists(potential_local_path):
                local_image_path = potential_local_path
                break
            
            # Smart match: look for any image starting with the slug
            img_dir = os.path.join(base_dir, "images")
            if os.path.exists(img_dir):
                patterns = [f"{url_slug}*_summary.png", f"*{url_slug}*_summary.png"]
                for pattern in patterns:
                    matches = glob.glob(os.path.join(img_dir, pattern))
                    if matches:
                        # Use the latest modified one
                        matches.sort(key=os.path.getmtime, reverse=True)
                        local_image_path = matches[0]
                        break
            if local_image_path: break

        # 2. If no local summary image, check extracted images from HTML
        if not local_image_path and data['images']:
            for img_src in data['images']:
                if img_src.startswith('http') or img_src.startswith('data:image'):
                    local_image_path = img_src
                    break
                else:
                    # Resolve relative path found in HTML
                    # If we found local HTML, the image might be relative to it
                    if local_html_path:
                        html_dir = os.path.dirname(local_html_path)
                        # Remove leading '../' if present as we are resolving relative to html_dir
                        clean_src = img_src
                        if clean_src.startswith('../'):
                            # Go up one level from html_dir (e.g., from html/ko to html)
                            parent_dir = os.path.dirname(html_dir)
                            resolved_path = os.path.join(parent_dir, clean_src.replace('../', '', 1))
                        else:
                            resolved_path = os.path.join(html_dir, clean_src)
                        
                        if os.path.exists(resolved_path):
                            local_image_path = resolved_path
                            break

        if local_image_path:
            if os.path.exists(local_image_path) if isinstance(local_image_path, str) and not local_image_path.startswith(('http', 'data')) else True:
                print(f"Found image to upload: {local_image_path}")
            else:
                print(f"Image source identified but path not found: {local_image_path}")
                local_image_path = None

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

