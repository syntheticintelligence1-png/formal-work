// H2: ShareableRebalancePool - after a pool-emptying liquidation (epoch reset), a vote-sharing staker whose
// co-staker checkpointed first can never checkpoint again: _getVoteOwnerHistoryBalances (L15663-L15673) returns
// the stored owner aggregate 0, _computeBoostRatio divides by it (L15691) -> Panic(0x12) in _getBoostRatio
// (L15594-L15626) called from _updateSnapshot(fxn) (L15296-L15299).
// Part 2 replays the owner-aggregate rounding trace found by models/owner_aggregate.py (L15364 underflow).
const { ethers, E18, DAY, WEEK, now, setTime, advance, tx, view, prod, setupPool } = require("./lib");

async function main() {
  const fx = await setupPool("Shareable");
  const { admin, A, C, O, liq, dist, base, fxn, ve, pool } = fx;
  console.log("== Part 1: division by zero after an epoch reset ==");
  await (await pool.grantRole(await pool.VE_SHARING_ROLE(), O.address)).wait();
  await (await ve.set(O.address, 50n * E18)).wait();
  await (await ve.set(admin.address, 50n * E18)).wait();
  await tx("O.toggleVoteSharing(A)", pool.connect(O).toggleVoteSharing(A.address));
  await tx("O.toggleVoteSharing(C)", pool.connect(O).toggleVoteSharing(C.address));
  await tx("A.deposit(100e18)", pool.connect(A).deposit(100n * E18, A.address));
  await tx("C.deposit(100e18)", pool.connect(C).deposit(100n * E18, C.address));
  await tx("A.acceptSharedVote(O)", pool.connect(A).acceptSharedVote(O.address));
  await tx("C.acceptSharedVote(O)", pool.connect(C).acceptSharedVote(O.address));
  await tx("dist.depositReward(FXN, 7000e18)", pool.connect(dist).depositReward(await fxn.getAddress(), 7000n * E18));
  const t = await now();
  await setTime((Math.floor(t / WEEK) + 1) * WEEK + 3 * DAY);        // cross a week boundary
  await tx("liquidate(max) - consumes the whole pool", pool.connect(liq).liquidate(ethers.MaxUint256, 0));
  const st = await pool.totalSupplyHistory((await pool.numTotalSupplyHistory()) - 1n);
  console.log("  product after liquidation:", prod(st.product), "totalSupply =", (await pool.totalSupply()).toString());
  await view("claimable(A, base) [liquidation proceeds]", pool.claimable(A.address, await base.getAddress()), ethers.formatEther);
  await advance(3600);
  await tx("C.claim()", pool.connect(C)["claim()"]());
  console.log("  voteOwnerBalances(O).amount =", (await pool.voteOwnerBalances(O.address)).amount.toString());
  const b0 = await base.balanceOf(A.address);
  await tx("A.claim()", pool.connect(A)["claim()"]());
  await tx("checkpoint(A) by anyone", pool.connect(C).checkpoint(A.address));
  await tx("A.rejectSharedVote()", pool.connect(A).rejectSharedVote());
  await tx("O.toggleVoteSharing(A)", pool.connect(O).toggleVoteSharing(A.address));
  await advance(60 * DAY);
  await tx("A.claim() 60 days later", pool.connect(A)["claim()"]());
  console.log("  base received by A:", ethers.formatEther((await base.balanceOf(A.address)) - b0));

  console.log("\n== Part 2: owner aggregate 1 wei below the stakers' sum (trace from owner_aggregate.py) ==");
  const g = await setupPool("Shareable");
  await (await g.pool.grantRole(await g.pool.VE_SHARING_ROLE(), g.O.address)).wait();
  await (await g.ve.set(g.O.address, 50n * E18)).wait();
  await tx("O.toggleVoteSharing(A)", g.pool.connect(g.O).toggleVoteSharing(g.A.address));
  await tx("O.toggleVoteSharing(B)", g.pool.connect(g.O).toggleVoteSharing(g.B.address));
  const bA = 639189062038055809266n, bB = 447474374413978216932n, other = 3960614769954294115397n;
  await tx("A.deposit(bA)", g.pool.connect(g.A).deposit(bA, g.A.address));
  await tx("B.deposit(bB)", g.pool.connect(g.B).deposit(bB, g.B.address));
  await tx("Z(D).deposit(other)", g.pool.connect(g.D).deposit(other, g.D.address));
  await tx("A.acceptSharedVote(O)", g.pool.connect(g.A).acceptSharedVote(g.O.address));
  await tx("B.acceptSharedVote(O)", g.pool.connect(g.B).acceptSharedVote(g.O.address));
  for (const L of [1225113896997647728728n, 749904313238506790301n, 639883797614578962450n]) {
    await tx(`liquidate(${L})`, g.pool.connect(g.liq).liquidate(L, 0));
    await tx("checkpoint(A)", g.pool.checkpoint(g.A.address));
  }
  await tx("checkpoint(B)", g.pool.checkpoint(g.B.address));
  const oa = (await g.pool.voteOwnerBalances(g.O.address)).amount;
  const ba = await g.pool.balanceOf(g.A.address), bb = await g.pool.balanceOf(g.B.address);
  console.log(`  owner aggregate=${oa} A=${ba} B=${bb} A+B-owner=${ba + bb - oa}`);
  await tx("A.withdraw(max)", g.pool.connect(g.A).withdraw(ethers.MaxUint256, g.A.address));
  await tx("B.withdraw(max)", g.pool.connect(g.B).withdraw(ethers.MaxUint256, g.B.address));
  await tx("B.rejectSharedVote()", g.pool.connect(g.B).rejectSharedVote());
  await tx("B.withdraw(balance - 1)", g.pool.connect(g.B).withdraw(bb - 1n, g.B.address));
  await view("balanceOf(B) left in pool", g.pool.balanceOf(g.B.address));
}

main().catch((e) => {
  console.error(e);
  process.exit(1);
});
