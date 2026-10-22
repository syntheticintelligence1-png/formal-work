// B3 on K1/K2: identical reward inflow (1400e18 over 14 days), different notify granularity.
// Causal pokes: the chunk accrued during ((i)*step, (i+1)*step] is notified at (i+1)*step. Alice staked from day 0; Bob stakes at day 14 (+10s). Measure at day 28.
const { ethers, E18, DAY, at, mineAt, now } = require("../lib");
async function run(label, chunks) {
  const [admin, alice, bob] = await ethers.getSigners();
  const P = 7 * DAY;
  const R = await ethers.deployContract("MockToken", ["R"]);
  const K = await ethers.deployContract("KernelMRA", [P]);
  await (await K.initialize()).wait();
  await (await K.registerRewardToken(R.target, admin.address)).wait();
  await (await R.mint(admin.address, 1400n * E18)).wait();
  await (await R.approve(K.target, ethers.MaxUint256)).wait();
  const t0 = (await now()) + 100;
  await at(t0); await (await K.connect(alice).stake(E18)).wait();
  const total = 1400n * E18, horizon = 14 * DAY, step = horizon / chunks;
  let sent = 0n, reextend = 0, queuedHits = 0;
  for (let i = 0; i < chunks; i++) {
    const amt = i === chunks - 1 ? total - sent : total / BigInt(chunks);
    const before = await K.rewardData(R.target);
    await at(t0 + (i + 1) * step); await (await K.depositReward(R.target, amt)).wait();
    const after = await K.rewardData(R.target);
    if (after.finishAt !== before.finishAt) reextend++; else queuedHits++;
    sent += amt;
  }
  await at(t0 + 14 * DAY + 10); await (await K.connect(bob).stake(E18)).wait();
  await at(t0 + 28 * DAY); await (await K.checkpoint(alice.address)).wait();
  await at(t0 + 28 * DAY + 1); await (await K.checkpoint(bob.address)).wait();
  const cA = await K.claimable(alice.address, R.target), cB = await K.claimable(bob.address, R.target);
  const rd = await K.rewardData(R.target); const [d, left] = await K.pendingRewards(R.target);
  const f = (x) => (Number(x) / 1e18).toFixed(3).padStart(9);
  console.log(`${label.padEnd(22)} notifies=${String(chunks).padStart(4)} period-restarts=${String(reextend).padStart(4)} queued-only=${String(queuedHits).padStart(4)} | Alice=${f(cA)} Bob=${f(cB)} undistributed=${f(rd.queued + d + left)}`);
}
async function main() {
  await run("S_weekly (2x700)", 2);
  await run("S_daily (14x100)", 14);
  await run("S_6h (56x25)", 56);
  await run("S_hourly (336)", 336);
}
main().catch((e) => { console.error(e); process.exit(1); });
