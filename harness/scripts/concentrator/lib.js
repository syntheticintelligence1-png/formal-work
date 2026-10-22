const hre = require("hardhat");
const { ethers } = hre;

const E18 = 10n ** 18n;
const DAY = 86400n;
const T0 = 1_900_000_000n;

async function installAt(addr, name) {
  const art = await hre.artifacts.readArtifact(name);
  await hre.network.provider.send("hardhat_setCode", [addr, art.deployedBytecode]);
  return ethers.getContractAt(name, addr);
}

async function deploy(name, args = []) {
  const f = await ethers.getContractFactory(name);
  const c = await f.deploy(...args);
  await c.waitForDeployment();
  return c;
}

async function setTime(t) {
  await hre.network.provider.send("evm_setNextBlockTimestamp", [Number(t)]);
}

async function snapshot() {
  return hre.network.provider.send("evm_snapshot", []);
}

async function revertTo(id) {
  await hre.network.provider.send("evm_revert", [id]);
}

function reason(e) {
  const m = e.shortMessage || e.message || String(e);
  return m.replace(/\s+/g, " ").slice(0, 160);
}

async function tryTx(label, fn) {
  try {
    const tx = await fn();
    if (tx && tx.wait) await tx.wait();
    console.log(`    ${label} -> OK`);
    return true;
  } catch (e) {
    console.log(`    ${label} -> REVERT (${reason(e)})`);
    return false;
  }
}

module.exports = { hre, ethers, E18, DAY, T0, installAt, deploy, setTime, snapshot, revertTo, reason, tryTx };
