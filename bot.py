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

TOKEN = os.environ["DISCORD_BOT_TOKEN"]
PASSWORD = "Test1234Abc!"
COGNITO_CLIENT_ID = "1kvg8re5bgu9ljqnnkjosu477k"
USER_POOL_ID = "eu-west-1_7hEawdalF"
GUERRILLA_API = "https://api.guerrillamail.com/ajax.php"
OREATE_BASE = "https://www.oreateai.com"

VALID_IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp", ".tiff"}

VIDEO_SIZES = [
    "1280x720",
    "720x1280",
]

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
intents.message_content = True  # Enable message content intent for DMs
client = discord.Client(intents=intents)
tree = app_commands.CommandTree(client)


# ─── Temp email ───────────────────────────────────────────────────────────────

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
                or self._extract_code(d.get("mail_from", ""))
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

VIDEO_MODELS = {"fal_veo3", "fal_veo3_fast", "sora_2"}
ASPECT_RATIO_MODELS = {"fal_veo3", "fal_veo3_fast", "nanobanana_pro"}


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


# ─── OreateAI image generation (Nano Banana 2) ───────────────────────────────

import json as _json
import base64 as _base64

_OREATE_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"


def _oreate_generate_email() -> str:
    chars = string.ascii_lowercase + string.digits
    return "".join(random.choices(chars, k=14)) + "@gmail.com"


def _oreate_generate_password() -> str:
    return "Aa" + "".join(random.choices("0123456789abcdef", k=8)) + "1"


def _oreate_encrypt_password(plain_text: str, public_key_pem: str) -> str:
    from Crypto.PublicKey import RSA
    from Crypto.Cipher import PKCS1_v1_5

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


def _oreate_create_session() -> tuple:
    """Returns (session, email, password, ticket_id) with cookies already set."""
    sess = requests.Session()
    sess.headers.update({
        "User-Agent": _OREATE_UA,
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "en-US,en;q=0.9",
        "Locale": "en-US",
        "Client-Type": "pc",
    })

    ticket_res = sess.get(
        f"{OREATE_BASE}/passport/api/getticket",
        headers={"Referer": f"{OREATE_BASE}/home/vertical/aiImage"},
        timeout=30,
    )
    ticket_res.raise_for_status()
    ticket_data = ticket_res.json()
    print(f"[OreateAI] Ticket response: {ticket_data.get('status')}")

    ticket_id = ticket_data["data"]["ticketID"]
    public_key = ticket_data["data"]["pk"]

    email = _oreate_generate_email()
    password = _oreate_generate_password()
    encrypted_password = _oreate_encrypt_password(password, public_key)
    print(f"[OreateAI] Signing up with email: {email}")

    signup_res = sess.post(
        f"{OREATE_BASE}/passport/api/emailsignupin",
        headers={
            "Content-Type": "application/json",
            "Origin": OREATE_BASE,
            "Referer": f"{OREATE_BASE}/home/vertical/aiImage",
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
    print(f"[OreateAI] Signup response code: {signup_data.get('status', {}).get('code')} msg: {signup_data.get('status', {}).get('msg')}")

    if signup_data.get("status", {}).get("code") != 0:
        raise RuntimeError(f"OreateAI signup failed: {signup_data.get('status', {}).get('msg')}")

    sess.headers.update({
        "Origin": OREATE_BASE,
        "Referer": f"{OREATE_BASE}/home/chat/aiImage",
    })
    return sess, email, password


def _oreate_upload_image(sess: requests.Session, image_bytes: bytes, filename: str, ext: str) -> dict:
    clean_name = re.sub(r"\.[^.]+$", "", filename)

    token_res = sess.post(
        f"{OREATE_BASE}/oreate/convert/getuploadbostoken",
        headers={
            "Content-Type": "application/json",
            "Origin": OREATE_BASE,
            "Referer": f"{OREATE_BASE}/home/chat/aiImage",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
        },
        json={
            "mFileList": [{"filename": clean_name, "fileExt": ext, "size": len(image_bytes)}],
            "source": "aiImage",
        },
        timeout=30,
    )
    token_res.raise_for_status()
    token_json = token_res.json()
    print(f"[OreateAI] Upload token response: {token_json}")

    if token_json.get("status", {}).get("code") != 0:
        raise RuntimeError(f"Upload token failed: {token_json.get('status', {}).get('msg')}")

    key_list = token_json.get("data", {}).get("KeyList", {})
    key_data = key_list.get(f"{clean_name}.{ext}") or (list(key_list.values())[0] if key_list else None)
    if not key_data:
        raise RuntimeError(f"No upload token key received. Available keys: {list(key_list.keys())}")

    bucket = key_data["bucket"]
    object_path = key_data["objectPath"]
    session_key = key_data["sessionkey"]
    content_type = f"image/{'jpeg' if ext == 'jpg' else ext}"

    print(f"[OreateAI] GCS upload — bucket: {bucket}, path: {object_path[:60]}")

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
    if not (init_res.ok or 200 <= init_res.status_code < 400):
        raise RuntimeError(f"GCS init failed: {init_res.status_code} {init_res.text[:200]}")

    upload_url = init_res.headers.get("location") or init_res.headers.get("Location")
    if not upload_url:
        raise RuntimeError("GCS did not return upload URL")

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
        raise RuntimeError(f"GCS upload PUT failed: {put_res.status_code} {put_res.text[:200]}")

    print(f"[OreateAI] GCS upload success — objectPath: {object_path[:60]}")

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


def _oreate_extract_image_url(text: str):
    if not text:
        return None
    m = re.search(r"\((https?://[^)\s]+)\)", text)
    if m:
        return m.group(1)
    m = re.search(r"(https?://[^\s\"'<>]+\.(jpg|jpeg|png|gif|webp|bmp|svg)(\?[^\s\"'<>]*)?)", text, re.IGNORECASE)
    if m:
        return m.group(1)
    m = re.search(r"(https?://[^\s\"'<>]+)", text)
    if m:
        return m.group(1)
    return None


def run_oreate_generation(prompt: str, size: str, ref_images: list) -> dict:
    """ref_images: list of (bytes, filename, ext) tuples, pre-downloaded."""
    # Never append a size string — let the AI match the ref image or decide freely
    final_prompt = prompt

    print(f"[OreateAI] Starting generation — prompt: {final_prompt[:80]}")
    print(f"[OreateAI] Ref images to upload: {len(ref_images)}")
    sess, email, password = _oreate_create_session()

    attachments = []
    for idx, (image_bytes, filename, file_ext) in enumerate(ref_images[:9]):
        try:
            print(f"[OreateAI] Uploading ref {idx+1}: {filename} ({len(image_bytes)} bytes, ext={file_ext})")
            att = _oreate_upload_image(sess, image_bytes, filename, file_ext)
            attachments.append(att)
            print(f"[OreateAI] Ref {idx+1} uploaded OK — bos_url: {att.get('bos_url', '')[:80]}")
        except Exception as e:
            import traceback
            print(f"[OreateAI] Ref {idx+1} upload FAILED: {e}")
            traceback.print_exc()

    print(f"[OreateAI] {len(attachments)}/{len(ref_images)} refs uploaded successfully")

    chat_res = sess.post(
        f"{OREATE_BASE}/oreate/create/chat",
        headers={"Content-Type": "application/json"},
        json={"type": "aiImage", "docId": ""},
        timeout=30,
    )
    chat_res.raise_for_status()
    chat_data = chat_res.json()
    chat_id = chat_data.get("data", {}).get("chatId")
    print(f"[OreateAI] chatId: {chat_id}")
    if not chat_id:
        raise RuntimeError(f"OreateAI: no chatId in response: {chat_data}")

    sse_res = sess.post(
        f"{OREATE_BASE}/oreate/sse/stream",
        headers={"Content-Type": "application/json", "Accept": "text/event-stream"},
        json={
            "clientType": "pc",
            "type": "chat",
            "chatType": "aiImage",
            "chatId": chat_id,
            "focusId": chat_id,
            "from": "home",
            "isFirst": True,
            "messages": [{"role": "user", "content": final_prompt, "attachments": attachments}],
        },
        stream=True,
        timeout=180,
    )
    sse_res.raise_for_status()
    print("[OreateAI] SSE stream started, waiting for image URL...")

    image_url = None
    buf = ""
    full_response = ""

    for chunk in sse_res.iter_content(chunk_size=None, decode_unicode=True):
        if not chunk:
            continue
        buf += chunk
        full_response += chunk
        lines = buf.split("\n")
        buf = lines[-1]

        for line in lines[:-1]:
            if not line.startswith("data:"):
                continue
            json_str = line[5:].strip()
            if not json_str:
                continue

            extracted = _oreate_extract_image_url(json_str)
            if extracted and "." in extracted.split("/")[-1]:
                image_url = extracted
                break

            try:
                data = _json.loads(json_str)
                result_text = data.get("data", {}).get("result", "")
                if result_text:
                    extracted = _oreate_extract_image_url(result_text)
                    if extracted:
                        image_url = extracted
                        break
                for key in ("imageUrl", "url", "image_url"):
                    val = data.get("data", {}).get(key)
                    if val and val.startswith("http"):
                        image_url = val
                        break
                if image_url:
                    break
                if data.get("event") == "error":
                    raise RuntimeError(f"OreateAI server error: {data.get('data', {}).get('msg')}")
            except (_json.JSONDecodeError, KeyError, TypeError):
                pass

        if image_url:
            break

    if not image_url:
        image_url = _oreate_extract_image_url(full_response)

    print(f"[OreateAI] Image URL found: {image_url}")
    if not image_url:
        print(f"[OreateAI] Full response (last 500): {full_response[-500:]}")
        raise RuntimeError("OreateAI: no image URL found in response")

    return {
        "url": image_url,
        "download_url": image_url,
        "is_nanobanana2": True,
    }


# ─── Dispatch ─────────────────────────────────────────────────────────────────

def run_generation(prompt: str, size: str, model: str, ref_images: list = None) -> dict:
    if model == "nanobanana_2":
        return run_oreate_generation(prompt, size, ref_images or [])
    return run_synthesia_generation(prompt, size, model)


# ─── Helpers ──────────────────────────────────────────────────────────────────

def format_duration(seconds):
    minutes, secs = divmod(int(seconds), 60)
    if minutes > 0:
        return f"{minutes}m {secs}s"
    return f"{secs}s"


PROGRESS_STAGES = [
    {"threshold": 0,   "label": "Initializing",        "emoji": "\u2699\ufe0f"},
    {"threshold": 5,   "label": "Creating account",    "emoji": "\ud83d\udce7"},
    {"threshold": 15,  "label": "Verifying email",     "emoji": "\u2709\ufe0f"},
    {"threshold": 30,  "label": "Setting up workspace","emoji": "\ud83d\udee0\ufe0f"},
    {"threshold": 65,  "label": "Generating media",    "emoji": "\ud83c\udfa8"},
    {"threshold": 120, "label": "Rendering",           "emoji": "\ud83c\udfac"},
    {"threshold": 300, "label": "Finalizing",          "emoji": "\u2728"},
]

NB2_PROGRESS_STAGES = [
    {"threshold": 0,  "label": "Initializing",          "emoji": "\u2699\ufe0f"},
    {"threshold": 3,  "label": "Creating account",      "emoji": "\ud83d\udce7"},
    {"threshold": 10, "label": "Generating image",      "emoji": "\ud83c\udfa8"},
    {"threshold": 60, "label": "Finalizing",            "emoji": "\u2728"},
]


def get_stage(elapsed, stages):
    current = stages[0]
    for stage in stages:
        if elapsed >= stage["threshold"]:
            current = stage
    return current


def build_progress_embed(prompt, size_label, elapsed, model_label, model_value=""):
    stages = NB2_PROGRESS_STAGES if model_value == "nanobanana_2" else PROGRESS_STAGES
    stage = get_stage(elapsed, stages)

    bar_length = 20
    estimated_total = 60 if model_value == "nanobanana_2" else 180
    progress = min(elapsed / estimated_total, 0.95)
    filled = int(bar_length * progress)
    bar = "\u2588" * filled + "\u2591" * (bar_length - filled)

    embed = discord.Embed(
        title="\ud83c\udfa8  Generating Your Media",
        color=PROGRESS_COLOR,
    )
    embed.add_field(name="\ud83d\udcdd Prompt", value=f"```{prompt[:200]}```", inline=False)
    if size_label:
        embed.add_field(name="\ud83d\udccf Size", value=f"`{size_label}`", inline=True)
    embed.add_field(name="\ud83e\udde0 Model", value=f"`{model_label}`", inline=True)
    embed.add_field(name="\u23f1\ufe0f Elapsed", value=f"`{format_duration(elapsed)}`", inline=True)
    embed.add_field(name=f"{stage['emoji']} Status", value=f"**{stage['label']}**", inline=True)
    embed.add_field(name="Progress", value=f"`{bar}` {int(progress * 100)}%", inline=False)
    embed.set_footer(text=f"Powered by {model_label}  |  Please wait...")
    return embed


def build_success_embed(prompt, size_label, duration, model_label, model_value=""):
    embed = discord.Embed(
        title="\u2705  Media Generated Successfully!",
        color=SUCCESS_COLOR,
        timestamp=discord.utils.utcnow(),
    )
    embed.add_field(name="\ud83d\udcdd Prompt", value=f"```{prompt[:200]}```", inline=False)
    if size_label:
        embed.add_field(name="\ud83d\udccf Size", value=f"`{size_label}`", inline=True)
    embed.add_field(name="\ud83e\udde0 Model", value=f"`{model_label}`", inline=True)
    embed.add_field(name="\u23f1\ufe0f Time Taken", value=f"`{format_duration(duration)}`", inline=True)
    embed.set_footer(text=f"Powered by {model_label}")
    return embed


def build_error_embed(error_msg, prompt, size_label, model_label, model_value=""):
    embed = discord.Embed(
        title="\u274c  Generation Failed",
        color=ERROR_COLOR,
        timestamp=discord.utils.utcnow(),
    )
    embed.add_field(name="\ud83d\udcdd Prompt", value=f"```{prompt[:200]}```", inline=False)
    if size_label:
        embed.add_field(name="\ud83d\udccf Size", value=f"`{size_label}`", inline=True)
    embed.add_field(name="\ud83e\udde0 Model", value=f"`{model_label}`", inline=True)
    embed.add_field(name="\u26a0\ufe0f Error", value=f"```{str(error_msg)[:500]}```", inline=False)
    embed.set_footer(text="Please try again later")
    return embed


def build_filter_error_embed(prompt, size_label, model_label, model_value=""):
    embed = discord.Embed(
        title="\ud83d\udeab  Request Declined",
        description=(
            "Your request could not be processed. This may be due to content policy "
            "restrictions or a temporary issue with the generation service.\n\n"
            "Please revise your prompt and try again."
        ),
        color=ERROR_COLOR,
        timestamp=discord.utils.utcnow(),
    )
    embed.add_field(name="\ud83d\udcdd Prompt", value=f"```{prompt[:200]}```", inline=False)
    embed.add_field(name="\ud83e\udde0 Model", value=f"`{model_label}`", inline=True)
    if size_label:
        embed.add_field(name="\ud83d\udccf Size", value=f"`{size_label}`", inline=True)
    embed.set_footer(text="Try a different prompt or model")
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

# Random sizes NBP can pick when user selects "AI decided"
import random as _random
NBP_AI_SIZES = ["1080x1080", "1280x720", "720x1280"]

model_choices = [
    app_commands.Choice(name="Nano Banana Pro", value="nanobanana_pro"),
    app_commands.Choice(name="Nano Banana 2",   value="nanobanana_2"),
    app_commands.Choice(name="Sora 2",          value="sora_2"),
    app_commands.Choice(name="Veo 3.1",         value="fal_veo3"),
    app_commands.Choice(name="Veo 3.1 Fast",    value="fal_veo3_fast"),
]

MODEL_LABELS = {
    "nanobanana_pro": "Nano Banana Pro",
    "nanobanana_2":   "Nano Banana 2",
    "sora_2":         "Sora 2",
    "fal_veo3":       "Veo 3.1",
    "fal_veo3_fast":  "Veo 3.1 Fast",
}


@client.event
async def on_ready():
    # Sync commands globally (this makes them work in DMs too)
    await tree.sync()
    print(f"Bot is online! Logged in as: {client.user}")
    print(f"Commands are available in: Servers and DMs")


# Add these decorators to EVERY command to enable DM usage
@discord.app_commands.allowed_installs(guilds=True, users=True)
@discord.app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
@tree.command(name="generate", description="Generate AI media via Synthesia")
@app_commands.describe(
    prompt="What the media should show",
    model="AI model to use (default: Nano Banana Pro)",
    size="Video resolution (not used for Nano Banana 2)",
    ref1="Reference image 1 (Nano Banana 2 only — must end in .png/.jpg/etc)",
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

    # Determine the effective size value and display label
    raw_size = size.value if size else None

    if model_value == "nanobanana_2":
        # NB2 always lets AI decide — size string is never sent to the model
        size_value = raw_size or "ai_decide"
        size_label = "AI decided"
    elif raw_size == "ai_decide" or raw_size is None:
        if model_value in VIDEO_MODELS:
            # Video AI decide: pick random non-1:1 size internally
            size_value = _random.choice(["1280x720", "720x1280"])
        else:
            # NBP AI decide: pick random size including 1:1
            size_value = _random.choice(NBP_AI_SIZES)
        size_label = "AI decided"
    else:
        size_value = raw_size
        size_label = SIZE_LABELS.get(size_value, size_value)

    actual_prompt = prompt

    # Pre-download ref images in async context so URLs don't expire and bytes are ready
    ref_images = []  # list of (bytes, filename, ext)
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
                f"\u26a0\ufe0f These attachments don't appear to be valid images "
                f"(must end in .png, .jpg, .jpeg, .gif, .webp, etc): "
                f"`{'`, `'.join(bad_refs)}`",
                ephemeral=True,
            )
            return

        # Download bytes now, before spawning the thread
        downloaded = []
        for attachment_obj, fname, ext in ref_images:
            try:
                img_bytes = await attachment_obj.read()
                downloaded.append((img_bytes, fname, ext))
                print(f"[OreateAI] Downloaded ref '{fname}': {len(img_bytes)} bytes")
            except Exception as e:
                print(f"[OreateAI] Failed to download ref '{fname}': {e}")
        ref_images = downloaded
    else:
        if any(r is not None for r in [ref1, ref2, ref3, ref4, ref5, ref6, ref7, ref8, ref9]):
            await interaction.response.send_message(
                "\u26a0\ufe0f Reference images are only supported with **Nano Banana 2**.",
                ephemeral=True,
            )
            return

    start_embed = build_progress_embed(prompt, size_label, 0, model_label, model_value)
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
                progress_embed = build_progress_embed(prompt, size_label, elapsed, model_label, model_value)
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
        error_embed = build_filter_error_embed(prompt, size_label, model_label, model_value)
        await status_msg.edit(embed=error_embed)
        await interaction.followup.send(
            f"{interaction.user.mention} Your request could not be completed. Please try a different prompt."
        )
        return

    result = generation_result["data"]
    success_embed = build_success_embed(prompt, size_label, total_time, model_label, model_value)

    media_file = None
    download_url = result.get("download_url") or result.get("url")
    if download_url:
        try:
            is_image = model_value not in VIDEO_MODELS
            print(f"[Download] Fetching media from: {download_url}")

            if result.get("is_nanobanana2"):
                r = requests.get(
                    download_url,
                    headers={
                        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
                        "Accept": "*/*",
                        "Referer": "https://www.oreateai.com/",
                    },
                    timeout=60,
                    verify=False,
                )
                print(f"[Download] Status {r.status_code}, size {len(r.content)} bytes")
                r.raise_for_status()
                media_bytes = r.content
            else:
                media_bytes = requests.get(download_url, timeout=60).content
                print(f"[Download] Got {len(media_bytes)} bytes")

            ext = "jpg" if result.get("is_nanobanana2") else ("png" if is_image else "mp4")
            filename = f"generated_media.{ext}"

            if len(media_bytes) < 25 * 1024 * 1024:
                media_file = discord.File(io.BytesIO(media_bytes), filename=filename)
                print(f"[Download] File ready: {filename}")
                # Show image inside the embed; videos are attached but linked below
                if is_image:
                    success_embed.set_image(url=f"attachment://{filename}")
            else:
                success_embed.add_field(
                    name="\ud83d\udce5 Download",
                    value=f"[Click to download (file too large to attach)]({download_url})",
                    inline=False,
                )
        except Exception as dl_err:
            print(f"[Download] ERROR: {dl_err}")
            if download_url:
                success_embed.add_field(
                    name="\ud83d\udce5 Download",
                    value=f"[Click to download]({download_url})",
                    inline=False,
                )

    # For videos: embed the video URL directly in the embed dict
    if model_value in VIDEO_MODELS:
        video_url = result.get("download_url") or result.get("url")
        if video_url:
            embed_dict = success_embed.to_dict()
            embed_dict["video"] = {"url": video_url}
            success_embed = discord.Embed.from_dict(embed_dict)

    if media_file:
        await status_msg.edit(embed=success_embed, attachments=[media_file])
    else:
        await status_msg.edit(embed=success_embed)

    await interaction.followup.send(
        f"{interaction.user.mention} Your media is ready! **{format_duration(total_time)}** to generate."
    )


@discord.app_commands.allowed_installs(guilds=True, users=True)
@discord.app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
@tree.command(name="sizes", description="View all available media sizes")
async def sizes(interaction: discord.Interaction):
    embed = discord.Embed(
        title="\ud83d\udccf  Available Sizes",
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
        embed.add_field(name="\ud83c\udf05 Landscape", value="\n".join(landscape), inline=False)
    if portrait:
        embed.add_field(name="\ud83d\udcf1 Portrait", value="\n".join(portrait), inline=False)
    if square:
        embed.add_field(name="\u2b1c Square", value="\n".join(square), inline=False)
    await interaction.response.send_message(embed=embed)


@discord.app_commands.allowed_installs(guilds=True, users=True)
@discord.app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
@tree.command(name="models", description="View all available AI models")
async def models_cmd(interaction: discord.Interaction):
    embed = discord.Embed(
        title="\ud83e\udde0  Available Models",
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
            "`Veo 3.1 Fast` — Google Veo 3.1 (faster)"
        ),
        inline=False,
    )
    embed.add_field(
        name="\ud83d\uddbc\ufe0f Reference images",
        value="Only **Nano Banana 2** supports reference images (up to 9). Attach your images as `ref1`–`ref9` in the `/generate` command.",
        inline=False,
    )
    await interaction.response.send_message(embed=embed)


# Optional: Add a simple text command to demonstrate DM functionality
@client.event
async def on_message(message):
    # Don't respond to the bot itself
    if message.author == client.user:
        return

    # Simple ping command that works in DMs
    if message.content.lower() == "!ping":
        await message.channel.send("Pong! 🏓")

    # Let the bot know where it's being used
    if isinstance(message.channel, discord.DMChannel):
        print(f"Bot received DM from {message.author}: {message.content}")


if __name__ == "__main__":
    if not TOKEN:
        print("ERROR: DISCORD_BOT_TOKEN environment variable not set!")
        exit(1)
    print("Starting Discord Bot...")
    print("The bot will work in both servers and DMs!")
    print("\nIMPORTANT: Make sure to re-invite your bot with the correct scopes:")
    print(f"https://discord.com/oauth2/authorize?client_id={client.user.id if client.user else 'YOUR_CLIENT_ID'}&permissions=274877958144&scope=bot+applications.commands")
    client.run(TOKEN)