# WORKDROP Meteora adapter

Server-side, read and transaction-construction adapter using the official DBC 1.5.12 and DAMM v2 1.4.10 SDKs. It does not contain keys, sign, submit, or claim transaction success. It makes no fixture fallback on RPC failure.

## Check

```powershell
cd integrations/meteora
pnpm install --frozen-lockfile
pnpm check
```

Import `MeteoraAdapter` from `src/index.ts` in a server process. Supply an RPC URL, the actual DBC pool and base/quote mints, the selected DAMM migration fee config, and an integer number of base units per credit. `snapshot()` reads DBC state, mint authority and supply, and the derived DAMM pool account. `quoteDbcBuy` / `quoteDbcSell` and `quoteDammBuy` / `quoteDammSell` quote whole credits in base units. `prepareDbcTrade` / `prepareDammTrade` re-read state and construct bounded transactions for a specified wallet signer. The caller must simulate, present fees and price impact where supported, obtain that wallet's signature, send, confirm/finalize, and reconcile actual token balances. A returned transaction or quote is not a purchase or sale.

The WORKDROP entitlement program accepts only classic SPL Token for the credit mint. Every adapter read rejects a DBC config with `tokenType != 0`, so a Token-2022 DBC credit cannot be treated as a redeemable WORKDROP credit.

## Real-program local validator gate (2026-09-24)

`real-program-gate.mjs` succeeded on Agave `solana-test-validator 4.2.2` in WSL, using the official DBC SDK fixture binaries for DBC and DAMM v2. A read-only clone of the official DAMM v2 customizable migration config `A8gMrEPJkacWkcb3DGwtJwTe16HktSEfvwtuDh2MCtck` from mainnet was required; the plain fixture validator lacked this account. The DBC program's `flash_rent` migration path also needed 1 local airdropped SOL on its pool-authority PDA before migration. No mainnet transaction or spending occurred.

The script created a fresh DBC config/pool, bought exact-output base tokens, burned 1,000,000 base units from the buyer's token account, completed the DBC curve, migrated to a real fixture DAMM v2 pool, bought an exact-output token amount there using a second wallet, and burned another 1,000,000 base units. Both burns reduced mint supply by the expected amount. The last run exited 0; local signatures and account balances are in [`docs/integration-evidence.md`](../../docs/integration-evidence.md). The selected curve is a test curve with extreme local airdropped SOL liquidity and does **not** validate a funded pilot price or mainnet deployment.

Reproduction requires the [official DBC SDK repo](https://github.com/MeteoraAg/dynamic-bonding-curve-sdk) at commit `0c5e375f1f9764e82d8b59a49698a0748ef8a739`, Agave 4.2.2 in WSL, and a local validator on port 8899. Start the official `start-validator` command from that repo's `packages/dynamic-bonding-curve` package, adding `--url https://api.mainnet-beta.solana.com --clone A8gMrEPJkacWkcb3DGwtJwTe16HktSEfvwtuDh2MCtck` to the validator arguments; this only reads the config account. Then run `node real-program-gate.mjs` here. The script refuses a non-loopback RPC URL. Resetting the validator ledger destroys these local transaction references.

## Runtime gates still open

- No DBC config or pool has been created through this adapter. Pin an approved config and inspect its quote mint badge, fixed supply, allocations, migration threshold, lock terms, fees, migration fee recipient, and current SDK validation. Record actual mint/freeze authority and config keys after creation.
- The fixture test establishes the **Meteora protocol** path, including external SPL burns before and after migration. It does not execute WORKDROP's Anchor redemption program, its attester, or artifact delivery. This adapter has not been exercised against a real deployed WORKDROP mint/pool, devnet, or mainnet. Simulate every user transaction and re-quote after stale quotes, rejected signatures, or network changes.
- `snapshot()` treats DBC migration progress `3` plus the derived DAMM account owned by the DAMM v2 program, with matching mints, as migrated. The fixture test observed progress `2 → 3` and a successful DAMM swap. Validate the exact migration fee config and pool account for the pilot before enabling its customer route.
- DAMM quote `priceImpact` comes from the official SDK and needs UI unit validation on a real migrated pool. DBC's exact-output quote API does not expose price impact in its result; this adapter reports it as `null` rather than inventing one.
- This module does not implement a wallet auth flow, transaction simulation, status recovery, accounting ledger, fee claim, or program upgrade audit. It must stay on the server; do not bundle it with browser secrets.

Research and official links: [`docs/research/meteora.md`](../../docs/research/meteora.md).
