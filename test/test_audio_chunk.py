"""
TTS 오디오 청크 분할 생성 테스트 스크립트
test/audio_script.md 파일을 읽어서 청크 분할 → TTS 생성 → WAV 합성을 테스트합니다.
"""
import asyncio
import os
import sys
import time

# 프로젝트 루트를 path에 추가
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)
sys.path.insert(0, os.path.join(project_root, 'web_app'))

from dotenv import load_dotenv
load_dotenv(os.path.join(project_root, '.env'))

# DB에서 암호화된 환경변수 로드 (GEMINI_API_KEY 등)
from web_app.services.crypto_service import CryptoService
CryptoService.load_env_from_db()

from web_app.services.audio_generator_service import AudioGeneratorService


async def main():
    # 1. 스크립트 파일 읽기
    script_path = os.path.join(project_root, 'test', 'audio_script.md')
    with open(script_path, 'r', encoding='utf-8') as f:
        script = f.read().strip()

    print(f"📄 스크립트 로드: {len(script)}자")
    print(f"{'='*60}")

    # 2. 서비스 초기화
    service = AudioGeneratorService()

    # 3. 청크 분할 테스트 (dry run)
    chunks = service._split_script_into_chunks(script, language='ko')
    print(f"\n🔪 청크 분할 결과: {len(chunks)}개 청크")
    for i, chunk in enumerate(chunks):
        estimated_sec = len(chunk) / 5.8
        print(f"   [{i+1}] {len(chunk)}자 (예상 {estimated_sec:.1f}초) | {chunk[:50]}...")
    print(f"{'='*60}")

    # 4. 실제 TTS 생성 테스트
    print(f"\n🎵 TTS 생성 시작...")
    start_time = time.time()

    result = await service.generate_audio_from_script(
        script=script,
        output_filename='test_chunk_audio',
        voice='Leda',
        language='ko',
        metadata={'test': True, 'source': 'audio_script.md'}
    )

    elapsed = time.time() - start_time

    # 5. 결과 출력
    print(f"\n{'='*60}")
    print(f"📊 결과:")
    print(f"   상태: {result.get('status')}")
    if result.get('status') == 'success':
        print(f"   파일: {result.get('audio_path')}")
        print(f"   길이: {result.get('duration')}초")
        print(f"   크기: {result.get('file_size', 0) / 1024:.1f} KB")
        print(f"   음성: {result.get('voice')}")
        print(f"   소요: {elapsed:.1f}초")
    else:
        print(f"   에러: {result.get('message')}")


if __name__ == '__main__':
    asyncio.run(main())
