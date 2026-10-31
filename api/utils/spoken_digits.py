"""Unambiguous standalone digit words used in supported Indian languages.

Forms are based on Unicode CLDR's locale-specific number spellout rules:
https://github.com/unicode-org/cldr/tree/main/common/rbnf
This is not a general number, date, or speech-recognition parser.
"""

REGIONAL_SPOKEN_DIGITS = {
    # Bengali
    "শূন্য": "0", "এক": "1", "দুই": "2", "তিন": "3", "চার": "4",
    "পাঁচ": "5", "ছয়": "6", "সাত": "7", "আট": "8", "নয়": "9",
    # Tamil
    "பூஜ்யம்": "0", "ஒன்று": "1", "இரண்டு": "2", "மூன்று": "3", "நான்கு": "4",
    "ஐந்து": "5", "ஆறு": "6", "ஏழு": "7", "எட்டு": "8", "ஒன்பது": "9",
    # Telugu
    "సున్నా": "0", "ఒకటి": "1", "రెండు": "2", "మూడు": "3", "నాలుగు": "4",
    "ఐదు": "5", "ఆరు": "6", "ఏడు": "7", "ఎనిమిది": "8", "తొమ్మిది": "9",
    # Kannada
    "ಸೊನ್ನೆ": "0", "ಒಂದು": "1", "ಎರಡು": "2", "ಮೂರು": "3", "ನಾಲ್ಕು": "4",
    "ಐದು": "5", "ಆರು": "6", "ಏಳು": "7", "ಎಂಟು": "8", "ಒಂಬತ್ತು": "9",
    # Malayalam: use the standalone form ഒന്ന് rather than the article ഒരു.
    "പൂജ്യം": "0", "ഒന്ന്": "1", "രണ്ട്": "2", "മൂന്ന്": "3", "നാല്": "4",
    "അഞ്ച്": "5", "ആറ്": "6", "ഏഴ്": "7", "എട്ട്": "8", "ഒൻപത്": "9",
    # Punjabi (Gurmukhi)
    "ਸਿਫ਼ਰ": "0", "ਇੱਕ": "1", "ਦੋ": "2", "ਤਿੰਨ": "3", "ਚਾਰ": "4",
    "ਪੰਜ": "5", "ਛੇ": "6", "ਸੱਤ": "7", "ਅੱਠ": "8", "ਨੌਂ": "9",
    # Marathi forms that differ from the Hindi entries already in the parser.
    "दोन": "2", "पाच": "5", "सहा": "6", "नऊ": "9",
    # Nepali standalone forms from Unicode CLDR's spellout-numbering rules.
    # These differ enough from common Hindi spellings to merit explicit aliases.
    "शुन्य": "0", "दुई": "2", "तिन": "3", "पाँच": "5", "छ": "6",
}
