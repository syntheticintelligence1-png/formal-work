# Integer model of TreasuryWithFundingCost (L17346-L17513) + MarketWithFundingCost hooks (L17187-L17217)
# + TreasuryV2.mintFToken/redeem (L9549-L9620) + FxStableMath (L7991-L8238). Base token has 18 decimals,
# so getWrapppedValue/getUnderlyingValue are identities (baseTokenScale = 1, L9527-L9534).
# Run: python3 -I funding_cost.py
PREC = 10**18
MAX_LEV = 100 * 10**18


def lev_ratio(B, F, twap):                       # FxStableMath.leverageRatio L8226-L8237
    rho = (F * PREC * PREC) // (B * twap)
    if rho >= PREC:
        return MAX_LEV
    r = (PREC * PREC) // (PREC - rho)
    return min(r, MAX_LEV)


def xnav(B, F, X, p):                            # _computeXTokenNav L17485-L17499
    if X == 0:
        return PREC
    bv, fv = B * p, F * PREC
    return (bv - fv) // X if bv >= fv else 0


class T:
    def __init__(s, B, F, X, p, I0, t0, scale=5 * 10**17):
        s.B, s.F, s.X, s.p, s.twap = B, F, X, p, p
        s.bal = B                       # custody (wrapped == underlying here)
        s.I, s.Is, s.ts, s.now = I0, I0, t0, t0
        s.scale = scale
        s.valid = True
        s.distributed = 0

    def funding_rate(s):                          # getFundingRate L17301-L17306
        fr = ((s.I - s.Is) * PREC) // s.Is
        return (fr * s.scale) // PREC

    def harvestable(s, B):                        # _harvestable L17502-L17512 (state at baseSupply B)
        xn = xnav(B, s.F, s.X, s.p)
        lev = lev_ratio(B, s.F, s.twap)
        cost = (xn * s.X * (lev - PREC)) // lev
        cost = (cost * s.funding_rate()) // PREC
        return cost // s.p

    def load(s, deduct):                          # _loadSwapState(action, deduct) L17460-L17482
        B = s.B
        if deduct and s.ts < s.now:
            B -= s.harvestable(B)
        return B

    def harvest(s):                               # harvest() L17409-L17426
        if s.ts == s.now:
            return 0
        if not s.valid:
            return 0
        B = s.load(False)
        if xnav(B, s.F, s.X, s.p) == 0:
            return 0
        r = s.harvestable(B)
        s.B -= r
        s.Is, s.ts = s.I, s.now                   # _captureFundingRate L17323-L17332
        s.bal -= r
        s.distributed += r
        return r

    def market_mint_f(s, b):                      # MarketWithFundingCost.mintFToken -> hook -> TreasuryV2.mintFToken
        s.harvest()                               # harvestFundingCost modifier L17187-L17195
        B = s.load(True)                          # virtual _loadSwapState(Action.MintFToken) L17449-L17457
        fout = (b * s.p) // PREC                  # FxStableMath.mintFToken L8178
        s.B = B + b                               # L9562 persists the deducted baseSupply
        s.F += fout
        s.bal += b
        return fout

    def xvalue(s):
        return xnav(s.B, s.F, s.X, s.p) * s.X // PREC


def scenario(k_invalid_actions):
    t = T(B=1000 * PREC, F=10**6 * PREC, X=10**6 * PREC, p=2000 * PREC, I0=PREC, t0=0)
    t.now = 86400
    t.I = PREC + 10**16                           # crvUSD rate_mul grew 1% since the last capture
    x0 = t.xvalue()
    t.valid = False                               # oracle reports isValid=false (IFxPriceOracleV2 L9964-L9968)
    for _ in range(k_invalid_actions):
        t.market_mint_f(10**9)                    # tiny fToken mints (baseIn > 0 required, L7204)
    t.valid = True
    t.now += 1
    t.harvest()                                   # first valid harvest
    surplus = t.bal - t.B
    return t, x0, surplus


print("=== F1: repeated funding-cost deduction while harvest() early-returns (price invalid) ===")
for k in [0, 1, 5, 20]:
    t, x0, surplus = scenario(k)
    print("k=%2d invalid-price actions: totalBaseToken drop=%.6f base, distributed=%.6f base, custody-ledger surplus=%.6f base, xValue %.2f -> %.2f USD"
          % (k, (1000 * PREC + k * 10**9 - t.B) / 1e18, t.distributed / 1e18, surplus / 1e18, x0 / 1e18, t.xvalue() / 1e18))

print("\n=== B3: flow property of funding accrual (valid prices, no other actions) ===")
def two_step(split):
    t = T(B=1000 * PREC, F=10**6 * PREC, X=10**6 * PREC, p=2000 * PREC, I0=PREC, t0=0)
    I_end = PREC + 10**17                          # +10% index over the whole interval
    if split:
        t.now, t.I = 1, PREC + 5 * 10**16          # poke when index is +5%
        t.harvest()
    t.now, t.I = 2, I_end
    t.harvest()
    return t.distributed
one, two = two_step(False), two_step(True)
print("U_{s+t}: one harvest over +10%% index: %d wei; U_t o U_s: two harvests (+5%%, then rest): %d wei; D = %d wei (%.4f%% of charge)"
      % (one, two, one - two, 100 * (one - two) / one))

print("\n=== B3: price at poke time re-prices the whole unsettled interval ===")
for p in [1800, 2000, 2200]:
    t = T(B=1000 * PREC, F=10**6 * PREC, X=10**6 * PREC, p=2000 * PREC, I0=PREC, t0=0)
    t.now, t.I = 86400, PREC + 10**16
    t.p = t.twap = p * PREC
    r = t.harvest()
    print("harvest when price=%d: charge = %.6f base (= %.2f USD)" % (p, r / 1e18, r * p / 1e18))
