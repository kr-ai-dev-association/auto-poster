# 🚀 AI Auto-Poster & Content Automation System

통합 웹 애플리케이션으로 Wiki 자동 변환/배포, YouTube 영상 편집/업로드, LinkedIn 소셜 홍보를 한 번에 처리하는 AI 기반 콘텐츠 자동화 시스템입니다.

## 🎯 주요 특징

- 🌐 **웹 UI**: FastAPI + Alpine.js 기반의 직관적인 인터페이스
- 🔒 **보안 시스템**: DB 암호화 기반 보안 파일 관리
- 🤖 **AI 통합**: Google Gemini를 활용한 자동 콘텐츠 생성
- 🔐 **인증/권한**: JWT 기반 회원 관리 및 슈퍼 관리자 승인 시스템
- 🌍 **다국어**: 한국어/영어 자동 변환 및 배포
- 🗺️ **기획 고도화**: Google Search 기반 팩트 체크 및 이미지 기획
- ⚡ **성능 최적화**: 대용량 PDF (File API) 지원 및 대본 기반 고속 메타데이터 생성

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
│   │   ├── youtube_service.py    # YouTube 업로드 + 썸네일 자동 생성
│   │   ├── pdf2mp4_service.py    # PDF to MP4 변환 (Basic/Smart 모드)
│   │   ├── audio_generator_service.py   # 대본 생성 + TTS 음성 생성
│   │   └── content_generator_service.py # AI 기획안 + 이미지 생성
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

# Gen Video 기능용
pip install pdf2image moviepy
pip install git+https://github.com/openai/whisper.git  # Smart 모드용

# OCR 기능용 (이미지 기반 PDF 텍스트 추출)
pip install paddlepaddle paddleocr
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

#### UI/UX 특징
- **접이식 사이드바**: 좌측 사이드바를 접어 작업 공간 확대 (접힌 상태에서 아이콘 + 툴팁 표시)
- **메뉴 구성**: 영상 생성 → 타이밍 편집 → 유튜브 포스터 → 위키 오토 포스터 → 영상 관리
- **반응형 디자인**: 다양한 화면 크기에 최적화
- **다국어 지원**: 한국어/영어 UI 전환

#### 📝 Wiki Auto Poster
- 마크다운 파일 업로드 또는 직접 작성
- **타이틀 이미지 생성 방식 선택**:
  - 🤖 **자동 생성**: Gemini AI가 콘텐츠를 분석하여 16:9 요약 이미지 자동 생성
  - ✏️ **수동 삽입**: MD 파일에 이미지 링크를 직접 삽입 (구글 드라이브 링크 자동 변환 지원)
- 구글 드라이브 이미지 링크 자동 변환 (공유 링크 → 직접 이미지 URL)
- 한국어/영어 동시 변환 및 배포
- Firebase/GCS 자동 배포
- HTML 미리보기 기능
- LinkedIn 자동 홍보 (한글/영문)

#### 🎬 Youtube Poster
- PDF 기반 메타데이터 자동 생성 (제목, 설명, 태그)
- **대용량 PDF 처리**: 
  - 50MB 이상 PDF 자동 압축 (PyPDF2 + img2pdf 기반)
  - 기본 압축 효과 부족 시 이미지 품질 낮춰서 재압축 (JPEG 70%, DPI 150)
  - 텍스트 기반 PDF: 텍스트 추출 후 AI 분석 (최대 50페이지)
  - 이미지 기반 PDF: 압축 후 File API 사용 (50MB 이하)
- **썸네일 자동 생성**: PDF 첫 페이지를 YouTube 썸네일(1280x720)로 자동 변환 및 업로드
- 로고 합성 및 비디오 편집
- 카테고리별 리소스 관리 (tech/entertainment/lifestyle/beauty)
- YouTube 자동 업로드
- LinkedIn 소셜 홍보 통합

#### 🎬 Gen Video (PDF to MP4)
- **Basic 모드**: PDF를 균등 분배된 슬라이드 영상으로 변환
- **Smart 모드**: Whisper 음성 인식 기반 PDF 페이지와 오디오 자동 동기화
  - **PDF 내장 나레이션 메타데이터**: PDF 파일에 임베드된 나레이션 텍스트를 우선 사용하여 정확한 슬라이드 타이밍 계산 (OCR 없이도 완벽한 매칭)
  - **Page 언급 감지**: 오디오에서 "Page X" 언급을 감지하여 슬라이드 타이밍 정확도 향상
  - **폴백 지원**: PDF 메타데이터 → JSON 사이드카 파일 → OCR 순서로 텍스트 추출
- **AI 자막 생성**: 3단계 상세도 선택 (키워드/요약/전체)
- NVENC GPU 가속 인코딩 (고속 변환)
- 생성된 영상 및 PDF 목록 관리 (다운로드/삭제)
- **타이밍 에디터**: 생성된 영상의 슬라이드 타이밍을 시각적으로 조정
  - 드래그 앤 드롭으로 슬라이드 순서 및 시간 조정
  - 좌/우 핸들 드래그로 시작/종료 시간 세밀 조정
  - 실시간 미리보기 및 재생 위치 표시
  - **OCR/오디오 텍스트 비교**: 슬라이드별 OCR 텍스트와 Whisper 오디오 텍스트 동시 표시
  - **실시간 재변환 진행률**: 재변환 시 프로그레스 바와 상태 메시지 표시
  - 타이밍 저장 후 영상 재변환 워크플로우

#### 📁 영상 관리
- 생성된 영상 통합 목록 조회
- **단계별 상태 표시**: 생성 → 타이밍 적용 → 포스팅 완료
- 필터링: 단계, 카테고리, 파일명 검색
- 영상 정보 표시: 파일명, 영상길이, 카테고리, PDF언어, 생성자, 생성시간
- 빠른 작업: 다운로드, YouTube 포스팅, 삭제

#### 🎙️ 오디오 생성기
PDF 문서를 분석하여 YouTube 영상용 대본을 생성하고 TTS로 음성을 생성합니다.
- **대본 자동 생성**: Gemini AI가 PDF를 분석하여 자연스러운 TTS용 대본 생성
- **TTS 음성 생성**: Gemini TTS를 사용한 고품질 음성 생성
- **다양한 음성 선택**: 8가지 음성 (Leda, Zephyr, Aoede, Charon, Fenrir, Kore, Puck, Orbit)
- **대본 스타일**: 교육적, 캐주얼, 전문적 스타일 선택
- **백그라운드 처리**: 페이지 새로고침해도 작업 계속 진행
- **다국어 지원**: 한국어/영어 대본 생성

#### 🎨 콘텐츠 생성기
AI 기반으로 YouTube 영상용 콘텐츠를 기획하고 슬라이드 이미지를 자동 생성합니다.
- **기획안 자동 생성**: 주제 입력 시 Gemini AI가 슬라이드 구조, 대본, 이미지 프롬프트 자동 생성
- **서브슬라이드 시스템**: 각 슬라이드에 2~4개의 서브슬라이드(프레임) 포함
  - `title` 타입: 슬라이드 주제 소개 화면 (제목 + 부제 + 핵심 메시지)
  - `detail` 타입: 세부 설명 화면 (데이터, 비교, 분석 등 심층 내용)
  - 화면 전환 빈도 2~3배 증가로 시각적 몰입도 향상
- **AI 이미지 생성**: Gemini를 활용한 서브슬라이드별 이미지 자동 생성
  - 텍스트 오버레이 포함 (title: 제목+부제+핵심 포인트 / detail: 핵심 포인트만)
  - 16:9 YouTube 최적화 비율
- **PDF 변환**: 생성된 이미지들을 PDF로 합쳐서 Gen Video에서 사용
  - **나레이션 메타데이터 임베드**: PDF 파일에 서브슬라이드별 나레이션 텍스트 자동 포함 (Smart 모드 타이밍 정확도 향상)
- **레거시 호환**: 서브슬라이드 없는 기존 기획안도 정상 동작 (`get_flat_sub_slides()` 자동 변환)
- **기획안 관리**: 기획안 목록, 이미지/프레임 개수 표시, 삭제 기능
- **이미지 미리보기**: 모달 창에서 이미지 확대, 좌우 네비게이션, 키보드 지원
- **일괄 삭제**: 기획안별 이미지 전체 삭제 기능

#### ⚡ 자동 파이프라인
주제 입력만으로 기획안 생성부터 YouTube 업로드까지 전체 과정을 자동화합니다.
- **원클릭 자동화**: 주제 입력 → 기획안 → 이미지 → PDF(나레이션 임베드) → 대본 → 오디오 → 비디오 → YouTube 업로드
- **실시간 진행 상황**: 7단계 파이프라인 진행률 및 상태 실시간 표시
- **통합 콘텐츠 ID**: `pipe_YYYYMMDD_xxxxxxxx` 형식으로 모든 생성물 추적
- **카테고리 지원**: tech, beauty, lifestyle, entertainment 중 선택
- **TTS 음성 선택**: 8가지 음성 중 선택 (기본값: Leda)
- **YouTube 공개 설정**: 비공개, 일부 공개, 공개 선택
- **Slack 알림**: 파이프라인 완료 시 YouTube URL 포함 알림 전송
- **AI 대본 생성**: PDF 이미지 분석을 통한 풍부한 대본 자동 생성 (5분+ 영상)

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
3. **타이틀 이미지 생성 방식 선택**:
   - **자동 생성**: Gemini AI가 자동으로 이미지 생성 (기본값)
   - **수동 삽입**: MD 파일 맨 위에 `![이미지 설명](구글드라이브링크)` 형식으로 삽입
4. 마크다운 파일 업로드 또는 내용 입력
5. "변환 및 배포" 버튼 클릭
6. 완료 후 미리보기 및 LinkedIn 홍보 가능

#### 구글 드라이브 이미지 사용법 (수동 삽입 모드)
1. 구글 드라이브에 이미지 업로드
2. 파일 우클릭 → "공유" → "링크가 있는 모든 사용자"로 설정
3. 마크다운 파일 맨 위에 다음 형식으로 삽입:
   ```markdown
   ![이미지 설명](https://drive.google.com/file/d/FILE_ID/view?usp=sharing)
   ```
4. Auto Poster가 자동으로 구글 드라이브 링크를 사용 가능한 이미지 URL로 변환

#### 배포 구조 및 저장 위치
변환된 HTML 콘텐츠는 **Google Cloud Firestore**에 저장됩니다:

**Firestore 구조:**
- **컬렉션**: `static-wiki`
- **문서 ID**: `wiki_id` (영문 슬러그, 예: `ai-trends-2025`)
- **문서 구조**:
  ```json
  {
    "id": "ai-trends-2025",
    "titles": {
      "ko": "2025 AI 트렌드 전망",
      "en": "AI Trends 2025"
    },
    "content": {
      "ko": "<html>한국어 HTML 콘텐츠</html>",
      "en": "<html>English HTML content</html>"
    },
    "thumbnailUrl": "https://storage.googleapis.com/.../wiki-images/.../image.png",
    "lastUpdated": "2025-01-15",
    "type": "firestore-content",
    "createdAt": "2025-01-15T10:30:00Z"
  }
  ```

**이미지 저장 위치 (Google Cloud Storage):**
- **경로**: `wiki-images/{wiki_id}/{filename}`
- **URL 형식**: `https://storage.googleapis.com/{bucket_name}/wiki-images/{wiki_id}/{filename}`
- **예시**: `https://storage.googleapis.com/my-bucket/wiki-images/ai-trends-2025/summary.png`

**ID 매핑 (Firestore):**
- 원본 파일명과 `wiki_id`의 매핑 정보는 Firestore의 별도 문서에 저장됩니다.
- 동일한 파일명으로 업로드 시 기존 `wiki_id`를 재사용합니다.

**접근 URL:**
- 배포된 콘텐츠는 `https://tony.banya.ai/report/{wiki_id}` 형식으로 접근 가능합니다.

### Youtube Poster 사용법
1. 메인 화면에서 "Youtube Poster" 선택
2. 카테고리 선택 (tech/entertainment)
3. 영상 파일 + PDF 메타데이터 소스 업로드
   - 직접 업로드 또는 Gen Video에서 생성된 영상/PDF 선택 가능
4. AI 메타데이터 미리보기 확인
5. 옵션 선택:
   - **AI 자막 자동 생성**: Whisper 기반 자막 생성
   - **PDF 첫 페이지를 썸네일로 사용**: PDF 첫 페이지를 1280x720 썸네일로 자동 변환
6. "Final Edit & Upload" 버튼 클릭
7. 완료 후 LinkedIn 소셜 홍보 가능

### Gen Video (PDF to MP4) 사용법
1. 메인 화면에서 "Gen Video" 선택
2. 변환 모드 선택:
   - **Basic**: 균등 분배 (오디오 없이도 가능)
   - **Smart**: 오디오와 PDF 나레이션 매칭 (오디오 필수)
     - PDF에 나레이션 메타데이터가 포함된 경우 자동으로 사용 (콘텐츠 생성기/자동 파이프라인으로 생성된 PDF)
     - 메타데이터가 없는 경우 OCR로 텍스트 추출 후 매칭
3. PDF 파일 업로드 (필수)
4. 오디오 파일 업로드 (Smart 모드 필수)
5. 해상도, 페이지당 시간 등 옵션 설정
6. "변환 시작" 버튼 클릭
7. 생성된 영상은 목록에서 다운로드/삭제 가능
8. YouTube Poster에서 바로 업로드 가능

### 타이밍 에디터 사용법
생성된 영상의 슬라이드 타이밍을 미세 조정하는 기능입니다.

1. Gen Video 목록에서 영상의 **편집** 버튼 클릭
2. 타이밍 에디터가 열리면:
   - **좌측**: PDF 슬라이드 미리보기 (줌/패닝 지원)
   - **우측 상단**: 현재 슬라이드의 OCR 텍스트
   - **우측 하단**: 해당 구간의 Whisper 오디오 텍스트 (Smart 모드 영상만)
   - **하단 타임라인**: 슬라이드 블록 시각화
3. 슬라이드 시간 조정:
   - **중앙 영역 드래그**: 슬라이드 전체를 이동
   - **좌측 핸들 드래그**: 시작 시간 조정 (이전 슬라이드 종료 시간도 연동)
   - **우측 핸들 드래그**: 종료 시간 조정 (다음 슬라이드 시작 시간도 연동)
   - **테이블 드래그 앤 드롭**: 슬라이드 순서 변경
4. **타이밍 저장** 버튼으로 변경사항 저장
5. 저장 후 **영상 재변환** 버튼이 나타나면 클릭하여 새 영상 생성
   - 재변환 중 프로그레스 바로 진행 상황 확인 가능
6. 추가 수정이 필요하면 타이밍을 다시 조정 (저장 버튼으로 복귀)

### 영상 관리 사용법
생성된 모든 영상을 한 곳에서 관리할 수 있습니다.

1. 좌측 메뉴에서 "영상 관리" 클릭
2. **필터 기능**:
   - **단계**: 생성 / 타이밍 적용 / 포스팅 완료
   - **카테고리**: tech, entertainment 등
   - **검색**: 파일명으로 검색
3. **단계 구분**:
   - 🔵 **생성**: 새로 생성된 영상
   - 🟡 **타이밍 적용**: 타이밍 편집 후 재변환된 영상
   - 🟢 **포스팅 완료**: YouTube 업로드 완료
4. **작업 버튼**:
   - **다운로드**: 영상 파일 다운로드
   - **YouTube 포스팅**: YouTube Poster로 이동하여 바로 업로드
   - **삭제**: 영상 및 관련 파일 삭제

### 오디오 생성기 사용법
PDF 문서에서 YouTube 영상용 대본과 음성을 자동 생성합니다.

1. 좌측 메뉴에서 "오디오 생성" 클릭
2. PDF 파일 업로드
3. 옵션 설정:
   - **언어**: 한국어/영어
   - **스타일**: 교육적, 캐주얼, 전문적
   - **음성**: 8가지 TTS 음성 중 선택
4. 생성 방법 선택:
   - **대본만 생성**: PDF 분석 후 대본만 생성 (수정 가능)
   - **오디오 생성**: 대본 생성 후 TTS 음성까지 자동 생성
5. 대본 편집 후 "오디오 생성" 버튼으로 음성 파일 생성
6. 생성된 오디오는 목록에서 다운로드/재생/삭제 가능
7. Gen Video에서 오디오 파일로 활용 가능

**백그라운드 처리**: 대본/오디오 생성 중 페이지를 새로고침해도 작업이 계속 진행됩니다.

### 콘텐츠 생성기 사용법
AI 기반으로 YouTube 영상용 슬라이드 콘텐츠를 자동 생성합니다.

1. 좌측 메뉴에서 "콘텐츠 생성" 클릭
2. **1단계: 기획안 생성**
   - 주제 입력 (예: "2025년 AI 트렌드")
   - 카테고리 선택 (교육, 리뷰, 뉴스 등)
   - 슬라이드 수 설정 (기본 15장)
   - "기획안 생성" 버튼 클릭
3. **2단계: 이미지 생성**
   - 기획안 목록에서 원하는 기획안 선택
   - "이미지 생성 시작" 버튼으로 모든 슬라이드 이미지 자동 생성
   - 생성된 이미지 미리보기 및 개별/전체 삭제 가능
4. **3단계: PDF 생성**
   - 이미지 생성 완료 후 "PDF 생성" 버튼 클릭
   - 생성된 PDF는 Gen Video에서 영상 변환에 사용 가능

### 자동 파이프라인 사용법
주제 입력만으로 전체 영상 제작 과정을 자동화합니다.

1. 좌측 메뉴에서 "콘텐츠 생성" 클릭 후 **자동** 탭 선택
2. **설정 입력**:
   - **주제/기획 아이디어**: 영상 주제 입력 (예: "2026년 AI 투자 전망")
   - **카테고리**: tech, beauty, lifestyle, entertainment 중 선택
   - **슬라이드 수**: 10~20장 (기본 15장)
   - **언어**: 한국어/영어
   - **TTS 음성**: 8가지 음성 중 선택 (기본: Leda)
   - **YouTube 공개 설정**: 비공개/일부 공개/공개
3. **파이프라인 시작** 버튼 클릭
4. **7단계 자동 진행**:
   - 1️⃣ 기획안 생성 (Google Search 기반 팩트 체크)
   - 2️⃣ 슬라이드 이미지 생성 (AI + 웹 이미지)
   - 3️⃣ PDF 생성
   - 4️⃣ AI 대본 생성 (PDF 분석 기반)
   - 5️⃣ TTS 오디오 생성
   - 6️⃣ Smart 모드 비디오 생성 (NVENC GPU 가속)
   - 7️⃣ YouTube 자동 업로드
5. **완료 알림**: Slack DM으로 YouTube URL 포함 알림 전송
6. **결과 확인**: 영상 관리 탭에서 생성된 영상 확인 및 관리

### 보안 파일 관리
1. 슈퍼 관리자로 로그인
2. 좌측 메뉴 "보안 파일 관리" 클릭
3. 파일 선택 및 타입 지정
4. 키 프레이즈 입력 (형식: `SUPER_ADMIN_ID:SUPER_ADMIN_PW`)
5. 암호화하여 업로드

---

## 🎨 콘텐츠 기획안 프롬프트 설계

AI 기획안 생성(`content_generator_service.py`)의 프롬프트는 **전문 에디토리얼 수준**의 콘텐츠를 생성하도록 설계되었습니다.

### 프롬프트 구조

```
역할 정의 → 언어/구조 제약 → 주제 입력 → 나레이션 품질 기준 → 이미지 프롬프트 품질 기준 → JSON 출력 형식 → 주의사항
```

### JSON 출력 구조

| 필드 | 설명 | 사용처 |
|------|------|--------|
| `title` | 영상 제목 (부제 포함) | YouTube 메타데이터 |
| `description` | 영상 설명 (2-3문장) | YouTube 메타데이터 |
| `slides[].title` | 슬라이드 제목 | title 타입 서브슬라이드 텍스트 오버레이 |
| `slides[].sub_slides[]` | 서브슬라이드 배열 (2~4개) | 각 프레임별 이미지/나레이션 |
| `slides[].sub_slides[].sub_number` | 서브슬라이드 번호 (1부터) | 파일명, 정렬 |
| `slides[].sub_slides[].type` | `"title"` 또는 `"detail"` | 텍스트 오버레이 스타일 분기 |
| `slides[].sub_slides[].content` | 화면 표시 핵심 메시지 (**최대 15단어**) | 이미지 텍스트 오버레이 |
| `slides[].sub_slides[].narration` | TTS 나레이션 대본 (**100자+, 15-25초**) | 오디오 생성, PDF 메타데이터 |
| `slides[].sub_slides[].image_prompt` | 이미지 생성 프롬프트 (영어, **3문장+**) | Gemini 이미지 생성 |
| `slides[].sub_slides[].web_image_keyword` | 웹 검색 이미지 키워드 | 참조 이미지 다운로드 |
| `slides[].sub_slides[].use_web_image` | 웹 이미지 사용 여부 | 이미지 생성 분기 |
| `hook` | 영상 시작 후크 (0-30초) | 인트로 |
| `call_to_action` | 구독/좋아요 유도 멘트 | 아웃트로 |
| `tags` | 관련 태그 목록 | YouTube 태그 |

### 서브슬라이드 시스템

각 슬라이드는 2~4개의 서브슬라이드(프레임)로 구성됩니다:
- **title 타입** (첫 번째): 슬라이드 주제 소개 — 상단 제목+부제, 하단 핵심 메시지
- **detail 타입** (이후): 세부 설명 — 하단 핵심 포인트만 (48pt 큰 폰트)
- 파일 명명: `{plan_id}_slide_{slide:02d}_{sub:02d}.png` (예: `pipe_20260211_abc123_slide_01_02.png`)
- PDF 페이지 수 = 총 서브슬라이드 수 → 기존 Smart 모드 타이밍 알고리즘이 자동으로 처리
- 레거시 기획안(sub_slides 없음)은 `get_flat_sub_slides()` 헬퍼가 자동 변환

### 나레이션 품질 기준

| 항목 | 기준 |
|------|------|
| **서브슬라이드당** | 최소 100자, 15-25초 |
| **슬라이드당 합계** | 최소 300자 (모든 서브슬라이드 narration 합) |
| **전체 합계** | 최소 4,000자 이상 (7-10분 영상) |
| **1문단** | 핵심 개념 + 배경 지식/역사적 맥락/과학적 원리 분석 |
| **2문단** | 실용적 적용 방법, 전문가 팁, 시청자 인사이트 |
| **문체** | 자연스러운 구어체 + 전문적 깊이 (에디토리얼 수준) |

**예시:**
> 토마토 스파게티는 단순한 탄수화물 섭취를 위한 수단을 넘어, 이탈리아 남부 나폴리에서 시작되어 전 세계 주방의 표준이 된 문화적 아이콘입니다. 현대의 홈 쿠킹 트렌드는 레스토랑 수준의 정교한 기술을 가정 내 조리 환경에 이식하려는 '전문가적 아마추어리즘'을 지향합니다...

### 이미지 프롬프트 품질 기준

프로페셔널 포토그래피 디렉션 수준으로 작성하며 다음 요소를 **반드시 포함**:

| 요소 | 설명 | 예시 |
|------|------|------|
| **구도** | 촬영 앵글/프레이밍 | wide shot, close-up, flat-lay, macro |
| **조명** | 광원 종류/방향 | golden hour, studio lighting, dramatic side light |
| **카메라** | 장비/렌즈/설정 | Phase One XF, 80mm lens, f/2.8 |
| **분위기** | 색감/무드 | warm tones, moody atmosphere, vibrant |
| **해상도** | 출력 품질 | 8k resolution, photorealistic |

**예시:**
> A wide, cinematic shot of a warm, sunlit rustic Italian kitchen. In the foreground, a beautifully plated tomato spaghetti with a glossy sauce and a fresh basil leaf sits on a dark, textured stone table. Soft steam is rising from the plate. The lighting is natural golden hour window light, creating long, soft shadows. Captured with a Phase One XF camera, 80mm lens, f/2.8, hyper-realistic texture, 8k resolution.

### 언어 규칙

| 언어 모드 | 한국어 필드 | 영어 필드 |
|-----------|------------|----------|
| `ko` (한국어) | title, description, content, narration, hook, call_to_action, tags | image_prompt, web_image_keyword, web_image_query |
| `en` (영어) | — | 모든 필드 |

### 도구 연동

- **Google Search**: 실시간 정보/최신 뉴스 주제에 자동 사용
- **모델**: Gemini (temperature: 0.2, max_output_tokens: 16384)

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

## 📋 변경 이력

### 2026-02-11: 서브슬라이드 시스템 도입
- **서브슬라이드**: 각 슬라이드에 2~4개 서브슬라이드(프레임) 추가 — 화면 전환 빈도 2~3배 증가
- **title/detail 타입**: title(주제 소개) + detail(세부 설명) 구분된 텍스트 오버레이
- **슬라이드 번호 배지 제거**: 화면 깔끔하게 정리
- **Gemini 프롬프트 업데이트**: 한국어/영어 모두 sub_slides 배열 생성하도록 변경
- **레거시 호환**: `get_flat_sub_slides()` 헬퍼로 기존 기획안 자동 변환
- **파일 명명 변경**: `slide_01.png` → `slide_01_01.png` (슬라이드번호_서브번호)
- **파이프라인 연동**: 서브슬라이드별 나레이션 수집 및 스크립트 조립
- **프론트엔드**: 프레임 수 표시, 서브슬라이드 상세 뷰 추가

### 2026-02-11: 오디오 청킹 개선
- TTS 청크 길이 ~1분 → ~2분으로 증가
- 청크 간 볼륨 정규화 (피크 기준 90%)
- 청크 사이 1초 무음 삽입

---

## 📝 라이선스
이 프로젝트는 MIT 라이선스를 따릅니다.
