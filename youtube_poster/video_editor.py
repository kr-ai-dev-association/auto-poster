import subprocess
import os
import sys
import json

def get_video_duration(video_path):
    """Returns the duration of a video in seconds."""
    cmd = [
        'ffprobe', '-v', 'error', '-show_entries', 'format=duration',
        '-of', 'default=noprint_wrappers=1:nokey=1', video_path
    ]
    try:
        output = subprocess.check_output(cmd, text=True).strip()
        return float(output)
    except Exception as e:
        print(f"Error getting duration: {e}")
        return 0

def get_video_info(video_path):
    """Returns the duration and resolution of a video."""
    cmd = [
        'ffprobe', '-v', 'error', '-select_streams', 'v:0',
        '-show_entries', 'format=duration:stream=width,height',
        '-of', 'json', video_path
    ]
    try:
        output = subprocess.check_output(cmd, text=True).strip()
        data = json.loads(output)
        duration = float(data['format']['duration'])
        width = int(data['streams'][0]['width'])
        height = int(data['streams'][0]['height'])
        return duration, width, height
    except Exception as e:
        print(f"Error getting video info: {e}")
        return 0, 1280, 720

def add_logo_to_video(video_input, logo_input, video_output, margin=30, logo_width=180):
    """
    Adds a static logo (bottom-right) and an animated outro logo with white fade-in.
    """
    if not os.path.exists(video_input):
        print(f"Error: Video file not found: {video_input}")
        return False
    
    duration, width, height = get_video_info(video_input)
    if duration == 0:
        return False
        
    # Animation starts 3 seconds before the end
    outro_start = max(0, duration - 3)
    print(f"Adding white fade and logo animation to {video_input}...")
    print(f"Video duration: {duration}s, Outro starts at: {outro_start}s")
    
    # Filter Explanation:
    # 1. Split logo for static and animated versions.
    # 2. Create a white background that fades in over 1.5 seconds.
    # 3. Scale animated logo from 0 to 800px over 2 seconds.
    # 4. Overlay static logo, white fade-in, draw italic URL, and then the animated center logo.
    
    font_path = "/System/Library/Fonts/Supplemental/Arial Italic.ttf"
    
    filter_complex = (
        f"[1:v]split[static][animated];"
        f"[static]scale={logo_width}:-1[st_logo];"
        f"[animated]scale='if(gte(t,{outro_start}), min(800, 800*(t-{outro_start})/2.0), 0)':-1:eval=frame[out_logo];"
        f"color=c=white:s={width}x{height}:d=3[white_src];"
        f"[white_src]fade=t=in:st=0:d=1.5:alpha=1[white_bg];"
        f"[0:v][st_logo]overlay=W-w-{margin}:H-h-{margin}[v1];"
        f"[v1][white_bg]overlay=enable='gte(t,{outro_start})'[v2];"
        f"[v2]drawtext=text='https\\://banya.ai':fontfile='{font_path}':fontsize=45:fontcolor=black:x=(w-tw)/2:y=(h/2)+130:enable='gte(t,{outro_start})'[v3];"
        f"[v3][out_logo]overlay=(W-w)/2:(H-h)/2:enable='gte(t,{outro_start})'"
    )
    
    cmd = [
        'ffmpeg', '-y',
        '-i', video_input,
        '-i', logo_input,
        '-filter_complex', filter_complex,
        '-c:a', 'copy',
        video_output
    ]
    
    try:
        process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        stdout, stderr = process.communicate()
        
        if process.returncode == 0:
            print(f"Successfully created: {video_output}")
            return True
        else:
            print(f"Error in ffmpeg processing: {stderr}")
            return False
    except Exception as e:
        print(f"Exception during video editing: {e}")
        return False

if __name__ == "__main__":
    # Test script
    base_dir = os.path.dirname(os.path.abspath(__file__))
    v_source_dir = os.path.join(base_dir, 'v_source')
    
    # Find mp4 and png
    video_files = [f for f in os.listdir(v_source_dir) if f.endswith('.mp4') and 'preview' not in f and 'final_video' not in f]
    logo_files = [f for f in os.listdir(v_source_dir) if f.endswith('.png')]
    
    if not video_files or not logo_files:
        print("Error: Could not find video or logo in v_source.")
        sys.exit(1)
        
    input_video = os.path.join(v_source_dir, video_files[0])
    input_logo = os.path.join(v_source_dir, logo_files[0])
    output_video = os.path.join(v_source_dir, "preview_with_logo.mp4")
    
    print(f"Testing logo overlay...")
    print(f"Video: {input_video}")
    print(f"Logo: {input_logo}")
    
    if add_logo_to_video(input_video, input_logo, output_video):
        print("\nVerification process complete.")
        print(f"Please check the preview file: {output_video}")
    else:
        print("\nLogo overlay failed.")

