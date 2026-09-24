import BN from 'bn.js';
import {
  ActivationType,
  DAMM_V2_PROGRAM_ID,
  DYNAMIC_BONDING_CURVE_PROGRAM_ID,
  DynamicBondingCurveClient,
  SwapMode as DbcSwapMode,
  deriveDammV2PoolAddress,
  getCurrentPoint,
} from '@meteora-ag/dynamic-bonding-curve-sdk';
import {
  CpAmm,
  SwapMode as DammSwapMode,
} from '@meteora-ag/cp-amm-sdk';
import { getMint, TOKEN_2022_PROGRAM_ID, TOKEN_PROGRAM_ID } from '@solana/spl-token';
import { type Commitment, Connection, PublicKey, type Transaction } from '@solana/web3.js';

export type Cluster = 'localnet' | 'devnet' | 'mainnet-beta';
export type Market = 'dbc' | 'damm-v2';
export type Direction = 'buy' | 'sell';
export type MarketState = 'trading-dbc' | 'curve-complete-awaiting-migration' | 'trading-damm-v2' | 'migration-state-inconsistent';

export interface AdapterConfig {
  rpcUrl: string;
  cluster: Cluster;
  dbcPool: string;
  baseMint: string;
  quoteMint: string;
  creditBaseUnits: string;
  /** The selected DAMM migration fee config key. Required to resolve its pool PDA. */
  dammConfig: string;
  commitment?: Commitment;
  maxQuoteAgeSlots?: number;
  maxSlippageBps?: number;
}

export interface MarketSnapshot {
  cluster: Cluster;
  slot: number;
  dbcPool: string;
  dammPool: string;
  state: MarketState;
  quoteReserve: string;
  migrationQuoteThreshold: string;
  migrationProgress: number;
  baseMintSupply: string;
  mintAuthority: string | null;
  freezeAuthority: string | null;
  baseDecimals: number;
  quoteDecimals: number;
}

export interface TradeQuote {
  market: Market;
  direction: Direction;
  cluster: Cluster;
  pool: string;
  slot: number;
  validUntilSlot: number;
  wholeCredits: string;
  baseUnits: string;
  expectedInput: string;
  maximumInput: string | null;
  expectedOutput: string;
  minimumOutput: string | null;
  tradingFee: string | null;
  protocolFee: string | null;
  priceImpact: string | null;
  slippageBps: number;
}

export interface PreparedTrade {
  quote: TradeQuote;
  transaction: Transaction;
  /** Caller must simulate, obtain a wallet signature, broadcast, and reconcile finalized balances. */
  requiredSigner: string;
}

const MAX_U64 = (1n << 64n) - 1n;

function baseUnits(value: string, name: string): bigint {
  if (!/^[1-9][0-9]*$/.test(value)) throw new Error(`${name} must be a positive integer string`);
  const amount = BigInt(value);
  if (amount > MAX_U64) throw new Error(`${name} exceeds u64`);
  return amount;
}

function boundedBps(value: number, max: number): number {
  if (!Number.isInteger(value) || value < 0 || value > max) throw new Error(`slippageBps must be 0..${max}`);
  return value;
}

function key(value: string, name: string): PublicKey {
  try { return new PublicKey(value); } catch { throw new Error(`${name} is not a Solana public key`); }
}

function bn(value: bigint): BN { return new BN(value.toString(10)); }
function decimal(value: { toString(radix?: number): string }): string { return value.toString(10); }

export class MeteoraAdapter {
  readonly connection: Connection;
  readonly dbc: DynamicBondingCurveClient;
  readonly damm: CpAmm;
  readonly pool: PublicKey;
  readonly baseMint: PublicKey;
  readonly quoteMint: PublicKey;
  readonly dammConfig: PublicKey;
  readonly dammPool: PublicKey;
  readonly creditBaseUnits: bigint;
  readonly maxQuoteAgeSlots: number;
  readonly maxSlippageBps: number;
  readonly cluster: Cluster;
  readonly commitment: Commitment;

  constructor(config: AdapterConfig) {
    this.cluster = config.cluster;
    this.commitment = config.commitment ?? 'confirmed';
    this.connection = new Connection(config.rpcUrl, this.commitment);
    this.dbc = new DynamicBondingCurveClient(this.connection, this.commitment);
    this.damm = new CpAmm(this.connection);
    this.pool = key(config.dbcPool, 'dbcPool');
    this.baseMint = key(config.baseMint, 'baseMint');
    this.quoteMint = key(config.quoteMint, 'quoteMint');
    this.dammConfig = key(config.dammConfig, 'dammConfig');
    this.dammPool = deriveDammV2PoolAddress(this.dammConfig, this.baseMint, this.quoteMint);
    this.creditBaseUnits = baseUnits(config.creditBaseUnits, 'creditBaseUnits');
    this.maxQuoteAgeSlots = config.maxQuoteAgeSlots ?? 20;
    this.maxSlippageBps = config.maxSlippageBps ?? 500;
    if (!Number.isInteger(this.maxQuoteAgeSlots) || this.maxQuoteAgeSlots < 1) throw new Error('maxQuoteAgeSlots must be positive');
    boundedBps(this.maxSlippageBps, 10_000);
  }

  private creditAmount(wholeCredits: string): bigint {
    const amount = baseUnits(wholeCredits, 'wholeCredits') * this.creditBaseUnits;
    if (amount > MAX_U64) throw new Error('trade amount exceeds u64');
    return amount;
  }

  private validateQuoteEnvelope(quote: TradeQuote, market: Market, pool: PublicKey): void {
    if (quote.market !== market || quote.cluster !== this.cluster || quote.pool !== pool.toBase58())
      throw new Error('quote market mismatch');
    if (quote.baseUnits !== this.creditAmount(quote.wholeCredits).toString())
      throw new Error('quote amount mismatch');
    if (!Number.isSafeInteger(quote.slot) || !Number.isSafeInteger(quote.validUntilSlot) ||
        quote.validUntilSlot < quote.slot || quote.validUntilSlot > quote.slot + this.maxQuoteAgeSlots)
      throw new Error('invalid quote validity window');
    boundedBps(quote.slippageBps, this.maxSlippageBps);
    if (quote.direction === 'buy') baseUnits(quote.maximumInput ?? '', 'maximumInput');
    else baseUnits(quote.minimumOutput ?? '', 'minimumOutput');
  }

  private async dbcAccounts() {
    const pool = await this.dbc.state.getPool(this.pool);
    if (!pool) throw new Error('DBC pool account does not exist');
    const config = await this.dbc.state.getPoolConfig(pool.poolState.config);
    if (!config) throw new Error('DBC config account does not exist');
    if (!pool.poolState.baseMint.equals(this.baseMint)) throw new Error('DBC base mint mismatch');
    if (config.tokenType !== 0) throw new Error('WORKDROP entitlement requires classic SPL Token, not Token-2022');
    if (!config.quoteMint.equals(this.quoteMint)) throw new Error('DBC quote mint mismatch');
    if (config.migrationOption !== 1) throw new Error('DBC pool does not target DAMM v2');
    return { pool, config };
  }

  async snapshot(): Promise<MarketSnapshot> {
    const { pool, config } = await this.dbcAccounts();
    const [slot, dammAccount, baseMint] = await Promise.all([
      this.connection.getSlot(this.commitment),
      this.connection.getAccountInfo(this.dammPool, this.commitment),
      getMint(this.connection, this.baseMint, this.commitment,
        config.tokenType === 0 ? TOKEN_PROGRAM_ID : TOKEN_2022_PROGRAM_ID),
    ]);
    if (dammAccount && !dammAccount.owner.equals(DAMM_V2_PROGRAM_ID)) throw new Error('derived DAMM address has wrong owner');
    const progress = pool.poolState.migrationProgress;
    const complete = pool.poolState.quoteReserve.gte(config.migrationQuoteThreshold);
    let state: MarketState;
    if (dammAccount && progress === 3) {
      const dammState = await this.damm.fetchPoolState(this.dammPool);
      const tokensMatch = [dammState.tokenAMint.toBase58(), dammState.tokenBMint.toBase58()].sort().join(':') ===
        [this.baseMint.toBase58(), this.quoteMint.toBase58()].sort().join(':');
      if (!tokensMatch) throw new Error('DAMM pool mint mismatch');
      state = 'trading-damm-v2';
    } else if (dammAccount || progress === 3) state = 'migration-state-inconsistent';
    else if (complete) state = 'curve-complete-awaiting-migration';
    else state = 'trading-dbc';
    const quoteMint = await getMint(this.connection, this.quoteMint, this.commitment,
      config.quoteTokenFlag === 0 ? TOKEN_PROGRAM_ID : TOKEN_2022_PROGRAM_ID);
    return {
      cluster: this.cluster, slot, dbcPool: this.pool.toBase58(), dammPool: this.dammPool.toBase58(), state,
      quoteReserve: decimal(pool.poolState.quoteReserve), migrationQuoteThreshold: decimal(config.migrationQuoteThreshold),
      migrationProgress: progress, baseMintSupply: baseMint.supply.toString(),
      mintAuthority: baseMint.mintAuthority?.toBase58() ?? null, freezeAuthority: baseMint.freezeAuthority?.toBase58() ?? null,
      baseDecimals: baseMint.decimals, quoteDecimals: quoteMint.decimals,
    };
  }

  async quoteDbcBuy(wholeCredits: string, slippageBps: number): Promise<TradeQuote> {
    const amount = this.creditAmount(wholeCredits);
    const slippage = boundedBps(slippageBps, this.maxSlippageBps);
    const { pool, config } = await this.dbcAccounts();
    if (pool.poolState.quoteReserve.gte(config.migrationQuoteThreshold) || pool.poolState.migrationProgress !== 0)
      throw new Error('DBC buying is closed; refresh market state');
    const [slot, currentPoint] = await Promise.all([
      this.connection.getSlot(this.commitment),
      getCurrentPoint(this.connection, config.activationType as ActivationType),
    ]);
    const quote = this.dbc.pool.swapQuote2({
      virtualPool: pool, config, swapBaseForQuote: false, swapMode: DbcSwapMode.ExactOut,
      amountOut: bn(amount), slippageBps: slippage, currentPoint,
      hasReferral: false, eligibleForFirstSwapWithMinFee: false,
    });
    if (!quote.maximumAmountIn || quote.outputAmount.lt(bn(amount))) throw new Error('exact-output quote unavailable');
    return {
      market: 'dbc', direction: 'buy', cluster: this.cluster, pool: this.pool.toBase58(), slot,
      validUntilSlot: slot + this.maxQuoteAgeSlots, wholeCredits, baseUnits: amount.toString(),
      expectedInput: decimal(quote.includedFeeInputAmount), maximumInput: decimal(quote.maximumAmountIn),
      expectedOutput: decimal(quote.outputAmount), minimumOutput: null,
      tradingFee: decimal(quote.tradingFee), protocolFee: decimal(quote.protocolFee), priceImpact: null, slippageBps: slippage,
    };
  }

  async quoteDbcSell(wholeCredits: string, slippageBps: number): Promise<TradeQuote> {
    const amount = this.creditAmount(wholeCredits);
    const slippage = boundedBps(slippageBps, this.maxSlippageBps);
    const { pool, config } = await this.dbcAccounts();
    if (pool.poolState.quoteReserve.gte(config.migrationQuoteThreshold) || pool.poolState.migrationProgress !== 0)
      throw new Error('DBC selling is closed; refresh market state');
    const [slot, currentPoint] = await Promise.all([
      this.connection.getSlot(this.commitment),
      getCurrentPoint(this.connection, config.activationType as ActivationType),
    ]);
    const quote = this.dbc.pool.swapQuote2({
      virtualPool: pool, config, swapBaseForQuote: true, swapMode: DbcSwapMode.ExactIn,
      amountIn: bn(amount), slippageBps: slippage, currentPoint,
      hasReferral: false, eligibleForFirstSwapWithMinFee: false,
    });
    if (!quote.minimumAmountOut || quote.amountLeft.gt(new BN(0))) throw new Error('exact-input sell quote unavailable');
    return {
      market: 'dbc', direction: 'sell', cluster: this.cluster, pool: this.pool.toBase58(), slot,
      validUntilSlot: slot + this.maxQuoteAgeSlots, wholeCredits, baseUnits: amount.toString(),
      expectedInput: amount.toString(), maximumInput: null,
      expectedOutput: decimal(quote.outputAmount), minimumOutput: decimal(quote.minimumAmountOut),
      tradingFee: decimal(quote.tradingFee), protocolFee: decimal(quote.protocolFee), priceImpact: null, slippageBps: slippage,
    };
  }

  private async dammAccounts() {
    const snapshot = await this.snapshot();
    if (snapshot.state !== 'trading-damm-v2') throw new Error(`DAMM trading unavailable: ${snapshot.state}`);
    const pool = await this.damm.fetchPoolState(this.dammPool);
    const tokenAMintInfo = await this.connection.getAccountInfo(pool.tokenAMint, this.commitment);
    const tokenBMintInfo = await this.connection.getAccountInfo(pool.tokenBMint, this.commitment);
    if (!tokenAMintInfo || !tokenBMintInfo) throw new Error('DAMM mint account missing');
    const supportedProgram = (program: PublicKey) => program.equals(TOKEN_PROGRAM_ID) || program.equals(TOKEN_2022_PROGRAM_ID);
    if (!supportedProgram(tokenAMintInfo.owner) || !supportedProgram(tokenBMintInfo.owner))
      throw new Error('unsupported DAMM token program');
    const [mintA, mintB] = await Promise.all([
      getMint(this.connection, pool.tokenAMint, this.commitment, tokenAMintInfo.owner),
      getMint(this.connection, pool.tokenBMint, this.commitment, tokenBMintInfo.owner),
    ]);
    return { snapshot, pool, mintA, mintB, tokenAProgram: tokenAMintInfo.owner, tokenBProgram: tokenBMintInfo.owner };
  }

  async quoteDammBuy(wholeCredits: string, slippageBps: number): Promise<TradeQuote> {
    return this.quoteDamm('buy', wholeCredits, slippageBps);
  }

  async quoteDammSell(wholeCredits: string, slippageBps: number): Promise<TradeQuote> {
    return this.quoteDamm('sell', wholeCredits, slippageBps);
  }

  private async quoteDamm(direction: Direction, wholeCredits: string, slippageBps: number): Promise<TradeQuote> {
    const amount = this.creditAmount(wholeCredits);
    const slippage = boundedBps(slippageBps, this.maxSlippageBps);
    const { snapshot, pool, mintA, mintB } = await this.dammAccounts();
    const currentPoint = await getCurrentPoint(this.connection, pool.activationType as ActivationType);
    const inputTokenMint = direction === 'buy' ? this.quoteMint : this.baseMint;
    const quoteParams = {
      poolState: pool, inputTokenMint, slippage, currentPoint,
      tokenADecimal: mintA.decimals, tokenBDecimal: mintB.decimals, hasReferral: false,
    };
    const quote = direction === 'buy'
      ? this.damm.getQuote2({ ...quoteParams, swapMode: DammSwapMode.ExactOut, amountOut: bn(amount) })
      : this.damm.getQuote2({ ...quoteParams, swapMode: DammSwapMode.ExactIn, amountIn: bn(amount) });
    if (direction === 'buy' && (!quote.maximumAmountIn || quote.outputAmount.lt(bn(amount))))
      throw new Error('DAMM exact-output quote unavailable');
    if (direction === 'sell' && (!quote.minimumAmountOut || quote.amountLeft.gt(new BN(0))))
      throw new Error('DAMM exact-input quote unavailable');
    return {
      market: 'damm-v2', direction, cluster: this.cluster, pool: this.dammPool.toBase58(),
      slot: snapshot.slot, validUntilSlot: snapshot.slot + this.maxQuoteAgeSlots,
      wholeCredits, baseUnits: amount.toString(),
      expectedInput: direction === 'buy' ? decimal(quote.includedFeeInputAmount) : amount.toString(),
      maximumInput: quote.maximumAmountIn ? decimal(quote.maximumAmountIn) : null,
      expectedOutput: decimal(quote.outputAmount),
      minimumOutput: quote.minimumAmountOut ? decimal(quote.minimumAmountOut) : null,
      tradingFee: decimal(quote.claimingFee.add(quote.compoundingFee)),
      protocolFee: decimal(quote.protocolFee), priceImpact: quote.priceImpact.toString(), slippageBps: slippage,
    };
  }

  async prepareDammTrade(quote: TradeQuote, owner: string): Promise<PreparedTrade> {
    this.validateQuoteEnvelope(quote, 'damm-v2', this.dammPool);
    const slot = await this.connection.getSlot(this.commitment);
    if (slot > quote.validUntilSlot || slot < quote.slot) throw new Error('stale quote');
    const fresh = await this.quoteDamm(quote.direction, quote.wholeCredits, quote.slippageBps);
    if (quote.direction === 'buy' && BigInt(fresh.maximumInput!) > BigInt(quote.maximumInput!))
      throw new Error('market moved beyond maximum input; re-quote');
    if (quote.direction === 'sell' && BigInt(fresh.minimumOutput!) < BigInt(quote.minimumOutput!))
      throw new Error('market moved below minimum output; re-quote');
    const { pool, tokenAProgram, tokenBProgram } = await this.dammAccounts();
    const signer = key(owner, 'owner');
    const params = {
      payer: signer, pool: this.dammPool,
      inputTokenMint: quote.direction === 'buy' ? this.quoteMint : this.baseMint,
      outputTokenMint: quote.direction === 'buy' ? this.baseMint : this.quoteMint,
      tokenAMint: pool.tokenAMint, tokenBMint: pool.tokenBMint,
      tokenAVault: pool.tokenAVault, tokenBVault: pool.tokenBVault,
      tokenAProgram, tokenBProgram, referralTokenAccount: null,
      poolState: pool,
    };
    const transaction = quote.direction === 'buy'
      ? await this.damm.swap2({ ...params, swapMode: DammSwapMode.ExactOut,
          amountOut: bn(BigInt(quote.baseUnits)), maximumAmountIn: bn(BigInt(quote.maximumInput!)) })
      : await this.damm.swap2({ ...params, swapMode: DammSwapMode.ExactIn,
          amountIn: bn(BigInt(quote.baseUnits)), minimumAmountOut: bn(BigInt(quote.minimumOutput!)) });
    return { quote, transaction, requiredSigner: signer.toBase58() };
  }

  async prepareDbcTrade(quote: TradeQuote, owner: string): Promise<PreparedTrade> {
    this.validateQuoteEnvelope(quote, 'dbc', this.pool);
    const slot = await this.connection.getSlot(this.commitment);
    if (slot > quote.validUntilSlot || slot < quote.slot) throw new Error('stale quote');
    const fresh = quote.direction === 'buy'
      ? await this.quoteDbcBuy(quote.wholeCredits, quote.slippageBps)
      : await this.quoteDbcSell(quote.wholeCredits, quote.slippageBps);
    if (quote.direction === 'buy' && BigInt(fresh.maximumInput!) > BigInt(quote.maximumInput!))
      throw new Error('market moved beyond maximum input; re-quote');
    if (quote.direction === 'sell' && BigInt(fresh.minimumOutput!) < BigInt(quote.minimumOutput!))
      throw new Error('market moved below minimum output; re-quote');
    const signer = key(owner, 'owner');
    const transaction = quote.direction === 'buy'
      ? await this.dbc.pool.swap2({
          pool: this.pool, owner: signer, swapBaseForQuote: false, swapMode: DbcSwapMode.ExactOut,
          amountOut: bn(BigInt(quote.baseUnits)), maximumAmountIn: bn(BigInt(quote.maximumInput!)), referralTokenAccount: null,
        })
      : await this.dbc.pool.swap2({
          pool: this.pool, owner: signer, swapBaseForQuote: true, swapMode: DbcSwapMode.ExactIn,
          amountIn: bn(BigInt(quote.baseUnits)), minimumAmountOut: bn(BigInt(quote.minimumOutput!)), referralTokenAccount: null,
        });
    return { quote, transaction, requiredSigner: signer.toBase58() };
  }
}

export { DYNAMIC_BONDING_CURVE_PROGRAM_ID, DAMM_V2_PROGRAM_ID };
