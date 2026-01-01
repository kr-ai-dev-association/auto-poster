import subprocess
import os
import sys

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

def add_logo_to_video(video_input, logo_input, video_output, margin=30, logo_width=180):
    """
    Adds a static logo (bottom-right) and an animated outro logo (center zoom).
    """
    if not os.path.exists(video_input):
        print(f"Error: Video file not found: {video_input}")
        return False
    
    duration = get_video_duration(video_input)
    if duration == 0:
        return False
        
    outro_start = max(0, duration - 2)
    print(f"Adding logo and outro animation to {video_input}...")
    print(f"Video duration: {duration}s, Outro starts at: {outro_start}s")
    
    # Filter Explanation:
    # [1:v] - Logo input
    # split[static][animated] - Split logo for two uses
    # [static]scale=180:-1[st_logo] - Static watermark logo
    # [animated]scale='if(gte(t,OUTRO_START), min(800, 800*(t-OUTRO_START)/1.5), 0)':-1:eval=frame[out_logo] - Expanding logo
    # overlay=W-w-30:H-h-30 - Place static logo
    # overlay=(W-w)/2:(H-h)/2:enable='gte(t,OUTRO_START)' - Place animated logo at center
    
    filter_complex = (
        f"[1:v]split[static][animated];"
        f"[static]scale={logo_width}:-1[st_logo];"
        f"[animated]scale='if(gte(t,{outro_start}), min(800, 800*(t-{outro_start})/1.5), 0)':-1:eval=frame[out_logo];"
        f"[0:v][st_logo]overlay=W-w-{margin}:H-h-{margin}[v1];"
        f"[v1][out_logo]overlay=(W-w)/2:(H-h)/2:enable='gte(t,{outro_start})'"
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

