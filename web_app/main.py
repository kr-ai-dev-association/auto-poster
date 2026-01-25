from fastapi import FastAPI, Request, UploadFile, File, Form, BackgroundTasks, Depends, HTTPException, status
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, JSONResponse, FileResponse, RedirectResponse
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
import uvicorn
import os
import shutil
import asyncio
import uuid
from datetime import timedelta
from sqlalchemy.orm import Session
from pydantic import BaseModel

from services.converter_service import ConverterService
from services.linkedin_service import LinkedinService
from services.youtube_service import YouTubeService
from services.crypto_service import CryptoService
from services.pdf2mp4_service import PDF2MP4Service
from services.audio_generator_service import audio_generator
from services.content_generator_service import content_generator
from services import auth_service
from core import database, models

# DB 초기화
models.Base.metadata.create_all(bind=database.engine)

app = FastAPI(title="Auto Poster")

# 정적 파일 및 템플릿 설정
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

# 서비스 인스턴스 (startup_event에서 재초기화됨)
converter = None
linkedin = None
youtube = None
pdf2mp4 = None

# OAuth2 설정
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login")

# Pydantic 모델
class UserSignup(BaseModel):
    name: str
    email: str
    password: str

class Token(BaseModel):
    access_token: str
    token_type: str

# 의존성: DB 세션 및 수퍼 관리자 초기화
@app.on_event("startup")
async def startup_event():
    global converter, linkedin, youtube, pdf2mp4

    # 1. 환경 변수 로드 (DB 우선, 로컬 폴백)
    CryptoService.load_env_from_db()

    # 2. 서비스 인스턴스 초기화 (환경 변수 로드 후)
    converter = ConverterService()
    linkedin = LinkedinService()
    youtube = YouTubeService()
    pdf2mp4 = PDF2MP4Service()

    # 3. 수퍼 관리자 초기화
    db = database.SessionLocal()
    try:
        auth_service.init_super_admin(db)
    finally:
        db.close()

def get_current_user(token: str = Depends(oauth2_scheme), db: Session = Depends(database.get_db)):
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = auth_service.jwt.decode(token, auth_service.SECRET_KEY, algorithms=[auth_service.ALGORITHM])
        email: str = payload.get("sub")
        if email is None:
            raise credentials_exception
    except auth_service.JWTError:
        raise credentials_exception
    
    user = db.query(models.User).filter(models.User.email == email).first()
    if user is None:
        raise credentials_exception
    if not user.is_active:
        raise HTTPException(status_code=403, detail="승인 대기 중인 계정입니다.")
    return user

def get_super_admin(user: models.User = Depends(get_current_user)):
    if not user.is_super_admin:
        raise HTTPException(status_code=403, detail="권한이 없습니다.")
    return user

# --- 페이지 라우트 ---

@app.get("/favicon.ico")
async def favicon():
    """Favicon 반환"""
    favicon_path = os.path.join("static", "imgs", "ai_profile.ico")
    if os.path.exists(favicon_path):
        return FileResponse(favicon_path, media_type="image/x-icon")
    raise HTTPException(status_code=404, detail="Favicon not found")

@app.get("/", response_class=HTMLResponse)
async def read_root(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    return templates.TemplateResponse("login.html", {"request": request})

@app.get("/signup", response_class=HTMLResponse)
async def signup_page(request: Request):
    return templates.TemplateResponse("signup.html", {"request": request})

@app.get("/admin/users", response_class=HTMLResponse)
async def admin_users_page(request: Request):
    return templates.TemplateResponse("admin_users.html", {"request": request})

@app.get("/admin/secure-files", response_class=HTMLResponse)
async def admin_secure_files_page(request: Request):
    return templates.TemplateResponse("admin_secure_files.html", {"request": request})

# --- 인증 API ---

@app.post("/api/auth/signup")
async def signup(user_data: UserSignup, db: Session = Depends(database.get_db)):
    # 이메일 중복 확인
    if db.query(models.User).filter(models.User.email == user_data.email).first():
        raise HTTPException(status_code=400, detail="이미 등록된 이메일입니다.")
    
    # 비밀번호 강도 확인
    if not auth_service.validate_password_strength(user_data.password):
        raise HTTPException(status_code=400, detail="비밀번호는 영문 대소문자, 숫자, 특수문자 조합으로 8자리 이상이어야 합니다.")
    
    new_user = models.User(
        name=user_data.name,
        email=user_data.email,
        password_hash=auth_service.get_password_hash(user_data.password),
        is_active=False
    )
    db.add(new_user)
    db.commit()
    return {"message": "Signup successful, waiting for approval"}

@app.post("/api/auth/login", response_model=Token)
async def login(form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(database.get_db)):
    user = db.query(models.User).filter(models.User.email == form_data.username).first()
    if not user or not auth_service.verify_password(form_data.password, user.password_hash):
        raise HTTPException(status_code=401, detail="이메일 또는 비밀번호가 잘못되었습니다.")
    
    if not user.is_active:
        raise HTTPException(status_code=403, detail="승인 대기 중인 계정입니다. 관리자에게 문의하세요.")
    
    access_token_expires = timedelta(minutes=auth_service.ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = auth_service.create_access_token(
        data={"sub": user.email}, expires_delta=access_token_expires
    )
    return {"access_token": access_token, "token_type": "bearer"}

# --- 관리자 API ---

@app.get("/api/admin/users")
async def get_users(db: Session = Depends(database.get_db), admin: models.User = Depends(get_super_admin)):
    users = db.query(models.User).all()
    return users

@app.post("/api/admin/users/{user_id}/approve")
async def approve_user(user_id: int, db: Session = Depends(database.get_db), admin: models.User = Depends(get_super_admin)):
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="사용자를 찾을 수 없습니다.")
    user.is_active = True
    db.commit()
    return {"message": "User approved"}

@app.delete("/api/admin/users/{user_id}")
async def delete_user(user_id: int, db: Session = Depends(database.get_db), admin: models.User = Depends(get_super_admin)):
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="사용자를 찾을 수 없습니다.")
    if user.is_super_admin:
        raise HTTPException(status_code=400, detail="수퍼 관리자는 삭제할 수 없습니다.")
    db.delete(user)
    db.commit()
    return {"message": "User deleted"}

# --- 보안 파일 관리 API (슈퍼 관리자 전용) ---

@app.get("/api/admin/secure-files")
async def list_secure_files(db: Session = Depends(database.get_db), admin: models.User = Depends(get_super_admin)):
    """암호화된 보안 파일 목록 조회"""
    files = db.query(models.SecureFile).all()
    return [{
        "id": f.id,
        "file_name": f.file_name,
        "file_type": f.file_type,
        "description": f.description,
        "updated_at": f.updated_at.isoformat() if f.updated_at else None
    } for f in files]

@app.post("/api/admin/secure-files")
async def upload_secure_file(
    file: UploadFile = File(...),
    file_type: str = Form(...),
    description: str = Form(""),
    key_phrase: str = Form(...),
    db: Session = Depends(database.get_db),
    admin: models.User = Depends(get_super_admin)
):
    """
    보안 파일 업로드 및 암호화 저장
    file_type: 'firebase', 'youtube', 'env'
    """
    try:
        # 파일 읽기
        file_content = await file.read()
        
        # 암호화
        encrypted_content = CryptoService.encrypt_file(file_content, key_phrase)
        
        # DB에 저장 (기존 파일이 있으면 업데이트)
        existing = db.query(models.SecureFile).filter(
            models.SecureFile.file_name == file.filename
        ).first()
        
        if existing:
            existing.encrypted_content = encrypted_content
            existing.file_type = file_type
            existing.description = description
            existing.uploaded_by = admin.id
            db.commit()
            return {"status": "success", "message": f"{file.filename} 파일이 업데이트되었습니다."}
        else:
            new_file = models.SecureFile(
                file_name=file.filename,
                file_type=file_type,
                encrypted_content=encrypted_content,
                description=description,
                uploaded_by=admin.id
            )
            db.add(new_file)
            db.commit()
            return {"status": "success", "message": f"{file.filename} 파일이 저장되었습니다."}
    
    except Exception as e:
        return JSONResponse(status_code=500, content={"status": "error", "message": str(e)})

@app.get("/api/admin/secure-files/{file_id}/decrypt")
async def decrypt_secure_file(
    file_id: int,
    key_phrase: str,
    db: Session = Depends(database.get_db),
    admin: models.User = Depends(get_super_admin)
):
    """
    보안 파일 복호화 및 다운로드 (테스트용)
    """
    secure_file = db.query(models.SecureFile).filter(models.SecureFile.id == file_id).first()
    if not secure_file:
        raise HTTPException(status_code=404, detail="파일을 찾을 수 없습니다.")
    
    try:
        decrypted_content = CryptoService.decrypt_file(secure_file.encrypted_content, key_phrase)
        return FileResponse(
            path=None,
            content=decrypted_content,
            media_type="application/octet-stream",
            filename=secure_file.file_name
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"복호화 실패: 잘못된 키 프레이즈이거나 파일이 손상되었습니다. ({str(e)})")

@app.delete("/api/admin/secure-files/{file_id}")
async def delete_secure_file(
    file_id: int,
    db: Session = Depends(database.get_db),
    admin: models.User = Depends(get_super_admin)
):
    """보안 파일 삭제"""
    secure_file = db.query(models.SecureFile).filter(models.SecureFile.id == file_id).first()
    if not secure_file:
        raise HTTPException(status_code=404, detail="파일을 찾을 수 없습니다.")
    
    db.delete(secure_file)
    db.commit()
    return {"message": f"{secure_file.file_name} 파일이 삭제되었습니다."}

# --- 기존 API (보안 적용) ---

@app.post("/api/upload")
async def process_content(
    file: UploadFile = File(None),
    content: str = Form(None),
    title: str = Form(None),
    image_mode: str = Form("auto"),
    category: str = Form("tech"),
    user: models.User = Depends(get_current_user)
):
    """
    파일 업로드 또는 텍스트 직접 입력을 처리합니다.
    image_mode: 'auto' (자동 생성) 또는 'manual' (수동 삽입)
    category: 'tech' (Tech Wiki) 또는 'news' (Banya Official News)
    """
    if not file and not content:
        return JSONResponse(status_code=400, content={"message": "No file or content provided"})

    # image_mode 검증
    if image_mode not in ['auto', 'manual']:
        image_mode = 'auto'
    
    # category 검증
    if category not in ['tech', 'news']:
        category = 'tech'

    # 1. 파일 처리
    if file:
        filename = file.filename
        content_bytes = await file.read()
        markdown_text = content_bytes.decode("utf-8")
    
    # 2. 텍스트 직접 입력 처리
    else:
        if not title:
            return JSONResponse(status_code=400, content={"message": "Title is required for text input"})
        filename = f"{title}.md"
        markdown_text = content

    # 3. 비동기 변환 작업 시작
    if not converter:
        return JSONResponse(status_code=503, content={"status": "error", "message": "Service not initialized. Please wait a moment and try again."})
    
    try:
        result = await converter.process_markdown(markdown_text, filename, image_mode=image_mode, category=category)
        return JSONResponse(content=result)
    except Exception as e:
        return JSONResponse(status_code=500, content={"status": "error", "message": str(e)})

@app.post("/api/share/linkedin")
async def share_linkedin(
    wiki_id: str = Form(...),
    wiki_url: str = Form(...),
    lang: str = Form("ko"),
    user: models.User = Depends(get_current_user)
):
    """
    배포된 위키를 LinkedIn에 공유합니다.
    """
    if not linkedin:
        return JSONResponse(status_code=503, content={"status": "error", "message": "Service not initialized. Please wait a moment and try again."})
    
    try:
        result = await linkedin.share_wiki(wiki_id, wiki_url, lang)
        return JSONResponse(content=result)
    except Exception as e:
        return JSONResponse(status_code=500, content={"status": "error", "message": str(e)})

# --- Youtube Poster Endpoints ---

@app.post("/api/youtube/metadata")
async def generate_youtube_metadata(
    pdf: UploadFile = File(None),
    pdf_id: str = Form(None),
    plan_id: str = Form(None),  # 기획안 ID 추가
    category: str = Form(...),
    lang: str = Form("ko"),
    user: models.User = Depends(get_current_user)
):
    """PDF 분석 또는 기획 대본을 통해 유튜브 메타데이터를 생성합니다.
    pdf 파일을 직접 업로드하거나, pdf_id 또는 plan_id를 참조할 수 있습니다.
    """
    if not youtube:
        return JSONResponse(status_code=503, content={"status": "error", "message": "Service not initialized. Please wait a moment and try again."})

    try:
        from web_app.services.youtube_service import YouTubeMetadataValidator
        
        content = None
        text_content = None

        # 1. 기획안(plan_id)이 있는 경우: 대본 텍스트 사용 (PDF 업로드 불필요)
        if plan_id:
            plan_path = os.path.join(content_generator.output_dir, f"plan_{plan_id}.json")
            if os.path.exists(plan_path):
                import json
                with open(plan_path, 'r', encoding='utf-8') as f:
                    plan = json.load(f)
                
                # 대본 텍스트 구성
                title = plan.get('title', 'Untitled')
                text_content = f"Title: {title}\n\n"
                
                # 타겟 독자 등 메타 정보 추가
                if 'target_audience' in plan:
                     text_content += f"Target Audience: {plan['target_audience']}\n"
                if 'video_style' in plan:
                     text_content += f"Style: {plan['video_style']}\n\n"

                # 슬라이드별 나레이션 합치기
                for slide in plan.get('slides', []):
                     num = slide.get('slide_number', 0)
                     narration = slide.get('narration', '')
                     content_text = slide.get('content', '')
                     text_content += f"[Slide {num}]\nContent: {content_text}\nNarration: {narration}\n\n"
                
                print(f"📝 기획안({plan_id})에서 대본 추출 완료 (길이: {len(text_content)})")
            else:
                return JSONResponse(status_code=404, content={"status": "error", "message": "Plan not found"})

        # 2. PDF 내용 가져오기 (기획안이 없는 경우)
        elif pdf_id and pdf2mp4:
            # Gen Video에서 선택한 PDF 사용
            pdf_path = pdf2mp4.get_pdf_path(pdf_id)
            if not pdf_path or not os.path.exists(pdf_path):
                return JSONResponse(status_code=404, content={"status": "error", "message": "Selected PDF not found"})
            with open(pdf_path, 'rb') as f:
                content = f.read()
        elif pdf:
            # 직접 업로드한 PDF 사용
            content = await pdf.read()
        else:
            return JSONResponse(status_code=400, content={"status": "error", "message": "PDF file, pdf_id, or plan_id is required"})

        # 메타데이터 생성 호출 (text_content가 있으면 우선 사용)
        metadata = await youtube.generate_metadata(content, category, lang, text_content=text_content)

        # 검증 결과 포함
        is_valid, errors, warnings = YouTubeMetadataValidator.validate(metadata)

        return JSONResponse(content={
            "status": "success",
            "metadata": metadata,
            "validation": {
                "is_valid": is_valid,
                "errors": errors,
                "warnings": warnings
            }
        })
    except Exception as e:
        return JSONResponse(status_code=500, content={"status": "error", "message": str(e)})

class MetadataValidationRequest(BaseModel):
    title: str = ""
    description: str = ""
    tags: list = []

@app.post("/api/youtube/metadata/validate")
async def validate_youtube_metadata(
    metadata: MetadataValidationRequest,
    user: models.User = Depends(get_current_user)
):
    """YouTube 메타데이터를 검증합니다."""
    try:
        from web_app.services.youtube_service import YouTubeMetadataValidator
        
        metadata_dict = {
            "title": metadata.title,
            "description": metadata.description,
            "tags": metadata.tags
        }
        
        is_valid, errors, warnings = YouTubeMetadataValidator.validate(metadata_dict)
        
        return JSONResponse(content={
            "status": "success",
            "validation": {
                "is_valid": is_valid,
                "errors": errors,
                "warnings": warnings
            }
        })
    except Exception as e:
        return JSONResponse(status_code=500, content={"status": "error", "message": str(e)})

@app.post("/api/youtube/upload")
async def youtube_upload(
    background_tasks: BackgroundTasks,
    video: UploadFile = File(...),
    pdf: UploadFile = File(None),
    pdf_id: str = Form(None),
    category: str = Form(...),
    lang: str = Form("ko"),
    use_thumbnail: bool = Form(True),
    user: models.User = Depends(get_current_user)
):
    """영상을 처리하고 유튜브에 업로드합니다 (비동기)."""
    if not youtube:
        return JSONResponse(status_code=503, content={"status": "error", "message": "Service not initialized. Please wait a moment and try again."})

    try:
        video_content = await video.read()
        filename = video.filename

        # PDF 내용 가져오기 (업로드 또는 Gen Video에서 선택)
        if pdf_id and pdf2mp4:
            # Gen Video에서 선택한 PDF 사용
            pdf_path = pdf2mp4.get_pdf_path(pdf_id)
            if not pdf_path or not os.path.exists(pdf_path):
                return JSONResponse(status_code=404, content={"status": "error", "message": "Selected PDF not found"})
            with open(pdf_path, 'rb') as f:
                pdf_content = f.read()
        elif pdf:
            # 직접 업로드한 PDF 사용
            pdf_content = await pdf.read()
        else:
            return JSONResponse(status_code=400, content={"status": "error", "message": "PDF file or pdf_id is required"})

        # 업로드 ID 생성 및 초기 상태 설정
        upload_id = str(uuid.uuid4())
        YouTubeService.update_upload_progress(upload_id, 'init', 0, '업로드 요청 접수됨')
        
        # 백그라운드 작업 시작
        background_tasks.add_task(
            youtube.process_and_upload,
            video_content, filename, pdf_content, category, lang, use_thumbnail, upload_id
        )
        
        return JSONResponse(content={"status": "processing", "upload_id": upload_id})
    except Exception as e:
        return JSONResponse(status_code=500, content={"status": "error", "message": str(e)})

@app.get("/api/youtube/status/{upload_id}")
async def get_youtube_upload_status(upload_id: str, user: models.User = Depends(get_current_user)):
    """유튜브 업로드 상태를 조회합니다."""
    progress = YouTubeService.get_upload_progress(upload_id)
    if not progress:
        return JSONResponse(status_code=404, content={"status": "error", "message": "Upload task not found"})
    
    return JSONResponse(content=progress)

@app.post("/api/youtube/share/linkedin")
async def youtube_share_linkedin(
    video_id: str = Form(...),
    video_url: str = Form(...),
    lang: str = Form("ko"),
    user: models.User = Depends(get_current_user)
):
    """유튜브 영상을 링크드인에 공유합니다."""
    if not youtube:
        return JSONResponse(status_code=503, content={"status": "error", "message": "Service not initialized. Please wait a moment and try again."})
    
    try:
        result = await youtube.share_to_linkedin(video_id, video_url, lang)
        return JSONResponse(content=result)
    except Exception as e:
        return JSONResponse(status_code=500, content={"status": "error", "message": str(e)})

@app.get("/api/auth/me")
async def get_me(user: models.User = Depends(get_current_user)):
    return {
        "id": user.id,
        "name": user.name,
        "email": user.email,
        "is_super_admin": user.is_super_admin
    }

# --- Gen Video (PDF to MP4) Endpoints ---

@app.get("/api/genvideo/logo/{category}")
async def get_genvideo_logo(category: str, token: str = None, db: Session = Depends(database.get_db)):
    """카테고리별 현재 로고 이미지를 반환합니다."""
    if not token:
        raise HTTPException(status_code=401, detail="Token required")

    try:
        user = get_current_user(token, db)
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid token")

    if not youtube:
        return JSONResponse(status_code=503, content={"status": "error", "message": "Service not initialized"})

    logo_path = youtube.get_logo_path(category)
    if logo_path and os.path.exists(logo_path):
        return FileResponse(logo_path)
    return JSONResponse(status_code=404, content={"message": "Logo not found"})

@app.post("/api/genvideo/logo/upload")
async def upload_genvideo_logo(
    logo: UploadFile = File(...),
    category: str = Form(...),
    user: models.User = Depends(get_current_user)
):
    """새로운 로고 이미지를 업로드합니다."""
    if not youtube:
        return JSONResponse(status_code=503, content={"status": "error", "message": "Service not initialized"})

    try:
        content = await logo.read()

        # 로고 저장 경로
        v_dir = os.path.join(youtube.base_v_dir, category)
        if not os.path.exists(v_dir):
            os.makedirs(v_dir, exist_ok=True)

        # 기존 로고 삭제
        existing_logos = [f for f in os.listdir(v_dir) if f.lower().endswith('.png') and 'logo' in f.lower()]
        for f in existing_logos:
            os.remove(os.path.join(v_dir, f))

        # 새 로고 저장
        save_path = os.path.join(v_dir, f"logo_{logo.filename}")
        with open(save_path, "wb") as f:
            f.write(content)

        return JSONResponse(content={"status": "success", "message": "Logo uploaded successfully"})
    except Exception as e:
        return JSONResponse(status_code=500, content={"status": "error", "message": str(e)})

@app.get("/api/genvideo/categories")
async def get_genvideo_categories(user: models.User = Depends(get_current_user)):
    """사용 가능한 카테고리 목록을 반환합니다."""
    if not youtube:
        return JSONResponse(status_code=503, content={"status": "error", "message": "Service not initialized"})

    categories = youtube.get_categories()
    return JSONResponse(content={"status": "success", "categories": categories})

@app.post("/api/genvideo/convert")
async def convert_pdf_to_video(
    pdf: UploadFile = File(...),
    audio: UploadFile = File(None),
    mode: str = Form("basic"),
    page_duration: float = Form(5.0),
    transition: str = Form("fade"),
    transition_duration: float = Form(0.5),
    resolution: str = Form("1920x1080"),
    fps: int = Form(30),
    auto_duration: bool = Form(False),
    category: str = Form(None),
    ocr_lang: str = Form("korean"),
    gen_subtitles: bool = Form(False),
    subtitle_lang: str = Form("ko"),
    subtitle_level: int = Form(1),
    user: models.User = Depends(get_current_user)
):
    """PDF를 MP4 영상으로 변환합니다.

    subtitle_level:
        1 - 키워드 중심 (간결)
        2 - 요약 중심 (균형)
        3 - 전체 자막 (상세)
    """
    if not pdf2mp4:
        return JSONResponse(
            status_code=503,
            content={"status": "error", "message": "Service not initialized"}
        )

    try:
        pdf_content = await pdf.read()
        audio_content = await audio.read() if audio else None
        audio_filename = audio.filename if audio else None

        # 해상도 파싱
        width, height = map(int, resolution.split('x'))

        # 로고 경로 가져오기
        logo_path = None
        if category:
            logo_path = youtube.get_logo_path(category)
        else:
            # 카테고리가 지정되지 않으면 첫 번째 카테고리의 로고 사용
            categories = youtube.get_categories()
            if categories:
                logo_path = youtube.get_logo_path(categories[0])

        import asyncio

        if mode == "smart":
            result = await asyncio.to_thread(
                pdf2mp4.convert_smart_sync,
                pdf_content=pdf_content,
                filename=pdf.filename,
                audio_content=audio_content,
                audio_filename=audio_filename,
                transition=transition,
                transition_duration=transition_duration,
                width=width,
                height=height,
                fps=fps,
                logo_path=logo_path,
                ocr_lang=ocr_lang,
                gen_subtitles=gen_subtitles,
                subtitle_lang=subtitle_lang,
                subtitle_level=subtitle_level,
                youtube_service=youtube,
                category=category or '',
                created_by=user.email if user else ''
            )
        else:
            result = await asyncio.to_thread(
                pdf2mp4.convert_basic_sync,
                pdf_content=pdf_content,
                filename=pdf.filename,
                audio_content=audio_content,
                audio_filename=audio_filename,
                page_duration=page_duration,
                transition=transition,
                transition_duration=transition_duration,
                width=width,
                height=height,
                fps=fps,
                auto_duration=auto_duration,
                logo_path=logo_path,
                ocr_lang=ocr_lang,
                gen_subtitles=gen_subtitles,
                subtitle_lang=subtitle_lang,
                subtitle_level=subtitle_level,
                youtube_service=youtube,
                category=category or '',
                created_by=user.email if user else ''
            )

        return JSONResponse(content=result)

    except Exception as e:
        return JSONResponse(
            status_code=500,
            content={"status": "error", "message": str(e)}
        )

@app.get("/api/genvideo/progress/{video_id}")
async def get_conversion_progress(
    video_id: str,
    user: models.User = Depends(get_current_user)
):
    """변환 진행률을 조회합니다."""
    from services.pdf2mp4_service import PDF2MP4Service
    progress = PDF2MP4Service.get_progress(video_id)
    if progress:
        return JSONResponse(content={"status": "success", **progress})
    return JSONResponse(content={"status": "not_found", "message": "No progress found for this video_id"})

@app.get("/api/genvideo/progress")
async def get_all_conversion_progress(
    user: models.User = Depends(get_current_user)
):
    """진행 중인 모든 변환의 진행률을 조회합니다."""
    from services.pdf2mp4_service import PDF2MP4Service
    all_progress = PDF2MP4Service._progress_store
    if all_progress:
        return JSONResponse(content={"status": "success", "conversions": list(all_progress.values())})
    return JSONResponse(content={"status": "success", "conversions": []})

@app.post("/api/genvideo/cancel/{video_id}")
async def cancel_conversion(
    video_id: str,
    user: models.User = Depends(get_current_user)
):
    """진행 중인 변환을 취소합니다."""
    if not pdf2mp4:
        return JSONResponse(
            status_code=503,
            content={"status": "error", "message": "Service not initialized"}
        )

    result = pdf2mp4.cancel_conversion(video_id)
    return JSONResponse(content=result)

@app.get("/api/genvideo/list")
async def list_generated_videos(
    user: models.User = Depends(get_current_user)
):
    """생성된 영상 목록을 조회합니다."""
    if not pdf2mp4:
        return JSONResponse(
            status_code=503,
            content={"status": "error", "message": "Service not initialized"}
        )

    videos = pdf2mp4.get_video_list()
    return JSONResponse(content={"status": "success", "videos": videos})


@app.get("/api/genvideo/manage/list")
async def list_videos_for_management(
    user: models.User = Depends(get_current_user),
    db: Session = Depends(database.get_db)
):
    """영상 관리 페이지용 상세 목록을 조회합니다."""
    if not pdf2mp4:
        return JSONResponse(
            status_code=503,
            content={"status": "error", "message": "Service not initialized"}
        )

    videos = pdf2mp4.get_video_list()

    # 각 영상에 추가 정보 추가
    enhanced_videos = []
    for video in videos:
        video_id = video.get('id', '')

        # 기본 단계 판단
        # 기본 단계 판단
        stage = video.get('stage', 'generated')

        # 이미 'posted' 상태라면 유지 (메타데이터에서 읽어옴)
        if stage != 'posted':
            # 재변환된 영상인지 확인 (메타에 reencoded 플래그가 있거나 파일명에 _edited_ 포함)
            if video.get('reencoded') or '_edited_' in video.get('filename', ''):
                stage = 'reencoded'
            else:
                # 타이밍 파일 존재 여부로 'timed' 단계 판단
                timing_file = os.path.join(pdf2mp4.output_dir, f"{video_id}_timing.json")
                if os.path.exists(timing_file):
                    try:
                        import json
                        with open(timing_file, 'r') as f:
                            timing_data = json.load(f)
                            # 타이밍이 수정되었는지 확인
                            if timing_data.get('edited'):
                                stage = 'timed'
                    except:
                        pass

        enhanced_video = {
            **video,
            'stage': stage,
            'category': video.get('category', ''),
            'ocr_lang': video.get('ocr_lang', ''),
            'created_by': video.get('created_by', user.email if user else ''),
            'pdf_name': video.get('pdf_name', ''),
        }
        enhanced_videos.append(enhanced_video)

    # 생성일 기준 내림차순 정렬
    enhanced_videos.sort(key=lambda x: x.get('created_at', ''), reverse=True)

    return JSONResponse(content={"status": "success", "videos": enhanced_videos})


@app.get("/api/genvideo/info")
async def get_genvideo_info(
    user: models.User = Depends(get_current_user)
):
    """Gen Video 서비스 정보를 조회합니다."""
    if not pdf2mp4:
        return JSONResponse(
            status_code=503,
            content={"status": "error", "message": "Service not initialized"}
        )

    return JSONResponse(content={
        "status": "success",
        "transitions": pdf2mp4.get_transitions(),
        "smart_mode_available": pdf2mp4.is_smart_mode_available()
    })

@app.get("/api/genvideo/download/{video_id}")
async def download_generated_video(
    video_id: str,
    token: str = None,
    db: Session = Depends(database.get_db)
):
    """생성된 영상을 다운로드합니다. (쿼리 파라미터 토큰 지원)"""
    # 토큰 검증
    if not token:
        raise HTTPException(status_code=401, detail="Token required")

    try:
        user = get_current_user(token, db)
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid token")

    if not pdf2mp4:
        return JSONResponse(
            status_code=503,
            content={"status": "error", "message": "Service not initialized"}
        )

    video_path = pdf2mp4.get_video_path(video_id)
    if video_path and os.path.exists(video_path):
        return FileResponse(
            video_path,
            media_type="video/mp4",
            filename=os.path.basename(video_path)
        )

    return JSONResponse(
        status_code=404,
        content={"status": "error", "message": "Video not found"}
    )

@app.delete("/api/genvideo/{video_id}")
async def delete_generated_video(
    video_id: str,
    user: models.User = Depends(get_current_user)
):
    """생성된 영상을 삭제합니다."""
    if not pdf2mp4:
        return JSONResponse(
            status_code=503,
            content={"status": "error", "message": "Service not initialized"}
        )

    if pdf2mp4.delete_video(video_id):
        return JSONResponse(content={"status": "success", "message": "Video deleted"})

    return JSONResponse(
        status_code=404,
        content={"status": "error", "message": "Video not found"}
    )

# --- Gen Video PDF Endpoints ---

@app.get("/api/genvideo/pdfs")
async def list_generated_pdfs(
    user: models.User = Depends(get_current_user)
):
    """Gen Video에서 사용된 PDF 목록을 조회합니다."""
    if not pdf2mp4:
        return JSONResponse(
            status_code=503,
            content={"status": "error", "message": "Service not initialized"}
        )

    pdfs = pdf2mp4.get_pdf_list()
    return JSONResponse(content={"status": "success", "pdfs": pdfs})

@app.get("/api/genvideo/pdf/{pdf_id}")
async def get_generated_pdf(
    pdf_id: str,
    token: str = None,
    db: Session = Depends(database.get_db)
):
    """저장된 PDF 파일 내용을 반환합니다. (다운로드 또는 메타데이터 생성용)"""
    # 토큰 검증
    if not token:
        raise HTTPException(status_code=401, detail="Token required")

    try:
        user = get_current_user(token, db)
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid token")

    if not pdf2mp4:
        return JSONResponse(
            status_code=503,
            content={"status": "error", "message": "Service not initialized"}
        )

    pdf_path = pdf2mp4.get_pdf_path(pdf_id)
    if pdf_path and os.path.exists(pdf_path):
        return FileResponse(
            pdf_path,
            media_type="application/pdf",
            filename=os.path.basename(pdf_path)
        )

    return JSONResponse(
        status_code=404,
        content={"status": "error", "message": "PDF not found"}
    )

@app.delete("/api/genvideo/pdf/{pdf_id}")
async def delete_generated_pdf(pdf_id: str, user: models.User = Depends(get_current_user)):
    """저장된 PDF 파일을 삭제합니다."""
    if not pdf2mp4:
        return JSONResponse(
            status_code=503,
            content={"status": "error", "message": "Service not initialized"}
        )

    pdf_path = pdf2mp4.get_pdf_path(pdf_id)
    if pdf_path and os.path.exists(pdf_path):
        try:
            os.remove(pdf_path)
        except Exception as e:
            return JSONResponse(
                status_code=500,
                content={"status": "error", "message": str(e)}
            )

    # 파일이 없어도 성공으로 처리 (이미 삭제된 것으로 간주)
    return JSONResponse(content={"status": "success", "message": "PDF deleted"})

@app.get("/api/genvideo/timing/{video_id}")
async def get_video_timing(
    video_id: str,
    db: Session = Depends(database.get_db),
    user: models.User = Depends(get_current_user)
):
    """영상의 타이밍 정보를 반환합니다 (가벼운 데이터만)."""
    import json
    from pdf2image import convert_from_bytes

    if not pdf2mp4:
        return JSONResponse(
            status_code=503,
            content={"status": "error", "message": "Service not initialized"}
        )

    # 영상 정보 가져오기
    video_info = pdf2mp4.get_video_info(video_id)
    if not video_info:
        return JSONResponse(
            status_code=404,
            content={"status": "error", "message": "Video not found"}
        )

    # 타이밍 파일 경로
    video_dir = pdf2mp4.output_dir
    timing_file = os.path.join(video_dir, f"{video_id}_timing.json")

    timings = []
    page_texts = []
    transcript_segments = []
    duration = 0
    num_slides = 0

    # 타이밍 파일 로드
    if os.path.exists(timing_file):
        try:
            with open(timing_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
                timings = data.get('timings', [])
                page_texts = data.get('page_texts', [])
                transcript_segments = data.get('transcript_segments', [])
                num_slides = len(timings)
                # 타이밍에서 duration 계산
                if timings:
                    last_timing = timings[-1]
                    duration = last_timing.get('start', 0) + last_timing.get('duration', 0)
        except Exception as e:
            print(f"Error loading timing file: {e}")

    # 타이밍이 없으면 PDF에서 페이지 수만 확인
    if not timings:
        pdf_path = pdf2mp4.get_pdf_path(video_id)
        if pdf_path and os.path.exists(pdf_path):
            try:
                with open(pdf_path, 'rb') as f:
                    pdf_content = f.read()
                images = convert_from_bytes(pdf_content, dpi=36)  # 매우 저해상도로 페이지 수만 확인
                num_slides = len(images)
                # 기본 균등 분배
                if duration > 0 and num_slides > 0:
                    page_duration = duration / num_slides
                    timings = [
                        {'start': i * page_duration, 'duration': page_duration}
                        for i in range(num_slides)
                    ]
            except Exception as e:
                print(f"Error counting PDF pages: {e}")

    return JSONResponse(content={
        "status": "success",
        "timings": timings,
        "pageTexts": page_texts,
        "transcriptSegments": transcript_segments,
        "numSlides": num_slides,
        "duration": duration
    })


@app.get("/api/genvideo/timing/{video_id}/slide/{slide_index}")
async def get_slide_image(
    video_id: str,
    slide_index: int,
    db: Session = Depends(database.get_db),
    user: models.User = Depends(get_current_user)
):
    """특정 슬라이드의 이미지와 OCR 텍스트를 반환합니다 (로고 합성 포함)."""
    import json
    from pdf2image import convert_from_bytes
    import base64
    from io import BytesIO
    from PIL import Image
    import numpy as np

    if not pdf2mp4:
        return JSONResponse(
            status_code=503,
            content={"status": "error", "message": "Service not initialized"}
        )

    pdf_path = pdf2mp4.get_pdf_path(video_id)
    if not pdf_path or not os.path.exists(pdf_path):
        return JSONResponse(
            status_code=404,
            content={"status": "error", "message": "PDF not found"}
        )

    try:
        with open(pdf_path, 'rb') as f:
            pdf_content = f.read()

        # 특정 페이지만 변환 (first_page와 last_page는 1-based index)
        images = convert_from_bytes(
            pdf_content,
            dpi=100,
            first_page=slide_index + 1,
            last_page=slide_index + 1
        )

        if not images:
            return JSONResponse(
                status_code=404,
                content={"status": "error", "message": "Slide not found"}
            )

        img = images[0]

        # 메타 파일에서 카테고리 가져와서 로고 경로 결정
        logo_path = None
        video_info = pdf2mp4.get_video_info(video_id)
        category = video_info.get('category', '') if video_info else ''
        if category:
            logo_path = youtube.get_logo_path(category)
        if not logo_path:
            categories = youtube.get_categories()
            if categories:
                logo_path = youtube.get_logo_path(categories[0])

        # 로고 합성하여 리사이즈 (영상과 동일한 방식)
        logo_img = None
        if logo_path and os.path.exists(logo_path):
            logo_img = Image.open(logo_path).convert('RGBA')

        # _resize_image와 유사한 로직으로 로고 합성
        width, height = 800, 600  # 미리보기 크기
        orig_width, orig_height = img.size
        ratio = min(width / orig_width, height / orig_height)
        new_width = int(orig_width * ratio)
        new_height = int(orig_height * ratio)

        img_resized = img.resize((new_width, new_height), Image.Resampling.LANCZOS)
        background = Image.new('RGB', (width, height), (0, 0, 0))
        offset_x = (width - new_width) // 2
        offset_y = (height - new_height) // 2
        background.paste(img_resized, (offset_x, offset_y))

        # 로고 합성
        if logo_img is not None:
            logo_target_width = int(new_width * 0.10)
            if logo_target_width > 0:
                logo_ratio = logo_target_width / logo_img.width
                logo_new_height = int(logo_img.height * logo_ratio)
                logo_resized = logo_img.resize((logo_target_width, logo_new_height), Image.Resampling.LANCZOS)
                logo_x = width - logo_target_width
                logo_y = height - logo_new_height
                if logo_resized.mode == 'RGBA':
                    background.paste(logo_resized, (logo_x, logo_y), logo_resized)
                else:
                    background.paste(logo_resized, (logo_x, logo_y))

        # 이미지를 base64로 인코딩
        buffered = BytesIO()
        background.save(buffered, format="PNG", optimize=True)
        img_str = base64.b64encode(buffered.getvalue()).decode()

        # OCR 텍스트 (캐시된 타이밍 파일에서 가져오거나 간단한 텍스트 추출)
        ocr_text = ""
        timing_file = os.path.join(pdf2mp4.output_dir, f"{video_id}_timing.json")
        if os.path.exists(timing_file):
            try:
                with open(timing_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    texts = data.get('page_texts', [])
                    if slide_index < len(texts):
                        ocr_text = texts[slide_index]
            except:
                pass

        # 캐시된 텍스트가 없으면 PyPDF2로 간단히 추출
        if not ocr_text:
            page_texts = pdf2mp4._extract_pdf_page_texts(pdf_content)
            if slide_index < len(page_texts):
                ocr_text = page_texts[slide_index]

        return JSONResponse(content={
            "status": "success",
            "index": slide_index,
            "imageUrl": f'data:image/png;base64,{img_str}',
            "ocrText": ocr_text
        })

    except Exception as e:
        print(f"Error extracting slide {slide_index}: {e}")
        return JSONResponse(
            status_code=500,
            content={"status": "error", "message": str(e)}
        )

@app.post("/api/genvideo/timing/{video_id}")
async def save_video_timing(
    video_id: str,
    request: Request,
    user: models.User = Depends(get_current_user)
):
    """영상의 타이밍 정보를 저장합니다."""
    import json

    if not pdf2mp4:
        return JSONResponse(
            status_code=503,
            content={"status": "error", "message": "Service not initialized"}
        )

    try:
        data = await request.json()
        timings = data.get('timings', [])

        # 기존 타이밍 파일에서 page_texts 가져오기
        video_dir = pdf2mp4.output_dir
        timing_file = os.path.join(video_dir, f"{video_id}_timing.json")

        page_texts = []
        if os.path.exists(timing_file):
            try:
                with open(timing_file, 'r', encoding='utf-8') as f:
                    existing_data = json.load(f)
                    page_texts = existing_data.get('page_texts', [])
            except:
                pass

        # 타이밍 파일 저장 (page_texts 유지)
        timing_data = {
            'timings': timings,
            'page_texts': page_texts
        }
        with open(timing_file, 'w', encoding='utf-8') as f:
            json.dump(timing_data, f, ensure_ascii=False, indent=2)

        return JSONResponse(content={"status": "success", "message": "Timing saved"})
    except Exception as e:
        return JSONResponse(
            status_code=500,
            content={"status": "error", "message": str(e)}
        )


@app.post("/api/genvideo/reencode/{video_id}")
async def reencode_video(
    video_id: str,
    request: Request,
    background_tasks: BackgroundTasks,
    user: models.User = Depends(get_current_user)
):
    """편집된 타이밍으로 영상을 재변환합니다 (비동기 방식)."""
    import json
    import uuid
    from pdf2image import convert_from_bytes

    if not pdf2mp4:
        return JSONResponse(
            status_code=503,
            content={"status": "error", "message": "Service not initialized"}
        )

    try:
        data = await request.json()
        timings = data.get('timings', [])
        async_mode = data.get('async', True)  # 기본적으로 비동기 모드

        if not timings:
            return JSONResponse(
                status_code=400,
                content={"status": "error", "message": "No timings provided"}
            )

        # 기존 영상 정보 가져오기
        video_info = pdf2mp4.get_video_info(video_id)
        if not video_info:
            return JSONResponse(
                status_code=404,
                content={"status": "error", "message": "Video not found"}
            )

        # PDF 파일 경로
        pdf_path = pdf2mp4.get_pdf_path(video_id)
        if not pdf_path or not os.path.exists(pdf_path):
            return JSONResponse(
                status_code=404,
                content={"status": "error", "message": "PDF not found for this video"}
            )

        # 오디오 파일 경로 (영상에서 추출하거나 기존 오디오 사용)
        video_path = video_info.get('file_path')

        # 메타 파일에서 카테고리 가져와서 로고 경로 결정
        logo_path = None
        category = video_info.get('category', '')
        if category:
            logo_path = youtube.get_logo_path(category)
        if not logo_path:
            # 카테고리가 없으면 첫 번째 카테고리의 로고 사용
            categories = youtube.get_categories()
            if categories:
                logo_path = youtube.get_logo_path(categories[0])

        # 새 reencode_id 생성 (진행률 추적용)
        reencode_id = str(uuid.uuid4())[:8]

        # 진행률 초기화 (백그라운드 태스크 시작 전에 미리 설정)
        from services.pdf2mp4_service import PDF2MP4Service
        PDF2MP4Service.update_progress(reencode_id, 'init', 0, '🔄 재변환 준비 중...', None)

        if async_mode:
            # 비동기 모드: 즉시 reencode_id 반환하고 백그라운드에서 처리
            import asyncio

            async def run_reencode():
                result = await pdf2mp4.reencode_with_timings(
                    video_id=video_id,
                    pdf_path=pdf_path,
                    video_path=video_path,
                    timings=timings,
                    logo_path=logo_path,
                    reencode_id=reencode_id  # 진행률 추적용 ID 전달
                )
                # 완료 시 결과를 진행률 저장소에 저장 (이미 reencode_with_timings에서 처리됨)

            # 백그라운드에서 실행
            asyncio.create_task(run_reencode())

            return JSONResponse(content={
                "status": "started",
                "message": "재변환이 시작되었습니다",
                "reencode_id": reencode_id
            })
        else:
            # 동기 모드: 완료까지 대기
            result = await pdf2mp4.reencode_with_timings(
                video_id=video_id,
                pdf_path=pdf_path,
                video_path=video_path,
                timings=timings,
                logo_path=logo_path,
                reencode_id=reencode_id
            )
            return JSONResponse(content=result)

    except Exception as e:
        print(f"Error re-encoding video: {e}")
        return JSONResponse(
            status_code=500,
            content={"status": "error", "message": str(e)}
        )


@app.post("/api/genvideo/linkedin-post")
async def linkedin_post_from_genvideo(
    video_id: str = Form(...),
    category: str = Form(...),
    lang: str = Form("ko"),
    user: models.User = Depends(get_current_user)
):
    """Gen Video에서 생성된 영상을 LinkedIn에 포스팅합니다."""
    if not pdf2mp4:
        return JSONResponse(
            status_code=503,
            content={"status": "error", "message": "Service not initialized"}
        )

    try:
        # 영상 정보 가져오기
        video_info = pdf2mp4.get_video_info(video_id)
        if not video_info:
            return JSONResponse(
                status_code=404,
                content={"status": "error", "message": "Video not found"}
            )

        # PDF 파일 경로
        pdf_path = pdf2mp4.get_pdf_path(video_id)
        if not pdf_path or not os.path.exists(pdf_path):
            return JSONResponse(
                status_code=404,
                content={"status": "error", "message": "PDF not found for this video"}
            )

        video_path = video_info.get('file_path')
        if not video_path or not os.path.exists(video_path):
            return JSONResponse(
                status_code=404,
                content={"status": "error", "message": "Video file not found"}
            )

        # PDF에서 메타데이터 생성
        with open(pdf_path, 'rb') as f:
            pdf_content = f.read()

        metadata = youtube.poster.generate_metadata(pdf_content, category=category, lang=lang)
        if not metadata:
            return JSONResponse(
                status_code=500,
                content={"status": "error", "message": "Failed to generate metadata from PDF"}
            )

        # LinkedIn 포스팅
        from core.linkedin_poster import LinkedInPoster

        title = metadata.get('title', 'Video')
        description = metadata.get('description', '')

        # PDF 첫 페이지에서 썸네일 생성
        thumbnail_path = None
        try:
            import fitz  # PyMuPDF
            doc = fitz.open(pdf_path)
            page = doc.load_page(0)
            pix = page.get_pixmap(matrix=fitz.Matrix(2, 2))
            thumbnail_path = os.path.join(pdf2mp4.temp_dir, f"{video_id}_linkedin_thumb.png")
            pix.save(thumbnail_path)
            doc.close()
        except Exception as thumb_err:
            print(f"Failed to create thumbnail: {thumb_err}")

        # LinkedIn 포스터 초기화
        linkedin_poster = LinkedInPoster()

        # 이미지 업로드 (썸네일이 있는 경우)
        image_urn = None
        if thumbnail_path and os.path.exists(thumbnail_path):
            image_urn = linkedin_poster.upload_image(thumbnail_path)

        # 포스트 텍스트 작성
        post_text = f"{title}\n\n{description}"

        # LinkedIn에 포스팅
        result = linkedin_poster.post_text(
            text=post_text,
            title=title,
            uploaded_image_urn=image_urn
        )

        # 썸네일 정리
        if thumbnail_path and os.path.exists(thumbnail_path):
            os.remove(thumbnail_path)

        if result:
            post_id = result.get('id', '')
            return JSONResponse(content={
                "status": "success",
                "message": f"LinkedIn 포스팅 완료: {title}",
                "linkedin_post_id": post_id
            })
        else:
            return JSONResponse(
                status_code=500,
                content={"status": "error", "message": "LinkedIn posting failed"}
            )

    except Exception as e:
        print(f"Error posting to LinkedIn: {e}")
        import traceback
        traceback.print_exc()
        return JSONResponse(
            status_code=500,
            content={"status": "error", "message": str(e)}
        )


@app.post("/api/youtube/upload-from-genvideo")
async def youtube_upload_from_genvideo(
    background_tasks: BackgroundTasks,
    video_id: str = Form(...),
    pdf: UploadFile = File(None),
    pdf_id: str = Form(None),
    category: str = Form(...),
    lang: str = Form("ko"),
    use_thumbnail: bool = Form(True),
    user: models.User = Depends(get_current_user)
):
    """Gen Video에서 생성된 영상을 YouTube에 업로드합니다. (비동기)"""
    if not youtube or not pdf2mp4:
        return JSONResponse(
            status_code=503,
            content={"status": "error", "message": "Service not initialized"}
        )

    # Gen Video 파일 경로 조회
    video_path = pdf2mp4.get_video_path(video_id)
    if not video_path or not os.path.exists(video_path):
        return JSONResponse(
            status_code=404,
            content={"status": "error", "message": "Generated video not found"}
        )

    try:
        # 영상 파일 읽기
        with open(video_path, 'rb') as f:
            video_content = f.read()
        filename = os.path.basename(video_path)

        # PDF 내용 가져오기 (업로드 또는 Gen Video에서 선택)
        if pdf_id:
            # Gen Video에서 선택한 PDF 사용
            pdf_path = pdf2mp4.get_pdf_path(pdf_id)
            if not pdf_path or not os.path.exists(pdf_path):
                return JSONResponse(status_code=404, content={"status": "error", "message": "Selected PDF not found"})
            with open(pdf_path, 'rb') as f:
                pdf_content = f.read()
        elif pdf:
            # 직접 업로드한 PDF 사용
            pdf_content = await pdf.read()
        else:
            return JSONResponse(status_code=400, content={"status": "error", "message": "PDF file or pdf_id is required"})

        # 업로드 ID 생성 및 초기 상태 설정
        upload_id = str(uuid.uuid4())
        YouTubeService.update_upload_progress(upload_id, 'init', 0, '업로드 요청 접수됨 (Gen Video)')
        
        # 백그라운드 작업 시작
        background_tasks.add_task(
            youtube.process_and_upload,
            video_content, filename, pdf_content, category, lang, use_thumbnail, upload_id, gen_video_id=video_id
        )

        return JSONResponse(content={"status": "processing", "upload_id": upload_id})

    except Exception as e:
        return JSONResponse(
            status_code=500,
            content={"status": "error", "message": str(e)}
        )


# --- 오디오 생성 API ---

@app.get("/api/audio/voices")
async def get_available_voices(user: models.User = Depends(get_current_user)):
    """사용 가능한 TTS 음성 목록을 반환합니다."""
    voices = audio_generator.get_available_voices()
    return {"status": "success", "voices": voices}


@app.post("/api/audio/generate-script")
async def generate_script_from_pdf(
    pdf: UploadFile = File(...),
    language: str = Form("ko"),
    style: str = Form("educational"),
    background: bool = Form(True),
    user: models.User = Depends(get_current_user)
):
    """PDF에서 YouTube 영상용 대본을 생성합니다.

    background=True인 경우 백그라운드에서 실행되며 task_id를 반환합니다.
    클라이언트는 /api/audio/task/{task_id}로 진행 상황을 폴링해야 합니다.
    """
    try:
        pdf_bytes = await pdf.read()

        if background:
            # 백그라운드 태스크로 실행
            task_id = audio_generator.create_task('script', {
                'language': language,
                'style': style,
                'pdf_filename': pdf.filename
            })

            # 백그라운드에서 실행
            asyncio.create_task(
                audio_generator.run_script_generation_task(
                    task_id=task_id,
                    pdf_bytes=pdf_bytes,
                    language=language,
                    style=style
                )
            )

            return JSONResponse(content={
                "status": "started",
                "task_id": task_id,
                "message": "대본 생성이 시작되었습니다"
            })
        else:
            # 동기 모드 (기존 방식)
            result = await audio_generator.generate_script_from_pdf(
                pdf_bytes=pdf_bytes,
                language=language,
                style=style
            )
            return JSONResponse(content=result)

    except Exception as e:
        return JSONResponse(
            status_code=500,
            content={"status": "error", "message": str(e)}
        )


@app.post("/api/audio/generate-tts")
async def generate_audio_from_script(
    script: str = Form(...),
    voice: str = Form("Leda"),
    filename: str = Form(None),
    language: str = Form(None),
    style: str = Form(None),
    pdf_filename: str = Form(None),
    background: bool = Form(True),
    user: models.User = Depends(get_current_user)
):
    """대본에서 TTS 오디오를 생성합니다.

    background=True인 경우 백그라운드에서 실행되며 task_id를 반환합니다.
    클라이언트는 /api/audio/task/{task_id}로 진행 상황을 폴링해야 합니다.
    """
    try:
        # 메타데이터 구성
        metadata = {
            'language': language,
            'style': style,
            'pdf_filename': pdf_filename,
            'created_by': user.email
        }

        if background:
            # 백그라운드 태스크로 실행
            task_id = audio_generator.create_task('audio', {
                'voice': voice,
                'script_length': len(script),
                **metadata
            })

            # 백그라운드에서 실행
            asyncio.create_task(
                audio_generator.run_audio_generation_task(
                    task_id=task_id,
                    script=script,
                    voice=voice,
                    filename=filename,
                    metadata=metadata
                )
            )

            return JSONResponse(content={
                "status": "started",
                "task_id": task_id,
                "message": "오디오 생성이 시작되었습니다"
            })
        else:
            # 동기 모드 (기존 방식)
            result = await audio_generator.generate_audio_from_script(
                script=script,
                output_filename=filename,
                voice=voice,
                metadata=metadata
            )
            return JSONResponse(content=result)

    except Exception as e:
        return JSONResponse(
            status_code=500,
            content={"status": "error", "message": str(e)}
        )


@app.post("/api/audio/generate")
async def generate_audio_from_pdf(
    pdf: UploadFile = File(...),
    language: str = Form("ko"),
    style: str = Form("educational"),
    voice: str = Form("Leda"),
    filename: str = Form(None),
    user: models.User = Depends(get_current_user)
):
    """PDF에서 직접 오디오를 생성합니다 (대본 생성 + TTS)."""
    try:
        pdf_bytes = await pdf.read()

        # 파일명이 없으면 PDF 파일명 사용
        if not filename and pdf.filename:
            filename = os.path.splitext(pdf.filename)[0]

        result = await audio_generator.generate_audio_from_pdf(
            pdf_bytes=pdf_bytes,
            output_filename=filename,
            language=language,
            style=style,
            voice=voice
        )

        return JSONResponse(content=result)

    except Exception as e:
        return JSONResponse(
            status_code=500,
            content={"status": "error", "message": str(e)}
        )


@app.get("/api/audio/list")
async def list_generated_audio(user: models.User = Depends(get_current_user)):
    """생성된 오디오 파일 목록을 반환합니다."""
    audio_files = audio_generator.list_generated_audio()
    return {"status": "success", "audio_files": audio_files}


@app.get("/api/audio/download/{filename}")
async def download_audio(filename: str, token: str = None):
    """오디오 파일을 다운로드합니다."""
    # 토큰 검증
    if not token:
        raise HTTPException(status_code=401, detail="Token required")

    try:
        payload = auth_service.jwt.decode(token, auth_service.SECRET_KEY, algorithms=[auth_service.ALGORITHM])
    except:
        raise HTTPException(status_code=401, detail="Invalid token")

    filepath = os.path.join(audio_generator.output_dir, filename)
    if not os.path.exists(filepath):
        raise HTTPException(status_code=404, detail="File not found")

    return FileResponse(
        filepath,
        media_type="audio/wav",
        filename=filename
    )


@app.delete("/api/audio/{filename}")
async def delete_audio(filename: str, user: models.User = Depends(get_current_user)):
    """오디오 파일을 삭제합니다."""
    success = audio_generator.delete_audio(filename)
    if success:
        return {"status": "success", "message": "Audio file deleted"}
    else:
        raise HTTPException(status_code=404, detail="File not found")


@app.get("/api/audio/task/{task_id}")
async def get_audio_task_status(task_id: str, user: models.User = Depends(get_current_user)):
    """백그라운드 태스크의 진행 상황을 조회합니다."""
    task = audio_generator.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    return JSONResponse(content=task)


@app.delete("/api/audio/task/{task_id}")
async def delete_audio_task(task_id: str, user: models.User = Depends(get_current_user)):
    """완료된 태스크를 삭제합니다."""
    task = audio_generator.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    audio_generator.delete_task(task_id)
    return {"status": "success", "message": "Task deleted"}


# ========== Common API (Categories & Languages) ==========

# 통합 카테고리 데이터
CATEGORIES = [
    {"id": "tech", "name_ko": "테크", "name_en": "Tech", "description_ko": "기술, IT, AI 관련 콘텐츠", "description_en": "Technology, IT, AI content"},
    {"id": "entertainment", "name_ko": "엔터테인먼트", "name_en": "Entertainment", "description_ko": "영화, 음악, 연예 콘텐츠", "description_en": "Movies, music, celebrity content"},
    {"id": "beauty", "name_ko": "뷰티", "name_en": "Beauty", "description_ko": "화장품, 스킨케어, 메이크업", "description_en": "Cosmetics, skincare, makeup"},
    {"id": "lifestyle", "name_ko": "라이프스타일", "name_en": "Lifestyle", "description_ko": "일상, 여행, 음식, 패션", "description_en": "Daily life, travel, food, fashion"},
]

# 통합 언어 데이터
LANGUAGES = [
    {"id": "ko", "name_ko": "한국어", "name_en": "Korean"},
    {"id": "en", "name_ko": "영어", "name_en": "English"},
]


@app.get("/api/common/categories")
async def get_categories(user: models.User = Depends(get_current_user)):
    """카테고리 목록을 반환합니다."""
    return JSONResponse(content={"status": "success", "categories": CATEGORIES})


@app.get("/api/common/languages")
async def get_languages(user: models.User = Depends(get_current_user)):
    """언어 목록을 반환합니다."""
    return JSONResponse(content={"status": "success", "languages": LANGUAGES})


# ========== Content Generator API ==========

@app.post("/api/content/generate-plan")
async def generate_content_plan(
    topic: str = Form(...),
    category: str = Form("educational"),
    target_slides: int = Form(15),
    language: str = Form("ko"),
    additional_instructions: str = Form(""),
    user: models.User = Depends(get_current_user)
):
    """콘텐츠 기획안을 생성합니다."""
    try:
        result = await content_generator.generate_content_plan(
            topic=topic,
            category=category,
            target_slides=target_slides,
            language=language,
            additional_instructions=additional_instructions
        )
        return JSONResponse(content=result)
    except Exception as e:
        return JSONResponse(
            status_code=500,
            content={"status": "error", "message": str(e)}
        )


@app.post("/api/content/generate-images/{plan_id}")
async def generate_plan_images(
    plan_id: str,
    user: models.User = Depends(get_current_user)
):
    """기획안의 모든 슬라이드 이미지를 생성합니다."""
    try:
        result = await content_generator.generate_all_images(plan_id=plan_id)
        return JSONResponse(content=result)
    except Exception as e:
        return JSONResponse(
            status_code=500,
            content={"status": "error", "message": str(e)}
        )


@app.post("/api/content/create-pdf/{plan_id}")
async def create_pdf_from_plan(
    plan_id: str,
    title: str = Form(None),
    user: models.User = Depends(get_current_user)
):
    """생성된 이미지들을 PDF로 합칩니다."""
    try:
        result = await content_generator.create_pdf_from_plan(
            plan_id=plan_id,
            title=title
        )
        return JSONResponse(content=result)
    except Exception as e:
        return JSONResponse(
            status_code=500,
            content={"status": "error", "message": str(e)}
        )


@app.get("/api/content/plans")
async def list_content_plans(user: models.User = Depends(get_current_user)):
    """기획안 목록을 반환합니다."""
    plans = content_generator.list_plans()
    return {"status": "success", "plans": plans}


@app.get("/api/content/plan/{plan_id}")
async def get_content_plan(plan_id: str, user: models.User = Depends(get_current_user)):
    """특정 기획안을 반환합니다."""
    plan = content_generator.get_plan(plan_id)
    if plan:
        return {"status": "success", "plan": plan}
    else:
        raise HTTPException(status_code=404, detail="Plan not found")


@app.delete("/api/content/plan/{plan_id}")
async def delete_content_plan(plan_id: str, user: models.User = Depends(get_current_user)):
    """기획안과 관련 파일들을 삭제합니다."""
    success = content_generator.delete_plan(plan_id)
    if success:
        return {"status": "success", "message": "Plan deleted"}
    else:
        raise HTTPException(status_code=404, detail="Plan not found")


@app.get("/api/content/plan/{plan_id}/images")
async def list_plan_images(plan_id: str, user: models.User = Depends(get_current_user)):
    """기획안의 생성된 이미지 목록을 반환합니다."""
    images = content_generator.list_images_for_plan(plan_id)
    return {"status": "success", "images": images, "plan_id": plan_id}


@app.get("/api/content/image/download/{filename}")
async def download_content_image(filename: str, token: str = None):
    """생성된 이미지를 다운로드합니다."""
    if not token:
        raise HTTPException(status_code=401, detail="Token required")

    try:
        payload = auth_service.jwt.decode(token, auth_service.SECRET_KEY, algorithms=[auth_service.ALGORITHM])
    except:
        raise HTTPException(status_code=401, detail="Invalid token")

    filepath = os.path.join(content_generator.output_dir, filename)
    if not os.path.exists(filepath):
        raise HTTPException(status_code=404, detail="File not found")

    return FileResponse(
        filepath,
        media_type="image/png",
        filename=filename
    )


@app.delete("/api/content/image/{filename}")
async def delete_content_image(filename: str, user: models.User = Depends(get_current_user)):
    """생성된 이미지를 삭제합니다."""
    filepath = os.path.join(content_generator.output_dir, filename)
    if not os.path.exists(filepath):
        raise HTTPException(status_code=404, detail="File not found")

    try:
        os.remove(filepath)
        return {"status": "success", "message": "Image deleted"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/content/pdfs")
async def list_generated_pdfs(user: models.User = Depends(get_current_user)):
    """생성된 PDF 목록을 반환합니다."""
    pdfs = content_generator.list_generated_pdfs()
    return {"status": "success", "pdfs": pdfs}


@app.get("/api/content/pdf/download/{filename}")
async def download_generated_pdf(filename: str, token: str = None):
    """생성된 PDF를 다운로드합니다."""
    if not token:
        raise HTTPException(status_code=401, detail="Token required")

    try:
        payload = auth_service.jwt.decode(token, auth_service.SECRET_KEY, algorithms=[auth_service.ALGORITHM])
    except:
        raise HTTPException(status_code=401, detail="Invalid token")

    filepath = os.path.join(content_generator.pdf_dir, filename)
    if not os.path.exists(filepath):
        raise HTTPException(status_code=404, detail="File not found")

    return FileResponse(
        filepath,
        media_type="application/pdf",
        filename=filename
    )


@app.delete("/api/content/pdf/{filename}")
async def delete_generated_pdf(filename: str, user: models.User = Depends(get_current_user)):
    """생성된 PDF를 삭제합니다."""
    success = content_generator.delete_pdf(filename)
    if success:
        return {"status": "success", "message": "PDF deleted"}
    else:
        raise HTTPException(status_code=404, detail="File not found")


# ========== Auto Pipeline API ==========

from services.auto_pipeline_service import auto_pipeline


class PipelineStartRequest(BaseModel):
    topic: str
    category: str = 'educational'
    target_slides: int = 15
    language: str = 'ko'
    additional_instructions: str = ''
    voice: str = 'Kore'
    script_style: str = 'educational'
    youtube_privacy: str = 'private'


@app.post("/api/pipeline/start")
async def start_auto_pipeline(
    request: PipelineStartRequest,
    background_tasks: BackgroundTasks,
    user: models.User = Depends(get_current_user)
):
    """전체 자동화 파이프라인을 시작합니다."""
    pipeline_id = str(uuid.uuid4())[:8]

    # 파이프라인 초기화
    auto_pipeline.pipelines[pipeline_id] = {
        'id': pipeline_id,
        'topic': request.topic,
        'category': request.category,
        'language': request.language,
        'status': 'starting',
        'current_step': 'initializing',
        'progress': 0,
        'steps_completed': [],
        'error': None,
        'result': {},
        'user_id': user.id
    }

    # 백그라운드에서 파이프라인 실행
    async def run_pipeline():
        try:
            await auto_pipeline.run_full_pipeline(
                topic=request.topic,
                category=request.category,
                target_slides=request.target_slides,
                language=request.language,
                additional_instructions=request.additional_instructions,
                voice=request.voice,
                script_style=request.script_style,
                youtube_privacy=request.youtube_privacy,
                user_id=user.id
            )
        except Exception as e:
            import traceback
            traceback.print_exc()
            auto_pipeline.pipelines[pipeline_id]['status'] = 'failed'
            auto_pipeline.pipelines[pipeline_id]['error'] = str(e)

    # asyncio.create_task로 백그라운드 실행
    asyncio.create_task(run_pipeline())

    return JSONResponse(content={
        "status": "started",
        "pipeline_id": pipeline_id,
        "message": "파이프라인이 시작되었습니다."
    })


@app.get("/api/pipeline/status/{pipeline_id}")
async def get_pipeline_status(pipeline_id: str, user: models.User = Depends(get_current_user)):
    """파이프라인 상태를 조회합니다."""
    pipeline = auto_pipeline.get_pipeline_status(pipeline_id)
    if not pipeline:
        raise HTTPException(status_code=404, detail="Pipeline not found")

    return JSONResponse(content={
        "status": "success",
        "pipeline": pipeline
    })


@app.get("/api/pipeline/list")
async def list_pipelines(user: models.User = Depends(get_current_user)):
    """사용자의 파이프라인 목록을 반환합니다."""
    pipelines = auto_pipeline.list_pipelines()
    # 사용자 필터링 (선택적)
    user_pipelines = [p for p in pipelines if p.get('user_id') == user.id]
    return JSONResponse(content={
        "status": "success",
        "pipelines": user_pipelines
    })


@app.post("/api/pipeline/cancel/{pipeline_id}")
async def cancel_pipeline(pipeline_id: str, user: models.User = Depends(get_current_user)):
    """파이프라인을 취소합니다."""
    success = auto_pipeline.cancel_pipeline(pipeline_id)
    if success:
        return {"status": "success", "message": "Pipeline cancelled"}
    else:
        raise HTTPException(status_code=400, detail="Cannot cancel pipeline")


if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)

