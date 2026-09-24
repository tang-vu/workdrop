# Integration evidence — 2026-09-24

This file separates source inspection, local execution, and actual chain evidence. The local product is a simulation and uses no real token or pool.

| Component | Pinned code / identifiers | Executed evidence | Missing gate |
| --- | --- | --- | --- |
| Entitlement program | Anchor 0.31.1; `programs/workdrop/src/lib.rs`; placeholder program ID | `cargo check -p workdrop_entitlement` passes. Local SQLite tests exercise analogous states, not this program. | Validator adversarial tests, reviewed program ID, deployment signature, request/complete/timeout transaction signatures, authority audit. |
| Meteora DBC | Official `@meteora-ag/dynamic-bonding-curve-sdk` 1.5.12; program `dbcij3LWUppWqq96dh6gJWwBifmcGfLSB5D4DuSMaqN` | TypeScript adapter compiles. On local Agave 4.2.2 with official DBC binary: config/pool creation, exact-output buy, external SPL burn, and curve graduation succeeded. Details below. | Approved pilot config/mint, WORKDROP Anchor redemption, actual customer transaction flow, deployed-network evidence and fee reconciliation. |
| Meteora DAMM v2 | Official `@meteora-ag/cp-amm-sdk` 1.4.10; program `cpamdpZCGKUy5JxQXB4dcpGPiikHawvSWAd6mEn1sGG` | On the same local validator, the DBC pool migrated to the derived DAMM v2 pool. A second wallet bought one token exactly and burned it. Details below. | Pilot fee config and funding, real fee claim/account movements, deployed-network post-migration verification. |
| Solami | `app/solami.py`, project-scoped JSON-RPC path | Cursor, overlap, deduplication and stale-state behavior pass isolated tests using a fake transport. | Project credential, relevant deployed addresses, authenticated live responses, decoded product activity and reconciliation against authoritative accounts. |
| Renderer | Pillow 12.2.0; FFmpeg 8.1.1 on measured Windows host | Sample and four walkthrough MP4s probed as 1920×1080, 30 FPS, 450 frames, 15 seconds, H.264/yuv420p. | Rebenchmark and pin licensed font/runtime on deployment host. |

## Meteora real-program local fixture run

Run on 2026-09-24 using Agave `solana-test-validator 4.2.2`, official DBC SDK repository commit `0c5e375` fixture binaries (`dynamic_bonding_curve.so`, `cp_amm.so`, `amm.so`, `locker.so`, `metaplex.so`, `mercurial_vault.so`, `transfer_hook_counter.so`). Program IDs were the DBC and DAMM v2 IDs above. The mainnet DAMM v2 config `A8gMrEPJkacWkcb3DGwtJwTe16HktSEfvwtuDh2MCtck` was cloned **read-only** into local genesis; its absence in the plain fixture caused `AccountOwnedByWrongProgram` during migration. The DBC pool-authority PDA also needed 1 **local airdropped** SOL for the program's `flash_rent` migration path. No mainnet transaction or spending occurred.

The final successful script run (`integrations/meteora/real-program-gate.mjs`, exit 0) used local mint `9MxAPaq5n9h1xax2JXUu25MD4uxgHw95XiRiDxSR36Dk`, DBC pool `14Lzn1GSouMca8eZmabLEZjVTNBXEoVwiUZivnGN91Jb`, and derived DAMM pool `DcJQp9vPuNPCNJJzngMpQUufjtWQ32j5SR2Z6teN7A3H`:

| Action | Local validator signature / observed result |
| --- | --- |
| Create DBC config and pool | `5Sn9RXJy44d7vjwWxGZ7AxisjSijcgBRALZjFQr2FHFRYJ6Ck9dn2j4XAvxyCE6oswEGr32AF7kAVfmBfgduqD2S`; `4B439H9TaL6eLuAwxZ91eyvC2gpE7VvCQEVcxy6bjNtE9HqDotiMwLSndD3WvPT8chNEnzy7PVjY5dsoKqsss2Mt` |
| Exact-output DBC buy (1,000 test tokens) | `2Bgx3ZdKX1Ju9qtWat6gUz6DSYpypXwTnMVCN6pYWd5KREFzpxgBvzUwMsicmLTosTxf1aMMhcudGHg1DyfKqWW7`; buyer balance `1,000,000,000` base units |
| External SPL burn (one test token) | `5L4RPys14webp6SKcvscQ9CHMms4AaVcBRozu35srtNvaE5XtN2qaneyKDo9uw2gwP1Wai6UNF7W2jRjSviJLYFY`; mint supply decreased by `1,000,000` base units |
| DBC graduation | `2mEtbK5iWrfX74oe8npEFK3rVsXavrYrAREz2tTuorjrHTqdiLHLBV8N7C8dfoKP9hoAuYwhrA3fKnGVbuF1XUyW`; quote reserve reached `30,044,747,159` vs threshold `30,044,747,158` quote base units; progress `2` |
| Fund migration PDA and migrate | `2uZBzUBrgDXH3npmMuruAooDm74KoR4ab9Mm6sUYZPQxjazSdWz2hRCCeREchvTVUpPMyAA54prhnmqhPRnUUVPG`; `a5KdMErwFgLEEsfZErgns8wvZuL8rMLWGNDYezKQnaAN3QKsPxEnwo5vDK3fnH7JZEPmx8jiiY7gHT8oDpSUKZJ`; progress `3` |
| Second-wallet DAMM exact-output buy and external burn | `583YwUzTwA2ME7jUM7m8e3JTTQuL8KK6FkAFtop6VRoBv6P1RdbuLMPA2wA3hwFAAni12tKVk2Lw67mMPL8QFZyJ`; second-wallet balance `1,000,000`; burn `2VzmvH9V5v97E3PpdoeeufyS6m3k2b6Sbz4q2sshDqDBizLVrKc2pujM2HWodpFBEA2vR5Pwcswds69AjoegPS18`; mint supply decreased by another `1,000,000` |

Final read-only reconciliation of this local run: mint supply `999,999,998,000,000` from initial `1,000,000,000,000,000`; DBC base vault `55,080,343,667`, DBC quote vault `3,423,471,219`, DAMM base vault `26,986,191,103,265`, DAMM quote vault `26,986,192,913` base units. Two external burns account for the 2,000,000 supply decrease. The local validator ledger can be reset; these signatures are **not** explorer links, devnet/mainnet activity, WORKDROP program completion records, or customer traction. The extreme test curve and local airdropped SOL do not establish pilot costs or sustainable liquidity.

No WORKDROP onchain redemption transaction was executed. No mainnet money moved, API charges or claimed creator fees were incurred. See [Meteora research](research/meteora.md), [Solami research](research/solami.md), and [readiness](readiness.md) for remaining gates.
