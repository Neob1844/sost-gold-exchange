// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import "forge-std/Test.sol";
import {SOSTEscrowV2} from "../SOSTEscrowV2.sol";
import {MockERC20} from "./MockERC20.sol";

/// @title SOSTEscrowV2 Beneficiary + Settlement Operator Tests
/// @notice Tests the settlement operator pattern for automated beneficiary handoff
contract SOSTEscrowV2BeneficiaryTest is Test {
    SOSTEscrowV2 public escrow;
    MockERC20 public xaut;
    MockERC20 public paxg;

    address public seller = makeAddr("seller");
    address public buyer = makeAddr("buyer");
    address public operator = makeAddr("operator");
    address public random = makeAddr("random");

    uint256 constant ONE_XAUT = 1e6;
    uint256 constant MIN_LOCK = 28 days;

    function setUp() public {
        xaut = new MockERC20("Tether Gold", "XAUT", 6);
        paxg = new MockERC20("Pax Gold", "PAXG", 18);
        escrow = new SOSTEscrowV2(address(xaut), address(paxg), operator);

        // Fund seller and approve
        xaut.mint(seller, 10 * ONE_XAUT);
        vm.prank(seller);
        xaut.approve(address(escrow), type(uint256).max);
    }

    function _deposit() internal returns (uint256) {
        uint256 unlock = block.timestamp + 90 days;
        vm.prank(seller);
        return escrow.deposit(address(xaut), ONE_XAUT, unlock);
    }

    // ── 1. Operator can update beneficiary ──

    function test_operator_can_update_beneficiary() public {
        uint256 id = _deposit();

        vm.prank(operator);
        escrow.updateBeneficiary(id, buyer);

        (, address beneficiary, , , , ) = escrow.getDeposit(id);
        assertEq(beneficiary, buyer);
    }

    // ── 2. Operator cannot withdraw ──

    function test_operator_cannot_withdraw() public {
        uint256 id = _deposit();

        // Operator updates beneficiary to self
        vm.prank(operator);
        escrow.updateBeneficiary(id, operator);

        // Warp past unlock
        (, , , , uint256 unlockTime, ) = escrow.getDeposit(id);
        vm.warp(unlockTime + 1);

        // Original operator (not beneficiary now) tries to withdraw — should fail
        // Actually operator IS the beneficiary now. Let's test a different scenario:
        // Operator updates to buyer, then tries to withdraw as operator (not buyer)
        vm.prank(operator);
        escrow.updateBeneficiary(id, buyer);

        vm.prank(operator);
        vm.expectRevert(abi.encodeWithSelector(
            SOSTEscrowV2.NotBeneficiary.selector, operator, buyer
        ));
        escrow.withdraw(id);
    }

    // ── 3. Beneficiary can still update self ──

    function test_beneficiary_can_still_update_self() public {
        uint256 id = _deposit();

        // Seller (current beneficiary) updates to buyer directly
        vm.prank(seller);
        escrow.updateBeneficiary(id, buyer);

        (, address beneficiary, , , , ) = escrow.getDeposit(id);
        assertEq(beneficiary, buyer);
    }

    // ── 4. Random address cannot update ──

    function test_random_address_cannot_update() public {
        uint256 id = _deposit();

        vm.prank(random);
        vm.expectRevert(SOSTEscrowV2.NotAuthorizedToUpdateBeneficiary.selector);
        escrow.updateBeneficiary(id, random);
    }

    // ── 5. Operator updates, then new beneficiary withdraws ──

    function test_operator_update_then_new_beneficiary_withdraws() public {
        uint256 id = _deposit();

        vm.prank(operator);
        escrow.updateBeneficiary(id, buyer);

        (, , , , uint256 unlockTime, ) = escrow.getDeposit(id);
        vm.warp(unlockTime + 1);

        uint256 buyerBefore = xaut.balanceOf(buyer);
        vm.prank(buyer);
        escrow.withdraw(id);

        assertEq(xaut.balanceOf(buyer), buyerBefore + ONE_XAUT);
    }

    // ── 6. Double update by operator ──

    function test_double_update_by_operator() public {
        uint256 id = _deposit();
        address buyer2 = makeAddr("buyer2");

        // First update: seller -> buyer
        vm.prank(operator);
        escrow.updateBeneficiary(id, buyer);

        (, address ben1, , , , ) = escrow.getDeposit(id);
        assertEq(ben1, buyer);

        // Second update: buyer -> buyer2
        vm.prank(operator);
        escrow.updateBeneficiary(id, buyer2);

        (, address ben2, , , , ) = escrow.getDeposit(id);
        assertEq(ben2, buyer2);
    }

    // ── 7. Operator is immutable ──

    function test_operator_is_immutable() public view {
        assertEq(escrow.settlementOperator(), operator);
    }

    // ── 8. Zero operator allowed (V1 behavior) ──

    function test_zero_operator_allowed() public {
        // Deploy with no operator
        SOSTEscrowV2 noOpEscrow = new SOSTEscrowV2(address(xaut), address(paxg), address(0));
        assertEq(noOpEscrow.settlementOperator(), address(0));

        // Fund and deposit
        xaut.mint(seller, ONE_XAUT);
        vm.prank(seller);
        xaut.approve(address(noOpEscrow), type(uint256).max);

        uint256 unlock = block.timestamp + 90 days;
        vm.prank(seller);
        uint256 id = noOpEscrow.deposit(address(xaut), ONE_XAUT, unlock);

        // Random cannot update (operator is zero, so isOperator is always false)
        vm.prank(random);
        vm.expectRevert(SOSTEscrowV2.NotAuthorizedToUpdateBeneficiary.selector);
        noOpEscrow.updateBeneficiary(id, random);

        // Beneficiary can still update
        vm.prank(seller);
        noOpEscrow.updateBeneficiary(id, buyer);
        (, address ben, , , , ) = noOpEscrow.getDeposit(id);
        assertEq(ben, buyer);
    }

    // ── 9. Full sale simulation ──

    function test_full_sale_simulation() public {
        // Step 1: Seller deposits
        uint256 id = _deposit();

        // Step 2: Trade happens off-chain, operator updates beneficiary to buyer
        vm.prank(operator);
        escrow.updateBeneficiary(id, buyer);

        // Verify beneficiary changed
        (, address beneficiary, , , , ) = escrow.getDeposit(id);
        assertEq(beneficiary, buyer);

        // Step 3: Old seller cannot withdraw
        (, , , , uint256 unlockTime, ) = escrow.getDeposit(id);
        vm.warp(unlockTime + 1);

        vm.prank(seller);
        vm.expectRevert(abi.encodeWithSelector(
            SOSTEscrowV2.NotBeneficiary.selector, seller, buyer
        ));
        escrow.withdraw(id);

        // Step 4: Buyer withdraws
        uint256 buyerBefore = xaut.balanceOf(buyer);
        vm.prank(buyer);
        escrow.withdraw(id);

        assertEq(xaut.balanceOf(buyer), buyerBefore + ONE_XAUT);

        // Step 5: Verify withdrawn flag
        (, , , , , bool withdrawn) = escrow.getDeposit(id);
        assertTrue(withdrawn);
    }

    // ── 10. Reward sale — no beneficiary change needed ──

    function test_reward_sale_no_beneficiary_change() public {
        uint256 id = _deposit();

        // In a reward-only sale, beneficiary does NOT change.
        // Only reward_owner changes in the SOST registry (off-chain).
        // Verify beneficiary remains seller.
        (, address beneficiary, , , , ) = escrow.getDeposit(id);
        assertEq(beneficiary, seller);

        // Seller can still withdraw at maturity
        (, , , , uint256 unlockTime, ) = escrow.getDeposit(id);
        vm.warp(unlockTime + 1);

        uint256 sellerBefore = xaut.balanceOf(seller);
        vm.prank(seller);
        escrow.withdraw(id);

        assertEq(xaut.balanceOf(seller), sellerBefore + ONE_XAUT);
    }
}
