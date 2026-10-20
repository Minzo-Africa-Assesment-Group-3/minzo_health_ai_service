# Minzo AI service

The AI service helps people search the Minzo healthcare directory and checks
published customer reviews. Backend remains responsible for saving data,
permissions and the final review status.

| Name | Meaning |
| --- | --- |
| Backend | The Express.js application and its database |
| AI | This FastAPI and LangChain service |

The conversational assistant is read-only, with optional tools for the signed-in
user's own profile and reviews. Review moderation is a separate,
authenticated workflow that may approve, flag or reject a review.

## Install and run

Python 3.11 or newer is required. From the project folder:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -e '.[dev]'
cp .env.example .env
```

If `.env` already exists, keep it and add the missing settings instead of copying
over it. After configuring the keys, start the server:

```bash
.venv/bin/python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

On Windows PowerShell, without activating the environment:

```powershell
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e '.[dev]'
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

Swagger: <http://127.0.0.1:8000/docs>. Health: <http://127.0.0.1:8000/health>.
Use Swagger's **Authorize** button to enter `SERVICE_API_KEY`.

## Configuration

| Setting | Purpose |
| --- | --- |
| `OPENAI_API_KEY` | Credential for the model provider |
| `OPENAI_MODEL` | Model used by the assistant and review analyser |
| `SERVICE_API_KEY` | Protects incoming requests to AI through `X-Service-Key` |
| `EXPRESS_API_BASE_URL` | Backend origin, e.g. `http://127.0.0.1:3000`; omit `/api/v1` |
| `AI_MODERATION_SERVICE_KEY` | Credential sent to Backend's moderation endpoint; must match Backend's setting with the same name and contain at least 32 characters |
| `EXPRESS_REQUEST_TIMEOUT_SECONDS` | Timeout for each Backend request; default 10 seconds |
| `MODERATION_FLAG_CONFIDENCE_THRESHOLD` | Results below this score need human review; default 0.85 |
| `MODERATION_BLOCK_CONFIDENCE_THRESHOLD` | Minimum score for automatic rejection; default 0.95 and high severity is also required |
| `MODERATION_POLICY_VERSION` | Identifies the moderation rules in analysis-only responses |

`SERVICE_API_KEY` and `AI_MODERATION_SERVICE_KEY` protect opposite directions and
can be different. Keep both on the server. `EXPRESS_SERVICE_TOKEN` is a legacy
setting; it does not authenticate moderation callbacks or public directory reads.
Backend sets `AI_MODERATION_ACTOR_REFERENCE` to identify this moderator in its audit history.

Generate a key with `openssl rand -hex 32`. Do not put real keys in Git or frontend code.
Inside a container, `127.0.0.1` refers to that container, so use the reachable
Backend service address instead.

## Analyse a review and save the decision

```http
POST /v1/moderation/customer-reviews/evaluate
X-Service-Key: <AI SERVICE_API_KEY>
Content-Type: application/json
```

```json
{
  "reviewId": "9b2c7aaa-fb70-438c-a863-a31634985683",
  "reviewUpdatedAt": "2026-10-19T10:30:00.000Z",
  "stars": 2,
  "text": "The waiting time was too long.",
  "business": {
    "id": "9dc967aa-d458-4a52-a06f-dc1e29598148",
    "name": "Example Medical Center"
  }
}
```

All fields above are required. Use a real, unreviewed review from your Backend.
Copy its `updatedAt` exactly into `reviewUpdatedAt`. The example IDs will not exist
in your database. Send the current text and stars, not invented content for an
existing review ID. The review must be `UNREVIEWED`; an already-reviewed or edited
record will return a conflict.

The AI checks the text and makes this request automatically:

```http
PATCH /api/v1/automation/customer-reviews/{reviewId}/moderation
X-Service-Key: <AI_MODERATION_SERVICE_KEY>
```

```json
{
  "decision": "APPROVED",
  "reason": "Ordinary criticism of the service.",
  "reviewUpdatedAt": "2026-10-19T10:30:00.000Z"
}
```

When Backend confirms the save, AI returns:

```json
{
  "reviewId": "9b2c7aaa-fb70-438c-a863-a31634985683",
  "reviewUpdatedAt": "2026-10-19T10:30:00.000Z",
  "decision": "APPROVED",
  "reason": "Ordinary criticism of the service.",
  "confidence": 0.99,
  "categories": ["none"],
  "callbackStatus": "RECORDED",
  "moderationId": "479247ab-6aab-4af8-b9a9-e170e7e24d31",
  "moderatedBy": "AI"
}
```

Confidence is an estimate, not proof. Confidence and categories are returned by
AI but are not stored by the current Backend callback contract.

| Decision | What happens |
| --- | --- |
| `APPROVED` | Review remains visible |
| `FLAGGED` | Review stays visible; a Minzo admin should check it |
| `REJECTED` | Backend hides the review |

Negative reviews and low ratings are allowed. Uncertain results or missing reasons
are sent for human review. The model cannot select the callback URL, service key,
review ID or review version: application code binds these to the incoming request.

### Errors and retries

| HTTP status | Meaning and next action |
| --- | --- |
| 401 | Incoming AI service key is missing or wrong |
| 422 | Input is invalid; check UUIDs, timestamp, stars and text |
| 404 | Backend review is missing or deleted; stop |
| 409 | Review changed or was already moderated; do not force the old decision |
| 502 | Callback failed or returned an invalid confirmation; check Backend connectivity and callback key |
| 503 | Required configuration is missing |

Callback errors include `callbackStatus: NOT_CONFIRMED`. Temporary callback failures
are retried up to three attempts with short delays. The model is not rerun during
these retries. A timeout may mean Backend saved the decision but its reply was lost;
a later 409 is not reported as success. Check the moderation history in that case.
This is a synchronous workflow, not a durable job queue. If the process stops,
there is no background recovery worker.

## Analysis-only endpoint

The existing `POST /v1/moderation/reviews` remains available. It accepts
`review_id`, `review_version`, `text`, optional `stars` and `locale`, and returns
`allow`, `flag` or `block` plus policy information. It does not call Backend or
change a review. Use it for trying sample text without database changes.

## Ask the assistant

```http
POST /v1/assistant/messages
X-Service-Key: <AI SERVICE_API_KEY>
```

```json
{
  "conversation_id": "conversation-123",
  "message": "Find clinics in Monrovia",
  "history": [],
  "principal": {}
}
```

| Field | Required? | Meaning |
| --- | --- | --- |
| `message` | Yes | Current question, up to 5,000 characters |
| `conversation_id` | No | Conversation label; generated if omitted |
| `history` | No | Up to 20 earlier `{ "role": "user" or "assistant", "content": "..." }` messages, in order |
| `business_context` | No | `business_id` and/or `business_slug` for the currently viewed business |
| `principal` | No | Keep empty for public directory questions |

Reusing `conversation_id` alone does not restore past messages. Include `history`
for follow-up questions. The response contains `conversation_id`, `answer` and
`proposed_action: null`. Requests with write capabilities, delegation tokens or a
`confirmed_action` are rejected. The assistant cannot moderate reviews or send
business messages.

### Signed-in users: profile and recent reviews

The frontend sends its normal login access token to Backend:

```http
POST /api/v1/assistant/messages
Authorization: Bearer <user-access-token>
Content-Type: application/json
```

```json
{
  "message": "Show my recent reviews",
  "conversation_id": "chat-123",
  "history": []
}
```

Backend verifies the user token, then forwards it to AI in the Authorization header,
alongside the server-held X-Service-Key. The frontend never needs the service key
or a user ID. Omit Authorization for anonymous public questions.

AI checks the bearer token against Backend before enabling personal tools:

| AI tool | Backend endpoint | Access |
| --- | --- | --- |
| `get_my_profile()` | `GET /api/v1/me` | Current user's name, email, phone and account status |
| `get_my_reviews(page_number, page_size)` | `GET /api/v1/me/reviews` | Current user's reviews, newest first, including hidden/anonymous reviews |

The token lives in a request-scoped client. It is never passed to the model prompt,
conversation history, tool arguments or responses. The model cannot choose a user
ID. Body `principal.user_id` does not enable personal tools. No token means no
personal tools. An invalid or expired token returns 401; unavailable accounts return
403. Refresh the user session in the frontend and retry when appropriate.

For direct AI Swagger testing, provide both X-Service-Key and optional UserBearerAuth
using your actual user access token. These headers also work on AI's streaming route.
The new Backend relay currently returns JSON; it does not proxy the streaming route.

For streaming, use `POST /v1/assistant/messages/stream` with the same body and key.
Events are `start`, `token`, `done` and `error`. Use `curl -N` or a Fetch stream;
Swagger may wait until the stream finishes before displaying the result.

## Directory tools

| Information | Backend route |
| --- | --- |
| Business profile | `GET /api/v1/businesses/:slug` |
| Business search | `GET /api/v1/businesses` |
| Reviews | `GET /api/v1/businesses/:id/reviews` |
| Rating | `GET /api/v1/businesses/:id/rating` |
| Services | `GET /api/v1/services` |
| Counties | `GET /api/v1/counties` |
| Cities | `GET /api/v1/cities` |

The adapter converts the tool's `page` parameter to Backend's `pageNumber`.
City search requires `countyId` and `search`. Proximity search needs latitude,
longitude and radius together. These public calls do not carry the moderation key.

## What still needs connecting in Backend

The AI evaluation endpoint and its callback are ready for direct Swagger/API testing.
Backend still needs to send the review to AI after publication and after edits.
Keep review publication independent of AI availability; failed analysis leaves it
available for human review. Backend now provides POST /api/v1/assistant/messages as
the frontend chat relay. Configure Backend AI_SERVICE_URL (default localhost:8000)
and SERVICE_API_KEY to match AI. Do not send SERVICE_API_KEY from the browser.

```text
Customer -> Backend: publish review
Backend -> AI: review ID, timestamp, text, stars, business
AI -> Model: analyse the content
AI -> Backend: save decision for that review and timestamp
Backend -> AI: confirm saved decision and audit ID
AI -> Caller: RECORDED
```

## Tests

```bash
.venv/bin/python -m pytest
.venv/bin/python -m ruff check .
```

Tests use a fake model and mocked Backend responses. They cover classification,
callback credentials, exact version forwarding, retry limits, conflicts, invalid
confirmations, read-only chat, streaming, and request validation. They do not
require provider credentials or modify your database.
