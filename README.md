# Secure 1:1 Audio Calls on AWS (Amazon Chime SDK + Serverless)

Minimal, production-ready 1:1 audio calling MVP built with **Amazon Chime SDK Meetings**, **AWS SAM** (API Gateway + Lambda + DynamoDB), and a static frontend on **S3 + CloudFront (HTTPS)**.

- Admin page issues short-lived **host/guest links** with **JWT** tokens  
- Room page asks for mic permission (pre-join test + VU meter) and joins the meeting  
- Invite links expire; room TTL auto-cleans in DynamoDB

---

## Architecture

```text
S3 (static) -- CloudFront (HTTPS) --> index.html / room.html
                                         |
Browser (Chime JS SDK, mic) -------------+----> API Gateway (HTTP API)
/rooms (admin key)  -> Lambda (rooms) -> DynamoDB (rooms, invites + TTL)
/rooms/{id}/join -> Lambda (join) -----> Amazon Chime SDK Meetings (Create/Get/Attendee)
```

**Key points**
- No SFU to operate; Chime media is managed by AWS
- Serverless pay-per-use for API + DB
- JWT invites (HS256), Admin API key, CORS locked to CloudFront domain

---

## Repository layout

```text
backend/
  rooms/app.py          # create room, issue invites (JWT), store TTL entries
  join/app.py           # verify invite, Create/Get Meeting, Create Attendee
  common_jwt.py         # HS256 sign/verify helpers
frontend/
  index.html            # admin UI (create room + links)
  room.html             # pre-join (mic test) + Chime session (join/mute/leave)
  vendor/amazon-chime-sdk.min.js  # browser bundle (IIFE, window.ChimeSDK)
template.yaml           # SAM (HTTP API, 2 Lambdas, 2 Dynamo tables, S3 website)
```

---

## Prerequisites

- AWS CLI configured (`aws configure`)
- **AWS SAM CLI** (build/deploy)
- Node.js 18+ (**only** to build the browser SDK bundle)
- Python 3.12 runtime on Lambda (via SAM)

---

## Quick start

### 1) Deploy backend (SAM)

Generate secrets (do **not** commit them):

```bash
# macOS/Linux
JWT_SECRET=$(openssl rand -hex 32)
ADMIN_KEY=$(openssl rand -hex 16)

sam deploy --guided \
  --stack-name chime-audio-mvp \
  --parameter-overrides \
    JwtSecret=$JWT_SECRET \
    AdminApiKey=$ADMIN_KEY \
    MediaRegion=eu-central-1   # pick region closest to end users
```

**Outputs to note**:
- `HttpApiUrl` — e.g., `https://xxxxx.execute-api.eu-central-1.amazonaws.com`
- `WebsiteBucketName` — S3 bucket for static frontend

> If `join` returns 500 “Missing ExternalMeetingId”: ensure you use `boto3.client('chime-sdk-meetings')`, pass `ExternalMeetingId` to `CreateMeeting`, and on subsequent joins return **full** meeting via `GetMeeting` (for `MediaPlacement`).

---

### 2) Build the Chime SDK browser bundle

Commit the built file (simplest flow):

```bash
npm init -y
npm i amazon-chime-sdk-js@^3
npm i -D esbuild@^0.23

npx esbuild node_modules/amazon-chime-sdk-js/build/index.js \
  --bundle --minify --format=iife --global-name=ChimeSDK \
  --platform=browser --main-fields=browser,module,main --conditions=browser \
  --define:global=window --define:process.env.NODE_ENV='"production"' \
  --outfile=frontend/vendor/amazon-chime-sdk.min.js
```

In `frontend/room.html`:

```html
<script src="vendor/amazon-chime-sdk.min.js"></script>
```

*(If you prefer not to commit large vendor files, add an npm script `build:sdk` and ignore `frontend/vendor/` in `.gitignore`.)*

---

### 3) Set API base URL in the frontend

In `frontend/index.html` and `frontend/room.html`:

```js
const API_BASE = "https://<your-api-id>.execute-api.<region>.amazonaws.com";
```

*(Optionally, put it in `frontend/config.js` and read from `window.APP_CONFIG.API_BASE`.)*

---

### 4) Upload the frontend to S3

```bash
aws s3 sync frontend/ s3://<WebsiteBucketName>/ --delete
```

You can open the S3 **Website endpoint** to test admin UI, but **microphone requires HTTPS** → use CloudFront.

---

### 5) Enable HTTPS with CloudFront

Create a CloudFront distribution:

- **Origin**: S3 **Website** endpoint (not REST)
- **Viewer Protocol Policy**: Redirect HTTP → **HTTPS**
- **Default Root Object**: `index.html`

Open:
- `https://<cloudfront-domain>/index.html` — create a room; copy **host/guest** links
- `https://<cloudfront-domain>/room.html?room=...&t=...` — mic test, **Join**

On updates:
```bash
aws cloudfront create-invalidation --distribution-id <DIST_ID> --paths "/*"
```

---

## Local development

```bash
cd frontend
python3 -m http.server 8000
# Open http://localhost:8000/index.html
# Open room link from the admin page
```

`localhost` is a secure context, so mic permissions work.

---

## Security

- Admin endpoint `/rooms` requires `X-Admin-Key`
- Invite links are **HS256 JWT** with short TTL; DynamoDB enforces one-time use
- Lock CORS on the HTTP API to your CloudFront domain in `template.yaml` once verified

---

## Costs

- Chime media minutes + API/Lambda/DynamoDB/S3/CloudFront (pay-per-use)
- Idle costs ~zero (static hosting + small tables)

---

## Troubleshooting

- **Empty mic list** → use **HTTPS**/`localhost`, click **Test** to grant permission
- **Second join fails with `MediaPlacement` undefined** → return **full** meeting via `GetMeeting` when it already exists
- **500 `Missing ExternalMeetingId`** → pass `ExternalMeetingId` in `CreateMeeting` (e.g., `room_id[:64]`)
- **CORS error** → set `CorsConfiguration` on `HttpApi` to allow your CloudFront origin
- **Frontend not updating** → CloudFront invalidation

---

## License

MIT — see [LICENSE](LICENSE).
