# Deployment gate and recovery runbook

This build is intended for **local review only**. Do not expose its API publicly: `X-Demo-Wallet` is a walkthrough selector, not authentication, and no Solana transaction is authoritative in the app. No network or cloud deployment was made.

## Local service layout

1. Install pinned Python requirements, FFmpeg/ffprobe, Node and the pinned pnpm from the README.
2. Set `WORKDROP_DATA_DIR` to a private directory with sufficient disk space. Keep it outside any public static route. `WORKDROP_MODE=local` is the only accepted mode.
3. Start `python -m uvicorn app.server:app --host 127.0.0.1 --port 8000` and `corepack pnpm dev` in `web/`. An optional second render worker is `python -m scripts.worker` with the same data directory.
4. Use `python -m scripts.reconcile` after a walkthrough. Back up SQLite and the input/output directories together while workers are stopped; a database backup without artifacts cannot serve completed outputs.
5. Examine `jobs` in SQLite for Requested jobs near deadline, exhausted attempts, expired leases, or completed jobs whose MP4 is missing. A user can recover a timed-out local credit through `/api/jobs/{id}/recover`; in a live version this must be a direct permissionless chain transaction.

## Before any live deployment

- Generate and review a unique program keypair; replace the placeholder Anchor program ID. Build and deploy to a verified cluster, then test wrong signer, mint, token program, account substitution, duplicate nonce, completion/timeout races, account closure, and direct recovery.
- Choose and validate the DBC config with the pinned SDK. Verify quote mint, decimals, complete issued supply, mint and freeze authority, DBC/DAMM vault allocations, fee destinations and claims, and the entire pre-graduation burn → migration → post-migration trade sequence on real programs. Record signatures and balances.
- Fund the provider's whole-batch service obligation independently of quote reserves and future fees. Record the source account, actual deposit, exact pilot budget, retry contingency, and measured host costs.
- Replace the local selector with replay-resistant wallet authentication. Bind authenticated wallets to job records and use private object storage with short-lived signed download URLs. Keep completion signing keys and Solami credentials server-side. Add durable queue leases, storage health checks, transaction reconciliation, and alerting.
- Supply `SOLAMI_RPC_URL` (official HTTPS endpoint with a project key) and `WORKDROP_LIVE_ADDRESSES` only after relevant mint, pool and program addresses exist. Verify connection and relevant finalized transactions; current observer records references but does not decode trade direction.
- Run privacy and retention checks, a security review, and a live end-to-end test before enabling real funds. Do not label source-verified SDK calls as executed transactions.

## Current costs and actions

No mainnet money-moving action, API purchase, deployment fee, token issuance, or paid Solami request occurred in this build. The Meteora local validator gate used locally airdropped SOL and official program fixtures; see `docs/integration-evidence.md` for its ephemeral signatures. Exact mainnet transaction costs and accounts **cannot yet be specified** because no approved mint/config, provider wallet, quote mint, or funded budget exists. The next engineering gate is deploying and testing the WORKDROP Anchor entitlement program with the Meteora fixture path, including completion and timeout. No mainnet spend is needed for that gate.
