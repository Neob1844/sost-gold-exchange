// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import "forge-std/Test.sol";
import {SOSTEscrow} from "../SOSTEscrow.sol";
import {MockERC20} from "./MockERC20.sol";

contract SOSTEscrowTest is Test {
    SOSTEscrow public escrow;
    MockERC20 public xaut;
    MockERC20 public paxg;

    address public alice = makeAddr("alice");
    address public bob = makeAddr("bob");

    uint256 constant XAUT_MIN = 1000;         // 0.001 oz
    uint256 constant PAXG_MIN = 1e15;          // 0.001 oz
    uint256 constant ONE_XAUT = 1e6;           // 1 oz
    uint256 constant ONE_PAXG = 1e18;          // 1 oz
    uint256 constant MIN_LOCK = 28 days;
    uint256 constant MAX_LOCK = 366 days;

    function setUp() public {
        xaut = new MockERC20("Tether Gold", "XAUT", 6);
        paxg = new MockERC20("Pax Gold", "PAXG", 18);
        escrow = new SOSTEscrow(address(xaut), address(paxg));

        // Fund alice
        xaut.mint(alice, 10 * ONE_XAUT);
        paxg.mint(alice, 10 * ONE_PAXG);

        // Alice approves escrow
        vm.startPrank(alice);
        xaut.approve(address(escrow), type(uint256).max);
        paxg.approve(address(escrow), type(uint256).max);
        vm.stopPrank();
    }

    // ── Happy path deposits ──

    function test_deposit_xaut_ok() public {
        uint256 unlock = block.timestamp + 90 days;
        vm.prank(alice);
        uint256 id = escrow.deposit(address(xaut), ONE_XAUT, unlock);

        assertEq(id, 0);
        assertEq(escrow.depositCount(), 1);
        assertEq(escrow.totalLocked(address(xaut)), ONE_XAUT);

        (address depositor, address token, uint256 amount, uint256 unlockTime, bool withdrawn) = escrow.getDeposit(0);
        assertEq(depositor, alice);
        assertEq(token, address(xaut));
        assertEq(amount, ONE_XAUT);
        assertEq(unlockTime, unlock);
        assertFalse(withdrawn);
    }

    function test_deposit_paxg_ok() public {
        uint256 unlock = block.timestamp + 90 days;
        vm.prank(alice);
        uint256 id = escrow.deposit(address(paxg), ONE_PAXG, unlock);

        assertEq(id, 0);
        assertEq(escrow.totalLocked(address(paxg)), ONE_PAXG);
    }

    // ── Happy path withdraw ──

    function test_withdraw_after_unlock() public {
        uint256 unlock = block.timestamp + 90 days;
        vm.prank(alice);
        escrow.deposit(address(xaut), ONE_XAUT, unlock);

        // Warp past unlock
        vm.warp(unlock + 1);

        uint256 balBefore = xaut.balanceOf(alice);
        vm.prank(alice);
        escrow.withdraw(0);

        assertEq(xaut.balanceOf(alice), balBefore + ONE_XAUT);
        assertEq(escrow.totalLocked(address(xaut)), 0);

        (, , , , bool withdrawn) = escrow.getDeposit(0);
        assertTrue(withdrawn);
    }

    function test_withdraw_exact_unlock_time() public {
        uint256 unlock = block.timestamp + MIN_LOCK;
        vm.prank(alice);
        escrow.deposit(address(xaut), ONE_XAUT, unlock);

        // Warp to exactly unlockTime (>= should work)
        vm.warp(unlock);
        vm.prank(alice);
        escrow.withdraw(0);

        (, , , , bool withdrawn) = escrow.getDeposit(0);
        assertTrue(withdrawn);
    }

    // ── Revert: withdraw before unlock ──

    function test_revert_withdraw_before_unlock() public {
        uint256 unlock = block.timestamp + 90 days;
        vm.prank(alice);
        escrow.deposit(address(xaut), ONE_XAUT, unlock);

        vm.prank(alice);
        vm.expectRevert(abi.encodeWithSelector(
            SOSTEscrow.StillLocked.selector, unlock, block.timestamp
        ));
        escrow.withdraw(0);
    }

    // ── Revert: token not allowed ──

    function test_revert_token_not_allowed() public {
        MockERC20 fake = new MockERC20("Fake", "FAKE", 18);
        fake.mint(alice, 1e18);
        vm.startPrank(alice);
        fake.approve(address(escrow), type(uint256).max);

        vm.expectRevert(abi.encodeWithSelector(
            SOSTEscrow.TokenNotAllowed.selector, address(fake)
        ));
        escrow.deposit(address(fake), 1e18, block.timestamp + 90 days);
        vm.stopPrank();
    }

    // ── Revert: below minimum ──

    function test_revert_below_minimum_xaut() public {
        vm.prank(alice);
        vm.expectRevert(abi.encodeWithSelector(
            SOSTEscrow.AmountBelowMinimum.selector, XAUT_MIN - 1, XAUT_MIN
        ));
        escrow.deposit(address(xaut), XAUT_MIN - 1, block.timestamp + 90 days);
    }

    function test_revert_below_minimum_paxg() public {
        vm.prank(alice);
        vm.expectRevert(abi.encodeWithSelector(
            SOSTEscrow.AmountBelowMinimum.selector, PAXG_MIN - 1, PAXG_MIN
        ));
        escrow.deposit(address(paxg), PAXG_MIN - 1, block.timestamp + 90 days);
    }

    // ── Revert: lock duration ──

    function test_revert_lock_too_short() public {
        uint256 unlock = block.timestamp + MIN_LOCK - 1;
        vm.prank(alice);
        vm.expectRevert(abi.encodeWithSelector(
            SOSTEscrow.LockDurationTooShort.selector, MIN_LOCK - 1, MIN_LOCK
        ));
        escrow.deposit(address(xaut), ONE_XAUT, unlock);
    }

    function test_revert_lock_too_long() public {
        uint256 unlock = block.timestamp + MAX_LOCK + 1;
        vm.prank(alice);
        vm.expectRevert(abi.encodeWithSelector(
            SOSTEscrow.LockDurationTooLong.selector, MAX_LOCK + 1, MAX_LOCK
        ));
        escrow.deposit(address(xaut), ONE_XAUT, unlock);
    }

    // ── Revert: transferFrom fails ──

    function test_revert_transferFrom_fails() public {
        xaut.setShouldFailTransferFrom(true);

        vm.prank(alice);
        vm.expectRevert(SOSTEscrow.TransferFailed.selector);
        escrow.deposit(address(xaut), ONE_XAUT, block.timestamp + 90 days);
    }

    // ── Revert: double withdraw ──

    function test_revert_double_withdraw() public {
        uint256 unlock = block.timestamp + MIN_LOCK;
        vm.prank(alice);
        escrow.deposit(address(xaut), ONE_XAUT, unlock);

        vm.warp(unlock);
        vm.prank(alice);
        escrow.withdraw(0);

        vm.prank(alice);
        vm.expectRevert(abi.encodeWithSelector(
            SOSTEscrow.AlreadyWithdrawn.selector, 0
        ));
        escrow.withdraw(0);
    }

    // ── Revert: not depositor ──

    function test_revert_not_depositor() public {
        uint256 unlock = block.timestamp + 90 days;
        vm.prank(alice);
        escrow.deposit(address(xaut), ONE_XAUT, unlock);

        vm.warp(unlock + 1);
        vm.prank(bob);
        vm.expectRevert(abi.encodeWithSelector(
            SOSTEscrow.NotDepositor.selector, bob, alice
        ));
        escrow.withdraw(0);
    }

    // ── totalLocked updates correctly ──

    function test_totalLocked_updates() public {
        uint256 unlock = block.timestamp + 90 days;

        vm.startPrank(alice);
        escrow.deposit(address(xaut), ONE_XAUT, unlock);
        escrow.deposit(address(xaut), ONE_XAUT, unlock);
        vm.stopPrank();

        assertEq(escrow.totalLocked(address(xaut)), 2 * ONE_XAUT);

        vm.warp(unlock);
        vm.prank(alice);
        escrow.withdraw(0);

        assertEq(escrow.totalLocked(address(xaut)), ONE_XAUT);
    }

    // ── Events emitted correctly ──

    function test_events_emitted() public {
        uint256 unlock = block.timestamp + 90 days;

        vm.expectEmit(true, true, true, true);
        emit SOSTEscrow.GoldDeposited(0, alice, address(xaut), ONE_XAUT, unlock);

        vm.prank(alice);
        escrow.deposit(address(xaut), ONE_XAUT, unlock);

        vm.warp(unlock);
        vm.expectEmit(true, true, false, true);
        emit SOSTEscrow.GoldWithdrawn(0, alice, address(xaut), ONE_XAUT);

        vm.prank(alice);
        escrow.withdraw(0);
    }

    // ── View functions ──

    function test_getUserDepositIds() public {
        uint256 unlock = block.timestamp + 90 days;
        vm.startPrank(alice);
        escrow.deposit(address(xaut), ONE_XAUT, unlock);
        escrow.deposit(address(paxg), ONE_PAXG, unlock);
        escrow.deposit(address(xaut), XAUT_MIN, unlock);
        vm.stopPrank();

        uint256[] memory ids = escrow.getUserDepositIds(alice);
        assertEq(ids.length, 3);
        assertEq(ids[0], 0);
        assertEq(ids[1], 1);
        assertEq(ids[2], 2);
    }

    function test_canWithdraw() public {
        uint256 unlock = block.timestamp + 90 days;
        vm.prank(alice);
        escrow.deposit(address(xaut), ONE_XAUT, unlock);

        assertFalse(escrow.canWithdraw(0));

        vm.warp(unlock);
        assertTrue(escrow.canWithdraw(0));

        vm.prank(alice);
        escrow.withdraw(0);
        assertFalse(escrow.canWithdraw(0));  // already withdrawn
    }

    // ── Deposit not found ──

    function test_revert_deposit_not_found() public {
        vm.prank(alice);
        vm.expectRevert(abi.encodeWithSelector(
            SOSTEscrow.DepositNotFound.selector, 999
        ));
        escrow.withdraw(999);
    }

    // ── Unlock time not in future ──

    function test_revert_unlock_not_in_future() public {
        vm.prank(alice);
        vm.expectRevert(abi.encodeWithSelector(
            SOSTEscrow.UnlockTimeNotInFuture.selector, block.timestamp, block.timestamp
        ));
        escrow.deposit(address(xaut), ONE_XAUT, block.timestamp);
    }
}
