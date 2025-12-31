# 🚀 LinkedIn Auto-Poster & Wiki Converter (AI Tech Curator)

이 프로젝트는 웹 콘텐츠를 분석하여 전문적인 LinkedIn 포스트를 자동 생성하고, 마크다운 파일을 고품질 HTML 위키 페이지로 변환하는 AI 기반 자동화 도구입니다. **Gemini 3 Flash Preview** 모델로 텍스트를 처리하고, **Gemini 2.5 Flash Image** 모델로 요약 이미지를 생성하여 최신 AI 기술을 통합적으로 활용합니다.

## 🌟 주요 기능

### 1. LinkedIn 자동 포스팅 (AI Tech Curator)
-   **멀티 플랫폼 스크레이핑**: 일반 HTML 및 Google Docs 기반 콘텐츠에서 제목, 본문, 이미지를 정확하게 추출합니다.
-   **AI 전문 요약 (Tech Curator Persona)**: 전문 기술 큐레이터의 시각에서 독자의 호기심을 유발하는 깊이 있는 기술 리포트 스타일의 포스트를 생성합니다.
-   **LinkedIn 최적화 포맷팅**: 유니코드 볼드체 변환, 가독성 높은 여백 처리, 자동 해시태그 생성을 수행합니다.
-   **이미지 및 링크 연동**: 본문 내 이미지를 LinkedIn 자산으로 자동 등록하고 원문 블로그 링크를 삽입합니다.

### 2. 마크다운-HTML 위키 변환
-   **다국어 동시 변환**: 하나의 마크다운 파일을 국문과 영문 버전으로 동시 변환하며, 각각 `html/ko/`, `html/en/` 디렉토리에 저장합니다.
-   **파일명 동기화**: 국문과 영문 버전의 파일명을 동일한 영문 슬러그(Slug)로 통일하여 배포 경로 및 인코딩 문제를 해결합니다.
-   **AI 요약 이미지 생성**: **Gemini 2.5 Flash Image** 모델을 사용하여 기술 일러스트를 생성하고 `html/images/`에 저장합니다.
-   **구조적 자동 배포 및 정리**: 변환 완료 후 `html/` 디렉토리의 전체 구조를 `/Volumes/Transcend/Projects/tech-blog/html`로 복사하고, 로컬의 임시 `html/` 디렉토리는 자동으로 삭제하여 공간을 최적화합니다.
-   **고품질 렌더링**: MathJax v3를 이용한 수식 줄바꿈 방지 처리 및 코드 블록 다크 모드 스타일이 적용됩니다.

## 🛠 설치 및 설정

### 1. 가상환경 구축 (Python 3.12 권장)
```bash
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 2. 환경 변수 설정 (.env)
```env
LINKEDIN_CLIENT_ID=your_client_id
LINKEDIN_CLIENT_SECRET=your_client_secret
LINKEDIN_REDIRECT_URI=https://tony.bany.ai
LINKEDIN_ACCESS_TOKEN=your_access_token
LINKEDIN_PERSON_URN=urn:li:person:your_urn
GEMINI_API_KEY=your_gemini_api_key
```

## 🚀 실행 방법

### 1. 마크다운 위키 변환 및 이미지 생성
```bash
python md_to_html_converter.py
```
- `source/` 폴더의 모든 `.md` 파일을 변환하여 `html/` 폴더에 임시 저장합니다.
- 변환 시 **Gemini 2.5 Flash Image** 모델을 통해 본문 내용을 요약한 16:9 비율의 기술 일러스트를 자동 생성합니다.
- 생성된 결과물은 자동으로 절대 경로 `/Volumes/Transcend/Projects/tech-blog/html`로 복사된 후, 로컬의 `html/` 폴더는 삭제됩니다.

### 2. LinkedIn 포스팅 실행
```bash
python main.py
```
-   **스마트 콘텐츠 참조**: `contents.json`의 URL 슬러그를 기반으로 배포 디렉토리(`/Volumes/Transcend/Projects/tech-blog/html`)에서 HTML과 이미지를 자동으로 찾아냅니다.
-   **지능형 이미지 매칭**: 패턴 매칭을 통해 관련 요약 이미지를 찾아내고, HTML 내의 상대 경로 이미지까지 분석하여 LinkedIn에 업로드합니다.
-   **글자 수 자동 관리**: 유니코드 볼드체 사용 시의 바이트 증가를 고려하여 LinkedIn 제한(3,000자) 내로 요약문을 자동 조절합니다.
-   실행 후 생성된 포스트 프리뷰와 첨부된 이미지를 확인하고 `y`를 입력하면 LinkedIn에 게시됩니다.

## 📂 프로젝트 구조

-   `main.py`: LinkedIn 포스팅 프로세스 제어
-   `md_to_html_converter.py`: 마크다운-HTML 위키 변환 엔진
-   `scraper.py`: 웹 콘텐츠 및 이미지 추출 엔진
-   `summarizer.py`: Gemini AI 기반 요약 및 텍스트 처리
-   `linkedin_poster.py`: LinkedIn API 연동 및 자산 관리
-   `source/`: 변환할 마크다운 파일 저장소
-   `html/`: 변환된 HTML 파일 저장소
-   `template.html`: 위키 페이지 디자인 템플릿
-   `auth_helper.py`: LinkedIn OAuth 인증 도구

## 📝 라이선스

이 프로젝트는 MIT 라이선스를 따릅니다.
