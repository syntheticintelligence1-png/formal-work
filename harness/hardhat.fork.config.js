require("@nomicfoundation/hardhat-ethers");
// Fork config: same compilers as hardhat.config.js, plus a mainnet fork for verifying external-venue premises.
const FORK_BLOCK = Number(process.env.FORK_BLOCK || 26243800);
const FORK_URL = process.env.FORK_URL || "https://ethereum-rpc.publicnode.com";
module.exports = {
  solidity: {
    compilers: [
      { version: "0.7.6", settings: { optimizer: { enabled: true, runs: 200 } } },
      { version: "0.8.20", settings: { optimizer: { enabled: true, runs: 200 } } },
    ],
  },
  networks: {
    hardhat: {
      allowUnlimitedContractSize: true,
      forking: { url: FORK_URL, blockNumber: FORK_BLOCK },
      chains: { 1: { hardforkHistory: { london: 12965000, shanghai: 17034870, cancun: 19426587 } } },
    },
  },
  paths: { sources: "./contracts", tests: "./test", cache: "./cache-fork", artifacts: "./artifacts" },
};
