"""Avoid separate CPU synthesis requests for tiny adjacent sentences."""

import re

from pipecat.utils.text.base_text_aggregator import (
    Aggregation, AggregationType, BaseTextAggregator,
)
from pipecat.utils.text.simple_text_aggregator import SimpleTextAggregator


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
        self._min_characters = min_characters
        self._first_chunk_characters = first_chunk_characters or min_characters
        self._emitted = False
        self._first_clause_characters = first_clause_characters
        self._first_phrase_characters = first_phrase_characters
        self._streaming_phrase_characters = streaming_phrase_characters

    @property
    def text(self) -> Aggregation:
        return Aggregation(
            text=self._join(self._pending, self._sentences.text.text),
            type=AggregationType.SENTENCE,
        )

    @staticmethod
    def _join(first: str, second: str) -> str:
        return " ".join(part for part in (first.strip(), second.strip()) if part)

    async def aggregate(self, text: str):
        async for sentence in self._sentences.aggregate(text):
            self._pending = self._join(self._pending, sentence.text)
            threshold = self._min_characters if self._emitted else self._first_chunk_characters
            if len(self._pending) >= threshold:
                result, self._pending = self._pending, ""
                self._emitted = True
                yield Aggregation(text=result, type=AggregationType.SENTENCE)
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
                tail = buffered[boundary.end():]
                await self._sentences.reset()
                self._pending = ""
                self._emitted = True
                yield Aggregation(text=first, type=AggregationType.SENTENCE)
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
            minimum = self._first_phrase_characters
            # Release as soon as the *first* suitable space arrives. Waiting
            # for the entire lookahead window added avoidable generation time.
            if len(buffered) > minimum:
                boundary = re.search(r"\s", buffered[minimum:minimum + 17])
                if boundary:
                    split_at = minimum + boundary.start()
                    first = self._join(self._pending, buffered[:split_at])
                    tail = buffered[split_at:]
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
            minimum = self._streaming_phrase_characters
            if len(combined) > minimum:
                boundary = re.search(r"\s", combined[minimum:minimum + 17])
                if boundary:
                    split_at = minimum + boundary.start()
                    first, tail = combined[:split_at], combined[split_at:]
                    await self._sentences.reset()
                    # Retain the unspoken suffix locally. Re-feeding it into
                    # SimpleTextAggregator discards its leading separator on
                    # some incremental Indic tokens, which joins words.
                    self._pending = tail.strip()
                    yield Aggregation(text=first, type=AggregationType.SENTENCE)

    async def flush(self) -> Aggregation | None:
        tail = await self._sentences.flush()
        text = self._join(self._pending, tail.text if tail else "")
        self._pending = ""
        self._emitted = False
        return Aggregation(text=text, type=AggregationType.SENTENCE) if text else None

    async def reset(self):
        self._pending = ""
        self._emitted = False
        await self._sentences.reset()

    async def handle_interruption(self):
        await self.reset()
