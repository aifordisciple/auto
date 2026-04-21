# Phase 2: Dual-Channel Auth + Refresh Token System

## Context

Phase 1 (completed) laid the database foundation: `phone_number` field, `OAuthAccount`/`ActiveSession` tables, refresh token utility functions, and Pydantic schemas. No new endpoints or frontend changes were made.

Phase 2 builds the complete authentication workflow on top of this foundation, introducing SMS-based login, Redis-backed rate limiting, and a dual-token session system with httpOnly Cookie storage.

## Key Decisions

- **SMS Provider**: Alibaba Cloud (Aliyun) SMS
- **OTP Policy**: Standard — 6-digit code, 5min TTL, 10/day/phone, 5/hour/IP, 60s cooldown
- **Token Storage**: httpOnly Cookie mode (both AT and RT in cookies, `SameSite=Lax`, `Secure` in production)

## Architecture

### Backend: Risk Control Engine

**File**: `app/services/risk_control.py`

New module using existing `RedisCache` (from `cache_service.py`) for all rate limiting and OTP storage.

Key functions:
- `check_sms_rate_limit(phone, ip)` — 60s cooldown lock + daily 10/phone + hourly 5/IP
- `record_sms_sent(phone, otp)` — write OTP to Redis (TTL 300s) + cooldown lock + daily counter
- `verify_otp(phone, code)` — constant-time compare + 3-error burn + atomic delete on success
- `check_login_risk(phone, ip)` — 5-failure lockout (30min) + exponential backoff
- `record_login_failure(phone, ip)` / `clear_login_failure(phone, ip)`

Redis key patterns:
- `auth:sms:code:{phone}` — OTP value (TTL 300s)
- `auth:sms:err:{phone}` — OTP error count (TTL 300s)
- `risk:sms:lock:{phone}` — 60s cooldown sentinel
- `risk:sms:daily:{phone}` — daily send counter (TTL 86400s)
- `risk:sms:ip:{ip}` — hourly IP counter (TTL 3600s)
- `risk:login:fail:{phone}` — login failure count (TTL 1800s)
- `risk:login:lock:{phone}` — account lock sentinel (TTL 1800s)
- `risk:login:fail:{ip}` — IP failure count (TTL 3600s)

### Backend: Aliyun SMS Service

**File**: `app/services/sms_service.py`

- `AliyunSMSService` class with lazy client initialization
- `send_verification_code(phone, code)` — async send via Aliyun SDK
- Config: `ALIYUN_ACCESS_KEY_ID`, `ALIYUN_ACCESS_KEY_SECRET`, `ALIYUN_SMS_SIGN_NAME`, `ALIYUN_SMS_TEMPLATE_CODE`
- On send failure: auto-release Redis cooldown lock for retry

### Backend: Auth Endpoints

**File**: `app/api/routes/auth.py` (additions only, existing endpoints unchanged)

New endpoints:

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/auth/send-sms` | POST | Send OTP (risk check → generate → Redis store → async SMS) |
| `/auth/login/sms` | POST | OTP login (verify → auto-register/lookup → issue dual tokens) |
| `/auth/login/password` | POST | Password login (risk check → verify → issue dual tokens) |
| `/auth/refresh` | POST | Silent refresh (Cookie RT → validate session → new AT) |
| `/auth/logout` | POST | Logout (revoke session + clear cookies) |
| `/auth/sessions` | GET | List active sessions for current user |
| `/auth/sessions/{id}/revoke` | POST | Revoke a specific session (kick device) |

**Auto-register behavior** (for `/auth/login/sms` with new phone):
- Create User with `email=f"{phone}@phone.placeholder"`, `hashed_password=None`, `phone_number=phone`
- This placeholder email allows the NOT NULL constraint to pass; user can set real email later
- The `hashed_password=None` is valid (Phase 1 made it nullable)

**Dual-token issuance flow** (unified for all login endpoints):

1. Generate Access Token (JWT, 15min expiry)
2. Generate Refresh Token (`secrets.token_urlsafe(64)`)
3. Store `hash_refresh_token(rt)` in `active_sessions` table with device info
4. Set two httpOnly cookies: `access_token` (15min) + `refresh_token` (7 days)
5. Response body also returns `access_token` for SSE/WebSocket compatibility

**Cookie settings**:
- `HttpOnly=True` — JS cannot read
- `Secure=settings.SECURE_COOKIES` — True in production (HTTPS only)
- `SameSite=Lax` — CSRF protection
- `Path=/api` — scoped to API routes

### Backend: Config Additions

**File**: `app/core/config.py`

New settings:
- `ACCESS_TOKEN_EXPIRE_MINUTES: int = 15` (changed from 10080; only affects new endpoints)
- Note: existing `/login` endpoint retains its own 7-day AT logic — we do not modify it
- `ALIYUN_ACCESS_KEY_ID: str = ""`
- `ALIYUN_ACCESS_KEY_SECRET: str = ""`
- `ALIYUN_SMS_SIGN_NAME: str = "Autonome"`
- `ALIYUN_SMS_TEMPLATE_CODE: str = ""`

### Frontend: Login Page

**File**: `src/app/login/page.tsx`

- Three-tab layout: SMS login / Password login / Email login (backward compat)
- SMS tab: phone input + OTP input + 60s countdown send button
- Password tab: phone + password (for users who set passwords)
- Email tab: existing email+password flow (unchanged logic)
- On login success: redirect to `/` (cookies set automatically by browser)

### Frontend: API Client

**File**: `src/lib/api.ts`

- Add `credentials: 'include'` to all fetch calls (auto-send cookies)
- 401 interceptor: pause request queue → call `/auth/refresh` → retry with new AT
- Concurrent refresh lock: single refresh at a time, queue others
- On refresh failure: clear state, redirect to `/login`
- Remove manual `Authorization: Bearer` header injection (cookie handles it)
- Keep `getToken()` for SSE/WebSocket that need explicit token

### Frontend: Auth Store

**File**: `src/store/useAuthStore.ts`

- Remove `token` from localStorage persist (cookies manage tokens)
- Add `phone_number`, `is_email_verified`, `is_2fa_enabled` to user interface
- `logout()` calls `/auth/logout` endpoint then clears local state
- `fetchProfile()` updates user info from `/auth/me`

## Compatibility Guarantees

1. Existing `/register` and `/login` endpoints are **not modified**
2. Existing email+password login flow works unchanged
3. New endpoints are additive — no existing code is altered
4. Frontend login page retains email+password as a tab
5. All existing API calls continue to work (cookie-based auth is transparent)

## Files Changed

| File | Action | Description |
|------|--------|-------------|
| `app/services/risk_control.py` | Create | Redis-backed risk control engine |
| `app/services/sms_service.py` | Create | Aliyun SMS service wrapper |
| `app/api/routes/auth.py` | Modify | Add 7 new endpoints |
| `app/core/config.py` | Modify | Add Aliyun config + change AT expiry |
| `app/core/security.py` | Modify | Add cookie helper functions |
| `src/app/login/page.tsx` | Modify | Three-tab login UI |
| `src/lib/api.ts` | Modify | Cookie-based auth + 401 refresh interceptor |
| `src/store/useAuthStore.ts` | Modify | Cookie mode + new user fields |
| `requirements.txt` | Modify | Add alibabacloud SMS SDK |

## Verification

1. **Rate limiting**: Rapidly call `/auth/send-sms` → should get 429 after limits
2. **OTP flow**: Send SMS → receive code → login → get cookies → access protected API
3. **Auto-register**: New phone number → login → User record created in DB
4. **Backward compat**: Existing email+password login still works
5. **Token refresh**: Set AT expiry to 1min → wait → click → auto-refresh, no interruption
6. **Cookie security**: `document.cookie` in browser console should NOT show tokens
7. **Session management**: Login on two browsers → see both in `/auth/sessions` → revoke one → kicked
