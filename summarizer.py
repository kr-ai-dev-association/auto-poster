from google import genai
import os
from dotenv import load_dotenv

load_dotenv()

class GeminiSummarizer:
    def __init__(self, api_key=None):
        self.api_key = api_key or os.getenv("GEMINI_API_KEY")
            
        if self.api_key:
            self.client = genai.Client(api_key=self.api_key)
            self.model_id = 'gemini-flash-latest'
        else:
            self.client = None

    def summarize(self, title, content, lang='ko'):
        if not self.client:
            return f"📢 {title}\n\n{content[:500]}..."

        if lang == 'en':
            prompt = f"""
            You are a professional social media manager. 
            Based on the title and content of the webpage provided below, write the best post to publish on LinkedIn in English.
            
            [Instructions - Important]
            1. LinkedIn does not support Markdown. Use Unicode Bold (e.g., 𝗧𝗲𝘅𝘁) for emphasis where needed.
            2. The first line should be a strong title using Unicode Bold and emojis.
            3. Summarize the main content into 3-5 bullet points (•).
            4. Use sufficient spacing (line breaks) between paragraphs for readability.
            5. Include 3-5 relevant hashtags at the end.
            
            Title: {title}
            Content: {content}
            """
        else:
            prompt = f"""
            당신은 전문 소셜 미디어 매니저입니다. 
            아래 제공된 웹페이지의 제목과 내용을 바탕으로 LinkedIn에 게시할 최적의 포스트를 작성해주세요. 한국어로 작성해야 합니다.
            
            [지침 - 중요]
            1. LinkedIn은 마크다운을 지원하지 않습니다. 강조하고 싶은 단어(제목 등)는 유니코드 볼드체(예: 𝗧𝗲𝘅𝘁)를 사용하여 강조 효과를 주세요.
            2. 첫 줄은 유니코드 볼드체와 이모지를 사용하여 제목을 강렬하게 작성하세요.
            3. 본문 내용을 핵심 위주로 3~5개의 불렛 포인트(•)로 요약하세요.
            4. 문단 사이에는 충분한 공백(줄바꿈)을 두어 가독성을 높이세요.
            5. 마지막에는 관련 해시태그를 3~5개 포함하세요.
            
            제목: {title}
            내용: {content}
            """
        
        try:
            response = self.client.models.generate_content(
                model=self.model_id,
                contents=prompt
            )
            return response.text.strip()
        except Exception as e:
            print(f"Error generating summary with Gemini GenAI SDK: {e}")
            return f"📢 {title}\n\n{content[:500]}..."

if __name__ == "__main__":
    # Test
    summarizer = GeminiSummarizer()
    print(summarizer.summarize("테스트 제목", "테스트 내용입니다. " * 10))
