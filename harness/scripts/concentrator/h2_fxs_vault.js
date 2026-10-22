// H2: AladdinFXSConvexVault (L17736-L17877) on ConcentratorConvexVault (L10833-L11574), bundle bytecode.
const { hre, ethers, E18, DAY, T0, installAt, deploy, setTime, snapshot, revertTo, tryTx } = require("./lib");

const FXS = "0x3432B6A60D23Ca0dFCa7761B7ab56459D9C964D0"; // == cvxFXS constant (L17756, L17760)
const BOOSTER = "0xF403C135812408BFbE8713b5A23a04b3D48AAE31";
const ZERO = ethers.ZeroAddress;

async function main() {
  const [owner, alice, bob, carol, mallory, keeper, platform, aliceRx] = await ethers.getSigners();
  const fxs = await installAt(FXS, "MockERC20");
  const booster = await installAt(BOOSTER, "MockBooster");
  const crv = await deploy("MockERC20");
  const cvxfxs = await deploy("MockERC20"); // the REAL cvxFXS token (distinct address)
  const usdc = await deploy("MockERC20");
  const lps = [await deploy("MockERC20"), await deploy("MockERC20"), await deploy("MockERC20")];
  const rps = [];
  for (let i = 0; i < 3; i++) {
    rps.push(await deploy("MockRewardPool", [await lps[i].getAddress(), await crv.getAddress(), FXS]));
    await (await booster.setPool(i + 1, await lps[i].getAddress(), await rps[i].getAddress())).wait();
  }
  const zap = await deploy("MockZap");
  await (await zap.setPrice(await crv.getAddress(), FXS, E18)).wait();
  await (await zap.setPrice(FXS, ZERO, 10n ** 15n)).wait();
  await (await zap.setPrice(FXS, await usdc.getAddress(), 3n * 10n ** 6n)).wait();
  await (await zap.setPrice(FXS, await cvxfxs.getAddress(), 13n * 10n ** 17n)).wait();
  await hre.network.provider.send("hardhat_setBalance", [await zap.getAddress(), "0x3635C9ADC5DEA00000"]); // 1000 ETH
  const afxs = await deploy("MockAFXS", [FXS, await cvxfxs.getAddress()]);
  const v = await deploy("FXSVaultHarness");
  const V = await v.getAddress();
  await (await v.initialize(await afxs.getAddress(), await zap.getAddress(), platform.address)).wait();
  await (await v.addPool(1, [await crv.getAddress()], 0, 0, 0)).wait();
  await (await v.addPool(2, [await crv.getAddress()], 0, 0, 0)).wait();
  await (await v.addPool(3, [FXS], 0, 0, 0)).wait();
  const users = [alice, bob, carol];
  for (let i = 0; i < 3; i++) {
    await (await lps[i].mint(users[i].address, 100n * E18)).wait();
    await (await lps[i].connect(users[i]).approve(V, ethers.MaxUint256)).wait();
    await (await v.connect(users[i]).deposit(i, users[i].address, 100n * E18)).wait();
  }
  console.log(`  FXS allowance vault->aFXS after initialize (approve of the 'cvxFXS' constant): ${await fxs.allowance(V, await afxs.getAddress())}`);

  console.log("== H2.cross-pool: harvest(pid) converts whole-vault balances (L11209-L11213) ==");
  await (await rps[0].accrue(V, 60n * E18, 0)).wait();
  await (await rps[1].accrue(V, 60n * E18, 0)).wait();
  const s0 = await snapshot();
  for (const push of [false, true]) {
    if (push) await (await rps[1].connect(mallory)["getReward(address,bool)"](V, true)).wait();
    await (await v.connect(keeper).harvest(0, keeper.address, 0)).wait();
    await (await v.connect(keeper).harvest(1, keeper.address, 0)).wait();
    console.log(`    R1 push of pool-1 rewards=${push}: pendingReward(0,alice)=${await v.pendingReward(0, alice.address)} pendingReward(1,bob)=${await v.pendingReward(1, bob.address)}`);
    if (!push) await revertTo(s0);
  }

  console.log("== H2.alias: _claim with claimAsToken != aFXS uses FXS where cvxFXS is meant (L17816-L17830) ==");
  console.log(`    vault: aFXS=${await afxs.balanceOf(V)} FXS=${await fxs.balanceOf(V)} cvxFXS=${await cvxfxs.balanceOf(V)}`);
  for (const [name, tok] of [["FXS", FXS], ["cvxFXS(real)", await cvxfxs.getAddress()], ["USDC", await usdc.getAddress()], ["ETH", ZERO]]) {
    await tryTx(`alice claim(0, aliceRx, 0, ${name}) with no FXS in vault`, () => v.connect(alice).claim(0, aliceRx.address, 0, tok));
  }
  await (await rps[2].accrue(V, 0, 150n * E18)).wait();
  await (await rps[2].connect(mallory)["getReward(address,bool)"](V, true)).wait();
  console.log(`    after R1 getReward(vault) on pool-2's reward pool: vault FXS=${await fxs.balanceOf(V)}`);
  const s1 = await snapshot();
  await (await v.connect(alice).claim(0, aliceRx.address, 0, FXS)).wait();
  console.log(`    alice claim as FXS: aliceRx FXS=${await fxs.balanceOf(aliceRx.address)}; vault FXS=${await fxs.balanceOf(V)} cvxFXS(stranded)=${await cvxfxs.balanceOf(V)} aFXS=${await afxs.balanceOf(V)}`);
  await (await v.connect(keeper).harvest(2, keeper.address, 0)).wait();
  console.log(`    harvest(2) afterwards: pendingReward(2,carol)=${await v.pendingReward(2, carol.address)} (125e18 without the alias)`);
  await revertTo(s1);
  await tryTx("alice claim as ETH, vault holds FXS but no ETH", () => v.connect(alice).claim(0, aliceRx.address, 0, ZERO));
  await hre.network.provider.send("hardhat_setBalance", [V, "0xAD78EBC5AC6200000"]); // 200 ETH
  const a0 = await ethers.provider.getBalance(alice.address);
  const r0 = await ethers.provider.getBalance(aliceRx.address);
  const ret = await v.connect(alice).claim.staticCall(0, aliceRx.address, 0, ZERO, { gasPrice: 0 });
  await (await v.connect(alice).claim(0, aliceRx.address, 0, ZERO, { gasPrice: 0 })).wait();
  console.log(`    alice claim as ETH with 200 ETH in vault: returns ${ret}; msg.sender(alice) +${(await ethers.provider.getBalance(alice.address)) - a0} wei; recipient(aliceRx) +${(await ethers.provider.getBalance(aliceRx.address)) - r0} wei; vault ETH left ${await ethers.provider.getBalance(V)}`);

  console.log("== H2.dead-branch: _zapAsRewardToken with FXS == cvxFXS ==");
  await (await fxs.mint(V, 10n * E18)).wait();
  const fx0 = await fxs.balanceOf(V);
  const cv0 = await cvxfxs.balanceOf(V);
  const out = await v.zapAsRewardTokenX.staticCall([FXS], [10n * E18]);
  await (await v.zapAsRewardTokenX([FXS], [10n * E18])).wait();
  console.log(`    tokens=[cvxFXS constant] amounts=[10e18]: aFXS minted=${out}; FXS pulled=${fx0 - (await fxs.balanceOf(V))}; real cvxFXS pulled=${cv0 - (await cvxfxs.balanceOf(V))} (aFXS.deposit path never used)`);
  console.log("== H2.duplicate-entry: pool reward list [FXS, cvxFXS-constant] (owner config) read through harvest() ==");
  const s2 = await snapshot();
  await (await v.updatePoolRewardTokens(2, [FXS, FXS])).wait();
  await (await rps[2].accrue(V, 0, 50n * E18)).wait();
  console.log(`    vault FXS before harvest(2) = ${await fxs.balanceOf(V)} (+50e18 to be claimed by getReward)`);
  await tryTx("harvest(2) with convexRewardTokens=[FXS, FXS]", () => v.connect(keeper).harvest(2, keeper.address, 0));
  await revertTo(s2);
  await (await rps[2].accrue(V, 0, 50n * E18)).wait();
  await tryTx("harvest(2) with convexRewardTokens=[FXS] (control)", () => v.connect(keeper).harvest(2, keeper.address, 0));
}

main().catch((e) => {
  console.error(e);
  process.exit(1);
});
