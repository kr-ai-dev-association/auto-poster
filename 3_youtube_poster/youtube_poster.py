import sys
import os
from dotenv import load_dotenv

# Add project root to path to import from core
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from core.linkedin_poster import LinkedInPoster
from core.summarizer import GeminiSummarizer

load_dotenv()

class YouTubePoster:
    def __init__(self):
        self.poster = LinkedInPoster()
        self.summarizer = GeminiSummarizer()

    def post_video_summary(self, video_url):
        """
        Skeleton for YouTube video auto-poster.
        1. Extract transcript or info from YouTube.
        2. Summarize using Gemini.
        3. Post to LinkedIn.
        """
        print(f"Starting YouTube auto-posting for: {video_url}")
        # TODO: Implement YouTube extraction logic
        # summary = self.summarizer.summarize(title, transcript, lang='ko')
        # self.poster.post_text(summary, ...)
        print("YouTube auto-posting is currently under development.")

def main():
    video_url = input("Enter YouTube Video URL: ")
    if not video_url:
        print("No URL provided.")
        return
        
    app = YouTubePoster()
    app.post_video_summary(video_url)

if __name__ == "__main__":
    main()

