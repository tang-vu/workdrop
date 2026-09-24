use anchor_lang::prelude::*;
use anchor_spl::token_interface::{self, Burn, Mint, TokenAccount, TokenInterface, TransferChecked};

// Placeholder development ID. Replace with a generated program key before deployment.
declare_id!("11111111111111111111111111111111");

#[program]
pub mod workdrop_entitlement {
    use super::*;

    pub fn initialize_batch(ctx: Context<InitializeBatch>, manifest_hash: [u8; 32], credit_amount: u64, deadline_seconds: i64) -> Result<()> {
        require!(credit_amount > 0, WorkdropError::InvalidAmount);
        require!(deadline_seconds > 0 && deadline_seconds <= 7 * 24 * 3600, WorkdropError::InvalidDeadline);
        require!(ctx.accounts.mint.mint_authority.is_none(), WorkdropError::MutableSupply);
        require!(ctx.accounts.mint.freeze_authority.is_none(), WorkdropError::FreezeAuthority);
        require_keys_eq!(ctx.accounts.token_program.key(), anchor_spl::token::ID, WorkdropError::UnsupportedTokenProgram);
        let batch = &mut ctx.accounts.batch;
        batch.mint = ctx.accounts.mint.key();
        batch.token_program = ctx.accounts.token_program.key();
        batch.provider = ctx.accounts.provider.key();
        batch.admission_authority = ctx.accounts.admission_authority.key();
        batch.completion_authority = ctx.accounts.completion_authority.key();
        batch.manifest_hash = manifest_hash;
        batch.credit_amount = credit_amount;
        batch.deadline_seconds = deadline_seconds;
        batch.bump = ctx.bumps.batch;
        Ok(())
    }

    pub fn request(ctx: Context<Request>, nonce: [u8; 16], input_commitment: [u8; 32], admission_valid_until: i64) -> Result<()> {
        let clock = Clock::get()?;
        require!(clock.unix_timestamp <= admission_valid_until, WorkdropError::AdmissionExpired);
        require!(admission_valid_until <= clock.unix_timestamp.checked_add(3600).ok_or(WorkdropError::Overflow)?, WorkdropError::AdmissionTooLong);
        let batch = &ctx.accounts.batch;
        let deadline = clock.unix_timestamp.checked_add(batch.deadline_seconds).ok_or(WorkdropError::Overflow)?;
        let request = &mut ctx.accounts.request;
        request.batch = batch.key();
        request.requester = ctx.accounts.requester.key();
        request.original_token_account = ctx.accounts.requester_token.key();
        request.nonce = nonce;
        request.input_commitment = input_commitment;
        request.manifest_hash = batch.manifest_hash;
        request.mint = batch.mint;
        request.token_program = batch.token_program;
        request.completion_authority = batch.completion_authority;
        request.amount = batch.credit_amount;
        request.deadline = deadline;
        request.state = RequestState::Requested;
        request.bump = ctx.bumps.request;
        let cpi_accounts = TransferChecked {
            from: ctx.accounts.requester_token.to_account_info(),
            mint: ctx.accounts.mint.to_account_info(),
            to: ctx.accounts.escrow.to_account_info(),
            authority: ctx.accounts.requester.to_account_info(),
        };
        token_interface::transfer_checked(CpiContext::new(ctx.accounts.token_program.to_account_info(), cpi_accounts), batch.credit_amount, ctx.accounts.mint.decimals)?;
        Ok(())
    }

    pub fn complete(ctx: Context<Complete>, artifact_hash: [u8; 32], receipt_hash: [u8; 32]) -> Result<()> {
        let clock = Clock::get()?;
        let request = &mut ctx.accounts.request;
        require!(request.state == RequestState::Requested, WorkdropError::Terminal);
        require!(clock.unix_timestamp < request.deadline, WorkdropError::DeadlinePassed);
        require!(artifact_hash != [0; 32] && receipt_hash != [0; 32], WorkdropError::InvalidReceipt);
        let batch_key = request.batch;
        let requester_key = request.requester;
        let nonce = request.nonce;
        let bump = [request.bump];
        let signer_seeds: &[&[u8]] = &[b"request", batch_key.as_ref(), requester_key.as_ref(), &nonce, &bump];
        token_interface::burn(CpiContext::new_with_signer(ctx.accounts.token_program.to_account_info(), Burn {
            mint: ctx.accounts.mint.to_account_info(),
            from: ctx.accounts.escrow.to_account_info(),
            authority: request.to_account_info(),
        }, &[signer_seeds]), request.amount)?;
        request.state = RequestState::Completed;
        request.artifact_hash = artifact_hash;
        request.receipt_hash = receipt_hash;
        request.terminal_at = clock.unix_timestamp;
        Ok(())
    }

    pub fn timeout(ctx: Context<Timeout>) -> Result<()> {
        let clock = Clock::get()?;
        let request = &mut ctx.accounts.request;
        require!(request.state == RequestState::Requested, WorkdropError::Terminal);
        require!(clock.unix_timestamp >= request.deadline, WorkdropError::NotTimedOut);
        let batch_key = request.batch;
        let requester_key = request.requester;
        let nonce = request.nonce;
        let bump = [request.bump];
        let signer_seeds: &[&[u8]] = &[b"request", batch_key.as_ref(), requester_key.as_ref(), &nonce, &bump];
        token_interface::transfer_checked(CpiContext::new_with_signer(ctx.accounts.token_program.to_account_info(), TransferChecked {
            from: ctx.accounts.escrow.to_account_info(),
            mint: ctx.accounts.mint.to_account_info(),
            to: ctx.accounts.original_token_account.to_account_info(),
            authority: request.to_account_info(),
        }, &[signer_seeds]), request.amount, ctx.accounts.mint.decimals)?;
        request.state = RequestState::TimedOut;
        request.terminal_at = clock.unix_timestamp;
        Ok(())
    }
}

#[derive(Accounts)]
pub struct InitializeBatch<'info> {
    #[account(init, payer = provider, space = 8 + Batch::INIT_SPACE, seeds = [b"batch", mint.key().as_ref()], bump)]
    pub batch: Account<'info, Batch>,
    #[account(mut)] pub provider: Signer<'info>,
    pub admission_authority: Signer<'info>,
    pub completion_authority: Signer<'info>,
    pub mint: InterfaceAccount<'info, Mint>,
    pub token_program: Interface<'info, TokenInterface>,
    pub system_program: Program<'info, System>,
}

#[derive(Accounts)]
#[instruction(nonce: [u8; 16])]
pub struct Request<'info> {
    #[account(seeds = [b"batch", mint.key().as_ref()], bump = batch.bump, has_one = mint, has_one = token_program, has_one = admission_authority)]
    pub batch: Account<'info, Batch>,
    #[account(init, payer = requester, space = 8 + RedemptionRequest::INIT_SPACE, seeds = [b"request", batch.key().as_ref(), requester.key().as_ref(), &nonce], bump)]
    pub request: Account<'info, RedemptionRequest>,
    #[account(init, payer = requester, token::mint = mint, token::authority = request, token::token_program = token_program, seeds = [b"escrow", request.key().as_ref()], bump)]
    pub escrow: InterfaceAccount<'info, TokenAccount>,
    #[account(mut)] pub requester: Signer<'info>,
    pub admission_authority: Signer<'info>,
    #[account(mut, token::mint = mint, token::authority = requester, token::token_program = token_program)]
    pub requester_token: InterfaceAccount<'info, TokenAccount>,
    pub mint: InterfaceAccount<'info, Mint>,
    pub token_program: Interface<'info, TokenInterface>,
    pub system_program: Program<'info, System>,
}

#[derive(Accounts)]
pub struct Complete<'info> {
    #[account(mut, has_one = mint, has_one = token_program, has_one = completion_authority, seeds = [b"request", request.batch.as_ref(), request.requester.as_ref(), &request.nonce], bump = request.bump)]
    pub request: Account<'info, RedemptionRequest>,
    pub completion_authority: Signer<'info>,
    #[account(mut, token::mint = mint, token::authority = request, token::token_program = token_program, seeds = [b"escrow", request.key().as_ref()], bump)]
    pub escrow: InterfaceAccount<'info, TokenAccount>,
    #[account(mut)] pub mint: InterfaceAccount<'info, Mint>,
    pub token_program: Interface<'info, TokenInterface>,
}

#[derive(Accounts)]
pub struct Timeout<'info> {
    #[account(mut, has_one = mint, has_one = token_program, has_one = original_token_account, seeds = [b"request", request.batch.as_ref(), request.requester.as_ref(), &request.nonce], bump = request.bump)]
    pub request: Account<'info, RedemptionRequest>,
    #[account(mut, token::mint = mint, token::authority = request, token::token_program = token_program, seeds = [b"escrow", request.key().as_ref()], bump)]
    pub escrow: InterfaceAccount<'info, TokenAccount>,
    #[account(mut, token::mint = mint, token::authority = request.requester, token::token_program = token_program)]
    pub original_token_account: InterfaceAccount<'info, TokenAccount>,
    pub mint: InterfaceAccount<'info, Mint>,
    pub token_program: Interface<'info, TokenInterface>,
}

#[account]
#[derive(InitSpace)]
pub struct Batch {
    pub mint: Pubkey,
    pub token_program: Pubkey,
    pub provider: Pubkey,
    pub admission_authority: Pubkey,
    pub completion_authority: Pubkey,
    pub manifest_hash: [u8; 32],
    pub credit_amount: u64,
    pub deadline_seconds: i64,
    pub bump: u8,
}

#[account]
#[derive(InitSpace)]
pub struct RedemptionRequest {
    pub batch: Pubkey,
    pub requester: Pubkey,
    pub original_token_account: Pubkey,
    pub nonce: [u8; 16],
    pub input_commitment: [u8; 32],
    pub manifest_hash: [u8; 32],
    pub mint: Pubkey,
    pub token_program: Pubkey,
    pub completion_authority: Pubkey,
    pub amount: u64,
    pub deadline: i64,
    pub state: RequestState,
    pub artifact_hash: [u8; 32],
    pub receipt_hash: [u8; 32],
    pub terminal_at: i64,
    pub bump: u8,
}

#[derive(AnchorSerialize, AnchorDeserialize, Clone, Copy, PartialEq, Eq, InitSpace)]
pub enum RequestState { Requested, Completed, TimedOut }

#[error_code]
pub enum WorkdropError {
    #[msg("Credit amount must be positive")] InvalidAmount,
    #[msg("Invalid delivery deadline policy")] InvalidDeadline,
    #[msg("Mint authority must be revoked")] MutableSupply,
    #[msg("Freeze authority must be revoked")] FreezeAuthority,
    #[msg("Admission expired")] AdmissionExpired,
    #[msg("Admission validity exceeds policy")] AdmissionTooLong,
    #[msg("Arithmetic overflow")] Overflow,
    #[msg("Request already has a terminal state")] Terminal,
    #[msg("Completion deadline passed")] DeadlinePassed,
    #[msg("Receipt commitments are required")] InvalidReceipt,
    #[msg("Request is not yet timed out")] NotTimedOut,
    #[msg("Pilot supports only the classic SPL token program")] UnsupportedTokenProgram,
}
