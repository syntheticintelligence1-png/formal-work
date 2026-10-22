"""Exact port of clever/Furnace.sol (bundle L4272-L4886) ledger/index/tempo logic,
plus clever/generic/MetaFurnace.sol (L4890-L5500) as a subclass where it differs.

Custody (CVX, clevCVX, reward-pool stake) is modelled as plain integer balances with
ERC20 revert-on-insufficient semantics. External venues (CVX_REWARD_POOL, zap, strategy)
are modelled by their assumed contracts (see REPORT section 5).
"""
from solsem import (Revert, require, u64, u128, s_add, s_sub, s_mul, s_div, sc_u128,
                    E128, U128, U256, sub256, mul256)


class UserInfo:
    __slots__ = ("unrealised", "realised", "paid", "lastIdx")

    def __init__(self):
        self.unrealised = 0  # uint128
        self.realised = 0  # uint128
        self.paid = 0  # uint192 accUnrealisedFractionPaid (holds a uint128 value)
        self.lastIdx = 0  # uint64 lastDistributeIndex

    def __repr__(self):
        return "U(unr=%d, rea=%d, paid=%d, idx=%d)" % (self.unrealised, self.realised, self.paid, self.lastIdx)

    def __deepcopy__(self, memo):
        n = UserInfo()
        n.unrealised, n.realised, n.paid, n.lastIdx = self.unrealised, self.realised, self.paid, self.lastIdx
        return n


def toU128(v):  # Furnace._toU128 L4860-L4863
    require(v < 340282366920938463463374607431768211456, "Furnace: overflow")
    return v


def mul128(a, b):  # L4866-L4870 (also MetaFurnace L5480)
    if a == 0:
        return b
    if b == 0:
        return a
    return u128((a * b) // E128)


def muldiv128(a, b, c):  # L4873-L4885 (also MetaFurnace L5487)
    if b == 0:
        if c == 0:
            return a
        return a // c
    if c == 0:
        return s_mul(a, b) // E128
    return s_mul(a, b) // c


class Furnace:
    """clever/Furnace.sol. Units: wei. now = block.timestamp."""

    def __init__(self, periodLength=0, stakePercentage=0, stakeThreshold=0):
        # ledger / index
        self.totalUnrealised = 0  # uint128 L4348
        self.totalRealised = 0  # uint128 L4350
        self.acc = 0  # uint128 accUnrealisedFraction L4352
        self.distributeIndex = 0  # uint64 L4354
        self.lastPaidOff = 0  # uint64 L4356
        self.users = {}
        # tempo (LinearReward L4376-L4389)
        self.rate = 0  # uint128
        self.periodLength = periodLength  # uint32
        self.lastUpdate = 0  # uint48
        self.finishAt = 0  # uint48
        # policy
        self.stakePercentage = stakePercentage
        self.stakeThreshold = stakeThreshold
        # custody (exogenous)
        self.cvx = 0  # CVX.balanceOf(F)
        self.staked = 0  # CVX_REWARD_POOL.balanceOf(F)
        self.clev = 0  # clevCVX.balanceOf(F)
        self.now = 1_700_000_000
        self.log = []

    # ---------------- helpers ----------------
    def u(self, a):
        if a not in self.users:
            self.users[a] = UserInfo()
        return self.users[a]

    # ---------------- views ----------------
    def getUserInfo(self, a):  # L4432-L4448
        i = self.users.get(a, UserInfo())
        if i.lastIdx < self.lastPaidOff:
            return (0, u128(i.unrealised + i.realised))
        nu = u128(toU128(muldiv128(i.unrealised, self.acc, u128(i.paid))) + 1)
        if nu >= i.unrealised:
            nu = i.unrealised
        nr = u128(u128(i.unrealised - nu) + i.realised)
        return (nu, nr)

    def leftover(self):
        if self.periodLength != 0 and self.now < self.finishAt:
            return (self.finishAt - self.now) * self.rate
        return 0

    def totalCVXInPool(self):  # L4452-L4465: balance.add(staked).sub(leftover)
        return s_sub(s_add(self.cvx, self.staked), self.leftover())

    # ---------------- internal ----------------
    def _updatePendingDistribution(self):  # L4672-L4687
        if self.periodLength > 0:
            cur = self.finishAt
            if cur > self.now:
                cur = self.now
            dur = cur - self.lastUpdate if cur >= self.lastUpdate else 0
            if dur > 0:
                self.lastUpdate = self.now
                self._reduceGlobalDebt(s_mul(dur, self.rate))

    def _updateUserInfo(self, a):  # L4691-L4721
        self._updatePendingDistribution()
        i = self.u(a)
        acc = self.acc
        idx = self.distributeIndex
        if i.lastIdx < self.lastPaidOff:
            i.realised = u128(i.unrealised + i.realised)
            i.unrealised = 0
        else:
            nu = u128(toU128(muldiv128(i.unrealised, acc, u128(i.paid))) + 1)
            if nu >= i.unrealised:
                nu = i.unrealised
            nr = u128(u128(i.unrealised - nu) + i.realised)
            i.unrealised, i.realised = nu, nr
        i.paid = acc
        i.lastIdx = idx

    def _deposit(self, a, amount):  # L4727-L4757
        self._updateUserInfo(a)
        tu, tr = self.totalUnrealised, self.totalRealised
        free = s_sub(self.totalCVXInPool(), tr)
        if free >= amount:
            nu, nr = 0, amount
        else:
            nu, nr = amount - free, free
        i = self.u(a)
        i.realised = toU128(s_add(nr, i.realised))
        i.unrealised = toU128(s_add(nu, i.unrealised))
        self.totalRealised = toU128(s_add(tr, nr))
        self.totalUnrealised = toU128(s_add(tu, nu))
        return (nu, nr)

    def _withdraw(self, sender, amount):  # L4762-L4771
        i = self.u(sender)
        require(amount <= i.unrealised, "Furnace: clevCVX not enough")
        i.unrealised = u128(i.unrealised - amount)
        self.totalUnrealised = u128(sub256(self.totalUnrealised, amount))  # unchecked, "never overflow here"
        require(self.clev >= amount, "ERC20: transfer amount exceeds balance")
        self.clev -= amount
        return amount

    def _claim(self, sender):  # L4775-L4791
        i = self.u(sender)
        amount = i.realised
        self.totalRealised = u128(s_sub(self.totalRealised, amount))
        i.realised = 0
        if self.cvx < amount:
            need = amount - self.cvx
            require(self.staked >= need, "RewardPool: withdraw exceeds stake")
            self.staked -= need
            self.cvx += need
        require(self.cvx >= amount, "ERC20: transfer amount exceeds balance")
        self.cvx -= amount
        require(self.clev >= amount, "ERC20: burn amount exceeds balance")
        self.clev -= amount
        return amount

    def _distribute(self, origin, amount):  # L4796-L4832
        self._updatePendingDistribution()
        if self.periodLength == 0:
            self._reduceGlobalDebt(amount)
        else:
            if self.now >= self.finishAt:
                self.rate = toU128(amount // self.periodLength)
            else:
                rem = self.finishAt - self.now
                lo = rem * self.rate
                self.rate = toU128((amount + lo) // self.periodLength)
            self.lastUpdate = self.now
            self.finishAt = self.now + self.periodLength
        # stake extra CVX (L4820-L4829)
        toStake = s_div(s_mul(self.totalCVXInPool(), self.stakePercentage), 10**9)
        if self.staked < toStake:
            toStake -= self.staked
            if toStake >= self.stakeThreshold:
                require(self.cvx >= toStake, "ERC20: stake exceeds balance")
                self.cvx -= toStake
                self.staked += toStake

    def _reduceGlobalDebt(self, amount):  # L4836-L4857
        self.distributeIndex = u64(self.distributeIndex + 1)
        tu, tr, acc = self.totalUnrealised, self.totalRealised, self.acc
        if amount >= tu:
            self.totalUnrealised = 0
            self.totalRealised = toU128(tu + tr)
            self.acc = 0
            self.lastPaidOff = self.distributeIndex
        else:
            self.totalUnrealised = u128(tu - amount)
            self.totalRealised = toU128(tr + amount)
            frac = toU128(((tu - amount) * E128) // tu)
            self.acc = mul128(acc, frac)

    # ---------------- external ----------------
    def deposit(self, a, amount):  # L4471 / depositFor L4483
        require(amount > 0, "Furnace: deposit zero clevCVX")
        self.clev += amount
        return self._deposit(a, amount)

    def withdraw(self, a, amount):  # L4495
        require(amount > 0, "Furnace: withdraw zero CVX")
        self._updateUserInfo(a)
        return self._withdraw(a, amount)

    def withdrawAll(self, a):  # L4504
        self._updateUserInfo(a)
        return self._withdraw(a, self.u(a).unrealised)

    def claim(self, a):  # L4512
        self._updateUserInfo(a)
        return self._claim(a)

    def exit(self, a):  # L4520
        self._updateUserInfo(a)
        w = self._withdraw(a, self.u(a).unrealised)
        c = self._claim(a)
        return (w, c)

    def distribute(self, origin, amount):  # L4530 (onlyWhitelisted)
        require(amount > 0, "Furnace: distribute zero CVX")
        self.cvx += amount
        self._distribute(origin, amount)

    def updatePendingDistribution(self):  # L4578 (permissionless)
        self._updatePendingDistribution()

    def updatePeriodLength(self, P):  # L4662 (governor/owner)
        self.periodLength = P

    # ---------------- reporting ----------------
    def snap(self, *users):
        s = "TU=%d TR=%d acc=%d idx=%d lpo=%d | rate=%d P=%d lastUpd=%d finishAt=%d | cvx=%d staked=%d clev=%d" % (
            self.totalUnrealised, self.totalRealised, self.acc, self.distributeIndex, self.lastPaidOff,
            self.rate, self.periodLength, self.lastUpdate, self.finishAt, self.cvx, self.staked, self.clev)
        for a in users:
            s += "\n      %s: stored=%r alpha=%s" % (a, self.users.get(a, UserInfo()), self.alpha_str(a))
        return s

    def alpha_str(self, a):
        try:
            return repr(self.getUserInfo(a))
        except Revert as e:
            return "VIEW-REVERT(%s)" % e


class MockYieldStrategy:
    """ICLeverYieldStrategy (L4168-L4250) under its documented contract; price 1e18 (1 yield = 1 underlying)."""

    def __init__(self):
        self.underlying = 0
        self.price = 10**18

    def totalUnderlyingToken(self):
        return self.underlying


class MetaFurnace(Furnace):
    """clever/generic/MetaFurnace.sol differences: decimals scale, SafeCast, totalBaseTokenInPool,
    strategy custody, distribute without transfer, permissionless harvest."""

    def __init__(self, baseDecimals=18, periodLength=0, percentage=0, threshold=0, strategy=None):
        super().__init__(periodLength)
        self.scale = 10 ** (18 - baseDecimals)  # L5331
        self.percentage = percentage  # yieldInfo.percentage (1e5)
        self.threshold = threshold
        self.strategy = strategy
        self.base = 0  # baseToken.balanceOf(F)
        self.debt = 0  # debtToken.balanceOf(F)

    def totalBaseTokenInPool(self):  # L5070-L5085
        lo = 0
        if self.periodLength != 0 and self.now < self.finishAt:
            lo = (self.finishAt - self.now) * self.rate  # debt units (rate set from scaled amount, L5412/L5420)
        bal = s_sub(self.base, lo)  # L5079: balanceOf(this).sub(_leftover) BEFORE adding strategy
        if self.strategy is None:
            return bal
        return s_add(bal, self.strategy.totalUnderlyingToken())

    def _reduceGlobalDebt(self, amount):  # L5452-L5477
        self.distributeIndex = u64(self.distributeIndex + 1)
        tu, tr = self.totalUnrealised, self.totalRealised
        if amount >= tu:
            self.totalRealised = sc_u128(u128(tu + tr))  # uint128 + uint128 wraps before SafeCast
            self.totalUnrealised = 0
            self.acc = 0
            self.lastPaidOff = self.distributeIndex
        else:
            frac = sc_u128(((tu - amount) * E128) // tu)
            self.totalUnrealised = u128(tu - amount)
            self.totalRealised = sc_u128(tr + amount)
            self.acc = mul128(self.acc, frac)

    def _updateUserInfo(self, a):  # L5290-L5320 (SafeCast instead of _toU128)
        self._updatePendingDistribution()
        i = self.u(a)
        acc = self.acc
        idx = self.distributeIndex
        if i.lastIdx < self.lastPaidOff:
            i.realised = u128(i.unrealised + i.realised)
            i.unrealised = 0
        else:
            nu = u128(sc_u128(muldiv128(i.unrealised, acc, u128(i.paid))) + 1)
            if nu >= i.unrealised:
                nu = i.unrealised
            i.unrealised, i.realised = nu, u128(u128(i.unrealised - nu) + i.realised)
        i.paid = acc
        i.lastIdx = idx

    def getUserInfo(self, a):  # L5046-L5067
        i = self.users.get(a, UserInfo())
        if i.lastIdx < self.lastPaidOff:
            return (0, u128(i.unrealised + i.realised))
        nu = u128(sc_u128(muldiv128(i.unrealised, self.acc, u128(i.paid))) + 1)
        if nu >= i.unrealised:
            nu = i.unrealised
        return (nu, u128(u128(i.unrealised - nu) + i.realised))

    def _deposit(self, a, amount):  # L5326-L5357
        self._updateUserInfo(a)
        tu, tr = self.totalUnrealised, self.totalRealised
        free = s_sub(mul256(self.totalBaseTokenInPool(), self.scale), tr)
        if free >= amount:
            nu, nr = 0, amount
        else:
            nu, nr = amount - free, free
        i = self.u(a)
        i.realised = sc_u128(s_add(nr, i.realised))
        i.unrealised = sc_u128(s_add(nu, i.unrealised))
        self.totalRealised = sc_u128(s_add(tr, nr))
        self.totalUnrealised = sc_u128(s_add(tu, nu))
        return (nu, nr)

    def deposit(self, a, amount):  # L5090
        require(amount > 0, "Furnace: deposit zero amount")
        self.debt += amount
        return self._deposit(a, amount)

    def _withdraw(self, sender, amount):  # L5362-L5371
        i = self.u(sender)
        require(amount <= i.unrealised, "Furnace: debtToken not enough")
        i.unrealised = u128(i.unrealised - amount)
        self.totalUnrealised = u128(sub256(self.totalUnrealised, amount))
        require(self.debt >= amount, "ERC20: transfer amount exceeds balance")
        self.debt -= amount
        return amount

    def _claim(self, sender):  # L5375-L5401
        i = self.u(sender)
        debtAmount = i.realised
        self.totalRealised = u128(s_sub(self.totalRealised, debtAmount))
        i.realised = 0
        baseAmount = debtAmount // self.scale
        bal = self.base
        if bal < baseAmount:
            require(self.strategy is not None, "call to address(0) strategy")
            y = ((baseAmount - bal) * 10**18) // self.strategy.price
            diff = y * self.strategy.price // 10**18
            require(self.strategy.underlying >= diff, "strategy: insufficient")
            self.strategy.underlying -= diff
            self.base += diff
            baseAmount = bal + diff
        require(self.base >= baseAmount, "ERC20: transfer amount exceeds balance")
        self.base -= baseAmount
        require(self.debt >= debtAmount, "ERC20: burn amount exceeds balance")
        self.debt -= debtAmount
        return baseAmount

    def _distribute(self, origin, amount):  # L5406-L5448
        self._updatePendingDistribution()
        amount = mul256(amount, self.scale)
        if self.periodLength == 0:
            self._reduceGlobalDebt(amount)
        else:
            if self.now >= self.finishAt:
                self.rate = sc_u128(amount // self.periodLength)
            else:
                rem = self.finishAt - self.now
                self.rate = sc_u128((amount + rem * self.rate) // self.periodLength)
            self.lastUpdate = self.now
            self.finishAt = self.now + self.periodLength
        if self.strategy is not None:
            exp = s_mul(self.totalBaseTokenInPool(), self.percentage) // 10**5
            st = self.strategy.totalUnderlyingToken()
            if st < exp:
                exp -= st
                if exp >= self.threshold:
                    require(self.base >= exp, "ERC20: transfer amount exceeds balance")
                    self.base -= exp
                    self.strategy.underlying += exp

    def distribute(self, origin, amount):  # L5130: NO token transfer (caller pre-transfers, L5552-L5554)
        self._distribute(origin, amount)

    def snap(self, *users):
        s = "TU=%d TR=%d acc=%d | rate=%d P=%d lastUpd=%d finishAt=%d | base=%d strat=%d debt=%d" % (
            self.totalUnrealised, self.totalRealised, self.acc, self.rate, self.periodLength, self.lastUpdate,
            self.finishAt, self.base, self.strategy.underlying if self.strategy else 0, self.debt)
        for a in users:
            s += "\n      %s: stored=%r alpha=%s" % (a, self.users.get(a, UserInfo()), self.alpha_str(a))
        return s
