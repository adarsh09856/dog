"""Call-scoped, request-only snapshots of validated caller details."""


class CallerStateContext:
    def __init__(self, state: dict | None = None):
        # Text-chat services are reconstructed on each turn. Keep the prior
        # request-only reminder in the existing call checkpoint so it can be
        # removed before the current snapshot is inserted.
        self._state = state if isinstance(state, dict) else {}
        snapshots = self._state.get("snapshots")
        self._snapshots = {
            value for value in snapshots.values() if isinstance(value, str)
        } if isinstance(snapshots, dict) else set()

    def _save(self) -> None:
        # Keep only one current snapshot so corrections cannot conflict with
        # stale facts and long calls do not grow the prompt on every change.
        self._state["snapshots"] = (
            {"current": next(iter(self._snapshots))} if self._snapshots else {}
        )

    def apply(self, messages: list, reminder: str | None) -> list:
        """Inject one current, request-only caller-state reminder.

        Historical snapshots preserve a longer model-cache prefix, but leave
        contradictory names, phone numbers, and booking details in the same
        prompt after a correction. Replace old snapshots with the latest
        validated state immediately before the latest caller turn. The reminder
        is never committed to caller history.
        """
        result = [
            message for message in messages
            if not (
                isinstance(message, dict)
                and message.get("role") == "system"
                and isinstance(message.get("content"), str)
                and message.get("content") in self._snapshots
            )
        ]
        self._snapshots.clear()
        latest_user_index = next((
            index for index in range(len(result) - 1, -1, -1)
            if isinstance(result[index], dict)
            and result[index].get("role") == "user"
        ), None)
        if latest_user_index is None or not isinstance(reminder, str) or not reminder:
            self._save()
            return result

        result.insert(latest_user_index, {"role": "system", "content": reminder})
        self._snapshots.add(reminder)
        self._save()
        return result
