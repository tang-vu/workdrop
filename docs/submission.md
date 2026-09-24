# Submission drafts — not submitted

## Short English description

WORKDROP turns a defined piece of creative work into a transferable service credit. The first drop is one 15-second product teaser: upload one product screenshot and short copy, receive a finished H.264 MP4, or sell an unused credit to someone who wants the same service. A future live batch would use Meteora DBC to launch and trade credits, DAMM v2 after migration, an Anchor escrow for use and timeout recovery, and Solami to reconcile chain activity. The current build proves the four-video customer story **locally**; it is not an onchain launch.

## Problem, insight and pilot customer

Small creators and product teams want finished marketing assets, but buying open-ended AI generation leaves uncertainty about output, timing and cost. A narrow service makes the promise legible: one screenshot, one short brief, one finished silent teaser. Transferability gives a buyer another option if their launch changes. The provider remains obligated to fulfill every outstanding whole credit, including those in pool inventory. A real pilot should recruit a small number of creators who already have product screenshots, ask them to judge the delivered video against the contract, and measure whether they would pay for it or trade unused capacity. No external users, paid conversions or traction have been recorded.

## 2–3 minute presentation script

**0:00–0:25 — Need.** “A creator can buy AI tools all day and still not know whether they will get a usable finished asset. WORKDROP starts with a smaller promise: a 15-second product teaser from one screenshot and three lines of copy.”

**0:25–0:55 — Product.** “A drop is a finite batch of identical service credits. One whole credit covers the complete output. A holder can use it or sell it unused; the next holder can use it for their own product.”

**0:55–1:35 — Demo.** “Here is the shipped MP4. In our local two-wallet sequence A buys ten, makes three videos, sells seven, then B buys seven and makes a fourth. A ends at zero, B at six, and four completed requests account for four consumed credits.” Clearly say **local simulation** while showing this build.

**1:35–2:10 — Solana lifecycle.** “Our intended chain path is a fixed-supply mint, Meteora DBC trading, a request-specific Anchor escrow, attested completion burn or permissionless timeout return, then DAMM v2 trading after migration. The current code includes a compiling Anchor draft and a compiling official-SDK trade adapter, but the actual DBC-to-DAMM burn compatibility test is still a gate. We will not show a simulated migration as live.”

**2:10–2:40 — Business.** “The provider must pre-fund every potential render. DBC reserves are liquidity, not our revenue. We begin with one template and one provider, then expand only after creators validate usefulness and fulfillment economics.”

## Product demo script, at most 3 minutes

1. Play the real 15-second teaser on Explore and show its 1920×1080, 450-frame metadata.
2. Show the exact terms and the **local simulated** $5 quote. Select demo wallet A; buy ten credits.
3. Submit three distinct jobs with valid screenshots/copy and wait for actual CPU renders. For a prerecorded walkthrough, run `python -m scripts.demo` beforehand with a fresh `WORKDROP_DATA_DIR`, then open that same data directory in the app; disclose that the four jobs were prepared in advance. Open the three playable MP4s and their local receipts.
4. Sell A's seven unused credits; switch to demo wallet B; buy seven and submit one new job using B's own inputs.
5. Show B's fourth video and Provider reconciliation: A 0, B 6, pool 2, completed 4. State plainly that Meteora and onchain settlement are **not yet verified**.

Do not compress a render wait into a fabricated timer. For a recorded demo, use an honestly precomputed dataset and label it.

## Founder and market facts to confirm

Founder identity, location, legal eligibility, relevant credentials, team membership, product domain, customer interviews, and actual willingness to pay are **not supplied**. Add them from evidence before submission. Closest alternative categories to research with citations: direct AI video generators, creative agencies/freelancers, and tokenized service or AI-agent marketplaces. WORKDROP's testable distinction is a precisely specified completed-work credit that can be redeemed or resold unused through an active market. Do not claim novelty or superiority without a documented comparison.

## Pilot outreach draft — do not send without instruction

“I’m testing WORKDROP, a service that turns one product screenshot and a short brief into a 15-second teaser. We’re running a small pilot and want honest feedback on whether the finished file is usable for your next launch. Would you try one? We’ll explain the exact input rules, delivery deadline, and how your screenshot is handled before you share anything.”

Feedback questions: Was the output usable as delivered? What edit would matter most? Was the brief easy to prepare? Was the 48-hour deadline acceptable? Would you buy one at the quoted price? Would you value being able to sell an unused credit? Do you permit an anonymized quote or case study?

Track metrics in separate columns for builder tests, gifted credits, external paid purchases, external redemptions, resale transactions, repeat purchases, successful deliveries, failed deliveries, and actual cost. Do not infer independent demand from the builder-operated two-wallet sequence.

## Reused work and source inventory

The repository's initial commit (`a393baf`) contained only `.gitattributes`; the current WORKDROP source, documentation, and original Aura sample graphics were added after that commit. This repository history alone cannot establish whether a team member developed related work elsewhere before September 14. The team must confirm and disclose any relevant earlier product work in the Colosseum form; [Colosseum's FAQ](https://colosseum.com/hackathon) permits reuse but judges only contest-period work. Third-party packages are enumerated in `requirements.txt`, `web/pnpm-lock.yaml`, and `Cargo.lock`; their licenses need a final inventory before publication. The renderer uses installed system fonts and the repository contains no stock imagery or music.

## Track-to-evidence matrix

| Track | Current evidence | Rule or judging fit | Remaining gate |
| --- | --- | --- | --- |
| [Colosseum main event](https://colosseum.com/hackathon) | Real local teaser, four-artifact builder demo, defined service economics; `assets/sample/`, `tests/test_local_loop.py`, `docs/accounting.md` | Functionality, UX and business plan can be presented with accurate local labels. | Complete the onchain loop and customer validation; confirm team eligibility; register, submit the English entry, 2–3 minute presentation and ≤3 minute demo. |
| [Solana ecosystem](https://colosseum.com/worldsfair) | Anchor program source in `programs/workdrop`; local ledger tests are **not** Solana transactions. | The event's Solana award is for products integrating the Solana blockchain. | Validator tests, program deployment, client wiring and transaction references before claiming a working Solana integration. |
| [Meteora DBC](https://superteam.fun/earn/listing/meteora-dbc) | Official-SDK adapter and a real-program local validator fixture trace in `integrations/meteora/` and `docs/integration-evidence.md`: DBC create/buy, external burn, graduation, DAMM migration/buy, external burn. | Depth of DBC/DAMM integration, execution, originality and real use are judging factors; mainnet activity is preferred. | Connect and test WORKDROP Anchor redemption rather than raw SPL burns, validate a funded pilot config and fees, deploy with transaction evidence, and submit on Superteam Earn. |
| [Solami](https://superteam.fun/earn/listing/build-something-live-on-solana-data) | Unauthenticated, unverified RPC observer adapter in `app/solami.py`. | A meaningful Solami data path, public runnable repo and 2–3 minute live mainnet demo are required. | Authenticate and record real Solami responses for WORKDROP transactions, publish an authorized runnable repo, demonstrate on mainnet and submit. |
| [Superteam Vietnam](https://superteam.fun/earn/listing/colosseum-crypto-worlds-fair-hackathon-superteam-vietnam-track) | Verified requirements in `docs/research/rules.md`; no team eligibility or registration evidence. | Vietnam base country, separate registration/group step, October 4 pitch and both platform submissions are required; online pitch is accepted. | Confirm eligibility and pitch schedule, register, pitch, and submit to Colosseum and Superteam Earn. |

Main deadline: **2026-10-13 13:59 ICT** per [official rules](https://colosseum.com/legal/Crypto%20World%27s%20Fair%20Hackathon%20Rules.pdf) and listing timestamps reviewed 2026-09-23. The Vietnam Demo Day is October 4; its exact pitch time was not visible. Recheck rules before publication. Cash prizes, infrastructure credits and potential accelerator investment are separate categories. No prize, eligibility or traction claim is established by this draft.
