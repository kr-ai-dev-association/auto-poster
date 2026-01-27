"""
PDF to MP4 변환 서비스
PDF 파일을 MP4 영상으로 변환하는 기능을 제공합니다.
NVENC GPU 가속을 직접 사용합니다.
"""

import os
import tempfile
import shutil
import uuid
import json
from datetime import datetime
from typing import Optional, List, Dict, Any
from dataclasses import dataclass
import subprocess

# PDF to Image
from pdf2image import convert_from_bytes
import io

# PDF text extraction
try:
    import PyPDF2
    PYPDF_AVAILABLE = True
except ImportError:
    PYPDF_AVAILABLE = False

# PaddleOCR for image-based PDF text extraction
try:
    from paddleocr import PaddleOCR
    PADDLEOCR_AVAILABLE = True
except ImportError:
    PADDLEOCR_AVAILABLE = False
    print("Warning: PaddleOCR not installed. OCR-based text extraction will not be available.")

from PIL import Image
import numpy as np
import re
from difflib import SequenceMatcher

# Whisper for Smart mode (optional)
try:
    import whisper
    WHISPER_AVAILABLE = True
except ImportError:
    WHISPER_AVAILABLE = False
    print("Warning: openai-whisper not installed. Smart mode will not be available.")

# Sentence Transformers for semantic similarity (optional)
try:
    from sentence_transformers import SentenceTransformer
    SENTENCE_TRANSFORMERS_AVAILABLE = True
except ImportError:
    SENTENCE_TRANSFORMERS_AVAILABLE = False
    print("Warning: sentence-transformers not installed. Semantic similarity will not be available.")

# Deep Translator for English to Korean translation (optional)
try:
    from deep_translator import GoogleTranslator
    TRANSLATOR_AVAILABLE = True
except ImportError:
    TRANSLATOR_AVAILABLE = False
    print("Warning: deep-translator not installed. English to Korean translation will not be available.")


@dataclass
class ConversionConfig:
    """변환 설정"""
    page_duration: float = 5.0
    transition_duration: float = 0.5
    transition_type: str = 'fade'
    fps: int = 30
    width: int = 1920
    height: int = 1080
    dpi: int = 200


class PDF2MP4Service:
    """PDF를 MP4 영상으로 변환하는 서비스 (NVENC 직접 사용)"""

    TRANSITIONS = ['fade', 'slide_left', 'slide_right', 'slide_up', 'slide_down', 'zoom', 'none']
    AUDIO_FORMATS = ['.mp3', '.wav', '.m4a', '.aac', '.ogg']
    _progress_store: Dict[str, Dict[str, Any]] = {}
    _cancel_store: Dict[str, bool] = {}  # 취소 요청 저장소
    _temp_dirs: Dict[str, str] = {}  # video_id -> temp_dir 매핑
    _process_pids: Dict[str, int] = {}  # video_id -> process PID 매핑

    def __init__(self):
        self.output_dir = os.path.join(
            os.path.dirname(__file__),
            '..', '..', 'generated_videos'
        )
        self.pdf_dir = os.path.join(
            os.path.dirname(__file__),
            '..', '..', 'generated_pdfs'
        )
        os.makedirs(self.output_dir, exist_ok=True)
        os.makedirs(self.pdf_dir, exist_ok=True)
        self._whisper_model = None
        self._paddleocr = None
        self._sentence_model = None
        self._translator = None

    def get_paddleocr(self, lang: str = 'korean'):
        """PaddleOCR 모델 (지연 로딩) - 언어별 캐시"""
        if not PADDLEOCR_AVAILABLE:
            return None

        # 언어별 캐시 키
        cache_key = f'_paddleocr_{lang}'
        if not hasattr(self, cache_key) or getattr(self, cache_key) is None:
            print(f"Loading PaddleOCR model (lang={lang})...")
            setattr(self, cache_key, PaddleOCR(use_angle_cls=True, lang=lang, show_log=False))
        return getattr(self, cache_key)

    @property
    def paddleocr(self):
        """PaddleOCR 모델 (기본 한국어) - 하위 호환성"""
        return self.get_paddleocr('korean')

    @classmethod
    def get_progress(cls, video_id: str) -> Optional[Dict[str, Any]]:
        return cls._progress_store.get(video_id)

    @classmethod
    def update_progress(cls, video_id: str, stage: str, progress: int, message: str, eta_or_result: Optional[Any] = None):
        progress_data = {
            'video_id': video_id,
            'step': stage,
            'progress': progress,
            'message': message,
            'timestamp': datetime.now().isoformat()
        }
        # eta_or_result가 dict이면 result로, 숫자면 eta로 처리
        if isinstance(eta_or_result, dict):
            progress_data['result'] = eta_or_result
        else:
            progress_data['eta'] = eta_or_result
        cls._progress_store[video_id] = progress_data

    @classmethod
    def clear_progress(cls, video_id: str):
        if video_id in cls._progress_store:
            del cls._progress_store[video_id]

    @classmethod
    def get_in_progress_tasks(cls) -> Dict[str, Dict[str, Any]]:
        """진행 중인 모든 태스크를 반환합니다."""
        in_progress = {}
        for video_id, progress_data in cls._progress_store.items():
            # 완료되지 않은 태스크만 반환 (stage가 complete, error, cancelled가 아닌 것)
            stage = progress_data.get('stage', '')
            if stage not in ['complete', 'error', 'cancelled']:
                in_progress[video_id] = progress_data
        return in_progress

    @classmethod
    def request_cancel(cls, video_id: str) -> bool:
        """변환 취소 요청"""
        if video_id in cls._progress_store:
            cls._cancel_store[video_id] = True
            return True
        return False

    @classmethod
    def is_cancelled(cls, video_id: str) -> bool:
        """취소 요청 여부 확인"""
        return cls._cancel_store.get(video_id, False)

    @classmethod
    def clear_cancel(cls, video_id: str):
        """취소 상태 정리"""
        if video_id in cls._cancel_store:
            del cls._cancel_store[video_id]

    @classmethod
    def register_temp_dir(cls, video_id: str, temp_dir: str):
        """임시 디렉토리 등록"""
        cls._temp_dirs[video_id] = temp_dir

    @classmethod
    def cleanup_temp_dir(cls, video_id: str):
        """임시 디렉토리 정리"""
        if video_id in cls._temp_dirs:
            temp_dir = cls._temp_dirs[video_id]
            if os.path.exists(temp_dir):
                import shutil
                shutil.rmtree(temp_dir, ignore_errors=True)
                print(f"[{video_id}] 🗑️ 임시 디렉토리 삭제: {temp_dir}")
            del cls._temp_dirs[video_id]

    @classmethod
    def register_process_pid(cls, video_id: str, pid: int):
        """변환 프로세스 PID 등록"""
        cls._process_pids[video_id] = pid
        print(f"[{video_id}] 📝 프로세스 PID 등록: {pid}")

    @classmethod
    def clear_process_pid(cls, video_id: str):
        """프로세스 PID 정리"""
        if video_id in cls._process_pids:
            del cls._process_pids[video_id]

    @classmethod
    def kill_process(cls, video_id: str) -> bool:
        """변환 프로세스 강제 종료"""
        import signal
        if video_id not in cls._process_pids:
            return False

        pid = cls._process_pids[video_id]
        try:
            # 프로세스 그룹 전체 종료 (자식 프로세스 포함)
            os.killpg(os.getpgid(pid), signal.SIGTERM)
            print(f"[{video_id}] 🛑 프로세스 그룹 종료 시도: {pid}")
        except ProcessLookupError:
            print(f"[{video_id}] ⚠️ 프로세스가 이미 종료됨: {pid}")
        except PermissionError:
            # 프로세스 그룹 종료 실패시 단일 프로세스 종료 시도
            try:
                os.kill(pid, signal.SIGTERM)
                print(f"[{video_id}] 🛑 단일 프로세스 종료: {pid}")
            except:
                pass
        except Exception as e:
            print(f"[{video_id}] ⚠️ 프로세스 종료 실패: {e}")
            return False

        cls.clear_process_pid(video_id)
        return True

    def cancel_conversion(self, video_id: str) -> Dict[str, Any]:
        """변환 취소 및 정리"""
        if video_id not in self._progress_store:
            return {'status': 'error', 'message': '진행 중인 변환을 찾을 수 없습니다.'}

        # 취소 플래그 설정
        self.request_cancel(video_id)

        # 프로세스 강제 종료
        self.kill_process(video_id)

        # 임시 파일 정리
        self.cleanup_temp_dir(video_id)

        # 생성된 출력 파일 삭제
        for f in os.listdir(self.output_dir):
            if video_id in f:
                file_path = os.path.join(self.output_dir, f)
                try:
                    os.remove(file_path)
                    print(f"[{video_id}] 🗑️ 출력 파일 삭제: {f}")
                except Exception as e:
                    print(f"[{video_id}] ⚠️ 파일 삭제 실패: {f} - {e}")

        # 생성된 PDF 파일 삭제
        for f in os.listdir(self.pdf_dir):
            if video_id in f:
                file_path = os.path.join(self.pdf_dir, f)
                try:
                    os.remove(file_path)
                    print(f"[{video_id}] 🗑️ PDF 파일 삭제: {f}")
                except Exception as e:
                    print(f"[{video_id}] ⚠️ PDF 삭제 실패: {f} - {e}")

        # 진행 상태 업데이트
        self.update_progress(video_id, 'cancelled', 0, '❌ 변환이 취소되었습니다.', None)

        return {'status': 'success', 'message': '변환이 취소되었습니다.'}

    @property
    def whisper_model(self):
        if self._whisper_model is None and WHISPER_AVAILABLE:
            import torch
            device = "cuda" if torch.cuda.is_available() else "cpu"
            print(f"Loading Whisper model (base) on {device}...")
            self._whisper_model = whisper.load_model("base", device=device)
        return self._whisper_model

    @property
    def sentence_model(self):
        """Sentence Transformer 모델 (지연 로딩)"""
        if self._sentence_model is None and SENTENCE_TRANSFORMERS_AVAILABLE:
            import torch
            device = "cuda" if torch.cuda.is_available() else "cpu"
            print(f"Loading Sentence Transformer model on {device}...")
            self._sentence_model = SentenceTransformer('all-MiniLM-L6-v2', device=device)
        return self._sentence_model

    @property
    def translator(self):
        """Google Translator (지연 로딩)"""
        if self._translator is None and TRANSLATOR_AVAILABLE:
            print("Loading Google Translator (deep-translator)...")
            self._translator = GoogleTranslator(source='en', target='ko')
        return self._translator

    def _resize_image(self, img: Image.Image, width: int, height: int, logo_img: Image.Image = None) -> np.ndarray:
        """이미지를 지정된 크기로 리사이즈 (종횡비 유지, 검은 배경, 로고 합성)"""
        orig_width, orig_height = img.size
        ratio = min(width / orig_width, height / orig_height)
        new_width = int(orig_width * ratio)
        new_height = int(orig_height * ratio)

        img_resized = img.resize((new_width, new_height), Image.Resampling.LANCZOS)
        background = Image.new('RGB', (width, height), (0, 0, 0))
        offset_x = (width - new_width) // 2
        offset_y = (height - new_height) // 2
        background.paste(img_resized, (offset_x, offset_y))

        # 로고 합성 (영상 프레임 우측 하단 끝에 맞춤)
        if logo_img is not None:
            # 로고 크기 조정 (문서 너비의 약 10%)
            logo_target_width = int(new_width * 0.10)
            logo_ratio = logo_target_width / logo_img.width
            logo_new_height = int(logo_img.height * logo_ratio)
            logo_resized = logo_img.resize((logo_target_width, logo_new_height), Image.Resampling.LANCZOS)

            # 영상 프레임 우측 하단 끝에 로고 배치
            logo_x = width - logo_target_width
            logo_y = height - logo_new_height

            # 알파 채널이 있으면 투명도 적용하여 합성
            if logo_resized.mode == 'RGBA':
                background.paste(logo_resized, (logo_x, logo_y), logo_resized)
            else:
                background.paste(logo_resized, (logo_x, logo_y))

        return np.array(background)

    def _extract_pdf_page_texts(self, pdf_content: bytes) -> List[str]:
        """PDF 각 페이지에서 텍스트 추출 (PyPDF2 실패 시 OCR 사용)"""
        page_texts = []

        # 1. PyPDF2로 텍스트 추출 시도
        if PYPDF_AVAILABLE:
            try:
                pdf_reader = PyPDF2.PdfReader(io.BytesIO(pdf_content))
                for page in pdf_reader.pages:
                    text = page.extract_text() or ""
                    text = text.lower()
                    text = re.sub(r'[^\w\s]', ' ', text)
                    text = ' '.join(text.split())
                    page_texts.append(text)

                # 텍스트가 추출되었는지 확인
                total_text = ''.join(page_texts)
                if len(total_text) > 50:  # 충분한 텍스트가 있으면 반환
                    print(f"PyPDF2로 텍스트 추출 성공: {len(total_text)} 문자")
                    return page_texts
                else:
                    print(f"PyPDF2 텍스트 부족 ({len(total_text)} 문자), OCR 시도...")
                    page_texts = []  # 리셋
            except Exception as e:
                print(f"PyPDF2 텍스트 추출 오류: {e}")

        return page_texts

    def _extract_text_with_ocr(self, images: List[Image.Image], video_id: str = "", ocr_lang: str = "korean") -> List[str]:
        """PaddleOCR을 사용하여 이미지에서 텍스트 추출"""
        ocr_model = self.get_paddleocr(ocr_lang)
        if not PADDLEOCR_AVAILABLE or ocr_model is None:
            print(f"[{video_id}] PaddleOCR 사용 불가")
            return []

        page_texts = []
        print(f"[{video_id}] 🔍 PaddleOCR로 {len(images)}개 페이지 텍스트 추출 시작 (lang={ocr_lang})")

        for i, img in enumerate(images):
            try:
                # PIL Image를 numpy array로 변환
                img_array = np.array(img.convert('RGB'))

                # OCR 수행 (PaddleOCR 2.x)
                result = ocr_model.ocr(img_array, cls=True)

                # 텍스트 추출
                texts = []
                if result and result[0]:
                    for line in result[0]:
                        if line and len(line) >= 2:
                            text = line[1][0] if isinstance(line[1], tuple) else line[1]
                            texts.append(text)

                # 정규화
                page_text = ' '.join(texts).lower()
                page_text = re.sub(r'[^\w\s]', ' ', page_text)
                page_text = ' '.join(page_text.split())
                page_texts.append(page_text)

                if (i + 1) % 5 == 0 or i == len(images) - 1:
                    print(f"[{video_id}]   OCR 진행: {i + 1}/{len(images)} 페이지")

            except Exception as e:
                print(f"[{video_id}] OCR 오류 (페이지 {i + 1}): {e}")
                page_texts.append("")

        return page_texts

    def _is_mostly_english(self, text: str) -> bool:
        """텍스트가 주로 영문인지 확인 (60% 이상 영문이면 True)"""
        if not text or len(text.strip()) < 10:
            return False

        # 영문 알파벳 문자 수 세기
        english_chars = sum(1 for c in text if c.isalpha() and ord(c) < 128)
        # 전체 알파벳 문자 수 (한글 포함)
        total_alpha = sum(1 for c in text if c.isalpha())

        if total_alpha == 0:
            return False

        english_ratio = english_chars / total_alpha
        return english_ratio > 0.6

    def _extract_english_words(self, text: str, min_length: int = 3) -> List[str]:
        """텍스트에서 영문 단어만 추출 (기술 용어 등)"""
        # 영문 단어 패턴 (연속된 영문자)
        words = re.findall(r'[a-zA-Z]{3,}', text)
        # 소문자로 변환하고 중복 제거
        unique_words = list(set(w.lower() for w in words if len(w) >= min_length))
        return unique_words

    def _translate_english_keywords_to_korean(self, texts: List[str], video_id: str = "") -> List[str]:
        """텍스트 내 영문 키워드를 한국어로 번역하여 텍스트에 추가 (매칭 정확도 향상용)

        한글+영문 혼합 문서에서 영문 기술 용어를 한국어로 변환하여
        한국어 오디오 트랜스크립트와의 매칭률을 높입니다.
        """
        if not TRANSLATOR_AVAILABLE or self.translator is None:
            print(f"[{video_id}] Google Translator 사용 불가 - 번역 건너뜀")
            return texts

        enhanced_texts = []
        translated_count = 0

        # 기술 용어 사전 (번역 캐시)
        translation_cache = {}

        print(f"[{video_id}] 🌐 영문 키워드 한국어 번역 시작...")

        for i, text in enumerate(texts):
            if not text or not text.strip():
                enhanced_texts.append(text)
                continue

            # 영문 단어 추출
            english_words = self._extract_english_words(text, min_length=4)

            if not english_words:
                enhanced_texts.append(text)
                continue

            # 번역할 단어들 (캐시에 없는 것만)
            words_to_translate = [w for w in english_words if w not in translation_cache]

            if words_to_translate:
                try:
                    # 단어들을 한 번에 번역 (효율성)
                    words_text = ' | '.join(words_to_translate[:30])  # 최대 30개
                    translated = self.translator.translate(words_text)

                    if translated:
                        translated_words = translated.split(' | ')
                        for orig, trans in zip(words_to_translate[:30], translated_words):
                            trans = trans.strip()
                            # 번역 결과가 원본과 다르고 의미있는 경우만 캐시
                            if trans and trans.lower() != orig.lower() and len(trans) > 1:
                                translation_cache[orig] = trans
                        translated_count += 1

                except Exception as e:
                    print(f"[{video_id}] 번역 오류 (페이지 {i + 1}): {e}")

            # 원본 텍스트에 번역된 키워드 추가
            translated_keywords = []
            for word in english_words:
                if word in translation_cache:
                    translated_keywords.append(translation_cache[word])

            # 원본 + 번역된 키워드 결합
            if translated_keywords:
                enhanced_text = text + ' ' + ' '.join(translated_keywords)
            else:
                enhanced_text = text

            enhanced_texts.append(enhanced_text)

            if (i + 1) % 5 == 0:
                print(f"[{video_id}]   번역 진행: {i + 1}/{len(texts)} 페이지")

        print(f"[{video_id}] ✅ 키워드 번역 완료: {len(translation_cache)}개 용어 번역됨")
        if translation_cache:
            sample = list(translation_cache.items())[:5]
            print(f"[{video_id}]   예시: {sample}")

        return enhanced_texts

    def _find_page_mentions_in_transcript(
        self,
        segments: List[Dict],
        num_pages: int,
        video_id: str = ""
    ) -> Dict[int, float]:
        """
        Whisper 세그먼트에서 'Page X' 언급을 탐지하여 페이지별 시작 시간 추출

        Args:
            segments: Whisper 세그먼트 목록
            num_pages: PDF 총 페이지 수
            video_id: 로깅용 비디오 ID

        Returns:
            {페이지번호: 언급시간} 딕셔너리 (1-indexed)
        """
        # 영어 숫자 단어 -> 숫자 매핑
        number_words = {
            'one': 1, 'two': 2, 'three': 3, 'four': 4, 'five': 5,
            'six': 6, 'seven': 7, 'eight': 8, 'nine': 9, 'ten': 10,
            'eleven': 11, 'twelve': 12, 'thirteen': 13, 'fourteen': 14, 'fifteen': 15,
            'sixteen': 16, 'seventeen': 17, 'eighteen': 18, 'nineteen': 19, 'twenty': 20,
            'first': 1, 'second': 2, 'third': 3, 'fourth': 4, 'fifth': 5,
            'sixth': 6, 'seventh': 7, 'eighth': 8, 'ninth': 9, 'tenth': 10
        }

        page_mentions = {}  # {page_num: earliest_mention_time}

        for seg in segments:
            text = seg.get('text', '').lower()
            seg_time = seg['start']

            # 패턴 1: "page two", "page three" 등 영어 단어
            for word, num in number_words.items():
                # "page two", "page 2" 패턴
                if f"page {word}" in text and num <= num_pages:
                    if num not in page_mentions or seg_time < page_mentions[num]:
                        page_mentions[num] = seg_time
                # "slide two", "slide 2" 패턴도 지원
                if f"slide {word}" in text and num <= num_pages:
                    if num not in page_mentions or seg_time < page_mentions[num]:
                        page_mentions[num] = seg_time

            # 패턴 2: "page 2", "page 10" 등 숫자
            import re
            # "page X" 패턴
            for match in re.finditer(r'page\s*(\d+)', text):
                num = int(match.group(1))
                if 1 <= num <= num_pages:
                    if num not in page_mentions or seg_time < page_mentions[num]:
                        page_mentions[num] = seg_time

            # "slide X" 패턴
            for match in re.finditer(r'slide\s*(\d+)', text):
                num = int(match.group(1))
                if 1 <= num <= num_pages:
                    if num not in page_mentions or seg_time < page_mentions[num]:
                        page_mentions[num] = seg_time

        if page_mentions:
            print(f"[{video_id}] 📌 Page 언급 탐지 결과: {len(page_mentions)}개 페이지")
            for page_num in sorted(page_mentions.keys()):
                print(f"[{video_id}]   Page {page_num}: {page_mentions[page_num]:.1f}초")
        else:
            print(f"[{video_id}] ⚠️ Page 언급을 찾지 못함 (키워드 매칭으로 폴백)")

        return page_mentions

    def _extract_keywords_from_page(self, text: str, min_length: int = 4) -> List[str]:
        """페이지 텍스트에서 중요 키워드 추출"""
        # 일반적인 불용어
        stopwords = {
            'the', 'and', 'for', 'that', 'this', 'with', 'from', 'have', 'has',
            'are', 'was', 'were', 'been', 'being', 'will', 'would', 'could',
            'should', 'may', 'might', 'must', 'shall', 'can', 'need', 'does',
            'did', 'done', 'doing', 'just', 'only', 'also', 'very', 'much',
            'more', 'most', 'such', 'like', 'than', 'then', 'when', 'where',
            'which', 'what', 'who', 'whom', 'whose', 'how', 'why', 'all',
            'each', 'every', 'both', 'few', 'many', 'some', 'any', 'other',
            'into', 'through', 'during', 'before', 'after', 'above', 'below',
            'between', 'under', 'again', 'further', 'once', 'here', 'there',
            'about', 'over', 'these', 'those', 'their', 'them', 'they', 'your',
            'page', 'slide', 'copyright', 'reserved', 'rights'
        }

        words = text.split()
        keywords = []

        for word in words:
            if len(word) >= min_length and word not in stopwords:
                keywords.append(word)

        # 중복 제거하면서 순서 유지
        seen = set()
        unique_keywords = []
        for kw in keywords:
            if kw not in seen:
                seen.add(kw)
                unique_keywords.append(kw)

        return unique_keywords[:30]  # 상위 30개 키워드

    def _find_keyword_in_transcript(
        self,
        keyword: str,
        segments: List[Dict],
        search_start: float = 0
    ) -> Optional[float]:
        """트랜스크립트에서 키워드가 처음 등장하는 시간 찾기"""
        keyword_lower = keyword.lower()

        for segment in segments:
            if segment['start'] < search_start:
                continue

            segment_text = segment.get('text', '').lower()
            # 정규화
            segment_text = re.sub(r'[^\w\s]', ' ', segment_text)

            if keyword_lower in segment_text:
                return segment['start']

            # 부분 매칭 (Fuzzy matching)
            for word in segment_text.split():
                if len(word) >= 4:
                    ratio = SequenceMatcher(None, keyword_lower, word).ratio()
                    if ratio > 0.8:  # 80% 이상 유사
                        return segment['start']

        return None

    def _find_best_segment_for_keywords(
        self,
        keywords: List[str],
        segments: List[Dict],
        search_start: float = 0,
        window_size: int = 5
    ) -> tuple[Optional[float], List[str], int]:
        """
        여러 키워드를 검색하여 가장 많은 키워드가 매칭되는 구간 찾기

        Args:
            keywords: 검색할 키워드 목록
            segments: Whisper 세그먼트 목록
            search_start: 검색 시작 시간
            window_size: 연속 세그먼트 윈도우 크기

        Returns:
            (매칭 시간, 매칭된 키워드 목록, 매칭 수)
        """
        if not keywords or not segments:
            return None, [], 0

        best_time = None
        best_matched_keywords = []
        best_match_count = 0

        # 검색 시작 위치 찾기
        start_idx = 0
        for i, seg in enumerate(segments):
            if seg['start'] >= search_start:
                start_idx = i
                break

        # 슬라이딩 윈도우로 연속 세그먼트 검색
        for i in range(start_idx, len(segments)):
            # 윈도우 내 텍스트 결합
            window_end = min(i + window_size, len(segments))
            window_text = ' '.join(
                seg.get('text', '') for seg in segments[i:window_end]
            ).lower()
            window_text = re.sub(r'[^\w\s]', ' ', window_text)
            window_words = set(window_text.split())

            # 키워드 매칭 수 계산
            matched_keywords = []
            for kw in keywords:
                kw_lower = kw.lower()
                # 정확 매칭
                if kw_lower in window_text:
                    matched_keywords.append(kw)
                    continue
                # 부분 매칭 (fuzzy)
                for word in window_words:
                    if len(word) >= 4:
                        ratio = SequenceMatcher(None, kw_lower, word).ratio()
                        if ratio > 0.8:
                            matched_keywords.append(kw)
                            break

            # 최소 2개 이상 매칭되어야 유효한 결과
            if len(matched_keywords) >= 2 and len(matched_keywords) > best_match_count:
                best_match_count = len(matched_keywords)
                best_matched_keywords = matched_keywords
                best_time = segments[i]['start']

        return best_time, best_matched_keywords, best_match_count

    def _compute_semantic_similarity(
        self,
        page_text: str,
        segment_text: str
    ) -> float:
        """두 텍스트 간의 의미적 유사도 계산 (0~1)"""
        if not SENTENCE_TRANSFORMERS_AVAILABLE or self.sentence_model is None:
            return 0.0

        if not page_text.strip() or not segment_text.strip():
            return 0.0

        try:
            embeddings = self.sentence_model.encode([page_text, segment_text])
            # 코사인 유사도 계산
            similarity = np.dot(embeddings[0], embeddings[1]) / (
                np.linalg.norm(embeddings[0]) * np.linalg.norm(embeddings[1])
            )
            return float(max(0, similarity))  # 음수 방지
        except Exception as e:
            print(f"Semantic similarity error: {e}")
            return 0.0

    def _detect_potential_transitions(
        self,
        segments: List[Dict],
        min_pause_seconds: float = 0.5,
        video_id: str = ""
    ) -> List[float]:
        """
        음성 세그먼트 간 자연스러운 전환 지점 감지
        - 긴 휴지(pause) 감지
        - 주제 전환 힌트 단어 감지

        Returns:
            잠재적 전환 지점 시간 목록
        """
        transition_points = []

        # 전환 힌트 단어 (한국어/영어)
        transition_hints = {
            '다음', '그럼', '그래서', '하지만', '그런데', '또한', '먼저', '마지막',
            '첫째', '둘째', '셋째', '결론', '정리하면', '요약하면', '예를들어',
            'next', 'then', 'now', 'first', 'second', 'third', 'finally',
            'however', 'but', 'also', 'let\'s', 'moving'
        }

        for i in range(1, len(segments)):
            prev_seg = segments[i - 1]
            curr_seg = segments[i]

            prev_end = prev_seg.get('end', prev_seg['start'])
            curr_start = curr_seg['start']

            # 휴지 시간 계산
            pause_duration = curr_start - prev_end

            # 현재 세그먼트 텍스트
            curr_text = curr_seg.get('text', '').lower().strip()

            # 전환 점수 계산
            transition_score = 0.0

            # 1. 긴 휴지
            if pause_duration >= min_pause_seconds:
                transition_score += min(pause_duration / 2.0, 0.5)  # 최대 0.5

            # 2. 전환 힌트 단어로 시작
            for hint in transition_hints:
                if curr_text.startswith(hint):
                    transition_score += 0.3
                    break

            # 3. 이전 세그먼트가 문장 종결로 끝남 (. ? !)
            prev_text = prev_seg.get('text', '').strip()
            if prev_text and prev_text[-1] in '.?!다요':
                transition_score += 0.2

            # 일정 점수 이상이면 전환 지점으로 추가
            if transition_score >= 0.4:
                transition_points.append(curr_start)

        return transition_points

    def _find_best_segment_with_semantic(
        self,
        page_text: str,
        keywords: List[str],
        segments: List[Dict],
        search_start: float,
        search_end: float,
        window_seconds: float = 30.0,
        video_id: str = ""
    ) -> tuple[Optional[float], float, int]:
        """
        키워드 매칭과 의미적 유사도를 결합하여 최적의 세그먼트 찾기

        Args:
            page_text: 페이지 전체 텍스트
            keywords: 페이지에서 추출한 키워드 목록
            segments: Whisper 세그먼트 목록
            search_start: 검색 시작 시간
            search_end: 검색 종료 시간
            window_seconds: 윈도우 크기 (초)
            video_id: 로깅용 비디오 ID

        Returns:
            (매칭 시간, 결합 점수, 키워드 매칭 수)
        """
        if not segments:
            return None, 0.0, 0

        best_time = None
        best_score = 0.0
        best_keyword_count = 0

        # 검색 범위 내 세그먼트들을 윈도우로 그룹화
        current_window_start = search_start
        while current_window_start < search_end:
            window_end_time = min(current_window_start + window_seconds, search_end)

            # 윈도우 내 세그먼트 텍스트 수집
            window_segments = []
            window_text_parts = []
            for seg in segments:
                seg_start = seg['start']
                if seg_start >= current_window_start and seg_start < window_end_time:
                    window_segments.append(seg)
                    window_text_parts.append(seg.get('text', ''))

            if not window_segments:
                current_window_start += window_seconds / 2  # 50% 오버랩
                continue

            window_text = ' '.join(window_text_parts).lower()
            window_text_normalized = re.sub(r'[^\w\s]', ' ', window_text)

            # 1. 키워드 매칭 점수 (0~1)
            keyword_matches = 0
            for kw in keywords:
                kw_lower = kw.lower()
                if kw_lower in window_text_normalized:
                    keyword_matches += 1
                else:
                    # Fuzzy 매칭
                    for word in window_text_normalized.split():
                        if len(word) >= 4:
                            ratio = SequenceMatcher(None, kw_lower, word).ratio()
                            if ratio > 0.8:
                                keyword_matches += 1
                                break

            keyword_score = min(keyword_matches / max(len(keywords), 1), 1.0)

            # 2. 의미적 유사도 점수 (0~1)
            semantic_score = self._compute_semantic_similarity(page_text, window_text)

            # 3. 결합 점수 계산 (키워드 80%, 의미적 유사도 20%)
            combined_score = (keyword_score * 0.8) + (semantic_score * 0.2)

            if combined_score > best_score:
                best_score = combined_score
                best_time = window_segments[0]['start']
                best_keyword_count = keyword_matches

            current_window_start += window_seconds / 2  # 50% 오버랩으로 다음 윈도우

        return best_time, best_score, best_keyword_count

    def _find_best_segment_with_position(
        self,
        page_text: str,
        keywords: List[str],
        segments: List[Dict],
        search_start: float,
        search_end: float,
        expected_start: float,
        base_page_duration: float,
        window_seconds: float = 15.0,
        video_id: str = ""
    ) -> tuple[Optional[float], float, int]:
        """
        키워드 매칭 + 의미적 유사도 + 위치 근접도를 결합하여 최적의 세그먼트 찾기

        Args:
            page_text: 페이지 전체 텍스트
            keywords: 페이지에서 추출한 키워드 목록
            segments: Whisper 세그먼트 목록
            search_start: 검색 시작 시간
            search_end: 검색 종료 시간
            expected_start: 예상 시작 시간 (균등 분배 기준)
            base_page_duration: 기본 페이지당 예상 길이
            window_seconds: 윈도우 크기 (초)
            video_id: 로깅용 비디오 ID

        Returns:
            (매칭 시간, 결합 점수, 키워드 매칭 수)
        """
        if not segments:
            return None, 0.0, 0

        best_time = None
        best_score = 0.0
        best_keyword_count = 0

        # 검색 범위 내 세그먼트들을 윈도우로 그룹화
        current_window_start = search_start
        while current_window_start < search_end:
            window_end_time = min(current_window_start + window_seconds, search_end)

            # 윈도우 내 세그먼트 텍스트 수집
            window_segments = []
            window_text_parts = []
            for seg in segments:
                seg_start = seg['start']
                if seg_start >= current_window_start and seg_start < window_end_time:
                    window_segments.append(seg)
                    window_text_parts.append(seg.get('text', ''))

            if not window_segments:
                current_window_start += window_seconds / 2
                continue

            window_text = ' '.join(window_text_parts).lower()
            window_text_normalized = re.sub(r'[^\w\s]', ' ', window_text)

            # 1. 키워드 매칭 점수 (0~1)
            keyword_matches = 0
            for kw in keywords:
                kw_lower = kw.lower()
                if kw_lower in window_text_normalized:
                    keyword_matches += 1
                else:
                    # Fuzzy 매칭
                    for word in window_text_normalized.split():
                        if len(word) >= 4:
                            ratio = SequenceMatcher(None, kw_lower, word).ratio()
                            if ratio > 0.8:
                                keyword_matches += 1
                                break

            keyword_score = min(keyword_matches / max(len(keywords), 1), 1.0)

            # 2. 의미적 유사도 점수 (0~1)
            semantic_score = self._compute_semantic_similarity(page_text, window_text)

            # 3. 위치 근접도 점수 (0~1) - 예상 시작 시간과 가까울수록 높은 점수
            window_time = window_segments[0]['start']
            time_diff = abs(window_time - expected_start)
            # 예상 시간에서 ±1 페이지 길이 내에 있으면 높은 점수
            position_score = max(0, 1.0 - (time_diff / (base_page_duration * 2)))

            # 4. 결합 점수 계산 (키워드 60%, 의미 15%, 위치 25%)
            # 위치 가중치를 높여서 예상 시간 근처 우선
            combined_score = (keyword_score * 0.60) + (semantic_score * 0.15) + (position_score * 0.25)

            if combined_score > best_score:
                best_score = combined_score
                best_time = window_time
                best_keyword_count = keyword_matches

            current_window_start += window_seconds / 2  # 50% 오버랩

        return best_time, best_score, best_keyword_count

    def _encode_video_nvenc(
        self,
        images: List[np.ndarray],
        timings: List[Dict[str, float]],
        audio_path: Optional[str],
        output_path: str,
        fps: int,
        width: int,
        height: int,
        video_id: str,
        cancel_check: callable = None
    ) -> bool:
        """NVENC를 직접 사용하여 영상 인코딩"""

        # ffmpeg 명령어 구성
        ffmpeg_cmd = [
            'ffmpeg', '-y',
            '-f', 'rawvideo',
            '-vcodec', 'rawvideo',
            '-s', f'{width}x{height}',
            '-pix_fmt', 'rgb24',
            '-r', str(fps),
            '-i', '-',
        ]

        if audio_path:
            ffmpeg_cmd.extend(['-i', audio_path])

        ffmpeg_cmd.extend([
            '-c:v', 'h264_nvenc',
            '-preset', 'p4',  # 빠른 프리셋
            '-rc', 'vbr',
            '-cq', '23',
            '-pix_fmt', 'yuv420p',
        ])

        if audio_path:
            ffmpeg_cmd.extend(['-c:a', 'aac', '-b:a', '192k'])
        else:
            ffmpeg_cmd.extend(['-an'])

        ffmpeg_cmd.append(output_path)

        # ffmpeg 프로세스 시작 (새 프로세스 그룹으로)
        process = subprocess.Popen(
            ffmpeg_cmd,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            start_new_session=True  # 취소 시 프로세스 그룹 전체 종료 가능
        )

        # 프로세스 PID 등록 (취소 시 종료를 위해)
        self.register_process_pid(video_id, process.pid)

        # 총 프레임 수 계산
        total_duration = timings[-1]['start'] + timings[-1]['duration'] if timings else 0
        total_frames = int(total_duration * fps)

        print(f"[{video_id}] 🎬 NVENC 인코딩 시작: {total_frames} 프레임, {total_duration:.1f}초")

        # 프레임 생성 및 전송
        frame_count = 0
        current_image_idx = 0

        try:
            for frame_idx in range(total_frames):
                # 취소 확인 (100프레임마다)
                if cancel_check and frame_idx % 100 == 0 and cancel_check():
                    print(f"[{video_id}] ❌ 인코딩 취소됨")
                    process.stdin.close()
                    process.terminate()
                    process.wait()
                    self.clear_process_pid(video_id)
                    # 출력 파일 삭제
                    if os.path.exists(output_path):
                        os.remove(output_path)
                    return False

                t = frame_idx / fps

                # 현재 시간에 해당하는 이미지 찾기
                while current_image_idx < len(timings) - 1:
                    next_start = timings[current_image_idx + 1]['start']
                    if t >= next_start:
                        current_image_idx += 1
                    else:
                        break

                # 이미지 프레임 쓰기
                frame = images[min(current_image_idx, len(images) - 1)]
                process.stdin.write(frame.astype(np.uint8).tobytes())
                frame_count += 1

                # 진행률 업데이트 (5% 단위)
                if frame_count % max(1, total_frames // 20) == 0:
                    progress = int((frame_count / total_frames) * 100)
                    eta = int((total_frames - frame_count) / fps * 0.05)  # NVENC는 매우 빠름
                    self.update_progress(video_id, 'encoding', min(95, 60 + progress * 0.35),
                                       f'🎬 인코딩 중... {progress}%', eta)
                    print(f"[{video_id}] 진행: {progress}% ({frame_count}/{total_frames})")
        except BrokenPipeError:
            # ffmpeg가 일찍 종료됨 - stderr 확인
            stderr = process.stderr.read()
            print(f"[{video_id}] FFmpeg가 조기 종료됨: {stderr.decode()}")
            process.wait()
            return False

        process.stdin.close()
        process.wait()

        # 프로세스 PID 정리
        self.clear_process_pid(video_id)

        stderr_output = process.stderr.read().decode() if process.stderr else ""

        if process.returncode != 0:
            print(f"[{video_id}] FFmpeg 오류 (코드 {process.returncode}): {stderr_output}")
            return False

        print(f"[{video_id}] ✅ NVENC 인코딩 완료: {frame_count} 프레임")
        return True

    def _generate_and_burn_subtitles(
        self,
        video_path: str,
        video_id: str,
        temp_dir: str,
        youtube_service,
        subtitle_lang: str = 'ko',
        subtitle_level: int = 1
    ) -> Optional[str]:
        """AI로 자막을 생성하고 영상에 합성합니다. (동기 함수)

        Args:
            video_path: 원본 영상 경로
            video_id: 비디오 ID (로깅용)
            temp_dir: 임시 디렉토리
            youtube_service: YouTubeService 인스턴스
            subtitle_lang: 자막 언어 ('ko' 또는 'en')
            subtitle_level: 자막 상세도 (1: 키워드, 2: 요약, 3: 전체)

        Returns:
            자막이 합성된 새 영상 경로, 실패 시 None
        """
        try:
            print(f"[{video_id}] 🎤 AI 자막 생성 시작 (언어: {subtitle_lang}, 레벨: {subtitle_level})")

            # 1. 자막 생성 (YouTubeService의 generate_subtitles 사용)
            srt_path = youtube_service.poster.generate_subtitles_with_level(
                video_path,
                lang=subtitle_lang,
                level=subtitle_level
            )

            if not srt_path or not os.path.exists(srt_path):
                print(f"[{video_id}] ⚠️ 자막 파일 생성 실패")
                return None

            print(f"[{video_id}] 📝 자막 파일 생성 완료: {srt_path}")

            # 2. FFmpeg로 자막 합성 (burn-in)
            output_path = os.path.join(temp_dir, f"subtitled_{video_id}.mp4")

            # SRT 파일 경로를 FFmpeg에서 사용할 수 있도록 이스케이프
            srt_escaped = srt_path.replace('\\', '/').replace(':', '\\:')

            cmd = [
                'ffmpeg', '-y',
                '-i', video_path,
                '-vf', f"subtitles='{srt_escaped}':force_style='FontSize=24,PrimaryColour=&HFFFFFF&,OutlineColour=&H000000&,Outline=2,MarginV=50'",
                '-c:v', 'h264_nvenc',
                '-preset', 'p4',
                '-b:v', '8M',
                '-c:a', 'copy',
                output_path
            ]

            print(f"[{video_id}] 🎬 자막 합성 중...")
            result = subprocess.run(cmd, capture_output=True, text=True)

            if result.returncode != 0:
                print(f"[{video_id}] ⚠️ 자막 합성 실패: {result.stderr}")
                # 폴백: CPU 인코딩 시도
                cmd[cmd.index('-c:v') + 1] = 'libx264'
                cmd = [c for c in cmd if c not in ['-preset', 'p4']]
                result = subprocess.run(cmd, capture_output=True, text=True)
                if result.returncode != 0:
                    print(f"[{video_id}] ❌ CPU 인코딩도 실패: {result.stderr}")
                    return None

            # 임시 SRT 파일 삭제
            if os.path.exists(srt_path):
                os.remove(srt_path)

            print(f"[{video_id}] ✅ 자막 합성 완료")
            return output_path

        except Exception as e:
            print(f"[{video_id}] ❌ 자막 생성/합성 오류: {e}")
            import traceback
            traceback.print_exc()
            return None

    def convert_basic_sync(
        self,
        pdf_content: bytes,
        filename: str,
        audio_content: Optional[bytes] = None,
        audio_filename: Optional[str] = None,
        page_duration: float = 5.0,
        transition: str = 'fade',
        transition_duration: float = 0.5,
        width: int = 1920,
        height: int = 1080,
        fps: int = 30,
        dpi: int = 200,
        auto_duration: bool = False,
        logo_path: Optional[str] = None,
        ocr_lang: str = 'korean',
        gen_subtitles: bool = False,
        subtitle_lang: str = 'ko',
        subtitle_level: int = 1,
        youtube_service = None,
        category: str = '',
        created_by: str = ''
    ) -> Dict[str, Any]:
        """Basic 모드: 고정 시간 간격으로 PDF를 영상으로 변환 (동기 버전)

        gen_subtitles: True이면 AI 자막 생성
        subtitle_lang: 자막 언어 (ko, en)
        subtitle_level: 자막 상세도 (1: 키워드, 2: 요약, 3: 전체)
        youtube_service: 자막 생성을 위한 YouTubeService 인스턴스
        category: 영상 카테고리
        created_by: 생성자 이메일
        """
        video_id = str(uuid.uuid4())[:8]
        temp_dir = tempfile.mkdtemp(prefix=f'pdf2mp4_{video_id}_')
        self.register_temp_dir(video_id, temp_dir)

        try:
            print(f"[{video_id}] Starting Basic conversion for: {filename}")

            # 취소 확인 헬퍼 함수
            def check_cancelled():
                if self.is_cancelled(video_id):
                    raise Exception("CANCELLED")

            # 1. PDF를 이미지로 변환
            print(f"[{video_id}] Converting PDF to images (DPI: {dpi})...")
            images = convert_from_bytes(pdf_content, dpi=dpi)
            print(f"[{video_id}] Extracted {len(images)} pages")

            check_cancelled()

            # 로고 이미지 로드
            logo_img = None
            if logo_path and os.path.exists(logo_path):
                logo_img = Image.open(logo_path).convert('RGBA')
                print(f"[{video_id}] Logo loaded: {logo_path}")

            # 2. 이미지 리사이즈 (로고 합성 포함)
            resized_images = []
            for i, img in enumerate(images):
                check_cancelled()
                resized = self._resize_image(img, width, height, logo_img)
                resized_images.append(resized)
                self.update_progress(video_id, 'processing', int(10 + (i / len(images)) * 30),
                                   f'📄 이미지 처리 중... ({i+1}/{len(images)})', None)

            check_cancelled()

            # 2.5. PDF 텍스트 추출 (타이밍 편집기용)
            self.update_progress(video_id, 'text_extract', 35, '📝 텍스트 추출 중...', None)
            page_texts = self._extract_pdf_page_texts(pdf_content)
            total_text_len = sum(len(t) for t in page_texts)
            if total_text_len < 50 and PADDLEOCR_AVAILABLE:
                print(f"[{video_id}] PyPDF2 텍스트 부족 ({total_text_len} 문자), OCR 사용 (lang={ocr_lang})")
                page_texts = self._extract_text_with_ocr(images, video_id, ocr_lang)
            print(f"[{video_id}] 텍스트 추출 완료: {len(page_texts)} 페이지")

            check_cancelled()

            # 3. 오디오 처리
            audio_path = None
            audio_duration = 0
            if audio_content:
                audio_ext = os.path.splitext(audio_filename or '.mp3')[1].lower()
                audio_path = os.path.join(temp_dir, f'audio{audio_ext}')
                with open(audio_path, 'wb') as f:
                    f.write(audio_content)

                # ffprobe로 오디오 길이 확인
                result = subprocess.run(
                    ['ffprobe', '-v', 'error', '-show_entries', 'format=duration',
                     '-of', 'default=noprint_wrappers=1:nokey=1', audio_path],
                    capture_output=True, text=True
                )
                audio_duration = float(result.stdout.strip()) if result.stdout.strip() else 0
                print(f"[{video_id}] Audio loaded: {audio_duration:.2f}s")

                if auto_duration and audio_duration > 0:
                    page_duration = audio_duration / len(images)
                    print(f"[{video_id}] Auto page duration: {page_duration:.2f}s")

            # 4. 타이밍 계산
            timings = []
            for i in range(len(resized_images)):
                start_time = i * page_duration
                timings.append({'start': start_time, 'duration': page_duration})

            # 오디오에 맞게 조정 - 오디오 끝부분이 잘리지 않도록 마진 추가
            if audio_duration > 0:
                total_video_duration = timings[-1]['start'] + timings[-1]['duration']
                # 오디오 길이 + 0.5초 마진으로 비디오 길이 설정 (오디오 끝 잘림 방지)
                target_duration = audio_duration + 0.5
                if target_duration > total_video_duration:
                    # 마지막 이미지 연장
                    timings[-1]['duration'] = target_duration - timings[-1]['start']
                    print(f"[{video_id}] 마지막 슬라이드 연장: {total_video_duration:.1f}초 → {target_duration:.1f}초")

            check_cancelled()

            # 5. 영상 출력
            output_filename = f"{os.path.splitext(filename)[0]}_{video_id}.mp4"
            output_path = os.path.join(self.output_dir, output_filename)
            video_duration = timings[-1]['start'] + timings[-1]['duration']

            print(f"[{video_id}] 🎬 NVENC GPU 가속 인코딩 시작")
            print(f"[{video_id}] 📊 영상 길이: {video_duration:.1f}초")

            success = self._encode_video_nvenc(
                resized_images, timings, audio_path, output_path, fps, width, height, video_id,
                cancel_check=lambda: self.is_cancelled(video_id)
            )

            if self.is_cancelled(video_id):
                raise Exception("CANCELLED")

            if not success:
                raise Exception("NVENC encoding failed")

            # 6. 원본 PDF 저장 (YouTube Poster에서 재사용 가능)
            pdf_filename = f"{os.path.splitext(filename)[0]}_{video_id}.pdf"
            pdf_path = os.path.join(self.pdf_dir, pdf_filename)
            with open(pdf_path, 'wb') as f:
                f.write(pdf_content)
            print(f"[{video_id}] 📄 원본 PDF 저장: {pdf_filename}")

            video_info = {
                'id': video_id,
                'filename': output_filename,
                'original_pdf': filename,
                'pdf_path': pdf_path,
                'mode': 'basic',
                'page_count': len(images),
                'duration': video_duration,
                'resolution': f'{width}x{height}',
                'transition': transition,
                'page_duration': page_duration,
                'created_at': datetime.utcnow().isoformat(),
                'file_path': output_path,
                'file_size': os.path.getsize(output_path)
            }

            # 타이밍 정보를 JSON 파일로 저장 (타이밍 편집기용) - OCR 텍스트 포함
            import json
            timing_file = os.path.join(self.output_dir, f"{video_id}_timing.json")
            timing_data = {
                'timings': timings,
                'page_texts': page_texts if page_texts else []
            }
            with open(timing_file, 'w', encoding='utf-8') as f:
                json.dump(timing_data, f, ensure_ascii=False, indent=2)
            print(f"[{video_id}] 타이밍 정보 저장: {timing_file} (OCR 텍스트 포함)")

            # 메타데이터 파일 저장 (영상 관리용)
            meta_file = os.path.join(self.output_dir, f"{video_id}_meta.json")
            meta_data = {
                'category': category,
                'ocr_lang': ocr_lang,
                'created_by': created_by,
                'duration': video_duration,
                'mode': 'basic',
                'pdf_name': filename,  # 원본 PDF 파일명
                'created_at': datetime.utcnow().isoformat(),
                'stage': 'generated'  # 초기 스테이지: 생성 완료
            }
            with open(meta_file, 'w', encoding='utf-8') as f:
                json.dump(meta_data, f, ensure_ascii=False, indent=2)
            print(f"[{video_id}] 메타데이터 저장: {meta_file}")

            # 7. AI 자막 생성 (옵션)
            if gen_subtitles and youtube_service:
                self.update_progress(video_id, 'subtitles', 90, '🎤 AI 자막 생성 중...', None)
                try:
                    final_output = self._generate_and_burn_subtitles(
                        video_path=output_path,
                        video_id=video_id,
                        temp_dir=temp_dir,
                        youtube_service=youtube_service,
                        subtitle_lang=subtitle_lang,
                        subtitle_level=subtitle_level
                    )
                    if final_output and final_output != output_path:
                        # 자막이 합성된 새 파일로 교체
                        os.remove(output_path)
                        os.rename(final_output, output_path)
                        print(f"[{video_id}] ✅ 자막 합성 완료")
                        video_info['has_subtitles'] = True
                except Exception as sub_err:
                    print(f"[{video_id}] ⚠️ 자막 생성 실패 (영상은 정상): {sub_err}")
                    video_info['subtitle_error'] = str(sub_err)

            print(f"[{video_id}] Conversion completed successfully")
            return {'status': 'success', 'video': video_info}

        except Exception as e:
            error_msg = str(e)
            if error_msg == "CANCELLED":
                print(f"[{video_id}] ❌ 변환 취소됨")
                return {'status': 'cancelled', 'message': '변환이 취소되었습니다.', 'video_id': video_id}
            print(f"[{video_id}] Conversion failed: {error_msg}")
            import traceback
            traceback.print_exc()
            return {'status': 'error', 'message': error_msg}
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)
            self.cleanup_temp_dir(video_id)
            self.clear_cancel(video_id)
            self.clear_process_pid(video_id)

    def convert_smart_sync(
        self,
        pdf_content: bytes,
        filename: str,
        audio_content: bytes,
        audio_filename: str,
        transition: str = 'fade',
        transition_duration: float = 0.5,
        width: int = 1920,
        height: int = 1080,
        fps: int = 30,
        dpi: int = 200,
        logo_path: Optional[str] = None,
        ocr_lang: str = 'korean',
        gen_subtitles: bool = False,
        subtitle_lang: str = 'ko',
        subtitle_level: int = 1,
        youtube_service = None,
        category: str = '',
        created_by: str = '',
        content_id: str = None,
        title: str = None,
        language: str = ''
    ) -> Dict[str, Any]:
        """Smart 모드: Whisper로 오디오 분석, 자동 페이지 타이밍 결정

        gen_subtitles: True이면 AI 자막 생성
        subtitle_lang: 자막 언어 (ko, en)
        subtitle_level: 자막 상세도 (1: 키워드, 2: 요약, 3: 전체)
        youtube_service: 자막 생성을 위한 YouTubeService 인스턴스
        category: 영상 카테고리
        created_by: 생성자 이메일
        content_id: 통합 콘텐츠 ID (파이프라인에서 전달, 없으면 자동 생성)
        title: 영상 제목 (파일명으로 사용, 없으면 기존 방식 사용)
        language: 콘텐츠 언어 (ko, en)
        """
        if not WHISPER_AVAILABLE:
            return {
                'status': 'error',
                'message': 'Whisper not installed. Smart mode requires openai-whisper package.'
            }

        if not audio_content:
            return {
                'status': 'error',
                'message': 'Smart mode requires an audio file.'
            }

        # content_id가 있으면 사용, 없으면 PDF 파일명에서 추출 시도
        actual_content_id = content_id
        if not actual_content_id:
            # PDF 파일명에서 pipe_ 패턴 추출 시도
            import re
            pipe_match = re.match(r'^(pipe_\d{8}_[a-f0-9]{8})(?:\.pdf)?', filename)
            if pipe_match:
                actual_content_id = pipe_match.group(1)

        # video_id는 항상 고유하게 생성 (timestamp 기반)
        video_id = str(int(datetime.utcnow().timestamp() * 100) % 100000000)
        temp_dir = tempfile.mkdtemp(prefix=f'pdf2mp4_smart_{video_id}_')
        self.register_temp_dir(video_id, temp_dir)

        try:
            print(f"[{video_id}] Starting Smart conversion for: {filename}")
            self.update_progress(video_id, 'init', 0, '변환 시작...', None)

            # 취소 확인 헬퍼 함수
            def check_cancelled():
                if self.is_cancelled(video_id):
                    raise Exception("CANCELLED")

            # 1. 오디오 파일 저장 및 전사
            audio_ext = os.path.splitext(audio_filename)[1].lower()
            audio_path = os.path.join(temp_dir, f'audio{audio_ext}')
            with open(audio_path, 'wb') as f:
                f.write(audio_content)

            check_cancelled()
            self.update_progress(video_id, 'whisper', 10, '🎤 Whisper로 오디오 분석 중...', None)
            print(f"[{video_id}] Transcribing audio with Whisper...")
            result = self.whisper_model.transcribe(audio_path)
            transcript_text = result.get('text', '')
            segments = result.get('segments', [])
            print(f"[{video_id}] Transcription complete: {len(segments)} segments")
            self.update_progress(video_id, 'whisper_done', 30, f'✅ 오디오 분석 완료 ({len(segments)}개 세그먼트)', None)

            check_cancelled()
            # 2. PDF를 이미지로 변환
            self.update_progress(video_id, 'pdf', 35, '📄 PDF를 이미지로 변환 중...', None)
            print(f"[{video_id}] Converting PDF to images...")
            images = convert_from_bytes(pdf_content, dpi=dpi)
            num_pages = len(images)
            print(f"[{video_id}] Extracted {num_pages} pages")
            self.update_progress(video_id, 'pdf_done', 40, f'✅ PDF 변환 완료 ({num_pages}페이지)', None)

            # 3. PDF 텍스트 추출 (키워드 매칭용)
            self.update_progress(video_id, 'text_extract', 42, '📝 PDF 텍스트 추출 중...', None)
            print(f"[{video_id}] Extracting text from PDF pages...")
            page_texts = self._extract_pdf_page_texts(pdf_content)

            # PyPDF2가 실패했거나 텍스트가 부족하면 OCR 사용
            total_text_len = sum(len(t) for t in page_texts)
            if total_text_len < 50 and PADDLEOCR_AVAILABLE:
                print(f"[{video_id}] PyPDF2 텍스트 부족 ({total_text_len} 문자), OCR 사용 (lang={ocr_lang})")
                self.update_progress(video_id, 'ocr', 43, '🔍 OCR로 텍스트 추출 중...', None)
                page_texts = self._extract_text_with_ocr(images, video_id, ocr_lang)

            print(f"[{video_id}] Extracted text from {len(page_texts)} pages (총 {sum(len(t) for t in page_texts)} 문자)")

            check_cancelled()

            # 3.5. 영문 키워드를 한국어로 번역 (매칭 정확도 향상)
            # 한글+영문 혼합 문서에서 영문 기술 용어를 번역하여 매칭률 향상
            page_texts_for_matching = page_texts  # 원본 보존 (타이밍 편집기용)
            if page_texts and TRANSLATOR_AVAILABLE:
                self.update_progress(video_id, 'translate', 44, '🌐 영문 키워드 한국어 번역 중...', None)
                page_texts_for_matching = self._translate_english_keywords_to_korean(page_texts, video_id)
                print(f"[{video_id}] 번역된 키워드가 추가된 텍스트를 매칭에 사용")

            check_cancelled()

            # 로고 이미지 로드
            logo_img = None
            if logo_path and os.path.exists(logo_path):
                logo_img = Image.open(logo_path).convert('RGBA')
                print(f"[{video_id}] Logo loaded: {logo_path}")

            # 4. 이미지 리사이즈 (로고 합성 포함)
            resized_images = []
            for i, img in enumerate(images):
                check_cancelled()
                resized = self._resize_image(img, width, height, logo_img)
                resized_images.append(resized)
                self.update_progress(video_id, 'processing', int(45 + (i / len(images)) * 10),
                                   f'📄 이미지 처리 중... ({i+1}/{len(images)})', None)

            # 5. 오디오 길이 확인
            result_probe = subprocess.run(
                ['ffprobe', '-v', 'error', '-show_entries', 'format=duration',
                 '-of', 'default=noprint_wrappers=1:nokey=1', audio_path],
                capture_output=True, text=True
            )
            total_duration = float(result_probe.stdout.strip()) if result_probe.stdout.strip() else 0

            # 6. 페이지 타이밍 계산 (키워드 기반) - 번역된 텍스트 사용
            self.update_progress(video_id, 'timing', 45, '🔍 키워드 기반 타이밍 계산 중...', None)
            page_timings = self._calculate_smart_timings(
                segments, num_pages, total_duration, page_texts_for_matching, video_id
            )
            print(f"[{video_id}] Page timings: {page_timings}")
            self.update_progress(video_id, 'timing_done', 50, '⏱️ 페이지 타이밍 계산 완료', None)

            # 6. 마지막 페이지 연장 (오디오 끝까지 + 마진) - 오디오 끝부분 잘림 방지
            audio_margin = 0.5  # 오디오 끝 잘림 방지 마진
            target_duration = total_duration + audio_margin
            if page_timings:
                last_end = page_timings[-1]['start'] + page_timings[-1]['duration']
                if last_end < target_duration:
                    page_timings[-1]['duration'] = target_duration - page_timings[-1]['start']
                    print(f"[{video_id}] 마지막 슬라이드 연장: {last_end:.1f}초 → {target_duration:.1f}초")

            # 7. 영상 출력
            # 제목이 있으면 제목으로 파일명 생성, 없으면 기존 방식
            if title:
                # 파일명에 사용할 수 없는 문자 제거
                import re
                safe_title = re.sub(r'[\\/*?:"<>|]', '', title)
                safe_title = safe_title.strip()[:100]  # 최대 100자
                output_filename = f"{safe_title}_{video_id}.mp4"
            else:
                # filename에서 확장자 제거한 base_name
                base_name = os.path.splitext(filename)[0]
                # base_name과 video_id가 같으면 중복 방지
                if base_name == video_id:
                    output_filename = f"{video_id}.mp4"
                else:
                    output_filename = f"{base_name}_smart_{video_id}.mp4"
            output_path = os.path.join(self.output_dir, output_filename)

            video_duration = page_timings[-1]['start'] + page_timings[-1]['duration'] if page_timings else 0
            eta_seconds = int(video_duration * 0.05)  # NVENC는 빠름
            self.update_progress(video_id, 'encoding', 55, f'🎬 NVENC 인코딩 중... (예상 {eta_seconds}초)', eta_seconds)

            check_cancelled()

            print(f"[{video_id}] 🎬 NVENC GPU 가속 인코딩 시작")
            print(f"[{video_id}] 📊 영상 길이: {video_duration:.1f}초")

            success = self._encode_video_nvenc(
                resized_images, page_timings, audio_path, output_path, fps, width, height, video_id,
                cancel_check=lambda: self.is_cancelled(video_id)
            )

            if self.is_cancelled(video_id):
                raise Exception("CANCELLED")

            if not success:
                raise Exception("NVENC encoding failed")

            # 6. 원본 PDF 저장 (YouTube Poster에서 재사용 가능)
            # content_id가 전달된 경우 (파이프라인), PDF는 이미 저장되어 있으므로 중복 저장 방지
            if content_id:
                # 파이프라인에서 이미 생성된 PDF 경로 사용
                pdf_filename = f"{content_id}.pdf"
                pdf_path = os.path.join(self.pdf_dir, pdf_filename)
                if not os.path.exists(pdf_path):
                    # PDF가 없으면 저장
                    with open(pdf_path, 'wb') as f:
                        f.write(pdf_content)
                    print(f"[{video_id}] 📄 원본 PDF 저장: {pdf_filename}")
                else:
                    print(f"[{video_id}] 📄 기존 PDF 사용: {pdf_filename}")
            else:
                # 기존 방식: filename에서 추출
                pdf_filename = f"{os.path.splitext(filename)[0]}_{video_id}.pdf"
                pdf_path = os.path.join(self.pdf_dir, pdf_filename)
                with open(pdf_path, 'wb') as f:
                    f.write(pdf_content)
                print(f"[{video_id}] 📄 원본 PDF 저장: {pdf_filename}")

            self.update_progress(video_id, 'complete', 100, '✅ 변환 완료!', 0)

            video_info = {
                'id': video_id,
                'content_id': actual_content_id or video_id,  # 파이프라인 콘텐츠 ID
                'filename': output_filename,
                'original_pdf': filename,
                'pdf_path': pdf_path,
                'mode': 'smart',
                'page_count': num_pages,
                'duration': video_duration,
                'resolution': f'{width}x{height}',
                'transition': transition,
                'page_timings': page_timings,
                'transcript_preview': transcript_text[:500] if transcript_text else None,
                'created_at': datetime.utcnow().isoformat(),
                'file_path': output_path,
                'file_size': os.path.getsize(output_path)
            }

            # 타이밍 정보를 JSON 파일로 저장 (타이밍 편집기용) - OCR 텍스트 포함
            import json
            timing_file = os.path.join(self.output_dir, f"{video_id}_timing.json")
            # Whisper 세그먼트를 간소화하여 저장 (타이밍 편집기용)
            simplified_segments = []
            for seg in segments:
                simplified_segments.append({
                    'start': round(seg.get('start', 0), 2),
                    'end': round(seg.get('end', 0), 2),
                    'text': seg.get('text', '').strip()
                })

            timing_data = {
                'content_id': actual_content_id or video_id,  # 파이프라인 콘텐츠 ID
                'video_id': video_id,  # 고유 영상 ID
                'timings': page_timings,
                'page_texts': page_texts if page_texts else [],
                'transcript_segments': simplified_segments  # Whisper 세그먼트 추가
            }
            with open(timing_file, 'w', encoding='utf-8') as f:
                json.dump(timing_data, f, ensure_ascii=False, indent=2)
            print(f"[{video_id}] 타이밍 정보 저장: {timing_file} (OCR 텍스트 + Whisper 세그먼트 포함)")

            # 메타데이터 파일 저장 (영상 관리용)
            meta_file = os.path.join(self.output_dir, f"{video_id}_meta.json")
            meta_data = {
                'content_id': actual_content_id or video_id,  # 파이프라인 콘텐츠 ID (제목/플랜 연결용)
                'category': category,
                'ocr_lang': ocr_lang,
                'language': language,  # 콘텐츠 언어
                'created_by': created_by,
                'duration': video_duration,
                'mode': 'smart',
                'pdf_name': filename,  # 원본 PDF 파일명
                'created_at': datetime.utcnow().isoformat(),
                'stage': 'generated'  # 초기 스테이지: 생성 완료
            }
            with open(meta_file, 'w', encoding='utf-8') as f:
                json.dump(meta_data, f, ensure_ascii=False, indent=2)
            print(f"[{video_id}] 메타데이터 저장: {meta_file}")

            # 7. AI 자막 생성 (옵션)
            if gen_subtitles and youtube_service:
                self.update_progress(video_id, 'subtitles', 95, '🎤 AI 자막 생성 중...', None)
                try:
                    final_output = self._generate_and_burn_subtitles(
                        video_path=output_path,
                        video_id=video_id,
                        temp_dir=temp_dir,
                        youtube_service=youtube_service,
                        subtitle_lang=subtitle_lang,
                        subtitle_level=subtitle_level
                    )
                    if final_output and final_output != output_path:
                        # 자막이 합성된 새 파일로 교체
                        os.remove(output_path)
                        os.rename(final_output, output_path)
                        print(f"[{video_id}] ✅ 자막 합성 완료")
                        video_info['has_subtitles'] = True
                except Exception as sub_err:
                    print(f"[{video_id}] ⚠️ 자막 생성 실패 (영상은 정상): {sub_err}")
                    video_info['subtitle_error'] = str(sub_err)

            print(f"[{video_id}] Smart conversion completed successfully")
            return {'status': 'success', 'video': video_info}

        except Exception as e:
            error_msg = str(e)
            if error_msg == "CANCELLED":
                print(f"[{video_id}] ❌ Smart 변환 취소됨")
                return {'status': 'cancelled', 'message': '변환이 취소되었습니다.', 'video_id': video_id}
            print(f"[{video_id}] Smart conversion failed: {error_msg}")
            import traceback
            traceback.print_exc()
            return {'status': 'error', 'message': error_msg}
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)
            self.cleanup_temp_dir(video_id)
            self.clear_cancel(video_id)
            self.clear_process_pid(video_id)

    # Async 래퍼 (하위 호환성)
    async def convert_basic(self, **kwargs):
        """Basic 모드 변환 (async 래퍼)"""
        import asyncio
        return await asyncio.to_thread(self.convert_basic_sync, **kwargs)

    async def convert_smart(self, **kwargs):
        """Smart 모드 변환 (async 래퍼)"""
        import asyncio
        return await asyncio.to_thread(self.convert_smart_sync, **kwargs)

    def _calculate_smart_timings(
        self,
        segments: List[Dict],
        num_pages: int,
        total_duration: float,
        page_texts: Optional[List[str]] = None,
        video_id: str = ""
    ) -> List[Dict[str, float]]:
        """PDF 페이지 키워드와 Whisper 트랜스크립트를 매칭하여 페이지 타이밍 계산

        개선된 알고리즘 v4 (하이브리드 + 전환점 감지):
        1. 우선순위 1: "Page X" 언급 탐지 (신뢰도 95%)
        2. 우선순위 2: 자연스러운 전환점 감지 (휴지, 힌트 단어)
        3. 우선순위 3: 키워드 + 의미적 유사도 매칭
        4. 앵커 포인트 기반 구간 분할 및 보간
        5. 순차적 제약 조건 유지 (페이지 순서 보장)
        """

        # 기본 폴백: 균등 분배
        if not segments or num_pages <= 0:
            page_duration = total_duration / max(num_pages, 1)
            return [
                {'start': i * page_duration, 'duration': page_duration}
                for i in range(num_pages)
            ]

        # 텍스트가 없으면 균등 분배
        if not page_texts or len(page_texts) != num_pages:
            print(f"[{video_id}] 텍스트 없음 - 균등 분배 사용")
            return self._calculate_equal_timings(segments, num_pages, total_duration)

        print(f"[{video_id}] 🔍 하이브리드 페이지 매칭 시작 (v4: Page언급 + 전환점 + 키워드 + 의미)")

        # 디버그: Whisper 세그먼트 샘플
        print(f"[{video_id}] 📝 Whisper 세그먼트 샘플:")
        for seg in segments[:5]:
            print(f"[{video_id}]   [{seg['start']:.1f}s] {seg.get('text', '')[:80]}")

        # ========== 0단계: 잠재적 전환점 감지 ==========
        transition_points = self._detect_potential_transitions(segments, min_pause_seconds=0.4, video_id=video_id)
        print(f"[{video_id}] 🔄 잠재적 전환점: {len(transition_points)}개 감지")
        if transition_points[:10]:
            print(f"[{video_id}]   처음 10개: {[f'{t:.1f}s' for t in transition_points[:10]]}")

        # ========== 1단계: Page 언급 탐지 (최우선) ==========
        page_mentions = self._find_page_mentions_in_transcript(segments, num_pages, video_id)

        # ========== 2단계: 키워드 추출 ==========
        page_keywords = []
        print(f"[{video_id}] 📄 페이지별 키워드:")
        for i, pt in enumerate(page_texts):
            kws = self._extract_keywords_from_page(pt)
            page_keywords.append(kws)
            if i < 3:
                print(f"[{video_id}]   페이지 {i+1}: {kws[:10]}")

        # 기본 설정
        base_page_duration = total_duration / num_pages
        min_page_duration = 3.0

        # ========== 3단계: 앵커 포인트 설정 ==========
        # Page 언급이 있는 페이지를 앵커로 사용
        # 첫 페이지는 항상 0초 (앵커)
        anchors = {1: 0.0}  # {page_num: start_time}
        anchor_confidences = {1: 1.0}

        # Page 언급을 앵커에 추가
        for page_num, mention_time in page_mentions.items():
            anchors[page_num] = mention_time
            anchor_confidences[page_num] = 0.95  # 높은 신뢰도

        print(f"[{video_id}] ⚓ 앵커 포인트: {len(anchors)}개 (Page 1 + Page 언급 {len(page_mentions)}개)")

        # ========== 4단계: 나머지 페이지 키워드/의미 매칭 ==========
        use_semantic = SENTENCE_TRANSFORMERS_AVAILABLE and self.sentence_model is not None
        if use_semantic:
            print(f"[{video_id}] ✅ Semantic similarity 활성화")
        else:
            print(f"[{video_id}] ⚠️ Semantic similarity 비활성화")

        # 앵커가 없는 페이지들에 대해 키워드 매칭 시도
        for page_idx in range(1, num_pages):
            page_num = page_idx + 1  # 1-indexed

            # 이미 앵커가 있으면 스킵
            if page_num in anchors:
                continue

            page_text = page_texts[page_idx]
            keywords = page_keywords[page_idx]

            # 이 페이지 앞뒤의 가장 가까운 앵커 찾기
            prev_anchor_page = max([p for p in anchors.keys() if p < page_num], default=1)
            next_anchor_page = min([p for p in anchors.keys() if p > page_num], default=num_pages + 1)

            prev_anchor_time = anchors[prev_anchor_page]
            next_anchor_time = anchors.get(next_anchor_page, total_duration)

            # 검색 범위: 앵커 사이
            search_start = prev_anchor_time + min_page_duration
            search_end = next_anchor_time - min_page_duration

            if search_start >= search_end:
                continue  # 보간으로 처리

            best_time = None
            best_score = 0.0
            match_info = ""

            # 의미적 유사도 + 키워드 매칭 (위치 가중치 제거)
            if use_semantic and page_text.strip():
                match_time, score, kw_count = self._find_best_segment_semantic_only(
                    page_text,
                    keywords[:20],
                    segments,
                    search_start,
                    search_end,
                    window_seconds=20.0,
                    video_id=video_id
                )

                if match_time is not None and score > 0.15:
                    best_time = match_time
                    best_score = score
                    match_info = f"semantic+kw (score={score:.2f}, kw={kw_count})"

            # 키워드만 매칭
            if best_time is None and keywords:
                multi_match_time, matched_kws, match_count = self._find_best_segment_for_keywords(
                    keywords[:20],
                    segments,
                    search_start=search_start,
                    window_size=5
                )

                if multi_match_time is not None and search_start <= multi_match_time <= search_end:
                    if match_count >= 2:
                        best_time = multi_match_time
                        best_score = match_count / len(keywords) if keywords else 0.0
                        match_info = f"keyword ({match_count}개)"

            if best_time is not None:
                # 가장 가까운 전환점으로 스냅 (±3초 이내)
                snapped_time = best_time
                for tp in transition_points:
                    if search_start <= tp <= search_end:
                        if abs(tp - best_time) <= 3.0:
                            snapped_time = tp
                            break

                anchors[page_num] = snapped_time
                anchor_confidences[page_num] = min(best_score, 0.7)  # 최대 70% 신뢰도
                if snapped_time != best_time:
                    print(f"[{video_id}]   페이지 {page_num}: {match_info} @ {best_time:.1f}초 → 전환점 {snapped_time:.1f}초")
                else:
                    print(f"[{video_id}]   페이지 {page_num}: {match_info} @ {best_time:.1f}초")

        # ========== 5단계: 앵커 기반 보간 ==========
        page_start_times = self._interpolate_from_anchors(
            anchors, num_pages, total_duration, min_page_duration, video_id
        )

        # ========== 6단계: 순차 정렬 보장 ==========
        page_start_times = self._ensure_sequential_order(
            page_start_times, min_page_duration, total_duration, video_id
        )

        # 타이밍 생성
        timings = []
        for i in range(num_pages):
            start_time = page_start_times[i]
            if i < num_pages - 1:
                end_time = page_start_times[i + 1]
            else:
                end_time = total_duration

            timings.append({
                'start': start_time,
                'duration': max(end_time - start_time, min_page_duration)
            })

        return timings

    def _find_best_segment_semantic_only(
        self,
        page_text: str,
        keywords: List[str],
        segments: List[Dict],
        search_start: float,
        search_end: float,
        window_seconds: float = 20.0,
        video_id: str = ""
    ) -> tuple[Optional[float], float, int]:
        """
        키워드 + 의미적 유사도만 사용 (위치 가중치 제외)
        """
        if not segments:
            return None, 0.0, 0

        best_time = None
        best_score = 0.0
        best_keyword_count = 0

        current_window_start = search_start
        while current_window_start < search_end:
            window_end_time = min(current_window_start + window_seconds, search_end)

            window_segments = []
            window_text_parts = []
            for seg in segments:
                seg_start = seg['start']
                if seg_start >= current_window_start and seg_start < window_end_time:
                    window_segments.append(seg)
                    window_text_parts.append(seg.get('text', ''))

            if not window_segments:
                current_window_start += window_seconds / 2
                continue

            window_text = ' '.join(window_text_parts).lower()
            window_text_normalized = re.sub(r'[^\w\s]', ' ', window_text)

            # 키워드 매칭 점수
            keyword_matches = 0
            for kw in keywords:
                kw_lower = kw.lower()
                if kw_lower in window_text_normalized:
                    keyword_matches += 1
                else:
                    for word in window_text_normalized.split():
                        if len(word) >= 4:
                            ratio = SequenceMatcher(None, kw_lower, word).ratio()
                            if ratio > 0.8:
                                keyword_matches += 1
                                break

            keyword_score = min(keyword_matches / max(len(keywords), 1), 1.0)

            # 의미적 유사도 점수
            semantic_score = self._compute_semantic_similarity(page_text, window_text)

            # 결합 점수 (키워드 70%, 의미 30% - 위치 가중치 제거)
            combined_score = (keyword_score * 0.70) + (semantic_score * 0.30)

            if combined_score > best_score:
                best_score = combined_score
                best_time = window_segments[0]['start']
                best_keyword_count = keyword_matches

            current_window_start += window_seconds / 2

        return best_time, best_score, best_keyword_count

    def _interpolate_from_anchors(
        self,
        anchors: Dict[int, float],
        num_pages: int,
        total_duration: float,
        min_page_duration: float,
        video_id: str = ""
    ) -> List[float]:
        """
        앵커 포인트를 기반으로 나머지 페이지 시간 보간
        """
        page_start_times = [None] * num_pages

        # 앵커 값 설정
        for page_num, start_time in anchors.items():
            if 1 <= page_num <= num_pages:
                page_start_times[page_num - 1] = start_time

        # 첫 페이지 보장
        if page_start_times[0] is None:
            page_start_times[0] = 0.0

        # 마지막 페이지 앵커 추가 (총 영상 길이)
        sorted_anchors = sorted(anchors.keys())
        if num_pages not in anchors:
            # 마지막 앵커 이후 남은 시간을 마지막 페이지들에 분배
            pass

        # 보간 수행
        print(f"[{video_id}] 📊 앵커 기반 보간:")

        # 각 구간별로 보간
        i = 0
        while i < num_pages:
            if page_start_times[i] is not None:
                # 앵커 포인트 찾음
                anchor_start_idx = i
                anchor_start_time = page_start_times[i]

                # 다음 앵커 찾기
                j = i + 1
                while j < num_pages and page_start_times[j] is None:
                    j += 1

                if j < num_pages:
                    # 다음 앵커까지 보간
                    anchor_end_idx = j
                    anchor_end_time = page_start_times[j]
                else:
                    # 마지막까지 보간
                    anchor_end_idx = num_pages
                    anchor_end_time = total_duration

                # 구간 내 페이지들 균등 보간
                pages_in_range = anchor_end_idx - anchor_start_idx
                time_range = anchor_end_time - anchor_start_time

                for k in range(anchor_start_idx + 1, anchor_end_idx):
                    ratio = (k - anchor_start_idx) / pages_in_range
                    page_start_times[k] = anchor_start_time + (time_range * ratio)

                i = j
            else:
                i += 1

        # None이 남아있으면 균등 분배
        for i in range(num_pages):
            if page_start_times[i] is None:
                page_start_times[i] = (i / num_pages) * total_duration

        return page_start_times

    def _ensure_sequential_order(
        self,
        page_start_times: List[float],
        min_page_duration: float,
        total_duration: float,
        video_id: str = ""
    ) -> List[float]:
        """
        페이지 시작 시간이 순차적으로 증가하도록 보장
        """
        result = page_start_times.copy()

        # 순방향 검사: 이전 페이지보다 늦게 시작하도록
        for i in range(1, len(result)):
            min_start = result[i - 1] + min_page_duration
            if result[i] < min_start:
                result[i] = min_start

        # 역방향 검사: 마지막 페이지가 총 시간을 넘지 않도록
        if result[-1] > total_duration - min_page_duration:
            result[-1] = total_duration - min_page_duration

            # 역방향으로 조정
            for i in range(len(result) - 2, -1, -1):
                max_start = result[i + 1] - min_page_duration
                if result[i] > max_start:
                    result[i] = max(0, max_start)

        return result

    def _calculate_equal_timings(
        self,
        segments: List[Dict],
        num_pages: int,
        total_duration: float
    ) -> List[Dict[str, float]]:
        """세그먼트 균등 분배 방식 (폴백)"""
        segment_count = len(segments)
        segments_per_page = max(1, segment_count // num_pages)

        timings = []
        for i in range(num_pages):
            start_idx = i * segments_per_page
            end_idx = min(start_idx + segments_per_page, segment_count)

            if i == num_pages - 1:
                end_idx = segment_count

            if start_idx < segment_count:
                start_time = segments[start_idx]['start']
                if end_idx < segment_count:
                    end_time = segments[end_idx]['start']
                else:
                    end_time = total_duration

                timings.append({
                    'start': start_time,
                    'duration': end_time - start_time
                })
            else:
                if timings:
                    last_end = timings[-1]['start'] + timings[-1]['duration']
                    remaining = total_duration - last_end
                    pages_left = num_pages - i
                    duration = remaining / pages_left
                    timings.append({
                        'start': last_end,
                        'duration': duration
                    })

        return timings

    def _interpolate_missing_times(
        self,
        page_start_times: List[Optional[float]],
        total_duration: float,
        min_duration: float,
        video_id: str
    ) -> List[float]:
        """매칭되지 않은 페이지 시간을 보간"""
        result = page_start_times.copy()
        num_pages = len(result)

        # None 값들을 선형 보간
        i = 0
        while i < num_pages:
            if result[i] is None:
                # None 시퀀스의 시작과 끝 찾기
                start_idx = i
                while i < num_pages and result[i] is None:
                    i += 1
                end_idx = i

                # 보간을 위한 시작/끝 시간 결정
                if start_idx == 0:
                    prev_time = 0.0
                else:
                    prev_time = result[start_idx - 1]

                if end_idx >= num_pages:
                    next_time = total_duration
                else:
                    next_time = result[end_idx]

                # 선형 보간
                gap_count = end_idx - start_idx + 1
                time_step = (next_time - prev_time) / gap_count

                for j in range(start_idx, end_idx):
                    result[j] = prev_time + time_step * (j - start_idx + 1)
                    print(f"[{video_id}]   페이지 {j + 1}: (보간) @ {result[j]:.1f}초")
            else:
                i += 1

        # 최소 간격 보장
        for i in range(1, num_pages):
            if result[i] < result[i-1] + min_duration:
                result[i] = result[i-1] + min_duration

        return result

    def get_video_list(self) -> List[Dict[str, Any]]:
        """생성된 영상 목록 조회"""
        import re
        videos = []
        if os.path.exists(self.output_dir):
            for f in os.listdir(self.output_dir):
                if f.endswith('.mp4'):
                    path = os.path.join(self.output_dir, f)

                    # video_id 추출 로직 개선
                    # 1. Smart 모드 형식: pipe_YYYYMMDD_xxxxxxxx_smart_XXXXXXXX.mp4 -> XXXXXXXX
                    # 2. 파이프라인 형식 (파일명 중간에 pipe_가 있는 경우): 【제목】_pipe_YYYYMMDD_xxxxxxxx.mp4
                    # 3. 파이프라인 형식 (파일명 시작이 pipe_인 경우): pipe_YYYYMMDD_xxxxxxxx.mp4
                    # 4. 일반 형식: filename_xxxxxxxx.mp4

                    # Smart 모드 형식 확인: pipe_로 시작하고 _smart_가 포함된 경우
                    smart_mode_match = re.match(r'^pipe_\d{8}_[a-f0-9]{8}_smart_(\d+)\.mp4$', f)
                    # 파일명 중간에 _pipe_ 패턴이 있는지 확인 (제목_pipe_날짜_ID 형식)
                    pipe_middle_match = re.search(r'_(pipe_\d{8}_[a-f0-9]{8})(?:\.mp4|_)', f)
                    # 파일명 시작이 pipe_인 경우 (smart가 아닌 경우만)
                    pipe_start_match = re.match(r'^(pipe_\d{8}_[a-f0-9]{8})(?:\.mp4)$', f)

                    if smart_mode_match:
                        video_id = smart_mode_match.group(1)
                    elif pipe_middle_match:
                        video_id = pipe_middle_match.group(1)
                    elif pipe_start_match:
                        video_id = pipe_start_match.group(1)
                    else:
                        parts = f.rsplit('_', 1)
                        video_id = parts[1].replace('.mp4', '') if len(parts) > 1 else f.replace('.mp4', '')

                    video_data = {
                        'id': video_id,
                        'filename': f,
                        'file_path': path,
                        'file_size': os.path.getsize(path),
                        'created_at': datetime.fromtimestamp(os.path.getctime(path)).isoformat()
                    }

                    # 타이밍 JSON 파일에서 추가 정보 로드 (duration 계산)
                    timing_file = os.path.join(self.output_dir, f"{video_id}_timing.json")
                    if os.path.exists(timing_file):
                        try:
                            import json
                            with open(timing_file, 'r', encoding='utf-8') as tf:
                                timing_data = json.load(tf)
                                timings = timing_data.get('timings', [])
                                if timings:
                                    last_timing = timings[-1]
                                    video_data['duration'] = last_timing.get('start', 0) + last_timing.get('duration', 0)
                                # 메타데이터 로드
                                video_data['category'] = timing_data.get('category', '')
                                video_data['ocr_lang'] = timing_data.get('ocr_lang', '')
                                video_data['created_by'] = timing_data.get('created_by', '')
                        except Exception as e:
                            print(f"Error loading timing file for {video_id}: {e}")

                    # 메타데이터 JSON 파일에서 추가 정보 로드
                    meta_file = os.path.join(self.output_dir, f"{video_id}_meta.json")
                    if os.path.exists(meta_file):
                        try:
                            import json
                            with open(meta_file, 'r', encoding='utf-8') as mf:
                                meta_data = json.load(mf)
                                video_data['category'] = meta_data.get('category', video_data.get('category', ''))
                                video_data['ocr_lang'] = meta_data.get('ocr_lang', video_data.get('ocr_lang', ''))
                                video_data['language'] = meta_data.get('language', video_data.get('language', ''))
                                video_data['created_by'] = meta_data.get('created_by', video_data.get('created_by', ''))
                                video_data['duration'] = meta_data.get('duration', video_data.get('duration', 0))
                                video_data['pdf_name'] = meta_data.get('pdf_name', '')
                                video_data['stage'] = meta_data.get('stage', '')
                                video_data['content_id'] = meta_data.get('content_id', video_id)
                        except Exception as e:
                            print(f"Error loading meta file for {video_id}: {e}")

                    # PDF 메타데이터에서 language, title 가져오기
                    content_id = video_data.get('content_id', video_id)
                    pdf_meta_file = os.path.join(self.pdf_dir, f"{content_id}.json")
                    if os.path.exists(pdf_meta_file):
                        try:
                            with open(pdf_meta_file, 'r', encoding='utf-8') as pf:
                                pdf_meta = json.load(pf)
                                video_data['language'] = pdf_meta.get('language', '')
                                video_data['title'] = pdf_meta.get('title', '')
                        except Exception as e:
                            print(f"Error loading PDF meta for {content_id}: {e}")

                    # 기획안에서 추가 정보 가져오기 (메타 파일에 없는 경우)
                    plan_file = os.path.join(os.path.dirname(self.output_dir), 'generated_content', f"plan_{content_id}.json")
                    if os.path.exists(plan_file):
                        try:
                            with open(plan_file, 'r', encoding='utf-8') as plf:
                                plan_data = json.load(plf)
                                if not video_data.get('title'):
                                    video_data['title'] = plan_data.get('title', '')
                                if not video_data.get('language'):
                                    video_data['language'] = plan_data.get('language', '')
                                if not video_data.get('category'):
                                    video_data['category'] = plan_data.get('category', '')
                                if not video_data.get('created_by'):
                                    video_data['created_by'] = plan_data.get('created_by', '')
                        except Exception as e:
                            print(f"Error loading plan for {content_id}: {e}")

                    # 메타 파일이 없는 경우 파일명에서 PDF 이름 추출 시도
                    if not video_data.get('pdf_name'):
                        # 파일명 형식: "PDF이름_VideoID.mp4"
                        if len(parts) > 1:
                            pdf_base_name = parts[0]  # PDF이름 부분
                            video_data['pdf_name'] = pdf_base_name + '.pdf'

                    videos.append(video_data)

        return sorted(videos, key=lambda x: x['created_at'], reverse=True)

    def get_video_path(self, video_id: str) -> Optional[str]:
        if not os.path.exists(self.output_dir):
            return None
        for f in os.listdir(self.output_dir):
            if video_id in f and f.endswith('.mp4'):
                return os.path.join(self.output_dir, f)
        return None

    def get_video_info(self, video_id: str) -> Optional[Dict[str, Any]]:
        path = self.get_video_path(video_id)
        if path and os.path.exists(path):
            filename = os.path.basename(path)
            info = {
                'id': video_id,
                'filename': filename,
                'file_path': path,
                'file_size': os.path.getsize(path),
                'created_at': datetime.fromtimestamp(os.path.getctime(path)).isoformat()
            }
            # 메타데이터 파일에서 카테고리 등 추가 정보 읽기
            meta_file = os.path.join(self.output_dir, f"{video_id}_meta.json")
            if os.path.exists(meta_file):
                try:
                    with open(meta_file, 'r', encoding='utf-8') as f:
                        meta_data = json.load(f)
                        info['category'] = meta_data.get('category', '')
                        info['ocr_lang'] = meta_data.get('ocr_lang', '')
                        info['mode'] = meta_data.get('mode', 'basic')
                        info['pdf_name'] = meta_data.get('pdf_name', '')
                        # 단계 정보도 메타데이터에 있으면 가져오기
                        if 'stage' in meta_data:
                            info['stage'] = meta_data['stage']
                except Exception as e:
                    print(f"[{video_id}] 메타데이터 읽기 오류: {e}")
            return info
        return None

    def get_video_transcript(self, video_id: str) -> Optional[str]:
        """비디오의 트랜스크립트 텍스트를 반환합니다.

        다음 순서로 트랜스크립트를 찾습니다:
        1. generated_audio 디렉토리의 JSON 파일 (script 필드) - 가장 완전한 대본
        2. _timing.json 파일의 transcript_segments (Whisper 변환)
        3. _timing.json 파일의 page_texts (OCR)

        Args:
            video_id: 비디오 ID

        Returns:
            트랜스크립트 텍스트 또는 None
        """
        # 1. generated_audio 디렉토리에서 대본 찾기 (가장 완전한 대본)
        audio_dir = os.path.join(os.path.dirname(self.output_dir), 'generated_audio')
        if os.path.exists(audio_dir):
            for f in os.listdir(audio_dir):
                if f.endswith('.json') and video_id in f:
                    audio_json_path = os.path.join(audio_dir, f)
                    try:
                        with open(audio_json_path, 'r', encoding='utf-8') as af:
                            audio_data = json.load(af)
                            script = audio_data.get('script', '')
                            if script and len(script) >= 100:
                                print(f"[{video_id}] 오디오 대본 추출: {len(script)} 문자 (from {f})")
                                return script
                    except Exception as e:
                        print(f"[{video_id}] 오디오 대본 읽기 오류: {e}")

        # 2. _timing.json 파일에서 트랜스크립트 찾기
        timing_file = os.path.join(self.output_dir, f"{video_id}_timing.json")
        if os.path.exists(timing_file):
            try:
                with open(timing_file, 'r', encoding='utf-8') as f:
                    timing_data = json.load(f)

                # Whisper 트랜스크립트 우선 사용
                transcript_segments = timing_data.get('transcript_segments', [])
                if transcript_segments:
                    transcript_text = ' '.join([seg.get('text', '').strip() for seg in transcript_segments])
                    if transcript_text and len(transcript_text) >= 100:
                        print(f"[{video_id}] Whisper 트랜스크립트 추출: {len(transcript_text)} 문자")
                        return transcript_text

                # Whisper 트랜스크립트가 없거나 짧으면 OCR 텍스트 사용
                page_texts = timing_data.get('page_texts', [])
                if page_texts:
                    ocr_text = '\n\n'.join([text.strip() for text in page_texts if text.strip()])
                    if ocr_text and len(ocr_text) >= 100:
                        print(f"[{video_id}] OCR 텍스트 추출: {len(ocr_text)} 문자")
                        return ocr_text

            except Exception as e:
                print(f"[{video_id}] 타이밍 파일 읽기 오류: {e}")

        print(f"[{video_id}] 트랜스크립트/대본 없음 또는 너무 짧음")
        return None

    def update_video_stage(self, video_id: str, stage: str) -> bool:
        """비디오의 단계(stage)를 업데이트합니다."""
        meta_file = os.path.join(self.output_dir, f"{video_id}_meta.json")
        try:
            meta_data = {}
            if os.path.exists(meta_file):
                with open(meta_file, 'r', encoding='utf-8') as f:
                    meta_data = json.load(f)
            
            meta_data['stage'] = stage
            meta_data['updated_at'] = datetime.now().isoformat()
            
            with open(meta_file, 'w', encoding='utf-8') as f:
                json.dump(meta_data, f, ensure_ascii=False, indent=2)
            
            print(f"[{video_id}] Video stage updated to: {stage}")
            return True
        except Exception as e:
            print(f"[{video_id}] Failed to update video stage: {e}")
            return False

    def delete_video(self, video_id: str) -> bool:
        path = self.get_video_path(video_id)
        if path and os.path.exists(path):
            print(f"[{video_id}] 영상 삭제: {path}")
            os.remove(path)

            # 연관된 PDF도 삭제
            pdf_path = self.get_pdf_path(video_id)
            if pdf_path and os.path.exists(pdf_path):
                print(f"[{video_id}] PDF 삭제: {pdf_path}")
                os.remove(pdf_path)
            else:
                print(f"[{video_id}] PDF 파일 없음 (video_id로 검색)")

            # 타이밍 JSON 파일 삭제
            timing_file = os.path.join(self.output_dir, f"{video_id}_timing.json")
            if os.path.exists(timing_file):
                print(f"[{video_id}] 타이밍 파일 삭제: {timing_file}")
                os.remove(timing_file)

            # 메타데이터 JSON 파일 삭제
            meta_file = os.path.join(self.output_dir, f"{video_id}_meta.json")
            if os.path.exists(meta_file):
                print(f"[{video_id}] 메타데이터 파일 삭제: {meta_file}")
                os.remove(meta_file)

            return True
        return False

    def cleanup_orphan_files(self) -> Dict[str, List[str]]:
        """
        고아 파일 정리: 영상 파일이 없는 타이밍/메타 파일, PDF 파일 삭제
        Returns: {'deleted_timings': [...], 'deleted_metas': [...], 'deleted_pdfs': [...]}
        """
        result = {
            'deleted_timings': [],
            'deleted_metas': [],
            'deleted_pdfs': []
        }

        # 1. 현재 존재하는 영상 ID 목록 수집
        video_ids = set()
        if os.path.exists(self.output_dir):
            for f in os.listdir(self.output_dir):
                if f.endswith('.mp4'):
                    parts = f.rsplit('_', 1)
                    video_id = parts[1].replace('.mp4', '') if len(parts) > 1 else f.replace('.mp4', '')
                    video_ids.add(video_id)

        # 2. 고아 타이밍 파일 삭제
        if os.path.exists(self.output_dir):
            for f in os.listdir(self.output_dir):
                if f.endswith('_timing.json'):
                    timing_id = f.replace('_timing.json', '')
                    if timing_id not in video_ids:
                        path = os.path.join(self.output_dir, f)
                        os.remove(path)
                        result['deleted_timings'].append(f)
                        print(f"고아 타이밍 파일 삭제: {f}")

        # 3. 고아 메타 파일 삭제
        if os.path.exists(self.output_dir):
            for f in os.listdir(self.output_dir):
                if f.endswith('_meta.json'):
                    meta_id = f.replace('_meta.json', '')
                    if meta_id not in video_ids:
                        path = os.path.join(self.output_dir, f)
                        os.remove(path)
                        result['deleted_metas'].append(f)
                        print(f"고아 메타 파일 삭제: {f}")

        # 4. 고아 PDF 파일 삭제
        if os.path.exists(self.pdf_dir):
            for f in os.listdir(self.pdf_dir):
                if f.endswith('.pdf'):
                    parts = f.rsplit('_', 1)
                    pdf_id = parts[1].replace('.pdf', '') if len(parts) > 1 else ''
                    if pdf_id and pdf_id not in video_ids:
                        path = os.path.join(self.pdf_dir, f)
                        os.remove(path)
                        result['deleted_pdfs'].append(f)
                        print(f"고아 PDF 파일 삭제: {f}")

        total = len(result['deleted_timings']) + len(result['deleted_metas']) + len(result['deleted_pdfs'])
        print(f"고아 파일 정리 완료: 총 {total}개 파일 삭제")

        return result

    def get_pdf_list(self) -> List[Dict[str, Any]]:
        """저장된 PDF 목록 조회"""
        pdfs = []
        if os.path.exists(self.pdf_dir):
            for f in os.listdir(self.pdf_dir):
                if f.endswith('.pdf'):
                    path = os.path.join(self.pdf_dir, f)

                    # JSON 메타데이터 파일에서 정보 로드
                    meta_path = path.rsplit('.', 1)[0] + '.json'
                    metadata = {}
                    if os.path.exists(meta_path):
                        try:
                            with open(meta_path, 'r', encoding='utf-8') as mf:
                                metadata = json.load(mf)
                        except Exception:
                            pass

                    # ID 결정: 메타데이터의 plan_id 또는 파일명에서 추출
                    if metadata.get('plan_id'):
                        pdf_id = metadata['plan_id']
                    else:
                        # 기존 방식 (fallback)
                        parts = f.rsplit('_', 1)
                        pdf_id = parts[1].replace('.pdf', '') if len(parts) > 1 else f.replace('.pdf', '')

                    pdfs.append({
                        'id': pdf_id,
                        'filename': f,
                        'original_name': f,  # 원본 파일명 그대로 사용
                        'title': metadata.get('title', f.replace('.pdf', '')),
                        'file_path': path,
                        'file_size': os.path.getsize(path),
                        'slide_count': metadata.get('slide_count', 0),
                        'language': metadata.get('language', 'ko'),
                        'category': metadata.get('category', ''),
                        'created_at': datetime.fromtimestamp(os.path.getctime(path)).isoformat()
                    })

        return sorted(pdfs, key=lambda x: x['created_at'], reverse=True)

    def get_pdf_path(self, pdf_id: str) -> Optional[str]:
        """PDF 파일 경로 조회"""
        if not os.path.exists(self.pdf_dir):
            return None
        for f in os.listdir(self.pdf_dir):
            if pdf_id in f and f.endswith('.pdf'):
                return os.path.join(self.pdf_dir, f)
        return None

    def get_pdf_info(self, pdf_id: str) -> Optional[Dict[str, Any]]:
        """PDF 파일 정보 조회"""
        path = self.get_pdf_path(pdf_id)
        if path and os.path.exists(path):
            filename = os.path.basename(path)

            # JSON 메타데이터 파일에서 정보 로드
            meta_path = path.rsplit('.', 1)[0] + '.json'
            metadata = {}
            if os.path.exists(meta_path):
                try:
                    with open(meta_path, 'r', encoding='utf-8') as mf:
                        metadata = json.load(mf)
                except Exception:
                    pass

            return {
                'id': pdf_id,
                'filename': filename,
                'original_name': filename,  # 원본 파일명 그대로 사용
                'title': metadata.get('title', filename.replace('.pdf', '')),
                'file_path': path,
                'file_size': os.path.getsize(path),
                'slide_count': metadata.get('slide_count', 0),
                'language': metadata.get('language', 'ko'),
                'category': metadata.get('category', ''),
                'created_at': datetime.fromtimestamp(os.path.getctime(path)).isoformat()
            }
        return None

    def get_transitions(self) -> List[str]:
        return self.TRANSITIONS.copy()

    def is_smart_mode_available(self) -> bool:
        return WHISPER_AVAILABLE

    async def reencode_with_timings(
        self,
        video_id: str,
        pdf_path: str,
        video_path: str,
        timings: List[Dict[str, float]],
        width: int = 1920,
        height: int = 1080,
        fps: int = 30,
        dpi: int = 200,
        logo_path: Optional[str] = None,
        reencode_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """편집된 타이밍으로 영상을 재변환합니다."""
        # reencode_id가 제공되면 사용, 아니면 새로 생성
        new_video_id = reencode_id or str(uuid.uuid4())[:8]
        temp_dir = tempfile.mkdtemp(prefix=f'pdf2mp4_reencode_{new_video_id}_')
        self.register_temp_dir(new_video_id, temp_dir)

        try:
            # 진행률 초기화 (new_video_id로 추적)
            self.update_progress(new_video_id, 'init', 0, '🔄 재변환 준비 중...', None)

            print(f"[{new_video_id}] 🔄 Re-encoding with custom timings")
            print(f"[{new_video_id}] PDF: {pdf_path}")
            print(f"[{new_video_id}] Original Video: {video_path}")
            print(f"[{new_video_id}] Timings: {len(timings)} slides")

            # 1. PDF를 이미지로 변환
            self.update_progress(new_video_id, 'pdf', 10, '📄 PDF 이미지 변환 중...', None)
            with open(pdf_path, 'rb') as f:
                pdf_content = f.read()
            images = convert_from_bytes(pdf_content, dpi=dpi)
            print(f"[{new_video_id}] Extracted {len(images)} pages")

            # 이미지 수와 타이밍 수 확인
            if len(images) != len(timings):
                print(f"[{new_video_id}] Warning: Image count ({len(images)}) != Timing count ({len(timings)})")
                # 타이밍 수에 맞춰 조정
                if len(timings) < len(images):
                    images = images[:len(timings)]
                else:
                    timings = timings[:len(images)]

            # 로고 이미지 로드
            logo_img = None
            if logo_path and os.path.exists(logo_path):
                logo_img = Image.open(logo_path).convert('RGBA')
                print(f"[{new_video_id}] Logo loaded: {logo_path}")

            # 2. 이미지 리사이즈 (로고 합성 포함)
            self.update_progress(new_video_id, 'resize', 20, '🖼️ 이미지 리사이즈 중...', None)
            resized_images = []
            for i, img in enumerate(images):
                resized = self._resize_image(img, width, height, logo_img)
                resized_images.append(resized)

            # 3. 기존 영상에서 오디오 추출
            self.update_progress(new_video_id, 'audio', 30, '🎵 오디오 추출 중...', None)
            audio_path = os.path.join(temp_dir, 'audio.aac')
            audio_duration = 0
            try:
                subprocess.run([
                    'ffmpeg', '-y', '-i', video_path,
                    '-vn', '-acodec', 'copy', audio_path
                ], capture_output=True, check=True)
                print(f"[{new_video_id}] Audio extracted")
            except subprocess.CalledProcessError as e:
                # AAC 추출 실패 시 MP3로 시도
                audio_path = os.path.join(temp_dir, 'audio.mp3')
                try:
                    subprocess.run([
                        'ffmpeg', '-y', '-i', video_path,
                        '-vn', '-acodec', 'libmp3lame', '-q:a', '2', audio_path
                    ], capture_output=True, check=True)
                    print(f"[{new_video_id}] Audio extracted as MP3")
                except:
                    audio_path = None
                    print(f"[{new_video_id}] No audio extracted")

            # 오디오 길이 확인 및 마지막 타이밍 조정 (오디오 끝 잘림 방지)
            if audio_path and os.path.exists(audio_path):
                result = subprocess.run(
                    ['ffprobe', '-v', 'error', '-show_entries', 'format=duration',
                     '-of', 'default=noprint_wrappers=1:nokey=1', audio_path],
                    capture_output=True, text=True
                )
                audio_duration = float(result.stdout.strip()) if result.stdout.strip() else 0
                print(f"[{new_video_id}] Audio duration: {audio_duration:.2f}s")

                # 비디오가 오디오보다 짧으면 마지막 슬라이드 연장
                target_duration = audio_duration + 0.5  # 0.5초 마진
                video_end = timings[-1]['start'] + timings[-1]['duration']
                if video_end < target_duration:
                    timings[-1]['duration'] = target_duration - timings[-1]['start']
                    print(f"[{new_video_id}] 마지막 슬라이드 연장: {video_end:.1f}초 → {target_duration:.1f}초")

            # 4. 영상 출력
            self.update_progress(new_video_id, 'encode', 40, '🎬 영상 인코딩 중...', None)
            original_filename = os.path.basename(video_path)
            base_name = original_filename.rsplit('_', 1)[0]  # video_id 제거
            output_filename = f"{base_name}_edited_{new_video_id}.mp4"
            output_path = os.path.join(self.output_dir, output_filename)

            video_duration = timings[-1]['start'] + timings[-1]['duration']
            print(f"[{new_video_id}] 🎬 NVENC GPU 가속 인코딩 시작")
            print(f"[{new_video_id}] 📊 영상 길이: {video_duration:.1f}초")

            success = self._encode_video_nvenc(
                resized_images, timings, audio_path, output_path, fps, width, height, new_video_id
            )

            if not success:
                raise Exception("Video encoding failed")

            self.update_progress(new_video_id, 'finalize', 90, '📁 파일 정리 중...', None)

            # 5. PDF 복사 (새 video_id로)
            new_pdf_path = os.path.join(self.pdf_dir, f"{os.path.basename(pdf_path).rsplit('_', 1)[0]}_{new_video_id}.pdf")
            import shutil
            shutil.copy(pdf_path, new_pdf_path)
            print(f"[{new_video_id}] PDF copied: {new_pdf_path}")

            # 6. 타이밍 정보 저장
            import json
            timing_file = os.path.join(self.output_dir, f"{new_video_id}_timing.json")

            # 기존 타이밍 파일에서 page_texts, transcript_segments 가져오기
            page_texts = []
            transcript_segments = []
            old_timing_file = os.path.join(self.output_dir, f"{video_id}_timing.json")
            if os.path.exists(old_timing_file):
                try:
                    with open(old_timing_file, 'r', encoding='utf-8') as f:
                        old_data = json.load(f)
                        page_texts = old_data.get('page_texts', [])
                        transcript_segments = old_data.get('transcript_segments', [])
                except:
                    pass

            timing_data = {
                'timings': timings,
                'page_texts': page_texts,
                'transcript_segments': transcript_segments,  # Whisper 세그먼트 유지
                'edited': True  # 편집된 타이밍임을 표시
            }
            with open(timing_file, 'w', encoding='utf-8') as f:
                json.dump(timing_data, f, ensure_ascii=False, indent=2)

            # 7. 메타데이터 파일 저장 (기존 메타에서 복사 + 업데이트)
            meta_file = os.path.join(self.output_dir, f"{new_video_id}_meta.json")
            old_meta_file = os.path.join(self.output_dir, f"{video_id}_meta.json")
            meta_data = {
                'category': '',
                'ocr_lang': '',
                'created_by': '',
                'duration': video_duration,
                'mode': 'edited',
                'original_video_id': video_id,
                'pdf_name': os.path.basename(new_pdf_path),
                'created_at': datetime.utcnow().isoformat(),
                'stage': 'reencoded'  # 재변환 완료 스테이지
            }
            # 기존 메타데이터에서 정보 복사
            if os.path.exists(old_meta_file):
                try:
                    with open(old_meta_file, 'r', encoding='utf-8') as f:
                        old_meta = json.load(f)
                        meta_data['category'] = old_meta.get('category', '')
                        meta_data['ocr_lang'] = old_meta.get('ocr_lang', '')
                        meta_data['created_by'] = old_meta.get('created_by', '')
                except:
                    pass
            with open(meta_file, 'w', encoding='utf-8') as f:
                json.dump(meta_data, f, ensure_ascii=False, indent=2)
            print(f"[{new_video_id}] 메타데이터 저장: {meta_file}")

            # 8. 기존 파일 삭제 (원본 영상, PDF, 타이밍, 메타)
            print(f"[{new_video_id}] 🗑️ 기존 파일 정리 중...")

            # 기존 영상 삭제
            if os.path.exists(video_path):
                os.remove(video_path)
                print(f"[{new_video_id}]   기존 영상 삭제: {video_path}")

            # 기존 PDF 삭제
            if os.path.exists(pdf_path) and pdf_path != new_pdf_path:
                os.remove(pdf_path)
                print(f"[{new_video_id}]   기존 PDF 삭제: {pdf_path}")

            # 기존 타이밍 파일 삭제
            if os.path.exists(old_timing_file):
                os.remove(old_timing_file)
                print(f"[{new_video_id}]   기존 타이밍 삭제: {old_timing_file}")

            # 기존 메타 파일 삭제
            if os.path.exists(old_meta_file):
                os.remove(old_meta_file)
                print(f"[{new_video_id}]   기존 메타 삭제: {old_meta_file}")

            video_info = {
                'id': new_video_id,
                'filename': output_filename,
                'original_video_id': video_id,
                'page_count': len(images),
                'duration': video_duration,
                'resolution': f'{width}x{height}',
                'created_at': datetime.utcnow().isoformat(),
                'file_path': output_path,
                'file_size': os.path.getsize(output_path),
                'reencoded': True  # 재변환된 영상임을 표시
            }

            result = {'status': 'success', 'video': video_info, 'reencode_id': new_video_id}
            self.update_progress(new_video_id, 'complete', 100, '✅ 재변환 완료!', result)
            print(f"[{new_video_id}] ✅ Re-encoding completed successfully")
            return result

        except Exception as e:
            error_result = {'status': 'error', 'message': str(e), 'reencode_id': new_video_id}
            self.update_progress(new_video_id, 'error', 0, f'❌ 오류: {str(e)}', error_result)
            print(f"[{new_video_id}] ❌ Re-encoding failed: {e}")
            return error_result
        finally:
            self.cleanup_temp_dir(new_video_id)
            self.clear_process_pid(new_video_id)
