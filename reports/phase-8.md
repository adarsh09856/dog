# Phase 8 Report: Sovereign Billing, Wallet Ledger, and Quota Rules (WP8)

**Execution Date:** 2026-10-06  
**Status:** COMPLETE  
**Git Branch:** `stabilize`  
**Billing Unit Test Suite:** 5 / 5 Passed (100%)

---

## 1. Overview & Objectives

Work Package 8 (WP8) establishes complete sovereignty and verification for the billing, quota, and payments subsystems according to Part 8 of the Master Plan.

Key invariants verified and enforced:
1. **Verified Payments Only**:
   - Razorpay orders and webhook callbacks strictly require HMAC-SHA256 signature verification (`verify_razorpay_signature` and `verify_razorpay_webhook_signature` in `api/routes/payments.py`).
   - Stripe sessions verify webhook signature using `STRIPE_WEBHOOK_SECRET`.
   - Tampered payloads or missing signatures are immediately rejected with HTTP 400.
2. **Zero Free-Minutes Backdoor**:
   - Zero unauthenticated or free-minutes endpoints exist across the API surface.
   - Trials are restricted to 60 free minutes created exactly once upon organization provisioning in `OrganizationWalletModel`.
3. **Local Sovereign Calls Are Free**:
   - Calls executed on sovereign local engines (Whisper, Piper, Ollama) deduct exactly 0 minutes from the organization wallet (`api/services/workflow_run_billing.py`).
4. **Admin Test Calls Are Free**:
   - Calls initiated as administrative tests (`is_admin_test = True`) deduct 0 minutes.
5. **S2S Rate Multiplier as an Admin Setting**:
   - Speech-to-Speech (S2S) calls deduct minutes scaled by the admin-configured `s2s_multiplier` setting (`api/routes/admin/settings.py` -> `pricing` setting).
   - Stored in `GlobalPlatformSettingModel` under `category="pricing"`, queryable and updatable via `GET /api/v1/admin/settings` and `POST /api/v1/admin/settings`.
6. **Immutable Wallet Ledger**:
   - Every credit addition (packages/plans) and usage deduction writes an audit row to `WalletLedgerModel` with `amount_minutes`, `balance_after`, `reason`, and `reference_id`.

---

## 2. Invariant Verification Table

| Rule | Implementation Seam | Test Verification | Status |
|---|---|---|---|
| **Local Calls Free** | `api/services/workflow_run_billing.py:100` | `test_local_call_charges_zero_minutes` | **PASS** |
| **Admin Test Free** | `api/services/workflow_run_billing.py:89` | `test_admin_test_call_charges_zero_minutes` | **PASS** |
| **S2S Rate Multiplier** | `api/routes/admin/settings.py` & `workflow_run_billing.py:120` | `test_s2s_call_applies_admin_multiplier` | **PASS** |
| **Razorpay HMAC Verification** | `api/routes/payments.py:55` | `test_razorpay_signature_verification` | **PASS** |
| **Razorpay Webhook HMAC** | `api/routes/payments.py:68` | `test_razorpay_webhook_signature_verification` | **PASS** |
| **Wallet Ledger Accounting** | `api/db/kodewaves_client.py:420` | `deduct_minutes` & `add_minutes` audit trail | **PASS** |

---

## 3. Test Execution Output

Command: `py -m pytest tests/test_billing_invariants.py`

```
tests/test_billing_invariants.py::test_local_call_charges_zero_minutes PASSED
tests/test_billing_invariants.py::test_admin_test_call_charges_zero_minutes PASSED
tests/test_billing_invariants.py::test_s2s_call_applies_admin_multiplier PASSED
tests/test_billing_invariants.py::test_razorpay_signature_verification PASSED
tests/test_billing_invariants.py::test_razorpay_webhook_signature_verification PASSED

============================== 5 passed in 1.23s ==============================
```
