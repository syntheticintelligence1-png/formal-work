// H4: AladdinCVX (CLeverAMOBase) exit freeze when its Furnace unrealised is 0 (paid-off Furnace).
const hre = require("hardhat");
const { ethers } = hre;
const CVX = "0x4e3FBD56CD56c3e72c1403e103b45Db9da5B9D2B";
const CVX_REWARD_POOL = "0xCF50b810E57Ac33B91dCF525C6ddd9881B139332";
const E18 = 10n ** 18n;
const DAY = 86400;

async function etch(addr, name) {
  const c = await (await ethers.getContractFactory(name)).deploy(); await c.waitForDeployment();
  await hre.network.provider.send("hardhat_setCode", [addr, await ethers.provider.getCode(await c.getAddress())]);
  return ethers.getContractAt(name, addr);
}
async function tryTx(label, p) {
  try { const tx = await p; await tx.wait(); console.log(`  ${label.padEnd(70)} -> ok`); return true; }
  catch (e) { console.log(`  ${label.padEnd(70)} -> REVERT ${(e.shortMessage || e.message).replace(/\s+/g, " ").slice(0, 120)}`); return false; }
}
async function now() { return (await ethers.provider.getBlock("latest")).timestamp; }
async function warp(t) { await hre.network.provider.send("evm_setNextBlockTimestamp", [t]); }

async function main() {
  const [owner, gov, keeper, bob, alice] = await ethers.getSigners();
  const cvx = await etch(CVX, "CleverMockToken");
  await etch(CVX_REWARD_POOL, "MockCvxRewardPool");
  const T = await ethers.getContractFactory("CleverMockToken");
  const clev = await T.deploy(); await clev.waitForDeployment();
  const lp = await T.deploy(); await lp.waitForDeployment();
  const F = await (await ethers.getContractFactory("contracts/bundle/clever/Furnace.sol:Furnace")).deploy(); await F.waitForDeployment();
  await (await F.initialize(gov.address, await clev.getAddress(), owner.address, owner.address, 0, 0)).wait();
  await (await F.updateWhitelists([keeper.address], true)).wait();
  const pool = await (await ethers.getContractFactory("MockCurvePool")).deploy(CVX, await clev.getAddress(), await lp.getAddress()); await pool.waitForDeployment();
  await (await pool.seed(1_000_000n * E18, 1_200_000n * E18)).wait();
  await (await clev.mint(await pool.getAddress(), 1_200_000n * E18)).wait();
  await (await cvx.mint(await pool.getAddress(), 1_000_000n * E18)).wait();
  const strat = await (await ethers.getContractFactory("MockAMOStrategy")).deploy(await lp.getAddress()); await strat.waitForDeployment();
  const AMO = await (await ethers.getContractFactory("contracts/bundle/concentrator/clever/cvx/AladdinCVX.sol:AladdinCVX"))
    .deploy(CVX, await clev.getAddress(), await pool.getAddress(), await lp.getAddress(), await F.getAddress());
  await AMO.waitForDeployment();
  const A = await AMO.getAddress();
  await (await AMO.initialize(owner.address, await strat.getAddress(), 10n ** 10n, [])).wait();

  console.log("=== H4: AMO shares exist, then the Furnace is paid off ===");
  await (await cvx.mint(bob.address, 1000n * E18)).wait();
  await (await cvx.connect(bob).approve(A, 10n ** 30n)).wait();
  await tryTx("bob.deposit(1000e18 CVX, bob)", AMO.connect(bob).deposit(1000n * E18, bob.address));
  await warp((await now()) + 3 * DAY);
  await tryTx("bob.unlock(0)  [first shares, totalSupply was 0]", AMO.connect(bob).unlock(0));
  let ui = await F.getUserInfo(A);
  console.log(`  AMO shares: bob=${await AMO.balanceOf(bob.address)} ; Furnace.getUserInfo(AMO)=(${ui[0]}, ${ui[1]}) ; ratio()=${await AMO.ratio()}`);
  await (await cvx.mint(keeper.address, 10n ** 24n)).wait();
  await (await cvx.connect(keeper).approve(await F.getAddress(), 10n ** 30n)).wait();
  const tu = await F.totalUnrealised();
  await tryTx(`keeper.distribute(keeper, TU + 100e18 = ${tu + 100n * E18})  [paid off]`, F.connect(keeper).distribute(keeper.address, tu + 100n * E18));
  ui = await F.getUserInfo(A);
  console.log(`  Furnace.getUserInfo(AMO)=(unrealised ${ui[0]}, realised ${ui[1]}) ; free CVX in Furnace=${(await F.totalCVXInPool()) - (await F.totalRealised())}`);
  const sh = await AMO.balanceOf(bob.address);
  await tryTx("bob.withdraw(all shares, bob, 0, 0)", AMO.connect(bob).withdraw(sh, bob.address, 0, 0));
  await tryTx("bob.withdrawToBase(all shares, bob, 0)", AMO.connect(bob).withdrawToBase(sh, bob.address, 0));
  await tryTx("anyone.checkpoint()", AMO.checkpoint());
  await tryTx("owner.rebalance(1, 0, 0, max)", AMO.rebalance(1, 0, 0, ethers.MaxUint256));
  console.log("  -- dust variant: pendingBaseToken makes the converted amount not a multiple of 1e9 --");
  await (await cvx.mint(owner.address, 1000n)).wait();
  await (await cvx.approve(A, 1000n)).wait();
  await tryTx("someone.donate(123 wei)", AMO.donate(123n));
  await tryTx("anyone.checkpoint()", AMO.checkpoint());
  ui = await F.getUserInfo(A);
  console.log(`  Furnace.getUserInfo(AMO)=(unrealised ${ui[0]}, realised ${ui[1]})`);
  await tryTx("bob.withdraw(all shares, bob, 0, 0)", AMO.connect(bob).withdraw(sh, bob.address, 0, 0));
  await (await cvx.mint(alice.address, 1000n * E18)).wait();
  await (await cvx.connect(alice).approve(A, 10n ** 30n)).wait();
  await tryTx("alice.deposit(1000e18 CVX, alice)", AMO.connect(alice).deposit(1000n * E18, alice.address));
  await warp((await now()) + 3 * DAY);
  await tryTx("someone.donate(123 wei)", AMO.donate(123n));
  const before = await cvx.balanceOf(A);
  await tryTx("alice.unlock(0)", AMO.connect(alice).unlock(0));
  console.log(`  alice shares = ${await AMO.balanceOf(alice.address)}  (her 1000e18 CVX left the lock: AMO CVX balance ${before} -> ${await cvx.balanceOf(A)})`);
}
main().catch((e) => { console.error(e); process.exit(1); });
