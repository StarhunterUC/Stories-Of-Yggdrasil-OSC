# GitHub Release Notes — v0.8.14

- Prevents repeated Libra encounter-end cleanup notices from spamming Recent Activity.
- Suppresses only the known non-actionable cleanup message for 45 seconds.
- Preserves normal grouping for all other repeated events.
- Prevents suppressed cleanup repeats from filling `events.log`.
