"""Avoid separate CPU synthesis requests for tiny adjacent sentences."""

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

    def __init__(self, min_characters: int = 48):
        super().__init__()
        self._sentences = SimpleTextAggregator()
        self._pending = ""
        self._min_characters = min_characters

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
            if len(self._pending) >= self._min_characters:
                result, self._pending = self._pending, ""
                yield Aggregation(text=result, type=AggregationType.SENTENCE)

    async def flush(self) -> Aggregation | None:
        tail = await self._sentences.flush()
        text = self._join(self._pending, tail.text if tail else "")
        self._pending = ""
        return Aggregation(text=text, type=AggregationType.SENTENCE) if text else None

    async def reset(self):
        self._pending = ""
        await self._sentences.reset()

    async def handle_interruption(self):
        await self.reset()
