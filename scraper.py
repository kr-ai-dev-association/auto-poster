import requests
from bs4 import BeautifulSoup
import re
import base64

def fetch_html_content(url):
    try:
        response = requests.get(url, timeout=15)
        response.raise_for_status()
        return response.text
    except Exception as e:
        print(f"Error fetching {url}: {e}")
        return None

def parse_content(html, original_url):
    if not html:
        return None
    
    soup = BeautifulSoup(html, 'html.parser')
    
    # Better title extraction for Google Doc exports
    title = "No Title"
    if soup.title and soup.title.string:
        title = soup.title.string
    
    # If title is still "No Title" or looks like a placeholder, try h1 or first bold text
    if title == "No Title" or "Google Docs" in title:
        h1 = soup.find('h1')
        if h1:
            title = h1.get_text()
        else:
            # Google Docs often uses spans with specific styles for titles
            first_p = soup.find('p')
            if first_p:
                title = first_p.get_text()
    
    content = ""
    # Prioritize specific content areas for better extraction
    main_content = soup.find('main') or soup.find('article') or soup.find('div', class_='content')
    
    if main_content:
        content = main_content.get_text(separator='\n', strip=True)
    else:
        # Try to find common content containers if main/article not found
        content_div = soup.find('div', id='content') or soup.find('div', id='main')
        if content_div:
            content = content_div.get_text(separator='\n', strip=True)
        else:
            content = soup.body.get_text(separator='\n', strip=True) if soup.body else ""
    
    images = []
    # Extract images
    for img_tag in soup.find_all('img'):
        img_src = img_tag.get('src')
        if img_src:
            # Handle base64 encoded images
            if img_src.startswith('data:image'):
                images.append(img_src)
            elif img_src.startswith('http') or img_src.startswith('https'):
                images.append(img_src)
    
    return {
        "title": title.strip(),
        "content": content.strip(),
        "images": images
    }

def get_google_doc_id(wiki_url):
    match = re.search(r'wiki/([a-zA-Z0-9_-]+)', wiki_url)
    if match:
        return match.group(1)
    return None

if __name__ == "__main__":
    # Test with a Google Doc based wiki URL
    test_wiki_url = "https://tony.banya.ai/wiki/1dB5-2nmjndb_rM8Ukh6Ym1ORSTHw0jun2yMwXQBSYvs"
    doc_id = get_google_doc_id(test_wiki_url)
    if doc_id:
        google_doc_url = f"https://docs.google.com/document/d/{doc_id}/export?format=html"
        print(f"Detected wiki URL, fetching from Google Doc: {google_doc_url}")
        html = fetch_html_content(google_doc_url)
        data = parse_content(html, test_wiki_url)
        if data:
            print(f"Title: {data['title']}")
            print(f"Content snippet: {data['content'][:200]}...")
            print(f"Images count: {len(data['images'])}")
    else:
        print("Not a recognized wiki URL format.")
