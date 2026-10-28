# TTS replacement research — 2026-10-21

## Current decision and do-not-repeat evidence

- **DhVaani commercial-use correction (Oct21):** its current official card declares `cc-by-nc-4.0` and says the weights derive from an NC base. Earlier Apache-2.0 notes below and in handoff files are stale. Do not deploy it for the commercial Kodewaves service without separate rights. Browser account approval only grants download access, not commercial rights.
- **Do not repeat the Indic-Mio LiteRT trial on this 16-GB VPS.** Oct18 peak RSS was about 8.6 GB; the Oct20 isolated 4-GB container was OOM-killed during model load. The trial container/image and 2.8-GB cache were removed. The failure applies to this LiteRT runtime, not every possible quantized/native runtime of the model.
- The next distinct quality candidate is Indic-Parler, but it has 20 officially supported Indian languages plus English; Punjabi and Kashmiri remain unofficial. Its documented speaker/style controls are relevant, but it is not an accepted all-22 CPU solution and its weights are gated. Do not install a large serving stack before a bounded synthesis benchmark.
- Existing **native Indic-Mio** engineering artifacts use llama.cpp speech-token generation plus the 24-kHz MioCodec. A local two-thread probe produced first decoded prefixes in 0.78–0.90 s, but prefix consistency, transport playback, VPS performance, male/female quality and all-language accuracy were not accepted. These are different from the failed LiteRT trial. The codec is not proven causal; do not stream cumulative-prefix differences without checking boundary stability.
- Production run 280: first user turn was about 31.9 s to audible audio; second about 4.8 s. Run 281 with shortened boilerplate was worse (37.2-s LLM first token, 45.4-s measured response). Prompt edit was reverted. Both used Indus and Hindi-fixed IndicConformer; Kannada speech was transcribed in Devanagari. These runs do not constitute Kannada accuracy acceptance.
- Isolated Qwen3.5 2B Q4 repeated-prompt TTFT was 0.36 s versus Q8 1.13 s, but varied Hindi/Kannada prompts still needed 3–4 s and produced semantically poor replies. The trial was removed and no live LLM selection changed. Cache-hit benchmarks must not be advertised as ordinary turn latency.

Latest requirement: retire Indus after a verified replacement; regional Rasa alone misses Hindi and English. Retain all-22 scheduled-language scope, male/female identity, natural Indian speech, self-hosted CPU deployment and measured latency.

## Live CPU baseline (2026-10-21)

Measured from the VPS host through each container's `/v1/audio/speech` endpoint with uncached sample phrases. HTTP first byte is **not** caller-audible first audio; the LLM, orchestration, WebRTC and telephone transport add delay. These are single requests, not p95 or concurrency acceptance.

| Existing engine | Sample | HTTP first byte | HTTP completion | Observation |
|---|---|---:|---:|---|
| Indic VITS Rasa, Tamil female | `வணக்கம், நான் உங்களுக்கு எப்படி உதவ முடியும்? உங்கள் கேள்வியைச் சொல்லுங்கள்.` | 1.839 s | 1.843 s | Catalog reports `streaming: false`; essentially the whole utterance is generated before the first byte. |
| Indus Pocket, Hindi female | `नमस्ते, मैं आपकी कैसे मदद कर सकती हूँ? अपना सवाल बताइए।` | 0.192 s | 2.193 s | Service streams bytes earlier, but does not cover the required regional languages. |

The locally downloaded Indic-Parler folder still lacks `model.safetensors` (3.75 GB) as of this check; no real Parler synthesis or CPU latency claim is possible yet. Its prepared service is not a deployed/visible model.

Additional candidate screen: [Svara inference](https://github.com/Kenpath/svara-tts-inference) lists Hindi, Indian English, Tamil, Telugu, Kannada and Malayalam with male/female profiles, but its production deployment requires an NVIDIA GPU with 16+ GB VRAM. A GGUF local example is documented without 4-core CPU first-audio measurements; it cannot be called a proven low-latency VPS solution. [IndicF5](https://github.com/AI4Bharat/IndicF5) lacks English in its published language list. Neither is currently a verified replacement. Voice naturalness must be judged from blind listening samples of the actual deployed CPU output, including code-switching, not inferred from parameter count or GPU demos.

The installed Rasa VITS checkpoint exposes only its documented 13-language speaker IDs; Hindi and English cannot be added by labeling spare embedding slots. [Open-Speech-EkStep's published Vakyansh weights](https://github.com/Open-Speech-EkStep/vakyansh-models) include Hindi and English male/female checkpoints, along with Tamil, Telugu, Kannada and Malayalam. They use Glow-TTS plus HiFi-GAN rather than this Rasa VITS checkpoint, so a separate runtime and language router would be needed. Their repository advertises MIT, but naturalness, Indian English accent, CPU first audio, and per-weight rights still require validation before deployment. Generic English [sherpa-onnx VITS checkpoints](https://github.com/k2-fsa/sherpa/blob/master/docs/source/onnx/tts/pretrained_models/vits.rst) are not established Indian-English voices.

**Vakyansh availability correction:** the official Hindi female Glow-TTS and HiFi-GAN links and English female Glow-TTS link returned HTTP 403 on 2026-10-21. They are unsuitable as the immediate production fix despite the published catalog.

**Next lightweight candidate split, pending actual listening and VPS measurement:** [MeloTTS](https://github.com/myshell-ai/MeloTTS) has a documented Indian-English speaker, MIT code, and claims CPU real-time inference. The [IIT-Madras FastSpeech2-HS model mirror](https://github.com/gagneetkaur04/Bhashini-TTS) lists Hindi weights under CC BY 4.0, while [another ONNX INT8 export](https://github.com/Henil21/Bhashini-TTS) lists Hindi male/female but lacks an explicit repository license. Rasa can remain for Tamil, Telugu, Kannada, Malayalam and its other trained languages. None of these new candidates has passed a Kodewaves CPU synthesis, naturalness, concurrency, or end-to-end test. Three runtimes may also exceed the 4-core latency budget; only one or two active voice models should stay resident if testing proves this path viable. Do not expose this split as installed yet.

| Candidate | Coverage and identity/style | Decision/evidence |
|---|---|---|
| ARTPARK-IISc/DhVaani-0.5 | Published 27-language training list covers all 22 scheduled languages plus English and additional Indian varieties. ~123M parameters; 491-MB weights. Reference-conditioned voice, not a packaged male/female library. **Current weights license: CC-BY-NC-4.0.** | **Excluded from commercial deployment without separate rights.** Native CPU path documented, but mixed-language prosody explicitly not trained and low-resource languages weaker. No accepted VPS latency or quality result. |
| ai4bharat/indic-parler-tts | Published key-capability list: 20 Indian languages + English; Kashmiri and Punjabi unofficial. 69 voices, Indian English and style/emotion caption controls; emotion coverage limited by language. Card retains older inconsistent 18-language wording further down. | Strong expression/voice candidate; all-22 quality and CPU latency unproven. Config HTTP 401 from server. Do not advertise full verified coverage. |
| Supertone/supertonic-3 | Native ONNX, 31 languages including Hindi and English; other scheduled Indian languages absent from documented list. OpenRAIL-M weights, MIT sample code. | Potential CPU component only, not a complete all-22 replacement. Config HTTP 200 from server. No new weights installed. |
| k2-fsa/OmniVoice (including INT8 exports) | Broad multilingual voice design/reference conditioning; 0.6B. | Rejected for this commercial platform: official model weights CC-BY-NC, despite Apache-2.0 code. CPU exporter numbers are backbone-forward timings, not full synthesis or response latency. |
| SPRINGLab/Indic-Mio | Published all 22 + English; Apache-2.0. | Previous LiteRT candidate exceeded practical memory budget on this deployment; do not re-enable or relabel as production-ready. |

Primary sources:
- https://huggingface.co/ARTPARK-IISc/DhVaani-0.5
- https://huggingface.co/ai4bharat/indic-parler-tts
- https://huggingface.co/Supertone/supertonic-3
- https://huggingface.co/k2-fsa/OmniVoice
- https://huggingface.co/gaber/OmniVoice-ONNX-CPU-INT8
- https://github.com/k2-fsa/OmniVoice/issues/152
- https://huggingface.co/SPRINGLab/Indic-Mio

No current candidate has passed the requested combination of all-22 language accuracy, natural code-switching, stable gender/voice, expression, CPU memory and measured 700–800-ms full-pipeline latency. Research establishes a shortlist, not acceptance. No current agent config was changed and no serving model removed during this research.
