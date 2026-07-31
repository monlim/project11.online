# WhatsApp website bot

Lets Project Eleven administrators request website changes over WhatsApp.
Claude makes the change and opens a **pull request**; nothing goes live until a
person merges it on GitHub.

```
Admin on WhatsApp ──> this webhook service ──> GitHub Action runs Claude
                                                      │
Admin gets reply with review link  <────────  PR opened on the repo
                    (merge the PR on GitHub to publish)
```

## One-time setup

### 1. Meta / WhatsApp side (business account required)

1. Create a Meta developer app at developers.facebook.com → "Business" type,
   and add the **WhatsApp** product.
2. Note the **Phone number ID** (use the free test number to start, or connect
   a real business number) and create a **permanent access token** (System
   User token with `whatsapp_business_messaging` permission).
3. Note the **App secret** (App settings → Basic).

### 2. GitHub side

1. Create a **fine-grained personal access token** for `monlim/project11.online`
   with *Contents: read and write* (this lets the webhook fire the workflow).
2. In the repo → Settings → Secrets and variables → Actions, add:
   - `ANTHROPIC_API_KEY` — from console.anthropic.com
   - `WHATSAPP_TOKEN` — the access token from step 1
   - `WHATSAPP_PHONE_NUMBER_ID` — the phone number ID from step 1

### 3. Deploy this service (any container host; Fly.io / Cloud Run / Render)

Set these environment variables on the service:

| Variable          | Value                                                        |
|-------------------|--------------------------------------------------------------|
| `VERIFY_TOKEN`    | any random string you make up                                |
| `APP_SECRET`      | Meta app secret                                              |
| `WHATSAPP_TOKEN`  | WhatsApp access token                                        |
| `PHONE_NUMBER_ID` | WhatsApp phone number ID                                     |
| `GITHUB_TOKEN`    | the fine-grained PAT                                         |
| `GITHUB_REPO`     | `monlim/project11.online`                                    |
| `ADMIN_NUMBERS`   | comma-separated admin numbers, e.g. `614xxxxxxxx,628xxxxxxx` |

Example with Fly.io:

```bash
cd whatsapp-bot
fly launch --no-deploy          # accept defaults, creates fly.toml
fly secrets set VERIFY_TOKEN=... APP_SECRET=... WHATSAPP_TOKEN=... \
  PHONE_NUMBER_ID=... GITHUB_TOKEN=... GITHUB_REPO=monlim/project11.online \
  ADMIN_NUMBERS=614xxxxxxxx
fly deploy
```

### 4. Connect the webhook

In the Meta app → WhatsApp → Configuration → Webhook:
- Callback URL: `https://<your-service>/webhook`
- Verify token: the `VERIFY_TOKEN` you chose
- Subscribe to the **messages** field.

## Using it

An administrator (whose number is in `ADMIN_NUMBERS`) messages the bot number:

> Change the gallery opening hours to 10am–4pm

The bot acknowledges, and a few minutes later replies with a summary and a
pull-request link. Open the link, check the change, press **Merge** — the site
updates a minute later. Messages from unknown numbers are ignored.

## Notifications

- The requester always gets the result + PR link on WhatsApp.
- If `WA_OWNER_NUMBER` (repo secret) is set, the owner also gets an alert
  whenever someone else requests a change.
- When a `whatsapp/*` PR is merged or closed, both the requester and the owner
  are told the outcome (published / declined). The requester's number is stored
  encrypted in the PR body using the `WA_STATE_KEY` repo secret.
- WhatsApp only allows free-form messages within 24h of the recipient's last
  message to the bot; outside that window the workflows fall back to the
  generic hello_world template as a "check the bot chat" ping.

Extra repo secrets for notifications: `WA_OWNER_NUMBER` (owner's number,
digits only with country code) and `WA_STATE_KEY` (any random string, e.g.
`openssl rand -hex 16`).

## Notes

- Text requests only for now (photo attachments could be added later).
- The GitHub Action's prompt constrains Claude to site-content edits; it cannot
  touch workflows, DNS config, or this bot.
- Meta access tokens can expire depending on how they were created — a System
  User token is the long-lived option.
