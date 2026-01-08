# 🔒 보안 파일 관리 시스템

## 개요
Auto Poster의 보안 파일 관리 시스템은 민감한 설정 파일(서비스 계정 키, API 키 등)을 암호화하여 데이터베이스에 안전하게 저장하고 관리하는 기능을 제공합니다.

## 주요 기능

### 1. 암호화 방식
- **알고리즘**: Fernet (대칭키 암호화)
- **키 생성**: SHA256 해시 기반
- **키 프레이즈**: `SUPER_ADMIN_ID:SUPER_ADMIN_PW` 형식
  - 예: `admin@banya.ai:Admin1234!@#`

### 2. 지원 파일 타입
- **Firebase** (`serviceAccountKey.json`): Firebase/GCS 서비스 계정 키
- **YouTube** (`client_secrets.json`): YouTube Data API OAuth 클라이언트 시크릿
- **Environment** (`.env`): 환경 변수 설정 파일

### 3. 보안 수준
- ✅ 파일은 AES-128 암호화되어 DB에 저장
- ✅ 키 프레이즈 없이는 복호화 불가능
- ✅ 슈퍼 관리자만 접근 가능
- ✅ 로컬 파일 폴백 지원 (개발 환경)

## 사용 방법

### 1. 보안 파일 업로드

#### 웹 UI 사용
1. 슈퍼 관리자로 로그인
2. 좌측 메뉴에서 **"보안 파일 관리"** 클릭
3. 파일 선택 및 타입 지정
4. 키 프레이즈 입력 (형식: `ID:비밀번호`)
5. "🔐 암호화하여 업로드" 버튼 클릭

#### 첫 업로드 예시
```
파일: serviceAccountKey.json
타입: firebase
설명: Firebase 프로덕션 서비스 계정 키
키 프레이즈: admin@banya.ai:Admin1234!@#
```

### 2. 자동 로드 확인

업로드 후 애플리케이션을 재시작하면:

```bash
✅ Firebase credentials loaded from encrypted DB
✅ Firebase/GCS Clients Initialized
```

DB에 파일이 없으면 로컬 파일로 폴백:
```bash
⚠️ No encrypted credentials in DB, falling back to local file...
✅ Firebase credentials loaded from local file
```

### 3. 파일 관리

**조회**: `/api/admin/secure-files` (GET)
- 저장된 보안 파일 목록 조회
- 파일명, 타입, 설명, 업데이트 일시 확인

**삭제**: `/api/admin/secure-files/{file_id}` (DELETE)
- 더 이상 사용하지 않는 보안 파일 삭제
- 슈퍼 관리자 권한 필요

## 아키텍처

### DB 스키마 (`SecureFile`)
```python
class SecureFile(Base):
    id: Integer (Primary Key)
    file_name: String (Unique, Index)  # 예: 'serviceAccountKey.json'
    file_type: String                   # 'firebase', 'youtube', 'env'
    encrypted_content: LargeBinary      # 암호화된 파일 내용
    description: Text                   # 파일 설명
    uploaded_by: Integer                # 업로드한 관리자 User ID
    created_at: DateTime
    updated_at: DateTime
```

### 암호화 프로세스
```
[원본 파일] 
    ↓
[SHA256(키 프레이즈) → Fernet 키 생성]
    ↓
[Fernet.encrypt(파일 내용)]
    ↓
[암호화된 바이너리 → DB 저장]
```

### 복호화 프로세스
```
[DB에서 암호화된 파일 조회]
    ↓
[SHA256(키 프레이즈) → Fernet 키 재생성]
    ↓
[Fernet.decrypt(암호화된 내용)]
    ↓
[메모리에 복호화된 파일 로드]
```

## 코드 예시

### 서비스에서 암호화된 파일 사용

```python
from services.crypto_service import CryptoService

# 방법 1: 바이트로 직접 로드
decrypted_content = CryptoService.get_decrypted_file_from_db('serviceAccountKey.json')
service_account_info = json.loads(decrypted_content.decode('utf-8'))

# 방법 2: 임시 파일로 저장
temp_path = CryptoService.get_decrypted_file_path('client_secrets.json', '/tmp')
# temp_path를 파일 경로가 필요한 라이브러리에 전달
```

### 새 서비스에 통합

```python
class NewService:
    def __init__(self):
        try:
            # DB에서 암호화된 파일 로드 시도
            from services.crypto_service import CryptoService
            key_content = CryptoService.get_decrypted_file_from_db('my_api_key.json')
            self.api_key = json.loads(key_content.decode('utf-8'))['key']
            print("✅ API key loaded from encrypted DB")
        except FileNotFoundError:
            # 폴백: 로컬 파일 사용
            with open('my_api_key.json', 'r') as f:
                self.api_key = json.load(f)['key']
            print("⚠️ Using local API key file")
```

## 보안 권장 사항

### ✅ DO (권장)
1. **프로덕션 환경에서는 반드시 이 시스템 사용**
   - 모든 보안 파일을 DB에 암호화하여 저장
   - `.gitignore`에 로컬 키 파일 등록

2. **강력한 키 프레이즈 사용**
   - 최소 20자 이상
   - 대소문자, 숫자, 특수문자 조합
   - 예: `super_admin_2026@banya.ai:Str0ng!P@ssw0rd#2026`

3. **키 프레이즈 안전하게 보관**
   - 비밀번호 관리자 사용
   - 팀원과 안전한 채널로만 공유
   - 주기적으로 변경

4. **정기적인 보안 감사**
   - 업로드된 파일 목록 확인
   - 불필요한 파일 삭제
   - 접근 로그 모니터링

### ❌ DON'T (금지)
1. ❌ 키 프레이즈를 코드에 하드코딩
2. ❌ 키 프레이즈를 Git에 커밋
3. ❌ 약한 키 프레이즈 사용 (예: `admin:1234`)
4. ❌ 프로덕션 환경에서 로컬 파일 의존

## 마이그레이션 가이드

### 기존 로컬 파일 → DB 암호화 마이그레이션

#### 1단계: 로컬 파일 확인
```bash
# 현재 사용 중인 보안 파일 확인
ls -la 1_md_converter/serviceAccountKey.json
ls -la 3_youtube_poster/client_secrets.json
```

#### 2단계: 웹 UI에서 업로드
1. `/admin/secure-files` 접속
2. 각 파일을 순서대로 업로드:
   - `serviceAccountKey.json` (타입: firebase)
   - `client_secrets.json` (타입: youtube)
   - `.env` (타입: env) - 선택사항

#### 3단계: 애플리케이션 재시작
```bash
# 로그 확인: DB에서 로드되는지 체크
✅ Firebase credentials loaded from encrypted DB
```

#### 4단계: 로컬 파일 백업 및 제거
```bash
# 백업
mkdir -p ~/secure_backup
cp 1_md_converter/serviceAccountKey.json ~/secure_backup/
cp 3_youtube_poster/client_secrets.json ~/secure_backup/

# 제거 (DB 로드 확인 후)
rm 1_md_converter/serviceAccountKey.json
rm 3_youtube_poster/client_secrets.json
```

## 문제 해결

### Q1: "잘못된 키 프레이즈" 오류
**원인**: 입력한 키 프레이즈가 업로드 시와 다름

**해결**:
1. `.env` 파일에서 `SUPER_ADMIN_ID`, `SUPER_ADMIN_PW` 확인
2. 형식 확인: `ID:PW` (콜론으로 구분)
3. 공백이나 줄바꿈 없는지 확인

### Q2: "DB에 파일이 없습니다" 오류
**원인**: 해당 파일이 아직 업로드되지 않음

**해결**:
1. `/admin/secure-files`에서 파일 업로드
2. 파일명을 정확히 입력 (예: `serviceAccountKey.json`)

### Q3: 암호화 키 분실
**현상**: 키 프레이즈를 잊어버림

**해결**:
1. **복구 불가능** - Fernet은 키 없이 복구 불가
2. 백업 파일로 재업로드 필요
3. 새 서비스 계정 키 발급 권장

### Q4: 로컬 파일 폴백 사용 중
**현상**: 계속 "falling back to local file" 메시지

**원인**: DB에 파일이 없음

**해결**:
1. 로컬 파일을 `/admin/secure-files`에서 업로드
2. 애플리케이션 재시작
3. "loaded from encrypted DB" 메시지 확인

## API 레퍼런스

### 엔드포인트 목록

#### GET `/api/admin/secure-files`
보안 파일 목록 조회 (슈퍼 관리자 전용)

**응답**:
```json
[
  {
    "id": 1,
    "file_name": "serviceAccountKey.json",
    "file_type": "firebase",
    "description": "Firebase 프로덕션 키",
    "updated_at": "2026-01-09T15:30:00"
  }
]
```

#### POST `/api/admin/secure-files`
보안 파일 업로드 및 암호화 저장

**요청** (multipart/form-data):
- `file`: 업로드할 파일
- `file_type`: 'firebase' | 'youtube' | 'env'
- `description`: 파일 설명 (선택)
- `key_phrase`: 암호화 키 프레이즈

**응답**:
```json
{
  "status": "success",
  "message": "serviceAccountKey.json 파일이 저장되었습니다."
}
```

#### DELETE `/api/admin/secure-files/{file_id}`
보안 파일 삭제

**응답**:
```json
{
  "message": "serviceAccountKey.json 파일이 삭제되었습니다."
}
```

## 향후 개선 사항

- [ ] PBKDF2 키 유도 함수로 업그레이드 (현재: SHA256)
- [ ] 키 로테이션 기능 추가
- [ ] 접근 로그 및 감사 추적
- [ ] 다중 키 프레이즈 지원 (팀원별)
- [ ] YouTube `client_secrets.json` 자동 로드 구현
- [ ] 자동 백업 및 복구 기능

## 기술 스택

- **암호화**: `cryptography` (Fernet)
- **DB**: SQLite / SQLAlchemy
- **인증**: JWT (슈퍼 관리자 전용)
- **UI**: Alpine.js + Tailwind CSS

## 라이센스 및 주의사항

이 보안 시스템은 민감한 데이터를 다룹니다. 프로덕션 사용 시:
- 정기적인 보안 감사 수행
- 키 프레이즈 주기적 변경
- 접근 권한 최소화
- 백업 전략 수립

---

**📚 더 알아보기**:
- [Cryptography 문서](https://cryptography.io/)
- [Google Cloud IAM 모범 사례](https://cloud.google.com/iam/docs/best-practices-service-accounts)

