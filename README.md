# 🚀 AI Auto-Poster & Content Automation System

이 프로젝트는 마크다운 위키 변환, 테크 블로그 자동 포스팅, 유투브 콘텐츠 자동 포스팅의 세 가지 주요 기능을 제공하는 통합 콘텐츠 자동화 시스템입니다.

## 📂 프로젝트 구조

```text
.
├── core/                   # 공용 코어 모듈
│   ├── auth_helper.py      # LinkedIn OAuth 인증 도구
│   ├── linkedin_poster.py  # LinkedIn API 연동 엔진
│   └── summarizer.py       # Gemini AI 요약 엔진
├── 1_md_converter/         # 기능 1: 마크다운 위키 변환기
│   ├── md_to_html_converter.py
│   ├── template.html
│   └── source/             # 변환할 마크다운 원본 파일 저장소
├── 2_blog_poster/          # 기능 2: 테크 블로그 자동 포스팅기
│   ├── linkedin_blog_poster.py
│   ├── scraper.py
│   └── contents.json
├── 3_youtube_poster/       # 기능 3: 유투브 동영상 자동 포스팅기 (개발 중)
│   └── youtube_poster.py
├── requirements.txt        # 의존성 패키지 목록
└── .env                    # 환경 변수 및 API 키 설정
```

---

## 🌟 주요 기능 및 사용법

### 1. 마크다운 위키 변환기 (`1_md_converter`)
마크다운 파일을 고품질 HTML 위키 페이지로 변환하고 AI 요약 이미지를 자동 생성합니다.

- **실행 방법**:
  ```bash
  python 1_md_converter/md_to_html_converter.py
  ```
- **주요 기능**:
  - `1_md_converter/source/` 내 마크다운 파일을 분석하여 국문/영문 HTML 동시 생성.
  - **Gemini 2.5 Flash Image** 기반의 16:9 기술 일러스트 자동 생성.
  - 배포 경로(`/Volumes/Transcend/Projects/tech-blog/html`)로 자동 복사 및 로컬 정리.
  - MathJax 수식 및 코드 블록 다크 모드 최적화.

### 2. 테크 블로그 자동 포스팅기 (`2_blog_poster`)
생성된 위키 페이지 또는 외부 블로그 URL을 분석하여 LinkedIn에 전문적인 기술 포스트를 작성합니다.

- **실행 방법**:
  ```bash
  python 2_blog_poster/linkedin_blog_poster.py
  ```
- **주요 기능**:
  - `contents.json`의 URL을 기반으로 로컬/배포된 HTML 콘텐츠 우선 분석.
  - 전문 기술 큐레이터 스타일의 AI 요약문 생성.
  - 유니코드 볼드체 및 LinkedIn 글자 수 제한(3,000자) 자동 관리.
  - 이미지 자동 업로드 및 원문 링크 삽입.

### 3. 유투브 동영상 자동 포스팅기 (`3_youtube_poster`)
유투브 영상과 관련 PDF 문서를 분석하여 자동으로 영상을 업로드하고 SEO에 최적화된 메타데이터를 작성합니다.

- **사전 준비**:
  1. Google Cloud Console에서 YouTube Data API v3를 활성화합니다.
  2. OAuth 2.0 클라이언트 ID를 생성하고 `client_secrets.json` 파일을 다운로드하여 `3_youtube_poster/` 폴더에 넣습니다.
  3. 업로드할 PDF와 MP4 파일을 `3_youtube_poster/v_source/` 폴더에 넣습니다.
- **실행 방법**:
  ```bash
  python 3_youtube_poster/youtube_poster.py
  ```
- **주요 기능**:
  - `v_source/` 내 PDF 파일을 읽어 핵심 내용을 추출.
  - Gemini AI를 활용하여 제목, 설명, 태그 등 YouTube SEO 메타데이터 자동 생성.
  - YouTube API를 통해 지정된 계정(`tony@banya.ai`)으로 영상 자동 업로드.
  - 업로드 전 프리뷰 및 사용자 확인 단계 포함.

---

## 🛠 설치 및 설정

### 1. 가상환경 및 패키지 설치
```bash
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 2. 환경 변수 설정 (`.env`)
프로젝트 루트에 `.env` 파일을 생성하고 다음 정보를 입력합니다.
```env
LINKEDIN_CLIENT_ID=your_id
LINKEDIN_CLIENT_SECRET=your_secret
LINKEDIN_ACCESS_TOKEN=your_token
LINKEDIN_PERSON_URN=urn:li:person:your_urn
GEMINI_API_KEY=your_key
```

---

## 📝 라이선스
이 프로젝트는 MIT 라이선스를 따릅니다.
