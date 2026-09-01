#!/usr/bin/env bash
# End-to-end smoke test of the whole FR-01-35 user journey, run against a
# live server (default http://127.0.0.1:8000). Uses timestamp-suffixed
# emails so it's safe to re-run against the same dev database repeatedly.
#
#   uvicorn app.main:app &          # server must already be running
#   bash scripts/smoke_test.sh
#
# Exits non-zero on the first unexpected status code / field, printing
# what was expected vs what came back.

set -u
BASE="${BASE_URL:-http://127.0.0.1:8000}"
STAMP=$(date +%s)
PASS=0
FAIL=0

pass() { PASS=$((PASS+1)); echo "  OK: $1"; }
fail() { FAIL=$((FAIL+1)); echo "  FAIL: $1"; }
step() { echo; echo "== $1 =="; }

expect_status() {
  local desc="$1" expected="$2" actual="$3"
  if [ "$actual" = "$expected" ]; then pass "$desc (HTTP $actual)"; else fail "$desc (expected $expected, got $actual)"; fi
}

json_field() { python3 -c "import sys,json; print(json.load(sys.stdin).get('$1',''))"; }

# ---------------------------------------------------------------------------
step "0. Health check"
HTTP=$(curl -s -o /dev/null -w "%{http_code}" "$BASE/health")
expect_status "server is up" 200 "$HTTP"

# ---------------------------------------------------------------------------
step "1-4. Registration, login, profile (FR-01/02/03/04a)"
SENDER_EMAIL="smoke-sender-$STAMP@example.com"
SENDER_MOBILE="+2782${STAMP: -7}"

RESP=$(curl -s -w "\n%{http_code}" -X POST "$BASE/auth/register" -H "Content-Type: application/json" \
  -d "{\"full_name\":\"Smoke Sender\",\"email\":\"$SENDER_EMAIL\",\"mobile_number\":\"$SENDER_MOBILE\",\"password\":\"SmokePass123\"}")
expect_status "register sender" 201 "$(echo "$RESP" | tail -1)"

DUP=$(curl -s -o /dev/null -w "%{http_code}" -X POST "$BASE/auth/register" -H "Content-Type: application/json" \
  -d "{\"full_name\":\"Dup\",\"email\":\"$SENDER_EMAIL\",\"mobile_number\":\"+27000000000\",\"password\":\"SmokePass123\"}")
expect_status "duplicate email rejected" 409 "$DUP"

LOGIN=$(curl -s -X POST "$BASE/auth/login" -H "Content-Type: application/json" \
  -d "{\"email\":\"$SENDER_EMAIL\",\"password\":\"SmokePass123\"}")
TOKEN=$(echo "$LOGIN" | json_field access_token)
[ -n "$TOKEN" ] && pass "login returns access token" || fail "login returned no token"
AUTH="Authorization: Bearer $TOKEN"

PROFILE_HTTP=$(curl -s -o /dev/null -w "%{http_code}" "$BASE/users/me" -H "$AUTH")
expect_status "view own profile" 200 "$PROFILE_HTTP"

UPDATE_RESP=$(curl -s -X PATCH "$BASE/users/me" -H "$AUTH" -H "Content-Type: application/json" -d '{"full_name":"Smoke Sender Updated"}')
[ "$(echo "$UPDATE_RESP" | json_field full_name)" = "Smoke Sender Updated" ] && pass "profile update persisted" || fail "profile update did not persist"

# ---------------------------------------------------------------------------
step "5-9. KYC submit + admin review (FR-05-09a, FR-33)"
KYC_STATUS_BEFORE=$(curl -s "$BASE/kyc/me/status" -H "$AUTH" | json_field status)
[ "$KYC_STATUS_BEFORE" = "not_submitted" ] && pass "KYC status starts not_submitted" || fail "unexpected initial KYC status: $KYC_STATUS_BEFORE"

curl -s -X POST "$BASE/kyc" -H "$AUTH" -H "Content-Type: application/json" -d "{
  \"full_name\":\"Smoke Sender\",\"date_of_birth\":\"1990-01-01\",\"nationality\":\"South African\",
  \"identification_number\":\"9001015009087\",\"residential_address\":\"1 Test Street\",
  \"mobile_number\":\"$SENDER_MOBILE\",\"email_address\":\"$SENDER_EMAIL\",\"source_of_funds\":\"Salary\"
}" > /dev/null

KYC_STATUS_AFTER=$(curl -s "$BASE/kyc/me/status" -H "$AUTH" | json_field status)
[ "$KYC_STATUS_AFTER" = "pending" ] && pass "KYC status pending after submission" || fail "unexpected KYC status after submit: $KYC_STATUS_AFTER"

BLOCKED=$(curl -s -o /dev/null -w "%{http_code}" -X POST "$BASE/remittances" -H "$AUTH" -H "Content-Type: application/json" \
  -d '{"beneficiary_id":"whatever","zar_amount":"10.00"}')
expect_status "quote blocked before KYC approval (FR-09)" 403 "$BLOCKED"

ADMIN_EMAIL="ops-admin@example.com"
ADMIN_LOGIN=$(curl -s -X POST "$BASE/auth/login" -H "Content-Type: application/json" -d "{\"email\":\"$ADMIN_EMAIL\",\"password\":\"AdminPass123\"}")
ADMIN_TOKEN=$(echo "$ADMIN_LOGIN" | json_field access_token)
if [ -z "$ADMIN_TOKEN" ]; then
  fail "no admin account found - run: python -m scripts.create_admin \"Admin\" $ADMIN_EMAIL +27000000099 AdminPass123"
  echo; echo "Cannot continue without an admin. $PASS passed, $FAIL failed so far."; exit 1
fi
pass "admin login"
ADMIN_AUTH="Authorization: Bearer $ADMIN_TOKEN"

APP_ID=$(curl -s "$BASE/kyc?kyc_status=pending" -H "$ADMIN_AUTH" | python3 -c "
import sys, json
apps = json.load(sys.stdin)
match = [a for a in apps if a['email_address'] == '$SENDER_EMAIL']
print(match[0]['id'] if match else '')
")
[ -n "$APP_ID" ] && pass "admin sees pending application" || fail "admin did not see pending application"

curl -s -X POST "$BASE/kyc/$APP_ID/approve" -H "$ADMIN_AUTH" > /dev/null
KYC_STATUS_FINAL=$(curl -s "$BASE/kyc/me/status" -H "$AUTH" | json_field status)
[ "$KYC_STATUS_FINAL" = "approved" ] && pass "KYC approved (FR-08a reflects it)" || fail "KYC not approved: $KYC_STATUS_FINAL"

# ---------------------------------------------------------------------------
step "10-14. Beneficiary + recipient linking (FR-10-12c)"
RECIPIENT_EMAIL="smoke-recipient-$STAMP@example.com"
RECIPIENT_MOBILE="+2783${STAMP: -7}"

curl -s -X POST "$BASE/auth/register" -H "Content-Type: application/json" \
  -d "{\"full_name\":\"Smoke Recipient\",\"email\":\"$RECIPIENT_EMAIL\",\"mobile_number\":\"$RECIPIENT_MOBILE\",\"password\":\"SmokePass123\"}" > /dev/null

BEN_RESP=$(curl -s -X POST "$BASE/beneficiaries" -H "$AUTH" -H "Content-Type: application/json" -d "{
  \"full_name\":\"Smoke Recipient\",\"email_address\":\"$RECIPIENT_EMAIL\",
  \"country\":\"South Africa\",\"payout_currency\":\"USD\",\"relationship_to_sender\":\"Friend\"
}")
BEN_ID=$(echo "$BEN_RESP" | json_field id)
[ -n "$BEN_ID" ] && pass "beneficiary created" || fail "beneficiary creation failed"
[ "$(echo "$BEN_RESP" | json_field linked_user_id)" != "None" ] && pass "beneficiary auto-linked to existing recipient (FR-12a)" || fail "beneficiary did not auto-link"
[ "$(echo "$BEN_RESP" | json_field wallet_provisioned)" = "True" ] && pass "wallet provisioned on link (FR-12b)" || fail "wallet not provisioned on link"

# raise limits so this run's quote isn't blocked by prior smoke-test runs
curl -s -X PUT "$BASE/admin/limit-tiers/verified" -H "$ADMIN_AUTH" -H "Content-Type: application/json" \
  -d '{"daily_limit_zar":"100000000","monthly_limit_zar":"1000000000"}' > /dev/null

# ---------------------------------------------------------------------------
step "15-17. Quote, fees, limits (FR-13-17)"
LIMITS=$(curl -s "$BASE/limits/me" -H "$AUTH")
[ "$(echo "$LIMITS" | json_field tier)" = "verified" ] && pass "sender sees verified tier (FR-16a)" || fail "unexpected tier"

QUOTE=$(curl -s -X POST "$BASE/remittances" -H "$AUTH" -H "Content-Type: application/json" \
  -d "{\"beneficiary_id\":\"$BEN_ID\",\"zar_amount\":\"1000.00\"}")
RID=$(echo "$QUOTE" | json_field id)
[ -n "$RID" ] && pass "quote created (FR-14)" || fail "quote creation failed"
[ "$(echo "$QUOTE" | json_field status)" = "quoted" ] && pass "quote status is 'quoted'" || fail "unexpected quote status"

# ---------------------------------------------------------------------------
step "18-20. Simulated cash-in (FR-18-20)"
curl -s -X POST "$BASE/remittances/$RID/cash-in" -H "$AUTH" -H "Content-Type: application/json" \
  -d '{"method":"bank_transfer"}' > /dev/null
CONFIRM=$(curl -s -X POST "$BASE/remittances/$RID/confirm-cash-in" -H "$ADMIN_AUTH")
[ "$(echo "$CONFIRM" | json_field status)" = "settlement_queued" ] && pass "cash-in confirmed, settlement auto-queued (FR-19/20/21)" || fail "unexpected status after confirm: $(echo "$CONFIRM" | json_field status)"

# ---------------------------------------------------------------------------
step "21-26. Queue & Settlement - REAL XRPL Testnet transaction (FR-21-26)"
echo "  (this makes a real network call and may take several seconds)"
RUN_RESULT=$(curl -s -X POST "$BASE/admin/settlement/run" -H "$ADMIN_AUTH")
MSG_STATUS=$(echo "$RUN_RESULT" | python3 -c "import sys,json; r=json.load(sys.stdin); print(r[0]['status'] if r else 'NONE')")
if [ "$MSG_STATUS" = "completed" ]; then
  pass "settlement completed on real XRPL Testnet"
elif [ "$MSG_STATUS" = "failed" ]; then
  REASON=$(echo "$RUN_RESULT" | python3 -c "import sys,json; r=json.load(sys.stdin); print(r[0]['failure_reason'] if r else '')")
  fail "settlement failed (may be expected if platform wallet liquidity is exhausted): $REASON"
else
  fail "no settlement message was processed"
fi

REMITTANCE_AFTER=$(curl -s "$BASE/remittances/me" -H "$AUTH" | python3 -c "
import sys, json
rs = json.load(sys.stdin)
match = [r for r in rs if r['id'] == '$RID']
print(json.dumps(match[0]) if match else '{}')
")
TX_HASH=$(echo "$REMITTANCE_AFTER" | json_field xrpl_settlement_tx_hash)
[ -n "$TX_HASH" ] && [ "$TX_HASH" != "None" ] && pass "settlement tx hash recorded: $TX_HASH (FR-23)" || echo "  (no tx hash - only expected if settlement failed above)"

# ---------------------------------------------------------------------------
step "27-28. Recipient wallet + sender history (FR-27/28/28a)"
RECIPIENT_LOGIN=$(curl -s -X POST "$BASE/auth/login" -H "Content-Type: application/json" -d "{\"email\":\"$RECIPIENT_EMAIL\",\"password\":\"SmokePass123\"}")
RTOKEN=$(echo "$RECIPIENT_LOGIN" | json_field access_token)
RAUTH="Authorization: Bearer $RTOKEN"

WALLET=$(curl -s "$BASE/wallet/me" -H "$RAUTH")
WALLET_BALANCE=$(echo "$WALLET" | json_field balance_rlusd)
echo "  recipient wallet balance: $WALLET_BALANCE RLUSD"

HISTORY_COUNT=$(curl -s "$BASE/remittances/me" -H "$AUTH" | python3 -c "import sys,json; print(len(json.load(sys.stdin)))")
[ "$HISTORY_COUNT" -ge 1 ] && pass "sender sees own remittance history (FR-28a): $HISTORY_COUNT record(s)" || fail "sender history empty"

# ---------------------------------------------------------------------------
step "29-32, 35. Simulated cash-out (FR-09a, FR-29-32, FR-35)"
CO_BLOCKED=$(curl -s -o /dev/null -w "%{http_code}" -X POST "$BASE/cash-outs" -H "$RAUTH" -H "Content-Type: application/json" \
  -d '{"rlusd_amount":"1.000000","fiat_currency":"USD"}')
expect_status "cash-out blocked before recipient KYC (FR-09a)" 403 "$CO_BLOCKED"

curl -s -X POST "$BASE/kyc" -H "$RAUTH" -H "Content-Type: application/json" -d "{
  \"full_name\":\"Smoke Recipient\",\"date_of_birth\":\"1992-02-02\",\"nationality\":\"South African\",
  \"identification_number\":\"9202025009087\",\"residential_address\":\"2 Test Street\",
  \"mobile_number\":\"$RECIPIENT_MOBILE\",\"email_address\":\"$RECIPIENT_EMAIL\",\"source_of_funds\":\"Employment\"
}" > /dev/null
RECIPIENT_APP_ID=$(curl -s "$BASE/kyc?kyc_status=pending" -H "$ADMIN_AUTH" | python3 -c "
import sys, json
apps = json.load(sys.stdin)
match = [a for a in apps if a['email_address'] == '$RECIPIENT_EMAIL']
print(match[0]['id'] if match else '')
")
curl -s -X POST "$BASE/kyc/$RECIPIENT_APP_ID/approve" -H "$ADMIN_AUTH" > /dev/null

if python3 -c "exit(0 if float('$WALLET_BALANCE') >= 1 else 1)" 2>/dev/null; then
  CASHOUT=$(curl -s -X POST "$BASE/cash-outs" -H "$RAUTH" -H "Content-Type: application/json" \
    -d '{"rlusd_amount":"1.000000","fiat_currency":"USD"}')
  CO_ID=$(echo "$CASHOUT" | json_field id)
  [ -n "$CO_ID" ] && pass "cash-out requested (FR-30/31): payout \$$(echo "$CASHOUT" | json_field fiat_payout_amount)" || fail "cash-out request failed: $CASHOUT"

  if [ -n "$CO_ID" ]; then
    curl -s -X POST "$BASE/cash-outs/$CO_ID/approve" -H "$ADMIN_AUTH" > /dev/null
    COMPLETE=$(curl -s -X POST "$BASE/cash-outs/$CO_ID/complete" -H "$ADMIN_AUTH")
    [ "$(echo "$COMPLETE" | json_field status)" = "completed" ] && pass "cash-out lifecycle requested->approved->completed (FR-32/35)" || fail "cash-out did not complete"
  fi
else
  echo "  SKIPPED: recipient balance ($WALLET_BALANCE) too low to test cash-out - settlement above likely failed"
fi

# ---------------------------------------------------------------------------
step "Access control checks"
NON_ADMIN_BLOCKED=$(curl -s -o /dev/null -w "%{http_code}" "$BASE/kyc" -H "$AUTH")
expect_status "non-admin blocked from admin KYC list" 403 "$NON_ADMIN_BLOCKED"

curl -s -X POST "$BASE/auth/logout" -H "$AUTH" > /dev/null
POST_LOGOUT=$(curl -s -o /dev/null -w "%{http_code}" "$BASE/users/me" -H "$AUTH")
expect_status "session dead after logout (FR-02a)" 401 "$POST_LOGOUT"

# ---------------------------------------------------------------------------
echo
echo "=================================================="
echo "  $PASS passed, $FAIL failed"
echo "=================================================="
[ "$FAIL" -eq 0 ] && exit 0 || exit 1
