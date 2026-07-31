#!/usr/bin/env python3
"""Send a WhatsApp text message — used by the GitHub workflows.

Usage: wa_send.py <recipient-number> <message-body>
Env:   WHATSAPP_TOKEN, PHONE_NUMBER_ID

Free-form texts are only deliverable inside WhatsApp's 24-hour service window
(opened whenever the recipient last messaged the bot). Outside it, Meta rejects
the send, so we fall back to the pre-approved hello_world template — a generic
ping that tells the person to check the bot chat / GitHub.
"""
import json
import os
import sys
import urllib.error
import urllib.request


def send(payload: dict) -> int:
    req = urllib.request.Request(
        f"https://graph.facebook.com/v25.0/{os.environ['PHONE_NUMBER_ID']}/messages",
        data=json.dumps(payload).encode(),
        headers={
            "Authorization": f"Bearer {os.environ['WHATSAPP_TOKEN']}",
            "Content-Type": "application/json",
        },
    )
    return urllib.request.urlopen(req, timeout=20).status


def main() -> None:
    if len(sys.argv) < 3 or not sys.argv[1].strip():
        print("wa_send: no recipient, skipping")
        return
    to, body = sys.argv[1].strip(), sys.argv[2]
    try:
        send({"messaging_product": "whatsapp", "to": to, "type": "text",
              "text": {"body": body[:4000]}})
        print("wa_send: text sent")
    except urllib.error.HTTPError as e:
        print(f"wa_send: text rejected ({e.code}), trying template fallback")
        try:
            send({"messaging_product": "whatsapp", "to": to, "type": "template",
                  "template": {"name": "hello_world", "language": {"code": "en_US"}}})
            print("wa_send: template fallback sent")
        except Exception as e2:
            print(f"wa_send: template fallback failed: {e2}")


if __name__ == "__main__":
    main()
