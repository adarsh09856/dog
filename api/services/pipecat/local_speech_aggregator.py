"""Avoid separate CPU synthesis requests for tiny adjacent sentences."""

import re
import unicodedata

from api.utils.spoken_digits import REGIONAL_SPOKEN_DIGITS

from pipecat.utils.text.base_text_aggregator import (
    Aggregation, AggregationType, BaseTextAggregator,
)
from pipecat.utils.text.simple_text_aggregator import SimpleTextAggregator


_NUMBER_AND_DATE_WORDS = frozenset({
    "zero", "oh", "one", "two", "three", "four", "five", "six", "seven",
    "eight", "nine", "ten", "eleven", "twelve", "thirteen", "fourteen",
    "fifteen", "sixteen", "seventeen", "eighteen", "nineteen", "twenty",
    "thirty", "forty", "fifty", "sixty", "seventy", "eighty", "ninety",
    "hundred", "thousand", "double", "triple", "first", "second", "third",
    "fourth", "fifth", "sixth", "seventh", "eighth", "ninth", "tenth",
    "eleventh", "twelfth", "thirteenth", "fourteenth", "fifteenth",
    "sixteenth", "seventeenth", "eighteenth", "nineteenth", "twentieth",
    "thirtieth", "january", "february", "march", "april", "may", "june",
    "july", "august", "september", "october", "november", "december",
    "शून्य", "जीरो", "ज़ीरो", "एक", "दो", "तीन", "चार", "पांच", "पाँच",
    "छह", "सात", "आठ", "नौ", "दस", "ग्यारह", "बारह", "बीस", "तीस",
    # Hindi cardinal forms from Unicode CLDR rbnf/hi.xml. Day and year words
    # must remain attached to their month/scale, just like English numbers.
    "तेरह", "चौदह", "पन्द्रह", "पंद्रह", "सोलह", "सत्रह", "अठारह", "उन्नीस",
    "इक्कीस", "बाईस", "तेईस", "चौबीस", "पच्चीस", "छब्बीस", "सत्ताईस",
    "अट्ठाईस", "अट्ठाइस", "अठाईस", "उनतीस", "इकतीस", "बत्तीस", "तैंतीस",
    "चौंतीस", "पैंतीस", "छत्तीस", "सैंतीस", "अड़तीस", "उनतालीस", "चालीस",
    "इकतालीस", "बयालीस", "तैंतालीस", "चौवालीस", "पैंतालीस", "छियालीस",
    "सैंतालीस", "अड़तालीस", "उनचास", "पचास", "इक्यावन", "बावन", "तिरेपन",
    "चौवन", "पचपन", "छप्पन", "सत्तावन", "अट्ठावन", "उनसठ", "साठ", "इकसठ",
    "बासठ", "तिरेसठ", "चौंसठ", "पैंसठ", "छियासठ", "सड़सठ", "अड़सठ",
    "उनहत्तर", "सत्तर", "इकहत्तर", "बहत्तर", "तिहत्तर", "चौहत्तर", "पचहत्तर",
    "छिहत्तर", "सतहत्तर", "अठहत्तर", "उनासी", "अस्सी", "इक्यासी", "बयासी",
    "तिरासी", "चौरासी", "पचासी", "छियासी", "सत्तासी", "अट्ठासी", "नवासी",
    "नब्बे", "इक्यानबे", "बानबे", "तिरानबे", "चौरानबे", "पंचानबे", "छियानबे",
    "सत्तानबे", "अट्ठानबे", "निन्यानबे", "सौ", "हज़ार", "हजार", "लाख", "करोड़",
    "डबल", "ट्रिपल", "वन", "ओन", "टू", "थ्री", "फोर", "फाइव", "सिक्स",
    "सेवन", "एट", "ऐट", "आइट", "नाइन", "नाईन", "ट्वेंटी", "सेवन",
    "जनवरी", "फरवरी", "मार्च", "अप्रैल", "मई", "जून", "जुलाई", "अगस्त",
    "सितंबर", "अक्टूबर", "नवंबर", "दिसंबर",
})


def _number_or_date_word(word: str) -> bool:
    word = unicodedata.normalize("NFC", word.casefold().strip(".,!?।॥:;()[]{}\"'"))
    if any(char.isdecimal() for char in word):
        return True
    # Hyphenated English numbers such as twenty-seven are one spoken group.
    return bool(word) and all(
        part in _NUMBER_AND_DATE_WORDS or part in REGIONAL_SPOKEN_DIGITS
        for part in word.split("-")
    )


def _safe_number_boundary(text: str, previous_end: int, following_start: int) -> bool:
    previous = text[:previous_end].rstrip().rsplit(None, 2)
    after_connector = (
        len(previous) >= 2
        and previous[-1].casefold() in {"and", "और"}
        and _number_or_date_word(previous[-2])
    )
    if not previous or not (_number_or_date_word(previous[-1]) or after_connector):
        return True
    following = text[following_start:].lstrip()
    next_word = re.match(r"\S+", following)
    # A streamed token may still be an unfinished word. Wait for its
    # terminating whitespace before deciding whether the number ended.
    if not next_word or next_word.end() == len(following):
        return False
    if _number_or_date_word(next_word.group()):
        return False
    if next_word.group().casefold() in {"and", "और"}:
        remainder = following[next_word.end():].lstrip()
        after_connector = re.match(r"\S+", remainder)
        if not after_connector or after_connector.end() == len(remainder):
            return False
        if _number_or_date_word(after_connector.group()):
            return False
    return True


def _phrase_boundary(text: str, minimum: int) -> tuple[int, int] | None:
    """Avoid ending a synthesis request in the middle of a number or date."""
    for boundary in re.finditer(r"\s", text[minimum:]):
        start = minimum + boundary.start()
        end = minimum + boundary.end()
        if _safe_number_boundary(text, start, end):
            return start, end
    return None


class LocalSpeechAggregator(BaseTextAggregator):
    """Join short sentences while retaining normal streaming for longer ones.

    Independent HTTP synthesis has a fixed cost per request. Speaking a tiny
    acknowledgement alone often finishes before the next request has audio,
    causing a long unnatural pause. Flush still releases short answers at the
    end of the LLM response; interruptions discard all pending text.
    """

    def __init__(
        self, min_characters: int = 48, first_chunk_characters: int | None = None,
        first_clause_characters: int | None = None,
        first_phrase_characters: int | None = None,
        streaming_phrase_characters: int | None = None,
    ):
        super().__init__()
        self._sentences = SimpleTextAggregator()
        self._pending = ""
        self._phrase_tail = ""
        self._min_characters = min_characters
        self._first_chunk_characters = first_chunk_characters or min_characters
        self._emitted = False
        self._first_clause_characters = first_clause_characters
        self._first_phrase_characters = first_phrase_characters
        self._streaming_phrase_characters = streaming_phrase_characters

    @property
    def text(self) -> Aggregation:
        return Aggregation(
            text=self._join(self._pending, self._sentences.text.text + self._phrase_tail),
            type=AggregationType.SENTENCE,
        )

    @staticmethod
    def _join(first: str, second: str) -> str:
        return " ".join(part for part in (first.strip(), second.strip()) if part)

    async def aggregate(self, text: str):
        # A phrase split can leave half of the next word in this token.
        # Reattach it verbatim before sentence parsing, never as a completed
        # sentence (whose join operation intentionally adds a separator).
        text = self._phrase_tail + text
        self._phrase_tail = ""
        async for sentence in self._sentences.aggregate(text):
            self._pending = self._join(self._pending, sentence.text)
            threshold = self._min_characters if self._emitted else self._first_chunk_characters
            if len(self._pending) >= threshold:
                result, self._pending = self._pending, ""
                self._emitted = True
                yield Aggregation(text=result + " ", type=AggregationType.SENTENCE)
        # Optional first-clause release for slow streaming models. Only split
        # at a natural punctuation boundary followed by whitespace, never a
        # word-count deadline or the comma in a number. Later chunks retain
        # sentence batching to avoid repeated synthesis gaps.
        if not self._emitted and self._first_clause_characters:
            buffered = self._sentences.text.text
            # SimpleTextAggregator's public text property trims edge spaces.
            # Restore only the lookahead that arrived in this input token.
            if text and text[-1].isspace():
                buffered += " "
            for boundary in re.finditer(r"(?<!\d)[,;،؛](?=\s)", buffered):
                first = self._join(self._pending, buffered[:boundary.end()])
                if len(first) < self._first_clause_characters:
                    continue
                if not _safe_number_boundary(buffered, boundary.end(), boundary.end()):
                    continue
                tail = buffered[boundary.end():]
                await self._sentences.reset()
                self._pending = ""
                self._emitted = True
                yield Aggregation(text=first + " ", type=AggregationType.SENTENCE)
                # Re-enter through the same path so a large token containing
                # the remainder is processed just like incremental tokens.
                async for part in self.aggregate(tail):
                    yield part
                break
        # Some conversational replies have no punctuation for an entire long
        # sentence. Bound the first-phrase wait at a word boundary, while
        # retaining the rest for the normal sentence aggregator. A short
        # fragment would create both choppy speech and an extra CPU request.
        if not self._emitted and self._first_phrase_characters:
            buffered = self._sentences.text.text
            if text and text[-1].isspace():
                buffered += " "
            # A short completed sentence can already be waiting in _pending
            # while the next sentence is still arriving. Include it when
            # testing for a safe first phrase, or an available word boundary
            # can be held until the next sentence completes.
            prefix = self._pending.strip()
            # Keep the trailing lookahead whitespace on buffered: the split
            # includes its boundary in the spoken phrase, so dropping this
            # trailing separator here would concatenate the tail with the next
            # LLM token when that token does not carry a leading space.
            combined = f"{prefix} {buffered}" if prefix and buffered else prefix or buffered
            minimum = self._first_phrase_characters
            # Release as soon as the *first* suitable space arrives. Waiting
            # for the entire lookahead window added avoidable generation time.
            if len(combined) > minimum and not combined.rstrip().endswith((".", "?", "!", "।", "॥")):
                boundary = _phrase_boundary(combined, minimum)
                if boundary:
                    split_at, split_end = boundary
                    # Keep the separating whitespace on the emitted phrase.
                    # The next synthesis request passes through the sentence
                    # aggregator, which trims leading whitespace.
                    first = combined[:split_end]
                    tail = combined[split_end:]
                    await self._sentences.reset()
                    self._pending = ""
                    self._emitted = True
                    yield Aggregation(text=first, type=AggregationType.SENTENCE)
                    async for part in self.aggregate(tail):
                        yield part

        # The first-phrase release above starts speech early. Once it has
        # started, local HTTP TTS can prefetch further word-boundary phrases
        # while the current audio is playing. Without this branch every later
        # phrase waits for a full sentence terminator, which is the source of
        # audible gaps on slow CPU LLMs.
        if self._emitted and self._streaming_phrase_characters:
            buffered = self._sentences.text.text
            if text and text[-1].isspace():
                buffered += " "
            combined = self._join(self._pending, buffered)
            if text and text[-1].isspace():
                combined += " "
            minimum = self._streaming_phrase_characters
            if len(combined) > minimum and not combined.rstrip().endswith((".", "?", "!", "।", "॥")):
                boundary = _phrase_boundary(combined, minimum)
                if boundary:
                    split_at, split_end = boundary
                    first, tail = combined[:split_end], combined[split_end:]
                    await self._sentences.reset()
                    self._pending = ""
                    self._phrase_tail = tail
                    yield Aggregation(text=first, type=AggregationType.SENTENCE)

    async def flush(self) -> Aggregation | None:
        tail = await self._sentences.flush()
        text = self._join(self._pending, (tail.text if tail else "") + self._phrase_tail)
        self._pending = ""
        self._phrase_tail = ""
        self._emitted = False
        return Aggregation(text=text, type=AggregationType.SENTENCE) if text else None

    async def reset(self):
        self._pending = ""
        self._phrase_tail = ""
        self._emitted = False
        await self._sentences.reset()

    async def handle_interruption(self):
        await self.reset()
