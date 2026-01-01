from google import genai
import os
from dotenv import load_dotenv

load_dotenv()

class GeminiSummarizer:
    def __init__(self, api_key=None):
        self.api_key = api_key or os.getenv("GEMINI_API_KEY")
            
        if self.api_key:
            self.client = genai.Client(api_key=self.api_key)
            self.model_id = 'gemini-2.0-flash'
        else:
            self.client = None

    def to_unicode_bold(self, text):
        # Simplified mapping for alphanumeric characters to Unicode bold
        bold_map = {
            'a': '𝗮', 'b': '𝗯', 'c': '𝗰', 'd': '𝗱', 'e': '𝗲', 'f': '𝗳', 'g': '𝗴', 'h': '𝗵', 'i': '𝗶', 'j': '𝗷', 'k': '𝗸', 'l': '𝗹', 'm': '𝗺',
            'n': '𝗻', 'o': '𝗼', 'p': '𝗽', 'q': '𝗾', 'r': '𝗿', 's': '𝘀', 't': '𝘁', 'u': '𝘂', 'v': '𝘃', 'w': '𝘄', 'x': '𝘅', 'y': '𝘆', 'z': '𝘇',
            'A': '𝗔', 'B': '𝗕', 'C': '𝗖', 'D': '𝗗', 'E': '𝗘', 'F': '𝗙', 'G': '𝗚', 'H': '𝗛', 'I': '𝗜', 'J': '𝗝', 'K': '𝗞', 'L': '𝗟', 'M': '𝗠',
            'N': '𝗡', 'O': '𝗢', 'P': '𝗣', 'Q': '𝗤', 'R': '𝗥', 'S': '𝗦', 'T': '𝗧', 'U': '𝗨', 'V': '𝗩', 'W': '𝗪', 'X': '𝗫', 'Y': '𝗬', 'Z': '𝗭',
            '0': '𝟬', '1': '𝟭', '2': '𝟮', '3': '𝟯', '4': '𝟰', '5': '𝟱', '6': '𝟲', '7': '𝟳', '8': '𝟴', '9': '𝟵'
        }
        return "".join(bold_map.get(c, c) for c in text)

    def post_process_bold(self, text):
        import re
        # Find **text** or __text__ and replace with unicode bold
        def replace_bold(match):
            content = match.group(1)
            return self.to_unicode_bold(content)
        
        text = re.sub(r'\*\*(.*?)\*\*', replace_bold, text)
        text = re.sub(r'__(.*?)__', replace_bold, text)
        return text

    def summarize(self, title, content, lang='ko'):
        if not self.client:
            return self._fallback_summary(title, content, lang)

        max_char_limit = 2400 # Conservative limit for LinkedIn (UTF-16)
        
        if lang == 'en':
            prompt = f"""
            You are a professional Tech Curator and Social Media Strategist.
            Based on the title and content provided, write a deep and engaging LinkedIn post in English.
            
            [Persona & Tone]
            - Professional, analytical, and insightful.
            - Objective curator style.
            - Use a "Tech Insight" persona.
            
            [Instructions - Important]
            1. **Hook the reader**: Start with a curiosity-inducing question or provocative statement.
            2. **Depth with Brevity**: Provide a detailed summary but keep it concise.
            3. **No Markdown**: Do NOT use ** or __.
            4. **Structure**: Hook, Context, 3-5 Bullet Points, Conclusion.
            5. **Spacing**: Use double line breaks between sections.
            6. **Hashtags**: Include 5 relevant hashtags at the bottom.
            7. **No URLs**: Do NOT include any links in your summary.
            8. **STRICT Length Limit**: The summary MUST be under 2200 characters.
            
            Title: {title}
            Content: {content}
            """
        else:
            prompt = f"""
            당신은 전문 기술 큐레이터이자 소셜 미디어 전략가입니다. 
            제공된 제목과 내용을 바탕으로 깊이 있고 몰입감 있는 LinkedIn 포스트를 한국어로 작성해주세요.
            
            [페르소나 및 톤앤매너]
            - 전문적이고 분석적이며 통찰력 있는 어조.
            - 객관적인 기술 리포트 스타일.
            
            [지침 - 중요]
            1. **강렬한 후킹**: 독자의 호기심을 자극하는 화두로 시작하세요.
            2. **핵심 요약**: 핵심 원리와 임팩트를 상세하되 간결하게 설명하세요.
            3. **마크다운 절대 금지**: (#, ##, **, __ 등) 마크다운을 지원하지 않습니다. 
            4. **유니코드 볼드**: 강조가 필요한 용어에만 유니코드 볼드체(예: 𝗧𝗲𝘅𝘁)를 사용하세요.
            5. **구조화**: 도입부, 상세 맥락, 3~5개 분석 포인트, 결론.
            6. **해시태그**: 마지막에 관련도가 높은 해시태그를 5개 포함하세요.
            7. **URL 제외**: 요약 본문에는 링크를 포함하지 마세요.
            8. **STRICT 분량 제한**: 전체 요약문은 공백 포함 2200자를 넘지 않아야 합니다.
            
            제목: {title}
            내용: {content}
            """
        
        try:
            response = self.client.models.generate_content(
                model=self.model_id,
                contents=prompt
            )
            text = response.text.strip()
            text = self.post_process_bold(text)
            
            # Final safety check for length (counting UTF-16 code units for LinkedIn)
            def get_utf16_len(s):
                return len(s.encode('utf-16-le')) // 2

            while get_utf16_len(text) > max_char_limit:
                lines = text.split('\n')
                if len(lines) > 1:
                    text = '\n'.join(lines[:-1]).strip()
                else:
                    text = text[:max_char_limit-3].strip() + "..."
                if not text: break
            
            return text
        except Exception as e:
            print(f"Error generating summary with Gemini: {e}")
            return self._fallback_summary(title, content, lang)

    def _fallback_summary(self, title, content, lang='ko'):
        bold_title = self.to_unicode_bold(title)
        if lang == 'en':
            text = f"🚀 {bold_title}\n\n"
            text += "The landscape of technology is shifting. Are we prepared for what's next?\n\n"
            text += "This report dives deep into the strategic implications of current technical trends and why they matter for the future of the industry.\n\n"
            text += "• Understanding the core architectural shifts\n"
            text += "• Analyzing the impact on developer productivity\n"
            text += "• Strategic optimal points for enterprise scaling\n\n"
            text += "Explore the full technical breakdown below.\n\n"
            text += "#TechInsight #FutureOfTech #AI #Engineering #StrategicTech"
        else:
            text = f"🚀 {bold_title}\n\n"
            text += "기술의 패러다임이 변하고 있습니다. 우리는 다가올 변화에 얼마나 준비되어 있을까요?\n\n"
            text += "본 리포트는 현재 진행 중인 기술적 전환의 핵심 원리와 그것이 산업 전반에 미칠 전략적 영향력을 심층 분석합니다.\n\n"
            text += "• 아키텍처의 근본적인 변화와 그 배경\n"
            text += "• 개발 생산성 및 생태계에 미치는 실질적 임팩트\n"
            text += "• 기업 규모 확장을 위한 전략적 최적점 분석\n\n"
            text += "상세한 기술 분석 내용을 아래 링크를 통해 확인해 보시기 바랍니다.\n\n"
            text += "#기술인사이트 #미래기술 #AI #엔지니어링 #전략기술"
        return text

if __name__ == "__main__":
    summarizer = GeminiSummarizer()
    print(summarizer.summarize("테스트 제목", "테스트 내용입니다. " * 10))
