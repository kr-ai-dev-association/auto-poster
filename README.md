# 🚀 LinkedIn Auto-Poster & Wiki Converter (AI Tech Curator)

이 프로젝트는 웹 콘텐츠를 분석하여 전문적인 LinkedIn 포스트를 자동 생성하고, 마크다운 파일을 고품질 HTML 위키 페이지로 변환하는 AI 기반 자동화 도구입니다. **Gemini 3 Flash Preview** 모델을 사용하여 최신 AI 성능을 활용합니다.

## 🌟 주요 기능

### 1. LinkedIn 자동 포스팅 (AI Tech Curator)
-   **멀티 플랫폼 스크레이핑**: 일반 HTML 및 Google Docs 기반 콘텐츠에서 제목, 본문, 이미지를 정확하게 추출합니다.
-   **AI 전문 요약 (Tech Curator Persona)**: 전문 기술 큐레이터의 시각에서 독자의 호기심을 유발하는 깊이 있는 기술 리포트 스타일의 포스트를 생성합니다.
-   **LinkedIn 최적화 포맷팅**: 유니코드 볼드체 변환, 가독성 높은 여백 처리, 자동 해시태그 생성을 수행합니다.
-   **이미지 및 링크 연동**: 본문 내 이미지를 LinkedIn 자산으로 자동 등록하고 원문 블로그 링크를 삽입합니다.

### 2. 마크다운-HTML 위키 변환
-   **Gemini 3 기반 변환**: `source/` 디렉토리의 `.md` 파일을 AI가 분석하여 구조화된 HTML로 재구성합니다.
-   **반응형 레이아웃**: `@template.html`의 CSS/JS 설정을 100% 반영하여 모바일과 데스크탑에 최적화된 레이아웃을 제공합니다.
-   **LaTeX 수식 렌더링**: **MathJax v3**를 통합하여 문서 내의 복잡한 수식을 미려하게 렌더링합니다.

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

### LinkedIn 포스팅 실행
```bash
python main.py
```
- 실행 후 생성된 포스트 프리뷰를 확인하고 `y`를 입력하면 LinkedIn에 게시됩니다.

### 마크다운 위키 변환 실행
```bash
python md_to_html_converter.py
```
- `source/` 폴더의 모든 `.md` 파일을 변환하여 `html/` 폴더에 저장합니다.

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
