# Indic-Parler CPU candidate

This service is staged for evaluation. It has not passed real model synthesis,
voice quality, memory, or response-latency acceptance on the production VPS.

Provision authorized files before starting:

- `/models/indic-parler/`: the complete `ai4bharat/indic-parler-tts` model,
  including config, all weight shards and prompt tokenizer files.
- `/models/description-tokenizer/`: the complete tokenizer named by the model's
  `config.text_encoder._name_or_path`. This is separate from the prompt tokenizer.

The service uses `local_files_only=True` and offline Hub settings. It does not
download weights or require credentials during startup or a call.

The API accepts `model=indic-parler-tts`, a named voice, text, `pcm` or `wav`,
and speed. PCM uses the native Parler streamer, then stateful resampling to
24-kHz mono signed 16-bit PCM. WAV buffers the same PCM for browser demos.
Speed adjusts the spoken pace description, not the sample rate or pitch.
Requests are serialized; another live request receives 429 instead of silently
queuing behind CPU synthesis. Disconnects stop generation before releasing the
shared model lock.

The voice controls speaker identity and descriptive gender. The model derives
the spoken language from the input text; this does not add STT language detection.
Twenty scheduled Indian languages and English are reported from the current
official support list. Punjabi and Kashmiri are experimental, not accepted.
The four initial named speakers are evaluation choices, not proof of natural
speech across every language. Expand the voice pool after listening acceptance.

Before migration, measure cold/warm first PCM, real-time factor, peak RSS, silence,
clipping, truncation, Hindi/English/code-mixed clarity and regional pronunciation.
Then verify complete web and telephone turns, interruption, follow-ups and grammar.
Only remove the old model containers after references are migrated and those
checks pass. Preserve recordings, database/storage volumes and other sites.

Sources:
- https://huggingface.co/ai4bharat/indic-parler-tts
- https://github.com/huggingface/parler-tts/blob/main/INFERENCE.md
