# Voice Agent Hub - Technical Debt & Issues

**Last Updated:** 2026-03-19
**Total Issues:** 26

---

## 🔴 CRITICAL - Immediate (Before Production)

### Security Vulnerabilities

- [x] **Issue #1: XSS Vulnerability in Device Auth Verification Page** (HIGH SEVERITY) ✅ FIXED
  - **File:** `backend/main.py:91-148`
  - **Problem:** Device code directly interpolated into HTML/JavaScript without escaping
  - **Risk:** Code injection, XSS attacks
  - **Fix:** Use `html.escape()` for HTML context and JSON serialization for JavaScript context
  ```python
  # BAD
  <div class="code">{code}</div>
  code: '{code}',

  # GOOD
  from html import escape
  <div class="code">{escape(code)}</div>
  code: {json.dumps(code)},
  ```

- [x] **Issue #3: Hardcoded Default Secret in Makefile** (MEDIUM SEVERITY) ✅ FIXED
  - **File:** `Makefile:26`
  - **Problem:** Default `HUB_SECRET` in version control enables token forgery
  - **Risk:** Anyone with repo access can forge authentication tokens
  - **Fix:** Remove default; fail loudly if HUB_SECRET not set
  ```makefile
  # Remove this line:
  HUB_SECRET=$(or $(HUB_SECRET),6c20986d23d3010a2ed87b3f72c6eb63b4eaf62d88570056d598fd068ad22145)

  # Add validation instead:
  ifndef HUB_SECRET
  $(error HUB_SECRET environment variable must be set)
  endif
  ```

- [x] **Issue #4: Encryption Key Auto-Generation** (HIGH SEVERITY) ✅ FIXED
  - **File:** `backend/config.py:7-14`
  - **Problem:** Generates ephemeral encryption key if not set, causing permanent data loss on restart
  - **Risk:** All encrypted API keys become inaccessible after restart
  - **Fix:** Fail hard with error instead of generating ephemeral key
  ```python
  def _get_encryption_key() -> str:
      key = os.getenv("HUB_ENCRYPTION_KEY")
      if not key:
          raise RuntimeError(
              "HUB_ENCRYPTION_KEY must be set in environment. "
              "Generate one with: python -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())'"
          )
      return key
  ```

- [x] **Issue #2: Overly Broad Exception Handling in Database Init** (MEDIUM SEVERITY) ✅ FIXED
  - **File:** `backend/database.py:26`
  - **Problem:** `except Exception: pass` swallows all errors including corruption, permission issues
  - **Risk:** Silent failures, impossible debugging, data corruption
  - **Fix:** Catch specific exceptions only
  ```python
  for sql in migrations:
      try:
          await conn.execute(text(sql))
      except sqlalchemy.exc.OperationalError:
          pass  # Column already exists
  ```

---

## 🟡 HIGH PRIORITY - This Sprint

### Bugs & Reliability

- [x] **Issue #5: Device Code Expiry Mismatch** ✅ FIXED
  - **Files:** `backend/auth.py:8`, `backend/main.py:54,70`
  - **Problem:** Inconsistent expiry time definition (900s vs 300s)
  - **Fix:** Ensure consistency across codebase
  ```python
  # Standardize to 15 minutes everywhere:
  DEVICE_CODE_EXPIRES = timedelta(seconds=900)
  expires_in: int = 900
  ```

- [x] **Issue #6: Race Condition in Device Code Approval** ✅ ALREADY FIXED
  - **File:** `backend/main.py:157-187`
  - **Problem:** No check preventing duplicate approvals of same device code
  - **Risk:** Concurrent requests could cause inconsistent state
  - **Fix:** Add check for already-approved state before processing
  ```python
  if device.approved:
      raise HTTPException(status_code=400, detail="Device code already approved")
  device.approved = True
  # ... rest of logic
  ```

- [x] **Issue #7: Missing Input Validation on Email & Name** ✅ FIXED
  - **File:** `backend/main.py:151-155`
  - **Problem:** No length limits, format validation, or sanitization
  - **Risk:** Unicode/homograph attacks, buffer issues, invalid data
  - **Fix:** Add Pydantic validators
  ```python
  from pydantic import EmailStr, Field

  class VerifyBody(BaseModel):
      code: str = Field(..., regex=r'^[0-9a-f]{32}$')
      email: EmailStr
      name: str = Field(..., min_length=1, max_length=255, strip_whitespace=True)
  ```

- [x] **Issue #10: Missing Transaction Error Handling in Agent Registration** ✅ FIXED
  - **File:** `backend/main.py:205-244`
  - **Problem:** No try-except around commit/refresh operations
  - **Risk:** Confusing error messages, inconsistent database state
  - **Fix:** Add proper error handling with rollback
  ```python
  try:
      db.add(reg)
      await db.commit()
      await db.refresh(reg)
  except Exception as e:
      await db.rollback()
      raise HTTPException(status_code=500, detail=f"Failed to register agent: {str(e)}")
  ```

- [ ] **Issue #11: Null/Optional Field Never Checked in Call Dispatch**
  - **File:** `backend/main.py:296-307`
  - **Problem:** Background agent dispatch fails silently if credentials invalid
  - **Risk:** Agent never joins call, user hears nothing
  - **Fix:** Validate credentials before dispatch, add error logging
  ```python
  async def _dispatch_agent(...):
      if not all([lk_url, lk_key, lk_secret, agent_name]):
          logger.error(f"Invalid credentials for agent dispatch to {room_name}")
          return

      try:
          await asyncio.sleep(1.5)
          async with livekit_api.LiveKitAPI(...) as lk:
              await lk.agent_dispatch.create_dispatch(...)
      except Exception as e:
          logger.error(f"Agent dispatch failed for {room_name}: {e}")
  ```

### Code Quality

- [ ] **Issue #14: No Logging Throughout Backend**
  - **Files:** All backend modules
  - **Problem:** Zero logging statements; critical warnings use print()
  - **Risk:** No audit trail, impossible to debug production issues
  - **Fix:** Add structured logging
  ```python
  import logging
  logger = logging.getLogger(__name__)

  # Add logging for:
  # - Authentication attempts (success/failure)
  # - API key operations (encrypt/decrypt)
  # - Database errors
  # - Background task failures
  # - Admin operations
  ```
  - Locations to add logging:
    - `backend/main.py`: Auth endpoints, agent registration, connect endpoint
    - `backend/auth.py`: Token generation, validation
    - `backend/crypto.py`: Encryption operations
    - `backend/database.py`: Migration failures, deduplication

- [x] **Issue #13: Print Statement for Critical Warnings** ✅ FIXED
  - **File:** `backend/config.py:10-12`
  - **Problem:** Critical security warning uses print() and exposes encryption key
  - **Fix:** Replace with logging.error() (removed as part of Issue #4 fix)

- [ ] **Issue #20: Missing Database Indexes**
  - **File:** `backend/models.py`
  - **Problem:** No indexes on frequently queried fields
  - **Risk:** Slow queries as dataset grows
  - **Fix:** Add indexes to User.email, AgentRegistration.user_id, DeviceCode.code
  ```python
  class User(Base):
      email: Mapped[str] = mapped_column(String, unique=True, nullable=False, index=True)

  class AgentRegistration(Base):
      user_id: Mapped[str] = mapped_column(String, ForeignKey("users.id"), nullable=False, index=True)

  class DeviceCode(Base):
      code: Mapped[str] = mapped_column(String, primary_key=True, index=True)
  ```

---

## 🟠 MEDIUM PRIORITY - Next Sprint

### Security Improvements

- [ ] **Issue #8: SQL Injection Risk from LIKE Pattern**
  - **File:** `backend/database.py:50-55`
  - **Problem:** Uses raw SQL with text() for deletion
  - **Fix:** Use parameterized SQLAlchemy queries
  ```python
  from sqlalchemy import delete
  stmt = delete(User).where(User.email.like('inttest-%@example.com'))
  await conn.execute(stmt)
  ```

- [ ] **Add Rate Limiting to Auth Endpoints**
  - Auth endpoints (`/auth/device`, `/auth/verify`, `/auth/device/token`) have no rate limiting
  - Risk: Brute force attacks, DoS
  - Consider: slowapi or fastapi-limiter

### Performance

- [ ] **Issue #9: Inefficient Deduplication Query**
  - **File:** `backend/database.py:37-47`
  - **Problem:** O(n²) nested correlated subqueries
  - **Fix:** Use window functions or simpler logic
  ```python
  # Use ROW_NUMBER() window function instead:
  DELETE FROM agent_registrations
  WHERE id IN (
      SELECT id FROM (
          SELECT id, ROW_NUMBER() OVER (PARTITION BY user_id ORDER BY created_at DESC) as rn
          FROM agent_registrations
      ) WHERE rn > 1
  )
  ```

- [ ] **Issue #19: Hardcoded 1.5 Second Sleep Before Agent Dispatch**
  - **File:** `backend/main.py:299`
  - **Problem:** Arbitrary delay doesn't verify caller actually joined
  - **Fix:** Implement proper room state checking via LiveKit API
  ```python
  # Instead of sleep, poll room participants:
  async def _wait_for_participant(lk, room_name, timeout=5.0):
      start = time.time()
      while time.time() - start < timeout:
          room = await lk.room.get_room(room_name)
          if room.num_participants > 0:
              return True
          await asyncio.sleep(0.2)
      return False
  ```

### Infrastructure & Deployment

- [ ] **Issue #26: Auto-Deploy to Fly.io on Master Merge**
  - **Problem:** No automated deployment pipeline for production
  - **Fix:** Set up GitHub Actions to deploy to Fly.io on master merge
  - **Requirements:**
    - Production site: Deploy to main Fly app on master merge
    - Dev/staging site: Separate Fly app for testing interim changes
    - Secrets management: Store FLY_API_TOKEN in GitHub secrets
  ```yaml
  # .github/workflows/deploy.yml
  name: Deploy
  on:
    push:
      branches: [master]
  jobs:
    deploy:
      runs-on: ubuntu-latest
      steps:
        - uses: actions/checkout@v4
        - uses: superfly/flyctl-actions/setup-flyctl@master
        - run: flyctl deploy --remote-only
          env:
            FLY_API_TOKEN: ${{ secrets.FLY_API_TOKEN }}
  ```

### Code Organization

- [ ] **Issue #12: Inconsistent Error Response Format**
  - **Files:** Throughout `backend/main.py`
  - **Problem:** Some endpoints return `{"ok": true}`, others use HTTPException detail
  - **Fix:** Define standardized error response model
  ```python
  class ErrorResponse(BaseModel):
      error: str
      detail: Optional[str] = None

  class SuccessResponse(BaseModel):
      success: bool = True
      data: Optional[dict] = None
  ```

- [ ] **Issue #18: Code Duplication - Device Code HTML Generation**
  - **Files:** `backend/main.py:91-148`, `frontend/src/pages/Verify.tsx:66-121`
  - **Problem:** Nearly identical HTML forms duplicated
  - **Fix:** Move verification form to frontend only, use JSON API from backend
  - Backend should return JSON: `{"device_code": "...", "status": "pending|approved", "error": "..."}`
  - Frontend handles all rendering

### Testing

- [ ] **Issue #21: No Test for Device Code Duplicate Approval**
  - Add test: Concurrent approvals of same device code
  - Add test: Re-approval of already-approved device code

- [ ] **Issue #22: No Test for Encryption/Decryption Roundtrip Failure**
  - Add test: `/agent/config` endpoint when decryption fails
  - Add error handling for decryption failures

- [ ] **Issue #23: Missing Authorization Tests**
  - Add test: User A cannot access user B's agent configs via `/agent/config`
  - Add test: `/DELETE /admin/test-user` requires correct X-Hub-Secret
  - Add test: `/DELETE /admin/test-user` rejects invalid secret

- [ ] **Issue #24: Missing Timezone Tests**
  - Add test: Device code expiry with different timezone scenarios
  - Add test: UTC handling in datetime comparisons

### Frontend

- [ ] **Issue #17: Frontend Missing Error Boundary**
  - **File:** `frontend/src/App.tsx`
  - **Problem:** No error boundary for React component errors
  - **Risk:** LiveKitRoom errors crash entire app with blank screen
  - **Fix:** Add error boundary component
  ```typescript
  class ErrorBoundary extends React.Component<Props, State> {
      componentDidCatch(error: Error, errorInfo: React.ErrorInfo) {
          console.error('React error:', error, errorInfo);
      }
      render() {
          if (this.state.hasError) {
              return <div>Something went wrong. Please refresh.</div>;
          }
          return this.props.children;
      }
  }
  ```

- [ ] **Issue #15: Frontend Race Condition in Poll Cleanup**
  - **File:** `frontend/src/pages/Verify.tsx:40,17-38`
  - **Problem:** Missing dependency in useEffect, multiple polling intervals could run
  - **Fix:** Add `code` to dependency array
  ```typescript
  useEffect(() => {
      // ... polling logic
      return () => { if (pollRef.current) clearInterval(pollRef.current); };
  }, [code]); // Add code dependency
  ```

- [ ] **Issue #16: Frontend Unhandled Network Errors in Poll**
  - **File:** `frontend/src/pages/Verify.tsx:33-36`
  - **Problem:** All errors silently swallowed, user stuck in "waiting" state
  - **Fix:** Add logging and distinguish transient vs permanent errors
  ```typescript
  catch (error) {
      console.error('Poll error:', error);
      if (error instanceof TypeError) {
          // Network error - keep polling
      } else {
          setError('Connection failed. Please refresh.');
          clearInterval(pollRef.current);
      }
  }
  ```

---

## 🔵 LOW PRIORITY - Future

### Cleanup

- [ ] **Issue #25: Unused Google OAuth Configuration**
  - **File:** `backend/config.py:13-15`, `.env.example`
  - **Problem:** Commented-out dead code suggests incomplete OAuth integration
  - **Fix:** Remove unused Google OAuth references or complete the implementation

- [ ] **Deprecation Warning: FastAPI on_event**
  - **File:** `backend/main.py:41`
  - **Warning:** `@app.on_event("startup")` is deprecated
  - **Fix:** Migrate to lifespan event handlers
  ```python
  from contextlib import asynccontextmanager

  @asynccontextmanager
  async def lifespan(app: FastAPI):
      # Startup
      await init_db()
      yield
      # Shutdown (if needed)

  app = FastAPI(lifespan=lifespan)
  ```

### Documentation

- [ ] Add API documentation with OpenAPI/Swagger examples
- [ ] Document device code authentication flow with sequence diagram
- [ ] Add architecture diagram showing LiveKit integration
- [ ] Document encryption key rotation procedure
- [ ] Add troubleshooting guide for common issues

---

## Summary Statistics

| Category | Count | Critical | High | Medium | Low |
|----------|-------|----------|------|--------|-----|
| Security | 4 | 3 | 0 | 1 | 0 |
| Bugs | 7 | 0 | 5 | 2 | 0 |
| Code Quality | 9 | 0 | 2 | 4 | 3 |
| Performance | 2 | 0 | 0 | 2 | 0 |
| Testing | 4 | 0 | 0 | 4 | 0 |
| **Total** | **26** | **3** | **7** | **13** | **3** |

---

## Security Checklist

- [x] Authentication implemented (JWT + device flow)
- [x] Sensitive data encrypted (API keys)
- [ ] No XSS vulnerabilities (Issue #1)
- [x] No SQL injection (mostly safe with SQLAlchemy, except Issue #8)
- [ ] Secrets not in version control (Issue #3)
- [ ] Input validation complete (Issue #7)
- [ ] Rate limiting on auth endpoints
- [ ] Comprehensive audit logging (Issue #14)
- [x] CORS configured appropriately
- [ ] Error messages don't leak sensitive info

---

## Notes

- **Before deploying to production:** Complete all CRITICAL issues
- **Test thoroughly:** Add integration tests for all security fixes
- **Monitor:** Set up logging aggregation and alerting
- **Rotate secrets:** Generate new HUB_SECRET and HUB_ENCRYPTION_KEY for production
- **Backup:** Ensure DATABASE_URL and HUB_ENCRYPTION_KEY are backed up securely
