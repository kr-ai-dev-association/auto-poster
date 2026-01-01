import subprocess
import os
import sys

def add_logo_to_video(video_input, logo_input, video_output, margin=30, logo_width=150):
    """
    Adds a logo to the bottom-right corner of a video using ffmpeg.
    
    Args:
        video_input (str): Path to input video.
        logo_input (str): Path to logo image.
        video_output (str): Path to output video.
        margin (int): Margin from the edges in pixels.
        logo_width (int): Target width for the logo in pixels (maintains aspect ratio).
    """
    if not os.path.exists(video_input):
        print(f"Error: Video file not found: {video_input}")
        return False
    if not os.path.exists(logo_input):
        print(f"Error: Logo file not found: {logo_input}")
        return False

    print(f"Adding logo to {video_input}...")
    
    # FFmpeg command:
    # 1. Resize logo to specified width
    # 2. Overlay it in the bottom-right corner with margin
    # We use -c:a copy to avoid re-encoding audio
    cmd = [
        'ffmpeg', '-y',
        '-i', video_input,
        '-i', logo_input,
        '-filter_complex', f"[1:v]scale={logo_width}:-1 [logo]; [0:v][logo]overlay=W-w-{margin}:H-h-{margin}",
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
    video_files = [f for f in os.listdir(v_source_dir) if f.endswith('.mp4')]
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

