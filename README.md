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
│   └── contents.json       # 포스팅할 URL 설정 (단일 URL 방식)
├── 3_youtube_poster/       # 기능 3: 유투브 동영상 자동 포스팅기
│   ├── youtube_poster.py   # 메인 실행 스크립트
│   └── v_source/           # 업로드할 MP4 및 분석용 PDF 저장소
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
  - **Gemini 2.0 Flash** 기반의 16:9 기술 일러스트 자동 생성 및 2회 재시도 로직.
  - 영문 슬러그 기반의 파일명 동기화 (`filename_ko.html`, `filename_en.html`).
  - 배포 경로(`/Volumes/Transcend/Projects/tech-blog/html`)로 자동 복사 및 로컬 정리.
  - MathJax 수식 및 코드 블록 다크 모드 최적화.

### 2. 테크 블로그 자동 포스팅기 (`2_blog_poster`)
생성된 위키 페이지 또는 외부 블로그 URL을 분석하여 LinkedIn에 전문적인 기술 포스트를 작성합니다.

- **실행 방법**:
  ```bash
  python 2_blog_poster/linkedin_blog_poster.py
  ```
- **주요 기능**:
  - `contents.json`의 단일 URL을 기반으로 국문/영문 포스트 순차 생성.
  - 로컬/배포된 HTML 콘텐츠를 우선 분석하여 정확한 요약 수행.
  - 유니코드 볼드체 및 LinkedIn UTF-16 글자 수 제한(3,000자) 자동 관리 및 트리밍.
  - 이미지 자동 매칭 업로드 및 원문 링크 삽입.
  - 설정 파일이나 URL 누락 시 에러 출력 후 안전한 프로그램 종료.

### 3. 유투브 동영상 자동 포스팅기 (`3_youtube_poster`)
유투브 영상과 관련 PDF 문서를 분석하여 자동으로 영상을 업로드하고 SEO에 최적화된 메타데이터를 작성합니다.

- **사전 준비**:
  1. Google Cloud Console에서 **YouTube Data API v3**를 활성화합니다.
  2. OAuth 2.0 클라이언트 ID(데스크톱 앱)를 생성하고 JSON을 다운로드하여 `3_youtube_poster/client_secrets.json`으로 저장합니다.
  3. 업로드할 PDF와 MP4 파일을 `3_youtube_poster/v_source/` 폴더에 넣습니다.
- **실행 방법**:
  ```bash
  python 3_youtube_poster/youtube_poster.py
  ```
- **주요 기능**:
  - **Gemini 멀티모달 분석**: PDF 파일을 Gemini에 직접 업로드하여 내용을 완벽하게 파악.
  - **다국어 지원**: 실행 시 한국어(ko) 또는 영어(en) 중 원하는 언어로 메타데이터 생성 선택 가능.
  - **SEO 최적화**: 분석된 내용을 바탕으로 제목, 상세 설명, 해시태그 자동 생성.
  - **YouTube API 업로드**: 지정된 계정(`tony@banya.ai`)으로 영상 자동 업로드 및 업로드 전 프리뷰 제공.
  - **인증 관리**: 최초 1회 브라우저 인증 후 `token.pickle`을 통해 이후 자동 로그인 지원.

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
