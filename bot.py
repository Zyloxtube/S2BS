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
import secrets
import hashlib
from emailnator import Emailnator

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

# ─── LUNO STUDIO NANO BANANA PRO CONFIGURATION (EXACT MATCH TO WORKING CODE) ───
LUNO_SUPABASE_URL = "https://liuvfhbmbtunebdwhiqh.supabase.co"
LUNO_API_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImxpdXZmaGJtYnR1bmViZHdoaXFoIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NzQ2MTY0MTYsImV4cCI6MjA5MDE5MjQxNn0.R8Ybduar3YilzBwbK3V8bgNSUQO66VDQmDgmNNjeVsI"

LUNO_HEADERS = {
    "accept": "*/*",
    "accept-language": "en-US,en;q=0.9",
    "apikey": LUNO_API_KEY,
    "content-type": "application/json;charset=UTF-8",
    "origin": "https://www.lunostudio.ai",
    "referer": "https://www.lunostudio.ai/",
    "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "x-client-info": "supabase-ssr/0.9.0 createBrowserClient",
    "x-supabase-api-version": "2024-01-01"
}

# ─── LUNO STUDIO FUNCTIONS (EXACT MATCH TO WORKING CODE) ───────────────────────
def luno_generate_code_challenge():
    code_verifier = secrets.token_urlsafe(32)
    code_challenge = _base64.urlsafe_b64encode(
        hashlib.sha256(code_verifier.encode()).digest()
    ).decode().replace('=', '')
    return code_challenge, code_verifier

def luno_get_temp_email():
    emailnator = Emailnator()
    email_data = emailnator.generate_email()
    email = email_data["email"][0]
    print(f"[+] Generated Luno email: {email}")
    return emailnator, email

def luno_wait_for_verification_code(emailnator, email, timeout=120):
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

def luno_signup(email, password, code_challenge):
    url = f"{LUNO_SUPABASE_URL}/auth/v1/signup"
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

def luno_verify_email(email, verification_code):
    url = f"{LUNO_SUPABASE_URL}/auth/v1/verify"
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

def luno_create_cookie_value(verify_result):
    """Create the exact cookie value format from the verify result"""
    cookie_data = {
        "access_token": verify_result['access_token'],
        "token_type": verify_result.get('token_type', 'bearer'),
        "expires_in": verify_result.get('expires_in', 3600),
        "expires_at": verify_result.get('expires_at'),
        "refresh_token": verify_result.get('refresh_token'),
        "user": verify_result.get('user')
    }
    
    json_str = _json.dumps(cookie_data)
    base64_encoded = _base64.b64encode(json_str.encode()).decode()
    return f"base64-{base64_encoded}"

def luno_create_project(cookie_value, project_id, timestamp):
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

def luno_generate_image(cookie_value, project_id, prompt, ref_image_urls=None):
    """Generate AI image with the cookie"""
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
    
    # Use provided reference images or empty list
    image_input = ref_image_urls if ref_image_urls else []
    
    payload = {
        "prompt": prompt,
        "aspectRatio": "1:1",
        "model": "google/nano-banana-pro",
        "imageInput": image_input,
        "duration": 4,
        "generateAudio": True,
        "resolution": "1K",
        "modelOptions": {
            "grounding": "off"
        }
    }
    
    print(f"\n[*] Generating image with prompt: {prompt[:50]}...")
    response = requests.post(url, headers=headers, json=payload)
    print(f"[*] Generate response: {response.status_code}")
    
    if response.status_code == 200:
        return response.json()
    else:
        print(f"[!] Failed: {response.text}")
        return None

def run_luno_nanobanana_generation(prompt: str, ref_images: list = None) -> dict:
    """Run Luno Studio Nano Banana Pro generation using exact working pattern"""
    
    print("=" * 70)
    print("Luno Studio Auto Signup & Image Generator")
    print("=" * 70)
    
    # Step 1: Generate temporary email
    print("\n[Step 1] Generating temporary email...")
    emailnator, email = luno_get_temp_email()
    
    password = secrets.token_urlsafe(12)
    code_challenge, code_verifier = luno_generate_code_challenge()
    print(f"[+] Password: {password}")
    
    # Step 2: Sign up
    print("\n[Step 2] Creating account...")
    signup_result = luno_signup(email, password, code_challenge)
    
    if not signup_result or 'id' not in signup_result:
        raise Exception("Signup failed")
    
    user_id = signup_result['id']
    print(f"[+] User ID: {user_id}")
    
    # Step 3: Get verification code
    print("\n[Step 3] Getting verification code...")
    try:
        verification_code = luno_wait_for_verification_code(emailnator, email)
    except Exception as e:
        raise Exception(f"Failed to get verification code: {e}")
    
    # Step 4: Verify email
    print("\n[Step 4] Verifying email...")
    verify_result = luno_verify_email(email, verification_code)
    
    if not verify_result or 'access_token' not in verify_result:
        raise Exception("Verification failed")
    
    print(f"[+] Email verified!")
    
    # Create the cookie value from the verify result
    cookie_value = luno_create_cookie_value(verify_result)
    print(f"[+] Cookie created")
    
    # Step 5: Create project
    print("\n[Step 5] Creating project...")
    timestamp = int(time.time() * 1000)
    project_id = f"proj-{timestamp}-{secrets.token_urlsafe(5).replace('-', '')}"
    
    project_result = luno_create_project(cookie_value, project_id, timestamp)
    
    if not project_result:
        raise Exception("Project creation failed")
    
    print(f"[+] Project ID: {project_id}")
    
    # Step 5.5: Process reference images if any
    ref_urls = []
    if ref_images:
        print(f"\n[Step 5.5] Processing {len(ref_images)} reference images...")
        for idx, (image_bytes, filename, ext) in enumerate(ref_images[:5]):
            try:
                print(f"  Processing image {idx+1}: {filename}")
                # Convert image to base64 data URI
                mime_type = f"image/{'jpeg' if ext == 'jpg' else ext}"
                b64_data = _base64.b64encode(image_bytes).decode()
                data_uri = f"data:{mime_type};base64,{b64_data}"
                ref_urls.append(data_uri)
                print(f"  ✓ Image {idx+1} converted")
            except Exception as e:
                print(f"  ✗ Failed to process image {idx+1}: {e}")
    
    # Step 6: Generate image
    print("\n[Step 6] Generating AI image...")
    generation_result = luno_generate_image(cookie_value, project_id, prompt, ref_urls if ref_urls else None)
    
    if generation_result and 'output' in generation_result and generation_result['output']:
        image_url = generation_result['output'][0]
        print("\n" + "=" * 70)
        print("✅ IMAGE GENERATED SUCCESSFULLY!")
        print("=" * 70)
        print(f"\n🔗 {image_url}\n")
        print("=" * 70)
        
        return {
            "url": image_url,
            "download_url": image_url,
            "is_nanobanana_pro_alt": True,
            "email": email,
            "password": password,
        }
    else:
        raise Exception("Image generation failed - no output URL")
