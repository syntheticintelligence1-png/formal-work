// K1: LinearReward.increase precondition (lastUpdate == now) — library-level behaviour when it is violated,
// and the 10%-rule queue whose release needs a further notify (liveness).
const { ethers, E18, DAY, at, mineAt, now } = require("../lib");
async function main() {
  const P = 7 * DAY;
  const L = await ethers.deployContract("LinearRewardProbe");
  const fmt = async () => { const d = await L.data(); const [dist, left] = await L.pending(); return `queued=${d.queued} rate=${d.rate} lastUpdate=${d.lastUpdate} finishAt=${d.finishAt} | pending=(${dist}, ${left})`; };
  const t0 = (await now()) + 1000;
  // Branch 1 (now >= finishAt) without prior accrual: un-accrued mass rate*(finishAt-lastUpdate) is overwritten.
  await (await L.set(0, 10n ** 12n, t0, t0 + P)).wait();
  await mineAt(t0 + P + 100);
  console.log("B1 pre :", await fmt());
  await at(t0 + P + 200); await (await L.increase(P, 0)).wait();
  console.log("B1 post:", await fmt(), " <- mass 1e12*P =", (10n ** 12n) * BigInt(P), "no longer represented");
  // Branch 2 (now < finishAt) without prior accrual: un-accrued mass is rolled into the new period (not destroyed).
  const t1 = (await now()) + 1000;
  await (await L.set(0, 10n ** 12n, t1, t1 + P)).wait();
  await mineAt(t1 + P / 2);
  console.log("B2 pre :", await fmt());
  await at(t1 + P / 2 + 1); await (await L.increase(P, 10n ** 12n * BigInt(P))).wait();
  console.log("B2 post:", await fmt());
  // 10% rule: a small notify inside a period is queued; queue is released only by a later notify.
  const t2 = (await now()) + 1000;
  await (await L.set(0, 0, 0, 0)).wait();
  await at(t2); await (await L.increase(P, 700n * E18)).wait();
  console.log("Q0 after increase(700e18):", await fmt());
  await at(t2 + DAY); await (await L.increase(P, 1n * E18)).wait();
  console.log("Q1 after increase(1e18) @+1d:", await fmt());
  await mineAt(t2 + 30 * DAY);
  console.log("Q2 @+30d, no further notify:", await fmt());
}
main().catch((e) => { console.error(e); process.exit(1); });
