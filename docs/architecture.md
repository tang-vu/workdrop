# Service and state model

The immutable local batch binds `service-manifest.json` through its canonical SHA-256 hash (`sort_keys` JSON serialization). It issues 12 × 1,000,000 base units. One whole credit is 1,000,000 units, and one request reserves exactly one credit. Fractions may exist in a future market but cannot make a fractional video. The current local market only trades whole credits.

```
Available credit ──request──> Requested / reserved ──render, validate, store──> Completed / burned
                                      │
                                      └──at deadline──> TimedOut / returned to original owner
```

Worker labels `queued`, `rendering`, `settling`, and `retry available` are offchain progress states. They never alter entitlement themselves. SQLite `BEGIN IMMEDIATE` serializes local buy/sell/request/complete/timeout; a read transaction makes multi-table accounting snapshots consistent. `UNIQUE(owner, nonce)` makes request creation idempotent and substituted retries fail. Job rows remain durable. The renderer writes a temporary MP4, validates it with ffprobe, atomically moves it into private storage, then changes the local terminal state. The API only serves a completed job's video to its selected demo owner. Worker startup resubmits pending jobs with remaining attempts. A 660-second SQLite lease prevents two local processes from claiming the same job; FFmpeg is bounded to 600 seconds. This is still a pilot queue, not a distributed production scheduler.

The **onchain draft** in `programs/workdrop` separates batch configuration, request PDA, and per-request escrow. It requires provider and authority signatures to initialize immutable terms, provider admission to request, owner signature and exact credit transfer, attester signature for completion burn, and a permissionless timeout return to the recorded token account. Nonces remain in durable request accounts. It is not deployed, audited, or connected to the backend. The signing authority can attest an artifact hash; the hash does not prove video quality or independent AI execution.

## Trust and recovery

- Provider and completion signer are trusted for fulfillment. Users should inspect the manifest before a future onchain purchase. A deadline is not a cash refund; a timed-out credit returns and the provider's service obligation persists.
- Input screenshots and output MP4s stay under the configured local data directory. Do not expose that directory through a static web server. Local demo wallet headers are intentionally not public authentication.
- If rendering fails, the job remains Requested for at most two attempts. The credit is still reserved until deadline. If timeout wins, the worker must not release its MP4. If completion wins, timeout fails. A stored output can be recovered after a worker restart.
- A provider must monitor jobs, storage, disk capacity, deadline proximity, and the finalized chain state in a future live deployment. Reconcile the job database against request PDAs after transaction uncertainty, then release the private artifact only after finalized completion.
- The optional Solami observer uses server-side RPC configuration, a persistent signature store, overlapping scans, finalized transaction fetches, and a last-success/stale indicator. It does not decode swaps or establish live integration without project credentials and relevant addresses.
