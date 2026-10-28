"""Call-scoped, request-only snapshots of validated caller details."""


class CallerStateContext:
    def __init__(self):
        self._users: list[str] = []
        self._snapshots: dict[int, str] = {}

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
        return result
