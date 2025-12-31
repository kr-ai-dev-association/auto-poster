import os
import glob
import re
import base64
import io
import shutil
from tqdm import tqdm
from PIL import Image
from google import genai
from google.genai import types
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

class MDToHTMLConverter:
    def __init__(self, api_key=None):
        self.api_key = api_key or os.getenv("GEMINI_API_KEY")
        if self.api_key:
            self.client = genai.Client(api_key=self.api_key)
            # User requested gemini-3-flash-preview for text
            self.model_id = 'gemini-3-flash-preview' 
            # Added models/ prefix to the requested model name
            self.image_model_id = 'models/gemini-2.5-flash-image'
        else:
            self.client = None
            print("Error: GEMINI_API_KEY not found in .env file.")

    def _generate_summary_image(self, md_content, output_base_name, lang, output_dir):
        """Generate a summary image using Gemini image model."""
        if not self.client:
            return None

        # 1. Get a visual prompt from Gemini based on content
        try:
            visual_prompt_query = f"""
            Based on the following technical content, create a concise, artistic, and professional image generation prompt (in English) 
            that summarizes the key concept visually. The image should be suitable for a tech wiki header.
            
            Content:
            {md_content[:2000]} 
            """
            
            prompt_res = self.client.models.generate_content(
                model=self.model_id,
                contents=visual_prompt_query
            )
            visual_prompt = prompt_res.text.strip()
        except Exception as e:
            tqdm.write(f"    - Failed to generate visual prompt: {e}")
            return None

        # 2. Generate the image
        try:
            image_data = None
            if "gemini-2.5-flash-image" in self.image_model_id:
                response = self.client.models.generate_content(
                    model=self.image_model_id,
                    contents=f"Generate a professional technical illustration in 16:9 aspect ratio for: {visual_prompt}"
                )
                
                if not response.candidates:
                    tqdm.write(f"    - Image generation response has no candidates. Response: {response}")
                
                for candidate in response.candidates:
                    if candidate.finish_reason and candidate.finish_reason != "STOP":
                        tqdm.write(f"    - Image generation finished with reason: {candidate.finish_reason}")
                    
                    if not candidate.content or not candidate.content.parts:
                        continue
                        
                    for part in candidate.content.parts:
                        if part.inline_data and "image" in part.inline_data.mime_type:
                            image_data = part.inline_data.data
                            break
                    if image_data: break
            else:
                # Standard image models (like Imagen) use generate_images
                # Requested 16:9 aspect ratio
                image_response = self.client.models.generate_images(
                    model=self.image_model_id,
                    prompt=visual_prompt,
                    config=types.GenerateImagesConfig(
                        number_of_images=1,
                        aspect_ratio="16:9",
                        include_rai_reason=True
                    )
                )
                if image_response.generated_images:
                    image_data = image_response.generated_images[0].image_bytes
            
            if not image_data:
                tqdm.write("    - No image was generated.")
                return None

            # 3. Process and crop image to 16:9
            try:
                img = Image.open(io.BytesIO(image_data))
                width, height = img.size
                target_ratio = 16 / 9
                current_ratio = width / height

                if current_ratio > target_ratio:
                    # Too wide, crop sides
                    new_width = height * target_ratio
                    left = (width - new_width) / 2
                    right = (width + new_width) / 2
                    top = 0
                    bottom = height
                    img = img.crop((left, top, right, bottom))
                elif current_ratio < target_ratio:
                    # Too tall, crop top and bottom
                    new_height = width / target_ratio
                    left = 0
                    right = width
                    top = (height - new_height) / 2
                    bottom = (height + new_height) / 2
                    img = img.crop((left, top, right, bottom))
                
                # Convert back to bytes for saving
                img_byte_arr = io.BytesIO()
                img.save(img_byte_arr, format='PNG')
                image_data = img_byte_arr.getvalue()
            except Exception as e:
                tqdm.write(f"    - Image cropping failed: {e}")

            # 4. Save the image
            images_dir = os.path.join(output_dir, "images")
            os.makedirs(images_dir, exist_ok=True)
            
            image_filename = f"{output_base_name}_summary.png"
            image_path = os.path.join(images_dir, image_filename)
            
            with open(image_path, "wb") as f:
                f.write(image_data)
            
            tqdm.write(f"    - Successfully generated summary image: {image_path}")
            return f"images/{image_filename}"
        except Exception as e:
            tqdm.write(f"    - Error during image generation with {self.image_model_id}: {e}")
            return None

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

    def _post_process_math_spacing(self, html_content):
        """Remove unnatural line breaks and block tags around inline math formulas."""
        # 1. Remove <p>, <div>, or <br> tags that isolate an inline formula
        html_content = re.sub(r'<(p|div|span)[^>]*>\s*(\$[^\$]+\$)\s*</\1>', r' \2 ', html_content)
        html_content = re.sub(r'<br\s*/?>\s*(\$[^\$]+\$)', r' \1', html_content)
        html_content = re.sub(r'(\$[^\$]+\$)\s*<br\s*/?>', r'\1 ', html_content)
        
        # 2. Remove newlines and multiple spaces immediately before or after inline formulas
        html_content = re.sub(r'\s*\n\s*(\$[^\$]+\$)\s*', r' \1 ', html_content)
        html_content = re.sub(r'\s*(\$[^\$]+\$)\s*\n\s*', r' \1 ', html_content)
        
        # 3. Clean up leading/trailing spaces inside parent tags if they surround math
        html_content = re.sub(r'>\s*(\$[^\$]+\$)\s*<', r'>\1<', html_content)

        return html_content

    def convert_file(self, md_file_path, output_dir="html"):
        """Convert a single MD file to both KO and EN HTML versions using a single shared summary image."""
        if not self.client:
            return

        filename = os.path.basename(md_file_path)
        base_name = os.path.splitext(filename)[0]

        with open(md_file_path, 'r', encoding='utf-8') as f:
            md_content = f.read()

        tqdm.write(f"--- Processing {filename} ---")

        # Create subdirectories
        ko_dir = os.path.join(output_dir, "ko")
        en_dir = os.path.join(output_dir, "en")
        images_dir = os.path.join(output_dir, "images")
        for d in [ko_dir, en_dir, images_dir]:
            os.makedirs(d, exist_ok=True)

        # 1. Determine English filename first (to use for the shared image name)
        tqdm.write(f"  - Translating filename for English version...")
        en_base_name = f"{base_name}_en"
        try:
            name_prompt = f"Translate this title into a concise, professional English filename (no extension, lowercase, use hyphens for spaces): {base_name}"
            name_response = self.client.models.generate_content(model=self.model_id, contents=name_prompt)
            translated_base = name_response.text.strip().lower().replace(" ", "-")
            en_base_name = re.sub(r'[^\w\-_\.]', '', translated_base)
        except Exception as e:
            tqdm.write(f"    - Filename translation failed, using default: {e}")

        # 2. Generate a single summary image (shared by both versions)
        # Images are stored in html/images/, so the relative path for HTML in html/ko/ or html/en/ 
        # needs to go up one level: ../images/
        image_rel_path_for_html = self._generate_summary_image(md_content, en_base_name, "shared", output_dir)
        # Fix relative path for nested HTML structure
        if image_rel_path_for_html:
            image_rel_path_for_html = f"../{image_rel_path_for_html}"
        
        image_html = ""
        if image_rel_path_for_html:
            image_html = f'<div class="my-6 rounded-lg overflow-hidden border border-[#a2a9b1] shadow-sm"><img src="{image_rel_path_for_html}" alt="Summary Image" class="w-full h-auto object-cover" style="aspect-ratio: 16/9;"></div>'

        template_styles = self._get_template_styles()

        # 3. Generate both HTML versions
        for lang in ["ko", "en"]:
            lang_label = "Korean" if lang == "ko" else "English"
            translation_instruction = ""
            
            # Both versions now use the same English base name for path consistency
            if lang == "ko":
                target_filename = f"{en_base_name}_ko.html"
                target_path = os.path.join(ko_dir, target_filename)
            else:
                target_filename = f"{en_base_name}_en.html"
                target_path = os.path.join(en_dir, target_filename)
                translation_instruction = "IMPORTANT: First, translate the entire content into natural, professional technical English."
            
            tqdm.write(f"  - Generating {lang_label} version...")

            prompt = f"""
You are an expert web developer, technical writer, and translator. 
{translation_instruction}

Convert the following Markdown content into a clean, professional, and responsive HTML document in {lang_label}.

[CRITICAL REQUIREMENTS]
1. **Structure**: Use the exact HTML structure provided below for the <body>. 
   - **DO NOT CHANGE** the <img> tag's `src` attribute. Use the provided {image_html} as-is.
   <article class="wiki-content">
     <div class="flex justify-between items-start border-b border-[#a2a9b1] pb-2 mb-6">
       <h1 class="text-3xl font-sans font-bold text-[#000] leading-tight">{{{{TITLE_IN_{lang.upper()}}}}}</h1>
       <div class="flex items-center gap-2 mt-2 ml-4 shrink-0">
         <button class="p-1.5 text-gray-500 hover:text-blue-600 hover:bg-gray-100 rounded-full transition-all" title="Copy Link">
           <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M10 13a5 5 0 0 0 7.54.54l3-3a5 5 0 0 0-7.07-7.07l-1.72 1.71"></path><path d="M14 11a5 5 0 0 0-7.54-.54l-3 3a5 5 0 0 0 7.07 7.07l1.71-1.71"></path></svg>
         </button>
       </div>
     </div>

     {image_html}

     <div class="wiki-html-content prose prose-slate max-w-none text-[#202122] leading-relaxed">
       <style>
         {template_styles}
       </style>
       {{{{CONTENT_IN_HTML_IN_{lang.upper()}}}}}
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

3. **MathJax v3 Integration & Formatting**:
   - Any LaTeX formulas in the Markdown (e.g., $...$ or $$...$$) MUST be preserved exactly in the HTML.
   - **IMPORTANT**: Single dollar sign formulas (e.g., $x$) are INLINE math. DO NOT put them on a new line or wrap them in block elements like <div> or <p>. They must remain part of the surrounding text line to prevent unnatural line breaks.
   - Only double dollar sign formulas (e.g., $$...$$) should be treated as display/block math.
   - Include the following MathJax configuration, style, and script in the <head>:
     <style>
       mjx-container {{
         display: inline !important;
         margin: 0 !important;
         vertical-align: middle;
         white-space: nowrap !important;
       }}
       mjx-container[display="true"] {{
         display: block !important;
         margin: 1.5em 0 !important;
         text-align: center;
         white-space: normal !important;
       }}
       /* Prevent Tailwind prose from breaking math */
       .prose mjx-container {{
         display: inline-block !important;
       }}
       /* Force text color to black and code block styles */
       .wiki-html-content {{
         color: #000 !important;
       }}
       .wiki-html-content pre {{
         background-color: #000 !important;
         color: #fff !important;
         padding: 1.5em !important;
         border-radius: 0.5rem !important;
         overflow-x: auto !important;
       }}
       .wiki-html-content code {{
         background-color: #000 !important;
         color: #fff !important;
         padding: 0.2em 0.4em !important;
         border-radius: 0.25rem !important;
         font-size: 0.9em !important;
       }}
       /* Keep inline code blocks from looking weird inside paragraphs */
       p code, li code {{
         display: inline !important;
         vertical-align: baseline !important;
       }}
     </style>
     <script>
       window.MathJax = {{
         tex: {{
           inlineMath: [['$', '$'], ['\\\\(', '\\\\)']],
           displayMath: [['$$', '$$'], ['\\\\[', '\\\\]']],
           processEscapes: true,
           packages: {{'[+]': ['base', 'ams', 'noerrors', 'noundefined']}}
         }},
         svg: {{ fontCache: 'global', scale: 1.0 }},
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

                # Post-process to fix math spacing issue
                html_output = self._post_process_math_spacing(html_output)

                os.makedirs(os.path.dirname(target_path), exist_ok=True)
                with open(target_path, 'w', encoding='utf-8') as f:
                    f.write(html_output)
                
                tqdm.write(f"    - Successfully saved to: {target_path}")
            except Exception as e:
                tqdm.write(f"    - Error during Gemini API call for {lang}: {e}")

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

    output_dir = "html"
    dest_dir = "/Volumes/Transcend/Projects/tech-blog/html"

    print(f"🚀 Starting conversion of {len(md_files)} files...")
    
    # Progress bar for the entire process
    for md_file in tqdm(md_files, desc="Converting MD to HTML", unit="file"):
        converter.convert_file(md_file, output_dir=output_dir)

    # Copy files to destination after all conversions are done
    print(f"\n📂 Copying generated files to {dest_dir}...")
    try:
        if os.path.exists(output_dir):
            if os.path.exists(dest_dir):
                # Using copytree with dirs_exist_ok=True (Python 3.8+)
                shutil.copytree(output_dir, dest_dir, dirs_exist_ok=True)
            else:
                shutil.copytree(output_dir, dest_dir)
            
            print(f"✅ Successfully copied all files to {dest_dir}")
            
            # Clean up: Delete local html/ directory after successful deployment
            print(f"🧹 Cleaning up local {output_dir} directory...")
            shutil.rmtree(output_dir)
            print(f"✅ Cleanup complete.")
        else:
            print(f"⚠️ No files were generated in {output_dir} to copy.")
        
    except Exception as e:
        print(f"❌ Error during file copy or cleanup: {e}")

    print("\n✨ All tasks completed!")

if __name__ == "__main__":
    main()

