const hre = require("hardhat");
const { ethers } = hre;
const E18 = 10n ** 18n;
const DAY = 86400;
async function at(t) { await hre.network.provider.send("evm_setNextBlockTimestamp", [t]); }
async function mineAt(t) { await at(t); await hre.network.provider.send("evm_mine"); }
async function now() { return (await ethers.provider.getBlock("latest")).timestamp; }
async function expectRevert(p, label) {
  try { const tx = await p; await tx.wait(); return `${label}: NO REVERT`; }
  catch (e) { const m = (e.shortMessage || e.message || "").split("\n")[0]; return `${label}: REVERT (${m})`; }
}
module.exports = { hre, ethers, E18, DAY, at, mineAt, now, expectRevert };
