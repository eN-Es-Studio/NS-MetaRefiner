import random
import sys
import types
import importlib.util
import importlib.metadata

# === HACK FOR CPU: Mock flash_attn & Metadata Distribution (Super Robust) ===
if 'flash_attn' not in sys.modules:
    # 1. Buat module palsu seperti biasa
    fake_spec = importlib.util.spec_from_loader('flash_attn', loader=None)
    fake_module = types.ModuleType('flash_attn')
    fake_module.__spec__ = fake_spec
    fake_module.flash_attn_func = lambda *args, **kwargs: None
    fake_module.flash_attn_qkvpacked_func = lambda *args, **kwargs: None
    sys.modules['flash_attn'] = fake_module

    # 2. Trik Tambahan: Tipu importlib.metadata agar Transformers tidak IndexError
    _orig_packages_distributions = importlib.metadata.packages_distributions
    def _fake_packages_distributions():
        dists = _orig_packages_distributions()
        if 'flash_attn' not in dists:
            # Berikan mapping distribusi palsu ke nama paket
            dists['flash_attn'] = ['flash-attn']
        return dists
    importlib.metadata.packages_distributions = _fake_packages_distributions
# ============================================================================
import gc
import os
import io
import json
import base64
import requests
import subprocess
import time
import threading
import shutil
import csv
import re
import webbrowser
import logging
import tempfile
import keyring
import ctypes
import winsound
from datetime import timedelta
from queue import Queue, Empty 
from pathlib import Path

# === VERSI APLIKASI ===
CURRENT_VERSION = "1.0.0" 

# === IDENTITAS APLIKASI ===
APP_NAME = "NS MetaRefiner"
COMPANY_NAME = "eN-Es-Studio"

# === KONFIGURASI GITHUB (UNTUK AUTO UPDATE) ===
GITHUB_USER = "eN-Es-Studio"
GITHUB_REPO = "NS-MetaRefiner"
# ==============================================

# === LOGIKA LOKASI FILE ===
if getattr(sys, 'frozen', False):
    # Lokasi: C:\Users\NamaUser\AppData\Roaming\NS MetaRefiner
    app_data_path = os.path.join(os.environ['APPDATA'], APP_NAME)
    if not os.path.exists(app_data_path):
        os.makedirs(app_data_path)
    BASE_DIR = app_data_path
else:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))

LOG_DIR = BASE_DIR
# Nama file log & config disesuaikan
LOG_FILE = os.path.join(LOG_DIR, "ns_meta_refiner_debug.log")
CONFIG_FILE = os.path.join(BASE_DIR, "ns_meta_refiner_config.json")
# ============================================================


def resource_path(relative_path):
    """ Mendapatkan path absolut, bekerja untuk dev dan PyInstaller """
    try:
        # PyInstaller menyimpan file di folder temp _MEIPASS
        base_path = sys._MEIPASS
    except Exception:
        # Jika biasa, pakai BASE_DIR
        base_path = BASE_DIR
    
    full_path = os.path.join(base_path, relative_path)
    if not os.path.exists(full_path):
         # Fallback: cari di folder yang sama dengan EXE/Script
         full_path = os.path.join(BASE_DIR, relative_path)
         
    return full_path
# ======================================================

# --- 1. LOGGING SETUP ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s', handlers=[logging.FileHandler(LOG_FILE, encoding='utf-8'), logging.StreamHandler(sys.stdout)])
logger = logging.getLogger(__name__)
logging.getLogger("transformers").setLevel(logging.WARNING)

# --- 2. DEPENDENCY CHECK ---
def has_nvidia_gpu():
    """Cek apakah PC memiliki GPU Nvidia yang terdeteksi."""
    try:
        # Coba jalankan perintah nvidia-smi (standar driver Nvidia)
        subprocess.run(['nvidia-smi'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
        return True
    except:
        return False

def install_dependencies():
    # === TAMBAHKAN BLOK INI DI PALING ATAS FUNGSI ===
    # Jika berjalan sebagai EXE, langsung lewati fungsi ini agar tidak crash/loop
    if getattr(sys, 'frozen', False):
        logger.info("[SYSTEM] Berjalan dalam mode EXE, melewati pemeriksaan instalasi pip.")
        return
    libs = {
        "customtkinter": "customtkinter", 
      #  "transformers": "transformers>=4.41.0", 
	"transformers": "transformers", 
        "torch": "torch", 
        "pillow": "PIL", 
        "opencv-python": "cv2", 
        "piexif": "piexif", 
        "requests": "requests", 
        "keyring": "keyring", 
        "cairosvg": "cairosvg",
        "iptcinfo3": "iptcinfo3",
        "pymupdf": "fitz",
        "mutagen": "mutagen"
    }
    
    for lib, imp in libs.items():
        try:
            __import__(imp)
            logger.info(f"[OK] {lib}")
        except ImportError:
            logger.info(f"[INSTALL] {lib}...")
            try:
                if lib == "torch":
                    # Logika Pintar: Cek GPU dulu
                    if has_nvidia_gpu():
                        logger.info("[SYSTEM] Nvidia GPU Detected! Installing CUDA version (faster)...")
                        # Install versi standar (biasanya sudah include CUDA)
                        subprocess.check_call([sys.executable, "-m", "pip", "install", "torch", "torchvision"])
                    else:
                        logger.info("[SYSTEM] No GPU Detected. Installing CPU version (lightweight)...")
                        # Install versi CPU saja (ukuran kecil)
                        subprocess.check_call([sys.executable, "-m", "pip", "install", "torch", "torchvision", "--index-url", "https://download.pytorch.org/whl/cpu"])
                else:
                    subprocess.check_call([sys.executable, "-m", "pip", "install", lib])
                logger.info(f"[OK] {lib} installed")
            except Exception as e:
                logger.error(f"Failed: {lib}: {e}")

install_dependencies()

import customtkinter as ctk
from tkinter import filedialog, messagebox
from PIL import Image, PngImagePlugin
import torch
from transformers import AutoProcessor, AutoModelForCausalLM
import cv2
import piexif
import numpy as np
from iptcinfo3 import IPTCInfo
import fitz  # <--- TAMBAHKAN INI (untuk PDF)
import mutagen # <--- Untuk Video
from mutagen.mp4 import MP4 # <--- Khusus MP4
from mutagen.id3 import ID3 # <--- Khusus error handling
import xml.etree.ElementTree as ET # <--- Untuk XMP (Vektor/Video)

# --- 3. DEVICE DETECTION ---
device = "cuda" if torch.cuda.is_available() else "mps" if hasattr(torch.backends, 'mps') and torch.backends.mps.is_available() else "cpu"
logger.info(f"Device: {device.upper()}")

# ... (import statements di paling atas) ...

# *** TULISAN BARU: Tambahkan fungsi pembersihan di sini ***
def sanitize_api_key(raw_key_string):
    """
    Membersihkan input mentah API Key yang berantakan.
    Bisa menerima input dengan pemisah: Enter, Koma, atau Spasi.
    Mengembalikan LIST berisi kunci-kunci yang bersih.
    """
    if not raw_key_string or not raw_key_string.strip():
        return []
    
    # 1. Ganti semua Koma dan Enter menjadi Spasi
    cleaned_input = raw_key_string.replace(',', ' ').replace('\n', ' ').replace('\r', ' ')
    
    # 2. Pecah string berdasarkan Spasi
    potential_keys = cleaned_input.split()
    
    # 3. Filter: Ambil hanya yang valid (panjang > 5 karakter)
    valid_keys = [key.strip() for key in potential_keys if len(key.strip()) > 5]
    
    return valid_keys

# --- 4. TITLE CLEANER & SEO OPTIMIZER ---
class TitleCleaner:
    # Tambahkan pola sampah yang sering muncul di awal kalimat Florence-2
    GARBAGE_PATTERNS = [
        # Tambahkan 'the\s+image\s+is' dan 'this\s+image\s+is' di sini
        (r'^(the\s+image\s+shows|the\s+image\s+is|this\s+image\s+shows|this\s+image\s+is|an\s+image\s+of|image\s+description|here\'?s\s+)\s*', ''), 
        (r'[^\w\s\-]', ''), 
        (r'\s+', ' ')
    ]
    
    @staticmethod
    def clean(title):
        if not title: return "Stock Asset"
        result = title.strip()
        
        # 1. Hapus pola sampah (garbage patterns)
        for pattern, replacement in TitleCleaner.GARBAGE_PATTERNS:
            result = re.sub(pattern, replacement, result, flags=re.IGNORECASE)
            
        # 2. Hapus pengulangan kata yang berdekatan (misal: "Wallpaper Wallpaper" -> "Wallpaper")
        result = re.sub(r'\b(\w+)(?:\s+\1\b)+', r'\1', result, flags=re.IGNORECASE)
        
        # 3. Hapus pengulangan frasa pendek (misal: "Purple Waves Purple Waves" -> "Purple Waves")
        for _ in range(2): # Jalankan 2 kali untuk memastikan bersih
            result = re.sub(r'(\b\w+(?:\s+\w+){0,3})\s+\1\b', r'\1', result, flags=re.IGNORECASE)

        # 4. Kapitalisasi dan Batasi Panjang
        return " ".join(word.capitalize() for word in result.split())[:200]

class SEOOptimizer:
    # 1. Daftar kata yang tidak penting (Stop Words) - akan dihapus dari keyword
    STOP_WORDS = {
        "the", "and", "with", "a", "an", "of", "in", "on", "at", "to", "for", "is", "are", 
        "it", "this", "that", "by", "from", "or", "be", "as", "was", "were", "has", "have"
    }
    
    # 2. Padanan Kata (Synonyms) - Menambah kekayaan keyword
    # Format: "kata asli": ["sinonim 1", "sinonim 2"]
    SYNONYMS = {
        "sunset": ["golden hour", "dusk", "evening", "sunrise"],
        "beach": ["coastline", "sand", "shore", "sea", "ocean"],
        "person": ["model", "human", "people", "portrait", "man", "woman"],
        "blue": ["azure", "cyan", "navy"],
        "nature": ["outdoor", "environment", "landscape", "natural"],
        "city": ["urban", "skyline", "metropolitan", "downtown"],
        "food": ["cuisine", "meal", "dish", "cooking", "delicious", "tasty"],
        "animal": ["wildlife", "creature", "fauna", "mammal", "pet", "beast"],
        "flower": ["bloom", "blossom", "flora", "botanical"],
        "background": ["backdrop", "texture", "pattern"],
        "business": ["corporate", "office", "professional", "work"],
        "technology": ["tech", "digital", "modern", "innovation", "gadget"],
        "water": ["liquid", "aqua", "splash", "drop", "wave"]
    }
    
    # 3. Kata Kunci Komersial (Hanya ditambahkan di akhir jika relevan)
    COMMERCIAL_KEYWORDS = ["background", "wallpaper", "concept", "design", "illustration", "template"]

    @staticmethod
    def generate_seo_keywords(caption):
        # Ambil semua kata dari caption
        words = re.findall(r'\b\w+\b', caption.lower())
        
        # Filter: Hapus stop words dan kata pendek
        filtered_words = [w for w in words if len(w) > 2 and w not in SEOOptimizer.STOP_WORDS]
        
        # --- STRATEGI PENGGUNAAN ---
        primary_keywords = []   # Kelompok 1: Kata dari judul (Paling Penting)
        secondary_keywords = [] # Kelompok 2: Sinonim & Deskripsi
        commercial_keywords = []# Kelompok 3: Kata komersial
        
        # 1. Ambil kata unik dari judul (Prioritas Utama)
        unique_words = list(dict.fromkeys(filtered_words))
        primary_keywords = unique_words[:5] 
        
        # 2. Cari Sinonim dari kata-kata utama
        for word in primary_keywords:
            if word in SEOOptimizer.SYNONYMS:
                syns = SEOOptimizer.SYNONYMS[word]
                for syn in syns:
                    if syn not in unique_words: # Jangan duplikat dengan judul
                        secondary_keywords.append(syn)
        
        # 3. Tambahkan sisa kata dari judul yang belum masuk primary
        remaining_title_words = [w for w in unique_words[5:] if w not in secondary_keywords]
        secondary_keywords.extend(remaining_title_words)
        
        # 4. Tambahkan Kata Komersial (Hanya jika belum ada)
        for comm in SEOOptimizer.COMMERCIAL_KEYWORDS:
            if comm not in primary_keywords and comm not in secondary_keywords:
                commercial_keywords.append(comm)
                
        # --- SUSUN URUTAN FINAL ---
        # Urutan: Primary (Subjek) -> Secondary (Deskripsi/Sinonim) -> Commercial
        final_list = primary_keywords + secondary_keywords + commercial_keywords
        
        # FUNGSI PENGAMAN: Hapus duplikat secara paksa tapi pertahankan urutan prioritas
        final_list = list(dict.fromkeys(final_list))
        
        # Batasi maksimal 25 keyword (standar Adobe Stock)
        final_list = final_list[:25]
        
        return ", ".join(final_list)

title_cleaner = TitleCleaner()
seo_optimizer = SEOOptimizer()

# --- 4.5. IMAGE SORTER / FILTER (ADVANCED GROUPING) ---

class ImageSorter:
    CATEGORIES = {
        "Border-Frame": [
            "margin", "letterbox", "white bar", "black bar", "colored bar", 
            "white border", "black border", "pillarbox", "anamorphic border"
        ],
        "Celebrity": [
            "famous person", "celebrity", "actor", "singer", "musician",
            "public figure", "famous character",
            # === Nama-nama Spesifik ===
            "ronaldo", "messi", "taylor swift", "elon musk", "trump",
            "biden", "justin bieber", "kpop", "hollywood star"
        ],
        "Brand-Logo": [
            "popular brand", "logo", "branding", "company logo", 
            "product logo", "corporate logo", "trademark"
        ],
        "Watermark-Signature": [
            "watermark", "signature", "copyright", 
            "shutterstock", "getty images", "adobe stock", "istock", 
            "123rf", "depositphotos", "dreamstime", "alamy"
        ],
        # === KATEGORI BARU: OVERLAY (SAFE LIST) ===
        # Hanya kata-kata spesifik yang jelas-jelas sampah visual
        "Overlay": [
            "date stamp", "timestamp", 
            "lower third", "news ticker", 
            "burnt-in text"
        ],
        # ==========================================
        "AI-Artifact": [
            "deformed", "distorted", "mutated", "extra fingers", "bad anatomy",
            "missing fingers", "fused fingers", "malformed hand", "claw",
            "disfigured", "extra limbs", "poorly drawn", "ugly", "three hands", "extra hand"
        ],
        "Technical-Issue": [
            # Focus & Blur
            "out of focus", "blurry", "blurred", "motion blur", "unfocused",
            # Noise & Artifact
            "grainy", "noise", "pixelated", "low quality", "compression artifact",
            # Lighting
            "overexposed", "underexposed", "too dark", "too bright", "washed out",
            # Color
            "color cast", "yellow tint", "blue tint", "bad white balance"
        ]
    }

    # Buat lookup dictionary: Kata -> Kategori
    WORD_TO_CATEGORY = {}
    for category, words in CATEGORIES.items():
        for word in words:
            WORD_TO_CATEGORY[word] = category

    @staticmethod
    def check_if_rejected(caption):
        caption_lower = caption.lower()
        
        # 1. CEK KONTEKS ARTISTIK / ABSTRAK (SUPER WHITELIST)
        artistic_context = [
            "background", "wallpaper", "texture", "pattern", "abstract", 
            "bokeh", "light effect", "glow", "sparkle", "gradient", "defocused", 
            "silhouette", "sunset", "sunrise", "backlit", "shadow", "contre-jour", 
            "3d render", "illustration", "digital art", "concept", "render", 
            "neon", "cyberpunk", "futuristic", "virtual", "cg", "cgi"
        ]
        is_artistic_content = any(re.search(r'\b' + w + r'\b', caption_lower) for w in artistic_context)

        # === TAMBAHAN: WHITELIST KHUSUS ANATOMI (SILUET) ===
        # Jika gambar adalah siluet/bayangan, matikan sensor "Bad Anatomy"
        # karena detail tubuh memang tidak terlihat.
        silhouette_context = ["silhouette", "shadow", "backlit", "contre-jour", "dark figure", "black figure"]
        is_silhouette = any(re.search(r'\b' + w + r'\b', caption_lower) for w in silhouette_context)
        # ===================================================

        # 2. CEK PENGECUALIAN UMUM (Clean Image)
        exclusion_phrases = ["no watermark", "without watermark", "no text", "clean image", "no logo"]
        for phrase in exclusion_phrases:
            if phrase in caption_lower:
                return False, [], None

        # 3. Cek Kata Terlarang
        found_reasons = []
        found_categories = set()
        
        for word, category in ImageSorter.WORD_TO_CATEGORY.items():
            pattern = r'\b' + re.escape(word) + r'\b'
            if re.search(pattern, caption_lower):
                
                # === LOGIKA PENGAMAN FINAL ===
                
                # A. Lewati Technical Issue jika Artistik
                if category == "Technical-Issue" and is_artistic_content:
                    continue
                
                # B. Lewati AI-Artifact (Bad Anatomy) jika Siluet
                # (Ini solusi untuk masalah Anda)
                if category == "AI-Artifact" and is_silhouette:
                    continue
                
                # =============================
                if word == "signature":
                    ignore_context = ["smile", "style", "look", "move", "pose", "haircut"]
                    is_context_valid = any(ctx in caption_lower for ctx in ignore_context)
                    if is_context_valid:
                        continue 
                found_reasons.append(word)
                found_categories.add(category)
        
        # 4. Deteksi Signature Generic (Teks di Pojok)
            if "Watermark-Signature" not in found_categories:
                text_indicators = [
                    "text", "writing", "handwriting", "signature", "autograph", "font", "word", "number",
                    "inscription", "initials", "mark", "scribble", "cursive", "note", "caption"
                ]
                location_indicators = ["corner", "bottom", "top", "side", "edge", "right", "left", "lower"]
                
                has_text = any(re.search(r'\b' + word + r'\b', caption_lower) for word in text_indicators)
                has_location = any(re.search(r'\b' + word + r'\b', caption_lower) for word in location_indicators)
                
                subject_whitelist = ["document", "paper", "form", "newspaper", "book", "screen", "monitor", "sign", "banner", "poster", "receipt", "invoice", "card", "money", "coin", "banknote"]
                
                # Definisi Tekstur Alam (Diperlukan untuk logika di bawah)
                texture_whitelist = ["stone", "wall", "rock", "texture", "marble", "granite", "surface", "floor", "ground", "leaf", "wood", "bark", "sand"]
                
                is_text_on_subject = any(re.search(r'\b' + w + r'\b', caption_lower) for w in subject_whitelist)
                is_natural_texture = any(re.search(r'\b' + w + r'\b', caption_lower) for w in texture_whitelist)

                # === PERBAIKAN: DETEKSI TAHUN & LOGIKA BARU ===
                # Deteksi adanya Tahun (1900-2099)
                has_year = re.search(r'\b(19\d{2}|20\d{2})\b', caption_lower)
                
                # Logika:
                # Jika ada Teks + Lokasi + Bukan di kertas...
                if has_text and has_location and not is_text_on_subject:
                    # TOLAK jika: (Ada Tahun) ATAU (Bukan Tekstur Alam)
                    # Alasan: Jika ada tahun "2024", pasti itu watermark modern, walau backgroundnya batu.
                    if has_year or not is_natural_texture:
                        found_reasons.append("text in corner/edge (suspected signature)")
                        found_categories.add("Watermark-Signature")

        if found_reasons:
            primary_category = list(found_categories)[0] 
            return True, found_reasons, primary_category
            
        return False, [], None

image_sorter = ImageSorter()

# --- 5. DUPLICATE HANDLER (SMART) ---
class DuplicateHandler:
    def __init__(self): 
        self.used_titles = set() # Pakai set untuk cek cepat

    def get_unique_title(self, title, keywords_str):
        title_lower = title.lower()
        
        # Jika judul belum pernah dipakai, langsung return
        if title_lower not in self.used_titles:
            self.used_titles.add(title_lower)
            return title
        
        # Jika DUPLIKAT: Coba perbaiki dengan Keyword
        logger.info(f"[Duplicate] Title '{title}' exists. Enhancing with keywords...")
        
        # Pecah keywords jadi list
        kw_list = [k.strip() for k in keywords_str.split(',') if k.strip()]
        
        # Coba tambahkan keyword ke judul hingga unik
        for kw in kw_list:
            # Hindari keyword yang sudah ada di judul
            if kw.lower() not in title_lower:
                # Buat judul baru: Judul Asli + Keyword
                # Contoh: "Goldfish" + "Swimming" -> "Goldfish Swimming"
                new_title = f"{title} {kw.capitalize()}"
                new_title_lower = new_title.lower()
                
                if new_title_lower not in self.used_titles:
                    self.used_titles.add(new_title_lower)
                    logger.info(f"[Duplicate] Fixed: {new_title}")
                    return new_title

        # Fallback Terakhir: Jika keyword habis/unik semua, pakai angka
        count = 1
        while True:
            new_title = f"{title} {count}"
            if new_title.lower() not in self.used_titles:
                self.used_titles.add(new_title.lower())
                return new_title
            count += 1

duplicate_handler = DuplicateHandler()

# --- 6. API HEALTH MONITOR ---
class APIHealthMonitor:
    def __init__(self):
        self.status = {eng: {"healthy": True, "count": 0} for eng in ["Gemini", "Groq", "Mistral", "OpenAI", "Local"]}
    def record_success(self, engine): self.status[engine]["count"] += 1; self.status[engine]["healthy"] = True
    def record_failure(self, engine): self.status[engine]["healthy"] = False
    def get_status_string(self): return " | ".join([f"[{'OK' if s['healthy'] else 'XX'}] {eng}({s['count']})" for eng, s in self.status.items()])
    def get_engine_stats(self): return {eng: {"success": s["count"], "failures": 0} for eng, s in self.status.items()}

api_monitor = APIHealthMonitor()

# --- 7. CONFIG & KEYRING ---

CONFIG_FILE = os.path.join(BASE_DIR, "NS-MetaRefiner_config.json")

def get_api_key_from_keyring(service_name, username):
    try: return keyring.get_password(service_name, username)
    except Exception as e: logger.error(f"Keyring error: {e}"); return None

def save_api_key_to_keyring(service_name, username, api_key):
    try: keyring.set_password(service_name, username, api_key); logger.info(f"API key for {username} saved.")
    except Exception as e: logger.error(f"Keyring error: {e}"); messagebox.showerror("Keyring Error", f"Failed to save API key: {e}")

def load_config():
    # Default jika file belum ada
    default = {
        "Gemini": "", "Groq": "", "Mistral": "", "OpenAI": "", 
        "last_engine": "Local (BLIP)",
        # Tambahkan default numerik di sini
        "min_title_len": 35,
        "max_title_len": 75,
        "min_kw_len": 40,
        "max_kw_len": 49,
        "worker_count": 5,
        "delay": 5,
        "sorting_enabled": True,
        "last_output_dir": "",
        "last_input_dir": ""
    }
    
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r", encoding='utf-8') as f:
                file_config = json.load(f)
                # Gabungkan default dengan file (file akan override default)
                config = {**default, **file_config}
                
                # Logika Keyring (tetap dipertahankan)
                for eng in ["Gemini", "Groq", "Mistral", "OpenAI"]:
                    if eng in config and config[eng] and config[eng] != "KEYRING_STORED":
                        save_api_key_to_keyring(APP_NAME, eng, config[eng])
                        config[eng] = "KEYRING_STORED"
                return config
        except Exception as e: logger.error(f"Failed to load config: {e}")
    return default

def save_config(data):
    try:
        config_to_save = data.copy()
        # Untuk keamanan, jangan simpan API Key asli di file json
        for eng in ["Gemini", "Groq", "Mistral", "OpenAI"]:
            if eng in config_to_save: config_to_save[eng] = "KEYRING_STORED"
        
        # Tulis ke file
        with open(CONFIG_FILE, "w", encoding='utf-8') as f:
            json.dump(config_to_save, f, indent=2)
            
    except Exception as e:
        logger.error(f"Config save failed: {e}")

# --- 8. AI ENGINE (FLORENCE-2) ---
processor = None
local_model = None
_model_loaded = False
model_lock = threading.Lock()

def load_local_ai_now():
    global processor, local_model, _model_loaded
    with model_lock:
        if _model_loaded: return
        try:
            # --- TAMBAHAN PESAN JELAS ---
            logger.info("Initializing AI Engine...")
            logger.info("Checking/Downloading model components (~500MB)...")
            logger.info("PLEASE WAIT... Do not close the app if it seems stuck.")
            # -----------------------------
            
            model_id = "microsoft/Florence-2-base"
            
            # Load Processor
            logger.info("[1/2] Downloading Processor config...")
            processor = AutoProcessor.from_pretrained(model_id, trust_remote_code=True)
            
            # Load Model (AutoModelForCausalLM untuk versi 4.44)
            logger.info("[2/2] Downloading Model weights (largest file)...")
            local_model = AutoModelForCausalLM.from_pretrained(model_id, trust_remote_code=True).to(device)
            
            if device == "cuda":
                local_model.half()
                
            local_model.eval()
            _model_loaded = True
            logger.info(f"[OK] Florence-2 Model loaded on {device.upper()}")
        except Exception as e: 
            logger.error(f"Model load failed: {e}"); 
            raise

def get_caption_local(img_path):
    try:
        if not _model_loaded: load_local_ai_now()
        
        task_prompt = "<MORE_DETAILED_CAPTION>"
        
        with Image.open(img_path) as img:
            if img.mode != "RGB":
                img = img.convert("RGB")
            
            inputs = processor(text=task_prompt, images=img, return_tensors="pt").to(device)
            
            # === LOGIKA ADAPTIF: GPU vs CPU ===
            if device == "cuda":
                beams = 3      # GPU Kuat -> Kualitas Maksimal
                max_tokens = 100
            else:
                beams = 1      # CPU Lemah -> Kecepatan Kilat
                max_tokens = 100
            
            # Menghindari warning jika beams=1
            early_stop = True if beams > 1 else False
            # ==================================

            with torch.no_grad():
                generated_ids = local_model.generate(
                    input_ids=inputs["input_ids"],
                    pixel_values=inputs["pixel_values"],
                    max_new_tokens=max_tokens,
                    num_beams=beams,
                    early_stopping=early_stop
                )
            
            generated_text = processor.batch_decode(generated_ids, skip_special_tokens=False)[0]
            parsed_answer = processor.post_process_generation(generated_text, task=task_prompt, image_size=(img.width, img.height))
            
            caption = parsed_answer[task_prompt]
            
            # === TAMBAHAN: Bersihkan memori GPU setelah inferensi ===
            del inputs, generated_ids
            
            # Jika pakai Nvidia GPU, kosongkan cache VRAM
            if device == "cuda":
                torch.cuda.empty_cache()
            # -------------------------------------------------------
            
            return title_cleaner.clean(caption)
            
    except Exception as e: 
        logger.error(f"Local caption failed: {e}")
        api_monitor.record_failure("Local") 
        return "Stock Asset"

# --- 9. METADATA EMBEDDER ---
class MetadataEmbedder:
    @staticmethod
    def create_xmp_sidecar(file_path, title, keywords):
        """Membuat file XMP sidecar (untuk EPS, AI, MOV, dll)."""
        try:
            xmp_path = file_path + ".xmp"
            
            kw_list = [k.strip() for k in keywords.split(',') if k.strip()]
            kw_xml = "".join([f"<rdf:li>{kw}</rdf:li>" for kw in kw_list])
            
            xmp_content = f'''<?xpacket begin="" id="W5M0MpCehiHzreSzNTczkc9d"?>
<x:xmpmeta xmlns:x="adobe:ns:meta/">
 <rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#">
  <rdf:Description rdf:about=""
    xmlns:dc="http://purl.org/dc/elements/1.1/"
    xmlns:photoshop="http://ns.adobe.com/photoshop/1.0/">
   <dc:title><rdf:Alt><rdf:li xml:lang="x-default">{title}</rdf:li></rdf:Alt></dc:title>
   <dc:subject><rdf:Bag>{kw_xml}</rdf:Bag></dc:subject>
   <photoshop:Headline>{title}</photoshop:Headline>
  </rdf:Description>
 </rdf:RDF>
</x:xmpmeta>
<?xpacket end="w"?>'''

            with open(xmp_path, 'w', encoding='utf-8') as f:
                f.write(xmp_content)
            
            logger.info(f"[Embed] ✅ Created XMP Sidecar: {os.path.basename(xmp_path)}")
            return True
        except Exception as e:
            logger.error(f"XMP Sidecar failed: {e}")
            return False

    @staticmethod
    def embed_metadata(file_path, title, keywords, category):
        ext = os.path.splitext(file_path)[1].lower()
        logger.info(f"[Embed] Processing: {os.path.basename(file_path)} ({ext})")

        # === LANGKAH 1: COBA EXIFTOOL DULU (SOLUSI UTAMA) ===
        # ExifTool bisa menangani hampir semua format (JPG, PNG, MP4, PDF, AI, EPS, MOV)
        success, msg = run_exiftool(file_path, title, keywords)
        
        if success:
            logger.info(f"[Embed] ✅ Success via ExifTool: {file_path}")
            return True
        else:
            # Jika ExifTool belum terinstall atau gagal, gunakan metode lama (Fallback)
            logger.warning(f"[Embed] ExifTool failed ({msg}). Using Python fallback...")
            
            # === LANGKAH 2: FALLBACK KHUSUS FORMAT (KODE LAMA ANDA) ===
            
            # --- LOGIKA JPEG/JPG ---
            if ext in ('.jpg', '.jpeg'):
                try:
                    img = Image.open(file_path)
                    exif_dict = {"0th": {}, "Exif": {}}
                    if 'exif' in img.info:
                        try: exif_dict = piexif.load(img.info['exif'])
                        except: pass 
                    exif_dict["0th"][piexif.ImageIFD.ImageDescription] = title.encode('utf-8')
                    exif_bytes = piexif.dump(exif_dict)
                    img.save(file_path, "jpeg", exif=exif_bytes, quality=95)
                    img.close()

                    iptc = IPTCInfo(file_path, force=True)
                    kw_list = [k.strip().encode('utf-8') for k in keywords.split(',') if k.strip()]
                    iptc['keywords'] = kw_list
                    iptc['headline'] = title.encode('utf-8')
                    iptc.save()
                    
                    backup_path = file_path + "~"
                    if os.path.exists(backup_path):
                        try: os.remove(backup_path)
                        except: pass
                    logger.info(f"[Embed] ✅ JPEG embedded (Fallback): {file_path}")
                    return True
                except Exception as e: logger.error(f"[Embed] JPEG failed: {e}"); return False
            
            # --- LOGIKA PNG ---
            elif ext == '.png':
                try:
                    img = Image.open(file_path)
                    pnginfo = PngImagePlugin.PngInfo()
                    pnginfo.add_text("Title", title)
                    pnginfo.add_text("Keywords", keywords)
                    img.save(file_path, "PNG", pnginfo=pnginfo)
                    logger.info(f"[Embed] ✅ PNG embedded (Fallback): {file_path}")
                    return True
                except Exception as e: logger.error(f"[Embed] PNG failed: {e}"); return False
            
            # --- LOGIKA VIDEO MP4 ---
            elif ext == '.mp4':
                try:
                    video = MP4(file_path)
                    video["\xa9nam"] = title 
                    video["\xa9key"] = [k.strip() for k in keywords.split(',') if k.strip()]
                    video.save()
                    logger.info(f"[Embed] ✅ MP4 embedded (Fallback): {file_path}")
                    return True
                except Exception as e:
                    logger.warning(f"[Embed] MP4 fallback failed: {e}")
                    return MetadataEmbedder.create_xmp_sidecar(file_path, title, keywords)

            # --- LOGIKA PDF ---
            elif ext == '.pdf':
                try:
                    doc = fitz.open(file_path)
                    meta = doc.metadata
                    meta['title'] = title
                    meta['subject'] = keywords
                    meta['keywords'] = keywords
                    doc.set_metadata(meta)
                    doc.save(file_path, incremental=True, encryption=0)
                    doc.close()
                    logger.info(f"[Embed] ✅ PDF embedded (Fallback): {file_path}")
                    return True
                except Exception as e:
                    logger.error(f"[Embed] PDF failed: {e}")
                    return False

            # --- LOGIKA SVG ---
            elif ext == '.svg':
                try:
                    import xml.etree.ElementTree as ET
                    tree = ET.parse(file_path)
                    root = tree.getroot()
                    ns = {'svg': 'http://www.w3.org/2000/svg'}
                    
                    for item in root.findall('svg:title', ns): root.remove(item)
                    for item in root.findall('svg:desc', ns): root.remove(item)
                    
                    title_el = ET.SubElement(root, 'title')
                    title_el.text = title
                    desc_el = ET.SubElement(root, 'desc')
                    desc_el.text = keywords
                    
                    ET.register_namespace('', ns['svg'])
                    tree.write(file_path, encoding='utf-8', xml_declaration=True)
                    logger.info(f"[Embed] ✅ SVG embedded (Fallback): {file_path}")
                    return True
                except Exception as e:
                    logger.error(f"[Embed] SVG failed: {e}")
                    return False

            # --- LOGIKA LAIN (AI, EPS, MOV, AVI) -> PAKAI XMP SIDECAR ---
            else:
                return MetadataEmbedder.create_xmp_sidecar(file_path, title, keywords)

metadata_embedder = MetadataEmbedder()

# --- 9.5 MULTI-AGENCY CSV EXPORTER ---
class AgencyExporter:
    def __init__(self, output_dir):
        self.output_dir = output_dir
        self.files = {} # Menyimpan file handle
        self.writers = {} # Menyimpan csv writer
        
        # Konfigurasi Format Setiap Agensi (Verified)
        self.configs = {
            # 1. Adobe Stock: Category 0 = Auto Detect
            "Adobe Stock": {
                "filename": "adobe_stock_ready.csv",
                "header": ['Filename', 'File Type', 'Title', 'Keywords', 'Category', 'Releases', 'Metadata Embedded', 'Notes']
            },
            # 2. Shutterstock: Description & Keywords Wajib
            "Shutterstock": {
                "filename": "shutterstock_ready.csv",
                "header": ['Filename', 'Description', 'Keywords', 'Categories', 'Editorial', 'Mature content', 'Illustration']
            },
            # 3. 123RF: Format country biasanya ID
            "123RF": {
                "filename": "123rf_ready.csv",
                "header": ['oldfilename', '123rf_filename', 'description', 'keywords', 'country']
            },
            # 4. Vecteezy: Hapus kata 'vector' di keyword jika perlu
            "Vecteezy": {
                "filename": "vecteezy_ready.csv",
                "header": ['Filename', 'Title', 'Description', 'Keywords', 'License', 'Id']
            },
            # 5. Depositphotos
            "Depositphotos": {
                "filename": "depositphotos_ready.csv",
                "header": ['Filename', 'Title', 'Description', 'Keywords', 'Category', 'Nudity', 'Editorial']
            },
            # 6. Freepik
            "Freepik": {
                "filename": "freepik_ready.csv",
                "header": ['Filename', 'Title', 'Description', 'Keywords', 'Category']
            },
            # 7. Getty Images: Headline & Caption terpisah
            "Getty Images": {
                "filename": "getty_images_ready.csv",
                "header": ['Filename', 'Headline', 'Caption', 'Keywords', 'Category']
            },
            # 8. Miri Canvas
            "Miri Canvas": {
                "filename": "miri_canvas_ready.csv",
                "header": ['fileName', 'uniqueId', 'elementName', 'keywords', 'tier', 'contentType']
            }
        }
        
        self._init_files()

    def _init_files(self):
        """Membuka semua file CSV dan tulis header jika baru."""
        for agency, conf in self.configs.items():
            path = os.path.join(self.output_dir, conf['filename'])
            file_exists = os.path.isfile(path) and os.path.getsize(path) > 0
            
            # utf-8-sig untuk Excel
            f = open(path, 'a', newline='', encoding='utf-8-sig')
            writer = csv.writer(f, delimiter=',', quotechar='"', quoting=csv.QUOTE_MINIMAL)
            
            if not file_exists:
                writer.writerow(conf['header'])
            
            self.files[agency] = f
            self.writers[agency] = writer

    def write_row(self, data):
        """Menerjemahkan data umum ke format setiap agensi."""
        filename = data['filename']
        title = data['title']
        keywords = data['keywords']
        file_type = data['file_type']
        
        # 1. Adobe Stock (Category 0 = Auto Detect)
        self.writers["Adobe Stock"].writerow([
            filename, file_type, title, keywords, 0, 'no', 'yes', ''
        ])

        # 2. Shutterstock
        is_illustration = "Yes" if file_type == "vector" else "No"
        self.writers["Shutterstock"].writerow([
            filename, title, keywords, "Abstract", "no", "no", is_illustration
        ])

        # 3. 123RF
        self.writers["123RF"].writerow([
            filename, filename, title, keywords, "ID"
        ])

        # 4. Vecteezy
        clean_filename = filename.replace(':', '-')
        banned_words = ['vector', 'close-up', 'close_up']
        kw_list = [kw.strip() for kw in keywords.split(',')]
        filtered_kws = [kw for kw in kw_list if kw.lower() not in banned_words]
        clean_keywords = ", ".join(filtered_kws)
        self.writers["Vecteezy"].writerow([
            clean_filename, title, title, clean_keywords, "pro", ""
        ])

        # 5. Depositphotos
        self.writers["Depositphotos"].writerow([
            filename, title, title, keywords, "", "no", "no"
        ])

        # 6. Freepik
        self.writers["Freepik"].writerow([
            filename, title, title, keywords, 0
        ])

        # 7. Getty Images
        # Headline = Title, Caption = Title (Deskripsi)
        self.writers["Getty Images"].writerow([
            filename, title, title, keywords, ""
        ])

        # 8. Miri Canvas
        content_type = "vector" if file_type == "vector" else "image"
        self.writers["Miri Canvas"].writerow([
            filename, "", title, keywords, "Premium", content_type
        ])

    def close_all(self):
        """Tutup semua file dengan aman."""
        for f in self.files.values():
            try:
                f.close()
            except:
                pass

# --- 10. IMAGE & FILE OPTIMIZATION ---
def optimize_image_fast(img_path, output_path, max_size=1280): # Atau 1500
    try:
        with Image.open(img_path) as img:
            if img.mode in ('RGBA', 'LA', 'P'): img = img.convert('RGB')
            img.thumbnail((max_size, max_size), Image.Resampling.LANCZOS)
            img.save(output_path, "JPEG", quality=95, optimize=False)
            return os.path.getsize(output_path)
    except Exception as e: logger.error(f"Image optimization failed: {e}"); return 0

def resize_image_for_api(image_path, max_size=512):
    """
    Resize gambar di memori (RAM) menjadi max_size (512px) 
    untuk menghemat biaya dan kecepatan upload ke API.
    Mengembalikan data base64.
    """
    try:
        with Image.open(image_path) as img:
            # Konversi ke RGB jika RGBA/Mode lain
            if img.mode != "RGB":
                img = img.convert("RGB")
            
            # Resize (Pertahankan Aspect Ratio)
            # Thumbnail otomatis menghitung sisi terpanjang
            img.thumbnail((max_size, max_size), Image.Resampling.LANCZOS)
            
            # Simpan ke memori buffer (bukan file fisik)
            buffer = io.BytesIO()
            img.save(buffer, format="JPEG", quality=85) # Quality 85 cukup untuk AI
            buffer.seek(0)
            
            # Encode ke Base64
            return base64.b64encode(buffer.read()).decode('utf-8')
            
    except Exception as e:
        logger.error(f"Failed to resize for API: {e}")
        # Fallback: kirim original jika resize gagal
        try:
            with open(image_path, "rb") as f:
                return base64.b64encode(f.read()).decode('utf-8')
        except: return None

def extract_video_frames(video_path, output_dir, num_frames=3):
    frames = []
    try:
        cap = cv2.VideoCapture(video_path)
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        
        if total_frames == 0: return []

        # Logika Posisi
        if num_frames == 1:
            positions = [int(total_frames * 0.5)] # Tengah
        elif num_frames == 2:
            positions = [                          # Awal & Akhir (20% & 80%)
                int(total_frames * 0.2), 
                int(total_frames * 0.8)
            ]
        else: # 3 frame atau lebih
            positions = [
                int(total_frames * 0.1),
                int(total_frames * 0.5),
                int(total_frames * 0.9)
            ]

        for idx, target_frame in enumerate(positions):
            cap.set(cv2.CAP_PROP_POS_FRAMES, target_frame)
            ret, frame = cap.read()
            
            if ret and frame is not None:
                frame_path = os.path.join(output_dir, f"frame_{idx}.jpg")
                cv2.imwrite(frame_path, frame, [cv2.IMWRITE_JPEG_QUALITY, 95])
                frames.append(frame_path)

        cap.release()
        return frames

    except Exception as e:
        logger.error(f"Frame extraction failed: {e}")
        return []

def extract_video_frame_fast(video_path, output_path):
    """Mengambil 1 frame tengah saja (untuk API & Fallback)."""
    try:
        cap = cv2.VideoCapture(video_path)
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        if total_frames == 0: return False
        
        target_frame = total_frames // 2
        cap.set(cv2.CAP_PROP_POS_FRAMES, target_frame)
        ret, frame = cap.read()
        cap.release()
        
        if ret and frame is not None:
            cv2.imwrite(output_path, frame, [cv2.IMWRITE_JPEG_QUALITY, 95])
            return True
        return False
    except Exception as e:
        logger.error(f"Single frame extraction failed: {e}")
        return False

def detect_signature_visual(image_path, logger=None):
    """
    VISUAL DETECTOR v9 (Smart Skin Filter):
    1. Deteksi bentuk mencurigakan di pojok.
    2. CEK WARNA KULIT: Jika warnanya mirip kulit -> LEWATI (Pasti bagian tubuh/bad anatomy).
    3. Jika warnanya hitam/putih/tajam -> BARU TOLAK sebagai Signature.
    """
    try:
        img = cv2.imread(image_path)
        if img is None: return False, None

        h, w = img.shape[:2]
        margin_h = int(h * 0.18)
        margin_w = int(w * 0.18)

        corners = [
            ("Bottom-Right", img[h-margin_h:h, w-margin_w:w]),
            ("Bottom-Left",  img[h-margin_h:h, 0:margin_w]),
            ("Top-Right",    img[0:margin_h, w-margin_w:w]),
            ("Top-Left",     img[0:margin_h, 0:margin_w])
        ]

        for corner_name, crop in corners:
            gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
            
            # Metode Adaptif
            thresh = cv2.adaptiveThreshold(gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, 
                                          cv2.THRESH_BINARY_INV, 15, 5)

            contours, _ = cv2.findContours(thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            
            for cnt in contours:
                area = cv2.contourArea(cnt)
                crop_area = crop.shape[0] * crop.shape[1]
                
                # Filter Ukuran
                if area < 40 or area > (crop_area * 0.20): continue

                x, y, cw, ch = cv2.boundingRect(cnt)
                aspect_ratio = cw / float(ch) if ch > 0 else 1.0
                
                # Analisis Bentuk
                hull = cv2.convexHull(cnt)
                hull_area = cv2.contourArea(hull)
                solidity = (area / hull_area) if hull_area > 0 else 0
                
                perimeter = cv2.arcLength(cnt, True)
                complexity = (perimeter * perimeter) / area if area > 0 else 0

                is_logo = (solidity > 0.8) or (aspect_ratio > 2.5)
                is_handwriting = complexity > 25 
                
                if not (is_logo or is_handwriting):
                    continue 

                # === FILTER WARNA KULIT (SOLUSI UTAMA) ===
                mask = np.zeros(gray.shape, dtype=np.uint8)
                cv2.drawContours(mask, [cnt], -1, 255, -1)
                
                hsv_crop = cv2.cvtColor(crop, cv2.COLOR_BGR2HSV)
                mean_hsv = cv2.mean(hsv_crop, mask=mask)
                hue = mean_hsv[0]
                saturation = mean_hsv[1]
                
                # Logika Deteksi Kulit (Skin Tone)
                # Hue 0-25 (Merah ke Kuning), Saturation 15-100 (Tidak abu-abu)
                is_skin_tone = (hue < 25) and (saturation > 15 and saturation < 100)

                # Jika terdeteksi warna kulit -> LEWATI.
                # Kemungkinan besar ini adalah tangan/jari yang keluar masuk frame (Bad Anatomy).
                # Biarkan API (Mistral/Gemini) yang menolaknya sebagai "Bad Anatomy".
                if is_skin_tone:
                    if logger: logger.info(f"[Visual] Skin tone detected in {corner_name}. Ignoring (Likely body part).")
                    continue 
                # ========================================

                # Filter Tekstur (Khusus yang BUKAN kulit)
                mean_gray, std_gray = cv2.meanStdDev(gray, mask=mask)
                if saturation > 45 or std_gray[0][0] > 35:
                    continue 
                
                # KEPUTUSAN FINAL: TOLAK SEBAGAI SIGNATURE
                if logger: logger.info(f"[Visual] Reject in {corner_name} (Shape:{int(complexity)} Sat:{int(saturation)} Hue:{int(hue)})")
                return True, {"status": "VISUAL_REJECT", "score": 10}

        return False, None

    except Exception as e:
        if logger: logger.error(f"Visual error: {e}")
        return False, None

def convert_svg_to_image(svg_path, output_path, size=(800, 800)):
    """Mengkonversi file SVG menjadi gambar PNG menggunakan CairoSVG."""
    try:
        import cairosvg
        
        # Konversi SVG ke byte PNG
        png_data = cairosvg.svg2png(url=svg_path, output_width=size[0], output_height=size[1])
        
        # Buka byte data dengan Pillow
        img = Image.open(io.BytesIO(png_data))
        
        # Konversi ke RGB (hapus transparansi)
        if img.mode in ('RGBA', 'LA', 'P'):
            background = Image.new('RGB', img.size, (255, 255, 255))
            if img.mode == 'P':
                img = img.convert('RGBA')
            background.paste(img, mask=img.split()[-1] if img.mode in ('RGBA', 'LA') else None)
            img = background
            
        img.save(output_path, "PNG")
        logger.info(f"[SVG] Successfully converted {svg_path}")
        return True
        
    except Exception as e:
        logger.warning(f"[SVG] Conversion failed for {svg_path}: {e}. Using fallback blank image.")
        try:
            # Fallback jika error (misal windows butuh GTK)
            img = Image.new('RGB', size, color='white')
            img.save(output_path, "PNG")
            return True
        except Exception as e_fallback:
            logger.error(f"[SVG] Fallback also failed: {e_fallback}")
            return False

# --- 11. API REFINEMENT HELPER ---
def clean_json_response(text):
    """
    Pembersih JSON yang tangguh.
    1. Hapus Markdown.
    2. Hapus karakter ilegal.
    3. POTONG teks ekstra (Extra Data) di luar kurung kurawal {}.
    """
    text = text.strip()
    
    # 1. Hapus pembungkus markdown ```json ... ```
    if text.startswith("```json"):
        text = text[7:]
    if text.startswith("```"):
        text = text[3:]
    if text.endswith("```"):
        text = text[:-3]
    text = text.strip()

    # 2. Hapus karakter kontrol ilegal (Enter, Tab) yang bikin error di Mistral/Pixtral
    import re
    text = re.sub(r'[\x00-\x1f\x7f-\x9f]', ' ', text)
    
    # 3. PERBAIKAN "EXTRA DATA": Ambil hanya isi antara { dan } terakhir
    start_index = text.find('{')
    end_index = text.rfind('}')
    
    if start_index != -1 and end_index != -1 and end_index > start_index:
        text = text[start_index : end_index + 1]
    else:
        return ""

    return text

def run_exiftool(file_path, title, keywords):
    """
    Universal Metadata Embedder menggunakan ExifTool.
    """
    local_exiftool_path = os.path.join(BASE_DIR, "exiftool.exe")
    
    if os.path.exists(local_exiftool_path):
        exiftool_exe = local_exiftool_path
    else:
        exiftool_exe = "exiftool"

    try:
        kw_list = [k.strip() for k in keywords.split(',') if k.strip()]
        
        cmd = [
            exiftool_exe,
            '-overwrite_original',
            '-P',
            f'-Title={title}',
            f'-Description={title}',
            f'-Headline={title}',
            f'-Subject={",".join(kw_list)}', 
            f'-Keywords={",".join(kw_list)}', 
            file_path
        ]

        # Jalankan proses
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        
        if result.returncode == 0:
            return True, "Success"
        else:
            # === PERBAIKAN: TAMPILKAN KODE ERROR & STDOUT ===
            # Kadang ExifTool error tapi stderr kosong, infonya di stdout
            err_msg = result.stderr.strip()
            if not err_msg:
                err_msg = result.stdout.strip()
            
            # Jika masih kosong, tampilkan kode angka
            if not err_msg:
                err_msg = f"Exit Code: {result.returncode}"
                
            return False, err_msg
            
    except subprocess.TimeoutExpired:
        return False, "Timeout"
    except FileNotFoundError:
        return False, "ExifTool not installed"
    except Exception as e:
        return False, str(e)

# === TAMBAHKAN FUNGSI BARU INI DI SINI ===
def get_caption_online_vision(img_path, engine_name, api_key, min_len=35, max_len=75, min_kw=35, max_kw=49):
    """Mengirim gambar ke Vision API dengan Backoff + Jitter."""
    try:
        # 1. Resize gambar untuk hemat biaya
        base64_image = resize_image_for_api(img_path, max_size=512) # min. 512 - 768
        if not base64_image: return None

        # === PROMPT FINAL (AMAN BOKEH, TATO, KALIGRAFI) ===
        prompt_text = f"""
        Act as a Stock Photo Quality Inspector and SEO Expert.

        ROLE: Your job is to REJECT defective images and ACCEPT clean stock photos.
        LANGUAGE: REPLY IN ENGLISH ONLY.

        === REJECTION RULES (PRIORITY 1) ===
        Reject if found:
        - Watermarks or Signatures (Names/Logos in corners).
        - Bad Anatomy (Extra fingers, distorted limbs/faces).
        - Unintentional Blur (Camera shake, focus errors).
        - Copyrighted Text.

        === EXCEPTIONS (DO NOT REJECT) ===
        - Bokeh / Background Blur / Light Leaks (Artistic).
        - Tattoos on skin (Body art).
        - Calligraphy / Typography Art (Main subject).
        - Silhouettes / Shadows.

        === RESPONSE FORMAT (JSON ONLY) ===
        SCENARIO A (Defect Found):
        {{
            "is_rejected": true,
            "rejection_reasons": ["list reason here"],
            "title": "REJECTED",
            "keywords": "rejected"
        }}

        SCENARIO B (Clean/Good):
        {{
            "is_rejected": false,
            "title": "Descriptive Title ({min_len}-{max_len} chars)",
            "keywords": "relevant keywords ({min_kw}-{max_kw} keywords)"
        }}
        """
        max_retries = 3
        base_delay = 0.5 
        max_delay = 5.0
        
        for attempt in range(max_retries):
            try:
                response = None
                
                # --- KONFIGURASI PER ENGINE ---
                
                if engine_name == "Gemini":
                    # === TAMBAHKAN ROTASI MODEL DI SINI ===
                    GEMINI_MODELS = [
                        "gemini-3.1-flash-lite",
                        "gemini-2.5-flash-lite",
                        "gemini-1.5-flash-8b" # Cadangan
                    ]
                    
                    headers = {"Content-Type": "application/json"}
                    payload = {
                        "contents": [{"parts": [{"text": prompt_text}, {"inline_data": {"mime_type": "image/jpeg", "data": base64_image}}]}],
                        "generationConfig": {"responseMimeType": "application/json"}
                    }

                    gemini_success = False
                    response = None  # Inisialisasi awal untuk mencegah NameError

                    # LOOP MODEL ROTATION
                    for model_name in GEMINI_MODELS:
                        try:
                            logger.info(f"[Vision Gemini] Trying model: {model_name} (Attempt: {attempt + 1})")
                            url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={api_key}"
                            
                            response = requests.post(url, headers=headers, json=payload, timeout=30)
                            
                            if response.status_code == 200:
                                logger.info(f"[Vision Gemini] Success with {model_name}")
                                gemini_success = True
                                break  # Berhasil, keluar dari loop rotasi model
                            elif response.status_code in [429, 500, 503]:
                                logger.warning(f"[Vision Gemini] Model {model_name} Limit/Error ({response.status_code}). Rotating...")
                                continue  # Coba model berikutnya di dalam list
                            else:
                                logger.error(f"[Vision Gemini] Fatal Error on {model_name}: {response.text}")
                                break  # Error fatal (misal 400/403), hentikan rotasi model
                        except Exception as e:
                            logger.warning(f"[Vision Gemini] Conn Error on {model_name}: {e}")
                            continue
                            
                    # Jika seluruh model di list Gemini gagal, log ke monitor tetapi biarkan mengalir ke backoff global di bawah
                    if not gemini_success:
                        logger.error("[Vision Gemini] All rotated Gemini models failed in this attempt.")

                elif engine_name == "Groq":
                    url = "https://api.groq.com/openai/v1/chat/completions"
                    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
                    
                    model_id = "meta-llama/llama-4-scout-17b-16e-instruct"
                    
                    # Prompt ringkas untuk menghindari error blank
                    # groq_prompt = f"""
                    # Analyze image. Title ({min_len}-{max_len} chars). Keywords ({min_kw}-{max_kw}).
                    # Check defects: Bad anatomy, Watermarks, Logos.
                    # JSON output only.
                    # """

                    payload = {
                        "model": model_id,
                        "messages": [{"role": "user", "content": [{"type": "text", "text": prompt_text}, {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{base64_image}"}}]}],
                        "max_tokens": 200
                    }
                    response = requests.post(url, headers=headers, json=payload, timeout=30)

                elif engine_name == "Mistral":
                    url = "https://api.mistral.ai/v1/chat/completions"
                    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
                    
                    # PILIHAN MODEL:
                    # 1. "pixtral-12b-2409" -> Spesialis Vision (Paling Jeli untuk deteksi cacat)
                    # 2. "mistral-small-latest" -> Multimodal Umum (Sesuai screenshot, tapi kurang detail)
                    
                    model_id = "mistral-small-latest" 
                    
                    payload = {
                        "model": model_id,
                        "messages": [{"role": "user", "content": [{"type": "text", "text": prompt_text}, {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{base64_image}"}}]}],
                        "max_tokens": 200
                    }
                    response = requests.post(url, headers=headers, json=payload, timeout=30)

                # =====================================================
                # OPENAI (Berbayar - GPT-4o-mini)
                # =====================================================
                elif engine_name == "OpenAI":
                    url = "https://api.openai.com/v1/chat/completions"
                    headers = {
                        "Authorization": f"Bearer {api_key}",
                        "Content-Type": "application/json"
                    }
                    payload = {
                        "model": "gpt-4o-mini", # Model termurah & vision support
                        "messages": [
                            {
                                "role": "user",
                                "content": [
                                    {"type": "text", "text": prompt_text},
                                    {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{base64_image}"}}
                                ]
                            }
                        ],
                        "max_tokens": 200
                    }
                    response = requests.post(url, headers=headers, json=payload, timeout=30)

                # --- CEK HASIL RESPONSE ---
                if response and response.status_code == 200:
                    data = response.json()
                    content_str = ""
                    
                    if engine_name == "Gemini":
                        content_str = data['candidates'][0]['content']['parts'][0]['text']
                    else: 
                        content_str = data['choices'][0]['message']['content']
                    
                    cleaned = clean_json_response(content_str)
                    result = json.loads(cleaned)
                    return result
                
                # --- LOGIKA BACKOFF + JITTER JIKA GAGAL ---
                if attempt < max_retries - 1:
                    backoff_time = min(max_delay, base_delay * (2 ** attempt))
                    jitter = random.uniform(0, backoff_time * 0.5)
                    sleep_duration = backoff_time + jitter
                    sleep_duration = min(sleep_duration, max_delay)
                    
                    logger.warning(f"[Vision API] Error {response.status_code if response else 'No Resp'}. Retrying in {sleep_duration:.2f}s...")
                    time.sleep(sleep_duration)
                else:
                    logger.error(f"[Vision API] Final Fail: {response.status_code if response else 'Unknown'}")
                    api_monitor.record_failure(engine_name)
                    return None

            except requests.exceptions.RequestException as e:
                # ... (handling error koneksi sama seperti sebelumnya) ...
                if attempt < max_retries - 1:
                     time.sleep(2)
                else:
                    api_monitor.record_failure(engine_name)
                    return None

    except Exception as e:
        logger.error(f"[Vision API] Global Failed: {e}")
        api_monitor.record_failure(engine_name)
        return None

# --- 12. PROCESSING WORKER ---
def get_random_api_key(service_name, engine_name):
    """Mengambil satu API key secara acak dari penyimpanan."""
    raw_keys = get_api_key_from_keyring(service_name, engine_name)
    if not raw_keys:
        return None
    
    # Pecah string berdasarkan pemisah '|||'
    keys_list = raw_keys.split("|||")
    
    # Filter jika ada yang kosong
    valid_keys = [k for k in keys_list if k.strip()]
    
    if not valid_keys:
        return None
        
    # Kembalikan satu key secara acak (Rotasi Key)
    return random.choice(valid_keys)

def verify_api_online(engine_name, api_key):
    """Menguji koneksi API ke endpoint model (tanpa membuang token banyak)."""
    try:
        headers = {}
        url = ""
        
        if engine_name == "Groq":
            url = "https://api.groq.com/openai/v1/models"
            headers = {"Authorization": f"Bearer {api_key}"}
        elif engine_name == "Mistral":
            url = "https://api.mistral.ai/v1/models"
            headers = {"Authorization": f"Bearer {api_key}"}
        elif engine_name == "OpenAI":
            url = "https://api.openai.com/v1/models"
            headers = {"Authorization": f"Bearer {api_key}"}
        elif engine_name == "Gemini":
            # Gemini pakai key di parameter URL
            url = f"https://generativelanguage.googleapis.com/v1beta/models?key={api_key}"
        else:
            return False

        response = requests.get(url, headers=headers, timeout=10)
        return response.status_code == 200
        
    except Exception as e:
        logger.error(f"Verify API failed: {e}")
        return False

class ProcessingWorker(threading.Thread):
    def __init__(self, worker_id, task_queue, result_queue, engine, config):
        super().__init__(daemon=True)
        self.worker_id = worker_id
        self.task_queue = task_queue
        self.result_queue = result_queue
        self.engine = engine
        self.config = config

    def run(self):
        while True:
            task = self.task_queue.get()
            if task is None: break
            
            try:
                result = self.process_file(task[0], task[1], task[2], task[3])
                self.result_queue.put(result)
            except Exception as e:
                logger.error(f"Worker {self.worker_id} error: {e}")
                self.result_queue.put({'status': 'error', 'file': task[0], 'error': str(e), 'api_used': 'UNKNOWN'})
            finally:
                self.task_queue.task_done()

    def process_file(self, file_path, dest_dir, f_map, op_mode):
        name = os.path.basename(file_path)
        ext = os.path.splitext(name)[1].lower()
        temp_v = None
        api_used = "UNKNOWN"
        try:
            # === CEK STOP ===
            if self.config.get('stop_requested', False):
                logger.info(f"Skip {name}: Stop requested by user.")
                return {'status': 'error', 'file': file_path, 'error': 'Skipped (User Stop)', 'api_used': 'SYSTEM'}
            
            if not os.path.isfile(file_path) or not os.access(file_path, os.R_OK):
                logger.warning(f"Skip: File tidak ditemukan: {os.path.basename(file_path)}")
                return {'status': 'error', 'file': file_path, 'error': 'File not found at start', 'api_used': 'SYSTEM'}

            with tempfile.NamedTemporaryFile(suffix='.jpg', delete=False) as tmp: temp_v = tmp.name
            
            # --- PRA-PEROSES FILE ---
            if ext in ('.jpg', '.jpeg', '.png'):
                temp_v_opt = temp_v.replace('.jpg', '_opt.jpg')
                size = optimize_image_fast(file_path, temp_v_opt)
                if size > 0: temp_v = temp_v_opt
                else: temp_v = file_path
            elif ext == '.svg':
                if not convert_svg_to_image(file_path, temp_v): return {'status': 'error', 'file': file_path, 'error': 'SVG conversion failed', 'api_used': 'VECTOR_ERROR'}
            elif ext in ('.psd', '.eps'):
                try:
                    with Image.open(file_path) as img:
                        if img.mode in ('RGBA', 'LA', 'P'): img = img.convert('RGB')
                        img.thumbnail((1200, 1200), Image.Resampling.LANCZOS)
                        img.save(temp_v, "JPEG", quality=95)
                except:
                    img = Image.new('RGB', (800, 800), color='white')
                    img.save(temp_v, "JPEG")
            elif ext in ('.pdf', '.ai'):
                try:
                    doc = fitz.open(file_path)
                    page = doc.load_page(0)
                    pix = page.get_pixmap()
                    pix.save(temp_v)
                    doc.close()
                except:
                    img = Image.new('RGB', (800, 800), color='white')
                    img.save(temp_v, "JPEG")
            
            # === TAMBAHKAN BLOK INI UNTUK VIDEO ===
            elif ext in ('.mp4', '.mov', '.mkv', '.avi', '.mpeg'):
                # Untuk video, kita tidak perlu bikin 'temp_v' (preview) di sini
                # Karena frame akan di-extract nanti saat diproses API/Local
                # Biarkan temp_v sebagai path temporary kosong atau handle nanti
                pass 
            # ======================================
            
            else:
                # Fallback untuk tipe file lain (misal: .gif, .bmp, .webp, dll)
                # Coba optimasi sebagai gambar umum
                temp_v_opt = temp_v.replace('.jpg', '_opt.jpg')
                size = optimize_image_fast(file_path, temp_v_opt)
                if size > 0: temp_v = temp_v_opt
                else: temp_v = file_path
            
            # --- PENGATURAN ---
            min_len = self.config.get('min_title_len', 35)
            max_len = self.config.get('max_title_len', 75)
            min_kw = self.config.get('min_kw_len', 35)
            max_kw = self.config.get('max_kw_len', 49)
            
            caption = "Stock Asset"
            keywords_str = ""
            api_used = "UNKNOWN"
            local_caption = ""
            is_rejected = False
            reject_category = None
            rejection_detail = ""

            try:
                logger.info(f"[API] Starting analysis...")
                sorting_is_on = self.config.get('sorting_enabled', True)

                # ==========================================================
                # LOGIKA UTAMA: AI ANALYSIS (TANPA OPENCV)
                # ==========================================================

                # --- LOGIKA ROTASI API ---
                engines_to_try = []
                if self.engine == "Auto Rotate (Gemini/Mistral/Groq)":
                    candidates = ['Gemini', 'Mistral', 'Groq']
                    random.shuffle(candidates)
                    engines_to_try = candidates
                else:
                    engines_to_try = [self.engine]

                vision_result = None
                successful_engine = None
                
                # Siapkan file analisis
                file_to_analyze = temp_v
                is_video_temp = False
                if ext in ('.mp4', '.mov', '.mkv', '.avi', '.mpeg'):
                    temp_api_vid = tempfile.NamedTemporaryFile(suffix='.jpg', delete=False).name
                    if extract_video_frame_fast(file_path, temp_api_vid):
                        file_to_analyze = temp_api_vid
                        is_video_temp = True

                # === LOOP PERCOBAAN API ===
                for current_engine in engines_to_try:
                    if current_engine == "Local (BLIP)": continue
                    
                    api_key = get_random_api_key("NS-MetaRefiner", current_engine)
                    
                    if api_key:
                        logger.info(f"[Vision] Trying {current_engine}...")
                        vision_result = get_caption_online_vision(file_to_analyze, current_engine, api_key, min_len, max_len, min_kw, max_kw)
                        
                        if vision_result:
                            successful_engine = current_engine
                            
                            # === LOGIKA JIKA DITOLAK ===
                            if vision_result.get("is_rejected") == True:
                                is_rejected = True
                                reasons = vision_result.get("rejection_reasons", ["Defect detected by AI"])
                                rejection_detail = ", ".join(reasons)
                                
                                # === LOGIKA PEMILIH KATEGORI OTOMATIS ===
                                # Gabungkan alasan menjadi satu teks untuk dicek
                                reasons_text = " ".join(reasons).lower()
                                
                                # 1. PRIORITAS PERTAMA: Anatomi (Karena ini yang paling sering salah)
                                if any(word in reasons_text for word in ["anatomy", "finger", "limb", "face", "body", "distorted", "mutated", "malformed", "extra"]):
                                    reject_category = "AI-Artifact"
                                
                                # 2. PRIORITAS KEDUA: Watermark / Teks Terlarang
                                elif any(word in reasons_text for word in ["watermark", "signature", "logo", "text", "copyright", "stamp", "date"]):
                                    reject_category = "Watermark-Signature"
                                
                                # 3. PRIORITAS KETIGA: Masalah Teknis (Blur/Noise)
                                elif any(word in reasons_text for word in ["blur", "noise", "pixel", "quality", "focus", "dark", "bright", "exposed"]):
                                    reject_category = "Technical-Issue"
                                
                                # 4. PRIORITAS KEEMPAT: Orang Terkenal
                                elif any(word in reasons_text for word in ["celebrity", "famous", "public figure"]):
                                    reject_category = "Celebrity"
                                
                                # 5. DEFAULT: Jika tidak cocok kategori di atas
                                else:
                                    reject_category = "AI-Detected-Defect"
                                # ================================

                                caption = "REJECTED"
                                keywords_str = "rejected"
                                api_used = current_engine
                                logger.info(f"[Vision] {current_engine} REJECTED -> Category: {reject_category}")
                                break
                            
                            # === TAMBAHKAN BAGIAN INI: LOGIKA JIKA DITERIMA ===
                            else:
                                # Ambil Judul dan Keywords dari JSON API
                                caption = vision_result.get("title", "Stock Asset")
                                keywords_str = vision_result.get("keywords", "")
                                
                                # Update local_caption untuk keperluan sortir duplikat
                                local_caption = caption 
                                
                                api_used = current_engine
                                logger.info(f"[Vision] {current_engine} ACCEPTED.")
                                break # Hentikan loop karena sudah sukses
                            # ===================================================
                        
                        else:
                            logger.warning(f"[Vision] {current_engine} FAILED. Trying next...")
                            api_monitor.record_failure(current_engine)
                    else:
                        logger.warning(f"[Vision] No API Key for {current_engine}. Skipping...")
                
                # Bersihkan file video sementara
                if is_video_temp and os.path.exists(file_to_analyze):
                    try: os.remove(file_to_analyze)
                    except: pass
                
                # === FALLBACK KE LOCAL (BLIP) ===
                if not vision_result:
                    n_frames = 1 if device == "cpu" else 3
                    
                    if ext in ('.mp4', '.mov', '.mkv', '.avi', '.mpeg'):
                        temp_dir_loc = tempfile.mkdtemp()
                        extracted_frames = extract_video_frames(file_path, temp_dir_loc, num_frames=n_frames)
                        if not extracted_frames:
                            single_temp = os.path.join(temp_dir_loc, "fallback.jpg")
                            if extract_video_frame_fast(file_path, single_temp):
                                extracted_frames = [single_temp]
                        if extracted_frames:
                            all_captions = []
                            for frame_img in extracted_frames:
                                all_captions.append(get_caption_local(frame_img))
                            local_caption = " Scene: ".join(all_captions)
                            try: shutil.rmtree(temp_dir_loc)
                            except: pass
                        else:
                            local_caption = "Video footage"
                    else:
                        local_caption = get_caption_local(temp_v)
                    
                    caption = local_caption
                    keywords_str = seo_optimizer.generate_seo_keywords(caption)
                    api_used = "LOCAL (Fallback)" if self.engine != "Local (BLIP)" else "LOCAL"
                    logger.info(f"[Process] Using Local AI.")

            except Exception as e:
                logger.error(f"[API] Hybrid process failed: {e}")
                caption = "Stock Asset"
                keywords_str = ""
                api_used = "ERROR"

            # --- SORTIR AI (TEXT BASED) ---
            if sorting_is_on:
                
                # === PERBAIKAN: Cek dulu apakah API sudah menolak ===
                # Jika API sudah menolak (is_rejected = True), LEWATI text sorter ini.
                # Jika API belum menolak (is_rejected = False), baru cek teks lokal.
                if not is_rejected:
                    is_rejected, reasons, reject_category = image_sorter.check_if_rejected(local_caption)
                # ===================================================
                
                # === AKTIVASI VISUAL CHECK v8 (SMART CONTEXT) ===
                # Jika lolos cek teks, cek visual watermark
                if not is_rejected:
                    
                    # --- KONDISI BARU: HANYA JALANKAN OPENCV JIKA PAKAI BLIP (LOCAL) ---
                    if "LOCAL" in api_used:
                        
                        # Filter Konteks (Skip untuk kaligrafi/tato)
                        skip_visual_keywords = [
                            "calligraphy", "kaligrafi", "inscription", 
                            "tattoo", "tattoos", "crack", "cracks", "cracked", 
                            "vein", "veins", "leaf"
                        ]
                        is_complex_content = any(word in local_caption.lower() for word in skip_visual_keywords)
                        
                        if is_complex_content:
                            logger.info(f"[Sortir Visual] Skip: Complex content detected.")
                        else:
                            # Jalankan Visual Check
                            vis_rejected, vis_data = detect_signature_visual(temp_v, logger)
                            
                            if vis_rejected:
                                is_rejected = True
                                reasons = ["visual watermark detected"]
                                reject_category = "Watermark-Signature"
                                
                                if isinstance(vis_data, dict):
                                    log_status = vis_data.get("status", "DETECTED")
                                    logger.info(f"[Sortir Visual] Reject: {log_status} (File moved to: {reject_category})")
                                else:
                                    logger.info(f"[Sortir Visual] Reject: {vis_data}")
                                    
                    # --- AKHIR KONDISI LOCAL ---

                # ================================================                               

                if is_rejected:
                    api_used = "REJECTED"
                    caption = f"REJECTED: {', '.join(reasons)}"
                    keywords_str = "rejected"
                    rejection_detail = ', '.join(reasons)
                    logger.info(f"[Sortir AI] Reject: {reasons}")
                else:
                    logger.info(f"[Sortir AI] ACCEPTED.")
                    if "LOCAL" in api_used:
                        api_monitor.record_success("Local")
                    elif successful_engine:
                        api_monitor.record_success(successful_engine)

            # --- PROSES HASIL ---
            title = title_cleaner.clean(caption)
            
            # Logika Title Enhancement
            max_len = self.config.get('max_title_len', 75)
            min_len = self.config.get('min_title_len', 35)
            generic_words = ["background", "wallpaper", "stock asset", "image", "photo"]
            is_weak = len(title) < min_len or any(w in title.lower() for w in generic_words)
            if is_weak and keywords_str:
                top_kws = [k.strip().capitalize() for k in keywords_str.split(',')[:2] if k.strip()]
                if top_kws: title = f"{title} {' '.join(top_kws)}"
            if len(title) > max_len: title = title[:max_len].rsplit(' ', 1)[0]
            if not keywords_str: keywords_str = seo_optimizer.generate_seo_keywords(title)
            
            category = 0
            title = duplicate_handler.get_unique_title(title, keywords_str)
           
            # === PERBAIKAN: SANITASI NAMA FILE DENGAN UNDERSCORE ===
            # 1. Hapus karakter ilegal (Windows tidak suka: \ / : * ? " < > |)
            sanitized = re.sub(r'[\\/*?:"<>|]', '', title).strip()
            
            # 2. Ganti Spasi dengan Underscore (Untuk Vecteezy/Adobe)
            sanitized = sanitized.replace(' ', '_')
            
            # 3. Hapus underscore ganda (misal "Beautiful__Sunset" -> "Beautiful_Sunset")
            while '__' in sanitized:
                sanitized = sanitized.replace('__', '_')
            
            # 4. Batasi panjang dan buang kata terakhir jika terpotong
            sanitized = sanitized[:80]
            
            # Cek jika terpotong (tidak full), buang kata terakhir yang mungkin terpenggal
            if len(sanitized) >= 80 and '_' in sanitized:
                sanitized = sanitized.rsplit('_', 1)[0]
                
            sanitized = sanitized.strip('_')
            
            # Fallback jika judul kosong
            if not sanitized:
                first_kw = keywords_str.split(',')[0].strip() if keywords_str else ""
                if first_kw: 
                    sanitized = re.sub(r'[\\/*?:"<>|]', '', first_kw).replace(' ', '_').strip('_')
                if not sanitized:
                    original_name = os.path.splitext(os.path.basename(file_path))[0]
                    sanitized = re.sub(r'[\\/*?:"<>|]', '', original_name).replace(' ', '_').strip('_')
                if not sanitized: 
                    sanitized = f"asset_{int(time.time())}"
            # ========================================================
            
            new_name = f"{sanitized}{ext}"
            
            # Folder logic
            if is_rejected:
                final_dest_dir = os.path.join(dest_dir, "Rejected", reject_category)
            else:
                final_dest_dir = dest_dir
            
            os.makedirs(final_dest_dir, exist_ok=True)
            dest_path = os.path.join(final_dest_dir, new_name)
            
            if os.path.exists(dest_path):
                base, ext_part = os.path.splitext(new_name)
                counter = 1
                while os.path.exists(os.path.join(final_dest_dir, f"{base}{counter}{ext_part}")):
                    counter += 1
                new_name = f"{base}{counter}{ext_part}"
                dest_path = os.path.join(final_dest_dir, new_name)
            
            shutil.copy2(file_path, dest_path)
            
            if not is_rejected:
                metadata_embedder.embed_metadata(dest_path, title, keywords_str, category)
                embedded = "yes"
            else:
                embedded = "no"
            
            if op_mode == "move":
                try:
                    if os.path.exists(dest_path) and os.path.getsize(dest_path) > 0:
                        os.remove(file_path)
                except: pass
            
            file_type = "image" if ext in ('.jpg', '.png', '.jpeg') else "video" if ext in ('.mp4', '.mov') else "vector"
            notes = "Metadata embedded" if file_type == "image" else "Use Adobe Stock Video Uploader" if file_type == "video" else "Convert to PDF recommended"
            
            return {
                'status': 'success', 'file': file_path, 'filename': new_name, 'title': title,
                'keywords': keywords_str, 'category': category, 'releases': 'no', 'file_type': file_type,
                'embedded': embedded, 'notes': notes, 'dest': dest_path, 'api_used': api_used,
                'rejection_detail': rejection_detail
            }
        except Exception as e:
            logger.error(f"[Process] Error: {e}")
            return {'status': 'error', 'file': file_path, 'error': str(e), 'api_used': api_used}
        finally:
            if temp_v and os.path.exists(temp_v): os.remove(temp_v)

# --- AUTO INSTALLER HELPER ---
TOOL_URLS = {
    # Link resmi Ghostscript
    "Ghostscript": "https://github.com/ArtifexSoftware/ghostpdl-downloads/releases/download/gs10030/gs10030w64.exe",
    # Link resmi GTK
    "GTK3": "https://github.com/tschoonj/GTK-for-Windows-Runtime-Environment-Installer/releases/download/2022-01-04/gtk3-runtime-2022-01-04-ts-win64.exe",
    # === LINK EXIFTOOL (Versi 32-bit Agar Universal) ===
    "ExifTool": "https://exiftool.org/exiftool-13.58_32.zip"   # https://exiftool.org/exiftool-13.58_64.zip
}

def check_tool_installed(name):
    """Cek apakah tool sudah ada."""
    try:
        if name == "Ghostscript":
            subprocess.run(['gswin64c', '--version'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
            return True
        elif name == "GTK3":
            subprocess.run(['where', 'libgtk-3-0.dll'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
            return True
        elif name == "ExifTool":
            # Cek di folder aplikasi dulu
            local_path = os.path.join(BASE_DIR, "exiftool.exe")
            if os.path.exists(local_path):
                return True
            # Cek di system path
            subprocess.run(['exiftool', '-ver'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
            return True
    except:
        return False
    return False

def install_tool(name, url):
    """Download dan install tool ke folder aplikasi."""
    try:
        logger.info(f"[Installer] Downloading {name}...")
        
        installer_path = os.path.join(tempfile.gettempdir(), f"{name}_setup.zip" if name == "ExifTool" else f"{name}_setup.exe")
        
        # 1. Download
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
        response = requests.get(url, stream=True, headers=headers, allow_redirects=True)
        response.raise_for_status()
        
        with open(installer_path, 'wb') as f:
            for chunk in response.iter_content(chunk_size=8192):
                f.write(chunk)
        
        file_size = os.path.getsize(installer_path)
        logger.info(f"[Installer] Download complete: {file_size} bytes.")
        
        if name == "ExifTool" and file_size < 5000000:
            logger.error("Download failed: Zip file is too small.")
            return False

        # 2. Logika Khusus ExifTool (Ekstrak Semua)
        if name == "ExifTool":
            import zipfile
            import shutil
            try:
                with zipfile.ZipFile(installer_path, 'r') as zip_ref:
                    logger.info("Extracting all files from ZIP...")
                    
                    # Ekstrak SEMUA isi zip ke folder sementara dulu
                    temp_extract_dir = os.path.join(tempfile.gettempdir(), "exiftool_temp")
                    if os.path.exists(temp_extract_dir):
                        shutil.rmtree(temp_extract_dir)
                    
                    zip_ref.extractall(temp_extract_dir)
                    
                    # Cari file exiftool(-k).exe di dalam folder hasil ekstrak
                    found_exe = None
                    for root, dirs, files in os.walk(temp_extract_dir):
                        for file in files:
                            if file.lower() in ['exiftool(-k).exe', 'exiftool.exe']:
                                found_exe = os.path.join(root, file)
                                break
                        if found_exe: break
                    
                    if found_exe:
                        # Pindahkan file exe ke BASE_DIR dengan nama exiftool.exe
                        dest_exe = os.path.join(BASE_DIR, "exiftool.exe")
                        shutil.move(found_exe, dest_exe)
                        
                        # PENTING: Pindahkan juga folder 'exiftool_files' jika ada
                        # Karena exiftool versi ini butuh folder tersebut
                        src_lib_folder = os.path.join(os.path.dirname(found_exe), "exiftool_files")
                        if os.path.exists(src_lib_folder):
                            dest_lib_folder = os.path.join(BASE_DIR, "exiftool_files")
                            # Hapus folder lama jika ada
                            if os.path.exists(dest_lib_folder):
                                shutil.rmtree(dest_lib_folder)
                            shutil.move(src_lib_folder, dest_lib_folder)
                            logger.info("Moved 'exiftool_files' folder.")

                        logger.info(f"[Installer] ✅ SUCCESS: ExifTool installed.")
                        return True
                    else:
                        logger.error("Exiftool executable not found after extraction.")
                        return False

            except zipfile.BadZipFile:
                logger.error("Downloaded file is not a valid ZIP.")
                return False
            except Exception as e:
                logger.error(f"Extraction error: {e}")
                return False

        # Logika Installer Lain
        else:
            logger.info(f"[Installer] Running {name} installer...")
            ctypes.windll.shell32.ShellExecuteW(None, "runas", installer_path, "/S", None, 1)
            return True
            
    except Exception as e:
        logger.error(f"Install failed: {e}")
        return False
        # ============================================

def check_and_prompt_installation():
    """Fungsi utama untuk mengecek dan menawarkan instalasi."""
    missing_tools = []
    
    if not check_tool_installed("Ghostscript"):
        missing_tools.append("Ghostscript (Untuk file EPS)")
    
    if not check_tool_installed("GTK3"):
        missing_tools.append("GTK3 Runtime (Untuk file SVG)")

    # === TAMBAHKAN CEK EXIFTOOL ===
    if not check_tool_installed("ExifTool"):
        missing_tools.append("ExifTool (Untuk Metadata Video/Adobe)")
    # ==============================

    if missing_tools:
        # Tanyakan ke user via MsgBox
        msg = "Diperlukan software tambahan untuk dukungan penuh:\n\n"
        msg += "\n".join([f"- {t}" for t in missing_tools])
        msg += "\n\nInstall otomatis sekarang? (Butuh koneksi internet)"
        
        if messagebox.askyesno("Missing Tools", msg):
            installed_any = False
            # === TAMBAHKAN "ExifTool" KE DAFTAR LOOP ===
            for tool in ["Ghostscript", "GTK3", "ExifTool"]:
                # Hanya install yang belum ada (cek string di missing_tools)
                if any(tool in t for t in missing_tools):
                    if install_tool(tool, TOOL_URLS[tool]):
                        installed_any = True
            
            if installed_any:
                messagebox.showwarning("Restart Required", 
                    "Proses instalasi dimulai di background.\n\nTUNGGU sebentar hingga selesai, lalu RESTART aplikasi ini.")

# --- 13. UI ---
class NSMetaRefinerApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        # Judul Window
        self.title(f"{APP_NAME} v{CURRENT_VERSION}   |   Intelligent Metadata & Sorting")

        # === OTOMATIS SEMBUNYIKAN CONSOLE SAAT MULAI ===
        try:
            console_window = ctypes.windll.kernel32.GetConsoleWindow()
            if console_window:
                ctypes.windll.user32.ShowWindow(console_window, 0) # 0 = Hide
                self.console_visible = False
        except:
            pass
        # ==============================================
        
        # === PENGATURAN UKURAN JENDELA (Tulis sekali saja di sini) ===
        self.geometry("960x850")
        self.minsize(960, 850) # Tambahan: Agar window tidak bisa dikecilkan
        # ============================================================
        
        self.configure(fg_color="#121212")
        # === PASANG ICON JENDELA (TASKBAR & TITLE BAR) ===
        ico_path = resource_path("logo.ico")
        # -----------------------
        if os.path.exists(ico_path):
            self.iconbitmap(ico_path)
        # ================================================
        self.config_data = load_config()
        self.selected_paths = []
        self.out_path = ""
        self.stop_requested = False
        self.sorting_enabled = ctk.BooleanVar(value=True)  # Gunakan BooleanVar untuk Switch
        
        # Variabel Show/Hide
        self.keys_visible = self.config_data.get("keys_visible", True)
        self.hidden_key_data = ""
        
        self.setup_ui()
        self.on_engine_change(self.engine_var.get())
        
        # === 1. LOAD PENGATURAN NUMERIK ===
        if 'min_title_len' in self.config_data:
            self.min_title_entry.delete(0, "end")
            self.min_title_entry.insert(0, str(self.config_data['min_title_len']))
        if 'max_title_len' in self.config_data:
            self.max_title_entry.delete(0, "end")
            self.max_title_entry.insert(0, str(self.config_data['max_title_len']))
        if 'min_kw_len' in self.config_data:
            self.min_kw_entry.delete(0, "end")
            self.min_kw_entry.insert(0, str(self.config_data['min_kw_len']))
        if 'max_kw_len' in self.config_data:
            self.max_kw_entry.delete(0, "end")
            self.max_kw_entry.insert(0, str(self.config_data['max_kw_len']))
        if 'worker_count' in self.config_data:
            self.worker_count_entry.delete(0, "end")
            self.worker_count_entry.insert(0, str(self.config_data['worker_count']))
        if 'delay' in self.config_data:
            self.delay_entry.delete(0, "end")
            self.delay_entry.insert(0, str(self.config_data['delay']))

        # === 2. LOAD PATH & AUTO FILL FILE (GANTI BAGIAN INI) ===
        # Load Output Dir
        if 'last_output_dir' in self.config_data and os.path.exists(self.config_data['last_output_dir']):
            self.out_path = self.config_data['last_output_dir']
            self.out_label.configure(text=self.out_path[-40:], text_color="#2ecc71")
        
        # Load Input Dir + Auto Scan File
        if 'last_input_dir' in self.config_data and os.path.exists(self.config_data['last_input_dir']):
            saved_dir = self.config_data['last_input_dir']
            
            # 1. Update Label Path
            display_text = saved_dir
            if len(saved_dir) > 45: display_text = "..." + saved_dir[-42:]
            self.in_label.configure(text=display_text, text_color="#2ecc71")
            
            # 2. Otomatis isi list file
            try:
                valid_exts = ('.jpg', '.jpeg', '.png', '.mp4', '.mov', '.mkv', '.avi', '.mpeg', '.svg', '.eps', '.psd', '.pdf', '.ai')
                files_found = [
                    os.path.join(saved_dir, f) for f in os.listdir(saved_dir) 
                    if f.lower().endswith(valid_exts) and os.path.isfile(os.path.join(saved_dir, f))
                ]
                
                if files_found:
                    self.selected_paths = files_found
                    self.file_list_box.delete("1.0", "end")
                    for i, p in enumerate(self.selected_paths):
                        self.file_list_box.insert("end", f"{i+1}. {os.path.basename(p)}\n")
                    self.val_r.set(f"LEFT: {len(self.selected_paths)}")
            except Exception as e:
                logger.error(f"Failed to auto-load input files: {e}")
        # ==============================================

        logger.info("App started")
        
        # Cek tools installer
        threading.Thread(target=check_and_prompt_installation, daemon=True).start()

        self.check_for_updates()
    
    def setup_ui(self):
        # --- HEADER (Minimalis: Hanya Tombol Aksi) ---
        header_frame = ctk.CTkFrame(self, fg_color="transparent")
        header_frame.pack(pady=(10, 5), fill="x")

        # Tombol DONATE (Pojok Kanan)
        donate_btn = ctk.CTkButton(
            header_frame, 
            text="♥ DONATE", 
            command=lambda: webbrowser.open("https://sociabuzz.com/ns_metarefiner/donate"),
            font=("Segoe UI", 11, "bold"),
            fg_color="#d4af37",
            text_color="#000000",
            hover_color="#c19a2e",
            height=30,
            width=80
        )
        donate_btn.pack(side="right", padx=15, pady=5)
        
        # --- MAIN CONTAINER ---
        main_box = ctk.CTkFrame(self, fg_color="transparent")
        main_box.pack(fill="both", expand=True, padx=15, pady=5)
        
        # === LEFT COLUMN ===
        self.left_col = ctk.CTkFrame(main_box, fg_color="transparent", width=400)
        self.left_col.pack(side="left", fill="y", padx=(0, 10))
        self.left_col.pack_propagate(False) 

        # 1. API ENGINE
        self.api_frame = ctk.CTkFrame(self.left_col, fg_color="#1E1E1E", corner_radius=8)
        self.api_frame.pack(fill="x", pady=(0, 5))
        
        ctk.CTkLabel(self.api_frame, text="AI ENGINE", font=("Segoe UI", 12, "bold"), text_color="#d4af37").place(x=10, y=5)
        self.engine_var = ctk.StringVar(value=self.config_data.get("last_engine", "Local (BLIP)"))
        self.engine_menu = ctk.CTkOptionMenu(self.api_frame, variable=self.engine_var, values=["Local (BLIP)", "Auto Rotate (Gemini/Mistral/Groq)", "Gemini", "Groq", "Mistral", "OpenAI (Premium)"], command=self.on_engine_change, height=28, font=("Segoe UI", 11))
        self.engine_menu.pack(fill="x", padx=10, pady=(28, 5))

        # === AREA INPUT API (Entry + Tombol) ===
        self.input_area_frame = ctk.CTkFrame(self.api_frame, fg_color="transparent")
        self.input_area_frame.pack(fill="x", padx=10, pady=5)

        self.api_key_entry = ctk.CTkTextbox(self.input_area_frame, height=50, fg_color="#0D0D0D", font=("Consolas", 11), wrap="none")
        self.api_key_entry.pack(fill="x")
        
        btn_row = ctk.CTkFrame(self.input_area_frame, fg_color="transparent")
        btn_row.pack(fill="x", pady=(5, 0))
        ctk.CTkButton(btn_row, text="Save API", command=self.save_current_config, height=26, fg_color="#1F6AA5", font=("Segoe UI", 11)).pack(side="left", expand=True, fill="x", padx=(0,2))
        ctk.CTkButton(btn_row, text="Check", command=self.check_api_status, height=26, fg_color="#d4af37", text_color="#000", font=("Segoe UI", 11)).pack(side="left", expand=True, fill="x", padx=(2,0))
        self.toggle_btn = ctk.CTkButton(btn_row, text="Hide", command=self.toggle_key_visibility, height=26, fg_color="#555", font=("Segoe UI", 11), width=60)
        self.toggle_btn.pack(side="left", padx=(5,0))

        # === AREA INFO (Hanya Muncul saat Local/Auto) ===
        self.api_info_label = ctk.CTkLabel(self.api_frame, text="", font=("Segoe UI", 11), text_color="#AAAAAA", justify="left", wraplength=380, height=80)

        self.api_status_text = ctk.CTkLabel(self.api_frame, text="Status: Ready", font=("Consolas", 10), text_color="#888")
        self.api_status_text.pack(pady=(0, 5))

        # 2. INPUT FILES
        input_frame = ctk.CTkFrame(self.left_col, fg_color="#1E1E1E", corner_radius=8)
        input_frame.pack(fill="x", pady=(0, 5))
        ctk.CTkLabel(input_frame, text="INPUT FILES", font=("Segoe UI", 12, "bold"), text_color="#d4af37").place(x=10, y=8)
        
        in_row = ctk.CTkFrame(input_frame, fg_color="transparent")
        in_row.pack(fill="x", padx=10, pady=(28, 5))
        self.in_mode = ctk.StringVar(value="file")
        ctk.CTkRadioButton(in_row, text="File", variable=self.in_mode, value="file", font=("Segoe UI", 11)).pack(side="left")
        ctk.CTkRadioButton(in_row, text="Folder", variable=self.in_mode, value="folder", font=("Segoe UI", 11)).pack(side="left", padx=5)
        ctk.CTkButton(in_row, text="BROWSE", width=60, height=26, fg_color="#2D8A4E", command=self.add_input, font=("Segoe UI", 11)).pack(side="right")

        self.in_label = ctk.CTkLabel(input_frame, text="No input selected", text_color="#666", font=("Segoe UI", 11), anchor="w")
        self.in_label.pack(fill="x", padx=10, pady=(0, 2))

        self.file_list_box = ctk.CTkTextbox(input_frame, height=80, fg_color="#0D0D0D", font=("Consolas", 11), text_color="#888")
        self.file_list_box.pack(fill="x", padx=10, pady=5)
        ctk.CTkButton(input_frame, text="CLEAR LIST", width=80, height=24, fg_color="#C42B2B", command=self.clear_input, font=("Segoe UI", 11)).pack(anchor="e", padx=10, pady=(0, 5))

        # 3. OUTPUT FILES
        output_frame = ctk.CTkFrame(self.left_col, fg_color="#1E1E1E", corner_radius=8)
        output_frame.pack(fill="x", pady=(0, 5))
        ctk.CTkLabel(output_frame, text="OUTPUT FILES", font=("Segoe UI", 12, "bold"), text_color="#d4af37").place(x=10, y=8)
        
        row_mode = ctk.CTkFrame(output_frame, fg_color="transparent")
        row_mode.pack(fill="x", padx=10, pady=(28, 5))
        
        self.op_mode = ctk.StringVar(value="copy")
        ctk.CTkRadioButton(row_mode, text="Copy", variable=self.op_mode, value="copy", font=("Segoe UI", 11)).pack(side="left")
        ctk.CTkRadioButton(row_mode, text="Move", variable=self.op_mode, value="move", font=("Segoe UI", 11)).pack(side="left", padx=5)
        ctk.CTkButton(row_mode, text="BROWSE", width=70, height=26, fg_color="#1F6AA5", command=self.select_output, font=("Segoe UI", 11)).pack(side="right")

        self.out_label = ctk.CTkLabel(output_frame, text="No output selected", text_color="#666", font=("Segoe UI", 11), anchor="w")
        self.out_label.pack(fill="x", padx=10, pady=(0, 5))

        # 4. ADVANCED SETTINGS
        adv_frame = ctk.CTkFrame(self.left_col, fg_color="#1E1E1E", corner_radius=8)
        adv_frame.pack(fill="x", pady=(0, 5))
        ctk.CTkLabel(adv_frame, text="ADVANCED SETTINGS", font=("Segoe UI", 12, "bold"), text_color="#d4af37").place(x=10, y=8)

        set_grid = ctk.CTkFrame(adv_frame, fg_color="transparent")
        set_grid.pack(fill="x", padx=10, pady=(28, 10))
        set_grid.grid_columnconfigure((0,1,2), weight=1)

        # Kolom 1
        col1 = ctk.CTkFrame(set_grid, fg_color="transparent")
        col1.grid(row=0, column=0, padx=5, pady=5, sticky="nsew")
        ctk.CTkLabel(col1, text="TITLE LIMITS", font=("Segoe UI", 10, "bold"), text_color="#AAA").pack()
        r1_1 = ctk.CTkFrame(col1, fg_color="transparent"); r1_1.pack(fill="x", pady=2)
        ctk.CTkLabel(r1_1, text="Min:", font=("Segoe UI", 9), width=25, anchor="w").pack(side="left")
        self.min_title_entry = ctk.CTkEntry(r1_1, width=30, height=24, font=("Segoe UI", 11))
        self.min_title_entry.insert(0, "35")
        self.min_title_entry.pack(side="right", expand=True, fill="x")

        r1_2 = ctk.CTkFrame(col1, fg_color="transparent"); r1_2.pack(fill="x", pady=2)
        ctk.CTkLabel(r1_2, text="Max:", font=("Segoe UI", 9), width=25, anchor="w").pack(side="left")
        self.max_title_entry = ctk.CTkEntry(r1_2, width=30, height=24, font=("Segoe UI", 11))
        self.max_title_entry.insert(0, "75")
        self.max_title_entry.pack(side="right", expand=True, fill="x")

        # Kolom 2
        col2 = ctk.CTkFrame(set_grid, fg_color="transparent")
        col2.grid(row=0, column=1, padx=5, pady=5, sticky="nsew")
        ctk.CTkLabel(col2, text="KEYWORDS (Qty)", font=("Segoe UI", 10, "bold"), text_color="#AAA").pack()
        
        r2_1 = ctk.CTkFrame(col2, fg_color="transparent"); r2_1.pack(fill="x", pady=2)
        ctk.CTkLabel(r2_1, text="Min:", font=("Segoe UI", 9), width=25, anchor="w").pack(side="left")
        self.min_kw_entry = ctk.CTkEntry(r2_1, width=30, height=24, font=("Segoe UI", 11))
        self.min_kw_entry.insert(0, "40")
        self.min_kw_entry.pack(side="right", expand=True, fill="x")

        r2_2 = ctk.CTkFrame(col2, fg_color="transparent"); r2_2.pack(fill="x", pady=2)
        ctk.CTkLabel(r2_2, text="Max:", font=("Segoe UI", 9), width=25, anchor="w").pack(side="left")
        self.max_kw_entry = ctk.CTkEntry(r2_2, width=30, height=24, font=("Segoe UI", 11))
        self.max_kw_entry.insert(0, "49")
        self.max_kw_entry.pack(side="right", expand=True, fill="x")

        # Kolom 3
        col3 = ctk.CTkFrame(set_grid, fg_color="transparent")
        col3.grid(row=0, column=2, padx=5, pady=5, sticky="nsew")
        ctk.CTkLabel(col3, text="WORKER", font=("Segoe UI", 10, "bold"), text_color="#AAA").pack()
        
        r3_1 = ctk.CTkFrame(col3, fg_color="transparent"); r3_1.pack(fill="x", pady=2)
        ctk.CTkLabel(r3_1, text="Count:", font=("Segoe UI", 9), width=25, anchor="w").pack(side="left")
        self.worker_count_entry = ctk.CTkEntry(r3_1, width=30, height=24, font=("Segoe UI", 11))
        self.worker_count_entry.insert(0, "5")
        self.worker_count_entry.pack(side="right", expand=True, fill="x")

        r3_2 = ctk.CTkFrame(col3, fg_color="transparent"); r3_2.pack(fill="x", pady=2)
        ctk.CTkLabel(r3_2, text="Delay:", font=("Segoe UI", 9), width=25, anchor="w").pack(side="left")
        self.delay_entry = ctk.CTkEntry(r3_2, width=30, height=24, font=("Segoe UI", 11))
        self.delay_entry.insert(0, "5")
        self.delay_entry.pack(side="right", expand=True, fill="x")
        
        sort_switch = ctk.CTkSwitch(adv_frame, text="Auto Sort (Reject Watermark/Logo)", variable=self.sorting_enabled, font=("Segoe UI", 11), text_color="#FFF")
        sort_switch.pack(pady=(10, 5), padx=10, anchor="w")

        # === RIGHT COLUMN ===
        right_col = ctk.CTkFrame(main_box, fg_color="transparent")
        right_col.pack(side="left", fill="both", expand=True, padx=(5, 0))
        
        # Progress
        prog_frame = ctk.CTkFrame(right_col, fg_color="#1E1E1E", corner_radius=8)
        prog_frame.pack(fill="x", pady=(0, 5))
        ctk.CTkLabel(prog_frame, text="PROGRESS", font=("Segoe UI", 12, "bold"), text_color="#d4af37").place(x=10, y=5)
        
        self.status_lbl = ctk.CTkLabel(prog_frame, text="Ready", font=("Segoe UI", 11), text_color="#555")
        self.status_lbl.pack(pady=(28, 2))
        self.p_bar = ctk.CTkProgressBar(prog_frame, fg_color="#0D0D0D", progress_color="#2ecc71", height=10)
        self.p_bar.set(0)
        self.p_bar.pack(fill="x", padx=10, pady=5)
        
        stat_row = ctk.CTkFrame(prog_frame, fg_color="transparent")
        stat_row.pack(fill="x", padx=10, pady=(2, 10))
        self.val_s = ctk.StringVar(value="OK: 0"); self.val_f = ctk.StringVar(value="FAIL: 0")
        self.val_r = ctk.StringVar(value="LEFT: 0"); self.val_e = ctk.StringVar(value="ETA: --:--")
        ctk.CTkLabel(stat_row, textvariable=self.val_s, text_color="#2ecc71", font=("Segoe UI", 11, "bold")).pack(side="left", padx=5)
        ctk.CTkLabel(stat_row, textvariable=self.val_f, text_color="#e74c3c", font=("Segoe UI", 11, "bold")).pack(side="left", padx=5)
        ctk.CTkLabel(stat_row, textvariable=self.val_r, text_color="#FFF", font=("Segoe UI", 11, "bold")).pack(side="left", padx=5)
        ctk.CTkLabel(stat_row, textvariable=self.val_e, text_color="#3498db", font=("Segoe UI", 11, "bold")).pack(side="left", padx=5)
        
        # Log
        log_frame = ctk.CTkFrame(right_col, fg_color="#1E1E1E", corner_radius=8)
        log_frame.pack(fill="both", expand=True)
        ctk.CTkLabel(log_frame, text="LOG OUTPUT", font=("Segoe UI", 12, "bold"), text_color="#d4af37").place(x=10, y=2)

        ctk.CTkButton(log_frame, text="CLEAR LOG", width=70, height=20, fg_color="#C42B2B", command=lambda: self.log_box.delete("1.0", "end"), font=("Segoe UI", 11)).place(relx=1.0, y=4, anchor="ne", x=-10)
        self.log_box = ctk.CTkTextbox(log_frame, fg_color="#0D0D0D", font=("Consolas", 12), text_color="#00FF00")
        self.log_box.pack(fill="both", expand=True, padx=10, pady=(28, 10))
        
        self.log_box._textbox.tag_config("BLUE", foreground="#3498db")
        self.log_box._textbox.tag_config("GREEN", foreground="#2ecc71")
        self.log_box._textbox.tag_config("ORANGE", foreground="#e67e22")
        self.log_box._textbox.tag_config("YELLOW", foreground="#f1c40f")
        self.log_box._textbox.tag_config("RED", foreground="#ff0000")
        self.log_box._textbox.tag_config("NEON_GREEN", foreground="#00FF00")

        # --- BOTTOM BUTTONS ---
        btn_row = ctk.CTkFrame(self, fg_color="transparent")
        btn_row.pack(fill="x", padx=15, pady=10)
        self.btn_run = ctk.CTkButton(btn_row, text="START PROCESSING", fg_color="#2D8A4E", font=("Segoe UI", 15, "bold"), height=45, command=self.start_process)
        self.btn_run.pack(side="left", fill="x", expand=True, padx=(0, 5))
        self.btn_stop = ctk.CTkButton(btn_row, text="STOP", fg_color="#C42B2B", font=("Segoe UI", 15, "bold"), height=45, state="disabled", command=self.stop)
        self.btn_stop.pack(side="left", fill="x", expand=True)
        
        # === FOOTER ===
        footer_frame = ctk.CTkFrame(self, fg_color="transparent")
        footer_frame.pack(pady=(0, 5))

        ctk.CTkLabel(footer_frame, text=f"© 2026 {COMPANY_NAME} - {APP_NAME} v{CURRENT_VERSION} ", 
                     font=("Segoe UI", 10), text_color="#444").pack(side="left")

        ctk.CTkLabel(footer_frame, text="(FREE - Not For Sale)", 
                     font=("Segoe UI", 10, "bold", "italic"), text_color="#FF3333").pack(side="left")

        ctk.CTkLabel(footer_frame, text="  |  ", text_color="#444").pack(side="left")
        
        ctk.CTkButton(footer_frame, text="Show Logs (CMD)", command=self.toggle_console, 
                      width=100, height=20, fg_color="transparent", text_color="#888", 
                      border_width=1, border_color="#555", font=("Segoe UI", 9)).pack(side="left")

        self.protocol("WM_DELETE_WINDOW", self.on_closing)
    def on_engine_change(self, choice):
        try:
            # ==========================================================
            # KASUS 1: LOCAL & AUTO ROTATE (Sembunyikan Input, Tampilkan Info)
            # ==========================================================
            if choice == "Local (BLIP)" or choice.startswith("Auto Rotate"):
                
                # 1. Sembunyikan Area Input (Entry + Tombol)
                self.input_area_frame.pack_forget()
                
                # 2. Tampilkan Label Informasi
                self.api_info_label.pack(fill="x", padx=10, pady=5, before=self.api_status_text)
                
                # 3. Set teks sesuai pilihan
                if choice == "Local (BLIP)":
                    info_text = "LOCAL MODE ACTIVE.\n\nNo API Key required.\nProcessing runs 100% offline on this computer."
                    self.api_status_text.configure(text="Mode: Local (BLIP)", text_color="#2ecc71")
                else: # Auto Rotate
                    info_text = "AUTO ROTATE MODE ACTIVE.\n\nThis mode rotates between Gemini, Groq, and Mistral automatically.\n\nPlease ensure you have saved API keys for each engine individually."
                    self.api_status_text.configure(text="Mode: Auto Rotate", text_color="#2ecc71")
                
                self.api_info_label.configure(text=info_text)
                
                # Reset state
                self.keys_visible = True
                self.hidden_key_data = ""
                self.config_data["last_engine"] = choice
                save_config(self.config_data)
                return

            # ==========================================================
            # KASUS 2: API SPESIFIK (Tampilkan Input, Sembunyikan Info)
            # ==========================================================
            
            # 1. Sembunyikan Label Informasi
            self.api_info_label.pack_forget()
            
            # 2. Tampilkan Area Input
            self.input_area_frame.pack(fill="x", padx=10, pady=5, before=self.api_status_text)

            # Aktifkan tombol toggle
            self.toggle_btn.configure(state="normal")
            self.api_key_entry.configure(state="normal")

            # ... (Sisa logika load key tetap sama) ...
            new_keys = ""
            api_key = get_api_key_from_keyring("NS-MetaRefiner", choice)
            if api_key:
                new_keys = api_key.replace("|||", "\n")
            
            self.hidden_key_data = new_keys
            
            if self.keys_visible:
                self.api_key_entry.configure(state="normal")
                self.api_key_entry.delete("1.0", "end")
                self.api_key_entry.insert("1.0", new_keys)
                self.toggle_btn.configure(text="Hide")
            else:
                key_count = len([k for k in new_keys.splitlines() if k.strip()])
                self.api_key_entry.configure(state="normal")
                self.api_key_entry.delete("1.0", "end")
                
                if key_count > 0:
                    self.api_key_entry.insert("1.0", f"[ {key_count} Keys Hidden - Click 'Show' ]")
                    self.api_key_entry.configure(state="disabled")
                    self.toggle_btn.configure(text="Show")
                else:
                    self.api_key_entry.insert("1.0", "")
                    self.toggle_btn.configure(text="Hide")
                    self.keys_visible = True
            
            self.config_data["last_engine"] = choice
            save_config(self.config_data)
            self.update_api_status()
            
        except Exception as e: 
            logger.error(f"Engine change failed: {e}")

    def toggle_key_visibility(self):
        """Fungsi untuk menyembunyikan atau menampilkan API Key."""
        if self.keys_visible:
            # --- LOGIKA SEMBUNYIKAN ---
            current_text = self.api_key_entry.get("1.0", "end-1c").strip()
            
            if not current_text:
                return

            self.hidden_key_data = current_text
            key_count = len([k for k in current_text.splitlines() if k.strip()])
            
            self.api_key_entry.configure(state="normal")
            self.api_key_entry.delete("1.0", "end")
            self.api_key_entry.insert("1.0", f"[ {key_count} Keys Hidden - Click 'Show' ]")
            self.api_key_entry.configure(state="disabled")
            
            self.toggle_btn.configure(text="Show")
            self.keys_visible = False
            
            # === SIMPAN STATUS KE CONFIG ===
            self.config_data["keys_visible"] = False
            save_config(self.config_data)
            # ===============================
            
        else:
            # --- LOGIKA TAMPILKAN ---
            self.api_key_entry.configure(state="normal")
            self.api_key_entry.delete("1.0", "end")
            
            if self.hidden_key_data:
                self.api_key_entry.insert("1.0", self.hidden_key_data)
            
            self.toggle_btn.configure(text="Hide")
            self.keys_visible = True
            
            # === SIMPAN STATUS KE CONFIG ===
            self.config_data["keys_visible"] = True
            save_config(self.config_data)
            # ===============================

    def update_api_status(self):
        # 1. Ambil engine yang sedang aktif di menu UI
        selected_ui = self.engine_var.get()
        
        # === WARNA PALETTE ===
        COLOR_READY = "#00FF00"  # Hijau Neon Menyala (Untuk API Ready)
        COLOR_WAITING = "#e74c3c" # Merah (Untuk No Key)
        COLOR_LOCAL = "#2ecc71"  # Hijau Standar (Untuk Local)
        # =====================
        
        # 2. Mapping nama UI
        monitor_key = selected_ui
        
        if selected_ui == "Local (BLIP)":
            monitor_key = "Local"
        elif selected_ui == "OpenAI (Premium)":
            monitor_key = "OpenAI"
            
        # === LOGIKA KHUSUS AUTO ROTATE ===
        elif selected_ui.startswith("Auto Rotate"):
            candidates = ['Gemini', 'Mistral', 'Groq']
            summary_parts = []
            total_keys = 0
            
            for eng in candidates:
                keys = get_api_key_from_keyring("NS-MetaRefiner", eng)
                if keys:
                    k_count = len([k for k in keys.split("|||") if k.strip()])
                else:
                    k_count = 0
                
                total_keys += k_count
                short_name = eng[:3] 
                summary_parts.append(f"{short_name}:{k_count}")
            
            total_success = sum(api_monitor.status.get(e, {}).get("count", 0) for e in candidates)
            
            status_text = f"Status: [{' '.join(summary_parts)}] Auto Rotate ({total_success} done)"
            
            # LOGIKA WARN AUTO ROTATE:
            # Jika Total Keys > 0 -> Hijau Menyala. Jika 0 -> Merah.
            if total_keys > 0:
                self.api_status_text.configure(text=status_text, text_color=COLOR_READY)
            else:
                self.api_status_text.configure(text=status_text, text_color=COLOR_WAITING)
            return
        # ===================================

        # 3. LOGIKA UNTUK ENGINE TUNGGAL (Gemini, Groq, Local, dll)
        
        # Khusus Local -> Selalu Hijau (tidak perlu cek key)
        if monitor_key == "Local":
            data = api_monitor.status.get("Local", {"count": 0})
            status_text = f"Status: [READY] Local ({data['count']} processed)"
            self.api_status_text.configure(text=status_text, text_color=COLOR_LOCAL)
            return

        # Untuk API Lainnya -> Cek Jumlah Key
        key_count = 0
        try:
            raw_keys = get_api_key_from_keyring("NS-MetaRefiner", monitor_key)
            if raw_keys:
                valid_keys = [k for k in raw_keys.split("|||") if k.strip()]
                key_count = len(valid_keys)
        except:
            key_count = 0

        data = api_monitor.status.get(monitor_key, {"healthy": True, "count": 0})
        success_count = data["count"]
        
        # Penentuan Teks & Warna
        if key_count > 0:
            status_text = f"Status: [{key_count} Keys] {monitor_key} ({success_count} success)"
            self.api_status_text.configure(text=status_text, text_color=COLOR_READY) # Hijau Menyala
        else:
            status_text = f"Status: [No Key] {monitor_key} (Input Required)"
            self.api_status_text.configure(text=status_text, text_color=COLOR_WAITING) # Merah

    def save_current_config(self):
        try:
            engine = self.engine_var.get()
            
            # === LOGIKA PINTAR ===
            # Jika sedang Hidden, pakai data dari memori. Jika Visible, baca dari kotak.
            if not self.keys_visible:
                raw_input = self.hidden_key_data
            else:
                raw_input = self.api_key_entry.get("1.0", "end-1c")
            # =====================
            
            valid_keys = sanitize_api_key(raw_input)

            if not valid_keys:
                messagebox.showwarning("Warning", "No valid API keys detected.")
                return

            combined_keys = "|||".join(valid_keys)
            save_api_key_to_keyring("NS-MetaRefiner", engine, combined_keys)
            
            self.config_data[engine] = "KEYRING_STORED"
            save_config(self.config_data)
            
            messagebox.showinfo("Success", f"Saved {len(valid_keys)} API key(s) for {engine}!")
            logger.info(f"Saved {len(valid_keys)} keys for {engine}")
            self.update_api_status()
            
        except Exception as e:
            logger.error(f"Save failed: {e}")
            messagebox.showerror("Error", f"Failed to save API key: {e}")

    def check_api_status(self):
        engine = self.engine_var.get()
        
        if engine == "Local (BLIP)":
            self.api_status_text.configure(text="API: LOCAL MODE", text_color="#2ecc71")
            return
        
        self.api_status_text.configure(text="Verifying...", text_color="#FFF")
        self.update()
        
        # === LOGIKA PINTAR ===
        if not self.keys_visible:
            # Jika sedang hidden, ambil dari memori
            raw_key_ui = self.hidden_key_data
            source = "Hidden Memory"
        else:
            # Jika visible, ambil dari UI
            raw_key_ui = self.api_key_entry.get("1.0", "end-1c")
            source = "Input Box"
        # =====================

        clean_keys_list = sanitize_api_key(raw_key_ui)
        
        keys_to_check = []
        if clean_keys_list:
            keys_to_check = clean_keys_list
        else:
            stored_keys_str = get_api_key_from_keyring("NS-MetaRefiner", engine)
            if stored_keys_str:
                keys_to_check = stored_keys_str.split("|||")
                source = "Keyring Storage"

        if not keys_to_check:
            self.api_status_text.configure(text="API: NO KEY FOUND", text_color="#e74c3c")
            self.write_log("Tidak ada API Key.", "WARN")
            return
            
        test_key = keys_to_check[0]
        self.write_log(f"Verifying {len(keys_to_check)} key(s) from {source}...", "INFO")
        is_valid = verify_api_online(engine, test_key)
        
        if is_valid:
             self.api_status_text.configure(text=f"API: {engine} VALID ({len(keys_to_check)} keys)", text_color="#2ecc71")
             self.write_log(f"Connection successful for {engine}.", "DONE")
        else:
             self.api_status_text.configure(text="API: INVALID/ERROR", text_color="#e74c3c")
             self.write_log(f"Failed to verify {engine}. Check key or network.", "ERROR")

    def write_log(self, msg, level="INFO"):
        try:
            # 1. Map Level ke Simbol
            icon_map = {
                "STEP": ">>>", 
                "DONE": "✓",
                "ERROR": "⚠",
                "INFO": "[*]",
                "WARN": "[?]",
                "START": " →",
                "HEADER": "-->",
                "STATUS": "[*]",
                "ENGINE_SUCCESS": "✓" # Ikon khusus untuk sukses engine
            }
            icon = icon_map.get(level, "[.]")
            
            # 2. Map Level ke Tag Warna
            color_map = {
                "START": "BLUE",
                "STEP": "NEON_GREEN",
                "DONE": "GREEN",
                "ERROR": "RED",
                "WARN": "ORANGE",
                "HEADER": "YELLOW",
                "STATUS": "YELLOW",
                "SUCCESS": "NEON_GREEN" 
            }
            
            timestamp = time.strftime("%H:%M:%S")

            # === LOGIKA KHUSUS: DUA WARNA UNTUK ENGINE SUCCESS ===
            if level == "ENGINE_SUCCESS":
                # Format msg harus: "NamaEngine::NAMAFILE"
                # Kita pecah string
                parts = msg.split("::", 1)
                engine_name = parts[0] if len(parts) > 0 else "Unknown"
                file_name = parts[1] if len(parts) > 1 else ""
                
                # 1. Tampilkan Timestamp & Ikon (Hijau Biasa)
                self.log_box._textbox.insert("end", f"[{timestamp}] {icon} ", "GREEN")
                
                # 2. Tampilkan Nama Engine (Hijau Neon Terang)
                self.log_box._textbox.insert("end", f"{engine_name}", "NEON_GREEN")
                
                # 3. Tampilkan Panah & Nama File (Hijau Biasa)
                self.log_box._textbox.insert("end", f" → {file_name}\n", "GREEN")
            
            else:
                # Logika Standar (1 Warna)
                tag = color_map.get(level, "")
                log_entry = f"[{timestamp}] {icon} {msg}\n"
                self.log_box._textbox.insert("end", log_entry, tag)
            
            self.log_box.see("end")
            self.update()
            
        except Exception as e:
            print(f"Log error: {e}")

    def add_input(self):
        try:
            fs = []
            if self.in_mode.get() == "file": fs = filedialog.askopenfilenames(filetypes=[("Media", "*.jpg *.jpeg *.png *.mp4 *.mov *.mkv *.avi *.mpeg *.svg *.eps *.psd *.pdf *.ai")])
            else:
                d = filedialog.askdirectory()
                if d and os.path.isdir(d): fs = [os.path.join(d, x) for x in os.listdir(d) if x.lower().endswith(('.jpg', '.jpeg', '.png', '.mp4', '.mov', '.mkv', '.avi', '.mpeg', '.svg', '.eps', '.psd', '.pdf', '.ai')) and os.path.isfile(os.path.join(d, x))]
            if fs:
                valid = [f for f in fs if os.path.isfile(f) and os.access(f, os.R_OK)]
                
                # --- PERBAIKAN: Hapus duplikat dari daftar baru ---
                # Ubah ke set untuk menghapus duplikat, lalu kembali ke list
                valid = list(set(valid))
                
                # Gabungkan dengan daftar lama
                self.selected_paths.extend(valid)
                
                # --- PERBAIKAN: Hapus duplikat dari total daftar ---
                # Ini memastikan tidak ada file yang diproses 2x
                self.selected_paths = list(dict.fromkeys(self.selected_paths))
                
                self.file_list_box.delete("1.0", "end")
                for i, p in enumerate(self.selected_paths): self.file_list_box.insert("end", f"{i+1}. {os.path.basename(p)}\n")
                self.val_r.set(f"LEFT: {len(self.selected_paths)}")
                self.write_log(f"Added {len(valid)} files", "INFO")
                # === TAMBAHKAN LOGIKA UPDATE LABEL LOKASI ===
                if self.selected_paths:
                    # Ambil folder parent dari file pertama
                    first_file_path = self.selected_paths[0]
                    parent_dir = os.path.dirname(first_file_path)
                    
                    # Jika panjang, potong (misal: D:/Users/.../Folder)
                    display_text = parent_dir
                    if len(parent_dir) > 45:
                        display_text = "..." + parent_dir[-42:]
                    
                    self.in_label.configure(text=display_text, text_color="#2ecc71") # Hijau
                # ============================================
        except Exception as e: logger.error(f"Add input failed: {e}"); messagebox.showerror("Error", f"Failed: {e}")
    def clear_input(self): self.selected_paths = []; self.file_list_box.delete("1.0", "end"); self.val_r.set("LEFT: 0")

    def select_output(self):
        try:
            out = filedialog.askdirectory()
            if out and os.path.isdir(out) and os.access(out, os.W_OK):
                self.out_path = out
                self.out_label.configure(text=out[-40:] if len(out) > 40 else out, text_color="#2ecc71")
                self.write_log("Output set", "INFO")
            elif out and not os.access(out, os.W_OK):
                 messagebox.showerror("Permission Error", "Cannot write to the selected output directory. Please choose a different folder.")
        except Exception as e: logger.error(f"Output selection failed: {e}"); messagebox.showerror("Error", f"Failed: {e}")

    def stop(self):
        # 1. Set flag utama UI
        self.stop_requested = True
        
        # 2. PENTING: Kirim sinyal ke config_data agar Worker tahu
        self.config_data['stop_requested'] = True
        
        # 3. Catat di log
        self.write_log("STOP REQUESTED! Finishing current file...", "WARN")
        
        # 4. Nonaktifkan tombol stop agar tidak dikali berkali-kali
        self.btn_stop.configure(state="disabled")

    # --- TAMBAHKAN FUNGSI INI ---
    def on_closing(self):
        """Dipanggil saat user klik tombol X di jendela."""
        if self.btn_run.cget("state") == "disabled":
            if messagebox.askokcancel("Keluar", "Proses masih berjalan. Yakin ingin membatalkan dan keluar?"):
                self.stop_requested = True
                
                # === TAMBAHKAN INI JUGA: Stop Worker saat window ditutup ===
                self.config_data['stop_requested'] = True

                self.destroy()
        else:
            self.destroy()

    # === TAMBAHKAN FUNGSI BARU DI SINI (SEJAJAR DENGAN on_closing) ===
    def toggle_console(self):
        """Menampilkan atau menyembunyikan jendela CMD."""
        try:
            console_window = ctypes.windll.kernel32.GetConsoleWindow()
            
            if console_window:
                if not hasattr(self, 'console_visible'):
                    self.console_visible = True 
                
                if self.console_visible:
                    # === PERINTAH SEMBUNYIKAN ===
                    # SW_HIDE = 0 (Benar-benar hilang)
                    ctypes.windll.user32.ShowWindow(console_window, 0)
                    self.console_visible = False
                    self.write_log("Console hidden.", "INFO")
                else:
                    # === PERINTAH MUNCULKAN + DEPAN ===
                    # SW_SHOW = 5 (Munculkan)
                    ctypes.windll.user32.ShowWindow(console_window, 5)
                    
                    # SetForegroundWindow: Paksa muncul paling depan
                    ctypes.windll.user32.SetForegroundWindow(console_window)
                    
                    self.console_visible = True
                    self.write_log("Console shown.", "INFO")
            else:
                self.write_log("No console attached.", "WARN")
                
        except Exception as e:
            logger.error(f"Toggle console failed: {e}")
    # ==================================================================

    def start_process(self):
        try:
            # === 1. RESET STOP FLAG ===
            self.stop_requested = False
            self.config_data['stop_requested'] = False

            # === 2. AUTO-SAVE CONFIG (PENTING!) ===
            # Simpan semua pengaturan numerik ke config
            try:
                self.config_data['min_title_len'] = int(self.min_title_entry.get())
                self.config_data['max_title_len'] = int(self.max_title_entry.get())
                self.config_data['min_kw_len'] = int(self.min_kw_entry.get())
                self.config_data['max_kw_len'] = int(self.max_kw_entry.get())
                self.config_data['worker_count'] = int(self.worker_count_entry.get())
                self.config_data['delay'] = int(self.delay_entry.get())
            except ValueError:
                # Jika user mengisi huruf, biarkan default
                logger.warning("Input setting tidak valid, menggunakan default.")
            
            # Simpan pilihan Engine & Sortir
            self.config_data['last_engine'] = self.engine_var.get()
            self.config_data['sorting_enabled'] = self.sorting_enabled.get()
            
            # Simpan lokasi Path
            if self.out_path:
                self.config_data['last_output_dir'] = self.out_path
            
            if self.selected_paths:
                # Simpan folder parent dari file pertama yg dipilih
                self.config_data['last_input_dir'] = os.path.dirname(self.selected_paths[0])

            # Tulis ke file JSON
            save_config(self.config_data)
            logger.info("Configuration auto-saved successfully.")
            # =======================================

            # === 3. VALIDASI INPUT ===
            # (Kode pembersihan list file yang sudah ada sebelumnya)
            unique_files = list(set(self.selected_paths))
            existing_files = [f for f in unique_files if os.path.exists(f)]
            self.selected_paths = existing_files
            
            self.file_list_box.delete("1.0", "end")
            for i, p in enumerate(self.selected_paths): self.file_list_box.insert("end", f"{i+1}. {os.path.basename(p)}\n")
            self.val_r.set(f"LEFT: {len(self.selected_paths)}")

            if not self.selected_paths: messagebox.showwarning("Warning", "No valid files to process."); return
            if not self.out_path: messagebox.showwarning("Warning", "Select output folder"); return
            
            # Jalankan proses di thread terpisah
            threading.Thread(target=self.core_logic, daemon=True).start()
            
        except Exception as e: 
            logger.error(f"Start failed: {e}")

    def core_logic(self):
        start_time = time.time()
        self.btn_run.configure(state="disabled")
        self.btn_stop.configure(state="normal")
        
        # === PEMBUKA RAHANG BAJA (CADANGAN) ===
        self.stop_requested = False
        self.config_data['stop_requested'] = False
        # =====================================
        
        # Filter file valid
        valid_files = []
        seen = set()
        for p in self.selected_paths:
            if p not in seen and os.path.exists(p):
                valid_files.append(p)
                seen.add(p)
        
        self.selected_paths = valid_files
        total = len(self.selected_paths)

        # === TAMBAHKAN RINGKASAN AWAL ===
        engine_name = self.engine_var.get()
        self.write_log(f"Engine Selected: {engine_name}", "INFO")
        self.write_log(f"Files to Process: {total}", "INFO")
        # =================================

        # Update UI Awal
        self.file_list_box.delete("1.0", "end")
        for i, p in enumerate(self.selected_paths): self.file_list_box.insert("end", f"{i+1}. {os.path.basename(p)}\n")
        self.val_r.set(f"LEFT: {total}")
        
        if total == 0:
            self.write_log("No valid files found.", "WARN")
            self.btn_run.configure(state="normal")
            self.btn_stop.configure(state="disabled")
            return

        success_c = 0
        failed_c = 0
        rejected_c = 0
        
        # Baca pengaturan
        try:
            min_title_len = int(self.min_title_entry.get())
            max_title_len = int(self.max_title_entry.get())
            min_kw_len = int(self.min_kw_entry.get())
            max_kw_len = int(self.max_kw_entry.get())
            
            self.config_data['min_title_len'] = min_title_len
            self.config_data['max_title_len'] = max_title_len
            self.config_data['min_kw_len'] = min_kw_len
            self.config_data['max_kw_len'] = max_kw_len
            
        except ValueError:
            self.config_data['min_title_len'] = 35
            self.config_data['max_title_len'] = 75
            self.config_data['min_kw_len'] = 35
            self.config_data['max_kw_len'] = 49

        try:
            engine = self.engine_var.get()
            if engine == "Local (BLIP)": self.write_log("Loading AI Model...", "INFO"); load_local_ai_now()
            
            try:
                num_workers = int(self.worker_count_entry.get())
                delay_time = int(self.delay_entry.get())
            except ValueError:
                num_workers = 4
                delay_time = 0
            
            self.config_data['delay'] = delay_time 
            self.config_data['sorting_enabled'] = self.sorting_enabled.get()
            
            task_queue = Queue()
            result_queue = Queue()
            workers = []
            
            # Inisialisasi Worker
            for i in range(num_workers): 
                w = ProcessingWorker(i, task_queue, result_queue, engine, self.config_data)
                w.start()
                workers.append(w)
            
            # === PERBAIKAN FINAL: PERSIAPAN FOLDER & CSV PISAH ===
            exts = {os.path.splitext(f)[1].lower() for f in self.selected_paths}
            
            exporters = {} # Penampung CSV per tipe
            f_map = {}     # Penampung lokasi folder per tipe
            
            # 1. Folder Images
            if any(e in ('.jpg', '.png', '.jpeg') for e in exts):
                img_dir = os.path.join(self.out_path, "Images")
                os.makedirs(img_dir, exist_ok=True)
                f_map['image'] = img_dir
                
                csv_img_dir = os.path.join(img_dir, "Metadata_CSV")
                os.makedirs(csv_img_dir, exist_ok=True)
                exporters['image'] = AgencyExporter(csv_img_dir)
            
            # 2. Folder Videos
            if any(e in ('.mp4', '.mov', '.mkv', '.avi', '.mpeg') for e in exts):
                vid_dir = os.path.join(self.out_path, "Videos")
                os.makedirs(vid_dir, exist_ok=True)
                f_map['video'] = vid_dir
                
                csv_vid_dir = os.path.join(vid_dir, "Metadata_CSV")
                os.makedirs(csv_vid_dir, exist_ok=True)
                exporters['video'] = AgencyExporter(csv_vid_dir)

            # 3. Folder Vectors
            if any(e in ('.svg', '.eps', '.psd', '.pdf', '.ai') for e in exts):
                vec_dir = os.path.join(self.out_path, "Vectors")
                os.makedirs(vec_dir, exist_ok=True)
                f_map['vector'] = vec_dir
                
                csv_vec_dir = os.path.join(vec_dir, "Metadata_CSV")
                os.makedirs(csv_vec_dir, exist_ok=True)
                exporters['vector'] = AgencyExporter(csv_vec_dir)
            # =====================================================
            
            self.write_log(f"============== Process Queue =============", "HEADER")
            
            processed = 0
            i = 0
            batch_num = 0
            
            while i < total:
                if self.stop_requested: break
                
                batch_num += 1
                batch_files = self.selected_paths[i : i + num_workers]
                batch_size = len(batch_files)
                
                self.write_log(f"Starting Batch {batch_num} ({batch_size} files)", "STEP")
                
                for file_path in batch_files:
                    ext = os.path.splitext(file_path)[1].lower()
                    ftype = "image" if ext in ('.jpg', '.png', '.jpeg') else "video" if ext in ('.mp4', '.mov', '.mkv', '.avi', '.mpeg') else "vector"
                    
                    # Ambil dest_dir dari f_map, jika tidak ada pakai out_path
                    dest_dir = f_map.get(ftype, self.out_path)
                    
                    self.write_log(f"Processing {os.path.basename(file_path)}...", "START")
                    task_queue.put((file_path, dest_dir, f_map, self.op_mode.get()))
                self.write_log(f"Please wait Processing...", "STEP")
                
                batch_processed = 0
                while batch_processed < batch_size:
                    if self.stop_requested: break 
                    try:
                        result = result_queue.get(timeout=2.0)
                        batch_processed += 1
                        processed += 1
                        
                        if result['status'] == 'success':
                            if result.get('api_used') in ['REJECTED', 'OPENCV_REJECT']:
                                rejected_c += 1
                                orig_name = os.path.basename(result['file'])
                                reason = result.get('rejection_detail', 'Unknown reason')
                                self.write_log(f"{orig_name} → REJECTED ({reason})", "WARN")
                            else:
                                success_c += 1
                                
                                # === TULIS CSV KE FOLDER Masing-masing ===
                                ftype = result['file_type']
                                if ftype in exporters:
                                    exporters[ftype].write_row({
                                        'filename': result['filename'], 
                                        'title': result['title'], 
                                        'keywords': result['keywords'], 
                                        'file_type': ftype
                                    })
                                # =========================================
                                
                                engine_used = result.get('api_used', 'Unknown')
                                new_name = result['filename']
                                note = ""
                                if result.get('embedded') == 'no' and result['file_type'] == 'image': note = " (Metadata skipped)"
                                self.write_log(f"{engine_used}::{new_name}{note}", "ENGINE_SUCCESS")
                            
                        else:
                            failed_c += 1
                            orig_name = os.path.basename(result['file'])
                            error_msg = result.get('error', 'Unknown error')
                            self.write_log(f"{orig_name} → Error: {error_msg}", "ERROR")
                        
                        # Update UI (Aman)
                        avg_time = (time.time() - start_time) / processed if processed > 0 else 0
                        eta_val = int(avg_time * (total - processed))
                        
                        self.after(0, lambda p=processed, t=total: self.p_bar.set(p / t))
                        self.after(0, lambda s=success_c: self.val_s.set(f"OK: {s}"))
                        self.after(0, lambda f=failed_c: self.val_f.set(f"FAIL: {f}"))
                        self.after(0, lambda r=(total-processed): self.val_r.set(f"LEFT: {r}"))
                        self.after(0, lambda e=eta_val: self.val_e.set(f"ETA: {str(timedelta(seconds=e))[2:]}"))
                        self.after(0, self.update_api_status)

                    except Empty:
                        pass
                        
                    except Exception as e:
                        logger.warning(f"Error in batch loop: {e}")
                
                if not self.stop_requested and (i + num_workers) < total:
                    if delay_time > 0:
                        self.write_log(f"Batch {batch_num} complete. Cooling down for {delay_time} seconds...", "STATUS")
                        time.sleep(delay_time)
                gc.collect()
                i += num_workers
            
            # --- SELESAI ---
            # Tutup semua CSV
            for exp in exporters.values():
                exp.close_all()
            
            for _ in range(num_workers): task_queue.put(None)
            for w in workers: w.join(timeout=5.0)
            
            logger.info("All workers stopped successfully.")
            
            elapsed = round(time.time() - start_time, 2)
            
            self.write_log("============= Summary Process =============", "HEADER")
            self.write_log(f"{'Total Assets'.ljust(12)}   : {total}", "STEP")
            self.write_log(f" {'Accepted'.ljust(12)}   : {success_c}", "DONE")
            self.write_log(f" {'Rejected'.ljust(12)}   : {rejected_c}", "ERROR")
            self.write_log(f"{'Errors'.ljust(12)}   : {failed_c}", "WARN")
            self.write_log(f" {'Time Taken'.ljust(12)}   : {elapsed}s", "START")
            
            stats = api_monitor.get_engine_stats()
            for eng_name, data in stats.items():
                success_count = data.get('success', 0)
                if success_count > 0:
                    self.write_log(f"{eng_name.ljust(15)}: {success_count} success", "INFO")

            try: winsound.MessageBeep(winsound.MB_ICONASTERISK)
            except: pass

            self.after(500, lambda: self.show_report(
                total, success_c, rejected_c, failed_c, elapsed, self.engine_var.get(), stats
            ))

        except Exception as e:
            logger.error(f"Core logic failed: {e}")
            self.write_log(f"FATAL: {str(e)[:80]}", "ERROR")
        finally:
            self.btn_run.configure(state="normal")
            self.btn_stop.configure(state="disabled")

    def show_report(self, total, accepted, rejected, failed, elapsed_time, selected_engine, stats):
        try:
            pop = ctk.CTkToplevel(self)
            pop.title("Processing Report")
            # Ukuran sedikit dikembalikan ke 550 karena font lebih kecil
            pop.geometry("520x650") 
            pop.attributes("-topmost", True)
            pop.configure(fg_color="#0D0D0D")
            ctk.CTkLabel(pop, text="PROCESSING COMPLETE", font=("Segoe UI", 20, "bold"), text_color="#d4af37").pack(pady=(20, 10))
            
            # === STATISTIK UTAMA (Font Diperkecil Jadi 14) ===
            stats_frame = ctk.CTkFrame(pop, fg_color="transparent")
            stats_frame.pack(pady=(5, 0)) # Jarak atas dikurangi

            ctk.CTkLabel(stats_frame, text=f"Total Assets: {total}", font=("Segoe UI", 14), text_color="#FFFFFF").pack(anchor="w", padx=20, pady=1)
            ctk.CTkLabel(stats_frame, text=f"✓ Accepted: {accepted}", font=("Segoe UI", 14, "bold"), text_color="#2ecc71").pack(anchor="w", padx=20, pady=1)
            ctk.CTkLabel(stats_frame, text=f"✗ Rejected: {rejected}", font=("Segoe UI", 14, "bold"), text_color="#e74c3c").pack(anchor="w", padx=20, pady=1)
            ctk.CTkLabel(stats_frame, text=f"⚠ Errors: {failed}", font=("Segoe UI", 14, "bold"), text_color="#e67e22").pack(anchor="w", padx=20, pady=1)
            ctk.CTkLabel(stats_frame, text=f"Time Taken: {elapsed_time}s", font=("Segoe UI", 13), text_color="#888888").pack(anchor="w", padx=20, pady=(2, 5))

            # === GARIS PEMISAH ===
            ctk.CTkFrame(pop, height=2, fg_color="#333333").pack(fill="x", padx=20, pady=5)

            # === API USAGE (DINAMIS) ===
            ctk.CTkLabel(pop, text="API USAGE", font=("Segoe UI", 12, "bold"), text_color="#AAAAAA").pack(anchor="w", padx=20, pady=(10, 2))
            
            # Kita akan gabungkan semua jadi satu teks agar jaraknya rapat persis seperti Features
            usage_lines = []
            for engine_name, data in stats.items():
                count = data.get('success', 0)
                if count > 0:
                    usage_lines.append(f" → {engine_name}: {count} success")
            
            if usage_lines:
                # Gabungkan dengan \n (enter)
                final_usage_text = "\n".join(usage_lines)
                ctk.CTkLabel(pop, text=final_usage_text, font=("Consolas", 12), 
                             text_color="#3498db", justify="left").pack(anchor="w", padx=25, pady=(0, 5))
            else:
                ctk.CTkLabel(pop, text=" → No external API usage recorded", 
                             font=("Consolas", 12), text_color="#555").pack(anchor="w", padx=25, pady=(0, 5))

            # === GARIS PEMISAH ===
            ctk.CTkFrame(pop, height=2, fg_color="#333333").pack(fill="x", padx=20, pady=5)

            # === PROCESSING FEATURES ===
            features_text = """PROCESSING FEATURES:
✓ Hybrid BLIP+AI architecture
✓ Auto Sort (Reject Logo/Watermark)
✓ SEO Optimized Titles & Keywords
✓ Metadata Embedded
✓ Professional stock-ready"""
            
            ctk.CTkLabel(pop, text=features_text, font=("Consolas", 11), justify="left", text_color="#AAAAAA").pack(anchor="w", padx=20)

            # === TAMBAHAN TEKS MOTIVASI DONASI ===
            # Baris 1: Normal (Consolas 11, Abu-abu)
            ctk.CTkLabel(pop, text="If you find this app helpful, please consider giving the developer \na small token of appreciation for improvements and feature updates. Thank you.", 
                         font=("Consolas", 11), text_color="#AAAAAA", justify="center").pack(pady=(15, 0))
            
            # Baris 2: Besar, Tebal, Merah Menyala
            ctk.CTkLabel(pop, text="Your Charity Will Cure Your Illness and Increase Your Income.", 
                         font=("Segoe UI", 13, "bold"), text_color="#FF3333", justify="center").pack(pady=(5, 0))
            
            # Baris 3: Miring (Consolas 11 Italic, Abu-abu)
            ctk.CTkLabel(pop, text="Sedekahmu Menyembuhkan Penyakitmu Dan Melancarkan Rizkimu", 
                         font=("Consolas", 11, "italic"), text_color="#AAAAAA", justify="center").pack(pady=(0, 10))
            # ======================================

            # === TOMBOL BAWAH ===
            button_frame = ctk.CTkFrame(pop, fg_color="transparent")
            button_frame.pack(fill="x", padx=20, pady=15)
            
            ctk.CTkButton(button_frame, text="SUPPORT WITH A DONATION", 
                          command=lambda: webbrowser.open("https://sociabuzz.com/ns_metarefiner/donate"), 
                          font=("Segoe UI", 12, "bold"), fg_color="#FF6B6B", hover_color="#FF5252", height=40).pack(side="left", fill="x", expand=True, padx=(0, 10))
            
            ctk.CTkButton(button_frame, text="CLOSE", font=("Segoe UI", 12, "bold"), 
                          command=pop.destroy, width=100, fg_color="#555555", hover_color="#666666").pack(side="left")

        except Exception as e: 
            logger.error(f"Report failed: {e}")

    # === FUNGSI CEK UPDATE ===

    def check_for_updates(self):
        """Cek update ke GitHub Releases untuk Repo Publik."""
        def run_check():
            try:
                api_url = f"https://api.github.com/repos/{GITHUB_USER}/{GITHUB_REPO}/releases/latest"
                
                headers = {
                    "Accept": "application/vnd.github.v3+json",
                    "User-Agent": f"NS-MetaRefiner/{CURRENT_VERSION}"
                }
                
                response = requests.get(api_url, headers=headers, timeout=10)
                
                if response.status_code == 200:
                    data = response.json()
                    remote_version = data.get("tag_name", "0.0.0")
                    
                    remote_clean = remote_version.lstrip('v')
                    local_clean = CURRENT_VERSION.lstrip('v')

                    if remote_clean != local_clean:
                        assets = data.get("assets", [])
                        download_url = None
                        for asset in assets:
                            if asset["name"].endswith(".exe"):
                                download_url = asset["browser_download_url"]
                                break
                        if not download_url:
                            download_url = data.get("html_url")

                        # Tampilkan popup (GUI)
                        self.after(0, lambda: self.show_update_popup(remote_clean, download_url))
                        
            except Exception as e:
                logger.error(f"Update check failed: {e}")
        
        threading.Thread(target=run_check, daemon=True).start()
                        

    # === POPUP CEK UPDATE===

    def show_update_popup(self, version, url):
        """Menampilkan popup jika ada versi baru."""
        msg = (
            f"Versi terbaru tersedia: v{version}\n\n"
            f"Versi Anda: v{CURRENT_VERSION}\n\n"
            f"Download sekarang?"
        )
        # Menggunakan messagebox dari tkinter
        if messagebox.askyesno("Update Tersedia", msg):
            webbrowser.open(url)

if __name__ == "__main__":
    try:
        app = NSMetaRefinerApp() # Nama kelas baru
        app.mainloop()
    except Exception as e:
        logger.error(f"App failed: {e}")
        messagebox.showerror("Fatal Error", f"An unexpected error occurred:\n\n{e}")