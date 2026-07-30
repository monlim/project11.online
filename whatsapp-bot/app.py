#!/usr/bin/env python3
"""WhatsApp -> GitHub bridge for project11.online website change requests.

Receives WhatsApp Cloud API webhooks, checks the sender against an allowlist
of administrator phone numbers, and fires a GitHub repository_dispatch event
that runs the "WhatsApp website request" workflow (which has Claude Code make
the change and open a pull request).

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
import hashlib
import hmac
import json
import os
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

seen_message_ids: set[str] = set()  # WhatsApp retries webhooks; dedupe


def send_whatsapp(to: str, body: str) -> None:
    payload = {
        "messaging_product": "whatsapp",
        "to": to,
        "type": "text",
        "text": {"body": body[:4000]},
    }
    req = urllib.request.Request(
        f"https://graph.facebook.com/v20.0/{PHONE_NUMBER_ID}/messages",
        data=json.dumps(payload).encode(),
        headers={
            "Authorization": f"Bearer {WHATSAPP_TOKEN}",
            "Content-Type": "application/json",
        },
    )
    urllib.request.urlopen(req, timeout=15)


def dispatch_to_github(request_text: str, sender: str) -> None:
    payload = {
        "event_type": "website-request",
        "client_payload": {"request": request_text, "sender": sender},
    }
    req = urllib.request.Request(
        f"https://api.github.com/repos/{GITHUB_REPO}/dispatches",
        data=json.dumps(payload).encode(),
        headers={
            "Authorization": f"Bearer {GITHUB_TOKEN}",
            "Accept": "application/vnd.github+json",
            "Content-Type": "application/json",
        },
    )
    urllib.request.urlopen(req, timeout=15)


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
                    line += f" ERROR {err.get('code')}: {err.get('title')} — {err.get('message', '')} {json.dumps(err.get('error_data', {}))}"
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

    if msg.get("type") != "text":
        send_whatsapp(sender, "I can only take text requests for now. "
                              "Describe the change you'd like in words.")
        return

    text = msg["text"]["body"].strip()
    if len(text) < 8:
        send_whatsapp(sender, "Please describe the website change you'd like "
                              "in a full sentence.")
        return

    try:
        dispatch_to_github(text, sender)
        send_whatsapp(sender, "Got it - working on that now. I'll reply with a "
                              "review link when the change is ready (usually a "
                              "few minutes).")
    except Exception:
        send_whatsapp(sender, "Sorry, I couldn't start that request. Please "
                              "try again shortly.")


@app.get("/")
async def health():
    return {"service": "project11 whatsapp bot", "ok": True}
