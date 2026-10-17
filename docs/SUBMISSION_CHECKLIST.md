# Release and submission checklist

The [official rules](https://github.com/microsoft/insidethegamehackathon/blob/main/OFFICIAL%20RULES.md) set registration to close **October 20, 2026 at noon Pacific** and submissions to close **October 27, 2026 at 11:59 p.m. Pacific**. A team must appoint an eligible representative. The public working demo must stay available free of charge without restrictions through the judging period ending November 10, 2026.

## Product release

- [x] Match starts, pauses, resets, changes speed, and reaches full time from a clean local browser session.
- [x] Score and stats match the golden fixture at sampled minutes and at full time.
- [x] Goal, shot surge, and possession swing insights appear with evidence.
- [x] Fan and Analyst modes show different wording over the same facts.
- [x] Every match screen clearly says **Synthetic match data**.
- [ ] Foundry path is demonstrated if access exists; fallback works and is described accurately.
- [x] Recap matches final score and selected moments.
- [ ] Public demo opens without a team login; mobile and desktop layouts are usable.
- [x] No keys, tokens, private endpoints, or personal data are committed or exposed in the browser build.
- [ ] README includes setup, architecture, actual Microsoft services, limitations, and a public demo URL (URL awaits deployment).

## Required submission assets from the brief

- [ ] Public GitHub repository with source and license decision.
- [ ] Working public demo or test build and access instructions.
- [ ] Public video shorter than two minutes showing the actual product working, hosted on YouTube, Vimeo, Facebook Video, or Youku.
- [ ] Short English pitch: problem, users, solution, AI grounding, and Microsoft technology actually used.
- [ ] English text or required translations for all submission materials.
- [ ] Team registration completed before October 20 noon Pacific; eligible representative appointed.
- [ ] Official category and eligibility requirements checked.
- [ ] Demo access remains free and unrestricted through November 10.
- [ ] Final links tested in a private browser session and pasted into the organizer form.
- [ ] Submission completed before October 27 at 11:59 p.m. Pacific; receipt saved.

## Suggested 110-second video script

| Time | Scene | What to say/show |
|---|---|---|
| 0-15s | Problem | Scores alone do not explain why a match is changing. Show the synthetic label. |
| 15-35s | Replay | Start the fictional match; events and stats update together. |
| 35-60s | Insight | Open a key moment; show its supporting window/counts/event IDs. |
| 60-80s | Personalization | Toggle Fan to Analyst; same evidence, different depth. |
| 80-100s | Full time | Jump to final recap. |
| 100-110s | Build claim | Name only the Microsoft services actually integrated and show repo/demo links. |

Record the app itself, not mockups. Rehearse with cached or fallback explanations so a network delay does not consume the time limit. Verify the final export duration.

## Pitch skeleton

> MatchLens is a companion for a fictional football match. It turns synthetic events into verified statistics and explains meaningful patterns for casual fans and analysts. Every explanation shows its evidence, and the recap uses only computed match facts. We built it with [actual stack and Microsoft services]. The demo is replayable so judges can inspect the same moment and compare viewer modes.

Replace the bracketed phrase only after the deployment is live. Avoid claims about real match data, official Premier League feeds, or multiple AI agents unless those capabilities actually exist.
