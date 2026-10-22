// H5: B5 propagation - Furnace rate-0 freeze (P>0) blocks every AladdinCVX entry point that checkpoints.
const hre = require("hardhat");
const { ethers } = hre;
const CVX = "0x4e3FBD56CD56c3e72c1403e103b45Db9da5B9D2B";
const CVX_REWARD_POOL = "0xCF50b810E57Ac33B91dCF525C6ddd9881B139332";
const E18 = 10n ** 18n, DAY = 86400;
async function etch(addr, name) {
  const c = await (await ethers.getContractFactory(name)).deploy(); await c.waitForDeployment();
  await hre.network.provider.send("hardhat_setCode", [addr, await ethers.provider.getCode(await c.getAddress())]);
  return ethers.getContractAt(name, addr);
}
async function tryTx(label, p) {
  try { const tx = await p; await tx.wait(); console.log(`  ${label.padEnd(60)} -> ok`); }
  catch (e) { console.log(`  ${label.padEnd(60)} -> REVERT ${(e.shortMessage || e.message).replace(/\s+/g, " ").slice(0, 110)}`); }
}
async function now() { return (await ethers.provider.getBlock("latest")).timestamp; }
async function warp(t) { await hre.network.provider.send("evm_setNextBlockTimestamp", [t]); }
async function main() {
  const [owner, gov, keeper, bob] = await ethers.getSigners();
  const cvx = await etch(CVX, "CleverMockToken"); await etch(CVX_REWARD_POOL, "MockCvxRewardPool");
  const T = await ethers.getContractFactory("CleverMockToken");
  const clev = await T.deploy(); const lp = await T.deploy(); await clev.waitForDeployment(); await lp.waitForDeployment();
  const F = await (await ethers.getContractFactory("contracts/bundle/clever/Furnace.sol:Furnace")).deploy(); await F.waitForDeployment();
  await (await F.initialize(gov.address, await clev.getAddress(), owner.address, owner.address, 0, 0)).wait();
  await (await F.connect(gov).updatePeriodLength(7 * DAY)).wait();
  await (await F.updateWhitelists([keeper.address], true)).wait();
  const pool = await (await ethers.getContractFactory("MockCurvePool")).deploy(CVX, await clev.getAddress(), await lp.getAddress()); await pool.waitForDeployment();
  await (await pool.seed(1_000_000n * E18, 1_200_000n * E18)).wait();
  await (await clev.mint(await pool.getAddress(), 1_200_000n * E18)).wait(); await (await cvx.mint(await pool.getAddress(), 1_000_000n * E18)).wait();
  const strat = await (await ethers.getContractFactory("MockAMOStrategy")).deploy(await lp.getAddress()); await strat.waitForDeployment();
  const AMO = await (await ethers.getContractFactory("contracts/bundle/concentrator/clever/cvx/AladdinCVX.sol:AladdinCVX"))
    .deploy(CVX, await clev.getAddress(), await pool.getAddress(), await lp.getAddress(), await F.getAddress()); await AMO.waitForDeployment();
  const A = await AMO.getAddress();
  await (await AMO.initialize(owner.address, await strat.getAddress(), 10n ** 10n, [])).wait();
  await (await cvx.mint(bob.address, 1000n * E18)).wait(); await (await cvx.connect(bob).approve(A, 10n ** 30n)).wait();
  await (await cvx.mint(keeper.address, 10n ** 24n)).wait(); await (await cvx.connect(keeper).approve(await F.getAddress(), 10n ** 30n)).wait();
  console.log("=== H5: AMO over a Furnace with periodLength = 7 days ===");
  await tryTx("bob.deposit(1000e18 CVX, bob)", AMO.connect(bob).deposit(1000n * E18, bob.address));
  await warp((await now()) + 3 * DAY);
  await tryTx("bob.unlock(0)", AMO.connect(bob).unlock(0));
  await tryTx("keeper.distribute(keeper, 100e18)  [period starts]", F.connect(keeper).distribute(keeper.address, 100n * E18));
  await warp((await now()) + 8 * DAY);
  await tryTx("whitelisted distribute(.., 1) after finishAt (= locker.donate(1))", F.connect(keeper).distribute(keeper.address, 1n));
  await warp((await now()) + 12);
  const sh = await AMO.balanceOf(bob.address);
  await tryTx("AMO.checkpoint()", AMO.checkpoint());
  await tryTx("bob.withdraw(all, bob, 0, 0)", AMO.connect(bob).withdraw(sh, bob.address, 0, 0));
  await tryTx("bob.withdrawToBase(all, bob, 0)", AMO.connect(bob).withdrawToBase(sh, bob.address, 0));
  await tryTx("AMO.harvest(bob, 0)  [harvester unset]", AMO.harvest(bob.address, 0));
}
main().catch((e) => { console.error(e); process.exit(1); });
