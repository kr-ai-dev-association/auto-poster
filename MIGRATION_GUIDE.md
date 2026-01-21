# Auto-Poster 서버 이관 가이드

이 문서는 Auto-Poster 프로젝트를 새로운 서버로 이관할 때 필요한 백업 항목과 절차를 설명합니다.

---

## 1. 필수 백업 항목

### 1.1 SQLite 데이터베이스
암호화된 보안 파일(.env, serviceAccountKey.json 등)과 모든 애플리케이션 데이터가 저장되어 있습니다.

```bash
# 백업
cp /home/ubuntu/auto-poster/auto_poster.db ./backup/

# 복원
cp ./backup/auto_poster.db /home/ubuntu/auto-poster/
```

### 1.2 생성된 영상 폴더
Gen Video 기능으로 생성된 모든 MP4 파일이 저장되어 있습니다.

```bash
# 백업
tar -czvf generated_videos_backup.tar.gz /home/ubuntu/auto-poster/generated_videos/

# 복원
tar -xzvf generated_videos_backup.tar.gz -C /home/ubuntu/auto-poster/
```

### 1.3 시스템 환경 변수 (중요!)
프로덕션 모드에서 DB의 암호화된 파일을 복호화하는 데 필요한 마스터 키입니다.

**반드시 기록해 둘 환경 변수:**
| 변수명 | 설명 |
|--------|------|
| `SUPER_ADMIN_ID` | 슈퍼 관리자 ID (암호화 키의 일부) |
| `SUPER_ADMIN_PW` | 슈퍼 관리자 비밀번호 (암호화 키의 일부) |
| `ENVIRONMENT` | 실행 환경 (`production` 또는 `development`) |

```bash
# 현재 값 확인
echo $SUPER_ADMIN_ID
echo $SUPER_ADMIN_PW
echo $ENVIRONMENT
```

> **주의:** 이 값들이 없으면 DB에 저장된 암호화된 .env 파일을 복호화할 수 없습니다!

---

## 2. 선택적 백업 항목

### 2.1 로컬 .env 파일 (개발 환경만)
개발 환경에서 사용하는 경우에만 해당됩니다. 프로덕션에서는 DB에 암호화되어 저장됩니다.

```bash
# 백업 (개발 환경인 경우)
cp /home/ubuntu/auto-poster/.env ./backup/
```

---

## 3. 새 서버 이관 절차

### 3.1 시스템 패키지 설치
```bash
# Ubuntu/Debian
sudo apt-get update
sudo apt-get install -y poppler-utils ffmpeg python3 python3-pip python3-venv
```

### 3.2 프로젝트 클론
```bash
cd /home/ubuntu
git clone https://github.com/your-repo/auto-poster.git
cd auto-poster
```

### 3.3 Python 환경 설정
```bash
# 가상환경 생성 (선택사항이지만 권장)
python3 -m venv venv
source venv/bin/activate

# 의존성 설치
pip install -r requirements.txt

# Whisper 설치 (Smart 모드용)
pip install git+https://github.com/openai/whisper.git
```

### 3.4 백업 파일 복원
```bash
# 데이터베이스 복원
cp ./backup/auto_poster.db /home/ubuntu/auto-poster/

# 생성된 영상 폴더 복원
tar -xzvf generated_videos_backup.tar.gz -C /home/ubuntu/auto-poster/

# 디렉토리가 없으면 생성
mkdir -p /home/ubuntu/auto-poster/generated_videos
```

### 3.5 시스템 환경 변수 설정
```bash
# /etc/environment 또는 ~/.bashrc에 추가
export SUPER_ADMIN_ID="your_admin_id"
export SUPER_ADMIN_PW="your_admin_password"
export ENVIRONMENT="production"

# 적용
source ~/.bashrc
```

또는 systemd 서비스 파일에 환경 변수 추가:
```ini
[Service]
Environment="SUPER_ADMIN_ID=your_admin_id"
Environment="SUPER_ADMIN_PW=your_admin_password"
Environment="ENVIRONMENT=production"
```

### 3.6 애플리케이션 실행
```bash
cd /home/ubuntu/auto-poster/web_app
uvicorn main:app --host 0.0.0.0 --port 8000
```

---

## 4. 검증 체크리스트

이관 완료 후 다음 항목을 확인하세요:

- [ ] 웹 애플리케이션 접속 가능 여부
- [ ] 로그인 기능 정상 작동
- [ ] Wiki Poster 기능 테스트
- [ ] YouTube Poster 기능 테스트
- [ ] Gen Video Basic 모드 변환 테스트
- [ ] Gen Video Smart 모드 변환 테스트
- [ ] 보안 파일 관리 페이지 접근 가능 여부
- [ ] 기존 생성된 영상 목록 조회

---

## 5. 문제 해결

### 암호화된 파일 복호화 실패
```
❌ [PRODUCTION] .env 파일이 DB에 없습니다.
```
→ `SUPER_ADMIN_ID`와 `SUPER_ADMIN_PW` 환경 변수가 이전 서버와 동일한지 확인

### Gen Video 변환 실패
```
pdf2image 또는 moviepy 관련 오류
```
→ 시스템 패키지 설치 확인: `sudo apt-get install poppler-utils ffmpeg`

### Whisper 관련 오류 (Smart 모드)
```
Whisper not installed
```
→ Whisper 재설치: `pip install git+https://github.com/openai/whisper.git`

---

## 6. 보안 주의사항

1. **SUPER_ADMIN_ID/PW는 절대 공개 저장소에 커밋하지 마세요**
2. 백업 파일은 안전한 위치에 암호화하여 보관하세요
3. 이관 완료 후 이전 서버의 데이터를 안전하게 삭제하세요
4. 새 서버에서 방화벽 설정을 확인하세요

---

*마지막 업데이트: 2026-01-21*
