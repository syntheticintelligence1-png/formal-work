"""Port of CLeverAMOBase (L8324-L8844) + AladdinCVX (L8866-L9183) control flow on top of the Furnace
model (furnace_model.py) and the Curve reference (amo_model.py).  Used by t12 and t17."""
from solsem import Revert, require, atomic, U256
from furnace_model import Furnace
import amo_model as M

E18 = 10**18
RP = 10**10  # RATIO_PRECISION (L8352)


class AMO:
    def __init__(self, furnace, pool, supply, lp_in_strategy, initialRatio=RP):
        self.F = furnace
        self.pool = pool
        self.totalSupply = supply
        self.lp = lp_in_strategy  # ICLeverAMOStrategy.strategyBalance()   [A-STR1]
        self.base = 0  # CVX held by the AMO (locked user deposits)
        self.pending = 0
        self.initialRatio = initialRatio
        self.locked = {}
        self.shares = {}

    def debtBalance(self):  # L9020-L9023
        return self.F.getUserInfo("AMO")[0]

    def claimBaseFromFurnace(self):  # L9098-L9102 (balance differential)
        before = self.F.cvx + self.F.staked
        got = self.F.claim("AMO")
        return got

    def convertFromBaseToken(self, amount):  # L9031-L9068
        debtBal = lpBal = 0
        if self.totalSupply == 0:
            add = M.searchSplit(self.pool, amount, self.initialRatio, RP)
        else:
            debtBal = self.debtBalance(); lpBal = self.lp
            add = M.searchSplit(self.pool, amount, lpBal, debtBal)
        lpOut = self.pool.add_liquidity([add, 0], 0)
        debtOut = self.pool.exchange(0, 1, amount - add, 0)
        den = M.w(debtBal + debtOut)
        require(den != 0, "AladdinCVX L9067: _ratio division by zero (0.7 INVALID)")
        ratio = M.w((lpBal + lpOut) * RP) // den
        return debtOut, lpOut, ratio

    def checkpoint(self, userSupply):  # L8764-L8788
        b = self.claimBaseFromFurnace() + userSupply
        if self.pending > 0:
            b += self.pending; self.pending = 0
        dOut = lOut = 0
        if b > 0:
            dOut, lOut, _ = self.convertFromBaseToken(b)
            self.F.deposit("AMO", dOut)      # _depositDebtToken -> Furnace.deposit (L4471: require > 0)
            require(lOut > 0, "strategy: deposit zero")  # IConcentratorStrategy.deposit precondition [C] L8259
            self.lp += lOut
        return b, dOut, lOut

    def unlock(self, user, minShareOut):  # L8540-L8587
        unlocked = self.locked.pop(user, 0)
        require(unlocked > 0, "CLeverAMO: no unlocks")
        total, debtOut, lpOut = self.checkpoint(unlocked)
        debtOut = M.d(M.w(debtOut * unlocked), total)
        lpOut = M.d(M.w(lpOut * unlocked), total)
        S = self.totalSupply
        if S == 0:
            sh = max(debtOut, lpOut)
        else:
            debtBal = self.debtBalance(); lpBal = self.lp
            require(M.w(debtBal - debtOut) != 0, "CLeverAMOBase L8575: division by zero")
            dsh = M.w(debtOut * S) // M.w(debtBal - debtOut)
            require(M.w(lpBal - lpOut) != 0, "CLeverAMOBase L8576: division by zero")
            lsh = M.w(lpOut * S) // M.w(lpBal - lpOut)
            sh = min(dsh, lsh)
            self.dbg = dict(debtOut=debtOut, debtBal=debtBal, wrapped=debtBal < debtOut, dsh=dsh, lsh=lsh)
        require(sh >= minShareOut, "CLeverAMO: insufficient shares")
        self.totalSupply += sh
        self.shares[user] = self.shares.get(user, 0) + sh
        return sh


    def withdraw(self, user, shares):  # L8590-L8616 (shares of `user`)
        require(shares > 0, "CLeverAMO: amount is zero")
        self.checkpoint(0)
        S = self.totalSupply
        self.shares[user] -= shares; self.totalSupply -= shares
        lpOut = M.d(self.lp * shares, S)
        debtOut = M.d(self.debtBalance() * shares, S)
        self.F.withdraw("AMO", debtOut)        # _withdrawDebtToken -> Furnace.withdraw (L4495: require > 0)
        self.lp -= lpOut
        return (lpOut, debtOut)


