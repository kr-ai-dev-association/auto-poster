import os
import glob
import re
from google import genai
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

class MDToHTMLConverter:
    def __init__(self, api_key=None):
        self.api_key = api_key or os.getenv("GEMINI_API_KEY")
        if self.api_key:
            self.client = genai.Client(api_key=self.api_key)
            # User requested gemini-3-flash-preview
            self.model_id = 'gemini-3-flash-preview' 
        else:
            self.client = None
            print("Error: GEMINI_API_KEY not found in .env file.")

    def _get_template_styles(self):
        """Extract styles from template.html."""
        try:
            with open("template.html", "r", encoding="utf-8") as f:
                content = f.read()
                style_match = re.search(r'<style>(.*?)</style>', content, re.DOTALL)
                if style_match:
                    return style_match.group(1).strip()
        except Exception as e:
            print(f"Warning: Could not read styles from template.html: {e}")
        return ""

    def convert_file(self, md_file_path, output_dir="html"):
        """Convert a single MD file to HTML using Gemini."""
        if not self.client:
            return

        filename = os.path.basename(md_file_path)
        base_name = os.path.splitext(filename)[0]
        output_file_path = os.path.join(output_dir, f"{base_name}.html")

        with open(md_file_path, 'r', encoding='utf-8') as f:
            md_content = f.read()

        print(f"--- Converting {filename} to HTML ---")

        template_styles = self._get_template_styles()

        prompt = f"""
You are an expert web developer and technical writer. 
Convert the following Markdown content into a clean, professional, and responsive HTML document.

[CRITICAL REQUIREMENTS]
1. **Structure**: Use the following HTML structure for the <body>:
   <article class="wiki-content">
     <div class="flex justify-between items-start border-b border-[#a2a9b1] pb-2 mb-6">
       <h1 class="text-3xl font-sans font-bold text-[#000] leading-tight">{{{{TITLE}}}}</h1>
       <div class="flex items-center gap-2 mt-2 ml-4 shrink-0">
         <button class="p-1.5 text-gray-500 hover:text-blue-600 hover:bg-gray-100 rounded-full transition-all" title="Copy Link">
           <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M10 13a5 5 0 0 0 7.54.54l3-3a5 5 0 0 0-7.07-7.07l-1.72 1.71"></path><path d="M14 11a5 5 0 0 0-7.54-.54l-3 3a5 5 0 0 0 7.07 7.07l1.71-1.71"></path></svg>
         </button>
       </div>
     </div>
     <div class="wiki-html-content prose prose-slate max-w-none text-[#202122] leading-relaxed">
       <style>
         {template_styles}
       </style>
       {{{{CONTENT_IN_HTML}}}}
     </div>
     <div class="mt-12 pt-4 border-t border-[#a2a9b1] text-xs text-[#444] font-medium italic">
        This page was last edited on Dec 30, 2025.
     </div>
   </article>

2. **Styles & Layout**: 
   - Use Tailwind CSS for responsiveness and layout. Include:
     <script src="https://cdn.tailwindcss.com"></script>
     <script src="https://cdn.tailwindcss.com?plugins=typography"></script>
   - Ensure the generated HTML content inside .wiki-html-content uses appropriate semantic tags (h2, h3, p, ul, li, etc.) and matches the aesthetic of the template.

3. **MathJax v3 Integration**:
   - Any LaTeX formulas in the Markdown (e.g., $...$ or $$...$$) MUST be preserved exactly in the HTML so MathJax can render them.
   - Include the following MathJax configuration and script in the <head>:
     <script>
       window.MathJax = {{
         tex: {{
           inlineMath: [['$', '$'], ['\\\\(', '\\\\)']],
           displayMath: [['$$', '$$'], ['\\\\[', '\\\\]']],
           processEscapes: true,
           packages: {{'[+]': ['base', 'ams', 'noerrors', 'noundefined']}}
         }},
         svg: {{ fontCache: 'global', scale: 1.0, displayAlign: 'center' }},
         startup: {{ typeset: true }}
       }};
     </script>
     <script src="https://cdn.jsdelivr.net/npm/mathjax@3/es5/tex-svg.js" id="MathJax-script" async></script>

4. **Output**: 
   - Return a COMPLETE, valid HTML5 document starting with <!DOCTYPE html>.
   - The <head> should include appropriate meta tags, title, Tailwind scripts, and MathJax setup.
   - The <body> should contain the <article> structure described above.
   - DO NOT include markdown code fences (like ```html) or any extra text.

[MARKDOWN CONTENT TO CONVERT]
{md_content}
"""

        try:
            response = self.client.models.generate_content(
                model=self.model_id,
                contents=prompt
            )
            html_output = response.text.strip()
            
            # Remove any accidental markdown formatting from the response
            html_output = re.sub(r'^```html\s*', '', html_output)
            html_output = re.sub(r'\s*```$', '', html_output)

            os.makedirs(output_dir, exist_ok=True)
            with open(output_file_path, 'w', encoding='utf-8') as f:
                f.write(html_output)
            
            print(f"Successfully converted and saved to: {output_file_path}")
        except Exception as e:
            print(f"Error during Gemini API call for {filename}: {e}")

def main():
    # Ensure source directory exists
    if not os.path.exists("source"):
        print("Error: 'source' directory not found.")
        return

    converter = MDToHTMLConverter()
    md_files = glob.glob("source/*.md")
    
    if not md_files:
        print("No markdown files found in 'source/' directory.")
        return

    for md_file in md_files:
        converter.convert_file(md_file)

if __name__ == "__main__":
    main()

