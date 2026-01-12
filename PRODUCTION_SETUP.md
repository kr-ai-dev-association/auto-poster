# 프로덕션 모드 설정 가이드

## 시스템 요구사항

### 필수 패키지 설치

YouTube 비디오 업로드 기능을 사용하려면 FFmpeg가 필요합니다:

```bash
sudo apt update
sudo apt install -y ffmpeg
```

설치 확인:
```bash
which ffmpeg ffprobe
ffmpeg -version
```

## 현재 상태
- ✅ `ENVIRONMENT=production`으로 설정 완료
- ⚠️ DB에 업로드된 보안 파일들이 복호화되지 않음

## 문제 원인
DB에 업로드된 파일들이 업로드 시 사용한 키 프레이즈와 현재 `.env`의 `SUPER_ADMIN_ID:SUPER_ADMIN_PW`가 일치하지 않아 복호화가 실패합니다.

## 해결 방법

### 1. 올바른 키 프레이즈 확인
키 프레이즈는 다음 형식이어야 합니다:
```
SUPER_ADMIN_ID:SUPER_ADMIN_PW
```

예시:
```
tony@banya.ai:YourPassword123!
```

### 2. 보안 파일 재업로드
웹 인터페이스에서 다음 단계를 수행하세요:

1. **로그인**: http://서버IP:8000/login
   - 슈퍼 관리자 계정으로 로그인

2. **보안 파일 관리 페이지 접속**: http://서버IP:8000/admin/secure-files

3. **기존 파일 삭제** (있는 경우):
   - 각 파일 옆의 "삭제" 버튼 클릭
   - 삭제할 파일:
     - `.env`
     - `serviceAccountKey.json`
     - `client_secrets.json`

4. **파일 재업로드**:
   - 각 파일을 하나씩 업로드
   - **키 프레이즈**: `SUPER_ADMIN_ID:SUPER_ADMIN_PW` 형식으로 입력
     - 예: `tony@banya.ai:YourPassword123!`
   - **중요**: 모든 파일 업로드 시 **동일한 키 프레이즈**를 사용해야 합니다!

### 3. 업로드할 파일들

#### `.env` 파일
```
ENVIRONMENT=production
SUPER_ADMIN_ID=your-email@domain.com
SUPER_ADMIN_PW=YourSecurePassword123!
SECRET_KEY=your-secret-key-here
GEMINI_API_KEY=your-gemini-api-key
YOUTUBE_API_KEY=your-youtube-api-key
LINKEDIN_ACCESS_TOKEN=your-linkedin-token
LINKEDIN_PERSON_URN=your-person-urn
```

#### `serviceAccountKey.json`
- Firebase 서비스 계정 키 파일

#### `client_secrets.json`
- YouTube OAuth 클라이언트 시크릿 파일

### 4. 서버 재시작
파일 업로드 후 서버를 재시작하여 환경 변수를 로드합니다:

```bash
pkill -f uvicorn
cd /home/ubuntu/auto-poster/web_app
../venv/bin/python -m uvicorn main:app --host 0.0.0.0 --port 8000
```

### 5. 확인
서버 로그에서 다음 메시지가 보이면 성공:
```
✅ [PRODUCTION] Environment variables loaded from encrypted DB
✅ [PRODUCTION] Firebase credentials loaded from encrypted DB
✅ [PRODUCTION] YouTube client_secrets loaded from encrypted DB
```

## 주의사항

⚠️ **중요**: 
- 키 프레이즈를 분실하면 파일을 복구할 수 없습니다
- 모든 파일 업로드 시 **반드시 동일한 키 프레이즈**를 사용하세요
- 키 프레이즈는 `SUPER_ADMIN_ID:SUPER_ADMIN_PW` 형식이어야 합니다

## 문제 해결

### 복호화 실패 시
1. DB에서 파일 삭제
2. 올바른 키 프레이즈로 다시 업로드
3. 서버 재시작

### 환경 변수가 로드되지 않을 때
1. `/admin/secure-files`에서 `.env` 파일이 있는지 확인
2. 키 프레이즈가 올바른지 확인
3. 서버 로그 확인: `tail -f /tmp/server.log`
