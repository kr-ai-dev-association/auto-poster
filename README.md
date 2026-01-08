# 🚀 AI Auto-Poster & Content Automation System

통합 웹 애플리케이션으로 Wiki 자동 변환/배포, YouTube 영상 편집/업로드, LinkedIn 소셜 홍보를 한 번에 처리하는 AI 기반 콘텐츠 자동화 시스템입니다.

## 🎯 주요 특징

- 🌐 **웹 UI**: FastAPI + Alpine.js 기반의 직관적인 인터페이스
- 🔒 **보안 시스템**: DB 암호화 기반 보안 파일 관리
- 🤖 **AI 통합**: Google Gemini를 활용한 자동 콘텐츠 생성
- 🔐 **인증/권한**: JWT 기반 회원 관리 및 슈퍼 관리자 승인 시스템
- 🌍 **다국어**: 한국어/영어 자동 변환 및 배포

## 📂 프로젝트 구조

```text
.
├── web_app/                      # 🌐 웹 애플리케이션 (FastAPI)
│   ├── main.py                   # FastAPI 메인 애플리케이션
│   ├── core/                     # 핵심 모듈
│   │   ├── database.py           # SQLAlchemy DB 설정
│   │   └── models.py             # DB 모델 (User, SecureFile)
│   ├── services/                 # 비즈니스 로직
│   │   ├── auth_service.py       # 인증/권한 관리
│   │   ├── crypto_service.py     # 암호화/복호화
│   │   ├── converter_service.py  # 마크다운 변환
│   │   ├── firebase_service.py   # Firebase/GCS 연동
│   │   ├── linkedin_service.py   # LinkedIn 포스팅
│   │   └── youtube_service.py    # YouTube 업로드
│   ├── templates/                # HTML 템플릿
│   │   ├── index.html            # 메인 UI
│   │   ├── login.html            # 로그인
│   │   ├── signup.html           # 회원가입
│   │   ├── admin_users.html      # 회원 관리
│   │   └── admin_secure_files.html # 보안 파일 관리
│   └── autoposter.db             # SQLite 데이터베이스
├── core/                         # 공용 코어 모듈
│   ├── auth_helper.py            # LinkedIn OAuth
│   ├── linkedin_poster.py        # LinkedIn API
│   └── summarizer.py             # Gemini AI
├── youtube_poster/               # YouTube 편집/업로드
│   ├── youtube_poster.py         # 메인 스크립트
│   ├── video_editor.py           # 비디오 편집 (로고, 자막)
│   └── v_source/                 # 영상 리소스
│       ├── tech/                 # 기술 카테고리
│       │   ├── *.mp4             # 원본 영상
│       │   ├── *.pdf             # 메타데이터 소스
│       │   ├── *.png             # 로고
│       │   └── desc_*.md         # 설명 템플릿
│       └── entertainment/        # 엔터테인먼트 카테고리
├── secrets/                      # 🔐 보안 파일 (로컬 개발용)
│   ├── serviceAccountKey.json    # Firebase 서비스 계정 키
│   └── client_secrets.json       # YouTube OAuth 클라이언트
├── legacy/                       # 📦 레거시 스크립트 (참고용)
│   ├── md_converter/             # 구 마크다운 변환기
│   ├── blog_poster/              # 구 블로그 포스팅
│   └── youtube_poster/           # 구 YouTube 업로드
├── DEPLOYMENT_GUIDE.md           # 🚀 서버 배포 가이드
├── SECURITY_MANAGEMENT.md        # 🔒 보안 파일 관리 가이드
├── README.md                     # 📖 프로젝트 문서
├── requirements.txt              # Python 의존성
├── .env                          # 환경 변수
└── .gitignore                    # Git 제외 파일
```

### 🔐 보안 파일 관리

**개발 환경:**
- `secrets/` 디렉토리에 키 파일 배치
- Git에서 자동 제외 (`.gitignore`)

**프로덕션 환경:**
- `/admin/secure-files`에서 DB 암호화 업로드
- `secrets/` 디렉토리 불필요

자세한 내용: [SECURITY_MANAGEMENT.md](./SECURITY_MANAGEMENT.md)

---

## 🚀 빠른 시작

### 1. 저장소 클론
```bash
git clone https://github.com/kr-ai-dev-association/auto-poster.git
cd auto-poster
```

### 2. 가상환경 설정
```bash
python3 -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install --upgrade pip
```

### 3. 의존성 설치
```bash
pip install fastapi uvicorn[standard]
pip install sqlalchemy python-jose[cryptography] passlib[bcrypt]
pip install python-dotenv google-generativeai
pip install google-cloud-storage google-cloud-firestore
pip install google-auth google-auth-oauthlib google-api-python-client
pip install Pillow beautifulsoup4 python-multipart cryptography
```

### 4. 환경 변수 설정
```bash
# .env 파일 생성
cat > .env << EOF
ENVIRONMENT=development
SUPER_ADMIN_ID=admin@yourdomain.com
SUPER_ADMIN_PW=YourSecurePassword123!
SECRET_KEY=$(python3 -c "import secrets; print(secrets.token_hex(32))")
GEMINI_API_KEY=your-gemini-api-key
EOF
```

### 5. 서버 실행
```bash
cd web_app
../venv/bin/python -m uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

**접속**: http://localhost:8000

---

## 🌟 주요 기능

### 🌐 웹 애플리케이션
FastAPI 기반의 통합 웹 인터페이스로 모든 기능을 제공합니다.

#### 📝 Wiki Auto Poster
- 마크다운 파일 업로드 또는 직접 작성
- AI 기반 16:9 요약 이미지 자동 생성
- 한국어/영어 동시 변환 및 배포
- Firebase/GCS 자동 배포
- HTML 미리보기 기능
- LinkedIn 자동 홍보 (한글/영문)

#### 🎬 Youtube Poster
- PDF 기반 메타데이터 자동 생성 (제목, 설명, 태그)
- AI 자막 생성 (선택사항)
- 로고 합성 및 비디오 편집
- 카테고리별 리소스 관리 (tech/entertainment)
- YouTube 자동 업로드
- LinkedIn 소셜 홍보 통합

#### 🔐 보안 파일 관리
- 슈퍼 관리자 전용 암호화 시스템
- `serviceAccountKey.json`, `client_secrets.json`, `.env` DB 암호화 저장
- Fernet 대칭키 암호화
- 개발/프로덕션 환경 자동 구분

#### 👥 회원 관리
- JWT 기반 인증
- 회원가입 및 로그인
- 슈퍼 관리자 승인 시스템
- 비밀번호 강도 검증 (8자 이상, 대소문자/숫자/특수문자)

---

## 📖 상세 가이드

### Wiki Auto Poster 사용법
1. 로그인 후 메인 화면에서 "Wiki Auto Poster" 선택
2. **파일 업로드** 또는 **직접 작성** 탭 선택
3. 마크다운 파일 업로드 또는 내용 입력
4. "변환 및 배포" 버튼 클릭
5. 완료 후 미리보기 및 LinkedIn 홍보 가능

### Youtube Poster 사용법
1. 메인 화면에서 "Youtube Poster" 선택
2. 카테고리 선택 (tech/entertainment)
3. 영상 파일 + PDF 메타데이터 소스 업로드
4. AI 메타데이터 미리보기 확인
5. 자막 생성 옵션 선택
6. "Final Edit & Upload" 버튼 클릭
7. 완료 후 LinkedIn 소셜 홍보 가능

### 보안 파일 관리
1. 슈퍼 관리자로 로그인
2. 좌측 메뉴 "보안 파일 관리" 클릭
3. 파일 선택 및 타입 지정
4. 키 프레이즈 입력 (형식: `SUPER_ADMIN_ID:SUPER_ADMIN_PW`)
5. 암호화하여 업로드

---

## 🔒 보안 설정

### 환경 구분
`.env` 파일에서 환경 설정:
```bash
# 개발 환경 (로컬 파일 폴백 허용)
ENVIRONMENT=development

# 프로덕션 (DB만 사용, 폴백 금지)
ENVIRONMENT=production
```

### 프로덕션 배포 전 체크리스트
- [ ] 모든 보안 파일을 `/admin/secure-files`에서 업로드
- [ ] `.env`에 `ENVIRONMENT=production` 설정
- [ ] 강력한 `SUPER_ADMIN_PW` 사용 (20자 이상)
- [ ] `SECRET_KEY` 무작위 생성
- [ ] 로컬 보안 키 파일 제거

자세한 내용은 **[SECURITY_MANAGEMENT.md](./SECURITY_MANAGEMENT.md)** 참조

---

## 🚀 프로덕션 배포

### 서버 배포 가이드
완전한 서버 설치 및 배포 가이드는 **[DEPLOYMENT_GUIDE.md](./DEPLOYMENT_GUIDE.md)** 참조

### 간단 요약
```bash
# 1. Ubuntu 서버 설정
sudo apt update && sudo apt upgrade -y
sudo apt install -y python3 python3-venv nginx supervisor ffmpeg

# 2. 애플리케이션 배포
git clone https://github.com/kr-ai-dev-association/auto-poster.git
cd auto-poster
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# 3. 보안 파일 DB 업로드
# /admin/secure-files에서 업로드

# 4. 프로덕션 환경 설정
echo "ENVIRONMENT=production" >> .env

# 5. Supervisor + Nginx 설정
# DEPLOYMENT_GUIDE.md 참조
```

---

## 🔧 레거시 스크립트 (선택사항)

### 1. 마크다운 위키 변환기 (레거시)
마크다운 파일을 고품질 HTML 위키 페이지로 변환하고 AI 요약 이미지를 자동 생성합니다.

- **실행 방법**:
  ```bash
  python 1_md_converter/md_to_html_converter.py
  ```
- **주요 기능**:
  - `1_md_converter/source/` 내 마크다운 파일을 분석하여 국문/영문 HTML 동시 생성.
  - **Gemini 2.0 Flash** 기반의 16:9 기술 일러스트 자동 생성 및 2회 재시도 로직.
  - **콘텐츠 복사 도구**: HTML 페이지 상단 및 각 섹션(h2, h3)별로 즉시 복사 가능한 아이콘 삽입.
  - 영문 슬러그 기반의 파일명 동기화 (`filename_ko.html`, `filename_en.html`).
  - 배포 경로(`/Volumes/Transcend/Projects/tech-blog/html`)로 자동 복사 및 로컬 정리.

### 2. 링크드인 자동 포스팅기 (`2_blog_poster`)
기술 블로그 포스트나 유튜브 영상을 분석하여 LinkedIn에 전문적인 기술 포스트를 작성합니다.

#### 2.1. 테크 블로그 포스팅
- **실행 방법**:
  ```bash
  python 2_blog_poster/linkedin_blog_poster.py
  ```
- **주요 기능**:
  - `blog.json`의 단일 URL을 기반으로 국문/영문 포스트 순차 생성.
  - 로컬/배포된 HTML 콘텐츠를 우선 분석하여 정확한 요약 수행.
  - 유니코드 볼드체 및 LinkedIn UTF-16 글자 수 제한(3,000자) 자동 관리.

#### 2.2. 테크 유튜브 포스팅
- **실행 방법**:
  ```bash
  python 2_blog_poster/linkedin_youtube_poster.py
  ```
- **주요 기능**:
  - `youtube.json`의 유튜브 URL을 기반으로 메타데이터(제목, 설명, 썸네일) 추출.
  - Gemini AI를 사용하여 영상 내용을 분석하고 LinkedIn용 요약문 생성.
  - 영상 썸네일을 자동으로 다운로드하여 LinkedIn 포스트에 첨부.

### 3. 유투브 동영상 자동 포스팅기 (`youtube_poster`)
유투브 영상 분석, 로고 및 자막 합성, 마케팅 최적화 설명 생성 및 자동 업로드를 수행합니다.

- **사전 준비**:
  1. Google Cloud Console에서 **YouTube Data API v3** 활성화 및 OAuth 클라이언트 ID(JSON) 다운로드.
  2. `secrets/client_secrets.json`으로 저장.
  3. `v_source/` 폴더 내 카테고리별(`tech`, `entertainment`)로 MP4, PDF, 로고 이미지, 다국어 고정 설명(`desc_ko.md`, `desc_en.md`) 준비.
- **실행 방법**:
  ```bash
  python youtube_poster/youtube_poster.py
  ```
- **주요 기능**:
  - **카테고리 선택**: 실행 시 `tech` 또는 `entertainment`를 선택하여 해당 경로의 리소스를 사용.
  - **선택적 자막 생성**: 실행 시 자막 생성 여부를 선택 가능 (기본값: 생성 안 함).
  - **지능형 자막 생성 및 합성**:
    - **핵심 문장 요약**: Gemini AI가 영상을 분석하여 핵심 구문 위주 자막 생성 및 2.5초 이상 노출 보정.
    - **스타일 최적화**: 반투명 검정 배경 박스 + 흰색 글자, 정규표현식 기반의 안정적인 파싱.
  - **동영상 로고 및 효과**: 우측 하단 로고 삽입 및 마지막 3초 애니메이션 아웃로 효과.
  - **마케팅 메타데이터**: 다국어 템플릿(`desc_ko.md`, `desc_en.md`) 기반 스토리텔링 설명, SEO 해시태그, 클릭 가능 링크 생성.
  - **자동 정리**: 업로드 완료 후 임시 파일(SRT, 중간 영상 등) 자동 삭제.

### 4. 유튜브 재업로드 전용기 (레거시)
업로드 중 한도 초과나 오류로 실패했을 때, 이미 가공된 영상과 메타데이터를 사용하여 업로드만 다시 수행합니다.

> ⚠️ **참고**: 이 기능은 `legacy/youtube_poster/upload_only.py`로 이동되었습니다. 웹 UI를 통한 업로드를 권장합니다.

---

## 🛠 설치 및 설정

### 1. 가상환경 및 패키지 설치
```bash
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
# 시스템에 ffmpeg가 설치되어 있어야 합니다. (brew install ffmpeg)
```

### 2. 환경 변수 설정 (`.env`)
```env
LINKEDIN_CLIENT_ID=your_id
LINKEDIN_CLIENT_SECRET=your_secret
LINKEDIN_ACCESS_TOKEN=your_token
LINKEDIN_PERSON_URN=urn:li:person:your_urn
GEMINI_API_KEY=your_key
YOUTUBE_API_KEY=your_youtube_api_key
```

---

## 📝 라이선스
이 프로젝트는 MIT 라이선스를 따릅니다.
