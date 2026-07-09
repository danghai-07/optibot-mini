# Demonstration screenshots

Images for the [Demonstration (screenshots)](../README.md#demonstration-screenshots) section in the root README (substitute for video submission).

| File | Requirement |
|------|-------------|
| [scrape.png](scrape.png) | Scrape ≥30 Zendesk articles → Markdown (`data/articles/`) |
| [screenshot-railway-logs.png](screenshot-railway-logs.png) | API upload (first run): `added: 35`, `skipped: 0` |
| [delta-skipped.png](delta-skipped.png) | Delta sync (second run): `skipped: 35`, `added: 0` |
| [railway-cron.png](railway-cron.png) | Railway daily cron (`0 2 * * *` UTC) |
| [screenshot-playground.png](screenshot-playground.png) | OptiBot chat test with `Article URL:` citations |

**Chat test:** run `python scripts/test_chat.py "How do I add a YouTube video?"` after sync.
