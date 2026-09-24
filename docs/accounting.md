# Pilot accounting and capacity

**Local simulation, not a funded live launch.** The 12-credit cap is a prototype limit. There is no committed onchain mint, pool inventory, provider capital deposit, fee claim, or refund collateral. A live issuance must remain gated until the full 12-credit fulfillment budget is actually funded and the real DBC/DAMM path is tested.

## Units and obligations

All local credit quantities are integer base units. Reconciliation is:

`issued = holder available + local pool inventory + redemption escrow + completed-request burns`

On a clean batch: 12 = 0 + 12 + 0 + 0. After the scripted two-wallet story: **12 = 6 (B) + 2 (pool) + 0 (escrow) + 4 (completed)**. Wallet A has zero. The pool's two unsold credits remain potential service obligations. A voluntary SPL burn would need its own category; it would never increment completed work without a successful request completion record.

The local quote is fixed at **$5.00 per whole credit** only to exercise UI and accounting. It is not an actual Meteora quote. Demo wallet cash and pool quote cash are separate from operating funds. No creator fees are accrued or claimed. No DAMM liquidity or refund backing exists. Do not count DBC purchase principal as provider income.

## Measured baseline and budgeting assumptions

The optimized sample renderer produced a 15.0-second, 450-frame H.264/yuv420p MP4 in **9.39 seconds** on Intel Xeon E5-2678 v3 (12 cores/24 logical), Windows, Pillow 12.2.0, FFmpeg 8.1.1. Sample output was 127,980 bytes. One scene has slow screenshot zoom; the other three are typographic scenes. The output has no audio. This is one sample measurement, not a throughput or SLA benchmark.

For planning only, suppose a CPU host costs $0.05/hour, each render uses 30 billable seconds including setup and upload, each job may render twice, and each retained artifact plus thumbnail costs 10 MB for 30 days at $0.03/GB-month. Twelve fulfilled credits then require at most **24 renders × 30 s = 720 s**, or **$0.01 CPU** at that assumed rate, plus less than **$0.01 storage**. These arithmetic estimates omit idle host time, bandwidth, monitoring, support, provider labor, failed uploads, payment fees, taxes, and a contingency. A credible funded pilot should reserve a materially larger operating amount (proposed **$50**) before onchain launch, then revise it after real host measurements and actual vendor quotes. **No such funds have been deposited or proved here.**

No hard credit expiry exists. The 48-hour deadline applies to an individual accepted request. A returned credit retains the same service terms. If the batch never graduates from DBC, provider obligations still cover all outstanding units; the proposed operating reserve must not depend on graduation or future fee claims.
