# Stories Of Yggdrasil OSC Desktop v0.8.14

## Activity cleanup QOL

Sam.py may publish multiple unique Libra cleanup records when an encounter ends.
The Desktop now treats that specific cleanup as an idempotent notification:

- The first cleanup appears normally.
- Matching repeats are ignored for 45 seconds.
- The visible row no longer becomes `×2`, `×3`, or `×4`.
- Ignored repeats are not written to the saved activity log.
- Other repeated events continue using normal duplicate grouping.

No Sam.py, Fight System, OSC API, or Unity Tool update is required.
