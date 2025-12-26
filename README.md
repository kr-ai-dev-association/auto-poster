# 🚀 LinkedIn Auto-Poster (AI Tech Curator)

이 프로젝트는 특정 웹페이지(특히 Google Docs 기반 위키)의 콘텐츠를 자동으로 분석하고, **Gemini 2.0 Flash AI**를 사용하여 전문적인 LinkedIn 포스트를 작성 및 게시하는 자동화 도구입니다.

## 🌟 주요 기능

-   **멀티 플랫폼 스크레이핑**: 일반 HTML 페이지는 물론, `tony.banya.ai/wiki`와 같은 Google Docs 기반 콘텐츠에서 제목, 본문, 이미지를 정확하게 추출합니다.
-   **AI 전문 요약 (Tech Curator Persona)**: 1인칭 표현을 배제하고 전문 기술 큐레이터의 시각에서 독자의 호기심을 유발하는 깊이 있는 기술 리포트 스타일의 포스트를 생성합니다.
-   **Gemini 2.0 Flash 적용**: 최신 구글 제미나이 모델을 사용하여 빠르고 통찰력 있는 요약 결과물을 제공합니다.
-   **LinkedIn 최적화 포맷팅**:
    -   마크다운을 지원하지 않는 LinkedIn을 위해 핵심 키워드 **유니코드 볼드체** 변환 기능을 지원합니다.
    -   가독성을 극대화한 이모지 활용 및 여백(Double line breaks) 처리를 수행합니다.
    -   관련도 높은 해시태그 5개 이상을 자동으로 생성합니다.
-   **이미지 자동 업로드**: 웹페이지 내의 이미지를 추출하여 LinkedIn 자산(Asset)으로 등록하고 포스트에 첨부합니다.
-   **다국어 지원**: `contents.json` 설정을 통해 영어(EN)와 한국어(KO) 포스팅을 각각의 언어 특성에 맞게 처리합니다.

## 🛠 설치 및 설정

### 1. 가상환경 구축 (Python 3.12 권장)
```bash
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 2. 환경 변수 설정 (.env)
프로젝트 루트에 `.env` 파일을 생성하고 다음 정보를 입력합니다.
```env
LINKEDIN_CLIENT_ID=your_client_id
LINKEDIN_CLIENT_SECRET=your_client_secret
LINKEDIN_REDIRECT_URI=https://tony.bany.ai
LINKEDIN_ACCESS_TOKEN=your_access_token
LINKEDIN_PERSON_URN=urn:li:person:your_urn
GEMINI_API_KEY=your_gemini_api_key
```

### 3. 포스팅 대상 설정 (contents.json)
```json
{
    "en": { "url": "영문 블로그 주소" },
    "ko": { "url": "한글 블로그 주소" }
}
```

## 🚀 실행 방법

```bash
python main.py
```
- 실행 후 생성된 포스트 프리뷰를 확인하고 `y`를 입력하면 LinkedIn에 즉시 게시됩니다.

## 📂 프로젝트 구조

-   `main.py`: 전체 프로세스 제어 및 실행 메인 루프
-   `scraper.py`: 웹 콘텐츠 및 이미지 추출 엔진
-   `summarizer.py`: Gemini AI 기반 기술 큐레이션 요약 엔진
-   `linkedin_poster.py`: LinkedIn API 연동 (이미지 업로드 및 UGC 포스팅)
-   `auth_helper.py`: LinkedIn OAuth 2.0 인증 보조 도구

## 📝 라이선스

이 프로젝트는 MIT 라이선스를 따릅니다.
