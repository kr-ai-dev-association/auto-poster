from fastapi import FastAPI, Request, UploadFile, File, Form, BackgroundTasks, Depends, HTTPException, status
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, JSONResponse, FileResponse, RedirectResponse
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
import uvicorn
import os
import shutil
from datetime import timedelta
from sqlalchemy.orm import Session
from pydantic import BaseModel

from services.converter_service import ConverterService
from services.linkedin_service import LinkedinService
from services.youtube_service import YouTubeService
from services import auth_service
from core import database, models

# DB 초기화
models.Base.metadata.create_all(bind=database.engine)

app = FastAPI(title="Auto Poster")

# 정적 파일 및 템플릿 설정
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

# 서비스 인스턴스
converter = ConverterService()
linkedin = LinkedinService()
youtube = YouTubeService()

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

# --- 기존 API (보안 적용) ---

@app.post("/api/upload")
async def process_content(
    file: UploadFile = File(None),
    content: str = Form(None),
    title: str = Form(None),
    user: models.User = Depends(get_current_user)
):
    """
    파일 업로드 또는 텍스트 직접 입력을 처리합니다.
    """
    if not file and not content:
        return JSONResponse(status_code=400, content={"message": "No file or content provided"})

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
    try:
        result = await converter.process_markdown(markdown_text, filename)
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
    try:
        result = await linkedin.share_wiki(wiki_id, wiki_url, lang)
        return JSONResponse(content=result)
    except Exception as e:
        return JSONResponse(status_code=500, content={"status": "error", "message": str(e)})

# --- Youtube Poster Endpoints ---

@app.get("/api/youtube/logo/{category}")
async def get_youtube_logo(category: str, token: str = None, db: Session = Depends(database.get_db)):
    """카테고리별 현재 로고 이미지를 반환합니다. (이미지 태그용 토큰 지원)"""
    if not token:
        raise HTTPException(status_code=401, detail="Token required")
    
    try:
        user = get_current_user(token, db)
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid token")

    logo_path = youtube.get_logo_path(category)
    if logo_path and os.path.exists(logo_path):
        return FileResponse(logo_path)
    return JSONResponse(status_code=404, content={"message": "Logo not found"})

@app.post("/api/youtube/logo/upload")
async def upload_youtube_logo(
    logo: UploadFile = File(...),
    category: str = Form(...),
    user: models.User = Depends(get_current_user)
):
    """새로운 로고 이미지를 업로드하고 교체합니다."""
    try:
        content = await logo.read()
        youtube.save_logo(category, content, logo.filename)
        return JSONResponse(content={"status": "success", "message": "Logo uploaded successfully"})
    except Exception as e:
        return JSONResponse(status_code=500, content={"status": "error", "message": str(e)})

@app.post("/api/youtube/metadata")
async def generate_youtube_metadata(
    pdf: UploadFile = File(...),
    category: str = Form(...),
    lang: str = Form("ko"),
    user: models.User = Depends(get_current_user)
):
    """PDF 분석을 통해 유튜브 메타데이터를 생성합니다."""
    try:
        content = await pdf.read()
        metadata = await youtube.generate_metadata(content, category, lang)
        return JSONResponse(content={"status": "success", "metadata": metadata})
    except Exception as e:
        return JSONResponse(status_code=500, content={"status": "error", "message": str(e)})

@app.post("/api/youtube/upload")
async def youtube_upload(
    video: UploadFile = File(...),
    pdf: UploadFile = File(...),
    category: str = Form(...),
    lang: str = Form("ko"),
    gen_sub: bool = Form(False),
    user: models.User = Depends(get_current_user)
):
    """영상을 처리하고 유튜브에 업로드합니다."""
    try:
        video_content = await video.read()
        pdf_content = await pdf.read()
        result = await youtube.process_and_upload(
            video_content, video.filename, pdf_content, category, lang, gen_sub
        )
        return JSONResponse(content=result)
    except Exception as e:
        return JSONResponse(status_code=500, content={"status": "error", "message": str(e)})

@app.post("/api/youtube/share/linkedin")
async def youtube_share_linkedin(
    video_id: str = Form(...),
    video_url: str = Form(...),
    lang: str = Form("ko"),
    user: models.User = Depends(get_current_user)
):
    """유튜브 영상을 링크드인에 공유합니다."""
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

if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)

