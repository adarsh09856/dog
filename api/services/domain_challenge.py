"""Verify client license domain control through a DNS TXT challenge."""

import hashlib
import hmac

import dns.asyncresolver
import dns.exception


def challenge_record_name(domain: str) -> str:
    return f"_kodewaves-verification.{domain}"


async def dns_proves_domain(domain: str, expected_token_sha256: str) -> bool:
    # Query public resolvers from the owner service, not a split-horizon or
    # client-controlled local resolver, and use an absolute DNS name.
    resolver = dns.asyncresolver.Resolver(configure=False)
    resolver.nameservers = ["1.1.1.1", "8.8.8.8"]
    try:
        records = await resolver.resolve(f"{challenge_record_name(domain)}.", "TXT", lifetime=5.0)
    except dns.exception.DNSException:
        return False
    for record in records:
        try:
            value = b"".join(record.strings).decode("ascii")
        except (AttributeError, UnicodeError):
            continue
        prefix = "kodewaves-verification="
        if not value.startswith(prefix):
            continue
        actual = hashlib.sha256(value[len(prefix):].encode("ascii")).hexdigest()
        if hmac.compare_digest(actual, expected_token_sha256):
            return True
    return False
