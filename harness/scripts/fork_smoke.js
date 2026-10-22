const hre = require("hardhat");
const { ethers } = hre;
async function main() {
  const bn = await ethers.provider.getBlockNumber();
  console.log("fork block:", bn);
  const erc20 = ["function symbol() view returns (string)", "function name() view returns (string)", "function decimals() view returns (uint8)"];
  for (const [label, addr] of [
    ["CVX", "0x4e3FBD56CD56c3e72c1403e103b45Db9da5B9D2B"],
    ["cvxRewardPool", "0xCF50b810E57Ac33B91dCF525C6ddd9881B139332"],
    ["CvxLockerV2", "0x72a19342e8F1838460eBFCCEf09F6585e32db86E"],
    ["FXS(0x3432)", "0x3432B6A60D23Ca0dFCa7761B7ab56459D9C964D0"],
    ["cvxFXS(real 0xFEEf)", "0xFEEf77d3f69374f66429C91d732A244f074bdf74"],
  ]) {
    const code = await ethers.provider.getCode(addr);
    let sym = "-";
    try { sym = await new ethers.Contract(addr, erc20, ethers.provider).symbol(); } catch (e) { sym = "(no symbol)"; }
    console.log(`${label.padEnd(22)} ${addr} codeLen=${(code.length - 2) / 2} symbol=${sym}`);
  }
}
main().catch((e) => { console.error(e.message || e); process.exit(1); });
