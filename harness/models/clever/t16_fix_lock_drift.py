"""T16  _fixLockDrift (L13708-L13762): ledger effect of the epoch-gated patch, all-processed vs one
patch epoch missed.  Only the global ledger (TUG = totalUnlockedGlobal, TPUG = totalPendingUnlockGlobal,
pendingUnlocked[]) is modelled; Convex releases are abstracted (the patch's own comments define the
intended netBorrow trajectory).  Constants: L13011-L13015; pendingUnlocked values: comments L13709-L13713.
User entitlement E = sum of pendings that users already hold per-user (2817, 2818, 2838, 2957 + each
epoch's original pending).  We report TUG - E (the patch's "netBorrowAfter") after each epoch.
"""
import datetime
D12 = 76667262837450359231536
D13 = 32351447410870579373820
D15 = 561911228961951745608
D16 = 237756223183328739207623
D13A = 3173000000000000000000
PU0 = {2817: 209189203791910235264, 2818: 1562240117453267819353, 2752: 0,
       2838: 4469427261945621070254, 2957: 141926991451881642610311}
E18 = 10**18

def epoch_date(e):
    return datetime.datetime.fromtimestamp(e * 604800, datetime.timezone.utc).strftime("%Y-%m-%d")

class Rev(Exception):
    pass

def sub(a, b):
    if b > a:
        raise Rev("SafeMath: subtraction overflow")
    return a - b

def run(skip=(), TUG0=0, orig=None):
    orig = orig or {}
    pu = dict(PU0); pu.update({e: v for e, v in orig.items()})
    TUG, TPUG = TUG0, 10**30          # TPUG large: we track deltas only
    E = 0                              # users' already-credited entitlement drawn on TUG (2817,2818,2838,2957 + processed)
    trace = []
    for cur in [2957, 2958] + list(range(2959, 2976)):
        if cur in skip:
            trace.append((cur, "SKIPPED", TUG - E)); continue
        try:
            # _fixLockDrift(cur)
            if cur == 2957:
                pu[2838] = pu[2838] + pu[2957]; pu[2957] = 0
            elif cur == 2958:
                s = pu[2838] + D12 + D13
                pu[2958] = pu.get(2958, 0) + s
                TPUG += sub(D12, pu[2817]) + sub(D13, pu[2818])
                TUG = sub(TUG, D13A)          # 3173 CVX transferred to owner(), L13729-L13730
                E += pu[2817] + pu[2818] + pu[2838]   # drifted user pendings settle here (comment L13721)
            elif cur == 2970:
                TUG = sub(TUG, sub(D12, pu[2817]))
            elif cur == 2971:
                TUG = sub(TUG, sub(sub(D13, pu[2818]), D13A))
            elif cur == 2972:
                s = D12 + D13
                pu[2972] = pu.get(2972, 0) + s; TPUG += s
            elif cur == 2973:
                TUG = sub(TUG, D15)
            elif cur == 2974:
                TUG = sub(TUG, sub(sub(D16, pu[2838]), D15))
            elif cur == 2975:
                TUG = sub(TUG, sub(D12 + D13, sub(D16, pu[2838])))
            # processUnlockableCVX: move pendingUnlocked[cur] (Convex release assumed sufficient)
            p = pu.get(cur, 0)
            TUG += p; TPUG -= p; pu[cur] = 0
            E += orig.get(cur, 0)
            trace.append((cur, "ok", TUG - E))
        except Rev as e:
            trace.append((cur, "REVERT " + str(e), TUG - E))
    return trace

print("epoch dates: 2957=%s 2958=%s 2970=%s 2975=%s ; 'now' (2026-10-22) = epoch %d" % (
    epoch_date(2957), epoch_date(2958), epoch_date(2970), epoch_date(2975),
    int(datetime.datetime(2026, 10, 22).replace(tzinfo=datetime.timezone.utc).timestamp()) // 604800))
TUG0 = 10_000 * E18
for skip in [(), (2958,), (2970,), (2971,), (2972,), (2974,)]:
    tr = run(skip=skip, TUG0=TUG0)
    shown = [(e, s, round(x / E18, 2)) for (e, s, x) in tr if e in (2957, 2958, 2970, 2971, 2972, 2973, 2974, 2975)]
    print("skip=%-8s TUG-E (CVX) after each patch epoch:" % (skip,))
    for e, s, x in shown:
        print("     %d %-34s %14.2f" % (e, s, x))
