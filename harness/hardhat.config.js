require("@nomicfoundation/hardhat-ethers");

// Sources: the bundle extracted verbatim under contracts/bundle, plus harness contracts under contracts/harness.
module.exports = {
  solidity: {
    compilers: [
      { version: "0.7.6", settings: { optimizer: { enabled: true, runs: 200 } } },
      { version: "0.8.20", settings: { optimizer: { enabled: true, runs: 200 } } },
    ],
  },
  networks: { hardhat: { allowUnlimitedContractSize: true, initialBaseFeePerGas: 0 } },
  paths: { sources: "./contracts", tests: "./test", cache: "./cache", artifacts: "./artifacts" },
};
