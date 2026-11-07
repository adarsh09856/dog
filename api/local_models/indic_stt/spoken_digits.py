"""Exact phone-digit lexicon shared by call capture and Indic STT rescue.

These are standalone digit words, not a general number parser. Keep aliases
exact: fuzzy token splitting can silently invent contact digits.
"""

REGIONAL_SPOKEN_DIGITS = {
    # Assamese (Assamese script; Assamese forms that differ from Bengali).
    "শূন্য": "0", "শূণ্য": "0", "এক": "1", "দুই": "2", "তিনি": "3", "চাৰি": "4",
    "পাঁচ": "5", "পাচ": "5", "ছয়": "6", "সাত": "7", "আঠ": "8",
    "নয়": "9", "নয়": "9",
    # Bengali.
    "শূন্য": "0", "এক": "1", "দুই": "2", "তিন": "3", "চার": "4",
    "পাঁচ": "5", "ছয়": "6", "সাত": "7", "আট": "8", "নয়": "9",
    # Bodo (Devanagari spellings of the standalone number words).
    "लाथिखो": "0", "लाथिख'": "0", "से": "1", "नै": "2", "थाम": "3",
    "ब्रै": "4", "बा": "5", "द'": "6", "द": "6", "स्नि": "7", "दाइन": "8",
    "गु": "9",
    # Dogri (Devanagari).
    "शून्य": "0", "इक": "1", "द'ऊं": "2", "त्रै": "3", "चार": "4",
    "पंज": "5", "छे": "6", "सत्त": "7", "अट्ठ": "8", "नौ": "9",
    # Tamil.
    "பூஜ்யம்": "0", "ஒன்று": "1", "இரண்டு": "2", "மூன்று": "3", "நான்கு": "4",
    "ஐந்து": "5", "ஆறு": "6", "ஏழு": "7", "எட்டு": "8", "ஒன்பது": "9",
    # Telugu.
    "సున్నా": "0", "ఒకటి": "1", "రెండు": "2", "మూడు": "3", "నాలుగు": "4",
    "ఐదు": "5", "ఆరు": "6", "ఏడు": "7", "ఎనిమిది": "8", "తొమ్మిది": "9",
    # Kannada.
    "ಸೊನ್ನೆ": "0", "ಒಂದು": "1", "ಎರಡು": "2", "ಮೂರು": "3", "ನಾಲ್ಕು": "4",
    "ಐದು": "5", "ಆರು": "6", "ಏಳು": "7", "ಎಂಟು": "8", "ಒಂಬತ್ತು": "9",
    # Malayalam: use the standalone form ഒന്ന് rather than the article ഒരു.
    "പൂജ്യം": "0", "ഒന്ന്": "1", "രണ്ട്": "2", "മൂന്ന്": "3", "നാല്": "4",
    "അഞ്ച്": "5", "ആറ്": "6", "ഏഴ്": "7", "എട്ട്": "8", "ഒൻപത്": "9",
    # Punjabi (Gurmukhi).
    "ਸਿਫ਼ਰ": "0", "ਇੱਕ": "1", "ਦੋ": "2", "ਤਿੰਨ": "3", "ਚਾਰ": "4",
    "ਪੰਜ": "5", "ਛੇ": "6", "ਸੱਤ": "7", "ਅੱਠ": "8", "ਨੌਂ": "9",
    # Marathi forms that differ from the Hindi entries.
    "दोन": "2", "पाच": "5", "सहा": "6", "नऊ": "9",
    # Nepali aliases that differ from common Hindi spellings.
    "शुन्य": "0", "दुई": "2", "तिन": "3", "पाँच": "5", "छ": "6",
    # Common Romanized Nepali forms. These are used only inside an active
    # phone slot; exact matching avoids splitting ordinary English words.
    "shunya": "0", "dui": "2", "tin": "3", "chha": "6",
    # Maithili (Devanagari), including its common short forms.
    "शून्य": "0", "एक": "1", "दू": "2", "तीन": "3", "चारि": "4",
    "पाँच": "5", "छौ": "6", "छः": "6", "सात": "7", "आठ": "8", "नौ": "9",
    # Sanskrit standalone cardinal forms (several inflect by gender).
    "शून्यम्": "0", "एकम्": "1", "द्वि": "2", "द्वे": "2", "द्वौ": "2",
    "त्रि": "3", "त्रयः": "3", "त्रय": "3", "त्रीणि": "3", "तिस्रः": "3",
    "चतुर्": "4", "चत्वारि": "4", "चत्वारः": "4", "चतस्रः": "4",
    "पञ्च": "5", "पंच": "5", "षट्": "6", "षट": "6", "षड्": "6",
    "सप्त": "7", "अष्ट": "8", "नव": "9",
}

# Language-independent and ASR-phonetic spellings already accepted by the
# phone slot. The joined aliases are observed exact decoder outputs; no fuzzy
# segmentation is performed.
PHONE_SPOKEN_DIGITS = {
    **REGIONAL_SPOKEN_DIGITS,
    # Common Romanized Hindi forms emitted by multilingual STT for Hinglish
    # phone dictation. Exact-token matching is safe because parsing only runs
    # inside an active phone slot.
    "shunya": "0", "shoonya": "0", "ek": "1", "ikk": "1",
    "do": "2", "doh": "2", "teen": "3", "tin": "3",
    "char": "4", "chaar": "4", "panch": "5", "paanch": "5",
    "cheh": "6", "chhe": "6", "saat": "7", "aath": "8",
    "ath": "8", "nau": "9", "nao": "9",
    "zero": "0", "oh": "0", "शून्य": "0", "जीरो": "0", "ज़ीरो": "0",
    "one": "1", "एक": "1", "वन": "1", "ओन": "1", "two": "2", "दो": "2", "टू": "2",
    "three": "3", "तीन": "3", "थ्री": "3", "four": "4", "चार": "4", "फोर": "4",
    "five": "5", "पांच": "5", "पाँच": "5", "फाइव": "5",
    "six": "6", "छह": "6", "सिक्स": "6", "seven": "7", "सात": "7", "सेवन": "7",
    "eight": "8", "आठ": "8", "एट": "8", "ऐट": "8", "nine": "9", "नौ": "9", "नाइन": "9",
    "नीन": "9", "निन": "9", "नान": "9", "नाईन": "9", "थी": "3", "आइट": "8", "आईट": "8",
    "on": "1", "run": "1", "won": "1", "wan": "1",
    "फोरन": "41", "नाइनफोर": "94",
    "ફોરન": "41", "નાઇનફોર": "94",
    "નાઇન": "9", "નાઈટ": "9", "ફાઇવ": "5", "ફાઈવ": "5",
    "થ્રી": "3", "એઇટ": "8", "એઈટ": "8", "ફોર": "4", "વન": "1",
    "જીરો": "0", "ઝીરો": "0", "நைன்": "9", "ஜீரோ": "0", "ஜிரோ": "0",
    "ஃபோர்": "4", "ஃபைவ்": "5", "பைவ்": "5", "த்ரீ": "3", "எய்ட்": "8",
    "ஏய்ட்": "8", "ஏஐட்": "8",
}

# These homophones are accepted by call capture only as an uncertain "one";
# keep them out of STT candidate scoring so they cannot inflate a rescue score.
PHONE_SCORING_DIGITS = {
    **{
        word: digit for word, digit in PHONE_SPOKEN_DIGITS.items()
        if word not in {"on", "run", "won", "wan"}
    },
    "double": "double", "डबल": "double", "ડબલ": "double", "டபுள்": "double",
}


def count_spoken_phone_digits(text: str) -> int:
    """Count exact spoken digit groups for STT candidate comparison."""
    import re

    tokens = [
        token.strip("()[]{}\"")
        for token in re.split(r"[\s,.!?।॥:;\-–—]+", str(text or "").casefold())
        if token.strip("()[]{}\"")
    ]
    count = 0
    repeat_next = False
    for token in tokens:
        if token.isdecimal():
            count += len(token)
            repeat_next = False
            continue
        value = PHONE_SCORING_DIGITS.get(token)
        if value == "double":
            repeat_next = True
        elif value is not None:
            count += 2 if repeat_next else (len(value) if value.isdecimal() else 0)
            repeat_next = False
        else:
            repeat_next = False
    return count
