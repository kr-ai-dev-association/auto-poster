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
│   ├── video_editor.py     # 로고 삽입 및 비디오 편집 도구
│   └── v_source/           # 업로드할 MP4, 분석용 PDF, 로고, 다국어 설명(desc_ko.md, desc_en.md) 저장소
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

### 2. 테크 블로그 자동 포스팅기 (`2_blog_poster`)
생성된 위키 페이지 또는 외부 블로그 URL을 분석하여 LinkedIn에 전문적인 기술 포스트를 작성합니다.

- **실행 방법**:
  ```bash
  python 2_blog_poster/linkedin_blog_poster.py
  ```
- **주요 기능**:
  - `contents.json`의 단일 URL을 기반으로 국문/영문 포스트 순차 생성.
  - 로컬/배포된 HTML 콘텐츠를 우선 분석하여 정확한 요약 수행.
  - 유니코드 볼드체 및 LinkedIn UTF-16 글자 수 제한(3,000자) 자동 관리.

### 3. 유투브 동영상 자동 포스팅기 (`3_youtube_poster`)
유투브 영상 분석, 로고 및 자막 합성, 마케팅 최적화 설명 생성 및 자동 업로드를 수행합니다.

- **사전 준비**:
  1. Google Cloud Console에서 **YouTube Data API v3** 활성화 및 OAuth 클라이언트 ID(JSON) 다운로드.
  2. `3_youtube_poster/client_secrets.json`으로 저장.
  3. `v_source/` 폴더에 MP4, PDF, 로고 이미지, 다국어 고정 설명(`desc_ko.md`, `desc_en.md`) 준비.
- **실행 방법**:
  ```bash
  python 3_youtube_poster/youtube_poster.py
  ```
- **주요 기능**:
  - **지능형 자막 생성 및 합성**:
    - **핵심 문장 요약**: Gemini AI가 영상을 분석하여 핵심 구문 위주 자막 생성 및 2.5초 이상 노출 보정.
    - **스타일 최적화**: 반투명 검정 배경 박스 + 흰색 글자, 정규표현식 기반의 안정적인 파싱.
  - **동영상 로고 및 효과**: 우측 하단 로고 삽입 및 마지막 3초 애니메이션 아웃로 효과.
  - **마케팅 메타데이터**: 다국어 템플릿(`desc_ko.md`, `desc_en.md`) 기반 스토리텔링 설명, SEO 해시태그, 클릭 가능 링크 생성.
  - **자동 정리**: 업로드 완료 후 임시 파일(SRT, 중간 영상 등) 자동 삭제.

### 4. 유튜브 재업로드 전용기 (`3_youtube_poster/upload_only.py`)
업로드 중 한도 초과나 오류로 실패했을 때, 이미 가공된 영상과 메타데이터를 사용하여 업로드만 다시 수행합니다.

- **사용 시점**:
  - `youtube_poster.py` 실행 중 업로드 단계에서 에러가 발생했을 때.
  - `v_source/`에 `final_youtube_post_*.mp4`와 `metadata_*.json` 파일이 남아있을 때.
- **실행 방법**:
  ```bash
  python 3_youtube_poster/upload_only.py
  ```
- **주요 기능**:
  - 이미 가공된 영상 목록 중 선택하여 즉시 업로드 세션 시작.
  - 별도의 AI 분석이나 영상 편집 과정(ffmpeg) 없이 매우 빠르게 진행.
  - 업로드 성공 후 선택적인 파일 정리 기능 제공.

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
```

---

## 📝 라이선스
이 프로젝트는 MIT 라이선스를 따릅니다.
