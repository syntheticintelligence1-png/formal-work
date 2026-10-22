// K2/O2a: periodLength == 0 and total share == 0 at deposit time -> `queued` is never consumed.
const { ethers, E18, DAY, at, mineAt, now, expectRevert } = require("../lib");
async function main() {
  const [admin, alice] = await ethers.getSigners();
  const R = await ethers.deployContract("MockToken", ["R"]);
  const K = await ethers.deployContract("KernelMRA", [0]);
  await (await K.initialize()).wait();
  await (await K.registerRewardToken(R.target, admin.address)).wait();
  await (await R.mint(admin.address, 101n * E18)).wait();
  await (await R.approve(K.target, ethers.MaxUint256)).wait();
  const show = async (tag) => {
    const rd = await K.rewardData(R.target);
    const snap = await K.rewardSnapshot(R.target);
    console.log(`${tag.padEnd(46)} | totalShare=${await K.totalShare()} queued=${rd.queued} integral=${snap.integral} bal(K)=${await R.balanceOf(K.target)} claimable(alice)=${await K.claimable(alice.address, R.target)}`);
  };
  const t0 = (await now()) + 100;
  await show("s0 (periodLength=0)");
  await at(t0); await (await K.depositReward(R.target, 100n * E18)).wait();
  await show("a1 depositReward(R,100e18) @ totalShare=0");
  await at(t0 + 10); await (await K.connect(alice).stake(10n * E18)).wait();
  await show("a2 alice.stake(10e18)");
  await at(t0 + 20); await (await K.depositReward(R.target, 0)).wait();
  await show("a3 depositReward(R,0)");
  await at(t0 + 30); await (await K.depositReward(R.target, 1n * E18)).wait();
  await show("a4 depositReward(R,1e18)");
  await at(t0 + 40 + 365 * DAY); await (await K.connect(alice).claim()).wait();
  await show("a5 alice.claim() after 365 days");
  console.log(await expectRevert(K.unregisterRewardToken(R.target), "a6 unregisterRewardToken(R)"));
}
main().catch((e) => { console.error(e); process.exit(1); });
