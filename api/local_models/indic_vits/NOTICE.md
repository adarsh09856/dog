AI4Bharat VITS Rasa 13
=====================

Model and architecture: AI4Bharat, VITS TTS for Indian Languages (Ashwin Sankar, 2024).
Source: https://huggingface.co/ai4bharat/vits_rasa_13
License: Creative Commons Attribution 4.0 International.
License text: https://creativecommons.org/licenses/by/4.0/legalcode

ONNX export: MatiasLin, revision b5afd4e991e3bdd6195528de650e2ed219d47506.
https://huggingface.co/MatiasLin/sherpa-onnx-vits-rasa-13
The export is a derivative of the above model, distributed under CC BY 4.0.
Kodewaves serves that export with the documented CONV style and trained speaker slots.
Kodewaves does not claim authorship of the model or that it supports all Indian languages.

The regional model supports the 13 languages and 20 speaker slots documented by AI4Bharat.
The adapter also loads installed Piper Hindi and Urdu models, each subject to its
distributed model card and licenses. They are not additional AI4Bharat speakers.

Indian English: MyShell.ai MeloTTS-English, EN_INDIA speaker (speaker ID 2).
Original model: https://huggingface.co/myshell-ai/MeloTTS-English
Code and model license: MIT. https://github.com/myshell-ai/MeloTTS/blob/main/LICENSE
ONNX conversion by M5Stack:
https://huggingface.co/M5Stack/MeloTTS-English-axmodel
Pinned revision: 815731592c5c050da9505fa4b7f16aee74fb06a8.
The three inference assets are additionally checked against SHA-256 digests in app.py.
Upstream does not document the EN_INDIA speaker's gender. Kodewaves does not
claim that this single speaker provides both male and female voices.

Reply-script routing selects these engines behind one speech endpoint, including
script changes inside a reply. Shared-script languages require language context.
Native callbacks forward PCM during synthesis; callback granularity depends on
the selected model. This is not a claim of word-level or token-level synthesis.
