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
import pickle
import atexit

# Custom adapter to ignore SSL verification
class SSLAdapter(HTTPAdapter):
    def init_poolmanager(self, *args, **kwargs):
        kwargs['ssl_version'] = ssl.PROTOCOL_TLSv1_2
        kwargs['cert_reqs'] = ssl.CERT_NONE
        kwargs['assert_hostname'] = False
        return super().init_poolmanager(*args, **kwargs)

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
BROKEN_COLOR = 0x800020  # Burgundy color for broken mode
BUGGY_COLOR = 0x9932CC   # Purple/Borage color for buggy mode

BROWSER_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Referer": "https://oreateai.com/",
    "Accept": "image/avif,image/webp,image/apng,image/svg+xml,image/*,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}

intents = discord.Intents.default()
intents.message_content = True
client = discord.Client(intents=intents)
tree = app_commands.CommandTree(client)

# Create a session that ignores SSL verification for image downloads
download_session = requests.Session()
download_session.mount('https://', SSLAdapter())
download_session.verify = False

# ─── Persistent Storage System ────────────────────────────────────────────────
DATA_DIR = "/tmp/bot_data"  # Render's writable temp directory
BANS_FILE = os.path.join(DATA_DIR, "bans.pkl")
STATUS_FILE = os.path.join(DATA_DIR, "status.pkl")

# Create data directory if it doesn't exist
os.makedirs(DATA_DIR, exist_ok=True)

def save_bans(bans_dict):
    """Save bans to file"""
    try:
        # Convert datetime objects to strings for JSON serialization
        serializable_bans = {}
        for user_id, (expiry, reason, banned_by) in bans_dict.items():
            if expiry:
                serializable_bans[user_id] = (expiry.isoformat(), reason, banned_by)
            else:
                serializable_bans[user_id] = (None, reason, banned_by)
        
        with open(BANS_FILE, 'w') as f:
            _json.dump(serializable_bans, f)
        return True
    except Exception as e:
        print(f"Error saving bans: {e}")
        return False

def load_bans():
    """Load bans from file"""
    try:
        if os.path.exists(BANS_FILE):
            with open(BANS_FILE, 'r') as f:
                serializable_bans = _json.load(f)
            
            # Convert back to datetime objects
            bans = {}
            for user_id, (expiry_str, reason, banned_by) in serializable_bans.items():
                user_id = int(user_id)
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
    """Save bot status to file"""
    try:
        with open(STATUS_FILE, 'w') as f:
            _json.dump(status_data, f)
        return True
    except Exception as e:
        print(f"Error saving status: {e}")
        return False

def load_status():
    """Load bot status from file"""
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
        """Load status from file"""
        data = load_status()
        self.status = data.get("status", self.NORMAL)
        self.description = data.get("description", "")
    
    def save(self):
        """Save status to file"""
        save_status({"status": self.status, "description": self.description})
    
    def set_status(self, status: str, description: str = ""):
        self.status = status
        self.description = description
        self.save()
    
    def get_status(self):
        return self.status, self.description
    
    def can_generate(self):
        return self.status != self.BROKEN

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
        # Auto-save on exit
        atexit.register(self.save)
    
    def load(self):
        """Load bans from file"""
        self.bans = load_bans()
        self.clean_expired()
        self.save()  # Save after cleaning
    
    def save(self):
        """Save bans to file"""
        save_bans(self.bans)
    
    def ban(self, user_id: int, duration_key: str, reason: str, banned_by: str) -> Tuple[bool, str]:
        if duration_key not in DURATIONS:
            return False, "Invalid duration"
        
        if duration_key == "perm":
            expiry = None
        else:
            expiry = datetime.utcnow() + DURATIONS[duration_key]
        
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
            if remaining.days > 0:
                time_left = f"{remaining.days}d {hours}h"
            elif hours > 0:
                time_left = f"{hours}h {minutes}m"
            else:
                time_left = f"{minutes}m"
            return True, f"Banned until {expiry.strftime('%Y-%m-%d %H:%M UTC')} ({time_left} left)\nReason: {reason}"
        else:
            return True, f"Permanently banned\nReason: {reason}"
    
    def get_bans(self) -> Dict:
        return self.bans.copy()
    
    def clean_expired(self):
        to_remove = []
        for user_id, (expiry, _, _) in self.bans.items():
            if expiry and datetime.utcnow() > expiry:
                to_remove.append(user_id)
        for user_id in to_remove:
            del self.bans[user_id]
        if to_remove:
            self.save()

ban_manager = BanManager()

def is_owner(interaction: discord.Interaction) -> bool:
    try:
        return interaction.user.id == interaction.client.application.owner_id
    except:
        return False

def check_banned(interaction: discord.Interaction) -> bool:
    banned, message = ban_manager.is_banned(interaction.user.id)
    if banned:
        return True
    return False

# ─── إعداد خادم الويب (لـ Render) ─────────────────────────────────────────────
app = Flask(__name__)

@app.route('/')
def home():
    return "🤖 Bot is alive and running 24/7!"

@app.route('/ping')
def ping():
    return "pong"

@app.route('/stats')
def stats():
    """View bot statistics"""
    bans = ban_manager.get_bans()
    status, desc = bot_status.get_status()
    return {
        "status": status,
        "description": desc,
        "total_bans": len(bans),
        "uptime": "online"
    }

def run_web():
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 8080)))

def keep_alive():
    t = Thread(target=run_web)
    t.daemon = True
    t.start()

# ─── Temp email ──────────────────────────────────────────────────────────────

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
            r = requests.get(
                f"{GUERRILLA_API}?f=check_email&sid_token={self.sid_token}&seq={self.seq}",
                timeout=15,
            )
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
            r = requests.get(
                f"{GUERRILLA_API}?f=fetch_email&email_id={mail_id}&sid_token={self.sid_token}",
                timeout=15,
            )
            d = r.json()
            body = re.sub(r"<[^>]+>", "", d.get("mail_body", "") or "")
            return (
                self._extract_code(d.get("mail_subject", ""))
                or self._extract_code(body)
            )
        except Exception:
            return None

    @staticmethod
    def _extract_code(text):
        if not text:
            return None
        m = re.search(r"(\d{6})", text)
        if m:
            return m.group(1)
        m = re.search(r"(\d{5})", text)
        if m:
            return m.group(1)
        m = re.search(r"(\d{4})", text)
        return m.group(1) if m else None

    def wait_for_code(self, timeout=120, interval=3):
        deadline = time.time() + timeout
        while time.time() < deadline:
            code = self.check_inbox()
            if code:
                return code
            time.sleep(interval)
        return None

# ─── Cognito auth ─────────────────────────────────────────────────────────────

def sign_up_with_cognito(email):
    try:
        cognito = Cognito(
            user_pool_id=USER_POOL_ID,
            client_id=COGNITO_CLIENT_ID,
            username=email,
            user_pool_region="eu-west-1",
        )
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
        cognito = Cognito(
            user_pool_id=USER_POOL_ID,
            client_id=COGNITO_CLIENT_ID,
            username=email,
            user_pool_region="eu-west-1",
        )
        cognito.confirm_sign_up(confirmation_code=code)
        return True
    except Exception as e:
        raise RuntimeError(f"Confirmation failed: {str(e)}")

def sign_in_with_cognito(email):
    try:
        cognito = Cognito(
            user_pool_id=USER_POOL_ID,
            client_id=COGNITO_CLIENT_ID,
            username=email,
            user_pool_region="eu-west-1",
        )
        cognito.authenticate(password=PASSWORD)
        id_token = cognito.id_token
        if not id_token:
            raise RuntimeError("Failed to get ID token after authentication")
        return id_token
    except Exception as e:
        error_msg = str(e)
        if "NEW_PASSWORD_REQUIRED" in error_msg:
            try:
                cognito = Cognito(
                    user_pool_id=USER_POOL_ID,
                    client_id=COGNITO_CLIENT_ID,
                    username=email,
                    user_pool_region="eu-west-1",
                )
                cognito.authenticate(password=PASSWORD)
                if hasattr(cognito, "new_password_required") and cognito.new_password_required:
                    cognito.set_new_password_challenge(PASSWORD)
                    cognito.authenticate(password=PASSWORD)
                return cognito.id_token
            except Exception as inner_e:
                raise RuntimeError(f"Failed to handle password change: {str(inner_e)}")
        raise RuntimeError(f"Authentication failed: {error_msg}")

# ─── Synthesia workspace ───────────────────────────────────────────────────────

def create_workspace(id_token):
    headers = {
        "Authorization": id_token,
        "Content-Type": "application/json",
    }
    res = requests.get("https://api.synthesia.io/workspaces?scope=public", headers=headers)
    res.raise_for_status()
    data = res.json()
    if data.get("results") and len(data["results"]) > 0:
        workspace_id = data["results"][0]["id"]
    else:
        res = requests.post(
            "https://api.synthesia.io/workspaces",
            headers=headers,
            json={"strict": True, "includeDemoVideos": False},
        )
        res.raise_for_status()
        workspace_id = res.json()["workspace"]["id"]

    try:
        requests.post(
            "https://api.synthesia.io/user/onboarding/setPreferredWorkspaceId",
            headers=headers,
            json={"workspaceId": workspace_id},
        )
    except Exception:
        pass

    try:
        requests.post(
            "https://api.synthesia.io/user/onboarding/initialize",
            headers=headers,
            json={
                "featureFlags": {"freemiumEnabled": True},
                "queryParams": {"paymentPlanType": "free"},
                "allowReinitialize": False,
            },
        )
    except Exception:
        pass

    for _ in range(5):
        try:
            res = requests.post(
                "https://api.synthesia.io/user/onboarding/completeCurrentStep",
                headers=headers,
                json={"featureFlags": {"freemiumEnabled": True}},
            )
            if res.status_code != 200:
                break
        except Exception:
            break

    try:
        requests.post(
            "https://api.synthesia.io/user/questionnaire",
            headers=headers,
            json={
                "company": {"size": "emerging", "industry": "professional_services"},
                "seniority": "individual_contributor",
                "persona": "marketing",
            },
        )
    except Exception:
        pass

    try:
        requests.post(
            "https://api.synthesia.io/user/signupForm",
            headers=headers,
            json={"analyticsCookies": {}},
        )
    except Exception:
        pass

    try:
        requests.post(
            f"https://api.synthesia.io/billing/self-serve/{workspace_id}/paywall",
            headers=headers,
            json={
                "targetPlan": "freemium",
                "redirectUrl": "https://app.synthesia.io/#/?plan_created=true&payment_plan=freemium",
            },
        )
    except Exception:
        pass

    time.sleep(30)
    return workspace_id

# ─── Synthesia media generation ───────────────────────────────────────────────

SIZE_TO_ASPECT_RATIO = {
    "1280x720": "16:9",
    "720x1280": "9:16",
    "1080x1080": "1:1",
}

VIDEO_MODELS = {"fal_veo3", "fal_veo3_fast", "sora_2", "seedance_2", "wan_2_6"}

def start_synthesia_generation(token, workspace_id, prompt, size, model):
    try:
        aspect_ratio = SIZE_TO_ASPECT_RATIO.get(size, "16:9")

        if model == "sora_2":
            model_request = {
                "modelName": "sora_2",
                "generateAudio": True,
                "aspectRatio": aspect_ratio,
            }
            media_type = "video"
        elif model in ("fal_veo3", "fal_veo3_fast"):
            model_request = {
                "modelName": model,
                "aspectRatio": aspect_ratio,
                "generateAudio": True,
            }
            media_type = "video"
        else:
            model_request = {
                "modelName": "nanobanana_pro",
                "aspectRatio": aspect_ratio,
            }
            media_type = "image"

        r = requests.post(
            "https://api.prd.synthesia.io/avatarServices/api/generatedMedia/stockFootage/bulk?numberOfResults=1",
            headers={"Authorization": token, "Content-Type": "application/json"},
            json={
                "mediaType": media_type,
                "modelRequest": model_request,
                "userPrompt": prompt,
                "workspaceId": workspace_id,
            },
            timeout=30,
        )
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
            r = requests.get(
                f"https://api.synthesia.io/assets/{asset_id}",
                headers={"Authorization": token},
                timeout=20,
            )
            r.raise_for_status()
            data = r.json()
            status = data.get("uploadMetadata", {}).get("status", "unknown")
            if status == "ready":
                return data
            if status == "failed":
                raise RuntimeError("Generation failed on Synthesia side.")
            time.sleep(interval)
        except requests.exceptions.RequestException as e:
            print(f"Polling error: {e}, retrying...")
            time.sleep(interval)
    raise TimeoutError("Generation timed out after 10 minutes.")

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

    return {
        "url": result.get("url", ""),
        "download_url": result.get("downloadUrl", ""),
    }

# ─── OreateAI image generation (Nano Banana 2) with correct upload method ───

_OREATE_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"

def _oreate_generate_email() -> str:
    chars = string.ascii_lowercase + string.digits
    return "".join(random.choices(chars, k=14)) + "@gmail.com"

def _oreate_generate_password() -> str:
    return "Aa" + "".join(random.choices("0123456789abcdef", k=8)) + "1!"

def _oreate_encrypt_password(plain_text: str, public_key_pem: str) -> str:
    clean_pem = public_key_pem.strip()
    if "BEGIN RSA PUBLIC KEY" in clean_pem:
        b64 = (
            clean_pem
            .replace("-----BEGIN RSA PUBLIC KEY-----", "")
            .replace("-----END RSA PUBLIC KEY-----", "")
            .replace("\n", "").replace("\r", "").strip()
        )
        key = RSA.import_key(_base64.b64decode(b64))
    else:
        key = RSA.import_key(clean_pem)

    cipher = PKCS1_v1_5.new(key)
    return _base64.b64encode(cipher.encrypt(plain_text.encode())).decode()

def _oreate_upload_image_to_gcs(image_bytes: bytes, filename: str, ext: str, session_cookies: dict) -> dict:
    """Upload image to GCS using the correct method from oreate_upload.ts"""
    clean_name = re.sub(r"\.[^.]+$", "", filename)
    
    # Step 1: Get upload token from OreateAI
    token_res = requests.post(
        f"{OREATE_BASE}/oreate/convert/getuploadbostoken",
        headers={
            "Content-Type": "application/json",
            "Origin": OREATE_BASE,
            "Referer": f"{OREATE_BASE}/home/chat/aiImage",
            "Cookie": "; ".join([f"{k}={v}" for k, v in session_cookies.items()]),
            "User-Agent": _OREATE_UA,
        },
        json={
            "mFileList": [{"filename": clean_name, "fileExt": ext, "size": len(image_bytes)}],
            "source": "aiImage",
        },
        timeout=30,
    )
    token_res.raise_for_status()
    token_json = token_res.json()
    
    if token_json.get("status", {}).get("code") != 0:
        raise RuntimeError(f"Upload token failed: {token_json.get('status', {}).get('msg')}")
    
    # Get key data
    key_list = token_json.get("data", {}).get("KeyList", {})
    key_data = key_list.get(f"{clean_name}.{ext}")
    if not key_data and key_list:
        # Try to get first available key
        key_data = list(key_list.values())[0]
    if not key_data:
        raise RuntimeError(f"No upload token key received. Available: {list(key_list.keys())}")
    
    bucket = key_data["bucket"]
    object_path = key_data["objectPath"]
    session_key = key_data["sessionkey"]
    content_type = f"image/{'jpeg' if ext == 'jpg' else ext}"
    
    # Step 2: Initialize GCS resumable upload
    gcs_init_url = (
        f"https://storage.googleapis.com/upload/storage/v1/b/{bucket}/o"
        f"?uploadType=resumable&name={requests.utils.quote(object_path, safe='')}"
    )
    
    init_res = requests.post(
        gcs_init_url,
        headers={
            "Authorization": f"Bearer {session_key}",
            "Content-Type": "application/json",
            "X-Upload-Content-Type": content_type,
            "X-Upload-Content-Length": str(len(image_bytes)),
            "Origin": OREATE_BASE,
            "Referer": f"{OREATE_BASE}/",
        },
        timeout=30,
    )
    if not (200 <= init_res.status_code < 400):
        raise RuntimeError(f"GCS init failed: {init_res.status_code}")
    
    upload_url = init_res.headers.get("location") or init_res.headers.get("Location")
    if not upload_url:
        raise RuntimeError("GCS did not return upload URL")
    
    # Step 3: Upload binary data to GCS
    put_res = requests.put(
        upload_url,
        headers={
            "Content-Type": content_type,
            "Origin": OREATE_BASE,
            "Referer": f"{OREATE_BASE}/",
        },
        data=image_bytes,
        timeout=120,
    )
    if not put_res.ok:
        raise RuntimeError(f"GCS upload failed: {put_res.status_code}")
    
    # Return attachment object for generation request
    return {
        "bos_url": object_path,
        "doc_title": clean_name,
        "doc_type": ext,
        "size": len(image_bytes),
        "bosUrl": object_path,
        "flag": "upload",
        "type": "file",
        "status": 1,
    }

def _oreate_extract_image_url_from_stream(response_text: str) -> str:
    """Extract image URL from SSE stream response"""
    if not response_text:
        return None
    
    # Look for imgUrl or url in data events
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
            except (_json.JSONDecodeError, KeyError):
                pass
    
    # Fallback: find URL in text
    m = re.search(r"(https?://[^\s\"'<>]+\.(jpg|jpeg|png|gif|webp|bmp)(\?[^\s\"'<>]*)?)", response_text, re.IGNORECASE)
    if m:
        return m.group(1)
    return None

def run_oreate_generation(prompt: str, size: str, ref_images: list) -> dict:
    """Generate image using Nano Banana 2 with correct upload method"""
    
    # Step 1: Get ticket and public key
    ticket_res = requests.get(
        f"{OREATE_BASE}/passport/api/getticket",
        headers={
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "en-US,en;q=0.9",
            "Client-Type": "pc",
            "Locale": "en-US",
            "Referer": f"{OREATE_BASE}/home/vertical/aiImage",
            "User-Agent": _OREATE_UA,
        },
        timeout=30,
    )
    ticket_res.raise_for_status()
    ticket_data = ticket_res.json()
    
    ticket_id = ticket_data["data"]["ticketID"]
    public_key = ticket_data["data"]["pk"]
    
    # Extract cookies from ticket response
    cookies = ticket_res.cookies.get_dict()
    
    # Step 2: Generate account credentials
    email = _oreate_generate_email()
    password = _oreate_generate_password()
    encrypted_password = _oreate_encrypt_password(password, public_key)
    
    # Step 3: Create account
    signup_res = requests.post(
        f"{OREATE_BASE}/passport/api/emailsignupin",
        headers={
            "Accept": "application/json, text/plain, */*",
            "Content-Type": "application/json",
            "Cookie": "; ".join([f"{k}={v}" for k, v in cookies.items()]),
            "Locale": "en-US",
            "Origin": OREATE_BASE,
            "Referer": f"{OREATE_BASE}/home/vertical/aiImage",
            "User-Agent": _OREATE_UA,
        },
        json={
            "fr": "GGSEMIMAGE",
            "email": email,
            "ticketID": ticket_id,
            "password": encrypted_password,
            "jt": "",
        },
        timeout=30,
    )
    signup_res.raise_for_status()
    signup_data = signup_res.json()
    
    if signup_data.get("status", {}).get("code") != 0:
        raise RuntimeError(f"OreateAI signup failed: {signup_data.get('status', {}).get('msg')}")
    
    # Update cookies with session cookies
    session_cookies = signup_res.cookies.get_dict()
    session_cookies.update(cookies)
    
    # Extract OUID if present
    ouid = session_cookies.get('OUID', '')
    
    # Step 4: Upload reference images
    attachments = []
    for idx, (image_bytes, filename, file_ext) in enumerate(ref_images[:9]):
        try:
            att = _oreate_upload_image_to_gcs(image_bytes, filename, file_ext, session_cookies)
            attachments.append(att)
            print(f"Uploaded reference image {idx+1}: {att['bos_url']}")
        except Exception as e:
            print(f"Ref {idx+1} upload FAILED: {e}")
    
    # Step 5: Create chat session
    chat_res = requests.post(
        f"{OREATE_BASE}/oreate/create/chat",
        headers={
            "Accept": "application/json, text/plain, */*",
            "Content-Type": "application/json",
            "Locale": "en-US",
            "Origin": OREATE_BASE,
            "Referer": f"{OREATE_BASE}/home/chat/aiImage",
            "User-Agent": _OREATE_UA,
            "Cookie": "; ".join([f"{k}={v}" for k, v in session_cookies.items()]),
        },
        json={"type": "aiImage", "docId": ""},
        timeout=30,
    )
    chat_res.raise_for_status()
    chat_data = chat_res.json()
    chat_id = chat_data.get("data", {}).get("chatId")
    if not chat_id:
        raise RuntimeError(f"OreateAI: no chatId in response")
    
    # Step 6: Generate image via SSE stream
    jt_token = "31$eyJrIj4iOCI0Iix5IkciQEdIRExETEtPSEpOUiJJIkFqIjwiNTw9OUE5QT08Pz5CQSI+IjYzIlEiSlFSTlZOVTk5ODY1OiIzIit5IkYiQD9AIj4iOCJQIklHS09KUExQIi0ibSI/Il1Yem52dVYxXTV2M0t2R1grXGZBQDNqTjx6bk5vVDxyclRyY18pPC8tdGpGRkNhWHloM2l0NGNlZDNCd2dIdl1vKXRZQ0VeRWY2L0lcN3pOKTpEUkAtNFA8S0xnRFg1XjY9eTBcWFVxX2dEeHhNbUFqTWNMZU9mV1VRVnFIeXhRYHNyTlQzVUVnSDFsRWxbWlxuaEo7OzlpcExQSXNqVzY8cj49PVAqcmEwQV1JblxgPjVjbFFSLEE2TGV0cGdmR1gzTz8tWXZkUlpKZSlEWUE6WltrajpDQGVQMzZyM3A5bHNdYzxSY29USUlrWmNlb2MwTl5KLk5zVUR4NURnPjc6W3o1TFk/djFyR2o1V3hceilvNy9nUms0c2NRZjQ5djcwOipgL09YWXVFdEtnNDMtNylvT3Zzblc0dnBQV0d4T088Xm5xVFJIaTdcS2BrbkpQW11wLmlfb1VyUTMzbk42XixTQXFiU3k/LF9EW2BgeGwyYTMtbmYzOTVtR290LjxBMC09cWdCW1FJVHhkLT03ODpCZC8xQ2dWTDc1SyxOMi4seEA7UlQxKUlPfCk1X2BjO3MubVBScWJbODh4VWl1L0oscHRdclJXQV90Zmg1WWBJL2tVLjtcfDIyfGZnOmg9QUFDQ3BEQXN3SERNdkd5TXpPU1MuUFUzYzQ5In0="
    
    request_body = {
        "jt": jt_token,
        "ua": _OREATE_UA,
        "js_env": "h5",
        "extra": {
            "email": email,
            "vip": "0",
            "reg_ts": int(time.time()),
            "deviceID": "EB78F52161CDCA4F55EF242566DAC05E:FG=1",
            "bid": "19caf744b12438441a8a1c",
            "doc_name": "",
            "module_name": "gpt4o",
        },
        "clientType": "wap",
        "type": "chat",
        "chatType": "aiImage",
        "chatTitle": "Unnamed Session",
        "focusId": chat_id,
        "chatId": chat_id,
        "from": "home",
        "messages": [{
            "role": "user",
            "content": prompt,
            "attachments": attachments,
        }],
        "isFirst": True,
    }
    
    sse_res = requests.post(
        f"{OREATE_BASE}/oreate/sse/stream",
        headers={
            "Accept": "text/event-stream",
            "Content-Type": "application/json",
            "Locale": "en-US",
            "Origin": OREATE_BASE,
            "Referer": f"{OREATE_BASE}/home/chat/aiImage",
            "User-Agent": _OREATE_UA,
            "Cookie": "; ".join([f"{k}={v}" for k, v in session_cookies.items()]),
        },
        json=request_body,
        stream=True,
        timeout=180,
    )
    sse_res.raise_for_status()
    
    # Parse SSE stream
    image_url = None
    full_response = ""
    
    for chunk in sse_res.iter_content(chunk_size=None, decode_unicode=True):
        if not chunk:
            continue
        full_response += chunk
        
        # Try to extract image URL from each chunk
        extracted = _oreate_extract_image_url_from_stream(chunk)
        if extracted:
            image_url = extracted
            break
        
        # Parse JSON from data lines
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
                except (_json.JSONDecodeError, KeyError):
                    pass
        
        if image_url:
            break
    
    # Final fallback extraction
    if not image_url:
        image_url = _oreate_extract_image_url_from_stream(full_response)
    
    if not image_url:
        raise RuntimeError("OreateAI: no image URL found in response")
    
    return {
        "url": image_url,
        "download_url": image_url,
        "is_nanobanana2": True,
    }

# ─── Wan 2.6 Video Generation with Reference Images ─────────────────────────────

def _oreate_generate_video_password() -> str:
    """Generate password for video account"""
    chars = []
    for _ in range(8):
        chars.append(random.choice("0123456789abcdef"))
    return "Aa" + "".join(chars) + "1"

def _oreate_upload_video_reference_image(image_bytes: bytes, filename: str, ext: str, session_cookies: dict) -> dict:
    """Upload reference image for video generation"""
    clean_name = re.sub(r"\.[^.]+$", "", filename)
    
    # Step 1: Get upload token from OreateAI
    token_res = requests.post(
        f"{OREATE_BASE}/oreate/convert/getuploadbostoken",
        headers={
            "Content-Type": "application/json",
            "Origin": OREATE_BASE,
            "Referer": f"{OREATE_BASE}/home/chat/aiVideo",
            "Cookie": "; ".join([f"{k}={v}" for k, v in session_cookies.items()]),
            "User-Agent": _OREATE_UA,
        },
        json={
            "mFileList": [{"filename": clean_name, "fileExt": ext, "size": len(image_bytes)}],
            "source": "aiVideo",
        },
        timeout=30,
    )
    token_res.raise_for_status()
    token_json = token_res.json()
    
    if token_json.get("status", {}).get("code") != 0:
        raise RuntimeError(f"Upload token failed: {token_json.get('status', {}).get('msg')}")
    
    # Get key data
    key_list = token_json.get("data", {}).get("KeyList", {})
    key_data = key_list.get(f"{clean_name}.{ext}")
    if not key_data and key_list:
        key_data = list(key_list.values())[0]
    if not key_data:
        raise RuntimeError(f"No upload token key received. Available: {list(key_list.keys())}")
    
    bucket = key_data["bucket"]
    object_path = key_data["objectPath"]
    session_key = key_data["sessionkey"]
    content_type = f"image/{'jpeg' if ext == 'jpg' else ext}"
    
    # Step 2: Initialize GCS resumable upload
    gcs_init_url = (
        f"https://storage.googleapis.com/upload/storage/v1/b/{bucket}/o"
        f"?uploadType=resumable&name={requests.utils.quote(object_path, safe='')}"
    )
    
    init_res = requests.post(
        gcs_init_url,
        headers={
            "Authorization": f"Bearer {session_key}",
            "Content-Type": "application/json",
            "X-Upload-Content-Type": content_type,
            "X-Upload-Content-Length": str(len(image_bytes)),
            "Origin": OREATE_BASE,
            "Referer": f"{OREATE_BASE}/",
        },
        timeout=30,
    )
    if not (200 <= init_res.status_code < 400):
        raise RuntimeError(f"GCS init failed: {init_res.status_code}")
    
    upload_url = init_res.headers.get("location") or init_res.headers.get("Location")
    if not upload_url:
        raise RuntimeError("GCS did not return upload URL")
    
    # Step 3: Upload binary data to GCS
    put_res = requests.put(
        upload_url,
        headers={
            "Content-Type": content_type,
            "Origin": OREATE_BASE,
            "Referer": f"{OREATE_BASE}/",
        },
        data=image_bytes,
        timeout=120,
    )
    if not put_res.ok:
        raise RuntimeError(f"GCS upload failed: {put_res.status_code}")
    
    # Return attachment object for generation request
    return {
        "bos_url": object_path,
        "doc_title": clean_name,
        "doc_type": ext,
        "size": len(image_bytes),
        "bosUrl": object_path,
        "flag": "upload",
        "type": "file",
        "status": 1,
    }

def run_wan26_generation(prompt: str, size: str, ref_images: list = None) -> dict:
    """Generate video using Wan 2.6 with reference images support"""
    
    # Step 1: Get ticket and public key (for video)
    ticket_res = requests.get(
        f"{OREATE_BASE}/passport/api/getticket",
        headers={
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "en-US,en;q=0.9",
            "Client-Type": "pc",
            "Locale": "en-US",
            "Referer": f"{OREATE_BASE}/home/vertical/aiVideo",
            "User-Agent": _OREATE_UA,
        },
        timeout=30,
    )
    ticket_res.raise_for_status()
    ticket_data = ticket_res.json()
    
    ticket_id = ticket_data["data"]["ticketID"]
    public_key = ticket_data["data"]["pk"]
    
    # Extract cookies from ticket response
    cookies = ticket_res.cookies.get_dict()
    
    # Step 2: Generate account credentials
    email = _oreate_generate_email()
    password = _oreate_generate_video_password()
    encrypted_password = _oreate_encrypt_password(password, public_key)
    
    # Step 3: Create account (using GGSEMVIDEO for video)
    signup_res = requests.post(
        f"{OREATE_BASE}/passport/api/emailsignupin",
        headers={
            "Accept": "application/json, text/plain, */*",
            "Content-Type": "application/json",
            "Cookie": "; ".join([f"{k}={v}" for k, v in cookies.items()]),
            "Locale": "en-US",
            "Origin": OREATE_BASE,
            "Referer": f"{OREATE_BASE}/home/vertical/aiVideo",
            "User-Agent": _OREATE_UA,
        },
        json={
            "fr": "GGSEMVIDEO",
            "email": email,
            "ticketID": ticket_id,
            "password": encrypted_password,
            "jt": "",
        },
        timeout=30,
    )
    signup_res.raise_for_status()
    signup_data = signup_res.json()
    
    if signup_data.get("status", {}).get("code") != 0:
        raise RuntimeError(f"Wan 2.6 signup failed: {signup_data.get('status', {}).get('msg')}")
    
    # Update cookies with session cookies
    session_cookies = signup_res.cookies.get_dict()
    session_cookies.update(cookies)
    
    # Step 4: Upload reference images (if any)
    attachments = []
    if ref_images:
        for idx, (image_bytes, filename, file_ext) in enumerate(ref_images[:9]):
            try:
                att = _oreate_upload_video_reference_image(image_bytes, filename, file_ext, session_cookies)
                attachments.append(att)
                print(f"Uploaded reference image {idx+1} for video: {att['bos_url']}")
            except Exception as e:
                print(f"Ref {idx+1} upload FAILED: {e}")
    
    # Step 5: Create video chat session
    chat_res = requests.post(
        f"{OREATE_BASE}/oreate/create/chat",
        headers={
            "Accept": "application/json, text/plain, */*",
            "Content-Type": "application/json",
            "Locale": "en-US",
            "Origin": OREATE_BASE,
            "Referer": f"{OREATE_BASE}/home/chat/aiVideo",
            "User-Agent": _OREATE_UA,
            "Cookie": "; ".join([f"{k}={v}" for k, v in session_cookies.items()]),
        },
        json={"type": "aiVideo", "docId": ""},
        timeout=30,
    )
    chat_res.raise_for_status()
    chat_data = chat_res.json()
    chat_id = chat_data.get("data", {}).get("chatId")
    if not chat_id:
        raise RuntimeError(f"Wan 2.6: no chatId in response")
    
    # Step 6: Generate video via SSE stream
    jt_token = "31$eyJrIj4iOCI0Iix5IkciQEdIRExETEtPSEpOUiJJIkFqIjwiNTw9OUE5QT08Pz5CQSI+IjYzIlEiSlFSTlZOVTk5ODY1OiIzIit5IkYiQD9AIj4iOCJQIklHS09KUExQIi0ibSI/Il1Yem52dVYxXTV2M0t2R1grXGZBQDNqTjx6bk5vVDxyclRyY18pPC8tdGpGRkNhWHloM2l0NGNlZDNCd2dIdl1vKXRZQ0VeRWY2L0lcN3pOKTpEUkAtNFA8S0xnRFg1XjY9eTBcWFVxX2dEeHhNbUFqTWNMZU9mV1VRVnFIeXhRYHNyTlQzVUVnSDFsRWxbWlxuaEo7OzlpcExQSXNqVzY8cj49PVAqcmEwQV1JblxgPjVjbFFSLEE2TGV0cGdmR1gzTz8tWXZkUlpKZSlEWUE6WltrajpDQGVQMzZyM3A5bHNdYzxSY29USUlrWmNlb2MwTl5KLk5zVUR4NURnPjc6W3o1TFk/djFyR2o1V3hceilvNy9nUms0c2NRZjQ5djcwOipgL09YWXVFdEtnNDMtNylvT3Zzblc0dnBQV0d4T088Xm5xVFJIaTdcS2BrbkpQW11wLmlfb1VyUTMzbk42XixTQXFiU3k/LF9EW2BgeGwyYTMtbmYzOTVtR290LjxBMC09cWdCW1FJVHhkLT03ODpCZC8xQ2dWTDc1SyxOMi4seEA7UlQxKUlPfCk1X2BjO3MubVBScWJbODh4VWl1L0oscHRdclJXQV90Zmg1WWBJL2tVLjtcfDIyfGZnOmg9QUFDQ3BEQXN3SERNdkd5TXpPU1MuUFUzYzQ5In0="
    
    request_body = {
        "jt": jt_token,
        "ua": _OREATE_UA,
        "js_env": "h5",
        "extra": {
            "email": email,
            "vip": "0",
            "reg_ts": int(time.time()),
            "deviceID": "EB78F52161CDCA4F55EF242566DAC05E:FG=1",
            "bid": "19caf744b12438441a8a1c",
            "doc_name": "",
            "module_name": "gpt4o",
        },
        "clientType": "pc",
        "type": "chat",
        "chatType": "aiVideo",
        "chatTitle": "Unnamed Session",
        "focusId": chat_id,
        "chatId": chat_id,
        "from": "home",
        "messages": [{
            "role": "user",
            "content": prompt,
            "attachments": attachments,
        }],
        "isFirst": True,
    }
    
    sse_res = requests.post(
        f"{OREATE_BASE}/oreate/sse/stream",
        headers={
            "Accept": "text/event-stream",
            "Content-Type": "application/json",
            "Locale": "en-US",
            "Origin": OREATE_BASE,
            "Referer": f"{OREATE_BASE}/home/chat/aiVideo",
            "User-Agent": _OREATE_UA,
            "Cookie": "; ".join([f"{k}={v}" for k, v in session_cookies.items()]),
        },
        json=request_body,
        stream=True,
        timeout=180,
    )
    sse_res.raise_for_status()
    
    # Parse SSE stream for video URL
    video_url = None
    full_response = ""
    
    for chunk in sse_res.iter_content(chunk_size=None, decode_unicode=True):
        if not chunk:
            continue
        full_response += chunk
        
        # Look for video URLs in the stream
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
                except (_json.JSONDecodeError, KeyError):
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
    
    return {
        "url": video_url,
        "download_url": video_url,
    }

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
    m = re.search(r'(\d{6})', text)
    if m:
        return m.group(1)
    m = re.search(r'(\d{5})', text)
    if m:
        return m.group(1)
    m = re.search(r'(?:verification\s+code|verification|code|otp)[^\d]{0,20}?(\d{4})', text, re.IGNORECASE)
    if m:
        return m.group(1)
    m = re.search(r'(\d{4})', text)
    return m.group(1) if m else None

def _buzzy_generate_temp_email():
    response = requests.get(f"{GUERRILLA_API}?f=get_email_address")
    data = response.json()
    if 'email_addr' not in data:
        raise Exception(f"Failed to generate temp email")
    sid_token = data['sid_token']
    local_part = data['email_addr'].split('@')[0]
    email = f"{local_part}@sharklasers.com"
    return email, sid_token

def _buzzy_generate_random_password():
    upper = random.choice(string.ascii_uppercase)
    lower = ''.join(random.choices(string.ascii_lowercase, k=3))
    nums = str(random.randint(1000, 9999))
    return upper + lower + nums

def _buzzy_send_verification_code(email):
    response = requests.post(
        'https://api.buzzy.now/api/v1/user/send-email-code',
        json={'email': email, 'type': 1},
        headers={'Content-Type': 'application/json'}
    )
    data = response.json()
    if data.get('code') != 200:
        raise Exception(f"Failed to send verification code")
    return True

def _buzzy_wait_for_code(sid_token, max_attempts=30, interval=4):
    current_seq = 0
    seen_ids = set()
    for attempt in range(max_attempts):
        response = requests.get(
            f"{GUERRILLA_API}?f=check_email&sid_token={sid_token}&seq={current_seq}"
        )
        data = response.json()
        if 'seq' in data:
            current_seq = data['seq']

        for mail in data.get('list', []):
            mail_id = mail.get('mail_id')
            if mail_id in seen_ids:
                continue
            seen_ids.add(mail_id)

            code = (
                _extract_code_from_text(mail.get('mail_subject', '')) or
                _extract_code_from_text(mail.get('mail_from', ''))
            )

            if not code:
                try:
                    full = requests.get(
                        f"{GUERRILLA_API}?f=fetch_email&email_id={mail_id}&sid_token={sid_token}"
                    ).json()
                    body = full.get('mail_body', '') or full.get('mail_excerpt', '')
                    code = (
                        _extract_code_from_text(_strip_html(body)) or
                        _extract_code_from_text(body)
                    )
                except Exception:
                    pass

            if code:
                return code

        time.sleep(interval)
    return None

def _buzzy_register_user(email, password, email_code):
    response = requests.post(
        'https://api.buzzy.now/api/v1/user/register',
        json={'email': email, 'password': password, 'emailCode': email_code},
        headers={'Content-Type': 'application/json'}
    )
    data = response.json()
    if data.get('code') == 200:
        return data['data']['token']
    raise Exception(f"Registration failed")

def _buzzy_create_video_project(token, prompt):
    response = requests.post(
        'https://api.buzzy.now/api/app/v1/project/create',
        json={
            'name': 'Untitled',
            'workflowType': 'SOTA',
            'instructionSegments': [{'type': 'text', 'content': prompt}],
            'imageUrls': [],
            'duration': 10,
            'aspectRatio': '16:9',
            'prompt': prompt
        },
        headers={
            'Content-Type': 'application/json',
            'Authorization': f'Bearer {token}'
        }
    )
    data = response.json()
    if data.get('code') == 201:
        return data['data']['id']
    raise Exception(f"Failed to create video project")

def _buzzy_poll_for_video(token, project_id, interval=5):
    while True:
        response = requests.get(
            'https://api.buzzy.now/api/app/v1/project/list?pageNumber=1&pageSize=100',
            headers={
                'Authorization': f'Bearer {token}',
                'accept': 'application/json, text/plain, */*',
                'accept-language': 'en-US,en;q=0.9',
                'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
            }
        )
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
                if results and len(results) > 0:
                    video_url = results[0].get('videoUrl')
                    if video_url:
                        return video_url

                video_urls = target.get('videoUrls', [])
                if video_urls and len(video_urls) > 0:
                    video_url = video_urls[0]
                    if video_url:
                        return video_url

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

    return {
        "url": video_url,
        "download_url": video_url,
    }

# ─── Dispatch ─────────────────────────────────────────────────────────────────

def run_generation(prompt: str, size: str, model: str, ref_images: list = None) -> dict:
    if model == "nanobanana_2":
        return run_oreate_generation(prompt, size, ref_images or [])
    if model == "seedance_2":
        return run_seedance2_generation(prompt)
    if model == "wan_2_6":
        return run_wan26_generation(prompt, size, ref_images or [])
    return run_synthesia_generation(prompt, size, model)

# ─── Multi-generation Handler ──────────────────────────────────────────────────

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
        self.results = []
        self.failed = []
        self.completed = 0
        self.status_message = None
        self.start_time = None
    
    async def run(self):
        self.start_time = time.time()
        
        # Initial progress embed
        embed = self._build_pending_embed()
        self.status_message = await self.interaction.original_response()
        await self.status_message.edit(embed=embed)
        
        # Generate each item
        for i in range(self.amount):
            try:
                loop = asyncio.get_event_loop()
                result = await loop.run_in_executor(
                    None, run_generation, self.prompt, self.size_value, self.model_value, self.ref_images
                )
                self.results.append(result)
                self.completed += 1
            except Exception as exc:
                self.failed.append(str(exc))
                self.completed += 1
            
            # Update progress embed after each completion
            embed = self._build_pending_embed()
            await self.status_message.edit(embed=embed)
        
        # Final result
        total_time = time.time() - self.start_time
        
        if self.completed == 0:
            # All failed
            error_embed = self._build_error_embed("All generations failed")
            await self.status_message.edit(embed=error_embed)
            await self.interaction.followup.send(
                f"{self.interaction.user.mention} ❌ All {self.amount} generations failed!",
                ephemeral=True
            )
        else:
            # Success with some results
            success_embed = self._build_success_embed(total_time)
            await self.status_message.edit(embed=success_embed)
            await self.interaction.followup.send(
                f"{self.interaction.user.mention} ✅ Completed **{len(self.results)}/{self.amount}** generations! Took **{self._format_duration(total_time)}**.",
                ephemeral=True
            )
            
            # Send individual results as separate messages
            for idx, result in enumerate(self.results, 1):
                download_url = result.get("download_url") or result.get("url")
                if download_url:
                    await self.interaction.followup.send(
                        f"🎬 **Generation #{idx}**\n📥 Download: {download_url}",
                        ephemeral=True
                    )
    
    def _build_pending_embed(self):
        # Check bot status
        status, status_desc = bot_status.get_status()
        
        color = PROGRESS_COLOR
        title = "🎨 Batch Generation in Progress"
        
        if status == BotStatus.BUGGY:
            color = BUGGY_COLOR
            title = "⚠️ [BUGGY MODE] " + title
        
        embed = discord.Embed(
            title=title,
            color=color,
        )
        
        if status == BotStatus.BUGGY and status_desc:
            embed.description = f"**⚠️ NOTE:** {status_desc}"
        
        embed.add_field(name="📝 Prompt", value=f"```{self.prompt[:200]}```", inline=False)
        embed.add_field(name="📏 Size", value=f"`{self.size_label}`", inline=True)
        embed.add_field(name="🧠 Model", value=f"`{self.model_label}`", inline=True)
        embed.add_field(name="📊 Progress", value=f"**{self.completed}/{self.amount} completed**", inline=True)
        
        # Add completed links
        if self.results:
            links_text = ""
            for idx, result in enumerate(self.results, 1):
                url = result.get("download_url") or result.get("url")
                if url:
                    links_text += f"✅ #{idx}: [Link]({url})\n"
                else:
                    links_text += f"❌ #{idx}: Failed\n"
                if len(links_text) > 900:
                    links_text = links_text[:897] + "..."
                    break
            if links_text:
                embed.add_field(name="✅ Completed", value=links_text, inline=False)
        
        # Add pending count
        pending = self.amount - self.completed
        if pending > 0:
            embed.add_field(name="⏳ Pending", value=f"{pending} generation(s) remaining...", inline=False)
        
        elapsed = time.time() - self.start_time if self.start_time else 0
        embed.add_field(name="⏱️ Elapsed", value=f"`{self._format_duration(elapsed)}`", inline=True)
        
        footer = f"Powered by {self.model_label}  |  Generating {self.amount} item(s)"
        if status == BotStatus.BUGGY and status_desc:
            footer = f"⚠️ NOTE: {status_desc[:100]} | {footer}"
        
        embed.set_footer(text=footer)
        
        return embed
    
    def _build_success_embed(self, duration):
        status, status_desc = bot_status.get_status()
        
        color = SUCCESS_COLOR
        title = "✅ Batch Generation Complete!"
        
        if status == BotStatus.BUGGY:
            color = BUGGY_COLOR
            title = "⚠️ [BUGGY MODE] " + title
        
        embed = discord.Embed(
            title=title,
            color=color,
            timestamp=discord.utils.utcnow(),
        )
        
        if status == BotStatus.BUGGY and status_desc:
            embed.description = f"**⚠️ NOTE:** {status_desc}"
        
        embed.add_field(name="📝 Prompt", value=f"```{self.prompt[:200]}```", inline=False)
        embed.add_field(name="📏 Size", value=f"`{self.size_label}`", inline=True)
        embed.add_field(name="🧠 Model", value=f"`{self.model_label}`", inline=True)
        embed.add_field(name="📊 Results", value=f"**{len(self.results)}/{self.amount} successful**", inline=True)
        embed.add_field(name="⏱️ Total Time", value=f"`{self._format_duration(duration)}`", inline=True)
        
        # Add all links
        links_text = ""
        for idx, result in enumerate(self.results, 1):
            url = result.get("download_url") or result.get("url")
            if url:
                links_text += f"✅ **#{idx}:** [Click to download]({url})\n"
            else:
                links_text += f"❌ **#{idx}:** Failed\n"
        
        if links_text:
            embed.add_field(name="📥 Download Links", value=links_text[:1024], inline=False)
        
        if self.failed:
            embed.add_field(name="⚠️ Failed", value=f"{len(self.failed)} generation(s) failed", inline=True)
        
        footer = f"Powered by {self.model_label}"
        if status == BotStatus.BUGGY and status_desc:
            footer = f"⚠️ NOTE: {status_desc[:100]} | {footer}"
        
        embed.set_footer(text=footer)
        return embed
    
    def _build_error_embed(self, error_msg):
        status, status_desc = bot_status.get_status()
        
        color = ERROR_COLOR
        title = "❌ Batch Generation Failed"
        
        if status == BotStatus.BUGGY:
            color = BUGGY_COLOR
            title = "⚠️ [BUGGY MODE] " + title
        
        embed = discord.Embed(
            title=title,
            color=color,
            timestamp=discord.utils.utcnow(),
        )
        
        if status == BotStatus.BUGGY and status_desc:
            embed.description = f"**⚠️ NOTE:** {status_desc}"
        
        embed.add_field(name="📝 Prompt", value=f"```{self.prompt[:200]}```", inline=False)
        embed.add_field(name="📏 Size", value=f"`{self.size_label}`", inline=True)
        embed.add_field(name="🧠 Model", value=f"`{self.model_label}`", inline=True)
        embed.add_field(name="⚠️ Error", value=f"```{error_msg[:500]}```", inline=False)
        
        footer = "Please try again later"
        if status == BotStatus.BUGGY and status_desc:
            footer = f"⚠️ NOTE: {status_desc[:100]} | {footer}"
        
        embed.set_footer(text=footer)
        return embed
    
    @staticmethod
    def _format_duration(seconds):
        minutes, secs = divmod(int(seconds), 60)
        if minutes > 0:
            return f"{minutes}m {secs}s"
        return f"{secs}s"

# ─── Helpers ──────────────────────────────────────────────────────────────────

def format_duration(seconds):
    minutes, secs = divmod(int(seconds), 60)
    if minutes > 0:
        return f"{minutes}m {secs}s"
    return f"{secs}s"

PROGRESS_STAGES = [
    {"threshold": 0,   "label": "Initializing",         "emoji": "⚙️"},
    {"threshold": 5,   "label": "Creating account",     "emoji": "📧"},
    {"threshold": 15,  "label": "Verifying email",      "emoji": "✉️"},
    {"threshold": 30,  "label": "Setting up workspace", "emoji": "🛠️"},
    {"threshold": 65,  "label": "Generating media",     "emoji": "🎨"},
    {"threshold": 120, "label": "Rendering",            "emoji": "🎬"},
    {"threshold": 300, "label": "Finalizing",           "emoji": "✨"},
]

NB2_PROGRESS_STAGES = [
    {"threshold": 0,  "label": "Initializing",     "emoji": "⚙️"},
    {"threshold": 3,  "label": "Creating account", "emoji": "📧"},
    {"threshold": 10, "label": "Generating image", "emoji": "🎨"},
    {"threshold": 60, "label": "Finalizing",       "emoji": "✨"},
]

WAN26_PROGRESS_STAGES = [
    {"threshold": 0,   "label": "Initializing",       "emoji": "⚙️"},
    {"threshold": 5,   "label": "Creating account",   "emoji": "📧"},
    {"threshold": 10,  "label": "Uploading images",   "emoji": "📤"},
    {"threshold": 20,  "label": "Generating video",   "emoji": "🎨"},
    {"threshold": 90,  "label": "Rendering",          "emoji": "🎬"},
    {"threshold": 105, "label": "Finalizing",         "emoji": "✨"},
]

SEEDANCE2_PROGRESS_STAGES = [
    {"threshold": 0,   "label": "Initializing",       "emoji": "⚙️"},
    {"threshold": 5,   "label": "Creating account",   "emoji": "📧"},
    {"threshold": 15,  "label": "Verifying email",    "emoji": "✉️"},
    {"threshold": 30,  "label": "Registering user",   "emoji": "📝"},
    {"threshold": 60,  "label": "Generating video",   "emoji": "🎨"},
    {"threshold": 300, "label": "Rendering",          "emoji": "🎬"},
    {"threshold": 600, "label": "Finalizing",         "emoji": "✨"},
]

def get_stage(elapsed, stages):
    current = stages[0]
    for stage in stages:
        if elapsed >= stage["threshold"]:
            current = stage
    return current

def build_progress_embed(prompt, size_label, elapsed, model_label, model_value="", ref_count=0):
    # Check bot status for modifications
    status, status_desc = bot_status.get_status()
    
    if status == BotStatus.BROKEN:
        embed = discord.Embed(
            title="🔴 Bot is Currently Broken",
            description=f"**⚠️ NOTE:** {status_desc if status_desc else 'The bot is currently experiencing issues and cannot generate media.'}",
            color=BROKEN_COLOR,
        )
        embed.add_field(name="📝 Prompt", value=f"```{prompt[:200]}```", inline=False)
        embed.add_field(name="🧠 Model", value=f"`{model_label}`", inline=True)
        embed.set_footer(text="Please try again later when the bot is fixed.")
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

    bar_length = 20
    progress = min(elapsed / estimated_total, 0.95)
    filled = int(bar_length * progress)
    bar = "█" * filled + "░" * (bar_length - filled)

    # Apply status modifications
    color = PROGRESS_COLOR
    title = "🎨  Generating Your Media"
    footer = f"Powered by {model_label}  |  Please wait..."
    
    if status == BotStatus.BUGGY:
        color = BUGGY_COLOR
        title = "⚠️ [BUGGY MODE] " + title
        footer = "⚠️ NOTE: Bot is in buggy mode - " + (status_desc if status_desc else "Some features may not work correctly") + " | " + footer

    embed = discord.Embed(
        title=title,
        color=color,
    )
    
    if status == BotStatus.BUGGY and status_desc:
        embed.description = f"**⚠️ NOTE:** {status_desc}"
    
    embed.add_field(name="📝 Prompt", value=f"```{prompt[:200]}```", inline=False)
    if size_label:
        embed.add_field(name="📏 Size", value=f"`{size_label}`", inline=True)
    embed.add_field(name="🧠 Model", value=f"`{model_label}`", inline=True)
    if ref_count > 0:
        embed.add_field(name="🖼️ Reference Images", value=f"`{ref_count} image(s)`", inline=True)
    embed.add_field(name="⏱️ Elapsed", value=f"`{format_duration(elapsed)}`", inline=True)
    embed.add_field(name=f"{stage['emoji']} Status", value=f"**{stage['label']}**", inline=True)
    embed.add_field(name="Progress", value=f"`{bar}` {int(progress * 100)}%", inline=False)
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
    
    embed = discord.Embed(
        title=title,
        color=color,
        timestamp=discord.utils.utcnow(),
    )
    
    if status == BotStatus.BUGGY and status_desc:
        embed.description = f"**⚠️ NOTE:** {status_desc}"
    
    embed.add_field(name="📝 Prompt", value=f"```{prompt[:200]}```", inline=False)
    if size_label:
        embed.add_field(name="📏 Size", value=f"`{size_label}`", inline=True)
    embed.add_field(name="🧠 Model", value=f"`{model_label}`", inline=True)
    embed.add_field(name="⏱️ Time Taken", value=f"`{format_duration(duration)}`", inline=True)
    
    # Add reference images section if any
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
    
    embed = discord.Embed(
        title=title,
        color=color,
        timestamp=discord.utils.utcnow(),
    )
    
    if status == BotStatus.BUGGY and status_desc:
        embed.description = f"**⚠️ NOTE:** {status_desc}"
    
    embed.add_field(name="📝 Prompt", value=f"```{prompt[:200]}```", inline=False)
    if size_label:
        embed.add_field(name="📏 Size", value=f"`{size_label}`", inline=True)
    embed.add_field(name="🧠 Model", value=f"`{model_label}`", inline=True)
    
    # Add reference images section if any
    if ref_images and len(ref_images) > 0:
        ref_text = ""
        for idx, (_, filename, _) in enumerate(ref_images[:9], 1):
            ref_text += f"📷 **Ref {idx}:** `{filename}`\n"
        embed.add_field(name=f"🖼️ Reference Images ({len(ref_images)})", value=ref_text, inline=False)
    
    embed.add_field(name="⚠️ Error", value=f"```{str(error_msg)[:500]}```", inline=False)
    embed.set_footer(text=footer)
    return embed

# ─── Discord commands ─────────────────────────────────────────────────────────

SIZE_LABELS = {
    "1080x1080": "1:1",
    "720x1280":  "9:16",
    "1280x720":  "16:9",
    "ai_decide": "AI decided",
}

size_choices = [
    app_commands.Choice(name="16:9",       value="1280x720"),
    app_commands.Choice(name="9:16",       value="720x1280"),
    app_commands.Choice(name="AI decided", value="ai_decide"),
]

NBP_AI_SIZES = ["1080x1080", "1280x720", "720x1280"]

model_choices = [
    app_commands.Choice(name="Nano Banana Pro", value="nanobanana_pro"),
    app_commands.Choice(name="Nano Banana 2",   value="nanobanana_2"),
    app_commands.Choice(name="Sora 2",          value="sora_2"),
    app_commands.Choice(name="Veo 3.1",         value="fal_veo3"),
    app_commands.Choice(name="Veo 3.1 Fast",    value="fal_veo3_fast"),
    app_commands.Choice(name="Seedance 2",      value="seedance_2"),
    app_commands.Choice(name="Wan 2.6",         value="wan_2_6"),
]

amount_choices = [
    app_commands.Choice(name="1", value=1),
    app_commands.Choice(name="2", value=2),
    app_commands.Choice(name="3", value=3),
    app_commands.Choice(name="4", value=4),
    app_commands.Choice(name="5", value=5),
    app_commands.Choice(name="6", value=6),
    app_commands.Choice(name="7", value=7),
    app_commands.Choice(name="8", value=8),
    app_commands.Choice(name="9", value=9),
    app_commands.Choice(name="10", value=10),
]

MODEL_LABELS = {
    "nanobanana_pro": "Nano Banana Pro",
    "nanobanana_2":   "Nano Banana 2",
    "sora_2":         "Sora 2",
    "fal_veo3":       "Veo 3.1",
    "fal_veo3_fast":  "Veo 3.1 Fast",
    "seedance_2":     "Seedance 2",
    "wan_2_6":        "Wan 2.6",
}

@client.event
async def on_ready():
    await tree.sync()
    print(f"✅ Bot is online! Logged in as: {client.user}")
    print(f"🚀 Commands available in: Servers and DMs")
    print(f"🌐 Web server running on port {int(os.environ.get('PORT', 8080))}")
    print(f"📁 Data directory: {DATA_DIR}")
    print(f"📊 Current status: {bot_status.status}")
    print(f"🔨 Total bans: {len(ban_manager.get_bans())}")

@discord.app_commands.allowed_installs(guilds=True, users=True)
@discord.app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
@tree.command(name="generate", description="Generate AI media")
@app_commands.describe(
    prompt="What the media should show",
    model="AI model to use (default: Nano Banana Pro)",
    size="Video resolution",
    amount="Number of videos to generate (1-10)",
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
    # Check if user is banned
    banned, ban_msg = ban_manager.is_banned(interaction.user.id)
    if banned:
        embed = discord.Embed(
            title="🔒 You are Banned",
            description=ban_msg,
            color=ERROR_COLOR,
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)
        return
    
    # Check bot status
    status, status_desc = bot_status.get_status()
    if status == BotStatus.BROKEN:
        embed = discord.Embed(
            title="🔴 Bot is Currently Broken",
            description=f"**⚠️ NOTE:** {status_desc if status_desc else 'The bot is currently experiencing issues and cannot generate media.'}\n\nPlease try again later when the bot is fixed.",
            color=BROKEN_COLOR,
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)
        return
    
    amount_value = amount.value if amount else 1
    
    model_value = model.value if model else "nanobanana_pro"
    model_label = MODEL_LABELS.get(model_value, model_value)

    raw_size = size.value if size else None

    if model_value == "nanobanana_2":
        size_value = raw_size or "ai_decide"
        size_label = "AI decided"
    elif model_value == "seedance_2":
        size_value = "1280x720"
        size_label = "16:9"
    elif model_value == "wan_2_6":
        size_value = "1280x720"
        size_label = "16:9"
    elif raw_size == "ai_decide" or raw_size is None:
        if model_value in VIDEO_MODELS:
            size_value = random.choice(["1280x720", "720x1280"])
        else:
            size_value = random.choice(NBP_AI_SIZES)
        size_label = "AI decided"
    else:
        size_value = raw_size
        size_label = SIZE_LABELS.get(size_value, size_value)

    actual_prompt = prompt

    ref_images = []
    # Allow reference images for Nano Banana 2 AND Wan 2.6
    if model_value in ["nanobanana_2", "wan_2_6"]:
        raw_refs = [ref1, ref2, ref3, ref4, ref5, ref6, ref7, ref8, ref9]
        bad_refs = []
        for attachment in raw_refs:
            if attachment is None:
                continue
            fname = attachment.filename
            ext = fname.rsplit(".", 1)[-1].lower() if "." in fname else ""
            if not ext or f".{ext}" not in VALID_IMAGE_EXTENSIONS:
                bad_refs.append(fname)
            else:
                ref_images.append((attachment, fname, ext))

        if bad_refs:
            await interaction.response.send_message(
                f"⚠️ Invalid images: `{'`, `'.join(bad_refs)}`",
                ephemeral=True,
            )
            return

        downloaded = []
        for attachment_obj, fname, ext in ref_images:
            try:
                img_bytes = await attachment_obj.read()
                downloaded.append((img_bytes, fname, ext))
            except Exception as e:
                print(f"Failed to download {fname}: {e}")
        ref_images = downloaded
    else:
        if any(r is not None for r in [ref1, ref2, ref3, ref4, ref5, ref6, ref7, ref8, ref9]):
            await interaction.response.send_message(
                "⚠️ Reference images only work with **Nano Banana 2** or **Wan 2.6**.",
                ephemeral=True,
            )
            return

    # Handle multiple generations
    if amount_value > 1:
        start_embed = build_progress_embed(prompt, size_label, 0, model_label, model_value, len(ref_images))
        await interaction.response.send_message(embed=start_embed)
        
        handler = MultiGenerationHandler(
            interaction, actual_prompt, model_value, model_label,
            size_value, size_label, amount_value, ref_images
        )
        await handler.run()
        return
    
    # Single generation (original flow)
    start_embed = build_progress_embed(prompt, size_label, 0, model_label, model_value, len(ref_images))
    await interaction.response.send_message(embed=start_embed)
    status_msg = await interaction.original_response()

    start_time = time.time()
    generation_done = asyncio.Event()
    generation_result = {"data": None, "error": None}

    async def run_gen():
        try:
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(
                None, run_generation, actual_prompt, size_value, model_value, ref_images
            )
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
    try:
        await timer_task
    except asyncio.CancelledError:
        pass

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
            # Use the custom session that ignores SSL verification
            response = download_session.get(download_url, timeout=60)
            response.raise_for_status()
            media_bytes = response.content
            
            # Determine if it's an image or video
            is_image = model_value not in VIDEO_MODELS or model_value == "nanobanana_2"
            ext = "png" if is_image else "mp4"
            filename = f"generated_media.{ext}"
            
            # For videos, check file size (Discord has 25MB limit for attachments)
            if not is_image and len(media_bytes) > 25 * 1024 * 1024:
                # Video too large for Discord, just provide download link
                success_embed.add_field(
                    name="📥 Download",
                    value=f"[Click to download video]({download_url})",
                    inline=False,
                )
            else:
                media_file = discord.File(io.BytesIO(media_bytes), filename=filename)
                if is_image:
                    success_embed.set_image(url=f"attachment://{filename}")
                else:
                    success_embed.add_field(
                        name="📥 Download",
                        value=f"[Click to download video]({download_url})",
                        inline=False,
                    )
        except Exception as dl_err:
            print(f"Download error: {dl_err}")
            if download_url:
                success_embed.add_field(
                    name="📥 Download",
                    value=f"[Click to download]({download_url})",
                    inline=False,
                )

    if media_file:
        await status_msg.edit(embed=success_embed, attachments=[media_file])
    else:
        await status_msg.edit(embed=success_embed)

    await interaction.followup.send(
        f"{interaction.user.mention} Media ready! Took **{format_duration(total_time)}**."
    )

@discord.app_commands.allowed_installs(guilds=True, users=True)
@discord.app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
@tree.command(name="ping", description="Check if bot is alive")
async def ping_cmd(interaction: discord.Interaction):
    # Check ban
    banned, _ = ban_manager.is_banned(interaction.user.id)
    if banned:
        await interaction.response.send_message("🔒 You are banned from using this bot.", ephemeral=True)
        return
    
    status, status_desc = bot_status.get_status()
    
    embed = discord.Embed(
        title="🏓 Pong!",
        description=f"Latency: `{round(client.latency * 1000)}ms`\nStatus: ✅ Online",
        color=SUCCESS_COLOR,
    )
    
    if status == BotStatus.BUGGY:
        embed.color = BUGGY_COLOR
        embed.title = "⚠️ [BUGGY MODE] " + embed.title
        embed.description += f"\n\n⚠️ **NOTE:** {status_desc if status_desc else 'Bot is in buggy mode'}"
    elif status == BotStatus.BROKEN:
        embed.color = BROKEN_COLOR
        embed.title = "🔴 [BROKEN MODE] " + embed.title
        embed.description = f"⚠️ **NOTE:** {status_desc if status_desc else 'Bot is currently broken'}\n\nLatency: `{round(client.latency * 1000)}ms`"
    
    await interaction.response.send_message(embed=embed)

# ─── Status Command (Owner Only) ──────────────────────────────────────────────

status_choices = [
    app_commands.Choice(name="Normal", value="normal"),
    app_commands.Choice(name="Buggy", value="buggy"),
    app_commands.Choice(name="Broken", value="broken"),
]

@tree.command(name="status", description="Set bot status (Owner only)")
@app_commands.describe(
    mode="Bot operation mode",
    description="Description/reason for the status change"
)
@app_commands.choices(mode=status_choices)
async def status_cmd(
    interaction: discord.Interaction,
    mode: app_commands.Choice[str],
    description: str = ""
):
    if not is_owner(interaction):
        embed = discord.Embed(
            title="❌ Permission Denied",
            description="Only the bot owner can use this command.",
            color=ERROR_COLOR,
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)
        return
    
    bot_status.set_status(mode.value, description)
    
    color = SUCCESS_COLOR
    if mode.value == BotStatus.BUGGY:
        color = BUGGY_COLOR
    elif mode.value == BotStatus.BROKEN:
        color = BROKEN_COLOR
    
    embed = discord.Embed(
        title="✅ Bot Status Updated",
        color=color,
        timestamp=discord.utils.utcnow(),
    )
    embed.add_field(name="Mode", value=f"`{mode.value.upper()}`", inline=True)
    if description:
        embed.add_field(name="Description", value=description, inline=False)
    
    await interaction.response.send_message(embed=embed)

# ─── Ban Commands (Owner Only) ────────────────────────────────────────────────

duration_choices = [
    app_commands.Choice(name="1 minute", value="1m"),
    app_commands.Choice(name="5 minutes", value="5m"),
    app_commands.Choice(name="10 minutes", value="10m"),
    app_commands.Choice(name="20 minutes", value="20m"),
    app_commands.Choice(name="30 minutes", value="30m"),
    app_commands.Choice(name="1 hour", value="1h"),
    app_commands.Choice(name="2 hours", value="2h"),
    app_commands.Choice(name="3 hours", value="3h"),
    app_commands.Choice(name="6 hours", value="6h"),
    app_commands.Choice(name="12 hours", value="12h"),
    app_commands.Choice(name="1 day", value="1d"),
    app_commands.Choice(name="2 days", value="2d"),
    app_commands.Choice(name="3 days", value="3d"),
    app_commands.Choice(name="4 days", value="4d"),
    app_commands.Choice(name="5 days", value="5d"),
    app_commands.Choice(name="6 days", value="6d"),
    app_commands.Choice(name="1 week", value="1w"),
    app_commands.Choice(name="2 weeks", value="2w"),
    app_commands.Choice(name="3 weeks", value="3w"),
    app_commands.Choice(name="1 month", value="1mo"),
    app_commands.Choice(name="2 months", value="2mo"),
    app_commands.Choice(name="3 months", value="3mo"),
    app_commands.Choice(name="6 months", value="6mo"),
    app_commands.Choice(name="Permanent", value="perm"),
]

@tree.command(name="ban", description="Ban a user from using the bot (Owner only)")
@app_commands.describe(
    user="The user to ban",
    duration="Ban duration",
    reason="Reason for the ban"
)
@app_commands.choices(duration=duration_choices)
async def ban_cmd(
    interaction: discord.Interaction,
    user: discord.User,
    duration: app_commands.Choice[str],
    reason: str = ""
):
    if not is_owner(interaction):
        embed = discord.Embed(
            title="❌ Permission Denied",
            description="Only the bot owner can use this command.",
            color=ERROR_COLOR,
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)
        return
    
    if user.id == interaction.client.application.owner_id:
        embed = discord.Embed(
            title="❌ Cannot Ban Owner",
            description="You cannot ban yourself.",
            color=ERROR_COLOR,
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)
        return
    
    success, message = ban_manager.ban(user.id, duration.value, reason, str(interaction.user))
    
    if success:
        embed = discord.Embed(
            title="🔨 User Banned",
            description=f"✅ {message}",
            color=ERROR_COLOR,
            timestamp=discord.utils.utcnow(),
        )
        embed.add_field(name="Banned User", value=f"{user.mention} (`{user.id}`)", inline=True)
        embed.add_field(name="Banned By", value=str(interaction.user), inline=True)
        if reason:
            embed.add_field(name="Reason", value=reason, inline=False)
        await interaction.response.send_message(embed=embed)
    else:
        embed = discord.Embed(
            title="❌ Ban Failed",
            description=message,
            color=ERROR_COLOR,
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)

@tree.command(name="unban", description="Unban a user (Owner only)")
@app_commands.describe(
    user="The user to unban"
)
async def unban_cmd(
    interaction: discord.Interaction,
    user: discord.User
):
    if not is_owner(interaction):
        embed = discord.Embed(
            title="❌ Permission Denied",
            description="Only the bot owner can use this command.",
            color=ERROR_COLOR,
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)
        return
    
    if ban_manager.unban(user.id):
        embed = discord.Embed(
            title="✅ User Unbanned",
            description=f"{user.mention} (`{user.id}`) has been unbanned and can now use the bot again.",
            color=SUCCESS_COLOR,
            timestamp=discord.utils.utcnow(),
        )
        await interaction.response.send_message(embed=embed)
    else:
        embed = discord.Embed(
            title="❌ User Not Banned",
            description=f"{user.mention} (`{user.id}`) is not currently banned.",
            color=ERROR_COLOR,
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)

@tree.command(name="banlist", description="Show all banned users (Owner only)")
async def banlist_cmd(interaction: discord.Interaction):
    if not is_owner(interaction):
        embed = discord.Embed(
            title="❌ Permission Denied",
            description="Only the bot owner can use this command.",
            color=ERROR_COLOR,
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)
        return
    
    ban_manager.clean_expired()
    bans = ban_manager.get_bans()
    
    if not bans:
        embed = discord.Embed(
            title="📋 Ban List",
            description="No users are currently banned.",
            color=INFO_COLOR,
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)
        return
    
    embed = discord.Embed(
        title="📋 Ban List",
        description=f"Total banned users: {len(bans)}",
        color=INFO_COLOR,
        timestamp=discord.utils.utcnow(),
    )
    
    for user_id, (expiry, reason, banned_by) in bans.items():
        try:
            user = await client.fetch_user(user_id)
            user_name = f"{user.name} ({user.display_name})" if hasattr(user, 'display_name') else user.name
        except:
            user_name = f"Unknown User ({user_id})"
        
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
        
        embed.add_field(
            name=user_name,
            value=f"**Ban Info:**\n┣ Expires: {expiry_text}\n┣ Banned by: {banned_by}\n┗ Reason: {reason if reason else 'No reason provided'}",
            inline=False
        )
    
    await interaction.response.send_message(embed=embed, ephemeral=True)

@discord.app_commands.allowed_installs(guilds=True, users=True)
@discord.app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
@tree.command(name="sizes", description="View all available media sizes")
async def sizes_cmd(interaction: discord.Interaction):
    banned, _ = ban_manager.is_banned(interaction.user.id)
    if banned:
        await interaction.response.send_message("🔒 You are banned from using this bot.", ephemeral=True)
        return
    
    embed = discord.Embed(
        title="📏  Available Sizes",
        description="Use these with `/generate` to pick your resolution.",
        color=INFO_COLOR,
    )
    landscape, portrait, square = [], [], []
    for size in VIDEO_SIZES:
        w, h = map(int, size.split("x"))
        entry = f"`{size}`"
        if w == h:
            square.append(entry)
        elif w > h:
            landscape.append(entry)
        else:
            portrait.append(entry)
    if landscape:
        embed.add_field(name="🌅 Landscape", value="\n".join(landscape), inline=False)
    if portrait:
        embed.add_field(name="📱 Portrait", value="\n".join(portrait), inline=False)
    if square:
        embed.add_field(name="⬛ Square", value="\n".join(square), inline=False)
    await interaction.response.send_message(embed=embed)

@discord.app_commands.allowed_installs(guilds=True, users=True)
@discord.app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
@tree.command(name="models", description="View all available AI models")
async def models_cmd(interaction: discord.Interaction):
    banned, _ = ban_manager.is_banned(interaction.user.id)
    if banned:
        await interaction.response.send_message("🔒 You are banned from using this bot.", ephemeral=True)
        return
    
    embed = discord.Embed(
        title="🧠  Available Models",
        color=INFO_COLOR,
    )
    embed.add_field(
        name="Image models",
        value=(
            "`Nano Banana Pro` — fast AI image generation\n"
            "`Nano Banana 2` — image generation with up to 9 reference images"
        ),
        inline=False,
    )
    embed.add_field(
        name="Video models (with audio)",
        value=(
            "`Sora 2` — OpenAI Sora v2\n"
            "`Veo 3.1` — Google Veo 3.1\n"
            "`Veo 3.1 Fast` — Google Veo 3.1 (faster)\n"
            "`Seedance 2` — Seedance v2\n"
            "`Wan 2.6` — Wan 2.6 video generation with reference images"
        ),
        inline=False,
    )
    await interaction.response.send_message(embed=embed)

# ─── تشغيل البوت ────────────────────────────────────────────────────────────

if __name__ == "__main__":
    # تشغيل خادم الويب أولاً
    keep_alive()
    
    # التحقق من وجود التوكن
    TOKEN = os.environ.get("DISCORD_BOT_TOKEN")
    if not TOKEN:
        print("❌ ERROR: DISCORD_BOT_TOKEN environment variable not set!")
        exit(1)
    
    # تشغيل البوت
    print("🚀 Starting Discord Bot on Render...")
    print("📡 Bot will run 24/7!")
    print(f"💾 Data persistence: Enabled (saves to {DATA_DIR})")
    client.run(TOKEN)
