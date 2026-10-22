# Stability-mode guard composition in MarketV2 (L7187-L7390) over TreasuryV2/FxStableMath (L9437-L9620, L8039-L8218).
# Single price source (min = max = twap = p) so the guard reads are price-consistent; base token 18 dec, rate 1.
# Run: python3 -I stability.py
PREC = 10**18
FEE = 10**18                                  # MarketV2.FEE_PRECISION L7009


class Revert(Exception):
    pass


class Sys:
    def __init__(s, B, F, X, p):
        s.B, s.F, s.X, s.p = B, F, X, p
        s.SR = 13 * 10**17                     # stabilityRatio 1.3
        s.f_mint = (25 * 10**14, 0)            # default 0.25%, delta 0
        s.x_mint = (10**16, -10**16)           # default 1%, delta -1%  (0% while it helps leave stability mode)
        s.x_redeem = (10**16, 7 * 10**16)      # default 1%, delta +7%  (8% when entering/staying in stability mode)
        s.fMintPausedInSM = True               # L7214
        s.xRedeemPausedInSM = False            # L7360
        s.fees = 0

    def xnav(s):                               # _loadSwapState L9895-L9902
        bv, fv = s.B * s.p, s.F * PREC
        return (bv - fv) // s.X if bv >= fv else 0

    def cr(s):                                 # collateralRatio L9437-L9444
        return s.B * s.p // s.F

    def max_mint_f(s, ncr):                    # L8039-L8064
        bv, fv = s.B * s.p * PREC, ncr * s.F * PREC
        if bv > fv:
            return (bv - fv) // (s.p * (ncr - PREC))
        return 0

    def max_mint_x(s, ncr):                    # L8074-L8098
        bv, fv = s.p * s.B * PREC, ncr * s.F * PREC
        if fv > bv:
            return (fv - bv) // (s.p * PREC)
        return 0

    def max_redeem_x(s, ncr):                  # L8143-L8167 (returns xToken amount)
        bv, fv = s.B * s.p * PREC, ncr * s.F * PREC
        if bv > fv:
            return (bv - fv) // (s.xnav() * PREC)
        return 0

    @staticmethod
    def deduct_mint_fee(b, fr0, fr1, mx):      # L7625-L7647
        mxg = (mx * FEE) // (FEE - fr0)
        if b <= mxg:
            fee = b * fr0 // FEE
        else:
            fee = mxg * fr0 // FEE + (b - mxg) * fr1 // FEE
        return b - fee, fee

    @staticmethod
    def redeem_fee_ratio(a, fr0, fr1, mx):     # L7693-L7705
        if a <= mx:
            return fr0
        return (mx * fr0 + (a - mx) * fr1) // a

    def mint_x(s, b):
        mx = s.max_mint_x(s.SR)
        d, dl = s.x_mint
        net, fee = s.deduct_mint_fee(b, d + dl, d, mx)   # fee0 = default+delta, fee1 = default  (L7618-L7622)
        out = net * s.p * s.X // (s.B * s.p - s.F * PREC)  # FxStableMath.mintXToken L8190-L8191
        s.B += net; s.X += out; s.fees += fee
        return out

    def mint_f(s, b):
        mx = s.max_mint_f(s.SR)
        if s.fMintPausedInSM:
            if s.cr() <= s.SR:
                raise Revert("ErrorFTokenMintPausedInStabilityMode")
            b = min(b, mx)
        d, dl = s.f_mint
        net, fee = s.deduct_mint_fee(b, d, d + dl, mx)
        out = net * s.p // PREC                           # L8178
        s.B += net; s.F += out; s.fees += fee
        return out, b

    def redeem_x(s, xin):
        mx = s.max_redeem_x(s.SR)
        if s.xRedeemPausedInSM:
            if s.cr() <= s.SR:
                raise Revert("ErrorXTokenRedeemPausedInStabilityMode")
            xin = min(xin, mx)
        d, dl = s.x_redeem
        fr = s.redeem_fee_ratio(xin, d, d + dl, mx)       # L7680-L7684
        xval = s.B * s.p - s.F * PREC
        out = (xin * xval // s.X) // s.p                  # FxStableMath.redeem L8214-L8216
        s.B -= out; s.X -= xin
        fee = out * fr // FEE
        s.fees += fee
        return out - fee


s = Sys(B=1250 * PREC, F=10**6 * PREC, X=10**6 * PREC, p=1000 * PREC)
print("t0: CR=%.4f (stability ratio 1.3) fSupply=%.0f  -> stability mode; fToken mint paused in SM, xToken redeem NOT paused"
      % (s.cr() / 1e18, s.F / 1e18))
try:
    s.mint_f(100 * PREC)
except Revert as e:
    print("   direct mintFToken -> REVERT %s (guard holds)" % e)
x = s.mint_x(500 * PREC)
print("1. mintXToken(500 base): x minted=%.2f, CR=%.4f" % (x / 1e18, s.cr() / 1e18))
f, used = s.mint_f(10**6 * PREC)
print("2. mintFToken(1e6 base requested, capped to %.4f base): f minted=%.2f, CR=%.4f" % (used / 1e18, f / 1e18, s.cr() / 1e18))
out = s.redeem_x(x)
print("3. redeemXToken(all %.2f x): base out (net)=%.4f, CR=%.4f, fSupply=%.0f" % (x / 1e18, out / 1e18, s.cr() / 1e18, s.F / 1e18))
print("net: fSupply +%.0f while CR went 1.2500 -> %.4f (stability mode before and after); attacker paid fees %.4f base (%.3f%% of f minted)"
      % ((s.F - 10**6 * PREC) / 1e18, s.cr() / 1e18, s.fees / 1e18, 100 * s.fees / (f * PREC // s.p)))

print("\n=== K6-like: fee ratio 1e18 accepted by _validateFeeRatio (L7525-L7532) ===")
try:
    Sys.deduct_mint_fee(10**18, FEE, FEE, 0)
except ZeroDivisionError:
    print("_deductMintFee with feeRatio0 == FEE_PRECISION: (max*1e18)/(1e18-1e18) -> Panic(0x12) division by zero (every fToken mint reverts)")
