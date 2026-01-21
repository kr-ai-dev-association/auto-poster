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

### 1.3 .env 파일
로컬에 보관 중인 `.env` 파일을 백업해 두세요. 이 파일에는 API 키와 슈퍼 관리자 계정 정보가 포함되어 있습니다.

> **참고:** 슈퍼 관리자 계정(`SUPER_ADMIN_ID`, `SUPER_ADMIN_PW`)은 DB의 암호화된 파일을 복호화하는 마스터 키로 사용됩니다.

---

## 2. 선택적 백업 항목

### 2.1 로컬 .env 파일 (개발 환경만)
개발 환경에서 사용하는 경우에만 해당됩니다. 프로덕션에서는 DB에 암호화되어 저장됩니다.

```bash
# 백업 (개발 환경인 경우)
cp /home/ubuntu/auto-poster/.env ./backup/
```

---

## 3. 백업 파일 생성 및 다운로드

### 3.1 서버에서 백업 파일 생성
```bash
# 서버에 SSH 접속 후 실행
cd /home/ubuntu/auto-poster

# 백업 디렉토리 생성 및 파일 복사
mkdir -p backup_$(date +%Y%m%d)
cp web_app/autoposter.db backup_$(date +%Y%m%d)/
cp -r generated_videos backup_$(date +%Y%m%d)/

# 압축 파일 생성
tar -czvf migration_backup_$(date +%Y%m%d).tar.gz backup_$(date +%Y%m%d)/
```

### 3.2 로컬 PC로 다운로드
```bash
# 로컬 PC 터미널에서 실행 (SSH 키 파일 경로와 서버 주소를 수정하세요)
scp -i <ssh_key_file> ubuntu@<server_ip>:/home/ubuntu/auto-poster/migration_backup_*.tar.gz /path/to/local/backup/

# 예시:
# scp -i rsa_id ubuntu@210.109.80.198:/home/ubuntu/auto-poster/migration_backup_20260121.tar.gz /Users/tony/Downloads/backup/
```

---

## 4. 새 서버 이관 절차

### 4.1 시스템 패키지 설치
```bash
# Ubuntu/Debian
sudo apt-get update
sudo apt-get install -y poppler-utils ffmpeg python3 python3-pip python3-venv
```

### 4.2 프로젝트 클론
```bash
cd /home/ubuntu
git clone https://github.com/kr-ai-dev-association/auto-poster.git
cd auto-poster
```

### 4.3 Python 환경 설정
```bash
# 가상환경 생성 (선택사항이지만 권장)
python3 -m venv venv
source venv/bin/activate

# 의존성 설치
pip install -r requirements.txt

# Whisper 설치 (Smart 모드용)
pip install git+https://github.com/openai/whisper.git
```

### 4.4 백업 파일 업로드 및 복원

#### 로컬 PC에서 새 서버로 백업 파일 업로드
```bash
# 로컬 PC 터미널에서 실행
scp -i <ssh_key_file> /path/to/local/backup/migration_backup_*.tar.gz ubuntu@<new_server_ip>:/home/ubuntu/

# 예시:
# scp -i rsa_id /Users/tony/Downloads/backup/migration_backup_20260121.tar.gz ubuntu@새서버IP:/home/ubuntu/
```

#### 새 서버에서 백업 파일 복원
```bash
# 새 서버에 SSH 접속 후 실행
cd /home/ubuntu

# 압축 해제
tar -xzvf migration_backup_*.tar.gz

# 데이터베이스 복원 (backup_YYYYMMDD 폴더명 확인 후 실행)
cp backup_20260121/autoposter.db /home/ubuntu/auto-poster/web_app/

# 생성된 영상 폴더 복원
cp -r backup_20260121/generated_videos /home/ubuntu/auto-poster/

# 디렉토리가 없으면 생성
mkdir -p /home/ubuntu/auto-poster/generated_videos
```

### 4.5 .env 파일 복원
로컬에 백업해 둔 `.env` 파일을 새 서버의 `web_app` 디렉토리에 복사합니다.

```bash
# 로컬 PC에서 새 서버로 .env 파일 업로드
scp -i <ssh_key_file> /path/to/local/.env ubuntu@<new_server_ip>:/home/ubuntu/auto-poster/web_app/
```

### 4.6 애플리케이션 실행
```bash
cd /home/ubuntu/auto-poster/web_app
uvicorn main:app --host 0.0.0.0 --port 8000
```

---

## 5. 검증 체크리스트

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

## 6. 문제 해결

### 암호화된 파일 복호화 실패
```
❌ [PRODUCTION] .env 파일이 DB에 없습니다.
```
→ `.env` 파일이 `web_app` 디렉토리에 있는지 확인하고, `SUPER_ADMIN_ID`와 `SUPER_ADMIN_PW` 값이 이전 서버와 동일한지 확인

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

## 7. 보안 주의사항

1. **`.env` 파일은 절대 공개 저장소에 커밋하지 마세요**
2. 백업 파일은 안전한 위치에 암호화하여 보관하세요
3. 이관 완료 후 이전 서버의 데이터를 안전하게 삭제하세요
4. 새 서버에서 방화벽 설정을 확인하세요

---

*마지막 업데이트: 2026-01-21*
