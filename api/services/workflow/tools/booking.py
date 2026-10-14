"""Native booking tool: confirmation is returned only after persistence."""

from datetime import datetime

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    ValidationError,
    field_validator,
    model_validator,
)

from api.db import appointments


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
