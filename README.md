# Minzo Express AI

A separate Python FastAPI and LangChain service for Minzo Africa. It does not
replace the deterministic Express backend. The Express application remains the
source of truth for users, businesses, reviews, authorization, messages, and
audit records.

The initial service provides:

- structured post-publication review classification with deterministic policy gates;
- a conversational assistant for directory and account questions;
- read-only tools for business lookup, discovery, reviews, ratings, services, counties,
  and cities;
- a two-phase, explicitly confirmed tool for sending business messages;
- service-to-service authentication on protected endpoints;
- a single Express API adapter aligned with the current public Minzo contracts.

## Architecture

```text
Client
  -> Express API (authentication, authorization, business rules, persistence)
      -> Minzo Express AI (reasoning and classification)
          -> Express API (narrow tool calls)
          -> OpenAI model
```

The browser must not call this service directly. Express authenticates the caller,
builds the trusted principal context, and calls this service. The model never
receives a tool that can choose an acting user, delegation token, idempotency key,
or mutation arguments.

## Project structure

```text
app/
├── main.py                     # Imports and exposes the FastAPI application only
├── bootstrap.py                # Application factory and HTTP-client lifespan
├── llm.py                      # OpenAI ChatModel construction
├── api/
│   ├── router.py               # Top-level public and protected router composition
│   ├── dependencies.py         # FastAPI dependency wiring
│   ├── errors.py               # HTTP exception translation
│   └── routes/                 # Thin HTTP handlers
├── assistant/
│   ├── service.py              # LangChain agent orchestration
│   ├── tools.py                # Request-scoped LangChain tools
│   └── prompts.py              # Assistant system policy
├── review_moderation/
│   ├── service.py              # Structured review classification
│   └── prompts.py              # Moderation policy
├── clients/
│   └── express_api.py          # Deterministic Express API adapter
├── core/
│   ├── config.py               # Environment configuration
│   └── security.py             # Service-key authentication
└── schemas/                    # Pydantic request and response contracts
```

## Set up

Python 3.11 or newer is required.

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e '.[dev]'
cp .env.example .env
```

Fill in `.env` when the API keys are available. Generate a long random
`SERVICE_API_KEY` and configure the same value in the Express backend.

Start the service:

```bash
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

OpenAPI documentation is available at `http://127.0.0.1:8000/docs` and the
public health endpoint is `http://127.0.0.1:8000/health`.

Use the Swagger **Authorize** button to enter `SERVICE_API_KEY` for protected
assistant and moderation requests.

## Moderate a review

```bash
curl -X POST http://127.0.0.1:8000/v1/moderation/reviews \
  -H 'Content-Type: application/json' \
  -H 'X-Service-Key: replace-with-a-long-random-value' \
  -d '{
    "review_id": "review-123",
    "text": "The clinic opened two hours late.",
    "stars": 2,
    "locale": "en-LR"
  }'
```

The endpoint returns a structured decision with `action`, categories, severity,
confidence, whether a human must review it, a content hash, model name, review
version, and policy version. Deterministic code downgrades uncertain or inconsistent
model outcomes to `flag`; the model cannot directly force a consequential decision.

The AI service does not currently delete or hide a review. The next integration
phase will add a restricted Express automation endpoint that records an
`AUTOMATION` actor and rejects stale review versions. Negative feedback must not be
treated as abuse merely because it criticizes a business.

## Ask the assistant

```bash
curl -X POST http://127.0.0.1:8000/v1/assistant/messages \
  -H 'Content-Type: application/json' \
  -H 'X-Service-Key: replace-with-a-long-random-value' \
  -d '{
    "conversation_id": "conversation-123",
    "principal": {},
    "message": "Find a highly rated clinic in Montserrado"
  }'
```

### Assistant request contract

For an ordinary public question, `message` is the only mandatory JSON field.
Protected assistant endpoints also require `X-Service-Key` as an HTTP header; the
service key must never be placed in the request body or exposed to the browser.

| Field | Mandatory | Supplied by | Purpose |
|---|---:|---|---|
| `message` | Yes | User through the frontend | The current question or instruction |
| `conversation_id` | No, but recommended | Frontend or Express | Correlates requests belonging to the same conversation |
| `history` | No | Express | Supplies previous conversation turns until server-side memory is implemented |
| `business_context` | No | Frontend through Express | Identifies the business currently displayed |
| `principal` | Only for authenticated actions | Express only | Supplies trusted user identity and explicitly granted capabilities |
| `confirmed_action` | Only when executing an action | Express only | Binds the assistant to an exact action already confirmed by the user |

The minimum request body is:

```json
{
  "message": "Find clinics in Monrovia"
}
```

For consistent frontend correlation, prefer:

```json
{
  "conversation_id": "conversation-123",
  "principal": {},
  "message": "Find clinics in Monrovia"
}
```

#### `message`

- Required and trimmed before use.
- Must not be blank.
- Maximum length is 5,000 characters.
- Contains only the current user message; previous turns belong in `history`.

#### `conversation_id`

- Optional; the service generates a UUID when it is omitted.
- Maximum length is 128 characters.
- Reuse it for all requests belonging to the same conversation.
- It currently provides correlation only. Conversation history is not yet persisted,
  so reusing the ID by itself does not restore previous messages.

#### `history`

History is a chronological list containing at most 20 previous messages:

```json
{
  "conversation_id": "conversation-123",
  "message": "Which one has the best rating?",
  "history": [
    {
      "role": "user",
      "content": "Find clinics in Monrovia"
    },
    {
      "role": "assistant",
      "content": "I found three clinics."
    }
  ]
}
```

Each history entry requires a `role` of `user` or `assistant` and nonblank `content`
of at most 5,000 characters. Do not append the current `message` to `history`.
Express should eventually load trusted conversation history instead of accepting it
directly from a browser.

#### `business_context`

Use business context when the assistant is opened from a specific business page:

```json
{
  "message": "What services does this facility provide?",
  "business_context": {
    "business_id": "5cd2e747-3c63-4f8d-8ab2-5e03ac43dceb",
    "business_slug": "example-clinic"
  }
}
```

`business_id` supports business-specific ratings, reviews, and actions.
`business_slug` supports retrieving the public business profile. Both are optional,
but an empty `business_context` object should be omitted.

#### `principal`

`principal` is trusted Express-to-AI context, not ordinary browser input:

```json
{
  "user_id": "user-123",
  "capabilities": ["send_business_message"],
  "delegation_token": "short-lived-signed-token"
}
```

| Principal field | Mandatory | Purpose |
|---|---:|---|
| `user_id` | Required when a capability is granted | Identifies the authenticated user |
| `capabilities` | Required for a write action | Restricts which action the assistant may perform |
| `delegation_token` | Required when a capability is granted | Gives short-lived authorization to call Express |

The model never receives the delegation token. Public read-only requests use an
empty principal: `"principal": {}`.

#### `confirmed_action`

`confirmed_action` is supplied only after the user has reviewed and approved the
exact action. For a business message, all of these values are required:

| Action field | Purpose |
|---|---|
| `type` | Identifies the permitted operation |
| `business_id` | Binds confirmation to one business |
| `message` | Binds confirmation to the exact approved message, maximum 2,000 characters |
| `idempotency_key` | Prevents the same confirmed action from executing twice |

The `idempotency_key` must contain between 8 and 128 characters. A confirmed action
is rejected unless `principal.capabilities` contains `send_business_message` and the
principal includes both a user ID and delegation token.

For a normal request, no write tool is available. If the user asks to send a
business message, the assistant returns a `proposed_action` containing the exact
business ID and message and marks it as requiring confirmation.

After the user confirms it, Express sends a new internal request with a trusted
principal and an exact confirmed action:

```json
{
  "conversation_id": "conversation-123",
  "principal": {
    "user_id": "user-123",
    "capabilities": ["send_business_message"],
    "delegation_token": "short-lived-signed-token"
  },
  "message": "Yes, send that message.",
  "confirmed_action": {
    "type": "send_business_message",
    "business_id": "business-uuid",
    "message": "Please call me about an appointment.",
    "idempotency_key": "message-confirmation-123"
  }
}
```

Only then is a write tool created. It has no model-controlled arguments and sends
exactly the server-confirmed payload at most once.

## Stream assistant responses

The JSON endpoint remains the easiest option in Swagger. For progressive frontend
rendering, use the Server-Sent Events endpoint:

```bash
curl -N -X POST http://127.0.0.1:8000/v1/assistant/messages/stream \
  -H 'Content-Type: application/json' \
  -H 'X-Service-Key: replace-with-your-service-key' \
  -d '{
    "conversation_id": "conversation-123",
    "principal": {},
    "message": "What can Minzo help me find?"
  }'
```

The event sequence is:

```text
start -> token... -> proposed_action (optional) -> done
```

Swagger can send the streaming request, but it normally displays the response after
completion. A browser `fetch()` stream or `curl -N` renders tokens as they arrive.

## Connect the Express API

The HTTP paths are isolated in `app/clients/express_api.py`:

| Tool operation | Express route |
|---|---|
| Business details | `GET /api/v1/businesses/:slug` |
| Directory search | `GET /api/v1/businesses` |
| Business reviews | `GET /api/v1/businesses/:id/reviews` |
| Business rating | `GET /api/v1/businesses/:id/rating` |
| Service lookup | `GET /api/v1/services` |
| County lookup | `GET /api/v1/counties` |
| City lookup | `GET /api/v1/cities` |
| Send message | `POST /api/v1/businesses/:id/contact-messages` |

The remaining Express integration task is to mint and verify the short-lived
delegation token and enforce idempotency. The insecure `X-Acting-User-Id` behavior
has been removed.

## Safety boundaries

- Authentication, authorization, ownership checks, rate limits, and audit logs
  stay in Express.
- Model moderation is a signal. Deterministic policy code escalates borderline
  decisions to a human moderator.
- Tool responses are treated as untrusted data to reduce prompt-injection risk.
- Write tools are omitted unless Express provides a capability, a delegation token,
  and an exact confirmed action.
- Anonymous review identities and private registration documents must never be
  returned by tool endpoints.
- The assistant does not diagnose conditions, prescribe treatments, or guarantee
  facility availability.
- Do not send an assistant-generated business message without explicit confirmation.

## Tests

```bash
.venv/bin/python -m pytest
ruff check .
```

The direct `.venv/bin/pytest` launcher may contain a stale absolute path if this
folder was copied. Invoking pytest through the virtual-environment Python avoids
that launcher issue.
