"""
m04 - ConcentratorCompounderStash.processBatch (L2405-L2436) with ConcentratorStashBase._transfer (L156-L161) / _convert (L170-L188),
0.8.20 semantics. Compared with the NatSpec intent (L2394-L2404): every non-asset token is converted with its partial
route to the intermediate token, the intermediate total is converted with the final route to `asset`.
Converter abstraction (A-CONV, ITokenConverter L193-L311 "Assuming that the input token is already in the contract"):
  convert(route=(tin,tout,price), amountIn, recipient): requires converter's tin balance >= amountIn, pays
  amountIn*price/1e18 of tout to recipient, returns it; amountIn == 0 returns 0 (variant `zero_reverts` reverts).
Compounder abstraction: depositReward(x) pulls x `asset` from the stash (IRewardDistributor L945-L948).
Run: python3 -I m04_stash_processbatch.py
"""
import copy
from collections import defaultdict


class Revert(Exception):
    pass


def req(c, m):
    if not c:
        raise Revert(m)


E18 = 10 ** 18
FEE = 10 ** 9
ASSET, SDT, WETH = "asset", "SDT", "WETH"


class World:
    def __init__(self, zero_reverts=False):
        self.bal = defaultdict(int)
        self.zero_reverts = zero_reverts
        self.harvesterRatio = 0
        self.expenseRatio = 0
        self.deposited = 0

    def transfer(self, t, frm, to, a):
        req(self.bal[(t, frm)] >= a, f"ERC20: transfer amount exceeds balance [{t}@{frm}]")
        self.bal[(t, frm)] -= a
        self.bal[(t, to)] += a

    # ITokenConverter.convert (mock, A-CONV)
    def convert(self, route, amountIn, recipient):
        tin, tout, price = route
        if amountIn == 0:
            req(not self.zero_reverts, "converter: zero amount")
            return 0
        req(self.bal[(tin, "converter")] >= amountIn, f"converter: insufficient {tin}")
        self.bal[(tin, "converter")] -= amountIn
        out = amountIn * price // E18
        self.bal[(tout, recipient)] += out
        return out

    # ConcentratorStashBase._transfer (L156-L161): BDR of the whole stash balance (L157)
    def _transfer(self, token):
        amt = self.bal[(token, "stash")]
        if amt > 0:
            self.transfer(token, "stash", "converter", amt)
        return amt

    # ConcentratorStashBase._convert (L170-L188)
    def _convert(self, amountIn, routes, receiver):
        out = amountIn
        n = len(routes)
        if n > 0:
            for i in range(n - 1):
                out = self.convert(routes[i], out, "converter")
            out = self.convert(routes[n - 1], out, receiver)
        return out

    # ConcentratorCompounderStash._distribute (L2447-L2474)
    def _distribute(self, assets, minAsset, receiver):
        req(assets >= minAsset, "InsufficientHarvestedAssets")
        hb = assets * self.harvesterRatio // FEE
        if hb:
            self.transfer(ASSET, "stash", receiver, hb)
        pf = assets * self.expenseRatio // FEE
        if pf:
            self.transfer(ASSET, "stash", "treasury", pf)
        x = assets - hb - pf
        self.transfer(ASSET, "stash", "compounder", x)  # compounder.depositReward(x) pulls x
        self.deposited += x

    def processBatch(self, tokens, partialRoutes, intermediate, finalRoute, receiver, minAsset):  # L2405-L2436
        assets = 0
        im = 0
        calls = []
        for i, t in enumerate(tokens):
            if t == ASSET:
                assets = self.bal[(t, "stash")]  # `=` (overwrite), not `+=`
            else:
                amount = self._transfer(t)
                if amount > 0:
                    if intermediate == ASSET:
                        calls.append(("im", t, amount, assets))
                        im += self._convert(assets, partialRoutes[i], "converter")  # amountIn = _assets (!)
                    else:
                        calls.append(("direct", t, amount, assets))
                        assets += self._convert(assets, partialRoutes[i], "stash")  # amountIn = _assets (!)
        if im > 0:
            assets += self._convert(im, finalRoute, "stash")
        self._distribute(assets, minAsset, receiver)
        return assets, calls

    def intended(self, tokens, partialRoutes, finalRoute):
        """reference semantics from the NatSpec: convert each token's own amount, then the intermediate total"""
        w = copy.deepcopy(self)
        assets = 0
        im = 0
        for i, t in enumerate(tokens):
            if t == ASSET:
                assets += w.bal[(t, "stash")]
            else:
                a = w._transfer(t)
                if a:
                    im += w._convert(a, partialRoutes[i], "converter")
        if im:
            assets += w._convert(im, finalRoute, "stash")
        return assets


def run(label, w, *args):
    snap = copy.deepcopy(w.__dict__)
    try:
        assets, calls = w.processBatch(*args)
        print(f"  {label}: OK _assets={assets} convert-calls(kind, token, _amount, amountIn passed)={calls}")
        print(f"     stash->compounder deposited={w.deposited}; stranded in converter: "
              f"{ {t: w.bal[(t, 'converter')] for t in (SDT, WETH, ASSET) if w.bal[(t, 'converter')]} }")
    except Revert as e:
        w.__dict__.clear()
        w.__dict__.update(snap)
        print(f"  {label}: REVERT('{e}')")


if __name__ == "__main__":
    SDT_WETH = (SDT, WETH, 5 * 10 ** 14)  # 1 SDT = 0.0005 WETH
    WETH_ASSET = (WETH, ASSET, 2000 * E18)  # 1 WETH = 2000 asset
    SDT_ASSET = (SDT, ASSET, E18)
    print("== processBatch: tokens=[SDT], intermediate=WETH, partial=[[SDT->WETH]], final=[WETH->asset] ==")
    for zr in (False, True):
        w = World(zero_reverts=zr)
        w.bal[(SDT, "stash")] = 100 * E18
        w.bal[(WETH, "converter")] = 0
        print(f"  intended result (NatSpec) = {w.intended([SDT], [[SDT_WETH]], [WETH_ASSET])} asset")
        run(f"converter zero-input {'reverts' if zr else 'returns 0'}, minAsset=0", w,
            [SDT], [[SDT_WETH]], WETH, [WETH_ASSET], "keeper", 0)
    w = World()
    w.bal[(SDT, "stash")] = 100 * E18
    run("minAsset=1 (any positive slippage bound)", w, [SDT], [[SDT_WETH]], WETH, [WETH_ASSET], "keeper", 1)
    print("== processBatch: tokens=[asset, SDT] (stash holds 10e18 asset), same routes ==")
    w = World()
    w.bal[(SDT, "stash")] = 100 * E18
    w.bal[(ASSET, "stash")] = 10 * E18
    print(f"  intended result (NatSpec) = {w.intended([ASSET, SDT], [[], [SDT_WETH]], [WETH_ASSET])} asset")
    run("minAsset=0", w, [ASSET, SDT], [[], [SDT_WETH]], WETH, [WETH_ASSET], "keeper", 0)
    print("== processBatch: intermediate == asset, tokens=[asset, SDT], partial=[[],[SDT->asset]], final=[] ==")
    w = World()
    w.bal[(SDT, "stash")] = 100 * E18
    w.bal[(ASSET, "stash")] = 10 * E18
    print(f"  intended result (NatSpec) = {w.intended([ASSET, SDT], [[], [SDT_ASSET]], [])} asset")
    run("minAsset=0", w, [ASSET, SDT], [[], [SDT_ASSET]], ASSET, [], "keeper", 0)
    print("== process (single token) for comparison: converts the token's own balance ==")
    w = World()
    w.bal[(SDT, "stash")] = 100 * E18
    amt = w._transfer(SDT)
    out = w._convert(amt, [SDT_WETH, WETH_ASSET], "stash")
    w._distribute(out, 0, "keeper")
    print(f"  process(SDT, [SDT->WETH, WETH->asset]) -> {out} asset deposited={w.deposited}")
