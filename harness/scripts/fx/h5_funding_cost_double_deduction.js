// H5: TreasuryWithFundingCost + MarketWithFundingCost. While the oracle reports isValid=false, harvest() returns
// early (L17415) without capturing the borrow-rate snapshot, but every mint/redeem loads the state with the funding
// cost deducted (L17477-L17481) and persists it into totalBaseToken (TreasuryV2 L9562 / L9581 / L9617).
const { ethers, E18, DAY, advance, tx, view, deploy } = require("./lib");
const hre = require("hardhat");

async function main() {
  const [admin, user, platform, reserve] = await ethers.getSigners();
  const base = await deploy("FxMockToken", "base", "BASE", 18);
  const f = await deploy("FxMockToken", "f", "F", 18);
  const x = await deploy("FxMockToken", "x", "X", 18);
  const oracle = await deploy("FxMockOracleV2");
  const amm = await deploy("FxMockCrvUSDAmm");
  const registry = await deploy("FxMockRegistry");
  const splitter = await deploy("FxMockSplitter");
  const T = await deploy("TreasuryWithFundingCost", await base.getAddress(), await f.getAddress(), await x.getAddress());
  await (await T.initialize(platform.address, await splitter.getAddress(), await oracle.getAddress(), 10n ** 30n, 3600, await amm.getAddress())).wait();
  await (await T.grantRole(await T.PROTOCOL_INITIALIZER_ROLE(), admin.address)).wait();
  await (await base.mint(await T.getAddress(), 1000n * E18)).wait();
  await (await T.initializeProtocol(1000n * E18)).wait();
  const M = await deploy("MarketWithFundingCost", await T.getAddress());
  await (await M.initialize(platform.address, reserve.address, await registry.getAddress())).wait();
  await (await M.updateStabilityRatio(13n * 10n ** 17n)).wait();
  await (await T.grantRole(await T.FX_MARKET_ROLE(), await M.getAddress())).wait();
  await (await base.mint(user.address, 100n * E18)).wait();
  await (await base.connect(user).approve(await M.getAddress(), ethers.MaxUint256)).wait();

  const show = async (label) => {
    const tb = await T.totalBaseToken();
    const bal = await base.balanceOf(await T.getAddress());
    const pf = await base.balanceOf(platform.address);
    console.log(`  ${label}: totalBaseToken=${ethers.formatEther(tb)} custody=${ethers.formatEther(bal)} ` +
      `custody-ledger=${ethers.formatEther(bal - tb)} distributed(platform)=${ethers.formatEther(pf)}`);
  };
  console.log("init: fSupply =", ethers.formatEther(await f.totalSupply()), " xSupply =", ethers.formatEther(await x.totalSupply()),
    " CR =", ethers.formatEther(await T.collateralRatio()));
  await (await amm.set(101n * 10n ** 16n)).wait();       // crvUSD rate_mul +1%
  await advance(DAY);
  await view("harvestable() [funding cost pending]", T.harvestable(), ethers.formatEther);
  const snap = await hre.network.provider.send("evm_snapshot", []);

  console.log("\n== control: price valid ==");
  await tx("user.mintFToken(1e9)", M.connect(user).mintFToken(10n ** 9n, user.address, 0));
  await show("after");

  await hre.network.provider.send("evm_revert", [snap]);
  console.log("\n== oracle isValid=false: 5 tiny mints, then price valid again ==");
  await (await oracle.set(false, 2000n * E18)).wait();
  for (let i = 1; i <= 5; i++) {
    await tx(`user.mintFToken(1e9) #${i}`, M.connect(user).mintFToken(10n ** 9n, user.address, 0));
    await show(`after #${i}`);
  }
  await (await oracle.set(true, 2000n * E18)).wait();
  await tx("user.mintFToken(1e9) (valid -> hook harvests)", M.connect(user).mintFToken(10n ** 9n, user.address, 0));
  await show("final");
  await view("harvestable() afterwards", T.harvestable(), ethers.formatEther);
}

main().catch((e) => {
  console.error(e);
  process.exit(1);
});
