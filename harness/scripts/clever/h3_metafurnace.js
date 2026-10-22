// H3: MetaFurnace.totalBaseTokenInPool ordering (a) and unit (b) defects on bundle bytecode.
const hre = require("hardhat");
const { ethers } = hre;
const E18 = 10n ** 18n;
const DAY = 86400;

async function tryTx(label, p) {
  try { const tx = await p; await tx.wait(); console.log(`  ${label.padEnd(66)} -> ok`); return true; }
  catch (e) { console.log(`  ${label.padEnd(66)} -> REVERT ${(e.shortMessage || e.message).replace(/\s+/g, " ").slice(0, 100)}`); return false; }
}
async function tryView(label, p) {
  try { console.log(`  ${label.padEnd(66)} -> ${await p}`); } catch (e) { console.log(`  ${label.padEnd(66)} -> VIEW REVERT ${(e.shortMessage || e.message).replace(/\s+/g, " ").slice(0, 90)}`); }
}
async function now() { return (await ethers.provider.getBlock("latest")).timestamp; }
async function warp(t) { await hre.network.provider.send("evm_setNextBlockTimestamp", [t]); }

async function setup(baseDec, withStrategy, pct) {
  const [owner, dist, alice, bob] = await ethers.getSigners();
  const T = await ethers.getContractFactory("CleverMockToken");
  const base = await T.deploy(); await base.waitForDeployment();
  if (baseDec !== 18) await (await base.setDecimals(baseDec)).wait();
  const debt = await T.deploy(); await debt.waitForDeployment();
  const MF = await (await ethers.getContractFactory("contracts/bundle/clever/generic/MetaFurnace.sol:MetaFurnace")).deploy();
  await MF.waitForDeployment();
  const A = await MF.getAddress();
  await (await MF.initialize(await base.getAddress(), await debt.getAddress())).wait();
  await (await MF.updatePeriodLength(7 * DAY)).wait();
  await (await MF.updateWhitelists([dist.address], true)).wait();
  let S = null;
  if (withStrategy) {
    S = await (await ethers.getContractFactory("MockYieldStrategy")).deploy(await base.getAddress());
    await S.waitForDeployment();
    await (await MF.migrateStrategy(await S.getAddress())).wait();
    await (await MF.updateYieldInfo(pct, 0)).wait();
  }
  for (const u of [alice, bob]) {
    await (await debt.mint(u.address, 10000n * E18)).wait();
    await (await debt.connect(u).approve(A, 10n ** 30n)).wait();
  }
  await (await base.mint(dist.address, 10n ** 30n)).wait();
  return { MF, A, base, debt, S, dist, alice, bob };
}

async function main() {
  console.log("=== H3a: 18-dec base, P = 7d, strategy percentage 65535/1e5 (uint16 max, L4984 / L5198) ===");
  let c = await setup(18, true, 65535);
  await tryTx("alice.deposit(alice, 1000e18 debt)", c.MF.connect(c.alice).deposit(c.alice.address, 1000n * E18));
  await (await c.base.connect(c.dist).transfer(c.A, 700n * E18)).wait();
  await tryTx("dist: transfer 700e18 base + distribute(dist, base, 700e18)", c.MF.connect(c.dist).distribute(c.dist.address, await c.base.getAddress(), 700n * E18));
  const t0 = await now();
  await warp(t0 + 8 * DAY);
  await tryTx("updatePendingDistribution() after period 1", c.MF.updatePendingDistribution());
  await (await c.base.connect(c.dist).transfer(c.A, 700n * E18)).wait();
  await tryTx("dist: transfer 700e18 base + distribute(...) [period 2]", c.MF.connect(c.dist).distribute(c.dist.address, await c.base.getAddress(), 700n * E18));
  console.log(`  base in contract=${await c.base.balanceOf(c.A)} in strategy=${await c.base.balanceOf(await c.S.getAddress())}`);
  await tryView("totalBaseTokenInPool()", c.MF.totalBaseTokenInPool());
  await tryTx("alice.claim(alice)  [realised from period 1]", c.MF.connect(c.alice).claim(c.alice.address));
  console.log(`  base in contract=${await c.base.balanceOf(c.A)} in strategy=${await c.base.balanceOf(await c.S.getAddress())}`);
  await tryView("totalBaseTokenInPool()", c.MF.totalBaseTokenInPool());
  await tryTx("bob.deposit(bob, 10e18 debt)", c.MF.connect(c.bob).deposit(c.bob.address, 10n * E18));
  await tryTx("dist: distribute(dist, base, 1)  [harvest path L5436]", c.MF.connect(c.dist).distribute(c.dist.address, await c.base.getAddress(), 1n));

  console.log("\n=== H3b: 6-dec base, P = 7d, no strategy ===");
  c = await setup(6, false, 0);
  await tryTx("alice.deposit(alice, 1000e18 debt)", c.MF.connect(c.alice).deposit(c.alice.address, 1000n * E18));
  await (await c.base.connect(c.dist).transfer(c.A, 700n * 10n ** 6n)).wait();
  await tryTx("dist: transfer 700e6 base + distribute(dist, base, 700e6)", c.MF.connect(c.dist).distribute(c.dist.address, await c.base.getAddress(), 700n * 10n ** 6n));
  const ri = await c.MF.rewardInfo();
  console.log(`  rewardInfo.ratePerSecond = ${ri.ratePerSecond} (debt units/s); base balance = ${await c.base.balanceOf(c.A)} (base units)`);
  await warp((await now()) + DAY);
  await tryView("totalBaseTokenInPool()", c.MF.totalBaseTokenInPool());
  await tryTx("bob.deposit(bob, 10e18 debt)  [during period]", c.MF.connect(c.bob).deposit(c.bob.address, 10n * E18));

  console.log("\n=== H3c: 6-dec base, P = 7d, strategy 50% ===");
  c = await setup(6, true, 50000);
  await tryTx("alice.deposit(alice, 1000e18 debt)", c.MF.connect(c.alice).deposit(c.alice.address, 1000n * E18));
  await (await c.base.connect(c.dist).transfer(c.A, 700n * 10n ** 6n)).wait();
  await tryTx("dist: transfer 700e6 + distribute(dist, base, 700e6)", c.MF.connect(c.dist).distribute(c.dist.address, await c.base.getAddress(), 700n * 10n ** 6n));
}
main().catch((e) => { console.error(e); process.exit(1); });
