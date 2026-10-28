"""Compare local conversation behavior; diagnostic output is not an accuracy certification."""
import argparse
import asyncio
import json
import time

import httpx

CASES = {
    "en": (
        "I need help with my order.",
        "Please share your order number. I cannot check live tracking here.",
        "My order number is TEST-123. Can you check its status?",
    ),
    "kn": (
        "ನನ್ನ ಆರ್ಡರ್ ಬಗ್ಗೆ ಸಹಾಯ ಬೇಕು",
        "ದಯವಿಟ್ಟು ನಿಮ್ಮ ಆರ್ಡರ್ ಸಂಖ್ಯೆ ತಿಳಿಸಿ. ಇಲ್ಲಿ ನೇರ ಟ್ರ್ಯಾಕಿಂಗ್ ಮಾಹಿತಿ ಲಭ್ಯವಿಲ್ಲ.",
        "ನನ್ನ ಆರ್ಡರ್ ಸಂಖ್ಯೆ ಒಂದು ಎರಡು ಮೂರು, ಅದರ ಸ್ಥಿತಿ ನೋಡಬಹುದೇ",
    ),
    "hi": (
        "मुझे अपने ऑर्डर के बारे में मदद चाहिए।",
        "आपका ऑर्डर नंबर क्या है? यहाँ लाइव ट्रैकिंग उपलब्ध नहीं है।",
        "मेरा ऑर्डर नंबर एक दो तीन है। क्या आप उसकी स्थिति देख सकती हैं?",
    ),
}
SYSTEM = (
    "You are a female customer-support assistant. Reply in one short sentence in "
    "the caller's language. Continue the conversation and use details already supplied. "
    "You have no connected tracking, order-changing or staff-contact tools. Never "
    "claim to check or change a record or contact staff. If asked for shipment status, "
    "clearly say you cannot access it and suggest contacting the seller. Do not ask "
    "again for a supplied order number. Never invent an ID, status or contact method. "
    "Keep credentials, private records and admin information confidential."
)


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--endpoint", default="http://ollama:11434/v1")
    parser.add_argument("--model", required=True)
    args = parser.parse_args()
    async with httpx.AsyncClient(timeout=60) as client:
        for language, (first, answer, followup) in CASES.items():
            system = SYSTEM
            if args.model.casefold().startswith("qwen3:"):
                # Mirror the runtime's documented Qwen3 prompt control. The
                # OpenAI-compatible endpoint alone may ignore `think:false`.
                system += "\n/no_think"
            messages = [
                {"role": "system", "content": system},
                {"role": "user", "content": first},
                {"role": "assistant", "content": answer},
                {"role": "user", "content": followup},
            ]
            body = {"model": args.model, "messages": messages, "stream": True,
                    "temperature": 0.1, "max_tokens": 96,
                    "think": False, "reasoning_effort": "none"}
            start = time.monotonic(); first_token = None; text = ""; finish = None
            async with client.stream("POST", f"{args.endpoint}/chat/completions", json=body) as response:
                response.raise_for_status()
                async for line in response.aiter_lines():
                    if not line.startswith("data: ") or line == "data: [DONE]":
                        continue
                    choices = json.loads(line[6:]).get("choices") or []
                    if not choices:
                        continue
                    content = choices[0].get("delta", {}).get("content") or ""
                    finish = choices[0].get("finish_reason") or finish
                    if content:
                        if first_token is None:
                            first_token = time.monotonic() - start
                        text += content
            print(json.dumps({"model": args.model, "language": language,
                "first_token_seconds": first_token, "total_seconds": time.monotonic()-start,
                "finish_reason": finish, "answer": text}, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    asyncio.run(main())
