# After90 match desk refresh

The dashboard uses one editorial football theme: warm neutral surfaces, a dark
forest match panel, lime replay accents and coral away-team comparisons. Shared
variables replace the earlier stacked theme overrides. Typography and spacing
create a clear hierarchy across the scoreboard, controls, insights and evidence.
The studio graphic uses the same visual language. No external font request or
new runtime dependency is required.

Replay behaviour, match data, AI provenance and evidence remain unchanged. A
skip link and wrapping header label preserve keyboard and narrow-screen access;
reduced-motion preferences are respected. The document title now uses After90.

Validation: 13 frontend behaviour tests and production build passed. Chromium153
release checks passed with no runtime errors or axe violations in the four
checked states (desktop Analyst, full-time Fan, mobile390 and mobile320). Replay,
recap, overlays, activity keyboard focus and horizontal overflow checks passed.
These checks cover tested states rather than claim accessibility certification.
