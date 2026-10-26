# After90 AI delivery plan

This plan uses the twelve phases agreed on October 24, 2026. Its numbering is
separate from the historical five-phase plan and from frontend PR #1/#2.
**After90** is the product name; `backend.matchlens` remains the internal Python
package to preserve compatibility. All match data is synthetic.

## Scope and owners

| Owner | Responsibility | Interface/handoff |
| --- | --- | --- |
| Billi | Deterministic facts, contextual interpretation, story ledger, backend integration | Canonical context packet to AI and UI |
| Maryam | Foundry adapter, bounded narrative selection, evidence validation, fallback | Paired Fan/Analyst narrative and generation metadata |
| Ayesha | Presentation, accessible replay, evidence, audience modes, studio overlay preview | Typed frontend consumer of the AI contract |
| Zoya | Evaluation corpus, Azure access, public release, demo and submission | Test evidence and verified public links |

Core release: replay, contextual evidence, paired audience narratives, recap,
structured overlay output, reliable fallback, Azure/Foundry proof and public demo.
Optional after release: favourite-team priority, player focus, extra language or
purposeful agent collaboration with measured benefit. Video detection, real match
feeds, tracking, accounts, and extra infrastructure remain deferred.

## Dependency order

| Wave | Phase | Dependency | Completion evidence |
| --- | --- | --- | --- |
| 1 | 1 Scope/contracts | None | Typed Python/TypeScript contracts and ownership documented |
| 1 | 2 Foundry/Azure readiness | None | Offline preflight plus real endpoint proof and human account/access checks |
| 1 | 3 Evaluation scenarios | Existing golden fixture; phase 1 for contract checks | Distinct cases with expected outcomes and runner |
| 2 | 4 Evidence/context | 1 | Canonical, time-bounded packets and interpretation tests |
| 2 | 5 Generation/validation | 2 live access, 4 | Structured selection, semantic controls, fallbacks, live model evaluation |
| 2 | 6 Story ledger/recap | 4 | Deterministic ranked/deduplicated stories and full-time packet |
| 3 | 7 Backend reliability/API | 5, 6 | Cache/lock/timeout/versioning integration and endpoint tests |
| 3 | 8 UI personalization/overlay | 1 for mocks; 5 for integration | Accessible audience modes, evidence and studio preview |
| 4 | 9 Integrated evaluation | 3, 7, 8 | Accuracy/failure/performance and browser evidence |
| 4 | 10 Public Azure release | Preparation parallel with 9; release requires 9 | Actual public deployed build and Foundry connection |
| 5 | 11 Optional extensions | 10 | At most one extension passing the same acceptance checks |
| 5 | 12 Demo/submission | Pitch can start after 1; final video requires 10 | Video under two minutes, working public links, submission receipt |

An offline-only phase 5 implementation may proceed against the typed transport
contract while phase 2 is externally blocked. This is preparation, not satisfaction
of the live Foundry dependency. Do not report waves 1/2 fully complete without that
proof. Injected clients and templates never establish live model quality.

## Existing frontend integration

The AI work is stacked on `feature/interactive-match-intelligence`, which already
contains the frontend Phase 1 changes and reviewed activity fixes. PR #1 targets
main and PR #2 targets `feature/frontend-improvements`. Both were open at the
start of this work. This working branch does not merge those PRs or replace their
review gates. Merge the existing frontend PRs in their agreed order before final
main-branch integration. No unrelated client work is changed.

## Acceptance audit

Each phase must distinguish implemented code, offline verification, real service
verification, and owner/account actions. `docs/AI_PROGRESS.md` records the final
checklist for this implementation and any remaining blockers. Definitions of done
include relevant tests and an accurate source label; no model calculates canonical
statistics or invents tactics, chance quality, speed, injury, or player tracking.
