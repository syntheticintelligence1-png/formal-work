"""T03  accUnrealisedFraction precision underflow (B2 structural defect at a boundary state).

acc encodes a real in [0,1) as acc/2^128 with the special code 0 == 1.0 (L4329-L4331).
_mul128 (L4866-L4870) returns floor(a*b/2^128); if a*b < 2^128 the product underflows to
the code 0, i.e. it is decoded as 1.0 without lastPaidOffDistributeIndex being bumped.
_muldiv128(U, 0, c!=0) (L4878-L4880) then returns U/c, and after the next reduction
acc = _mul128(0, f) = f (L4867) restarts at ~1.0.  Users whose snapshot predates the
underflow get alpha^U = min(..., U) = their *stored* U back (realisation reverted) or a
_toU128 overflow revert (exit-liveness).
Reaching it needs two reductions that each leave ~1 wei of a large TU.
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from solsem import atomic, U128
from furnace_model import Furnace

def run(label, F, fn, *a):
    r = atomic(F, fn, *a)
    print("  %-54s -> %s" % (label, r))
    return r

D1 = 2**65   # ~36.9 clevCVX
X = 2**65
F = Furnace(periodLength=0)
run("A.deposit(2^65)          [A.paid = 0]", F, F.deposit, "A", D1)
run("distribute(2^65 - 1)     [TU -> 1]", F, F.distribute, "locker", D1 - 1)
print("  state:", F.snap("A"))
run("V.deposit(2^65)          [V.paid = acc_1]", F, F.deposit, "V", X)
run("distribute(2^65)         [TU -> 1]", F, F.distribute, "locker", X)
print("  state:", F.snap("A", "V"))
print("  acc == 0 (underflow, decoded as 1.0)?", F.acc == 0, "  lastPaidOff bumped?", F.lastPaidOff != 0)
tot = sum(F.getUserInfo(a)[0] for a in ("A", "V"))
print("  sum alpha^U = %d  vs  TU = %d  (excess %d wei)" % (tot, F.totalUnrealised, tot - F.totalUnrealised))
print("  A's realisation (2^65-1 wei) has been reverted to unrealised; it is still booked in TR")
run("W.deposit(10^21)", F, F.deposit, "W", 10**21)
run("distribute(10^20)        [acc := _mul128(0,f) = f]", F, F.distribute, "locker", 10**20)
print("  state:", F.snap("A", "V", "W"))
run("V.withdrawAll()  (stale paid = acc_1 small)", F, F.withdrawAll, "V")
run("A.withdrawAll()", F, F.withdrawAll, "A")
print("  state:", F.snap("A", "V", "W"))
print("  TU wrapped?", F.totalUnrealised > U128 // 2)
