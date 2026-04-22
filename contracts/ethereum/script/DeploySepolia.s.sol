// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import {Script, console} from "forge-std/Script.sol";
import {MockERC20} from "../test/MockERC20.sol";
import {SOSTEscrow} from "../SOSTEscrow.sol";

/**
 * Sepolia deployment script for SOST Gold Exchange alpha testing.
 *
 * Deploys:
 *   1. MockERC20 "Mock XAUT" (6 decimals)  — simulates Tether Gold
 *   2. MockERC20 "Mock PAXG" (18 decimals) — simulates Paxos Gold
 *   3. SOSTEscrow(xaut, paxg)              — timelocked gold escrow
 *
 * Usage:
 *   source .env
 *   forge script script/DeploySepolia.s.sol:DeploySepolia \
 *     --rpc-url $SEPOLIA_RPC_URL \
 *     --private-key $DEPLOYER_PRIVATE_KEY \
 *     --broadcast \
 *     --verify \
 *     --etherscan-api-key $ETHERSCAN_API_KEY \
 *     -vvvv
 */
contract DeploySepolia is Script {
    function run() external {
        vm.startBroadcast();

        // 1. Deploy mock XAUT (6 decimals, matching real Tether Gold)
        MockERC20 xaut = new MockERC20("Mock XAUT", "XAUT", 6);
        console.log("MockERC20 XAUT deployed at:", address(xaut));

        // 2. Deploy mock PAXG (18 decimals, matching real Paxos Gold)
        MockERC20 paxg = new MockERC20("Mock PAXG", "PAXG", 18);
        console.log("MockERC20 PAXG deployed at:", address(paxg));

        // 3. Deploy SOSTEscrow with the two mock token addresses
        SOSTEscrow escrow = new SOSTEscrow(address(xaut), address(paxg));
        console.log("SOSTEscrow deployed at:", address(escrow));

        vm.stopBroadcast();

        // Summary
        console.log("========================================");
        console.log("  Sepolia Deployment Complete");
        console.log("========================================");
        console.log("  XAUT:   ", address(xaut));
        console.log("  PAXG:   ", address(paxg));
        console.log("  Escrow: ", address(escrow));
        console.log("========================================");
    }
}
