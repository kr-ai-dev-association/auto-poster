#!/usr/bin/env python3
"""
YouTube OAuth Token Generator
=============================
이 스크립트를 로컬 PC에서 실행하여 token.pickle을 생성합니다.

사용법:
1. Google Cloud Console에서 OAuth 2.0 Client ID를 생성하고
   client_secrets.json을 다운로드합니다.
2. 이 스크립트와 client_secrets.json을 같은 폴더에 놓습니다.
3. 필요한 패키지를 설치합니다:
   pip install google-auth-oauthlib google-api-python-client
4. 스크립트를 실행합니다:
   python generate_token.py
5. 브라우저에서 Google 계정으로 로그인하고 권한을 승인합니다.
6. 생성된 token.pickle 파일을 서버에 업로드합니다:
   scp token.pickle ubuntu@210.109.80.198:/home/ubuntu/auto-poster/youtube_poster/
"""

import os
import pickle
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request

SCOPES = ['https://www.googleapis.com/auth/youtube.upload']
CLIENT_SECRETS_FILE = 'client_secrets.json'
TOKEN_FILE = 'token.pickle'


def generate_token():
    """OAuth 인증을 수행하고 token.pickle을 생성합니다."""
    creds = None

    # 기존 토큰이 있으면 로드
    if os.path.exists(TOKEN_FILE):
        print(f"📂 기존 토큰 파일 발견: {TOKEN_FILE}")
        with open(TOKEN_FILE, 'rb') as token:
            creds = pickle.load(token)

        if creds and creds.valid:
            print("✅ 기존 토큰이 유효합니다!")
            return
        elif creds and creds.expired and creds.refresh_token:
            print("🔄 토큰이 만료됨, 갱신 시도...")
            try:
                creds.refresh(Request())
                with open(TOKEN_FILE, 'wb') as token:
                    pickle.dump(creds, token)
                print("✅ 토큰 갱신 완료!")
                return
            except Exception as e:
                print(f"❌ 토큰 갱신 실패: {e}")
                print("🔄 새로운 인증을 진행합니다...")

    # client_secrets.json 확인
    if not os.path.exists(CLIENT_SECRETS_FILE):
        print(f"❌ {CLIENT_SECRETS_FILE} 파일을 찾을 수 없습니다!")
        print()
        print("📋 client_secrets.json 생성 방법:")
        print("1. https://console.cloud.google.com/apis/credentials 접속")
        print("2. '사용자 인증 정보 만들기' → 'OAuth 클라이언트 ID'")
        print("3. 애플리케이션 유형: '데스크톱 앱' 선택")
        print("4. JSON 다운로드 후 이름을 'client_secrets.json'으로 변경")
        print(f"5. 이 스크립트와 같은 폴더({os.getcwd()})에 저장")
        return

    # OAuth 플로우 실행
    print("🌐 브라우저에서 Google 계정으로 로그인하세요...")
    flow = InstalledAppFlow.from_client_secrets_file(CLIENT_SECRETS_FILE, SCOPES)
    creds = flow.run_local_server(port=8080)

    # 토큰 저장
    with open(TOKEN_FILE, 'wb') as token:
        pickle.dump(creds, token)

    print()
    print("=" * 60)
    print("✅ token.pickle 생성 완료!")
    print("=" * 60)
    print()
    print("📤 서버에 업로드하려면 다음 명령을 실행하세요:")
    print()
    print(f"   scp {TOKEN_FILE} ubuntu@210.109.80.198:/home/ubuntu/auto-poster/youtube_poster/")
    print()
    print("또는 웹 인터페이스의 /admin/secure-files에서 업로드할 수 있습니다.")


if __name__ == '__main__':
    generate_token()
