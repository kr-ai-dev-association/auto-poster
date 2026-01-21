# 🚀 Auto Poster 서버 배포 가이드

완전한 서버 설치 및 배포 가이드입니다. 개발 환경부터 프로덕션 배포까지 단계별로 안내합니다.

## 📋 목차
1. [시스템 요구사항](#시스템-요구사항)
2. [개발 환경 설정](#개발-환경-설정)
3. [프로덕션 배포](#프로덕션-배포)
4. [보안 설정](#보안-설정)
5. [서버 관리](#서버-관리)
6. [문제 해결](#문제-해결)

---

## 시스템 요구사항

### 최소 사양
- **OS**: Ubuntu 20.04 LTS 이상 / macOS 10.15 이상
- **CPU**: 2 Core 이상
- **RAM**: 4GB 이상
- **Storage**: 20GB 이상 (여유 공간)
- **Python**: 3.9 이상 (권장: 3.12)

### 권장 사양 (프로덕션)
- **CPU**: 4 Core 이상
- **RAM**: 8GB 이상
- **Storage**: 50GB 이상 SSD

### 필수 소프트웨어
- Python 3.9+
- pip
- Git
- FFmpeg (영상 처리용)
- SQLite3
- Poppler (PDF 이미지 변환용)

### 권장 소프트웨어 (GPU 가속)
- NVIDIA GPU + CUDA (NVENC 인코딩 가속)

---

## 개발 환경 설정

### 1. 저장소 클론

```bash
# 1. Git 저장소 클론
git clone https://github.com/kr-ai-dev-association/auto-poster.git
cd auto-poster

# 2. 브랜치 확인
git branch -a
git checkout main
```

### 2. Python 가상환경 설정

```bash
# 1. Python 버전 확인
python3 --version  # 3.9 이상이어야 함

# 2. 가상환경 생성
python3 -m venv venv

# 3. 가상환경 활성화
# macOS/Linux:
source venv/bin/activate

# Windows:
venv\Scripts\activate

# 4. pip 업그레이드
pip install --upgrade pip
```

### 3. 의존성 설치

```bash
# 1. 필수 패키지 설치
pip install fastapi uvicorn[standard]
pip install sqlalchemy python-jose[cryptography] passlib[bcrypt]
pip install python-dotenv google-generativeai
pip install google-cloud-storage google-cloud-firestore
pip install google-auth google-auth-oauthlib google-auth-httplib2
pip install google-api-python-client
pip install Pillow beautifulsoup4 python-multipart
pip install cryptography

# 2. Gen Video 기능용 추가 패키지
pip install pdf2image moviepy
pip install git+https://github.com/openai/whisper.git  # Smart 모드용
pip install paddlepaddle paddleocr  # OCR 기능용

# 3. 설치 확인
pip list | grep -E "fastapi|sqlalchemy|google|whisper|paddle"
```

### 4. FFmpeg 및 Poppler 설치

**macOS (Homebrew):**
```bash
brew install ffmpeg poppler
ffmpeg -version
```

**Ubuntu/Debian:**
```bash
sudo apt update
sudo apt install ffmpeg poppler-utils
ffmpeg -version
pdftoppm -v
```

**CentOS/RHEL:**
```bash
sudo yum install epel-release
sudo yum install ffmpeg poppler-utils
ffmpeg -version
```

### 4-1. GPU 가속 설정 (선택사항)

NVENC GPU 인코딩을 사용하려면 NVIDIA 드라이버와 CUDA가 필요합니다:

```bash
# NVIDIA 드라이버 설치 확인
nvidia-smi

# FFmpeg NVENC 지원 확인
ffmpeg -encoders | grep nvenc
```

### 5. 환경 변수 설정

```bash
# 1. .env 파일 생성
cat > .env << 'EOF'
# 환경 설정
ENVIRONMENT=development

# 관리자 계정
SUPER_ADMIN_ID=admin@yourdomain.com
SUPER_ADMIN_PW=ChangeMe!SecurePassword123

# JWT 시크릿 (무작위 생성)
SECRET_KEY=your-secret-key-here-change-this

# Google Gemini AI
GEMINI_API_KEY=your-gemini-api-key

# YouTube API
YOUTUBE_API_KEY=your-youtube-api-key

# LinkedIn (선택사항)
LINKEDIN_ACCESS_TOKEN=your-linkedin-token
LINKEDIN_PERSON_URN=your-person-urn
EOF

# 2. SECRET_KEY 생성
python3 -c "import secrets; print('SECRET_KEY=' + secrets.token_hex(32))"
# 출력된 값을 .env의 SECRET_KEY에 복사

# 3. 파일 권한 설정 (중요!)
chmod 600 .env
```

### 6. 보안 파일 준비

```bash
# 1. 디렉토리 생성
mkdir -p secrets
mkdir -p youtube_poster

# 2. Firebase 서비스 계정 키 배치
# Google Cloud Console에서 다운로드한 JSON 파일을:
cp /path/to/your/serviceAccountKey.json 1_md_converter/

# 3. YouTube OAuth 클라이언트 시크릿 배치
# Google Cloud Console에서 다운로드한 JSON 파일을:
cp /path/to/your/serviceAccountKey.json secrets/
cp /path/to/your/client_secrets.json secrets/

# 4. 파일 권한 설정
chmod 600 secrets/serviceAccountKey.json
chmod 600 secrets/client_secrets.json
```

### 7. 데이터베이스 초기화

```bash
cd web_app

# DB 테이블 생성
python3 -c "
from core import database, models
models.Base.metadata.create_all(bind=database.engine)
print('✅ Database initialized')
"

# DB 파일 확인
ls -lh autoposter.db
```

### 8. 개발 서버 실행

```bash
# web_app 디렉토리에서
cd /path/to/auto-poster/web_app

# 서버 시작 (개발 모드, 자동 리로드)
../venv/bin/python -m uvicorn main:app --host 0.0.0.0 --port 8000 --reload

# 또는 간단하게
uvicorn main:app --reload
```

**접속 확인:**
- 웹 UI: http://localhost:8000
- API 문서: http://localhost:8000/docs
- 관리자: http://localhost:8000/admin/secure-files

---

## 프로덕션 배포

### 1. 서버 준비 (Ubuntu 예시)

```bash
# 1. 시스템 업데이트
sudo apt update && sudo apt upgrade -y

# 2. 필수 패키지 설치
sudo apt install -y python3 python3-pip python3-venv git nginx supervisor
sudo apt install -y ffmpeg sqlite3

# 3. 방화벽 설정
sudo ufw allow 22    # SSH
sudo ufw allow 80    # HTTP
sudo ufw allow 443   # HTTPS
sudo ufw enable
```

### 2. 애플리케이션 배포

```bash
# 1. 배포 사용자 생성
sudo useradd -m -s /bin/bash autoposter
sudo su - autoposter

# 2. 저장소 클론
cd /home/autoposter
git clone https://github.com/kr-ai-dev-association/auto-poster.git
cd auto-poster

# 3. 가상환경 및 의존성 설치
python3 -m venv venv
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt  # requirements.txt 생성 필요
```

### 3. requirements.txt 생성

```bash
# 개발 환경에서 생성
cd /path/to/auto-poster
source venv/bin/activate
pip freeze > requirements.txt

# 또는 수동으로 생성
cat > requirements.txt << 'EOF'
fastapi==0.109.0
uvicorn[standard]==0.27.0
sqlalchemy==2.0.25
python-jose[cryptography]==3.3.0
passlib[bcrypt]==1.7.4
python-multipart==0.0.6
python-dotenv==1.0.0
google-generativeai==0.3.2
google-cloud-storage==2.14.0
google-cloud-firestore==2.14.0
google-auth==2.27.0
google-auth-oauthlib==1.2.0
google-auth-httplib2==0.2.0
google-api-python-client==2.116.0
Pillow==10.2.0
beautifulsoup4==4.12.3
cryptography==42.0.0
EOF
```

### 4. 프로덕션 환경 변수 설정

```bash
# /home/autoposter/auto-poster/.env
cat > .env << 'EOF'
# 프로덕션 환경
ENVIRONMENT=production

# 관리자 계정 (강력한 비밀번호 사용!)
SUPER_ADMIN_ID=admin@yourdomain.com
SUPER_ADMIN_PW=VeryStrong!Password123!@#

# JWT 시크릿 (반드시 변경)
SECRET_KEY=생성된-64자-랜덤-문자열

# API Keys
GEMINI_API_KEY=your-production-key
YOUTUBE_API_KEY=your-production-key

# LinkedIn
LINKEDIN_ACCESS_TOKEN=your-token
LINKEDIN_PERSON_URN=your-urn
EOF

chmod 600 .env
```

### 5. 보안 파일 DB 업로드

**중요: 프로덕션에서는 로컬 파일 대신 DB 암호화 사용**

```bash
# 1. 개발 서버 임시 실행 (보안 파일 업로드용)
cd /home/autoposter/auto-poster/web_app
../venv/bin/python -m uvicorn main:app --host 127.0.0.1 --port 8000 &

# 2. 웹 브라우저로 접속
# http://your-server-ip:8000/login
# 슈퍼 관리자로 로그인 후:
# http://your-server-ip:8000/admin/secure-files

# 3. 다음 파일들을 업로드:
# - serviceAccountKey.json (타입: firebase)
# - client_secrets.json (타입: youtube)
# - .env (타입: env, 선택사항)

# 4. 업로드 후 임시 서버 종료
pkill -f uvicorn

# 5. 로컬 보안 파일 제거 (선택사항)
rm -f secrets/serviceAccountKey.json
rm -f secrets/client_secrets.json
```

### 6. Supervisor 설정 (프로세스 관리)

```bash
# Supervisor 설정 파일 생성
sudo tee /etc/supervisor/conf.d/autoposter.conf << 'EOF'
[program:autoposter]
directory=/home/autoposter/auto-poster/web_app
command=/home/autoposter/auto-poster/venv/bin/uvicorn main:app --host 127.0.0.1 --port 8000 --workers 4
user=autoposter
autostart=true
autorestart=true
stopasgroup=true
killasgroup=true
stdout_logfile=/var/log/autoposter/access.log
stderr_logfile=/var/log/autoposter/error.log
environment=PATH="/home/autoposter/auto-poster/venv/bin"
EOF

# 로그 디렉토리 생성
sudo mkdir -p /var/log/autoposter
sudo chown autoposter:autoposter /var/log/autoposter

# Supervisor 재시작
sudo supervisorctl reread
sudo supervisorctl update
sudo supervisorctl start autoposter

# 상태 확인
sudo supervisorctl status autoposter
```

### 7. Nginx 리버스 프록시 설정

```bash
# Nginx 설정 파일 생성
sudo tee /etc/nginx/sites-available/autoposter << 'EOF'
server {
    listen 80;
    server_name your-domain.com;  # 실제 도메인으로 변경

    client_max_body_size 100M;  # 파일 업로드 크기 제한

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        
        # WebSocket 지원 (필요시)
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
    }

    # 정적 파일 캐싱
    location /static/ {
        alias /home/autoposter/auto-poster/web_app/static/;
        expires 1y;
        add_header Cache-Control "public, immutable";
    }
}
EOF

# 심볼릭 링크 생성
sudo ln -s /etc/nginx/sites-available/autoposter /etc/nginx/sites-enabled/

# Nginx 설정 테스트
sudo nginx -t

# Nginx 재시작
sudo systemctl restart nginx
```

### 8. SSL 인증서 설정 (Let's Encrypt)

```bash
# Certbot 설치
sudo apt install certbot python3-certbot-nginx -y

# SSL 인증서 발급 및 자동 설정
sudo certbot --nginx -d your-domain.com

# 자동 갱신 테스트
sudo certbot renew --dry-run

# 자동 갱신은 cron으로 자동 설정됨
```

---

## 보안 설정

### 1. 파일 권한 설정

```bash
# 소유권 설정
sudo chown -R autoposter:autoposter /home/autoposter/auto-poster

# 디렉토리 권한
find /home/autoposter/auto-poster -type d -exec chmod 755 {} \;

# 파일 권한
find /home/autoposter/auto-poster -type f -exec chmod 644 {} \;

# 실행 파일 권한
chmod 755 /home/autoposter/auto-poster/venv/bin/*

# 민감한 파일 권한 강화
chmod 600 /home/autoposter/auto-poster/.env
chmod 600 /home/autoposter/auto-poster/web_app/autoposter.db
```

### 2. SELinux 설정 (CentOS/RHEL)

```bash
# SELinux 상태 확인
getenforce

# 포트 허용
sudo semanage port -a -t http_port_t -p tcp 8000

# 컨텍스트 설정
sudo chcon -R -t httpd_sys_content_t /home/autoposter/auto-poster
```

### 3. 보안 체크리스트

- [ ] `.env` 파일이 `.gitignore`에 포함되어 있는지 확인
- [ ] 강력한 `SUPER_ADMIN_PW` 사용 (20자 이상, 특수문자 포함)
- [ ] `SECRET_KEY`를 무작위 생성하여 사용
- [ ] 모든 보안 파일을 DB에 암호화하여 저장
- [ ] `ENVIRONMENT=production` 설정
- [ ] 로컬 보안 키 파일 제거
- [ ] 방화벽 규칙 적용
- [ ] SSL 인증서 설치
- [ ] 정기 백업 설정

---

## 서버 관리

### 서비스 제어

```bash
# Supervisor를 통한 제어
sudo supervisorctl stop autoposter    # 정지
sudo supervisorctl start autoposter   # 시작
sudo supervisorctl restart autoposter # 재시작
sudo supervisorctl status autoposter  # 상태 확인

# 로그 확인
sudo tail -f /var/log/autoposter/access.log
sudo tail -f /var/log/autoposter/error.log
```

### 업데이트 배포

```bash
# 1. 애플리케이션 사용자로 전환
sudo su - autoposter

# 2. 저장소 업데이트
cd /home/autoposter/auto-poster
git pull origin main

# 3. 의존성 업데이트 (필요시)
source venv/bin/activate
pip install --upgrade -r requirements.txt

# 4. 데이터베이스 마이그레이션 (필요시)
cd web_app
python3 -c "
from core import database, models
models.Base.metadata.create_all(bind=database.engine)
"

# 5. 서비스 재시작
exit  # autoposter 사용자 종료
sudo supervisorctl restart autoposter
```

### 백업

```bash
# 자동 백업 스크립트 생성
sudo tee /home/autoposter/backup.sh << 'EOF'
#!/bin/bash
DATE=$(date +%Y%m%d_%H%M%S)
BACKUP_DIR="/home/autoposter/backups"
APP_DIR="/home/autoposter/auto-poster"

mkdir -p $BACKUP_DIR

# DB 백업
cp $APP_DIR/web_app/autoposter.db $BACKUP_DIR/autoposter_$DATE.db

# .env 백업
cp $APP_DIR/.env $BACKUP_DIR/env_$DATE

# 7일 이상 된 백업 삭제
find $BACKUP_DIR -name "*.db" -mtime +7 -delete
find $BACKUP_DIR -name "env_*" -mtime +7 -delete

echo "✅ Backup completed: $DATE"
EOF

chmod +x /home/autoposter/backup.sh

# Cron 작업 추가 (매일 새벽 2시)
(crontab -l 2>/dev/null; echo "0 2 * * * /home/autoposter/backup.sh") | crontab -
```

### 모니터링

```bash
# 시스템 리소스 확인
htop

# 프로세스 확인
ps aux | grep uvicorn

# 포트 확인
sudo netstat -tulpn | grep :8000

# 디스크 사용량
df -h
du -sh /home/autoposter/auto-poster

# 로그 실시간 모니터링
tail -f /var/log/autoposter/error.log
tail -f /var/log/nginx/error.log
```

---

## 문제 해결

### 서버가 시작되지 않음

**1. 로그 확인**
```bash
sudo tail -100 /var/log/autoposter/error.log
sudo supervisorctl tail -f autoposter stderr
```

**2. 수동 실행으로 에러 확인**
```bash
sudo su - autoposter
cd /home/autoposter/auto-poster/web_app
../venv/bin/python -m uvicorn main:app --host 127.0.0.1 --port 8000
```

**3. 일반적인 원인**
- `.env` 파일 누락 → 파일 생성 확인
- 포트 충돌 → `lsof -i :8000`로 확인
- DB 파일 권한 → `chmod 644 autoposter.db`
- Python 버전 → `python3 --version` (3.9 이상 필요)

### 프로덕션에서 보안 파일 로드 실패

**증상:**
```bash
❌ [PRODUCTION] DB에 'serviceAccountKey.json' 파일이 없습니다.
```

**해결:**
1. `/admin/secure-files`에서 파일 업로드 확인
2. 키 프레이즈가 `.env`의 `SUPER_ADMIN_ID:SUPER_ADMIN_PW`와 일치하는지 확인
3. DB 파일 권한 확인: `ls -la web_app/autoposter.db`

### Nginx 502 Bad Gateway

**원인:** 백엔드 서버가 실행되지 않음

**해결:**
```bash
# 1. 백엔드 상태 확인
sudo supervisorctl status autoposter

# 2. 재시작
sudo supervisorctl restart autoposter

# 3. 수동 테스트
curl http://127.0.0.1:8000
```

### 파일 업로드 실패

**원인:** 파일 크기 제한 초과

**해결:**
```bash
# Nginx 설정 수정
sudo nano /etc/nginx/sites-available/autoposter
# client_max_body_size 100M; 추가

# Nginx 재시작
sudo systemctl restart nginx
```

### 메모리 부족

**증상:** 서버가 자주 재시작됨

**해결:**
```bash
# 1. Worker 수 줄이기
sudo nano /etc/supervisor/conf.d/autoposter.conf
# --workers 4 → --workers 2

# 2. Swap 메모리 추가
sudo fallocate -l 2G /swapfile
sudo chmod 600 /swapfile
sudo mkswap /swapfile
sudo swapon /swapfile

# 영구 적용
echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab
```

---

## 고급 설정

### Docker 배포 (선택사항)

```dockerfile
# Dockerfile
FROM python:3.12-slim

WORKDIR /app

# FFmpeg 설치
RUN apt-get update && apt-get install -y ffmpeg && rm -rf /var/lib/apt/lists/*

# 의존성 설치
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 애플리케이션 복사
COPY . .

# 포트 노출
EXPOSE 8000

# 실행
CMD ["uvicorn", "web_app.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

```yaml
# docker-compose.yml
version: '3.8'

services:
  autoposter:
    build: .
    ports:
      - "8000:8000"
    volumes:
      - ./web_app/autoposter.db:/app/web_app/autoposter.db
      - ./.env:/app/.env
    environment:
      - ENVIRONMENT=production
    restart: always
```

### 성능 최적화

```bash
# Uvicorn Workers 조정
# CPU 코어 수에 따라 조정 (일반적으로 CPU 코어 수 * 2)
--workers 4

# 로그 레벨 조정 (프로덕션)
--log-level warning

# 타임아웃 설정
--timeout-keep-alive 5
```

---

## 체크리스트

### 배포 전 체크리스트

- [ ] 모든 의존성 설치 확인
- [ ] `.env` 파일 설정 (ENVIRONMENT=production)
- [ ] 보안 파일 DB 업로드 완료
- [ ] 강력한 비밀번호 설정
- [ ] SSL 인증서 발급
- [ ] 방화벽 규칙 적용
- [ ] Nginx 설정 완료
- [ ] Supervisor 설정 완료
- [ ] 백업 스크립트 설정
- [ ] 모니터링 설정

### 배포 후 체크리스트

- [ ] 웹 UI 접속 테스트
- [ ] 슈퍼 관리자 로그인 테스트
- [ ] Wiki 변환/배포 테스트
- [ ] YouTube 업로드 테스트 (썸네일 자동 생성 포함)
- [ ] Gen Video Basic 모드 테스트
- [ ] Gen Video Smart 모드 테스트 (Whisper + PaddleOCR)
- [ ] 보안 파일 관리 페이지 접속 테스트
- [ ] 로그 확인
- [ ] 성능 모니터링 설정
- [ ] 정기 백업 확인

---

## 참고 자료

- [FastAPI 공식 문서](https://fastapi.tiangolo.com/)
- [Uvicorn 배포 가이드](https://www.uvicorn.org/deployment/)
- [Nginx 설정 가이드](https://nginx.org/en/docs/)
- [Let's Encrypt](https://letsencrypt.org/)
- [보안 파일 관리 시스템](./SECURITY_MANAGEMENT.md)

---

**문의 및 지원**: Issues를 통해 문의해주세요.

© 2026 Banya AI - Auto Poster

