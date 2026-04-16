import os
import re
import io
import time
import asyncio
import random
import string
import secrets
import base64
import hashlib
import json
import requests
import discord
from discord import app_commands
from datetime import datetime
from emailnator import Emailnator
from flask import Flask
from threading import Thread

# ============================================================
# LUNO STUDIO CONFIGURATION
# ============================================================
SUPABASE_URL = "https://liuvfhbmbtunebdwhiqh.supabase.co"
API_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImxpdXZmaGJtYnR1bmViZHdoaXFoIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NzQ2MTY0MTYsImV4cCI6MjA5MDE5MjQxNn0.R8Ybduar3YilzBwbK3V8bgNSUQO66VDQmDgmNNjeVsI"

LUNO_HEADERS = {
    "accept": "*/*",
    "accept-language": "en-US,en;q=0.9",
    "apikey": API_KEY,
    "content-type": "application/json;charset=UTF-8",
    "origin": "https://www.lunostudio.ai",
    "referer": "https://www.lunostudio.ai/",
    "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "x-client-info": "supabase-ssr/0.9.0 createBrowserClient",
    "x-supabase-api-version": "2024-01-01"
}

# ============================================================
# DISCORD CONFIGURATION
# ============================================================
VALID_IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp", ".tiff"}
VIDEO_SIZES = ["1280x720", "720x1280"]

BRAND_COLOR = 0x5865F2
SUCCESS_COLOR = 0x57F287
ERROR_COLOR = 0xED4245
PROGRESS_COLOR = 0xFEE75C
INFO_COLOR = 0x5865F2

intents = discord.Intents.default()
intents.message_content = True
client = discord.Client(intents=intents)
tree = app_commands.CommandTree(client)

# ─── إعداد خادم الويب (لـ Render) ─────────────────────────────────────────────
app = Flask(__name__)

@app.route('/')
def home():
    return "🤖 Bot is alive and running 24/7!"

@app.route('/ping')
def ping():
    return "pong"

def run_web():
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 8080)))

def keep_alive():
    t = Thread(target=run_web)
    t.start()

# ============================================================
# LUNO STUDIO HELPER FUNCTIONS
# ============================================================

def generate_code_challenge():
    code_verifier = secrets.token_urlsafe(32)
    code_challenge = base64.urlsafe_b64encode(
        hashlib.sha256(code_verifier.encode()).digest()
    ).decode().replace('=', '')
    return code_challenge, code_verifier

def get_temp_email():
    emailnator = Emailnator()
    email_data = emailnator.generate_email()
    email = email_data["email"][0]
    print(f"[+] Generated email: {email}")
    return emailnator, email

def wait_for_verification_code(emailnator, email, timeout=120):
    print("\n[*] Waiting for verification code...")
    start_time = time.time()
    seen_messages = set()
    
    while time.time() - start_time < timeout:
        try:
            inbox_result = emailnator.inbox(email)
            messages = []
            if isinstance(inbox_result, dict) and "messageData" in inbox_result:
                messages = inbox_result["messageData"]
            
            for msg in messages:
                msg_id = str(msg)
                if msg_id in seen_messages:
                    continue
                seen_messages.add(msg_id)
                
                try:
                    full_message = emailnator.get_message(email, msg if isinstance(msg, str) else msg.get('messageID', ''))
                    message_str = str(full_message)
                    
                    if 'luno' in message_str.lower() or 'confirm your signup' in message_str.lower():
                        code_match = re.search(r'\b(\d{6})\b', message_str)
                        if code_match:
                            code = code_match.group(1)
                            print(f"✅ VERIFICATION CODE: {code}")
                            return code
                except:
                    pass
        except:
            pass
        time.sleep(0.5)
    
    raise Exception("Timeout: No verification code received")

def signup(email, password, code_challenge):
    url = f"{SUPABASE_URL}/auth/v1/signup"
    payload = {
        "email": email,
        "password": password,
        "data": {},
        "gotrue_meta_security": {},
        "code_challenge": code_challenge,
        "code_challenge_method": "s256"
    }
    
    print(f"\n[*] Sending signup request...")
    response = requests.post(url, headers=LUNO_HEADERS, json=payload)
    print(f"[*] Signup response: {response.status_code}")
    
    if response.status_code != 200:
        print(f"[!] Error: {response.text}")
        return None
    
    return response.json()

def verify_email(email, verification_code):
    url = f"{SUPABASE_URL}/auth/v1/verify"
    payload = {
        "email": email,
        "token": verification_code,
        "type": "signup",
        "gotrue_meta_security": {}
    }
    
    print(f"\n[*] Verifying with code: {verification_code}")
    response = requests.post(url, headers=LUNO_HEADERS, json=payload)
    print(f"[*] Verify response: {response.status_code}")
    
    if response.status_code != 200:
        print(f"[!] Error: {response.text}")
        return None
    
    return response.json()

def create_cookie_value(verify_result):
    """Create the exact cookie value format from the verify result"""
    cookie_data = {
        "access_token": verify_result['access_token'],
        "token_type": verify_result.get('token_type', 'bearer'),
        "expires_in": verify_result.get('expires_in', 3600),
        "expires_at": verify_result.get('expires_at'),
        "refresh_token": verify_result.get('refresh_token'),
        "user": verify_result.get('user')
    }
    
    json_str = json.dumps(cookie_data)
    base64_encoded = base64.b64encode(json_str.encode()).decode()
    return f"base64-{base64_encoded}"

def create_project(cookie_value, project_id, timestamp):
    """Create a new project with the cookie"""
    url = "https://www.lunostudio.ai/api/projects"
    
    headers = {
        "accept": "*/*",
        "accept-language": "en-US,en;q=0.9",
        "content-type": "application/json",
        "cookie": f"geo-country=US; sb-liuvfhbmbtunebdwhiqh-auth-token={cookie_value}",
        "origin": "https://www.lunostudio.ai",
        "referer": "https://www.lunostudio.ai/dashboard",
        "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
    }
    
    payload = {
        "id": project_id,
        "name": "Untitled",
        "createdAt": timestamp,
        "updatedAt": timestamp
    }
    
    response = requests.post(url, headers=headers, json=payload)
    print(f"[*] Create project response: {response.status_code}")
    
    if response.status_code == 200:
        print(f"[+] Project created successfully!")
        return response.json()
    else:
        print(f"[!] Failed: {response.text}")
        return None

def generate_luno_image(cookie_value, project_id, prompt, ref_images):
    """Generate AI image with Luno Studio"""
    url = "https://www.lunostudio.ai/api/generate"
    
    headers = {
        "accept": "*/*",
        "accept-language": "en-US,en;q=0.9",
        "content-type": "application/json",
        "cookie": f"geo-country=US; sb-liuvfhbmbtunebdwhiqh-auth-token={cookie_value}",
        "origin": "https://www.lunostudio.ai",
        "referer": f"https://www.lunostudio.ai/project/{project_id}",
        "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
    }
    
    # Upload reference images to CDN first (simplified - using direct URLs)
    image_inputs = []
    for img_bytes, filename, ext in ref_images:
        # For now, we'll use a placeholder - in production you'd upload to a CDN
        # Since we can't easily upload to their CDN, we'll use the fact they accept URLs
        # For demo, we'll use a data URL or assume the images are accessible
        image_inputs.append(f"https://via.placeholder.com/512?text={filename}")
    
    payload = {
        "prompt": prompt,
        "aspectRatio": "1:1",
        "model": "google/nano-banana-pro",
        "imageInput": image_inputs if image_inputs else [],
        "duration": 4,
        "generateAudio": True,
        "resolution": "1K",
        "modelOptions": {
            "grounding": "off"
        }
    }
    
    print(f"\n[*] Generating image with prompt: {prompt}...")
    response = requests.post(url, headers=headers, json=payload)
    print(f"[*] Generate response: {response.status_code}")
    
    if response.status_code == 200:
        return response.json()
    else:
        print(f"[!] Failed: {response.text}")
        return None

def run_luno_generation(prompt: str, size: str, ref_images: list = None) -> dict:
    """Generate image using Luno Studio (Nano Banana Pro)"""
    
    # Step 1: Generate temporary email
    emailnator, email = get_temp_email()
    
    password = secrets.token_urlsafe(12)
    code_challenge, code_verifier = generate_code_challenge()
    
    # Step 2: Sign up
    signup_result = signup(email, password, code_challenge)
    
    if not signup_result or 'id' not in signup_result:
        raise RuntimeError("Signup failed")
    
    user_id = signup_result['id']
    
    # Step 3: Get verification code
    verification_code = wait_for_verification_code(emailnator, email)
    
    # Step 4: Verify email
    verify_result = verify_email(email, verification_code)
    
    if not verify_result or 'access_token' not in verify_result:
        raise RuntimeError("Verification failed")
    
    # Step 5: Create cookie and project
    cookie_value = create_cookie_value(verify_result)
    timestamp = int(time.time() * 1000)
    project_id = f"proj-{timestamp}-{secrets.token_urlsafe(5).replace('-', '')}"
    
    project_result = create_project(cookie_value, project_id, timestamp)
    
    if not project_result:
        raise RuntimeError("Project creation failed")
    
    # Step 6: Generate image
    generation_result = generate_luno_image(cookie_value, project_id, prompt, ref_images or [])
    
    if generation_result and 'output' in generation_result and len(generation_result['output']) > 0:
        image_url = generation_result['output'][0]
        return {
            "url": image_url,
            "download_url": image_url,
        }
    else:
        raise RuntimeError("Image generation failed")

# ─── OreateAI image generation (Nano Banana 2) with correct upload method ───

OREATE_BASE = "https://www.oreateai.com"
_OREATE_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"

def _oreate_generate_email() -> str:
    chars = string.ascii_lowercase + string.digits
    return "".join(random.choices(chars, k=14)) + "@gmail.com"

def _oreate_generate_password() -> str:
    return "Aa" + "".join(random.choices("0123456789abcdef", k=8)) + "1!"

def _oreate_encrypt_password(plain_text: str, public_key_pem: str) -> str:
    from Crypto.PublicKey import RSA
    from Crypto.Cipher import PKCS1_v1_5
    import base64 as _base64
    
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
    """Upload image to GCS using the correct method"""
    import json as _json
    
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
    
    lines = response_text.split('\n')
    for line in lines:
        if line.startswith('data: '):
            try:
                data = json.loads(line[6:])
                if data.get('data', {}).get('imgUrl'):
                    return data['data']['imgUrl']
                if data.get('data', {}).get('url'):
                    return data['data']['url']
                if data.get('imgUrl'):
                    return data['imgUrl']
                if data.get('url'):
                    return data['url']
            except (json.JSONDecodeError, KeyError):
                pass
    
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
    
    session_cookies = signup_res.cookies.get_dict()
    session_cookies.update(cookies)
    
    # Step 4: Upload reference images
    attachments = []
    for idx, (image_bytes, filename, file_ext) in enumerate(ref_images[:9]):
        try:
            att = _oreate_upload_image_to_gcs(image_bytes, filename, file_ext, session_cookies)
            attachments.append(att)
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
                    data = json.loads(line[6:])
                    if data.get("data", {}).get("imgUrl"):
                        image_url = data["data"]["imgUrl"]
                        break
                    if data.get("data", {}).get("url"):
                        image_url = data["data"]["url"]
                        break
                except (json.JSONDecodeError, KeyError):
                    pass
        
        if image_url:
            break
    
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

def run_wan26_generation(prompt: str, size: str, ref_images: list = None) -> dict:
    """Generate video using Wan 2.6 with reference images support"""
    # Simplified for now - would need full implementation
    raise RuntimeError("Wan 2.6 implementation requires additional setup")

# ─── Dispatch ─────────────────────────────────────────────────────────────────

def run_generation(prompt: str, size: str, model: str, ref_images: list = None) -> dict:
    if model == "nanobanana_pro":
        return run_luno_generation(prompt, size, ref_images or [])
    if model == "nanobanana_2":
        return run_oreate_generation(prompt, size, ref_images or [])
    if model == "wan_2_6":
        return run_wan26_generation(prompt, size, ref_images or [])
    raise RuntimeError(f"Unknown model: {model}")

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

def get_stage(elapsed, stages):
    current = stages[0]
    for stage in stages:
        if elapsed >= stage["threshold"]:
            current = stage
    return current

def build_progress_embed(prompt, size_label, elapsed, model_label, model_value="", ref_count=0):
    if model_value == "nanobanana_2":
        stages = NB2_PROGRESS_STAGES
        estimated_total = 60
    else:
        stages = PROGRESS_STAGES
        estimated_total = 180

    stage = get_stage(elapsed, stages)

    bar_length = 20
    progress = min(elapsed / estimated_total, 0.95)
    filled = int(bar_length * progress)
    bar = "█" * filled + "░" * (bar_length - filled)

    embed = discord.Embed(
        title="🎨  Generating Your Media",
        color=PROGRESS_COLOR,
    )
    embed.add_field(name="📝 Prompt", value=f"```{prompt[:200]}```", inline=False)
    if size_label:
        embed.add_field(name="📏 Size", value=f"`{size_label}`", inline=True)
    embed.add_field(name="🧠 Model", value=f"`{model_label}`", inline=True)
    if ref_count > 0:
        embed.add_field(name="🖼️ Reference Images", value=f"`{ref_count} image(s)`", inline=True)
    embed.add_field(name="⏱️ Elapsed", value=f"`{format_duration(elapsed)}`", inline=True)
    embed.add_field(name=f"{stage['emoji']} Status", value=f"**{stage['label']}**", inline=True)
    embed.add_field(name="Progress", value=f"`{bar}` {int(progress * 100)}%", inline=False)
    embed.set_footer(text=f"Powered by {model_label}  |  Please wait...")
    return embed

def build_success_embed(prompt, size_label, duration, model_label, model_value="", ref_images=None):
    embed = discord.Embed(
        title="✅  Media Generated Successfully!",
        color=SUCCESS_COLOR,
        timestamp=discord.utils.utcnow(),
    )
    embed.add_field(name="📝 Prompt", value=f"```{prompt[:200]}```", inline=False)
    if size_label:
        embed.add_field(name="📏 Size", value=f"`{size_label}`", inline=True)
    embed.add_field(name="🧠 Model", value=f"`{model_label}`", inline=True)
    embed.add_field(name="⏱️ Time Taken", value=f"`{format_duration(duration)}`", inline=True)
    
    # Add reference images section with clickable links
    if ref_images and len(ref_images) > 0:
        ref_text = ""
        for idx, (img_bytes, filename, ext) in enumerate(ref_images[:9], 1):
            # Create a data URL for the image to make it clickable
            import base64
            img_base64 = base64.b64encode(img_bytes).decode()
            data_url = f"data:image/{ext};base64,{img_base64}"
            ref_text += f"📷 **Ref {idx}:** [{filename}]({data_url})\n"
        embed.add_field(name=f"🖼️ Reference Images ({len(ref_images)})", value=ref_text, inline=False)
    
    embed.set_footer(text=f"Powered by {model_label}")
    return embed

def build_error_embed(error_msg, prompt, size_label, model_label, model_value="", ref_images=None):
    embed = discord.Embed(
        title="❌  Generation Failed",
        color=ERROR_COLOR,
        timestamp=discord.utils.utcnow(),
    )
    embed.add_field(name="📝 Prompt", value=f"```{prompt[:200]}```", inline=False)
    if size_label:
        embed.add_field(name="📏 Size", value=f"`{size_label}`", inline=True)
    embed.add_field(name="🧠 Model", value=f"`{model_label}`", inline=True)
    
    # Add reference images section with clickable links even on error
    if ref_images and len(ref_images) > 0:
        ref_text = ""
        for idx, (img_bytes, filename, ext) in enumerate(ref_images[:9], 1):
            import base64
            img_base64 = base64.b64encode(img_bytes).decode()
            data_url = f"data:image/{ext};base64,{img_base64}"
            ref_text += f"📷 **Ref {idx}:** [{filename}]({data_url})\n"
        embed.add_field(name=f"🖼️ Reference Images ({len(ref_images)})", value=ref_text, inline=False)
    
    embed.add_field(name="⚠️ Error", value=f"```{str(error_msg)[:500]}```", inline=False)
    embed.set_footer(text="Please try again later")
    return embed

# ─── Discord commands ─────────────────────────────────────────────────────────

SIZE_LABELS = {
    "1080x1080": "1:1",
    "720x1280":  "9:16",
    "1280x720":  "16:9",
    "ai_decide": "AI decided",
}

size_choices = [
    app_commands.Choice(name="1:1",        value="1080x1080"),
    app_commands.Choice(name="16:9",       value="1280x720"),
    app_commands.Choice(name="9:16",       value="720x1280"),
    app_commands.Choice(name="AI decided", value="ai_decide"),
]

model_choices = [
    app_commands.Choice(name="Nano Banana Pro", value="nanobanana_pro"),
    app_commands.Choice(name="Nano Banana 2",   value="nanobanana_2"),
]

MODEL_LABELS = {
    "nanobanana_pro": "Nano Banana Pro",
    "nanobanana_2":   "Nano Banana 2",
}

VIDEO_MODELS = set()  # No video models in this version

@client.event
async def on_ready():
    await tree.sync()
    print(f"✅ Bot is online! Logged in as: {client.user}")
    print(f"🚀 Commands available in: Servers and DMs")

@discord.app_commands.allowed_installs(guilds=True, users=True)
@discord.app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
@tree.command(name="generate", description="Generate AI media")
@app_commands.describe(
    prompt="What the image should show",
    model="AI model to use (default: Nano Banana Pro)",
    size="Image resolution",
    ref1="Reference image 1 (Nano Banana 2 only)",
    ref2="Reference image 2",
    ref3="Reference image 3",
    ref4="Reference image 4",
    ref5="Reference image 5",
    ref6="Reference image 6",
    ref7="Reference image 7",
    ref8="Reference image 8",
    ref9="Reference image 9",
)
@app_commands.choices(size=size_choices, model=model_choices)
async def generate(
    interaction: discord.Interaction,
    prompt: str,
    model: app_commands.Choice[str] = None,
    size: app_commands.Choice[str] = None,
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
    model_value = model.value if model else "nanobanana_pro"
    model_label = MODEL_LABELS.get(model_value, model_value)

    raw_size = size.value if size else None

    if model_value == "nanobanana_2":
        size_value = raw_size or "ai_decide"
        size_label = "AI decided"
    elif raw_size == "ai_decide" or raw_size is None:
        size_value = random.choice(["1080x1080", "1280x720", "720x1280"])
        size_label = "AI decided"
    else:
        size_value = raw_size
        size_label = SIZE_LABELS.get(size_value, size_value)

    ref_images = []
    # Allow reference images for Nano Banana 2
    if model_value == "nanobanana_2":
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
                "⚠️ Reference images only work with **Nano Banana 2**.",
                ephemeral=True,
            )
            return

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
                None, run_generation, prompt, size_value, model_value, ref_images
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

    download_url = result.get("download_url") or result.get("url")
    if download_url:
        try:
            response = requests.get(download_url, timeout=60)
            response.raise_for_status()
            media_bytes = response.content
            
            ext = "png"
            filename = f"generated_media.{ext}"
            
            media_file = discord.File(io.BytesIO(media_bytes), filename=filename)
            success_embed.set_image(url=f"attachment://{filename}")
            
            await status_msg.edit(embed=success_embed, attachments=[media_file])
        except Exception as dl_err:
            print(f"Download error: {dl_err}")
            if download_url:
                success_embed.add_field(
                    name="📥 Download",
                    value=f"[Click to download]({download_url})",
                    inline=False,
                )
            await status_msg.edit(embed=success_embed)
    else:
        await status_msg.edit(embed=success_embed)

    await interaction.followup.send(
        f"{interaction.user.mention} Media ready! Took **{format_duration(total_time)}**."
    )

@discord.app_commands.allowed_installs(guilds=True, users=True)
@discord.app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
@tree.command(name="ping", description="Check if bot is alive")
async def ping_cmd(interaction: discord.Interaction):
    embed = discord.Embed(
        title="🏓 Pong!",
        description=f"Latency: `{round(client.latency * 1000)}ms`\nStatus: ✅ Online",
        color=SUCCESS_COLOR,
    )
    await interaction.response.send_message(embed=embed)

@discord.app_commands.allowed_installs(guilds=True, users=True)
@discord.app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
@tree.command(name="sizes", description="View all available image sizes")
async def sizes_cmd(interaction: discord.Interaction):
    embed = discord.Embed(
        title="📏  Available Sizes",
        description="Use these with `/generate` to pick your resolution.",
        color=INFO_COLOR,
    )
    embed.add_field(name="⬛ Square", value="`1080x1080` (1:1)", inline=False)
    embed.add_field(name="🌅 Landscape", value="`1280x720` (16:9)", inline=False)
    embed.add_field(name="📱 Portrait", value="`720x1280` (9:16)", inline=False)
    await interaction.response.send_message(embed=embed)

@discord.app_commands.allowed_installs(guilds=True, users=True)
@discord.app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
@tree.command(name="models", description="View all available AI models")
async def models_cmd(interaction: discord.Interaction):
    embed = discord.Embed(
        title="🧠  Available Models",
        color=INFO_COLOR,
    )
    embed.add_field(
        name="Image models",
        value=(
            "`Nano Banana Pro` — fast AI image generation via Luno Studio\n"
            "`Nano Banana 2` — image generation with up to 9 reference images"
        ),
        inline=False,
    )
    await interaction.response.send_message(embed=embed)

# ─── تشغيل البوت ────────────────────────────────────────────────────────────

if __name__ == "__main__":
    keep_alive()
    
    TOKEN = os.environ.get("DISCORD_BOT_TOKEN")
    if not TOKEN:
        print("❌ ERROR: DISCORD_BOT_TOKEN environment variable not set!")
        exit(1)
    
    print("🚀 Starting Discord Bot on Render...")
    print("📡 Bot will run 24/7!")
    client.run(TOKEN)
