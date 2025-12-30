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
                # gemini-2.5-flash-image uses generate_content for image output
                # Requested 16:9 aspect ratio
                response = self.client.models.generate_content(
                    model=self.image_model_id,
                    contents=f"Generate a professional technical illustration in 16:9 aspect ratio for: {visual_prompt}"
                )
                for candidate in response.candidates:
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

    def convert_file(self, md_file_path, output_dir="html"):
        """Convert a single MD file to both KO and EN HTML versions using a single shared summary image."""
        if not self.client:
            return

        filename = os.path.basename(md_file_path)
        base_name = os.path.splitext(filename)[0]

        with open(md_file_path, 'r', encoding='utf-8') as f:
            md_content = f.read()

        tqdm.write(f"--- Processing {filename} ---")

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
        # Using the translated English base name for the image file
        image_rel_path = self._generate_summary_image(md_content, en_base_name, "shared", output_dir)
        image_html = ""
        if image_rel_path:
            image_html = f'<div class="my-6 rounded-lg overflow-hidden border border-[#a2a9b1] shadow-sm"><img src="{image_rel_path}" alt="Summary Image" class="w-full h-auto object-cover" style="aspect-ratio: 16/9;"></div>'

        template_styles = self._get_template_styles()

        # 3. Generate both HTML versions
        for lang in ["ko", "en"]:
            lang_label = "Korean" if lang == "ko" else "English"
            translation_instruction = ""
            target_filename = f"{base_name}_ko.html" if lang == "ko" else f"{en_base_name}.html"

            if lang == "en":
                translation_instruction = "IMPORTANT: First, translate the entire content into natural, professional technical English."
            
            tqdm.write(f"  - Generating {lang_label} version...")

            prompt = f"""
You are an expert web developer, technical writer, and translator. 
{translation_instruction}

Convert the following Markdown content into a clean, professional, and responsive HTML document in {lang_label}.

[CRITICAL REQUIREMENTS]
1. **Structure**: Use the following HTML structure for the <body>:
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
                output_file_path = os.path.join(output_dir, target_filename)
                with open(output_file_path, 'w', encoding='utf-8') as f:
                    f.write(html_output)
                
                tqdm.write(f"    - Successfully saved to: {output_file_path}")
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
        if not os.path.exists(dest_dir):
            os.makedirs(dest_dir, exist_ok=True)
        
        # Copy all HTML files
        for html_file in glob.glob(os.path.join(output_dir, "*.html")):
            shutil.copy2(html_file, dest_dir)
            
        # Copy images directory
        src_images = os.path.join(output_dir, "images")
        dest_images = os.path.join(dest_dir, "images")
        if os.path.exists(src_images):
            if os.path.exists(dest_images):
                # Using copytree with dirs_exist_ok=True (Python 3.8+)
                shutil.copytree(src_images, dest_images, dirs_exist_ok=True)
            else:
                shutil.copytree(src_images, dest_images)
        
        print(f"✅ Successfully copied all files to {dest_dir}")
    except Exception as e:
        print(f"❌ Error during file copy: {e}")

    print("\n✨ All tasks completed!")

if __name__ == "__main__":
    main()

