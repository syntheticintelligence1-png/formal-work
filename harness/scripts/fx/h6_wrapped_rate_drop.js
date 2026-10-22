// H6: WrappedTokenTreasuryV2 (L5719-L5821) + MarketV2. totalBaseToken is kept in underlying units (L9562, L9617) and is
// never re-marked when the wrapped->underlying rate falls (Rv: slashing). _transferBaseToken (L9860-L9879) then needs
// more wrapped tokens than custody holds; with no strategy the call to address(0) reverts. Order of exit decides who
// bears the shortfall: junior xToken holders exiting first leave senior fToken holders unable to redeem.
const { ethers, E18, tx, view, deploy } = require("./lib");

async function main() {
  const [admin, fHolder, xHolder, platform, reserve] = await ethers.getSigners();
  const base = await deploy("FxMockToken", "wstETH", "W", 18);
  const f = await deploy("FxMockToken", "f", "F", 18);
  const x = await deploy("FxMockToken", "x", "X", 18);
  const oracle = await deploy("FxMockOracleV2");
  const rate = await deploy("FxMockRateProvider");
  const registry = await deploy("FxMockRegistry");
  const splitter = await deploy("FxMockSplitter");
  await (await rate.set(11n * 10n ** 17n)).wait();                     // 1 wrapped = 1.1 underlying
  const T = await deploy("WrappedTokenTreasuryV2", await base.getAddress(), await f.getAddress(), await x.getAddress());
  await (await T.initialize(platform.address, await splitter.getAddress(), await rate.getAddress(), await oracle.getAddress(), 10n ** 30n, 3600)).wait();
  await (await T.grantRole(await T.PROTOCOL_INITIALIZER_ROLE(), admin.address)).wait();
  await (await base.mint(await T.getAddress(), 1000n * E18)).wait();
  await (await T.initializeProtocol(1100n * E18)).wait();              // underlying value of 1000 wrapped
  const M = await deploy("MarketV2", await T.getAddress());
  await (await M.initialize(platform.address, reserve.address, await registry.getAddress())).wait();
  await (await M.updateStabilityRatio(13n * 10n ** 17n)).wait();
  await (await T.grantRole(await T.FX_MARKET_ROLE(), await M.getAddress())).wait();
  await (await f.transfer(fHolder.address, await f.balanceOf(admin.address))).wait();
  await (await x.transfer(xHolder.address, await x.balanceOf(admin.address))).wait();
  console.log("init: totalBaseToken(underlying) =", ethers.formatEther(await T.totalBaseToken()),
    " custody(wrapped) =", ethers.formatEther(await base.balanceOf(await T.getAddress())),
    " f =", ethers.formatEther(await f.totalSupply()), " x =", ethers.formatEther(await x.totalSupply()));

  await (await rate.set(105n * 10n ** 16n)).wait();                    // Rv: rate falls 1.10 -> 1.05 (-4.5%)
  console.log("rate 1.10 -> 1.05: ledger still", ethers.formatEther(await T.totalBaseToken()),
    "underlying; custody worth", ethers.formatEther((await base.balanceOf(await T.getAddress())) * 105n / 100n), "underlying");
  await view("collateralRatio()", T.collateralRatio(), ethers.formatEther);
  await view("isUnderCollateral()", T.isUnderCollateral());

  await tx("xHolder.redeemXToken(all) [junior exits first]", M.connect(xHolder).redeemXToken(ethers.MaxUint256, xHolder.address, 0));
  console.log("  xHolder received wrapped:", ethers.formatEther(await base.balanceOf(xHolder.address)));
  await tx("fHolder.redeemFToken(all) [senior]", M.connect(fHolder).redeemFToken(ethers.MaxUint256, fHolder.address, 0));
  await tx("fHolder.redeemFToken(500000e18)", M.connect(fHolder).redeemFToken(500000n * E18, fHolder.address, 0));
  console.log("  fHolder received wrapped:", ethers.formatEther(await base.balanceOf(fHolder.address)),
    "; fToken left:", ethers.formatEther(await f.balanceOf(fHolder.address)),
    "; custody left:", ethers.formatEther(await base.balanceOf(await T.getAddress())));
  await tx("fHolder.redeemFToken(remaining)", M.connect(fHolder).redeemFToken(ethers.MaxUint256, fHolder.address, 0));
}

main().catch((e) => {
  console.error(e);
  process.exit(1);
});
