"""The local CPU TTS adapter must release native audio before synthesis ends."""

import asyncio
import ctypes
import threading

import numpy as np
import pytest

from api.local_models.indic_mio import app as mio


@pytest.mark.asyncio
async def test_pcm_stream_releases_native_callback_before_generation_finishes(monkeypatch):
    release = threading.Event()
    finished = threading.Event()

    class FakeModel:
        def sc_indic_mio_synthesize(self, _handle, _text, callback, _context):
            samples = (ctypes.c_float * 2)(0.25, -0.25)
            callback(samples, 2, False, None)
            if not release.wait(3):
                return 1
            callback(samples, 2, True, None)
            finished.set()
            return 0

        def sc_indic_mio_last_error(self, _handle):
            return b"timed out"

    monkeypatch.setattr(mio, "MODEL", FakeModel())
    monkeypatch.setattr(mio, "HANDLE", 1)
    stream = mio.stream_pcm(mio.SpeechRequest(input="Hello", response_format="pcm"))
    try:
        first = await asyncio.wait_for(anext(stream), 2)
        assert first == (np.array([0.25, -0.25]) * 32767).astype("<i2").tobytes()
        assert not finished.is_set()
        release.set()
        assert await asyncio.wait_for(anext(stream), 2) == first
        with pytest.raises(StopAsyncIteration):
            await asyncio.wait_for(anext(stream), 2)
    finally:
        release.set()
        await stream.aclose()
