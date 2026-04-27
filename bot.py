import os
import re
import io
import time
import asyncio
import random
import string
import requests
import discord
from discord import app_commands
from pycognito import Cognito
from urllib.parse import urlparse
import json as _json
import base64 as _base64
from html.parser import HTMLParser
from Crypto.PublicKey import RSA
from Crypto.Cipher import PKCS1_v1_5
from flask import Flask
from threading import Thread
import ssl
from requests.adapters import HTTPAdapter
from urllib3.poolmanager import PoolManager
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
import atexit

# Custom adapter to ignore SSL verification
class SSLAdapter(HTTPAdapter):
    def init_poolmanager(self, *args, **kwargs):
        kwargs['ssl_version'] = ssl.PROTOCOL_TLSv1_2
        kwargs['cert_reqs'] = ssl.CERT_NONE
        kwargs['assert_hostname'] = False
        return super().init_poolmanager(*args, **kwargs)

# ─── Bot Owner Configuration ───────────────────────────────────────────────────
BOT_OWNER_ID = 1348735671044673636

PASSWORD = "Test1234Abc!"
COGNITO_CLIENT_ID = "1kvg8re5bgu9ljqnnkjosu477k"
USER_POOL_ID = "eu-west-1_7hEawdalF"
GUERRILLA_API = "https://api.guerrillamail.com/ajax.php"
OREATE_BASE = "https://www.oreateai.com"

VALID_IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp", ".tiff"}
VIDEO_SIZES = ["1280x720", "720x1280"]

BRAND_COLOR = 0x5865F2
SUCCESS_COLOR = 0x57F287
ERROR_COLOR = 0xED4245
PROGRESS_COLOR = 0xFEE75C
INFO_COLOR = 0x5865F2
BROKEN_COLOR = 0x800020
BUGGY_COLOR = 0x9932CC

intents = discord.Intents.default()
intents.message_content = True
client = discord.Client(intents=intents)
tree = app_commands.CommandTree(client)

download_session = requests.Session()
download_session.mount('https://', SSLAdapter())
download_session.verify = False

# ─── Persistent Storage ────────────────────────────────────────────────────────
DATA_DIR = "/tmp/bot_data"
BANS_FILE = os.path.join(DATA_DIR, "bans.json")
STATUS_FILE = os.path.join(DATA_DIR, "status.json")

os.makedirs(DATA_DIR, exist_ok=True)

def save_bans(bans_dict):
    try:
        serializable_bans = {}
        for user_id, (expiry, reason, banned_by) in bans_dict.items():
            if expiry:
                serializable_bans[str(user_id)] = (expiry.isoformat(), reason, banned_by)
            else:
                serializable_bans[str(user_id)] = (None, reason, banned_by)
        with open(BANS_FILE, 'w') as f:
            _json.dump(serializable_bans, f, indent=2)
        return True
    except Exception as e:
        print(f"Error saving bans: {e}")
        return False

def load_bans():
    try:
        if os.path.exists(BANS_FILE):
            with open(BANS_FILE, 'r') as f:
                serializable_bans = _json.load(f)
            bans = {}
            for user_id_str, (expiry_str, reason, banned_by) in serializable_bans.items():
                user_id = int(user_id_str)
                if expiry_str:
                    expiry = datetime.fromisoformat(expiry_str)
                    bans[user_id] = (expiry, reason, banned_by)
                else:
                    bans[user_id] = (None, reason, banned_by)
            return bans
    except Exception as e:
        print(f"Error loading bans: {e}")
    return {}

def save_status(status_data):
    try:
        with open(STATUS_FILE, 'w') as f:
            _json.dump(status_data, f, indent=2)
        return True
    except Exception as e:
        print(f"Error saving status: {e}")
        return False

def load_status():
    try:
        if os.path.exists(STATUS_FILE):
            with open(STATUS_FILE, 'r') as f:
                return _json.load(f)
    except Exception as e:
        print(f"Error loading status: {e}")
    return {"status": "normal", "description": ""}

# ─── Bot Status System ─────────────────────────────────────────────────────────
class BotStatus:
    NORMAL = "normal"
    BUGGY = "buggy"
    BROKEN = "broken"
    
    def __init__(self):
        self.load()
    
    def load(self):
        data = load_status()
        self.status = data.get("status", self.NORMAL)
        self.description = data.get("description", "")
    
    def save(self):
        save_status({"status": self.status, "description": self.description})
    
    def set_status(self, status: str, description: str = ""):
        self.status = status
        self.description = description
        self.save()
    
    def get_status(self):
        return self.status, self.description

bot_status = BotStatus()

# ─── Ban System ────────────────────────────────────────────────────────────────
DURATIONS = {
    "1m": timedelta(minutes=1), "5m": timedelta(minutes=5), "10m": timedelta(minutes=10),
    "20m": timedelta(minutes=20), "30m": timedelta(minutes=30),
    "1h": timedelta(hours=1), "2h": timedelta(hours=2), "3h": timedelta(hours=3),
    "6h": timedelta(hours=6), "12h": timedelta(hours=12),
    "1d": timedelta(days=1), "2d": timedelta(days=2), "3d": timedelta(days=3),
    "4d": timedelta(days=4), "5d": timedelta(days=5), "6d": timedelta(days=6),
    "1w": timedelta(weeks=1), "2w": timedelta(weeks=2), "3w": timedelta(weeks=3),
    "1mo": timedelta(days=30), "2mo": timedelta(days=60), "3mo": timedelta(days=90),
    "6mo": timedelta(days=180), "perm": None
}

DURATION_NAMES = {
    "1m": "1 minute", "5m": "5 minutes", "10m": "10 minutes", "20m": "20 minutes",
    "30m": "30 minutes", "1h": "1 hour", "2h": "2 hours", "3h": "3 hours",
    "6h": "6 hours", "12h": "12 hours", "1d": "1 day", "2d": "2 days", "3d": "3 days",
    "4d": "4 days", "5d": "5 days", "6d": "6 days", "1w": "1 week", "2w": "2 weeks",
    "3w": "3 weeks", "1mo": "1 month", "2mo": "2 months", "3mo": "3 months",
    "6mo": "6 months", "perm": "Permanent"
}

class BanManager:
    def __init__(self):
        self.load()
        atexit.register(self.save)
    
    def load(self):
        self.bans = load_bans()
        self.clean_expired()
        self.save()
    
    def save(self):
        save_bans(self.bans)
    
    def ban(self, user_id: int, duration_key: str, reason: str, banned_by: str) -> Tuple[bool, str]:
        if duration_key not in DURATIONS:
            return False, "Invalid duration"
        expiry = None if duration_key == "perm" else datetime.utcnow() + DURATIONS[duration_key]
        self.bans[user_id] = (expiry, reason, banned_by)
        self.save()
        return True, f"Banned <@{user_id}> for {DURATION_NAMES[duration_key]}" + (f"\nReason: {reason}" if reason else "")
    
    def unban(self, user_id: int) -> bool:
        if user_id in self.bans:
            del self.bans[user_id]
            self.save()
            return True
        return False
    
    def is_banned(self, user_id: int) -> Tuple[bool, Optional[str]]:
        if user_id not in self.bans:
            return False, None
        expiry, reason, banned_by = self.bans[user_id]
        if expiry and datetime.utcnow() > expiry:
            del self.bans[user_id]
            self.save()
            return False, None
        if expiry:
            remaining = expiry - datetime.utcnow()
            hours = remaining.seconds // 3600
            minutes = (remaining.seconds % 3600) // 60
            time_left = f"{remaining.days}d {hours}h" if remaining.days > 0 else (f"{hours}h {minutes}m" if hours > 0 else f"{minutes}m")
            return True, f"Banned until {expiry.strftime('%Y-%m-%d %H:%M UTC')} ({time_left} left)\nReason: {reason}"
        return True, f"Permanently banned\nReason: {reason}"
    
    def get_bans(self) -> Dict:
        return self.bans.copy()
    
    def clean_expired(self):
        to_remove = [uid for uid, (expiry, _, _) in self.bans.items() if expiry and datetime.utcnow() > expiry]
        for uid in to_remove:
            del self.bans[uid]
        if to_remove:
            self.save()

ban_manager = BanManager()

def is_owner(interaction: discord.Interaction) -> bool:
    return interaction.user.id == BOT_OWNER_ID

# ─── Web Server ─────────────────────────────────────────────────────────────
app = Flask(__name__)

@app.route('/')
def home():
    return "🤖 Bot is alive and running 24/7!"

@app.route('/ping')
def ping():
    return "pong"

@app.route('/stats')
def stats():
    bans = ban_manager.get_bans()
    status, desc = bot_status.get_status()
    return {"status": status, "description": desc, "total_bans": len(bans), "owner_id": BOT_OWNER_ID}

def run_web():
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 8080)))

def keep_alive():
    t = Thread(target=run_web)
    t.daemon = True
    t.start()

# ─── Temp Email ──────────────────────────────────────────────────────────────
class TempEmail:
    def __init__(self):
        self.sid_token = None
        self.email_addr = None
        self.seq = 0
        self.seen_ids = set()

    def generate(self):
        r = requests.get(f"{GUERRILLA_API}?f=get_email_address", timeout=15)
        data = r.json()
        self.sid_token = data["sid_token"]
        self.seq = 0
        self.seen_ids = set()
        raw = data["email_addr"]
        at = raw.find("@")
        self.email_addr = (raw[:at + 1] if at != -1 else raw + "@") + "sharklasers.com"
        return self.email_addr

    def check_inbox(self):
        if not self.sid_token:
            return None
        try:
            r = requests.get(f"{GUERRILLA_API}?f=check_email&sid_token={self.sid_token}&seq={self.seq}", timeout=15)
            data = r.json()
            if "seq" in data:
                self.seq = data["seq"]
            for email in data.get("list", []):
                if email["mail_id"] in self.seen_ids:
                    continue
                self.seen_ids.add(email["mail_id"])
                code = self._extract_code(email.get("mail_subject", ""))
                if not code:
                    code = self._fetch_body_code(email["mail_id"])
                if code:
                    return code
        except Exception:
            pass
        return None

    def _fetch_body_code(self, mail_id):
        try:
            r = requests.get(f"{GUERRILLA_API}?f=fetch_email&email_id={mail_id}&sid_token={self.sid_token}", timeout=15)
            d = r.json()
            body = re.sub(r"<[^>]+>", "", d.get("mail_body", "") or "")
            return self._extract_code(d.get("mail_subject", "")) or self._extract_code(body)
        except Exception:
            return None

    @staticmethod
    def _extract_code(text):
        if not text:
            return None
        m = re.search(r"(\d{6})", text) or re.search(r"(\d{5})", text) or re.search(r"(\d{4})", text)
        return m.group(1) if m else None

    def wait_for_code(self, timeout=120, interval=3):
        deadline = time.time() + timeout
        while time.time() < deadline:
            code = self.check_inbox()
            if code:
                return code
            time.sleep(interval)
        return None

# ─── Cognito Auth ─────────────────────────────────────────────────────────────
def sign_up_with_cognito(email):
    try:
        cognito = Cognito(user_pool_id=USER_POOL_ID, client_id=COGNITO_CLIENT_ID, username=email, user_pool_region="eu-west-1")
        cognito.email = email
        cognito.given_name = "Bot"
        cognito.family_name = "User"
        cognito.register(username=email, password=PASSWORD)
        return {"status": "success", "message": "User signed up, waiting for confirmation"}
    except Exception as e:
        error_msg = str(e)
        if "User already exists" in error_msg or "UsernameExistsException" in error_msg:
            return {"status": "exists", "message": "User already exists"}
        raise RuntimeError(f"Sign-up failed: {error_msg}")

def confirm_sign_up_with_cognito(email, code):
    try:
        cognito = Cognito(user_pool_id=USER_POOL_ID, client_id=COGNITO_CLIENT_ID, username=email, user_pool_region="eu-west-1")
        cognito.confirm_sign_up(confirmation_code=code)
        return True
    except Exception as e:
        raise RuntimeError(f"Confirmation failed: {str(e)}")

def sign_in_with_cognito(email):
    try:
        cognito = Cognito(user_pool_id=USER_POOL_ID, client_id=COGNITO_CLIENT_ID, username=email, user_pool_region="eu-west-1")
        cognito.authenticate(password=PASSWORD)
        id_token = cognito.id_token
        if not id_token:
            raise RuntimeError("Failed to get ID token after authentication")
        return id_token
    except Exception as e:
        error_msg = str(e)
        if "NEW_PASSWORD_REQUIRED" in error_msg:
            try:
                cognito = Cognito(user_pool_id=USER_POOL_ID, client_id=COGNITO_CLIENT_ID, username=email, user_pool_region="eu-west-1")
                cognito.authenticate(password=PASSWORD)
                if hasattr(cognito, "new_password_required") and cognito.new_password_required:
                    cognito.set_new_password_challenge(PASSWORD)
                    cognito.authenticate(password=PASSWORD)
                return cognito.id_token
            except Exception as inner_e:
                raise RuntimeError(f"Failed to handle password change: {str(inner_e)}")
        raise RuntimeError(f"Authentication failed: {error_msg}")

# ─── Synthesia Generation ───────────────────────────────────────────────────────
SIZE_TO_ASPECT_RATIO = {"1280x720": "16:9", "720x1280": "9:16", "1080x1080": "1:1"}
VIDEO_MODELS = {"fal_veo3", "fal_veo3_fast", "sora_2", "seedance_2", "wan_2_6"}

def start_synthesia_generation(token, workspace_id, prompt, size, model):
    try:
        aspect_ratio = SIZE_TO_ASPECT_RATIO.get(size, "16:9")
        if model == "sora_2":
            model_request = {"modelName": "sora_2", "generateAudio": True, "aspectRatio": aspect_ratio}
            media_type = "video"
        elif model in ("fal_veo3", "fal_veo3_fast"):
            model_request = {"modelName": model, "aspectRatio": aspect_ratio, "generateAudio": True}
            media_type = "video"
        else:
            model_request = {"modelName": "nanobanana_pro", "aspectRatio": aspect_ratio}
            media_type = "image"
        r = requests.post("https://api.prd.synthesia.io/avatarServices/api/generatedMedia/stockFootage/bulk?numberOfResults=1",
            headers={"Authorization": token, "Content-Type": "application/json"},
            json={"mediaType": media_type, "modelRequest": model_request, "userPrompt": prompt, "workspaceId": workspace_id}, timeout=30)
        r.raise_for_status()
        result = r.json()
        if not result or len(result) == 0:
            raise RuntimeError("No asset ID returned from Synthesia")
        return result[0]["mediaAssetId"]
    except requests.exceptions.RequestException as e:
        raise RuntimeError(f"Failed to start generation: {str(e)}")

def poll_synthesia(token, asset_id, timeout=600, interval=8):
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            r = requests.get(f"https://api.synthesia.io/assets/{asset_id}", headers={"Authorization": token}, timeout=20)
            r.raise_for_status()
            data = r.json()
            status = data.get("uploadMetadata", {}).get("status", "unknown")
            if status == "ready":
                return data
            if status == "failed":
                raise RuntimeError("Generation failed on Synthesia side.")
            time.sleep(interval)
        except requests.exceptions.RequestException:
            time.sleep(interval)
    raise TimeoutError("Generation timed out after 10 minutes.")

def create_workspace(id_token):
    headers = {"Authorization": id_token, "Content-Type": "application/json"}
    res = requests.get("https://api.synthesia.io/workspaces?scope=public", headers=headers)
    res.raise_for_status()
    data = res.json()
    if data.get("results") and len(data["results"]) > 0:
        workspace_id = data["results"][0]["id"]
    else:
        res = requests.post("https://api.synthesia.io/workspaces", headers=headers, json={"strict": True, "includeDemoVideos": False})
        res.raise_for_status()
        workspace_id = res.json()["workspace"]["id"]
    try:
        requests.post("https://api.synthesia.io/user/onboarding/setPreferredWorkspaceId", headers=headers, json={"workspaceId": workspace_id})
    except Exception:
        pass
    try:
        requests.post("https://api.synthesia.io/user/onboarding/initialize", headers=headers, json={"featureFlags": {"freemiumEnabled": True}, "queryParams": {"paymentPlanType": "free"}, "allowReinitialize": False})
    except Exception:
        pass
    for _ in range(5):
        try:
            res = requests.post("https://api.synthesia.io/user/onboarding/completeCurrentStep", headers=headers, json={"featureFlags": {"freemiumEnabled": True}})
            if res.status_code != 200:
                break
        except Exception:
            break
    try:
        requests.post("https://api.synthesia.io/user/questionnaire", headers=headers, json={"company": {"size": "emerging", "industry": "professional_services"}, "seniority": "individual_contributor", "persona": "marketing"})
    except Exception:
        pass
    try:
        requests.post("https://api.synthesia.io/user/signupForm", headers=headers, json={"analyticsCookies": {}})
    except Exception:
        pass
    try:
        requests.post(f"https://api.synthesia.io/billing/self-serve/{workspace_id}/paywall", headers=headers, json={"targetPlan": "freemium", "redirectUrl": "https://app.synthesia.io/#/?plan_created=true&payment_plan=freemium"})
    except Exception:
        pass
    time.sleep(30)
    return workspace_id

def run_synthesia_generation(prompt: str, size: str, model: str) -> dict:
    temp = TempEmail()
    email = temp.generate()
    sign_up_with_cognito(email)
    code = temp.wait_for_code(timeout=120)
    if not code:
        raise RuntimeError("Timed out waiting for email verification code.")
    confirm_sign_up_with_cognito(email, code)
    token = sign_in_with_cognito(email)
    workspace_id = create_workspace(token)
    asset_id = start_synthesia_generation(token, workspace_id, prompt, size, model)
    result = poll_synthesia(token, asset_id)
    return {"url": result.get("url", ""), "download_url": result.get("downloadUrl", "")}

# ─── OreateAI Generation ───────────────────────────────────────────────────────
_OREATE_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"

def _oreate_generate_email() -> str:
    return "".join(random.choices(string.ascii_lowercase + string.digits, k=14)) + "@gmail.com"

def _oreate_generate_password() -> str:
    return "Aa" + "".join(random.choices("0123456789abcdef", k=8)) + "1!"

def _oreate_encrypt_password(plain_text: str, public_key_pem: str) -> str:
    clean_pem = public_key_pem.strip()
    if "BEGIN RSA PUBLIC KEY" in clean_pem:
        b64 = clean_pem.replace("-----BEGIN RSA PUBLIC KEY-----", "").replace("-----END RSA PUBLIC KEY-----", "").replace("\n", "").replace("\r", "").strip()
        key = RSA.import_key(_base64.b64decode(b64))
    else:
        key = RSA.import_key(clean_pem)
    cipher = PKCS1_v1_5.new(key)
    return _base64.b64encode(cipher.encrypt(plain_text.encode())).decode()

def _oreate_upload_image_to_gcs(image_bytes: bytes, filename: str, ext: str, session_cookies: dict) -> dict:
    clean_name = re.sub(r"\.[^.]+$", "", filename)
    token_res = requests.post(f"{OREATE_BASE}/oreate/convert/getuploadbostoken",
        headers={"Content-Type": "application/json", "Origin": OREATE_BASE, "Referer": f"{OREATE_BASE}/home/chat/aiImage",
                 "Cookie": "; ".join([f"{k}={v}" for k, v in session_cookies.items()]), "User-Agent": _OREATE_UA},
        json={"mFileList": [{"filename": clean_name, "fileExt": ext, "size": len(image_bytes)}], "source": "aiImage"}, timeout=30)
    token_res.raise_for_status()
    token_json = token_res.json()
    if token_json.get("status", {}).get("code") != 0:
        raise RuntimeError(f"Upload token failed: {token_json.get('status', {}).get('msg')}")
    key_list = token_json.get("data", {}).get("KeyList", {})
    key_data = key_list.get(f"{clean_name}.{ext}") or (list(key_list.values())[0] if key_list else None)
    if not key_data:
        raise RuntimeError(f"No upload token key received")
    bucket, object_path, session_key = key_data["bucket"], key_data["objectPath"], key_data["sessionkey"]
    content_type = f"image/{'jpeg' if ext == 'jpg' else ext}"
    gcs_init_url = f"https://storage.googleapis.com/upload/storage/v1/b/{bucket}/o?uploadType=resumable&name={requests.utils.quote(object_path, safe='')}"
    init_res = requests.post(gcs_init_url, headers={"Authorization": f"Bearer {session_key}", "Content-Type": "application/json",
                          "X-Upload-Content-Type": content_type, "X-Upload-Content-Length": str(len(image_bytes)),
                          "Origin": OREATE_BASE, "Referer": f"{OREATE_BASE}/"}, timeout=30)
    if not (200 <= init_res.status_code < 400):
        raise RuntimeError(f"GCS init failed: {init_res.status_code}")
    upload_url = init_res.headers.get("location") or init_res.headers.get("Location")
    if not upload_url:
        raise RuntimeError("GCS did not return upload URL")
    put_res = requests.put(upload_url, headers={"Content-Type": content_type, "Origin": OREATE_BASE, "Referer": f"{OREATE_BASE}/"}, data=image_bytes, timeout=120)
    if not put_res.ok:
        raise RuntimeError(f"GCS upload failed: {put_res.status_code}")
    return {"bos_url": object_path, "doc_title": clean_name, "doc_type": ext, "size": len(image_bytes), "bosUrl": object_path, "flag": "upload", "type": "file", "status": 1}

def _oreate_extract_image_url_from_stream(response_text: str) -> str:
    if not response_text:
        return None
    lines = response_text.split('\n')
    for line in lines:
        if line.startswith('data: '):
            try:
                data = _json.loads(line[6:])
                if data.get('data', {}).get('imgUrl'):
                    return data['data']['imgUrl']
                if data.get('data', {}).get('url'):
                    return data['data']['url']
                if data.get('imgUrl'):
                    return data['imgUrl']
                if data.get('url'):
                    return data['url']
            except:
                pass
    m = re.search(r"(https?://[^\s\"'<>]+\.(jpg|jpeg|png|gif|webp|bmp)(\?[^\s\"'<>]*)?)", response_text, re.IGNORECASE)
    return m.group(1) if m else None

def run_oreate_generation(prompt: str, size: str, ref_images: list) -> dict:
    ticket_res = requests.get(f"{OREATE_BASE}/passport/api/getticket",
        headers={"Accept": "application/json, text/plain, */*", "Accept-Language": "en-US,en;q=0.9", "Client-Type": "pc", "Locale": "en-US",
                 "Referer": f"{OREATE_BASE}/home/vertical/aiImage", "User-Agent": _OREATE_UA}, timeout=30)
    ticket_res.raise_for_status()
    ticket_data = ticket_res.json()
    ticket_id, public_key = ticket_data["data"]["ticketID"], ticket_data["data"]["pk"]
    cookies = ticket_res.cookies.get_dict()
    email, password = _oreate_generate_email(), _oreate_generate_password()
    encrypted_password = _oreate_encrypt_password(password, public_key)
    signup_res = requests.post(f"{OREATE_BASE}/passport/api/emailsignupin",
        headers={"Accept": "application/json, text/plain, */*", "Content-Type": "application/json", "Cookie": "; ".join([f"{k}={v}" for k, v in cookies.items()]),
                 "Locale": "en-US", "Origin": OREATE_BASE, "Referer": f"{OREATE_BASE}/home/vertical/aiImage", "User-Agent": _OREATE_UA},
        json={"fr": "GGSEMIMAGE", "email": email, "ticketID": ticket_id, "password": encrypted_password, "jt": ""}, timeout=30)
    signup_res.raise_for_status()
    signup_data = signup_res.json()
    if signup_data.get("status", {}).get("code") != 0:
        raise RuntimeError(f"OreateAI signup failed: {signup_data.get('status', {}).get('msg')}")
    session_cookies = signup_res.cookies.get_dict()
    session_cookies.update(cookies)
    attachments = []
    for idx, (image_bytes, filename, file_ext) in enumerate(ref_images[:9]):
        try:
            attachments.append(_oreate_upload_image_to_gcs(image_bytes, filename, file_ext, session_cookies))
        except Exception as e:
            print(f"Ref {idx+1} upload FAILED: {e}")
    chat_res = requests.post(f"{OREATE_BASE}/oreate/create/chat",
        headers={"Accept": "application/json, text/plain, */*", "Content-Type": "application/json", "Locale": "en-US", "Origin": OREATE_BASE,
                 "Referer": f"{OREATE_BASE}/home/chat/aiImage", "User-Agent": _OREATE_UA, "Cookie": "; ".join([f"{k}={v}" for k, v in session_cookies.items()])},
        json={"type": "aiImage", "docId": ""}, timeout=30)
    chat_res.raise_for_status()
    chat_id = chat_res.json().get("data", {}).get("chatId")
    if not chat_id:
        raise RuntimeError(f"OreateAI: no chatId in response")
    jt_token = "31$eyJrIj4iOCI0Iix5IkciQEdIRExETEtPSEpOUiJJIkFqIjwiNTw9OUE5QT08Pz5CQSI+IjYzIlEiSlFSTlZOVTk5ODY1OiIzIit5IkYiQD9AIj4iOCJQIklHS09KUExQIi0ibSI/Il1Yem52dVYxXTV2M0t2R1grXGZBQDNqTjx6bk5vVDxyclRyY18pPC8tdGpGRkNhWHloM2l0NGNlZDNCd2dIdl1vKXRZQ0VeRWY2L0lcN3pOKTpEUkAtNFA8S0xnRFg1XjY9eTBcWFVxX2dEeHhNbUFqTWNMZU9mV1VRVnFIeXhRYHNyTlQzVUVnSDFsRWxbWlxuaEo7OzlpcExQSXNqVzY8cj49PVAqcmEwQV1JblxgPjVjbFFSLEE2TGV0cGdmR1gzTz8tWXZkUlpKZSlEWUE6WltrajpDQGVQMzZyM3A5bHNdYzxSY29USUlrWmNlb2MwTl5KLk5zVUR4NURnPjc6W3o1TFk/djFyR2o1V3hceilvNy9nUms0c2NRZjQ5djcwOipgL09YWXVFdEtnNDMtNylvT3Zzblc0dnBQV0d4T088Xm5xVFJIaTdcS2BrbkpQW11wLmlfb1VyUTMzbk42XixTQXFiU3k/LF9EW2BgeGwyYTMtbmYzOTVtR290LjxBMC09cWdCW1FJVHhkLT03ODpCZC8xQ2dWTDc1SyxOMi4seEA7UlQxKUlPfCk1X2BjO3MubVBScWJbODh4VWl1L0oscHRdclJXQV90Zmg1WWBJL2tVLjtcfDIyfGZnOmg9QUFDQ3BEQXN3SERNdkd5TXpPU1MuUFUzYzQ5In0="
    request_body = {"jt": jt_token, "ua": _OREATE_UA, "js_env": "h5",
        "extra": {"email": email, "vip": "0", "reg_ts": int(time.time()), "deviceID": "EB78F52161CDCA4F55EF242566DAC05E:FG=1", "bid": "19caf744b12438441a8a1c", "doc_name": "", "module_name": "gpt4o"},
        "clientType": "wap", "type": "chat", "chatType": "aiImage", "chatTitle": "Unnamed Session", "focusId": chat_id, "chatId": chat_id, "from": "home",
        "messages": [{"role": "user", "content": prompt, "attachments": attachments}], "isFirst": True}
    sse_res = requests.post(f"{OREATE_BASE}/oreate/sse/stream",
        headers={"Accept": "text/event-stream", "Content-Type": "application/json", "Locale": "en-US", "Origin": OREATE_BASE,
                 "Referer": f"{OREATE_BASE}/home/chat/aiImage", "User-Agent": _OREATE_UA, "Cookie": "; ".join([f"{k}={v}" for k, v in session_cookies.items()])},
        json=request_body, stream=True, timeout=180)
    sse_res.raise_for_status()
    image_url = None
    full_response = ""
    for chunk in sse_res.iter_content(chunk_size=None, decode_unicode=True):
        if not chunk:
            continue
        full_response += chunk
        extracted = _oreate_extract_image_url_from_stream(chunk)
        if extracted:
            image_url = extracted
            break
        lines = chunk.split("\n")
        for line in lines:
            if line.startswith("data: "):
                try:
                    data = _json.loads(line[6:])
                    if data.get("data", {}).get("imgUrl"):
                        image_url = data["data"]["imgUrl"]
                        break
                    if data.get("data", {}).get("url"):
                        image_url = data["data"]["url"]
                        break
                except:
                    pass
        if image_url:
            break
    if not image_url:
        image_url = _oreate_extract_image_url_from_stream(full_response)
    if not image_url:
        raise RuntimeError("OreateAI: no image URL found in response")
    return {"url": image_url, "download_url": image_url, "is_nanobanana2": True}

# ─── Wan 2.6 Generation ─────────────────────────────────────────────────────
def _oreate_generate_video_password() -> str:
    return "Aa" + "".join(random.choices("0123456789abcdef", k=8)) + "1"

def _oreate_upload_video_reference_image(image_bytes: bytes, filename: str, ext: str, session_cookies: dict) -> dict:
    clean_name = re.sub(r"\.[^.]+$", "", filename)
    token_res = requests.post(f"{OREATE_BASE}/oreate/convert/getuploadbostoken",
        headers={"Content-Type": "application/json", "Origin": OREATE_BASE, "Referer": f"{OREATE_BASE}/home/chat/aiVideo",
                 "Cookie": "; ".join([f"{k}={v}" for k, v in session_cookies.items()]), "User-Agent": _OREATE_UA},
        json={"mFileList": [{"filename": clean_name, "fileExt": ext, "size": len(image_bytes)}], "source": "aiVideo"}, timeout=30)
    token_res.raise_for_status()
    token_json = token_res.json()
    if token_json.get("status", {}).get("code") != 0:
        raise RuntimeError(f"Upload token failed: {token_json.get('status', {}).get('msg')}")
    key_list = token_json.get("data", {}).get("KeyList", {})
    key_data = key_list.get(f"{clean_name}.{ext}") or (list(key_list.values())[0] if key_list else None)
    if not key_data:
        raise RuntimeError(f"No upload token key received")
    bucket, object_path, session_key = key_data["bucket"], key_data["objectPath"], key_data["sessionkey"]
    content_type = f"image/{'jpeg' if ext == 'jpg' else ext}"
    gcs_init_url = f"https://storage.googleapis.com/upload/storage/v1/b/{bucket}/o?uploadType=resumable&name={requests.utils.quote(object_path, safe='')}"
    init_res = requests.post(gcs_init_url, headers={"Authorization": f"Bearer {session_key}", "Content-Type": "application/json",
                          "X-Upload-Content-Type": content_type, "X-Upload-Content-Length": str(len(image_bytes)),
                          "Origin": OREATE_BASE, "Referer": f"{OREATE_BASE}/"}, timeout=30)
    if not (200 <= init_res.status_code < 400):
        raise RuntimeError(f"GCS init failed: {init_res.status_code}")
    upload_url = init_res.headers.get("location") or init_res.headers.get("Location")
    if not upload_url:
        raise RuntimeError("GCS did not return upload URL")
    put_res = requests.put(upload_url, headers={"Content-Type": content_type, "Origin": OREATE_BASE, "Referer": f"{OREATE_BASE}/"}, data=image_bytes, timeout=120)
    if not put_res.ok:
        raise RuntimeError(f"GCS upload failed: {put_res.status_code}")
    return {"bos_url": object_path, "doc_title": clean_name, "doc_type": ext, "size": len(image_bytes), "bosUrl": object_path, "flag": "upload", "type": "file", "status": 1}

def run_wan26_generation(prompt: str, size: str, ref_images: list = None) -> dict:
    ticket_res = requests.get(f"{OREATE_BASE}/passport/api/getticket",
        headers={"Accept": "application/json, text/plain, */*", "Accept-Language": "en-US,en;q=0.9", "Client-Type": "pc", "Locale": "en-US",
                 "Referer": f"{OREATE_BASE}/home/vertical/aiVideo", "User-Agent": _OREATE_UA}, timeout=30)
    ticket_res.raise_for_status()
    ticket_data = ticket_res.json()
    ticket_id, public_key = ticket_data["data"]["ticketID"], ticket_data["data"]["pk"]
    cookies = ticket_res.cookies.get_dict()
    email, password = _oreate_generate_email(), _oreate_generate_video_password()
    encrypted_password = _oreate_encrypt_password(password, public_key)
    signup_res = requests.post(f"{OREATE_BASE}/passport/api/emailsignupin",
        headers={"Accept": "application/json, text/plain, */*", "Content-Type": "application/json", "Cookie": "; ".join([f"{k}={v}" for k, v in cookies.items()]),
                 "Locale": "en-US", "Origin": OREATE_BASE, "Referer": f"{OREATE_BASE}/home/vertical/aiVideo", "User-Agent": _OREATE_UA},
        json={"fr": "GGSEMVIDEO", "email": email, "ticketID": ticket_id, "password": encrypted_password, "jt": ""}, timeout=30)
    signup_res.raise_for_status()
    signup_data = signup_res.json()
    if signup_data.get("status", {}).get("code") != 0:
        raise RuntimeError(f"Wan 2.6 signup failed: {signup_data.get('status', {}).get('msg')}")
    session_cookies = signup_res.cookies.get_dict()
    session_cookies.update(cookies)
    attachments = []
    if ref_images:
        for idx, (image_bytes, filename, file_ext) in enumerate(ref_images[:9]):
            try:
                attachments.append(_oreate_upload_video_reference_image(image_bytes, filename, file_ext, session_cookies))
            except Exception as e:
                print(f"Ref {idx+1} upload FAILED: {e}")
    chat_res = requests.post(f"{OREATE_BASE}/oreate/create/chat",
        headers={"Accept": "application/json, text/plain, */*", "Content-Type": "application/json", "Locale": "en-US", "Origin": OREATE_BASE,
                 "Referer": f"{OREATE_BASE}/home/chat/aiVideo", "User-Agent": _OREATE_UA, "Cookie": "; ".join([f"{k}={v}" for k, v in session_cookies.items()])},
        json={"type": "aiVideo", "docId": ""}, timeout=30)
    chat_res.raise_for_status()
    chat_id = chat_res.json().get("data", {}).get("chatId")
    if not chat_id:
        raise RuntimeError(f"Wan 2.6: no chatId in response")
    jt_token = "31$eyJrIj4iOCI0Iix5IkciQEdIRExETEtPSEpOUiJJIkFqIjwiNTw9OUE5QT08Pz5CQSI+IjYzIlEiSlFSTlZOVTk5ODY1OiIzIit5IkYiQD9AIj4iOCJQIklHS09KUExQIi0ibSI/Il1Yem52dVYxXTV2M0t2R1grXGZBQDNqTjx6bk5vVDxyclRyY18pPC8tdGpGRkNhWHloM2l0NGNlZDNCd2dIdl1vKXRZQ0VeRWY2L0lcN3pOKTpEUkAtNFA8S0xnRFg1XjY9eTBcWFVxX2dEeHhNbUFqTWNMZU9mV1VRVnFIeXhRYHNyTlQzVUVnSDFsRWxbWlxuaEo7OzlpcExQSXNqVzY8cj49PVAqcmEwQV1JblxgPjVjbFFSLEE2TGV0cGdmR1gzTz8tWXZkUlpKZSlEWUE6WltrajpDQGVQMzZyM3A5bHNdYzxSY29USUlrWmNlb2MwTl5KLk5zVUR4NURnPjc6W3o1TFk/djFyR2o1V3hceilvNy9nUms0c2NRZjQ5djcwOipgL09YWXVFdEtnNDMtNylvT3Zzblc0dnBQV0d4T088Xm5xVFJIaTdcS2BrbkpQW11wLmlfb1VyUTMzbk42XixTQXFiU3k/LF9EW2BgeGwyYTMtbmYzOTVtR290LjxBMC09cWdCW1FJVHhkLT03ODpCZC8xQ2dWTDc1SyxOMi4seEA7UlQxKUlPfCk1X2BjO3MubVBScWJbODh4VWl1L0oscHRdclJXQV90Zmg1WWBJL2tVLjtcfDIyfGZnOmg9QUFDQ3BEQXN3SERNdkd5TXpPU1MuUFUzYzQ5In0="
    request_body = {"jt": jt_token, "ua": _OREATE_UA, "js_env": "h5",
        "extra": {"email": email, "vip": "0", "reg_ts": int(time.time()), "deviceID": "EB78F52161CDCA4F55EF242566DAC05E:FG=1", "bid": "19caf744b12438441a8a1c", "doc_name": "", "module_name": "gpt4o"},
        "clientType": "pc", "type": "chat", "chatType": "aiVideo", "chatTitle": "Unnamed Session", "focusId": chat_id, "chatId": chat_id, "from": "home",
        "messages": [{"role": "user", "content": prompt, "attachments": attachments}], "isFirst": True}
    sse_res = requests.post(f"{OREATE_BASE}/oreate/sse/stream",
        headers={"Accept": "text/event-stream", "Content-Type": "application/json", "Locale": "en-US", "Origin": OREATE_BASE,
                 "Referer": f"{OREATE_BASE}/home/chat/aiVideo", "User-Agent": _OREATE_UA, "Cookie": "; ".join([f"{k}={v}" for k, v in session_cookies.items()])},
        json=request_body, stream=True, timeout=180)
    sse_res.raise_for_status()
    video_url = None
    full_response = ""
    for chunk in sse_res.iter_content(chunk_size=None, decode_unicode=True):
        if not chunk:
            continue
        full_response += chunk
        lines = chunk.split("\n")
        for line in lines:
            if line.startswith("data: "):
                try:
                    data = _json.loads(line[6:])
                    if data.get("data", {}).get("videoUrl"):
                        video_url = data["data"]["videoUrl"]
                        break
                    if data.get("data", {}).get("url"):
                        url = data["data"]["url"]
                        if url and any(url.endswith(ext) for ext in ['.mp4', '.mov', '.avi', '.webm', '.mkv']):
                            video_url = url
                            break
                    if data.get("videoUrl"):
                        video_url = data["videoUrl"]
                        break
                    if data.get("url"):
                        url = data["url"]
                        if url and any(url.endswith(ext) for ext in ['.mp4', '.mov', '.avi', '.webm', '.mkv']):
                            video_url = url
                            break
                except:
                    pass
        if not video_url:
            url_match = re.search(r"(https?://[^\s\"'<>]+\.(mp4|mov|avi|webm|mkv)(\?[^\s\"'<>]*)?)", chunk, re.IGNORECASE)
            if url_match:
                video_url = url_match.group(1)
                break
        if video_url:
            break
    if not video_url:
        url_match = re.search(r"(https?://[^\s\"'<>]+\.(mp4|mov|avi|webm|mkv)(\?[^\s\"'<>]*)?)", full_response, re.IGNORECASE)
        if url_match:
            video_url = url_match.group(1)
    if not video_url:
        raise RuntimeError("Wan 2.6: no video URL found in response")
    return {"url": video_url, "download_url": video_url}

# ─── Seedance 2 via Buzzy ─────────────────────────────────────────────────────
class _HTMLTextExtractor(HTMLParser):
    def __init__(self):
        super().__init__()
        self._parts = []
    def handle_data(self, data):
        self._parts.append(data)
    def get_text(self):
        return ' '.join(self._parts)

def _strip_html(html):
    if not html:
        return ''
    parser = _HTMLTextExtractor()
    try:
        parser.feed(html)
        return parser.get_text()
    except Exception:
        return html

def _extract_code_from_text(text):
    if not text:
        return None
    m = re.search(r'(\d{6})', text) or re.search(r'(\d{5})', text) or re.search(r'(?:verification\s+code|verification|code|otp)[^\d]{0,20}?(\d{4})', text, re.IGNORECASE) or re.search(r'(\d{4})', text)
    return m.group(1) if m else None

def _buzzy_generate_temp_email():
    response = requests.get(f"{GUERRILLA_API}?f=get_email_address")
    data = response.json()
    if 'email_addr' not in data:
        raise Exception(f"Failed to generate temp email")
    sid_token = data['sid_token']
    local_part = data['email_addr'].split('@')[0]
    return f"{local_part}@sharklasers.com", sid_token

def _buzzy_generate_random_password():
    return random.choice(string.ascii_uppercase) + ''.join(random.choices(string.ascii_lowercase, k=3)) + str(random.randint(1000, 9999))

def _buzzy_send_verification_code(email):
    response = requests.post('https://api.buzzy.now/api/v1/user/send-email-code', json={'email': email, 'type': 1}, headers={'Content-Type': 'application/json'})
    data = response.json()
    if data.get('code') != 200:
        raise Exception(f"Failed to send verification code")
    return True

def _buzzy_wait_for_code(sid_token, max_attempts=30, interval=4):
    current_seq, seen_ids = 0, set()
    for attempt in range(max_attempts):
        response = requests.get(f"{GUERRILLA_API}?f=check_email&sid_token={sid_token}&seq={current_seq}")
        data = response.json()
        if 'seq' in data:
            current_seq = data['seq']
        for mail in data.get('list', []):
            mail_id = mail.get('mail_id')
            if mail_id in seen_ids:
                continue
            seen_ids.add(mail_id)
            code = _extract_code_from_text(mail.get('mail_subject', '')) or _extract_code_from_text(mail.get('mail_from', ''))
            if not code:
                try:
                    full = requests.get(f"{GUERRILLA_API}?f=fetch_email&email_id={mail_id}&sid_token={sid_token}").json()
                    body = full.get('mail_body', '') or full.get('mail_excerpt', '')
                    code = _extract_code_from_text(_strip_html(body)) or _extract_code_from_text(body)
                except Exception:
                    pass
            if code:
                return code
        time.sleep(interval)
    return None

def _buzzy_register_user(email, password, email_code):
    response = requests.post('https://api.buzzy.now/api/v1/user/register', json={'email': email, 'password': password, 'emailCode': email_code}, headers={'Content-Type': 'application/json'})
    data = response.json()
    if data.get('code') == 200:
        return data['data']['token']
    raise Exception(f"Registration failed")

def _buzzy_create_video_project(token, prompt):
    response = requests.post('https://api.buzzy.now/api/app/v1/project/create',
        json={'name': 'Untitled', 'workflowType': 'SOTA', 'instructionSegments': [{'type': 'text', 'content': prompt}], 'imageUrls': [], 'duration': 10, 'aspectRatio': '16:9', 'prompt': prompt},
        headers={'Content-Type': 'application/json', 'Authorization': f'Bearer {token}'})
    data = response.json()
    if data.get('code') == 201:
        return data['data']['id']
    raise Exception(f"Failed to create video project")

def _buzzy_poll_for_video(token, project_id, interval=5):
    while True:
        response = requests.get('https://api.buzzy.now/api/app/v1/project/list?pageNumber=1&pageSize=100',
            headers={'Authorization': f'Bearer {token}', 'accept': 'application/json, text/plain, */*', 'accept-language': 'en-US,en;q=0.9', 'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'})
        data = response.json()
        if data.get('code') != 200:
            time.sleep(interval)
            continue
        records = data.get('data', {}).get('records', [])
        target = next((p for p in records if p.get('id') == project_id), None)
        if target:
            status = target.get('status', 'unknown')
            if status == 'success':
                results = target.get('results', [])
                if results and len(results) > 0 and results[0].get('videoUrl'):
                    return results[0]['videoUrl']
                video_urls = target.get('videoUrls', [])
                if video_urls and len(video_urls) > 0 and video_urls[0]:
                    return video_urls[0]
            elif status == 'failed':
                raise Exception(f"Video generation failed")
        time.sleep(interval)

def run_seedance2_generation(prompt: str) -> dict:
    email, sid_token = _buzzy_generate_temp_email()
    password = _buzzy_generate_random_password()
    _buzzy_send_verification_code(email)
    code = _buzzy_wait_for_code(sid_token)
    if not code:
        raise Exception("Did not receive a verification code")
    token = _buzzy_register_user(email, password, code)
    project_id = _buzzy_create_video_project(token, prompt)
    video_url = _buzzy_poll_for_video(token, project_id)
    return {"url": video_url, "download_url": video_url}

# ─── Dispatch ─────────────────────────────────────────────────────────────────
def run_generation(prompt: str, size: str, model: str, ref_images: list = None) -> dict:
    if model == "nanobanana_2":
        return run_oreate_generation(prompt, size, ref_images or [])
    if model == "seedance_2":
        return run_seedance2_generation(prompt)
    if model == "wan_2_6":
        return run_wan26_generation(prompt, size, ref_images or [])
    return run_synthesia_generation(prompt, size, model)

# ─── Progress Tracking ──────────────────────────────────────────────────────
def format_duration(seconds):
    minutes, secs = divmod(int(seconds), 60)
    return f"{minutes}m {secs}s" if minutes > 0 else f"{secs}s"

PROGRESS_STAGES = [
    {"threshold": 0, "label": "Initializing", "emoji": "⚙️"},
    {"threshold": 5, "label": "Creating account", "emoji": "📧"},
    {"threshold": 15, "label": "Verifying email", "emoji": "✉️"},
    {"threshold": 30, "label": "Setting up workspace", "emoji": "🛠️"},
    {"threshold": 65, "label": "Generating media", "emoji": "🎨"},
    {"threshold": 120, "label": "Rendering", "emoji": "🎬"},
    {"threshold": 300, "label": "Finalizing", "emoji": "✨"},
]

NB2_PROGRESS_STAGES = [
    {"threshold": 0, "label": "Initializing", "emoji": "⚙️"},
    {"threshold": 3, "label": "Creating account", "emoji": "📧"},
    {"threshold": 10, "label": "Generating image", "emoji": "🎨"},
    {"threshold": 60, "label": "Finalizing", "emoji": "✨"},
]

WAN26_PROGRESS_STAGES = [
    {"threshold": 0, "label": "Initializing", "emoji": "⚙️"},
    {"threshold": 5, "label": "Creating account", "emoji": "📧"},
    {"threshold": 10, "label": "Uploading images", "emoji": "📤"},
    {"threshold": 20, "label": "Generating video", "emoji": "🎨"},
    {"threshold": 90, "label": "Rendering", "emoji": "🎬"},
    {"threshold": 105, "label": "Finalizing", "emoji": "✨"},
]

SEEDANCE2_PROGRESS_STAGES = [
    {"threshold": 0, "label": "Initializing", "emoji": "⚙️"},
    {"threshold": 5, "label": "Creating account", "emoji": "📧"},
    {"threshold": 15, "label": "Verifying email", "emoji": "✉️"},
    {"threshold": 30, "label": "Registering user", "emoji": "📝"},
    {"threshold": 60, "label": "Generating video", "emoji": "🎨"},
    {"threshold": 300, "label": "Rendering", "emoji": "🎬"},
    {"threshold": 600, "label": "Finalizing", "emoji": "✨"},
]

def get_stage(elapsed, stages):
    current = stages[0]
    for stage in stages:
        if elapsed >= stage["threshold"]:
            current = stage
    return current

def get_progress_bar(progress_percent, length=20):
    filled = int(length * progress_percent)
    return "█" * filled + "░" * (length - filled)

def build_progress_embed(prompt, size_label, elapsed, model_label, model_value="", ref_count=0, completed=None, total=None, results=None):
    status, status_desc = bot_status.get_status()
    
    if status == BotStatus.BROKEN:
        embed = discord.Embed(title="🔴 Bot is Currently Broken", color=BROKEN_COLOR)
        embed.description = f"**⚠️ NOTE:** {status_desc if status_desc else 'The bot is currently experiencing issues and cannot generate media.'}"
        embed.add_field(name="📝 Prompt", value=f"```{prompt[:200]}```", inline=False)
        return embed
    
    if model_value == "nanobanana_2":
        stages = NB2_PROGRESS_STAGES
        estimated_total = 60
    elif model_value == "seedance_2":
        stages = SEEDANCE2_PROGRESS_STAGES
        estimated_total = 840
    elif model_value == "wan_2_6":
        stages = WAN26_PROGRESS_STAGES
        estimated_total = 120
    else:
        stages = PROGRESS_STAGES
        estimated_total = 180

    stage = get_stage(elapsed, stages)
    
    if total and total > 1:
        progress_percent = completed / total if completed else 0
        if completed == 0:
            stage_label = "Starting batch generation (ALL videos in parallel)"
            stage_emoji = "🚀"
        elif completed < total:
            stage_label = f"Generating {completed}/{total} videos completed"
            stage_emoji = "🎬"
        else:
            stage_label = "All videos complete!"
            stage_emoji = "✨"
    else:
        progress_percent = min(elapsed / estimated_total, 0.95)
        stage_label = stage["label"]
        stage_emoji = stage["emoji"]
    
    bar = get_progress_bar(progress_percent)
    
    color = PROGRESS_COLOR
    title = "🎨  Generating Your Media"
    footer = f"Powered by {model_label}  |  Please wait..."
    
    if status == BotStatus.BUGGY:
        color = BUGGY_COLOR
        title = "⚠️ [BUGGY MODE] " + title
        footer = "⚠️ NOTE: Bot is in buggy mode - " + (status_desc if status_desc else "Some features may not work correctly") + " | " + footer

    embed = discord.Embed(title=title, color=color)
    
    if status == BotStatus.BUGGY and status_desc:
        embed.description = f"**⚠️ NOTE:** {status_desc}"
    
    embed.add_field(name="📝 Prompt", value=f"```{prompt[:200]}```", inline=False)
    if size_label:
        embed.add_field(name="📏 Size", value=f"`{size_label}`", inline=True)
    embed.add_field(name="🧠 Model", value=f"`{model_label}`", inline=True)
    if ref_count > 0:
        embed.add_field(name="🖼️ Reference Images", value=f"`{ref_count} image(s)`", inline=True)
    embed.add_field(name="⏱️ Elapsed", value=f"`{format_duration(elapsed)}`", inline=True)
    embed.add_field(name=f"{stage_emoji} Status", value=f"**{stage_label}**", inline=True)
    embed.add_field(name="Progress", value=f"`{bar}` {int(progress_percent * 100)}%", inline=False)
    
    if total and total > 1:
        embed.add_field(name="📊 Batch Progress", value=f"**{completed}/{total} videos completed**\n🎬 All videos generating in PARALLEL!", inline=False)
    
    # Show completed links in the SAME message
    if results and len(results) > 0:
        links_text = ""
        for idx, result in enumerate(results, 1):
            if result and result.get("url"):
                url = result.get("download_url") or result.get("url")
                links_text += f"✅ **Video #{idx}:** [Click to download]({url})\n"
            elif result and result.get("error"):
                links_text += f"❌ **Video #{idx}:** Failed - {result.get('error', 'Unknown error')[:50]}\n"
            else:
                links_text += f"⏳ **Video #{idx}:** Still generating...\n"
            
            if len(links_text) > 1800:
                links_text = links_text[:1797] + "..."
                break
        
        if links_text:
            embed.add_field(name="📥 Download Links (Updating Live)", value=links_text[:1024], inline=False)
    
    embed.set_footer(text=footer)
    return embed

def build_success_embed(prompt, size_label, duration, model_label, model_value="", ref_images=None):
    status, status_desc = bot_status.get_status()
    
    color = SUCCESS_COLOR
    title = "✅  Media Generated Successfully!"
    footer = f"Powered by {model_label}"
    
    if status == BotStatus.BUGGY:
        color = BUGGY_COLOR
        title = "⚠️ [BUGGY MODE] " + title
        footer = "⚠️ NOTE: Bot is in buggy mode - " + (status_desc if status_desc else "Some features may not work correctly") + " | " + footer
    
    embed = discord.Embed(title=title, color=color, timestamp=discord.utils.utcnow())
    
    if status == BotStatus.BUGGY and status_desc:
        embed.description = f"**⚠️ NOTE:** {status_desc}"
    
    embed.add_field(name="📝 Prompt", value=f"```{prompt[:200]}```", inline=False)
    if size_label:
        embed.add_field(name="📏 Size", value=f"`{size_label}`", inline=True)
    embed.add_field(name="🧠 Model", value=f"`{model_label}`", inline=True)
    embed.add_field(name="⏱️ Time Taken", value=f"`{format_duration(duration)}`", inline=True)
    
    if ref_images and len(ref_images) > 0:
        ref_text = ""
        for idx, (_, filename, _) in enumerate(ref_images[:9], 1):
            ref_text += f"📷 **Ref {idx}:** `{filename}`\n"
        embed.add_field(name=f"🖼️ Reference Images ({len(ref_images)})", value=ref_text, inline=False)
    
    embed.set_footer(text=footer)
    return embed

def build_error_embed(error_msg, prompt, size_label, model_label, model_value="", ref_images=None):
    status, status_desc = bot_status.get_status()
    
    color = ERROR_COLOR
    title = "❌  Generation Failed"
    footer = "Please try again later"
    
    if status == BotStatus.BUGGY:
        color = BUGGY_COLOR
        title = "⚠️ [BUGGY MODE] " + title
        footer = "⚠️ NOTE: Bot is in buggy mode - " + (status_desc if status_desc else "Some features may not work correctly") + " | " + footer
    
    embed = discord.Embed(title=title, color=color, timestamp=discord.utils.utcnow())
    
    if status == BotStatus.BUGGY and status_desc:
        embed.description = f"**⚠️ NOTE:** {status_desc}"
    
    embed.add_field(name="📝 Prompt", value=f"```{prompt[:200]}```", inline=False)
    if size_label:
        embed.add_field(name="📏 Size", value=f"`{size_label}`", inline=True)
    embed.add_field(name="🧠 Model", value=f"`{model_label}`", inline=True)
    
    if ref_images and len(ref_images) > 0:
        ref_text = ""
        for idx, (_, filename, _) in enumerate(ref_images[:9], 1):
            ref_text += f"📷 **Ref {idx}:** `{filename}`\n"
        embed.add_field(name=f"🖼️ Reference Images ({len(ref_images)})", value=ref_text, inline=False)
    
    embed.add_field(name="⚠️ Error", value=f"```{str(error_msg)[:500]}```", inline=False)
    embed.set_footer(text=footer)
    return embed

# ─── Multi-generation Handler (ALL LINKS IN SAME MESSAGE) ────────────────────
class MultiGenerationHandler:
    def __init__(self, interaction: discord.Interaction, prompt: str, model_value: str, model_label: str, 
                 size_value: str, size_label: str, amount: int, ref_images: list):
        self.interaction = interaction
        self.prompt = prompt
        self.model_value = model_value
        self.model_label = model_label
        self.size_value = size_value
        self.size_label = size_label
        self.amount = amount
        self.ref_images = ref_images
        self.results = [None] * amount
        self.completed = 0
        self.status_message = None
        self.start_time = None
        self.generation_done = False
        self.lock = asyncio.Lock()
    
    async def run(self):
        self.start_time = time.time()
        
        # Send initial progress embed
        embed = build_progress_embed(self.prompt, self.size_label, 0, self.model_label, 
                                      self.model_value, len(self.ref_images), 0, self.amount, self.results)
        await self.interaction.response.send_message(embed=embed)
        self.status_message = await self.interaction.original_response()
        
        # Start timer update task
        timer_task = asyncio.create_task(self._update_timer())
        
        # Create all tasks to run in PARALLEL
        tasks = []
        for i in range(self.amount):
            task = asyncio.create_task(self._generate_one(i))
            tasks.append(task)
        
        # Wait for all to complete
        await asyncio.gather(*tasks)
        
        # Stop timer
        self.generation_done = True
        timer_task.cancel()
        try:
            await timer_task
        except asyncio.CancelledError:
            pass
        
        # Final update with all links
        total_time = time.time() - self.start_time
        successful = len([r for r in self.results if r and r.get("url")])
        
        final_embed = discord.Embed(
            title="✅ Batch Generation Complete!",
            description=f"**{successful}/{self.amount}** videos generated successfully!\n⏱️ Total time: **{format_duration(total_time)}**",
            color=SUCCESS_COLOR,
            timestamp=discord.utils.utcnow()
        )
        
        # Add all links to final message
        links_text = ""
        for idx, result in enumerate(self.results, 1):
            if result and result.get("url"):
                url = result.get("download_url") or result.get("url")
                links_text += f"✅ **Video #{idx}:** [Click to download]({url})\n"
            elif result and result.get("error"):
                links_text += f"❌ **Video #{idx}:** Failed\n"
            else:
                links_text += f"❌ **Video #{idx}:** Failed\n"
        
        if links_text:
            final_embed.add_field(name="📥 All Download Links", value=links_text[:1024], inline=False)
        
        await self.status_message.edit(embed=final_embed)
    
    async def _generate_one(self, index: int):
        """Generate one video and update the SAME message with its link"""
        try:
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(
                None, run_generation, self.prompt, self.size_value, self.model_value, self.ref_images
            )
            async with self.lock:
                self.results[index] = result
                self.completed += 1
        except Exception as exc:
            async with self.lock:
                self.results[index] = {"error": str(exc), "url": None}
                self.completed += 1
        
        # Update the message immediately with the new link
        elapsed = time.time() - self.start_time
        embed = build_progress_embed(self.prompt, self.size_label, elapsed, self.model_label,
                                      self.model_value, len(self.ref_images), self.completed, self.amount, self.results)
        await self.status_message.edit(embed=embed)
    
    async def _update_timer(self):
        """Update the timer display every 3 seconds"""
        while not self.generation_done:
            await asyncio.sleep(3)
            if self.generation_done:
                break
            try:
                elapsed = time.time() - self.start_time
                embed = build_progress_embed(self.prompt, self.size_label, elapsed, self.model_label,
                                              self.model_value, len(self.ref_images), self.completed, self.amount, self.results)
                await self.status_message.edit(embed=embed)
            except Exception as e:
                print(f"Timer update error: {e}")

# ─── Discord Commands ─────────────────────────────────────────────────────────
SIZE_LABELS = {"1080x1080": "1:1", "720x1280": "9:16", "1280x720": "16:9", "ai_decide": "AI decided"}
size_choices = [app_commands.Choice(name="16:9", value="1280x720"), app_commands.Choice(name="9:16", value="720x1280"), app_commands.Choice(name="AI decided", value="ai_decide")]
NBP_AI_SIZES = ["1080x1080", "1280x720", "720x1280"]

model_choices = [
    app_commands.Choice(name="Nano Banana Pro", value="nanobanana_pro"),
    app_commands.Choice(name="Nano Banana 2", value="nanobanana_2"),
    app_commands.Choice(name="Sora 2", value="sora_2"),
    app_commands.Choice(name="Veo 3.1", value="fal_veo3"),
    app_commands.Choice(name="Veo 3.1 Fast", value="fal_veo3_fast"),
    app_commands.Choice(name="Seedance 2", value="seedance_2"),
    app_commands.Choice(name="Wan 2.6", value="wan_2_6"),
]

amount_choices = [app_commands.Choice(name=str(i), value=i) for i in range(1, 11)]

MODEL_LABELS = {
    "nanobanana_pro": "Nano Banana Pro", "nanobanana_2": "Nano Banana 2", "sora_2": "Sora 2",
    "fal_veo3": "Veo 3.1", "fal_veo3_fast": "Veo 3.1 Fast", "seedance_2": "Seedance 2", "wan_2_6": "Wan 2.6",
}

@client.event
async def on_ready():
    await tree.sync()
    print(f"✅ Bot online! Logged in as: {client.user}")
    print(f"👑 Owner ID: {BOT_OWNER_ID}")

@discord.app_commands.allowed_installs(guilds=True, users=True)
@discord.app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
@tree.command(name="generate", description="Generate AI media")
@app_commands.describe(
    prompt="What the media should show",
    model="AI model to use",
    size="Resolution",
    amount="Number to generate (1-10) - ALL GENERATE IN PARALLEL",
    ref1="Reference image 1 (Nano Banana 2 / Wan 2.6 only)",
    ref2="Reference image 2",
    ref3="Reference image 3",
    ref4="Reference image 4",
    ref5="Reference image 5",
    ref6="Reference image 6",
    ref7="Reference image 7",
    ref8="Reference image 8",
    ref9="Reference image 9",
)
@app_commands.choices(size=size_choices, model=model_choices, amount=amount_choices)
async def generate(
    interaction: discord.Interaction, 
    prompt: str,
    model: app_commands.Choice[str] = None, 
    size: app_commands.Choice[str] = None,
    amount: app_commands.Choice[int] = None,
    ref1: discord.Attachment = None, 
    ref2: discord.Attachment = None, 
    ref3: discord.Attachment = None,
    ref4: discord.Attachment = None, 
    ref5: discord.Attachment = None, 
    ref6: discord.Attachment = None,
    ref7: discord.Attachment = None, 
    ref8: discord.Attachment = None, 
    ref9: discord.Attachment = None,
):
    # Check ban
    banned, ban_msg = ban_manager.is_banned(interaction.user.id)
    if banned:
        embed = discord.Embed(title="🔒 You are Banned", description=ban_msg, color=ERROR_COLOR)
        await interaction.response.send_message(embed=embed, ephemeral=True)
        return
    
    # Check bot status
    status, status_desc = bot_status.get_status()
    if status == BotStatus.BROKEN:
        embed = discord.Embed(title="🔴 Bot is Currently Broken", color=BROKEN_COLOR)
        embed.description = f"**⚠️ NOTE:** {status_desc if status_desc else 'The bot is currently experiencing issues.'}"
        await interaction.response.send_message(embed=embed, ephemeral=True)
        return
    
    amount_value = amount.value if amount else 1
    model_value = model.value if model else "nanobanana_pro"
    model_label = MODEL_LABELS.get(model_value, model_value)
    raw_size = size.value if size else None

    # Determine size
    if model_value == "nanobanana_2":
        size_value, size_label = raw_size or "ai_decide", "AI decided"
    elif model_value in ["seedance_2", "wan_2_6"]:
        size_value, size_label = "1280x720", "16:9"
    elif raw_size == "ai_decide" or raw_size is None:
        if model_value in VIDEO_MODELS:
            size_value = random.choice(["1280x720", "720x1280"])
        else:
            size_value = random.choice(NBP_AI_SIZES)
        size_label = "AI decided"
    else:
        size_value, size_label = raw_size, SIZE_LABELS.get(raw_size, raw_size)

    # Handle reference images
    ref_images = []
    if model_value in ["nanobanana_2", "wan_2_6"]:
        raw_refs = [ref1, ref2, ref3, ref4, ref5, ref6, ref7, ref8, ref9]
        bad_refs = []
        for attachment in raw_refs:
            if not attachment:
                continue
            ext = attachment.filename.split(".")[-1].lower() if "." in attachment.filename else ""
            if not ext or f".{ext}" not in VALID_IMAGE_EXTENSIONS:
                bad_refs.append(attachment.filename)
            else:
                ref_images.append(attachment)
        
        if bad_refs:
            await interaction.response.send_message(f"⚠️ Invalid images: `{'`, `'.join(bad_refs)}`", ephemeral=True)
            return
        
        downloaded = []
        for attachment in ref_images:
            try:
                img_bytes = await attachment.read()
                ext = attachment.filename.split(".")[-1].lower()
                downloaded.append((img_bytes, attachment.filename, ext))
            except Exception as e:
                print(f"Failed to download: {e}")
        ref_images = downloaded
    else:
        if any([ref1, ref2, ref3, ref4, ref5, ref6, ref7, ref8, ref9]):
            await interaction.response.send_message("⚠️ Reference images only work with **Nano Banana 2** or **Wan 2.6**.", ephemeral=True)
            return

    # Handle batch generation (PARALLEL with links in same message)
    if amount_value > 1:
        handler = MultiGenerationHandler(interaction, prompt, model_value, model_label,
                                          size_value, size_label, amount_value, ref_images)
        await handler.run()
        return
    
    # Single generation
    start_embed = build_progress_embed(prompt, size_label, 0, model_label, model_value, len(ref_images))
    await interaction.response.send_message(embed=start_embed)
    status_msg = await interaction.original_response()

    start_time = time.time()
    generation_done = asyncio.Event()
    generation_result = {"data": None, "error": None}

    async def run_gen():
        try:
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(None, run_generation, prompt, size_value, model_value, ref_images)
            generation_result["data"] = result
        except Exception as exc:
            generation_result["error"] = str(exc)
        finally:
            generation_done.set()

    async def update_timer():
        while not generation_done.is_set():
            await asyncio.sleep(3)
            if generation_done.is_set():
                break
            elapsed = time.time() - start_time
            try:
                progress_embed = build_progress_embed(prompt, size_label, elapsed, model_label, model_value, len(ref_images))
                await status_msg.edit(embed=progress_embed)
            except Exception:
                pass

    asyncio.create_task(run_gen())
    timer_task = asyncio.create_task(update_timer())
    await generation_done.wait()
    timer_task.cancel()
    
    total_time = time.time() - start_time

    if generation_result["error"]:
        error_embed = build_error_embed(generation_result["error"], prompt, size_label, model_label, model_value, ref_images)
        await status_msg.edit(embed=error_embed)
        return

    result = generation_result["data"]
    success_embed = build_success_embed(prompt, size_label, total_time, model_label, model_value, ref_images)

    media_file = None
    download_url = result.get("download_url") or result.get("url")
    if download_url:
        try:
            response = download_session.get(download_url, timeout=60)
            response.raise_for_status()
            media_bytes = response.content
            is_image = model_value not in VIDEO_MODELS or model_value == "nanobanana_2"
            ext = "png" if is_image else "mp4"
            filename = f"generated_media.{ext}"
            
            if not is_image and len(media_bytes) > 25 * 1024 * 1024:
                success_embed.add_field(name="📥 Download", value=f"[Click to download video]({download_url})", inline=False)
            else:
                media_file = discord.File(io.BytesIO(media_bytes), filename=filename)
                if is_image:
                    success_embed.set_image(url=f"attachment://{filename}")
                else:
                    success_embed.add_field(name="📥 Download", value=f"[Click to download video]({download_url})", inline=False)
        except Exception as dl_err:
            print(f"Download error: {dl_err}")
            if download_url:
                success_embed.add_field(name="📥 Download", value=f"[Click to download]({download_url})", inline=False)

    if media_file:
        await status_msg.edit(embed=success_embed, attachments=[media_file])
    else:
        await status_msg.edit(embed=success_embed)

    await interaction.followup.send(
        f"{interaction.user.mention} Media ready! Took **{format_duration(total_time)}**.",
        ephemeral=True
    )

# ─── Utility Commands ──────────────────────────────────────────────────────────
@tree.command(name="ping", description="Check if bot is alive")
async def ping_cmd(interaction: discord.Interaction):
    if ban_manager.is_banned(interaction.user.id)[0]:
        await interaction.response.send_message("🔒 You are banned.", ephemeral=True)
        return
    
    status, status_desc = bot_status.get_status()
    embed = discord.Embed(title="🏓 Pong!", description=f"Latency: `{round(client.latency * 1000)}ms`", color=SUCCESS_COLOR)
    
    if status == BotStatus.BUGGY:
        embed.color = BUGGY_COLOR
        embed.title = "⚠️ [BUGGY MODE] " + embed.title
        embed.description += f"\n\n⚠️ **NOTE:** {status_desc if status_desc else 'Bot is in buggy mode'}"
    elif status == BotStatus.BROKEN:
        embed.color = BROKEN_COLOR
        embed.title = "🔴 [BROKEN MODE] " + embed.title
        embed.description = f"⚠️ **NOTE:** {status_desc if status_desc else 'Bot is currently broken'}\n\nLatency: `{round(client.latency * 1000)}ms`"
    
    await interaction.response.send_message(embed=embed)

@tree.command(name="sizes", description="View all available media sizes")
async def sizes_cmd(interaction: discord.Interaction):
    if ban_manager.is_banned(interaction.user.id)[0]:
        await interaction.response.send_message("🔒 You are banned.", ephemeral=True)
        return
    
    embed = discord.Embed(title="📏 Available Sizes", color=INFO_COLOR)
    embed.add_field(name="🌅 Landscape (16:9)", value="`1280x720`", inline=False)
    embed.add_field(name="📱 Portrait (9:16)", value="`720x1280`", inline=False)
    embed.add_field(name="⬛ Square (1:1)", value="`1080x1080`", inline=False)
    embed.add_field(name="🤖 AI Decided", value="Let the AI choose the best size", inline=False)
    await interaction.response.send_message(embed=embed)

@tree.command(name="models", description="View all available AI models")
async def models_cmd(interaction: discord.Interaction):
    if ban_manager.is_banned(interaction.user.id)[0]:
        await interaction.response.send_message("🔒 You are banned.", ephemeral=True)
        return
    
    embed = discord.Embed(title="🧠 Available Models", color=INFO_COLOR)
    embed.add_field(name="🖼️ Image Models", 
                    value="`Nano Banana Pro` — Fast AI image generation\n`Nano Banana 2` — Up to 9 reference images", 
                    inline=False)
    embed.add_field(name="🎬 Video Models", 
                    value="`Sora 2` — OpenAI Sora v2\n`Veo 3.1` — Google Veo 3.1\n`Veo 3.1 Fast` — Faster version\n`Seedance 2` — Seedance v2\n`Wan 2.6` — With reference images\n\n**✨ ALL VIDEOS GENERATE IN PARALLEL!**", 
                    inline=False)
    await interaction.response.send_message(embed=embed)

# ─── Moderation Commands (Owner Only) ────────────────────────────────────────
status_choices = [
    app_commands.Choice(name="Normal", value="normal"),
    app_commands.Choice(name="Buggy", value="buggy"),
    app_commands.Choice(name="Broken", value="broken")
]

@tree.command(name="status", description="Set bot status (Owner only)")
@app_commands.describe(mode="Bot operation mode", description="Description/reason for the status change")
@app_commands.choices(mode=status_choices)
async def status_cmd(interaction: discord.Interaction, mode: app_commands.Choice[str], description: str = ""):
    if not is_owner(interaction):
        await interaction.response.send_message("❌ Only the bot owner can use this command.", ephemeral=True)
        return
    
    bot_status.set_status(mode.value, description)
    
    color = SUCCESS_COLOR
    if mode.value == BotStatus.BUGGY:
        color = BUGGY_COLOR
    elif mode.value == BotStatus.BROKEN:
        color = BROKEN_COLOR
    
    embed = discord.Embed(title="✅ Bot Status Updated", color=color, timestamp=discord.utils.utcnow())
    embed.add_field(name="Mode", value=f"`{mode.value.upper()}`", inline=True)
    if description:
        embed.add_field(name="Description", value=description, inline=False)
    
    await interaction.response.send_message(embed=embed)

duration_choices = [app_commands.Choice(name=name, value=value) for value, name in DURATION_NAMES.items()]

@tree.command(name="ban", description="Ban a user from using the bot (Owner only)")
@app_commands.describe(user="The user to ban", duration="Ban duration", reason="Reason for the ban")
@app_commands.choices(duration=duration_choices)
async def ban_cmd(interaction: discord.Interaction, user: discord.User, duration: app_commands.Choice[str], reason: str = ""):
    if not is_owner(interaction):
        await interaction.response.send_message("❌ Only the bot owner can use this command.", ephemeral=True)
        return
    
    if user.id == BOT_OWNER_ID:
        await interaction.response.send_message("❌ You cannot ban the bot owner.", ephemeral=True)
        return
    
    success, msg = ban_manager.ban(user.id, duration.value, reason, str(interaction.user))
    
    if success:
        embed = discord.Embed(title="🔨 User Banned", description=msg, color=ERROR_COLOR, timestamp=discord.utils.utcnow())
        embed.add_field(name="Banned User", value=f"{user.mention} (`{user.id}`)", inline=True)
        embed.add_field(name="Banned By", value=str(interaction.user), inline=True)
        if reason:
            embed.add_field(name="Reason", value=reason, inline=False)
        await interaction.response.send_message(embed=embed)
    else:
        await interaction.response.send_message(f"❌ {msg}", ephemeral=True)

@tree.command(name="unban", description="Unban a user (Owner only)")
@app_commands.describe(user="The user to unban")
async def unban_cmd(interaction: discord.Interaction, user: discord.User):
    if not is_owner(interaction):
        await interaction.response.send_message("❌ Only the bot owner can use this command.", ephemeral=True)
        return
    
    if ban_manager.unban(user.id):
        embed = discord.Embed(title="✅ User Unbanned", description=f"{user.mention} (`{user.id}`) has been unbanned.", color=SUCCESS_COLOR, timestamp=discord.utils.utcnow())
        await interaction.response.send_message(embed=embed)
    else:
        await interaction.response.send_message(f"❌ {user.mention} is not currently banned.", ephemeral=True)

@tree.command(name="banlist", description="Show all banned users (Owner only)")
async def banlist_cmd(interaction: discord.Interaction):
    if not is_owner(interaction):
        await interaction.response.send_message("❌ Only the bot owner can use this command.", ephemeral=True)
        return
    
    ban_manager.clean_expired()
    bans = ban_manager.get_bans()
    
    if not bans:
        embed = discord.Embed(title="📋 Ban List", description="No users are currently banned.", color=INFO_COLOR)
        await interaction.response.send_message(embed=embed, ephemeral=True)
        return
    
    embed = discord.Embed(title="📋 Ban List", description=f"Total banned users: {len(bans)}", color=INFO_COLOR, timestamp=discord.utils.utcnow())
    
    for uid, (expiry, reason, banner) in bans.items():
        try:
            user = await client.fetch_user(uid)
            name = f"{user.name}" + (f" ({user.display_name})" if hasattr(user, 'display_name') else "")
        except:
            name = f"Unknown User ({uid})"
        
        if expiry:
            time_left = expiry - datetime.utcnow()
            hours = time_left.seconds // 3600
            minutes = (time_left.seconds % 3600) // 60
            if time_left.days > 0:
                expiry_text = f"{time_left.days}d {hours}h left"
            elif hours > 0:
                expiry_text = f"{hours}h {minutes}m left"
            else:
                expiry_text = f"{minutes}m left"
            expiry_text += f"\n(until {expiry.strftime('%Y-%m-%d %H:%M UTC')})"
        else:
            expiry_text = "Permanent"
        
        embed.add_field(name=name, value=f"**Expires:** {expiry_text}\n**Reason:** {reason or 'None'}\n**Banned by:** {banner}", inline=False)
    
    await interaction.response.send_message(embed=embed, ephemeral=True)

# ─── Run Bot ─────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    keep_alive()
    TOKEN = os.environ.get("DISCORD_BOT_TOKEN")
    if not TOKEN:
        print("❌ DISCORD_BOT_TOKEN environment variable not set!")
        exit(1)
    print("🚀 Starting Discord Bot on Render...")
    print("📡 Bot will run 24/7!")
    print(f"💾 Data persistence: Enabled (saves to {DATA_DIR})")
    print(f"👑 Owner ID: {BOT_OWNER_ID}")
    print(f"🎬 ALL VIDEOS GENERATE IN PARALLEL with links appearing in the SAME message!")
    client.run(TOKEN)
