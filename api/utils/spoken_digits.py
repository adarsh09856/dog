"""Compatibility import for the shared exact phone-digit lexicon."""

from api.local_models.indic_stt.spoken_digits import (
    PHONE_SCORING_DIGITS,
    PHONE_SPOKEN_DIGITS,
    REGIONAL_SPOKEN_DIGITS,
    count_spoken_phone_digits,
)

__all__ = [
    "PHONE_SCORING_DIGITS",
    "PHONE_SPOKEN_DIGITS",
    "REGIONAL_SPOKEN_DIGITS",
    "count_spoken_phone_digits",
]
