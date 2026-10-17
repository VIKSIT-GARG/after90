# Release and submission checklist

The supplied team brief lists these deliverables. Zoya must verify them against the organizer's official page, including the exact deadline, time zone, category, and public-access rules.

## Product release

- [ ] Match starts, pauses, resets, changes speed, and reaches full time from a clean browser session.
- [ ] Score and stats match the golden fixture at sampled minutes and at full time.
- [ ] At least one goal, one attacking pattern, and one possession/alternative trend insight appear with evidence.
- [ ] Fan and Analyst modes show different wording over the same facts.
- [ ] Every match screen clearly says **Synthetic match data**.
- [ ] Foundry path is demonstrated if access exists; fallback works and is described accurately.
- [ ] Recap matches final score and selected moments.
- [ ] Public demo opens without a team login; mobile and desktop layouts are usable.
- [ ] No keys, tokens, private endpoints, or personal data are committed or exposed in the browser.
- [ ] README includes setup, architecture, actual Microsoft services, limitations, and demo URL.

## Required submission assets from the brief

- [ ] Public GitHub repository with source and license decision.
- [ ] Working public demo or test build and access instructions.
- [ ] Public video shorter than two minutes showing the actual product working.
- [ ] Short English pitch: problem, users, solution, AI grounding, and Microsoft technology actually used.
- [ ] English text or required translations for all submission materials.
- [ ] Official category and eligibility requirements checked.
- [ ] Final links tested in a private browser session and pasted into the organizer form.
- [ ] Submission completed before the verified official deadline; receipt saved.

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
