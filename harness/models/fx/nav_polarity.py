# Value-partition invariant I-NAV (TreasuryV2 + FxStableMath, fNav == 1, L7997, L9882-L9905):
#   for each action a priced at pi_a:  xNav_pi_a(post) >= xNav_pi_a(pre)   (no dilution of incumbent xToken holders)
# Prices per action: L9919-L9929 (MintFToken, RedeemXToken -> minPrice ; MintXToken, RedeemFToken, None -> maxPrice).
# Also: per-action output deficit vs the exact rational output (quantized defect, polarity).
# Run: python3 -I nav_polarity.py
import random
from fractions import Fraction as Q
PREC = 10**18
random.seed(11)

viol = 0; n = 0; worst_def = Q(0); over = 0
for _ in range(200000):
    pmin = random.randint(500, 5000) * PREC + random.randint(0, PREC)
    pmax = pmin + random.randint(0, pmin // 50)
    B = random.randint(1, 10**6) * PREC + random.randint(0, PREC)
    F = random.randint(1, int(B * pmin // PREC * 0.9) + 1)
    X = random.randint(1, 10**7) * PREC + random.randint(0, PREC)
    act = random.choice(["mintF", "mintX", "redeemF", "redeemX"])
    amt = random.randint(1, 10**4) * PREC + random.randint(0, PREC)
    if act == "mintF":
        p = pmin; out = (amt * p) // PREC; ideal = Q(amt * p, PREC)                                  # L8178
        B2, F2, X2 = B + amt, F + out, X
    elif act == "mintX":
        p = pmax; out = (amt * p * X) // (B * p - F * PREC); ideal = Q(amt * p * X, B * p - F * PREC)  # L8190-L8191
        B2, F2, X2 = B + amt, F, X + out
    elif act == "redeemF":
        p = pmax; fin = min(F, amt); out = (fin * PREC) // p; ideal = Q(fin * PREC, p)               # L8212
        B2, F2, X2 = B - out, F - fin, X
    else:
        p = pmin; xin = min(X - 1, amt)
        if xin <= 0:
            continue
        xv = B * p - F * PREC
        out = ((xin * xv) // X) // p; ideal = Q(xin * xv, X * p)                                       # L8214-L8216
        B2, F2, X2 = B - out, F, X - xin
    n += 1
    if out > ideal:
        over += 1
    worst_def = max(worst_def, ideal - out)
    if (B2 * p - F2 * PREC) * X < (B * p - F * PREC) * X2:   # xVal/X compared exactly
        viol += 1
print("actions checked: %d" % n)
print("  dilution of incumbent xToken holders at the action's own price: %d cases" % viol)
print("  outputs exceeding the exact rational amount (liability-inflating): %d cases" % over)
print("  max output deficit vs exact amount: %.6f output-token wei (quantized, polarity <= 0)" % float(worst_def))
