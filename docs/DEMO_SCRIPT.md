# MatchLens live demo script (target: 110 seconds)

**Synthetic match data.** Screen-record the actual working public app, with its fictional-data label visible. Rehearse the exact clicks against the release candidate and verify the exported duration is below 120 seconds. Use the fallback explanation if Foundry access or response time is uncertain, and describe its source honestly.

The [official rules](https://github.com/microsoft/insidethegamehackathon/blob/main/OFFICIAL%20RULES.md) require footage of the working project on its intended platform and a public video link on YouTube, Vimeo, Facebook Video, or Youku. The submission also needs a public GitHub repository and working project access. Submission closes **October 27, 2026 at 11:59 p.m. Pacific Time**; registration closes **October 20, 2026 at 12:00 p.m. Pacific Time**.

| Time | On screen | Spoken track |
|---|---|---|
| 0–12s | Open the public dashboard; keep the synthetic label in frame. | “MatchLens helps fans understand a fictional football match as it unfolds. Every event here is synthetic.” |
| 12–32s | Start replay; point to clock, event feed, score, shots, passes, and possession. Pause briefly. | “A fixed event fixture drives the replay. Score and statistics are calculated from those events, so the same minute always shows the same facts.” |
| 32–55s | Jump to minute 29. Open the goal insight `goal-e072` and show evidence IDs and the linked shot. | “This goal card cites the events behind the score change. You can inspect the evidence rather than taking the explanation on trust.” |
| 55–75s | Switch Fan to Analyst on the same card. Keep evidence visible. | “Fan mode is brief; Analyst mode adds detail. Both use the same verified match facts.” |
| 75–95s | Jump to full time and open the recap. Show Northstar Quay 2, Copper Vale 1. | “At full time, the recap uses the final computed score, statistics, and selected evidenced moments.” |
| 95–110s | Return to dashboard or show a simple closing card with tested public app and repository links. | “The deployed app uses React, FastAPI, and [name only Microsoft services actually used]. Try the replay yourself at these public links.” |

## Recording cues

- Preload the public page in a private browser to prove judges can open it, then record a fresh replay from minute 0. Hide personal account details and tokens.
- Use the controls that exist in the release build. If a planned action or card differs, update this script from the actual UI before recording.
- At minute 29, the checked-in fixture yields `goal-e072`, an earlier shot surge, and a possession swing. Show the visible evidence as implemented; avoid describing tactics, causes, or player behavior that the events do not prove.
- If the app shows `source: template`, say “template explanation.” Say “Foundry generated” only after a real Foundry response has been verified. Replace the bracketed service phrase before export.
- After export, check duration, audio, readable labels, links, and access without team login. Save the final file and submission receipt with the team’s submission materials.
