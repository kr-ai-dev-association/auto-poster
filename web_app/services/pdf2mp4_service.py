"""
PDF to MP4 변환 서비스
PDF 파일을 MP4 영상으로 변환하는 기능을 제공합니다.
NVENC GPU 가속을 직접 사용합니다.
"""

import os
import tempfile
import shutil
import uuid
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
    def update_progress(cls, video_id: str, stage: str, progress: int, message: str, eta: Optional[int] = None):
        cls._progress_store[video_id] = {
            'video_id': video_id,
            'stage': stage,
            'progress': progress,
            'message': message,
            'eta': eta,
            'timestamp': datetime.now().isoformat()
        }

    @classmethod
    def clear_progress(cls, video_id: str):
        if video_id in cls._progress_store:
            del cls._progress_store[video_id]

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

    def cancel_conversion(self, video_id: str) -> Dict[str, Any]:
        """변환 취소 및 정리"""
        if not self.request_cancel(video_id):
            return {'status': 'error', 'message': '진행 중인 변환을 찾을 수 없습니다.'}

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

        # ffmpeg 프로세스 시작
        process = subprocess.Popen(
            ffmpeg_cmd,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE
        )

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

        stderr_output = process.stderr.read().decode() if process.stderr else ""

        if process.returncode != 0:
            print(f"[{video_id}] FFmpeg 오류 (코드 {process.returncode}): {stderr_output}")
            return False

        print(f"[{video_id}] ✅ NVENC 인코딩 완료: {frame_count} 프레임")
        return True

    async def _generate_and_burn_subtitles(
        self,
        video_path: str,
        video_id: str,
        temp_dir: str,
        youtube_service,
        subtitle_lang: str = 'ko',
        subtitle_level: int = 1
    ) -> Optional[str]:
        """AI로 자막을 생성하고 영상에 합성합니다.

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

    async def convert_basic(
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
        youtube_service = None
    ) -> Dict[str, Any]:
        """Basic 모드: 고정 시간 간격으로 PDF를 영상으로 변환

        gen_subtitles: True이면 AI 자막 생성
        subtitle_lang: 자막 언어 (ko, en)
        subtitle_level: 자막 상세도 (1: 키워드, 2: 요약, 3: 전체)
        youtube_service: 자막 생성을 위한 YouTubeService 인스턴스
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

            # 오디오에 맞게 조정
            if audio_duration > 0:
                total_video_duration = len(images) * page_duration
                if audio_duration > total_video_duration:
                    # 마지막 이미지 연장
                    extra = audio_duration - total_video_duration + 2.0  # 2초 마진
                    timings[-1]['duration'] += extra

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

            # 7. AI 자막 생성 (옵션)
            if gen_subtitles and youtube_service:
                self.update_progress(video_id, 'subtitles', 90, '🎤 AI 자막 생성 중...', None)
                try:
                    final_output = await self._generate_and_burn_subtitles(
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

    async def convert_smart(
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
        youtube_service = None
    ) -> Dict[str, Any]:
        """Smart 모드: Whisper로 오디오 분석, 자동 페이지 타이밍 결정

        gen_subtitles: True이면 AI 자막 생성
        subtitle_lang: 자막 언어 (ko, en)
        subtitle_level: 자막 상세도 (1: 키워드, 2: 요약, 3: 전체)
        youtube_service: 자막 생성을 위한 YouTubeService 인스턴스
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

        video_id = str(uuid.uuid4())[:8]
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

            # 6. 마지막 페이지 연장 (오디오 끝까지 + 마진)
            audio_margin = 2.0
            target_duration = total_duration + audio_margin
            if page_timings:
                last_end = page_timings[-1]['start'] + page_timings[-1]['duration']
                if last_end < target_duration:
                    page_timings[-1]['duration'] = target_duration - page_timings[-1]['start']

            # 7. 영상 출력
            output_filename = f"{os.path.splitext(filename)[0]}_smart_{video_id}.mp4"
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
            pdf_filename = f"{os.path.splitext(filename)[0]}_{video_id}.pdf"
            pdf_path = os.path.join(self.pdf_dir, pdf_filename)
            with open(pdf_path, 'wb') as f:
                f.write(pdf_content)
            print(f"[{video_id}] 📄 원본 PDF 저장: {pdf_filename}")

            self.update_progress(video_id, 'complete', 100, '✅ 변환 완료!', 0)

            video_info = {
                'id': video_id,
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
            timing_data = {
                'timings': page_timings,
                'page_texts': page_texts if page_texts else []
            }
            with open(timing_file, 'w', encoding='utf-8') as f:
                json.dump(timing_data, f, ensure_ascii=False, indent=2)
            print(f"[{video_id}] 타이밍 정보 저장: {timing_file} (OCR 텍스트 포함)")

            # 7. AI 자막 생성 (옵션)
            if gen_subtitles and youtube_service:
                self.update_progress(video_id, 'subtitles', 95, '🎤 AI 자막 생성 중...', None)
                try:
                    final_output = await self._generate_and_burn_subtitles(
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

    def _calculate_smart_timings(
        self,
        segments: List[Dict],
        num_pages: int,
        total_duration: float,
        page_texts: Optional[List[str]] = None,
        video_id: str = ""
    ) -> List[Dict[str, float]]:
        """PDF 페이지 키워드와 Whisper 트랜스크립트를 매칭하여 페이지 타이밍 계산

        개선된 알고리즘 v2:
        1. 전체 남은 시간 범위에서 검색 (제한된 마진 대신)
        2. 키워드 + 의미적 유사도 + 위치 근접도를 결합
        3. 최소 페이지 표시 시간 보장하되 짧은 슬라이드도 허용
        4. 순차적 제약 조건 유지 (페이지 순서 보장)
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

        print(f"[{video_id}] 🔍 키워드 + 의미적 유사도 기반 페이지 매칭 시작 (v2)")

        # 디버그: Whisper 세그먼트 샘플
        print(f"[{video_id}] 📝 Whisper 세그먼트 샘플:")
        for seg in segments[:5]:
            print(f"[{video_id}]   [{seg['start']:.1f}s] {seg.get('text', '')[:80]}")

        # 각 페이지별 키워드 추출
        page_keywords = []
        print(f"[{video_id}] 📄 페이지별 키워드:")
        for i, pt in enumerate(page_texts):
            kws = self._extract_keywords_from_page(pt)
            page_keywords.append(kws)
            if i < 3:
                print(f"[{video_id}]   페이지 {i+1}: {kws[:10]}")

        # 기본 설정
        base_page_duration = total_duration / num_pages
        min_page_duration = 3.0  # 최소 페이지 표시 시간 (짧은 슬라이드 허용을 위해 5초→3초)

        # 첫 페이지는 항상 0초, 신뢰도 1.0
        page_start_times = [0.0]
        page_confidences = [1.0]

        # Semantic similarity 사용 가능 여부 확인
        use_semantic = SENTENCE_TRANSFORMERS_AVAILABLE and self.sentence_model is not None
        if use_semantic:
            print(f"[{video_id}] ✅ Semantic similarity 활성화 (키워드 80% + 의미 20%)")
        else:
            print(f"[{video_id}] ⚠️ Semantic similarity 비활성화 (키워드만 사용)")

        for page_idx in range(1, num_pages):
            page_text = page_texts[page_idx]
            keywords = page_keywords[page_idx]

            # 예상 시작 시간 (균등 분배 기준)
            expected_start = page_idx * base_page_duration

            # 이전 페이지의 실제 시작 시간
            last_valid_time = page_start_times[-1]
            if last_valid_time is None:
                for t in reversed(page_start_times):
                    if t is not None:
                        last_valid_time = t
                        break
                if last_valid_time is None:
                    last_valid_time = (page_idx - 1) * base_page_duration

            # 남은 페이지 수를 고려한 최대 검색 범위 계산
            remaining_pages = num_pages - page_idx
            remaining_time = total_duration - last_valid_time
            max_time_per_page = remaining_time / remaining_pages if remaining_pages > 0 else remaining_time

            # 검색 범위: 이전 페이지 이후부터 ~ 남은 시간의 60%까지 (다음 페이지들 여유 확보)
            search_start = last_valid_time + min_page_duration
            search_end = min(last_valid_time + max_time_per_page * 2, total_duration - (remaining_pages - 1) * min_page_duration)

            # 검색 범위가 유효하지 않으면 보간으로 처리
            if search_start >= search_end:
                page_start_times.append(None)
                page_confidences.append(0.0)
                print(f"[{video_id}]   페이지 {page_idx + 1}: (검색 범위 없음, 보간 예정)")
                continue

            best_time = None
            best_score = 0.0
            match_info = ""

            if use_semantic and page_text.strip():
                # 의미적 유사도 + 키워드 + 위치 근접도 결합 방식
                match_time, score, kw_count = self._find_best_segment_with_position(
                    page_text,
                    keywords[:20],
                    segments,
                    search_start,
                    search_end,
                    expected_start,
                    base_page_duration,
                    window_seconds=15.0,
                    video_id=video_id
                )

                if match_time is not None and score > 0.10:  # 최소 점수 임계값 낮춤 (0.15→0.10)
                    best_time = match_time
                    best_score = score
                    match_info = f"semantic+kw+pos (score={score:.2f}, kw={kw_count})"

            # Semantic 매칭 실패 시 키워드만 사용
            if best_time is None and keywords:
                multi_match_time, matched_kws, match_count = self._find_best_segment_for_keywords(
                    keywords[:20],
                    segments,
                    search_start=search_start,
                    window_size=5
                )

                # 매칭 시간이 검색 범위 내에 있는지 확인
                if multi_match_time is not None and search_start <= multi_match_time <= search_end:
                    if match_count >= 1:  # 최소 매칭 수 낮춤 (2→1)
                        best_time = multi_match_time
                        best_score = match_count / len(keywords) if keywords else 0.0
                        match_info = f"keyword ({match_count}개: {matched_kws[:3]})"

            if best_time is not None:
                page_start_times.append(best_time)
                page_confidences.append(best_score)
                print(f"[{video_id}]   페이지 {page_idx + 1}: {match_info} @ {best_time:.1f}초 (범위: {search_start:.1f}~{search_end:.1f}초)")
            else:
                page_start_times.append(None)
                page_confidences.append(0.0)
                print(f"[{video_id}]   페이지 {page_idx + 1}: (매칭 실패, 보간 예정) (범위: {search_start:.1f}~{search_end:.1f}초)")

        # 매칭되지 않은 페이지들 보간 처리
        page_start_times = self._interpolate_missing_times(
            page_start_times, total_duration, min_page_duration, video_id
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
        videos = []
        if os.path.exists(self.output_dir):
            for f in os.listdir(self.output_dir):
                if f.endswith('.mp4'):
                    path = os.path.join(self.output_dir, f)
                    parts = f.rsplit('_', 1)
                    video_id = parts[1].replace('.mp4', '') if len(parts) > 1 else f.replace('.mp4', '')

                    videos.append({
                        'id': video_id,
                        'filename': f,
                        'file_path': path,
                        'file_size': os.path.getsize(path),
                        'created_at': datetime.fromtimestamp(os.path.getctime(path)).isoformat()
                    })

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
            return {
                'id': video_id,
                'filename': filename,
                'file_path': path,
                'file_size': os.path.getsize(path),
                'created_at': datetime.fromtimestamp(os.path.getctime(path)).isoformat()
            }
        return None

    def delete_video(self, video_id: str) -> bool:
        path = self.get_video_path(video_id)
        if path and os.path.exists(path):
            os.remove(path)
            # 연관된 PDF도 삭제
            pdf_path = self.get_pdf_path(video_id)
            if pdf_path and os.path.exists(pdf_path):
                os.remove(pdf_path)
            return True
        return False

    def get_pdf_list(self) -> List[Dict[str, Any]]:
        """저장된 PDF 목록 조회"""
        pdfs = []
        if os.path.exists(self.pdf_dir):
            for f in os.listdir(self.pdf_dir):
                if f.endswith('.pdf'):
                    path = os.path.join(self.pdf_dir, f)
                    parts = f.rsplit('_', 1)
                    pdf_id = parts[1].replace('.pdf', '') if len(parts) > 1 else f.replace('.pdf', '')

                    pdfs.append({
                        'id': pdf_id,
                        'filename': f,
                        'original_name': parts[0] + '.pdf' if len(parts) > 1 else f,
                        'file_path': path,
                        'file_size': os.path.getsize(path),
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
            parts = filename.rsplit('_', 1)
            return {
                'id': pdf_id,
                'filename': filename,
                'original_name': parts[0] + '.pdf' if len(parts) > 1 else filename,
                'file_path': path,
                'file_size': os.path.getsize(path),
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
        dpi: int = 200
    ) -> Dict[str, Any]:
        """편집된 타이밍으로 영상을 재변환합니다."""
        new_video_id = str(uuid.uuid4())[:8]
        temp_dir = tempfile.mkdtemp(prefix=f'pdf2mp4_reencode_{new_video_id}_')
        self.register_temp_dir(new_video_id, temp_dir)

        try:
            print(f"[{new_video_id}] 🔄 Re-encoding with custom timings")
            print(f"[{new_video_id}] PDF: {pdf_path}")
            print(f"[{new_video_id}] Original Video: {video_path}")
            print(f"[{new_video_id}] Timings: {len(timings)} slides")

            # 1. PDF를 이미지로 변환
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

            # 2. 이미지 리사이즈
            resized_images = []
            for i, img in enumerate(images):
                resized = self._resize_image(img, width, height)
                resized_images.append(resized)

            # 3. 기존 영상에서 오디오 추출
            audio_path = os.path.join(temp_dir, 'audio.aac')
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

            # 4. 영상 출력
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

            # 5. PDF 복사 (새 video_id로)
            new_pdf_path = os.path.join(self.pdf_dir, f"{os.path.basename(pdf_path).rsplit('_', 1)[0]}_{new_video_id}.pdf")
            import shutil
            shutil.copy(pdf_path, new_pdf_path)
            print(f"[{new_video_id}] PDF copied: {new_pdf_path}")

            # 6. 타이밍 정보 저장
            import json
            timing_file = os.path.join(self.output_dir, f"{new_video_id}_timing.json")

            # 기존 타이밍 파일에서 page_texts 가져오기
            page_texts = []
            old_timing_file = os.path.join(self.output_dir, f"{video_id}_timing.json")
            if os.path.exists(old_timing_file):
                try:
                    with open(old_timing_file, 'r', encoding='utf-8') as f:
                        old_data = json.load(f)
                        page_texts = old_data.get('page_texts', [])
                except:
                    pass

            timing_data = {
                'timings': timings,
                'page_texts': page_texts
            }
            with open(timing_file, 'w', encoding='utf-8') as f:
                json.dump(timing_data, f, ensure_ascii=False, indent=2)

            video_info = {
                'id': new_video_id,
                'filename': output_filename,
                'original_video_id': video_id,
                'page_count': len(images),
                'duration': video_duration,
                'resolution': f'{width}x{height}',
                'created_at': datetime.utcnow().isoformat(),
                'file_path': output_path,
                'file_size': os.path.getsize(output_path)
            }

            print(f"[{new_video_id}] ✅ Re-encoding completed successfully")
            return {'status': 'success', 'video': video_info}

        except Exception as e:
            print(f"[{new_video_id}] ❌ Re-encoding failed: {e}")
            return {'status': 'error', 'message': str(e)}
        finally:
            self.cleanup_temp_dir(new_video_id)
