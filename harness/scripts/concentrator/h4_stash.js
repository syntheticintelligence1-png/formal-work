// H4: ConcentratorCompounderStash (L2309-L2475) + ConcentratorStashBase (L133-L188), bundle bytecode.
const { ethers, E18, deploy, snapshot, revertTo, tryTx } = require("./lib");

async function main() {
  const [owner, harvester, keeper, treasury] = await ethers.getSigners();
  const asset = await deploy("MockERC20");
  const sdt = await deploy("MockERC20");
  const weth = await deploy("MockERC20");
  const conv = await deploy("MockConverter");
  const C = await conv.getAddress();
  await (await conv.setRoute(1, await sdt.getAddress(), await weth.getAddress(), 5n * 10n ** 14n)).wait(); // 1 SDT = 0.0005 WETH
  await (await conv.setRoute(2, await weth.getAddress(), await asset.getAddress(), 2000n * E18)).wait(); // 1 WETH = 2000 asset
  const comp = await deploy("MockCompounder", [await asset.getAddress(), harvester.address, C, treasury.address]);
  const stash = await deploy("ConcentratorCompounderStash", [await comp.getAddress()]);
  const S = await stash.getAddress();
  await (await sdt.mint(S, 100n * E18)).wait();
  let snap = await snapshot();

  console.log("== H4: processBatch([SDT], [[SDT->WETH]], WETH, [WETH->asset], keeper, minAsset) ==");
  const before = await sdt.balanceOf(C);
  await (await stash.connect(harvester).processBatch([await sdt.getAddress()], [[1n]], await weth.getAddress(), [2n], keeper.address, 0)).wait();
  console.log(`    minAsset=0 -> OK; compounder received ${await comp.totalRewards()} asset; SDT now held by converter: ${(await sdt.balanceOf(C)) - before}; SDT left in stash: ${await sdt.balanceOf(S)}`);
  await revertTo(snap);
  snap = await snapshot();
  const SDTa = await sdt.getAddress();
  const WETHa = await weth.getAddress();
  await tryTx("minAsset=1", () => stash.connect(harvester).processBatch([SDTa], [[1n]], WETHa, [2n], keeper.address, 1));
  await revertTo(snap);
  snap = await snapshot();
  await (await stash.connect(harvester).process(await sdt.getAddress(), [1n, 2n], keeper.address, 0)).wait();
  console.log(`    control process(SDT, [SDT->WETH, WETH->asset]) -> compounder received ${await comp.totalRewards()} asset`);
  await revertTo(snap);
  await tryTx("processBatch called by a non-harvester", () => stash.connect(keeper).processBatch([], [], WETHa, [], keeper.address, 0));
}

main().catch((e) => {
  console.error(e);
  process.exit(1);
});
