"""T12  B5 gluing AladdinCVX/CLeverAMOBase <-> Furnace.

G_{AMO,F}: debt deposited by the AMO via _depositDebtToken (L9088-L9090) is reflected 1:1 in
_debtBalanceInContract() = Furnace.getUserInfo(AMO).unrealised (L9020-L9023).
Furnace._deposit realises min(freeCVX, amount) immediately (L4734-L4747), so G fails whenever
the Furnace holds free CVX (after a paid-off distribution).  CLeverAMOBase.unlock then computes
    shares_debt = _debtOut * S / (_debtBalance - _debtOut)          (L8575, unchecked 0.7)
and _convertFromBaseToken splits with num/den = lpBalance/debtBalance (L9050).

Port of CLeverAMOBase.unlock/_checkpoint (L8540-L8587, L8764-L8788) and AladdinCVX conversion
(L9031-L9068) on top of the Furnace model (furnace_model.py) and the Curve reference (amo_model.py).
"""
import os, sys, copy
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from solsem import Revert, require, atomic, U256
from furnace_model import Furnace
import amo_model as M

E18 = 10**18
RP = 10**10  # RATIO_PRECISION


from amo_port import AMO, RP


def setup(paid_off):
    F = Furnace(periodLength=0)
    pool = M.CurvePlain2(1_000_000 * E18, 1_200_000 * E18, A=100)  # CVX index 0 (base), clevCVX index 1 (debt)
    amo = AMO(F, pool, supply=100_000 * E18, lp_in_strategy=60_000 * E18)
    F.clev += 50_000 * E18; F._deposit("AMO", 50_000 * E18)      # AMO's debt in the Furnace
    F.clev += 10_000 * E18; F._deposit("others", 10_000 * E18)
    dist = 70_000 * E18 if paid_off else 20_000 * E18
    F.distribute("locker", dist)                                    # harvest -> distribute
    amo.base += 1_000 * E18; amo.locked["alice"] = 1_000 * E18      # alice's matured lock
    return F, amo

for paid_off in (False, True):
    F, amo = setup(paid_off)
    free = F.totalCVXInPool() - F.totalRealised
    print("=== T12 paid_off=%s : Furnace TU=%d free CVX=%d, AMO debtBalance=%d ===" % (
        paid_off, F.totalUnrealised, free, amo.debtBalance()))
    for mso in (0, 1):
        A2 = copy.deepcopy(amo)
        r = atomic(A2, A2.unlock, "alice", mso)
        print("  alice.unlock(minShareOut=%d) -> %s" % (mso, r))
        if r[0] == "ok" and hasattr(A2, "dbg"):
            print("     debtOut(user)=%d debtBalance(after)=%d wrapped=%s debt-shares=%d lp-shares=%d" % (
                A2.dbg["debtOut"], A2.dbg["debtBal"], A2.dbg["wrapped"], A2.dbg["dsh"], A2.dbg["lsh"]))

print()
print("=== T12b: partially free CVX: Furnace free CVX smaller than the AMO's debt purchase ===")
F, amo = setup(True)
F.clev += 9_000 * E18; F._deposit("others2", 9_000 * E18)   # someone consumes most free CVX
F.clev += 2_000 * E18; F._deposit("AMO", 2_000 * E18)       # AMO gets a small unrealised position again
print("  free CVX=%d  AMO debtBalance=%d" % (F.totalCVXInPool() - F.totalRealised, amo.debtBalance()))
A2 = copy.deepcopy(amo)
r = atomic(A2, A2.unlock, "alice", 0)
print("  alice.unlock(0) ->", r, getattr(A2, "dbg", None))

print()
print("=== T12c: exit path when the AMO's Furnace unrealised is 0 (paid-off Furnace) ===")
F, amo = setup(True)
amo.shares["bob"] = 10_000 * E18
A2 = copy.deepcopy(amo)
print("  bob.withdraw(10000e18 shares)                  ->", atomic(A2, A2.withdraw, "bob", 10_000 * E18))
A3 = copy.deepcopy(amo)
A3.F.claim("AMO")   # suppose the realised base had already been claimed (claim returns 0 now)
print("  bob.withdraw(...) with nothing left to claim   ->", atomic(A3, A3.withdraw, "bob", 10_000 * E18))
print("  (withdrawToBase L8619-L8646 calls the same _checkpoint(0) and _withdrawDebtToken(_, this))")

print()
print("=== T12d: paid-off Furnace, converted amount not a multiple of 1e9 (pendingBaseToken dust) ===")
for dust in (123, 999_999_999, 7 * 10**17 + 5):
    F, amo = setup(True)
    amo.pending = dust
    A2 = copy.deepcopy(amo)
    r = atomic(A2, A2.unlock, "alice", 0)
    print("  dust=%-22d alice.unlock(0) -> %s %s" % (dust, r, getattr(A2, "dbg", "")))
