"""
Twilio Signature Helper & Test Utility.

Computes and verifies Twilio X-Twilio-Signature headers for webhook calls,
accounting for reverse-proxy URL rewriting, HTTPS termination, and query parameters.
"""

import argparse
import base64
import hashlib
import hmac
import os
import re
import sys
from typing import Any, Dict, List, Optional


def compute_twilio_signature(url: str, params: Dict[str, Any], auth_token: str) -> str:
    """
    Compute Twilio HMAC-SHA1 signature according to Twilio specification:
    1. Start with the full webhook URL (including scheme, host, path, query).
    2. Sort POST parameter keys alphabetically.
    3. Append each key and its value to the URL string with no delimiter.
    4. Compute HMAC-SHA1 digest using auth_token as key.
    5. Return base64-encoded string.
    """
    s = url
    if params:
        for key in sorted(params.keys()):
            val = params[key]
            if val is not None:
                s += f"{key}{val}"

    mac = hmac.new(auth_token.encode("utf-8"), s.encode("utf-8"), hashlib.sha1)
    return base64.b64encode(mac.digest()).decode("utf-8").strip()


def get_candidate_urls(url: str) -> List[str]:
    """
    Generate candidate URLs to handle reverse proxy transformations
    (Nginx SSL termination, port stripping, http/https rewriting).
    """
    candidates = [url]
    if url.startswith("http://"):
        candidates.append("https://" + url[7:])
    elif url.startswith("https://"):
        candidates.append("http://" + url[8:])

    for u in list(candidates):
        clean_u = re.sub(r":(8000|80|443)", "", u)
        if clean_u not in candidates:
            candidates.append(clean_u)

    return candidates


def verify_twilio_signature(
    url: str,
    params: Dict[str, Any],
    signature: str,
    auth_token: str,
    check_candidates: bool = True,
) -> bool:
    """
    Verify incoming Twilio signature against expected URL and candidate variations.
    """
    if not auth_token or not signature:
        return False

    urls_to_test = get_candidate_urls(url) if check_candidates else [url]

    for cand_url in urls_to_test:
        expected = compute_twilio_signature(cand_url, params, auth_token)
        if hmac.compare_digest(expected, signature):
            return True

    return False


def main():
    parser = argparse.ArgumentParser(description="Twilio Webhook Signature Generator & Validator")
    parser.add_argument("--url", required=True, help="Full webhook URL (e.g. https://api.kodewaves.in/api/v1/telephony/twiml)")
    parser.add_argument("--token", required=True, help="Twilio Auth Token")
    parser.add_argument("--sig", help="X-Twilio-Signature to verify (if verifying)")
    parser.add_argument("--param", action="append", help="POST parameter in key=value format (can repeat)")
    parser.add_argument("--verify", action="store_true", help="Verify signature instead of computing")

    args = parser.parse_args()

    params: Dict[str, Any] = {}
    if args.param:
        for p in args.param:
            if "=" in p:
                k, v = p.split("=", 1)
                params[k] = v
            else:
                params[p] = ""

    if args.verify:
        if not args.sig:
            print("ERROR: --sig is required when --verify is specified.", file=sys.stderr)
            sys.exit(1)
        valid = verify_twilio_signature(args.url, params, args.sig, args.token)
        if valid:
            print("[PASS] Signature is VALID.")
            sys.exit(0)
        else:
            print("[FAIL] Signature is INVALID.", file=sys.stderr)
            sys.exit(1)
    else:
        sig = compute_twilio_signature(args.url, params, args.token)
        print(f"Computed X-Twilio-Signature: {sig}")
        candidates = get_candidate_urls(args.url)
        if len(candidates) > 1:
            print("\nCandidate signatures (for proxy resilience):")
            for c in candidates:
                cand_sig = compute_twilio_signature(c, params, args.token)
                print(f"  {c} -> {cand_sig}")


if __name__ == "__main__":
    main()
