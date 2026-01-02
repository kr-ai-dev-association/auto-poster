import os
import sys
import json

# Add project root to path to import from core
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from youtube_poster import YouTubeAutoPoster

def main():
    poster = YouTubeAutoPoster()
    base_v_dir = os.path.join(os.path.dirname(__file__), 'v_source')
    
    print("\nSelect Category for Upload:")
    print("1. tech (Default)")
    print("2. entertainment")
    cat_choice = input("Choice: ").strip()
    category = 'entertainment' if cat_choice == '2' else 'tech'
    
    v_dir = os.path.join(base_v_dir, category)
    if not os.path.exists(v_dir):
        print(f"❌ Category directory not found: {v_dir}")
        return
    
    # Find already processed video files
    video_files = [f for f in os.listdir(v_dir) if f.startswith('final_youtube_post_') and f.endswith('.mp4')]
    
    if not video_files:
        print("❌ No processed video files found in v_source.")
        print("   Look for files named 'final_youtube_post_ko.mp4' or similar.")
        return

    print("\n📦 Found processed videos:")
    for i, f in enumerate(video_files, 1):
        print(f"   {i}. {f}")
    
    choice = input("\nSelect video to upload (number): ").strip()
    try:
        idx = int(choice) - 1
        video_file = video_files[idx]
        lang = 'ko' if '_ko.mp4' in video_file else 'en'
    except (ValueError, IndexError):
        print("❌ Invalid selection.")
        return

    video_path = os.path.join(v_dir, video_file)
    metadata_path = os.path.join(v_dir, f"metadata_{lang}.json")

    if not os.path.exists(metadata_path):
        print(f"❌ Metadata file not found: {metadata_path}")
        return

    with open(metadata_path, 'r', encoding='utf-8') as f:
        metadata = json.load(f)

    print(f"\n🚀 Ready to upload:")
    print(f"   - Video: {video_file}")
    print(f"   - Title: {metadata.get('title')}")
    print(f"   - Lang: {lang}")

    if input("\nConfirm upload? (y/n): ").lower() == 'y':
        poster.upload_video(video_path, metadata)
        
        # Ask to cleanup after successful upload only
        if input("\nCleanup processed files? (y/n): ").lower() == 'y':
            try:
                os.remove(video_path)
                os.remove(metadata_path)
                print("   - Deleted processed files.")
            except Exception as e:
                print(f"   - Cleanup error: {e}")
    else:
        print("❌ Upload cancelled.")

if __name__ == "__main__":
    main()



