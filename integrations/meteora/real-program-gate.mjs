/** Local validator only. Uses fresh, ephemeral test wallets and official Meteora fixtures. */
import BN from 'bn.js';
import {
  Connection, Keypair, LAMPORTS_PER_SOL, sendAndConfirmTransaction, SystemProgram, Transaction,
} from '@solana/web3.js';
import {
  createBurnInstruction, getAccount, getAssociatedTokenAddressSync, getMint,
  NATIVE_MINT, TOKEN_PROGRAM_ID,
} from '@solana/spl-token';
import {
  ActivationType, BaseFeeMode, buildCurveWithCustomSqrtPrices,
  CollectFeeMode, createSqrtPrices, DammV2BaseFeeMode, DammV2DynamicFeeMode,
  DAMM_V2_MIGRATION_FEE_ADDRESS, deriveDbcPoolAddress, deriveDbcPoolAuthority, DynamicBondingCurveClient,
  deriveDammV2PoolAddress,
  MigratedCollectFeeMode, MigrationFeeOption, MigrationOption, SwapMode,
  TokenAuthorityOption, TokenDecimal, TokenType,
} from '@meteora-ag/dynamic-bonding-curve-sdk';
import { CpAmm, SwapMode as DammSwapMode } from '@meteora-ag/cp-amm-sdk';

const rpc = process.env.WORKDROP_LOCAL_RPC ?? 'http://127.0.0.1:8899';
if (!/^http:\/\/(127\.0\.0\.1|localhost):8899$/.test(rpc))
  throw new Error('real-program gate only runs against local validator port 8899');
const connection = new Connection(rpc, 'confirmed');
const client = new DynamicBondingCurveClient(connection, 'confirmed');
const partner = Keypair.generate();
const creator = Keypair.generate();
const buyer = Keypair.generate();
const config = Keypair.generate();
const baseMint = Keypair.generate();
const dammConfig = DAMM_V2_MIGRATION_FEE_ADDRESS[6];

async function fund(wallet, sol = 30) {
  const sig = await connection.requestAirdrop(wallet.publicKey, sol * LAMPORTS_PER_SOL);
  const blockhash = await connection.getLatestBlockhash();
  await connection.confirmTransaction({ signature: sig, ...blockhash }, 'confirmed');
}

async function send(tx, signers) {
  tx.feePayer = signers[0].publicKey;
  return sendAndConfirmTransaction(connection, tx, signers, { commitment: 'confirmed' });
}

const sqrtPrices = createSqrtPrices(
  [0.000000001, 0.00000000105, 0.000000002, 0.000001],
  TokenDecimal.SIX, TokenDecimal.NINE,
);
const curve = buildCurveWithCustomSqrtPrices({
  token: { tokenType: TokenType.SPLToken, tokenBaseDecimal: TokenDecimal.SIX,
    tokenQuoteDecimal: TokenDecimal.NINE,
    tokenAuthorityOption: TokenAuthorityOption.PartnerUpdateAuthority,
    totalTokenSupply: 1_000_000_000, leftover: 1000 },
  fee: { baseFeeParams: { baseFeeMode: BaseFeeMode.FeeSchedulerLinear,
    feeSchedulerParam: { startingFeeBps: 120, endingFeeBps: 120,
      numberOfPeriod: 0, totalDuration: 0 } },
    dynamicFeeEnabled: true, collectFeeMode: CollectFeeMode.QuoteToken,
    creatorTradingFeePercentage: 0, poolCreationFee: 1,
    enableFirstSwapWithMinFee: false },
  migration: { migrationOption: MigrationOption.MET_DAMM_V2,
    migrationFeeOption: MigrationFeeOption.Customizable,
    migrationFee: { feePercentage: 10, creatorFeePercentage: 50 },
    migratedPoolFee: { collectFeeMode: MigratedCollectFeeMode.QuoteToken,
      dynamicFee: DammV2DynamicFeeMode.Enabled, poolFeeBps: 120,
      baseFeeMode: DammV2BaseFeeMode.FeeTimeSchedulerLinear } },
  liquidityDistribution: { partnerLiquidityPercentage: 0,
    partnerPermanentLockedLiquidityPercentage: 100,
    creatorLiquidityPercentage: 0,
    creatorPermanentLockedLiquidityPercentage: 0 },
  lockedVesting: { totalLockedVestingAmount: 0, numberOfVestingPeriod: 0,
    cliffUnlockAmount: 0, totalVestingDuration: 0,
    cliffDurationFromMigrationTime: 0 },
  activationType: ActivationType.Timestamp, sqrtPrices, liquidityWeights: [2, 1, 1],
});

console.log('validator', await connection.getVersion());
await Promise.all([fund(partner), fund(creator), fund(buyer)]);
const configTx = await client.partner.createConfig({
  config: config.publicKey, feeClaimer: partner.publicKey,
  leftoverReceiver: partner.publicKey, payer: partner.publicKey,
  quoteMint: NATIVE_MINT, ...curve,
});
console.log('createConfig', await send(configTx, [partner, config]));
const poolTx = await client.creator.createPool({
  baseMint: baseMint.publicKey, config: config.publicKey,
  name: 'WORKDROP local gate', symbol: 'WDTEST',
  uri: 'https://example.invalid/workdrop-local-gate.json',
  payer: creator.publicKey, poolCreator: creator.publicKey,
});
console.log('createPool', await send(poolTx, [creator, baseMint]));
const pool = deriveDbcPoolAddress(NATIVE_MINT, baseMint.publicKey, config.publicKey);
const cfg = await client.state.getPoolConfig(config.publicKey);
console.log('pool', pool.toBase58(), 'mint', baseMint.publicKey.toBase58(),
  'migrationThreshold', cfg.migrationQuoteThreshold.toString(),
  'swapBaseAmount', cfg.swapBaseAmount.toString());
const credit = new BN(1_000_000);
const purchaseAmount = credit.mul(new BN(1000));
const buyQuote = client.pool.swapQuote2({
  virtualPool: await client.state.getPool(pool), config: cfg,
  swapBaseForQuote: false, swapMode: SwapMode.ExactOut,
  amountOut: purchaseAmount, slippageBps: 100, hasReferral: false,
  eligibleForFirstSwapWithMinFee: false, currentPoint: new BN(Math.floor(Date.now() / 1000)),
});
console.log('buyQuote', buyQuote.includedFeeInputAmount.toString(), buyQuote.maximumAmountIn.toString());
const buyTx = await client.pool.swap2({
  pool, owner: buyer.publicKey, swapBaseForQuote: false,
  swapMode: SwapMode.ExactOut, amountOut: purchaseAmount,
  maximumAmountIn: buyQuote.maximumAmountIn, referralTokenAccount: null,
});
console.log('buy', await send(buyTx, [buyer]));
const buyerAta = getAssociatedTokenAddressSync(baseMint.publicKey, buyer.publicKey);
console.log('buyerBeforeBurn', (await getAccount(connection, buyerAta)).amount.toString());
const mintBefore = (await getMint(connection, baseMint.publicKey)).supply;
const burnTx = new (await import('@solana/web3.js')).Transaction().add(
  createBurnInstruction(buyerAta, baseMint.publicKey, buyer.publicKey, credit, [], TOKEN_PROGRAM_ID),
);
console.log('externalBurn', await send(burnTx, [buyer]));
const mintAfter = (await getMint(connection, baseMint.publicKey)).supply;
if (mintBefore - mintAfter !== 1_000_000n) throw new Error('mint supply burn delta mismatch');
console.log('burnDelta', (mintBefore - mintAfter).toString());
console.log('curveState', (await client.state.getPool(pool)).poolState.quoteReserve.toString());
let completed;
for (let attempt = 0; attempt < 8; attempt++) {
  completed = await client.state.getPool(pool);
  if (completed.poolState.quoteReserve.gte(cfg.migrationQuoteThreshold)) break;
  await fund(buyer, 100);
  const graduationIn = new BN(60 * LAMPORTS_PER_SOL);
  const graduationQuote = client.pool.swapQuote2({
    virtualPool: completed, config: cfg,
    swapBaseForQuote: false, swapMode: SwapMode.PartialFill,
    amountIn: graduationIn, slippageBps: 500, hasReferral: false,
    eligibleForFirstSwapWithMinFee: false, currentPoint: new BN(Math.floor(Date.now() / 1000)),
  });
  console.log('graduationQuote', attempt, graduationQuote.outputAmount.toString(),
    graduationQuote.minimumAmountOut?.toString(), graduationQuote.amountLeft.toString());
  const graduationTx = await client.pool.swap2({
    pool, owner: buyer.publicKey, swapBaseForQuote: false,
    swapMode: SwapMode.PartialFill, amountIn: graduationIn,
    minimumAmountOut: graduationQuote.minimumAmountOut, referralTokenAccount: null,
  });
  console.log('graduationSwap', await send(graduationTx, [buyer]));
}
completed = await client.state.getPool(pool);
console.log('afterGraduation', 'reserve', completed.poolState.quoteReserve.toString(),
  'progress', completed.poolState.migrationProgress);
if (completed.poolState.quoteReserve.lt(cfg.migrationQuoteThreshold))
  throw new Error('curve did not reach graduation threshold');
const dbcPoolAuthority = deriveDbcPoolAuthority();
console.log('fundMigrationRent', await send(new Transaction().add(SystemProgram.transfer({
  fromPubkey: creator.publicKey, toPubkey: dbcPoolAuthority, lamports: LAMPORTS_PER_SOL,
})), [creator]));
const migration = await client.migration.migrateToDammV2({
  pool, dammConfig, payer: creator.publicKey,
});
console.log('migrationTxBuilt', migration.transaction.instructions.length);
console.log('migration', await send(migration.transaction,
  [creator, migration.firstPositionNftKeypair, migration.secondPositionNftKeypair]));
console.log('afterMigration', (await client.state.getPool(pool)).poolState.migrationProgress);
const dammPool = deriveDammV2PoolAddress(dammConfig, baseMint.publicKey, NATIVE_MINT);
const damm = new CpAmm(connection);
const dammState = await damm.fetchPoolState(dammPool);
console.log('dammPool', dammPool.toBase58(), 'liquidity', dammState.liquidity.toString());
const secondBuyer = Keypair.generate();
await fund(secondBuyer, 10);
const dammQuote = damm.getQuote2({
  poolState: dammState, inputTokenMint: NATIVE_MINT,
  swapMode: DammSwapMode.ExactOut, amountOut: credit,
  slippage: 500, currentPoint: new BN(Math.floor(Date.now() / 1000)),
  tokenADecimal: 6, tokenBDecimal: 9, hasReferral: false,
});
console.log('dammQuote', dammQuote.includedFeeInputAmount.toString(),
  dammQuote.maximumAmountIn?.toString());
const dammBuy = await damm.swap2({
  payer: secondBuyer.publicKey, pool: dammPool, inputTokenMint: NATIVE_MINT,
  outputTokenMint: baseMint.publicKey,
  tokenAMint: dammState.tokenAMint, tokenBMint: dammState.tokenBMint,
  tokenAVault: dammState.tokenAVault, tokenBVault: dammState.tokenBVault,
  tokenAProgram: TOKEN_PROGRAM_ID, tokenBProgram: TOKEN_PROGRAM_ID,
  referralTokenAccount: null, poolState: dammState,
  swapMode: DammSwapMode.ExactOut, amountOut: credit,
  maximumAmountIn: dammQuote.maximumAmountIn,
});
console.log('dammBuy', await send(dammBuy, [secondBuyer]));
const secondAta = getAssociatedTokenAddressSync(baseMint.publicKey, secondBuyer.publicKey);
console.log('secondBuyerBalance', (await getAccount(connection, secondAta)).amount.toString());
const supplyBeforeSecondBurn = (await getMint(connection, baseMint.publicKey)).supply;
console.log('secondBurn', await send(new Transaction().add(createBurnInstruction(
  secondAta, baseMint.publicKey, secondBuyer.publicKey, credit, [], TOKEN_PROGRAM_ID,
)), [secondBuyer]));
const supplyAfterSecondBurn = (await getMint(connection, baseMint.publicKey)).supply;
if (supplyBeforeSecondBurn - supplyAfterSecondBurn !== 1_000_000n)
  throw new Error('post-migration burn delta mismatch');
console.log('postMigrationBurnDelta', (supplyBeforeSecondBurn - supplyAfterSecondBurn).toString());
