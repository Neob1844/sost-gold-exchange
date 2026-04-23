// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import "forge-std/Test.sol";
import {SOSTEscrowV2} from "../SOSTEscrowV2.sol";
import {MockERC20} from "./MockERC20.sol";

contract SOSTEscrowV2Test is Test {
    SOSTEscrowV2 public escrow;
    MockERC20 public xaut;
    MockERC20 public paxg;

    address public alice = makeAddr("alice");
    address public bob = makeAddr("bob");
    address public charlie = makeAddr("charlie");

    uint256 constant XAUT_MIN = 1000;
    uint256 constant PAXG_MIN = 1e15;
    uint256 constant ONE_XAUT = 1e6;
    uint256 constant ONE_PAXG = 1e18;
    uint256 constant MIN_LOCK = 28 days;
    uint256 constant MAX_LOCK = 366 days;

    function setUp() public {
        xaut = new MockERC20("Tether Gold", "XAUT", 6);
        paxg = new MockERC20("Pax Gold", "PAXG", 18);
        escrow = new SOSTEscrowV2(address(xaut), address(paxg));

        // Fund alice
        xaut.mint(alice, 10 * ONE_XAUT);
        paxg.mint(alice, 10 * ONE_PAXG);

        // Alice approves escrow
        vm.startPrank(alice);
        xaut.approve(address(escrow), type(uint256).max);
        paxg.approve(address(escrow), type(uint256).max);
        vm.stopPrank();
    }

    // ── Beneficiary tests ──

    function test_deposit_sets_beneficiary_to_sender() public {
        uint256 unlock = block.timestamp + 90 days;
        vm.prank(alice);
        uint256 id = escrow.deposit(address(xaut), ONE_XAUT, unlock);

        (address depositor, address beneficiary, , , , ) = escrow.getDeposit(id);
        assertEq(depositor, alice);
        assertEq(beneficiary, alice);
    }

    function test_depositFor_sets_custom_beneficiary() public {
        uint256 unlock = block.timestamp + 90 days;
        vm.prank(alice);
        uint256 id = escrow.depositFor(address(xaut), ONE_XAUT, unlock, bob);

        (address depositor, address beneficiary, , , , ) = escrow.getDeposit(id);
        assertEq(depositor, alice);
        assertEq(beneficiary, bob);
    }

    function test_withdraw_pays_beneficiary_not_depositor() public {
        uint256 unlock = block.timestamp + 90 days;
        vm.prank(alice);
        uint256 id = escrow.depositFor(address(xaut), ONE_XAUT, unlock, bob);

        vm.warp(unlock + 1);

        uint256 bobBefore = xaut.balanceOf(bob);
        uint256 aliceBefore = xaut.balanceOf(alice);

        vm.prank(bob);
        escrow.withdraw(id);

        assertEq(xaut.balanceOf(bob), bobBefore + ONE_XAUT);
        assertEq(xaut.balanceOf(alice), aliceBefore); // alice gets nothing
    }

    function test_updateBeneficiary_by_current_beneficiary() public {
        uint256 unlock = block.timestamp + 90 days;
        vm.prank(alice);
        uint256 id = escrow.deposit(address(xaut), ONE_XAUT, unlock);

        vm.prank(alice);
        escrow.updateBeneficiary(id, bob);

        (, address beneficiary, , , , ) = escrow.getDeposit(id);
        assertEq(beneficiary, bob);
    }

    function test_updateBeneficiary_by_non_beneficiary_fails() public {
        uint256 unlock = block.timestamp + 90 days;
        vm.prank(alice);
        uint256 id = escrow.deposit(address(xaut), ONE_XAUT, unlock);

        vm.prank(bob);
        vm.expectRevert(abi.encodeWithSelector(
            SOSTEscrowV2.NotBeneficiary.selector, bob, alice
        ));
        escrow.updateBeneficiary(id, charlie);
    }

    function test_updateBeneficiary_to_zero_address_fails() public {
        uint256 unlock = block.timestamp + 90 days;
        vm.prank(alice);
        uint256 id = escrow.deposit(address(xaut), ONE_XAUT, unlock);

        vm.prank(alice);
        vm.expectRevert(SOSTEscrowV2.ZeroAddress.selector);
        escrow.updateBeneficiary(id, address(0));
    }

    function test_withdraw_after_beneficiary_change() public {
        uint256 unlock = block.timestamp + 90 days;
        vm.prank(alice);
        uint256 id = escrow.deposit(address(xaut), ONE_XAUT, unlock);

        // Alice transfers beneficiary to bob
        vm.prank(alice);
        escrow.updateBeneficiary(id, bob);

        vm.warp(unlock + 1);

        uint256 bobBefore = xaut.balanceOf(bob);
        vm.prank(bob);
        escrow.withdraw(id);

        assertEq(xaut.balanceOf(bob), bobBefore + ONE_XAUT);
    }

    function test_beneficiary_updated_event() public {
        uint256 unlock = block.timestamp + 90 days;
        vm.prank(alice);
        uint256 id = escrow.deposit(address(xaut), ONE_XAUT, unlock);

        vm.expectEmit(true, false, false, true);
        emit SOSTEscrowV2.BeneficiaryUpdated(id, alice, bob);

        vm.prank(alice);
        escrow.updateBeneficiary(id, bob);
    }

    // ── Standard deposit tests (same as v1) ──

    function test_deposit_xaut_ok() public {
        uint256 unlock = block.timestamp + 90 days;
        vm.prank(alice);
        uint256 id = escrow.deposit(address(xaut), ONE_XAUT, unlock);

        assertEq(id, 0);
        assertEq(escrow.depositCount(), 1);
        assertEq(escrow.totalLocked(address(xaut)), ONE_XAUT);

        (address depositor, address beneficiary, address token, uint256 amount, uint256 unlockTime, bool withdrawn) = escrow.getDeposit(0);
        assertEq(depositor, alice);
        assertEq(beneficiary, alice);
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

    // ── Revert tests ──

    function test_revert_token_not_allowed() public {
        MockERC20 fake = new MockERC20("Fake", "FAKE", 18);
        fake.mint(alice, 1e18);
        vm.startPrank(alice);
        fake.approve(address(escrow), type(uint256).max);

        vm.expectRevert(abi.encodeWithSelector(
            SOSTEscrowV2.TokenNotAllowed.selector, address(fake)
        ));
        escrow.deposit(address(fake), 1e18, block.timestamp + 90 days);
        vm.stopPrank();
    }

    function test_revert_below_minimum() public {
        vm.prank(alice);
        vm.expectRevert(abi.encodeWithSelector(
            SOSTEscrowV2.AmountBelowMinimum.selector, XAUT_MIN - 1, XAUT_MIN
        ));
        escrow.deposit(address(xaut), XAUT_MIN - 1, block.timestamp + 90 days);
    }

    function test_revert_lock_too_short() public {
        uint256 unlock = block.timestamp + MIN_LOCK - 1;
        vm.prank(alice);
        vm.expectRevert(abi.encodeWithSelector(
            SOSTEscrowV2.LockDurationTooShort.selector, MIN_LOCK - 1, MIN_LOCK
        ));
        escrow.deposit(address(xaut), ONE_XAUT, unlock);
    }

    function test_revert_lock_too_long() public {
        uint256 unlock = block.timestamp + MAX_LOCK + 1;
        vm.prank(alice);
        vm.expectRevert(abi.encodeWithSelector(
            SOSTEscrowV2.LockDurationTooLong.selector, MAX_LOCK + 1, MAX_LOCK
        ));
        escrow.deposit(address(xaut), ONE_XAUT, unlock);
    }

    function test_revert_before_unlock() public {
        uint256 unlock = block.timestamp + 90 days;
        vm.prank(alice);
        escrow.deposit(address(xaut), ONE_XAUT, unlock);

        vm.prank(alice);
        vm.expectRevert(abi.encodeWithSelector(
            SOSTEscrowV2.StillLocked.selector, unlock, block.timestamp
        ));
        escrow.withdraw(0);
    }

    function test_revert_double_withdraw() public {
        uint256 unlock = block.timestamp + MIN_LOCK;
        vm.prank(alice);
        escrow.deposit(address(xaut), ONE_XAUT, unlock);

        vm.warp(unlock);
        vm.prank(alice);
        escrow.withdraw(0);

        vm.prank(alice);
        vm.expectRevert(abi.encodeWithSelector(
            SOSTEscrowV2.AlreadyWithdrawn.selector, 0
        ));
        escrow.withdraw(0);
    }

    function test_revert_not_beneficiary_withdraw() public {
        uint256 unlock = block.timestamp + 90 days;
        vm.prank(alice);
        escrow.deposit(address(xaut), ONE_XAUT, unlock);

        vm.warp(unlock + 1);

        // Bob is NOT the beneficiary — should revert
        vm.prank(bob);
        vm.expectRevert(abi.encodeWithSelector(
            SOSTEscrowV2.NotBeneficiary.selector, bob, alice
        ));
        escrow.withdraw(0);
    }

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
}
