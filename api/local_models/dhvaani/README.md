Place licensed, consented 3–10 second mono PCM16 WAV reference recordings here.
Create `voices.json` beside them with entries such as:

```json
[
  {
    "id": "indian-female",
    "name": "Indian female",
    "gender": "female",
    "accent": "Indian multilingual",
    "file": "female.wav",
    "transcript": "The exact words spoken in female.wav",
    "preview_text": "Hello, how can I help you?"
  }
]
```

The reference and its transcript control the sound of DhVaani. Keep voice
recordings out of Git unless their distribution rights are established.
