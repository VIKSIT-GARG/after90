# MatchLens submission pitch draft

## One sentence

MatchLens turns a fictional football match into a replayable, evidence-backed explanation of what changed and when.

## Short English pitch

Following a match should mean more than watching a score change. MatchLens lets fans replay a fully synthetic football fixture and inspect the events behind each key moment. A deterministic engine calculates score, shots, passes, possession, and insight evidence from the event record. Fan and Analyst views explain the same verified facts at different levels of detail, and a full-time recap summarizes the final snapshot. Every insight includes supporting event IDs so viewers can check the explanation. The React dashboard and FastAPI backend are packaged as one container. An optional Microsoft Foundry Responses adapter can write grounded prose when configured; the working local demo currently uses labeled deterministic templates. Azure Container Apps deployment is prepared but has not yet been published.

## Submission fields to fill after publication

- **Public repository:** pending team publication and license decision.
- **Working demo URL:** pending Azure account and deployment.
- **Public video URL:** pending upload of the final under-two-minute recording.
- **Category:** pending team selection against the official categories.
- **Microsoft services actually demonstrated:** pending live Foundry and/or Azure verification. Describe only a service that is used by the submitted build.
- **Team representative and members:** pending registration confirmation.

## What the demo proves

1. The same minute produces the same score, statistics, and insight IDs.
2. Every insight shown in the UI has canonical evidence and event IDs.
3. Switching Fan and Analyst changes wording while preserving the evidence.
4. A model outage or unsupported model claim uses a clearly labeled template.
5. The full-time recap agrees with the final computed snapshot.

Use [DEMO_SCRIPT.md](DEMO_SCRIPT.md) for the walkthrough. The supplied fixture, teams, players, and events are fictional; do not suggest access to official league data or footage.
