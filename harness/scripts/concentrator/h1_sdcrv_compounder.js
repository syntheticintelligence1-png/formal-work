// H1: SdCrvCompounder (bundle bytecode, L1182-L1587 + AladdinCompounder L2748-L3144) against a wrapper mock.
const { ethers, E18, DAY, T0, installAt, deploy, setTime, snapshot, revertTo, tryTx } = require("./lib");

const CRV = "0xD533a949740bb3306d119CC777fa900bA034cd52";
const SDCRV_GAUGE = "0x7f50786A0b15723D741727882ee99a0BF34e3466";
const SD_VE_CRV = "0x478bBC744811eE8310B461514BDc29D03739084D";
const SDCRV = "0xD1b5651E55D4CeeD36251c61c50C889B36F6abB5";
const MAX = ethers.MaxUint256;

async function fresh(signers) {
  const [owner, , , , , stash] = signers;
  const wrapper = await deploy("MockSdWrapper", [SDCRV]);
  const c = await deploy("SdCrvCompounderHarness", [await wrapper.getAddress(), await wrapper.getAddress()]);
  await (await c.init()).wait();
  await (await c.initializeV2(stash.address)).wait();
  return { c, wrapper };
}

async function fund(sd, c, who, amt) {
  await (await sd.mint(who.address, amt)).wait();
  await (await sd.connect(who).approve(await c.getAddress(), MAX)).wait();
}

async function main() {
  const signers = await ethers.getSigners();
  const [owner, alice, bob, mallory, victim, stash, platform] = signers;
  for (const a of [CRV, SDCRV_GAUGE, SD_VE_CRV, SDCRV]) await installAt(a, "MockERC20");
  const sd = await ethers.getContractAt("MockERC20", SDCRV);

  console.log("== H1.S2: withdraw fee 5%, SdCrvCompounder._withdraw takes no fee ==");
  {
    await setTime(T0);
    const { c } = await fresh(signers);
    await (await c.updateFeeInfo(platform.address, 0, 0, 50_000_000)).wait();
    for (const u of [alice, bob]) {
      await fund(sd, c, u, 100n * E18);
      await (await c.connect(u).deposit(100n * E18, u.address)).wait();
    }
    await fund(sd, c, stash, 10n * E18);
    await (await c.connect(stash).depositReward(10n * E18)).wait(); // periodLength == 0 -> immediate
    console.log(`    TS=${await c.totalSupply()} TAS=${await c.totalAssetsStoredX()} totalAssets()=${await c.totalAssets()}`);
    const pr = await c.previewRedeem(10n * E18);
    const b0 = await sd.balanceOf(signers[7].address);
    await (await c.connect(alice).redeem(10n * E18, signers[7].address, alice.address)).wait();
    const got = (await sd.balanceOf(signers[7].address)) - b0;
    console.log(`    previewRedeem(10e18)=${pr} redeem(10e18) delivered=${got} (delivered-preview=${got - pr})`);
    const pw = await c.previewWithdraw(10n * E18);
    const b1 = await sd.balanceOf(signers[8].address);
    const sh0 = await c.balanceOf(bob.address);
    await (await c.connect(bob).withdraw(10n * E18, signers[8].address, bob.address)).wait();
    const got2 = (await sd.balanceOf(signers[8].address)) - b1;
    console.log(`    previewWithdraw(10e18)=${pw} withdraw(10e18): burned=${sh0 - (await c.balanceOf(bob.address))} delivered=${got2} (requested 10e18)`);
    await tryTx("withdraw(type(uint256).max) by alice", () => c.connect(alice).withdraw(MAX, alice.address, alice.address));
    await tryTx("redeem(type(uint256).max) by alice", () => c.connect(alice).redeem(MAX, alice.address, alice.address));
  }

  console.log("== H1.mint: TS=2, TAS=3, mint(1) ==");
  {
    const { c } = await fresh(signers);
    await fund(sd, c, alice, 2n);
    await (await c.connect(alice).deposit(2n, alice.address)).wait();
    await fund(sd, c, stash, 1n);
    await (await c.connect(stash).depositReward(1n)).wait();
    await fund(sd, c, bob, 10n);
    const pm = await c.previewMint(1n);
    const s0 = await sd.balanceOf(bob.address);
    await (await c.connect(bob).mint(1n, bob.address)).wait();
    console.log(`    previewMint(1)=${pm}; mint(1): assets pulled=${s0 - (await sd.balanceOf(bob.address))}, shares received=${await c.balanceOf(bob.address)}`);
  }

  console.log("== H1.S3: periodLength 7d, vault emptied while streaming; first depositor captures; victim gets 0 shares ==");
  {
    const t = T0 + 100n * DAY;
    await setTime(t);
    const { c } = await fresh(signers);
    await (await c.updateRewardPeriodLength(7n * DAY)).wait();
    await fund(sd, c, alice, 1000n * E18);
    await fund(sd, c, stash, 700n * E18);
    await fund(sd, c, mallory, 1n);
    await fund(sd, c, victim, 150n * E18);
    await setTime(t + 100n);
    await (await c.connect(alice).deposit(1000n * E18, alice.address)).wait();
    await setTime(t + 110n);
    await (await c.connect(stash).depositReward(700n * E18)).wait();
    const ri = await c.rewardInfo();
    console.log(`    rewardInfo rate=${ri.rate} periodLength=${ri.periodLength}`);
    await setTime(t + 110n + DAY);
    const a0 = await sd.balanceOf(alice.address);
    await (await c.connect(alice).redeem(MAX, alice.address, alice.address)).wait();
    console.log(`    +1d alice redeems all -> ${(await sd.balanceOf(alice.address)) - a0}; TS=${await c.totalSupply()} TAS=${await c.totalAssetsStoredX()}`);
    await setTime(t + 110n + 3n * DAY);
    await (await c.connect(mallory).deposit(1n, mallory.address)).wait();
    console.log(`    +3d mallory deposit(1) -> shares ${await c.balanceOf(mallory.address)}; totalAssets()=${await c.totalAssets()}`);
    console.log(`    victim previewDeposit(150e18)=${await c.previewDeposit(150n * E18)}`);
    await setTime(t + 111n + 3n * DAY);
    await (await c.connect(victim).deposit(150n * E18, victim.address)).wait();
    console.log(`    +3d+1s victim deposit(150e18) -> shares ${await c.balanceOf(victim.address)}; TAS=${await c.totalAssetsStoredX()}`);
    const m0 = await sd.balanceOf(mallory.address);
    await setTime(t + 112n + 3n * DAY);
    await (await c.connect(mallory).redeem(MAX, mallory.address, mallory.address)).wait();
    console.log(`    mallory redeems 1 share -> ${(await sd.balanceOf(mallory.address)) - m0}`);
    await tryTx("victim redeem(MAX)", () => c.connect(victim).redeem(MAX, victim.address, victim.address));
  }

  console.log("== H1.P0: periodLength 0, empty vault receives reward -> TAS>0, TS=0 -> deposits mint 0 shares ==");
  {
    const { c } = await fresh(signers);
    await fund(sd, c, stash, 10n * E18);
    await (await c.connect(stash).depositReward(10n * E18)).wait();
    console.log(`    TS=${await c.totalSupply()} TAS=${await c.totalAssetsStoredX()}`);
    await fund(sd, c, alice, 100n * E18);
    await (await c.connect(alice).deposit(100n * E18, alice.address)).wait();
    console.log(`    alice deposit(100e18) -> shares ${await c.balanceOf(alice.address)}; TS=${await c.totalSupply()} TAS=${await c.totalAssetsStoredX()}`);
    await tryTx("alice redeem(MAX)", () => c.connect(alice).redeem(MAX, alice.address, alice.address));
    const { c: h } = await fresh(signers);
    await (await h.updateFeeInfo(platform.address, 100_000_000, 0, 0)).wait();
    await tryTx("harvest() on an empty vault with platform fee 10%", () => h.harvest(owner.address, 0));
  }

  console.log("== H1.S4: periodLength 7d -> 0 at +1d (owner), back to 7d at +10d ==");
  for (const settle of [false, true]) {
    const t = T0 + (settle ? 300n : 200n) * DAY;
    await setTime(t);
    const { c } = await fresh(signers);
    await (await c.updateRewardPeriodLength(7n * DAY)).wait();
    for (const u of [alice, bob]) await fund(sd, c, u, 1000n * E18);
    await fund(sd, c, stash, 700n * E18);
    await setTime(t + 100n);
    await (await c.connect(alice).deposit(1000n * E18, alice.address)).wait();
    await setTime(t + 101n);
    await (await c.connect(bob).deposit(1000n * E18, bob.address)).wait();
    await setTime(t + 110n);
    await (await c.connect(stash).depositReward(700n * E18)).wait();
    await setTime(t + 110n + DAY);
    if (settle) await (await c.checkpoint()).wait();
    else await (await sd.mint(owner.address, 0n)).wait();
    await (await c.updateRewardPeriodLength(0)).wait();
    await setTime(t + 110n + 2n * DAY);
    await (await sd.mint(owner.address, 0n)).wait();
    const pr = await c.previewRedeem(await c.balanceOf(bob.address));
    const b0 = await sd.balanceOf(bob.address);
    await (await c.connect(bob).redeem(MAX, bob.address, bob.address)).wait();
    const gb = (await sd.balanceOf(bob.address)) - b0;
    await setTime(t + 110n + 10n * DAY);
    await (await c.updateRewardPeriodLength(7n * DAY)).wait();
    await (await c.checkpoint()).wait();
    const a0 = await sd.balanceOf(alice.address);
    await (await c.connect(alice).redeem(MAX, alice.address, alice.address)).wait();
    const ga = (await sd.balanceOf(alice.address)) - a0;
    console.log(`    settle*=${settle}: bob previewRedeem(at block before redeem)=${pr} redeem=${gb} (preview-actual=${pr - gb}); alice at +10d redeem=${ga}`);
  }
}

main().catch((e) => {
  console.error(e);
  process.exit(1);
});
