// K3: (i) conservation with obligations discharged; (ii) relaxation of O3a (share change without checkpoint).
const { ethers, E18, DAY, at, mineAt, now, expectRevert } = require("../lib");
async function run(violate, globalFirst) {
  const [admin, alice, bob] = await ethers.getSigners();
  const P = 7 * DAY;
  const R = await ethers.deployContract("MockToken", ["R"]);
  const K = await ethers.deployContract("KernelMRA", [P]);
  await (await K.initialize()).wait();
  await (await K.registerRewardToken(R.target, admin.address)).wait();
  await (await R.mint(admin.address, 1000n * E18)).wait();
  await (await R.approve(K.target, ethers.MaxUint256)).wait();
  const t0 = (await now()) + 100;
  const line = async (tag) => console.log(`${tag.padEnd(44)} | S=${await K.totalShare()} I=${(await K.rewardSnapshot(R.target)).integral} bal=${await R.balanceOf(K.target)} c(A)=${await K.claimable(alice.address, R.target)} c(B)=${await K.claimable(bob.address, R.target)}`);
  await at(t0); await (await K.connect(alice).stake(10n * E18)).wait(); await line("a1 A.stake(10e18)");
  await at(t0 + 1); await (await K.depositReward(R.target, 700n * E18)).wait(); await line("a2 depositReward(700e18), P=7d");
  await at(t0 + 1 + P / 2);
  if (violate) {
    if (globalFirst) { await (await K.checkpoint(admin.address)).wait(); await line("a3g checkpoint(admin) [global integral advanced]"); }
    await (await K.connect(bob).stakeWithoutCheckpoint(10n * E18)).wait(); await line(globalFirst ? "a3' B.stakeWithoutCheckpoint [O3a broken only]" : "a3' B.stakeWithoutCheckpoint [O3a+O3b broken]"); }
  else { await (await K.connect(bob).stake(10n * E18)).wait(); await line("a3 B.stake(10e18)"); }
  await at(t0 + 2 + P); await (await K.checkpoint(alice.address)).wait(); await line("a4 checkpoint(A) after period end");
  const cA = await K.claimable(alice.address, R.target), cB = await K.claimable(bob.address, R.target);
  console.log(`   sum claimable = ${cA + cB}  vs deposited 700e18 -> surplus(deposit - sum) = ${700n * E18 - (cA + cB)}`);
  await at(t0 + 3 + P); console.log("  ", await expectRevert(K.connect(bob)["claim()"](), "a5 B.claim()"));
  await at(t0 + 4 + P); console.log("  ", await expectRevert(K.connect(alice)["claim()"](), "a6 A.claim()"));
  await line("a7 final");
}
async function main() {
  console.log("== obligations discharged =="); await run(false, false);
  console.log("== O3a and O3b relaxed (no global, no user checkpoint) =="); await run(true, false);
  console.log("== O3a relaxed only (global checkpoint done, user snapshot stale) =="); await run(true, true);
}
main().catch((e) => { console.error(e); process.exit(1); });
