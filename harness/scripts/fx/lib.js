const hre = require("hardhat");
const { ethers } = hre;

const E18 = 10n ** 18n;
const DAY = 86400;
const WEEK = 7 * DAY;

async function now() {
  return (await ethers.provider.getBlock("latest")).timestamp;
}
async function setTime(t) {
  await hre.network.provider.send("evm_setNextBlockTimestamp", [t]);
  await hre.network.provider.send("evm_mine");
}
async function advance(dt) {
  await setTime((await now()) + dt);
}
function why(e) {
  const m = e.shortMessage || e.message || String(e);
  return m.split("\n")[0].slice(0, 160);
}
async function tx(label, p) {
  try {
    const r = await (await p).wait();
    console.log(`  ${label}: ok`);
    return r;
  } catch (e) {
    console.log(`  ${label}: REVERT ${why(e)}`);
    return null;
  }
}
async function view(label, p, fmt = (x) => x.toString()) {
  try {
    const r = await p;
    console.log(`  ${label} = ${fmt(r)}`);
    return r;
  } catch (e) {
    console.log(`  ${label}: REVERT ${why(e)}`);
    return null;
  }
}
async function deploy(name, ...args) {
  const f = await ethers.getContractFactory(name);
  const c = await f.deploy(...args);
  await c.waitForDeployment();
  return c;
}
function prod(p) {
  p = BigInt(p);
  return `(epoch ${p >> 88n}, exp ${(p >> 64n) & 0xffffffn}, mag ${p & 0xffffffffffffffffn})`;
}

// Deploys tokens, mocks and a rebalance pool. kind: "Boostable" | "Shareable"
async function setupPool(kind) {
  const [admin, A, B, C, D, O, liq, dist] = await ethers.getSigners();
  const base = await deploy("FxMockToken", "base", "BASE", 18);
  const f = await deploy("FxMockToken", "fToken", "F", 18);
  const fxn = await deploy("FxMockToken", "FXN", "FXN", 18);
  const ve = await deploy("FxMockVE");
  const treasury = await deploy("FxMockPoolTreasury", await base.getAddress(), await f.getAddress());
  const market = await deploy("FxMockPoolMarket", await base.getAddress(), await f.getAddress());
  let pool;
  if (kind === "Boostable") {
    pool = await deploy("BoostableRebalancePool", await fxn.getAddress(), await ve.getAddress(), admin.address);
  } else {
    const helper = await deploy("FxMockVeHelper", await ve.getAddress());
    pool = await deploy(kind === "ShareableV2" ? "ShareableRebalancePoolV2" : "ShareableRebalancePool",
      await fxn.getAddress(), await ve.getAddress(), await helper.getAddress(), admin.address);
  }
  await (await pool.initialize(await treasury.getAddress(), await market.getAddress(), ethers.ZeroAddress)).wait();
  await (await pool.registerRewardToken(await fxn.getAddress(), dist.address)).wait();
  await (await pool.registerRewardToken(await base.getAddress(), dist.address)).wait();
  await (await pool.grantRole(await pool.LIQUIDATOR_ROLE(), liq.address)).wait();
  await (await pool.updateLiquidatableCollateralRatio(2n * E18)).wait();
  for (const s of [A, B, C, D, O]) {
    await (await f.mint(s.address, 10n ** 30n)).wait();
    await (await f.connect(s).approve(await pool.getAddress(), ethers.MaxUint256)).wait();
  }
  await (await fxn.mint(dist.address, 10n ** 30n)).wait();
  await (await fxn.connect(dist).approve(await pool.getAddress(), ethers.MaxUint256)).wait();
  return { admin, A, B, C, D, O, liq, dist, base, f, fxn, ve, treasury, market, pool };
}

module.exports = { hre, ethers, E18, DAY, WEEK, now, setTime, advance, why, tx, view, deploy, prod, setupPool };
