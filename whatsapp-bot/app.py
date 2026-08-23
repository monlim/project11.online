#!/usr/bin/env python3
"""WhatsApp -> GitHub bridge for project11.online website change requests.

Receives WhatsApp Cloud API webhooks, checks the sender against an allowlist
of administrator phone numbers, and fires a GitHub repository_dispatch event
that runs the "WhatsApp website request" workflow (which has Claude Code make
the change and open a pull request).

Photos and videos are supported: attachments are downloaded from WhatsApp and
committed to the `media-inbox` branch, then handed to the workflow. An
attachment with a caption is actioned straight away; an attachment without one
is held until the administrator sends a follow-up instruction.

Environment variables (all required):
  VERIFY_TOKEN      any string you choose; also entered in the Meta webhook config
  APP_SECRET        Meta app secret, used to verify webhook signatures
  WHATSAPP_TOKEN    WhatsApp Cloud API access token (for sending replies)
  PHONE_NUMBER_ID   the bot's WhatsApp phone-number ID from Meta
  GITHUB_TOKEN      fine-grained PAT for the site repo with Contents read/write
  GITHUB_REPO       e.g. monlim/project11.online
  ADMIN_NUMBERS     comma-separated admin phone numbers, digits only with
                    country code, e.g. 614xxxxxxxx,628xxxxxxxxx
"""
import base64
import hashlib
import hmac
import json
import mimetypes
import os
import time
import urllib.error
import urllib.request

from fastapi import FastAPI, Request, Response

app = FastAPI()

VERIFY_TOKEN = os.environ["VERIFY_TOKEN"]
APP_SECRET = os.environ["APP_SECRET"].encode()
WHATSAPP_TOKEN = os.environ["WHATSAPP_TOKEN"]
PHONE_NUMBER_ID = os.environ["PHONE_NUMBER_ID"]
GITHUB_TOKEN = os.environ["GITHUB_TOKEN"]
GITHUB_REPO = os.environ["GITHUB_REPO"]
ADMIN_NUMBERS = {n.strip() for n in os.environ["ADMIN_NUMBERS"].split(",") if n.strip()}

GRAPH = "https://graph.facebook.com/v25.0"
GH = f"https://api.github.com/repos/{GITHUB_REPO}"
MEDIA_BRANCH = "media-inbox"
MAX_MEDIA_BYTES = 10 * 1024 * 1024
PENDING_TTL = 24 * 3600

seen_message_ids: set[str] = set()  # WhatsApp retries webhooks; dedupe


# ---------------------------------------------------------------- WhatsApp ---

def send_whatsapp(to: str, body: str) -> None:
    payload = {
        "messaging_product": "whatsapp",
        "to": to,
        "type": "text",
        "text": {"body": body[:4000]},
    }
    req = urllib.request.Request(
        f"{GRAPH}/{PHONE_NUMBER_ID}/messages",
        data=json.dumps(payload).encode(),
        headers={
            "Authorization": f"Bearer {WHATSAPP_TOKEN}",
            "Content-Type": "application/json",
        },
    )
    urllib.request.urlopen(req, timeout=15)


def download_media(media_id: str) -> tuple[bytes, str]:
    """Fetch a WhatsApp media object: returns (bytes, mime_type)."""
    info_req = urllib.request.Request(
        f"{GRAPH}/{media_id}",
        headers={"Authorization": f"Bearer {WHATSAPP_TOKEN}"},
    )
    info = json.load(urllib.request.urlopen(info_req, timeout=20))
    mime = (info.get("mime_type") or "").split(";")[0]
    if int(info.get("file_size") or 0) > MAX_MEDIA_BYTES:
        raise ValueError("too big")
    bin_req = urllib.request.Request(
        info["url"],
        headers={
            "Authorization": f"Bearer {WHATSAPP_TOKEN}",
            "User-Agent": "project11-bot/1.0",
        },
    )
    data = urllib.request.urlopen(bin_req, timeout=60).read()
    if len(data) > MAX_MEDIA_BYTES:
        raise ValueError("too big")
    return data, mime


# ------------------------------------------------------------------ GitHub ---

def gh_request(method: str, url: str, body: dict | None = None):
    req = urllib.request.Request(
        url,
        method=method,
        data=json.dumps(body).encode() if body is not None else None,
        headers={
            "Authorization": f"Bearer {GITHUB_TOKEN}",
            "Accept": "application/vnd.github+json",
            "Content-Type": "application/json",
        },
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        raw = resp.read()
    return json.loads(raw) if raw else {}


def ensure_media_branch() -> None:
    try:
        gh_request("GET", f"{GH}/git/ref/heads/{MEDIA_BRANCH}")
    except urllib.error.HTTPError as e:
        if e.code != 404:
            raise
        main = gh_request("GET", f"{GH}/git/ref/heads/main")
        gh_request("POST", f"{GH}/git/refs", {
            "ref": f"refs/heads/{MEDIA_BRANCH}",
            "sha": main["object"]["sha"],
        })


def gh_read_file(path: str) -> tuple[dict | None, str | None]:
    """Returns (parsed_json_content, sha) for a JSON file on the media branch."""
    try:
        info = gh_request("GET", f"{GH}/contents/{path}?ref={MEDIA_BRANCH}")
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return None, None
        raise
    raw = base64.b64decode(info["content"])
    try:
        return json.loads(raw), info["sha"]
    except Exception:
        return None, info["sha"]


def gh_write_file(path: str, data: bytes, message: str, sha: str | None = None) -> None:
    body = {
        "message": message,
        "content": base64.b64encode(data).decode(),
        "branch": MEDIA_BRANCH,
    }
    if sha:
        body["sha"] = sha
    gh_request("PUT", f"{GH}/contents/{path}", body)


# ----------------------------------------------------------- pending media ---

def pending_path(sender: str) -> str:
    digest = hashlib.sha256((sender + APP_SECRET.decode()).encode()).hexdigest()[:16]
    return f"pending/{digest}.json"


def load_pending(sender: str) -> list[dict]:
    data, _ = gh_read_file(pending_path(sender))
    if not isinstance(data, list):
        return []
    cutoff = time.time() - PENDING_TTL
    return [item for item in data if item.get("ts", 0) > cutoff]


def save_pending(sender: str, items: list[dict]) -> None:
    path = pending_path(sender)
    _, sha = gh_read_file(path)
    gh_write_file(path, json.dumps(items).encode(), "Update pending media", sha)


def store_media(data: bytes, mime: str, filename: str | None) -> str:
    ext = ""
    if filename and "." in filename:
        ext = "." + filename.rsplit(".", 1)[1].lower()
    if not ext:
        ext = {"image/jpeg": ".jpg", "image/png": ".png", "image/webp": ".webp",
               "video/mp4": ".mp4", "application/pdf": ".pdf"}.get(mime) \
            or mimetypes.guess_extension(mime) or ".bin"
    name = f"{int(time.time())}-{hashlib.sha256(data).hexdigest()[:8]}{ext}"
    path = f"media/{name}"
    ensure_media_branch()
    gh_write_file(path, data, f"Add WhatsApp attachment {name}")
    return path


# ---------------------------------------------------------------- dispatch ---

def dispatch_to_github(request_text: str, sender: str, media: list[str]) -> None:
    payload = {
        "event_type": "website-request",
        "client_payload": {
            "request": request_text,
            "sender": sender,
            "media": ",".join(media),
        },
    }
    gh_request("POST", f"{GH}/dispatches", payload)


# ----------------------------------------------------------------- webhook ---

@app.get("/webhook")
async def verify(request: Request):
    """Meta's one-time webhook verification handshake."""
    q = request.query_params
    if q.get("hub.mode") == "subscribe" and q.get("hub.verify_token") == VERIFY_TOKEN:
        return Response(content=q.get("hub.challenge", ""), media_type="text/plain")
    return Response(status_code=403)


@app.post("/webhook")
async def receive(request: Request):
    raw = await request.body()

    # Verify the payload really came from Meta
    sig = request.headers.get("x-hub-signature-256", "")
    expected = "sha256=" + hmac.new(APP_SECRET, raw, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(sig, expected):
        return Response(status_code=403)

    data = json.loads(raw)
    for entry in data.get("entry", []):
        for change in entry.get("changes", []):
            value = change.get("value", {})
            for msg in value.get("messages", []):
                handle_message(msg)
            for st in value.get("statuses", []):
                line = f"status: {st.get('status')} id={st.get('id', '')[-12:]}"
                for err in st.get("errors", []) or []:
                    line += (f" ERROR {err.get('code')}: {err.get('title')} — "
                             f"{err.get('message', '')} {json.dumps(err.get('error_data', {}))}")
                print(line, flush=True)
    return {"ok": True}


def handle_message(msg: dict) -> None:
    mid = msg.get("id", "")
    if mid in seen_message_ids:
        return
    seen_message_ids.add(mid)
    if len(seen_message_ids) > 5000:
        seen_message_ids.clear()

    sender = msg.get("from", "")
    if sender not in ADMIN_NUMBERS:
        return  # silently ignore anyone who isn't an administrator

    mtype = msg.get("type")
    try:
        if mtype in ("image", "video", "document"):
            handle_attachment(msg, sender, mtype)
        elif mtype == "text":
            handle_text(msg["text"]["body"].strip(), sender)
        else:
            send_whatsapp(sender, "I can work with text, photos, videos and PDFs. "
                                  "Voice notes and stickers I can't use, sorry.")
    except Exception as exc:  # noqa: BLE001 - report anything unexpected to the admin
        print(f"handle_message error: {exc!r}", flush=True)
        send_whatsapp(sender, "Sorry, something went wrong handling that. "
                              "Please try again in a moment.")


def handle_attachment(msg: dict, sender: str, mtype: str) -> None:
    obj = msg.get(mtype, {})
    mime = (obj.get("mime_type") or "").split(";")[0]
    if not mime.startswith(("image/", "video/")) and mime != "application/pdf":
        send_whatsapp(sender, "I can only use photos, videos and PDFs as "
                              "website content.")
        return

    try:
        data, mime = download_media(obj["id"])
    except ValueError:
        send_whatsapp(sender, "That file is too large for me to handle (limit is "
                              "about 10 MB). Could you send a smaller version?")
        return

    path = store_media(data, mime, obj.get("filename"))
    caption = (obj.get("caption") or "").strip()

    pending = load_pending(sender)
    pending.append({"path": path, "mime": mime, "ts": time.time()})

    if caption:
        media = [item["path"] for item in pending]
        dispatch_to_github(caption, sender, media)
        save_pending(sender, [])
        count = len(media)
        send_whatsapp(sender, f"Got it - working on that now with {count} "
                              f"attachment{'s' if count > 1 else ''}. I'll reply with a "
                              "review link when the change is ready.")
    else:
        save_pending(sender, pending)
        send_whatsapp(sender, f"Saved that {mtype} ({len(pending)} waiting). Send me a "
                              "message describing where it should go on the website, "
                              "or send more files first.")


def handle_text(text: str, sender: str) -> None:
    if len(text) < 8:
        send_whatsapp(sender, "Please describe the website change you'd like "
                              "in a full sentence.")
        return

    pending = load_pending(sender)
    media = [item["path"] for item in pending]

    dispatch_to_github(text, sender, media)
    if media:
        save_pending(sender, [])
        send_whatsapp(sender, f"Got it - working on that now with {len(media)} "
                              f"attachment{'s' if len(media) > 1 else ''}. I'll reply "
                              "with a review link when the change is ready.")
    else:
        send_whatsapp(sender, "Got it - working on that now. I'll reply with a "
                              "review link when the change is ready (usually a "
                              "few minutes).")


@app.get("/")
async def health():
    return {"service": "project11 whatsapp bot", "ok": True}
