// K1-Pre1 discharge in the rebalance pool: `_checkpoint` notifies freshly minted FXN (L16306) BEFORE the base
// `_checkpoint` accrues pending rewards (L16309). When the FXN period has ended, LinearReward.increase takes branch
// beta1 and overwrites the un-accrued tail. Control run: same emissions, but the pool has no gauge configured and
// FXN is pushed through depositReward (which accrues first, L3659).
const { ethers, E18, DAY, at, mineAt, now, expectRevert } = require("../lib");
async function run(withGauge, lastPokeOffset) {
  const [admin, A, dist] = await ethers.getSigners();
  const base = await ethers.deployContract("PGToken", ["BASE"]);
  const f = await ethers.deployContract("PGToken", ["F"]);
  const fxn = await ethers.deployContract("PGToken", ["FXN"]);
  const ve = await ethers.deployContract("PGVotingEscrow");
  const tr = await ethers.deployContract("PGTreasury", [base.target, f.target]);
  const minter = await ethers.deployContract("PGMinter", [fxn.target]);
  const pool = await ethers.deployContract("BoostableRebalancePool", [fxn.target, ve.target, minter.target]);
  const gaugeAddr = withGauge ? "0x000000000000000000000000000000000000dEaD" : ethers.ZeroAddress;
  await (await pool.initialize(tr.target, admin.address, gaugeAddr)).wait();
  await (await pool.registerRewardToken(fxn.target, dist.address)).wait();
  await (await ve.set(A.address, 100n * E18)).wait(); // A holds all veFXN -> boost ratio 100% (isolates K1-Pre1 from boost forfeiture)
  await (await f.mint(A.address, 1000n * E18)).wait();
  await (await f.connect(A).approve(pool.target, ethers.MaxUint256)).wait();
  await (await fxn.mint(dist.address, 10n ** 24n)).wait();
  await (await fxn.connect(dist).approve(pool.target, ethers.MaxUint256)).wait();
  const P = 7 * DAY;
  const t0 = (await now()) + 100;
  const st = async (tag) => {
    const rd = await pool.rewardData(fxn.target);
    console.log(`   ${tag.padEnd(58)} rate=${rd.rate} lastUpdate=${rd.lastUpdate} finishAt=${rd.finishAt} queued=${rd.queued} | claimable(A)=${await pool.claimable(A.address, fxn.target)} FXN(pool)=${await fxn.balanceOf(pool.target)}`);
  };
  await at(t0); await (await pool.connect(A).deposit(100n * E18, A.address)).wait();
  await st("a1 A.deposit(100e18) [first checkpoint]");
  const t1 = t0 + DAY + 10;
  if (withGauge) { await (await minter.setNext(700n * E18)).wait(); await at(t1); await (await pool.checkpoint(A.address)).wait(); await st("a2 checkpoint(A) -> gauge mints 700e18, notify (L16306)"); }
  else { await at(t1); await (await pool.connect(dist).depositReward(fxn.target, 700n * E18)).wait(); await st("a2 dist.depositReward(700e18) (control path)"); }
  await at(t1 + lastPokeOffset); await (await pool.checkpoint(A.address)).wait();
  await st(`a3 checkpoint(A) at +${lastPokeOffset / DAY}d [last poke inside period]`);
  await at(t1 + 11 * DAY); await (await pool.checkpoint(A.address)).wait();
  await st("a4 checkpoint(A) at +11d [after finishAt; gauge mint 0]");
  await at(t1 + 30 * DAY); await (await pool.checkpoint(A.address)).wait();
  await st("a5 checkpoint(A) at +30d");
  console.log(`   boost ratio(A) = ${Number(await pool.getBoostRatio(A.address)) / 1e18}`);
  const c = await pool.claimable(A.address, fxn.target), b = await fxn.balanceOf(pool.target);
  console.log(`   => credited ${Number(c) / 1e18} of ${Number(b) / 1e18} FXN held; uncredited (stranded) = ${Number(b - c) / 1e18}`);
}
async function main() {
  console.log("== control: depositReward path (accrue-then-notify) =="); await run(false, 1 * DAY);
  console.log("== gauge path, last in-period poke at +1d =="); await run(true, 1 * DAY);
  console.log("== gauge path, last in-period poke at +6.9d =="); await run(true, Math.floor(6.9 * DAY));
}
main().catch((e) => { console.error(e); process.exit(1); });
