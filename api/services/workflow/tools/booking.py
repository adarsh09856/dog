"""Native booking tool: confirmation is returned only after persistence."""

from datetime import datetime
import re

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    ValidationError,
    field_validator,
    model_validator,
)
from fastapi import HTTPException

from api.db import appointments
from api.services.client_worker_entitlements import require_client_worker_features
from api.services.saas_entitlements import enforce_saas_feature


def caller_phone_matches_booking(phone: str, messages: list) -> bool:
    """Reject altered digits when the caller explicitly supplied an E.164 phone.

    Prefer the latest caller correction. Assistant readbacks are not evidence
    because the model may itself have copied the number incorrectly.
    """
    digits = str.maketrans("०१२३४५६७८९", "0123456789")
    for message in reversed(messages):
        if not isinstance(message, dict) or message.get("role") != "user":
            continue
        text = message.get("content")
        if not isinstance(text, str):
            continue
        numbers = re.findall(r"\+\d{10,15}(?!\d)", text.translate(digits))
        if numbers:
            supplied = re.sub(r"\D", "", str(phone).translate(digits))
            return supplied == numbers[-1].lstrip("+")
    # Caller ID or previously verified contact data may supply the phone when
    # the caller has not spoken an explicit international number.
    return True


def caller_confirmed_booking(messages: list) -> bool:
    """Read consent from the caller, rather than trusting an LLM boolean."""
    from api.services.workflow.confirmed_booking import room_booking_active

    if room_booking_active(messages):
        return False
    dialogue = [m for m in messages if isinstance(m, dict) and m.get("role") in ("user", "assistant")]
    caller_index = next((i for i in range(len(dialogue) - 1, -1, -1) if dialogue[i].get("role") == "user"), None)
    if caller_index is None:
        return False
    text = dialogue[caller_index].get("content")
    if not isinstance(text, str) or re.search(
        r"\b(don['’]t|do not|cancel(?:led|lation)?|not|no|never|nahi|nahin|mat)\b"
        r"|नहीं|मत\s|रद्द|कैंसल|कॅन्सल", text, re.I,
    ):
        return False
    recent = " ".join(str(m.get("content", "")) for m in dialogue[max(0, caller_index - 4):caller_index + 1])
    if not re.search(r"\b(appointment|booking|consultation|reservation)\b|अपॉइंटमेंट|बुकिंग|नियुक्ति", recent, re.I):
        return False
    if re.search(r"\b(?:I|we)\s+(?:explicitly\s+)?confirm\b|\bmain\s+confirm\s+kart[ai]\s+(?:hu|hun|hoon)\b|पुष्टि\s+कर(?:ता|ती|ते)|पक्का\s+कर", text, re.I):
        return True
    # A caller may repeat the details while confirming in Hinglish. The
    # short-answer fullmatch below intentionally rejects extra words, so keep
    # this explicit affirmative + imperative case separate.
    if (
        re.search(r"\+\d{10,15}(?!\d)", text)
        and re.search(r"\b\d{1,2}\s+[A-Za-z]+\s+\d{4}\b", text)
        and re.search(
        r"\b(?:haan|han|yes|ji)\b[\s\S]*\b(?:confirm\s+hai|(?:confirm|book)\s+kar\s+(?:do|dijiye|dena))\b",
        text,
        re.I,
        )
    ):
        return True
    if not re.fullmatch(
        r"\s*(?:(?:yes|ok|okay|haan|han|ha|ji|हाँ|हां|जी)(?:[,.]?\s+(?:please|go ahead|confirm(?:\s+kar\s+(?:do|dijiye))?|book\s+kar\s+(?:do|dijiye)|हाँ|हां|haan|han|बुक\s+कर\s+दो))?"
        r"|correct|that's right|go ahead|theek hai|ठीक है|(?:confirm|book)\s+kar\s+(?:do|dijiye))[.!।\s]*",
        text, re.I,
    ):
        return False
    previous = next((m.get("content", "") for m in reversed(dialogue[:caller_index]) if m.get("role") == "assistant"), "")
    if not isinstance(previous, str):
        return False
    booking_readback = re.search(
        r"\b(appointment|booking|consultation|reservation|book)\b|अपॉइंटमेंट|बुकिंग|नियुक्ति|बुक", previous, re.I,
    )
    confirmation_question = re.search(
        r"\b(confirm|sahi|theek)\b|is (?:this|that|everything) correct|पुष्टि|सही|पक्का"
        r"|\b(?:shall|should|may|can) I\b[^?]*\bbook\b|\bgo ahead and book\b"
        r"|(?:बुक(?:िंग)?|कन्फर्म|कंफर्म)\s+कर\s*(?:दूँ|दूं|दें)|\bbook\s+kar\s+(?:du|doon|dun)\b", previous, re.I,
    )
    return bool(booking_readback and confirmation_question)


class BookingArguments(BaseModel):
    model_config = ConfigDict(extra="forbid")

    customer_name: str = Field(min_length=1, max_length=100)
    customer_phone: str = Field(min_length=1, max_length=30)
    customer_email: str | None = Field(default=None, max_length=255)
    title: str = Field(default="Consultation", min_length=1, max_length=200)
    start_time: datetime = Field(
        description="Caller-confirmed ISO 8601 start, with year, date and timezone offset."
    )
    end_time: datetime | None = Field(
        default=None,
        description="ISO 8601 end with timezone; omit to use workspace duration.",
    )
    notes: str | None = None
    confirmed_by_caller: bool = Field(
        description="True only after the caller agrees to this exact date and time."
    )

    @field_validator("start_time", "end_time")
    @classmethod
    def timezone_required(cls, value):
        if value is not None and (value.tzinfo is None or value.utcoffset() is None):
            raise ValueError("Confirm the timezone before booking")
        return value

    @field_validator("customer_phone")
    @classmethod
    def complete_phone_required(cls, value):
        normalized = value.translate(str.maketrans("०१२३४५६७८९", "0123456789"))
        if not re.fullmatch(r"\+?[\d\s().-]+", normalized.strip()) or not 7 <= len(re.sub(r"\D", "", normalized)) <= 15:
            raise ValueError("Ask for a complete phone number, including its country code")
        return value

    @field_validator("customer_name", "customer_phone", "title")
    @classmethod
    def strip_required(cls, value):
        value = value.strip()
        if not value:
            raise ValueError("Customer name, phone and title cannot be blank")
        return value

    @model_validator(mode="after")
    def confirmed_interval(self):
        if not self.confirmed_by_caller:
            raise ValueError("Ask the caller to confirm the exact date and time first")
        if self.end_time is not None and self.end_time <= self.start_time:
            raise ValueError("End time must be after start time")
        return self


async def execute_booking(arguments, organization_id):
    if not organization_id:
        return {
            "status": "error",
            "booked": False,
            "error": "Workspace unavailable; no booking was saved",
        }
    try:
        await require_client_worker_features("appointments")
        await enforce_saas_feature(organization_id, "appointments")
        booking = BookingArguments.model_validate(arguments)
        if booking.start_time <= datetime.now(booking.start_time.tzinfo):
            return {
                "status": "error",
                "booked": False,
                "error": "Confirm a future date and time; no booking was saved",
            }
        result = await appointments.save_appointment(
            organization_id,
            {
                **booking.model_dump(exclude={"confirmed_by_caller"}),
                "status": "confirmed",
            },
        )
        return {
            "status": "success",
            "booked": True,
            "appointment_id": result["id"],
            "start_time": booking.start_time.isoformat(),
            "message": "Appointment saved in the workspace calendar",
        }
    except ValidationError as exc:
        errors = "; ".join(error["msg"] for error in exc.errors(include_input=False))
        return {"status": "error", "booked": False, "error": errors}
    except HTTPException as exc:
        return {"status": "error", "booked": False, "error": str(exc.detail)}
    except FileExistsError:
        return {
            "status": "conflict",
            "booked": False,
            "error": "That time is unavailable. Ask for another time; no booking was saved",
        }
    except (LookupError, ValueError):
        return {
            "status": "error",
            "booked": False,
            "error": "Booking details are invalid or unavailable; no booking was saved",
        }
