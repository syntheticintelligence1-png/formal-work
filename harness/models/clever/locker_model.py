"""Exact port of the ledger/schedule logic of clever/CLeverCVXLocker.sol (L12944-L14131).

Environment (out of bundle, assumed contracts - see REPORT sec. 5):
  ConvexLocker (CvxLockerV2 at CVX_LOCKER L13005):
    lock(amount) at epoch e      -> lock entry expiring at epoch e+17           [A-CVX1]
    processExpiredLocks(false)   -> releases every entry with expiry <= now;
                                    reverts "no exp locks" if none expired     [A-CVX2]
    getReward(account, stake)    -> permissionless                             [A-CVX3]
  RewardPool (cvxRewardPool, CVX_REWARD_POOL L13003): stake/withdraw 1:1, no loss  [A-CRP1]
  Furnace: distribute pulls `amount` CVX from the locker                         [A-F1]
"""
from solsem import Revert, require, u112, u128, u192, s_add, s_sub, s_mul, s_div

WEEK = 86400 * 7
PRECISION = 10**18
FEE = 10**9


class ConvexLocker:
    def __init__(self):
        self.locks = {}  # expiryEpoch -> amount (for the CLever locker account)

    def lock(self, epoch, amount):
        self.locks[epoch + 17] = self.locks.get(epoch + 17, 0) + amount

    def processExpiredLocks(self, epoch):
        exp = [e for e in self.locks if e <= epoch]
        amt = sum(self.locks[e] for e in exp)
        require(amt > 0, "CvxLocker: no exp locks")
        for e in exp:
            del self.locks[e]
        return amt

    def total(self):
        return sum(self.locks.values())


class LUser:
    def __init__(self):
        self.totalDebt = 0
        self.rewards = 0
        self.rewardPerSharePaid = 0
        self.totalLocked = 0
        self.totalUnlocked = 0
        self.nextUnlockIndex = 0
        self.epochLocked = [0] * 17
        self.pendingUnlockList = []  # [pendingUnlock, unlockEpoch]


class Locker:
    def __init__(self, reserveRate=5 * 10**8, stakePercentage=0, stakeThreshold=0, platformFee=0, bounty=0):
        self.totalLockedGlobal = 0
        self.totalPendingUnlockGlobal = 0
        self.totalUnlockedGlobal = 0
        self.totalDebtGlobal = 0
        self.accRewardPerShare = 0
        self.users = {}
        self.pendingUnlocked = {}
        self.reserveRate = reserveRate
        self.stakePercentage = stakePercentage
        self.stakeThreshold = stakeThreshold
        self.platformFeePercentage = platformFee
        self.harvestBountyPercentage = bounty
        # custody
        self.cvx = 0
        self.staked = 0
        self.convex = ConvexLocker()
        self.furnace_received = 0
        self.platform_received = 0
        self.clev_minted = 0
        self.now = 2900 * WEEK + 3600

    def epoch(self):
        return self.now // WEEK

    def u(self, a):
        if a not in self.users:
            self.users[a] = LUser()
        return self.users[a]

    def totalCVXInPool(self):  # L13255-L13260
        return s_add(self.cvx, self.staked)

    # ---------------- internal ----------------
    def _updateReward(self, a):  # L13917-L13948
        i = self.u(a)
        tdg = self.totalDebtGlobal
        td = i.totalDebt
        r = s_add(i.rewards, s_mul(s_sub(self.accRewardPerShare, i.rewardPerSharePaid), i.totalLocked) // PRECISION)
        i.rewardPerSharePaid = u192(self.accRewardPerShare)
        if td > 0:
            if r >= td:
                r -= td; tdg -= td; td = 0
            else:
                tdg -= r; td -= r; r = 0
        i.totalDebt = u128(td)
        i.rewards = u128(r)
        self.totalDebtGlobal = tdg

    def _updateUnlocked(self, a):  # L13952-L13974
        i = self.u(a)
        cur = self.epoch()
        idx = i.nextUnlockIndex
        tot = i.totalUnlocked
        while idx < len(i.pendingUnlockList):
            amt, ep = i.pendingUnlockList[idx]
            if ep <= cur:
                tot = tot + amt
                i.pendingUnlockList[idx] = [0, 0]
            else:
                break
            idx += 1
        i.totalUnlocked = u112(tot)
        i.nextUnlockIndex = idx

    def _checkAccountHealth(self, dep, debt, newUnlock, newBorrow):  # L14120-L14130
        require(s_mul(s_sub(dep, newUnlock), self.reserveRate) >= s_mul(s_add(debt, newBorrow), FEE),
                "unlock or borrow exceeds limit")

    def _distribute(self, amount):  # L14064-L14091
        if self.totalLockedGlobal > 0:
            self.accRewardPerShare = s_add(self.accRewardPerShare, s_mul(amount, PRECISION) // self.totalLockedGlobal)
        require(self.cvx >= amount, "CVX: transfer amount exceeds balance (Furnace.distribute pull)")
        self.cvx -= amount
        self.furnace_received += amount
        bs = self.staked
        toStake = s_div(s_mul(s_add(bs, self.cvx), self.stakePercentage), FEE)
        if bs < toStake:
            toStake -= bs
            if toStake >= self.stakeThreshold:
                self.cvx -= toStake
                self.staked += toStake

    # ---------------- external ----------------
    def deposit(self, a, amount):  # L13283-L13307
        require(amount != 0, "ZeroValue")
        self.cvx += amount
        self._updateReward(a)
        self.cvx -= amount
        self.convex.lock(self.epoch(), amount)
        cur = self.epoch()
        i = self.u(a)
        i.totalLocked = u112(amount + i.totalLocked)
        i.epochLocked[cur % 17] += amount
        self.totalLockedGlobal = s_add(amount, self.totalLockedGlobal)

    def unlock(self, a, amount):  # L13312-L13370
        require(amount != 0, "ZeroValue")
        self._updateReward(a)
        self._updateUnlocked(a)
        i = self.u(a)
        tl, td = i.totalLocked, i.totalDebt
        require(amount <= tl, "InsufficientToUnlock")
        self._checkAccountHealth(tl, td, amount, 0)
        i.totalLocked = u112(tl - amount)
        self.totalLockedGlobal -= amount
        self.totalPendingUnlockGlobal += amount
        nxt = self.epoch() + 1
        for _ in range(17):
            idx = nxt % 17
            locked = i.epochLocked[idx]
            un = locked if amount >= locked else amount
            if un > 0:
                i.epochLocked[idx] = locked - un
                amount -= un
                self.pendingUnlocked[nxt] = self.pendingUnlocked.get(nxt, 0) + un
                if not i.pendingUnlockList or i.pendingUnlockList[-1][1] != nxt:
                    i.pendingUnlockList.append([un, nxt])
                else:
                    i.pendingUnlockList[-1][0] += un
            if amount == 0:
                break
            nxt += 1

    def withdrawUnlocked(self, a):  # L13373-L13397
        self._updateReward(a)
        self._updateUnlocked(a)
        i = self.u(a)
        un = i.totalUnlocked
        i.totalUnlocked = 0
        self.totalUnlockedGlobal = s_sub(self.totalUnlockedGlobal, un)
        if self.cvx < un:
            need = un - self.cvx
            require(self.staked >= need, "RewardPool: withdraw exceeds stake")
            self.staked -= need; self.cvx += need
        require(self.cvx >= un, "CVX: transfer amount exceeds balance")
        self.cvx -= un
        return un

    def borrow(self, a, amount):  # L13435-L13467 (mint to sender)
        require(amount != 0, "ZeroValue")
        self._updateReward(a)
        i = self.u(a)
        r = i.rewards
        bwl = 0
        if r >= amount:
            i.rewards = u128(r - amount)
        else:
            i.rewards = 0
            bwl = amount - r
        if bwl > 0:
            self._checkAccountHealth(i.totalLocked, i.totalDebt, 0, bwl)
            i.totalDebt = u128(i.totalDebt + bwl)
            self.totalDebtGlobal = self.totalDebtGlobal + bwl
        self.clev_minted += amount

    def donate(self, amount):  # L13471-L13476
        require(amount != 0, "ZeroValue")
        self.cvx += amount
        self._distribute(amount)

    def harvest(self, cvx_out):  # L13482-L13530; zap output modelled as cvx_out CVX received
        self.cvx += cvx_out
        amt = cvx_out
        dist = amt
        pf = self.platformFeePercentage
        if pf > 0:
            pf = (dist * pf) // FEE
            dist -= pf
            self.cvx -= pf; self.platform_received += pf
        hb = self.harvestBountyPercentage
        if hb > 0:
            hb = (dist * hb) // FEE
            dist -= hb
            self.cvx -= hb
        self._distribute(dist)
        return amt

    def bribe_harvest_cvx(self, claimed_now, claim_amount):
        """harvestVotiumLikeBribes (L13543-L13573) for a single CVX bribe claim param:
        if not isClaimed -> claim (CVX arrives now); _swapToCVX counts _amounts[i] for token==CVX
        (L14036-L14037) without measuring the balance; then _convertAndDistributeBribes L13976."""
        if claimed_now:
            self.cvx += claim_amount
        amountCVX = claim_amount
        dist = amountCVX
        pf = self.platformFeePercentage
        if pf > 0:
            pf = (dist * pf) // FEE
            dist -= pf
            require(self.cvx >= pf, "CVX: transfer amount exceeds balance")
            self.cvx -= pf; self.platform_received += pf
        self._distribute(dist)
        return amountCVX

    def processUnlockableCVX(self):  # L13665-L13703 (keeper); _fixLockDrift omitted (epoch-gated patch)
        cur = self.epoch()
        extra = s_sub(self.totalCVXInPool(), self.totalUnlockedGlobal)
        before = self.cvx
        self.cvx += self.convex.processExpiredLocks(cur)
        curbal = self.cvx
        unlocked = s_add(s_sub(curbal, before), extra)
        pending = self.pendingUnlocked.get(cur, 0)
        if pending > 0:
            require(unlocked >= pending, "insufficient unlocked CVX")
            unlocked -= pending
            self.totalUnlockedGlobal = s_add(self.totalUnlockedGlobal, pending)
            self.totalPendingUnlockGlobal -= pending
            self.pendingUnlocked[cur] = 0
        if unlocked > 0:
            if curbal < unlocked:
                need = unlocked - curbal
                require(self.staked >= need, "RewardPool: withdraw exceeds stake")
                self.staked -= need; self.cvx += need
            require(self.cvx >= unlocked, "CVX: lock amount exceeds balance")
            self.cvx -= unlocked
            self.convex.lock(cur, unlocked)

    # ---------------- invariants ----------------
    def invariants(self):
        """I-L1: TLG + TPUG == CVX locked in Convex (+ relocked extras, so >=)
           I-L2: TUG <= CVX in contract + staked  (backing of unlocked principal)
           I-L3: sum_u user unlocked claims (incl. matured pending) <= TUG"""
        cur = self.epoch()
        matured = 0
        for i in self.users.values():
            matured += i.totalUnlocked + sum(x[0] for x in i.pendingUnlockList[i.nextUnlockIndex:] if x[1] <= cur)
        return {
            "I-L1 TLG+TPUG<=convex": self.totalLockedGlobal + self.totalPendingUnlockGlobal <= self.convex.total(),
            "I-L2 TUG<=cvx+staked": self.totalUnlockedGlobal <= self.cvx + self.staked,
            "I-L3 matured<=TUG": matured <= self.totalUnlockedGlobal,
            "_": "TLG=%d TPUG=%d TUG=%d convex=%d cvx=%d staked=%d matured=%d" % (
                self.totalLockedGlobal, self.totalPendingUnlockGlobal, self.totalUnlockedGlobal,
                self.convex.total(), self.cvx, self.staked, matured),
        }
