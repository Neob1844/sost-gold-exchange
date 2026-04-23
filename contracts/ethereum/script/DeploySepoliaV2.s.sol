// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import {Script, console} from "forge-std/Script.sol";
import {MockERC20} from "../test/MockERC20.sol";
import {SOSTEscrowV2} from "../SOSTEscrowV2.sol";

/**
 * Sepolia deployment script for SOSTEscrowV2 alpha testing.
 *
 * Deploys:
 *   1. MockERC20 "Mock XAUT" (6 decimals)  — simulates Tether Gold
 *   2. MockERC20 "Mock PAXG" (18 decimals) — simulates Paxos Gold
 *   3. SOSTEscrowV2(xaut, paxg)            — timelocked gold escrow with beneficiary support
 *
 * Usage:
 *   source .env
 *   forge script script/DeploySepoliaV2.s.sol:DeploySepoliaV2 \
 *     --rpc-url $SEPOLIA_RPC_URL \
 *     --private-key $DEPLOYER_PRIVATE_KEY \
 *     --broadcast \
 *     --verify \
 *     --etherscan-api-key $ETHERSCAN_API_KEY \
 *     -vvvv
 */
contract DeploySepoliaV2 is Script {
    function run() external {
        vm.startBroadcast();

        // 1. Deploy mock XAUT (6 decimals, matching real Tether Gold)
        MockERC20 xaut = new MockERC20("Mock XAUT", "XAUT", 6);
        console.log("MockERC20 XAUT deployed at:", address(xaut));

        // 2. Deploy mock PAXG (18 decimals, matching real Paxos Gold)
        MockERC20 paxg = new MockERC20("Mock PAXG", "PAXG", 18);
        console.log("MockERC20 PAXG deployed at:", address(paxg));

        // 3. Deploy SOSTEscrowV2 with the two mock token addresses
        SOSTEscrowV2 escrow = new SOSTEscrowV2(address(xaut), address(paxg));
        console.log("SOSTEscrowV2 deployed at:", address(escrow));

        vm.stopBroadcast();

        // Summary
        console.log("========================================");
        console.log("  Sepolia V2 Deployment Complete");
        console.log("========================================");
        console.log("  XAUT:     ", address(xaut));
        console.log("  PAXG:     ", address(paxg));
        console.log("  EscrowV2: ", address(escrow));
        console.log("========================================");
    }
}
