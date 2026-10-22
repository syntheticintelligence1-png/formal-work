"""
m06 - Kernel obligation discharge, K5 (WordCodec.insertUint, L20-L33) at its Concentrator call sites, and
K6 (FeeCustomization, L3996-L4110) at its AladdinCompounder consumer.
insertUint does not mask `value`: result = (word & ~(mask << off)) | (value << off)  (mod 2^256).
Call sites: ConcentratorBaseV2 L1108 (expense, off 0), L1122 (harvester, off 30), L1136 (withdraw fee, off 60),
ConcentratorStakeDAOGaugeWrapper L715 (booster, off 90); all 30-bit fields; guards L1102, L1116, L1130, L709.
Run: python3 -I m06_k5_k6_bounds.py
"""
M256 = 1 << 256


def insertUint(word, value, offset, bits):
    mask = (1 << bits) - 1
    cleared = word & (~(mask << offset) % M256)
    return (cleared | ((value << offset) % M256)) % M256


def decodeUint(word, offset, bits):
    return (word >> offset) & ((1 << bits) - 1)


FIELDS = {"expense": (0, 5 * 10 ** 8), "harvester": (30, 10 ** 8), "withdrawFee": (60, 10 ** 8), "booster": (90, 2 * 10 ** 8)}

if __name__ == "__main__":
    print("K5 discharge: guard maxima vs 2^30 =", 1 << 30)
    word = 0
    for name, (off, mx) in FIELDS.items():
        word = insertUint(word, mx, off, 30)
    ok = all(decodeUint(word, off, 30) == mx for name, (off, mx) in FIELDS.items())
    print("  all four fields written at their guard maximum, read back intact:", ok,
          {n: decodeUint(word, o, 30) for n, (o, _) in FIELDS.items()})
    # exhaustive boundary sweep of each field against every other field's extreme values
    bad = 0
    for name, (off, mx) in FIELDS.items():
        for v in (0, 1, mx - 1, mx):
            for other in (0, (1 << 30) - 1):
                w = 0
                for n2, (o2, _) in FIELDS.items():
                    w = insertUint(w, other, o2, 30)
                w2 = insertUint(w, v, off, 30)
                for n2, (o2, _) in FIELDS.items():
                    if n2 != name and decodeUint(w2, o2, 30) != other:
                        bad += 1
                if decodeUint(w2, off, 30) != v:
                    bad += 1
    print("  boundary sweep corruptions:", bad)
    print("Relaxation (guard >= 2^30): expense value 2^30 + 7 written at offset 0")
    w = insertUint(0, 12344, 30, 30)
    w = insertUint(w, (1 << 30) + 7, 0, 30)
    print("  expense reads", decodeUint(w, 0, 30), "; harvester field corrupted from 12344 to", decodeUint(w, 30, 30))
    print()
    FEE_PRECISION = 10 ** 9
    print("K6 discharge in AladdinCompounder: setWithdrawFeeForUser requires rate <= 1e8 (L3059);")
    print("  minimal divisor FEE_PRECISION - rate =", FEE_PRECISION - 10 ** 8, "(> 0) at L2980")
    print("Relaxation: a consumer that exposes _setFeeCustomization with only its own bound rate <= 1e9 (L4036):")
    rate = 10 ** 9
    try:
        d = FEE_PRECISION - rate
        if d == 0:
            raise ZeroDivisionError
        print("  divisor", d)
    except ZeroDivisionError:
        print("  rate = 1e9 -> SafeMath.div(x, 0) -> revert 'SafeMath: division by zero' in withdraw() for that owner")
