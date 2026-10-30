"""Call-scoped, request-only snapshots of validated caller details."""


class CallerStateContext:
    def __init__(self, state: dict | None = None):
        # Text-chat services are reconstructed on each turn. Keep only the
        # prompt-prefix bookkeeping in the existing call checkpoint so the
        # next service can preserve earlier reminder positions.
        self._state = state if isinstance(state, dict) else {}
        users = self._state.get("users")
        snapshots = self._state.get("snapshots")
        self._users = [v for v in users if isinstance(v, str)] if isinstance(users, list) else []
        self._snapshots = {
            int(k): v for k, v in snapshots.items()
            if str(k).isdigit() and isinstance(v, str)
        } if isinstance(snapshots, dict) else {}

    def _save(self) -> None:
        self._state["users"] = list(self._users)
        self._state["snapshots"] = {str(k): v for k, v in self._snapshots.items()}

    def apply(self, messages: list, reminder: str | None) -> list:
        """Retain earlier request prefixes; append facts only when they change.

        Moving one reminder to the newest user turn on every request invalidates
        the model's prefix cache. Anchor each snapshot to the turn that first
        exposed it instead. Later corrections get a later snapshot. These are
        private to one service instance and never written into caller history.
        """
        users = [
            (index, message["content"])
            for index, message in enumerate(messages)
            if isinstance(message, dict) and message.get("role") == "user"
            and isinstance(message.get("content"), str)
        ]
        current = [content for _, content in users]
        common = 0
        for before, after in zip(self._users, current):
            if before != after:
                break
            common += 1
        # A truncated or edited conversation must not inherit snapshots from
        # discarded turns. The latest validated facts are reanchored below.
        self._snapshots = {
            ordinal: value for ordinal, value in self._snapshots.items()
            if ordinal < common
        }
        self._users = current
        if not users or not reminder:
            self._snapshots.clear()
            self._save()
            return list(messages)

        last_snapshot = next(reversed(self._snapshots.values()), None)
        if reminder != last_snapshot:
            self._snapshots[len(users) - 1] = reminder

        by_index = {
            users[ordinal][0]: value
            for ordinal, value in self._snapshots.items()
        }
        result = []
        for index, message in enumerate(messages):
            if index in by_index:
                result.append({"role": "system", "content": by_index[index]})
            result.append(message)
        self._save()
        return result
