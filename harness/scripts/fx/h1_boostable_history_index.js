// H1: BoostableRebalancePool boostCheckpoint.historyIndex = numTotalSupplyHistory (L16315) points one past the
// last written totalSupplyHistory entry after a claim/checkpoint that records no supply (L16412-L16423 not called).
// _boostRatioAt (L16543-L16580) then reads the zero struct totalSupplyHistory[n].
const { ethers, E18, DAY, now, setTime, advance, tx, view, prod, setupPool } = require("./lib");

async function main() {
  const fx = await setupPool("Boostable");
  const { A, B, C, D, liq, dist, fxn, ve, pool } = fx;
  const pct = (r) => (Number(r) / 1e16).toFixed(2) + "%";

  console.log("== Variant (a): exponent 0 -> boost ratio silently forced to the 40% floor ==");
  await (await ve.set(A.address, 50n * E18)).wait();
  await (await ve.set(B.address, 50n * E18)).wait();
  await tx("A.deposit(100e18)", pool.connect(A).deposit(100n * E18, A.address));
  await tx("B.deposit(100e18)", pool.connect(B).deposit(100n * E18, B.address));
  await tx("dist.depositReward(FXN, 7000e18)", pool.connect(dist).depositReward(await fxn.getAddress(), 7000n * E18));
  await advance(DAY);
  await tx("A.claim()  [checkpoint without supply record]", pool.connect(A)["claim()"]());
  console.log("  numTotalSupplyHistory =", (await pool.numTotalSupplyHistory()).toString(),
    "; boostCheckpoint(A).historyIndex =", (await pool.boostCheckpoint(A.address)).historyIndex.toString(),
    "; boostCheckpoint(B).historyIndex =", (await pool.boostCheckpoint(B.address)).historyIndex.toString());
  await advance(DAY);
  await view("getBoostRatio(A)", pool.getBoostRatio(A.address), pct);
  await view("getBoostRatio(B)", pool.getBoostRatio(B.address), pct);
  const fa0 = await fxn.balanceOf(A.address), fb0 = await fxn.balanceOf(B.address);
  await tx("A.claim()", pool.connect(A)["claim()"]());
  await tx("B.claim()", pool.connect(B)["claim()"]());
  const fa = (await fxn.balanceOf(A.address)) - fa0, fb = (await fxn.balanceOf(B.address)) - fb0;
  console.log(`  FXN received in this claim: A=${ethers.formatEther(fa)} (covers 1 day), B=${ethers.formatEther(fb)} (covers 2 days)`);

  console.log("\n== Variant (b): exponent >= 1 -> checked uint24 underflow in _getCompoundedBalance (L16445) ==");
  const fx2 = await setupPool("Boostable");
  const p2 = fx2.pool;
  await (await fx2.ve.set(fx2.A.address, 50n * E18)).wait();
  await (await fx2.ve.set(fx2.B.address, 50n * E18)).wait();
  await tx("C.deposit(1e18)", p2.connect(fx2.C).deposit(E18, fx2.C.address));
  await tx("liquidate(maxAmount = 1e18 - 1e8)", p2.connect(fx2.liq).liquidate(E18 - 10n ** 8n, 0));
  const ts = await p2.totalSupplyHistory((await p2.numTotalSupplyHistory()) - 1n);
  console.log("  product after liquidation:", prod(ts.product));
  await tx("A.deposit(100e18)", p2.connect(fx2.A).deposit(100n * E18, fx2.A.address));
  await tx("B.deposit(100e18)", p2.connect(fx2.B).deposit(100n * E18, fx2.B.address));
  await tx("dist.depositReward(FXN, 7000e18)", p2.connect(fx2.dist).depositReward(await fx2.fxn.getAddress(), 7000n * E18));
  await advance(DAY);
  await tx("A.claim()", p2.connect(fx2.A)["claim()"]());
  await advance(DAY);
  await view("getBoostRatio(A)", p2.getBoostRatio(fx2.A.address), pct);
  await view("claimable(A, FXN)", p2.claimable(fx2.A.address, await fx2.fxn.getAddress()));
  await tx("A.claim()", p2.connect(fx2.A)["claim()"]());
  await tx("A.withdraw(1e18)", p2.connect(fx2.A).withdraw(E18, fx2.A.address));
  await tx("A.deposit(1e18)", p2.connect(fx2.A).deposit(E18, fx2.A.address));
  await view("getBoostRatio(B) (control)", p2.getBoostRatio(fx2.B.address), pct);
  await advance(10 * DAY);
  await tx("A.withdraw(1e18) after 10 more days", p2.connect(fx2.A).withdraw(E18, fx2.A.address));
  await tx("D.deposit(1 wei) for a fresh receiver (appends a history entry)", p2.connect(fx2.D).deposit(1n, fx2.D.address));
  await tx("A.withdraw(1e18) after the append", p2.connect(fx2.A).withdraw(E18, fx2.A.address));
}

main().catch((e) => {
  console.error(e);
  process.exit(1);
});
